"""Controlled Numba/BLAS factorial, no change to numerical solver."""
import hashlib,io,json,os,subprocess,sys,tempfile,zipfile
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_info
HERE=Path(__file__).resolve().parent
P=json.loads((HERE/"protocol.json").read_text())
OUT=Path("r4b5a4c-output").resolve();OUT.mkdir(exist_ok=True)
def emit(k,v):print("R4B5A4C_"+k,json.dumps(v,allow_nan=False),flush=True)
def write(k,v):(OUT/k).write_text(json.dumps(v,indent=2,allow_nan=False)+"\n")
def require(x,m):
    if not x:raise RuntimeError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(obj):return sha(json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
parent=HERE.parent/"r4b5a4a"/"audit.py"
src=parent.read_text();src=src[:src.index('if len(sys.argv)>1 and sys.argv[1]=="trial":')]
ns={"__file__":str(parent),"__name__":"thread_parent"}
exec(compile(src,str(parent),"exec"),ns);ns["OUT"]=OUT
def stable(f):
    g=ns["stable_fingerprint"](f)
    g.pop("numba_cache_dir",None)
    g["compiler_env"]=dict(g["compiler_env"]);g["compiler_env"].pop("NUMBA_CACHE_DIR",None)
    return g
def finish(status,**extra):
    report={"status":status,"scientific_hold":True,"NEAR_GATE":"NOT_EVALUATED_TECHNICAL_ONLY","medium_fine_run":False,"n98304_run":False,"dss_tested":False,"amr_implemented":False,**extra}
    write("result.json",report);emit("RESULT",report);sys.exit(0)
if len(sys.argv)>1 and sys.argv[1]=="trial":
    key,N,B=sys.argv[2],int(sys.argv[3]),int(sys.argv[4])
    cache=Path(os.environ["NUMBA_CACHE_DIR"]).resolve()
    require(cache.is_dir() and not list(cache.iterdir()),"CACHE_NOT_EMPTY")
    threads={k:str(N if k=="NUMBA_NUM_THREADS" else B) for k in ns["E"]["environment"]["threads"]}
    ns["E"]["environment"]["threads"]=threads
    pools=threadpool_info();blas=[x for x in pools if x.get("user_api")=="blas"]
    require(bool(blas) and all(x["num_threads"]==B for x in blas),"ACTUAL_BLAS_THREADS")
    require(ns["numba"].config.NUMBA_NUM_THREADS==N,"NUMBA_THREADS")
    ns["trial"](key,True)
    f=json.loads((OUT/(key+"-environment.json")).read_text())
    files=[str(x.relative_to(cache)) for x in cache.rglob("*") if x.is_file()]
    require(Path(f["numba_cache_dir"]).resolve()==cache and any(x.endswith(".nbc") for x in files) and any(x.endswith(".nbi") for x in files),"CACHE_WITNESS")
    fixed=stable(f)
    platform={k:fixed[k] for k in ("image_os","image_version","kernel","machine","cpu","python","python_build_flags","cflags","numpy","numba","llvmlite","blas_library_hashes","numba_cpu_name","numba_cpu_features","numba_opt","numba_disable_jit","compiler_env")}
    record={"id":key,"N":N,"B":B,"cache":str(cache),"cache_initial_empty":True,"cache_files":files,"threadpool_info":pools,"fingerprint_sha256":canonical(fixed),"platform_sha256":canonical(platform),"cpu":f["cpu"]["model name"],"pass":True}
    write(key+"-receipt.json",record);emit("RECEIPT",record);sys.exit(0)
def getzip(path,digest):
    raw=Path(path).read_bytes();require(sha(raw)==digest,"ZIP_HASH");return zipfile.ZipFile(io.BytesIO(raw))
def arr(z,name,key):
    names=[n for n in z.namelist() if Path(n).name==name];require(len(names)==1,"ZIP_MEMBER")
    with np.load(io.BytesIO(z.read(names[0])),allow_pickle=False) as a:return a[key].copy()
parent=P["parent"]
with getzip(sys.argv[1],parent["historical_zip_sha256"]) as z:h=arr(z,"traces.npz","coarse")
with getzip(sys.argv[2],parent["failed_zip_sha256"]) as z:f=arr(z,"coarse-radial.npz","trace")
with getzip(sys.argv[3],parent["zip_sha256"]) as z:require(any(Path(n).name=="result.json" for n in z.namelist()),"PARENT_RESULT")
require(sha(h.tobytes(order="C"))==parent["historical_array_sha256"] and sha(f.tobytes(order="C"))==parent["failed_array_sha256"],"PARENT_ARRAY_HASH")
diagnostics={}
for j,name in enumerate(ns["COLS"]):
    a,b=np.ascontiguousarray(h[:,j]),np.ascontiguousarray(f[:,j])
    u,v=a.view(np.uint64),b.view(np.uint64);ix=np.flatnonzero(u!=v)
    if not len(ix):continue
    x,y=a[ix],b[ix];mag=np.maximum(abs(x),abs(y));d=abs(x-y)
    near=mag<1e-30
    rel=np.divide(d,mag,out=np.zeros_like(d),where=mag>0)
    def order(w):return np.where((w>>np.uint64(63))!=0,~w,w^np.uint64(1<<63))
    U,V=order(u[ix]),order(v[ix]);ulp=np.maximum(U,V)-np.minimum(U,V)
    i=int(np.argmax(d))
    diagnostics[name]={"mismatches":len(ix),"near_zero_both":int(near.sum()),"non_near_zero":int((~near).sum()),"magnitude_min":float(mag.min()),"magnitude_max":float(mag.max()),"max_abs_pair":[float(x[i]),float(y[i])],"max_ulp":int(ulp.max()),"max_relative":float(rel.max()),"nonnear_exceed_8ulp":int(np.sum((~near)&(ulp>8))),"nonnear_exceed_relative":int(np.sum((~near)&(rel>2e-15))),"classification":"NEAR_ZERO" if near.all() else "MIXED_OR_NON_NEAR_ZERO","hard_gate_unchanged":True}
emit("NEAR_ZERO_AUDIT",diagnostics);write("near_zero.json",diagnostics)
solver,_=ns["original"]()
M=.9*3*np.sqrt(3)/4;syn=[]
for n in (256,512,1024):
    dx=4/n;r=(np.arange(n)+.5)*dx;m=M*r**3/(r*r+1)**1.5;c=2*m/r
    p=np.sqrt(3*M/(2*np.pi*(r*r+1)**2.5*(1-c)))
    a,al,mn,edge=solver["geometry"](p,np.zeros_like(p),r,dx,False)
    cn=2*mn/r;i=int(np.argmax(cn))
    aa=(cn[i-1]+cn[i+1]-2*cn[i])/2;bb=(cn[i+1]-cn[i-1])/2
    z=-bb/(2*aa) if aa<0 else np.inf
    fit={"r":float(r[i]+z*dx),"C":float(cn[i]+bb*z+aa*z*z)} if abs(z)<=1 else None
    syn.append({"n":n,"C_Linf":float(np.max(abs(cn-c))),"native_r":float(r[i]),"native_C":float(cn[i]),"native_C_error":float(abs(cn[i]-.9)),"subcell":fit,"subcell_C_error":abs(fit["C"]-.9) if fit else None,"subcell_r_error":abs(fit["r"]-np.sqrt(2)) if fit else None})
emit("SUBCELL",{"cases":syn,"diagnostic_only":True});write("subcell.json",syn)
def trial(key,N,B):
    cache=Path(tempfile.mkdtemp(prefix=key+"-",dir=OUT))
    env=dict(os.environ);env["NUMBA_CACHE_DIR"]=str(cache)
    for k in ns["E"]["environment"]["threads"]:env[k]=str(N if k=="NUMBA_NUM_THREADS" else B)
    subprocess.run([sys.executable,str(Path(__file__).resolve()),"trial",key,str(N),str(B)],env=env,check=True)
    a=np.load(OUT/(key+"-trace.npy"),allow_pickle=False)
    case=json.loads((OUT/(key+"-case.json")).read_text());case.pop("elapsed_seconds")
    receipt=json.loads((OUT/(key+"-receipt.json")).read_text())
    return a,case,receipt
cells={};platform=None;baseline=None
for cell in P["factorial"]["cells"]:
    key,N,B=cell["id"],cell["numba"],cell["blas"]
    a,ar,ae=trial(key+"_1",N,B);b,br,be=trial(key+"_2",N,B)
    cmp=ns["compare"](a,b);ah=ns["compare"](a,h);af=ns["compare"](a,f)
    stable_env=ae["fingerprint_sha256"]==be["fingerprint_sha256"]
    if platform is None:platform=ae["platform_sha256"]
    same_platform=platform==ae["platform_sha256"]==be["platform_sha256"]
    repeat=cmp["exact"] and ar==br and stable_env and same_platform and ae["cache"]!=be["cache"]
    rec={"id":key,"numba":N,"blas":B,"repeat_exact":bool(repeat),"environment_equal":stable_env,"same_platform":same_platform,"historical_exact":ah["exact"],"failed_exact":af["exact"],"trace_sha256":ah["sha_a"],"historical_mismatches":{k:v for k,v in (ah["columns"] or {}).items() if v["bit_mismatch"]},"repeat_comparison":cmp}
    cells[key]=rec;emit("CELL",rec);write("cells.json",cells)
    if not repeat:finish("THREAD_CONDITIONED_REPEATABILITY_HOLD",cells=cells)
    if key=="N1B1":
        if not ah["exact"]:finish("THREAD_BASELINE_HISTORICAL_HOLD",cells=cells)
        baseline=ah["sha_a"]
effect=[k for k,v in cells.items() if not v["historical_exact"]]
match=[k for k,v in cells.items() if v["failed_exact"]]
finish("THREAD_FACTORIAL_COMPLETE__SCIENTIFIC_HOLD",cells=cells,observed_effect_cells=effect,exact_historical_failed_signature_cells=match,historical_root_cause="UNRESOLVED_CPU_AND_EXECUTION_CONFOUND",scope="one VM; tested threads only")
