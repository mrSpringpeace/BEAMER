"""Dialog Nastavení – jazyk, formát čísel, zobrazení VVÚ."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QCheckBox,
    QDialogButtonBox, QLabel, QGroupBox,
)

from ..settings import SETTINGS
from ..i18n import tr
from .spin import NoWheelSpinBox


class SettingsDialog(QDialog):
    # signály: změna jazyka (vyžaduje přestavbu UI), změna formátu/zobrazení (jen překreslení)
    language_changed = Signal()
    display_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Nastavení"))
        self.setMinimumWidth(360)
        v = QVBoxLayout(self)

        g = QGroupBox()
        f = QFormLayout(g)

        self.lang_cb = QComboBox()
        self.lang_cb.addItem("Čeština", "cs")
        self.lang_cb.addItem("English", "en")
        self.lang_cb.setCurrentIndex(self.lang_cb.findData(SETTINGS.language))
        self.lang_cb.currentIndexChanged.connect(self._on_language)
        f.addRow(tr("Jazyk / Language"), self.lang_cb)

        self.fmt_cb = QComboBox()
        self.fmt_cb.addItem(tr("Fixed (pevný)"), "fixed")
        self.fmt_cb.addItem(tr("Scientific (vědecký)"), "scientific")
        self.fmt_cb.setCurrentIndex(self.fmt_cb.findData(SETTINGS.number_format))
        self.fmt_cb.currentIndexChanged.connect(self._on_format)
        f.addRow(tr("Formát čísel"), self.fmt_cb)

        self.dec_sp = NoWheelSpinBox()
        self.dec_sp.setRange(0, 10)
        self.dec_sp.setValue(SETTINGS.decimals)
        self.dec_sp.valueChanged.connect(self._on_decimals)
        f.addRow(tr("Desetinná místa:"), self.dec_sp)

        self.vvu_cb = QCheckBox(tr("VVÚ v jednom grafu"))
        self.vvu_cb.setChecked(SETTINGS.vvu_combined)
        self.vvu_cb.toggled.connect(self._on_vvu)
        f.addRow(self.vvu_cb)

        self.deform_cb = QCheckBox(tr("Zobrazit průhyb a pootočení"))
        self.deform_cb.setChecked(SETTINGS.vvu_show_deform)
        self.deform_cb.toggled.connect(self._on_deform)
        f.addRow(self.deform_cb)

        v.addWidget(g)
        note = QLabel(tr("Změna jazyka se projeví v celém rozhraní."))
        note.setStyleSheet("color:#666; font-size:11px;")
        note.setWordWrap(True)
        v.addWidget(note)

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.accept)
        bb.accepted.connect(self.accept)
        v.addWidget(bb)

    def _on_language(self, _):
        SETTINGS.language = self.lang_cb.currentData()
        SETTINGS.save()
        self.language_changed.emit()

    def _on_format(self, _):
        SETTINGS.number_format = self.fmt_cb.currentData()
        SETTINGS.save()
        self.display_changed.emit()

    def _on_decimals(self, v):
        SETTINGS.decimals = int(v)
        SETTINGS.save()
        self.display_changed.emit()

    def _on_vvu(self, on):
        SETTINGS.vvu_combined = bool(on)
        SETTINGS.save()
        self.display_changed.emit()

    def _on_deform(self, on):
        SETTINGS.vvu_show_deform = bool(on)
        SETTINGS.save()
        self.display_changed.emit()
