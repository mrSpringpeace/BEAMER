"""Vlastní tíha nosníku (zatížení typu ``self_weight``).

Zatížení nese jen rozsah ``x1–x2`` a zatěžovací stav; hodnota se odvozuje
z modelu při každém výpočtu: lineární hmotnost μ(x) = Σ ρᵢ·Aᵢ(x) (složený PID
sčítá části s vlastní hustotou), spojité zatížení q(x) = −μ(x)·g, působí
svisle dolů (−z). Přetížení n se zadává faktorem zatěžovacího stavu.

Před výpočtem/kreslením se ``self_weight`` rozvine na obyčejná spojitá
zatížení (``expanded_loads``) – po úsecích konstantní, u náběhu po částech
lineární. Řešič tak nepotřebuje žádný nový mechanismus a výsledek vždy
odpovídá aktuálnímu průřezu i materiálu.

Jednotky: ρ [g/cm³] = 1e-6 kg/mm³, A [mm²] → μ [kg/mm], q = μ·g [N/mm].
"""
from __future__ import annotations

import copy

G_STD = 9.80665          # normální tíhové zrychlení [m/s²]
_RHO = 1e-6              # g/cm³ → kg/mm³
_TAPER_PIECES = 8        # počet lineárních kousků na úsek s náběhem


def _area(poly):
    from .section import _raw_moments
    return abs(_raw_moments(poly)[0]) if poly and len(poly) >= 3 else 0.0


def linear_mass(state, x, resolver=None) -> float:
    """Lineární hmotnost nosníku v poloze x [kg/mm]."""
    from .sections_along import (SectionResolver, segment_at, property_by_id)
    seg = segment_at(state, x)
    pid = getattr(seg, "property_id", None)
    prop = property_by_id(state, pid) if pid else None
    if prop is not None and getattr(prop, "composite_parts", None):
        from .composite import _positioned_bodies
        mu = 0.0
        for (outer, holes), mat in _positioned_bodies(state, prop):
            a = _area(outer) - sum(_area(h) for h in holes)
            mu += float(getattr(mat, "rho", 0.0) or 0.0) * _RHO * a
        return mu
    res = resolver or SectionResolver(state)
    A = float(res.at(x).A)
    rho = float(getattr(res.material_at(x), "rho", 0.0) or 0.0)
    return rho * _RHO * A


def _pieces(state, x1, x2):
    """Intervaly [a, b] rozsahu x1–x2 rozdělené na hranicích úseků; úseky
    s náběhem dál na `_TAPER_PIECES` kousků."""
    from .sections_along import normalized_segments, eff_defs
    out = []
    for seg in normalized_segments(state):
        a, b = max(x1, seg.x1), min(x2, seg.x2)
        if b - a <= 1e-9:
            continue
        _s1, s2 = eff_defs(state, seg)
        n = _TAPER_PIECES if s2 is not None else 1
        for i in range(n):
            out.append((a + (b - a) * i / n, a + (b - a) * (i + 1) / n, s2 is not None))
    return out


def expand(state, ld, resolver=None):
    """Rozvine jedno zatížení vlastní tíhou na seznam spojitých zatížení."""
    from .model import Load
    from .sections_along import SectionResolver
    res = resolver or SectionResolver(state)
    L = float(state.length)
    x1 = max(0.0, min(float(ld.x1), L))
    x2 = max(0.0, min(float(ld.x2), L))
    if x2 < x1:
        x1, x2 = x2, x1
    out = []
    for i, (a, b, tapered) in enumerate(_pieces(state, x1, x2)):
        if tapered:     # vzorek kousek dovnitř, ať se nebere sousední úsek
            eps = min(1e-6, (b - a) * 1e-6)
            qa = -linear_mass(state, a + eps, res) * G_STD
            qb = -linear_mass(state, b - eps, res) * G_STD
        else:
            qa = qb = -linear_mass(state, 0.5 * (a + b), res) * G_STD
        out.append(Load(id=f"{ld.id}#sw{i}", type="distributed", name=ld.name,
                        load_case_id=ld.load_case_id, x1=a, x2=b, q1=qa, q2=qb))
    return out


def expanded_loads(state, resolver=None):
    """Zatížení stavu s rozvinutou vlastní tíhou (ostatní beze změny)."""
    if not any(ld.type == "self_weight" for ld in state.loads):
        return list(state.loads)
    out = []
    for ld in state.loads:
        if ld.type == "self_weight":
            out.extend(expand(state, ld, resolver))
        else:
            out.append(ld)
    return out


def with_self_weight(state, resolver=None):
    """Mělká kopie stavu, kde je vlastní tíha nahrazena spojitými zatíženími.
    Bez vlastní tíhy vrací původní objekt (žádná kopie, žádná režie)."""
    if not any(ld.type == "self_weight" for ld in state.loads):
        return state
    st = copy.copy(state)
    st.loads = expanded_loads(state, resolver)
    return st


def summary(state, ld):
    """(hmotnost M [kg], tíha W [N]) zatížení vlastní tíhou – pro UI a report."""
    M = 0.0
    for d in expand(state, ld):
        M += -(d.q1 + d.q2) / 2.0 * (d.x2 - d.x1) / G_STD
    return M, M * G_STD
