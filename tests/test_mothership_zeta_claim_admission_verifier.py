import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "registry/myth_busted/FALLOUT-3-MOTHERSHIP-ZETA-BIRTH-ABDUCTION-CLAIM-ADMISSION-TECHNICAL-v2.7.json"
MOD_PATH = ROOT / "tools/evidence_claim_admission_verifier.py"
spec = importlib.util.spec_from_file_location("evidence_claim_admission_verifier", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def load(): return mod.load_json(SPEC)

def test_birthday_trace_passes():
    r=mod.verify_claim(load(),"MZ_BIRTHDAY_MEMORY_DESIGN_TRACE_EXISTS",["EV_MZ_BIRTHDAY_COMMENT"])
    assert r["result"]=="PASS"

def test_alien_exam_passes():
    r=mod.verify_claim(load(),"LONE_WANDERER_IS_SUBJECTED_TO_ALIEN_EXAMINATION",["EV_MZ_ABDUCTION_SCRIPT"])
    assert r["result"]=="PASS"

def test_staged_birth_rejects():
    r=mod.verify_claim(load(),"ZETANS_PREARRANGED_LONE_WANDERER_BIRTH",["EV_PROJECT_PURITY_PREGNANCY","EV_CG00_BIRTH","EV_MZ_ABDUCTION_SCRIPT"])
    assert r["result"]=="REJECT"

def test_specific_preselection_rejects():
    r=mod.verify_claim(load(),"ZETANS_SPECIFICALLY_PRESELECTED_LONE_WANDERER",["EV_MZ_ABDUCTION_SCRIPT"])
    assert r["result"]=="REJECT"

def test_general_program_passes():
    r=mod.verify_claim(load(),"ZETAN_GENERAL_CAPTIVE_PROGRAM_INCLUDES_COLLECTION_AND_EXPERIMENTATION",["EV_ALIEN_CAPTIVE_LOGS"])
    assert r["result"]=="PASS"

def test_removed_source_binding_rejects_birthday_trace():
    r=mod.verify_claim(load(),"MZ_BIRTHDAY_MEMORY_DESIGN_TRACE_EXISTS",["EV_MZ_BIRTHDAY_COMMENT"],mutations=[{"evidence_id":"EV_MZ_BIRTHDAY_COMMENT","field":"source_bound","value":False}])
    assert r["result"]=="REJECT"
