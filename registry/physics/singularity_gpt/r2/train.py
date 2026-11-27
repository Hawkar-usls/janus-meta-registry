#!/usr/bin/env python3
"""R2: verified numerical source ingestion, field surrogate, geometry diagnostics."""
import hashlib,json,math,os,time,urllib.request
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
torch.set_num_threads(2)
HERE=Path(__file__).resolve().parent
OUT=Path("singularity-r2-output");OUT.mkdir(exist_ok=True)
P=json.loads((HERE/"protocol.json").read_text())
def write(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
def sha(b):return hashlib.sha256(b).hexdigest()
def summary(d):
    if isinstance(d,dict):
        return {"type":"dict","count":len(d),"first_keys":list(d)[:12],"first_value_keys":list(next(iter(d.values())))[:20] if d and isinstance(next(iter(d.values())),dict) else None}
    return {"type":type(d).__name__,"count":len(d)}
raw={};receipt=[]
for f in P["files"]:
    path=f["path"]
    url="https://raw.githubusercontent.com/"+P["source_repository"]+"/"+P["source_commit"]+"/"+path
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url,timeout=120) as response:b=response.read(f["bytes"]+1)
            assert len(b)==f["bytes"]
            assert hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()==f["git_blob_sha1"]
            d=json.loads(b);break
        except Exception:
            if attempt==2:raise
            time.sleep(2)
    raw[path]=d
    receipt.append({**f,"sha256":sha(b),"schema":summary(d)})
    write("ingestion.json",{"files":receipt,"bytes":sum(z["bytes"] for z in receipt)})
    print("VERIFIED",path,len(b),flush=True)
base=raw["complete_data/critcoll_data.json"];plot=raw["complete_data/critcoll_data_plot.json"]
# Plot copy is a derived configuration, not a second independent observation.
common=set(base)&set(plot)
same=sum(base[k].get("Initial_Conditions")==plot[k].get("Initial_Conditions") for k in common if isinstance(base[k],dict) and isinstance(plot[k],dict))
# Audit boundaryData separately, without assigning unverified physical semantics.
bd=raw["complete_data/boundaryData.json"]
write("source_schema.json",{"base":summary(base),"boundary":summary(bd),"plot":summary(plot),"common_dimension_keys":len(common),"identical_initial_conditions":same,"plot_used_for_training":False})
# Normalize sampling of source field grids; restrict to the interior to avoid singular endpoints.
xs=np.linspace(.025,.975,32);phase=np.arange(64)/64
def sample_field(d):
    delta=float(d["Delta"]);keys=sorted((float(k),k) for k in d if k!="Delta")
    x=np.array([a for a,k in keys])
    assert np.all(np.diff(x)>0) and x[0]<=xs[0] and x[-1]>=xs[-1]
    fields=[]
    for name in ["A","f","U","V"]:
        a=np.array([d[k][name] for _,k in keys],dtype=float)
        assert a.ndim==2 and np.isfinite(a).all()
        # upstream plotting script uses endpoint-inclusive linspace.
        t=np.linspace(0,1,a.shape[1])
        y=np.array([np.interp(phase,t,row) for row in a])
        fields.append(np.array([np.interp(xs,x,y[:,j]) for j in range(len(phase))]))
    z=np.stack(fields,-1)
    assert (z[:,:,:2]>0).all()
    return delta,z
grids={}
for dim in (3.046,4.,5.5):
    key="complete_data/3D_plot_data/fields_%0.6f_0.json"%dim
    grids[dim]=sample_field(raw[key])
# Geometry quantities on true and predicted fields, with log-time scale fixed at one echo.
def geom(dim,delta,z):
    a,f,u,v=np.moveaxis(z,-1,0);x=xs[None,:];tau=phase[:,None]*delta
    scale=np.exp(-2*tau)*a*a
    gtt=scale*(x*x-f*f);gtx=-scale*x;gxx=scale
    det=gtt*gxx-gtx*gtx
    plus=x+f;minus=x-f
    def null(s):return gtt+2*gtx*s+gxx*s*s
    denom=np.maximum(scale*(1+x*x+f*f),1e-20)
    good=(f*f-x*x)>0
    # Fixed-x observers only, not general geodesic clocks.
    clock=np.exp(-tau)*a*np.sqrt(np.maximum(f*f-x*x,0))
    ricci=-(dim-2)*np.exp(2*tau)*u*v*(dim-2)**3/4/(a*a*x*x)
    compact=1-a**-2
    metric=np.stack([gtt,gtx,gxx],-1)
    return {"metric":metric,"ricci":ricci,"compactness":compact,"clock":clock,"timelike_mask":good,"null_plus":plus,"null_minus":minus,"diagnostic":{"lorentzian_fraction":float(np.mean(det<0)),"null_residual_max":float(max(np.max(abs(null(plus)/denom)),np.max(abs(null(minus)/denom)))),"wrong_null_residual_mean":float(np.mean(abs(null(plus+.1)/denom))),"timelike_fraction":float(good.mean()),"max_compactness":float(compact.max()),"dss_metric_factor":math.exp(-2*delta),"dss_ricci_factor":math.exp(2*delta),"dss_kretschmann_factor_only":math.exp(4*delta)}}
# Source field parity diagnostics: imposed DSS is not an independent proof.
def parity(z):
    return {"metric_half_echo_mae":float(np.mean(abs(z[:32,:,:2]-z[32:,:,:2]))),"matter_half_echo_antisymmetry_mae":float(np.mean(abs(z[:32,:,2:]+z[32:,:,2:])))}
# Boundary sequence dataset from canonical (not plot duplicate) source.
boundary=[]
for k,item in base.items():
    try:
        d=float(k); ic=item["Initial_Conditions"]
        a=[np.asarray(ic[n],dtype=float) for n in ("fc","psic","Up")]
        delta=float(ic["Delta"])
        if not all(v.ndim==1 and len(v)>=8 and np.isfinite(v).all() for v in a):continue
        z=np.stack([np.interp(phase,np.arange(len(v))/len(v),v,period=1) for v in a],-1)
        boundary.append((d,delta,z))
    except (KeyError,TypeError,ValueError):continue
boundary.sort(key=lambda z:z[0])
btrain=[z for z in boundary if not 3.9<=z[0]<=4.1];btest=[z for z in boundary if 3.9<=z[0]<=4.1]
assert btrain and btest, "boundary schema or test coverage missing"
# Known old corpus kept as auxiliary echo reference, excluding the held band.
r1=json.loads((HERE.parent/"r1/corpus.json").read_text())
old=[(d,v) for d,v in r1["full_precision_series"]["DeltaList.dat"]["rows"] if not 3.9<=d<=4.1]
manifest={"field_train":[3.046,5.5],"field_test":[4.],"boundary_train_D":[z[0] for z in btrain],"boundary_test_D":[z[0] for z in btest],"r1_echo_train_rows":len(old),"field_grid_shape":[64,32,4],"source_sha256":[r["sha256"] for r in receipt],"source_parity":{str(d):parity(z) for d,(_,z) in grids.items()}}
write("precommit.json",manifest)
class Model(nn.Module):
    def __init__(self,nin,nout):
        super().__init__();self.inp=nn.Linear(nin,48)
        self.enc=nn.TransformerEncoder(nn.TransformerEncoderLayer(48,4,96,dropout=0,batch_first=True,norm_first=True),2,enable_nested_tensor=False);self.head=nn.Linear(48,nout)
    def forward(self,x):return self.head(self.enc(self.inp(x)))
def train_model(x,y,xt,seed,steps):
    torch.manual_seed(seed)
    x=torch.tensor(x,dtype=torch.float32);y=torch.tensor(y,dtype=torch.float32);xt=torch.tensor(xt,dtype=torch.float32)
    mu=y.mean((0,1));sd=y.std((0,1)).clamp_min(1e-6)
    model=Model(x.shape[-1],y.shape[-1]);opt=torch.optim.AdamW(model.parameters(),lr=.002)
    for step in range(steps):
        idx=torch.randint(len(x),(min(16,len(x)),))
        loss=F.mse_loss(model(x[idx]),(y[idx]-mu)/sd)
        assert torch.isfinite(loss);opt.zero_grad();loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1.,error_if_nonfinite=True);opt.step()
    model.eval()
    with torch.no_grad():pred=(model(xt)*sd+mu).numpy()
    return model,pred,{"mean":mu,"std":sd}
def boundary_x(d):
    return np.stack([np.full(64,d-4),np.sin(2*np.pi*phase),np.cos(2*np.pi*phase)],-1)
bx=np.stack([boundary_x(d) for d,_,_ in btrain]);by=np.stack([z for d,_,z in btrain])
bxt=np.stack([boundary_x(d) for d,_,_ in btest]);byt=np.stack([z for d,_,z in btest])
# Interpolation from nearest train dimensions, per phase and channel.
left=max([z for z in btrain if z[0]<3.9],key=lambda z:z[0]);right=min([z for z in btrain if z[0]>4.1],key=lambda z:z[0])
bb=np.stack([left[2]+(right[2]-left[2])*(d-left[0])/(right[0]-left[0]) for d,_,_ in btest])
def field_x(d):
    p,x=np.meshgrid(phase,xs,indexing="ij")
    return np.stack([np.full_like(p,d-4),x,np.sin(2*np.pi*p),np.cos(2*np.pi*p),np.sin(4*np.pi*p),np.cos(4*np.pi*p)],-1)
fx=np.concatenate([field_x(d) for d in (3.046,5.5)])
fy=np.concatenate([grids[d][1] for d in (3.046,5.5)])
fxt=field_x(4.);dt,truth=grids[4.]
fb=grids[3.046][1]+(grids[5.5][1]-grids[3.046][1])*(4-3.046)/(5.5-3.046)
# Echo period prediction from old training rows, not the target's true period.
echo=float(np.interp(4.,[z[0] for z in sorted(old)],[z[1] for z in sorted(old)]))
def mae(a,b):return float(np.mean(np.abs(a-b)))
truegeo=geom(4,dt,truth);basegeo=geom(4,echo,fb)
def geo_errors(g):
    mask=g["timelike_mask"]&truegeo["timelike_mask"]
    return {"metric_mae":mae(g["metric"],truegeo["metric"]),"ricci_mae":mae(g["ricci"],truegeo["ricci"]),"compactness_mae":mae(g["compactness"],truegeo["compactness"]),"clock_mae_on_joint_timelike":mae(g["clock"][mask],truegeo["clock"][mask]) if mask.any() else None,"timelike_mask_accuracy":float(np.mean(g["timelike_mask"]==truegeo["timelike_mask"])),"null_slope_mae":mae(g["null_plus"],truegeo["null_plus"])}
results=[]
for s in (1729,2718,3141):
    bm,bp,bnorm=train_model(bx,by,bxt,s,400)
    fm,fp,fnorm=train_model(fx,fy,fxt,s,600)
    # No clipping rescue: invalid metric predictions fail the geometry diagnostic.
    valid=bool(np.isfinite(fp).all() and (fp[:,:,:2]>0).all())
    g=geom(4,echo,fp) if valid else None
    row={"seed":s,"boundary_mae":mae(bp,byt),"boundary_baseline_mae":mae(bb,byt),"field_mae_by_channel":dict(zip(["A","f","U","V"],[mae(fp[:,:,j],truth[:,:,j]) for j in range(4)])),"field_baseline_mae_by_channel":dict(zip(["A","f","U","V"],[mae(fb[:,:,j],truth[:,:,j]) for j in range(4)])),"valid_metric":valid,"geometry_errors":geo_errors(g) if g else None,"geometry_diagnostic":g["diagnostic"] if g else None,"predicted_parity":parity(fp)}
    torch.save({"state_dict":bm.state_dict(),"normalization":bnorm},OUT/f"boundary-{s}.pt");torch.save({"state_dict":fm.state_dict(),"normalization":fnorm},OUT/f"field-{s}.pt")
    results.append(row);print(json.dumps(row),flush=True)
report={"status":"R2_ENGINEERING_EXAM_COMPLETED__SCIENTIFIC_HOLD","source_bytes":sum(z["bytes"] for z in receipt),"boundary_count":len(boundary),"boundary_train":len(btrain),"boundary_test":len(btest),"field_train_dimensions":2,"field_test_dimensions":1,"echo_period_predicted":echo,"echo_period_reference":dt,"source_geometry":truegeo["diagnostic"],"baseline_geometry_errors":geo_errors(basegeo),"results":results,"field_beats_baseline_all_channels_all_seeds":all(all(v<r["field_baseline_mae_by_channel"][k] for k,v in r["field_mae_by_channel"].items()) for r in results),"boundary_beats_baseline_all_seeds":all(r["boundary_mae"]<r["boundary_baseline_mae"] for r in results),"event_horizon_formation":"OPEN_REQUIRES_SUPERCRITICAL_EVOLUTION","full_riemann_tensor":"NOT_COMPUTED","kretschmann":"DSS_SCALING_ONLY","proper_time":"LOCAL_FIXED_X_RATE_NOT_INTEGRATED_GEODESIC","independent_einstein_evolution":False,"weights_promoted":False}
write("result.json",report);print(json.dumps(report,indent=2),flush=True)
