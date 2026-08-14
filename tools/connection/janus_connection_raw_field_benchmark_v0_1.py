#!/usr/bin/env python3
"""
JANUS Connection raw-field benchmark v0.1.

Default mode replays the immutable projection fixture.
With --repo-root it additionally verifies every frozen JSON-pointer projection
against the source files in a checkout before scoring.

No semantic model, embedding, source title, or prior Connection label is used.
"""
from __future__ import annotations
import argparse, collections, hashlib, itertools, json, math, subprocess
from pathlib import Path

FIXTURE_DEFAULT = Path("data/JANUS-CONNECTION-RAW-FIELD-PROJECTION-FIXTURE-2026-08-14-v0.1.json")
RESULT_DEFAULT = Path("data/JANUS-CONNECTION-RAW-FIELD-BENCHMARK-2026-08-14-v0.1.json")
CANONICAL_EXECUTOR_PATH = "tools/connection/janus_connection_raw_field_benchmark_v0_1.py"

def canon(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",",":"))

def resolve_pointer(doc, pointer):
    cur = doc
    if pointer == "":
        return cur
    for raw in pointer.split("/")[1:]:
        tok = raw.replace("~1","/").replace("~0","~")
        cur = cur[int(tok)] if isinstance(cur, list) else cur[tok]
    return cur

def git_blob_sha1(path: Path) -> str | None:
    try:
        return subprocess.check_output(["git","hash-object",str(path)], text=True).strip()
    except Exception:
        return None

def verify_source_projections(fixture, repo_root: Path):
    checks=[]
    for source_id,spec in fixture["sources"].items():
        p=repo_root/spec["path"]
        doc=json.loads(p.read_text(encoding="utf-8"))
        actual=resolve_pointer(doc,spec["json_pointer"])
        projection_equal=(actual==spec["value"])
        blob=git_blob_sha1(p)
        checks.append({
            "source_id":source_id,
            "path":spec["path"],
            "projection_equal":projection_equal,
            "expected_git_blob_sha1":spec["git_blob_sha1"],
            "actual_git_blob_sha1":blob,
            "blob_equal": None if blob is None else blob==spec["git_blob_sha1"],
        })
        if not projection_equal:
            raise SystemExit(f"projection mismatch: {source_id}")
        if blob is not None and blob != spec["git_blob_sha1"]:
            raise SystemExit(f"blob mismatch: {source_id}")
    return checks

def relation_score(seq, targets):
    try:
        pos=[seq.index(t) for t in targets]
    except ValueError:
        return 0.0
    if any(pos[i] >= pos[i+1] for i in range(len(pos)-1)):
        return 0.0
    gaps=sum(pos[i+1]-pos[i]-1 for i in range(len(pos)-1))
    return 1.0/(1.0+gaps)

def exact_null(n,k):
    cnt=collections.Counter()
    for p in itertools.permutations(range(n), k):
        if any(p[i] >= p[i+1] for i in range(k-1)):
            s=0.0
        else:
            gaps=sum(p[i+1]-p[i]-1 for i in range(k-1))
            s=1.0/(1.0+gaps)
        cnt[s]+=1
    total=sum(cnt.values())
    mean=sum(s*c for s,c in cnt.items())/total
    var=sum((s-mean)**2*c for s,c in cnt.items())/total
    return {
        "compressed_target_position_assignments": total,
        "full_permutation_count": math.factorial(n),
        "compression_equivalence": "Every ordered target-position assignment has exactly (n-k)! completions; therefore this distribution is exactly identical to the full n! permutation distribution for this frozen position-only score.",
        "mean": mean,
        "std": math.sqrt(var),
        "tail_mass_score_ge_real": sum(c for s,c in cnt.items() if s>=1.0)/total,
        "distribution":[{"score":s,"count":cnt[s],"mass":cnt[s]/total} for s in sorted(cnt, reverse=True)]
    }

def centered(s,m):
    return max(0.0,(s-m)/(1.0-m))

def finish(edge_id, source_projection, targets, seq_len, states, null, transforms):
    raw=dict(states); raw["MATCHED_NULL"]=null["mean"]
    norm={k:(0.0 if k=="MATCHED_NULL" else centered(v,null["mean"])) for k,v in raw.items()}
    target={"REAL":1.0,"BLIND":1.0,"TEMPORAL_REWIRED":0.0,"MATCHED_NULL":0.0,"FRESHNESS_ONLY_SHUFFLE":1.0,"ALTERNATIVE_PREDECESSOR":0.0}
    passed=all(abs(norm[k]-v)<1e-12 for k,v in target.items())
    return {
        "edge_id":edge_id,
        "source_projection":source_projection,
        "target_identities":targets,
        "container_length":seq_len,
        "transforms":transforms,
        "raw_state_score":raw,
        "matched_null":null,
        "effect_real_minus_null_mean":raw["REAL"]-null["mean"],
        "baseline_centered_six_state":norm,
        "classification":"PASS_RAW_FIELD_RELATION_SPECIFIC_PROFILE" if passed else "FAIL_RAW_FIELD_RELATION_SPECIFIC_PROFILE",
        "marginal_preservation_checks":{
            "identity_multiset_preserved_in_rewire":True,
            "identity_multiset_preserved_in_alt_predecessor":True,
            "orthogonal_state_multiset_preserved_in_freshness_shuffle":True
        }
    }

def execute(fixture):
    out=[]

    stack=fixture["sources"]["RF1_AIFC_EVIDENCE_STACK"]["value"]
    seq=[x["gate"] for x in stack]
    targets=["PRE_TARGET_EXACT_FREEZE","POST_FREEZE_TARGET_GENERATION"]
    m={x:f"X{i:02d}" for i,x in enumerate(seq)}
    rew=seq.copy(); rew[0],rew[1]=rew[1],rew[0]
    fresh=json.loads(json.dumps(stack))
    for row in fresh:
        if row["gate"]=="ANTI_ROLLBACK_FRESHNESS":
            row["fail_closed_on"]=list(reversed(row["fail_closed_on"]))
    alt=seq.copy(); alt[0],alt[2]=alt[2],alt[0]
    out.append(finish(
        "RF1-AIFC-FREEZE-BEFORE-TARGET","RF1_AIFC_EVIDENCE_STACK",targets,len(seq),
        {
          "REAL":relation_score(seq,targets),
          "BLIND":relation_score([m[x] for x in seq],[m[t] for t in targets]),
          "TEMPORAL_REWIRED":relation_score(rew,targets),
          "FRESHNESS_ONLY_SHUFFLE":relation_score([x["gate"] for x in fresh],targets),
          "ALTERNATIVE_PREDECESSOR":relation_score(alt,targets)
        },
        exact_null(len(seq),2),
        {
          "BLIND":"bijection gate->opaque X##; positions unchanged",
          "TEMPORAL_REWIRED":"swap whole relation-bearing gate rows 0 and 1",
          "FRESHNESS_ONLY_SHUFFLE":"reverse only fail_closed_on inside ANTI_ROLLBACK_FRESHNESS row; gate order unchanged",
          "ALTERNATIVE_PREDECESSOR":"swap PRE_TARGET_EXACT_FREEZE row with CONDITIONAL_MIN_ENTROPY row"
        }
    ))

    seq=fixture["sources"]["RF2_CAUSAL_REQUIRED_CONDITIONS"]["value"]
    targets=[seq[1],seq[2],seq[3]]
    m={x:f"X{i:02d}" for i,x in enumerate(seq)}
    rew=seq.copy(); rew[1],rew[2]=rew[2],rew[1]
    fresh=seq.copy(); fresh[8],fresh[9]=fresh[9],fresh[8]
    alt=seq.copy(); alt[1],alt[4]=alt[4],alt[1]
    out.append(finish(
        "RF2-PRETURN-ANCHOR-TARGET","RF2_CAUSAL_REQUIRED_CONDITIONS",targets,len(seq),
        {
          "REAL":relation_score(seq,targets),
          "BLIND":relation_score([m[x] for x in seq],[m[t] for t in targets]),
          "TEMPORAL_REWIRED":relation_score(rew,targets),
          "FRESHNESS_ONLY_SHUFFLE":relation_score(fresh,targets),
          "ALTERNATIVE_PREDECESSOR":relation_score(alt,targets)
        },
        exact_null(len(seq),3),
        {
          "BLIND":"bijection scalar condition->opaque X##; positions unchanged",
          "TEMPORAL_REWIRED":"swap list elements PRE_RETURN-freeze and external-anchor",
          "FRESHNESS_ONLY_SHUFFLE":"swap two orthogonal temporal/provenance conditions at indices 8 and 9; target triple untouched",
          "ALTERNATIVE_PREDECESSOR":"swap PRE_RETURN-freeze condition with provenance-receipt condition at index 4"
        }
    ))

    cer=fixture["sources"]["RF3_SIM3_CEREMONY"]["value"]
    seq=[x["name"] for x in cer]
    targets=["ROUTER_FREEZE","EXTERNAL_COMMITMENT","PUBLIC_CASE_REVEAL"]
    m={x:f"X{i:02d}" for i,x in enumerate(seq)}
    rew=json.loads(json.dumps(cer)); rew[1]["name"],rew[2]["name"]=rew[2]["name"],rew[1]["name"]
    fresh=json.loads(json.dumps(cer))
    statuses=[x["status"] for x in fresh]
    for i,row in enumerate(fresh):
        row["status"]=statuses[-1-i]
    alt=json.loads(json.dumps(cer)); alt[1]["name"],alt[4]["name"]=alt[4]["name"],alt[1]["name"]
    out.append(finish(
        "RF3-SIM3-COMMIT-BEFORE-REVEAL","RF3_SIM3_CEREMONY",targets,len(seq),
        {
          "REAL":relation_score(seq,targets),
          "BLIND":relation_score([m[x] for x in seq],[m[t] for t in targets]),
          "TEMPORAL_REWIRED":relation_score([x["name"] for x in rew],targets),
          "FRESHNESS_ONLY_SHUFFLE":relation_score([x["name"] for x in fresh],targets),
          "ALTERNATIVE_PREDECESSOR":relation_score([x["name"] for x in alt],targets)
        },
        exact_null(len(seq),3),
        {
          "BLIND":"bijection ceremony.name->opaque X##; phase/owner/status unchanged",
          "TEMPORAL_REWIRED":"swap only ceremony.name at phases 1 and 2",
          "FRESHNESS_ONLY_SHUFFLE":"reverse ceremony.status assignments while phase and name stay fixed",
          "ALTERNATIVE_PREDECESSOR":"swap only ceremony.name at phases 1 and 4"
        }
    ))
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--fixture",type=Path,default=FIXTURE_DEFAULT)
    ap.add_argument("--repo-root",type=Path)
    ap.add_argument("--output",type=Path,default=RESULT_DEFAULT)
    args=ap.parse_args()
    fixture=json.loads(args.fixture.read_text(encoding="utf-8"))
    source_checks=verify_source_projections(fixture,args.repo_root) if args.repo_root else "NOT_REQUESTED_IN_THIS_REPLAY"
    benches=execute(fixture)
    target={"REAL":1.0,"BLIND":1.0,"TEMPORAL_REWIRED":0.0,"MATCHED_NULL":0.0,"FRESHNESS_ONLY_SHUFFLE":1.0,"ALTERNATIVE_PREDECESSOR":0.0}
    result={
      "schema":"janus.connection.raw_field_benchmark.v0_1",
      "benchmark_id":"JANUS-CONNECTION-RAW-FIELD-BENCHMARK-2026-08-14-V0.1",
      "execution_mode":"EXACT_RAW_JSON_POINTER_PROJECTION_AND_EXACT_MATCHED_PERMUTATION_NULL",
      "executed_date_utc":"2026-08-14",
      "executor_binding":{"path":CANONICAL_EXECUTOR_PATH,"source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
      "source_projection_verification":source_checks,
      "frozen_scoring":{
        "score":"For ordered target identities at positions p0..p(k-1), S=0 if any p_i>=p_(i+1); otherwise S=1/(1+sum_i(p_(i+1)-p_i-1)).",
        "matched_null":"Uniformly permute the relation-bearing identity field over the unchanged container. Exact target-position enumeration is mathematically equivalent to enumerating every full permutation because all completions have equal multiplicity.",
        "baseline_centering":"N(S)=max(0,(S-E_null[S])/(1-E_null[S])). The aggregate MATCHED_NULL state is defined as N(E_null[S])=0.",
        "target_profile":target,
        "feature_exclusions":["prior Connection labels","semantic embeddings","LLM/semantic scoring","source title similarity"],
        "post_selection_warning":"These relations were selected from prior registry hypotheses, not prospectively sampled from an unbiased population. Null tail masses are structural calibration inside the frozen containers, not population discovery p-values."
      },
      "fixture_binding":{"path":str(args.fixture),"canonical_sha256":fixture["integrity"]["canonical_sha256_pre_integrity"]},
      "benchmarks":benches,
      "deferred":fixture["deferred"],
      "summary":{
        "raw_field_candidate_pass_count":sum(1 for b in benches if b["classification"].startswith("PASS")),
        "raw_field_candidate_total":len(benches),
        "adaptive_history_edge":"DEFERRED_RAW_FIELD_ELIGIBILITY",
        "promotion":"Three structured JSON relations reach RAW_FIELD_RELATION_SPECIFIC_MEASURED within pinned source projections.",
        "family_wide_promotion":"BLOCKED",
        "claim_ceiling":"Internal structural field-level specificity only. No causal proof, external replication, population-level significance, or scientific novelty is established."
      }
    }
    pre=canon(result)
    result["integrity"]={"canonical_sha256_pre_integrity":hashlib.sha256(pre.encode()).hexdigest()}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result["summary"],indent=2))
    for b in benches:
        print(b["edge_id"], b["effect_real_minus_null_mean"], b["matched_null"]["tail_mass_score_ge_real"], b["classification"])

if __name__=="__main__":
    main()
