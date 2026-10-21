"""抓取指定标题的窗口（置顶后按屏幕坐标截取）。"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    title = sys.argv[1] if len(sys.argv) > 1 else "Battery Pulse"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else (ROOT / "shots" / "window.png")

    u = ctypes.WinDLL("user32", use_last_error=True)
    u.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    try:
        u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass
    u.FindWindowW.restype = wintypes.HWND
    u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    u.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]

    # FindWindowW 在 DPI/线程上下文变化后可能匹配不到，改用枚举
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found = []

    def cb(hwnd, _):
        n = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, n, 256)
        if u.IsWindowVisible(hwnd) and n.value.strip() == title:
            found.append(hwnd)
        return True

    u.EnumWindows(EnumProc(cb), 0)
    h = found[0] if found else 0
    print("hwnd:", h, "candidates:", len(found))
    if not h:
        return
    u.SetWindowPos(h, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
    u.SetForegroundWindow(h)
    time.sleep(1.0)

    r = wintypes.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    from PIL import ImageGrab

    im = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom))
    im.save(out)
    print("saved", out, im.size)


if __name__ == "__main__":
    main()
