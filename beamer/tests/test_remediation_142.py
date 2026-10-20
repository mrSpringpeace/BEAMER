"""Regrese nálezů auditu BEAMER 1.42 z 2026-09-11."""
from __future__ import annotations

import pytest

from beamer.analysis import _thermal_at, build_influence, envelope_over_combinations
from beamer.analysis import max_stresses_fast, reserves_along_beam
from beamer.composite import composite_weighted
from beamer.defaults import create_default_state
from beamer.model import (
    Body, CrossSectionDef, Load, LoadCase, LoadCombination, Material, ProjectState,
    Property, SectionSegment, Support, migrate_combinations_to_loads,
)
from beamer.section import build_section
from beamer.sections_along import interp_def
from beamer.solver import _load_multiplier, solve_beam


def _points(points):
    return [{"y": y, "z": z} for y, z in points]


def test_legacy_polygon_hole_uses_complete_geometry_for_centroid_and_inertia():
    outer = _points([(0, 0), (100, 0), (100, 100), (0, 100)])
    hole = _points([(60, 40), (80, 40), (80, 60), (60, 60)])
    definition = CrossSectionDef(
        type="polygon", polygon_points=outer, polygon_holes=[hole]
    )
    section = build_section(definition, fem=False)
    assert section.A == pytest.approx(9600.0)
    assert section.cx == pytest.approx(49.1666666667)
    assert section.cz == pytest.approx(50.0)
    assert section.Iy == pytest.approx(8_320_000.0)
    assert section.Iz == pytest.approx(8_153_333.333333)


def test_polygon_fem_receives_rotated_geometry():
    definition = CrossSectionDef(
        type="polygon",
        bodies=[Body(_points([(-10, -50), (10, -50), (10, 50), (-10, 50)]))],
        rotation=90.0,
    )
    section = build_section(definition, fem=True)
    assert section.Iy == pytest.approx(20 * 100**3 / 12 / 25, rel=1e-12)
    assert section.b == pytest.approx(100.0)
    assert section.h == pytest.approx(20.0)
    coords = section.shear_field["coords"]
    assert max(coords[:, 0]) - min(coords[:, 0]) > 4 * (
        max(coords[:, 1]) - min(coords[:, 1])
    )


def test_taper_preserves_rotation_and_polygon_holes():
    rectangle = CrossSectionDef(type="rectangle", params={"b": 20, "h": 100}, rotation=90)
    middle = interp_def(rectangle, rectangle, 0.5)
    assert middle.rotation == pytest.approx(90.0)
    assert build_section(middle, fem=False).Iy == pytest.approx(20 * 100**3 / 12 / 25)

    outer = _points([(0, 0), (10, 0), (10, 10), (0, 10)])
    hole = _points([(2, 2), (4, 2), (4, 4), (2, 4)])
    polygon = CrossSectionDef(type="polygon", polygon_points=outer, polygon_holes=[hole])
    tapered = interp_def(polygon, polygon, 0.5)
    assert tapered.polygon_holes == [hole]


def test_multibody_bending_checks_every_body_boundary():
    first = Body(_points([(0, 0), (100, 0), (100, 100), (0, 100)]))
    second = Body(_points([(200, 45), (210, 45), (210, 55), (200, 55)]))
    section = build_section(CrossSectionDef(type="polygon", bodies=[first, second]), fem=False)
    influence = build_influence(section)
    sigma, _tau, _mises = max_stresses_fast(influence, 0, 0, 0, 0, Mz=1e6)
    expected = max(abs(y) for outer, _holes in section.bodies_c for y, _z in outer) * 1e6 / section.Iz
    assert sigma == pytest.approx(expected)


def test_rf_scan_always_visits_short_section_segment():
    state = create_default_state()
    state.length = 2000.0
    strong = CrossSectionDef(type="rectangle", params={"b": 100, "h": 100})
    weak = CrossSectionDef(type="rectangle", params={"b": 1, "h": 1})
    state.supports = [Support("fixed", 0.0, "fixed")]
    state.section_segments = [
        SectionSegment(0, 1001, strong), SectionSegment(1001, 1002, weak),
        SectionSegment(1002, 2000, strong),
    ]
    lc = state.load_cases[0].id
    state.loads = [Load("m", "moment", "M", lc, x=2000, My=1000)]
    state.load_combinations = [LoadCombination("c", "C", {lc: 1.0})]
    state.selected_active_combination_id = "c"
    result = solve_beam(state)
    reserves = reserves_along_beam(result, state, n_stations=20)
    critical = min(reserves, key=lambda item: item.RF)
    assert 1001.0 <= critical.x <= 1002.0
    assert critical.RF < 1.0


def test_rf_scan_visits_arbitrary_point_load_and_both_sides_of_jump():
    state = create_default_state()
    state.length = 2000.0
    state.cross_section = CrossSectionDef(
        type="rectangle", params={"b": 20, "h": 100}
    )
    state.section_segments = [SectionSegment(0, state.length, state.cross_section)]
    state.supports = [Support("a", 0, "pin"), Support("b", state.length, "roller")]
    lc = state.load_cases[0].id
    load_x = 657.3
    state.loads = [Load("p", "point_force", "P", lc, x=load_x, Fz=-5000)]
    state.load_combinations = [LoadCombination("c", "C", {lc: 1.0})]
    state.selected_active_combination_id = "c"

    result = solve_beam(state)
    reserves = reserves_along_beam(result, state, n_stations=20)
    at_load = [item for item in reserves if item.x == pytest.approx(load_x)]
    assert len(at_load) == 1

    local_sides = [
        point
        for element in result.elements
        for point in (element["points"][0], element["points"][-1])
        if point.x == pytest.approx(load_x)
    ]
    assert len(local_sides) == 2
    # Řídicí hodnota v místě bodové síly musí zahrnout větší smyk na obou
    # stranách skoku, nikoli jen konec levého prvku uložený v result.points.
    section = result.section
    influence = build_influence(section)
    expected_mises = max(
        max_stresses_fast(influence, p.N, p.V, p.M, p.Mk)[2]
        for p in local_sides
    )
    assert at_load[0].mises_max == pytest.approx(expected_mises)


def test_legacy_migration_preserves_precedence_without_adding_factors():
    a = Load("a", "point_force", "A", "lc")
    b = Load("b", "point_force", "B", "lc")
    state = ProjectState(
        loads=[a, b], load_cases=[LoadCase("lc", "LC")],
        load_combinations=[LoadCombination("c", "C", {"lc": 2.0, "a": 3.0})],
    )
    migrate_combinations_to_loads(state)
    assert len(state.load_cases) == 2
    assert _load_multiplier(state, a) == pytest.approx(3.0)
    assert _load_multiplier(state, b) == pytest.approx(2.0)
    assert set(state.load_combinations[0].factors) == {c.id for c in state.load_cases}


def test_new_load_does_not_change_disabled_case_factor():
    load = Load("a", "point_force", "A", "lc")
    state = ProjectState(
        loads=[load], load_cases=[LoadCase("lc", "LC")],
        load_combinations=[LoadCombination("c", "C", {"lc": 0.0})],
    )
    new = Load("b", "point_force", "B", "lc")
    state.loads.append(new)
    assert state.load_combinations[0].factors == {"lc": 0.0}
    assert _load_multiplier(state, new) == 0.0


def test_thermal_postprocessing_uses_explicit_combination_factors():
    thermal = Load("t", "thermal", "T", "lc", x1=0, x2=100, dT=80, dT_grad=20)
    state = ProjectState(
        loads=[thermal], load_cases=[LoadCase("lc", "LC")],
        load_combinations=[LoadCombination("off", "off", {"lc": 0})],
        selected_active_combination_id="off",
    )
    assert _thermal_at(state, 50, {"lc": 2.0}) == pytest.approx((160.0, 40.0))


def test_solver_result_keeps_snapshot_of_combination_factors():
    state = create_default_state()
    lc = state.load_cases[0].id
    state.loads.append(
        Load("t", "thermal", "T", lc, x1=0, x2=state.length, dT=40)
    )
    state.active_combination().factors[lc] = 2.0

    result = solve_beam(state)
    state.active_combination().factors[lc] = 0.0

    assert result.factors == {lc: 2.0}
    assert _thermal_at(state, state.length / 2, result.factors) == pytest.approx((80, 0))


def test_overlapping_composite_parts_are_rejected():
    material = Material("m", "M", 210000, 81000, 0.3, 7.85, 235, 360)
    section = CrossSectionDef(type="rectangle", params={"b": 20, "h": 20}, id="r")
    prop = Property("p", 1, composite_parts=[
        {"section_id": "r", "material_id": "m", "dy": 0, "dz": 0, "angle": 0},
        {"section_id": "r", "material_id": "m", "dy": 10, "dz": 0, "angle": 0},
    ])
    state = ProjectState(
        sections=[section], properties=[prop], materials=[material], selected_material_id="m"
    )
    with pytest.raises(ValueError, match="překrývají"):
        composite_weighted(state, prop)


def test_envelope_lists_unstable_combinations():
    state = create_default_state()
    state.section_segments = []
    state.cross_section = CrossSectionDef(type="rectangle", params={"b": 20, "h": 100})
    state.supports = [
        Support("a", 0, "pin", restrain_torsion=False),
        Support("b", state.length, "roller", restrain_torsion=False),
    ]
    lc_v = state.load_cases[0].id
    lc_t = "lc_t"
    state.load_cases.append(LoadCase(lc_t, "Torze"))
    state.loads = [
        Load("v", "point_force", "F", lc_v, x=state.length/2, Fz=-100),
        Load("t", "torsion", "T", lc_t, x=state.length, Mx=100),
    ]
    state.load_combinations = [
        LoadCombination("vertical", "Svislá", {lc_v: 1, lc_t: 0}),
        LoadCombination("torsion", "Torzní mechanismus", {lc_v: 0, lc_t: 1}),
    ]
    envelope = envelope_over_combinations(state, n_stations=12)
    assert envelope is not None
    assert envelope.n_combos == 1
    assert envelope.failed_combos == ["Torzní mechanismus"]


def test_table_envelope_keeps_incomplete_marker_with_governing_combo():
    from beamer.gui.loadcase_dialog import LoadCaseBuilderDialog
    from beamer.i18n import tr

    columns = ["Kombinace", "RF min", "x(RFmin) [mm]", tr("stav")]
    rows = [
        {"Kombinace": "Provoz", "RF min": 1.5, "x(RFmin) [mm]": 500.0},
        {"Kombinace": "Mechanismus", tr("stav"): tr("NESTABILNÍ")},
    ]
    envelope = LoadCaseBuilderDialog._envelope_row(None, columns, rows)
    assert envelope["Kombinace"] == "◆ OBÁLKA NEÚPLNÁ · řídí Provoz"


def test_loading_state_invalidates_result_and_queues_recompute_for_running_worker():
    from types import SimpleNamespace

    from beamer.gui.main_window import MainWindow

    class Combo:
        def blockSignals(self, _blocked):
            pass

        def findData(self, _value):
            return 0

        def setCurrentIndex(self, _index):
            pass

    class Worker:
        def isRunning(self):
            return True

    calls = []
    panel = SimpleNamespace(state=None, reload_from_state=lambda: None)
    window = SimpleNamespace(
        _worker=Worker(), _recompute_after_worker=False, _input_revision=7,
        _dirty=False, result=object(), reserves=[object()],
        results_panel=SimpleNamespace(clear_analysis=lambda: calls.append("clear")),
        input_panel=panel, rf_basis_cb=Combo(), sigred_cb=Combo(), tau_cb=Combo(),
        _lc_dialog=None, _sec_sig="old", _modified=True, _current_file="old.json",
        _live_update_section=lambda: calls.append("section"),
        _refresh_views=lambda: calls.append("views"),
        compute=lambda: calls.append("compute"), _update_title=lambda: None,
    )

    new_state = create_default_state()
    MainWindow._load_state(window, new_state)

    assert window.state is new_state
    assert window._input_revision == 8
    assert window._dirty is True
    assert window.result is None
    assert window.reserves == []
    assert window._recompute_after_worker is True
    assert "compute" not in calls
