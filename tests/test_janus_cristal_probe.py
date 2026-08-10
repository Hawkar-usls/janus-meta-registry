#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path

import numpy as np

P = Path(__file__).resolve().parents[1] / "tools" / "janus_cristal_probe.py"
spec = importlib.util.spec_from_file_location("jcp", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class JanusCristalProbeTests(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(m.classify_token("A1+B2=3"), "FORMULA_LIKE_OCR_TOKEN")
        self.assertEqual(m.classify_token("HELLO"), "WORD_LIKE_OCR_TOKEN")
        self.assertEqual(m.classify_token("IF(X)"), "CODE_LIKE_OCR_TOKEN")

    def test_shuffle_deterministic_and_shape(self):
        a = np.arange(10000, dtype=np.uint8).reshape(100, 100)
        b = m.block_shuffle(a, block=20, seed=1138)
        c = m.block_shuffle(a, block=20, seed=1138)
        self.assertEqual(a.shape, b.shape)
        self.assertTrue(np.array_equal(b, c))
        self.assertFalse(np.array_equal(a, b))

    def test_entropy(self):
        self.assertAlmostEqual(m.entropy_u8(np.zeros((32, 32), dtype=np.uint8)), 0.0, places=6)

    def test_fft_periodicity(self):
        x = np.tile(np.array([0, 255] * 128, dtype=np.uint8), (256, 1))
        r = m.fft_periodicity(x)
        self.assertGreater(r["peak_to_mean"], 1)

    def test_normalize_no_arbitrary_chars(self):
        self.assertEqual(m.normalize_text(" a b$c=1! "), "ABC=1")


if __name__ == "__main__":
    unittest.main()
