"""Regrese a analytická validace Vlasovovy torze (etapa C / 1.39)."""

import math

import numpy as np
import pytest

from beamer.model import (
    CrossSectionDef,
    Load,
    LoadCase,
    LoadCombination,
    Material,
    ProjectState,
    Property,
    Support,
)
from beamer.project_io import dict_to_state, state_to_dict
from beamer.solver import _vlasov_torsion_block, solve_beam


def test_warping_options_roundtrip_and_legacy_defaults():
    """Nové volby se serializují; starý projekt zůstane na Saint-Venantovi."""
    state = ProjectState(
        supports=[Support("s", 0.0, "fixed", restrain_warping=True)],
        tau_mode="exact",
        torsion_theory="vlasov",
    )
    loaded = dict_to_state(state_to_dict(state))
    assert loaded.tau_mode == "exact"
    assert loaded.torsion_theory == "vlasov"
    assert loaded.supports[0].restrain_warping is True

    legacy = dict_to_state({
        "supports": [{"id": "old", "x": 0.0, "type": "fixed"}],
    })
    assert legacy.tau_mode == "conservative"
    assert legacy.torsion_theory == "saint-venant"
    assert legacy.supports[0].restrain_warping is None


def test_vlasov_mode_requests_exact_section(monkeypatch):
    """Iω je nosná veličina: Vlasov nesmí použít parametrickou aproximaci."""
    from beamer import sections_along

    calls = []

    def fake_build(section_def, fem=True, exact=False):
        calls.append(exact)
        return object()

    monkeypatch.setattr(sections_along, "build_section", fake_build)
    state = ProjectState(torsion_theory="vlasov")
    sections_along.SectionResolver(state).at(0.0)
    assert calls == [True]


def test_vlasov_torsion_block_energy_and_rigid_mode():
    """Matice vychází přímo z ∫(GJ θ'² + EIw θ''²) dx."""
    L, GJ, EIw = 800.0, 2.4e8, 7.5e12
    k = _vlasov_torsion_block(L, GJ, EIw)
    assert np.allclose(k, k.T)
    assert np.allclose(k @ np.array([1.0, 0.0, 1.0, 0.0]), 0.0,
                       atol=1e-5)
    beta = 2.5e-4
    linear = np.array([0.0, beta, beta*L, beta])
    assert math.isclose(float(linear @ k @ linear), GJ*beta**2*L,
                        rel_tol=1e-12)


def _torsion_state(*, vlasov: bool, Iw: float) -> tuple[ProjectState, float, float, float]:
    L = 1200.0
    E, G = 70000.0, 27000.0
    IT = 8500.0
    torque = 3.2e5
    mat = Material("m", "Al", E, G, 0.3, 2.7, 250.0, 320.0)
    params = {"A": 1500.0, "Iy": 4.0e6, "Iz": 5.0e5, "IT": IT}
    if Iw > 0:
        params["Iw"] = Iw
    section = CrossSectionDef(type="direct", params=params)
    load = Load("t", "torsion", "T", "lc", x=L, Mx=torque)
    state = ProjectState(
        length=L,
        supports=[Support("s", 0.0, "fixed")],
        load_cases=[LoadCase("lc", "LC")],
        load_combinations=[LoadCombination("c", "C", {"t": 1.0})],
        loads=[load],
        materials=[mat],
        selected_material_id=mat.id,
        cross_section=section,
        selected_active_combination_id="c",
        torsion_theory="vlasov" if vlasov else "saint-venant",
    )
    return state, torque, G*IT, E*Iw


def test_restrained_cantilever_matches_closed_vlasov_solution():
    """Konzola, θ(0)=θ'(0)=0, B(L)=0, T(L)=T: uzavřené řešení Vlasova."""
    Iw = 2.5e8
    state, torque, GJ, EIw = _torsion_state(vlasov=True, Iw=Iw)
    result = solve_beam(state)
    assert result.is_stable, result.error_message
    tip = result.points[-1]
    alpha = math.sqrt(GJ/EIw)
    expected = torque/GJ * (state.length - math.tanh(alpha*state.length)/alpha)
    assert math.isclose(tip.theta, expected, rel_tol=2e-5)
    effective_ratio = torque*state.length/(tip.theta*GJ)
    expected_ratio = state.length / (
        state.length - math.tanh(alpha*state.length)/alpha
    )
    assert effective_ratio > 1.0
    assert math.isclose(effective_ratio, expected_ratio, rel_tol=2e-5)
    assert abs(tip.B) <= 1e-5 * max(abs(p.B) for p in result.points)
    # Recovery používá derivaci kubického θ uvnitř posledního prvku; při síti
    # solveru (~40 prvků) konverguje celkový moment s rezervou pod 0,01 %.
    assert math.isclose(tip.Mk, torque, rel_tol=1e-4)
    assert abs(result.reactions[0].B_warping) > 0.0


def test_saint_venant_default_and_zero_iw_degeneracy():
    """Výchozí model se nemění a Vlasov s Iω=0 dá přesně stejnou torzi."""
    legacy, torque, GJ, _ = _torsion_state(vlasov=False, Iw=0.0)
    degenerate, _, _, _ = _torsion_state(vlasov=True, Iw=0.0)
    r_legacy = solve_beam(legacy)
    r_degenerate = solve_beam(degenerate)
    assert r_legacy.is_stable and r_degenerate.is_stable
    expected = torque*legacy.length/GJ
    assert math.isclose(r_legacy.points[-1].theta, expected, rel_tol=1e-10)
    assert math.isclose(r_degenerate.points[-1].theta,
                        r_legacy.points[-1].theta, rel_tol=1e-10)


def test_free_warping_cantilever_reduces_to_saint_venant():
    """Je-li deplanace volná na obou koncích, bimoment zmizí a θ=T·L/GJ."""
    state, torque, GJ, _ = _torsion_state(vlasov=True, Iw=2.5e8)
    state.supports[0].restrain_warping = False
    result = solve_beam(state)
    assert result.is_stable, result.error_message
    assert math.isclose(result.points[-1].theta, torque*state.length/GJ,
                        rel_tol=2e-5)
    assert max(abs(p.B) for p in result.points) < 1e-2


def test_text_report_states_effective_warping_boundary_condition():
    """Protokol nesmí skrýt, zda podpora deplanaci skutečně brání."""
    from beamer.report import build_report

    state, _, _, _ = _torsion_state(vlasov=True, Iw=2.5e8)
    result = solve_beam(state)
    assert "deplanace=bráněná" in build_report(state, result, [])
    state.supports[0].restrain_warping = False
    result = solve_beam(state)
    assert "deplanace=volná" in build_report(state, result, [])


def test_composite_warping_rigidity_scales_with_material_E():
    """Různomateriálová cesta integruje E po ploše, ne E_ref·geometrické Iω."""
    pytest.importorskip("scipy")
    pytest.importorskip("shapely")
    from beamer.composite_fem import composite_warping_EIw

    mat_web = Material("mw", "Web", 70000.0, 27000.0, 0.3, 2.7, 250.0, 320.0)
    mat_flange = Material("mf", "Flange", 70000.0, 27000.0, 0.3, 2.7,
                          250.0, 320.0)
    web = CrossSectionDef(type="rectangle", params={"b": 8.0, "h": 80.0},
                          id="web", name="web")
    flange = CrossSectionDef(type="rectangle", params={"b": 60.0, "h": 8.0},
                             id="flange", name="flange")
    prop = Property(
        id="p", pid=1, name="T",
        composite_parts=[
            {"section_id": "web", "material_id": "mw", "dy": 0.0,
             "dz": 0.0, "angle": 0.0},
            {"section_id": "flange", "material_id": "mf", "dy": 0.0,
             "dz": 36.0, "angle": 0.0},
        ],
    )
    state = ProjectState(
        length=100.0, sections=[web, flange], properties=[prop],
        materials=[mat_web, mat_flange], selected_material_id=mat_web.id,
    )
    e1 = composite_warping_EIw(state, prop)
    mat_flange.E *= 2.0
    e2 = composite_warping_EIw(state, prop)
    mat_web.E *= 2.0
    e3 = composite_warping_EIw(state, prop)
    assert e1 is not None and e1 > 0.0 and e2 is not None and e3 is not None
    assert 1.0 < e2/e1 < 2.0
    assert math.isclose(e3/e1, 2.0, rel_tol=1e-10)


def test_warping_normal_stress_uses_fem_sectorial_coordinate():
    """σw=B·ω/Iω musí vstoupit do stejné RF cesty jako ostatní normálové napětí."""
    pytest.importorskip("scipy")
    from beamer.analysis import build_influence, max_stresses_fast

    L = 900.0
    mat = Material("m", "Al", 70000.0, 27000.0, 0.3, 2.7, 250.0, 320.0)
    section = CrossSectionDef(
        type="i_section",
        params={"h": 160.0, "tw": 6.0, "bf1": 90.0, "tf1": 9.0,
                "bf2": 90.0, "tf2": 9.0, "r": 6.0},
    )
    load = Load("t", "torsion", "T", "lc", x=L, Mx=2.0e5)
    state = ProjectState(
        length=L, supports=[Support("s", 0.0, "fixed")],
        load_cases=[LoadCase("lc", "LC")],
        load_combinations=[LoadCombination("c", "C", {"t": 1.0})],
        loads=[load], materials=[mat], selected_material_id=mat.id,
        cross_section=section, selected_active_combination_id="c",
        torsion_theory="vlasov",
    )
    result = solve_beam(state)
    assert result.is_stable, result.error_message
    cs = result.section
    assert cs is not None and cs.fem_used and cs.warping_field is not None
    root = result.points[0]
    wf = cs.warping_field
    expected_sigma = abs(root.B/cs.Iw) * float(np.max(np.abs(wf["node_omega"])))
    sg, tu, mises = max_stresses_fast(
        build_influence(cs), root.N, root.V, root.M, root.Mk,
        B=root.B, T_sv=root.T_sv, T_w=root.T_w, warping=True,
    )
    assert expected_sigma > 0.0
    assert math.isclose(sg, expected_sigma, rel_tol=1e-10)
    assert tu > 0.0 and mises >= sg
