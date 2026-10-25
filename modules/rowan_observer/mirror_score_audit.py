#!/usr/bin/env python3
"""Reproduce eight BBC1 raw-versus-processed comparisons using a pinned raw mirror.

A public mirror is secondary evidence, not original laboratory-source attestation.
Nonzero return on any mismatch. Never adjusts historic targets or fitted weights.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import primary_score_gate as base

MIRROR_COMMIT="b8319fa062ed22d86b329cddd40418234df7f1d8"
MIRROR_PATH=("tables/data_unpacked_labeled_proteingym_raw_proteingym_v1.3_"
 "substitutions_raw_DMS_substitutions_raw_DMS_"
 "BBC1_YEAST_Tsuboyama_2023_1TG0.csv.jsonl")
MIRROR_SHA256="72621b29b9ea84e89cabc97c5854ce9a6de19a9a517fd1f6414f250156d4de03"
REPORTED_SOURCE_PATH=("data/unpacked/labeled/proteingym_raw/proteingym/v1.3/"
 "substitutions_raw_DMS/substitutions_raw_DMS/"
 "BBC1_YEAST_Tsuboyama_2023_1TG0.csv")

def audit(metadata_bytes,processed_bytes,receipt,mirror_bytes):
    meta=base.verify_metadata(metadata_bytes)
    processed=base.verify_processed(processed_bytes,receipt)
    digest=hashlib.sha256(mirror_bytes).hexdigest()
    if digest!=MIRROR_SHA256:
        raise base.GateHold("PINNED_MIRROR_SHA256_DRIFT")
    expected=set(base.MUTATIONS)
    raw={}
    try:
        text=mirror_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise base.GateHold("RAW_MIRROR_NOT_UTF8") from exc
    for line in text.splitlines():
        if not line.strip():continue
        row=json.loads(line)
        if row.get("dataset_id")!="proteingym_raw":
            raise base.GateHold("RAW_MIRROR_DATASET_ID_DRIFT")
        if row.get("source_file")!=REPORTED_SOURCE_PATH:
            raise base.GateHold("RAW_MIRROR_SOURCE_PATH_DRIFT")
        fields=row.get("row")
        if not isinstance(fields,dict):raise base.GateHold("INVALID_RAW_MIRROR_ROW")
        mut=fields.get("mut_type")
        if mut not in expected:continue
        if fields.get("mut_class")!="single":
            raise base.GateHold("RAW_MIRROR_MUTATION_CLASS_DRIFT")
        if fields.get("WT_name")!="1TG0.pdb":
            raise base.GateHold("RAW_MIRROR_WT_NAME_DRIFT")
        if fields.get("aa_seq")!=base.mutation_sequence(mut):
            raise base.GateHold("RAW_MIRROR_SEQUENCE_DRIFT_"+mut)
        if mut in raw:raise base.GateHold("RAW_MIRROR_DUPLICATE_"+mut)
        val=base.finite(fields.get(base.RAW_COL))
        idx=row.get("row_index")
        if not isinstance(idx,int) or idx<0:raise base.GateHold("RAW_MIRROR_ROW_ID_INVALID")
        raw[mut]={"raw_score":val,"row_index":idx}
    if set(raw)!=expected:raise base.GateHold("RAW_MIRROR_MISSING_FROZEN_ROWS")
    comparison=[]
    for mut in base.MUTATIONS:
        score=processed[mut];obs=raw[mut]["raw_score"]
        comparison.append({
            "mutation":mut,"raw_mirror_row_index":raw[mut]["row_index"],
            "processed_label":score,"mirrored_raw_ddG_ML_float":obs,
            "processed_minus_raw":score-obs,
            "match_tolerance_1e_9":abs(score-obs)<=1e-9
        })
    failed=[x["mutation"] for x in comparison if not x["match_tolerance_1e_9"]]
    return {
      "schema_id":"janus.rowan.bbc1.mirrored_raw_score_discrepancy.v1",
      "status":"HOLD_RAW_MIRROR_PROCESSED_MISMATCH" if failed else
               "MATCH_IN_SECONDARY_MIRROR_PRIMARY_SOURCE_UNVERIFIED",
      "independent_mirror_repository":"LiteFold/ProteinGym",
      "independent_mirror_revision":MIRROR_COMMIT,
      "independent_mirror_path":MIRROR_PATH,
      "independent_mirror_sha256":digest,
      "reported_original_source_path":REPORTED_SOURCE_PATH,
      "score_name":base.RAW_COL,
      "score_directionality":int(meta["raw_DMS_directionality"]),
      "thermodynamic_paper_unit":"kcal/mol",
      "pinned_processed_sha256":base.TSV_SHA,
      "original_2023_lab_csv_sha256":"UNVERIFIED",
      "primary_lab_bytewise_validation":"NOT_DONE",
      "n_compared":len(comparison),
      "n_matching":len(comparison)-len(failed),
      "n_discrepant":len(failed),
      "discrepant_mutations":failed,
      "all_comparisons":comparison,
      "free_provider_submissions":0,
      "model_retraining_permitted":False,
      "model_production_promotion":False,
      "scientific_interpretation":"Mirrored public raw DMS and pinned third-party processed DMS disagree; no silent sign/offset adjustment or target correction. Determine version/transform from original published source before reusing labels.",
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--metadata",required=True,type=Path)
    p.add_argument("--processed",required=True,type=Path)
    p.add_argument("--receipt",required=True,type=Path)
    p.add_argument("--mirror-jsonl",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    try:
        if a.output.exists():raise base.GateHold("OUTPUT_EXISTS")
        value=audit(a.metadata.read_bytes(),a.processed.read_bytes(),
          json.loads(a.receipt.read_text(encoding="utf-8")),a.mirror_jsonl.read_bytes())
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        print("ROWAN_MIRROR_SCORE_AUDIT="+value["status"])
        print("ROWAN_MIRROR_SCORE_N_MATCHING="+str(value["n_matching"]))
        print("ROWAN_MIRROR_SCORE_N_DISCREPANT="+str(value["n_discrepant"]))
        return 2 if value["n_discrepant"] else 0
    except (base.GateHold,ValueError,OSError) as exc:
        print("ROWAN_MIRROR_SCORE_AUDIT=HOLD_"+str(exc))
        return 2

if __name__=="__main__":raise SystemExit(main())
