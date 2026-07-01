"""Dialog Nastavení – jazyk, formát čísel, zobrazení VVÚ."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox, QCheckBox,
    QDialogButtonBox, QLabel, QGroupBox, QLineEdit, QPushButton, QFileDialog,
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

        self.theme_cb = QComboBox()
        self.theme_cb.addItem(tr("Podle systému"), "system")
        self.theme_cb.addItem(tr("Světlý"), "light")
        self.theme_cb.addItem(tr("Tmavý"), "dark")
        self.theme_cb.setCurrentIndex(max(0, self.theme_cb.findData(SETTINGS.theme)))
        self.theme_cb.currentIndexChanged.connect(self._on_theme)
        f.addRow(tr("Vzhled"), self.theme_cb)

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

        # ── sdílená knihovna ──
        gl = QGroupBox(tr("Sdílená knihovna (materiály a profily)"))
        fl = QVBoxLayout(gl)
        row = QHBoxLayout()
        self.shared_edit = QLineEdit(SETTINGS.shared_library_dir or "")
        self.shared_edit.setReadOnly(True)
        self.shared_edit.setPlaceholderText(tr("(nenastaveno – jen uživatelská knihovna)"))
        row.addWidget(self.shared_edit, 1)
        browse = QPushButton(tr("Procházet…"))
        browse.clicked.connect(self._browse_shared)
        row.addWidget(browse)
        clear = QPushButton(tr("Vymazat"))
        clear.clicked.connect(self._clear_shared)
        row.addWidget(clear)
        fl.addLayout(row)
        hint = QLabel(tr("Společná složka (např. síťový disk). Knihovny se pak "
                         "načítají ze sdílené i uživatelské; zápis jde do "
                         "uživatelské, do sdílené jen přes „Publikovat“."))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        fl.addWidget(hint)
        v.addWidget(gl)

        note = QLabel(tr("Změna jazyka se projeví v celém rozhraní."))
        note.setObjectName("hint")
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

    def _on_theme(self, _):
        SETTINGS.theme = self.theme_cb.currentData()
        SETTINGS.save()
        from .theme import apply_theme
        from .plots import apply_chart_theme
        from PySide6.QtWidgets import QApplication
        apply_theme(QApplication.instance(), SETTINGS.theme)
        apply_chart_theme(SETTINGS.theme)
        self.display_changed.emit()

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

    def _browse_shared(self):
        start = SETTINGS.shared_library_dir or ""
        path = QFileDialog.getExistingDirectory(
            self, tr("Vyberte složku sdílené knihovny"), start)
        if path:
            SETTINGS.shared_library_dir = path
            SETTINGS.save()
            self.shared_edit.setText(path)

    def _clear_shared(self):
        SETTINGS.shared_library_dir = ""
        SETTINGS.save()
        self.shared_edit.clear()
