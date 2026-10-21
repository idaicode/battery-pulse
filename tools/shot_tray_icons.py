"""展开任务栏溢出区并截取托盘图标（做完自动收起，尽量不打扰鼠标）。"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab  # noqa: E402

u = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
u.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
u.FindWindowW.restype = wintypes.HWND
u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u.EnumChildWindows.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.LPARAM]
u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def find_chevron():
    """任务栏上那个 ^ 按钮：TrayNotifyWnd 的第一个 Button 子窗口。"""
    bar = u.FindWindowW("Shell_TrayWnd", None)
    found = []

    def cb(h, _):
        cls = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(h, cls, 64)
        if cls.value == "Button":
            r = wintypes.RECT()
            u.GetWindowRect(h, ctypes.byref(r))
            if r.right - r.left > 4 and r.bottom - r.top > 4:
                found.append((h, r))
        return True

    u.EnumChildWindows(bar, ctypes.cast(PROC(cb), ctypes.c_void_p), 0)
    return found[-1] if found else (None, None)


def click(x: int, y: int) -> None:
    u.SetCursorPos(x, y)
    time.sleep(0.15)
    u.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
    time.sleep(0.05)
    u.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP


def main() -> int:
    hwnd, r = find_chevron()
    if not hwnd:
        print("没找到展开按钮")
        return 1
    cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2

    from core.tray import NOTIFYICONIDENTIFIER

    u.FindWindowW.restype = wintypes.HWND
    tray = u.FindWindowW("BatteryPulseTrayWnd", None)
    if not tray:
        print("托盘窗口不在")
        return 1

    # 已经展开的话先不动
    overflow = u.FindWindowW("NotifyIconOverflowWindow", None)
    if not overflow or not u.IsWindowVisible(overflow):
        click(cx, cy)
        time.sleep(0.9)

    shell32.Shell_NotifyIconGetRect.argtypes = [
        ctypes.POINTER(NOTIFYICONIDENTIFIER), ctypes.POINTER(wintypes.RECT),
    ]
    shell32.Shell_NotifyIconGetRect.restype = ctypes.c_long

    rects = []
    for uid in (1, 2):
        nii = NOTIFYICONIDENTIFIER()
        nii.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
        nii.hWnd = tray
        nii.uID = uid
        rr = wintypes.RECT()
        if shell32.Shell_NotifyIconGetRect(ctypes.byref(nii), ctypes.byref(rr)) == 0:
            rects.append(rr)
            print(f"icon {uid}: ({rr.left},{rr.top}) {rr.right - rr.left}x{rr.bottom - rr.top}")

    if rects:
        pad = 10
        box = (
            min(r.left for r in rects) - pad,
            min(r.top for r in rects) - pad,
            max(r.right for r in rects) + pad,
            max(r.bottom for r in rects) + pad,
        )
        im = ImageGrab.grab(bbox=box)
        im.save(ROOT / "shots" / "tray_icons.png")
        im.resize((im.width * 5, im.height * 5)).save(ROOT / "shots" / "tray_icons_zoom.png")
        print("saved tray_icons.png", im.size)

    click(cx, cy)  # 收起溢出区
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
