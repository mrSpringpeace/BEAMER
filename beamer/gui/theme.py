"""Vzhled aplikace (světlý / tmavý motiv) – design tokeny + Qt style sheet (QSS).

Inspirováno přístupem z projektu OpenAPL: dvě sady tokenů (light, dark) plní jeden
QSS builder. Klíčové pravidlo pro čistý tmavý režim: pozadí kreslí jen *kontejnery*,
`QLabel` je průhledný – text tak nikdy nesedí na obdélníku jiného odstínu než panel
za ním. Motiv se nastaví přes :func:`apply_theme` na QApplication.

Motiv „system" se rozliší podle systémové palety (tmavé pozadí okna → dark).
"""
from __future__ import annotations

# ── design tokeny ────────────────────────────────────────────────────────────
# s0 = okno/stránka, s1 = jemný panel, s2 = vyvýšený povrch (vstupy, karty).
LIGHT = {
    "s0": "#f4f6f9", "s1": "#eef2f7", "s2": "#ffffff",
    "border": "#dfe4ea", "border_strong": "#c2cad4",
    "text": "#1f2733", "text2": "#55606e", "muted": "#8a94a2",
    "accent": "#2f6fb0", "accent_bg": "#e6f1fb", "accent_fg": "#185fa5",
    "on_accent": "#ffffff",
    "ok_fg": "#1e7d46", "danger_fg": "#b3261e",
    "header_bg": "#e9e9e9", "header_bg_open": "#e0e4ea",
}
DARK = {
    "s0": "#1b222c", "s1": "#222b37", "s2": "#2a3441",
    "border": "#38424f", "border_strong": "#4a5666",
    "text": "#e7edf3", "text2": "#aeb8c4", "muted": "#8492a0",
    "accent": "#5b9bd9", "accent_bg": "#1d3346", "accent_fg": "#aacdf0",
    "on_accent": "#0b0f14",
    "ok_fg": "#7fcf9a", "danger_fg": "#e8917f",
    "header_bg": "#2f3a48", "header_bg_open": "#33445a",
}
_TOKENS = {"light": LIGHT, "dark": DARK}


def resolve(theme: str) -> str:
    """Přeloží 'system' na 'light'/'dark' podle systémové palety; jinak vrátí vstup."""
    if theme in ("light", "dark"):
        return theme
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            c = app.palette().window().color()
            # perceived brightness
            if (0.299*c.red() + 0.587*c.green() + 0.114*c.blue()) < 128:
                return "dark"
    except Exception:
        pass
    return "light"


def tokens(theme: str) -> dict:
    return _TOKENS.get(resolve(theme), LIGHT)


def build_qss(theme: str) -> str:
    t = tokens(theme)
    return f"""
    /* Základ: barva textu všude; pozadí kreslí jen kontejnery, QLabel je průhledný,
       takže text vždy odpovídá panelu za ním (čitelnost v tmavém režimu). */
    QWidget {{ color: {t['text']}; }}
    QMainWindow, QDialog {{ background: {t['s0']}; }}
    QLabel {{ background: transparent; }}
    QLabel#hint {{ color: {t['muted']}; font-size: 11px; }}
    QLabel#groupTitle {{ color: {t['text']}; font-weight: bold; font-size: 13px;
        padding: 2px 0 3px 0; border-bottom: 1px solid {t['border']}; }}
    QToolTip {{ background: {t['s2']}; color: {t['text']}; border: 1px solid {t['border']}; }}

    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QAbstractSpinBox {{
        background: {t['s2']}; color: {t['text']};
        border: 1px solid {t['border_strong']}; border-radius: 6px;
        padding: 2px 6px; selection-background-color: {t['accent']};
        selection-color: {t['on_accent']};
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
    QAbstractSpinBox:focus {{ border: 1px solid {t['accent']}; }}
    QComboBox QAbstractItemView {{
        background: {t['s2']}; color: {t['text']}; border: 1px solid {t['border']};
        selection-background-color: {t['accent_bg']}; selection-color: {t['accent_fg']};
    }}

    QPushButton {{
        background: {t['s2']}; color: {t['text']};
        border: 1px solid {t['border_strong']}; border-radius: 7px; padding: 5px 12px;
    }}
    QPushButton:hover {{ background: {t['s1']}; border-color: {t['accent']}; }}
    QPushButton:pressed {{ background: {t['accent_bg']}; }}
    QPushButton:disabled {{ color: {t['muted']}; border-color: {t['border']}; }}
    QPushButton#primary {{ background: {t['accent']}; color: {t['on_accent']}; border: none; font-weight: 500; }}
    QPushButton#primary:hover {{ background: {t['accent_fg']}; }}

    QTabWidget::pane {{ border: 1px solid {t['border']}; border-radius: 8px; top: -1px; }}
    QTabBar::tab {{ background: transparent; color: {t['text2']}; padding: 6px 12px;
        margin-right: 2px; border: 1px solid transparent;
        border-top-left-radius: 6px; border-top-right-radius: 6px; }}
    QTabBar::tab:selected {{ color: {t['accent_fg']}; border-color: {t['border']};
        border-bottom-color: {t['s0']}; background: {t['s0']}; }}
    QTabBar::tab:hover:!selected {{ color: {t['text']}; }}

    QTableWidget, QTableView, QTreeView, QListWidget {{
        background: {t['s2']}; alternate-background-color: {t['s1']};
        border: 1px solid {t['border']}; border-radius: 6px; gridline-color: {t['border']};
        selection-background-color: {t['accent_bg']}; selection-color: {t['accent_fg']}; }}
    QHeaderView::section {{ background: {t['s1']}; color: {t['text2']}; padding: 4px 8px;
        border: none; border-bottom: 1px solid {t['border']}; }}
    QTableCornerButton::section {{ background: {t['s1']}; border: none; }}

    QMenuBar {{ background: {t['s1']}; }}
    QMenuBar::item {{ background: transparent; padding: 5px 10px; }}
    QMenuBar::item:selected {{ background: {t['accent_bg']}; color: {t['accent_fg']}; }}
    QMenu {{ background: {t['s2']}; color: {t['text']}; border: 1px solid {t['border']}; }}
    QMenu::item {{ padding: 5px 22px; }}
    QMenu::item:selected {{ background: {t['accent_bg']}; color: {t['accent_fg']}; }}
    QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 8px; }}
    QStatusBar {{ background: {t['s1']}; color: {t['text2']}; }}

    QGroupBox {{ border: 1px solid {t['border']}; border-radius: 8px; margin-top: 8px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {t['text2']}; }}

    /* Sbalitelné sekce levého panelu (šedý pruh hlavičky) */
    QToolButton#collapsibleHeader {{ background: {t['header_bg']};
        border: 1px solid {t['border']}; border-radius: 3px; font-weight: bold;
        text-align: left; padding: 4px 6px; margin-top: 3px; }}
    QToolButton#collapsibleHeader:hover {{ background: {t['header_bg_open']}; }}
    QToolButton#collapsibleHeader:checked {{ background: {t['header_bg_open']};
        border-color: {t['border_strong']}; }}

    QScrollArea {{ border: none; background: {t['s0']}; }}
    QSplitter::handle {{ background: {t['border']}; }}
    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {t['border_strong']}; border-radius: 6px; min-height: 24px; }}
    QScrollBar::handle:vertical:hover {{ background: {t['muted']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 0; }}
    QScrollBar::handle:horizontal {{ background: {t['border_strong']}; border-radius: 6px; min-width: 24px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QCheckBox, QRadioButton {{ background: transparent; spacing: 6px; }}

    /* Levá ikonová lišta (pro budoucí přepínání karet vstupu) */
    QListWidget#card_rail {{ background: {t['s1']}; border: none;
        border-right: 1px solid {t['border']}; outline: 0; }}
    QListWidget#card_rail::item {{ border-radius: 8px; margin: 3px; }}
    QListWidget#card_rail::item:hover {{ background: {t['s2']}; }}
    QListWidget#card_rail::item:selected {{ background: {t['accent_bg']}; }}
    """


def _apply_palette(app, theme: str) -> None:
    """Nastaví QPalette dle motivu – aby i nestylované plochy (pozadí karet,
    vstupní pole) měly správnou barvu (samotný QSS je neobarví)."""
    from PySide6.QtGui import QPalette, QColor
    from PySide6.QtCore import Qt
    t = tokens(theme)
    C = lambda h: QColor(h)
    p = QPalette()
    p.setColor(QPalette.Window, C(t["s0"]))
    p.setColor(QPalette.WindowText, C(t["text"]))
    p.setColor(QPalette.Base, C(t["s2"]))
    p.setColor(QPalette.AlternateBase, C(t["s1"]))
    p.setColor(QPalette.Text, C(t["text"]))
    p.setColor(QPalette.Button, C(t["s2"]))
    p.setColor(QPalette.ButtonText, C(t["text"]))
    p.setColor(QPalette.ToolTipBase, C(t["s2"]))
    p.setColor(QPalette.ToolTipText, C(t["text"]))
    p.setColor(QPalette.PlaceholderText, C(t["muted"]))
    p.setColor(QPalette.Highlight, C(t["accent"]))
    p.setColor(QPalette.HighlightedText, C(t["on_accent"]))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, C(t["muted"]))
    app.setPalette(p)


def apply_theme(app, theme: str) -> None:
    """Aplikuje paletu + QSS motivu na QApplication + zachová platnou velikost fontu."""
    if app is None:
        return
    _apply_palette(app, theme)
    app.setStyleSheet(build_qss(theme))
    font = app.font()
    if font.pointSize() <= 0:
        font.setPointSize(10)
    app.setFont(font)


# ── matplotlib „inženýrský" styl grafů (připraveno pro kartu grafů) ──────────
def chart_rc(theme: str) -> dict:
    """rcParams pro čistý technický vzhled (bez horní/pravé osy, ticky dovnitř,
    jemný major+minor grid). Barvy dle motivu."""
    t = tokens(theme)
    return {
        "axes.titlesize": 10.5, "axes.titlelocation": "left",
        "axes.titlecolor": t["text"], "axes.labelsize": 9.5,
        "axes.labelcolor": t["text2"], "axes.edgecolor": t["border_strong"],
        "axes.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
        "axes.axisbelow": True, "axes.facecolor": t["s2"],
        "figure.facecolor": t["s2"],
        "xtick.direction": "in", "ytick.direction": "in",
        "xtick.color": t["text2"], "ytick.color": t["text2"],
        "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
        "grid.color": t["border"], "legend.frameon": False, "legend.fontsize": 8.5,
        "lines.linewidth": 1.9, "text.color": t["text"],
    }
