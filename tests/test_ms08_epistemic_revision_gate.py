import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "registry/myth_busted/FALLOUT-3-MS08-AFFECTED-PARTY-EPISTEMIC-REVISION-TECHNICAL-v2.9.json"
MOD_PATH = ROOT / "tools/ms08_admission_verifier.py"

spec = importlib.util.spec_from_file_location("ms08_admission_verifier", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def load():
    return mod.load_json(SPEC)


def test_epistemic_revision_passes():
    s = load()
    r = mod.verify_claim(
        s,
        "A3_21_MODEL_REVISION_FROM_RUNAWAY_TESTIMONY",
        ["EV_RETENTION_ROLE", "EV_POST_VIOLET_RECOLLECTION", "EV_PRETRANS_PERSONHOOD"],
    )
    assert r["result"] == "PASS"


def test_group_personhood_generalization_passes():
    s = load()
    r = mod.verify_claim(s, "A3_21_GENERALIZED_TO_SYNTH_PERSONHOOD", ["EV_PRETRANS_PERSONHOOD"])
    assert r["result"] == "PASS"


def test_self_interest_does_not_prove_falsehood():
    s = load()
    r = mod.verify_claim(
        s,
        "A3_21_TESTIMONY_IS_FALSE_BECAUSE_SELF_INTEREST",
        ["EV_SELF_INTEREST_ADMISSION", "EV_POST_VIOLET_RECOLLECTION"],
    )
    assert r["result"] == "REJECT"
    assert any(x["code"] == "NO_DIRECT_SUPPORT_FOR_ANY_REQUIRED_ALTERNATIVE" for x in r["reasons"])


def test_enforcer_role_does_not_discount_affected_party_testimony():
    s = load()
    r = mod.verify_claim(
        s,
        "RUNAWAY_TESTIMONY_IS_IRRELEVANT_BECAUSE_A3_21_WAS_ENFORCER",
        ["EV_RETENTION_ROLE", "EV_POST_VIOLET_RECOLLECTION"],
    )
    assert r["result"] == "REJECT"


def test_warning_does_not_prove_rebellion_leadership():
    s = load()
    r = mod.verify_claim(s, "A3_21_LED_SYNTH_REBELLION", ["EV_PRETRANS_PERSONHOOD"])
    assert r["result"] == "REJECT"


def test_repetition_does_not_create_independent_quorum():
    s = load()
    r = mod.verify_claim(
        s,
        "EVERY_RUNAWAY_IS_INDEPENDENT_ENUMERATED_WITNESS",
        ["EV_POST_VIOLET_RECOLLECTION"],
    )
    assert r["result"] == "REJECT"


def test_removed_source_binding_breaks_revision_proof():
    s = load()
    r = mod.verify_claim(
        s,
        "A3_21_MODEL_REVISION_FROM_RUNAWAY_TESTIMONY",
        ["EV_RETENTION_ROLE", "EV_POST_VIOLET_RECOLLECTION", "EV_PRETRANS_PERSONHOOD"],
        mutations=[
            {
                "evidence_id": "EV_POST_VIOLET_RECOLLECTION",
                "field": "source_bound",
                "value": False,
            }
        ],
    )
    assert r["result"] == "REJECT"
    assert "EV_POST_VIOLET_RECOLLECTION" in r["inadmissible_evidence_ids"]
