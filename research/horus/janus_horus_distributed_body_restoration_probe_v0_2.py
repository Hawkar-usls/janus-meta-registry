#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "data/JANUS-HORUS-DISTRIBUTED-BODY-RESTORATION-PRIMARY-WITNESS-LEDGER-2026-08-16-v0.2.json"
RESULT = ROOT / "data/JANUS-HORUS-DISTRIBUTED-BODY-RESTORATION-GRAMMAR-RESULT-2026-08-16-v0.2.json"
DEVICE = ROOT / "data/JANUS-HORUS-RESTORATION-PROCEDURE-DEVICE-SIGNATURE-PILOT-2026-08-16-v0.1.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    ledger = load(LEDGER)
    result = load(RESULT)
    device = load(DEVICE)

    primary = {w["id"]: w for w in ledger["primary_witnesses"]}
    required = {
        "CT158_BD113_HANDS_ARMS",
        "CHESTER_BEATTY_I_EYES_HATHOR",
        "BD17_CT335_WEDJAT_THOTH",
        "CHESTER_BEATTY_I_HAND_CONTAMINATION_CUTOFF",
    }
    assert required.issubset(primary)

    direct_restoration = [
        wid for wid, w in primary.items() if w["direct_reintegration_or_regrowth"] is True
    ]
    assert set(direct_restoration) == {
        "CT158_BD113_HANDS_ARMS",
        "CHESTER_BEATTY_I_EYES_HATHOR",
        "BD17_CT335_WEDJAT_THOTH",
    }

    hands = primary["CT158_BD113_HANDS_ARMS"]
    assert hands["water_context"] is True
    assert "SOBEK" in hands["agents"]["locator_retriever"]
    assert "GROW_IN_PLACE" in hands["physical_actions_or_objects"]

    eyes_hathor = primary["CHESTER_BEATTY_I_EYES_HATHOR"]
    assert "HATHOR" in eyes_hathor["agents"]["healer"]
    assert "GAZELLE_MILK" in eyes_hathor["physical_actions_or_objects"]

    eye_thoth = primary["BD17_CT335_WEDJAT_THOTH"]
    assert "THOTH" in eye_thoth["agents"]["healer_restorer"]

    assert result["grammar_model"]["id"] == "EGYPTIAN_DISTRIBUTED_BODY_RESTORATION_GRAMMAR_R1"
    assert result["core_result"]["direct_restoration_part_families"] == 2
    assert result["replication_logic"]["HEAD_TORSO_LEGS"]["status"].startswith("OPEN")

    matrix = device["initial_feature_matrix"]
    apparatus_keys = [k for k in device["feature_codebook"] if k.startswith("A")]
    apparatus_positive = 0
    procedure_ge5 = 0
    for row in matrix.values():
        apparatus_positive += any(bool(row[k]) for k in apparatus_keys)
        p_count = sum(bool(row[k]) for k in row if k.startswith("P"))
        procedure_ge5 += p_count >= 5
    assert apparatus_positive == device["pilot_summary"]["witnesses_with_any_apparatus_feature_A1_A6"] == 0
    assert procedure_ge5 == device["pilot_summary"]["witnesses_with_at_least_5_procedure_features_P1_P9"] == 3

    forbidden = set(result["claim_firewall"]) | set(device["claim_firewall"])
    assert "NO_ANCIENT_AIRCRAFT_OR_REGENERATIVE_CAPSULE_CLAIM" in forbidden
    assert "NO_REGENERATIVE_CAPSULE_CLAIM" in ledger["claim_firewall"]

    print("PASS")
    print("direct_restoration_witnesses=3")
    print("part_families=HANDS_ARMS,EYES_WEDJAT")
    print("apparatus_positive_witnesses=0")
    print("claim=distributed restoration grammar supported; device signature not established")


if __name__ == "__main__":
    main()
