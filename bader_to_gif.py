#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Bader 电荷可视化命令行工具 (ACF.dat + POSCAR -> 旋转 GIF)。

示例:
    python bader_to_gif.py --poscar test/POSCAR --acf test/ACF.dat ^
        --out outputs/bader.gif --frames 60 --view front --rot-axis c

    # 只出一张静态 PNG
    python bader_to_gif.py --acf test/ACF.dat --poscar test/POSCAR ^
        --out outputs/bader.png --frames 1 --rot-angle 0

运行环境: D:\\miniconda3\\envs\\chem_env
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bader_core as core


def main():
    ap = argparse.ArgumentParser(
        description="把 ACF.dat + POSCAR 渲染成 Bader 电荷可视化的旋转 GIF",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--poscar", default="POSCAR", help="POSCAR / CONTCAR 路径")
    ap.add_argument("--acf", default="ACF.dat", help="ACF.dat 路径")
    ap.add_argument("--potcar", default=None,
                    help="POTCAR 路径 (可选, 用于计算 Δq); 缺省时在 ACF 同目录自动查找")
    ap.add_argument("-o", "--out", default="outputs/bader.gif",
                    help="输出 GIF; 若为 .png 则输出单帧")
    ap.add_argument("--html", default=None,
                    help="额外导出自包含的独立 HTML 结果页 (自带 3Dmol.js)")

    ap.add_argument("--label", default="charge",
                    choices=list(core.LABEL_MODES),
                    help="原子标注: charge/element/index/none")
    ap.add_argument("--color", default="element",
                    choices=list(core.COLOR_MODES),
                    help="着色方式: element/charge")
    ap.add_argument("--style", default="ballstick",
                    choices=["ballstick", "sphere", "stick", "line"],
                    help="显示风格")
    ap.add_argument("--no-labels", dest="show_labels", action="store_false",
                    default=True, help="不显示原子标签")
    ap.add_argument("--no-cell", dest="show_cell", action="store_false",
                    default=True, help="不显示晶胞框")
    ap.add_argument("--no-legend", dest="with_legend", action="store_false",
                    default=True, help="不叠加底部图例")
    ap.add_argument("--bg", default="white", help="背景色 (white/black/#rrggbb)")
    ap.add_argument("--radius-scale", type=float, default=0.6,
                    help="VESTA 半径缩放系数 (默认 0.6)")
    ap.add_argument("--zoom", type=float, default=1.1, help="取景缩放 (默认 1.1)")

    ap.add_argument("--view", default="front", choices=list(core.VIEW_NAMES),
                    help="基准视角 (默认 front)")
    ap.add_argument("--rot-axis", default="c",
                    choices=["a", "b", "c", "screen-v", "screen-h"],
                    help="旋转轴 (默认 c)")
    ap.add_argument("--rot-angle", type=float, default=360.0,
                    help="整段旋转总角度 (默认 360)")
    ap.add_argument("--frames", type=int, default=60, help="帧数 (默认 60)")
    ap.add_argument("--fps", type=float, default=20.0, help="帧率 (默认 20)")
    ap.add_argument("--pingpong", action="store_true", help="正放 + 倒放")
    ap.add_argument("--loop", type=int, default=0,
                    help="循环次数, 0 = 无限 (默认 0); -1 = 不循环")
    ap.add_argument("--colors", type=int, default=256, help="GIF 调色板颜色数")

    ap.add_argument("-w", "--width", type=int, default=640, help="宽 (像素)")
    ap.add_argument("--height", type=int, default=None, help="高 (像素, 默认同宽)")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="超采样倍率, 2 更清晰")
    ap.add_argument("--gif-width", type=int, default=None,
                    help="GIF 输出宽度 (默认同 --width)")
    ap.add_argument("--browser", default=None,
                    help="浏览器 channel (msedge/chrome), 默认自动查找")
    ap.add_argument("--show-browser", action="store_true", help="显示浏览器窗口")

    args = ap.parse_args()

    if args.height is None:
        args.height = args.width

    data = core.load_bader_data(args.poscar, args.acf, args.potcar)
    print(f"[信息] {data['atom_count']} 个原子, 元素 {data['elements']}")
    print(f"[信息] 总 Bader 电荷 {data['total_charge']:.4f} e")
    for w in data["warnings"]:
        print(f"[警告] {w}")
    if data["has_delta"]:
        print(f"[信息] Δq 范围 {data['value_min']:.4f} ~ {data['value_max']:.4f} e")
    else:
        print("[信息] 未使用 POTCAR, 显示原始 Bader 电荷")

    if args.html:
        hp = core.export_standalone_html(data, args.html)
        print(f"[完成] 已导出独立 HTML: {hp}")

    out = str(args.out)
    if out.lower().endswith(".png"):
        res = core.render_single_png(
            data, out, label_mode=args.label, color_mode=args.color,
            view=args.view, width=args.width, height=args.height,
            style=args.style, radius_scale=args.radius_scale,
            show_cell=args.show_cell, bg=args.bg, zoom=args.zoom,
            show_labels=args.show_labels, browser=args.browser,
            show_browser=args.show_browser, log=print)
        print(f"[完成] {res}")
        return

    loop = None if args.loop is not None and args.loop < 0 else args.loop
    res = core.render_gif(
        data, out, label_mode=args.label, color_mode=args.color,
        view=args.view, rot_axis=args.rot_axis, rot_total=args.rot_angle,
        frames=args.frames, fps=args.fps, width=args.width, height=args.height,
        style=args.style, radius_scale=args.radius_scale,
        show_cell=args.show_cell, bg=args.bg, zoom=args.zoom,
        pingpong=args.pingpong, loop=loop, colors=args.colors,
        scale=args.scale, gif_width=args.gif_width,
        show_labels=args.show_labels, with_legend=args.with_legend,
        browser=args.browser, show_browser=args.show_browser, log=print)
    print(f"[完成] {res['path']}  {res['frames']} 帧  {res['size_mb']:.2f} MB")


if __name__ == "__main__":
    sys.exit(main())
