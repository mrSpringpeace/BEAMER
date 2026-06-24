# Changelog

Version format: **X.XX**

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
