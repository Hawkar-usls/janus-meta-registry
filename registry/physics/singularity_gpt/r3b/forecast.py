#!/usr/bin/env python3
"""Initial-state only forecast; labels from frozen R3A, no echo target."""
import json,hashlib,zipfile
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
torch.set_num_threads(2)
HERE=Path(__file__).resolve().parent;OUT=Path("singularity-r3b-output");OUT.mkdir(exist_ok=True)
P=json.loads((HERE/"protocol.json").read_text())
blob=Path("r3a.zip").read_bytes()
assert hashlib.sha256(blob).hexdigest()==P["parent_zip_sha256"]
with zipfile.ZipFile("r3a.zip") as z:
    for name in ("result.json","cases.json","trajectories.npz"):
        (OUT/("parent-"+name)).write_bytes(z.read(name))
R=json.loads((OUT/"parent-result.json").read_text());C=json.loads((OUT/"parent-cases.json").read_text())
assert R["controls_pass"]
D=np.load(OUT/"parent-trajectories.npz",allow_pickle=False)
T=np.array([1.,2.,4.,6.]);tr=[];te=[]
for label in R["resolution_agreement_mass_gated_labels"]:
    fam,A=label["family"],label["amplitude"]
    rr=[c for c in C if c["family"]==fam and c["amplitude"]==A and c["n"] in (768,1536)]
    if len(rr)!=2 or not all(c.get("momentum_relative_l2",1)<.02 for c in rr):continue
    key=f"{fam}_{A}_1536"
    h=D[key+"_history"];f=D[key+"_fields"]
    assert h[-1,0]>=T[-1] and np.isfinite(f).all()
    def at(t):
        j=np.searchsorted(h[:,0],t);j=min(max(j,1),len(h)-1)
        w=(t-h[j-1,0])/(h[j,0]-h[j-1,0])
        return f[j-1]*(1-w)+f[j]*w
    r={"key":key,"initial":f[0,:,:4],"mass":float(h[0,5]),"targets":np.stack([at(t) for t in T]),"train_targets":np.stack([at(t) for t in np.arange(.25,6.01,.25)]) if fam=="train_shell" else None}
    (tr if fam=="train_shell" else te).append(r)
assert len(tr)>=6 and len(te)>=6
def write(n,d): (OUT/n).write_text(json.dumps(d,indent=2,allow_nan=False)+"\n")
def sha(x):return hashlib.sha256(np.ascontiguousarray(x).tobytes()).hexdigest()
write("forecast_precommit.json",{"train":[{"key":r["key"],"input_sha":sha(r["initial"]),"target_sha":sha(r["train_targets"])} for r in tr],"test":[{"key":r["key"],"input_sha":sha(r["initial"]),"target_sha":sha(r["targets"])} for r in te],"horizons":T.tolist(),"artifact_sha256":P["parent_zip_sha256"]})
# Fit normalization on train profiles only; scale changes in prediction targets.
train_y=np.stack([r["train_targets"][:,:,:4] for r in tr])
scale=np.maximum(np.std(train_y,axis=(0,1,2)),1e-6)
rad=np.linspace(.1,12,64);ts=np.arange(.25,6.01,.25)
def tokens(initial,t):
    return np.concatenate([initial/scale,rad[:,None]/12,np.full((64,1),t/6)],axis=1)
x=np.stack([tokens(r["initial"],t) for r in tr for t in ts])
y=np.concatenate([r["train_targets"][:,:,:4]/scale for r in tr])
xt=np.stack([tokens(r["initial"],t) for r in te for t in T])
truth=np.stack([r["targets"] for r in te])
def derive(pred):
    p,q,a,alpha=np.moveaxis(pred,-1,0)
    valid=np.isfinite(pred).all() and (a>0).all() and (alpha>0).all()
    if not valid:return None
    return np.stack([p,q,a,alpha,1-a**-2,8*np.pi*(p*p-q*q)/a**2],axis=-1)
def score(pred):
    z=derive(pred)
    err=np.mean(abs(pred-truth[...,:4]),axis=(1,2))/scale
    return {"mean_normalized_mae":float(err.mean()),"trajectory_mae":err.mean(1).tolist(),"channel_mae":np.mean(abs(pred-truth[...,:4]),axis=(0,1,2)).tolist(),"geometry_valid":z is not None,"compactness_mae":float(np.mean(abs(z[...,4]-truth[...,4]))) if z is not None else None,"ricci_mae":float(np.mean(abs(z[...,5]-truth[...,5]))) if z is not None else None}
persistence=np.stack([np.repeat(r["initial"][None],len(T),axis=0) for r in te])
nearest=np.stack([min(tr,key=lambda q:np.mean(((q["initial"]-r["initial"])/scale)**2))["targets"][...,:4] for r in te])
ordered=sorted(tr,key=lambda r:r["mass"]);m=np.array([r["mass"] for r in ordered]);v=np.stack([r["targets"][...,:4] for r in ordered])
def interp_mass(q):
    k=np.searchsorted(m,q);k=min(max(k,1),len(m)-1);w=np.clip((q-m[k-1])/(m[k]-m[k-1]),0,1)
    return v[k-1]*(1-w)+v[k]*w
interpolation=np.stack([interp_mass(r["mass"]) for r in te])
baselines={k:score(v) for k,v in (("persistence",persistence),("nearest_profile",nearest),("mass_interpolation",interpolation))}
class Forecast(nn.Module):
    def __init__(self):
        super().__init__();self.inp=nn.Linear(6,48);self.enc=nn.TransformerEncoder(nn.TransformerEncoderLayer(48,4,96,dropout=0,batch_first=True,norm_first=True),2,enable_nested_tensor=False);self.head=nn.Linear(48,4)
    def forward(self,x):return x[:,:,:4]+self.head(self.enc(self.inp(x)))
x=torch.tensor(x,dtype=torch.float32);y=torch.tensor(y,dtype=torch.float32);xt=torch.tensor(xt,dtype=torch.float32)
results=[]
for seed in P["training"]["seeds"]:
    torch.manual_seed(seed);model=Forecast();opt=torch.optim.AdamW(model.parameters(),lr=.001)
    for step in range(600):
        i=torch.randint(len(x),(16,));loss=F.smooth_l1_loss(model(x[i]),y[i]);assert torch.isfinite(loss)
        opt.zero_grad();loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1.,error_if_nonfinite=True);opt.step()
    model.eval()
    with torch.no_grad():pred=model(xt).numpy().reshape(len(te),len(T),64,4)*scale
    r={"seed":seed,"parameters":sum(p.numel() for p in model.parameters()),**score(pred)};results.append(r)
    torch.save({"state_dict":model.state_dict(),"scale":torch.tensor(scale)},OUT/f"forecast-{seed}.pt")
    np.save(OUT/f"predictions-{seed}.npy",pred);print("FORECAST",json.dumps(r),flush=True)
best=min(r["mean_normalized_mae"] for r in baselines.values())
admit=all(r["geometry_valid"] and r["mean_normalized_mae"]<best and r["compactness_mae"]<min(b["compactness_mae"] for b in baselines.values() if b["geometry_valid"]) and r["ricci_mae"]<min(b["ricci_mae"] for b in baselines.values() if b["geometry_valid"]) for r in results)
report={"status":"FORECAST_EXAM_COMPLETED","train_trajectories":len(tr),"test_trajectories":len(te),"horizons":T.tolist(),"baselines":baselines,"results":results,"forecast_gate":admit,"historical_family_holdout":True,"independent_solver_validation":False,"weights_promoted":False}
write("forecast_result.json",report);print("FORECAST_RESULT",json.dumps(report),flush=True)
