"""Oracle tangent decomposition of narrowband noise, diagnostic not calibration."""
import ast,json,hashlib,sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE.parent/"r4b3"),str(HERE.parent/"r4b2")]
from generator import cases
import rivals
P=json.loads((HERE/"protocol.json").read_text())
parent=json.loads((HERE.parent/"r4b4"/"protocol.json").read_text())["generator"]
cfg={**parent,"new_seed":parent["seed"]};OUT=Path("r4b7-output");OUT.mkdir(exist_ok=True)
path=HERE.parent/"r4b3"/"phase.py";node=next(x for x in ast.parse(path.read_text()).body if isinstance(x,ast.FunctionDef) and x.name=="phase_ci")
env={"np":np,"least_squares":least_squares};exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),"exec"),env)
clean={};rows=[]
for c in cases(cfg):
    if c["subtype"]!="positive" or c["kind"]!="narrowband":continue
    s,t,y=c["s"],c["t"],c["raw"]/c["envelope"];u=s/s[-1];f=s[-1]/c["truth_period"]
    if c["level"]==0:
        clean[c["i"]]=y.copy();continue
    if c["level"] not in (.001,.01):continue
    base=clean[c["i"]];noise=y-base;a=2*np.pi*f*u
    B=np.column_stack((np.ones(len(u)),np.sin(a),np.cos(a)))
    w=np.linalg.lstsq(B,base,rcond=None)[0];der=w[1]*np.cos(a)-w[2]*np.sin(a)
    nuisance=np.column_stack((B,2*np.pi*u*der));Q,_=np.linalg.qr(nuisance);v=np.pi*u*u*der;v-=Q@(Q.T@v);v/=np.linalg.norm(v)
    Qall=np.column_stack((Q,v));parallel=Qall@(Qall.T@noise);orth=noise-parallel;phase_only=v*np.dot(v,noise)
    for name,z in (("original",noise),("parallel",parallel),("orthogonal",orth),("chirp_tangent_only",phase_only)):
        ci=env["phase_ci"](s,base+z,f);se=ci["se"];std=ci["drift"]/se if se>0 else None
        rows.append({"i":c["i"],"level":c["level"],"component":name,"energy_fraction":float(np.dot(z,z)/max(np.dot(noise,noise),1e-30)),"drift":ci["drift"],"se":se,"z":std,"coverage":ci["ci95"][0]<=0<=ci["ci95"][1],"fit_success":ci["fit_success"]})
    if len(rows)==800:break
summary=[]
for level,comp in sorted({(r["level"],r["component"]) for r in rows}):
    a=[r for r in rows if (r["level"],r["component"])==(level,comp)];z=[r["z"] for r in a if r["z"] is not None]
    summary.append({"level":level,"component":comp,"n":len(a),"coverage":sum(r["coverage"] for r in a),"median_energy_fraction":float(np.median([r["energy_fraction"] for r in a])),"mean_drift":float(np.mean([r["drift"] for r in a])),"sd_drift":float(np.std([r["drift"] for r in a])),"median_se":float(np.median([r["se"] for r in a])),"z_mean":float(np.mean(z)) if z else None,"z_sd":float(np.std(z)) if z else None})
result={"mode":"projection","summary":summary,"n":len(rows),"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest(),"scientific_hold":True,"physical_use_authorized":False,"limitations":["Oracle true log time, envelope, frequency and noiseless signal used solely for synthetic diagnostic.","Projected noise components are not independent draws and have different energy; no renormalization.","Removing tangent projection suppresses first-order drift by construction; cannot prove model misspecification or covariance error alone."]}
for name,obj in (("trials.json",rows),("result.json",result)):(OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
print("R4B7_RESULT",json.dumps(result,allow_nan=False),flush=True)
