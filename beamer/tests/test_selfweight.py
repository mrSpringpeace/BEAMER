"""Vlastní tíha nosníku (Load type "self_weight", q = −ρ·A(x)·g)."""
from __future__ import annotations

import pytest

from beamer.defaults import create_default_state
from beamer.model import (
    CrossSectionDef, Load, LoadCombination, Material, SectionSegment, Support,
)
from beamer.project_io import dict_to_state, state_to_dict
from beamer.selfweight import G_STD, expanded_loads, summary
from beamer.solver import solve_beam

RHO = 7.85                       # g/cm³ (ocel)


def _state(segments, loads_factor=1.0):
    st = create_default_state()
    mat = Material("steel", "Ocel", 210000, 81000, 0.3, RHO, 355, 510)
    st.materials = [mat]
    st.selected_material_id = mat.id
    st.section_segments = segments
    st.length = segments[-1].x2
    st.cross_section = segments[0].sec1
    st.supports = [Support("a", 0, "pin"), Support("b", st.length, "roller")]
    lc = st.load_cases[0].id
    st.loads = [Load("sw", "self_weight", "G", lc, x1=0.0, x2=st.length)]
    st.load_combinations = [LoadCombination("c", "C", {lc: loads_factor})]
    st.selected_active_combination_id = "c"
    return st


def _rect(b, h):
    return CrossSectionDef(type="rectangle", params={"b": b, "h": h})


def test_prismatic_self_weight_matches_rho_a_g():
    L, A = 2000.0, 20 * 100
    st = _state([SectionSegment(0, L, _rect(20, 100))])
    q = RHO * 1e-6 * A * G_STD                       # N/mm
    M, W = summary(st, st.loads[0])
    assert M == pytest.approx(RHO * 1e-6 * A * L, rel=1e-12)
    assert W == pytest.approx(q * L, rel=1e-12)

    r = solve_beam(st)
    assert r.is_stable
    assert sum(rc.Rz for rc in r.reactions) == pytest.approx(q * L, rel=1e-9)
    assert max(abs(p.M) for p in r.points) == pytest.approx(q * L**2 / 8, rel=5e-3)


def test_self_weight_scales_with_load_case_factor():
    L = 1500.0
    st = _state([SectionSegment(0, L, _rect(30, 60))], loads_factor=3.0)
    W = summary(st, st.loads[0])[1]
    r = solve_beam(st)
    assert sum(rc.Rz for rc in r.reactions) == pytest.approx(3.0 * W, rel=1e-9)


def test_segments_and_partial_range():
    st = _state([SectionSegment(0, 1000, _rect(20, 100)),
                 SectionSegment(1000, 2000, _rect(40, 100))])
    st.loads[0].x1, st.loads[0].x2 = 500.0, 1500.0
    M, _ = summary(st, st.loads[0])
    assert M == pytest.approx(RHO * 1e-6 * (2000 * 500 + 4000 * 500), rel=1e-12)
    parts = [d for d in expanded_loads(st) if d.type == "distributed"]
    assert [(d.x1, d.x2) for d in parts] == [(500.0, 1000.0), (1000.0, 1500.0)]


def test_tapered_segment_mass_close_to_exact_volume():
    # b konstantní, h 100 → 200 lineárně: přesný objem = b·(h1+h2)/2·L
    seg = SectionSegment(0, 1000, _rect(20, 100), sec2=_rect(20, 200))
    st = _state([seg])
    M, _ = summary(st, st.loads[0])
    assert M == pytest.approx(RHO * 1e-6 * 20 * 150 * 1000, rel=1e-6)


def test_follows_material_density_change_and_roundtrips():
    st = _state([SectionSegment(0, 1000, _rect(20, 100))])
    m1 = summary(st, st.loads[0])[0]
    st.materials[0].rho = 2.70                   # hliník
    assert summary(st, st.loads[0])[0] == pytest.approx(m1 * 2.70 / RHO)

    st2 = dict_to_state(state_to_dict(st))
    assert st2.loads[0].type == "self_weight"
    assert summary(st2, st2.loads[0])[0] == pytest.approx(m1 * 2.70 / RHO)


def test_composite_pid_sums_part_densities():
    from beamer.model import Property
    st = _state([SectionSegment(0, 1000, _rect(20, 100))])
    st.materials.append(Material("al", "Al", 70000, 27000, 0.33, 2.70, 300, 400))
    st.sections = [
        CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}, id="s1", name="R1"),
        CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}, id="s2", name="R2"),
    ]
    st.properties = [Property(id="p", pid=1, name="sendvič", composite_parts=[
        {"section_id": "s1", "material_id": "steel", "dy": 0, "dz": 30, "angle": 0},
        {"section_id": "s2", "material_id": "al", "dy": 0, "dz": -30, "angle": 0},
    ])]
    st.section_segments[0].property_id = "p"
    M, _ = summary(st, st.loads[0])
    assert M == pytest.approx((RHO + 2.70) * 1e-6 * 800 * 1000, rel=1e-12)
