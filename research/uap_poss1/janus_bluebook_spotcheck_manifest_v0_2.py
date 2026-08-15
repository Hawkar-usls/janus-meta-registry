#!/usr/bin/env python3
"""Deterministic nuclear-blind Blue Book validation sample v0.2.

Corrective change from v0.1: eligibility is restricted to exact-date rows inside
the preregistered 1949-11-19 through 1957-04-28 study window. The sample is
selected from blind-index bytes only and never reads nuclear labels.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, random
from datetime import date
from pathlib import Path

RUNNER_ID="JANUS-BLUEBOOK-SPOTCHECK-MANIFEST-v0.2"
START,END=date(1949,11,19),date(1957,4,28)

def sha_file(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--blind-index",required=True); ap.add_argument("--output",required=True)
    ap.add_argument("--positive-n",type=int,default=12); ap.add_argument("--negative-n",type=int,default=12)
    a=ap.parse_args(); p=Path(a.blind_index); h=sha_file(p)
    rows=list(csv.DictReader(p.open(encoding="utf-8-sig")))
    eligible=[]
    for r in rows:
        if not (r.get("nara_naid") or "").strip() or not (r.get("occurrence_date") or "").strip(): continue
        try: d=date.fromisoformat(r["occurrence_date"])
        except ValueError: continue
        if START<=d<=END: eligible.append(r)
    pos=[r for r in eligible if int(r.get("starlike_screen") or 0)==1]
    neg=[r for r in eligible if int(r.get("starlike_screen") or 0)==0]
    seed=int(h[:16],16); rng=random.Random(seed)
    psel=pos if len(pos)<=a.positive_n else rng.sample(pos,a.positive_n)
    nsel=neg if len(neg)<=a.negative_n else rng.sample(neg,a.negative_n)
    selected=[]
    for cls,ss in [("STARLIKE_POSITIVE",psel),("STARLIKE_NEGATIVE",nsel)]:
        for r in ss:
            selected.append({
                "validation_stratum":cls,
                "nara_naid":r.get("nara_naid",""),
                "occurrence_date_extracted":r.get("occurrence_date",""),
                "source_url":r.get("source_url",""),
                "summary_sha256":r.get("summary_sha256",""),
                "summary_sample":(r.get("summary_sample") or "")[:1200],
                "verify_naid_against_source":"PENDING",
                "verify_occurrence_date_against_record_card":"PENDING",
                "verify_starlike_label_against_record_card_or_narrative":"PENDING",
                "validator_notes":""
            })
    out={
        "runner_id":RUNNER_ID,
        "status":"DETERMINISTIC_NUCLEAR_BLIND_STUDY_WINDOW_SPOTCHECK_SAMPLE_FROZEN",
        "study_window":[START.isoformat(),END.isoformat()],
        "blind_index_sha256":h,
        "seed_from_blind_sha256_prefix":seed,
        "eligible_study_rows":len(eligible),
        "starlike_positive_population":len(pos),
        "starlike_negative_population":len(neg),
        "selected_positive":len(psel),
        "selected_negative":len(nsel),
        "selection_has_nuclear_calendar_access":False,
        "rows":selected,
        "admission_rule":"Sample membership is immutable after freeze; failures remain and count against validation."
    }
    Path(a.output).write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({k:v for k,v in out.items() if k!="rows"},indent=2,ensure_ascii=False))
if __name__=="__main__": main()
