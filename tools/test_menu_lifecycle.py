"""托盘菜单生命周期回归：开、ESC 关、点非交互区不关、连点右键不嵌套。

这几条都是自绘弹层容易出错的地方 —— 菜单是模态的（自己跑 GetMessageW 循环），
而托盘窗口的消息又会在这个循环里被派发回来，一不小心就嵌套出孤儿窗口。
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.test_menu_click import PAD, ROW_H, H_HEADER, SHADOW, W_CARD, row_center  # noqa: E402

WM_TRAY_CALLBACK = 0x8000 + 1
WM_RBUTTONUP = 0x0205
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_KEYDOWN = 0x0100
VK_ESCAPE = 0x1B

u = ctypes.WinDLL("user32", use_last_error=True)
u.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u.FindWindowW.restype = wintypes.HWND
u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]


def menus() -> list[int]:
    """枚举所有菜单窗口（不只是第一个，才能发现孤儿）。"""
    found = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(128)
        u.GetClassNameW(hwnd, buf, 128)
        if buf.value == "BatteryPulseMenu":
            found.append(hwnd)
        return True

    u.EnumWindows(ctypes.cast(proc(cb), ctypes.c_void_p), 0)
    return found


def right_click(uid: int = 1) -> None:
    tray = u.FindWindowW("BatteryPulseTrayWnd", None)
    u.PostMessageW(tray, WM_TRAY_CALLBACK, uid, WM_RBUTTONUP)


def click(hwnd: int, key: str) -> None:
    r = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    scale = (r.right - r.left) / (W_CARD + 2 + SHADOW * 2)
    lx, ly = row_center(key)
    lp = (int((ly + SHADOW) * scale) << 16) | int((lx + SHADOW) * scale)
    u.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, lp)
    u.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)


def main() -> int:
    fails = []

    def check(name, cond):
        print(f"{'✅' if cond else '❌'} {name}")
        if not cond:
            fails.append(name)

    # 1. 右键弹出
    right_click()
    time.sleep(1.0)
    ms = menus()
    check(f"右键弹出且只有一个窗口 (实际 {len(ms)})", len(ms) == 1)
    if not ms:
        return 1
    menu = ms[0]

    # 2. 点中间的数值区（非交互行）不应关闭
    click(menu, "th_value")
    time.sleep(0.8)
    check("点数值区后菜单仍在（不误关）", len(menus()) == 1)

    # 3. ESC 关闭
    u.PostMessageW(menu, WM_KEYDOWN, VK_ESCAPE, 0)
    time.sleep(0.8)
    check("ESC 能关闭菜单", len(menus()) == 0)

    # 4. 连发两次右键：不能嵌套出两个窗口
    right_click()
    time.sleep(0.9)
    right_click()
    time.sleep(0.9)
    n = len(menus())
    check(f"连点右键不产生嵌套 (实际 {n})", n <= 1)

    # 5. 点一下开关，应当生效并自动关闭
    ms = menus()
    if ms:
        click(ms[0], "sound")
        time.sleep(1.0)
    check("点击开关后菜单自动关闭", len(menus()) == 0)

    print("\n结果：", "全部通过" if not fails else f"{len(fails)} 项失败 -> {fails}")
    return 0 if not fails else 2


if __name__ == "__main__":
    raise SystemExit(main())
