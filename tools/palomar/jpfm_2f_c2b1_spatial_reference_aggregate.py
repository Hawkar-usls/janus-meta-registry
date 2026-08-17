#!/usr/bin/env python3
"""Aggregate C2B1 engineering shards; evaluate only frozen engineering gates."""
from __future__ import annotations
import argparse, gzip, hashlib, io, json, math
from pathlib import Path
import numpy as np
import pandas as pd

EXPECTED_ROWS=128
EXPECTED_PLATES=90
EXPECTED_TARGET_TILES=110
SHARD_COUNT=10
REF_MIN=20
HOLDOUT_CSV_SHA="bc30aab00bb79d5414cd4f2c4b7490c49f3e05058270286fb1c1aeb40cf8d871"
HOLDOUT_GZ_SHA="0a6311472ce9f88baa42f7cb4c7765b8757c83792ba6526c15f9f93680d28d9a"
HOLDOUT_CANON="50c79682c53cb718067229f832587e0d5ccd5ce338b49b140a7f7d3d32187db8"
ADMISSION_CANON="27373cc8f40fe8a368d42e05c6541bc77a1c5f95eb589f1bc0ec9b8ceaafd751"
DEDUP_CANON="16a93c7b515fb55685307dd3d808561882887f58e08b21d95474d6659a4da9f2"
ZCOLS=["local_FWHM_IMAGE_z","local_ELONGATION_z","local_SPREAD_MODEL_z"]

def sha(b):return hashlib.sha256(b).hexdigest()
def canon(o):return sha(json.dumps(o,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode())
def load_holdout(path):
    gz=path.read_bytes()
    if sha(gz)!=HOLDOUT_GZ_SHA: raise RuntimeError("holdout gzip mismatch")
    raw=gzip.decompress(gz)
    if sha(raw)!=HOLDOUT_CSV_SHA: raise RuntimeError("holdout csv mismatch")
    d=pd.read_csv(io.BytesIO(raw)); d["src_id"]=d.src_id.astype(str); d["plate_id"]=d.plate_id.astype(str); d["tile_id"]=d.tile_id.astype(str)
    if len(d)!=EXPECTED_ROWS or d.src_id.nunique()!=EXPECTED_ROWS or d.plate_id.nunique()!=EXPECTED_PLATES or d.tile_id.nunique()!=EXPECTED_TARGET_TILES: raise RuntimeError("holdout invariant")
    return d

def qstats(x):
    a=pd.to_numeric(pd.Series(x),errors="coerce").to_numpy(float); a=a[np.isfinite(a)]
    if not len(a):return {"n_finite":0}
    return {"n_finite":int(len(a)),"min":float(a.min()),"p05":float(np.quantile(a,.05)),"p25":float(np.quantile(a,.25)),"median":float(np.median(a)),"p75":float(np.quantile(a,.75)),"p95":float(np.quantile(a,.95)),"max":float(a.max())}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--holdout",required=True,type=Path); ap.add_argument("--shards-dir",required=True,type=Path); ap.add_argument("--out-json",required=True,type=Path); ap.add_argument("--out-sidecar-gz",required=True,type=Path)
    a=ap.parse_args(); a.out_json.parent.mkdir(parents=True,exist_ok=True)
    hold=load_holdout(a.holdout); plates=sorted(hold.plate_id.unique()); assign={p:i%SHARD_COUNT for i,p in enumerate(plates)}
    rps=sorted(a.shards_dir.glob("JANUS-PALOMAR-JPFM-2F-C2B1-SHARD-*-RECEIPT-RUN-001.json"))
    if len(rps)!=SHARD_COUNT: raise RuntimeError(f"expected 10 receipts got {len(rps)}")
    frames=[]; receipts=[]; seen=set(); seenplates=set(); rdigest=[]
    for rp in rps:
        r=json.loads(rp.read_text()); p=dict(r); integ=p.pop("integrity",None)
        if not integ or canon(p)!=integ.get("canonical_payload_sha256_without_integrity"): raise RuntimeError(f"receipt hash {rp.name}")
        idx=int(r["shard"]["index"])
        if idx in seen or r["status"]!="EXECUTED_SHARD_RECEIPT__NO_GLOBAL_OUTCOME_OR_MORPHOLOGY_INFERENCE": raise RuntimeError("receipt status/index")
        if r["bindings"]["admission_canonical_sha256"]!=ADMISSION_CANON or r["bindings"]["dedup_addendum_canonical_sha256"]!=DEDUP_CANON or r["bindings"]["holdout_canonical_sha256"]!=HOLDOUT_CANON: raise RuntimeError("receipt binding")
        if r["external_label_firewall"]["external_label_reveal_authorized"] is not False: raise RuntimeError("firewall")
        exp=[p for p in plates if assign[p]==idx]; got=[str(x) for x in r["shard"]["assigned_plates"]]
        if got!=exp: raise RuntimeError(f"plate partition {idx}")
        if seenplates.intersection(got): raise RuntimeError("plate overlap")
        seenplates.update(got); seen.add(idx); rdigest.append(integ["canonical_payload_sha256_without_integrity"])
        sp=a.shards_dir/r["sidecar"]["path"]
        gz=sp.read_bytes(); raw=gzip.decompress(gz)
        if sha(gz)!=r["sidecar"]["gzip_sha256"] or sha(raw)!=r["sidecar"]["csv_sha256"]: raise RuntimeError("sidecar hash")
        d=pd.read_csv(io.BytesIO(raw)); d["src_id"]=d.src_id.astype(str)
        if len(d)!=r["sidecar"]["rows"] or d.src_id.duplicated().any():raise RuntimeError("sidecar rows")
        frames.append(d); receipts.append(r)
    if seen!=set(range(SHARD_COUNT)) or seenplates!=set(plates):raise RuntimeError("partition incomplete")
    full=pd.concat(frames,ignore_index=True); full["src_id"]=full.src_id.astype(str)
    if len(full)!=EXPECTED_ROWS or full.src_id.nunique()!=EXPECTED_ROWS or set(full.src_id)!=set(hold.src_id): raise RuntimeError("128 union")
    # Frozen context identity.
    ck=full.merge(hold[["src_id","plate_id","tile_id","object_id","structural_cluster","sample_role"]],on="src_id",suffixes=("","_frozen"),validate="one_to_one")
    for c in ["plate_id","tile_id","object_id","structural_cluster","sample_role"]:
        if not (ck[c].astype(str)==ck[c+"_frozen"].astype(str)).all():raise RuntimeError(f"context drift {c}")

    exact=full.exact_object_status.astype(str).eq("EXACT_NUMBER_RECOVERED")
    exact_n=int(exact.sum()); exact_frac=exact_n/EXPECTED_ROWS
    sep=pd.to_numeric(full.get("pass2_to_s0_sep_arcsec"),errors="coerce")
    sep_frac=float((exact & np.isfinite(sep) & (sep<=10)).sum()/exact_n) if exact_n else 0.0
    raw=full.loc[exact,["FWHM_IMAGE","ELONGATION","SPREAD_MODEL"]].apply(pd.to_numeric,errors="coerce").to_numpy(float) if exact_n else np.empty((0,3))
    raw_frac=float(np.isfinite(raw).all(axis=1).mean()) if exact_n else 0.0
    shape_failed=pd.to_numeric(full.get("shape_failed"),errors="coerce").fillna(1).astype(int)
    shape_frac=float((exact & shape_failed.eq(0)).sum()/exact_n) if exact_n else 0.0
    refcount=pd.to_numeric(full.get("reference_count"),errors="coerce")
    z=full[ZCOLS].apply(pd.to_numeric,errors="coerce").to_numpy(float)
    norm=full.reference_support_status.astype(str).eq("PASS") & (refcount>=REF_MIN) & np.isfinite(z).all(axis=1)
    norm_n=int(norm.sum()); norm_frac=norm_n/EXPECTED_ROWS
    plate_recs=[x for r in receipts for x in r["execution"]["plate_receipts"]]
    plate_pass=sum(str(x.get("plate_status"))=="PASS" for x in plate_recs); plate_frac=plate_pass/EXPECTED_PLATES
    processed=sum(int(x.get("grid_cells_processed",0)) for x in plate_recs); detcells=sum(int(x.get("detection_pass_cells",0)) for x in plate_recs)
    gates={
      "plate_and_target_tile_replay":{"pass":plate_frac>=0.95 and exact_frac>=0.90,"plate_pass":plate_pass,"plate_fraction":plate_frac,"exact_target_rows":exact_n,"exact_target_fraction":exact_frac,"required_plate_fraction":0.95,"required_exact_fraction":0.90},
      "sky_consistency":{"pass":sep_frac>=0.90,"le10arcsec_fraction_among_exact":sep_frac,"required_fraction":0.90,"separation_arcsec":qstats(sep[exact])},
      "raw_upstream_morphology":{"pass":raw_frac>=0.95,"finite_fraction_among_exact":raw_frac,"required_fraction":0.95},
      "shape_execution":{"pass":shape_frac>=0.90,"success_fraction_among_exact":shape_frac,"required_fraction":0.90},
      "reference_normalization":{"pass":norm_frac>=0.80,"pass_rows":norm_n,"pass_fraction":norm_frac,"required_fraction":0.80,"minimum_reference_stars":20,"reference_count":qstats(refcount)}
    }
    if not gates["plate_and_target_tile_replay"]["pass"]: outcome="FAIL_CLOSED_TARGET_TILE_OR_OBJECT_REPLAY"
    elif not gates["sky_consistency"]["pass"]: outcome="FAIL_CLOSED_SKY_CONSISTENCY"
    elif not gates["raw_upstream_morphology"]["pass"]: outcome="FAIL_CLOSED_RAW_UPSTREAM_MORPHOLOGY"
    elif not gates["shape_execution"]["pass"]: outcome="FAIL_CLOSED_SHAPE_REPLAY"
    elif not gates["reference_normalization"]["pass"]: outcome="FAIL_CLOSED_SPATIAL_REFERENCE_SUPPORT_REPAIR"
    else: outcome="PASS_SPATIAL_REFERENCE_SUPPORT_ENGINEERING_GATE"
    ring=pd.to_numeric(full.get("selected_reference_ring"),errors="coerce")
    ring_census={str(i):int((ring==i).sum()) for i in range(4)}; ring_census["none"]=int(ring.isna().sum())
    cluster=[]
    for (cl,role),g in full.assign(_norm=norm).groupby(["structural_cluster","sample_role"],sort=True):
        cluster.append({"cluster":int(cl),"sample_role":str(role),"rows":int(len(g)),"normalization_pass":int(g._norm.sum()),"normalization_fraction":float(g._norm.mean()),"reference_count":qstats(g.reference_count)})
    full=full.sort_values(["structural_cluster","sample_role","src_id"],kind="stable").reset_index(drop=True)
    rawcsv=full.to_csv(index=False,lineterminator="\n",float_format="%.12g").encode(); csvsha=sha(rawcsv)
    with a.out_sidecar_gz.open("wb") as f:
        with gzip.GzipFile(filename="",mode="wb",fileobj=f,mtime=0) as zz:zz.write(rawcsv)
    gzsha=sha(a.out_sidecar_gz.read_bytes())
    result={
      "artifact_id":"JANUS-PALOMAR-JPFM-2F-C2B1-SPATIAL-REFERENCE-SUPPORT-ENGINEERING-RUN-001","experiment_id":"JPFM-2F-C2B1","schema_version":"1.0",
      "date":pd.Timestamp.utcnow().date().isoformat(),"status":"EXECUTED_AND_SHARD_INTEGRITY_VERIFIED","engineering_outcome":outcome,
      "claim_ceiling":"REFERENCE_SUPPORT_ENGINEERING_ONLY__NO_MORPHOLOGY_ASSOCIATION_INFERENCE__NO_EXTERNAL_LABEL_REVEAL__NO_CAUSAL_OR_ORIGIN_CLAIM",
      "bindings":{"admission_canonical_sha256":ADMISSION_CANON,"dedup_addendum_canonical_sha256":DEDUP_CANON,"holdout_canonical_sha256":HOLDOUT_CANON,"holdout_csv_sha256":HOLDOUT_CSV_SHA,"holdout_gzip_sha256":HOLDOUT_GZ_SHA},
      "shard_integrity":{"pass":True,"shards":10,"receipt_canonical_sha256":rdigest,"plates_union":len(seenplates),"source_rows_union":len(full),"source_ids_unique":full.src_id.nunique()},
      "transport_and_compute":{"plate_grid_cells_processed":processed,"detection_pass_cells":detcells,"full_grid_capacity_if_all_plates":EXPECTED_PLATES*49,"adaptive_fraction_of_full_grid":float(processed/(EXPECTED_PLATES*49)),"full_remote_plate_array_accessed":False},
      "engineering_gates":gates,"selected_ring_census":ring_census,"cluster_role_support_census":cluster,
      "morphology_association_inference":{"status":"FORBIDDEN_IN_C2B1_ENGINEERING_REPLAY","executed":False},
      "external_label_firewall":{"external_label_reveal_authorized":False,"date_or_external_environment_used":False},
      "sidecar":{"path":str(a.out_sidecar_gz),"rows":128,"csv_sha256":csvsha,"gzip_sha256":gzsha},
      "next_gate":"FREEZE_C2B2_NEW_NONOVERLAPPING_512_PLUS_HOLDOUT_BEFORE_MORPHOLOGY_INFERENCE" if outcome=="PASS_SPATIAL_REFERENCE_SUPPORT_ENGINEERING_GATE" else "PRESERVE_C2B1_NEGATIVE_CERTIFICATE__LOCALIZE_FAILURE_WITHOUT_THRESHOLD_RELAXATION"
    }
    result["integrity"]={"canonical_payload_sha256_without_integrity":canon(result)}
    a.out_json.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print("C2B1_ENGINEERING_OUTCOME",outcome,"norm",norm_n,"/128","rings",ring_census,"cells",processed,flush=True)
    print("C2B1_RESULT_CANONICAL",result["integrity"]["canonical_payload_sha256_without_integrity"],flush=True)

if __name__=="__main__":main()
