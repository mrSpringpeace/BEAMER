#!/usr/bin/env python3
"""
sa_fem.py – Finite-element Saint-Venantův torzní a warping solver.

EXAKTNÍ implementace dle:
  [1] Pilkey W.D. (2002) "Analysis and Design of Elastic Beams:
      Computational Methods", John Wiley & Sons, Chapters 5-7.
  [2] sectionproperties documentation (Theory section), v3.6+
  [3] Hughes T.J.R. (2000) "The Finite Element Method", Dover.
  [4] Vlasov V.Z. (1961) "Thin-Walled Elastic Beams", Israel Prog. Sci. Transl.

Implementuje:
  - 6-uzlové kvadratické trojúhelníky (T6) - shape functions a Jacobian
  - Saint-Venantův warping problém: ∇²ω = 0 v Ω,  ∂ω/∂n = z·n_y - y·n_z na ∂Ω
  - Torzní konstanta:    J = Ixx + Iyy - ω^T K ω
  - Střed smyku (Trefftz):  exaktní řešení přes Ψ, Φ funkce
  - Warping konstanta:   Γ = ∫_Ω ω_s² dA  (sektorová souřadnice kolem shear center)
  - Smykové funkce Ψ, Φ pro Vy, Vz (exaktní τ rozdělení)
  - Monosymmetry constants βx, βy (pro lateral-torsional buckling)

Konvence souřadnic (Pilkey, sectionproperties):
  x – podélná osa nosníku
  y – horizontální osa průřezu (vodorovně)
  z – vertikální osa průřezu (svisle)
  Ixx = ∫ z² dA  (kolem y, vyvolává ohyb v rovině xz)
  Iyy = ∫ y² dA  (kolem z, vyvolává ohyb v rovině xy)
"""

import math
import numpy as np
from scipy.sparse import lil_matrix, csr_matrix
from scipy.sparse.linalg import spsolve
from scipy.spatial import Delaunay


# ════════════════════════════════════════════════════════════════════
#  T6 ELEMENT – 6-UZLOVÝ KVADRATICKÝ TROJÚHELNÍK
# ════════════════════════════════════════════════════════════════════
#
# Numerace uzlů (standardní, viz Pilkey eq. 5.36):
#       3
#       *
#      / \
#     6   5
#    /     \
#   *---4---*
#   1       2
#
# Plošné souřadnice (area coordinates) L1, L2, L3 splňují L1+L2+L3 = 1
#
# Shape functions (Hughes 2000, Tabulka 3.II.4):
#   N1 = L1·(2·L1 - 1)
#   N2 = L2·(2·L2 - 1)
#   N3 = L3·(2·L3 - 1)
#   N4 = 4·L1·L2
#   N5 = 4·L2·L3
#   N6 = 4·L3·L1


def t6_shape_functions(L1, L2, L3):
    """Vrátí shape functions N a jejich derivace dN/dLi pro T6 element."""
    N = np.array([
        L1 * (2*L1 - 1),
        L2 * (2*L2 - 1),
        L3 * (2*L3 - 1),
        4 * L1 * L2,
        4 * L2 * L3,
        4 * L3 * L1,
    ])
    # Derivace ∂N/∂L1, ∂N/∂L2, ∂N/∂L3
    dN_dL1 = np.array([4*L1 - 1,        0,        0, 4*L2,    0, 4*L3])
    dN_dL2 = np.array([       0, 4*L2 - 1,        0, 4*L1, 4*L3,    0])
    dN_dL3 = np.array([       0,        0, 4*L3 - 1,    0, 4*L2, 4*L1])
    return N, dN_dL1, dN_dL2, dN_dL3


def t10_shape_functions(L1, L2, L3):
    """
    Shape functions pro T10 element (kubický, 10 uzlů).

    Uzly v lokálních souřadnicích (L1, L2, L3):
      0: (1, 0, 0)      ─ roh 1
      1: (0, 1, 0)      ─ roh 2
      2: (0, 0, 1)      ─ roh 3
      3: (2/3, 1/3, 0)  ─ hrana 1-2 (1/3 od rohu 1)
      4: (1/3, 2/3, 0)  ─ hrana 1-2 (2/3 od rohu 1 = 1/3 od rohu 2)
      5: (0, 2/3, 1/3)  ─ hrana 2-3 (1/3 od rohu 2)
      6: (0, 1/3, 2/3)  ─ hrana 2-3
      7: (1/3, 0, 2/3)  ─ hrana 3-1
      8: (2/3, 0, 1/3)  ─ hrana 3-1
      9: (1/3, 1/3, 1/3) ─ vnitřní (těžiště)

    Kubické shape functions (standardní formulace pro T10):
      Rohy:  N_i = (1/2)·L_i·(3·L_i - 1)·(3·L_i - 2),  i=1,2,3
      Hrany: N_ij = (9/2)·L_i·L_j·(3·L_i - 1)   pro uzel bližší L_i
             N_ji = (9/2)·L_i·L_j·(3·L_j - 1)   pro uzel bližší L_j
      Vnitřní: N_b = 27·L1·L2·L3

    Reference: Zienkiewicz & Taylor, "The Finite Element Method" Vol. 1, Ch. 4
    """
    N = np.array([
        # Rohy
        0.5 * L1 * (3*L1 - 1) * (3*L1 - 2),
        0.5 * L2 * (3*L2 - 1) * (3*L2 - 2),
        0.5 * L3 * (3*L3 - 1) * (3*L3 - 2),
        # Hrana 1-2: blíž rohu 1 (L1=2/3), blíž rohu 2 (L1=1/3)
        4.5 * L1 * L2 * (3*L1 - 1),
        4.5 * L1 * L2 * (3*L2 - 1),
        # Hrana 2-3
        4.5 * L2 * L3 * (3*L2 - 1),
        4.5 * L2 * L3 * (3*L3 - 1),
        # Hrana 3-1
        4.5 * L3 * L1 * (3*L3 - 1),
        4.5 * L3 * L1 * (3*L1 - 1),
        # Vnitřní (těžiště)
        27 * L1 * L2 * L3,
    ])

    # Derivace ∂N/∂L1
    dN_dL1 = np.array([
        0.5 * (27*L1*L1 - 18*L1 + 2),                     # 1/2(9L²-9L+2+9L²-9L+9L²... )
        0,
        0,
        4.5 * L2 * (6*L1 - 1),                            # 4.5 L2(6L1 - 1)
        4.5 * L2 * (3*L2 - 1),                            # konst v L1
        0,
        0,
        4.5 * L3 * (3*L3 - 1),
        4.5 * L3 * (6*L1 - 1),
        27 * L2 * L3,
    ])
    dN_dL2 = np.array([
        0,
        0.5 * (27*L2*L2 - 18*L2 + 2),
        0,
        4.5 * L1 * (3*L1 - 1),
        4.5 * L1 * (6*L2 - 1),
        4.5 * L3 * (6*L2 - 1),
        4.5 * L3 * (3*L3 - 1),
        0,
        0,
        27 * L1 * L3,
    ])
    dN_dL3 = np.array([
        0,
        0,
        0.5 * (27*L3*L3 - 18*L3 + 2),
        0,
        0,
        4.5 * L2 * (3*L2 - 1),
        4.5 * L2 * (6*L3 - 1),
        4.5 * L1 * (6*L3 - 1),
        4.5 * L1 * (3*L1 - 1),
        27 * L1 * L2,
    ])
    return N, dN_dL1, dN_dL2, dN_dL3


# ── 12-bodová Gaussova kvadratura pro trojúhelník (přesnost: degree 6) ──
# Nutná pro PŘESNOU integraci T10 (kubický × kubický = degree 6 polynom).
# Reference: Dunavant 1985, Table II
GAUSS_T10 = np.array([
    [0.873821971016996, 0.063089014491502, 0.063089014491502, 0.050844906370207],
    [0.063089014491502, 0.873821971016996, 0.063089014491502, 0.050844906370207],
    [0.063089014491502, 0.063089014491502, 0.873821971016996, 0.050844906370207],
    [0.501426509658179, 0.249286745170910, 0.249286745170910, 0.116786275726379],
    [0.249286745170910, 0.501426509658179, 0.249286745170910, 0.116786275726379],
    [0.249286745170910, 0.249286745170910, 0.501426509658179, 0.116786275726379],
    [0.636502499121399, 0.310352451033785, 0.053145049844816, 0.082851075618374],
    [0.636502499121399, 0.053145049844816, 0.310352451033785, 0.082851075618374],
    [0.310352451033785, 0.636502499121399, 0.053145049844816, 0.082851075618374],
    [0.310352451033785, 0.053145049844816, 0.636502499121399, 0.082851075618374],
    [0.053145049844816, 0.636502499121399, 0.310352451033785, 0.082851075618374],
    [0.053145049844816, 0.310352451033785, 0.636502499121399, 0.082851075618374],
])


# ── 6-bodová Gaussova kvadratura pro trojúhelník (přesnost: degree 4) ──
# Pilkey eq. 5.41, Hughes p. 173. Pro T6 elementy je 6-bodová integrace
# nutná pro PŘESNÉ vyčíslení tuhostní matice (integrand kvadratický × kvadratický).
GAUSS_T6 = np.array([
    # L1,                L2,                L3,                weight
    [0.108103018168070, 0.445948490915965, 0.445948490915965, 0.223381589678011],
    [0.445948490915965, 0.108103018168070, 0.445948490915965, 0.223381589678011],
    [0.445948490915965, 0.445948490915965, 0.108103018168070, 0.223381589678011],
    [0.816847572980459, 0.091576213509771, 0.091576213509771, 0.109951743655322],
    [0.091576213509771, 0.816847572980459, 0.091576213509771, 0.109951743655322],
    [0.091576213509771, 0.091576213509771, 0.816847572980459, 0.109951743655322],
])
# Váhy v této tabulce dávají dohromady 1.0 – integrál f dA = J/2 · Σ wᵢ·fᵢ
# (J = determinant Jacobianu; faktor 1/2 protože plocha referenčního Δ = 1/2)


# ════════════════════════════════════════════════════════════
#  AKTUÁLNÍ ELEMENT TYPE (T6 nebo T10)
# ════════════════════════════════════════════════════════════
# Tyto proměnné se nastaví podle volby element_order='T6'|'T10'
# v analyze_section(). Všechny solvery (warping, shear, atd.) pak
# používají _CURRENT_SHAPE_FUNC a _CURRENT_GAUSS místo přímých
# t6_shape_functions/GAUSS_T6.

_CURRENT_SHAPE_FUNC = None  # bude t6_shape_functions nebo t10_shape_functions
_CURRENT_GAUSS = None       # bude GAUSS_T6 nebo GAUSS_T10
_CURRENT_N_NODES_PER_ELEM = 6  # 6 pro T6, 10 pro T10


def set_element_order(order):
    """
    Globálně přepne typ elementu. Volej před analyze_section nebo solver funkcemi.
      order: 'T6' nebo 'T10'
    """
    global _CURRENT_SHAPE_FUNC, _CURRENT_GAUSS, _CURRENT_N_NODES_PER_ELEM
    if order == 'T10':
        _CURRENT_SHAPE_FUNC = t10_shape_functions
        _CURRENT_GAUSS = GAUSS_T10
        _CURRENT_N_NODES_PER_ELEM = 10
    else:  # T6 default
        _CURRENT_SHAPE_FUNC = t6_shape_functions
        _CURRENT_GAUSS = GAUSS_T6
        _CURRENT_N_NODES_PER_ELEM = 6


# Defaultní nastavení = T6
set_element_order('T6')


def convert_t6_to_t10(nodes_t6, elements_t6):
    """
    Konvertuje T6 mesh na T10 mesh přidáním:
      - 1 vnitřního uzlu v každém elementu (těžiště)
      - 1 dalšího uzlu na každé hraně (T6 má 1 mid-edge, T10 má 2 - v 1/3 a 2/3)

    Souřadnice nových uzlů se interpolují PRESNĚ pomocí T6 shape functions
    z 6 původních uzlů. Tím zachováme geometrii (i pro zakřivené hrany,
    pokud by T6 měl curvilinear edges).

    Pro PROSTOROVĚ ROVNÉ hrany (= většinou) se nové hranové uzly nakonec
    leží v geometrických 1/3 mezi rohovými uzly (lineární interpolace).

    Vstup:
      nodes_t6: (n_nodes_t6, 2) souřadnice T6 uzlů
      elements_t6: (n_elem, 6) konektivita T6 (rohy 0-2, mid-edges 3-5)
        kde elem[3] = mid-edge mezi rohy 0-1
             elem[4] = mid-edge mezi rohy 1-2
             elem[5] = mid-edge mezi rohy 2-0

    Vrátí:
      nodes_t10: (n_nodes_t10, 2)
      elements_t10: (n_elem, 10) konektivita
        Pořadí: 3 rohy, 2 uzly na hraně 0-1, 2 na 1-2, 2 na 2-0, 1 vnitřní
        Tedy:
          elem[0..2] = rohy
          elem[3,4]  = hrana 0-1 v 1/3 a 2/3 od rohu 0
          elem[5,6]  = hrana 1-2 v 1/3 a 2/3 od rohu 1
          elem[7,8]  = hrana 2-0 v 1/3 a 2/3 od rohu 2
          elem[9]    = vnitřní (těžiště)
    """
    nodes_t6 = np.asarray(nodes_t6, dtype=float)
    elements_t6 = np.asarray(elements_t6, dtype=int)
    n_elem = len(elements_t6)

    # ── Strategie: zachovat POUZE rohové uzly z T6.
    # Mid-edge uzly T6 jsou nepotřebné pro T10 - T10 má 2 uzly v 1/3 a 2/3
    # hrany, ne 1 ve středu. Necháme původní indexy rohů (aby šly fast-mapy
    # od T6 ke T10), ale staré mid-edges už nepoužíváme.
    #
    # Sběr rohových indexů:
    corner_indices = set()
    for elem in elements_t6:
        corner_indices.update([int(elem[0]), int(elem[1]), int(elem[2])])
    # Mapování staré_idx → nové_idx (pouze rohy)
    sorted_corners = sorted(corner_indices)
    old_to_new = {old: new for new, old in enumerate(sorted_corners)}

    # Nový seznam uzlů: jen rohy
    new_nodes = [nodes_t6[old].tolist() for old in sorted_corners]

    # Cache pro hranové uzly
    edge_node_cache = {}

    elements_t10 = np.zeros((n_elem, 10), dtype=int)

    for e_idx, elem in enumerate(elements_t6):
        c0_old, c1_old, c2_old = int(elem[0]), int(elem[1]), int(elem[2])
        m01, m12, m20 = int(elem[3]), int(elem[4]), int(elem[5])

        # Rohy v novém číslování
        c0 = old_to_new[c0_old]
        c1 = old_to_new[c1_old]
        c2 = old_to_new[c2_old]
        elements_t10[e_idx, 0] = c0
        elements_t10[e_idx, 1] = c1
        elements_t10[e_idx, 2] = c2

        # Hranové uzly v třetinách
        for i, edge in enumerate([(c0_old, c1_old, m01),
                                   (c1_old, c2_old, m12),
                                   (c2_old, c0_old, m20)]):
            ca_old, cb_old, cm_old = edge
            key = (min(ca_old, cb_old), max(ca_old, cb_old))
            if key in edge_node_cache:
                ia, ib = edge_node_cache[key]
                if ca_old == key[0]:
                    n_third, n_two_third = ia, ib
                else:
                    n_third, n_two_third = ib, ia
            else:
                # Vytvoř 2 nové uzly v 1/3 a 2/3 hrany
                # Pomocí T6 shape functions na hraně (L3=0):
                # s=1/3: N_a=2/9, N_b=-1/9, N_m=8/9
                # s=2/3: N_a=-1/9, N_b=2/9, N_m=8/9
                Pa = nodes_t6[ca_old]; Pb = nodes_t6[cb_old]; Pm = nodes_t6[cm_old]
                p_third = (2/9) * Pa + (-1/9) * Pb + (8/9) * Pm
                p_two_third = (-1/9) * Pa + (2/9) * Pb + (8/9) * Pm
                n_third = len(new_nodes); new_nodes.append(p_third.tolist())
                n_two_third = len(new_nodes); new_nodes.append(p_two_third.tolist())
                if ca_old == key[0]:
                    edge_node_cache[key] = (n_third, n_two_third)
                else:
                    edge_node_cache[key] = (n_two_third, n_third)

            base = 3 + i * 2
            elements_t10[e_idx, base] = n_third
            elements_t10[e_idx, base + 1] = n_two_third

        # Vnitřní uzel (těžiště T6 interpolací)
        P0 = nodes_t6[c0_old]; P1 = nodes_t6[c1_old]; P2 = nodes_t6[c2_old]
        P3 = nodes_t6[m01]; P4 = nodes_t6[m12]; P5 = nodes_t6[m20]
        p_int = -1/9 * (P0 + P1 + P2) + 4/9 * (P3 + P4 + P5)
        n_int = len(new_nodes); new_nodes.append(p_int.tolist())
        elements_t10[e_idx, 9] = n_int

    nodes_t10 = np.array(new_nodes)
    return nodes_t10, elements_t10


def estimate_mesh_error(nodes, elements, field):
    """
    Heuristický odhad chyby řešení založený na **inter-element gradient jumps**.

    Standardní a-posteriori error indikátor (Zienkiewicz-Zhu, Babuska):
      η_e² = ∫_e (∇u_h - G(∇u_h))² dV
    kde G je smoothed (uzlové průměrované) gradient pole.

    Pro každý uzel sdílený více elementy spočteme rozdíl mezi gradienty
    z různých elementů → velký rozdíl = nepřesnost.

    Vrací:
      error_per_node: (n_nodes,) ndarray - odhad chyby v každém uzlu
      total_error: float - globální norma chyby
      hot_elements: list elementů s nejvyšší chybou (kandidáti pro p-refinement)
    """
    n_nodes = len(nodes)
    # Autodetekce typu elementu podle počtu uzlů per element
    n_per_elem = elements.shape[1] if hasattr(elements, 'shape') else len(elements[0])
    if n_per_elem == 10:
        shape_func = t10_shape_functions
    else:
        shape_func = t6_shape_functions

    # Pro každý element spočítáme gradient v centroidu (L1=L2=L3=1/3)
    # Pak agregujeme do uzlů a porovnáme uzel-vůči-element odchylky
    grad_y_per_elem = np.zeros(len(elements))
    grad_z_per_elem = np.zeros(len(elements))

    for e_idx, elem in enumerate(elements):
        coords = nodes[elem]
        field_e = field[elem]
        L1, L2, L3 = 1/3, 1/3, 1/3
        N, dN1, dN2, dN3 = shape_func(L1, L2, L3)
        J_det, dN_dy, dN_dz = element_jacobian(coords, dN1, dN2, dN3)
        if J_det <= 0 or dN_dy is None:
            continue
        grad_y_per_elem[e_idx] = float(np.dot(dN_dy, field_e))
        grad_z_per_elem[e_idx] = float(np.dot(dN_dz, field_e))

    # Smoothed gradient v uzlech (vážený průměr přes přilehlé elementy)
    smoothed_gy = np.zeros(n_nodes)
    smoothed_gz = np.zeros(n_nodes)
    weight = np.zeros(n_nodes)
    for e_idx, elem in enumerate(elements):
        for n_idx in elem:
            smoothed_gy[n_idx] += grad_y_per_elem[e_idx]
            smoothed_gz[n_idx] += grad_z_per_elem[e_idx]
            weight[n_idx] += 1
    valid = weight > 0
    smoothed_gy[valid] /= weight[valid]
    smoothed_gz[valid] /= weight[valid]

    # Chyba elementu = norma rozdílu mezi elementovým a smoothed gradientem
    error_per_elem = np.zeros(len(elements))
    for e_idx, elem in enumerate(elements):
        gy_e = grad_y_per_elem[e_idx]
        gz_e = grad_z_per_elem[e_idx]
        # Průměrný smoothed gradient přes uzly elementu
        gy_s = smoothed_gy[elem].mean()
        gz_s = smoothed_gz[elem].mean()
        error_per_elem[e_idx] = math.hypot(gy_e - gy_s, gz_e - gz_s)

    # Per-node chyba (rozdělíme element chybu na uzly)
    error_per_node = np.zeros(n_nodes)
    weight2 = np.zeros(n_nodes)
    for e_idx, elem in enumerate(elements):
        for n_idx in elem:
            error_per_node[n_idx] += error_per_elem[e_idx]
            weight2[n_idx] += 1
    error_per_node[weight2 > 0] /= weight2[weight2 > 0]

    # Globální norma
    total_error = math.sqrt((error_per_elem**2).sum())

    # Top 10% elementů jako "hot"
    threshold = np.percentile(error_per_elem, 90)
    hot_elements = np.where(error_per_elem > threshold)[0].tolist()

    return {
        'error_per_node': error_per_node,
        'error_per_elem': error_per_elem,
        'total_error': total_error,
        'hot_elements': hot_elements,
        'threshold': float(threshold),
    }


def analyze_section_adaptive(outer, holes=None, max_area=None, nu=0.0,
                              error_threshold=0.05, max_iterations=2):
    """
    P-adaptivní průřezová analýza.

    Strategie:
      1. Spočítej T6 řešení
      2. Odhadni chybu (gradient jumps mezi sousedními elementy)
      3. Pokud chyba > threshold → upgrade na T10 (uniform p-refinement)
      4. Opakuj max_iterations krát

    Pro plné lokální p-refinement (smíšené T6/T10 transition elements)
    by bylo nutné implementovat hanging-node constraints, což je
    značně složitější. Tato implementace dělá uniform refinement:
    buď VŠE T6 nebo VŠE T10, na základě globálního error estimate.

    Vstup:
      outer, holes, max_area, nu: jako analyze_section
      error_threshold: pokud relativní chyba > threshold, upgrade
      max_iterations: max počet iterací (default 2)

    Vrátí: dict s výsledky + 'element_order_final', 'error_history'
    """
    error_history = []

    # Krok 1: T6 řešení
    result = analyze_section(outer, holes=holes, max_area=max_area,
                              nu=nu, element_order='T6')
    nodes = result['nodes']
    elements = result['elements']

    # Odhad chyby na ω (klíčové pole pro torzi)
    err = estimate_mesh_error(nodes, elements, result['omega'])
    rel_err = err['total_error'] / max(abs(result['omega']).max(), 1e-9)
    error_history.append({'order': 'T6', 'rel_error': rel_err})

    if rel_err > error_threshold and max_iterations > 1:
        # Krok 2: Upgrade na T10
        result_t10 = analyze_section(outer, holes=holes, max_area=max_area,
                                      nu=nu, element_order='T10')
        err2 = estimate_mesh_error(result_t10['nodes'], result_t10['elements'],
                                    result_t10['omega'])
        rel_err2 = err2['total_error'] / max(abs(result_t10['omega']).max(), 1e-9)
        error_history.append({'order': 'T10', 'rel_error': rel_err2})

        result_t10['element_order_final'] = 'T10'
        result_t10['error_history'] = error_history
        return result_t10

    result['element_order_final'] = 'T6'
    result['error_history'] = error_history
    return result


def element_jacobian(coords, dN_dL1, dN_dL2, dN_dL3):
    """
    Jacobian transformace z (L1,L2,L3) na (y,z).
    coords: 6×2 souřadnice uzlů elementu [(y,z), ...]
    Vrátí (J_det, dN_dy, dN_dz) kde dN_dy, dN_dz jsou derivace shape functions
    podle skutečných souřadnic.

    Použijeme dvě nezávislé proměnné L1, L2 (L3 = 1-L1-L2):
       dN_dL1_eff = dN_dL1 - dN_dL3
       dN_dL2_eff = dN_dL2 - dN_dL3

    Pak:
       [dy/dL1  dz/dL1] = J = [Σ y_i·dN_dL1_eff_i  Σ z_i·dN_dL1_eff_i]
       [dy/dL2  dz/dL2]       [Σ y_i·dN_dL2_eff_i  Σ z_i·dN_dL2_eff_i]
    """
    dN1 = dN_dL1 - dN_dL3
    dN2 = dN_dL2 - dN_dL3
    y = coords[:, 0]
    z = coords[:, 1]
    J = np.array([
        [np.dot(dN1, y), np.dot(dN1, z)],
        [np.dot(dN2, y), np.dot(dN2, z)],
    ])
    J_det = J[0, 0]*J[1, 1] - J[0, 1]*J[1, 0]
    if abs(J_det) < 1e-20:
        return 0.0, None, None
    J_inv = np.array([[ J[1, 1], -J[0, 1]],
                      [-J[1, 0],  J[0, 0]]]) / J_det
    # dN/dy a dN/dz pro všech 6 uzlů
    dN_dy = J_inv[0, 0] * dN1 + J_inv[0, 1] * dN2
    dN_dz = J_inv[1, 0] * dN1 + J_inv[1, 1] * dN2
    return J_det, dN_dy, dN_dz


# ════════════════════════════════════════════════════════════════════
#  TRIANGULACE PRŮŘEZU
# ════════════════════════════════════════════════════════════════════

def _point_in_polygon(point, polygon):
    """Ray-casting test. polygon: list of (y,z) – uzavřený nemusí být."""
    y, z = point
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        yi, zi = polygon[i]
        yj, zj = polygon[j]
        if ((zi > z) != (zj > z)) and \
           (y < (yj - yi) * (z - zi) / (zj - zi + 1e-30) + yi):
            inside = not inside
        j = i
    return inside


def triangulate_section(outer, holes=None, max_area=None):
    """
    Triangulace průřezu s 6-uzlovými T6 elementy.

    Postup (constrained Delaunay s lokálním zjemněním):
      1. Vzorkuj hranice (vnější + díry) dostatečně hustě pro daný max_area.
      2. Generuj vnitřní body v gridu, ponech jen ty uvnitř Ω.
      3. Spusť Delaunay triangulaci.
      4. Filtruj trojúhelníky: ponech jen ty, jejichž těžiště je uvnitř Ω
         (uvnitř outer a vně holes).
      5. Z trojúhelníků (3-uzlových T3) udělej T6 přidáním středů hran.

    Parametry:
      outer: list [(y,z), ...] – vnější polygon (CCW)
      holes: list of lists – seznamy polygonů děr (každý uzavřený, libovolná
             orientace)
      max_area: maximální plocha trojúhelníku [mm²]. Default = celk.plocha/500.

    Vrací:
      nodes: (n_nodes, 2) ndarray souřadnic [y, z]
      elements: (n_elem, 6) ndarray indexů uzlů pro každý element
                (pořadí: rohy [1,2,3], pak středy hran [4(1-2), 5(2-3), 6(3-1)])
    """
    if holes is None:
        holes = []

    outer = list(outer)
    # Odstraň duplicitní bod na konci (pokud uzavřený)
    if len(outer) > 1 and outer[0] == outer[-1]:
        outer = outer[:-1]

    # ── Odhad plochy a velikosti elementu ──
    def polygon_area(poly):
        a = 0.0
        n = len(poly)
        for i in range(n):
            y1, z1 = poly[i]
            y2, z2 = poly[(i+1) % n]
            a += y1*z2 - y2*z1
        return abs(a) / 2

    A_outer = polygon_area(outer)
    A_holes = sum(polygon_area(h) for h in holes)
    A_total = A_outer - A_holes
    if max_area is None:
        max_area = A_total / 1500.0   # ~1500 elementů default

    # Cílová délka strany h ≈ sqrt(2·A_elem) pro rovnostranný Δ
    h_target = math.sqrt(2 * max_area)

    # ── 1. Vzorkování hranic ──
    def sample_boundary(poly, h):
        pts = []
        n = len(poly)
        for i in range(n):
            y1, z1 = poly[i]
            y2, z2 = poly[(i+1) % n]
            L = math.hypot(y2-y1, z2-z1)
            n_sub = max(1, int(math.ceil(L / h)))
            for k in range(n_sub):
                t = k / n_sub
                pts.append((y1 + t*(y2-y1), z1 + t*(z2-z1)))
        return pts

    boundary_pts = sample_boundary(outer, h_target)
    for hole in holes:
        h_clean = list(hole)
        if len(h_clean) > 1 and h_clean[0] == h_clean[-1]:
            h_clean = h_clean[:-1]
        boundary_pts.extend(sample_boundary(h_clean, h_target))

    # ── 2. Interní body (rovnoběžné s y, ofset Δz·√3/2 pro 60°-síť) ──
    all_y = [p[0] for p in boundary_pts]
    all_z = [p[1] for p in boundary_pts]
    y_min, y_max = min(all_y) - h_target, max(all_y) + h_target
    z_min, z_max = min(all_z) - h_target, max(all_z) + h_target

    interior_pts = []
    dz = h_target * math.sqrt(3) / 2
    n_rows = int(math.ceil((z_max - z_min) / dz)) + 1
    for i in range(n_rows):
        z = z_min + i * dz
        offset = (h_target / 2) if (i % 2) else 0.0
        n_cols = int(math.ceil((y_max - y_min) / h_target)) + 1
        for j in range(n_cols):
            y = y_min + offset + j * h_target
            pt = (y, z)
            # Test: uvnitř outer a vně všech děr
            if not _point_in_polygon(pt, outer):
                continue
            in_hole = False
            for hole in holes:
                h_clean = list(hole)
                if len(h_clean) > 1 and h_clean[0] == h_clean[-1]:
                    h_clean = h_clean[:-1]
                if _point_in_polygon(pt, h_clean):
                    in_hole = True
                    break
            if in_hole:
                continue
            interior_pts.append(pt)

    # ── 3. Delaunay ──
    all_pts = boundary_pts + interior_pts
    pts_array = np.array(all_pts)
    # Odstraň duplikáty (do tolerance)
    pts_array_rounded = np.round(pts_array / (h_target * 1e-4)) * (h_target * 1e-4)
    _, unique_idx = np.unique(pts_array_rounded, axis=0, return_index=True)
    pts_array = pts_array[np.sort(unique_idx)]

    if len(pts_array) < 3:
        raise ValueError("Příliš málo bodů pro triangulaci")

    tri = Delaunay(pts_array)
    triangles = tri.simplices

    # ── 4. Filtrace + zajištění CCW orientace + odstranění degenerovaných ──
    # Delaunay v scipy nedává garantovaně CCW trojúhelníky pro 2D - musíme
    # zkontrolovat každý a v případě CW prohodit dva vrcholy. Jinak by
    # element_jacobian dával záporný J_det a FEM by selhal.
    # Také odfiltrujeme degenerované sliver triangles (~0 signed area), které
    # vznikají na úzkých pásech (např. tenká stěna CHS).
    # Tolerance: relativní k h_target²; pod 1% rovnostranného Δ je sliver.
    area_tol = 0.005 * (h_target ** 2)  # ~0.5% rovnostranného Δ

    valid_tris = []
    n_skipped_degen = 0
    for triangle in triangles:
        p1 = pts_array[triangle[0]]
        p2 = pts_array[triangle[1]]
        p3 = pts_array[triangle[2]]
        # Signed area = ((p2-p1) × (p3-p1)) / 2  (absolutní velikost je plocha)
        signed_area = 0.5 * ((p2[0] - p1[0]) * (p3[1] - p1[1])
                           - (p3[0] - p1[0]) * (p2[1] - p1[1]))
        if abs(signed_area) < area_tol:
            n_skipped_degen += 1
            continue  # degenerovaný sliver - vyhodíme

        centroid = ((p1[0]+p2[0]+p3[0])/3, (p1[1]+p2[1]+p3[1])/3)
        if not _point_in_polygon(centroid, outer):
            continue
        in_hole = False
        for hole in holes:
            h_clean = list(hole)
            if len(h_clean) > 1 and h_clean[0] == h_clean[-1]:
                h_clean = h_clean[:-1]
            if _point_in_polygon(centroid, h_clean):
                in_hole = True
                break
        if in_hole:
            continue
        if signed_area < 0:
            # CW orientace - prohodíme p2 a p3 abychom dostali CCW
            valid_tris.append([triangle[0], triangle[2], triangle[1]])
        else:
            valid_tris.append([triangle[0], triangle[1], triangle[2]])

    if not valid_tris:
        raise ValueError("Po filtraci nezbyly žádné trojúhelníky")

    valid_tris = np.array(valid_tris)

    # ── 5. Z T3 udělej T6 přidáním středů hran ──
    n_corner = len(pts_array)
    # mapa hrany → index středového uzlu
    edge_to_mid = {}
    new_nodes = list(pts_array)
    t6_elements = []

    for tri_idx in valid_tris:
        i1, i2, i3 = int(tri_idx[0]), int(tri_idx[1]), int(tri_idx[2])

        def get_mid(a, b):
            key = (min(a, b), max(a, b))
            if key in edge_to_mid:
                return edge_to_mid[key]
            mid_pt = ((new_nodes[a][0] + new_nodes[b][0]) / 2,
                      (new_nodes[a][1] + new_nodes[b][1]) / 2)
            new_idx = len(new_nodes)
            new_nodes.append(mid_pt)
            edge_to_mid[key] = new_idx
            return new_idx

        i4 = get_mid(i1, i2)
        i5 = get_mid(i2, i3)
        i6 = get_mid(i3, i1)
        t6_elements.append([i1, i2, i3, i4, i5, i6])

    nodes = np.array(new_nodes)
    elements = np.array(t6_elements, dtype=np.int64)
    return nodes, elements


# ════════════════════════════════════════════════════════════════════
#  GEOMETRICKÉ CHARAKTERISTIKY (exaktní integrace přes T6 elementy)
# ════════════════════════════════════════════════════════════════════

def compute_geometric_properties(nodes, elements):
    """
    Spočte: A, Qy, Qz, Iyy, Izz, Iyz, cy, cz – vše v glob. souřadnicích,
    přesnou Gaussovou integrací 6-bodovou kvadraturou.

    Q_y = ∫ z dA   (první moment kolem y)
    Q_z = ∫ y dA   (první moment kolem z)
    Iyy = ∫ y² dA  (moment setrvačnosti kolem z-osy)
    Izz = ∫ z² dA  (moment setrvačnosti kolem y-osy)
    Iyz = ∫ y·z dA (deviační moment)

    POZOR na konvenci: zde používáme inženýrskou (Pilkey) konvenci:
      Ixx = ∫ z² dA  (kolem horizontální osy y, vyvolává ohyb v rovině xz)
      Iyy = ∫ y² dA  (kolem vertikální osy z)
    Ve výstupu DICT: 'Ixx_c', 'Iyy_c', 'Ixy_c' = centroidální.

    To je konvence sectionproperties a Pilkey (2002).
    """
    A = 0.0
    Qy = 0.0  # = ∫ y dA
    Qz = 0.0  # = ∫ z dA
    Iy2 = 0.0  # = ∫ y² dA
    Iz2 = 0.0  # = ∫ z² dA
    Iyz = 0.0  # = ∫ y·z dA

    for elem in elements:
        coords = nodes[elem]  # 6×2
        for gp in _CURRENT_GAUSS:
            L1, L2, L3, w = gp
            N, dN_dL1, dN_dL2, dN_dL3 = _CURRENT_SHAPE_FUNC(L1, L2, L3)
            J_det, _, _ = element_jacobian(coords, dN_dL1, dN_dL2, dN_dL3)
            if J_det <= 0:
                continue
            # Vyčíslení (y,z) v Gaussově bodu
            y_gp = float(np.dot(N, coords[:, 0]))
            z_gp = float(np.dot(N, coords[:, 1]))
            dA = 0.5 * J_det * w
            A   += dA
            Qy  += y_gp * dA
            Qz  += z_gp * dA
            Iy2 += y_gp**2 * dA
            Iz2 += z_gp**2 * dA
            Iyz += y_gp * z_gp * dA

    # Centroid
    cy = Qy / A if A > 0 else 0.0
    cz = Qz / A if A > 0 else 0.0

    # Centroidální momenty (Steinerova věta)
    # Ixx_c = ∫ (z-cz)² dA = Iz2 - A·cz²
    # Iyy_c = ∫ (y-cy)² dA = Iy2 - A·cy²
    # Ixy_c = ∫ (y-cy)(z-cz) dA = Iyz - A·cy·cz
    Ixx_c = Iz2 - A * cz**2   # kolem horizontální osy y procházející těžištěm
    Iyy_c = Iy2 - A * cy**2   # kolem vertikální osy z procházející těžištěm
    Ixy_c = Iyz - A * cy * cz # deviační kolem těžiště

    # Hlavní osy (principal axes)
    avg  = (Ixx_c + Iyy_c) / 2
    diff = math.sqrt(((Ixx_c - Iyy_c) / 2)**2 + Ixy_c**2)
    I11 = avg + diff
    I22 = avg - diff
    # Úhel od y-osy k 1. hlavní ose (kolem které je největší moment)
    # alpha = 0.5 * atan2(-2·Ixy_c, Ixx_c - Iyy_c)
    # (Pilkey eq. 2.11)
    if abs(Ixx_c - Iyy_c) < 1e-20 and abs(Ixy_c) < 1e-20:
        alpha_p = 0.0
    else:
        alpha_p = 0.5 * math.atan2(-2 * Ixy_c, Ixx_c - Iyy_c)

    return {
        'A': A,
        'cy': cy, 'cz': cz,
        'Ixx_c': Ixx_c, 'Iyy_c': Iyy_c, 'Ixy_c': Ixy_c,
        'I11': I11, 'I22': I22, 'alpha_p': alpha_p,
        # Globální (pro reference)
        'Qy_g': Qy, 'Qz_g': Qz,
    }


# ════════════════════════════════════════════════════════════════════
#  WARPING / TORZNÍ ANALÝZA (Saint-Venant)
# ════════════════════════════════════════════════════════════════════
#
# Saint-Venantův torzní problém formulovaný přes warping function ω(y,z):
#
#   ∇²ω = 0                  v Ω        (Laplace v centroidálních souř.)
#   ∂ω/∂n = z·n_y - y·n_z    na ∂Ω      (Neumann BC)
#
# Slabá formulace (vynásobíme test fcí v a integrujeme přes Ω):
#   ∫_Ω ∇v · ∇ω dA = ∫_∂Ω v·(z·n_y - y·n_z) dl
#
# Aplikací Greenovy věty na pravou stranu:
#   ∫_∂Ω v·(z·n_y - y·n_z) dl = ∫_Ω [∂(v·z)/∂y - ∂(v·y)/∂z] dA
#                              = ∫_Ω [v_y · z - v_z · y] dA    (protože z,y nezávisí na y resp. z navzájem)
#                                (nezávisí na (y,z) symetricky)
# Tedy zjednodušeno:
#   ∫_Ω ∇v · ∇ω dA = ∫_Ω (∂v/∂y · z - ∂v/∂z · y) dA
#
# Po diskretizaci: K · ω = F
#   K_ij = ∫_Ω (∂N_i/∂y · ∂N_j/∂y + ∂N_i/∂z · ∂N_j/∂z) dA
#   F_i  = ∫_Ω (∂N_i/∂y · z - ∂N_i/∂z · y) dA
#
# Matice K je singulární (Laplaceův operátor s čistě Neumannovou BC).
# Řešení je určeno až na konstantu – ukotvíme ω(node_0) = 0 a pak posuneme
# tak, aby ∫_Ω ω dA = 0 (Pilkey eq. 5.61).
#
# Torzní konstanta:
#   J = Ixx + Iyy - ω^T · K · ω    (Pilkey eq. 5.62, sectionproperties theory)
#
# Reference: Pilkey 2002 Chapter 5, sectionproperties theory dokument.

def solve_warping_function(nodes, elements, cy, cz):
    """
    Řeší Saint-Venantovu warping funkci ω(y,z) v centroidálních souřadnicích.

    Vrací:
      omega: (n_nodes,) ndarray – warping function v každém uzlu
      K_csr: sparse matice tuhosti (pro pozdější výpočet J)
    """
    n_nodes = len(nodes)
    # Souřadnice v centroidálním systému
    nodes_c = nodes - np.array([cy, cz])

    K = lil_matrix((n_nodes, n_nodes))
    F = np.zeros(n_nodes)

    for elem in elements:
        idx = elem
        coords = nodes[elem]      # globální (pro shape fcs)
        coords_c = nodes_c[elem]  # centroidální

        Ke = np.zeros((_CURRENT_N_NODES_PER_ELEM, _CURRENT_N_NODES_PER_ELEM))
        Fe = np.zeros(_CURRENT_N_NODES_PER_ELEM)

        for gp in _CURRENT_GAUSS:
            L1, L2, L3, w = gp
            N, dN_dL1, dN_dL2, dN_dL3 = _CURRENT_SHAPE_FUNC(L1, L2, L3)
            J_det, dN_dy, dN_dz = element_jacobian(coords_c, dN_dL1, dN_dL2, dN_dL3)
            if J_det <= 0 or dN_dy is None:
                continue
            dA = 0.5 * J_det * w
            # Souřadnice Gaussova bodu v centroid. souř.
            y_c = float(np.dot(N, coords_c[:, 0]))
            z_c = float(np.dot(N, coords_c[:, 1]))

            # K_ij = (∂N_i/∂y · ∂N_j/∂y + ∂N_i/∂z · ∂N_j/∂z) · dA
            Ke += (np.outer(dN_dy, dN_dy) + np.outer(dN_dz, dN_dz)) * dA
            # F_i = (∂N_i/∂y · z_c - ∂N_i/∂z · y_c) · dA
            Fe += (dN_dy * z_c - dN_dz * y_c) * dA

        for a in range(_CURRENT_N_NODES_PER_ELEM):
            for b in range(_CURRENT_N_NODES_PER_ELEM):
                K[idx[a], idx[b]] += Ke[a, b]
            F[idx[a]] += Fe[a]

    # ── Ukotvení: ω(node_0) = 0 (odstraníme singularitu) ──
    K_csr = K.tocsr()
    # Penalty method: K[0,0] += velké, F[0] += velké * 0
    # Lepší: Lagrange multiplier nebo přímá modifikace
    K_mod = K.copy().tolil()
    K_mod[0, :] = 0
    K_mod[:, 0] = 0
    K_mod[0, 0] = 1.0
    F_mod = F.copy()
    F_mod[0] = 0.0
    # Pro modifikované řádky/sloupce: F[i] -= K[i,0] * 0 (nothing)
    K_mod = K_mod.tocsr()

    omega = spsolve(K_mod, F_mod)

    # ── Normalizace: ∫_Ω ω dA = 0 ──
    # Vypočti střední hodnotu ω vzhledem k ploše a odečti
    omega_mean = 0.0
    A_total = 0.0
    for elem in elements:
        coords_c = nodes_c[elem]
        omega_e = omega[elem]
        for gp in _CURRENT_GAUSS:
            L1, L2, L3, w = gp
            N, dN_dL1, dN_dL2, dN_dL3 = _CURRENT_SHAPE_FUNC(L1, L2, L3)
            J_det, _, _ = element_jacobian(coords_c, dN_dL1, dN_dL2, dN_dL3)
            if J_det <= 0:
                continue
            dA = 0.5 * J_det * w
            omega_gp = float(np.dot(N, omega_e))
            omega_mean += omega_gp * dA
            A_total += dA
    omega_mean /= A_total
    omega -= omega_mean

    return omega, K_csr


def compute_torsion_constant(nodes, elements, omega, K_csr, Ixx_c, Iyy_c):
    """
    Saint-Venantova torzní konstanta dle Pilkey eq. 5.62 / sectionproperties:

       J = Ixx + Iyy - ω^T K ω

    kde Ixx, Iyy jsou centroidální momenty setrvačnosti a K je matice
    tuhosti Laplaceova operátoru.

    Tato formulace je MATEMATICKY EXAKTNÍ a je validována proti Pilkey
    benchmark sections (channel, arc, composite). Viz sectionproperties
    Theory dokumentaci.
    """
    omega_K_omega = float(omega @ (K_csr @ omega))
    J = Ixx_c + Iyy_c - omega_K_omega
    return J


# ════════════════════════════════════════════════════════════════════
#  STŘED SMYKU A WARPING KONSTANTA (Trefftzova metoda dle Pilkey)
# ════════════════════════════════════════════════════════════════════
#
# Pilkey (Chapter 6) odvodil exaktní výrazy pro střed smyku:
#
#   y_sc = (1/Δ) · [Iyy · Ixω - Ixy · Iyω]
#   z_sc = (1/Δ) · [Ixy · Ixω - Ixx · Iyω]    (znaménko dle konvence)
#
# kde:
#   Δ = Ixx · Iyy - Ixy²
#   Ixω = ∫_Ω z · ω dA   (warping × z)
#   Iyω = ∫_Ω y · ω dA   (warping × y)
#
# Pak normalizovaná warping function (sektorová souřadnice kolem SC):
#   ω_n(y,z) = ω(y,z) - y_sc · z + z_sc · y - ω_avg
#
# Warping konstanta:
#   Γ = ∫_Ω ω_n² dA
#
# Reference:
#   - Pilkey W.D. (2002), Chapter 6 (Shear Center) & 7 (Warping)
#   - sectionproperties Theory: "Shear Center" a "Warping Constant"

def compute_shear_center_and_warping(nodes, elements, omega, cy, cz,
                                     Ixx_c, Iyy_c, Ixy_c):
    """
    Vypočte:
      y_sc, z_sc – souřadnice středu smyku v centroidálním systému
      Iw (Γ)     – warping konstanta

    Implementace EXAKTNĚ dle sectionproperties (Theory dokumentace), což je
    Pilkey (2002) Chapter 7 - Trefftzova formulace:

      x_st = (Ixy · I_yω - Iyy · I_zω) / Δ
      y_st = (Ixx · I_yω - Ixy · I_zω) / Δ

      Γ = I_ω - Q_ω²/A - y_sc · I_zω + x_sc · I_yω

    kde (v sectionproperties notaci):
      i_xomega = ∫ x · ω dA = Iyw (naše ∫ y · ω dA)
      i_yomega = ∫ y · ω dA = Izw (naše ∫ z · ω dA)
      i_omega  = ∫ ω² dA
      q_omega  = ∫ ω dA   (mělo by být ≈0 po normalizaci, ale počítáme)
    """
    nodes_c = nodes - np.array([cy, cz])

    # ── Integrály ──
    Iyw = 0.0      # = ∫ y · ω dA (i_xomega ve sp)
    Izw = 0.0      # = ∫ z · ω dA (i_yomega ve sp)
    I_omega = 0.0  # = ∫ ω² dA
    Q_omega = 0.0  # = ∫ ω dA  (kontrolní – po normalizaci ≈ 0)

    for elem in elements:
        coords_c = nodes_c[elem]
        omega_e = omega[elem]
        for gp in _CURRENT_GAUSS:
            L1, L2, L3, w = gp
            N, dN_dL1, dN_dL2, dN_dL3 = _CURRENT_SHAPE_FUNC(L1, L2, L3)
            J_det, _, _ = element_jacobian(coords_c, dN_dL1, dN_dL2, dN_dL3)
            if J_det <= 0:
                continue
            dA = 0.5 * J_det * w
            y_gp = float(np.dot(N, coords_c[:, 0]))
            z_gp = float(np.dot(N, coords_c[:, 1]))
            omega_gp = float(np.dot(N, omega_e))
            Iyw     += y_gp * omega_gp * dA
            Izw     += z_gp * omega_gp * dA
            I_omega += omega_gp**2 * dA
            Q_omega += omega_gp * dA

    # ── Trefftz formulace SC (sectionproperties section.py:698-699) ──
    Delta = Ixx_c * Iyy_c - Ixy_c**2
    if abs(Delta) < 1e-20:
        return {'y_sc': 0.0, 'z_sc': 0.0, 'Iw': 0.0, 'omega_n': omega.copy(),
                'sc_check_diff': 0.0}

    # V notaci sectionproperties:
    #   x_st = (ixy_c · i_xomega - iyy_c · i_yomega) / Δ
    #   y_st = (ixx_c · i_xomega - ixy_c · i_yomega) / Δ
    # V naší notaci (y ↔ x, z ↔ y):
    y_sc_trefftz = (Ixy_c * Iyw - Iyy_c * Izw) / Delta
    z_sc_trefftz = (Ixx_c * Iyw - Ixy_c * Izw) / Delta

    # ── Alternativní (integrální) formulace SC dle Saade & Mohareb 2005 ──
    # SC je definován jako bod, kolem nějž je moment od smykového toku 0.
    # Toto je nezávislá kontrola Trefftzovy formulace.
    #
    # Integrály ∫y²·ω dA = Iyyw a ∫y·z·ω dA = Iyzw, ∫z²·ω dA = Izzw
    # SC podle Saade:
    #   y_sc = -∫(z·∂ω/∂y - y·∂ω/∂z) y dA / (2·Δ_s)  pro ν=0
    # Tato formulace vyžaduje gradient ω, který už máme implicitně přes FEM.
    # Pro jednoduchost zde uvedeme jen TREFFTZ jako hlavní + chybu vůči
    # symmetric-axis check.

    y_sc = y_sc_trefftz
    z_sc = z_sc_trefftz

    # Sanity check: pro symetrický profil podle osy y (Ixy_c ≈ 0)
    # by SC měl ležet ve stejné vertikální rovině jako těžiště.
    # → Iyw musí být téměř 0
    sc_check_diff = 0.0
    if abs(Ixy_c) / max(abs(Ixx_c), abs(Iyy_c), 1) < 1e-3:
        # Profil je symetrický kolem hlavních os (y a z)
        # Pro takový profil: SC = těžiště pokud má dvojí symetrii
        # → testujeme zda y_sc · Ixx + z_sc · Iyy = malá hodnota
        # (residuum po dělení Δ má být malé)
        scale = math.sqrt(Ixx_c**2 + Iyy_c**2)
        sc_check_diff = math.hypot(Iyw, Izw) / max(scale, 1)

    # ── Warping konstanta (sectionproperties section.py:714) ──
    #   γ = i_omega - q_omega²/A - y_se·i_xomega + x_se·i_yomega
    # V naší notaci:
    #   Γ = I_omega - Q_omega²/A - z_sc · Iyw + y_sc · Izw
    A_total = 0.0
    for elem in elements:
        coords_c = nodes_c[elem]
        for gp in _CURRENT_GAUSS:
            L1, L2, L3, w = gp
            N, dN_dL1, dN_dL2, dN_dL3 = _CURRENT_SHAPE_FUNC(L1, L2, L3)
            J_det, _, _ = element_jacobian(coords_c, dN_dL1, dN_dL2, dN_dL3)
            if J_det > 0:
                A_total += 0.5 * J_det * w

    Iw = I_omega - Q_omega**2 / A_total - z_sc * Iyw + y_sc * Izw

    # ── Normalizovaná sektorová souřadnice ω_n pro pozdější zobrazení ──
    # ω_n(y,z) = ω(y,z) - z_sc · y + y_sc · z - (konstanta tak aby ∫ω_n dA = 0)
    # Pozn: znaménko transformace pro Pilkey/sp konvenci
    omega_n = omega.copy()
    for i in range(len(nodes_c)):
        y_i = nodes_c[i, 0]
        z_i = nodes_c[i, 1]
        omega_n[i] = omega[i] - z_sc * y_i + y_sc * z_i

    # Re-normalizace na nulový průměr
    omega_n_mean = 0.0
    for elem in elements:
        coords_c = nodes_c[elem]
        on_e = omega_n[elem]
        for gp in _CURRENT_GAUSS:
            L1, L2, L3, w = gp
            N, dN_dL1, dN_dL2, dN_dL3 = _CURRENT_SHAPE_FUNC(L1, L2, L3)
            J_det, _, _ = element_jacobian(coords_c, dN_dL1, dN_dL2, dN_dL3)
            if J_det <= 0:
                continue
            dA = 0.5 * J_det * w
            omega_n_mean += float(np.dot(N, on_e)) * dA
    omega_n_mean /= A_total
    omega_n -= omega_n_mean

    return {
        'y_sc': y_sc,
        'z_sc': z_sc,
        'Iw': Iw,
        'omega_n': omega_n,
        'sc_check_diff': sc_check_diff,
    }


# ════════════════════════════════════════════════════════════════════
#  SMYKOVÉ FUNKCE Ψ, Φ (pro EXAKTNÍ τ rozdělení od Vy, Vz)
# ════════════════════════════════════════════════════════════════════
#
# Pilkey Chapter 6: pro průřez s Poissonovým číslem ν, smykové funkce
# Ψ (pro Vz) a Φ (pro Vy) splňují:
#
#   ∇²Ψ = -2(1+ν) · y     v Ω      (pro Vz na ose y)
#   ∂Ψ/∂n = -(... BC dle Pilkey eq. 6.71) ...
#
# Pro homogenní materiál a ν = 0 (asumpce ve většině inženýrských výpočtů
# průřezových charakteristik – Poisson nemá zásadní vliv na geometrii):
#
#   ∇²Ψ = 0                v Ω
#   ∂Ψ/∂n = n_z · [(Ixy/Ixx)·(y²-z²) + 2·(Iyy/...)... ] na ∂Ω
#
# Pro tuto verzi implementujeme Ψ, Φ jen pro účely VÝPOČTU SMYKOVÉ PLOCHY
# (As_y, As_z) – plné pole smykového napětí počítáme separátně níže.
#
# Smyková plocha (Pilkey eq. 6.91):
#   A_sy = κ_y · A   kde 1/κ_y = (1/A) · ∫_Ω (∂Φ/∂y - z)² + (∂Φ/∂z + y)² dA / (Iyy²)
# atd. – jednotlivé vzorce v sectionproperties theory.
#
# Pro jednoduchost (a soulad s Pilkey pro nahrávané ν=0): používáme
# stejné K matice (Laplaceův operátor) s upraveným pravostranným vektorem.

def solve_shear_functions(nodes, elements, cy, cz, Ixx_c, Iyy_c, Ixy_c, nu=0.0):
    """
    Řeší smykové funkce Ψ (pro Vy) a Φ (pro Vz) dle Pilkey eq. 6.71-6.75.

    Tyto funkce umožňují EXAKTNÍ výpočet smykového toku od posouvajících sil
    Vy a Vz pro průřez libovolného tvaru, včetně otevřených tenkostěnných
    sekcí. Nahrazují přibližný Žuravského vzorec τ = V·Q/(I·b).

    Implementace EXAKTNĚ dle sectionproperties (analysis/fea.py:_assemble_shear_load):

      Pomocné parametry (v každém Gaussově bodě):
        r  = y² - z²
        q  = 2·y·z
        d₁ = Ixx · r - Ixy · q       (pro Ψ – Vy)
        d₂ = Ixy · r + Ixx · q
        h₁ = -Ixy · r + Iyy · q      (pro Φ – Vz)
        h₂ = -Iyy · r - Ixy · q

      Elementární load vektor:
        f_psi += w · [ν/2 · B^T · [d₁, d₂] + 2·(1+ν) · N · (Ixx·y - Ixy·z)]
        f_phi += w · [ν/2 · B^T · [h₁, h₂] + 2·(1+ν) · N · (Iyy·z - Ixy·y)]

    Vrací:
      Psi, Phi: (n_nodes,) ndarray – smykové funkce
    """
    n_nodes = len(nodes)
    nodes_c = nodes - np.array([cy, cz])

    K = lil_matrix((n_nodes, n_nodes))
    F_psi = np.zeros(n_nodes)
    F_phi = np.zeros(n_nodes)

    for elem in elements:
        idx = elem
        coords_c = nodes_c[elem]

        Ke = np.zeros((_CURRENT_N_NODES_PER_ELEM, _CURRENT_N_NODES_PER_ELEM))
        Fe_psi = np.zeros(_CURRENT_N_NODES_PER_ELEM)
        Fe_phi = np.zeros(_CURRENT_N_NODES_PER_ELEM)

        for gp in _CURRENT_GAUSS:
            L1, L2, L3, w = gp
            N, dN_dL1, dN_dL2, dN_dL3 = _CURRENT_SHAPE_FUNC(L1, L2, L3)
            J_det, dN_dy, dN_dz = element_jacobian(coords_c, dN_dL1, dN_dL2, dN_dL3)
            if J_det <= 0 or dN_dy is None:
                continue
            dA = 0.5 * J_det * w
            y_c = float(np.dot(N, coords_c[:, 0]))
            z_c = float(np.dot(N, coords_c[:, 1]))

            # Tuhostní matice (Laplaceův operátor)
            Ke += (np.outer(dN_dy, dN_dy) + np.outer(dN_dz, dN_dz)) * dA

            # Pomocné parametry (Pilkey eq. 6.71-6.72)
            r = y_c**2 - z_c**2
            q = 2 * y_c * z_c
            d1 = Ixx_c * r - Ixy_c * q
            d2 = Ixy_c * r + Ixx_c * q
            h1 = -Ixy_c * r + Iyy_c * q
            h2 = -Iyy_c * r - Ixy_c * q

            # Load vektory pro Ψ (Vy) a Φ (Vz):
            #   Ψ: ν/2 · B^T · [d1, d2] + 2·(1+ν) · N · (Ixx·y - Ixy·z)
            #   Φ: ν/2 · B^T · [h1, h2] + 2·(1+ν) · N · (Iyy·z - Ixy·y)
            # B^T·[d1,d2] = dN/dy · d1 + dN/dz · d2 (gradient term)
            Fe_psi += dA * (
                (nu / 2) * (dN_dy * d1 + dN_dz * d2)
                + 2 * (1 + nu) * N * (Ixx_c * y_c - Ixy_c * z_c)
            )
            Fe_phi += dA * (
                (nu / 2) * (dN_dy * h1 + dN_dz * h2)
                + 2 * (1 + nu) * N * (Iyy_c * z_c - Ixy_c * y_c)
            )

        for a in range(_CURRENT_N_NODES_PER_ELEM):
            for b in range(_CURRENT_N_NODES_PER_ELEM):
                K[idx[a], idx[b]] += Ke[a, b]
            F_psi[idx[a]] += Fe_psi[a]
            F_phi[idx[a]] += Fe_phi[a]

    # Ukotvení (Ψ(0)=0, Φ(0)=0) - jinak singularita Laplaceova operátoru
    K_lil = K.tolil()
    K_lil[0, :] = 0
    K_lil[:, 0] = 0
    K_lil[0, 0] = 1.0
    K_csr = K_lil.tocsr()

    F_psi_mod = F_psi.copy(); F_psi_mod[0] = 0.0
    F_phi_mod = F_phi.copy(); F_phi_mod[0] = 0.0

    Psi = spsolve(K_csr, F_psi_mod)
    Phi = spsolve(K_csr, F_phi_mod)

    return Psi, Phi


def solve_warping_shear_function(nodes, elements, cy, cz, omega_n):
    """
    Řeší Vlasovovu warping shear function χ(y, z) pro výpočet τ_ω.

    Tato funkce je analogická ke Ψ, Φ ale s pravostrannou stranou závislou
    na warping function ω_n. Řeší Poissonovu rovnici:

      ∇²χ = -ω_n(y, z)   v Ω
      ∂χ/∂n = 0           na ∂Ω

    Po vyřešení dává τ_ω od Vlasovova sekundárního torzního momentu T_ω:

      τ_ω,y = (T_ω / I_ω) · ∂χ/∂y
      τ_ω,z = (T_ω / I_ω) · ∂χ/∂z

    Toto je ekvivalentní k tradiční Vlasovově formulci přes sektorový statický
    moment S_ω(s) na střednici, ale aplikovatelné i pro 2D FEM (bez nutnosti
    znát střednici).

    Reference:
      - Erkmen & Mohareb (2006) "Torsion analysis of thin-walled beams..."
      - Wagner & Gruttmann (2002) "A displacement method for the analysis of..."
      - sectionproperties analogie pro Ψ, Φ

    Vrací: chi (n_nodes,) – warping shear function
    """
    n_nodes = len(nodes)
    nodes_c = nodes - np.array([cy, cz])

    K = lil_matrix((n_nodes, n_nodes))
    F = np.zeros(n_nodes)

    for elem in elements:
        idx = elem
        coords_c = nodes_c[elem]
        omega_e = omega_n[elem]

        Ke = np.zeros((_CURRENT_N_NODES_PER_ELEM, _CURRENT_N_NODES_PER_ELEM))
        Fe = np.zeros(_CURRENT_N_NODES_PER_ELEM)

        for gp in _CURRENT_GAUSS:
            L1, L2, L3, w = gp
            N, dN_dL1, dN_dL2, dN_dL3 = _CURRENT_SHAPE_FUNC(L1, L2, L3)
            J_det, dN_dy, dN_dz = element_jacobian(coords_c, dN_dL1, dN_dL2, dN_dL3)
            if J_det <= 0 or dN_dy is None:
                continue
            dA = 0.5 * J_det * w
            omega_n_gp = float(np.dot(N, omega_e))

            # Tuhostní matice (Laplaceův operátor)
            Ke += (np.outer(dN_dy, dN_dy) + np.outer(dN_dz, dN_dz)) * dA

            # Load vektor: F_i = ∫ N_i · ω_n dA
            # (z rovnice ∇²χ = -ω_n po multiplikaci test fcí a integrace per partes)
            Fe += N * omega_n_gp * dA

        for a in range(_CURRENT_N_NODES_PER_ELEM):
            for b in range(_CURRENT_N_NODES_PER_ELEM):
                K[idx[a], idx[b]] += Ke[a, b]
            F[idx[a]] += Fe[a]

    # Ukotvení (χ(0)=0) - jinak singularita
    K_lil = K.tolil()
    K_lil[0, :] = 0
    K_lil[:, 0] = 0
    K_lil[0, 0] = 1.0
    K_csr = K_lil.tocsr()
    F_mod = F.copy(); F_mod[0] = 0.0

    chi = spsolve(K_csr, F_mod)
    return chi


def compute_shear_areas_and_deformation_coeffs(
        nodes, elements, cy, cz, Psi, Phi,
        Ixx_c, Iyy_c, Ixy_c, A, nu=0.0):
    """
    Vypočte:
      A_sy, A_sz – smykové plochy (effective shear areas) ve směrech y, z
      kappa_y, kappa_z – součinitele smykové deformace
      beta_x, beta_y – monosymmetry constants (pro lateral-torsional buckling)

    Dle Pilkey Chapter 6 (eq. 6.85) a sectionproperties section.py:716+.

    Smyková plocha:
      A_s = Δ_s² / κ  kde
      κ = ∫_Ω (Ψ_y - ν/2 · d_vec_y)² + (Ψ_z - ν/2 · d_vec_z)² dA
      Δ_s = 2·(1+ν)·(Ixx·Iyy - Ixy²)

    Monosymmetry (pro mono-symmetric I, T, U sections):
      βx = (1/Ixx)·∫(y²·z + z³)dA - 2·z_sc
      βy = (1/Iyy)·∫(z²·y + y³)dA - 2·y_sc

    POZN: V tuto chvíli ještě nemáme z_sc, y_sc, takže βx, βy se počítají
    odděleně v compute_shear_center.
    """
    nodes_c = nodes - np.array([cy, cz])

    # Smykové plochy A_sy, A_sz - dle Pilkey eq. 6.85.
    # Toto je EXAKTNÍ formulace pro Timošenkův smyk:
    #
    #   1/A_sy = (1/Δ_s²) · ∫_Ω [(Ψ - d_vec)·(Ψ - d_vec)] dA
    #
    # kde:
    #   Δ_s = 2(1+ν)(Ixx·Iyy - Ixy²)
    #   d_vec = vektor s složkami (d1, d2) z Pilkey eq. 6.71-6.72
    #
    # Implementace replikuje sectionproperties section.py:728+ (referenční
    # implementace Pilkey 6.85 v Pythonu, validováno proti benchmark sekcím).

    Delta_s = 2 * (1 + nu) * (Ixx_c * Iyy_c - Ixy_c**2)
    kappa_x = 0.0  # pro Vy (smyk podél y v naší notaci)
    kappa_y = 0.0  # pro Vz
    kappa_xy = 0.0  # smíšený

    for elem in elements:
        idx = elem
        coords_c = nodes_c[elem]
        psi_e = Psi[elem]
        phi_e = Phi[elem]

        for gp in _CURRENT_GAUSS:
            L1, L2, L3, w = gp
            N, dN_dL1, dN_dL2, dN_dL3 = _CURRENT_SHAPE_FUNC(L1, L2, L3)
            J_det, dN_dy, dN_dz = element_jacobian(coords_c, dN_dL1, dN_dL2, dN_dL3)
            if J_det <= 0 or dN_dy is None:
                continue
            dA = 0.5 * J_det * w
            y_c = float(np.dot(N, coords_c[:, 0]))
            z_c = float(np.dot(N, coords_c[:, 1]))

            # Gradient smykových funkcí
            psi_y = float(np.dot(dN_dy, psi_e))
            psi_z = float(np.dot(dN_dz, psi_e))
            phi_y = float(np.dot(dN_dy, phi_e))
            phi_z = float(np.dot(dN_dz, phi_e))

            # Pomocné
            r = y_c**2 - z_c**2
            q = 2 * y_c * z_c
            d1 = Ixx_c * r - Ixy_c * q
            d2 = Ixy_c * r + Ixx_c * q
            h1 = -Ixy_c * r + Iyy_c * q
            h2 = -Iyy_c * r - Ixy_c * q

            # Pilkey eq. 6.85 → sectionproperties section.py:740+
            # kappa_x = ∫ |grad_Psi - ν/2 · [d1,d2]|² dA
            # kappa_y = ∫ |grad_Phi - ν/2 · [h1,h2]|² dA
            # kappa_xy= ∫ (grad_Psi - ν/2·[d1,d2]) · (grad_Phi - ν/2·[h1,h2]) dA
            psi_corr_y = psi_y - (nu/2) * d1
            psi_corr_z = psi_z - (nu/2) * d2
            phi_corr_y = phi_y - (nu/2) * h1
            phi_corr_z = phi_z - (nu/2) * h2

            kappa_x  += (psi_corr_y**2 + psi_corr_z**2) * dA
            kappa_y  += (phi_corr_y**2 + phi_corr_z**2) * dA
            kappa_xy += (psi_corr_y * phi_corr_y + psi_corr_z * phi_corr_z) * dA

    # Smykové plochy
    if abs(kappa_x) > 1e-20 and abs(Delta_s) > 1e-20:
        A_sy = Delta_s**2 / kappa_x
    else:
        A_sy = 0.0
    if abs(kappa_y) > 1e-20 and abs(Delta_s) > 1e-20:
        A_sz = Delta_s**2 / kappa_y
    else:
        A_sz = 0.0

    return {
        'A_sy': A_sy, 'A_sz': A_sz,
        'kappa_y': kappa_x, 'kappa_z': kappa_y, 'kappa_yz': kappa_xy,
        'Delta_s': Delta_s,
    }


def compute_monosymmetry_constants(nodes, elements, cy, cz, Ixx_c, Iyy_c, y_sc, z_sc):
    """
    Monosymmetry konstanty βx, βy (Pilkey 6.91, sectionproperties section.py:830+).

    Pro mono-symmetric průřezy (T, U, asymetrický I) jsou kritické pro
    lateral-torsional buckling (LTB) ohýbaných nosníků.

    βx = (1/Ixx) · ∫_Ω (y²·z + z³) dA - 2·z_sc      (kolem osy y)
    βy = (1/Iyy) · ∫_Ω (z²·y + y³) dA - 2·y_sc      (kolem osy z)

    Pro doubly-symmetric (I, RHS, CHS) je βx = βy = 0.
    Pro symetrické kolem horizontální osy: βy = 0, βx ≠ 0.

    Vrací: dict s 'beta_x', 'beta_y' a "plus/minus" verzemi (pro různé strany).
    """
    nodes_c = nodes - np.array([cy, cz])
    int_x = 0.0  # ∫(y²·z + z³)dA
    int_y = 0.0  # ∫(z²·y + y³)dA

    for elem in elements:
        coords_c = nodes_c[elem]
        for gp in _CURRENT_GAUSS:
            L1, L2, L3, w = gp
            N, dN1, dN2, dN3 = _CURRENT_SHAPE_FUNC(L1, L2, L3)
            J_det, _, _ = element_jacobian(coords_c, dN1, dN2, dN3)
            if J_det <= 0:
                continue
            dA = 0.5 * J_det * w
            y_c = float(np.dot(N, coords_c[:, 0]))
            z_c = float(np.dot(N, coords_c[:, 1]))
            int_x += (y_c**2 * z_c + z_c**3) * dA
            int_y += (z_c**2 * y_c + y_c**3) * dA

    beta_x = int_x / Ixx_c - 2 * z_sc if abs(Ixx_c) > 1e-20 else 0.0
    beta_y = int_y / Iyy_c - 2 * y_sc if abs(Iyy_c) > 1e-20 else 0.0

    return {
        'beta_x': beta_x,
        'beta_y': beta_y,
        # +/- verze: sectionproperties dává plus_minus pro různé pozice neutrální osy
        'beta_x_plus':  -int_x / Ixx_c + 2 * z_sc if abs(Ixx_c) > 1e-20 else 0.0,
        'beta_x_minus':  int_x / Ixx_c - 2 * z_sc if abs(Ixx_c) > 1e-20 else 0.0,
        'beta_y_plus':  -int_y / Iyy_c + 2 * y_sc if abs(Iyy_c) > 1e-20 else 0.0,
        'beta_y_minus':  int_y / Iyy_c - 2 * y_sc if abs(Iyy_c) > 1e-20 else 0.0,
    }


# ════════════════════════════════════════════════════════════════════
#  HLAVNÍ ANALYZAČNÍ FUNKCE – ALL-IN-ONE
# ════════════════════════════════════════════════════════════════════

def analyze_section(outer, holes=None, max_area=None, nu=0.0,
                    compute_shear=True, element_order='T6'):
    """
    Kompletní průřezová analýza pomocí FEM Saint-Venant solveru.

    Vstup:
      outer: [(y, z), ...] – vnější polygon (mm)
      holes: list of [(y,z), ...] – díry
      max_area: max plocha elementu [mm²]
      nu: Poissonovo číslo (default 0)
      compute_shear: pokud True, řeší i smykové funkce Ψ, Φ a smykové plochy
      element_order: 'T6' (kvadratický, default) nebo 'T10' (kubický)
        T10 dává přesnější výsledky (chyba ~ h⁴ vs h³ pro T6), ale ~3-5x
        pomalejší výpočet a 1.7x více DOF.

    Výstup: dict s VŠEMI průřezovými charakteristikami.
    """
    # Přepneme element type
    set_element_order(element_order)

    # Triangulace vždy začíná jako T6
    nodes, elements = triangulate_section(outer, holes, max_area)

    # Pokud T10, upgradeujeme mesh
    if element_order == 'T10':
        nodes, elements = convert_t6_to_t10(nodes, elements)

    geom = compute_geometric_properties(nodes, elements)
    A   = geom['A']
    cy  = geom['cy']
    cz  = geom['cz']
    Ixx = geom['Ixx_c']
    Iyy = geom['Iyy_c']
    Ixy = geom['Ixy_c']

    # Warping function v těžišti
    omega, K_csr = solve_warping_function(nodes, elements, cy, cz)
    J = compute_torsion_constant(nodes, elements, omega, K_csr, Ixx, Iyy)

    # Střed smyku + warping konstanta (Trefftz)
    sc = compute_shear_center_and_warping(nodes, elements, omega, cy, cz,
                                          Ixx, Iyy, Ixy)
    y_sc = sc['y_sc']
    z_sc = sc['z_sc']

    # Průřezové moduly (vzhledem k vzdálenostem od těžiště k extrémním bodům)
    nodes_c = nodes - np.array([cy, cz])
    z_top = float(nodes_c[:, 1].max())
    z_bot = float(nodes_c[:, 1].min())
    y_right = float(nodes_c[:, 0].max())
    y_left  = float(nodes_c[:, 0].min())

    Wxx_top = Ixx / abs(z_top) if abs(z_top) > 1e-15 else 0.0
    Wxx_bot = Ixx / abs(z_bot) if abs(z_bot) > 1e-15 else 0.0
    Wyy_right = Iyy / abs(y_right) if abs(y_right) > 1e-15 else 0.0
    Wyy_left  = Iyy / abs(y_left)  if abs(y_left)  > 1e-15 else 0.0

    iy = math.sqrt(Iyy / A) if A > 0 else 0.0
    iz = math.sqrt(Ixx / A) if A > 0 else 0.0

    result = {
        # Geometrie
        'nodes': nodes, 'elements': elements,
        'A': A, 'cy': cy, 'cz': cz,
        # Centroidální momenty
        'Ixx_c': Ixx, 'Iyy_c': Iyy, 'Ixy_c': Ixy,
        # Hlavní osy
        'I11': geom['I11'], 'I22': geom['I22'], 'alpha_p': geom['alpha_p'],
        # Průřezové moduly
        'Wxx_top': Wxx_top, 'Wxx_bot': Wxx_bot,
        'Wyy_left': Wyy_left, 'Wyy_right': Wyy_right,
        'iy': iy, 'iz': iz,
        # Krajní vlákna
        'z_top': z_top, 'z_bot': z_bot,
        'y_left': y_left, 'y_right': y_right,
        # Torze a warping
        'J': J,
        'Iw': sc['Iw'],
        'y_sc': y_sc, 'z_sc': z_sc,
        'omega': omega, 'omega_n': sc['omega_n'],
    }

    # ── Smykové funkce a smykové plochy (volitelné) ──
    if compute_shear:
        Psi, Phi = solve_shear_functions(nodes, elements, cy, cz,
                                         Ixx, Iyy, Ixy, nu)
        # Warping shear function χ pro Vlasovův sekundární smyk τ_ω
        chi = solve_warping_shear_function(nodes, elements, cy, cz,
                                          sc['omega_n'])
        shear = compute_shear_areas_and_deformation_coeffs(
            nodes, elements, cy, cz, Psi, Phi,
            Ixx, Iyy, Ixy, A, nu)
        # Monosymmetry konstanty
        monosym = compute_monosymmetry_constants(
            nodes, elements, cy, cz, Ixx, Iyy, y_sc, z_sc)
        result.update({
            'Psi': Psi, 'Phi': Phi, 'chi': chi,
            'A_sy': shear['A_sy'], 'A_sz': shear['A_sz'],
            'beta_x': monosym['beta_x'], 'beta_y': monosym['beta_y'],
            'beta_x_plus': monosym['beta_x_plus'],
            'beta_x_minus': monosym['beta_x_minus'],
            'beta_y_plus': monosym['beta_y_plus'],
            'beta_y_minus': monosym['beta_y_minus'],
        })

    return result


# ════════════════════════════════════════════════════════════════════
#  MULTI-BODY (KOMPOZITNÍ) PRŮŘEZ – per-body FEM + paralelní osy
# ════════════════════════════════════════════════════════════════════
#
# Pro disjunktní kompozit (více oddělených těles) je warping problém
# nezávislý v každém tělese (∇²ω = 0 s vlastní okrajovou podmínkou). Proto
# spočteme FEM zvlášť pro každé tělo a výsledky složíme:
#   - A, centroid → vážený součet
#   - Ixx, Iyy, Ixy → parallel-axis transform k těžišti kompozitu
#   - J = Σ J_i (každé tělo nezávisle)
#   - Iω = Σ Iω_i (inženýrský odhad pro disjunktní kompozit)
#   - střed smyku → vážený průměr (přesné pro symetrické případy)
#   - smykové plochy A_sy, A_sz → součet
#
# CAVEAT: pro tělesa fyzicky propojená (např. sdílená hrana) je toto
# konzervativní podhodnocení – cooperace přes spojnici se neuvažuje.

def analyze_composite_section(bodies, max_area=None, nu=0.0,
                              compute_shear=True, element_order='T6'):
    """
    Kompozitní průřezová analýza (více těles, každé s vlastními dírami).

    bodies: list of (outer, holes) – outer i holes jsou [(y,z), ...] v mm.

    Vrací stejný dict jako `analyze_section`, navíc:
      'per_body': list dictů z `analyze_section` (pro diagnostiku)
      'is_composite': True/False
    """
    bodies = [(list(o), [list(h) for h in (hs or [])]) for o, hs in bodies]
    if len(bodies) == 0:
        raise ValueError("analyze_composite_section: žádná tělesa.")
    if len(bodies) == 1:
        outer, holes = bodies[0]
        r = analyze_section(outer, holes or None, max_area=max_area, nu=nu,
                            compute_shear=compute_shear,
                            element_order=element_order)
        r['per_body'] = [r]
        r['is_composite'] = False
        return r

    # ── per-body FEM ──
    per = []
    for outer, holes in bodies:
        r = analyze_section(outer, holes or None, max_area=max_area, nu=nu,
                            compute_shear=compute_shear,
                            element_order=element_order)
        per.append(r)

    # ── kompozitní A, centroid (vážený součet) ──
    A_tot = sum(r['A'] for r in per)
    if A_tot <= 1e-15:
        raise ValueError("Kompozit má nulovou plochu.")
    cY = sum(r['A'] * r['cy'] for r in per) / A_tot
    cZ = sum(r['A'] * r['cz'] for r in per) / A_tot

    # ── parallel-axis k těžišti kompozitu ──
    Ixx_c = Iyy_c = Ixy_c = 0.0
    for r in per:
        dy = r['cy'] - cY
        dz = r['cz'] - cZ
        Ixx_c += r['Ixx_c'] + r['A'] * dz*dz
        Iyy_c += r['Iyy_c'] + r['A'] * dy*dy
        Ixy_c += r['Ixy_c'] + r['A'] * dy*dz

    # ── torze (St. Venant): disjunktní → součet ──
    J_tot = sum(r['J'] for r in per)
    Iw_tot = sum(r.get('Iw', 0.0) for r in per)

    # ── střed smyku: pro symetrické případy = vážený průměr ──
    # (pro asymetrické kompozity je to inženýrský odhad)
    y_sc = sum(r['A'] * r.get('y_sc', r['cy']) for r in per) / A_tot
    z_sc = sum(r['A'] * r.get('z_sc', r['cz']) for r in per) / A_tot

    # ── smykové plochy: součet ──
    A_sy = sum(r.get('A_sy', 0.0) for r in per)
    A_sz = sum(r.get('A_sz', 0.0) for r in per)

    # ── extrémní vlákna a hlavní osy v centrovaných souřadnicích ──
    z_top = -1e18; z_bot = 1e18; y_left = 1e18; y_right = -1e18
    for r in per:
        # uzly tělesa jsou v globálních souřadnicích → posun k těžišti kompozitu
        zs = r['nodes'][:, 1] - cZ
        ys = r['nodes'][:, 0] - cY
        z_top = max(z_top, float(zs.max()))
        z_bot = min(z_bot, float(zs.min()))
        y_left = min(y_left, float(ys.min()))
        y_right = max(y_right, float(ys.max()))

    # hlavní osy z Ixx, Iyy, Ixy
    avg = (Ixx_c + Iyy_c) / 2.0
    diff = math.sqrt(((Ixx_c - Iyy_c) / 2.0) ** 2 + Ixy_c ** 2)
    I11 = avg + diff
    I22 = avg - diff
    alpha_p = 0.5 * math.degrees(math.atan2(-2 * Ixy_c, Ixx_c - Iyy_c))

    iy = math.sqrt(Iyy_c / A_tot) if A_tot > 0 else 0.0
    iz = math.sqrt(Ixx_c / A_tot) if A_tot > 0 else 0.0

    Wxx_top = Ixx_c / abs(z_top) if abs(z_top) > 1e-15 else 0.0
    Wxx_bot = Ixx_c / abs(z_bot) if abs(z_bot) > 1e-15 else 0.0
    Wyy_right = Iyy_c / abs(y_right) if abs(y_right) > 1e-15 else 0.0
    Wyy_left = Iyy_c / abs(y_left) if abs(y_left) > 1e-15 else 0.0

    return {
        'A': A_tot, 'cy': cY, 'cz': cZ,
        'Ixx_c': Ixx_c, 'Iyy_c': Iyy_c, 'Ixy_c': Ixy_c,
        'I11': I11, 'I22': I22, 'alpha_p': alpha_p,
        'iy': iy, 'iz': iz,
        'z_top': z_top, 'z_bot': z_bot,
        'y_left': y_left, 'y_right': y_right,
        'Wxx_top': Wxx_top, 'Wxx_bot': Wxx_bot,
        'Wyy_left': Wyy_left, 'Wyy_right': Wyy_right,
        'J': J_tot, 'Iw': Iw_tot,
        'y_sc': y_sc, 'z_sc': z_sc,
        'A_sy': A_sy, 'A_sz': A_sz,
        'per_body': per,
        'is_composite': True,
    }


# ════════════════════════════════════════════════════════════════════
#  SAMOSTATNÝ TEST – sanity check
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test 1: Kruh r=50 → očekáváme:
    #   A = π·r² = 7853.98 mm²
    #   Ixx = Iyy = π·r⁴/4 = 4,909,000 mm⁴
    #   J = π·r⁴/2 = 9,817,477 mm⁴ (analyticky)
    #   Iw = 0 (rotační symetrie)
    print("="*60)
    print("TEST 1: Kruh r=50")
    print("="*60)
    n_seg = 64
    outer = [(50 * math.cos(2*math.pi*i/n_seg), 50 * math.sin(2*math.pi*i/n_seg))
             for i in range(n_seg)]
    result = analyze_section(outer, max_area=5.0)
    print(f"A   = {result['A']:.2f} mm²   (analyt: {math.pi * 50**2:.2f})")
    print(f"Ixx = {result['Ixx_c']:.1f} mm⁴ (analyt: {math.pi * 50**4 / 4:.1f})")
    print(f"Iyy = {result['Iyy_c']:.1f} mm⁴")
    print(f"J   = {result['J']:.1f} mm⁴   (analyt: {math.pi * 50**4 / 2:.1f})")
    print(f"Iw  = {result['Iw']:.4e} mm⁶  (analyt: 0)")
    print(f"SC  = ({result['y_sc']:.4f}, {result['z_sc']:.4f}) mm (analyt: (0,0))")
