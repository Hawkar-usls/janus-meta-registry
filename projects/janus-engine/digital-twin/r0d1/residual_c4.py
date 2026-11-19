"""R0D1C4: block recovery and held-run-out tests; mechanisms not identified."""
import json, math, statistics as st, tarfile, hashlib
from pathlib import Path
SHA='fdcf8d27c8d04e7f47db14039c366b79e12ccc7e00d789a198189be3c931db9a'
V=.0070588701445034046;R=8.314462618;K=5.884527667675732e-11
REC=[(8,1200,18050,17700,5000,.478),(14,1540,18300,18300,5000,.5737333333333333),(10,1800,17050,17800,13000,.663),(12,2100,20400,21000,5000,27.46/36.29),(6,2400,18050,18450,5000,.847)]
def read(t,n):
    d={}
    for l in t.extractfile(f'experiments/exp10/data_exp10_{n:02}.txt'):
        try:x=list(map(float,l.split()))
        except ValueError:continue
        if len(x)==19 and x[0]>1e9 and all(map(math.isfinite,x)):d.setdefault(x[0],x)
    a=[d[k] for k in sorted(d)];s=a[0][0]
    for x in a:x[0]-=s
    return a
def slope(x,y):
    a,b=st.mean(x),st.mean(y);return sum((i-a)*(j-b) for i,j in zip(x,y))/sum((i-a)**2 for i in x)
def inv(x):return 1e6*V*x[9]/(R*(x[1]+273.15))
def valid(x):return x[9]>1 and 0<x[1]<60 and x[6]>0
def blocks(a,lo,hi,q,water,width=600):
    out=[]
    for start in range(lo,hi-width+1,width):
        x=[r for r in a if start<=r[0]<start+width and valid(r)]
        if len(x)<250 or x[-1][0]-x[0][0]<580 or max(v[0]-u[0] for u,v in zip(x,x[1:]))>10:continue
        m=st.mean(3*K*1e6*(q/.663)**(1/3)*(water(r[0])-r[9]) for r in x) if q else 0.
        g=st.mean((.2095*r[6]-r[9])/1000 for r in x)
        out.append(dict(start_s=start,samples=len(x),measured=slope([r[0] for r in x],[inv(r) for r in x]),membrane=m,ambient_gradient_kpa=g,mean_pO2_pa=st.mean(r[9] for r in x),mean_current_ma=st.mean(r[13] for r in x)))
    return out
def ls1(x,y):return sum(a*b for a,b in zip(x,y))/sum(a*a for a in x)
def fit(rows,kind):
    m=[r['membrane'] for r in rows];g=[r['ambient_gradient_kpa'] for r in rows];y=[r['measured'] for r in rows]
    if kind=='frozen':return 1.,0.
    if kind=='frozen_plus_ingress':return 1.,max(0,ls1(g,[v-u for v,u in zip(y,m)]))
    if kind=='scaled_membrane':return max(0,ls1(m,y)),0.
    mm=sum(v*v for v in m);gg=sum(v*v for v in g);mg=sum(a*b for a,b in zip(m,g));my=sum(a*b for a,b in zip(m,y));gy=sum(a*b for a,b in zip(g,y));det=mm*gg-mg*mg
    candidates=[(max(0,my/mm),0),(0,max(0,gy/gg)),(0,0)]
    if det>1e-16:
        a,b=(my*gg-gy*mg)/det,(gy*mm-my*mg)/det
        if min(a,b)>=0:candidates.append((a,b))
    return min(candidates,key=lambda c:sum((a*c[0]+b*c[1]-v)**2 for a,b,v in zip(m,g,y)))
def rmse(a):return math.sqrt(st.mean(v*v for v in a))
def eval_models(groups):
    models={}
    for kind in ('frozen','frozen_plus_ingress','scaled_membrane','scaled_plus_ingress'):
        folds=[]
        for k,rows in groups.items():
            train=[r for j,x in groups.items() if j!=k for r in x];c=fit(train,kind)
            folds.append(dict(held_out=k,n=len(rows),coefficients=c,rmse=rmse([c[0]*r['membrane']+c[1]*r['ambient_gradient_kpa']-r['measured'] for r in rows])))
        models[kind]={'folds':folds,'macro_rmse':st.mean(r['rmse'] for r in folds),'all_data_fit_descriptive':fit([r for x in groups.values() for r in x],kind)}
    return models
def step(a):
    segments=[]
    for label,lo,hi,q in [('pre_valve',0,30,0),('valve_transient',45,120,0),('pump_off',150,600,0),('1200_early',690,1000,.478),('1200_stable',1200,5000,.478),('2400_early',5700,6500,.847),('2400_late',6500,13000,.847)]:
        x=[r for r in a if lo<=r[0]<hi and valid(r)]
        segments.append(dict(label=label,start_s=lo,end_s=hi,samples=len(x),mean_pO2_pa=st.mean(r[9] for r in x),mean_total_pa=st.mean(r[5] for r in x),flux_umol_s=slope([r[0] for r in x],[inv(r) for r in x]),mean_current_ma=st.mean(r[13] for r in x),predicted_membrane_scenarios={str(w):st.mean(3*K*1e6*(q/.663)**(1/3)*(w-r[9]) for r in x) if q else 0 for w in (14000,17660,18900)}))
    return segments
def fc_models(data):
    groups={k:v['samples'] for k,v in data['exp09'].items()};out={}
    for model in ('faraday_only','constant_residual','pressure_reaction','log_residual'):
        folds=[]
        for k,rows in groups.items():
            train=[r for j,x in groups.items() if j!=k for r in x];y=[r['signed_residual_umol_s'] for r in train]
            if model=='faraday_only':f=lambda r:0.
            elif model=='constant_residual':c=st.mean(y);f=lambda r:c
            elif model=='pressure_reaction':c=max(0,ls1([r['pO2_Pa']/20950 for r in train],y));f=lambda r:c*r['pO2_Pa']/20950
            else:
                x=[math.log(math.sqrt(r['pO2_Pa']/20950)) for r in train];b=slope(x,y);a=st.mean(y)-b*st.mean(x);f=lambda r:a+b*math.log(math.sqrt(r['pO2_Pa']/20950))
            folds.append(dict(held_out=k,n=len(rows),rmse=rmse([f(r)-r['signed_residual_umol_s'] for r in rows])))
        out[model]=dict(folds=folds,macro_rmse=st.mean(r['rmse'] for r in folds))
    return out
def main():
    p=Path('verified-experiments.tgz')
    if hashlib.sha256(p.read_bytes()).hexdigest()!=SHA:raise ValueError('archive mismatch')
    gas=json.loads(Path('r0d1c2-results.json').read_text())
    if gas['source_sha256']!=SHA:raise ValueError('source mismatch')
    groups={}
    with tarfile.open(p) as t:
        for n,rpm,w0,w1,lo,q in REC:
            a=read(t,n);duration=a[-1][0];groups[str(rpm)]=blocks(a,lo,20000,q,lambda s:w0+(w1-w0)*s/duration)
        step_rows=read(t,5);steps=step(step_rows)
    result=dict(stage='R0D1C4',status='PARTIAL_HYPOTHESES_TESTED_IDENTIFICATION_HOLD',source_sha256=SHA,exp10_step=steps,exp10_05_rows=len(step_rows),exp10_05_duration_s=step_rows[-1][0],recovery_blocks=groups,recovery_models=eval_models(groups),fc_models=fc_models(gas),limitations=['Block-average regression slopes, not full free-run trajectories. Retrospective; no blind external test; one run per rpm.','Ambient gradient proxy from channel 6 and dry 20.95% O2; logger schema and humidity unresolved. Nonnegative ingress coefficient is a hypothesis, not measured leak.','Pump off membrane flow set to zero only for diagnostic forced-flow term; diffusion/valve mixing not modeled. EXP10-05 water pO2 not recorded in notes; scenarios only.','EXP09 residual includes all non-Faradaic processes: pressure reaction is not unique identification. Different configurations between runs.','No joint validated predictive model or RUN008 update.'],physical_janus_runs=0,run008_modified=False)
    Path('r0d1c4-results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','exp10_05_rows','exp10_05_duration_s','exp10_step','recovery_models','fc_models')},indent=2))
if __name__=='__main__':main()
