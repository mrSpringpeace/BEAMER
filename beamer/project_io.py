"""Uložení / načtení projektu jako JSON."""
from __future__ import annotations

import json
from dataclasses import asdict

from .model import (
    Material, Support, Hinge, Load, LoadCase, LoadCombination,
    CrossSectionDef, SectionSegment, ProjectState, Body,
)


def state_to_dict(state: ProjectState) -> dict:
    return {
        "length": state.length,
        "supports": [asdict(s) for s in state.supports],
        "hinges": [asdict(h) for h in state.hinges],
        "load_cases": [asdict(c) for c in state.load_cases],
        "load_combinations": [asdict(c) for c in state.load_combinations],
        "loads": [asdict(l) for l in state.loads],
        "materials": [asdict(m) for m in state.materials],
        "selected_material_id": state.selected_material_id,
        "cross_section": asdict(state.cross_section),
        "section_segments": [asdict(s) for s in state.section_segments],
        "additional_factor": state.additional_factor,
        "plasticity_enabled": state.plasticity_enabled,
        "plasticity_method": state.plasticity_method,
        "theory": state.theory,
        "selected_active_combination_id": state.selected_active_combination_id,
    }


def _csdef(d):
    if d is None:
        return None
    bodies_raw = d.get("bodies")
    bodies = None
    if bodies_raw:
        bodies = [
            Body(
                points=list(b.get("points") or []),
                holes=list(b.get("holes") or []),
            )
            for b in bodies_raw
        ]
    return CrossSectionDef(
        type=d.get("type", "i_section"),
        params=d.get("params", {}),
        polygon_points=d.get("polygon_points"),
        polygon_holes=d.get("polygon_holes"),
        polygon_thickness=d.get("polygon_thickness"),
        polygon_closed=d.get("polygon_closed", False),
        bodies=bodies,
    )


def dict_to_state(d: dict) -> ProjectState:
    cs = d.get("cross_section", {})
    return ProjectState(
        length=d.get("length", 2000),
        supports=[Support(**s) for s in d.get("supports", [])],
        hinges=[Hinge(**h) for h in d.get("hinges", [])],
        load_cases=[LoadCase(**c) for c in d.get("load_cases", [])],
        load_combinations=[LoadCombination(**c) for c in d.get("load_combinations", [])],
        loads=[Load(**l) for l in d.get("loads", [])],
        materials=[Material(**m) for m in d.get("materials", [])],
        selected_material_id=d.get("selected_material_id", ""),
        cross_section=_csdef(cs),
        section_segments=[
            SectionSegment(
                x1=s.get("x1", 0), x2=s.get("x2", 0),
                sec1=_csdef(s.get("sec1")), sec2=_csdef(s.get("sec2")),
                E=s.get("E"), material_id=s.get("material_id"),
            ) for s in d.get("section_segments", [])
        ],
        additional_factor=d.get("additional_factor",
                                 d.get("fitting_factor", 1.0)),  # zpětná kompat.
        plasticity_enabled=d.get("plasticity_enabled", False),
        plasticity_method=d.get("plasticity_method", "analytic"),
        theory=d.get("theory", "euler-bernoulli"),
        selected_active_combination_id=d.get("selected_active_combination_id", ""),
    )


def save_project(state: ProjectState, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state_to_dict(state), f, ensure_ascii=False, indent=2)


def load_project(path: str) -> ProjectState:
    with open(path, "r", encoding="utf-8") as f:
        return dict_to_state(json.load(f))
