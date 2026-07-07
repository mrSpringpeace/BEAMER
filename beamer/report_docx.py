# -*- coding: utf-8 -*-
"""Výpočtový protokol (DOCX) – tisknutelný dokument pro průkaz.

Zrcadlí textový protokol (`report.build_report`), ale strukturovaně: nadpisy,
tabulky a vložené grafy (schéma, VVÚ, posouzení). Volající (GUI) může předat
PNG obrázky svých pláten v `images` = {"schema": bytes, "vvu": bytes,
"margin": bytes}; když chybí, sekce s obrázkem se vynechá.
"""
from __future__ import annotations

import datetime
import io

from .i18n import tr
from .settings import fmt


def _tbl(doc, headers):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Light Grid Accent 1"
    for j, h in enumerate(headers):
        t.rows[0].cells[j].text = str(h)
    return t


def _row(t, values):
    cells = t.add_row().cells
    for j, v in enumerate(values):
        cells[j].text = v if isinstance(v, str) else fmt(v)


def _img(doc, images, key, width_mm=160):
    if not images or key not in images or not images[key]:
        return
    try:
        from docx.shared import Mm
        doc.add_picture(io.BytesIO(images[key]), width=Mm(width_mm))
    except Exception:
        pass


def build_docx(state, result, margins, path, images=None, project_name=""):
    """Sestaví a uloží protokol DOCX. Vrací cestu."""
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from .sections_along import (normalized_segments, eff_defs,
                                 material_for_segment)
    from .section import build_section

    doc = Document()
    h = doc.add_heading(tr("BEAMER – Protokol statické analýzy nosníku"), 0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if project_name:
        pn = doc.add_paragraph(project_name)
        pn.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ── 1 Nosník a model ──
    doc.add_heading(tr("1  Nosník a model"), 1)
    doc.add_paragraph(f"{tr('Délka L')} = {fmt(state.length)} mm    "
                      f"{tr('Teorie')} = {state.theory}    "
                      f"{tr('Dodatečný součinitel')} = {fmt(state.additional_factor)}")
    try:
        comb = state.active_combination()
        if comb:
            doc.add_paragraph(tr("Zobrazená kombinace: ") + comb.name)
    except Exception:
        pass

    doc.add_heading(tr("Podpory"), 2)
    t = _tbl(doc, ["#", "x [mm]", tr("typ"), tr("úhel [°]"), tr("k / Δ")])
    for i, s in enumerate(state.supports):
        extra = ""
        if s.type == "spring":
            extra = f"k_z={fmt(getattr(s,'spring_z',0))} N/mm"
        elif abs(getattr(s, "settlement", 0.0)) > 1e-9:
            extra = f"Δ={fmt(s.settlement)} mm"
        _row(t, [str(i + 1), fmt(s.x), s.type, fmt(s.angle), extra])

    doc.add_heading(tr("Zatížení"), 2)
    t = _tbl(doc, [tr("typ"), tr("popis")])
    from .report import _load_desc
    for ld in state.loads:
        _row(t, [ld.type, _load_desc(ld)])

    _img(doc, images, "schema")

    # ── 2 Úseky a průřezy ──
    doc.add_heading(tr("2  Úseky a průřezy"), 1)
    t = _tbl(doc, [tr("Úsek"), "x [mm]", tr("materiál"), tr("průřez"),
                   "A [mm²]", "Iy [mm⁴]", "Iz [mm⁴]", "IT [mm⁴]"])
    for i, seg in enumerate(normalized_segments(state)):
        sec1, _ = eff_defs(state, seg)
        mat = material_for_segment(state, seg)
        try:
            sc = build_section(sec1, fem=False)
            avals = [fmt(sc.A), fmt(sc.Iy), fmt(sc.Iz), fmt(sc.IT)]
        except Exception:
            avals = ["—", "—", "—", "—"]
        _row(t, [str(i + 1), f"{fmt(seg.x1)}–{fmt(seg.x2)}",
                 getattr(mat, "name", "?"), getattr(sec1, "type", "?")] + avals)

    # ── 3 Vnitřní účinky + reakce ──
    if result and result.is_stable and result.points:
        P = result.points
        doc.add_heading(tr("3  Vnitřní účinky (extrémy) a reakce"), 1)
        t = _tbl(doc, [tr("veličina"), tr("min"), tr("max"), tr("jednotka")])
        for a, unit in (("N", "N"), ("V", "N"), ("M", "N·mm"), ("Mk", "N·mm"), ("w", "mm")):
            vals = [getattr(p, a) for p in P]
            _row(t, [a, fmt(min(vals)), fmt(max(vals)), unit])
        _img(doc, images, "vvu")

        doc.add_heading(tr("Reakce"), 2)
        t = _tbl(doc, ["x [mm]", "Rx [N]", "Rz [N]", "My [N·mm]", "Mk [N·mm]"])
        for rc in result.reactions:
            _row(t, [fmt(rc.x), fmt(rc.Rx), fmt(rc.Rz), fmt(rc.Ry), fmt(rc.Rx_torsion)])

    # ── 4 Posouzení (RF) ──
    if margins:
        crit = min(margins, key=lambda mm: mm.RF)
        doc.add_heading(tr("4  Posouzení (RF = reserve factor, ≥ 1 vyhovuje)"), 1)
        doc.add_paragraph(
            f"σ_red,max = {fmt(max(mm.mises_max for mm in margins))} MPa    "
            f"RF_min = {fmt(crit.RF)} ({crit.critical}) @ x = {fmt(crit.x)} mm")
        _img(doc, images, "margin")

    # ── Vzpěr, konzervativní kontrola (sdílená obálka přes kombinace) ──
    if result and result.is_stable and result.points:
        from .analysis import buckling_check, conservative_check, envelope_over_combinations
        env = None
        if getattr(state, "load_combinations", None):
            try:
                env = envelope_over_combinations(state)
            except Exception:
                env = None
        try:
            bc = buckling_check(state, result, env=env)
        except Exception:
            bc = None
        if bc is not None:
            scope = (tr("obálka přes všechny kombinace") if env is not None
                     else tr("zobrazená kombinace"))
            doc.add_heading(tr("Vzpěrná stabilita (Johnson-Euler, tlačené úseky)")
                            + f" – {scope}", 1)
            t = _tbl(doc, [tr("Úsek"), "N [N]", "λ", "σ_cr [MPa]", "P_cr [N]", "RF_vzpěr"])
            for r in bc.rows:
                _row(t, [r["label"], fmt(r["N"]), fmt(r["lam"]),
                         fmt(r["sigma_cr"]), fmt(r["P_cr"]), fmt(r["RF"])])
            doc.add_paragraph(f"RF_vzpěr,min = {fmt(bc.rf_min)} ({tr('řídí')} {bc.crit_label})")

        # fáze 2: bifurkace soustavy (vlastní čísla)
        from .analysis import buckling_eigen_check
        try:
            be = buckling_eigen_check(state, result)
        except Exception:
            be = None
        if be is not None:
            doc.add_heading(tr("Vzpěrná stabilita – fáze 2 (bifurkace soustavy, vlastní čísla)")
                            + f" – {tr('zobrazená kombinace')}", 1)
            doc.add_paragraph(f"λ_cr = {fmt(be.lam_cr)} = RF_vzpěr   "
                              f"P_cr = {fmt(be.P_cr)} N   N_ref = {fmt(be.N_ref)} N   "
                              f"μ_eff = {fmt(be.mu_eff)}")
            doc.add_paragraph(tr("Vzpěrná délka vyplývá z okrajových podmínek (bez ručního "
                                 "μ); slabá osa I_min; osové pole z rovnováhy jedné kombinace."))
            _img(doc, images, "buckling")

        if env is not None:
            try:
                cc = conservative_check(state, env=env)
            except Exception:
                cc = None
            if cc is not None:
                doc.add_heading(tr("Konzervativní obálková kontrola (maxima naráz v řezu)"), 1)
                doc.add_paragraph(f"|N|={fmt(cc.N_max)} N   |V|={fmt(cc.V_max)} N   "
                                  f"|M|={fmt(cc.M_max)} N·mm   |Mk|={fmt(cc.Mk_max)} N·mm")
                t = _tbl(doc, [tr("Úsek"), "σ [MPa]", "τ [MPa]", "σ_red [MPa]", "RF"])
                for r in cc.rows:
                    _row(t, [r["label"], fmt(r["sigma"]), fmt(r["tau"]),
                             fmt(r["sred"]), fmt(r["RF"])])
                doc.add_paragraph(f"RF_konzervativní = {fmt(cc.rf_min)} "
                                  f"({tr('řídí')} {cc.crit_label})")

    doc.save(path)
    return path
