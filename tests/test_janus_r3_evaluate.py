"""JANUS-R3 continuous metadata quality gates are NOT scientific fact checks."""
import copy
import json
from pathlib import Path
import unittest

from tools.janus_r3_evaluate import evaluate,validate_quality,fingerprinted_sources
from tools.janus_public_source_intake import IntakeError
from test_public_source_intake import fixture
from tools.janus_public_source_intake import collect,canonical,digest


class R3Quality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=collect(fetch=fixture(),at="2026-11-11T15:00:00+00:00")

    def _resign(self,record):
        record["source_digest_sha256"]=digest(canonical(record["sources"]))
        record["record_id"]="JANUS-PUBLIC-SOURCES-"+record["source_digest_sha256"][:20]
        record["receipt_sha256"]=digest(canonical({
            k:v for k,v in record.items() if k!="receipt_sha256"
        }))
        return record

    def test_valid_public_metadata_is_review_only(self):
        r=evaluate(self.base)
        validate_quality(r,self.base)
        self.assertEqual(r["metadata_sources_with_integrity"],5)
        self.assertGreater(r["new_metadata_id_count"],0)
        self.assertEqual(r["review_decision"],"NEW_METADATA_REQUIRES_CURATOR_REVIEW")
        self.assertFalse(r["model_training_authorized"])
        self.assertFalse(r["scientific_knowledge_promoted"])
        self.assertFalse(r["article_claims_independently_verified"])

    def test_ocean_run_provenance_only_not_independent_science(self):
        report=evaluate(self.base)
        ocean=report["source_statuses"]["ocean_action"]
        self.assertTrue(ocean["integrity_passed"])
        self.assertEqual(ocean["records"],1)
        self.assertFalse(report["model_training_authorized"])
        self.assertFalse(report["neural_model_improved"])

    def test_ocean_action_repo_spoof_is_rejected_after_resigning(self):
        fake=copy.deepcopy(self.base)
        fake["sources"]["ocean_action"]["repository"]="Hawkar-usls/evil"
        self._resign(fake)
        with self.assertRaisesRegex(IntakeError,"R3_ACTION_REPOSITORY_SPOOF"):
            evaluate(fake)

    def test_legacy_four_provider_history_remains_valid(self):
        legacy=copy.deepcopy(self.base)
        legacy["sources"].pop("ocean_action")
        self._resign(legacy)
        old_report=evaluate(legacy)
        self.assertEqual(old_report["metadata_sources_with_integrity"],4)
        new_report=evaluate(self.base,[legacy])
        self.assertEqual(new_report["new_metadata_id_count"],1)
        self.assertFalse(new_report["model_training_dispatched"])

    def test_repeat_metadata_never_triggers_training(self):
        one=copy.deepcopy(self.base)
        two=copy.deepcopy(self.base)
        two["observed_at_utc"]="2026-11-12T15:00:00+00:00"
        self._resign(two)
        result=evaluate(two,[one])
        self.assertEqual(result["new_metadata_id_count"],0)
        self.assertEqual(result["review_decision"],"NO_NEW_METADATA")
        self.assertFalse(result["model_training_dispatched"])

    def test_new_doi_means_review_not_model_update(self):
        prior=copy.deepcopy(self.base)
        latest=copy.deepcopy(self.base)
        latest["sources"]["openalex"]["papers"][0]["doi_url"] = "https://doi.org/10.5555/new-public-paper"
        self._resign(latest)
        r=evaluate(latest,[prior])
        self.assertEqual(r["new_metadata_id_count"],1)
        self.assertFalse(r["model_training_authorized"])

    def test_unsupported_source_status_fails_closed(self):
        bad=copy.deepcopy(self.base)
        bad["sources"]["openalex"]["status"]="INDEPENDENT_PROOF_OF_RETROCAUSALITY"
        self._resign(bad)
        with self.assertRaisesRegex(IntakeError,"R3_INVALID_SOURCE_STATUS"):
            fingerprinted_sources(bad)

    def test_fake_doi_fails_even_with_recomputed_receipt_sha(self):
        bad=copy.deepcopy(self.base)
        bad["sources"]["openalex"]["papers"][0]["doi_url"]="http://localhost/claim"
        self._resign(bad)
        with self.assertRaisesRegex(IntakeError,"R3_INVALID_DOI_METADATA"):
            evaluate(bad)

    def test_wikipedia_wrong_domain_fails(self):
        bad=copy.deepcopy(self.base)
        bad["sources"]["wikipedia"]["article_metadata"][0]["article_url"] = "https://evil.example/wiki/not-source"
        self._resign(bad)
        with self.assertRaisesRegex(IntakeError,"R3_WIKI_CARD_URL"):
            evaluate(bad)

    def test_tampered_quality_flags_rejected(self):
        r=evaluate(self.base)
        r["model_training_authorized"]=True
        with self.assertRaisesRegex(IntakeError,"R3_UNAUTHORIZED_PROMOTION"):
            validate_quality(r,self.base)

    def test_metadata_mutation_does_not_elevate_science(self):
        bad=copy.deepcopy(self.base)
        bad["sources"]["gdelt_gkg"]["article_claims_independently_verified"]=True
        self._resign(bad)
        with self.assertRaisesRegex(IntakeError,"R3_GDELT_CANNOT_CLAIM_FACT_VERIFIED"):
            evaluate(bad)

    def test_provider_429_not_reported_as_false_fact(self):
        x=copy.deepcopy(self.base)
        x["sources"]["gdelt_gkg"]={"status":"PROVIDER_UNAVAILABLE",
                                  "reason":"UPSTREAM_HTTP_429"}
        self._resign(x)
        r=evaluate(x)
        self.assertEqual(r["unavailable_provider_count"],1)
        self.assertFalse(r["news_claims_fact_checked"])
        self.assertFalse(r["model_training_dispatched"])

if __name__=="__main__":
    unittest.main()
