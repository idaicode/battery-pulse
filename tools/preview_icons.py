"""图标预览：把托盘图标在深/浅两种任务栏底色上放大排开，肉眼验收。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw  # noqa: E402

from core.tray import _render  # noqa: E402

CASES = [(86, 0), (63, 0), (18, 1), (7, 2), (None, 3), (100, 0)]
SIZES = [16, 24, 32]
SCALE = 6


def main() -> int:
    cell_w, cell_h = 170, 130
    cols = len(CASES)
    rows = len(SIZES) * 2  # 深色 / 浅色 两种底
    W, H = cell_w * cols, cell_h * rows
    canvas = Image.new("RGB", (W, H), (32, 33, 36))
    d = ImageDraw.Draw(canvas)

    for r in range(rows):
        dark = r < len(SIZES)
        bg = (32, 33, 36) if dark else (243, 243, 243)
        d.rectangle((0, r * cell_h, W, (r + 1) * cell_h), fill=bg)

    for bi, size in enumerate(SIZES):
        for dark, row_base in ((True, bi), (False, bi + len(SIZES))):
            for ci, (pct, lvl) in enumerate(CASES):
                icon = _render(size, pct, lvl)
                # 左侧贴真实尺寸（看像素密度），右侧放大一份（看细节）
                cx = ci * cell_w + 42
                cy = row_base * cell_h + 62
                canvas.paste(icon, (cx - size // 2, cy - size // 2), icon)
                big = icon.resize((size * 3, size * 3), Image.NEAREST)
                canvas.paste(big, (ci * cell_w + 78, cy - big.height // 2), big)

    out = ROOT / "shots" / "icons.png"
    canvas.save(out)
    print("saved", out, canvas.size, "| 行顺序: 16/24/32 深底, 16/24/32 浅底")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
