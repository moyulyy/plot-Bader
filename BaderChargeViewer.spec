# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

生成便携版目录 dist/BaderChargeViewer/（内含 BaderChargeViewer.exe）。
    pyinstaller --noconfirm --clean BaderChargeViewer.spec
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

APP_NAME = "BaderChargeViewer"

datas = [
    ("3dmol/3Dmol-min.js", "3dmol"),
    ("assets", "assets"),
    ("samples", "samples"),
]
binaries = []
hiddenimports = []

# 打包 Playwright(Python 端) ，用于调用系统 Edge/Chrome 逐帧渲染 GIF。
# 其浏览器内核不打包，运行时使用系统自带 Edge(Win10/11 默认)。
for _pkg in ("playwright",):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h
hiddenimports += collect_submodules("playwright")

a = Analysis(
    ["bader_gui.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib", "tkinter", "PyQt5", "PyQt6", "PySide2",
        "IPython", "pytest", "notebook", "jupyter", "pandas", "scipy",
        "setuptools", "pip", "wheel",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/app.ico",
    version="assets/version_info.txt",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
