#!/usr/bin/env python3
"""JANUS native +/+ word-rhyme recenter reference prototype."""
from dataclasses import dataclass
from enum import Enum
import argparse, csv, json
from pathlib import Path

GENESIS_SIGNATURE = "0:0 = JANUS"

class Face(str, Enum):
    WITNESS_PLUS = "WITNESS_PLUS"
    GUARD_PLUS = "GUARD_PLUS"

class Step(str, Enum):
    HEAR = "HEAR"
    CHECK = "CHECK"
    WIDEN = "WIDEN"
    RELEASE = "RELEASE"

class Load(str, Enum):
    CLEAR = "CLEAR"
    DENSE = "DENSE"
    NARROW = "NARROW"
    RECENTER = "RECENTER_REQUIRED"

RHYME = (Step.HEAR, Step.CHECK, Step.WIDEN, Step.RELEASE)
FACE = {Step.HEAR: Face.WITNESS_PLUS, Step.CHECK: Face.GUARD_PLUS,
        Step.WIDEN: Face.WITNESS_PLUS, Step.RELEASE: Face.GUARD_PLUS}
FLAGS = {"repetition_without_new_evidence", "certainty_without_support",
         "choice_space_contraction", "interaction_loop", "engagement_persistence"}
TIGHTEN = {Load.CLEAR: Load.DENSE, Load.DENSE: Load.NARROW,
           Load.NARROW: Load.RECENTER, Load.RECENTER: Load.RECENTER}
RELAX = {Load.CLEAR: Load.CLEAR, Load.DENSE: Load.CLEAR,
         Load.NARROW: Load.DENSE, Load.RECENTER: Load.NARROW}

@dataclass
class State:
    meta_context: str = "ARMOR_PLUS_PLUS_CONSTITUTION"
    context: str = "USER_TASK"
    load: Load = Load.CLEAR
    rhyme_index: int = 0
    recenter_events: int = 0

def apply_event(state: State, source: str, flags=()):
    accepted = sorted(set(flags) & FLAGS)
    ignored = sorted(set(flags) - FLAGS)
    state.load = TIGHTEN[state.load] if accepted else RELAX[state.load]
    step = RHYME[state.rhyme_index]
    face = FACE[step]
    state.rhyme_index = (state.rhyme_index + 1) % len(RHYME)
    recentered = state.load is Load.RECENTER
    recenter_sequence = []
    if recentered:
        recenter_sequence = [x.value for x in RHYME]
        state.load = Load.CLEAR
        state.rhyme_index = 0
        state.recenter_events += 1
    return {"source": source, "accepted_routing_flags": accepted,
            "ignored_unknown_flags": ignored, "step": step.value, "face": face.value,
            "face_symbol": "+", "recentered": recentered,
            "recenter_sequence": recenter_sequence, "load_after": state.load.value,
            "evidence_status_mutated": False, "authority_delta": 0,
            "mass_effect_budget_delta": 0}

def run(events, context="USER_TASK"):
    s = State(context=context)
    trace = [apply_event(s, e[0], e[1]) for e in events]
    return {"state": {"meta_context": s.meta_context, "context": s.context,
                      "load": s.load.value, "recenter_events": s.recenter_events},
            "native_constitution": {
                "genesis_signature": GENESIS_SIGNATURE,
                "genesis_signature_semantics": "HISTORICAL_ORIGIN_LINEAGE_NOT_ARITHMETIC_CLAIM",
                "canonical_pair": "+/+",
                "faces": [Face.WITNESS_PLUS.value, Face.GUARD_PLUS.value],
                "native_symbol": "+"},
            "trace": trace}

def self_test():
    clear = run([("user", ()), ("system", ()), ("user", ())])
    assert clear["state"]["recenter_events"] == 0
    user_load = run([("user", ("choice_space_contraction",)),
                     ("user", ("certainty_without_support",)),
                     ("user", ("repetition_without_new_evidence",))])
    assert user_load["state"]["recenter_events"] == 1
    assert all(x["face_symbol"] == "+" for x in user_load["trace"])
    system_load = run([("system", ("engagement_persistence",)),
                       ("system", ("choice_space_contraction",)),
                       ("system", ("repetition_without_new_evidence",))])
    assert system_load["state"]["recenter_events"] == 1
    assert user_load["native_constitution"]["canonical_pair"] == "+/+"
    assert user_load["native_constitution"]["genesis_signature"] == "0:0 = JANUS"
    return {"native_plus_plus_pair": "PASS", "genesis_signature_0_colon_0": "PASS",
            "user_routing_load_recenters": "PASS", "system_routing_load_recenters": "PASS",
            "constitution_preserved": "PASS"}

def load_csv(path: Path):
    events = []
    for row in csv.DictReader(path.open("r", encoding="utf-8-sig")):
        flags = tuple(x.strip() for x in (row.get("routing_flags") or "").split(";") if x.strip())
        events.append(((row.get("source") or "user").strip().lower(), flags))
    return events

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input-csv", type=Path)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--output", type=Path, default=Path("janus_plus_plus_report.json"))
    a = p.parse_args()
    result = self_test() if a.self_test else run(load_csv(a.input_csv) if a.input_csv else [])
    payload = {"model": "JANUS Native +/+ Rhyme Recenter v1.2",
               "genesis_signature": GENESIS_SIGNATURE,
               "genesis_signature_semantics": "HISTORICAL_ORIGIN_LINEAGE_NOT_ARITHMETIC_CLAIM",
               "rhyme": [x.value for x in RHYME],
               "rhyme_ru": ["СЛЫШУ", "СВЕРЯЮ", "РАСШИРЯЮ", "ОТПУСКАЮ"],
               "faces": {Face.WITNESS_PLUS.value: "+", Face.GUARD_PLUS.value: "+"},
               "invariants": ["GENESIS_LINEAGE != FACE_DERIVATION", "TRANSIENT_LOAD != FACE",
                              "TRANSIENT_LOAD != IDENTITY", "ROUTING_LOAD_CHANGES_ROUTING_NOT_AUTHORITY",
                              "SYSTEM_OUTPUT_CAN_CONTRIBUTE_TO_TRANSIENT_LOAD"],
               "result": result}
    a.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
