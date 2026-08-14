from __future__ import annotations

import argparse
import json
import pathlib
from datetime import datetime, timezone


def load(path: str) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec = load(args.spec)
    acquisition = load(spec["machine_evidence"][0])
    discovery = load(spec["machine_evidence"][1])
    torrossa = load(spec["machine_evidence"][2])

    acq_map = {x["candidate_id"]: x for x in acquisition["candidate_results"]}
    tor_map = {x["candidate_id"]: x for x in torrossa["probe_results"]}

    checks = {
        "parent_canonical_is_v2_18": spec["parent_canonical_state"].endswith("v2.18.json"),
        "candidate_set_exact": set(acq_map) == set(spec["candidate_set"]),
        "initial_acquisition_zero_seals": acquisition["summary"]["sealed_candidate_count"] == 0,
        "initial_acquisition_no_content": acquisition["summary"]["source_content_inspected"] is False,
        "initial_acquisition_no_readings": acquisition["summary"]["source_native_sign_readings_seen"] is False,
        "initial_acquisition_no_overlap": acquisition["summary"]["overlap_selected"] is False,
        "initial_acquisition_no_science": acquisition["summary"]["scientific_comparison_performed"] is False,
        "initial_acquisition_no_r3b": acquisition["summary"]["strict_r3b_replication_established"] is False,
        "route_discovery_complete": discovery["status"] == "METADATA_ONLY_EXTERNAL_ROUTE_DISCOVERY_COMPLETE",
        "route_discovery_did_not_follow_new_routes": discovery["summary"]["newly_discovered_routes_followed"] is False,
        "route_discovery_no_content": discovery["summary"]["source_content_inspected"] is False,
        "route_discovery_no_readings": discovery["summary"]["source_native_sign_readings_seen"] is False,
        "route_discovery_no_overlap": discovery["summary"]["overlap_selected"] is False,
        "torrossa_zero_seals": torrossa["summary"]["sealed_candidate_count"] == 0,
        "torrossa_no_content": torrossa["summary"]["source_content_inspected"] is False,
        "torrossa_no_readings": torrossa["summary"]["source_native_sign_readings_seen"] is False,
        "torrossa_no_overlap": torrossa["summary"]["overlap_selected"] is False,
        "torrossa_no_r3b": torrossa["summary"]["strict_r3b_replication_established"] is False,
        "torrossa_2021_nonpdf": tor_map["NOTTI_2021_THERA"]["classification"] == "FETCHED_NONPDF_RESPONSE_NOT_ADMITTED",
        "torrossa_ph13_nonpdf": tor_map["NOTTI_2024_PH13"]["classification"] == "FETCHED_NONPDF_RESPONSE_NOT_ADMITTED",
        "all_iulm_candidates_nonpdf": all(x["classification"] == "FETCHED_NONPDF_RESPONSE_NOT_ADMITTED" for x in acq_map.values()),
        "human_sweep_not_overclaimed": spec["human_assisted_public_index_sweep"]["machine_replayable"] is False and "not a proof" in spec["human_assisted_public_index_sweep"]["epistemic_limit"].lower(),
    }
    passed = all(checks.values())

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3B-0-STRICT-BLIND-ACQUISITION-FRONTIER-AUDIT-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "strict_blind_acquisition_frontier_audit_result",
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_spec": args.spec,
        "status": "STRICT_BLIND_ACQUISITION_FRONTIER_NEGATIVE_BLINDNESS_PRESERVED" if passed else "FRONTIER_AUDIT_NONPASS",
        "machine_evidence": spec["machine_evidence"],
        "candidate_terminal": {
            "NOTTI_2021_THERA": "NO_PRECONTENT_PDF_SEAL_IULM_SAML_AND_TORROSSA_METADATA_ONLY",
            "NOTTI_2025_THERA_MONOGRAPH": "NO_PRECONTENT_PDF_SEAL_IULM_SAML_OFFICIAL_PAID_EBOOK_ROUTE_NOT_FOLLOWED",
            "NOTTI_2024_PH13": "NO_PRECONTENT_PDF_SEAL_IULM_SAML_AND_TORROSSA_METADATA_ONLY",
        },
        "summary": {
            "candidate_count": 3,
            "sealed_candidate_count": 0,
            "source_native_sign_readings_seen": False,
            "source_content_inspected": False,
            "overlap_selected": False,
            "scientific_comparison_performed": False,
            "strict_r3b_replication_established": False,
            "blind_eligibility_destroyed": False,
            "public_copy_absence_proved": False,
        },
        "human_assisted_public_index_sweep": spec["human_assisted_public_index_sweep"],
        "forbidden_routes": spec["forbidden_routes"],
        "checks": checks,
        "all_checks_pass": passed,
        "next_atomic_requirement": "Acquire an exact lawful byte-bearing copy through a new route or user-supplied lawful copy. Before reading it, create and persist an exact SHA-256/byte-length receipt; only then freeze source-native overlap in a separate gate.",
        "claim_ceiling": spec["claim_ceiling"],
    }
    out = pathlib.Path(args.out)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "summary": result["summary"], "checks": checks}, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
