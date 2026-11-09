# -*- coding: utf-8 -*-
"""导航线稿图标：QPainter 现画，避免字形缺字与尺寸过小。"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

DEFAULT = "#9DA1AB"


def _stroke(p, pts, close=False):
    path = QPainterPath(QPointF(*pts[0]))
    for x, y in pts[1:]:
        path.lineTo(QPointF(x, y))
    if close:
        path.closeSubpath()
    p.drawPath(path)


def icon(name: str, size: int = 22, color: str = DEFAULT) -> QIcon:
    s = int(size)
    pix = QPixmap(s * 2, s * 2)
    pix.setDevicePixelRatio(2.0)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.3, s * 0.065))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    u = s / 24.0

    def P(x, y):
        return QPointF(x * u, y * u)

    def R(x, y, w, h):
        return QRectF(x * u, y * u, w * u, h * u)

    if name == "dashboard":
        for x, y in ((3, 3), (13.5, 3), (3, 13.5), (13.5, 13.5)):
            p.drawRoundedRect(R(x, y, 7.5, 7.5), 1.6 * u, 1.6 * u)
    elif name == "calendar":
        p.drawRoundedRect(R(3, 5, 18, 15.5), 2 * u, 2 * u)
        _stroke(p, [(3, 9.5), (21, 9.5)])
        _stroke(p, [(8, 2.5), (8, 6.5)])
        _stroke(p, [(16, 2.5), (16, 6.5)])
        _stroke(p, [(7, 13.5), (10, 13.5)])
        _stroke(p, [(13, 13.5), (16, 13.5)])
        _stroke(p, [(7, 17.5), (10, 17.5)])
    elif name == "design":
        p.drawRoundedRect(R(3, 4, 18, 16), 2 * u, 2 * u)
        p.drawEllipse(R(7.5, 8, 3.2, 3.2))
        _stroke(p, [(3.4, 18.6), (9.4, 12.2), (13.2, 16.2), (16.4, 12.6), (20.6, 17.6)])
    elif name == "stage":
        p.drawEllipse(R(9, 2.6, 6, 6))
        _stroke(p, [(10.6, 8.4), (6, 21)])
        _stroke(p, [(13.4, 8.4), (18, 21)])
        _stroke(p, [(3.5, 21), (20.5, 21)])
    elif name == "memo":
        p.drawRoundedRect(R(4, 5, 16, 16), 2 * u, 2 * u)
        _stroke(p, [(8, 10), (16, 10)])
        _stroke(p, [(8, 13.6), (16, 13.6)])
        _stroke(p, [(8, 17.2), (12.5, 17.2)])
    elif name == "ai":
        _stroke(p, [(12, 3), (12, 21)])
        _stroke(p, [(3, 12), (21, 12)])
        _stroke(p, [(6.4, 6.4), (9.6, 9.6)])
        _stroke(p, [(14.4, 14.4), (17.6, 17.6)])
        _stroke(p, [(17.6, 6.4), (14.4, 9.6)])
        _stroke(p, [(9.6, 14.4), (6.4, 17.6)])
    elif name == "prep":
        p.drawRoundedRect(R(4, 3.5, 16, 17.5), 2 * u, 2 * u)
        p.drawRoundedRect(R(8.5, 1.6, 7, 3.4), 1.4 * u, 1.4 * u)
        _stroke(p, [(8, 11.2), (11, 14.2), (16.4, 8.6)])
    elif name == "music":
        p.drawEllipse(R(3.4, 14.6, 4.4, 4.4))
        _stroke(p, [(7.8, 14.6), (7.8, 4.5)])
        _stroke(p, [(7.8, 4.5), (14.8, 4.5), (14.8, 8.6)])
        p.drawEllipse(R(12.6, 13.2, 4.2, 4.2))
        _stroke(p, [(16.8, 13.2), (16.8, 5.6)])
    elif name == "settings":
        p.drawEllipse(R(8.6, 8.6, 6.8, 6.8))
        for k in range(8):
            import math
            a = 2 * math.pi * k / 8
            _stroke(p, [(12 + 8.4 * math.cos(a), 12 + 8.4 * math.sin(a)),
                        (12 + 10.6 * math.cos(a), 12 + 10.6 * math.sin(a))])
    elif name == "dev":
        for y, kx in ((6.6, 8.6), (12, 14.4), (17.4, 6.4)):
            _stroke(p, [(3.2, y), (20.8, y)])
            p.setBrush(QColor(color))
            p.drawEllipse(R(kx - 1.5, y - 1.5, 3, 3))
            p.setBrush(Qt.NoBrush)
    p.end()
    return QIcon(pix)
