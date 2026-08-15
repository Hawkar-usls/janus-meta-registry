#!/usr/bin/env python3
"""Aggregate JPFM-2F-C0M header-only plate shards into the frozen full-S0 acquisition map."""
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

EXPECTED_ROWS = 122820
SHARD_COUNT = 16
REQUIRED_OUTPUT_COLUMNS = [
    "src_id", "tile_id", "object_id", "plate_id", "ra", "dec",
    "structural_cluster", "anomaly_score", "tile_x0", "tile_y0",
    "fullplate_x0", "fullplate_y0", "local_pixel_scale_arcsec",
    "tile_section_x_start_fullplate", "tile_section_y_start_fullplate",
    "tile_width_px", "tile_height_px", "distance_to_tile_edge_px",
    "tan_refit_median_arcsec", "tan_refit_max_arcsec", "crpix_dx", "crpix_dy"
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def qstats(vals) -> dict:
    a = pd.to_numeric(pd.Series(vals), errors="coerce").to_numpy(float)
    a = a[np.isfinite(a)]
    if not len(a):
        return {"n_finite": 0}
    return {
        "n_finite": int(len(a)), "min": float(np.min(a)),
        "p01": float(np.quantile(a, 0.01)), "p05": float(np.quantile(a, 0.05)),
        "median": float(np.median(a)), "p95": float(np.quantile(a, 0.95)),
        "p99": float(np.quantile(a, 0.99)), "max": float(np.max(a))
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--admission", required=True, type=Path)
    ap.add_argument("--c0h-result", required=True, type=Path)
    ap.add_argument("--shards-dir", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--out-manifest-gz", required=True, type=Path)
    args = ap.parse_args()
    args.out_json.parent.mkdir(parents=True, exist_ok=True)

    print("[C0M aggregate] [1/7] bind preregistration and admitted C0H parent", flush=True)
    admission = json.loads(args.admission.read_text(encoding="utf-8"))
    if admission.get("status") != "PREREGISTERED_AFTER_C0H_PASS_BEFORE_C0M_OUTCOME":
        raise RuntimeError("C0M admission status mismatch")
    if int(admission["sharding_contract"]["shard_count"]) != SHARD_COUNT:
        raise RuntimeError("C0M shard count differs from preregistration")
    admission_sha = sha256_bytes(args.admission.read_bytes())

    c0h = json.loads(args.c0h_result.read_text(encoding="utf-8"))
    if c0h.get("outcome") != "PASS_HEADER_ONLY_TILE_WCS_EQUIVALENCE":
        raise RuntimeError("C0M parent C0H is not admitted PASS")
    if c0h["transport_contract"]["remote_image_section_accessed"] is not False or c0h["transport_contract"]["remote_image_array_materialized"] is not False:
        raise RuntimeError("C0M parent no-pixel contract violated")
    c0h_sha = sha256_bytes(args.c0h_result.read_bytes())

    print("[C0M aggregate] [2/7] reconstruct frozen expected full S0 union", flush=True)
    structural, s0 = b2.load_inputs(args.manifest)
    expected_src = set(s0.src_id.astype(str))
    expected_plates = sorted(s0.plate_id.astype(str).unique())
    expected_tiles = set(s0.tile_id.astype(str))
    if len(s0) != EXPECTED_ROWS or len(expected_src) != EXPECTED_ROWS:
        raise RuntimeError("frozen S0 expected-union invariant failed")
    if structural.src_id.astype(str).nunique() != EXPECTED_ROWS:
        raise RuntimeError("frozen structural manifest source invariant failed")
    plate_assignment = {p: i % SHARD_COUNT for i, p in enumerate(expected_plates)}

    print("[C0M aggregate] [3/7] verify all shard receipts, assignments and hashes", flush=True)
    receipt_paths = sorted(args.shards_dir.glob("JANUS-PALOMAR-JPFM-2F-C0M-SHARD-*-RECEIPT-RUN-001.json"))
    if len(receipt_paths) != SHARD_COUNT:
        raise RuntimeError(f"expected {SHARD_COUNT} C0M receipts, got {len(receipt_paths)}")
    frames = []
    receipts = []
    seen_indices = set()
    seen_plates = set()
    receipt_digests = []
    for rp in receipt_paths:
        r = json.loads(rp.read_text(encoding="utf-8"))
        idx = int(r["shard"]["index"])
        if idx in seen_indices or not 0 <= idx < SHARD_COUNT:
            raise RuntimeError("duplicate/invalid C0M shard index")
        seen_indices.add(idx)
        if r.get("status") != "EXECUTED_SHARD_RECEIPT__NO_GLOBAL_OUTCOME" or int(r["shard"]["count"]) != SHARD_COUNT:
            raise RuntimeError("C0M shard receipt status/count mismatch")
        if r["external_label_firewall"]["external_label_reveal_authorized"] is not False:
            raise RuntimeError("C0M external-label firewall violation")
        if r["execution"]["remote_image_section_accessed"] is not False or r["execution"]["remote_image_array_materialized"] is not False:
            raise RuntimeError("C0M pixel transport violation")
        payload = dict(r); integ = payload.pop("integrity", None)
        if not integ or canonical_sha(payload) != integ.get("canonical_payload_sha256_without_integrity"):
            raise RuntimeError(f"C0M receipt canonical hash mismatch {rp.name}")
        receipt_digests.append(integ["canonical_payload_sha256_without_integrity"])

        assigned = [str(x) for x in r["shard"]["assigned_plates"]]
        expected_for_idx = [p for p in expected_plates if plate_assignment[p] == idx]
        if assigned != expected_for_idx:
            raise RuntimeError(f"C0M shard {idx} deterministic plate assignment mismatch")
        if seen_plates.intersection(assigned):
            raise RuntimeError("C0M cross-shard plate overlap")
        seen_plates.update(assigned)

        sp = args.shards_dir / str(r["sidecar"]["path"])
        if not sp.exists():
            raise RuntimeError(f"missing C0M shard sidecar {sp.name}")
        gz = sp.read_bytes(); raw = gzip.decompress(gz)
        if sha256_bytes(gz) != r["sidecar"]["gzip_sha256"] or sha256_bytes(raw) != r["sidecar"]["csv_sha256"]:
            raise RuntimeError(f"C0M shard sidecar hash mismatch {idx}")
        df = pd.read_csv(io.BytesIO(raw))
        if len(df) != int(r["sidecar"]["rows"]) or df.src_id.astype(str).duplicated().any():
            raise RuntimeError(f"C0M shard sidecar row/unique invariant failed {idx}")
        if set(df.plate_id.astype(str)) - set(assigned):
            raise RuntimeError(f"C0M shard sidecar has out-of-shard plate {idx}")
        frames.append(df); receipts.append(r)

    if seen_indices != set(range(SHARD_COUNT)) or seen_plates != set(expected_plates):
        raise RuntimeError("C0M plate partition union incomplete")

    print("[C0M aggregate] [4/7] exact 122,820 source/tile union integrity", flush=True)
    full = pd.concat(frames, ignore_index=True)
    got_src = full.src_id.astype(str)
    source_integrity = len(full) == EXPECTED_ROWS and got_src.nunique() == EXPECTED_ROWS and set(got_src) == expected_src
    plate_integrity = set(full.plate_id.astype(str)) == set(expected_plates)
    tile_integrity = set(full.tile_id.astype(str)) == expected_tiles
    if not (source_integrity and plate_integrity and tile_integrity):
        missing = len(expected_src - set(got_src)); extra = len(set(got_src) - expected_src)
        raise RuntimeError(f"C0M exact union failed missing={missing} extra={extra}")

    print("[C0M aggregate] [5/7] evaluate frozen global mapping gates", flush=True)
    plate_failures = sum(int(r["execution"]["plate_failure_count"]) for r in receipts)
    active_models = sum(int(r["shard"]["active_tile_models_built"]) for r in receipts)
    expected_active_tiles = len(expected_tiles)
    mapped = full.map_status.astype(str).eq("HEADER_ONLY_MAPPED")
    finite_cols = ["tile_x0", "tile_y0", "fullplate_x0", "fullplate_y0", "local_pixel_scale_arcsec"]
    numeric = full[finite_cols].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    finite_rows = np.isfinite(numeric).all(axis=1)
    edge = pd.to_numeric(full.distance_to_tile_edge_px, errors="coerce").to_numpy(float)
    in_bounds = np.isfinite(edge) & (edge >= 0.0)

    binding_pass = source_integrity and plate_integrity
    header_tile_pass = plate_failures == 0 and active_models == expected_active_tiles and tile_integrity
    coverage_pass = bool(mapped.all()) and bool(finite_rows.all())
    bounds_pass = bool(in_bounds.all())
    if not binding_pass:
        outcome = "FAIL_CLOSED_STRUCTURAL_OR_PLATE_BINDING"
    elif not header_tile_pass:
        outcome = "FAIL_CLOSED_HEADER_OR_TILE_IDENTITY"
    elif not (coverage_pass and bounds_pass):
        outcome = "FAIL_CLOSED_PREDICTION_COVERAGE_OR_BOUNDS"
    else:
        outcome = "PASS_FULL_S0_HEADER_ONLY_ACQUISITION_MAP_FROZEN"

    print("[C0M aggregate] [6/7] freeze compact full acquisition manifest", flush=True)
    missing_cols = [c for c in REQUIRED_OUTPUT_COLUMNS if c not in full.columns]
    if missing_cols:
        raise RuntimeError(f"C0M output missing required columns: {missing_cols}")
    full_out = full[REQUIRED_OUTPUT_COLUMNS].copy().sort_values("src_id", kind="stable").reset_index(drop=True)
    csv_bytes = full_out.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode("utf-8")
    csv_sha = sha256_bytes(csv_bytes)
    with args.out_manifest_gz.open("wb") as fout:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fout, mtime=0) as z:
            z.write(csv_bytes)
    gz_sha = sha256_bytes(args.out_manifest_gz.read_bytes())

    print("[C0M aggregate] [7/7] write global result", flush=True)
    result = {
        "artifact_id": "JANUS-PALOMAR-JPFM-2F-C0M-FULL-S0-HEADER-ONLY-ACQUISITION-MAP-RUN-001",
        "experiment_id": "JPFM-2F-C0M",
        "schema_version": "1.0",
        "date": pd.Timestamp.utcnow().date().isoformat(),
        "status": "EXECUTED_AND_SHARD_INTEGRITY_VERIFIED",
        "outcome": outcome,
        "claim_ceiling": "FULL_COHORT_HEADER_ONLY_PIXEL_ACQUISITION_COORDINATE_MAP_ONLY__NO_PIXEL_MORPHOLOGY_YET__EXTERNAL_LABELS_SEALED__NO_ORIGIN_CLAIM",
        "bindings": {
            "admission_path": str(args.admission), "admission_file_sha256": admission_sha,
            "C0H_result_path": str(args.c0h_result), "C0H_result_file_sha256": c0h_sha,
            "C0H_result_canonical_sha256": c0h["integrity"]["canonical_payload_sha256_without_integrity"],
            "poss_commit": b2.POSS_COMMIT,
            "stage_S0_csv_sha256": b2.S0_CSV_SHA256,
            "tile_manifest_csv_sha256": b2.TILES_CSV_SHA256,
            "structural_manifest_csv_sha256": b2.MANIFEST_CSV_SHA256
        },
        "shard_integrity": {
            "gate_pass": True, "shard_count": SHARD_COUNT,
            "receipt_canonical_sha256": receipt_digests,
            "distinct_plates_union": int(len(seen_plates)), "plate_overlap_count": 0,
            "source_rows_union": int(len(full)), "source_ids_unique": int(got_src.nunique()),
            "source_union_equals_frozen_S0": bool(source_integrity),
            "active_tiles_union": int(full.tile_id.astype(str).nunique()),
            "tile_union_equals_frozen_active_S0_tiles": bool(tile_integrity)
        },
        "cohort": {
            "rows": EXPECTED_ROWS,
            "distinct_plates": int(len(expected_plates)),
            "distinct_active_tiles": int(expected_active_tiles),
            "structural_clusters": int(full.structural_cluster.nunique())
        },
        "gates": {
            "source_and_plate_binding": {"pass": bool(binding_pass)},
            "header_and_tile_identity": {"pass": bool(header_tile_pass), "plate_failure_count": int(plate_failures), "active_tile_models_built": int(active_models)},
            "prediction_coverage": {"pass": bool(coverage_pass), "mapped_rows": int(mapped.sum()), "finite_prediction_rows": int(finite_rows.sum())},
            "tile_bounds": {"pass": bool(bounds_pass), "in_bounds_rows": int(in_bounds.sum()), "distance_to_tile_edge_px": qstats(edge)}
        },
        "acquisition_coordinate_summary": {
            "tile_x0": qstats(full.tile_x0), "tile_y0": qstats(full.tile_y0),
            "fullplate_x0": qstats(full.fullplate_x0), "fullplate_y0": qstats(full.fullplate_y0),
            "local_pixel_scale_arcsec": qstats(full.local_pixel_scale_arcsec),
            "tan_refit_median_arcsec": qstats(full.tan_refit_median_arcsec),
            "tan_refit_max_arcsec": qstats(full.tan_refit_max_arcsec)
        },
        "transport_contract": {
            "remote_image_section_accessed": False,
            "remote_image_array_materialized": False,
            "remote_named_plate_headers_only": True
        },
        "external_label_firewall": {"external_label_reveal_authorized": False, "date_or_external_environment_used": False},
        "manifest": {
            "path": str(args.out_manifest_gz), "rows": int(len(full_out)), "columns": REQUIRED_OUTPUT_COLUMNS,
            "csv_sha256": csv_sha, "gzip_sha256": gz_sha
        },
        "next_gate": "JPFM_2F_C1_NAMED_PLATE_SPARSE_STAMP_TRANSPORT_AND_DIRECT_MORPHOLOGY" if outcome == "PASS_FULL_S0_HEADER_ONLY_ACQUISITION_MAP_FROZEN" else "FULL_COHORT_PIXEL_ACQUISITION_MAP_NOT_ADMITTED"
    }
    result["integrity"] = {"canonical_payload_sha256_without_integrity": canonical_sha(result)}
    args.out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("OUTCOME", outcome, flush=True)
    print("ROWS", len(full_out), "PLATES", len(expected_plates), "ACTIVE_TILES", expected_active_tiles, flush=True)
    print("MIN_TILE_EDGE_PX", float(np.nanmin(edge)), flush=True)
    print("MANIFEST_CSV_SHA256", csv_sha, flush=True)
    print("RESULT_CANONICAL_SHA256", result["integrity"]["canonical_payload_sha256_without_integrity"], flush=True)


if __name__ == "__main__":
    main()
