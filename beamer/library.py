"""Knihovna materiálů a profilů uložená v programu (~/.beamer/).

Materiály i profily se ukládají do JSON v adresáři nastavení a jsou dostupné
napříč projekty. Profily lze také importovat/exportovat do samostatných souborů.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict

from .model import Material, CrossSectionDef

_DIR = os.path.join(os.path.expanduser("~"), ".beamer")
_MAT_PATH = os.path.join(_DIR, "materials.json")
_PROF_PATH = os.path.join(_DIR, "profiles.json")


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _write(path, data):
    try:
        os.makedirs(_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _csdef_from_dict(d) -> CrossSectionDef:
    return CrossSectionDef(
        type=d.get("type", "i_section"),
        params=d.get("params", {}),
        polygon_points=d.get("polygon_points"),
        polygon_holes=d.get("polygon_holes"),
        polygon_thickness=d.get("polygon_thickness"),
        polygon_closed=d.get("polygon_closed", False),
    )


# ── materiály ──────────────────────────────────────────────
def load_materials() -> list:
    out = []
    for d in _read(_MAT_PATH):
        try:
            out.append(Material(**d))
        except Exception:
            pass
    return out


def save_material(mat: Material):
    data = _read(_MAT_PATH)
    md = asdict(mat)
    md["is_custom"] = True
    # přepiš podle názvu, jinak přidej
    for i, d in enumerate(data):
        if d.get("name") == mat.name:
            data[i] = md
            break
    else:
        data.append(md)
    _write(_MAT_PATH, data)


def delete_material(name: str):
    data = [d for d in _read(_MAT_PATH) if d.get("name") != name]
    _write(_MAT_PATH, data)


# ── profily ────────────────────────────────────────────────
def load_profiles() -> list:
    """Vrací [(name, CrossSectionDef), ...]."""
    out = []
    for d in _read(_PROF_PATH):
        try:
            out.append((d.get("name", "?"), _csdef_from_dict(d.get("section", {}))))
        except Exception:
            pass
    return out


def save_profile(name: str, sdef: CrossSectionDef):
    data = _read(_PROF_PATH)
    pd = {"name": name, "section": asdict(sdef)}
    for i, d in enumerate(data):
        if d.get("name") == name:
            data[i] = pd
            break
    else:
        data.append(pd)
    _write(_PROF_PATH, data)


def delete_profile(name: str):
    data = [d for d in _read(_PROF_PATH) if d.get("name") != name]
    _write(_PROF_PATH, data)


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
