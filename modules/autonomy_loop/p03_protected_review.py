#!/usr/bin/env python3
"""P0.3 cross-organ protected-review *candidate*, not protected acceptance.

This code intentionally DOES NOT mint checkpoint acceptance. It binds original
same-owner cross-repository receipts into an inspectable matrix, rejects fake
self-approval and requires a distinct externally authenticated reviewer.
The source code is still in a draft branch, not a required/protected main check.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
from modules.autonomy_loop import p03_recovery_matrix as recovery

SCHEMA="janus.autonomy.p03_protected_review_report.v1"
EVIDENCE=Path("data/autonomy_map/P03_CROSS_ORGAN_EVIDENCE_20261123.json")
HEX40=re.compile(r"[0-9a-f]{40}\Z")
HEX64=re.compile(r"[0-9a-f]{64}\Z")


class AdmissionHold(ValueError):
    pass


def validate(manifest, latest, checkpoint):
    if not isinstance(manifest,dict) or manifest.get("schema")!="janus.autonomy.p03_crossorgan_evidence.v1":
        raise AdmissionHold("UNVERIFIED_CROSSORGAN_MANIFEST")
    a=manifest.get("private_receiver_ack")
    g=manifest.get("genesis_context_consumer")
    p=manifest.get("protected_review")
    f=manifest.get("failure_recovery")
    b=manifest.get("boundaries")
    if any(type(x) is not dict for x in (a,g,p,f,b)):
        raise AdmissionHold("INCOMPLETE_CROSSORGAN_EVIDENCE")
    if (a.get("source_repository")!="Hawkar-usls/SkinGPT" or
        a.get("sender_repository")!="Hawkar-usls/janus-lapis" or
        a.get("evidence_scope")!="AUTHORIZED_SAME_OWNER_PRIVATE_INBOX_READ" or
        a.get("produced")!=2 or a.get("confirmed")!=2 or a.get("pending")!=0 or
        a.get("last_batch_identity_sha_match") is not True or
        a.get("third_party_custodian_verified") is not False or
        a.get("runtime_consumption_proven") is not False or
        a.get("no_private_identifiers_or_ack_content_in_manifest") is not True or
        a.get("sender_active_worker_has_credential_proven") is not False):
        raise AdmissionHold("PRIVATE_RECEIVER_ACK_SCOPE_OR_TRUTH_DRIFT")
    if (g.get("repository")!="Hawkar-usls/Janus_Genesis" or
        g.get("run_id")!=45227943588 or
        g.get("original_successful_ci")!="https://github.com/Hawkar-usls/Janus_Genesis/actions/runs/45227943588" or
        g.get("source_commit")!="df796fe68b57771294a02ea941aa8ea64824956c" or
        g.get("source_state_commit")!="b7d7a469f0a57a782e9253597b62fa92fd5cb5a1" or
        g.get("input_context_sha256")!="f5c35a30874627239f177cc1b8b5d17873960e68cd3fc35e3ba82508cbef5090" or
        g.get("artifact_zip_sha256")!="0b15c7de7e638f68a0bc275371229e775eb4d7a31e48556376bb922f30ab241f" or
        g.get("event_id_sha256")!="ce95cc5370cfdebfa606246d92bbed2fc5352c81c122403efd6bfce9d1fe67ea" or
        g.get("query_result_sha256")!="4516ac546b78839dee4c6c2ae66e06bb567b85acd61b89afd482d73726f2c636" or
        g.get("lens_identity_sha256")!="829930d591fe6fc09d8a1df5364f05ef8e94adaaa2417b0daf4aba5c714eba7e" or
        g.get("receipt_sha256")!="92cba90559b685ef6b88a0a0bf4d6c10a73e68383f5bd0f1c1271e8aa67418db" or
        g.get("source_home_sequence")!=433 or g.get("input_context_sequence")!=105 or
        g.get("items_processed")!=24 or
        g.get("control_lens_items")!=24 or
        any(g.get(k)!=0 for k in ("forward_lens_items","reverse_lens_items","counterevidence_lens_items")) or
        g.get("executed_deterministic_context_query") is not True or
        g.get("model_call_attested") is not False or
        g.get("p03_admission") is not False or
        g.get("cloud_home_state_mutated") is not False):
        raise AdmissionHold("GENESIS_CONSUMER_PROOF_SCOPE_OR_TRUTH_DRIFT")
    if (any(p.get(k) is not False for k in (
           "protected_independent_checker_active_on_main",
           "outside_custodian_signed_p03_acceptance",
           "accepted_phase_p03",
           "authorized_checkpoint_updated",
           "owner_human_approval_recorded",
           "source_change_authority")) or
        any(f.get(k) is not False for k in (
           "live_cloud_clean_handoff_attested_in_this_lane",
           "github_platform_outage_recovery_attested",
           "recovery_has_graduation_authority")) or
        f.get("synthetic_fault_injection_exists") is not True or
        any(b.get(k) is not False for k in (
           "production_weights_updated","terminal_fork_workflow_reenabled",
           "autonomous_dispatch_performed","source_checkpoint_rewritten")) or
        type(b.get("new_repositories_created")) is not int or
        b["new_repositories_created"]!=0):
        raise AdmissionHold("UNAUTHENTICATED_AUTHORITY_ESCALATION")
    if (latest.get("schema")!="janus.autonomy.latest.v1" or
        checkpoint.get("schema")!="janus.autonomy.checkpoint.v1" or
        latest.get("current_phase")!="P0.3" or
        checkpoint.get("current_phase")!="P0.3"):
        raise AdmissionHold("P03_PHASE_NOT_TRUSTWORTHY")
    return True


def assess(manifest, latest, checkpoint, source_digest):
    validate(manifest,latest,checkpoint)
    if not HEX64.fullmatch(str(source_digest)):
        raise AdmissionHold("UNBOUND_EVIDENCE_DIGEST")
    g=manifest["genesis_context_consumer"]
    a=manifest["private_receiver_ack"]
    checks={
      "receiver_inbox_durable_ack":"SAME_OWNER_ORIGINAL_READ_2_OF_2_NOT_FRESH_EXTERNAL_REPLAY",
      "sender_active_worker_token":"HOLD_CREDENTIAL_NOT_PROVEN",
      "genesis_context_software_query":"ORIGINAL_GITHUB_CPU_RUN_24_HASH_BOUND_ITEMS",
      "genesis_neural_model_consumption":"HOLD_NOT_ATTESTED",
      "four_lens_fitness":"HOLD_1_OF_4_LENSES_PRESENT",
      "externally_authenticated_review":"HOLD_NO_PROTECTED_CUSTODIAN",
      "checkpoint_anchor":"HOLD_DRIFT" if latest.get("state_sha256")!=checkpoint.get("last_verified_snapshot") else "MATCH_ONLY_NOT_ACCEPTANCE",
      "phase_p03_acceptance":"HOLD_NOT_ACCEPTED",
      "real_cross_worker_recovery":"HOLD_CLEAN_REPLAY_NOT_INDEPENDENTLY_ATTESTED",
      "github_platform_failover":"HOLD_SINGLE_PLATFORM"
    }
    report={
      "schema":SCHEMA,
      "status":"HOLD_P03_NO_INDEPENDENT_CONSUMPTION_AND_PHASE_ADMISSION",
      "basis":"ORIGINAL_SAME_OWNER_RECEIPTS_AND_LOCAL_SOURCE_SNAPSHOT_ONLY",
      "original_receiver_claim_verified_at_inbox_only":a["last_batch_identity_sha_match"],
      "actual_software_items_processed":g["items_processed"],
      "original_genesis_run_id":g["run_id"],
      "genesis_model_call_attested":False,
      "evidence_manifest_sha256":source_digest,
      "latest_snapshot_sha256":latest["state_sha256"],
      "last_verified_checkpoint_snapshot_sha256":checkpoint["last_verified_snapshot"],
      "gates":checks,
      "can_update_checkpoint":False,
      "can_wake_janus":False,
      "may_fork_or_spawn_organ":False,
      "can_promote_model":False,
      "p03_accepted":False,
      "signing_key_or_secret_loaded":False,
      "independent_external_acceptance_performed":False,
      "required_next_sources":[
          "ADMIN_SCOPED_PRIVATE_ACK_READ_IN_LAPIS_MAIN",
          "GENESIS_NEURAL_MODEL_CONSUMPTION_AND_CLEAN_WORKER_REPLAY_RECEIPT",
          "PROTECTED_EXTERNAL_CUSTODIAN_REVIEW_AND_AUTHENTICATED_ACCEPTANCE",
          "REVIEWED_CHECKPOINT_SUPERSESSION_NOT_RESET"
      ]
    }
    report["receipt_sha256"]=hashlib.sha256(json.dumps(report,
              ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("."))
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    latest,checkpoint,_,_=recovery.read_evidence(args.root)
    raw=(args.root/EVIDENCE).read_bytes()
    if len(raw)>20_000:
        raise AdmissionHold("EVIDENCE_TOO_LARGE")
    manifest=recovery.decode_strict(raw)
    report=assess(manifest,latest,checkpoint,hashlib.sha256(raw).hexdigest())
    args.out.parent.mkdir(parents=True,exist_ok=True)
    if args.out.exists():
        raise AdmissionHold("OUTPUT_EXISTS")
    args.out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":report["status"],"gates":report["gates"],
                     "p03_accepted":report["p03_accepted"]},sort_keys=True))


if __name__=="__main__":
    main()
