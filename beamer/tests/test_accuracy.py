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


# ═══════════════════════════════════════════════════════════════
#  BEAM – další analytické benchmarky (průhyb, reakce, i staticky neurčité)
# ═══════════════════════════════════════════════════════════════

def _EI():
    cs = build_section(CrossSectionDef(type="rectangle", params={"b": 100.0, "h": 200.0}))
    return MAT.E * cs.Iy


def test_cantilever_end_moment():
    """Konzola s koncovým momentem M: w_konec = M·L²/(2EI), φ_konec = M·L/EI,
    a ohybový moment po celé délce konstantní = M."""
    L, M = 1000.0, 1.0e6
    st = make_state(L, [Support("a", 0, "fixed", 0)],
                    [Load("m", "moment", "M", "lc", x=L, My=M)])
    r = solve_beam(st)
    assert r.is_stable
    EI = _EI()
    assert _rel(max(abs(p.w) for p in r.points), M*L*L/(2*EI)) < 1e-2
    assert _rel(max(abs(p.phi) for p in r.points), M*L/EI) < 1e-2
    assert _rel(max(abs(p.M) for p in r.points), M) < 1e-3


def test_simply_supported_central_point_load():
    """Prostý nosník, osamělá síla uprostřed P: w_mid = P·L³/(48EI), M_mid = P·L/4."""
    L, P = 2000.0, 1000.0
    st = make_state(L, [Support("a", 0, "pin", 0), Support("b", L, "roller", 0)],
                    [Load("p", "point_force", "P", "lc", x=L/2, Fz=-P)])
    r = solve_beam(st)
    assert r.is_stable
    EI = _EI()
    assert _rel(max(abs(p.w) for p in r.points), P*L**3/(48*EI)) < 1e-2
    assert _rel(max(abs(p.M) for p in r.points), P*L/4) < 1e-3


def test_propped_cantilever_udl():
    """Vetknutá–podepřená (staticky NEURČITÁ), spojité q: reakce v podpoře
    R = 3qL/8, moment u vetknutí = qL²/8 (a je to největší |M|)."""
    L, q = 2000.0, 2.0
    st = make_state(L, [Support("a", 0, "fixed", 0), Support("b", L, "roller", 0)],
                    [Load("q", "distributed", "q", "lc", x1=0, x2=L, q1=-q, q2=-q)])
    r = solve_beam(st)
    assert r.is_stable
    R_prop = next(rc for rc in r.reactions if rc.support_type == "roller")
    assert _rel(abs(R_prop.Rz), 3*q*L/8) < 5e-3
    assert _rel(max(abs(p.M) for p in r.points), q*L**2/8) < 5e-3


def test_fixed_fixed_udl():
    """Oboustranně vetknutá (staticky NEURČITÁ), spojité q: reakce qL/2 na
    každé straně, moment u konců qL²/12 (největší |M|)."""
    L, q = 2000.0, 2.0
    st = make_state(L, [Support("a", 0, "fixed", 0), Support("b", L, "fixed", 0)],
                    [Load("q", "distributed", "q", "lc", x1=0, x2=L, q1=-q, q2=-q)])
    r = solve_beam(st)
    assert r.is_stable
    for rc in r.reactions:
        assert _rel(abs(rc.Rz), q*L/2) < 5e-3
    assert _rel(max(abs(p.M) for p in r.points), q*L**2/12) < 5e-3


# ═══════════════════════════════════════════════════════════════
#  SLOŽENÝ PID (geometrické skládání z profilů knihovny)
# ═══════════════════════════════════════════════════════════════

def test_composite_pid_assembly():
    """Složený PID ze dvou knihovních obdélníků posunutých svisle → kompozit
    dvou těles; A = součet ploch, symetrie (Iyz≈0)."""
    from beamer.composite import composite_def
    from beamer.model import Property
    r1 = CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}, id="s1", name="R1")
    r2 = CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}, id="s2", name="R2")
    st = ProjectState(length=100.0, sections=[r1, r2],
                      materials=[Material(**vars(MAT))], selected_material_id=MAT.id)
    prop = Property(id="p1", pid=1, name="slozeny", composite_parts=[
        {"section_id": "s1", "dy": 0, "dz": 30, "angle": 0},
        {"section_id": "s2", "dy": 0, "dz": -30, "angle": 0},
    ])
    st.properties = [prop]
    cdef = composite_def(st, prop)
    assert cdef is not None and cdef.bodies is not None and len(cdef.bodies) == 2
    cs = build_section(cdef, fem=False)
    assert _rel(cs.A, 2 * 40 * 20) < 1e-6
    assert abs(cs.Iyz) < 1e-6 * cs.Iy            # svisle symetrické → Iyz ≈ 0
    # a přes eff_defs (úsek → PID) se vrátí týž složený průřez
    from beamer.sections_along import eff_defs
    seg = SectionSegment(0.0, 100.0, CrossSectionDef(), None, property_id="p1")
    st.section_segments = [seg]
    s1, s2 = eff_defs(st, seg)
    assert s2 is None and s1.bodies is not None and len(s1.bodies) == 2


def test_composite_tube_over_rod():
    """Trubka přes tyč (souosé): kompozit = mezikruží + plný kruh, A = obojí."""
    from beamer.composite import composite_def
    from beamer.model import Property
    rod = CrossSectionDef(type="circle", params={"D": 20}, id="rod", name="tyč")
    tube = CrossSectionDef(type="tube", params={"Do": 40, "t": 5}, id="tube", name="trubka")
    st = ProjectState(length=100.0, sections=[rod, tube],
                      materials=[Material(**vars(MAT))], selected_material_id=MAT.id)
    prop = Property(id="p", pid=1, name="tyč v trubce", composite_parts=[
        {"section_id": "rod", "dy": 0, "dz": 0, "angle": 0},
        {"section_id": "tube", "dy": 0, "dz": 0, "angle": 0},
    ])
    cs = build_section(composite_def(st, prop), fem=False)
    A_rod = math.pi * 10**2
    A_tube = math.pi * (20**2 - 15**2)
    assert _rel(cs.A, A_rod + A_tube) < 0.01     # kruhy polygonálně aprox.


def test_composite_weighted_reduces_to_geometric():
    """Jeden materiál: modulem vážené EIy = E · geometrické Iy (redukce), NA = těžiště."""
    from beamer.composite import composite_def, composite_weighted
    from beamer.model import Property
    r = CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}, id="s", name="R")
    st = ProjectState(length=100.0, sections=[r], materials=[Material(**vars(MAT))],
                      selected_material_id=MAT.id)
    prop = Property(id="p", pid=1, name="c", composite_parts=[
        {"section_id": "s", "material_id": MAT.id, "dy": 0, "dz": 30, "angle": 0},
        {"section_id": "s", "material_id": MAT.id, "dy": 0, "dz": -30, "angle": 0},
    ])
    w = composite_weighted(st, prop)
    cs = build_section(composite_def(st, prop), fem=False)   # geometrický kompozit
    assert not w.multi_material
    assert abs(w.z_NA) < 1e-6 and abs(w.y_NA) < 1e-6         # symetrie
    assert _rel(w.EIy, MAT.E * cs.Iy) < 1e-6                 # EIy = E·Iy
    assert _rel(w.A_eq, cs.A) < 1e-6                         # A_eq = A (E_ref=E)


def test_composite_weighted_neutral_axis_shift():
    """Dva materiály (tužší nahoře): neutrální osa se posune k tuhému materiálu."""
    from beamer.composite import composite_weighted
    from beamer.model import Property
    steel = Material("st", "Ocel", E=210000.0, G=81000.0, nu=0.3, rho=7.85, Re=235, Rm=360)
    alu = Material("al", "Hliník", E=70000.0, G=27000.0, nu=0.33, rho=2.7, Re=200, Rm=300)
    r = CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}, id="s", name="R")
    st = ProjectState(length=100.0, sections=[r], materials=[steel, alu],
                      selected_material_id="st")
    prop = Property(id="p", pid=1, name="c", composite_parts=[
        {"section_id": "s", "material_id": "st", "dy": 0, "dz": 30, "angle": 0},   # tuhá nahoře
        {"section_id": "s", "material_id": "al", "dy": 0, "dz": -30, "angle": 0},
    ])
    w = composite_weighted(st, prop)
    assert w.multi_material
    A = 40 * 20
    # z_NA = ΣEᵢAᵢzᵢ / ΣEᵢAᵢ = A·30·(Est−Eal)/(A·(Est+Eal))
    z_expect = 30 * (210000 - 70000) / (210000 + 70000)      # = 15.0 mm nahoru
    assert _rel(w.z_NA, z_expect) < 1e-6
    assert w.z_NA > 0                                        # posun k tužšímu (nahoru)
    assert _rel(w.EA, (210000 + 70000) * A) < 1e-6


def test_composite_beam_deflection_uses_weighted_EI():
    """Prostý nosník s osamělou silou uprostřed, průřez = složený PID ze DVOU
    materiálů (ocel nahoře, hliník dole). Průhyb musí odpovídat modulem vážené
    tuhosti: w_mid = P·L³/(48·EIy). Ověřuje napojení B1 do solveru."""
    from beamer.model import Property
    from beamer.composite import composite_weighted, composite_def
    steel = Material("st", "Ocel", E=210000, G=81000, nu=0.3, rho=7.85, Re=235, Rm=360)
    alu = Material("al", "Hliník", E=70000, G=27000, nu=0.33, rho=2.7, Re=200, Rm=300)
    r = CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}, id="s", name="R")
    prop = Property(id="p", pid=1, name="bimetal", composite_parts=[
        {"section_id": "s", "material_id": "st", "dy": 0, "dz": 10, "angle": 0},
        {"section_id": "s", "material_id": "al", "dy": 0, "dz": -10, "angle": 0},
    ])
    L, P = 2000.0, 1000.0
    seg = SectionSegment(0.0, L, CrossSectionDef(), None, property_id="p")
    st = ProjectState(
        length=L, supports=[Support("a", 0, "pin", 0), Support("b", L, "roller", 0)],
        load_cases=[LoadCase("lc", "LC", False)],
        load_combinations=[LoadCombination("c", "C", {"f": 1.0})],
        loads=[Load("f", "point_force", "P", "lc", x=L/2, Fz=-P)],
        materials=[steel, alu], selected_material_id="st", sections=[r],
        properties=[prop], cross_section=CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}),
        section_segments=[seg], additional_factor=1.0, selected_active_combination_id="c")
    w = composite_weighted(st, prop)
    res = solve_beam(st)
    assert res.is_stable
    w_max = max(abs(p.w) for p in res.points)
    assert _rel(w_max, P*L**3/(48*w.EIy)) < 1e-2       # průhyb dle vážené EIy
    assert _rel(max(abs(p.M) for p in res.points), P*L/4) < 1e-3   # M nezávisí na materiálu
    # směs ocel+hliník je poddajnější než celá ocel (kontrola, že vážení působí)
    EIy_all_steel = 210000 * build_section(composite_def(st, prop), fem=False).Iy
    assert w.EIy < EIy_all_steel


def test_composite_assessment_wired():
    """Posouzení složeného nosníku vrací per-materiálové RF (values_at_x i
    reserves_along_beam), řídicí RF = min přes materiály."""
    from beamer.model import Property
    from beamer.analysis import values_at_x_multi, reserves_along_beam
    steel = Material("st", "Ocel", E=210000, G=81000, nu=0.3, rho=7.85, Re=235, Rm=360)
    alu = Material("al", "Hliník", E=70000, G=27000, nu=0.33, rho=2.7, Re=200, Rm=300)
    r = CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}, id="s", name="R")
    seg = SectionSegment(0.0, 2000.0, CrossSectionDef(), None, property_id="p")
    st = ProjectState(
        length=2000.0, supports=[Support("a", 0, "pin", 0), Support("b", 2000, "roller", 0)],
        load_cases=[LoadCase("lc", "LC", False)],
        load_combinations=[LoadCombination("c", "C", {"f": 1.0})],
        loads=[Load("f", "point_force", "P", "lc", x=1000, Fz=-5000.0)],
        materials=[steel, alu], selected_material_id="st", sections=[r],
        properties=[Property(id="p", pid=1, name="bimetal", composite_parts=[
            {"section_id": "s", "material_id": "st", "dy": 0, "dz": 10, "angle": 0},
            {"section_id": "s", "material_id": "al", "dy": 0, "dz": -10, "angle": 0}])],
        cross_section=CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}),
        section_segments=[seg], additional_factor=1.0, selected_active_combination_id="c")
    res = solve_beam(st)
    d = values_at_x_multi(res, st, 1000.0)[0]
    assert d.get("composite") and len(d.get("materials", [])) == 2
    assert d["RF"] == min(m["RF_yield"] for m in d["materials"]) or \
           d["RF"] == min(min(m["RF_yield"], m["RF_ultimate"]) for m in d["materials"])
    marg = reserves_along_beam(res, st)
    assert marg and all(m.RF > 0 for m in marg)


def test_composite_torsion_end_to_end():
    """Vetknutý složený nosník + kroutící moment: per-materiálové posouzení
    projde celým řetězcem (solver GJ_eff → analýza) a nese torzní τ > 0 →
    σ_red > σ v obou materiálech."""
    from beamer.model import Property
    from beamer.analysis import values_at_x_multi
    steel = Material("st", "Ocel", E=210000, G=81000, nu=0.3, rho=7.85, Re=235, Rm=360)
    alu = Material("al", "Hliník", E=70000, G=27000, nu=0.33, rho=2.7, Re=200, Rm=300)
    r = CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}, id="s", name="R")
    seg = SectionSegment(0.0, 1000.0, CrossSectionDef(), None, property_id="p")
    st = ProjectState(
        length=1000.0, supports=[Support("a", 0, "fixed", 0)],
        load_cases=[LoadCase("lc", "LC", False)],
        load_combinations=[LoadCombination("c", "C", {"t": 1.0})],
        loads=[Load("t", "torsion", "T", "lc", x=1000, Mx=5.0e5)],
        materials=[steel, alu], selected_material_id="st", sections=[r],
        properties=[Property(id="p", pid=1, name="bimetal", composite_parts=[
            {"section_id": "s", "material_id": "st", "dy": 0, "dz": 10, "angle": 0},
            {"section_id": "s", "material_id": "al", "dy": 0, "dz": -10, "angle": 0}])],
        cross_section=CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}),
        section_segments=[seg], additional_factor=1.0, selected_active_combination_id="c")
    res = solve_beam(st)
    d = values_at_x_multi(res, st, 500.0)[0]
    assert d.get("composite") and abs(d["Mk"]) > 1.0
    assert d["tau_max"] > 0.0
    for mm in d["materials"]:
        assert mm["tau_max"] > 0.0
        assert mm["mises_max"] >= mm["sigma_max"]


def test_composite_stress_per_material():
    """Napětí per materiál (bimetal pod momentem): tužší materiál (ocel) nese
    vyšší napětí; RF se počítá z jeho vlastní pevnosti."""
    from beamer.model import Property
    from beamer.composite import composite_stress
    steel = Material("st", "Ocel", E=210000, G=81000, nu=0.3, rho=7.85, Re=235, Rm=360)
    alu = Material("al", "Hliník", E=70000, G=27000, nu=0.33, rho=2.7, Re=200, Rm=300)
    r = CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}, id="s", name="R")
    st = ProjectState(length=100.0, sections=[r], materials=[steel, alu],
                      selected_material_id="st")
    prop = Property(id="p", pid=1, name="bimetal", composite_parts=[
        {"section_id": "s", "material_id": "st", "dy": 0, "dz": 10, "angle": 0},
        {"section_id": "s", "material_id": "al", "dy": 0, "dz": -10, "angle": 0},
    ])
    rows = composite_stress(st, prop, N=0.0, M=1.0e6)
    assert rows is not None and len(rows) == 2
    by = {r_["material"]: r_ for r_ in rows}
    assert by["Ocel"]["sigma_max"] > by["Hliník"]["sigma_max"]     # tužší nese víc
    # RF z vlastní pevnosti materiálu
    assert by["Ocel"]["RF_yield"] == steel.Re / by["Ocel"]["sigma_max"]


def test_section_rotation_90_swaps_Iy_Iz():
    """Natočení průřezu o 90° prohodí Iy a Iz (plocha beze změny)."""
    r0 = build_section(CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}), fem=False)
    r90 = build_section(CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}, rotation=90), fem=False)
    assert _rel(r90.A, r0.A) < 1e-9
    assert _rel(r90.Iy, r0.Iz) < 1e-3
    assert _rel(r90.Iz, r0.Iy) < 1e-3


def test_section_rotation_45_transformed_inertia():
    """Natočení o 45°: Iy=Iz=(Iy0+Iz0)/2 a |Iyz|=|Iy0−Iz0|/2 (Mohrova transformace)."""
    r0 = build_section(CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}), fem=False)
    r45 = build_section(CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}, rotation=45), fem=False)
    assert _rel(r45.Iy, (r0.Iy + r0.Iz)/2) < 1e-3
    assert _rel(r45.Iz, (r0.Iy + r0.Iz)/2) < 1e-3
    assert _rel(abs(r45.Iyz), abs(r0.Iy - r0.Iz)/2) < 1e-3


def test_pid_rotation_applied_and_beam():
    """Natočení na PID (90°) se projeví v průřezu i v průhybu nosníku
    (loading se přepočítá na natočený profil = transformované Iy)."""
    from beamer.model import Property
    r = CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}, id="s", name="R")
    seg = SectionSegment(0.0, 2000.0, CrossSectionDef(), None, property_id="p")
    st = ProjectState(
        length=2000.0, supports=[Support("a", 0, "pin", 0), Support("b", 2000, "roller", 0)],
        load_cases=[LoadCase("lc", "LC", False)],
        load_combinations=[LoadCombination("c", "C", {"f": 1.0})],
        loads=[Load("f", "point_force", "P", "lc", x=1000, Fz=-1000.0)],
        materials=[Material(**vars(MAT))], selected_material_id=MAT.id, sections=[r],
        properties=[Property(id="p", pid=1, name="X", sec1_id="s", rotation=90)],
        cross_section=CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}),
        section_segments=[seg], additional_factor=1.0, selected_active_combination_id="c")
    from beamer.sections_along import eff_defs
    s1, _ = eff_defs(st, seg)
    cs = build_section(s1, fem=False)
    r0 = build_section(r, fem=False)
    assert _rel(cs.Iy, r0.Iz) < 1e-3          # PID 90° → Iy = Iz0
    res = solve_beam(st)
    assert res.is_stable
    w_max = max(abs(p.w) for p in res.points)
    assert _rel(w_max, 1000.0*2000.0**3/(48*MAT.E*cs.Iy)) < 1e-2   # průhyb dle natočené Iy


# ═══════════════════════════════════════════════════════════════
#  KŘÍŽOVÁ VALIDACE proti sectionproperties (nezávislá knihovna, dev-only)
# ═══════════════════════════════════════════════════════════════

def test_xval_rotation_vs_sectionproperties():
    """Natočený obdélník: Iy/Iz/Iyz musí sedět s sectionproperties."""
    import pytest
    pytest.importorskip("sectionproperties")
    from sectionproperties.pre.library import rectangular_section
    from sectionproperties.analysis import Section
    for ang in (0, 30, 45, 90):
        g = rectangular_section(d=20, b=40).rotate_section(angle=ang)
        g.create_mesh(mesh_sizes=[0.5])
        s = Section(g); s.calculate_geometric_properties()
        ixx, iyy, ixy = s.get_ic()
        cs = build_section(CrossSectionDef(type="rectangle", params={"b": 40, "h": 20},
                                           rotation=ang), fem=False)
        assert _rel(cs.Iy, ixx) < 1e-6
        assert _rel(cs.Iz, iyy) < 1e-6
        assert _rel(abs(cs.Iyz), abs(ixy)) < 1e-6 or abs(cs.Iyz) < 1e-3


def test_xval_composite_vs_sectionproperties():
    """Složený dvoumateriál: EA, EIy k neutrální ose a poloha NA vs
    sectionproperties (modulem vážené / transformované charakteristiky)."""
    import pytest
    pytest.importorskip("sectionproperties")
    from sectionproperties.pre.library import rectangular_section
    from sectionproperties.pre import Material as SPMat
    from sectionproperties.analysis import Section
    from beamer.model import Property
    from beamer.composite import composite_weighted
    st_sp = SPMat("st", 210000, 0.3, 235, 7.85e-6, "grey")
    al_sp = SPMat("al", 70000, 0.33, 200, 2.7e-6, "blue")
    geom = (rectangular_section(d=20, b=40, material=st_sp).shift_section(-20, 0)
            + rectangular_section(d=20, b=40, material=al_sp).shift_section(-20, -20))
    geom.create_mesh(mesh_sizes=[0.5])
    s = Section(geom); s.calculate_geometric_properties()
    EA_sp, EIy_sp, cz_sp = s.get_ea(), s.get_eic()[0], s.get_c()[1]
    steel = Material("st", "Ocel", E=210000, G=81000, nu=0.3, rho=7.85, Re=235, Rm=360)
    alu = Material("al", "Hliník", E=70000, G=27000, nu=0.33, rho=2.7, Re=200, Rm=300)
    r = CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}, id="s", name="R")
    prop = Property(id="p", pid=1, name="c", composite_parts=[
        {"section_id": "s", "material_id": "st", "dy": 0, "dz": 10, "angle": 0},
        {"section_id": "s", "material_id": "al", "dy": 0, "dz": -10, "angle": 0}])
    stt = ProjectState(length=100, sections=[r], materials=[steel, alu], selected_material_id="st")
    w = composite_weighted(stt, prop)
    assert _rel(w.EA, EA_sp) < 1e-6
    assert _rel(w.EIy, EIy_sp) < 1e-6
    assert _rel(w.z_NA, cz_sp) < 1e-6


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


# ═══════════════════════════════════════════════════════════════
#  B2 – tagging elementů materiálem (podpora variabilního G FEM)
# ═══════════════════════════════════════════════════════════════

def test_b2_element_region_tagging():
    """Element se přiřadí té oblasti, do které padne jeho těžiště."""
    from beamer.composite_fem import assign_element_regions
    nodes = [(0.2, 0.5), (0.4, 0.5), (0.3, 0.8),      # trojúhelník v oblasti A
             (1.2, 0.5), (1.4, 0.5), (1.3, 0.8)]      # trojúhelník v oblasti B
    elements = [[0, 1, 2], [3, 4, 5]]
    regions = [(([(0, 0), (1, 0), (1, 1), (0, 1)], []), "A"),
               (([(1, 0), (2, 0), (2, 1), (1, 1)], []), "B")]
    idx, payloads = assign_element_regions(nodes, elements, regions)
    assert idx == [0, 1]
    assert payloads[idx[0]] == "A" and payloads[idx[1]] == "B"


def test_b2_tagging_respects_holes():
    """Těžiště v díře oblasti → element se do ní nezařadí."""
    from beamer.composite_fem import assign_element_regions
    nodes = [(4.9, 5.0), (5.1, 5.0), (5.0, 5.2)]      # střed velkého čtverce s dírou
    elements = [[0, 1, 2]]
    outer = [(0, 0), (10, 0), (10, 10), (0, 10)]
    hole = [(4, 4), (6, 4), (6, 6), (4, 6)]           # díra kolem středu
    regions = [((outer, [hole]), "S")]
    idx, _ = assign_element_regions(nodes, elements, regions)
    assert idx == [-1]                                 # v díře → nezařazeno


def test_b2_variable_G_reduces_and_scales():
    """Variabilní-G warping: konstantní G=1 dá IDENTICKÉ J jako dosud (regrese),
    konstantní G=2 dá GJ_eff = 2·J (správné škálování)."""
    from beamer import _fem
    _fem.set_element_order("T6")
    outer = [(-50, -30), (50, -30), (50, 30), (-50, 30)]   # obdélník 100×60
    nodes, elements = _fem.triangulate_section(outer, None)
    g = _fem.compute_geometric_properties(nodes, elements)
    cy, cz, Ixx, Iyy = g['cy'], g['cz'], g['Ixx_c'], g['Iyy_c']
    om0, K0 = _fem.solve_warping_function(nodes, elements, cy, cz)
    J0 = _fem.compute_torsion_constant(nodes, elements, om0, K0, Ixx, Iyy)
    G1 = [1.0]*len(elements)
    om1, K1 = _fem.solve_warping_function(nodes, elements, cy, cz, elem_G=G1)
    J1 = _fem.compute_torsion_constant(nodes, elements, om1, K1, Ixx, Iyy, elem_G=G1, cy=cy, cz=cz)
    assert _rel(J1, J0) < 1e-9
    G2 = [2.0]*len(elements)
    om2, K2 = _fem.solve_warping_function(nodes, elements, cy, cz, elem_G=G2)
    J2 = _fem.compute_torsion_constant(nodes, elements, om2, K2, Ixx, Iyy, elem_G=G2, cy=cy, cz=cz)
    assert _rel(J2, 2.0*J0) < 1e-9


def _composite_state(parts, sections, materials):
    from beamer.model import Property
    prop = Property(id="p", pid=1, name="c", composite_parts=parts)
    st = ProjectState(length=100, sections=sections, materials=materials,
                      selected_material_id=materials[0].id, properties=[prop])
    return st, prop


def test_b2_composite_GJ_single_material_reduces():
    """(GJ)_eff složeného ze STEJNÉHO materiálu = G·J geometrického průřezu."""
    from beamer.composite_fem import composite_torsion_GJ
    from beamer import _fem
    mat = Material("a", "Ocel", E=210000, G=81000, nu=0.3, rho=7.85, Re=235, Rm=360)
    r = CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}, id="r", name="R")
    st, prop = _composite_state(
        [{"section_id": "r", "material_id": "a", "dy": 0, "dz": 10, "angle": 0},
         {"section_id": "r", "material_id": "a", "dy": 0, "dz": -10, "angle": 0}],
        [r], [mat])
    GJ = composite_torsion_GJ(st, prop)
    # geometrická torze celku 40×40 (dvě 40×20 na sobě) přes stejný mesh
    _fem.set_element_order("T6")
    outer = [(-20, -20), (20, -20), (20, 20), (-20, 20)]
    nodes, elements = _fem.triangulate_section(outer, None)
    g = _fem.compute_geometric_properties(nodes, elements)
    om, K = _fem.solve_warping_function(nodes, elements, g["cy"], g["cz"])
    J = _fem.compute_torsion_constant(nodes, elements, om, K, g["Ixx_c"], g["Iyy_c"])
    assert _rel(GJ, 81000.0 * J) < 5e-3


def test_b2_composite_GJ_concentric_analytic():
    """Souosá tyč v trubce (různé G, ω=0): (GJ)_eff = G_tyč·J_tyč + G_trubka·J_trubka."""
    from beamer.composite_fem import composite_torsion_GJ
    steel = Material("st", "Ocel", E=210000, G=81000, nu=0.3, rho=7.85, Re=235, Rm=360)
    alu = Material("al", "Hliník", E=70000, G=27000, nu=0.33, rho=2.7, Re=200, Rm=300)
    rod = CrossSectionDef(type="circle", params={"D": 20}, id="rod", name="tyč")
    tube = CrossSectionDef(type="tube", params={"Do": 40, "t": 10}, id="tube", name="trubka")
    st, prop = _composite_state(
        [{"section_id": "rod", "material_id": "st", "dy": 0, "dz": 0, "angle": 0},
         {"section_id": "tube", "material_id": "al", "dy": 0, "dz": 0, "angle": 0}],
        [rod, tube], [steel, alu])
    GJ = composite_torsion_GJ(st, prop)
    Jrod = math.pi * 10**4 / 2
    Jtube = math.pi * (20**4 - 10**4) / 2
    GJ_anal = 81000 * Jrod + 27000 * Jtube
    assert _rel(GJ, GJ_anal) < 1e-2      # polygonizace kruhu ~0,3 %


def test_xval_composite_GJ_vs_sectionproperties():
    """Vázaný variabilní-G warping (nesymetrický spoj, různé G) vs sectionproperties.
    E_sp := G_mat → sectionproperties get_ej váží stejným modulem jako naše GJ."""
    import pytest
    pytest.importorskip("sectionproperties")
    from sectionproperties.pre.library import rectangular_section as rs
    from sectionproperties.pre import Material as SPMat
    from sectionproperties.analysis import Section
    from beamer.composite_fem import composite_torsion_GJ
    G1, G2 = 81000.0, 27000.0
    m1 = Material("a", "Tuhý", E=2*G1*1.3, G=G1, nu=0.3, rho=7.85, Re=235, Rm=360)
    m2 = Material("b", "Měkký", E=2*G2*1.3, G=G2, nu=0.3, rho=2.7, Re=200, Rm=300)
    r = CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}, id="r", name="R")
    st, prop = _composite_state(
        [{"section_id": "r", "material_id": "a", "dy": 0, "dz": 10, "angle": 0},
         {"section_id": "r", "material_id": "b", "dy": 0, "dz": -10, "angle": 0}],
        [r], [m1, m2])
    GJ = composite_torsion_GJ(st, prop)
    a_sp = SPMat("a", G1, 0.3, 235, 7.85e-6, "grey")
    b_sp = SPMat("b", G2, 0.3, 200, 2.7e-6, "blue")
    geom = (rs(d=20, b=40, material=a_sp).shift_section(x_offset=-20, y_offset=0)
            + rs(d=20, b=40, material=b_sp).shift_section(x_offset=-20, y_offset=-20))
    geom.create_mesh(mesh_sizes=[1.0])
    s = Section(geom); s.calculate_geometric_properties(); s.calculate_warping_properties()
    assert _rel(GJ, s.get_ej()) < 2e-2


def test_b2_composite_von_mises_torsion():
    """Plný von Mises složeného: čistý ohyb → τ=0, mises=σ; čistá torze → σ=0,
    mises=√3·τ a τ per materiál ≈ Gᵢ·θ'·r (souosá tyč v trubce)."""
    from beamer.composite_fem import composite_stress_field, composite_torsion_GJ
    steel = Material("st", "Ocel", E=210000, G=81000, nu=0.3, rho=7.85, Re=235, Rm=360)
    alu = Material("al", "Hliník", E=70000, G=27000, nu=0.33, rho=2.7, Re=200, Rm=300)
    rod = CrossSectionDef(type="circle", params={"D": 20}, id="rod", name="tyč")
    tube = CrossSectionDef(type="tube", params={"Do": 40, "t": 10}, id="tube", name="trubka")
    st, prop = _composite_state(
        [{"section_id": "rod", "material_id": "st", "dy": 0, "dz": 0, "angle": 0},
         {"section_id": "tube", "material_id": "al", "dy": 0, "dz": 0, "angle": 0}],
        [rod, tube], [steel, alu])
    # čistý ohyb → τ=0, mises=σ
    fb = composite_stress_field(st, prop, 0.0, 1.0e6, 0.0)
    for a in fb["materials"].values():
        assert a["tau_max"] < 1e-6
        assert _rel(a["mises_max"], a["sigma_max"]) < 1e-9
    # čistá torze → σ=0, mises=√3·τ, τ per materiál ≈ Gᵢ·θ'·r
    Mk = 1.0e6
    GJ = composite_torsion_GJ(st, prop)
    thp = Mk / GJ
    ft = composite_stress_field(st, prop, 0.0, 0.0, Mk)
    assert ft["materials"]["st"]["sigma_max"] < 1e-6
    assert _rel(ft["materials"]["al"]["mises_max"],
                math.sqrt(3) * ft["materials"]["al"]["tau_max"]) < 1e-9
    assert _rel(ft["materials"]["al"]["tau_max"], 27000 * thp * 20) < 3e-2   # trubka r=20
    assert _rel(ft["materials"]["st"]["tau_max"], 81000 * thp * 10) < 6e-2   # tyč r=10 (rozhraní)


def test_b2_composite_transverse_shear_reduces():
    """Transverzální smyk τ_V složeného ze STEJNÉHO materiálu = Žuravskij
    obdélníku: τ_max = 1.5·V/A (E-vážený Žuravskij se redukuje na klasický)."""
    from beamer.composite_fem import composite_stress_field
    steel = Material("st", "Ocel", E=210000, G=81000, nu=0.3, rho=7.85, Re=235, Rm=360)
    r = CrossSectionDef(type="rectangle", params={"b": 40, "h": 20}, id="r", name="R")
    st, prop = _composite_state(
        [{"section_id": "r", "material_id": "st", "dy": 0, "dz": 10, "angle": 0},
         {"section_id": "r", "material_id": "st", "dy": 0, "dz": -10, "angle": 0}],
        [r], [steel])
    V = 1000.0
    f = composite_stress_field(st, prop, 0.0, 0.0, 0.0, V)
    tauV = f["materials"]["st"]["tau_max"]
    assert _rel(tauV, 1.5 * V / (40 * 40)) < 1e-3      # 40×40, τ_max = 1.5 V/A
