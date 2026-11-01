"""JANUS LOGOS R1.2: frozen external observed NIST measurements.

Read source fixtures mirrored byte-for-byte from NIST / ceres-solver.
The source datfiles include published reference models, but the discovery
input exposes only measured train/validation x-y pairs. Not truly blind.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

HERE=Path(__file__).resolve().parent/"data_r12"
NAMES=("ECKERLE4","CHWIRUT2")
FILE={"ECKERLE4":"Eckerle4.dat","CHWIRUT2":"Chwirut2.dat"}
EXPECTED={"ECKERLE4":(35,35,(21,7,7)),"CHWIRUT2":(54,22,(29,9,16))}
PAIR=re.compile(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)[eE][+-]?\d+)\s+([+-]?(?:\d+\.?\d*|\.\d+)[eE][+-]?\d+)\s*$")

def rows(name):
    if name not in NAMES:raise ValueError("Unrecognized case")
    text=(HERE/FILE[name]).read_text(encoding="utf-8")
    pairs=[]
    for line in text.splitlines():
        m=PAIR.fullmatch(line)
        if m:pairs.append((float(m[2]),float(m[1])))
    n,u,_=EXPECTED[name]
    if len(pairs)!=n or len(set(x for x,y in pairs))!=u:
        raise ValueError(f"Unverifiable NIST dataset shape: {name}")
    return pairs

def normalize(name,x):
    return (x-400.0)/100.0 if name=="ECKERLE4" else x/6.0

def split(name):
    pairs=rows(name)
    unique=sorted({x for x,y in pairs})
    which={x:("test" if i%5==0 else "validation" if i%5==1 else "train")
           for i,x in enumerate(unique)}
    partitions={"train":[],"validation":[],"test":[]}
    for x,y in pairs:
        partitions[which[x]].append([normalize(name,x),y])
    n,u,expected=EXPECTED[name]
    counts=tuple(len(partitions[k]) for k in ("train","validation","test"))
    if counts!=expected:raise ValueError("Frozen holdout counts violated")
    if {x for x,y in partitions["train"]}&{x for x,y in partitions["test"]}:
        raise ValueError("Identical x leakage")
    return partitions

def discovery():
    studies=[]
    for name in NAMES:
        d=split(name)
        studies.append({"id":name,"train":d["train"],"validation":d["validation"]})
    for name in NAMES:
        d=split(name)
        y=[p[1] for p in d["validation"]]
        shift=len(y)//2
        studies.append({"id":name+"_SHUFFLED_VALIDATION","train":d["train"],
                        "validation":[[row[0],y[(i+shift)%len(y)]]
                                      for i,row in enumerate(d["validation"])]})
    return {"experiment":"JANUS-LOGOS-001","phase":"R1.2",
            "source":"NIST_STDR_OBSERVED_NONLINEAR_MEASUREMENTS","cases":studies}

def canonical_sha(o):
    return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--part",choices=("discover","inventory"),required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    if a.part=="discover":result=discovery()
    else:
        result={"experiment":"JANUS-LOGOS-001","phase":"R1.2","source":"NIST_STDR_OBSERVED_NONLINEAR_MEASUREMENTS",
                "datasets":{name:{"counts":[len(split(name)[k]) for k in ("train","validation","test")],
                                  "dataset_sha256":hashlib.sha256((HERE/FILE[name]).read_bytes()).hexdigest()}
                            for name in NAMES}}
    Path(a.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"part":a.part,"cases":[s["id"] for s in result["cases"]] if "cases" in result else list(result["datasets"])}))
if __name__=="__main__":main()
