#!/usr/bin/env python3
"""R3A constrained spherical EKG evolution; polar areal chart stops before trapping."""
import json, math, hashlib
from pathlib import Path
import numpy as np
from numba import njit
HERE=Path(__file__).resolve().parent
OUT=Path("singularity-r3-output");OUT.mkdir(exist_ok=True)
P=json.loads((HERE/"protocol.json").read_text())
def write(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
@njit(cache=True)
def initial(r,A,r0,w,t=0.):
    xp=(r+t-r0)/w; xm=(-r+t-r0)/w
    p=np.exp(-xp*xp);m=np.exp(-xm*xm)
    dp=-2*xp*p/w;dm=-2*xm*m/w
    return A*((dp+dm)/r-(p-m)/(r*r)),A*(dp-dm)/r
@njit(cache=True)
def geometry(phi,pi,r,h,flat):
    n=len(r);a=np.ones(n);alpha=np.ones(n);mass=np.zeros(n)
    if flat:return a,alpha,mass,0.
    edge=0.
    for j in range(n):
        s=phi[j]**2+pi[j]**2
        q=2*np.pi*r[j]**2*s
        # exact cell update for locally constant q and r; no division by q
        loss=-np.expm1(-q*h/r[j])
        mass[j]=edge+(r[j]/2-edge)*loss
        edge=mass[j]+(r[j]/2-mass[j])*loss
        c=2*mass[j]/r[j]
        if not np.isfinite(c) or c>=.999:
            return a,alpha,mass,np.nan
        a[j]=1/np.sqrt(1-c)
    R=r[-1]+h/2
    if 2*edge>=R:return a,alpha,mass,np.nan
    la=.5*np.log(1-2*edge/R)
    for j in range(n-1,-1,-1):
        g=(a[j]**2-1)/(2*r[j])+2*np.pi*r[j]*(phi[j]**2+pi[j]**2)
        alpha[j]=np.exp(la-.5*h*g)
        la-=h*g
    return a,alpha,mass,edge
@njit(cache=True)
def at(x,i,parity):
    if i<0:return parity*x[-i-1]
    if i>=len(x):return 0.
    return x[i]
@njit(cache=True)
def rhs(phi,pi,r,h,flat):
    a,alpha,m,edge=geometry(phi,pi,r,h,flat)
    if not np.isfinite(edge):
        return np.full_like(phi,np.nan),np.full_like(pi,np.nan)
    v=alpha/a;u=v*pi;w=v*phi;n=len(r)
    dp=np.empty(n);dq=np.empty(n)
    for j in range(n):
        rf=(j+1)*h;lf=j*h
        ur=.5*(u[j]+at(u,j+1,1));ul=.5*(u[j]+at(u,j-1,1))
        wr=.5*(w[j]+at(w,j+1,-1));wl=.5*(w[j]+at(w,j-1,-1))
        dp[j]=(ur-ul)/h
        dq[j]=3*(rf*rf*wr-lf*lf*wl)/(rf**3-lf**3)
        # weak high-frequency damping, odd Phi / even Pi at origin
        dp[j]-=.02/h*(at(phi,j-2,-1)-4*at(phi,j-1,-1)+6*phi[j]-4*at(phi,j+1,-1)+at(phi,j+2,-1))
        dq[j]-=.02/h*(at(pi,j-2,1)-4*at(pi,j-1,1)+6*pi[j]-4*at(pi,j+1,1)+at(pi,j+2,1))
    return dp,dq
@njit(cache=True)
def advance(p,q,r,h,dt,flat):
    a,b=rhs(p,q,r,h,flat)
    c,d=rhs(p+dt*a/2,q+dt*b/2,r,h,flat)
    e,f=rhs(p+dt*c/2,q+dt*d/2,r,h,flat)
    g,k=rhs(p+dt*e,q+dt*f,r,h,flat)
    return p+dt*(a+2*c+2*e+g)/6,q+dt*(b+2*d+2*f+k)/6
def flat_test(n):
    h=30/n;r=(np.arange(n)+.5)*h
    p,q=initial(r,.01,5.,1.);t=0.
    while t<8-1e-12:
        dt=min(.3*h,8-t);p,q=advance(p,q,r,h,dt,True);t+=dt
    ep,eq=initial(r,.01,5.,1.,8.)
    err=np.sqrt(np.sum(r*r*((p-ep)**2+(q-eq)**2))/np.sum(r*r*(ep**2+eq**2)))
    return float(err)
def evolve(n,A,r0,w):
    h=30/n;r=(np.arange(n)+.5)*h
    p,q=initial(r,A,r0,w);a,alpha,m,M0=geometry(p,q,r,h,False)
    if not np.isfinite(M0):return {"class":"INVALID_INITIAL"},None
    c0=float(np.max(2*m/r))
    if c0>=.65:return {"class":"INITIAL_TOO_COMPACT","initial_compactness":c0},None
    t=0.;proper=0.;maxc=c0;maxdrift=0.;maxR=0.;history=[];snap=[];sample_times=np.linspace(0,16,65);nexts=0
    label="UNRESOLVED";flux_errors=[];prev_m=m.copy()
    def collect():
        nonlocal maxc,maxR,maxdrift
        c=2*m/r;R=8*np.pi*(p*p-q*q)/(a*a)
        maxc=max(maxc,float(c.max()));maxR=max(maxR,float(np.max(np.abs(R))))
        maxdrift=max(maxdrift,abs(M-M0)/max(M0,1e-30))
        history.append([t,proper,float(c.max()),float(alpha[0]),float(np.max(np.abs(R))),float(M),float(m[np.searchsorted(r,3.)])])
        radial=np.linspace(.1,12,64)
        snap.append(np.stack([np.interp(radial,r,z) for z in (p,q,a,alpha,c,R)],axis=-1))
    M=M0;collect();nexts=1
    while t<16-1e-12:
        dt=min(.3*h,16-t)
        oldalpha=alpha[0];oldm=m.copy();oldflux=4*np.pi*r*r*alpha/a**3*p*q
        pn,qn=advance(p,q,r,h,dt,False)
        if not (np.isfinite(pn).all() and np.isfinite(qn).all()):label="NUMERICAL_FAILURE";break
        an,aln,mn,Mn=geometry(pn,qn,r,h,False)
        if not np.isfinite(Mn):label="NUMERICAL_FAILURE";break
        # independent momentum-constraint consistency (not the solved radial constraint).
        newflux=4*np.pi*r*r*aln/an**3*pn*qn
        mask=(r>.25)&(r<12)
        fl=.5*(oldflux+newflux);dm=(mn-oldm)/dt
        flux_errors.append([float(np.sum((dm[mask]-fl[mask])**2)),float(np.sum(fl[mask]**2))])
        p,q,a,alpha,m,M=pn,qn,an,aln,mn,Mn;t+=dt
        proper+=dt*.5*(oldalpha+alpha[0])
        c=2*m/r;maxc=max(maxc,float(c.max()))
        maxR=max(maxR,float(np.max(np.abs(8*np.pi*(p*p-q*q)/(a*a)))))
        maxdrift=max(maxdrift,abs(M-M0)/max(M0,1e-30))
        if t>=sample_times[nexts]-1e-12 if nexts<len(sample_times) else False:
            collect();nexts+=1
        if c.max()>=.85:label="NEAR_TRAPPING_PROXY";break
    if t>history[-1][0]+1e-10:collect()
    inner=float(m[np.searchsorted(r,3.)]/max(M0,1e-30))
    if label=="UNRESOLVED" and t>=16-1e-8 and inner<.05 and np.max(2*m/r)<.2:label="DISPERSAL_PROXY"
    flux=np.array(flux_errors)
    return {"class":label,"initial_compactness":c0,"peak_compactness":maxc,"final_compactness":float(np.max(2*m/r)),"initial_mass":float(M0),"mass_relative_drift":float(maxdrift),"inner_mass_fraction":inner,"peak_abs_ricci":maxR,"end_t":t,"central_proper_time":proper,"momentum_relative_l2":float(np.sqrt(flux[:,0].sum()/max(flux[:,1].sum(),1e-30))) if len(flux) else None,"samples":len(history)},(np.asarray(history),np.asarray(snap))
ns=P["numerics"]["grid_cells"];errors=[flat_test(n) for n in ns]
r=(np.arange(ns[0])+.5)*30/ns[0];a,al,m,M=geometry(np.zeros_like(r),np.zeros_like(r),r,30/ns[0],False)
vacuum=bool(np.array_equal(a,np.ones_like(a)) and np.array_equal(al,np.ones_like(al)) and M==0)
flat_ok=all(a>b for a,b in zip(errors,errors[1:])) and errors[-1]<.05
controls={"flat_wave_relative_l2":dict(zip(map(str,ns),errors)),"flat_wave_pass":flat_ok,"vacuum_pass":vacuum}
write("controls.json",controls);print("CONTROLS",json.dumps(controls),flush=True)
rows=[];arrays={}
for fam in P["numerics"]["families"]:
    for A in P["numerics"]["amplitudes"]:
        for n in ns:
            d,trace=evolve(n,A,fam["r0"],fam["width"])
            key=f"{fam['name']}_{A}_{n}"
            row={"family":fam["name"],"amplitude":A,"n":n,**d};rows.append(row)
            if trace is not None:arrays[key+"_history"],arrays[key+"_fields"]=trace
            print("CASE",json.dumps(row),flush=True)
        write("cases.json",rows)
np.savez_compressed(OUT/"trajectories.npz",**arrays)
labels=[]
for fam in P["numerics"]["families"]:
    for A in P["numerics"]["amplitudes"]:
        rr=[r for r in rows if r["family"]==fam["name"] and r["amplitude"]==A and r["n"] in ns[-2:]]
        if len(rr)==2 and rr[0]["class"]==rr[1]["class"] and rr[0]["class"] in ("NEAR_TRAPPING_PROXY","DISPERSAL_PROXY") and all(r["mass_relative_drift"]<.05 for r in rr):
            labels.append({"family":fam["name"],"amplitude":A,"class":rr[-1]["class"],"peak_compactness":rr[-1]["peak_compactness"],"n":rr[-1]["n"]})
brackets={}
for fam in P["numerics"]["families"]:
    name=fam["name"];low=[r["amplitude"] for r in labels if r["family"]==name and r["class"]=="DISPERSAL_PROXY"];high=[r["amplitude"] for r in labels if r["family"]==name and r["class"]=="NEAR_TRAPPING_PROXY"]
    brackets[name]={"max_dispersal_amplitude":max(low) if low else None,"min_near_trapping_amplitude":min(high) if high else None,"ordered_bracket":bool(low and high and max(low)<min(high))}
report={"status":"R3A_ENGINEERING_EXAM_COMPLETED__SCIENTIFIC_HOLD","controls":controls,"cases":len(rows),"resolution_agreement_mass_gated_labels":labels,"proxy_brackets":brackets,"controls_pass":flat_ok and vacuum,"event_horizon_observed":False,"trapped_surface_crossed":False,"critical_exponent_measured":False,"dss_reproduced":False,"neural_training":"DEFERRED_PENDING_SOLVER_REVIEW","trajectory_columns":{"history":["coordinate_time","central_clock_approx","max_compactness","central_lapse","max_abs_Ricci","outer_mass","inner_mass"],"fields":["Phi","Pi","a","alpha","compactness","Ricci"]},"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest()}
write("result.json",report);print("R3_RESULT",json.dumps(report),flush=True)
