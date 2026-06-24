"""Konstrukční tvar průřezu z primitiv (obdélník, kruh) a booleovských operací.

Vyhodnotí seznam tvarů (add / subtract / intersect) přes shapely a převede
výsledek na `bodies` = [(outer_pts, [hole_pts, …]), …] v konvenci průřezu
(y vodorovně, z svisle), který spotřebuje CrossSection.

Tvar (dict):
  {"kind": "rect", "op": "add"|"sub"|"int", "y":cy, "z":cz, "w":, "h":, "angle":deg}
  {"kind": "circle", "op": ..., "y":cy, "z":cz, "d": průměr}
  (poloha y = vodorovná osa náhledu; klíč "x" je akceptován pro zpětnou kompat.)
"""
from __future__ import annotations


def _cy(s):
    return float(s.get("y", s.get("x", 0)) or 0)


def _primitive(s, n_circle=64):
    from shapely.geometry import Polygon, Point
    from shapely import affinity
    k = s.get("kind")
    if k == "rect":
        y, z = _cy(s), float(s.get("z", 0) or 0)
        w, h = float(s.get("w", 0)), float(s.get("h", 0))
        if w <= 0 or h <= 0:
            return None
        p = Polygon([(y - w/2, z - h/2), (y + w/2, z - h/2),
                     (y + w/2, z + h/2), (y - w/2, z + h/2)])
        ang = float(s.get("angle", 0) or 0)
        if abs(ang) > 1e-9:
            p = affinity.rotate(p, ang, origin=(y, z))
        return p
    if k == "circle":
        r = float(s.get("d", 0)) / 2.0
        if r <= 0:
            return None
        return Point(_cy(s), float(s.get("z", 0) or 0)).buffer(
            r, quad_segs=max(8, n_circle // 4))
    return None


def shapes_to_bodies(shapes, n_circle=64):
    """Vyhodnotí konstrukční tvar → bodies. Prázdné/neplatné → []."""
    if not shapes:
        return []
    geom = None
    for s in shapes:
        g = _primitive(s, n_circle)
        if g is None or g.is_empty:
            continue
        op = s.get("op", "add")
        if geom is None:
            geom = g if op != "sub" else None      # první „sub" na prázdné = nic
            continue
        try:
            if op == "add":
                geom = geom.union(g)
            elif op == "sub":
                geom = geom.difference(g)
            elif op == "int":
                geom = geom.intersection(g)
        except Exception:
            pass
    if geom is None or geom.is_empty:
        return []

    polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    bodies = []
    for poly in polys:
        if poly.geom_type != "Polygon" or poly.is_empty or poly.area < 1e-9:
            continue
        outer = [(float(x), float(y)) for x, y in poly.exterior.coords[:-1]]
        holes = [[(float(x), float(y)) for x, y in ring.coords[:-1]]
                 for ring in poly.interiors]
        if len(outer) >= 3:
            bodies.append((outer, holes))
    return bodies
