"""R0D1C3: compare frozen twin to pinned CFD and identify signed net residuals.
Never interpret a net inventory change as a unique physical leakage measurement."""
import hashlib, json, math, statistics as st, tarfile
from pathlib import Path
from audit_inventory import slope
SHA="fdcf8d27c8d04e7f47db14039c366b79e12ccc7e00d789a198189be3c931db9a"
CFD_SHA="3f5d6e8fe5d07cbd022ac63c08b7873571b3333176fec7ef5303be2fe984ed4d"
V=.0070588701445034046
R=8.314462618
K=5.884527667675732e-11
def read(p):
    x=json.loads(Path(p).read_text())
    if x["source_sha256"]!=SHA:raise ValueError("experiment provenance mismatch")
    return x
def cfd_comparison():
    d=json.loads(Path(__file__).with_name("cfd-reference.json").read_text())
    if d["sha256"]!=CFD_SHA or d["receipt"]["run_id"]!=44590687016:raise ValueError("CFD receipt mismatch")
    wanted={(r,p) for r in (1200,1800,2400) for p in range(3000,17001,2000)}|{(1500,7000),(2100,7000)}
    if len(d["points"])!=26 or {(x["rpm"],x["internal_pO2_pa"]) for x in d["points"]}!=wanted:raise ValueError("CFD coverage")
    result=[]
    for x in d["points"]:
        q=x["water_inlet_m3_s"]*1000
        y=K*3*x["delta_p_pa"]*(q/.663)**(1/3)*1e6
        ref=x["membrane_flux_umol_s"]
        result.append(dict(x,twin_flux_umol_s=y,error_umol_s=y-ref,relative_abs_error=abs(y-ref)/ref,water_relative_imbalance=abs(x["water_net_m3_s"]/x["water_inlet_m3_s"])))
    def metrics(a):
        return {"n":len(a),"rmse_umol_s":math.sqrt(st.mean(x["error_umol_s"]**2 for x in a)),"mare":st.mean(x["relative_abs_error"] for x in a),"max_abs_scalar_closure_umol_s":max(abs(x["signed_membrane_scalar_closure_umol_s"]) for x in a),"max_water_relative_imbalance":max(x["water_relative_imbalance"] for x in a)}
    return {"receipt":d["receipt"],"all":metrics(result),"figure3":metrics([x for x in result if x["figure3_visible"]]),"by_rpm":{str(r):metrics([x for x in result if x["rpm"]==r]) for r in (1200,1500,1800,2100,2400)},"points":result,"boundary":"Shared publication, not independent validation. Snapshot at solver time 1 s; scalar inventory accumulation and convergence are not established."}
def leak_controls(t):
    out=[]
    for n in (1,2):
        data={};bad=0
        for l in t.extractfile(f"experiments/exp00_leaktest/leak_test0{n}.txt"):
            try:
                x=list(map(float,l.split()))
                if len(x)!=19 or not all(map(math.isfinite,x)) or x[0]<=1e9:raise ValueError()
            except ValueError:bad+=1;continue
            data.setdefault(x[0],x)
        a=[data[k] for k in sorted(data)];t0=a[0][0];duration=a[-1][0]-t0
        bins={}
        for x in a:bins.setdefault(int((x[0]-t0)//600)*600,[]).append(x)
        wins=[]
        for lo in range(0,int(duration)-600+1,600):
            b=bins.get(lo,[])
            if len(b)<250 or b[-1][0]-b[0][0]<580 or max(y[0]-x[0] for x,y in zip(b,b[1:]))>10 or any(abs(x[13])>1 or x[17]!=0 or x[9]<500 for x in b):continue
            ts=[x[0]-t0 for x in b]
            o=[V*x[9]/(R*(x[2]+273.15))*1e6 for x in b]
            dry=[V*(x[5]-x[8]/100*610.94*math.exp(17.625*x[2]/(x[2]+243.04)))/(R*(x[2]+273.15))*1e6 for x in b]
            wins.append({"start_s":lo,"samples":len(b),"mean_pO2_pa":st.mean(x[9] for x in b),"mean_total_pa":st.mean(x[5] for x in b),"o2_inventory_slope_umol_s":slope(ts,o),"dry_inventory_slope_umol_s":slope(ts,dry),"flag18_nonzero_samples":sum(x[18]!=0 for x in b)})
        out.append({"run":n,"raw_unique_rows":len(a),"invalid_lines_including_headers":bad,"duration_s":duration,"windows":wins})
    return out
def main():
    archive=Path("verified-experiments.tgz")
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=SHA:raise ValueError("archive mismatch")
    cfd=cfd_comparison()
    with tarfile.open(archive,"r:gz") as t:leak=leak_controls(t)
    gas=read("r0d1c2-results.json")
    controls=[dict(r) for k,v in gas["exp09"].items() for r in v["samples"] if r["current_A"]<.001]
    rec=gas["recovery_membrane_model_equivalent_residual"]
    # Only conditional net-model residuals, not bounds on physical leakage.
    losses=[x["signed_residual_umol_s"] for x in controls]
    equivalent=[x["unmodelled_sink_umol_s"] for x in rec]
    allwindows=[w for x in leak for w in x["windows"]]
    out={"stage":"R0D1C3","status":"PARTIAL_CFD_AGREEMENT_NET_RESIDUAL_CONSTRAINED_COMPONENTS_NOT_IDENTIFIED","source_sha256":SHA,"cfd":cfd,"exp00":leak,"exp00_summary":{"raw_rows":sum(x["raw_unique_rows"] for x in leak),"windows":len(allwindows),"window_samples":sum(w["samples"] for w in allwindows),"o2_inventory_slope_range_umol_s":[min(w["o2_inventory_slope_umol_s"] for w in allwindows),max(w["o2_inventory_slope_umol_s"] for w in allwindows)],"strict_flag18_zero_windows":sum(w["flag18_nonzero_samples"]==0 for w in allwindows)},"exp09_no_load":{"n":len(controls),"range_umol_s":[min(losses),max(losses)],"samples":controls},"exp10_recovery":{"n":len(rec),"equivalent_signed_residual_range_umol_s":[min(equivalent),max(equivalent)],"runs":rec},"identifiability":{"equation":"dn/dt = membrane - faradaic - loss + ingress","counterexample":"For any h>=0, loss+h and ingress+h produce identical inventory observations; membrane and loss also trade off. No unique true-loss bound from these records without extra assumptions.","conditional_ranges_only":True},"limitations":["EXP00 old sensor, unknown gas configuration and volume; use reconstructed volume only as scale assumption. No-load current criterion does not prove FC disconnected.","600 s nonoverlapping screening windows, abs(I)<=1mA, state17=0, pO2>=500Pa, >=250 rows, span>=580s and no gap>10s. Flag18 retained, not confirmed purge; no qualifying fully flag-free window. Not an operational leak calibration.","EXP09 unloaded FC connected/possibly fueled, not physically disconnected; EXP10 recovery has separate conditions.","CFD output shared provenance and scalar balance not closed; no independent validation or solver rerun.","All five EXP10 recovery runs retained; residual may incorporate model discrepancy."],"physical_janus_runs":0,"run008_modified":False}
    Path("r0d1c3-results.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({k:out[k] for k in ("status","exp00_summary","identifiability")},indent=2))
    print(json.dumps({"cfd_all":cfd["all"],"exp09_no_load":{k:v for k,v in out["exp09_no_load"].items() if k!="samples"},"exp10_range":out["exp10_recovery"]["equivalent_signed_residual_range_umol_s"]},indent=2))
if __name__=="__main__":main()
