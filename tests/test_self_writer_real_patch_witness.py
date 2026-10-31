"""Independent immutable real model-repair journal sanity checks."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
from datetime import datetime, timedelta, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"modules/autonomy_coder"))
from real_operational_consumer import floor_age_us

WITNESS=ROOT/"data/self_writer/JANUS_SELF_WRITER_REAL_REPAIR_001.json"
MODULE=ROOT/"modules/autonomy_coder/real_operational_consumer.py"

def git_blob_sha(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

class ModelRepairWitnessTests(unittest.TestCase):
    def test_trusted_journal_and_exact_installed_source(self):
        w=json.loads(WITNESS.read_bytes())
        self.assertEqual(w["status"],"INSTALLED_REAL_MAIN_AND_CLOUD_CANARY_PASS__FULL_AUTONOMY_NOT_PROVEN")
        raw=MODULE.read_bytes()
        self.assertEqual(git_blob_sha(raw),w["installation"]["postmerge_target_git_blob_sha"])
        source=w["typed_compilation"]["source"]
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),
                         w["typed_compilation"]["source_sha256"])
        self.assertEqual(source,"def floor_age_us(delta_us):\n    return delta_us // 1000000\n")
        self.assertEqual(raw.count(source.encode()),1)
        self.assertFalse(w["model_proposal"]["raw_source_admitted"])
        self.assertFalse(w["installation"]["model_can_modify_main_directly"])
        self.assertFalse(w["limits"]["native_demiurge_authorship_proven"])
        self.assertFalse(w["limits"]["p2_ten_independent_tasks_accepted"])

    def test_model_raw_rejection_historical_provenance(self):
        w=json.loads(WITNESS.read_bytes())
        for x in w["model_proposal"]["raw_variants"]:
            self.assertEqual(hashlib.sha256(x["source"].encode()).hexdigest(),
                             x["source_sha256"])
            self.assertIn("import math",x["source"])
            self.assertIn("REJECTED",x["original_verdict"])
        self.assertEqual(w["typed_compilation"]["independent_variants_passed"],2)
        self.assertEqual(w["typed_compilation"]["independent_cases_each"],417)

    def test_real_signed_boundary_and_exact_fallback_scope(self):
        for microseconds in (-10**16-1,-3600000001,-1500000,-500000,-1,0,1,
                             500000,3600000000,3600000001,10**16+1):
            with self.subTest(us=microseconds):
                self.assertEqual(floor_age_us(microseconds),microseconds//1000000)
        w=json.loads(WITNESS.read_bytes())
        self.assertFalse(w["rollback"]["automatic_main_revert_enabled"])
        self.assertEqual(w["rollback"]["target_merge_commit"],
                         w["installation"]["merge_commit_sha"])
        self.assertNotEqual(w["installation"]["previous_commit_sha"],
                            w["installation"]["merge_commit_sha"])

if __name__=="__main__":
    unittest.main()
