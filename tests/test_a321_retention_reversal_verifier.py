import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "registry/myth_busted/FALLOUT-3-A3-21-SYNTH-RELATION-RETENTION-REVERSAL-TECHNICAL-v2.8.json"
MOD_PATH = ROOT / "tools/evidence_claim_admission_verifier.py"
spec = importlib.util.spec_from_file_location("evidence_claim_admission_verifier", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def load(): return mod.load_json(SPEC)

def test_retention_hunter_passes():
    assert mod.verify_claim(load(),"A3_21_WAS_RETENTION_HUNTER_OF_RUNAWAYS",["EV_ZIMMER_A321_ROLE"])["result"]=="PASS"

def test_runaway_testimony_changed_a321():
    assert mod.verify_claim(load(),"RUNAWAY_TESTIMONY_CHANGED_A3_21",["EV_HARKNESS_POST_VIOLET_REVERSAL"])["result"]=="PASS"

def test_collective_personhood_passes():
    assert mod.verify_claim(load(),"A3_21_RECOGNIZED_SYNTH_PERSONHOOD_AND_COLLECTIVE_MEMBERSHIP",["EV_SHIPPED_SELF_DETERMINATION_RECORDING"])["result"]=="PASS"

def test_rebellion_leader_overclaim_rejects():
    assert mod.verify_claim(load(),"A3_21_IS_REBELLION_LEADER",["EV_SHIPPED_SELF_DETERMINATION_RECORDING","EV_HARKNESS_POST_VIOLET_REVERSAL"])["result"]=="REJECT"

def test_courser_overclaim_rejects():
    assert mod.verify_claim(load(),"A3_21_IS_FIRST_COURSER",["EV_ZIMMER_A321_ROLE"])["result"]=="REJECT"

def test_cut_content_alone_cannot_prove_shipped_claim():
    assert mod.verify_claim(load(),"A3_21_RECOGNIZED_SYNTH_PERSONHOOD_AND_COLLECTIVE_MEMBERSHIP",["EV_CUT_TRANSCRIPT"])["result"]=="REJECT"

def test_removed_source_binding_breaks_reversal():
    r=mod.verify_claim(load(),"RUNAWAY_TESTIMONY_CHANGED_A3_21",["EV_HARKNESS_POST_VIOLET_REVERSAL"],mutations=[{"evidence_id":"EV_HARKNESS_POST_VIOLET_REVERSAL","field":"source_bound","value":False}])
    assert r["result"]=="REJECT"
