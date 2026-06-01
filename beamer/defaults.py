"""Knihovna materiálů a výchozí stav projektu."""
from __future__ import annotations

import copy as _copy

from .model import (
    Material, Support, Hinge, Load, LoadCase, LoadCombination,
    CrossSectionDef, SectionSegment, ProjectState,
)

MATERIAL_LIBRARY = [
    Material("mat_al2024", "Al 2024-T3", 73100, 28000, 0.33, 2.78, 345, 483),
    Material("mat_al7075", "Al 7075-T6", 71700, 26900, 0.33, 2.81, 503, 572),
    Material("mat_al6061", "Al 6061-T6", 68900, 26000, 0.33, 2.70, 276, 310),
    Material("mat_ti6al4v", "Ti-6Al-4V", 113800, 44000, 0.342, 4.43, 828, 896),
    Material("mat_4130", "Ocel 4130", 200000, 77000, 0.29, 7.83, 435, 670),
]


def create_empty_state() -> ProjectState:
    """Prázdná úloha – bez podpor, kloubů a zatížení (pro start a Soubor→Nový).
    Materiály, jeden zatěžovací stav/kombinace a výchozí průřez zůstávají,
    aby uživatel mohl rovnou přidávat prvky."""
    LC = "lc_1"
    COMB = "comb_1"
    isec = CrossSectionDef(type="i_section",
                           params={"h": 120, "tw": 5, "bf1": 80, "tf1": 8, "bf2": 80, "tf2": 8})
    return ProjectState(
        length=1000,
        supports=[],
        hinges=[],
        load_cases=[LoadCase(LC, "LC1 – Provozní", False)],
        load_combinations=[LoadCombination(COMB, "Kombi 1", {LC: 1.0})],
        loads=[],
        materials=[Material(**vars(m)) for m in MATERIAL_LIBRARY],
        selected_material_id="mat_al2024",
        cross_section=_copy.deepcopy(isec),
        section_segments=[SectionSegment(0.0, 1000.0, _copy.deepcopy(isec), None,
                                         material_id="mat_al2024")],
        additional_factor=1.0,
        theory="euler-bernoulli",
        selected_active_combination_id=COMB,
    )


def create_default_state() -> ProjectState:
    LC = "lc_1"
    COMB = "comb_1"
    isec = CrossSectionDef(type="i_section",
                           params={"h": 120, "tw": 5, "bf1": 80, "tf1": 8, "bf2": 80, "tf2": 8})
    return ProjectState(
        length=2000,
        supports=[
            Support("sup_A", 0, "pin", 0),
            Support("sup_B", 2000, "roller", 0),
        ],
        hinges=[],
        load_cases=[LoadCase(LC, "LC1 – Provozní", False)],
        load_combinations=[LoadCombination(COMB, "Kombi 1", {LC: 1.0})],
        loads=[
            Load("load_q1", "distributed", "Spojité zatížení", LC,
                 x1=0, x2=2000, q1=-1.0, q2=-1.0),
        ],
        materials=[Material(**vars(m)) for m in MATERIAL_LIBRARY],
        selected_material_id="mat_al2024",
        cross_section=_copy.deepcopy(isec),
        section_segments=[SectionSegment(0.0, 2000.0, _copy.deepcopy(isec), None,
                                         material_id="mat_al2024")],
        additional_factor=1.0,
        theory="euler-bernoulli",
        selected_active_combination_id=COMB,
    )


def ensure_parts(state: ProjectState):
    """Migrace: nemá-li projekt úseky, vytvoří jeden úsek z cross_section +
    globálního materiálu pokrývající celý nosník."""
    if not state.section_segments:
        state.section_segments = [SectionSegment(
            0.0, float(state.length), _copy.deepcopy(state.cross_section), None,
            material_id=state.selected_material_id or (state.materials[0].id if state.materials else None))]
    return state
