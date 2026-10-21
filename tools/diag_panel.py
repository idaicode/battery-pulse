"""诊断主面板窗口状态：是否存在、是否可见、位置尺寸、所属进程。"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

u = ctypes.WinDLL("user32", use_last_error=True)
k = ctypes.WinDLL("kernel32", use_last_error=True)
u.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
u.FindWindowW.restype = wintypes.HWND
u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
u.IsWindowVisible.argtypes = [wintypes.HWND]
u.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

GWL_STYLE = -16
GWL_EXSTYLE = -20
PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

rows = []


def cb(hwnd, _):
    buf = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(hwnd, buf, 256)
    title = buf.value
    if "Battery" not in title and "pywebview" not in title.lower():
        return True
    cls = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(hwnd, cls, 256)
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    r = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    rows.append({
        "hwnd": hwnd,
        "title": title,
        "class": cls.value,
        "pid": pid.value,
        "visible": bool(u.IsWindowVisible(hwnd)),
        "rect": (r.left, r.top, r.right - r.left, r.bottom - r.top),
        "style": hex(u.GetWindowLongW(hwnd, GWL_STYLE) & 0xFFFFFFFF),
        "exstyle": hex(u.GetWindowLongW(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF),
    })
    return True


u.EnumWindows(ctypes.cast(PROC(cb), ctypes.c_void_p), 0)

print(f"匹配窗口数: {len(rows)}")
for x in rows:
    print(
        f"  hwnd={x['hwnd']} pid={x['pid']} visible={x['visible']} "
        f"rect={x['rect']}\n    title={x['title']!r} class={x['class']} "
        f"style={x['style']} ex={x['exstyle']}"
    )

h = u.FindWindowW(None, "Battery Pulse")
print("FindWindowW(None,'Battery Pulse') =", h)
if not rows and h == 0:
    print(">> 没有任何面板窗口存在（说明窗口没建出来，或被销毁）")
