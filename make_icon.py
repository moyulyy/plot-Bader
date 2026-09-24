#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成 Bader 电荷可视化工作台的应用图标 assets/app.ico / assets/app.png。

设计: 青绿渐变圆角方块 + 原子符号（三条电子轨道 + 原子核 + 电子），
     与蓝色的 CONTCAR 图标区分开。

运行:
    D:\\miniconda3\\envs\\chem_env\\python.exe make_icon.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
OUT_ICO = ASSETS / "app.ico"
OUT_PNG = ASSETS / "app.png"


def rounded_gradient(size: int) -> Image.Image:
    """青绿 -> 深青 竖直渐变的圆角方块。"""
    scale = 4
    s = size * scale
    grad = Image.new("RGBA", (s, s))
    px = grad.load()
    top = (45, 212, 191)     # teal-400
    bot = (11, 96, 120)      # 深青
    for y in range(s):
        t = y / max(1, s - 1)
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        for x in range(s):
            px[x, y] = (r, g, b, 255)

    # 左上角高光
    hi = Image.new("L", (s, s), 0)
    ImageDraw.Draw(hi).polygon([(0, 0), (s, 0), (0, s)], fill=55)
    hi = hi.filter(ImageFilter.GaussianBlur(s * 0.12))
    grad = Image.composite(Image.new("RGBA", (s, s), (255, 255, 255, 255)),
                           grad, hi)

    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1],
                                           radius=int(s * 0.22), fill=255)
    out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask)
    return out.resize((size, size), Image.LANCZOS)


def draw_atom(img: Image.Image, supersample: int = 4) -> Image.Image:
    """在圆角方块上绘制原子（三条轨道 + 原子核 + 电子）。"""
    size = img.size[0]
    w = size * supersample
    base = img.resize((w, w), Image.LANCZOS)
    cx = cy = w / 2.0
    rx, ry = w * 0.40, w * 0.155
    line_w = max(2, int(round(w * 0.018)))

    orbits = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    for angle in (0.0, 60.0, 120.0):
        layer = Image.new("RGBA", (w, w), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                  outline=(255, 255, 255, 235), width=line_w)
        layer = layer.rotate(angle, resample=Image.BICUBIC, center=(cx, cy))
        orbits = Image.alpha_composite(orbits, layer)

    # 电子: 每条轨道放一个小圆点
    d = ImageDraw.Draw(orbits)
    r_e = w * 0.045
    for angle, theta_deg in ((0.0, 20.0), (60.0, 140.0), (120.0, 260.0)):
        theta = math.radians(theta_deg)
        ex, ey = rx * math.cos(theta), ry * math.sin(theta)
        a = math.radians(angle)
        x = cx + ex * math.cos(a) - ey * math.sin(a)
        y = cy + ex * math.sin(a) + ey * math.cos(a)
        d.ellipse([x - r_e, y - r_e, x + r_e, y + r_e], fill=(255, 255, 255, 255))

    # 原子核
    r_n = w * 0.078
    d.ellipse([cx - r_n, cy - r_n, cx + r_n, cy + r_n], fill=(255, 255, 255, 255))
    d.ellipse([cx - r_n * 0.42, cy - r_n * 0.42,
               cx + r_n * 0.42, cy + r_n * 0.42], fill=(45, 212, 191, 255))

    composed = Image.alpha_composite(base, orbits)
    return composed.resize((size, size), Image.LANCZOS)


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    img = draw_atom(rounded_gradient(256))
    img.save(OUT_PNG)
    img.save(OUT_ICO, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                             (64, 64), (128, 128), (256, 256)])
    print(f"[完成] 已生成 {OUT_ICO}")
    print(f"[完成] 已生成 {OUT_PNG}")


if __name__ == "__main__":
    main()
