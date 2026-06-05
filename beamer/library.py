"""Knihovna materiálů a profilů – dvouúrovňová: uživatelská + sdílená.

  • Uživatelská (lokální): ~/.beamer/  – per-user, čtení i zápis (jako dosud).
  • Sdílená (úložiště):    složka z nastavení (SETTINGS.shared_library_dir) –
    společná knihovna; čtení vždy, zápis jen přes „Publikovat" (s potvrzením).

Obě úrovně používají stejný formát: materials.json, profiles.json.
Profily lze také importovat/exportovat do samostatných souborů.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict

from .model import Material, CrossSectionDef

_LOCAL_DIR = os.path.join(os.path.expanduser("~"), ".beamer")


# ── cesty ──────────────────────────────────────────────────
def _shared_dir() -> str:
    """Aktuálně nastavená sdílená složka (prázdné = vypnuto)."""
    from .settings import SETTINGS
    return (getattr(SETTINGS, "shared_library_dir", "") or "").strip()


def shared_dir_configured() -> bool:
    return bool(_shared_dir())


def _mat_path(base: str) -> str:
    return os.path.join(base, "materials.json")


def _prof_path(base: str) -> str:
    return os.path.join(base, "profiles.json")


# ── nízkoúrovňové IO ───────────────────────────────────────
def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _write(path, data) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _csdef_from_dict(d) -> CrossSectionDef:
    bodies_raw = d.get("bodies")
    bodies = None
    if bodies_raw:
        from .model import Body
        bodies = [Body(points=list(b.get("points") or []),
                       holes=list(b.get("holes") or [])) for b in bodies_raw]
    return CrossSectionDef(
        type=d.get("type", "i_section"),
        params=d.get("params", {}),
        polygon_points=d.get("polygon_points"),
        polygon_holes=d.get("polygon_holes"),
        polygon_thickness=d.get("polygon_thickness"),
        polygon_closed=d.get("polygon_closed", False),
        bodies=bodies,
    )


# ── materiály: čtení ───────────────────────────────────────
def _load_materials_from(base: str) -> list:
    out = []
    for d in _read(_mat_path(base)):
        try:
            out.append(Material(**d))
        except Exception:
            pass
    return out


def load_materials() -> list:
    """Zpětně kompatibilní: jen uživatelská knihovna."""
    return _load_materials_from(_LOCAL_DIR)


def load_materials_grouped() -> list:
    """[(source, [Material,...]), ...] kde source ∈ {"shared","user"}.
    Sdílená sekce jen pokud je složka nastavená (i prázdná → sekce s 0 položkami
    se vynechá)."""
    groups = []
    sd = _shared_dir()
    if sd:
        sm = _load_materials_from(sd)
        if sm:
            groups.append(("shared", sm))
    groups.append(("user", _load_materials_from(_LOCAL_DIR)))
    return groups


# ── materiály: zápis (uživatelská) ─────────────────────────
def _upsert(data, key_field, key_val, record):
    for i, d in enumerate(data):
        if d.get(key_field) == key_val:
            data[i] = record
            return
    data.append(record)


def save_material(mat: Material):
    data = _read(_mat_path(_LOCAL_DIR))
    md = asdict(mat); md["is_custom"] = True
    _upsert(data, "name", mat.name, md)
    _write(_mat_path(_LOCAL_DIR), data)


def delete_material(name: str):
    data = [d for d in _read(_mat_path(_LOCAL_DIR)) if d.get("name") != name]
    _write(_mat_path(_LOCAL_DIR), data)


# ── materiály: publikace (sdílená) ─────────────────────────
def publish_material(mat: Material) -> bool:
    """Zapíše materiál do SDÍLENÉ knihovny. False pokud složka není nastavená
    nebo zápis selhal."""
    sd = _shared_dir()
    if not sd:
        return False
    data = _read(_mat_path(sd))
    md = asdict(mat); md["is_custom"] = False
    _upsert(data, "name", mat.name, md)
    return _write(_mat_path(sd), data)


# ── profily: čtení ─────────────────────────────────────────
def _load_profiles_from(base: str) -> list:
    out = []
    for d in _read(_prof_path(base)):
        try:
            out.append((d.get("name", "?"), _csdef_from_dict(d.get("section", {}))))
        except Exception:
            pass
    return out


def load_profiles() -> list:
    """Zpětně kompatibilní: jen uživatelská knihovna. [(name, CrossSectionDef),…]"""
    return _load_profiles_from(_LOCAL_DIR)


def load_profiles_grouped() -> list:
    """[(source, [(name, sdef),…]), …] se source ∈ {"shared","user"}."""
    groups = []
    sd = _shared_dir()
    if sd:
        sp = _load_profiles_from(sd)
        if sp:
            groups.append(("shared", sp))
    groups.append(("user", _load_profiles_from(_LOCAL_DIR)))
    return groups


# ── profily: zápis (uživatelská) ───────────────────────────
def save_profile(name: str, sdef: CrossSectionDef):
    data = _read(_prof_path(_LOCAL_DIR))
    _upsert(data, "name", name, {"name": name, "section": asdict(sdef)})
    _write(_prof_path(_LOCAL_DIR), data)


def delete_profile(name: str):
    data = [d for d in _read(_prof_path(_LOCAL_DIR)) if d.get("name") != name]
    _write(_prof_path(_LOCAL_DIR), data)


# ── profily: publikace (sdílená) ───────────────────────────
def publish_profile(name: str, sdef: CrossSectionDef) -> bool:
    sd = _shared_dir()
    if not sd:
        return False
    data = _read(_prof_path(sd))
    _upsert(data, "name", name, {"name": name, "section": asdict(sdef)})
    return _write(_prof_path(sd), data)


# ── import / export profilu do souboru ─────────────────────
def export_profile(sdef: CrossSectionDef, name: str, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"beamer_profile": True, "name": name, "section": asdict(sdef)},
                  f, ensure_ascii=False, indent=2)


def import_profile(path: str):
    """Vrací (name, CrossSectionDef)."""
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    sec = d.get("section", d)   # umožni i holý CrossSectionDef
    return d.get("name", "profil"), _csdef_from_dict(sec)
