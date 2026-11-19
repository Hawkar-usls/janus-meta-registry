"""Independent reconstruction of the experimental points and dynamic O2 audit.
Source: Merckelbach & Georgopanos, doi:10.1002/advs.202410358;
archive doi:10.5281/zenodo.12784504. No execution of author code."""
import argparse, hashlib, json, math, statistics, tarfile
from pathlib import Path
from calibrate import evaluate, self_test
SHA="fdcf8d27c8d04e7f47db14039c366b79e12ccc7e00d789a198189be3c931db9a"
FLOWS={1200:.478,1800:.663,2400:.847}
# Author-documented no-fuel-cell recovery conditions; retain all five, including 2100 rpm.
RECOVERY=[(8,1200,18050,17700,5000),(14,1540,18300,18300,5000),(10,1800,17050,17800,13000),(12,2100,20400,21000,5000),(6,2400,18050,18450,5000)]
def rows(t):
    result=[]
    for line in t.extractfile("experiments/exp_aggregate_data.txt").read().decode().splitlines():
        if not line.strip() or line.startswith("#"): continue
        i,n,p,current,w,rpm=line.split()
        result.append(dict(run_id=i,flux_mol_s=float(n)*1e-6,p_internal_pa=float(p),current_ma=float(current),p_water_pa=float(w),flow_l_s=FLOWS[int(rpm)]))
    if len(result)!=9: raise ValueError("unexpected point count")
    return result
def normalize(points,mode):
    return [dict(r,delta_p_pa=(17660 if mode=="figure3_common_pressure" else r["p_water_pa"])-r["p_internal_pa"]) for r in points]
def raw(t,n):
    data=[];seen=set();invalid=0
    for line in t.extractfile(f"experiments/exp10/data_exp10_{n:02}.txt"):
        try: x=list(map(float,line.split()))
        except ValueError: invalid+=1;continue
        if len(x)!=19 or not all(map(math.isfinite,x)) or x[0]<=1e9 or x[0] in seen:
            invalid+=1;continue
        seen.add(x[0]);data.append(x)
    data.sort(key=lambda x:x[0])
    start=data[0][0]
    return [(x[0]-start,x[9],x[1]+273.15,x[13],x[-1]) for x in data],invalid
def recovery(t, spec, kref):
    n,rpm,w0,w1,tmin=spec
    data,invalid=raw(t,n);duration=data[-1][0]
    raw_window=[x for x in data if tmin<=x[0]<=20000]
    # Exclude sensor zeros; no interpolation over missing points.
    a=[x for x in raw_window if x[1]>1 and 270<x[2]<330]
    if len(a)<2: raise ValueError("empty recovery window")
    # Intermediate pump speeds: linear interpolation of the published flow endpoints.
    q=.478+(.847-.478)*(rpm-1200)/1200
    if rpm in FLOWS:q=FLOWS[rpm]
    kpred=kref*(q/.663)**(1/3)
    V=.007061;R=8.314;A=3.
    w=lambda x:w0+(w1-w0)*x/duration
    inv=lambda x:V*x[1]/(R*x[2])
    inv0=inv(a[0]);m=inv0
    integral=0.;xx=0.;xy=0.;errors=[];gaps=[]
    curves=[]
    for i,x in enumerate(a):
        if i:
            prev=a[i-1];dt=x[0]-prev[0];gaps.append(dt)
            integral+=dt*((w(prev[0])-prev[1])+(w(x[0])-x[1]))/2
            yy=inv(x)-inv0;xx+=integral**2;xy+=integral*yy
            # Free-run inventory prediction, driven only by recorded temperature and prescribed water pO2.
            # Exact step under midpoint exogenous forcing.
            tm=(x[2]+prev[2])/2;wm=(w(x[0])+w(prev[0]))/2
            rate=kpred*A*R*tm/V
            eq=V*wm/(R*tm)
            m=eq+(m-eq)*math.exp(-rate*dt)
        pred=m*R*x[2]/V
        errors.append(pred-x[1])
        if i==0 or i==len(a)-1 or i%300==0:
            curves.append({"t_s":x[0],"measured_pa":x[1],"predicted_pa":pred,"water_pa":w(x[0])})
    kfit=xy/xx/A
    return {"run_id":f"10.{n}","rpm":rpm,"flow_l_s":q,"samples":len(a),
      "invalid_or_duplicate_rows_full_file":invalid,"window_excluded":len(raw_window)-len(a),
      "max_gap_s":max(gaps),"window_s":[tmin,20000],"median_current_ma":statistics.median(x[3] for x in a),
      "purge_field_values":sorted(set(x[4] for x in a)),
      "fitted_k":kfit,"steady_predicted_k":kpred,"ratio":kfit/kpred,
      "pressure_rmse_pa":math.sqrt(sum(e*e for e in errors)/len(errors)),
      "pressure_end_error_pa":errors[-1],"curves":curves}
def main():
    p=argparse.ArgumentParser();p.add_argument("--archive",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    if hashlib.sha256(a.archive.read_bytes()).hexdigest()!=SHA:raise ValueError("archive SHA256 mismatch")
    with tarfile.open(a.archive,"r:gz") as t:
        points=rows(t);series={}
        for mode in ("figure3_common_pressure","individual_recorded_pressure"):
            normalized=normalize(points,mode);series[mode]={"points":normalized,"models":evaluate(normalized)}
        kref=series["figure3_common_pressure"]["models"]["laminar_scaling"]["all_data_fit_k_descriptive_only"]
        rec=[recovery(t,s,kref) for s in RECOVERY]
    result={"stage":"R0D1B","status":"PARTIAL_AGGREGATE_REPRODUCTION_DYNAMIC_VALIDATION_OPEN",
      "source_sha256":SHA,"self_test":self_test(),"published_experimental_points":9,
      "physical_janus_runs":0,"full_figure3_reproduced":False,"run008_modified":False,
      "series":series,"dynamic_recovery_screen":rec,
      "limitations":["Published aggregate flux reconstructed as plotted, not independently derived from original loaded fuel-cell time windows.",
      "Raw channel mapping inferred from logged values and author plots; purge semantics and leak/volume corrections require independent audit.",
      "No-fuel-cell recovery screen includes all five documented runs; no repair of sensor zeros; water pressure interpolated from author notes; intermediate flow rates interpolated.",
      "Model extrapolation to new geometry is not validated. Only three flow groups. Public data is not an external blinded holdout.",
      "Full CFD Figure 3 curves require separate OpenFOAM archive."]}
    a.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],"models":{m:{k:v["metrics"] for k,v in s["models"].items()} for m,s in series.items()},"raw_recovery":[{k:v for k,v in x.items() if k!="curves"} for x in rec]},indent=2))
if __name__=="__main__":main()
