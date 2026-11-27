import json,hashlib,zipfile,io
from pathlib import Path
import numpy as np
OUT=Path("r3c-audit");OUT.mkdir(exist_ok=True)
b=Path("echo.zip").read_bytes()
assert hashlib.sha256(b).hexdigest()=="275761ae314bde450c6dd5f6dd6f2a37f27b8286d8f09e608d0d8708d21e71c9"
with zipfile.ZipFile(io.BytesIO(b)) as z:
    cases=json.loads(z.read("echo_cases.json"));r=json.loads(z.read("echo_result.json"));data=np.load(io.BytesIO(z.read("echo_traces.npz")),allow_pickle=False)
rows=[]
for e in r["estimates"]:
    fam,n=e["family"],e["n"]
    cc=[c for c in cases if c["family"]==fam and c["n"]==n]
    mid=[c for c in cc if "_mid" in c["key"]]
    last=mid[-1] if mid else None
    reason="BUDGET_EXHAUSTED" if len(mid)==10 else ("MASS_OR_INVALID_GATE" if last and last.get("mass_drift",1)>=.05 else "UNRESOLVED_OR_NUMERICAL_CLASS")
    low=e["proxy_bracket"][0];high=e["proxy_bracket"][1]
    trace=next((c for c in reversed(cc) if c["A"]==low and c["class"]=="DISPERSAL_PROXY"),None)
    diag={}
    if trace:
        x=data[trace["key"]];v=x[:,2];mag=abs(v);t=x[:,1];h=30/n
        raw=np.where((mag[1:-1]>mag[:-2])&(mag[1:-1]>=mag[2:]))[0]+1
        resolved=[int(i) for i in raw if mag[i]>mag.max()*1e-4 and x[i,3]>0 and 1/np.sqrt(x[i,3])>=8*h]
        counts={"windows":0,"alternating":0,"growth":0,"shrinking":0,"stable_ratio":0}
        for k in range(len(resolved)-4):
            ii=resolved[k:k+5];amp=mag[ii];sg=np.sign(v[ii]);dt=np.diff(t[ii])
            counts["windows"]+=1
            if not np.all(sg[1:]!=sg[:-1]):continue
            counts["alternating"]+=1
            if not np.all(amp[1:]>1.1*amp[:-1]):continue
            counts["growth"]+=1
            if not (np.all(dt>0) and np.all(dt[1:]<dt[:-1])):continue
            counts["shrinking"]+=1
            ds=2*np.log(dt[:-1]/dt[1:]);med=np.median(ds)
            if med>0 and np.max(abs(ds-med))/med<=.2:counts["stable_ratio"]+=1
        diag={"raw_extrema":len(raw),"resolved_extrema":len(resolved),"gate_funnel":counts,"minimum_curvature_length_over_h":float(np.min(1/np.sqrt(np.maximum(x[:,3],1e-300)))/h),"trace_end_t":float(x[-1,0]),"trace_end_proper":float(x[-1,1]),"final_compactness":float(x[-1,4])}
    rows.append({"family":fam,"n":n,"bracket":e["proxy_bracket"],"width":high-low,"midpoint":(low+high)/2,"bisection_attempts":len(mid),"last_attempt":last,"stop_reason":reason,"echo_funnel":diag})
report={"status":"READ_ONLY_FROZEN_ARTIFACT_AUDIT","source_artifact_sha256":hashlib.sha256(b).hexdigest(),"rows":rows,"solver_changed":False,"reference_period_used":False,"scientific_hold":True}
(OUT/"audit.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
print("R3C_AUDIT",json.dumps(report,allow_nan=False))
