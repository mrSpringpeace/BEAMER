"""Import Ministatik .rez (definice průřezu).

Formát Ministatik *.rez má dva podformáty, rozpoznané podle počtu čísel
na druhém neprázdném řádku:

  Mode A – obrysová definice (1 číslo na řádku):
      <title>
      N_outer
      y z              (N_outer řádků)
      N_polygonal_holes
      [pro každou díru:]  N_pts \n  y z (N_pts řádků)
      N_circular_holes
      d y z            (N_circular_holes řádků; průměr, střed)

  Mode B – střednicová definice (2 čísla na řádku):
      <title>
      N_pts  N_segments
      thickness
      y z              (N_pts řádků = první segment)
      [pro každý další segment:]  N_pts \n  thickness \n  y z (N_pts řádků)
      N_circular_holes
      d y z

Mapování do našeho modelu:
  Mode A  →  jedno Body (vnější obrys + díry + kruhové díry → polygon-32)
  Mode B  →  každý segment = jedno Body (offset polyline o ±t/2);
             kruhové díry se přiřadí podle geografického obsahu k tělesu,
             ve kterém leží jejich střed (jinak se ignorují).
"""
from __future__ import annotations

import math
from typing import List, Optional

from .model import Body, CrossSectionDef


# ─────────────────────────────────────────────────────────────────
#  Vstupní bod – načtení ze souboru
# ─────────────────────────────────────────────────────────────────

def load_rez(path: str) -> CrossSectionDef:
    """Načte .rez ze souboru a vrátí CrossSectionDef typu 'polygon' s bodies."""
    # Ministatik soubory bývají v cp1250 (CZ); zkusíme to, fallback utf-8
    try:
        with open(path, encoding="cp1250") as f:
            txt = f.read()
    except UnicodeDecodeError:
        with open(path, encoding="utf-8", errors="replace") as f:
            txt = f.read()
    return parse_rez(txt)


def parse_rez(text: str) -> CrossSectionDef:
    """Parsuje obsah .rez (jako string) na CrossSectionDef."""
    # tokenizujeme: ponecháme řádky, ale jen ty neprázdné
    raw_lines = text.splitlines()
    lines: List[str] = [ln.strip() for ln in raw_lines if ln.strip()]
    if not lines:
        raise ValueError("Prázdný .rez soubor.")
    # první řádek = title (přeskočíme)
    cursor = [1]   # mutable index

    def next_line() -> str:
        if cursor[0] >= len(lines):
            raise ValueError("Neočekávaný konec .rez souboru.")
        ln = lines[cursor[0]]
        cursor[0] += 1
        return ln

    header = next_line()
    parts = header.split()
    if len(parts) == 1:
        return _parse_mode_a(int(parts[0]), next_line)
    if len(parts) >= 2:
        return _parse_mode_b(int(parts[0]), int(parts[1]), next_line)
    raise ValueError(f"Neznámá hlavička .rez: {header!r}")


# ─────────────────────────────────────────────────────────────────
#  Mode A – vnější obrys + díry + kruhové díry
# ─────────────────────────────────────────────────────────────────

def _parse_mode_a(n_outer: int, next_line) -> CrossSectionDef:
    outer = [_read_yz(next_line()) for _ in range(n_outer)]
    n_holes = int(next_line())
    holes = []
    for _ in range(n_holes):
        npts = int(next_line())
        holes.append([_read_yz(next_line()) for __ in range(npts)])
    try:
        n_circ = int(next_line())
    except ValueError:
        n_circ = 0
    for _ in range(n_circ):
        d, y, z = (float(x) for x in next_line().split())
        holes.append(_circle_to_polygon(d / 2.0, y, z))
    body = Body(points=outer, holes=holes)
    return CrossSectionDef(type="polygon", bodies=[body])


# ─────────────────────────────────────────────────────────────────
#  Mode B – střednice + tloušťka, N segmentů
# ─────────────────────────────────────────────────────────────────

def _parse_mode_b(npts_first: int, n_segments: int, next_line) -> CrossSectionDef:
    segments = []
    n = npts_first
    for s in range(n_segments):
        if s > 0:
            n = int(next_line())
        thickness = float(next_line())
        pts = [_read_yz_tuple(next_line()) for _ in range(n)]
        segments.append((pts, thickness))

    try:
        n_circ = int(next_line())
    except (ValueError, StopIteration):
        n_circ = 0
    circles = []
    for _ in range(n_circ):
        d, y, z = (float(x) for x in next_line().split())
        circles.append((d / 2.0, y, z))

    bodies = []
    for pts, t in segments:
        outline = _offset_polyline_to_polygon(pts, t)
        if outline:
            bodies.append(Body(points=outline, holes=[]))

    # přiřaď kruhové díry podle obsažení
    for r, y, z in circles:
        idx = _which_body_contains(bodies, y, z)
        hole = _circle_to_polygon(r, y, z)
        if idx is not None:
            bodies[idx].holes.append(hole)
        # jinak ignorujeme (kruhová díra mimo jakékoli tělo)

    if not bodies:
        raise ValueError(".rez Mode B: žádné platné segmenty.")
    return CrossSectionDef(type="polygon", bodies=bodies)


# ─────────────────────────────────────────────────────────────────
#  Pomocné: čtení, offset polyline, kruh → polygon, point-in-poly
# ─────────────────────────────────────────────────────────────────

def _read_yz(line: str) -> dict:
    y, z = (float(x) for x in line.split()[:2])
    return {"y": y, "z": z}


def _read_yz_tuple(line: str):
    y, z = (float(x) for x in line.split()[:2])
    return (y, z)


def _circle_to_polygon(r: float, cy: float, cz: float, n: int = 32) -> list:
    return [{"y": cy + r * math.cos(2 * math.pi * i / n),
             "z": cz + r * math.sin(2 * math.pi * i / n)}
            for i in range(n)]


def _offset_polyline_to_polygon(pts, thickness: float):
    """Otevřená polyline (N pts) + tloušťka → uzavřený offset polygon.
    Vrací list dictů [{'y':..,'z':..}, ...]."""
    if len(pts) < 2 or thickness <= 0:
        return []
    h = thickness / 2.0
    # hrany (s normálou = +90° levá strana)
    edges = []
    for i in range(len(pts) - 1):
        y1, z1 = pts[i]
        y2, z2 = pts[i + 1]
        L = math.hypot(y2 - y1, z2 - z1)
        if L < 1e-12:
            continue
        nx = -(z2 - z1) / L
        nz = (y2 - y1) / L
        edges.append(((y1, z1), (y2, z2), (nx, nz)))
    if not edges:
        return []

    # left strana: posuň každou hranu o +h·n, najdi průsečíky sousedních;
    # konce: prodlužuj přímou kolmici (square cap)
    left = []
    right = []
    P0, Q0, n0 = edges[0]
    left.append((P0[0] + h * n0[0], P0[1] + h * n0[1]))
    right.append((P0[0] - h * n0[0], P0[1] - h * n0[1]))
    for k in range(1, len(edges)):
        Pp, Qp, np_ = edges[k - 1]
        P, Q, n = edges[k]
        L1a = (Pp[0] + h * np_[0], Pp[1] + h * np_[1])
        L1b = (Qp[0] + h * np_[0], Qp[1] + h * np_[1])
        L2a = (P[0] + h * n[0],   P[1] + h * n[1])
        L2b = (Q[0] + h * n[0],   Q[1] + h * n[1])
        R1a = (Pp[0] - h * np_[0], Pp[1] - h * np_[1])
        R1b = (Qp[0] - h * np_[0], Qp[1] - h * np_[1])
        R2a = (P[0] - h * n[0],   P[1] - h * n[1])
        R2b = (Q[0] - h * n[0],   Q[1] - h * n[1])
        left.append(_intersect_lines(L1a, L1b, L2a, L2b))
        right.append(_intersect_lines(R1a, R1b, R2a, R2b))
    # poslední bod (cap)
    Pe, Qe, ne = edges[-1]
    left.append((Qe[0] + h * ne[0], Qe[1] + h * ne[1]))
    right.append((Qe[0] - h * ne[0], Qe[1] - h * ne[1]))

    # uzavřený polygon CCW: left (od P0 k Qe) + reversed right
    poly = [{"y": p[0], "z": p[1]} for p in left]
    poly += [{"y": p[0], "z": p[1]} for p in reversed(right)]
    return poly


def _intersect_lines(A1, A2, B1, B2):
    """Průsečík čar A1-A2 a B1-B2 (parametricky). Rovnoběžné → střed (Qp ~ P)."""
    x1, y1 = A1; x2, y2 = A2
    x3, y3 = B1; x4, y4 = B2
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-12:
        # rovnoběžné → vezmi koncový bod první čáry (= P_i + h·n_prev), což je
        # logická hranice „bez ostrého rohu"
        return (A2[0], A2[1])
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def _which_body_contains(bodies, y: float, z: float) -> Optional[int]:
    for i, b in enumerate(bodies):
        if _point_in_poly(y, z, b.points):
            return i
    return None


def _point_in_poly(y: float, z: float, poly) -> bool:
    n = len(poly)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        yi, zi = poly[i]["y"], poly[i]["z"]
        yj, zj = poly[j]["y"], poly[j]["z"]
        if ((zi > z) != (zj > z)) and \
           (y < (yj - yi) * (z - zi) / ((zj - zi) + 1e-30) + yi):
            inside = not inside
        j = i
    return inside
