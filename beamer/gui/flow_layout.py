"""Zalamovací layout (port příkladu Qt „Flow Layout").

Položky se skládají zleva doprava a když se nevejdou, pokračují na dalším
řádku. Používá se pro horní lištu hlavního okna – při zvětšeném měřítku
Windows (např. 200–300 %) se jinak jeden dlouhý řádek ovládacích prvků
nevejde na obrazovku a okno nejde zmenšit.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QSize, QPoint
from PySide6.QtWidgets import QLayout, QSizePolicy


class FlowLayout(QLayout):
    def __init__(self, parent=None, h_spacing=6, v_spacing=4):
        super().__init__(parent)
        self._items = []
        self._h = h_spacing
        self._v = v_spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, test):
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        items = [it for it in self._items
                 if it.widget() is None
                 or it.widget().isVisibleTo(it.widget().parentWidget())]
        # jednotná výška řádku → combo, tlačítko i checkbox svisle na středu
        row_h = max((it.sizeHint().height() for it in items), default=0)
        x, y = r.x(), r.y()
        for it in items:
            hint = it.sizeHint()
            if x > r.x() and x + hint.width() > r.right() + 1:
                x = r.x()
                y += row_h + self._v
            if not test:
                it.setGeometry(QRect(QPoint(x, y + (row_h - hint.height()) // 2), hint))
            x += hint.width() + self._h
        return y + row_h - rect.y() + m.top() + m.bottom()
