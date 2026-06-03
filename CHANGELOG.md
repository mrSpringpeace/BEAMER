# Changelog

Version format: **X.XX**

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
