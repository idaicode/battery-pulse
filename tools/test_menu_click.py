"""验证自绘菜单的点击是否真的命中（DPI 缩放修复后的回归测试）。

做法：给托盘窗口投右键消息 → 找到菜单窗口 → 按 `menu.py` 的逻辑布局算出
「低功耗模式」那一行的客户端坐标 → 投 WM_LBUTTONDOWN → 回读配置确认翻转。
"""
from __future__ import annotations

import ctypes
import json
import sys
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WM_TRAY_CALLBACK = 0x8000 + 1
WM_RBUTTONUP = 0x0205
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202

# 与 core/menu.py 保持一致
PAD, ROW_H, H_HEADER, SHADOW, W_CARD = 12, 32, 58, 22, 296


def row_center(key: str) -> tuple[float, float]:
    """按 menu._layout 的顺序重算某行可点区域的中心（逻辑坐标）。"""
    y = PAD + H_HEADER + 1 + 8
    full = (PAD, W_CARD - PAD)            # 通栏行的 x 范围
    y_open = y; y += ROW_H
    y_refresh = y; y += ROW_H
    y += 8
    y += 22                               # section 标题
    gx, grp_w = (W_CARD - 116) // 2, 116  # 阈值 [-][+] 组的布局
    y_step = y; y += ROW_H + 8
    rows = {
        "open": (full, y_open),
        "refresh": (full, y_refresh),
        "th_down": ((gx, gx + 32), y_step),
        "th_up": ((gx + grp_w - 32, gx + grp_w), y_step),
        "th_value": ((gx + 32, gx + grp_w - 32), y_step),
    }
    for k in ("notify", "sound", "low_power", "autostart"):
        rows[k] = (full, y); y += ROW_H
    if key not in rows:
        raise KeyError(key)
    (x0, x1), top = rows[key]
    return (x0 + x1) / 2, top + ROW_H / 2


# 行 key → 配置字段
CFG_KEY = {"th_up": "warn_threshold", "th_down": "warn_threshold"}


def api(path: str):
    with urllib.request.urlopen(f"http://127.0.0.1:8731{path}", timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    uid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    target = sys.argv[2] if len(sys.argv) > 2 else "low_power"

    u = ctypes.WinDLL("user32", use_last_error=True)
    u.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u.FindWindowW.restype = wintypes.HWND
    u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

    tray = u.FindWindowW("BatteryPulseTrayWnd", None)
    if not tray:
        print("找不到托盘窗口")
        return 1

    before = api("/api/state")["config"]
    cfg_key = CFG_KEY.get(target, target)
    print(f"{target} before: {before.get(cfg_key)}")

    u.PostMessageW(tray, WM_TRAY_CALLBACK, uid, WM_RBUTTONUP)
    time.sleep(1.2)

    menu = u.FindWindowW("BatteryPulseMenu", None)
    if not menu:
        print("菜单没弹出")
        return 1
    r = wintypes.RECT()
    u.GetWindowRect(menu, ctypes.byref(r))
    w_px, h_px = r.right - r.left, r.bottom - r.top
    scale = w_px / (W_CARD + 2 + SHADOW * 2)
    print(f"menu {w_px}x{h_px}  scale={scale:.3f}")

    lx, ly = row_center(target)
    px, py = int((lx + SHADOW) * scale), int((ly + SHADOW) * scale)
    print(f"click client=({px},{py})  logical=({lx},{ly})")

    lp = (py << 16) | px
    u.PostMessageW(menu, WM_LBUTTONDOWN, 1, lp)
    u.PostMessageW(menu, WM_LBUTTONUP, 0, lp)
    time.sleep(1.4)

    after = api("/api/state")["config"]
    print(f"{target} after:  {after.get(cfg_key)}")
    ok = after.get(cfg_key) != before.get(cfg_key)
    print("RESULT:", "TOGGLED ✅" if ok else "未生效 ❌")

    log = ROOT / "data" / "menu.log"
    print("=== menu.log ===")
    print(log.read_text(encoding="utf-8").strip() if log.exists() else "(空)")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
