"""Import skutečné geometrie průřezu z textu a IGES/IGS křivek.

Výstupem je vždy ``CrossSectionDef(type="polygon", bodies=...)`` v mm. Import
je záměrně striktní: otevřená smyčka, nerovinný IGES nebo nepodporované entity
bez použitelné křivky skončí chybou, nikoli domyšlenou geometrií.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass

import numpy as np

from .model import Body, CrossSectionDef


class SectionImportError(ValueError):
    """Vstup nepopisuje jednoznačný uzavřený průřez."""


def _signed_area(points: list[tuple[float, float]]) -> float:
    return 0.5*sum(
        x1*y2-x2*y1
        for (x1, y1), (x2, y2) in zip(points, points[1:]+points[:1])
    )


def _segments_intersect(a, b, c, d, tol: float) -> bool:
    def orient(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])

    def on_segment(p, q, r):
        return (min(p[0], r[0])-tol <= q[0] <= max(p[0], r[0])+tol
                and min(p[1], r[1])-tol <= q[1] <= max(p[1], r[1])+tol)

    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    if ((o1 > tol and o2 < -tol) or (o1 < -tol and o2 > tol)) and (
            (o3 > tol and o4 < -tol) or (o3 < -tol and o4 > tol)):
        return True
    return ((abs(o1) <= tol and on_segment(a, c, b))
            or (abs(o2) <= tol and on_segment(a, d, b))
            or (abs(o3) <= tol and on_segment(c, a, d))
            or (abs(o4) <= tol and on_segment(c, b, d)))


def _ring_edges(ring):
    return list(zip(ring, ring[1:]+ring[:1]))


def _validate_simple_ring(ring, tol: float):
    edges = _ring_edges(ring)
    for i, (a, b) in enumerate(edges):
        for j in range(i+1, len(edges)):
            if j in (i+1, len(edges)-1 if i == 0 else -1):
                continue
            c, d = edges[j]
            if _segments_intersect(a, b, c, d, tol):
                raise SectionImportError("Smyčka průřezu se sama kříží nebo překrývá.")


def _validate_ring_boundaries(rings, tol: float):
    for i, first in enumerate(rings):
        for second in rings[i+1:]:
            if any(_segments_intersect(a, b, c, d, tol)
                   for a, b in _ring_edges(first)
                   for c, d in _ring_edges(second)):
                raise SectionImportError("Smyčky průřezu se kříží nebo dotýkají.")


def _point_in_ring(point: tuple[float, float], ring: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    j = len(ring)-1
    for i, (xi, yi) in enumerate(ring):
        xj, yj = ring[j]
        if (yi > y) != (yj > y):
            xcut = (xj-xi)*(y-yi)/(yj-yi)+xi
            if x < xcut:
                inside = not inside
        j = i
    return inside


def _clean_ring(points: list[tuple[float, float]], tol: float = 1e-9):
    out: list[tuple[float, float]] = []
    for point in points:
        p = (float(point[0]), float(point[1]))
        if not out or math.dist(p, out[-1]) > tol:
            out.append(p)
    if len(out) > 1 and math.dist(out[0], out[-1]) <= tol:
        out.pop()
    if len(out) < 3:
        raise SectionImportError("Každá smyčka průřezu musí mít alespoň tři různé body.")
    span = max(max(p[0] for p in out)-min(p[0] for p in out),
               max(p[1] for p in out)-min(p[1] for p in out), 1.0)
    _validate_simple_ring(out, tol*span)
    if abs(_signed_area(out)) <= tol*tol:
        raise SectionImportError("Smyčka průřezu má nulovou plochu.")
    return out


def _rings_to_bodies(rings: list[list[tuple[float, float]]]) -> list[Body]:
    """Klasifikuje vnořené smyčky sudá=outer, lichá=hole."""
    clean = [_clean_ring(ring) for ring in rings]
    span = max((max(max(p[axis] for p in ring)-min(p[axis] for p in ring)
                    for axis in (0, 1)) for ring in clean), default=1.0)
    _validate_ring_boundaries(clean, max(1e-9*span, 1e-9))
    order = sorted(range(len(clean)), key=lambda i: abs(_signed_area(clean[i])), reverse=True)
    parent: dict[int, int | None] = {}
    depth: dict[int, int] = {}
    for pos, idx in enumerate(order):
        containers = [j for j in order[:pos] if _point_in_ring(clean[idx][0], clean[j])]
        par = min(containers, key=lambda j: abs(_signed_area(clean[j]))) if containers else None
        parent[idx] = par
        depth[idx] = 0 if par is None else depth[par]+1
    bodies = []
    body_for_ring = {}
    for idx in order:
        if depth[idx] % 2 == 0:
            body = Body(points=[{"y": y, "z": z} for y, z in clean[idx]], holes=[])
            bodies.append(body)
            body_for_ring[idx] = body
        else:
            par = parent[idx]
            while par is not None and depth[par] % 2:
                par = parent[par]
            if par is None or par not in body_for_ring:
                raise SectionImportError("Díru nelze přiřadit k vnějšímu obrysu.")
            body_for_ring[par].holes.append([{"y": y, "z": z} for y, z in clean[idx]])
    return bodies


def _text_numbers(line: str, line_no: int) -> tuple[float, float] | None:
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.lower().replace(" ", "") in ("y,z", "x,y", "y;z", "x;y"):
        return None
    if ";" in stripped:
        parts = [p.strip().replace(",", ".") for p in stripped.split(";") if p.strip()]
    else:
        ws = stripped.split()
        if len(ws) == 2:
            parts = [p.replace(",", ".") for p in ws]
        else:
            parts = [p.strip() for p in stripped.split(",") if p.strip()]
    if len(parts) != 2:
        raise SectionImportError(f"Řádek {line_no}: očekávány právě dvě souřadnice y,z.")
    try:
        return float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise SectionImportError(f"Řádek {line_no}: neplatná číselná souřadnice.") from exc


def parse_section_text(text: str, name: str = "") -> CrossSectionDef:
    """Načte body ``y z``; značky OUTER/HOLE/BODY oddělují smyčky a tělesa."""
    rings: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    explicit_roles: list[str] = []
    role = "auto"

    def finish():
        nonlocal current
        if current:
            rings.append(current)
            explicit_roles.append(role)
            current = []

    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].split("//", 1)[0].strip()
        marker = line.upper().rstrip(":")
        if marker in ("OUTER", "HOLE", "BODY"):
            finish()
            role = "outer" if marker in ("OUTER", "BODY") else "hole"
            continue
        if not line:
            finish()
            role = "auto"
            continue
        point = _text_numbers(line, line_no)
        if point is not None:
            current.append(point)
    finish()
    if not rings:
        raise SectionImportError("Textový soubor neobsahuje žádnou smyčku průřezu.")

    if any(r != "auto" for r in explicit_roles):
        clean_rings = [_clean_ring(ring) for ring in rings]
        span = max((max(max(p[axis] for p in ring)-min(p[axis] for p in ring)
                        for axis in (0, 1)) for ring in clean_rings), default=1.0)
        _validate_ring_boundaries(clean_rings, max(1e-9*span, 1e-9))
        bodies: list[Body] = []
        active: Body | None = None
        active_outer = None
        for clean, ring_role in zip(clean_rings, explicit_roles):
            if ring_role in ("outer", "auto"):
                active = Body(points=[{"y": y, "z": z} for y, z in clean], holes=[])
                bodies.append(active)
                active_outer = clean
            elif active is None:
                raise SectionImportError("Značka HOLE musí následovat za OUTER nebo BODY.")
            elif active_outer is None or not _point_in_ring(clean[0], active_outer):
                raise SectionImportError("Smyčka HOLE neleží uvnitř předchozího OUTER/BODY.")
            else:
                active.holes.append([{"y": y, "z": z} for y, z in clean])
    else:
        bodies = _rings_to_bodies(rings)
    return CrossSectionDef(type="polygon", bodies=bodies, name=name)


def load_section_text(path: str) -> CrossSectionDef:
    with open(path, "r", encoding="utf-8-sig", errors="strict") as stream:
        return parse_section_text(stream.read(), os.path.splitext(os.path.basename(path))[0])


def _iges_number(token: str) -> float:
    token = token.strip().replace("D", "E").replace("d", "e")
    return float(token) if token else 0.0


def _iges_int(field: str, default: int = 0) -> int:
    try:
        return int(field.strip())
    except (TypeError, ValueError):
        return default


def _global_params(lines: list[str]) -> list[str]:
    data = "".join(line[:72] for line in lines)
    out: list[str] = []
    token: list[str] = []
    parameter_sep = ","
    record_sep = ";"
    i = 0
    while i < len(data):
        match = re.match(r"(\d+)H", data[i:], flags=re.IGNORECASE)
        if match:
            count = int(match.group(1))
            i += len(match.group(0))
            value = data[i:i+count]
            token.append(value)
            # První parametr sám definuje oddělovač dalších parametrů.
            if not out and len(token) == 1 and len(value) == 1:
                parameter_sep = value
            i += count
            continue
        char = data[i]
        if char == parameter_sep:
            out.append("".join(token).strip())
            token = []
            if len(out) == 2 and len(out[1]) == 1:
                record_sep = out[1]
            i += 1
            continue
        if char == record_sep:
            out.append("".join(token).strip())
            break
        token.append(char)
        i += 1
    return out


def _iges_scale_to_mm(lines: list[str]) -> float:
    params = _global_params(lines)
    flag = _iges_int(params[13], 2) if len(params) > 13 else 2
    factors = {
        1: 25.4, 2: 1.0, 4: 304.8, 5: 1_609_344.0, 6: 1000.0,
        7: 1_000_000.0, 8: 0.0254, 9: 0.001, 10: 10.0, 11: 0.0000254,
    }
    if flag not in factors:
        raise SectionImportError(f"IGES používá nepodporovanou jednotkovou volbu {flag}.")
    return factors[flag]


@dataclass(frozen=True)
class _DirectoryEntry:
    sequence: int
    entity_type: int
    transform: int
    form: int


def _iges_tokens(data: str) -> list[str]:
    return [token.strip() for token in re.split(r"[,;]", data) if token.strip()]


def _transform_point(point, matrix):
    x, y, z = point
    if matrix is None:
        return float(x), float(y), float(z)
    return (
        matrix[0]*x+matrix[1]*y+matrix[2]*z+matrix[3],
        matrix[4]*x+matrix[5]*y+matrix[6]*z+matrix[7],
        matrix[8]*x+matrix[9]*y+matrix[10]*z+matrix[11],
    )


def _basis(i: int, degree: int, u: float, knots: list[float], n_ctrl: int) -> float:
    if degree == 0:
        if knots[i] <= u < knots[i+1] or (i == n_ctrl-1 and u == knots[-1]):
            return 1.0
        return 0.0
    left_den = knots[i+degree]-knots[i]
    right_den = knots[i+degree+1]-knots[i+1]
    left = ((u-knots[i])/left_den*_basis(i, degree-1, u, knots, n_ctrl)
            if left_den else 0.0)
    right = ((knots[i+degree+1]-u)/right_den
             *_basis(i+1, degree-1, u, knots, n_ctrl) if right_den else 0.0)
    return left+right


def _bspline_points(values: list[float]) -> list[tuple[float, float, float]]:
    if len(values) < 8:
        raise SectionImportError("Neúplná IGES entita 126 (B-spline).")
    k, degree = int(values[0]), int(values[1])
    n_ctrl = k+1
    cursor = 6
    knot_count = k+degree+2
    knots = values[cursor:cursor+knot_count]
    cursor += knot_count
    weights = values[cursor:cursor+n_ctrl]
    cursor += n_ctrl
    flat = values[cursor:cursor+3*n_ctrl]
    cursor += 3*n_ctrl
    if len(knots) != knot_count or len(weights) != n_ctrl or len(flat) != 3*n_ctrl:
        raise SectionImportError("Neúplná data řídicích bodů IGES B-spline.")
    ctrl = [tuple(flat[3*i:3*i+3]) for i in range(n_ctrl)]
    if len(values[cursor:cursor+2]) < 2:
        raise SectionImportError("IGES B-spline nemá rozsah parametru.")
    u0, u1 = values[cursor:cursor+2]
    count = max(16, 8*n_ctrl)
    out: list[tuple[float, float, float]] = []
    for step in range(count+1):
        u = u0+(u1-u0)*step/count
        nums = [_basis(i, degree, u, knots, n_ctrl)*weights[i] for i in range(n_ctrl)]
        den = sum(nums)
        if abs(den) <= 1e-15:
            raise SectionImportError("Singulární parametr IGES B-spline.")
        out.append((
            sum(nums[i]*ctrl[i][0] for i in range(n_ctrl))/den,
            sum(nums[i]*ctrl[i][1] for i in range(n_ctrl))/den,
            sum(nums[i]*ctrl[i][2] for i in range(n_ctrl))/den,
        ))
    return out


def _entity_points(entity_type: int, tokens: list[str]):
    values = [_iges_number(token) for token in tokens[1:]]
    if entity_type == 110:
        if len(values) < 6:
            raise SectionImportError("Neúplná IGES úsečka 110.")
        return [tuple(values[:3]), tuple(values[3:6])]
    if entity_type == 100:
        if len(values) < 7:
            raise SectionImportError("Neúplný IGES oblouk 100.")
        z, cx, cy, sx, sy, ex, ey = values[:7]
        a0, a1 = math.atan2(sy-cy, sx-cx), math.atan2(ey-cy, ex-cx)
        delta = (a1-a0) % (2.0*math.pi)
        if delta <= 1e-12:
            delta = 2.0*math.pi
        radius = math.hypot(sx-cx, sy-cy)
        count = max(8, int(math.ceil(delta/(math.pi/24.0))))
        return [(cx+radius*math.cos(a0+delta*i/count),
                 cy+radius*math.sin(a0+delta*i/count), z) for i in range(count+1)]
    if entity_type == 106:
        if len(values) < 3:
            raise SectionImportError("Neúplná IGES polyline 106.")
        ip, count = int(values[0]), int(values[1])
        data = values[2:]
        if ip == 1:
            z, data = data[0], data[1:]
            return [(data[2*i], data[2*i+1], z) for i in range(count)]
        stride = 3 if ip == 2 else 6 if ip == 3 else 0
        if not stride or len(data) < stride*count:
            raise SectionImportError(f"Nepodporovaný nebo neúplný IGES 106 IP={ip}.")
        return [tuple(data[stride*i:stride*i+3]) for i in range(count)]
    if entity_type == 126:
        return _bspline_points(values)
    return None


def _join_segments(segments: list[list[tuple[float, float, float]]]):
    if not segments:
        raise SectionImportError("IGES neobsahuje podporované křivky průřezu.")
    coords = np.asarray([p for segment in segments for p in segment], dtype=float)
    span = max(float(np.ptp(coords, axis=0).max()), 1.0)
    tol = max(1e-7*span, 1e-7)
    unused = [list(segment) for segment in segments]
    loops = []
    while unused:
        chain = unused.pop(0)
        while math.dist(chain[-1], chain[0]) > tol:
            found = None
            for i, segment in enumerate(unused):
                if math.dist(chain[-1], segment[0]) <= tol:
                    found = i, segment
                    break
                if math.dist(chain[-1], segment[-1]) <= tol:
                    found = i, list(reversed(segment))
                    break
            if found is None:
                raise SectionImportError("IGES křivky netvoří uzavřenou navazující smyčku.")
            idx, segment = found
            unused.pop(idx)
            chain.extend(segment[1:])
        chain[-1] = chain[0]
        loops.append(chain[:-1])
    return loops


def _project_planar(loops, scale: float):
    points = np.asarray([p for loop in loops for p in loop], dtype=float)*scale
    ranges = np.ptp(points, axis=0)
    span = max(float(ranges.max()), 1.0)
    flat = int(np.argmin(ranges))
    if ranges[flat] <= 1e-6*span:
        axes = {2: (0, 1), 1: (0, 2), 0: (1, 2)}[flat]
        return [[(p[axes[0]]*scale, p[axes[1]]*scale) for p in loop] for loop in loops]
    center = points.mean(axis=0)
    _, singular, vh = np.linalg.svd(points-center, full_matrices=False)
    if singular[-1] > 1e-5*max(singular[0], 1e-12):
        raise SectionImportError("IGES křivka není rovinná; průřez musí ležet v jedné rovině.")
    normal = vh[-1]
    reference = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(reference, normal))) > 0.9:
        reference = np.array([0.0, 1.0, 0.0])
    axis_y = reference-np.dot(reference, normal)*normal
    axis_y /= np.linalg.norm(axis_y)
    axis_z = np.cross(normal, axis_y)
    return [[(float(np.dot(np.asarray(p)*scale-center, axis_y)),
              float(np.dot(np.asarray(p)*scale-center, axis_z))) for p in loop]
            for loop in loops]


def parse_iges(text: str, name: str = "") -> CrossSectionDef:
    lines = [line.rstrip("\r\n").ljust(80) for line in text.splitlines() if line.strip()]
    globals_ = [line for line in lines if len(line) > 72 and line[72] == "G"]
    directories = [line for line in lines if len(line) > 72 and line[72] == "D"]
    parameters = [line for line in lines if len(line) > 72 and line[72] == "P"]
    if not directories or not parameters:
        raise SectionImportError("Soubor nemá platné IGES Directory/Parameter záznamy.")
    entries = {}
    for i in range(0, len(directories)-1, 2):
        first, second = directories[i], directories[i+1]
        seq = _iges_int(first[73:80])
        entries[seq] = _DirectoryEntry(
            seq, _iges_int(first[0:8]), _iges_int(first[48:56]),
            _iges_int(second[32:40]),
        )
    pdata: dict[int, str] = {}
    for line in parameters:
        pointer = _iges_int(line[64:72])
        pdata[pointer] = pdata.get(pointer, "")+line[:64]
    token_map = {seq: _iges_tokens(pdata.get(seq, "")) for seq in entries}
    transforms = {}
    for seq, entry in entries.items():
        tokens = token_map[seq]
        if entry.entity_type == 124 and len(tokens) >= 13:
            transforms[seq] = [_iges_number(v) for v in tokens[1:13]]
    unsupported = set()
    segments = []
    for seq, entry in entries.items():
        tokens = token_map[seq]
        if not tokens or entry.entity_type in (102, 124):
            continue
        points = _entity_points(entry.entity_type, tokens)
        if points is None:
            unsupported.add(entry.entity_type)
            continue
        matrix = transforms.get(entry.transform)
        segments.append([_transform_point(point, matrix) for point in points])
    if not segments:
        detail = f"; nalezené typy: {sorted(unsupported)}" if unsupported else ""
        raise SectionImportError("IGES neobsahuje podporované křivky 100/106/110/126"+detail)
    loops_3d = _join_segments(segments)
    loops_2d = _project_planar(loops_3d, _iges_scale_to_mm(globals_))
    return CrossSectionDef(type="polygon", bodies=_rings_to_bodies(loops_2d), name=name)


def load_iges(path: str) -> CrossSectionDef:
    with open(path, "r", encoding="ascii", errors="replace") as stream:
        return parse_iges(stream.read(), os.path.splitext(os.path.basename(path))[0])
