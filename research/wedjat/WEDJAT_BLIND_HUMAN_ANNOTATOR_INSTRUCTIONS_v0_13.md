# WEDJAT blind human anatomical annotation — v0.13

## Purpose

Mark visible anatomical/morphological components of anonymized Wedjat images without using object identity, date, period, glyph names, fractions, prior JANUS results, or another annotator's work.

## Independence

Work alone. Do not reverse-search the image, inspect hidden/private mappings, compare with another annotator, or consult the expected glyph correspondences. Submit your package before any discussion with the second annotator.

## Coordinate rule

Use the exact displayed source dimensions. Store integer pixel coordinates in the image's native coordinate system. Do not crop, mirror, rotate, rescale, denoise, sharpen, or alter contrast for annotation. UI zoom is allowed only if coordinates remain in original pixels.

## Components

1. `A1_EYEBROW_UPPER_EYE` — visible eyebrow/upper-eye element. Exclude suspension loops and external ornament.
2. `A2_HUMAN_EYE_CONTOUR` — principal human-eye-shaped contour. Exclude pupil/iris and lower falcon markings.
3. `A3_PUPIL` — visibly distinct central pupil/iris. If not visible, do not infer one from symmetry.
4. `A4_VERTICAL_FALCON_MARK` — predominantly vertical lower falcon-derived mark. Keep separate from the diagonal mark even if they touch.
5. `A5_DIAGONAL_FALCON_MARK` — diagonal lower facial mark extending toward the curl. Stop where the line clearly transitions into the spiral/curl.
6. `A6_SPIRAL_CURL` — curved/spiral terminal. Begin at the first clear tangent-to-curvature transition. If it cannot be separated, mark `NOT_SEPARABLE` rather than guessing.

## Visibility states

Use exactly one: `VISIBLE`, `PARTIAL`, `DAMAGED`, `OCCLUDED`, `NOT_SEPARABLE`, `ABSENT_OR_NOT_DEPICTED`, `UNSURE`.

## Representations

- A1: polyline; optional narrow polygon.
- A2: closed or near-closed contour polyline.
- A3: closed polygon or ellipse landmarks.
- A4/A5: centerline polyline plus approximate width in pixels.
- A6: centerline polyline.

Do not force a component to exist. A clean `ABSENT_OR_NOT_DEPICTED`, `NOT_SEPARABLE`, or `UNSURE` is scientifically preferable to a guessed trace.

## Submission freeze

Complete every image, set the three attestation booleans to `true`, and do not edit after submission. The coordinator must SHA-256 freeze both annotator packages before object identity, chronology, glyph targets, fraction labels, or similarity scores are unlocked.

## Claim boundary

This annotation records geometry only. It is not a translation, reading, fraction assignment, historical derivation, or hidden-text claim.
