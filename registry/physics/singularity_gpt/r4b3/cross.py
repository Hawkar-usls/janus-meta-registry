"""Two frozen detectors on both regenerated historical banks, no calibration."""
import sys,json,hashlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE.parent/"r4b0"),str(HERE.parent/"r4b2")]
import echo as old
import rivals as new
OUT=Path("r4b3-output");OUT.mkdir(exist_ok=True)
mode=sys.argv[1]
P=json.loads((HERE/"protocol.json").read_text())
def write(n,x): (OUT/n).write_text(json.dumps(x,indent=2,allow_nan=False)+"\n")
def digest(t,v):return hashlib.sha256(np.asarray(np.column_stack((t,v)),dtype="<f8").tobytes()).hexdigest()
rows=[]
if mode=="r4b0":
    cfg=old.P["synthetic"];rng=np.random.default_rng(cfg["seed"])
    for period in cfg["clean_periods"]:old.signal(rng,period,"iid",0,True)
    for kind in cfg["noise_types"]:
        for level in cfg["noise_levels"]:
            for positive in (True,False):
                for i in range(cfg["n_per_noise_type_level_class"]):
                    period=float(rng.uniform(*cfg["positive_period_range"]))
                    t,v=old.signal(rng,period,kind,level,positive);s=-np.log(-t)
                    pa,_=old.estimate(t,v);pb,*_=new.detect(s,t,v/np.exp(s-s[-1]))
                    rows.append({"kind":kind,"level":level,"subtype":"positive" if positive else "mixed_negative","i":i,"truth":period if positive else None,"old":pa,"new":pb,"input_sha256":digest(t,v)})
elif mode=="r4b2":
    orig=new.detect;captured=[]
    def wrapped(s,t,y):
        v=y*np.exp(s-s[-1]);pa,_=old.estimate(t,v);ret=orig(s,t,y)
        captured.append((pa,digest(t,v)))
        return ret
    new.detect=wrapped;new.write=lambda *x:None
    rr=new.bank(new.D["seed"])
    assert len(rr)==len(captured)
    for r,(pa,h) in zip(rr,captured):
        rows.append({"kind":r["noise"],"level":r["level"],"subtype":r["subtype"],"i":r["i"],"truth":r["truth"],"old":pa,"new":r["estimate"],"input_sha256":h})
else:raise ValueError(mode)
def summarize(rr,det):
    a=[r for r in rr if r["subtype"]=="positive"];b=[r for r in rr if r["subtype"]!="positive"]
    return {"positive_correct":sum(r[det] is not None and abs(r[det]-r["truth"])/r["truth"]<=.05 for r in a),"positive_n":len(a),"negative_hits":sum(r[det] is not None for r in b),"negative_n":len(b)}
summary={}
for det in ("old","new"):
    summary[det]={"all":summarize(rows,det),"subgroups":[{"kind":k,"level":l,"subtype":s,**summarize([r for r in rows if r["kind"]==k and r["level"]==l and r["subtype"]==s],det)} for k,l,s in sorted({(r["kind"],r["level"],r["subtype"]) for r in rows})]}
result={"mode":mode,"summary":summary,"same_raw_waveforms":True,"information_equal":False,"information_asymmetry":"New detector receives oracle log-coordinate and envelope-normalized data; old detector receives original raw waveform. Algorithm comparison conditional on different inputs, not a fair equal-information deployment comparison.","historical_reproduction_check":{"old_on_r4b0_expected":[588,253],"new_on_r4b2_expected":[599,49]},"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest()}
expected=(588,253) if mode=="r4b0" else (599,49)
actual=summary["old" if mode=="r4b0" else "new"]["all"]
result["historical_counts_match"]=bool((actual["positive_correct"],actual["negative_hits"])==expected)
write("trials.json",rows);write("result.json",result)
print("R4B3_CROSS_RESULT",json.dumps(result,allow_nan=False),flush=True)
