"""Uživatelské nastavení (jazyk, formát čísel, zobrazení VVÚ) + perzistence.

Nastavení se ukládá do ~/.beamer/settings.json a je dostupné přes globální
singleton SETTINGS. Formátování čísel přes fmt().
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, asdict, field

_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".beamer")
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "settings.json")


@dataclass
class Settings:
    language: str = "en"            # "cs" | "en"
    number_format: str = "fixed"    # "fixed" | "scientific"
    decimals: int = 2               # počet desetinných míst
    vvu_combined: bool = False      # VVÚ v jednom grafu
    vvu_show_deform: bool = True    # ve sloučeném VVÚ zobrazit průhyb a pootočení
    shared_library_dir: str = ""    # složka sdílené knihovny (materiály/profily); "" = vypnuto
    last_dir: str = ""              # naposledy použitý adresář v dialozích otevřít/uložit
    theme: str = "system"           # vzhled: "system" | "light" | "dark"
    recent_files: list = field(default_factory=list)  # naposledy otevřené projekty (nejnovější první)
    panel_expanded: dict = field(default_factory=dict)  # stav rozbalení sekcí levého panelu {klíč: bool}

    def save(self):
        try:
            os.makedirs(_CONFIG_DIR, exist_ok=True)
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_recent(self, path: str, limit: int = 8):
        """Zařadí soubor na začátek seznamu naposledy otevřených (bez duplicit)."""
        if not path:
            return
        path = os.path.abspath(path)
        lst = [p for p in (self.recent_files or []) if os.path.abspath(p) != path]
        lst.insert(0, path)
        self.recent_files = lst[:limit]
        self.save()


def _load() -> Settings:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        s = Settings()
        for k in ("language", "number_format", "decimals", "vvu_combined",
                  "vvu_show_deform", "shared_library_dir", "last_dir",
                  "theme", "recent_files", "panel_expanded"):
            if k in d:
                setattr(s, k, d[k])
        return s
    except Exception:
        return Settings()


SETTINGS = _load()


def fmt(x, sig_for_g=4) -> str:
    """Naformátuje číslo dle aktuálního nastavení (fixed / scientific)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if math.isnan(v):
        return "—"
    if math.isinf(v):
        return "∞" if v > 0 else "−∞"
    d = max(0, int(SETTINGS.decimals))
    if SETTINGS.number_format == "scientific":
        return f"{v:.{d}e}"
    return f"{v:.{d}f}"
