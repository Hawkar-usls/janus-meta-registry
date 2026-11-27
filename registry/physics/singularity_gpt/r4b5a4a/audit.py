"""Same-VM, fresh-process repeatability control; no scientific admission."""
import hashlib,io,json,os,platform,subprocess,sys,sysconfig,zipfile,contextlib
from pathlib import Path
import numpy as np
import numba,llvmlite
HERE=Path(__file__).resolve().parent
P=json.loads((HERE/"protocol.json").read_text())
E=json.loads((HERE/"execution_precommit.json").read_text())
OUT=Path("r4b5a4a-output").resolve();OUT.mkdir(exist_ok=True)
COLS=["t","tau","central_derivative_2","central_derivative_3","Ricci_2","Ricci_3","C_max","mass","inner_mass_fraction","probe_p","probe_q","probe_scalar","face_flux_integral","old_flux_integral","analytic_flux_integral","face_residual","old_residual","reference_flux_integral","reference_residual"]
def write(name,obj):(OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
def emit(tag,obj):print("R4B5A4A_"+tag,json.dumps(obj,allow_nan=False),flush=True)
def require(ok,msg):
    if not ok:raise RuntimeError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def fingerprint():
    info=io.StringIO()
    with contextlib.redirect_stdout(info):np.show_config();np.show_runtime()
    cpu=Path("/proc/cpuinfo").read_text().split("\n\n")[0]
    cpu={k.strip():v.strip() for line in cpu.splitlines() if ":" in line for k,v in [line.split(":",1)] if k.strip() in ("vendor_id","model name","cpu family","model","stepping","flags")}
    libs={}
    for line in Path("/proc/self/maps").read_text().splitlines():
        p=line.split()[-1]
        if p.startswith("/") and ("blas" in p.lower() or "lapack" in p.lower()):
            path=Path(p)
            if path.is_file():libs[str(path)]=sha(path.read_bytes())
    return {"image_os":os.getenv("ImageOS"),"image_version":os.getenv("ImageVersion"),"kernel":platform.release(),"machine":platform.machine(),"cpu":cpu,"python":sys.version,"python_build_flags":sysconfig.get_config_var("CONFIG_ARGS"),"cflags":sysconfig.get_config_var("CFLAGS"),"numpy":np.__version__,"numba":numba.__version__,"llvmlite":llvmlite.__version__,"numpy_config_runtime":info.getvalue(),"blas_library_hashes":libs,"thread_env":{k:os.getenv(k) for k in E["environment"]["threads"]},"numba_threads":numba.config.NUMBA_NUM_THREADS,"numba_cpu_name":numba.config.CPU_NAME,"numba_cpu_features":numba.config.CPU_FEATURES,"numba_opt":str(numba.config.OPT),"numba_disable_jit":numba.config.DISABLE_JIT,"numba_cache_dir":numba.config.CACHE_DIR,"compiler_env":{k:os.getenv(k) for k in ("CC","CXX","CFLAGS","CPPFLAGS","LDFLAGS","NUMBA_CPU_NAME","NUMBA_CPU_FEATURES","NUMBA_OPT","NUMBA_DISABLE_JIT","NUMBA_CACHE_DIR")},"container_digest":None}
def stable_fingerprint(f):
    # show_runtime may include process-specific threadpool memory addresses;
    # keep full report but normalize only such address lines for comparison.
    import re
    g=dict(f);g["numpy_config_runtime"]=re.sub(r"0x[0-9a-fA-F]+","<address>",g["numpy_config_runtime"])
    return g
def original(capture=False):
    path=HERE.parent/"r4b5a3"/"audit.py"
    s=path.read_text();s=s[:s.index("rows={};traces={}")]
    ns={"__file__":str(path),"__name__":"r4b5a4a_trial"}
    if capture:
        cap_source=(HERE.parent/"r4b5a4"/"audit.py").read_text()
        cap_source=cap_source[cap_source.index("def local_peaks("):cap_source.index("def load_original(")]
        cap_ns={"np":np,"P":json.loads((HERE.parent/"r4b5a4"/"protocol.json").read_text())}
        exec(compile(cap_source,"capture-only","exec"),cap_ns)
        cap=cap_ns["Capture"]("coarse")
        before='        data.append([t,T,v2,v3,R2,R3,c,E,inner,pp,qq,ss,*integ.tolist(),*maxres.tolist(),refinteg,maxrefres])'
        after=before+"\n        capture(t,T,r,p,q,a,al,m)"
        require(s.count(before)==1,"CAPTURE_TARGET")
        patched=s.replace(before,after);require(patched.replace(after,before)==s,"CAPTURE_REVERSIBLE")
        ns["capture"]=cap;s=patched
    else:cap=None
    exec(compile(s,str(path),"exec"),ns)
    return ns,cap
def trial(key,capture):
    f=fingerprint();write(key+"-environment.json",f)
    require(f["thread_env"]==E["environment"]["threads"],"THREAD_ENV")
    require((f["numpy"],f["numba"],f["llvmlite"])==("2.2.6","0.61.2","0.44.0") and sys.version_info[:3]==(3,11,18),"PACKAGE_VERSIONS")
    ns,cap=original(capture)
    cfg={k:v for k,v in P["configuration"].items() if k!="stop"}
    row,x=ns["run"](cfg,True)
    write(key+"-case.json",row);np.save(OUT/(key+"-trace.npy"),x,allow_pickle=False)
    if cap is not None:
        np.savez_compressed(OUT/(key+"-capture.npz"),argmax_history=np.asarray(cap.history),**{"tau_"+str(t):v for t,v in cap.snap.items()})
        emit("CAPTURE_SUPPORT",{"present":list(cap.snap),"NOT_REACHED":[t for t in cap.targets if t not in cap.snap]})
    emit("TRIAL",{"id":key,"trace_sha256":sha(x.tobytes(order="C")),"shape":list(x.shape),"case":row})
def synthetic():
    ns,_=original();results={}
    for name,k in (("weak",.002),("strong",.9/(2*4**2))):
        cases=[]
        for n in (256,512,1024):
            h=4/n;r=(np.arange(n)+.5)*h;c=2*k*r*r;m=k*r**3
            p=np.sqrt(3*k/(2*np.pi*(1-c)));q=np.zeros_like(p)
            a,al,mn,M=ns["geometry"](p,q,r,h,False);cn=2*mn/r
            ae=1/np.sqrt(1-c);ale=(1-2*k*4**2)**1.5/(1-c)
            cases.append({"n":n,"finite":bool(np.isfinite(M) and np.isfinite(a).all() and np.isfinite(al).all()),"max_C":float(np.max(cn)),"C_Linf":float(np.max(np.abs(cn-c))),"m_Linf":float(np.max(np.abs(mn-m))),"a_Linf":float(np.max(np.abs(a-ae))),"alpha_Linf":float(np.max(np.abs(al-ale)))})
        errors=[v["C_Linf"] for v in cases]
        orders=[float(np.log2(a/b)) for a,b in zip(errors,errors[1:])]
        ok=all(v["finite"] and v["max_C"]<.999 for v in cases) and errors[-1]<=.0005 and all(1.5<=p<=2.5 for p in orders)
        results[name]={"cases":cases,"C_orders":orders,"pass":bool(ok)}
    emit("SYNTHETIC",results);write("synthetic.json",results)
    return all(v["pass"] for v in results.values())
def extract(path,digest,member,key=None):
    raw=Path(path).read_bytes();require(sha(raw)==digest,"ZIP_DIGEST")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=[n for n in z.namelist() if Path(n).name==member];require(len(names)==1,"ZIP_MEMBER")
        with np.load(io.BytesIO(z.read(names[0])),allow_pickle=False) as arr:return arr[key].copy()
def compare(a,b):
    report={"shape_a":list(a.shape),"shape_b":list(b.shape),"dtype_a":str(a.dtype),"dtype_b":str(b.dtype),"sha_a":sha(a.tobytes(order="C")),"sha_b":sha(b.tobytes(order="C"))}
    if a.shape!=b.shape or a.dtype!=b.dtype or a.ndim!=2 or a.shape[1]!=19:
        return {**report,"exact":False,"columns":None}
    require(a.dtype==np.float64 and np.isfinite(a).all() and np.isfinite(b).all(),"TRACE_SCHEMA")
    a=np.ascontiguousarray(a);b=np.ascontiguousarray(b)
    bits=a.view(np.uint64)!=b.view(np.uint64);nums=a!=b
    columns={}
    for i,name in enumerate(COLS):
        ids=np.flatnonzero(bits[:,i]);first=int(ids[0]) if len(ids) else None
        columns[name]={"bit_mismatch":int(np.sum(bits[:,i])),"numeric_mismatch":int(np.sum(nums[:,i])),"bit_only":int(np.sum(bits[:,i]&~nums[:,i])),"signed_zero":int(np.sum(bits[:,i]&(a[:,i]==0)&(b[:,i]==0))),"max_abs":float(np.max(np.abs(a[:,i]-b[:,i]))),"first":None if first is None else {"row":first,"a":float(a[first,i]),"b":float(b[first,i]),"a_hex":hex(int(a.view(np.uint64)[first,i])),"b_hex":hex(int(b.view(np.uint64)[first,i]))}}
    return {**report,"exact":bool(not bits.any()),"columns":columns}
def finish(status,**extra):
    result={"status":status,"scientific_hold":True,"historical_gate_preserved":True,"medium_fine_run":False,"n98304_run":False,"dss_tested":False,"amr_implemented":False,"NEAR_GATE":"NOT_EVALUATED_TECHNICAL_ONLY",**extra}
    write("result.json",result);emit("RESULT",result);sys.exit(0)
if len(sys.argv)>1 and sys.argv[1]=="trial":
    trial(sys.argv[2],sys.argv[3]=="capture");sys.exit(0)
historical=extract(sys.argv[1],P["parent"]["historical_zip_sha256"],"traces.npz","coarse")
failed=extract(sys.argv[2],P["parent"]["failed_zip_sha256"],"coarse-radial.npz","trace")
comparisons={"historical_vs_failed":compare(historical,failed)}
emit("COMPARE",{"pair":"historical_vs_failed",**comparisons["historical_vs_failed"]})
write("comparisons.json",comparisons)
if not synthetic():finish("SYNTHETIC_STRONG_FIELD_HOLD")
def run_trial(key,capture=False):
    subprocess.run([sys.executable,str(Path(__file__).resolve()),"trial",key,"capture" if capture else "baseline"],check=True)
    return np.load(OUT/(key+"-trace.npy"),allow_pickle=False),json.loads((OUT/(key+"-case.json")).read_text()),json.loads((OUT/(key+"-environment.json")).read_text())
def case_values(row):return {k:v for k,v in row.items() if k!="elapsed_seconds"}
def record(name,a,b):
    comparisons[name]=compare(a,b);emit("COMPARE",{"pair":name,**comparisons[name]});write("comparisons.json",comparisons)
    return comparisons[name]["exact"]
a,ar,ae=run_trial("baseline_a");b,br,be=run_trial("baseline_b")
same_env=stable_fingerprint(ae)==stable_fingerprint(be);same_case=case_values(ar)==case_values(br)
same_trace=record("baseline_a_vs_b",a,b)
record("historical_vs_baseline_a",historical,a);record("failed_vs_baseline_a",failed,a)
emit("BASELINE_GATE",{"environment_equal":same_env,"case_exact":same_case,"trace_exact":same_trace,"pass":bool(same_env and same_case and same_trace)})
if not all((same_env,same_case,same_trace)):finish("TECHNICAL_OR_INTEGRITY_HOLD__BASELINE_REPEATABILITY",comparisons=comparisons)
c,cr,ce=run_trial("instrumented_c",True)
env=stable_fingerprint(ae)==stable_fingerprint(ce)
cases=case_values(ar)==case_values(cr)==case_values(br)
ac=record("baseline_a_vs_instrumented_c",a,c);bc=record("baseline_b_vs_instrumented_c",b,c)
hc=record("historical_vs_instrumented_c",historical,c);fc=record("failed_vs_instrumented_c",failed,c)
gate=bool(env and cases and ac and bc)
emit("INSTRUMENTATION_GATE",{"environment_equal":env,"case_exact":cases,"baseline_a_exact":ac,"baseline_b_exact":bc,"historical_exact":hc,"failed_exact":fc,"pass":gate})
finish("INSTRUMENTATION_NEUTRALITY_PASS__SCIENTIFIC_HOLD" if gate else "TECHNICAL_OR_INTEGRITY_HOLD__CAPTURE_NEUTRALITY_UNRESOLVED",paired_neutrality=gate,historical_exact=hc,comparisons=comparisons)
