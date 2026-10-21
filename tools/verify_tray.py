"""托盘自检：确认图标真的注册进通知区域，并打印它的屏幕坐标。

图标不显示时先跑这个：
    .venv\\Scripts\\python.exe tools\\verify_tray.py
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import tray as T  # noqa: E402


class FakeManager:
    """喂两份假数据，不碰真实硬件。"""

    def __init__(self):
        self.cfg = {
            "warn_threshold": 20,
            "critical_threshold": 10,
            "notify": True,
            "sound": True,
            "low_power": False,
        }

    @property
    def devices(self):
        now = time.time()
        return [
            {
                "id": "hid:test:1",
                "name": "G304 Lightspeed Wireless Gaming Mouse",
                "vendor": "logitech",
                "percent": 90,
                "online": True,
                "status": "放电中",
                "updated": now,
            },
            {
                "id": "ble:TEST",
                "name": "RK98RGB 5.0",
                "vendor": "ble",
                "percent": 12,
                "online": True,
                "status": "放电中",
                "updated": now,
            },
        ]

    def refresh(self):
        pass

    def update_config(self, patch):
        self.cfg.update(patch)
        return self.cfg


def rect_of(hwnd, uid):
    nid = T.NOTIFYICONIDENTIFIER()
    nid.cbSize = ctypes.sizeof(nid)
    nid.hWnd = hwnd
    nid.uID = uid
    r = wintypes.RECT()
    hr = T.shell32.Shell_NotifyIconGetRect(ctypes.byref(nid), ctypes.byref(r))
    return hr, r


def main() -> int:
    t = T.Tray(FakeManager(), lambda: "http://127.0.0.1:8731/")
    ok = t.start()
    print("托盘线程就绪:", ok)
    print("窗口句柄:", t._hwnd)
    print("图标槽位:", {k: v["added"] for k, v in t._slots.items()})
    time.sleep(0.6)
    for uid in range(1, t._slot_count + 1):
        hr, r = rect_of(t._hwnd, uid)
        print(f"图标 {uid}: hr=0x{hr & 0xFFFFFFFF:08X} rect=({r.left},{r.top},{r.right},{r.bottom})")
    print("提示（图标在溢出区时 rect 可能为空，hr!=0 也不代表失败）")
    input("按回车移除图标并退出...")
    t.quit()
    time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
