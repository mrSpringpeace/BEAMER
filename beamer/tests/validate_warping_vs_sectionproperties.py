"""Krizova validace Iw a stredu smyku pro OTEVRENE profily proti sectionproperties.

Porovnava tri cesty:
  A) BEAMER parametricky (analyticky _approx_Iw + analyticky SC)
  B) BEAMER FEM (prevod na polygon + analyze_section)
  C) sectionproperties (referencni)
"""
import sys
sys.path.insert(0, r"C:\Uziv\BEAMER\PYTHON")

CASES = [
    ("I-profil 200x100 t10/6", "i_section",
     {"h": 200, "tw": 6, "bf1": 100, "tf1": 10, "bf2": 100, "tf2": 10}),
    ("T-profil 200x120 t12/8", "t_section",
     {"h": 200, "b": 120, "tw": 8, "tf": 12}),
    ("L-profil 100x100 t10", "l_section", {"h": 100, "b": 100, "t": 10}),
    ("U-profil 200x80 t8", "c_section", {"h": 200, "b": 80, "t": 8}),
]


def beamer_paths(typ, params):
    from beamer.model import CrossSectionDef
    from beamer.section import build_section
    par = build_section(CrossSectionDef(type=typ, params=params), fem=False)
    pts = [{"y": float(y), "z": float(z)} for y, z in par._pts_c]
    fem = build_section(CrossSectionDef(type="polygon", polygon_points=pts), fem=True)
    return par, fem, [(float(y), float(z)) for y, z in par._pts_c]


def sp_reference(pts):
    from sectionproperties.pre.geometry import Geometry
    from sectionproperties.analysis.section import Section
    from shapely.geometry import Polygon
    geom = Geometry(Polygon(pts))
    geom = geom.create_mesh(mesh_sizes=[max(1.0, Polygon(pts).area / 400.0)])
    sec = Section(geom)
    sec.calculate_geometric_properties()
    sec.calculate_warping_properties()
    return {
        "A": sec.get_area(),
        "ixx": sec.get_ic()[0],
        "J": sec.get_j(),
        "Gamma": sec.get_gamma(),
        "sc": sec.get_sc(),      # (x_sc, y_sc) v jejich konvenci = (y, z) u nas
    }


def main():
    print(f"{'pripad':26s} {'velicina':8s} {'parametr.':>14s} {'BEAMER FEM':>14s} "
          f"{'sectionprop.':>14s}  {'par/ref':>9s} {'fem/ref':>9s}")
    print("-" * 106)
    for name, typ, params in CASES:
        try:
            par, fem, pts = beamer_paths(typ, params)
            ref = sp_reference(pts)
        except Exception as exc:
            print(f"{name:26s} CHYBA: {exc}")
            continue

        def row(lbl, pv, fv, rv):
            pr = f"{pv/rv:9.3f}" if rv else "        -"
            fr = f"{fv/rv:9.3f}" if rv else "        -"
            print(f"{name:26s} {lbl:8s} {pv:14.6g} {fv:14.6g} {rv:14.6g}  {pr} {fr}")

        row("A", par.A, fem.A, ref["A"])
        row("Iy", par.Iy, fem.Iy, ref["ixx"])
        row("IT", par.IT, fem.IT, ref["J"])
        row("Iw", par.Iw, fem.Iw, ref["Gamma"])
        # stred smyku: sectionproperties vraci (x_sc, y_sc) v globalnich souradnicich
        # geometrie; nase pts jsou uz centroidalni, takze to jsou primo offsety
        row("y_SC", par.y_SC, fem.y_SC, ref["sc"][0])
        row("z_SC", par.z_SC, fem.z_SC, ref["sc"][1])
        print()


if __name__ == "__main__":
    main()
