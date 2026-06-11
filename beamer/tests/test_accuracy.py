"""Přesnostní (accuracy) testy – proti tabulkovým/analytickým hodnotám.

Doplněk ke konzistenčním testům v test_verification.py. Tyto testy by
zachytily chyby typu „IT obdélníku s prohozenými stranami" nebo „špatný
vzorec τ_t pro uzavřené průřezy" (audit v1.13 → opravy v1.14).
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from beamer.model import (
    Material, Support, Hinge, Load, LoadCase, LoadCombination,
    CrossSectionDef, SectionSegment, ProjectState, Body,
)
from beamer.section import build_section
from beamer.solver import solve_beam
from beamer.analysis import forces_from_beam

MAT = Material("m_steel", "Steel", E=210000.0, G=81000.0, nu=0.3,
               rho=7.85, Re=235.0, Rm=360.0)


def make_state(length, supports, loads, theory="euler-bernoulli", hinges=None,
               sec=None):
    sec = sec or CrossSectionDef(type="rectangle", params={"b": 100.0, "h": 200.0})
    return ProjectState(
        length=float(length), supports=supports, hinges=hinges or [],
        load_cases=[LoadCase("lc", "LC", False)],
        load_combinations=[LoadCombination("c", "C", {"lc": 1.0})],
        loads=loads, materials=[Material(**vars(MAT))],
        selected_material_id=MAT.id, cross_section=sec,
        section_segments=[SectionSegment(0.0, float(length), sec, None,
                                         material_id=MAT.id)],
        additional_factor=1.0, theory=theory,
        selected_active_combination_id="c",
    )


def _rel(a, b):
    return abs(a - b) / (abs(b) if abs(b) > 1e-12 else 1.0)


def _tau_t_max(cs, Mk_nmm, n=120):
    f = forces_from_beam(N=0, V=0, M=0, Mk=Mk_nmm)
    prof = cs.profile(f, N=n)
    vals = [abs(p["tauT"]) for p in prof if not math.isnan(p["tauT"])]
    return max(vals) / 1e6 if vals else 0.0     # MPa


# ═══════════════════════════════════════════════════════════════
#  CHARAKTERISTIKY – přesnost proti analytice
# ═══════════════════════════════════════════════════════════════

def test_props_circle():
    D = 100.0
    cs = build_section(CrossSectionDef(type="circle", params={"D": D}))
    assert _rel(cs.A, math.pi * D**2 / 4) < 5e-3
    assert _rel(cs.Iy, math.pi * D**4 / 64) < 5e-3
    assert _rel(cs.IT, math.pi * D**4 / 32) < 5e-3


def test_props_tube():
    Do, t = 100.0, 5.0
    Di = Do - 2 * t
    cs = build_section(CrossSectionDef(type="tube", params={"Do": Do, "t": t}))
    assert _rel(cs.A, math.pi * (Do**2 - Di**2) / 4) < 5e-3
    assert _rel(cs.Iy, math.pi * (Do**4 - Di**4) / 64) < 5e-3
    assert _rel(cs.IT, math.pi * (Do**4 - Di**4) / 32) < 1e-6   # analyticky


def test_IT_rectangle_saint_venant():
    """C2 regrese: J = c1·a·t³ (kratší strana v kubíku), Roark/Timoshenko."""
    for b, h in [(100.0, 60.0), (100.0, 200.0), (80.0, 100.0)]:
        cs = build_section(CrossSectionDef(type="rectangle", params={"b": b, "h": h}))
        a_, t_ = max(b, h), min(b, h)
        c1 = 1/3 * (1 - 0.63*(t_/a_) + 0.052*(t_/a_)**5)
        J_ref = c1 * a_ * t_**3
        assert _rel(cs.IT, J_ref) < 0.02, f"IT {b}x{h}: {cs.IT} vs {J_ref}"


def test_IT_I_section_open_thin_walled():
    """I-profil: IT = Σ(1/3)·b·t³ (otevřený tenkostěnný)."""
    h, bf, tw, tf = 200.0, 100.0, 6.0, 10.0
    cs = build_section(CrossSectionDef(
        type="i_section",
        params={"h": h, "bf1": bf, "bf2": bf, "tw": tw, "tf1": tf, "tf2": tf}))
    hw = h - 2 * tf
    J_ref = (hw * tw**3 + 2 * bf * tf**3) / 3
    assert _rel(cs.IT, J_ref) < 1e-6


def test_composite_two_flanges():
    """Kompozit (2 pásnice bez stojiny): A, Iy přesně dle steineru."""
    bt = Body(points=[{"y": -50, "z": 80}, {"y": 50, "z": 80},
                      {"y": 50, "z": 100}, {"y": -50, "z": 100}])
    bb = Body(points=[{"y": -50, "z": -100}, {"y": 50, "z": -100},
                      {"y": 50, "z": -80}, {"y": -50, "z": -80}])
    cs = build_section(CrossSectionDef(type="polygon", bodies=[bt, bb]), fem=False)
    assert _rel(cs.A, 4000.0) < 1e-9
    Iy_ref = 2 * (100 * 20**3 / 12 + 100 * 20 * 90**2)
    assert _rel(cs.Iy, Iy_ref) < 1e-9
    assert abs(cs.cx) < 1e-9 and abs(cs.cz) < 1e-9


def test_square_with_hole():
    b = Body(points=[{"y": -50, "z": -50}, {"y": 50, "z": -50},
                     {"y": 50, "z": 50}, {"y": -50, "z": 50}],
             holes=[[{"y": -20, "z": -20}, {"y": 20, "z": -20},
                     {"y": 20, "z": 20}, {"y": -20, "z": 20}]])
    cs = build_section(CrossSectionDef(type="polygon", bodies=[b]), fem=False)
    assert _rel(cs.A, 8400.0) < 1e-9
    assert _rel(cs.Iy, (100**4 - 40**4) / 12) < 1e-9


def test_alpha_pl_rectangle():
    cs = build_section(CrossSectionDef(type="rectangle", params={"b": 100, "h": 200}))
    assert _rel(cs.alpha_pl, 1.5) < 0.01     # Wpl/Wel = 1.5 pro obdélník


# ═══════════════════════════════════════════════════════════════
#  TORZNÍ SMYKOVÉ NAPĚTÍ – per model (C1 regrese)
# ═══════════════════════════════════════════════════════════════

MK = 1.0e6      # N·mm


def test_tau_t_circle():
    D = 100.0
    cs = build_section(CrossSectionDef(type="circle", params={"D": D}))
    tau_ref = MK * (D/2) / cs.IT                       # MPa (mm jednotky)
    assert _rel(_tau_t_max(cs, MK), tau_ref) < 0.02


def test_tau_t_tube():
    Do, t = 100.0, 5.0
    cs = build_section(CrossSectionDef(type="tube", params={"Do": Do, "t": t}))
    tau_ref = MK * (Do/2) / cs.IT
    assert _rel(_tau_t_max(cs, MK), tau_ref) < 0.02


def test_tau_t_box_bredt():
    H, B, tw = 200.0, 100.0, 6.0
    cs = build_section(CrossSectionDef(type="box", params={"H": H, "B": B, "tw": tw}))
    Am = (H - tw) * (B - tw)
    tau_ref = MK / (2 * Am * tw)
    assert _rel(_tau_t_max(cs, MK), tau_ref) < 0.05


def test_tau_t_open_I():
    h, bf, tw, tf = 200.0, 100.0, 6.0, 10.0
    cs = build_section(CrossSectionDef(
        type="i_section",
        params={"h": h, "bf1": bf, "bf2": bf, "tw": tw, "tf1": tf, "tf2": tf}))
    tau_ref = MK * tf / cs.IT          # max na nejtlustší stěně (pásnice)
    assert _rel(_tau_t_max(cs, MK), tau_ref) < 0.10


# ═══════════════════════════════════════════════════════════════
#  NAPĚTÍ – velikost (ne jen znaménko)
# ═══════════════════════════════════════════════════════════════

def test_sigma_M_over_W():
    b, h, M = 100.0, 200.0, 5.0e6        # N·mm
    cs = build_section(CrossSectionDef(type="rectangle", params={"b": b, "h": h}))
    f = forces_from_beam(N=0, V=0, M=M, Mk=0)
    s = cs.stress(f, cs.z_top * 0.9999)
    W = b * h**2 / 6
    assert _rel(abs(s["sigma"]) / 1e6, M / W) < 5e-3


def test_tau_V_rectangle_parabola():
    """Žuravskij: τ_max = 1.5·V/A v neutrální ose obdélníku."""
    b, h, V = 100.0, 200.0, 1.0e5        # N
    cs = build_section(CrossSectionDef(type="rectangle", params={"b": b, "h": h}))
    f = forces_from_beam(N=0, V=V, M=0, Mk=0)
    s = cs.stress(f, 0.0)
    assert _rel(abs(s["tauVz"]) / 1e6, 1.5 * V / (b * h)) < 5e-3


# ═══════════════════════════════════════════════════════════════
#  SOLVER – další případy
# ═══════════════════════════════════════════════════════════════

def test_point_moment_reactions():
    L, M0 = 2000.0, 1.0e6
    st = make_state(L, [Support("a", 0, "pin", 0), Support("b", L, "roller", 0)],
                    [Load("m", "moment", "M", "lc", x=L/2, My=M0)])
    r = solve_beam(st)
    assert r.is_stable
    Rz = sorted(rc.Rz for rc in r.reactions)
    assert _rel(Rz[1], M0 / L) < 1e-6 and _rel(-Rz[0], M0 / L) < 1e-6
    assert abs(sum(rc.Rz for rc in r.reactions)) < 1e-6 * M0 / L


def test_hinge_zero_moment():
    L = 2000.0
    st = make_state(L, [Support("a", 0, "pin", 0), Support("b", L, "fixed", 0)],
                    [Load("f", "point_force", "F", "lc", x=500.0, Fz=-1000.0)],
                    hinges=[Hinge("h1", 1000.0)])
    r = solve_beam(st)
    assert r.is_stable
    p = min(r.points, key=lambda p: abs(p.x - 1000.0))
    Mmax = max(abs(q.M) for q in r.points)
    assert abs(p.M) < 1e-6 * max(Mmax, 1.0)
    assert _rel(sum(rc.Rz for rc in r.reactions), 1000.0) < 1e-9


def test_equilibrium_udl():
    L, q = 2000.0, 2.5
    st = make_state(L, [Support("a", 0, "pin", 0), Support("b", L, "roller", 0)],
                    [Load("q", "distributed", "q", "lc", x1=0, x2=L, q1=-q, q2=-q)])
    r = solve_beam(st)
    assert _rel(sum(rc.Rz for rc in r.reactions), q * L) < 1e-9


def test_skew_roller_45deg():
    """Šikmá rolna 45°: reakce musí ležet ve směru normály (Rx = Rz)
    a platí globální rovnováha. (M1 – dříve se úhel tiše ignoroval.)"""
    L, F = 2000.0, 1000.0
    st = make_state(L, [Support("a", 0, "pin", 0), Support("b", L, "roller", 45.0)],
                    [Load("f", "point_force", "F", "lc", x=L/2, Fz=-F)])
    r = solve_beam(st)
    assert r.is_stable
    rb = next(rc for rc in r.reactions if rc.support_type == "roller")
    ra = next(rc for rc in r.reactions if rc.support_type == "pin")
    assert _rel(rb.Rx, rb.Rz) < 1e-3                  # R ∥ n = (sin45, cos45)
    assert abs(ra.Rx + rb.Rx) < 1e-6 * F              # ΣFx = 0
    assert _rel(ra.Rz + rb.Rz, F) < 1e-6              # ΣFz = F


def test_timoshenko_udl_exact():
    """Timoshenko prostý nosník + UDL: δ_mid = 5qL⁴/384EI + qL²/(8·G·As)."""
    L, q = 2000.0, 1.0
    st = make_state(L, [Support("a", 0, "pin", 0), Support("b", L, "roller", 0)],
                    [Load("q", "distributed", "q", "lc", x1=0, x2=L, q1=-q, q2=-q)],
                    theory="timoshenko")
    r = solve_beam(st)
    cs = build_section(CrossSectionDef(type="rectangle", params={"b": 100, "h": 200}))
    As = cs.Asz if cs.Asz > 0 else cs.kappa * cs.A
    w_ref = 5*q*L**4/(384*MAT.E*cs.Iy) + q*L**2/(8*MAT.G*As)
    w_max = max(abs(p.w) for p in r.points)
    assert _rel(w_max, w_ref) < 5e-3


def test_unstable_beam_returns_message():
    """Nedostatečné podepření vrátí korektní chybovou hlášku (ne výjimku)."""
    L = 1000.0
    st = make_state(L, [], [Load("f", "point_force", "F", "lc", x=L/2, Fz=-1.0)])
    r = solve_beam(st)
    assert not r.is_stable
    assert r.error_message


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
