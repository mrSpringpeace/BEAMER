# Changelog

Version format: **X.XX**

## 1.29
**Biaxial bending / spatial loading (solver 4 → 6 DOF).** A major core extension:
the beam can now be loaded in both transverse planes (not only vertically).
- **6 DOF per node** (u, w, θy, v, θz, θx) — a second bending plane x-y
  (stiffness EIz). **New loads:** `Fy` (horizontal transverse force) and `Mz`
  (moment about the z-axis). A planar problem (Fy=Mz=0) stays **unchanged**
  (byte-identical to the previous solver), so simple analyses aren't complicated.
- **Skew bending (Iyz coupling).** An unsymmetric/rotated section deflects
  sideways under a vertical load; the coupling of the two bending planes through
  the product of inertia Iyz is included both in the element stiffness and in the
  stress assessment. Validated by the physical equivalence "rotate the section by
  α vs rotate the load by −α" (deflection and stress invariant).
- **Biaxial stress into the RF.** The normal stress is evaluated at the section's
  true extreme fibres with the full unsymmetric-bending formula (My, Mz, Iy, Iz,
  Iyz) — the critical point is usually at a corner, not on the axis.
- **UI:** a transverse force can be entered by **its Fy/Fz components, or by
  magnitude and angle** (0° = straight down) — any direction around the beam,
  two-way linked. The internal-force diagrams show **both planes** (V_z/V_y,
  M_y/M_z, w/v); the horizontal curves appear only when non-zero. The schematic
  marks an out-of-plane force.

Note: a composite (multi-material) section is still assessed uniaxially; a
biaxial composite check, buckling about both axes and N+M interaction are planned
follow-ups.

## 1.28
Buckling, temperature, schematic and a rotation fix:
- **Column buckling — phase 2 (system bifurcation, eigenvalues).** Solves the
  generalized eigenproblem (K_b + λ·K_g)·φ = 0 in the transverse (weak) plane:
  K_b = bending stiffness about the weak axis EI_min, K_g = geometric stiffness
  from the actual axial-force distribution N(x) of the displayed combination.
  The smallest positive λ is the **critical load factor** (RF_buckling). The
  effective length (μ) **follows from the boundary conditions** — no manual
  estimate as in phase 1. The report (text and DOCX) gets a section with λ_cr,
  P_cr, μ_eff and a **buckling mode-shape figure**. Validated against three Euler
  cases (μ = 1.0 / 0.5 / 2.0). Computed only for the report export (the live tab
  stays fast). No moment interaction (N+M) yet.
- **Thermal load — phase 2: gradient through the section depth → bending.** A new
  "gradient ΔT" field (top-fibre minus bottom-fibre temperature) produces a
  thermal curvature κ = α·ΔT_grad/h and moment M = EI·κ. A simply supported beam
  bends freely (thermal camber, no stress); a statically indeterminate one
  develops stress from the restrained curvature.
- **The schematic draws loads in the context of the displayed combination.** Only
  loads with a non-zero factor in the active combination are shown, scaled by the
  factor × the additional factor (so the schematic matches the reactions). A
  **"across combinations"** toggle turns the filter off and shows all entered
  loads at their defined magnitude.
- **Fix: rotating a parametric section corrupted the shear center and Iω.** The
  scanline approximation is only valid in the natural orientation; for a rotated
  section (rectangle/circle/tube/I/T/L/U/C/direct) it ran on the rotated geometry
  → wrong shear center (y_SC hard-wired to 0) and Iω. It is now computed from an
  un-rotated twin and the shear-center vector is rotated (Iω and Wk are
  rotation-invariant). The beam result (internal forces/deflection/RF) was
  unaffected — only the Section-tab properties were fixed.

## 1.27

**Critical fix (wrong results for assemblies with a rotated PID):**
- **The section resolver cached the section by the `id()` of a transient copy.**
  When several segments referenced a PID with rotation/taper, `eff_defs`
  returned a temporary copy of the definition; after that copy was
  garbage-collected its `id()` could be reused for a neighbouring segment, so a
  **foreign section** was substituted into the cut → wrong (and
  non-deterministic) reserve factors. It surfaced with a profile rotated by 90°
  in the PID across two segments. The `id()`-based cache was removed; the
  resolver now builds the section directly. (The bug was also present in 1.26.)

New features (approved roadmap — quick wins):
- **Envelope over load combinations.** The core computes the internal-force and
  RF envelope across all combinations; the Load Case Builder gains an
  **Envelope plot** (min/max internal forces over combinations) and an
  **ENVELOPE** row with the worst RF.
- **Conservative envelope check** (hand-analysis style): sums the beam-wide
  maxima |N|, |V|, |M|, |Mk| into a single cut → an upper-bound RF. In the
  report export.
- **Column buckling (phase 1).** Johnson–Euler per compressed segment (weak axis
  I_min, buckling length L = μ·L_segment; μ is editable). RF_buckling in the
  report; evaluated over the N envelope.
- **Elastic supports and prescribed support behaviour.** New **spring** type
  (vertical stiffness k_z). For rigid supports, a vertical-bond choice:
  **rigid** / **clearance** (the node moves freely within ±g, then seats — a
  non-linear active-set contact) / **settlement** (a prescribed drop Δ).
- **Thermal load (phase 1):** uniform ΔT over a segment → equivalent axial
  forces, N corrected by −EA·α·ΔT. Thermal-expansion coefficient α in the
  material editor.
- **Distributed load from a curve:** paste `x, q` text (point pairs) → a
  piecewise-linear distributed load.
- **Direct section** with independently entered properties A, Iy, Iz, IT
  (no geometry — for tabulated/standard profiles).
- **Show/hide loads and supports** in the schematic (choices are remembered).
- **DOCX calculation report** (export for substantiation; schematic and
  diagram images).

UI:
- **Support panel on two rows** per support (1: number, x, type; 2:
  angle/stiffness/vertical bond + delete) — the six-column table was narrow and
  the controls cramped.
- Unit shown directly next to the support value (mm vs N/mm).

Internal (branch audit, fixes A1–A6):
- Thermal boundaries added to the discretisation (previously ~2.4 % N error at a
  ΔT boundary).
- Conservative check and buckling moved out of the live Results tab (export
  only) — the live tab stays fast.
- Buckling computed from the N envelope (not just the displayed combination).
- `composite_assess` takes the loading as a parameter (no state mutation).

## 1.26

UI and usability:
- **Fix: flashing small windows on project load.** `CollapsibleBox` called
  `content.setVisible()` before `content` had a parent, so it briefly became a
  standalone top-level window (then immediately hid) on every panel rebuild. The
  unsaved-changes confirmation was unrelated and worked correctly.
- **Save** (Ctrl+S) writes straight to the currently open file without a dialog;
  **Save As…** (Ctrl+Shift+S) always shows the dialog.
- **Demo beam** moved into the File menu (after Save As), separated by a divider.
- **A newly added or duplicated item** (section, PID, segment, load) now appears
  expanded in the panel.
- **Duplicate** for section, PID, segment and load (a copy with a new id right
  after the original, "(copy)" in the name; segment positions are recomputed).
- **The mouse wheel no longer changes values** in dropdowns (material, PID,
  type…). Scrolling the panel used to switch the selection by accident.
- **Construction/polygon editor: preview in the input frame.** The origin (0,0)
  is the axis cross where the entered y,z point; the resulting centroid is marked
  separately. Previously the preview was centroid-centered, so an entered
  position (e.g. a circle at 0,0) did not match the picture — it looked like a
  bug but was only a different frame.
- **New "Stress along the beam" tab** in the centre: the σ_red (von Mises)
  envelope on top and, below it, the σ (normal) and τ (shear) components that
  feed into it.

## 1.25

Fixes from a deep review of the computational core (findings N1–N9):

- **N1 (serious): bending sign in composite sections.** Per-material σ used the
  bending term with the opposite sign relative to the axial force (against the
  solver convention "positive M = tension at the bottom fibre"). Pure bending or
  a symmetric section leaves |σ| unchanged (which is why tests passed), but for
  N+M on an asymmetric composite one material came out non-conservative
  (measured up to −36 % σ, i.e. RF overestimated by ~55 %). Fixed in both the
  B1 path and the FEM field + regression test.
- **N3: composite σ is now evaluated at element corners** (they reach the
  extreme fibre) instead of centroids (~2 % underestimate); τ stays at the
  centroid (stable on the non-conforming mesh), von Mises pairs them per corner.
  σ_max now matches the exact fibre to machine precision.
- **N2: the composite-assessment fallback is no longer silent.** If the FEM
  field fails, the result carries a flag and the UI shows a warning
  ("normal σ only, τ=0") — previously shear vanished quietly under torque.
- **N6: the "conservative σ⊕τ" reduced-stress mode now applies to composites**
  (per material √(σ_max²+3τ_max²) from the peaks; it was ignored before).
- **N4: the composite mesh cache detects edits of polygon/boolean library
  profiles** (signature now covers polygon points/bodies/shapes; previously a
  stale GJ/τ survived until restart).
- **N7: composite shear stiffness is weighted**: GAs = ΣGᵢAᵢ·(As/A)
  (Timoshenko; previously one material's G × geometric As).
- **N5: the composition dialog no longer offers profiles without geometry**
  (the "direct input" type used to be silently dropped from the assembly).
- **N8: the per-segment critical-section table** takes material/type through
  the PID (previously inline segment fields → wrong material name).
- **N9: a position inside a gap between segments** maps to the nearest segment
  (previously always the last one).

63 tests.

## 1.24

- Composite sections – **full per-material von Mises** (completes the composite
  stress calculation): a composite PID is now assessed against the reduced stress
  from all components — normal σ (modulus-weighted), torsional shear τ_t and
  transverse shear τ_V, each separately per material, with the reserve factor (RF)
  taken from that material's own strength.
  - **Torsion:** effective stiffness (GJ)_eff via a variable-G Saint-Venant FEM
    (each mesh element carries its material's G); the solver uses it directly.
    Validated against sectionproperties (concentric rod-in-tube and an asymmetric
    bonded joint) and analytically.
  - **Torsional stress τ_t** from the warping field; **τ_V** from an
    E-weighted Jourawski formula (reduces to the classic one for a single material).
  - The Cross-section tab, RF-along-the-beam and the report show σ/τ/σ_red and RF
    per material.
  - Note: the mesh is non-conforming at material interfaces → stress is sampled at
    the element centroid (convergent; a few % at the interface on a very coarse
    mesh). `beamer/composite_fem.py`, `beamer/_fem.py` (variable-G warping).

## 1.23

- **Fix (RF along a beam with several segments):** the RF-along-the-beam
  assessment could cross segment boundaries when selecting the cross-section — for
  a beam with a step change in section, one segment could be evaluated through the
  neighbouring segment's section (e.g. the moment of a stiffer segment divided by
  the weaker segment's section modulus → falsely low RF and the wrong critical
  location; at the opposite boundary the reverse, an unsafely overestimated RF).
  The section and material are now always resolved at the actual position x and
  segment boundaries are never crossed. The single-section check (Cross-section
  tab) was already correct; the "segment RF ≠ global min RF" mismatch is gone.
  `reserves_along_beam`.

## 1.22

- Composite profiles with different materials (PID): a PID can be marked
  "Composite of profiles" and, in the composition dialog, assembled from ready
  profiles in the library (pick a section, material, position dy/dz, angle) with a
  live preview. The calculation is modulus-weighted (transformed section):
  EA=ΣEᵢAᵢ, neutral-axis position from the stiffnesses, EIy about the NA; the
  solver uses effective stiffnesses EA/EIy/GJ/GAs (single material unchanged).
  Stress and RF are assessed **per material** (Cross-section tab, RF along the
  beam, report). `beamer/composite.py`, `Property.composite_parts`,
  `Body.material_id`.
- Profile rotation (PID): a "Rotation [°]" field rotates the whole cross-section —
  Iy/Iz/Iyz, stress and the solver are all computed from the rotated shape
  (planar tool: uses the transformed Iy, ignores the biaxial Iyz coupling).
  `CrossSectionDef.rotation`, `Property.rotation`.
- Cross-validation against the sectionproperties library (dev-only, skipped on
  CI): rotation (Iy/Iz/Iyz) and the composite section (EA/EIy/neutral axis) match
  to machine precision.

## 1.21

- Layout: the centre of the window is now split into tabs **[Internal forces |
  Cross-section & stress]**. The Cross-section tab moved from the right panel into
  the centre, where it has more room for deeper evaluation (stress contours,
  composite materials – roadmap). The right panel keeps Results / Assessment (RF)
  / Report. The active-combination indicator (▶) also shows on the Cross-section
  tab. No change to calculations or the project format.
- Tests: +4 analytical benchmarks (cantilever with end moment, simply supported
  beam with a central point load, and the statically indeterminate propped
  cantilever + fixed-fixed beam under UDL — validating the direct stiffness
  method against closed-form solutions). 38 tests total.

## 1.20

- Fix: the skew-roller solver now does one step of iterative refinement. The
  penalty system is ill-conditioned and its residual depended on the LAPACK
  backend (the skew-roller test passed locally but failed on CI). Refinement
  drops the residual by orders of magnitude independently of the backend; the
  instability threshold for the penalty case was also loosened.
- Polygon editor: a new vertex can be inserted right after a chosen point (the
  "＋" button in the coordinate-table row) — it lands on the midpoint of the edge
  to the next point and can then be dragged. No more starting over when a point
  was forgotten. "+ Add point at end" stays.
- Ministatik (.rez) import is now offered at the section-type level — the type
  dropdown (Circle / Rectangle / Polygon / …) has an "Import from Ministatik
  (.rez)…" entry after the types, instead of a standalone button shown for every
  type. (Groundwork in place for future imports: text file, IGS.)

## 1.19

- Appearance: light / dark theme (Settings → Appearance: System / Light / Dark).
  Fixes unreadable text for users whose OS is in dark mode. The theme is applied
  via both QPalette and QSS (`beamer/gui/theme.py`, light/dark tokens), so even
  unstyled surfaces (left-panel fields, card backgrounds) are coloured. Charts
  are intentionally always light (even in dark mode) so they stay readable like
  an engineering drawing; only the surrounding chrome (panels, the tables on the
  Cross-section and Assessment tabs) darkens. The centre column (schema + force
  diagrams) stays light.
- The window title shows the current file name (Office-style): "file.json —
  BEAMER v1.19", with a "●" marker for unsaved changes.
- File menu → "Recent files" (last 8 projects) for quick reopening; stored in
  settings.
- The active displayed load combination is shown in the top bar (▶ name), in the
  Results tab header, and now also in the beam-schema title (centre panel), which
  is visible next to any right-hand tab — so the active combination is always in
  view.
- UI fixes: the splitter between the left panel and the centre is draggable again
  (removed the max-width cap, 6 px handle, non-collapsible panels); the A− / A+
  font-size buttons on the Results tab are wider so the text fits.
- Left panel – icon rail: the inputs are grouped into cards (Beam; Materials;
  Sections; PID properties; Segments; Supports & hinges; Loads; Control points &
  factors) switched by a thin vertical icon rail on the left
  (`beamer/gui/icons.py`). The collapsible boxes around top-level groups were
  dropped (the rail replaces them) — a group now shows a bold title and its
  content directly; per-item boxes (individual segments/loads/PIDs) and the
  Results-tab sections stay collapsible.
- Charts – engineering template: no top/right spines, inward ticks, a light
  major+minor grid, consistent fonts and theme-aware colours (light/dark).
  Annotation boxes and the beam schema follow the theme (legible on dark too).
  `plots.apply_chart_theme`, `theme.chart_rc`.

## 1.18

- Load Case Builder – combinations reworked: a combination is now defined by
  picking the individual loads that go into it (one table column per load, not
  per load case). Each load gets a factor (0 = not used, 1 = full, e.g.
  1.35/1.5). "+ All ×1" builds a combination with every load. Combination factors
  are keyed by load id; the solver falls back to the load-case id for backwards
  compatibility, and older projects are migrated automatically on load (a load
  case's factor is copied onto its loads). Columns refresh when loads change.
- Performance: `build_section` now has a content cache (definition signature +
  FEM flag), so the same geometry is not rebuilt repeatedly. Boolean
  (construction) and polygonal sections with the expensive FEM Saint-Venant
  solver were recomputed on every analysis and redraw (control points, segment
  selection), which made a boolean profile extremely slow. The FEM now runs once
  per geometry and is reused.

## 1.17

- Section editor – clearer boolean construction mode: the input panel and the
  preview are separated by a draggable splitter. The shapes editor uses the y
  axis (horizontal, previously "x") consistently with the preview axes (y, z),
  and a note explains that the y,z position is relative between shapes and the
  preview is centroid-referenced (so moving a single shape alone does not change
  the picture). The data key "x" is still accepted for backwards compatibility.
- Cross-section library: a new "Cross-sections (library)" group under Materials
  holds named sections reused across segments and PID properties (like the
  material library). Segments and PIDs pick a section from a dropdown (library +
  "(inline – custom)"); "Edit…" edits the effective section (a library section
  propagates everywhere), "→ library" promotes an inline section into the
  library. Deleting a referenced section is blocked. Fully backwards compatible
  (older projects keep their inline sections; no migration).
- PID properties (FEM pre-processor style): a named {material + section} under a
  number; a segment just selects a PID. Inline definitions remain for quick
  one-off segments.
- Boolean construction section: a new section type built from primitives
  (rectangle, circle) combined with union / difference / intersection. Requires
  the Shapely library.
- Distributed-load generator: replace a transverse force by a statically
  equivalent linear distributed load (trapezoid keeps resultant and moment –
  including the negative-end "see-saw" for an edge force; constant; triangle).
  Axial force and torque are kept as separate point loads. Separate window with
  a live q(x) preview.
- σ_red (von Mises) mode switch in the top bar: "exact max" (the true maximum
  over the section – the σ and τ peaks lie at different fibres and are not added)
  vs "conservative (σ⊕τ)" = √(σ_max²+3·τ_max²) for pins/bolts. The Cross-section
  tab now shows the fibre z at which σ and τ peak.
- Left panel: all groups are collapsible panels with a grey header; the
  expanded/collapsed state is remembered across projects and restarts. The total
  length was removed from the Beam group (it is derived from the segment
  lengths). The section-type dropdown shows all types without scrolling.
- Cross-section tab: the results table is split into collapsible sections
  (Cross-section properties, Stress at the section, Internal-force extremes,
  Whole-beam assessment); the diagrams and the section drawing are unchanged.

## 1.16

- Load Case Builder (a separate, non-modal window; the "Load Cases" button in
  the top bar): manage load cases and combinations (Σ factor × case) and read a
  summary table — one row per combination with columns for N/V/M/Mk/w extremes,
  σ_red max, RF min + x, reactions and control-point values. Export to CSV, copy
  to the clipboard (TSV for spreadsheets), "Show selected combination in the main
  window". Every load belongs to a case; "+ Cases ×1 (auto)" builds a unit
  combination per case. The solver evaluates any combination without mutating the
  state (`solve_beam(state, factors=…)`).
- Diagram peak x-coordinates shown to one decimal place (previously integer).
- Cross-section tab: smaller section drawing and diagrams, more room for the
  table.

## 1.15

- VVÚ diagram peak labels now also show the x-coordinate (value @ x).
- Top bar switch for the governing RF basis: min(Re,Rm) / Re / Rm (saved in the
  project, recomputed without re-solving).
- A material added to the project (custom or from the library) appears
  immediately in the per-segment material dropdowns (no restart needed).
- Materials selected from the library now show editable, pre-filled values — you
  can start from a default and just tweak it. The Materials group is collapsible.
- Beam scheme draws segments in alternating black / dark grey for readability.
- Results tab: A− / A+ buttons to change the font size.
- Assessment (RF) tab: more robust axis clipping (percentile of the governing
  curve + headroom) when minima/maxima are large.
- Report tab: the Max |V| / |M| / |Mk| buttons now cycle through the peaks of
  the quantity (repeated clicks) — easy to step from the support moment to the
  in-span maximum.
- Cross-section & stress tab: the assessment table now also lists the component
  stresses (normal σ, shear τ) next to σ_red; the small stress diagrams show a
  min/max legend.
- A control point exactly at a segment boundary now reports results for BOTH
  segments (same internal forces, but different section/material → different
  stress and RF, left and right) — in the Report and in the Cross-section tab
  selector.
- File Open/Save/Export dialogs remember the last used directory.
- Left panel: swapped the order of Control points and Factors.
- Build: clean `beamer.spec` (one-file BEAMER.exe) + `BUILD_EXE.bat`.

## 1.14

Results of an internal mathematics audit — corrections and refinements:

- **Fixed the torsion constant of a solid rectangle** (scanline path): the
  Saint-Venant formula had the sides swapped (c1·t·a³ instead of c1·a·t³),
  overestimating IT by up to (a/t)² — 4× for a 100×200 section. This affected
  the parametric rectangle and the no-SciPy fallback; the FEM path (polygons)
  was correct. Now matches Roark within 0.1 %.
- **Fixed the torsional shear stress τ_t**: previously a single open-thin-walled
  formula (Mk·t/IT) was used for all sections, underestimating the stress for
  tubes (up to ~125×), closed boxes (~10×) and solid circles. Now a per-type
  torsion model is used: circle/tube τ = Mk·R/J, closed box by Bredt
  τ = Mk/(2·Am·t), solid rectangle τ = Mk/(α·a·b²) (Roark), open profiles
  unchanged. A single shared implementation feeds both the point-stress
  evaluation and the assessment influence coefficients. Pure-bending results
  are unaffected.
- **Skew roller support**: a roller angle other than 0°/90° was silently
  treated as vertical. It is now constrained by a penalty spring along the
  roller normal n = (sin α, cos α); the reaction acts along the normal and
  global equilibrium holds.
- **Timoshenko interpolation**: deflection and rotation between nodes now use
  the Interdependent Interpolation Element (Reddy) consistent with the
  Timoshenko element; for Φ = 0 it reduces exactly to the Hermite functions
  (Euler–Bernoulli unchanged).
- **More robust instability detection**: near-singular systems (which LAPACK
  "solves" with garbage) are now caught by finiteness and residual checks;
  also fixed a crash in the singular-matrix error handler.
- **Test suite extended to 28 tests** (`beamer/tests/test_accuracy.py`):
  accuracy of IT (rectangle/circle/tube/I vs Roark and analytics), τ_t per
  torsion model, σ = M/W, τ = 1.5·V/A, point-moment reactions, Gerber hinge,
  equilibrium, 45° skew roller, exact Timoshenko UDL, instability reporting.
- Documented modelling assumptions in the manual: scalar summation of shear
  components in von Mises (conservative on flanges), Iω/shear centre of
  parametric profiles as estimates (FEM for polygons only), α_pl as a
  pure-bending heuristic, composite J = Σ Jᵢ.

## 1.13

- **Verification test suite** (`beamer/tests/test_verification.py`, pytest):
  results are checked against closed-form solutions — cantilever / simply
  supported / fixed-fixed beams (deflection and moment), torsion (θ = Mk·L/GJ),
  Timoshenko vs Euler–Bernoulli, and the stress sign convention. Run with
  `python -m pytest beamer/tests/ -v` (pytest is listed in requirements-dev.txt).
  Internal forces and deflections match the analytical solutions to machine
  precision.
- **Stress sign convention fix:** bending stress σ now follows physics — a
  sagging moment (M > 0) gives compression on the top fibre and tension on the
  bottom fibre (previously inverted). This affects the stress diagram and the
  signed σ values. The assessment (von Mises σ_red and RF) is independent of the
  sign of σ, so the reserve factors are unchanged.

## 1.12

- **Shared library (materials & profiles):** in addition to the per-user library
  (`~/.beamer/`), you can set a **shared folder** in Settings (e.g. a network
  drive). The “From library” menus then show separate **Shared** / **User**
  sections, so the global and local databases never clash. Saving goes to the
  user library; writing to the shared one is done via **Publish** with a double
  confirmation (so it is never changed by accident). If the shared path is empty
  or unreachable, the app keeps working with the user library only.
- **Control points:** optional sections (x coordinate + name) added in the left
  panel. They are drawn as markers on the beam scheme and their results
  (N, V, M, Mk, deflection, σ, τ, von Mises, RF) are listed in the Results tab
  and both exports (text report and a dedicated CSV table). They do not affect
  the analysis — adding one only refreshes the report, no recompute.
- The text report (Results tab + TXT export) is now localized — it follows the
  selected language (previously it was always Czech).

## 1.11

- **Unsaved-work protection:** actions that would discard the current project
  (New, Open, Demo beam, or closing the app) now prompt to save when there are
  unsaved changes — Save / Don't save / Cancel. No prompt for a fresh, unmodified
  project.
- VVÚ diagrams: max/min value labels no longer overlap the chart title (added
  top headroom on the y-axis).
- The beam scheme and the result curves are now visually aligned — same drawing
  margins and x-range, so the beam start/end line up with the curve start/end,
  with minimal empty space on the left.
- Fixed a 1.10 regression where the live preview (scheme + cross-section) did not
  refresh after editing inputs.

## 1.10

### Cross-sections
- Fixed the hollow rectangle (RHS / box): it is now represented as one body with
  a rectangular hole (continuous outline, hole actually cut out). Area and
  moments of inertia from Green's theorem; torsion constant *IT* from
  Bredt–Batho (closed thin-walled).
- Circle and tube previews now draw a proper outline (filled `Circle` /
  `Annulus` with edge), instead of edgeless slice shading.

### New: Report tab
- A new **Report** tab shows values at any chosen section *x*: internal forces
  (N, V, M, Mk, deflection, rotations), the cross-section at *x* (type, A, Iy,
  IT), stresses (σ, τ, von Mises) and reserve factors. The coordinate can be
  typed in, or jumped to characteristic sections via buttons: max |V|, max |M|,
  max |Mk| and the most critical section (min RF).

### Export
- Export of result curves to **CSV** (File → Export curves (CSV)…): N, V, M, Mk,
  deflection and rotation curves plus the reactions table, in one file.
  Engineering format (comma separator, decimal point). Resolution is optional —
  the default is the full solver resolution; a lower count is resampled by
  linear interpolation.

### Docs
- Added [BUILD_EXECUTABLE.md](BUILD_EXECUTABLE.md) — how to package a standalone
  `.exe` with PyInstaller.

## 1.09

First public release.

### Beam analysis
- Beam solver — direct stiffness method (4 DOF per node: *u*, *w*, *φ*, *θ*),
  handles statically indeterminate beams; Euler–Bernoulli / Timoshenko theory.
- Internal forces *N*, *V*, *M*, *Mk*, deflection *w* and rotation *φ* with
  extrema marked; diagrams can be shown separately or combined into one graph.
- Segment-based model: each segment has its own length, material (library
  reference) and cross-section, including tapered transitions. Per-segment
  *E*, *G* and material strengths.

### Cross-sections
- Parametric library: rectangle, hollow rectangle (RHS), circle, tube (CHS),
  I, T, L, U/C, plus a section defined directly by *Iy*.
- Arbitrary **polygonal** sections with an interactive editor (draw + coordinate
  table), pan / wheel-zoom, per-vertex coordinate labels.
- **Composite (multi-body)** sections — multiple separate bodies, each with its
  own outline and any number of holes; evaluated as one section. The preview
  shows the whole assembly with holes actually cut out.
- Accurate properties: *A*, *Iy*, *Iz*, *Iyz* from Green's theorem (signed sum
  over outlines and holes of all bodies); *IT*, *Iω*, shear center and effective
  shear areas from a FEM Saint-Venant solver (T6 triangles). For composite
  sections the FEM runs per body and the results are combined.
- Section moduli for hand checks: Wb,y = Iy/iy, Wb,z = Iz/iz, Wt = IT/it.
- Plasticity shape factor α_pl = Wpl/Wel (analytic or tabular), applied to the
  ultimate reserve.

### Stress & assessment
- Normal and shear stress, von Mises equivalent stress, stress profiles across
  the section height.
- Reserve factor (RF) along the whole beam: RF_yield = Re/σ, RF_ultimate = Rm/σ,
  RF = min of the two (RF ≥ 1 passes). Adaptive clipping of the RF axis when
  values get very large.

### Files & UI
- JSON project save/load, text report and PNG diagram export.
- Material library (aerospace alloys and steel) with custom materials.
- Bilingual UI (English / Czech), number format options.
- Computation on demand (worker thread + progress bar); inputs update the
  schematic preview in real time.
