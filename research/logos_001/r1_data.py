"""Frozen synthetic scientific-law cases for JANUS-LOGOS-001 R1.

No holdout coordinates or target values are emitted from this file.  Ground
truth is kept outside the discovery input, but source is publicly auditable:
this is process separation, not a cryptographically secret benchmark.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

def noise(case_id, split, index):
    b=hashlib.sha256(f"{case_id}|{split}|{index}".encode()).digest()
    return 2.0 * int.from_bytes(b[:8],"big") / (2**64) - 1.0

def law(case_id, x, split, index):
    if case_id=="C01": return 0.75+1.5*x
    if case_id=="C02": return -0.25+0.5*x+1.25*x*x
    if case_id=="C03": return 0.4+1.2*math.sin(math.pi*x)
    if case_id=="C04": return 0.1-x+1.5*x*x*x
    if case_id=="N01": return noise(case_id,split,index)
    if case_id=="N02": return -0.1+0.75*x*x
    raise ValueError("Unknown synthetic case")

def generate():
    cases=[]
    for case_id in ("C01","C02","C03","C04","N01","N02"):
        train=[[(-1.0+2.0*i/29),law(case_id,-1.0+2.0*i/29,"train",i)] for i in range(30)]
        validation=[[(-0.97+1.94*i/22),law(case_id,-0.97+1.94*i/22,"validation",i)] for i in range(23)]
        cases.append({"id":case_id,"train":train,"validation":validation})
    return {"experiment":"JANUS-LOGOS-001","phase":"R1","protocol":"JANUS_LOGOS_001_R1_1_0","cases":cases}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    args=p.parse_args()
    obj=generate()
    Path(args.out).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("Frozen TRAIN+VALIDATION generated. No test labels produced.")

if __name__=="__main__":main()
