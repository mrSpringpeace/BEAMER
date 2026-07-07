"""Beam solver – přímá metoda tuhosti (Euler-Bernoulli / Timoshenko).

Prostorový prutový prvek, 6 DOF na uzel:
  0: u   (axiální posun, x)
  1: w   (příčný průhyb svislý, z)      – ohyb v rovině x-z, tuhost EIy
  2: θy  (ohybové pootočení kolem y)
  3: v   (příčný průhyb vodorovný, y)   – ohyb v rovině x-y, tuhost EIz
  4: θz  (ohybové pootočení kolem z)
  5: θx  (torzní pootočení)

FÁZE A (biaxiál): dvě ohybové roviny jsou zatím DEKUPLOVANÉ (bez Iyz vazby) –
planar úloha (Fy=Mz=0) dává identické výsledky jako dřívější 4-DOF solver.
Iyz spřažení (šikmý ohyb) = fáze B.

Jednotky: mm, N, MPa(N/mm²). Tah kladný. Svislé zatížení +nahoru.
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
    V: float      # posouvající síla svislá V_z (N) – rovina x-z
    M: float      # ohybový moment M_y (N·mm) – rovina x-z
    Mk: float     # kroutící moment (N·mm)
    w: float      # průhyb svislý (mm, z)
    phi: float    # ohybové pootočení θy (rad)
    theta: float  # torzní pootočení (rad)
    # druhá rovina (x-y) – biaxiál (fáze A: nenulové jen při Fy/Mz)
    v: float = 0.0      # průhyb vodorovný (mm, y)
    V_y: float = 0.0    # posouvající síla vodorovná (N)
    M_z: float = 0.0    # ohybový moment kolem osy z (N·mm)
    phi_z: float = 0.0  # ohybové pootočení θz (rad)


@dataclass
class Reaction:
    x: float
    support_type: str
    Rx: float
    Rz: float
    Ry: float          # momentová reakce kolem y (N·mm)
    Rx_torsion: float  # torzní reakce (N·mm)
    Ry_force: float = 0.0   # vodorovná silová reakce (N, y) – biaxiál
    Rz_moment: float = 0.0  # momentová reakce kolem z (N·mm) – biaxiál


@dataclass
class SolverResult:
    points: list
    reactions: list
    elements: list
    is_stable: bool
    section: CrossSection = None
    error_message: str = ""
    resolver: object = None      # SectionResolver (proměnný průřez)


def _load_multiplier(state, ld, factors=None):
    """Násobitel zatížení `ld` v dané kombinaci. Faktory jsou primárně klíčované
    podle id zatížení (nový model „vyber zatížení do kombinace"); pokud klíč
    chybí, zkusí se id zatěžovacího stavu (zpětná kompatibilita se starým
    modelem faktor×stav)."""
    if factors is None:
        comb = state.active_combination()
        factors = comb.factors if comb else {}
    comb_f = factors.get(getattr(ld, "id", None))
    if comb_f is None:
        comb_f = factors.get(getattr(ld, "load_case_id", None), 0.0)
    # zatížení = početní (ultimate) síly × volitelný dodatečný součinitel
    return comb_f * getattr(state, "additional_factor", 1.0)


def solve_beam(state, factors=None) -> SolverResult:
    """`factors` (dict lc_id→faktor) přepíše aktivní kombinaci – umožní spočítat
    libovolnou kombinaci/stav bez mutace state (pro Load Case Builder)."""
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
        Iz = cs.Iz
        Iyz = getattr(cs, "Iyz", 0.0)
        J = cs.IT
        kappa = cs.kappa
        As = cs.Asz if cs.Asz > 0 else A * kappa
        Asy = cs.Asy if getattr(cs, "Asy", 0.0) > 0 else A * kappa
        E_e = resolver.E_at(x_mid)      # per-úsekové E (materiál úseku / override)
        if E_e is None:
            E_e = E
        G_e = resolver.G_at(x_mid)      # per-úsekové G (materiál úseku)
        if G_e is None:
            G_e = G
        # efektivní tuhosti: pro složený PID z různých materiálů modulem vážené
        # (EA=ΣEᵢAᵢ, EIy/EIz k neutrální ose), jinak E·geometrie. Torze složeného =
        # variabilní-G FEM (GJ)_eff (B2); jinak G·J. Smyková tuhost složeného
        # GAs = ΣGᵢAᵢ·(As/A) – vážená plocha × smykový poměr sjednocené geometrie.
        w = resolver.weighted_at(x_mid)
        if w is not None:
            EA, EIy = w.EA, w.EIy
            EIz = getattr(w, "EIz", None) or E_e * Iz
            EIyz = getattr(w, "EIyz", None)
            if EIyz is None:
                EIyz = E_e * Iyz
            GJ = w.GJ if getattr(w, "GJ", None) else G_e * J
            GA_w = getattr(w, "GA", None)
            GAs = GA_w * (As / A) if (GA_w and A > 1e-12) else G_e * As
            GAsy = GA_w * (Asy / A) if (GA_w and A > 1e-12) else G_e * Asy
        else:
            EA, EIy, EIz, EIyz = E_e * A, E_e * Iy, E_e * Iz, E_e * Iyz
            GJ = G_e * J
            GAs = G_e * As
            GAsy = G_e * Asy
        return EA, EIy, EIz, EIyz, GJ, GAs, GAsy, cs

    # ── 1. Diskretizace ──
    xs = {0.0, float(length)}
    for s in state.supports:
        if 0 <= s.x <= length:
            xs.add(float(s.x))
    for h in state.hinges:
        if 0 <= h.x <= length:
            xs.add(float(h.x))
    for ld in state.loads:
        if ld.type in ("distributed", "thermal"):
            # hranice oblasti MUSÍ být uzly – element nesmí přeskakovat rozhraní
            # (u teploty by dostal ΔT dle svého středu → chyba N až ~2 %)
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
    from .sections_along import eff_defs
    def in_tapered(xa, xb):
        xm = (xa+xb)/2
        for sg in segs:
            if sg.x1 - 1e-6 <= xm <= sg.x2 + 1e-6:
                if eff_defs(state, sg)[1] is not None:   # náběh (PID i inline)
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

    nodes = [{"id": i, "x": x, "dof": i*6} for i, x in enumerate(filtered)]
    num_nodes = len(nodes)
    num_dof = num_nodes * 6

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
        EA_e, EIy_e, EIz_e, EIyz_e, GJ_e, GAs_e, GAsy_e, cs_e = elem_props(x_mid)
        mat_e = resolver.material_at(x_mid)
        alpha_e = float(getattr(mat_e, "alpha", 0.0) or 0.0)
        elements.append({
            "id": i, "ns": ns, "ne": ne,
            "L": ne["x"] - ns["x"],
            "release_start": has_hinge, "release_end": False,
            "xs": ns["x"], "xe": ne["x"],
            "EA": EA_e, "EIy": EIy_e, "EIz": EIz_e, "EIyz": EIyz_e, "GJ": GJ_e,
            "GAs": GAs_e, "GAsy": GAsy_e, "section": cs_e,
            "alpha": alpha_e,
        })

    K = np.zeros((num_dof, num_dof))
    F = np.zeros(num_dof)

    theory = state.theory

    def _bending_block(EI, GA, L_e):
        """4×4 ohybová tuhost [w1,θ1,w2,θ2] (Timoshenko IIE / Euler-Bernoulli)."""
        Phi = (12*EI)/(GA*L_e**2) if theory == "timoshenko" else 0.0
        f = EI/(L_e**3*(1+Phi))
        b11 = 12*f
        b12 = 6*L_e*f
        b22 = (4+Phi)*L_e**2*f
        b26 = (2-Phi)*L_e**2*f
        return np.array([[b11,  b12, -b11,  b12],
                         [b12,  b22, -b12,  b26],
                         [-b11, -b12, b11, -b12],
                         [b12,  b26, -b12,  b22]])

    def _eb_bending(EI, L_e):
        """Euler-Bernoulli ohybová 4×4 (Φ=0) – pro Iyz křížové spřažení."""
        f = EI/L_e**3
        return f*np.array([[12,     6*L_e,   -12,     6*L_e],
                           [6*L_e,  4*L_e**2, -6*L_e,  2*L_e**2],
                           [-12,   -6*L_e,    12,     -6*L_e],
                           [6*L_e,  2*L_e**2, -6*L_e,  4*L_e**2]])

    def k_element(L_e, EA, EIy, EIz, EIyz, GJ, GAs, GAsy):
        k = np.zeros((12, 12))
        ka = EA/L_e
        k[0, 0] = ka; k[0, 6] = -ka; k[6, 0] = -ka; k[6, 6] = ka
        kt = GJ/L_e
        k[5, 5] = kt; k[5, 11] = -kt; k[11, 5] = -kt; k[11, 11] = kt
        idx1 = [1, 2, 7, 8]     # rovina x-z (w,θy)
        idx2 = [3, 4, 9, 10]    # rovina x-y (v,θz)
        kb1 = _bending_block(EIy, GAs, L_e)          # EIy
        kb2 = _bending_block(EIz, GAsy, L_e)         # EIz
        kc = _eb_bending(EIyz, L_e) if abs(EIyz) > 1e-30 else None   # Iyz spřažení
        for a in range(4):
            for c in range(4):
                k[idx1[a], idx1[c]] += kb1[a, c]
                k[idx2[a], idx2[c]] += kb2[a, c]
                if kc is not None:                   # křížové bloky (šikmý ohyb)
                    k[idx1[a], idx2[c]] += kc[a, c]
                    k[idx2[a], idx1[c]] += kc[a, c]
        return k

    for elem in elements:
        L_e = elem["L"]
        k_e = k_element(L_e, elem["EA"], elem["EIy"], elem["EIz"], elem["EIyz"],
                        elem["GJ"], elem["GAs"], elem["GAsy"])

        # kloub = uvolnění ohybových pootočení (obě roviny) na daném konci
        released = []
        if elem["release_start"]:
            released += [2, 4]     # θy, θz na začátku
        if elem["release_end"]:
            released += [8, 10]    # θy, θz na konci
        if released:
            active = [i for i in range(12) if i not in released]
            kii = k_e[np.ix_(active, active)]
            kir = k_e[np.ix_(active, released)]
            kri = k_e[np.ix_(released, active)]
            krr = k_e[np.ix_(released, released)]
            try:
                kcond = kii - kir @ np.linalg.inv(krr) @ kri
                k_new = np.zeros((12, 12))
                for r, ai in enumerate(active):
                    for c, aj in enumerate(active):
                        k_new[ai, aj] = kcond[r, c]
                k_e = k_new
            except np.linalg.LinAlgError:
                pass

        ds, de = elem["ns"]["dof"], elem["ne"]["dof"]
        l2g = [ds+0, ds+1, ds+2, ds+3, ds+4, ds+5,
               de+0, de+1, de+2, de+3, de+4, de+5]
        for r in range(12):
            for c in range(12):
                K[l2g[r], l2g[c]] += k_e[r, c]

    # ── zatížení ──
    for ld in state.loads:
        mult = _load_multiplier(state, ld, factors)
        if mult == 0:
            continue
        if ld.type == "point_force":
            nd = node_at(ld.x)
            if nd:
                F[nd["dof"]+0] += ld.Fx*mult
                F[nd["dof"]+1] += ld.Fz*mult                    # svislá (w)
                F[nd["dof"]+3] += getattr(ld, "Fy", 0.0)*mult   # vodorovná (v)
                if abs(ld.eccentricity) > 1e-5:
                    F[nd["dof"]+5] += ld.Fz*ld.eccentricity*mult  # Mk = Fz·e (torze)
        elif ld.type == "moment":
            nd = node_at(ld.x)
            if nd:
                F[nd["dof"]+2] += ld.My*mult                    # ohyb kolem y (θy)
                F[nd["dof"]+4] += getattr(ld, "Mz", 0.0)*mult   # ohyb kolem z (θz)
        elif ld.type == "torsion":
            nd = node_at(ld.x)
            if nd:
                F[nd["dof"]+5] += ld.Mx*mult
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

    # ── teplotní zatížení: ekvivalentní uzlové síly ──
    # Rovnoměrné ΔT → osová dilatace ε_th=α·ΔT; při vazbě vzniká osová síla
    # (vektor baru EA·α·ΔT·[−1,+1]). Gradient přes výšku (ΔT_grad = T_horní−T_dolní)
    # → teplotní křivost κ_th=α·ΔT_grad/h a moment M_th=EIy·κ_th; ekvivalentní
    # uzlové momenty [0,−M_th,0,+M_th] (jako fixed-end od gradientu). Recovery
    # odečte teplotní přetvoření z N i z M (volný prvek → napětí 0, vázaný → pnutí).
    def dT_at(sg):
        vu = vg = 0.0
        for ld in state.loads:
            if ld.type != "thermal":
                continue
            if ld.x1 - 1e-9 <= sg <= ld.x2 + 1e-9:
                lm = _load_multiplier(state, ld, factors)
                vu += float(getattr(ld, "dT", 0.0) or 0.0) * lm
                vg += float(getattr(ld, "dT_grad", 0.0) or 0.0) * lm
        return vu, vg
    for elem in elements:
        dT_e, dTg_e = dT_at((elem["xs"] + elem["xe"]) / 2.0)
        elem["dT"] = dT_e
        # rovnoměrná složka → osová síla
        if abs(dT_e) > 1e-12:
            N_th = elem["EA"] * elem["alpha"] * dT_e     # EA·α·ΔT
            F[elem["ns"]["dof"]+0] += -N_th
            F[elem["ne"]["dof"]+0] += +N_th
        # gradient → teplotní moment (křivost)
        M_th = 0.0
        if abs(dTg_e) > 1e-12 and elem["alpha"] != 0.0:
            cs = elem["section"]
            h = float(getattr(cs, "z_top", 0.0)) - float(getattr(cs, "z_bot", 0.0))
            if h > 1e-9:
                kth = elem["alpha"] * dTg_e / h          # teplotní křivost
                M_th = elem["EIy"] * kth
                F[elem["ns"]["dof"]+2] += -M_th
                F[elem["ne"]["dof"]+2] += +M_th
        elem["M_th"] = M_th

    # ── okrajové podmínky ──
    constrained = set()    # DOF držené na NULE (tuhé podpory)
    prescribed = {}        # DOF → nenulový předepsaný posun (settlement)
    springs = []           # (dof, tuhost) – pružné podpory
    skew_rollers = []      # (dof_u, sinα, cosα) – šikmé rolny přes penaltu
    gap_supports = []      # (dof_w, vůle) – podpora s vůlí (nelineární kontakt)
    for sup in state.supports:
        nd = node_at(sup.x)
        if not nd:
            continue
        d = nd["dof"]
        # DOF: 0:u 1:w 2:θy 3:v 4:θz 5:θx. Vodorovný příčný posun v (d+3) drží
        # každá podpora (fáze A: laterální podepření v obou příčných rovinách;
        # v je dekuplované od w, takže planar výsledek se nemění), vetknutí drží
        # navíc θz (d+4). Iyz spřažení a přesná 3D sémantika podpor = fáze B/C.
        if sup.type == "spring":
            kz = float(getattr(sup, "spring_z", 0.0) or 0.0)
            kry = float(getattr(sup, "spring_ry", 0.0) or 0.0)
            if kz > 0:
                springs.append((d+1, kz))     # svislá pružina (w)
            if kry > 0:
                springs.append((d+2, kry))    # rotační pružina (θy)
            constrained.add(d+3)              # vodorovně tuhá (fáze A)
            continue
        # tuhé typy – svislý DOF: vůle (gap, nelineární) > předepsaný posun
        # (settlement) > tuhý (0). Vůle a settlement se vylučují (gap má přednost).
        settle = float(getattr(sup, "settlement", 0.0) or 0.0)
        gap = float(getattr(sup, "gap", 0.0) or 0.0)

        def _hold_vertical(dv, settle=settle, gap=gap):
            if gap > 1e-12:
                gap_supports.append((dv, gap))
            elif abs(settle) > 1e-12:
                prescribed[dv] = settle
            else:
                constrained.add(dv)

        if sup.type == "fixed":
            constrained |= {d, d+2, d+3, d+4, d+5}
            _hold_vertical(d+1)
        elif sup.type == "pin":
            constrained |= {d, d+3, d+5}
            _hold_vertical(d+1)
        elif sup.type == "roller":
            constrained.add(d+3)              # vodorovně příčně drží
            rad = np.radians(sup.angle or 0.0)
            s_, c_ = float(np.sin(rad)), float(np.cos(rad))
            if abs(s_) < 1e-5:
                _hold_vertical(d+1)           # vodorovná rolna → drží w
            elif abs(c_) < 1e-5:
                constrained.add(d)            # svislá → drží u
            else:
                skew_rollers.append((d, s_, c_))

    if not any(dof % 6 == 5 for dof in constrained) and nodes:
        constrained.add(nodes[0]["dof"]+5)    # torze – zabránit rotaci tělesa
    if not any(dof % 6 == 0 for dof in constrained) and nodes and not skew_rollers:
        constrained.add(nodes[0]["dof"]+0)    # osa – zabránit posuvu tělesa
    # v-rovina (v,θz) zrcadlí w-rovinu (v držené u každé podpory, θz u vetknutí)
    # → stabilní právě když je stabilní svislá rovina; samostatný fallback netřeba.

    def _solve_once(presc):
        """Sestaví soustavu s danými předepsanými posuny (settlement + aktivní
        vůle) a vyřeší. Vrací U, nebo None při nestabilitě."""
        K_s = K.copy()
        F_s = F.copy()
        if skew_rollers:
            kpen = 1e5 * max(float(np.abs(np.diag(K)).max()), 1.0)
            for d, s_, c_ in skew_rollers:
                K_s[d, d] += kpen * s_ * s_
                K_s[d, d+1] += kpen * s_ * c_
                K_s[d+1, d] += kpen * s_ * c_
                K_s[d+1, d+1] += kpen * c_ * c_
        for dof, k in springs:
            K_s[dof, dof] += k
        if presc:
            cols = {dof: K_s[:, dof].copy() for dof in presc}
            for dof, g in presc.items():
                F_s -= cols[dof] * g
            for dof in presc:
                K_s[:, dof] = 0.0
        for dof in constrained:
            K_s[dof, :] = 0; K_s[dof, dof] = 1.0; F_s[dof] = 0.0
        for dof, g in presc.items():
            K_s[dof, :] = 0; K_s[dof, dof] = 1.0; F_s[dof] = g
        try:
            U = np.linalg.solve(K_s, F_s)
            if skew_rollers and np.all(np.isfinite(U)):
                U = U + np.linalg.solve(K_s, F_s - K_s @ U)
        except np.linalg.LinAlgError:
            return None
        if not np.all(np.isfinite(U)):
            return None
        res_tol = 1e-3 if skew_rollers else 1e-6
        resid = float(np.linalg.norm(K_s @ U - F_s))
        if resid > res_tol * (float(np.linalg.norm(F_s)) + 1.0):
            return None
        return U

    # ── řešení s aktivní množinou pro VŮLE (nelineární kontakt) ──
    # Podpora s vůlí g nechá uzel volný v ±g; teprve při |w|>g „dosedne" (drží
    # se na ±g). Aktivní množina: řeš, aktivuj překročené, uvolni ty, kde reakce
    # táhne od stěny (nefyzikální). Bez vůlí je to jediný přímý solve (regrese).
    U = _solve_once(prescribed)
    if gap_supports:
        rscale = float(np.abs(F).max()) + 1.0
        gap_active = {}
        for _it in range(30):
            if U is None:
                if not gap_active:            # bez kontaktu mechanismus → dosedni vše
                    for dw, g in gap_supports:
                        gap_active[dw] = 0.0
                    U = _solve_once({**prescribed, **gap_active})
                    continue
                break
            R = K @ U - F
            changed = False
            for dw, g in gap_supports:
                if dw in gap_active:
                    val = gap_active[dw]
                    if val != 0.0 and ((val > 0 and R[dw] > 1e-6 * rscale) or
                                       (val < 0 and R[dw] < -1e-6 * rscale)):
                        del gap_active[dw]; changed = True   # reakce táhne → uvolni
                else:
                    w = U[dw]
                    if abs(w) > g + 1e-9:
                        gap_active[dw] = math.copysign(g, w); changed = True
            if not changed:
                break
            U = _solve_once({**prescribed, **gap_active})
    if U is None:
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
        reactions.append(Reaction(sup.x, sup.type, R[d], R[d+1], R[d+2], R[d+5],
                                  Ry_force=R[d+3], Rz_moment=R[d+4]))

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
                lm = _load_multiplier(state, ld, factors)
                if lm == 0:
                    continue
                dlen = ld.x2 - ld.x1
                qv = ld.q1 + (ld.q2 - ld.q1)*(sg - ld.x1)/dlen if dlen > 1e-12 else ld.q1
                q += qv * lm
        return q

    def _iie_shapes(xi, L_e, Phi):
        """IIE (Reddy) tvarové funkce: N pro průhyb, H pro pootočení; konzistentní
        s Timoshenkem, pro Φ=0 přesně klasické Hermitovy (Euler-Bernoulli)."""
        op = 1.0 + Phi
        N1 = (1 - 3*xi**2 + 2*xi**3 + Phi*(1 - xi)) / op
        N2 = L_e*(xi - 2*xi**2 + xi**3 + 0.5*Phi*(xi - xi**2)) / op
        N3 = (3*xi**2 - 2*xi**3 + Phi*xi) / op
        N4 = L_e*(-xi**2 + xi**3 - 0.5*Phi*(xi - xi**2)) / op
        H1 = 6*(xi**2 - xi) / (L_e*op)
        H2 = (3*xi**2 - 4*xi + 1 + Phi*(1 - xi)) / op
        H3 = 6*(xi - xi**2) / (L_e*op)
        H4 = (3*xi**2 - 2*xi + Phi*xi) / op
        return N1, N2, N3, N4, H1, H2, H3, H4

    for elem in elements:
        L_e = elem["L"]
        sd = elem["ns"]["dof"]
        ed = elem["ne"]["dof"]
        # DOF: 0:u 1:w 2:θy 3:v 4:θz 5:θx
        u1, w1, phi1, v1, phiz1, th1 = (U[sd], U[sd+1], U[sd+2], U[sd+3], U[sd+4], U[sd+5])
        u2, w2, phi2, v2, phiz2, th2 = (U[ed], U[ed+1], U[ed+2], U[ed+3], U[ed+4], U[ed+5])

        EA_e, EIy_e, EIz_e, EIyz_e, GJ_e, GAs_e, GAsy_e = (
            elem["EA"], elem["EIy"], elem["EIz"], elem["EIyz"],
            elem["GJ"], elem["GAs"], elem["GAsy"])
        Phi_e = (12*EIy_e)/(GAs_e*L_e**2) if theory == "timoshenko" else 0.0
        Phi_z = (12*EIz_e)/(GAsy_e*L_e**2) if theory == "timoshenko" else 0.0
        kb = _bending_block(EIy_e, GAs_e, L_e)      # rovina x-z (w, θy)
        kb2 = _bending_block(EIz_e, GAsy_e, L_e)    # rovina x-y (v, θz)
        kc = _eb_bending(EIyz_e, L_e) if abs(EIyz_e) > 1e-30 else None  # Iyz spřažení
        ub = np.array([w1, phi1, w2, phi2])
        ub2 = np.array([v1, phiz1, v2, phiz2])

        # ekvivalentní uzlové síly od spojitého zatížení na CELÉM prvku (jen svislá
        # rovina – vodorovné spojité zatížení fáze A neuvažuje)
        feq = np.zeros(4)
        for ld in state.loads:
            lm = _load_multiplier(state, ld, factors)
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

        # teplotní gradient: stejný ekvivalentní moment jako při sestavení, aby
        # koncové momenty (a tím M(x)) obsahovaly teplotní příspěvek
        M_th = elem.get("M_th", 0.0)
        if abs(M_th) > 1e-12:
            feq += np.array([0.0, -M_th, 0.0, +M_th])

        # koncové síly včetně Iyz spřažení (šikmý ohyb): každá rovina dostane i
        # příspěvek druhé přes křížovou tuhost EIyz·G
        cpl1 = kc @ ub2 if kc is not None else 0.0
        cpl2 = kc @ ub if kc is not None else 0.0
        fend = kb @ ub + cpl1 - feq   # svislá rovina [Fz1, My1, Fz2, My2]
        Mi = 0.0 if elem["release_start"] else -fend[1]
        Mj = 0.0 if elem["release_end"] else fend[3]

        # vodorovná rovina (fáze A: jen uzlová Fy/Mz, žádné spojité/teplotní)
        fend2 = kb2 @ ub2 + cpl2      # [Fy1, Mz1, Fy2, Mz2]
        Mi2 = 0.0 if elem["release_start"] else -fend2[1]
        Mj2 = 0.0 if elem["release_end"] else fend2[3]
        Vi2 = (Mj2 - Mi2)/L_e if L_e > 1e-12 else 0.0   # V_y konstantní (bez spoj. zat.)

        # jemná mřížka pro kumulativní integrály zatížení (lokální s = 0..L)
        sgrid = np.linspace(0.0, L_e, NG)
        qgrid = np.array([q_total_at(elem["xs"] + s) for s in sgrid])
        A0 = np.concatenate([[0.0], np.cumsum((qgrid[1:]+qgrid[:-1])/2*np.diff(sgrid))])      # ∫q ds
        A1 = np.concatenate([[0.0], np.cumsum((qgrid[1:]*sgrid[1:]+qgrid[:-1]*sgrid[:-1])/2*np.diff(sgrid))])  # ∫s·q ds
        IL = L_e*A0[-1] - A1[-1]    # ∫(L−s)q ds
        Vi = (Mj - Mi - IL)/L_e if L_e > 1e-12 else 0.0

        # osová síla: mechanické přetvoření = celkové − teplotní (α·ΔT)
        N = (EA_e/L_e)*(u2-u1) - EA_e*elem.get("alpha", 0.0)*elem.get("dT", 0.0)
        Mk = (GJ_e/L_e)*(th2-th1)

        local_points = []
        nsteps = 100
        for i in range(nsteps+1):
            xi = i/nsteps
            xloc = xi*L_e

            N1, N2, N3, N4, H1, H2, H3, H4 = _iie_shapes(xi, L_e, Phi_e)
            w = N1*w1 + N2*phi1 + N3*w2 + N4*phi2
            phi = H1*w1 + H2*phi1 + H3*w2 + H4*phi2
            # vodorovná rovina (v, θz)
            n1, n2, n3, n4, h1, h2, h3, h4 = _iie_shapes(xi, L_e, Phi_z)
            v = n1*v1 + n2*phiz1 + n3*v2 + n4*phiz2
            phiz = h1*v1 + h2*phiz1 + h3*v2 + h4*phiz2
            theta = th1 + (th2-th1)*xi

            a0 = float(np.interp(xloc, sgrid, A0))
            a1 = float(np.interp(xloc, sgrid, A1))
            I1 = xloc*a0 - a1           # ∫₀ˣ(x−s)q ds
            M = Mi + Vi*xloc + I1
            V = Vi + a0
            M_z = Mi2 + Vi2*xloc        # vodorovná rovina (bez spojitého zatížení)
            V_y = Vi2

            local_points.append(BeamPoint(elem["xs"]+xloc, N, V, M, Mk, w, phi, theta,
                                          v=v, V_y=V_y, M_z=M_z, phi_z=phiz))

        elem_results.append({"id": elem["id"], "xs": elem["xs"], "xe": elem["xe"],
                             "points": local_points, "section": elem["section"]})
        if not all_points:
            all_points.extend(local_points)
        else:
            all_points.extend(local_points[1:])

    res = SolverResult(all_points, reactions, elem_results, True, rep_section)
    res.resolver = resolver
    return res
