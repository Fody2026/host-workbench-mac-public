# -*- coding: utf-8 -*-
"""矢量图标：用 QPainter 现绘，保证清晰且跟随主题色"""
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QPolygonF, QPainterPath, QFont

import theme


def _color(kind="text"):
    t = theme.THEMES.get(theme.current_theme(), theme.THEMES["暗夜金"])
    return t.get(kind, t["text"])


def _pm(size, painter_fn, color):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(color), 2))
    p.setBrush(Qt.NoBrush)
    painter_fn(p, size)
    p.end()
    return pm


def icon(name, size=22, color=None):
    """返回 QIcon；name 支持 play/pause/stop/prev/next/loop_one/loop_list/no_loop/
    volume/settings/add/list/folder/delete/edit/copy"""
    from PySide6.QtGui import QIcon
    c = color or _color("text")

    def draw(p, s):
        m = s * 0.12
        r = QRectF(m, m, s - 2 * m, s - 2 * m)
        if name == "play":
            tri = QPolygonF([QPointF(s * 0.28, s * 0.18), QPointF(s * 0.28, s * 0.82),
                             QPointF(s * 0.82, s * 0.5)])
            p.setBrush(QColor(c))
            p.setPen(Qt.NoPen)
            p.drawPolygon(tri)
        elif name == "pause":
            p.setBrush(QColor(c))
            p.setPen(Qt.NoPen)
            w = s * 0.16
            p.drawRoundedRect(QRectF(s * 0.30, s * 0.20, w, s * 0.60), 2, 2)
            p.drawRoundedRect(QRectF(s * 0.54, s * 0.20, w, s * 0.60), 2, 2)
        elif name == "stop":
            p.setBrush(QColor(c))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(s * 0.28, s * 0.28, s * 0.44, s * 0.44), 2, 2)
        elif name == "prev":
            p.setBrush(QColor(c))
            p.setPen(Qt.NoPen)
            p.drawRect(QRectF(s * 0.24, s * 0.22, s * 0.08, s * 0.56))
            p.drawPolygon(QPolygonF([QPointF(s * 0.78, s * 0.22), QPointF(s * 0.78, s * 0.78),
                                     QPointF(s * 0.36, s * 0.5)]))
        elif name == "next":
            p.setBrush(QColor(c))
            p.setPen(Qt.NoPen)
            p.drawRect(QRectF(s * 0.68, s * 0.22, s * 0.08, s * 0.56))
            p.drawPolygon(QPolygonF([QPointF(s * 0.22, s * 0.22), QPointF(s * 0.22, s * 0.78),
                                     QPointF(s * 0.64, s * 0.5)]))
        elif name in ("loop_one", "loop_list"):
            path = QPainterPath()
            path.arcMoveTo(QRectF(s * 0.20, s * 0.24, s * 0.60, s * 0.52), 60)
            path.arcTo(QRectF(s * 0.20, s * 0.24, s * 0.60, s * 0.52), 60, 300)
            p.setPen(QPen(QColor(c), 2))
            p.drawPath(path)
            # 箭头
            p.setBrush(QColor(c))
            p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygonF([QPointF(s * 0.76, s * 0.22), QPointF(s * 0.86, s * 0.32),
                                     QPointF(s * 0.72, s * 0.36)]))
            if name == "loop_one":
                f = QFont("Arial")
                f.setPixelSize(int(s * 0.42))
                f.setBold(True)
                p.setFont(f)
                p.setPen(QPen(QColor(c)))
                p.drawText(QRectF(s * 0.34, s * 0.34, s * 0.32, s * 0.32), Qt.AlignCenter, "1")
        elif name == "no_loop":
            p.setPen(QPen(QColor(c), 2))
            p.drawLine(QPointF(s * 0.22, s * 0.5), QPointF(s * 0.80, s * 0.5))
            p.setBrush(QColor(c))
            p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygonF([QPointF(s * 0.84, s * 0.5), QPointF(s * 0.70, s * 0.40),
                                     QPointF(s * 0.70, s * 0.60)]))
        elif name == "volume":
            p.setPen(QPen(QColor(c), 2))
            p.setBrush(QColor(c))
            p.drawPolygon(QPolygonF([QPointF(s * 0.18, s * 0.40), QPointF(s * 0.30, s * 0.40),
                                     QPointF(s * 0.42, s * 0.28), QPointF(s * 0.42, s * 0.72),
                                     QPointF(s * 0.30, s * 0.60), QPointF(s * 0.18, s * 0.60)]))
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(s * 0.42, s * 0.30, s * 0.30, s * 0.40), -70 * 16, 140 * 16)
        elif name == "add":
            p.drawLine(QPointF(s * 0.5, s * 0.24), QPointF(s * 0.5, s * 0.76))
            p.drawLine(QPointF(s * 0.24, s * 0.5), QPointF(s * 0.76, s * 0.5))
        elif name == "list":
            for i, y in enumerate((0.30, 0.50, 0.70)):
                p.setBrush(QColor(c))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(s * 0.24, s * y), 2.2, 2.2)
                p.drawLine(QPointF(s * 0.36, s * y), QPointF(s * 0.80, s * y))
        elif name in ("folder", "copy", "delete", "edit", "settings"):
            p.drawRoundedRect(QRectF(s * 0.20, s * 0.30, s * 0.60, s * 0.44), 3, 3)
            if name == "folder":
                p.drawLine(QPointF(s * 0.20, s * 0.34), QPointF(s * 0.40, s * 0.34))

    if name == "settings":
        c2 = color or _color("sub")
        return QIcon(_pm(size, lambda p, s: (p.setPen(QPen(QColor(c2), 2)),
                                             p.drawEllipse(QPointF(s / 2, s / 2), s * 0.26, s * 0.26),
                                             p.drawEllipse(QPointF(s / 2, s / 2), s * 0.09, s * 0.09)), c2))
    return QIcon(_pm(size, draw, c))


def accent_icon(name, size=22):
    return icon(name, size, _color("accent"))
