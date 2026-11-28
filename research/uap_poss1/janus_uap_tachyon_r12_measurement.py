#!/usr/bin/env python3
import csv, hashlib, io, json, math, pathlib, subprocess, sys, tempfile, urllib.request
import numpy as np
import h5py
from scipy import signal
R=pathlib.Path("registry/uap")
P=R/"JANUS-UAP-TACHYON-R1.2-MEASUREMENT-CONTRACT-2026-11-28-v1.0.json"
O=R/"JANUS-UAP-TACHYON-R1.2-MEASUREMENT-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text()); c=299792458.0
checks=[]
def check(name,passed,detail):
    checks.append({"id":name,"pass":bool(passed),"detail":detail})
    if not passed:raise AssertionError(name)
def advance(L,r):
    # cancellation-free 1 - 1/sqrt(1+r^2)
    h=math.hypot(1,r)
    return L/c*r*r/(h*(h+1))
rr=p["frozen_exam"]["synthetic_ratios"];vv=[math.hypot(1,r) for r in rr]
check("KINEMATICS",all(a<b for a,b in zip(vv,vv[1:])) and all(math.isclose(advance(1e6,r),1e6/c*(1-1/v),rel_tol=1e-9) for r,v in zip(rr,vv)),{"r":rr,"v_over_c":vv})
check("BASELINE_SCALING",all(math.isclose(advance(2e6,r),2*advance(1e6,r),rel_tol=1e-14) for r in rr),{"ratios":rr})
check("STABLE_SMALL_RATIO",math.isclose(advance(1e6,1e-10),1e6/c*0.5e-20,rel_tol=1e-14),{"advance_s":advance(1e6,1e-10)})
f=np.array([400.,450.,500.,550.,600.,650.,700.,750.,800.]);x=(600/f)**2
A=np.column_stack([np.ones(len(f)),x,-x])
rank=int(np.linalg.matrix_rank(A))
check("LEADING_ORDER_DEGENERACY",rank==2,{"shape":list(A.shape),"rank":rank,"parameters":3,"null_vector":[0,1,1]})
# Restricted equal absolute leading-order coefficients; compare exact corrections.
z=0.01*x
pl=(1-z)**(-0.5)-1
ta=1-(1+z)**(-0.5)
check("RESTRICTED_HIGHER_ORDER",bool(np.all(pl>ta)),{"max_difference_dimensionless":float(np.max(pl-ta)),"not_carrier_unique":True})
def get(url,cap=12_000_000):
    req=urllib.request.Request(url,headers={"User-Agent":"JANUS measurement reproducibility research/1.2","Accept":"*/*"})
    with urllib.request.urlopen(req,timeout=45) as r:
        b=r.read(cap+1)
        if len(b)>cap:raise ValueError("size cap exceeded")
        return b,{"url":url,"final_url":r.geturl(),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest(),"content_type":r.headers.get("Content-Type"),"http_status":r.status}
def run(args,timeout=100):
    try:
        a=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
        return {"exit":a.returncode,"stdout_tail":a.stdout[-2000:],"stderr_tail":a.stderr[-1000:],"status":"EXECUTED_PASS" if a.returncode==0 else "EXECUTED_NONZERO"}
    except Exception as e:return {"status":"BLOCKED","error":str(e)[:400]}
def fail(e):return {"status":"BLOCKED_OR_INCOMPATIBLE","error":str(e)[:400]}
# OPERA: independently published summary, not a blind fit. Confirm cited paper text accessible where possible.
op=p["inputs"]["opera"];upper=op["relative_speed_90CI"][1];rmax=math.sqrt(upper*(2+upper))
opera={"status":"PUBLISHED_SUMMARY_CONDITIONAL_BOUND","source":op["url"],"relative_speed_90CI":op["relative_speed_90CI"],"mu_c2_over_E_upper":rmax,"condition":"If all measured muon neutrinos follow T1 at a fixed E, ratio exceeding this value conflicts with published speed interval. No generic carrier mass bound, no raw likelihood reanalysis."}
try:
    b,proof=get(op["url"],3_000_000);opera["landing_page_receipt"]=proof
except Exception as e:opera["landing_page_receipt"]=fail(e)
check("OPERA_BOUND_INVERSION",math.isclose(math.hypot(1,rmax)-1,upper,rel_tol=1e-10),{"rmax":rmax})
source_receipts=[]
if "sha256" in opera.get("landing_page_receipt",{}):source_receipts.append(("OPERA publication",opera["landing_page_receipt"]))
try:
    b,proof=get(p["inputs"]["chime"]["url"]);source_receipts.append(("CHIME catalog",proof))
    reader=csv.DictReader(io.StringIO(b.decode("utf-8-sig")));rows=list(reader)
    assert set(p["inputs"]["chime"]["fields"])<=set(reader.fieldnames)
    names={r["tns_name"] for r in rows if r["tns_name"]}
    def number(s):
        try:
            q=float(s)
            return q if math.isfinite(q) else None
        except (ValueError,TypeError):return None
    dm=[number(r["dm_fitb"]) for r in rows];valid=[v for v in dm if v is not None]
    ok=len(rows)==600 and len(names)==536 and bool(valid)
    chime={**proof,"status":"CATALOG_CONTROL_PASS" if ok else "CATALOG_SCHEMA_OR_COUNT_HOLD","rows":len(rows),"unique_bursts":len(names),"finite_dm_rows":len(valid),"positive_dm_rows":sum(x>0 for x in valid),"dm_min_median_max":[float(np.min(valid)),float(np.median(valid)),float(np.max(valid))] if valid else None,"carrier_fit":None,"reason":"Published fit DM already derived under ordinary dispersive model; emission time, independent plasma column and carrier detector response unavailable."}
except Exception as e:chime=fail(e)
try:
    gg=p["inputs"]["gwosc"];ss={};gmeta={}
    for d in ("H1","L1"):
        b,proof=get(gg[d]);source_receipts.append(("GWOSC "+d,proof))
        with h5py.File(io.BytesIO(b),"r") as h:
            a=h["strain/Strain"][:];start=float(h["meta/GPSstart"][()]);dur=float(h["meta/Duration"][()])
        fs=len(a)/dur
        assert start==gg["gps_start"] and dur==32 and fs==4096 and np.all(np.isfinite(a))
        ss[d]=np.asarray(a,dtype=float);gmeta[d]={**proof,"samples":len(a),"gps_start":start,"duration_s":dur,"sample_rate":fs}
    fs=4096;start=gg["gps_start"];lo,hi=[int(round((v-start)*fs)) for v in gg["event_window_gps"]]
    sos=signal.butter(4,gg["filter_hz"],btype="bandpass",fs=fs,output="sos")
    white={}
    for d,a in ss.items():
        bg=np.concatenate((a[:12*fs],a[20*fs:]))
        fq,ps=signal.welch(bg,fs=fs,nperseg=fs)
        w=np.interp(np.fft.rfftfreq(len(a),1/fs),fq,ps)
        w=np.maximum(w,np.max(w)*1e-12)
        x=np.fft.irfft(np.fft.rfft(a)/np.sqrt(w),n=len(a))
        white[d]=signal.sosfiltfilt(sos,x)
    maxlag=int(round(gg["lag_scan_ms"]*fs/1000))
    def corr(l,h):
        a=white["H1"];b=white["L1"];v=[]
        for lag in range(-maxlag,maxlag+1):
            # Positive lag = H1 arrives later than L1.
            x=a[l+lag:h+lag];y=b[l:h]
            x=x-x.mean();y=y-y.mean()
            v.append(float(np.dot(x,y)/(np.linalg.norm(x)*np.linalg.norm(y))))
        i=int(np.argmax(np.abs(v)));return {"lag_samples":i-maxlag,"H1_minus_L1_ms":(i-maxlag)*1000/fs,"signed_correlation":v[i],"abs_correlation":abs(v[i])}
    evt=corr(lo,hi);off=[corr(int(v*fs),int(v*fs)+hi-lo) for v in gg["off_windows_relative_s"]]
    med=float(np.median([v["abs_correlation"] for v in off]));ok=4<=evt["H1_minus_L1_ms"]<=10 and evt["abs_correlation"]>med
    gw={"status":"KNOWN_EVENT_TIMING_CONTROL_PASS" if ok else "KNOWN_EVENT_TIMING_CONTROL_HOLD","files":gmeta,"event":evt,"off_windows":off,"off_median_abs_corr":med,"method":"Fixed whitening/bandpass; absolute correlation, not a speed estimate or formal p-value. Known event chosen a priori but not blind.","carrier_identity":None}
except Exception as e:gw=fail(e)
# Native organ calls run in read-only job, without repository write credentials.
topa=pathlib.Path("/tmp/janus-topa");demi=pathlib.Path("/tmp/janus-demi")
def clone(folder,organ):
    spec=p["organs"][organ];url="https://github.com/"+spec["repo"]+".git"
    folder.mkdir(exist_ok=True)
    for args in (["git","init","-q",str(folder)],["git","-C",str(folder),"fetch","--depth=1",url,spec["commit"]],["git","-C",str(folder),"checkout","--detach","FETCH_HEAD"]):
        r=run(args,120)
        if r.get("exit")!=0:return r
    actual=subprocess.check_output(["git","-C",str(folder),"rev-parse","HEAD"],text=True).strip()
    assert actual==spec["commit"]
    return {"status":"PIN_VERIFIED","commit":actual}
tp=clone(topa,"TOPA");dp=clone(demi,"TACHYON")
organs={"TOPA":{"checkout":tp},"TACHYON":{"checkout":dp}}
records=[]
if tp["status"]=="PIN_VERIFIED":
    try:
        sys.path.insert(0,str(topa/"tools"));import topa_archive_gateway as gateway
        for title,proof in source_receipts:
            r=gateway.archive_record("PUBLIC_INSTRUMENT",proof["url"],title,source_meta=proof,extra={"measurement_contract":p["artifact_id"],"record_role":"CONTROL_DATA_PROVENANCE"})
            assert r["scientific_authority"]=="DISCOVERY_AND_ARCHIVAL_PROVENANCE_ONLY" and r["record_sha256"]
            records.append(r)
        organs["TOPA"].update({"status":"NATIVE_SOURCE_RECORDS_EXECUTED" if records else "NO_ACQUIRED_SOURCE","native_records":records,"count":len(records)})
    except Exception as e:organs["TOPA"].update(fail(e))
    organs["RETINA"]={"native_video_smoke":run([sys.executable,str(topa/"tools/topa_retina_video.py"),"--self-test"]),"new_strain_diagnostic":gw["status"],"native_signal_analysis_executed":False,"scope":"Video self-test is not radio/optical signal processing; raw strain analysis is new adapter."}
else:organs["RETINA"]={"status":"BLOCKED_TOPA_CHECKOUT","native_signal_analysis_executed":False}
with tempfile.TemporaryDirectory() as td:
    e=run([sys.executable,"EYE/r4_1/eye_r4_1_minimum_witness_set_solver.py","--input","EYE/r4_7_rt/retro_tahyon_competing_model_benchmark.json","--output-dir",td])
    v=run([sys.executable,"EYE/r4_7_rt/validate_retro_tahyon_competing_model.py","--source","registry/uap/Retro-Tahyon.json","--model","EYE/r4_7_rt/retro_tahyon_competing_model_benchmark.json","--generated-dir",td]) if e.get("exit")==0 else {"status":"BLOCKED_SOLVER"}
    organs["EYE"]={"solver":e,"validator":v,"status":"NATIVE_BENCHMARK_EXECUTED_PASS" if e.get("exit")==0 and v.get("exit")==0 else "NATIVE_BENCHMARK_HOLD","timing_adapter":gw["status"],"scope":"Existing witness model is not fitted to GW data; timing calculation is separate."}
    if dp["status"]=="PIN_VERIFIED":
        a=run([sys.executable,str(demi/"tools/tachyon_r5f_causal_memory_audit.py"),"--audit"],120)
        organs["TACHYON"]["native_causal_audit"]=a
        try:
            sys.path.insert(0,str(demi/"tools"));import source_bound_witness as w
            ev=[{"evidence_id":"OPERA","relation":"context_only","source":op["url"]},{"evidence_id":"CHIME","relation":"context_only","source":p["inputs"]["chime"]["url"]},{"evidence_id":"GWOSC","relation":"context_only","source":gg["H1"] if "gg" in locals() else p["inputs"]["gwosc"]["H1"]}]
            pkt={"schema":w.SCHEMA,"witness_id":"JANUS_CARRIER_CONTROL","case_id":"R1.2","evidence":ev,"questions":[{"question_id":"H4","text":"Do these controls identify a tachyon carrier?","target_claim":"carrier identification","evidence_ids":["OPERA","CHIME","GWOSC"]}]}
            file=pathlib.Path(td)/"packet.json";file.write_text(json.dumps(pkt));ans=w.analyze_packet(w.load_packet(file))
            organs["TACHYON"].update({"native_witness_result":ans,"status":"NATIVE_WITNESS_PACKET_EXECUTED","scope":"Relations assigned by preregistered adapter; this is rule execution, not independent scientific judgment."})
        except Exception as e:organs["TACHYON"].update(fail(e))
result={"schema":"janus.uap_tachyon.measurement_result.v1","status":"KINEMATIC_MODEL_AND_CONTROLS_EXECUTED__CARRIER_IDENTITY_HOLD","source_commit":p["source_commit"],"protocol_sha256":hashlib.sha256(P.read_bytes()).hexdigest(),"authority_changed":False,"synthetic_checks":checks,"published_control":opera,"chime":chime,"gwosc":gw,"organ_receipts":organs,"empirical_tachyon_carrier_specific_observables":0,"empirical_uap_paired_measurements":0,"carrier_model_specific_response":"NOT_DEFINED","physical_claim":False,"independent_blind_exam":"NOT_EXECUTED__INDEPENDENT_PUBLIC_KNOWN_CONTROLS_ONLY","next":"Calibrated carrier interaction model with exclusive detector response, source-independent blind custodian and native RETINA waveform adapter."}
O.write_text(json.dumps(result,ensure_ascii=True,indent=2,allow_nan=False)+"\n");assert json.loads(O.read_text())==result
print(json.dumps({"synthetic_passed":sum(t["pass"] for t in checks),"synthetic_total":len(checks),"opera_ratio_upper":rmax,"chime":chime.get("status"),"chime_rows":chime.get("rows"),"gwosc":gw.get("status"),"lag_ms":gw.get("event",{}).get("H1_minus_L1_ms"),"organs":{k:v.get("status",v.get("native_video_smoke",{}).get("status","UNKNOWN")) for k,v in organs.items()},"carrier":"HOLD"}))
