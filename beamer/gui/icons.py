"""Vektorové ikony levé lišty (kreslené QPainterem, bez souborů).

Kreslí se na mřížce 24×24 jednotek tenkou čarou se zaoblenými konci. QIcon
dostane pixmapy pro více měřítek obrazovky (100–400 %), takže ikony zůstávají
ostré i při zvětšení zobrazení ve Windows. Volitelně druhá barva pro stav
„vybráno" (QIcon.On) – zvýraznění aktivní karty."""
from __future__ import annotations

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QPolygonF

_SCALES = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0)


def _draw(p: QPainter, key: str, color: str) -> None:
    ink = QColor(color)
    tint = QColor(color)
    tint.setAlphaF(0.18)
    pen = QPen(ink)
    pen.setWidthF(1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    def line(x1, y1, x2, y2):
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def poly(pts, close=False, fill=False):
        pl = QPolygonF([QPointF(x, y) for x, y in pts])
        if close:
            p.setBrush(tint if fill else Qt.NoBrush)
            p.drawPolygon(pl)
            p.setBrush(Qt.NoBrush)
        else:
            p.drawPolyline(pl)

    def arrow_down(x, y1, y2):
        line(x, y1, x, y2)
        poly([(x - 2.2, y2 - 2.6), (x, y2), (x + 2.2, y2 - 2.6)])

    if key == "model":                       # nosník na kloubové a posuvné podpoře
        p.setBrush(tint)
        p.drawRoundedRect(QRectF(3, 8.5, 18, 3.5), 1, 1)
        p.setBrush(Qt.NoBrush)
        poly([(6.5, 12), (3.8, 17), (9.2, 17)], close=True)
        p.drawEllipse(QPointF(17.5, 14.6), 2.4, 2.4)
        line(3, 19.5, 21, 19.5)
    elif key == "material":                  # krychle materiálu (izometrie)
        poly([(12, 3.5), (20, 7.5), (12, 11.5), (4, 7.5)], close=True, fill=True)
        poly([(4, 7.5), (4, 16.5), (12, 20.5), (20, 16.5), (20, 7.5)])
        line(12, 11.5, 12, 20.5)
    elif key == "section":                   # průřez I-profilu
        poly([(5, 4), (19, 4), (19, 7), (13.5, 7), (13.5, 17), (19, 17),
              (19, 20), (5, 20), (5, 17), (10.5, 17), (10.5, 7), (5, 7)],
             close=True, fill=True)
    elif key == "pid":                       # štítek vlastnosti (PID)
        poly([(3.5, 7), (14, 7), (20.5, 12), (14, 17), (3.5, 17)],
             close=True, fill=True)
        p.drawEllipse(QPointF(14.2, 12), 1.5, 1.5)
        line(6.5, 10.5, 10.5, 10.5)
        line(6.5, 13.5, 9.5, 13.5)
    elif key == "segs":                      # nosník dělený na úseky
        p.setBrush(tint)
        p.drawRoundedRect(QRectF(3, 10, 18, 4), 1, 1)
        p.setBrush(Qt.NoBrush)
        line(9, 6.5, 9, 17.5)
        line(15, 6.5, 15, 17.5)
    elif key == "supports":                  # kloubová podpora na zemi
        p.drawEllipse(QPointF(12, 6.5), 2.2, 2.2)
        poly([(12, 8.7), (6.5, 16), (17.5, 16)], close=True, fill=True)
        line(4, 16, 20, 16)
        for x in (7, 11, 15, 19):
            line(x, 16, x - 2.5, 19.5)
    elif key == "loads":                     # spojité zatížení na nosník
        line(4.5, 4.5, 19.5, 4.5)
        for x in (6, 12, 18):
            arrow_down(x, 4.5, 14)
        p.setBrush(tint)
        p.drawRoundedRect(QRectF(3, 17, 18, 3), 1, 1)
        p.setBrush(Qt.NoBrush)
    elif key == "eval":                      # kruh + fajfka (posouzení)
        p.setBrush(tint)
        p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
        p.setBrush(Qt.NoBrush)
        poly([(8, 12.3), (11, 15.3), (16.5, 9)])
    elif key == "matsec":                    # vrstvy (materiál + průřez)
        for y in (7, 12, 17):
            line(5, y, 19, y)


def _pixmap(key: str, color: str, size: int, scale: float) -> QPixmap:
    px = max(1, round(size * scale))
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.scale(px / 24.0, px / 24.0)
    _draw(p, key, color)
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


def card_icon(key: str, color: str = "#55606e", size: int = 24,
              on_color: str | None = None) -> QIcon:
    icon = QIcon()
    for sc in _SCALES:
        icon.addPixmap(_pixmap(key, color, size, sc), QIcon.Normal, QIcon.Off)
        if on_color:
            icon.addPixmap(_pixmap(key, on_color, size, sc), QIcon.Normal, QIcon.On)
    return icon
