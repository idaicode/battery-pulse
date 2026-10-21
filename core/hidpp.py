"""Logitech HID++ 2.0 读取层。

适配「同一物理接口下短报文(0x10)/长报文(0x11)被 Windows 拆成两个 collection」的接收器，
同时兼容只在短 collection 应答的老设备。
"""
from __future__ import annotations

import re
import time

import hid

VID_LOGITECH = 0x046D
USAGE_PAGE_HIDPP = 0xFF00

REPORT_SHORT = 0x10
REPORT_LONG = 0x11
SW_ID = 0x0F  # 软件 ID，2.0 里由主机自选，0x0F 常用

# --- Feature ID ---
FEAT_ROOT = 0x0000
FEAT_DEVICE_FW = 0x0003
FEAT_DEVICE_NAME = 0x0005
FEAT_BATTERY_STATUS = 0x1000  # BATTERY_LEVEL_STATUS：直接给百分比
FEAT_BATTERY_VOLTAGE = 0x1001  # BATTERY_VOLTAGE：给 mV

# 0x1000 的放电状态码
BATTERY_STATUS_TEXT = {
    0: "放电中",
    1: "充电中",
    2: "接近充满",
    3: "已充满",
    4: "异常",
    5: "慢充中",
}


def enumerate_hidpp_collections(vid=VID_LOGITECH):
    """返回 [(device_dict, collection_kind)]，kind 为 'short'/'long'。"""
    found = []
    for d in hid.enumerate(vid):
        if d["usage_page"] != USAGE_PAGE_HIDPP:
            continue
        # usage 1 = 短报文控制集合，usage 2 = 长报文集合，其余（如 usage 4）不是 HID++ 通道
        if d["usage"] == 0x0001:
            kind = "short"
        elif d["usage"] == 0x0002:
            kind = "long"
        else:
            continue
        found.append((d, kind))
    return found


def group_interfaces(vid=VID_LOGITECH):
    """把同一 MI 下的 short/long collection 配对。

    返回 [{'name': 'MI_02', 'short': path|None, 'long': path|None}]
    """
    groups: dict[str, dict] = {}
    for d, kind in enumerate_hidpp_collections(vid):
        path = d["path"].decode() if isinstance(d["path"], bytes) else d["path"]
        # 取 \\?\HID#VID_xxx&PID_yyy&MI_zz 作为分组键（去掉 &ColNN，同一接口的短/长集合要配对）
        key = path.split("#")[1] if "#" in path else path
        key = re.sub(r"&Col\d+", "", key)
        groups.setdefault(key, {"name": key, "short": None, "long": None})
        groups[key][kind] = path
    return list(groups.values())


class HIDPPDevice:
    def __init__(self, short_path: str | None, long_path: str | None):
        self.handles = []
        self.short_dev = None
        self.long_dev = None
        for path, attr in ((short_path, "short_dev"), (long_path, "long_dev")):
            if not path:
                continue
            try:
                dev = hid.device()
                # hidapi 的 open_path 在 Windows 下需要 bytes
                dev.open_path(path.encode("mbcs") if isinstance(path, str) else path)
                setattr(self, attr, dev)
                self.handles.append(dev)
            except Exception:
                setattr(self, attr, None)

    # ---------- 底层收发 ----------
    def _write_long(self, buf):
        if not self.long_dev:
            return False
        try:
            return self.long_dev.write(buf) > 0
        except Exception:
            return False

    def _write_short(self, buf):
        if not self.short_dev:
            return False
        try:
            return self.short_dev.write(buf) > 0
        except Exception:
            return False

    def _drain(self):
        """清掉迟到的旧响应，避免错位。"""
        for dev in self.handles:
            while True:
                try:
                    if not dev.read(64, 1):
                        break
                except Exception:
                    break

    def request(self, dev_idx: int, feat_idx: int, func: int, params=(), timeout=0.45, long=True):
        """发一条 HID++ 2.0 请求并等待匹配的响应，返回 r[4:] 或 None。"""
        self._drain()
        if long:
            buf = [REPORT_LONG, dev_idx, feat_idx, (func << 4) | SW_ID] + (list(params) + [0] * 16)[:16]
            ok = self._write_long(buf)
            if not ok:
                buf = [REPORT_SHORT, dev_idx, feat_idx, (func << 4) | SW_ID] + (list(params) + [0] * 3)[:3]
                ok = self._write_short(buf)
        else:
            buf = [REPORT_SHORT, dev_idx, feat_idx, (func << 4) | SW_ID] + (list(params) + [0] * 3)[:3]
            ok = self._write_short(buf)
        if not ok:
            return None

        deadline = time.time() + timeout
        while time.time() < deadline:
            slice_ms = 60
            for dev in self.handles:
                try:
                    r = dev.read(64, slice_ms)
                except Exception:
                    continue
                if not r or len(r) < 4:
                    continue
                if r[1] != dev_idx:
                    continue
                if (r[3] & 0x0F) != SW_ID or (r[3] >> 4) != func:
                    continue
                if r[2] == 0xFF:  # 错误报文
                    return None
                return r[4:]
            if time.time() > deadline:
                break
        return None

    def get_feature(self, dev_idx: int, feature_id: int) -> int:
        """返回 feature index，0 表示不支持。"""
        r = self.request(dev_idx, FEAT_ROOT, 0, [feature_id >> 8, feature_id & 0xFF])
        return r[0] if r else 0

    def protocol_version(self, dev_idx: int = 0xFF):
        r = self.request(dev_idx, FEAT_ROOT, 1)
        if not r:
            return None
        return r[0], r[1]

    def device_name(self, dev_idx: int) -> str:
        fi = self.get_feature(dev_idx, FEAT_DEVICE_NAME)
        if not fi:
            return ""
        r = self.request(dev_idx, fi, 0)
        if not r:
            return ""
        length = r[0]
        out = b""
        for off in range(0, max(length, 1), 16):
            chunk = self.request(dev_idx, fi, 1, [off])
            if not chunk:
                break
            out += bytes(chunk[:16])
        return out.decode("utf-8", "ignore").strip("\x00").strip()

    def battery(self, dev_idx: int) -> dict | None:
        """优先用 0x1000 拿百分比，退化为 0x1001 用电压换算。"""
        fi = self.get_feature(dev_idx, FEAT_BATTERY_STATUS)
        if fi:
            r = self.request(dev_idx, fi, 0)
            if r:
                pct = r[0]
                status_code = r[1] if len(r) > 1 else None
                external = r[2] if len(r) > 2 else None
                if 0 <= pct <= 100:
                    # 部分固件在 p1 塞的是私有值（G304 返回 0x32），此时用外部供电位判断
                    if status_code in BATTERY_STATUS_TEXT:
                        status = BATTERY_STATUS_TEXT[status_code]
                        charging = status_code in (1, 2, 3)
                        external_power = bool(external) if external is not None else None
                    else:
                        charging = bool(external)
                        status = "充电中" if charging else "放电中"
                        external_power = bool(external) if external is not None else None
                    return {
                        "percent": pct,
                        "status": status,
                        "charging": charging,
                        "external_power": external_power,
                        "source": "0x1000",
                    }
        fi = self.get_feature(dev_idx, FEAT_BATTERY_VOLTAGE)
        if fi:
            r = self.request(dev_idx, fi, 0)
            if r and len(r) >= 2:
                mv = (r[0] << 8) | r[1]
                flags = r[2] if len(r) > 2 else 0
                pct = r[3] if len(r) > 3 and 0 < r[3] <= 100 else voltage_to_percent(mv)
                return {
                    "percent": pct,
                    "status": "充电中" if flags & 0x01 else "放电中",
                    "charging": bool(flags & 0x01),
                    "voltage_mv": mv,
                    "source": "0x1001",
                }
        return None

    def close(self):
        for dev in self.handles:
            try:
                dev.close()
            except Exception:
                pass
        self.handles = []


def voltage_to_percent(mv: int) -> int:
    """AA/AAA 干电池电压→电量百分比的近似曲线（Logitech 游戏外设常用）。"""
    if mv <= 0:
        return 0
    # 1.5V 碱性：约 1600mV 满，1100mV 空；镍氢略低
    lo, hi = 1100, 1600
    if mv >= hi:
        return 100
    if mv <= lo:
        return 5
    return max(5, min(100, round((mv - lo) / (hi - lo) * 95) + 5))


def scan(vid=VID_LOGITECH, verbose=False):
    """扫描所有 Logitech 接收器，返回 [{'dev_index', 'name', 'battery', 'interface'}]"""
    results = []
    for grp in group_interfaces(vid):
        if not grp["short"] and not grp["long"]:
            continue
        dev = HIDPPDevice(grp["short"], grp["long"])
        if not dev.handles:
            continue
        try:
            for idx in range(1, 7):
                pv = dev.protocol_version(idx)
                if not pv:
                    continue
                name = dev.device_name(idx)
                bat = dev.battery(idx)
                results.append(
                    {
                        "dev_index": idx,
                        "name": name,
                        "protocol": f"{pv[0]}.{pv[1]}",
                        "battery": bat,
                        "interface": grp["name"],
                    }
                )
                if verbose:
                    print(f"  idx={idx} name={name!r} proto={pv} battery={bat}")
        finally:
            dev.close()
    return results


if __name__ == "__main__":
    print("接口分组:")
    for g in group_interfaces():
        print("  ", g["name"], "short=", bool(g["short"]), "long=", bool(g["long"]))
    print("\n扫描结果:")
    for r in scan(verbose=True):
        print(r)
