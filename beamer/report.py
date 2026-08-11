"""Textový protokol výpočtu (lokalizovaný CS/EN přes tr())."""
from __future__ import annotations

import datetime

from .settings import fmt
from .i18n import tr



def _has_sharp_reentrant(state):
    """True, má-li některý úsek parametrický profil s vnitřním koutem a r=0.
    U takového profilu je špička τ v koutě singulární (závisí na hustotě sítě)."""
    types = {"i_section", "t_section", "l_section", "c_section", "u_section"}
    try:
        from .sections_along import normalized_segments, eff_defs
        for seg in normalized_segments(state):
            for sd in eff_defs(state, seg):
                if sd is None:
                    continue
                if sd.type in types and float((sd.params or {}).get("r", 0.0) or 0.0) <= 0:
                    return True
    except Exception:
        pass
    return False

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
    L.append(f"  {tr('Teorie ohybu')} = {state.theory}")
    L.append(f"  {tr('Teorie torze')} = "
             f"{getattr(state, 'torsion_theory', 'saint-venant')}")
    L.append(f"  {tr('Dodatečný součinitel')} = {state.additional_factor}  "
             f"({tr('aplikuje se pouze na ne-ULS zatěžovací stavy')})")
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
        if getattr(state, "torsion_theory", "saint-venant") == "vlasov":
            hold = getattr(s, "restrain_warping", None)
            hold = (s.type == "fixed") if hold is None else bool(hold)
            status = tr("bráněná") if hold else tr("volná")
            extra += f"  {tr('deplanace')}={status}"
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
            exact = (getattr(state, "tau_mode", "conservative") == "exact"
                     or getattr(state, "torsion_theory", "saint-venant") == "vlasov")
            sc = build_section(sec1, exact=exact)
            L.append(f"     A={fmt(sc.A)} mm²  Iy={fmt(sc.Iy)} mm⁴  Iz={fmt(sc.Iz)} mm⁴  "
                     f"IT={fmt(sc.IT)} mm⁴  Iω={fmt(sc.Iw)} mm⁶")
            if not getattr(sc, "strength_available", True):
                L.append("     ⚠ " + getattr(sc, "analysis_note", "Posouzení není dostupné."))
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
            if c.RF_local_buckling is not None:
                L.append(f"       RF_local={fmt(c.RF_local_buckling)} "
                         f"({c.critical_wall})")
            if c.RF_crippling is not None:
                L.append(f"       RF_crippling={fmt(c.RF_crippling)}")
        L.append("")

    if result and result.is_stable and result.points:
        N = [p.N for p in result.points]
        V = [p.V for p in result.points]
        Vy = [getattr(p, "V_y", 0.0) for p in result.points]
        M = [p.M for p in result.points]
        Mz = [getattr(p, "M_z", 0.0) for p in result.points]
        Mk = [p.Mk for p in result.points]
        B = [getattr(p, "B", 0.0) for p in result.points]
        Tsv = [getattr(p, "T_sv", p.Mk) for p in result.points]
        Tw = [getattr(p, "T_w", 0.0) for p in result.points]
        beta = [getattr(p, "warping_rate", 0.0) for p in result.points]
        w = [p.w for p in result.points]
        v = [getattr(p, "v", 0.0) for p in result.points]
        u = [getattr(p, "u", 0.0) for p in result.points]
        L.append(tr("VNITŘNÍ ÚČINKY (extrémy)"))
        L.append(f"  N : {fmt(min(N))} … {fmt(max(N))} N")
        L.append(f"  V : {fmt(min(V))} … {fmt(max(V))} N")
        L.append(f"  Vy: {fmt(min(Vy))} … {fmt(max(Vy))} N")
        L.append(f"  M : {fmt(min(M))} … {fmt(max(M))} N·mm")
        L.append(f"  Mz: {fmt(min(Mz))} … {fmt(max(Mz))} N·mm")
        L.append(f"  Mk: {fmt(min(Mk))} … {fmt(max(Mk))} N·mm")
        if getattr(state, "torsion_theory", "saint-venant") == "vlasov":
            L.append(f"  Tsv: {fmt(min(Tsv))} … {fmt(max(Tsv))} N·mm")
            L.append(f"  Tω : {fmt(min(Tw))} … {fmt(max(Tw))} N·mm")
            L.append(f"  B  : {fmt(min(B))} … {fmt(max(B))} N·mm²")
            L.append(f"  θ' : {fmt(min(beta))} … {fmt(max(beta))} 1/mm")
        L.append(f"  w : {fmt(min(w))} … {fmt(max(w))} mm")
        L.append(f"  v : {fmt(min(v))} … {fmt(max(v))} mm")
        if max(abs(min(u)), abs(max(u))) > 1e-9:      # osově zatížený prut
            L.append(f"  u : {fmt(min(u))} … {fmt(max(u))} mm")
            L.append(tr("  celkové prodloužení ΔL: ") + f"{fmt(u[-1] - u[0])} mm")
        L.append("")
        L.append(tr("REAKCE"))
        for rc in result.reactions:
            line = (f"  x={rc.x:.0f}: Rx={fmt(rc.Rx)} N  Ry={fmt(rc.Ry_force)} N  "
                     f"Rz={fmt(rc.Rz)} N  My={fmt(rc.Ry)} N·mm  "
                     f"Mz={fmt(rc.Rz_moment)} N·mm  Mx={fmt(rc.Rx_torsion)} N·mm")
            if getattr(state, "torsion_theory", "saint-venant") == "vlasov":
                line += f"  B={fmt(getattr(rc, 'B_warping', 0.0))} N·mm²"
            L.append(line)
        L.append("")

    if margins:
        crit = min(margins, key=lambda mm: mm.RF)
        L.append(tr("POSOUZENÍ (RF = reserve factor, ≥ 1 vyhovuje)"))
        if getattr(state, "torsion_theory", "saint-venant") == "vlasov":
            L.append(tr("  Torze: Vlasov (7 DOF, bráněná/volná deplanace, "
                        "σw=B·ω/Iω a sekundární τw zahrnuty)"))
        # model skládání smyku – ovlivňuje σ_red, patří do protokolu
        if getattr(state, "tau_mode", "conservative") == "exact":
            L.append(tr("  Smyk: přesné 2D pole (Pilkey Ψ/Φ, vektorové skládání "
                        "s torzí)"))
            if _has_sharp_reentrant(state):
                L.append(tr("    ⚠ Profil má ostrý vnitřní kout (r=0): špička τ "
                            "v koutě je singulární a závisí na síti – zadej zaoblení r."))
        else:
            L.append(tr("  Smyk: konzervativní (Žuravskij, |τ_V|+|τ_t|)"))
        if getattr(state, "plasticity_enabled", False):
            L.append(f"  {tr('Plasticita: ZAP')} ({state.plasticity_method}) – RF_ultimate = α_pl·Rm/σ")
            # α_pl v ŘÍDICÍM řezu: uživatel jinak nevidí, proč se zapnutí
            # neprojevilo (uplatní se jen v ultimate a klesá se smykem)
            try:
                from .analysis import values_at_x
                dv = values_at_x(result, state, crit.x)
                a_nom = dv.get("alpha_pl", 1.0)
                a_eff = dv.get("alpha_pl_eff", 1.0)
                L.append(tr("  α_pl v řídicím řezu: zadaná %s, uplatněná %s")
                         % (fmt(a_nom), fmt(a_eff)))
                if a_nom > 1.0 and a_eff < a_nom - 1e-9:
                    L.append(tr("    (snížena interakcí se smykem / osovou silou "
                                "– viz THEORY.md)"))
                if crit.critical == "yield":
                    L.append(tr("    pozn.: řídí mez kluzu – α_pl ovlivňuje jen "
                                "RF_ultimate"))
            except Exception:
                pass
        L.append(f"  σ_red,max ({tr('celý nosník')}) = {fmt(max(mm.mises_max for mm in margins))} MPa")
        L.append(f"  RF_min ({tr('celý nosník')}) = {fmt(crit.RF)} ({crit.critical}) @ x={crit.x:.0f} mm")
        if crit.RF_local_buckling is not None:
            L.append(f"  RF_local = {fmt(crit.RF_local_buckling)} "
                     f"(stěna: {crit.critical_wall})")
        if crit.RF_crippling is not None:
            L.append(f"  RF_crippling = {fmt(crit.RF_crippling)}")
        L.append(tr("  Lokální boulení: klasická desková teorie; crippling: "
                    "empirická metoda Needham/Gerard, jen pro známou topologii."))
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

        # fáze 2: bifurkace soustavy (vlastní čísla) – dražší (~0,3 s), jen export
        if include_conservative:
            from .analysis import buckling_eigen_check
            try:
                be = buckling_eigen_check(state, result)
            except Exception:
                be = None
            if be is not None:
                L.append(tr("VZPĚRNÁ STABILITA – FÁZE 2 (bifurkace soustavy, vlastní čísla)")
                         + f" – {tr('zobrazená kombinace')}")
                L.append(f"  λ_cr = {fmt(be.lam_cr)} = RF_vzpěr "
                         f"({tr('násobitel zatížení do vybočení')})")
                L.append(f"  P_cr = {fmt(be.P_cr)} N   (N_ref = {fmt(be.N_ref)} N)   "
                         f"μ_eff = {fmt(be.mu_eff)}")
                L.append("  " + tr("(slabá osa I_min; vzpěrná délka VYPLYNE z okrajových "
                                   "podmínek – bez ručního μ; osové pole z rovnováhy jedné "
                                   "kombinace; podpory drží příčný posun i v rovině vybočení; "
                                   "bez interakce s ohybem)"))
                # silná osa (I_max) – ukázat jen když se liší (nesymetrický řez)
                try:
                    be_s = buckling_eigen_check(state, result, axis="max")
                except Exception:
                    be_s = None
                if be_s is not None and abs(be_s.lam_cr - be.lam_cr) > 1e-3 * be.lam_cr:
                    L.append(f"  {tr('silná osa I_max')}: λ_cr = {fmt(be_s.lam_cr)}  "
                             f"P_cr = {fmt(be_s.P_cr)} N   μ_eff = {fmt(be_s.mu_eff)}  "
                             f"({tr('řídí slabá osa')})")
                L.append("")

        # beam-column: interakce tlak + ohyb (Bruhn)
        from .analysis import beam_column_check
        try:
            bcx = beam_column_check(state, result)
        except Exception:
            bcx = None
        if bcx is not None:
            L.append(tr("INTERAKCE TLAK + OHYB (beam-column, Bruhn)") + f" – {tr('zobrazená kombinace')}")
            for r in bcx.rows:
                L.append(f"    {r['label']}: N={fmt(r['N'])} N  P_cr={fmt(r['P_cr'])} N  "
                         f"R_c={fmt(r['R_c'])}  σ_ohyb={fmt(r['sigma_b'])} MPa  R_b={fmt(r['R_b'])}  "
                         f"RF={fmt(r['RF'])}  MS={fmt(r['MS'])}")
            L.append(f"  RF_min = {fmt(bcx.rf_min)} ({tr('řídí')} {bcx.crit_label})")
            L.append("  " + tr("(R_c + R_b/(1−R_c) ≤ 1; RF = 1/R_int, MS = RF−1; jen tlačené úseky)"))
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
            L.append(f"     N={fmt(d0['N'])} N  V={fmt(d0['V'])} N  Vy={fmt(d0['V_y'])} N  "
                     f"M={fmt(d0['M'])} N·mm  Mz={fmt(d0['M_z'])} N·mm  "
                     f"Mk={fmt(d0['Mk'])} N·mm  w={fmt(d0['w'])} mm  v={fmt(d0['v'])} mm")
            if getattr(state, "torsion_theory", "saint-venant") == "vlasov":
                L.append(f"     Tsv={fmt(d0['T_sv'])} N·mm  Tω={fmt(d0['T_w'])} N·mm  "
                         f"B={fmt(d0['B'])} N·mm²  θ'={fmt(d0['warping_rate'])} 1/mm")
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
                if d.get("RF_local_buckling") is not None:
                    L.append(f"       RF_local={fmt(d['RF_local_buckling'])} "
                             f"({d.get('critical_wall', '')})")
                if d.get("RF_crippling") is not None:
                    L.append(f"       RF_crippling={fmt(d['RF_crippling'])}")
        L.append("")

    L.append("=" * 60)
    return "\n".join(L)


def _load_desc(ld):
    if ld.type == "point_force":
        s = f"x={ld.x:.0f} Fx={ld.Fx} N Fz={ld.Fz} N"
        if abs(getattr(ld, "Fy", 0.0)) > 1e-9:
            s += f" Fy={ld.Fy} N"
        return s + f" ecc={ld.eccentricity} mm"
    if ld.type == "distributed":
        s = f"x1={ld.x1:.0f} x2={ld.x2:.0f} q1={ld.q1} q2={ld.q2} N/mm"
        if abs(getattr(ld, "qy1", 0.0)) > 1e-9 or abs(getattr(ld, "qy2", 0.0)) > 1e-9:
            s += f"  qy1={ld.qy1} qy2={ld.qy2} N/mm"
        return s
    if ld.type == "moment":
        s = f"x={ld.x:.0f} My={ld.My} N·mm"
        if abs(getattr(ld, "Mz", 0.0)) > 1e-9:
            s += f" Mz={ld.Mz} N·mm"
        return s
    if ld.type == "torsion":
        return f"x={ld.x:.0f} Mx={ld.Mx} N·mm"
    if ld.type == "thermal":
        s = f"x1={ld.x1:.0f} x2={ld.x2:.0f} ΔT={ld.dT} °C"
        if abs(getattr(ld, "dT_grad", 0.0)) > 1e-9:
            s += f" grad={ld.dT_grad} °C"
        return s
    return ""
