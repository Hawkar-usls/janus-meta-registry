#!/usr/bin/env python3
"""Freeze the 512-source label-blind C2A upstream morphology corpus before pixel replay."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path

import pandas as pd

EXPECTED_ROWS = 512
EXPECTED_TILES = 360
EXPECTED_PLATES = 234
CLUSTERS = 16
N_TYPICAL = 16
N_UNUSUAL = 16
C0M_CSV_SHA = "d41bfc95e9f0219d76ee383d057938287dcaaef8ba5005c66414d4a2422f75c0"
C0M_GZ_SHA = "8493e1dc6b3d89ecd1984d0826b663f2a12ede9664a3c5bb4812b51b6d3a0eca"
C0M_RESULT_CANONICAL_SHA = "2bc8ee104cb05d588a264a7f25d3d3713907f689da9aafb7c72f726627bdf5ba"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--c0m-result", required=True, type=Path)
    ap.add_argument("--c0m-map", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--out-manifest-gz", required=True, type=Path)
    args = ap.parse_args(); args.out_json.parent.mkdir(parents=True, exist_ok=True)

    parent = json.loads(args.c0m_result.read_text(encoding="utf-8"))
    if parent.get("outcome") != "PASS_FULL_S0_HEADER_ONLY_ACQUISITION_MAP_FROZEN":
        raise RuntimeError("C2A sample freeze parent C0M is not admitted PASS")
    if parent.get("integrity", {}).get("canonical_payload_sha256_without_integrity") != C0M_RESULT_CANONICAL_SHA:
        raise RuntimeError("C2A sample freeze C0M canonical binding mismatch")
    if parent["external_label_firewall"]["external_label_reveal_authorized"] is not False:
        raise RuntimeError("C2A sample freeze parent external-label firewall is open")

    gz = args.c0m_map.read_bytes()
    if sha256_bytes(gz) != C0M_GZ_SHA:
        raise RuntimeError("C2A sample freeze C0M gzip hash mismatch")
    raw = gzip.decompress(gz)
    if sha256_bytes(raw) != C0M_CSV_SHA:
        raise RuntimeError("C2A sample freeze C0M CSV hash mismatch")
    df = pd.read_csv(io.BytesIO(raw))
    df["src_id"] = df.src_id.astype(str)
    if len(df) != 122820 or df.src_id.nunique() != 122820:
        raise RuntimeError("C2A sample freeze C0M cohort invariant failed")

    selected = []
    for cluster in range(CLUSTERS):
        g = df[pd.to_numeric(df.structural_cluster, errors="coerce") == cluster].copy()
        if len(g) < N_TYPICAL + N_UNUSUAL:
            raise RuntimeError(f"cluster {cluster} too small for frozen sample")
        g["anomaly_score"] = pd.to_numeric(g.anomaly_score, errors="coerce")
        if g.anomaly_score.isna().any():
            raise RuntimeError(f"cluster {cluster} has nonfinite anomaly score")
        med = float(g.anomaly_score.median())
        g["_median_distance"] = (g.anomaly_score - med).abs()
        typical = g.sort_values(["_median_distance", "src_id"], kind="stable").head(N_TYPICAL).copy()
        typical["sample_role"] = "typical"
        used = set(typical.src_id)
        unusual = g[~g.src_id.isin(used)].sort_values(
            ["anomaly_score", "src_id"], ascending=[False, True], kind="stable"
        ).head(N_UNUSUAL).copy()
        unusual["sample_role"] = "unusual"
        selected.extend([typical, unusual])

    out = pd.concat(selected, ignore_index=True)
    keep = [
        "src_id", "tile_id", "object_id", "plate_id", "ra", "dec",
        "structural_cluster", "sample_role", "anomaly_score", "tile_x0", "tile_y0",
        "fullplate_x0", "fullplate_y0", "distance_to_tile_edge_px"
    ]
    out = out[keep].sort_values(["structural_cluster", "sample_role", "src_id"], kind="stable").reset_index(drop=True)

    if len(out) != EXPECTED_ROWS or out.src_id.nunique() != EXPECTED_ROWS:
        raise RuntimeError("C2A sample row/unique invariant failed")
    if out.tile_id.nunique() != EXPECTED_TILES or out.plate_id.nunique() != EXPECTED_PLATES:
        raise RuntimeError(f"C2A sample topology changed: tiles={out.tile_id.nunique()} plates={out.plate_id.nunique()}")
    by_cluster = out.groupby("structural_cluster").size().to_dict()
    by_role = out.groupby(["structural_cluster", "sample_role"]).size().to_dict()
    for c in range(CLUSTERS):
        if by_cluster.get(c) != 32 or by_role.get((c, "typical")) != 16 or by_role.get((c, "unusual")) != 16:
            raise RuntimeError(f"C2A cluster/role balance failed for {c}")

    csv_bytes = out.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode("utf-8")
    csv_sha = sha256_bytes(csv_bytes)
    with args.out_manifest_gz.open("wb") as fout:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fout, mtime=0) as z:
            z.write(csv_bytes)
    gz_sha = sha256_bytes(args.out_manifest_gz.read_bytes())

    plate_census = out.groupby("structural_cluster").plate_id.nunique().astype(int).to_dict()
    tile_census = out.groupby("structural_cluster").tile_id.nunique().astype(int).to_dict()
    result = {
        "artifact_id": "JANUS-PALOMAR-JPFM-2F-C2A-STRATIFIED-UPSTREAM-MORPHOLOGY-SAMPLE-FREEZE-RUN-001",
        "experiment_id": "JPFM-2F-C2A-SAMPLE-FREEZE",
        "schema_version": "1.0",
        "date": pd.Timestamp.utcnow().date().isoformat(),
        "status": "FROZEN_BEFORE_C2A_PIXEL_REPLAY",
        "claim_ceiling": "LABEL_BLIND_SAMPLE_FREEZE_ONLY__NO_NEW_PIXEL_MEASUREMENT__NO_EXTERNAL_LABEL_INFERENCE__NO_ORIGIN_CLAIM",
        "bindings": {
            "admission_path": "data/JANUS-PALOMAR-JPFM-2F-C2A-STRATIFIED-UPSTREAM-MORPHOLOGY-SAMPLE-FREEZE-ADMISSION-v1.0.json",
            "C0M_result_path": str(args.c0m_result),
            "C0M_result_canonical_sha256": C0M_RESULT_CANONICAL_SHA,
            "C0M_manifest_csv_sha256": C0M_CSV_SHA,
            "C0M_manifest_gzip_sha256": C0M_GZ_SHA
        },
        "selection": {
            "clusters": CLUSTERS,
            "typical_per_cluster": N_TYPICAL,
            "unusual_per_cluster": N_UNUSUAL,
            "rows": int(len(out)),
            "distinct_tiles": int(out.tile_id.nunique()),
            "distinct_plates": int(out.plate_id.nunique()),
            "pixel_or_morphology_features_used": False,
            "external_labels_used": False
        },
        "per_cluster": [
            {
                "cluster": int(c),
                "rows": 32,
                "typical": 16,
                "unusual": 16,
                "distinct_tiles": int(tile_census[c]),
                "distinct_plates": int(plate_census[c])
            }
            for c in range(CLUSTERS)
        ],
        "manifest": {
            "path": str(args.out_manifest_gz),
            "rows": int(len(out)),
            "columns": keep,
            "csv_sha256": csv_sha,
            "gzip_sha256": gz_sha
        },
        "external_label_firewall": {"external_label_reveal_authorized": False},
        "next_gate": "JPFM_2F_C2A_STRATIFIED_UPSTREAM_MORPHOLOGY_REPLAY"
    }
    result["integrity"] = {"canonical_payload_sha256_without_integrity": canonical_sha(result)}
    args.out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("C2A_SAMPLE_FROZEN rows", len(out), "tiles", out.tile_id.nunique(), "plates", out.plate_id.nunique())
    print("MANIFEST_CSV_SHA256", csv_sha)
    print("MANIFEST_GZIP_SHA256", gz_sha)
    print("RESULT_CANONICAL_SHA256", result["integrity"]["canonical_payload_sha256_without_integrity"])


if __name__ == "__main__":
    main()
