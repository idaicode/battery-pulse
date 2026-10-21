"""生成应用图标：陶土色圆角方块 + 白色电池，多尺寸打进 .ico。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ACCENT = (191, 90, 60, 255)
CREAM = (250, 247, 240, 255)


def draw(size: int) -> Image.Image:
    ss = 8
    n = size * ss
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = int(n * 0.24)
    d.rounded_rectangle((0, 0, n - 1, n - 1), radius=r, fill=ACCENT)

    # 电池外形：横向圆角矩形 + 正极小凸起
    bw, bh = n * 0.56, n * 0.30
    bx0, by0 = (n - bw - n * 0.09) / 2, (n - bh) / 2
    bx1, by1 = bx0 + bw, by0 + bh
    lw = max(2, int(n * 0.045))
    d.rounded_rectangle((bx0, by0, bx1, by1), radius=int(bh * 0.32), outline=CREAM, width=lw)
    # 正极帽
    cap_w, cap_h = n * 0.055, bh * 0.42
    d.rounded_rectangle(
        (bx1 + n * 0.012, by0 + (bh - cap_h) / 2, bx1 + n * 0.012 + cap_w, by1 - (bh - cap_h) / 2),
        radius=int(cap_h * 0.35), fill=CREAM,
    )
    # 电量填充
    pad = bh * 0.26
    d.rounded_rectangle(
        (bx0 + pad, by0 + pad, bx0 + bw * 0.62, by1 - pad), radius=int(bh * 0.16), fill=CREAM,
    )
    return im.resize((size, size), Image.LANCZOS)


def main() -> None:
    out = ROOT / "ui" / "app.ico"
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    ims = [draw(s) for s in sizes]
    ims[-1].save(out, format="ICO", sizes=[(s, s) for s in sizes])
    for s, im in zip(sizes, ims):
        if s in (32, 64, 256):
            im.save(ROOT / "shots" / f"icon_{s}.png")
    print("saved", out, out.stat().st_size, "bytes")


if __name__ == "__main__":
    sys.exit(main())
