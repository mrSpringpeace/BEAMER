"""Import nosníku z programu Ministatik (*.nos).

Formát (textový, kódování cp1250, CRLF):
  řádek 0: hlavička (text)
  řádek 1: typ nosníku  (1 = kloub+rolny, 2 = vetknutí+rolny,
                         3 = vetknutí na obou koncích, mezi rolny)
  řádek 2: celková délka L (= X konce posledního úseku)
  bloky (počet na samostatném řádku + tolik řádků dat):
    ÚSEKY      [Jx_poč, Jx_konc, E, X_konec]   (X_konec = kumulativní konec)
    PODPORY    [průhyb, poloha]
    SÍLY       [velikost, poloha]
    MOMENTY    [velikost, poloha]
    SPOJITÁ    [Q_poč, X_poč, Q_konc, X_konec]

Mapování do BEAMER: úseky → proměnný průřez (přímé Iy, tapered) s per-úsekovým E;
podpory dle typu (pin/roller/fixed). Zatížení se importují s velikostmi z .nos.
"""
from __future__ import annotations

from .model import (
    ProjectState, Support, Load, LoadCase, LoadCombination,
    CrossSectionDef, SectionSegment, new_id,
)
from .defaults import MATERIAL_LIBRARY


def _floats(line):
    out = []
    for tok in line.replace(",", ".").split():
        try:
            out.append(float(tok))
        except ValueError:
            pass
    return out


def parse_nos(path: str) -> dict:
    """Načte .nos a vrátí slovník s rozparsovanými daty."""
    with open(path, "r", encoding="cp1250", errors="replace") as f:
        raw = [ln.rstrip("\r\n") for ln in f]
    lines = [ln for ln in raw if ln.strip() != ""]
    if len(lines) < 4:
        raise ValueError("Soubor .nos je příliš krátký nebo poškozený.")

    # lines[0] = hlavička
    beam_type = int(float(lines[1].split()[0]))
    L_total = _floats(lines[2])[0]

    i = 3

    def read_block():
        nonlocal i
        n = int(float(lines[i].split()[0]))
        i += 1
        rows = []
        for _ in range(n):
            rows.append(_floats(lines[i]))
            i += 1
        return rows

    segments = read_block()    # [Jx1, Jx2, E, X_end]
    supports = read_block()    # [deflection, position]
    forces = read_block()      # [magnitude, position]
    moments = read_block()     # [magnitude, position]
    distributed = read_block()  # [Q1, X1, Q2, X2]

    return {
        "type": beam_type, "L": L_total, "segments": segments,
        "supports": supports, "forces": forces, "moments": moments,
        "distributed": distributed,
    }


def nos_to_state(data: dict) -> ProjectState:
    """Sestaví ProjectState z rozparsovaného .nos."""
    beam_type = data["type"]
    L = data["L"]

    # ── úseky → proměnný průřez (přímé Iy, tapered) + per-úsekové E ──
    segs = []
    x_prev = 0.0
    for row in data["segments"]:
        Jx1, Jx2, E, x_end = row[0], row[1], row[2], row[3]
        sec1 = CrossSectionDef(type="direct", params={"Iy": Jx1})
        sec2 = (None if abs(Jx2 - Jx1) < 1e-9
                else CrossSectionDef(type="direct", params={"Iy": Jx2}))
        segs.append(SectionSegment(x1=x_prev, x2=x_end, sec1=sec1, sec2=sec2, E=E))
        x_prev = x_end
    if not L:
        L = x_prev

    # ── podpory dle typu ──
    sup_positions = [row[1] for row in data["supports"]]
    supports = []
    n = len(sup_positions)
    for idx, pos in enumerate(sup_positions):
        if beam_type == 1:
            stype = "pin" if idx == 0 else "roller"
        elif beam_type == 2:
            stype = "fixed" if idx == 0 else "roller"
        else:  # typ 3: první a poslední vetknuté, mezi rolny
            stype = "fixed" if (idx == 0 or idx == n - 1) else "roller"
        supports.append(Support(new_id("sup"), float(pos), stype, 0.0))

    LC = "lc_1"
    COMB = "comb_1"
    loads = []
    for mag, pos in ((r[0], r[1]) for r in data["forces"]):
        ld = Load(new_id("load"), "point_force", "Síla", LC)
        ld.x = float(pos)
        ld.Fz = float(mag)
        loads.append(ld)
    for mag, pos in ((r[0], r[1]) for r in data["moments"]):
        ld = Load(new_id("load"), "moment", "Moment", LC)
        ld.x = float(pos)
        ld.My = float(mag)
        loads.append(ld)
    for q1, x1, q2, x2 in ((r[0], r[1], r[2], r[3]) for r in data["distributed"]):
        ld = Load(new_id("load"), "distributed", "Spojité", LC)
        ld.x1 = float(x1)
        ld.x2 = float(x2)
        ld.q1 = float(q1)
        ld.q2 = float(q2)
        loads.append(ld)

    # globální materiál (E z 1. úseku jako fallback; per-úsek E nese segment)
    E0 = data["segments"][0][2] if data["segments"] else 72000.0
    materials = [type(MATERIAL_LIBRARY[0])(**vars(m)) for m in MATERIAL_LIBRARY]
    mat = materials[0]
    mat.E = E0

    st = ProjectState(
        length=float(L),
        supports=supports,
        hinges=[],
        load_cases=[LoadCase(LC, "Ministatik", False)],
        load_combinations=[LoadCombination(COMB, "Kombi 1", {LC: 1.0})],
        loads=loads,
        materials=materials,
        selected_material_id=mat.id,
        cross_section=CrossSectionDef(type="direct", params={"Iy": data["segments"][0][0]}),
        section_segments=segs,
        additional_factor=1.0,
        theory="euler-bernoulli",
        selected_active_combination_id=COMB,
    )
    return st


def load_nos(path: str) -> ProjectState:
    return nos_to_state(parse_nos(path))
