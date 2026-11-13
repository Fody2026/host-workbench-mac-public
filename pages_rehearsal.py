# -*- coding: utf-8 -*-
"""预演沙盘：真实宴会厅底图 + 3D 人物 + 动线 + 时间轴 + 全屏 + PNG/MP4 导出"""
import os
import re
import json
import math
import copy
import time
import shutil
import tempfile
import datetime
import logging
import subprocess

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, Signal, QTimer, QRect
from PySide6.QtGui import (QPainter, QPen, QBrush, QColor, QPixmap, QImage, QFont,
                           QIcon, QPolygonF, QRadialGradient, QLinearGradient,
                           QPainterPath)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
    QComboBox, QLineEdit, QSpinBox, QSlider, QCheckBox, QListWidget, QListWidgetItem,
    QTabWidget, QScrollArea, QFileDialog, QMessageBox, QProgressDialog,
    QAbstractItemView, QSizePolicy, QGraphicsDropShadowEffect, QApplication
)

import common
import theme
from common import data_dir, asset_path

logger = logging.getLogger(__name__)

SCENE_W, SCENE_H = 1600, 1200
HALL_DIR = os.path.join("sandbox", "hall")
PEOPLE_DIR = os.path.join("sandbox", "people")
PROPS_DIR = os.path.join("sandbox", "props")

ROLES = ["新郎", "新娘", "司仪", "伴郎", "伴娘", "父母", "长辈", "花童", "宠物",
         "跟妆", "督导", "摄影", "摄像", "音控", "新人组", "父母组", "长辈组"]
ROLE_MODEL = {"新郎": "p12", "新娘": "p11", "司仪": "p01", "伴郎": "p03", "伴娘": "p02",
              "父母": "p16", "长辈": "p14", "督导": "p01", "摄影": "p10",
              "摄像": "p10", "音控": "p01", "花童": "p18", "宠物": "p06",
              "跟妆": "p19", "新人组": "p13", "父母组": "p17", "长辈组": "p15",
              "圆桌": "f01", "长条桌": "f02", "长条凳": "f03"}
FURNITURE_ROLES = {"圆桌", "长条桌", "长条凳"}
FURN_SCALE = {"圆桌": 1.35, "长条桌": 1.05, "长条凳": 0.55}
SEG_COLORS = ["#C9A86A", "#A98E63", "#8E7A55", "#B79A6B", "#97794F", "#C2A578"]

LAYOUT_FILE = os.path.join(data_dir(), "sandbox_layout.json")


def accent():
    return theme.THEMES[theme.current_theme()]["accent"]


def accent_dim():
    t = theme.THEMES[theme.current_theme()]
    return t.get("accent_hover", t["accent"])


def make_card(parent=None, alt=False):
    f = QFrame(parent)
    f.setObjectName("CardAlt" if alt else "Card")
    return f


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def parse_minutes(text):
    m = re.match(r"^\s*(\d{1,2})[:：](\d{2})", str(text or ""))
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return h * 60 + mi


def fmt_mmss(sec):
    sec = max(0, int(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"


# ============================================================
#  3D 人物模型库
# ============================================================
class ModelLib:
    def __init__(self):
        self.halls = []
        self.models = []
        self._pm = {}
        self.reload()

    def reload(self):
        self.halls = load_json(asset_path(os.path.join(HALL_DIR, "index.json")), [])
        people = load_json(asset_path(os.path.join(PEOPLE_DIR, "index.json")), [])
        props = load_json(asset_path(os.path.join(PROPS_DIR, "index.json")), [])
        for p in people:
            p.setdefault("kind", "person")
        self.models = people + props
        self._pm.clear()

    def hall_path(self, hid):
        for h in self.halls:
            if h["id"] == hid:
                return asset_path(os.path.join(HALL_DIR, h["file"]))
        return asset_path(os.path.join(HALL_DIR, "hall1.jpg"))

    def hall_thumb(self, hid):
        return asset_path(os.path.join(HALL_DIR, "thumbs", hid + ".jpg"))

    def model(self, mid):
        for m in self.models:
            if m["id"] == mid:
                return m
        return self.models[0] if self.models else {"id": "p01", "file": "p01.png", "name": "人物"}

    def model_pm(self, mid):
        if mid not in self._pm:
            m = self.model(mid)
            d = PROPS_DIR if m.get("kind") == "prop" else PEOPLE_DIR
            pm = QPixmap(asset_path(os.path.join(d, m["file"])))
            self._pm[mid] = pm
        return self._pm[mid]

    def model_thumb(self, mid):
        pm = self.model_pm(mid)
        if pm.isNull():
            return QIcon()
        return QIcon(pm.scaled(72, 112, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def model_id_for_role(self, role):
        return ROLE_MODEL.get(role, "p01")


# ============================================================
#  沙盘画布
# ============================================================
class SandboxCanvas(QWidget):
    actorSelected = Signal(int)
    sceneEdited = Signal()
    editStarted = Signal()
    progressChanged = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(560, 420)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.models = ModelLib()
        self.hall_id = "hall1"
        self.bg_anchor = 0.34
        self.blur = 0.0
        self.dim = 18
        self.show_grid = False
        self.actors = []
        self.sel = -1
        self.path_mode = False
        self.progress = 0.0
        self.phase_count = 1
        self.current_phase = 0
        self._bg_src = QPixmap()
        self._bg = QPixmap()
        self._backdrop = QPixmap()
        self._drag = None
        self._load_hall(self.hall_id)

    # ---------- 底图 ----------
    def _load_hall(self, hid):
        self.hall_id = hid
        pm = QPixmap(self.models.hall_path(hid))
        self._bg_src = pm
        self._rebuild_bg()

    def set_hall(self, hid):
        if hid and hid != self.hall_id:
            self._load_hall(hid)
            self.update()

    def _rebuild_bg(self):
        pm = self._bg_src
        if pm.isNull():
            self._bg = QPixmap(SCENE_W, SCENE_H)
            self._bg.fill(QColor("#14161C"))
            return
        # 先做柔化（缩图再放大，快且自然）
        if self.blur > 0.3:
            f = int(4 + self.blur * 1.6)
            sm = pm.scaled(max(2, pm.width() // f), max(2, pm.height() // f),
                           Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            pm = sm.scaled(pm.width(), pm.height(), Qt.IgnoreAspectRatio,
                           Qt.SmoothTransformation)
        # 强制拉伸铺满画布，不再上下裁切/拖动
        self._bg = pm.scaled(SCENE_W, SCENE_H, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self._backdrop = self._bg.scaled(40, 30, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

    def set_look(self, blur=None, dim=None, anchor=None):
        if blur is not None:
            self.blur = float(blur)
        if dim is not None:
            self.dim = int(dim)
        if anchor is not None:
            self.bg_anchor = float(anchor)
        self._rebuild_bg()
        self.update()

    # ---------- 人物 ----------
    def add_actor(self, role, name=None, model=None, x=None, y=None):
        model = model or self.models.model_id_for_role(role)
        actor = {
            "id": "a" + datetime.datetime.now().strftime("%H%M%S%f")[:10],
            "role": role, "name": name or role, "model": model,
            "x": 0.5 if x is None else float(x),
            "y": 0.88 if y is None else float(y),
            "scale": 1.0, "facing": 1,
            "paths": [],
        }
        self.actors.append(actor)
        self.sel = len(self.actors) - 1
        self.update()
        self.actorSelected.emit(self.sel)
        return actor

    def remove_actor(self, idx):
        if 0 <= idx < len(self.actors):
            self.actors.pop(idx)
            self.sel = min(idx, len(self.actors) - 1)
            self.update()
            self.actorSelected.emit(self.sel)

    def selected_actor(self):
        if 0 <= self.sel < len(self.actors):
            return self.actors[self.sel]
        return None

    def set_progress(self, p):
        self.progress = max(0.0, min(1.0, float(p)))
        self.update()
        self.progressChanged.emit(self.progress)

    def set_phase_count(self, n):
        self.phase_count = max(1, int(n))
        for a in self.actors:
            paths = a.setdefault("paths", [])
            while len(paths) < self.phase_count:
                paths.append([])
        self.update()

    def _actor_paths(self, actor):
        paths = actor.get("paths")
        if not paths and actor.get("path"):
            paths = [actor["path"]]
            actor["paths"] = paths
        return paths or []

    def _endpoint_before(self, actor, phase):
        paths = self._actor_paths(actor)
        pos = None
        for i in range(min(phase, len(paths))):
            path = paths[i] or []
            if len(path) >= 2:
                pos = tuple(path[-1])
            elif len(path) == 1:
                pos = tuple(path[0])
        return pos

    def add_phase_point(self, actor, phase, x, y):
        paths = actor.setdefault("paths", [])
        while len(paths) <= phase:
            paths.append([])
        path = paths[phase]
        if not path and phase > 0:
            prev = self._endpoint_before(actor, phase)
            if prev:
                path.append([round(prev[0], 4), round(prev[1], 4)])
        path.append([round(x, 4), round(y, 4)])
        self.update()

    def actor_position(self, actor):
        n = max(1, int(self.phase_count))
        paths = self._actor_paths(actor)
        if not paths:
            return (actor["x"], actor["y"])
        p = max(0.0, min(1.0, self.progress)) * n
        k = min(n - 1, int(p))
        local = p - k
        pos = (actor["x"], actor["y"])
        for i in range(k):
            path = paths[i] if i < len(paths) else []
            if len(path) >= 2:
                pos = tuple(path[-1])
            elif len(path) == 1:
                pos = tuple(path[0])
        path = paths[k] if k < len(paths) else []
        if len(path) >= 2:
            return self._point_on_path(path, local)
        if len(path) == 1:
            return tuple(path[0])
        return pos

    @staticmethod
    def _point_on_path(path, t):
        lens = []
        total = 0.0
        for i in range(1, len(path)):
            d = math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1])
            lens.append(d)
            total += d
        if total <= 0:
            return tuple(path[0])
        target = total * t
        acc = 0.0
        for i, d in enumerate(lens):
            if acc + d >= target:
                k = (target - acc) / d if d > 0 else 0
                x = path[i][0] + (path[i + 1][0] - path[i][0]) * k
                y = path[i][1] + (path[i + 1][1] - path[i][1]) * k
                return (x, y)
            acc += d
        return tuple(path[-1])

    def sprite_size(self, actor, y):
        base = 118 + 120 * y
        role = actor.get("role")
        if role in FURNITURE_ROLES:
            base *= FURN_SCALE.get(role, 1.0)
        return base * float(actor.get("scale", 1.0))

    def actor_rect(self, actor, idx):
        x, y = self.actor_position(actor)
        h = self.sprite_size(actor, y)
        pm = self.models.model_pm(actor.get("model"))
        wr = pm.width() / pm.height() if pm.height() else 0.4
        w = h * wr
        cx = x * SCENE_W
        cy = y * SCENE_H
        return QRectF(cx - w / 2, cy - h, w, h)

    def to_image(self, scale=1.0):
        w = max(1, int(SCENE_W * scale))
        h = max(1, int(SCENE_H * scale))
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(QColor("#0B0C10"))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.scale(scale, scale)
        self._paint_scene(p)
        p.end()
        return img

    # ---------- 绘制 ----------
    def _target_rect(self):
        m = 10
        # 直接铺满整个窗口，不再按比例留黑边/上下留白
        return QRectF(0, 0, max(1, self.width()), max(1, self.height()))

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#08090C"))
        if not self._backdrop.isNull():
            p.drawPixmap(self.rect(), self._backdrop)
            p.fillRect(self.rect(), QColor(6, 7, 10, 226))
        r = self._target_rect()
        p.save()
        p.translate(r.x(), r.y())
        p.scale(r.width() / SCENE_W, r.height() / SCENE_H)
        self._paint_scene(p)
        p.restore()
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5))
        if self.path_mode:
            p.setPen(QPen(QColor(accent()), 1))
            p.drawRect(r.adjusted(1, 1, -1, -1))

    def _paint_scene(self, p):
        # 底图
        if not self._bg.isNull():
            p.drawPixmap(0, 0, SCENE_W, SCENE_H, self._bg)
        # 明暗 + 暗角
        if self.dim > 0:
            p.fillRect(0, 0, SCENE_W, SCENE_H, QColor(0, 0, 0, self.dim))
        vg = QRadialGradient(SCENE_W / 2, SCENE_H * 0.46, SCENE_W * 0.72)
        vg.setColorAt(0, QColor(0, 0, 0, 0))
        vg.setColorAt(0.72, QColor(0, 0, 0, 40))
        vg.setColorAt(1, QColor(0, 0, 0, 132))
        p.fillRect(0, 0, SCENE_W, SCENE_H, vg)
        # 上下渐变，压住底图水印
        g2 = QLinearGradient(0, SCENE_H * 0.86, 0, SCENE_H)
        g2.setColorAt(0, QColor(5, 6, 9, 0))
        g2.setColorAt(1, QColor(5, 6, 9, 150))
        p.fillRect(0, int(SCENE_H * 0.86), SCENE_W, int(SCENE_H * 0.14), g2)

        if self.show_grid:
            p.setPen(QPen(QColor(255, 255, 255, 26), 1))
            for gx in range(0, SCENE_W + 1, 100):
                p.drawLine(gx, 0, gx, SCENE_H)
            for gy in range(0, SCENE_H + 1, 100):
                p.drawLine(0, gy, SCENE_W, gy)

        # 舞台 / 入口 标注
        f = QFont("Microsoft YaHei UI")
        f.setPixelSize(22)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 3)
        p.setFont(f)
        p.setPen(QColor(accent()))
        p.drawText(56, 66, "STAGE · 舞台")
        p.setPen(QColor(255, 255, 255, 120))
        p.drawText(56, SCENE_H - 34, "ENTRANCE · 入场口")

        # 动线（先画，人物压在上面；当前环节高亮，其它环节淡显）
        for a in self.actors:
            paths = self._actor_paths(a)
            for pi, path in enumerate(paths):
                if len(path) < 2:
                    continue
                current = (pi == self.current_phase)
                pts = [QPointF(x * SCENE_W, y * SCENE_H) for x, y in path]
                col = QColor(accent())
                col.setAlpha(200 if current else 60)
                pen = QPen(col, 3.2 if current else 1.8, Qt.DashLine)
                pen.setDashPattern([6, 6])
                p.setPen(pen)
                p.drawPolyline(QPolygonF(pts))
                if not current:
                    continue
                p.setPen(QPen(QColor(accent()), 1.4))
                p.setBrush(QColor(accent()))
                for pt in pts:
                    p.drawEllipse(pt, 4.2, 4.2)
                # 终点箭头
                a0, b0 = pts[-2], pts[-1]
                ang = math.atan2(b0.y() - a0.y(), b0.x() - a0.x())
                head = QPolygonF([
                    b0,
                    QPointF(b0.x() - 18 * math.cos(ang - 0.4), b0.y() - 18 * math.sin(ang - 0.4)),
                    QPointF(b0.x() - 18 * math.cos(ang + 0.4), b0.y() - 18 * math.sin(ang + 0.4)),
                ])
                p.drawPolygon(head)

        # 人物
        order = sorted(range(len(self.actors)), key=lambda i: self.actor_position(self.actors[i])[1])
        fnt = QFont("Microsoft YaHei UI")
        for idx in order:
            a = self.actors[idx]
            x, y = self.actor_position(a)
            h = self.sprite_size(a, y)
            pm = self.models.model_pm(a.get("model"))
            if pm.isNull():
                continue
            wr = pm.width() / pm.height() if pm.height() else 0.4
            w = h * wr
            cx, cy = x * SCENE_W, y * SCENE_H
            # 投影
            sh = QRectF(cx - w * 0.34, cy - h * 0.026, w * 0.68, h * 0.075)
            sg = QRadialGradient(sh.center(), sh.width() / 2)
            sg.setColorAt(0, QColor(0, 0, 0, 120))
            sg.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(sg)
            p.setPen(Qt.NoPen)
            p.drawEllipse(sh)
            # 人物
            if a.get("facing", 1) < 0:
                p.save()
                p.translate(cx, 0)
                p.scale(-1, 1)
                p.drawPixmap(QRectF(-w / 2, cy - h, w, h), pm,
                             QRectF(0, 0, pm.width(), pm.height()))
                p.restore()
            else:
                p.drawPixmap(QRectF(cx - w / 2, cy - h, w, h), pm,
                             QRectF(0, 0, pm.width(), pm.height()))
            # 选中环
            is_prop = a.get("role") in FURNITURE_ROLES
            if idx == self.sel:
                fnt.setPixelSize(19)
                p.setFont(fnt)
                name = a.get("name") or a.get("role")
                if not is_prop:
                    tw = p.fontMetrics().horizontalAdvance(name) + 26
                    tag = QRectF(cx - tw / 2, cy + 8, tw, 30)
                    p.setPen(QPen(QColor(accent()), 1.4))
                    p.setBrush(QColor(0, 0, 0, 165))
                    p.drawRoundedRect(tag, 8, 8)
                    p.setPen(QColor(accent()))
                    p.drawText(tag, Qt.AlignCenter, name)
                ring = QRectF(cx - w / 2 - 8, cy - h - 8, w + 16, h + 10)
                pen = QPen(QColor(accent()), 2, Qt.DashLine)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(ring, 10, 10)
            elif not is_prop:
                fnt.setPixelSize(17)
                p.setFont(fnt)
                name = a.get("name") or a.get("role")
                tw = p.fontMetrics().horizontalAdvance(name) + 20
                tag = QRectF(cx - tw / 2, cy + 6, tw, 26)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 120))
                p.drawRoundedRect(tag, 7, 7)
                p.setPen(QColor(235, 232, 225, 210))
                p.drawText(tag, Qt.AlignCenter, name)

        if not self.actors:
            fnt.setPixelSize(26)
            p.setFont(fnt)
            p.setPen(QColor(255, 255, 255, 130))
            p.drawText(QRectF(0, SCENE_H * 0.6, SCENE_W, 60), Qt.AlignCenter,
                       "从左侧名单点「上场」，把人物放进宴会厅")

    # ---------- 交互 ----------
    def _scene_pos(self, ev):
        r = self._target_rect()
        if r.width() <= 0 or r.height() <= 0:
            return None
        sx = (ev.position().x() - r.x()) / r.width()
        sy = (ev.position().y() - r.y()) / r.height()
        if not (0 <= sx <= 1 and 0 <= sy <= 1):
            return None
        return sx, sy

    def _hit(self, pos):
        sx, sy = pos
        cx, cy = sx * SCENE_W, sy * SCENE_H
        for idx in sorted(range(len(self.actors)),
                          key=lambda i: self.actor_position(self.actors[i])[1], reverse=True):
            r = self.actor_rect(self.actors[idx], idx)
            if r.adjusted(-12, -6, 12, 12).contains(QPointF(cx, cy)):
                return idx
        return -1

    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        pos = self._scene_pos(ev)
        if pos is None:
            return
        sx, sy = pos
        if self.path_mode:
            a = self.selected_actor()
            if a is None:
                idx = self._hit(pos)
                if idx < 0:
                    return
                self.sel = idx
                self.actorSelected.emit(self.sel)
                a = self.actors[idx]
            self.editStarted.emit()
            self.add_phase_point(a, self.current_phase, sx, sy)
            self.sceneEdited.emit()
            return
        idx = self._hit(pos)
        self.sel = idx
        self.actorSelected.emit(idx)
        self.update()
        if idx >= 0:
            a = self.actors[idx]
            cx, cy = self.actor_position(a)
            self.editStarted.emit()
            self._drag = (idx, cx - sx, cy - sy)
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, ev):
        if self._drag:
            idx, ox, oy = self._drag
            pos = self._scene_pos(ev)
            if pos and 0 <= idx < len(self.actors):
                sx, sy = pos
                a = self.actors[idx]
                a["x"] = max(0.03, min(0.97, sx + ox))
                a["y"] = max(0.06, min(0.98, sy + oy))
                a["paths"] = []
                self.update()
            return
        if self.path_mode:
            self.setCursor(Qt.CrossCursor)
            return
        pos = self._scene_pos(ev)
        if pos and self._hit(pos) >= 0:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, ev):
        if self._drag:
            self._drag = None
            self.setCursor(Qt.ArrowCursor)
            self.sceneEdited.emit()

    def mouseDoubleClickEvent(self, ev):
        pos = self._scene_pos(ev)
        if pos is None:
            return
        idx = self._hit(pos)
        if idx >= 0:
            self.sel = idx
            self.actorSelected.emit(idx)
            self.update()

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.sel >= 0:
            self.remove_actor(self.sel)
            self.sceneEdited.emit()
            return
        super().keyPressEvent(ev)


# ============================================================
#  时间轴
# ============================================================
class TimelineWidget(QWidget):
    """动线环节时间轴：等分显示 N 个环节，点击选中并跳转"""

    seeked = Signal(float)
    phaseClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(86)
        self.setCursor(Qt.PointingHandCursor)
        self.phase_count = 1
        self.duration = 30
        self.progress = 0.0
        self.current_phase = 0

    def set_phases(self, n, duration, current=0):
        self.phase_count = max(1, int(n))
        self.duration = max(1, int(duration))
        self.current_phase = max(0, min(int(current), self.phase_count - 1))
        self.update()

    def set_progress(self, p):
        self.progress = max(0.0, min(1.0, float(p)))
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        card = QRectF(0, 2, w, h - 4)
        path = QPainterPath()
        path.addRoundedRect(card, 10, 10)
        p.fillPath(path, QColor(18, 20, 26))
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        p.drawPath(path)
        track = QRectF(8, 26, max(10, w - 16), 34)
        path = QPainterPath()
        path.addRoundedRect(track, 8, 8)
        p.fillPath(path, QColor(255, 255, 255, 18))
        p.setPen(QPen(QColor(255, 255, 255, 28), 1))
        p.drawPath(path)

        n = self.phase_count
        secs = self.duration / max(1, n)
        for i in range(n):
            x0 = track.x() + track.width() * i / n
            x1 = track.x() + track.width() * (i + 1) / n
            block = QRectF(x0 + 2, track.y() + 3, max(3, x1 - x0 - 4), track.height() - 6)
            c = QColor(SEG_COLORS[i % len(SEG_COLORS)])
            if i == self.current_phase:
                c.setAlpha(240)
            elif i < self.current_phase:
                c.setAlpha(175)
            else:
                c.setAlpha(105)
            p.fillRect(block, c)
            if block.width() > 34:
                f = QFont("Microsoft YaHei UI")
                f.setPixelSize(11)
                p.setFont(f)
                p.setPen(QColor(24, 22, 18, 235))
                p.drawText(block.adjusted(5, 1, -3, -1), Qt.AlignLeft | Qt.AlignTop,
                           f"{i + 1}")
                if block.width() > 74:
                    p.setPen(QColor(30, 27, 22, 235))
                    p.drawText(block.adjusted(5, 1, -4, -1), Qt.AlignRight | Qt.AlignVCenter,
                               f"{secs:.1f}s")
            if block.width() > 70:
                f = QFont("Microsoft YaHei UI")
                f.setPixelSize(10)
                p.setFont(f)
                p.setPen(QColor(255, 255, 255, 150))
                p.drawText(QRectF(x0 + 5, track.bottom() + 1, max(30, x1 - x0 - 8), 16),
                           Qt.AlignLeft | Qt.AlignVCenter, f"环节 {i + 1}")

        px = track.x() + track.width() * self.progress
        p.setPen(QPen(QColor(accent()), 2))
        p.drawLine(QPointF(px, track.y() - 8), QPointF(px, track.bottom() + 8))
        p.setBrush(QColor(accent()))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(px - 6, track.y() - 14), QPointF(px + 6, track.y() - 14),
                                 QPointF(px, track.y() - 6)]))
        f = QFont("Microsoft YaHei UI")
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 160))
        p.drawText(QRectF(track.x(), 2, track.width(), 16), Qt.AlignLeft,
                   f"动线环节 · {n} 段 · 总时长 {fmt_mmss(self.duration)}")

    def mousePressEvent(self, ev):
        w = max(1, self.width() - 16)
        p = (ev.position().x() - 8) / w
        p = max(0.0, min(1.0, p))
        self.seeked.emit(p)
        idx = min(self.phase_count - 1, int(p * self.phase_count))
        self.phaseClicked.emit(idx)


class RehearsalPage(QWidget):
    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.models = ModelLib()
        self._phase = 0
        self._undo = []
        self._playing = False
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._last_tick = time.time()
        self._full = False
        self._build_ui()
        self._restore_layout()
        self.refresh()

    # ---------------- UI ----------------
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # 顶栏
        self.topbar = QWidget()
        top = QHBoxLayout(self.topbar)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        tbox = QVBoxLayout()
        tbox.setSpacing(2)
        title = QLabel("预演沙盘")
        title.setObjectName("Title")
        self.lb_hall = QLabel("宴会厅实景 · 3D 人物 · 动线预演")
        self.lb_hall.setObjectName("Body")
        tbox.addWidget(title)
        tbox.addWidget(self.lb_hall)
        top.addLayout(tbox)
        top.addStretch()
        b_full = QPushButton("⛶ 全屏")
        b_full.clicked.connect(self.toggle_fullscreen)
        b_png = QPushButton("导出 PNG")
        b_png.clicked.connect(self.export_png)
        b_mp4 = QPushButton("导出 MP4")
        b_mp4.setObjectName("Primary")
        b_mp4.clicked.connect(lambda: self.export_mp4())
        b_undo = QPushButton("↶ 撤销")
        b_undo.clicked.connect(self.undo)
        b_save = QPushButton("保存方案")
        b_save.clicked.connect(self.save_layout)
        b_load = QPushButton("加载方案")
        b_load.clicked.connect(self.load_layout)
        b_clear = QPushButton("清空人物")
        b_clear.clicked.connect(self.clear_all)
        for b in (b_undo, b_save, b_load, b_clear, b_png, b_mp4, b_full):
            top.addWidget(b)
        outer.addWidget(self.topbar)

        # 主体两栏
        body = QHBoxLayout()
        body.setSpacing(10)

        # 中：画布 + 时间轴 + 播放条
        center = QWidget()
        cv = QVBoxLayout(center)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(8)
        self.canvas = SandboxCanvas()
        self.canvas.actorSelected.connect(self.on_actor_selected)
        self.canvas.sceneEdited.connect(self._on_canvas_edited)
        self.canvas.editStarted.connect(self._snapshot)
        cv.addWidget(self.canvas, 1)
        self.timeline = TimelineWidget()
        self.timeline.seeked.connect(self.on_seek)
        self.timeline.phaseClicked.connect(lambda i: self._on_phase_pick(i, seek=False))
        cv.addWidget(self.timeline)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_play = QPushButton("▶ 播放动线")
        self.btn_play.setObjectName("Primary")
        self.btn_play.clicked.connect(self.toggle_play)
        bar.addWidget(self.btn_play)
        b_stop = QPushButton("■ 停止")
        b_stop.clicked.connect(self.stop_play)
        bar.addWidget(b_stop)
        self.chk_loop = QCheckBox("循环")
        bar.addWidget(self.chk_loop)
        bar.addWidget(QLabel("演示时长"))
        self.sp_secs = QSpinBox()
        self.sp_secs.setRange(1, 2147483647)
        self.sp_secs.setValue(24)
        self.sp_secs.setSuffix(" 秒")
        self.sp_secs.setFixedWidth(120)
        self.sp_secs.valueChanged.connect(self._on_secs_changed)
        bar.addWidget(self.sp_secs)
        self.lb_time = QLabel("00:00 / 00:24")
        self.lb_time.setObjectName("Body")
        bar.addWidget(self.lb_time)
        bar.addStretch()
        cv.addLayout(bar)
        body.addWidget(center, 1)

        # 右：配置卡（三页签）
        self.right_card = make_card()
        self.right_card.setFixedWidth(292)
        rv = QVBoxLayout(self.right_card)
        rv.setContentsMargins(12, 12, 12, 12)
        rv.setSpacing(8)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("PrepTabs")
        self.tabs.addTab(self._tab_scene(), "场景")
        self.tabs.addTab(self._tab_people(), "人物")
        self.tabs.addTab(self._tab_path(), "动线")
        rv.addWidget(self.tabs, 1)
        body.addWidget(self.right_card)

        outer.addLayout(body, 1)

        self.lbl_fs = QLabel("按 Esc 退出全屏", self)
        self.lbl_fs.setStyleSheet("color:#C9A86A;background:rgba(0,0,0,150);"
                                  "padding:4px 10px;border-radius:8px;font-size:12px;")
        self.lbl_fs.hide()

        from PySide6.QtGui import QShortcut, QKeySequence
        sc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        sc.setContext(Qt.WidgetWithChildrenShortcut)
        sc.activated.connect(self.exit_fullscreen)

    def _tab_scene(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 12, 10, 10)
        v.setSpacing(8)
        lb = QLabel("宴会厅底图")
        lb.setObjectName("SectionTitle")
        v.addWidget(lb)
        self.hall_list = QListWidget()
        self.hall_list.setObjectName("Plain")
        self.hall_list.setViewMode(QListWidget.IconMode)
        self.hall_list.setResizeMode(QListWidget.Adjust)
        self.hall_list.setMovement(QListWidget.Static)
        self.hall_list.setSpacing(4)
        self.hall_list.setGridSize(QSize(108, 98))
        self.hall_list.setIconSize(QSize(96, 62))
        self.hall_list.setFixedHeight(218)
        for h in self.models.halls:
            pm = QPixmap(self.models.hall_thumb(h["id"]))
            short = h["name"].split("·")[-1]
            it = QListWidgetItem(QIcon(pm), short)
            it.setToolTip(h["name"])
            it.setData(Qt.UserRole, h["id"])
            self.hall_list.addItem(it)
        self.hall_list.currentRowChanged.connect(self._on_hall_changed)
        v.addWidget(self.hall_list)
        self.lb_hall_name = QLabel("")
        self.lb_hall_name.setObjectName("Body")
        v.addWidget(self.lb_hall_name)

        lb2 = QLabel("画面质感")
        lb2.setObjectName("SectionTitle")
        v.addWidget(lb2)
        g = QGridLayout()
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(6)
        g.addWidget(QLabel("柔化"), 0, 0)
        self.sl_blur = QSlider(Qt.Horizontal)
        self.sl_blur.setRange(0, 100)
        self.sl_blur.setValue(0)
        self.sl_blur.valueChanged.connect(self._on_look)
        g.addWidget(self.sl_blur, 0, 1)
        v.addLayout(g)
        self.chk_grid = QCheckBox("显示网格")
        self.chk_grid.toggled.connect(self._on_grid)
        v.addWidget(self.chk_grid)
        b_reset = QPushButton("恢复默认画面")
        b_reset.clicked.connect(self._reset_look)
        v.addWidget(b_reset)

        lb3 = QLabel("宴会桌椅")
        lb3.setObjectName("SectionTitle")
        v.addWidget(lb3)
        row_prop = QHBoxLayout()
        row_prop.setSpacing(6)
        for label, role in (("圆桌", "圆桌"), ("长桌", "长条桌"), ("长凳", "长条凳")):
            b = QPushButton("＋" + label)
            b.clicked.connect(lambda _=False, r=role: self.add_prop(r))
            row_prop.addWidget(b)
        v.addLayout(row_prop)
        tip_prop = QLabel("点一下放到舞台，可拖动摆位；选中后可在「人物」页签调大小或删除。")
        tip_prop.setObjectName("Body")
        tip_prop.setWordWrap(True)
        v.addWidget(tip_prop)

        tip = QLabel("底图来自素材包里的 6 个宴会厅实景；柔化让画面更干净，也让人物更突出。")
        tip.setObjectName("Body")
        tip.setWordWrap(True)
        v.addWidget(tip)
        v.addStretch()
        return w

    def _tab_people(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 12, 10, 10)
        v.setSpacing(8)
        self.lb_stage = QLabel("")
        self.lb_stage.setObjectName("SectionTitle")
        v.addWidget(self.lb_stage)
        row_add = QHBoxLayout()
        self.cb_quick_role = QComboBox()
        self.cb_quick_role.addItems(ROLES)
        self.ed_quick_name = QLineEdit()
        self.ed_quick_name.setPlaceholderText("称呼（可空）")
        row_add.addWidget(self.cb_quick_role, 1)
        row_add.addWidget(self.ed_quick_name, 1)
        v.addLayout(row_add)
        b_add = QPushButton("＋ 上场")
        b_add.setObjectName("Primary")
        b_add.clicked.connect(self.add_quick_actor)
        v.addWidget(b_add)

        self.lb_sel = QLabel("未选中人物")
        self.lb_sel.setObjectName("Body")
        v.addWidget(self.lb_sel)

        g = QGridLayout()
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(6)
        g.addWidget(QLabel("称呼"), 0, 0)
        self.ed_name = QLineEdit()
        self.ed_name.editingFinished.connect(self._on_actor_edit)
        g.addWidget(self.ed_name, 0, 1)
        g.addWidget(QLabel("角色"), 1, 0)
        self.cb_role = QComboBox()
        self.cb_role.addItems(ROLES + ["圆桌", "长条桌", "长条凳"])
        self.cb_role.currentIndexChanged.connect(self._on_actor_edit)
        g.addWidget(self.cb_role, 1, 1)
        g.addWidget(QLabel("大小"), 2, 0)
        self.sl_scale = QSlider(Qt.Horizontal)
        self.sl_scale.setRange(60, 160)
        self.sl_scale.setValue(100)
        self.sl_scale.valueChanged.connect(self._on_actor_edit)
        g.addWidget(self.sl_scale, 2, 1)
        v.addLayout(g)

        row = QHBoxLayout()
        b_flip = QPushButton("左右转身")
        b_flip.clicked.connect(self.flip_actor)
        b_del = QPushButton("删除选中")
        b_del.setObjectName("Danger")
        b_del.clicked.connect(self.delete_actor)
        row.addWidget(b_flip)
        row.addWidget(b_del)
        v.addLayout(row)

        lb = QLabel("3D 人物模型（单击上场，双击替换选中人物）")
        lb.setObjectName("SectionTitle")
        lb.setWordWrap(True)
        v.addWidget(lb)
        self.model_list = QListWidget()
        self.model_list.setObjectName("Plain")
        self.model_list.setViewMode(QListWidget.IconMode)
        self.model_list.setResizeMode(QListWidget.Adjust)
        self.model_list.setMovement(QListWidget.Static)
        self.model_list.setSpacing(2)
        self.model_list.setGridSize(QSize(92, 126))
        self.model_list.setIconSize(QSize(64, 94))
        self.model_list.setFixedHeight(260)
        for m in self.models.models:
            it = QListWidgetItem(self.models.model_thumb(m["id"]), m["name"])
            it.setData(Qt.UserRole, m["id"])
            self.model_list.addItem(it)
        self.model_list.itemClicked.connect(self._model_clicked)
        self.model_list.itemDoubleClicked.connect(self._model_dblclicked)
        self._pending_model = None
        self._model_click_timer = QTimer(self)
        self._model_click_timer.setSingleShot(True)
        self._model_click_timer.setInterval(220)
        self._model_click_timer.timeout.connect(self._commit_model_click)
        v.addWidget(self.model_list)

        lb2 = QLabel("快速排位")
        lb2.setObjectName("SectionTitle")
        v.addWidget(lb2)
        grid = QGridLayout()
        grid.setSpacing(6)
        b1 = QPushButton("新人居中")
        b1.clicked.connect(lambda: self.preset_place("couple"))
        b2 = QPushButton("父母两侧")
        b2.clicked.connect(lambda: self.preset_place("parents"))
        b3 = QPushButton("伴郎伴娘")
        b3.clicked.connect(lambda: self.preset_place("bridesmaids"))
        b4 = QPushButton("司仪上台")
        b4.clicked.connect(lambda: self.preset_place("host"))
        grid.addWidget(b1, 0, 0)
        grid.addWidget(b2, 0, 1)
        grid.addWidget(b3, 1, 0)
        grid.addWidget(b4, 1, 1)
        v.addLayout(grid)
        v.addStretch()
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        sa.setWidget(w)
        outer = QWidget()
        lo = QVBoxLayout(outer)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.addWidget(sa)
        return outer

    def _tab_path(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 12, 10, 10)
        v.setSpacing(8)
        lb = QLabel("动线环节")
        lb.setObjectName("SectionTitle")
        v.addWidget(lb)
        rowp = QHBoxLayout()
        rowp.addWidget(QLabel("环节数"))
        self.sp_phases = QSpinBox()
        self.sp_phases.setRange(1, 99)
        self.sp_phases.setValue(1)
        self.sp_phases.setFixedWidth(64)
        self.sp_phases.valueChanged.connect(self._on_phases_changed)
        rowp.addWidget(self.sp_phases)
        self.lb_phase_secs = QLabel("")
        self.lb_phase_secs.setObjectName("Body")
        rowp.addWidget(self.lb_phase_secs, 1)
        v.addLayout(rowp)
        rowc = QHBoxLayout()
        rowc.addWidget(QLabel("当前环节"))
        self.cb_phase = QComboBox()
        self.cb_phase.addItem("环节 1")
        self.cb_phase.currentIndexChanged.connect(self._on_phase_pick)
        rowc.addWidget(self.cb_phase, 1)
        v.addLayout(rowc)
        tip_ph = QLabel("环节数可任意设置；每个环节只播放你在该环节画的动线，"
                        "没画下一段的人物会停在原地。点时间轴也能切环节。")
        tip_ph.setObjectName("Body")
        tip_ph.setWordWrap(True)
        v.addWidget(tip_ph)

        lb2 = QLabel("当前环节的动线")
        lb2.setObjectName("SectionTitle")
        v.addWidget(lb2)
        self.btn_path = QPushButton("✎ 画动线（点舞台加点）")
        self.btn_path.setCheckable(True)
        self.btn_path.toggled.connect(self.toggle_path_mode)
        v.addWidget(self.btn_path)
        row = QHBoxLayout()
        b_clr = QPushButton("清除本环节")
        b_clr.clicked.connect(self.clear_path)
        b_all = QPushButton("清除全部")
        b_all.clicked.connect(self.clear_all_paths)
        row.addWidget(b_clr)
        row.addWidget(b_all)
        v.addLayout(row)
        b_aisle = QPushButton("一键：新人入场动线")
        b_aisle.setObjectName("Primary")
        b_aisle.clicked.connect(self.preset_aisle_path)
        v.addWidget(b_aisle)
        b_split = QPushButton("均分当前动线到各环节")
        b_split.setToolTip("把选中人物当前环节的整条动线平均切成 N 段，每段一个环节")
        b_split.clicked.connect(self.split_current_path)
        v.addWidget(b_split)
        self.lb_path = QLabel("")
        self.lb_path.setObjectName("Body")
        self.lb_path.setWordWrap(True)
        v.addWidget(self.lb_path)

        lb3 = QLabel("导出")
        lb3.setObjectName("SectionTitle")
        v.addWidget(lb3)
        b_png = QPushButton("导出当前画面 PNG")
        b_png.clicked.connect(self.export_png)
        b_mp4 = QPushButton("导出动线演示 MP4")
        b_mp4.setObjectName("Primary")
        b_mp4.clicked.connect(lambda: self.export_mp4())
        v.addWidget(b_png)
        v.addWidget(b_mp4)
        tip2 = QLabel("MP4 按「演示时长」逐帧渲染，时长等于演示时长；超长会先确认。")
        tip2.setObjectName("Body")
        tip2.setWordWrap(True)
        v.addWidget(tip2)
        v.addStretch()
        return w

    # ---------------- 数据 ----------------
    def refresh(self):
        self.refresh_roster()
        self._rebuild_timeline()
        self._sync_hall_name()

    def _rebuild_timeline(self):
        n = max(1, self.sp_phases.value())
        self._phase = max(0, min(int(self._phase), n - 1))
        self.canvas.set_phase_count(n)
        self.canvas.current_phase = self._phase
        self._update_phase_combo()
        self.timeline.set_phases(n, self.sp_secs.value(), self._phase)
        self._update_time_label()
        if hasattr(self, "lb_phase_secs"):
            self.lb_phase_secs.setText(f"每环节 {self.sp_secs.value() / n:.1f} 秒")

    def _update_phase_combo(self):
        if not hasattr(self, "cb_phase"):
            return
        n = max(1, self.sp_phases.value())
        self.cb_phase.blockSignals(True)
        self.cb_phase.clear()
        for i in range(n):
            self.cb_phase.addItem(f"环节 {i + 1}")
        self.cb_phase.setCurrentIndex(self._phase)
        self.cb_phase.blockSignals(False)

    def _on_phases_changed(self, v):
        self._phase = min(self._phase, max(0, v - 1))
        self.canvas.set_phase_count(v)
        self._rebuild_timeline()

    def _on_phase_pick(self, idx, seek=True):
        if idx < 0:
            return
        self._phase = idx
        self.canvas.current_phase = idx
        self._update_phase_combo()
        n = max(1, self.sp_phases.value())
        if seek:
            self.on_seek(idx / n)
        else:
            self.timeline.set_phases(n, self.sp_secs.value(), idx)
        self.canvas.update()
        self.on_actor_selected(self.canvas.sel)
        if self.btn_path.isChecked():
            self.btn_path.setText(f"✎ 画动线中…（环节 {self._phase + 1}，点舞台加点）")

    def _update_time_label(self):
        secs = self.sp_secs.value()
        self.lb_time.setText(f"{fmt_mmss(secs * self.canvas.progress)} / {fmt_mmss(secs)}")

    def refresh_roster(self):
        if not hasattr(self, "lb_stage"):
            return
        people = [a for a in self.canvas.actors if a.get("role") not in FURNITURE_ROLES]
        props = len(self.canvas.actors) - len(people)
        extra = f" · {props} 件桌椅" if props else ""
        self.lb_stage.setText(f"场上 {len(people)} 人{extra}")

    def add_quick_actor(self):
        role = self.cb_quick_role.currentText()
        name = self.ed_quick_name.text().strip() or role
        self.ed_quick_name.clear()
        self._snapshot()
        self.add_actor(role, name)

    def add_actor(self, role, name):
        n = len(self.canvas.actors)
        x = 0.5 + ((n % 4) - 1.5) * 0.07
        y = 0.90 - (n // 4) * 0.035
        self.canvas.add_actor(role, name, x=x, y=y)
        self.refresh_roster()
        self.on_actor_selected(self.canvas.sel)

    # ---------------- 选中同步 ----------------
    def on_actor_selected(self, idx):
        a = self.canvas.selected_actor()
        if not a:
            self.lb_sel.setText("未选中人物")
            self.ed_name.setEnabled(False)
            self.cb_role.setEnabled(False)
            self.sl_scale.setEnabled(False)
            self.lb_path.setText("先选中一个人物，再画动线。")
            return
        self.ed_name.setEnabled(True)
        self.cb_role.setEnabled(True)
        self.sl_scale.setEnabled(True)
        self.lb_sel.setText(f"选中：{a.get('name') or a.get('role')}")
        for w, val in ((self.ed_name, a.get("name", "")),):
            w.blockSignals(True)
            w.setText(str(val))
            w.blockSignals(False)
        self.cb_role.blockSignals(True)
        idx2 = self.cb_role.findText(a.get("role", ""))
        self.cb_role.setCurrentIndex(max(0, idx2))
        self.cb_role.blockSignals(False)
        self.sl_scale.blockSignals(True)
        self.sl_scale.setValue(int(float(a.get("scale", 1.0)) * 100))
        self.sl_scale.blockSignals(False)
        self._select_model_in_list(a.get("model"))
        paths = a.get("paths") or []
        path = paths[self._phase] if self._phase < len(paths) else []
        n = len(path or [])
        dist = self._path_len(path or [])
        self.lb_path.setText(
            f"环节 {self._phase + 1} 动线：{n} 个节点 · 约 {dist:.0f} 像素" if n
            else f"环节 {self._phase + 1} 还没有动线，点「画动线」后在舞台上依次点位置。")

    def _select_model_in_list(self, mid):
        for i in range(self.model_list.count()):
            it = self.model_list.item(i)
            if it.data(Qt.UserRole) == mid:
                if self.model_list.currentRow() != i:
                    self.model_list.blockSignals(True)
                    self.model_list.setCurrentRow(i)
                    self.model_list.blockSignals(False)
                return

    def _on_actor_edit(self, *_):
        a = self.canvas.selected_actor()
        if not a:
            return
        a["name"] = self.ed_name.text().strip() or a.get("role", "")
        a["role"] = self.cb_role.currentText()
        a["scale"] = self.sl_scale.value() / 100
        self.canvas.update()
        self.lb_sel.setText(f"选中：{a.get('name')}")

    def _model_clicked(self, item):
        self._pending_model = item
        self._model_click_timer.start()

    def _commit_model_click(self):
        item = self._pending_model
        self._pending_model = None
        if item is not None:
            self._add_from_model(item)

    def _model_dblclicked(self, item):
        self._model_click_timer.stop()
        self._pending_model = None
        a = self.canvas.selected_actor()
        if not a:
            self._add_from_model(item)
            return
        self._snapshot()
        a["model"] = item.data(Qt.UserRole)
        self.canvas.update()

    def _add_from_model(self, item):
        mid = item.data(Qt.UserRole)
        m = self.models.model(mid)
        role = m.get("role") or "新郎"
        name = m.get("name") or role
        self._snapshot()
        if role in FURNITURE_ROLES:
            n = len([a for a in self.canvas.actors if a.get("role") in FURNITURE_ROLES])
            x = 0.30 + (n % 4) * 0.13
            y = 0.55 + (n // 4) * 0.12
        else:
            n = len([a for a in self.canvas.actors if a.get("role") not in FURNITURE_ROLES])
            x = 0.5 + ((n % 4) - 1.5) * 0.07
            y = 0.90 - (n // 4) * 0.035
        self.canvas.add_actor(role, name, model=mid, x=x, y=y)
        self.refresh_roster()
        self.on_actor_selected(self.canvas.sel)

    def flip_actor(self):
        a = self.canvas.selected_actor()
        if not a:
            return
        self._snapshot()
        a["facing"] = -1 if a.get("facing", 1) > 0 else 1
        self.canvas.update()

    def delete_actor(self):
        if self.canvas.sel < 0:
            return
        self._snapshot()
        self.canvas.remove_actor(self.canvas.sel)
        self.refresh_roster()

    def preset_place(self, kind):
        if not self.canvas.actors:
            QMessageBox.information(self, "提示", "先在左侧名单让人物上场")
            return
        self._snapshot()
        specs = {
            "couple": [("新郎", 0.462, 0.60), ("新娘", 0.538, 0.60)],
            "parents": [("父母", 0.34, 0.52), ("长辈", 0.66, 0.52)],
            "bridesmaids": [("伴郎", 0.40, 0.80), ("伴郎", 0.44, 0.82),
                            ("伴娘", 0.56, 0.80)],
            "host": [("司仪", 0.50, 0.27)],
        }[kind]
        used = set()
        for role, x, y in specs:
            actor = next((a for a in self.canvas.actors
                          if a.get("role") == role and id(a) not in used), None)
            if actor is None:
                actor = self.canvas.add_actor(role, role, x=x, y=y)
                used.add(id(actor))
            else:
                used.add(id(actor))
                actor["x"], actor["y"] = x, y
                actor["path"] = []
        self.canvas.update()
        self.refresh_roster()

    # ---------------- 场景 ----------------
    def _on_hall_changed(self, row):
        if row < 0 or row >= len(self.models.halls):
            return
        h = self.models.halls[row]
        self._snapshot()
        self.canvas.set_hall(h["id"])
        self._sync_hall_name()

    def _sync_hall_name(self):
        hid = self.canvas.hall_id
        name = next((h["name"] for h in self.models.halls if h["id"] == hid), "")
        self.lb_hall_name.setText(f"当前：{name}")
        self.lb_hall.setText(f"{name} · 动线推演")
        for i, h in enumerate(self.models.halls):
            if h["id"] == hid:
                self.hall_list.blockSignals(True)
                self.hall_list.setCurrentRow(i)
                self.hall_list.blockSignals(False)
                break

    def _on_look(self, *_):
        self.canvas.set_look(blur=self.sl_blur.value() / 10.0)

    def _reset_look(self):
        self.sl_blur.setValue(0)
        self._on_look()
        self.chk_grid.setChecked(False)

    def add_prop(self, role):
        """在舞台放一张宴会桌/凳"""
        self._snapshot()
        n = len([a for a in self.canvas.actors if a.get("role") in FURNITURE_ROLES])
        x = 0.30 + (n % 4) * 0.13
        y = 0.55 + (n // 4) * 0.12
        self.canvas.add_actor(role, role, x=x, y=y)
        self.refresh_roster()
        self.on_actor_selected(self.canvas.sel)
        self.tabs.setCurrentIndex(1)

    def _on_grid(self, on):
        self.canvas.show_grid = bool(on)
        self.canvas.update()

    # ---------------- 动线 ----------------
    def toggle_path_mode(self, on):
        self.canvas.path_mode = bool(on)
        self.canvas.current_phase = self._phase
        self.canvas.setCursor(Qt.CrossCursor if on else Qt.ArrowCursor)
        self.btn_path.setText(
            f"✎ 画动线中…（环节 {self._phase + 1}，点舞台加点）" if on
            else "✎ 画动线（点舞台加点）")

    def clear_path(self):
        a = self.canvas.selected_actor()
        if not a:
            return
        self._snapshot()
        paths = a.setdefault("paths", [])
        if self._phase < len(paths):
            paths[self._phase] = []
        self.canvas.update()
        self.on_actor_selected(self.canvas.sel)

    def clear_all_paths(self):
        self._snapshot()
        for a in self.canvas.actors:
            a["paths"] = []
            a.pop("path", None)
        self.canvas.update()

    def preset_aisle_path(self):
        couple = [a for a in self.canvas.actors if a.get("role") in ("新郎", "新娘")]
        if not couple:
            QMessageBox.information(self, "提示", "请先让新郎、新娘上场（人物页签「＋上场」或点模型）")
            return
        self._snapshot()
        lane = {"新郎": 0.462, "新娘": 0.538}
        for a in couple:
            x = lane.get(a.get("role"), a.get("x", 0.5))
            paths = a.setdefault("paths", [])
            while len(paths) < 1:
                paths.append([])
            paths[0] = [[x, 0.965], [x, 0.86], [x, 0.74], [x, 0.63], [x, 0.55]]
            a["x"], a["y"] = x, 0.965
        self._phase = 0
        self.canvas.current_phase = 0
        self.sp_phases.setValue(max(1, self.sp_phases.value()))
        self.canvas.set_progress(0.0)
        self._rebuild_timeline()
        self.canvas.update()
        self.lb_path.setText("已生成第 1 环节新人入场动线：从入场口沿通道走到舞台前。")
        self.tabs.setCurrentIndex(2)

    def split_current_path(self):
        """把选中人物当前环节的整条动线平均切成 N 段，分给 N 个环节"""
        a = self.canvas.selected_actor()
        if not a:
            QMessageBox.information(self, "提示", "先选中一个人物，再均分动线。")
            return
        paths = a.setdefault("paths", [])
        path = paths[self._phase] if self._phase < len(paths) else []
        if len(path) < 2:
            QMessageBox.information(self, "提示", "当前环节还没有动线，先画一条完整动线再均分。")
            return
        n = max(1, self.sp_phases.value())
        if n < 2:
            QMessageBox.information(self, "提示", "环节数至少设为 2 才能均分。")
            return
        self._snapshot()
        total = 0.0
        dists = [0.0]
        for i in range(1, len(path)):
            total += math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1])
            dists.append(total)
        if total <= 0:
            return
        segments = []
        for i in range(n):
            t0, t1 = i / n, (i + 1) / n
            seg = [self.canvas._point_on_path(path, t0)]
            for j, v in enumerate(path):
                if t0 * total + 1e-6 < dists[j] < t1 * total - 1e-6:
                    seg.append((v[0], v[1]))
            seg.append(self.canvas._point_on_path(path, t1))
            clean = []
            for p in seg:
                if not clean or math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 1e-5:
                    clean.append([round(p[0], 4), round(p[1], 4)])
            segments.append(clean)
        a["paths"] = segments
        self._phase = 0
        self.canvas.current_phase = 0
        self.canvas.set_progress(0.0)
        self._rebuild_timeline()
        self.canvas.update()
        self.lb_path.setText(f"已把整条动线均分为 {n} 段，每段对应一个环节；播放时按环节逐段走。")
        if self.btn_path.isChecked():
            self.btn_path.setText(f"✎ 画动线中…（环节 1，点舞台加点）")

    @staticmethod
    def _path_len(path):
        return sum(math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]) * SCENE_W
                   for i in range(1, len(path)))

    # ---------------- 播放 ----------------
    def toggle_play(self):
        if self._playing:
            self.stop_play()
            return
        if not self.canvas.actors:
            QMessageBox.information(self, "提示", "舞台上还没有人物，先在人物页签上场吧")
            return
        self._playing = True
        self._last_tick = time.time()
        self.btn_play.setText("⏸ 暂停")
        self._timer.start()

    def stop_play(self):
        self._playing = False
        self._timer.stop()
        self.btn_play.setText("▶ 播放动线")
        self.canvas.set_progress(0.0)
        self._phase = 0
        self.canvas.current_phase = 0
        self._rebuild_timeline()
        self.timeline.set_progress(0.0)
        self._update_time_label()

    def _tick(self):
        now = time.time()
        dt = max(0.0, now - self._last_tick)
        self._last_tick = now
        secs = max(1.0, float(self.sp_secs.value()))
        p = self.canvas.progress + dt / secs
        if p >= 1.0:
            if self.chk_loop.isChecked():
                p = 0.0
            else:
                p = 1.0
                self.canvas.set_progress(p)
                self._sync_phase(p)
                self.timeline.set_progress(p)
                self._update_time_label()
                self.stop_play()
                return
        self.canvas.set_progress(p)
        self._sync_phase(p)
        self.timeline.set_progress(p)
        self._update_time_label()

    def _sync_phase(self, p):
        n = max(1, self.sp_phases.value())
        ph = min(n - 1, max(0, int(p * n)))
        if ph != self._phase:
            self._phase = ph
            self.canvas.current_phase = ph
            self._update_phase_combo()
        self.timeline.set_phases(n, self.sp_secs.value(), self._phase)

    def on_seek(self, p):
        self.canvas.set_progress(p)
        self._sync_phase(p)
        self.timeline.set_progress(p)
        self._update_time_label()

    def _on_secs_changed(self, v):
        self._rebuild_timeline()
        self.timeline.set_progress(self.canvas.progress)

    # ---------------- 快照 / 撤销 ----------------
    def _dump(self):
        return {
            "hall": self.canvas.hall_id,
            "look": {"blur": self.canvas.blur, "anchor": self.canvas.bg_anchor},
            "secs": self.sp_secs.value(),
            "phases": self.sp_phases.value(),
            "phase": self._phase,
            "actors": copy.deepcopy(self.canvas.actors),
        }

    def _snapshot(self):
        try:
            self._undo.append(self._dump())
            if len(self._undo) > 30:
                self._undo.pop(0)
        except Exception:
            pass

    def _apply(self, d):
        actors = copy.deepcopy(d.get("actors", []))
        for a in actors:
            if not a.get("paths") and a.get("path"):
                a["paths"] = [a["path"]]
            a.pop("path", None)
        self.canvas.actors = actors
        self.canvas.sel = -1
        look = d.get("look", {})
        self.sl_blur.setValue(int(float(look.get("blur", 0.0)) * 10))
        self.canvas.set_hall(d.get("hall", "hall1"))
        self._on_look()
        self.sp_phases.blockSignals(True)
        self.sp_phases.setValue(int(d.get("phases", 1) or 1))
        self.sp_phases.blockSignals(False)
        self._phase = int(d.get("phase", 0) or 0)
        self.sp_secs.blockSignals(True)
        self.sp_secs.setValue(int(d.get("secs", 24) or 24))
        self.sp_secs.blockSignals(False)
        self.canvas.set_phase_count(self.sp_phases.value())
        self.canvas.set_progress(0.0)
        self._rebuild_timeline()
        self.canvas.update()
        self.refresh_roster()

    def undo(self):
        if not self._undo:
            QMessageBox.information(self, "提示", "没有可撤销的操作了")
            return
        self._apply(self._undo.pop())

    def clear_all(self):
        if not self.canvas.actors:
            return
        if QMessageBox.question(self, "确认", "清空舞台上的人物与动线？") != QMessageBox.Yes:
            return
        self._snapshot()
        self.canvas.actors = []
        self.canvas.sel = -1
        self.canvas.update()
        self.refresh_roster()

    def _on_canvas_edited(self):
        self.refresh_roster()
        self._update_time_label()

    # ---------------- 保存 / 加载 ----------------
    def save_layout(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存沙盘方案", os.path.join(data_dir(), "沙盘方案.json"),
            "沙盘方案 (*.json)")
        if not path:
            return
        try:
            d = self._dump()
            d["name"] = os.path.splitext(os.path.basename(path))[0]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
            try:
                with open(LAYOUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, indent=1)
            except Exception:
                pass
            QMessageBox.information(self, "已保存", path)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def load_layout(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "加载沙盘方案", data_dir(), "沙盘方案 (*.json)")
        if not path:
            return
        self._load_from(path, notify=True)

    def _load_from(self, path, notify=False):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            self._snapshot()
            self._apply(d)
            if notify:
                QMessageBox.information(self, "已加载", f"方案：{d.get('name', os.path.basename(path))}")
        except Exception as e:
            if notify:
                QMessageBox.critical(self, "加载失败", str(e))

    def _restore_layout(self):
        try:
            with open(LAYOUT_FILE, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("actors") is not None:
                self._apply(d)
            return
        except Exception:
            pass
        # 默认：新人 + 司仪 已在台上
        self.canvas.add_actor("司仪", "主持人", x=0.50, y=0.27)
        self.canvas.add_actor("新郎", "新郎", x=0.462, y=0.62)
        self.canvas.add_actor("新娘", "新娘", x=0.538, y=0.62)
        self.canvas.sel = -1

    # ---------------- 全屏 ----------------
    def toggle_fullscreen(self):
        if self._full:
            self.exit_fullscreen()
        else:
            self._full = True
            self.topbar.hide()
            self.right_card.hide()
            self.lbl_fs.show()
            self.window().showFullScreen()
            QTimer.singleShot(150, self._place_fs_label)

    def _place_fs_label(self):
        self.lbl_fs.move(self.width() - 150, 16)
        self.lbl_fs.raise_()

    def exit_fullscreen(self):
        if not self._full:
            return
        self._full = False
        self.topbar.show()
        self.right_card.show()
        self.lbl_fs.hide()
        self.window().showNormal()

    # ---------------- 导出 ----------------
    def export_png(self):
        default = os.path.join(
            data_dir(), f"沙盘_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        path, _ = QFileDialog.getSaveFileName(self, "导出沙盘画面", default, "PNG 图片 (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        try:
            img = self.canvas.to_image(1.5)
            if img.save(path, "PNG"):
                QMessageBox.information(self, "导出成功", path)
            else:
                QMessageBox.warning(self, "导出失败", "文件写入失败，请检查路径")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _ffmpeg(self):
        p = asset_path("ffmpeg.exe")
        return p if os.path.exists(p) else "ffmpeg"

    def export_mp4(self, out_path=None, fps=24, silent=False):
        if out_path is None:
            default = os.path.join(
                data_dir(), f"沙盘演示_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
            out_path, _ = QFileDialog.getSaveFileName(self, "导出动线演示", default,
                                                      "MP4 视频 (*.mp4)")
            if not out_path:
                return
            if not out_path.lower().endswith(".mp4"):
                out_path += ".mp4"
        ff = self._ffmpeg()
        if ff != "ffmpeg" and not os.path.exists(ff):
            QMessageBox.warning(self, "缺少 ffmpeg", "没有找到内置 ffmpeg，无法导出视频。")
            return
        secs = max(1, int(self.sp_secs.value()))
        if not silent and secs > 3600:
            if QMessageBox.question(
                    self, "时长较长",
                    f"演示时长 {fmt_mmss(secs)}，逐帧渲染会很久，是否继续？") != QMessageBox.Yes:
                return
        if secs > 86400:
            QMessageBox.warning(self, "无法导出", "MP4 单次导出暂不支持超过 24 小时的时长。")
            return
        n = max(2, int(secs * fps))
        img_scale = 1280 / SCENE_W
        w = int(SCENE_W * img_scale)
        h = int(SCENE_H * img_scale)
        dlg = QProgressDialog("正在渲染动线演示…", "取消", 0, n, self)
        dlg.setWindowTitle("导出 MP4")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        old_p = self.canvas.progress
        flags = 0x08000000 if os.name == "nt" else 0
        cmd = [ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgba",
               "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
               "-movflags", "+faststart", out_path]
        proc = None
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    creationflags=flags)
            for i in range(n):
                if dlg.wasCanceled():
                    proc.kill()
                    dlg.close()
                    return
                self.canvas.set_progress(i / (n - 1))
                img = self.canvas.to_image(img_scale).convertToFormat(QImage.Format_RGBA8888)
                data = img.constBits().tobytes()
                proc.stdin.write(data)
                if i % 4 == 0:
                    dlg.setValue(i)
                    QApplication.processEvents()
            dlg.setValue(n)
            proc.stdin.close()
            err = proc.stderr.read()
            proc.wait(timeout=600)
            if proc.returncode != 0:
                raise RuntimeError(err.decode("utf-8", "ignore")[-600:])
            if not silent:
                QMessageBox.information(self, "导出成功", f"已生成 {n} 帧的动线演示：\n{out_path}")
        except Exception as e:
            if not silent:
                QMessageBox.critical(self, "导出失败", str(e))
            else:
                logger.exception("MP4 导出失败")
        finally:
            dlg.close()
            self.canvas.set_progress(old_p)
            if proc and proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass
