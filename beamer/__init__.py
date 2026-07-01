"""BEAMER – lokální Python aplikace pro statickou analýzu nosníku a napjatosti průřezu.

Letecké konstrukční výpočty:
  • VVÚ přímého nosníku (přímá metoda tuhosti, Euler-Bernoulli / Timoshenko)
  • Průřezové charakteristiky (A, Iy, Iz, Iyz, I1/I2, J/IT, Iω, střed smyku, ...)
  • Napjatost po průřezu (σ, τ_V, τ_t, von Mises) + diagramy
  • Posouzení MS / rezervní faktor

Výpočetní jádro pro průřez vychází z programu kolegy (section_analyzer),
beam solver z původní webové verze (přímá metoda tuhosti).
"""

__version__ = "1.20"

import os as _os


def icon_path(ext: str = "ico") -> str:
    """Cesta k ikoně programu (beam_icon.ico/png) v kořeni projektu."""
    root = _os.path.dirname(_os.path.dirname(__file__))
    return _os.path.join(root, f"beam_icon.{ext}")
