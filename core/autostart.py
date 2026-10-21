"""开机自启：写 HKCU\\...\\Run，用 pythonw 拉起，不闪控制台窗口。

之所以不用「启动」文件夹快捷方式：cmd 会先闪一下黑框；写注册表则是纯静默。
"""
from __future__ import annotations

import sys
import winreg
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "BatteryPulse"


def _pythonw() -> Path:
    """优先 pythonw.exe：同等环境但无控制台窗口。"""
    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        cand = exe.with_name("pythonw.exe")
        if cand.exists():
            return cand
    return exe


def command() -> str:
    """打包后直接指向 exe；源码运行时用 pythonw 拉起 app.py。

    自启一律用 --tray：不创建 WebView2 窗口，常驻内存最小，
    需要面板时从托盘菜单打开。
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    return f'"{_pythonw()}" "{ROOT / "app.py"}" --tray'


def enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable() -> bool:
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
        return True
    except OSError:
        return False


def disable() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def toggle() -> bool:
    """切换并返回切换后的状态。"""
    if enabled():
        disable()
        return False
    enable()
    return True
