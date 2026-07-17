"""Napjatostní vyhodnocení a posouzení MS na základě výsledků solveru.

Optimalizace: napětí je při konstantní geometrii LINEÁRNÍ funkcí vnitřních sil
(N, V, M, Mk). Geometrické vlivové koeficienty (z/Iy, Q/(Iy·b), t/IT) se proto
spočítají JEDNOU na z-grid (`StressInfluence`) a pak se jen škálují silami –
posouzení MS podél nosníku je tak ~1000× rychlejší než opakovaný scanline.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .section import CrossSection


def forces_from_beam(N, V, M, Mk, Vy=0.0, Mz=0.0):
    """Převede VVÚ nosníku na slovník sil pro CrossSection.stress.
    Síly v N, momenty v N·m (solver dává N·mm → /1e3)."""
    return {
        "Fx": N, "Fy": Vy, "Fz": V,
        "My": M/1e3, "Mz": Mz/1e3, "Mk": Mk/1e3,
    }


# ═══════════════════════════════════════════════════════════
#  VLIVOVÉ KOEFICIENTY (předpočítané geometrické pole)
# ═══════════════════════════════════════════════════════════

@dataclass
class StressInfluence:
    """Předpočítané geometrické koeficienty na z-gridu (jednotky SI).

    σ(z)   = N·c_sN + My·c_sM            [Pa]   (My v N·m)
    τ(z)   = Fz·c_tV + Mk·c_tT           [Pa]   (Mk v N·m)

    Biaxiál (fáze B): normálové napětí v rozích bounding boxu z plného vzorce
    nesymetrického ohybu (Iy, Iz, Iyz) – umožní zahrnout M_z.
    """
    z_mm: np.ndarray     # z-grid [mm od těžiště]
    c_sN: float          # 1/A_si          [1/m²]
    c_sM: np.ndarray     # z_si/Iy_si      [1/m³]
    c_tV: np.ndarray     # Q_si/(Iy_si·b_si)
    c_tT: np.ndarray     # t_si/IT_si
    # biaxiální data (SI: m, m⁴) – rohy bounding boxu a momenty setrvačnosti
    Iy_si: float = 0.0
    Iz_si: float = 0.0
    Iyz_si: float = 0.0
    corners: tuple = ()  # ((y,z), …) [m] – 4 rohy bounding boxu od těžiště
    y_mm: np.ndarray | None = None
    c_tVy: np.ndarray | None = None


def build_influence(section: CrossSection, n=60) -> StressInfluence:
    """Spočítá vlivové koeficienty pro daný průřez (jednou). Drahá scanline část."""
    A_si = section.A/1e6
    Iy_si = section.Iy/1e12

    z = np.linspace(section.z_bot*0.9999, section.z_top*0.9999, n)
    c_sM = np.zeros(n)
    c_tV = np.zeros(n)
    c_tT = np.zeros(n)
    for i, zi in enumerate(z):
        bz_mm = section.width_at(zi)
        if bz_mm < 1e-10:        # dutá zóna
            c_sM[i] = np.nan
            c_tV[i] = np.nan
            c_tT[i] = np.nan
            continue
        # sagging M>0 → tlak nahoře (+z): záporné znaménko (shodně s section.stress)
        c_sM[i] = -(zi/1e3)/Iy_si if Iy_si > 1e-30 else 0.0
        Q_si = section.Q_at(zi)/1e9
        b_si = bz_mm/1e3
        c_tV[i] = Q_si/(Iy_si*b_si) if (Iy_si > 1e-30 and b_si > 1e-15) else 0.0
        # τ_t dle torzního modelu průřezu (open/Bredt/kruh/…) – sdílené se stress()
        c_tT[i] = section._tau_t_coeff(zi)
    c_sN = 1.0/A_si if A_si > 1e-30 else 0.0
    # biaxiální data: skutečné hraniční body (od těžiště) v metrech + Iz, Iyz.
    # Body obrysu (_pts_c) → přesné krajní vlákno i pro natočený/nepravoúhlý řez;
    # kruh/trubka perimetr; jinak fallback rohy bounding boxu.
    Iz_si = section.Iz/1e12
    Iyz_si = getattr(section, "Iyz", 0.0)/1e12
    bpts = getattr(section, "_pts_c", None)
    if bpts:
        corners = tuple((y/1e3, zc/1e3) for y, zc in bpts)
    elif getattr(section, "_circle_r_out", 0.0):
        r = section._circle_r_out/1e3
        corners = tuple((r*math.cos(t), r*math.sin(t))
                        for t in np.linspace(0, 2*math.pi, 24, endpoint=False))
    else:
        zt, zb = section.z_top/1e3, section.z_bot/1e3
        yl, yr = getattr(section, "y_left", 0.0)/1e3, getattr(section, "y_right", 0.0)/1e3
        corners = ((yl, zt), (yr, zt), (yl, zb), (yr, zb))
    # Vodorovný smyk Vy: analogický scan po šířce průřezu. Dříve se V_y v RF
    # zcela ignoroval, přestože jej 6-DOF solver počítá.
    y = np.linspace(section.y_left*0.9999, section.y_right*0.9999, n)
    c_tVy = np.zeros(n)
    for i, yi in enumerate(y):
        h_mm = section.height_at_y(yi)
        if h_mm < 1e-10:
            c_tVy[i] = np.nan
            continue
        Qy_si = section.Q_Vy_at_y(yi)/1e9
        h_si = h_mm/1e3
        c_tVy[i] = Qy_si/(Iz_si*h_si) if (Iz_si > 1e-30 and h_si > 1e-15) else 0.0
    return StressInfluence(z, c_sN, c_sM, c_tV, c_tT,
                           Iy_si=Iy_si, Iz_si=Iz_si, Iyz_si=Iyz_si, corners=corners,
                           y_mm=y, c_tVy=c_tVy)


def max_stresses_fast(infl: StressInfluence, N, V, M, Mk, Mz=0.0, combine=False,
                      Vy=0.0):
    """Max |σ|, |τ|, σ_red [MPa] z předpočítaných koeficientů. Vektorizováno.

    combine=False → σ_red = skutečné maximum von Mises po řezu (špička σ a špička
    τ jsou obecně v RŮZNÝCH bodech, proto σ_red může = max(|σ|), když ohyb vyhrává).
    combine=True  → konzervativní σ_red = √(σ_max²+3·τ_max²) (špičky sečteny na
    povrchu; vhodné pro čepy/šrouby, kde nosníková teorie τ=0 na okraji je sporná).

    `Mz` (N·mm, ohyb kolem z) → biaxiál: normálové napětí se vyhodnotí i v rozích
    bounding boxu plným vzorcem nesymetrického ohybu (Iy, Iz, Iyz). Pro Mz=0 a
    Iyz=0 (symetrický řez) se biaxiální větev přeskočí → identické s uniaxiálem.
    """
    My = M/1e3      # N·mm → N·m
    Mz_nm = Mz/1e3
    Mk_nm = Mk/1e3
    sigma = N*infl.c_sN + My*infl.c_sM            # Pa (z-scan po ose, jen My)
    # Smyk od V a torze je v prostoru vektorové pole. Jednorozměrný scan nemá
    # informaci o straně průřezu, na které se složky sčítají; algebraický součet
    # proto při změně znaménka Mk vedl k nefyzikálnímu rušení. Použijeme bezpečnou
    # horní mez součtem lokálních velikostí. Pro Vy přidáme maximum druhého scanu.
    tau_z = np.abs(V*infl.c_tV) + np.abs(Mk_nm*infl.c_tT)
    tau_y_peak = 0.0
    if infl.c_tVy is not None and abs(Vy) > 0.0:
        tau_y_peak = _maxabs_raw(Vy*infl.c_tVy)
    tau = tau_z

    def _maxabs(a):
        a = a[~np.isnan(a)]
        return float(np.max(np.abs(a)))/1e6 if a.size else 0.0
    sg = _maxabs(sigma)
    tu_z = _maxabs(tau)
    tu = tu_z + tau_y_peak/1e6

    # biaxiální normálové napětí v rozích (M_z a/nebo Iyz) – jinak přeskoč
    if infl.corners and (abs(Mz_nm) > 1e-12 or abs(infl.Iyz_si) > 1e-40):
        Iy, Iz, Iyz = infl.Iy_si, infl.Iz_si, infl.Iyz_si
        denom = Iy*Iz - Iyz*Iyz
        if denom > 1e-40:
            cN = N*infl.c_sN
            sb = 0.0
            for yc, zc in infl.corners:
                s = cN - ((My*Iz - Mz_nm*Iyz)*zc + (Mz_nm*Iy - My*Iyz)*yc)/denom
                sb = max(sb, abs(s))
            sg = max(sg, sb/1e6)
            # von Mises v rohu: τ_V≈0 na krajním vlákně, zůstává torzní τ_t
            tt = abs(Mk_nm) * _maxabs_raw(infl.c_tT)      # Pa
            mz_corner = math.sqrt((sg*1e6)**2 + 3*tt**2)/1e6
        else:
            mz_corner = 0.0
    else:
        mz_corner = 0.0

    if combine:
        mz = math.sqrt(sg**2 + 3*tu**2)
    else:
        mz = max(_maxabs(np.sqrt(sigma**2 + 3*tau**2)), mz_corner)
        if tau_y_peak > 0.0:
            # Bez plného 2D pole nelze bezpečně určit společné místo špiček obou
            # smykových rovin. Konzervativně použijeme jejich horní mez.
            mz = max(mz, math.sqrt(sg**2 + 3*tu**2))
    return sg, tu, mz


def _maxabs_raw(a):
    a = np.asarray(a)
    a = a[~np.isnan(a)]
    return float(np.max(np.abs(a))) if a.size else 0.0


def peak_locations(infl: StressInfluence, N, V, M, Mk):
    """Poloha (z [mm] od těžiště) maxima |σ| a maxima |τ| v řezu – pro popisky,
    aby bylo zřejmé, že obě špičky obecně vznikají v různých vláknech."""
    My = M/1e3
    Mk_nm = Mk/1e3
    sigma = N*infl.c_sN + My*infl.c_sM
    tau = V*infl.c_tV + Mk_nm*infl.c_tT
    z = np.asarray(infl.z_mm)

    def _argabs(a):
        a = np.where(np.isnan(a), 0.0, np.abs(a))
        if a.size == 0 or not np.any(a):
            return 0.0
        return float(z[int(np.argmax(a))])
    return _argabs(sigma), _argabs(tau)


# ═══════════════════════════════════════════════════════════
#  DETAILNÍ PROFIL (pro diagram v jednom místě)
# ═══════════════════════════════════════════════════════════

@dataclass
class StressProfile:
    z: list
    sigma: list
    tau: list
    mises: list


def stress_profile(section: CrossSection, N, V, M, Mk, n=160, Mz=0.0,
                   Vy=0.0) -> StressProfile:
    """Detailní průběh napětí po výšce (pro diagram). Výstup MPa.
    Používá rychlé vlivové koeficienty (vektorizováno)."""
    infl = build_influence(section, n=n)
    My = M/1e3
    Mk_nm = Mk/1e3
    sigma_pa = N*infl.c_sN + My*infl.c_sM
    if abs(Mz) > 1e-12 or abs(infl.Iyz_si) > 1e-40:
        from .section import _scan_intersections
        denom = infl.Iy_si*infl.Iz_si - infl.Iyz_si**2
        if denom > 1e-40:
            for i, z_mm in enumerate(infl.z_mm):
                if getattr(section, "bodies_c", None):
                    ys = []
                    for outer, holes in section.bodies_c:
                        ys.extend(_scan_intersections(outer, z_mm))
                        for hole in holes:
                            ys.extend(_scan_intersections(hole, z_mm))
                elif getattr(section, "_pts_c", None):
                    ys = _scan_intersections(section._pts_c, z_mm)
                elif getattr(section, "_circle_r_out", 0.0):
                    dy = math.sqrt(max(section._circle_r_out**2-z_mm**2, 0.0))
                    ys = [-dy, dy]
                else:
                    ys = [section.y_left, section.y_right]
                candidates = []
                for y_mm in ys:
                    y, z = y_mm/1e3, z_mm/1e3
                    candidates.append(
                        N*infl.c_sN
                        - ((My*infl.Iz_si-(Mz/1e3)*infl.Iyz_si)*z
                           + ((Mz/1e3)*infl.Iy_si-My*infl.Iyz_si)*y)/denom
                    )
                if candidates:
                    sigma_pa[i] = max(candidates, key=abs)
    tau_pa = np.abs(V*infl.c_tV) + np.abs(Mk_nm*infl.c_tT)
    if infl.c_tVy is not None and abs(Vy) > 0.0:
        tau_pa += _maxabs_raw(Vy*infl.c_tVy)
    sigma = sigma_pa/1e6
    tau = tau_pa/1e6
    mises = np.sqrt((sigma)**2 + 3*(tau)**2)
    return StressProfile(list(infl.z_mm), list(sigma), list(tau), list(mises))


def max_stresses(section: CrossSection, N, V, M, Mk, n=60):
    """Maximální |σ|, |τ|, σ_red v průřezu (MPa). Kompat. wrapper."""
    infl = build_influence(section, n=n)
    return max_stresses_fast(infl, N, V, M, Mk)


# ═══════════════════════════════════════════════════════════
#  POSOUZENÍ MS PODÉL NOSNÍKU
# ═══════════════════════════════════════════════════════════

@dataclass
class ReserveResult:
    x: float
    sigma_max: float
    tau_max: float
    mises_max: float
    RF_yield: float        # Re / σ_red
    RF_ultimate: float     # Rm / σ_red
    RF: float              # min(RF_yield, RF_ultimate); ≥ 1 = vyhovuje
    critical: str


def _principal_inertia_min(section):
    """Menší hlavní moment setrvačnosti včetně Iyz vazby."""
    i1 = float(getattr(section, "I1", 0.0) or 0.0)
    i2 = float(getattr(section, "I2", 0.0) or 0.0)
    if i1 > 0.0 and i2 > 0.0:
        return min(i1, i2)
    iy = float(getattr(section, "Iy", 0.0) or 0.0)
    iz = float(getattr(section, "Iz", 0.0) or 0.0)
    iyz = float(getattr(section, "Iyz", 0.0) or 0.0)
    return 0.5 * (iy + iz) - math.sqrt((0.5 * (iy - iz))**2 + iyz**2)


def _principal_value_min(yy, zz, yz):
    return 0.5*(yy + zz) - math.sqrt((0.5*(yy-zz))**2 + yz**2)


def _stability_properties(state, seg, x, section, material):
    """Homogenní ekvivalent pro Johnson/Euler, se zachováním kompozitního EI."""
    if not getattr(section, "stability_available", True):
        return None
    from .sections_along import property_by_id
    prop = property_by_id(state, getattr(seg, "property_id", None))
    if prop is not None and getattr(prop, "composite_parts", None):
        from .composite import composite_compression_capacity, composite_weighted
        weighted = composite_weighted(state, prop)
        if weighted is None or weighted.E_ref <= 0.0 or weighted.A_eq <= 0.0:
            return None
        ei_min = _principal_value_min(
            weighted.EIy, weighted.EIz, weighted.EIyz,
        )
        if ei_min <= 0.0:
            return None
        area = weighted.A_eq
        inertia = ei_min / weighted.E_ref
        squash = composite_compression_capacity(state, prop)
        fcy = squash / area if squash > 0.0 else 0.0
        return area, inertia, weighted.E_ref, fcy, ei_min, prop
    area = float(getattr(section, "A", 0.0) or 0.0)
    inertia = _principal_inertia_min(section)
    e_mod = getattr(seg, "E", None) or getattr(material, "E", 0.0)
    fcy = getattr(material, "Fcy", None)
    if fcy is None or fcy <= 0.0:
        fcy = getattr(material, "Re", 0.0)
    return area, inertia, float(e_mod), float(fcy), float(e_mod)*inertia, None


def _plastic_capacity_factor(alpha, enabled, N, V, M, Mk, Mz=0.0, Vy=0.0):
    """Tvarový součinitel platí pouze pro čistý ohyb kolem své definované osy.

    Pro kombinaci s osovou silou, smykem, torzí či biaxiálním ohybem nelze
    násobit celé von Misesovo napětí hodnotou Wpl/Wel. Dokud není implementována
    plná plastická interakce, je bezpečná hodnota 1.0.
    """
    if not enabled or alpha <= 1.0 or abs(M) <= 1e-12:
        return 1.0
    other = max(abs(N), abs(V), abs(Mk), abs(Mz), abs(Vy))
    scale = max(abs(M), 1.0)
    return alpha if other <= 1e-10 * scale else 1.0


def _thermal_at(state, x):
    """Efektivní (rovnoměrné ΔT, gradient ΔT) v poloze x."""
    from .solver import _load_multiplier
    v = vg = 0.0
    for ld in getattr(state, "loads", None) or []:
        if getattr(ld, "type", None) != "thermal":
            continue
        if ld.x1 - 1e-9 <= x <= ld.x2 + 1e-9:
            v += float(getattr(ld, "dT", 0.0) or 0.0) * _load_multiplier(state, ld)
            vg += float(getattr(ld, "dT_grad", 0.0) or 0.0) * _load_multiplier(state, ld)
    return v, vg


def _thermal_dT_at(state, x):
    """Kompatibilní wrapper vracející pouze rovnoměrnou složku."""
    return _thermal_at(state, x)[0]


def reserves_along_beam(result, state, n_stations=120, progress=None):
    """Posouzení RF (reserve factor) podél nosníku – zatížení = početní (ultimate).
    RF_yield = Re/σ_red, RF_ultimate = Rm/σ_red. `progress(frac)` callback 0..1.
    Vlivové koeficienty se počítají jednou → rychlé i pro stovky stanic."""
    section = result.section
    if section is None or not result.points:
        return []
    basis = getattr(state, "rf_basis", "min")
    combine = getattr(state, "sigma_red_mode", "exact") == "combined"
    plast = getattr(state, "plasticity_enabled", False)
    g_mat = state.material()
    resolver = getattr(result, "resolver", None)

    def mat_at(x):
        if resolver is not None:
            return resolver.material_at(x)
        return g_mat

    # tvarový součinitel plasticity – zohlední se jen v RF_ultimate
    from .section import ALPHA_PL_TABLE
    method = getattr(state, "plasticity_method", "analytic")

    def alpha_pl_for(cs):
        if not plast:
            return 1.0
        if method == "tabular":
            return ALPHA_PL_TABLE.get(getattr(cs, "section_type", None),
                                      getattr(cs, "alpha_pl", 1.0))
        return getattr(cs, "alpha_pl", 1.0)

    pts = result.points
    xs = np.array([p.x for p in pts])

    # Vlivové koeficienty: pro jeden/prizmatické průřezy se postaví jen pro
    # několik unikátních průřezů; pro tapered na omezené reprezentativní mřížce
    # (margins-scan nepotřebuje řez v každém bodě). build_influence je drahé.
    if resolver is None:
        base_infl = (build_influence(section, n=60)
                     if getattr(section, "strength_available", True) else None)
        base_alpha = alpha_pl_for(section)
        def data_at(x):
            return base_infl, base_alpha, g_mat.Re, g_mat.Rm
    else:
        # Vlivové koeficienty pro průřez SKUTEČNĚ v poloze x, cache dle identity
        # průřezu. resolver.at vrací u prizmatického úseku stejný objekt (→ jen
        # pár buildů), u tapered kvantizuje t (→ omezená množina). DŘÍVE se
        # snapovalo na nejbližší bod globální mřížky 24 bodů, což u hranice úseků
        # přiřadilo VEDLEJŠÍ (jiný) průřez → špatné napětí/RF (reserves scan
        # křížil hranici úseku). Teď se nikdy nekříží hranice.
        seen = {}

        def data_at(x):
            cs = resolver.at(x)
            mat = resolver.material_at(x)
            key = (id(cs), id(mat))
            if key not in seen:
                infl = (build_influence(cs, n=50)
                        if getattr(cs, "strength_available", True) else None)
                seen[key] = (infl, alpha_pl_for(cs), mat.Re, mat.Rm)
            return seen[key]

    if progress:
        progress(0.5)

    from .sections_along import segment_at, property_by_id
    out = []
    for i in range(n_stations):
        xq = xs[0] + (xs[-1]-xs[0])*i/(n_stations-1)
        idx = int(np.argmin(np.abs(xs - xq)))
        p = pts[idx]
        # složený PID z různých materiálů → RF per materiál (min)
        seg = segment_at(state, p.x)
        pr = property_by_id(state, getattr(seg, "property_id", None))
        if pr is not None and getattr(pr, "composite_parts", None):
            from .composite import composite_assess
            dtemp, dtemp_grad = _thermal_at(state, p.x)
            ca = composite_assess(state, pr, p.N, p.M, basis, Mk=p.Mk, V=p.V,
                                  Vy=getattr(p, "V_y", 0.0),
                                  Mz=getattr(p, "M_z", 0.0),
                                  dT=dtemp, dT_grad=dtemp_grad)
            if ca is not None:
                out.append(ReserveResult(p.x, ca["sigma_max"], ca["tau_max"], ca["mises_max"],
                                         ca["RF_yield"], ca["RF_ultimate"], ca["RF"],
                                         ca["critical"]))
                continue
        infl, alpha, Re, Rm = data_at(p.x)
        if infl is None:
            continue
        vy = getattr(p, "V_y", 0.0)
        mz_b = getattr(p, "M_z", 0.0)
        sg, tu, mz = max_stresses_fast(infl, p.N, p.V, p.M, p.Mk,
                                       Mz=mz_b, combine=combine, Vy=vy)
        RF_y = (Re/mz) if mz > 1e-9 else float("inf")
        # plastická rezerva (α_pl·M_pl) se uplatní jen v ultimate
        alpha_eff = _plastic_capacity_factor(
            alpha, plast, p.N, p.V, p.M, p.Mk, Mz=mz_b, Vy=vy
        )
        RF_u = (alpha_eff*Rm/mz) if mz > 1e-9 else float("inf")
        if basis == "yield":
            RF, crit = RF_y, "yield"
        elif basis == "ultimate":
            RF, crit = RF_u, "ultimate"
        else:
            RF = min(RF_y, RF_u)
            crit = "yield" if RF_y <= RF_u else "ultimate"
        out.append(ReserveResult(p.x, sg, tu, mz, RF_y, RF_u, RF, crit))
        if progress and i % 10 == 0:
            progress(0.5 + 0.5*i/n_stations)
    if progress:
        progress(1.0)
    return out


def _assess(section, mat, state, N, V, M, Mk, seg=None, Mz=0.0, dT=0.0,
            Vy=0.0, dT_grad=0.0):
    """Napětí (σ/τ/σ_red) a rezervní faktory pro daný průřez+materiál a VVÚ.
    Vrací dílčí dict (bez x/VVÚ). Pro složený PID z různých materiálů (seg s
    property_id) vrátí per-materiálové posouzení (normálové, B1). `Mz` = ohyb
    kolem osy z (biaxiál)."""
    if seg is not None:
        pid = getattr(seg, "property_id", None)
        if pid:
            from .sections_along import property_by_id
            p = property_by_id(state, pid)
            if p is not None and getattr(p, "composite_parts", None):
                from .composite import composite_assess
                ca = composite_assess(state, p, N, M, getattr(state, "rf_basis", "min"),
                                      Mk=Mk, V=V, Vy=Vy, Mz=Mz, dT=dT,
                                      dT_grad=dT_grad)
                if ca is not None:
                    ca.update({"section": section, "material": mat, "alpha_pl": 1.0,
                               "sigma_z": None, "tau_z": None})
                    return ca
    if section is not None and not getattr(section, "strength_available", True):
        return {
            "section": section, "material": mat,
            "assessment_available": False,
            "assessment_note": getattr(
                section, "analysis_note", "Napětí a RF nejsou pro tento průřez dostupné.",
            ),
            "sigma_max": None, "tau_max": None, "mises_max": None,
            "sigma_z": None, "tau_z": None,
            "RF_yield": None, "RF_ultimate": None, "RF": None,
            "critical": "unavailable", "alpha_pl": 1.0,
        }
    sg = tu = mz = 0.0
    z_sg = z_tu = 0.0
    combine = getattr(state, "sigma_red_mode", "exact") == "combined"
    if section is not None and getattr(section, "valid", False):
        infl = build_influence(section, n=80)
        sg, tu, mz = max_stresses_fast(
            infl, N, V, M, Mk, Mz=Mz, combine=combine, Vy=Vy
        )
        z_sg, z_tu = peak_locations(infl, N, V, M, Mk)

    from .section import ALPHA_PL_TABLE
    alpha = 1.0
    if getattr(state, "plasticity_enabled", False) and section is not None:
        if getattr(state, "plasticity_method", "analytic") == "tabular":
            alpha = ALPHA_PL_TABLE.get(getattr(section, "section_type", None),
                                       getattr(section, "alpha_pl", 1.0))
        else:
            alpha = getattr(section, "alpha_pl", 1.0)

    Re = getattr(mat, "Re", 0.0); Rm = getattr(mat, "Rm", 0.0)
    RF_y = (Re / mz) if mz > 1e-9 else float("inf")
    alpha_eff = _plastic_capacity_factor(
        alpha, getattr(state, "plasticity_enabled", False),
        N, V, M, Mk, Mz=Mz, Vy=Vy,
    )
    RF_u = (alpha_eff * Rm / mz) if mz > 1e-9 else float("inf")
    basis = getattr(state, "rf_basis", "min")
    if basis == "yield":
        RF, crit = RF_y, "yield"
    elif basis == "ultimate":
        RF, crit = RF_u, "ultimate"
    else:
        RF = min(RF_y, RF_u)
        crit = "yield" if RF_y <= RF_u else "ultimate"
    return {
        "section": section, "material": mat,
        "sigma_max": sg, "tau_max": tu, "mises_max": mz,
        "sigma_z": z_sg, "tau_z": z_tu, "sigma_red_combined": combine,
        "RF_yield": RF_y, "RF_ultimate": RF_u, "RF": RF,
        "critical": crit, "alpha_pl": alpha,
    }


def _interp_forces(result, x):
    """(x_clamp, N, V, M, Mk, w, phi, theta) lineárně interpolované v poloze x."""
    pts = result.points
    xs = [p.x for p in pts]
    x = max(xs[0], min(xs[-1], float(x)))

    def interp(attr):
        return float(np.interp(x, xs, [getattr(p, attr) for p in pts]))

    return (x, interp("N"), interp("V"), interp("M"), interp("Mk"),
            interp("w"), interp("phi"), interp("theta"))


def values_at_x(result, state, x):
    """Kompletní hodnoty v libovolném řezu x: VVÚ (lineárně interpolované),
    průřez a materiál v řezu, napětí (σ/τ/σ_red) a rezervní faktory.
    Vrací dict, nebo None pokud výsledek není stabilní."""
    if result is None or not getattr(result, "is_stable", False) or not result.points:
        return None
    x, N, V, M, Mk, w, phi, theta = _interp_forces(result, x)
    resolver = getattr(result, "resolver", None)
    from .sections_along import segment_at
    seg = segment_at(state, x)
    if resolver is not None:
        section = resolver.at(x)
        mat = resolver.material_at(x)
    else:
        section = result.section
        mat = state.material()
    Mz = float(np.interp(x, [p.x for p in result.points],
                         [getattr(p, "M_z", 0.0) for p in result.points]))
    Vy = float(np.interp(x, [p.x for p in result.points],
                         [getattr(p, "V_y", 0.0) for p in result.points]))
    v_y = float(np.interp(x, [p.x for p in result.points],
                          [getattr(p, "v", 0.0) for p in result.points]))
    phi_z = float(np.interp(x, [p.x for p in result.points],
                            [getattr(p, "phi_z", 0.0) for p in result.points]))
    d = {"x": x, "N": N, "V": V, "V_y": Vy, "M": M, "M_z": Mz,
         "Mk": Mk, "w": w, "v": v_y, "phi": phi, "phi_z": phi_z,
         "theta": theta}
    dtemp, dtemp_grad = _thermal_at(state, x)
    d.update(_assess(section, mat, state, N, V, M, Mk, seg=seg, Mz=Mz,
                     dT=dtemp, dT_grad=dtemp_grad, Vy=Vy))
    return d


def values_at_x_multi(result, state, x, tol=1e-3):
    """Jako values_at_x, ale na rozhraní dvou úseků vrátí výsledky z OBOU
    (stejné VVÚ, různý průřez/materiál → různé napětí a RF). Vrací list dictů;
    každý navíc obsahuje 'seg_index' a 'seg_side' ("" | "vlevo" | "vpravo")."""
    if result is None or not getattr(result, "is_stable", False) or not result.points:
        return []
    from .sections_along import (segments_at, def_for_segment,
                                 material_for_segment, normalized_segments)
    from .section import build_section
    x, N, V, M, Mk, w, phi, theta = _interp_forces(result, x)
    Mz = float(np.interp(x, [p.x for p in result.points],
                         [getattr(p, "M_z", 0.0) for p in result.points]))
    Vy = float(np.interp(x, [p.x for p in result.points],
                         [getattr(p, "V_y", 0.0) for p in result.points]))
    v_y = float(np.interp(x, [p.x for p in result.points],
                          [getattr(p, "v", 0.0) for p in result.points]))
    phi_z = float(np.interp(x, [p.x for p in result.points],
                            [getattr(p, "phi_z", 0.0) for p in result.points]))
    base = {"x": x, "N": N, "V": V, "V_y": Vy, "M": M, "M_z": Mz,
            "Mk": Mk, "w": w, "v": v_y, "phi": phi, "phi_z": phi_z,
            "theta": theta}

    all_segs = normalized_segments(state)
    segs = segments_at(state, x, tol)
    out = []
    for seg in segs:
        try:
            section = build_section(def_for_segment(state, seg, x))
        except Exception:
            section = None
        mat = material_for_segment(state, seg)
        d = dict(base)
        dtemp, dtemp_grad = _thermal_at(state, x)
        d.update(_assess(section, mat, state, N, V, M, Mk, seg=seg, Mz=Mz,
                         dT=dtemp, dT_grad=dtemp_grad, Vy=Vy))
        try:
            d["seg_index"] = all_segs.index(seg)
        except ValueError:
            d["seg_index"] = 0
        d["seg_side"] = ""
        out.append(d)
    if len(out) == 2:                       # rozhraní: označ vlevo/vpravo dle x1
        order = sorted(range(2), key=lambda k: segs[k].x1)
        out[order[0]]["seg_side"] = "vlevo"
        out[order[1]]["seg_side"] = "vpravo"
    return out


@dataclass
class EnvelopeResult:
    """Obálka přes VŠECHNY kombinace. VVÚ = min/max v každé poloze; RF = minimum
    (nejnepříznivější) v každé stanici + řídicí kombinace. Diskretizace je stejná
    napříč kombinacemi (uzly závisí na polohách zatížení/podpor/úseků, ne na
    faktorech), přesto se hodnoty pro robustnost interpolují na společnou mřížku."""
    xv: list                       # x pro VVÚ [mm]
    N_min: list; N_max: list
    V_min: list; V_max: list
    M_min: list; M_max: list
    Mk_min: list; Mk_max: list
    w_min: list; w_max: list
    xs: list                       # x pro RF (stanice) [mm]
    rf_min: list                   # min RF přes kombinace v každé stanici
    rf_gov: list                   # název řídicí (nejnižší RF) kombinace / stanice
    sred_max: list                 # max σ_red přes kombinace / stanice
    crit_rf: float                 # celkové minimum RF
    crit_x: float
    crit_combo: str
    n_combos: int                  # počet stabilně spočtených kombinací


def envelope_over_combinations(state, n_stations=120, progress=None):
    """Spočte obálku VVÚ a RF přes všechny definované kombinace. Vrací
    EnvelopeResult, nebo None (žádné kombinace / žádná stabilní). `progress`
    callback 0..1."""
    from .solver import solve_beam
    combos = getattr(state, "load_combinations", None) or []
    if not combos:
        return None

    xv = None
    Nmn = Nmx = Vmn = Vmx = Mmn = Mmx = Kmn = Kmx = wmn = wmx = None
    xs = None
    rf_min = None
    rf_gov = None
    sred_max = None
    n_ok = 0
    for ci, comb in enumerate(combos):
        res = solve_beam(state, factors=comb.factors)
        if not res.is_stable or not res.points:
            continue
        n_ok += 1
        xc = np.array([p.x for p in res.points])

        def col(attr):
            return np.array([getattr(p, attr) for p in res.points])

        if xv is None:
            xv = xc
            Nmn = col("N").copy(); Nmx = Nmn.copy()
            Vmn = col("V").copy(); Vmx = Vmn.copy()
            Mmn = col("M").copy(); Mmx = Mmn.copy()
            Kmn = col("Mk").copy(); Kmx = Kmn.copy()
            wmn = col("w").copy(); wmx = wmn.copy()
        else:
            def env(mn, mx, attr):
                y = np.interp(xv, xc, col(attr)) if len(xc) != len(xv) \
                    or not np.allclose(xc, xv) else col(attr)
                return np.minimum(mn, y), np.maximum(mx, y)
            Nmn, Nmx = env(Nmn, Nmx, "N")
            Vmn, Vmx = env(Vmn, Vmx, "V")
            Mmn, Mmx = env(Mmn, Mmx, "M")
            Kmn, Kmx = env(Kmn, Kmx, "Mk")
            wmn, wmx = env(wmn, wmx, "w")

        rsv = reserves_along_beam(res, state, n_stations)
        if rsv:
            rx = np.array([r.x for r in rsv])
            rrf = np.array([r.RF for r in rsv])
            rsr = np.array([r.mises_max for r in rsv])
            if xs is None:
                xs = rx
                rf_min = rrf.copy()
                rf_gov = [comb.name] * len(rx)
                sred_max = rsr.copy()
            else:
                if len(rx) != len(xs) or not np.allclose(rx, xs):
                    rrf = np.interp(xs, rx, rrf)
                    rsr = np.interp(xs, rx, rsr)
                for i in range(len(xs)):
                    if rrf[i] < rf_min[i]:
                        rf_min[i] = rrf[i]
                        rf_gov[i] = comb.name
                    if rsr[i] > sred_max[i]:
                        sred_max[i] = rsr[i]
        if progress:
            progress((ci + 1) / len(combos))

    if xv is None or xs is None:
        return None
    ci = int(np.argmin(rf_min))
    return EnvelopeResult(
        list(xv), list(Nmn), list(Nmx), list(Vmn), list(Vmx),
        list(Mmn), list(Mmx), list(Kmn), list(Kmx), list(wmn), list(wmx),
        list(xs), list(rf_min), list(rf_gov), list(sred_max),
        float(rf_min[ci]), float(xs[ci]), rf_gov[ci], n_ok)


@dataclass
class ConservativeResult:
    """Konzervativní obálková kontrola (styl ruční analýzy): maxima vnitřních sil
    přes CELÝ nosník a všechny kombinace se dosadí na každý průřez, jako by
    působila naráz v jednom řezu. σ_red = √(σ_max²+3·τ_max²) ze špiček (σ=N/A+M/W,
    τ=V·Q/(Iy·b)+Mk·t/IT). RF_konz = min přes průřezy. Vždy horní odhad vůči
    přesnému řezovému RF."""
    N_max: float; V_max: float; M_max: float; Mk_max: float
    rows: list                    # [{seg, label, material, sigma, tau, sred, RF}]
    rf_min: float
    crit_label: str
    crit_material: str
    n_combos: int


def conservative_check(state, basis=None, env=None):
    """Konzervativní obálková kontrola. `basis` (min/yield/ultimate) jinak
    state.rf_basis. `env` = předpočítaná obálka (envelope_over_combinations) –
    předávat, kde už existuje; jinak se spočítá (n_kombinací × solve+reserves,
    DRAHÉ – nevolat v horké cestě). Vrací ConservativeResult, nebo None."""
    if env is None:
        env = envelope_over_combinations(state)
    if env is None:
        return None
    def _amax(lo, hi):
        return max(max(abs(v) for v in lo), max(abs(v) for v in hi))
    N_max = _amax(env.N_min, env.N_max)
    V_max = _amax(env.V_min, env.V_max)
    M_max = _amax(env.M_min, env.M_max)
    Mk_max = _amax(env.Mk_min, env.Mk_max)

    from .sections_along import (normalized_segments, def_for_segment,
                                 material_for_segment, property_by_id)
    from .section import build_section
    basis = basis or getattr(state, "rf_basis", "min")
    inf = float("inf")
    rows = []
    for i, seg in enumerate(normalized_segments(state)):
        xm = (seg.x1 + seg.x2) / 2.0
        mat = material_for_segment(state, seg)
        Re = getattr(mat, "Re", 0.0); Rm = getattr(mat, "Rm", 0.0)
        pid = getattr(seg, "property_id", None)
        p = property_by_id(state, pid)
        # složený PID → per-materiálové posouzení (konzervativně kombinované;
        # combine=True parametrem, bez mutace state – bezpečné vůči workeru)
        if p is not None and getattr(p, "composite_parts", None):
            from .composite import composite_assess
            ca = composite_assess(state, p, N_max, M_max, basis,
                                  Mk=Mk_max, V=V_max, combine=True)
            if ca:
                rows.append({"seg": i, "label": f"{tr_('Úsek')} {i+1} (kompozit)",
                             "material": "—", "sigma": ca["sigma_max"],
                             "tau": ca["tau_max"], "sred": ca["mises_max"],
                             "RF": ca["RF"]})
            continue
        try:
            section = build_section(def_for_segment(state, seg, xm))
        except Exception:
            continue
        if section is None or not getattr(section, "valid", False):
            continue
        infl = build_influence(section, n=80)
        sg, tu, mz = max_stresses_fast(infl, N_max, V_max, M_max, Mk_max, combine=True)
        RF_y = (Re / mz) if mz > 1e-9 else inf
        RF_u = (Rm / mz) if mz > 1e-9 else inf   # bez plast. rezervy (konzervativní)
        if basis == "yield":
            RF = RF_y
        elif basis == "ultimate":
            RF = RF_u
        else:
            RF = min(RF_y, RF_u)
        tp = getattr(section, "section_type", "?")
        rows.append({"seg": i, "label": f"{tr_('Úsek')} {i+1} · {tp}",
                     "material": getattr(mat, "name", "?"),
                     "sigma": sg, "tau": tu, "sred": mz, "RF": RF})
    if not rows:
        return None
    crit = min(rows, key=lambda r: r["RF"])
    return ConservativeResult(N_max, V_max, M_max, Mk_max, rows,
                              crit["RF"], crit["label"], crit["material"], env.n_combos)


@dataclass
class BucklingResult:
    """Posouzení vzpěrné stability (fáze 1: Johnson-Euler sloup per úsek).
    Tlačené úseky (N<0): kritické napětí σ_cr dle štíhlosti λ=μ·L/i_min,
    Euler pro štíhlé, Johnson parabola pro krátké; RF_vzpěr = σ_cr·A/|N|."""
    rows: list                     # [{seg, label, N, lam, sigma_cr, P_cr, RF}]
    rf_min: float
    crit_label: str


def _johnson_euler_sigma_cr(E, Fcy, lam):
    """Kritické napětí sloupu [MPa] dle štíhlosti λ. Euler pro λ≥λ_cr, Johnson
    parabola pro λ<λ_cr (tečné napojení při σ=Fcy/2). λ = μ·L/i_min."""
    import math
    if lam <= 1e-9 or E <= 0 or Fcy <= 0:
        return Fcy
    lam_cr = math.pi * math.sqrt(2.0 * E / Fcy)
    if lam >= lam_cr:
        return math.pi**2 * E / lam**2                 # Euler
    return Fcy * (1.0 - Fcy * lam**2 / (4.0 * math.pi**2 * E))   # Johnson


def buckling_check(state, result, env=None):
    """Vzpěr per úsek (fáze 1). Bere tlakovou osovou sílu (min N v úseku), slabou
    osu (I_min), μ z úseku (buckling_mu). `env` = obálka přes kombinace: pak se
    tlak bere z OBÁLKY N (nejnepříznivější kombinace per úsek), jinak jen ze
    zobrazeného výsledku. Vrací BucklingResult nebo None."""
    import math
    if result is None or not getattr(result, "is_stable", False) or not result.points:
        return None
    from .sections_along import (normalized_segments, def_for_segment,
                                 material_for_segment)
    from .section import build_section
    pts = result.points
    env_x = env_N = None
    if env is not None:
        env_x = np.asarray(env.xv)
        env_N = np.asarray(env.N_min)            # min N po délce přes kombinace
    rows = []
    for i, seg in enumerate(normalized_segments(state)):
        if env_N is not None:
            m = (env_x >= seg.x1 - 1e-6) & (env_x <= seg.x2 + 1e-6)
            if not m.any():
                continue
            N_c = float(env_N[m].min())          # obálkový tlak (přes kombinace)
        else:
            seg_pts = [p for p in pts if seg.x1 - 1e-6 <= p.x <= seg.x2 + 1e-6]
            if not seg_pts:
                continue
            N_c = min(p.N for p in seg_pts)      # nejzápornější = největší tlak
        if N_c >= 0:                             # jen tah → vzpěr neřešíme
            continue
        xm = (seg.x1 + seg.x2) / 2.0
        try:
            sec = build_section(def_for_segment(state, seg, xm), fem=False)
        except Exception:
            continue
        if sec is None or not getattr(sec, "valid", False):
            continue
        mat = material_for_segment(state, seg)
        props = _stability_properties(state, seg, xm, sec, mat)
        if props is None:
            continue
        area, I_min, E, Fcy, _ei_min, _prop = props
        i_min = math.sqrt(I_min / area) if I_min > 0 and area > 0 else 0.0
        if i_min <= 1e-9:
            continue
        mu = float(getattr(seg, "buckling_mu", 1.0) or 1.0)
        Lb = mu * (seg.x2 - seg.x1)
        lam = Lb / i_min
        sigma_cr = _johnson_euler_sigma_cr(E, Fcy, lam)
        P_cr = sigma_cr * area
        RF = P_cr / abs(N_c) if abs(N_c) > 1e-9 else float("inf")
        rows.append({"seg": i, "label": f"{tr_('Úsek')} {i+1}", "N": N_c,
                     "lam": lam, "sigma_cr": sigma_cr, "P_cr": P_cr, "RF": RF})
    if not rows:
        return None
    crit = min(rows, key=lambda r: r["RF"])
    return BucklingResult(rows, crit["RF"], crit["label"])


@dataclass
class BucklingEigenResult:
    """Vzpěrná stabilita fáze 2 – lineární bifurkační analýza celé soustavy.

    Řeší zobecněný problém vlastních čísel (K_b + λ·K_g)·φ = 0 v příčné (slabé)
    rovině: K_b = ohybová tuhost o slabé ose EI_min, K_g = geometrická (počáteční
    napětí) matice ze skutečného rozložení osové síly N(x) zobrazené kombinace.
    Nejmenší kladné λ = **kritický násobitel zatížení** (RF_vzpěr = λ_cr; loads
    lze násobit λ_cr, než soustava vybočí). Vzpěrná délka (μ) VYPLYNE z okrajových
    podmínek – žádný ruční odhad jako ve fázi 1."""
    lam_cr: float                  # kritický násobitel (RF_vzpěr)
    P_cr: float                    # kritická osová síla v nejtlačenějším místě [N]
    N_ref: float                   # referenční (max) tlak zobrazené kombinace [N]
    mu_eff: float                  # efektivní součinitel vzpěrné délky (odvozený)
    x_mode: list                   # uzly [mm]
    w_mode: list                   # tvar vybočení (normovaný na max=1)
    note: str = ""


def buckling_eigen_check(state, result, factors=None, n_target=80, axis="min"):
    """Vzpěr fáze 2 (vlastní čísla). Vrací `BucklingEigenResult` nebo None.
    `axis="min"` = slabá osa I_min (řídí; výchozí), `axis="max"` = silná osa I_max.
    Osová síla z `result` (rovnovážné pole jedné kombinace – NE obálka).
    Předpoklady: podpory drží příčný posun i v rovině vybočení (pin/rolna/
    vetknutí → w=0, vetknutí i φ=0), pružiny elasticky; klouby fáze 2 zatím
    neuvažují moment. Bez tlaku → None. Pozn.: při shodném podepření obou rovin
    řídí slabá osa; silná osa je relevantní až při odlišném vyztužení per rovina."""
    if result is None or not getattr(result, "is_stable", False) or not result.points:
        return None
    try:
        from scipy.linalg import eig as _geig
    except Exception:
        return None
    from .sections_along import SectionResolver, normalized_segments

    pts = sorted(result.points, key=lambda p: p.x)
    xv = np.array([p.x for p in pts])
    Nv = np.array([p.N for p in pts])
    if float(Nv.min()) >= -1e-6:                 # nikde tlak → vzpěr neřešíme
        return None
    L = float(state.length)

    # ── mřížka: uzly v podporách, kloubech, hranicích úseků; zhustit ~n_target ──
    nodeset = {0.0, L}
    for s in state.supports:
        if 0 <= s.x <= L:
            nodeset.add(float(s.x))
    for h in state.hinges:
        if 0 <= h.x <= L:
            nodeset.add(float(h.x))
    for sg in normalized_segments(state):
        for xb in (sg.x1, sg.x2):
            if 0 <= xb <= L:
                nodeset.add(float(xb))
    base = sorted(nodeset)
    step = max(L / max(n_target, 1), 1e-6)
    xs = [base[0]]
    for a, b in zip(base[:-1], base[1:]):
        nsub = max(1, int(math.ceil((b - a) / step)))
        for k in range(1, nsub + 1):
            xs.append(a + (b - a) * k / nsub)
    xs = np.array(xs)
    nn = len(xs)
    ndof = 2 * nn                                # w, φ na uzel

    resolver = SectionResolver(state)

    def EImin_at(xm):
        sec = resolver.at(xm)
        if sec is None or not getattr(sec, "valid", False) or sec.A <= 1e-9:
            return None
        if not getattr(sec, "stability_available", True):
            return None
        weighted = resolver.weighted_at(xm)
        if weighted is not None:
            avg = 0.5*(weighted.EIy + weighted.EIz)
            diff = math.sqrt((0.5*(weighted.EIy-weighted.EIz))**2
                             + weighted.EIyz**2)
            return avg + diff if axis == "max" else avg - diff
        E_e = resolver.E_at(xm) or state.material().E
        if axis == "max":
            inertia = max(float(getattr(sec, "I1", 0.0) or 0.0),
                          float(getattr(sec, "I2", 0.0) or 0.0))
            if inertia <= 0.0:
                inertia = max(sec.Iy, sec.Iz)
        else:
            inertia = _principal_inertia_min(sec)
        return E_e * inertia

    Kb = np.zeros((ndof, ndof))
    Kg = np.zeros((ndof, ndof))
    for i in range(nn - 1):
        le = float(xs[i + 1] - xs[i])
        if le <= 1e-9:
            continue
        xm = 0.5 * (xs[i] + xs[i + 1])
        EI = EImin_at(xm)
        if EI is None or EI <= 0:
            return None
        Ne = float(np.interp(xm, xv, Nv))        # osová síla (tah +), tlak < 0
        # ohybová tuhost (Euler-Bernoulli, Hermite)
        c = EI / le**3
        kb = c * np.array([
            [12,     6*le,    -12,     6*le],
            [6*le,   4*le**2, -6*le,   2*le**2],
            [-12,   -6*le,     12,    -6*le],
            [6*le,   2*le**2, -6*le,   4*le**2]])
        # geometrická (konzistentní), tah +
        g = Ne / (30.0 * le)
        kg = g * np.array([
            [36,     3*le,   -36,     3*le],
            [3*le,   4*le**2, -3*le, -le**2],
            [-36,   -3*le,    36,    -3*le],
            [3*le,  -le**2,  -3*le,   4*le**2]])
        d = [2*i, 2*i+1, 2*i+2, 2*i+3]
        for a in range(4):
            for b in range(4):
                Kb[d[a], d[b]] += kb[a, b]
                Kg[d[a], d[b]] += kg[a, b]

    # ── okrajové podmínky z podpor ──
    def node_at(x):
        j = int(np.argmin(np.abs(xs - x)))
        return j if abs(xs[j] - x) < 1e-3 else None

    fixed = set()
    for s in state.supports:
        j = node_at(s.x)
        if j is None:
            continue
        if s.type == "spring":
            Kb[2*j, 2*j] += float(getattr(s, "spring_z", 0.0) or 0.0)
            Kb[2*j+1, 2*j+1] += float(getattr(s, "spring_ry", 0.0) or 0.0)
        else:
            fixed.add(2*j)                       # w=0 (pin/rolna/vetknutí)
            if s.type == "fixed":
                fixed.add(2*j+1)                 # φ=0 (vetknutí)

    free = [d for d in range(ndof) if d not in fixed]
    if len(free) < 2:
        return None
    Kb_r = Kb[np.ix_(free, free)]
    Kg_r = Kg[np.ix_(free, free)]

    # (K_b + λ·K_g)φ=0  →  K_b φ = λ·(−K_g)φ ; nejmenší kladné reálné λ
    try:
        w, V = _geig(Kb_r, -Kg_r)
    except Exception:
        return None
    lam_cr = None
    vec = None
    for k in range(len(w)):
        lk = w[k]
        if abs(lk.imag) > 1e-6 * (abs(lk.real) + 1.0):
            continue
        lr = float(lk.real)
        if lr <= 1e-9 or not np.isfinite(lr):
            continue
        if lam_cr is None or lr < lam_cr:
            lam_cr = lr
            vec = np.real(V[:, k])
    if lam_cr is None:
        return None

    # tvar vybočení (w složky) na uzly
    wfull = np.zeros(ndof)
    for idx, d in enumerate(free):
        wfull[d] = vec[idx]
    wmode = wfull[0::2]
    wmax = float(np.max(np.abs(wmode)))
    if wmax > 1e-15:
        wmode = wmode / wmax

    N_ref = float(Nv.min())                      # největší tlak (nejzápornější)
    P_cr = lam_cr * abs(N_ref)
    # efektivní μ z Eulera: P_cr = π²·EI_min/(μ·L)²  → μ = π·√(EI_min/P_cr)/L
    xc = float(xv[int(np.argmin(Nv))])
    EI_ref = EImin_at(min(max(xc, 1e-6), L - 1e-6)) or 0.0
    mu_eff = (math.pi * math.sqrt(EI_ref / P_cr) / L) if (P_cr > 0 and EI_ref > 0) else 0.0

    return BucklingEigenResult(
        lam_cr=lam_cr, P_cr=P_cr, N_ref=N_ref, mu_eff=mu_eff,
        x_mode=[float(x) for x in xs], w_mode=[float(v) for v in wmode],
        note="")


@dataclass
class BeamColumnResult:
    """Interakce tlak + ohyb (beam-column) dle Bruhna – tlačené úseky."""
    rows: list                 # [{seg,label,N,P_cr,R_c,sigma_b,R_b,R_int,RF,MS}]
    rf_min: float
    crit_label: str


def beam_column_check(state, result, env=None):
    """Interakce tlaku a ohybu (beam-column) leteckou interakční rovnicí (Bruhn):

        R_c + R_b/(1 − R_c) ≤ 1 ,   R_c = |N|/P_cr ,   R_b = σ_ohyb/F_dov

    R_c je poměr osového tlaku ke kritickému (Euler/Johnson), R_b poměr ohybového
    napětí k dovolenému; člen 1/(1−R_c) je zesílení ohybu od tlaku (P-δ). Reserve
    faktor RF = 1/R_int, míra bezpečnosti MS = RF − 1. Řeší jen tlačené úseky
    (N<0); ohyb a osové účinky se berou ze ZOBRAZENÉ kombinace (fyzicky
    konzistentní rovnovážný stav). Vrací `BeamColumnResult` nebo None."""
    import math
    if result is None or not getattr(result, "is_stable", False) or not result.points:
        return None
    from .sections_along import (normalized_segments, def_for_segment,
                                 material_for_segment)
    from .section import build_section
    pts = result.points
    basis = getattr(state, "rf_basis", "min")
    combine = getattr(state, "sigma_red_mode", "exact") == "combined"
    rows = []
    for i, seg in enumerate(normalized_segments(state)):
        seg_pts = [p for p in pts if seg.x1 - 1e-6 <= p.x <= seg.x2 + 1e-6]
        if not seg_pts:
            continue
        N_c = min(p.N for p in seg_pts)          # nejzápornější = největší tlak
        if N_c >= 0:                             # jen tlak → beam-column neřešíme
            continue
        xm = (seg.x1 + seg.x2) / 2.0
        try:
            sec = build_section(def_for_segment(state, seg, xm), fem=False)
        except Exception:
            continue
        if sec is None or not getattr(sec, "valid", False):
            continue
        mat = material_for_segment(state, seg)
        props = _stability_properties(state, seg, xm, sec, mat)
        if props is None:
            continue
        area, I_min, E, Fcy, _ei_min, composite_prop = props
        i_min = math.sqrt(I_min / area) if I_min > 0 and area > 0 else 0.0
        if i_min <= 1e-9:
            continue
        mu = float(getattr(seg, "buckling_mu", 1.0) or 1.0)
        lam = mu * (seg.x2 - seg.x1) / i_min
        P_cr = _johnson_euler_sigma_cr(E, Fcy, lam) * area
        R_c = abs(N_c) / P_cr if P_cr > 1e-9 else float("inf")
        # ohybové napětí (biaxiálně, bez osové složky) v úseku
        M_seg = max((abs(p.M) for p in seg_pts), default=0.0)
        Mz_seg = max((abs(getattr(p, "M_z", 0.0)) for p in seg_pts), default=0.0)
        if composite_prop is not None:
            from .composite import composite_stress
            stress_rows = composite_stress(
                state, composite_prop, 0.0, M_seg, Mz=Mz_seg,
            ) or []
            sig_b = max((row["sigma_max"] for row in stress_rows), default=0.0)
            ratios = []
            for row in stress_rows:
                if basis == "yield":
                    allowable = row["Re"]
                elif basis == "ultimate":
                    allowable = row["Rm"]
                else:
                    allowable = min(row["Re"], row["Rm"])
                ratios.append(row["sigma_max"] / allowable
                              if allowable > 1e-9 else float("inf"))
            R_b = max(ratios, default=0.0)
        else:
            infl = build_influence(sec, n=60)
            sig_b, _, _ = max_stresses_fast(
                infl, 0.0, 0.0, M_seg, 0.0, Mz=Mz_seg, combine=combine,
            )
            Re = getattr(mat, "Re", 0.0); Rm = getattr(mat, "Rm", 0.0)
            if basis == "yield":
                F_b = Re
            elif basis == "ultimate":
                F_b = Rm
            else:
                F_b = min(Re, Rm) if (Re > 0 and Rm > 0) else max(Re, Rm)
            R_b = sig_b / F_b if F_b > 1e-9 else float("inf")
        R_int = float("inf") if R_c >= 1.0 else R_c + R_b / (1.0 - R_c)
        RF = 1.0 / R_int if R_int > 1e-12 else float("inf")
        rows.append({"seg": i, "label": f"{tr_('Úsek')} {i+1}", "N": N_c, "P_cr": P_cr,
                     "R_c": R_c, "sigma_b": sig_b, "R_b": R_b, "R_int": R_int,
                     "RF": RF, "MS": RF - 1.0})
    if not rows:
        return None
    crit = min(rows, key=lambda r: r["RF"])
    return BeamColumnResult(rows, crit["RF"], crit["label"])


def load_case_summary(state, factors, label=""):
    """Souhrnný řádek pro jednu kombinaci (faktory lc_id→faktor) pro Load Case
    Builder. Vrací (cols, result), kde cols = [(název_sloupce, hodnota), …]
    v pevném pořadí (ploché, pro tabulku/CSV/schránku)."""
    from .solver import solve_beam
    res = solve_beam(state, factors=factors)
    cols = [("Kombinace", label)]
    if not res.is_stable or not res.points:
        cols.append((tr_("stav"), tr_("NESTABILNÍ")))
        return cols, res
    P = res.points

    def mm(attr):
        vals = [getattr(p, attr) for p in P]
        return max(vals), min(vals)

    for a, unit in [("N", "N"), ("V", "N"), ("M", "N·mm"), ("Mk", "N·mm"), ("w", "mm")]:
        mx, mn = mm(a)
        cols.append((f"{a} max [{unit}]", mx))
        cols.append((f"{a} min [{unit}]", mn))
    rsv = reserves_along_beam(res, state)
    if rsv:
        crit = min(rsv, key=lambda r: r.RF)
        cols.append(("σ_red max [MPa]", max(r.mises_max for r in rsv)))
        cols.append(("RF min", crit.RF))
        cols.append(("x(RFmin) [mm]", crit.x))
    for i, rc in enumerate(res.reactions):
        cols.append((f"R{i+1} Rz [N]", rc.Rz))
        cols.append((f"R{i+1} My [N·mm]", rc.Ry))
    cps = getattr(state, "control_points", None) or []
    for oi, cp in sorted(enumerate(cps), key=lambda t: t[1].x):
        nm = (cp.name.strip() if getattr(cp, "name", "") else "") or f"K{oi+1}"
        d = values_at_x(res, state, cp.x)
        if d:
            cols.append((f"{nm} M [N·mm]", d["M"]))
            cols.append((f"{nm} σ_red [MPa]", d["mises_max"]))
            cols.append((f"{nm} RF", d["RF"]))
    return cols, res


def tr_(s):
    from .i18n import tr
    return tr(s)


def extremum_x(result, attr):
    """x [mm], kde |attr| (např. 'V', 'M', 'Mk') nabývá maxima. None pokud nelze."""
    if result is None or not result.points:
        return None
    p = max(result.points, key=lambda pt: abs(getattr(pt, attr)))
    return p.x


def critical_x(reserves):
    """x [mm] nejkritičtějšího řezu (nejnižší RF). None pokud nejsou rezervy."""
    if not reserves:
        return None
    return min(reserves, key=lambda r: r.RF).x


def peaks_x(result, attr):
    """Lokální špičky |attr| (V/M/Mk/…) podél nosníku, seřazené sestupně dle
    velikosti. Vrací list x [mm]. Pro cyklování špiček v kartě Report –
    např. u vetknutého nosníku: 1. špička = moment ve vetknutí, 2. = max na poli."""
    if result is None or not result.points:
        return []
    pts = result.points
    xs = [p.x for p in pts]
    av = [abs(getattr(p, attr)) for p in pts]
    n = len(av)
    if n == 0 or max(av) < 1e-9:
        return []
    span = (xs[-1] - xs[0]) or 1.0
    cand = []
    for i in range(n):
        left = av[i-1] if i > 0 else -1.0
        right = av[i+1] if i < n-1 else -1.0
        # lokální max; vnitřní body plata vynech (musí být ostře větší aspoň 1×)
        if av[i] >= left and av[i] >= right and (av[i] > left or av[i] > right):
            cand.append(i)
    cand.sort(key=lambda i: -av[i])
    chosen = []
    for i in cand:
        if all(abs(xs[i] - xs[j]) > 0.01 * span for j in chosen):
            chosen.append(i)
    return [xs[i] for i in chosen]


def critical_per_part(state, reserves):
    """Pro každý úsek (section_segment) vrátí kritickou stanici (nejnižší RF).
    Vrací list dictů: {idx, x1, x2, material, section_type, crit (ReserveResult|None)}.
    Materiál a typ průřezu se berou EFEKTIVNĚ (přes PID / knihovní odkaz),
    ne z inline polí úseku – ta jsou u PID úseků jen placeholder."""
    from .sections_along import (normalized_segments, material_for_segment,
                                 eff_defs, property_by_id)
    segs = normalized_segments(state)
    out = []
    for i, seg in enumerate(segs):
        in_seg = [r for r in reserves if seg.x1 - 1e-6 <= r.x <= seg.x2 + 1e-6]
        crit = min(in_seg, key=lambda r: r.RF) if in_seg else None
        mat = material_for_segment(state, seg)
        mat_name = mat.name if mat else "?"
        p = property_by_id(state, getattr(seg, "property_id", None))
        if p is not None and getattr(p, "composite_parts", None):
            sec_type = "composite"
        else:
            s1, _s2 = eff_defs(state, seg)
            sec_type = getattr(s1, "type", None) or "?"
        out.append({
            "idx": i, "x1": seg.x1, "x2": seg.x2,
            "material": mat_name, "section_type": sec_type, "crit": crit,
        })
    return out
