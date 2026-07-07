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
    """
    z_mm: np.ndarray     # z-grid [mm od těžiště]
    c_sN: float          # 1/A_si          [1/m²]
    c_sM: np.ndarray     # z_si/Iy_si      [1/m³]
    c_tV: np.ndarray     # Q_si/(Iy_si·b_si)
    c_tT: np.ndarray     # t_si/IT_si


def build_influence(section: CrossSection, n=60) -> StressInfluence:
    """Spočítá vlivové koeficienty pro daný průřez (jednou). Drahá scanline část."""
    A_si = section.A/1e6
    Iy_si = section.Iy/1e12
    IT_si = section.IT/1e12

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
    return StressInfluence(z, c_sN, c_sM, c_tV, c_tT)


def max_stresses_fast(infl: StressInfluence, N, V, M, Mk, combine=False):
    """Max |σ|, |τ|, σ_red [MPa] z předpočítaných koeficientů. Vektorizováno.

    combine=False → σ_red = skutečné maximum von Mises po řezu (špička σ a špička
    τ jsou obecně v RŮZNÝCH bodech, proto σ_red může = max(|σ|), když ohyb vyhrává).
    combine=True  → konzervativní σ_red = √(σ_max²+3·τ_max²) (špičky sečteny na
    povrchu; vhodné pro čepy/šrouby, kde nosníková teorie τ=0 na okraji je sporná).
    """
    My = M/1e3      # N·mm → N·m
    Mk_nm = Mk/1e3
    sigma = N*infl.c_sN + My*infl.c_sM            # Pa
    tau = V*infl.c_tV + Mk_nm*infl.c_tT           # Pa
    def _maxabs(a):
        a = a[~np.isnan(a)]
        return float(np.max(np.abs(a)))/1e6 if a.size else 0.0
    sg, tu = _maxabs(sigma), _maxabs(tau)
    if combine:
        mz = math.sqrt(sg**2 + 3*tu**2)
    else:
        mz = _maxabs(np.sqrt(sigma**2 + 3*tau**2))
    return sg, tu, mz


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


def stress_profile(section: CrossSection, N, V, M, Mk, n=160) -> StressProfile:
    """Detailní průběh napětí po výšce (pro diagram). Výstup MPa.
    Používá rychlé vlivové koeficienty (vektorizováno)."""
    infl = build_influence(section, n=n)
    My = M/1e3
    Mk_nm = Mk/1e3
    sigma = (N*infl.c_sN + My*infl.c_sM)/1e6
    tau = (V*infl.c_tV + Mk_nm*infl.c_tT)/1e6
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


def reserves_along_beam(result, state, n_stations=120, progress=None):
    """Posouzení RF (reserve factor) podél nosníku – zatížení = početní (ultimate).
    RF_yield = Re/σ_red, RF_ultimate = Rm/σ_red. `progress(frac)` callback 0..1.
    Vlivové koeficienty se počítají jednou → rychlé i pro stovky stanic."""
    section = result.section
    if section is None or not result.points:
        return []
    basis = getattr(state, "rf_basis", "min")
    combine = getattr(state, "sigma_red_mode", "exact") == "combined"
    g_mat = state.material()
    resolver = getattr(result, "resolver", None)

    def mat_at(x):
        if resolver is not None:
            return resolver.material_at(x)
        return g_mat

    # tvarový součinitel plasticity – zohlední se jen v RF_ultimate
    from .section import ALPHA_PL_TABLE
    plast = getattr(state, "plasticity_enabled", False)
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
        base_infl = build_influence(section, n=60)
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
                seen[key] = (build_influence(cs, n=50), alpha_pl_for(cs), mat.Re, mat.Rm)
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
            ca = composite_assess(state, pr, p.N, p.M, basis, Mk=p.Mk, V=p.V)
            if ca is not None:
                out.append(ReserveResult(p.x, ca["sigma_max"], ca["tau_max"], ca["mises_max"],
                                         ca["RF_yield"], ca["RF_ultimate"], ca["RF"],
                                         ca["critical"]))
                continue
        infl, alpha, Re, Rm = data_at(p.x)
        sg, tu, mz = max_stresses_fast(infl, p.N, p.V, p.M, p.Mk, combine=combine)
        RF_y = (Re/mz) if mz > 1e-9 else float("inf")
        # plastická rezerva (α_pl·M_pl) se uplatní jen v ultimate
        RF_u = (alpha*Rm/mz) if mz > 1e-9 else float("inf")
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


def _assess(section, mat, state, N, V, M, Mk, seg=None):
    """Napětí (σ/τ/σ_red) a rezervní faktory pro daný průřez+materiál a VVÚ.
    Vrací dílčí dict (bez x/VVÚ). Pro složený PID z různých materiálů (seg s
    property_id) vrátí per-materiálové posouzení (normálové, B1)."""
    if seg is not None:
        pid = getattr(seg, "property_id", None)
        if pid:
            from .sections_along import property_by_id
            p = property_by_id(state, pid)
            if p is not None and getattr(p, "composite_parts", None):
                from .composite import composite_assess
                ca = composite_assess(state, p, N, M, getattr(state, "rf_basis", "min"), Mk=Mk, V=V)
                if ca is not None:
                    ca.update({"section": section, "material": mat, "alpha_pl": 1.0,
                               "sigma_z": None, "tau_z": None})
                    return ca
    sg = tu = mz = 0.0
    z_sg = z_tu = 0.0
    combine = getattr(state, "sigma_red_mode", "exact") == "combined"
    if section is not None and getattr(section, "valid", False):
        infl = build_influence(section, n=80)
        sg, tu, mz = max_stresses_fast(infl, N, V, M, Mk, combine=combine)
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
    RF_u = (alpha * Rm / mz) if mz > 1e-9 else float("inf")
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
    d = {"x": x, "N": N, "V": V, "M": M, "Mk": Mk, "w": w, "phi": phi, "theta": theta}
    d.update(_assess(section, mat, state, N, V, M, Mk, seg=seg))
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
    base = {"x": x, "N": N, "V": V, "M": M, "Mk": Mk, "w": w, "phi": phi, "theta": theta}

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
        d.update(_assess(section, mat, state, N, V, M, Mk, seg=seg))
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
    import numpy as np
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
        if sec is None or not getattr(sec, "valid", False) or sec.A <= 1e-9:
            continue
        I_min = min(sec.Iy, sec.Iz)
        i_min = math.sqrt(I_min / sec.A) if I_min > 0 else 0.0
        if i_min <= 1e-9:
            continue
        mat = material_for_segment(state, seg)
        E = getattr(seg, "E", None) or getattr(mat, "E", 210000.0)
        Fcy = getattr(mat, "Re", 235.0)
        mu = float(getattr(seg, "buckling_mu", 1.0) or 1.0)
        Lb = mu * (seg.x2 - seg.x1)
        lam = Lb / i_min
        sigma_cr = _johnson_euler_sigma_cr(E, Fcy, lam)
        P_cr = sigma_cr * sec.A
        RF = P_cr / abs(N_c) if abs(N_c) > 1e-9 else float("inf")
        rows.append({"seg": i, "label": f"{tr_('Úsek')} {i+1}", "N": N_c,
                     "lam": lam, "sigma_cr": sigma_cr, "P_cr": P_cr, "RF": RF})
    if not rows:
        return None
    crit = min(rows, key=lambda r: r["RF"])
    return BucklingResult(rows, crit["RF"], crit["label"])


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
