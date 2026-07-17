# BEAMER 1.32 — theory, assumptions and limits of validity

This document is part of the computational model. It describes what the program
actually solves, which conventions it uses and when a result must not be taken
as a structural assessment.

## Units and signs

Internal units are mm, N and MPa (= N/mm²). Tensile axial force `N` is
positive. The global beam axis is `x`; `w/Fz/My` form the x–z plane and
`v/Fy/Mz` the x–y plane. Torsion is `Mx`, the torsional rotation `theta`.
Positive `My` (sagging) puts the top fibre in compression. Exports always state
the unit in the column header.

## Beam solver

An element has 6 DOF per node: `[u, w, ry, v, rz, rx]`. Bending uses
Euler–Bernoulli or Timoshenko theory according to the project setting. An
unsymmetric section includes the `EIyz` coupling. Axial and Saint-Venant
torsional stiffnesses are `EA` and `GJ`.

An internal hinge releases both bending moments. The stiffness and the
consistent load vector are condensed by the same static condensation; the
released DOF is reconstructed during recovery. A loaded unrestrained axial or
torsional rigid-body mode is a mechanism and the solver rejects it. A reference
zero DOF is added only to an unloaded rigid-body mode, where it produces no
reaction.

Supports have explicit 3D options `restrain_y`, `restrain_rz` and
`restrain_torsion`; a spring may have `spring_z`, `spring_y`, `spring_ry` and
`spring_rz`. A value of `None` keeps the historical semantics of the support
type.

## Cross-section and stress

Normal stress uses the full biaxial relation with `Iy`, `Iz`, `Iyz`. Vertical
and horizontal transverse shear use Zhuravskii's formula. Shear from transverse
force and torsion is combined conservatively by summing magnitudes (no full
joint 2D vector field yet); the result is invariant to the sign of the torque.
The reduced stress is von Mises.

The plastic shape factor `Wpl/Wel` is applied only to pure uniaxial bending.
For axial force, shear, torsion, biaxial or combined loading the factor stays
1.0 until a full plastic interaction is implemented and validated.

A direct `Iy` import from `.nos` is a stiffness model only. The synthetic
outline may be used for display, never for stress, RF or buckling. Those
results are marked as unavailable until real geometry is entered.

## Composites and temperature

A composite uses `EA = ΣEiAi` and the principal values of the matrix
`[[EIy, EIyz], [EIyz, EIz]]`. Euler buckling and the bifurcation check
therefore keep the true E-weighted `EI`. The Johnson branch uses an equivalent
section and the compressive capacity `ΣFcy,i Ai`; a missing `Fcy` is explicitly
substituted by `Re`.

Thermal resultants are integrated per material: `∫E alpha T dA` and
`∫E alpha T (z-zNA) dA`. This holds for a uniform change as well as a linear
gradient between the top and bottom fibre. The composite assessment includes
the corresponding self-stress.

## Stability

Phase 1 uses the Johnson–Euler curve and the smaller principal moment of
inertia, not a naive `min(Iy, Iz)`. Phase 2 solves the linear eigenvalue
problem `(Kb + lambda Kg)q=0`. This is a linear bifurcation of an ideal member
without imperfections, residual stresses, local buckling and material
nonlinearity. The beam-column check is an elastic interaction; it does not
replace the code interaction equation of a specific structure.

## Section FEM and fallbacks

A general polygon uses an adaptive T6/T10 Saint-Venant analysis and stores an
error estimate, the final element order and a failure reason if any. When the
composite stress field fails, the B1 fallback is flagged `b1_fallback` in the
result including the reason; shear is not assessed in this mode and the UI
warns about it.

## Loads, materials and allowables

`LoadCase.is_ultimate=True` means an already factored ULS load; the global
`additional_factor` is not applied to it again. For a non-ULS case it is
applied.

The built-in library contains nominal values, not guaranteed A/B-basis
allowables. The `source` and `allowables_basis` fields therefore explicitly
state "Legacy BEAMER nominal library" and the requirement to verify against the
governing specification. For a certification calculation the user must enter
approved data including `Fcy`/`Fsu`.

## Core references

- S. P. Timoshenko, J. M. Gere: *Theory of Elastic Stability*.
- W. C. Young, R. G. Budynas: *Roark's Formulas for Stress and Strain*.
- W. D. Pilkey: *Analysis and Design of Elastic Beams*.
- V. Z. Vlasov: *Thin-Walled Elastic Beams*.
- E. F. Bruhn: *Analysis and Design of Flight Vehicle Structures*.

A numerical claim is not considered verified merely by matching a golden
snapshot. The regressions contain analytic invariants and external
comparisons; the exact verified dependency versions are in
`requirements-lock.txt` and CI tests them on Python 3.11 and 3.13.
