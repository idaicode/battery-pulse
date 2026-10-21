"""最小验证：frameless WebView2 窗口能否创建、能否截图。"""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from pathlib import Path

os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--disable-gpu --no-sandbox --disable-software-rasterizer --disable-features=RendererCodeIntegrity"

import webview

ROOT = Path(__file__).resolve().parent.parent
TITLE = "BatteryPulseTest"


def capture() -> None:
    time.sleep(4.0)
    u = ctypes.WinDLL("user32", use_last_error=True)
    g = ctypes.WinDLL("gdi32", use_last_error=True)
    u.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    try:
        u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass
    u.FindWindowW.restype = wintypes.HWND
    u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    u.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]

    class BIH(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
        ]

    class BI(ctypes.Structure):
        _fields_ = [("bmiHeader", BIH), ("colors", wintypes.DWORD * 3)]

    h = u.FindWindowW(None, TITLE)
    print("hwnd:", h)
    if not h:
        print("窗口没找到")
        webview.windows[0].destroy()
        return
    r = wintypes.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    w, hh = r.right - r.left, r.bottom - r.top
    print("size:", w, hh)

    # 提到前台，否则抓到的是被遮住的桌面
    u.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    u.SetWindowPos(h, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)  # TOPMOST|NOSIZE|NOSIZE
    u.SetForegroundWindow(h)
    time.sleep(1.5)

    hdc = u.GetDC(None)
    mdc = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, w, hh)
    g.SelectObject(mdc, bmp)
    ok = u.PrintWindow(h, mdc, 2)
    bi = BI()
    bi.bmiHeader.biSize = ctypes.sizeof(BIH)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -hh
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(w * hh * 4)
    g.GetDIBits(mdc, bmp, 0, hh, buf, ctypes.byref(bi), 0)
    from PIL import Image

    im = Image.frombuffer("RGBA", (w, hh), buf, "raw", "BGRA", 0, 1).convert("RGB")
    out = ROOT / "shots" / "wv_test.png"
    im.save(out)
    print("PrintWindow:", ok, "saved:", out)

    from PIL import ImageGrab

    shot = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom))
    shot.save(ROOT / "shots" / "wv_grab.png")
    print("grab saved, size:", shot.size)
    webview.windows[0].destroy()


def main() -> None:
    win = webview.create_window(
        TITLE,
        url=(ROOT / "ui" / "index.html").as_uri(),
        width=900,
        height=620,
        frameless=True,
        easy_drag=False,
        background_color="#F5F2EA",
    )
    print("window created:", win)
    webview.start(capture, gui="edgechromium")


if __name__ == "__main__":
    main()
