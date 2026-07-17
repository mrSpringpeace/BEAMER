"""Správce knihovny profilů (průřezů) – samostatné okno.

Edituje PŘÍMO uživatelskou knihovnu (~/.beamer/profiles.json): nový, duplikovat,
přejmenovat, upravit geometrii (editor průřezu), smazat, přeuspořádat (pořadí
v souboru = pořadí v nabídkách). Sdílená knihovna jen pro čtení (kopie do
uživatelské, publikace s potvrzením). Vpravo živý náhled tvaru.

Úpravy knihovny se NEpropisují do projektů – projekt má vlastní kopie průřezů.
"""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QMessageBox, QMenu, QDialogButtonBox,
    QWidget, QSplitter,
)

from .. import library
from ..i18n import tr
from ..model import CrossSectionDef, new_id
from .plots import SectionCanvas


class ProfileLibraryDialog(QDialog):
    """Okno „Knihovna profilů". Po zavření volající obnoví výběry průřezů."""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        # [(name, CrossSectionDef), …] v pořadí souboru
        self.profs: list = library.load_profiles()
        self.setWindowTitle(tr("Knihovna profilů"))
        self.resize(860, 540)

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

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("název profilu"))
        self.name_edit.textChanged.connect(self._rename)
        lv.addWidget(self.name_edit)

        row1 = QHBoxLayout()
        for txt, fn, tip in (
                ("＋ " + tr("Nový"), self._new, tr("Nový profil (obdélník – pak uprav)")),
                ("✎ " + tr("Upravit…"), self._edit, tr("Otevře editor průřezu")),
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
                         "seskup si např. trubky k sobě)"))
        up.clicked.connect(lambda: self._move(-1))
        dn = QPushButton("▼ " + tr("Níž"))
        dn.clicked.connect(lambda: self._move(+1))
        row2.addWidget(up)
        row2.addWidget(dn)
        lv.addLayout(row2)

        row3 = QHBoxLayout()
        takeb = QPushButton(tr("⤓ Převzít z projektu") + " ▾")
        takeb.setToolTip(tr("Uloží průřez z otevřeného projektu do knihovny"))
        takeb.clicked.connect(self._take_from_project)
        row3.addWidget(takeb)
        pubb = QPushButton(tr("Publikovat do sdílené…"))
        pubb.setEnabled(library.shared_dir_configured())
        pubb.clicked.connect(self._publish)
        row3.addWidget(pubb)
        lv.addLayout(row3)
        split.addWidget(left)

        # ── vpravo: náhled + sdílená ──
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(6, 0, 0, 0)
        self.canvas = SectionCanvas()
        rv.addWidget(self.canvas, 1)
        hint = QLabel(tr("Změny se ukládají hned. Úprava knihovny nemění "
                         "průřezy už zkopírované do projektů."))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        rv.addWidget(hint)

        shared = library.load_profiles_grouped()
        self.shared_profs = next((p for s, p in shared if s == "shared"), [])
        if self.shared_profs:
            rv.addWidget(QLabel(tr("Sdílená knihovna (jen pro čtení)") + ":"))
            self.shared_list = QListWidget()
            self.shared_list.setMaximumHeight(120)
            for n, _sd in self.shared_profs:
                QListWidgetItem(n, self.shared_list)
            rv.addWidget(self.shared_list)
            cpb = QPushButton(tr("Zkopírovat vybraný do uživatelské"))
            cpb.clicked.connect(self._copy_shared)
            rv.addWidget(cpb)
        split.addWidget(right)
        split.setSizes([380, 460])

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.accept)
        bb.accepted.connect(self.accept)
        root.addWidget(bb)

        self._reload_list()

    # ── seznam ──
    def _reload_list(self, select: int | None = None):
        self.listw.blockSignals(True)
        self.listw.clear()
        for n, _sd in self.profs:
            QListWidgetItem(n, self.listw)
        self.listw.blockSignals(False)
        if self.profs:
            row = select if select is not None else 0
            self.listw.setCurrentRow(max(0, min(row, len(self.profs) - 1)))
            self._on_select(self.listw.currentRow())
        else:
            self._on_select(-1)

    def _on_select(self, row):
        ok = 0 <= row < len(self.profs)
        self.name_edit.blockSignals(True)
        self.name_edit.setText(self.profs[row][0] if ok else "")
        self.name_edit.setEnabled(ok)
        self.name_edit.blockSignals(False)
        self._preview()

    def _preview(self):
        r = self.listw.currentRow()
        if not (0 <= r < len(self.profs)):
            self.canvas.plot(None)
            return
        from ..section import build_section
        try:
            cs = build_section(self.profs[r][1], fem=False)
        except Exception:
            cs = None
        self.canvas.plot(cs)

    def _save(self):
        library.save_profiles(self.profs)

    # ── operace ──
    def _rename(self, s):
        r = self.listw.currentRow()
        if not (0 <= r < len(self.profs)):
            return
        self.profs[r] = (s, self.profs[r][1])
        it = self.listw.item(r)
        if it is not None:
            it.setText(s)
        self._save()

    def _new(self):
        sdef = CrossSectionDef(type="rectangle", params={"b": 100.0, "h": 200.0},
                               id=new_id("sec"))
        self.profs.append((tr("Nový profil"), sdef))
        self._save()
        self._reload_list(len(self.profs) - 1)
        self._edit()                    # rovnou otevři editor

    def _edit(self):
        r = self.listw.currentRow()
        if not (0 <= r < len(self.profs)):
            return
        from .section_dialog import SectionEditorDialog
        dlg = SectionEditorDialog.for_def(self.profs[r][1], self)
        dlg.exec()
        self._save()
        self._preview()

    def _dup(self):
        r = self.listw.currentRow()
        if not (0 <= r < len(self.profs)):
            return
        n, sd = self.profs[r]
        d = copy.deepcopy(sd)
        d.id = new_id("sec")
        self.profs.insert(r + 1, (n + tr(" (kopie)"), d))
        self._save()
        self._reload_list(r + 1)

    def _del(self):
        r = self.listw.currentRow()
        if not (0 <= r < len(self.profs)):
            return
        n = self.profs[r][0]
        if QMessageBox.question(
                self, tr("Smazat z knihovny"),
                tr("Smazat profil „%s“ z uživatelské knihovny?\nProjekty, které "
                   "ho už používají, mají vlastní kopii a nezmění se.") % n,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.profs.pop(r)
        self._save()
        self._reload_list(r)

    def _move(self, delta):
        i = self.listw.currentRow()
        j = i + delta
        if not (0 <= i < len(self.profs)) or not (0 <= j < len(self.profs)):
            return
        self.profs[i], self.profs[j] = self.profs[j], self.profs[i]
        self._save()
        self._reload_list(j)

    def _take_from_project(self):
        menu = QMenu(self)
        if not self.state.sections:
            menu.addAction(tr("(projekt nemá průřezy)")).setEnabled(False)
        for s in self.state.sections:
            act = menu.addAction(s.name or tr("Průřez"))
            act.triggered.connect(lambda _=False, ss=s: self._take_one(
                ss.name or tr("Průřez"), ss))
        menu.exec(self.cursor().pos())

    def _take_one(self, name, sdef):
        d = copy.deepcopy(sdef)
        for i, (n, _sd) in enumerate(self.profs):     # upsert dle názvu
            if n == name:
                self.profs[i] = (name, d)
                self._save()
                self._reload_list(i)
                return
        self.profs.append((name, d))
        self._save()
        self._reload_list(len(self.profs) - 1)

    def _copy_shared(self):
        r = self.shared_list.currentRow()
        if not (0 <= r < len(self.shared_profs)):
            return
        n, sd = self.shared_profs[r]
        self._take_one(n, sd)

    def _publish(self):
        r = self.listw.currentRow()
        if not (0 <= r < len(self.profs)):
            return
        n, sd = self.profs[r]
        if QMessageBox.question(
                self, tr("Publikovat do sdílené"),
                tr("Publikovat profil „%s“ do SDÍLENÉ knihovny pro všechny uživatele?") % n,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if QMessageBox.warning(
                self, tr("Potvrdit publikaci"),
                tr("Sdílená knihovna je společná pro celý tým. Opravdu zapsat?"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if library.publish_profile(n, sd):
            QMessageBox.information(self, tr("Sdílená knihovna"),
                                    tr("Profil publikován do sdílené knihovny: ") + n)
        else:
            QMessageBox.critical(self, tr("Sdílená knihovna"),
                                 tr("Publikace selhala (zkontrolujte cestu a práva)."))
