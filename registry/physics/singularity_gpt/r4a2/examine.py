"""R4A2 fixed point and classifier shadow audit; no early-stop authority."""
import json,hashlib,io,zipfile
from pathlib import Path
import numpy as np
from diagnostic_lib import run
HERE=Path(__file__).resolve().parent;OUT=Path("r4a2-output");OUT.mkdir(exist_ok=True)
P=json.loads((HERE/"protocol.json").read_text())
def write(n,d): (OUT/n).write_text(json.dumps(d,indent=2,allow_nan=False)+"\n")
b=Path("r4a.zip").read_bytes();assert hashlib.sha256(b).hexdigest()==P["source_zip_sha256"]
with zipfile.ZipFile(io.BytesIO(b)) as z:
    old=json.loads(z.read("result.json"))
    old_data=np.load(io.BytesIO(z.read("traces.npz")),allow_pickle=False)
    traces={k:old_data[k] for k in old_data.files}
rows={r["key"]:r for r in old["fixed_cases"]}
rows.update(held_original=old["held_original"],held_extended=old["held_extended"])
new={}
for key in ("fixed_case","noncritical_control","held_confirmation"):
    p=P[key];r,x=run(p["A"],p["r0"],p["width"],p["R"],p["n"],p.get("checkpoints",[p.get("t_end",16)]))
    traces[key]=x;rows[key]=r;new[key]=r
    print("NEW_CASE",json.dumps({"key":key,**r}),flush=True)
    write("new_cases.json",new)
# Fixed criterion frozen before examination, evaluate in shadow mode on full traces.
def shadow(x):
    cfg=P["early_indicator"];t=x[:,0];c=x[:,6];m=x[:,8]
    slope=lambda u,v:float(np.polyfit(u,v,1)[0])
    for i in np.where((t>=cfg["minimum_t"])&(c<cfg["max_current_compactness"])&(m<cfg["max_inner_mass_fraction"]))[0]:
        j=np.searchsorted(t,t[i]-cfg["window"])
        if i-j<8 or t[i]-t[j]<cfg["window"]-.02:continue
        k=np.searchsorted(t,t[i]-cfg["window"]/2)
        if k-j<3 or i-k<3:continue
        if c[i]>=c[j] or m[i]>=m[j]:continue
        if not all(slope(t[l:r+1],y[l:r+1])<0 for y in (c,m) for l,r in ((j,k),(k,i))):continue
        drift=float(np.max(abs(x[:i+1,7]-x[0,7]))/x[0,7])
        if drift>=P["mass_relative_budget"]:continue
        return {"candidate_t":float(t[i]),"candidate_c":float(c[i]),"candidate_inner_mass":float(m[i]),"mass_drift_at_candidate":drift}
    return None
shadow_rows=[]
for k,x in traces.items():
    if k not in rows:continue
    r=rows[k];s=shadow(x);final=r["status"]
    shadow_rows.append({"key":k,"final_class":final,"historical_or_new": "new" if k in new else "historical","candidate":s,"false_positive_near_trapping":bool(s and final=="NEAR_TRAPPING_PROXY"),"unresolved_candidate":bool(s and final=="UNRESOLVED"),"potential_saved_time":float(x[-1,0]-s["candidate_t"]) if s else None})
# Compare the same initial amplitude over shared central proper time.
pair=[]
keys=["fixed_0.11484375_1536","fixed_0.11484375_3072","fixed_case"]
for a,b in zip(keys,keys[1:]):
    x,y=traces[a],traces[b];h1=rows[a]["h"];h2=rows[b]["h"]
    t=np.linspace(0,min(x[-1,1],y[-1,1]),4096)
    v=np.interp(t,x[:,1],x[:,2]);w=np.interp(t,y[:,1],y[:,2])
    cx=np.interp(t,x[:,1],x[:,4]);cy=np.interp(t,y[:,1],y[:,4])
    mask=(cx*h1*h1<=1/64)&(cy*h2*h2<=1/64)
    rel=lambda u,v:float(np.linalg.norm(u-v)/max(np.linalg.norm(v),1e-30))
    pair.append({"coarse":a,"fine":b,"common_proper_time":float(t[-1]),"relative_l2":rel(v,w),"jointly_resolved_fraction":float(mask.mean()),"resolved_relative_l2":rel(v[mask],w[mask]) if mask.any() else None})
# Reuse R3B peak criterion as an exploratory negative-control test on regularized
# uniform proper-time samples. Block shuffle residuals preserves short correlations.
def echo(t,v,h):
    mag=abs(v);curv=8*np.pi*v*v
    peaks=np.where((mag[1:-1]>mag[:-2])&(mag[1:-1]>=mag[2:]))[0]+1
    peaks=[i for i in peaks if mag[i]>max(mag)*1e-4 and curv[i]>0 and 1/np.sqrt(curv[i])>=8*h]
    for k in range(len(peaks)-4):
        ii=peaks[k:k+5];amp=mag[ii];sg=np.sign(v[ii]);dt=np.diff(t[ii])
        if not (np.all(sg[1:]!=sg[:-1]) and np.all(amp[1:]>1.1*amp[:-1]) and np.all(dt>0) and np.all(dt[1:]<dt[:-1])):continue
        ds=2*np.log(dt[:-1]/dt[1:]);med=np.median(ds)
        if med>0 and np.max(abs(ds-med))/med<=.2:return True
    return False
rng=np.random.default_rng(P["echo_negative_control"]["seed"]);null=[]
for key in ("fixed_case","noncritical_control","held_confirmation"):
    x=traces[key];h=rows[key]["h"]
    # fixed 4096-point proper-time grid, matched preprocessing for original and surrogates
    t=np.linspace(x[0,1],x[-1,1],4096);v=np.interp(t,x[:,1],x[:,2])
    trend=np.convolve(np.pad(v,(32,32),mode="edge"),np.ones(65)/65,mode="valid")
    blocks=(v-trend).reshape(-1,16)
    hits=sum(echo(t,trend+blocks[rng.permutation(len(blocks))].reshape(-1),h) for _ in range(199))
    null.append({"key":key,"raw_trace_rule_hit":bool(echo(x[:,1],x[:,2],h)),"resampled_rule_hit":bool(echo(t,v,h)),"surrogate_hits":int(hits),"surrogates":199,"smoothed_empirical_hit_rate":float((hits+1)/200)})
report={"status":"R4A2_SCHEME_DIAGNOSTICS__SCIENTIFIC_HOLD","new_cases":new,"matched_pairs":pair,"mass_budget_pass":{k:bool(r["checkpoints"][-1]["mass_drift"]<P["mass_relative_budget"]) for k,r in new.items()},"shadow_classifier":shadow_rows,"shadow_false_positives":sum(r["false_positive_near_trapping"] for r in shadow_rows),"early_stop_authorized":False,"null_controls":null,"reference_period_used":False,"amr_implemented":False,"third_family_tested":False,"production_changed":False,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest()}
write("result.json",report);np.savez_compressed(OUT/"new_traces.npz",**{k:traces[k] for k in new})
print("R4A2_RESULT",json.dumps(report),flush=True)
