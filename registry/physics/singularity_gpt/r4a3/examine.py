"""R4A3: pre-AMR resolution exam and independent synthetic DSS sensitivity."""
import ast,io,json,hashlib,math,sys,zipfile
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"r4a2"))
from diagnostic_lib import run
P=json.loads((HERE/"protocol.json").read_text())
OUT=Path("r4a3-output");OUT.mkdir(exist_ok=True)
mode=sys.argv[1]
def write(n,d): (OUT/n).write_text(json.dumps(d,indent=2,allow_nan=False)+"\n")
def load(name):
    b=Path(name+".zip").read_bytes()
    assert hashlib.sha256(b).hexdigest()==P["artifacts"][name]["sha256"]
    return zipfile.ZipFile(io.BytesIO(b))
def frozen_function(path,name,env):
    node=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),"exec"),env)
    return env[name]
def simulate(cfg,A=None,n=None):
    return run(cfg["A"] if A is None else A,cfg["r0"],cfg["w"],cfg["R"],cfg["n"] if n is None else n,cfg["checkpoints"])
def mass_pass(r):return r["checkpoints"][-1]["mass_drift"]<P["mass_budget"]
traces={}
if mode=="fixed":
    with load("r4a") as z:
        old=json.loads(z.read("result.json"))
        a=np.load(io.BytesIO(z.read("traces.npz")),allow_pickle=False)
        for n in (1536,3072):traces[str(n)]=a[f"fixed_0.11484375_{n}"]
    with load("r4a2") as z:
        old2=json.loads(z.read("result.json"))
        a=np.load(io.BytesIO(z.read("new_traces.npz")),allow_pickle=False)
        traces["6144"]=a["fixed_case"]
    new,x=simulate(P["fixed"]);traces["12288"]=x
    def compare(ns):
        t=np.linspace(0,min(traces[str(n)][-1,1] for n in ns),8192)
        v={n:np.interp(t,traces[str(n)][:,1],traces[str(n)][:,2]) for n in ns}
        c={n:8*np.pi*v[n]**2 for n in ns}
        mask=np.logical_and.reduce([c[n]*(30/n)**2<=1/64 for n in ns])
        rel=lambda u,w:float(np.linalg.norm(u-w)/max(np.linalg.norm(w),1e-30))
        return {"n":ns,"common_proper_time":float(t[-1]),"all_resolved_fraction":float(mask.mean()),"pairs":[{"coarse":a,"fine":b,"relative_l2":rel(v[a],v[b]),"resolved_relative_l2":rel(v[a][mask],v[b][mask]) if mask.any() else None,"peak_Ricci_ratio":float(max(c[b])/max(max(c[a]),1e-300))} for a,b in zip(ns,ns[1:])]}
    result={"new_case":new,"mass_budget_pass":mass_pass(new),"same_class_on_three_finest":bool(new["status"]==old2["new_cases"]["fixed_case"]["status"]=="DISPERSAL_PROXY"),"common_time_comparisons":[compare([1536,3072,6144,12288]),compare([3072,6144,12288])]}
elif mode=="bracket":
    cfg=P["bracket"];lo,hi=cfg["Alo"],cfg["Ahi"];cases=[]
    with load("r4a2") as z:lower=json.loads(z.read("result.json"))["new_cases"]["fixed_case"]
    assert lower["A"]==lo and lower["n"]==cfg["n"] and lower["status"]=="DISPERSAL_PROXY" and mass_pass(lower)
    upper,x=simulate(cfg,hi);cases.append(upper);traces["upper"]=x
    stop="UPPER_NOT_ADMITTED"
    if upper["status"]=="NEAR_TRAPPING_PROXY" and mass_pass(upper):
        stop="BUDGET_EXHAUSTED"
        for i in range(cfg["steps"]):
            mid=(lo+hi)/2;r,x=simulate(cfg,mid);cases.append(r);traces[f"mid{i}"]=x
            print("BRACKET_CASE",json.dumps(r),flush=True)
            if not mass_pass(r):stop="MASS_BUDGET";break
            if r["status"]=="DISPERSAL_PROXY":lo=mid
            elif r["status"]=="NEAR_TRAPPING_PROXY":hi=mid
            else:stop=r["status"];break
        bracket=[lo,hi]
    else:bracket=None
    result={"proxy_bracket":bracket,"stop_reason":stop,"cases":cases,"lower_historical":lower,"threshold_physical":False}
elif mode=="controls":
    cfg=P["controls"]
    oldP=json.loads((HERE.parent/"r4a2"/"protocol.json").read_text())
    shadow=frozen_function(HERE.parent/"r4a2"/"examine.py","shadow",{"np":np,"P":oldP})
    pairs=[]
    for A in cfg["A"]:
        rr=[]
        for n in cfg["n"]:
            r,x=simulate(cfg,A,n);s=shadow(x);traces[f"{A}_{n}"]=x
            rr.append({"case":r,"shadow_candidate":s,"mass_budget_pass":mass_pass(r)})
            print("PROXY_CONTROL",json.dumps(rr[-1]),flush=True)
        eligible=all(z["case"]["status"]=="NEAR_TRAPPING_PROXY" and z["mass_budget_pass"] for z in rr)
        pairs.append({"A":A,"eligible_pair":eligible,"results":rr,"false_early_dispersal":any(z["shadow_candidate"] is not None for z in rr) if eligible else None})
    result={"pairs":pairs,"eligible_amplitudes":sum(z["eligible_pair"] for z in pairs),"false_positive_pairs":sum(z["false_early_dispersal"] is True for z in pairs),"early_stop_authorized":False,"true_trapped_surface_control":False}
elif mode=="positive":
    cfg=P["positive"];rng=np.random.default_rng(cfg["seed"])
    estimate=frozen_function(HERE.parent/"r3b"/"echo_probe.py","echo_estimate",{"np":np,"math":math})
    rows=[]
    for period in cfg["periods"]:
        s=np.linspace(0,period*cfg["log_span_cycles"],cfg["points"])
        # Synthetic central derivative: exponential envelope, sinusoidal in log scale.
        # The supplied truth is used only by the signal generator and scorer.
        t=-np.exp(-s);base=np.exp(s-s[-1])*np.sin(2*np.pi*s/period+.31)
        for noise in cfg["relative_noise"]:
            v=base*(1+noise*rng.standard_normal(len(base)))
            x=np.column_stack((t,t,v,8*np.pi*v*v,np.zeros_like(t),np.ones_like(t)))
            q=estimate(x,cfg["n"]);pred=q["candidate"]["full_period_median"] if q.get("candidate") else None
            err=abs(pred-period)/period if pred is not None else None
            rows.append({"synthetic_period":period,"relative_noise":noise,"estimated":pred,"relative_error":err,"within_tolerance":bool(err is not None and err<=cfg["accept_clean_relative_error"]),"details":q})
    clean=[r for r in rows if r["relative_noise"]==0 and r["synthetic_period"]<=4.1]
    result={"rows":rows,"clean_core_pass":all(r["within_tolerance"] for r in clean),"clean_core_detected":sum(r["within_tolerance"] for r in clean),"clean_core_total":len(clean),"physical_DSS_established":False,"physical_reference_period_used":False}
else:raise ValueError(mode)
result.update({"mode":mode,"scientific_hold":True,"amr_implemented":False,"production_changed":False,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest()})
write("result.json",result)
if traces:np.savez_compressed(OUT/"traces.npz",**traces)
print("R4A3_RESULT",json.dumps(result,allow_nan=False),flush=True)
