"""Vstupní a výsledkové panely."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QLabel,
    QDoubleSpinBox, QComboBox, QPushButton, QScrollArea, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy, QLineEdit,
    QCheckBox, QToolButton,
)
from PySide6.QtCore import Qt as _Qt


class CollapsibleBox(QWidget):
    """Sbalitelný panel – hlavička (QToolButton se šipkou) + skrývatelný obsah."""
    def __init__(self, title="", expanded=False):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setStyleSheet("QToolButton{border:none; font-weight:bold; text-align:left;}")
        self.toggle.setToolButtonStyle(_Qt.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(_Qt.DownArrow if expanded else _Qt.RightArrow)
        self.toggle.toggled.connect(self._on_toggle)
        v.addWidget(self.toggle)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(10, 2, 2, 6)
        self.content.setVisible(expanded)
        v.addWidget(self.content)

    def _on_toggle(self, on):
        self.content.setVisible(on)
        self.toggle.setArrowType(_Qt.DownArrow if on else _Qt.RightArrow)

    def setTitle(self, t):
        self.toggle.setText(t)

from ..model import (
    Material, Support, Hinge, ControlPoint, Load, LoadCase, LoadCombination,
    CrossSectionDef, SectionSegment, new_id,
)
from ..i18n import tr
from ..settings import fmt
from .spin import NoWheelDoubleSpinBox

# parametry pro každý typ průřezu: (klíč, popisek, výchozí)
SECTION_PARAMS = {
    "rectangle": [("b", "šířka b", 100), ("h", "výška h", 200)],
    "box": [("B", "šířka B", 100), ("H", "výška H", 200), ("tw", "tl. stěny tw", 6)],
    "circle": [("D", "průměr D", 100)],
    "tube": [("Do", "vnější ⌀ Do", 100), ("t", "tloušťka t", 5)],
    "i_section": [("h", "výška h", 200), ("tw", "stojina tw", 6),
                  ("bf1", "horní pásnice bf1", 100), ("tf1", "tl. tf1", 10),
                  ("bf2", "dolní pásnice bf2", 100), ("tf2", "tl. tf2", 10)],
    "t_section": [("h", "výška h", 200), ("b", "pásnice b", 120),
                  ("tw", "stojina tw", 8), ("tf", "pásnice tf", 12)],
    "l_section": [("h", "výška h", 100), ("b", "šířka b", 100), ("t", "tloušťka t", 10)],
    "c_section": [("h", "výška h", 200), ("b", "šířka b", 80), ("t", "tloušťka t", 8)],
    "direct": [("Iy", "moment setrvačnosti Iy", 1.0e6)],
}
SECTION_LABELS = {
    "rectangle": "Obdélník", "box": "Dutý obdélník (RHS)", "circle": "Kruh",
    "tube": "Trubka (CHS)", "i_section": "I-profil", "t_section": "T-profil",
    "l_section": "L-profil", "c_section": "U/C-profil",
    "polygon": "Vlastní (polygon)", "direct": "Přímé Iy (EI model)",
}

# výchozí polygon při přepnutí na vlastní průřez (obdélník 100×200)
DEFAULT_POLYGON = [
    {"y": -50, "z": -100}, {"y": 50, "z": -100},
    {"y": 50, "z": 100}, {"y": -50, "z": 100},
]


def _fit_table(table):
    """Nastaví výšku tabulky tak, aby byly vidět VŠECHNY řádky (bez scrollu)."""
    h = table.horizontalHeader().height() + 2 * table.frameWidth()
    for r in range(table.rowCount()):
        h += table.rowHeight(r)
    if table.rowCount() == 0:
        h += 4
    table.setMinimumHeight(h)
    table.setMaximumHeight(h)


def _spin(val, mn=-1e9, mx=1e9, step=1.0, dec=3, suffix=""):
    sp = NoWheelDoubleSpinBox()
    sp.setRange(mn, mx)
    sp.setDecimals(dec)
    sp.setSingleStep(step)
    sp.setValue(val)
    if suffix:
        sp.setSuffix(suffix)
    sp.setMaximumWidth(140)
    return sp


class InputPanel(QScrollArea):
    """Levý panel se vstupy. Při změně emituje `changed`;
    změna kontrolních bodů (která nevyžaduje přepočet) emituje `control_changed`."""
    changed = Signal()
    control_changed = Signal()

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.setWidgetResizable(True)
        self._build()

    def _build(self):
        container = QWidget()
        self.layout = QVBoxLayout(container)
        self.layout.setSpacing(8)
        self.setWidget(container)

        self._build_general()
        self._build_material()
        self._build_section()
        self._build_supports()
        self._build_hinges()
        self._build_loads()
        self._build_factors()
        self._build_control_points()
        self.layout.addStretch(1)

    def _emit(self, *_):
        self.changed.emit()

    # ── obecné ──
    def _build_general(self):
        g = QGroupBox(tr("Nosník"))
        f = QFormLayout(g)
        self.len_lbl = QLabel()
        f.addRow(tr("Celková délka L:"), self.len_lbl)

        self.theory_cb = QComboBox()
        self.theory_cb.addItem("Euler–Bernoulli", "euler-bernoulli")
        self.theory_cb.addItem("Timoshenko", "timoshenko")
        idx = self.theory_cb.findData(self.state.theory)
        self.theory_cb.setCurrentIndex(max(0, idx))
        self.theory_cb.currentIndexChanged.connect(self._on_theory)
        f.addRow(tr("Teorie:"), self.theory_cb)
        self.layout.addWidget(g)
        self._update_len_label()

    def _update_len_label(self):
        if hasattr(self, "len_lbl"):
            self.len_lbl.setText(f"{self.state.length:.1f} mm")

    def _on_length(self, v):
        self.state.length = v
        self._emit()

    def _on_theory(self, _):
        self.state.theory = self.theory_cb.currentData()
        self._emit()

    # ── materiál ──
    def _build_material(self):
        g = QGroupBox(tr("Materiály (knihovna)"))
        v = QVBoxLayout(g)
        row = QHBoxLayout()
        self.mat_cb = QComboBox()
        self._reload_mat_combo()
        self.mat_cb.currentIndexChanged.connect(self._on_material)
        row.addWidget(self.mat_cb, 1)
        addb = QPushButton(tr("+ Vlastní"))
        addb.setMaximumWidth(90)
        addb.clicked.connect(self._add_custom_material)
        row.addWidget(addb)
        v.addLayout(row)

        librow = QHBoxLayout()
        save_lib = QPushButton(tr("💾 Do knihovny ▾"))
        save_lib.clicked.connect(self._material_save_menu)
        librow.addWidget(save_lib)
        from_lib = QPushButton(tr("📂 Z knihovny"))
        from_lib.clicked.connect(self._material_from_lib)
        librow.addWidget(from_lib)
        v.addLayout(librow)

        # needitovatelný popis (pro knihovní materiály)
        self.mat_info = QLabel()
        self.mat_info.setStyleSheet("color:#555; font-size:11px;")
        v.addWidget(self.mat_info)

        # editovatelný formulář (pro vlastní materiály)
        self.mat_edit_host = QWidget()
        self.mat_edit_form = QFormLayout(self.mat_edit_host)
        self.mat_edit_form.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.mat_edit_host)

        self.layout.addWidget(g)
        self._refresh_material_view()

    def _reload_mat_combo(self):
        self.mat_cb.blockSignals(True)
        self.mat_cb.clear()
        for m in self.state.materials:
            label = m.name + (tr(" (vlastní)") if getattr(m, "is_custom", False) else "")
            self.mat_cb.addItem(label, m.id)
        idx = self.mat_cb.findData(self.state.selected_material_id)
        self.mat_cb.setCurrentIndex(max(0, idx))
        self.mat_cb.blockSignals(False)

    def _on_material(self, _):
        self.state.selected_material_id = self.mat_cb.currentData()
        self._refresh_material_view()
        self._emit()

    def _add_custom_material(self):
        m = Material(new_id("mat"), tr("Vlastní materiál"),
                     E=70000, G=27000, nu=0.3, rho=2.8, Re=300, Rm=400, is_custom=True)
        self.state.materials.append(m)
        self.state.selected_material_id = m.id
        self._reload_mat_combo()
        self._refresh_material_view()
        self._emit()

    def _refresh_material_view(self):
        m = self.state.material()
        # vyčisti editor
        while self.mat_edit_form.rowCount():
            self.mat_edit_form.removeRow(0)
        if getattr(m, "is_custom", False):
            self.mat_info.setVisible(False)
            self.mat_edit_host.setVisible(True)
            name = QLineEdit(m.name)
            name.textChanged.connect(lambda s, mm=m: (setattr(mm, "name", s), self._mat_renamed()))
            self.mat_edit_form.addRow(tr("Název:"), name)
            for attr, label, suf, dec in [
                ("E", "E", " MPa", 0), ("G", "G", " MPa", 0), ("nu", "ν", "", 3),
                ("Re", "Re (mez kluzu)", " MPa", 0), ("Rm", "Rm (pevnost)", " MPa", 0),
                ("rho", "ρ", " g/cm³", 3),
            ]:
                sp = _spin(getattr(m, attr), 0, 1e6, 1.0, dec, suf)
                sp.valueChanged.connect(lambda val, a=attr, mm=m: (setattr(mm, a, val), self._emit()))
                self.mat_edit_form.addRow(tr(label) + ":", sp)
            db = QPushButton(tr("Smazat tento materiál"))
            db.clicked.connect(lambda _, mm=m: self._del_material(mm))
            self.mat_edit_form.addRow(db)
        else:
            self.mat_edit_host.setVisible(False)
            self.mat_info.setVisible(True)
            self.mat_info.setText(
                f"E={m.E:.0f} MPa  G={m.G:.0f} MPa\nRe={m.Re:.0f} MPa  Rm={m.Rm:.0f} MPa  ρ={m.rho} g/cm³")

    def _mat_renamed(self):
        idx = self.mat_cb.currentIndex()
        m = self.state.material()
        self.mat_cb.setItemText(idx, m.name + tr(" (vlastní)"))
        self._emit()

    def _material_save_menu(self):
        from .. import library
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        a_user = menu.addAction(tr("Uložit do uživatelské knihovny"))
        a_user.triggered.connect(self._save_material_to_lib)
        a_pub = menu.addAction(tr("Publikovat do sdílené knihovny…"))
        a_pub.setEnabled(library.shared_dir_configured())
        a_pub.triggered.connect(self._publish_material)
        menu.exec(self.cursor().pos())

    def _save_material_to_lib(self):
        from .. import library
        from PySide6.QtWidgets import QMessageBox
        m = self.state.material()
        library.save_material(m)
        QMessageBox.information(self, tr("Knihovna"),
                                tr("Materiál uložen do uživatelské knihovny: ") + m.name)

    def _publish_material(self):
        from .. import library
        from PySide6.QtWidgets import QMessageBox
        if not library.shared_dir_configured():
            QMessageBox.information(self, tr("Sdílená knihovna"),
                tr("Nejprve nastavte složku sdílené knihovny v Nastavení."))
            return
        m = self.state.material()
        if QMessageBox.question(
                self, tr("Publikovat do sdílené"),
                tr("Publikovat materiál „%s“ do SDÍLENÉ knihovny pro všechny uživatele?") % m.name,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if QMessageBox.warning(
                self, tr("Potvrdit publikaci"),
                tr("Sdílená knihovna je společná pro celý tým. Opravdu zapsat?"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if library.publish_material(m):
            QMessageBox.information(self, tr("Sdílená knihovna"),
                                    tr("Materiál publikován do sdílené knihovny: ") + m.name)
        else:
            QMessageBox.critical(self, tr("Sdílená knihovna"),
                                 tr("Publikace selhala (zkontrolujte cestu a práva)."))

    def _material_from_lib(self):
        from .. import library
        from PySide6.QtWidgets import QMenu
        groups = library.load_materials_grouped()
        menu = QMenu(self)
        any_item = False
        for src, mats in groups:
            if not mats:
                continue
            menu.addSection(tr("Sdílená") if src == "shared" else tr("Uživatelská"))
            for m in mats:
                any_item = True
                act = menu.addAction(m.name)
                act.triggered.connect(lambda _=False, mm=m: self._add_lib_material(mm))
        if not any_item:
            menu.addAction(tr("(knihovna je prázdná)")).setEnabled(False)
        menu.exec(self.cursor().pos())

    def _add_lib_material(self, mat):
        m = Material(new_id("mat"), mat.name, mat.E, mat.G, mat.nu, mat.rho,
                     mat.Re, mat.Rm, is_custom=True)
        self.state.materials.append(m)
        self.state.selected_material_id = m.id
        self._reload_mat_combo()
        self._refresh_material_view()
        self._emit()

    def _del_material(self, m):
        if len(self.state.materials) <= 1:
            return
        self.state.materials.remove(m)
        self.state.selected_material_id = self.state.materials[0].id
        self._reload_mat_combo()
        self._refresh_material_view()
        self._emit()

    def _clear_layout(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
            elif it.layout():
                self._clear_layout(it.layout())

    # ── úseky nosníku (každý: délka + materiál + průřez) ──
    def _build_section(self):
        from .. import defaults
        defaults.ensure_parts(self.state)
        g = QGroupBox(tr("Úseky nosníku"))
        v = QVBoxLayout(g)
        info = QLabel(tr("Každý úsek má délku, materiál a průřez (vč. náběhu)."))
        info.setWordWrap(True)
        info.setStyleSheet("color:#555; font-size:11px;")
        v.addWidget(info)
        self.parts_host = QWidget()
        self.parts_layout = QVBoxLayout(self.parts_host)
        self.parts_layout.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.parts_host)
        addb = QPushButton(tr("+ Přidat úsek"))
        addb.clicked.connect(self._add_part)
        v.addWidget(addb)
        self.layout.addWidget(g)
        self._refresh_parts()

    def _part_title(self, i, seg):
        mat = next((m for m in self.state.materials if m.id == seg.material_id), None)
        mname = mat.name if mat else "?"
        tp = tr(SECTION_LABELS.get(seg.sec1.type, seg.sec1.type))
        return f"{tr('Úsek')} {i+1}:  L={seg.length:.0f} mm · {mname} · {tp}"

    def _refresh_parts(self):
        self._clear_layout(self.parts_layout)
        self._part_boxes = []
        for i, seg in enumerate(self.state.section_segments):
            box = self._part_box(i, seg)
            self._part_boxes.append(box)
            self.parts_layout.addWidget(box)
        self._update_len_label()

    def _part_box(self, i, seg):
        box = CollapsibleBox(self._part_title(i, seg), expanded=(len(self.state.section_segments) <= 2))
        cl = box.content_layout
        f = QFormLayout()
        cl.addLayout(f)
        # délka
        lsp = _spin(seg.length, 0.01, 1e6, 50, 1, " mm")
        lsp.valueChanged.connect(lambda val, s=seg, b=box: self._set_part_length(s, val, b))
        f.addRow(tr("Délka:"), lsp)
        # materiál (odkaz do knihovny)
        mcb = QComboBox()
        for m in self.state.materials:
            mcb.addItem(m.name, m.id)
        mcb.setCurrentIndex(max(0, mcb.findData(seg.material_id)))
        mcb.currentIndexChanged.connect(lambda _, s=seg, c=mcb, b=box, idx=i:
                                        self._on_part_material(s, c.currentData(), b, idx))
        f.addRow(tr("Materiál:"), mcb)
        # průřez A
        ea = QPushButton(f"{tr('Průřez')}: {tr(SECTION_LABELS.get(seg.sec1.type, seg.sec1.type))} …")
        ea.clicked.connect(lambda _, s=seg: self._edit_seg_section(s, "sec1"))
        cl.addWidget(ea)
        # profily knihovna / import / export (pro sec1)
        prow = QHBoxLayout()
        for txt, fn in ((tr("💾 Uložit profil ▾"), self._profile_save_menu),
                        (tr("📂 Z knihovny"), self._profile_from_lib),
                        (tr("⤓ Import"), self._import_profile),
                        (tr("⤒ Export"), self._export_profile)):
            b = QPushButton(txt)
            b.clicked.connect(lambda _, s=seg, fn=fn: fn(s))
            prow.addWidget(b)
        cl.addLayout(prow)
        # náběh
        taper = QCheckBox(tr("Náběh (tapered) → průřez B"))
        taper.setChecked(seg.tapered)
        taper.toggled.connect(lambda on, s=seg: self._toggle_taper(s, on))
        cl.addWidget(taper)
        if seg.tapered:
            eb = QPushButton(f"{tr('Průřez B')}: {tr(SECTION_LABELS.get(seg.sec2.type, seg.sec2.type))} …")
            eb.clicked.connect(lambda _, s=seg: self._edit_seg_section(s, "sec2"))
            cl.addWidget(eb)
        # smazat úsek
        if len(self.state.section_segments) > 1:
            db = QPushButton(tr("Smazat úsek"))
            db.clicked.connect(lambda _, s=seg: self._del_part(s))
            cl.addWidget(db)
        return box

    def _set_part_length(self, seg, new_len, box):
        parts = self.state.section_segments
        lengths = [p.length for p in parts]
        lengths[parts.index(seg)] = max(new_len, 0.01)
        x = 0.0
        for p, Lp in zip(parts, lengths):
            p.x1 = x
            p.x2 = x + Lp
            x += Lp
        self.state.length = x
        box.setTitle(self._part_title(parts.index(seg), seg))
        self._update_len_label()
        self._emit()

    def _on_part_material(self, seg, mid, box, idx):
        seg.material_id = mid
        seg.E = None        # zvolený materiál řídí E/G (zruší přímý E override z .nos)
        box.setTitle(self._part_title(idx, seg))
        self._emit()

    def _add_part(self):
        import copy as _c
        parts = self.state.section_segments
        base = parts[-1] if parts else None
        sec = _c.deepcopy(base.sec1) if base else _c.deepcopy(self.state.cross_section)
        mid = base.material_id if base else self.state.selected_material_id
        x1 = parts[-1].x2 if parts else 0.0
        parts.append(SectionSegment(x1, x1 + 1000.0, sec, None, material_id=mid))
        # přepočet celkové délky
        self.state.length = parts[-1].x2
        self._refresh_parts()
        self._emit()

    def _del_part(self, seg):
        parts = self.state.section_segments
        parts.remove(seg)
        x = 0.0
        for p in parts:
            Lp = p.length
            p.x1 = x
            p.x2 = x + Lp
            x += Lp
        self.state.length = x if parts else self.state.length
        self._refresh_parts()
        self._emit()

    def _toggle_taper(self, seg, on):
        import copy as _c
        if on and seg.sec2 is None:
            seg.sec2 = _c.deepcopy(seg.sec1)
        if not on:
            seg.sec2 = None
        self._refresh_parts()
        self._emit()

    def _edit_seg_section(self, seg, which):
        from .section_dialog import SectionEditorDialog
        dlg = SectionEditorDialog.for_def(getattr(seg, which), self)
        dlg.changed.connect(self._emit)
        dlg.exec()
        self._refresh_parts()
        self._emit()

    # ── profily: knihovna + import/export (pro daný úsek) ──
    def _apply_profile(self, seg, sdef):
        import copy as _c
        seg.sec1 = _c.deepcopy(sdef)
        self._refresh_parts()
        self._emit()

    def _profile_save_menu(self, seg):
        from .. import library
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        a_user = menu.addAction(tr("Uložit do uživatelské knihovny"))
        a_user.triggered.connect(lambda: self._save_profile(seg))
        a_pub = menu.addAction(tr("Publikovat do sdílené knihovny…"))
        a_pub.setEnabled(library.shared_dir_configured())
        a_pub.triggered.connect(lambda: self._publish_profile(seg))
        menu.exec(self.cursor().pos())

    def _save_profile(self, seg):
        from .. import library
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        name, ok = QInputDialog.getText(self, tr("Uložit profil"), tr("Název profilu:"))
        if ok and name.strip():
            library.save_profile(name.strip(), seg.sec1)
            QMessageBox.information(self, tr("Knihovna"),
                                   tr("Profil uložen do uživatelské knihovny: ") + name.strip())

    def _publish_profile(self, seg):
        from .. import library
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        if not library.shared_dir_configured():
            QMessageBox.information(self, tr("Sdílená knihovna"),
                tr("Nejprve nastavte složku sdílené knihovny v Nastavení."))
            return
        name, ok = QInputDialog.getText(self, tr("Publikovat profil"), tr("Název profilu:"))
        name = name.strip() if ok else ""
        if not name:
            return
        if QMessageBox.question(
                self, tr("Publikovat do sdílené"),
                tr("Publikovat profil „%s“ do SDÍLENÉ knihovny pro všechny uživatele?") % name,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if QMessageBox.warning(
                self, tr("Potvrdit publikaci"),
                tr("Sdílená knihovna je společná pro celý tým. Opravdu zapsat?"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if library.publish_profile(name, seg.sec1):
            QMessageBox.information(self, tr("Sdílená knihovna"),
                                   tr("Profil publikován do sdílené knihovny: ") + name)
        else:
            QMessageBox.critical(self, tr("Sdílená knihovna"),
                                 tr("Publikace selhala (zkontrolujte cestu a práva)."))

    def _profile_from_lib(self, seg):
        from .. import library
        from PySide6.QtWidgets import QMenu
        groups = library.load_profiles_grouped()
        menu = QMenu(self)
        any_item = False
        for src, profs in groups:
            if not profs:
                continue
            menu.addSection(tr("Sdílená") if src == "shared" else tr("Uživatelská"))
            for name, sdef in profs:
                any_item = True
                act = menu.addAction(f"{name}  ({tr(SECTION_LABELS.get(sdef.type, sdef.type))})")
                act.triggered.connect(lambda _=False, s=sdef, sg=seg: self._apply_profile(sg, s))
        if not any_item:
            menu.addAction(tr("(knihovna je prázdná)")).setEnabled(False)
        menu.exec(self.cursor().pos())

    def _import_profile(self, seg):
        from .. import library
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        path, _f = QFileDialog.getOpenFileName(self, tr("Import profilu"), "",
                                               "BEAMER profil (*.json)")
        if not path:
            return
        try:
            name, sdef = library.import_profile(path)
            self._apply_profile(seg, sdef)
        except Exception as e:
            QMessageBox.critical(self, tr("Chyba"), tr("Nelze importovat: ") + str(e))

    def _export_profile(self, seg):
        from .. import library
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        path, _f = QFileDialog.getSaveFileName(self, tr("Export profilu"), "profil.json",
                                               "BEAMER profil (*.json)")
        if not path:
            return
        try:
            library.export_profile(seg.sec1, seg.sec1.type, path)
        except Exception as e:
            QMessageBox.critical(self, tr("Chyba"), tr("Nelze exportovat: ") + str(e))

    # ── podpory ──
    def _build_supports(self):
        g = QGroupBox(tr("Podpory"))
        v = QVBoxLayout(g)
        self.sup_table = QTableWidget(0, 5)
        self.sup_table.setHorizontalHeaderLabels(["#", "x [mm]", tr("typ"), tr("úhel [°]"), ""])
        self.sup_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.sup_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.sup_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sup_table.verticalHeader().setVisible(False)
        v.addWidget(self.sup_table)
        btn = QPushButton(tr("+ Přidat podporu"))
        btn.clicked.connect(self._add_support)
        v.addWidget(btn)
        self.layout.addWidget(g)
        self._refresh_supports()

    def _refresh_supports(self):
        self.sup_table.setRowCount(0)
        for i, sup in enumerate(self.state.supports):
            r = self.sup_table.rowCount()
            self.sup_table.insertRow(r)
            num = QTableWidgetItem(str(i + 1))
            num.setTextAlignment(Qt.AlignCenter)
            num.setFlags(Qt.ItemIsEnabled)
            self.sup_table.setItem(r, 0, num)
            xsp = _spin(sup.x, 0, 1e6, 50, 1)
            xsp.valueChanged.connect(lambda val, s=sup: (setattr(s, "x", val), self._emit()))
            self.sup_table.setCellWidget(r, 1, xsp)
            cb = QComboBox()
            for tp, lbl in [("pin", "kloub"), ("roller", "rolna"), ("fixed", "vetknutí")]:
                cb.addItem(tr(lbl), tp)
            cb.setCurrentIndex(cb.findData(sup.type))
            cb.currentIndexChanged.connect(lambda _, s=sup, c=cb: (setattr(s, "type", c.currentData()), self._emit()))
            self.sup_table.setCellWidget(r, 2, cb)
            asp = _spin(sup.angle, -180, 180, 5, 0)
            asp.valueChanged.connect(lambda val, s=sup: (setattr(s, "angle", val), self._emit()))
            self.sup_table.setCellWidget(r, 3, asp)
            db = QPushButton("✕")
            db.setMaximumWidth(30)
            db.clicked.connect(lambda _, s=sup: self._del_support(s))
            self.sup_table.setCellWidget(r, 4, db)
        _fit_table(self.sup_table)

    def _add_support(self):
        self.state.supports.append(Support(new_id("sup"), 0, "pin", 0))
        self._refresh_supports()
        self._emit()

    def _del_support(self, sup):
        self.state.supports.remove(sup)
        self._refresh_supports()
        self._emit()

    # ── klouby ──
    def _build_hinges(self):
        g = QGroupBox(tr("Klouby"))
        v = QVBoxLayout(g)
        self.hinge_table = QTableWidget(0, 2)
        self.hinge_table.setHorizontalHeaderLabels(["x [mm]", ""])
        self.hinge_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hinge_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.hinge_table.verticalHeader().setVisible(False)
        v.addWidget(self.hinge_table)
        btn = QPushButton(tr("+ Přidat kloub"))
        btn.clicked.connect(self._add_hinge)
        v.addWidget(btn)
        self.layout.addWidget(g)
        self._refresh_hinges()

    def _refresh_hinges(self):
        self.hinge_table.setRowCount(0)
        for h in self.state.hinges:
            r = self.hinge_table.rowCount()
            self.hinge_table.insertRow(r)
            xsp = _spin(h.x, 0, 1e6, 50, 1)
            xsp.valueChanged.connect(lambda val, hh=h: (setattr(hh, "x", val), self._emit()))
            self.hinge_table.setCellWidget(r, 0, xsp)
            db = QPushButton("✕")
            db.setMaximumWidth(30)
            db.clicked.connect(lambda _, hh=h: self._del_hinge(hh))
            self.hinge_table.setCellWidget(r, 1, db)
        _fit_table(self.hinge_table)

    def _add_hinge(self):
        self.state.hinges.append(Hinge(new_id("hinge"), self.state.length/2))
        self._refresh_hinges()
        self._emit()

    def _del_hinge(self, h):
        self.state.hinges.remove(h)
        self._refresh_hinges()
        self._emit()

    # ── kontrolní body (report, neovlivní výpočet) ──
    def _build_control_points(self):
        g = QGroupBox(tr("Kontrolní body"))
        v = QVBoxLayout(g)
        hint = QLabel(tr("Volitelné řezy, ve kterých se vypíšou výsledky "
                         "(karta Výsledky + export). Nemění výpočet."))
        hint.setStyleSheet("color:#666; font-size:11px;")
        hint.setWordWrap(True)
        v.addWidget(hint)
        self.cp_table = QTableWidget(0, 3)
        self.cp_table.setHorizontalHeaderLabels(["x [mm]", tr("název"), ""])
        self.cp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cp_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cp_table.verticalHeader().setVisible(False)
        v.addWidget(self.cp_table)
        btn = QPushButton(tr("+ Přidat bod"))
        btn.clicked.connect(self._add_control_point)
        v.addWidget(btn)
        self.layout.addWidget(g)
        self._refresh_control_points()

    def _refresh_control_points(self):
        self.cp_table.setRowCount(0)
        for cp in self.state.control_points:
            r = self.cp_table.rowCount()
            self.cp_table.insertRow(r)
            xsp = _spin(cp.x, 0, 1e6, 50, 1)
            xsp.valueChanged.connect(
                lambda val, c=cp: (setattr(c, "x", val), self._emit_control()))
            self.cp_table.setCellWidget(r, 0, xsp)
            nm = QLineEdit(cp.name)
            nm.setPlaceholderText(tr("(volitelné)"))
            nm.textChanged.connect(
                lambda s, c=cp: (setattr(c, "name", s), self._emit_control()))
            self.cp_table.setCellWidget(r, 1, nm)
            db = QPushButton("✕")
            db.setMaximumWidth(30)
            db.clicked.connect(lambda _, c=cp: self._del_control_point(c))
            self.cp_table.setCellWidget(r, 2, db)
        _fit_table(self.cp_table)

    def _emit_control(self, *_):
        """Změna kontrolních bodů – nevyžaduje přepočet, jen překreslení
        výsledků/schématu."""
        self.control_changed.emit()

    def _add_control_point(self):
        self.state.control_points.append(
            ControlPoint(new_id("cp"), self.state.length / 2))
        self._refresh_control_points()
        self._emit_control()

    def _del_control_point(self, cp):
        self.state.control_points.remove(cp)
        self._refresh_control_points()
        self._emit_control()

    # ── zatížení ──
    def _build_loads(self):
        g = QGroupBox(tr("Zatížení"))
        v = QVBoxLayout(g)
        self.loads_host = QWidget()
        self.loads_layout = QVBoxLayout(self.loads_host)
        self.loads_layout.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.loads_host)
        row = QHBoxLayout()
        for tp, lbl in [("point_force", "+ Síla"), ("distributed", "+ Spojité"),
                        ("moment", "+ Moment"), ("torsion", "+ Krut")]:
            b = QPushButton(tr(lbl))
            b.clicked.connect(lambda _, t=tp: self._add_load(t))
            row.addWidget(b)
        v.addLayout(row)
        self.layout.addWidget(g)
        self._refresh_loads()

    def _refresh_loads(self):
        while self.loads_layout.count():
            w = self.loads_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        lc_id = self.state.load_cases[0].id if self.state.load_cases else ""
        for ld in self.state.loads:
            self.loads_layout.addWidget(self._load_row(ld))

    def _load_title(self, ld):
        labels = {"point_force": "Bodová síla", "distributed": "Spojité",
                  "moment": "Ohyb. moment", "torsion": "Krut"}
        base = tr(labels.get(ld.type, ld.type))
        nm = f" · {ld.name}" if ld.name else ""
        if ld.type == "point_force":
            v = f"  Fz={ld.Fz:.0f} N @ x={ld.x:.0f}"
        elif ld.type == "distributed":
            v = f"  q={ld.q1:.1f}→{ld.q2:.1f} ({ld.x1:.0f}–{ld.x2:.0f})"
        elif ld.type == "moment":
            v = f"  My={ld.My:.0f} @ x={ld.x:.0f}"
        else:
            v = f"  Mx={ld.Mx:.0f} @ x={ld.x:.0f}"
        return f"{base}{nm}{v}"

    def _load_row(self, ld):
        n = len(self.state.loads)
        box = CollapsibleBox(self._load_title(ld), expanded=(n <= 3))
        cl = box.content_layout
        f = QFormLayout()
        cl.addLayout(f)

        name = QLineEdit(ld.name)
        name.setPlaceholderText(tr("popisek zatížení"))
        name.textChanged.connect(lambda s, l=ld, b=box: (setattr(l, "name", s),
                                                         b.setTitle(self._load_title(l)), self._emit()))
        f.addRow(tr("Název:"), name)

        def bind(attr, suffix, dec=2, step=1.0):
            sp = _spin(getattr(ld, attr), -1e9, 1e9, step, dec, suffix)
            sp.valueChanged.connect(lambda v, a=attr, b=box: (setattr(ld, a, v),
                                                             b.setTitle(self._load_title(ld)), self._emit()))
            return sp

        if ld.type == "point_force":
            f.addRow("x:", bind("x", " mm", 1, 50))
            f.addRow("Fx:", bind("Fx", " N"))
            f.addRow(tr("Fz (+nahoru):"), bind("Fz", " N"))
            f.addRow(tr("excentricita:"), bind("eccentricity", " mm"))
        elif ld.type == "distributed":
            f.addRow("x1:", bind("x1", " mm", 1, 50))
            f.addRow("x2:", bind("x2", " mm", 1, 50))
            f.addRow("q1:", bind("q1", " N/mm"))
            f.addRow("q2:", bind("q2", " N/mm"))
        elif ld.type == "moment":
            f.addRow("x:", bind("x", " mm", 1, 50))
            f.addRow("My:", bind("My", " N·mm"))
        elif ld.type == "torsion":
            f.addRow("x:", bind("x", " mm", 1, 50))
            f.addRow("Mx:", bind("Mx", " N·mm"))

        db = QPushButton(tr("Smazat zatížení"))
        db.clicked.connect(lambda _, l=ld: self._del_load(l))
        cl.addWidget(db)
        return box

    def _add_load(self, tp):
        lc_id = self.state.load_cases[0].id if self.state.load_cases else ""
        ld = Load(new_id("load"), tp, "Zatížení", lc_id)
        if tp == "distributed":
            ld.x1 = 0
            ld.x2 = self.state.length
            ld.q1 = ld.q2 = -1.0
        elif tp == "point_force":
            ld.x = self.state.length/2
            ld.Fz = -1000.0
        elif tp == "moment":
            ld.x = self.state.length/2
            ld.My = 1e5
        elif tp == "torsion":
            ld.x = self.state.length/2
            ld.Mx = 1e5
        self.state.loads.append(ld)
        self._refresh_loads()
        self._emit()

    def _del_load(self, ld):
        self.state.loads.remove(ld)
        self._refresh_loads()
        self._emit()

    # ── součinitel + plasticita ──
    def _build_factors(self):
        g = QGroupBox(tr("Součinitel"))
        f = QFormLayout(g)
        self.af_sp = _spin(self.state.additional_factor, 0.0, 100.0, 0.05, 3)
        self.af_sp.valueChanged.connect(lambda v: (setattr(self.state, "additional_factor", v), self._emit()))
        f.addRow(tr("Dodatečný součinitel:"), self.af_sp)
        note = QLabel(tr("Zatížení se zadává jako početní (ultimate) síla."))
        note.setWordWrap(True)
        note.setStyleSheet("color:#666; font-size:11px;")
        f.addRow(note)

        self.plast_cb = QCheckBox(tr("Využít součinitel plasticity (RF_ultimate)"))
        self.plast_cb.setChecked(self.state.plasticity_enabled)
        self.plast_cb.toggled.connect(self._on_plast_toggle)
        f.addRow(self.plast_cb)
        self.plast_method_cb = QComboBox()
        self.plast_method_cb.addItem(tr("analyticky (W_pl/W_el)"), "analytic")
        self.plast_method_cb.addItem(tr("tabulkově (známé profily)"), "tabular")
        self.plast_method_cb.setCurrentIndex(
            max(0, self.plast_method_cb.findData(self.state.plasticity_method)))
        self.plast_method_cb.currentIndexChanged.connect(self._on_plast_method)
        self.plast_method_cb.setEnabled(self.state.plasticity_enabled)
        f.addRow(tr("Metoda α_pl:"), self.plast_method_cb)
        self.layout.addWidget(g)

    def _on_plast_toggle(self, on):
        self.state.plasticity_enabled = bool(on)
        self.plast_method_cb.setEnabled(bool(on))
        self._emit()

    def _on_plast_method(self, _):
        self.state.plasticity_method = self.plast_method_cb.currentData()
        self._emit()

    def reload_from_state(self):
        """Přestaví celý panel podle aktuálního state (po načtení projektu)."""
        old = self.takeWidget()
        if old:
            old.deleteLater()
        self._build()


class ResultsPanel(QWidget):
    """Tabulka průřezových charakteristik (živě) + extrémů VVÚ a MS (na výpočet).

    Sekce „Průřez" se aktualizuje ihned při změně dimenzí/typu;
    sekce „VVÚ" a „Posouzení" až po stisku Spočítat.
    """

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([tr("Veličina"), tr("Hodnota")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        v.addWidget(self.table)
        self._section_rows = []
        self._analysis_rows = []

    def _render(self):
        rows = self._section_rows + self._analysis_rows
        self.table.setRowCount(0)
        for name, val in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(name))
            self.table.setItem(r, 1, QTableWidgetItem(val))

    def set_section(self, sec, title=None):
        """Živá aktualizace charakteristik průřezu (bez VVÚ/MS)."""
        if title is None:
            title = tr("— Průřez —")
        rows = []
        if sec and sec.valid:
            rows += [
                (title, ""),
                ("A [mm²]", fmt(sec.A)),
                ("Iy [mm⁴]", fmt(sec.Iy)),
                ("Iz [mm⁴]", fmt(sec.Iz)),
                ("Iyz [mm⁴]", fmt(sec.Iyz)),
                ("I1 / I2 [mm⁴]", f"{fmt(sec.I1)} / {fmt(sec.I2)}"),
                ("α [°]", fmt(sec.alpha)),
                ("IT (St.Venant) [mm⁴]", fmt(sec.IT)),
                ("Iω [mm⁶]", fmt(sec.Iw)),
                (tr("metoda IT/Iω"), tr("FEM (přesné)") if getattr(sec, "fem_used", False) else tr("scanline")),
                ("Wy_top / Wy_bot [mm³]", f"{fmt(sec.Wy_top)} / {fmt(sec.Wy_bot)}"),
                ("Wb,y = Iy/iy [mm³]", fmt(getattr(sec, "Wb_y", 0))),
                ("Wb,z = Iz/iz [mm³]", fmt(getattr(sec, "Wb_z", 0))),
                ("Wt = IT/it [mm³]", fmt(getattr(sec, "Wb_t", 0))),
                ("Wel,y / Wpl,y [mm³]", f"{fmt(getattr(sec,'Wel_y',0))} / {fmt(getattr(sec,'Wpl_y',0))}"),
                ("α_pl,y (souč. plasticity)", fmt(getattr(sec, "alpha_pl", 1.0))),
                ("iy / iz [mm]", f"{fmt(sec.iy)} / {fmt(sec.iz)}"),
                (tr("střed smyku z_SC [mm]"), fmt(sec.z_SC)),
                (tr("κ (Timoshenko)"), fmt(sec.kappa)),
                ("A_sz [mm²]", fmt(sec.Asz)),
            ]
        else:
            rows += [(title, ""), (tr("neplatný průřez"), "")]
        self._section_rows = rows
        self._render()

    def set_analysis(self, result, state, margins):
        """VVÚ extrémy + MS – po výpočtu."""
        rows = []
        if result and result.is_stable and result.points:
            N = [p.N for p in result.points]
            V = [p.V for p in result.points]
            M = [p.M for p in result.points]
            Mk = [p.Mk for p in result.points]
            w = [p.w for p in result.points]
            rows += [
                (tr("— VVÚ (extrémy) —"), ""),
                ("N max/min [N]", f"{fmt(max(N))} / {fmt(min(N))}"),
                ("V max/min [N]", f"{fmt(max(V))} / {fmt(min(V))}"),
                ("M max/min [N·mm]", f"{fmt(max(M))} / {fmt(min(M))}"),
                ("Mk max/min [N·mm]", f"{fmt(max(Mk))} / {fmt(min(Mk))}"),
                ("w max/min [mm]", f"{fmt(max(w))} / {fmt(min(w))}"),
            ]
            for i, rc in enumerate(result.reactions):
                rows.append((f"{tr('Reakce')} {i+1} (x={rc.x:.0f}) Rz [N]", fmt(rc.Rz)))
        if margins:
            crit = min(margins, key=lambda m: m.RF)
            rows += [
                (tr("— Posouzení —"), ""),
                ("σ_red max [MPa]", fmt(max(m.mises_max for m in margins))),
                ("RF_min", f"{fmt(crit.RF)} ({crit.critical}) @ x={crit.x:.0f}"),
                ("RF_yield / RF_ult", f"{fmt(crit.RF_yield)} / {fmt(crit.RF_ultimate)}"),
            ]
        self._analysis_rows = rows
        self._render()

    def clear_analysis(self):
        self._analysis_rows = [(tr("— VVÚ / posouzení —"), tr("stiskněte Spočítat"))]
        self._render()


class ReportPanel(QWidget):
    """Karta Report: hodnoty (VVÚ, napětí, RF) v libovolně zvoleném řezu x.

    Souřadnici lze zadat ručně, nebo skočit tlačítky na charakteristické řezy
    (max |V|, max |M|, max |Mk|, nejkritičtější řez). Data se naplní přes
    `set_context(result, state, reserves)` po výpočtu.
    """

    def __init__(self):
        super().__init__()
        self._result = None
        self._state = None
        self._reserves = None

        v = QVBoxLayout(self)

        # ── volba souřadnice ──
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Souřadnice x [mm]:")))
        self.x_spin = QDoubleSpinBox()
        self.x_spin.setDecimals(1)
        self.x_spin.setRange(0.0, 1e9)
        self.x_spin.setSingleStep(10.0)
        self.x_spin.setKeyboardTracking(False)
        row.addWidget(self.x_spin, 1)
        self.btn_show = QPushButton(tr("Zobrazit"))
        self.btn_show.clicked.connect(self._on_show)
        row.addWidget(self.btn_show)
        v.addLayout(row)

        # ── tlačítka na charakteristické řezy ──
        grid = QHBoxLayout()
        self.btn_v = QPushButton(tr("Max |V|"))
        self.btn_m = QPushButton(tr("Max |M|"))
        self.btn_mk = QPushButton(tr("Max |Mk|"))
        self.btn_crit = QPushButton(tr("Kritický (min RF)"))
        self.btn_v.clicked.connect(lambda: self._jump_extremum("V"))
        self.btn_m.clicked.connect(lambda: self._jump_extremum("M"))
        self.btn_mk.clicked.connect(lambda: self._jump_extremum("Mk"))
        self.btn_crit.clicked.connect(self._jump_critical)
        for b in (self.btn_v, self.btn_m, self.btn_mk, self.btn_crit):
            grid.addWidget(b)
        v.addLayout(grid)

        # ── výstupní tabulka ──
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([tr("Veličina"), tr("Hodnota")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        v.addWidget(self.table, 1)

        self._set_enabled(False)
        self._info(tr("Spusťte výpočet (Spočítat) a zvolte řez."))

    # ── veřejné API ──
    def set_context(self, result, state, reserves):
        self._result = result
        self._state = state
        self._reserves = reserves
        ok = bool(result and getattr(result, "is_stable", False) and result.points)
        self._set_enabled(ok)
        if not ok:
            self._info(tr("Výsledek není k dispozici (nosník nestabilní?)."))
            return
        # rozsah x dle délky nosníku, klampni aktuální hodnotu
        L = float(getattr(state, "length", 0.0) or result.points[-1].x)
        self.x_spin.setMaximum(L)
        if self.x_spin.value() > L:
            self.x_spin.setValue(L)
        self._show_at(self.x_spin.value())

    # ── interní ──
    def _set_enabled(self, on):
        for wdg in (self.x_spin, self.btn_show, self.btn_v, self.btn_m,
                    self.btn_mk, self.btn_crit):
            wdg.setEnabled(on)

    def _info(self, msg):
        self.table.setRowCount(0)
        self.table.insertRow(0)
        self.table.setItem(0, 0, QTableWidgetItem(msg))
        self.table.setItem(0, 1, QTableWidgetItem(""))

    def _on_show(self):
        self._show_at(self.x_spin.value())

    def _jump_extremum(self, attr):
        from ..analysis import extremum_x
        x = extremum_x(self._result, attr)
        if x is None:
            return
        self._set_x(x)

    def _jump_critical(self):
        from ..analysis import critical_x
        x = critical_x(self._reserves)
        if x is None:
            return
        self._set_x(x)

    def _set_x(self, x):
        self.x_spin.blockSignals(True)
        self.x_spin.setValue(float(x))
        self.x_spin.blockSignals(False)
        self._show_at(float(x))

    def _show_at(self, x):
        from ..analysis import values_at_x
        import math
        d = values_at_x(self._result, self._state, x)
        if d is None:
            self._info(tr("Výsledek není k dispozici."))
            return
        sec = d["section"]
        mat = d["material"]
        deg = 180.0 / math.pi
        rows = [
            (f"— {tr('Řez')} x = {fmt(d['x'])} mm —", ""),
            (tr("— Vnitřní účinky —"), ""),
            ("N [N]", fmt(d["N"])),
            ("V [N]", fmt(d["V"])),
            ("M [N·mm]", fmt(d["M"])),
            ("Mk [N·mm]", fmt(d["Mk"])),
            ("w (průhyb) [mm]", fmt(d["w"])),
            ("φ (ohyb. pootočení) [°]", fmt(d["phi"] * deg)),
            ("θ (torzní pootočení) [°]", fmt(d["theta"] * deg)),
        ]
        if sec is not None and getattr(sec, "valid", False):
            rows += [
                (tr("— Průřez v řezu —"), ""),
                (tr("typ"), str(getattr(sec, "section_type", "?"))),
                ("A [mm²]", fmt(sec.A)),
                ("Iy [mm⁴]", fmt(sec.Iy)),
                ("IT [mm⁴]", fmt(sec.IT)),
            ]
        rows += [
            (tr("— Napětí —"), ""),
            ("σ max [MPa]", fmt(d["sigma_max"])),
            ("τ max [MPa]", fmt(d["tau_max"])),
            ("σ_red (von Mises) [MPa]", fmt(d["mises_max"])),
        ]
        if mat is not None:
            rows += [
                (tr("— Materiál / posouzení —"), ""),
                (tr("materiál"), getattr(mat, "name", "?")),
                ("Re / Rm [MPa]", f"{fmt(getattr(mat,'Re',0))} / {fmt(getattr(mat,'Rm',0))}"),
            ]
        rows += [
            ("RF_yield", fmt(d["RF_yield"])),
            ("RF_ultimate", fmt(d["RF_ultimate"])),
            ("RF (min)", f"{fmt(d['RF'])}  ({d['critical']})"),
        ]
        self.table.setRowCount(0)
        for name, val in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(name))
            self.table.setItem(r, 1, QTableWidgetItem(val))
