"""R0D1C1: independently reconstruct EXP09 coefficients and EXP03 volume.
Stdlib only. Source scripts are inspected, never executed."""
import argparse, hashlib, json, math, statistics as st, tarfile, bisect
from pathlib import Path
from audit_inventory import load, window, slope, WINDOWS, REC, SHA, volume_controls
R=8.314462618
VFC=.002210447+.000024
VFULL=.007061
def fc_rows(t,n):return load(t,f"exp09_fuelcell_calibration/data_exp09_{n:02}.txt")
def features(i,p):return [i,math.log(math.sqrt(p/20950)),1.]
def dot(a,b):return math.fsum(x*y for x,y in zip(a,b))
def fit(X,y):
    a=[[math.fsum(r[i]*r[j] for r in X) for j in range(3)]+[math.fsum(r[i]*v for r,v in zip(X,y))] for i in range(3)]
    for i in range(3):
        k=max(range(i,3),key=lambda j:abs(a[j][i]));a[i],a[k]=a[k],a[i]
        f=a[i][i];a[i]=[x/f for x in a[i]]
        for j in range(3):
            if i!=j:
                f=a[j][i];a[j]=[x-f*v for x,v in zip(a[j],a[i])]
    return [x[-1] for x in a]
def rmse(x):return math.sqrt(st.mean(v*v for v in x))
def segments(a):
    cuts=[0]+[i for i in range(1,len(a)) if a[i][17]!=a[i-1][17]]+[len(a)]
    out=[]
    for l,h in zip(cuts[:-1],cuts[1:]):
        end=a[h][0] if h<len(a) else a[-1][0]
        x=[v for v in a[l:h] if end-180<=v[0]<end and v[9]>0]
        if len(x)<15:continue
        ts=[v[0] for v in x];ps=[v[9] for v in x];temps=[v[1]+273.15 for v in x]
        dp=slope(ts,ps);I=st.mean(v[13] for v in x)*.001
        out.append({"lights":x[0][17],"current_A":I,"pO2_Pa":st.mean(ps),"samples":len(x),"purge_samples":sum(v[18]>0 for v in x),"pressure_slope_umol_s":-dp*VFC/R/st.mean(temps)*1e6,"inventory_slope_umol_s":-slope(ts,[VFC*p/R*T**-1 for p,T in zip(ps,temps)])*1e6,"archival_field_index_reconstruction_umol_s":-dp*VFC/R/(273.15+dp)*1e6})
    return out
def fc_fit(t):
    rows={n:segments(fc_rows(t,n)) for n in (1,2,3,5)};train=rows[5]
    X=[features(r["current_A"],r["pO2_Pa"]) for r in train]
    models={}
    for key in ("pressure_slope_umol_s","inventory_slope_umol_s","archival_field_index_reconstruction_umol_s"):
        y=[r[key] for r in train];c=fit(X,y)
        models[key]={"coefficients":c,"train_rmse_umol_s":rmse([dot(v,c)-q for v,q in zip(X,y)]),"cross_run_screen":{str(n):{"segments":len(rows[n]),"rmse_umol_s":rmse([dot(features(r["current_A"],r["pO2_Pa"]),c)-r["inventory_slope_umol_s"] for r in rows[n]])} for n in (1,2,3)}}
    return {"segments":rows,"models":models,"boundary":"EXP09-05 fit, tests on EXP09-01/02 two hydrosticks and EXP09-03 one; not blind and configuration varies. Effective total O2 depletion not pure FC consumption. 15-sample minimum excludes tiny windows; initial partial segment retained."}
def avg(a):return [st.mean(a[i:i+5]) for i in range(len(a)-4)]
def grad(a):return [a[1]-a[0]]+[(a[i+1]-a[i-1])/2 for i in range(1,len(a)-1)]+[a[-1]-a[-2]]
def leak_selection(t,n,lo,hi):
    a=load(t,f"exp03_volume_test/data_exp03_{n:02}.txt");ts=[v[0] for v in a]
    l=min(range(len(a)),key=lambda i:abs(ts[i]-lo));h=min(range(len(a)),key=lambda i:abs(ts[i]-hi))
    p=avg([v[5] for v in a]);d=avg([v/w for v,w in zip(grad(p),grad(avg(ts)))])
    return p[l:h],d[l:h]
def interp(x,xp,yp):
    i=bisect.bisect_right(xp,x)
    if i==0:return yp[0]
    if i==len(xp):return yp[-1]
    return yp[i-1]+(yp[i]-yp[i-1])*(x-xp[i-1])/(xp[i]-xp[i-1])
def volume(t):
    old=volume_controls(t);v=st.mean(x["container_l"] for x in old["container_controls"])
    p5,d5=leak_selection(t,10,105,230);p6,d6=leak_selection(t,9,93,395);pa=101871
    x5=[(pa-p)/pa for p in p5[::-1]];x6=[(pa-p)/pa for p in p6[::-1]]
    # np.interp assumes increasing xp. Verify before using.
    if any(b<a for a,b in zip(x5,x5[1:])):raise ValueError("nonmonotonic interpolation coordinates")
    y=[interp(x,x5,[d/pa for d in d5[::-1]]) for x in x6];x=[d/pa for d in d6[::-1]]
    a=st.mean(x);b=st.mean(y);factor=math.fsum((i-a)*(j-b) for i,j in zip(x,y))/math.fsum((i-a)**2 for i in x)
    return {"ratio":factor,"container_l":v,"full_l":factor*(v+.0245)-.0245,"published_l":7.061,"samples":len(x),"method":"Five-point smooth, index gradient ratio, five-point smooth, author windows, interpolation and analytic minimum of residual variance."}
def purge(a,V):
    ts=[r[0] for r in a];inv=[V*r[9]/R/(r[1]+273.15)*1e6 for r in a]
    events=[i for i in range(len(a)) if a[i][18]>0 and (i==0 or a[i-1][18]==0)]
    values=[]
    for i in events:
        tau=ts[i];pre=[j for j in range(bisect.bisect_left(ts,tau-30),bisect.bisect_right(ts,tau-5)) if a[j][9]>1];post=[j for j in range(bisect.bisect_left(ts,tau+5),bisect.bisect_right(ts,tau+30)) if a[j][9]>1]
        if min(len(pre),len(post))<5:continue
        def intercept(js):
            x=[ts[j]-tau for j in js];y=[inv[j] for j in js]
            return st.mean(y)-slope(x,y)*st.mean(x)
        values.append(intercept(pre)-intercept(post))
    return {"flag_rising_edges":len(events),"usable_windows":len(values),"median_signed_jump_umol":st.median(values) if values else None,"sum_signed_jump_umol":sum(values),"negative_count":sum(x<0 for x in values),"range_umol":[min(values),max(values)] if values else None,"interpretation":"Signed inventory discontinuity, not measured purge mass. Anode purge may affect cathode indirectly. Negative jumps retained; no forced-positive loss."}
def loaded_screen(t,c):
    rr=[]
    for name,s,n,lo,hi,ref in WINDOWS:
        a=window(load(t,f"exp{s:02}"+("_production" if s==8 else "")+f"/data_exp{s:02}_{n:02}.txt"),lo,hi)
        inv=slope([x[0] for x in a],[VFULL*x[9]/R/(x[1]+273.15) for x in a])*1e6
        f=inv+st.mean(dot(features(x[13]*.001,x[9]),c) for x in a)
        rr.append({"run":name,"flux_umol_s":f,"reference_umol_s":ref,"residual":f-ref})
    return {"runs":rr,"rmse_umol_s":rmse([r["residual"] for r in rr]),"boundary":"Same retrospective windows, unmeasured loss unresolved; do not replace production model."}
def main():
    p=argparse.ArgumentParser();p.add_argument("--archive",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    if hashlib.sha256(a.archive.read_bytes()).hexdigest()!=SHA:raise ValueError("archive mismatch")
    with tarfile.open(a.archive,"r:gz") as t:
        fc=fc_fit(t);vol=volume(t);c=fc["models"]["inventory_slope_umol_s"]["coefficients"]
        purges={"09.05":purge(fc_rows(t,5),VFC),"08.02":purge(load(t,"exp08_production/data_exp08_02.txt"),VFULL)}
        for n,*_ in REC:purges[f"10.{n:02}"]=purge(load(t,f"exp10/data_exp10_{n:02}.txt"),VFULL)
        result={"stage":"R0D1C1","status":"PARTIAL_VOLUME_REPRODUCED_FC_CORRECTION_TRANSFER_HOLD","source_sha256":SHA,"fc":fc,"volume":vol,"purge":purges,"loaded_screen":loaded_screen(t,c),"column_mapping":{"index_base":0,"corroborated":{"0":"timestamp","9":"O2 partial pressure inferred from threshold commands","13":"current mA inferred from load steps","17":"lights load state matches documented 0/1/2/3 sequence","18":"purge flag candidate supported by binary periodic pulses"},"provisional":{"1":"bme1 temperature C","2":"bme2 temperature C","5":"bme2 pressure Pa","10":"unresolved; do NOT assert gas flow"},"logger_module_present":False,"boundary":"No original bugs_data schema in archive; mapping requires logger source or author documentation."},"physical_janus_runs":0,"run008_modified":False}
    a.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
