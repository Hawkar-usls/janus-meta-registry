#!/usr/bin/env python3
"""Fail-closed Rowan FireProt evaluation readiness and prediction freeze gate.

No FireProt numeric labels are loaded or imported. No paid API calls or Boltz2
inference is performed. The *existing* pre-committed 10x20 manifest and zero
baseline are read only. Provider-equivalent real Boltz2 pTM/avg_lddt and an
independent prospective label custodian are REQUIRED; never generate fake values.
"""
from __future__ import annotations
import argparse,hashlib,json,math,re
from pathlib import Path

MANIFEST_SHA256="9a44fd6c01afca2b21990b0f4364cb3dbf89ad61686295f55005f86001ce7b92"
ZERO_SHA256="0b827cd8ee6bd018a72762924dc55a6b68e8ba560ce0db70bb18d3be54ab9d6a"
MODEL_SHA256="52e0d6e75d603f0596ac7938715e45fccaf38835fac0ed110176128e33d86cf3"
FROZEN_COEF=(-1.327737761434,0.196413135791,-0.045214428615)
SOURCE_ARCHIVE_SHA256="b1403d86b43307f3a7dfc95ff6b72386c64068e8be1191bc7685d37bc8d654b2"
DIGEST=re.compile(r"^[0-9a-f]{64}$")
METRIC_KEYS=("ptm","avg_lddt")
CONTROLS=("wildtype","mutant")

class GateHold(ValueError):pass
def sha(b):return hashlib.sha256(b).hexdigest()
def valid_sha(x):return isinstance(x,str) and bool(DIGEST.fullmatch(x))
def finite_unit(x):
    if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not 0<=x<=1:
        raise GateHold("INVALID_PROVIDED_CONFIDENCE_SCORE")
    return float(x)

def dataset(manifest_bytes,zero_bytes):
    if sha(manifest_bytes)!=MANIFEST_SHA256 or sha(zero_bytes)!=ZERO_SHA256:
        raise GateHold("FROZEN_PUBLIC_INPUT_OR_ZERO_REFERENCE_SHA_DRIFT")
    m=json.loads(manifest_bytes);z=json.loads(zero_bytes)
    if m.get("schema_id")!="janus.rowan.external_fireprot_label_quarantined_input.v1":
        raise GateHold("INVALID_INPUT_SCHEMA")
    if m.get("source",{}).get("zip_sha256")!=SOURCE_ARCHIVE_SHA256:
        raise GateHold("FIREPROT_SOURCE_ARCHIVE_DRIFT")
    if m.get("inference",{}).get("frozen_shadow_model_sha256")!=MODEL_SHA256:
        raise GateHold("FROZEN_MODEL_IDENTITY_DRIFT")
    if z.get("manifest_sha256")!=MANIFEST_SHA256:
        raise GateHold("ZERO_REFERENCE_NOT_BOUND_TO_INPUT")
    if z.get("schema_id")!="janus.rowan.external_fireprot_zero_reference_commit.v1" or z.get("shadow_features_computed") is not False:
        raise GateHold("INVALID_ZERO_REFERENCE")
    domains=m.get("domains",[])
    if len(domains)!=10 or sum(len(d.get("variants",[])) for d in domains)!=200:
        raise GateHold("FROZEN_10X20_SIZE_DRIFT")
    pairs={(d["pdb_id"],v["mutation"]):{
             "wt_sha":d["wildtype_sha256"],
             "mutant_sha":v["mutant_sequence_sha256"],
             "pdb_member_sha":d["pdb_member_sha256"]} for d in domains for v in d["variants"]}
    if len(pairs)!=200:raise GateHold("DUPLICATE_FROZEN_MUTATIONS")
    if set((x["pdb_id"],x["mutation"]) for x in z["entries"])!=set(pairs):
        raise GateHold("ZERO_REFERENCE_ENTRIES_DRIFT")
    if any(x.get("predicted_delta_delta_G_kcal_per_mol")!=0.0 for x in z["entries"]):
        raise GateHold("ZERO_REFERENCE_VALUE_DRIFT")
    return m,pairs

def attest_labels(custody):
    """Signing statements alone never make *already public* labels prospective."""
    if not custody or custody.get("schema_id")!="janus.rowan.external.prospective_custodian.v1":
        raise GateHold("INDEPENDENT_LABEL_CUSTODIAN_NOT_DOCUMENTED")
    for k in ("custodian_organization","named_responsible_person","independent_contact",
              "dataset_label_commitment_sha256","attestation_sha256","signed_at_utc",
              "independent_collection_protocol_doi_or_url"):
        if not custody.get(k):raise GateHold("CUSTODIAN_FIELD_MISSING_"+k)
    for k in ("dataset_label_commitment_sha256","attestation_sha256"):
        if not valid_sha(custody[k]):raise GateHold("CUSTODY_DIGEST_INVALID_"+k)
    if custody.get("unpublished_new_measurements") is not True:
        raise GateHold("PREEXISTING_FIREPROT_PUBLIC_LABELS_NOT_PROSPECTIVE_BLIND")
    if custody.get("custodian_can_withhold_labels_from_JANUS_until_predictions_freeze") is not True:
        raise GateHold("NO_INDEPENDENT_BLIND_ACCESS_CONTROL")
    if custody.get("personal_identity_independent_from_JANUS_operator") is not True:
        raise GateHold("CUSTODIAN_NOT_INDEPENDENT")
    if custody.get("labels_seen_by_JANUS") is not False:
        raise GateHold("LABEL_PREVIOUSLY_SEEN")
    return True

def validate_pairs(pair_receipts,pairs):
    """Check supplied evidence only. No source records are invented here."""
    if len(pair_receipts)!=200:raise GateHold("COMPARABLE_SOURCE_PAIR_COUNT_NOT_200")
    observed=set();wt={}
    for record in pair_receipts:
        if record.get("schema_id")!="janus.rowan.external_fireprot.boltz2_pair.v1":
            raise GateHold("SOURCE_PAIR_SCHEMA_INVALID")
        key=(record.get("pdb_id"),record.get("mutation"))
        if key not in pairs or key in observed:raise GateHold("UNFROZEN_OR_DUPLICATE_PAIR")
        observed.add(key)
        spec=pairs[key]
        if record.get("wt_sequence_sha256")!=spec["wt_sha"] or record.get("mutant_sequence_sha256")!=spec["mutant_sha"]:
            raise GateHold("PAIR_SEQUENCE_NOT_FROZEN")
        if record.get("pdb_member_sha256")!=spec["pdb_member_sha"]:
            raise GateHold("PDB_STRUCTURE_PROVENANCE_MISMATCH")
        for k in ("provider","model_identifier","model_revision","inference_config_sha256","metric_equivalence_witness_sha256"):
            if not record.get(k):raise GateHold("PAIR_PROVENANCE_FIELD_MISSING_"+k)
        for k in ("inference_config_sha256","metric_equivalence_witness_sha256"):
            if not valid_sha(record[k]):raise GateHold("PAIR_PROVENANCE_DIGEST_BAD")
        if record.get("metric_equivalence_witness_attested") is not True:
            raise GateHold("ROWAN_S2_METRIC_EQUIVALENCE_NOT_PROVEN")
        if record.get("metric_mapping")!="MATCHED_PTMS_AND_NORMALIZED_AVG_LDDT":
            raise GateHold("ROWAN_METRIC_MAPPING_NOT_EQUIVALENT")
        for ctrl in CONTROLS:
            source=record.get(ctrl)
            if not isinstance(source,dict):raise GateHold("PAIR_MISSING_"+ctrl)
            for metric in METRIC_KEYS:finite_unit(source.get(metric))
            if not valid_sha(source.get("source_artifact_sha256")) or not source.get("immutable_source_uri"):
                raise GateHold("PAIRED_OUTPUT_NOT_SOURCE_BOUND_"+ctrl)
        w=record["wildtype"]
        domain=key[0]
        reference=(record["provider"],record["model_identifier"],record["model_revision"],
                   record["inference_config_sha256"],record["metric_equivalence_witness_sha256"],
                   w["ptm"],w["avg_lddt"],w["source_artifact_sha256"])
        if domain in wt and wt[domain]!=reference:raise GateHold("WT_FEATURE_OR_PROVIDER_CONFIG_INCONSISTENT")
        wt[domain]=reference
    if len(wt)!=10:raise GateHold("NOT_TEN_DISTINCT_WT_RESULTS")
    model_configs={(r["provider"],r["model_identifier"],r["model_revision"],
                    r["inference_config_sha256"],r["metric_equivalence_witness_sha256"]) for r in pair_receipts}
    if len(model_configs)!=1:raise GateHold("MODEL_PROVIDER_VERSION_OR_CONFIG_INCONSISTENT")
    return { (r["pdb_id"],r["mutation"]):r for r in pair_receipts }

def predictions(pair_map):
    """Only calculate on already verified source-backed confidence scores."""
    output=[]
    for (pdb,mutation),r in sorted(pair_map.items()):
        dp=finite_unit(r["mutant"]["ptm"])-finite_unit(r["wildtype"]["ptm"])
        dl=finite_unit(r["mutant"]["avg_lddt"])-finite_unit(r["wildtype"]["avg_lddt"])
        y=FROZEN_COEF[0]+FROZEN_COEF[1]*10*dp+FROZEN_COEF[2]*10*dl
        output.append({"pdb_id":pdb,"mutation":mutation,
                       "predicted_delta_delta_G_kcal_per_mol":y,
                       "no_label_access":True,
                       "source_mutant_sha256":r["mutant"]["source_artifact_sha256"],
                       "source_wt_sha256":r["wildtype"]["source_artifact_sha256"]})
    return output

def preflight(manifest_bytes,baseline_bytes,pair_data=None,custody=None):
    m,pairs=dataset(manifest_bytes,baseline_bytes)
    state={
        "schema_id":"janus.rowan.fireprot_blind_feature_readiness.v1",
        "state":"HOLD_NO_PROSPECTIVE_BLIND_OR_210_MATCHED_SOURCE_FEATURES",
        "frozen_candidate_count":200,"frozen_domains":10,
        "required_wildtype_results":10,
        "required_mutant_results":200,
        "model_sha256":MODEL_SHA256,
        "model_coefficients":{"intercept":FROZEN_COEF[0],
                              "ptm_delta_times_10":FROZEN_COEF[1],
                              "avg_lddt_delta_times_10":FROZEN_COEF[2]},
        "baseline_frozen":True,
        "public_fireprot_is_not_prospective_blind":True,
        "source_assay_aggregate_sign_reference":"FireProtDB negative ddG generally stabilizing; independently verify each original paper/measurement metadata before labeling",
        "proposed_target_transform":"JANUS_StabilizingPositive=-FireProtDB_ddG",
        "source_sign_for_each_primary_assay":"OPEN",
        "model_metric_equivalence_to_original_rowan":"OPEN",
        "new_boltz2_predictions_generated":0,
        "new_paid_rowan_calls":0,
        "production_promotion":False,
        "nonblind_public_label_use_for_validation":False,
        "independent_prospective_label_custodian":"NOT_ATTESTED",
        "shadow_predictions_frozen":False,
        "next_gate":"Preflight actual inference on no-cost hardware and establish equivalence via separate BBC1 bridge without using FireProt labels. Secure independent new label custodian before calling a test prospectively blind."
    }
    if pair_data is None or custody is None:
        return state,None
    attest_labels(custody)
    verified=validate_pairs(pair_data,pairs)
    state["state"]="PAIRED_PREDICTION_ARTIFACT_READY_FOR_IMMUTABLE_FREEZE_NOT_PERFORMANCE_VALIDATION"
    state["source_sign_for_each_primary_assay"]="MUST_BE_AUDITED_BEFORE_LABEL_RELEASE"
    state["independent_prospective_label_custodian"]="ATTESTATION_SUBMITTED_VERIFY_SIGNATURE_OUT_OF_BAND"
    state["shadow_predictions_frozen"]=False
    return state,predictions(verified)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",required=True,type=Path)
    ap.add_argument("--baseline",required=True,type=Path)
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--pair-evidence",type=Path)
    ap.add_argument("--custody-attestation",type=Path)
    a=ap.parse_args()
    try:
        if a.out.exists():raise GateHold("IMMUTABLE_OUTPUT_EXISTS")
        state,p=preflight(a.manifest.read_bytes(),a.baseline.read_bytes(),
             json.loads(a.pair_evidence.read_text(encoding="utf8")) if a.pair_evidence else None,
             json.loads(a.custody_attestation.read_text(encoding="utf8")) if a.custody_attestation else None)
        state["source_evidence_manifest_sha256"]=MANIFEST_SHA256
        state["zero_reference_sha256"]=ZERO_SHA256
        state["provided_pair_predictions"]=p
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(json.dumps(state,indent=2,allow_nan=False)+"\n",encoding="utf8")
        print("ROWAN_FIREPROT_PROSPECTIVE_GATE="+state["state"])
        return 2 if p is None else 0
    except (GateHold,ValueError,OSError) as exc:
        print("ROWAN_FIREPROT_PROSPECTIVE_GATE=HOLD_"+str(exc))
        return 2
if __name__=="__main__":raise SystemExit(main())
