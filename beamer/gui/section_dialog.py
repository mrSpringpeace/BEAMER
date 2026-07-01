"""Samostatné okno pro pohodlnou editaci průřezu (parametrický i vlastní polygon).

Vlevo volba typu + rozměry / editor polygonu, vpravo velký živý náhled a
průřezové charakteristiky. Mutuje přímo state.cross_section a emituje `changed`.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox, QGroupBox,
    QDoubleSpinBox, QLabel, QDialogButtonBox, QWidget, QPushButton,
    QFileDialog, QMessageBox, QSplitter,
)

from ..section import build_section
from ..i18n import tr
from ..settings import fmt
from .spin import NoWheelDoubleSpinBox
from .plots import SectionCanvas


class SectionEditorDialog(QDialog):
    changed = Signal()

    @classmethod
    def for_def(cls, sdef, parent=None):
        return cls(sdef, parent)

    def __init__(self, sdef, parent=None):
        super().__init__(parent)
        from .widgets import SECTION_PARAMS, SECTION_LABELS, DEFAULT_POLYGON
        self._PARAMS = SECTION_PARAMS
        self._LABELS = SECTION_LABELS
        self._DEFAULT_POLY = DEFAULT_POLYGON
        self.sdef = sdef
        self.setWindowTitle(tr("Editor průřezu"))
        self.resize(1280, 820)
        self._fem_dirty = False    # pro polygon: zda je třeba spočítat FEM

        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        # ── levý sloupec: typ + rozměry / polygon ──
        left_w = QWidget()
        left = QVBoxLayout(left_w)
        left.setContentsMargins(0, 0, 0, 0)
        g = QGroupBox(tr("Typ a rozměry"))
        gv = QVBoxLayout(g)
        self.cb = QComboBox()
        for key, label in self._LABELS.items():
            self.cb.addItem(tr(label), key)
        # ukázat všechny typy najednou, bez skrolování v rozbaleném seznamu
        self.cb.setMaxVisibleItems(len(self._LABELS) + 1)
        self.cb.setStyleSheet("QComboBox{combobox-popup:0;}")
        i = self.cb.findData(self.sdef.type)
        self.cb.setCurrentIndex(max(0, i))
        self.cb.currentIndexChanged.connect(self._on_type)
        gv.addWidget(self.cb)
        # Import .rez (Ministatik) – pohodlný import průřezu ze souboru
        self.btn_import_rez = QPushButton(tr("Import .rez (Ministatik)…"))
        self.btn_import_rez.clicked.connect(self._on_import_rez)
        gv.addWidget(self.btn_import_rez)
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        gv.addWidget(self.form_host)
        left.addWidget(g)
        left.addStretch(1)
        splitter.addWidget(left_w)

        # ── pravý sloupec: náhled + charakteristiky ──
        right_w = QWidget()
        right = QVBoxLayout(right_w)
        right.setContentsMargins(0, 0, 0, 0)
        self.canvas = SectionCanvas()
        right.addWidget(self.canvas, 1)
        self.props = QLabel()
        self.props.setStyleSheet("font-family:monospace; font-size:11px;")
        self.props.setAlignment(Qt.AlignTop)
        right.addWidget(self.props, 0)

        # tlačítko „Spočítat (FEM)" pro polygon: rychlý živý náhled bez FEM,
        # přesné hodnoty se spočtou na povel / při zavření okna
        row = QHBoxLayout()
        self.fem_btn = QPushButton(tr("Spočítat (FEM)"))
        self.fem_btn.clicked.connect(self._compute_fem)
        row.addWidget(self.fem_btn)
        self.fem_lbl = QLabel("")
        self.fem_lbl.setObjectName("hint")
        row.addWidget(self.fem_lbl, 1)
        right.addLayout(row)

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.accept)
        bb.accepted.connect(self.accept)
        right.addWidget(bb)

        splitter.addWidget(right_w)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 900])

        self._rebuild_form()
        self._refresh_preview()

    def _on_type(self, _):
        t = self.cb.currentData()
        self.sdef.type = t
        if t == "polygon":
            if not self.sdef.polygon_points:
                self.sdef.polygon_points = [dict(p) for p in self._DEFAULT_POLY]
        elif t == "construction":
            if not self.sdef.shapes:
                from .shapes_editor import default_shape
                self.sdef.shapes = [default_shape("rect")]
        else:
            self.sdef.params = {k: d for k, _, d in self._PARAMS.get(t, [])}
        self._rebuild_form()
        self._changed()

    def _on_import_rez(self):
        """Import průřezu z Ministatik .rez (Mode A obrys+díry / Mode B
        midline+thickness). Přepíše bodies/typ aktuální definice."""
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Načíst průřez (.rez)"), "",
            "Ministatik .rez (*.rez);;Všechny soubory (*)")
        if not path:
            return
        try:
            from ..rez_io import load_rez
            new_sdef = load_rez(path)
        except Exception as e:
            QMessageBox.critical(self, tr("Chyba importu"),
                                 tr("Nelze načíst .rez:\n") + f"{e}")
            return
        # nahrazení aktuální definice (mutace v place – sdef sdílí volající)
        self.sdef.type = new_sdef.type
        self.sdef.bodies = new_sdef.bodies
        self.sdef.polygon_points = None
        self.sdef.polygon_holes = None
        self.sdef.params = {}
        # přepni combo na "polygon" bez vyvolání _on_type smyčky
        i = self.cb.findData("polygon")
        if i >= 0:
            self.cb.blockSignals(True)
            self.cb.setCurrentIndex(i)
            self.cb.blockSignals(False)
        self._rebuild_form()
        self._fem_dirty = True
        self._changed()
        QMessageBox.information(
            self, tr("Import"),
            tr("Načteno") + f": {len(new_sdef.bodies)} " + tr("těleso/těles."))

    def _rebuild_form(self):
        while self.form.rowCount():
            self.form.removeRow(0)
        t = self.sdef.type
        if t == "polygon":
            from .poly_editor import PolygonEditor
            ed = PolygonEditor(self.sdef)
            ed.changed.connect(self._changed)
            self.form.addRow(ed)
            return
        if t == "construction":
            from .shapes_editor import ShapesEditor
            ed = ShapesEditor(self.sdef)
            ed.changed.connect(self._changed)
            self.form.addRow(ed)
            return
        for key, label, default in self._PARAMS.get(t, []):
            val = float(self.sdef.params.get(key, default))
            sp = NoWheelDoubleSpinBox()
            if t == "direct":            # přímý moment setrvačnosti Iy [mm⁴]
                sp.setRange(0.0, 1e12)
                sp.setDecimals(1)
                sp.setSuffix(" mm⁴")
            else:
                sp.setRange(0.01, 1e5)
                sp.setDecimals(2)
                sp.setSuffix(" mm")
            sp.setValue(val)
            sp.valueChanged.connect(lambda v, k=key: self._on_param(k, v))
            self.form.addRow(tr(label) + ":", sp)

    def _on_param(self, key, v):
        self.sdef.params[key] = v
        self._changed()

    def _changed(self):
        # při živé editaci polygonu/konstr. tvaru přeskočíme drahý FEM (jen scanline)
        if self.sdef.type in ("polygon", "construction"):
            self._fem_dirty = True
        self._refresh_preview(fem=False)
        self.changed.emit()

    def _compute_fem(self):
        self._refresh_preview(fem=True)
        self._fem_dirty = False

    def accept(self):
        if self.sdef.type in ("polygon", "construction") and self._fem_dirty:
            try:
                self._refresh_preview(fem=True)
                self._fem_dirty = False
                self.changed.emit()
            except Exception:
                pass
        super().accept()

    def _refresh_preview(self, fem=True):
        try:
            sec = build_section(self.sdef, fem=fem)
        except Exception as e:
            self.canvas.plot(None)
            self.props.setText(f"{tr('Neplatný průřez:')}\n{e}")
            return
        # status FEM (relevantní pro polygon a konstrukční tvar)
        if self.sdef.type in ("polygon", "construction"):
            self.fem_btn.setEnabled(self._fem_dirty or not fem)
            if fem and getattr(sec, "fem_used", False):
                self.fem_lbl.setText(tr("FEM přepočteno (přesné IT, Iω, střed smyku)."))
            else:
                self.fem_lbl.setText(tr("Předběžné (scanline). Stiskněte Spočítat (FEM) pro přesné hodnoty."))
        else:
            self.fem_btn.setEnabled(False)
            self.fem_lbl.setText("")
        self.canvas.plot(sec)
        femtag = " (FEM)" if getattr(sec, "fem_used", False) else ""
        sc = tr("střed smyku")
        nb = len(sec.bodies_c) if getattr(sec, "bodies_c", None) else 1
        comp_line = (tr("Kompozit: %d těles – vyhodnocováno jako celek\n") % nb) \
                    if nb > 1 else ""
        self.props.setText(
            comp_line +
            f"A   = {fmt(sec.A)} mm²\n"
            f"Iy  = {fmt(sec.Iy)} mm⁴      Iz = {fmt(sec.Iz)} mm⁴\n"
            f"Iyz = {fmt(sec.Iyz)} mm⁴\n"
            f"I1  = {fmt(sec.I1)}   I2 = {fmt(sec.I2)}   α={fmt(sec.alpha)}°\n"
            f"IT  = {fmt(sec.IT)} mm⁴{femtag}   Iω = {fmt(sec.Iw)} mm⁶\n"
            f"iy  = {fmt(sec.iy)} mm   iz = {fmt(sec.iz)} mm   it = {fmt(getattr(sec,'it',0))} mm\n"
            f"Wb,y = {fmt(getattr(sec,'Wb_y',0))}   Wb,z = {fmt(getattr(sec,'Wb_z',0))}   "
            f"Wt = {fmt(getattr(sec,'Wb_t',0))}\n"
            f"Wel,y = {fmt(getattr(sec,'Wel_y',0))}   Wpl,y = {fmt(getattr(sec,'Wpl_y',0))}   "
            f"α_pl = {fmt(getattr(sec,'alpha_pl',1.0))}\n"
            f"{sc} z_SC = {fmt(sec.z_SC)} mm   y_SC = {fmt(sec.y_SC)} mm\n"
            f"κ = {fmt(sec.kappa)}   A_sz = {fmt(sec.Asz)} mm²")
