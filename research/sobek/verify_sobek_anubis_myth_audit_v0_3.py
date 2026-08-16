#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "JANUS-SOBEK-ANUBIS-MYTH-ICONOGRAPHY-CONFOUND-AUDIT-2026-08-16-v0.3.json"


def require(condition, message):
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def main():
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    require(doc["version"] == "v0.3", "version must be v0.3")
    require("ANUBIS_CANID_CONTROL_REQUIRED" in doc["status"], "status must retain Anubis/canid control requirement")

    ctrl = doc["anubis_canid_control"]["blind_test_requirement"]
    require(ctrl["minimum_canid_deity_controls"] >= 20, "canid-deity controls must be >=20")
    require(ctrl["minimum_anubis_explicitly_identified_when_unblinded"] >= 8, "Anubis anchors must be >=8")
    require(ctrl["minimum_wepwawet_or_other_canid_controls"] >= 6, "other canid controls must be >=6")
    require(ctrl["identity_labels_hidden_during_feature_extraction"] is True, "feature extraction must stay blind")

    ledger = {row["claim_id"]: row for row in doc["myth_claim_ledger"]}
    required = {
        "M1_RA_DISMEMBERED_AND_SOBEK_GATHERS_RA_PARTS": "REJECTED_AS_CURRENT_CANONICAL_CLAIM",
        "M2_OSIRIS_DISMEMBERED_BY_SETH": "SUPPORTED_CORE_NARRATIVE",
        "M3_OSIRIS_EXACTLY_14_PARTS": "DO_NOT_TREAT_AS_UNIVERSAL_PHARAONIC_CONSTANT",
        "M4_SOBEK_RETRIEVES_HORUS_HANDS": "SUPPORTED",
        "M5_SETH_CUT_OFF_HORUS_HANDS_IN_BD113": "REJECTED_FOR_THIS_TEXTUAL_WITNESS",
        "M7_SOBEK_SWALLOWED_OSIRIS_PART_AND_LOST_TONGUE": "TEXTUALLY_UNCERTAIN_DO_NOT_PROMOTE",
        "M11_EYE_OF_OSIRIS_AS_SEPARATE_STANDARD_ICONOGRAPHIC_SYMBOL": "NOT_SUPPORTED_AS_A_PARALLEL_CANONICAL_ICONOGRAPHIC_CLASS"
    }
    for claim_id, verdict in required.items():
        require(claim_id in ledger, f"missing claim ledger row {claim_id}")
        require(ledger[claim_id]["verdict"] == verdict, f"claim {claim_id} verdict changed")

    firewall = set(doc["claim_firewall"])
    required_firewall = {
        "DO_NOT_FIX_OSIRIS_PART_COUNT_AT_14_AS_UNIVERSAL",
        "DO_NOT_ATTRIBUTE_HORUS_HAND_AMPUTATION_TO_SETH_IN_BD113",
        "DO_NOT_PROMOTE_SOBEK_TONGUE_STORY_FROM_DAMAGED_TEXT_TO_CERTAINTY",
        "DO_NOT_LABEL_COFFIN_WEDJAT_EYES_AS_STANDARD_EYE_OF_OSIRIS",
        "DO_NOT_CALL_EVERY_CANID_ANUBIS",
        "DO_NOT_CALL_EVERY_CROCODILE_SOBEK",
        "NO_DIRECT_SOBEK_WEDJAT_LINEAGE_CLAIM",
        "NO_FRACTION_BINARY_ASCII_PYTHON_OR_HIDDEN_TEXT_CLAIM"
    }
    require(required_firewall <= firewall, "claim firewall incomplete")

    amendment = doc["protocol_amendment_for_sobek_v0_2"]
    classes = set(amendment["required_control_classes"])
    require("CANID_DEITIES_ANUBIS_WEPWAWET_DUAMUTEF_WHERE_ELIGIBLE" in classes, "canid control class missing")
    require("NON_SOBEK_CROCODILES" in classes, "generic crocodile controls missing")
    require("LOW_RESOLUTION_OR_DAMAGED_STYLIZED_ANIMAL_HEADS" in classes, "stress controls missing")

    print("PASS: Sobek-Anubis myth/iconography audit v0.3 claim ceiling and control gates intact")


if __name__ == "__main__":
    main()
