#!/usr/bin/env python3
"""Freeze C2B1 128-source engineering holdout before any new pixel replay."""
from __future__ import annotations
import argparse, gzip, hashlib, io, json
from pathlib import Path
import numpy as np
import pandas as pd

ADMISSION_CANON="27373cc8f40fe8a368d42e05c6541bc77a1c5f95eb589f1bc0ec9b8ceaafd751"
C0M_CSV_SHA="d41bfc95e9f0219d76ee383d057938287dcaaef8ba5005c66414d4a2422f75c0"
C0M_GZ_SHA="8493e1dc6b3d89ecd1984d0826b663f2a12ede9664a3c5bb4812b51b6d3a0eca"
C2A_CSV_SHA="a3656b181648e5abf933859199b5712e945b932610fffdd6c810785cff341b21"
C2A_GZ_SHA="3d4c7513b4add64324fddeedd04e9379b415f729fb36a76d977b871845638ca7"
N_PER_ROLE=4
CLUSTERS=16
EXPECTED=128

def h(b): return hashlib.sha256(b).hexdigest()
def canon(o): return h(json.dumps(o,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode())
def load(path,gzsha,csvsha):
    gz=path.read_bytes()
    if h(gz)!=gzsha: raise RuntimeError(f"{path.name}: gzip hash mismatch")
    raw=gzip.decompress(gz)
    if h(raw)!=csvsha: raise RuntimeError(f"{path.name}: csv hash mismatch")
    return pd.read_csv(io.BytesIO(raw))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--admission",required=True,type=Path)
    ap.add_argument("--c0m-map",required=True,type=Path)
    ap.add_argument("--c2a-sample",required=True,type=Path)
    ap.add_argument("--out-json",required=True,type=Path)
    ap.add_argument("--out-gz",required=True,type=Path)
    a=ap.parse_args(); a.out_json.parent.mkdir(parents=True,exist_ok=True)

    print("[C2B1 holdout] [1/5] verify admission",flush=True)
    adm=json.loads(a.admission.read_text())
    p=dict(adm); integ=p.pop("integrity")
    if canon(p)!=integ["canonical_payload_sha256_without_integrity"] or integ["canonical_payload_sha256_without_integrity"]!=ADMISSION_CANON:
        raise RuntimeError("C2B1 admission canonical mismatch")
    if adm["status"]!="PREREGISTERED_AFTER_C2B0_DIAGNOSTIC_BEFORE_C2B1_HOLDOUT_FREEZE_OR_PIXEL_REPLAY":
        raise RuntimeError("C2B1 admission status mismatch")
    if adm["engineering_holdout"]["rows"]!=128 or adm["engineering_holdout"]["typical_per_cluster"]!=4 or adm["engineering_holdout"]["unusual_per_cluster"]!=4:
        raise RuntimeError("C2B1 holdout contract drift")
    if adm["reference_star_contract"]["minimum_reference_stars"]!=20:
        raise RuntimeError("C2B1 minimum reference drift")
    if adm["external_label_firewall"]["external_label_reveal_authorized"] is not False:
        raise RuntimeError("C2B1 firewall open")

    print("[C2B1 holdout] [2/5] hash-gate C0M and C2A sample",flush=True)
    m=load(a.c0m_map,C0M_GZ_SHA,C0M_CSV_SHA); m["src_id"]=m.src_id.astype(str); m["tile_id"]=m.tile_id.astype(str)
    c2a=load(a.c2a_sample,C2A_GZ_SHA,C2A_CSV_SHA); c2a["src_id"]=c2a.src_id.astype(str); c2a["tile_id"]=c2a.tile_id.astype(str)
    if len(m)!=122820 or m.src_id.nunique()!=122820: raise RuntimeError("C0M invariant")
    if len(c2a)!=512 or c2a.src_id.nunique()!=512: raise RuntimeError("C2A sample invariant")
    old_src=set(c2a.src_id); old_tiles=set(c2a.tile_id)

    print("[C2B1 holdout] [3/5] deterministic source/tile-disjoint selection",flush=True)
    selected=[]; pool_census=[]
    m["structural_cluster"]=pd.to_numeric(m.structural_cluster,errors="raise").astype(int)
    m["anomaly_score"]=pd.to_numeric(m.anomaly_score,errors="raise").astype(float)
    for cl in range(CLUSTERS):
        allc=m[m.structural_cluster==cl].copy()
        med=float(allc.anomaly_score.median())
        pool=allc[(~allc.src_id.isin(old_src)) & (~allc.tile_id.isin(old_tiles))].copy()
        pool["_median_distance"]=(pool.anomaly_score-med).abs()
        pool_census.append({"cluster":cl,"full_rows":int(len(allc)),"eligible_after_C2A_src_tile_exclusion":int(len(pool)),
                            "eligible_distinct_tiles":int(pool.tile_id.nunique()),"eligible_distinct_plates":int(pool.plate_id.nunique())})
        if len(pool)<2*N_PER_ROLE:
            raise RuntimeError(f"cluster {cl}: insufficient tile-disjoint pool {len(pool)}")
        typ=pool.sort_values(["_median_distance","src_id"],kind="stable").head(N_PER_ROLE).copy()
        typ["sample_role"]="typical"
        used=set(typ.src_id)
        unu=pool[~pool.src_id.isin(used)].sort_values(["anomaly_score","src_id"],ascending=[False,True],kind="stable").head(N_PER_ROLE).copy()
        if len(unu)!=N_PER_ROLE: raise RuntimeError(f"cluster {cl}: unusual underflow")
        unu["sample_role"]="unusual"
        selected += [typ,unu]
    out=pd.concat(selected,ignore_index=True)
    keep=["src_id","tile_id","object_id","plate_id","ra","dec","structural_cluster","sample_role","anomaly_score",
          "tile_x0","tile_y0","fullplate_x0","fullplate_y0","local_pixel_scale_arcsec","distance_to_tile_edge_px",
          "tan_refit_median_arcsec","tan_refit_max_arcsec","crpix_dx","crpix_dy"]
    out=out[keep].sort_values(["structural_cluster","sample_role","src_id"],kind="stable").reset_index(drop=True)

    print("[C2B1 holdout] [4/5] enforce independence and balance",flush=True)
    if len(out)!=EXPECTED or out.src_id.nunique()!=EXPECTED: raise RuntimeError("C2B1 row/unique invariant")
    if set(out.src_id)&old_src: raise RuntimeError("C2B1 source overlap C2A")
    if set(out.tile_id)&old_tiles: raise RuntimeError("C2B1 tile overlap C2A")
    for cl in range(CLUSTERS):
        g=out[out.structural_cluster==cl]
        if len(g)!=8 or int((g.sample_role=="typical").sum())!=4 or int((g.sample_role=="unusual").sum())!=4:
            raise RuntimeError(f"C2B1 balance failure cluster {cl}")

    raw=out.to_csv(index=False,lineterminator="\n",float_format="%.12g").encode()
    csvsha=h(raw)
    with a.out_gz.open("wb") as f:
        with gzip.GzipFile(filename="",mode="wb",fileobj=f,mtime=0) as z: z.write(raw)
    gzsha=h(a.out_gz.read_bytes())
    overlap_plates=len(set(out.plate_id.astype(str)) & set(c2a.plate_id.astype(str)))

    print("[C2B1 holdout] [5/5] freeze manifest",flush=True)
    result={
      "artifact_id":"JANUS-PALOMAR-JPFM-2F-C2B1-ENGINEERING-HOLDOUT-FREEZE-RUN-001",
      "experiment_id":"JPFM-2F-C2B1-HOLDOUT-FREEZE","schema_version":"1.0",
      "date":pd.Timestamp.utcnow().date().isoformat(),
      "status":"FROZEN_BEFORE_C2B1_PIXEL_REPLAY",
      "claim_ceiling":"ENGINEERING_HOLDOUT_FREEZE_ONLY__NO_NEW_PIXEL_MEASUREMENT__NO_MORPHOLOGY_INFERENCE__NO_EXTERNAL_LABEL_REVEAL",
      "bindings":{"C2B1_admission_canonical_sha256":ADMISSION_CANON,"C0M_csv_sha256":C0M_CSV_SHA,"C0M_gzip_sha256":C0M_GZ_SHA,
                  "C2A_sample_csv_sha256":C2A_CSV_SHA,"C2A_sample_gzip_sha256":C2A_GZ_SHA},
      "selection":{"rows":128,"clusters":16,"typical_per_cluster":4,"unusual_per_cluster":4,
                   "source_overlap_with_C2A":0,"tile_overlap_with_C2A":0,"plate_overlap_with_C2A":int(overlap_plates),
                   "distinct_tiles":int(out.tile_id.nunique()),"distinct_plates":int(out.plate_id.nunique()),
                   "pixel_or_morphology_features_used":False,"external_labels_used":False},
      "pool_census":pool_census,
      "manifest":{"path":str(a.out_gz),"rows":128,"columns":keep,"csv_sha256":csvsha,"gzip_sha256":gzsha},
      "external_label_firewall":{"external_label_reveal_authorized":False},
      "next_gate":"JPFM_2F_C2B1_SPATIAL_REFERENCE_SUPPORT_ENGINEERING_REPLAY"
    }
    result["integrity"]={"canonical_payload_sha256_without_integrity":canon(result)}
    a.out_json.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print("C2B1_HOLDOUT_FROZEN",len(out),"tiles",out.tile_id.nunique(),"plates",out.plate_id.nunique(),"plate_overlap_C2A",overlap_plates,flush=True)
    print("C2B1_HOLDOUT_CSV_SHA256",csvsha,flush=True)
    print("C2B1_HOLDOUT_CANONICAL",result["integrity"]["canonical_payload_sha256_without_integrity"],flush=True)

if __name__=="__main__": main()
