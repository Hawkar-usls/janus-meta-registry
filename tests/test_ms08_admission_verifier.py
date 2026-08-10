import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "registry/myth_busted/FALLOUT-3-MS08-EVIDENCE-CLAIM-ADMISSION-TECHNICAL-v2.6.json"
MOD_PATH = ROOT / "tools/ms08_admission_verifier.py"

spec = importlib.util.spec_from_file_location("ms08_admission_verifier", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def load():
    return mod.load_json(SPEC)

def test_positive_harkness_identity_passes():
    s = load()
    r = mod.verify_claim(
        s,
        "HARKNESS_IS_POST_TRANSFORMATION_A3_21",
        [
            "EV_PINKERTON_LOG3_HARKNESS",
            "EV_HARKNESS_POST_VIOLET_DIALOGUE",
            "EV_ZIMMER_BETA_RESET_ON_HARKNESS",
        ],
    )
    assert r["result"] == "PASS"

def test_genuine_component_does_not_prove_death():
    s = load()
    r = mod.verify_claim(
        s,
        "HARKNESS_IS_DEAD",
        [
            "EV_ANDROID_COMPONENT",
            "EV_ZIMMER_COMPONENT_INTERPRETATION",
        ],
    )
    assert r["result"] == "REJECT"
    assert any(x["code"] == "NO_DIRECT_SUPPORT_FOR_ANY_REQUIRED_ALTERNATIVE" for x in r["reasons"])

def test_counterexample_blocks_death_claim():
    s = load()
    r = mod.verify_claim(
        s,
        "HARKNESS_IS_DEAD",
        [
            "EV_ANDROID_COMPONENT",
            "EV_ZIMMER_COMPONENT_INTERPRETATION",
            "EV_VICTORIA_COMPONENT_COUNTEREXAMPLE",
        ],
    )
    assert r["result"] == "REJECT"
    assert "HARKNESS_ALIVE_WHILE_COMPONENT_CAN_BE_PRESENTED" in r["blocking_atoms_present"]

def test_removed_provenance_breaks_positive_proof():
    s = load()
    r = mod.verify_claim(
        s,
        "HARKNESS_IS_POST_TRANSFORMATION_A3_21",
        [
            "EV_PINKERTON_LOG3_HARKNESS",
            "EV_HARKNESS_POST_VIOLET_DIALOGUE",
            "EV_ZIMMER_BETA_RESET_ON_HARKNESS",
        ],
        mutations=[
            {
                "evidence_id": "EV_PINKERTON_LOG3_HARKNESS",
                "field": "source_bound",
                "value": False,
            }
        ],
    )
    assert r["result"] == "REJECT"
    assert "EV_PINKERTON_LOG3_HARKNESS" in r["inadmissible_evidence_ids"]

def test_authentic_but_unrelated_object_cannot_fill_missing_atom():
    s = load()
    r = mod.verify_claim(
        s,
        "HARKNESS_IS_POST_TRANSFORMATION_A3_21",
        [
            "EV_ANDROID_COMPONENT",
            "EV_HARKNESS_POST_VIOLET_DIALOGUE",
            "EV_ZIMMER_BETA_RESET_ON_HARKNESS",
        ],
    )
    assert r["result"] == "REJECT"
    missing = next(x for x in r["reasons"] if x["code"] == "MISSING_REQUIRED_ATOMS")
    assert "A3_21_TO_HARKNESS_TRANSFORMATION_RECORDED" in missing["atoms"]
