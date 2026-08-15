#!/usr/bin/env python3
"""Aggregate deterministic JPFM-2F-B3S tile shards and evaluate the frozen B3 gates once."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jpfm_2f_b2_tile_lineage_replay as b2

EXPECTED_SAMPLE_N = 64
EXPECTED_TILES = 52
FROZEN_SHARD_COUNT = 4


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def quantiles(series) -> dict:
    a = pd.to_numeric(series, errors="coerce").to_numpy(float)
    a = a[np.isfinite(a)]
    if not len(a):
        return {"n_finite": 0}
    return {
        "n_finite": int(len(a)),
        "min": float(np.min(a)),
        "p05": float(np.quantile(a, 0.05)),
        "median": float(np.median(a)),
        "p95": float(np.quantile(a, 0.95)),
        "max": float(np.max(a))
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--shards-dir", required=True, type=Path)
    ap.add_argument("--plan", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--out-sidecar-gz", required=True, type=Path)
    args = ap.parse_args()
    args.out_json.parent.mkdir(parents=True, exist_ok=True)

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    if plan.get("status") != "PREREGISTERED_AFTER_B3_WALLCLOCK_TIMEOUT_WITHOUT_B3_OUTCOME__BEFORE_B3S_OUTCOME":
        raise RuntimeError("B3S execution plan status mismatch")
    if int(plan["sharding_contract"]["shard_count"]) != FROZEN_SHARD_COUNT:
        raise RuntimeError("B3S frozen shard-count mismatch")
    plan_sha256 = sha256_bytes(args.plan.read_bytes())

    print("[B3S aggregate] [1/7] reconstruct exact frozen expected sample", flush=True)
    manifest, s0 = b2.load_inputs(args.manifest)
    expected = b2.select_same_64(manifest)
    expected = expected.merge(
        s0[["src_id", "tile_id", "object_id", "ra", "dec", "plate_id"]],
        on="src_id", validate="one_to_one"
    )
    expected_src = set(expected.src_id.astype(str))
    expected_tiles = sorted(expected.tile_id.astype(str).unique())
    if len(expected_src) != EXPECTED_SAMPLE_N or len(expected_tiles) != EXPECTED_TILES:
        raise RuntimeError("frozen expected sample invariants failed")
    expected_assignment = {tid: i % FROZEN_SHARD_COUNT for i, tid in enumerate(expected_tiles)}

    print("[B3S aggregate] [2/7] verify shard receipts, hashes and deterministic partition", flush=True)
    receipt_paths = sorted(args.shards_dir.glob("JANUS-PALOMAR-JPFM-2F-B3S-SHARD-*-RECEIPT-RUN-001.json"))
    if len(receipt_paths) != FROZEN_SHARD_COUNT:
        raise RuntimeError(f"expected {FROZEN_SHARD_COUNT} shard receipts, got {len(receipt_paths)}")

    receipts = []
    frames = []
    seen_indices = set()
    seen_tiles = set()
    receipt_digests = []
    for rp in receipt_paths:
        r = json.loads(rp.read_text(encoding="utf-8"))
        idx = int(r["shard"]["index"])
        if idx in seen_indices or not 0 <= idx < FROZEN_SHARD_COUNT:
            raise RuntimeError("duplicate/invalid shard index")
        seen_indices.add(idx)
        if int(r["shard"]["count"]) != FROZEN_SHARD_COUNT:
            raise RuntimeError("shard-count receipt mismatch")
        if r.get("status") != "EXECUTED_SHARD_RECEIPT__NO_GLOBAL_OUTCOME":
            raise RuntimeError("shard receipt status mismatch")
        if r["external_label_firewall"]["external_label_reveal_authorized"] is not False:
            raise RuntimeError("external-label firewall violation")
        payload = dict(r)
        integ = payload.pop("integrity", None)
        if not integ or canonical_sha(payload) != integ.get("canonical_payload_sha256_without_integrity"):
            raise RuntimeError(f"receipt canonical hash mismatch: {rp.name}")
        receipt_digests.append(integ["canonical_payload_sha256_without_integrity"])

        assigned = [str(x) for x in r["shard"]["assigned_tiles"]]
        expected_for_idx = [t for t in expected_tiles if expected_assignment[t] == idx]
        if assigned != expected_for_idx or len(assigned) != 13:
            raise RuntimeError(f"shard {idx} tile assignment differs from frozen plan")
        if seen_tiles.intersection(assigned):
            raise RuntimeError("cross-shard tile overlap")
        seen_tiles.update(assigned)

        sp = args.shards_dir / str(r["sidecar"]["path"])
        if not sp.exists():
            raise RuntimeError(f"missing shard sidecar {sp.name}")
        gz = sp.read_bytes()
        if sha256_bytes(gz) != r["sidecar"]["gzip_sha256"]:
            raise RuntimeError(f"shard gzip hash mismatch {idx}")
        raw = gzip.decompress(gz)
        if sha256_bytes(raw) != r["sidecar"]["csv_sha256"]:
            raise RuntimeError(f"shard CSV hash mismatch {idx}")
        df = pd.read_csv(io.BytesIO(raw))
        if len(df) != int(r["sidecar"]["rows"]):
            raise RuntimeError(f"shard row count mismatch {idx}")
        if set(df.tile_id.astype(str)) - set(assigned):
            raise RuntimeError(f"shard sidecar contains out-of-shard tile {idx}")
        if not (pd.to_numeric(df.b3s_shard_index, errors="coerce") == idx).all():
            raise RuntimeError(f"shard sidecar index mismatch {idx}")
        frames.append(df)
        receipts.append(r)

    if seen_indices != set(range(FROZEN_SHARD_COUNT)) or seen_tiles != set(expected_tiles):
        raise RuntimeError("shard partition is incomplete")

    print("[B3S aggregate] [3/7] exact-union source integrity", flush=True)
    audit = pd.concat(frames, ignore_index=True)
    got_src = list(audit.src_id.astype(str))
    if len(got_src) != EXPECTED_SAMPLE_N or len(set(got_src)) != EXPECTED_SAMPLE_N:
        raise RuntimeError("aggregate must contain exactly 64 unique source rows")
    if set(got_src) != expected_src:
        missing = sorted(expected_src - set(got_src))
        extra = sorted(set(got_src) - expected_src)
        raise RuntimeError(f"aggregate src_id mismatch missing={missing[:5]} extra={extra[:5]}")

    # One deterministic status per tile.
    tile_status = audit[["tile_id", "tile_identity_reconstructed", "tile_detection_status"]].copy()
    for tid, g in tile_status.groupby("tile_id"):
        if g.tile_identity_reconstructed.astype(str).nunique() != 1 or g.tile_detection_status.astype(str).nunique() != 1:
            raise RuntimeError(f"inconsistent per-source tile receipt for {tid}")
    tile_status = tile_status.drop_duplicates("tile_id")
    if len(tile_status) != EXPECTED_TILES:
        raise RuntimeError("aggregate distinct-tile count mismatch")

    print("[B3S aggregate] [4/7] evaluate frozen B3 gates", flush=True)
    tile_identity_rows = int(audit.tile_identity_reconstructed.astype(bool).sum())
    tile_identity_pass = tile_identity_rows == EXPECTED_SAMPLE_N and bool(tile_status.tile_identity_reconstructed.astype(bool).all())
    detection_tiles_pass = int((tile_status.tile_detection_status.astype(str) == "PASS").sum())
    detection_fraction = detection_tiles_pass / EXPECTED_TILES
    detection_pass = detection_fraction >= 0.95

    exact = audit.exact_object_status.astype(str).eq("EXACT_NUMBER_RECOVERED")
    exact_n = int(exact.sum())
    exact_frac = exact_n / EXPECTED_SAMPLE_N
    object_pass = exact_frac >= 0.90

    sep = pd.to_numeric(audit.get("pass2_to_s0_sep_arcsec"), errors="coerce")
    sep_exact = sep[exact & np.isfinite(sep)].to_numpy(float)
    sep_le10_frac = float((sep_exact <= 10.0).mean()) if len(sep_exact) else 0.0
    sep_pass = sep_le10_frac >= 0.90

    raw_cols = ["pass2_fwhm_image", "pass2_elongation", "pass2_spread_model"]
    if exact_n:
        raw = audit.loc[exact, raw_cols].apply(pd.to_numeric, errors="coerce").to_numpy(float)
        raw_morph_frac = float(np.isfinite(raw).all(axis=1).mean())
    else:
        raw_morph_frac = 0.0
    raw_morph_pass = raw_morph_frac >= 0.95

    shape_failed = pd.to_numeric(audit.get("shape_failed"), errors="coerce").fillna(1).astype(int)
    shape_success_exact = exact & shape_failed.eq(0)
    shape_success_n = int(shape_success_exact.sum())
    shape_success_frac = shape_success_n / exact_n if exact_n else 0.0
    shape_pass = shape_success_frac >= 0.90

    if not (tile_identity_pass and detection_pass):
        outcome = "FAIL_CLOSED_TILE_OR_DETECTION_REPLAY"
    elif not (object_pass and sep_pass):
        outcome = "FAIL_CLOSED_OBJECT_LINEAGE"
    elif not raw_morph_pass:
        outcome = "FAIL_CLOSED_RAW_MORPHOLOGY"
    elif not shape_pass:
        outcome = "FAIL_CLOSED_SHAPE_COMPATIBILITY_REPAIR"
    else:
        outcome = "PASS_SHAPE_COMPATIBILITY_REPLAY__PIXEL_MORPHOLOGY_PILOT_ADMITTED"

    print("[B3S aggregate] [5/7] verify compatibility patch identity across shards", flush=True)
    original_hashes = {r["compatibility_repair"]["original_sha256"] for r in receipts}
    repaired_hashes = {r["compatibility_repair"]["repaired_sha256"] for r in receipts}
    metric_changed = {bool(r["compatibility_repair"]["metric_formula_changed"]) for r in receipts}
    if len(original_hashes) != 1 or len(repaired_hashes) != 1 or metric_changed != {False}:
        raise RuntimeError("compatibility patch differs across shards")

    print("[B3S aggregate] [6/7] freeze aggregate sidecar", flush=True)
    audit = audit.sort_values(["structural_cluster", "sample_role", "src_id"], kind="stable").reset_index(drop=True)
    sidecar_csv = audit.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode("utf-8")
    sidecar_csv_sha = sha256_bytes(sidecar_csv)
    with args.out_sidecar_gz.open("wb") as fout:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fout, mtime=0) as gz:
            gz.write(sidecar_csv)
    sidecar_gz_sha = sha256_bytes(args.out_sidecar_gz.read_bytes())

    print("[B3S aggregate] [7/7] write single global outcome", flush=True)
    result = {
        "artifact_id": "JANUS-PALOMAR-JPFM-2F-B3S-SHARD-AGGREGATE-RUN-001",
        "experiment_id": "JPFM-2F-B3S",
        "schema_version": "1.0",
        "date": pd.Timestamp.utcnow().date().isoformat(),
        "status": "EXECUTED_AND_SHARD_INTEGRITY_VERIFIED",
        "outcome": outcome,
        "claim_ceiling": "SHARDED_EXECUTION_OF_FROZEN_PIXEL_MORPHOLOGY_MEASUREMENT_PILOT_ONLY__EXTERNAL_LABELS_SEALED__NO_CAUSAL_OR_ORIGIN_CLAIM",
        "bindings": {
            "execution_plan_path": str(args.plan),
            "execution_plan_sha256": plan_sha256,
            "B3_admission_path": "data/JANUS-PALOMAR-JPFM-2F-B3-SHAPE-COMPATIBILITY-REPLAY-ADMISSION-v1.0.json",
            "B2_result_path": "data/JANUS-PALOMAR-JPFM-2F-B2-TILE-LINEAGE-REPLAY-RUN-001.json",
            "poss_commit": b2.POSS_COMMIT,
            "structural_manifest_csv_sha256": b2.MANIFEST_CSV_SHA256,
            "structural_manifest_gzip_sha256": b2.MANIFEST_GZ_SHA256
        },
        "shard_integrity": {
            "gate_pass": True,
            "shard_count": FROZEN_SHARD_COUNT,
            "receipt_canonical_sha256": receipt_digests,
            "distinct_tiles_union": int(len(seen_tiles)),
            "tile_overlap_count": 0,
            "source_rows_union": int(len(audit)),
            "source_ids_unique": int(audit.src_id.astype(str).nunique()),
            "source_union_equals_frozen_same64": True
        },
        "sample": {
            "rows": EXPECTED_SAMPLE_N,
            "distinct_tiles": EXPECTED_TILES,
            "distinct_plates": int(expected.plate_id.nunique()),
            "same_as_B1_B2_B3": True
        },
        "tile_and_detection": {
            "tile_identity_rows": tile_identity_rows,
            "tile_identity_pass": tile_identity_pass,
            "required_distinct_tiles": EXPECTED_TILES,
            "detection_tiles_pass": detection_tiles_pass,
            "detection_pass_fraction": detection_fraction,
            "detection_gate_pass": detection_pass,
            "detection_status_census": {str(k): int(v) for k, v in tile_status.tile_detection_status.value_counts(dropna=False).items()}
        },
        "object_lineage": {
            "exact_NUMBER_recovered": exact_n,
            "exact_NUMBER_fraction": exact_frac,
            "exact_NUMBER_gate_pass": object_pass,
            "pass2_to_S0_sep_le10_fraction": sep_le10_frac,
            "sky_consistency_gate_pass": sep_pass,
            "pass2_to_S0_sep_arcsec": quantiles(sep[exact])
        },
        "raw_pass2_morphology": {
            "finite_FWHM_ELONGATION_SPREAD_fraction_among_exact": raw_morph_frac,
            "gate_pass": raw_morph_pass,
            "FWHM_IMAGE_px": quantiles(audit.loc[exact, "pass2_fwhm_image"]),
            "ELONGATION": quantiles(audit.loc[exact, "pass2_elongation"]),
            "SPREAD_MODEL": quantiles(audit.loc[exact, "pass2_spread_model"]),
            "SNR_WIN": quantiles(audit.loc[exact, "pass2_snr_win"])
        },
        "repaired_shape_stage": {
            "shape_success_exact": shape_success_n,
            "shape_success_fraction_among_exact": shape_success_frac,
            "gate_pass": shape_pass,
            "per_shard_returncodes": [int(r["execution"]["shape_returncode"]) for r in sorted(receipts, key=lambda x: int(x["shard"]["index"]))],
            "failure_reason_census": {str(k): int(v) for k, v in audit.loc[exact & ~shape_success_exact, "failure_reason"].fillna("MISSING").value_counts().items()} if exact_n else {},
            "profile_diff": quantiles(audit.get("profile_diff", pd.Series(dtype=float))),
            "circularity": quantiles(audit.get("circularity", pd.Series(dtype=float))),
            "shape_defect": quantiles(audit.get("shape_defect", pd.Series(dtype=float))),
            "circle_deviation": quantiles(audit.get("circle_deviation", pd.Series(dtype=float))),
            "stars_used": quantiles(audit.get("stars_used", pd.Series(dtype=float)))
        },
        "compatibility_repair": {
            "original_upstream_shape_sha256": next(iter(original_hashes)),
            "repaired_shape_sha256": next(iter(repaired_hashes)),
            "metric_formula_changed": False
        },
        "external_label_firewall": {
            "external_label_reveal_authorized": False,
            "date_or_external_environment_used": False
        },
        "sidecar": {
            "path": str(args.out_sidecar_gz),
            "rows": int(len(audit)),
            "csv_sha256": sidecar_csv_sha,
            "gzip_sha256": sidecar_gz_sha
        },
        "next_gate": (
            "JPFM_2F_C_LABEL_BLIND_PIXEL_MORPHOLOGY_SIDECAR_SCALEOUT"
            if outcome == "PASS_SHAPE_COMPATIBILITY_REPLAY__PIXEL_MORPHOLOGY_PILOT_ADMITTED"
            else "REPAIR_REMAINING_MEASUREMENT_FAILURE_WITHOUT_EXTERNAL_LABEL_REVEAL"
        )
    }
    result["integrity"] = {"canonical_payload_sha256_without_integrity": canonical_sha(result)}
    args.out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("OUTCOME", outcome, flush=True)
    print(
        "EXACT_NUMBER", exact_n,
        "RAW_MORPH_FRAC", raw_morph_frac,
        "SHAPE_SUCCESS", shape_success_n,
        "SHAPE_SUCCESS_FRAC", shape_success_frac,
        flush=True
    )
    print("SIDECAR_CSV_SHA256", sidecar_csv_sha, flush=True)
    print("RESULT_CANONICAL_SHA256", result["integrity"]["canonical_payload_sha256_without_integrity"], flush=True)


if __name__ == "__main__":
    main()
