"""任务栏托盘：每只设备一个图标。

设计取向是「几乎不占资源」：
- 消息循环用 GetMessageW 阻塞，没有任何 while+sleep 轮询，空闲时 CPU 为 0；
- 只在采集完成 / 鼠标事件时投递一条消息，图标要真的变了才重建 HICON；
- 全程只有本进程一个窗口，不额外起进程。
"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

from . import autostart

# ---------------- Win32 常量 ----------------
WM_APP = 0x8000
WM_TRAY_CALLBACK = WM_APP + 1
WM_TRAY_UPDATE = WM_APP + 2
WM_TRAY_EXIT = WM_APP + 3

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_NULL = 0x0000
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2

NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04
NIF_INFO = 0x10
NIF_SHOWTIP = 0x80

MF_STRING = 0x0000
MF_POPUP = 0x0010
MF_SEPARATOR = 0x0800
MF_CHECKED = 0x0008
MF_DISABLED = 0x0002
MF_GRAYED = 0x0001

TPM_LEFTALIGN = 0x0000
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100

SM_CXSMICON = 49

# 菜单命令 id
ID_OPEN = 100
ID_REFRESH = 101
ID_THRESHOLD_BASE = 110  # 110.. 对应 THRESHOLDS
ID_NOTIFY = 130
ID_SOUND = 131
ID_LOWPOWER = 132
ID_AUTOSTART = 140
ID_QUIT = 199

THRESHOLDS = (10, 15, 20, 25, 30, 40, 50)

# 0 正常 / 1 偏低 / 2 危急 / 3 离线
COLORS = {
    0: (78, 107, 87, 255),    # 墨绿，和界面同色系
    1: (192, 134, 54, 255),   # 琥珀
    2: (180, 69, 58, 255),    # 砖红
    3: (140, 138, 128, 255),  # 中性灰
}
LABELS = {0: "正常", 1: "偏低", 2: "危急", 3: "离线"}


# ---------------- Win32 结构 ----------------
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("guidItem", GUID),
    ]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

kernel32.GetModuleHandleW.restype = wintypes.HMODULE
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.CreateIconIndirect.restype = wintypes.HICON
user32.LoadImageW.restype = wintypes.HANDLE
user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, ctypes.c_void_p,
]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
shell32.Shell_NotifyIconGetRect.argtypes = [
    ctypes.POINTER(NOTIFYICONIDENTIFIER), ctypes.POINTER(wintypes.RECT),
]
shell32.Shell_NotifyIconGetRect.restype = ctypes.c_long
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.UINT, ctypes.c_void_p]
gdi32.CreateBitmap.restype = wintypes.HBITMAP
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]

# 下面这些 argtypes 不能省：64 位句柄按默认 int 传递会被截断/溢出
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p,
]
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
user32.RegisterWindowMessageW.restype = wintypes.UINT
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = ctypes.c_ssize_t
user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
user32.PostQuitMessage.argtypes = [ctypes.c_int]


# ---------------- 图标绘制 ----------------
def _icon_size() -> int:
    """取系统小图标尺寸（16/20/24/32），跟随 DPI。"""
    size = user32.GetSystemMetrics(SM_CXSMICON) or 16
    return max(16, min(64, int(size)))


_FONTS: dict[int, object] = {}


def _font(px: int):
    from PIL import ImageFont

    if px not in _FONTS:
        _FONTS[px] = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", px)
    return _FONTS[px]


# 图标配色：和面板同一套（米白卡 + 墨色字），进度条用状态色
C_CARD = (240, 238, 230, 255)    # #F0EEE6 卡片底
C_EDGE = (203, 197, 182, 255)    # 极淡描边，浅色任务栏上也分得清边界
C_INK = (47, 46, 41, 255)        # #2F2E29 数字
C_TRACK = (216, 211, 198, 255)   # 进度条空槽


def _render(size: int, pct, level: int):
    """托盘图标：米白圆角卡片 + 墨色电量数字 + 底部进度条。

    数字给精确值，底部横条给「还剩多少」的一眼可见量。浅色卡片在深色任务栏
    上很醒目；浅色任务栏上靠淡淡描边和深色数字拉开层次，两种主题都读得清。
    """
    from PIL import Image, ImageDraw

    ss = 8  # 超采样倍率，缩小后边缘才干净
    n = size * ss
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    m = n * 0.025                      # 卡片几乎铺满图标，只留一线给圆角
    x0 = y0 = m
    x1 = y1 = n - m
    card_w, card_h = x1 - x0, y1 - y0
    d.rounded_rectangle(
        (x0, y0, x1, y1),
        radius=card_w * 0.24,
        fill=C_CARD,
        outline=C_EDGE,
        width=max(1, round(n * 0.012)),
    )

    # 底部进度条占的纵向空间
    bar_h = card_h * 0.135
    bar_pad_b = card_h * 0.085
    bar_pad_x = card_w * 0.155
    bar_top = y1 - bar_pad_b - bar_h
    bar_bottom = y1 - bar_pad_b
    bar_x0 = x0 + bar_pad_x
    bar_x1 = x1 - bar_pad_x

    # 数字：在「卡片顶 → 进度条上沿」之间居中
    text_top = y0
    text_bottom = bar_top - card_h * 0.03
    text_h = text_bottom - text_top
    text_max_w = card_w * 0.80

    text = "–" if pct is None else str(max(0, min(100, int(round(pct)))))
    px = int(text_h * 1.35)
    while px > 6 * ss:
        f = _font(px)
        box = d.textbbox((0, 0), text, font=f)
        if (box[2] - box[0]) <= text_max_w and (box[3] - box[1]) <= text_h:
            break
        px -= ss
    f = _font(px)
    box = d.textbbox((0, 0), text, font=f)
    tw, th = box[2] - box[0], box[3] - box[1]
    d.text(
        ((x0 + x1) / 2 - tw / 2 - box[0], (text_top + text_bottom) / 2 - th / 2 - box[1]),
        text, font=f, fill=C_INK,
    )

    # 进度条：空槽 + 按电量比例填充（离线只留空槽）
    radius = bar_h / 2
    d.rounded_rectangle((bar_x0, bar_top, bar_x1, bar_bottom), radius=radius, fill=C_TRACK)
    if pct is not None:
        fill_w = (bar_x1 - bar_x0) * max(0, min(100, pct)) / 100.0
        if fill_w > 0:
            fill_w = max(fill_w, bar_h)  # 再低也要留一个圆点，别缩成看不见的细线
            d.rounded_rectangle(
                (bar_x0, bar_top, bar_x0 + fill_w, bar_bottom),
                radius=radius, fill=COLORS[level],
            )

    return im.resize((size, size), Image.LANCZOS)


def _hicon(img) -> int:
    """PIL RGBA → HICON（CreateIconIndirect + 32bpp DIB）。"""
    w, h = img.size
    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h  # 负数 = 自上而下
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0  # BI_RGB

    bits = ctypes.c_void_p()
    hdc = gdi32.CreateCompatibleDC(None)
    try:
        hbm_color = gdi32.CreateDIBSection(hdc, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0)
        raw = img.convert("RGBA").tobytes("raw", "BGRA")
        ctypes.memmove(bits, raw, len(raw))
        hbm_mask = gdi32.CreateBitmap(w, h, 1, 1, None)
        info = ICONINFO()
        info.fIcon = 1
        info.hbmMask = hbm_mask
        info.hbmColor = hbm_color
        hicon = user32.CreateIconIndirect(ctypes.byref(info))
        gdi32.DeleteObject(hbm_color)
        gdi32.DeleteObject(hbm_mask)
        return hicon
    finally:
        gdi32.DeleteDC(hdc)


# ---------------- 托盘 ----------------
class Tray:
    def __init__(self, manager, url_getter, on_exit=None, on_open=None):
        self.manager = manager
        self.url_getter = url_getter
        self.on_exit = on_exit
        self.on_open = on_open

        self._hwnd = None
        self._thread = None
        self._ready = threading.Event()
        self._wndproc_ref = None
        self._ipc = 0

        self._slots: dict[int, dict] = {}  # uid -> {sig, hicon, added}
        self._slot_count = 0
        self._img_cache: dict[tuple, object] = {}
        self._hinted = False
        self._retry = 0

    # ---- 对外 ----
    @property
    def icon_count(self) -> int:
        return sum(1 for s in self._slots.values() if s.get("added"))

    def start(self) -> bool:
        self._thread = threading.Thread(target=self._run, name="tray", daemon=True)
        self._thread.start()
        return self._ready.wait(4.0)

    def post_update(self) -> None:
        """任意线程调用：让托盘线程去同步图标。"""
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_TRAY_UPDATE, 0, 0)

    def quit(self) -> None:
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_TRAY_EXIT, 0, 0)

    def balloon(self, title: str, text: str) -> None:
        """弹一条托盘气泡（图标被折叠时 Windows 也会在右下角显示）。"""
        if not self._hwnd:
            return
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_INFO
        nid.dwInfoFlags = 0x1  # NIIF_INFO
        nid.szInfoTitle = title[:63]
        nid.szInfo = text[:255]
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    # ---- 线程主体 ----
    def _run(self) -> None:
        try:
            user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
        except Exception:
            pass

        hinst = kernel32.GetModuleHandleW(None)
        self._wndproc_ref = WNDPROC(self._wndproc)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0
        wc.lpfnWndProc = ctypes.cast(self._wndproc_ref, ctypes.c_void_p)
        wc.hInstance = hinst
        wc.lpszClassName = "BatteryPulseTrayWnd"
        user32.RegisterClassExW(ctypes.byref(wc))

        self._hwnd = user32.CreateWindowExW(
            0, "BatteryPulseTrayWnd", "Battery Pulse", 0, 0, 0, 0, 0, None, None, hinst, None
        )
        self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self._ipc = user32.RegisterWindowMessageW("BatteryPulseIPC")

        self._sync(force=True)
        self._ready.set()

        msg = wintypes.MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:  # 0 = WM_QUIT
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        self._remove_all()
        if self.on_exit:
            try:
                self.on_exit()
            except Exception:
                pass

    # ---- 消息处理 ----
    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAY_CALLBACK:
                event = lparam & 0xFFFF
                uid = int(wparam)
                if event == WM_LBUTTONUP:
                    self._on_left(uid)
                elif event == WM_LBUTTONDBLCLK:
                    self._on_double(uid)
                elif event == WM_RBUTTONUP:
                    self._on_right(uid)
                return 0
            if msg == WM_TRAY_UPDATE:
                self._sync()
                return 0
            if msg == WM_TRAY_EXIT:
                self._quit()
                return 0
            if msg == self._taskbar_created:  # 资源管理器重启，图标要重新挂
                for slot in self._slots.values():
                    slot["added"] = False
                self._sync(force=True)
                return 0
            if msg == WM_DESTROY:
                # 自己投 WM_QUIT：不依赖 DefWindowProc 的默认行为，退出路径才确定
                user32.PostQuitMessage(0)
                return 0
            if msg == WM_CLOSE:
                self._quit()
                return 0
        except Exception:
            pass
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _quit(self) -> None:
        self._remove_all()
        if self._hwnd:
            user32.DestroyWindow(self._hwnd)
            user32.PostQuitMessage(0)

    # ---- 图标同步 ----
    def _cfg(self) -> dict:
        return {
            "warn_threshold": int(self.manager.cfg["warn_threshold"]),
            "critical_threshold": int(self.manager.cfg["critical_threshold"]),
            "notify": bool(self.manager.cfg.get("notify")),
            "sound": bool(self.manager.cfg.get("sound")),
            "low_power": bool(self.manager.cfg.get("low_power")),
        }

    @staticmethod
    def _level(dev: dict | None, cfg: dict) -> int:
        if not dev or not dev.get("online") or dev.get("percent") is None:
            return 3
        pct = int(dev["percent"])
        if pct <= cfg["critical_threshold"]:
            return 2
        if pct <= cfg["warn_threshold"]:
            return 1
        return 0

    def _ordered(self) -> list[dict]:
        devs = self.manager.devices
        # 罗技（HID++）排前面，其余按 id 稳定排序
        return sorted(devs, key=lambda d: (0 if d.get("vendor") == "logitech" else 1, d.get("id", "")))

    def _sync(self, force: bool = False) -> None:
        cfg = self._cfg()
        devs = self._ordered()
        count = max(self._slot_count, min(4, len(devs)))
        if count == 0:
            return
        self._slot_count = count
        size = _icon_size()
        failed = False

        for i in range(count):
            uid = i + 1
            dev = devs[i] if i < len(devs) else None
            level = self._level(dev, cfg)
            pct = None if level == 3 else int(dev["percent"])
            name = (dev or {}).get("name") or "未连接"
            if pct is None:
                tip = f"{name} · 离线"
            else:
                tip = f"{name} · {pct}% · {LABELS[level]}"

            sig = (pct, level, size, tip)
            slot = self._slots.setdefault(uid, {"sig": None, "hicon": None, "added": False})
            if not force and slot["sig"] == sig and slot["added"]:
                continue

            if slot["hicon"] and slot["sig"] != sig:
                user32.DestroyIcon(slot["hicon"])
                slot["hicon"] = None
            if not slot["hicon"]:
                key = (pct, level, size)
                img = self._img_cache.get(key)
                if img is None:
                    img = _render(size, pct, level)
                    if len(self._img_cache) > 48:
                        self._img_cache.clear()
                    self._img_cache[key] = img
                slot["hicon"] = _hicon(img)

            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = self._hwnd
            nid.uID = uid
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage = WM_TRAY_CALLBACK
            nid.hIcon = slot["hicon"]
            nid.szTip = tip[:127]
            action = NIM_MODIFY if slot["added"] else NIM_ADD
            ok = shell32.Shell_NotifyIconW(action, ctypes.byref(nid))
            if ok:
                slot["added"] = True
                slot["sig"] = sig
            else:
                # 注册失败就别记账。explorer 重启后托盘服务要几秒才就绪，
                # 这一下失败很常见；旧代码无论如何都置 added=True，于是
                # 后面的 _sync 全被 sig 相同的判断跳过，图标永久丢失。
                slot["added"] = False
                slot["sig"] = None
                failed = True

        if failed and self._retry < 30:
            self._retry += 1
            threading.Timer(1.5, self.post_update).start()
        elif not failed:
            self._retry = 0

        if not self._hinted:
            self._hinted = True
            self._hint_if_hidden()

    def _hint_if_hidden(self) -> None:
        """Windows 10 会把新图标塞进 ^ 溢出区，且没有 API 能直接提升 —— 提示用户拖一次。"""
        hidden = 0
        for uid, slot in self._slots.items():
            if not slot.get("added"):
                continue
            nii = NOTIFYICONIDENTIFIER()
            nii.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
            nii.hWnd = self._hwnd
            nii.uID = uid
            rect = wintypes.RECT()
            if shell32.Shell_NotifyIconGetRect(ctypes.byref(nii), ctypes.byref(rect)) == 1:  # S_FALSE = 在溢出区
                hidden += 1
        if not hidden:
            return
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_INFO
        nid.dwInfoFlags = 0x1  # NIIF_INFO
        nid.szInfoTitle = "电量图标被折叠了"
        nid.szInfo = "把托盘里的电量图标从 ^ 拖到任务栏上，Windows 会记住这个位置"
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _remove_all(self) -> None:
        for uid, slot in list(self._slots.items()):
            if slot.get("added"):
                nid = NOTIFYICONDATAW()
                nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
                nid.hWnd = self._hwnd
                nid.uID = uid
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            if slot.get("hicon"):
                user32.DestroyIcon(slot["hicon"])
                slot["hicon"] = None
            slot["added"] = False
        self._img_cache.clear()

    # ---- 交互 ----
    def _device_of(self, uid: int) -> dict | None:
        devs = self._ordered()
        idx = uid - 1
        return devs[idx] if 0 <= idx < len(devs) else None

    def _on_left(self, uid: int) -> None:
        """左键 = 立刻刷新一次（放线程里，别卡住消息循环）。"""
        threading.Thread(target=self._refresh_now, daemon=True).start()

    def _on_double(self, uid: int) -> None:
        self._open_panel()

    def _open_panel(self) -> None:
        try:
            if self.on_open:
                self.on_open()
            else:
                import webbrowser

                webbrowser.open(self.url_getter())
        except Exception:
            pass

    def _refresh_now(self) -> None:
        try:
            self.manager.refresh()
        except Exception:
            pass
        self.post_update()

    def _dpi_scale(self) -> float:
        """取主显示器的实际缩放。

        不用 GetDpiForSystem：它受进程 DPI 感知模式影响，在 WebView2 先进场的
        情况下会返回 96，导致菜单按 1.0 渲染、而系统按 1.5 显示，点击坐标全错。
        GetDpiForMonitor 直接问显示器，不受进程模式影响。
        """
        try:
            shcore = ctypes.WinDLL("shcore", use_last_error=True)
            user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
            user32.MonitorFromPoint.restype = wintypes.HMONITOR
            mon = user32.MonitorFromPoint(wintypes.POINT(0, 0), 2)  # MONITOR_DEFAULTTOPRIMARY
            dx, dy = ctypes.c_uint(), ctypes.c_uint()
            shcore.GetDpiForMonitor(mon, 0, ctypes.byref(dx), ctypes.byref(dy))
            if dx.value:
                return max(1.0, dx.value / 96.0)
        except Exception:
            pass
        try:
            user32.GetDpiForSystem.restype = wintypes.UINT
            return max(1.0, user32.GetDpiForSystem() / 96.0)
        except Exception:
            return 1.0

    @staticmethod
    def _ago(ts) -> str:
        import time as _t

        if not ts:
            return "等待同步"
        d = max(0, int(_t.time() - ts))
        if d < 10:
            return "刚刚同步"
        if d < 60:
            return f"{d} 秒前"
        if d < 3600:
            return f"{d // 60} 分钟前"
        return f"{d // 3600} 小时前"

    def _menu_state(self, uid: int) -> dict:
        cfg = self._cfg()
        dev = self._device_of(uid)
        d = None
        if dev:
            level = self._level(dev, cfg)
            parts = [LABELS[level]]
            if dev.get("transport"):
                parts.append(str(dev["transport"]))
            if dev.get("online"):
                parts.append(self._ago(dev.get("updated")))
            else:
                parts.append(dev.get("note") or "离线")
            d = {
                "name": dev.get("name") or "未知设备",
                "percent": None if level == 3 else int(dev["percent"]),
                "level": level,
                "status_line": " · ".join(p for p in parts if p),
            }
        return {
            "device": d,
            "warn_threshold": int(cfg["warn_threshold"]),
            "notify": bool(cfg["notify"]),
            "sound": bool(cfg["sound"]),
            "low_power": bool(cfg["low_power"]),
            "autostart": autostart.enabled(),
        }

    def _on_right(self, uid: int) -> None:
        """右键 = 自绘的 Claude 风格弹层（原生菜单无法定制配色）。"""
        from .menu import (
            R_AUTOSTART,
            R_LOWPOWER,
            R_NOTIFY,
            R_OPEN,
            R_QUIT,
            R_REFRESH,
            R_SOUND,
            R_TH_DOWN,
            R_TH_UP,
            THRESHOLDS,
            PopupMenu,
        )

        # 防重入。菜单是模态的：show() 内部自己跑 GetMessageW 循环，而托盘窗口的
        # 消息仍会在这个循环里被取出并派发回本函数。若此时再建一个 PopupMenu，
        # 旧菜单就失去了 _active 引用 —— 窗口没人管、ESC 和点击全部失效，
        # 于是桌面上留一块永远关不掉的孤儿面板。这里遇到已开着的菜单就收起来。
        if PopupMenu._active is not None:
            PopupMenu._active.close()
            return

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        scale = self._dpi_scale()

        while True:
            menu = PopupMenu(self._menu_state(uid), scale=scale)
            action = menu.show(pt.x, pt.y)
            if not action:
                return
            key = action[0]

            if key == R_OPEN:
                self._open_panel()
                return
            if key == R_REFRESH:
                threading.Thread(target=self._refresh_now, daemon=True).start()
                return
            if key == R_QUIT:
                self._quit()
                return
            if key in (R_TH_DOWN, R_TH_UP):
                cur = int(self._cfg()["warn_threshold"])
                idx = min(range(len(THRESHOLDS)), key=lambda i: abs(THRESHOLDS[i] - cur))
                idx += 1 if key == R_TH_UP else -1
                idx = max(0, min(len(THRESHOLDS) - 1, idx))
                self.manager.update_config({"warn_threshold": THRESHOLDS[idx]})
            elif key in (R_NOTIFY, R_SOUND, R_LOWPOWER):
                self.manager.update_config({key: not self._cfg()[key]})
            elif key == R_AUTOSTART:
                autostart.toggle()
            else:
                return
            self.post_update()
