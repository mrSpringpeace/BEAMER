"""Okno skladby složeného PID – poskládání profilů z knihovny průřezů.

Mutuje `prop.composite_parts` (list dict {section_id, material_id, dy, dz, angle}).
Vlevo tabulka částí, vpravo živý náhled sestaveného průřezu. Materiál se u částí
už zadává (uloží se), ale výpočet je zatím jednomateriálový (geometrie) – modulem
vážený vícemateriálový výpočet přijde jako další krok.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QWidget, QTableWidget,
    QComboBox, QPushButton, QLabel, QHeaderView, QDialogButtonBox,
)

from ..i18n import tr
from ..settings import fmt
from .spin import NoWheelDoubleSpinBox
from .plots import SectionCanvas


class CompositeEditorDialog(QDialog):
    def __init__(self, state, prop, parent=None):
        super().__init__(parent)
        self.state = state
        self.prop = prop
        if prop.composite_parts is None:
            prop.composite_parts = []
        self.setWindowTitle(tr("Skladba složeného průřezu") +
                            f" – {prop.name or ('PID ' + str(prop.pid))}")
        self.resize(940, 560)

        root = QHBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        root.addWidget(split)

        # ── levý sloupec: tabulka částí ──
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        hint = QLabel(tr("Poskládej profily z knihovny. Poloha dy,dz je vzájemná "
                         "mezi profily [mm]; náhled se vztahuje k těžišti sestavy."))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lv.addWidget(hint)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [tr("Profil"), tr("Materiál"), "dy", "dz", tr("úhel°"), ""])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        lv.addWidget(self.table)
        addb = QPushButton(tr("+ Přidat profil"))
        addb.clicked.connect(self._add)
        lv.addWidget(addb)
        note = QLabel(tr("Poznámka: výpočet je zatím jednomateriálový (geometrie). "
                         "Materiál částí se uloží pro budoucí vícemateriálový výpočet."))
        note.setObjectName("hint")
        note.setWordWrap(True)
        lv.addWidget(note)
        split.addWidget(left)

        # ── pravý sloupec: náhled ──
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self.canvas = SectionCanvas()
        rv.addWidget(self.canvas, 1)
        self.info = QLabel("")
        self.info.setObjectName("hint")
        rv.addWidget(self.info)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.accept)
        rv.addWidget(bb)
        split.addWidget(right)
        split.setSizes([460, 480])

        self._rebuild()

    # ── operace ──
    def _add(self):
        if not self.state.sections:
            self.info.setText(tr("Nejdřív přidej průřez do knihovny (Průřezy)."))
            return
        mid = (self.state.selected_material_id or
               (self.state.materials[0].id if self.state.materials else None))
        self.prop.composite_parts.append(
            {"section_id": self.state.sections[0].id, "material_id": mid,
             "dy": 0.0, "dz": 0.0, "angle": 0.0})
        self._rebuild()

    def _del(self, idx):
        if 0 <= idx < len(self.prop.composite_parts):
            self.prop.composite_parts.pop(idx)
            self._rebuild()

    def _set(self, idx, key, val):
        self.prop.composite_parts[idx][key] = val
        self._preview()

    def _rebuild(self):
        self.table.setRowCount(0)
        for i, part in enumerate(self.prop.composite_parts):
            r = self.table.rowCount()
            self.table.insertRow(r)
            sc = QComboBox()
            for s in self.state.sections:
                sc.addItem(s.name or tr("Průřez"), s.id)
            sc.setCurrentIndex(max(0, sc.findData(part.get("section_id"))))
            sc.currentIndexChanged.connect(
                lambda _, ii=i, c=sc: self._set(ii, "section_id", c.currentData()))
            self.table.setCellWidget(r, 0, sc)
            mc = QComboBox()
            for m in self.state.materials:
                mc.addItem(m.name, m.id)
            mc.setCurrentIndex(max(0, mc.findData(part.get("material_id"))))
            mc.currentIndexChanged.connect(
                lambda _, ii=i, c=mc: self._set(ii, "material_id", c.currentData()))
            self.table.setCellWidget(r, 1, mc)
            for col, key in ((2, "dy"), (3, "dz"), (4, "angle")):
                sp = NoWheelDoubleSpinBox()
                sp.setRange(-1e5, 1e5)
                sp.setDecimals(2)
                sp.setMaximumWidth(80)
                sp.setValue(float(part.get(key, 0.0)))
                sp.valueChanged.connect(lambda v, ii=i, k=key: self._set(ii, k, v))
                self.table.setCellWidget(r, col, sp)
            db = QPushButton("✕")
            db.setMaximumWidth(28)
            db.clicked.connect(lambda _, ii=i: self._del(ii))
            self.table.setCellWidget(r, 5, db)
        self._preview()

    def _preview(self):
        from ..composite import composite_def
        from ..section import build_section
        cdef = composite_def(self.state, self.prop)
        if cdef is None:
            self.canvas.plot(None)
            self.info.setText(tr("Přidej alespoň jeden profil."))
            return
        try:
            cs = build_section(cdef, fem=False)
            self.canvas.plot(cs)
            self.info.setText(
                f"A = {fmt(cs.A)} mm²    Iy = {fmt(cs.Iy)} mm⁴    Iz = {fmt(cs.Iz)} mm⁴")
        except Exception as e:
            self.canvas.plot(None)
            self.info.setText(tr("Chyba skladby: ") + str(e))
