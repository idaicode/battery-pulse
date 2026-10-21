"""设备状态管理：轮询调度、低电量预警、内存指标。"""
from __future__ import annotations

import ctypes
import gc
import threading
import time
from ctypes import wintypes

from . import ble, config, notify

# ---------- 进程内存 ----------


class _PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi", use_last_error=True)

# 必须显式声明 argtypes：否则 64 位 HANDLE 会按 C int 传参被截断
_kernel32.GetCurrentProcess.restype = wintypes.HANDLE
_psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
_psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
_psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
_psapi.EmptyWorkingSet.restype = wintypes.BOOL
_kernel32.SetProcessWorkingSetSize.argtypes = [wintypes.HANDLE, ctypes.c_size_t, ctypes.c_size_t]
_kernel32.SetProcessWorkingSetSize.restype = wintypes.BOOL


def working_set_bytes() -> int:
    pmc = _PMC()
    pmc.cb = ctypes.sizeof(pmc)
    handle = _kernel32.GetCurrentProcess()
    if _psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
        return int(pmc.WorkingSetSize)
    return 0


def trim_working_set() -> int:
    """把空闲页还给系统，任务管理器里的占用会立刻下降。"""
    handle = _kernel32.GetCurrentProcess()
    try:
        _psapi.EmptyWorkingSet(handle)
    except Exception:
        pass
    try:
        _kernel32.SetProcessWorkingSetSize(handle, ctypes.c_size_t(-1), ctypes.c_size_t(-1))
    except Exception:
        pass
    gc.collect()
    return working_set_bytes()


# ---------- 状态 ----------

WARN_COOLDOWN = 30 * 60  # 同一设备同一档位 30 分钟内只提醒一次
WARN_DEBOUNCE = 60  # 任意两次提醒之间至少间隔 1 分钟，防止连发
WARN_RESET_MARGIN = 5  # 电量回升超过阈值 5% 才重置提醒状态
BLE_OFFLINE_BACKOFF = 45  # 读不到的 BLE 设备，45 秒内不再重试
AUTO_TRIM_IDLE = 180  # 界面 3 分钟没动过，才考虑自动回收
AUTO_TRIM_RSS = 32 * 1048576  # 只有超过 32MB 才回收，避免无意义的抖动
AUTO_TRIM_INTERVAL = 300  # 最多 5 分钟一次


def _fmt_ts(ts: float | None) -> str | None:
    if not ts:
        return None
    return time.strftime("%H:%M:%S", time.localtime(ts))


class Manager:
    def __init__(self):
        self.cfg = config.load()
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self._devices: list[dict] = []
        self._last_refresh = 0.0
        self._last_activity = time.time()
        self._started = time.time()
        self._events: list[dict] = []
        self._warn_state: dict[str, dict] = {}
        self._ble_skip_until: dict[str, float] = {}
        self._peak_rss = 0
        self._last_trim = 0.0
        self._scanning = False
        self._stop = threading.Event()
        self._listeners: list = []

    def add_listener(self, fn) -> None:
        """采集完成后回调（托盘用它通知重画图标）。回调里只做投递消息之类的小事。"""
        self._listeners.append(fn)

    # ---------- 对外 ----------
    @property
    def devices(self) -> list[dict]:
        with self._lock:
            return [dict(d) for d in self._devices]

    def touch(self):
        self._last_activity = time.time()

    def interval(self) -> int:
        idle = time.time() - self._last_activity > 120
        if self.cfg.get("low_power"):
            return int(self.cfg["poll_low_power"])
        return int(self.cfg["poll_idle"] if idle else self.cfg["poll_active"])

    def update_config(self, patch: dict) -> dict:
        with self._lock:
            for key in ("warn_threshold", "critical_threshold", "notify", "sound", "low_power"):
                if key in patch:
                    self.cfg[key] = patch[key]
            self.cfg["warn_threshold"] = max(5, min(90, int(self.cfg["warn_threshold"])))
            self.cfg["critical_threshold"] = max(1, min(int(self.cfg["warn_threshold"]) - 1, int(self.cfg["critical_threshold"])))
            config.save(self.cfg)
        return self.cfg

    def snapshot(self) -> dict:
        rss = working_set_bytes()
        self._peak_rss = max(self._peak_rss, rss)
        with self._lock:
            devices = [dict(d) for d in self._devices]
            events = list(self._events[-8:])
        return {
            "devices": devices,
            "config": {
                "warn_threshold": self.cfg["warn_threshold"],
                "critical_threshold": self.cfg["critical_threshold"],
                "notify": self.cfg["notify"],
                "sound": self.cfg["sound"],
                "low_power": self.cfg["low_power"],
            },
            "meta": {
                "interval": self.interval(),
                "rss_mb": round(rss / 1048576, 1),
                "peak_rss_mb": round(self._peak_rss / 1048576, 1),
                "last_refresh": _fmt_ts(self._last_refresh),
                "uptime": int(time.time() - self._started),
                "events": events,
                "scanning": self._scanning,
            },
        }

    # ---------- 采集 ----------
    def refresh(self) -> None:
        if not self._refresh_lock.acquire(blocking=False):
            return
        try:
            devices: list[dict] = []
            devices.extend(self._read_hid())
            devices.extend(self._read_ble())
            with self._lock:
                self._devices = devices
                self._last_refresh = time.time()
            self._check_warnings(devices)
            for fn in self._listeners:
                try:
                    fn()
                except Exception:
                    pass
        except Exception as exc:  # 采集失败不应影响服务
            self._push_event("error", f"采集异常：{exc}")
        finally:
            self._refresh_lock.release()

    def _read_hid(self) -> list[dict]:
        try:
            from . import hidpp
        except Exception:
            return []
        out = []
        try:
            for item in hidpp.scan():
                bat = item.get("battery") or {}
                pct = bat.get("percent")
                out.append(
                    {
                        "id": f"hid:{item['interface']}:{item['dev_index']}",
                        "name": item.get("name") or "Logitech 设备",
                        "vendor": "logitech",
                        "transport": "2.4G 接收器",
                        "percent": pct,
                        "charging": bool(bat.get("charging")),
                        "status": bat.get("status") or ("放电中" if pct is not None else "未知"),
                        "online": pct is not None,
                        "note": f"HID++ {item.get('protocol', '')}".strip(),
                        "updated": time.time(),
                    }
                )
        except Exception:
            pass
        return out

    def _read_ble(self) -> list[dict]:
        out = []
        targets = list(self.cfg.get("ble_devices") or [])
        ignored = set(self.cfg.get("ignored_macs") or [])
        for t in targets:
            mac = (t.get("mac") or "").upper()
            if not mac or mac in ignored:
                continue
            now = time.time()
            if self._ble_skip_until.get(mac, 0) > now:
                out.append(self._offline_ble(mac, t.get("name", ""), "等待重试"))
                continue
            r = ble.read_one(mac, timeout=3.5)
            if not r:
                self._ble_skip_until[mac] = now + BLE_OFFLINE_BACKOFF
                out.append(self._offline_ble(mac, t.get("name", ""), "读取失败"))
                continue
            pct = r.get("percent")
            if pct is None:
                self._ble_skip_until[mac] = now + BLE_OFFLINE_BACKOFF
                hint = "未连接" if not r.get("online") else "无电池服务"
                out.append(self._offline_ble(mac, t.get("name") or r.get("name", ""), hint))
                continue
            self._ble_skip_until.pop(mac, None)
            out.append(
                {
                    "id": f"ble:{mac}",
                    "name": t.get("name") or r.get("name") or "BLE 设备",
                    "vendor": "ble",
                    "transport": "蓝牙 LE",
                    "percent": int(pct),
                    "charging": False,
                    "status": "放电中",
                    "online": True,
                    "note": "GATT 0x180F",
                    "updated": time.time(),
                }
            )
        return out

    def _offline_ble(self, mac: str, name: str, hint: str) -> dict:
        return {
            "id": f"ble:{mac}",
            "name": name or "BLE 设备",
            "vendor": "ble",
            "transport": "蓝牙 LE",
            "percent": None,
            "charging": False,
            "status": hint,
            "online": False,
            "note": "2.4G 模式下读不到电量",
            "updated": time.time(),
        }

    # ---------- 预警 ----------
    def _check_warnings(self, devices: list[dict]) -> None:
        warn_th = int(self.cfg["warn_threshold"])
        crit_th = int(self.cfg["critical_threshold"])
        now = time.time()
        for d in devices:
            pct = d.get("percent")
            if pct is None or d.get("charging"):
                continue
            did = d["id"]
            st = self._warn_state.setdefault(did, {"level": 0, "ts": 0.0})

            # 电量回升到阈值以上，重置，等下一次跌破再提醒
            if pct > warn_th + WARN_RESET_MARGIN:
                st["level"] = 0
                st["ts"] = 0.0
                continue

            level = 2 if pct <= crit_th else (1 if pct <= warn_th else 0)
            if level == 0:
                continue
            if now - st["ts"] < WARN_DEBOUNCE:  # 防抖：短时间内不连发
                continue
            if level < st["level"]:  # 降级（比如从临界回到偏低）不重复打扰
                st["level"] = level
                continue
            if level == st["level"] and now - st["ts"] < WARN_COOLDOWN:
                continue

            st["level"] = level
            st["ts"] = now
            self._fire_warning(d, level)

    def _fire_warning(self, d: dict, level: int) -> None:
        pct = d["percent"]
        if level >= 2:
            title = f"{d['name']} 电量严重不足"
            msg = f"仅剩 {pct}%，请立刻更换电池或充电"
        else:
            title = f"{d['name']} 电量偏低"
            msg = f"剩余 {pct}%，建议尽快更换电池或充电"
        self._push_event("critical" if level >= 2 else "warn", f"{d['name']} {pct}%")
        if self.cfg.get("notify"):
            ok = notify.toast(title, msg, sound=self.cfg.get("sound", True))
            if not ok and self.cfg.get("sound", True):
                notify.beep()

    def _push_event(self, kind: str, text: str) -> None:
        with self._lock:
            self._events.append({"kind": kind, "text": text, "ts": _fmt_ts(time.time())})
            if len(self._events) > 60:
                self._events = self._events[-40:]

    # ---------- 设备发现 ----------
    def scan_ble(self, timeout: float = 5.0) -> list[dict]:
        self._scanning = True
        try:
            found = ble.probe(timeout=timeout)
        finally:
            self._scanning = False
        if not found:
            return []
        known = {t.get("mac", "").upper() for t in self.cfg.get("ble_devices") or []}
        changed = False
        for item in found:
            mac = item["mac"].upper()
            if mac in known:
                continue
            self.cfg.setdefault("ble_devices", []).append({"mac": mac, "name": item.get("name") or mac})
            known.add(mac)
            changed = True
        if changed:
            config.save(self.cfg)
            self._ble_skip_until.clear()
        self.refresh()
        return found

    def trim(self, silent: bool = False) -> dict:
        before = working_set_bytes()
        after = trim_working_set()
        self._last_trim = time.time()
        if not silent:
            self._push_event("info", f"释放内存 {round((before - after) / 1048576, 1)} MB")
        return {"before_mb": round(before / 1048576, 1), "after_mb": round(after / 1048576, 1)}

    def test_notify(self) -> None:
        notify.toast("电量预警测试", "通知通道正常，低电量时会这样提醒你", sound=True)

    # ---------- 主循环 ----------
    def poll_loop(self) -> None:
        # 首次启动：自动发现一次 BLE 设备
        if not self.cfg.get("ble_devices"):
            try:
                threading.Thread(target=self.scan_ble, daemon=True).start()
            except Exception:
                pass
        while not self._stop.is_set():
            if time.time() - self._last_refresh >= self.interval():
                self.refresh()
            if self.cfg.get("low_power"):
                gc.collect()
            idle_for = time.time() - self._last_activity
            if (
                idle_for > AUTO_TRIM_IDLE
                and time.time() - self._last_trim > AUTO_TRIM_INTERVAL
                and working_set_bytes() > AUTO_TRIM_RSS
            ):
                self.trim(silent=True)
            time.sleep(1.0)

    def start(self) -> None:
        self.refresh()
        threading.Thread(target=self.poll_loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
