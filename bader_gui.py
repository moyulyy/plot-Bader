#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Bader 电荷可视化工作台 (PySide6, iOS / macOS 风格)

读取 ACF.dat + POSCAR (可选 POTCAR 计算电荷差 Δq), 提供:

    * 内嵌 3Dmol.js 交互 3D 窗口, 拖动旋转 / 滚轮缩放
    * 三种标注: 原子序号 / 元素类型 / Bader 电荷差 Δq
    * 两种着色: 按元素 (VESTA/Jmol 配色) / 按电荷差 (蓝-白-红)
    * 六个基于晶胞矢量的标准视角
    * 绕晶胞 a/b/c 轴匀速旋转, 生成旋转 GIF (Playwright + 3Dmol.js)

运行:
    D:\\miniconda3\\envs\\chem_env\\python.exe bader_gui.py
    或双击 run_gui.bat
"""

from __future__ import annotations

import os
import queue
import shutil
import sys
import tempfile
import threading
import traceback
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# QWebEngine 需要在使用前导入
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
except Exception as _exc:  # noqa: BLE001
    print("无法导入 QtWebEngineWidgets:", _exc, file=sys.stderr)
    raise

from PIL import Image
from PySide6.QtCore import (QEvent, QPointF, QRectF, QSize, Qt, QTimer, QUrl,
                            Signal)
from PySide6.QtGui import (QColor, QIcon, QMovie, QPainter, QPalette, QPixmap)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDialog,
                               QDoubleSpinBox, QFileDialog, QFrame,
                               QGraphicsDropShadowEffect, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton,
                               QScrollArea, QSizePolicy, QSpinBox,
                               QStackedWidget, QStyle, QStyleOption,
                               QTableWidget, QTableWidgetItem,
                               QAbstractItemView, QHeaderView, QVBoxLayout,
                               QWidget)

import bader_core as core
from ui_kit import (DARK, LIGHT, THEME, Card, ComboBox, SegmentedControl,
                    SliderField, Switch, apply_theme, field_label, hint_label)

def _app_dir() -> Path:
    """程序所在目录: 打包后为 exe 所在目录, 源码运行时为项目根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return HERE


APP_DIR = _app_dir()
DEFAULT_OUT_DIR = APP_DIR / "outputs"


def _queue_writer(q):
    class _W:
        def write(self, s):
            if s:
                q.put(("log", s.rstrip("\n")))

        def flush(self):
            pass
    return _W()


# ==========================================================================
# 进度弹窗 (无边框, 非模态)
# ==========================================================================
class ProgressDialog(QDialog):
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint
                            | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(False)
        self.setFixedWidth(400)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        frame = QFrame()
        frame.setObjectName("Window")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 100))
        frame.setGraphicsEffect(shadow)
        outer.addWidget(frame)
        root = QVBoxLayout(frame)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)
        self.lbl_title = QLabel("正在生成 GIF")
        self.lbl_title.setObjectName("H1")
        root.addWidget(self.lbl_title)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(True)
        self.bar.setFixedHeight(16)
        root.addWidget(self.bar)
        self.lbl_status = QLabel("准备中…")
        self.lbl_status.setObjectName("Hint")
        root.addWidget(self.lbl_status)
        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("Secondary")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self._on_cancel)
        row.addWidget(self.btn_cancel)
        root.addLayout(row)

    def begin(self, title="正在生成 GIF"):
        self.lbl_title.setText(title)
        self.bar.setValue(0)
        self.lbl_status.setText("准备中…")
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setText("取消")
        self.show()
        self.raise_()

    def set_progress(self, i, n):
        self.bar.setValue(int(100 * i / max(n, 1)))
        self.lbl_status.setText(f"正在渲染截图 {i}/{n}")

    def set_status(self, text):
        self.lbl_status.setText(text)

    def finish(self):
        self.bar.setValue(100)
        self.hide()

    def _on_cancel(self):
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("正在停止…")
        self.lbl_status.setText("正在停止, 请稍候…")
        self.cancelled.emit()


# ==========================================================================
# GIF 预览画布
# ==========================================================================
class GifCanvas(QWidget):
    viewChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Preview")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.OpenHandCursor)
        self.movie = None
        self.placeholder = ("还没有生成 GIF\n\n在「GIF 生成」页点「生成 GIF」,"
                            "完成后会自动跳到这里")
        self.user_zoom = None
        self.pan = QPointF(0.0, 0.0)
        self._drag = None

    def sizeHint(self):  # noqa: N802
        return QSize(520, 360)

    def minimumSizeHint(self):  # noqa: N802
        return QSize(200, 160)

    def set_movie(self, movie):
        self.movie = movie
        self.user_zoom = None
        self.pan = QPointF(0.0, 0.0)
        self.update()
        self.viewChanged.emit()

    def _frame(self):
        try:
            movie = self.movie
            return movie.currentPixmap() if movie is not None else None
        except RuntimeError:
            return None

    def fit_scale(self):
        pm = self._frame()
        if pm is None or pm.isNull() or pm.width() <= 0:
            return 1.0
        dpr = float(self.devicePixelRatioF() or 1.0)
        return min(self.width() * dpr / pm.width(),
                   self.height() * dpr / pm.height(), 1.0)

    def effective_scale(self):
        return self.fit_scale() if self.user_zoom is None else float(self.user_zoom)

    def reset_view(self):
        self.user_zoom = None
        self.pan = QPointF(0.0, 0.0)
        self.update()
        self.viewChanged.emit()

    def refresh(self):
        self.update()

    def wheelEvent(self, event):  # noqa: N802
        pm = self._frame()
        if pm is None or pm.isNull():
            return
        delta = event.angleDelta().y()
        if not delta:
            return
        dpr = float(self.devicePixelRatioF() or 1.0)
        k0 = self.effective_scale()
        k1 = max(0.05, min(8.0, k0 * (1.1 ** (delta / 120.0))))
        ux = event.position().x() * dpr - self.width() * dpr / 2.0
        uy = event.position().y() * dpr - self.height() * dpr / 2.0
        px = self.pan.x() * dpr
        py = self.pan.y() * dpr
        ratio = k1 / k0 if k0 else 1.0
        self.pan = QPointF((ux - (ux - px) * ratio) / dpr,
                           (uy - (uy - py) * ratio) / dpr)
        self.user_zoom = k1
        self.update()
        self.viewChanged.emit()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and self._frame() is not None:
            self._drag = (event.position(), QPointF(self.pan))
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag is None:
            return
        start, base = self._drag
        self.pan = base + (event.position() - start)
        self.update()
        self.viewChanged.emit()

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._drag = None
        self.setCursor(Qt.OpenHandCursor)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        self.reset_view()

    def paintEvent(self, event):  # noqa: N802
        opt = QStyleOption()
        opt.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, painter, self)
        pm = self._frame()
        if pm is None or pm.isNull() or pm.width() <= 0:
            painter.setPen(QColor(THEME["text_dim"]))
            painter.drawText(self.rect(), Qt.AlignCenter, self.placeholder)
            return
        dpr = float(self.devicePixelRatioF() or 1.0)
        k = self.effective_scale()
        tw = max(1, int(round(pm.width() * k)))
        th = max(1, int(round(pm.height() * k)))
        if (tw, th) != (pm.width(), pm.height()):
            mode = Qt.SmoothTransformation if k < 1.0 else Qt.FastTransformation
            pm = pm.scaled(tw, th, Qt.KeepAspectRatio, mode)
        x_dev = round(self.width() * dpr / 2.0 + self.pan.x() * dpr - pm.width() / 2.0)
        y_dev = round(self.height() * dpr / 2.0 + self.pan.y() * dpr - pm.height() / 2.0)
        pm.setDevicePixelRatio(dpr)
        painter.drawPixmap(QPointF(x_dev / dpr, y_dev / dpr), pm)


# ==========================================================================
# 内嵌 3D 结构查看器
# ==========================================================================
class StructureViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tmpdir = Path(tempfile.mkdtemp(prefix="bader-viewer-"))
        self._ready = False
        self._pending: list[str] = []
        self._poll = 0
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(320)

        self.web = QWebEngineView(self)
        self.web.setMinimumHeight(280)
        self.web.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.web.loadFinished.connect(self._on_load)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        holder = QFrame()
        holder.setObjectName("Card")
        holder.setAttribute(Qt.WA_StyledBackground, True)
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(6, 6, 6, 6)
        hl.addWidget(self.web)
        root.addWidget(holder, 1)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        tip = QLabel("拖动旋转 · 滚轮缩放 · 双击复位")
        tip.setObjectName("Chip")
        bar.addWidget(tip)
        bar.addStretch(1)
        self.btn_reset = QPushButton("重置视角")
        self.btn_reset.setObjectName("Ghost")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.clicked.connect(lambda: self.run("window.resetView();"))
        bar.addWidget(self.btn_reset)
        root.addLayout(bar)

    def load(self, geom, cfg):
        js = core.ensure_3dmol_js()
        html = core.build_html(js, geom, cfg)
        # 明确设置页面背景色, 避免顶层窗口半透明时 WebEngine 露出黑色底
        bg = str(cfg.get("bg", "white") or "white")
        color = QColor(bg)
        if not color.isValid():
            color = QColor("white")
        try:
            self.web.page().setBackgroundColor(color)
        except Exception:  # noqa: BLE001
            pass
        # 同时给 WebEngine 控件一个实底色, 避免无边框半透明窗口下露出黑底
        try:
            self.web.setStyleSheet(
                "QWebEngineView{background:%s;border:none;}" % color.name())
            self.web.setAttribute(Qt.WA_TranslucentBackground, False)
        except Exception:  # noqa: BLE001
            pass
        path = self._tmpdir / "viewer.html"
        path.write_text(html, encoding="utf-8")
        self._ready = False
        self.web.load(QUrl.fromLocalFile(str(path.resolve())))

    def _on_load(self, ok):
        if not ok:
            return
        self._poll = 0
        QTimer.singleShot(150, self._poll_ready)

    def _poll_ready(self):
        if self._ready:
            return
        self._poll += 1

        def cb(val):
            if val:
                self._ready = True
                for js in self._pending:
                    self.web.page().runJavaScript(js)
                self._pending.clear()
            elif self._poll < 100:
                QTimer.singleShot(150, self._poll_ready)

        self.web.page().runJavaScript("window.ready === true", cb)

    def run(self, js, callback=None):
        if self._ready:
            if callback is not None:
                self.web.page().runJavaScript(js, callback)
            else:
                self.web.page().runJavaScript(js)
        else:
            self._pending.append(js)

    def closeEvent(self, event):  # noqa: N802
        try:
            self.web.stop()
            self.web.setParent(None)
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        super().closeEvent(event)

    def shutdown(self):
        try:
            self.web.stop()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(self._tmpdir, ignore_errors=True)


# ==========================================================================
# 主窗口
# ==========================================================================
class MainWindow(QWidget):
    POLL_MS = 120
    RESIZE_MARGIN = 6
    DEFAULT_W = 1360
    DEFAULT_H = 860

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bader 电荷可视化 · 旋转 GIF 工作台")
        self.setMinimumSize(1000, 680)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        # 使用不透明窗口: 避免无边框半透明窗口下 QWebEngine 未绘制像素透出桌面（黑线）
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)
        self.setMouseTracking(True)

        self._dark = False
        self._first_show = False
        self._filled = False
        self._switches: list[Switch] = []
        self._resize_edge = None
        self._resize_start = None

        self.data: dict | None = None
        self.last_output: str | None = None
        self.preview_path: str | None = None
        self.preview_movie = None
        self._gif_size = None
        self.worker = None
        self.cancel_evt = threading.Event()
        self.q: queue.Queue = queue.Queue()

        self._build()
        self._set_icon()
        self._view_timer = QTimer(self)
        self._view_timer.setSingleShot(True)
        self._view_timer.timeout.connect(self._reload_viewer)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(self.POLL_MS)

    # ------------------------------------------------------------------
    def _set_icon(self):
        ico = HERE / "assets" / "app.ico"
        if ico.is_file():
            icon = QIcon(str(ico))
            self.setWindowIcon(icon)
            app = QApplication.instance()
            if app is not None:
                app.setWindowIcon(icon)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        self.outer = outer
        self.container = QFrame()
        self.container.setObjectName("Window")
        outer.addWidget(self.container)

        root = QVBoxLayout(self.container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_titlebar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self._build_actionbar())

        self.pages = QStackedWidget()
        self.pages.addWidget(self._page_structure())
        self.pages.addWidget(self._page_table())
        self.pages.addWidget(self._page_gif())
        self.pages.addWidget(self._page_preview())
        self.pages.addWidget(self._page_log())
        self.pages.currentChanged.connect(self._on_page_changed)
        right.addWidget(self.pages, 1)
        right.addWidget(self._build_footer())

        wrap = QWidget()
        wrap.setLayout(right)
        body.addWidget(wrap, 1)
        root.addLayout(body, 1)

    # ---- 窗口背景（不透明, 避免 WebEngine 底边透出黑色） ----
    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)

    # ---- 标题栏 ----
    def _build_titlebar(self):
        bar = QWidget()
        bar.setObjectName("TitleBar")
        bar.setFixedHeight(48)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(8)
        for name, slot in (("TrafficClose", self.close),
                           ("TrafficMin", self.showMinimized),
                           ("TrafficMax", self._toggle_max)):
            btn = QPushButton()
            btn.setObjectName(name)
            btn.setFixedSize(12, 12)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(slot)
            lay.addWidget(btn)
        lay.addStretch(1)
        title = QLabel("Bader 电荷可视化  ·  ACF.dat + POSCAR")
        title.setObjectName("AppName")
        lay.addWidget(title)
        lay.addStretch(1)
        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setObjectName("Ghost")
        self.theme_btn.setFixedWidth(38)
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setToolTip("切换深色 / 浅色主题")
        self.theme_btn.clicked.connect(self._toggle_theme)
        lay.addWidget(self.theme_btn)
        return bar

    def _toggle_max(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def _is_framed_fullscreen(self) -> bool:
        return bool(self.isMaximized() or self.isFullScreen()
                    or getattr(self, "_filled", False))

    def _apply_window_frame(self):
        maxed = self._is_framed_fullscreen()
        m = 0
        self.outer.setContentsMargins(m, m, m, m)
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor(THEME["container"]))
        self.setPalette(pal)
        val = "true" if maxed else "false"
        if self.container.property("Maxed") != val:
            self.container.setProperty("Maxed", val)
            self.container.style().unpolish(self.container)
            self.container.style().polish(self.container)
        self.update()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if not self._first_show:
            self._first_show = True
            scr = QApplication.primaryScreen()
            if scr is not None:
                g = scr.availableGeometry()
                w = min(self.DEFAULT_W, int(g.width() * 0.9))
                h = min(self.DEFAULT_H, int(g.height() * 0.9))
                self.resize(max(w, self.minimumWidth()), max(h, self.minimumHeight()))
                self.move(g.x() + max(0, (g.width() - w) // 2),
                          g.y() + max(0, (g.height() - h) // 2))
            self._filled = False
            self._autoload_defaults()
        self._apply_window_frame()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if getattr(self, "preview_movie", None) is not None:
            self._paint_preview_frame()

    def changeEvent(self, event):  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            if self.windowState() & Qt.WindowMaximized:
                self._filled = False
            self._apply_window_frame()

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key_F11:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
            event.accept()
            return
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self.showNormal()
            event.accept()
            return
        super().keyPressEvent(event)

    def _toggle_theme(self):
        self._dark = not self._dark
        apply_theme(QApplication.instance(), DARK if self._dark else LIGHT)
        self.theme_btn.setText("☀️" if self._dark else "🌙")
        for sw in self._switches:
            sw.apply_theme(THEME)
        self._apply_window_frame()

    # ---- 侧边栏 ----
    def _build_sidebar(self):
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(216)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(16, 18, 16, 16)
        lay.setSpacing(4)
        brand = QLabel("Bader 工作台")
        brand.setObjectName("SidebarBrand")
        lay.addWidget(brand)
        sub = QLabel("ACF.dat · POSCAR · GIF")
        sub.setObjectName("SidebarSub")
        lay.addWidget(sub)
        lay.addSpacing(16)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        items = [("结构可视化", 0), ("原子数据表", 1), ("GIF 生成", 2),
                 ("GIF 预览", 3), ("日志", 4)]
        for text, idx in items:
            btn = QPushButton(text)
            btn.setObjectName("NavItem")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, i=idx: self.pages.setCurrentIndex(i))
            self.nav_group.addButton(btn)
            lay.addWidget(btn)
            if idx == 0:
                btn.setChecked(True)
        lay.addStretch(1)
        self.lbl_data = QLabel("尚未加载数据")
        self.lbl_data.setObjectName("SidebarSub")
        self.lbl_data.setWordWrap(True)
        lay.addWidget(self.lbl_data)
        return side

    # ---- 动作栏 ----
    def _build_actionbar(self):
        bar = QWidget()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(24, 16, 24, 8)
        lay.setSpacing(10)
        self.page_title = QLabel("结构可视化")
        self.page_title.setObjectName("H1")
        lay.addWidget(self.page_title)
        lay.addStretch(1)
        self.btn_html = QPushButton("导出 HTML")
        self.btn_html.setObjectName("Secondary")
        self.btn_html.setCursor(Qt.PointingHandCursor)
        self.btn_html.setToolTip("导出与网页版一致的独立 HTML 结果页 (自带 3Dmol.js)")
        self.btn_html.clicked.connect(self._export_html)
        lay.addWidget(self.btn_html)
        self.btn_run = QPushButton("生成 GIF")
        self.btn_run.setObjectName("Primary")
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.clicked.connect(self._start)
        lay.addWidget(self.btn_run)
        return bar

    def _build_footer(self):
        foot = QWidget()
        lay = QVBoxLayout(foot)
        lay.setContentsMargins(24, 6, 24, 16)
        lay.setSpacing(6)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        lay.addWidget(self.progress)
        self.status = QLabel("就绪 · 请选择 POSCAR 与 ACF.dat")
        self.status.setObjectName("Footer")
        lay.addWidget(self.status)
        return foot

    # ---- 通用布局工具 ----
    def _make_scroll(self, margins=(24, 4, 24, 16), spacing=16):
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        area.viewport().setAutoFillBackground(False)
        inner = QWidget()
        inner.setObjectName("PageInner")
        inner.setAttribute(Qt.WA_StyledBackground, True)
        area.setWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(*margins)
        lay.setSpacing(spacing)
        return area, lay

    def _side_panel(self, width=356):
        area, lay = self._make_scroll(margins=(0, 0, 8, 0), spacing=12)
        area.setFixedWidth(width)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        return area, lay

    def _two_col_page(self, build_main, build_side, margins=(20, 2, 20, 12),
                      spacing=14, side_width=356, main_tail_stretch=True):
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(*margins)
        h.setSpacing(spacing)
        main, mlay = self._make_scroll(margins=(0, 0, 10, 0), spacing=12)
        build_main(mlay)
        if main_tail_stretch:
            mlay.addStretch(1)
        h.addWidget(main, 1)
        side, slay = self._side_panel(side_width)
        build_side(slay)
        slay.addStretch(1)
        h.addWidget(side, 0)
        return page

    def _file_row(self, parent_card, label, var, pick_dir=False, types=None,
                  save=False, on_change=True):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(field_label(label, 70))
        edit = QLineEdit(var)
        row.addWidget(edit, 1)
        btn = QPushButton("文件夹" if pick_dir else ("另存" if save else "浏览"))
        btn.setObjectName("Browse")
        btn.setCursor(Qt.PointingHandCursor)

        def pick():
            if pick_dir:
                path = QFileDialog.getExistingDirectory(self, "选择目录",
                                                        edit.text() or str(HERE))
            elif save:
                path, _ = QFileDialog.getSaveFileName(
                    self, "选择输出文件", edit.text() or str(HERE),
                    types or "GIF 动画 (*.gif)")
            else:
                path, _ = QFileDialog.getOpenFileName(
                    self, "选择文件", edit.text() or str(HERE),
                    types or "所有文件 (*)")
            if path:
                edit.setText(path)

        btn.clicked.connect(pick)
        row.addWidget(btn)
        parent_card.add_layout(row)
        if on_change:
            edit.editingFinished.connect(self._reload_data)
        return edit

    def _switch_row(self, text, value, hint=None):
        row = QHBoxLayout()
        row.setSpacing(10)
        lab = QLabel(text)
        lab.setObjectName("FieldLabel")
        row.addWidget(lab)
        row.addStretch(1)
        sw = Switch()
        sw.setChecked(value, animate=False)
        sw.apply_theme(THEME)
        self._switches.append(sw)
        row.addWidget(sw)
        box = QVBoxLayout()
        box.setSpacing(2)
        box.addLayout(row)
        if hint:
            box.addWidget(hint_label(hint))
        return sw, box

    def _entry_row(self, parent_card, label, value, width=110, cast=float,
                   minimum=0.0, maximum=1e9, decimals=2, step=1.0, label_width=90):
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(field_label(label, label_width))
        if cast is int:
            edit = QSpinBox()
            edit.setRange(int(minimum), int(maximum))
            edit.setSingleStep(int(step))
        else:
            edit = QDoubleSpinBox()
            edit.setRange(float(minimum), float(maximum))
            edit.setDecimals(int(decimals))
            edit.setSingleStep(float(step))
        edit.setValue(value)
        edit.setFixedWidth(width)
        row.addWidget(edit)
        row.addStretch(1)
        parent_card.add_layout(row)
        return edit

    def _dir_row(self, parent_card, label, var, on_change=True):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(field_label(label, 56))
        edit = QLineEdit(var)
        edit.setPlaceholderText("选择包含 POSCAR / ACF.dat 的目录")
        row.addWidget(edit, 1)
        btn = QPushButton("浏览")
        btn.setObjectName("Browse")
        btn.setCursor(Qt.PointingHandCursor)

        def pick():
            path = QFileDialog.getExistingDirectory(self, "选择输入目录",
                                                    edit.text() or str(HERE))
            if path:
                edit.setText(path)
                if on_change:
                    self._reload_data()

        btn.clicked.connect(pick)
        row.addWidget(btn)
        parent_card.add_layout(row)
        if on_change:
            edit.editingFinished.connect(self._reload_data)
        return edit

    def _labeled_cell(self, label, widget, label_width=84):
        cell = QWidget()
        h = QHBoxLayout(cell)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        h.addWidget(field_label(label, label_width))
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        h.addWidget(widget, 1)
        return cell

    def _grid_entry(self, grid, r, c, label, value, cast=float,
                    minimum=0.0, maximum=1e9, decimals=2, step=1.0,
                    label_width=84):
        if cast is int:
            edit = QSpinBox()
            edit.setRange(int(minimum), int(maximum))
            edit.setSingleStep(int(step))
        else:
            edit = QDoubleSpinBox()
            edit.setRange(float(minimum), float(maximum))
            edit.setDecimals(int(decimals))
            edit.setSingleStep(float(step))
        edit.setValue(value)
        edit.setMinimumWidth(90)
        grid.addWidget(self._labeled_cell(label, edit, label_width), r, c)
        return edit

    def _grid_combo(self, grid, r, c, label, items, current=0, label_width=84):
        cb = ComboBox()
        for key, text in items:
            cb.addItem(text, key)
        cb.setCurrentIndex(current)
        grid.addWidget(self._labeled_cell(label, cb, label_width), r, c)
        return cb

    # ==================================================================
    # 页面 1: 结构可视化
    # ==================================================================
    def _page_structure(self):
        def build_main(lay):
            # 中间区域: 「结构可视化」标题下方、3D 视图上方, 居中放置基准视角
            bar = QWidget()
            hb = QHBoxLayout(bar)
            hb.setContentsMargins(0, 2, 0, 4)
            hb.setSpacing(10)
            hb.addStretch(1)
            title = QLabel("基准视角")
            title.setObjectName("FieldLabel")
            hb.addWidget(title)
            self.seg_view = SegmentedControl(
                [(k, core.VIEW_LABELS[k]) for k in core.VIEW_NAMES], value="front")
            self.seg_view.changed.connect(lambda _=None: self._reload_viewer())
            hb.addWidget(self.seg_view)
            hb.addStretch(1)
            lay.addWidget(bar)

            self.viewer = StructureViewer()
            lay.addWidget(self.viewer, 1)

        def build_side(lay):
            card = Card("输入目录")
            self.e_dir = self._dir_row(card, "目录", self._default_dir())
            card.add(hint_label("自动读取该目录下的 POSCAR/CONTCAR、ACF.dat 与 "
                                "POTCAR（可选，用于计算 Δq = q_Bader − ZVAL）。"))
            self.lbl_files = QLabel("—")
            self.lbl_files.setObjectName("Hint")
            self.lbl_files.setWordWrap(True)
            self.lbl_files.setTextInteractionFlags(Qt.TextSelectableByMouse)
            card.add(self.lbl_files)
            row = QHBoxLayout()
            btn_load = QPushButton("重新载入")
            btn_load.setObjectName("Secondary")
            btn_load.setCursor(Qt.PointingHandCursor)
            btn_load.clicked.connect(self._reload_data)
            row.addWidget(btn_load)
            btn_html = QPushButton("导出 HTML")
            btn_html.setObjectName("Secondary")
            btn_html.setCursor(Qt.PointingHandCursor)
            btn_html.setToolTip("导出与网页版一致的独立 HTML 结果页 (自带 3Dmol.js)")
            btn_html.clicked.connect(self._export_html)
            row.addWidget(btn_html)
            card.add_layout(row)
            lay.addWidget(card)

            card2 = Card("显示设置")
            grid = QGridLayout()
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(10)
            self.cb_label = self._grid_combo(
                grid, 0, 0, "标注",
                [(k, core.LABEL_MODE_NAMES[k]) for k in core.LABEL_MODES],
                0, 56)
            self.cb_label.currentIndexChanged.connect(
                lambda _=None: self._reload_viewer())
            self.cb_color = self._grid_combo(
                grid, 1, 0, "着色",
                [(k, core.COLOR_MODE_NAMES[k]) for k in core.COLOR_MODES],
                0, 56)
            self.cb_color.currentIndexChanged.connect(
                lambda _=None: self._reload_viewer())
            self.cb_style = self._grid_combo(
                grid, 2, 0, "样式",
                [("ballstick", "球棍模型"), ("sphere", "空间填充"),
                 ("stick", "棍状"), ("line", "线框")], 0, 56)
            self.cb_style.currentIndexChanged.connect(
                lambda _=None: self._reload_viewer())
            self.cb_bg = ComboBox()
            self.cb_bg.addItems(["white", "black", "#f5f7fa", "#0c1114"])
            self.cb_bg.setEditable(True)
            self.cb_bg.currentIndexChanged.connect(
                lambda _=None: self._reload_viewer())
            grid.addWidget(self._labeled_cell("背景", self.cb_bg, 56), 3, 0)
            card2.add_layout(grid)

            self.sl_radius = SliderField("半径系数", 0.2, 1.6, 0.6, steps=140,
                                         fmt="{:.2f}", width=56)
            self.sl_radius.slider.valueChanged.connect(self._schedule_view_refresh)
            card2.add(self.sl_radius)

            self.sl_zoom = SliderField("缩放", 0.4, 3.0, 1.25, steps=260,
                                       fmt="{:.2f}", width=56)
            self.sl_zoom.slider.valueChanged.connect(self._schedule_view_refresh)
            card2.add(self.sl_zoom)

            self.sl_label_size = SliderField("标签字号", 6, 30, 12, steps=24,
                                             fmt="{:.0f}", width=56)
            self.sl_label_size.slider.valueChanged.connect(self._schedule_view_refresh)
            card2.add(self.sl_label_size)

            self.sw_cell, box = self._switch_row("显示晶胞框", True)
            self.sw_cell.toggled.connect(lambda _=None: self._reload_viewer())
            card2.add_layout(box)
            self.sw_labels, box = self._switch_row("显示标签", True)
            self.sw_labels.toggled.connect(lambda _=None: self._reload_viewer())
            card2.add_layout(box)
            lay.addWidget(card2)

            card3 = Card("统计")
            self.lbl_stats = QLabel("—")
            self.lbl_stats.setObjectName("Hint")
            self.lbl_stats.setWordWrap(True)
            self.lbl_stats.setTextInteractionFlags(Qt.TextSelectableByMouse)
            card3.add(self.lbl_stats)
            lay.addWidget(card3)

        return self._two_col_page(build_main, build_side, main_tail_stretch=False)

    def _default_dir(self):
        for name in ("test", "samples"):
            for base in (APP_DIR, HERE):
                if (base / name / "ACF.dat").is_file():
                    return str(base / name)
        return str(APP_DIR)

    # ==================================================================
    # 页面 2: 原子数据表
    # ==================================================================
    def _page_table(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 6, 20, 12)
        card = Card("原子 Bader 电荷明细")
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["序号", "元素", "X (Å)", "Y (Å)", "Z (Å)",
             "ZVAL", "Bader 电荷 (e)", "Δq (e)"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setCornerButtonEnabled(False)
        self.table.setMinimumHeight(380)
        hh = self.table.horizontalHeader()
        hh.setHighlightSections(False)
        hh.setSectionResizeMode(QHeaderView.Stretch)
        hh.setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        card.add(self.table)
        card.body.setStretchFactor(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(hint_label("Δq = q_Bader − ZVAL; 红色表示电子富集, 蓝色表示电子亏损。"))
        row.addStretch(1)
        btn_html = QPushButton("导出 HTML")
        btn_html.setObjectName("Secondary")
        btn_html.setCursor(Qt.PointingHandCursor)
        btn_html.clicked.connect(self._export_html)
        row.addWidget(btn_html)
        btn = QPushButton("导出 CSV")
        btn.setObjectName("Secondary")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self._export_csv)
        row.addWidget(btn)
        card.add_layout(row)
        lay.addWidget(card, 1)
        return page

    def _populate_table(self):
        if not hasattr(self, "table"):
            return
        self.table.setRowCount(0)
        if not self.data:
            return
        has_delta = self.data["has_delta"]
        self.table.setRowCount(self.data["atom_count"])
        for r, a in enumerate(self.data["atoms"]):
            zval = f"{a['zval']:.2f}" if "zval" in a else "—"
            if has_delta:
                cells = [str(a["index"]), a["symbol"],
                         f"{a['x']:.6f}", f"{a['y']:.6f}", f"{a['z']:.6f}",
                         zval, f"{a['charge']:.6f}", f"{a['delta_charge']:+.6f}"]
            else:
                cells = [str(a["index"]), a["symbol"],
                         f"{a['x']:.6f}", f"{a['y']:.6f}", f"{a['z']:.6f}",
                         "—", f"{a['charge']:.6f}", "—"]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c >= 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignCenter)
                if has_delta and c == 7:
                    item.setForeground(QColor("#b91c1c" if a["delta_charge"] >= 0
                                              else "#1d4ed8"))
                self.table.setItem(r, c, item)

    def _export_html(self):
        if not self.data:
            self._toast("提示", "尚未加载数据。")
            return
        default = str(DEFAULT_OUT_DIR / core.HTML_NAME)
        path, _ = QFileDialog.getSaveFileName(self, "导出独立 HTML", default,
                                              "HTML 文件 (*.html)")
        if not path:
            return
        try:
            out = core.export_standalone_html(self.data, path)
            self._log(f"[完成] 已导出独立 HTML: {out}")
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Information)
            box.setWindowTitle("完成")
            box.setText(f"已导出独立 HTML 结果页:\n{out}")
            open_btn = box.addButton("打开 HTML", QMessageBox.AcceptRole)
            box.addButton("关闭", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is open_btn:
                try:
                    os.startfile(out)
                except AttributeError:
                    import subprocess
                    subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", out])
        except Exception as exc:  # noqa: BLE001
            self._log(f"[错误] 导出 HTML 失败: {exc}")
            self._toast("出错", str(exc), QMessageBox.Critical)

    def _export_csv(self):
        if not self.data:
            self._toast("提示", "尚未加载数据。")
            return
        default = str(DEFAULT_OUT_DIR / "bader_charge.csv")
        path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", default,
                                              "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            import csv
            header = ["index", "element", "x", "y", "z", "zval",
                      "bader_charge", "delta_charge"]
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh)
                writer.writerow(header)
                for a in self.data["atoms"]:
                    writer.writerow([
                        a["index"], a["symbol"], a["x"], a["y"], a["z"],
                        a.get("zval", ""), a["charge"],
                        a.get("delta_charge", "")])
            self._log(f"[完成] 已导出 CSV: {path}")
            self._toast("完成", f"已导出 CSV:\n{path}")
        except Exception as exc:  # noqa: BLE001
            self._log(f"[错误] 导出 CSV 失败: {exc}")
            self._toast("出错", str(exc), QMessageBox.Critical)

    # ==================================================================
    # 页面 2: GIF 生成
    # ==================================================================
    def _page_gif(self):
        def build_main(lay):
            card = Card("视角与旋转")
            grid = QGridLayout()
            grid.setHorizontalSpacing(22)
            grid.setVerticalSpacing(12)
            self.cb_gif_view = self._grid_combo(
                grid, 0, 0, "基准视角",
                [(k, core.VIEW_LABELS[k]) for k in core.VIEW_NAMES], 0)
            self.cb_axis = self._grid_combo(
                grid, 0, 1, "旋转轴",
                [(k, core.ROT_AXIS_NAMES[k])
                 for k in ("a", "b", "c", "screen-v", "screen-h")], 2)
            self.sp_angle = self._grid_entry(
                grid, 1, 0, "总转角 (°)", 360.0, cast=float,
                minimum=-3600, maximum=3600, step=15, decimals=1)
            self.sp_frames = self._grid_entry(
                grid, 1, 1, "帧数", 60, cast=int,
                minimum=2, maximum=1200, step=5)
            self.sp_fps = self._grid_entry(
                grid, 2, 0, "帧率 (fps)", 20.0, cast=float,
                minimum=1, maximum=60, step=1, decimals=1)
            card.add_layout(grid)
            card.add(hint_label("旋转轴 a/b/c 为晶胞物理轴, screen-v / screen-h "
                                "为当前屏幕的竖直 / 水平方向; 总转角 360° 时首尾无缝循环。"))
            lay.addWidget(card)

            card2 = Card("画布与输出")
            self.e_out = self._file_row(card2, "输出 GIF", self._default_out(),
                                        save=True, on_change=False)
            self.e_out.editingFinished.connect(self._refresh_summary)
            grid2 = QGridLayout()
            grid2.setHorizontalSpacing(22)
            grid2.setVerticalSpacing(12)
            self.sp_width = self._grid_entry(
                grid2, 0, 0, "宽 (px)", 640, cast=int,
                minimum=120, maximum=3000, step=20)
            self.sp_height = self._grid_entry(
                grid2, 0, 1, "高 (px)", 640, cast=int,
                minimum=120, maximum=3000, step=20)
            self.sp_scale = self._grid_entry(
                grid2, 1, 0, "超采样", 1.0, cast=float,
                minimum=1.0, maximum=4.0, step=0.5, decimals=1)
            self.sp_colors = self._grid_entry(
                grid2, 1, 1, "调色板", 256, cast=int,
                minimum=16, maximum=256, step=16)
            card2.add_layout(grid2)
            toggles = QHBoxLayout()
            toggles.setSpacing(26)
            self.sw_pingpong, box = self._switch_row("乒乓循环", False,
                                                     "正放 + 倒放")
            toggles.addLayout(box)
            self.sw_loop, box = self._switch_row("无限循环", True)
            toggles.addLayout(box)
            self.sw_legend, box = self._switch_row("底部图例", True,
                                                   "元素配色 / 电荷色带")
            toggles.addLayout(box)
            toggles.addStretch(1)
            card2.add_layout(toggles)
            lay.addWidget(card2)

            card3 = Card("说明")
            card3.add(hint_label(
                "· 渲染使用系统 Edge/Chrome + 3Dmol.js（需安装 playwright）。\n"
                "· 超采样 2 可输出更清晰的大图, 合成 GIF 时再缩放回目标宽度。\n"
                "· 帧率影响播放速度, 帧数影响旋转的平滑度。"))
            lay.addWidget(card3)

        def build_side(lay):
            card = Card("当前摘要")
            self.lbl_summary = QLabel("—")
            self.lbl_summary.setObjectName("Hint")
            self.lbl_summary.setWordWrap(True)
            self.lbl_summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
            card.add(self.lbl_summary)
            lay.addWidget(card)

            card2 = Card("操作")
            btn = QPushButton("生成 GIF")
            btn.setObjectName("Primary")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(self._start)
            card2.add(btn)
            btn_png = QPushButton("导出单帧 PNG")
            btn_png.setObjectName("Secondary")
            btn_png.setCursor(Qt.PointingHandCursor)
            btn_png.clicked.connect(self._export_png)
            card2.add(btn_png)
            btn_html = QPushButton("导出独立 HTML")
            btn_html.setObjectName("Secondary")
            btn_html.setCursor(Qt.PointingHandCursor)
            btn_html.clicked.connect(self._export_html)
            card2.add(btn_html)
            btn2 = QPushButton("打开输出目录")
            btn2.setObjectName("Ghost")
            btn2.setCursor(Qt.PointingHandCursor)
            btn2.clicked.connect(self._open_output_dir)
            card2.add(btn2)
            lay.addWidget(card2)

        return self._two_col_page(build_main, build_side)

    def _default_out(self):
        return str(DEFAULT_OUT_DIR / "bader.gif")

    # ==================================================================
    # 页面 3: 预览
    # ==================================================================
    def _page_preview(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 6, 16, 10)
        lay.setSpacing(8)
        card = Card("")
        card.vbox.setContentsMargins(10, 10, 10, 10)
        self.preview_canvas = GifCanvas()
        self.preview_canvas.viewChanged.connect(self._paint_preview_frame)
        card.add(self.preview_canvas)
        card.body.setStretchFactor(self.preview_canvas, 1)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_play = QPushButton("暂停")
        self.btn_play.setObjectName("Secondary")
        self.btn_play.setCursor(Qt.PointingHandCursor)
        self.btn_play.clicked.connect(self._toggle_play)
        row.addWidget(self.btn_play)
        b1 = QPushButton("打开 GIF 文件")
        b1.setObjectName("Ghost")
        b1.setCursor(Qt.PointingHandCursor)
        b1.clicked.connect(self._open_output)
        row.addWidget(b1)
        b2 = QPushButton("打开所在文件夹")
        b2.setObjectName("Ghost")
        b2.setCursor(Qt.PointingHandCursor)
        b2.clicked.connect(self._open_output_dir)
        row.addWidget(b2)
        hint = QLabel("滚轮缩放 · 拖动平移 · 双击复位")
        hint.setObjectName("Hint")
        row.addWidget(hint)
        row.addStretch(1)
        self.lbl_prev_info = QLabel("—")
        self.lbl_prev_info.setObjectName("Chip")
        row.addWidget(self.lbl_prev_info)
        card.add_layout(row)
        lay.addWidget(card, 1)
        return page

    # ==================================================================
    # 页面 4: 日志
    # ==================================================================
    def _page_log(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 6, 20, 12)
        card = Card("运行日志")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(6000)
        card.add(self.log)
        row = QHBoxLayout()
        row.addStretch(1)
        btn = QPushButton("清空")
        btn.setObjectName("Ghost")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.log.clear)
        row.addWidget(btn)
        card.add_layout(row)
        lay.addWidget(card, 1)
        return page

    # ==================================================================
    # 数据加载 / 视图刷新
    # ==================================================================
    def _on_page_changed(self, idx):
        names = ["结构可视化", "原子数据表", "GIF 生成", "GIF 预览", "日志"]
        if 0 <= idx < len(names):
            self.page_title.setText(names[idx])
            for b in self.nav_group.buttons():
                if b.text() == names[idx]:
                    b.setChecked(True)
        if idx == 3:
            mv = getattr(self, "preview_movie", None)
            if mv is not None:
                mv.start()
                self.btn_play.setText("暂停")
        else:
            mv = getattr(self, "preview_movie", None)
            if mv is not None:
                mv.stop()
        if idx == 2:
            self._refresh_summary()
        if idx == 1:
            self._populate_table()

    def _autoload_defaults(self):
        self._log(f"[信息] 工作目录: {HERE}")
        if self.e_dir.text().strip():
            self._reload_data()

    def _reload_data(self):
        folder = self.e_dir.text().strip()
        if not folder:
            return
        try:
            files = core.discover_files(folder)
        except Exception as exc:  # noqa: BLE001
            self.data = None
            self.status.setText("载入失败")
            self._log(f"[错误] {exc}")
            self.lbl_files.setText(f"无法读取目录: {exc}")
            self.lbl_stats.setText("载入失败")
            return

        self.lbl_files.setText(
            f"POSCAR : {Path(files['poscar']).name if files['poscar'] else '(未找到)'}\n"
            f"ACF.dat: {Path(files['acf']).name if files['acf'] else '(未找到)'}\n"
            f"POTCAR : {Path(files['potcar']).name if files['potcar'] else '(未找到)'}")

        missing = []
        if not files["poscar"]:
            missing.append("POSCAR/CONTCAR")
        if not files["acf"]:
            missing.append("ACF.dat")
        if missing:
            self.data = None
            self.status.setText("载入失败")
            msg = f"目录中缺少文件: {', '.join(missing)}"
            self._log(f"[错误] {msg}")
            self.lbl_stats.setText(msg)
            return

        try:
            self.data = core.load_bader_data(files["poscar"], files["acf"],
                                             files["potcar"], auto_potcar=True)
        except Exception as exc:  # noqa: BLE001
            self.data = None
            self.status.setText("载入失败")
            self._log(f"[错误] 载入失败: {exc}")
            self.lbl_stats.setText(f"载入失败:\n{exc}")
            return
        d = self.data
        for w in d["warnings"]:
            self._log(f"[警告] {w}")
        info = (f"已加载 · {d['atom_count']} 原子\n"
                f"元素: {', '.join(d['elements'])}")
        self.lbl_data.setText(info)
        value_name = "Δq" if d["has_delta"] else "Bader 电荷"
        stats = [
            f"原子总数: {d['atom_count']}",
            f"元素: {' '.join(f'{e}×{c}' for e, c in zip(d['elements'], d['counts']))}",
            f"总 Bader 电荷: {d['total_charge']:.4f} e",
            f"{value_name} 范围: {d['value_min']:.4f} ~ {d['value_max']:.4f} e",
            f"POSCAR: {Path(d['poscar_path']).name}",
            f"ACF.dat: {Path(d['acf_path']).name}",
            f"POTCAR: {Path(d['potcar_path']).name if d['potcar_path'] else '(未使用)'}",
        ]
        self.lbl_stats.setText("\n".join(stats))
        self.status.setText(f"加载完成: {d['atom_count']} 个原子")
        self._log(f"[完成] 已加载 {d['atom_count']} 个原子, "
                  f"元素 {d['elements']}, 来源 {Path(d['acf_path']).name}")
        self._reload_viewer()
        self._populate_table()
        self._refresh_summary()

    def _reload_viewer(self):
        if not self.data:
            return
        try:
            label_mode = self.cb_label.currentData()
            color_mode = self.cb_color.currentData()
            geom = core.build_geometry(
                self.data, label_mode=label_mode, color_mode=color_mode,
                radius_scale=self.sl_radius.value(),
                show_labels=self.sw_labels.isChecked())
            view = self.seg_view.value() or "front"
            orient = core.view_quaternion(self.data["lattice"], view)
            cfg = {
                "style": self.cb_style.currentData(),
                "show_cell": self.sw_cell.isChecked(),
                "cell_color": "#888888",
                "bg": self.cb_bg.currentText().strip() or "white",
                "zoom": self.sl_zoom.value(),
                "label_size": int(self.sl_label_size.value()),
                "interactive": True,
                "views": None,
                "orient": orient,
            }
            self.viewer.load(geom, cfg)
            self._refresh_summary()
        except Exception as exc:  # noqa: BLE001
            self._log(f"[错误] 刷新 3D 窗口失败: {exc}")
            self.status.setText("3D 窗口刷新失败")

    def _schedule_view_refresh(self):
        self._view_timer.start(120)

    # ==================================================================
    # GIF 任务
    # ==================================================================
    def _refresh_summary(self):
        if not self.data:
            self.lbl_summary.setText("尚未加载数据")
            return
        try:
            lines = [
                f"结构: {Path(self.data['poscar_path']).name}",
                f"原子: {self.data['atom_count']}",
                f"标注: {core.LABEL_MODE_NAMES[self.cb_label.currentData()]}",
                f"着色: {core.COLOR_MODE_NAMES[self.cb_color.currentData()]}",
                f"视角: {core.VIEW_LABELS[self.cb_gif_view.currentData()]}",
                f"旋转: {core.ROT_AXIS_NAMES[self.cb_axis.currentData()]} "
                f"{self.sp_angle.value():g}° · {self.sp_frames.value()} 帧",
                f"画布: {self.sp_width.value()} × {self.sp_height.value()}",
                f"帧率: {self.sp_fps.value():g} fps",
                f"输出: {self.e_out.text().strip() or '(未指定)'}",
            ]
            self.lbl_summary.setText("\n".join(lines))
        except Exception:  # noqa: BLE001
            pass

    def _collect_gif_config(self) -> dict:
        """在主线程收集界面参数, 供后台线程使用 (避免跨线程访问控件)。"""
        return {
            "label_mode": self.cb_label.currentData(),
            "color_mode": self.cb_color.currentData(),
            "view": self.cb_gif_view.currentData(),
            "rot_axis": self.cb_axis.currentData(),
            "rot_total": self.sp_angle.value(),
            "frames": self.sp_frames.value(),
            "fps": self.sp_fps.value(),
            "width": self.sp_width.value(),
            "height": self.sp_height.value(),
            "style": self.cb_style.currentData(),
            "radius_scale": self.sl_radius.value(),
            "show_cell": self.sw_cell.isChecked(),
            "bg": self.cb_bg.currentText().strip() or "white",
            "zoom": self.sl_zoom.value(),
            "pingpong": self.sw_pingpong.isChecked(),
            "loop": (0 if self.sw_loop.isChecked() else None),
            "colors": self.sp_colors.value(),
            "scale": self.sp_scale.value(),
            "show_labels": self.sw_labels.isChecked(),
            "label_size": int(self.sl_label_size.value()),
            "with_legend": self.sw_legend.isChecked(),
        }

    def _export_png(self):
        if not self.data:
            self._toast("提示", "尚未加载数据。")
            return
        default = str(DEFAULT_OUT_DIR / "bader_frame.png")
        path, _ = QFileDialog.getSaveFileName(self, "导出单帧 PNG", default,
                                              "PNG 图片 (*.png)")
        if not path:
            return
        cfg = self._collect_gif_config()
        self.btn_run.setEnabled(False)
        self.status.setText("渲染单帧…")

        def work():
            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = _queue_writer(self.q)
            try:
                out = core.render_single_png(self.data, path, **cfg)
                self.q.put(("png_done", out))
            except Exception:  # noqa: BLE001
                self.q.put(("error", traceback.format_exc()))
            finally:
                sys.stdout, sys.stderr = old_out, old_err
                self.q.put(("idle",))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _start(self):
        if self.worker and self.worker.is_alive():
            self._toast("提示", "已有任务在运行, 请等待或点击取消。")
            return
        if not self.data:
            self._toast("提示", "请先在「结构可视化」页选择 POSCAR 与 ACF.dat。")
            return
        out = self.e_out.text().strip()
        if not out:
            self._toast("参数有误", "请先指定输出 GIF 路径。")
            return
        cfg = self._collect_gif_config()
        self.cancel_evt.clear()
        self._stop_preview()
        self.btn_run.setEnabled(False)
        self.status.setText("渲染中…")
        self.progress.setValue(0)
        if getattr(self, "progress_dlg", None) is None:
            self.progress_dlg = ProgressDialog(self)
            self.progress_dlg.cancelled.connect(self._stop)
        self.progress_dlg.begin("正在生成 Bader GIF")
        self.worker = threading.Thread(target=self._run, args=(cfg, out), daemon=True)
        self.worker.start()

    def _stop(self):
        self.cancel_evt.set()
        self.status.setText("正在停止…")
        try:
            self.progress_dlg.set_status("正在停止, 请稍候…")
        except Exception:  # noqa: BLE001
            pass

    def _run(self, cfg, out):
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = _queue_writer(self.q)
        try:
            assert self.data is not None
            res = core.render_gif(
                self.data, out,
                progress=lambda i, n: self.q.put(("progress", i, n)),
                cancel=self.cancel_evt.is_set,
                **cfg,
            )
            self.q.put(("done", res["path"]))
        except Exception:  # noqa: BLE001
            self.q.put(("error", traceback.format_exc()))
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            self.q.put(("idle",))

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._log(msg[1])
                elif kind == "progress":
                    i, n = msg[1], msg[2]
                    self.progress.setValue(int(100 * i / max(n, 1)))
                    self.status.setText(f"渲染 {i}/{n}")
                    if getattr(self, "progress_dlg", None) and self.progress_dlg.isVisible():
                        self.progress_dlg.set_progress(i, n)
                elif kind == "done":
                    path = msg[1]
                    self.last_output = path
                    self.progress.setValue(100)
                    self.status.setText(f"完成: {Path(path).name}")
                    self._log(f"[完成] {path}")
                    if getattr(self, "progress_dlg", None):
                        self.progress_dlg.finish()
                    self._load_gif_preview(path)
                    self.pages.setCurrentIndex(3)
                    self._toast("完成", f"GIF 已生成:\n{path}")
                elif kind == "png_done":
                    out = msg[1]
                    self.last_output = out
                    self.status.setText(f"完成: {Path(out).name}")
                    self._log(f"[完成] 已导出单帧 PNG: {out}")
                    self._toast("完成", f"单帧 PNG 已生成:\n{out}")
                elif kind == "error":
                    if getattr(self, "progress_dlg", None):
                        self.progress_dlg.finish()
                    self.status.setText("出错")
                    self._log("[错误] " + str(msg[1]))
                    self._toast("出错", str(msg[1])[-1500:], QMessageBox.Critical)
                elif kind == "idle":
                    self.btn_run.setEnabled(True)
        except queue.Empty:
            pass

    # ==================================================================
    # 预览
    # ==================================================================
    def _load_gif_preview(self, path):
        if not path or not os.path.exists(path):
            return
        self._stop_preview()
        self.preview_path = path
        try:
            with Image.open(path) as im:
                self._gif_size = im.size
        except Exception:  # noqa: BLE001
            self._gif_size = None
        movie = QMovie(path)
        self.preview_movie = movie
        self.preview_canvas.set_movie(movie)
        movie.frameChanged.connect(self._paint_preview_frame)
        movie.start()
        self.btn_play.setText("暂停")
        self._log(f"[信息] 预览已载入: {path}")
        QTimer.singleShot(0, self._paint_preview_frame)

    def _stop_preview(self):
        mv = getattr(self, "preview_movie", None)
        if mv is not None:
            try:
                mv.stop()
                mv.frameChanged.disconnect(self._paint_preview_frame)
            except Exception:  # noqa: BLE001
                pass
        self.preview_movie = None
        if getattr(self, "preview_canvas", None) is not None:
            self.preview_canvas.set_movie(None)
        if mv is not None:
            mv.deleteLater()

    def _paint_preview_frame(self, *_):
        if getattr(self, "preview_canvas", None) is None:
            return
        self.preview_canvas.refresh()
        size = self._gif_size
        if not size:
            return
        k = self.preview_canvas.effective_scale()
        tag = (f"{k * 100:.0f}%" if self.preview_canvas.user_zoom is not None
               else ("1:1" if k >= 0.999 else f"适应 {k:.2f}×"))
        self.lbl_prev_info.setText(f"{size[0]} × {size[1]}  ·  {tag}")

    def _toggle_play(self):
        mv = getattr(self, "preview_movie", None)
        if mv is None:
            return
        if mv.state() == QMovie.Running:
            mv.stop()
            self.btn_play.setText("播放")
        else:
            mv.start()
            self.btn_play.setText("暂停")

    def _open_output(self):
        target = self.last_output or self.e_out.text().strip()
        if not target or not os.path.exists(target):
            self._toast("提示", "还没有可打开的输出文件。")
            return
        try:
            os.startfile(target)
        except AttributeError:
            import subprocess
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, target])

    def _open_output_dir(self):
        target = self.last_output or self.e_out.text().strip()
        target = os.path.dirname(os.path.abspath(target)) if target else str(HERE)
        if not os.path.isdir(target):
            target = str(HERE)
        try:
            os.startfile(target)
        except AttributeError:
            import subprocess
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, target])

    # ==================================================================
    def _log(self, text):
        if text:
            self.log.appendPlainText(str(text))

    def _toast(self, title, text, icon=QMessageBox.Information):
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(QMessageBox.Ok)
        box.exec()

    def closeEvent(self, event):  # noqa: N802
        self.cancel_evt.set()
        self._stop_preview()
        try:
            self.viewer.shutdown()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)


def main():
    # Windows: 设置 AppUserModelID, 让任务栏使用本程序图标而非 Python 默认图标
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "lyy.plotBader.gui.1")
        except Exception:  # noqa: BLE001
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("Bader 电荷可视化")
    app.setApplicationDisplayName("Bader 电荷可视化")
    ico = HERE / "assets" / "app.ico"
    if ico.is_file():
        app.setWindowIcon(QIcon(str(ico)))
    apply_theme(app, LIGHT)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
