"""Spouštěč aplikace BEAMER.

    python main.py
"""
import os
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

import beamer
from beamer.gui.main_window import MainWindow


def main():
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
