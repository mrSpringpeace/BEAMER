# Changelog

Version format: **X.XX**

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
