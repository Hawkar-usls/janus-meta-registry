#!/usr/bin/env python3
"""JPFM-2F-A label-blind structural/artifact stratification.

Consumes only the frozen public POSS-I S0 release, tile manifest, repair ledger,
plate correction table and plate primary headers.  It deliberately excludes all
external temporal/environmental/witness labels.  The output is a deterministic
structural cluster manifest that must be frozen before any later label reveal.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy.spatial import cKDTree
from sklearn.cluster import MiniBatchKMeans
from sklearn.ensemble import IsolationForest
from sklearn.metrics import adjusted_rand_score

POSS_COMMIT = "4005e200541b321ead3d6608f0162a14430ef1c2"
BASE = f"https://raw.githubusercontent.com/jannefi/poss1-plate-slice/{POSS_COMMIT}"
REL = "results/s0-642-20260814"
S0_URL = f"{BASE}/{REL}/stage_S0.csv.gz"
TILES_URL = f"{BASE}/{REL}/tile_manifest.csv.gz"
REPAIRS_URL = f"{BASE}/{REL}/repaired_astrometry_tiles.csv"
WCS_URL = f"{BASE}/data/plate_crpix_table.csv"
IRSA_FMT = "https://irsa.ipac.caltech.edu/data/DSS/images/dss1red/dss1red_{plate}.fits"

S0_GZ_SHA256 = "f19cf987756c62a68f55a472992d860e73ae63b3a4664189092b0e1fda77f7bb"
TILES_GZ_SHA256 = "a1652db2d15470a9e8630a1a2ac3a055e49be65880ca615126a9aaa8cc2da02d"
S0_CSV_SHA256 = "2ff92f2210acb387ef9ef4b88d561595d3883e9aab27065042627272b96590f0"
TILES_CSV_SHA256 = "5dcb90dc5d98550e5a60246aced2b097922a267c69e81f27d45d16a288142a99"

EXPECTED_ROWS = 122820
EXPECTED_TILES = 31458
EXPECTED_PLATES = 642
HEADER_RANGE_END = 131071
HEADER_MAX_BYTES = 1024 * 1024
HEADER_WORKERS = 10
K = 16
SEED = 20260815
BOOTSTRAP_REFITS = 12
BOOTSTRAP_FRACTION = 0.7
PLATE_HALF_WIDTH_DEG = 3.25

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "JANUS-JPFM-2F-blind-structural/1.0"})


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def get_bytes(url: str, timeout: int = 90) -> bytes:
    r = SESSION.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content


def require_hash(label: str, data: bytes, expected: str) -> None:
    got = sha256_bytes(data)
    if got != expected:
        raise RuntimeError(f"{label} sha256 mismatch: got={got} expected={expected}")


def read_public_tables():
    s0_gz, tiles_gz = get_bytes(S0_URL), get_bytes(TILES_URL)
    require_hash("stage_S0.csv.gz", s0_gz, S0_GZ_SHA256)
    require_hash("tile_manifest.csv.gz", tiles_gz, TILES_GZ_SHA256)
    s0_csv, tiles_csv = gzip.decompress(s0_gz), gzip.decompress(tiles_gz)
    require_hash("stage_S0.csv", s0_csv, S0_CSV_SHA256)
    require_hash("tile_manifest.csv", tiles_csv, TILES_CSV_SHA256)
    repairs_b, wcs_b = get_bytes(REPAIRS_URL), get_bytes(WCS_URL)
    s0 = pd.read_csv(io.BytesIO(s0_csv))
    tiles = pd.read_csv(io.BytesIO(tiles_csv))
    repairs = pd.read_csv(io.BytesIO(repairs_b))
    wcs = pd.read_csv(io.BytesIO(wcs_b))
    if len(s0) != EXPECTED_ROWS or len(tiles) != EXPECTED_TILES:
        raise RuntimeError(f"release row invariant failed: S0={len(s0)} tiles={len(tiles)}")
    if s0.src_id.duplicated().any():
        raise RuntimeError("src_id is not unique in frozen S0")
    return s0, tiles, repairs, wcs, {
        "stage_S0_gz_sha256": sha256_bytes(s0_gz),
        "stage_S0_csv_sha256": sha256_bytes(s0_csv),
        "tile_manifest_gz_sha256": sha256_bytes(tiles_gz),
        "tile_manifest_csv_sha256": sha256_bytes(tiles_csv),
        "repair_ledger_sha256": sha256_bytes(repairs_b),
        "plate_correction_table_sha256": sha256_bytes(wcs_b),
    }


def find_header_end(buf: bytes):
    for i in range(len(buf) // 80):
        if buf[i * 80:i * 80 + 8] == b"END     ":
            logical = (i + 1) * 80
            block = ((logical + 2879) // 2880) * 2880
            if len(buf) >= block:
                return block
    return None


def parse_card_value(raw: str):
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("'"):
        out, i = [], 1
        while i < len(raw):
            if raw[i] == "'":
                if i + 1 < len(raw) and raw[i + 1] == "'":
                    out.append("'"); i += 2; continue
                break
            out.append(raw[i]); i += 1
        return "".join(out).strip()
    token = raw.split("/", 1)[0].strip()
    if token in ("T", "F"):
        return token == "T"
    try:
        if any(c in token.upper() for c in (".", "E", "D")):
            return float(token.replace("D", "E"))
        return int(token)
    except Exception:
        return token


def parse_header_cards(header: bytes) -> dict:
    kv = {}
    for i in range(0, len(header), 80):
        card = header[i:i + 80].decode("ascii", errors="replace")
        key = card[:8].strip()
        if key == "END":
            break
        if len(card) >= 10 and card[8:10] == "= ":
            kv[key] = parse_card_value(card[10:])
    return kv


def header_plate_center(kv: dict):
    try:
        ra = 15.0 * (float(kv["PLTRAH"]) + float(kv["PLTRAM"]) / 60.0 + float(kv["PLTRAS"]) / 3600.0)
        mag = abs(float(kv["PLTDECD"])) + float(kv["PLTDECM"]) / 60.0 + float(kv["PLTDECS"]) / 3600.0
        dec = -mag if str(kv.get("PLTDECSN", "+")).strip() == "-" else mag
        return ra, dec
    except Exception as e:
        raise RuntimeError(f"plate centre missing from header: {e}")


def fetch_header(plate: str):
    url = IRSA_FMT.format(plate=plate)
    last = None
    for attempt in range(4):
        try:
            end = HEADER_RANGE_END
            while end < HEADER_MAX_BYTES:
                r = SESSION.get(url, headers={"Range": f"bytes=0-{end}"}, timeout=90)
                r.raise_for_status()
                data = r.content
                h_end = find_header_end(data)
                if h_end is not None:
                    header = data[:h_end]
                    kv = parse_header_cards(header)
                    ra, dec = header_plate_center(kv)
                    return {
                        "plate_id": plate,
                        "plate_ra_deg": float(ra),
                        "plate_dec_deg": float(dec),
                        "header_bytes": len(header),
                        "header_sha256": sha256_bytes(header),
                        "http_status": int(r.status_code),
                    }
                end = min(HEADER_MAX_BYTES - 1, 2 * end + 1)
            raise RuntimeError("header END not found within safety cap")
        except Exception as e:
            last = e
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"{plate}: header fetch failed: {last}")


def fetch_headers(plates):
    out = []
    with cf.ThreadPoolExecutor(max_workers=HEADER_WORKERS) as ex:
        futs = {ex.submit(fetch_header, p): p for p in plates}
        for i, fut in enumerate(cf.as_completed(futs), 1):
            out.append(fut.result())
            if i % 50 == 0 or i == len(plates):
                print(f"[headers] {i}/{len(plates)}", flush=True)
    df = pd.DataFrame(out).sort_values("plate_id").reset_index(drop=True)
    if len(df) != len(plates):
        raise RuntimeError("header count mismatch")
    return df


def wrap_delta_ra_deg(ra, ra0):
    d = np.asarray(ra, dtype=float) - float(ra0)
    return (d + 180.0) % 360.0 - 180.0


def triplet_q_from_vectors(v1, v2):
    cross = abs(v1[0] * v2[1] - v1[1] * v2[0])
    d1 = math.hypot(v1[0], v1[1])
    d2 = math.hypot(v2[0], v2[1])
    d12 = math.hypot(v1[0] - v2[0], v1[1] - v2[1])
    longest = max(d1, d2, d12)
    if longest <= 0:
        return 1.0, 0.0
    return cross / (longest * longest), longest * 3600.0


def geometry_for_plate(g: pd.DataFrame) -> pd.DataFrame:
    g = g.copy().reset_index(drop=False).rename(columns={"index": "global_index"})
    ra0 = float(g.plate_ra_deg.iloc[0]); dec0 = float(g.plate_dec_deg.iloc[0])
    x = wrap_delta_ra_deg(g.ra.to_numpy(float), ra0) * math.cos(math.radians(dec0))
    y = g.dec.to_numpy(float) - dec0
    coords = np.column_stack([x, y])
    n = len(g)
    tree = cKDTree(coords)
    kq = min(7, n)
    dist, idx = tree.query(coords, k=kq)
    if kq == 1:
        dist = dist[:, None]; idx = idx[:, None]
    nn = np.full(n, np.nan)
    if kq >= 2:
        nn = dist[:, 1] * 3600.0
    counts = {}
    for arcsec in (30, 60, 120, 300):
        rdeg = arcsec / 3600.0
        counts[arcsec] = np.asarray(tree.query_ball_point(coords, rdeg, return_length=True), dtype=int) - 1
    best_q = np.full(n, np.nan)
    best_span = np.full(n, np.nan)
    pca_linearity = np.full(n, np.nan)
    if kq >= 3:
        for i in range(n):
            neigh = [int(j) for j in np.atleast_1d(idx[i])[1:] if int(j) != i]
            qmin, span_at = float("inf"), np.nan
            for a in range(len(neigh)):
                v1 = coords[neigh[a]] - coords[i]
                for b in range(a + 1, len(neigh)):
                    v2 = coords[neigh[b]] - coords[i]
                    q, span = triplet_q_from_vectors(v1, v2)
                    if q < qmin:
                        qmin, span_at = q, span
            if math.isfinite(qmin):
                best_q[i], best_span[i] = qmin, span_at
            pts = coords[[i] + neigh]
            if len(pts) >= 3:
                c = pts - pts.mean(axis=0)
                cov = np.cov(c.T, bias=True)
                vals = np.linalg.eigvalsh(cov)
                lmin, lmax = float(vals[0]), float(vals[-1])
                pca_linearity[i] = 1.0 - (lmin / lmax if lmax > 0 else 1.0)
    return pd.DataFrame({
        "global_index": g.global_index.astype(int),
        "plate_x_deg": x,
        "plate_y_deg": y,
        "plate_r_deg": np.hypot(x, y),
        "plate_edge_proxy": np.maximum(np.abs(x), np.abs(y)) / PLATE_HALF_WIDTH_DEG,
        "nn_arcsec": nn,
        "n30": counts[30],
        "n60": counts[60],
        "n120": counts[120],
        "n300": counts[300],
        "best_triplet_q": best_q,
        "best_triplet_span_arcsec": best_span,
        "pca_linearity": pca_linearity,
    })


def build_feature_table(s0, tiles, repairs, wcs, headers):
    tile_map = tiles[["tile_id", "plate_id"]].drop_duplicates()
    if tile_map.tile_id.duplicated().any():
        raise RuntimeError("tile_id maps to multiple plates")
    d = s0.merge(tile_map, on="tile_id", how="left", validate="many_to_one")
    if d.plate_id.isna().any():
        raise RuntimeError("tile->plate join incomplete")
    plates = sorted(tile_map.plate_id.astype(str).unique())
    if len(plates) != EXPECTED_PLATES:
        raise RuntimeError(f"expected {EXPECTED_PLATES} plates, got {len(plates)}")
    d = d.merge(headers[["plate_id", "plate_ra_deg", "plate_dec_deg"]], on="plate_id", how="left", validate="many_to_one")
    if d[["plate_ra_deg", "plate_dec_deg"]].isna().any().any():
        raise RuntimeError("plate-centre join incomplete")
    wc = wcs.rename(columns={"plate": "plate_id"})[["plate_id", "offset_arcsec", "status"]]
    d = d.merge(wc, on="plate_id", how="left", validate="many_to_one")
    if d.offset_arcsec.isna().any():
        raise RuntimeError("plate correction join incomplete")
    repaired_tiles = set(repairs.loc[repairs.action.astype(str) == "repaired", "tile_id"].astype(str))
    d["repaired_tile"] = d.tile_id.astype(str).isin(repaired_tiles).astype(int)
    d["wcs_divergent_gt_1p5"] = (d.offset_arcsec.astype(float) > 1.5).astype(int)

    tile_counts = d.groupby("tile_id").size().rename("tile_candidate_count")
    all_tiles = tile_map.merge(tile_counts, left_on="tile_id", right_index=True, how="left").fillna({"tile_candidate_count": 0})
    all_tiles["tile_candidate_count"] = all_tiles.tile_candidate_count.astype(int)
    stats = all_tiles.groupby("plate_id").tile_candidate_count.agg(["mean", "std"]).rename(columns={"mean": "tile_mean", "std": "tile_std"})
    all_tiles = all_tiles.merge(stats, on="plate_id", how="left")
    all_tiles["tile_count_z_within_plate"] = np.where(
        all_tiles.tile_std.fillna(0).to_numpy(float) > 0,
        (all_tiles.tile_candidate_count - all_tiles.tile_mean) / all_tiles.tile_std,
        0.0,
    )
    d = d.merge(all_tiles[["tile_id", "tile_candidate_count", "tile_count_z_within_plate"]], on="tile_id", how="left", validate="many_to_one")
    plate_counts = d.groupby("plate_id").size().rename("plate_candidate_count")
    d = d.merge(plate_counts, on="plate_id", how="left", validate="many_to_one")

    d = d.reset_index(drop=True)
    pieces = []
    for i, (_plate, g) in enumerate(d.groupby("plate_id", sort=True), 1):
        pieces.append(geometry_for_plate(g))
        if i % 50 == 0 or i == EXPECTED_PLATES:
            print(f"[geometry] {i}/{EXPECTED_PLATES} plates", flush=True)
    geo = pd.concat(pieces, ignore_index=True).sort_values("global_index")
    if len(geo) != len(d) or not np.array_equal(geo.global_index.to_numpy(), np.arange(len(d))):
        raise RuntimeError("geometry row reconstruction mismatch")
    d = pd.concat([d.reset_index(drop=True), geo.drop(columns=["global_index"]).reset_index(drop=True)], axis=1)
    return d, all_tiles


RAW_FEATURES = [
    "nn_arcsec", "n30", "n60", "n120", "n300",
    "best_triplet_q", "best_triplet_span_arcsec", "pca_linearity",
    "tile_candidate_count", "plate_candidate_count", "tile_count_z_within_plate",
    "plate_x_deg", "plate_y_deg", "plate_r_deg", "plate_edge_proxy",
    "offset_arcsec", "wcs_divergent_gt_1p5", "repaired_tile",
]

MODEL_FEATURES = [
    "log_nn", "log_n30", "log_n60", "log_n120", "log_n300",
    "triplet_line_score", "log_triplet_span", "pca_linearity",
    "log_tile_count", "log_plate_count", "tile_count_z_within_plate",
    "plate_x_norm", "plate_y_norm", "plate_r_norm", "plate_edge_proxy",
    "log_wcs_offset", "wcs_divergent_gt_1p5", "repaired_tile",
]


def derived_model_features(d: pd.DataFrame) -> pd.DataFrame:
    x = pd.DataFrame(index=d.index)
    x["log_nn"] = np.log10(pd.to_numeric(d.nn_arcsec, errors="coerce") + 1.0)
    for r in (30, 60, 120, 300):
        x[f"log_n{r}"] = np.log1p(pd.to_numeric(d[f"n{r}"], errors="coerce"))
    x["triplet_line_score"] = -np.log10(np.clip(pd.to_numeric(d.best_triplet_q, errors="coerce"), 1e-6, None))
    x["log_triplet_span"] = np.log10(pd.to_numeric(d.best_triplet_span_arcsec, errors="coerce") + 1.0)
    x["pca_linearity"] = pd.to_numeric(d.pca_linearity, errors="coerce")
    x["log_tile_count"] = np.log1p(pd.to_numeric(d.tile_candidate_count, errors="coerce"))
    x["log_plate_count"] = np.log1p(pd.to_numeric(d.plate_candidate_count, errors="coerce"))
    x["tile_count_z_within_plate"] = pd.to_numeric(d.tile_count_z_within_plate, errors="coerce")
    x["plate_x_norm"] = pd.to_numeric(d.plate_x_deg, errors="coerce") / PLATE_HALF_WIDTH_DEG
    x["plate_y_norm"] = pd.to_numeric(d.plate_y_deg, errors="coerce") / PLATE_HALF_WIDTH_DEG
    x["plate_r_norm"] = pd.to_numeric(d.plate_r_deg, errors="coerce") / PLATE_HALF_WIDTH_DEG
    x["plate_edge_proxy"] = pd.to_numeric(d.plate_edge_proxy, errors="coerce")
    x["log_wcs_offset"] = np.log1p(pd.to_numeric(d.offset_arcsec, errors="coerce"))
    x["wcs_divergent_gt_1p5"] = pd.to_numeric(d.wcs_divergent_gt_1p5, errors="coerce")
    x["repaired_tile"] = pd.to_numeric(d.repaired_tile, errors="coerce")
    return x[MODEL_FEATURES]


def robust_scale(x: pd.DataFrame):
    arr = x.to_numpy(float)
    med = np.nanmedian(arr, axis=0)
    filled = np.where(np.isfinite(arr), arr, med[None, :])
    mad = np.median(np.abs(filled - med[None, :]), axis=0)
    sigma = 1.4826 * mad
    std = filled.std(axis=0)
    sigma = np.where(sigma > 1e-12, sigma, np.where(std > 1e-12, std, 1.0))
    z = (filled - med[None, :]) / sigma[None, :]
    z = np.clip(z, -8.0, 8.0)
    if not np.isfinite(z).all():
        raise RuntimeError("non-finite standardized feature matrix")
    meta = {
        col: {"median": float(med[i]), "robust_sigma": float(sigma[i]), "missing": int(np.sum(~np.isfinite(arr[:, i])))}
        for i, col in enumerate(x.columns)
    }
    return z, meta


def quantiles(s):
    a = np.asarray(s, dtype=float)
    a = a[np.isfinite(a)]
    if not len(a):
        return None
    return {str(q): float(np.quantile(a, q)) for q in (0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1)}


def cluster_summaries(d, x_raw, labels, anomaly_score):
    out = []
    tmp = d[["src_id", "plate_id", "tile_id"]].copy()
    tmp["cluster"] = labels
    tmp["anomaly_score"] = anomaly_score
    for c in sorted(np.unique(labels)):
        ix = np.flatnonzero(labels == c)
        g = tmp.iloc[ix]
        plate_vc = g.plate_id.value_counts()
        tile_vc = g.tile_id.value_counts()
        medians = {col: float(np.nanmedian(x_raw.iloc[ix][col].to_numpy(float))) for col in x_raw.columns}
        out.append({
            "cluster": int(c),
            "rows": int(len(ix)),
            "fraction": float(len(ix) / len(labels)),
            "unique_plates": int(g.plate_id.nunique()),
            "unique_tiles": int(g.tile_id.nunique()),
            "max_single_plate_fraction": float(plate_vc.iloc[0] / len(ix)),
            "max_single_tile_fraction": float(tile_vc.iloc[0] / len(ix)),
            "median_anomaly_score": float(np.median(anomaly_score[ix])),
            "raw_feature_medians": medians,
        })
    return out


def canonical_json_sha(obj):
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--out-manifest-gz", required=True, type=Path)
    args = ap.parse_args()
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_manifest_gz.parent.mkdir(parents=True, exist_ok=True)

    print("[1/7] public release hash gates", flush=True)
    s0, tiles, repairs, wcs, hashes = read_public_tables()
    tile_map = tiles[["tile_id", "plate_id"]].drop_duplicates()
    plates = sorted(tile_map.plate_id.astype(str).unique())
    if len(plates) != EXPECTED_PLATES:
        raise RuntimeError("plate invariant failed before headers")

    print("[2/7] stream public plate headers", flush=True)
    headers = fetch_headers(plates)

    print("[3/7] construct structural/artifact features", flush=True)
    d, all_tiles = build_feature_table(s0, tiles, repairs, wcs, headers)
    if len(d) != EXPECTED_ROWS:
        raise RuntimeError("feature table row count mismatch")
    raw = d[RAW_FEATURES].copy()
    model_raw = derived_model_features(d)
    z, scaling = robust_scale(model_raw)

    print("[4/7] deterministic blind coarse partition", flush=True)
    km = MiniBatchKMeans(
        n_clusters=K, random_state=SEED, batch_size=8192, n_init=20,
        max_iter=100, reassignment_ratio=0.01,
    )
    labels = km.fit_predict(z)

    print("[5/7] deterministic rare-structure score", flush=True)
    iso = IsolationForest(
        n_estimators=400, max_samples=min(8192, len(z)), contamination="auto",
        random_state=SEED, n_jobs=-1,
    )
    iso.fit(z)
    anomaly_score = -iso.score_samples(z)
    order = np.argsort(-anomaly_score, kind="stable")
    rank = np.empty(len(z), dtype=int); rank[order] = np.arange(1, len(z) + 1)
    percentile = rank / float(len(z))
    tails = {
        "tail_0p1": (percentile <= 0.001).astype(int),
        "tail_0p5": (percentile <= 0.005).astype(int),
        "tail_1p0": (percentile <= 0.01).astype(int),
    }

    print("[6/7] cluster stability refits", flush=True)
    rng = np.random.default_rng(SEED)
    ari = []
    nboot = int(round(BOOTSTRAP_FRACTION * len(z)))
    for b in range(BOOTSTRAP_REFITS):
        sample = rng.choice(len(z), size=nboot, replace=True)
        bk = MiniBatchKMeans(
            n_clusters=K, random_state=SEED + 1000 + b, batch_size=8192,
            n_init=20, max_iter=100, reassignment_ratio=0.01,
        )
        bk.fit(z[sample])
        pred = bk.predict(z)
        a = float(adjusted_rand_score(labels, pred))
        ari.append(a)
        print(f"[stability] {b + 1}/{BOOTSTRAP_REFITS} ARI={a:.6f}", flush=True)

    print("[7/7] freeze compact blind manifest + result", flush=True)
    manifest = pd.DataFrame({
        "src_id": d.src_id.astype(str),
        "structural_cluster": labels.astype(int),
        "anomaly_score": anomaly_score,
        "anomaly_percentile_rank": percentile,
        **tails,
    }).sort_values("src_id", kind="stable").reset_index(drop=True)
    manifest_csv = manifest.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode("utf-8")
    manifest_csv_sha = sha256_bytes(manifest_csv)
    with gzip.GzipFile(filename="", mode="wb", fileobj=args.out_manifest_gz.open("wb"), mtime=0) as gz:
        gz.write(manifest_csv)
    manifest_gz_sha = sha256_bytes(args.out_manifest_gz.read_bytes())

    cluster_summary = cluster_summaries(d, model_raw, labels, anomaly_score)
    result = {
        "artifact_id": "JANUS-PALOMAR-JPFM-2F-A-BLIND-STRUCTURAL-STRATIFICATION-RUN-001",
        "experiment_id": "JPFM-2F-A",
        "schema_version": "1.0",
        "date": dt.date.today().isoformat(),
        "status": "EXECUTED_BLIND_STRUCTURAL_STRATIFICATION",
        "claim_ceiling": "BLIND_STRUCTURAL_AND_ARTIFACT_STRATIFICATION_ONLY__PIXEL_MORPHOLOGY_PENDING__NO_EXTERNAL_LABEL_INFERENCE",
        "bindings": {
            "admission_path": "data/JANUS-PALOMAR-JPFM-2F-BLIND-STRUCTURAL-STRATIFICATION-ADMISSION-v1.0.json",
            "poss_repository": "jannefi/poss1-plate-slice",
            "poss_commit": POSS_COMMIT,
            "poss_release": REL,
            "release_hashes": hashes,
        },
        "invariants": {
            "rows": int(len(d)),
            "tiles": int(tile_map.tile_id.nunique()),
            "plates": int(d.plate_id.nunique()),
            "src_id_unique": bool(not d.src_id.duplicated().any()),
            "tile_join_complete": bool(not d.plate_id.isna().any()),
            "header_join_complete": bool(not d.plate_ra_deg.isna().any()),
            "model_matrix_finite": bool(np.isfinite(z).all()),
            "full_plate_image_arrays_downloaded": false,
        },
        "blind_feature_contract": {
            "raw_features": RAW_FEATURES,
            "model_features": MODEL_FEATURES,
            "absolute_coordinates_used_as_model_features": false,
            "date_or_external_labels_available_to_model": false,
            "scaling": scaling,
            "raw_feature_quantiles": {col: quantiles(raw[col]) for col in RAW_FEATURES},
        },
        "coarse_partition": {
            "algorithm": "MiniBatchKMeans",
            "k": K,
            "seed": SEED,
            "cluster_sizes": {str(k): int(v) for k, v in pd.Series(labels).value_counts().sort_index().items()},
            "standardized_centroids": {
                str(i): {MODEL_FEATURES[j]: float(km.cluster_centers_[i, j]) for j in range(len(MODEL_FEATURES))}
                for i in range(K)
            },
            "cluster_context_summary": cluster_summary,
        },
        "rare_structure": {
            "algorithm": "IsolationForest",
            "seed": SEED,
            "score_semantics": "higher anomaly_score is more structurally unusual in the frozen blind feature space",
            "score_quantiles": quantiles(anomaly_score),
            "tail_counts": {k: int(v.sum()) for k, v in tails.items()},
        },
        "stability": {
            "bootstrap_refits": BOOTSTRAP_REFITS,
            "bootstrap_fraction": BOOTSTRAP_FRACTION,
            "adjusted_rand_index": ari,
            "ari_min": float(min(ari)),
            "ari_median": float(np.median(ari)),
            "ari_max": float(max(ari)),
        },
        "artifact_context": {
            "repaired_tile_rows": int(d.repaired_tile.sum()),
            "wcs_divergent_gt_1p5_rows": int(d.wcs_divergent_gt_1p5.sum()),
            "tiles_with_zero_candidates": int((all_tiles.tile_candidate_count == 0).sum()),
            "max_tile_candidate_count": int(all_tiles.tile_candidate_count.max()),
            "max_plate_candidate_count": int(d.groupby("plate_id").size().max()),
        },
        "manifest": {
            "path": str(args.out_manifest_gz),
            "rows": int(len(manifest)),
            "columns": list(manifest.columns),
            "csv_sha256": manifest_csv_sha,
            "gzip_sha256": manifest_gz_sha,
        },
        "next_gate": {
            "code": "JPFM_2F_B_PIXEL_MORPHOLOGY_SIDECAR_REQUIRED",
            "reason": "The frozen compact S0 release does not ship source-level PSF/shape metrics. Structural strata are not promoted to physical morphology classes until a label-blind public pixel-morphology sidecar is built and joined.",
            "required_features": [
                "FWHM_IMAGE_or_fwhm_ratio", "ELONGATION", "SPREAD_MODEL_or_spread_snr",
                "profile_diff", "circularity", "shape_defect", "circle_deviation", "psf_reference_quality"
            ],
        },
    }
    result["integrity"] = {"canonical_payload_sha256_without_integrity": canonical_json_sha(result)}
    args.out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("MANIFEST_CSV_SHA256", manifest_csv_sha, flush=True)
    print("RESULT_CANONICAL_SHA256", result["integrity"]["canonical_payload_sha256_without_integrity"], flush=True)
    print("STABILITY_MEDIAN_ARI", result["stability"]["ari_median"], flush=True)


if __name__ == "__main__":
    main()
