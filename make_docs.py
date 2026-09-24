# -*- coding: utf-8 -*-
"""生成 README 所需截图与示例产物 (开发用)。

用法:
    D:\\miniconda3\\envs\\chem_env\\python.exe make_docs.py

产物:
    docs/ui_structure.png  docs/ui_table.png  docs/ui_gif.png
    docs/demo.gif          docs/standalone_html.png
    outputs/bader_sample.gif  outputs/bader_sample.png
    outputs/bader_standalone.html
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import bader_core as core  # noqa: E402

TEST = ROOT / "test"
DOCS = ROOT / "docs"
OUT = ROOT / "outputs"
DOCS.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)


def load():
    files = core.discover_files(TEST)
    return files, core.load_bader_data(files["poscar"], files["acf"], files.get("potcar"))


def gen_samples():
    files, data = load()
    print(f"[docs] 数据: {data['atom_count']} 原子")
    core.render_gif(data, OUT / "bader_sample.gif", label_mode="charge",
                    color_mode="element", view="front", rot_axis="c",
                    frames=48, fps=18, width=560, with_legend=True,
                    log=lambda m: None)
    core.render_single_png(data, OUT / "bader_sample.png", label_mode="charge",
                           color_mode="element", view="front", width=900,
                           with_legend=True, log=lambda m: None)
    core.render_gif(data, DOCS / "demo.gif", label_mode="charge",
                    color_mode="element", view="front", rot_axis="c",
                    frames=48, fps=18, width=460, with_legend=True,
                    log=lambda m: None)
    core.export_standalone_html(data, OUT / "bader_standalone.html")
    print("[docs] 示例 GIF / PNG / HTML 完成")


def shoot_standalone():
    from playwright.sync_api import sync_playwright
    uri = (OUT / "bader_standalone.html").resolve().as_uri()
    with sync_playwright() as pw:
        browser = core.launch_browser(pw, None, True, None)
        page = browser.new_page(viewport={"width": 1400, "height": 920},
                                device_scale_factor=1.0)
        page.goto(uri, wait_until="load")
        page.wait_for_timeout(7000)
        page.screenshot(path=str(DOCS / "standalone_html.png"))
        browser.close()
    print("[docs] standalone_html.png 完成")


def shoot_gui():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from ui_kit import LIGHT, apply_theme
    import bader_gui as g

    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app, LIGHT)
    w = g.MainWindow()
    w.resize(1360, 860)
    w.e_dir.setText(str(TEST))
    w.show()

    steps = [0, 1, 2]
    names = {0: "ui_structure.png", 1: "ui_table.png", 2: "ui_gif.png"}

    def snap(i=0):
        if i >= len(steps):
            w.close()
            app.quit()
            return
        w.pages.setCurrentIndex(steps[i])
        QTimer.singleShot(700, lambda: (
            w.grab().save(str(DOCS / names[steps[i]])),
            print(f"[docs] {names[steps[i]]} 完成"),
            snap(i + 1),
        ))

    QTimer.singleShot(8000, snap)
    app.exec()


def main():
    gen_samples()
    shoot_standalone()
    shoot_gui()
    print("[docs] 全部完成")


if __name__ == "__main__":
    main()
