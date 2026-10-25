"""Synthetic tests of independent raw mirror audit and mismatch detection."""
import hashlib, json, unittest
from unittest.mock import patch
import mirror_score_audit as mirror
import primary_score_gate as g
from test_primary_score_gate import data, LABELS

def records(*,mismatch=False):
    entries=[]
    for idx,(mut,score) in enumerate(zip(g.MUTATIONS,LABELS)):
        row_score=(-1.0025844433957378 if mut=="W38L" and mismatch else score)
        entries.append({"dataset_id":"proteingym_raw","row_index":idx,
          "source_file":mirror.REPORTED_SOURCE_PATH,
          "row":{"mut_type":mut,"mut_class":"single","WT_name":"1TG0.pdb",
                 "aa_seq":g.mutation_sequence(mut),g.RAW_COL:str(row_score)}})
    return ("\n".join(json.dumps(x) for x in entries)+"\n").encode()

class MirrorTests(unittest.TestCase):
    def audit_with_pins(self,mirror_bytes):
        m,p,r,receipt=data()
        with patch.object(g,"METADATA_BLOB_SHA",g.git_blob_sha(m)),\
             patch.object(g,"TSV_SHA",hashlib.sha256(p).hexdigest()),\
             patch.object(mirror,"MIRROR_SHA256",hashlib.sha256(mirror_bytes).hexdigest()):
            return mirror.audit(m,p,receipt,mirror_bytes)

    def test_clean_mirror_is_not_original_primary_provenance(self):
        report=self.audit_with_pins(records())
        self.assertEqual(report["n_matching"],8)
        self.assertEqual(report["n_discrepant"],0)
        self.assertEqual(report["primary_lab_bytewise_validation"],"NOT_DONE")
        self.assertFalse(report["model_production_promotion"])

    def test_w38l_discrepancy_blocks_promotion(self):
        report=self.audit_with_pins(records(mismatch=True))
        self.assertEqual(report["status"],"HOLD_RAW_MIRROR_PROCESSED_MISMATCH")
        self.assertEqual(report["n_matching"],7)
        self.assertEqual(report["discrepant_mutations"],["W38L"])
        diff=next(x for x in report["all_comparisons"] if x["mutation"]=="W38L")
        self.assertAlmostEqual(diff["processed_minus_raw"],0.1580303778741)

    def test_mutation_identity_mismatch_fails(self):
        rows=records().replace(b'"aa_seq": "EVPF',b'"aa_seq": "XXXXXXXXXXXXXXXX',1)
        with self.assertRaisesRegex(g.GateHold,"RAW_MIRROR_SEQUENCE_DRIFT"):
            self.audit_with_pins(rows)

    def test_unpinned_raw_mirror_fails(self):
        m,p,r,receipt=data()
        raw=records()
        with patch.object(g,"METADATA_BLOB_SHA",g.git_blob_sha(m)),\
             patch.object(g,"TSV_SHA",hashlib.sha256(p).hexdigest()):
            with self.assertRaisesRegex(g.GateHold,"PINNED_MIRROR_SHA256_DRIFT"):
                mirror.audit(m,p,receipt,raw)

if __name__=="__main__":unittest.main()
