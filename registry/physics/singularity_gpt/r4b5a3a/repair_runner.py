"""Reporting-only wrapper. Original protocol and numerical source remain immutable."""
import hashlib, io, json, sys, zipfile
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
ORIGINAL=HERE.parent/"r4b5a3"/"audit.py"
REPAIR=json.loads((HERE/"repair_protocol.json").read_text())
TRACE=json.loads((HERE/"trace_verification_precommit.json").read_text())
FAIL=json.loads((ORIGINAL.parent/"technical_failure_archive.json").read_text())
def scalar(obj):
    if isinstance(obj,(np.bool_,np.integer,np.floating)):
        value=obj.item()
        if type(value) in (bool,int,float): return value
    raise TypeError("unsupported JSON scalar: "+type(obj).__name__)
def emit(kind,obj):
    print("R4B5A3A_"+kind,json.dumps(obj,default=scalar,allow_nan=False),flush=True)
def require(ok,msg):
    if not ok:raise RuntimeError(msg)
# Synthetic event schema roundtrip, strict finite JSON, unknown types rejected.
synthetic={"id":"schema","pass":np.bool_(True),"checks":{"fixed_support":np.bool_(False)},"events":{"0.85":{"index":np.int64(12),"tau":np.float64(5.5)}}}
decoded=json.loads(json.dumps(synthetic,default=scalar,allow_nan=False))
require(set(decoded)=={"id","pass","checks","events"} and type(decoded["pass"]) is bool and type(decoded["checks"]["fixed_support"]) is bool and type(decoded["events"]["0.85"]["index"]) is int and type(decoded["events"]["0.85"]["tau"]) is float and decoded=={"id":"schema","pass":True,"checks":{"fixed_support":False},"events":{"0.85":{"index":12,"tau":5.5}}},"SYNTHETIC_SCHEMA")
for invalid in (np.float64(np.nan),np.float32(np.inf),object(),np.array([1])):
    try:json.dumps({"invalid":invalid},default=scalar,allow_nan=False)
    except (ValueError,TypeError):pass
    else:raise RuntimeError("STRICT_JSON_REJECTION")
prior=json.loads((HERE.parent/"r4b5a2"/"result_archive.json").read_text())
require(len(prior["logged_evidence"])==12 and prior["logged_evidence"][-1]["data"]["status"]=="CURVATURE_RECOVERY_HOLD","PRIOR_ARCHIVE")
# Strictly re-encode all existing parsed records.
json.dumps(prior,allow_nan=False)
archive_path=Path(sys.argv[1])
raw=archive_path.read_bytes()
require(hashlib.sha256(raw).hexdigest()==TRACE["zip_sha256"],"HISTORICAL_ZIP_DIGEST")
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    def member(name):
        names=[x for x in z.namelist() if Path(x).name==name]
        require(len(names)==1,"ARTIFACT_MEMBER_"+name)
        return z.read(names[0])
    old_case=json.loads(member("cases.json"))["coarse"]
    with np.load(io.BytesIO(member("traces.npz")),allow_pickle=False) as data:
        require(data.files==["coarse"],"HISTORICAL_TRACE_KEYS")
        old_trace=data["coarse"].copy()
def independent_safety(row,x):
    e0=float(x[0,7]);h=row["h"]
    metrics={"finite":bool(np.isfinite(x).all()),"time_increasing":bool(np.all(np.diff(x[:,0])>0) and np.all(np.diff(x[:,1])>0)),"steps":int(len(x)-1),"peak_C":float(np.max(x[:,6])),"Ricci":float(np.max(x[:,4])),"Ricci_alt":float(np.max(x[:,5])),"mass_drift":float(np.max(np.abs(x[:,7]-e0))/e0),"outer_residual":float(np.max(x[:,15])),"interior_residual":float(np.max(x[:,18])),"final_tau":float(x[-1,1])}
    metrics["scale"]=float(1/np.sqrt(metrics["Ricci"])/h)
    metrics["scale_alt"]=float(1/np.sqrt(metrics["Ricci_alt"])/h)
    mapping={"steps":"steps","peak_C":"peak_compactness","Ricci":"curvature_peak","Ricci_alt":"curvature_peak_alt","mass_drift":"mass_drift","outer_residual":"direct_balance_residual_max","interior_residual":"reference_interior_balance_residual_max","final_tau":"proper_time","scale":"scale","scale_alt":"scale_alt"}
    matches={k:bool(abs(metrics[k]-row[v])<=1e-12*max(abs(row[v]),1e-30)) for k,v in mapping.items()}
    ok=metrics["finite"] and metrics["time_increasing"] and all(matches.values()) and metrics["peak_C"]>=.90 and min(metrics["scale"],metrics["scale_alt"])>=8 and max(metrics["mass_drift"],metrics["outer_residual"],metrics["interior_residual"])<.01
    return {"pass":bool(ok),"metrics":metrics,"matches":matches}
logged={k:v for k,v in FAIL["case"].items() if k not in ("id","elapsed_seconds")}
def values(row):return {k:v for k,v in row.items() if k!="elapsed_seconds"}
require(values(old_case)==logged,"ARCHIVED_CASE_LOG_MISMATCH")
old_safety=independent_safety(old_case,old_trace)
require(old_safety["pass"],"HISTORICAL_TRACE_SAFETY")
emit("PREFLIGHT",{"schema":True,"strict_json":True,"prior_archive":True,"zip_sha256":TRACE["zip_sha256"],"historical_trace_shape":list(old_trace.shape),"historical_safety":old_safety})
def replay_hook(key,row,x):
    if key!="coarse":return
    same=values(row)==values(old_case)
    array_same=x.dtype==old_trace.dtype and x.shape==old_trace.shape and x.tobytes(order="C")==old_trace.tobytes(order="C")
    safety=independent_safety(row,x)
    report={"case_exact_excluding_elapsed":same,"array_bytes_exact":array_same,"historical_trace_sha256":hashlib.sha256(old_trace.tobytes(order="C")).hexdigest(),"replayed_trace_sha256":hashlib.sha256(x.tobytes(order="C")).hexdigest(),"safety":safety,"pass":bool(same and array_same and safety["pass"])}
    emit("EXACT_REPLAY",report)
    require(report["pass"],"TECHNICAL_REPLAY_HOLD")
source=ORIGINAL.read_text()
patched=source
changes=[
    ('json.dumps(obj,indent=2,allow_nan=False)','json.dumps(obj,indent=2,allow_nan=False,default=serialization_scalar)'),
    ('json.dumps(obj,allow_nan=False)','json.dumps(obj,allow_nan=False,default=serialization_scalar)'),
    ('    execute(key,cfg(n,cfl),True)\n    checks[key]=check_run(key)','    execute(key,cfg(n,cfl),True)\n    replay_hook(key,rows[key],traces[key])\n    checks[key]=check_run(key)')]
for before,after in changes:
    require(patched.count(before)==1,"PATCH_TARGET")
    patched=patched.replace(before,after)
reversed_source=patched
for before,after in reversed(changes):reversed_source=reversed_source.replace(after,before)
require(reversed_source==source,"SOURCE_REVERSIBILITY")
require(patched[patched.index("def run("):patched.index("rows={};traces={}")] == source[source.index("def run("):source.index("rows={};traces={}")] ,"NUMERICAL_SOURCE_CHANGED")
emit("SOURCE",{"numerical_run_unchanged":True,"reversible_reporting_patch":True,"original_protocol_sha256":hashlib.sha256((ORIGINAL.parent/"protocol.json").read_bytes()).hexdigest()})
exec(compile(patched,str(ORIGINAL),"exec"),{"__name__":"__main__","__file__":str(ORIGINAL),"serialization_scalar":scalar,"replay_hook":replay_hook})
