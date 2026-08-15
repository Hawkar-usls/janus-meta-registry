#!/usr/bin/env python3
"""Aggregate C2A shards, evaluate frozen measurement gates, then run preregistered blind morphology inference."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

EXPECTED_ROWS = 512
EXPECTED_TILES = 360
EXPECTED_PLATES = 234
SHARD_COUNT = 16
N_PERM = 50000
SEED = 20260815
SAMPLE_CSV_SHA = "a3656b181648e5abf933859199b5712e945b932610fffdd6c810785cff341b21"
SAMPLE_GZ_SHA = "3d4c7513b4add64324fddeedd04e9379b415f729fb36a76d977b871845638ca7"
SAMPLE_FREEZE_CANONICAL_SHA = "e4e5c8e13be97f4c54a12fc1cc217a5ed1fdcba763795aa47dc0d921b3d8d958"
PRIMARY = ["local_FWHM_IMAGE_z", "local_ELONGATION_z", "local_SPREAD_MODEL_z"]


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
        "p05": float(np.quantile(a, 0.05)), "median": float(np.median(a)),
        "p95": float(np.quantile(a, 0.95)), "max": float(np.max(a))
    }


def load_sample(path: Path) -> pd.DataFrame:
    gz = path.read_bytes()
    if sha256_bytes(gz) != SAMPLE_GZ_SHA:
        raise RuntimeError("C2A aggregate sample gzip hash mismatch")
    raw = gzip.decompress(gz)
    if sha256_bytes(raw) != SAMPLE_CSV_SHA:
        raise RuntimeError("C2A aggregate sample CSV hash mismatch")
    df = pd.read_csv(io.BytesIO(raw)); df["src_id"] = df.src_id.astype(str)
    if len(df) != EXPECTED_ROWS or df.src_id.nunique() != EXPECTED_ROWS or df.tile_id.nunique() != EXPECTED_TILES or df.plate_id.nunique() != EXPECTED_PLATES:
        raise RuntimeError("C2A aggregate sample invariant failed")
    return df


def robust_scale_matrix(x: np.ndarray):
    med = np.median(x, axis=0)
    mad = np.median(np.abs(x - med), axis=0)
    sig = 1.4826 * mad
    if np.any(~np.isfinite(sig)) or np.any(sig <= 0):
        return None, med, sig
    return (x - med) / sig, med, sig


def global_r2(x: np.ndarray, y: np.ndarray) -> float:
    overall = np.mean(x, axis=0)
    tss = float(np.sum((x - overall) ** 2))
    if not math.isfinite(tss) or tss <= 0:
        return float("nan")
    bss = 0.0
    for c in range(16):
        m = y == c
        n = int(m.sum())
        if n:
            d = np.mean(x[m], axis=0) - overall
            bss += n * float(np.sum(d * d))
    return bss / tss


def cluster_distances(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    out = np.full(16, np.nan, dtype=float)
    for c in range(16):
        a = y == c
        b = ~a
        if int(a.sum()) and int(b.sum()):
            out[c] = float(np.linalg.norm(np.mean(x[a], axis=0) - np.mean(x[b], axis=0)))
    return out


def role_stratified_permutation(y_full: np.ndarray, roles_full: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    yp = y_full.copy()
    for role in ("typical", "unusual"):
        idx = np.flatnonzero(roles_full == role)
        yp[idx] = rng.permutation(y_full[idx])
    return yp


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True, type=Path)
    ap.add_argument("--admission", required=True, type=Path)
    ap.add_argument("--shards-dir", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--out-sidecar-gz", required=True, type=Path)
    args = ap.parse_args(); args.out_json.parent.mkdir(parents=True, exist_ok=True)

    print("[C2A aggregate] [1/9] bind exact frozen sample and preregistration", flush=True)
    sample = load_sample(args.sample)
    admission = json.loads(args.admission.read_text(encoding="utf-8"))
    if admission.get("status") != "PREREGISTERED_AFTER_EXACT_512_SAMPLE_FREEZE_BEFORE_C2A_PIXEL_OUTCOME":
        raise RuntimeError("C2A admission status mismatch")
    if admission["frozen_sample_binding"]["manifest_csv_sha256"] != SAMPLE_CSV_SHA or admission["frozen_sample_binding"]["manifest_gzip_sha256"] != SAMPLE_GZ_SHA:
        raise RuntimeError("C2A admission sample binding mismatch")
    if admission["external_label_firewall"]["external_label_reveal_authorized"] is not False:
        raise RuntimeError("C2A admission external-label firewall open")
    admission_sha = sha256_bytes(args.admission.read_bytes())

    expected_tiles = sorted(sample.tile_id.astype(str).unique())
    expected_src = set(sample.src_id.astype(str))
    assignment = {tid: i % SHARD_COUNT for i, tid in enumerate(expected_tiles)}

    print("[C2A aggregate] [2/9] verify 16 shard receipts and exact deterministic tile partition", flush=True)
    rps = sorted(args.shards_dir.glob("JANUS-PALOMAR-JPFM-2F-C2A-SHARD-*-RECEIPT-RUN-001.json"))
    if len(rps) != SHARD_COUNT:
        raise RuntimeError(f"expected {SHARD_COUNT} C2A receipts, got {len(rps)}")
    frames=[]; receipts=[]; seen_idx=set(); seen_tiles=set(); receipt_digests=[]
    for rp in rps:
        r=json.loads(rp.read_text(encoding="utf-8")); idx=int(r["shard"]["index"])
        if idx in seen_idx or not 0 <= idx < SHARD_COUNT:
            raise RuntimeError("duplicate/invalid C2A shard index")
        seen_idx.add(idx)
        if r.get("status") != "EXECUTED_SHARD_RECEIPT__NO_GLOBAL_OUTCOME_OR_INFERENCE" or int(r["shard"]["count"]) != SHARD_COUNT:
            raise RuntimeError("C2A shard receipt status/count mismatch")
        if r["external_label_firewall"]["external_label_reveal_authorized"] is not False:
            raise RuntimeError("C2A external-label firewall violation")
        payload=dict(r); integ=payload.pop("integrity", None)
        if not integ or canonical_sha(payload) != integ.get("canonical_payload_sha256_without_integrity"):
            raise RuntimeError(f"C2A receipt canonical hash mismatch {rp.name}")
        receipt_digests.append(integ["canonical_payload_sha256_without_integrity"])
        assigned=[str(x) for x in r["shard"]["assigned_tiles"]]
        expected_for_idx=[t for t in expected_tiles if assignment[t]==idx]
        if assigned != expected_for_idx:
            raise RuntimeError(f"C2A shard {idx} tile assignment mismatch")
        if seen_tiles.intersection(assigned):
            raise RuntimeError("C2A cross-shard tile overlap")
        seen_tiles.update(assigned)
        sp=args.shards_dir/str(r["sidecar"]["path"])
        if not sp.exists():
            raise RuntimeError(f"missing C2A sidecar {sp.name}")
        gz=sp.read_bytes(); raw=gzip.decompress(gz)
        if sha256_bytes(gz)!=r["sidecar"]["gzip_sha256"] or sha256_bytes(raw)!=r["sidecar"]["csv_sha256"]:
            raise RuntimeError(f"C2A shard sidecar hash mismatch {idx}")
        df=pd.read_csv(io.BytesIO(raw)); df["src_id"]=df.src_id.astype(str)
        if len(df)!=int(r["sidecar"]["rows"]) or df.src_id.duplicated().any():
            raise RuntimeError(f"C2A shard sidecar row/unique failure {idx}")
        if set(df.tile_id.astype(str))-set(assigned):
            raise RuntimeError(f"C2A shard sidecar contains out-of-shard tile {idx}")
        frames.append(df); receipts.append(r)
    if seen_idx != set(range(SHARD_COUNT)) or seen_tiles != set(expected_tiles):
        raise RuntimeError("C2A shard partition incomplete")

    print("[C2A aggregate] [3/9] exact 512-source union", flush=True)
    full=pd.concat(frames, ignore_index=True); full["src_id"]=full.src_id.astype(str)
    if len(full)!=EXPECTED_ROWS or full.src_id.nunique()!=EXPECTED_ROWS or set(full.src_id)!=expected_src:
        raise RuntimeError("C2A exact source union failed")
    # Preserve frozen source order/context from sample and prevent shard metadata from changing membership.
    frozen_context=sample[["src_id","structural_cluster","sample_role","anomaly_score","plate_id","tile_id","object_id"]].copy()
    check=full.merge(frozen_context, on="src_id", suffixes=("","_frozen"), validate="one_to_one")
    for c in ["structural_cluster","sample_role","plate_id","tile_id","object_id"]:
        if not (check[c].astype(str)==check[c+"_frozen"].astype(str)).all():
            raise RuntimeError(f"C2A frozen context mismatch: {c}")

    print("[C2A aggregate] [4/9] evaluate preregistered measurement gates", flush=True)
    tile_state=full[["tile_id","tile_identity_reconstructed","tile_detection_status"]].drop_duplicates()
    if tile_state.tile_id.nunique()!=EXPECTED_TILES:
        raise RuntimeError("C2A tile-state count mismatch")
    tile_identity_pass=bool(tile_state.tile_identity_reconstructed.astype(bool).all())
    detection_tiles=int((tile_state.tile_detection_status.astype(str)=="PASS").sum())
    detection_frac=detection_tiles/EXPECTED_TILES
    detection_pass=detection_frac>=0.95
    exact=full.exact_object_status.astype(str).eq("EXACT_NUMBER_RECOVERED")
    exact_n=int(exact.sum()); exact_frac=exact_n/EXPECTED_ROWS; exact_pass=exact_frac>=0.90
    sep=pd.to_numeric(full.get("pass2_to_s0_sep_arcsec"), errors="coerce")
    sep_good=exact & np.isfinite(sep) & (sep<=10.0)
    sep_frac=float(sep_good.sum()/exact_n) if exact_n else 0.0; sep_pass=sep_frac>=0.90
    raw_cols=["pass2_fwhm_image","pass2_elongation","pass2_spread_model"]
    raw=full.loc[exact,raw_cols].apply(pd.to_numeric,errors="coerce").to_numpy(float) if exact_n else np.empty((0,3))
    raw_frac=float(np.isfinite(raw).all(axis=1).mean()) if exact_n else 0.0; raw_pass=raw_frac>=0.95
    shape_failed=pd.to_numeric(full.get("shape_failed"),errors="coerce").fillna(1).astype(int)
    shape_ok=exact & shape_failed.eq(0); shape_frac=float(shape_ok.sum()/exact_n) if exact_n else 0.0; shape_pass=shape_frac>=0.90
    norm=full.loc[exact,PRIMARY].apply(pd.to_numeric,errors="coerce").to_numpy(float) if exact_n else np.empty((0,3))
    norm_frac=float(np.isfinite(norm).all(axis=1).mean()) if exact_n else 0.0; norm_pass=norm_frac>=0.80

    if not (tile_identity_pass and detection_pass):
        measurement_outcome="FAIL_CLOSED_TILE_OR_DETECTION_REPLAY"
    elif not (exact_pass and sep_pass):
        measurement_outcome="FAIL_CLOSED_OBJECT_LINEAGE"
    elif not raw_pass:
        measurement_outcome="FAIL_CLOSED_RAW_UPSTREAM_MORPHOLOGY"
    elif not shape_pass:
        measurement_outcome="FAIL_CLOSED_SHAPE_REPLAY"
    elif not norm_pass:
        measurement_outcome="FAIL_CLOSED_LOCAL_REFERENCE_NORMALIZATION"
    else:
        measurement_outcome="PASS_STRATIFIED_UPSTREAM_MORPHOLOGY_CORPUS_ADMITTED"

    print("[C2A aggregate] [5/9] freeze aggregate source sidecar before inference", flush=True)
    full=full.sort_values(["structural_cluster","sample_role","src_id"],kind="stable").reset_index(drop=True)
    csv_bytes=full.to_csv(index=False,lineterminator="\n",float_format="%.12g").encode("utf-8")
    csv_sha=sha256_bytes(csv_bytes)
    with args.out_sidecar_gz.open("wb") as fout:
        with gzip.GzipFile(filename="",mode="wb",fileobj=fout,mtime=0) as z:
            z.write(csv_bytes)
    gz_sha=sha256_bytes(args.out_sidecar_gz.read_bytes())

    print("[C2A aggregate] [6/9] preregistered complete-case morphology matrix", flush=True)
    prim=full[PRIMARY].apply(pd.to_numeric,errors="coerce").to_numpy(float)
    complete=np.isfinite(prim).all(axis=1)
    complete_n=int(complete.sum()); complete_frac=complete_n/EXPECTED_ROWS
    inference_status="WITHHELD_MEASUREMENT_NOT_ADMITTED"
    inference={
        "status": inference_status,
        "complete_rows": complete_n,
        "complete_fraction": complete_frac,
        "permutations": N_PERM,
        "seed": SEED
    }

    if measurement_outcome=="PASS_STRATIFIED_UPSTREAM_MORPHOLOGY_CORPUS_ADMITTED":
        if complete_frac < 0.80:
            inference["status"]="WITHHELD_INSUFFICIENT_NORMALIZED_COVERAGE"
        else:
            x_scaled, med, sig=robust_scale_matrix(prim[complete])
            if x_scaled is None:
                inference["status"]="WITHHELD_NONPOSITIVE_GLOBAL_MAD"
                inference["global_feature_medians"]=med.tolist()
                inference["global_feature_robust_sigmas"]=sig.tolist()
            else:
                print("[C2A aggregate] [7/9] 50,000 role-stratified blind permutations + maxT", flush=True)
                y_full=pd.to_numeric(full.structural_cluster,errors="raise").to_numpy(int)
                roles_full=full.sample_role.astype(str).to_numpy()
                y_obs=y_full[complete]
                obs_r2=global_r2(x_scaled,y_obs)
                obs_dist=cluster_distances(x_scaled,y_obs)
                rng=np.random.default_rng(SEED)
                r2_hits=0
                maxT_hits=np.zeros(16,dtype=np.int64)
                null_r2=np.empty(N_PERM,dtype=float)
                null_max=np.empty(N_PERM,dtype=float)
                for i in range(N_PERM):
                    yp_full=role_stratified_permutation(y_full,roles_full,rng)
                    yp=yp_full[complete]
                    stat=global_r2(x_scaled,yp)
                    dist=cluster_distances(x_scaled,yp)
                    mx=float(np.nanmax(dist))
                    null_r2[i]=stat; null_max[i]=mx
                    if stat>=obs_r2: r2_hits+=1
                    maxT_hits += (mx>=obs_dist)
                    if (i+1)%10000==0:
                        print(f"[C2A permutation] {i+1}/{N_PERM}",flush=True)
                global_p=(1+r2_hits)/(N_PERM+1)
                adj=(1+maxT_hits)/(N_PERM+1)
                inference={
                    "status":"EXECUTED_BLIND_MORPHOLOGY_ASSOCIATION_TEST",
                    "complete_rows":complete_n,"complete_fraction":complete_frac,
                    "feature_matrix":PRIMARY,
                    "global_feature_medians":med.tolist(),
                    "global_feature_robust_sigmas":sig.tolist(),
                    "global_observed_R2_like":float(obs_r2),
                    "global_permutation_p":float(global_p),
                    "global_alpha":0.05,
                    "global_significant":bool(global_p<0.05),
                    "permutations":N_PERM,"seed":SEED,
                    "null_R2_summary":qstats(null_r2),
                    "cluster_followups":[
                        {
                            "cluster":int(c),
                            "observed_one_vs_rest_centroid_distance":float(obs_dist[c]) if np.isfinite(obs_dist[c]) else None,
                            "maxT_adjusted_p":float(adj[c]) if np.isfinite(obs_dist[c]) else None,
                            "familywise_alpha":0.05,
                            "significant_after_maxT":bool(np.isfinite(obs_dist[c]) and global_p<0.05 and adj[c]<0.05)
                        }
                        for c in range(16)
                    ],
                    "null_maxT_summary":qstats(null_max),
                    "interpretation_ceiling":"STRUCTURAL_STRATA_CARRY_LOCAL_NORMALIZED_MORPHOLOGY_INFORMATION_ONLY__NOT_PHYSICAL_CLASS_OR_ORIGIN"
                }

    print("[C2A aggregate] [8/9] descriptive frozen-cluster morphology summaries", flush=True)
    cluster_summaries=[]
    for c,g in full.groupby("structural_cluster",sort=True):
        cluster_summaries.append({
            "cluster":int(c),"rows":int(len(g)),
            "exact_rows":int(g.exact_object_status.astype(str).eq("EXACT_NUMBER_RECOVERED").sum()),
            "local_reference_count":qstats(g.get("local_reference_star_count")),
            "FWHM_IMAGE":qstats(g.get("pass2_fwhm_image")),
            "ELONGATION":qstats(g.get("pass2_elongation")),
            "SPREAD_MODEL":qstats(g.get("pass2_spread_model")),
            "local_sharpness_z":qstats(g.get("local_sharpness_z")),
            "local_ELONGATION_z":qstats(g.get("local_ELONGATION_z")),
            "local_SPREAD_MODEL_z":qstats(g.get("local_SPREAD_MODEL_z")),
            "profile_diff":qstats(g.get("profile_diff")),
            "circularity":qstats(g.get("circularity")),
            "circle_deviation":qstats(g.get("circle_deviation"))
        })

    print("[C2A aggregate] [9/9] write single global measurement/inference result", flush=True)
    result={
        "artifact_id":"JANUS-PALOMAR-JPFM-2F-C2A-STRATIFIED-UPSTREAM-MORPHOLOGY-REPLAY-RUN-001",
        "experiment_id":"JPFM-2F-C2A","schema_version":"1.0",
        "date":pd.Timestamp.utcnow().date().isoformat(),
        "status":"EXECUTED_AND_SHARD_INTEGRITY_VERIFIED",
        "measurement_outcome":measurement_outcome,
        "claim_ceiling":"LABEL_BLIND_STRATIFIED_UPSTREAM_MORPHOLOGY_AND_STRUCTURAL_ASSOCIATION_ONLY__NO_EXTERNAL_LABEL_INFERENCE__NO_CAUSAL_OR_ORIGIN_CLAIM",
        "bindings":{
            "admission_path":str(args.admission),"admission_file_sha256":admission_sha,
            "sample_path":str(args.sample),"sample_csv_sha256":SAMPLE_CSV_SHA,"sample_gzip_sha256":SAMPLE_GZ_SHA,
            "sample_freeze_canonical_sha256":SAMPLE_FREEZE_CANONICAL_SHA,
            "poss_commit":"4005e200541b321ead3d6608f0162a14430ef1c2"
        },
        "shard_integrity":{
            "gate_pass":True,"shard_count":SHARD_COUNT,"receipt_canonical_sha256":receipt_digests,
            "distinct_tiles_union":len(seen_tiles),"tile_overlap_count":0,
            "source_rows_union":len(full),"source_ids_unique":int(full.src_id.nunique()),
            "source_union_equals_frozen_512":True
        },
        "measurement_gates":{
            "tile_identity":{"pass":tile_identity_pass,"exact_reconstructed_tiles":int(tile_state.tile_identity_reconstructed.astype(bool).sum()),"required":EXPECTED_TILES},
            "detection_chain":{"pass":detection_pass,"tiles_pass":detection_tiles,"fraction":detection_frac,"required_fraction":0.95},
            "exact_object_id":{"pass":exact_pass,"rows":exact_n,"fraction":exact_frac,"required_fraction":0.90},
            "sky_consistency":{"pass":sep_pass,"le10_fraction_among_exact":sep_frac,"required_fraction":0.90,"separation_arcsec":qstats(sep[exact])},
            "raw_upstream_morphology":{"pass":raw_pass,"finite_fraction_among_exact":raw_frac,"required_fraction":0.95},
            "shape_execution":{"pass":shape_pass,"success_fraction_among_exact":shape_frac,"required_fraction":0.90},
            "local_reference_normalization":{"pass":norm_pass,"finite_primary_z_fraction_among_exact":norm_frac,"required_fraction":0.80,"reference_star_count":qstats(full.get("local_reference_star_count"))}
        },
        "blind_morphology_inference":inference,
        "cluster_summaries":cluster_summaries,
        "external_label_firewall":{"external_label_reveal_authorized":False,"date_or_external_environment_used":False},
        "sidecar":{"path":str(args.out_sidecar_gz),"rows":len(full),"csv_sha256":csv_sha,"gzip_sha256":gz_sha},
        "next_gate":(
            "JPFM_2F_C2B_FREEZE_LARGER_OR_FULL_LABEL_BLIND_MORPHOLOGY_MANIFEST"
            if measurement_outcome=="PASS_STRATIFIED_UPSTREAM_MORPHOLOGY_CORPUS_ADMITTED"
            else "C2A_MEASUREMENT_CORPUS_NOT_ADMITTED__LOCALIZE_FAILURE_WITHOUT_EXTERNAL_LABEL_REVEAL"
        )
    }
    result["integrity"]={"canonical_payload_sha256_without_integrity":canonical_sha(result)}
    args.out_json.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("MEASUREMENT_OUTCOME",measurement_outcome,flush=True)
    print("EXACT",exact_n,"RAW_FRAC",raw_frac,"SHAPE_FRAC",shape_frac,"LOCAL_NORM_FRAC",norm_frac,flush=True)
    print("INFERENCE_STATUS",inference.get("status"),"GLOBAL_P",inference.get("global_permutation_p"),flush=True)
    print("SIDECAR_CSV_SHA256",csv_sha,flush=True)
    print("RESULT_CANONICAL_SHA256",result["integrity"]["canonical_payload_sha256_without_integrity"],flush=True)


if __name__=="__main__":
    main()
