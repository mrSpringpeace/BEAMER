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


def segments_at(state, x: float, tol: float = 1e-3) -> list:
    """Úsek(y) přiléhající k poloze x. Uvnitř úseku 1 úsek; přesně na rozhraní
    dvou různých úseků vrátí oba (levý + pravý)."""
    out = [s for s in normalized_segments(state) if s.x1 - tol <= x <= s.x2 + tol]
    return out or [segment_at(state, x)]


def property_by_id(state, pid_id):
    for p in getattr(state, "properties", None) or []:
        if p.id == pid_id:
            return p
    return None


def section_by_id(state, sec_id):
    """Vrátí pojmenovaný průřez z knihovny state.sections podle id, nebo None."""
    if not sec_id:
        return None
    for s in getattr(state, "sections", None) or []:
        if getattr(s, "id", None) == sec_id:
            return s
    return None


def _resolve_secref(state, ref_id, embedded):
    """Odkaz do knihovny (ref_id) má přednost; když chybí/neexistuje, padá na
    zapečený (inline) průřez `embedded`."""
    lib = section_by_id(state, ref_id)
    return lib if lib is not None else embedded


def eff_defs(state, seg):
    """Efektivní (sec1, sec2) úseku – z PID (property_id), jinak inline.
    Oba zdroje mohou odkazovat do knihovny průřezů (sec1_id/sec2_id) – odkaz má
    přednost, jinak se použije zapečený sec1/sec2 (zpětná kompatibilita)."""
    pid = getattr(seg, "property_id", None)
    if pid:
        p = property_by_id(state, pid)
        if p is not None:
            s1 = _resolve_secref(state, getattr(p, "sec1_id", None), p.sec1)
            s2 = _resolve_secref(state, getattr(p, "sec2_id", None), p.sec2)
            return s1, s2
    s1 = _resolve_secref(state, getattr(seg, "sec1_id", None), seg.sec1)
    s2 = _resolve_secref(state, getattr(seg, "sec2_id", None), seg.sec2)
    return s1, s2


def eff_material_id(state, seg):
    """Efektivní material_id úseku – z PID, jinak inline."""
    pid = getattr(seg, "property_id", None)
    if pid:
        p = property_by_id(state, pid)
        if p is not None:
            return p.material_id
    return getattr(seg, "material_id", None)


def _def_in_span(sec1, sec2, x1, x2, x):
    """Definice průřezu v x z dvojice (sec1, sec2) na rozsahu [x1,x2]."""
    if sec2 is None:
        return sec1
    span = x2 - x1
    t = 0.0 if span <= 1e-9 else max(0.0, min(1.0, (x - x1) / span))
    return interp_def(sec1, sec2, t)


def def_for_segment(state, seg: SectionSegment, x: float) -> CrossSectionDef:
    """Definice průřezu konkrétního úseku v poloze x (PID/inline, interpolace pro
    tapered)."""
    sec1, sec2 = eff_defs(state, seg)
    return _def_in_span(sec1, sec2, seg.x1, seg.x2, x)


def material_for_segment(state, seg: SectionSegment):
    """Materiál konkrétního úseku (PID/inline material_id), jinak globální."""
    mid = eff_material_id(state, seg)
    if mid:
        for m in state.materials:
            if m.id == mid:
                return m
    return state.material()


def def_at(state, x: float) -> CrossSectionDef:
    """Definice průřezu v poloze x (PID/inline, interpolovaná pro tapered)."""
    return def_for_segment(state, segment_at(state, x), x)


class SectionResolver:
    """Staví/cachuje CrossSection podél nosníku. Pro prizmatické úseky cachuje
    podle identity úseku; pro tapered staví v daném x (parametrické ~okamžité)."""

    def __init__(self, state):
        self.state = state
        self._cache = {}

    def at(self, x: float) -> CrossSection:
        seg = segment_at(self.state, x)
        sec1, sec2 = eff_defs(self.state, seg)
        if sec2 is None:
            key = id(sec1)
            cs = self._cache.get(key)
            if cs is None:
                cs = build_section(sec1)
                self._cache[key] = cs
            return cs
        # tapered – kvantizuj x na ~1 mm kvůli cache
        span = seg.x2 - seg.x1
        t = 0.0 if span <= 1e-9 else max(0.0, min(1.0, (x - seg.x1)/span))
        key = (id(seg), id(sec1), id(sec2), round(t, 3))
        cs = self._cache.get(key)
        if cs is None:
            cs = build_section(interp_def(sec1, sec2, t))
            self._cache[key] = cs
        return cs

    def is_tapered_region(self, x: float) -> bool:
        _, sec2 = eff_defs(self.state, segment_at(self.state, x))
        return sec2 is not None

    def material_at(self, x: float):
        """Materiál úseku v poloze x (PID/inline material_id), jinak globální."""
        return material_for_segment(self.state, segment_at(self.state, x))

    def E_at(self, x: float):
        """Modul pružnosti E v poloze x. Priorita: přímý E (override) → materiál úseku."""
        seg = segment_at(self.state, x)
        if getattr(seg, "E", None) is not None:
            return seg.E
        return self.material_at(x).E

    def G_at(self, x: float):
        """Smykový modul G v poloze x (z materiálu úseku)."""
        return self.material_at(x).G
