#!/usr/bin/env python3
"""Run-independent BBC1 Boltz2 bridge receipt generator.

Only source-backed published structural scores. No Rowan API, no FireProt labels.
Uses single-sequence, MSA-free input as smoke test; cannot prove the original
Rowan S2 provider configuration or transfer metrics.
"""
from __future__ import annotations
import argparse,hashlib,json,math,os,sys
from pathlib import Path
from datetime import datetime, timezone

BBC1_WT="EVPFKVVAQFPYKSDYEDDLNFEKDQEIIVTSVEDAEWYFGEYQDSNGDVIEGIFPKSFVAVQG"
REFERENCE={
  "BBC1_WT":{"ptm":0.927,"avg_lddt":0.963},
  "BBC1_G53A":{"ptm":0.918,"avg_lddt":0.968}
}
CASES=("BBC1_WT","BBC1_G53A")
S2_SOURCE_RECEIPT_SHA256="c7f0ffb81e490d6dd555d1b6b073838ec0ed9fffd9c6fe6551b781023aaeeb06"
SOURCE_RECEIPT="data/rowan/receipts/ROWAN-S2-40236409772-51508154de2623c0.json"
PARAMETERS={
 "model":"boltz2",
 "msa_mode":"empty",
 "accelerator":"gpu",
 "no_kernels":True,
 "recycling_steps":3,
 "sampling_steps":200,
 "diffusion_samples":1,
 "seed":20261026,
 "num_workers":0,
 "preprocessing_threads":2
}

class Hold(ValueError):pass
def sha(b):return hashlib.sha256(b).hexdigest()

def cases():
    assert len(BBC1_WT)==64 and BBC1_WT[52]=="G"
    return {"BBC1_WT":BBC1_WT,"BBC1_G53A":BBC1_WT[:52]+"A"+BBC1_WT[53:]}

def yaml_payload(sequence):
    if len(sequence)!=64 or not sequence.isalpha():
        raise Hold("BBC1_INPUT_SEQUENCE_INVALID")
    return f"sequences:\n  - protein:\n      id: A\n      sequence: {sequence}\n      msa: empty\n".encode()

def generate_inputs(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    seqs=cases();records={}
    for name,seq in seqs.items():
        dest=folder/(name+".yaml")
        b=yaml_payload(seq)
        if dest.exists():
            actual=dest.read_bytes()
            # Windows newline conversion is bytewise distinct but YAML-equivalent.
            # Preserve the *actual* input hash: never rewrite an already used file.
            if actual.replace(b"\r\n",b"\n")!=b:
                raise Hold("FROZEN_YAML_INPUT_WOULD_CHANGE_"+name)
        else:
            dest.write_bytes(b)
            actual=b
        records[name]={"sequence_sha256":sha(seq.encode()),
                       "yaml_sha256":sha(actual),
                       "normalized_yaml_sha256":sha(b),
                       "original_input_line_endings":"CRLF" if b"\r\n" in actual else "LF",
                       "sequence_length":len(seq)}
    return records

def confidence_score(blob):
    doc=json.loads(blob)
    # Official Boltz-2 .json stores the pTM and average protein confidence.
    if not isinstance(doc,dict) or "ptm" not in doc or "complex_plddt" not in doc:
        raise Hold("REAL_BOLTZ2_CONFIDENCE_FIELDS_MISSING")
    scores={}
    for key in ("ptm","complex_plddt"):
        val=doc[key]
        if isinstance(val,bool) or not isinstance(val,(float,int)) or not math.isfinite(val) or not 0<=val<=1:
            raise Hold("BOLTZ2_CONFIDENCE_RANGE_BAD_"+key)
        scores[key]=float(val)
    return scores

def audit(root,confidence_files,model_ckpt=None):
    root=Path(root)
    source=generate_inputs(root)
    out={
      "schema_id":"janus.rowan.bbc1.local_boltz2_pair_smoke.v1",
      "recorded_utc":datetime.now(timezone.utc).isoformat(),
      "status":"HOLD_NO_LOCAL_BOLTZ2_PREDICTIONS",
      "scientific_status":"COMPATIBILITY_UNPROVEN",
      "source_reference":{"rowan_s2_provider_receipt":SOURCE_RECEIPT,
                          "rowan_s2_provider_receipt_sha256":S2_SOURCE_RECEIPT_SHA256,
                          "rowan_expected":REFERENCE},
      "inputs":source,
      "intended_parameters":PARAMETERS,
      "actual_provider_version_and_MSA_matches_original_rowan":"UNKNOWN_NOT_ATTESTED",
      "source_equivalence_constraints":"Official Boltz-2 complex_plddt is a candidate mean confidence proxy; Rowan avg_lddt must not be assumed identical without exact model/MSA/parameter provenance.",
      "rowan_external_credits_used":0,
      "model_training_or_refit":False,
      "production_promotion":False,
      "FireProt_outcome_labels_accessed":False,
      "local_confidence_files":{},
      "comparison":{}
    }
    scores={}
    for case in CASES:
        supplied=confidence_files.get(case)
        if supplied is None:continue
        p=Path(supplied)
        if not p.is_file():raise Hold("NO_REAL_CONFIDENCE_FILE_"+case)
        blob=p.read_bytes()
        score=confidence_score(blob)
        scores[case]=score
        out["local_confidence_files"][case]={"path_name":p.name,"sha256":sha(blob),
                                            "ptm":score["ptm"],"complex_plddt":score["complex_plddt"]}
        out["comparison"][case]={
          "rowan_ptm":REFERENCE[case]["ptm"],
          "local_ptm":score["ptm"],
          "ptm_delta_local_minus_rowan":score["ptm"]-REFERENCE[case]["ptm"],
          "rowan_avg_lddt":REFERENCE[case]["avg_lddt"],
          "local_complex_plddt":score["complex_plddt"],
          "lddt_proxy_delta_unvalidated":score["complex_plddt"]-REFERENCE[case]["avg_lddt"]
        }
    if model_ckpt is not None:
        p=Path(model_ckpt)
        if not p.is_file():raise Hold("BOLTZ2_CHECKPOINT_FILE_NOT_FOUND")
        out["local_checkpoint_sha256"]=sha(p.read_bytes())
        out["local_checkpoint_size_bytes"]=p.stat().st_size
    if len(scores)==2:
        out["status"]="PASS_TWO_LOCAL_BOLTZ2_RESULTS_METRIC_EQUIVALENCE_NOT_ESTABLISHED"
        out["comparison"]["pair_deltas"]={
          "local_delta_ptm":scores["BBC1_G53A"]["ptm"]-scores["BBC1_WT"]["ptm"],
          "rowan_delta_ptm":REFERENCE["BBC1_G53A"]["ptm"]-REFERENCE["BBC1_WT"]["ptm"],
          "local_delta_complex_plddt":scores["BBC1_G53A"]["complex_plddt"]-scores["BBC1_WT"]["complex_plddt"],
          "rowan_delta_avg_lddt":REFERENCE["BBC1_G53A"]["avg_lddt"]-REFERENCE["BBC1_WT"]["avg_lddt"]
        }
    elif len(scores)==1:
        out["status"]="PARTIAL_ONE_LOCAL_BOLTZ2_RESULT_NOT_COMPARABLE"
    return out

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--inputs",required=True,type=Path)
    parser.add_argument("--wt-confidence",type=Path)
    parser.add_argument("--mutant-confidence",type=Path)
    parser.add_argument("--checkpoint",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    a=parser.parse_args()
    try:
        if a.output.exists():raise Hold("IMMUTABLE_RECEIPT_ALREADY_EXISTS")
        r=audit(a.inputs,{"BBC1_WT":a.wt_confidence,
                          "BBC1_G53A":a.mutant_confidence},a.checkpoint)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(r,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf8")
        print("JANUS_BOLTZ2_BBC1_BRIDGE="+r["status"])
        return 0 if r["status"].startswith("PASS_TWO") else 2
    except (Hold,ValueError,OSError) as e:
        print("JANUS_BOLTZ2_BBC1_BRIDGE=HOLD_"+str(e))
        return 2
if __name__=="__main__":raise SystemExit(main())
