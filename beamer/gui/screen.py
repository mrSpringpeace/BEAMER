"""Velikost oken vůči dostupné ploše obrazovky.

Při zvětšeném měřítku Windows (150–300 %) je logická plocha obrazovky malá
(např. 4K při 300 % = 1280×720 logických px). Pevné `resize(1500, 950)` pak
otevře okno přesahující obrazovku. `fit_resize` požadovanou velikost ořízne
na dostupnou plochu a okno vycentruje."""
from __future__ import annotations

from PySide6.QtGui import QGuiApplication


def available_size(widget=None):
    scr = None
    if widget is not None:
        p = widget.parentWidget()
        scr = (p.screen() if p is not None else None) or widget.screen()
    scr = scr or QGuiApplication.primaryScreen()
    return scr.availableGeometry() if scr is not None else None


def fit_resize(widget, w: int, h: int, margin: float = 0.95) -> bool:
    """`widget.resize(w, h)` oříznuté na `margin` dostupné plochy obrazovky.
    Vrátí True, pokud se muselo oříznout (obrazovka je menší než požadavek)."""
    geo = available_size(widget)
    if geo is None:
        widget.resize(w, h)
        return False
    mw, mh = int(geo.width() * margin), int(geo.height() * margin)
    fw, fh = min(w, mw), min(h, mh)
    widget.resize(fw, fh)
    if widget.parentWidget() is None:
        widget.move(geo.x() + (geo.width() - fw) // 2,
                    geo.y() + (geo.height() - fh) // 2)
    return fw < w or fh < h
