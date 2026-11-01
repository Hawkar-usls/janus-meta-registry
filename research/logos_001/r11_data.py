"""NIST StRD observed calibration measurements, R1.1 fixed splits.

Sources, both 'Observed Data':
https://www.itl.nist.gov/div898/strd/lls/data/LINKS/DATA/Pontius.dat
https://www.itl.nist.gov/div898/strd/lls/data/LINKS/DATA/Norris.dat
Rows are in published source order, (response y, predictor x).
NIST attribution and usage caveats: data/JANUS-LOGOS-001-R11-PREREG-v1.0.json
No published certified regression equation is provided to the discoverer.
"""
import argparse
import hashlib
import json
from pathlib import Path

PONTIUS = [
 (.11019,150000),(.21956,300000),(.32949,450000),(.43899,600000),
 (.54803,750000),(.65694,900000),(.76562,1050000),(.87487,1200000),
 (.98292,1350000),(1.09146,1500000),(1.20001,1650000),(1.30822,1800000),
 (1.41599,1950000),(1.52399,2100000),(1.63194,2250000),(1.73947,2400000),
 (1.84646,2550000),(1.95392,2700000),(2.06128,2850000),(2.16844,3000000),
 (.11052,150000),(.22018,300000),(.32939,450000),(.43886,600000),
 (.54798,750000),(.65739,900000),(.76596,1050000),(.87474,1200000),
 (.98300,1350000),(1.09150,1500000),(1.20004,1650000),(1.30818,1800000),
 (1.41613,1950000),(1.52408,2100000),(1.63159,2250000),(1.73965,2400000),
 (1.84696,2550000),(1.95445,2700000),(2.06177,2850000),(2.16829,3000000)]
NORRIS = [
 (0.1,0.2),(338.8,337.4),(118.1,118.2),(888.0,884.6),(9.2,10.1),
 (228.1,226.5),(668.5,666.3),(998.5,996.3),(449.1,448.6),
 (778.9,777.0),(559.2,558.2),(0.3,0.4),(0.1,0.6),
 (778.1,775.5),(668.8,666.9),(339.3,338.0),(448.9,447.5),
 (10.8,11.6),(557.7,556.0),(228.3,228.1),(998.0,995.8),
 (888.8,887.6),(119.6,120.2),(0.3,0.3),(0.6,0.3),
 (557.6,556.8),(339.3,339.1),(888.0,887.2),(998.5,999.0),
 (778.9,779.0),(10.2,11.1),(117.6,118.3),(228.9,229.2),
 (668.4,669.1),(449.2,448.9),(0.2,0.5)]
assert len(PONTIUS)==40 and len(NORRIS)==36
assert len(set(x for y,x in PONTIUS))==20

def normalized(pair, name):
    y,x=pair
    return [x/(3000000.0 if name=="PONTIUS" else 1000.0),float(y)]

def split(name):
    values=PONTIUS if name=="PONTIUS" else NORRIS
    pools={"train":[],"validation":[],"test":[]}
    unique_x=sorted(set(x for y,x in PONTIUS))
    for i,pair in enumerate(values):
        slot = (unique_x.index(pair[1]) if name=="PONTIUS" else i)%5
        dest="test" if slot==0 else ("validation" if slot==1 else "train")
        pools[dest].append(normalized(pair,name))
    return pools

def discovery():
    datasets=[]
    for name in ("PONTIUS","NORRIS"):
        d=split(name)
        datasets.append({"id":name,"train":d["train"],"validation":d["validation"]})
    # The negative control intentionally breaks the x/y pairing on VALIDATION,
    # without changing the training observations or their genuine provenance.
    for name in ("PONTIUS","NORRIS"):
        d=split(name)
        vals=d["validation"]
        shifted=[vals[(i+3)%len(vals)][1] for i in range(len(vals))]
        datasets.append({"id":name+"_SHUFFLED_VAL",
                         "train":d["train"],
                         "validation":[[p[0],y] for p,y in zip(vals,shifted)]})
    return {"experiment":"JANUS-LOGOS-001","phase":"R1.1",
            "source":"NIST_STRD_OBSERVED_REAL_MEASUREMENTS",
            "datasets":datasets}

def sha256(obj):
    raw=json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--part",choices=("discover","witness"),required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    d=discovery() if a.part=="discover" else {
        "experiment":"JANUS-LOGOS-001","phase":"R1.1",
        "source":"NIST_STRD_OBSERVED_REAL_MEASUREMENTS",
        "all_rows_sha256":sha256({"PONTIUS":PONTIUS,"NORRIS":NORRIS}),
        "datasets":{name:split(name) for name in ("PONTIUS","NORRIS")}}
    Path(a.out).write_text(json.dumps(d,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"part":a.part,"datasets":list(d["datasets"]) if isinstance(d["datasets"],dict) else [x["id"] for x in d["datasets"]]}))

if __name__=="__main__":main()
