"""Frozen NIST observed measurements and group-disjoint R1.3 splits.

Files are byte-for-byte Git blobs from ceres-solver/ceres-solver/data/nist/,
also available at NIST ITL StRD nonlinear least squares datasets.
Only (x,y) scientific observations enter discovery. Original NIST headers
contain historical certified formulas; these are never supplied to proposer.
"""
import argparse, hashlib, json, re
from pathlib import Path
DIR=Path(__file__).resolve().parent/"data_r13"
SPECS={
"HAHN1":("Hahn1.dat",236,235,(142,47,47),"f3069d70abb3449eae006d330aa3f4a2506d1af4"),
"THURBER":("Thurber.dat",37,37,(21,8,8),"6d72fd93cfa072f53b155d456b2f50b16e686852"),
"BENNETT5":("Bennett5.dat",154,154,(92,31,31),"eba218a14a72c22ae35aa225f11054517bdd92dd")
}
NAMES=tuple(SPECS)
PAIR=re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)[Ee][+-]?\d+)\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)[Ee][+-]?\d+)\s*$")

def observed(name):
    file,n,uni,counts,sha=SPECS[name]
    raw=(DIR/file).read_bytes()
    blob=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    if blob!=sha:raise ValueError("NIST original provenance SHA mismatch "+name)
    rows=[]
    for line in raw.decode("utf-8").splitlines():
        m=PAIR.fullmatch(line)
        if m:rows.append((float(m[2]),float(m[1])))
    if len(rows)!=n or len(set(x for x,y in rows))!=uni:raise ValueError("Observed source dimensions changed")
    return rows

def split(name):
    raw=observed(name)
    unique=sorted({x for x,y in raw})
    xmin=unique[0];xmax=unique[-1]
    groups={x:("test" if i%5==0 else "validation" if i%5==1 else "train") for i,x in enumerate(unique)}
    out={"train":[],"validation":[],"test":[]}
    for x,y in raw:
        z=(x-xmin)/(xmax-xmin)
        out[groups[x]].append([z,y])
    if tuple(len(out[s]) for s in ("train","validation","test"))!=SPECS[name][3]:
        raise ValueError("Frozen group sizes changed")
    a,b,c=[{x for x,y in out[k]} for k in ("train","validation","test")]
    if a&b or a&c or b&c:raise ValueError("Group leakage")
    return out

def discovery_input():
    cases=[]
    for name in NAMES:
        d=split(name)
        cases.append({"id":name,"train":d["train"],"validation":d["validation"]})
    for name in NAMES:
        d=split(name)
        v=d["validation"]
        shift=len(v)//2
        cycled=[v[(i+shift)%len(v)][1] for i in range(len(v))]
        cases.append({"id":name+"_SHUFFLED_VALIDATION","train":d["train"],
                      "validation":[[r[0],label] for r,label in zip(v,cycled)]})
    return {"experiment":"JANUS-LOGOS-001","phase":"R1.3",
            "source":"NIST_STRD_NEW_REAL_INSTRUMENT_OBSERVATIONS","cases":cases}

def canonical_sha(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    a=p.parse_args()
    r=discovery_input()
    Path(a.out).write_text(json.dumps(r,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"cases":[x["id"] for x in r["cases"]],"source_sha":canonical_sha(r)}))
if __name__=="__main__":main()
