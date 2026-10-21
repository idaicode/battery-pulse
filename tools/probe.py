"""诊断探针：枚举 Logitech HID++ 设备，打印支持的 Feature 与电量读取结果。"""
import hid
import time

VID_LOGITECH = 0x046D
HIDPP_SHORT = 0x10
SW_ID = 0x0F


def find_control_interface():
    for d in hid.enumerate(VID_LOGITECH):
        if d["usage_page"] == 0xFF00 and d["usage"] == 0x0001:
            return d
    return None


class HIDPP:
    def __init__(self, path):
        self.dev = hid.device()
        self.dev.open_path(path)

    def close(self):
        try:
            self.dev.close()
        except Exception:
            pass

    def request(self, dev_idx, feat_idx, func, params=(), timeout=0.30):
        payload = (list(params) + [0, 0, 0])[:3]
        buf = [HIDPP_SHORT, dev_idx, feat_idx, (func << 4) | SW_ID] + payload
        self.dev.write(buf)
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = self.dev.read(20, max(10, int((deadline - time.time()) * 1000)))
            if not r:
                break
            if len(r) < 4:
                continue
            if r[1] != dev_idx or (r[3] & 0x0F) != SW_ID:
                continue
            if r[2] == 0xFF:
                return None
            return r
        return None

    def feature(self, dev_idx, feature_id):
        r = self.request(dev_idx, 0x00, 0, [feature_id >> 8, feature_id & 0xFF])
        return r[4] if r else 0


def to_str(data):
    return bytes(b for b in data if 32 <= b < 127).decode("ascii", "ignore")


def main():
    iface = find_control_interface()
    if not iface:
        print("!! 没找到 HID++ 控制接口")
        return
    print(f"控制接口: {iface['path'].decode()}")
    hp = HIDPP(iface["path"])
    try:
        r = hp.request(0xFF, 0x00, 1, timeout=0.25)
        print(f"接收器 0xFF protocol = {r[4]}.{r[5]}" if r else "接收器 0xFF 无响应")

        print("\n== 逐个设备索引探测 ==")
        for dev_idx in range(1, 7):
            r = hp.request(dev_idx, 0x00, 1, timeout=0.15)
            if not r:
                print(f"  [{dev_idx}] 无响应")
                continue
            print(f"  [{dev_idx}] 在线, protocol={r[4]}.{r[5]}")

            fi = hp.feature(dev_idx, 0x0005)
            name = ""
            if fi:
                n = hp.request(dev_idx, fi, 0, timeout=0.2)
                if n:
                    length = n[4]
                    parts = []
                    for off in range(0, length, 3):
                        chunk = hp.request(dev_idx, fi, 1, [off], timeout=0.2)
                        if not chunk:
                            break
                        parts.append(bytes(chunk[4:7]))
                    name = to_str(b"".join(parts))
            print(f"       名称(0x0005): {name or '(无)'}")

            fi2 = hp.feature(dev_idx, 0x0003)
            if fi2:
                cnt = hp.request(dev_idx, fi2, 0, timeout=0.2)
                if cnt:
                    for e in range(min(cnt[4], 4)):
                        info = hp.request(dev_idx, fi2, 1, [e], timeout=0.2)
                        if info:
                            print(f"       FW实体[{e}] raw={[hex(x) for x in info[4:12]]} 文本={to_str(info[4:12])}")

            for fid, label in ((0x1000, "BATTERY_LEVEL_STATUS"), (0x1001, "BATTERY_VOLTAGE")):
                f = hp.feature(dev_idx, fid)
                if not f:
                    print(f"       {label}(0x{fid:04X}): 不支持")
                    continue
                rr = hp.request(dev_idx, f, 0, timeout=0.3)
                if rr:
                    print(f"       {label}(0x{fid:04X}) fi={f} raw={[x for x in rr[4:12]]}")
    finally:
        hp.close()


if __name__ == "__main__":
    main()
