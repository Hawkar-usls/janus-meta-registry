"""R9C HEARTBEAT: bounded public synthetic lineage. No production data or self-modification."""
import hashlib,json,os,re,subprocess,tempfile,sys
from pathlib import Path
from collections import deque
from datetime import datetime,timezone
N=24
REPOS={"A":"Hawkar-usls/Janus","B":"Hawkar-usls/janus-meta-registry"}
STATE={"A":"research/chrono-dna-r9c-state-a","B":"research/chrono-dna-r9c-state-b"}
R9B={"A":"73040eea47640e0df71d0a93f81e2a626c505df7","B":"ad503d4f2d0e6647293f200b524e6a6e75368e7f"}
BASE={"A":"c95ee72a3bee01ba3db56803e1387ca8064860f8","B":"aa9f71a4c919cbe588ad87c4872c045ebce69cea"}
OLD_RUN={9:("45795332628","d070cda6e0317073b148e9bbb160beede3bedee3"),10:("45795396308","d0b35ae930293904566d3c188d1275d8b5bae2c5"),11:("45795494008","231a62060beb08244f4f6db865532b71f9a1c735"),12:("45795598911","2985e9ca5ef4ad9f850d6116ad9ab68862b7131d")}
BASE_HEAD="d12ccf590d5aafde88015cae6a524f31801793f0c0b943daf15e8b2650057fe4"
BASE_GRAPH="53ef0b41b7ad2f6003675d91d28c339a5e80042c29102cc5e0db411d74d46ff3"
R9B_HEAD="ebfc3f97d03621c83d9a4d407264033fdf25c9a3f42499e5d71432c3374f66c3"
R9B_GRAPH="67f4eb6e4225febc4da2ab29efdc8db25561a5830b587bd3f4175830b24d9be2"
WORKER="autonomy/chrono_dna/heartbeat.py"
WORKFLOW=".github/workflows/chrono-dna-r9c-heartbeat.yml"
POLICY="autonomy/chrono_dna/heartbeat_policy.json"
PREFIX="research/chrono_dna_r9c/records/"
END=datetime(2026,11,29,tzinfo=timezone.utc)
WAKE_SOURCES={"A":{"ESSENCE v0.5 read-only research heartbeat":".github/workflows/essence-readonly-heartbeat.yml","JANUS Rowan Read-Only Watch":".github/workflows/rowan-autonomous-readonly.yml","JANUS Rowan Lapis Fundamentum zero-credit subscriber":".github/workflows/rowan-lapis-fundamentum-autonomous-consumer.yml"},"B":{"JANUS Sentinel Cross-Repository Mesh Guardian":".github/workflows/janus-sentinel-mesh.yml","JANUS Autonomy Bounded Wake Guardian":".github/workflows/janus-autonomy-bounded-wake-guardian.yml","JANUS Rowan Ecosystem Independent Sync Witness":".github/workflows/janus-rowan-ecosystem-sync-witness.yml"}}

def req(ok,why):
    if not ok:raise ValueError(why)
def canon(x):return json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def sha(x):return hashlib.sha256(canon(x)).hexdigest()
def gh(e):return sha({"n":N,"edges":sorted(e)})
def owner(v):return "A" if v%2 else "B"
def cmd(*a,cwd=None):
    return subprocess.run(a,cwd=cwd,check=True,capture_output=True,timeout=90).stdout
def read(raw):
    req(len(raw)<131072,"SIZE")
    def unique(pairs):
        d={}
        for k,v in pairs:req(k not in d,"DUPLICATE_KEY");d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=unique)
def fetch(tmp,n,ref,tag):
    p=tmp/(n+"-"+tag);p.mkdir()
    cmd("git","init","-q",cwd=p)
    cmd("git","fetch","--depth=1","https://github.com/"+REPOS[n]+".git",ref,cwd=p)
    h=cmd("git","rev-parse","FETCH_HEAD",cwd=p).decode().strip()
    if re.fullmatch("[0-9a-f]{40}",ref):req(h==ref,"REF")
    return p,h
def file(p,h,path):return cmd("git","show",h+":"+path,cwd=p)
def blob(p,h,path):return cmd("git","rev-parse",h+":"+path,cwd=p).decode().strip()
def audit(e):
    a=[[] for _ in range(N)];d=[[N+1]*N for _ in range(N)]
    for i in range(N):d[i][i]=0
    for u,v in e:a[u].append(v);d[u][v]=1
    for k in range(N):
        for i in range(N):
            for j in range(N):d[i][j]=min(d[i][j],d[i][k]+d[k][j])
    for s in range(N):
        z={s:0};q=deque([s])
        while q:
            u=q.popleft()
            for v in a[u]:
                if v not in z:z[v]=z[u]+1;q.append(v)
        req(all(z.get(v,N+1)==d[s][v] for v in range(N)),"ORACLE")
    return N*N
def transition(v,e,h,prev):
    req(type(v) is int and 9<=v<=16,"VERSION")
    old=v<=12
    ops=[["add",v-1,v+10 if old else v+7],["del",v-1,v]]
    q={tuple(x) for x in e}
    for op,u,w in ops:
        req(0<=u<N and 0<=w<N and u!=w and ((u,w) in q)==(op=="del"),"EDGE")
        if op=="add":q.add((u,w))
        else:q.remove((u,w))
    out=sorted(map(list,q))
    return {"cap":"chrono.r9b.attested.fixture.v1" if old else "chrono.r9c.heartbeat.fixture.v1","version":v,"writer":owner(v),"parent":h,"before":gh(e),"after":gh(out),"ops":ops,"ack_previous_record":prev},out
def attest(p,n,old,source):
    workflow=".github/workflows/chrono-dna-r9b.yml" if old else WORKFLOW
    ref="refs/heads/research/chrono-dna-r9b-"+n.lower() if old else "refs/heads/main"
    result=cmd("gh","attestation","verify",str(p),"--repo",REPOS[n],"--signer-workflow",REPOS[n]+"/"+workflow,"--source-ref",ref,"--source-digest",source,"--deny-self-hosted-runners","--format","json")
    req(bool(json.loads(result)),"ATTESTATION")
def validate_wake(run,n,now=None):
    req(type(run) is dict and run.get("name") in WAKE_SOURCES[n],"WAKE_NAME")
    req(run.get("path")==WAKE_SOURCES[n][run["name"]] and run.get("head_branch")=="main" and run.get("event")=="schedule" and run.get("status")=="completed" and run.get("conclusion")=="success","WAKE_EVENT")
    req(run.get("repository",{}).get("full_name")==REPOS[n] and run.get("head_repository",{}).get("full_name")==REPOS[n],"WAKE_REPO")
    req(type(run.get("id")) is int and run["id"]>0 and type(run.get("run_attempt")) is int and run["run_attempt"]>0,"WAKE_ID")
    stamp=datetime.fromisoformat(run["created_at"].replace("Z","+00:00"))
    now=now or datetime.now(timezone.utc)
    req(stamp.tzinfo is not None and -60<=(now-stamp).total_seconds()<=86400,"WAKE_AGE")
    return str(run["id"])
def wake_api(n,wid,now=None):
    req(type(wid) is str and wid.isdigit() and len(wid)<=20,"WAKE_ID")
    run=read(cmd("gh","api","repos/"+REPOS[n]+"/actions/runs/"+wid))
    req(validate_wake(run,n,now)==wid,"WAKE_BINDING")
    return run
def local_wake(n,event):
    if event=="schedule":return True,None
    if event!="workflow_run":return False,None
    raw=Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes()
    data=read(raw);run=data["workflow_run"]
    if run.get("event")!="schedule" or run.get("conclusion")!="success" or run.get("head_branch")!="main":
        return False,None
    wid=validate_wake(run,n)
    actual=wake_api(n,wid)
    req(actual["head_sha"]==run["head_sha"] and actual["run_attempt"]==run["run_attempt"],"WAKE_PAYLOAD")
    return True,wid
def verify(raw,v,e,h,prev,tmp,policy):
    n=owner(v);r=read(raw);old=v<=12
    expected,out=transition(v,e,h,prev)
    fields={"delta","run_id","run_attempt"} if old else {"delta","run_id","run_attempt","source_sha","event"}
    req(type(r) is dict and (set(r)==fields or (not old and set(r)==fields|{"wake_run_id"})) and r["delta"]==expected,"DELTA")
    req(all(type(r[k]) is str and r[k].isdigit() for k in ("run_id","run_attempt")),"RUN_ID")
    if old:
        run,source=OLD_RUN[v];req(r["run_id"]==run and r["run_attempt"]=="1","OLD_RUN")
    else:
        source=r["source_sha"];req(type(source) is str and re.fullmatch("[0-9a-f]{40}",source) and r["event"] in ("schedule","workflow_run"),"SOURCE")
        run=read(cmd("gh","api","repos/"+REPOS[n]+"/actions/runs/"+r["run_id"]))
        req(run["event"]==r["event"] and run["head_sha"]==source and run["head_branch"]=="main" and str(run["run_attempt"])==r["run_attempt"] and run["path"]==WORKFLOW and run["conclusion"]=="success","RUN_NOT_ADMITTED")
        s,sh=fetch(tmp,n,source,"source"+str(v))
        pair=[blob(s,sh,WORKER),blob(s,sh,WORKFLOW)]
        req(pair in policy["allowed_source_pairs"][n],"SOURCE_CODE")
        if r["event"]=="workflow_run":
            req(pair==[policy["worker_blob"],policy["workflow_blobs"][n]],"WAKE_CODE")
            when=datetime.fromisoformat(run["created_at"].replace("Z","+00:00"))
            wake_api(n,r.get("wake_run_id"),when)
        else:req(r.get("wake_run_id") is None,"WAKE_UNEXPECTED")
    p=tmp/f"record-{v}.json";p.write_bytes(raw);attest(p,n,old,source)
    return out,sha(expected),hashlib.sha256(raw).hexdigest(),r["run_id"]
def plan(n,mode):
    req(os.environ.get("GITHUB_REPOSITORY")==REPOS[n],"REPO")
    event=os.environ.get("GITHUB_EVENT_NAME")
    policy=read(Path(POLICY).read_bytes())
    req(policy["version_cap"]==16 and policy["deadline"]=="2026-11-29T00:00:00Z","POLICY")
    if not policy["enabled"] or datetime.now(timezone.utc)>=END:
        print("R9C_DISABLED_OR_EXPIRED");return
    active,wake_id=local_wake(n,event)
    req(mode in ("plan","write") and (mode!="write" or active and os.environ.get("GITHUB_REF")=="refs/heads/main"),"EVENT")
    with tempfile.TemporaryDirectory() as t:
        tmp=Path(t);base=[];old={};states={};heads={};records={}
        for x in ("A","B"):
            p,k=fetch(tmp,x,BASE[x],"base")
            s=read(file(p,k,"research/chrono_dna_r9/journal.json"))
            req(s["done"] and s["version"]==8 and s["head"]==BASE_HEAD and gh(s["edges"])==BASE_GRAPH,"BASE")
            base.append(s["edges"]);old[x]=fetch(tmp,x,R9B[x],"old")
            states[x],heads[x]=fetch(tmp,x,"refs/heads/"+STATE[x],"state")
        req(base[0]==base[1],"BASE_DIVERGENCE")
        e=base[0];h=BASE_HEAD;prev=None;checked=0;runids=[]
        for v in range(9,13):
            p,k=old[owner(v)]
            e,h,prev,run=verify(file(p,k,f"research/chrono_dna_r9b/v{v}.json"),v,e,h,prev,tmp,policy)
            checked+=audit(e);runids.append(run)
        req(h==R9B_HEAD and gh(e)==R9B_GRAPH,"R9B_ANCHOR")
        for x in ("A","B"):
            names=cmd("git","ls-tree","-r","--name-only",heads[x],"--",PREFIX,cwd=states[x]).decode().splitlines()
            for path in names:
                match=re.fullmatch(re.escape(PREFIX)+r"v(13|14|15|16)\.json",path)
                req(match is not None,"UNEXPECTED_STATE_PATH");v=int(match.group(1))
                req(owner(v)==x and v not in records,"WRONG_WRITER_OR_DUP")
                records[v]=file(states[x],heads[x],path)
        req(sorted(records)==list(range(13,13+len(records))),"GAP")
        for v in sorted(records):
            e,h,prev,run=verify(records[v],v,e,h,prev,tmp,policy);checked+=audit(e);runids.append(run)
        req(len(runids)==len(set(runids)),"REUSED_RUN")
        used=[(owner(v),read(raw).get("wake_run_id")) for v,raw in records.items() if read(raw).get("wake_run_id") is not None]
        req(len(used)==len(set(used)),"WAKE_REUSED")
        v=13+len(records)
        result={"node":n,"next_version":v,"last_version":v-1,"head":h,"graph":gh(e),"audited_distances":checked,"event":event,"wake_run_id":wake_id,"state_head":heads[n]}
        if v==17:
            print(json.dumps({"status":"R9C_FINAL_AUDIT_PASS" if n=="A" and active else "R9C_CAP_REACHED",**result},sort_keys=True));return
        if owner(v)!=n or not active or (n,wake_id) in used:
            print(json.dumps({"status":"R9C_WAIT" if active else "R9C_PREFLIGHT_PASS",**result},sort_keys=True));return
        if mode=="plan":
            with open(os.environ["GITHUB_OUTPUT"],"a") as f:f.write("write=true\n")
            print(json.dumps({"status":"R9C_READY",**result}));return
        delta,out=transition(v,e,h,prev);checked+=audit(out)
        source=os.environ["GITHUB_SHA"];req(re.fullmatch("[0-9a-f]{40}",source),"SOURCE")
        r={"delta":delta,"run_id":os.environ["GITHUB_RUN_ID"],"run_attempt":os.environ["GITHUB_RUN_ATTEMPT"],"source_sha":source,"event":event,"wake_run_id":wake_id}
        p=Path("r9c-out")/f"v{v}.json";p.parent.mkdir(exist_ok=True);req(not p.exists(),"EXISTS");p.write_bytes(canon(r)+b"\n")
        with open(os.environ["GITHUB_OUTPUT"],"a") as f:f.write("record="+str(p)+"\nstate_head="+heads[n]+"\n")
        print(json.dumps({"status":"R9C_RECORD_READY","version":v,"graph":gh(out),"head":sha(delta),"audited_distances":checked}))
def selftest():
    e=[[i,i+1] for i in range(N-1)];h="0"*64;prev=None
    for v in range(9,17):
        d,e=transition(v,e,h,prev);h=sha(d);prev=sha({"delta":d});req(audit(e)==N*N,"AUDIT")
    for v in (8,17):
        try:transition(v,e,h,prev)
        except ValueError:pass
        else:raise ValueError("CAP")
    # Independent wake-envelope controls; no network or authority.
    now=datetime(2026,11,26,12,tzinfo=timezone.utc)
    for n in ("A","B"):
        name=next(iter(WAKE_SOURCES[n]))
        good={"name":name,"path":WAKE_SOURCES[n][name],"head_branch":"main","event":"schedule","status":"completed","conclusion":"success","repository":{"full_name":REPOS[n]},"head_repository":{"full_name":REPOS[n]},"id":123,"run_attempt":1,"created_at":"2026-11-26T11:00:00Z"}
        req(validate_wake(good,n,now)=="123","WAKE_POSITIVE")
        for patch in ({"event":"push"},{"event":"workflow_dispatch"},{"event":"pull_request"},{"conclusion":"failure"},{"head_branch":"other"},{"path":"wrong.yml"},{"repository":{"full_name":"other/repo"}},{"head_repository":{"full_name":"other/repo"}},{"created_at":"2026-11-24T11:00:00Z"},{"id":0}):
            try:validate_wake({**good,**patch},n,now)
            except ValueError:pass
            else:raise ValueError("WAKE_NEGATIVE")
    print("R9C1_WAKE_CONTROLS_PASS 20/20")
    print("R9C_LOCAL_CONTROLS_PASS")
if __name__=="__main__":
    if sys.argv[1]=="selftest":selftest()
    else:plan(sys.argv[1],sys.argv[2])
