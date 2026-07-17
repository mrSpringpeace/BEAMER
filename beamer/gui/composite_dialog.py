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
    QPushButton, QLabel, QHeaderView, QDialogButtonBox,
)

from ..i18n import tr
from ..settings import fmt
from .spin import NoWheelDoubleSpinBox, NoWheelComboBox
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
    def _usable_sections(self):
        """Knihovní profily s použitelnou geometrií. Typ „direct" (jen přímé
        charakteristiky, žádný obrys) by se do skladby tiše vynechal – proto
        se v nabídce vůbec neukazuje."""
        return [s for s in self.state.sections if self._usable_def(s)]

    @staticmethod
    def _usable_def(sd):
        """Má definice použitelnou geometrii pro skladbu? („direct" nikdy –
        syntetický obrys je jen tuhostní model.)"""
        from ..composite import section_bodies_centroidal
        if sd.type == "direct":
            return False
        try:
            return bool(section_bodies_centroidal(sd))
        except Exception:
            return False

    def _first_available_section_id(self):
        """První použitelný průřez: z projektu, jinak z knihovny profilů
        (zkopíruje se do projektu – nový projekt tak může začít skladbu rovnou
        knihovním profilem). None, když není nic."""
        usable = self._usable_sections()
        if usable:
            return usable[0].id
        from .. import library
        from .widgets import resolve_section_choice
        for _src, profs in library.load_profiles_grouped():
            for n, sd in profs:
                if self._usable_def(sd):
                    sid, _created = resolve_section_choice(
                        self.state, ("plib", n, sd))
                    return sid
        return None

    def _add(self):
        sid = self._first_available_section_id()
        if sid is None:
            self.info.setText(tr("Nejdřív přidej průřez s geometrií do knihovny "
                                 "(Průřezy). Typ „přímé zadání“ skládat nejde."))
            return
        mid = (self.state.selected_material_id or
               (self.state.materials[0].id if self.state.materials else None))
        self.prop.composite_parts.append(
            {"section_id": sid, "material_id": mid,
             "dy": 0.0, "dz": 0.0, "angle": 0.0})
        self._rebuild()

    def _del(self, idx):
        if 0 <= idx < len(self.prop.composite_parts):
            self.prop.composite_parts.pop(idx)
            self._rebuild()

    def _set(self, idx, key, val):
        self.prop.composite_parts[idx][key] = val
        self._preview()

    def _fill_part_section_combo(self, sc, current_id):
        """Průřezy projektu (použitelná geometrie) + knihovna profilů (též jen
        s geometrií – „direct" skládat nejde). Volba knihovního = kopie do
        projektu (stejný vzor jako materiály)."""
        from .. import library
        from .widgets import _HDR, _same_profile, SECTION_LABELS
        from PySide6.QtCore import Qt

        sc.blockSignals(True)
        sc.clear()
        for s in self._usable_sections():
            sc.addItem(s.name or tr("Průřez"), s.id)
        for src, profs in library.load_profiles_grouped():
            fresh = [(n, sd) for n, sd in profs
                     if self._usable_def(sd) and not any(
                         _same_profile(n, sd, ps) for ps in self.state.sections)]
            if not fresh:
                continue
            sc.addItem("— " + (tr("Sdílená") if src == "shared"
                               else tr("Uživatelská")) + " " + tr("knihovna") + " —",
                       _HDR)
            sc.model().item(sc.count() - 1).setFlags(Qt.NoItemFlags)
            for n, sd in fresh:
                sc.addItem(f"{n}  ({tr(SECTION_LABELS.get(sd.type, sd.type))})",
                           ("plib", n, sd))
        idx = sc.findData(current_id)
        sc.setCurrentIndex(max(0, idx))
        sc.blockSignals(False)

    def _set_section(self, idx, combo):
        from .widgets import _HDR, resolve_section_choice
        data = combo.currentData()
        if data == _HDR:
            return
        sid, created = resolve_section_choice(self.state, data)
        if sid is None:
            return
        self.prop.composite_parts[idx]["section_id"] = sid
        if created:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._rebuild)
        else:
            self._preview()

    def _set_material(self, idx, combo):
        from .widgets import resolve_material_choice
        mid, created = resolve_material_choice(self.state, combo.currentData())
        if mid is None:
            return                      # nadpis skupiny
        self.prop.composite_parts[idx]["material_id"] = mid
        if created:                     # comba v ostatních řádcích ať kopii vidí
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._rebuild)
        else:
            self._preview()

    def _rebuild(self):
        self.table.setRowCount(0)
        for i, part in enumerate(self.prop.composite_parts):
            r = self.table.rowCount()
            self.table.insertRow(r)
            sc = NoWheelComboBox()
            self._fill_part_section_combo(sc, part.get("section_id"))
            sc.currentIndexChanged.connect(
                lambda _, ii=i, c=sc: self._set_section(ii, c))
            self.table.setCellWidget(r, 0, sc)
            mc = NoWheelComboBox()
            from .widgets import fill_material_combo
            fill_material_combo(mc, self.state, part.get("material_id"))
            mc.currentIndexChanged.connect(
                lambda _, ii=i, c=mc: self._set_material(ii, c))
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
