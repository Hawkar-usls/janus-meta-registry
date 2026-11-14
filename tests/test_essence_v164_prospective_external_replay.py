"""ESSENCE v1.6.4 prospective source and no-production-power controls."""
import unittest
from pathlib import Path
import torch
from tools import essence_v164_prospective_external_replay as s

class ProspectiveExternalValidation(unittest.TestCase):
    def test_locked_frozen_spec_sha_and_no_prod_authority(self):
        x=s.freeze()
        self.assertFalse(x["production_authority"])
        self.assertFalse(x["external_independent_custodian"])
        self.assertEqual(x["selected_candidate_mask"],7)
        self.assertEqual(x["selected_layers"],list(s.SELECTED))

    def test_external_sources_are_exactly_versioned(self):
        x=s.freeze()
        self.assertEqual(len(x["sources"]),2)
        for src in x["sources"]:
            self.assertEqual(len(src["commit"]),40)
            self.assertEqual(len(src["git_blob_sha1"]),40)
            self.assertIn(src["repository"],("python/cpython","pytorch/pytorch"))

    def test_reject_foreign_repo_without_network(self):
        with self.assertRaisesRegex(ValueError,"EXTERNAL_SOURCE_NOT_WHITELISTED"):
            s.fetch_external({"repository":"malicious/server",
                              "commit":"0"*40,"file":"README.md"})

    def test_model_checkout_proves_real_original_checkpoint(self):
        repo=Path("runtime/essence_v164/demiurge")
        weights=s.verify_model(repo)
        self.assertEqual(s.sha(weights),s.CHECKPOINT_SHA)

    def test_actual_quantized_three_ffn_layers_and_fp32_head(self):
        repo=Path("runtime/essence_v164/demiurge")
        import sys
        sys.path.insert(0,str(repo))
        from janus_model.train_registry import load_checkpoint
        weights=s.verify_model(repo)
        model,obj=load_checkpoint(weights,expected_sha256=s.CHECKPOINT_SHA)
        model.eval()
        q,count=s.clone_native_mask7(model)
        self.assertEqual(count,3)
        self.assertIsInstance(q.lm_head,torch.nn.Linear)
        self.assertEqual(q.lm_head.weight.data_ptr(),q.token.weight.data_ptr())
        self.assertEqual(s.sha(weights),s.CHECKPOINT_SHA)

if __name__=="__main__":unittest.main()
