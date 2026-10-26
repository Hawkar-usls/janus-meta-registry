#!/usr/bin/env python3
"""Audit one preregistered 1EY0 T8A local Boltz2 result against frozen WT.

T8A first variant in frozen FireProt source manifest, no assay values read.
Verify exact bytes of real YAML, ColabFold alignments, Boltz confidences and
per-residue 136-aa NPZ. Do not confuse model confidence with ddG.
"""
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np

ORIGINAL="KLHKEPATLIKAIDGDTVKLMYKGQPMTFRLLLVDTPETKHPKKGVEKYGPEASAFTKKMVENAKKIEVEFDKGQRTDKYGRGLAYIYADGKMVNEALVRQGLAKVAYVYKPNNTHEQHLRKSEAQAKKEKLNIWS"
WT_SHA="94a6f4324114f9e643076e2bfcb727145d400345f4c5feff0607e5c1fb787be1"
T8A_SHA="1c9ea97ff41ea9f659d1712e422c2ea1f4aa3373463b1e17d3d682c156cddacb"
INPUT_YAML_SHA="84441663c1476b586e7781c3afa68714cf5e725158d325ac1dc71c2c26ca551d"
WT_CONF_SHA="725fd6bb09c2b3ea1534fffffda4cab8edd8242cd4d3053b883bfc9870cf76e2"
MUT_CONF_SHA="fb99e931111e43b34f2224fe25c8cd22dc6648a73ebedb9b273e6fed05a4d8d8"
WT_NPZ_SHA="c7f6b90cd4ac88b57c1f69bc3bb7c86224019da51a548f39fd6556508fdb5ef8"
MUT_NPZ_SHA="b51ea471a0b4814fe709d3b63dcc5df363adf832d61e570cf95c621f25fde768"
MSA_SHA={
 "1EY0_RCSB_136AA_WT":{
  "uniref.a3m":"040a6ca24c361ffea9afc59e7262915018dc65fac3d233ee9db9a31f170feb8d",
  "bfd.mgnify30.metaeuk30.smag30.a3m":"811414611942589619806ad4e70105dce333015c64cf537e95c1da07af987018"
 },
 "1EY0_RCSB_136AA_T8A":{
  "uniref.a3m":"b1bbb88b1c496f03459c67deb36121d8890a5e3a955b052a268be2f1817e4586",
  "bfd.mgnify30.metaeuk30.smag30.a3m":"4e10a90fccfba877df40d60a0d832764202c261c843cdf2ce5d0d4c5f248802a"
 }
}
class Hold(ValueError):pass
def sha(b):return hashlib.sha256(b).hexdigest()
def fsha(p):return sha(p.read_bytes())
def exact(path,expected,context):
 if not path.is_file() or fsha(path)!=expected:
  raise Hold(context+"_MISSING_OR_SHA_DRIFT")
def sequence_check():
 if len(ORIGINAL)!=136 or sha(ORIGINAL.encode())!=WT_SHA or ORIGINAL[7]!="T":
  raise Hold("ORIGINAL_136AA_SOURCE_DRIFT")
 changed=ORIGINAL[:7]+"A"+ORIGINAL[8:]
 if len(changed)!=136 or sha(changed.encode())!=T8A_SHA:
  raise Hold("MUTANT_SOURCE_DRIFT")
 return changed
def source_case(inputs,outputs,name,conf_sha,npz_sha):
 root=outputs/("boltz_results_"+name)
 confidence=list(root.rglob("confidence_"+name+"_model_0.json"))
 npz=list(root.rglob("plddt_"+name+"_model_0.npz"))
 if len(confidence)!=1 or len(npz)!=1:raise Hold("REQUIRED_REAL_OUTPUT_FILES_NOT_UNIQUE_"+name)
 exact(confidence[0],conf_sha,"CONFIDENCE_"+name)
 exact(npz[0],npz_sha,"PLDDT_NPZ_"+name)
 j=json.loads(confidence[0].read_bytes())
 for field in ("ptm","complex_plddt"):
  v=j.get(field)
  if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1:
   raise Hold("CONFIDENCE_OUT_OF_RANGE_"+name+"_"+field)
 with np.load(npz[0],allow_pickle=False) as z:
  if z.files!=["plddt"] or z["plddt"].shape!=(136,):
   raise Hold("PLDDT_NPZ_SCHEMA_DRIFT_"+name)
  a=z["plddt"]
  if not np.isfinite(a).all():raise Hold("NONFINITE_PLDDT")
  avg=float(a.mean())
 if abs(avg-j["complex_plddt"])>1e-7:
  raise Hold("PER_RESIDUE_MEAN_NOT_COMPLEX_"+name)
 msa_files={}
 for basename,expected in MSA_SHA[name].items():
  candidates=list(root.rglob(basename))
  if len(candidates)!=1:raise Hold("MSA_NOT_UNIQUE_"+name)
  p=candidates[0];exact(p,expected,"MSA_"+name+"_"+basename)
  msa_files[basename]={"sha256":expected,"size_bytes":p.stat().st_size}
 return {"ptm":float(j["ptm"]),"mean_plddt":float(j["complex_plddt"]),
         "mean_plddt_recomputed":avg,"count":136,
         "confidence_sha256":conf_sha,"residue_array_sha256":npz_sha,
         "msa":msa_files}
def audit(inputs,outputs):
 mutant=sequence_check()
 y=inputs/"1EY0_RCSB_136AA_T8A.yaml"
 exact(y,INPUT_YAML_SHA,"EXACT_MUTANT_INPUT_YAML")
 desired=f"sequences:\n  - protein:\n      id: A\n      sequence: {mutant}\n".encode()
 if y.read_bytes()!=desired:raise Hold("YAML_NOT_EXACT_136AA_MUTANT")
 wt=source_case(inputs,outputs,"1EY0_RCSB_136AA_WT",WT_CONF_SHA,WT_NPZ_SHA)
 mt=source_case(inputs,outputs,"1EY0_RCSB_136AA_T8A",MUT_CONF_SHA,MUT_NPZ_SHA)
 return {
  "schema_id":"janus.rowan.1ey0.T8A.local_real_MSA_mutant_delta.v1",
  "technical_status":"PASS_TWO_REAL_LOCAL_BOLTZ2_1EY0_WT_T8A_MSA_RUNS",
  "scientific_status":"STRUCTURAL_CONFIDENCE_DIAGNOSTIC_ONLY_NO_STABILITY_CLAIM",
  "source_prereg":"data/rowan/protocols/ROWAN-1EY0-T8A-SINGLE-MUTANT-STRUCTURAL-DELTA-PREREG-2026-10-26-v1.json",
  "source_frozen_manifest":"data/rowan/protocols/ROWAN-FIREPROT-HF-10X20-LABEL-FREE-INPUT-2026-10-26-v1.json",
  "wt_sequence_sha256":WT_SHA,"mutant_T8A_sequence_sha256":T8A_SHA,
  "mutant_input_yaml_sha256":INPUT_YAML_SHA,"mutant_position":"T8A; modeled PDB A:13",
  "model":"Boltz2 2.2.1","public_MSA":"api.colabfold.com",
  "config":{"recycling_steps":3,"sampling_steps":200,"diffusion_samples":1,"seed":20261026,"no_kernels":True},
  "wt":wt,"T8A":mt,
  "mutant_minus_wt":{
   "delta_ptm":mt["ptm"]-wt["ptm"],
   "delta_mean_plddt":mt["mean_plddt"]-wt["mean_plddt"]
  },
  "scientific_gates":{
   "source_fireprot_original_zip_member_sha_verified":False,
   "experimental_DDG_values_read":False,
   "new_unpublished_independent_custodian":False,
   "true_blind":False,
   "FireProt_210_mutants_not_authorized":True,
   "shadow_model_weights_modified":False,
   "production_promotion":False
  }
 }
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--inputs",type=Path,required=True)
 p.add_argument("--outputs",type=Path,required=True)
 p.add_argument("--out",type=Path,required=True)
 a=p.parse_args()
 try:
  if a.out.exists():raise Hold("IMMUTABLE_RECEIPT_EXISTS")
  result=audit(a.inputs,a.outputs)
  a.out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
  print("ROWAN_LOCAL_T8A_SOURCE_AUDIT="+result["technical_status"])
  return 0
 except (Hold,OSError,ValueError) as ex:
  print("ROWAN_LOCAL_T8A_SOURCE_AUDIT=HOLD_"+str(ex));return 2
if __name__=="__main__":raise SystemExit(main())
