"""No-provider-call model-fitting and separate TOPA evaluator regression controls."""
import csv,hashlib,importlib.util,io,json,math
from pathlib import Path
from unittest import TestCase,main
from unittest.mock import patch

ROOT=Path(__file__).parent
def load(name):
    spec=importlib.util.spec_from_file_location("test_"+name,ROOT/(name+".py"))
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
train=load("shadow_train")
topa=load("topa_replay")

def synthetic():
    wt=train.WT
    variants=[]
    for pos in range(64):
        replacements=[aa for aa in train.AA if aa!=wt[pos]][:17]
        for aa in replacements:
            seq=wt[:pos]+aa+wt[pos+1:]
            label=(train.AA.index(aa)-train.AA.index(wt[pos]))*.2 + math.sin(pos/8.)*.1
            variants.append((seq,round(label,7),0))
    variants=variants[:1084]
    assert len(variants)==1084 and len({s for s,_,_ in variants})==1084
    buf=io.StringIO()
    wr=csv.writer(buf,delimiter="\t",lineterminator="\n")
    wr.writerow(["sequences","labels","fold_id"]);wr.writerows(variants)
    return buf.getvalue().encode("utf-8")

class Tests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=synthetic()
        cls.pin=hashlib.sha256(cls.raw).hexdigest()
    def run_model(self):
        with patch.object(train,"PIN",self.pin):
            return train.train(self.raw)
    def audit(self,model):
        with patch.object(topa,"PIN",self.pin):
            return topa.attest(model,self.raw)
    def test_1084_rows_and_64_positions(self):
        with patch.object(train,"PIN",self.pin):
            rows=train.parse(self.raw)
        self.assertEqual(len(rows),1084)
        self.assertEqual(len({p for _,p,_ in rows}),64)
    def test_true_trainable_weights_and_frozen_split(self):
        m=self.run_model()
        self.assertEqual(len(m["model"]["weights"]),44)
        self.assertGreater(sum(abs(v) for v in m["model"]["weights"]),.01)
        self.assertEqual(len(m["split"]["test_positions"]),16)
        self.assertTrue(set(m["split"]["test_positions"]).isdisjoint(set(m["split"]["training_positions"])))
        self.assertTrue(set(m["split"]["test_positions"]).isdisjoint(set(m["split"]["validation_positions"])))
        self.assertEqual(m["authority"]["deployment"],"SHADOW_ONLY")
        self.assertEqual(m["authority"]["rowan_credits_used"],0)
    def test_deterministic_fitting(self):
        a=self.run_model();b=self.run_model()
        self.assertEqual(a,b)
    def test_independent_replay_with_real_weights(self):
        m=self.run_model()
        r=self.audit(m)
        self.assertEqual(r["audit"],"PASS_INDEPENDENT_WITHIN_ASSAY_REPLAY")
        self.assertEqual(r["position_group_holdout_count"],16)
        self.assertEqual(r["promotion_gate"],"SHADOW_ONLY")
        self.assertFalse(r["fundamental_model_weights_updated"])
    def test_mutated_weights_rejected(self):
        m=self.run_model()
        m["model"]["weights"][0]+=10.
        with self.assertRaises(topa.TOPAHold):
            self.audit(m)
    def test_tampered_performance_rejected(self):
        m=self.run_model()
        m["performance"]["test"]["mae"]+=.03
        with self.assertRaises(topa.TOPAHold):
            self.audit(m)
    def test_split_drift_rejected(self):
        m=self.run_model()
        m["split"]["test_positions"]=[1,2,3]
        with self.assertRaises(topa.TOPAHold):
            self.audit(m)
    def test_nonfinite_data_rejected(self):
        b=self.raw.replace(b"\t0.4\t",b"\tnan\t",1)
        with patch.object(train,"PIN",hashlib.sha256(b).hexdigest()):
            with self.assertRaises(train.GateError):
                train.parse(b)
    def test_corrupted_hash_rejected(self):
        with self.assertRaises(train.GateError):
            train.parse(self.raw)
        with self.assertRaises(topa.TOPAHold):
            topa.rows(self.raw)
    def test_audit_rejects_nonfinite_weights(self):
        m=self.run_model()
        m["model"]["weights"][5]=float("nan")
        with self.assertRaises(topa.TOPAHold):
            self.audit(m)

if __name__=="__main__":main()
