"""Generátor spojitého zatížení ze síly – samostatné nemodální okno.

Z příčné síly Fz na pozici x_F vygeneruje staticky ekvivalentní lineární
spojité zatížení na úseku [a,b]. Typy: lichoběžník (zachová R i moment, umí
i záporný konec u síly při kraji), konstantní (jen R), trojúhelník (vrchol
u síly). Osová síla a krut z excentricity se ponechají jako bodové zatížení.
"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QComboBox,
    QPushButton, QLabel, QCheckBox, QMessageBox,
)

from ..i18n import tr
from ..settings import fmt
from ..model import Load
from ..loadgen import generate_q, make_loads
from .spin import NoWheelDoubleSpinBox
from .plots import MplCanvas

_KINDS = [
    ("trapezoid", "Lichoběžník (zachovat moment)"),
    ("uniform", "Konstantní (jen výslednice)"),
    ("triangle", "Trojúhelník (vrchol u síly)"),
]


def _spin(val, mn=-1e12, mx=1e12, dec=2, step=1.0, suffix=""):
    sp = NoWheelDoubleSpinBox()
    sp.setRange(mn, mx)
    sp.setDecimals(dec)
    sp.setSingleStep(step)
    sp.setValue(val)
    if suffix:
        sp.setSuffix(suffix)
    return sp


class LoadGenDialog(QDialog):
    generated = Signal()      # do hlavního okna: zatížení se změnila

    def __init__(self, state, parent=None, preset: Load | None = None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle(tr("Generátor spojitého zatížení ze síly"))
        self.setModal(False)
        self.resize(720, 560)

        root = QHBoxLayout(self)

        # ── levý sloupec: vstupy ──
        left = QVBoxLayout()
        g = QGroupBox(tr("Zadání"))
        f = QFormLayout(g)

        self.src_cb = QComboBox()
        self.src_cb.addItem(tr("(ruční zadání)"), None)
        for ld in self.state.loads:
            if ld.type == "point_force":
                self.src_cb.addItem(f"{ld.name or tr('Síla')}  Fz={ld.Fz:.0f} @ {ld.x:.0f}", ld.id)
        self.src_cb.currentIndexChanged.connect(self._on_src)
        f.addRow(tr("Zdroj síly:"), self.src_cb)

        self.fz = _spin(-1000.0, suffix=" N")
        self.a = _spin(0.0, 0.0, 1e9, 1, 50, " mm")
        self.b = _spin(float(state.length), 0.0, 1e9, 1, 50, " mm")
        self.xf = _spin(float(state.length) / 2, 0.0, 1e9, 1, 50, " mm")
        for w in (self.fz, self.a, self.b, self.xf):
            w.valueChanged.connect(self._update)
        f.addRow(tr("Síla Fz (+nahoru):"), self.fz)
        f.addRow(tr("Začátek úseku a:"), self.a)
        f.addRow(tr("Konec úseku b:"), self.b)
        f.addRow(tr("Poloha síly x_F:"), self.xf)

        self.kind = QComboBox()
        for k, lbl in _KINDS:
            self.kind.addItem(tr(lbl), k)
        self.kind.currentIndexChanged.connect(self._update)
        f.addRow(tr("Typ rozložení:"), self.kind)

        self.lc = QComboBox()
        for c in self.state.load_cases:
            self.lc.addItem(c.name, c.id)
        f.addRow(tr("Cílový stav (LC):"), self.lc)

        self.remove_src = QCheckBox(tr("Odstranit původní sílu"))
        self.remove_src.setChecked(True)
        f.addRow("", self.remove_src)

        left.addWidget(g)
        self.info = QLabel()
        self.info.setStyleSheet("font-family:monospace; font-size:11px;")
        self.info.setAlignment(Qt.AlignTop)
        self.info.setWordWrap(True)
        left.addWidget(self.info)
        left.addStretch(1)

        btns = QHBoxLayout()
        b_gen = QPushButton(tr("Generovat"))
        b_gen.clicked.connect(self._generate)
        b_close = QPushButton(tr("Zavřít"))
        b_close.clicked.connect(self.close)
        btns.addStretch(1)
        btns.addWidget(b_gen)
        btns.addWidget(b_close)
        left.addLayout(btns)
        root.addLayout(left, 0)

        # ── pravý sloupec: náhled ──
        self.canvas = MplCanvas(figsize=(4, 3))
        root.addWidget(self.canvas, 1)

        if preset is not None:
            i = self.src_cb.findData(preset.id)
            if i >= 0:
                self.src_cb.setCurrentIndex(i)
        self._on_src()

    # ── zdroj síly ──
    def _current_src(self) -> Load | None:
        sid = self.src_cb.currentData()
        if not sid:
            return None
        return next((l for l in self.state.loads if l.id == sid), None)

    def _on_src(self, *_):
        src = self._current_src()
        manual = src is None
        self.fz.setEnabled(manual)
        self.xf.setEnabled(True)
        self.remove_src.setEnabled(not manual)
        if src is not None:
            self.fz.blockSignals(True)
            self.fz.setValue(src.Fz)
            self.fz.blockSignals(False)
            self.xf.blockSignals(True)
            self.xf.setValue(src.x)
            self.xf.blockSignals(False)
            i = self.lc.findData(src.load_case_id)
            if i >= 0:
                self.lc.setCurrentIndex(i)
        self._update()

    # ── výpočet + náhled ──
    def _compute(self):
        a, b = self.a.value(), self.b.value()
        if b <= a:
            return None
        return generate_q(a, b, self.fz.value(), self.xf.value(), self.kind.currentData())

    def _update(self, *_):
        a, b, Fz, xF = self.a.value(), self.b.value(), self.fz.value(), self.xf.value()
        res = self._compute()
        if res is None:
            self.info.setText(tr("Neplatný úsek: musí být b > a."))
            self.canvas.fig.clear()
            self.canvas.draw()
            return
        warn = ""
        if not res.moment_ok:
            warn = ("\n" + tr("⚠ Moment se nezachová: těžiště zatížení x̄=%s ≠ x_F=%s.")
                    % (f"{res.x_centroid:.1f}", f"{xF:.1f}"))
        if (res.q1 < 0) != (res.q2 < 0) and res.q1 != 0 and res.q2 != 0:
            warn += "\n" + tr("ⓘ Konce mají opačné znaménko (vyvážení momentu).")
        self.info.setText(
            f"q1 = {fmt(res.q1)} N/mm   q2 = {fmt(res.q2)} N/mm\n"
            f"{tr('výslednice')} R = {fmt(res.R)} N   "
            f"({tr('cíl')} Fz = {fmt(Fz)} N)\n"
            f"{tr('těžiště')} x̄ = {fmt(res.x_centroid)} mm   "
            f"({tr('cíl')} x_F = {fmt(xF)} mm)" + warn)
        self._draw(a, b, Fz, xF, res)

    def _draw(self, a, b, Fz, xF, res):
        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)
        L = float(self.state.length) or b
        ax.plot([0, L], [0, 0], color="#333", lw=2, zorder=3)
        # trapezoid q (nahoru = +)
        xs = [a, a, b, b]
        ys = [0, res.q1, res.q2, 0]
        ax.fill(xs, ys, color="#2a7", alpha=0.35, zorder=1)
        ax.plot([a, b], [res.q1, res.q2], color="#185", lw=1.5, zorder=2)
        ax.axhline(0, color="#999", lw=0.6)
        # původní síla (šipka)
        amp = max(abs(res.q1), abs(res.q2), abs(Fz) / max(b - a, 1), 1e-9)
        ax.annotate("", xy=(xF, 0), xytext=(xF, amp * (1 if Fz >= 0 else -1) * 1.3),
                    arrowprops=dict(arrowstyle="->", color="#c33", lw=2), zorder=4)
        ax.text(xF, amp * (1 if Fz >= 0 else -1) * 1.4, f"Fz={Fz:.0f}",
                color="#c33", ha="center", fontsize=8)
        ax.set_title(tr("Náhled q(x)"), fontsize=9)
        ax.set_xlabel("x [mm]")
        ax.set_ylabel("q [N/mm]")
        ax.margins(y=0.3)
        self.canvas.draw()

    # ── generování ──
    def _generate(self):
        a, b = self.a.value(), self.b.value()
        if b <= a:
            QMessageBox.warning(self, tr("Chyba"), tr("Úsek musí mít b > a."))
            return
        lc_id = self.lc.currentData() or (
            self.state.load_cases[0].id if self.state.load_cases else "")
        src = self._current_src()
        if src is None:
            src = Load("tmp", "point_force", "", lc_id)
            src.Fz = self.fz.value()
            src.x = self.xf.value()
        dist, extras = make_loads(self.state, a, b, src, self.xf.value(),
                                  self.kind.currentData(), lc_id)
        self.state.loads.append(dist)
        self.state.loads.extend(extras)
        removed = False
        if self.remove_src.isChecked() and self._current_src() is not None:
            try:
                self.state.loads.remove(self._current_src())
                removed = True
            except ValueError:
                pass
        # obnov nabídku zdrojů
        self.generated.emit()
        self._refresh_src_combo()
        msg = tr("Vytvořeno spojité zatížení.")
        if extras:
            msg += " " + tr("Ponecháno bodové: ") + ", ".join(
                e.type for e in extras) + "."
        if removed:
            msg += " " + tr("Původní síla odstraněna.")
        QMessageBox.information(self, tr("Hotovo"), msg)

    def _refresh_src_combo(self):
        self.src_cb.blockSignals(True)
        self.src_cb.clear()
        self.src_cb.addItem(tr("(ruční zadání)"), None)
        for ld in self.state.loads:
            if ld.type == "point_force":
                self.src_cb.addItem(
                    f"{ld.name or tr('Síla')}  Fz={ld.Fz:.0f} @ {ld.x:.0f}", ld.id)
        self.src_cb.blockSignals(False)
        self._update()

    def set_state(self, state):
        self.state = state
        self._refresh_src_combo()
