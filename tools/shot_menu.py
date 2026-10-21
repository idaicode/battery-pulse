"""抓真实弹出的托盘菜单（DPI 感知版）。

要点：不设 Per-Monitor-V2 的话，GetWindowRect 返回的是被系统缩放后的虚拟坐标，
grab 出来的区域会小一圈、错位一格，截出来就是糊的。
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parent.parent

WM_TRAY_CALLBACK = 0x8000 + 1
WM_RBUTTONUP = 0x0205
WM_KEYDOWN = 0x0100
VK_ESCAPE = 0x1B

u = ctypes.WinDLL("user32", use_last_error=True)
u.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u.FindWindowW.restype = wintypes.HWND
u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "shots" / "tray_menu.png"
    tray = u.FindWindowW("BatteryPulseTrayWnd", None)
    if not tray:
        print("找不到托盘窗口")
        return 1

    menu = 0
    for _ in range(8):
        u.PostMessageW(tray, WM_TRAY_CALLBACK, 1, WM_RBUTTONUP)
        time.sleep(1.0)
        menu = u.FindWindowW("BatteryPulseMenu", None)
        if menu:
            break
    if not menu:
        print("菜单没弹出")
        return 1

    r = wintypes.RECT()
    u.GetWindowRect(menu, ctypes.byref(r))
    print(f"menu {menu}  {r.right - r.left}x{r.bottom - r.top} @ {r.left},{r.top}")
    im = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    print("saved", out, im.size)

    u.PostMessageW(menu, WM_KEYDOWN, VK_ESCAPE, 0)
    for _ in range(20):
        time.sleep(0.2)
        if not u.FindWindowW("BatteryPulseMenu", None):
            print("菜单已关闭")
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
