#!/usr/bin/env python3
"""Independent read-only revalidation of JANUS v5.0 TOPA packet for EYE JSON memory.

Does NOT trust model-generated answers or infer empirical truth from TOPA SHA.
Only source-byte identity and a narrow negative-result learning record are
allowed into Meta Registry. No executables, commands, tokens or model weights.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

SOURCE = "research/essence/peer_v49/FIRST_PROSPECTIVE_READOUT.json"
TOPA_SHA = "0890172493d6ed0d3a62e79904c6a7593eb8a9f3"
PACKET_SCHEMA = "janus.agency.source_provenance_packet/5.0"
LATEST_SCHEMA = "janus.agency.latest_verified_packet/5.0"
LEARNING_SCHEMA = "janus.agency.meta_json_learning_input/5.0"
OUTPUT_SCHEMA = "janus.registry.independently_rechecked_ai_json/5.0"
HEX64 = re.compile(r"^[a-f0-9]{64}$")
HEX40 = re.compile(r"^[a-f0-9]{40}$")


def canonical(data):
    return json.dumps(data,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()


def sha(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def check_packet(packet):
    if not isinstance(packet,dict) or packet.get("receipt_sha256")!=sha({
            k:v for k,v in packet.items() if k!="receipt_sha256"}):
        raise ValueError("UNTRUSTED_SOURCE_PACKET_HASH")
    if (packet.get("schema")!=PACKET_SCHEMA or
        packet.get("status")!="SOURCE_INTEGRITY_VERIFIED_DISPATCH_REQUEST_ONLY" or
        packet.get("source_path")!=SOURCE or
        not HEX40.fullmatch(packet.get("source_commit","")) or
        not HEX64.fullmatch(packet.get("source_raw_sha256","")) or
        packet.get("topa_code_commit")!=TOPA_SHA or
        packet.get("beetle_task_id")!="janus_json_registry_provenance_audit" or
        packet.get("source_beetle_intent")!="EXPLICIT_USER_DISCOVERY_STEERING" or
        packet.get("native_model",{}).get("native_proposed_this_user_task") is not False or
        packet.get("external_scientific_validation") is not False or
        packet.get("production_write_authority") is not False or
        packet.get("sentinel_dispatch") is not False):
        raise ValueError("AGENCY_PACKET_CLAIM_ESCALATION")
    return packet


def bounded_read(path, maxbytes=180_000):
    p=Path(path)
    if not p.is_file() or p.is_symlink() or p.stat().st_size>maxbytes:
        raise ValueError("INVALID_OR_OVERLONG_SOURCE_JSON")
    return json.loads(p.read_text(encoding="utf-8"),
                      parse_constant=lambda _:(_ for _ in ()).throw(
                          ValueError("NONFINITE_JSON_FORBIDDEN")))


def verify(index,packet,raw):
    packet=check_packet(packet)
    if (index.get("schema")!=LATEST_SCHEMA or
        index.get("packet_id")!=packet["receipt_sha256"] or
        index.get("source_sha256")!=packet["source_raw_sha256"] or
        index.get("source_commit")!=packet["source_commit"] or
        index.get("beetle_intent_sha256")!=packet["beetle_intent_sha256"] or
        index.get("science_truth_authority") is not False or
        index.get("topa_structural_only") is not True):
        raise ValueError("META_SOURCE_INDEX_DIFFERENT_FROM_PACKET")
    original_bytes=Path(raw).read_bytes()
    source_sha=hashlib.sha256(original_bytes).hexdigest()
    if source_sha!=packet["source_raw_sha256"]:
        raise ValueError("META_RECHECK_SOURCE_BYTES_CHANGED")
    obj=json.loads(original_bytes)
    if (obj.get("schema")!="janus.essence.continual_prospective_first_trial_evidence/4.9" or
        obj.get("status")!="HOLD_REPLAY_DID_NOT_CLEAR_PREDECLARED_GATES" or
        obj.get("deployment",{}).get("production_admission") is not False or
        obj.get("interpretation",{}).get("external_custodian") is not False):
        raise ValueError("META_CANNOT_PROMOTE_SCIENTIFIC_OR_MODEL_CLAIMS")
    sem=hashlib.sha256(canonical(obj)+b"\n").hexdigest()
    f=packet.get("source_fact_json",{})
    if (f.get("schema")!=LEARNING_SCHEMA or
        f.get("source_repository")!="Hawkar-usls/Janus-Demiurge" or
        f.get("source_commit")!=packet["source_commit"] or
        f.get("source_path")!=SOURCE or
        f.get("source_raw_sha256")!=source_sha or
        f.get("topa_code_commit")!=TOPA_SHA or
        f.get("topa_semantic_stream_sha256")!=sem or
        f.get("research_verdict")!=obj["status"] or
        f.get("research_experiment_run_id")!=43755360999 or
        f.get("status")!="TOPA_STRUCTURAL_SOURCE_VERIFIED_NOT_SCIENTIFIC_TRUTH" or
        f.get("proof_authority")!="SOURCE_INTEGRITY_ONLY"):
        raise ValueError("META_TRAINING_SOURCE_NOT_INDEPENDENTLY_RECHECKED")
    r=obj["results"]
    counts={
        "replay_fresh_old":r["fresh_unseen_legacy_oracle"]["replay_exact"],
        "naive_fresh_old":r["fresh_unseen_legacy_oracle"]["naive_exact"],
        "replay_new_lapis_exact":r["lapis_paraphrased_source"]["replay_exact"],
        "new_lapis_count":r["lapis_paraphrased_source"]["n"],
    }
    if (f.get("confirmed_counts")!=counts or counts!={
            "replay_fresh_old":16,"naive_fresh_old":8,
            "replay_new_lapis_exact":0,"new_lapis_count":6}):
        raise ValueError("META_SOURCE_METRIC_MISMATCH")
    boundary=f.get("epistemic_boundary",{})
    if (boundary.get("topa_bytes_are_world_truth") is not False or
        boundary.get("model_output_is_independent_validation") is not False or
        boundary.get("used_as_direct_neural_supervision") is not False or
        boundary.get("automatic_model_promotion") is not False or
        boundary.get("verified_negative_results_preserved") is not True):
        raise ValueError("META_LEARNING_AUTHORITY_TOO_HIGH")
    record={
        "schema":OUTPUT_SCHEMA,"status":"SOURCE_AND_TOPA_JSON_HASH_RECHECK_PASS",
        "source_repository":"Hawkar-usls/Janus-Demiurge",
        "source_commit":packet["source_commit"],"source_path":SOURCE,
        "source_sha256":source_sha,"topa_source_commit":TOPA_SHA,
        "topa_semantic_sha256":sem,"agent_packet_sha256":packet["receipt_sha256"],
        "beetle_discovery_task_id":packet["beetle_task_id"],
        "native_autonomy_accepted":False,
        "json_memory_intake":"EYE_DERIVATIVE_INDEX_ONLY",
        "verification":"RAW_SOURCE_SHA_AND_INDEPENDENT_JSON_METRIC_RECOMPUTATION",
        "factual_experiment_status":obj["status"],
        "replay_vs_naive_old_route":{"replay":counts["replay_fresh_old"],
                                     "naive":counts["naive_fresh_old"]},
        "new_source_exact":{"correct":counts["replay_new_lapis_exact"],
                            "total":counts["new_lapis_count"]},
        "external_independent_replication":False,
        "scientific_truth_admission":False,"model_weight_change":False,
        "production_promotion":False,"sentinel_A_B_C_dispatch":False,
        "raw_model_text_reused_as_truth":False
    }
    record["record_sha256"]=sha(record)
    return record


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--latest",required=True)
    p.add_argument("--packet",required=True)
    p.add_argument("--source",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args()
    result=verify(bounded_read(args.latest),bounded_read(args.packet),
                  args.source)
    target=Path(args.out)
    if target.is_symlink():
        raise ValueError("SYMLINK_OUTPUT_REFUSED")
    target.parent.mkdir(parents=True,exist_ok=True)
    content=json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n"
    if target.exists():
        if target.read_text(encoding="utf-8")!=content:
            raise ValueError("CREATE_ONLY_VERIFIED_JSON_NEVER_OVERWRITE")
        print("ALREADY_VERIFIED_JSON_UNCHANGED")
        return
    target.write_text(content,encoding="utf-8")
    print(json.dumps({"status":result["status"],
                      "record_sha256":result["record_sha256"],
                      "external_validation":False,
                      "native_weights_updated":False},sort_keys=True))


if __name__=="__main__":
    main()
