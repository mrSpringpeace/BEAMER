"""Beam solver – přímá metoda tuhosti (Euler-Bernoulli / Timoshenko).

Port původního TS solveru. Rovinný prutový prvek, 4 DOF na uzel:
  0: u  (axiální posun)
  1: w  (příčný průhyb)
  2: φ  (ohybové pootočení)
  3: θ  (torzní pootočení)

Jednotky: mm, N, MPa(N/mm²). Tah kladný. Příčné zatížení +nahoru.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
import numpy as np

from .section import build_section, CrossSection


@dataclass
class BeamPoint:
    x: float
    N: float      # osová síla (N)
    V: float      # posouvající síla (N)
    M: float      # ohybový moment (N·mm)
    Mk: float     # kroutící moment (N·mm)
    w: float      # průhyb (mm)
    phi: float    # ohybové pootočení (rad)
    theta: float  # torzní pootočení (rad)


@dataclass
class Reaction:
    x: float
    support_type: str
    Rx: float
    Rz: float
    Ry: float          # ohybová reakce (N·mm)
    Rx_torsion: float  # torzní reakce (N·mm)


@dataclass
class SolverResult:
    points: list
    reactions: list
    elements: list
    is_stable: bool
    section: CrossSection = None
    error_message: str = ""
    resolver: object = None      # SectionResolver (proměnný průřez)


def _load_multiplier(state, load_case_id):
    comb = state.active_combination()
    factors = comb.factors if comb else {}
    comb_f = factors.get(load_case_id, 0.0)
    # zatížení = početní (ultimate) síly × volitelný dodatečný součinitel
    return comb_f * getattr(state, "additional_factor", 1.0)


def solve_beam(state) -> SolverResult:
    material = state.material()
    E, G = material.E, material.G

    length = state.length

    # ── průřez(y): jeden na celý nosník, prizmatické úseky, nebo tapered ──
    from .sections_along import SectionResolver, normalized_segments
    resolver = SectionResolver(state)
    try:
        rep_section = resolver.at(length/2)     # reprezentativní průřez (pro UI)
    except Exception as e:
        return SolverResult([], [], [], False, None,
                            f"Chyba při výpočtu průřezu: {e}")
    if not rep_section.valid:
        return SolverResult([], [], [], False, None, "Neplatný průřez.")

    def elem_props(x_mid):
        cs = resolver.at(x_mid)
        A = cs.A
        Iy = cs.Iy
        J = cs.IT
        kappa = cs.kappa
        As = cs.Asz if cs.Asz > 0 else A * kappa
        E_e = resolver.E_at(x_mid)      # per-úsekové E (materiál úseku / override)
        if E_e is None:
            E_e = E
        G_e = resolver.G_at(x_mid)      # per-úsekové G (materiál úseku)
        if G_e is None:
            G_e = G
        return A, Iy, J, As, cs, E_e, G_e

    # ── 1. Diskretizace ──
    xs = {0.0, float(length)}
    for s in state.supports:
        if 0 <= s.x <= length:
            xs.add(float(s.x))
    for h in state.hinges:
        if 0 <= h.x <= length:
            xs.add(float(h.x))
    for ld in state.loads:
        if ld.type == "distributed":
            if 0 <= ld.x1 <= length:
                xs.add(float(ld.x1))
            if 0 <= ld.x2 <= length:
                xs.add(float(ld.x2))
        else:
            if 0 <= ld.x <= length:
                xs.add(float(ld.x))
    # hranice úseků průřezu
    segs = normalized_segments(state)
    for sg in segs:
        if 0 <= sg.x1 <= length:
            xs.add(float(sg.x1))
        if 0 <= sg.x2 <= length:
            xs.add(float(sg.x2))
    xcoords = sorted(xs)
    filtered = []
    for x in xcoords:
        if not filtered or abs(x - filtered[-1]) > 1e-3:
            filtered.append(x)

    # Jemné dělení sítě. Důvod: kubické Hermitovy funkce nezachytí přesně
    # průhyb pod spojitým zatížením s málo prvky → bez zhuštění se w podceňuje.
    # (VVÚ M/V jsou přesné vždy – rekonstruují se statikou.) Tapered úseky
    # dělíme jemněji kvůli stepwise-konstantnímu průřezu.
    def in_tapered(xa, xb):
        xm = (xa+xb)/2
        for sg in segs:
            if sg.tapered and sg.x1 - 1e-6 <= xm <= sg.x2 + 1e-6:
                return sg
        return None
    step_global = max(length/40.0, 1e-3)      # ~40 prvků na celý nosník
    densified = [filtered[0]]
    for i in range(len(filtered)-1):
        xa, xb = filtered[i], filtered[i+1]
        step = step_global
        sg = in_tapered(xa, xb)
        if sg is not None:
            step = min(step, max((sg.x2 - sg.x1)/20.0, 1e-3))
        n_sub = max(1, int(math.ceil((xb-xa)/step)))
        for k in range(1, n_sub+1):
            densified.append(xa + (xb-xa)*k/n_sub)
    filtered = densified

    nodes = [{"id": i, "x": x, "dof": i*4} for i, x in enumerate(filtered)]
    num_nodes = len(nodes)
    num_dof = num_nodes * 4

    def node_at(x):
        for nd in nodes:
            if abs(nd["x"] - x) < 1e-3:
                return nd
        return None

    # ── elementy (každý si nese vlastní průřez podle středu) ──
    elements = []
    for i in range(num_nodes - 1):
        ns, ne = nodes[i], nodes[i+1]
        has_hinge = any(abs(h.x - ns["x"]) < 1e-3 for h in state.hinges)
        x_mid = (ns["x"] + ne["x"]) / 2
        A_e, Iy_e, J_e, As_e, cs_e, E_e, G_e = elem_props(x_mid)
        elements.append({
            "id": i, "ns": ns, "ne": ne,
            "L": ne["x"] - ns["x"],
            "release_start": has_hinge, "release_end": False,
            "xs": ns["x"], "xe": ne["x"],
            "A": A_e, "Iy": Iy_e, "J": J_e, "As": As_e, "section": cs_e,
            "E": E_e, "G": G_e,
        })

    K = np.zeros((num_dof, num_dof))
    F = np.zeros(num_dof)

    theory = state.theory

    def k_element(L_e, A, Iy, J, As, E_e, G_e):
        k = np.zeros((8, 8))
        ka = E_e*A/L_e
        k[0, 0] = ka; k[0, 4] = -ka; k[4, 0] = -ka; k[4, 4] = ka
        kt = G_e*J/L_e
        k[3, 3] = kt; k[3, 7] = -kt; k[7, 3] = -kt; k[7, 7] = kt
        Phi = (12*E_e*Iy)/(G_e*As*L_e**2) if theory == "timoshenko" else 0.0
        f = (E_e*Iy)/(L_e**3*(1+Phi))
        kb11 = 12*f
        kb12 = 6*L_e*f
        kb22 = (4+Phi)*L_e**2*f
        kb26 = (2-Phi)*L_e**2*f
        k[1, 1] = kb11; k[1, 2] = kb12; k[1, 5] = -kb11; k[1, 6] = kb12
        k[2, 1] = kb12; k[2, 2] = kb22; k[2, 5] = -kb12; k[2, 6] = kb26
        k[5, 1] = -kb11; k[5, 2] = -kb12; k[5, 5] = kb11; k[5, 6] = -kb12
        k[6, 1] = kb12; k[6, 2] = kb26; k[6, 5] = -kb12; k[6, 6] = kb22
        return k

    for elem in elements:
        L_e = elem["L"]
        k_e = k_element(L_e, elem["A"], elem["Iy"], elem["J"], elem["As"], elem["E"], elem["G"])

        released = []
        if elem["release_start"]:
            released.append(2)
        if elem["release_end"]:
            released.append(6)
        if released:
            active = [i for i in range(8) if i not in released]
            kii = k_e[np.ix_(active, active)]
            kir = k_e[np.ix_(active, released)]
            kri = k_e[np.ix_(released, active)]
            krr = k_e[np.ix_(released, released)]
            try:
                kcond = kii - kir @ np.linalg.inv(krr) @ kri
                k_new = np.zeros((8, 8))
                for r, ai in enumerate(active):
                    for c, aj in enumerate(active):
                        k_new[ai, aj] = kcond[r, c]
                k_e = k_new
            except np.linalg.LinAlgError:
                pass

        l2g = [elem["ns"]["dof"]+0, elem["ns"]["dof"]+1, elem["ns"]["dof"]+2, elem["ns"]["dof"]+3,
               elem["ne"]["dof"]+0, elem["ne"]["dof"]+1, elem["ne"]["dof"]+2, elem["ne"]["dof"]+3]
        for r in range(8):
            for c in range(8):
                K[l2g[r], l2g[c]] += k_e[r, c]

    # ── zatížení ──
    for ld in state.loads:
        mult = _load_multiplier(state, ld.load_case_id)
        if mult == 0:
            continue
        if ld.type == "point_force":
            nd = node_at(ld.x)
            if nd:
                F[nd["dof"]+0] += ld.Fx*mult
                F[nd["dof"]+1] += ld.Fz*mult
                if abs(ld.eccentricity) > 1e-5:
                    F[nd["dof"]+3] += ld.Fz*ld.eccentricity*mult
        elif ld.type == "moment":
            nd = node_at(ld.x)
            if nd:
                F[nd["dof"]+2] += ld.My*mult
        elif ld.type == "torsion":
            nd = node_at(ld.x)
            if nd:
                F[nd["dof"]+3] += ld.Mx*mult
        elif ld.type == "distributed":
            for elem in elements:
                os_ = max(elem["xs"], ld.x1)
                oe = min(elem["xe"], ld.x2)
                if oe - os_ > 1e-3:
                    dlen = ld.x2 - ld.x1
                    def qval(x):
                        return ld.q1 + (ld.q2-ld.q1)*(x-ld.x1)/dlen
                    qA, qB = qval(os_), qval(oe)
                    L_e = elem["L"]
                    F[elem["ns"]["dof"]+1] += (L_e/20)*(7*qA+3*qB)*mult
                    F[elem["ns"]["dof"]+2] += (L_e**2/60)*(3*qA+2*qB)*mult
                    F[elem["ne"]["dof"]+1] += (L_e/20)*(3*qA+7*qB)*mult
                    F[elem["ne"]["dof"]+2] += -(L_e**2/60)*(2*qA+3*qB)*mult

    # ── okrajové podmínky ──
    constrained = set()
    skew_rollers = []      # (dof_u, sinα, cosα) – šikmé rolny přes penaltu
    for sup in state.supports:
        nd = node_at(sup.x)
        if not nd:
            continue
        d = nd["dof"]
        if sup.type == "fixed":
            constrained |= {d, d+1, d+2, d+3}
        elif sup.type == "pin":
            constrained |= {d, d+1, d+3}
        elif sup.type == "roller":
            rad = np.radians(sup.angle or 0.0)
            s_, c_ = float(np.sin(rad)), float(np.cos(rad))
            if abs(s_) < 1e-5:
                constrained.add(d+1)          # vodorovná rolna → drží w
            elif abs(c_) < 1e-5:
                constrained.add(d)            # svislá → drží u
            else:
                skew_rollers.append((d, s_, c_))

    if not any(dof % 4 == 3 for dof in constrained) and nodes:
        constrained.add(nodes[0]["dof"]+3)
    if not any(dof % 4 == 0 for dof in constrained) and nodes and not skew_rollers:
        constrained.add(nodes[0]["dof"]+0)

    K_solved = K.copy()
    F_solved = F.copy()

    # šikmá rolna: vazba ve směru normály n = (sin α, cos α) penaltovou
    # pružinou v rovině (u, w). Penalta jde JEN do K_solved – reakce se pak
    # rekonstruují z původního K: R = K·U − F = −K_pen·U ∥ n.
    if skew_rollers:
        # 1e5× max. diagonála: dost tuhé na vazbu (rel. chyba ~1e-5),
        # ale nezničí podmíněnost soustavy (float64).
        kpen = 1e5 * max(float(np.abs(np.diag(K)).max()), 1.0)
        for d, s_, c_ in skew_rollers:
            K_solved[d, d] += kpen * s_ * s_
            K_solved[d, d+1] += kpen * s_ * c_
            K_solved[d+1, d] += kpen * s_ * c_
            K_solved[d+1, d+1] += kpen * c_ * c_
    for dof in constrained:
        K_solved[dof, :] = 0
        K_solved[dof, dof] = 1.0
        F_solved[dof] = 0.0

    try:
        U = np.linalg.solve(K_solved, F_solved)
    except np.linalg.LinAlgError:
        return SolverResult([], [], [], False, rep_section,
                            "Nestabilní soustava (mechanismus / nedostatečné podepření).")
    # LAPACK téměř-singulární soustavu „vyřeší" s nesmysly – kontrola
    # konečnosti a rezidua odhalí mechanismus/nedostatečné podepření.
    if not np.all(np.isfinite(U)):
        return SolverResult([], [], [], False, rep_section,
                            "Nestabilní soustava (mechanismus / nedostatečné podepření).")
    resid = float(np.linalg.norm(K_solved @ U - F_solved))
    if resid > 1e-6 * (float(np.linalg.norm(F_solved)) + 1.0):
        return SolverResult([], [], [], False, rep_section,
                            "Nestabilní soustava (mechanismus / nedostatečné podepření).")

    # ── reakce ──
    R = K @ U - F
    reactions = []
    for sup in state.supports:
        nd = node_at(sup.x)
        if not nd:
            continue
        d = nd["dof"]
        reactions.append(Reaction(sup.x, sup.type, R[d], R[d+1], R[d+2], R[d+3]))

    # ── VVÚ ──
    # Konvence: M kladný = tah na dolním vlákně (sagging). V = dM/dx.
    # Koncové momenty prvku z f = k·u − f_eq (statika), posouvající síla
    # dopočtena z okrajové podmínky M(L)=Mj, skutečné zatížení integrováno
    # analyticky (kvadraticky přesné i pro spojité zatížení).
    all_points = []
    elem_results = []
    NG = 201  # bodů jemné mřížky pro integraci zatížení v prvku

    def q_total_at(sg):
        """Hodnota spojitého zatížení (×mult) v globální poloze sg [N/mm]."""
        q = 0.0
        for ld in state.loads:
            if ld.type != "distributed":
                continue
            if ld.x1 - 1e-9 <= sg <= ld.x2 + 1e-9:
                lm = _load_multiplier(state, ld.load_case_id)
                if lm == 0:
                    continue
                dlen = ld.x2 - ld.x1
                qv = ld.q1 + (ld.q2 - ld.q1)*(sg - ld.x1)/dlen if dlen > 1e-12 else ld.q1
                q += qv * lm
        return q

    for elem in elements:
        L_e = elem["L"]
        sd = elem["ns"]["dof"]
        ed = elem["ne"]["dof"]
        u1, w1, phi1, th1 = U[sd], U[sd+1], U[sd+2], U[sd+3]
        u2, w2, phi2, th2 = U[ed], U[ed+1], U[ed+2], U[ed+3]

        A_e, Iy_e, J_e, As_e, E_e, G_e = (elem["A"], elem["Iy"], elem["J"], elem["As"],
                                          elem["E"], elem["G"])
        Phi_e = (12*E_e*Iy_e)/(G_e*As_e*L_e**2) if theory == "timoshenko" else 0.0
        fe = (E_e*Iy_e)/(L_e**3*(1+Phi_e))
        kb11 = 12*fe
        kb12 = 6*L_e*fe
        kb22 = (4+Phi_e)*L_e**2*fe
        kb26 = (2-Phi_e)*L_e**2*fe
        kb = np.array([
            [kb11,  kb12, -kb11,  kb12],
            [kb12,  kb22, -kb12,  kb26],
            [-kb11, -kb12, kb11, -kb12],
            [kb12,  kb26, -kb12,  kb22],
        ])
        ub = np.array([w1, phi1, w2, phi2])

        # ekvivalentní uzlové síly od spojitého zatížení na CELÉM prvku
        feq = np.zeros(4)
        for ld in state.loads:
            lm = _load_multiplier(state, ld.load_case_id)
            if lm == 0 or ld.type != "distributed":
                continue
            dlen = ld.x2 - ld.x1
            def qval(x):
                return ld.q1 + (ld.q2-ld.q1)*(x-ld.x1)/dlen if dlen > 1e-12 else ld.q1
            a = max(elem["xs"], ld.x1)
            b = min(elem["xe"], ld.x2)
            if b - a > 1e-9 and abs(b - a - L_e) < 1e-6:
                qA, qB = qval(a)*lm, qval(b)*lm
                feq += np.array([(L_e/20)*(7*qA+3*qB), (L_e**2/60)*(3*qA+2*qB),
                                 (L_e/20)*(3*qA+7*qB), -(L_e**2/60)*(2*qA+3*qB)])

        fend = kb @ ub - feq        # uzlové síly [Fz1, M1, Fz2, M2]
        Mi = 0.0 if elem["release_start"] else -fend[1]
        Mj = 0.0 if elem["release_end"] else fend[3]

        # jemná mřížka pro kumulativní integrály zatížení (lokální s = 0..L)
        sgrid = np.linspace(0.0, L_e, NG)
        qgrid = np.array([q_total_at(elem["xs"] + s) for s in sgrid])
        A0 = np.concatenate([[0.0], np.cumsum((qgrid[1:]+qgrid[:-1])/2*np.diff(sgrid))])      # ∫q ds
        A1 = np.concatenate([[0.0], np.cumsum((qgrid[1:]*sgrid[1:]+qgrid[:-1]*sgrid[:-1])/2*np.diff(sgrid))])  # ∫s·q ds
        IL = L_e*A0[-1] - A1[-1]    # ∫(L−s)q ds
        Vi = (Mj - Mi - IL)/L_e if L_e > 1e-12 else 0.0

        N = (E_e*A_e/L_e)*(u2-u1)
        Mk = (G_e*J_e/L_e)*(th2-th1)

        local_points = []
        nsteps = 100
        for i in range(nsteps+1):
            xi = i/nsteps
            xloc = xi*L_e

            # IIE interpolace (Reddy, Interdependent Interpolation Element):
            # w i φ konzistentní s Timoshenkovým prvkem; pro Φ=0 přechází
            # přesně v klasické Hermitovy funkce (Euler-Bernoulli).
            op = 1.0 + Phi_e
            N1 = (1 - 3*xi**2 + 2*xi**3 + Phi_e*(1 - xi)) / op
            N2 = L_e*(xi - 2*xi**2 + xi**3 + 0.5*Phi_e*(xi - xi**2)) / op
            N3 = (3*xi**2 - 2*xi**3 + Phi_e*xi) / op
            N4 = L_e*(-xi**2 + xi**3 - 0.5*Phi_e*(xi - xi**2)) / op
            w = N1*w1 + N2*phi1 + N3*w2 + N4*phi2
            H1 = 6*(xi**2 - xi) / (L_e*op)
            H2 = (3*xi**2 - 4*xi + 1 + Phi_e*(1 - xi)) / op
            H3 = 6*(xi - xi**2) / (L_e*op)
            H4 = (3*xi**2 - 2*xi + Phi_e*xi) / op
            phi = H1*w1 + H2*phi1 + H3*w2 + H4*phi2
            theta = th1 + (th2-th1)*xi

            a0 = float(np.interp(xloc, sgrid, A0))
            a1 = float(np.interp(xloc, sgrid, A1))
            I1 = xloc*a0 - a1           # ∫₀ˣ(x−s)q ds
            M = Mi + Vi*xloc + I1
            V = Vi + a0

            local_points.append(BeamPoint(elem["xs"]+xloc, N, V, M, Mk, w, phi, theta))

        elem_results.append({"id": elem["id"], "xs": elem["xs"], "xe": elem["xe"],
                             "points": local_points, "section": elem["section"]})
        if not all_points:
            all_points.extend(local_points)
        else:
            all_points.extend(local_points[1:])

    res = SolverResult(all_points, reactions, elem_results, True, rep_section)
    res.resolver = resolver
    return res
