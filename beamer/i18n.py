"""Lokalizace CS/EN. Překládají se řetězce s českými slovy; symbolové a
jednotkové popisky (A [mm²], x [mm], σ [MPa]…) zůstávají shodné.

Použití: ``tr("Nosník")`` → "Beam" při EN, jinak "Nosník".
Anglické termíny dle standardní inženýrské terminologie (EN 1993, Pilkey).
"""
from __future__ import annotations

from .settings import SETTINGS

EN = {
    # skupiny / panely
    "Nosník": "Beam",
    "Materiál": "Material",
    "Podpory": "Supports",
    "Klouby": "Hinges",
    "Zatížení": "Loads",
    "Součinitele (letecké)": "Factors (aerospace)",
    # nosník
    "Délka L:": "Length L:",
    "Celková délka L:": "Total length L:",
    "Teorie:": "Theory:",
    # úseky
    "Úseky nosníku": "Beam segments",
    "Každý úsek má délku, materiál a průřez (vč. náběhu).":
        "Each segment has a length, material and cross-section (incl. taper).",
    "Délka:": "Length:",
    "Materiál:": "Material:",
    "Průřez": "Cross-section",
    "Smazat úsek": "Delete segment",
    "Smazat zatížení": "Delete load",
    "Materiály (knihovna)": "Materials (library)",
    "Úsek:": "Segment:",
    "kritický řez": "critical section",
    # materiál
    "Volba:": "Selection:",
    "+ Vlastní": "+ Custom",
    "Vlastní materiál": "Custom material",
    " (vlastní)": " (custom)",
    "Název:": "Name:",
    "Re (mez kluzu)": "Re (yield strength)",
    "Rm (pevnost)": "Rm (ultimate strength)",
    "Smazat tento materiál": "Delete this material",
    # typy průřezů
    "Obdélník": "Rectangle",
    "Dutý obdélník (RHS)": "Rectangular hollow section (RHS)",
    "Kruh": "Circle",
    "Trubka (CHS)": "Tube (CHS)",
    "I-profil": "I-section",
    "T-profil": "T-section",
    "L-profil": "Angle (L)",
    "U/C-profil": "Channel (U/C)",
    "Vlastní (polygon)": "Custom (polygon)",
    # rozměry průřezu
    "šířka b": "width b",
    "výška h": "height h",
    "šířka B": "width B",
    "tl. stěny tw": "wall thickness tw",
    "průměr D": "diameter D",
    "vnější ⌀ Do": "outer dia. Do",
    "tloušťka t": "thickness t",
    "stojina tw": "web tw",
    "horní pásnice bf1": "top flange bf1",
    "tl. tf1": "thk. tf1",
    "dolní pásnice bf2": "bottom flange bf2",
    "tl. tf2": "thk. tf2",
    "pásnice b": "flange b",
    "pásnice tf": "flange tf",
    # průřez – ovládání
    "Proměnný průřez podél nosníku (úseky / náběh)":
        "Variable cross-section along beam (segments / taper)",
    "✎  Editovat v okně…": "✎  Edit in window…",
    "Úseky nosníku (mm). Náběh = plynulá změna průřezu mezi A a B (stejný typ).":
        "Beam segments (mm). Taper = smooth change between A and B (same type).",
    "+ Přidat úsek": "+ Add segment",
    "Úsek": "Segment",
    "Náběh (tapered) → průřez B": "Taper → cross-section B",
    "Průřez A": "Cross-section A",
    "Průřez B": "Cross-section B",
    # podpory
    "x [mm]": "x [mm]",
    "typ": "type",
    "úhel [°]": "angle [°]",
    "kloub": "pin",
    "rolna": "roller",
    "vetknutí": "fixed",
    "+ Přidat podporu": "+ Add support",
    "+ Přidat kloub": "+ Add hinge",
    # zatížení
    "+ Síla": "+ Force",
    "+ Spojité": "+ Distributed",
    "+ Moment": "+ Moment",
    "+ Krut": "+ Torque",
    "Bodová síla": "Point force",
    "Spojité": "Distributed load",
    "Ohyb. moment": "Bending moment",
    "Krut": "Torque",
    "popisek zatížení": "load label",
    "Fz (+nahoru):": "Fz (+up):",
    "excentricita:": "eccentricity:",
    # součinitel
    "Součinitel": "Factor",
    "Dodatečný součinitel:": "Additional factor:",
    "Zatížení se zadává jako početní (ultimate) síla.":
        "Loads are entered as design (ultimate) force.",
    "Využít součinitel plasticity (RF_ultimate)":
        "Use plastic shape factor (RF_ultimate)",
    "Metoda α_pl:": "α_pl method:",
    "analyticky (W_pl/W_el)": "analytic (W_pl/W_el)",
    "tabulkově (známé profily)": "tabular (known profiles)",
    # výsledky
    "Veličina": "Quantity",
    "Hodnota": "Value",
    "— Průřez —": "— Cross-section —",
    "— Průřez (uprostřed) —": "— Cross-section (midspan) —",
    "metoda IT/Iω": "IT/Iω method",
    "FEM (přesné)": "FEM (exact)",
    "scanline": "scanline",
    "střed smyku z_SC [mm]": "shear centre z_SC [mm]",
    "κ (Timoshenko)": "κ (Timoshenko)",
    "— VVÚ (extrémy) —": "— Internal forces (extremes) —",
    "— Posouzení —": "— Assessment —",
    "Reakce": "Reaction",
    "Průřez (kritický x=": "Cross-section (critical x=",
    "Průřez (uprostřed)": "Cross-section (midspan)",
    "neplatný průřez": "invalid cross-section",
    "— VVÚ / posouzení —": "— Internal forces / assessment —",
    "stiskněte Spočítat": "press Calculate",
    # hlavní okno
    "BEAMER – statická analýza nosníku": "BEAMER – beam static analysis",
    "▶  Spočítat  (F5)": "▶  Calculate  (F5)",
    "● změněno – stiskněte Spočítat": "● changed – press Calculate",
    "Počítám…": "Calculating…",
    "Přepočítáno.": "Recalculated.",
    "&Soubor": "&File",
    "Nový": "New",
    "Otevřít…": "Open…",
    "Uložit jako…": "Save as…",
    "Konec": "Quit",
    "Demo nosník": "Demo beam",
    "Nastavení…": "Settings…",
    "O programu": "About",
    "Statická analýza přímého nosníku a posouzení napjatosti po průřezu. "
    "Letecké konstrukční výpočty (VVÚ, průhyb, RF).":
        "Static analysis of a straight beam and cross-section stress assessment. "
        "Aerospace structural calculations (internal forces, deflection, RF).",
    "Otevřít projekt": "Open project",
    "Uložit projekt": "Save project",
    "Export protokolu": "Export report",
    "Export VVÚ": "Export diagrams",
    "Export protokolu (TXT)…": "Export report (TXT)…",
    "Export VVÚ (PNG)…": "Export diagrams (PNG)…",
    "Export křivek (CSV)…": "Export curves (CSV)…",
    "Rozlišení exportu": "Export resolution",
    "Počet bodů (max = plné rozlišení):": "Number of points (max = full resolution):",
    "Nejsou k dispozici výsledky.": "No results available.",
    "Křivky uloženy: ": "Curves saved: ",
    "bodů": "points",
    # ochrana neuložené práce
    "Neuložené změny": "Unsaved changes",
    "Projekt obsahuje neuložené změny. Chcete je uložit?":
        "The project has unsaved changes. Do you want to save them?",
    "Uložit": "Save",
    "Zavřít bez uložení": "Don't save",
    "Storno": "Cancel",
    # sdílená knihovna
    "Sdílená knihovna (materiály a profily)": "Shared library (materials and profiles)",
    "(nenastaveno – jen uživatelská knihovna)": "(not set – user library only)",
    "Procházet…": "Browse…",
    "Vymazat": "Clear",
    "Společná složka (např. síťový disk). Knihovny se pak "
    "načítají ze sdílené i uživatelské; zápis jde do "
    "uživatelské, do sdílené jen přes „Publikovat“.":
        "A common folder (e.g. a network drive). Libraries are then loaded from "
        "both the shared and the user library; saving writes to the user "
        "library, the shared one only via “Publish”.",
    "Vyberte složku sdílené knihovny": "Select shared library folder",
    "💾 Do knihovny ▾": "💾 To library ▾",
    "Uložit do uživatelské knihovny": "Save to user library",
    "Publikovat do sdílené knihovny…": "Publish to shared library…",
    "Materiál uložen do uživatelské knihovny: ": "Material saved to user library: ",
    "Sdílená knihovna": "Shared library",
    "Nejprve nastavte složku sdílené knihovny v Nastavení.":
        "First set the shared library folder in Settings.",
    "Publikovat do sdílené": "Publish to shared",
    "Publikovat materiál „%s“ do SDÍLENÉ knihovny pro všechny uživatele?":
        "Publish material “%s” to the SHARED library for all users?",
    "Potvrdit publikaci": "Confirm publish",
    "Sdílená knihovna je společná pro celý tým. Opravdu zapsat?":
        "The shared library is common to the whole team. Really write?",
    "Materiál publikován do sdílené knihovny: ": "Material published to shared library: ",
    "Publikace selhala (zkontrolujte cestu a práva).":
        "Publish failed (check the path and permissions).",
    "Sdílená": "Shared",
    "Uživatelská": "User",
    "💾 Uložit profil ▾": "💾 Save profile ▾",
    "Publikovat profil": "Publish profile",
    "Publikovat profil „%s“ do SDÍLENÉ knihovny pro všechny uživatele?":
        "Publish profile “%s” to the SHARED library for all users?",
    "RF k:": "RF to:",
    "Kontrolní bod": "Control point",
    "Vlastnosti (PID)": "Properties (PID)",
    "Pojmenované {materiál + průřez} pod číslem; úsek si pak "
    "jen vybere PID. Změna PID se propíše do všech úseků.":
        "Named {material + cross-section} under a number; a segment then just "
        "picks a PID. Editing a PID propagates to all segments.",
    "+ Přidat PID": "+ Add PID",
    "název vlastnosti": "property name",
    "Smazat PID": "Delete PID",
    "Vlastnost": "Property",
    "PID:": "PID:",
    "(inline – vlastní)": "(inline – custom)",
    "Materiál i průřez řídí zvolený PID (uprav v sekci Vlastnosti).":
        "Material and cross-section come from the selected PID (edit in Properties).",
    "vlevo": "left",
    "vpravo": "right",
    "v kritickém řezu (RF_min):": "at the critical section (RF_min):",
    "— Napětí v tomto řezu —": "— Stress at this section —",
    "— Posouzení (celý nosník) —": "— Assessment (whole beam) —",
    # Load Case Builder
    "⊞ Load Cases": "⊞ Load Cases",
    "Load Case Builder": "Load Case Builder",
    "Zatěžovací stavy": "Load cases",
    "Název stavu": "Case name",
    "+ Přidat stav": "+ Add case",
    "Musí zůstat aspoň jeden stav.": "At least one case must remain.",
    "Stav": "Case",
    "Kombinace (Σ faktor × stav)": "Combinations (Σ factor × case)",
    "Název kombinace": "Combination name",
    "+ Kombinace": "+ Combination",
    "+ Stavy ×1 (auto)": "+ Cases ×1 (auto)",
    "Kombinace": "Combination",
    "↻ Přepočítat tabulku": "↻ Recompute table",
    "⤒ Export CSV…": "⤒ Export CSV…",
    "⧉ Kopírovat (Excel)": "⧉ Copy (Excel)",
    "Zobrazit vybranou v hlavním okně": "Show selected in main window",
    "Tabulka zkopírována do schránky (vložte do Excelu).":
        "Table copied to clipboard (paste into Excel).",
    "Vyberte řádek (kombinaci) v tabulce.": "Select a row (combination) in the table.",
    "Export CSV…": "Export CSV…",
    "Stav (LC):": "Case (LC):",
    "stav": "status",
    "NESTABILNÍ": "UNSTABLE",
    "min(Re,Rm)": "min(Re,Rm)",
    "Velikost písma:": "Font size:",
    "Tip: opakovaný klik na Max cykluje mezi špičkami veličiny.":
        "Tip: repeated clicks on Max cycle through the peaks of the quantity.",
    "špička %d/%d |%s|": "peak %d/%d |%s|",
    "Profil uložen do uživatelské knihovny: ": "Profile saved to user library: ",
    "Profil publikován do sdílené knihovny: ": "Profile published to shared library: ",
    # kontrolní body
    "Kontrolní body": "Control points",
    "Volitelné řezy, ve kterých se vypíšou výsledky "
    "(karta Výsledky + export). Nemění výpočet.":
        "Optional sections where results are reported "
        "(Results tab + export). They do not change the analysis.",
    "název": "name",
    "(volitelné)": "(optional)",
    "+ Přidat bod": "+ Add point",
    # textový protokol (report.py)
    "BEAMER – PROTOKOL STATICKÉ ANALÝZY NOSNÍKU": "BEAMER – BEAM STATIC ANALYSIS REPORT",
    "NOSNÍK": "BEAM",
    "Délka L": "Length L",
    "Teorie": "Theory",
    "Dodatečný součinitel": "Additional factor",
    "zatížení = početní/ultimate": "loads = ultimate",
    "Podpory:": "Supports:",
    "úhel": "angle",
    "Klouby:": "Hinges:",
    "Zatížení:": "Loads:",
    "ÚSEKY NOSNÍKU": "BEAM SEGMENTS",
    "délka": "length",
    "Průřez:": "Cross-section:",
    "Kritický řez": "Critical section",
    "VNITŘNÍ ÚČINKY (extrémy)": "INTERNAL FORCES (extremes)",
    "REAKCE": "REACTIONS",
    "POSOUZENÍ (RF = reserve factor, ≥ 1 vyhovuje)":
        "ASSESSMENT (RF = reserve factor, ≥ 1 passes)",
    "Plasticita: ZAP": "Plasticity: ON",
    "celý nosník": "whole beam",
    "KONTROLNÍ BODY": "CONTROL POINTS",
    "Chyba": "Error",
    "VVÚ v jednom grafu": "Diagrams in one chart",
    "Průřez a napjatost": "Cross-section & stress",
    "Posouzení (RF)": "Assessment (RF)",
    # karta Report (hodnoty ve zvoleném řezu)
    "Report": "Report",
    "Souřadnice x [mm]:": "Coordinate x [mm]:",
    "Zobrazit": "Show",
    "Max |V|": "Max |V|",
    "Max |M|": "Max |M|",
    "Max |Mk|": "Max |Mk|",
    "Kritický (min RF)": "Critical (min RF)",
    "Spusťte výpočet (Spočítat) a zvolte řez.":
        "Run the analysis (Calculate) and pick a section.",
    "Výsledek není k dispozici (nosník nestabilní?).":
        "No result available (unstable beam?).",
    "Výsledek není k dispozici.": "No result available.",
    "Řez": "Section",
    "— Vnitřní účinky —": "— Internal forces —",
    "— Průřez v řezu —": "— Cross-section at x —",
    "— Napětí —": "— Stress —",
    "— Materiál / posouzení —": "— Material / assessment —",
    "materiál": "material",
    "w (průhyb) [mm]": "w (deflection) [mm]",
    "φ (ohyb. pootočení) [°]": "φ (bending rotation) [°]",
    "θ (torzní pootočení) [°]": "θ (torsional rotation) [°]",
    "změněno – stiskněte Spočítat": "changed – press Calculate",
    "Nelze načíst: ": "Cannot load: ",
    "Importovat Ministatik (*.nos)…": "Import Ministatik (*.nos)…",
    "Importováno z Ministatik: ": "Imported from Ministatik: ",
    "Nelze uložit: ": "Cannot save: ",
    "Nelze exportovat: ": "Cannot export: ",
    "Uloženo: ": "Saved: ",
    "Protokol uložen: ": "Report saved: ",
    "Obrázek uložen: ": "Image saved: ",
    # plots
    "Schéma nosníku": "Beam scheme",
    "axonometrie": "axonometry",
    "Axonometrie": "Axonometry",
    "Prostorové (axonometrické) schéma – ukáže obě ohybové roviny naráz "
    "(svislé Fz/q i vodorovné Fy/Mz, krut) a 3D deformovaný tvar.\n"
    "Vhodné pro biaxiální (mimorovinné) zatížení; boční pohled zůstává "
    "přesnější pro čistě svislé úlohy.":
        "Spatial (axonometric) scheme – shows both bending planes at once "
        "(vertical Fz/q and horizontal Fy/Mz, torsion) and the 3D deformed shape.\n"
        "Suited to biaxial (out-of-plane) loading; the side view stays more "
        "accurate for purely vertical problems.",
    "N – osová síla [N]": "N – axial force [N]",
    "V – posouvající síla [N]": "V – shear force [N]",
    "M – ohybový moment [N·mm]": "M – bending moment [N·mm]",
    "Mk – kroutící moment [N·mm]": "Mk – torsional moment [N·mm]",
    "w – průhyb [mm]": "w – deflection [mm]",
    "φ – pootočení [rad]": "φ – rotation [rad]",
    "Bez výsledku": "No result",
    "Náhled zadání – stiskněte Spočítat pro VVÚ":
        "Input preview – press Calculate for diagrams",
    "Neplatný průřez": "Invalid cross-section",
    "střed smyku": "shear centre",
    "Bez průřezu": "No cross-section",
    "z [mm od těžiště]": "z [mm from centroid]",
    "Napjatost": "Stress",
    "Bez dat": "No data",
    "Rezervní faktor podél nosníku": "Reserve factor along beam",
    "  (osa oříznuta)": "  (axis clipped)",
    "RF (ořez 10)": "RF (clipped 10)",
    "Vnitřní účinky": "Internal forces",
    "Síly [N]": "Forces [N]",
    "Momenty [N·mm]": "Moments [N·mm]",
    "Průhyb w [mm]": "Deflection w [mm]",
    "Pootočení φ [rad]": "Rotation φ [rad]",
    # dialog průřezu
    "Editor průřezu": "Cross-section editor",
    "Typ a rozměry": "Type and dimensions",
    "Neplatný průřez:": "Invalid cross-section:",
    "Spočítat (FEM)": "Compute (FEM)",
    "FEM přepočteno (přesné IT, Iω, střed smyku).":
        "FEM recomputed (exact IT, Iω, shear centre).",
    "Předběžné (scanline). Stiskněte Spočítat (FEM) pro přesné hodnoty.":
        "Preliminary (scanline). Press Compute (FEM) for exact values.",
    # poly editor
    "Snap na mřížku 5 mm": "Snap to 5 mm grid",
    "Vymazat vše": "Clear all",
    "L-klik: přidat/táhnout bod · P-klik: smazat bod":
        "L-click: add/drag point · R-click: delete point",
    # nastavení
    "Nastavení": "Settings",
    "Jazyk / Language": "Jazyk / Language",
    "Čeština": "Čeština",
    "English": "English",
    "Formát čísel": "Number format",
    "Fixed (pevný)": "Fixed",
    "Scientific (vědecký)": "Scientific",
    "Desetinná místa:": "Decimal places:",
    "Zavřít": "Close",
    "Změna jazyka se projeví v celém rozhraní.":
        "Language change applies across the whole interface.",
    # knihovna / profily / materiály
    "💾 Do knihovny": "💾 To library",
    "📂 Z knihovny": "📂 From library",
    "💾 Uložit profil": "💾 Save profile",
    "⤓ Import": "⤓ Import",
    "⤒ Export": "⤒ Export",
    "Knihovna": "Library",
    "Materiál uložen do knihovny: ": "Material saved to library: ",
    "(knihovna je prázdná)": "(library is empty)",
    "Uložit profil": "Save profile",
    "Název profilu:": "Profile name:",
    "Profil uložen: ": "Profile saved: ",
    "Import profilu": "Import profile",
    "Export profilu": "Export profile",
    "Nelze importovat: ": "Cannot import: ",
    # knihovna materiálů (živá comba + správce)
    "Projekt": "Project",
    "knihovna": "library",
    "🗂 Knihovna…": "🗂 Library…",
    "Správa knihovny materiálů: nový, duplikovat, upravit, smazat, pořadí":
        "Manage the material library: new, duplicate, edit, delete, reorder",
    "Knihovna materiálů": "Material library",
    "Uživatelská knihovna": "User library",
    "Duplikovat": "Duplicate",
    "Smazat": "Delete",
    "Přidat nový materiál do knihovny": "Add a new material to the library",
    "Kopie vybraného (pak uprav)": "Copy of the selected one (then edit)",
    "Smaže jen z knihovny – projekty mají vlastní kopie":
        "Deletes from the library only – projects keep their own copies",
    "Výš": "Up",
    "Níž": "Down",
    "Posunout v seznamu nahoru (pořadí se ukládá – seskup si např. oceli k sobě)":
        "Move up in the list (the order is saved – e.g. group steels together)",
    "⤓ Převzít z projektu": "⤓ Take from project",
    "Uloží materiál z otevřeného projektu do knihovny":
        "Saves a material from the open project into the library",
    "Publikovat do sdílené…": "Publish to shared…",
    "Změny se ukládají hned. Úprava knihovny nemění materiály už zkopírované "
    "do projektů.":
        "Changes are saved immediately. Editing the library does not change "
        "materials already copied into projects.",
    "Sdílená knihovna (jen pro čtení)": "Shared library (read-only)",
    "Zkopírovat vybraný do uživatelské": "Copy selected to user library",
    "Smazat z knihovny": "Delete from library",
    "Smazat materiál „%s“ z uživatelské knihovny?\nProjekty, které ho už "
    "používají, mají vlastní kopii a nezmění se.":
        "Delete material “%s” from the user library?\nProjects already using "
        "it keep their own copy and will not change.",
    "Nový materiál": "New material",
    " (kopie)": " (copy)",
    "(projekt nemá materiály)": "(project has no materials)",
    "(knihovna je prázdná – přidej „Nový“)": "(library is empty – press “New”)",
    "α (roztažnost):": "α (expansion):",
    "Fcy (tlaková mez kluzu):": "Fcy (compressive yield):",
    "Fsu (mez ve smyku):": "Fsu (shear ultimate):",
    "0 = nezadáno → použije se Re": "0 = not set → Re is used",
    "0 = nezadáno → von Mises z Rm": "0 = not set → von Mises from Rm",
    "Zdroj:": "Source:",
    "Báze hodnot:": "Allowables basis:",
    "původ dat / specifikace": "data origin / specification",
    # knihovna profilů
    "Knihovna profilů": "Profile library",
    "Správa knihovny profilů: nový, duplikovat, upravit, smazat, pořadí":
        "Manage the profile library: new, duplicate, edit, delete, reorder",
    "Nový profil (obdélník – pak uprav)": "New profile (rectangle – then edit)",
    "Otevře editor průřezu": "Opens the cross-section editor",
    "Posunout v seznamu nahoru (pořadí se ukládá – seskup si např. trubky k sobě)":
        "Move up in the list (the order is saved – e.g. group tubes together)",
    "Uloží průřez z otevřeného projektu do knihovny":
        "Saves a cross-section from the open project into the library",
    "Změny se ukládají hned. Úprava knihovny nemění průřezy už zkopírované "
    "do projektů.":
        "Changes are saved immediately. Editing the library does not change "
        "cross-sections already copied into projects.",
    "Smazat profil „%s“ z uživatelské knihovny?\nProjekty, které ho už "
    "používají, mají vlastní kopii a nezmění se.":
        "Delete profile “%s” from the user library?\nProjects already using "
        "it keep their own copy and will not change.",
    "Nový profil": "New profile",
    "(projekt nemá průřezy)": "(project has no cross-sections)",
    "Upravit…": "Edit…",
    "(kopie)": "(copy)",
    "název profilu": "profile name",
    # osový posun / prodloužení
    "u – osový posun (prodloužení) [mm]": "u – axial displacement (elongation) [mm]",
    "u (osový posun) [mm]": "u (axial displacement) [mm]",
    "  celkové prodloužení ΔL: ": "  total elongation ΔL: ",
    # plasticita – vysvětlení
    "  α_pl v řídicím řezu: zadaná %s, uplatněná %s":
        "  α_pl at the critical section: entered %s, applied %s",
    "    (snížena interakcí se smykem / osovou silou – viz THEORY.md)":
        "    (reduced by shear / axial force interaction – see THEORY.md)",
    "    pozn.: řídí mez kluzu – α_pl ovlivňuje jen RF_ultimate":
        "    note: yield governs – α_pl affects RF_ultimate only",
    # varování na nulovou kombinaci
    "Kombinace „%s“ nezahrnuje žádné zatížení (všechny faktory 0) "
    "– otevři ⊞ Load Cases a nastav faktory.":
        "Combination “%s” includes no load (all factors are 0) – open "
        "⊞ Load Cases and set the factors.",
    # záložka výsledky + zobrazení
    "Výsledky": "Results",
    "Schéma (zadání + reakce)": "Scheme (input + reactions)",
    "Zobrazit průhyb a pootočení": "Show deflection and rotation",
    "deformovaný tvar": "deformed shape",
    "Všechny veličiny jsou nulové": "All quantities are zero",
}


def tr(s: str) -> str:
    if SETTINGS.language == "en":
        return EN.get(s, s)
    return s
