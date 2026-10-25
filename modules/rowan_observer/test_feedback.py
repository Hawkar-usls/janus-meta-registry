"""Controlled, synthetic tests of ongoing Rowan source-bound weight calibration."""
import importlib.util,hashlib,json,tempfile
from pathlib import Path
from unittest import TestCase,main
import copy

ROOT=Path(__file__).parent
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/(name+".py"))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m
learn=load("feedback_train")
topa=load("topa_feedback_replay")

def fake(n):
    arr=[]
    for i,(mut,q) in enumerate(zip(learn.MUTATIONS,learn.QUANTILES)):
        done=i<n
        v={"mutation":mut,"quantile":q,"published_processed_label":(i-3)*.8,
           "provider_state":"PROVIDER_RESULT_RETURNED" if done else "NOT_SUBMITTED"}
        if done:
            v["ptm"]=round(.85+i*.01,3)
            v["avg_lddt"]=round(.88+i*.008,3)
            v["credits_charged"]=5.
        arr.append(v)
    return {"schema_id":"janus.meta_registry.rowan_evidence_receipt.v1",
        "original_public_data_sha256":learn.PIN,
        "source":{"run_id":12345,"source_artifact_sha256":"a"*64},
        "wildtype":{"provider_state":"PROVIDER_RESULT_RETURNED","ptm":.84,"avg_lddt":.86},
        "calibration":{"classification":"SYNTHETIC_ONLY"},
        "cases":arr}

class FeedbackTests(TestCase):
    def test_initial_waits_without_three_mutants(self):
        self.assertIsNone(learn.fit_feedback(fake(0),"b"*64))
        self.assertIsNone(learn.fit_feedback(fake(2),"b"*64))
    def test_train_real_weights_when_four_evidence_cases(self):
        m=learn.fit_feedback(fake(4),"b"*64)
        self.assertEqual(len(m["fit"]["weights"]),2)
        self.assertEqual(m["split"]["completed_training_mutations"],list(learn.MUTATIONS[:4]))
        self.assertFalse(m["metrics"]["heldout_two_mutants_complete"])
        self.assertEqual(m["authority"]["rowan_credits_used"],0)
        self.assertFalse(m["authority"]["boltz2_weights_modified"])
    def test_independent_scalar_replay_when_n4(self):
        raw=fake(4);model=learn.fit_feedback(raw,"b"*64)
        review=topa.review(model,raw)
        self.assertEqual(review["audit"],"PASS_INDEPENDENT_SCALAR_COEFFICIENT_REPLAY")
        self.assertFalse(review["heldout_complete"])
    def test_holdout_only_after_both_frozen_mutants(self):
        raw=fake(8);model=learn.fit_feedback(raw,"b"*64)
        review=topa.review(model,raw)
        self.assertTrue(review["heldout_complete"])
        self.assertEqual(review["observed_training_mutations"],6)
        self.assertIsNotNone(review["heldout_mae"])
        self.assertEqual(review["promotion"],"DENIED_SHADOW_ONLY")
    def test_coefficient_tamper_rejected(self):
        raw=fake(8);model=learn.fit_feedback(raw,"b"*64)
        model["fit"]["weights"][0]+=1
        with self.assertRaises(topa.TOPAHold):topa.review(model,raw)
    def test_training_cannot_see_reserved_cases(self):
        a=fake(6);b=fake(8)
        self.assertEqual(learn.fit_feedback(a,"b"*64)["fit"],learn.fit_feedback(b,"b"*64)["fit"])
    def test_credit_alert_blocks_updates(self):
        r=fake(4)
        r["cases"][1]["provider_credit_cap_alert"]=True
        with self.assertRaises(learn.Hold):learn.fit_feedback(r,"b"*64)
    def test_source_state_sha_and_calibration_binding(self):
        r=fake(0)
        data=json.dumps(r,indent=2).encode()+b"\n"
        key=hashlib.sha256(learn.canonical(r["calibration"])).hexdigest()[:20]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/learn.BASE
            (p/"receipts").mkdir(parents=True)
            (p/"receipts"/"ROWAN-S2-12345-fixture.json").write_bytes(data)
            state={"schema_id":"janus.rowan.observer_state.v1",
                   "latest_durable_external_run":12345,
                   "underlying_state_is_derived_from":"a"*64,
                   "notification_dedupe_key":key}
            (p/"CANONICAL_STATE.json").write_text(json.dumps(state))
            output,digest=learn.find_verified_receipt(d)
            self.assertEqual(digest,hashlib.sha256(data).hexdigest())
            self.assertEqual(output["source"]["run_id"],12345)
            state["notification_dedupe_key"]="bad"
            (p/"CANONICAL_STATE.json").write_text(json.dumps(state))
            with self.assertRaises(learn.Hold):learn.find_verified_receipt(d)
    def write_canonical_fixture(self, root, raw):
        base=Path(root)/learn.BASE
        (base/"receipts").mkdir(parents=True,exist_ok=True)
        data=json.dumps(raw,indent=2).encode()+b"\n"
        rid=raw["source"]["run_id"]
        (base/"receipts"/f"ROWAN-S2-{rid}-test.json").write_bytes(data)
        state={"schema_id":"janus.rowan.observer_state.v1",
               "latest_durable_external_run":rid,
               "underlying_state_is_derived_from":raw["source"]["source_artifact_sha256"],
               "notification_dedupe_key":hashlib.sha256(
                   learn.canonical(raw["calibration"])).hexdigest()[:20]}
        (base/"CANONICAL_STATE.json").write_text(json.dumps(state))
        return base

    def test_repeated_collector_snapshot_does_not_mint_identical_weights(self):
        with tempfile.TemporaryDirectory() as d:
            first=fake(3)
            base=self.write_canonical_fixture(d,first)
            original=learn.run(d)
            self.assertTrue(original.is_file())
            second=copy.deepcopy(first)
            second["source"]={"run_id":12346,"source_artifact_sha256":"c"*64}
            self.write_canonical_fixture(d,second)
            reused=learn.run(d)
            self.assertEqual(reused,original)
            self.assertEqual(len(list((base/"feedback").glob("FEEDBACK-RUN*.json"))),1)
            third=fake(4)
            third["source"]={"run_id":12347,"source_artifact_sha256":"d"*64}
            self.write_canonical_fixture(d,third)
            newer=learn.run(d)
            self.assertNotEqual(newer,original)
            self.assertEqual(len(list((base/"feedback").glob("FEEDBACK-RUN*.json"))),2)

    def test_changed_original_source_or_fitted_coefficients_cannot_hide_as_noop(self):
        with tempfile.TemporaryDirectory() as d:
            first=fake(3)
            base=self.write_canonical_fixture(d,first)
            original=learn.run(d)
            second=copy.deepcopy(first)
            second["source"]={"run_id":12346,"source_artifact_sha256":"c"*64}
            self.write_canonical_fixture(d,second)
            bad=json.loads(original.read_text(encoding="utf-8"))
            bad["fit"]["weights"][0]+=0.25
            original.write_text(json.dumps(bad),encoding="utf-8")
            with self.assertRaisesRegex(learn.Hold,"SAME_INPUT_DIVERGENT_FEEDBACK_MODEL"):
                learn.run(d)

    def test_source_mutant_list_falsifier(self):
        r=fake(8);m=learn.fit_feedback(r,"b"*64)
        r["cases"][7]["mutation"]="WRONG"
        with self.assertRaises(topa.TOPAHold):topa.review(m,r)

if __name__=="__main__":main()
