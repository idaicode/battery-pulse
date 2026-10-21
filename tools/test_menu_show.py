"""实测弹层：创建 → 截图 → 模拟点击 → 校验返回值。"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab  # noqa: E402

from core import menu as M  # noqa: E402

STATE = {
    "device": {"name": "G304", "percent": 90, "level": 0, "status_line": "正常 · 2.4G 接收器 · 刚刚同步"},
    "warn_threshold": 20,
    "notify": True,
    "sound": True,
    "low_power": False,
    "autostart": True,
}


def main() -> None:
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    try:
        u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception as e:
        print("dpi:", e)

    scale = 1.5
    m = M.PopupMenu(STATE, scale=scale)
    target_key = sys.argv[1] if len(sys.argv) > 1 else M.R_REFRESH

    def work() -> None:
        # 先悬停在目标行上，方便截图看清 hover 态
        time.sleep(1.2)
        hwnd = m._hwnd
        row = next((r for r in m.rows if r.key == target_key), None)
        if not hwnd or not row:
            print("no hwnd/row")
            return
        x0, y0, x1, y1 = row.rect
        cx = int((x0 + x1) / 2 * scale)
        cy = int((y0 + y1) / 2 * scale)
        lp = (cy << 16) | cx

        u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u.PostMessageW(hwnd, M.WM_MOUSEMOVE, 0, lp)
        time.sleep(0.9)

        # 截图（按窗口实际位置）
        r = wintypes.RECT()
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.GetWindowRect(hwnd, ctypes.byref(r))
        shot = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom))
        shot.save(ROOT / "shots" / "menu_live.png")
        print("shot", shot.size, "at", r.left, r.top)

        time.sleep(0.4)
        u.PostMessageW(hwnd, M.WM_LBUTTONDOWN, 1, lp)

    threading.Thread(target=work, daemon=True).start()
    res = m.show(1750, 950)
    print("RESULT:", res)


if __name__ == "__main__":
    main()
