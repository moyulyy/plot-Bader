# -*- coding: utf-8 -*-
"""一键打包 Windows 便携版并生成 zip 压缩包。

用法:
    D:\\miniconda3\\envs\\chem_env\\python.exe build_exe.py

产物:
    dist/BaderChargeViewer/BaderChargeViewer.exe     # 便携版程序(双击运行)
    dist/BaderChargeViewer-<版本>-win64-portable.zip # 可分发的压缩包
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_NAME = "BaderChargeViewer"
VERSION = "1.0.0"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP_DIR = DIST / APP_NAME
ZIP_PATH = DIST / f"{APP_NAME}-{VERSION}-win64-portable.zip"


def run(cmd: list[str]) -> None:
    print("[build]", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)


def main() -> int:
    print(f"== 打包 {APP_NAME} v{VERSION} ==")
    for p in (BUILD, DIST):
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)

    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         f"{APP_NAME}.spec"])

    exe = APP_DIR / f"{APP_NAME}.exe"
    if not exe.is_file():
        print("!! 未找到生成的 exe:", exe, file=sys.stderr)
        return 1

    # 附带说明文件
    (APP_DIR / "使用说明.txt").write_text(
        "Bader 电荷可视化工作台 · 便携版\n"
        "================================\n\n"
        "1. 双击 BaderChargeViewer.exe 启动(无需安装 Python)。\n"
        "2. 左侧选择包含 POSCAR/CONTCAR、ACF.dat(可选 POTCAR)的目录。\n"
        "3. samples/ 目录内含示例数据(POSCAR/CONTCAR/ACF.dat)可直接试用。\n"
        "4. 生成 GIF 需要系统自带 Edge(Win10/11 默认)或 Chrome。\n\n"
        "输出文件默认写入本目录下的 outputs/ 文件夹。\n",
        encoding="utf-8",
    )

    print("[zip]", ZIP_PATH.name)
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(APP_DIR.rglob("*")):
            if f.is_file():
                z.write(f, Path(APP_NAME) / f.relative_to(APP_DIR))

    size = ZIP_PATH.stat().st_size
    print(f"== 完成: {exe}")
    print(f"== 压缩包: {ZIP_PATH} ({size / 1048576:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
