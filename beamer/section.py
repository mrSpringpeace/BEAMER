"""Výpočetní jádro průřezu a napjatosti.

Portováno z kolegova programu (section_analyzer) – ověřené jádro:
  • přesné charakteristiky polygonu (Greenova věta)
  • scanline statický moment Q, šířka, tloušťka stěny
  • IT (St. Venant) – 4 strategie, warping Iω (Vlasov), střed smyku
  • napjatost σ / τ_Vz / τ_Vy / τ_t / von Mises a průběhové profily

Konvence: x = vodorovná osa (y v beam značení), z = svislá osa.
Polygon `pts_xy` = [(x_mm, z_mm), ...] v absolutních souřadnicích.
"""
from __future__ import annotations

import math
import numpy as np


# ═══════════════════════════════════════════════════════════
#  GEOMETRIE – vrstvy pro kruh
# ═══════════════════════════════════════════════════════════

def slices_from_circle(cx, cy, r_out, r_in=0.0, n=240):
    """Vrstvy (slices) pro kruhový průřez nebo mezikruží. Vrací [zb,zt,yl,yr] v metrech."""
    slices = []
    y_bot = cy - r_out
    y_top = cy + r_out
    dy = (y_top - y_bot) / n
    for i in range(n):
        zb = y_bot + i * dy
        zt = zb + dy
        zm = (zb + zt) / 2
        dz = zm - cy
        if abs(dz) > r_out:
            continue
        half_out = math.sqrt(max(r_out**2 - dz**2, 0))
        half_in = math.sqrt(max(r_in**2 - dz**2, 0)) if r_in > 0 else 0.0
        if r_in > 0 and half_in > 0:
            slices.append([zb/1e3, zt/1e3, (cx - half_out)/1e3, (cx - half_in)/1e3])
            slices.append([zb/1e3, zt/1e3, (cx + half_in)/1e3, (cx + half_out)/1e3])
        else:
            slices.append([zb/1e3, zt/1e3, (cx - half_out)/1e3, (cx + half_out)/1e3])
    return slices


# ═══════════════════════════════════════════════════════════
#  POMOCNÉ FUNKCE PRŮŘEZU
# ═══════════════════════════════════════════════════════════

def _raw_moments(pts):
    """Signed momenty polygonu k počátku (Greenova věta).
    Vrátí (M00, M10, M01, M20, M02, M11) — kladná orientace CCW, záporná CW.
    Slouží jako stavební kámen pro kompozitní průřez (outer kladný, holes záporné)."""
    n = len(pts)
    A2 = Sx = Sz = Szz = Sxx = Sxz = 0.0
    for i in range(n):
        xi, zi = pts[i]
        xj, zj = pts[(i + 1) % n]
        c = xi*zj - xj*zi
        A2 += c
        Sx += (xi + xj)*c
        Sz += (zi + zj)*c
        Szz += (zi**2 + zi*zj + zj**2)*c
        Sxx += (xi**2 + xi*xj + xj**2)*c
        Sxz += (xi*zj + 2*xi*zi + 2*xj*zj + xj*zi)*c
    return A2/2.0, Sx/6.0, Sz/6.0, Sxx/12.0, Szz/12.0, Sxz/24.0


def _composite_moments(bodies):
    """Souhrnné momenty kompozitního průřezu = list of (outer_pts, [hole_pts,...]).
    Outer příspěvek se započítá kladně, díry odečtou. Orientace polygonů se
    automaticky normalizuje (CCW = kladný objem). Vrátí (A, cx, cz, Iy, Iz, Iyz)
    k těžišti kompozitu, nebo None pokud neplatné."""
    M00 = M10 = M01 = M20 = M02 = M11 = 0.0
    for outer, holes in bodies:
        if not outer or len(outer) < 3:
            continue
        m00, m10, m01, m20, m02, m11 = _raw_moments(outer)
        sg = 1.0 if m00 >= 0 else -1.0
        M00 += sg*m00; M10 += sg*m10; M01 += sg*m01
        M20 += sg*m20; M02 += sg*m02; M11 += sg*m11
        for h in holes:
            if not h or len(h) < 3:
                continue
            h00, h10, h01, h20, h02, h11 = _raw_moments(h)
            sgh = 1.0 if h00 >= 0 else -1.0
            M00 -= sgh*h00; M10 -= sgh*h10; M01 -= sgh*h01
            M20 -= sgh*h20; M02 -= sgh*h02; M11 -= sgh*h11
    if M00 <= 1e-12:
        return None
    cx = M10 / M00; cz = M01 / M00
    Iy = M02 - M00*cz**2     # ∫z² dA k těžišti
    Iz = M20 - M00*cx**2
    Iyz = M11 - M00*cx*cz
    return M00, cx, cz, Iy, Iz, Iyz


def _poly_props(pts_xy):
    """Přesné charakteristiky polygonu (Greenova věta). Vrací A, cx, cz, Iy, Iz, Iyz."""
    n = len(pts_xy)
    A2 = Sx = Sz = Szz = Sxx = Sxz = 0.0
    for i in range(n):
        xi, zi = pts_xy[i]
        xj, zj = pts_xy[(i + 1) % n]
        c = xi*zj - xj*zi
        A2 += c
        Sx += (xi+xj)*c
        Sz += (zi+zj)*c
        Szz += (zi**2 + zi*zj + zj**2)*c
        Sxx += (xi**2 + xi*xj + xj**2)*c
        Sxz += (xi*zj + 2*xi*zi + 2*xj*zj + xj*zi)*c
    A = A2/2
    sg = 1 if A >= 0 else -1
    A = abs(A)
    if A < 1e-12:
        return 0, 0, 0, 0, 0, 0
    cx = sg*Sx/(6*A)
    cz = sg*Sz/(6*A)
    Iy = abs(sg*Szz/12) - A*cz**2      # ∫z²dA – k vodorovné ose
    Iz = abs(sg*Sxx/12) - A*cx**2      # ∫x²dA – ke svislé ose
    Iyz = sg*Sxz/24 - A*cx*cz
    return A, cx, cz, Iy, Iz, Iyz


def _poly_Q_scanline(pts_xy, z_cut_mm, n_sub=500):
    """Statický moment Q části polygonu NAD z_cut [mm]. Scanline. Vrací mm³."""
    all_z = [p[1] for p in pts_xy]
    z_top = max(all_z)
    z_bot = min(all_z)
    if z_cut_mm >= z_top:
        return 0.0
    if z_cut_mm <= z_bot:
        A, cx, cz, Iy, Iz, _ = _poly_props(pts_xy)
        return A * cz
    z_start = max(z_cut_mm, z_bot)
    dz = (z_top - z_start) / n_sub
    Q = 0.0
    n = len(pts_xy)
    for k in range(n_sub):
        zm = z_start + (k + 0.5) * dz
        xs = []
        for i in range(n):
            xi, zi = pts_xy[i]
            xj, zj = pts_xy[(i + 1) % n]
            if min(zi, zj) <= zm < max(zi, zj):
                t = (zm - zi)/(zj - zi)
                xs.append(xi + t*(xj - xi))
        if len(xs) >= 2:
            xs.sort()
            for j in range(0, len(xs) - 1, 2):
                Q += (xs[j+1] - xs[j]) * zm * dz
    return Q


def _scan_intersections(poly, z_mm):
    """Setříděné x-souřadnice průsečíků polygonu s horizontálou z=z_mm."""
    n = len(poly)
    xs = []
    for i in range(n):
        xi, zi = poly[i]
        xj, zj = poly[(i + 1) % n]
        if min(zi, zj) <= z_mm <= max(zi, zj) and abs(zj - zi) > 1e-9:
            t = (z_mm - zi) / (zj - zi)
            xs.append(xi + t * (xj - xi))
    xs.sort()
    return xs


def _width_at_z_composite(bodies_c, z_mm):
    """Šířka kompozitního průřezu v úrovni z (mm od těžiště).
    Pro každé těleso even-odd s vlastními dírami; výsledky se sčítají."""
    total = 0.0
    for outer, holes in bodies_c:
        xs = list(_scan_intersections(outer, z_mm))
        for h in holes:
            xs.extend(_scan_intersections(h, z_mm))
        xs.sort()
        for j in range(0, len(xs) - 1, 2):
            total += xs[j + 1] - xs[j]
    return total if total > 1e-15 else 0.0


def _Q_at_z_composite(bodies_c, z_cut_mm, z_top_mm, n_sub=500):
    """∫(z'-0)·dA pro část nad z_cut, k těžišti. mm³."""
    if z_cut_mm >= z_top_mm:
        return 0.0
    dz = (z_top_mm - z_cut_mm) / n_sub
    Q = 0.0
    for k in range(n_sub):
        zm = z_cut_mm + (k + 0.5) * dz
        w = _width_at_z_composite(bodies_c, zm)
        if w > 0:
            Q += w * zm * dz
    return Q


def _scan_intersections_v(poly, x_mm):
    """Setříděné z-souřadnice průsečíků polygonu s vertikálou x=x_mm."""
    n = len(poly)
    zs = []
    for i in range(n):
        xi, zi = poly[i]
        xj, zj = poly[(i + 1) % n]
        if min(xi, xj) <= x_mm <= max(xi, xj) and abs(xj - xi) > 1e-9:
            t = (x_mm - xi) / (xj - xi)
            zs.append(zi + t * (zj - zi))
    zs.sort()
    return zs


def _height_at_y_composite(bodies_c, y_mm):
    """Celková (svislá) výška kompozitu na vertikále x=y_mm."""
    total = 0.0
    for outer, holes in bodies_c:
        zs = list(_scan_intersections_v(outer, y_mm))
        for h in holes:
            zs.extend(_scan_intersections_v(h, y_mm))
        zs.sort()
        for j in range(0, len(zs) - 1, 2):
            total += zs[j + 1] - zs[j]
    return total if total > 1e-15 else 0.0


def _Q_Vy_at_y_composite(bodies_c, y_cut_mm, n_sub=500):
    """∫y·dA pro část kompozitu vpravo od y_cut, k těžišti. mm³."""
    # globální rozsah napříč všemi tělesy
    y_max = -1e18
    for outer, _ in bodies_c:
        for x, _z in outer:
            if x > y_max:
                y_max = x
    if y_cut_mm >= y_max:
        return 0.0
    dy = (y_max - y_cut_mm) / n_sub
    Q = 0.0
    for k in range(n_sub):
        ym = y_cut_mm + (k + 0.5) * dy
        h = _height_at_y_composite(bodies_c, ym)
        if h > 0:
            Q += h * ym * dy
    return Q


def _y_extreme_at_z_composite(bodies_c, z_mm):
    """Krajní y (max abs) v úrovni z napříč tělesy. 0 pokud nikde nezasahuje."""
    best = 0.0
    found = False
    for outer, _ in bodies_c:
        xs = _scan_intersections(outer, z_mm)
        if xs:
            found = True
            cand = max([xs[0], xs[-1]], key=abs)
            if abs(cand) > abs(best):
                best = cand
    return best if found else 0.0


def _t_wall_at_composite(bodies_c, z_mm, n_x=6):
    """Tloušťka stěny (min) v úrovni z přes všechna tělesa kompozitu."""
    t_min = 1e9
    for outer, holes in bodies_c:
        xs_h = list(_scan_intersections(outer, z_mm))
        for h in holes:
            xs_h.extend(_scan_intersections(h, z_mm))
        xs_h.sort()
        if len(xs_h) < 2:
            continue
        for j in range(0, len(xs_h) - 1, 2):
            x_lo, x_hi = xs_h[j], xs_h[j + 1]
            w = x_hi - x_lo
            if w < 1e-3:
                continue
            for k in range(n_x):
                x_s = x_lo + w * (k + 0.5) / n_x
                # vertikální průnik všech polygonů (outer + holes) tělesa
                zs_v = list(_scan_intersections_v(outer, x_s))
                for h in holes:
                    zs_v.extend(_scan_intersections_v(h, x_s))
                zs_v.sort()
                for m in range(0, len(zs_v) - 1, 2):
                    h_v = zs_v[m + 1] - zs_v[m]
                    if h_v > 1e-3:
                        t_min = min(t_min, min(w, h_v))
    return t_min if t_min < 1e9 else 1e-15


def _poly_width_at(pts_xy, z_mm):
    """Šířka průřezu v úrovni z [mm] – scanline."""
    n = len(pts_xy)
    xs = []
    for i in range(n):
        xi, zi = pts_xy[i]
        xj, zj = pts_xy[(i + 1) % n]
        if min(zi, zj) <= z_mm <= max(zi, zj) and abs(zj - zi) > 1e-9:
            t = (z_mm - zi)/(zj - zi)
            xs.append(xi + t*(xj - xi))
    if len(xs) < 2:
        return 1e-15
    xs.sort()
    w = sum(xs[j+1] - xs[j] for j in range(0, len(xs) - 1, 2))
    return w if w > 1e-15 else 1e-15


# ═══════════════════════════════════════════════════════════
#  HLAVNÍ TŘÍDA
# ═══════════════════════════════════════════════════════════

class CrossSection:
    """Průřezové charakteristiky a napjatostní analýza.

    pts_xy            : [(x_mm, z_mm), ...] polygon (absolutní souřadnice)
    slices_for_circle : vrstvy pro kruhové průřezy (z slices_from_circle)
    walls             : [(b_mm, t_mm), ...] stěny pro přesný IT (volitelné)
    """

    def __init__(self, pts_xy=None, slices_for_circle=None, walls=None,
                 IT_override=None, bodies=None):
        self.valid = False
        self.pts = pts_xy
        self._sl_circ = slices_for_circle
        self._walls_input = walls
        self._IT_override = IT_override
        # bodies = list of (outer_pts_xy, [hole_pts_xy, ...]) v původních souř.;
        # None = legacy single polygon (přes pts_xy / slices_for_circle).
        self._bodies_orig = bodies
        self.bodies_c = None      # nastaví se v _compute (centroidální souř.)
        self._compute()

    # ─────────────────────────────────────────────────────────
    def _compute(self):
        if self._bodies_orig:                       # ── kompozit (více těles + díry) ──
            res = _composite_moments(self._bodies_orig)
            if res is None:
                return
            A, cx, cz, Iy, Iz, Iyz = res
            self.cx_raw = cx
            self.cz_raw = cz
        elif self.pts and len(self.pts) >= 3:
            A, cx, cz, Iy, Iz, Iyz = _poly_props(self.pts)
            self.cx_raw = cx
            self.cz_raw = cz
        elif self._sl_circ:
            sl = self._sl_circ
            A = Az = Ay = 0.0
            for zb, zt, yl, yr in sl:
                a = (zt-zb)*(yr-yl)
                A += a
                Az += a*(zb+zt)/2
                Ay += a*(yl+yr)/2
            if A < 1e-15:
                return
            cz_m = Az/A
            cx_m = Ay/A
            Iy = Iz = Iyz = 0.0
            for zb, zt, yl, yr in sl:
                h, w = zt-zb, yr-yl
                a = h*w
                zci = (zb+zt)/2 - cz_m
                yci = (yl+yr)/2 - cx_m
                Iy += w*h**3/12 + a*zci**2
                Iz += h*w**3/12 + a*yci**2
                Iyz += a*zci*yci
            A *= 1e6
            Iy *= 1e12
            Iz *= 1e12
            Iyz *= 1e12
            cz = cz_m*1e3
            cx = cx_m*1e3
            self.cx_raw = cx
            self.cz_raw = cz
        else:
            self.cx_raw = 0.0
            self.cz_raw = 0.0
            return

        if A < 1e-9:
            return
        self.A = A
        self.cx = cx
        self.cz = cz
        self.Iy = Iy
        self.Iz = Iz
        self.Iyz = Iyz

        # rozsah souřadnic (pro z_top/z_bot/y_left/y_right)
        if self._bodies_orig:
            allp = [p for outer, _ in self._bodies_orig for p in outer]
            xs = [p[0] for p in allp]
            zs = [p[1] for p in allp]
            # pro legacy zobrazení použij obrys prvního tělesa
            self.pts = list(self._bodies_orig[0][0])
        else:
            zs = [p[1] for p in self.pts] if self.pts else []
            xs = [p[0] for p in self.pts] if self.pts else []
            if self._sl_circ and not self.pts:
                zs = [s[0]*1e3 for s in self._sl_circ] + [s[1]*1e3 for s in self._sl_circ]
                xs = [s[2]*1e3 for s in self._sl_circ] + [s[3]*1e3 for s in self._sl_circ]
        self.z_top = max(zs) - cz
        self.z_bot = min(zs) - cz
        self.y_right = max(xs) - cx
        self.y_left = min(xs) - cx
        self.h = self.z_top - self.z_bot
        self.b = self.y_right - self.y_left
        self.zc = cz - min(zs)            # těžiště od dna

        self.Wy_top = Iy/abs(self.z_top) if abs(self.z_top) > 1e-9 else 0
        self.Wy_bot = Iy/abs(self.z_bot) if abs(self.z_bot) > 1e-9 else 0
        self.Wz_r = Iz/abs(self.y_right) if abs(self.y_right) > 1e-9 else 0
        self.iy = math.sqrt(Iy/A)
        self.iz = math.sqrt(Iz/A)

        avg = (Iy+Iz)/2
        diff = math.sqrt(((Iy-Iz)/2)**2 + Iyz**2)
        self.I1 = avg + diff
        self.I2 = avg - diff
        self.alpha = 0.5*math.degrees(math.atan2(-2*Iyz, Iy-Iz))

        if self.pts:
            self._pts_c = [(x-cx, z-cz) for x, z in self.pts]
        else:
            self._pts_c = None

        # centroidální souřadnice všech těles (pro scanline kompozitu)
        if self._bodies_orig:
            self.bodies_c = []
            for outer, holes in self._bodies_orig:
                outer_c = [(p[0]-cx, p[1]-cz) for p in outer]
                holes_c = [[(p[0]-cx, p[1]-cz) for p in h] for h in holes]
                self.bodies_c.append((outer_c, holes_c))

        self.z_SC = self._approx_SC()
        self.y_SC = 0.0
        self.IT = self._compute_IT()
        self.Iw = self._approx_Iw()

        e_top = abs(self.z_SC - self.z_top)
        e_bot = abs(self.z_SC - self.z_bot)
        omega_max = max(e_top, e_bot) * (self.b / 2.0) if self.b > 0 else 1.0
        self.Wk = self.Iw / omega_max if (omega_max > 1e-9 and self.Iw > 0) else 0.0

        self.Ip = self.Iy + self.Iz
        self.ip = math.sqrt(self.Ip / self.A) if self.A > 0 else 0.0

        # moduly průřezu Wx = Ix/ix (přes poloměr setrvačnosti) – pro ruční kontrolu
        self.Wb_y = (self.Iy / self.iy) if self.iy > 1e-12 else 0.0   # ohyb k ose y
        self.Wb_z = (self.Iz / self.iz) if self.iz > 1e-12 else 0.0   # ohyb k ose z
        # modul v krutu: it = √(IT/A) → Wt = IT/it = √(IT·A)
        self.it = math.sqrt(self.IT / self.A) if (self.A > 0 and self.IT > 0) else 0.0
        self.Wb_t = (self.IT / self.it) if self.it > 1e-12 else 0.0
        r_max_sq = max(
            self.y_right**2 + self.z_top**2,
            self.y_right**2 + self.z_bot**2,
            abs(self.y_left)**2 + self.z_top**2,
            abs(self.y_left)**2 + self.z_bot**2,
        )
        r_max = math.sqrt(r_max_sq) if r_max_sq > 0 else 1.0
        self.Wp = self.Ip / r_max

        # Timoshenkův smykový součinitel (efektivní smyková plocha)
        self.kappa, self.Asz, self.Asy = self._shear_coeff()

        # Plastické charakteristiky (ohyb k ose y) – analyticky
        self.section_type = None
        self._compute_plastic()

        self.valid = True

    def _compute_plastic(self, n=400):
        """W_el,y, W_pl,y a tvarový součinitel plasticity α_pl = W_pl/W_el.
        PNA (plastická neutrální osa) = vodorovná čára dělící plochu na poloviny;
        W_pl = první statický moment obou polovin k PNA. Numericky přes width_at."""
        self.Wel_y = 0.0
        self.Wpl_y = 0.0
        self.alpha_pl = 1.0
        zmax = max(abs(self.z_top), abs(self.z_bot))
        if self.Iy <= 0 or zmax <= 1e-9:
            return
        self.Wel_y = self.Iy / zmax
        dz = (self.z_top - self.z_bot) / n
        # vzorkování ve středech buněk (přesné pro konstantní šířku)
        zs = self.z_bot + (np.arange(n) + 0.5) * dz
        w = np.array([max(self.width_at(float(z)), 0.0) for z in zs])
        dA = w * dz
        A = float(dA.sum())
        if A <= 1e-12:
            return
        # PNA: kde kumulativní plocha zdola dosáhne A/2
        cum = np.cumsum(dA)
        half = A / 2.0
        z_p = float(np.interp(half, cum, zs))
        # plastický modul = Σ w·|z − z_p|·dz
        self.Wpl_y = float((w * np.abs(zs - z_p) * dz).sum())
        if self.Wel_y > 1e-12:
            self.alpha_pl = max(1.0, self.Wpl_y / self.Wel_y)

    # ─────────────────────────────────────────────────────────
    def _shear_coeff(self):
        """Odhad κ a efektivní smykové plochy A_sz, A_sy.
        Pro tenkostěnné (jsou-li walls) odlišíme stojinu/pásnice; jinak 5/6."""
        if self._walls_input and len(self._walls_input) >= 1:
            # první stěna brána jako stojina (nese svislý smyk)
            b_web, t_web = self._walls_input[0]
            Asz = b_web * t_web
            Asy = max(self.A - Asz, self.A * 0.3)
            kappa = Asz / self.A if self.A > 0 else 5/6
            return kappa, Asz, Asy
        if self._sl_circ is not None:
            kappa = 0.9
            return kappa, self.A*kappa, self.A*kappa
        kappa = 5/6
        return kappa, self.A*kappa, self.A*kappa

    # ─── IT (St. Venant) ─────────────────────────────────────
    def _compute_IT(self):
        if self._IT_override is not None:
            return self._IT_override
        if self._walls_input:
            IT = 0.0
            for b_, t_ in self._walls_input:
                if b_ > 0 and t_ > 0:
                    IT += (1.0/3.0) * b_ * t_**3
            return IT

        # kompozit: J ≈ Σ J_tělesa (inženýrský přístup pro otevřené tenkostěnné/
        # disjunktní průřezy; Bredt-Batho cooperace tělesy zde NENÍ uvažována).
        if self.bodies_c:
            IT = 0.0
            for outer, _holes in self.bodies_c:
                IT += self._IT_polygon(outer)
            return IT

        if not self.pts:
            if not self._sl_circ:
                return 0.0
            all_r = [max(abs(yl), abs(yr)) * 1e3 for _, _, yl, yr in self._sl_circ]
            r_out = max(all_r) if all_r else 0.0
            r_in = 0.0
            for zb, zt, yl, yr in self._sl_circ:
                zm = (zb+zt)/2 * 1e3
                if abs(zm) < r_out * 0.15:
                    w = (yr-yl)*1e3
                    if w < r_out * 1.5:
                        r_in = max(r_in, abs(yl)*1e3)
            return math.pi/2.0 * (r_out**4 - r_in**4)

        if not getattr(self, "_pts_c", None):
            return 0.0
        return self._IT_polygon(self._pts_c)

    def _IT_polygon(self, pts):
        """IT polygonálního tělesa – auto-detekce stěn (otevřený tenkostěnný)
        nebo fallback na masivní obdélníkový vztah."""
        n = len(pts)
        EPS = 0.05

        def intersections_h(z_cut):
            xs = []
            for i in range(n):
                xi, zi = pts[i]
                xj, zj = pts[(i+1) % n]
                if min(zi, zj) < z_cut <= max(zi, zj) and abs(zj-zi) > 1e-9:
                    t = (z_cut-zi)/(zj-zi)
                    xs.append(xi+t*(xj-xi))
            return sorted(xs)

        horiz = {}
        vert = {}
        for i in range(n):
            xi, zi = pts[i]
            xj, zj = pts[(i+1) % n]
            if abs(zj-zi) < EPS and abs(xj-xi) > 0.5:
                z_key = round((zi+zj)/2, 2)
                horiz.setdefault(z_key, []).append((min(xi, xj), max(xi, xj)))
            elif abs(xj-xi) < EPS and abs(zj-zi) > 0.5:
                x_key = round((xi+xj)/2, 2)
                vert.setdefault(x_key, []).append((min(zi, zj), max(zi, zj)))

        if not horiz and not vert:
            return self._IT_solid_scanline(pts)

        IT = 0.0
        z_levels = sorted(horiz.keys())
        x_levels = sorted(vert.keys())

        used_z = set()
        for z1 in z_levels:
            if z1 in used_z:
                continue
            b1 = sum(e-s for s, e in horiz[z1])
            best = None
            for z2 in z_levels:
                if z2 == z1 or z2 in used_z:
                    continue
                b2 = sum(e-s for s, e in horiz[z2])
                t = abs(z2-z1)
                b_avg = (b1+b2)/2
                if t > 1e-9 and b_avg/t > 3.0 and min(b1, b2)/max(b1, b2) > 0.25:
                    if best is None or t < best[0]:
                        best = (t, z2, b_avg)
            if best is not None:
                t_fl, z2, b_avg = best
                IT += (1.0/3.0) * b_avg * t_fl**3
                used_z.add(z1)
                used_z.add(z2)

        used_x = set()
        for x1 in x_levels:
            if x1 in used_x:
                continue
            h1 = sum(e-s for s, e in vert[x1])
            best = None
            for x2 in x_levels:
                if x2 == x1 or x2 in used_x:
                    continue
                h2 = sum(e-s for s, e in vert[x2])
                t = abs(x2-x1)
                h_avg = (h1+h2)/2
                if t > 1e-9 and h_avg/t > 3.0 and min(h1, h2)/max(h1, h2) > 0.25:
                    if best is None or t < best[0]:
                        best = (t, x2, h_avg)
            if best is not None:
                t_web, x2, h_avg = best
                IT += (1.0/3.0) * h_avg * t_web**3
                used_x.add(x1)
                used_x.add(x2)

        if IT > 1e-9:
            return IT
        return self._IT_solid_scanline(pts)

    def _IT_solid_scanline(self, pts):
        """IT masivního obdélníkového průřezu (Timoshenko korekce)."""
        all_z = [p[1] for p in pts]
        all_x = [p[0] for p in pts]
        h_total = max(all_z) - min(all_z)
        b_total = max(all_x) - min(all_x)
        a_ = max(h_total, b_total)
        t_ = min(h_total, b_total)
        if t_ < 1e-3:
            return 0.0
        bt = a_ / t_
        c1 = 1.0/3.0 * (1.0 - 0.630/bt + 0.052/bt**5)
        return c1 * t_ * a_**3

    # ─── warping Iω (Vlasov) ─────────────────────────────────
    def _approx_Iw(self):
        # Pro kompozit (více disjunktních těles) je Iω věcí FEM (fáze 2);
        # otevřený tenkostěnný odhad zde nedává smysl bez topologie.
        if self.bodies_c:
            return 0.0
        if not self.pts:
            return 0.0
        yS = self.y_SC
        zS = self.z_SC
        pts = self._pts_c
        if not pts or len(pts) < 3:
            return 0.0
        n = len(pts)

        omega = [0.0]*n
        for i in range(n):
            xi, zi = pts[i]
            xj, zj = pts[(i+1) % n]
            dx = xj-xi
            dz = zj-zi
            xm = xi-yS
            zm = zi-zS
            L = math.hypot(dx, dz)
            rho = (xm*dz - zm*dx)/L if L > 1e-9 else 0.0
            if i + 1 < n:
                omega[i+1] = omega[i] + rho*L

        omega_avg = 0.0
        total_A = 0.0
        for i in range(n):
            xi, zi = pts[i]
            xj, zj = pts[(i+1) % n]
            L = math.hypot(xj-xi, zj-zi)
            zm = (zi+zj)/2
            t_here = self.t_wall_at(zm) if hasattr(self, "t_wall_at") else max(self.b, self.h)/20
            A_seg = L*t_here
            omega_m = (omega[i] + omega[(i+1) % n])/2
            omega_avg += omega_m*A_seg
            total_A += A_seg
        if total_A > 0:
            omega_avg /= total_A
        omega = [o - omega_avg for o in omega]

        Iw = 0.0
        for i in range(n):
            xi, zi = pts[i]
            xj, zj = pts[(i+1) % n]
            L = math.hypot(xj-xi, zj-zi)
            zm = (zi+zj)/2
            t_here = self.t_wall_at(zm) if hasattr(self, "t_wall_at") else max(self.b, self.h)/20
            omega_m = (omega[i] + omega[(i+1) % n])/2
            Iw += t_here*L*omega_m**2
        return Iw

    def _approx_SC(self):
        # Kompozit: bez topologie střednic odhad nedělá smysl; nech na 0
        # (symetrické případy => střed smyku = těžiště).
        if self.bodies_c:
            return 0.0
        if not self.pts:
            return 0.0
        Iz_z = Iz_s = 0.0
        n = len(self.pts)
        for i in range(n):
            xi, zi = self.pts[i]
            xj, zj = self.pts[(i+1) % n]
            L = math.hypot(xj-xi, zj-zi)
            xci = (xi+xj)/2 - self.cx
            zci = (zi+zj)/2 - self.cz
            Iz_z += L*xci**2*zci
            Iz_s += L*xci**2
        return Iz_z/Iz_s if Iz_s > 0 else 0.0

    # ─── geometrické dotazy ──────────────────────────────────
    def width_at(self, z_mm):
        if self.bodies_c:
            return _width_at_z_composite(self.bodies_c, z_mm)
        if self._pts_c:
            return _poly_width_at(self._pts_c, z_mm)
        if self._sl_circ:
            z_m = z_mm / 1e3 + self.cz / 1e3
            w = sum(s[3]-s[2] for s in self._sl_circ if s[0] <= z_m < s[1]) * 1e3
            return w if w > 1e-15 else 0.0
        return 0.0

    def t_wall_at_y(self, y_mm):
        pts = self._pts_c
        if not pts:
            return 1e-15
        n = len(pts)
        zs = []
        for i in range(n):
            xi, zi = pts[i]
            xj, zj = pts[(i+1) % n]
            if min(xi, xj) < y_mm <= max(xi, xj) and abs(xj-xi) > 1e-9:
                t = (y_mm-xi)/(xj-xi)
                zs.append(zi+t*(zj-zi))
        zs.sort()
        if len(zs) < 2:
            return 1e-15
        t_min = 1e9
        for j in range(0, len(zs)-1, 2):
            h_v = zs[j+1]-zs[j]
            if h_v < 1e-3:
                continue
            zm = (zs[j]+zs[j+1])/2
            bz = self.width_at(zm)
            t_min = min(t_min, min(h_v, bz))
        return t_min if t_min < 1e9 else 1e-15

    def Q_Vy_at_y(self, y_mm):
        """Statický moment části vpravo od y_cut k ose z. Vrací mm³."""
        if self.bodies_c:
            return _Q_Vy_at_y_composite(self.bodies_c, y_mm)
        pts = self._pts_c
        if not pts:
            if self._sl_circ:
                Q = 0.0
                for zb, zt, yl, yr in self._sl_circ:
                    if yr*1e3 <= y_mm:
                        continue
                    w = (zt-zb)*1e3
                    y_lo = max(yl*1e3, y_mm)
                    y_hi = yr*1e3
                    y_ci = (y_lo+y_hi)/2
                    Q += w*(y_hi-y_lo)*y_ci
                return Q
            return 0.0
        n = len(pts)
        Q = 0.0
        N_sub = 500
        all_y = [p[0] for p in pts]
        y_hi_g = max(all_y)
        y_lo_g = min(all_y)
        if y_mm >= y_hi_g:
            return 0.0
        y_start = max(y_mm, y_lo_g)
        dy = (y_hi_g - y_start) / N_sub
        for k in range(N_sub):
            ym = y_start + (k+0.5)*dy
            zs = []
            for i in range(n):
                xi, zi = pts[i]
                xj, zj = pts[(i+1) % n]
                if min(xi, xj) < ym <= max(xi, xj) and abs(xj-xi) > 1e-9:
                    t2 = (ym-xi)/(xj-xi)
                    zs.append(zi+t2*(zj-zi))
            zs.sort()
            for j in range(0, len(zs)-1, 2):
                h_v = zs[j+1]-zs[j]
                if h_v > 1e-3:
                    Q += h_v * ym * dy
        return Q

    def height_at_y(self, y_mm):
        if self.bodies_c:
            return _height_at_y_composite(self.bodies_c, y_mm) or 1e-15
        pts = self._pts_c
        if not pts:
            if self._sl_circ:
                y_m = y_mm/1e3
                h = sum((zt-zb)*1e3 for zb, zt, yl, yr in self._sl_circ if yl <= y_m <= yr)
                return h if h > 1e-15 else 1e-15
            return 1e-15
        n = len(pts)
        zs = []
        for i in range(n):
            xi, zi = pts[i]
            xj, zj = pts[(i+1) % n]
            if min(xi, xj) < y_mm <= max(xi, xj) and abs(xj-xi) > 1e-9:
                t = (y_mm-xi)/(xj-xi)
                zs.append(zi+t*(zj-zi))
        zs.sort()
        if len(zs) < 2:
            return 1e-15
        return sum(zs[j+1]-zs[j] for j in range(0, len(zs)-1, 2))

    def Q_at(self, z_mm):
        """Statický moment části NAD z_mm [mm od těžiště]. Vrací mm³."""
        if self.bodies_c:
            return _Q_at_z_composite(self.bodies_c, z_mm, self.z_top)
        if self._pts_c:
            return _poly_Q_scanline(self._pts_c, z_mm)
        if self._sl_circ:
            zc_m = self.cz / 1e3
            z_m = z_mm / 1e3 + zc_m
            Q = 0.0
            for zb, zt, yl, yr in self._sl_circ:
                if zt <= z_m:
                    continue
                w = (yr - yl) * 1e3
                if zb >= z_m:
                    Q += w * (zt-zb)*1e3 * ((zb+zt)/2*1e3 - self.cz)
                else:
                    ha = (zt - z_m) * 1e3
                    Q += w * ha * (z_mm + ha/2)
            return Q
        return 0.0

    def t_wall_at(self, z_mm, n_x=6):
        """Tloušťka stěny v úrovni z [mm od těžiště]."""
        if self.bodies_c:
            return _t_wall_at_composite(self.bodies_c, z_mm, n_x=n_x)
        if self._sl_circ:
            z_m = z_mm / 1e3 + self.cz / 1e3
            t = None
            for zb, zt, yl, yr in self._sl_circ:
                if zb <= z_m < zt:
                    ti = min((zt-zb)*1e3, (yr-yl)*1e3)
                    if t is None or ti < t:
                        t = ti
            return t if t else 1e-15
        pts = self._pts_c
        if not pts:
            return 1e-15
        n = len(pts)
        xs_h = []
        for i in range(n):
            xi, zi = pts[i]
            xj, zj = pts[(i+1) % n]
            if min(zi, zj) < z_mm <= max(zi, zj) and abs(zj-zi) > 1e-9:
                t2 = (z_mm-zi)/(zj-zi)
                xs_h.append(xi + t2*(xj-xi))
        xs_h.sort()
        if len(xs_h) < 2:
            return 1e-15
        t_min = 1e9
        for j in range(0, len(xs_h)-1, 2):
            x_lo, x_hi = xs_h[j], xs_h[j+1]
            w = x_hi - x_lo
            if w < 1e-3:
                continue
            for k in range(n_x):
                x_s = x_lo + w*(k+0.5)/n_x
                zs_v = []
                for i in range(n):
                    xi, zi = pts[i]
                    xj, zj = pts[(i+1) % n]
                    if min(xi, xj) < x_s <= max(xi, xj) and abs(xj-xi) > 1e-9:
                        t3 = (x_s-xi)/(xj-xi)
                        zs_v.append(zi + t3*(zj-zi))
                zs_v.sort()
                for m in range(0, len(zs_v)-1, 2):
                    h_v = zs_v[m+1] - zs_v[m]
                    if h_v > 1e-3:
                        t_min = min(t_min, min(w, h_v))
        return t_min if t_min < 1e9 else 1e-15

    # ─── napjatost ───────────────────────────────────────────
    def stress(self, forces, z_mm, y_mm=0.0):
        """Napětí v bodě (y_mm, z_mm) [mm od těžiště]. Síly N, momenty N·m."""
        Fx = forces["Fx"]; Fy = forces["Fy"]; Fz = forces["Fz"]
        My = forces["My"]; Mz = forces["Mz"]; Mk = forces["Mk"]
        z = z_mm/1e3
        y = y_mm/1e3
        Iy = self.Iy/1e12; Iz = self.Iz/1e12; A = self.A/1e6

        bz_check = self.width_at(z_mm)
        if bz_check < 1e-10:
            nan = float("nan")
            return dict(sigma=nan, tauVz=nan, tauVy=0.0, tauT=nan,
                        tau=nan, mises=nan, Q=0.0, hollow=True)

        sigma = Fx/A + My*z/Iy + Mz*y/Iz

        Q = self.Q_at(z_mm)/1e9
        bz = self.width_at(z_mm)/1e3
        tauVz = Fz*Q/(Iy*bz) if bz > 1e-15 else 0.0

        Qy = self.Q_Vy_at_y(y_mm)/1e9
        hy = self.height_at_y(y_mm)/1e3
        tauVy = Fy*Qy/(Iz*hy) if hy > 1e-15 else 0.0

        IT = self.IT/1e12
        tw = self.t_wall_at(z_mm)/1e3
        tauT = Mk*tw/IT if IT > 1e-30 else 0.0

        tau = tauVz + tauVy + tauT
        mises = math.sqrt(sigma**2 + 3*tau**2)
        return dict(sigma=sigma, tauVz=tauVz, tauVy=tauVy, tauT=tauT,
                    tau=tau, mises=mises, Q=Q)

    def profile(self, forces, N=300):
        """Průběh napětí po výšce (svislý diagram). Napětí v MPa (Pa→MPa převede volající)."""
        Fy = forces.get("Fy", 0)
        zs = np.linspace(self.z_bot*0.9999, self.z_top*0.9999, N)
        result = []
        for z in zs:
            if self.width_at(z) < 1e-10:
                result.append({"z": z, "sigma": float("nan"),
                               "tauVz": float("nan"), "tauVy": 0.0,
                               "tauT": float("nan"), "tau": float("nan"),
                               "mises": float("nan"), "Q": 0.0, "hollow": True})
                continue
            y_ext = self._y_extreme_at_z(z)
            s = self.stress(forces, z, y_mm=y_ext)
            if s.get("hollow"):
                s["z"] = z
                result.append(s)
                continue
            if abs(Fy) > 1e-15:
                tau_Vy_max = self._tau_Vy_max_at_z(Fy, z)
                s = dict(s, tauVy=tau_Vy_max,
                         tau=s["tauVz"]+tau_Vy_max+s["tauT"],
                         mises=math.sqrt(s["sigma"]**2 +
                               3*(s["tauVz"]+tau_Vy_max+s["tauT"])**2))
            s["z"] = z
            result.append(s)
        return result

    def _y_extreme_at_z(self, z_mm):
        if self.bodies_c:
            return _y_extreme_at_z_composite(self.bodies_c, z_mm)
        pts = self._pts_c
        if not pts:
            return 0.0
        n = len(pts)
        xs = []
        for i in range(n):
            xi, zi = pts[i]
            xj, zj = pts[(i+1) % n]
            if min(zi, zj) < z_mm <= max(zi, zj) and abs(zj-zi) > 1e-9:
                t = (z_mm-zi)/(zj-zi)
                xs.append(xi+t*(xj-xi))
        if not xs:
            return 0.0
        xs.sort()
        return max([xs[0], xs[-1]], key=abs)

    def _tau_Vy_max_at_z(self, Fy, z_mm, n_samp=8):
        if abs(Fy) < 1e-15:
            return 0.0
        if self.bodies_c:
            xs = []
            for outer, holes in self.bodies_c:
                xs.extend(_scan_intersections(outer, z_mm))
                for h in holes:
                    xs.extend(_scan_intersections(h, z_mm))
            xs.sort()
        else:
            pts = self._pts_c
            if not pts:
                return 0.0
            n = len(pts)
            xs = []
            for i in range(n):
                xi, zi = pts[i]
                xj, zj = pts[(i+1) % n]
                if min(zi, zj) < z_mm <= max(zi, zj) and abs(zj-zi) > 1e-9:
                    t = (z_mm-zi)/(zj-zi)
                    xs.append(xi+t*(xj-xi))
            xs.sort()
        if len(xs) < 2:
            return 0.0
        Iz = self.Iz/1e12
        best = 0.0
        for j in range(0, len(xs)-1, 2):
            for k in range(n_samp):
                y = xs[j] + (xs[j+1]-xs[j])*(k+0.5)/n_samp
                Qy = self.Q_Vy_at_y(y)/1e9
                hy = self.height_at_y(y)/1e3
                if hy > 1e-15:
                    tau = abs(Fy*Qy/(Iz*hy))
                    if tau > best:
                        best = tau
        return best

    def _z_extreme_at_y(self, y_mm):
        if self.bodies_c:
            zs = []
            for outer, _ in self.bodies_c:
                zs.extend(_scan_intersections_v(outer, y_mm))
            if not zs:
                return 0.0
            zs.sort()
            return max([zs[0], zs[-1]], key=abs)
        pts = self._pts_c
        if not pts:
            return 0.0
        n = len(pts)
        zs = []
        for i in range(n):
            xi, zi = pts[i]
            xj, zj = pts[(i+1) % n]
            if min(xi, xj) < y_mm <= max(xi, xj) and abs(xj-xi) > 1e-9:
                t = (y_mm-xi)/(xj-xi)
                zs.append(zi+t*(zj-zi))
        if not zs:
            return 0.0
        zs.sort()
        return max([zs[0], zs[-1]], key=abs)


# ═══════════════════════════════════════════════════════════
#  GENERÁTORY PROFILŮ  →  (pts_xy, walls, slices, IT_override)
# ═══════════════════════════════════════════════════════════

def _segs_to_pts(pts):
    return [(float(x), float(z)) for x, z in pts]


def make_I(h, b_top, b_bot, tw, tf_top, tf_bot):
    hw = h - tf_top - tf_bot
    pts = [
        (-b_bot/2, -h/2), (b_bot/2, -h/2),
        (b_bot/2, -h/2 + tf_bot), (tw/2, -h/2 + tf_bot),
        (tw/2, h/2 - tf_top), (b_top/2, h/2 - tf_top),
        (b_top/2, h/2), (-b_top/2, h/2),
        (-b_top/2, h/2 - tf_top), (-tw/2, h/2 - tf_top),
        (-tw/2, -h/2 + tf_bot), (-b_bot/2, -h/2 + tf_bot),
    ]
    return _segs_to_pts(pts), [(hw, tw), (b_top, tf_top), (b_bot, tf_bot)], None, None


def make_rect(w, h):
    pts = [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]
    return _segs_to_pts(pts), None, None, None


def make_T(h, b, tw, tf):
    hw = h - tf
    pts = [(-b/2, h/2), (b/2, h/2), (b/2, h/2-tf), (tw/2, h/2-tf),
           (tw/2, -h/2), (-tw/2, -h/2), (-tw/2, h/2-tf), (-b/2, h/2-tf)]
    return _segs_to_pts(pts), [(hw, tw), (b, tf)], None, None


def make_L(h, b, t):
    pts = [(-b/2, -h/2), (b/2, -h/2), (b/2, -h/2+t),
           (-b/2+t, -h/2+t), (-b/2+t, h/2), (-b/2, h/2)]
    return _segs_to_pts(pts), [(h-t, t), (b, t)], None, None


def make_U(h, b, t):
    pts = [(-b/2, -h/2), (b/2, -h/2), (b/2, h/2), (b/2-t, h/2),
           (b/2-t, -h/2+t), (-b/2+t, -h/2+t), (-b/2+t, h/2), (-b/2, h/2)]
    return _segs_to_pts(pts), [(h, t), (b-t, t), (b-t, t)], None, None


def make_box(h, b, t):
    """Dutý obdélníkový průřez (RHS). IT dle Bredt-Batho (uzavřený)."""
    outer = [(-b/2, -h/2), (b/2, -h/2), (b/2, h/2), (-b/2, h/2)]
    hi, bi = h-2*t, b-2*t
    inner = [(-bi/2, -hi/2), (-bi/2, hi/2), (bi/2, hi/2), (bi/2, -hi/2)]
    pts = _segs_to_pts(outer + inner)
    Am = (h-t)*(b-t)
    IT = 4*Am**2 / (2*(h-t)/t + 2*(b-t)/t)
    return pts, None, None, IT


def make_circle(D):
    r = D/2
    return None, None, slices_from_circle(0, 0, r, 0.0), None


def make_tube(Do, t):
    r_out = Do/2
    r_in = r_out - t
    IT = math.pi/2.0 * (r_out**4 - r_in**4)   # mezikruží – analyticky
    return None, None, slices_from_circle(0, 0, r_out, r_in), IT


# ═══════════════════════════════════════════════════════════
#  BUILDER:  CrossSectionDef  →  CrossSection
# ═══════════════════════════════════════════════════════════

# Tabulkové hodnoty součinitele plasticity (ohyb k silné ose y) dle rešerše
ALPHA_PL_TABLE = {
    "rectangle": 1.50,
    "circle": 1.698,        # 16/(3π)
    "tube": 1.273,          # 4/π (tenkostěnná trubka)
    "box": 1.15,            # tenkostěnný box (orientačně)
    "i_section": 1.14,      # válcovaný I k silné ose
    "t_section": 1.70,      # T-profil (silně nesymetrický)
    "c_section": 1.17,      # U/C k silné ose
    "u_section": 1.17,
    "l_section": 1.50,      # orientačně
}


def build_section(sdef, fem: bool = True) -> CrossSection:
    """Sestaví CrossSection z definice (model.CrossSectionDef).

    fem=False – pro polygon přeskočí FEM Saint-Venant solver (rychlý živý náhled).
                IT, Iω, střed smyku zůstanou na scanline odhadech.
    """
    t = sdef.type
    p = sdef.params or {}

    def gv(key, default):
        try:
            return float(p.get(key, default))
        except (TypeError, ValueError):
            return float(default)

    if t == "rectangle":
        pts, walls, sl, IT = make_rect(gv("b", 100), gv("h", 200))
    elif t == "box":
        # Dutý obdélník (RHS) = jedno těleso s pravoúhlou dírou. Dřívější zápis
        # jako jeden polygon (vnější+vnitřní body za sebou) vedl k rozpojenému
        # obrysu; korektně je to outer + hole. IT dle Bredt-Batho (uzavřený).
        H = gv("H", 200); B = gv("B", 100); tw = gv("tw", 6)
        outer = [(-B/2, -H/2), (B/2, -H/2), (B/2, H/2), (-B/2, H/2)]
        bi, hi = B - 2*tw, H - 2*tw
        holes = []
        if bi > 0 and hi > 0:
            holes = [[(-bi/2, -hi/2), (bi/2, -hi/2), (bi/2, hi/2), (-bi/2, hi/2)]]
            Am = (H - tw) * (B - tw)
            IT = 4 * Am**2 / (2*(H - tw)/tw + 2*(B - tw)/tw)
        else:
            IT = None   # degenerovaný (tw ≥ rozměr) → ponech výpočet na jádře
        cs = CrossSection(bodies=[(outer, holes)], IT_override=IT)
        cs.section_type = "box"
        return cs
    elif t == "circle":
        pts, walls, sl, IT = make_circle(gv("D", 100))
    elif t == "tube":
        pts, walls, sl, IT = make_tube(gv("Do", 100), gv("t", 5))
    elif t == "i_section":
        pts, walls, sl, IT = make_I(gv("h", 200), gv("bf1", 100), gv("bf2", 100),
                                    gv("tw", 6), gv("tf1", 10), gv("tf2", 10))
    elif t == "t_section":
        pts, walls, sl, IT = make_T(gv("h", 200), gv("b", 120), gv("tw", 8), gv("tf", 12))
    elif t == "l_section":
        pts, walls, sl, IT = make_L(gv("h", 100), gv("b", 100), gv("t", 10))
    elif t in ("c_section", "u_section"):
        pts, walls, sl, IT = make_U(gv("h", 200), gv("b", 80), gv("t", 8))
    elif t == "direct":
        # průřez zadaný přímo momentem setrvačnosti Iy (import .nos / EI model);
        # geometrie se syntetizuje jako čtverec se shodným Iy (h⁴/12 = Iy)
        Iy = max(gv("Iy", 1000.0), 1e-9)
        h = (12.0 * Iy) ** 0.25
        pts, walls, sl, IT = make_rect(h, h)
    elif t == "polygon":
        # nový kompozitní zápis přes `bodies` (více těles + díry)
        bodies = sdef.bodies
        if bodies:
            bodies_pts = []
            for b in bodies:
                pts = (b.points if hasattr(b, "points") else b.get("points", []))
                holes_src = (b.holes if hasattr(b, "holes") else b.get("holes", []))
                outer = [(float(p["y"]), float(p["z"])) for p in (pts or [])]
                holes = [[(float(p["y"]), float(p["z"])) for p in h]
                         for h in (holes_src or []) if len(h) >= 3]
                if len(outer) >= 3:
                    bodies_pts.append((outer, holes))
            if not bodies_pts:
                raise ValueError("Kompozitní průřez nemá žádné platné těleso.")
            # Pro jedno těleso (s libovolnými dírami) můžeme spustit FEM jádro
            # přes legacy single-polygon API (přesné IT/Iω/střed smyku/smyk. plochy).
            if len(bodies_pts) == 1:
                outer, holes = bodies_pts[0]
                cs = CrossSection(bodies=bodies_pts)
                if fem:
                    _apply_fem_properties(cs, outer, holes)
                else:
                    cs.fem_used = False
            else:
                # multi-body FEM: per-body Saint-Venant + paralelní osy
                cs = CrossSection(bodies=bodies_pts)
                if fem:
                    _apply_fem_composite(cs, bodies_pts)
                else:
                    cs.fem_used = False
            cs.section_type = "polygon"
            return cs
        # legacy single polygon (zpětná kompat. pro starší projekty bez bodies)
        ppts = sdef.polygon_points or []
        pts = [(float(pt["y"]), float(pt["z"])) for pt in ppts]
        if len(pts) < 3:
            raise ValueError("Vlastní průřez potřebuje alespoň 3 body.")
        holes = [[(float(p["y"]), float(p["z"])) for p in h]
                 for h in (sdef.polygon_holes or []) if len(h) >= 3]
        cs = CrossSection(pts_xy=pts)
        if fem:
            _apply_fem_properties(cs, pts, holes)   # přesné IT, Iw, střed smyku, smyk. plochy
        else:
            cs.fem_used = False
        cs.section_type = "polygon"
        return cs
    else:
        raise ValueError(f"Neznámý typ průřezu: {t}")

    cs = CrossSection(pts_xy=pts, slices_for_circle=sl, walls=walls, IT_override=IT)
    cs.section_type = t
    # poloměry pro čisté vykreslení obrysu kruhu / trubky v náhledu
    if t == "circle":
        cs._circle_r_out = gv("D", 100) / 2.0
        cs._circle_r_in = 0.0
    elif t == "tube":
        ro = gv("Do", 100) / 2.0
        cs._circle_r_out = ro
        cs._circle_r_in = max(0.0, ro - gv("t", 5))
    return cs


def _apply_fem_properties(cs: CrossSection, outer, holes=None):
    """Přepíše IT, Iw, střed smyku a smykové plochy přesnými FEM hodnotami
    (Saint-Venant solver z _fem). A/Iy/Iz ponecháme z Greenovy věty
    (přesné a konzistentní s geometrickými dotazy). Při chybě/chybějícím
    scipy zůstanou scanline odhady."""
    if not cs.valid:
        return
    try:
        from . import _fem
    except Exception:
        cs.fem_used = False
        return
    try:
        r = _fem.analyze_section(outer, holes=holes or None, element_order="T6")
    except Exception:
        cs.fem_used = False
        return
    cs.IT = float(r["J"])
    cs.Iw = float(r["Iw"])
    cs.z_SC = float(r["z_sc"])
    cs.y_SC = float(r["y_sc"])
    # U průřezů s dírami scanline geometrie plochu neodečítá → převezmi
    # i A/I z FEM, aby beam solver a charakteristiky byly správné.
    if holes:
        cs.A = float(r["A"])
        cs.Iy = float(r["Ixx_c"])
        cs.Iz = float(r["Iyy_c"])
        cs.Iyz = float(r["Ixy_c"])
        cs.iy = (cs.Iy / cs.A) ** 0.5 if cs.A > 0 else 0.0
        cs.iz = (cs.Iz / cs.A) ** 0.5 if cs.A > 0 else 0.0
        cs.Wy_top = cs.Iy / abs(cs.z_top) if abs(cs.z_top) > 1e-9 else 0
        cs.Wy_bot = cs.Iy / abs(cs.z_bot) if abs(cs.z_bot) > 1e-9 else 0
        cs.Ip = cs.Iy + cs.Iz
    A_sz = float(r.get("A_sz", 0.0))
    A_sy = float(r.get("A_sy", 0.0))
    if A_sz > 0:
        cs.Asz = A_sz
        cs.kappa = A_sz / cs.A if cs.A > 0 else cs.kappa
    if A_sy > 0:
        cs.Asy = A_sy
    # warpingový modul s aktualizovaným Iw
    e_top = abs(cs.z_SC - cs.z_top)
    e_bot = abs(cs.z_SC - cs.z_bot)
    omega_max = max(e_top, e_bot) * (cs.b / 2.0) if cs.b > 0 else 1.0
    cs.Wk = cs.Iw / omega_max if (omega_max > 1e-9 and cs.Iw > 0) else 0.0
    cs.fem_used = True


def _apply_fem_composite(cs: CrossSection, bodies_pts):
    """Aplikuje multi-body FEM (per-body Saint-Venant + paralelní osy) na cs.
    Při chybě / nedostupném scipy nechá scanline odhady."""
    if not cs.valid:
        return
    try:
        from . import _fem
    except Exception:
        cs.fem_used = False
        return
    try:
        r = _fem.analyze_composite_section(bodies_pts, element_order="T6")
    except Exception:
        cs.fem_used = False
        return
    # geometrii (A, centroid, Ixx, Iyy, Ixy) máme přesně přes Greenovu větu;
    # z FEM přejímáme zejména torzi, warping, střed smyku a smykové plochy.
    cs.IT = float(r["J"])
    cs.Iw = float(r["Iw"])
    cs.z_SC = float(r["z_sc"])
    cs.y_SC = float(r["y_sc"])
    A_sz = float(r.get("A_sz", 0.0))
    A_sy = float(r.get("A_sy", 0.0))
    if A_sz > 0:
        cs.Asz = A_sz
        cs.kappa = A_sz / cs.A if cs.A > 0 else cs.kappa
    if A_sy > 0:
        cs.Asy = A_sy
    # warpingový modul (přibližně)
    e_top = abs(cs.z_SC - cs.z_top)
    e_bot = abs(cs.z_SC - cs.z_bot)
    omega_max = max(e_top, e_bot) * (cs.b / 2.0) if cs.b > 0 else 1.0
    cs.Wk = cs.Iw / omega_max if (omega_max > 1e-9 and cs.Iw > 0) else 0.0
    # přepočti moduly průřezu odpovídající novému IT
    cs.it = math.sqrt(cs.IT / cs.A) if (cs.A > 0 and cs.IT > 0) else 0.0
    cs.Wb_t = (cs.IT / cs.it) if cs.it > 1e-12 else 0.0
    cs.fem_used = True
