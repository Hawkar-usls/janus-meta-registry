#!/usr/bin/env python3
import datetime as dt
import hashlib
import json
import os
import pathlib
import urllib.request
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
PREREG_PATH = ROOT / "data/JANUS-INDEPENDENT-FUTURE-DRAND-BENCH-PREREG-2026-09-01-v1.0.json"
RESULT_DIR = ROOT / "data/independent_future_bench"
SUMMARY_PATH = ROOT / "data/JANUS-INDEPENDENT-FUTURE-DRAND-BENCH-SUMMARY-2026-09-01-v1.0.json"
PREREG_COMMIT = "0cec26aabcee7d4dc7c057cc79d8d690b55e3321"
PREREG_COMMIT_UTC = dt.datetime(2026, 9, 1, 1, 14, 37, tzinfo=dt.timezone.utc)
FETCH_DELAY_SECONDS = 120


def parse_utc(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def iso_now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "JANUS-causal-difference-test/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def result_path(n):
    return RESULT_DIR / f"JANUS-DRAND-INDEPENDENT-FUTURE-TRIAL-{n:02d}-2026-09-01-v1.0.json"


def main():
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    authority = prereg["external_entropy_authority"]
    chain_hash = authority["chain_hash"]
    genesis = int(authority["genesis_time_unix"])
    period = int(authority["period_seconds"])
    now = dt.datetime.now(dt.timezone.utc)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    created = []

    relay_templates = prereg["fetch_policy"]["required_relays"]

    for trial in prereg["trials"]:
        n = int(trial["trial"])
        out = result_path(n)
        if out.exists():
            continue

        target = parse_utc(trial["target_utc"])
        if now < target + dt.timedelta(seconds=FETCH_DELAY_SECONDS):
            continue

        base = {
            "schema": "janus.independent_future.drand_trial_result.v1",
            "trial": n,
            "run_utc": iso_now(),
            "prereg_path": str(PREREG_PATH.relative_to(ROOT)),
            "prereg_commit": PREREG_COMMIT,
            "prereg_commit_utc": PREREG_COMMIT_UTC.isoformat().replace("+00:00", "Z"),
            "target_utc": trial["target_utc"],
            "target_local": trial["target_local"],
            "quicknet_round": trial["quicknet_round"],
            "frozen_candidate_derivation_utf8": trial["candidate_derivation_utf8"],
            "frozen_candidate_sha256": trial["pre_return_candidate_sha256"],
            "github_run_id": os.getenv("GITHUB_RUN_ID"),
            "github_sha": os.getenv("GITHUB_SHA"),
            "hard_boundaries": [
                "MISS_DOES_NOT_DISPROVE_ALL_RETROCAUSAL_THEORIES",
                "MATCH_DOES_NOT_BY_ITSELF_PROVE_RETROCAUSALITY",
                "DRAND_TARGET != SIRIUS_MESSAGE",
                "A1 != A2 != A3 != A4 != A5"
            ]
        }

        if not PREREG_COMMIT_UTC < target:
            base.update({
                "prereg_ordering": "INVALID_TARGET_NOT_AFTER_GIT_FREEZE",
                "scorable": False,
                "classification": "PRE_REG_ORDERING_INVALID",
                "exact_match": None,
                "note": "Git commit provenance is authoritative; no target fetch is used to rescue an invalid prospective trial."
            })
            write_json(out, base)
            created.append(out)
            continue

        candidate_recomputed = hashlib.sha256(trial["candidate_derivation_utf8"].encode("utf-8")).hexdigest()
        expected_round = ((int(target.timestamp()) - genesis) // period) + 1
        base["prereg_ordering"] = "PASS_GIT_FREEZE_BEFORE_TARGET"
        base["candidate_recomputed_sha256"] = candidate_recomputed
        base["candidate_recompute_pass"] = candidate_recomputed == trial["pre_return_candidate_sha256"]
        base["round_formula_expected"] = expected_round
        base["round_formula_pass"] = expected_round == int(trial["quicknet_round"])

        if not base["candidate_recompute_pass"] or not base["round_formula_pass"]:
            base.update({
                "scorable": False,
                "classification": "PRE_REG_MISMATCH",
                "exact_match": None
            })
            write_json(out, base)
            created.append(out)
            continue

        relay_responses = []
        for tmpl in relay_templates:
            url = tmpl.format(chain_hash=chain_hash, round=trial["quicknet_round"])
            rec = {"url": url, "fetch_utc": iso_now()}
            try:
                payload = fetch_json(url)
                rec.update({
                    "ok": True,
                    "round": payload.get("round"),
                    "randomness": payload.get("randomness"),
                    "signature": payload.get("signature"),
                    "previous_signature": payload.get("previous_signature")
                })
            except Exception as e:
                rec.update({"ok": False, "error": f"{type(e).__name__}: {e}"})
            relay_responses.append(rec)

        base["relay_responses"] = relay_responses
        successful = [r for r in relay_responses if r.get("ok") and r.get("randomness")]
        if len(successful) < 2:
            base.update({
                "scorable": False,
                "classification": "DATA_ACCESS_BLOCKED",
                "exact_match": None,
                "signature_verification": "NOT_PERFORMED"
            })
            write_json(out, base)
            created.append(out)
            continue

        pairs = [(r.get("round"), r.get("randomness")) for r in successful]
        counts = Counter(pairs)
        consensus_pair, consensus_count = counts.most_common(1)[0]
        if consensus_count < 2 or len(counts) != 1:
            base.update({
                "scorable": False,
                "classification": "DATA_INTEGRITY_HOLD",
                "exact_match": None,
                "relay_consensus": False,
                "signature_verification": "NOT_PERFORMED"
            })
            write_json(out, base)
            created.append(out)
            continue

        observed_round, target_randomness = consensus_pair
        if int(observed_round) != int(trial["quicknet_round"]):
            base.update({
                "scorable": False,
                "classification": "DATA_INTEGRITY_HOLD",
                "exact_match": None,
                "relay_consensus": True,
                "note": "Relays agreed with each other but returned a different round than frozen target."
            })
            write_json(out, base)
            created.append(out)
            continue

        exact = target_randomness.lower() == trial["pre_return_candidate_sha256"].lower()
        base.update({
            "scorable": True,
            "relay_consensus": True,
            "relay_consensus_count": consensus_count,
            "target_randomness": target_randomness,
            "exact_match": exact,
            "classification": "EXACT_MATCH_REQUIRES_FULL_AUDIT" if exact else "MISS_EXPECTED_NULL",
            "signature_verification": "NOT_PERFORMED_SIGNATURES_PRESERVED_RELAY_AGREEMENT_ONLY",
            "causal_difference": {
                "H0_forward_independence_prediction": "candidate != later drand target",
                "H1_operational_future_information_discriminator": "candidate == later drand target by exact 256-bit equality",
                "observed": "H1_EXACT_BIT_DISCRIMINATOR_TRIGGERED" if exact else "H0_COMPATIBLE_MISS"
            }
        })
        write_json(out, base)
        created.append(out)

    paths = [result_path(i) for i in range(1, 17)]
    if all(p.exists() for p in paths) and not SUMMARY_PATH.exists():
        results = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
        classes = Counter(r["classification"] for r in results)
        valid_scorable = sum(1 for r in results if r.get("scorable") is True)
        exact_matches = sum(1 for r in results if r.get("exact_match") is True)
        summary = {
            "schema": "janus.independent_future.drand_bench_summary.v1",
            "artifact_id": "JANUS-INDEPENDENT-FUTURE-DRAND-BENCH-SUMMARY-2026-09-01-v1.0",
            "created_utc": iso_now(),
            "prereg_commit": PREREG_COMMIT,
            "planned_trials": 16,
            "valid_scorable_trials": valid_scorable,
            "class_counts": dict(classes),
            "exact_matches": exact_matches,
            "planned_frozen_union_bound": "16 * 2^-256 = 2^-252 under uniform independent-target premise",
            "corrected_valid_family_union_bound": f"{valid_scorable} * 2^-256 under the same premise",
            "interpretation": "No exact matches is the expected null calibration and does not disprove all retrocausal theories. Any exact match is only an audit trigger, not proof of retrocausality.",
            "trial_01_correction": "PRE_REG_ORDERING_INVALID because target preceded Git freeze; retained rather than erased.",
            "signature_verification_ceiling": "This runner preserves signatures and requires multi-relay agreement but does not perform BLS verification; a positive candidate would require independent signature verification before promotion.",
            "canonical_seal": "COMPARE THE TWO WITNESSES BY A FROZEN DIFFERENCE. KEEP FAILURES. DO NOT LET A MATCH WRITE ITS OWN RULES."
        }
        write_json(SUMMARY_PATH, summary)
        created.append(SUMMARY_PATH)

    print(json.dumps({"created": [str(p.relative_to(ROOT)) for p in created], "now_utc": iso_now()}, indent=2))


if __name__ == "__main__":
    main()
