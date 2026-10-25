"""Synthetic proof obligations, no FireProt outcome labels and no GPU costs."""
from __future__ import annotations
import hashlib,importlib.util,io,json,pathlib,unittest
from unittest import mock
p=pathlib.Path(__file__).with_name("fireprot_inference_and_custody_gate.py")
s=importlib.util.spec_from_file_location("preflight",p)
g=importlib.util.module_from_spec(s);s.loader.exec_module(g)

def fake_manifest():
    dd=[]
    for j in range(10):
        pid=f"T{j:03}"
        dd.append({"pdb_id":pid,"wildtype_sha256":"0"*64,
             "pdb_member_sha256":"1"*64,
             "variants":[{"mutation":f"A{k+1}C","mutant_sequence_sha256":"2"*64} for k in range(20)]})
    return {"schema_id":"janus.rowan.external_fireprot_label_quarantined_input.v1",
        "source":{"zip_sha256":g.SOURCE_ARCHIVE_SHA256},
        "inference":{"frozen_shadow_model_sha256":g.MODEL_SHA256},
        "domains":dd}

def fake_baseline(mraw):
    obj=json.loads(mraw)
    return {"schema_id":"janus.rowan.external_fireprot_zero_reference_commit.v1",
            "manifest_sha256":g.sha(mraw),
            "shadow_features_computed":False,
            "entries":[{"pdb_id":d["pdb_id"],"mutation":v["mutation"],
                       "predicted_delta_delta_G_kcal_per_mol":0.0}
                       for d in obj["domains"] for v in d["variants"]]}

def fake_pairmap():
    pairs={}
    for j in range(10):
        pid=f"T{j:03}"
        for k in range(20):
            name=f"A{k+1}C"
            pairs[pid,name]={"wt_sha":"0"*64,"mutant_sha":"2"*64,"pdb_member_sha":"1"*64}
    return pairs

def fake_receipts():
    results=[]
    for (pdb,mut),spec in fake_pairmap().items():
        results.append({
            "schema_id":"janus.rowan.external_fireprot.boltz2_pair.v1",
            "pdb_id":pdb,"mutation":mut,
            "wt_sequence_sha256":spec["wt_sha"],
            "mutant_sequence_sha256":spec["mutant_sha"],
            "pdb_member_sha256":spec["pdb_member_sha"],
            "provider":"test-only","model_identifier":"fixture","model_revision":"v1",
            "inference_config_sha256":"a"*64,"metric_equivalence_witness_sha256":"b"*64,
            "metric_equivalence_witness_attested":True,
            "metric_mapping":"MATCHED_PTMS_AND_NORMALIZED_AVG_LDDT",
            "wildtype":{"ptm":0.9,"avg_lddt":0.92,"source_artifact_sha256":"c"*64,
                        "immutable_source_uri":"https://example.invalid/wt"},
            "mutant":{"ptm":0.88,"avg_lddt":0.90,"source_artifact_sha256":"d"*64,
                        "immutable_source_uri":"https://example.invalid/mut"}
        })
    return results

class ReadinessTest(unittest.TestCase):
    def test_missing_sources_stays_hold(self):
        m=json.dumps(fake_manifest()).encode()
        b=json.dumps(fake_baseline(m)).encode()
        with mock.patch.object(g,"MANIFEST_SHA256",g.sha(m)),mock.patch.object(g,"ZERO_SHA256",g.sha(b)):
            status,pred=g.preflight(m,b)
        self.assertIsNone(pred)
        self.assertFalse(status["shadow_predictions_frozen"])
        self.assertTrue(status["public_fireprot_is_not_prospective_blind"])
    def test_source_manifest_checksum_blocks(self):
        with self.assertRaisesRegex(g.GateHold,"FROZEN_PUBLIC_INPUT_OR_ZERO_REFERENCE_SHA_DRIFT"):
            g.dataset(b"wrong",b"wrong")
    def test_fake_blind_claim_blocks(self):
        with self.assertRaisesRegex(g.GateHold,"INDEPENDENT_LABEL_CUSTODIAN_NOT_DOCUMENTED"):
            g.attest_labels(None)
        with self.assertRaisesRegex(g.GateHold,"PREEXISTING_FIREPROT_PUBLIC_LABELS_NOT_PROSPECTIVE_BLIND"):
            g.attest_labels({"schema_id":"janus.rowan.external.prospective_custodian.v1",
                **{k:"x" for k in ["custodian_organization","named_responsible_person",
                    "independent_contact","signed_at_utc","independent_collection_protocol_doi_or_url"]},
                "dataset_label_commitment_sha256":"a"*64,"attestation_sha256":"a"*64,
                "unpublished_new_measurements":False})
    def test_real_metrics_required_no_fabrication(self):
        with self.assertRaisesRegex(g.GateHold,"COMPARABLE_SOURCE_PAIR_COUNT_NOT_200"):
            g.validate_pairs([],fake_pairmap())
    def test_source_pair_complete(self):
        result=g.validate_pairs(fake_receipts(),fake_pairmap())
        self.assertEqual(len(result),200)
        preds=g.predictions(result)
        self.assertEqual(len(preds),200)
        y=-1.327737761434+.196413135791*10*(-.02)-.045214428615*10*(-.02)
        self.assertAlmostEqual(preds[0]["predicted_delta_delta_G_kcal_per_mol"],y)
        self.assertTrue(all(x["no_label_access"] for x in preds))
    def test_mutation_sha_drift_blocks(self):
        records=fake_receipts();records[0]["mutant_sequence_sha256"]="5"*64
        with self.assertRaisesRegex(g.GateHold,"PAIR_SEQUENCE_NOT_FROZEN"):
            g.validate_pairs(records,fake_pairmap())
    def test_wildtype_reproducibility(self):
        records=fake_receipts();records[1]["wildtype"]["ptm"]=.8
        with self.assertRaisesRegex(g.GateHold,"WT_FEATURE_OR_PROVIDER_CONFIG_INCONSISTENT"):
            g.validate_pairs(records,fake_pairmap())
    def test_provider_version_mixing_blocks(self):
        records=fake_receipts();records[-1]["model_revision"]="v2"
        with self.assertRaisesRegex(g.GateHold,"MODEL_PROVIDER_VERSION_OR_CONFIG_INCONSISTENT"):
            g.validate_pairs(records,fake_pairmap())
    def test_metric_equivalence_not_automatic(self):
        records=fake_receipts();records[0]["metric_equivalence_witness_attested"]=False
        with self.assertRaisesRegex(g.GateHold,"ROWAN_S2_METRIC_EQUIVALENCE_NOT_PROVEN"):
            g.validate_pairs(records,fake_pairmap())
    def test_nan_and_out_of_range_block(self):
        records=fake_receipts();records[0]["mutant"]["avg_lddt"]=float("nan")
        with self.assertRaisesRegex(g.GateHold,"INVALID_PROVIDED_CONFIDENCE_SCORE"):
            g.validate_pairs(records,fake_pairmap())
        records=fake_receipts();records[0]["mutant"]["ptm"]=1.2
        with self.assertRaisesRegex(g.GateHold,"INVALID_PROVIDED_CONFIDENCE_SCORE"):
            g.validate_pairs(records,fake_pairmap())
    def test_zero_reference_not_fake_production_model(self):
        m=json.dumps(fake_manifest()).encode()
        z=fake_baseline(m)
        z["entries"][0]["predicted_delta_delta_G_kcal_per_mol"]=.123
        b=json.dumps(z).encode()
        with mock.patch.object(g,"MANIFEST_SHA256",g.sha(m)),mock.patch.object(g,"ZERO_SHA256",g.sha(b)):
            with self.assertRaisesRegex(g.GateHold,"ZERO_REFERENCE_VALUE_DRIFT"):
                g.dataset(m,b)

if __name__=="__main__":unittest.main()
