"""Verifikační testy proti analytickým (closed-form) řešením.

Spuštění:
    python -m pytest beamer/tests/ -v
nebo bez pytestu:
    python beamer/tests/test_verification.py

Tolerance: průhyby rel. < 0.5 %, momenty (z rovnováhy) rel. < 0.2 %.
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from beamer.model import (
    Material, Support, Hinge, Load, LoadCase, LoadCombination,
    CrossSectionDef, SectionSegment, ProjectState,
)
from beamer.solver import solve_beam
from beamer.section import build_section
from beamer.analysis import forces_from_beam

# ── pevný materiál a průřez pro reprodukovatelnost ──
MAT = Material("m_steel", "Steel", E=200000.0, G=77000.0, nu=0.3,
               rho=7.85, Re=235.0, Rm=360.0)
RECT = CrossSectionDef(type="rectangle", params={"b": 100.0, "h": 200.0})


def make_state(length, supports, loads, theory="euler-bernoulli", section=None):
    sec = section or CrossSectionDef(type="rectangle", params={"b": 100.0, "h": 200.0})
    LC, COMB = "lc", "comb"
    return ProjectState(
        length=float(length),
        supports=supports,
        hinges=[],
        load_cases=[LoadCase(LC, "LC", False)],
        load_combinations=[LoadCombination(COMB, "C", {LC: 1.0})],
        loads=loads,
        materials=[Material(**vars(MAT))],
        selected_material_id=MAT.id,
        cross_section=sec,
        section_segments=[SectionSegment(0.0, float(length), sec, None,
                                         material_id=MAT.id)],
        additional_factor=1.0,
        theory=theory,
        selected_active_combination_id=COMB,
    )


def _sec_props():
    sc = build_section(RECT, fem=True)
    return sc


def _rel(a, b):
    return abs(a - b) / (abs(b) if abs(b) > 1e-12 else 1.0)


def _wmax(res):
    return max(abs(p.w) for p in res.points)


def _Mabs(res):
    return max(abs(p.M) for p in res.points)


# ═══════════════════════════════════════════════════════════════
#  OHYB – PRŮHYBY A MOMENTY
# ═══════════════════════════════════════════════════════════════

def test_cantilever_tip_force():
    """Vetknutý nosník + síla na konci: δ=FL³/3EI, M_fix=FL."""
    L, F = 1000.0, 1000.0
    st = make_state(L, [Support("s", 0.0, "fixed", 0)],
                    [Load("f", "point_force", "F", "lc", x=L, Fz=-F)])
    res = solve_beam(st)
    assert res.is_stable
    E, I = MAT.E, _sec_props().Iy
    assert _rel(_wmax(res), F * L**3 / (3 * E * I)) < 5e-3
    assert _rel(_Mabs(res), F * L) < 2e-3


def test_simply_supported_udl():
    """Prostý nosník + UDL: δ=5qL⁴/384EI, M_mid=qL²/8."""
    L, q = 2000.0, 1.0
    st = make_state(L, [Support("a", 0.0, "pin", 0), Support("b", L, "roller", 0)],
                    [Load("q", "distributed", "q", "lc", x1=0, x2=L, q1=-q, q2=-q)])
    res = solve_beam(st)
    assert res.is_stable
    E, I = MAT.E, _sec_props().Iy
    assert _rel(_wmax(res), 5 * q * L**4 / (384 * E * I)) < 5e-3
    assert _rel(_Mabs(res), q * L**2 / 8) < 2e-3


def test_cantilever_udl():
    """Vetknutý nosník + UDL: δ=qL⁴/8EI, M_fix=qL²/2."""
    L, q = 1500.0, 2.0
    st = make_state(L, [Support("s", 0.0, "fixed", 0)],
                    [Load("q", "distributed", "q", "lc", x1=0, x2=L, q1=-q, q2=-q)])
    res = solve_beam(st)
    assert res.is_stable
    E, I = MAT.E, _sec_props().Iy
    assert _rel(_wmax(res), q * L**4 / (8 * E * I)) < 5e-3
    assert _rel(_Mabs(res), q * L**2 / 2) < 2e-3


def test_fixed_fixed_center_force():
    """Oboustranně vetknutý + síla uprostřed: |M|=FL/8, δ=FL³/192EI."""
    L, F = 2000.0, 5000.0
    st = make_state(L, [Support("a", 0.0, "fixed", 0), Support("b", L, "fixed", 0)],
                    [Load("f", "point_force", "F", "lc", x=L / 2, Fz=-F)])
    res = solve_beam(st)
    assert res.is_stable
    E, I = MAT.E, _sec_props().Iy
    assert _rel(_wmax(res), F * L**3 / (192 * E * I)) < 1e-2
    assert _rel(_Mabs(res), F * L / 8) < 1e-2


# ═══════════════════════════════════════════════════════════════
#  TORZE
# ═══════════════════════════════════════════════════════════════

def test_torsion_cantilever():
    """Vetknutý nosník + kroutící moment na konci: θ=Mk·L/(G·J).
    Konzistenční test – používá J (IT) z programu."""
    L, Mk = 1000.0, 1.0e6
    st = make_state(L, [Support("s", 0.0, "fixed", 0)],
                    [Load("t", "torsion", "T", "lc", x=L, Mx=Mk)])
    res = solve_beam(st)
    assert res.is_stable
    G, J = MAT.G, _sec_props().IT
    theta_tip = max(abs(p.theta) for p in res.points)
    assert _rel(theta_tip, Mk * L / (G * J)) < 1e-2


# ═══════════════════════════════════════════════════════════════
#  TIMOSHENKO vs EULER-BERNOULLI
# ═══════════════════════════════════════════════════════════════

def test_timoshenko_adds_shear_deflection():
    """Timoshenko ≥ Euler-Bernoulli (smyk přidává průhyb); pro štíhlý nosník
    je rozdíl malý, pro krátký roste."""
    L, q = 2000.0, 1.0
    sup = [Support("a", 0.0, "pin", 0), Support("b", L, "roller", 0)]
    load = [Load("q", "distributed", "q", "lc", x1=0, x2=L, q1=-q, q2=-q)]
    w_eb = _wmax(solve_beam(make_state(L, sup, load, "euler-bernoulli")))
    w_tim = _wmax(solve_beam(make_state(L, sup, load, "timoshenko")))
    assert w_tim >= w_eb
    # rozdíl je řádově smyková deflekce qL²/(8·G·A_s); jen kontrola plausibility
    sc = _sec_props()
    A_s = sc.Asz if sc.Asz > 0 else sc.kappa * sc.A
    shear_est = q * L**2 / (8 * MAT.G * A_s)
    assert 0.2 * shear_est < (w_tim - w_eb) < 5.0 * shear_est


# ═══════════════════════════════════════════════════════════════
#  ZNAMÉNKOVÁ KONVENCE NAPĚTÍ
# ═══════════════════════════════════════════════════════════════

def test_bending_stress_sign_sagging():
    """Sagging (M>0): horní vlákno (+z) TLAK (σ<0), dolní (−z) TAH (σ>0).
    Kontrola fyzikálního znaménka σ v section.stress()."""
    sc = _sec_props()
    f = forces_from_beam(N=0.0, V=0.0, M=500000.0, Mk=0.0)   # My>0 = sagging
    s_top = sc.stress(f, sc.z_top * 0.999)["sigma"]
    s_bot = sc.stress(f, sc.z_bot * 0.999)["sigma"]
    assert s_top < 0.0, "horní vlákno má být tlak (σ<0) pro sagging"
    assert s_bot > 0.0, "dolní vlákno má být tah (σ>0) pro sagging"


def test_stress_profile_sign_consistent():
    """Diagram napětí (stress_profile) má stejné znaménko jako section.stress():
    sagging → σ nahoře záporné, dole kladné."""
    from beamer.analysis import stress_profile
    sc = _sec_props()
    prof = stress_profile(sc, N=0.0, V=0.0, M=500000.0, Mk=0.0, n=80)
    z = prof.z
    sig = prof.sigma
    i_top = max(range(len(z)), key=lambda k: z[k])
    i_bot = min(range(len(z)), key=lambda k: z[k])
    assert sig[i_top] < 0.0, "profil: horní vlákno má být tlak (σ<0)"
    assert sig[i_bot] > 0.0, "profil: dolní vlákno má být tah (σ>0)"


def test_von_mises_sign_invariant():
    """Posouzení (von Mises) je nezávislé na znaménku σ – RF musí být kladné
    a odpovídat Re/σ_red bez ohledu na konvenci."""
    sc = _sec_props()
    f = forces_from_beam(N=0.0, V=0.0, M=500000.0, Mk=0.0)
    s = sc.stress(f, sc.z_top * 0.999)
    mises = s["mises"]
    assert mises > 0
    assert abs(mises - abs(s["sigma"])) < 1e-6 * mises   # čistý ohyb: σ_red=|σ|


def test_construction_boolean_rect_minus_circle():
    """Konstrukční tvar: obdélník 100×200 mínus středový kruh ⌀50.
    A musí odpovídat b·h − π·r² (kruh polygonálně aproximován, tolerance 0,5 %)."""
    sdef = CrossSectionDef(type="construction", shapes=[
        {"kind": "rect", "op": "add", "x": 0, "z": 0, "w": 100, "h": 200},
        {"kind": "circle", "op": "sub", "x": 0, "z": 0, "d": 50},
    ])
    sec = build_section(sdef, fem=False)
    A_exact = 100.0 * 200.0 - math.pi * 25.0 ** 2
    assert abs(sec.A - A_exact) < 0.005 * A_exact
    assert sec.section_type == "construction"
    # symetrie → produkty setrvačnosti a střed smyku v ose
    assert abs(sec.Iyz) < 1e-3 * sec.Iy


def test_construction_two_separate_bodies():
    """Dva nepřekrývající se obdélníky → kompozit ze dvou těles."""
    sdef = CrossSectionDef(type="construction", shapes=[
        {"kind": "rect", "op": "add", "x": -100, "z": 0, "w": 50, "h": 50},
        {"kind": "rect", "op": "add", "x": 100, "z": 0, "w": 50, "h": 50},
    ])
    sec = build_section(sdef, fem=False)
    assert abs(sec.A - 2 * 50 * 50) < 1e-6
    assert sec.bodies_c is not None and len(sec.bodies_c) == 2


def test_loadgen_trapezoid_preserves_resultant_and_moment():
    """Lichoběžník zachovává výslednici i těžiště pro libovolnou polohu –
    včetně síly u kraje, kde jeden konec vyjde záporný (houpačka)."""
    from beamer.loadgen import generate_q
    # síla u levého kraje, c = L/6
    r = generate_q(0.0, 600.0, -600.0, 100.0, "trapezoid")
    assert abs(r.R - (-600.0)) < 1e-6
    assert abs(r.x_centroid - 100.0) < 1e-6
    assert r.moment_ok
    assert r.q1 < 0 < r.q2            # opačná znaménka konců
    # síla v 1/3 → pravoúhlý trojúhelník (jeden konec nulový)
    r3 = generate_q(0.0, 900.0, -900.0, 300.0, "trapezoid")
    assert abs(r3.q2) < 1e-9 and r3.moment_ok


def test_loadgen_static_equivalence_reactions():
    """Bodová síla a z ní vygenerovaný lichoběžník dají identické reakce."""
    from beamer.loadgen import generate_q
    L = 1000.0
    sup = [Support("s1", 0.0, "pin", 0), Support("s2", L, "roller", 0)]
    fF = Load("l", "point_force", "", "lc"); fF.x = 200.0; fF.Fz = -3000.0
    sa = make_state(L, sup, [fF])
    ra = solve_beam(sa)
    r = generate_q(0.0, L, -3000.0, 200.0, "trapezoid")
    fq = Load("l2", "distributed", "", "lc"); fq.x1 = 0.0; fq.x2 = L; fq.q1 = r.q1; fq.q2 = r.q2
    sb = make_state(L, sup, [fq])
    rb = solve_beam(sb)
    for rea, reb in zip(ra.reactions, rb.reactions):
        assert abs(rea.Rz - reb.Rz) < 1e-3


def test_section_library_reference_resolves():
    """Úsek odkazující do knihovny průřezů (sec1_id) se vyhodnotí podle knihovny;
    bez odkazu padá na zapečený inline (zpětná kompatibilita)."""
    from beamer.sections_along import eff_defs, section_by_id
    lib = CrossSectionDef(type="circle", params={"D": 30.0}, id="sec_lib", name="D30")
    inline = CrossSectionDef(type="rectangle", params={"b": 10.0, "h": 20.0})
    seg = SectionSegment(0.0, 100.0, sec1=inline, sec2=None)
    st = ProjectState(length=100.0, sections=[lib], section_segments=[seg])
    # bez odkazu → inline
    s1, _ = eff_defs(st, seg)
    assert s1.type == "rectangle"
    # s odkazem → knihovna
    seg.sec1_id = "sec_lib"
    s1, _ = eff_defs(st, seg)
    assert s1.type == "circle" and s1.params["D"] == 30.0
    assert section_by_id(st, "sec_lib") is lib
    # neexistující odkaz → fallback na inline
    seg.sec1_id = "sec_missing"
    s1, _ = eff_defs(st, seg)
    assert s1.type == "rectangle"


def test_section_library_roundtrip():
    """Knihovna průřezů a odkazy přežijí uložení/načtení projektu."""
    from beamer.project_io import state_to_dict, dict_to_state
    lib = CrossSectionDef(type="circle", params={"D": 18.0}, id="sec_a", name="Čep")
    seg = SectionSegment(0.0, 50.0, sec1=CrossSectionDef(), sec1_id="sec_a")
    st = ProjectState(length=50.0, sections=[lib], section_segments=[seg])
    st2 = dict_to_state(state_to_dict(st))
    assert len(st2.sections) == 1 and st2.sections[0].id == "sec_a"
    assert st2.sections[0].name == "Čep"
    assert st2.section_segments[0].sec1_id == "sec_a"


# ── manuální runner (bez pytestu) ──
if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {e!r}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
