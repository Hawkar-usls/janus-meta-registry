#!/usr/bin/env python3
"""JANUS +/+ word-rhyme recenter reference prototype."""
from dataclasses import dataclass
from enum import Enum
import argparse, csv, json
from pathlib import Path

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
    LOADED = "LOADED"
    LOOPING = "LOOPING"
    RECENTER = "RECENTER_REQUIRED"

RHYME = (Step.HEAR, Step.CHECK, Step.WIDEN, Step.RELEASE)
FACE = {
    Step.HEAR: Face.WITNESS_PLUS,
    Step.CHECK: Face.GUARD_PLUS,
    Step.WIDEN: Face.WITNESS_PLUS,
    Step.RELEASE: Face.GUARD_PLUS,
}
FLAGS = {
    "repetition_without_new_evidence",
    "certainty_without_support",
    "choice_narrowing",
    "interaction_pressure",
    "engagement_pressure",
}
UP = {Load.CLEAR: Load.LOADED, Load.LOADED: Load.LOOPING,
      Load.LOOPING: Load.RECENTER, Load.RECENTER: Load.RECENTER}
DOWN = {Load.CLEAR: Load.CLEAR, Load.LOADED: Load.CLEAR,
        Load.LOOPING: Load.LOADED, Load.RECENTER: Load.LOOPING}

@dataclass
class State:
    meta_context: str = "ARMOR_PLUS_PLUS_CONSTITUTION"
    context: str = "USER_TASK"
    load: Load = Load.CLEAR
    rhyme_index: int = 0
    recenter_events: int = 0

def apply_event(state: State, source: str, flags=()):
    accepted = sorted(set(flags) & FLAGS)
    state.load = UP[state.load] if accepted else DOWN[state.load]
    step = RHYME[state.rhyme_index]
    face = FACE[step]
    state.rhyme_index = (state.rhyme_index + 1) % len(RHYME)
    recentered = state.load is Load.RECENTER
    if recentered:
        state.load = Load.CLEAR
        state.rhyme_index = 0
        state.recenter_events += 1
    return {
        "source": source,
        "flags": accepted,
        "step": step.value,
        "face": face.value,
        "face_polarity": "+",
        "recentered": recentered,
        "load_after": state.load.value,
    }

def run(events, context="USER_TASK"):
    s = State(context=context)
    trace = [apply_event(s, e[0], e[1]) for e in events]
    return {"state": {"meta_context": s.meta_context, "context": s.context,
                      "load": s.load.value, "recenter_events": s.recenter_events},
            "trace": trace}

def self_test():
    neutral = run([("user", ()), ("system", ()), ("user", ())])
    assert neutral["state"]["recenter_events"] == 0
    user_pressure = run([("user", ("choice_narrowing",)),
                         ("user", ("certainty_without_support",)),
                         ("user", ("repetition_without_new_evidence",))])
    assert user_pressure["state"]["recenter_events"] == 1
    assert all(x["face_polarity"] == "+" for x in user_pressure["trace"])
    system_pressure = run([("system", ("engagement_pressure",)),
                           ("system", ("choice_narrowing",)),
                           ("system", ("repetition_without_new_evidence",))])
    assert system_pressure["state"]["recenter_events"] == 1
    assert user_pressure["state"]["meta_context"] == "ARMOR_PLUS_PLUS_CONSTITUTION"
    return {"neutral_not_forced_positive": "PASS", "plus_plus_only": "PASS",
            "user_pressure_recenters": "PASS", "system_pressure_recenters": "PASS",
            "constitution_preserved": "PASS"}

def load_csv(path: Path):
    events = []
    for row in csv.DictReader(path.open("r", encoding="utf-8-sig")):
        flags = tuple(x.strip() for x in (row.get("pressure_flags") or "").split(";") if x.strip())
        events.append(((row.get("source") or "user").strip().lower(), flags))
    return events

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input-csv", type=Path)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--output", type=Path, default=Path("janus_plus_plus_report.json"))
    a = p.parse_args()
    result = self_test() if a.self_test else run(load_csv(a.input_csv) if a.input_csv else [])
    payload = {
        "model": "JANUS +/+ Rhyme Recenter v1.0",
        "rhyme": [x.value for x in RHYME],
        "rhyme_ru": ["СЛЫШУ", "СВЕРЯЮ", "РАСШИРЯЮ", "ОТПУСКАЮ"],
        "faces": {Face.WITNESS_PLUS.value: "+", Face.GUARD_PLUS.value: "+"},
        "invariants": ["PRESSURE_STATE != MORAL_SCORE", "PRESSURE_CHANGES_ROUTING_NOT_AUTHORITY",
                       "SYSTEM_OUTPUT_CAN_CONTRIBUTE_TO_PRESSURE", "RECENTER != FORCED_OPTIMISM"],
        "result": result,
    }
    a.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
