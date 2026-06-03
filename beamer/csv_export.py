"""Export výsledných křivek (VVÚ + deformace) a reakcí do CSV.

Inženýrský formát: oddělovač sloupců ',' a desetinná tečka '.'
(NE česká Excel lokalizace ';' + ','). Jeden soubor obsahuje:
  • hlavičku s metadaty (řádky začínající '#'),
  • tabulku reakcí,
  • tabulku průběhových křivek.

Rozlišení křivek je volitelné: n_points=None → plné rozlišení solveru
(všechny body), jinak se rovnoměrně převzorkuje na n_points lineární
interpolací.
"""
from __future__ import annotations

import csv
import datetime

import numpy as np

# (hlavička sloupce, atribut BeamPoint)
CURVE_COLUMNS = [
    ("x_mm", "x"),
    ("N_N", "N"),
    ("V_N", "V"),
    ("M_Nmm", "M"),
    ("Mk_Nmm", "Mk"),
    ("w_mm", "w"),
    ("phi_rad", "phi"),
    ("theta_rad", "theta"),
]


def _fmt(v) -> str:
    """Číslo v inženýrském zápisu s desetinnou tečkou (max 6 platných cifer)."""
    try:
        return f"{float(v):.6g}"
    except (TypeError, ValueError):
        return str(v)


def export_curves_csv(state, result, path, n_points=None) -> int:
    """Zapíše reakce + průběhové křivky do CSV. Vrací počet exportovaných
    bodů křivek."""
    if result is None or not getattr(result, "is_stable", False) or not result.points:
        raise ValueError("Žádné stabilní výsledky k exportu.")

    pts = result.points
    xs = [p.x for p in pts]

    # ── sestav řádky křivek (případně převzorkuj) ──
    if n_points and int(n_points) < len(pts):
        xq = np.linspace(xs[0], xs[-1], int(n_points))
        series = {attr: np.interp(xq, xs, [getattr(p, attr) for p in pts])
                  for _, attr in CURVE_COLUMNS}
        rows = [[series[attr][i] for _, attr in CURVE_COLUMNS]
                for i in range(len(xq))]
    else:
        rows = [[getattr(p, attr) for _, attr in CURVE_COLUMNS] for p in pts]

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=",")
        # metadata
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        w.writerow([f"# BEAMER curve export {now}"])
        w.writerow([f"# Beam length L [mm] = {_fmt(state.length)}"])
        w.writerow([f"# Theory = {state.theory}"])
        w.writerow([f"# Additional factor = {_fmt(getattr(state, 'additional_factor', 1.0))}"])
        w.writerow([f"# Points = {len(rows)}"])
        w.writerow([])
        # reakce
        w.writerow(["# Reactions"])
        w.writerow(["x_mm", "support_type", "Rx_N", "Rz_N", "My_Nmm", "Mk_Nmm"])
        for rc in result.reactions:
            w.writerow([_fmt(rc.x), rc.support_type, _fmt(rc.Rx), _fmt(rc.Rz),
                        _fmt(rc.Ry), _fmt(rc.Rx_torsion)])
        w.writerow([])
        # křivky
        w.writerow(["# Internal force and deformation curves"])
        w.writerow([h for h, _ in CURVE_COLUMNS])
        for row in rows:
            w.writerow([_fmt(v) for v in row])

    return len(rows)
