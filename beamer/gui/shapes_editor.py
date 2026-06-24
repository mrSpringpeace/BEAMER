"""Editor konstrukčního tvaru: primitiva (obdélník, kruh) + booleovské operace.

Mutuje `sdef.shapes` (list dict) v place a emituje `changed`.
Tvar: {"kind":"rect"|"circle","op":"add"|"sub"|"int","x","z","w","h","angle","d"}
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QComboBox, QHeaderView, QLabel,
)

from ..i18n import tr
from .spin import NoWheelDoubleSpinBox

_OPS = [("add", "＋ sjednocení"), ("sub", "－ rozdíl"), ("int", "∩ průnik")]
_KINDS = [("rect", "Obdélník"), ("circle", "Kruh")]


def default_shape(kind="rect"):
    if kind == "circle":
        return {"kind": "circle", "op": "add", "x": 0.0, "z": 0.0, "d": 100.0}
    return {"kind": "rect", "op": "add", "x": 0.0, "z": 0.0,
            "w": 100.0, "h": 200.0, "angle": 0.0}


class ShapesEditor(QWidget):
    changed = Signal()

    def __init__(self, sdef):
        super().__init__()
        self.sdef = sdef
        if not self.sdef.shapes:
            self.sdef.shapes = [default_shape("rect")]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        info = QLabel(tr("Tvary se skládají shora dolů. První tvar přidává, "
                         "další upravují (sjednocení/rozdíl/průnik). [mm]"))
        info.setWordWrap(True)
        info.setStyleSheet("color:#888; font-size:11px;")
        lay.addWidget(info)

        btns = QHBoxLayout()
        b_rect = QPushButton(tr("＋ Obdélník"))
        b_circ = QPushButton(tr("＋ Kruh"))
        b_rect.clicked.connect(lambda: self._add("rect"))
        b_circ.clicked.connect(lambda: self._add("circle"))
        btns.addWidget(b_rect)
        btns.addWidget(b_circ)
        btns.addStretch(1)
        lay.addLayout(btns)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [tr("Tvar"), tr("Operace"), "x", "z",
             tr("š / ⌀"), tr("v"), tr("úhel°"), ""])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table)

        self._rebuild()

    # ── operace nad seznamem ──
    def _add(self, kind):
        s = default_shape(kind)
        if not self.sdef.shapes:
            s["op"] = "add"
        self.sdef.shapes.append(s)
        self._rebuild()
        self.changed.emit()

    def _del(self, idx):
        if 0 <= idx < len(self.sdef.shapes):
            self.sdef.shapes.pop(idx)
            self._rebuild()
            self.changed.emit()

    def _set(self, idx, key, val):
        self.sdef.shapes[idx][key] = val
        self.changed.emit()

    def _set_kind(self, idx, kind):
        s = self.sdef.shapes[idx]
        if s.get("kind") == kind:
            return
        op = s.get("op", "add")
        x, z = s.get("x", 0.0), s.get("z", 0.0)
        ns = default_shape(kind)
        ns.update({"op": op, "x": x, "z": z})
        self.sdef.shapes[idx] = ns
        self._rebuild()
        self.changed.emit()

    def _set_op(self, idx, op):
        self.sdef.shapes[idx]["op"] = op
        self.changed.emit()

    # ── stavba tabulky ──
    def _spin(self, val, idx, key, mn, mx, dec=2):
        sp = NoWheelDoubleSpinBox()
        sp.setRange(mn, mx)
        sp.setDecimals(dec)
        sp.setValue(float(val))
        sp.setMaximumWidth(90)
        sp.valueChanged.connect(lambda v, i=idx, k=key: self._set(i, k, v))
        return sp

    def _rebuild(self):
        self.table.setRowCount(0)
        for idx, s in enumerate(self.sdef.shapes or []):
            r = self.table.rowCount()
            self.table.insertRow(r)
            kind = s.get("kind", "rect")

            cb_kind = QComboBox()
            for k, lbl in _KINDS:
                cb_kind.addItem(tr(lbl), k)
            cb_kind.setCurrentIndex(max(0, [k for k, _ in _KINDS].index(kind)))
            cb_kind.currentIndexChanged.connect(
                lambda _, i=idx, c=cb_kind: self._set_kind(i, c.currentData()))
            self.table.setCellWidget(r, 0, cb_kind)

            cb_op = QComboBox()
            for op, lbl in _OPS:
                cb_op.addItem(tr(lbl), op)
            cur_op = s.get("op", "add")
            cb_op.setCurrentIndex(max(0, [o for o, _ in _OPS].index(cur_op)))
            cb_op.setEnabled(idx > 0)            # první tvar = vždy add
            cb_op.currentIndexChanged.connect(
                lambda _, i=idx, c=cb_op: self._set_op(i, c.currentData()))
            self.table.setCellWidget(r, 1, cb_op)

            self.table.setCellWidget(r, 2, self._spin(s.get("x", 0), idx, "x", -1e6, 1e6))
            self.table.setCellWidget(r, 3, self._spin(s.get("z", 0), idx, "z", -1e6, 1e6))

            if kind == "circle":
                self.table.setCellWidget(r, 4, self._spin(s.get("d", 100), idx, "d", 0.01, 1e6))
                self.table.setItem(r, 5, QTableWidgetItem("—"))
                self.table.setItem(r, 6, QTableWidgetItem("—"))
            else:
                self.table.setCellWidget(r, 4, self._spin(s.get("w", 100), idx, "w", 0.01, 1e6))
                self.table.setCellWidget(r, 5, self._spin(s.get("h", 200), idx, "h", 0.01, 1e6))
                self.table.setCellWidget(r, 6, self._spin(s.get("angle", 0), idx, "angle", -360, 360))

            btn = QPushButton("✕")
            btn.setMaximumWidth(28)
            btn.clicked.connect(lambda _, i=idx: self._del(i))
            self.table.setCellWidget(r, 7, btn)
        self.table.resizeColumnsToContents()
