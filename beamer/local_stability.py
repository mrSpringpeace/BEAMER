"""Lokální stabilita tenkostěnných parametrických průřezů.

Modul drží klasickou deskovou teorii odděleně od nosníkového solveru.  Pracuje
jen se stěnami, jejichž topologie je známá z parametrického generátoru; obecný
polygon se zde záměrně nedomýšlí.

Jednotky: délky mm, modul a napětí MPa.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
from typing import Literal


EdgeCondition = Literal["supported_supported", "supported_free"]


@dataclass(frozen=True)
class PlateWall:
    """Jedna plochá stěna průřezu v těžišťových souřadnicích y-z."""

    label: str
    width: float
    thickness: float
    edge_condition: EdgeCondition
    start_y: float
    start_z: float
    end_y: float
    end_z: float

    @property
    def area(self) -> float:
        return self.width * self.thickness

    @property
    def midpoint(self) -> tuple[float, float]:
        return ((self.start_y + self.end_y) / 2.0,
                (self.start_z + self.end_z) / 2.0)


@dataclass(frozen=True)
class WallBucklingResult:
    label: str
    sigma_compression: float
    sigma_cr: float
    RF: float
    k: float


@dataclass(frozen=True)
class LocalStabilityResult:
    """Lokální stabilita jednoho řezu; ``None`` znamená neaplikovatelné."""

    available: bool
    note: str = ""
    walls: tuple[WallBucklingResult, ...] = ()
    RF_local_buckling: float | None = None
    critical_wall: str = ""
    sigma_crippling: float | None = None
    RF_crippling: float | None = None
    crippling_method: str = ""


def _validate_plate_inputs(aspect_ratio: float, nu: float) -> None:
    if not math.isfinite(aspect_ratio) or aspect_ratio <= 0.0:
        raise ValueError("Poměr stran desky a/b musí být kladný a konečný.")
    if not math.isfinite(nu) or not (-0.99 < nu < 0.5):
        raise ValueError("Poissonovo číslo musí ležet v intervalu (-0.99, 0.5).")


def _k_supported_supported(aspect_ratio: float) -> float:
    """Přesné minimum Navierova řešení pro desku kloubově podepřenou po 4 hranách."""
    # k_m = (m/alpha + alpha/m)^2.  Minimum leží u m ~= alpha; širší
    # celočíselný rozsah drží řešení přesné i pro velmi krátké desky.
    m_max = max(8, int(math.ceil(aspect_ratio)) + 4)
    return min(
        (m / aspect_ratio + aspect_ratio / m) ** 2
        for m in range(1, m_max + 1)
    )


def _sf_determinant(t: float, q: float, nu: float) -> float:
    """Charakteristický determinant desky: podepřený a volný podélný okraj."""
    # Dimensionless roots of Y'''' - 2q²Y'' + (q⁴-lambda q²)Y = 0,
    # t = pi*sqrt(k), q = m*pi/(a/b).  Pro fyzikální první větev je t > q.
    qt = q * t
    aa = math.sqrt(q*q + qt)
    bb = math.sqrt(max(qt - q*q, 0.0))
    sh = math.sinh(aa)
    ch = math.cosh(aa)
    sb = math.sin(bb)
    cb = math.cos(bb)
    a1 = (aa*aa - nu*q*q) * sh
    d1 = (-bb*bb - nu*q*q) * sb
    a2 = aa * (aa*aa - (2.0 - nu)*q*q) * ch
    d2 = -bb * (bb*bb + (2.0 - nu)*q*q) * cb
    # Dělení společnou exponenciální škálou chrání delší hodnoty aa před
    # přetečením a nemění polohu kořenů.
    return (a1*d2 - d1*a2) / max(ch, 1.0)


@lru_cache(maxsize=256)
def _k_supported_free_cached(aspect_ratio: float, nu: float) -> float:
    """První vlastní hodnota desky s jedním podepřeným a jedním volným okrajem."""
    # Pro dlouhou desku je klasický limit 0.425; v praxi se tabulkuje 0.43.
    if aspect_ratio >= 20.0:
        return 0.425

    from scipy.optimize import brentq

    best = math.inf
    # Vyšší podélné půlvlny mohou řídit u delší desky.  Rozsah kolem alpha je
    # doplněn rezervou, stejně jako u uzavřeného Navierova řešení.
    m_max = max(6, int(math.ceil(aspect_ratio)) + 3)
    for m in range(1, m_max + 1):
        q = m * math.pi / aspect_ratio
        lo = q * (1.0 + 1e-7)
        hi = max(lo + 12.0*math.pi, 16.0*math.pi)
        # Husté bezrozměrné skenování je deterministické a vyhne se nepravému
        # kořeni B=0 přesně v t=q.
        n_scan = 1200
        prev_t = lo
        prev_f = _sf_determinant(prev_t, q, nu)
        for i in range(1, n_scan + 1):
            cur_t = lo + (hi - lo) * i / n_scan
            cur_f = _sf_determinant(cur_t, q, nu)
            if math.isfinite(prev_f) and math.isfinite(cur_f) and prev_f*cur_f < 0.0:
                root = brentq(_sf_determinant, prev_t, cur_t, args=(q, nu),
                              xtol=1e-11, rtol=1e-11)
                k = (root / math.pi) ** 2
                if k > 1e-8:
                    best = min(best, k)
                    break
            prev_t, prev_f = cur_t, cur_f
    if not math.isfinite(best):
        raise RuntimeError("Nepodařilo se určit součinitel boulení desky.")
    return best


def plate_buckling_coefficient(edge_condition: EdgeCondition,
                               aspect_ratio: float,
                               nu: float = 0.3) -> float:
    """Vrátí elastický součinitel k pro rovnoměrný tlak a zadané uložení."""
    _validate_plate_inputs(aspect_ratio, nu)
    if edge_condition == "supported_supported":
        return _k_supported_supported(aspect_ratio)
    if edge_condition == "supported_free":
        # Zaokrouhlení cache klíče nemá technický vliv, ale brání růstu cache u
        # tapered průřezů s numericky téměř shodným poměrem stran.
        return _k_supported_free_cached(round(aspect_ratio, 8), round(nu, 8))
    raise ValueError(f"Neznámé uložení stěny: {edge_condition}")


def elastic_plate_buckling_stress(E: float, nu: float, thickness: float,
                                  width: float, length: float,
                                  edge_condition: EdgeCondition) -> float:
    """Klasické elastické kritické tlakové napětí ploché stěny [MPa]."""
    if E <= 0.0 or thickness <= 0.0 or width <= 0.0 or length <= 0.0:
        raise ValueError("E, tloušťka, šířka a délka desky musí být kladné.")
    k = plate_buckling_coefficient(edge_condition, length / width, nu)
    return k * math.pi**2 * E / (12.0 * (1.0 - nu**2)) * (thickness / width)**2


def needham_crippling_stress(E: float, Fcy: float,
                             walls: list[PlateWall]) -> float | None:
    """Needhamova empirická kapacita konstantně tlustého profilu [MPa].

    ``b'`` je průměr šířek stěn. Koeficient C_e je 0.316/0.342/0.366 pro
    dva/jeden/žádný volný okraj. Metoda se neextrapoluje na více než dva volné
    okraje ani na proměnnou tloušťku.
    """
    if E <= 0.0 or Fcy <= 0.0 or not walls:
        return None
    ts = [wall.thickness for wall in walls]
    t = sum(ts) / len(ts)
    if t <= 0.0 or max(abs(ti-t) for ti in ts) > 1e-6*max(t, 1.0):
        return None
    free_edges = sum(wall.edge_condition == "supported_free" for wall in walls)
    ce = {2: 0.316, 1: 0.342, 0: 0.366}.get(free_edges)
    if ce is None:
        return None
    b_prime = sum(wall.width for wall in walls) / len(walls)
    slenderness = b_prime / t
    if slenderness < 10.0:
        return None
    return ce * math.sqrt(Fcy*E) / slenderness**0.75


def gerard_crippling_stress(E: float, Fcy: float, area: float,
                            t_average: float, section_type: str) -> float | None:
    """Gerardova kapacita běžných integrálních profilů [MPa].

    Používá klasifikaci původních rovnic: úhelník/multicorner (m=0.85),
    T/H s přímými nezatíženými hranami (m=0.4) a dvourohový U/C profil.
    Výsledek je omezen tabulkovou horní mezí vůči Fcy.
    """
    if min(E, Fcy, area, t_average) <= 0.0:
        return None
    if section_type == "l_section":
        g, cap = 2.0, 0.7
        ratio = 0.56 * (g*t_average**2/area * math.sqrt(E/Fcy))**0.85
    elif section_type == "box":
        g, cap = 4.0, 0.8
        ratio = 0.56 * (g*t_average**2/area * math.sqrt(E/Fcy))**0.85
    elif section_type in ("t_section", "i_section"):
        # g = počet původních stěnových prvků + řezy potřebné k rozdělení na
        # úhelníkové elementy: T 3+1, I 5+3.
        g = 4.0 if section_type == "t_section" else 8.0
        cap = 0.8
        ratio = 0.67 * (g*t_average**2/area * math.sqrt(E/Fcy))**0.4
    elif section_type in ("c_section", "u_section"):
        cap = 0.9
        ratio = 3.2 * (t_average**2/area * (E/Fcy)**(1.0/3.0))**0.75
    else:
        return None
    return min(ratio, cap) * Fcy


def gerard_stiffened_panel_stress(E: float, Fcy: float, area: float,
                                  t_average: float, t_skin: float, g: float,
                                  beta: float, exponent: float = 0.85) -> float:
    """Gerardova obecná rovnice pro validaci sestavy stěn/stiffened panelu."""
    if min(E, Fcy, area, t_average, t_skin, g, beta, exponent) <= 0.0:
        raise ValueError("Vstupy Gerardovy rovnice musí být kladné.")
    ratio = beta * (g*t_average*t_skin/area * math.sqrt(E/Fcy))**exponent
    return ratio * Fcy


def normal_stress_at_points(section, points: list[tuple[float, float]],
                            N: float, M: float, Mz: float = 0.0,
                            B: float = 0.0) -> list[float]:
    """Nosníkové normálové napětí [MPa] v bodech y-z (mm, N, Nmm)."""
    area = float(getattr(section, "A", 0.0) or 0.0)
    iy = float(getattr(section, "Iy", 0.0) or 0.0)
    iz = float(getattr(section, "Iz", 0.0) or 0.0)
    iyz = float(getattr(section, "Iyz", 0.0) or 0.0)
    den = iy*iz - iyz*iyz
    base = N/area if area > 1e-12 else 0.0
    out = []
    for y, z in points:
        sigma = base
        if den > 1e-20:
            sigma -= ((M*iz-Mz*iyz)*z + (Mz*iy-M*iyz)*y) / den
        elif iy > 1e-20:
            sigma -= M*z/iy
        out.append(sigma)

    wf = getattr(section, "warping_field", None)
    iw = float(wf.get("Iw", 0.0)) if wf else 0.0
    coords = wf.get("node_coords") if wf else None
    omega = wf.get("node_omega") if wf else None
    if abs(B) > 0.0 and iw > 0.0 and coords is not None and omega is not None:
        # Topologie a FEM síť sdílejí těžišťové souřadnice. Nejbližší uzel je
        # transparentní diskrétní interpolace; přesnost roste se stejnou sítí,
        # která určuje Iomega a warpingové RF.
        for i, (y, z) in enumerate(points):
            idx = min(range(len(coords)),
                      key=lambda j: (float(coords[j][0])-y)**2
                                    + (float(coords[j][1])-z)**2)
            out[i] += B/iw * float(omega[idx])
    return out


def assess_local_stability(section, material, length: float, N: float, M: float,
                           Mz: float = 0.0, B: float = 0.0) -> LocalStabilityResult:
    """Vyhodnotí stěnové boulení a crippling známého parametrického profilu."""
    walls = list(getattr(section, "local_walls", None) or [])
    if not walls:
        return LocalStabilityResult(
            False,
            getattr(section, "local_stability_note",
                    "Topologie stěn není pro tento průřez dostupná."),
        )
    E = float(getattr(material, "E", 0.0) or 0.0)
    nu = float(getattr(material, "nu", 0.0) or 0.0)
    fcy = getattr(material, "Fcy", None)
    Fcy = float(fcy if fcy is not None and fcy > 0.0
                else getattr(material, "Re", 0.0) or 0.0)
    if E <= 0.0 or Fcy <= 0.0 or length <= 0.0:
        return LocalStabilityResult(False, "Chybí kladné E, Fcy/Re nebo délka stěny.")

    rows = []
    for wall in walls:
        points = [(wall.start_y, wall.start_z), wall.midpoint,
                  (wall.end_y, wall.end_z)]
        stresses = normal_stress_at_points(section, points, N, M, Mz, B)
        compression = max(0.0, -min(stresses))
        k = plate_buckling_coefficient(wall.edge_condition,
                                       length/wall.width, nu)
        elastic = elastic_plate_buckling_stress(
            E, nu, wall.thickness, wall.width, length, wall.edge_condition,
        )
        sigma_cr = min(elastic, Fcy)
        rf = sigma_cr/compression if compression > 1e-9 else math.inf
        rows.append(WallBucklingResult(wall.label, compression, sigma_cr, rf, k))

    active = [row for row in rows if math.isfinite(row.RF)]
    if active:
        critical = min(active, key=lambda row: row.RF)
        rf_local = critical.RF
        critical_wall = critical.label
        compression_max = max(row.sigma_compression for row in active)
    else:
        rf_local = None
        critical_wall = ""
        compression_max = 0.0

    # Crippling je kapacita celé sestavy při rovnoměrném tlaku. Pod ohybem ji
    # porovnáváme s největším lokálním tlakem — vědomě konzervativní omezení.
    slenderness = min(wall.width/wall.thickness for wall in walls)
    sigma_crippling = None
    crippling_method = ""
    if slenderness >= 10.0:
        # Needham určuje kapacitu jednotlivých úhelníků a u složitějšího
        # stringeru vyžaduje jejich rozklad a plošně vážený součet. Samotný
        # L-profil je jediná zdejší rodina, kde je tento rozklad jednoznačný.
        section_type = getattr(section, "section_type", "")
        needham = (needham_crippling_stress(E, Fcy, walls)
                    if section_type == "l_section" else None)
        area = sum(wall.area for wall in walls)
        total_width = sum(wall.width for wall in walls)
        t_average = area/total_width if total_width > 0.0 else 0.0
        gerard = gerard_crippling_stress(
            E, Fcy, area, t_average, section_type,
        )
        candidates = [(v, name) for v, name in (
            (needham, "Needham"), (gerard, "Gerard"),
        ) if v is not None and v > 0.0]
        if candidates:
            sigma_crippling, crippling_method = min(candidates, key=lambda item: item[0])
    rf_crippling = (sigma_crippling/compression_max
                    if sigma_crippling is not None and compression_max > 1e-9
                    else None)
    return LocalStabilityResult(
        True, walls=tuple(rows), RF_local_buckling=rf_local,
        critical_wall=critical_wall, sigma_crippling=sigma_crippling,
        RF_crippling=rf_crippling, crippling_method=crippling_method,
    )
