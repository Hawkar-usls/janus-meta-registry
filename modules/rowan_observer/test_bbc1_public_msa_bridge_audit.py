"""Synthetic fail-closed checks for pinned BBC1 MSA run verifier."""
import importlib.util,io,json,tempfile,hashlib,unittest
from pathlib import Path
from unittest import mock
import numpy as np

src=Path(__file__).with_name("bbc1_public_msa_bridge_audit.py")
spec=importlib.util.spec_from_file_location("rowan_bbc1_public_msa_bridge_audit",src)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def writefixture(base):
    base=Path(base)
    inp=base/"inputs";out=base/"outputs"
    inp.mkdir();out.mkdir()
    cases={}
    for mutant in ("BBC1_WT_MSA","BBC1_G53A_MSA","BBC1_G48D_MSA"):
        b=f"sequences:\n  - protein:\n      id: A\n      sequence: ABCDEFGH\n".encode()
        (inp/(mutant+".yaml")).write_bytes(b)
        root=out/("boltz_results_"+mutant)
        target=root/"predictions"/mutant;target.mkdir(parents=True)
        scores={"ptm":0.92,"complex_plddt":0.95}
        confidence=target/("confidence_"+mutant+"_model_0.json")
        confidence.write_text(json.dumps(scores),encoding="utf8")
        plddt=target/("plddt_"+mutant+"_model_0.npz")
        np.savez(plddt,plddt=np.repeat(np.float64(.95),64))
        msa=root/"msa";msa.mkdir()
        names=("bfd.mgnify30.metaeuk30.smag30.a3m","uniref.a3m")
        files={}
        for name in names:
            q=msa/name;q.write_text(">query\nAAAA\n")
            files[name]=m.sha_bytes(q.read_bytes())
        cases[mutant]={
            "yaml_sha256":m.sha_bytes(b),
            "confidence_sha256":m.sha_bytes(confidence.read_bytes()),
            "plddt_npz_sha256":m.sha_bytes(plddt.read_bytes()),
            "msa_sha256":files,
            "rowan_ptm":.927,"rowan_avg_lddt":.963,
            "without_msa_ptm":.90,"without_msa_plddt":.91}
    return inp,out,cases

class ActualOutputsMandatory(unittest.TestCase):
    def test_valid_fixture_reports_hold_on_service_equivalence(self):
        with tempfile.TemporaryDirectory() as d:
            a,b,c=writefixture(d)
            with mock.patch.object(m,"CASES",c):
                got=m.audit(a,b)
            self.assertTrue(got["state"].startswith("PASS_LOCAL_BBC1_THREE_MSA"))
            self.assertFalse(got["scientific_guard"]["source_MSAs_bytewise_matched_to_private_rowan"])
            self.assertEqual(got["scientific_guard"]["FireProt_210_compute_gate"],"HOLD_DO_NOT_RUN")
    def test_missing_confidence_file_holds(self):
        with tempfile.TemporaryDirectory() as d:
            a,b,c=writefixture(d)
            next(b.rglob("confidence_BBC1_WT_MSA_model_0.json")).unlink()
            with mock.patch.object(m,"CASES",c):
                with self.assertRaisesRegex(m.AuditHold,"CONFIDENCE_NOT_EXACTLY_ONE"):
                    m.audit(a,b)
    def test_tampered_output_holds(self):
        with tempfile.TemporaryDirectory() as d:
            a,b,c=writefixture(d)
            p=next(b.rglob("confidence_BBC1_G53A_MSA_model_0.json"))
            p.write_text('{"ptm":0.999,"complex_plddt":0.95}')
            with mock.patch.object(m,"CASES",c):
                with self.assertRaisesRegex(m.AuditHold,"CONFIDENCE_BBC1_G53A_MSA_SHA"):
                    m.audit(a,b)
    def test_no_msa_yml_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a,b,c=writefixture(d)
            p=a/"BBC1_WT_MSA.yaml"
            p.write_bytes(p.read_bytes()+b"msa: empty\n")
            c["BBC1_WT_MSA"]["yaml_sha256"]=m.sha_bytes(p.read_bytes())
            with mock.patch.object(m,"CASES",c):
                with self.assertRaisesRegex(m.AuditHold,"MSA_MODE_INVALID"):
                    m.audit(a,b)
    def test_source_alignment_sha_required(self):
        with tempfile.TemporaryDirectory() as d:
            a,b,c=writefixture(d)
            p=next(b.rglob("uniref.a3m"));p.write_text(">another\nAAAA\n")
            with mock.patch.object(m,"CASES",c):
                with self.assertRaisesRegex(m.AuditHold,"MSA_"):
                    m.audit(a,b)
    def test_plddt_array_mean_not_complex_holds(self):
        with tempfile.TemporaryDirectory() as d:
            a,b,c=writefixture(d)
            p=next(b.rglob("plddt_BBC1_WT_MSA_model_0.npz"))
            np.savez(p,plddt=np.repeat(np.float64(.8),64))
            c["BBC1_WT_MSA"]["plddt_npz_sha256"]=m.sha_bytes(p.read_bytes())
            with mock.patch.object(m,"CASES",c):
                with self.assertRaisesRegex(m.AuditHold,"PLDDT_MEAN_NOT_COMPLEX_PLDDT"):
                    m.audit(a,b)
    def test_wrong_plddt_residue_count_holds(self):
        with tempfile.TemporaryDirectory() as d:
            a,b,c=writefixture(d)
            p=next(b.rglob("plddt_BBC1_WT_MSA_model_0.npz"))
            np.savez(p,plddt=np.repeat(np.float64(.95),63))
            c["BBC1_WT_MSA"]["plddt_npz_sha256"]=m.sha_bytes(p.read_bytes())
            with mock.patch.object(m,"CASES",c):
                with self.assertRaisesRegex(m.AuditHold,"PLDDT_LENGTH_OR_RANGE_INVALID"):
                    m.audit(a,b)
    def test_duplicate_confidence_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            a,b,c=writefixture(d)
            p=next(b.rglob("confidence_BBC1_WT_MSA_model_0.json"))
            q=b/"duplicates";q.mkdir();(q/p.name).write_bytes(p.read_bytes())
            with mock.patch.object(m,"CASES",c):
                with self.assertRaisesRegex(m.AuditHold,"CONFIDENCE_NOT_EXACTLY_ONE"):
                    m.audit(a,b)
if __name__=="__main__":unittest.main()
