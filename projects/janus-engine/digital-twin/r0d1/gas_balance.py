"""R0D1C2: separate ideal stack current from signed residual, not measured loss."""
import json, math, statistics as st
from pathlib import Path
F=96485.33212
N=13 # exp09_fuelcell_calibration/fc_performance.py: i/4/F*13
BETA=N*1e6/(4*F)
SHA="fdcf8d27c8d04e7f47db14039c366b79e12ccc7e00d789a198189be3c931db9a"
def read(p):
    a=json.loads(Path(p).read_text())
    if a["source_sha256"]!=SHA:raise ValueError("provenance mismatch")
    return a
def feature(r):return math.log(math.sqrt(r["pO2_Pa"]/20950))
def residual(r):return r["inventory_slope_umol_s"]-BETA*r["current_A"]
def coefficients(rows):
    x=[feature(r) for r in rows];y=[residual(r) for r in rows]
    xm,ym=st.mean(x),st.mean(y)
    b=sum((v-xm)*(w-ym) for v,w in zip(x,y))/sum((v-xm)**2 for v in x)
    return ym-b*xm,b
def rmse(v):return math.sqrt(st.mean(x*x for x in v))
def main():
    fc=read("r0d1c1-results.json");raw=read("r0d1c-results.json");curves=read("r0d1b-results.json")
    runs=fc["fc"]["segments"];train=runs["5"];a,b=coefficients(train)
    c=st.mean(residual(r) for r in train);screens={}
    for k,rows in runs.items():
        samples=[dict(r,faradaic_umol_s=BETA*r["current_A"],signed_residual_umol_s=residual(r)) for r in rows]
        screens[k]={"samples":samples,"n":len(rows),"residual_range_umol_s":[min(map(residual,rows)),max(map(residual,rows))],"negative_residuals":sum(residual(r)<0 for r in rows),"no_load_residuals_umol_s":[residual(r) for r in rows if r["current_A"]<.001],"rmse_faraday_only":rmse([residual(r) for r in rows]),"rmse_constant_residual":rmse([c-residual(r) for r in rows]),"rmse_log_residual":rmse([a+b*feature(r)-residual(r) for r in rows])}
    loaded=[]
    points={r["run_id"]:r for r in curves["series"]["individual_recorded_pressure"]["points"]}
    kref=curves["series"]["figure3_common_pressure"]["models"]["laminar_scaling"]["all_data_fit_k_descriptive_only"]
    for r in raw["loaded"]:
        p=r["mean_p_pa"];I=r["mean_current_ma"]*.001;ideal=BETA*I
        pred_res=a+b*math.log(math.sqrt(p/20950)); flux=r["inventory_umol_s"]+ideal+pred_res
        q=points[r["run"]];mem=kref*3*(q["p_water_pa"]-p)*(q["flow_l_s"]/.663)**(1/3)*1e6
        loaded.append({"run":r["run"],"faradaic_umol_s":ideal,"inventory_umol_s":r["inventory_umol_s"],"predicted_net_residual_umol_s":pred_res,"inferred_membrane_umol_s":flux,"published_flux_umol_s":r["reference_umol_s"],"comparison_error_umol_s":flux-r["reference_umol_s"],"required_residual_using_membrane_model_umol_s":mem-r["inventory_umol_s"]-ideal,"membrane_model_umol_s":mem})
    folds=[]
    for k,rows in runs.items():
        aa,bb=coefficients([r for j,rr in runs.items() if j!=k for r in rr])
        folds.append({"test_run":k,"train_runs":[j for j in runs if j!=k],"n":len(rows),"coefficients":[aa,bb],"rmse_umol_s":rmse([aa+bb*feature(r)-residual(r) for r in rows])})
    out={"stage":"R0D1C2","status":"PARTIAL_NET_RESIDUAL_IDENTIFIED_COMPONENTS_HOLD","source_sha256":SHA,"faraday_stack_cells":N,"faraday_umol_per_A_s":BETA,"train_run":"09.05","constant_residual_umol_s":c,"log_residual_coefficients":[a,b],"exp09":screens,"grouped_leave_run_out_descriptive":folds,"loaded":loaded,"loaded_rmse_umol_s":rmse([r["comparison_error_umol_s"] for r in loaded]),"recovery_membrane_model_equivalent_residual":raw["recovery"],"physical_janus_runs":0,"run008_modified":False,"limitations":["Assumes 13 active series cells and ideal four-electron oxygen reduction; current-derived term not a direct gas flow measurement.","EXP09 bypass net residual combines crossover, leakage, back-diffusion, sensor and inventory errors. Negative residuals preserved, not clipped.","One scalar oxygen balance cannot identify each loss; membrane-model residual also confounded with model error. EXP09 configurations differ and public cross-validation is not blind.","Loaded pressure-log term uses mean pressure, not per-sample integral. Comparison against published aggregate does not independently identify true flux.","No transfer qualification; no unmeasured auxiliary or loss set to zero."]}
    Path("r0d1c2-results.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({k:v for k,v in out.items() if k not in ("exp09","loaded","recovery_membrane_model_equivalent_residual")},indent=2))
if __name__=="__main__":main()
