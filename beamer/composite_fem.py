"""B2 – podpora vícemateriálového FEM (variabilní G/E po řezu).

První krok: přiřadit každému elementu sítě jeho materiál podle toho, ve které
části sestavy leží těžiště elementu (point-in-polygon). Výsledné pole G/E per
element pak půjde do vážené assembly warping/shear (torze/smyk) – jednomateriál
se redukuje na dnešní stav (G se vytkne).
"""
from __future__ import annotations


def _point_in_poly(y, z, poly):
    """Ray casting: leží (y,z) uvnitř polygonu [(y,z), …]?"""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        yi, zi = poly[i][0], poly[i][1]
        yj, zj = poly[j][0], poly[j][1]
        if ((zi > z) != (zj > z)) and \
           (y < (yj - yi) * (z - zi) / (zj - zi + 1e-30) + yi):
            inside = not inside
        j = i
    return inside


def _in_region(y, z, outer, holes):
    if not _point_in_poly(y, z, outer):
        return False
    for h in holes or []:
        if h and _point_in_poly(y, z, h):
            return False
    return True


def element_centroids(nodes, elements):
    """Těžiště elementů z rohových uzlů (T6/T10: první 3 indexy = rohy)."""
    out = []
    for elem in elements:
        c = elem[:3]
        cy = (nodes[c[0]][0] + nodes[c[1]][0] + nodes[c[2]][0]) / 3.0
        cz = (nodes[c[0]][1] + nodes[c[1]][1] + nodes[c[2]][1]) / 3.0
        out.append((cy, cz))
    return out


def _tag_elements(nodes, elements, orig_polys):
    """Každému elementu (dle těžiště) přiřadí (G, E, material_id) z těles."""
    from shapely.geometry import Point
    tags = []
    fallback = orig_polys[0][1:] if orig_polys else (81000.0, 210000.0, None)
    for (ey, ez) in element_centroids(nodes, elements):
        pt = Point(ey, ez)
        hit = fallback
        for poly, G, E, mid in orig_polys:
            if poly.contains(pt) or poly.touches(pt):
                hit = (G, E, mid)
                break
        tags.append(hit)
    return tags


_MESH_CACHE = {}
_MESH_CACHE_MAX = 24


def _prop_signature(state, prop):
    """Levná obsahová signatura složeného PID (geometrie + G/E materiálů) pro
    cache sítě/warpingu – FEM se pak nepočítá znovu pro každou stanici."""
    from .sections_along import section_by_id
    from .composite import _material_by_id
    parts = getattr(prop, "composite_parts", None) or []
    sig = [round(float(getattr(prop, "rotation", 0.0)), 6)]
    for p in parts:
        sid, mid = p.get("section_id"), p.get("material_id")
        sec = section_by_id(state, sid)
        st = None
        if sec is not None:
            st = (getattr(sec, "type", None),
                  tuple(sorted((getattr(sec, "params", {}) or {}).items())),
                  round(float(getattr(sec, "rotation", 0.0)), 6))
        m = _material_by_id(state, mid)
        GE = (round(float(getattr(m, "G", 0.0)), 6),
              round(float(getattr(m, "E", 0.0)), 6)) if m else None
        sig.append((sid, mid, p.get("dy"), p.get("dz"), p.get("angle"), st, GE))
    return repr(sig)


def _composite_mesh_and_warp(state, prop):
    """Cachovaný obal: nasíťuje složený PID a vyřeší variabilní-G warping.
    Klíč = obsahová signatura PID (geometrie + G/E). Vrací (components, GJ, orig)
    nebo None."""
    key = _prop_signature(state, prop)
    hit = _MESH_CACHE.get(key)
    if hit is not None:
        return hit
    res = _composite_mesh_and_warp_impl(state, prop)
    if res is not None:
        if len(_MESH_CACHE) >= _MESH_CACHE_MAX:
            _MESH_CACHE.clear()
        _MESH_CACHE[key] = res
    return res


def _composite_mesh_and_warp_impl(state, prop):
    """Nasíťuje složený PID po souvislých komponentách (shapely union) a v každé
    vyřeší variabilní-G warping. Vrací (components, GJ, orig) kde component je
    dict {nodes, elements, elem_G, tags, omega, cy, cz, GJ}. Sdílené jádro pro
    torzní tuhost i pro pole napětí. None, když nelze sestavit."""
    from .composite import _positioned_bodies
    from . import _fem
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    pbodies = _positioned_bodies(state, prop)
    if not pbodies:
        return None
    orig = []          # (shapely_polygon, G, material_id)
    polys = []
    for (outer, holes), mat in pbodies:
        try:
            poly = Polygon(outer, holes or [])
            if not poly.is_valid:
                poly = poly.buffer(0)
        except Exception:
            continue
        G = float(mat.G) if mat else 81000.0
        E = float(mat.E) if mat else 210000.0
        orig.append((poly, G, E, getattr(mat, "id", None)))
        polys.append(poly)
    if not polys:
        return None

    _fem.set_element_order("T6")
    merged = unary_union(polys)
    comps = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
    components = []
    GJ = 0.0
    for comp in comps:
        if comp.geom_type != "Polygon" or comp.area < 1e-9:
            continue
        outer = [(x, y) for x, y in comp.exterior.coords[:-1]]
        holes = [[(x, y) for x, y in r.coords[:-1]] for r in comp.interiors]
        nodes, elements = _fem.triangulate_section(outer, holes or None)
        g = _fem.compute_geometric_properties(nodes, elements)
        cy, cz, Ixx, Iyy = g["cy"], g["cz"], g["Ixx_c"], g["Iyy_c"]
        tags = _tag_elements(nodes, elements, orig)
        elem_G = [t[0] for t in tags]
        omega, K = _fem.solve_warping_function(nodes, elements, cy, cz, elem_G=elem_G)
        GJc = _fem.compute_torsion_constant(nodes, elements, omega, K, Ixx, Iyy,
                                            elem_G=elem_G, cy=cy, cz=cz)
        GJ += GJc
        # geometrie transverzálního smyku (E-vážený Žuravskij): z, E, plocha,
        # tětiva b(z) per element (nezávisí na zatížení → počítá se jednou)
        import numpy as _np
        cents = element_centroids(nodes, elements)
        ne = len(elements)
        zc = _np.array([c[1] for c in cents])
        Ee = _np.array([t[1] for t in tags])
        Ae = _np.zeros(ne)
        be = _np.zeros(ne)
        y0, z0, y1, z1 = comp.bounds
        for ei, elem in enumerate(elements):
            p = nodes[elem[0]]; q = nodes[elem[1]]; r = nodes[elem[2]]
            Ae[ei] = 0.5 * abs((q[0]-p[0])*(r[1]-p[1]) - (r[0]-p[0])*(q[1]-p[1]))
            be[ei] = _chord_length(comp, zc[ei], y0 - 1.0, y1 + 1.0)
        components.append({"nodes": nodes, "elements": elements, "elem_G": elem_G,
                           "tags": tags, "omega": omega, "cy": cy, "cz": cz, "GJ": GJc,
                           "zc": zc, "Ee": Ee, "Ae": Ae, "be": be})
    return components, GJ, orig


def _chord_length(poly, z, y_lo, y_hi):
    """Délka průniku vodorovné přímky ve výšce z s polygonem (šířka b(z))."""
    from shapely.geometry import LineString
    try:
        inter = poly.intersection(LineString([(y_lo, z), (y_hi, z)]))
    except Exception:
        return 0.0
    if inter.is_empty:
        return 0.0
    if inter.geom_type == "LineString":
        return inter.length
    if inter.geom_type in ("MultiLineString", "GeometryCollection"):
        return float(sum(getattr(g, "length", 0.0) for g in inter.geoms))
    return 0.0


def _material_at(orig, y, z):
    """(G, E, material_id) materiálu, který bod (y,z) obsahuje; jinak None."""
    from shapely.geometry import Point
    pt = Point(y, z)
    for poly, G, E, mid in orig:
        if poly.contains(pt) or poly.touches(pt):
            return G, E, mid
    return None


def composite_torsion_GJ(state, prop):
    """Efektivní torzní tuhost (GJ)_eff složeného PID přes variabilní-G FEM
    Saint-Venant. Sečte přes souvislé komponenty geometrie: v každé nasíťuje
    sjednocený tvar a každému elementu přiřadí G podle materiálu tělesa, ve
    kterém leží jeho těžiště (variabilní-G warping). Pro jeden materiál se
    redukuje na G·J (geometrická torze). Vrací GJ [N·mm²] nebo None."""
    res = _composite_mesh_and_warp(state, prop)
    if res is None:
        return None
    return res[1]


def composite_stress_field(state, prop, N, My, Mk, V=0.0):
    """Plné per-materiálové napětí složeného PID přes FEM pole: v každém elementu
    kombinuje normálové σ (B1, modulem vážené), torzní smyk τ_t (variabilní-G
    warping) a transverzální smyk τ_V (E-vážený Žuravskij, V·Q_E/(EIy·b)) ve
    STEJNÉM vlákně a počítá von Mises. τ_t a τ_V se sčítají konzervativně
    (|τ_t|+|τ_V|, jako u jednomateriálu). Vrací dict material_id →
    {material, E, sigma_max, tau_max, mises_max} (+ '_GJ'). None, když nelze."""
    import numpy as np
    from .composite import composite_weighted
    from . import _fem
    w = composite_weighted(state, prop)
    if w is None:
        return None
    res = _composite_mesh_and_warp(state, prop)
    if res is None:
        return None
    components, GJ, orig = res
    thetap = (Mk / GJ) if (GJ and abs(GJ) > 1e-9) else 0.0
    mats = {m.id: m for m in getattr(state, "materials", None) or []}
    agg = {}
    for comp in components:
        nodes, elements = comp["nodes"], comp["elements"]
        coords, shear = _fem.torsion_shear_centroids(
            nodes, elements, comp["omega"], comp["cy"], comp["cz"])
        # transverzální smyk: E-vážený statický moment nad vláknem (kumulativně
        # od horního okraje) → τ_V = V·Q_E/(EIy·b)
        zc, Ee, Ae, be = comp["zc"], comp["Ee"], comp["Ae"], comp["be"]
        order = np.argsort(zc)[::-1]         # od nejvyššího z dolů
        QE = np.zeros(len(zc))
        cum = 0.0
        for idx in order:
            QE[idx] = cum                    # moment plochy STRIKTNĚ nad vláknem
            cum += Ee[idx] * (zc[idx] - w.z_NA) * Ae[idx]
        for ei, (G_e, E_e, mid) in enumerate(comp["tags"]):
            ez = coords[ei, 1]
            sig = E_e * (N / w.EA + My * (ez - w.z_NA) / w.EIy)
            tau_t = G_e * thetap * float(np.hypot(shear[ei, 0], shear[ei, 1]))
            tau_V = (abs(V * QE[ei] / (w.EIy * be[ei]))
                     if (be[ei] > 1e-9 and abs(w.EIy) > 1e-9) else 0.0)
            tau = abs(tau_t) + tau_V         # konzervativní součet
            mis = float(np.sqrt(sig * sig + 3.0 * tau * tau))
            m = mats.get(mid)
            a = agg.setdefault(mid, {"material": getattr(m, "name", mid),
                                     "E": E_e, "Re": getattr(m, "Re", 0.0),
                                     "Rm": getattr(m, "Rm", 0.0),
                                     "sigma_max": 0.0, "tau_max": 0.0, "mises_max": 0.0})
            a["sigma_max"] = max(a["sigma_max"], abs(sig))
            a["tau_max"] = max(a["tau_max"], tau)
            a["mises_max"] = max(a["mises_max"], mis)
    return {"materials": agg, "_GJ": GJ}


def assign_element_regions(nodes, elements, regions):
    """Přiřadí každému elementu index oblasti (0..), do které padne jeho těžiště.
    `regions` = list ((outer, holes), payload). Vrací (idx_list, payloads) kde
    idx_list[e] = index oblasti (nebo -1 nezařazeno) a payloads jsou předané
    hodnoty (např. materiál/G) v pořadí regionů."""
    cents = element_centroids(nodes, elements)
    idx = []
    for (cy, cz) in cents:
        found = -1
        for ri, ((outer, holes), _payload) in enumerate(regions):
            if _in_region(cy, cz, outer, holes):
                found = ri
                break
        idx.append(found)
    payloads = [p for (_g, p) in regions]
    return idx, payloads
