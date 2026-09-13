import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import kym_blind_media_extractor as m  # noqa: E402


class BlindExtractorTests(unittest.TestCase):
    def test_html_parser_retains_only_media_attribute(self):
        secret = "WORK DEPRESSION HALLOWEEN SECRET CONTEXT"
        html = f'''<html><head>
        <title>{secret}</title>
        <meta name="description" content="{secret}">
        <meta property="og:image" content="https://i.kym-cdn.com/photos/images/original/000/000/001/test.gif">
        </head><body><h1>{secret}</h1><img src="https://evil.example/ad.jpg"></body></html>'''
        p = m._MediaMetaParser()
        p.feed(html)
        self.assertEqual(
            p.candidates,
            ["https://i.kym-cdn.com/photos/images/original/000/000/001/test.gif"],
        )
        self.assertNotIn(secret, json.dumps(p.candidates))

    def test_build_prepared_state_verifies_rank_and_first50(self):
        ids = [31, 7, 19, 2, 41]
        raw = ",".join(map(str, ids)).encode("ascii")
        payload = base64.b64encode(zlib.compress(raw)).decode("ascii")
        seed = "fixture-seed"
        rows = m._rank_rows(ids, seed)
        ranked_raw = ",".join(str(r["photo_id"]) for r in rows).encode("ascii")
        manifest = {
            "source": {"total_items_observed": len(ids), "unique_items_observed": len(ids)},
            "ordered_id_payload": {
                "encoding": "zlib+base64",
                "raw_decoded_length_bytes": len(raw),
                "decoded_sha256": hashlib.sha256(raw).hexdigest(),
                "payload": payload,
            },
        }
        prereg = {
            "sampling_manifest": {
                "item_count": len(ids),
                "unique_item_count": len(ids),
                "ordered_ids_sha256": hashlib.sha256(raw).hexdigest(),
            },
            "deterministic_randomization": {
                "seed": seed,
                "seed_sha256": hashlib.sha256(seed.encode()).hexdigest(),
                "rank_rule": m.EXPECTED_RANK_RULE,
                "full_ranked_order_sha256": hashlib.sha256(ranked_raw).hexdigest(),
                "first_50_ids_for_audit": [r["photo_id"] for r in rows],
            },
            "eligibility_screen": {"target_n": 20, "minimum_n": 15},
        }
        state = m.build_prepared_state(manifest, prereg)
        self.assertEqual(state["status"], "PREPARED__SCREENING_NOT_STARTED")
        self.assertEqual(state["cursor"], 0)
        self.assertEqual(state["pass_count"], 0)
        self.assertEqual(state["frame"]["ranked_order_serialization"], "comma_separated_decimal_ids")

    def test_public_receipt_has_no_url_or_semantic_text_fields(self):
        entry = {
            "photo_id": 1,
            "rank_position": 1,
            "rank_digest": "a" * 64,
            "retrieval_status": "OK",
            "media_url_sha256": "b" * 64,
            "media_sha256": "c" * 64,
            "media_mime": "image/gif",
            "media_bytes": 12,
            "neutral_file": "screen-0001.gif",
            "title": "forbidden",
            "caption": "forbidden",
            "tags": ["forbidden"],
            "media_url": "https://forbidden.example/name.gif",
        }
        out = m._public_receipt(entry)
        rendered = json.dumps(out)
        self.assertNotIn("forbidden", rendered)
        self.assertNotIn('"media_url"', rendered)
        self.assertIn("media_url_sha256", out)

    def test_record_stops_exactly_at_twenty(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            state_path = td / "state.json"
            screen_dir = td / "screen"
            screen_dir.mkdir()
            state = {
                "schema": m.STATE_SCHEMA,
                "status": "SCREENING_ACTIVE",
                "frame": {},
                "ranked": [],
                "cursor": 19,
                "ledger": [
                    {"photo_id": i, "eligibility": "PASS", "visual_reason_code": "DIRECT_SOURCE_IDENTIFIABLE"}
                    for i in range(1, 20)
                ],
                "pass_count": 19,
                "seen_media_sha256": {},
                "epistemic_firewall": {"context_coding": "LOCKED", "cri": "FORBIDDEN"},
                "active": {
                    "photo_id": 20,
                    "rank_position": 20,
                    "rank_digest": "d" * 64,
                    "retrieval_status": "OK",
                    "media_sha256": "e" * 64,
                    "media_url_sha256": "f" * 64,
                    "media_mime": "image/gif",
                    "media_bytes": 10,
                    "neutral_file": "screen-0020.gif",
                },
            }
            (screen_dir / "screen-0020.gif").write_bytes(b"GIF89a0000")
            m._atomic_write_json(state_path, state)
            out = m.record_decision(
                state_path,
                screen_dir,
                "PASS",
                "DIRECT_SOURCE_IDENTIFIABLE",
            )
            self.assertEqual(out["pass_count"], 20)
            self.assertEqual(out["status"], "SAMPLE_FROZEN__STOP_AT_20")
            saved = json.loads(state_path.read_text())
            self.assertEqual(saved["cursor"], 20)
            self.assertIsNone(saved["active"])
            self.assertFalse((screen_dir / "screen-0020.gif").exists())

    def test_freeze_requires_twenty_and_keeps_context_locked(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            state_path = td / "state.json"
            out_path = td / "freeze.json"
            ledger = [
                {
                    "photo_id": 100 + i,
                    "rank_position": i + 1,
                    "rank_digest": f"{i:064x}",
                    "retrieval_status": "OK",
                    "media_sha256": f"{i+1:064x}",
                    "media_url_sha256": f"{i+2:064x}",
                    "media_mime": "image/gif",
                    "media_bytes": 20,
                    "eligibility": "PASS",
                    "visual_reason_code": "DIRECT_SOURCE_IDENTIFIABLE",
                }
                for i in range(20)
            ]
            state = {
                "schema": m.STATE_SCHEMA,
                "status": "SAMPLE_FROZEN__STOP_AT_20",
                "frame": {"item_count": 832},
                "ledger": ledger,
                "pass_count": 20,
                "epistemic_firewall": {"context_coding": "LOCKED", "cri": "FORBIDDEN"},
            }
            m._atomic_write_json(state_path, state)
            out = m.freeze_sample(state_path, out_path)
            self.assertEqual(out["sample_n"], 20)
            frozen = json.loads(out_path.read_text())
            self.assertEqual(len(frozen["sample_ids_rank_order"]), 20)
            self.assertIn("remain locked", " ".join(frozen["epistemic_firewall"]))
            saved = json.loads(state_path.read_text())
            self.assertEqual(saved["status"], "SAMPLE_FREEZE_ARTIFACT_WRITTEN__AWAIT_EXTERNAL_SEAL")


if __name__ == "__main__":
    unittest.main()
