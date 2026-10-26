"""Synthetic adversarial tests for the single, frozen external 1EY0 WT audit."""
from __future__ import annotations
import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest import mock
import numpy as np

p=Path(__file__).with_name("fireprot_1ey0_wt_sequence_only_audit.py")
spec=importlib.util.spec_from_file_location("fireprot_1ey0_wt_sequence_only_audit",p)
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

def fixture(dir):
    base=Path(dir)
    y=base/(a.CASE+".yaml")
    y.write_bytes(a.source_yaml())
    root=base/"outputs"
    run=root/("boltz_results_"+a.CASE)
    preds=run/"predictions"/a.CASE
    preds.mkdir(parents=True)
    confidence=preds/("confidence_"+a.CASE+"_model_0.json")
    confidence.write_text(json.dumps({"ptm":.91,"complex_plddt":.95}),encoding="utf8")
    npz=preds/("plddt_"+a.CASE+"_model_0.npz")
    np.savez(npz,plddt=np.repeat(.95,136))
    msa=run/"msa"/"external_alignment"
    msa.mkdir(parents=True)
    for f in ("uniref.a3m","bfd.mgnify30.metaeuk30.smag30.a3m"):
        (msa/f).write_text(">query\nKLHKEPATLIKA\n",encoding="utf8")
    checkpoint=base/"frozen.ckpt"
    with checkpoint.open("wb") as f:
        f.seek(100000000)
        f.write(b"\0")
    return y,root,checkpoint,preds,msa

class ExternalWTSourceAuditTests(unittest.TestCase):
    def test_exact_136_aa_source_hash(self):
        self.assertEqual(len(a.FROZEN_WT),136)
        self.assertEqual(a.sha(a.FROZEN_WT.encode()),a.FROZEN_SEQ_SHA)
        self.assertEqual(a.sha(a.source_yaml()),a.FROZEN_YAML_SHA)
    def test_single_success_proves_only_technical_source(self):
        with tempfile.TemporaryDirectory() as d:
            y,r,c,_,_=fixture(d)
            out=a.audit(y,r,c)
            self.assertEqual(out["real_local_confidence"]["per_residue_plddt_count"],136)
            self.assertEqual(out["technical_status"],"PASS_REAL_EXTERNAL_1EY0_WT_GPU_LOCAL_BOLTZ2_WITH_MSA")
            self.assertFalse(out["identity"]["frozen_fireprot_pdb_member_bytes_matched"])
            self.assertFalse(out["resource_and_science_gates"]["transferred_shadow_model_validated"])
            self.assertEqual(out["resource_and_science_gates"]["external_mutant_jobs"],0)
    def test_mutated_yaml_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            y,r,c,_,_=fixture(d)
            y.write_bytes(a.source_yaml()+b"msa: empty\n")
            with self.assertRaisesRegex(a.Hold,"REAL_INPUT_YAML_NOT_FROZEN"):
                a.audit(y,r,c)
    def test_missing_real_confidence_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            y,r,c,p,_=fixture(d)
            (p/("confidence_"+a.CASE+"_model_0.json")).unlink()
            with self.assertRaisesRegex(a.Hold,"REAL_CONFIDENCE_JSON_COUNT_NOT_ONE"):
                a.audit(y,r,c)
    def test_wrong_confidence_score_range_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            y,r,c,p,_=fixture(d)
            (p/("confidence_"+a.CASE+"_model_0.json")).write_text('{"ptm":1.2,"complex_plddt":0.95}')
            with self.assertRaisesRegex(a.Hold,"REAL_CONFIDENCE_SCORE_INVALID_ptm"):
                a.audit(y,r,c)
    def test_135_residue_plddt_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            y,r,c,p,_=fixture(d)
            np.savez(p/("plddt_"+a.CASE+"_model_0.npz"),plddt=np.repeat(.95,135))
            with self.assertRaisesRegex(a.Hold,"PLDDT_RESIDUE_COUNT_OR_FINITE_INVALID"):
                a.audit(y,r,c)
    def test_wrong_mean_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            y,r,c,p,_=fixture(d)
            np.savez(p/("plddt_"+a.CASE+"_model_0.npz"),plddt=np.repeat(.9,136))
            with self.assertRaisesRegex(a.Hold,"PER_RESIDUE_MEAN_NOT_COMPLEX_PLDDT"):
                a.audit(y,r,c)
    def test_missing_alignment_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            y,r,c,_,msa=fixture(d)
            (msa/"uniref.a3m").unlink()
            with self.assertRaisesRegex(a.Hold,"REAL_MSA_TWO_FILES_REQUIRED"):
                a.audit(y,r,c)
    def test_missing_checkpoint_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            y,r,c,_,_=fixture(d)
            c.unlink()
            with self.assertRaisesRegex(a.Hold,"LOCAL_OFFICIAL_CHECKPOINT_NOT_PRESENT"):
                a.audit(y,r,c)
if __name__=="__main__":unittest.main()
