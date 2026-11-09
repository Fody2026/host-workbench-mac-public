# -*- coding: utf-8 -*-
"""图文设计：画布排版 + 磨砂质感素材库 + 高清导出（JPG / PNG）"""
import os
import json
import random
import datetime
import logging
import subprocess
import time

from PySide6.QtCore import Qt, QRectF, QSize, QPointF
from PySide6.QtGui import (QPainter, QPen, QBrush, QColor, QPixmap, QImage, QFont,
                           QPolygonF, QRadialGradient, QLinearGradient, QIcon,
                           QPainterPath, QTextOption)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
    QComboBox, QSpinBox, QSlider, QColorDialog, QFileDialog, QGraphicsView,
    QGraphicsScene, QGraphicsItem, QGraphicsTextItem, QGraphicsPixmapItem,
    QGraphicsPathItem, QMessageBox, QListWidget, QListWidgetItem, QLineEdit,
    QPlainTextEdit,
    QScrollArea, QGraphicsDropShadowEffect, QApplication, QDialog, QDialogButtonBox, QProgressDialog
)

import common
import theme
import fonts
from common import data_dir, get_setting

logger = logging.getLogger(__name__)

FONT_LABELS = {
    "Ma Shan Zheng": "马善政毛笔楷 · 艺术",
    "Long Cang": "龙藏体 · 艺术",
    "有字库龙藏体": "龙藏体（别名）",
    "ZCOOL KuaiLe": "站酷快乐体 · 艺术",
    "Noto Sans CJK SC": "思源黑体 · 免费商用",
    "站酷小薇体": "站酷小薇 · 宋韵（免费商用）",
    "ZCOOL XiaoWei": "站酷小薇 · 宋韵（免费商用）",
}

def translate_to_english(text):
    """用本地 Ollama 14B 做中英翻译；失败返回空"""
    text = (text or "").strip()
    if not text:
        return ""
    try:
        import requests
        r = requests.post("http://127.0.0.1:11434/api/generate", json={
            "model": "deepseek-r1:14b",
            "prompt": "Translate the following Chinese into natural English. Translate animal/object words by meaning, not pinyin (e.g. 猫猫 = cat). Output only the English translation: " + text,
            "stream": False,
        }, timeout=120)
        out = (r.json().get("response") or "").strip()
        import re as _re
        out = _re.sub(r"<think>.*?</think>", "", out, flags=_re.S).strip()
        if "<｜end▁of▁thinking｜>" in out:
            out = out.split("<｜end▁of▁thinking｜>")[-1].strip()
        return out
    except Exception:
        return ""


def accent() -> str:
    return theme.THEMES[theme.current_theme()]["accent"]


def make_card(parent=None, alt=False):
    f = QFrame(parent)
    f.setObjectName("CardAlt" if alt else "Card")
    return f


def cover_pixmap(pm: QPixmap, w: int, h: int, anchor_y=0.5) -> QPixmap:
    """等比铺满画布（多余部分裁掉）"""
    if pm.isNull() or w <= 0 or h <= 0:
        return pm
    scaled = pm.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = max(0, (scaled.width() - w) // 2)
    y = max(0, int((scaled.height() - h) * anchor_y))
    return scaled.copy(x, y, w, h)


# ============================================================
#  画布元素
# ============================================================
class TextItem(QGraphicsTextItem):
    def __init__(self, text="点击编辑文字"):
        super().__init__(text)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setDefaultTextColor(QColor("#F5F0E6"))
        f = QFont("Microsoft YaHei UI")
        f.setPixelSize(64)
        self.setFont(f)
        self.setTextWidth(900)
        self.setTextInteractionFlags(Qt.NoTextInteraction)

    def mouseDoubleClickEvent(self, ev):
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setFocus()
        super().mouseDoubleClickEvent(ev)

    def focusOutEvent(self, ev):
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        super().focusOutEvent(ev)


class PhotoItem(QGraphicsPixmapItem):
    def __init__(self, pixmap: QPixmap):
        super().__init__(pixmap)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setTransformationMode(Qt.SmoothTransformation)
        self.kind = "图片"


class CanvasView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setBackgroundBrush(QBrush(QColor("#0B0D11")))
        self.setFrameShape(QFrame.NoFrame)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)


# ============================================================
#  生图 API 设置
# ============================================================
class ImgApiDialog(QDialog):
    """选择免费 Pollinations 或自己的 OpenAI 兼容生图接口"""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("生图 API 设置")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 14)
        lay.setSpacing(10)
        tip = QLabel("默认用 Hugging Face 的 FLUX.1-schnell 免费接口（无需 Key，出图更耐看）；"
                     "Pollinations 作为备用。也可以接智谱 CogView-3-Flash 或豆包 Seedream，填自己的 Key。")
        tip.setObjectName("SubTitle")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(8)
        g.addWidget(QLabel("生图渠道"), 0, 0)
        self.cb = QComboBox()
        self.cb.addItem("Hugging Face · FLUX.1-schnell（免费，无需 Key）", "hf")
        self.cb.addItem("Pollinations · 免费（无需 Key，备用）", "pollinations")
        self.cb.addItem("智谱 CogView-3-Flash · 免费额度（需 Key）", "zhipu")
        self.cb.addItem("豆包 Seedream · 火山方舟（需 Key）", "doubao")
        self.cb.addItem("本地 SDXL 3.5B · 免费（需已部署）", "local")
        self.cb.addItem("自定义 OpenAI 兼容接口", "custom")
        g.addWidget(self.cb, 0, 1, 1, 2)
        g.addWidget(QLabel("接口地址"), 1, 0)
        self.ed_base = QLineEdit()
        g.addWidget(self.ed_base, 1, 1, 1, 2)
        g.addWidget(QLabel("API Key"), 2, 0)
        self.ed_key = QLineEdit()
        self.ed_key.setEchoMode(QLineEdit.Password)
        g.addWidget(self.ed_key, 2, 1, 1, 2)
        g.addWidget(QLabel("模型"), 3, 0)
        self.ed_model = QLineEdit()
        g.addWidget(self.ed_model, 3, 1, 1, 2)
        lay.addLayout(g)
        self.cb.currentIndexChanged.connect(self._sync)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("保存")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(self.save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        # 读取
        prov = db.get_setting("img_provider", "hf")
        self.cb.setCurrentIndex(max(0, self.cb.findData(prov)))
        self.ed_base.setText(db.get_setting("img_base_url", ""))
        self.ed_key.setText(db.get_setting("img_api_key", ""))
        self.ed_model.setText(db.get_setting("img_model", "") or "qwen-image")
        self._sync()

    def _sync(self, *_):
        prov = self.cb.currentData()
        custom = prov == "custom"
        need = prov not in ("pollinations", "hf", "local")
        self.ed_key.setEnabled(need)
        self.ed_model.setEnabled(need)
        self.ed_base.setEnabled(custom)
        if prov == "local":
            self.ed_base.clear(); self.ed_base.setPlaceholderText("本地 SDXL 无需填写")
            self.ed_model.clear(); self.ed_model.setPlaceholderText("本地模型无需填写")
            self.ed_key.clear(); self.ed_key.setPlaceholderText("本地模型无需填写")
        elif prov == "zhipu":
            self.ed_base.setText("https://open.bigmodel.cn/api/paas/v4")
            if "cogview" not in self.ed_model.text().strip():
                self.ed_model.setText("cogview-3-flash")
            self.ed_base.setPlaceholderText("https://open.bigmodel.cn/api/paas/v4")
            self.ed_key.setPlaceholderText("智谱开放平台 API Key")
        elif prov == "doubao":
            self.ed_base.setText("https://ark.cn-beijing.volces.com/api/v3")
            if "doubao" not in self.ed_model.text().strip():
                self.ed_model.setText("doubao-seedream-3-0-t2i-250415")
            self.ed_base.setPlaceholderText("https://ark.cn-beijing.volces.com/api/v3")
            self.ed_key.setPlaceholderText("火山方舟 API Key")
        elif custom:
            self.ed_base.setPlaceholderText("如 https://dashscope.aliyuncs.com/api/v1")
            self.ed_key.setPlaceholderText("接口 Key（可空）")
        else:
            self.ed_base.setPlaceholderText("免费渠道无需填写")
            self.ed_key.setPlaceholderText("免费渠道无需填写")

    def save(self):
        prov = self.cb.currentData() or "hf"
        base = self.ed_base.text().strip()
        model = self.ed_model.text().strip()
        if prov == "local":
            base = ""
            model = "sdxl-local"
        elif prov == "zhipu":
            base = base or "https://open.bigmodel.cn/api/paas/v4"
            model = model or "cogview-3-flash"
        elif prov == "doubao":
            base = base or "https://ark.cn-beijing.volces.com/api/v3"
            model = model or "doubao-seedream-3-0-t2i-250415"
        self.db.set_setting("img_provider", prov)
        self.db.set_setting("img_base_url", base)
        self.db.set_setting("img_api_key", self.ed_key.text().strip())
        self.db.set_setting("img_model", model)
        self.accept()


# ============================================================
#  图文设计页
# ============================================================
class DesignPage(QWidget):
    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.canvas_w, self.canvas_h = 1080, 1440
        self._bg_anchor = 0.5
        self._layers = []
        self._layer_guard = False
        self._build_ui()

    # ---------------- UI ----------------
    def _build_ui(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        # ===== 左：画布 =====
        left = make_card()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(14, 14, 14, 14)
        lv.setSpacing(10)
        top = QHBoxLayout()
        title = QLabel("图文设计")
        title.setObjectName("Title")
        top.addWidget(title)
        top.addStretch()
        self.cb_size = QComboBox()
        self.cb_size.setFixedWidth(150)
        self.cb_size.setEditable(True)
        self.cb_size.setInsertPolicy(QComboBox.NoInsert)
        self.cb_size.addItems(["1080×1440", "1080×1080", "1080×1920", "1920×1080", "1200×1600", "1440×1080"])
        self.cb_size.lineEdit().editingFinished.connect(
            lambda: self.set_size(self.cb_size.currentText()))
        self.cb_size.currentTextChanged.connect(self.set_size)
        top.addWidget(self.cb_size)
        top.addSpacing(10)
        b_jpg = QPushButton("导出 JPG")
        b_jpg.setMinimumWidth(94)
        b_jpg.clicked.connect(lambda: self.export_image("JPG"))
        b_png = QPushButton("导出 PNG")
        b_png.setMinimumWidth(94)
        b_png.setObjectName("Primary")
        b_png.clicked.connect(lambda: self.export_image("PNG"))
        top.addWidget(b_jpg)
        top.addWidget(b_png)
        b_ppt_top = QPushButton("生成 PPT")
        b_ppt_top.setMinimumWidth(94)
        b_ppt_top.clicked.connect(self.export_ppt)
        top.addWidget(b_ppt_top)
        lv.addLayout(top)
        sub = QLabel("文字图层 · 一键排版 · 高清导出 JPG / PNG")
        sub.setObjectName("SubTitle")
        lv.addWidget(sub)

        self.scene = QGraphicsScene(0, 0, self.canvas_w, self.canvas_h)
        self.scene.selectionChanged.connect(self.on_selection)
        self.view = CanvasView(self.scene)
        lv.addWidget(self.view, 1)
        lay.addWidget(left, 1)

        # ===== 右：工具面板 =====
        right = make_card()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(16, 16, 16, 16)
        rv.setSpacing(10)

        # --- 素材与图层 ---
        rv.addWidget(self._section("画布素材"))
        row = QHBoxLayout()
        b_photo = QPushButton("导入图片")
        b_photo.clicked.connect(self.add_photo)
        b_text = QPushButton("添加文字")
        b_text.clicked.connect(self.add_text)
        row.addWidget(b_photo)
        row.addWidget(b_text)
        rv.addLayout(row)
        row2 = QHBoxLayout()
        b_up = QPushButton("上移一层")
        b_up.clicked.connect(lambda: self.bring(1))
        b_dn = QPushButton("下移一层")
        b_dn.clicked.connect(lambda: self.bring(-1))
        b_del = QPushButton("删除选中")
        b_del.setObjectName("Danger")
        b_del.clicked.connect(self.delete_selected)
        row2.addWidget(b_up)
        row2.addWidget(b_dn)
        row2.addWidget(b_del)
        rv.addLayout(row2)

        # 图层列表（上 → 下），点选后可上移/下移
        lb_layer = QLabel("图层（上 → 下）")
        lb_layer.setObjectName("SectionTitle")
        rv.addWidget(lb_layer)
        self.layer_list = QListWidget()
        self.layer_list.setObjectName("Plain")
        self.layer_list.setFixedHeight(140)
        self.layer_list.currentRowChanged.connect(self._on_layer_row)
        rv.addWidget(self.layer_list)
        b_dup = QPushButton("复制选中图层")
        b_dup.clicked.connect(self.duplicate_selected)
        rv.addWidget(b_dup)

        # --- 选中项属性 ---
        rv.addWidget(self._section("选中项属性"))
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(8)
        g.setColumnStretch(1, 1)
        g.addWidget(QLabel("透明度"), 0, 0)
        self.sl_op = QSlider(Qt.Horizontal)
        self.sl_op.setRange(0, 100)
        self.sl_op.setValue(100)
        self.sl_op.valueChanged.connect(self.apply_props)
        g.addWidget(self.sl_op, 0, 1)
        g.addWidget(QLabel("缩放"), 1, 0)
        self.sl_scale = QSlider(Qt.Horizontal)
        self.sl_scale.setRange(20, 300)
        self.sl_scale.setValue(100)
        self.sl_scale.valueChanged.connect(self.apply_props)
        g.addWidget(self.sl_scale, 1, 1)
        g.addWidget(QLabel("字号"), 2, 0)
        self.sp_font = QSpinBox()
        self.sp_font.setRange(12, 240)
        self.sp_font.setValue(64)
        self.sp_font.valueChanged.connect(self.apply_props)
        g.addWidget(self.sp_font, 2, 1)
        g.addWidget(QLabel("字体"), 3, 0)
        self.cb_font = QComboBox()
        self.cb_font.setMinimumWidth(150)
        for fam in (fonts.available_fonts() or ["Microsoft YaHei UI"]):
            self.cb_font.addItem(FONT_LABELS.get(fam, fam), fam)
        self.cb_font.currentIndexChanged.connect(self.apply_props)
        g.addWidget(self.cb_font, 3, 1)
        rv.addLayout(g)

        row3 = QHBoxLayout()
        self.btn_color = QPushButton("文字颜色")
        self.btn_color.clicked.connect(self.pick_color)
        self.btn_center = QPushButton("水平居中")
        self.btn_center.clicked.connect(self.center_selected)
        row3.addWidget(self.btn_color)
        row3.addWidget(self.btn_center)
        rv.addLayout(row3)
        row4 = QHBoxLayout()
        self.btn_vertical = QPushButton("竖排版")
        self.btn_vertical.setCheckable(True)
        self.btn_vertical.clicked.connect(self.toggle_vertical)
        self.btn_shadow = QPushButton("字体阴影")
        self.btn_shadow.setCheckable(True)
        self.btn_shadow.toggled.connect(self.toggle_shadow)
        row4.addWidget(self.btn_vertical)
        row4.addWidget(self.btn_shadow)
        rv.addLayout(row4)
        b_fontfile = QPushButton("导入字体文件（ttf / otf）")
        b_fontfile.clicked.connect(self.import_font_file)
        rv.addWidget(b_fontfile)

        # --- AI 一键出图 ---
        rv.addWidget(self._section("AI 一键生图"))
        self.ed_theme = QPlainTextEdit()
        self.ed_theme.setFixedHeight(84)
        self.ed_theme.setPlaceholderText(
            "主题 / 新人姓名 / 想要的画面，例如：\n陈先生 & 李女士 · 香槟金婚礼 · 大量留白")
        rv.addWidget(self.ed_theme)
        row_tr = QHBoxLayout()
        row_tr.addStretch(1)
        self.btn_tr = QPushButton("一键翻译")
        self.btn_tr.setToolTip("用本地 DeepSeek 14B 把中文主题翻译成英文，再喂给 SDXL")
        self.btn_tr.clicked.connect(self.translate_theme)
        row_tr.addWidget(self.btn_tr)
        rv.addLayout(row_tr)
        row_ai = QHBoxLayout()
        self.btn_ai = QPushButton("一键排版")
        self.btn_ai.setObjectName("Primary")
        self.btn_ai.clicked.connect(self.ai_poster)
        self.btn_gen = QPushButton("文字生图")
        self.btn_gen.clicked.connect(self.gen_image_api)
        row_ai.addWidget(self.btn_ai, 1)
        row_ai.addWidget(self.btn_gen, 1)
        rv.addLayout(row_ai)
        tip_ai = QLabel("「一键翻译」把中文主题转成英文；「文字生图」按主题生成背景。")
        tip_ai.setObjectName("SubTitle")
        tip_ai.setWordWrap(True)
        rv.addWidget(tip_ai)
        row_img = QHBoxLayout()
        self.lb_img = QLabel("")
        self.lb_img.setObjectName("SubTitle")
        self.lb_img.setWordWrap(True)
        row_img.addWidget(self.lb_img, 1)
        b_api = QPushButton("生图 API…")
        b_api.clicked.connect(self.open_img_api)
        row_img.addWidget(b_api)
        rv.addLayout(row_img)
        self.refresh_img_label()

        rv.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(380)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        scroll.setWidget(right)
        lay.addWidget(scroll)

        # 底层画布
        self.base = QGraphicsPixmapItem()
        self._paint_base()
        self.scene.addItem(self.base)
        self.base.setZValue(-100)

        # 删除快捷键
        from PySide6.QtGui import QShortcut, QKeySequence
        sc = QShortcut(QKeySequence(Qt.Key_Delete), self)
        sc.setContext(Qt.WidgetShortcut)
        sc.activated.connect(self.delete_selected)

    @staticmethod
    def _section(text):
        lb = QLabel(text)
        lb.setObjectName("SectionTitle")
        return lb

    # ---------------- 画布底 ----------------
    def _paint_base(self):
        pm = QPixmap(self.canvas_w, self.canvas_h)
        pm.fill(QColor("#FFFFFF"))
        self.base.setPixmap(pm)

    def set_size(self, size_text):
        text = (size_text or "").lower().replace("x", "×").replace("*", "×")
        try:
            w, h = [int(x.strip()) for x in text.split("×")]
        except Exception:
            return
        w = max(200, min(6000, w)); h = max(200, min(6000, h))
        self.canvas_w, self.canvas_h = w, h
        self.cb_size.blockSignals(True)
        self.cb_size.setCurrentText(f"{w}×{h}")
        self.cb_size.blockSignals(False)
        self.scene.setSceneRect(0, 0, w, h)
        self._paint_base()
        self.base.setZValue(-100)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    # ---------------- 图层操作 ----------------
    def add_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        pm = QPixmap(path)
        if pm.isNull():
            QMessageBox.warning(self, "提示", "图片无法读取")
            return
        item = PhotoItem(pm)
        item.kind = "图片 · " + os.path.basename(path)
        if pm.width() > self.canvas_w * 0.7:
            scale = (self.canvas_w * 0.7) / pm.width()
            item.setScale(scale)
        item.setPos((self.canvas_w - pm.width() * item.scale()) / 2,
                    (self.canvas_h - pm.height() * item.scale()) / 2)
        self.scene.addItem(item)
        self._layers.append(item)
        self._restack()
        self.scene.clearSelection()
        item.setSelected(True)
        self.refresh_layers()

    def add_text(self):
        item = TextItem("婚礼主题 · 点击编辑")
        fam = self.cb_font.currentData() or self.cb_font.currentText()
        if fam:
            f = item.font()
            f.setFamily(fam)
            item.setFont(f)
        item.kind = "文字 · 婚礼主题"
        item.setPos(120, self.canvas_h // 2 - 120)
        item.setTextInteractionFlags(Qt.NoTextInteraction)
        self.scene.addItem(item)
        self._layers.append(item)
        self._restack()
        self.scene.clearSelection()
        item.setSelected(True)
        self.refresh_layers()

    def _restack(self):
        if getattr(self, "base", None):
            self.base.setZValue(-100)
        for i, it in enumerate(self._layers):
            it.setZValue(10 + i * 10)

    def refresh_layers(self):
        if not hasattr(self, "layer_list"):
            return
        self._layer_guard = True
        self.layer_list.clear()
        current = self.scene.selectedItems()
        cur = current[0] if current else None
        for it in reversed(self._layers):
            if isinstance(it, QGraphicsTextItem):
                t = it.toPlainText().strip().replace("\n", " ")[:16] or "文字"
                label = "文字 · " + t
            else:
                label = getattr(it, "kind", None) or "图片"
            row = QListWidgetItem(label)
            row.setData(Qt.UserRole, it)
            self.layer_list.addItem(row)
            if it is cur:
                self.layer_list.setCurrentRow(self.layer_list.count() - 1)
        self._layer_guard = False

    def _on_layer_row(self, row):
        if self._layer_guard or row < 0:
            return
        it = self.layer_list.item(row)
        if not it:
            return
        obj = it.data(Qt.UserRole)
        self._layer_guard = True
        self.scene.clearSelection()
        obj.setSelected(True)
        self.view.ensureVisible(obj)
        self._layer_guard = False

    def bring(self, delta):
        items = [it for it in self.scene.selectedItems() if it is not self.base]
        if not items:
            return
        it = items[0]
        if it not in self._layers:
            return
        i = self._layers.index(it)
        j = max(0, min(len(self._layers) - 1, i + delta))
        if i == j:
            return
        self._layers[i], self._layers[j] = self._layers[j], self._layers[i]
        self._restack()
        self.refresh_layers()
        it.setSelected(True)
        self.view.viewport().update()

    def delete_selected(self):
        for it in list(self.scene.selectedItems()):
            if it is self.base:
                continue
            if it in self._layers:
                self._layers.remove(it)
            self.scene.removeItem(it)
        self._restack()
        self.refresh_layers()

    def duplicate_selected(self):
        items = [it for it in self.scene.selectedItems() if it is not self.base]
        if not items:
            return
        it = items[0]
        if isinstance(it, QGraphicsTextItem):
            new = TextItem(it.toPlainText())
            new.setFont(it.font())
            new.setDefaultTextColor(it.defaultTextColor())
            if it.textWidth() > 0:
                new.setTextWidth(it.textWidth())
            new.kind = "文字 · " + it.toPlainText()[:12]
        elif isinstance(it, PhotoItem):
            new = PhotoItem(it.pixmap())
            new.kind = it.kind
        else:
            return
        new.setPos(it.pos() + QPointF(24, 24))
        new.setScale(it.scale())
        new.setOpacity(it.opacity())
        new.setTextInteractionFlags(Qt.NoTextInteraction)
        self.scene.addItem(new)
        self._layers.append(new)
        self._restack()
        self.scene.clearSelection()
        new.setSelected(True)
        self.refresh_layers()

    def on_selection(self):
        if getattr(self, "scene", None) is None:
            return
        try:
            items = self.scene.selectedItems()
        except RuntimeError:
            return
        if not items:
            self.refresh_layers()
            return
        it = items[0]
        self.refresh_layers()
        self.sl_op.blockSignals(True)
        self.sl_scale.blockSignals(True)
        self.sl_op.setValue(int(it.opacity() * 100))
        self.sl_scale.setValue(int(it.scale() * 100))
        if isinstance(it, QGraphicsTextItem):
            self.sp_font.blockSignals(True)
            self.sp_font.setValue(max(12, it.font().pixelSize()))
            self.sp_font.blockSignals(False)
            self.cb_font.blockSignals(True)
            fam = it.font().family()
            idx = self.cb_font.findData(fam)
            if idx < 0:
                idx = self.cb_font.findText(fam)
            if idx >= 0:
                self.cb_font.setCurrentIndex(idx)
            self.cb_font.blockSignals(False)
        self.sl_op.blockSignals(False)
        self.sl_scale.blockSignals(False)

    def apply_props(self):
        items = self.scene.selectedItems()
        if not items:
            return
        it = items[0]
        it.setOpacity(self.sl_op.value() / 100)
        it.setScale(self.sl_scale.value() / 100)
        if isinstance(it, QGraphicsTextItem):
            f = it.font()
            f.setPixelSize(self.sp_font.value())
            fam = self.cb_font.currentData() or self.cb_font.currentText()
            if fam:
                f.setFamily(fam)
            it.setFont(f)

    def pick_color(self):
        items = self.scene.selectedItems()
        if not items or not isinstance(items[0], QGraphicsTextItem):
            QMessageBox.information(self, "提示", "请先选中一个文字图层")
            return
        c = QColorDialog.getColor(items[0].defaultTextColor(), self, "选择文字颜色")
        if c.isValid():
            items[0].setDefaultTextColor(c)

    def center_selected(self):
        items = self.scene.selectedItems()
        if not items:
            return
        it = items[0]
        br = it.sceneBoundingRect()
        it.setPos(it.pos().x() + (self.canvas_w - br.width()) / 2 - br.x(), it.pos().y())

    def toggle_vertical(self, on):
        items = [it for it in self.scene.selectedItems() if isinstance(it, TextItem)]
        if not items:
            QMessageBox.information(self, "提示", "请先选中一个文字图层")
            self.btn_vertical.setChecked(False)
            return
        for it in items:
            txt = it.toPlainText()
            if on:
                it.setPlainText("\n".join(txt.replace("\n", "")))
            else:
                it.setPlainText(txt.replace("\n", ""))

    def toggle_shadow(self, on):
        items = [it for it in self.scene.selectedItems() if isinstance(it, TextItem)]
        if not items:
            self.btn_shadow.blockSignals(True)
            self.btn_shadow.setChecked(False)
            self.btn_shadow.blockSignals(False)
            return
        for it in items:
            if on:
                eff = QGraphicsDropShadowEffect()
                eff.setBlurRadius(16)
                eff.setOffset(5, 6)
                eff.setColor(QColor(0, 0, 0, 170))
                it.setGraphicsEffect(eff)
            else:
                it.setGraphicsEffect(None)

    def import_font_file(self):
        from PySide6.QtGui import QFontDatabase
        path, _ = QFileDialog.getOpenFileName(self, "导入字体", "", "字体文件 (*.ttf *.otf *.ttc)")
        if not path:
            return
        fid = QFontDatabase.addApplicationFont(path)
        if fid < 0:
            QMessageBox.warning(self, "导入失败", "字体文件无法识别")
            return
        fams = QFontDatabase.applicationFontFamilies(fid)
        for fam in fams:
            if self.cb_font.findData(fam) < 0:
                self.cb_font.addItem(fam, fam)
        if fams:
            self.cb_font.setCurrentIndex(self.cb_font.findData(fams[0]))
        QMessageBox.information(self, "已导入", "字体已加入下拉框，选中文字图层即可应用。")

    # ---------------- AI 一键排版 ----------------
    PALETTES = {
        "香槟金·优雅": ("#15171E", "#2A2418", "#C9A86A", "#F5EFE6"),
        "赤金·喜庆": ("#2A0E10", "#5C1616", "#E2B15C", "#FFF2DE"),
        "极简白·高级": ("#F4F1EC", "#E7E1D8", "#8B7B5E", "#2C2A26"),
        "森系绿·清新": ("#12231B", "#1E3A2C", "#A9C79A", "#F2F6ED"),
        "夜幕·浪漫": ("#0C1020", "#1A2140", "#C7B7E8", "#F0ECFA"),
    }

    def _ai_copy(self, theme_text, style):
        bg1, bg2, acc, fg = self.PALETTES.get(style, self.PALETTES["香槟金·优雅"])
        data = {"title": theme_text if len(theme_text) <= 12 else theme_text[:12],
                "subtitle": "WEDDING CEREMONY",
                "blessing": "愿此后余生，皆有良人相伴，岁岁欢愉，年年胜意。",
                "accent": acc, "fg": fg, "bg1": bg1, "bg2": bg2}
        base = self.db.get_setting("ai_base_url", "") if self.db else ""
        if not base:
            return data
        prompt = (
            "你是婚礼视觉设计师，请为婚礼海报写文案。"
            f"主题：{theme_text}；风格：{style}。"
            '只输出 JSON，不要任何解释，格式：'
            '{"title":"主标题(不超过8个字)","subtitle":"英文副标(不超过4个单词)",'
            '"blessing":"祝福语(不超过25个字)"}'
        )
        try:
            txt = common.call_ai(base, self.db.get_setting("ai_api_key", ""),
                                 self.db.get_setting("ai_model", "") or "deepseek-chat",
                                 prompt, timeout=25)
            j = txt[txt.find("{"): txt.rfind("}") + 1]
            obj = json.loads(j)
            for k in ("title", "subtitle", "blessing"):
                if obj.get(k):
                    data[k] = str(obj[k])
        except Exception:
            logger.warning("AI 出图文案失败，使用内置文案", exc_info=True)
        return data

    def ai_poster(self):
        theme_text = self.ed_theme.toPlainText().strip() or "我们的婚礼"
        style = "极简白·高级"
        self._ai_style = style
        self.btn_ai.setEnabled(False)
        self.btn_ai.setText("生成中…")
        QApplication.processEvents()
        try:
            data = self._ai_copy(theme_text, style)
            self._render_poster(data)
        finally:
            self.btn_ai.setEnabled(True)
            self.btn_ai.setText("一键排版")

    def _render_poster(self, d):
        d = dict(d or {})
        pal = self.PALETTES.get(getattr(self, "_ai_style", ""), self.PALETTES["香槟金·优雅"])
        for k, i in (("bg1", 0), ("bg2", 1), ("accent", 2), ("fg", 3)):
            d.setdefault(k, pal[i])
        d.setdefault("title", self.ed_theme.toPlainText().strip() or "婚礼邀请")
        d.setdefault("subtitle", "WEDDING INVITATION")
        d.setdefault("blessing", "愿以此生，护你周全")
        w, h = self.canvas_w, self.canvas_h
        pm = QPixmap(w, h)
        pm.fill(QColor(d["bg1"]))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, w * 0.4, h)
        grad.setColorAt(0, QColor(d["bg1"]))
        grad.setColorAt(1, QColor(d["bg2"]))
        p.fillRect(pm.rect(), grad)
        rg = QRadialGradient(w * 0.5, h * 0.34, w * 0.62)
        c = QColor(d["accent"])
        c.setAlpha(46)
        rg.setColorAt(0, c)
        c2 = QColor(d["accent"])
        c2.setAlpha(0)
        rg.setColorAt(1, c2)
        p.fillRect(pm.rect(), rg)
        pen = QPen(QColor(d["accent"]))
        pen.setWidth(max(2, int(w / 540)))
        p.setPen(pen)
        m = int(w * 0.055)
        p.drawRect(m, m, w - 2 * m, h - 2 * m)
        pen2 = QPen(QColor(d["accent"]), 1)
        p.setPen(pen2)
        m2 = m + int(w * 0.012)
        p.drawRect(m2, m2, w - 2 * m2, h - 2 * m2)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(d["accent"]))
        cx, top = w // 2, int(h * 0.14)
        p.drawPolygon(QPolygonF([QPointF(cx, top - 9), QPointF(cx + 9, top),
                                 QPointF(cx, top + 9), QPointF(cx - 9, top)]))
        p.setPen(pen2)
        p.drawLine(int(w * 0.3), int(h * 0.47), int(w * 0.7), int(h * 0.47))
        p.end()
        self.base.setPixmap(pm)
        self.base.setZValue(-100)

        for it in getattr(self, "_gen_items", []):
            try:
                self.scene.removeItem(it)
            except Exception:
                pass
        self._gen_items = []
        fam = self.cb_font.currentData() or self.cb_font.currentText() or "Microsoft YaHei UI"
        specs = [
            (d["title"], int(h * 0.062), True, d["fg"], h * 0.245),
            (d["subtitle"], int(h * 0.026), False, d["accent"], h * 0.385),
            (d["blessing"], int(h * 0.027), False, d["fg"], h * 0.72),
            (datetime.date.today().strftime("%Y . %m . %d"), int(h * 0.022), False,
             d["accent"], h * 0.855),
        ]
        for text, size, bold, color, y in specs:
            it = TextItem(text)
            f = QFont(fam)
            f.setPixelSize(size)
            f.setBold(bold)
            f.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
            it.setFont(f)
            it.setDefaultTextColor(QColor(color))
            it.setTextInteractionFlags(Qt.NoTextInteraction)
            if text is d["blessing"] or text == d["blessing"]:
                it.setTextWidth(w * 0.74)
                opt = QTextOption()
                opt.setAlignment(Qt.AlignHCenter)
                it.document().setDefaultTextOption(opt)
            it.setZValue(50)
            self.scene.addItem(it)
            it.setPos((w - it.boundingRect().width()) / 2, y)
            self._gen_items.append(it)
        self.scene.clearSelection()

    # ---------------- 文字生图 ----------------
    def _img_provider(self):
        if not self.db:
            return "hf"
        return self.db.get_setting("img_provider", "hf") or "hf"

    def refresh_img_label(self):
        if not hasattr(self, "lb_img"):
            return
        prov = self._img_provider()
        names = {"hf": "FLUX.1-schnell · 免费（无需 Key）",
                 "pollinations": "Pollinations 免费（备用）",
                 "zhipu": "智谱 CogView-3-Flash（免费额度，需 Key）",
                 "doubao": "豆包 Seedream（需 Key）",
                 "custom": "自定义接口",
                 "local": "本地 SDXL 3.5B"}
        text = "生图：" + names.get(prov, prov)
        if prov not in ("hf", "pollinations", "local"):
            model = self.db.get_setting("img_model", "") if self.db else ""
            if model:
                text += f" · {model}"
        if os.path.exists(r"D:\ComfyUI\models\checkpoints\sd_xl_base_1.0.safetensors"):
            text += " · 本地 SDXL 已检测"
        self.lb_img.setText(text)

    def open_img_api(self):
        if not self.db:
            return
        dlg = ImgApiDialog(self.db, self)
        if dlg.exec():
            self.refresh_img_label()

    def _style_pair(self):
        return ("高级婚礼", "elegant luxury wedding")

    def translate_theme(self):
        txt = self.ed_theme.toPlainText().strip()
        if not txt:
            return
        self.btn_tr.setEnabled(False)
        self.btn_tr.setText("翻译中…")
        QApplication.processEvents()
        out = translate_to_english(txt)
        self.btn_tr.setEnabled(True)
        self.btn_tr.setText("一键翻译")
        if out:
            self.ed_theme.setPlainText(out)
        else:
            QMessageBox.warning(self, "翻译失败", "本地 DeepSeek 14B 没有返回结果，请确认 Ollama 正在运行。")

    def gen_image_api(self):
        provider = self._img_provider()
        theme_text = self.ed_theme.toPlainText().strip()
        style_cn, style_en = self._style_pair()
        en_prompt = ("Luxury wedding editorial background, " + style_en +
                     ", soft cinematic light, elegant fine art photography, "
                     "large clean negative space at the top for text, "
                     "no people, no text, no watermark, ultra detailed, 8k")
        self.btn_gen.setEnabled(False)
        self.btn_gen.setText("生成中…")
        QApplication.processEvents()
        try:
            import requests
            pm = QPixmap()
            if provider == "hf":
                if self.canvas_h >= self.canvas_w:
                    w = 768
                    h = max(640, min(1152, int(768 * self.canvas_h / max(1, self.canvas_w))))
                else:
                    h = 768
                    w = max(640, min(1152, int(768 * self.canvas_w / max(1, self.canvas_h))))
                data = self._gen_hf_flux(en_prompt, w, h)
                pm.loadFromData(data)
                if pm.isNull():
                    from PIL import Image
                    import io as _io
                    pm = QPixmap.fromImage(QImage.fromData(data, "WEBP"))
                if pm.isNull():
                    raise RuntimeError("FLUX 返回的图片无法读取")
                self.base.setPixmap(cover_pixmap(pm, self.canvas_w, self.canvas_h))
                QMessageBox.information(
                    self, "生图完成",
                    "已用 FLUX.1-schnell（免费）生成并铺为画布背景；"
                    "不满意可以换「风格」或再生成一次。")
            elif provider == "pollinations":
                from urllib.parse import quote
                w = 1024
                h = int(1024 * self.canvas_h / max(1, self.canvas_w))
                h = max(512, min(1792, h))
                seed = random.randint(1, 999999)
                data = None
                last_err = None
                for model in ("flux", "turbo"):
                    url = ("https://image.pollinations.ai/prompt/" + quote(en_prompt) +
                           f"?width={w}&height={h}&nologo=true&model={model}&seed={seed}")
                    try:
                        r = requests.get(url, timeout=55,
                                         headers={"User-Agent": "HostWorkbench/3.5"})
                        if r.ok and len(r.content) > 1000:
                            data = r.content
                            break
                        last_err = RuntimeError(f"HTTP {r.status_code}")
                    except Exception as e:
                        last_err = e
                if not data:
                    raise RuntimeError(f"免费接口没有返回图片（{last_err}）")
                pm.loadFromData(data)
                if pm.isNull():
                    raise RuntimeError("免费接口返回的不是图片")
                pm = pm.copy(0, 0, pm.width(), max(1, int(pm.height() * 0.94)))
                self.base.setPixmap(cover_pixmap(pm, self.canvas_w, self.canvas_h))
                QMessageBox.information(
                    self, "生图完成",
                    "已用 Pollinations 免费接口生成并铺为画布背景；"
                    "不满意可以换个「风格」再生成一次。")
            elif provider == "local":
                model_path = r"D:\ComfyUI\models\checkpoints\sd_xl_base_1.0.safetensors"
                py_path = r"D:\Python311\python.exe"
                script = r"D:\SDXL\gen_once.py"
                if not (os.path.exists(model_path) and os.path.exists(py_path) and os.path.exists(script)):
                    raise RuntimeError("未检测到本地 SDXL，请确认 D:/ComfyUI 模型与 D:/Python311 已部署")
                out = os.path.join(data_dir(), "sdxl_design_tmp.png")
                prompt = (theme_text or "婚礼") + f"，{style_cn}，婚礼海报背景，高级留白，细腻光影，无人物，无文字，无水印"
                proc = subprocess.Popen([py_path, script, "--prompt", prompt, "--out", out,
                                         "--steps", "8", "--size", "1024"],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                dlg = QProgressDialog("本地 SDXL 生成中…（CPU 可能较慢）", "取消", 0, 0, self)
                dlg.setWindowTitle("本地生图")
                dlg.setWindowModality(Qt.WindowModal)
                dlg.setMinimumDuration(0)
                dlg.show()
                while proc.poll() is None:
                    QApplication.processEvents()
                    if dlg.wasCanceled():
                        proc.kill()
                        break
                    time.sleep(0.2)
                dlg.close()
                if proc.returncode not in (0, None):
                    err = (proc.stderr.read() or b"").decode("utf-8", "ignore")[-400:]
                    raise RuntimeError("本地生成失败：" + (err or f"退出码 {proc.returncode}"))
                if not os.path.exists(out):
                    raise RuntimeError("本地生成没有输出文件")
                pm.load(out)
                if pm.isNull():
                    raise RuntimeError("本地输出的图片无法读取")
                self.base.setPixmap(cover_pixmap(pm, self.canvas_w, self.canvas_h))
                QMessageBox.information(self, "生图完成", "已用本地 SDXL 生成并铺为画布背景。")
            else:
                if provider == "zhipu":
                    base = "https://open.bigmodel.cn/api/paas/v4"
                    model = "cogview-3-flash"
                    key = get_setting("img_api_key", "")
                elif provider == "doubao":
                    base = "https://ark.cn-beijing.volces.com/api/v3"
                    model = "doubao-seedream-3-0-t2i-250415"
                    key = get_setting("img_api_key", "")
                else:
                    base = get_setting("img_base_url", "")
                    key = get_setting("img_api_key", "")
                    model = get_setting("img_model", "") or "qwen-image"
                if not key:
                    QMessageBox.information(
                        self, "还需要 Key",
                        "智谱 CogView-3-Flash 有免费额度、豆包 Seedream 需开通，"
                        "请先在「生图 API…」里填自己的 Key；不想填 Key 可以直接用免费的 Pollinations。")
                    return
                if not base:
                    QMessageBox.information(
                        self, "未配置生图接口",
                        "请在「生图 API…」里填写接口地址、Key 与模型，或切回免费的 Pollinations。")
                    return
                prompt = (theme_text or "婚礼") + f"，{style_cn}，婚礼海报背景，" \
                         "高级留白，细腻光影，无人物，无文字，无水印，高清"
                url = base.rstrip("/")
                if not url.endswith("/images/generations"):
                    url += "/images/generations"
                headers = {"Content-Type": "application/json",
                           "Authorization": "Bearer " + key}
                r = requests.post(url, headers=headers, json={
                    "model": model, "prompt": prompt, "n": 1,
                    "size": "1024x1024", "response_format": "url",
                }, timeout=120)
                r.raise_for_status()
                data = r.json()
                item = (data.get("data") or [{}])[0]
                if item.get("b64_json"):
                    import base64
                    pm.loadFromData(base64.b64decode(item["b64_json"]))
                elif item.get("url"):
                    r2 = requests.get(item["url"], timeout=90)
                    r2.raise_for_status()
                    pm.loadFromData(r2.content)
                if pm.isNull():
                    raise RuntimeError("返回里没有可用的图片数据")
                self.base.setPixmap(cover_pixmap(pm, self.canvas_w, self.canvas_h))
                QMessageBox.information(self, "生图完成", "已铺为画布背景，可继续加文字排版。")
        except Exception as e:
            if provider == "local":
                extra = "\n\n本地 SDXL 在 780M 核显上只能 CPU 运行，512×512/6 步可能需要数分钟；急用建议切回 FLUX/Pollinations。"
            elif provider == "pollinations":
                extra = "\n\n免费接口可能较慢或被网络拦截；可在「生图 API…」里换智谱 CogView-3-Flash（免费额度）或自己的接口。"
            else:
                extra = "\n\n请核对 Key、模型名与接口地址（智谱 CogView-3-Flash / 豆包 Seedream）。"
            QMessageBox.warning(self, "生图失败", f"{e}{extra}")
        finally:
            self.btn_gen.setEnabled(True)
            self.btn_gen.setText("文字生图")

    # ---------------- 导出 ----------------
    def _canvas_image(self, fmt="PNG"):
        img = QImage(self.canvas_w, self.canvas_h, QImage.Format_ARGB32)
        img.fill(QColor("#FFFFFF") if fmt == "JPG" else Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        self.scene.clearSelection()
        self.scene.render(p, QRectF(0, 0, self.canvas_w, self.canvas_h),
                          QRectF(0, 0, self.canvas_w, self.canvas_h))
        p.end()
        return img

    def export_image(self, fmt="PNG"):
        default = os.path.join(
            data_dir(),
            f"图文设计_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt.lower()}")
        flt = "JPG 图片 (*.jpg)" if fmt == "JPG" else "PNG 图片 (*.png)"
        path, _ = QFileDialog.getSaveFileName(self, f"导出 {fmt}", default, flt)
        if not path:
            return
        if not path.lower().endswith((".jpg", ".jpeg", ".png")):
            path += "." + fmt.lower()
        img = self._canvas_image(fmt)
        ok = img.save(path, fmt)
        if ok:
            QMessageBox.information(self, "导出成功", f"已保存（{fmt}）：\n{path}")
        else:
            QMessageBox.warning(self, "导出失败", "文件写入失败，请检查路径")

    def export_ppt(self, out_path=None, silent=False):
        """把当前画面 + 文案 + 流程生成 16:9 提案 PPT"""
        try:
            from pptx import Presentation
            from pptx.util import Inches, Pt
            from pptx.dml.color import RGBColor
            from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
            from pptx.enum.shapes import MSO_SHAPE
        except Exception as e:
            QMessageBox.warning(self, "缺少组件", f"PPT 组件不可用：{e}")
            return
        theme_text = self.ed_theme.toPlainText().strip()
        texts = []
        for it in self._layers:
            if isinstance(it, QGraphicsTextItem):
                t = it.toPlainText().strip()
                if t:
                    texts.append((it.y(), t))
        texts.sort(key=lambda x: x[0])
        title = theme_text.splitlines()[0].strip() if theme_text else "我们的婚礼"
        if not title:
            title = "我们的婚礼"
        flows = []
        if self.db is not None:
            try:
                flows = self.db.prep_flow()
            except Exception:
                flows = []
        default = os.path.join(
            data_dir(), f"婚礼提案_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.pptx")
        if out_path is None:
            path, _ = QFileDialog.getSaveFileName(self, "生成提案 PPT", default,
                                                  "PowerPoint (*.pptx)")
            if not path:
                return
            if not path.lower().endswith(".pptx"):
                path += ".pptx"
        else:
            path = out_path
            if not path.lower().endswith(".pptx"):
                path += ".pptx"
        # 封面图
        cover_path = os.path.join(data_dir(), "cache", "_ppt_cover.png")
        os.makedirs(os.path.dirname(cover_path), exist_ok=True)
        self._canvas_image("PNG").save(cover_path, "PNG")

        gold = RGBColor(0xB0, 0x8D, 0x57)
        dark = RGBColor(0x2A, 0x26, 0x22)
        grey = RGBColor(0x6B, 0x62, 0x58)
        ivory = RGBColor(0xFB, 0xF8, 0xF3)
        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        blank = prs.slide_layouts[6]

        def bg(slide):
            bgshape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0,
                                             prs.slide_width, prs.slide_height)
            bgshape.fill.solid()
            bgshape.fill.fore_color.rgb = ivory
            bgshape.line.fill.background()
            line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.55), Inches(0.55),
                                          Inches(12.23), Inches(0.02))
            line.fill.solid()
            line.fill.fore_color.rgb = gold
            line.line.fill.background()

        def txt(slide, left, top, width, height, text, size=20, color=dark,
                bold=False, align=PP_ALIGN.LEFT, font="微软雅黑"):
            box = slide.shapes.add_textbox(left, top, width, height)
            tf = box.text_frame
            tf.word_wrap = True
            tf.vertical_anchor = MSO_ANCHOR.TOP
            tf.text = text
            for p in tf.paragraphs:
                p.alignment = align
                for r in p.runs:
                    r.font.size = Pt(size)
                    r.font.bold = bold
                    r.font.color.rgb = color
                    r.font.name = font
            return box

        # 1 封面
        s1 = prs.slides.add_slide(blank)
        bg(s1)
        txt(s1, Inches(0.9), Inches(0.95), Inches(7.4), Inches(0.5),
            "WEDDING PROPOSAL", 13, gold, True)
        txt(s1, Inches(0.9), Inches(1.5), Inches(7.0), Inches(2.2),
            title, 34, dark, True)
        txt(s1, Inches(0.9), Inches(3.4), Inches(6.6), Inches(2.2),
            "一场婚礼的提案\n主题 · 文案 · 流程 · 画面", 18, grey)
        txt(s1, Inches(0.9), Inches(6.55), Inches(7.0), Inches(0.4),
            datetime.date.today().strftime("%Y.%m.%d"), 12, gold)
        pic = s1.shapes.add_picture(cover_path, Inches(8.35), Inches(0.7),
                                    height=Inches(6.1))
        if pic.width > Inches(4.3):
            ratio = Inches(4.3) / pic.width
            pic.width = int(pic.width * ratio)
            pic.height = int(pic.height * ratio)
            pic.left = Inches(8.5)
            pic.top = Inches(0.9)

        # 2 主题文案
        s2 = prs.slides.add_slide(blank)
        bg(s2)
        txt(s2, Inches(0.9), Inches(0.9), Inches(8.0), Inches(0.6),
            "01  主题文案", 22, gold, True)
        body = "\n".join(t for _, t in texts[:6]) or theme_text or \
            "把两个人的故事，写成一段可以站在台上说出来的话。"
        txt(s2, Inches(0.9), Inches(1.75), Inches(11.5), Inches(5.0),
            body, 18, dark)
        txt(s2, Inches(11.9), Inches(6.9), Inches(0.8), Inches(0.3), "2", 11, grey)

        # 3 仪式流程
        s3 = prs.slides.add_slide(blank)
        bg(s3)
        txt(s3, Inches(0.9), Inches(0.9), Inches(8.0), Inches(0.6),
            "02  仪式流程", 22, gold, True)
        if flows:
            y = 1.7
            for r in flows[:8]:
                tm = (r.get("time") or "").strip()
                name = (r.get("title") or "").strip()
                loc = (r.get("location") or "").strip()
                txt(s3, Inches(0.95), Inches(y), Inches(2.2), Inches(0.4),
                    tm or "—", 16, gold, True)
                txt(s3, Inches(3.1), Inches(y), Inches(7.4), Inches(0.4),
                    name or "待定", 16, dark, True)
                if loc:
                    txt(s3, Inches(10.4), Inches(y), Inches(2.3), Inches(0.4),
                        loc, 12, grey)
                y += 0.62
        else:
            txt(s3, Inches(0.9), Inches(1.8), Inches(11.0), Inches(1.0),
                "流程待定：可在「备婚工具 → 流程清单」补全后重新生成。", 16, grey)
        txt(s3, Inches(11.9), Inches(6.9), Inches(0.8), Inches(0.3), "3", 11, grey)

        # 4 结尾
        s4 = prs.slides.add_slide(blank)
        bg(s4)
        txt(s4, Inches(0.9), Inches(2.2), Inches(11.5), Inches(0.8),
            "把这场婚礼，交给一个懂你们的人", 28, dark, True, PP_ALIGN.CENTER)
        txt(s4, Inches(0.9), Inches(3.3), Inches(11.5), Inches(1.2),
            "主持人提案 · 期待与你们一起完成", 18, grey, False, PP_ALIGN.CENTER)
        txt(s4, Inches(0.9), Inches(5.9), Inches(11.5), Inches(0.4),
            title, 13, gold, False, PP_ALIGN.CENTER)

        try:
            prs.save(path)
        except Exception as e:
            QMessageBox.warning(self, "导出失败", f"PPT 写入失败：{e}")
            return
        if not silent:
            QMessageBox.information(self, "PPT 已生成",
                                    f"已生成 4 页提案 PPT：\n{path}\n\n可直接用 PowerPoint 打开修改。")

