#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "tools" / "janus_cristal_probe.py"
spec = importlib.util.spec_from_file_location("jcp", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

A = ROOT / "tools" / "janus_cristal_admission.py"
aspec = importlib.util.spec_from_file_location("jca", A)
a = importlib.util.module_from_spec(aspec)
aspec.loader.exec_module(a)


class JanusCristalProbeTests(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(m.classify_token("A1+B2=3"), "FORMULA_LIKE_OCR_TOKEN")
        self.assertEqual(m.classify_token("HELLO"), "WORD_LIKE_OCR_TOKEN")
        self.assertEqual(m.classify_token("IF(X)"), "CODE_LIKE_OCR_TOKEN")

    def test_shuffle_deterministic_and_shape(self):
        x = np.arange(10000, dtype=np.uint8).reshape(100, 100)
        b = m.block_shuffle(x, block=20, seed=1138)
        c = m.block_shuffle(x, block=20, seed=1138)
        self.assertEqual(x.shape, b.shape)
        self.assertTrue(np.array_equal(b, c))
        self.assertFalse(np.array_equal(x, b))

    def test_entropy(self):
        self.assertAlmostEqual(m.entropy_u8(np.zeros((32, 32), dtype=np.uint8)), 0.0, places=6)

    def test_fft_periodicity(self):
        x = np.tile(np.array([0, 255] * 128, dtype=np.uint8), (256, 1))
        r = m.fft_periodicity(x)
        self.assertGreater(r["peak_to_mean"], 1)

    def test_normalize_no_arbitrary_chars(self):
        self.assertEqual(m.normalize_text(" a b$c=1! "), "ABC=1")

    def test_admission_rejects_two_character_ocr(self):
        raw = {"sources": [{
            "id": "s1", "modality": "VISIBLE_RECORDED",
            "semantic_analysis": {
                "persistent_candidates": [{"token": "AE", "class": "SYMBOL_SEQUENCE_OCR_TOKEN", "direct_transform_hits": 3}],
                "negative_control": {"tokens": []}
            }
        }]}
        r = a.admit(raw)
        self.assertEqual(r["admitted_count"], 0)
        self.assertTrue(any("TOKEN_SHORTER_THAN_3" in x["reasons"] for x in r["rejected_raw_persistent_candidates"]))

    def test_cross_modality_ocr_only_opens_next_gate(self):
        raw = {"sources": []}
        for sid, mod in [("s1", "VISIBLE_RECORDED"), ("s2", "UV_405_NM_RECORDED")]:
            raw["sources"].append({
                "id": sid, "modality": mod,
                "semantic_analysis": {
                    "persistent_candidates": [{"token": "HELLO", "class": "WORD_LIKE_OCR_TOKEN", "direct_transform_hits": 2}],
                    "negative_control": {"tokens": []}
                }
            })
        r = a.admit(raw)
        self.assertEqual(r["cross_modality_candidate_count"], 1)
        self.assertEqual(r["admitted_count"], 0)
        self.assertEqual(r["status"], "NO_SEMANTIC_CONTENT_ADMITTED")


if __name__ == "__main__":
    unittest.main()
