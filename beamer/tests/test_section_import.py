"""Regrese textového a IGES importu průřezu (etapa E / 1.41)."""
import pytest

from beamer.section import build_section
from beamer.section_import import (
    SectionImportError,
    _bspline_points,
    _entity_points,
    _transform_point,
    parse_iges,
    parse_section_text,
)


def test_text_import_outer_hole_and_decimal_comma():
    sdef = parse_section_text("""
        # vnější obrys v mm
        OUTER
        0,0 0,0
        100,0 0,0
        100,0 80,0
        0,0 80,0

        HOLE
        20;20
        20;60
        80;60
        80;20
    """, name="box_text")
    assert sdef.type == "polygon" and sdef.name == "box_text"
    assert len(sdef.bodies) == 1 and len(sdef.bodies[0].holes) == 1
    assert build_section(sdef, fem=False).A == pytest.approx(100*80-60*40)


def test_text_import_automatic_nesting_and_multiple_bodies():
    sdef = parse_section_text("""
        0 0
        20 0
        20 20
        0 20

        5 5
        5 15
        15 15
        15 5

        30 0
        40 0
        40 10
        30 10
    """)
    assert len(sdef.bodies) == 2
    assert sorted(len(body.holes) for body in sdef.bodies) == [0, 1]
    assert build_section(sdef, fem=False).A == pytest.approx(400.0)


def test_text_import_rejects_incomplete_ring():
    with pytest.raises(SectionImportError, match="alespoň tři"):
        parse_section_text("0 0\n10 0\n")


def test_text_import_rejects_self_intersection_and_external_hole():
    with pytest.raises(SectionImportError, match="sama kříží"):
        parse_section_text("0 0\n20 20\n0 20\n20 0")
    with pytest.raises(SectionImportError, match="neleží uvnitř"):
        parse_section_text("""
            OUTER
            0 0
            20 0
            20 20
            0 20
            HOLE
            30 30
            40 30
            40 40
            30 40
        """)


def _field(value):
    return f"{value:>8}"


def _iges_rectangle(width=100.0, height=50.0, unit_flag=2):
    """Minimální pevně sloupcovaný IGES se čtyřmi entitami Line (110)."""
    start = [(0.0, 0.0, 0.0), (width, 0.0, 0.0),
             (width, height, 0.0), (0.0, height, 0.0)]
    end = start[1:]+start[:1]
    lines = []
    global_values = ["1H,", "1H;", "4Htest", "4Htest", "", "", "32", "38",
                     "6", "308", "15", "4Htest", "1", str(unit_flag), "2HMM"]
    gdata = ",".join(global_values)+";"
    for seq, offset in enumerate(range(0, len(gdata), 72), 1):
        lines.append(gdata[offset:offset+72].ljust(72)+"G"+f"{seq:>7}")
    for idx, (p1, p2) in enumerate(zip(start, end)):
        seq = 2*idx+1
        d1 = _field(110)+_field(idx+1)+_field(0)*7
        d2 = (_field(110)+_field(0)+_field(0)+_field(1)+_field(0)+_field(0)
              +_field(0)+f"{'LINE':<8}"+_field(idx+1))
        lines.append(d1[:72].ljust(72)+"D"+f"{seq:>7}")
        lines.append(d2[:72].ljust(72)+"D"+f"{seq+1:>7}")
        pdata = "110,"+",".join(str(v) for v in (*p1, *p2))+";"
        lines.append(pdata[:64].ljust(64)+f"{seq:>8}"+"P"+f"{idx+1:>7}")
    return "\n".join(lines)


def test_iges_lines_join_to_closed_mm_rectangle():
    sdef = parse_iges(_iges_rectangle())
    assert len(sdef.bodies) == 1
    cs = build_section(sdef, fem=False)
    assert cs.A == pytest.approx(5000.0)
    assert cs.Iy == pytest.approx(100*50**3/12)


def test_iges_converts_inch_model_units_to_mm():
    cs = build_section(parse_iges(_iges_rectangle(2.0, 1.0, unit_flag=1)), fem=False)
    assert cs.A == pytest.approx(2.0*25.4**2)


def test_iges_rejects_open_curve_chain():
    text = "\n".join(_iges_rectangle().splitlines()[:-3])
    with pytest.raises(SectionImportError, match="uzavřenou"):
        parse_iges(text)


def test_iges_arc_bspline_and_transform_primitives():
    arc = _entity_points(100, ["100", "0", "0", "0", "1", "0", "0", "1"])
    assert arc[0] == pytest.approx((1.0, 0.0, 0.0))
    assert arc[-1] == pytest.approx((0.0, 1.0, 0.0))

    # K=1, M=1, kladné váhy: přímková B-spline od (0,0,0) do (10,0,0).
    spline = _bspline_points([
        1, 1, 0, 0, 1, 0,
        0, 0, 1, 1,
        1, 1,
        0, 0, 0, 10, 0, 0,
        0, 1,
    ])
    assert spline[0] == pytest.approx((0.0, 0.0, 0.0))
    assert spline[-1] == pytest.approx((10.0, 0.0, 0.0))

    matrix = [1, 0, 0, 10, 0, 1, 0, 20, 0, 0, 1, 30]
    assert _transform_point((1, 2, 3), matrix) == pytest.approx((11, 22, 33))


def test_section_dialog_exposes_text_and_iges_imports():
    from PySide6.QtWidgets import QApplication

    from beamer.gui.section_dialog import SectionEditorDialog
    from beamer.model import CrossSectionDef

    app = QApplication.instance() or QApplication([])
    dialog = SectionEditorDialog(CrossSectionDef())
    try:
        data = [dialog.cb.itemData(i) for i in range(dialog.cb.count())]
        assert "__import_text__" in data
        assert "__import_iges__" in data
    finally:
        dialog.close()
        app.processEvents()
