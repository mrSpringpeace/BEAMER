"""Správce knihovny materiálů – samostatné okno.

Edituje PŘÍMO uživatelskou knihovnu (~/.beamer/materials.json): nový, duplikovat,
smazat, přeuspořádat (pořadí v souboru = pořadí v nabídkách – uživatel si může
seskupit oceli k sobě, hliníky k sobě…). Sdílená knihovna je jen pro čtení
(kopie do uživatelské, publikace se stávajícím potvrzením).

Úpravy knihovny se NEpropisují do otevřených projektů – projekt má vlastní kopie
materiálů (soběstačný soubor); knihovna ovlivní jen budoucí přiřazení.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QMessageBox, QMenu,
    QDialogButtonBox, QWidget, QSplitter,
)

from .. import library
from ..i18n import tr
from ..model import Material, new_id
from .spin import NoWheelDoubleSpinBox


def _spin(val, mn=0.0, mx=1e6, step=1.0, dec=0, suffix=""):
    sp = NoWheelDoubleSpinBox()
    sp.setRange(mn, mx)
    sp.setDecimals(dec)
    sp.setSingleStep(step)
    sp.setValue(val)
    if suffix:
        sp.setSuffix(suffix)
    sp.setMaximumWidth(150)
    return sp


class MaterialLibraryDialog(QDialog):
    """Okno „Knihovna materiálů". Po zavření volající obnoví comba (živá
    knihovna je vidět hned)."""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.mats: list[Material] = library.load_materials()
        self.setWindowTitle(tr("Knihovna materiálů"))
        self.resize(760, 520)

        root = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        root.addWidget(split, 1)

        # ── vlevo: seznam + operace ──
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel(tr("Uživatelská knihovna") + ":"))
        self.listw = QListWidget()
        self.listw.currentRowChanged.connect(self._on_select)
        lv.addWidget(self.listw, 1)

        row1 = QHBoxLayout()
        for txt, fn, tip in (
                ("＋ " + tr("Nový"), self._new, tr("Přidat nový materiál do knihovny")),
                ("⧉ " + tr("Duplikovat"), self._dup, tr("Kopie vybraného (pak uprav)")),
                ("✕ " + tr("Smazat"), self._del,
                 tr("Smaže jen z knihovny – projekty mají vlastní kopie")),
        ):
            b = QPushButton(txt)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row1.addWidget(b)
        lv.addLayout(row1)

        row2 = QHBoxLayout()
        up = QPushButton("▲ " + tr("Výš"))
        up.setToolTip(tr("Posunout v seznamu nahoru (pořadí se ukládá – "
                         "seskup si např. oceli k sobě)"))
        up.clicked.connect(lambda: self._move(-1))
        dn = QPushButton("▼ " + tr("Níž"))
        dn.clicked.connect(lambda: self._move(+1))
        row2.addWidget(up)
        row2.addWidget(dn)
        lv.addLayout(row2)

        row3 = QHBoxLayout()
        takeb = QPushButton(tr("⤓ Převzít z projektu") + " ▾")
        takeb.setToolTip(tr("Uloží materiál z otevřeného projektu do knihovny"))
        takeb.clicked.connect(self._take_from_project)
        row3.addWidget(takeb)
        pubb = QPushButton(tr("Publikovat do sdílené…"))
        pubb.setEnabled(library.shared_dir_configured())
        pubb.clicked.connect(self._publish)
        row3.addWidget(pubb)
        lv.addLayout(row3)
        split.addWidget(left)

        # ── vpravo: editační formulář ──
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(6, 0, 0, 0)
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        self.form.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(self.form_host)
        hint = QLabel(tr("Změny se ukládají hned. Úprava knihovny nemění "
                         "materiály už zkopírované do projektů."))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        rv.addWidget(hint)

        # sdílená knihovna (jen pro čtení)
        shared = library.load_materials_grouped()
        shared_mats = next((m for s, m in shared if s == "shared"), [])
        if shared_mats:
            rv.addWidget(QLabel(tr("Sdílená knihovna (jen pro čtení)") + ":"))
            self.shared_list = QListWidget()
            self.shared_list.setMaximumHeight(140)
            for m in shared_mats:
                QListWidgetItem(m.name, self.shared_list)
            rv.addWidget(self.shared_list)
            cpb = QPushButton(tr("Zkopírovat vybraný do uživatelské"))
            cpb.clicked.connect(lambda: self._copy_shared(shared_mats))
            rv.addWidget(cpb)
        rv.addStretch(1)
        split.addWidget(right)
        split.setSizes([320, 420])

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.accept)
        bb.accepted.connect(self.accept)
        root.addWidget(bb)

        self._reload_list()

    # ── seznam ──
    def _reload_list(self, select: int | None = None):
        self.listw.blockSignals(True)
        self.listw.clear()
        for m in self.mats:
            QListWidgetItem(m.name, self.listw)
        self.listw.blockSignals(False)
        if self.mats:
            row = select if select is not None else 0
            self.listw.setCurrentRow(max(0, min(row, len(self.mats) - 1)))
        else:
            self._build_form(None)

    def _current(self) -> Material | None:
        r = self.listw.currentRow()
        return self.mats[r] if 0 <= r < len(self.mats) else None

    def _on_select(self, row):
        self._build_form(self.mats[row] if 0 <= row < len(self.mats) else None)

    def _save(self):
        library.save_materials(self.mats)

    # ── operace ──
    def _new(self):
        m = Material(new_id("mat"), tr("Nový materiál"),
                     E=210000, G=81000, nu=0.3, rho=7.85, Re=235, Rm=360,
                     is_custom=True)
        self.mats.append(m)
        self._save()
        self._reload_list(len(self.mats) - 1)

    def _dup(self):
        m = self._current()
        if m is None:
            return
        import copy
        d = copy.deepcopy(m)
        d.id = new_id("mat")
        d.name = m.name + tr(" (kopie)")
        i = self.listw.currentRow() + 1
        self.mats.insert(i, d)
        self._save()
        self._reload_list(i)

    def _del(self):
        m = self._current()
        if m is None:
            return
        if QMessageBox.question(
                self, tr("Smazat z knihovny"),
                tr("Smazat materiál „%s“ z uživatelské knihovny?\n"
                   "Projekty, které ho už používají, mají vlastní kopii "
                   "a nezmění se.") % m.name,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        i = self.listw.currentRow()
        self.mats.pop(i)
        self._save()
        self._reload_list(i)

    def _move(self, delta):
        i = self.listw.currentRow()
        j = i + delta
        if not (0 <= i < len(self.mats)) or not (0 <= j < len(self.mats)):
            return
        self.mats[i], self.mats[j] = self.mats[j], self.mats[i]
        self._save()
        self._reload_list(j)

    def _take_from_project(self):
        menu = QMenu(self)
        if not self.state.materials:
            menu.addAction(tr("(projekt nemá materiály)")).setEnabled(False)
        for m in self.state.materials:
            act = menu.addAction(m.name)
            act.triggered.connect(lambda _=False, mm=m: self._take_one(mm))
        menu.exec(self.cursor().pos())

    def _take_one(self, m):
        import copy
        d = copy.deepcopy(m)
        # upsert dle názvu (stejné chování jako dnešní „Do knihovny")
        for i, ex in enumerate(self.mats):
            if ex.name == d.name:
                d.id = ex.id
                self.mats[i] = d
                self._save()
                self._reload_list(i)
                return
        self.mats.append(d)
        self._save()
        self._reload_list(len(self.mats) - 1)

    def _copy_shared(self, shared_mats):
        r = getattr(self, "shared_list", None) and self.shared_list.currentRow()
        if r is None or not (0 <= r < len(shared_mats)):
            return
        self._take_one(shared_mats[r])

    def _publish(self):
        m = self._current()
        if m is None:
            return
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

    # ── formulář ──
    def _build_form(self, m: Material | None):
        while self.form.rowCount():
            self.form.removeRow(0)
        if m is None:
            self.form.addRow(QLabel(tr("(knihovna je prázdná – přidej „Nový“)")))
            return

        name = QLineEdit(m.name)
        name.textChanged.connect(lambda s, mm=m: self._rename(mm, s))
        self.form.addRow(tr("Název:"), name)

        for attr, label, suf, dec, step in [
            ("E", "E", " MPa", 0, 1000), ("G", "G", " MPa", 0, 1000),
            ("nu", "ν", "", 3, 0.01), ("Re", "Re (mez kluzu)", " MPa", 0, 5),
            ("Rm", "Rm (pevnost)", " MPa", 0, 5), ("rho", "ρ", " g/cm³", 3, 0.05),
        ]:
            sp = _spin(getattr(m, attr), 0, 1e6, step, dec, suf)
            sp.valueChanged.connect(
                lambda val, a=attr, mm=m: (setattr(mm, a, val), self._save()))
            self.form.addRow(tr(label) + ":", sp)

        asp = _spin((getattr(m, "alpha", 12e-6) or 0.0) * 1e6, 0, 1e3, 0.5, 2,
                    " ×10⁻⁶/°C")
        asp.valueChanged.connect(
            lambda val, mm=m: (setattr(mm, "alpha", val * 1e-6), self._save()))
        self.form.addRow(tr("α (roztažnost):"), asp)

        # volitelné pevnosti: 0 = nezadáno (None → výpočet použije náhradu)
        for attr, label, tip in [
            ("Fcy", tr("Fcy (tlaková mez kluzu):"),
             tr("0 = nezadáno → použije se Re")),
            ("Fsu", tr("Fsu (mez ve smyku):"),
             tr("0 = nezadáno → von Mises z Rm")),
        ]:
            sp = _spin(getattr(m, attr, None) or 0.0, 0, 1e6, 5, 0, " MPa")
            sp.setToolTip(tip)
            sp.valueChanged.connect(
                lambda val, a=attr, mm=m: (setattr(mm, a, val if val > 0 else None),
                                           self._save()))
            self.form.addRow(label, sp)

        src = QLineEdit(getattr(m, "source", "") or "")
        src.setPlaceholderText(tr("původ dat / specifikace"))
        src.textChanged.connect(
            lambda s, mm=m: (setattr(mm, "source", s), self._save()))
        self.form.addRow(tr("Zdroj:"), src)
        bas = QLineEdit(getattr(m, "allowables_basis", "") or "")
        bas.setPlaceholderText("nominal / A-basis / B-basis")
        bas.textChanged.connect(
            lambda s, mm=m: (setattr(mm, "allowables_basis", s), self._save()))
        self.form.addRow(tr("Báze hodnot:"), bas)

    def _rename(self, m, s):
        m.name = s
        it = self.listw.currentItem()
        if it is not None:
            it.setText(s)
        self._save()
