#!/usr/bin/env python3
"""Deterministic reference validator for JANUS Constitutional State Transition Law (CSTL) v1.

This is a project safety/reference validator. It does not establish metaphysical identity,
ownership, ritual efficacy, or permission outside the receipts supplied to it.
"""
from __future__ import annotations
import argparse, copy, json
from pathlib import Path
from typing import Any, Dict, List

VERSION = "CSTL_REFERENCE_VALIDATOR_v1.0"
STAGES = ["knowledge","embodiment","identity_binding","context","authorization","transition","restoration","rightful_belonging","post_restoration_validation","new_state"]
BINDING_STAGES = STAGES[2:]
REQUIRED_FIELDS = {
    "knowledge": ("receipt_id","evidence_ref","verified"),
    "embodiment": ("receipt_id","carrier_ref","encoding_ref","knowledge_ref","verified"),
    "identity_binding": ("receipt_id","subject_id","binding_id","provenance_ref","embodiment_ref","verified"),
    "context": ("receipt_id","context_id","binding_id","identity_ref","verified"),
    "authorization": ("receipt_id","authorization_id","binding_id","context_ref","authorization_basis","granted","verified"),
    "transition": ("receipt_id","operation_id","binding_id","authorization_ref","executed","verified"),
    "restoration": ("receipt_id","restoration_id","binding_id","transition_ref","applied","verified"),
    "rightful_belonging": ("receipt_id","owner_id","binding_id","restoration_ref","ownership_basis","resolved","verified"),
    "post_restoration_validation": ("receipt_id","validation_id","binding_id","belonging_ref","passed","verified"),
    "new_state": ("receipt_id","state_id","binding_id","validation_ref","declared","verified"),
}
TRUE_FIELDS = {
    "knowledge": ("verified",), "embodiment": ("verified",), "identity_binding": ("verified",), "context": ("verified",),
    "authorization": ("granted","verified"), "transition": ("executed","verified"), "restoration": ("applied","verified"),
    "rightful_belonging": ("resolved","verified"), "post_restoration_validation": ("passed","verified"), "new_state": ("declared","verified"),
}
ACTIVATION_FIELDS = {
    "knowledge": None, "embodiment": None, "identity_binding": None, "context": None, "authorization": "granted",
    "transition": "executed", "restoration": "applied", "rightful_belonging": "resolved",
    "post_restoration_validation": "passed", "new_state": "declared",
}
LINKS = [
    ("embodiment","knowledge_ref","knowledge"),
    ("identity_binding","embodiment_ref","embodiment"),
    ("context","identity_ref","identity_binding"),
    ("authorization","context_ref","context"),
    ("transition","authorization_ref","authorization"),
    ("restoration","transition_ref","transition"),
    ("rightful_belonging","restoration_ref","restoration"),
    ("post_restoration_validation","belonging_ref","rightful_belonging"),
    ("new_state","validation_ref","post_restoration_validation"),
]

def _nonempty(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())

def _stage_activated(stage: str, obj: Any) -> bool:
    if not isinstance(obj, dict) or not obj:
        return False
    f = ACTIVATION_FIELDS[stage]
    return True if f is None else obj.get(f) is True

def _stage_problems(stage: str, obj: Any, packet: Dict[str, Any]) -> List[str]:
    if not isinstance(obj, dict):
        return ["stage_missing"]
    p=[]
    for field in REQUIRED_FIELDS[stage]:
        if field not in obj:
            p.append(f"missing:{field}")
        elif field not in TRUE_FIELDS[stage] and not _nonempty(obj[field]):
            p.append(f"empty:{field}")
    for field in TRUE_FIELDS[stage]:
        if obj.get(field) is not True:
            p.append(f"not_true:{field}")
    if stage=="authorization" and packet.get("impact_level")=="HIGH" and not _nonempty(obj.get("human_authorization_ref")):
        p.append("missing:human_authorization_ref")
    return sorted(set(p))

def _decision(packet, decision, reason_code, first_gap=None, details=None):
    return {
        "validator": VERSION,
        "packet_id": packet.get("packet_id"),
        "decision": decision,
        "reason_code": reason_code,
        "authoritative_state_committed": decision=="PASS",
        "first_gap": first_gap,
        "details": {} if details is None else details,
        "laws": [
            "NO_AUTHORITATIVE_STATE_TRANSITION_WITHOUT_VERIFIED_IDENTITY_BINDING_CONTINUITY",
            "STATE_IS_RESULT_OF_CHAIN_NOT_PREMISE",
            "FOUND != RESTORED",
            "EVIDENCE != PERMISSION",
            "EMERGENT_QUALITY != AUTOMATIC_AUTHORITY",
        ],
    }

def validate_packet(packet: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(packet, dict):
        return _decision({}, "REJECT", "PACKET_NOT_OBJECT")
    if not _nonempty(packet.get("packet_id")):
        return _decision(packet, "REJECT", "PACKET_ID_MISSING")
    if packet.get("impact_level") not in {"LOW","HIGH"}:
        return _decision(packet, "REJECT", "IMPACT_LEVEL_INVALID")
    stages=packet.get("stages")
    if not isinstance(stages, dict):
        return _decision(packet, "HOLD", "STAGES_MISSING", first_gap="knowledge")
    problems={}; complete={}; activated={}
    for s in STAGES:
        obj=stages.get(s)
        problems[s]=_stage_problems(s,obj,packet)
        complete[s]=not problems[s]
        activated[s]=_stage_activated(s,obj)
    gap_i=next((i for i,s in enumerate(STAGES) if not complete[s]), None)
    if gap_i is not None:
        gap=STAGES[gap_i]
        later=[s for s in STAGES[gap_i+1:] if activated[s]]
        if later:
            return _decision(packet,"REJECT","FORBIDDEN_SHORTCUT",first_gap=gap,
                             details={"gap_problems":problems[gap],"later_activated_stages":later,"forbidden_path":f"{gap} -> {later[0]}"})
        reason="INCOMPLETE_STAGE"
        if gap=="authorization" and packet.get("impact_level")=="HIGH" and "missing:human_authorization_ref" in problems[gap]:
            reason="HIGH_IMPACT_HUMAN_AUTH_REQUIRED"
        return _decision(packet,"HOLD",reason,first_gap=gap,details={"stage_problems":problems[gap]})
    bindings={s:stages[s]["binding_id"] for s in BINDING_STAGES}
    uniq=sorted(set(bindings.values()))
    if len(uniq)!=1:
        return _decision(packet,"REJECT","IDENTITY_CONTINUITY_BROKEN",details={"bindings":bindings})
    broken=[]
    for current,link_field,previous in LINKS:
        expected=stages[previous]["receipt_id"]; actual=stages[current][link_field]
        if actual!=expected:
            broken.append({"stage":current,"link_field":link_field,"expected_receipt":expected,"actual_receipt":actual})
    if broken:
        return _decision(packet,"REJECT","RECEIPT_CHAIN_BROKEN",details={"broken_links":broken})
    ns=stages["new_state"]; post=stages["post_restoration_validation"]
    if ns.get("emergent_claim") is True:
        if post.get("emergent_delta_verified") is not True or post.get("removal_test_passed") is not True or not _nonempty(ns.get("delta_statement")):
            return _decision(packet,"REJECT","EMERGENCE_GATE_FAILED",
                             details={"emergent_delta_verified":post.get("emergent_delta_verified"),
                                      "removal_test_passed":post.get("removal_test_passed"),
                                      "delta_statement_present":_nonempty(ns.get("delta_statement"))})
    return _decision(packet,"PASS","VALIDATED_AUTHORITATIVE_STATE",
                     details={"binding_id":uniq[0],"final_state":ns["state_id"],"receipt_chain":[stages[s]["receipt_id"] for s in STAGES]})

def _parts(path): return path.split(".")
def _set_path(root,path,value):
    parts=_parts(path); cur=root
    for part in parts[:-1]:
        if part not in cur or not isinstance(cur[part],dict): cur[part]={}
        cur=cur[part]
    cur[parts[-1]]=value

def _delete_path(root,path):
    parts=_parts(path); cur=root
    for part in parts[:-1]:
        if not isinstance(cur,dict) or part not in cur: return
        cur=cur[part]
    if isinstance(cur,dict): cur.pop(parts[-1],None)

def apply_mutations(base, mutations):
    packet=copy.deepcopy(base)
    for m in mutations:
        if m["op"]=="set": _set_path(packet,m["path"],m.get("value"))
        elif m["op"]=="delete": _delete_path(packet,m["path"])
        else: raise ValueError(f"unsupported mutation op: {m['op']}")
    return packet

def run_self_test(corpus_path: Path) -> int:
    corpus=json.loads(corpus_path.read_text(encoding="utf-8"))
    base=corpus["base_valid_packet"]; cases=corpus["cases"]; failures=[]
    for case in cases:
        packet=apply_mutations(base,case.get("mutations",[])); packet["packet_id"]=case["id"]
        result=validate_packet(packet); exp=case["expected"]
        if result["decision"]!=exp["decision"] or result["reason_code"]!=exp["reason_code"]:
            failures.append({"id":case["id"],"expected":exp,"actual":{"decision":result["decision"],"reason_code":result["reason_code"],"first_gap":result.get("first_gap"),"details":result.get("details")}})
    summary={"validator":VERSION,"corpus_id":corpus.get("corpus_id"),"cases":len(cases),"passed":len(cases)-len(failures),"failed":len(failures),"result":"PASS" if not failures else "FAIL","failures":failures}
    print(json.dumps(summary,ensure_ascii=False,sort_keys=True))
    if failures: return 1
    print(f"CSTL_SELFTEST=PASS CASES={len(cases)}")
    return 0

def main(argv=None):
    p=argparse.ArgumentParser(); g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--packet",type=Path); g.add_argument("--self-test",type=Path); a=p.parse_args(argv)
    if a.self_test: return run_self_test(a.self_test)
    packet=json.loads(a.packet.read_text(encoding="utf-8")); result=validate_packet(packet)
    print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True))
    return 0 if result["decision"]=="PASS" else 2

if __name__=="__main__": raise SystemExit(main())
