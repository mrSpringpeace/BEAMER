"""Proměnný průřez podél nosníku – resolver průřezu v poloze x.

Podporuje:
  • jeden průřez na celý nosník (state.section_segments prázdné → state.cross_section)
  • prizmatické úseky (každý úsek konstantní průřez)
  • tapered (náběh) – plynulá změna stejného typu průřezu interpolací parametrů;
    řeší se jemným dělením na prvky se skutečným průřezem v každém místě.
"""
from __future__ import annotations

import copy

from .model import CrossSectionDef, SectionSegment
from .section import build_section, CrossSection


def interp_def(d1: CrossSectionDef, d2: CrossSectionDef, t: float) -> CrossSectionDef:
    """Interpoluje definici průřezu mezi d1 (t=0) a d2 (t=1).
    Vyžaduje stejný typ. Parametry / body polygonu se interpolují lineárně."""
    if d1.type != d2.type:
        raise ValueError("Náběh (tapered) vyžaduje stejný typ průřezu na obou koncích.")
    if d1.type == "polygon":
        p1 = d1.polygon_points or []
        p2 = d2.polygon_points or []
        if len(p1) != len(p2) or not p1:
            raise ValueError("Tapered polygon vyžaduje stejný počet bodů na obou koncích.")
        pts = [{"y": (1-t)*a["y"] + t*b["y"], "z": (1-t)*a["z"] + t*b["z"]}
               for a, b in zip(p1, p2)]
        return CrossSectionDef(type="polygon", polygon_points=pts)
    params = {}
    keys = set(d1.params) | set(d2.params)
    for k in keys:
        v1 = float(d1.params.get(k, d2.params.get(k, 0)))
        v2 = float(d2.params.get(k, d1.params.get(k, 0)))
        params[k] = (1-t)*v1 + t*v2
    return CrossSectionDef(type=d1.type, params=params)


def normalized_segments(state) -> list:
    """Vrátí seznam SectionSegment pokrývající [0, length].
    Pokud je definováno více úseků, doplní mezery prizmatickými úseky."""
    if not state.section_segments:
        return [SectionSegment(0.0, state.length, state.cross_section, None)]
    segs = sorted(state.section_segments, key=lambda s: s.x1)
    return segs


def segment_at(state, x: float) -> SectionSegment:
    for seg in normalized_segments(state):
        if seg.x1 - 1e-6 <= x <= seg.x2 + 1e-6:
            return seg
    # mimo definované úseky → nejbližší
    segs = normalized_segments(state)
    return segs[0] if x < segs[0].x1 else segs[-1]


def def_at(state, x: float) -> CrossSectionDef:
    """Definice průřezu v poloze x (interpolovaná pro tapered)."""
    seg = segment_at(state, x)
    if not seg.tapered:
        return seg.sec1
    span = seg.x2 - seg.x1
    t = 0.0 if span <= 1e-9 else max(0.0, min(1.0, (x - seg.x1)/span))
    return interp_def(seg.sec1, seg.sec2, t)


class SectionResolver:
    """Staví/cachuje CrossSection podél nosníku. Pro prizmatické úseky cachuje
    podle identity úseku; pro tapered staví v daném x (parametrické ~okamžité)."""

    def __init__(self, state):
        self.state = state
        self._cache = {}

    def at(self, x: float) -> CrossSection:
        seg = segment_at(self.state, x)
        if not seg.tapered:
            key = id(seg.sec1)
            cs = self._cache.get(key)
            if cs is None:
                cs = build_section(seg.sec1)
                self._cache[key] = cs
            return cs
        # tapered – kvantizuj x na ~1 mm kvůli cache
        span = seg.x2 - seg.x1
        t = 0.0 if span <= 1e-9 else max(0.0, min(1.0, (x - seg.x1)/span))
        key = (id(seg), round(t, 3))
        cs = self._cache.get(key)
        if cs is None:
            cs = build_section(interp_def(seg.sec1, seg.sec2, t))
            self._cache[key] = cs
        return cs

    def is_tapered_region(self, x: float) -> bool:
        return segment_at(self.state, x).tapered

    def material_at(self, x: float):
        """Materiál úseku v poloze x (dle material_id), jinak globální materiál."""
        seg = segment_at(self.state, x)
        mid = getattr(seg, "material_id", None)
        if mid:
            for m in self.state.materials:
                if m.id == mid:
                    return m
        return self.state.material()

    def E_at(self, x: float):
        """Modul pružnosti E v poloze x. Priorita: přímý E (override) → materiál úseku."""
        seg = segment_at(self.state, x)
        if getattr(seg, "E", None) is not None:
            return seg.E
        return self.material_at(x).E

    def G_at(self, x: float):
        """Smykový modul G v poloze x (z materiálu úseku)."""
        return self.material_at(x).G
