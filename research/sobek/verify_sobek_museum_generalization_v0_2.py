#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "data" / "JANUS-SOBEK-MUSEUM-ICONOGRAPHY-GENERALIZATION-2026-08-16-v0.2.json"

REQUIRED_FIREWALL = {
    "CURATOR_DESCRIPTION_SCREEN_IS_NOT_BLIND_IMAGE_EVIDENCE",
    "RELATED_TO_SOBEK_DOES_NOT_EQUAL_VISUALLY_ELIGIBLE_SOBEK_DEPICTION",
    "CROCODILE_DOES_NOT_ALWAYS_MEAN_SOBEK",
    "CROCODILE_HEAD_ALONE_DOES_NOT_ALWAYS_IDENTIFY_SOBEK",
    "SUN_DISK_OR_CROWN_DOES_NOT_BY_ITSELF_IDENTIFY_SOBEK_OR_SOBEK_RE",
    "NO_SOBEK_WEDJAT_DIRECT_LINEAGE_CLAIM",
    "NO_FRACTION_BINARY_ASCII_PYTHON_HIDDEN_TEXT_OR_UAP_CLAIM",
}


def fail(msg: str) -> None:
    raise SystemExit(f"FAIL: {msg}")


def main() -> None:
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    pool = data.get("target_pool", [])
    controls = data.get("control_canaries", [])
    summary = data.get("corpus_summary", {})
    firewall = set(data.get("claim_firewall", []))

    if len(pool) < 30:
        fail(f"target pool below preregistered minimum: {len(pool)}")
    if summary.get("sobek_target_pool_records") != len(pool):
        fail("corpus_summary target count does not match target_pool length")

    ids = [x.get("id") for x in pool]
    if len(ids) != len(set(ids)):
        fail("duplicate target IDs")

    resolved_periods = {x.get("period_group") for x in pool if x.get("period_group") not in {None, "UNRESOLVED"}}
    if len(resolved_periods) < 3:
        fail(f"need >=3 resolved period groups, got {sorted(resolved_periods)}")

    screened = [x for x in pool if x.get("eligibility") == "DESCRIPTION_SCREENED"]
    if len(screened) < 20:
        fail("description-screened anchor set unexpectedly small")

    morph = {x.get("morphology") for x in screened}
    if "FULL_CROCODILE" not in morph and "FULL_CROCODILE_ON_SHRINE" not in morph:
        fail("missing full-crocodile anchor")
    if "CROCODILE_HEADED_ANTHROPOMORPH" not in morph:
        fail("missing crocodile-headed anthropomorph anchor")
    if "FALCON_HEADED_CROCODILE" not in morph:
        fail("missing hybrid falcon-headed crocodile branch")

    modules = {m for x in screened for m in x.get("context_modules", [])}
    for required in ("SUN_DISK", "URAEI"):
        if required not in modules:
            fail(f"missing contextual module anchor: {required}")

    control_types = {x.get("type") for x in controls}
    if "NON_SOBEK_CROCODILE_CONTROL" not in control_types:
        fail("missing non-Sobek crocodile control canary")
    if "CROCODILE_HEADED_CANARY" not in control_types:
        fail("missing crocodile-headed identity canary")

    missing = REQUIRED_FIREWALL - firewall
    if missing:
        fail(f"missing claim-firewall entries: {sorted(missing)}")

    if data.get("blind_image_protocol", {}).get("status") != "PREREGISTERED_NOT_EXECUTED":
        fail("blind image protocol must remain explicitly not executed at v0.2")
    if summary.get("blind_image_feature_gate") != "OPEN_NOT_EXECUTED":
        fail("blind image feature gate must remain open")
    if data.get("comparison_to_wedjat", {}).get("no_lineage_claim") is not True:
        fail("Sobek-Wedjat no-lineage lock missing")

    claim = data.get("highest_admissible_claim", "").lower()
    if "not yet a blind or independent visual replication" not in claim:
        fail("highest admissible claim does not preserve independence ceiling")

    print("PASS: Sobek v0.2 source-description generalization artifact is internally consistent")
    print(f"target_pool={len(pool)} description_screened={len(screened)} controls_staged={len(controls)}")
    print(f"resolved_period_groups={sorted(resolved_periods)}")
    print("blind_image_feature_gate=OPEN_NOT_EXECUTED")


if __name__ == "__main__":
    main()
