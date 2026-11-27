"""Cold JIT reproduction, source/environment diff, and exact diagnostic ULP audit."""
import hashlib,io,json,os,subprocess,sys,tempfile,zipfile,re
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
P=json.loads((HERE/"protocol.json").read_text())
OUT=Path("r4b5a4b-output").resolve();OUT.mkdir(exist_ok=True)
def emit(k,v):print("R4B5A4B_"+k,json.dumps(v,allow_nan=False),flush=True)
def write(k,v):(OUT/k).write_text(json.dumps(v,indent=2,allow_nan=False)+"\n")
def require(x,msg):
    if not x:raise RuntimeError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
# Reuse the exact previously verified instrumentation and comparison definitions.
parent_path=HERE.parent/"r4b5a4a"/"audit.py"
src=parent_path.read_text()
prefix=src[:src.index('if len(sys.argv)>1 and sys.argv[1]=="trial":')]
ns={"__file__":str(parent_path),"__name__":"cold_parent"}
exec(compile(prefix,str(parent_path),"exec"),ns)
ns["OUT"]=OUT
def getzip(path,expected):
    raw=Path(path).read_bytes();require(sha(raw)==expected,"ZIP_DIGEST")
    return zipfile.ZipFile(io.BytesIO(raw))
def member(z,name):
    names=[n for n in z.namelist() if Path(n).name==name]
    require(len(names)==1,"ZIP_MEMBER_"+name);return z.read(names[0])
def array(z,name,key):
    with np.load(io.BytesIO(member(z,name)),allow_pickle=False) as a:return a[key].copy()
def stable(f):
    g=ns["stable_fingerprint"](f)
    g.pop("numba_cache_dir",None)
    g["compiler_env"]=dict(g["compiler_env"]);g["compiler_env"].pop("NUMBA_CACHE_DIR",None)
    return g
def digest(f):return sha(json.dumps(stable(f),sort_keys=True,separators=(",",":"),allow_nan=False).encode())
def finish(status,**extra):
    result={"status":status,"scientific_hold":True,"medium_fine_run":False,"n98304_run":False,"dss_tested":False,"amr_implemented":False,"NEAR_GATE":"NOT_EVALUATED_TECHNICAL_ONLY","historical_failure_preserved":True,**extra}
    write("result.json",result);emit("RESULT",result);sys.exit(0)
if len(sys.argv)>1 and sys.argv[1]=="trial":
    key,mode=sys.argv[2:4]
    cache=Path(os.environ["NUMBA_CACHE_DIR"]).resolve()
    require(cache.is_dir() and not list(cache.iterdir()),"COLD_CACHE_NOT_EMPTY")
    ns["trial"](key,mode=="capture")
    files=[str(x.relative_to(cache)) for x in cache.rglob("*") if x.is_file()]
    f=json.loads((OUT/(key+"-environment.json")).read_text())
    ok=Path(f["numba_cache_dir"]).resolve()==cache and any(x.endswith(".nbc") for x in files) and any(x.endswith(".nbi") for x in files)
    receipt={"id":key,"cache":str(cache),"initial_empty":True,"inventory":files,"environment_sha256":digest(f),"pass":bool(ok)}
    write(key+"-cold-cache.json",receipt);emit("COLD_CACHE",receipt)
    require(ok,"CACHE_COMPILATION_WITNESS");sys.exit(0)
old=P["parent"]
with getzip(sys.argv[1],old["historical"]["zip_sha256"]) as z:
    historical=array(z,"traces.npz","coarse")
with getzip(sys.argv[2],old["failed"]["zip_sha256"]) as z:
    failed=array(z,"coarse-radial.npz","trace")
    old_env=member(z,"environment.txt").decode()
with getzip(sys.argv[3],old["paired"]["zip_sha256"]) as z:
    paired={k:json.loads(member(z,k+"-environment.json")) for k in ("baseline_a","baseline_b","instrumented_c")}
require(sha(historical.tobytes(order="C"))==old["historical"]["array_sha256"] and sha(failed.tobytes(order="C"))==old["failed"]["array_sha256"],"ARRAY_DIGEST")
(OUT/"historical-environment.txt").write_text(old_env);write("paired-environment.json",paired)
# Compare actual historical evidence; unavailable fields remain unknown.
def match(pattern):
    m=re.search(pattern,old_env,re.M);return m.group(1).strip() if m else None
old_cpu=match(r"^Model name:\s*(.+)$")
old_flags=match(r"^Flags:\s*(.+)$")
old_threads={}
for key in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS","NUMBA_NUM_THREADS","BLIS_NUM_THREADS"):
    m=re.search(r"['\"]"+key+r"['\"]:\s*(None|'[^']*'|\"[^\"]*\")",old_env)
    old_threads[key]=m.group(1).strip("'\"") if m else "UNKNOWN"
new=paired["baseline_a"]
envdiff={"failed":{"cpu_model":old_cpu,"cpu_flags":old_flags,"threads":old_threads,"python":match(r"^(Python .+)$"),"numpy":match(r"^numpy==(.+)$"),"numba":match(r"^numba==(.+)$"),"llvmlite":match(r"^llvmlite==(.+)$"),"blas_runtime_raw":old_env[old_env.find("blas"):][:8000] if "blas" in old_env else None,"blas_library_hashes":"UNKNOWN","cache_dir":"UNKNOWN"},"paired":{"cpu":new["cpu"],"thread_env":new["thread_env"],"python":new["python"],"numpy":new["numpy"],"numba":new["numba"],"llvmlite":new["llvmlite"],"blas_library_hashes":new["blas_library_hashes"],"numpy_config_runtime":new["numpy_config_runtime"],"numba_cache_dir":new["numba_cache_dir"]},"cause":"UNRESOLVED; environment differences not controlled causal experiment"}
write("environment_diff.json",envdiff);emit("ENV_DIFF",{**envdiff,"failed":{**envdiff["failed"],"blas_runtime_raw":"see environment_diff.json"}})
source=(HERE.parent/"r4b5a3"/"audit.py").read_text()
loc=(HERE.parent/"r4b5a4"/"audit.py").read_text()
body=source[source.index("def run("):source.index("rows={};traces={}")]
capture=loc[loc.index("def local_peaks("):loc.index("def load_original(")]
line='        data.append([t,T,v2,v3,R2,R3,c,E,inner,pp,qq,ss,*integ.tolist(),*maxres.tolist(),refinteg,maxrefres])'
insertion=line+"\n        capture(t,T,r,p,q,a,al,m)"
require(body.count(line)==1 and body.replace(line,insertion).replace(insertion,line)==body,"REVERSIBILITY")
# Both harnesses extract the same original source and same capture implementation.
require('after=before+"\\n        capture(t,T,r,p,q,a,al,m)"' in src and 'after=before+"\\n        capture(t,T,r,p,q,a,al,m)"' in loc,"SOURCE_CAPTURE_INSERTION")
require('cap_source=cap_source[cap_source.index("def local_peaks("):cap_source.index("def load_original(")]' in src,"CAPTURE_SOURCE")
diff={"numerical_run_sha256":sha(body.encode()),"instrumented_run_sha256":sha(body.replace(line,insertion).encode()),"capture_definition_sha256":sha(capture.encode()),"collect_sha256":sha(body[body.index("    def collect():"):body.index("    collect();")].encode()),"reference_sha256":sha(body[body.index("        def reference():"):body.index("    boundary_r=")].encode()),"same_insertion":True,"same_capture_source":True,"harness_changes":["single process with synthetic before replay versus independent trial processes","fixed one-thread environment versus historical defaults","shared JIT cache policy in R4B5A.4a versus cold isolated here"],"claim":"Source identity supports no change of numerical expressions; actual earlier root cause not established."}
emit("SOURCE_DIFF",diff);write("source_diff.json",diff)
def mismatch(a,b):
    require(a.shape==b.shape and a.dtype==b.dtype==np.float64,"TRACE_SCHEMA")
    require(np.isfinite(a).all() and np.isfinite(b).all(),"TRACE_FINITE")
    tiny=np.finfo(np.float64).tiny
    result={}
    for j,name in enumerate(ns["COLS"]):
        x,y=np.ascontiguousarray(a[:,j]),np.ascontiguousarray(b[:,j])
        u,v=x.view(np.uint64),y.view(np.uint64)
        ix=np.flatnonzero(u!=v)
        if not len(ix):continue
        def ord_bits(w):return np.where((w>>np.uint64(63))!=0,~w,w^np.uint64(1<<63))
        uo,vo=ord_bits(u),ord_bits(v)
        ulp=np.maximum(uo,vo)-np.minimum(uo,vo)
        delta=np.abs(x-y);den=np.maximum(np.abs(x),np.abs(y))
        rel=np.divide(delta,den,out=np.zeros_like(delta),where=den>0)
        def pair(i):
            i=int(i)
            return {"row":i,"historical":float(x[i]),"failed":float(y[i]),"abs_error":float(delta[i]),"relative_error":float(rel[i]),"ulp":int(ulp[i]),"subnormal_a":bool(0<abs(x[i])<tiny),"subnormal_b":bool(0<abs(y[i])<tiny)}
        result[name]={"count":int(len(ix)),"first":pair(ix[0]),"max_absolute":pair(ix[np.argmax(delta[ix])]),"max_relative":pair(ix[np.argmax(rel[ix])]),"max_ulp":pair(ix[np.argmax(ulp[ix])]),"zero_transitions":int(np.sum((x[ix]==0)!=(y[ix]==0))),"subnormal_pairs":int(np.sum(((np.abs(x[ix])<tiny)&(x[ix]!=0))|((np.abs(y[ix])<tiny)&(y[ix]!=0))))}
    return {"columns":result,"float64_smallest_normal":float(tiny),"float64_epsilon":float(np.finfo(np.float64).eps),"strict_gate_unchanged":True}
mr=mismatch(historical,failed);write("historical_mismatch_ulp.json",mr);emit("MISMATCH_ULP",mr)
# Old synthetic checks plus new structurally different manufactured radial constraint.
if not ns["synthetic"]():finish("SYNTHETIC_CUBIC_HOLD")
solver,_=ns["original"]()
cases=[]
M=.9*3*np.sqrt(3)/4
for n in (256,512,1024):
    h=4/n;r=(np.arange(n)+.5)*h
    m=M*r**3/(r*r+1)**1.5;c=2*m/r
    p=np.sqrt(3*M/(2*np.pi*(r*r+1)**2.5*(1-c)));q=np.zeros_like(p)
    a,al,mn,edge=solver["geometry"](p,q,r,h,False);cn=2*mn/r;i=int(np.argmax(cn))
    cases.append({"n":n,"finite":bool(np.isfinite(edge) and np.isfinite(a).all() and np.isfinite(al).all()),"C_Linf":float(np.max(np.abs(cn-c))),"m_Linf":float(np.max(np.abs(mn-m))),"max_C":float(cn[i]),"argmax_r":float(r[i]),"argmax_error":float(abs(r[i]-np.sqrt(2))),"peak_error":float(abs(cn[i]-.9))})
errs=[x["C_Linf"] for x in cases];orders=[float(np.log2(a/b)) for a,b in zip(errs,errs[1:])]
ok=all(x["finite"] and x["max_C"]<.999 for x in cases) and errs[-1]<=.0005 and all(1.5<=p<=2.5 for p in orders)
report={"cases":cases,"orders":orders,"pass":bool(ok)}
emit("INTERIOR_MAX_SYNTHETIC",report);write("interior_max_synthetic.json",report)
if not ok:finish("SYNTHETIC_INTERIOR_MAX_HOLD")
def trial(key,capture=False):
    cache=Path(tempfile.mkdtemp(prefix=key+"-",dir=OUT))
    env=dict(os.environ);env["NUMBA_CACHE_DIR"]=str(cache)
    subprocess.run([sys.executable,str(Path(__file__).resolve()),"trial",key,"capture" if capture else "baseline"],env=env,check=True)
    return np.load(OUT/(key+"-trace.npy"),allow_pickle=False),json.loads((OUT/(key+"-case.json")).read_text()),json.loads((OUT/(key+"-cold-cache.json")).read_text())
def cv(r):return {k:v for k,v in r.items() if k!="elapsed_seconds"}
def cmp(a,b):return ns["compare"](a,b)
a,ar,ae=trial("baseline_a");b,br,be=trial("baseline_b")
ab=cmp(a,b);ah=cmp(a,historical);bh=cmp(b,historical)
gate=ae["pass"] and be["pass"] and ae["cache"]!=be["cache"] and ae["environment_sha256"]==be["environment_sha256"] and cv(ar)==cv(br) and ab["exact"] and ah["exact"] and bh["exact"]
emit("BASELINE_GATE",{"pass":bool(gate),"A_B":ab["exact"],"A_H":ah["exact"],"B_H":bh["exact"],"case_exact":cv(ar)==cv(br),"environment_exact":ae["environment_sha256"]==be["environment_sha256"],"cache_distinct":ae["cache"]!=be["cache"]})
if not gate:finish("COLD_BASELINE_REPLAY_HOLD",comparisons={"A_B":ab,"A_H":ah,"B_H":bh})
c,cr,ce=trial("instrumented_c",True)
ac,bc,ch=cmp(a,c),cmp(b,c),cmp(c,historical)
gate=ce["pass"] and len({ae["cache"],be["cache"],ce["cache"]})==3 and ae["environment_sha256"]==be["environment_sha256"]==ce["environment_sha256"] and cv(ar)==cv(br)==cv(cr) and all(x["exact"] for x in (ac,bc,ch))
report={"pass":bool(gate),"A_C":ac["exact"],"B_C":bc["exact"],"C_H":ch["exact"],"environment_exact":ae["environment_sha256"]==ce["environment_sha256"],"cache_distinct":len({ae["cache"],be["cache"],ce["cache"]})==3,"case_exact":cv(ar)==cv(br)==cv(cr)}
emit("COLD_NEUTRALITY_GATE",report)
finish("COLD_JIT_VERIFICATION_PASS__SCIENTIFIC_HOLD" if gate else "COLD_CAPTURE_REPLAY_HOLD",gate=report,comparisons={"A_B":ab,"A_H":ah,"B_H":bh,"A_C":ac,"B_C":bc,"C_H":ch},historical_root_cause="UNRESOLVED")
