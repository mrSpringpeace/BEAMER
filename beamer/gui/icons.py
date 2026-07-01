"""Jednoduché vektorové ikony pro levou lištu (kreslené QPainterem, bez souborů).

`card_icon(key, color, size)` vrátí QIcon s jednoduchou čárovou grafikou v dané
barvě – barvu volá volající podle motivu (světlý/tmavý)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QPolygonF


def card_icon(key: str, color: str = "#55606e", size: int = 22) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    s = float(size)

    def line(x1, y1, x2, y2):
        p.drawLine(QPointF(x1 * s, y1 * s), QPointF(x2 * s, y2 * s))

    def poly(pts, close=False):
        pl = QPolygonF([QPointF(x * s, y * s) for x, y in pts])
        p.drawPolyline(pl) if not close else p.drawPolygon(pl)

    if key == "model":                       # nosník + 2 podpory
        line(.12, .48, .88, .48)
        poly([(.22, .70), (.32, .48), (.42, .70)])
        poly([(.58, .70), (.68, .48), (.78, .70)])
    elif key == "matsec":                    # vrstvy (materiál + průřez)
        for y in (.30, .50, .70):
            line(.20, y, .80, y)
    elif key == "material":                  # plný blok materiálu
        p.setBrush(QColor(color))
        p.drawRoundedRect(QRectF(.24 * s, .26 * s, .52 * s, .48 * s), 3, 3)
    elif key == "section":                   # průřez I-profilu
        line(.28, .28, .72, .28)
        line(.28, .72, .72, .72)
        line(.5, .28, .5, .72)
    elif key == "pid":                        # štítek # (vlastnost pod číslem)
        line(.36, .28, .30, .72)
        line(.64, .28, .58, .72)
        line(.28, .44, .72, .44)
        line(.26, .60, .70, .60)
    elif key == "segs":                      # dělený nosník (úseky)
        line(.12, .5, .88, .5)
        line(.38, .36, .38, .64)
        line(.62, .36, .62, .64)
    elif key == "supports":                  # trojúhelníková podpora na zemi
        line(.15, .72, .85, .72)
        poly([(.34, .72), (.5, .38), (.66, .72)], close=True)
    elif key == "loads":                     # svislá šipka dolů
        line(.5, .18, .5, .74)
        poly([(.35, .56), (.5, .76), (.65, .56)])
    elif key == "eval":                      # kruh + fajfka (posouzení)
        p.drawArc(QRectF(.2 * s, .2 * s, .6 * s, .6 * s), 0, 360 * 16)
        poly([(.36, .52), (.46, .63), (.66, .38)])
    p.end()
    return QIcon(pm)
