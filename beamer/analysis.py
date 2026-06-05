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
        t_si = section.t_wall_at(zi)/1e3
        c_tT[i] = t_si/IT_si if IT_si > 1e-30 else 0.0
    c_sN = 1.0/A_si if A_si > 1e-30 else 0.0
    return StressInfluence(z, c_sN, c_sM, c_tV, c_tT)


def max_stresses_fast(infl: StressInfluence, N, V, M, Mk):
    """Max |σ|, |τ|, σ_red [MPa] z předpočítaných koeficientů. Vektorizováno."""
    My = M/1e3      # N·mm → N·m
    Mk_nm = Mk/1e3
    sigma = N*infl.c_sN + My*infl.c_sM            # Pa
    tau = V*infl.c_tV + Mk_nm*infl.c_tT           # Pa
    mises = np.sqrt(sigma**2 + 3*tau**2)
    def _maxabs(a):
        a = a[~np.isnan(a)]
        return float(np.max(np.abs(a)))/1e6 if a.size else 0.0
    return _maxabs(sigma), _maxabs(tau), _maxabs(mises)


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
        N_REP = 24
        rep_x = np.linspace(xs[0], xs[-1], N_REP)
        rep = []
        seen = {}
        for rx in rep_x:
            cs = resolver.at(float(rx))
            mat = resolver.material_at(float(rx))
            key = (id(cs), id(mat))
            if key not in seen:
                seen[key] = (build_influence(cs, n=50), alpha_pl_for(cs), mat.Re, mat.Rm)
            rep.append((rx, seen[key]))
        rep_xarr = np.array([rx for rx, _ in rep])

        def data_at(x):
            j = int(np.argmin(np.abs(rep_xarr - x)))
            return rep[j][1]

    if progress:
        progress(0.5)

    out = []
    for i in range(n_stations):
        xq = xs[0] + (xs[-1]-xs[0])*i/(n_stations-1)
        idx = int(np.argmin(np.abs(xs - xq)))
        p = pts[idx]
        infl, alpha, Re, Rm = data_at(p.x)
        sg, tu, mz = max_stresses_fast(infl, p.N, p.V, p.M, p.Mk)
        RF_y = (Re/mz) if mz > 1e-9 else float("inf")
        # plastická rezerva (α_pl·M_pl) se uplatní jen v ultimate
        RF_u = (alpha*Rm/mz) if mz > 1e-9 else float("inf")
        RF = min(RF_y, RF_u)
        crit = "yield" if RF_y <= RF_u else "ultimate"
        out.append(ReserveResult(p.x, sg, tu, mz, RF_y, RF_u, RF, crit))
        if progress and i % 10 == 0:
            progress(0.5 + 0.5*i/n_stations)
    if progress:
        progress(1.0)
    return out


def values_at_x(result, state, x):
    """Kompletní hodnoty v libovolném řezu x: VVÚ (lineárně interpolované),
    průřez a materiál v řezu, napětí (σ/τ/σ_red) a rezervní faktory.
    Vrací dict, nebo None pokud výsledek není stabilní."""
    if result is None or not getattr(result, "is_stable", False) or not result.points:
        return None
    pts = result.points
    xs = [p.x for p in pts]
    x = max(xs[0], min(xs[-1], float(x)))      # clamp do rozsahu nosníku

    def interp(attr):
        return float(np.interp(x, xs, [getattr(p, attr) for p in pts]))

    N = interp("N"); V = interp("V"); M = interp("M"); Mk = interp("Mk")
    w = interp("w"); phi = interp("phi"); theta = interp("theta")

    resolver = getattr(result, "resolver", None)
    if resolver is not None:
        section = resolver.at(x)
        mat = resolver.material_at(x)
    else:
        section = result.section
        mat = state.material()

    sg = tu = mz = 0.0
    if section is not None and getattr(section, "valid", False):
        infl = build_influence(section, n=80)
        sg, tu, mz = max_stresses_fast(infl, N, V, M, Mk)

    # součinitel plasticity (jen do RF_ultimate, dle nastavení)
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
    RF = min(RF_y, RF_u)
    crit = "yield" if RF_y <= RF_u else "ultimate"

    return {
        "x": x, "N": N, "V": V, "M": M, "Mk": Mk,
        "w": w, "phi": phi, "theta": theta,
        "section": section, "material": mat,
        "sigma_max": sg, "tau_max": tu, "mises_max": mz,
        "RF_yield": RF_y, "RF_ultimate": RF_u, "RF": RF,
        "critical": crit, "alpha_pl": alpha,
    }


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


def critical_per_part(state, reserves):
    """Pro každý úsek (section_segment) vrátí kritickou stanici (nejnižší RF).
    Vrací list dictů: {idx, x1, x2, material, section_type, crit (ReserveResult|None)}."""
    from .sections_along import normalized_segments
    segs = normalized_segments(state)
    out = []
    for i, seg in enumerate(segs):
        in_seg = [r for r in reserves if seg.x1 - 1e-6 <= r.x <= seg.x2 + 1e-6]
        crit = min(in_seg, key=lambda r: r.RF) if in_seg else None
        mid = getattr(seg, "material_id", None)
        mat = next((m for m in state.materials if m.id == mid), None)
        mat_name = mat.name if mat else (state.material().name if state.materials else "?")
        out.append({
            "idx": i, "x1": seg.x1, "x2": seg.x2,
            "material": mat_name, "section_type": seg.sec1.type, "crit": crit,
        })
    return out
