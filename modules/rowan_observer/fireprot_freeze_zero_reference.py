#!/usr/bin/env python3
"""Freeze a 200-variant zero-change comparator without fetching outcome labels.

This is **not** a shadow-model prediction. It is a precommitted null/reference
prediction that can be checked before a qualified label-custody event.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
EXPECTED_MODEL_SHA="52e0d6e75d603f0596ac7938715e45fccaf38835fac0ed110176128e33d86cf3"
EXPECTED_DATASET_SHA="b1403d86b43307f3a7dfc95ff6b72386c64068e8be1191bc7685d37bc8d654b2"
SCHEMA="janus.rowan.external_fireprot_label_quarantined_input.v1"
AA=set("ACDEFGHIKLMNPQRSTVWY")

class FreezeHold(ValueError):pass

def digest(raw):return hashlib.sha256(raw).hexdigest()
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf8")

def validate_manifest(manifest):
    if manifest.get("schema_id")!=SCHEMA:
        raise FreezeHold("WRONG_MANIFEST_SCHEMA")
    if manifest.get("honest_experiment_type")!="RETROSPECTIVE_PUBLIC_DATASET_NOT_TRUE_BLIND_NO_INDEPENDENT_CUSTODIAN":
        raise FreezeHold("MISSING_NONBLIND_DISCLOSURE")
    if manifest.get("source",{}).get("zip_sha256")!=EXPECTED_DATASET_SHA:
        raise FreezeHold("DATASET_DIGEST_DRIFT")
    if manifest.get("inference",{}).get("frozen_shadow_model_sha256")!=EXPECTED_MODEL_SHA:
        raise FreezeHold("FROZEN_SHADOW_DIGEST_DRIFT")
    if manifest.get("safety",{}).get("new_rowan_jobs")!=0:
        raise FreezeHold("NEW_ROWAN_JOB_UNAUTHORIZED")
    domains=manifest.get("domains")
    if not isinstance(domains,list) or len(domains)!=10:
        raise FreezeHold("DOMAIN_COUNT_NOT_10")
    ids=set();records=[];used_uniprot=set();used_interpro=set()
    for d in domains:
        pid=d.get("pdb_id")
        seq=d.get("wildtype_sequence")
        if not isinstance(pid,str) or not isinstance(seq,str) or any(c not in AA for c in seq):
            raise FreezeHold("INVALID_DOMAIN_SEQUENCE")
        if digest(seq.encode("ascii"))!=d.get("wildtype_sha256"):
            raise FreezeHold("WILDTYPE_SEQUENCE_SHA_DRIFT")
        if pid in ids:raise FreezeHold("DOMAIN_DUPLICATE")
        ids.add(pid)
        uid=d.get("uniprot_id")
        fam=set(d.get("interpro_families",[]))
        if not uid or uid in used_uniprot or not fam or used_interpro & fam:
            raise FreezeHold("FAMILY_OR_UNIPROT_NOT_DISJOINT")
        used_interpro|=fam;used_uniprot.add(uid)
        vs=d.get("variants")
        if not isinstance(vs,list) or len(vs)!=20:
            raise FreezeHold("VARIANT_COUNT_NOT_20")
        seen=set()
        for v in vs:
            pos=v.get("pdb_position_zero_based")
            wt=v.get("wild_type_residue")
            alt=v.get("mutant_residue")
            if type(pos) is not int or pos not in range(len(seq)) or seq[pos]!=wt or alt not in AA or alt==wt:
                raise FreezeHold("VARIANT_POSITION_OR_SEQUENCE_DRIFT")
            name=wt+str(pos+1)+alt
            if name!=v.get("mutation") or name in seen:
                raise FreezeHold("MUTATION_DUPLICATE_OR_ID_DRIFT")
            seen.add(name)
            mut=seq[:pos]+alt+seq[pos+1:]
            if digest(mut.encode("ascii"))!=v.get("mutant_sequence_sha256"):
                raise FreezeHold("MUTANT_SEQUENCE_SHA_DRIFT")
            records.append({
                "pdb_id":pid,
                "mutation":name,
                "pdb_position_zero_based":pos,
                "wildtype_sequence_sha256":d["wildtype_sha256"],
                "mutant_sequence_sha256":v["mutant_sequence_sha256"],
                "predicted_delta_delta_G_kcal_per_mol":0.0
            })
    if len(records)!=200 or len({(r["pdb_id"],r["mutation"]) for r in records})!=200:
        raise FreezeHold("DUPLICATE_OR_MISSING_REFERENCE_PREDICTION")
    return records

def freeze(manifest,manifest_sha):
    entries=validate_manifest(manifest)
    output={
        "schema_id":"janus.rowan.external_fireprot_zero_reference_commit.v1",
        "status":"FROZEN_ZERO_BASELINE_200_NOT_SHADOW_PREDICTIONS",
        "manifest_sha256":manifest_sha,
        "model_under_test":"FROZEN_ROWAN_S2_SHADOW_NOT_EVALUATED",
        "reference_baseline":"predict_zero_kcal_per_mol_for_all_mutations",
        "n_domains":10,
        "n_mutations":200,
        "zero_forecast_unit":"kcal/mol",
        "zero_reference_is_invariant_to_target_sign":True,
        "loss_comparison":"Equal-domain macro MAE vs shadow if and only if 200 signed shadow predictions and independent label custody are verified.",
        "label_access_statement":"This program opens only the label-free input JSON. Public source data remain publicly accessible, so this is NOT an externally blinded prospective study.",
        "public_source_is_retrospective":True,
        "shadow_features_computed":False,
        "new_rowan_jobs":0,
        "new_rowan_credits":0,
        "production_promotion_authorized":False,
        "entries":entries
    }
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args()
    try:
        if args.out.exists():raise FreezeHold("OUTPUT_ALREADY_EXISTS")
        raw=args.manifest.read_bytes()
        obj=json.loads(raw.decode("utf8"))
        report=freeze(obj,digest(raw))
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf8")
        print("JANUS_FIREPROT_ZERO_REFERENCE=FROZEN_200_NOT_SHADOW")
        return 0
    except (ValueError,OSError) as exc:
        print("JANUS_FIREPROT_ZERO_REFERENCE=HOLD_"+str(exc))
        return 2
if __name__=="__main__":raise SystemExit(main())
