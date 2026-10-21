"""模拟托盘右键，验证自绘菜单真实弹出，截图后 ESC 关闭。"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WM_TRAY_CALLBACK = 0x8000 + 1
WM_RBUTTONUP = 0x0205
WM_KEYDOWN = 0x0100
VK_ESCAPE = 0x1B


def main() -> None:
    uid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    try:
        u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass
    u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u.FindWindowW.restype = wintypes.HWND
    u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]

    tray = u.FindWindowW("BatteryPulseTrayWnd", None)
    print("tray hwnd:", tray)
    if not tray:
        return

    pt = wintypes.POINT()
    u.GetCursorPos(ctypes.byref(pt))
    print("cursor:", pt.x, pt.y)

    u.PostMessageW(tray, WM_TRAY_CALLBACK, uid, WM_RBUTTONUP)
    time.sleep(1.6)

    menu = u.FindWindowW("BatteryPulseMenu", None)
    print("menu hwnd:", menu)
    if menu:
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        r = wintypes.RECT()
        u.GetWindowRect(menu, ctypes.byref(r))
        print("menu rect:", r.left, r.top, r.right, r.bottom,
              "size:", r.right - r.left, r.bottom - r.top)
        from PIL import ImageGrab

        im = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom))
        im.save(ROOT / "shots" / "tray_menu.png")
        print("saved", im.size)
        u.PostMessageW(menu, WM_KEYDOWN, VK_ESCAPE, 0)
        time.sleep(0.6)
        print("menu closed:", u.FindWindowW("BatteryPulseMenu", None) == 0)
    else:
        print("菜单没弹出")


if __name__ == "__main__":
    main()
