"""极简 PowerShell 桥：避免引号地狱，统一用 -EncodedCommand。"""
from __future__ import annotations

import base64
import json
import subprocess

CREATE_NO_WINDOW = 0x08000000


def run_ps(script: str, timeout: int = 20) -> str:
    """同步执行 PowerShell，返回 stdout。"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )
    return proc.stdout.decode("utf-8", "ignore").strip()


def spawn_ps(script: str) -> None:
    """后台执行，不等待（用于通知这类一次性动作）。"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.Popen(
        ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )


def run_ps_json(script: str, timeout: int = 20):
    out = run_ps(script, timeout=timeout)
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None
