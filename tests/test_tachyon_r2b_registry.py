"""R2B provenance and claim-boundary regression tests, no human observations."""
import copy
import json
import unittest

from tools.validate_tachyon_r2b import EVIDENCE, canonical_digest, validate


def source_fixture():
    """Minimal source-shaped receipt; independent of any sibling checkout."""
    counts = [(6-high)**2 * (2*(low+1)*(6-high) + (low+1)**2)
              for low in range(5) for high in range(low+1, 6)]
    return {
        "r1_reproduction": {
            "grid_vectors": 1296, "directed_neighbor_comparisons": 8640,
            "directed_label_flips": 704, "unstable_vectors": 532,
            "dissociation_candidate_vectors": 48, "noncandidate_vectors": 1248,
            "indeterminate_vectors": 1232, "no_demo_dissociation_vectors": 16,
            "flip_fraction": 704/8640,
        },
        "baseline_comparison": {
            "constant": {"flip_fraction": 0.0},
            "one_feature_threshold": {"flip_fraction": 0.05},
            "uniform_seven_class_iid": {
                "seeds": list(range(8)), "samples": [{} for _ in range(8)],
                "mean_flip_fraction": 0.8569444444444444,
            },
            "r1_histogram_preserving_random_permutation": {
                "seeds": list(range(8)), "samples": [{} for _ in range(8)],
                "mean_flip_fraction": 0.4987847222222222,
            },
        },
        "threshold_sensitivity": {
            "rows": [{"candidate_vectors": n} for n in counts],
            "candidate_count_range": [3, 320],
        },
        "constructive_nonidentifiability": {
            "type": "CONSTRUCTIVE_MANY_TO_ONE_FORWARD_MODEL",
            "all_witnesses_same_forward_distribution": True,
            "distinct_observable_vectors_used_as_nonidentifiability_proof": False,
            "flip_statistics_used_as_nonidentifiability_proof": False,
            "witnesses": [{"latent_states_distinct": True, "same_forward_probabilities": True}
                          for _ in range(6)],
        },
        "power_analysis": {"illustrative_selected_design": {
            "assumed_dz": 0.3, "target_marginal_power": 0.9,
            "two_sided_alpha_per_endpoint": 0.025, "evaluable_holdout_pairs": 141,
            "total_evaluable_participants": 353, "recruitment_target_expected_retention": 442,
            "holdout_fraction": 0.4, "assumed_attrition_fraction": 0.2,
        }},
    }


class R2BRegistryTests(unittest.TestCase):
    def setUp(self):
        self.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_complete_provenance_and_boundaries(self):
        self.assertEqual(validate(self.evidence)["engineering"],
                         "LOCAL_BOUNDARY_AND_PROVENANCE_CHECKS_PASS")

    def test_pending_or_moving_source_ref_rejected(self):
        for ref in ("PENDING_SOURCE_PIN", "main", "a" * 39):
            evidence = copy.deepcopy(self.evidence)
            evidence["source"]["commit"] = ref
            with self.assertRaises(AssertionError):
                validate(evidence)

    def test_reviewer_arithmetic_error_rejected(self):
        self.evidence["corrections_to_external_review"]["noncandidate_vectors"] = 1232
        with self.assertRaises(AssertionError):
            validate(self.evidence, require_source_pin=False)

    def test_canonical_rule_rewrite_rejected(self):
        self.evidence["rule_001"]["content_sha256_lf_utf8"] = "0" * 64
        with self.assertRaises(AssertionError):
            validate(self.evidence, require_source_pin=False)

    def test_software_test_count_cannot_be_hypothesis_count(self):
        self.evidence["corrections_to_external_review"]["legacy_statistical_hypotheses"] = 36
        with self.assertRaises(AssertionError):
            validate(self.evidence, require_source_pin=False)

    def test_clinical_prevalence_and_authority_promotion_rejected(self):
        for section, key in (("corrections_to_external_review", "synthetic_grid_candidate_fraction_is_clinical_prevalence"),
                             ("privacy_and_runtime", "production_model_weights_changed"),
                             ("privacy_and_runtime", "patient_data_ingested")):
            evidence = copy.deepcopy(self.evidence)
            evidence[section][key] = True
            with self.assertRaises(AssertionError):
                validate(evidence, require_source_pin=False)

    def test_second_author_email_rejected(self):
        self.evidence["author_contact"]["second_email_sent_by_r2b"] = True
        with self.assertRaises(AssertionError):
            validate(self.evidence, require_source_pin=False)

    def test_regenerated_result_digest_verified(self):
        receipt = source_fixture()
        self.evidence["source"]["results_canonical_sha256"] = canonical_digest(receipt)
        self.assertTrue(validate(self.evidence, require_source_pin=False,
                                 source_receipt=receipt)["source_receipt_reproduced"])
        with self.assertRaises(AssertionError):
            validate(self.evidence, require_source_pin=False,
                     source_receipt={**receipt, "synthetic_only": False})

    def test_published_summary_cannot_drift_from_valid_source_digest(self):
        receipt = source_fixture()
        self.evidence["source"]["results_canonical_sha256"] = canonical_digest(receipt)
        for key, changed in (("constant_flip_fraction", 0.1),
                             ("uniform_seven_class_mean_flip_fraction_eight_seeds", 0.99),
                             ("threshold_pairs_reported", 14),
                             ("threshold_candidate_count_range", [3, 321]),
                             ("constructive_witnesses", 5)):
            evidence = copy.deepcopy(self.evidence)
            evidence["methods_results"][key] = changed
            with self.subTest(key=key), self.assertRaises(AssertionError):
                validate(evidence, source_receipt=receipt)
        self.evidence["methods_results"]["power_illustration"]["minimum_evaluable_holdout_participants"] = 50
        with self.assertRaises(AssertionError):
            validate(self.evidence, source_receipt=receipt)

    def test_updated_digest_cannot_hide_inconsistent_r1_or_methods_numbers(self):
        for section, key, changed in (
            ("r1_reproduction", "directed_label_flips", 700),
            ("r1_reproduction", "noncandidate_vectors", 1232),
            ("threshold_sensitivity", "candidate_count_range", [3, 319]),
            ("constructive_nonidentifiability", "all_witnesses_same_forward_distribution", False),
        ):
            receipt = source_fixture()
            receipt[section][key] = changed
            evidence = copy.deepcopy(self.evidence)
            evidence["source"]["results_canonical_sha256"] = canonical_digest(receipt)
            with self.subTest(section=section, key=key), self.assertRaises(AssertionError):
                validate(evidence, source_receipt=receipt)
        receipt = source_fixture()
        receipt["power_analysis"]["illustrative_selected_design"]["recruitment_target_expected_retention"] = 100
        self.evidence["source"]["results_canonical_sha256"] = canonical_digest(receipt)
        with self.assertRaises(AssertionError):
            validate(self.evidence, source_receipt=receipt)


if __name__ == "__main__":
    unittest.main()
