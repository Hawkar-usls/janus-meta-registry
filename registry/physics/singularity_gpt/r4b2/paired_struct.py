"""Paired replay of R4B0 detector with same waveform and identical innovation."""
import json,sys,hashlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"r4b0"))
from echo import estimate
P=json.loads((HERE/"protocol.json").read_text());D=P["detector"]
OUT=Path("r4b2-output");OUT.mkdir(exist_ok=True)
rng=np.random.default_rng(D["seed"]+1);rows=[]
for i in range(100):
    period=float(rng.uniform(1.2,5.6));s=np.linspace(0,5*period,4096);u=s/s[-1];t=-np.exp(-s);env=np.exp(s-s[-1])
    base=np.sin(2*np.pi*s/period+rng.uniform(0,2*np.pi));iid=rng.standard_normal(len(s));ar=iid.copy()
    for j in range(1,len(s)):ar[j]=.94*ar[j-1]+np.sqrt(1-.94**2)*ar[j]
    st=.65*np.sin(2*np.pi*(19*u+7*u*u)+rng.uniform(0,2*np.pi))+.35*iid
    for kind,z in (("iid",iid),("ar1",ar),("structured",st)):
        for level in D["noise_levels"]:
            v=env*(base+level*z/np.std(z));pred,_=estimate(t,v)
            rows.append({"i":i,"kind":kind,"level":level,"truth":period,"pred":pred,"correct":bool(pred is not None and abs(pred-period)/period<=.05)})
summary=[]
for level in D["noise_levels"]:
    a={r["i"]:r["correct"] for r in rows if r["level"]==level and r["kind"]=="iid"}
    for kind in D["noise_types"]:
        b={r["i"]:r["correct"] for r in rows if r["level"]==level and r["kind"]==kind}
        summary.append({"level":level,"kind":kind,"correct":sum(b.values()),"n":len(b),"wins_vs_iid":sum(b[i] and not a[i] for i in b),"losses_vs_iid":sum(a[i] and not b[i] for i in b)})
result={"summary":summary,"paired_original_detector":True,"physical_noise_calibrated":False,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest()}
(OUT/"result.json").write_text(json.dumps(result,indent=2)+"\n");(OUT/"trials.json").write_text(json.dumps(rows,indent=2)+"\n")
print("R4B2_STRUCT_RESULT",json.dumps(result),flush=True)
