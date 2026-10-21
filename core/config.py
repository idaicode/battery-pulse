"""配置持久化（便携式：存在程序目录 data/config.json）。"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path


def _app_dir() -> Path:
    """打包后配置写在 exe 旁边（便携），源码运行时写在项目根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


ROOT = _app_dir()
DATA_DIR = ROOT / "data"
CONFIG_PATH = DATA_DIR / "config.json"

DEFAULTS = {
    "port": 8731,
    "warn_threshold": 20,
    "critical_threshold": 10,
    "poll_active": 5,
    "poll_idle": 60,
    "poll_low_power": 120,
    "notify": True,
    "sound": True,
    "low_power": False,
    "ble_devices": [],  # [{"mac": "CB03BF7A1535", "name": "RK98RGB 5.0"}]
    "ignored_macs": [],
}

_lock = threading.RLock()


def load() -> dict:
    with _lock:
        cfg = dict(DEFAULTS)
        try:
            if CONFIG_PATH.exists():
                cfg.update(json.loads(CONFIG_PATH.read_text("utf-8")))
        except Exception:
            pass
        return cfg


def save(cfg: dict) -> None:
    with _lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        merged = dict(DEFAULTS)
        merged.update(cfg)
        tmp = CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(CONFIG_PATH)
