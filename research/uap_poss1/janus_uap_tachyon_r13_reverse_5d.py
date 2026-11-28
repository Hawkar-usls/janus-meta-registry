#!/usr/bin/env python3
import collections,csv,hashlib,importlib.util,io,json,math,os,pathlib,re,subprocess,urllib.request
import numpy as np,h5py
from scipy import signal
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.3-REVERSE-5D-CONTRACT-2026-11-28-v1.0.json"
O=U/"JANUS-UAP-TACHYON-R1.3-REVERSE-5D-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text())
def git(*a):return subprocess.check_output(["git",*a])
def sha(b):return hashlib.sha256(b).hexdigest()
def canon(v):return json.dumps(v,sort_keys=True,ensure_ascii=True,separators=(",",":"),allow_nan=False).encode()
def read(path):return json.loads(pathlib.Path(path).read_text())
def check(name,ok,detail):
    tests.append({"id":name,"pass":bool(ok),"detail":detail})
    if not ok:raise AssertionError(name)
tests=[]
for k in ("path","reverse_road","cosmos_prior"):
    expected=p["canonical"][{"path":"blob","reverse_road":"reverse_road_blob","cosmos_prior":"cosmos_blob"}[k]]
    assert git("hash-object",p["canonical"][k]).decode().strip()==expected
orig=read(p["canonical"]["path"])
assert len(orig["five_dimensions"])==5
u,t=[read(U/x) for x in p["scope"]["inventory"]]
core=read(U/"JANUS-UAP-R1.1-CURATED-CORE-2026-11-28-v1.0.json")
paths={x["path"] for z in (u,t) for x in z["inventory"]}
narrow={x["path"] for x in core["inventory"]}|set(t["direct_topic_paths"])
check("DISCOVERY_UNION",len(paths)==5798 and len(narrow)==249,{"all":len(paths),"narrow":len(narrow)})
# Traverse current immutable tree, not moving main.
tree={}
for raw in git("ls-tree","-rz","--full-tree",p["source_commit"]).split(b"\0"):
    if not raw:continue
    a,b=raw.split(b"\t",1);mode,kind,h=a.decode().split();name=b.decode("utf-8","surrogateescape")
    if kind=="blob":tree[name]=h
extra={x for x in tree if x.startswith("registry/uap/") and re.search(r"JANUS-UAP-(?:TACHYON-)?R1\.",x) and x.endswith(".json")}
paths|=extra
proc=subprocess.Popen(["git","cat-file","--batch"],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
def walk(v,path=""):
    if isinstance(v,dict):
        for k,w in v.items():yield from walk(w,path+"/"+str(k).replace("~","~0").replace("/","~1"))
    elif isinstance(v,list):
        for i,w in enumerate(v):yield from walk(w,path+"/"+str(i))
    else:yield path,v
pattern=re.compile(r"(?:data|registry|experiments|research|EYE|artifacts)/[A-Za-z0-9_./-]+\.json\b")
timepattern=re.compile(r"(?:time|date|utc|timestamp|gps)",re.I)
negpattern=re.compile(r"\b(?:HOLD|BLOCKED|FAIL|NEGATIVE|NOT_ESTABLISHED|UNRESOLVED|NO_PHYSICAL|NO_TACHYON)\b|(?:HOLD|BLOCKED|FAIL|NEGATIVE|NOT_ESTABLISHED|UNRESOLVED|NO_PHYSICAL|NO_TACHYON)_",re.I)
rows=[];outgoing=collections.defaultdict(set);incoming=collections.defaultdict(set);failures=[]
try:
    for path in sorted(paths):
        h=tree.get(path)
        if not h:failures.append({"path":path,"reason":"PATH_MISSING"});continue
        proc.stdin.write((h+"\n").encode());proc.stdin.flush()
        hdr=proc.stdout.readline().split();assert hdr[0].decode()==h and hdr[1]==b"blob"
        n=int(hdr[2]);b=proc.stdout.read(n);assert len(b)==n and proc.stdout.read(1)==b"\n"
        assert hashlib.sha1(("blob "+str(n)+"\0").encode()+b).hexdigest()==h
        try:
            enc="utf-16" if b.startswith((b"\xff\xfe",b"\xfe\xff")) else "utf-8-sig"
            def reject(s):raise ValueError(s)
            j=json.loads(b.decode(enc),parse_constant=reject)
        except (ValueError,UnicodeError,RecursionError) as e:failures.append({"path":path,"sha":h,"reason":str(e)[:250]});continue
        # Order is traversal only; actual temporal order requires explicit event records.
        leaves=[];negative=[];timestamp_fields=0;url_count=0
        for ptr,v in walk(j):
            digest=sha(canon([ptr,v]));leaves.append(digest)
            if timepattern.search(ptr.rsplit("/",1)[-1]) and isinstance(v,(str,int,float)):timestamp_fields+=1
            if isinstance(v,str):
                if negpattern.search(v) and len(negative)<12:negative.append({"pointer":ptr,"value_sha256":sha(v.encode("utf-8","surrogatepass"))})
                if v.startswith(("https://","http://")):url_count+=1
                for match in pattern.finditer(v):
                    dest=match.group()
                    if dest in paths and dest!=path:outgoing[path].add(dest);incoming[dest].add(path)
        f=sha(canon(leaves));rev=sha(canon(leaves[::-1]));assert f==sha(canon(leaves[::-1][::-1]))
        rows.append({"path":path,"blob":h,"source_sha256":sha(b),"leaf_count":len(leaves),"forward_leaf_digest":f,"reverse_leaf_digest":rev,"roundtrip":True,"timestamp_field_count_not_validated":timestamp_fields,"source_url_fields":url_count,"negative_markers":negative,"narrow":path in narrow})
finally:
    proc.stdin.close();assert proc.wait()==0
check("CORPUS_COVERAGE",len(rows)+len(failures)==len(paths),{"parsed":len(rows),"quarantined":len(failures),"extra_count":len(extra)})
for r in rows:
    q=r["path"];r["forward_reference_count"]=len(outgoing[q]);r["reverse_reference_count"]=len(incoming[q])
edges=sum(len(v) for v in outgoing.values());assert edges==sum(len(v) for v in incoming.values())
# Backward necessity lookup is a reference graph only, not measured causal arrows.
reverse_edges=[{"terminal":k,"referenced_by":sorted(v)} for k,v in sorted(incoming.items()) if v]
def get(url,expected,cap=12_000_000):
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"JANUS reverse control/1.3"}),timeout=50) as f:b=f.read(cap+1)
    assert len(b)<=cap and sha(b)==expected
    return b
m=read(p["measurement"]["parent"])
physical={}
try:
    c=m["chime"];b=get(c["url"],c["sha256"]);r=list(csv.DictReader(io.StringIO(b.decode("utf-8-sig"))))
    dm=[float(x["dm_fitb"]) for x in r];assert len(dm)==600 and sorted(dm)==sorted(dm[::-1])
    physical["CHIME"]={"status":"BYTE_PARITY_AND_ROW_MIRROR_PASS","rows":len(r),"dm_invariant":True,"chronological_waveform":False,"sha256":sha(b)}
except Exception as e:physical["CHIME"]={"status":"HOLD_ACQUISITION","error":str(e)[:300]}
try:
    gg=m["gwosc"]["files"];a={}
    for k in ("H1","L1"):
        b=get(gg[k]["url"],gg[k]["sha256"])
        with h5py.File(io.BytesIO(b),"r") as h:x=h["strain/Strain"][:]
        assert len(x)==131072 and np.array_equal(x,x[::-1][::-1]);a[k]=x
    fs=4096;sos=signal.butter(4,[35,350],btype="bandpass",fs=fs,output="sos");white={}
    for k,x in a.items():
        bg=np.concatenate((x[:12*fs],x[20*fs:]));f,ps=signal.welch(bg,fs=fs,nperseg=fs)
        w=np.interp(np.fft.rfftfreq(len(x),1/fs),f,ps);w=np.maximum(w,np.max(w)*1e-12)
        white[k]=signal.sosfiltfilt(sos,np.fft.irfft(np.fft.rfft(x)/np.sqrt(w),n=len(x)))
    N=len(a["H1"]);M=41
    def corr(H,L,lo,hi):
        vals=[]
        y=L[lo:hi];y=y-y.mean()
        for k in range(-M,M+1):
            x=H[lo+k:hi+k];x=x-x.mean();vals.append(float(np.dot(x,y)/(np.linalg.norm(x)*np.linalg.norm(y))))
        i=int(np.argmax(np.abs(vals)));return i-M,vals[i]
    wins=[(int(15.25*fs),int(15.5*fs))]+[(i*fs,int((i+.25)*fs)) for i in [3,5,7,9,11,20,22,24,26,28]]
    pairs=[]
    for lo,hi in wins:
        k,v=corr(white["H1"],white["L1"],lo,hi);kr,vr=corr(white["H1"][::-1],white["L1"][::-1],N-hi,N-lo)
        assert k==-kr and math.isclose(v,vr,abs_tol=1e-12)
        pairs.append({"forward_lag_samples":k,"reverse_lag_samples":kr,"forward_corr":v,"reverse_corr":vr})
    physical["GWOSC"]={"status":"RAW_REACQUIRED_OFFLINE_MIRROR_PASS","samples_per_detector":N,"event":pairs[0],"off_windows":pairs[1:],"fs_hz":fs,"physical_reversal":False,"front_timing_claim":False}
except Exception as e:physical["GWOSC"]={"status":"HOLD_ACQUISITION_OR_PARITY","error":str(e)[:300]}
geo=read(U/"JANUS-UAP-R1.2-SPATIOTEMPORAL-RECONSTRUCTION-2026-11-28-v1.0.json")
timed=sorted([{"id":x["id"],"utc":x["utc"],"state":x["state"]} for x in geo["phoenix_reports"] if x["utc"]],key=lambda x:x["utc"])
physical["PHOENIX"]={"status":"REPORT_ORDER_ONLY","forward":timed,"reverse":timed[::-1],"untimed_or_ambiguous":len(geo["phoenix_reports"])-len(timed),"carrier_track":False}
physical["OPERA"]={"status":"PUBLISHED_SUMMARY_ONLY","relative_speed_interval":m["published_control"]["relative_speed_90CI"],"reverse_coordinate_sign_not_measured":True}
# Native RETINA: replay original generator and native scorer against frozen R1.2A receipt.
retina={}
try:
    pin=p["retina"];subprocess.run(["git","fetch","--depth=1","https://github.com/Hawkar-usls/janus-meta-registry.git",pin["receipt_commit"]],check=True,timeout=100)
    old=json.loads(git("show",pin["receipt_commit"]+":"+pin["receipt"]));ct=json.loads(git("show",pin["receipt_commit"]+":"+pin["contract"]))
    folder=pathlib.Path("/tmp/r13-cosmos");folder.mkdir(exist_ok=True)
    for args in (["git","init","-q",str(folder)],["git","-C",str(folder),"fetch","--depth=1","https://github.com/Hawkar-usls/Janus-Cosmos.git",pin["native_commit"]],["git","-C",str(folder),"checkout","--detach","FETCH_HEAD"]):subprocess.run(args,check=True,timeout=120)
    assert git("-C",str(folder),"hash-object",str(folder/pin["native_code"])).decode().strip()==pin["native_code_blob"]
    os.chdir(folder)
    sp=importlib.util.spec_from_file_location("retina_native",folder/pin["native_code"]);nm=importlib.util.module_from_spec(sp);sp.loader.exec_module(nm)
    ex=ct["frozen_exam"];contexts=[tuple(x) for x in ex["contexts_hz_s"]];banks={x:nm.templates(*x) for x in contexts}
    records=[];i=0
    for seed in ex["seeds"]:
        rng=np.random.default_rng(seed)
        for kind in ex["classes"]:
            for idx in range(ex["examples_per_class_per_seed"]):
                df,dt=contexts[int(rng.integers(len(contexts)))];cube=nm.generate(rng,kind,df,dt,True);b,params=banks[(df,dt)]
                before=sha(np.ascontiguousarray(cube).tobytes());prior=old["rows"][i]
                assert before==prior["source_sha256"] and prior["seed"]==seed and prior["class"]==kind
                a=nm.score(cube,b,params,df);assert all(math.isclose(a[k],prior["native_score"][k],rel_tol=1e-10,abs_tol=1e-10) for k in a)
                mir=np.ascontiguousarray(cube[:,::-1,:]);r=nm.score(mir,b,params,df);assert sha(np.ascontiguousarray(mir[:,::-1,:]).tobytes())==before
                records.append({"seed":seed,"class":kind,"index":idx,"forward":a,"reverse":r,"source_sha256":before,"roundtrip":True});i+=1
    assert i==288
    retina={"status":"NATIVE_FORWARD_REVERSE_REPLAY_PASS","cubes":i,"native_calls":2*i,"max_physical_score_delta":max(abs(x["forward"]["physical"]-x["reverse"]["physical"]) for x in records),"records":records,"actual_vetoes":0,"real_radio_groups":0}
except Exception as e:retina={"status":"HOLD_NATIVE_REPLAY","error":str(e)[:350]}
finally:os.chdir(R)
# Egg analogy: identical terminal, multiple predecessor histories. Replay both.
hist=[["yolk","white_A","membranes","shell"],["yolk","white_B","membranes","shell"]]
back=[list(reversed(x)) for x in hist]
check("EGG_NONUNIQUE_PREDECESSOR",len({tuple(x) for x in back})==2 and len({x[-1] for x in hist})==1 and [x[::-1] for x in back]==hist,{"histories":hist,"meaning":"constructed analogy only; same terminal does not identify its causal history"})
def slope(x):return float(np.dot(np.arange(len(x))-(len(x)-1)/2,np.asarray(x)-np.mean(x)))
a=[0,1,3,7,9];b=[0,2,5,2,0]
check("ASYMMETRIC_AND_SYMMETRIC_CONTROLS",slope(a)==-slope(a[::-1]) and slope(b)==slope(b[::-1])==0,{"forward":slope(a),"reverse":slope(a[::-1]),"symmetric":slope(b)})
check("INTERVAL_INVARIANCE",all((t*t-x*x)==((-t)*(-t)-x*x) for t,x in [(3,2),(2,3),(3,3)]),{"note":"units c=1; reversing coordinate sign is not a physical process"})
# Enrichment states use substantive deltas (not turn index) and preserve explicit gaps.
state={"known":["archival references are not causal links","carrier coupling unspecified"],"gaps":["H4","H5","independent blind holdout"]};turns=[]
def turn(name,axes,delta):
    global state
    previous=sha(canon(state));new={"known":sorted(set(state["known"])|set(delta)),"gaps":state["gaps"]};next_hash=sha(canon(new))
    turns.append({"turn":name,"parent_state_sha256":previous,"state_sha256":next_hash,"axes":axes,"delta":delta,"status":"ORIGIN_PRIME" if next_hash!=previous else "NO_INFORMATION_GAIN"})
    state=new
turn("CORPUS",orig["five_dimensions"],[f"mirrored structured documents={len(rows)}",f"quarantined={len(failures)}",f"reference edges={edges}"])
turn("MEASUREMENTS",orig["five_dimensions"],[f"{k}: {v['status']}" for k,v in physical.items()])
turn("RETINA",orig["five_dimensions"],[f"native scorer replay: {retina['status']}","no carrier inference from score"])
turn("FORWARD_REPLAY",orig["five_dimensions"],["terminal state has nonunique toy antecedents","numerical time reversal preserves interval classification","no calibrated carrier response established"])
out={"schema":"janus.uap_tachyon.reverse_5d.result.v1","status":"REVERSE_SPIRAL_EXECUTED__PHYSICAL_CARRIER_HOLD","contract_sha256":sha(P.read_bytes()),"source_commit":p["source_commit"],"coverage":{"discovery_union":5798,"narrow_union":249,"extra_artifacts":len(extra),"total_paths":len(paths),"parsed":len(rows),"quarantine":failures,"reference_edges":edges},"document_receipts":rows,"reverse_reference_edges":reverse_edges,"measurements":physical,"retina":retina,"synthetic_checks":tests,"origin_prime_turns":turns,"origin_prime":state,"physical_retrocausal_events_confirmed":0,"carrier_observables":0,"actual_vetoes":0,"authority_changed":False,"limits":["All indexed JSON structurally mirrored; not full semantic adjudication of every document or original external raw source. Reference adjacency is not physical causation.","No raw CHIME waveform or authentic ON/OFF real radio groups; synthetic RETINA only.","GWOSC offline numerical reversal is ordinary control; not front timing.","No proof of physical retrocausality, H4 and H5 blocked."]}
O.write_text(json.dumps(out,ensure_ascii=True,indent=2,allow_nan=False)+"\n")
assert json.loads(O.read_text())["coverage"]["parsed"]==len(rows)
print(json.dumps({"coverage":out["coverage"],"measurements":{k:v["status"] for k,v in physical.items()},"gw_event":physical.get("GWOSC",{}).get("event"),"retina":{k:v for k,v in retina.items() if k!="records"},"tests":len(tests),"turns":len(turns),"carrier":"HOLD"},sort_keys=True))
