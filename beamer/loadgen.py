"""Generátor spojitého zatížení ze síly.

Nahradí příčnou bodovou sílu Fz staticky ekvivalentním lineárním spojitým
zatížením q1→q2 na úseku [a,b]. Princip: zachovat výslednici R=Fz a (volitelně)
těžiště x̄=x_F → reakce a VVÚ vně úseku zůstanou identické (Saint-Venant).

Lineární zatížení q(x), L=b−a, c=x_F−a (vzdálenost síly od levého kraje):
    R  = (q1+q2)/2·L
    x̄ = a + L·(q1+2q2)/(3(q1+q2))
Řešení pro zadané R=Fz a x̄=x_F:
    q1 = (2·Fz/L)·(2 − 3c/L)
    q2 = (2·Fz/L)·(3c/L − 1)
Pro c<L/3 vyjde q2<0 (a naopak) – „houpačka" protíná nulu, ale R i moment sedí.
"""
from __future__ import annotations

from dataclasses import dataclass

from .model import Load, new_id


@dataclass
class GenResult:
    q1: float
    q2: float
    R: float            # skutečná výslednice ∫q dx
    x_centroid: float   # skutečné těžiště zatížení
    moment_ok: bool     # zda těžiště odpovídá poloze síly (do tolerance)


def generate_q(a: float, b: float, Fz: float, x_F: float,
               kind: str = "trapezoid", tol: float = 1e-6) -> GenResult:
    """Vrátí (q1, q2, …) [N/mm] ekvivalentní spojité zatížení na [a,b].

    kind:
      "trapezoid" – lichoběžník zachovávající R i moment (umí i záporný konec),
      "uniform"   – konstantní q=Fz/L (zachová jen výslednici),
      "triangle"  – trojúhelník s vrcholem u síly (zachová jen výslednici).
    """
    L = b - a
    if L <= 1e-9:
        raise ValueError("Délka úseku musí být kladná (b > a).")
    c = x_F - a

    if kind == "uniform":
        q1 = q2 = Fz / L
    elif kind == "triangle":
        # vrchol na konci bližším síle, druhý konec nulový (R zachováno)
        if c <= L / 2.0:
            q1, q2 = 2.0 * Fz / L, 0.0
        else:
            q1, q2 = 0.0, 2.0 * Fz / L
    else:  # trapezoid – zachovat moment
        q1 = (2.0 * Fz / L) * (2.0 - 3.0 * c / L)
        q2 = (2.0 * Fz / L) * (3.0 * c / L - 1.0)

    R = (q1 + q2) / 2.0 * L
    if abs(q1 + q2) > 1e-12:
        x_centroid = a + L * (q1 + 2.0 * q2) / (3.0 * (q1 + q2))
    else:
        x_centroid = (a + b) / 2.0
    moment_ok = abs(x_centroid - x_F) <= max(tol, tol * L)
    return GenResult(q1, q2, R, x_centroid, moment_ok)


def make_loads(state, a: float, b: float, src: Load, x_F: float,
               kind: str, lc_id: str, name: str = "") -> tuple[Load, list[Load]]:
    """Z bodové síly `src` vytvoří spojité zatížení (z příčné Fz) a seznam
    zbytkových bodových zatížení nesoucích osovou sílu Fx a krut Fz·e
    (ty spojitý model neumí → ponechány jako bodové), umístěná v x_F.

    Vrací (distributed_load, extras).
    """
    res = generate_q(a, b, src.Fz, x_F, kind)
    base = src.name or ""
    dist = Load(new_id("load"), "distributed",
                name or (f"{base} (spojité)" if base else "Spojité ze síly"),
                lc_id)
    dist.x1, dist.x2, dist.q1, dist.q2 = a, b, res.q1, res.q2

    extras: list[Load] = []
    if abs(src.Fx) > 1e-12:                       # osová síla → bodová
        ax = Load(new_id("load"), "point_force",
                  f"{base} (osová N)" if base else "Zbytek – osová N", lc_id)
        ax.x, ax.Fx = x_F, src.Fx
        extras.append(ax)
    mk = src.Fz * src.eccentricity
    if abs(mk) > 1e-9:                            # krut Fz·e → bodový krut
        tq = Load(new_id("load"), "torsion",
                  f"{base} (krut Mk)" if base else "Zbytek – krut Mk", lc_id)
        tq.x, tq.Mx = x_F, mk
        extras.append(tq)
    return dist, extras
