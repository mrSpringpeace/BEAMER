"""Vykreslovací plátna (matplotlib embedded v Qt)."""
from __future__ import annotations

import math
import numpy as np

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch, Circle, Annulus

from ..analysis import stress_profile, forces_from_beam
from ..i18n import tr
from ..settings import SETTINGS, fmt


class MplCanvas(FigureCanvasQTAgg):
    def __init__(self, nrows=1, ncols=1, figsize=(5, 4)):
        self.fig = Figure(figsize=figsize, layout="constrained")
        super().__init__(self.fig)


def _draw_schema(ax, state, result=None):
    """Schéma nosníku: nosník, číslované podpory, klouby, zatížení (+popisky)
    a – je-li `result` – grafické reakce."""
    L = state.length
    ax.plot([0, L], [0, 0], color="#333", lw=3, solid_capstyle="round")
    ax.set_title(tr("Schéma nosníku"), fontsize=9, loc="left")

    # dělicí čáry úseků; textové popisky jen při malém počtu úseků (jinak nečitelné)
    segs = getattr(state, "section_segments", None) or []
    show_seg_labels = len(segs) <= 8
    for j, seg in enumerate(segs):
        if j > 0:
            ax.axvline(seg.x1, color="#bbb", lw=0.8, ls=":")
        if show_seg_labels:
            mid = getattr(seg, "material_id", None)
            mat = next((m for m in state.materials if m.id == mid), None)
            mname = mat.name if mat else ""
            ax.text((seg.x1 + seg.x2) / 2, 33, f"{tr('Úsek')} {j+1}\n{mname}\n{seg.sec1.type}",
                    ha="center", va="top", fontsize=6.5, color="#777")
    C_LOAD, C_DIST, C_MOM, C_TOR = "#c62828", "#ef6c00", "#6a1b9a", "#00838f"
    C_REAC = "#0a7d4f"

    # podpory + čísla
    for i, s in enumerate(state.supports):
        if s.type == "fixed":
            ax.plot([s.x, s.x], [-8, 8], color="#444", lw=4)
            ax.plot(s.x, 0, "s", color="#444", ms=8)
        elif s.type == "pin":
            ax.plot(s.x, 0, "^", color="#1565c0", ms=12)
        else:
            ax.plot(s.x, 0, "o", color="#2e7d32", ms=10)
            ax.plot(s.x, -6, "_", color="#2e7d32", ms=14)
        ax.annotate(str(i + 1), xy=(s.x, 0), textcoords="offset points",
                    xytext=(0, -16), ha="center", va="center",
                    fontsize=8, fontweight="bold", color="#1565c0",
                    bbox=dict(boxstyle="circle,pad=0.2", fc="white", ec="#1565c0", lw=1.2))
    # klouby
    for h in state.hinges:
        ax.plot(h.x, 0, "o", mfc="white", mec="#c62828", ms=8)

    # měřítko spojitého zatížení: max |q| → pevná amplituda (společné pro všechny)
    dloads = [ld for ld in state.loads if ld.type == "distributed"]
    qmax = max((max(abs(ld.q1), abs(ld.q2)) for ld in dloads), default=0.0)
    qscale = (16.0 / qmax) if qmax > 1e-12 else 0.0
    alen = max(L * 0.04, 1e-9)   # délka vodorovné šipky momentu [mm]

    # Měřítko šipek sil a reakcí. Délka ∝ √(velikost) – odmocninové stlačení
    # rozsahu: velké reakce neutlumí malé zadané síly, pořadí zůstává.
    AMP_F, FLOOR_F = 15.0, 5.0
    fvals = [abs(ld.Fz) for ld in state.loads if ld.type == "point_force" and abs(ld.Fz) > 1e-9]
    if result is not None and getattr(result, "is_stable", False):
        fvals += [abs(rc.Rz) for rc in result.reactions if abs(rc.Rz) > 1e-6]
    Fmax = max(fvals, default=1.0) or 1.0

    def flen(val):
        return FLOOR_F + (AMP_F - FLOOR_F) * math.sqrt(min(1.0, abs(val) / Fmax))

    # počitadla popisků dle typu (F1, q1, M1, T1 …)
    cnt = {"F": 0, "q": 0, "M": 0, "T": 0}

    # zatížení – šipka KONČÍ (hrot) v působišti na nosníku; +Fz míří nahoru
    for ld in state.loads:
        if ld.type == "point_force" and (abs(ld.Fz) > 1e-9 or abs(ld.Fx) > 1e-9):
            cnt["F"] += 1; code = f"F{cnt['F']}"
        elif ld.type == "distributed":
            cnt["q"] += 1; code = f"q{cnt['q']}"
        elif ld.type == "moment":
            cnt["M"] += 1; code = f"M{cnt['M']}"
        elif ld.type == "torsion":
            cnt["T"] += 1; code = f"T{cnt['T']}"
        else:
            code = ""

        if ld.type == "point_force" and abs(ld.Fz) > 1e-9:
            up = ld.Fz > 0
            tail = -flen(ld.Fz) if up else flen(ld.Fz)   # hrot v (x,0), ocas opačně ke směru
            ax.annotate("", xy=(ld.x, 0), xytext=(ld.x, tail),
                        arrowprops=dict(arrowstyle="-|>", color=C_LOAD, lw=1.6))
            ax.text(ld.x, tail + (-2 if up else 2), f"{code}\n{ld.Fz:.0f} N",
                    ha="center", va="top" if up else "bottom", fontsize=6.5, color=C_LOAD)
        elif ld.type == "distributed":
            # lichoběžník: výška ∝ q, +q nahoru. Profil na opačné straně než síla,
            # šipky míří k nosníku. Při změně znaménka profil prochází nosníkem.
            y1 = -qscale * ld.q1
            y2 = -qscale * ld.q2
            x1, x2 = ld.x1, ld.x2
            ax.fill([x1, x2, x2, x1], [y1, y2, 0, 0], color=C_DIST, alpha=0.12)
            ax.plot([x1, x2], [y1, y2], color=C_DIST, lw=1.3)        # šikmá horní hrana
            ax.plot([x1, x1], [0, y1], color=C_DIST, lw=0.9)         # svislé strany
            ax.plot([x2, x2], [0, y2], color=C_DIST, lw=0.9)
            nn = int(min(14, max(2, abs(x2 - x1) / max(L / 24, 1e-9))))
            for k in range(nn + 1):
                t = k / nn
                xi = x1 + (x2 - x1) * t
                yi = y1 + (y2 - y1) * t
                if abs(yi) > 0.6:
                    ax.annotate("", xy=(xi, 0), xytext=(xi, yi),
                                arrowprops=dict(arrowstyle="-|>", color=C_DIST, lw=0.8))
            ax.text(x1, y1 + (2 if y1 >= 0 else -2), f"{code}: {ld.q1:.1f}", ha="center",
                    va="bottom" if y1 >= 0 else "top", fontsize=6.5, color=C_DIST)
            ax.text(x2, y2 + (2 if y2 >= 0 else -2), f"{ld.q2:.1f} N/mm", ha="center",
                    va="bottom" if y2 >= 0 else "top", fontsize=6.5, color=C_DIST)
        elif ld.type == "point_force" and abs(ld.Fx) > 1e-9:
            dx = -flen(ld.Fx) if ld.Fx > 0 else flen(ld.Fx)
            ax.annotate("", xy=(ld.x, 0), xytext=(ld.x + dx, 0),
                        arrowprops=dict(arrowstyle="-|>", color=C_LOAD, lw=1.6))
            ax.text(ld.x, 5, code, ha="center", fontsize=6.5, color=C_LOAD)
        elif ld.type == "moment":
            # svislá čára + dvě vodorovné šipky (silová dvojice) dle orientace
            H = 15.0
            sgn = 1.0 if ld.My >= 0 else -1.0   # +M = CCW: horní šipka vlevo, dolní vpravo
            ax.plot([ld.x, ld.x], [-H, H], color=C_MOM, lw=1.4)
            ax.annotate("", xy=(ld.x - sgn*alen, H), xytext=(ld.x, H),
                        arrowprops=dict(arrowstyle="-|>", color=C_MOM, lw=1.6))
            ax.annotate("", xy=(ld.x + sgn*alen, -H), xytext=(ld.x, -H),
                        arrowprops=dict(arrowstyle="-|>", color=C_MOM, lw=1.6))
            ax.text(ld.x, H + 3, f"{code}  {ld.My:.0f}", ha="center", fontsize=6.5, color=C_MOM)
        elif ld.type == "torsion":
            ax.plot(ld.x, 0, "D", color=C_TOR, ms=6)
            ax.text(ld.x, 6, f"{code}  Mk={ld.Mx:.0f}", ha="center", fontsize=6.5, color=C_TOR)

    # deformovaný tvar (po výpočtu) – w(x) škálované na čitelnou amplitudu
    if result is not None and getattr(result, "is_stable", False) and result.points:
        xw = np.array([p.x for p in result.points])
        ww = np.array([p.w for p in result.points])
        wmax = float(np.max(np.abs(ww)))
        if wmax > 1e-12:
            amp = 16.0
            ax.plot(xw, ww / wmax * amp, color="#7b1fa2", lw=1.6, ls="--",
                    label=tr("deformovaný tvar"))
            ax.legend(loc="upper right", fontsize=7, framealpha=0.85)

    # reakce (po výpočtu)
    if result is not None and getattr(result, "is_stable", False):
        for rc in result.reactions:
            if abs(rc.Rz) > 1e-6:
                up = rc.Rz > 0
                Lp = flen(rc.Rz)
                tail = -(2 + Lp) if up else (2 + Lp)   # hrot těsně pod/nad osou u podpory
                head = -2 if up else 2
                ax.annotate("", xy=(rc.x, head), xytext=(rc.x, tail),
                            arrowprops=dict(arrowstyle="-|>", color=C_REAC, lw=1.8))
                ax.text(rc.x, tail + (-2 if up else 2), f"Rz={rc.Rz:.0f} N",
                        ha="center", va="top" if up else "bottom",
                        fontsize=6.5, color=C_REAC, fontweight="bold")
            if abs(rc.Rx) > 1e-6:
                dx = 32 if rc.Rx > 0 else -32
                ax.annotate("", xy=(rc.x, 0), xytext=(rc.x + dx, 0),
                            arrowprops=dict(arrowstyle="-|>", color=C_REAC, lw=2.0))
            if abs(rc.Ry) > 1e-6:
                ax.text(rc.x, 10, f"M={rc.Ry:.0f}", ha="center", fontsize=7,
                        color=C_REAC, fontweight="bold")

    ax.set_ylim(-42, 38)
    ax.set_yticks([])
    ax.set_xlim(-0.05 * L, 1.05 * L)
    ax.grid(True, axis="x", alpha=0.3)


def _annotate_extremes(ax, x, arr, color):
    """Vyznačí maximum a minimum křivky s číselnou hodnotou."""
    if len(arr) == 0:
        return
    rng = float(np.nanmax(arr) - np.nanmin(arr))
    if rng < 1e-12 and abs(float(np.nanmax(arr))) < 1e-12:
        return
    for idx, va in ((int(np.nanargmax(arr)), "bottom"), (int(np.nanargmin(arr)), "top")):
        xv, yv = x[idx], arr[idx]
        ax.plot(xv, yv, "o", color=color, ms=4)
        ax.annotate(fmt(yv), xy=(xv, yv), textcoords="offset points",
                    xytext=(0, 6 if va == "bottom" else -6), ha="center", va=va,
                    fontsize=7, color=color,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec=color, alpha=0.85, lw=0.6))


class SchemaCanvas(MplCanvas):
    """Samostatné plátno se schématem nosníku (vstup + reakce)."""

    def __init__(self):
        super().__init__(figsize=(6, 2.4))

    def plot(self, state, result=None):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        _draw_schema(ax, state, result)
        ax.set_xlabel("x [mm]", fontsize=8)
        self.draw()


class BeamDiagramCanvas(MplCanvas):
    """VVÚ (N, V, M, Mk) + deformace (w, φ). Režim `combined` = jeden graf
    s více osami; `show_deform` přidá/skryje průhyb a pootočení (i jejich osy)."""

    def __init__(self):
        super().__init__(figsize=(6, 11))
        self.combined = SETTINGS.vvu_combined
        self.show_deform = getattr(SETTINGS, "vvu_show_deform", True)

    def plot(self, state, result):
        self.fig.clear()
        if not result or not result.is_stable or not result.points:
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, result.error_message if result else tr("Bez výsledku"),
                    ha="center", va="center", color="crimson", wrap=True)
            ax.axis("off")
            self.draw()
            return
        pts = result.points
        x = np.array([p.x for p in pts])
        d = dict(N=np.array([p.N for p in pts]), V=np.array([p.V for p in pts]),
                 M=np.array([p.M for p in pts]), Mk=np.array([p.Mk for p in pts]),
                 w=np.array([p.w for p in pts]), phi=np.array([p.phi for p in pts]))
        if self.combined:
            self._plot_combined(x, d)
        else:
            self._plot_separate(x, d)
        self.draw()

    @staticmethod
    def _nonzero(arr):
        return float(np.nanmax(np.abs(arr))) > 1e-9

    def _plot_separate(self, x, d):
        candidates = [
            (tr("N – osová síla [N]"), d["N"], "#1565c0"),
            (tr("V – posouvající síla [N]"), d["V"], "#2e7d32"),
            (tr("M – ohybový moment [N·mm]"), d["M"], "#c62828"),
            (tr("Mk – kroutící moment [N·mm]"), d["Mk"], "#6a1b9a"),
        ]
        if self.show_deform:
            candidates += [
                (tr("w – průhyb [mm]"), d["w"], "#00838f"),
                (tr("φ – pootočení [rad]"), d["phi"], "#ef6c00"),
            ]
        # nulové veličiny (např. N, Mk bez příslušného zatížení) se nezobrazují
        specs = [s for s in candidates if self._nonzero(s[1])]
        if not specs:
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, tr("Všechny veličiny jsou nulové"),
                    ha="center", va="center", color="#888")
            ax.axis("off")
            self.setMinimumHeight(150)
            return
        self.setMinimumHeight(150 * len(specs))
        axes = self.fig.subplots(len(specs), 1, sharex=True)
        if len(specs) == 1:
            axes = [axes]
        for ax, (title, arr, color) in zip(axes, specs):
            ax.axhline(0, color="#999", lw=0.8)
            ax.plot(x, arr, color=color, lw=1.4)
            ax.fill_between(x, arr, 0, color=color, alpha=0.15)
            _annotate_extremes(ax, x, arr, color)
            ax.set_title(title, fontsize=8, loc="left")
            ax.grid(True, alpha=0.3)
            ax.tick_params(labelsize=7)
        axes[-1].set_xlabel("x [mm]", fontsize=8)

    def _plot_combined(self, x, d):
        """Jeden graf VVÚ s více osami seskupenými dle jednotek;
        nulové veličiny (i jejich osy) se vynechávají."""
        self.setMinimumHeight(460)
        ax = self.fig.add_subplot(111)
        C_N, C_V = "#1565c0", "#2e7d32"
        C_M, C_Mk = "#c62828", "#6a1b9a"
        C_w, C_p = "#00838f", "#ef6c00"

        ax.axhline(0, color="#999", lw=0.8)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)
        ax.set_xlabel("x [mm]", fontsize=8)
        lines = []

        # síly na hlavní ose
        if self._nonzero(d["N"]):
            lines += ax.plot(x, d["N"], color=C_N, lw=1.4, label="N [N]")
        if self._nonzero(d["V"]):
            lines += ax.plot(x, d["V"], color=C_V, lw=1.4, label="V [N]")
        ax.set_ylabel(tr("Síly [N]"), fontsize=8, color="#333")

        off = 52
        # momenty
        if self._nonzero(d["M"]) or self._nonzero(d["Mk"]):
            ax_m = ax.twinx()
            if self._nonzero(d["M"]):
                lines += ax_m.plot(x, d["M"], color=C_M, lw=1.4, label="M [N·mm]")
            if self._nonzero(d["Mk"]):
                lines += ax_m.plot(x, d["Mk"], color=C_Mk, lw=1.4, ls="--", label="Mk [N·mm]")
            ax_m.set_ylabel(tr("Momenty [N·mm]"), fontsize=8, color=C_M)
            ax_m.tick_params(axis="y", labelsize=7, labelcolor=C_M)

        if self.show_deform:
            if self._nonzero(d["w"]):
                ax_w = ax.twinx()
                ax_w.spines["right"].set_position(("outward", off)); off += 58
                lines += ax_w.plot(x, d["w"], color=C_w, lw=1.2, ls=":", label="w [mm]")
                ax_w.set_ylabel(tr("Průhyb w [mm]"), fontsize=8, color=C_w)
                ax_w.tick_params(axis="y", labelsize=7, labelcolor=C_w)
            if self._nonzero(d["phi"]):
                ax_p = ax.twinx()
                ax_p.spines["right"].set_position(("outward", off))
                lines += ax_p.plot(x, d["phi"], color=C_p, lw=1.2, ls=":", label="φ [rad]")
                ax_p.set_ylabel(tr("Pootočení φ [rad]"), fontsize=8, color=C_p)
                ax_p.tick_params(axis="y", labelsize=7, labelcolor=C_p)

        if lines:
            ax.legend(lines, [ln.get_label() for ln in lines], fontsize=7,
                      loc="upper center", ncol=3, framealpha=0.9)
        ax.set_title(tr("Vnitřní účinky"), fontsize=9, loc="left")


class SectionCanvas(MplCanvas):
    """Náhled tvaru průřezu s těžištěm, hlavními osami a středem smyku.
    Pro kompozit zobrazuje VŠECHNA tělesa s reálně vyřezanými dírami."""

    def __init__(self):
        super().__init__(figsize=(4, 4))

    @staticmethod
    def _signed_area(poly):
        s = 0.0
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            s += x1 * y2 - x2 * y1
        return s / 2.0

    @classmethod
    def _add_body_patch(cls, ax, outer, holes,
                        facecolor="#b4cdeb", edgecolor="#30568f", lw=1.4, alpha=0.9):
        """Vykreslí jedno těleso (vnější obrys + díry) jako jeden PathPatch
        s vyřezanými dírami (non-zero winding s opačnou orientací děr)."""
        if not outer or len(outer) < 3:
            return
        verts = []
        codes = []

        def _add_poly(poly, reverse=False):
            pts = list(reversed(poly)) if reverse else list(poly)
            for i, (x, y) in enumerate(pts):
                codes.append(MplPath.MOVETO if i == 0 else MplPath.LINETO)
                verts.append((x, y))
            # CLOSEPOLY vrchol musí být znovu prvním bodem cesty
            codes.append(MplPath.CLOSEPOLY)
            verts.append(pts[0])

        # vnější obrys: vždy CCW (kladný signed area)
        outer_ccw = cls._signed_area(outer) > 0
        _add_poly(outer, reverse=not outer_ccw)
        # díry: opačná orientace než outer ⇒ CW (záporný signed area)
        for h in holes:
            if len(h) < 3:
                continue
            h_ccw = cls._signed_area(h) > 0
            _add_poly(h, reverse=h_ccw)   # CCW → reverse na CW
        path = MplPath(verts, codes)
        patch = PathPatch(path, facecolor=facecolor, edgecolor=edgecolor,
                          lw=lw, alpha=alpha)
        ax.add_patch(patch)

    def plot(self, section):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.set_aspect("equal")
        if section is None or not section.valid:
            ax.text(0.5, 0.5, tr("Neplatný průřez"), ha="center", va="center")
            ax.axis("off")
            self.draw()
            return

        all_ys = []
        all_zs = []

        if getattr(section, "bodies_c", None):
            # kompozit: vykresli každé tělo jako celek s vyřezanými dírami
            for outer, holes in section.bodies_c:
                self._add_body_patch(ax, outer, holes)
                for q in outer:
                    all_ys.append(q[0]); all_zs.append(q[1])
                for h in holes:
                    for q in h:
                        all_ys.append(q[0]); all_zs.append(q[1])
        elif section.pts:
            pc = section._pts_c
            self._add_body_patch(ax, pc, [])
            all_ys = [p[0] for p in pc]
            all_zs = [p[1] for p in pc]
        elif section._sl_circ:
            # kruh / trubka: vykresli plný kruh nebo mezikruží jako patch
            # s plochou i obrysovou čárou (střed = těžiště, tj. počátek)
            r_out = getattr(section, "_circle_r_out", None)
            r_in = getattr(section, "_circle_r_in", 0.0) or 0.0
            if r_out is None:
                # fallback: odvoď vnější poloměr z vrstev
                r_out = max(max(abs(yl), abs(yr))
                            for _, _, yl, yr in section._sl_circ) * 1e3
            if r_in > 1e-9:
                patch = Annulus((0.0, 0.0), r_out, width=r_out - r_in,
                                facecolor="#b4cdeb", edgecolor="#30568f",
                                lw=1.4, alpha=0.9)
            else:
                patch = Circle((0.0, 0.0), r_out,
                               facecolor="#b4cdeb", edgecolor="#30568f",
                               lw=1.4, alpha=0.9)
            ax.add_patch(patch)
            all_ys.extend([-r_out, r_out]); all_zs.extend([-r_out, r_out])

        # limity tak, aby celý kompozit byl vidět včetně rezervy
        if all_ys and all_zs:
            pad = 0.06 * max(max(all_ys)-min(all_ys), max(all_zs)-min(all_zs), 1.0)
            ax.set_xlim(min(all_ys)-pad, max(all_ys)+pad)
            ax.set_ylim(min(all_zs)-pad, max(all_zs)+pad)

        # těžiště
        ax.plot(0, 0, "+", color="#c62828", ms=14, mew=2)
        # osy
        ax.axhline(0, color="#3070c8", lw=0.8, alpha=0.6)
        ax.axvline(0, color="#3070c8", lw=0.8, alpha=0.6)
        # střed smyku
        if abs(section.z_SC) > 1e-6 or abs(section.y_SC) > 1e-6:
            ax.plot(section.y_SC, section.z_SC, "x", color="#2e7d32", ms=10, mew=2,
                    label=tr("střed smyku"))
        # indikátor kompozitu (kolik těles je vyhodnoceno)
        if getattr(section, "bodies_c", None) and len(section.bodies_c) > 1:
            ax.set_title(tr("Průřez (kompozit, %d těles)") % len(section.bodies_c),
                         fontsize=9)
        else:
            ax.set_title(tr("Průřez"), fontsize=9)
        ax.set_xlabel("y [mm]", fontsize=8)
        ax.set_ylabel("z [mm]", fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)
        self.draw()


class StressCanvas(MplCanvas):
    """Diagram napětí po výšce průřezu (σ, τ, von Mises)."""

    def __init__(self):
        super().__init__(figsize=(5, 4))

    def plot(self, section, N, V, M, Mk):
        self.fig.clear()
        if section is None or not section.valid:
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, tr("Bez průřezu"), ha="center", va="center")
            ax.axis("off")
            self.draw()
            return

        prof = stress_profile(section, N, V, M, Mk, n=160)
        z = np.array(prof.z)
        sigma = np.array(prof.sigma)
        tau = np.array(prof.tau)
        mises = np.array(prof.mises)

        axes = self.fig.subplots(1, 3, sharey=True)
        data = [("σ [MPa]", sigma, "#1565c0"),
                ("τ [MPa]", tau, "#2e7d32"),
                ("σ_red [MPa]", mises, "#c62828")]
        for ax, (title, arr, color) in zip(axes, data):
            ax.axvline(0, color="#999", lw=0.8)
            ax.plot(arr, z, color=color, lw=1.5)
            ax.fill_betweenx(z, arr, 0, color=color, alpha=0.15)
            ax.set_title(title, fontsize=8)
            ax.grid(True, alpha=0.3)
            ax.tick_params(labelsize=7)
        axes[0].set_ylabel(tr("z [mm od těžiště]"), fontsize=8)
        self.fig.suptitle(f"{tr('Napjatost')}  (M={M:.0f} N·mm, V={V:.0f} N)", fontsize=9)
        self.draw()


class MarginCanvas(MplCanvas):
    """Průběh RF_yield a RF_ultimate podél nosníku s popisky minim."""

    def __init__(self):
        super().__init__(figsize=(6, 3))

    def plot(self, margins):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        if not margins:
            ax.text(0.5, 0.5, tr("Bez dat"), ha="center", va="center")
            ax.axis("off")
            self.draw()
            return
        x = np.array([m.x for m in margins])

        def clean(vals):
            return np.array([v if math.isfinite(v) else np.nan for v in vals])

        ry = clean([m.RF_yield for m in margins])
        ru = clean([m.RF_ultimate for m in margins])

        ax.plot(x, ry, color="#1565c0", lw=1.6, label="RF_yield")
        ax.plot(x, ru, color="#2e7d32", lw=1.6, label="RF_ultimate")
        ax.axhline(1.0, color="#c62828", lw=1.0, ls="--", label="RF = 1")

        # červené podbarvení tam, kde řídicí (menší) RF < 1
        rf_min = np.fmin(np.nan_to_num(ry, nan=np.inf), np.nan_to_num(ru, nan=np.inf))
        ax.fill_between(x, rf_min, 1.0, where=(rf_min < 1.0), color="#c62828", alpha=0.3)

        # popisky minim obou křivek
        for arr, color, lbl in ((ry, "#1565c0", "RF_yield"), (ru, "#2e7d32", "RF_ultimate")):
            if np.all(np.isnan(arr)):
                continue
            j = int(np.nanargmin(arr))
            yv = float(arr[j])
            ax.plot(x[j], yv, "o", color=color, ms=5)
            ax.annotate(f"{lbl},min = {fmt(yv)}", xy=(x[j], yv),
                        textcoords="offset points", xytext=(0, 8), ha="center",
                        fontsize=7, color=color,
                        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=color, alpha=0.9, lw=0.6))

        # adaptivní strop osy: když RF místy vychází obrovské (σ→0 u podpor/konců),
        # oříznem pohled tak, aby byl dobře vidět nízký (řídicí) RF podél nosníku
        finite = rf_min[np.isfinite(rf_min)]
        clipped = False
        if finite.size:
            rfmin = float(np.min(finite))
            cap = max(1.5, 3.0 * rfmin)            # ~3× minimum, min. 1,5
            true_top = float(np.nanmax(np.concatenate([ry[~np.isnan(ry)] if np.any(~np.isnan(ry)) else [0],
                                                       ru[~np.isnan(ru)] if np.any(~np.isnan(ru)) else [0]])))
            if true_top > cap * 1.2:
                ax.set_ylim(0, cap)
                clipped = True
        if not clipped:
            ax.set_ylim(bottom=0)
        ax.set_xlabel("x [mm]", fontsize=8)
        ax.set_ylabel("RF", fontsize=8)
        title = tr("Rezervní faktor podél nosníku")
        if clipped:
            title += tr("  (osa oříznuta)")
        ax.set_title(title, fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)
        ax.legend(fontsize=7, ncol=3, loc="upper right")
        self.draw()
