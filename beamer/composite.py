"""Skládání složeného průřezu (PID) z hotových profilů knihovny.

Každá část = dict {section_id, material_id, dy, dz, angle}. Geometrie každé části
se vezme z knihovního průřezu (centroidálně), otočí o `angle` a posune o (dy,dz);
všechny části se sloučí do jednoho vícetělesového CrossSectionDef (`bodies`).

Toto je GEOMETRICKÉ skládání (v1 – „kalená tyč v trubce" vypadá správně a spočítá
se jako dnešní jednomateriálový kompozit). Modulem vážený vícemateriálový výpočet
(EA, EIy, neutrální osa, σ per materiál) přijde jako druhý krok.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .model import CrossSectionDef, Body
from .section import build_section


def _rot_trans(pts, angle_deg, dy, dz):
    a = math.radians(angle_deg or 0.0)
    ca, sa = math.cos(a), math.sin(a)
    return [(y * ca - z * sa + dy, y * sa + z * ca + dz) for y, z in pts]


def _circle_poly(r, n=64):
    return [(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n))
            for k in range(n)]


def section_bodies_centroidal(sdef):
    """Geometrie průřezu jako [(outer, [holes]), …] v centroidálních souřadnicích
    (těžiště v 0,0). Pokrývá polygon/construction (vč. děr), kruh/trubku,
    box (díra z parametrů) i plné parametrické profily (jedno těleso)."""
    cs = build_section(sdef, fem=False)
    if getattr(cs, "bodies_c", None):
        return [([tuple(p) for p in outer], [[tuple(q) for q in h] for h in holes])
                for outer, holes in cs.bodies_c]
    t = sdef.type
    if t in ("circle", "tube"):
        ro = getattr(cs, "_circle_r_out", 0.0) or 0.0
        ri = getattr(cs, "_circle_r_in", 0.0) or 0.0
        return [(_circle_poly(ro), [_circle_poly(ri)] if ri > 1e-9 else [])]
    if t == "box":
        p = sdef.params or {}
        B, H, tw = float(p.get("B", 100)), float(p.get("H", 200)), float(p.get("tw", 6))
        outer = [(-B/2, -H/2), (B/2, -H/2), (B/2, H/2), (-B/2, H/2)]
        bi, hi = B/2 - tw, H/2 - tw
        hole = [(-bi, -hi), (bi, -hi), (bi, hi), (-bi, hi)]
        return [(outer, [hole] if bi > 0 and hi > 0 else [])]
    if getattr(cs, "_pts_c", None):
        return [(list(cs._pts_c), [])]
    return []


def assemble_parts(state, parts):
    """Z částí (list dict {section_id, dy, dz, angle}) sestaví bodies (list[Body])."""
    from .sections_along import section_by_id
    bodies = []
    for part in parts or []:
        sec = section_by_id(state, part.get("section_id"))
        if sec is None:
            continue
        dy, dz = float(part.get("dy", 0.0)), float(part.get("dz", 0.0))
        ang = float(part.get("angle", 0.0))
        mid = part.get("material_id")
        for outer, holes in section_bodies_centroidal(sec):
            o = _rot_trans(outer, ang, dy, dz)
            hs = [_rot_trans(h, ang, dy, dz) for h in holes]
            bodies.append(Body(
                points=[{"y": y, "z": z} for y, z in o],
                holes=[[{"y": y, "z": z} for y, z in h] for h in hs],
                material_id=mid))
    return bodies


def composite_def(state, prop):
    """CrossSectionDef složeného PID (geometrie), nebo None, když PID nemá parts."""
    parts = getattr(prop, "composite_parts", None)
    if not parts:
        return None
    bodies = assemble_parts(state, parts)
    if not bodies:
        return None
    return CrossSectionDef(type="polygon", bodies=bodies)


# ── B1: modulem vážené charakteristiky (transformovaný průřez) ───────────────
@dataclass
class CompositeProps:
    EA: float        # Σ Eᵢ·Aᵢ  [N]
    EIy: float       # Σ Eᵢ·I_yi k neutrální ose [N·mm²]
    EIz: float
    EIyz: float
    y_NA: float      # modulem vážené těžiště / neutrální osa [mm]
    z_NA: float
    E_ref: float     # referenční modul pro „ekvivalentní" geometrii
    A_eq: float      # transformovaná plocha  = EA / E_ref
    Iy_eq: float     # transformovaný moment  = EIy / E_ref
    Iz_eq: float
    multi_material: bool
    GJ: float = None     # (GJ)_eff torzní tuhost přes variabilní-G FEM [N·mm²]


def _material_by_id(state, mid):
    for m in getattr(state, "materials", None) or []:
        if m.id == mid:
            return m
    return state.material() if hasattr(state, "material") else None


def _material_E(state, mid, default=210000.0):
    m = _material_by_id(state, mid)
    return float(m.E) if m else default


def _positioned_bodies(state, prop):
    """[( (outer, [holes]), material ), …] – části sestavy v cílové poloze
    (posun+úhel části) + CELKOVÉ natočení PID (prop.rotation), s jejich materiálem."""
    from .sections_along import section_by_id
    prot = getattr(prop, "rotation", 0.0) or 0.0
    out = []
    for part in prop.composite_parts or []:
        sec = section_by_id(state, part.get("section_id"))
        if sec is None:
            continue
        mat = _material_by_id(state, part.get("material_id"))
        dy, dz = float(part.get("dy", 0.0)), float(part.get("dz", 0.0))
        ang = float(part.get("angle", 0.0))
        for outer, holes in section_bodies_centroidal(sec):
            o = _rot_trans(outer, ang, dy, dz)
            hs = [_rot_trans(h, ang, dy, dz) for h in holes]
            if prot:
                o = _rot_trans(o, prot, 0.0, 0.0)
                hs = [_rot_trans(h, prot, 0.0, 0.0) for h in hs]
            out.append(((o, hs), mat))
    return out


def composite_weighted(state, prop):
    """Modulem vážené charakteristiky složeného PID: EA, neutrální osa,
    EIy/EIz k NA, a „ekvivalentní" transformovaná geometrie (A_eq=EA/E_ref…).
    Vrátí CompositeProps, nebo None. Pro jeden materiál se redukuje na E·geometrie."""
    from .section import _raw_moments
    pbodies = _positioned_bodies(state, prop)
    if not pbodies:
        return None
    bodies_E = [(g, float(m.E) if m else 210000.0) for g, m in pbodies]
    EM = [0.0] * 6                       # E-vážené momenty M00,M10,M01,M20,M02,M11
    Es = set()
    for (outer, holes), E in bodies_E:
        Es.add(round(E, 6))
        if outer and len(outer) >= 3:
            m = _raw_moments(outer)
            sg = 1.0 if m[0] >= 0 else -1.0
            for k in range(6):
                EM[k] += E * sg * m[k]
        for h in holes:
            if h and len(h) >= 3:
                hm = _raw_moments(h)
                sgh = 1.0 if hm[0] >= 0 else -1.0
                for k in range(6):
                    EM[k] -= E * sgh * hm[k]
    EA = EM[0]
    if EA <= 1e-9:
        return None
    y_NA, z_NA = EM[1] / EA, EM[2] / EA
    EIy = EM[4] - EA * z_NA**2           # Σ Eᵢ ∫z² dA k NA
    EIz = EM[3] - EA * y_NA**2
    EIyz = EM[5] - EA * y_NA * z_NA
    E_ref = max(E for _, E in bodies_E)
    return CompositeProps(EA, EIy, EIz, EIyz, y_NA, z_NA, E_ref,
                          EA / E_ref, EIy / E_ref, EIz / E_ref, len(Es) > 1)


def composite_stress(state, prop, N, M):
    """Normálové napětí a RF PER MATERIÁL složeného PID (ohyb + osová síla, B1).
    N [N], M [N·mm]. σ v tělese materiálu i: σ = Eᵢ·(N/EA + M·(z−z_NA)/EIy).
    Vrátí list dict {material, E, sigma_max, RF_yield, RF_ultimate} (per materiál,
    max přes jeho tělesa), nebo None. Jen normálové – slouží jako B1 fallback,
    plný von Mises (σ+τ_t+τ_V) počítá composite_fem.composite_stress_field."""
    w = composite_weighted(state, prop)
    if w is None:
        return None
    agg = {}   # material_id -> dict
    for (outer, holes), mat in _positioned_bodies(state, prop):
        if mat is None or not outer:
            continue
        zs = [z for _, z in outer]
        for z in (min(zs), max(zs)):
            sig = mat.E * (N / w.EA + M * (z - w.z_NA) / w.EIy)
            a = agg.setdefault(mat.id, {"material": mat.name, "E": mat.E,
                                        "Re": mat.Re, "Rm": mat.Rm, "sigma_max": 0.0})
            a["sigma_max"] = max(a["sigma_max"], abs(sig))
    rows = []
    for a in agg.values():
        s = a["sigma_max"]
        a["RF_yield"] = (a["Re"] / s) if s > 1e-9 else float("inf")
        a["RF_ultimate"] = (a["Rm"] / s) if s > 1e-9 else float("inf")
        rows.append(a)
    return rows


def section_by_id_(state, sid):
    from .sections_along import section_by_id
    return section_by_id(state, sid)


def composite_assess(state, prop, N, M, basis="min", Mk=0.0, V=0.0):
    """Posouzení složeného PID PER MATERIÁL. B2: plný von Mises přes FEM pole
    (σ modulem vážené + τ z variabilní-G torze ve stejném bodě). Když FEM pole
    selže, spadne zpět na B1 (jen normálové σ). Vrací dict kompatibilní s
    _assess: sigma_max/tau_max/mises_max/RF (řídicí) + 'materials'. None, když
    není vícemateriálový."""
    w = composite_weighted(state, prop)
    if w is None or not w.multi_material:
        return None

    rows = None
    try:
        from .composite_fem import composite_stress_field
        field = composite_stress_field(state, prop, N, M, Mk, V)
    except Exception:
        field = None
    if field and field.get("materials"):
        rows = []
        for a in field["materials"].values():
            mz = a["mises_max"]
            a["RF_yield"] = (a["Re"] / mz) if mz > 1e-9 else float("inf")
            a["RF_ultimate"] = (a["Rm"] / mz) if mz > 1e-9 else float("inf")
            rows.append(a)
    if rows is None:                          # B1 fallback (jen normálové)
        rows = composite_stress(state, prop, N, M)
        for a in rows or []:
            a.setdefault("tau_max", 0.0)
            a.setdefault("mises_max", a["sigma_max"])
    if not rows:
        return None

    sigma_max = max(r["sigma_max"] for r in rows)
    tau_max = max(r.get("tau_max", 0.0) for r in rows)
    mises_max = max(r.get("mises_max", r["sigma_max"]) for r in rows)
    rfy = min(r["RF_yield"] for r in rows)
    rfu = min(r["RF_ultimate"] for r in rows)
    if basis == "yield":
        rf, crit = rfy, "yield"
    elif basis == "ultimate":
        rf, crit = rfu, "ultimate"
    else:
        rf = min(rfy, rfu)
        crit = "yield" if rfy <= rfu else "ultimate"
    return {"materials": rows, "sigma_max": sigma_max, "tau_max": tau_max,
            "mises_max": mises_max, "RF_yield": rfy, "RF_ultimate": rfu,
            "RF": rf, "critical": crit, "composite": True}
