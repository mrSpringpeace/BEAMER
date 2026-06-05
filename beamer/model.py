"""Datový model projektu – dataclasses zrcadlící původní TS typy.

Jednotky: délky mm, síly N, momenty N·mm, napětí MPa (=N/mm²),
moduly E,G v MPa, hustota g/cm³.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal, Optional

SupportType = Literal["fixed", "pin", "roller"]
LoadType = Literal["point_force", "moment", "torsion", "distributed"]
SectionType = Literal[
    "rectangle", "box", "circle", "tube",
    "i_section", "c_section", "t_section", "l_section", "u_section",
    "polygon", "direct",
]
Theory = Literal["euler-bernoulli", "timoshenko"]


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


@dataclass
class Support:
    id: str
    x: float                 # poloha podél nosníku (mm)
    type: SupportType
    angle: float = 0.0       # natočení rolny (°)


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
    Fz: float = 0.0          # příčná síla (N, +nahoru)
    eccentricity: float = 0.0  # excentricita -> Mk = Fz·e (mm)
    My: float = 0.0          # ohybový moment (N·mm)
    Mx: float = 0.0          # kroutící moment (N·mm)
    # spojité
    x1: float = 0.0
    x2: float = 0.0
    q1: float = 0.0          # N/mm (svislé, +nahoru)
    q2: float = 0.0


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


@dataclass
class CrossSectionDef:
    type: SectionType = "i_section"
    params: dict = field(default_factory=dict)         # rozměry (mm)
    polygon_points: Optional[list] = None              # [{"y":..,"z":..}, ...] (mm) – vnější obrys (legacy single body)
    polygon_holes: Optional[list] = None               # [[{"y":..,"z":..}, ...], ...] – díry (legacy single body)
    polygon_thickness: Optional[float] = None
    polygon_closed: bool = False
    bodies: Optional[list] = None                      # list[Body] pro kompozit; None = legacy single


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
    E: Optional[float] = None          # přímý modul E (MPa) – override (.nos); None = z materiálu
    material_id: Optional[str] = None  # odkaz na materiál v knihovně; None = globální

    @property
    def tapered(self) -> bool:
        return self.sec2 is not None

    @property
    def length(self) -> float:
        return self.x2 - self.x1


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
    additional_factor: float = 1.0   # dodatečný součinitel – násobí zatížení (ultimate síly)
    plasticity_enabled: bool = False  # využít součinitel plasticity v RF_ultimate
    plasticity_method: str = "analytic"  # "analytic" | "tabular"
    theory: Theory = "euler-bernoulli"
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
