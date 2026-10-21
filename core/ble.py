"""BLE 电池读取层（WinRT / GATT 0x180F）。

winrt 采用延迟导入：没有 BLE 设备或用户没开蓝牙时不会占用内存。
"""
from __future__ import annotations

import asyncio
import re
import uuid

from . import winps

BATTERY_SVC = uuid.UUID("0000180f-0000-1000-8000-00805f9b34fb")
BATTERY_CHAR = "00002a19-0000-1000-8000-00805f9b34fb"

_discover_cache: dict = {"ts": 0.0, "items": []}
DISCOVER_TTL = 60.0


def discover(force: bool = False, ttl: float = DISCOVER_TTL) -> list[dict]:
    """列出当前系统里存在的 BLE 设备（配对过且在场）。结果缓存 ttl 秒。"""
    import time

    if not force and time.time() - _discover_cache["ts"] < ttl:
        return _discover_cache["items"]

    script = r"""
$result = @()
Get-PnpDevice -PresentOnly |
  Where-Object { $_.InstanceId -like 'BTHLE\DEV_*' } |
  ForEach-Object {
    $m = [regex]::Match($_.InstanceId, 'BTHLE\\DEV_([0-9A-Fa-f]{12})')
    if ($m.Success) {
      $nm = $_.FriendlyName
      if ([string]::IsNullOrWhiteSpace($nm)) { $nm = '' }
      $nm = $nm -replace '^\s*Bluetooth\s+', ''
      $result += [pscustomobject]@{ mac = $m.Groups[1].Value.ToUpper(); name = $nm }
    }
  }
$result | Sort-Object mac -Unique | ConvertTo-Json -Compress
"""
    data = winps.run_ps_json(script, timeout=15)
    if isinstance(data, dict):
        data = [data]
    items = []
    for row in data or []:
        mac = (row.get("mac") or "").strip().upper()
        if not re.fullmatch(r"[0-9A-F]{12}", mac):
            continue
        items.append({"mac": mac, "name": (row.get("name") or "").strip()})

    _discover_cache["ts"] = time.time()
    _discover_cache["items"] = items
    return items


def _addr_int(mac: str) -> int:
    return int(mac.replace(":", "").replace("-", ""), 16)


async def _read_async(mac: str, timeout: float) -> dict | None:
    from winrt.windows.devices.bluetooth import BluetoothConnectionStatus, BluetoothLEDevice
    from winrt.windows.storage.streams import DataReader

    try:
        dev = await asyncio.wait_for(
            BluetoothLEDevice.from_bluetooth_address_async(_addr_int(mac)), timeout
        )
    except Exception:
        return None
    if dev is None:
        return None

    try:
        name = dev.name or ""
        connected = dev.connection_status == BluetoothConnectionStatus.CONNECTED
        if not connected:
            return {"online": False, "percent": None, "name": name, "mac": mac}
        try:
            res = await asyncio.wait_for(dev.get_gatt_services_for_uuid_async(BATTERY_SVC), timeout)
        except Exception:
            return {"online": True, "percent": None, "name": name, "mac": mac}
        if res is None or not res.services:
            return {"online": True, "percent": None, "name": name, "mac": mac}

        for svc in res.services:
            try:
                cres = await asyncio.wait_for(svc.get_characteristics_async(), timeout)
            except Exception:
                continue
            for ch in (cres.characteristics or []) if cres else []:
                if str(ch.uuid).lower() != BATTERY_CHAR:
                    continue
                try:
                    rr = await asyncio.wait_for(ch.read_value_async(), timeout)
                except Exception:
                    continue
                if rr is None or rr.value is None:
                    continue
                try:
                    dr = DataReader.from_buffer(rr.value)
                    pct = dr.read_byte()
                except Exception:
                    continue
                if 0 <= pct <= 100:
                    return {"online": True, "percent": pct, "name": name, "mac": mac}
                return {"online": True, "percent": None, "name": name, "mac": mac}
        return {"online": True, "percent": None, "name": name, "mac": mac}
    finally:
        try:
            dev.close()
        except Exception:
            pass


def read_one(mac: str, timeout: float = 6.0) -> dict | None:
    """读取单个 BLE 设备的电量。返回 {'online','percent','name','mac'}。"""
    try:
        return asyncio.run(_read_async(mac, timeout))
    except Exception:
        return None


def probe(timeout: float = 6.0) -> list[dict]:
    """扫描并逐个尝试读取，返回真正暴露了电池服务的设备。"""
    out = []
    for item in discover(force=True):
        r = read_one(item["mac"], timeout=timeout)
        if not r:
            continue
        if not r.get("name"):
            r["name"] = item["name"]
        if r.get("percent") is not None:
            out.append(r)
    return out
