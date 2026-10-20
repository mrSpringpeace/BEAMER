"""Datový model projektu – dataclasses zrcadlící původní TS typy.

Jednotky: délky mm, síly N, momenty N·mm, napětí MPa (=N/mm²),
moduly E,G v MPa, hustota g/cm³.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

SupportType = Literal["fixed", "pin", "roller", "spring"]
LoadType = Literal["point_force", "moment", "torsion", "distributed", "thermal",
                   "self_weight"]   # self_weight: q = −ρ·A(x)·g na x1–x2 (selfweight.py)
SectionType = Literal[
    "rectangle", "box", "circle", "tube",
    "i_section", "c_section", "t_section", "l_section", "u_section",
    "polygon", "direct", "construction",
]
Theory = Literal["euler-bernoulli", "timoshenko"]
TorsionTheory = Literal["saint-venant", "vlasov"]


@dataclass
class Material:
    id: str
    name: str
    E: float        # Youngův modul (MPa)
    G: float        # smykový modul (MPa)
    nu: float       # Poissonovo číslo
    rho: float      # hustota (g/cm³)
    Re: float       # mez kluzu (MPa)
    Rm: float       # mez pevnosti (MPa)
    is_custom: bool = False
    alpha: float = 12e-6   # součinitel teplotní roztažnosti [1/°C] (ocel ~12e-6)
    Fcy: Optional[float] = None  # tlaková mez kluzu [MPa]; None => Re
    Fsu: Optional[float] = None  # mezní smykové napětí [MPa]; None => von Mises z Rm
    source: str = ""             # původ dat / specifikace
    allowables_basis: str = ""   # např. nominal, A-basis, B-basis


@dataclass
class Support:
    id: str
    x: float                 # poloha podél nosníku (mm)
    type: SupportType
    angle: float = 0.0       # natočení rolny (°)
    spring_z: float = 0.0    # tuhost svislé pružiny [N/mm] (typ "spring")
    spring_ry: float = 0.0   # tuhost rotační (ohybové) pružiny [N·mm/rad] (typ "spring")
    settlement: float = 0.0  # předepsaný svislý posun podpory [mm] (kladné = nahoru)
    gap: float = 0.0         # vůle podpory [mm]: uzel volný v ±gap, pak dosedne (kontakt)
    # Explicitní 3D volby. None zachovává historickou sémantiku typu podpory.
    restrain_y: Optional[bool] = None       # vodorovný příčný posun v
    restrain_rz: Optional[bool] = None      # pootočení kolem z
    restrain_torsion: Optional[bool] = None # pootočení kolem x
    restrain_warping: Optional[bool] = None # deplanace θx' (jen Vlasov; None = dle typu)
    spring_y: float = 0.0                   # vodorovná pružina [N/mm]
    spring_rz: float = 0.0                  # pružina kolem z [N·mm/rad]


@dataclass
class Hinge:
    id: str
    x: float                 # poloha kloubu (mm)


@dataclass
class ControlPoint:
    """Kontrolní bod – řez, ve kterém se reportují výsledky (VVÚ, napětí, RF).
    Nemá vliv na výpočet, jen na kartu Výsledky a export."""
    id: str
    x: float                 # poloha řezu (mm)
    name: str = ""           # volitelný popisek


@dataclass
class Load:
    """Univerzální zatížení – pole se interpretují podle `type`."""
    id: str
    type: LoadType
    name: str
    load_case_id: str
    # bodové síly / moment / krut (poloha)
    x: float = 0.0
    Fx: float = 0.0          # osová síla (N)
    Fz: float = 0.0          # příčná síla svislá (N, +nahoru, rovina x-z)
    Fy: float = 0.0          # příčná síla vodorovná (N, rovina x-y) – biaxiál
    eccentricity: float = 0.0  # excentricita -> Mk = Fz·e (mm)
    My: float = 0.0          # ohybový moment kolem osy y (N·mm, rovina x-z)
    Mz: float = 0.0          # ohybový moment kolem osy z (N·mm, rovina x-y) – biaxiál
    Mx: float = 0.0          # kroutící moment (N·mm)
    # spojité
    x1: float = 0.0
    x2: float = 0.0
    q1: float = 0.0          # N/mm (svislé, +nahoru; rovina x–z)
    q2: float = 0.0
    qy1: float = 0.0         # N/mm (vodorovné, +y; rovina x–y) – biaxiál
    qy2: float = 0.0
    # teplotní zatížení (type "thermal"): rovnoměrné ΔT na [x1,x2]
    dT: float = 0.0          # změna teploty [°C] (+ = ohřev) – rovnoměrná složka → osová dilatace
    dT_grad: float = 0.0     # gradient přes výšku [°C]: T(horní vlákno) − T(dolní) → křivost/ohyb


@dataclass
class LoadCase:
    id: str
    name: str
    is_ultimate: bool = False


@dataclass
class LoadCombination:
    id: str
    name: str
    factors: dict = field(default_factory=dict)   # load_case_id -> faktor


@dataclass
class Body:
    """Jedno (vyplněné) těleso v kompozitním průřezu.

    Reprezentace je sjednocená polygon + díry. Vstup typu „střednice + tloušťka"
    se na polygon převede v UI před uložením (offset polyline o ±t/2).
    """
    points: list = field(default_factory=list)   # vnější obrys: [{"y":..,"z":..}, ...]
    holes: list = field(default_factory=list)    # díry: [[{"y":..,"z":..}, ...], ...]
    material_id: Optional[str] = None            # per-těleso materiál (složený PID); None = materiál úseku


@dataclass
class CrossSectionDef:
    type: SectionType = "i_section"
    params: dict = field(default_factory=dict)         # rozměry (mm)
    polygon_points: Optional[list] = None              # [{"y":..,"z":..}, ...] (mm) – vnější obrys (legacy single body)
    polygon_holes: Optional[list] = None               # [[{"y":..,"z":..}, ...], ...] – díry (legacy single body)
    polygon_thickness: Optional[float] = None
    polygon_closed: bool = False
    bodies: Optional[list] = None                      # list[Body] pro kompozit; None = legacy single
    shapes: Optional[list] = None                      # konstrukční tvar: list[dict] primitiv + bool. operací
    id: Optional[str] = None                           # identita v knihovně průřezů (None = zapečený inline)
    name: str = ""                                     # název v knihovně
    rotation: float = 0.0                              # natočení průřezu [°] (kolem těžiště)


@dataclass
class SectionSegment:
    """Úsek nosníku s vlastním průřezem.

    x1, x2  : rozsah úseku (mm)
    sec1    : průřez na začátku úseku (a celý úsek, pokud prizmatický)
    sec2    : průřez na konci úseku → None = prizmatický;
              jinak tapered (náběh) sec1→sec2 (stejný typ, interpolace parametrů)
    """
    x1: float
    x2: float
    sec1: CrossSectionDef = field(default_factory=CrossSectionDef)
    sec2: Optional[CrossSectionDef] = None
    sec1_id: Optional[str] = None      # odkaz na průřez v knihovně; None = zapečený sec1 (inline)
    sec2_id: Optional[str] = None      # odkaz na 2. průřez (náběh); None = zapečený sec2
    E: Optional[float] = None          # přímý modul E (MPa) – override (.nos); None = z materiálu
    material_id: Optional[str] = None  # odkaz na materiál v knihovně; None = globální
    property_id: Optional[str] = None  # odkaz na Property (PID); None = inline (sec1/material_id)
    buckling_mu: float = 1.0           # součinitel vzpěrné délky μ (L_vzpěr = μ·L_úseku)
    # Rozteč skutečných příčných podpor stěny pro lokální boulení [mm]. None =
    # konzervativní dlouhá deska; délka úseku nosníku se za podporu nepovažuje.
    local_buckling_length: Optional[float] = None

    @property
    def tapered(self) -> bool:
        return self.sec2 is not None

    @property
    def length(self) -> float:
        return self.x2 - self.x1


@dataclass
class Property:
    """Vlastnost pod číslem (PID) jako v FEM preprocesoru: pojmenovaná dvojice
    {materiál + průřez (+ náběh)}. Úsek na ni odkazuje přes property_id a sdílí
    ji s ostatními úseky – změna PID se propíše všude."""
    id: str
    pid: int                            # uživatelské číslo
    name: str = ""
    material_id: Optional[str] = None
    sec1: CrossSectionDef = field(default_factory=CrossSectionDef)
    sec2: Optional[CrossSectionDef] = None
    sec1_id: Optional[str] = None       # odkaz na průřez v knihovně; None = zapečený sec1
    sec2_id: Optional[str] = None       # odkaz na 2. průřez (náběh); None = zapečený sec2
    composite_parts: Optional[list] = None  # složený PID: [{section_id, material_id, dy, dz, angle}, …]
    rotation: float = 0.0                    # natočení celého průřezu PID [°]

    @property
    def tapered(self) -> bool:
        return self.sec2 is not None

    @property
    def is_composite(self) -> bool:
        # režim „složené" je zapnutý i s prázdným seznamem (0 profilů) – rozlišuj
        # None (vypnuto) od [] (zapnuto, zatím bez profilů)
        return self.composite_parts is not None


@dataclass
class ProjectState:
    length: float = 2000.0
    supports: list = field(default_factory=list)
    hinges: list = field(default_factory=list)
    control_points: list = field(default_factory=list)   # kontrolní body pro report (neovlivní výpočet)
    load_cases: list = field(default_factory=list)
    load_combinations: list = field(default_factory=list)
    loads: list = field(default_factory=list)
    materials: list = field(default_factory=list)
    selected_material_id: str = ""
    cross_section: CrossSectionDef = field(default_factory=CrossSectionDef)
    section_segments: list = field(default_factory=list)   # prázdné = jeden průřez na celý nosník
    sections: list = field(default_factory=list)           # knihovna pojmenovaných průřezů (CrossSectionDef s id)
    properties: list = field(default_factory=list)         # knihovna PID (Property); úseky na ně mohou odkazovat
    additional_factor: float = 1.0   # násobí jen ne-ULS zatěžovací stavy
    plasticity_enabled: bool = False  # využít součinitel plasticity v RF_ultimate
    plasticity_method: str = "analytic"  # "analytic" | "tabular"
    rf_basis: str = "min"             # řídicí RF: "min" | "yield" (Re) | "ultimate" (Rm)
    sigma_red_mode: str = "exact"     # σ_red: "exact" (skutečné max von Mises po řezu)
                                      #        | "combined" (konzervativní √(σ_max²+3τ_max²))
    tau_mode: str = "conservative"    # skládání smyku: "conservative" (|τ_V|+|τ_t|,
                                      #   Žuravskij – výchozí, jako dosud)
                                      # | "exact" (plné 2D pole Pilkey Ψ/Φ, vektorově;
                                      #   vyžaduje FEM průřezu → build_section(exact=True))
    theory: Theory = "euler-bernoulli"
    torsion_theory: TorsionTheory = "saint-venant"  # výchozí zachovává staré projekty
    selected_active_combination_id: str = ""

    @property
    def variable_section(self) -> bool:
        return bool(self.section_segments)

    def material(self) -> Material:
        for m in self.materials:
            if m.id == self.selected_material_id:
                return m
        return self.materials[0]

    def active_combination(self) -> Optional[LoadCombination]:
        for c in self.load_combinations:
            if c.id == self.selected_active_combination_id:
                return c
        return self.load_combinations[0] if self.load_combinations else None


# ── ID generátor ────────────────────────────────────────────
import itertools
import time
_counter = itertools.count(1)


def new_id(prefix: str = "id") -> str:
    return f"{prefix}_{int(time.time()*1000)}_{next(_counter)}"


def migrate_combinations_to_loads(state) -> None:
    """Jednorázově převede legacy faktor×zatížení na faktor×stav.

    Když mají dvě zatížení původně stejného stavu odlišný vektor faktorů přes
    kombinace, rozdělí se do samostatných automatických stavů. Tím se zachová
    přesná fyzika starého projektu bez nejednoznačného sčítání faktorů.
    Funkce je idempotentní; čistý model faktor×stav pouze zbaví neznámých klíčů.
    """
    loads = getattr(state, "loads", []) or []
    cases = getattr(state, "load_cases", []) or []
    combos = getattr(state, "load_combinations", []) or []
    load_ids = {l.id for l in loads}
    case_ids = {c.id for c in cases}
    has_load_keys = any(any(k in load_ids for k in (c.factors or {})) for c in combos)
    if not has_load_keys:
        for comb in combos:
            comb.factors = {k: float(v) for k, v in (comb.factors or {}).items()
                            if k in case_ids}
        return

    by_case: dict[str, list] = {c.id: [] for c in cases}
    for ld in loads:
        if ld.load_case_id not in by_case:
            auto = LoadCase(ld.load_case_id or new_id("lc"), "Importovaný stav", False)
            cases.append(auto)
            by_case[auto.id] = []
            ld.load_case_id = auto.id
        by_case[ld.load_case_id].append(ld)

    new_cases = []
    case_vectors: dict[str, tuple[float, ...]] = {}
    used_ids = {c.id for c in cases}
    for case in cases:
        members = by_case.get(case.id, [])
        groups: dict[tuple[float, ...], list] = {}
        for ld in members:
            vec = tuple(float((comb.factors or {}).get(
                ld.id, (comb.factors or {}).get(case.id, 0.0))) for comb in combos)
            groups.setdefault(vec, []).append(ld)
        if not groups:
            vec = tuple(float((comb.factors or {}).get(case.id, 0.0)) for comb in combos)
            groups[vec] = []
        for gi, (vec, group) in enumerate(groups.items(), 1):
            if gi == 1:
                target = case
            else:
                base = f"{case.id}__legacy_{gi}"
                cid = base
                suffix = 2
                while cid in used_ids:
                    cid = f"{base}_{suffix}"; suffix += 1
                used_ids.add(cid)
                target = LoadCase(cid, f"{case.name} · část {gi}", case.is_ultimate)
            new_cases.append(target)
            case_vectors[target.id] = vec
            for ld in group:
                ld.load_case_id = target.id
    state.load_cases = new_cases
    for ci, comb in enumerate(combos):
        comb.factors = {cid: vec[ci] for cid, vec in case_vectors.items()}
