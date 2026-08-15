#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import zipfile
from pathlib import Path

BB_ZIP_SHA = "01282a0cde76723fd405bebdf143f88acb57d9f3a79b4bebc89d84cdff4b9270"
BB_CSV_SHA = "f3beb68121a11bab9cfe63699edbad69e027e472e1f137ad34b4373a1d16841c"
POSS_ZIP_SHA = "f6f3ccfab5bdb9cadaea4526dc2489eb5743d4dab69ff19f5440de9dd98ac0db"
POSS_CSV_SHA = "4ce9a68403bfc2407b874a7674522cec6da46e758ca59eda581da561bfa4c765"

MANIFEST = Path("data/JANUS-PALOMAR-JPFM-4A-BUMPER-FINAL-CAPE-PHASE-MANIFEST-v1.0.json")
RESULT = Path("data/JANUS-PALOMAR-JPFM-4A-BUMPER-FINAL-CAPE-CALIBRATION-RESULT-v1.0.json")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def zip_member_bytes(path: Path, basename: str) -> bytes:
    with zipfile.ZipFile(path) as archive:
        matches = [name for name in archive.namelist() if name.endswith(basename)]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one {basename} in {path}; found {matches}")
        return archive.read(matches[0])


def parse_csv(data: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


def pm1(date_string: str) -> set[str]:
    d = dt.date.fromisoformat(date_string)
    return {(d + dt.timedelta(days=lag)).isoformat() for lag in (-1, 0, 1)}


def flag(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bluebook-zip", type=Path, required=True)
    parser.add_argument("--poss-zip", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if sha256_file(args.bluebook_zip) != BB_ZIP_SHA:
        raise RuntimeError("Blue Book artifact ZIP hash mismatch")
    if sha256_file(args.poss_zip) != POSS_ZIP_SHA:
        raise RuntimeError("POSS artifact ZIP hash mismatch")

    bluebook_bytes = zip_member_bytes(args.bluebook_zip, "bluebook_case_index_blind.csv")
    poss_bytes = zip_member_bytes(args.poss_zip, "plate_day_open_strict.csv")
    if sha256_bytes(bluebook_bytes) != BB_CSV_SHA:
        raise RuntimeError("Blue Book blind CSV hash mismatch")
    if sha256_bytes(poss_bytes) != POSS_CSV_SHA:
        raise RuntimeError("POSS strict plate-day CSV hash mismatch")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    stored = json.loads(RESULT.read_text(encoding="utf-8"))
    if manifest["status"] != "FINITE_ROCKET_PROGRAM_PHASE_FROZEN_BEFORE_BLUEBOOK_OR_POSS_JOIN":
        raise RuntimeError("Bumper manifest status gate failed")
    if manifest["outcome_blindness"]["association_computed"] is not False:
        raise RuntimeError("Bumper pre-outcome blindness gate failed")

    bluebook = parse_csv(bluebook_bytes)
    poss = parse_csv(poss_bytes)
    bluebook_by_date: dict[str, list[dict[str, str]]] = {}
    for row in bluebook:
        bluebook_by_date.setdefault(row["occurrence_date"], []).append(row)
    poss_by_date: dict[str, list[dict[str, str]]] = {}
    for row in poss:
        poss_by_date.setdefault(row["obs_date_utc"], []).append(row)
    poss_dates = set(poss_by_date)

    recomputed = []
    for event in manifest["events"]:
        date_string = event["date"]
        window = pm1(date_string)
        exact_rows = bluebook_by_date.get(date_string, [])
        nearby_rows = [row for day in sorted(window) for row in bluebook_by_date.get(day, [])]
        observed_nights = [day for day in sorted(window) if day in poss_dates]
        same_or_post = [day for day in observed_nights if day >= date_string]
        recomputed.append({
            "date": date_string,
            "round": event["round"],
            "event_status": event["status"],
            "bluebook_exact_day": {
                "case_rows": len(exact_rows),
                "starlike_rows": sum(flag(row["starlike_screen"]) for row in exact_rows),
                "compact_light_rows": sum(flag(row["compact_light_screen"]) for row in exact_rows),
            },
            "bluebook_plus_minus_1": {
                "case_rows": len(nearby_rows),
                "starlike_rows": sum(flag(row["starlike_screen"]) for row in nearby_rows),
                "compact_light_rows": sum(flag(row["compact_light_screen"]) for row in nearby_rows),
                "rows": [{
                    "occurrence_date": row["occurrence_date"],
                    "nara_naid": row["nara_naid"],
                    "title": row["title"],
                    "source_url": row["source_url"],
                    "starlike_screen": int(flag(row["starlike_screen"])),
                    "compact_light_screen": int(flag(row["compact_light_screen"])),
                    "summary_sha256": row["summary_sha256"],
                } for row in nearby_rows],
            },
            "poss_exact_day_observed": date_string in poss_dates,
            "poss_plus_minus_1_observed_nights": observed_nights,
            "poss_plus_minus_1_same_or_post_nights": same_or_post,
            "poss_window_rows": [dict(row) for day in observed_nights for row in poss_by_date[day]],
        })

    by_date = {row["date"]: row for row in recomputed}
    stored_by_date = {row["date"]: row for row in stored["results"]}
    checks: list[bool] = []
    for date_string in ("1950-07-19", "1950-07-24", "1950-07-29"):
        replay = by_date[date_string]
        frozen = stored_by_date[date_string]
        checks.extend([
            replay["event_status"] == frozen["event_status"],
            replay["bluebook_exact_day"]["case_rows"] == frozen["bluebook_exact_day"]["case_rows"],
            replay["bluebook_exact_day"]["starlike_rows"] == frozen["bluebook_exact_day"]["starlike_rows"],
            replay["bluebook_exact_day"]["compact_light_rows"] == frozen["bluebook_exact_day"]["compact_light_rows"],
            replay["bluebook_plus_minus_1"]["case_rows"] == frozen["bluebook_plus_minus_1"]["case_rows"],
            replay["poss_exact_day_observed"] == frozen["poss_exact_day"]["palomar_observed"],
        ])
        expected_nights = frozen["poss_plus_minus_1"].get("palomar_observed_nights", [])
        if isinstance(expected_nights, int):
            expected_nights = [] if expected_nights == 0 else [str(expected_nights)]
        checks.append(replay["poss_plus_minus_1_observed_nights"] == expected_nights)

    checks.extend([
        [row["nara_naid"] for row in by_date["1950-07-19"]["bluebook_plus_minus_1"]["rows"]] == ["28938046"],
        [row["nara_naid"] for row in by_date["1950-07-24"]["bluebook_plus_minus_1"]["rows"]] == [],
        [row["nara_naid"] for row in by_date["1950-07-29"]["bluebook_plus_minus_1"]["rows"]] == ["28938070"],
        by_date["1950-07-19"]["poss_plus_minus_1_same_or_post_nights"] == [],
        by_date["1950-07-24"]["poss_plus_minus_1_same_or_post_nights"] == [],
        by_date["1950-07-29"]["poss_plus_minus_1_same_or_post_nights"] == [],
        stored["aggregate_calibration"]["direct_bumper_attributions_admitted"] == 0,
        stored["bindings"]["current_authority_changed"] is False,
    ])
    if not all(checks):
        failed = [index for index, passed in enumerate(checks) if not passed]
        raise RuntimeError(f"Stored Bumper result replay mismatch at checks {failed}")

    receipt = {
        "artifact_id": "JANUS-PALOMAR-JPFM-4A-BUMPER-REPLAY-VERIFICATION-v1.0",
        "experiment_id": "JPFM-4A",
        "date": dt.date.today().isoformat(),
        "status": "REPLAY_VERIFIED_AGAINST_PINNED_BLUEBOOK_AND_POSS_ARTIFACTS",
        "epistemic_role": "REPRODUCIBILITY_REPAIR_FOR_PREVIOUSLY_RECORDED_BUMPER_CALIBRATION_RESULT",
        "bindings": {
            "manifest_path": str(MANIFEST),
            "manifest_sha256": sha256_file(MANIFEST),
            "stored_result_path": str(RESULT),
            "stored_result_sha256": sha256_file(RESULT),
            "bluebook_workflow_run": 31869957662,
            "bluebook_artifact_id": 9243186827,
            "bluebook_artifact_zip_sha256": BB_ZIP_SHA,
            "bluebook_blind_csv_sha256": BB_CSV_SHA,
            "poss_workflow_run": 31868766687,
            "poss_artifact_id": 9242798656,
            "poss_artifact_zip_sha256": POSS_ZIP_SHA,
            "poss_plate_day_strict_csv_sha256": POSS_CSV_SHA,
        },
        "recomputed_evidence_slice": recomputed,
        "verification": {
            "semantic_checks_total": len(checks),
            "semantic_checks_passed": sum(checks),
            "stored_result_replay_pass": all(checks),
            "geography_boundary": "The verifier rebinds the exact NARA rows and temporal opportunity. Qualitative geography judgments remain explicit in the immutable stored result and are not silently replaced by date-only logic.",
        },
        "aggregate_replay": {
            "bluebook_exact_day_case_rows": sum(row["bluebook_exact_day"]["case_rows"] for row in recomputed),
            "bluebook_plus_minus_1_case_rows": sum(row["bluebook_plus_minus_1"]["case_rows"] for row in recomputed),
            "bluebook_plus_minus_1_starlike_rows": sum(row["bluebook_plus_minus_1"]["starlike_rows"] for row in recomputed),
            "poss_exact_day_observed_dates": sum(row["poss_exact_day_observed"] for row in recomputed),
            "poss_plus_minus_1_same_or_post_event_observed_nights": sum(len(row["poss_plus_minus_1_same_or_post_nights"]) for row in recomputed),
            "verdict": "STORED_BUMPER_CALIBRATION_RESULT_REPRODUCED_FROM_PINNED_INPUT_ARTIFACTS",
        },
        "current_authority_changed": False,
        "claim_ceiling": "REPLAY_VERIFICATION_ONLY__NO_NEW_ATTRIBUTION_OR_CAUSAL_CLAIM",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
