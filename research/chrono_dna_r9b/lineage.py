"""R9B bounded keyless fixture. All received files are data, never code."""
import hashlib,json,os,subprocess,tempfile,sys
from pathlib import Path
from collections import deque
N=24
REPOS={"A":"Hawkar-usls/Janus","B":"Hawkar-usls/janus-meta-registry"}
BRANCH={"A":"research/chrono-dna-r9b-a","B":"research/chrono-dna-r9b-b"}
BASE_REFS={"A":"c95ee72a3bee01ba3db56803e1387ca8064860f8","B":"aa9f71a4c919cbe588ad87c4872c045ebce69cea"}
BASE_HEAD="d12ccf590d5aafde88015cae6a524f31801793f0c0b943daf15e8b2650057fe4"
BASE_GRAPH="53ef0b41b7ad2f6003675d91d28c339a5e80042c29102cc5e0db411d74d46ff3"
DIR=Path("research/chrono_dna_r9b")
CAP="chrono.r9b.attested.fixture.v1"
def req(x,msg):
    if not x:raise ValueError(msg)
def canon(x):return json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def sha(x):return hashlib.sha256(canon(x)).hexdigest()
def gh(e):return sha({"n":N,"edges":sorted(e)})
def owner(v):return "A" if v%2 else "B"
def cmd(*a,cwd=None):return subprocess.run(a,cwd=cwd,check=True,capture_output=True,timeout=60).stdout
def read(raw):
    req(len(raw)<131072,"SIZE")
    def unique(pairs):
        d={}
        for k,v in pairs:req(k not in d,"DUPLICATE_KEY");d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=unique)
def fetch(n,ref,path,tmp):
    d=tmp/n;d.mkdir(exist_ok=True)
    if not (d/".git").exists():cmd("git","init","-q",cwd=d)
    cmd("git","fetch","--depth=1","https://github.com/"+REPOS[n]+".git",ref,cwd=d)
    return cmd("git","show","FETCH_HEAD:"+path,cwd=d)
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
def transition(v,e,h,previous):
    ops=[["add",v-1,v+10],["del",v-1,v]]
    q={tuple(x) for x in e}
    for op,u,w in ops:
        req(0<=u<N and 0<=w<N and u!=w and ((u,w) in q)==(op=="del"),"EDGE")
        if op=="add":q.add((u,w))
        else:q.remove((u,w))
    out=sorted(map(list,q))
    return {"cap":CAP,"version":v,"writer":owner(v),"parent":h,"before":gh(e),"after":gh(out),"ops":ops,"ack_previous_record":previous},out
def attest(path,n):
    return cmd("gh","attestation","verify",str(path),"--repo",REPOS[n],"--signer-workflow",REPOS[n]+"/.github/workflows/chrono-dna-r9b.yml","--source-ref","refs/heads/"+BRANCH[n],"--deny-self-hosted-runners","--format","json")
def verify_record(raw,v,e,h,previous,tmp):
    n=owner(v);p=tmp/f"v{v}.json";p.write_bytes(raw)
    result=attest(p,n);req(bool(json.loads(result)),"ATTESTATION")
    r=read(raw);expected,out=transition(v,e,h,previous)
    req(type(r) is dict and set(r)=={"delta","run_id","run_attempt"},"SCHEMA")
    req(r["delta"]==expected and type(r["run_id"]) is str and r["run_id"].isdigit() and type(r["run_attempt"]) is str and r["run_attempt"].isdigit(),"DELTA")
    return out,sha(expected),hashlib.sha256(raw).hexdigest(),r
def main(n):
    req(os.environ.get("GITHUB_REPOSITORY")==REPOS[n] and os.environ.get("GITHUB_REF")=="refs/heads/"+BRANCH[n],"BRANCH")
    target=read((DIR/"request.json").read_bytes())["target"]
    req(type(target) is int and ((9<=target<=12 and owner(target)==n) or (target==13 and n=="A")),"TARGET")
    with tempfile.TemporaryDirectory() as t:
        tmp=Path(t);base=[]
        for x in ("A","B"):
            s=read(fetch(x,BASE_REFS[x],"research/chrono_dna_r9/journal.json",tmp))
            req(s["version"]==8 and s["done"] and s["head"]==BASE_HEAD and gh(s["edges"])==BASE_GRAPH,"BASE")
            base.append(s["edges"])
        req(base[0]==base[1],"BASE_DIVERGENCE")
        e=base[0];h=BASE_HEAD;previous=None;runs={};checked=0
        for v in range(9,target):
            raw=fetch(owner(v),"refs/heads/"+BRANCH[owner(v)],str(DIR/f"v{v}.json"),tmp)
            e,h,previous,r=verify_record(raw,v,e,h,previous,tmp)
            runs[str(v)]=r["run_id"];checked+=audit(e)
        if target==13:
            req(len(set(runs.values()))==4,"DISTINCT_RUNS")
            good=tmp/"v12.json";tamper=tmp/"tamper.json";tamper.write_bytes(good.read_bytes()+b" ")
            for p,x,label in [(tamper,"B","TAMPER"),(good,"A","WRONG_REPO")]:
                try:attest(p,x)
                except subprocess.CalledProcessError:pass
                else:raise ValueError(label)
            print(json.dumps({"status":"R9B_FINAL_AUDIT_PASS","version":12,"graph":gh(e),"head":h,"runs":runs,"audited_distances":checked,"negative":{"tamper":True,"wrong_repo":True},"action_authority":False},sort_keys=True));return
        dest=DIR/f"v{target}.json";req(not dest.exists(),"ALREADY_PUBLISHED")
        delta,out=transition(target,e,h,previous);checked+=audit(out)
        rec={"delta":delta,"run_id":os.environ["GITHUB_RUN_ID"],"run_attempt":os.environ["GITHUB_RUN_ATTEMPT"]}
        dest.write_bytes(canon(rec)+b"\n")
        print(json.dumps({"status":"R9B_RECORD_READY","version":target,"prior_verified":target-9,"graph":gh(out),"head":sha(delta),"audited_distances":checked,"run_id":rec["run_id"]}))
        with open(os.environ["GITHUB_OUTPUT"],"a") as f:f.write("record="+str(dest)+"\n")
if __name__=="__main__":main(sys.argv[1])
