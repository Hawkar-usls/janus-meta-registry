#!/usr/bin/env python3
"""
wedjat_lambda_probe.py

A reproducible mathematical/computational probe of the six values commonly
listed with the Wedjat / Eye-of-Horus diagram:

    1/2, 1/4, 1/8, 1/16, 1/32, 1/64

The script separates three questions:

1) Mathematics:
   Are these values a geometric progression?  Yes: lambda = 1/2.

2) Binary representation:
   What do the six values look like as binary fixed-point place values?

3) Image geometry:
   On the supplied modern infographic, do the *drawn glyph sizes themselves*
   shrink geometrically by lambda = 1/2?  This is tested only as an image-level
   hypothesis; it is NOT an archaeological claim.

No claim of an ancient hidden binary/Python encoding is made.
"""

from __future__ import annotations

from fractions import Fraction
from functools import reduce
from operator import or_
from pathlib import Path
import argparse
import math


PARTS = [
    ("smell",   Fraction(1, 2)),
    ("sight",   Fraction(1, 4)),
    ("thought", Fraction(1, 8)),
    ("hearing", Fraction(1, 16)),
    ("taste",   Fraction(1, 32)),
    ("touch",   Fraction(1, 64)),
]


def fixed_binary_from_power_of_two_fraction(frac: Fraction, places: int = 6) -> str:
    """Return exact binary fixed-point form for the fractions used here."""
    bits = []
    value = frac
    for _ in range(places):
        value *= 2
        if value >= 1:
            bits.append("1")
            value -= 1
        else:
            bits.append("0")
    if value != 0:
        raise ValueError("More binary places are required for exact representation.")
    return "0." + "".join(bits)


def math_probe() -> None:
    print("=== MATHEMATICAL / BINARY PROBE ===")
    values = [f for _, f in PARTS]

    ratios = [values[i + 1] / values[i] for i in range(len(values) - 1)]
    print("successive ratios:", ", ".join(str(r) for r in ratios))
    print("lambda:", ratios[0])

    print("\nSix fixed-point binary basis positions:")
    scaled_weights = []
    for name, frac in PARTS:
        binary = fixed_binary_from_power_of_two_fraction(frac, 6)
        weight = int(frac * 64)
        scaled_weights.append(weight)
        print(f"{name:7s} {str(frac):>4s} = {binary}_2   *64 -> {weight:2d} = {weight:06b}")

    total = sum(values, Fraction(0, 1))
    missing = Fraction(1, 1) - total
    print("\nExact sum:", total)
    print("Binary sum: 0.111111_2")
    print("Missing to 1:", missing)
    print("Missing binary: 0.000001_2")
    print("Completion: 0.111111_2 + 0.000001_2 = 1.000000_2")

    mask_or = reduce(or_, scaled_weights, 0)
    mask_sum = sum(scaled_weights)
    print("\nScaled-by-64 bit weights:", scaled_weights)
    print(f"bitwise OR = {mask_or} = 0b{mask_or:06b}")
    print(f"arithmetic sum = {mask_sum} = 0b{mask_sum:06b}")
    print(f"plus one missing unit = {mask_sum + 1} = 0b{mask_sum + 1:07b}")

    # Deliberately labelled as a modern/arbitrary interpretation.
    raw_byte = mask_sum.to_bytes(1, "big")
    ascii_char = raw_byte.decode("ascii")
    print("\nOptional modern byte interpretation only:")
    print(f"0b00{mask_sum:06b} = 0x{mask_sum:02X} = ASCII {ascii_char!r}")
    print("This is an encoding choice, not evidence of an ancient ASCII message.")

    # Demonstrate why a byte does not magically become valid Python source.
    try:
        compile(ascii_char, "<raw-wedjat-byte>", "exec")
        valid = True
        err = None
    except SyntaxError as exc:
        valid = False
        err = f"{exc.__class__.__name__}: {exc.msg}"
    print("Raw ASCII byte as Python source valid?:", valid)
    if err:
        print("Python parser result:", err)


def fit_lambda_from_measurements(values):
    """Fit y_k = C * lambda^k in log-space. Returns lambda and R^2."""
    n = len(values)
    xs = list(range(n))
    ys = [math.log(float(v)) for v in values]
    xbar = sum(xs) / n
    ybar = sum(ys) / n
    denom = sum((x - xbar) ** 2 for x in xs)
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denom
    intercept = ybar - slope * xbar
    predicted = [intercept + slope * x for x in xs]
    ss_res = sum((y - p) ** 2 for y, p in zip(ys, predicted))
    ss_tot = sum((y - ybar) ** 2 for y in ys)
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 1.0
    return math.exp(slope), r2


def unicode_probe() -> None:
    """
    Modern Unicode layer.

    Unicode encodes the complete udjat eye at U+13080 and the six following
    Egyptian-hieroglyph characters at U+13081..U+13086.  This is a MODERN
    character encoding layer, not evidence that ancient Egyptians used binary.
    """
    print("\n=== MODERN UNICODE / UTF-8 LAYER ===")
    cps = list(range(0x13080, 0x13087))
    labels = ["whole-eye", "1/2", "1/4", "1/8", "1/16", "1/32", "1/64"]
    for label, cp in zip(labels, cps):
        ch = chr(cp)
        data = ch.encode("utf-8")
        byte_hex = " ".join(f"{b:02X}" for b in data)
        byte_bits = " ".join(f"{b:08b}" for b in data)
        print(
            f"{label:9s} U+{cp:05X} {ch}  "
            f"UTF-8=[{byte_hex}]  bits={byte_bits}"
        )

    fraction_glyphs = "".join(chr(cp) for cp in range(0x13081, 0x13087))
    print("six fraction glyphs as a Python Unicode string:", repr(fraction_glyphs))
    print("code-point offsets from U+13080:",
          [ord(ch) - 0x13080 for ch in fraction_glyphs])

def image_probe(path: Path) -> None:
    """
    Probe the six black glyphs in the right-hand column of the supplied image.

    This uses normalized crop coordinates derived from the supplied 1023x675
    infographic, so resizing the same image should still work reasonably well.
    """
    try:
        from PIL import Image
    except ImportError:
        print("\n[PIL/Pillow not installed: skipping image probe]")
        return

    im = Image.open(path).convert("L")
    w, h = im.size

    # Right-column glyph zone, normalized from the supplied image.
    x0 = round(580 / 1023 * w)
    x1 = round(770 / 1023 * w)

    # Six y bands, normalized from the supplied image.
    bands_ref = [
        (28, 98),
        (130, 192),
        (233, 289),
        (332, 408),
        (442, 532),
        (545, 650),
    ]
    bands = [(round(a / 675 * h), round(b / 675 * h)) for a, b in bands_ref]

    pixels = im.load()
    threshold = 80
    rows = []

    for (name, frac), (y0, y1) in zip(PARTS, bands):
        coords = []
        for y in range(max(0, y0), min(h, y1)):
            for x in range(max(0, x0), min(w, x1)):
                if pixels[x, y] < threshold:
                    coords.append((x, y))
        if not coords:
            rows.append((name, frac, 0, 0, 0, 0.0))
            continue

        xs = [p[0] for p in coords]
        ys = [p[1] for p in coords]
        bw = max(xs) - min(xs) + 1
        bh = max(ys) - min(ys) + 1
        diag = math.hypot(bw, bh)
        rows.append((name, frac, len(coords), bw, bh, diag))

    areas = [r[2] for r in rows]
    diags = [r[5] for r in rows]

    print("\n=== IMAGE-GEOMETRY PROBE ===")
    print("Image:", path)
    print("This tests the modern infographic's drawn sizes, not ancient intent.")
    print(f"{'part':7s} {'fraction':>8s} {'black_px':>10s} {'bbox':>11s} {'diag':>9s}")
    for name, frac, area, bw, bh, diag in rows:
        print(f"{name:7s} {str(frac):>8s} {area:10d} {f'{bw}x{bh}':>11s} {diag:9.2f}")

    if all(v > 0 for v in areas):
        lam_area, r2_area = fit_lambda_from_measurements(areas)
        lam_diag, r2_diag = fit_lambda_from_measurements(diags)
        print("\nBest geometric-decay fit to black-pixel area:")
        print(f"lambda_hat = {lam_area:.6f}, R^2(log-space) = {r2_area:.4f}")
        print("Target lambda for repeated halving = 0.500000")
        print("\nBest geometric-decay fit to bounding-box diagonal:")
        print(f"lambda_hat = {lam_diag:.6f}, R^2(log-space) = {r2_diag:.4f}")
        print("Target lambda for repeated halving = 0.500000")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--image",
        type=Path,
        help="Optional path to the supplied Wedjat infographic for pixel-geometry probe.",
    )
    args = parser.parse_args()

    math_probe()
    unicode_probe()
    if args.image:
        image_probe(args.image)


if __name__ == "__main__":
    main()
