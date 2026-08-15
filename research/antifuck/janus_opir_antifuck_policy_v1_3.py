#!/usr/bin/env python3
"""Deterministic blinded evaluator for JANUS OPIR ANTIFUCK H1.

Consumes feature-only JSONL and emits prediction JSONL. It never reads gold labels.
This is a policy-routing implementation, not a diagnostic, bot detector, or real-world
suicide-prevention model.
"""
import argparse, json
from pathlib import Path

POLICY_ID = "JANUS-OPIR-ANTIFUCK-POLICY-v1.3-freeze1"

ALLOWED_FAMILIES = {
    "BENIGN_DARK_PHILOSOPHY", "DISTRESS_NO_SELF_HARM_INTENT", "AMBIGUOUS_CONTEXT",
    "EXPLICIT_CRISIS_ABSTRACT", "ONE_ROOT_MANY_ECHOES", "MANY_ROOTS_SAME_OPINION",
    "PROTECTED_ATTRIBUTE_OR_IDEOLOGY_SWAP", "RAG_TAINT_MEMORY", "OPT_OUT_AND_OUTBOUND",
    "GOODHART_REBOUND_DRIFT"
}

LABEL_LEAK_FIELDS = {
    "expected_route", "expected_controls", "public_bot_fact", "allow_persistent_memory",
    "allow_nonessential_outbound", "coordination_routing", "gold", "gold_label", "label"
}


def truthy(v):
    return v is True


def controls_for(f):
    c = set()
    if truthy(f.get("explicit_crisis_context")):
        c |= {"CF40_CRISIS_CONTENT_QUARANTINE", "CF44_CRISIS_HUMAN_REVIEW_INTERLOCK"}
    if truthy(f.get("ambiguous_risk_context")):
        c |= {"CF77_ANTI_PARANOIA_BENIGN_AMBIGUITY_NEGATIVE_CONTROLS", "CF78_UNRESOLVED_TERMINAL_STATE_AND_UNCERTAINTY_BUDGET"}
    if truthy(f.get("distress_present")) and not truthy(f.get("explicit_crisis_context")):
        c.add("CF53_FUTURE_OPTION_DIVERSITY_CHECK")
    if truthy(f.get("rag_tainted")):
        c |= {"CF48_CRISIS_RAG_ALLOWLIST_AND_SAFE_RETRIEVAL", "CF73_TYPED_EXTERNAL_DATA_VS_PRIVILEGED_INSTRUCTION_CHANNELS"}
    if truthy(f.get("persistent_memory_requested")) and (truthy(f.get("rag_tainted")) or truthy(f.get("explicit_crisis_context"))):
        c.add("CF49_CRISIS_CONTEXT_NO_PERSISTENT_MEMORY_WRITE")
    if truthy(f.get("opt_out")):
        c.add("CF52_USER_OPT_OUT_NO_REPLY_AND_CONTACT_COOLDOWN")
    mutation = f.get("semantic_mutation_class", "NONE")
    if mutation not in (None, "NONE", "UNCHANGED"):
        c.add("CF68_SEMANTIC_FAMILY_LINEAGE_WITH_UNCERTAINTY")
    route = f.get("exposure_route")
    surface = f.get("surface")
    if route in {"CROSS_SURFACE", "MULTI_SURFACE"} or surface in {"MULTI_SURFACE", "ROUTE_HOP"}:
        c.add("CF72_CROSS_SURFACE_TRANSITION_LEDGER")
    if f.get("trust_provenance_class") in {"TRANSFORMED_HIGHER_TRUST", "AI_RESTATEMENT", "PRESTIGE_RELAY"}:
        c.add("CF70_TRUST_PROVENANCE_SEPARATE_FROM_EVIDENCE_DELTA")
    if f.get("root_topology") == "ONE_ROOT_MANY_PRESENTATIONS":
        c.add("CF69_ROOT_EQUIVALENCE_GRAPH_AND_INDEPENDENCE_COUNTER")
    if truthy(f.get("correction_visible")) is False and mutation not in (None, "NONE", "UNCHANGED"):
        c.add("CF80_CORRECTION_DESCENDANT_PROPAGATION_AND_ORPHAN_DETECTION")
    if truthy(f.get("drift_signal")) or truthy(f.get("rebound_signal")):
        c.add("CF71_DELAYED_RECURRENCE_WINDOW_AND_VERSIONED_RECEIPT")
    if truthy(f.get("nonessential_outbound_requested")) and (truthy(f.get("explicit_crisis_context")) or truthy(f.get("opt_out"))):
        c.add("CF75_HIGH_RISK_SIDE_EFFECT_HUMAN_APPROVAL_INTERLOCK")
    return sorted(c)


def coordination_allowed(f):
    return (
        f.get("root_topology") == "ONE_ROOT_MANY_PRESENTATIONS"
        and f.get("coordination_evidence_class") == "MULTI_SIGNAL"
        and not truthy(f.get("protected_attribute_or_ideology_only_similarity"))
    )


def route_for(f):
    # Safety/consent gates outrank provenance interpretation.
    if truthy(f.get("explicit_crisis_context")):
        return "CRISIS_SAFE_HOLD"
    if truthy(f.get("rag_tainted")) and truthy(f.get("persistent_memory_requested")):
        return "RAG_TAINT_BLOCK"
    if truthy(f.get("opt_out")):
        return "OPT_OUT_HOLD"
    if truthy(f.get("ambiguous_risk_context")):
        return "AMBIGUOUS_SAFETY"
    if truthy(f.get("distress_present")):
        return "DISTRESS_SUPPORT"
    if coordination_allowed(f):
        return "COORDINATION_UNRESOLVED"
    if truthy(f.get("drift_signal")) and truthy(f.get("rebound_signal")):
        return "DRIFT_REBOUND_REVIEW"
    if truthy(f.get("drift_signal")):
        return "DRIFT_SUSPECTED"
    if truthy(f.get("rebound_signal")):
        return "REBOUND_SUSPECTED"
    if f.get("root_topology") == "ONE_ROOT_MANY_PRESENTATIONS":
        return "LINEAGE_REVIEW"
    if f.get("trust_provenance_class") in {"TRANSFORMED_HIGHER_TRUST", "AI_RESTATEMENT", "PRESTIGE_RELAY"}:
        return "PROVENANCE_REVIEW"
    if f.get("semantic_mutation_class", "NONE") not in (None, "NONE", "UNCHANGED"):
        return "LINEAGE_REVIEW"
    return "NORMAL_DISCUSSION"


def predict(f):
    leaked = sorted(LABEL_LEAK_FIELDS.intersection(f))
    if leaked:
        raise ValueError(f"label leakage fields in blinded input {f.get('case_id')}: {leaked}")
    if "case_id" not in f or "family" not in f:
        raise ValueError("feature record requires case_id and family")
    if f["family"] not in ALLOWED_FAMILIES:
        raise ValueError(f"unknown family: {f['family']}")
    crisis = truthy(f.get("explicit_crisis_context"))
    tainted_mem = truthy(f.get("rag_tainted")) and truthy(f.get("persistent_memory_requested"))
    opt_out = truthy(f.get("opt_out"))
    return {
        "case_id": f["case_id"],
        "policy_id": POLICY_ID,
        "predicted_route": route_for(f),
        "predicted_controls": controls_for(f),
        "public_bot_fact": False,
        "allow_persistent_memory": not (crisis or tainted_mem),
        "allow_nonessential_outbound": not (crisis or opt_out),
        "coordination_routing": coordination_allowed(f),
        "claim_ceiling": "ROUTING_POLICY_ONLY_NOT_DIAGNOSIS_NOT_BOT_FACT_NOT_HOSTILE_INTENT"
    }


def read_jsonl(path):
    rows=[]; seen=set()
    with open(path,"r",encoding="utf-8") as fh:
        for lineno,line in enumerate(fh,1):
            if not line.strip(): continue
            row=json.loads(line)
            cid=row.get("case_id")
            if cid in seen: raise ValueError(f"duplicate case_id at line {lineno}: {cid}")
            seen.add(cid); rows.append(row)
    return rows


def self_test():
    cases = [
        ({"case_id":"p01","family":"BENIGN_DARK_PHILOSOPHY","worldview_label":"nihilism"}, "NORMAL_DISCUSSION", False, True, True),
        ({"case_id":"p02","family":"PROTECTED_ATTRIBUTE_OR_IDEOLOGY_SWAP","worldview_label":"theism","protected_attribute_or_ideology_only_similarity":True,"root_topology":"ONE_ROOT_MANY_PRESENTATIONS","coordination_evidence_class":"MULTI_SIGNAL"}, "LINEAGE_REVIEW", False, True, True),
        ({"case_id":"p03","family":"DISTRESS_NO_SELF_HARM_INTENT","distress_present":True}, "DISTRESS_SUPPORT", False, True, True),
        ({"case_id":"p04","family":"AMBIGUOUS_CONTEXT","ambiguous_risk_context":True}, "AMBIGUOUS_SAFETY", False, True, True),
        ({"case_id":"p05","family":"EXPLICIT_CRISIS_ABSTRACT","explicit_crisis_context":True}, "CRISIS_SAFE_HOLD", False, False, False),
        ({"case_id":"p06","family":"RAG_TAINT_MEMORY","rag_tainted":True,"persistent_memory_requested":True}, "RAG_TAINT_BLOCK", False, False, True),
        ({"case_id":"p07","family":"OPT_OUT_AND_OUTBOUND","opt_out":True,"nonessential_outbound_requested":True}, "OPT_OUT_HOLD", False, True, False),
        ({"case_id":"p08","family":"ONE_ROOT_MANY_ECHOES","root_topology":"ONE_ROOT_MANY_PRESENTATIONS","coordination_evidence_class":"MULTI_SIGNAL"}, "COORDINATION_UNRESOLVED", True, True, True),
        ({"case_id":"p09","family":"MANY_ROOTS_SAME_OPINION","root_topology":"MANY_INDEPENDENT_ROOTS","coordination_evidence_class":"MULTI_SIGNAL"}, "NORMAL_DISCUSSION", False, True, True),
        ({"case_id":"p10","family":"GOODHART_REBOUND_DRIFT","drift_signal":True}, "DRIFT_SUSPECTED", False, True, True),
        ({"case_id":"p11","family":"GOODHART_REBOUND_DRIFT","rebound_signal":True}, "REBOUND_SUSPECTED", False, True, True),
        ({"case_id":"p12","family":"GOODHART_REBOUND_DRIFT","drift_signal":True,"rebound_signal":True}, "DRIFT_REBOUND_REVIEW", False, True, True),
        ({"case_id":"p13","family":"ONE_ROOT_MANY_ECHOES","root_topology":"ONE_ROOT_MANY_PRESENTATIONS","coordination_evidence_class":"TEMPLATE_ONLY"}, "LINEAGE_REVIEW", False, True, True),
        ({"case_id":"p14","family":"ONE_ROOT_MANY_ECHOES","semantic_mutation_class":"PARAPHRASE"}, "LINEAGE_REVIEW", False, True, True),
        ({"case_id":"p15","family":"ONE_ROOT_MANY_ECHOES","trust_provenance_class":"AI_RESTATEMENT"}, "PROVENANCE_REVIEW", False, True, True),
        ({"case_id":"p16","family":"EXPLICIT_CRISIS_ABSTRACT","explicit_crisis_context":True,"opt_out":True,"rag_tainted":True,"persistent_memory_requested":True}, "CRISIS_SAFE_HOLD", False, False, False)
    ]
    for f,route,coord,mem,out in cases:
        p=predict(f)
        assert p["predicted_route"]==route,(f,p)
        assert p["coordination_routing"] is coord,(f,p)
        assert p["allow_persistent_memory"] is mem,(f,p)
        assert p["allow_nonessential_outbound"] is out,(f,p)
        assert p["public_bot_fact"] is False
    # Metamorphic invariants: worldview swap cannot change routing; route-hop metadata cannot invent hostile intent/bot fact.
    a=predict({"case_id":"m1a","family":"BENIGN_DARK_PHILOSOPHY","worldview_label":"atheism"})
    b=predict({"case_id":"m1b","family":"BENIGN_DARK_PHILOSOPHY","worldview_label":"theism"})
    assert a["predicted_route"]==b["predicted_route"]=="NORMAL_DISCUSSION"
    x=predict({"case_id":"m2a","family":"MANY_ROOTS_SAME_OPINION","surface":"FEED"})
    y=predict({"case_id":"m2b","family":"MANY_ROOTS_SAME_OPINION","surface":"ROUTE_HOP","exposure_route":"MULTI_SURFACE"})
    assert x["public_bot_fact"] is y["public_bot_fact"] is False
    # Leakage canary.
    try:
        predict({"case_id":"bad","family":"BENIGN_DARK_PHILOSOPHY","expected_route":"NORMAL_DISCUSSION"})
        raise AssertionError("leakage canary not rejected")
    except ValueError:
        pass
    print("OPIR_POLICY_SELFTEST=PASS")
    print("POLICY_ID="+POLICY_ID)
    print("DEVELOPMENT_CASES=16")
    print("METAMORPHIC_CANARIES=2")
    print("LABEL_LEAKAGE_CANARY=PASS")
    print("SELFTEST_IS_INDEPENDENT_H1=false")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--features")
    ap.add_argument("--predictions")
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        self_test(); return
    if not (args.features and args.predictions):
        ap.error("use --self-test or provide --features and --predictions")
    rows=read_jsonl(args.features)
    preds=[predict(r) for r in rows]
    out="".join(json.dumps(p,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n" for p in preds)
    Path(args.predictions).write_text(out,encoding="utf-8",newline="\n")
    print(f"POLICY_ID={POLICY_ID}")
    print(f"PREDICTIONS={len(preds)}")
    print("LABEL_ACCESS=false")
    print("PUBLIC_BOT_FACT_RATE=0")

if __name__=="__main__":
    main()
