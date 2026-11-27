"""Diagnostic-only instrumentation of immutable R4B5A.3 integration."""
import hashlib,io,json,sys,time,zipfile
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
P=json.loads((HERE/"protocol.json").read_text())
OUT=Path("r4b5a4-output");OUT.mkdir(exist_ok=True)
START=time.monotonic()
def emit(tag,obj):
    print("R4B5A4_"+tag,json.dumps(obj,allow_nan=False),flush=True)
def write(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
def require(x,msg):
    if not x:raise RuntimeError(msg)
def finish(status,**extra):
    result={"status":status,"scientific_hold":True,"holds":["COMPACTNESS_CONVERGENCE_HOLD","EVENT_INVARIANCE_HOLD","LATE_TIME_RICCI_HOLD","IDENTIFIABILITY_HOLD independent"],"dss_tested":False,"amr_implemented":False,"n98304_run":False,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest(),**extra}
    write("result.json",result);emit("RESULT",result);sys.exit(0)
def scalar_order(a,b,signed=False):
    x,y=abs(a),abs(b)
    p=float(np.log2(x/y)) if min(x,y)>0 else None
    mono=not signed or a*b>0
    return {"d12":float(x),"d23":float(y),"p":p,"monotone":bool(mono),"pass":bool(p is not None and 1.5<=p<=2.5 and mono and y<x)}
def local_peaks(r,c):
    ids=np.flatnonzero((c[1:-1]>=c[:-2])&(c[1:-1]>c[2:]))+1
    # Endpoints only when genuine one-sided maxima.
    if c[0]>c[1]:ids=np.r_[0,ids]
    if c[-1]>c[-2]:ids=np.r_[ids,len(c)-1]
    if not len(ids):ids=np.array([int(np.argmax(c))])
    ids=ids[np.lexsort((ids,-c[ids]))][:4]
    return [{"i":int(i),"r":float(r[i]),"C":float(c[i])} for i in ids]
def vertex(r,c,i):
    if i<=0 or i>=len(c)-1:return None
    h=r[i+1]-r[i];a=(c[i-1]+c[i+1]-2*c[i])/2;b=(c[i+1]-c[i-1])/2
    if a>=0:return None
    z=-b/(2*a)
    if abs(z)>1:return None
    return {"r":float(r[i]+h*z),"C":float(c[i]+b*z+a*z*z)}
class Capture:
    def __init__(self,key):
        self.key=key;self.prev=None;self.snap={};self.history=[]
        self.targets=P["snapshots"]["tau"]
    def __call__(self,t,T,r,p,q,a,al,m):
        c=2*m/r;i=int(np.argmax(c));peaks=local_peaks(r,c)
        second=peaks[1] if len(peaks)>1 else None
        self.history.append([t,T,float(r[i]),float(c[i]),second["r"] if second else -1.,second["C"] if second else -1.,float(c[i]-second["C"]) if second else -1.])
        # Only copy previous/next native states while any target remains.
        if len(self.snap)==len(self.targets):return
        cur=np.stack((p,q,m,c,al/a),axis=1)
        if self.prev is not None:
            old_t,old= self.prev
            for target in self.targets:
                if target not in self.snap and old_t<=target<=T:
                    f=(target-old_t)/(T-old_t)
                    self.snap[target]=old+f*(cur-old)
        self.prev=(T,cur)
def load_original():
    path=HERE.parent/"r4b5a3"/"audit.py"
    s=path.read_text()
    s=s[:s.index("rows={};traces={}")]
    before='        data.append([t,T,v2,v3,R2,R3,c,E,inner,pp,qq,ss,*integ.tolist(),*maxres.tolist(),refinteg,maxrefres])'
    require(s.count(before)==1,"INSTRUMENTATION_POINT")
    after=before+"\n        capture(t,T,r,p,q,a,al,m)"
    patched=s.replace(before,after)
    require(patched.replace(after,before)==s,"INSTRUMENTATION_REVERSIBLE")
    # Read-only capture copies arrays; no changes to any solver input, step or stop.
    ns={"__file__":str(path),"__name__":"r4b5a4_parent","capture":None}
    exec(compile(patched,str(path),"exec"),ns)
    return ns
ns=load_original()
raw=Path(sys.argv[1]).read_bytes()
require(hashlib.sha256(raw).hexdigest()==P["parent"]["zip_sha256"],"PARENT_ZIP_SHA")
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    names=[x for x in z.namelist() if Path(x).name=="traces.npz"]
    require(len(names)==1,"PARENT_TRACE")
    with np.load(io.BytesIO(z.read(names[0])),allow_pickle=False) as arr:
        historical={k:arr[k].copy() for k in ("coarse","medium","fine")}
archive=json.loads((HERE.parent/"r4b5a3a"/"result_archive.json").read_text())
require(archive["run"]==P["parent"]["run"] and archive["logged_evidence"][-1]["data"]["status"]=="COMPACTNESS_CONVERGENCE_HOLD","PARENT_ARCHIVE")
old_cases={r["data"]["id"]:r["data"] for r in archive["logged_evidence"] if r["tag"]=="R4B5A3_CASE"}
def norms(x,y):
    d=x-y
    return {"L2":float(np.linalg.norm(d)),"Linf":float(np.max(np.abs(d))),"rel_L2":float(np.linalg.norm(d)/max(np.linalg.norm(y),1e-30)),"rel_Linf":float(np.max(np.abs(d))/max(np.max(np.abs(y)),1e-30))}
synthetic=[]
for n in (256,512,1024):
    h=4/n;r=(np.arange(n)+.5)*h;k=.002
    p=np.sqrt(3*k/(2*np.pi*(1-2*k*r*r)));q=np.zeros_like(p)
    a,al,m,M=ns["geometry"](p,q,r,h,False)
    exact=k*r**3;c=2*m/r;ce=2*k*r*r
    grid=np.linspace(r[0],r[-1],4097)
    mi=np.interp(grid,r,m);ci=np.interp(grid,r,c)
    peaks={}
    for name,v in (("isolated",.6-.03*(r-1.137)**2),("competing",np.maximum(.6-.08*(r-1.137)**2,.5999-.09*(r-2.731)**2))):
        i=int(np.argmax(v));fit=vertex(r,v,i)
        peaks[name]={"native":float(v[i]),"native_r":float(r[i]),"fit":fit,"local_maxima":local_peaks(r,v),"fit_error":abs(fit["C"]-.6) if fit else None}
    synthetic.append({"n":n,"mass":norms(m,exact),"C":norms(c,ce),"interpolated_mass_C":norms(2*mi/grid,2*k*grid**2),"direct_C_interpolation":norms(ci,2*k*grid**2),"peaks":peaks})
so={}
so={}
for q in ("mass","C","interpolated_mass_C","direct_C_interpolation"):
    e=[v[q]["Linf"] for v in synthetic]
    so[q]={"errors":e,"p12":float(np.log2(e[0]/e[1])) if min(e[:2])>0 else None,"p23":float(np.log2(e[1]/e[2])) if min(e[1:])>0 else None}
syn_ok=synthetic[-1]["C"]["Linf"]<=.0005 and all(v is not None and 1.5<=v<=2.5 for v in (so["C"]["p12"],so["C"]["p23"]))
emit("SYNTHETIC",{"cases":synthetic,"orders":so,"pass":bool(syn_ok)})
write("synthetic.json",{"cases":synthetic,"orders":so,"pass":bool(syn_ok)})
if not syn_ok:finish("SYNTHETIC_MASS_HOLD",synthetic=synthetic,orders=so)
caps={};traces={};rows={};replay={}
for key,n in (("coarse",12288),("medium",24576),("fine",49152)):
    if key=="fine":
        elapsed=time.monotonic()-START;projected=4*rows["medium"]["elapsed_seconds"]
        emit("BUDGET",{"elapsed":elapsed,"projected_fine":projected,"pass":elapsed+projected<=3000})
        if elapsed+projected>3000:finish("COMPUTE_BUDGET_HOLD",replay=replay)
    cap=Capture(key);ns["capture"]=cap
    cfg={"A":.1152,"r0":5,"w":1,"R":30,"n":n,"end":16,"CFL":.3,"family":"original","reference_radius":12}
    row,x=ns["run"](cfg,True)
    caps[key]=cap;traces[key]=x;rows[key]=row
    saved=historical[key]
    exact=x.dtype==saved.dtype and x.shape==saved.shape and x.tobytes(order="C")==saved.tobytes(order="C")
    old={k:v for k,v in old_cases[key].items() if k not in ("id","elapsed_seconds")}
    same_case={k:v for k,v in row.items() if k!="elapsed_seconds"}==old
    integrity=row["status"]=="EVENT_090_REACHED" and min(row["scale"],row["scale_alt"])>=8 and max(row["mass_drift"],row["direct_balance_residual_max"],row["reference_interior_balance_residual_max"])<.01
    support=all(t in cap.snap for t in P["snapshots"]["tau"][:10])
    replay[key]={"exact_trace":bool(exact),"exact_case":bool(same_case),"integrity":bool(integrity),"mandatory_support":bool(support),"trace_sha256":hashlib.sha256(x.tobytes(order="C")).hexdigest(),"snapshot_times":list(cap.snap),"row":row}
    emit("REPLAY",{"id":key,**replay[key]})
    np.savez_compressed(OUT/(key+"-radial.npz"),argmax_history=np.asarray(cap.history),trace=x,**{"tau_"+str(t):v for t,v in cap.snap.items()})
    write("replay.json",replay)
    if not all((exact,same_case,integrity,support)):finish("TECHNICAL_OR_INTEGRITY_HOLD",replay=replay)
def grid(key):
    n=rows[key]["n"];return (np.arange(n)+.5)*rows[key]["h"]
def profile_pair(k1,k2,t):
    r,s=grid(k1),grid(k2);a,b=caps[k1].snap[t],caps[k2].snap[t]
    common=r[(r>=s[0])&(r<=s[-1])]
    u=np.stack([np.interp(common,r,a[:,j]) for j in range(5)],axis=1)
    v=np.stack([np.interp(common,s,b[:,j]) for j in range(5)],axis=1)
    # Global common support uses the coarsest centers for BOTH adjacent pairs.
    cr=grid("coarse");cr=cr[(cr>=max(r[0],s[0]))&(cr<=min(r[-1],s[-1]))]
    u=np.stack([np.interp(cr,r,a[:,j]) for j in range(5)],axis=1)
    v=np.stack([np.interp(cr,s,b[:,j]) for j in range(5)],axis=1)
    i,j=int(np.argmax(a[:,3])),int(np.argmax(b[:,3]));c1,c2=float(a[i,3]),float(b[j,3])
    cp1,cp2=float(np.max(u[:,3])),float(np.max(v[:,3]))
    p1,p2=local_peaks(r,a[:,3]),local_peaks(s,b[:,3])
    def competing(peaks):
        return len(peaks)>1 and abs(peaks[0]["r"]-peaks[1]["r"])>2*rows[k1]["h"] and peaks[0]["C"]-peaks[1]["C"]<=.0005
    inner=cr<=.5;neighborhood=(cr>=min(r[i],s[j])-4*rows[k1]["h"])&(cr<=max(r[i],s[j])+4*rows[k1]["h"])
    delta=abs(float(r[i]-s[j]));matched={}
    for rr in (r[i],s[j]):
        if max(r[0],s[0])<=rr<=min(r[-1],s[-1]):
            matched[str(float(rr))]=[float(np.interp(rr,r,a[:,3])),float(np.interp(rr,s,b[:,3]))]
    return {"C":norms(u[:,3],v[:,3]),"mass":norms(u[:,2],v[:,2]),"inner_C":norms(u[inner,3],v[inner,3]),"inner_mass":norms(u[inner,2],v[inner,2]),"peak_neighborhood_C":norms(u[neighborhood,3],v[neighborhood,3]) if neighborhood.any() else None,"same_radius_C":matched,"mass_vs_C_interpolation":{"first":norms(2*u[:,2]/cr,u[:,3]),"second":norms(2*v[:,2]/cr,v[:,3])},"argmax_r":[float(r[i]),float(s[j])],"shift":delta,"shift_cells":[delta/rows[k1]["h"],delta/rows[k2]["h"]],"shift_gt_one_coarse_cell":bool(delta>rows[k1]["h"]),"local_maxima":[p1,p2],"competing_branch_candidates":[bool(competing(p1)),bool(competing(p2))],"subcell_vertices":[vertex(r,a[:,3],i),vertex(s,b[:,3],j)],"native_peak_difference":c1-c2,"common_grid_peak_difference":cp1-cp2,"sampling_increment_difference":(c1-cp1)-(c2-cp2),"decomposition_residual":(c1-c2)-(cp1-cp2)-((c1-cp1)-(c2-cp2))}
profiles={}
for t in P["snapshots"]["tau"]:
    missing=[k for k in caps if t not in caps[k].snap]
    if missing:
        report={"tau":t,"missing":missing,"pass":False};emit("PROFILE",report);profiles[str(t)]=report;continue
    a,b=profile_pair("coarse","medium",t),profile_pair("medium","fine",t)
    orders={q+"_"+n:scalar_order(a[q][n],b[q][n]) for q in ("C","mass","inner_C","inner_mass") for n in ("L2","Linf")}
    checks={"C_absolute":b["C"]["Linf"]<=.0005,"C_relative":max(b["C"]["rel_L2"],b["C"]["rel_Linf"])<=.01,"mass_relative":max(b["mass"]["rel_L2"],b["mass"]["rel_Linf"])<=.01,"C_peak":abs(b["native_peak_difference"])<=.0005,"C_orders":all(orders[q]["pass"] for q in ("C_L2","C_Linf")),"mass_orders":all(orders[q]["pass"] for q in ("mass_L2","mass_Linf"))}
    report={"tau":t,"pair_12":a,"pair_23":b,"orders":orders,"checks":checks,"pass":all(checks.values())}
    profiles[str(t)]=report;emit("PROFILE",report)
write("profiles.json",profiles)
def event(key,c):
    x=traces[key];i=int(np.flatnonzero(x[:,6]>=c)[0]);require(i>=2,"CROSSING_SUPPORT")
    a,b=x[i-1],x[i];dt=b[1]-a[1];slope=(b[6]-a[6])/dt
    lin=float(a[1]+(c-a[6])/slope)
    tt=(x[i-2:i+1,1]-a[1])/dt;vv=x[i-2:i+1,6]-c
    coef=np.polyfit(tt,vv,2)
    roots=np.roots(coef)
    valid=[float(z.real) for z in roots if abs(z.imag)<1e-10 and 0<=z.real<=1 and 2*coef[0]*z.real+coef[1]>0]
    quad=float(a[1]+valid[0]*dt) if len(valid)==1 else None
    def values(t):
        return [float(np.interp(t,x[:,1],x[:,k])) for k in (4,5)]
    return {"linear_tau":lin,"quadratic_tau":quad,"linear_Ricci":values(lin),"quadratic_Ricci":values(quad) if quad is not None else None,"slope":float(slope),"inverse_slope":float(1/slope),"bracket_dt":float(dt),"interpolator_delta":abs(quad-lin) if quad is not None else None}
events={}
for c in P["crossing"]["thresholds"]:
    e=[event(k,c) for k in ("coarse","medium","fine")];orders={};ricci={};decomp={}
    for name in ("linear","quadratic"):
        t=[v[name+"_tau"] for v in e]
        if any(v is None for v in t):orders[name]=None;ricci[name]=None;continue
        orders[name]=scalar_order(t[0]-t[1],t[1]-t[2],True)
        orders[name]["medium_fine_abs"]=abs(t[1]-t[2])
        a,b=e[1][name+"_Ricci"],e[2][name+"_Ricci"]
        ricci[name]=[abs(x-y)/max(abs(y),1e-30) for x,y in zip(a,b)]
        cut=min(t[1],t[2]);u,v=traces["medium"],traces["fine"]
        ca=[float(np.interp(cut,u[:,1],u[:,i])) for i in (4,5)]
        cb=[float(np.interp(cut,v[:,1],v[:,i])) for i in (4,5)]
        decomp[name]={"common_tau":cut,"proxies":[{"event_signed":x-y,"common_signed":p-q,"tail_signed":(x-p)-(y-q),"residual":(x-y)-(p-q)-((x-p)-(y-q))} for x,y,p,q in zip(a,b,ca,cb)]}
    lp=orders["linear"]["p"];qp=orders["quadratic"]["p"] if orders["quadratic"] else None
    sensitive=lp is not None and qp is not None and (lp*qp<0 or abs(lp-qp)>.5)
    ct=min(e[1]["linear_tau"],e[2]["linear_tau"])
    cm=[float(np.interp(ct,traces[k][:,1],traces[k][:,6])) for k in ("medium","fine")]
    report={"threshold":c,"events":e,"orders":orders,"estimator_sensitive":bool(sensitive),"Ricci_relative":ricci,"Ricci_event_time_decomposition":decomp,"first_order_crossing_sensitivity":abs(cm[0]-cm[1])*max(e[1]["inverse_slope"],e[2]["inverse_slope"]),"actual_linear_time_difference":abs(e[1]["linear_tau"]-e[2]["linear_tau"])}
    events[str(c)]=report;emit("CROSSING",report)
write("crossings.json",events)
finish("COMPACTNESS_LOCALIZATION_COMPLETE__SCIENTIFIC_HOLD",replay=replay,profile_pass={k:v["pass"] for k,v in profiles.items()},crossing_orders={k:v["orders"] for k,v in events.items()},diagnostic_only=True)
