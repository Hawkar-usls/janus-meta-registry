#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).with_name('wedjat_component_state_space_probe_v0_2.py')
spec = importlib.util.spec_from_file_location('wedjat_v02', MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


class WedjatStateSpaceV02Tests(unittest.TestCase):
    def test_exact_64_state_bijection(self):
        states = mod.build_state_space()
        self.assertEqual(len(states), 64)
        self.assertEqual(len({row['fraction_sum'] for row in states}), 64)
        self.assertTrue(all(row['mask_decimal'] == row['scaled_by_64'] for row in states))
        self.assertTrue(all(row['python_exec_matches_mask'] for row in states))

    def test_label_permutation_is_numeric_null(self):
        ctl = mod.label_permutation_control()
        self.assertEqual(ctl['permutations_checked'], 720)
        self.assertTrue(ctl['all_numeric_state_spaces_equal_baseline'])

    def test_leave_one_out_reduces_to_32_states(self):
        rows = mod.leave_one_out_controls()
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row['unique_subset_sums'] == 32 for row in rows))
        self.assertTrue(all(not row['complete_six_bit_grid_0_to_63_over_64'] for row in rows))

    def test_duplicate_weight_creates_collisions(self):
        ctl = mod.duplicate_weight_controls()
        self.assertEqual(ctl['case_count'], 30)
        self.assertTrue(ctl['all_cases_have_collisions'])

    def test_raw_ascii_does_not_decode_full_mask_as_python(self):
        ctl = mod.raw_ascii_python_control()
        self.assertEqual(ctl['full_mask_63_character'], '?')
        self.assertFalse(ctl['full_mask_63_valid_exec_source'])
        self.assertFalse(ctl['full_mask_63_valid_eval_source'])
        self.assertEqual(ctl['eval_valid_decimal_codes'], list(range(48, 58)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
