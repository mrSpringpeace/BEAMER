"""Regrese klasické deskové stability a topologie parametrických profilů."""
import math
from types import SimpleNamespace

import pytest

from beamer.local_stability import (
    assess_local_stability,
    elastic_plate_buckling_stress,
    gerard_stiffened_panel_stress,
    needham_crippling_stress,
    plate_buckling_coefficient,
)
from beamer.analysis import _assess, reserves_along_beam
from beamer.model import (
    CrossSectionDef,
    Load,
    LoadCase,
    LoadCombination,
    Material,
    ProjectState,
    SectionSegment,
    Support,
)
from beamer.report import build_report
from beamer.project_io import dict_to_state, state_to_dict
from beamer.section import build_section
from beamer.solver import solve_beam


def test_supported_plate_navier_coefficient_respects_aspect_ratio():
    assert plate_buckling_coefficient("supported_supported", 1.0) == pytest.approx(4.0)
    assert plate_buckling_coefficient("supported_supported", 0.5) == pytest.approx(6.25)
    assert plate_buckling_coefficient("supported_supported", 10.0) == pytest.approx(4.0)


def test_outstand_plate_reaches_classical_long_plate_limit():
    # Konečné poměry kontrolují vlastní řešení (NASA TM-108399, obr. 11),
    # nikoli pouze asymptotickou větev.
    assert plate_buckling_coefficient("supported_free", 1.0, 0.33) == pytest.approx(
        1.37958, rel=2e-5,
    )
    assert plate_buckling_coefficient("supported_free", 2.0, 0.33) == pytest.approx(
        0.64933, rel=2e-5,
    )
    assert plate_buckling_coefficient("supported_free", 5.0, 0.33) == pytest.approx(
        0.44594, rel=2e-4,
    )
    assert plate_buckling_coefficient("supported_free", 20.0, 0.33) == pytest.approx(0.425)


def test_local_plate_formula_matches_nasa_worked_example():
    # NASA TM-108399, worked example: outstanding flange, t=.125 in,
    # b=.625 in, E=10.8e6 psi, nu=.33, k=.43 -> 171452 psi.
    sigma = 0.43 * math.pi**2 * 10.8e6 / (12.0*(1.0-0.33**2)) * (0.125/0.625)**2
    assert sigma == pytest.approx(171452.0, rel=2e-4)
    # API používá klasický nekonečně dlouhý limit k=0.425.
    actual = elastic_plate_buckling_stress(
        10.8e6, 0.33, 0.125, 0.625, 20.0,
        "supported_free",
    )
    assert actual == pytest.approx(sigma * 0.425/0.43, rel=1e-10)


def test_needham_uses_edge_coefficient_and_rejects_nonuniform_thickness():
    cs = build_section(CrossSectionDef(
        type="l_section", params={"h": 2.0, "b": 2.0, "t": 0.125},
    ), fem=False)
    actual = needham_crippling_stress(10.8e6, 51_000.0, cs.local_walls)
    b_prime = (1.875 + 1.875)/2.0
    expected = 0.316*math.sqrt(51_000.0*10.8e6)/(b_prime/0.125)**0.75
    assert actual == pytest.approx(expected)

    unequal = build_section(CrossSectionDef(
        type="i_section", params={"h": 4, "bf1": 2, "bf2": 2,
                                  "tw": .1, "tf1": .12, "tf2": .1},
    ), fem=False)
    assert needham_crippling_stress(10.8e6, 51_000.0, unequal.local_walls) is None


def test_gerard_general_equation_reproduces_nasa_worked_example():
    actual = gerard_stiffened_panel_stress(
        E=10.8e6, Fcy=51_000.0, area=0.8183, t_average=0.1257,
        t_skin=0.1318, g=7.0, beta=0.5346, exponent=0.85,
    )
    # NASA TM-108399 worked result 50,463.89 psi; printed inputs jsou zaokrouhlené.
    assert actual == pytest.approx(50_463.89, rel=5e-4)


@pytest.mark.parametrize(
    "section_type,params,count,conditions",
    [
        ("i_section", {"h": 200, "bf1": 100, "bf2": 80, "tw": 6,
                       "tf1": 10, "tf2": 8}, 5,
         ["supported_supported"] + ["supported_free"]*4),
        ("t_section", {"h": 120, "b": 80, "tw": 5, "tf": 8}, 3,
         ["supported_free"]*3),
        ("l_section", {"h": 100, "b": 70, "t": 6}, 2,
         ["supported_free"]*2),
        ("u_section", {"h": 100, "b": 70, "t": 6}, 3,
         ["supported_supported", "supported_free", "supported_free"]),
        ("box", {"H": 100, "B": 70, "tw": 6}, 4,
         ["supported_supported"]*4),
    ],
)
def test_known_parametric_profiles_expose_authoritative_walls(
        section_type, params, count, conditions):
    cs = build_section(CrossSectionDef(type=section_type, params=params), fem=False)
    assert len(cs.local_walls) == count
    assert [wall.edge_condition for wall in cs.local_walls] == conditions
    assert all(wall.width > 0 and wall.thickness > 0 for wall in cs.local_walls)
    assert cs.local_stability_note == ""


def test_wall_coordinates_follow_section_rotation_about_centroid():
    base = build_section(CrossSectionDef(
        type="l_section", params={"h": 100, "b": 70, "t": 6}, rotation=0.0,
    ), fem=False)
    rotated = build_section(CrossSectionDef(
        type="l_section", params={"h": 100, "b": 70, "t": 6}, rotation=90.0,
    ), fem=False)
    for before, after in zip(base.local_walls, rotated.local_walls):
        assert after.start_y == pytest.approx(-before.start_z)
        assert after.start_z == pytest.approx(before.start_y)
        assert after.end_y == pytest.approx(-before.end_z)
        assert after.end_z == pytest.approx(before.end_y)


@pytest.mark.parametrize("section_type", ["rectangle", "circle", "tube", "polygon"])
def test_unknown_or_non_plate_topology_is_explicitly_unavailable(section_type):
    if section_type == "polygon":
        sdef = CrossSectionDef(type=section_type, polygon_points=[
            {"y": 0, "z": 0}, {"y": 20, "z": 0}, {"y": 0, "z": 20},
        ])
    else:
        sdef = CrossSectionDef(type=section_type)
    cs = build_section(sdef, fem=False)
    assert cs.local_walls == []
    assert "není" in cs.local_stability_note


def _aluminium():
    return Material("al", "Al", E=72_000.0, G=27_000.0, nu=0.33, rho=2.8,
                    Re=280.0, Rm=440.0, Fcy=270.0)


def _assessment_state(length=500.0):
    return SimpleNamespace(
        length=length, rf_basis="min", sigma_red_mode="exact",
        plasticity_enabled=False, tau_mode="conservative",
        torsion_theory="saint-venant",
    )


def test_wall_specific_compression_makes_local_buckling_govern_over_yield():
    cs = build_section(CrossSectionDef(
        type="i_section", params={"h": 100, "bf1": 80, "bf2": 80,
                                  "tw": 2, "tf1": 2, "tf2": 2},
    ), fem=False)
    mat = _aluminium()
    compression = 100.0
    local = assess_local_stability(
        cs, mat, 500.0, N=-compression*cs.A, M=0.0,
    )
    assert local.RF_local_buckling is not None
    assert local.RF_local_buckling < mat.Re/compression
    assert local.critical_wall.startswith("horní pásnice")

    assessed = _assess(
        cs, mat, _assessment_state(), -compression*cs.A, 0.0, 0.0, 0.0,
        seg=SimpleNamespace(length=500.0, local_buckling_length=500.0,
                            property_id=None),
    )
    expected = min(local.RF_local_buckling, local.RF_crippling)
    assert assessed["RF"] == pytest.approx(expected)
    assert assessed["critical"] in ("local_buckling", "crippling")


def test_tension_has_no_local_stability_rf():
    cs = build_section(CrossSectionDef(
        type="l_section", params={"h": 100, "b": 70, "t": 3},
    ), fem=False)
    local = assess_local_stability(cs, _aluminium(), 500.0,
                                   N=80.0*cs.A, M=0.0)
    assert local.RF_local_buckling is None
    assert local.RF_crippling is None


def test_thick_wall_does_not_apply_empirical_crippling_outside_domain():
    cs = build_section(CrossSectionDef(
        type="l_section", params={"h": 50, "b": 40, "t": 8},
    ), fem=False)
    mat = _aluminium()
    local = assess_local_stability(cs, mat, 200.0, N=-100.0*cs.A, M=0.0)
    assert local.RF_crippling is None
    assert local.RF_local_buckling == pytest.approx(mat.Fcy/100.0)


def test_axial_beam_pipeline_and_text_report_expose_local_modes():
    length = 500.0
    sdef = CrossSectionDef(
        type="i_section", params={"h": 100, "bf1": 80, "bf2": 80,
                                  "tw": 2, "tf1": 2, "tf2": 2},
    )
    mat = _aluminium()
    cs = build_section(sdef, fem=False)
    load = Load("p", "point_force", "tlak", "lc", x=length,
                Fx=-100.0*cs.A)
    state = ProjectState(
        length=length, supports=[Support("s", 0.0, "fixed")],
        loads=[load], load_cases=[LoadCase("lc", "LC")],
        load_combinations=[LoadCombination("comb", "COMB", {"lc": 1.0})],
        selected_active_combination_id="comb", materials=[mat],
        selected_material_id=mat.id, cross_section=sdef,
        section_segments=[SectionSegment(0.0, length, sdef, material_id=mat.id)],
    )
    result = solve_beam(state)
    margins = reserves_along_beam(result, state, n_stations=8)
    assert result.is_stable and margins
    critical = min(margins, key=lambda row: row.RF)
    assert critical.critical in ("local_buckling", "crippling")
    assert critical.RF_local_buckling is not None
    assert critical.RF_crippling is not None
    report = build_report(state, result, margins)
    assert "RF_local" in report
    assert "RF_crippling" in report
    assert "Needham/Gerard" in report


def test_finite_plate_length_is_explicit_and_roundtrips():
    sdef = CrossSectionDef(
        type="l_section", params={"h": 100, "b": 70, "t": 3},
    )
    mat = _aluminium()
    cs = build_section(sdef, fem=False)
    state = ProjectState(
        length=500.0, materials=[mat], selected_material_id=mat.id,
        cross_section=sdef,
        section_segments=[SectionSegment(
            0.0, 500.0, sdef, material_id=mat.id, local_buckling_length=50.0,
        )],
    )
    restored = dict_to_state(state_to_dict(state))
    assert restored.section_segments[0].local_buckling_length == 50.0

    demand = -100.0*cs.A
    short = assess_local_stability(cs, mat, 50.0, N=demand, M=0.0)
    long = assess_local_stability(cs, mat, 20.0*max(w.width for w in cs.local_walls),
                                  N=demand, M=0.0)
    assert short.RF_local_buckling > long.RF_local_buckling
