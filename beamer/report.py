"""Textový protokol výpočtu (lokalizovaný CS/EN přes tr())."""
from __future__ import annotations

import datetime

from .settings import fmt
from .i18n import tr


def build_report(state, result, margins, include_conservative=False) -> str:
    """`include_conservative=True` doplní obálkové sekce (konzervativní kontrola,
    vzpěr přes obálku N) – počítá obálku přes VŠECHNY kombinace (n×solve+reserves,
    drahé). Živá karta Výsledky volá s False (rychlé); exporty s True."""
    L = []
    L.append("=" * 60)
    L.append("  " + tr("BEAMER – PROTOKOL STATICKÉ ANALÝZY NOSNÍKU"))
    L.append("  " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    L.append("=" * 60)
    L.append("")

    L.append(tr("NOSNÍK"))
    L.append(f"  {tr('Délka L')} = {state.length} mm")
    L.append(f"  {tr('Teorie')} = {state.theory}")
    L.append(f"  {tr('Dodatečný součinitel')} = {state.additional_factor}  "
             f"({tr('zatížení = početní/ultimate')})")
    L.append("  " + tr("Podpory:"))
    for s in state.supports:
        extra = ""
        if s.type == "spring":
            extra = f"  k_z={fmt(getattr(s, 'spring_z', 0))} N/mm"
            if getattr(s, "spring_ry", 0):
                extra += f"  k_ry={fmt(s.spring_ry)} N·mm/rad"
        if abs(getattr(s, "settlement", 0.0)) > 1e-9:
            extra += f"  Δ={fmt(s.settlement)} mm ({tr('vnucený posun')})"
        if abs(getattr(s, "gap", 0.0)) > 1e-9:
            extra += f"  {tr('vůle')}=±{fmt(s.gap)} mm"
        L.append(f"    x={s.x:.0f} mm  {s.type}  {tr('úhel')}={s.angle}°{extra}")
    if state.hinges:
        L.append("  " + tr("Klouby:") + " " + ", ".join(f"x={h.x:.0f}" for h in state.hinges))
    L.append("  " + tr("Zatížení:"))
    for ld in state.loads:
        L.append(f"    {ld.type}: " + _load_desc(ld))
    L.append("")

    # ── úseky: materiál, průřez, kritický RF ──
    from .sections_along import normalized_segments
    from .section import build_section
    from .analysis import critical_per_part
    from .sections_along import eff_defs, material_for_segment
    segs = normalized_segments(state)
    parts_crit = critical_per_part(state, margins) if margins else [None]*len(segs)
    L.append(tr("ÚSEKY NOSNÍKU"))
    for i, seg in enumerate(segs):
        sec1, sec2 = eff_defs(state, seg)
        mat = material_for_segment(state, seg)
        pid = getattr(seg, "property_id", None)
        pid_tag = ""
        if pid:
            p = next((pp for pp in (getattr(state, "properties", None) or []) if pp.id == pid), None)
            if p:
                pid_tag = f"  [PID {p.pid}: {p.name}]"
        L.append(f"  ── {tr('Úsek')} {i+1}:  x = {seg.x1:.0f} … {seg.x2:.0f} mm  "
                 f"({tr('délka')} {seg.length:.0f} mm){pid_tag}")
        L.append(f"     {tr('Materiál:')} {mat.name}  E={fmt(mat.E)} MPa  G={fmt(mat.G)} MPa  "
                 f"Re={fmt(mat.Re)} MPa  Rm={fmt(mat.Rm)} MPa")
        tap = "" if sec2 is None else f" → {sec2.type}"
        L.append(f"     {tr('Průřez:')} {sec1.type}{tap}")
        try:
            sc = build_section(sec1)
            L.append(f"     A={fmt(sc.A)} mm²  Iy={fmt(sc.Iy)} mm⁴  Iz={fmt(sc.Iz)} mm⁴  "
                     f"IT={fmt(sc.IT)} mm⁴  Iω={fmt(sc.Iw)} mm⁶")
            L.append(f"     Wb,y={fmt(getattr(sc,'Wb_y',0))} Wb,z={fmt(getattr(sc,'Wb_z',0))} "
                     f"Wt={fmt(getattr(sc,'Wb_t',0))}   α_pl={fmt(getattr(sc,'alpha_pl',1.0))}")
        except Exception:
            pass
        cp = parts_crit[i] if i < len(parts_crit) else None
        if cp and cp.get("crit"):
            c = cp["crit"]
            L.append(f"     {tr('Kritický řez')} x={c.x:.0f}: σ_red={fmt(c.mises_max)} MPa  "
                     f"RF_yield={fmt(c.RF_yield)}  RF_ult={fmt(c.RF_ultimate)}  "
                     f"RF_min={fmt(c.RF)} ({c.critical})")
        L.append("")

    if result and result.is_stable and result.points:
        N = [p.N for p in result.points]
        V = [p.V for p in result.points]
        M = [p.M for p in result.points]
        Mk = [p.Mk for p in result.points]
        w = [p.w for p in result.points]
        L.append(tr("VNITŘNÍ ÚČINKY (extrémy)"))
        L.append(f"  N : {fmt(min(N))} … {fmt(max(N))} N")
        L.append(f"  V : {fmt(min(V))} … {fmt(max(V))} N")
        L.append(f"  M : {fmt(min(M))} … {fmt(max(M))} N·mm")
        L.append(f"  Mk: {fmt(min(Mk))} … {fmt(max(Mk))} N·mm")
        L.append(f"  w : {fmt(min(w))} … {fmt(max(w))} mm")
        L.append("")
        L.append(tr("REAKCE"))
        for rc in result.reactions:
            L.append(f"  x={rc.x:.0f}: Rx={fmt(rc.Rx)} N  Rz={fmt(rc.Rz)} N  "
                     f"My={fmt(rc.Ry)} N·mm  Mk={fmt(rc.Rx_torsion)} N·mm")
        L.append("")

    if margins:
        crit = min(margins, key=lambda mm: mm.RF)
        L.append(tr("POSOUZENÍ (RF = reserve factor, ≥ 1 vyhovuje)"))
        if getattr(state, "plasticity_enabled", False):
            L.append(f"  {tr('Plasticita: ZAP')} ({state.plasticity_method}) – RF_ultimate = α_pl·Rm/σ")
        L.append(f"  σ_red,max ({tr('celý nosník')}) = {fmt(max(mm.mises_max for mm in margins))} MPa")
        L.append(f"  RF_min ({tr('celý nosník')}) = {fmt(crit.RF)} ({crit.critical}) @ x={crit.x:.0f} mm")
        L.append("")

    # ── vzpěr + konzervativní obálková kontrola ──
    # Obálka přes kombinace je DRAHÁ (n×solve+reserves) → jen na explicitní
    # export (include_conservative=True); živá karta Výsledky ukáže vzpěr ze
    # zobrazené kombinace a odkáže na export/Load Case Builder.
    if result and result.is_stable and result.points:
        from .analysis import buckling_check, conservative_check, envelope_over_combinations
        env = None
        if include_conservative and getattr(state, "load_combinations", None):
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
            L.append(tr("VZPĚRNÁ STABILITA (Johnson-Euler, tlačené úseky)") + f" – {scope}")
            for r in bc.rows:
                L.append(f"    {r['label']}: N={fmt(r['N'])} N  λ={fmt(r['lam'])}  "
                         f"σ_cr={fmt(r['sigma_cr'])} MPa  P_cr={fmt(r['P_cr'])} N  "
                         f"RF_vzpěr={fmt(r['RF'])}")
            L.append(f"  RF_vzpěr,min = {fmt(bc.rf_min)} ({tr('řídí')} {bc.crit_label})")
            L.append("  " + tr("(slabá osa I_min, L_vzpěr=μ·L_úseku; fáze 1 – bez interakce s ohybem)"))
            L.append("")

        if env is not None:
            try:
                cc = conservative_check(state, env=env)
            except Exception:
                cc = None
            if cc is not None:
                L.append(tr("KONZERVATIVNÍ OBÁLKOVÁ KONTROLA (maxima naráz v řezu, přes všechny kombinace)"))
                L.append(f"  {tr('Maxima')}: |N|={fmt(cc.N_max)} N  |V|={fmt(cc.V_max)} N  "
                         f"|M|={fmt(cc.M_max)} N·mm  |Mk|={fmt(cc.Mk_max)} N·mm")
                for r in cc.rows:
                    L.append(f"    {r['label']}: σ={fmt(r['sigma'])} τ={fmt(r['tau'])} "
                             f"σ_red={fmt(r['sred'])} MPa  RF={fmt(r['RF'])}")
                L.append(f"  RF_konzervativní = {fmt(cc.rf_min)} ({tr('řídí')} {cc.crit_label})")
                L.append("  " + tr("(horní odhad – maxima z různých poloh sečtena; přesné RF viz výše)"))
                L.append("")
        elif getattr(state, "load_combinations", None):
            L.append(tr("(Konzervativní obálková kontrola a vzpěr přes obálku kombinací: "
                        "v exportu protokolu nebo v Load Case Builderu – Graf obálky.)"))
            L.append("")

    # ── kontrolní body (volitelné řezy) ──
    cps = getattr(state, "control_points", None) or []
    if cps and result and result.is_stable and result.points:
        from .analysis import values_at_x_multi
        L.append(tr("KONTROLNÍ BODY"))
        items = sorted(enumerate(cps), key=lambda t: t[1].x)
        for orig_idx, cp in items:
            ds = values_at_x_multi(result, state, cp.x)
            if not ds:
                continue
            nm = (cp.name.strip() if getattr(cp, "name", "") else "") or f"K{orig_idx+1}"
            L.append(f"  ── {nm}  (x = {ds[0]['x']:.0f} mm)")
            d0 = ds[0]
            L.append(f"     N={fmt(d0['N'])} N  V={fmt(d0['V'])} N  "
                     f"M={fmt(d0['M'])} N·mm  Mk={fmt(d0['Mk'])} N·mm  w={fmt(d0['w'])} mm")
            for d in ds:
                tag = ""
                if d.get("seg_side"):
                    tag = f" [{tr('úsek')} {d['seg_index']+1} – {tr(d['seg_side'])}]"
                mat = d["material"]; sec = d["section"]
                st = getattr(sec, "section_type", "?") if sec else "?"
                mn = getattr(mat, "name", "?") if mat else "?"
                L.append(f"     ·{tag} {st} / {mn}: "
                         f"σ={fmt(d['sigma_max'])} τ={fmt(d['tau_max'])} "
                         f"σ_red={fmt(d['mises_max'])} MPa  "
                         f"RF={fmt(d['RF'])} ({d['critical']})")
        L.append("")

    L.append("=" * 60)
    return "\n".join(L)


def _load_desc(ld):
    if ld.type == "point_force":
        return f"x={ld.x:.0f} Fx={ld.Fx} N Fz={ld.Fz} N ecc={ld.eccentricity} mm"
    if ld.type == "distributed":
        return f"x1={ld.x1:.0f} x2={ld.x2:.0f} q1={ld.q1} q2={ld.q2} N/mm"
    if ld.type == "moment":
        return f"x={ld.x:.0f} My={ld.My} N·mm"
    if ld.type == "torsion":
        return f"x={ld.x:.0f} Mx={ld.Mx} N·mm"
    if ld.type == "thermal":
        return f"x1={ld.x1:.0f} x2={ld.x2:.0f} ΔT={ld.dT} °C"
    return ""
