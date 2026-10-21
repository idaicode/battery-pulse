"""Battery Pulse —— 桌面电量面板。

用法：
    pythonw app.py             # 桌面窗口 + 托盘（默认）
    pythonw app.py --tray      # 只托盘，不起 WebView（最省内存）
    pythonw app.py --hidden    # 桌面窗口不开，只在托盘常驻
    python app.py --no-open    # 只起 HTTP 服务（调试用）
"""
from __future__ import annotations

import argparse
import ctypes
import json
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# 打包后：资源在 _internal（只读），配置/日志写在 exe 旁边（便携、可备份）
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
    RES_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    APP_DIR = RES_DIR = Path(__file__).resolve().parent

# 全进程统一用 Per-Monitor-V2：否则 pywebview 抢先设成别的模式后，
# 托盘算出来的缩放比会和实际窗口不符，自绘菜单的点击坐标全部落空。
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass

ROOT = APP_DIR
sys.path.insert(0, str(RES_DIR))
sys.path.insert(0, str(APP_DIR))

from core import __version__, autostart  # noqa: E402
from core.manager import Manager  # noqa: E402

UI_FILE = RES_DIR / "ui" / "index.html"

MANAGER: Manager | None = None
SERVER: ThreadingHTTPServer | None = None
TRAY = None
PANEL_API = None


def _state() -> dict:
    state = MANAGER.snapshot()
    state["meta"]["tray_icons"] = TRAY.icon_count if TRAY is not None else 0
    return state


class Handler(BaseHTTPRequestHandler):
    server_version = f"BatteryPulse/{__version__}"
    protocol_version = "HTTP/1.1"

    # 静音访问日志：减少后台 IO
    def log_message(self, fmt, *args):
        pass

    def _send(self, body: bytes, ctype: str = "application/json; charset=utf-8", code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, data, code: int = 200):
        self._send(json.dumps(data, ensure_ascii=False).encode("utf-8"), code=code)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/ping":
            self._send(b'{"pong":true}')
            return
        if path in ("/", "/index.html"):
            try:
                self._send(UI_FILE.read_bytes(), "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(b"<h1>ui/index.html missing</h1>", "text/html; charset=utf-8", 500)
            return
        if path == "/api/state":
            MANAGER.touch()
            self._json(_state())
            return
        if path in ("/favicon.ico", "/app.ico"):
            try:
                self._send((RES_DIR / "ui" / "app.ico").read_bytes(), "image/x-icon")
            except FileNotFoundError:
                self._send(b"", "image/x-icon", 204)
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {}

        MANAGER.touch()
        if path == "/api/config":
            cfg = MANAGER.update_config(payload)
            MANAGER.refresh()
            self._json({"ok": True, "config": cfg})
            return
        if path == "/api/refresh":
            MANAGER.refresh()
            self._json(_state())
            return
        if path == "/api/scan":
            found = MANAGER.scan_ble()
            self._json({"ok": True, "found": found, "state": _state()})
            return
        if path == "/api/trim":
            self._json({"ok": True, "result": MANAGER.trim(), "state": _state()})
            return
        if path == "/api/test-notify":
            MANAGER.test_notify()
            self._json({"ok": True})
            return
        if path == "/api/show":
            _show_panel()
            self._json({"ok": True})
            return
        if path == "/api/shutdown":
            self._json({"ok": True})
            threading.Thread(target=_shutdown_soon, daemon=True).start()
            return
        self._json({"error": "not found"}, 404)


def _shutdown_soon() -> None:
    time.sleep(0.35)
    if TRAY is not None:
        TRAY.quit()
    if SERVER is not None:
        SERVER.shutdown()


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _already_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def _pythonw_path() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        cand = exe.with_name("pythonw.exe")
        if cand.exists():
            return str(cand)
    return str(exe)


def _find_panel_window():
    """找主面板窗口（含已被隐藏的 —— 隐藏的窗口正是最需要找回来的）。"""
    import ctypes
    from ctypes import wintypes

    u = ctypes.WinDLL("user32", use_last_error=True)
    u.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
    u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    found = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, buf, 256)
        if buf.value.strip() != "Battery Pulse":
            return True
        cls = ctypes.create_unicode_buffer(128)
        u.GetClassNameW(hwnd, cls, 128)
        # 托盘的隐藏消息窗标题也叫 Battery Pulse，别把它当成面板
        if cls.value == "BatteryPulseTrayWnd":
            return True
        found.append((1 if u.IsWindowVisible(hwnd) else 0, hwnd))
        return True

    u.EnumWindows(ctypes.cast(proc(cb), ctypes.c_void_p), 0)
    if not found:
        return None
    found.sort(reverse=True)  # 可见的优先
    return found[0][1]


def _activate_window(hwnd) -> bool:
    """显示并带到最前（走和面板同一套前台锁绕行逻辑）。"""
    from core.desktop import force_foreground

    try:
        force_foreground(hwnd)
        return True
    except Exception:
        return False


_last_spawn = 0.0


def _spawn_panel() -> None:
    """纯托盘模式下来点“打开面板”：另起一个只负责窗口的进程，复用已有服务。"""
    global _last_spawn
    now = time.time()
    if now - _last_spawn < 4:
        return  # 连点两下别起两个窗口进程：同一个 WebView2 用户目录不能两开
    _last_spawn = now

    if getattr(sys, "frozen", False):
        args = [sys.executable, "--panel-only"]
    else:
        args = [_pythonw_path(), str(RES_DIR / "app.py"), "--panel-only"]
    if TRAY is not None:
        # WebView2 冷启动要好几秒，不给提示用户会以为点了没反应
        TRAY.balloon("Battery Pulse", "面板正在打开，首次启动需要几秒…")
    try:
        subprocess.Popen(
            args,
            cwd=str(APP_DIR),
            close_fds=True,
            creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | NEW_PROCESS_GROUP
        )
    except Exception:
        pass


def _show_panel() -> None:
    if PANEL_API is not None:
        PANEL_API.show_panel()
        return
    hwnd = _find_panel_window()
    if hwnd and _activate_window(hwnd):
        return
    _spawn_panel()


def _running_port(default: int) -> int:
    """扫一遍候选端口，找正在跑的服务。"""
    for candidate in [default] + list(range(8731, 8743)):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{candidate}/ping", timeout=0.6) as r:
                if r.status == 200:
                    return candidate
        except Exception:
            continue
    return default


def _run_panel_only(port: int) -> int:
    """只开窗口，不起服务、不建托盘。关掉窗口进程即退出。"""
    from core import desktop

    url = f"http://127.0.0.1:{port}/"
    desktop.run(lambda api: None, url, storage_dir=str(APP_DIR / "data" / "webview2"))
    return 0


def _wake_existing(port: int, want_panel: bool) -> None:
    """已有实例在跑：把它的面板叫到前台，而不是再开一个。"""
    if not want_panel:
        return
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/show",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=2).read()
    except Exception:
        pass


def _run_desktop(port: int, hidden: bool) -> int:
    """主线程跑 WebView2 消息循环，HTTP 服务与托盘在后台线程。"""
    global SERVER, TRAY, PANEL_API
    from core import desktop

    url = f"http://127.0.0.1:{port}/"

    # 服务先起来，不赌 WebView 初始化是否顺利
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    SERVER = server
    threading.Thread(target=server.serve_forever, name="http", daemon=True).start()

    def start_backend(api) -> None:
        global TRAY, PANEL_API
        PANEL_API = api

        from core.tray import Tray

        def quit_all() -> None:
            time.sleep(0.2)
            try:
                server.shutdown()
            except Exception:
                pass
            api.destroy()

        TRAY = Tray(MANAGER, lambda: url, on_exit=quit_all, on_open=api.show_panel)
        MANAGER.add_listener(TRAY.post_update)
        if not TRAY.start():
            TRAY = None

    try:
        desktop.run(start_backend, url, hidden=hidden, storage_dir=str(APP_DIR / "data" / "webview2"))
    except Exception as exc:
        # WebView2 起不来时别把服务带走
        print(f"桌面窗口启动失败：{exc}", file=sys.stderr)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass

    MANAGER.stop()
    try:
        server.server_close()
    except Exception:
        pass
    return 0


def main() -> int:
    global MANAGER, SERVER, TRAY
    ap = argparse.ArgumentParser(description="Battery Pulse")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--no-open", action="store_true", help="只起 HTTP 服务")
    ap.add_argument("--tray", action="store_true", help="只常驻托盘，不起桌面窗口")
    ap.add_argument("--hidden", action="store_true", help="启动时不显示桌面窗口")
    ap.add_argument("--panel-only", action="store_true", help="只开窗口，复用已在运行的服务")
    ap.add_argument("--autostart", choices=("on", "off", "status"), help="开机自启开关")
    args = ap.parse_args()

    if args.autostart:
        if args.autostart == "status":
            print("开机自启：", "已开启" if autostart.enabled() else "已关闭")
        elif args.autostart == "on":
            print("开机自启：", "已开启" if autostart.enable() else "设置失败")
        else:
            print("开机自启：", "已关闭" if autostart.disable() else "取消失败")
        return 0

    MANAGER = Manager()

    # 只开窗口：连已有服务，不重复起服务/托盘
    if args.panel_only:
        return _run_panel_only(_running_port(int(MANAGER.cfg.get("port", 8731))))

    port = args.port or int(MANAGER.cfg.get("port", 8731))

    if not _port_free(port):
        if _already_running(port):
            _wake_existing(port, want_panel=not (args.tray or args.no_open))
            return 0
        for candidate in range(port + 1, port + 12):
            if _port_free(candidate):
                port = candidate
                break
        else:
            print("没有可用端口", file=sys.stderr)
            return 1

    MANAGER.cfg["port"] = port
    MANAGER.start()

    # 桌面窗口模式（默认）
    if not args.tray and not args.no_open:
        return _run_desktop(port, hidden=args.hidden)

    # ---- 纯服务 / 纯托盘 ----
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    SERVER = server
    url = f"http://127.0.0.1:{port}/"

    http_thread = threading.Thread(target=server.serve_forever, name="http", daemon=True)
    http_thread.start()

    if args.tray:
        from core.tray import Tray

        def _quit_from_tray():
            time.sleep(0.2)
            try:
                server.shutdown()
            except Exception:
                pass

        TRAY = Tray(MANAGER, lambda: url, on_exit=_quit_from_tray, on_open=_show_panel)
        MANAGER.add_listener(TRAY.post_update)
        if not TRAY.start():
            print("托盘创建失败，回退到普通模式", file=sys.stderr)
            TRAY = None

    if not args.no_open and not args.tray:
        webbrowser.open(url)
    print(f"Battery Pulse 运行中：{url}")
    try:
        while http_thread.is_alive():
            http_thread.join(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        MANAGER.stop()
        if TRAY is not None:
            TRAY.quit()
        try:
            server.server_close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
