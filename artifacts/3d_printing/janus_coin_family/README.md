# JANUS coin family — 3D-printing artifacts

This directory binds the original two-sided JANUS coin, the validated v2.5
gimbal/fidget record, visual QA renders, and their machine-readable validation
receipts.

## Included binary artifact

- `JANUS_Coin(4)_TOPOLOGY_PRESERVED_REGISTRY.3mf` is the user-supplied JANUS
  coin repacked for registry transport. Only vertex decimal serialization was
  normalized to `1e-6 mm`; topology and the triangle block are unchanged.
- Original uploaded container SHA-256:
  `69487a52f9b512cb7bfeade0727ecc54e2ca95907b9690bd296d6bc86b7e1346`
- Registry artifact SHA-256:
  `4d01cb3be463c1c597a8cdd73b16ba0fbb23d85967b1188fa7f773c95efe0a9d`

## JANUS Axle Coin v2.5

The validation receipt and front/back geometry QA images are included. The
printable v2.5 3MF is intentionally not committed to this public repository at
this gate. Its mechanism source identifies itself as **Orbit — Customizable
Name Gyro Fidget**, designer **Kike**, under the embedded MakerWorld **Standard
Digital File License**. Public redistribution of a derivative digital model
requires a separate permission decision.

Validated local artifact SHA-256:
`a8a67e86d07059480454a8a6f816afbc3c6bff69610a1179efe07c6c07fa948c`.

This is a distribution gate, not a geometry failure. The full mechanical and
container validation is recorded in:

- `data/JANUS-AXLE-COIN-TWO-SIDED-LAUREL-A1-v2.5.json`
- `JANUS_AXLE_COIN_TWO_SIDED_LAUREL_A1_INLINE_v2.5_validation.json`

## Claim discipline

Digital validation confirms package structure, topology checks, protected
interface invariance, and measured clearances. It does not substitute for a
successful physical print, support removal, or durability test.
