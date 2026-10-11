#!/usr/bin/env python3
"""Strict admission layer for JANUS CRISTAL raw detector output."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

SEMANTIC_CLASSES = {
    "WORD_LIKE_OCR_TOKEN",
    "FORMULA_LIKE_OCR_TOKEN",
    "CODE_LIKE_OCR_TOKEN",
}


def admit(raw: dict) -> dict:
    by_token = defaultdict(list)
    rejected = []
    for source in raw.get("sources", []):
        sem = source.get("semantic_analysis", {})
        control_tokens = {t.get("token") for t in sem.get("negative_control", {}).get("tokens", [])}
        for cand in sem.get("persistent_candidates", []):
            token = cand.get("token", "")
            reasons = []
            if len(token) < 3:
                reasons.append("TOKEN_SHORTER_THAN_3")
            if cand.get("class") not in SEMANTIC_CLASSES:
                reasons.append("NOT_WORD_FORMULA_OR_CODE_CLASS")
            if token in control_tokens:
                reasons.append("ALSO_PRESENT_IN_SHUFFLED_NEGATIVE_CONTROL")
            if reasons:
                rejected.append({"source": source.get("id"), "token": token, "reasons": reasons})
                continue
            by_token[token].append({
                "source": source.get("id"),
                "modality": source.get("modality"),
                "class": cand.get("class"),
                "direct_transform_hits": cand.get("direct_transform_hits"),
            })

    cross_modal = []
    single_source = []
    for token, hits in sorted(by_token.items()):
        modalities = sorted({h["modality"] for h in hits})
        if len(modalities) >= 2:
            cross_modal.append({
                "token": token,
                "hits": hits,
                "modalities": modalities,
                "status": "CROSS_MODALITY_SEMANTIC_CANDIDATE_REQUIRES_INDEPENDENT_REPLICATION",
            })
        else:
            single_source.append({
                "token": token,
                "hits": hits,
                "status": "REJECTED_SINGLE_SOURCE_ONLY",
            })

    admitted = []
    # v1.0 intentionally admits none as a message/formula/code. Cross-modality OCR
    # would only open the next gate; it does not itself establish encoded semantics.
    return {
        "schema": "janus.cristal.semantic_admission.v1",
        "artifact_name": "Janus Cristal",
        "raw_source_count": len(raw.get("sources", [])),
        "minimum_token_length": 3,
        "accepted_ocr_classes_for_escalation": sorted(SEMANTIC_CLASSES),
        "rejected_raw_persistent_candidates": rejected,
        "single_source_semantic_candidates": single_source,
        "cross_modality_semantic_candidates": cross_modal,
        "cross_modality_candidate_count": len(cross_modal),
        "admitted_messages_or_formulas_or_code": admitted,
        "admitted_count": 0,
        "status": "NO_SEMANTIC_CONTENT_ADMITTED",
        "next_gate_if_cross_modality_candidate_appears": "PREREGISTER_ENCODING_AND_REPLICATE_ON_INDEPENDENT_SPECIMEN_BEFORE_ANY_SEMANTIC_CLAIM",
        "formal_rules": [
            "OCR_PERSISTENCE_WITHIN_PREPROCESSING != CROSS_MODALITY_REPLICATION",
            "CROSS_MODALITY_OCR != MESSAGE",
            "NO_POST_HOC_CIPHER_SEARCH",
            "ANNOTATED_SOURCE_TEXT_IS_INADMISSIBLE",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    raw = json.loads(Path(args.raw).read_text(encoding="utf-8"))
    result = admit(raw)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "cross_modality_candidate_count": result["cross_modality_candidate_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
