# BEAMER 1.41 — theory, assumptions and limits of validity

This document is part of the computational model. It states what BEAMER
actually solves, the conventions it uses, and when a result must not be treated
as a structural assessment.

## Units and signs

Internal units are mm, N and MPa (= N/mm²). Tensile axial force `N` is positive.
The beam axis is `x`; `w/Fz/My` form the x–z plane and `v/Fy/Mz` the x–y plane.
Torsion is `Mx` and twist is `theta`. Positive sagging `My` compresses the top
fibre. Exported columns always state their units.

## Beam solver

The default element has six DOF per node: `[u, w, ry, v, rz, rx]`. Bending uses
Euler–Bernoulli or Timoshenko theory. Unsymmetric sections include `EIyz`
coupling; axial and Saint-Venant torsional stiffnesses are `EA` and `GJ`.

An internal hinge releases both bending moments. Stiffness and consistent load
vectors are condensed together and the released DOF is reconstructed during
recovery. A loaded unrestrained axial or torsional rigid-body mode is a
mechanism and is rejected. A reference zero DOF is added only to an unloaded
rigid-body mode, where it creates no reaction.

Supports expose `restrain_y`, `restrain_rz` and `restrain_torsion`; springs may
define `spring_z`, `spring_y`, `spring_ry` and `spring_rz`. `None` preserves the
historical semantics of the support type.

### Restrained warping (Vlasov)

The default **Saint-Venant** option preserves the original 6-DOF `GJ` model.
The optional **Vlasov** model adds a seventh nodal DOF `theta'` and uses cubic
Hermite interpolation for `theta`. Its 14×14 element follows from

    U = 1/2 ∫ [GJ·(theta')² + EIomega·(theta'')²] dx.

BEAMER uses the internal convention

    T_SV = GJ·theta'
    T_w  = -EIomega·theta'''
    Mx   = T_SV + T_w
    B    = +EIomega·theta''.

Literature using the opposite sectorial-coordinate sign may write
`B=-EIomega·theta''`; the physical stress product is unchanged. Section stress
is assembled at the same point:

    sigma_w = (B/Iomega)·omega
    tau_w   = (T_w/Iomega)·grad(chi).

`omega` is the normalized FEM sectorial coordinate and `chi` the secondary
warping-shear function. A multi-material section integrates
`EIomega=∫E(y,z)·omega² dA` and uses local `E(y,z)` for normal warping stress.

Warping can be released or restrained at each support. For legacy `None`, a
fixed support restrains it and other supports release it. Vlasov mode always
requests an exact FEM section because analytical `Iomega` fallbacks are not
adequate for this stiffness. Closed/solid sections and numerically vanishing
`Iomega` reduce exactly to the original Saint-Venant block.

The analytical regression is a cantilever with
`theta(0)=theta'(0)=0`, free end bimoment and end torque `T`:

    theta(L) = T/GJ · [L - tanh(alpha·L)/alpha],
    alpha = sqrt(GJ/EIomega).

The model is linear elastic with piecewise-constant element properties. It does
not include nonlinear torsion, cross-section distortion or interaction between
local buckling and warping. A point torque is supported; distributed torsional
loading has no dedicated editor input.

## Cross-section stress

Normal stress uses the full biaxial relation with `Iy`, `Iz` and `Iyz`. Reduced
stress is von Mises. Transverse shear has two selectable models:

- **Legacy/conservative** (default): vertical and horizontal shear use
  Zhuravskii `tau=VQ/(Ib)` and are combined with torsional shear by summing
  magnitudes. Despite its name, it can underpredict shear in thin-walled open
  profiles (verified by 34% for the validation I-section).
- **Exact 2D field**: Pilkey Ψ/Φ shear functions are solved by the section FEM.
  The actual vector is assembled pointwise as
  `tau_vec=Vz·t_vz + Vy·t_vy + (Mk/IT)·t_tor`; von Mises therefore uses normal
  and shear stress at the same point. The rectangle regression agrees with
  Zhuravskii within 0.02%. Parameterized sections require `exact=True`.

### Re-entrant corner radii

An ideal sharp re-entrant web/flange corner in I/T/L/U profiles is an elastic
singularity: peak FEM shear grows with mesh refinement and a reserve factor
would become mesh-dependent. Real sections have a radius. Parameter `r` models
that radius; `r=0` and a missing legacy key mean the old sharp corner and cause
a warning in exact-shear mode. With a physical radius the solution converges.

### Plastic shape factor

`Wpl/Wel` is used only for uniaxial bending and only in `RF_ultimate`;
`RF_yield` is first-fibre yield. With `R_v=tau_V/tau_allow`, where `tau_allow`
is `Fsu` or the fallback `Rm/sqrt(3)`, the effective factor is

    alpha_eff = 1 + (alpha-1)·(1-(R_v/0.25)²)  for R_v < 0.25
    alpha_eff = 1                              otherwise.

Axial force, torsion and biaxial bending disable the plastic factor until a
validated full interaction model exists.

A direct `Iy` import from `.nos` is a stiffness-only model. Its synthetic
outline may be displayed but must not be used for stress, RF or buckling; those
results remain unavailable until real geometry is supplied.

## Importing real section geometry

Text import creates a polygon in mm from `y,z` pairs. Blank lines or
`OUTER`/`HOLE`/`BODY` delimit outlines, holes and separate bodies. A loop must
have at least three distinct points and nonzero area, may not self-intersect or
touch another boundary, and an explicit hole must lie inside its outer loop.
Ambiguous geometry is rejected rather than healed.

IGES/IGS import is a limited planar-curve converter following
[NISTIR 88-3813](https://nvlpubs.nist.gov/nistpubs/Legacy/IR/nbsir88-3813.pdf).
It supports circular arc 100, copious-data polyline 106, line 110 and rational
B-spline 126, plus model units and transformation matrix 124. Curves are
discretized before polygon analysis and must join into closed planar loops.
Open, intersecting, non-planar, unsupported-unit or otherwise invalid input
fails loudly. This is not CAD healing or a general IGES kernel.

After import the result is an ordinary `polygon` and uses the same FEM theory,
fallbacks and limitations as hand-entered geometry. File origin is not proof of
axis orientation, scale or structural relevance; check the preview and at least
`A`, `Iy` and `Iz`.

## Composites and temperature

Composite stiffness uses `EA=ΣEiAi` and the principal values of
`[[EIy,EIyz],[EIyz,EIz]]`. Euler buckling and eigenvalue buckling preserve the
actual E-weighted stiffness. Johnson uses an equivalent section and compression
capacity `ΣFcy,i Ai`, falling back explicitly from missing `Fcy` to `Re`.

Thermal resultants integrate `∫E alpha T dA` and
`∫E alpha T (z-zNA) dA` per material for uniform temperature and linear
through-depth gradients. Composite assessment includes the corresponding
self-equilibrating stress.

## Stability

Phase 1 uses Johnson–Euler with the smaller principal inertia, not simply
`min(Iy,Iz)`. Phase 2 solves the linear eigenproblem `(Kb+lambda Kg)q=0`.
It is ideal-member linear bifurcation without imperfections, residual stress,
local buckling or material nonlinearity. Beam-column assessment is an elastic
interaction, not a code-specific design equation.

### Local wall buckling

Local stability is separate from global member buckling and is available only
for parameterized I/T/L/U/C/box sections with known wall connectivity. Each wall
has width `b`, thickness `t`, centerline and supported/supported (`SS`) or
supported/free (`SF`) longitudinal edges. Generic polygons, direct-property
sections and composites are unavailable because an outline does not determine
joint stiffness or support conditions.

The elastic critical stress is

    sigma_cr,el = k·pi²E/[12(1-nu²)]·(t/b)².

For an SS wall BEAMER minimizes the exact Navier expression

    k = min_m (m/alpha + alpha/m)²,  alpha=a/b.

For an SF wall it solves the plate characteristic eigenproblem and retains the
aspect-ratio dependency; the long-plate limit is `k=0.425`. Dimension `a` is the
actual transverse-support spacing, not automatically the beam-segment length.
Unless entered explicitly, a conservative long-plate ratio `a/b=20` is used.
Wall capacity is `min(sigma_cr,el,Fcy)`, falling back to `Re` when needed.

Compression demand is evaluated at the start, midpoint and end of each wall
centerline with the full biaxial stress; Vlasov `B·omega/Iomega` is included
when active. A tensile wall has no local RF. The method predicts elastic onset,
not tangent-modulus buckling, effective width/postbuckling, imperfections,
residual stress, holes or interaction with global buckling.

### Section crippling

Needham crippling for a constant-thickness angle is

    Fcs = Ce·sqrt(Fcy E)/(b'/t)^0.75,

where `b'=(a+b)/2` and `Ce=0.316/0.342/0.366` for two/one/no free edges. More
complex stringers require an explicit angle decomposition, so BEAMER applies
Needham only to a standalone L-section.

Gerard uses total area `A`, average thickness `t_av` and a section family:

    Fcs/Fcy = 0.56 [g t_av²/A·sqrt(E/Fcy)]^0.85   (L, box)
    Fcs/Fcy = 0.67 [g t_av²/A·sqrt(E/Fcy)]^0.4    (T, I)
    Fcs/Fcy = 3.2  [t_av²/A·(E/Fcy)^(1/3)]^0.75  (U/C).

Family-specific caps are 0.7 Fcy (L), 0.8 Fcy (I/T/box) and 0.9 Fcy (U/C).
When both methods apply, the lower capacity governs. No empirical extrapolation
is made below `min(b/t)=10`; thick sections are governed by material capacity.
Under bending, uniform-compression capacity is conservatively compared with the
largest wall compression. This is an aerospace thin-wall screening method, not
a substitute for tests or approved product curves.

Primary public sources and validation examples:

- Gerard and Becker, [*Handbook of Structural Stability, Part I — Buckling of
  Flat Plates*](https://ntrs.nasa.gov/search.jsp?R=19930084505), NACA-TN-3781.
- Gerard, [*Handbook of Structural Stability, Part IV — Failure of Plates and
  Composite Elements*](https://ntrs.nasa.gov/citations/19930084522),
  NACA-TN-3784.
- Graham, [*Preliminary Analysis Techniques for Ring and Stringer Stiffened
  Cylindrical Shells*](https://ntrs.nasa.gov/citations/19930013915),
  NASA-TM-108399.

## Section FEM and fallbacks

A generic polygon uses adaptive T6/T10 Saint-Venant analysis and records error
estimate, final element order and any failure reason. If the composite stress
field fails, the B1 fallback is explicitly marked with its reason; shear is not
assessed in that fallback and the UI warns the user.

## Loads, materials and allowables

Horizontal and vertical point/distributed loads use the same assembly and
recovery chain. `LoadCase.is_ultimate=True` means an already factored ULS load;
the global `additional_factor` is not applied again.

Built-in materials are nominal, not guaranteed A/B-basis allowables. `source`
and `allowables_basis` identify the legacy nominal library and the need to
verify against the controlling specification. Certification work must supply
approved values including `Fcy` and `Fsu` and independently verify the result.

## Core references and maintenance boundary

- Timoshenko and Gere: *Theory of Elastic Stability*.
- Young and Budynas: *Roark's Formulas for Stress and Strain*.
- Pilkey: *Analysis and Design of Elastic Beams*.
- Vlasov: *Thin-Walled Elastic Beams*.
- Bruhn: *Analysis and Design of Flight Vehicle Structures*.

A numerical claim is not validated merely because it matches a golden
snapshot. Regressions include analytical invariants and independent
comparisons; locked dependency versions are tested on Python 3.11 and 3.13.

Version 1.41 closes the planned straight-beam scope. New theory or a change to
the computational core requires a separate decision, an independent validation
anchor, explicit golden-drift review and an update to this document. Ordinary
maintenance may fix defects, dependency compatibility, documentation and minor
UX without expanding the physical model.
