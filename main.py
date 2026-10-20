"""Spouštěč aplikace BEAMER.

    python main.py
"""
import os
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

import beamer
from beamer.gui.main_window import MainWindow


def _apply_ui_scale():
    """Uživatelské měřítko rozhraní (Nastavení → Měřítko rozhraní) se násobí
    s měřítkem Windows. Musí se nastavit PŘED vytvořením QApplication.
    Ručně nastavené QT_SCALE_FACTOR v prostředí má přednost."""
    from beamer.settings import SETTINGS
    try:
        f = float(getattr(SETTINGS, "ui_scale", 1.0) or 1.0)
    except (TypeError, ValueError):
        f = 1.0
    f = min(max(f, 0.5), 3.0)
    if abs(f - 1.0) > 1e-3 and "QT_SCALE_FACTOR" not in os.environ:
        os.environ["QT_SCALE_FACTOR"] = f"{f:g}"


def main():
    _apply_ui_scale()
    app = QApplication(sys.argv)
    app.setApplicationName("BEAMER")
    for ext in ("ico", "png"):
        p = beamer.icon_path(ext)
        if os.path.exists(p):
            app.setWindowIcon(QIcon(p))
            break
    from beamer.settings import SETTINGS
    from beamer.gui.theme import apply_theme
    from beamer.gui.plots import apply_chart_theme
    apply_theme(app, SETTINGS.theme)
    apply_chart_theme(SETTINGS.theme)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
