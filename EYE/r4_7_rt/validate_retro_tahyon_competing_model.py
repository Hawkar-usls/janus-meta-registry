#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

EXPECTED_SOURCE_ID = "JANUS-RETRO-TAHYON-ARCHIVAL-DOSSIER-v1.0"
EXPECTED_SOURCE_STATUS = "ARCHIVAL_PROVENANCE_ESTABLISHED__PHYSICAL_RETROCAUSAL_MECHANISM_NOT_ESTABLISHED"
EXPECTED_GATES = {
    "TOPA-RT-H1": "PROSPECTIVE_PRE_EVENT_INFORMATION_GATE",
    "TOPA-RT-H2": "TEMPORAL_KERNEL_GATE",
    "TOPA-RT-H3": "DAT_VS_FORCE_MODEL_GATE",
    "TOPA-RT-H4": "CARRIER_IDENTITY_GATE",
    "TOPA-RT-H5": "UAP_BRIDGE_GATE",
}
EXPECTED_MINIMUM = ["TOPA-RT-H1", "TOPA-RT-H3", "TOPA-RT-H4"]
EXPECTED_EDGES = {
    "TOPA-RT-H1": {
        tuple(sorted(x)) for x in [
            ["ORDINARY_CAUSAL_OR_LEAKAGE_NULL", "DAT_INFORMATION_SELECTION"],
            ["ORDINARY_CAUSAL_OR_LEAKAGE_NULL", "ADVANCED_TIME_PHYSICAL_CHANNEL"],
            ["ORDINARY_CAUSAL_OR_LEAKAGE_NULL", "TACHYON_SPECIFIC_CARRIER"],
        ]
    },
    "TOPA-RT-H2": set(),
    "TOPA-RT-H3": {
        tuple(sorted(x)) for x in [
            ["DAT_INFORMATION_SELECTION", "ADVANCED_TIME_PHYSICAL_CHANNEL"],
            ["DAT_INFORMATION_SELECTION", "TACHYON_SPECIFIC_CARRIER"],
        ]
    },
    "TOPA-RT-H4": {
        tuple(sorted(x)) for x in [
            ["TACHYON_SPECIFIC_CARRIER", "ORDINARY_CAUSAL_OR_LEAKAGE_NULL"],
            ["TACHYON_SPECIFIC_CARRIER", "DAT_INFORMATION_SELECTION"],
            ["TACHYON_SPECIFIC_CARRIER", "ADVANCED_TIME_PHYSICAL_CHANNEL"],
        ]
    },
    "TOPA-RT-H5": set(),
}


def load(path: Path):
    return json.loads(path.read_text())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--generated-dir", required=True)
    args = ap.parse_args()

    source_path = Path(args.source)
    model_path = Path(args.model)
    generated = Path(args.generated_dir)
    generated.mkdir(parents=True, exist_ok=True)
    source = load(source_path)
    model = load(model_path)

    assert source.get("artifact_id") == EXPECTED_SOURCE_ID, source.get("artifact_id")
    assert source.get("status") == EXPECTED_SOURCE_STATUS, source.get("status")
    assert model.get("source", {}).get("artifact_id") == EXPECTED_SOURCE_ID
    assert model.get("source", {}).get("required_source_status") == EXPECTED_SOURCE_STATUS

    gates = {g["id"]: g for g in source.get("topa_gates", [])}
    assert set(gates) == set(EXPECTED_GATES), sorted(gates)
    for gate_id, source_name in EXPECTED_GATES.items():
        assert gates[gate_id].get("name") == source_name, (gate_id, gates[gate_id])

    uap = source.get("uap_relevance", {})
    assert uap.get("direct_uap_tachyon_link_found") is False, uap
    assert uap.get("nara_rg615", {}).get("byte_level_bulk_scan") == "NOT_COMPLETED", uap

    forbidden = set(source.get("forbidden_inferences", []))
    required_forbidden = {
        "advanced solution -> information actually travels backward in time",
        "precognition-like statistic -> tachyon carrier",
        "tachyon reference -> UAP uses tachyons",
        "small p-value -> reversed causality",
        "duplicate archival copy -> independent replication",
    }
    assert required_forbidden <= forbidden, sorted(required_forbidden - forbidden)

    tests = {t["id"]: t for t in model.get("tests", [])}
    assert set(tests) == set(EXPECTED_GATES), sorted(tests)
    for gate_id in EXPECTED_GATES:
        t = tests[gate_id]
        assert t.get("source_name") == EXPECTED_GATES[gate_id]
        assert float(t.get("cost")) == 1.0, (gate_id, t.get("cost"))
        got_edges = {tuple(sorted(map(str, p))) for p in t.get("distinguishes", [])}
        assert got_edges == EXPECTED_EDGES[gate_id], (gate_id, got_edges, EXPECTED_EDGES[gate_id])
    assert tests["TOPA-RT-H5"].get("available") is False
    assert all(tests[x].get("available") is True for x in ["TOPA-RT-H1", "TOPA-RT-H2", "TOPA-RT-H3", "TOPA-RT-H4"])

    receipt = load(generated / "solver_receipt.json")
    minima = load(generated / "minimum_witness_sets.json")
    loo = load(generated / "leave_one_out_receipt.json")
    unresolved = load(generated / "unresolved_equivalence_classes.json")

    assert receipt.get("status") == "IDENTIFIABILITY_CANDIDATE", receipt
    assert receipt.get("search_status") == "EXACT_MINIMUM_FOUND", receipt
    assert receipt.get("exact_minimum_proved_under_declared_measurement_model") is True, receipt
    assert receipt.get("chosen_additional_tests") == EXPECTED_MINIMUM, receipt
    assert float(receipt.get("chosen_incremental_cost")) == 3.0, receipt
    assert receipt.get("remaining_unresolved_pairs") == [], receipt

    solutions = minima.get("solutions", [])
    assert len(solutions) == 1, solutions
    assert solutions[0].get("additional_tests") == EXPECTED_MINIMUM, solutions
    assert float(solutions[0].get("incremental_cost")) == 3.0, solutions
    assert loo.get("status") == "SUBSET_MINIMAL", loo
    assert {r["removed_test"] for r in loo.get("rows", [])} == set(EXPECTED_MINIMUM), loo
    assert all(r.get("required_for_this_solution") is True for r in loo.get("rows", [])), loo
    assert unresolved.get("unresolved_pairs") == [], unresolved

    source_map = {
        "schema": "janus.eye.r4_7_rt.source_to_benchmark_map.v1",
        "source_artifact_id": EXPECTED_SOURCE_ID,
        "source_status": EXPECTED_SOURCE_STATUS,
        "source_path": str(source_path),
        "benchmark_model": str(model_path),
        "source_uap_direct_link_found": False,
        "source_nara_byte_level_bulk_scan": "NOT_COMPLETED",
        "gate_mappings": [
            {
                "gate_id": gate_id,
                "source_name": EXPECTED_GATES[gate_id],
                "source_design": gates[gate_id].get("design"),
                "source_falsifier": gates[gate_id].get("falsifier"),
                "benchmark_available": bool(tests[gate_id].get("available")),
                "benchmark_unit_cost": float(tests[gate_id].get("cost")),
                "benchmark_pairwise_edges": [list(p) for p in sorted(EXPECTED_EDGES[gate_id])],
                "benchmark_semantics": tests[gate_id].get("benchmark_semantics"),
            }
            for gate_id in EXPECTED_GATES
        ],
        "added_abstractions": model.get("benchmark_abstractions", {}),
        "firewalls": model.get("firewalls", []),
    }
    (generated / "source_to_benchmark_map.json").write_text(
        json.dumps(source_map, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )

    validation = {
        "schema": "janus.eye.r4_7_rt.validation_receipt.v1",
        "status": "PASS_WITH_EPISTEMIC_CEILING",
        "source_grounding": "PASS_RETRO_TAHYON_SOURCE_STATUS_AND_H1_H5_GATES_MATCH",
        "uap_firewall": "PASS_H5_UNAVAILABLE_WHILE_DIRECT_UAP_TACHYON_LINK_FALSE",
        "minimum_witness_set": "PASS_EXACT_UNIT_COST_MINIMUM_H1_H3_H4",
        "leave_one_out": "PASS_ALL_THREE_SELECTED_GATES_REQUIRED",
        "source_git_commit": os.environ.get("GITHUB_SHA", "LOCAL_OR_UNKNOWN"),
        "ceiling": "IDENTIFIABILITY_ONLY_WITHIN_COARSE_JANUS_BENCHMARK_CATALOG__NO_RETROCAUSAL_OR_TACHYON_PHYSICAL_CLAIM",
        "firewalls": [
            "ARCHIVAL_PROVENANCE != PHYSICAL_TRUTH",
            "PROSPECTIVE_ANOMALY != RETROCAUSAL_MECHANISM",
            "RETROCAUSAL_MECHANISM != TACHYON_CARRIER",
            "TACHYON_REFERENCE != UAP_TACHYON_LINK",
            "UNIT_COST != EMPIRICAL_EXPERIMENT_COST",
            "IDENTIFIABLE_WITHIN_BENCHMARK_CATALOG != TRUE_CAUSE_PROVEN",
            "PAIRWISE_DISCRIMINATION_EDGE != OBSERVED_EXPERIMENTAL_RESULT",
        ],
    }
    (generated / "EYE-R4.7-RT-VALIDATION-RECEIPT.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(validation, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
