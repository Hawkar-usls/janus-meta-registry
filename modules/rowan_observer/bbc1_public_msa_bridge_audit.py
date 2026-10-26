#!/usr/bin/env python3
"""Independent exact-byte audit of *local* BBC1 WT/G53A Boltz2 MSA bridge.

NEVER claims external Rowan service/model equivalence. The old Rowan provider
used a private MSA server while this experiment used public ColabFold.
Only reads public-protein YAML, generated alignments, confidence JSON and
per-residue NPZ; it does not contact Rowan, FireProt, or any model provider.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np

CASES={
 "BBC1_WT_MSA":{
   "yaml_sha256":"9d74799b46375a1acf68e5de2830e1e505efc40798a7d126039864aeee40962d",
   "confidence_sha256":"bc0140e5ef4866de35c2dc04d9484b17f8366d737a4dd025fc9d93bbe8c7840e",
   "plddt_npz_sha256":"5637d59f58dd7ede355adb164c1fdd6a7a581599c8afefa54a60479641372f5e",
   "msa_sha256":{
      "bfd.mgnify30.metaeuk30.smag30.a3m":"db99e268f191388c275954c4df7753a5328998e98fe3a85c74426d209875c556",
      "uniref.a3m":"5754efb9eab8f5f92442c78b8dbfcc57023e9eb70d1e3307fe8a6038be64507a"
   },
   "rowan_ptm":.927,"rowan_avg_lddt":.963,
   "without_msa_ptm":.9174146056175232,"without_msa_plddt":.965494692325592
 },
 "BBC1_G53A_MSA":{
   "yaml_sha256":"97c95508c5b37a515d63756070b87c6f945eb904029d85d58e72b12bc6651e0a",
   "confidence_sha256":"559a66130268e67cb6ae153590a9712f6c860c86113d6619d9631efe9f5d1646",
   "plddt_npz_sha256":"2b831b46e6cb1f9ac1d888bf4269816364e808bfb880f1bcd70d224c3d38f25a",
   "msa_sha256":{
      "bfd.mgnify30.metaeuk30.smag30.a3m":"f49a6d6438d17d37abd859b44fe0a8867a5bb16ff2d3700301738efe185cf50d",
      "uniref.a3m":"bb3273fcc9fd6d9e62e1504bb33e3eeb456290dabd7562d8d22a48999309022b"
   },
   "rowan_ptm":.918,"rowan_avg_lddt":.968,
   "without_msa_ptm":.8305742740631104,"without_msa_plddt":.8682771921157837
 }
}
ROWAN_SOURCE_RECEIPT="data/rowan/receipts/ROWAN-S2-40236409772-51508154de2623c0.json"
OUTPUT_SOURCE="https://github.com/jwohlwend/boltz"
SOURCE_BUILD="boltz==2.2.1;torch==2.12.1+cu126;python==3.12.15"
EXPECTED_YAML_LABELS=("BBC1_WT_MSA","BBC1_G53A_MSA")
class AuditHold(ValueError):pass

def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def check_file_sha(p,expected,kind):
    p=Path(p)
    if not p.is_file() or sha_bytes(p.read_bytes())!=expected:
        raise AuditHold(kind+"_SHA_OR_FILE_HOLD")
    return p
def one_case(inputs,outputs,case):
    spec=CASES[case]
    inp=check_file_sha(Path(inputs)/(case+".yaml"),spec["yaml_sha256"],"YAML_"+case)
    y=inp.read_text(encoding="utf8")
    if "msa: empty" in y or "sequence:" not in y:
        raise AuditHold("MSA_MODE_INVALID_"+case)
    candidates=list(Path(outputs).rglob("confidence_"+case+"_model_0.json"))
    if len(candidates)!=1:raise AuditHold("CONFIDENCE_NOT_EXACTLY_ONE_"+case)
    conf=candidates[0]
    check_file_sha(conf,spec["confidence_sha256"],"CONFIDENCE_"+case)
    score=json.loads(conf.read_bytes())
    for k in ("ptm","complex_plddt"):
        v=score.get(k)
        if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1:
            raise AuditHold("BAD_SCORE_"+k+"_"+case)
    dirname=conf.parent
    plddt=check_file_sha(dirname/("plddt_"+case+"_model_0.npz"),spec["plddt_npz_sha256"],"PLDDT_"+case)
    with np.load(plddt,allow_pickle=False) as z:
        if z.files!=["plddt"]:raise AuditHold("PLDDT_NPZ_SCHEMA_DRIFT")
        vals=z["plddt"]
        if vals.shape!=(64,) or not np.isfinite(vals).all():
            raise AuditHold("PLDDT_LENGTH_OR_RANGE_INVALID")
        mean=float(vals.mean())
    if abs(mean-float(score["complex_plddt"]))>1e-7:
        raise AuditHold("PLDDT_MEAN_NOT_COMPLEX_PLDDT")
    msa={}
    scope=conf.parents[2]  # matching Boltz experiment root, not both sibling runs
    for basename,hash_ in spec["msa_sha256"].items():
        matches=list(scope.rglob(basename))
        if len(matches)!=1:raise AuditHold("MSA_PATH_NOT_UNIQUE_"+basename)
        p=check_file_sha(matches[0],hash_,"MSA_"+case+"_"+basename)
        msa[basename]={"sha256":hash_,"bytes":p.stat().st_size}
    return {
      "input_yaml_sha256":spec["yaml_sha256"],
      "confidence_json_sha256":spec["confidence_sha256"],
      "ptm":float(score["ptm"]),"complex_plddt":float(score["complex_plddt"]),
      "per_residue_plddt_mean":mean,"per_residue_count":64,
      "plddt_npz_sha256":spec["plddt_npz_sha256"],"msa_evidence":msa,
      "rowan_ptm":spec["rowan_ptm"],"rowan_avg_lddt":spec["rowan_avg_lddt"],
      "without_msa_ptm":spec["without_msa_ptm"],"without_msa_complex_plddt":spec["without_msa_plddt"],
      "ptm_delta_local_minus_rowan":float(score["ptm"])-spec["rowan_ptm"],
      "plddt_delta_local_minus_rowan_proxy":float(score["complex_plddt"])-spec["rowan_avg_lddt"]
    }
def audit(inputs,outputs):
    out={k:one_case(inputs,outputs,k) for k in EXPECTED_YAML_LABELS}
    def delta(metric):
        a=out["BBC1_WT_MSA"][metric]
        b=out["BBC1_G53A_MSA"][metric]
        return b-a
    return {
       "schema_id":"janus.rowan.bbc1.public_msa_real_two_case_bridge.v1",
       "state":"PASS_LOCAL_BBC1_TWO_MSA_SOURCE_VERIFIED_METRIC_PROVIDER_EQUIVALENCE_HOLD",
       "source_rowan_receipt":ROWAN_SOURCE_RECEIPT,
       "source_model":SOURCE_BUILD,
       "model_provenance_status":"INTERNAL_BOLTZ2_CHECKPOINT_CRC_PASS_FULL_SERVER_ETAG_TO_LOCAL_SHA_RELATIONSHIP_OPEN",
       "observed_MSA_provider":"https://api.colabfold.com",
       "rowan_MSA_provider":"PRIVATE_ROWAN_HOSTED_NOT_ACCESSIBLE",
       "experiment_params":{"model":"boltz2","recycling_steps":3,"sampling_steps":200,"diffusion_samples":1,"seed":20261026,"no_kernels":True,"mode":"public MSA server"},
       "cases":out,
       "pair_deltas":{
          "rowan_delta_ptm":.918-.927,
          "local_msa_delta_ptm":delta("ptm"),
          "local_no_msa_delta_ptm":.8305742740631104-.9174146056175232,
          "rowan_delta_avg_lddt":.968-.963,
          "local_msa_delta_complex_plddt":delta("complex_plddt"),
          "local_no_msa_delta_complex_plddt":.8682771921157837-.965494692325592
       },
       "scientific_guard":{
          "source_MSAs_bytewise_matched_to_private_rowan":False,
          "rowan_actual_seed_sampling_model_revision_attested":False,
          "rowan_avg_lddt_semantic_definition":"per-residue pLDDT average as documented in Rowan SDK",
          "single_chain_local_mean_equals_complex_plddt":True,
          "confidence_as_stability_fitness_proven":False,
          "FireProt_210_compute_gate":"HOLD_DO_NOT_RUN",
          "new_rowan_paid_workflows_submitted":0,
          "shadow_weights_modified":False,
          "production_promotion":False,
          "true_independent_blind_validation":False
       }
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--inputs",type=Path,required=True)
    ap.add_argument("--outputs",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    try:
        if args.out.exists():raise AuditHold("IMMUTABLE_OUTPUT_ALREADY_EXISTS")
        obj=audit(args.inputs,args.outputs)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_bytes((json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+"\n").encode())
        print("ROWAN_BBC1_PUBLIC_MSA_LOCAL_BRIDGE="+obj["state"])
        return 0
    except (AuditHold,OSError,ValueError) as ex:
        print("ROWAN_BBC1_PUBLIC_MSA_LOCAL_BRIDGE=HOLD_"+str(ex))
        return 2
if __name__=="__main__":raise SystemExit(main())
