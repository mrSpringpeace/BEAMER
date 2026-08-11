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
    GJ: float | None = None     # (GJ)_eff torzní tuhost přes variabilní-G FEM [N·mm²]
    EIw: float | None = None    # ∫E·ω²dA Vlasovova warpingová tuhost [N·mm⁴]
    GA: float | None = None     # Σ Gᵢ·Aᵢ – pro váženou smykovou tuhost GAs [N]
    EAalpha: float = 0.0  # Σ Eᵢ·αᵢ·Aᵢ – teplotní osová tuhost (bimetal) [N/°C]
    ESalpha: float = 0.0  # Σ Eᵢ·αᵢ·(z−z_NA)dA – teplotní moment (bimetal) [N·mm/°C]
    EIalpha: float = 0.0  # Σ Eᵢ·αᵢ·(z−z_NA)²dA [N·mm²/°C]


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
    bodies_E = [(g, float(m.E) if m else 210000.0,
                 float(m.G) if m else 81000.0,
                 float(getattr(m, "alpha", 0.0)) if m else 0.0) for g, m in pbodies]
    EM = [0.0] * 6                       # E-vážené momenty M00,M10,M01,M20,M02,M11
    GA = 0.0                             # Σ Gᵢ·Aᵢ (vážená smyková tuhost)
    EAalpha = 0.0                        # Σ Eᵢ·αᵢ·Aᵢ (teplotní osová tuhost)
    ESalpha_z = 0.0                      # Σ Eᵢ·αᵢ·∫z dA (před posunem na NA)
    EIalpha_z = 0.0                      # Σ Eᵢ·αᵢ·∫z² dA (před posunem na NA)
    Es = set()
    for (outer, holes), E, G, al in bodies_E:
        Es.add(round(E, 6))
        if outer and len(outer) >= 3:
            m = _raw_moments(outer)
            sg = 1.0 if m[0] >= 0 else -1.0
            for k in range(6):
                EM[k] += E * sg * m[k]
            GA += G * sg * m[0]
            EAalpha += E * al * sg * m[0]
            ESalpha_z += E * al * sg * m[2]        # m[2] = ∫z dA
            EIalpha_z += E * al * sg * m[4]        # m[4] = ∫z² dA
        for h in holes:
            if h and len(h) >= 3:
                hm = _raw_moments(h)
                sgh = 1.0 if hm[0] >= 0 else -1.0
                for k in range(6):
                    EM[k] -= E * sgh * hm[k]
                GA -= G * sgh * hm[0]
                EAalpha -= E * al * sgh * hm[0]
                ESalpha_z -= E * al * sgh * hm[2]
                EIalpha_z -= E * al * sgh * hm[4]
    EA = EM[0]
    if EA <= 1e-9:
        return None
    y_NA, z_NA = EM[1] / EA, EM[2] / EA
    EIy = EM[4] - EA * z_NA**2           # Σ Eᵢ ∫z² dA k NA
    EIz = EM[3] - EA * y_NA**2
    EIyz = EM[5] - EA * y_NA * z_NA
    ESalpha = ESalpha_z - z_NA * EAalpha  # teplotní 1. moment k NA (bimetal)
    EIalpha = EIalpha_z - 2.0*z_NA*ESalpha_z + z_NA*z_NA*EAalpha
    E_ref = max(E for _, E, _g, _a in bodies_E)
    return CompositeProps(EA, EIy, EIz, EIyz, y_NA, z_NA, E_ref,
                          EA / E_ref, EIy / E_ref, EIz / E_ref, len(Es) > 1,
                          GA=GA, EAalpha=EAalpha, ESalpha=ESalpha,
                          EIalpha=EIalpha)


def composite_compression_capacity(state, prop):
    """Součet tlakových mezních sil částí Σ(Fcy,i·Ai).

    Když materiál nemá samostatnou tlakovou mez ``Fcy``, použije se jeho ``Re``
    a výsledek je explicitně založen na izotropním fallbacku.
    """
    from .section import _raw_moments
    capacity = 0.0
    for (outer, holes), mat in _positioned_bodies(state, prop):
        if mat is None or len(outer) < 3:
            continue
        area = abs(_raw_moments(outer)[0])
        for hole in holes:
            if len(hole) >= 3:
                area -= abs(_raw_moments(hole)[0])
        fcy = getattr(mat, "Fcy", None)
        if fcy is None or fcy <= 0.0:
            fcy = getattr(mat, "Re", 0.0)
        capacity += max(area, 0.0) * float(fcy)
    return capacity


def composite_stress(state, prop, N, M, Mz=0.0, dT=0.0, dT_grad=0.0):
    """Normálové napětí a RF PER MATERIÁL složeného PID (ohyb + osová síla, B1).
    N [N], M=My, Mz [N·mm]. σ v tělese materiálu i: σ = Eᵢ·(N/EA − ohyb), kde
    ohyb je pro Mz≠0 nebo nesymetrický řez (EIyz≠0) plný vzorec nesymetrického
    ohybu s modulem váženými tuhostmi; jinak uniaxiál M·(z−z_NA)/EIy. Vrátí list
    dict {material, E, sigma_max, RF_yield, RF_ultimate}, nebo None. Jen normálové
    – B1 fallback; plný von Mises počítá composite_fem.composite_stress_field."""
    w = composite_weighted(state, prop)
    if w is None:
        return None
    denom = w.EIy * w.EIz - w.EIyz * w.EIyz
    biax = (abs(Mz) > 1e-12 or abs(w.EIyz) > 1e-30) and abs(denom) > 1e-30
    positioned = _positioned_bodies(state, prop)
    all_z = [z for (outer, holes), _mat in positioned
             for ring in [outer, *holes] for _y, z in ring]
    z_mid = 0.5*(min(all_z) + max(all_z)) if all_z else w.z_NA
    h = (max(all_z) - min(all_z)) if all_z else 0.0
    grad = dT_grad/h if h > 1e-12 else 0.0
    nth = (dT*w.EAalpha
           + grad*(w.ESalpha + (w.z_NA-z_mid)*w.EAalpha))
    mth = (dT*w.ESalpha
           + grad*(w.EIalpha + (w.z_NA-z_mid)*w.ESalpha))
    th = abs(dT) > 1e-12 or abs(dT_grad) > 1e-12
    eps0 = nth / w.EA if abs(w.EA) > 1e-12 else 0.0
    kth = mth / w.EIy if abs(w.EIy) > 1e-30 else 0.0
    agg = {}   # material_id -> dict
    for (outer, holes), mat in positioned:
        if mat is None or not outer:
            continue
        ys = [y for y, _ in outer]; zs = [z for _, z in outer]
        if biax:                              # rohy bounding boxu tělesa
            corners = [(min(ys), min(zs)), (max(ys), min(zs)),
                       (min(ys), max(zs)), (max(ys), max(zs))]
        else:                                 # jen z-extrémy (uniaxiál)
            corners = [(0.0, min(zs)), (0.0, max(zs))]
        for (y, z) in corners:
            dz = z - w.z_NA
            if biax:
                dy = y - w.y_NA
                sig = mat.E * (N / w.EA - ((M*w.EIz - Mz*w.EIyz)*dz
                                           + (Mz*w.EIy - M*w.EIyz)*dy)/denom)
            else:
                sig = mat.E * (N / w.EA - M * dz / w.EIy)
            if th:
                a_i = float(getattr(mat, "alpha", 0.0) or 0.0)
                temperature = dT + grad*(z-z_mid)
                sig += mat.E * (eps0 + kth * dz - a_i * temperature)
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


def composite_assess(state, prop, N, M, basis="min", Mk=0.0, V=0.0, combine=None,
                     Mz=0.0, dT=0.0, Vy=0.0, dT_grad=0.0,
                     B=0.0, T_sv=None, T_w=0.0):
    """Posouzení složeného PID PER MATERIÁL. B2: plný von Mises přes FEM pole
    (σ v rozích elementů + τ_t z variabilní-G torze + τ_V E-vážený Žuravskij).
    Režim σ_red „combined" (state.sigma_red_mode) se aplikuje per materiál:
    σ_red = √(σ_max² + 3·τ_max²) ze špiček (konzervativní, pro čepy/šrouby).
    Když FEM pole selže, spadne zpět na B1 (jen normálové σ) a výsledek nese
    příznak 'b1_fallback' – UI na to upozorní; pod krutem/smykem by jinak τ
    tiše zmizelo. Vrací dict kompatibilní s _assess: sigma_max/tau_max/
    mises_max/RF (řídicí) + 'materials'. None, když není vícemateriálový."""
    w = composite_weighted(state, prop)
    if w is None or not w.multi_material:
        return None
    if combine is None:      # explicitní parametr má přednost (bez mutace state)
        combine = getattr(state, "sigma_red_mode", "exact") == "combined"

    rows = None
    fallback = False
    fallback_reason = ""
    try:
        from .composite_fem import composite_stress_field
        field = composite_stress_field(
            state, prop, N, M, Mk, V, Mz=Mz, dT=dT, Vy=Vy,
            dT_grad=dT_grad, B=B, T_sv=T_sv, T_w=T_w,
        )
    except Exception as exc:
        field = None
        fallback_reason = f"{type(exc).__name__}: {exc}"
    if field and field.get("materials"):
        rows = list(field["materials"].values())
    if rows is None:                          # B1 fallback (jen normálové)
        fallback = True
        rows = composite_stress(
            state, prop, N, M, Mz=Mz, dT=dT, dT_grad=dT_grad,
        )
        for a in rows or []:
            a.setdefault("tau_max", 0.0)
            a.setdefault("mises_max", a["sigma_max"])
    if not rows:
        return None

    import math
    for a in rows:
        if combine:                            # špičky sečtené (konzervativní)
            a["mises_max"] = math.sqrt(a["sigma_max"]**2 + 3.0*a["tau_max"]**2)
        mz = a["mises_max"]
        a["RF_yield"] = (a["Re"] / mz) if mz > 1e-9 else float("inf")
        a["RF_ultimate"] = (a["Rm"] / mz) if mz > 1e-9 else float("inf")

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
            "RF": rf, "critical": crit, "composite": True,
            "b1_fallback": fallback, "fallback_reason": fallback_reason,
            "sigma_red_combined": combine}
