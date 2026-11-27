import json,hashlib,sys
from pathlib import Path
from collections import Counter
P=json.loads(Path(__file__).with_name("protocol.json").read_text())
def load(folder):
    a=list(Path(folder).rglob("trials.json"));assert len(a)==1
    b=a[0].read_bytes();rows=json.loads(b)
    return rows,hashlib.sha256(b).hexdigest()
old,ho=load(sys.argv[1]);new,hn=load(sys.argv[2])
def key(x):return tuple(x[k] for k in P["key"])
a={key(x):x for x in old};b={key(x):x for x in new};assert len(a)==len(b)==P["expected_n"] and a.keys()==b.keys()
counts=Counter();sub={k:Counter() for k in ("positive","near_dss_chirp","stationary")};examples={};patterns=Counter()
for k,x in a.items():
    y=b[k];diff=[]
    for field in P["fields"]:
        if field not in x or field not in y:
            counts["missing:"+field]+=1;continue
        if x[field]!=y[field]:
            counts[field]+=1;sub[k[0]][field]+=1;diff.append(field)
            if field not in examples:examples[field]={"key":k,"old":x[field],"new":y[field]}
    patterns["|".join(diff) or "identical"]+=1
d=dict(id=P["id"],source_sha256={"original":ho,"replay":hn},n=len(a),mismatch_counts=dict(counts),by_subtype={k:dict(v) for k,v in sub.items()},patterns=dict(patterns),examples=examples,scientific_hold=True,status="LOCALIZATION_COMPLETE__REPLAY_HOLD")
out=Path("r4b10b1-output");out.mkdir(exist_ok=True);(out/"result.json").write_text(json.dumps(d,indent=2)+"\n")
print("R4B10B1_RESULT",json.dumps(d),flush=True)
