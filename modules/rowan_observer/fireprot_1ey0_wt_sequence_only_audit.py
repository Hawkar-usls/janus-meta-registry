#!/usr/bin/env python3
"""Exact-source audit of one external WT-only local Boltz2 result (1EY0).

No FireProt measurement files; does NOT establish archived PDB member identity.
The RCSB 149-residue SEQRES span 6..141 is an independent 136-residue
sequence witness matching source-frozen metadata. A successful output is a
technical smoke check, not experimental stability prediction or validation.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np

FROZEN_WT="KLHKEPATLIKAIDGDTVKLMYKGQPMTFRLLLVDTPETKHPKKGVEKYGPEASAFTKKMVENAKKIEVEFDKGQRTDKYGRGLAYIYADGKMVNEALVRQGLAKVAYVYKPNNTHEQHLRKSEAQAKKEKLNIWS"
FROZEN_SEQ_SHA="94a6f4324114f9e643076e2bfcb727145d400345f4c5feff0607e5c1fb787be1"
FROZEN_YAML_SHA="f6f60fcc0108c0ede7f5e78bbd2e713f131aab0354c0bf5059f50bb4edcbe176"
CASE="1EY0_RCSB_136AA_WT"
class Hold(ValueError):pass
def sha(blob):return hashlib.sha256(blob).hexdigest()

def source_yaml():
    return f"sequences:\n  - protein:\n      id: A\n      sequence: {FROZEN_WT}\n".encode("utf-8")

def audit(input_yaml,output_root,checkpoint):
    if len(FROZEN_WT)!=136 or sha(FROZEN_WT.encode("ascii"))!=FROZEN_SEQ_SHA:
        raise Hold("FROZEN_SOURCE_WT_IDENTITY_DRIFT")
    pinned=source_yaml()
    if sha(pinned)!=FROZEN_YAML_SHA or input_yaml.read_bytes()!=pinned:
        raise Hold("REAL_INPUT_YAML_NOT_FROZEN")
    result_root=output_root/("boltz_results_"+CASE)
    f=sorted(result_root.rglob("confidence_"+CASE+"_model_0.json"))
    if len(f)!=1:raise Hold("REAL_CONFIDENCE_JSON_COUNT_NOT_ONE")
    conf=f[0];blob=conf.read_bytes()
    v=json.loads(blob)
    for k in ("ptm","complex_plddt"):
        if type(v.get(k)) not in (int,float) or not math.isfinite(v[k]) or not 0<=v[k]<=1:
            raise Hold("REAL_CONFIDENCE_SCORE_INVALID_"+k)
    ps=sorted(result_root.rglob("plddt_"+CASE+"_model_0.npz"))
    if len(ps)!=1:raise Hold("REAL_PLDDT_NPZ_COUNT_NOT_ONE")
    with np.load(ps[0],allow_pickle=False) as z:
        if z.files!=["plddt"]:raise Hold("PLDDT_KEYS_NOT_EXACT")
        vals=z["plddt"]
        if vals.shape!=(136,) or not np.isfinite(vals).all():
            raise Hold("PLDDT_RESIDUE_COUNT_OR_FINITE_INVALID")
        mean=float(vals.mean())
    if abs(mean-float(v["complex_plddt"]))>1e-7:
        raise Hold("PER_RESIDUE_MEAN_NOT_COMPLEX_PLDDT")
    msa=sorted(result_root.rglob("*.a3m"))
    names={p.name for p in msa}
    if len(msa)!=2 or names!={"uniref.a3m","bfd.mgnify30.metaeuk30.smag30.a3m"}:
        raise Hold("REAL_MSA_TWO_FILES_REQUIRED")
    for p in msa:
        if p.stat().st_size==0:raise Hold("MSA_FILE_EMPTY")
    if not checkpoint.is_file() or checkpoint.stat().st_size<100000000:
        raise Hold("LOCAL_OFFICIAL_CHECKPOINT_NOT_PRESENT")
    return {
      "schema_id":"janus.rowan.fireprot_1ey0.independent_rcsb_wt_only_local_boltz2_observation.v1",
      "technical_status":"PASS_REAL_EXTERNAL_1EY0_WT_GPU_LOCAL_BOLTZ2_WITH_MSA",
      "scientific_status":"NO_MUTANT_EFFECT_NO_STABILITY_PREDICTION_NO_TRUE_BLIND_LABELS",
      "registered_before_run":"data/rowan/protocols/ROWAN-1EY0-RCSB-136AA-SEQUENCE-ONLY-WT-SMOKE-PREREG-2026-10-26-v1.json",
      "identity":{
         "official_rcsb_source_url":"https://files.rcsb.org/download/1EY0.pdb",
         "pdb_deposited_sequence_length":149,
         "modeled_residue_span":"6-141",
         "source_wt_136aa_sha256":FROZEN_SEQ_SHA,
         "exact_amino_acid_identity":"136_OF_136",
         "frozen_fireprot_pdb_member_bytes_matched":False,
         "original_archived_pdb_member_sha256":"1fc8450e820f02840fee1720904df38498ddef12995ea6c4e40cb2c37fe7354d",
         "original_archive_sha_check":"HOLD_BLOCKED_DO_NOT_CLAIM"
      },
      "environment":{
         "boltz_version":"2.2.1",
         "torch":"2.12.1+cu126",
         "python":"3.12.15",
         "gpu":"NVIDIA GeForce RTX 2070 SUPER 8 GB",
         "public_msa_server":"https://api.colabfold.com",
         "settings":{"seed":20261026,"no_kernels":True,"recycling_steps":3,
                     "sampling_steps":200,"diffusion_samples":1,"max_parallel_samples":1,
                     "preprocessing_threads":2,"num_workers":0}
      },
      "sources":{
         "input_yaml_sha256":sha(input_yaml.read_bytes()),
         "confidence_json_sha256":sha(blob),
         "plddt_array_npz_sha256":sha(ps[0].read_bytes()),
         "model_conf_checkpoint_sha256":sha(checkpoint.read_bytes()),
         "msa":[{"filename":p.name,"sha256":sha(p.read_bytes()),"size_bytes":p.stat().st_size}
                for p in msa]
      },
      "real_local_confidence":{"ptm":float(v["ptm"]),
                               "complex_plddt":float(v["complex_plddt"]),
                               "per_residue_plddt_mean":mean,
                               "per_residue_plddt_count":136},
      "resource_and_science_gates":{
          "single_external_wt_jobs":1,
          "external_mutant_jobs":0,"FireProt_210_jobs":0,
          "paid_Rowans_jobs":0,
          "FireProt_experimental_labels_accessed":False,
          "independent_unpublished_label_custodian_exists":False,
          "transferred_shadow_model_validated":False,
          "new_shadow_coefficients_fit":False,
          "production_model_promotion":False,
          "safe_next_step":"Await separately verified original FireProt archive PDB chain/position provenance and genuinely independent label custody; no 210 mutant scale-up."
      }
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--yaml",type=Path,required=True)
    p.add_argument("--outputs",type=Path,required=True)
    p.add_argument("--checkpoint",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    try:
        if a.out.exists():raise Hold("IMMUTABLE_OBSERVATION_ALREADY_EXISTS")
        ret=audit(a.yaml,a.outputs,a.checkpoint)
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(json.dumps(ret,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        print("ROWAN_1EY0_WT_ONLY="+ret["technical_status"])
        return 0
    except (Hold,OSError,ValueError) as e:
        print("ROWAN_1EY0_WT_ONLY=HOLD_"+str(e))
        return 2
if __name__=="__main__":raise SystemExit(main())
