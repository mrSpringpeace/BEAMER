"""Regrese chyb nalezených při úplném auditu BEAMERu (2026-07).

Tyto testy cílí na fyzikální invarianty a mezní případy, které původní sada
nepokrývala. Nejsou to golden hodnoty současné implementace.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from beamer.analysis import (
    _assess,
    buckling_check,
    build_influence,
    max_stresses_fast,
    reserves_along_beam,
    values_at_x,
)
from beamer.defaults import MATERIAL_LIBRARY
from beamer.model import (
    CrossSectionDef,
    Hinge,
    Load,
    LoadCase,
    LoadCombination,
    Material,
    ProjectState,
    Property,
    SectionSegment,
    Support,
)
from beamer.project_io import (
    PROJECT_FORMAT_VERSION,
    dict_to_state,
    state_to_dict,
)
from beamer.section import build_section
from beamer.solver import solve_beam


MAT = Material(
    "m", "Steel", E=210000.0, G=81000.0, nu=0.3, rho=7.85,
    Re=235.0, Rm=360.0, alpha=12e-6,
)


def test_project_format_is_versioned_and_rejects_newer_schema():
    payload = state_to_dict(ProjectState())
    assert payload["format_version"] == PROJECT_FORMAT_VERSION
    payload["format_version"] += 1
    with pytest.raises(ValueError, match="novější formát"):
        dict_to_state(payload)


def _state(length, supports, loads, section=None, hinges=None):
    section = section or CrossSectionDef(type="rectangle", params={"b": 40, "h": 80})
    return ProjectState(
        length=length,
        materials=[MAT],
        selected_material_id="m",
        cross_section=section,
        section_segments=[SectionSegment(0.0, length, section, None)],
        supports=supports,
        hinges=hinges or [],
        load_cases=[LoadCase("lc", "LC")],
        loads=loads,
        load_combinations=[LoadCombination(
            id="c", name="c", factors={load.id: 1.0 for load in loads}
        )],
        additional_factor=1.0,
    )


def test_unrestrained_loaded_axial_and_torsion_modes_are_unstable():
    """Referenční fixace rigidního módu nesmí vytvořit fyzickou reakci."""
    supports = [Support("a", 0.0, "roller"), Support("b", 1000.0, "roller")]
    torsion = Load("t", "torsion", "T", "lc", x=500.0, Mx=100000.0)
    axial = Load("f", "point_force", "N", "lc", x=500.0, Fx=1000.0)
    assert not solve_beam(_state(1000.0, supports, [torsion])).is_stable
    assert not solve_beam(_state(1000.0, supports, [axial])).is_stable


def test_hinge_distributed_load_vector_is_condensed():
    """Gerberův nosník: krátké pravé pole nesmí záviset na globálním zahuštění."""
    length, hinge_x, q = 10000.0, 9900.0, -1.0
    load = Load("q", "distributed", "q", "lc", x1=hinge_x, x2=length, q1=q, q2=q)
    state = _state(
        length,
        [Support("a", 0.0, "fixed"), Support("b", length, "roller")],
        [load],
        hinges=[Hinge("h", hinge_x)],
    )
    result = solve_beam(state)
    assert result.is_stable
    reactions = sorted(result.reactions, key=lambda reaction: reaction.x)
    expected_end_reaction = abs(q) * (length - hinge_x) / 2.0
    assert math.isclose(reactions[0].Rz, expected_end_reaction, rel_tol=1e-8, abs_tol=1e-6)
    assert math.isclose(reactions[1].Rz, expected_end_reaction, rel_tol=1e-8, abs_tol=1e-6)
    assert math.isclose(
        reactions[0].Ry, expected_end_reaction * hinge_x, rel_tol=1e-8, abs_tol=1e-4
    )
    hinge_moment = min(result.points, key=lambda point: abs(point.x - hinge_x)).M
    assert abs(hinge_moment) < 1e-5


def test_buckling_uses_principal_minimum_inertia_for_rotated_section():
    section = CrossSectionDef(
        type="rectangle", params={"b": 40.0, "h": 80.0}, rotation=45.0
    )
    length, compression = 2000.0, 50000.0
    load = Load("n", "point_force", "N", "lc", x=length, Fx=-compression)
    state = _state(
        length,
        [Support("a", 0.0, "pin"), Support("b", length, "roller")],
        [load],
        section=section,
    )
    result = solve_beam(state)
    check = buckling_check(state, result)
    assert check is not None
    built = build_section(section, fem=False)
    principal_min = min(built.I1, built.I2)
    expected = math.pi**2 * MAT.E * principal_min / length**2
    assert math.isclose(check.rows[0]["P_cr"], expected, rel_tol=1e-6)


def test_plastic_shape_factor_does_not_increase_axial_or_shear_capacity():
    section = build_section(
        CrossSectionDef(type="rectangle", params={"b": 40.0, "h": 80.0}), fem=False
    )
    state = ProjectState(
        materials=[MAT], selected_material_id="m", rf_basis="ultimate",
        plasticity_enabled=False,
    )
    axial_off = _assess(section, MAT, state, N=100000.0, V=0.0, M=0.0, Mk=0.0)
    shear_off = _assess(section, MAT, state, N=0.0, V=100000.0, M=0.0, Mk=0.0)
    state.plasticity_enabled = True
    axial_on = _assess(section, MAT, state, N=100000.0, V=0.0, M=0.0, Mk=0.0)
    shear_on = _assess(section, MAT, state, N=0.0, V=100000.0, M=0.0, Mk=0.0)
    assert axial_on["RF_ultimate"] == axial_off["RF_ultimate"]
    assert shear_on["RF_ultimate"] == shear_off["RF_ultimate"]


def test_combined_transverse_shear_and_torsion_is_sign_invariant():
    section = build_section(
        CrossSectionDef(type="rectangle", params={"b": 40.0, "h": 80.0}), fem=False
    )
    influence = build_influence(section, n=601)
    shear = 10000.0
    centre = int(np.argmin(np.abs(influence.z_mm)))
    torque_nm = shear * influence.c_tV[centre] / influence.c_tT[centre]
    torque_nmm = torque_nm * 1000.0
    positive = max_stresses_fast(influence, 0.0, shear, 0.0, torque_nmm)
    negative = max_stresses_fast(influence, 0.0, shear, 0.0, -torque_nmm)
    assert math.isclose(positive[1], negative[1], rel_tol=1e-9)
    assert math.isclose(positive[2], negative[2], rel_tol=1e-9)


def test_horizontal_shear_is_included_in_section_assessment():
    load = Load("fy", "point_force", "Fy", "lc", x=500.0, Fy=-10000.0)
    state = _state(
        1000.0,
        [Support("a", 0.0, "pin"), Support("b", 1000.0, "roller")],
        [load],
    )
    result = solve_beam(state)
    assessment = values_at_x(result, state, 0.0)
    point = min(result.points, key=lambda item: item.x)
    expected = 1.5 * abs(point.V_y) / (40.0 * 80.0)
    assert assessment is not None
    assert math.isclose(assessment["tau_max"], expected, rel_tol=5e-3)
    assert math.isfinite(assessment["RF"])


def test_predefined_materials_have_explicit_thermal_expansion():
    by_id = {material.id: material for material in MATERIAL_LIBRARY}
    assert math.isclose(by_id["mat_al2024"].alpha, 23.2e-6, rel_tol=0.03)
    assert math.isclose(by_id["mat_al7075"].alpha, 23.6e-6, rel_tol=0.03)
    assert math.isclose(by_id["mat_al6061"].alpha, 23.6e-6, rel_tol=0.03)
    assert math.isclose(by_id["mat_ti6al4v"].alpha, 8.6e-6, rel_tol=0.05)
    assert math.isclose(by_id["mat_4130"].alpha, 11.7e-6, rel_tol=0.05)


def test_horizontal_and_torsional_support_constraints_are_explicit():
    load_y = Load("fy", "point_force", "Fy", "lc", x=1000.0, Fy=-1000.0)
    free_y = Support("a", 0.0, "fixed", restrain_y=False, restrain_rz=False)
    assert not solve_beam(_state(1000.0, [free_y], [load_y])).is_stable
    vertical = Load("fz", "point_force", "Fz", "lc", x=1000.0, Fz=-1000.0)
    assert solve_beam(_state(1000.0, [free_y], [vertical])).is_stable

    held_y = Support("a", 0.0, "fixed", restrain_y=True, restrain_rz=True)
    assert solve_beam(_state(1000.0, [held_y], [load_y])).is_stable

    torque = Load("t", "torsion", "T", "lc", x=1000.0, Mx=10000.0)
    free_t = Support("a", 0.0, "fixed", restrain_torsion=False)
    assert not solve_beam(_state(1000.0, [free_t], [torque])).is_stable


def test_composite_thermal_gradient_integrates_each_material_alpha():
    from beamer.composite import composite_weighted

    steel = MAT
    aluminium = Material(
        "al", "Al", E=70000.0, G=27000.0, nu=0.33, rho=2.7,
        Re=200.0, Rm=300.0, alpha=23e-6,
    )
    layer = CrossSectionDef(
        id="layer", name="layer", type="rectangle", params={"b": 40.0, "h": 20.0}
    )
    prop = Property(id="p", pid=1, composite_parts=[
        {"section_id": "layer", "material_id": "m", "dy": 0.0, "dz": 10.0,
         "angle": 0.0},
        {"section_id": "layer", "material_id": "al", "dy": 0.0, "dz": -10.0,
         "angle": 0.0},
    ])
    length = 1000.0
    thermal = Load(
        "tg", "thermal", "gradient", "lc", x1=0.0, x2=length, dT_grad=40.0
    )
    state = ProjectState(
        length=length,
        supports=[Support("a", 0.0, "fixed"), Support("b", length, "fixed")],
        loads=[thermal], load_cases=[LoadCase("lc", "LC")],
        load_combinations=[LoadCombination("c", "C", {"tg": 1.0})],
        materials=[steel, aluminium], selected_material_id="m",
        sections=[layer], properties=[prop],
        section_segments=[SectionSegment(
            0.0, length, CrossSectionDef(), None, property_id="p"
        )],
        selected_active_combination_id="c", additional_factor=1.0,
    )
    weighted = composite_weighted(state, prop)
    assert weighted is not None
    # Celková výška je 40 mm a geometrický střed leží v z=0.
    grad = thermal.dT_grad / 40.0
    expected_n = grad * (
        weighted.ESalpha + weighted.z_NA * weighted.EAalpha
    )
    expected_m = grad * (
        weighted.EIalpha + weighted.z_NA * weighted.ESalpha
    )
    result = solve_beam(state)
    assert result.is_stable
    middle = min(result.points, key=lambda point: abs(point.x - length/2.0))
    assert math.isclose(middle.N, -expected_n, rel_tol=1e-8, abs_tol=1e-5)
    assert math.isclose(middle.M, -expected_m, rel_tol=1e-8, abs_tol=1e-4)


def test_composite_buckling_uses_e_weighted_principal_stiffness():
    from beamer.composite import composite_weighted

    aluminium = Material(
        "al", "Al", E=70000.0, G=27000.0, nu=0.33, rho=2.7,
        Re=200.0, Rm=300.0, alpha=23e-6,
    )
    layer = CrossSectionDef(
        id="layer", name="layer", type="rectangle", params={"b": 20.0, "h": 20.0}
    )
    prop = Property(id="p", pid=1, composite_parts=[
        {"section_id": "layer", "material_id": "m", "dy": -10.0, "dz": 0.0,
         "angle": 0.0},
        {"section_id": "layer", "material_id": "al", "dy": 10.0, "dz": 0.0,
         "angle": 0.0},
    ])
    length = 5000.0
    compression = Load("n", "point_force", "N", "lc", x=length, Fx=-1000.0)
    state = ProjectState(
        length=length,
        supports=[Support("a", 0.0, "pin"), Support("b", length, "roller")],
        loads=[compression], load_cases=[LoadCase("lc", "LC")],
        load_combinations=[LoadCombination("c", "C", {"n": 1.0})],
        materials=[MAT, aluminium], selected_material_id="m",
        sections=[layer], properties=[prop],
        section_segments=[SectionSegment(
            0.0, length, CrossSectionDef(), None, property_id="p"
        )],
        selected_active_combination_id="c", additional_factor=1.0,
    )
    weighted = composite_weighted(state, prop)
    assert weighted is not None
    expected_ei = 0.5*(weighted.EIy + weighted.EIz) - math.sqrt(
        (0.5*(weighted.EIy-weighted.EIz))**2 + weighted.EIyz**2
    )
    result = solve_beam(state)
    check = buckling_check(state, result)
    assert check is not None
    expected = math.pi**2 * expected_ei / length**2
    assert math.isclose(check.rows[0]["P_cr"], expected, rel_tol=1e-6)


def test_nos_direct_iy_import_is_stiffness_only_not_fabricated_strength():
    from beamer.nos_io import nos_to_state

    state = nos_to_state({
        "type": 1, "L": 1000.0,
        "segments": [[2.0e6, 2.0e6, 210000.0, 1000.0]],
        "supports": [[0.0, 0.0], [0.0, 1000.0]],
        "forces": [[-1000.0, 500.0]], "moments": [], "distributed": [],
    })
    result = solve_beam(state)
    assert result.is_stable
    assessment = values_at_x(result, state, 500.0)
    assert assessment is not None
    assert assessment["assessment_available"] is False
    assert assessment["RF"] is None
    assert reserves_along_beam(result, state) == []
    assert buckling_check(state, result) is None


def test_ultimate_load_case_is_not_factored_twice():
    from beamer.solver import _load_multiplier

    load = Load("p", "point_force", "P", "lc", x=100.0, Fz=-100.0)
    state = _state(1000.0, [Support("a", 0.0, "fixed")], [load])
    state.additional_factor = 1.5
    state.load_cases[0].is_ultimate = False
    assert _load_multiplier(state, load) == 1.5
    state.load_cases[0].is_ultimate = True
    assert _load_multiplier(state, load) == 1.0
