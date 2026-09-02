#!/usr/bin/env python3
from __future__ import annotations
import argparse, copy, importlib.util, itertools, json, math, os
from pathlib import Path

class ModelError(ValueError):
    pass

def load_r44():
    path = Path(__file__).resolve().parents[1] / "r4_4" / "eye_r4_4_robust_witness_planner.py"
    spec = importlib.util.spec_from_file_location("eye_r4_4", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("R4_4_IMPORT_FAILED")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def norm_dist(d, label):
    out = {str(k): float(v) for k, v in dict(d).items()}
    if not out or any((not math.isfinite(v) or v < 0) for v in out.values()):
        raise ModelError(f"BAD_DISTRIBUTION:{label}")
    s = sum(out.values())
    if s <= 0 or abs(s - 1.0) > 1e-9:
        raise ModelError(f"PROBABILITIES_MUST_SUM_1:{label}:{s}")
    return out

def parse_base(d):
    causes = {}; total = 0.0
    for raw in d.get("cause_classes", []):
        x = {"id": raw} if isinstance(raw, str) else dict(raw)
        cid = str(x.get("id", "")).strip(); target = str(x.get("target_class", cid)).strip(); prior = float(x.get("prior", 1.0))
        if not cid or cid in causes or not target or prior <= 0 or not math.isfinite(prior):
            raise ModelError(f"BAD_CAUSE:{cid}")
        causes[cid] = {"target_class": target, "prior": prior}; total += prior
    if len(causes) < 2: raise ModelError("NEED_2_CAUSES")
    for c in causes.values(): c["prior"] /= total
    tests = {}
    for raw in d.get("tests", []):
        x = dict(raw); tid = str(x.get("id", "")).strip(); cost = float(x.get("cost", 1.0))
        if not tid or tid in tests: raise ModelError(f"BAD_TEST:{tid}")
        if cost < 0 or not math.isfinite(cost): raise ModelError(f"BAD_COST:{tid}")
        rows = dict(x.get("likelihood_by_cause", {})); base = {}
        if rows:
            if set(rows) != set(causes): raise ModelError(f"LIKELIHOOD_MAP_MISMATCH:{tid}")
            tmp = {c: norm_dist(rows[c], f"{tid}:{c}") for c in causes}; outcomes = sorted(set().union(*(set(v) for v in tmp.values())))
            for c in causes: base[c] = {o: tmp[c].get(o, 0.0) for o in outcomes}
        tests[tid] = {"cost": cost, "base": base, "available": bool(x.get("available", True)), "usable": bool(x.get("decision_usable", True)), "calibrated": bool(x.get("calibrated", False))}
    return causes, tests

def candidate_from_model(base, raw, causes, tests, default_id="candidate"):
    x = dict(raw); mid = str(x.get("id", default_id)).strip() or default_id; provenance = str(x.get("provenance", "declared model")).strip()
    priors = {c: causes[c]["prior"] for c in causes}
    if "prior_by_cause" in x:
        priors = norm_dist(x["prior_by_cause"], f"{mid}:priors")
        if set(priors) != set(causes): raise ModelError(f"CANDIDATE_PRIOR_MISMATCH:{mid}")
    likes = {tid: {c: dict(row) for c, row in t["base"].items()} for tid, t in tests.items()}
    for tid, rows in dict(x.get("likelihood_overrides", {})).items():
        if tid not in tests: raise ModelError(f"CANDIDATE_UNKNOWN_TEST:{mid}:{tid}")
        if set(rows) != set(causes): raise ModelError(f"CANDIDATE_LIKELIHOOD_CAUSE_MISMATCH:{mid}:{tid}")
        tmp = {c: norm_dist(rows[c], f"{mid}:{tid}:{c}") for c in causes}; outs = sorted(set().union(*(set(v) for v in tmp.values())))
        for c in causes: likes[tid][c] = {o: tmp[c].get(o, 0.0) for o in outs}
    return {"id": mid, "provenance": provenance, "weight": float(x.get("weight", 1.0)), "prior_by_cause": priors, "likelihoods": likes, "likelihood_overrides": copy.deepcopy(x.get("likelihood_overrides", {}))}

def validate_policy_tree(receipt):
    if receipt.get("status") != "EXACT_ROBUST_POLICY_FOUND": return
    nodes = {n["node_id"]: n for n in receipt.get("policy_nodes", [])}; root = receipt.get("root_node_id")
    if root not in nodes: raise ModelError("POLICY_ROOT_MISSING")
    def walk(nid, seen_tests, seen_nodes):
        if nid in seen_nodes: raise ModelError("POLICY_GRAPH_CYCLE")
        node = nodes[nid]
        if node.get("terminal"): return
        tid = str(node.get("next_test", ""))
        if not tid: raise ModelError("POLICY_TEST_MISSING")
        if tid in seen_tests: raise ModelError("REPEATED_TEST_ON_POLICY_PATH_UNSUPPORTED")
        branch = node.get("branches", [])
        if not branch: raise ModelError("POLICY_BRANCHES_MISSING")
        for b in branch:
            child = b.get("child_node_id")
            if child not in nodes: raise ModelError("POLICY_CHILD_MISSING")
            walk(child, seen_tests | {tid}, seen_nodes | {nid})
    walk(root, set(), set())

def evaluate_fixed_policy_exact(receipt, cand, causes, tests, min_outcome_probability=0.0):
    if receipt.get("status") != "EXACT_ROBUST_POLICY_FOUND": return {"status": "POLICY_NOT_EVALUABLE", "policy_status": receipt.get("status")}
    validate_policy_tree(receipt); nodes = {n["node_id"]: n for n in receipt.get("policy_nodes", [])}; root = receipt.get("root_node_id")
    acc = {"success": 0.0, "wrong": 0.0, "unresolved": 0.0, "out_of_support": 0.0, "expected_cost": 0.0}
    def rec(nid, cause, path_prob, cost):
        node = nodes[nid]
        if node.get("terminal"):
            label = node.get("identified_target_class"); target = causes[cause]["target_class"]
            if not label: acc["unresolved"] += path_prob
            elif label == target: acc["success"] += path_prob
            else: acc["wrong"] += path_prob
            acc["expected_cost"] += path_prob * cost; return
        tid = str(node.get("next_test", ""))
        if tid not in tests or tid not in cand["likelihoods"] or cause not in cand["likelihoods"][tid]:
            acc["out_of_support"] += path_prob; acc["expected_cost"] += path_prob * cost; return
        row = cand["likelihoods"][tid][cause]; branches = {str(b["outcome"]): b["child_node_id"] for b in node.get("branches", [])}; tcost = tests[tid]["cost"]; used = 0.0
        for outcome, p in row.items():
            p = float(p)
            if p <= min_outcome_probability: continue
            used += p; q = path_prob * p
            if outcome not in branches:
                acc["out_of_support"] += q; acc["expected_cost"] += q * (cost + tcost)
            else: rec(branches[outcome], cause, q, cost + tcost)
        if used < 1.0 - 1e-9:
            q = path_prob * max(0.0, 1.0 - used); acc["out_of_support"] += q; acc["expected_cost"] += q * (cost + tcost)
    for cause, prior in cand["prior_by_cause"].items(): rec(root, cause, float(prior), 0.0)
    hard = acc["wrong"] + acc["unresolved"] + acc["out_of_support"]
    return {"status": "EVALUATED", "candidate_id": cand["id"], "success_probability": round(acc["success"], 12), "wrong_decision_probability": round(acc["wrong"], 12), "unresolved_probability": round(acc["unresolved"], 12), "out_of_policy_support_probability": round(acc["out_of_support"], 12), "policy_risk": round(hard, 12), "expected_cost": round(acc["expected_cost"], 12)}

def parse_continuous_envelope(d, causes, tests):
    env = dict(d.get("uncertainty_envelope", {})); etype = str(env.get("type", "")).strip()
    if etype != "INDEPENDENT_BINARY_LIKELIHOOD_BOX": raise ModelError(f"UNSUPPORTED_CONTINUOUS_CLASS:{etype or 'MISSING'}")
    variables = []; seen_rows = set()
    for raw in env.get("likelihood_intervals", []):
        x = dict(raw); tid = str(x.get("test_id", "")).strip(); cause = str(x.get("cause_id", "")).strip(); outcome = str(x.get("outcome", "")).strip(); lo = float(x.get("lower")); hi = float(x.get("upper"))
        if tid not in tests or cause not in causes: raise ModelError(f"UNKNOWN_INTERVAL_TARGET:{tid}:{cause}")
        if not tests[tid]["available"] or not tests[tid]["usable"] or not tests[tid]["calibrated"]: raise ModelError(f"INTERVAL_TEST_NOT_DECISION_USABLE_CALIBRATED:{tid}")
        row = tests[tid]["base"].get(cause, {})
        if len(row) != 2 or outcome not in row: raise ModelError(f"BINARY_ROW_REQUIRED:{tid}:{cause}")
        if (tid, cause) in seen_rows: raise ModelError(f"DUPLICATE_UNCERTAIN_ROW:{tid}:{cause}")
        if not (0.0 <= lo <= hi <= 1.0): raise ModelError(f"BAD_INTERVAL:{tid}:{cause}")
        seen_rows.add((tid, cause)); other = next(o for o in row if o != outcome)
        variables.append({"kind": "likelihood", "id": f"L:{tid}:{cause}:{outcome}", "test_id": tid, "cause_id": cause, "outcome": outcome, "complement_outcome": other, "lower": lo, "upper": hi})
    prior = env.get("binary_prior_interval")
    if prior is not None:
        if len(causes) != 2: raise ModelError("BINARY_PRIOR_INTERVAL_REQUIRES_2_CAUSES")
        p = dict(prior); cause = str(p.get("cause_id", "")).strip(); lo = float(p.get("lower")); hi = float(p.get("upper"))
        if cause not in causes or not (0.0 <= lo <= hi <= 1.0): raise ModelError("BAD_BINARY_PRIOR_INTERVAL")
        other = next(c for c in causes if c != cause)
        variables.append({"kind": "prior", "id": f"P:{cause}", "cause_id": cause, "complement_cause_id": other, "lower": lo, "upper": hi})
    if not variables: raise ModelError("EMPTY_CONTINUOUS_BOX")
    return env, variables

def corner_model(base, variables, bits, causes, tests, prefix="r46_corner"):
    priors = {c: causes[c]["prior"] for c in causes}; overrides = {}; coords = {}
    for v, bit in zip(variables, bits):
        val = v["upper"] if bit else v["lower"]; coords[v["id"]] = val
        if v["kind"] == "prior":
            priors[v["cause_id"]] = val; priors[v["complement_cause_id"]] = 1.0 - val
        else:
            tid, cause = v["test_id"], v["cause_id"]
            if tid not in overrides: overrides[tid] = {c: dict(tests[tid]["base"][c]) for c in causes}
            overrides[tid][cause][v["outcome"]] = val; overrides[tid][cause][v["complement_outcome"]] = 1.0 - val
    bitstr = "".join("1" if b else "0" for b in bits)
    raw = {"id": f"{prefix}_{bitstr}", "weight": 1.0, "provenance": "R4.6 exact corner derived from declared continuous multi-affine uncertainty box", "prior_by_cause": priors, "likelihood_overrides": overrides}
    cand = candidate_from_model(base, raw, causes, tests, raw["id"]); cand["coordinates"] = coords; cand["corner_bits"] = bitstr
    return raw, cand

def exact_box_attack(receipt, base, variables, causes, tests, max_corners=65536):
    validate_policy_tree(receipt); dims = len(variables); corners = 1 << dims
    if corners > max_corners: return {"status": "UNKNOWN_RESOURCE_LIMIT", "reason": "CORNER_COUNT_EXCEEDS_EXACT_CEILING", "dimensions": dims, "corner_count": corners, "max_corners": max_corners}
    minp = float(base.get("requirements", {}).get("min_outcome_probability", 0.0)); rows = []
    for bits in itertools.product((0, 1), repeat=dims):
        raw, cand = corner_model(base, variables, bits, causes, tests); ev = evaluate_fixed_policy_exact(receipt, cand, causes, tests, minp); rows.append((raw, cand, ev))
    worst_risk = max(rows, key=lambda x: (x[2]["policy_risk"], x[2]["expected_cost"], x[1]["corner_bits"])); worst_cost = max(rows, key=lambda x: (x[2]["expected_cost"], x[2]["policy_risk"], x[1]["corner_bits"]))
    return {"status": "EXACT_CONTINUOUS_BOX_ATTACK_COMPLETED", "dimensions": dims, "corner_count": corners, "all_corners_evaluated": True, "extremum_certificate": "MULTI_AFFINE_BOX_EXTREMA_AT_VERTICES", "worst_risk": {"corner_model": worst_risk[0], "coordinates": worst_risk[1]["coordinates"], "evaluation": worst_risk[2]}, "worst_cost": {"corner_model": worst_cost[0], "coordinates": worst_cost[1]["coordinates"], "evaluation": worst_cost[2]}}

def solve(d, source="MODEL"):
    if "base_problem" not in d: raise ModelError("MISSING_BASE_PROBLEM")
    base = copy.deepcopy(d["base_problem"]); causes, tests = parse_base(base); r44 = load_r44(); current = copy.deepcopy(base); baseline = r44.solve(current, source)
    common = {"schema": "janus.eye.r4_6.continuous_uncertainty_receipt.v1", "artifact_id": d.get("id", source), "source_git_commit": os.getenv("GITHUB_SHA", "LOCAL_OR_UNKNOWN"), "continuous_class": "INDEPENDENT_BINARY_LIKELIHOOD_BOX"}
    if baseline.get("status") != "EXACT_ROBUST_POLICY_FOUND": return {**common, "status": "BASELINE_NOT_ROBUSTLY_SOLVABLE", "baseline_status": baseline.get("status"), "rounds": [], "authority": "NO_CONTINUOUS_ROBUSTNESS_CLAIM", "firewalls": ["BASELINE_NON_IDENTIFIABLE != CONTINUOUS_ADVERSARIAL_BREAK", "UNCERTAINTY_SET != TRUE_WORLD"]}
    if str(base.get("requirements", {}).get("robust_objective", "minimax_expected_cost")) != "minimax_expected_cost": return {**common, "status": "UNSUPPORTED_CONTINUOUS_CLASS", "reason": "R4_6_V1_REQUIRES_MINIMAX_R4_4_REPLAN"}
    _, variables = parse_continuous_envelope(d, causes, tests); cfg = dict(d.get("requirements", {})); max_rounds = int(cfg.get("max_expansion_rounds", 8)); max_dimensions = int(cfg.get("max_dimensions", 16)); max_corners = int(cfg.get("max_corners", 65536)); risk_epsilon = float(cfg.get("risk_epsilon", 1e-12)); cost_epsilon = float(cfg.get("cost_epsilon", 1e-12)); confidence = float(base.get("requirements", {}).get("confidence_threshold", 0.95)); max_policy_risk = float(cfg.get("max_policy_risk", 1.0 - confidence)); max_expected_cost = cfg.get("max_expected_cost"); max_expected_cost = None if max_expected_cost is None else float(max_expected_cost)
    if len(variables) > max_dimensions: return {**common, "status": "UNKNOWN_RESOURCE_LIMIT", "reason": "DIMENSION_COUNT_EXCEEDS_EXACT_CEILING", "dimensions": len(variables), "max_dimensions": max_dimensions, "authority": "NO_CONTINUOUS_COVERAGE_CLAIM"}
    rounds = []; current_receipt = baseline; added_signatures = set()
    for round_i in range(max_rounds + 1):
        attack = exact_box_attack(current_receipt, current, variables, causes, tests, max_corners)
        if attack.get("status") == "UNKNOWN_RESOURCE_LIMIT": return {**common, **attack, "rounds": rounds, "authority": "NO_CONTINUOUS_COVERAGE_CLAIM"}
        wr, wc = attack["worst_risk"], attack["worst_cost"]; risk_break = wr["evaluation"]["policy_risk"] > max_policy_risk + risk_epsilon; cost_break = max_expected_cost is not None and wc["evaluation"]["expected_cost"] > max_expected_cost + cost_epsilon
        if not risk_break and not cost_break:
            return {**common, "status": "CONTINUOUS_BOX_CERTIFIED_UNDER_DECLARED_CLASS", "exact_continuous_search_completed": True, "dimensions": len(variables), "corner_count_per_round": attack["corner_count"], "extremum_certificate": attack["extremum_certificate"], "max_policy_risk": max_policy_risk, "max_expected_cost": max_expected_cost, "worst_risk": wr, "worst_cost": wc, "rounds": rounds, "final_r4_4_status": current_receipt.get("status"), "final_root_next_test": current_receipt.get("root_next_test"), "final_robust_cost": current_receipt.get("robust_cost"), "authority": "EXACT_ONLY_FOR_DECLARED_MULTI_AFFINE_BINARY_LIKELIHOOD_BOX__NOT_TRUE_WORLD_ROBUSTNESS", "firewalls": ["CONTINUOUS_BOX_CERTIFICATE != TRUE_WORLD_ROBUSTNESS", "UNCERTAINTY_SET != TRUE_WORLD", "MULTI_AFFINE_CERTIFICATE != GENERAL_NONLINEAR_UNCERTAINTY_CERTIFICATE", "NO_BREAKER_IN_BOX != NO_BREAKER_OUTSIDE_BOX"]}
        selected = wr if risk_break else wc; selected_reason = "WORST_POLICY_RISK" if risk_break else "WORST_EXPECTED_COST"; raw = copy.deepcopy(selected["corner_model"]); signature = json.dumps({"prior": raw.get("prior_by_cause"), "likes": raw.get("likelihood_overrides")}, sort_keys=True)
        if signature in added_signatures: return {**common, "status": "R4_4_REPLAN_DOES_NOT_CONTROL_DECLARED_R4_6_GATE", "selected_reason": selected_reason, "selected_evaluation": selected["evaluation"], "rounds": rounds, "authority": "NO_CONTINUOUS_ROBUSTNESS_CLAIM"}
        if round_i >= max_rounds: return {**common, "status": "UNKNOWN_RESOURCE_LIMIT", "reason": "MAX_EXPANSION_ROUNDS_REACHED_WITH_CONTINUOUS_BREAKER", "selected_reason": selected_reason, "selected_evaluation": selected["evaluation"], "rounds": rounds, "authority": "NO_CONVERGENCE_CLAIM"}
        raw["id"] = f"r46_round_{round_i+1}_{raw['id']}"; raw["provenance"] = f"R4.6 exact continuous-box adversarial corner; round={round_i+1}; reason={selected_reason}"; current.setdefault("model_set", []).append(raw); added_signatures.add(signature); replanned = r44.solve(current, source)
        rounds.append({"round": round_i + 1, "selected_reason": selected_reason, "selected_corner_coordinates": selected["coordinates"], "selected_evaluation": selected["evaluation"], "pre_root_next_test": current_receipt.get("root_next_test"), "pre_robust_cost": current_receipt.get("robust_cost"), "post_r4_4_status": replanned.get("status"), "post_root_next_test": replanned.get("root_next_test"), "post_robust_cost": replanned.get("robust_cost")}); current_receipt = replanned; st = replanned.get("status")
        if st == "MODEL_SET_TOO_WIDE_FOR_COMMON_ROBUST_IDENTIFICATION": return {**common, "status": "MODEL_SET_EXPLODES_UNDER_CONTINUOUS_ADVERSARY", "rounds": rounds}
        if st == "ROBUST_NON_IDENTIFIABLE_UNDER_DECLARED_MODEL_SET": return {**common, "status": "ROBUST_NON_IDENTIFIABLE_AFTER_CONTINUOUS_EXPANSION", "rounds": rounds}
        if st == "UNKNOWN_RESOURCE_LIMIT": return {**common, "status": "UNKNOWN_RESOURCE_LIMIT", "reason": "R4_4_REPLAN_RESOURCE_LIMIT", "rounds": rounds}
        if st != "EXACT_ROBUST_POLICY_FOUND": return {**common, "status": "R4_4_REPLAN_TERMINATED", "r4_4_status": st, "rounds": rounds}
    raise AssertionError("UNREACHABLE")

def write_outputs(model_path, receipt, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    payloads = {"continuous_uncertainty_receipt.json": receipt, "continuous_attack_trace.json": {"schema": "janus.eye.r4_6.attack_trace.v1", "artifact_id": receipt.get("artifact_id"), "status": receipt.get("status"), "rounds": receipt.get("rounds", []), "source_git_commit": receipt.get("source_git_commit")}, "continuous_certificate_summary.json": {"schema": "janus.eye.r4_6.certificate_summary.v1", "artifact_id": receipt.get("artifact_id"), "status": receipt.get("status"), "continuous_class": receipt.get("continuous_class"), "dimensions": receipt.get("dimensions"), "extremum_certificate": receipt.get("extremum_certificate"), "final_root_next_test": receipt.get("final_root_next_test"), "final_robust_cost": receipt.get("final_robust_cost"), "source_model": str(model_path), "source_git_commit": receipt.get("source_git_commit"), "epistemic_ceiling": receipt.get("authority")}}
    for name, payload in payloads.items(): (outdir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--input", required=True); ap.add_argument("--output-dir", required=True); a = ap.parse_args(); p = Path(a.input); receipt = solve(json.loads(p.read_text(encoding="utf-8")), p.stem); write_outputs(p, receipt, Path(a.output_dir)); print(json.dumps({"status": receipt.get("status"), "final_root_next_test": receipt.get("final_root_next_test"), "rounds": len(receipt.get("rounds", []))}, sort_keys=True))

if __name__ == "__main__": main()
