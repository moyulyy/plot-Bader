#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Bader 电荷分析可视化核心 (ACF.dat + POSCAR -> 3D 结构 / 旋转 GIF)。

处理逻辑参考 work-list-0809 项目 ``/bader`` 页面 (bader_module/analysis.py +
static/bader.js): 按原子序号把 POSCAR 的元素与 ACF.dat 的 Bader 电荷对应,
可选地用 POTCAR 的 ZVAL 计算电荷差 Δq = q_Bader - ZVAL; 结构可视化提供
「原子序号 / 元素类型 / Bader 电荷差」三种标注方式。

GIF 渲染参考 CONT-gif 项目 (contcar_to_gif.py + viewer3d.py):
    结构 -> 3Dmol.js(浏览器 WebGL) 正交相机 -> Playwright 逐帧截图
    -> Pillow 合成旋转 GIF

运行环境: D:\\miniconda3\\envs\\chem_env
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent


def _bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return HERE


BUNDLE_DIR = _bundle_dir()

THREEDMOL_CANDIDATES = [
    HERE / "3dmol" / "3Dmol-min.js",
    BUNDLE_DIR / "3dmol" / "3Dmol-min.js",
    HERE.parent / "work-list-0809" / "static" / "vendor" / "3Dmol-min.js",
]
THREEDMOL_CDN = "https://3dmol.org/build/3Dmol-min.js"


# ==========================================================================
# 元素配色 / 半径
# ==========================================================================
# 与 bader.js 一致的完整周期表配色 (Jmol 风格), 用于元素着色。
ELEMENT_COLORS: dict[str, str] = {
    "H": "#FFFFFF", "He": "#D9FFFF", "Li": "#CC80FF", "Be": "#C2FF00",
    "B": "#FFB5B5", "C": "#909090", "N": "#3050F8", "O": "#FF0D0D",
    "F": "#90E050", "Ne": "#B3E3F5", "Na": "#AB5CF2", "Mg": "#8AFF00",
    "Al": "#BFA6A6", "Si": "#F0C8A0", "P": "#FF8000", "S": "#FFFF30",
    "Cl": "#1FF01F", "Ar": "#80D1E3", "K": "#8F40D4", "Ca": "#3DFF00",
    "Sc": "#E6E6E6", "Ti": "#BFC2C7", "V": "#A6A6AB", "Cr": "#8A99C7",
    "Mn": "#9C7AC7", "Fe": "#E06633", "Co": "#F090A0", "Ni": "#50D050",
    "Cu": "#C88033", "Zn": "#7D80B0", "Ga": "#C28F8F", "Ge": "#668F8F",
    "As": "#BD80E3", "Se": "#FFA100", "Br": "#A62929", "Kr": "#5CB8D1",
    "Rb": "#702EB0", "Sr": "#00FF00", "Y": "#94FFFF", "Zr": "#94E0E0",
    "Nb": "#73C2C9", "Mo": "#54B5B5", "Tc": "#3B9E9E", "Ru": "#248F8F",
    "Rh": "#0A7D8C", "Pd": "#006985", "Ag": "#C0C0C0", "Cd": "#FFD98F",
    "In": "#A67573", "Sn": "#668080", "Sb": "#9E63B5", "Te": "#D47A00",
    "I": "#940094", "Xe": "#429EB0", "Cs": "#57178F", "Ba": "#00C900",
    "La": "#70D4FF", "Ce": "#FFFFC7", "Pt": "#D0D0E0", "Au": "#FFD123",
    "Pb": "#575961", "Bi": "#9E4FB5", "U": "#008FFF",
}

# VESTA 经典半径 (Å), 用于球/键半径。
VESTA_RADII: dict[str, float] = {
    "H": 0.46, "C": 0.77, "N": 0.75, "O": 0.74, "F": 0.71, "Na": 1.02,
    "Mg": 0.72, "Al": 0.54, "Si": 1.17, "P": 1.10, "S": 1.04, "Cl": 0.99,
    "K": 1.38, "Ca": 1.00, "Sc": 1.70, "Ti": 0.86, "V": 1.71,
    "Cr": 1.66, "Mn": 1.61, "Fe": 0.83, "Co": 1.25, "Ni": 1.25,
    "Cu": 1.17, "Zn": 1.25, "Ga": 1.12, "Ge": 1.16, "As": 1.20,
    "Se": 1.16, "Br": 1.14, "Mo": 1.50, "Ru": 1.25, "Rh": 1.25,
    "Pd": 1.20, "Ag": 1.28, "Cd": 1.36, "In": 1.42, "Sn": 1.40,
    "Sb": 1.40, "Te": 1.36, "I": 1.33, "Pt": 1.23, "Au": 1.24,
    "Pb": 1.44, "Bi": 1.51,
}

DEFAULT_ELEMENT_COLOR = "#7c8798"
DEFAULT_RADIUS = 1.20


def element_color(symbol: str) -> str:
    return ELEMENT_COLORS.get(symbol, DEFAULT_ELEMENT_COLOR)


def element_radius(symbol: str, scale: float = 0.6,
                   uniform: float | None = None) -> float:
    if uniform is not None:
        return float(uniform)
    return round(VESTA_RADII.get(symbol, DEFAULT_RADIUS) * float(scale), 3)


# 电荷差配色 (蓝 = 电子亏损 / 负, 白 = 中性, 红 = 电子富集 / 正)
CHARGE_NEG = (29, 78, 216)      # #1d4ed8
CHARGE_MID = (243, 244, 246)    # #f3f4f6
CHARGE_POS = (185, 28, 28)      # #b91c1c


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _rgb_to_hex(rgb: Iterable[int]) -> str:
    r, g, b = (max(0, min(255, int(v))) for v in rgb)
    return "#%02x%02x%02x" % (r, g, b)


def charge_to_rgb(value: float, vmin: float, vmax: float) -> tuple[int, int, int]:
    """把电荷值映射到蓝-白-红发散色带 (以 0 为中心)。"""
    m = max(abs(float(vmin)), abs(float(vmax)), 1e-9)
    t = (float(value) + m) / (2.0 * m)
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return _lerp(CHARGE_NEG, CHARGE_MID, t / 0.5)
    return _lerp(CHARGE_MID, CHARGE_POS, (t - 0.5) / 0.5)


def charge_to_color(value: float, vmin: float, vmax: float) -> str:
    return _rgb_to_hex(charge_to_rgb(value, vmin, vmax))


def build_element_map(symbols: Iterable[str], radius_scale: float = 0.6,
                      uniform_radius: float | None = None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for el in sorted(set(symbols)):
        out[el] = {
            "color": element_color(el),
            "radius": element_radius(el, radius_scale, uniform_radius),
        }
    return out


# ==========================================================================
# 解析 POSCAR / ACF.dat / POTCAR
# ==========================================================================
def _read_text(path: str | os.PathLike[str]) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def parse_poscar(path: str | os.PathLike[str]) -> dict[str, Any]:
    """解析 POSCAR/CONTCAR, 返回晶格矢量与元素信息。

    原子坐标不使用 POSCAR 中的值 —— 与 /bader 页面一致, 结构坐标取 ACF.dat
    给出的笛卡尔坐标, POSCAR 只提供晶格矢量与元素种类/数量。
    """
    lines = _read_text(path).splitlines()
    if len(lines) < 8:
        raise ValueError("POSCAR 文件格式异常 (行数不足)")
    title = lines[0].strip()
    try:
        scale = float(lines[1].split()[0])
    except (ValueError, IndexError) as exc:
        raise ValueError("POSCAR 中的缩放因子无法解析") from exc

    lattice = []
    for line in lines[2:5]:
        parts = line.split()
        if len(parts) < 3:
            raise ValueError("POSCAR 中的晶格矢量格式异常")
        lattice.append([scale * float(parts[0]),
                        scale * float(parts[1]),
                        scale * float(parts[2])])

    elements = re.findall(r"[A-Z][a-z]*", lines[5])
    counts = [int(v) for v in re.findall(r"\d+", lines[6])]
    if not elements or not counts or len(elements) != len(counts):
        raise ValueError("POSCAR 中的元素或计数无法正确解析")

    symbols: list[str] = []
    for el, count in zip(elements, counts):
        symbols.extend([el] * count)

    return {
        "title": title,
        "scale": scale,
        "lattice": lattice,
        "elements": elements,
        "counts": counts,
        "symbols": symbols,
    }


def parse_acf(path: str | os.PathLike[str]) -> list[dict[str, float]]:
    """解析 ACF.dat 的原子表 (X Y Z CHARGE MIN DIST ATOMIC VOL)。"""
    lines = _read_text(path).splitlines()
    if len(lines) < 4:
        raise ValueError("ACF.dat 文件格式异常")
    atoms: list[dict[str, float]] = []
    for line in lines[2:]:
        parts = line.strip().split()
        if len(parts) < 5:
            # 到达分隔线 / 统计信息, 停止
            if atoms:
                break
            continue
        try:
            index = int(float(parts[0]))
            x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
            charge = float(parts[4])
        except ValueError:
            if atoms:
                break
            continue
        min_dist = float(parts[5]) if len(parts) > 5 else 0.0
        volume = float(parts[6]) if len(parts) > 6 else 0.0
        atoms.append({
            "index": index, "x": x, "y": y, "z": z,
            "charge": charge, "min_dist": min_dist, "volume": volume,
        })
    if not atoms:
        raise ValueError("ACF.dat 中未解析到原子数据")
    return atoms


def parse_potcar_zval(path: str | os.PathLike[str], counts: list[int]) -> list[float]:
    """从 POTCAR 读取每个元素的 ZVAL, 并按 counts 展开成逐原子列表。"""
    content = _read_text(path)
    zvals = [float(v) for v in re.findall(r"ZVAL\s*=\s*([-+]?\d+(?:\.\d+)?)", content)]
    if len(zvals) < len(counts):
        raise ValueError("POTCAR 中的 ZVAL 数量少于 POSCAR 的元素种类数")
    expanded: list[float] = []
    for zval, count in zip(zvals, counts):
        expanded.extend([zval] * count)
    return expanded


def auto_find_file(folder: str | os.PathLike[str], names: Iterable[str]) -> str | None:
    folder = Path(folder)
    for name in names:
        candidate = folder / name
        if candidate.is_file():
            return str(candidate)
    return None


def discover_files(folder: str | os.PathLike[str]) -> dict[str, Any]:
    """从给定目录自动查找 Bader 分析所需的输入文件。

    返回 {"folder", "poscar", "acf", "potcar"}; 未找到的文件为 None。
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"目录不存在: {folder}")
    return {
        "folder": str(folder),
        "poscar": auto_find_file(folder, ("POSCAR", "CONTCAR",
                                          "POSCAR.vasp", "CONTCAR.vasp")),
        "acf": auto_find_file(folder, ("ACF.dat", "ACF.dat.txt")),
        "potcar": auto_find_file(folder, ("POTCAR", "POTCAR.txt")),
    }


def load_bader_data(poscar_path: str, acf_path: str,
                    potcar_path: str | None = None,
                    auto_potcar: bool = True) -> dict[str, Any]:
    """读取并合并 POSCAR + ACF.dat (+ 可选 POTCAR), 返回统一数据结构。"""
    if not poscar_path or not os.path.isfile(poscar_path):
        raise FileNotFoundError(f"找不到 POSCAR 文件: {poscar_path}")
    if not acf_path or not os.path.isfile(acf_path):
        raise FileNotFoundError(f"找不到 ACF.dat 文件: {acf_path}")

    poscar = parse_poscar(poscar_path)
    acf_atoms = parse_acf(acf_path)

    if potcar_path is None and auto_potcar:
        potcar_path = auto_find_file(Path(acf_path).parent, ("POTCAR",))
    if potcar_path and not os.path.isfile(potcar_path):
        potcar_path = None

    warnings: list[str] = []
    npos = len(poscar["symbols"])
    if len(acf_atoms) != npos:
        raise ValueError(
            f"ACF.dat 原子数 ({len(acf_atoms)}) 与 POSCAR 原子数 ({npos}) 不一致")

    # 与 /bader 页面一致: 按 ACF 中的原子编号排序后再对应
    ordered = sorted(acf_atoms, key=lambda a: a["index"])
    indices = [a["index"] for a in ordered]
    if indices != list(range(1, npos + 1)):
        warnings.append("ACF.dat 中的原子编号不连续或与顺序不一致, 已按编号重新排序。")

    has_delta = False
    zvals: list[float] | None = None
    if potcar_path:
        try:
            zvals = parse_potcar_zval(potcar_path, poscar["counts"])
            if len(zvals) != npos:
                raise ValueError("POTCAR 展开后的 ZVAL 数量与原子数不一致")
            has_delta = True
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"POTCAR 解析失败, 改用原始 Bader 电荷: {exc}")
            zvals = None

    atoms: list[dict[str, Any]] = []
    for i in range(npos):
        acf_atom = ordered[i]
        symbol = poscar["symbols"][i]
        charge = float(acf_atom["charge"])
        entry: dict[str, Any] = {
            "index": i + 1,
            "symbol": symbol,
            "x": round(float(acf_atom["x"]), 6),
            "y": round(float(acf_atom["y"]), 6),
            "z": round(float(acf_atom["z"]), 6),
            "charge": round(charge, 6),
            "min_dist": round(float(acf_atom.get("min_dist", 0.0)), 6),
            "volume": round(float(acf_atom.get("volume", 0.0)), 6),
        }
        if zvals is not None:
            zval = float(zvals[i])
            entry["zval"] = round(zval, 6)
            entry["delta_charge"] = round(charge - zval, 6)
        atoms.append(entry)

    value_key = "delta_charge" if has_delta else "charge"
    values = [a[value_key] for a in atoms]

    return {
        "poscar_path": poscar_path,
        "acf_path": acf_path,
        "potcar_path": potcar_path if has_delta else None,
        "title": poscar["title"],
        "lattice": poscar["lattice"],
        "elements": poscar["elements"],
        "counts": poscar["counts"],
        "atoms": atoms,
        "atom_count": len(atoms),
        "has_delta": has_delta,
        "value_key": value_key,
        "value_min": min(values) if values else 0.0,
        "value_max": max(values) if values else 0.0,
        "total_charge": round(sum(a["charge"] for a in atoms), 6),
        "warnings": warnings,
    }


# ==========================================================================
# 几何 / 四元数 (与 CONT-gif 的 3Dmol 相机约定一致)
# ==========================================================================
VIEW_NAMES = ["front", "back", "top", "bottom", "right", "left"]
VIEW_LABELS = {
    "front": "正视", "back": "后视", "top": "俯视",
    "bottom": "仰视", "right": "右视", "left": "左视",
}
ROT_AXIS_NAMES = {
    "a": "a 轴", "b": "b 轴", "c": "c 轴",
    "screen-v": "屏幕竖直", "screen-h": "屏幕水平",
}


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    n = float(np.linalg.norm(v))
    if n < 1e-12:
        return np.array([1.0, 0.0, 0.0])
    return v / n


def cell_edges(lattice) -> list[list[float]]:
    """返回晶胞 12 条棱 [(x1,y1,z1,x2,y2,z2), ...]。"""
    cell = np.asarray(lattice, dtype=float).reshape(3, 3)
    corners = {k: i * cell[0] + j * cell[1] + kk * cell[2]
               for i in (0, 1) for j in (0, 1) for kk in (0, 1)
               for k in [(i, j, kk)]}
    edges = []
    for (i, j, k), p in corners.items():
        for d in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
            q = (i + d[0], j + d[1], k + d[2])
            if q in corners:
                r = corners[q]
                edges.append([float(p[0]), float(p[1]), float(p[2]),
                              float(r[0]), float(r[1]), float(r[2])])
    return edges


def fit_sphere(atoms: list[dict[str, Any]], lattice=None,
               include_cell: bool = True) -> list[float]:
    """取景包围球 [cx, cy, cz, radius]。"""
    pts = np.array([[a["x"], a["y"], a["z"]] for a in atoms], dtype=float)
    if include_cell and lattice is not None:
        cell = np.asarray(lattice, dtype=float).reshape(3, 3)
        corners = np.array([[i * cell[0] + j * cell[1] + k * cell[2]]
                            for i in (0, 1) for j in (0, 1) for k in (0, 1)]).reshape(-1, 3)
        pts = np.vstack([pts, corners])
    lo, hi = pts.min(0), pts.max(0)
    center = (lo + hi) / 2.0
    radius = float(np.linalg.norm(pts - center, axis=1).max())
    return [float(center[0]), float(center[1]), float(center[2]), max(radius, 1.0)]


def _quat_from_matrix(m) -> list[float]:
    m = np.asarray(m, dtype=float)
    t = float(m[0, 0] + m[1, 1] + m[2, 2])
    if t > 0.0:
        s = math.sqrt(t + 1.0) * 2.0
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s
    q = np.array([x, y, z, w], dtype=float)
    n = float(np.linalg.norm(q))
    if n < 1e-12:
        return [0.0, 0.0, 0.0, 1.0]
    q /= n
    if q[3] < 0:
        q = -q
    return [float(v) for v in q]


def _quat_matrix(q) -> np.ndarray:
    x, y, z, w = (float(v) for v in q)
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _axis_angle_matrix(axis, ang: float) -> np.ndarray:
    n = _unit(axis)
    k = np.array([[0.0, -n[2], n[1]], [n[2], 0.0, -n[0]], [-n[1], n[0], 0.0]])
    return np.eye(3) + math.sin(ang) * k + (1.0 - math.cos(ang)) * (k @ k)


def view_quaternion(lattice, name: str) -> list[float] | None:
    """根据晶胞矢量计算预设视角的四元数 (与 CONT-gif 一致)。"""
    try:
        cell = np.asarray(lattice, dtype=float).reshape(3, 3)
        a, b, c = cell[0], cell[1], cell[2]
        if name in ("front", "back"):
            ex, ey = _unit(a), c
        elif name in ("top", "bottom"):
            ex, ey = _unit(a), b
        else:
            ex, ey = _unit(b), c
        if name in ("back", "bottom", "left"):
            ex = -ex
        ey = np.asarray(ey, dtype=float) - float(np.dot(ey, ex)) * ex
        ey = _unit(ey)
        ez = _unit(np.cross(ex, ey))
        return _quat_from_matrix(np.array([ex, ey, ez]))
    except Exception:  # noqa: BLE001
        return None


def rotation_views(lattice, base_quat, axis_key: str, total_deg: float,
                   n: int, closed: bool | None = None) -> list[list[float]]:
    """绕指定轴匀速旋转, 返回 n 个朝向四元数。"""
    cell = np.asarray(lattice, dtype=float).reshape(3, 3)
    a, b, c = cell[0], cell[1], cell[2]
    if axis_key == "a":
        axis = _unit(a)
    elif axis_key == "b":
        axis = _unit(b)
    elif axis_key == "c":
        axis = _unit(c)
    else:
        axis = None
    rb = _quat_matrix(base_quat)
    if axis is None:
        axis = rb[1] if axis_key == "screen-v" else rb[0]
    axis = _unit(axis)

    n = max(1, int(n))
    total = float(total_deg)
    if closed is None:
        closed = (n > 1 and abs(total) > 1e-9
                  and abs(abs(total) % 360.0) < 1e-6)
    out = []
    for k in range(n):
        if n <= 1:
            t = 0.0
        elif closed:
            t = k / n
        else:
            t = k / (n - 1)
        ang = math.radians(total) * t
        r = rb @ _axis_angle_matrix(axis, ang)
        out.append(_quat_from_matrix(r))
    return out


# ==========================================================================
# 3Dmol.js
# ==========================================================================
def ensure_3dmol_js() -> str:
    for cand in THREEDMOL_CANDIDATES:
        if cand.is_file():
            return cand.read_text(encoding="utf-8", errors="ignore")
    raise FileNotFoundError(
        "未找到 3Dmol.js。请把 3Dmol-min.js 放到项目 3dmol/ 目录, "
        f"或手动下载 {THREEDMOL_CDN}")


# ==========================================================================
# HTML 构建
# ==========================================================================
LABEL_MODES = ["charge", "element", "index", "none"]
LABEL_MODE_NAMES = {
    "charge": "Bader 电荷差 (Δq)",
    "element": "元素类型",
    "index": "原子序号",
    "none": "不显示标签",
}
COLOR_MODES = ["element", "charge"]
COLOR_MODE_NAMES = {"element": "按元素着色", "charge": "按电荷差着色"}


def build_html(js: str, geom: dict[str, Any], cfg: dict[str, Any]) -> str:
    """生成内嵌 3Dmol.js 的 HTML 页面。

    geom: {"xyz","edges","elem_map","atom_colors","atom_radii","labels","fit"}
    cfg:  {"style","show_cell","cell_color","bg","zoom","pan","label_size",
           "interactive","views","orient","fov"}
    """
    xyz = geom["xyz"]
    edges = geom.get("edges") or []
    elem_map = geom.get("elem_map") or {}
    atom_colors = geom.get("atom_colors")
    atom_radii = geom.get("atom_radii")
    labels = geom.get("labels")
    fit = geom.get("fit")

    bg = cfg.get("bg") or "white"
    style = cfg.get("style") or "ballstick"
    show_cell = bool(cfg.get("show_cell", True))
    cell_color = cfg.get("cell_color") or "#888888"
    zoom = float(cfg.get("zoom", 1.25))
    pan = [float(v) for v in (cfg.get("pan") or (0.0, 0.0))]
    label_size = int(cfg.get("label_size", 12))
    interactive = bool(cfg.get("interactive", False))
    views = cfg.get("views")
    orient = cfg.get("orient")
    fov = float(cfg.get("fov", 20.0))

    views_json = json.dumps(views) if views else "null"
    orient_json = json.dumps(list(orient)) if orient is not None else "null"
    fit_json = json.dumps([float(v) for v in fit]) if fit else "null"
    atom_colors_json = json.dumps(atom_colors) if atom_colors else "null"
    atom_radii_json = json.dumps(atom_radii) if atom_radii else "null"
    labels_json = json.dumps(labels) if labels else "null"

    interact_js = ""
    if interactive:
        interact_js = """
window.resetView = function() { PAN = [PAN0[0], PAN0[1]]; ORTHO_ZOOM = 1.0;
                               viewer.setBackgroundColor(BG, 1.0); applyCamera(INIT_Q); };
window.setView = function(v) { viewer.setView(v); viewer.render(); };
window.getView = function() { return viewer.getView(); };
window.setPan = function(fx, fy) { PAN = [fx, fy]; refreshView(); };
window.setBackground = function(c) { viewer.setBackgroundColor(c, 1.0); viewer.render(); };
window.zoomByFactor = function(f) { ORTHO_ZOOM *= f; refreshView(); };
(function() {
  var el = document.getElementById('v');
  el.addEventListener('wheel', function(e) {
    e.preventDefault(); e.stopPropagation();
    var d = e.deltaY; if (!d) return;
    ORTHO_ZOOM = Math.max(0.05, Math.min(50.0,
                    ORTHO_ZOOM * (d < 0 ? 1.1 : 1.0 / 1.1)));
    refreshView();
  }, {passive: false, capture: true});
})();
"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Bader 3D</title>
<style>html,body{{width:100%;height:100%;margin:0;padding:0;overflow:hidden;background:{bg};}}
::-webkit-scrollbar{{width:0;height:0;display:none;}}
#v{{position:absolute;left:0;top:0;width:100%;height:100%;line-height:0;font-size:0;background:{bg};}}
#v canvas{{display:block;background:{bg};}}
#vfix{{position:absolute;left:0;bottom:0;width:100%;height:2px;background:{bg};pointer-events:none;}}</style>
<script>{js}</script></head>
<body>
<div id="v"></div>
<div id="vfix"></div>
<script>
const XYZ = {json.dumps(xyz)};
const EDGES = {json.dumps(edges)};
const ELEM = {json.dumps(elem_map)};
const ATOM_COLORS = {atom_colors_json};
const ATOM_RADII = {atom_radii_json};
const LABELS = {labels_json};
const STYLE_NAME = {json.dumps(style)};
const SHOW_CELL = {str(show_cell).lower()};
const CELL_COLOR = {json.dumps(cell_color)};
const BG = {json.dumps(bg)};
const FIT = {fit_json};
const ZOOM = {zoom};
const PAN0 = {json.dumps(pan)};
const ORIENT = {orient_json};
const VIEWS = {views_json};
const LABEL_SIZE = {label_size};
const FOV = {fov};

var viewer = $3Dmol.createViewer(document.getElementById('v'), {{backgroundColor: BG}});
viewer.addModel(XYZ, 'xyz');

function styleFor(color, radius) {{
  var st = {{}};
  var r = radius || 0.4;
  if (STYLE_NAME === 'sphere') st.sphere = {{radius: r}};
  else if (STYLE_NAME === 'stick') st.stick = {{radius: r * 0.35}};
  else if (STYLE_NAME === 'line') st.line = {{linewidth: 2}};
  else {{ st.stick = {{radius: r * 0.35}}; st.sphere = {{radius: r}}; }}
  if (color) {{
    if (st.sphere) st.sphere.color = color;
    if (st.stick) st.stick.color = color;
    if (st.line) st.line.color = color;
  }}
  return st;
}}

viewer.setStyle({{}}, styleFor(null, 0.4));
for (var el in ELEM) {{
  viewer.setStyle({{elem: el}}, styleFor(ELEM[el].color, ELEM[el].radius));
}}
if (ATOM_COLORS) {{
  for (var i = 0; i < ATOM_COLORS.length; i++) {{
    var rr = (ATOM_RADII && ATOM_RADII[i]) ? ATOM_RADII[i] : 0.4;
    viewer.setStyle({{index: i}}, styleFor(ATOM_COLORS[i], rr));
  }}
}}

function addCell() {{
  if (!SHOW_CELL) return;
  for (var i = 0; i < EDGES.length; i++) {{
    var e = EDGES[i];
    viewer.addLine({{start:{{x:e[0],y:e[1],z:e[2]}}, end:{{x:e[3],y:e[4],z:e[5]}},
                    color: CELL_COLOR, dashed: true, linewidth: 1}});
  }}
}}
addCell();

if (LABELS) {{
  for (var i = 0; i < LABELS.length; i++) {{
    var L = LABELS[i];
    viewer.addLabel(L.text, {{
      position: {{x: L.x, y: L.y, z: L.z}},
      fontSize: LABEL_SIZE,
      fontColor: L.color || '#111827',
      backgroundColor: 'rgba(255,255,255,0.82)',
      backgroundOpacity: 0.82,
      showBackground: true,
      inFront: true,
      alignment: 'center'
    }});
  }}
}}

// ---- 正交相机 (旋转时物体大小恒定) ----
viewer.setProjection('orthographic');
var ORTHO_ZOOM = 1.0;
var PAN = [PAN0[0], PAN0[1]];

function fovRadians() {{ return Math.PI / 180.0 * (viewer.fov || viewer.camera.fov || FOV); }}
function viewAspect() {{
  var a = viewer.ASPECT || (viewer.WIDTH && viewer.HEIGHT ? viewer.WIDTH / viewer.HEIGHT : 1.0);
  if (!isFinite(a) || a <= 0) a = 1.0;
  return a;
}}

function applyCamera(quat) {{
  if (!FIT) {{
    viewer.zoomTo(); viewer.zoom(ZOOM, 0);
    if (quat) {{
      var v = viewer.getView();
      viewer.setView([v[0], v[1], v[2], v[3], quat[0], quat[1], quat[2], quat[3]]);
    }}
    viewer.show();
    return;
  }}
  if (quat) viewer.rotationGroup.quaternion.set(quat[0], quat[1], quat[2], quat[3]);
  var fov = fovRadians();
  var aspect = viewAspect();
  var dist = FIT[3] * aspect / (ZOOM * ORTHO_ZOOM * Math.tan(fov));
  viewer.rotationGroup.position.set(0, 0, 0);
  viewer.rotationGroup.position.z = viewer.CAMERA_Z - dist;
  var halfW = dist * Math.tan(fov);
  var halfH = halfW / aspect;
  viewer.modelGroup.position.set(-FIT[0] + PAN[0] * 2.0 * halfW,
                                 -FIT[1] + PAN[1] * 2.0 * halfH,
                                 -FIT[2]);
  viewer.slabNear = -(FIT[3] + 20.0);
  viewer.slabFar = FIT[3] + 20.0;
  viewer.show();
}}
function refreshView() {{ applyCamera(null); }}

var INIT_Q = ORIENT || ((VIEWS && VIEWS[0]) ? VIEWS[0] : [0, 0, 0, 1]);
applyCamera(INIT_Q);
viewer.render();

window.showFrame = function(i) {{
  var q = (VIEWS && VIEWS[i % VIEWS.length]) ? VIEWS[i % VIEWS.length] : INIT_Q;
  applyCamera(q);
  viewer.render();
  window.currentFrame = i;
}};
window.capture = function() {{ return viewer.pngURI(); }};
window.numFrames = (VIEWS && VIEWS.length) ? VIEWS.length : 1;
window.setOrient = function(q) {{ INIT_Q = q; applyCamera(q); }};
window.addEventListener('resize', function () {{
  try {{ viewer.resize(); refreshView(); }} catch (e) {{}}
}});
{interact_js}
window.ready = true;
</script></body></html>"""


def build_geometry(data: dict[str, Any], label_mode: str = "charge",
                   color_mode: str = "element", radius_scale: float = 0.6,
                   uniform_radius: float | None = None,
                   show_labels: bool = True,
                   label_min_count: int = 0) -> dict[str, Any]:
    """根据数据与显示设置构造 3Dmol 几何信息。"""
    atoms = data["atoms"]
    symbols = [a["symbol"] for a in atoms]
    elem_map = build_element_map(symbols, radius_scale, uniform_radius)

    lines = [str(len(atoms)), "Bader structure"]
    for a in atoms:
        lines.append(f"{a['symbol']} {a['x']:.6f} {a['y']:.6f} {a['z']:.6f}")
    xyz = "\n".join(lines)

    value_key = data["value_key"]
    vmin, vmax = data["value_min"], data["value_max"]

    atom_colors = None
    if color_mode == "charge":
        atom_colors = [charge_to_color(a[value_key], vmin, vmax) for a in atoms]

    atom_radii = [elem_map[a["symbol"]]["radius"] for a in atoms]

    labels = None
    if show_labels and label_mode != "none" and len(atoms) >= int(label_min_count):
        labels = []
        for a in atoms:
            if label_mode == "index":
                text = str(a["index"])
                color = "#111827"
            elif label_mode == "element":
                text = a["symbol"]
                color = element_color(a["symbol"])
            else:  # charge
                if data["has_delta"]:
                    text = f"{a['delta_charge']:+.2f}"
                    color = "#b91c1c" if a["delta_charge"] >= 0 else "#1d4ed8"
                else:
                    text = f"{a['charge']:.2f}"
                    color = "#111827"
            labels.append({"x": a["x"], "y": a["y"], "z": a["z"],
                           "text": text, "color": color})

    return {
        "xyz": xyz,
        "edges": cell_edges(data["lattice"]),
        "elem_map": elem_map,
        "atom_colors": atom_colors,
        "atom_radii": atom_radii,
        "labels": labels,
        "fit": fit_sphere(atoms, data["lattice"], include_cell=True),
    }


# ==========================================================================
# 浏览器启动 (Playwright)
# ==========================================================================
def find_system_browser() -> str | None:
    names = ("msedge.exe", "chrome.exe")
    pf = os.environ.get("ProgramFiles") or r"C:\Program Files"
    pf86 = os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
    local = os.environ.get("LOCALAPPDATA") or ""
    cands = [
        os.path.join(pf86, r"Microsoft\Edge\Application\msedge.exe"),
        os.path.join(pf, r"Microsoft\Edge\Application\msedge.exe"),
        os.path.join(pf, r"Google\Chrome\Application\chrome.exe"),
        os.path.join(pf86, r"Google\Chrome\Application\chrome.exe"),
    ]
    if local:
        cands.append(os.path.join(local, r"Google\Chrome\Application\chrome.exe"))
        cands.append(os.path.join(local, r"Microsoft\Edge\Application\msedge.exe"))
    for p in cands:
        if p and os.path.isfile(p):
            return p
    try:
        import winreg
        bs = "\\"
        tail = ["Microsoft", "Windows", "CurrentVersion", "App Paths"]
        sub_keys = (bs.join(["SOFTWARE"] + tail),
                    bs.join(["SOFTWARE", "WOW6432Node"] + tail))
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in sub_keys:
                for nm in names:
                    try:
                        with winreg.OpenKey(root, sub + bs + nm) as key:
                            val = winreg.QueryValue(key, None)
                    except OSError:
                        continue
                    if val:
                        val = os.path.expandvars(str(val).strip('"'))
                        if os.path.isfile(val):
                            return val
    except Exception:  # noqa: BLE001
        pass
    for nm in names:
        p = shutil.which(nm)
        if p:
            return p
    return None


def launch_browser(pw, channel: str | None, headless: bool, log: Callable | None = None):
    tried, last = [], None
    if channel:
        plans = [(f"channel={channel}", {"channel": channel})]
    else:
        plans = []
        exe = find_system_browser()
        if exe:
            plans.append((exe, {"executable_path": exe}))
        plans.append(("channel=msedge", {"channel": "msedge"}))
        plans.append(("channel=chrome", {"channel": "chrome"}))
        plans.append(("playwright-chromium", {}))
    for label, extra in plans:
        try:
            browser = pw.chromium.launch(headless=headless, **extra)
            if log:
                log(f"[信息] 已启动浏览器: {label}")
            return browser
        except Exception as exc:  # noqa: BLE001
            tried.append(f"{label}: {exc}".splitlines()[0])
            last = exc
    raise RuntimeError(
        "无法启动浏览器:\n  " + "\n  ".join(tried) +
        "\n本程序需要系统自带的 Edge (Win10/11 默认都有) 或 Chrome, "
        "也可执行: python -m playwright install chromium\n"
        f"原始错误: {last}")


# ==========================================================================
# 逐帧渲染 / GIF 合成
# ==========================================================================
def render_pngs(data: dict[str, Any], geom: dict[str, Any], cfg: dict[str, Any],
                frames_dir: str | os.PathLike[str],
                progress: Callable[[int, int], None] | None = None,
                cancel: Callable[[], bool] | None = None,
                log: Callable[[str], None] | None = None) -> list[Path]:
    """用 Playwright + 3Dmol.js 逐帧截图, 返回 PNG 路径列表。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # noqa: BLE001
        raise RuntimeError("未安装 playwright, 请执行: pip install playwright") from exc

    frames_dir = Path(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    n = max(1, int(cfg.get("frames", 60)))
    width = max(80, int(cfg.get("width", 600)))
    height = max(80, int(cfg.get("height", width)))
    zoom = float(cfg.get("zoom", 1.25))
    ss = float(cfg.get("scale", 1.0) or 1.0)
    render_w = max(80, int(round(width * ss)))
    render_h = max(80, int(round(height * ss)))

    base_view = cfg.get("view", "front")
    base_quat = None
    if base_view in VIEW_NAMES:
        base_quat = view_quaternion(data["lattice"], base_view)
    if base_quat is None:
        base_quat = [0.0, 0.0, 0.0, 1.0]

    rot_axis = str(cfg.get("rot_axis", "c") or "")
    rot_total = float(cfg.get("rot_total", 360.0) or 0.0)
    if rot_axis and abs(rot_total) > 1e-9 and n > 1:
        views = rotation_views(data["lattice"], base_quat, rot_axis, rot_total, n)
        orient = None
    else:
        views = [list(base_quat) for _ in range(n)]
        orient = None

    js = ensure_3dmol_js()
    html_cfg = {
        "style": cfg.get("style", "ballstick"),
        "show_cell": cfg.get("show_cell", True),
        "cell_color": cfg.get("cell_color", "#888888"),
        "bg": cfg.get("bg", "white"),
        "zoom": zoom * ss,
        "pan": cfg.get("pan", (0.0, 0.0)),
        "label_size": cfg.get("label_size", 12) * max(1.0, ss),
        "interactive": False,
        "views": views,
        "orient": orient,
        "fov": 20.0,
    }
    html = build_html(js, geom, html_cfg)
    html_path = frames_dir / "_bader_viewer.html"
    html_path.write_text(html, encoding="utf-8")

    if log:
        log(f"[信息] 渲染 {n} 帧, CSS {render_w}x{render_h}, 超采样 x{ss:g}")

    paths: list[Path] = []
    with sync_playwright() as pw:
        browser = launch_browser(pw, cfg.get("browser"), not cfg.get("show_browser", False), log)
        page = browser.new_page(viewport={"width": render_w, "height": render_h},
                                device_scale_factor=1.0)
        page.goto(html_path.resolve().as_uri(), wait_until="domcontentloaded",
                  timeout=120000)
        page.wait_for_function("window.ready === true", timeout=120000)
        page.wait_for_timeout(400)
        total = page.evaluate("window.numFrames")
        for i in range(total):
            if cancel is not None and cancel():
                if log:
                    log("[信息] 已取消, 停止渲染")
                break
            page.evaluate(f"window.showFrame({i})")
            uri = page.evaluate("window.capture()")
            raw = base64.b64decode(uri.split(",", 1)[1])
            p = frames_dir / f"frame_{i:05d}.png"
            p.write_bytes(raw)
            paths.append(p)
            if progress is not None:
                progress(i + 1, total)
        browser.close()
    return paths


def build_gif(paths: list[Path], out_path: str | os.PathLike[str],
              duration: int = 50, loop: int | None = 0, colors: int = 256,
              pingpong: bool = False, width: int | None = None,
              annotate: Callable[[int, Image.Image], Image.Image] | None = None,
              log: Callable[[str], None] | None = None) -> int:
    """把 PNG 帧合成为 GIF, 返回帧数。"""
    frames = [Image.open(p).convert("RGB") for p in paths]
    if not frames:
        return 0
    if width and frames[0].width != width:
        h = round(width * frames[0].height / frames[0].width)
        frames = [f.resize((width, h), Image.LANCZOS) for f in frames]
    if annotate is not None:
        frames = [annotate(i, im) for i, im in enumerate(frames)]
    if pingpong and len(frames) > 2:
        frames = frames + frames[-2:0:-1]

    pal_frames = [f.convert("P", palette=Image.ADAPTIVE, colors=colors)
                  for f in frames]
    save_kwargs = dict(save_all=True, append_images=pal_frames[1:],
                       duration=duration, disposal=2, optimize=False)
    if loop is not None:
        save_kwargs["loop"] = loop
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    pal_frames[0].save(out_path, **save_kwargs)
    if log:
        log(f"[信息] GIF 已写入 {out_path} ({len(pal_frames)} 帧)")
    return len(pal_frames)


# ==========================================================================
# 图例 / 信息条 (PIL)
# ==========================================================================
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def load_font(size: int):
    for cand in _FONT_CANDIDATES:
        try:
            if os.path.isfile(cand):
                return ImageFont.truetype(cand, int(size))
        except Exception:  # noqa: BLE001
            continue
    try:
        return ImageFont.load_default()
    except Exception:  # noqa: BLE001
        return None


def _text_color_for(hex_color: str) -> str:
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        return "#111827" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#f9fafb"
    except Exception:  # noqa: BLE001
        return "#f9fafb"


def make_legend_strip(width: int, bg: str = "white",
                      entries: list[tuple[str, str]] | None = None,
                      gradient: tuple[float, float, str] | None = None,
                      title: str | None = None) -> Image.Image | None:
    """生成底部图例条。

    entries:  [(元素符号, 颜色)] 实心球 + 文本
    gradient: (vmin, vmax, 单位说明) 绘制蓝-白-红色带
    """
    entries = entries or []
    if not entries and gradient is None:
        return None
    is_dark = str(bg).lower() in ("black", "#000", "#000000")
    text_col = "#e5e7eb" if is_dark else "#1f2937"
    strip_bg = "#111827" if is_dark else "white"
    h = max(34, int(round(width * 0.052)))
    img = Image.new("RGB", (width, h), strip_bg)
    draw = ImageDraw.Draw(img)
    font = load_font(max(12, int(round(width * 0.017))))

    x = max(12, int(round(width * 0.02)))
    cy = h // 2

    if title:
        bbox = draw.textbbox((0, 0), title, font=font)
        th = bbox[3] - bbox[1]
        draw.text((x, cy - th / 2 - bbox[1]), title, fill=text_col, font=font)
        x += (bbox[2] - bbox[0]) + int(round(width * 0.025))

    if entries:
        r = max(6, int(round(h * 0.22)))
        for label, color in entries:
            draw.ellipse([x, cy - r, x + 2 * r, cy + r], fill=color,
                         outline="#9ca3af", width=1)
            x += 2 * r + 6
            bbox = draw.textbbox((0, 0), label, font=font)
            th = bbox[3] - bbox[1]
            draw.text((x, cy - th / 2 - bbox[1]), label, fill=text_col, font=font)
            x += (bbox[2] - bbox[0]) + int(round(width * 0.02))

    if gradient is not None:
        vmin, vmax, unit = gradient
        bar_w = max(120, int(round(width * 0.26)))
        bar_h = max(10, int(round(h * 0.3)))
        bar_x = width - bar_w - max(12, int(round(width * 0.02)))
        bar_y = cy - bar_h // 2
        neg, mid, pos = CHARGE_NEG, CHARGE_MID, CHARGE_POS
        for i in range(bar_w):
            t = i / max(1, bar_w - 1)
            if t < 0.5:
                col = _lerp(neg, mid, t / 0.5)
            else:
                col = _lerp(mid, pos, (t - 0.5) / 0.5)
            draw.line([bar_x + i, bar_y, bar_x + i, bar_y + bar_h], fill=col)
        draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
                       outline="#9ca3af")
        lo_text = f"{vmin:.2f}"
        hi_text = f"{vmax:.2f}"
        bbox = draw.textbbox((0, 0), lo_text, font=font)
        draw.text((bar_x - (bbox[2] - bbox[0]) - 6, cy - (bbox[3] - bbox[1]) / 2 - bbox[1]),
                  lo_text, fill=text_col, font=font)
        draw.text((bar_x + bar_w + 6, cy - (bbox[3] - bbox[1]) / 2 - bbox[1]),
                  hi_text, fill=text_col, font=font)
        if unit:
            bbox = draw.textbbox((0, 0), unit, font=font)
            draw.text((bar_x - (bbox[2] - bbox[0]) - 6,
                       bar_y - (bbox[3] - bbox[1]) - 4),
                      unit, fill=text_col, font=font)
    return img


def decorate_with_legend(image: Image.Image, data: dict[str, Any],
                         color_mode: str, bg: str = "white") -> Image.Image:
    """在单帧图片底部叠加元素图例 / 电荷色带。"""
    symbols = []
    for a in data["atoms"]:
        if a["symbol"] not in symbols:
            symbols.append(a["symbol"])
    entries = [(s, element_color(s)) for s in symbols]
    gradient = None
    if color_mode == "charge":
        unit = "Δq (e)" if data["has_delta"] else "q (e)"
        gradient = (data["value_min"], data["value_max"], unit)
        title = "Bader 电荷"
    else:
        title = None
    strip = make_legend_strip(image.width, bg=bg, entries=entries,
                              gradient=gradient, title=title)
    if strip is None:
        return image
    out = Image.new("RGB", (image.width, image.height + strip.height),
                    "#111827" if str(bg).lower() in ("black", "#000", "#000000") else "white")
    out.paste(image, (0, 0))
    out.paste(strip, (0, image.height))
    return out


# ==========================================================================
# 高层 API
# ==========================================================================
def render_gif(data: dict[str, Any], out_path: str | os.PathLike[str],
               label_mode: str = "charge", color_mode: str = "element",
               view: str = "front", rot_axis: str = "c", rot_total: float = 360.0,
               frames: int = 60, fps: float = 20.0, width: int = 600,
               height: int | None = None, style: str = "ballstick",
               radius_scale: float = 0.6, uniform_radius: float | None = None,
               show_cell: bool = True, cell_color: str = "#888888",
               bg: str = "white", zoom: float = 1.25,
               pingpong: bool = False, loop: int | None = 0, colors: int = 256,
               scale: float = 1.0, gif_width: int | None = None,
               show_labels: bool = True, label_size: int = 12,
               with_legend: bool = True, browser: str | None = None,
               show_browser: bool = False,
               progress: Callable[[int, int], None] | None = None,
               cancel: Callable[[], bool] | None = None,
               log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """完整流程: 结构 -> 逐帧截图 -> 旋转 GIF。返回结果摘要。"""
    if height is None:
        height = width
    geom = build_geometry(data, label_mode=label_mode, color_mode=color_mode,
                          radius_scale=radius_scale, uniform_radius=uniform_radius,
                          show_labels=show_labels)
    cfg = {
        "style": style, "show_cell": show_cell, "cell_color": cell_color,
        "bg": bg, "zoom": zoom, "label_size": label_size,
        "view": view, "rot_axis": rot_axis, "rot_total": rot_total,
        "frames": frames, "width": width, "height": height, "scale": scale,
        "browser": browser, "show_browser": show_browser, "pan": (0.0, 0.0),
    }
    tmp = Path(tempfile.mkdtemp(prefix="bader-frames-"))
    try:
        paths = render_pngs(data, geom, cfg, tmp, progress=progress,
                            cancel=cancel, log=log)
        if not paths:
            raise RuntimeError("没有生成任何帧")
        duration = max(1, int(round(1000.0 / max(fps, 0.1))))
        annotate = None
        if with_legend:
            annotate = lambda i, im: decorate_with_legend(im, data, color_mode, bg)  # noqa: E731
        target_w = gif_width or width
        n = build_gif(paths, out_path, duration=duration, loop=loop,
                      colors=colors, pingpong=pingpong, width=target_w,
                      annotate=annotate, log=log)
        size = os.path.getsize(out_path) / 1e6 if os.path.exists(out_path) else 0.0
        return {"ok": True, "path": str(out_path), "frames": n,
                "fps": fps, "size_mb": size}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def render_single_png(data: dict[str, Any], out_path: str | os.PathLike[str],
                      **kwargs) -> str:
    """渲染单帧 PNG (不旋转), 便于快速检查。"""
    kw = dict(kwargs)
    kw["frames"] = 1
    kw["rot_total"] = 0.0
    with_legend = kw.pop("with_legend", True)
    res = render_gif(data, out_path, with_legend=False, **kw)
    if with_legend:
        im = Image.open(out_path).convert("RGB")
        color_mode = kwargs.get("color_mode", "element")
        bg = kwargs.get("bg", "white")
        decorate_with_legend(im, data, color_mode, bg).save(out_path)
    return res["path"]


# ==========================================================================
# 独立 HTML 导出 (与 work-list-0809 /bader 结果页一致)
# ==========================================================================
HTML_NAME = "bader_charge_analysis.html"
GROUP_NAMES = ["A部分", "B部分", "C部分", "D部分", "E部分", "F部分"]

# 独立导出的补充样式 ( “Bader 电荷定义与判据” 部分的标题 / 列表 / 代码样式 )
_STANDALONE_EXTRA_CSS = """
/* —— 导出结果页: “Bader 电荷定义与判据” 补充说明 —— */
.bc-info-box .bc-info-heading {
    margin: 16px 0 6px;
    color: var(--text, #eef2f3);
    font-size: 0.82rem;
    font-weight: 700;
}
.bc-info-box .bc-info-heading:first-of-type { margin-top: 4px; }
.bc-info-box p { margin: 6px 0; line-height: 1.8; }
.bc-info-box ul { margin: 4px 0 8px; padding-left: 20px; }
.bc-info-box li { margin: 4px 0; line-height: 1.75; font-size: 0.74rem; }
.bc-info-box code {
    padding: 1px 5px;
    background: rgba(127, 127, 127, 0.18);
    border-radius: 3px;
    font-family: Consolas, "Courier New", monospace;
    font-size: 0.72rem;
    color: var(--text, #eef2f3);
}
.bc-criteria-table { max-width: 560px; margin: 6px 0 10px; }
.bc-criteria-table th, .bc-criteria-table td { font-size: 0.72rem; }
"""


def _escape_html(value: Any) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))


def _build_table_rows(charge_data: list[dict[str, Any]], group_names: list[str],
                      has_delta: bool) -> str:
    rows = []
    for atom in charge_data:
        if has_delta:
            delta = float(atom["delta_charge"])
            delta_class = "bc-charge-positive" if delta > 0 else "bc-charge-negative"
            delta_text = f"{delta:+.6f}"
            zval_text = f"{float(atom['zval']):.2f}" if atom.get("zval") is not None else "—"
        else:
            delta_class = ""
            delta_text = "—"
            zval_text = "—"
        group_checkboxes = "".join(
            f'<label class="bc-group-checkbox"><input type="checkbox" '
            f'data-group-name="{_escape_html(g)}" '
            f'data-atom-index="{atom["index"]}"><span>{_escape_html(g)}</span></label>'
            for g in group_names)
        rows.append("".join([
            f'<tr class="bc-atom-row" data-index="{atom["index"]}" '
            f'data-element="{_escape_html(atom["atom"])}" data-z="{atom["loc_z"]}">',
            f'<td>{atom["index"]}</td>',
            f'<td>{_escape_html(atom["atom"])}</td>',
            f'<td>{float(atom["loc_x"]):.6f}</td>',
            f'<td>{float(atom["loc_y"]):.6f}</td>',
            f'<td>{float(atom["loc_z"]):.6f}</td>',
            f'<td>{zval_text}</td>',
            f'<td>{float(atom["charge"]):.6f}</td>',
            f'<td class="{delta_class}">{delta_text}</td>',
            f'<td><div class="bc-group-checkboxes">{group_checkboxes}</div></td>',
            "</tr>",
        ]))
    return "\n".join(rows)


def _build_standalone_body(result: dict[str, Any]) -> str:
    has_delta = bool(result.get("has_delta", True))
    group_names = result.get("group_names", GROUP_NAMES)
    table_rows = _build_table_rows(result["charge_data"], group_names, has_delta)
    warning_block = ""
    for w in result.get("warnings", []):
        warning_block += f'<div class="bc-warning-banner">{_escape_html(w)}</div>'
    if not has_delta:
        warning_block += ('<div class="bc-warning-banner">未使用 POTCAR, '
                          '明细与分组中所示数值为原始 Bader 电荷 q_Bader, 不含 Δq。</div>')
    value_label = "Bader 电荷差（Δq）" if has_delta else "Bader 电荷（q）"
    return f"""
    <div class="bc-container">
        <div class="bc-header">
            <div>
                <h1>Bader 电荷分析结果</h1>
                <div class="bc-meta">处理时间：{_escape_html(result['generated_at'])}</div>
                <div class="bc-meta">数据来源：{_escape_html(result['job_id'])}</div>
            </div>
            <div class="bc-download-actions">
                <span class="bc-standalone-badge">独立 HTML 文件</span>
            </div>
        </div>
        {warning_block}
        <div class="bc-content">
            <div class="bc-summary-grid">
                <div class="bc-summary-card"><div class="bc-summary-label">原子总数</div><div class="bc-summary-value">{result['atom_count']}</div></div>
                <div class="bc-summary-card"><div class="bc-summary-label">总 Bader 电荷</div><div class="bc-summary-value">{result['total_charge']:.6f}</div></div>
                <div class="bc-summary-card"><div class="bc-summary-label">结构文件</div><div class="bc-summary-file">{_escape_html(Path(result['poscar_path']).name)}</div></div>
                <div class="bc-summary-card"><div class="bc-summary-label">赝势文件</div><div class="bc-summary-file">{_escape_html(Path(result['potcar_path']).name) if result.get('potcar_path') else '(未使用)'}</div></div>
                <div class="bc-summary-card"><div class="bc-summary-label">电荷文件</div><div class="bc-summary-file">{_escape_html(Path(result['acf_path']).name)}</div></div>
            </div>

            <div class="bc-section">
                <h2 class="bc-section-title">结构可视化</h2>
                <div class="bc-section-subtitle">三幅视图基于同一结构数据分别展示原子序号、元素类型与 Bader 电荷差，视角可独立调整。</div>
                <div class="bc-structure-viewers">
                    <div class="bc-viewer-panel" id="viewer-panel-1">
                        <div class="bc-viewer-header"><span>原子序号</span><button class="bc-fullscreen-btn" type="button" onclick="toggleFullscreen('viewer-panel-1')">全屏</button></div>
                        <div class="bc-viewer-container" id="viewer-index"></div>
                    </div>
                    <div class="bc-viewer-panel" id="viewer-panel-2">
                        <div class="bc-viewer-header"><span>元素类型</span><button class="bc-fullscreen-btn" type="button" onclick="toggleFullscreen('viewer-panel-2')">全屏</button></div>
                        <div class="bc-viewer-container" id="viewer-type"></div>
                    </div>
                    <div class="bc-viewer-panel" id="viewer-panel-3">
                        <div class="bc-viewer-header"><span>{_escape_html(value_label)}</span><button class="bc-fullscreen-btn" type="button" onclick="toggleFullscreen('viewer-panel-3')">全屏</button></div>
                        <div class="bc-viewer-container" id="viewer-charge"></div>
                    </div>
                </div>
                <div class="bc-legend-box">
                    <div class="bc-legend-title">元素颜色图例</div>
                    <div class="bc-legend-items" id="legend-items"></div>
                    <div class="bc-legend-note">说明：结构模型与图例使用同一套元素颜色；电荷差视图中红色标签表示较高的 Δq，蓝色标签表示较低的 Δq。</div>
                </div>
            </div>

            <div class="bc-section">
                <details class="bc-collapsible-section" open>
                    <summary class="bc-collapsible-summary">原子电荷明细</summary>
                    <div class="bc-table-wrap bc-collapsible-body">
                        <table class="bc-data-table">
                            <thead>
                                <tr>
                                    <th>序号</th>
                                    <th>元素</th>
                                    <th>X (Å)</th>
                                    <th>Y (Å)</th>
                                    <th>Z (Å)</th>
                                    <th>ZVAL</th>
                                    <th>Bader 电荷 (e)</th>
                                    <th>Δq (e)</th>
                                    <th>分组</th>
                                </tr>
                            </thead>
                            <tbody>
                                {table_rows}
                            </tbody>
                        </table>
                    </div>
                </details>
            </div>

            <div class="bc-section">
                <h2 class="bc-section-title">分组统计</h2>
                <div class="bc-grouping-panel">
                    <div class="bc-grouping-controls">
                        <label class="bc-control-block">
                            <span>分组方式</span>
                            <select id="grouping-mode">
                                <option value="manual">按索引分组</option>
                                <option value="element">按元素分组</option>
                                <option value="z-threshold">按 Z 阈值分组</option>
                            </select>
                        </label>
                        <label class="bc-control-block" id="z-threshold-block" hidden>
                            <span>Z 阈值</span>
                            <input id="z-threshold-input" type="number" step="any" placeholder="请输入 Z 阈值">
                        </label>
                    </div>
                    <div id="group-selection-container" class="bc-selection-container"></div>
                    <div class="bc-summary-grid bc-grouping-summary">
                        <div class="bc-summary-card"><div class="bc-summary-label">已选分组数</div><div class="bc-summary-value" id="selected-group-count">0</div></div>
                        <div class="bc-summary-card"><div class="bc-summary-label">命中原子数</div><div class="bc-summary-value" id="matched-atom-count">0</div></div>
                        <div class="bc-summary-card"><div class="bc-summary-label">命中原子 Δq 总和</div><div class="bc-summary-value" id="matched-delta-sum">0.000000</div></div>
                    </div>
                    <div class="bc-table-wrap">
                        <table class="bc-data-table">
                            <thead>
                                <tr>
                                    <th>分组</th>
                                    <th>原子数</th>
                                    <th>Δq 总和</th>
                                </tr>
                            </thead>
                            <tbody id="group-summary-body"></tbody>
                        </table>
                    </div>
                </div>
            </div>

            <div class="bc-section">
                <div class="bc-info-box">
                    <p class="bc-formula-title"><strong>Bader 电荷定义与判据</strong></p>
                    <p class="bc-formula-line">Δq = q<sub>Bader</sub> − ZVAL</p>

                    <p class="bc-info-heading">一、基本定义</p>
                    <ul>
                        <li><strong>q<sub>Bader</sub></strong>：Bader 分割后该原子“盆地”内积分的电子数，取自 <code>ACF.dat</code> 的 CHARGE 列。</li>
                        <li><strong>ZVAL</strong>：<code>POTCAR</code> 中该元素赝势的价电子数（valence electrons）。</li>
                        <li><strong>Δq</strong>：相对中性价电子数的偏移量，<span class="bc-charge-positive">Δq &gt; 0</span> 表示该原子区域电子相对富集，<span class="bc-charge-negative">Δq &lt; 0</span> 表示电子相对亏损。</li>
                    </ul>

                    <p class="bc-info-heading">二、方法背景</p>
                    <p>Bader 分析（Quantum Theory of Atoms in Molecules，QTAIM）是一种<strong>实空间电子密度拓扑分析</strong>：以电子密度 ρ(r) 的<strong>零通量面</strong>（∇ρ·n = 0）为界面，把空间划分为互不重叠、以原子核为中心的原子盆地，每个盆地内的电子积分即为该原子的 Bader 电荷。</p>
                    <ul>
                        <li>只依赖体系的三维电荷密度，<strong>不依赖波函数基组</strong>，因此对基组选择不敏感（区别于 Mulliken / Löwdin 等基于基组的布居分析）；但要求足够细的 FFT 网格与正确的芯区处理。</li>
                        <li>与 DDEC、CM5、Hirshfeld 等其它电荷分配方法并不等价，不同方法之间不宜直接混用数值；应保持方法一致后再比较。</li>
                    </ul>

                    <p class="bc-info-heading">三、判据与经验参考</p>
                    <div class="bc-table-wrap">
                        <table class="bc-data-table bc-criteria-table">
                            <thead><tr><th>|Δq| (e)</th><th>常见解读</th></tr></thead>
                            <tbody>
                                <tr><td>≲ 0.1</td><td>近似中性，电子转移很弱</td></tr>
                                <tr><td>0.1 – 0.5</td><td>轻度电子转移，多为极性共价 / 配位作用</td></tr>
                                <tr><td>0.5 – 1.5</td><td>显著电子转移，离子性明显</td></tr>
                                <tr><td>&gt; 1.5</td><td>强离子性；需结合体系与方法复核</td></tr>
                            </tbody>
                        </table>
                    </div>
                    <p>上述区间仅为一般经验参考，并非严格判据。Δq 反映的是<strong>价电子的重新分布</strong>，<strong>不等同于形式氧化态</strong>；对于金属性或电子离域较强的体系（如过渡金属 Mo 等），单个原子的 Bader 电荷应谨慎解读，通常比较同类原子之间的<strong>相对趋势</strong>比绝对值更有意义。</p>

                    <p class="bc-info-heading">四、结果可靠性自检</p>
                    <ul>
                        <li><strong>总电荷守恒</strong>：全部原子 q<sub>Bader</sub> 之和应接近体系价电子总数（VASP 输出中的 NELECT）。若偏差明显，说明电荷密度网格或 Bader 切分存在问题。</li>
                        <li><strong>真空区检查</strong>：<code>ACF.dat</code> 中 VACUUM CHARGE 应接近 0、VACUUM VOLUME 应接近设定的真空体积；异常通常提示分割失败或真空层不足。</li>
                        <li><strong>网格与芯区</strong>：Bader 电荷依赖 FFT 网格密度（NGXF / NGYF / NGZF）以及是否包含芯电荷（AECCAR0 芯密度 + AECCAR2 价密度，或用 <code>-c</code> 关闭芯电荷）。不同设置会给出不同的数值，比较前应保持设置一致并做收敛测试。</li>
                        <li><strong>周期性与表面体系</strong>：表面 / 吸附体系需保证足够真空层；跨周期的 Bader 盆地若被截断会影响结果。</li>
                    </ul>

                    <p class="bc-info-heading">五、局限性与使用建议</p>
                    <ul>
                        <li>绝对电荷值具有<strong>方法依赖性</strong>，不宜与实验“绝对电荷”直接比较；更适合用于同体系、同方法下的相对比较与趋势分析。</li>
                        <li>对强关联、阴离子、高氧化态体系，芯电子重分布会影响划分结果。</li>
                        <li>Bader 电荷不直接给出自旋 / 磁矩、键级或带中心等信息，通常需与磁矩、COHP / COOP、态密度、差分电荷密度等联合分析。</li>
                    </ul>
                </div>
            </div>
        </div>
        <div class="bc-footer">VASP Bader 电荷分析结果页 · 本地导出</div>
    </div>
    """


def _load_asset_text(path: str | os.PathLike[str] | None) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8", errors="ignore")


def export_standalone_html(data: dict[str, Any],
                           out_path: str | os.PathLike[str],
                           group_names: list[str] | None = None,
                           generated_at: str | None = None,
                           css_path: str | os.PathLike[str] | None = None,
                           js_path: str | os.PathLike[str] | None = None) -> str:
    """导出与 work-list-0809 `/bader` 结果页一致的独立 HTML 文件。

    文件自带内联 CSS、3Dmol.js 与 bader.js, 不依赖任何外部资源, 可直接打开。
    """
    from datetime import datetime

    group_names = list(group_names or GROUP_NAMES)
    charge_data = [{
        "index": a["index"],
        "atom": a["symbol"],
        "loc_x": a["x"],
        "loc_y": a["y"],
        "loc_z": a["z"],
        "zval": a.get("zval"),
        "charge": a["charge"],
        "delta_charge": a.get("delta_charge", a["charge"]),
    } for a in data["atoms"]]

    result = {
        "job_id": Path(data["acf_path"]).parent.name or "bader",
        "generated_at": generated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "poscar_path": data["poscar_path"],
        "acf_path": data["acf_path"],
        "potcar_path": data.get("potcar_path") or "",
        "atom_count": data["atom_count"],
        "total_charge": data["total_charge"],
        "charge_data": charge_data,
        "lattice_vectors": data["lattice"],
        "group_names": group_names,
        "has_delta": bool(data["has_delta"]),
        "warnings": list(data.get("warnings", [])),
    }

    css = _load_asset_text(css_path or (HERE / "assets" / "bader.css"))
    bader_js = _load_asset_text(js_path or (HERE / "assets" / "bader.js"))
    threedmol_js = ensure_3dmol_js()
    body = _build_standalone_body(result)
    data_json = json.dumps(result, ensure_ascii=False)
    groups_json = json.dumps(group_names, ensure_ascii=False)

    if not css.strip():
        css = (
            "body{background:#0c1114;color:#d9e0e3;font-family:'Microsoft YaHei UI',"
            "Segoe UI,sans-serif;margin:0}.bc-container{max-width:1440px;margin:14px auto;"
            "padding:0 18px 24px}.bc-viewer-container{height:360px;background:#f5f7fa;"
            "border-radius:6px}.bc-structure-viewers{display:grid;grid-template-columns:1fr "
            "1fr 1fr;gap:14px}.bc-data-table{width:100%;border-collapse:collapse}"
            ".bc-data-table th,.bc-data-table td{border:1px solid #30373c;padding:6px 8px;"
            "font-size:12px}.bc-charge-positive{color:#fb7185}.bc-charge-negative{color:#67b7dc}"
        )

    css = css + _STANDALONE_EXTRA_CSS

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bader Charge Analysis</title>
    <style>{css}</style>
</head>
<body class="bc-result-page">
    {body}
    <script>{threedmol_js}</script>
    <script>
        window.BADER_RESULT_DATA = {data_json};
        window.BADER_GROUP_NAMES = {groups_json};
        window.BADER_JOB_ID = {json.dumps(result['job_id'], ensure_ascii=False)};
        window.BADER_STANDALONE = true;
    </script>
    <script>{bader_js}</script>
</body>
</html>
"""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return str(out)
