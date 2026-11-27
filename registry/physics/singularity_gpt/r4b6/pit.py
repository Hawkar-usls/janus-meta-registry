"""Unconditional paired PIT diagnostics; no calibration fitted."""
import ast,json,sys,hashlib
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from scipy.special import ndtr
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE.parent/"r4b2"),str(HERE.parent/"r4b3")]
import rivals
from generator import cases
P=json.loads((HERE/"protocol.json").read_text())
parent=json.loads((HERE.parent/"r4b4"/"protocol.json").read_text())["generator"]
cfg={**parent,"new_seed":parent["seed"]}
OUT=Path("r4b6-output");OUT.mkdir(exist_ok=True)
path=HERE.parent/"r4b3"/"phase.py";node=next(x for x in ast.parse(path.read_text()).body if isinstance(x,ast.FunctionDef) and x.name=="phase_ci")
env={"np":np,"least_squares":least_squares};exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),"exec"),env)
rows=[]
for c in cases(cfg):
    if c["subtype"]!="positive" or c["level"]==0:continue
    s,t,y=c["s"],c["t"],c["raw"]/c["envelope"];u=s/s[-1];m=int(.55*len(y))
    q,w=rivals.fit(u,(t-t[0])/(t[-1]-t[0]),y[:m],"DSS")
    ci=env["phase_ci"](s,y,float(q[0]));se=ci["se"];z=ci["drift"]/se if se>0 else None
    # Oracle signal residual is used for diagnostic scoring only; detector never sees it.
    # Fit constant log frequency on complete signal to measure coherent residual spectrum.
    q2,w2=rivals.fit(u,(t-t[0])/(t[-1]-t[0]),y,"DSS")
    resid=y-rivals.basis(u,(t-t[0])/(t[-1]-t[0]),"DSS",q2)@w2
    rr=np.interp(np.linspace(0,1,len(y)),u,resid);power=abs(np.fft.rfft((rr-rr.mean())*np.hanning(len(rr))))**2
    concentration=float(np.max(power[1:])/max(np.sum(power[1:]),1e-30))
    rows.append({"kind":c["kind"],"level":c["level"],"i":c["i"],"drift":ci["drift"],"se":se,"z":z,"pit":float(ndtr(-z)) if z is not None else None,"coverage":ci["ci95"][0]<=0<=ci["ci95"][1],"residual_peak_power_fraction":concentration})
    if len(rows)==600:break
summary=[]
for k,l in sorted({(r["kind"],r["level"]) for r in rows}):
    a=[r for r in rows if (r["kind"],r["level"])==(k,l)];v=np.array([r["pit"] for r in a if r["pit"] is not None]);z=np.array([r["z"] for r in a if r["z"] is not None]);counts,_=np.histogram(v,bins=np.linspace(0,1,21));pr=np.arange(1,100)/100
    summary.append({"kind":k,"level":l,"n":len(a),"coverage":sum(r["coverage"] for r in a),"pit_mean":float(v.mean()),"pit_variance":float(v.var()),"pit_histogram":counts.tolist(),"qq_uniform":pr.tolist(),"qq_empirical":np.quantile(v,pr).tolist(),"z_mean":float(z.mean()),"z_sd":float(z.std()),"median_residual_peak_power_fraction":float(np.median([r["residual_peak_power_fraction"] for r in a]))})
paired=[]
for k in sorted({r["kind"] for r in rows}):
    a={r["i"]:r for r in rows if r["kind"]==k and r["level"]==.001};b={r["i"]:r for r in rows if r["kind"]==k and r["level"]==.01}
    dr=[b[i]["drift"]/a[i]["drift"] for i in a if abs(a[i]["drift"])>1e-12];sr=[b[i]["se"]/a[i]["se"] for i in a if a[i]["se"]>0];dz=[abs(b[i]["z"]-a[i]["z"]) for i in a if a[i]["z"] is not None and b[i]["z"] is not None]
    paired.append({"kind":k,"median_drift_scale":float(np.median(dr)),"median_se_scale":float(np.median(sr)),"median_abs_z_change":float(np.median(dz)),"same_coverage_decision":sum(a[i]["coverage"]==b[i]["coverage"] for i in a)})
result={"mode":"pit","summary":summary,"paired":paired,"scientific_hold":True,"physical_use_authorized":False,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest(),"limitations":["Fixed true zero drift confidence-distribution diagnostic, not predictive PIT.","Same latent waveform and noise realization across amplitudes; not independent repeated exams.","Spectral residual concentration and standardized errors diagnose misspecification but cannot isolate it causally."]}
for name,data in (("trials.json",rows),("result.json",result)):(OUT/name).write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")
print("R4B6_RESULT",json.dumps({**result,"summary":[{k:v for k,v in x.items() if not k.startswith("qq_")} for x in summary]},allow_nan=False),flush=True)
