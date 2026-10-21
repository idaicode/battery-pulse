"""离屏渲染菜单，导出 PNG 供检查（不弹窗）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from core.menu import PopupMenu  # noqa: E402

STATE = {
    "device": {
        "name": "G304 Lightspeed Wireless Gaming Mouse",
        "percent": 90,
        "level": 0,
        "status_line": "正常 · 2.4G 接收器 · 刚刚同步",
    },
    "warn_threshold": 20,
    "notify": True,
    "sound": True,
    "low_power": False,
    "autostart": True,
}

CASES = [
    ("normal", STATE),
    ("warn", {**STATE, "device": {"name": "RK98RGB 5.0", "percent": 15, "level": 1,
                                  "status_line": "偏低 · 蓝牙 · 12 秒前"}}),
    ("offline", {**STATE, "device": {"name": "RK98RGB 5.0", "percent": None, "level": 3,
                                     "status_line": "离线 · 2.4G 模式读不到电量"}}),
]


def main() -> None:
    scale = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    out_dir = ROOT / "shots"
    for name, state in CASES:
        m = PopupMenu(state, scale=scale)
        im = m.render()
        bg = Image.new("RGBA", (im.width + 40, im.height + 40), (232, 228, 218, 255))
        bg.alpha_composite(im, (20, 20))
        bg.convert("RGB").save(out_dir / f"menu_{name}.png")
        print(name, "size px:", im.size, "->", out_dir / f"menu_{name}.png")


if __name__ == "__main__":
    main()
