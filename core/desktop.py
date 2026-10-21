"""WebView2 桌面窗口外壳。

关键点：
- 窗口是 frameless 的，标题栏由 ui/index.html 自己画（`.titlebar`），
  拖动靠 pywebview 内置的 `.pywebview-drag-region`；
- Edge WebView2 在这类环境下需要禁用 GPU 合成，否则渲染进程会崩、窗口全黑；
- 窗口关闭 = 隐藏到托盘，不是退出；真正退出走托盘菜单。

⚠️ 窗口操作一律走 ctypes + HWND，不要碰 `window.on_top` / `window.show()`
这类 pythonnet 属性。原因是一处很容易踩死的死锁：

    JS 调用 pywebview.api.* 后，pywebview 在**新线程**里执行我们的方法
    （util.js_bridge_call._call）。若该线程去写 WinForms 属性（如 TopMost），
    WinForms 会把这次写入封送到 UI 线程；而 UI 线程上挂着 pywebview 注册的
    `timer.Tick += timer_tick` —— 那是个 **Python 回调**，要跑起来必须先拿 GIL。
    可是 GIL 正被这个卡在属性写入里的线程持有 → 两边互等，永久死锁。
    现象：窗口正常显示过，随后 HTTP 服务"假死"（端口还 LISTENING，连接堆在
    backlog，CPU 占用 0），所有 Python 线程一起冻住。

ctypes 调用会释放 GIL，且 ShowWindow / SetWindowPos / PostMessage 都是窗口管理器
层面的操作，不依赖 Python 回调，因此从任意线程调用都安全。
"""
from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes

# 必须在 import webview 之前设置（WebView2 启动时读这个环境变量）
# 只加 --disable-gpu 不够：这台机器上 RendererCodeIntegrity 会让渲染进程直接崩，
# 表现是窗口正常创建但整块全黑。必须显式关掉代码完整性校验。
os.environ.setdefault(
    "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
    "--disable-gpu --no-sandbox --disable-features=RendererCodeIntegrity",
)

BG = "#F0EEE6"

# ---------------- Win32 ----------------
_u = ctypes.WinDLL("user32", use_last_error=True)
_k = ctypes.WinDLL("kernel32", use_last_error=True)
_u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_u.FindWindowW.restype = wintypes.HWND
_u.IsWindow.argtypes = [wintypes.HWND]
_u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_u.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
_u.SetForegroundWindow.argtypes = [wintypes.HWND]
_u.SetForegroundWindow.restype = wintypes.BOOL
_u.GetForegroundWindow.restype = wintypes.HWND
_u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_u.GetWindowThreadProcessId.restype = wintypes.DWORD
_u.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
_u.AttachThreadInput.restype = wintypes.BOOL
_u.IsIconic.argtypes = [wintypes.HWND]
_u.IsIconic.restype = wintypes.BOOL
_u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_u.GetWindowRect.restype = wintypes.BOOL
_u.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
_u.MonitorFromWindow.restype = wintypes.HMONITOR
_u.MonitorFromRect.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
_u.MonitorFromRect.restype = wintypes.HMONITOR
_u.BringWindowToTop.argtypes = [wintypes.HWND]
_u.BringWindowToTop.restype = wintypes.BOOL
_u.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
_u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_u.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
_u.SystemParametersInfoW.restype = wintypes.BOOL
_k.GetCurrentThreadId.restype = wintypes.DWORD

HWND_TOPMOST = wintypes.HWND(-1)
HWND_NOTOPMOST = wintypes.HWND(-2)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_ASYNCWINDOWPOS = 0x4000  # 跨线程时不阻塞发送方 —— 这里很关键
SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9
WM_CLOSE = 0x0010
SPI_GETWORKAREA = 0x0030
MONITOR_DEFAULTTONULL = 0


# ---------------- 窗口显示 ----------------
TRAY_CLASS = "BatteryPulseTrayWnd"
_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _class_of(h) -> str:
    buf = ctypes.create_unicode_buffer(128)
    _u.GetClassNameW(h, buf, 128)
    return buf.value


def _title_of(h) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _u.GetWindowTextW(h, buf, 256)
    return buf.value.strip()


def _find_panel_hwnd(title: str = "Battery Pulse"):
    """找真正的面板窗口。

    不能用 `FindWindowW(None, title)`：托盘的隐藏消息窗**标题也是**
    "Battery Pulse"，它比面板先建出来，FindWindowW 很可能就返回它。之后
    ShowWindow / SetWindowPos / 居中全部作用在一个 202x56 的不可见窗口上，
    用户侧的症状就是「点了打开面板，什么都没发生」。
    所以按类名排除托盘窗口，并且要求尺寸像个真窗口。
    """
    found = []

    def _cb(h, _):
        if _title_of(h) != title or _class_of(h) == TRAY_CLASS:
            return True
        r = wintypes.RECT()
        if _u.GetWindowRect(h, ctypes.byref(r)) and (r.right - r.left) > 8:
            found.append(h)
        return True

    _u.EnumWindows(ctypes.cast(_ENUM_PROC(_cb), ctypes.c_void_p), 0)
    return found[0] if found else None


def _workarea() -> tuple[int, int, int, int]:
    """可用工作区（物理像素，已扣掉任务栏）。"""
    r = wintypes.RECT()
    _u.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0)
    return r.left, r.top, r.right, r.bottom


def _dpi_scale() -> float:
    """主显示器缩放。问显示器而不是进程，避免受 DPI 感知模式影响。"""
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        _u.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        _u.MonitorFromPoint.restype = wintypes.HMONITOR
        mon = _u.MonitorFromPoint(wintypes.POINT(0, 0), 2)  # MONITOR_DEFAULTTOPRIMARY
        dx = ctypes.c_uint()
        dy = ctypes.c_uint()
        shcore.GetDpiForMonitor(mon, 0, ctypes.byref(dx), ctypes.byref(dy))
        if dx.value:
            return max(1.0, dx.value / 96.0)
    except Exception:
        pass
    return 1.0


def fit_size(width: int, height: int, margin: int = 32) -> tuple[int, int]:
    """按工作区收缩默认尺寸。

    pywebview 的尺寸是**逻辑像素**：150% 缩放下 828 高会变成 1242 物理像素，
    在 1080p 屏幕上直接顶穿任务栏，底部按钮点不到。这里按实际工作区封顶。
    """
    s = _dpi_scale()
    left, top, right, bottom = _workarea()
    max_w = int((right - left) / s) - margin
    max_h = int((bottom - top) / s) - margin
    return min(width, max(560, max_w)), min(height, max(480, max_h))


def center_on_screen(width: int, height: int) -> tuple[int, int]:
    """逻辑坐标的居中位置（多显示器时落在主屏）。"""
    s = _dpi_scale()
    left, top, right, bottom = _workarea()
    x = left + max(0, int((right - left - width * s) / 2))
    y = top + max(0, int((bottom - top - height * s) / 2))
    return int(x / s), int(y / s)


def _center_window(h) -> None:
    """把窗口挪到工作区正中。

    不用 `create_window(x=, y=)` 定位：源码态它是对的，打包后 pywebview 会忽略
    这两个参数、退回 Windows 的级联位置（(190,190) 起每次 +38），于是窗口贴在
    左上角。直接用 SetWindowPos 定死，两个环境表现一致。
    """
    r = wintypes.RECT()
    if not _u.GetWindowRect(h, ctypes.byref(r)):
        return
    w, hh = r.right - r.left, r.bottom - r.top
    left, top, right, bottom = _workarea()
    x = left + max(0, (right - left - w) // 2)
    y = top + max(0, (bottom - top - hh) // 2)
    _u.SetWindowPos(h, None, x, y, 0, 0,
                    SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS)


def _ensure_on_screen(h) -> None:
    """窗口完全落在所有显示器之外时挪回主屏。

    显示器拔掉、分辨率变化后经常出现：窗口"显示"了但坐落在不存在的坐标上，
    用户侧完全没有视觉反馈，和死机没区别。

    判断用 MonitorFromRect（窗口矩形与显示器是否有交集），不用
    MonitorFromWindow：后者在非前台线程里会按窗口中心点算，窗口被移到屏幕边缘
    时容易误判成"无显示器"，进而触发一次不必要的重定位，把窗口位置挪偏。
    """
    r = wintypes.RECT()
    if not _u.GetWindowRect(h, ctypes.byref(r)):
        return
    if _u.MonitorFromRect(ctypes.byref(r), MONITOR_DEFAULTTONULL):
        return
    _center_window(h)


def force_foreground(h) -> bool:
    """把窗口显示出来并带到最前。

    Windows 的前台锁：只有当前持有前台窗口的进程才能调用 SetForegroundWindow，
    后台进程直接调只会让任务栏图标闪一下，窗口仍压在其他窗口下面 —— 这正是
    「点了打开面板但什么都没发生」的原因。绕法是把本线程的输入队列临时挂到
    前台线程上（AttachThreadInput），此时就获得了合法的前台权限。

    托底再走一次 TOPMOST→NOTOPMOST 的 z 序闪现：即使焦点抢不到，窗口在视觉上
    也已经到最前了，用户至少能看到它。
    """
    if _u.IsIconic(h):
        _u.ShowWindow(h, SW_RESTORE)
    else:
        _u.ShowWindow(h, SW_SHOW)
    _ensure_on_screen(h)

    if _u.GetForegroundWindow() == h:
        return True

    fg = _u.GetForegroundWindow()
    cur_tid = _k.GetCurrentThreadId()
    fg_tid = _u.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = False
    if fg_tid and fg_tid != cur_tid:
        attached = bool(_u.AttachThreadInput(cur_tid, fg_tid, True))
    try:
        _u.BringWindowToTop(h)
        _u.SetForegroundWindow(h)
    finally:
        if attached:
            _u.AttachThreadInput(cur_tid, fg_tid, False)

    if _u.GetForegroundWindow() == h:
        return True

    _u.SetWindowPos(h, HWND_TOPMOST, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS)
    _u.SetWindowPos(h, HWND_NOTOPMOST, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS)
    return False


class PanelApi:
    """暴露给页面的 JS 接口：window.pywebview.api.*

    注意：pywebview 会把 js_api 对象的**所有公开属性**递归遍历
    （webview/util.py :: get_functions）。所以不要把 Window 实例挂成公开属性，
    否则它会顺着 `win.native` 摸进 WinForms/COM 对象图，逐层 getattr 触发
    跨套间 COM 读取，刷出满屏 `[pywebview] Error while processing win.native...`。
    窗口句柄用 `_hwnd`（私有，不参与遍历），并且自己用 ctypes 找。
    """

    def __init__(self, title: str = "Battery Pulse"):
        self._title = title
        self._hwnd = None
        self._pinned = False
        self._on_quit = None
        self._centered = False

    # ---- HWND ----
    def _w(self):
        """取面板窗口句柄。ctypes 调用会释放 GIL，从任何线程来都安全。"""
        h = self._hwnd
        if h and _u.IsWindow(h) and _class_of(h) != TRAY_CLASS:
            return h
        self._hwnd = _find_panel_hwnd(self._title)
        return self._hwnd

    # ---- 页面调用（跑在 pywebview 的工作线程上）----
    def set_on_top(self, flag) -> bool:
        self._pinned = bool(flag)
        h = self._w()
        if h:
            _u.SetWindowPos(
                h, HWND_TOPMOST if self._pinned else HWND_NOTOPMOST,
                0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS,
            )
        return True

    def hide_panel(self) -> bool:
        h = self._w()
        if h:
            _u.ShowWindow(h, SW_HIDE)
        return True

    def quit_app(self) -> bool:
        if self._on_quit:
            self._on_quit()
        return True

    def window_state(self) -> dict:
        return {"pinned": self._pinned}

    # ---- Python 侧调用（托盘线程）----
    def show_panel(self) -> bool:
        h = self._w()
        if not h:
            return False
        # 以 --hidden 启动时窗口从没显示过，启动阶段的居中循环没机会出手，
        # 第一次打开时补上（之后就不再动，尊重用户自己拖的位置）。
        if not self._centered:
            _center_window(h)
            self._centered = True
        force_foreground(h)
        # 置顶状态要重新贴一次：上面的 z 序闪现将临时清掉 TopMost
        if self._pinned:
            _u.SetWindowPos(
                h, HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS,
            )
        return True

    def destroy(self) -> None:
        h = self._w()
        if h:
            _u.PostMessageW(h, WM_CLOSE, 0, 0)


def run(start_backend, url: str, *, hidden: bool = False, width: int = 940, height: int = 828,
        storage_dir: str | None = None):
    """创建窗口并进入 GUI 主循环。start_backend(api) 在后台线程执行，负责起服务与托盘。"""
    import webview

    title = "Battery Pulse"
    api = PanelApi(title)
    width, height = fit_size(width, height)
    x, y = center_on_screen(width, height)
    webview.create_window(
        title,
        url,
        width=width,
        height=height,
        x=x,
        y=y,
        min_size=(720, 560),
        frameless=True,
        easy_drag=False,
        background_color=BG,
        js_api=api,
        hidden=hidden,
    )

    def boot() -> None:
        # 窗口刚建出来时句柄可能还查不到，轮询几次再摆正位置
        def center_when_ready() -> None:
            import time as _t

            for _ in range(120):
                h = _find_panel_hwnd(title)
                # 必须等窗口真的可见：pywebview 显示窗口时会自己摆一次位置，
                # 早于它居中会被覆盖掉（表现为窗口总停在左上角的级联位置）。
                if h and _u.IsWindowVisible(h):
                    _t.sleep(0.4)
                    _center_window(h)
                    api._centered = True
                    return
                _t.sleep(0.2)

        threading.Thread(target=center_when_ready, daemon=True).start()
        start_backend(api)

    webview.start(
        boot,
        gui="edgechromium",
        private_mode=False,
        storage_path=storage_dir,
        debug=False,
    )
