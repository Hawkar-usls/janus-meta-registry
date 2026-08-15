#!/usr/bin/env python3
"""JANUS Wedjat v0.5 — eye identity/polarity graph consistency probe.

This probe does NOT infer ancient code. It asks a narrower historical question:
which simplified identity model of the Wedjat eye is consistent with a small set of
source-qualified museum/textual observations?

The admitted observations are deliberately heterogeneous and source-qualified:
- Met: Wedjat as healed eye of Horus; human+falcon morphology; period-dependent spiral.
- UCL Digital Egypt, Book of the Dead ch. 17: a damaged/repaired Wedjat in the
  Horus-Seth conflict is glossed in one passage as the right eye of Ra.
- British Museum: Horus's right/left eyes can be described as sun/moon; right,
  left and double-sided Wedjat amulets are catalogued; Naukratis records call
  left examples usually rare.
- Met relief: Wedjat eyes are offered to Khepri, newborn sun.

The output is a logical compatibility audit, not a frequency estimate or theology.
"""
from __future__ import annotations
import json
from pathlib import Path

EVIDENCE = {
    "MET_HEALED_HORUS": True,
    "MET_HUMAN_FALCON_HYBRID": True,
    "MET_VERTICAL_AND_DIAGONAL_SPIRAL_FALCON_MARKS": True,
    "UCL_BD17_RIGHT_EYE_OF_RA_GLOSS": True,
    "BM_HORUS_RIGHT_EYE_SUN": True,
    "BM_HORUS_LEFT_EYE_MOON": True,
    "BM_RIGHT_WEDJAT_AMULETS_EXIST": True,
    "BM_LEFT_WEDJAT_AMULETS_EXIST": True,
    "BM_DOUBLE_SIDED_WEDJAT_EXISTS": True,
    "BM_NAUKRATIS_LEFT_USUALLY_RARE": True,
    "MET_WEDJAT_OFFERED_TO_KHEPRI_SUN": True,
}

HYPOTHESES = {
    "H_LEFT_HORUS_MOON_ONLY": {
        "description": "Wedjat is exclusively the left eye of Horus and exclusively lunar.",
        "contradicted_by": [
            "UCL_BD17_RIGHT_EYE_OF_RA_GLOSS",
            "BM_RIGHT_WEDJAT_AMULETS_EXIST",
            "BM_HORUS_RIGHT_EYE_SUN",
            "MET_WEDJAT_OFFERED_TO_KHEPRI_SUN",
        ],
    },
    "H_RIGHT_RA_SUN_ONLY": {
        "description": "Wedjat is exclusively the right eye of Ra and exclusively solar.",
        "contradicted_by": [
            "MET_HEALED_HORUS",
            "BM_LEFT_WEDJAT_AMULETS_EXIST",
            "BM_HORUS_LEFT_EYE_MOON",
        ],
    },
    "H_FIXED_SIDE_ONLY": {
        "description": "Wedjat has one invariant physical side/orientation in all amuletic use.",
        "contradicted_by": [
            "BM_RIGHT_WEDJAT_AMULETS_EXIST",
            "BM_LEFT_WEDJAT_AMULETS_EXIST",
            "BM_DOUBLE_SIDED_WEDJAT_EXISTS",
        ],
    },
    "H_RESTORED_EYE_CONTEXTUAL_IDENTITY": {
        "description": "Wedjat is best treated as a sound/restored-eye motif whose deity, side and solar/lunar associations can be context-dependent rather than mutually exclusive.",
        "requires": [
            "MET_HEALED_HORUS",
            "UCL_BD17_RIGHT_EYE_OF_RA_GLOSS",
            "BM_RIGHT_WEDJAT_AMULETS_EXIST",
            "BM_LEFT_WEDJAT_AMULETS_EXIST",
        ],
        "contradicted_by": [],
    },
    "H_HYBRID_ANATOMY": {
        "description": "The canonical Wedjat combines a human eye core with falcon-derived markings rather than being a simple human-eye icon.",
        "requires": [
            "MET_HUMAN_FALCON_HYBRID",
            "MET_VERTICAL_AND_DIAGONAL_SPIRAL_FALCON_MARKS",
        ],
        "contradicted_by": [],
    },
}

ORIENTATION_AUDIT = {
    "sample_status": "PURPOSIVE_SOURCE_AUDIT_NOT_RANDOM_NOT_PREVALENCE_ESTIMATE",
    "one_sided_right_records": [
        "BM_EA18456", "BM_EA18517", "BM_EA62580", "BM_EA27552",
        "BM_X5222", "BM_X2231", "BM_X846", "BM_X2314"
    ],
    "one_sided_left_records": ["BM_X6290", "BM_X902", "BM_X2229"],
    "double_sided_records": ["BM_X905", "BM_X5225"],
    "note": "The audit establishes existence of right, left, and double-sided forms. It must not be used to estimate population frequencies. Separate British Museum Naukratis catalogue comments state that left Wedjat eyes are usually rare in that corpus."
}

def evaluate() -> dict:
    results = {}
    for hid, spec in HYPOTHESES.items():
        contradictions = [k for k in spec.get("contradicted_by", []) if EVIDENCE.get(k, False)]
        missing = [k for k in spec.get("requires", []) if not EVIDENCE.get(k, False)]
        compatible = (not contradictions) and (not missing)
        results[hid] = {
            "description": spec["description"],
            "compatible_with_admitted_evidence": compatible,
            "contradictions": contradictions,
            "missing_required_observations": missing,
        }
    return {
        "status": "CONTEXTUAL_WEDJAT_IDENTITY_MODEL_SUPPORTED_EXCLUSIVE_SIDE_MODELS_REJECTED",
        "evidence": EVIDENCE,
        "hypothesis_audit": results,
        "orientation_audit": {
            **ORIENTATION_AUDIT,
            "right_record_count": len(ORIENTATION_AUDIT["one_sided_right_records"]),
            "left_record_count": len(ORIENTATION_AUDIT["one_sided_left_records"]),
            "double_sided_record_count": len(ORIENTATION_AUDIT["double_sided_records"]),
        },
        "highest_admissible_claim": (
            "Within this source-qualified audit, mutually exclusive simplifications such as "
            "'Wedjat = only left Horus/moon', 'Wedjat = only right Ra/sun', or one invariant "
            "physical side are incompatible with the admitted evidence. A contextual model is "
            "better supported: Wedjat is a sound/restored eye motif associated with Horus in "
            "amuletic descriptions, can be glossed as the right eye of Ra in Book of the Dead "
            "chapter 17, occurs in right, left and double-sided amulets, and participates in "
            "solar contexts such as offerings to Khepri. Its canonical morphology is explicitly "
            "human-falcon hybrid. This does not imply that all contexts are interchangeable or "
            "that deity/side associations lack historical structure."
        ),
    }

def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    args = ap.parse_args()
    result = evaluate()
    s = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(s + "\n", encoding="utf-8")
    print(s)

if __name__ == "__main__":
    main()
