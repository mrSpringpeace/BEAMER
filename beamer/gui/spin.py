"""Číselná pole bez šipek a bez reakce na kolečko myši.

Hodnota se mění výhradně ručním zápisem. Kolečko se ignoruje (a propadne
nadřazenému scrollu, takže panel lze rolovat).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox, QAbstractSpinBox


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.setFocusPolicy(Qt.StrongFocus)
        # hodnotu „commitneme" až na Enter / opuštění pole – jinak by každá
        # zadaná číslice (1, 10, 100…) spustila živý přepočet a editace by lagovala
        self.setKeyboardTracking(False)

    def wheelEvent(self, e):
        e.ignore()


class NoWheelSpinBox(QSpinBox):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setKeyboardTracking(False)

    def wheelEvent(self, e):
        e.ignore()
