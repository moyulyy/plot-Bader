<div align="center">

<img src="assets/app.png" width="96" alt="logo">

# Bader 电荷可视化工作台

**ACF.dat + POSCAR &#8594; 交互式 3D 结构 · 旋转 GIF · 独立 HTML 报告**

把 VASP / Bader 的电荷分析结果，一键变成可交互、可预览、可分享的可视化成果。

[![Release](https://img.shields.io/github/v/release/moyulyy/plot-Bader?logo=github&color=2ea44f&label=Release)](https://github.com/moyulyy/plot-Bader/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/moyulyy/plot-Bader/total?logo=github&color=0366d6)](https://github.com/moyulyy/plot-Bader/releases)
[![License](https://img.shields.io/github/license/moyulyy/plot-Bader?color=blue)](LICENSE)
[![Stars](https://img.shields.io/github/stars/moyulyy/plot-Bader?logo=github&color=yellow)](https://github.com/moyulyy/plot-Bader/stargazers)

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/GUI-PySide6-41CD52?logo=qt&logoColor=white)
![3Dmol.js](https://img.shields.io/badge/3D-3Dmol.js-2dd4bf)
![Playwright](https://img.shields.io/badge/Render-Playwright-2EAD33?logo=playwright&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)

[⬇️ 下载](#-下载便携版) &nbsp;·&nbsp; [✨ 功能](#-功能亮点) &nbsp;·&nbsp; [🖼 预览](#-界面预览) &nbsp;·&nbsp; [🚀 快速开始](#-快速开始) &nbsp;·&nbsp; [⌨️ 命令行](#-命令行) &nbsp;·&nbsp; [📄 导出](#-导出结果页) &nbsp;·&nbsp; [📦 打包](#-打包为-exe) &nbsp;·&nbsp; [❓ FAQ](#-常见问题)

</div>

---

## 📖 这是什么？

一个**本地、离线、纯图形界面**的 Bader 电荷分析后处理小工具。给它一个包含 VASP / Bader
输出的目录，它会自动解析并生成三种可视化成果：

```text
 ACF.dat ─┐
 POSCAR  ─┼─►  解析 & 按原子序号匹配  ─►  3Dmol.js 交互式 3D  ─┬─►  🎞 旋转 GIF
 POTCAR  ─┘        (可选 Δq = q − ZVAL)                        ├─►  🖼 单帧 PNG
                                                               └─►  📄 独立 HTML 报告
```

- **不联网、不上传**：所有计算与渲染均在本机完成；
- **开箱即用**：提供免安装的 Windows 便携版；源码运行也只需 4 个依赖；
- **结果可分享**：导出的 HTML 报告完全自包含，双击即可打开。

---

## ⬇️ 下载（便携版）

**无需安装 Python**，下载解压即用：

<div align="center">

| 平台 | 文件 | 大小 |
| :--: | --- | :--: |
| **Windows 10 / 11 (x64)** | [**`BaderChargeViewer-1.0.0-win64-portable.zip`**](https://github.com/moyulyy/plot-Bader/releases/latest) | ~264 MB |

<a href="https://github.com/moyulyy/plot-Bader/releases/latest"><b>➡️ 前往 Releases 下载最新版本</b></a>

</div>

**三步上手：**

1. 下载并解压 `BaderChargeViewer-<版本>-win64-portable.zip`；
2. 双击目录中的 **`BaderChargeViewer.exe`**；
3. 左侧选择包含 `POSCAR` / `CONTCAR`、`ACF.dat`（可选 `POTCAR`）的目录。

> 📁 内置 `samples/` 示例数据可直接试用；输出默认写入程序目录下的 `outputs/`。
> 🎞 生成 GIF 需要系统自带 **Edge（Win10/11 默认）** 或 Chrome；解析与 3D 交互无需额外依赖。

---

## ✨ 功能亮点

|  | 模块 | 能力 |
| :--: | --- | --- |
| 🧪 | **数据解析** | 读取 `ACF.dat` + `POSCAR/CONTCAR`；可选 `POTCAR` 自动计算 `Δq = q_Bader − ZVAL`，按原子序号匹配 |
| 🧊 | **交互式 3D** | 内嵌 3Dmol.js：拖动旋转 · 滚轮缩放 · 双击复位 · 可显示晶胞框；正交相机，旋转时尺度恒定 |
| 🏷 | **三种标注** | 原子序号 / 元素类型 / Bader 电荷差 `Δq` |
| 🎨 | **两种着色** | 按元素（Jmol 配色）或按电荷差（以 0 为中心的蓝‑白‑红发散色带） |
| 🎞 | **旋转 GIF** | 绕晶胞 `a/b/c` 轴或屏幕轴匀速旋转，首尾无缝循环；支持乒乓、图例、超采样 |
| 📊 | **数据表** | 逐原子明细（`ZVAL` / `q` / `Δq`），`Δq` 红蓝染色，一键导出 CSV |
| 📄 | **独立 HTML** | 导出**完全自包含**的结果页：三视图 + 图例 + 明细 + 分组统计 + 判据说明 |
| 🖼 | **单帧 PNG** | 快速导出一张带图例的静态结构图 |

---

## 🖼 界面预览

<div align="center">

**① 结构可视化** — 基准视角居中，交互查看，右侧实时调参

<img src="docs/ui_structure.png" width="880">

</div>

<div align="center">

<table>
<tr>
<td width="50%" align="center"><b>② 原子数据表</b><br><img src="docs/ui_table.png" width="430"></td>
<td width="50%" align="center"><b>③ GIF 生成</b><br><img src="docs/ui_gif.png" width="430"></td>
</tr>
</table>

**rotating GIF · 旋转效果**

<img src="docs/demo.gif" width="440">

**standalone HTML · 导出的独立结果页**

<img src="docs/standalone_html.png" width="880">

</div>

---

## 🚀 快速开始

<details open>
<summary><b>方式 A · 便携版（推荐，无需 Python）</b></summary>

见上方 [⬇️ 下载](#-下载便携版)。解压后双击 `BaderChargeViewer.exe` 即可。

</details>

<details>
<summary><b>方式 B · 源码运行（需要 Python 3.10+，推荐 3.11）</b></summary>

```bat
:: 1) 安装依赖
pip install -r requirements.txt
::    或者双击： install_deps.bat

:: 2) 启动图形界面（无控制台）
run_gui.bat
::    等价于： python bader_gui.py

:: 3) 命令行快速生成
run_cli.bat
::    等价于：
python bader_to_gif.py ^
  --poscar samples\POSCAR --acf samples\ACF.dat ^
  --out outputs\bader.gif --html outputs\bader.html
```

</details>

---

## 🖥 界面导览

界面为 iOS / macOS 风格无边框窗口，共 5 个页面；右上角常驻 **「导出 HTML」「生成 GIF」**。

| 页面 | 说明 |
| :--: | --- |
| **① 结构可视化** | 顶部 **基准视角**（正视 / 后视 / 俯视 / 仰视 / 右视 / 左视，基于晶胞矢量）；左侧交互 3D；右侧输入目录 + 显示设置（标注 / 着色 / 样式 / 半径系数 / 缩放 / 标签字号 / 背景 / 晶胞框）+ 统计信息 |
| **② 原子数据表** | 逐原子 `序号 / 元素 / X / Y / Z / ZVAL / Bader 电荷 / Δq`，支持 **导出 CSV** 与 **导出 HTML** |
| **③ GIF 生成** | 左：视角与旋转、画布与输出、参数说明；右：摘要与操作（生成 GIF / 导出 PNG / 导出 HTML / 打开输出目录） |
| **④ GIF 预览** | 滚轮缩放、拖动平移、双击复位，像看图工具一样预览 |
| **⑤ 日志** | 完整运行日志，便于排查渲染 / 浏览器问题 |

**支持的样式**：球棍模型 · 空间填充 · 棍状 · 线框。

---

## ⌨️ 命令行

```bat
python bader_to_gif.py [选项]
```

| 选项 | 说明 | 默认 |
| --- | --- | --- |
| `--poscar` / `--acf` / `--potcar` | 输入文件 | `POSCAR` / `ACF.dat` / 同目录自动查找 |
| `-o, --out` | 输出 GIF（`.png` 则输出单帧） | `outputs/bader.gif` |
| `--html` | 额外导出自包含的独立 HTML 结果页 | — |
| `--label` | `charge` / `element` / `index` / `none` | `charge` |
| `--color` | `element` / `charge` | `element` |
| `--style` | `ballstick` / `sphere` / `stick` / `line` | `ballstick` |
| `--view` | `front` / `back` / `top` / `bottom` / `right` / `left` | `front` |
| `--rot-axis` | `a` / `b` / `c` / `screen-v` / `screen-h` | `c` |
| `--rot-angle` | 整段旋转总角度（`360` 无缝循环） | `360` |
| `--frames` / `--fps` | 帧数 / 帧率 | `60` / `20` |
| `-w, --width` / `--height` / `--scale` | 分辨率与超采样 | `640` / 同宽 / `1.0` |
| `--pingpong` / `--loop` | 乒乓循环 / 循环次数（`0` 无限，`-1` 不循环） | — / `0` |
| `--no-labels` / `--no-cell` / `--no-legend` | 关闭标签 / 晶胞框 / 底部图例 | — |

---

## 📄 导出结果页

导出的 HTML 是一个**完全自包含**的单文件报告——内联 CSS、3Dmol.js 与交互脚本，
不依赖任何外部资源，可直接双击打开或发送给他人：

<div align="center"><img src="docs/standalone_html.png" width="800"></div>

| 区块 | 内容 |
| --- | --- |
| 🧊 **三幅 3D 视图** | 原子序号 / 元素类型 / Bader 电荷差，各自可独立旋转与全屏 |
| 🎨 **图例** | 元素配色图例 + 电荷发散色带 |
| 📊 **原子明细表** | 逐原子 `X/Y/Z`、`ZVAL`、`q_Bader`、`Δq`，含 A–F 分组勾选框 |
| 📈 **分组统计** | 按索引 / 按元素 / 按 Z 阈值汇总 |
| 📚 **判据说明** | 基本定义、方法背景、经验判据、可靠性自检、局限性与使用建议 |

**导出方式**：界面右上角 / 数据表底部 / GIF 页「操作」卡片，或命令行 `--html outputs\bader.html`。

---

## 🔬 数据约定与判据

- 结构坐标统一取 **`ACF.dat`** 的笛卡尔坐标，`POSCAR` 只提供晶胞矢量与元素种类/数量；
- `Δq = q_Bader − ZVAL`：`Δq > 0` 表示电子富集（红），`Δq < 0` 表示电子亏损（蓝）；
- 未提供或无法解析 `POTCAR` 时，自动降级显示原始 Bader 电荷 `q_Bader`。

| \|Δq\| (e) | 常见解读 |
| :--: | --- |
| ≲ 0.1 | 近似中性，电子转移很弱 |
| 0.1 – 0.5 | 轻度电子转移（极性共价 / 配位） |
| 0.5 – 1.5 | 显著电子转移，离子性明显 |
| > 1.5 | 强离子性，需结合体系与方法复核 |

> ⚠️ `Δq` 反映价电子重新分布，**不等同于形式氧化态**；金属性 / 离域体系宜比较相对趋势，
> 并建议与磁矩、态密度、差分电荷密度等联合分析。

---

## 📦 打包为 exe

```bat
python build_exe.py
```

产物：

```text
dist/BaderChargeViewer/BaderChargeViewer.exe          # 便携版程序
dist/BaderChargeViewer-1.0.0-win64-portable.zip       # 可分发的压缩包
```

<details>
<summary><b>打包说明</b></summary>

配置见 `BaderChargeViewer.spec`：内嵌 3Dmol.js、`assets/`、`samples/` 与 Playwright
（浏览器内核不打包，运行时调用系统 Edge / Chrome，因此 GIF 渲染无需额外安装）。
文件版本、图标等信息由 `assets/version_info.txt` 与 `assets/app.ico` 提供。

</details>

---

## 🛠 技术栈与依赖

| 组件 | 版本 | 用途 |
| --- | :--: | --- |
| `numpy` | — | 数值与几何（晶胞 / 正交相机 / 四元数）计算 |
| `pillow` | — | GIF 合成、图例绘制、图标生成 |
| `PySide6` | ≥ 6.5 | 图形界面（含 QtWebEngine / Chromium 内核） |
| `playwright` | — | 驱动系统浏览器逐帧渲染（GIF / PNG） |
| `pyinstaller` | — | （可选）打包便携版 exe |

- 运行来源：`bader_gui.py`（界面） · `bader_core.py`（核心） · `bader_to_gif.py`（命令行） · `ui_kit.py`（组件库）；
- 辅助脚本：`make_icon.py`（生成图标） · `make_docs.py`（生成 README 截图） · `build_exe.py`（打包）；
- GIF 渲染需要 Chromium 内核浏览器：**Win10/11 自带 Edge** 即可；若都没有，可执行
  `python -m playwright install chromium`。

---

## 🗂 目录结构

```text
plot_Bader/
├─ bader_gui.py            # 图形界面主程序 (PySide6 + QWebEngineView)
├─ bader_core.py           # 解析 / 3Dmol HTML / 渲染 / GIF / 独立 HTML 核心
├─ bader_to_gif.py         # 命令行工具
├─ ui_kit.py               # iOS 风格 Qt 组件库
├─ make_icon.py            # 生成应用图标
├─ make_docs.py            # 生成 README 截图与示例产物
├─ build_exe.py            # 一键打包便携版 exe + zip
├─ BaderChargeViewer.spec  # PyInstaller 打包配置
├─ 3dmol/                  # 内嵌 3Dmol.js
├─ assets/                 # 图标 + 结果页资源 (bader.css / bader.js)
├─ samples/                # 示例数据 (POSCAR / CONTCAR / ACF.dat)
├─ docs/                   # README 截图
├─ outputs/                # 默认输出目录
├─ test/                   # 完整测试算例
├─ run_gui.bat             # 启动 GUI（无控制台）
├─ run_gui_debug.bat       # 调试启动（保留控制台）
├─ run_cli.bat             # 命令行示例
├─ install_deps.bat        # 安装依赖
├─ requirements.txt
└─ LICENSE
```

---

## ❓ 常见问题

<details>
<summary><b>没有 POTCAR 可以吗？</b></summary>

可以。程序会自动在同目录查找 `POTCAR`；找不到时直接显示原始 Bader 电荷 `q_Bader`，不计算 `Δq`。
出于版权原因，仓库与发行包**不附带 POTCAR**。
</details>

<details>
<summary><b>GIF 生成很慢 / 失败？</b></summary>

耗时由「帧数 × 分辨率」决定，可先减小帧数、宽高或超采样做测试。失败时查看「日志」页，
通常是找不到浏览器：安装 Edge/Chrome，或执行 `python -m playwright install chromium`。
</details>

<details>
<summary><b>3D 视图底部出现细线？</b></summary>

已从三方面处理：主窗口改为**不透明无边框窗口**并让内容铺满窗口（避免未绘制像素透出桌面）；
`canvas` 设为 `display:block`、显式背景色并在底部加同色覆盖条；Qt 侧显式设置页面与控件背景色。
</details>

<details>
<summary><b>支持 Linux / macOS 吗？</b></summary>

核心逻辑跨平台（PySide6 + 3Dmol.js），当前**仅提供 Windows x64 发行包**；其他平台可从源码运行。
</details>

<details>
<summary><b>数据会上传到云端吗？</b></summary>

不会。程序完全在本地运行，除启动系统浏览器做离线渲染外不联网。
</details>

---

## 🗺 Roadmap

- [ ] 支持导出 MP4 / APNG，提升 GIF 画质
- [ ] 支持多帧轨迹（XDATCAR）与动画自旋
- [ ] 自定义颜色映射与色标范围
- [ ] Linux / macOS 发行包

---

## 📜 License

本项目基于 [MIT License](LICENSE) 开源。

<div align="center">

如果这个项目对你有帮助，欢迎 ⭐ **Star** 支持一下～

</div>
