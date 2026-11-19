"""R0D1C independent inventory audit; no execution of external scripts."""
import argparse, hashlib, json, math, statistics, tarfile
from pathlib import Path

SHA="fdcf8d27c8d04e7f47db14039c366b79e12ccc7e00d789a198189be3c931db9a"
V=.007061
R=8.314462618
KREF=5.884527667675732e-11
REC=[(8,1200,18050,17700,5000),(14,1540,18300,18300,5000),(10,1800,17050,17800,13000),(12,2100,20400,21000,5000),(6,2400,18050,18450,5000)]
WINDOWS=[("8.2",8,2,18000,20400,1.990),("8.6",8,6,30000,33000,1.623),("8.7a",8,7,20000,27000,1.999),("8.7b",8,7,8000,12500,1.640),("8.8",8,8,10000,16500,1.630),("8.9",8,9,19000,23000,1.590),("8.10",8,10,18000,23000,1.600),("10.3",10,3,13000,19500,2.460),("10.4",10,4,13000,16800,2.520)]
PUMP={1200:.478,1500:.560,1800:.663,2100:27.46/36.29,2400:.847}
def load(t,path):
    rows={}
    for line in t.extractfile("experiments/"+path):
        try: x=list(map(float,line.split()))
        except ValueError: continue
        if len(x)==19 and x[0]>1e9 and all(map(math.isfinite,x)): rows.setdefault(x[0],x)
    a=[rows[k] for k in sorted(rows)]
    if not a: raise ValueError("empty raw file")
    start=a[0][0]
    for x in a:x[0]-=start
    return a
def window(a,lo,hi):
    rows=[x for x in a if lo<=x[0]<=hi and x[9]>1 and 0<x[1]<60]
    if len(rows)<2:raise ValueError("empty analysis window")
    return rows
def slope(t,y):
    a=statistics.mean(t);b=statistics.mean(y)
    return math.fsum((x-a)*(v-b) for x,v in zip(t,y))/math.fsum((x-a)**2 for x in t)
def flow(rpm):
    if rpm in PUMP:return PUMP[rpm]
    return PUMP[1500]+(PUMP[1800]-PUMP[1500])*(rpm-1500)/300
def recovery(t,spec):
    n,rpm,w0,w1,start=spec
    raw=load(t,f"exp10/data_exp10_{n:02}.txt")
    a=window(raw,start,20000)
    ts=[x[0] for x in a];p=[x[9] for x in a];temp=[x[1]+273.15 for x in a]
    g=[w0+(w1-w0)*x/raw[-1][0]-v for x,v in zip(ts,p)]
    integ=[0.]
    for i in range(1,len(a)):integ.append(integ[-1]+(ts[i]-ts[i-1])*(g[i]+g[i-1])/2)
    def fit(T):
        inv=[V*pp/(R*theta) for pp,theta in zip(p,T)]
        return math.fsum(i*(v-inv[0]) for i,v in zip(integ,inv))/math.fsum(i*i for i in integ)/3
    k=fit(temp);kfixed=fit([statistics.median(temp)]*len(a));kp=KREF*(flow(rpm)/.663)**(1/3)
    # Dry non-O2 inventory is a diagnostic, not a unique leak estimate.
    other=[V*(x[4]-x[9]-x[7]/100*610.94*math.exp(17.625*x[1]/(x[1]+243.04)))/(R*T) for x,T in zip(a,temp)]
    return {"rpm":rpm,"samples":len(a),"T_range_C":[min(temp)-273.15,max(temp)-273.15],"channel10_median":statistics.median(x[10] for x in a),"channel10_zero_fraction":sum(x[10]==0 for x in a)/len(a),"k_ratio":k/kp,"temperature_effect_percent":100*(k/kfixed-1),"volume_required_l":1000*V*kp/k,"volume_uncertainty_percent":.02/7.061*100,"unmodelled_sink_umol_s":3*(kp-k)*statistics.mean(g)*1e6,"inert_inventory_slope_umol_s":1e6*slope(ts,other),"purge_nonzero_rows":sum(x[18]!=0 for x in a)}
def loaded(t,spec):
    name,s,n,lo,hi,ref=spec
    a=window(load(t,f"exp{s:02}"+("_production" if s==8 else "")+f"/data_exp{s:02}_{n:02}.txt"),lo,hi)
    ts=[x[0] for x in a];p=[x[9] for x in a];temp=[x[1]+273.15 for x in a];I=[x[13]*1e-3 for x in a]
    # Published Eq.13 coefficients; archived fc_performance.py uses log(sqrt(p/20950)).
    fc=statistics.mean((3.25e-5*i+2.24e-7*math.log(math.sqrt(pp/20950))+1.19e-6)*1e6 for i,pp in zip(I,p))
    inventory=1e6*slope(ts,[V*pp/(R*T) for pp,T in zip(p,temp)])
    flux=fc+inventory
    return {"run":name,"window_s":[lo,hi],"samples":len(a),"mean_p_pa":statistics.mean(p),"mean_current_ma":statistics.mean(I)*1e3,"inventory_umol_s":inventory,"fc_umol_s":fc,"flux_umol_s":flux,"reference_umol_s":ref,"delta_umol_s":flux-ref,"purge_nonzero_rows":sum(x[18]!=0 for x in a)}
def volume_controls(t):
    # Linear pressure extrapolation on the author's EXP03 valve windows.
    results=[]
    for n,to,p1,t1 in [(4,399.1,102067,24.97),(5,675,102058,25.34)]:
        x=load(t,f"exp03_volume_test/data_exp03_{n:02}.txt")
        idx=min(range(len(x)),key=lambda i:abs(x[i][0]-to))
        a=x[idx-52:idx-2];b=x[idx+15:idx+65]
        def intercept(rows):
            tt=[v[0]-to for v in rows];pp=[v[5] for v in rows]
            return statistics.mean(pp)-slope(tt,pp)*statistics.mean(tt)
        p2,p3=intercept(a),intercept(b)
        T2=273.15+statistics.mean(v[2] for v in a);T3=273.15+statistics.mean(v[2] for v in b)
        factor=(p1*T3/(t1+273.15)-p3)/(p3-p2*T3/T2)
        results.append({"run":n,"factor":factor,"container_l":factor*.0245})
    # Matched total-pressure bins, temperature-corrected pressure slopes.
    # This deliberately differs from the author's variance/interpolation estimator.
    bins=[]
    for lo in (80000,85000,90000,95000):
        slopes=[];counts=[]
        for n,l,h in [(9,93,395),(10,105,230)]:
            rows=[v for v in load(t,f"exp03_volume_test/data_exp03_{n:02}.txt") if l<=v[0]<=h and lo<=v[5]<lo+5000]
            counts.append(len(rows))
            if len(rows)<3:raise ValueError("too few leak control samples")
            slopes.append(slope([v[0] for v in rows],[v[5]/(v[2]+273.15) for v in rows]))
        ratio=slopes[1]/slopes[0]
        bins.append({"pressure_pa":[lo,lo+5000],"samples_full_bypass":counts,"ratio":ratio,"total_l_screen":ratio*(statistics.mean(v["container_l"] for v in results)+.0245)})
    return {"container_controls":results,"matched_pressure_leak_control":bins,"boundary":"Artificial calibrated leak plug differs from operating seals. Small sample counts and estimator sensitivity; screening only, not validated total volume or runtime leak."}

def main():
    p=argparse.ArgumentParser();p.add_argument("--archive",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    if hashlib.sha256(a.archive.read_bytes()).hexdigest()!=SHA:raise ValueError("archive mismatch")
    with tarfile.open(a.archive,"r:gz") as t:
        rec=[recovery(t,r) for r in REC];loaded_rows=[loaded(t,w) for w in WINDOWS]
        volumes=volume_controls(t)
        script=t.extractfile("experiments/exp10/p_curves.py").read().decode()
        excluded_2100="Tscales[3] = np.nan" in script and "idx = np.array([0,1,2,4])" in script
    out={"stage":"R0D1C","status":"PARTIAL_RAW_INVENTORY_AUDIT_CAUSAL_ATTRIBUTION_HOLD","source_sha256":SHA,"recovery":rec,"volume_controls":volumes,"loaded":loaded_rows,"loaded_rmse":math.sqrt(statistics.mean(r["delta_umol_s"]**2 for r in loaded_rows)),"author_excluded_2100_from_linear_fit":excluded_2100,"physical_janus_runs":0,"full_cfd_reproduced":False,"run008_modified":False,"limitations":["Channel 10 is inferred to be gas flow; sensor schema not established independently; zero may be sensor fault.","Unmodelled sink is an equivalent residual, not a leak measurement. Purge flags are counted as nonzero samples, not distinct events; losses unquantified.","Fixed loaded windows selected retrospectively from notes and current traces; not exact published windows or blind validation.","Inventory slope plus published FC coefficients is an independent calculation, not independent FC calibration; neglects unknown leak and purge flux.","Volume valve controls independently reconstructed. Matched-pressure leak test is a screening estimator, not exact paper algorithm or runtime leak measurement.","All five recovery runs retained, including 2100 rpm."]}
    a.output.write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out,indent=2))
if __name__=="__main__":main()
