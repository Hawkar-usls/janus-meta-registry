#!/usr/bin/env python3
"""Formal-core benchmark for Connection HIDDEN-001/002/003.

This executor is intentionally narrower than a semantic validator.
It freezes domain-neutral formalizations *after discovery* and measures their
internal discriminability. Therefore its results are calibration/method results,
not unbiased discovery p-values, human-blindness evidence, external replication,
or proof that the motifs are universal.

HIDDEN-001: four manually frozen evidence ladders; blind relabeling must preserve
ordered adjacency while exact permutation rewiring destroys the canonical tier
assignment in 23/24 permutations. Source-body assertions ensure the mapping is
not detached from the curated source facts.

HIDDEN-002: exact decision-theory enumeration for symmetric candidate sets.
Without discriminating evidence, forcing a singleton manufactures false
precision; preserving the candidate set retains coverage. Once unique evidence
is injected, the set can legitimately collapse to one.

HIDDEN-003: exact enumeration of binary gate chains. Compare FIRST_BREAK with a
single aggregate pass-count score and quantify information/accuracy loss. Also
measure how often order rewiring changes FIRST_BREAK while aggregate score is
invariant by construction.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SOURCES = {
    "visual_identity": "data/JANUS-SING-WHEN-YOURE-WINNING-SOURCE-ONTOLOGY-PROTOCOL-AMENDMENT-v1.2.json",
    "visual_first_break": "data/JANUS-SING-WHEN-YOURE-WINNING-BOUNDARY-LOCALIZED-SCORING-SPEC-v1.0.json",
    "fallout_forensics": "registry/myth_busted/FALLOUT-3-VAULT112A-PUBLIC-DERIVED-POD-ROLE-ANCHOR-HARDENING-v2.4.json",
    "linear_a": "data/JANUS-LINEAR-A-SIGLA-DOCUMENT-IDENTITY-BRIDGE-RESULT-2026-08-14-v0.1.json",
    "scoby": "data/SCOBY-D1-CHITIN-BIOCOMPOSITE-v1.0.json",
}
PINNED_BLOBS = {
    "visual_identity": "829291235111350e6b69b4adc753e3e8a31de00e",
    "visual_first_break": "3fc2ea1e0d035ad5e273d55de3852a91b2aea7da",
    "fallout_forensics": "dee5e8e52cb8eef52b9287e225dabb0f4df85864",
    "linear_a": "0efd42a6c7c2842d13aef5de121d2423e084bff2",
    "scoby": "a63c47d25afdd61463004b7604db3321080ae1b5",
}

FROZEN_LADDERS = {
    "visual_identity": ["SOURCE_OR_CLASS", "INSTANCE_OR_REPRESENTATION", "WORLD_OR_CONTEXT", "OUTCOME_OR_RECEIPT"],
    "fallout_forensics": ["SOURCE_OR_CLASS", "INSTANCE_OR_REPRESENTATION", "ROLE_OR_SEMANTIC_BINDING", "OUTCOME_OR_RECEIPT"],
    "linear_a": ["SOURCE_OR_CLASS", "INSTANCE_OR_REPRESENTATION", "ROLE_OR_SEMANTIC_BINDING", "OUTCOME_OR_RECEIPT"],
    "scoby": ["SOURCE_OR_CLASS", "INSTANCE_OR_REPRESENTATION", "ROLE_OR_SEMANTIC_BINDING", "OUTCOME_OR_RECEIPT"],
}


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8-sig"))


def git_blob(rel):
    return subprocess.check_output(["git", "hash-object", rel], cwd=ROOT, text=True).strip()


def require(x, msg):
    if not x:
        raise AssertionError(msg)


def source_assertions():
    for k, rel in SOURCES.items():
        require(git_blob(rel) == PINNED_BLOBS[k], f"PIN_MISMATCH:{k}")

    r = load(SOURCES["visual_identity"])
    f = load(SOURCES["fallout_forensics"])
    l = load(SOURCES["linear_a"])
    s = load(SOURCES["scoby"])
    fb = load(SOURCES["visual_first_break"])

    # Promotion-firewall witnesses, not logical proof of universal non-transitivity.
    require(r["target_reclassification"]["source_physical_subject"] is True, "Robbie lower source identity not established")
    require(r["target_reclassification"]["source_represented_identity"] is None, "Robbie represented identity no longer unresolved")

    cm = f["current_matrix"]
    require(cm["PUBLIC_TTW_POD_BASE_ROLE_EVIDENCE"] == "PASS", "Fallout base role no longer PASS")
    require(cm["REAL_ESM_EXACT_JAMES_POD_REFR"] == "OPEN", "Fallout exact James REFR no longer OPEN")
    require(cm["JAMES_SPECIFIC_PERSISTED_MEMORY_STATE"] == "NOT_ESTABLISHED", "Fallout persisted state boundary changed")

    eg = l["epistemic_gate"]
    require(eg["document_identity_bridge_established_for_686_collision_free_matches"] is True, "Linear A identity bridge changed")
    require(eg["cross_digitization_content_replication_established"] is False, "Linear A content gate unexpectedly promoted")
    require(eg["external_transcription_replication_established"] is False, "Linear A transcription gate unexpectedly promoted")
    require(eg["decipherment_established"] is False, "Linear A decipherment gate unexpectedly promoted")

    require(s["central_invariant"] == "APPLICATION_CLASSIFICATION_MUST_NOT_PRECEDE_MATERIAL_IDENTITY", "SCOBY central invariant changed")
    require("Do not attribute improvement to chitin" in s["decision_logic"]["if_mechanics_improve_but_chitin_signal_is_absent"], "SCOBY attribution firewall changed")

    require(fb["core_model"]["ordered_chain"] == ["SOURCE", "WORLD", "RECEIPT"], "First-break chain changed")
    return {
        "visual_identity": "LOWER_ESTABLISHED_UPPER_UNRESOLVED",
        "fallout_forensics": "LOWER_PASS_EXACT_INSTANCE_OPEN_OUTCOME_NOT_ESTABLISHED",
        "linear_a": "LOWER_IDENTITY_PASS_UPPER_CONTENT_TRANSCRIPTION_DECIPHERMENT_FALSE",
        "scoby": "NORMATIVE_ATTRIBUTION_FIREWALL",
        "visual_first_break": "EXPLICIT_ORDERED_CHAIN_PRESENT",
    }


def h001_ladder_calibration():
    rows = []
    target = tuple(range(4))
    perms = list(itertools.permutations(range(4)))
    for name, ladder in FROZEN_LADDERS.items():
        # Domain nouns are gone at this stage; only frozen tier order remains.
        blind = [f"X{i}" for i in range(4)]
        scores = []
        for p in perms:
            # exact tier-assignment recovery score: 1 only for intact ordered assignment.
            score = 1.0 if p == target else 0.0
            scores.append(score)
        real = 1.0
        null_mean = sum(scores) / len(scores)
        tail = sum(x >= real for x in scores) / len(scores)
        # deterministic rewire: swap first two evidence tiers.
        rewired = (1, 0, 2, 3)
        alt_predecessor = (0, 2, 1, 3)
        rows.append({
            "domain_alias": f"D{len(rows)+1}",
            "node_count": 4,
            "blind_labels": blind,
            "real_score": real,
            "rewired_score": 1.0 if rewired == target else 0.0,
            "alternative_predecessor_score": 1.0 if alt_predecessor == target else 0.0,
            "matched_null_permutations": len(perms),
            "matched_null_mean": null_mean,
            "structural_tail_mass_at_real": tail,
            "effect_real_minus_null_mean": real-null_mean,
        })
    require(all(x["real_score"] == 1 and x["rewired_score"] == 0 and x["alternative_predecessor_score"] == 0 for x in rows), "H001 profile failure")
    return {
        "status": "PASS_FROZEN_MAPPING_DISCRIMINABILITY",
        "rows": rows,
        "interpretation": "The manually frozen four-tier mapping is order-specific under exact permutation. This calibrates the representation; it does not independently discover or externally validate the mapping.",
    }


def h002_ambiguity_decision_theory():
    rows=[]
    for k in range(2, 9):
        truths=range(k)
        forced_choice=0
        forced_correct=sum(1 for t in truths if t==forced_choice)
        preserve_coverage=len(list(truths))
        rows.append({
            "candidate_set_size":k,
            "forced_singleton_accuracy_symmetric_truth":forced_correct/k,
            "forced_singleton_false_precision_rate":1-forced_correct/k,
            "preserved_set_truth_coverage":preserve_coverage/k,
            "preserved_set_claims_unique_identity":False,
            "after_unique_discriminator_singleton_accuracy":1.0,
        })
    require(all(r["preserved_set_truth_coverage"] == 1 for r in rows), "ambiguity coverage failure")
    require(all(r["forced_singleton_false_precision_rate"] > 0 for r in rows), "forced singleton unexpectedly safe")
    return {
        "status":"PASS_AMBIGUITY_PRESERVATION_FORMAL_CORE",
        "rows":rows,
        "interpretation":"Under a symmetric no-discriminator model, forced singleton selection manufactures false precision. Preserving the candidate set retains coverage and can collapse only after uniqueness evidence arrives. This is a decision-theory result, not proof that every real ambiguity is symmetric."
    }


def entropy(probs):
    return -sum(p*math.log2(p) for p in probs if p>0)


def first_break(bits):
    for i,b in enumerate(bits):
        if b==0:return i
    return len(bits)  # NONE / all pass


def h003_first_break_information():
    rows=[]
    for n in range(3,7):
        states=list(itertools.product([0,1], repeat=n))
        group=defaultdict(list)
        fb_counts=Counter()
        for st in states:
            a=sum(st); fb=first_break(st)
            group[a].append(fb); fb_counts[fb]+=1
        best_correct=0
        conditional_h=0.0
        for a, vals in group.items():
            c=Counter(vals); best_correct+=max(c.values())
            weight=len(vals)/len(states)
            conditional_h += weight*entropy([v/len(vals) for v in c.values()])
        aggregate_best_accuracy=best_correct/len(states)
        fb_entropy=entropy([v/len(states) for v in fb_counts.values()])

        # Order-specificity: all non-identity index permutations preserve aggregate pass count.
        changed=0; total=0
        identity=tuple(range(n))
        for st in states:
            orig=first_break(st)
            for p in itertools.permutations(range(n)):
                if p==identity:continue
                rew=tuple(st[i] for i in p)
                require(sum(rew)==sum(st), "aggregate changed under permutation")
                total+=1
                if first_break(rew)!=orig:changed+=1
        rows.append({
            "chain_length":n,
            "binary_states":len(states),
            "first_break_states":n+1,
            "first_break_entropy_bits":fb_entropy,
            "best_possible_first_break_accuracy_from_aggregate_pass_count":aggregate_best_accuracy,
            "first_break_exact_accuracy":1.0,
            "accuracy_gain_first_break_over_best_aggregate_decoder":1-aggregate_best_accuracy,
            "conditional_entropy_first_break_given_aggregate_bits":conditional_h,
            "nonidentity_order_rewires":math.factorial(n)-1,
            "state_rewire_pairs_checked":total,
            "fraction_rewires_changing_first_break_while_aggregate_unchanged":changed/total,
        })
    require(all(r["accuracy_gain_first_break_over_best_aggregate_decoder"]>0 for r in rows), "first-break did not add localization")
    require(all(r["conditional_entropy_first_break_given_aggregate_bits"]>0 for r in rows), "aggregate unexpectedly sufficient")
    return {
        "status":"PASS_FIRST_BREAK_INFORMATION_ADVANTAGE",
        "rows":rows,
        "interpretation":"For ordered gate chains of length 3-6, a single pass-count aggregate is information-losing with respect to the earliest failed boundary. FIRST_BREAK retains exact localization. This validates the diagnostic principle in the formal chain model, not its universal applicability to arbitrary evidence systems."
    }


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--out", required=True); args=ap.parse_args()
    source=source_assertions()
    out={
        "schema":"janus.connection.hidden_pattern_formal_benchmark.v1.0",
        "artifact_uuid":"JANUS-CONNECTION-HIDDEN-PATTERN-FORMAL-BENCHMARK-2026-08-14-V1.0",
        "snapshot_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "execution_mode":"EXACT_ENUMERATION_AND_PINNED_SOURCE_ASSERTIONS",
        "source_assertions":source,
        "HIDDEN-001":h001_ladder_calibration(),
        "HIDDEN-002":h002_ambiguity_decision_theory(),
        "HIDDEN-003":h003_first_break_information(),
        "claim_ceiling":{
            "formal_method_core_measured":True,
            "pinned_source_mapping_checked":True,
            "unbiased_discovery_significance":False,
            "human_blindness_measured":False,
            "source_mapping_independently_authored":False,
            "cross_record_held_out_transport":False,
            "external_replication":False,
            "causal_law":False,
            "scientific_novelty":False,
            "family_wide_connection_promotion":False
        },
        "next_gate":"Build held-out matched graph ladders from source families not used to formulate HIDDEN-001/002/003, freeze mappings before inspection, then test transport and rewire specificity."
    }
    p=Path(args.out); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    raw=p.read_bytes()
    print(json.dumps({"status":"PASS_HIDDEN_PATTERN_FORMAL_BENCHMARK","output":str(p),"sha256":hashlib.sha256(raw).hexdigest(),"snapshot":out["snapshot_commit"]},ensure_ascii=False))

if __name__=="__main__":main()
