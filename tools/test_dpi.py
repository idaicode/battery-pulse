"""DPI 语义实测：设置 per-monitor-v2 后，pywebview 的 width/height 是逻辑还是物理像素。"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

MODES = {"none": None, "system": 1, "pmv2": -4}


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "none"
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    if MODES.get(mode):
        ok = u.SetProcessDpiAwarenessContext(ctypes.c_void_p(MODES[mode]))
        print("set dpi ctx:", ok, "->", mode)

    import webview

    u.GetDpiForSystem.restype = wintypes.UINT
    try:
        dpi_sys = u.GetDpiForSystem()
    except Exception:
        dpi_sys = 0
    print("GetDpiForSystem:", dpi_sys, "scale:", dpi_sys / 96)

    def job() -> None:
        time.sleep(1.5)
        u.FindWindowW.restype = wintypes.HWND
        u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        h = u.FindWindowW(None, "DPITest")
        print("hwnd:", h)
        if h:
            r = wintypes.RECT()
            u.GetWindowRect(h, ctypes.byref(r))
            print("window rect:", r.right - r.left, "x", r.bottom - r.top, "(requested 900x620)")
        for w in list(webview.windows):
            try:
                w.destroy()
            except Exception:
                pass

    webview.create_window("DPITest", html="<h1>x</h1>", width=900, height=620)
    webview.start(job, gui="edgechromium", private_mode=False,
                  storage_path=str(Path(__file__).resolve().parent.parent / "data" / "webview2"))


if __name__ == "__main__":
    main()
