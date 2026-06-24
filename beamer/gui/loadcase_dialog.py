"""Load Case Builder – nemodální okno pro správu zatěžovacích stavů (LC),
kombinací a souhrnné tabulky výsledků (extrémy VVÚ, reakce, RF, kontrolní body).

Sjednocený model A+B:
  • zatížení patří do stavu (LC) – přiřazení v hlavním panelu,
  • kombinace = Σ faktor·LC (A-tábor) nebo „stav ×1" (B-tábor, tlačítko auto),
  • tabulka: 1 řádek = 1 kombinace; CSV / schránka (TSV pro Excel) / zobrazení
    vybrané kombinace v hlavním okně.
"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QLabel, QLineEdit, QInputDialog, QFileDialog,
    QMessageBox, QApplication, QAbstractItemView,
)

from ..i18n import tr
from ..settings import fmt
from ..model import LoadCase, LoadCombination, new_id
from .spin import NoWheelDoubleSpinBox


class LoadCaseBuilderDialog(QDialog):
    show_combination = Signal(str)     # id kombinace k zobrazení v hlavním okně
    changed = Signal()                 # model se změnil (kvůli _modified / uložení)

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle(tr("Load Case Builder"))
        self.resize(1000, 640)
        self.setModal(False)
        root = QVBoxLayout(self)

        toprow = QHBoxLayout()
        toprow.addWidget(self._build_cases_box(), 1)
        toprow.addWidget(self._build_combos_box(), 2)
        root.addLayout(toprow)

        # ── souhrnná tabulka ──
        tbar = QHBoxLayout()
        b_calc = QPushButton(tr("↻ Přepočítat tabulku")); b_calc.clicked.connect(self._rebuild_table)
        b_csv = QPushButton(tr("⤒ Export CSV…")); b_csv.clicked.connect(self._export_csv)
        b_clip = QPushButton(tr("⧉ Kopírovat (Excel)")); b_clip.clicked.connect(self._copy_clipboard)
        b_show = QPushButton(tr("Zobrazit vybranou v hlavním okně")); b_show.clicked.connect(self._show_selected)
        tbar.addWidget(b_calc); tbar.addWidget(b_csv); tbar.addWidget(b_clip)
        tbar.addStretch(1); tbar.addWidget(b_show)
        root.addLayout(tbar)

        self.table = QTableWidget(0, 0)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        root.addWidget(self.table, 1)

        self._reload_all()

    # ── set_state (po načtení projektu) ──
    def set_state(self, state):
        self.state = state
        self._reload_all()

    def _reload_all(self):
        self._refresh_cases()
        self._refresh_combos()
        self._rebuild_table()

    # ════════════════════════════════════════════════════════════
    #  ZATĚŽOVACÍ STAVY (LC)
    # ════════════════════════════════════════════════════════════
    def _build_cases_box(self):
        g = QGroupBox(tr("Zatěžovací stavy"))
        v = QVBoxLayout(g)
        self.cases_tbl = QTableWidget(0, 2)
        self.cases_tbl.setHorizontalHeaderLabels([tr("Název stavu"), ""])
        self.cases_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.cases_tbl.verticalHeader().setVisible(False)
        v.addWidget(self.cases_tbl)
        b = QPushButton(tr("+ Přidat stav")); b.clicked.connect(self._add_case)
        v.addWidget(b)
        return g

    def _refresh_cases(self):
        self.cases_tbl.setRowCount(0)
        for lc in self.state.load_cases:
            r = self.cases_tbl.rowCount(); self.cases_tbl.insertRow(r)
            nm = QLineEdit(lc.name)
            nm.textChanged.connect(lambda s, c=lc: (setattr(c, "name", s), self._on_cases_renamed()))
            self.cases_tbl.setCellWidget(r, 0, nm)
            db = QPushButton("✕"); db.setMaximumWidth(30)
            db.clicked.connect(lambda _, c=lc: self._del_case(c))
            self.cases_tbl.setCellWidget(r, 1, db)

    def _on_cases_renamed(self):
        self._refresh_combos()      # hlavičky faktorů nesou názvy stavů
        self.changed.emit()

    def _add_case(self):
        self.state.load_cases.append(LoadCase(new_id("lc"), tr("Stav") + f" {len(self.state.load_cases)+1}", False))
        self._refresh_cases(); self._refresh_combos(); self.changed.emit()

    def _del_case(self, lc):
        if len(self.state.load_cases) <= 1:
            QMessageBox.information(self, tr("Zatěžovací stavy"),
                                   tr("Musí zůstat aspoň jeden stav."))
            return
        self.state.load_cases.remove(lc)
        # zatížení z mazaného stavu přesuň do prvního
        first = self.state.load_cases[0].id
        for ld in self.state.loads:
            if ld.load_case_id == lc.id:
                ld.load_case_id = first
        for comb in self.state.load_combinations:
            comb.factors.pop(lc.id, None)
        self._refresh_cases(); self._refresh_combos(); self.changed.emit()

    # ════════════════════════════════════════════════════════════
    #  KOMBINACE
    # ════════════════════════════════════════════════════════════
    def _build_combos_box(self):
        g = QGroupBox(tr("Kombinace (Σ faktor × stav)"))
        v = QVBoxLayout(g)
        self.combos_tbl = QTableWidget(0, 0)
        self.combos_tbl.verticalHeader().setVisible(False)
        v.addWidget(self.combos_tbl)
        row = QHBoxLayout()
        b1 = QPushButton(tr("+ Kombinace")); b1.clicked.connect(self._add_combo)
        b2 = QPushButton(tr("+ Stavy ×1 (auto)")); b2.clicked.connect(self._add_self_combos)
        row.addWidget(b1); row.addWidget(b2)
        v.addLayout(row)
        return g

    def _refresh_combos(self):
        cases = self.state.load_cases
        headers = [tr("Název kombinace")] + [c.name for c in cases] + [""]
        self.combos_tbl.clear()
        self.combos_tbl.setColumnCount(len(headers))
        self.combos_tbl.setHorizontalHeaderLabels(headers)
        self.combos_tbl.setRowCount(0)
        self.combos_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for comb in self.state.load_combinations:
            r = self.combos_tbl.rowCount(); self.combos_tbl.insertRow(r)
            nm = QLineEdit(comb.name)
            nm.textChanged.connect(lambda s, cb=comb: (setattr(cb, "name", s), self.changed.emit()))
            self.combos_tbl.setCellWidget(r, 0, nm)
            for j, lc in enumerate(cases):
                sp = NoWheelDoubleSpinBox(); sp.setRange(-100, 100); sp.setDecimals(2); sp.setSingleStep(0.05)
                sp.setValue(float(comb.factors.get(lc.id, 0.0)))
                sp.valueChanged.connect(lambda val, cb=comb, lid=lc.id: cb.factors.__setitem__(lid, val) or self.changed.emit())
                self.combos_tbl.setCellWidget(r, 1 + j, sp)
            db = QPushButton("✕"); db.setMaximumWidth(30)
            db.clicked.connect(lambda _, cb=comb: self._del_combo(cb))
            self.combos_tbl.setCellWidget(r, len(cases) + 1, db)

    def _add_combo(self):
        n = len(self.state.load_combinations) + 1
        self.state.load_combinations.append(
            LoadCombination(new_id("comb"), tr("Kombinace") + f" {n}", {}))
        self._refresh_combos(); self.changed.emit()

    def _add_self_combos(self):
        """Pro každý stav bez vlastní ×1 kombinace vytvoří „stav ×1"."""
        existing = set()
        for comb in self.state.load_combinations:
            nz = {k: v for k, v in comb.factors.items() if abs(v) > 1e-9}
            if len(nz) == 1 and abs(list(nz.values())[0] - 1.0) < 1e-9:
                existing.add(list(nz.keys())[0])
        for lc in self.state.load_cases:
            if lc.id not in existing:
                self.state.load_combinations.append(
                    LoadCombination(new_id("comb"), lc.name + " ×1", {lc.id: 1.0}))
        self._refresh_combos(); self._rebuild_table(); self.changed.emit()

    def _del_combo(self, comb):
        self.state.load_combinations.remove(comb)
        self._refresh_combos(); self.changed.emit()

    # ════════════════════════════════════════════════════════════
    #  SOUHRNNÁ TABULKA
    # ════════════════════════════════════════════════════════════
    def _compute_rows(self):
        from ..analysis import load_case_summary
        rows = []
        col_order = []
        for comb in self.state.load_combinations:
            cols, _ = load_case_summary(self.state, comb.factors, comb.name)
            d = {}
            for name, val in cols:
                d[name] = val
                if name not in col_order:
                    col_order.append(name)
            d["_combo_id"] = comb.id
            rows.append(d)
        return col_order, rows

    def _rebuild_table(self):
        col_order, rows = self._compute_rows()
        self._rows = rows
        self.table.clear()
        self.table.setColumnCount(len(col_order))
        self.table.setHorizontalHeaderLabels(col_order)
        self.table.setRowCount(len(rows))
        for i, d in enumerate(rows):
            for j, col in enumerate(col_order):
                v = d.get(col, "")
                txt = v if isinstance(v, str) else fmt(v)
                self.table.setItem(i, j, QTableWidgetItem(txt))
        self.table.resizeColumnsToContents()
        self._col_order = col_order

    def _table_as_tsv(self):
        lines = ["\t".join(self._col_order)]
        for d in self._rows:
            cells = []
            for col in self._col_order:
                v = d.get(col, "")
                cells.append(v if isinstance(v, str) else fmt(v))
            lines.append("\t".join(cells))
        return "\n".join(lines)

    def _copy_clipboard(self):
        if not getattr(self, "_rows", None):
            return
        QApplication.clipboard().setText(self._table_as_tsv())
        QMessageBox.information(self, tr("Kopírovat (Excel)"),
                               tr("Tabulka zkopírována do schránky (vložte do Excelu)."))

    def _export_csv(self):
        if not getattr(self, "_rows", None):
            return
        from ..settings import SETTINGS
        import os
        start = os.path.join(SETTINGS.last_dir or "", "load_cases.csv") if SETTINGS.last_dir else "load_cases.csv"
        path, _ = QFileDialog.getSaveFileName(self, tr("Export CSV…"), start, "CSV (*.csv)")
        if not path:
            return
        import csv
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=",")
                w.writerow(self._col_order)
                for d in self._rows:
                    w.writerow([(d.get(c, "") if isinstance(d.get(c, ""), str) else fmt(d.get(c, "")))
                                for c in self._col_order])
            try:
                SETTINGS.last_dir = os.path.dirname(path); SETTINGS.save()
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, tr("Chyba"), tr("Nelze exportovat: ") + str(e))

    def _show_selected(self):
        r = self.table.currentRow()
        if r < 0 or not getattr(self, "_rows", None) or r >= len(self._rows):
            QMessageBox.information(self, tr("Load Case Builder"),
                                   tr("Vyberte řádek (kombinaci) v tabulce."))
            return
        self.show_combination.emit(self._rows[r]["_combo_id"])
