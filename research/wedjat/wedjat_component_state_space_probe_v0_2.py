#!/usr/bin/env python3
"""JANUS Wedjat component/state-space probe v0.2.

This is a modern mathematical/computational experiment over the six values
commonly associated with a Wedjat fraction diagram:

    1/2, 1/4, 1/8, 1/16, 1/32, 1/64

The probe deliberately separates:
  * exact dyadic mathematics;
  * a modern six-bit state-space representation;
  * explicit Python source literals constructed from those bits;
  * a raw-byte/ASCII-to-Python negative control;
  * optional post-hoc robustness measurements on the supplied modern image.

It does NOT claim that ancient Egyptians used binary, ASCII, UTF-8, Python,
or that modern sensory labels are historically encoded by the mathematics.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import platform
import sys
from fractions import Fraction
from pathlib import Path
from typing import Iterable

VERSION = "v0.2"
PARTS = [
    {"label": "smell",   "fraction": Fraction(1, 2),  "glyph": "𓂁", "code_point": "U+13081"},
    {"label": "sight",   "fraction": Fraction(1, 4),  "glyph": "𓂂", "code_point": "U+13082"},
    {"label": "thought", "fraction": Fraction(1, 8),  "glyph": "𓂃", "code_point": "U+13083"},
    {"label": "hearing", "fraction": Fraction(1, 16), "glyph": "𓂄", "code_point": "U+13084"},
    {"label": "taste",   "fraction": Fraction(1, 32), "glyph": "𓂅", "code_point": "U+13085"},
    {"label": "touch",   "fraction": Fraction(1, 64), "glyph": "𓂆", "code_point": "U+13086"},
]


def qstr(x: Fraction) -> str:
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fixed_binary(frac: Fraction, places: int = 6) -> str:
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
        raise ValueError(f"fraction {frac} does not terminate in {places} binary places")
    return "0." + "".join(bits)


def subset_sum_from_bits(bits: str) -> Fraction:
    return sum(
        (p["fraction"] for bit, p in zip(bits, PARTS) if bit == "1"),
        Fraction(0, 1),
    )


def build_state_space() -> list[dict]:
    rows = []
    for mask in range(64):
        bits = f"{mask:06b}"
        frac = subset_sum_from_bits(bits)
        python_source = f"state = 0b{bits}\n"
        ns: dict[str, int] = {}
        compiled = compile(python_source, f"<wedjat-state-{mask}>", "exec")
        exec(compiled, {}, ns)
        rows.append({
            "mask_decimal": mask,
            "bits": bits,
            "fraction_sum": qstr(frac),
            "scaled_by_64": int(frac * 64),
            "active_parts": [p["label"] for bit, p in zip(bits, PARTS) if bit == "1"],
            "hamming_weight": bits.count("1"),
            "python_source": python_source.strip(),
            "python_exec_value": ns["state"],
            "python_exec_matches_mask": ns["state"] == mask,
        })
    return rows


def raw_ascii_python_control() -> dict:
    exec_valid = []
    eval_valid = []
    for n in range(64):
        ch = chr(n)
        try:
            compile(ch, f"<raw-byte-{n}>", "exec")
            exec_valid.append(n)
        except (SyntaxError, ValueError, TypeError):
            pass
        try:
            compile(ch, f"<raw-byte-{n}>", "eval")
            eval_valid.append(n)
        except (SyntaxError, ValueError, TypeError):
            pass
    return {
        "mapping_rule": "six-bit integer 0..63 interpreted directly as one ASCII code point",
        "mapping_is_modern_and_arbitrary": True,
        "exec_valid_count": len(exec_valid),
        "exec_valid_decimal_codes": exec_valid,
        "eval_valid_count": len(eval_valid),
        "eval_valid_decimal_codes": eval_valid,
        "eval_valid_printable_characters": [chr(n) for n in eval_valid],
        "full_mask_63_character": chr(63),
        "full_mask_63_character_repr": repr(chr(63)),
        "full_mask_63_valid_exec_source": 63 in exec_valid,
        "full_mask_63_valid_eval_source": 63 in eval_valid,
        "interpretation": (
            "Direct byte-to-source decoding does not yield a general Python language. "
            "The few accepted bytes are parser coincidences such as whitespace, '#', and digits."
        ),
    }


def leave_one_out_controls() -> list[dict]:
    out = []
    for removed_i, removed in enumerate(PARTS):
        kept = [p for i, p in enumerate(PARTS) if i != removed_i]
        sums = set()
        for mask in range(1 << len(kept)):
            bits = f"{mask:0{len(kept)}b}"
            total = sum(
                (p["fraction"] for bit, p in zip(bits, kept) if bit == "1"),
                Fraction(0, 1),
            )
            sums.add(total)
        out.append({
            "removed_label": removed["label"],
            "removed_fraction": qstr(removed["fraction"]),
            "unique_subset_sums": len(sums),
            "expected_for_five_independent_bits": 32,
            "maximum_sum": qstr(max(sums)),
            "complete_six_bit_grid_0_to_63_over_64": all(Fraction(i, 64) in sums for i in range(64)),
        })
    return out


def duplicate_weight_controls() -> dict:
    rows = []
    for replace_i, replaced in enumerate(PARTS):
        for source_i, source in enumerate(PARTS):
            if replace_i == source_i:
                continue
            vals = [p["fraction"] for p in PARTS]
            vals[replace_i] = vals[source_i]
            sums = set()
            for mask in range(64):
                bits = f"{mask:06b}"
                total = sum((v for bit, v in zip(bits, vals) if bit == "1"), Fraction(0, 1))
                sums.add(total)
            rows.append({
                "replaced_label": replaced["label"],
                "replacement_weight_from_label": source["label"],
                "unique_subset_sums": len(sums),
                "collisions_present": len(sums) < 64,
            })
    counts = [r["unique_subset_sums"] for r in rows]
    return {
        "cases": rows,
        "case_count": len(rows),
        "all_cases_have_collisions": all(r["collisions_present"] for r in rows),
        "unique_subset_sum_count_range": [min(counts), max(counts)],
        "interpretation": "Replacing any one distinct dyadic place value with a duplicate destroys the 64-state collision-free basis.",
    }


def label_permutation_control() -> dict:
    labels = [p["label"] for p in PARTS]
    baseline = {subset_sum_from_bits(f"{mask:06b}") for mask in range(64)}
    checked = 0
    all_equal = True
    for perm in itertools.permutations(labels):
        relabelled = [dict(p, label=label) for p, label in zip(PARTS, perm)]
        sums = set()
        for mask in range(64):
            bits = f"{mask:06b}"
            total = sum(
                (p["fraction"] for bit, p in zip(bits, relabelled) if bit == "1"),
                Fraction(0, 1),
            )
            sums.add(total)
        checked += 1
        if sums != baseline:
            all_equal = False
            break
    return {
        "permutations_checked": checked,
        "expected_6_factorial": math.factorial(6),
        "all_numeric_state_spaces_equal_baseline": all_equal,
        "numeric_weights_changed": False,
        "interpretation": (
            "The binary/state-space result depends on the six numeric powers of two, "
            "not on which modern sensory label is attached to which position."
        ),
    }


def fit_lambda(values: Iterable[float]) -> tuple[float, float]:
    vals = list(values)
    n = len(vals)
    xs = list(range(n))
    ys = [math.log(float(v)) for v in vals]
    xbar = sum(xs) / n
    ybar = sum(ys) / n
    denom = sum((x - xbar) ** 2 for x in xs)
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denom
    intercept = ybar - slope * xbar
    pred = [intercept + slope * x for x in xs]
    ss_res = sum((y - p) ** 2 for y, p in zip(ys, pred))
    ss_tot = sum((y - ybar) ** 2 for y in ys)
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 1.0
    return math.exp(slope), r2


def image_robustness_probe(path: Path) -> dict:
    try:
        from PIL import Image
    except ImportError as exc:
        return {"status": "SKIPPED_PILLOW_NOT_INSTALLED", "error": str(exc)}

    im = Image.open(path).convert("L")
    w, h = im.size
    x0 = round(580 / 1023 * w)
    x1 = round(770 / 1023 * w)
    bands_ref = [(28, 98), (130, 192), (233, 289), (332, 408), (442, 532), (545, 650)]
    bands = [(round(a / 675 * h), round(b / 675 * h)) for a, b in bands_ref]
    thresholds = [40, 60, 80, 100, 120, 140, 160, 180, 200]
    px = im.load()
    sweeps = []
    for threshold in thresholds:
        areas = []
        diags = []
        boxes = []
        for y0, y1 in bands:
            coords = [
                (x, y)
                for y in range(max(0, y0), min(h, y1))
                for x in range(max(0, x0), min(w, x1))
                if px[x, y] < threshold
            ]
            if not coords:
                areas.append(0)
                diags.append(0.0)
                boxes.append(None)
                continue
            xs = [x for x, _ in coords]
            ys = [y for _, y in coords]
            bw = max(xs) - min(xs) + 1
            bh = max(ys) - min(ys) + 1
            areas.append(len(coords))
            diags.append(math.hypot(bw, bh))
            boxes.append([bw, bh])
        if not all(v > 0 for v in areas) or not all(v > 0 for v in diags):
            sweeps.append({"threshold": threshold, "status": "EMPTY_COMPONENT"})
            continue
        lam_area, r2_area = fit_lambda(areas)
        lam_diag, r2_diag = fit_lambda(diags)
        sweeps.append({
            "threshold": threshold,
            "areas_black_pixels": areas,
            "bbox_width_height": boxes,
            "lambda_hat_area": lam_area,
            "R2_log_area": r2_area,
            "lambda_hat_bbox_diagonal": lam_diag,
            "R2_log_bbox_diagonal": r2_diag,
        })

    valid = [r for r in sweeps if "lambda_hat_area" in r]
    area_lams = [r["lambda_hat_area"] for r in valid]
    diag_lams = [r["lambda_hat_bbox_diagonal"] for r in valid]
    return {
        "status": "POSTHOC_ROBUSTNESS_SWEEP_EXECUTED",
        "posthoc_not_preregistered": True,
        "image_path_basename": path.name,
        "image_sha256": sha256_path(path),
        "image_bytes": path.stat().st_size,
        "image_dimensions": [w, h],
        "crop_policy": {
            "reference_dimensions": [1023, 675],
            "x_reference": [580, 770],
            "y_bands_reference": bands_ref,
            "normalization": "linear scaling to actual image dimensions",
        },
        "thresholds": thresholds,
        "sweeps": sweeps,
        "lambda_target_repeated_halving": 0.5,
        "area_lambda_range": [min(area_lams), max(area_lams)],
        "bbox_diagonal_lambda_range": [min(diag_lams), max(diag_lams)],
        "any_area_lambda_within_0_10_of_half": any(abs(x - 0.5) <= 0.10 for x in area_lams),
        "any_bbox_diagonal_lambda_within_0_10_of_half": any(abs(x - 0.5) <= 0.10 for x in diag_lams),
        "interpretation": (
            "Across the threshold sweep, the drawn component sizes of this modern infographic do not behave "
            "like repeated geometric halving. This is an image-specific negative control, not an archaeological result."
        ),
    }


def build_result(image: Path | None) -> dict:
    values = [p["fraction"] for p in PARTS]
    ratios = [values[i + 1] / values[i] for i in range(5)]
    states = build_state_space()
    state_sums = {Fraction(row["scaled_by_64"], 64) for row in states}
    hamming_hist = {str(k): sum(row["hamming_weight"] == k for row in states) for k in range(7)}

    parts = []
    for i, p in enumerate(PARTS):
        frac = p["fraction"]
        weight = int(frac * 64)
        bits = f"{weight:06b}"
        python_src = f"part = 0b{bits}\n"
        ns: dict[str, int] = {}
        exec(compile(python_src, f"<wedjat-part-{i}>", "exec"), {}, ns)
        parts.append({
            "index": i,
            "label": p["label"],
            "glyph": p["glyph"],
            "code_point": p["code_point"],
            "fraction": qstr(frac),
            "binary_fixed_point": fixed_binary(frac),
            "scaled_by_64": weight,
            "one_hot_bits": bits,
            "python_source": python_src.strip(),
            "python_exec_value": ns["part"],
            "python_exec_matches_scaled_weight": ns["part"] == weight,
        })

    full = sum(values, Fraction(0, 1))
    script_path = Path(__file__).resolve()
    result = {
        "artifact_uuid": "JANUS-WEDJAT-COMPONENT-STATE-SPACE-RESULT-2026-08-15-v0.2",
        "version": VERSION,
        "node_type": "exact_dyadic_component_state_space_probe",
        "status": "SIX_BIT_STATE_SPACE_EXACT_IMAGE_HALVING_NOT_SUPPORTED",
        "execution_provenance": {
            "script_basename": script_path.name,
            "script_sha256": sha256_path(script_path),
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "exact_rational_arithmetic": True,
        },
        "input_model": {
            "parts": parts,
            "successive_ratios": [qstr(r) for r in ratios],
            "lambda_exact": qstr(ratios[0]),
            "all_successive_ratios_equal": len(set(ratios)) == 1,
        },
        "state_space": {
            "state_count": len(states),
            "unique_fraction_sums": len(state_sums),
            "exact_grid_complete_0_to_63_over_64": all(Fraction(i, 64) in state_sums for i in range(64)),
            "bijection_mask_equals_fraction_times_64": all(row["mask_decimal"] == row["scaled_by_64"] for row in states),
            "all_constructed_python_binary_literals_execute_exactly": all(row["python_exec_matches_mask"] for row in states),
            "hamming_weight_histogram": hamming_hist,
            "states": states,
        },
        "completion_and_carry": {
            "all_parts_sum": qstr(full),
            "all_parts_bits": "111111",
            "all_parts_scaled_by_64": int(full * 64),
            "missing_to_one": qstr(Fraction(1, 1) - full),
            "missing_binary_fixed_point": "0.000001",
            "carry_identity": "0b111111 + 0b000001 = 0b1000000",
            "carry_decimal": [63, 1, 64],
        },
        "controls": {
            "label_permutation": label_permutation_control(),
            "leave_one_out": leave_one_out_controls(),
            "duplicate_weight": duplicate_weight_controls(),
            "raw_ascii_to_python": raw_ascii_python_control(),
        },
        "image_geometry": image_robustness_probe(image) if image else {"status": "NOT_REQUESTED"},
        "epistemic_gate": {
            "six_value_dyadic_progression_lambda_half": True,
            "complete_modern_six_bit_subset_state_space": True,
            "constructed_python_binary_literal_roundtrip": True,
            "modern_sensory_labels_required_for_binary_result": False,
            "direct_raw_ASCII_decodes_to_general_Python": False,
            "modern_infographic_component_geometry_supports_lambda_half": False if image else None,
            "ancient_binary_encoding_established": False,
            "ancient_ASCII_encoding_established": False,
            "ancient_Python_or_programming_language_established": False,
            "historical_sensory_mapping_established_by_this_probe": False,
            "Linear_A_evidentiary_transfer": False,
        },
        "highest_admissible_claim": (
            "Under a modern exact-rational formalization, the six dyadic values form a collision-free six-bit basis: "
            "every subset maps bijectively to one value on the 0/64..63/64 grid and to one Python 0b000000..0b111111 integer literal. "
            "This structure depends on the distinct powers-of-two weights, not on the attached sensory labels. "
            "Directly interpreting the resulting integers as ASCII does not produce a general Python decoding."
        ),
    }
    if image:
        result["highest_admissible_claim"] += (
            " A post-hoc threshold robustness sweep of the supplied modern infographic also fails to support "
            "lambda=1/2 scaling in the drawn component sizes; that negative result is image-specific."
        )
    return result


def compact_result(result: dict) -> dict:
    states = result["state_space"]["states"]
    state_digest = hashlib.sha256(
        json.dumps(states, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    sweeps = result["image_geometry"].get("sweeps", [])
    threshold_summary = [
        {
            k: row[k]
            for k in (
                "threshold",
                "lambda_hat_area",
                "R2_log_area",
                "lambda_hat_bbox_diagonal",
                "R2_log_bbox_diagonal",
            )
            if k in row
        }
        for row in sweeps
    ]
    return {
        "artifact_uuid": result["artifact_uuid"],
        "version": result["version"],
        "node_type": result["node_type"],
        "status": result["status"],
        "execution_provenance": result["execution_provenance"],
        "input_model": result["input_model"],
        "state_space": {k: v for k, v in result["state_space"].items() if k != "states"},
        "state_space_examples": [states[i] for i in (0, 1, 2, 3, 7, 15, 31, 42, 63)],
        "state_space_full_table_generated_by": "research/wedjat/wedjat_component_state_space_probe_v0_2.py",
        "state_space_full_table_sha256_canonical_json": state_digest,
        "completion_and_carry": result["completion_and_carry"],
        "controls": {
            "label_permutation": result["controls"]["label_permutation"],
            "leave_one_out": result["controls"]["leave_one_out"],
            "duplicate_weight": {
                k: v for k, v in result["controls"]["duplicate_weight"].items() if k != "cases"
            },
            "raw_ascii_to_python": result["controls"]["raw_ascii_to_python"],
        },
        "image_geometry": {k: v for k, v in result["image_geometry"].items() if k != "sweeps"},
        "image_geometry_threshold_summary": threshold_summary,
        "epistemic_gate": result["epistemic_gate"],
        "highest_admissible_claim": result["highest_admissible_claim"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--compact", action="store_true", help="Write compact registry result without the full 64-row table.")
    args = ap.parse_args()

    result = build_result(args.image)
    persisted = compact_result(result) if args.compact else result
    text = json.dumps(persisted, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    summary = {
        "status": result["status"],
        "state_count": result["state_space"]["state_count"],
        "unique_fraction_sums": result["state_space"]["unique_fraction_sums"],
        "grid_complete": result["state_space"]["exact_grid_complete_0_to_63_over_64"],
        "python_roundtrip": result["state_space"]["all_constructed_python_binary_literals_execute_exactly"],
        "raw_ascii_eval_valid_count": result["controls"]["raw_ascii_to_python"]["eval_valid_count"],
        "image_status": result["image_geometry"]["status"],
        "image_area_lambda_range": result["image_geometry"].get("area_lambda_range"),
        "image_diag_lambda_range": result["image_geometry"].get("bbox_diagonal_lambda_range"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
