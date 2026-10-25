#!/usr/bin/env python3
"""Fail-closed BBC1 score provenance gate; no provider calls or spending.

Reference metadata establishes phenotype name and sign, not identity of each raw
and processed numeric row. Primary raw row verification is an explicit gate.
"""
from __future__ import annotations
import argparse, csv, hashlib, io, json, math
from pathlib import Path

DMS_ID="BBC1_YEAST_Tsuboyama_2023_1TG0"
WT="EVPFKVVAQFPYKSDYEDDLNFEKDQEIIVTSVEDAEWYFGEYQDSNGDVIEGIFPKSFVAVQG"
METADATA_BLOB_SHA="8d1ea9a19c0404b511cd24378b25c2a5f86f10e9"
TSV_SHA="ca355a655381c95fe899d61a406251e0cd17d68bbabe287651d526fdeb821f87"
RAW_NAME="Tsuboyama2023_Dataset2_Dataset5"
MUTATIONS=("G53A","G48D","E27F","W38L","K13N","G64Q","Q44V","E42H")
RAW_COL="ddG_ML_float"

class GateHold(ValueError):pass

def exact_sha(blob,expected):
    if hashlib.sha256(blob).hexdigest()!=expected:raise GateHold("PROCESSED_SHA256_DRIFT")

def git_blob_sha(raw):
    return hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()

def mutation_sequence(mut):
    position=int(mut[1:-1])-1
    if position<0 or position>=len(WT) or WT[position]!=mut[0]:
        raise GateHold("WRONG_FROZEN_MUTATION")
    return WT[:position]+mut[-1]+WT[position+1:]

def finite(s):
    try:val=float(s)
    except (TypeError,ValueError):raise GateHold("INVALID_SCORE")
    if not math.isfinite(val):raise GateHold("NONFINITE_SCORE")
    return val

def verify_metadata(raw):
    if git_blob_sha(raw)!=METADATA_BLOB_SHA:raise GateHold("METADATA_SOURCE_BLOB_DRIFT")
    entries=[r for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
             if r.get("DMS_id")==DMS_ID]
    if len(entries)!=1:raise GateHold("METADATA_ASSAY_NOT_UNIQUE")
    r=entries[0]
    expected={
        "raw_DMS_phenotype_name":RAW_COL,
        "raw_DMS_directionality":"1",
        "raw_DMS_filename":RAW_NAME,
        "raw_DMS_mutant_column":"mut_type",
        "target_seq":WT,
        "seq_len":"64",
        "selection_type":"cDNA display proteolysis",
        "DMS_number_single_mutants":"1084",
    }
    for k,v in expected.items():
        if r.get(k)!=v:raise GateHold("METADATA_DRIFT_"+k)
    return {k:r[k] for k in expected}

def verify_processed(blob,receipt):
    exact_sha(blob,TSV_SHA)
    d=csv.DictReader(io.StringIO(blob.decode("utf-8-sig")),delimiter="\t")
    if not {"sequences","labels","fold_id"} <= set(d.fieldnames or []):
        raise GateHold("INVALID_PROCESSED_SCHEMA")
    targets={mutation_sequence(mut):mut for mut in MUTATIONS}
    observed={}
    for r in d:
        seq=(r.get("sequences") or "").strip()
        if seq not in targets:continue
        if seq in observed:raise GateHold("DUPLICATED_PROCESSED_SEQUENCE")
        score=finite(r.get("labels"))
        observed[seq]=score
        fold=r.get("fold_id")
        try:fold_i=int(fold)
        except (ValueError,TypeError):raise GateHold("INVALID_FOLD_ID")
        if not 0<=fold_i<=4:raise GateHold("INVALID_FOLD_ID")
    if len(observed)!=8:raise GateHold("MISSING_PROCESSED_FROZEN_ROW")
    if receipt.get("schema_id")!="janus.meta_registry.rowan_evidence_receipt.v1":
        raise GateHold("INVALID_ARCHIVED_RECEIPT")
    if receipt.get("original_public_data_sha256")!=TSV_SHA:
        raise GateHold("RECEIPT_PROCESSED_SHA_DRIFT")
    cases=receipt.get("cases")
    if not isinstance(cases,list) or len(cases)!=8:
        raise GateHold("FROZEN_CASE_COUNT_DRIFT")
    for case,mut in zip(cases,MUTATIONS):
        if case.get("mutation")!=mut:raise GateHold("FROZEN_MUTATION_ORDER_DRIFT")
        score=finite(case.get("published_processed_label"))
        if abs(observed[mutation_sequence(mut)]-score)>1e-9:
            raise GateHold("ARCHIVED_TO_PROCESSED_ROW_MISMATCH_"+mut)
    return {mut:observed[mutation_sequence(mut)] for mut in MUTATIONS}

def verify_raw(raw_bytes,observed):
    # Original ProteinGym raw DMS rows are not available in archived Rowan receipts.
    # Stream the independently supplied assay's RAW CSV and require exact 8 identities.
    raw=csv.DictReader(io.StringIO(raw_bytes.decode("utf-8-sig")))
    if not {RAW_COL,"mut_type","aa_seq"} <= set(raw.fieldnames or []):
        raise GateHold("RAW_ASSAY_FIELDS_MISSING")
    hits={}
    for row in raw:
        mut=(row.get("mut_type") or "").strip()
        if mut not in MUTATIONS:continue
        if (row.get("aa_seq") or "").strip()!=mutation_sequence(mut):
            continue
        if mut in hits:raise GateHold("RAW_MUTATION_NOT_UNIQUE_"+mut)
        hits[mut]=finite(row.get(RAW_COL))
    if set(hits)!=set(MUTATIONS):
        raise GateHold("RAW_ASSAY_EIGHT_ROWS_NOT_FOUND")
    for mut,value in hits.items():
        if abs(value-observed[mut])>1e-9:
            raise GateHold("RAW_TO_PROCESSED_TRANSFORM_NOT_IDENTITY_"+mut)
    return hits

def run(metadata,processed,receipt,raw=None):
    metadata_info=verify_metadata(metadata)
    observed=verify_processed(processed,receipt)
    raw_rows=verify_raw(raw,observed) if raw is not None else None
    return {
        "schema_id":"janus.rowan.bbc1.primary_score_audit.v1",
        "status":"PASS_EXACT_EIGHT_RAW_PROCESSED_ROW_IDENTITY" if raw_rows is not None
                 else "HOLD_RAW_ROW_IDENTITY_NOT_CHECKED",
        "assay_id":DMS_ID,
        "score_direction":"POSITIVE_IS_STABILIZING",
        "source_column":RAW_COL,
        "source_directionality":1,
        "source_paper_unit":"kcal/mol for delta-delta folding stability",
        "source_paper_doi":"10.1038/s41586-023-06328-6",
        "source_metadata_blob_sha":METADATA_BLOB_SHA,
        "source_processed_sha256":TSV_SHA,
        "observed_frozen_processed_labels":observed,
        "raw_rows_verified":raw_rows is not None,
        "raw_rows":raw_rows,
        "qualification":"Reference metadata and paper establish direction/unit; do not claim original row-level unit/transform identity before RAW CSV validation.",
        "model_production_promotion":False,
        "new_rowan_provider_jobs":0,
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--metadata",required=True,type=Path)
    parser.add_argument("--processed",required=True,type=Path)
    parser.add_argument("--receipt",required=True,type=Path)
    parser.add_argument("--raw",type=Path,help="Independent original ProteinGym BBC1 raw assay CSV")
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    try:
        if args.output.exists():raise GateHold("IMMUTABLE_OUTPUT_EXISTS")
        result=run(args.metadata.read_bytes(),args.processed.read_bytes(),
                   json.loads(args.receipt.read_text(encoding="utf-8")),
                   args.raw.read_bytes() if args.raw else None)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("x",encoding="utf-8") as f:
            json.dump(result,f,indent=2,allow_nan=False)
            f.write("\n")
        print("ROWAN_PRIMARY_LABEL_GATE="+result["status"])
        return 0 if result["raw_rows_verified"] else 2
    except (GateHold,OSError,ValueError) as exc:
        # Only an error code; never emit unreviewed source text.
        print("ROWAN_PRIMARY_LABEL_GATE=HOLD_"+str(exc))
        return 2

if __name__=="__main__":raise SystemExit(main())
