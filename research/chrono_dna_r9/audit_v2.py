"""R9A bounded public synthetic replication; no production authority."""
import base64, hashlib, json, subprocess, tempfile, time, sys, os
from pathlib import Path
from collections import deque
N=24; LAST=8; ZERO="0"*64; CAP="chrono.r9a.fixture.v1"
REPOS={"A":"Hawkar-usls/Janus","B":"Hawkar-usls/janus-meta-registry"}
BRANCH={"A":"research/chrono-dna-r9-node-a","B":"research/chrono-dna-r9-node-b"}
FILE="research/chrono_dna_r9/journal.json"
def req(ok,reason):
    if not ok: raise ValueError(reason)
def canon(x):return json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def sha(x):return hashlib.sha256(canon(x)).hexdigest()
def cmd(*args,cwd=None):return subprocess.run(args,cwd=cwd,check=True,capture_output=True,timeout=30).stdout
def keypair(root):
    p=root/"private.pem"; q=root/"public.pem"
    cmd("openssl","genpkey","-algorithm","ED25519","-out",str(p))
    p.chmod(0o600)
    cmd("openssl","pkey","-in",str(p),"-pubout","-out",str(q))
    return p,q.read_text()
def sign(b,k):
    with tempfile.TemporaryDirectory() as d:
        p=Path(d);(p/"b").write_bytes(canon(b))
        s=cmd("openssl","pkeyutl","-sign","-rawin","-inkey",str(k),"-in",str(p/"b"))
        return {"body":b,"signature":base64.b64encode(s).decode()}
def verify(p,pub):
    req(type(p) is dict and set(p)=={"body","signature"} and len(canon(p))<8192,"ENVELOPE")
    req(type(pub) is str and len(pub)<512,"KEY")
    with tempfile.TemporaryDirectory() as d:
        q=Path(d);(q/"b").write_bytes(canon(p["body"]));(q/"pub").write_text(pub)
        (q/"sig").write_bytes(base64.b64decode(p["signature"],validate=True))
        try:cmd("openssl","pkeyutl","-verify","-pubin","-rawin","-inkey",str(q/"pub"),"-in",str(q/"b"),"-sigfile",str(q/"sig"))
        except subprocess.CalledProcessError:raise ValueError("SIGNATURE")
    return p["body"]
def initial():return [[i,i+1] for i in range(N-1)]
def gh(e):return sha({"n":N,"edges":sorted(e)})
def owner(v):return "A" if v%2 else "B"
def other(n):return "B" if n=="A" else "A"
def mutate(e,ops):
    q={tuple(x) for x in e}
    req(type(ops) is list and len(ops)==2,"OPS")
    for op,u,w in ops:
        req(type(u) is int and type(w) is int and 0<=u<N and 0<=w<N and u!=w,"EDGE")
        req(op in ("add","del") and ((u,w) in q)==(op=="del"),"EDGE")
        if op=="add":q.add((u,w))
        else:q.remove((u,w))
    return sorted(map(list,q))
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
def body(v,e,h):
    ops=[["add",v-1,v+10],["del",v-1,v]]
    return {"cap":CAP,"type":"DELTA","id":f"R9A-{v}","writer":owner(v),"recipient":other(owner(v)),"version":v,"parent":h,"before":gh(e),"after":gh(mutate(e,ops)),"ops":ops}
def apply(p,pub,v,e,h):
    b=verify(p,pub);req(type(b) is dict and set(b)=={"cap","type","id","writer","recipient","version","parent","before","after","ops"},"SCHEMA")
    req(b["version"]==v,"VERSION")
    req(b["writer"]==owner(v) and b["recipient"]==other(owner(v)),"OWNER")
    req(b==body(v,e,h),"CHAIN_OR_DELTA")
    e=mutate(e,b["ops"]);return e,sha(b)
def ackbody(v,p):
    b=p["body"];return {"cap":CAP,"type":"ACK","version":v,"sender":other(owner(v)),"recipient":owner(v),"packet_sha256":sha(p),"head":sha(b),"graph":b["after"],"action_authority":False}
def checkack(a,p,pub,v):req(verify(a,pub)==ackbody(v,p),"ACK_BINDING")
def publish(s):
    path=Path(FILE);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(canon(s)+b"\n")
    cmd("git","add",FILE);cmd("git","commit","-m",f"R9A {s['node']} v{s['version']} journal")
    cmd("git","push","origin","HEAD:refs/heads/"+BRANCH[s["node"]])
def peer_read(peer,tmp):
    try:
        cmd("git","fetch","--depth=1","https://github.com/"+REPOS[peer]+".git","refs/heads/"+BRANCH[peer],cwd=tmp)
        raw=cmd("git","show","FETCH_HEAD:"+FILE,cwd=tmp)
    except subprocess.CalledProcessError:return None
    req(len(raw)<131072,"PEER_SIZE");s=json.loads(raw)
    req(s["cap"]==CAP and s["node"]==peer and s["repo"]==REPOS[peer] and s["fingerprint"]==sha(s["pub"]),"PEER_ID")
    return s
def newstate(n,pub):
    return {"cap":CAP,"node":n,"repo":REPOS[n],"pub":pub,"fingerprint":sha(pub),"peer_pub":None,"version":0,"head":ZERO,"edges":initial(),"packets":{},"acks":{},"verified_acks":[],"retry":{},"duplicate_deliveries":0,"audited_distances":0,"done":False}
def run(n):
    req(os.environ.get("GITHUB_REPOSITORY")==REPOS[n] and os.environ.get("GITHUB_REF")=="refs/heads/"+BRANCH[n],"BRANCH")
    req(not Path(FILE).exists(),"SESSION_ALREADY_EXISTS")
    cmd("git","config","user.name","chrono-r9-research[bot]");cmd("git","config","user.email","chrono-r9-research@users.noreply.github.com")
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);key,pub=keypair(root);tmp=root/"peer";tmp.mkdir();cmd("git","init","-q",cwd=tmp)
        s=newstate(n,pub);publish(s);wait=0;waiting=None
        for tick in range(70):
            p=peer_read(other(n),tmp)
            if p is None:time.sleep(3);continue
            if s["peer_pub"] is None:s["peer_pub"]=p["pub"];publish(s)
            req(p["pub"]==s["peer_pub"],"PEER_KEY_CHANGED")
            v=s["version"];vs=str(v)
            if v and owner(v)==n and v not in s["verified_acks"]:
                if vs in p["acks"]:
                    checkack(p["acks"][vs],s["packets"][vs],s["peer_pub"],v)
                    s["verified_acks"].append(v);publish(s);waiting=None;wait=0
                else:
                    if waiting!=v:waiting=v;wait=0
                    wait+=1
                    if wait==2:
                        s["retry"][vs]=sha(s["packets"][vs]);publish(s)
                    time.sleep(3);continue
            if v==1 and n=="B" and vs not in s["acks"]:
                if p["retry"].get(vs)==sha(s["packets"][vs]):
                    req(p["packets"][vs]==s["packets"][vs],"RETRY_CHANGED")
                    old=gh(s["edges"]);req(s["version"]==1 and old==s["packets"][vs]["body"]["after"],"DUP_STATE")
                    s["duplicate_deliveries"]+=1;s["acks"][vs]=sign(ackbody(v,s["packets"][vs]),key)
                    publish(s)
                else:time.sleep(3);continue
            if v==LAST:
                s["done"]=True;publish(s);print(json.dumps({"status":"SYNC_DONE","node":n,"version":v,"head":s["head"],"graph":gh(s["edges"]),"verified_acks":s["verified_acks"],"duplicates":s["duplicate_deliveries"]}));return
            w=v+1;ws=str(w)
            if owner(w)==n:
                pkt=sign(body(w,s["edges"],s["head"]),key);e,h=apply(pkt,pub,w,s["edges"],s["head"])
            elif ws in p["packets"]:
                pkt=p["packets"][ws];e,h=apply(pkt,s["peer_pub"],w,s["edges"],s["head"])
            else:time.sleep(3);continue
            s["edges"]=e;s["head"]=h;s["version"]=w;s["packets"][ws]=pkt;s["audited_distances"]+=audit(e)
            if owner(w)!=n and not (w==1 and n=="B"):s["acks"][ws]=sign(ackbody(w,pkt),key)
            publish(s);time.sleep(3)
        raise ValueError("BOUNDED_POLL_TIMEOUT")
def audit_run(n):
    s=json.loads(Path(FILE).read_bytes());req(s["done"] and s["version"]==LAST,"LOCAL_NOT_DONE")
    with tempfile.TemporaryDirectory() as d:
        cmd("git","init","-q",cwd=d);p=None
        for _ in range(30):
            p=peer_read(other(n),d)
            if p and p["done"]:break
            time.sleep(3)
        req(p and p["done"] and p["version"]==LAST,"PEER_NOT_DONE")
        req(s["peer_pub"]==p["pub"] and p["peer_pub"]==s["pub"],"KEY_BINDING")
        q={n:s,other(n):p};e=initial();h=ZERO;checked=0
        for v in range(1,LAST+1):
            w=owner(v);r=other(w);pkt=q[w]["packets"][str(v)]
            req(pkt==q[r]["packets"][str(v)],"PACKET_MISMATCH")
            e,h=apply(pkt,q[w]["pub"],v,e,h)
            checkack(q[r]["acks"][str(v)],pkt,q[r]["pub"],v)
            req(v in q[w]["verified_acks"],"ACK_NOT_VERIFIED")
            checked+=audit(e)
        req(all(x["edges"]==e and x["head"]==h and x["audited_distances"]==LAST*N*N for x in q.values()),"CONVERGENCE")
        req(q["B"]["duplicate_deliveries"]==1 and q["A"]["retry"].get("1")==sha(q["A"]["packets"]["1"]),"RETRY")
        tests={}
        def rejected(name,fn,reason):
            try:fn()
            except ValueError as exc:req(str(exc)==reason,"UNEXPECTED "+str(exc));tests[name]=True
            else:raise ValueError("UNEXPECTED_ACCEPT")
        pkt=q["A"]["packets"]["1"];bad=json.loads(canon(pkt));bad["body"]["after"]=ZERO
        rejected("tamper",lambda:apply(bad,q["A"]["pub"],1,initial(),ZERO),"SIGNATURE")
        rejected("wrong_key",lambda:apply(pkt,q["B"]["pub"],1,initial(),ZERO),"SIGNATURE")
        rejected("gap",lambda:apply(q["A"]["packets"]["3"],q["A"]["pub"],1,initial(),ZERO),"VERSION")
        rejected("stale",lambda:apply(pkt,q["A"]["pub"],LAST,e,h),"VERSION")
        print(json.dumps({"status":"R9A_AUDIT_PASS","node":n,"versions":LAST,"signed_acks":LAST,"graph":gh(e),"head":h,"audited_distances":checked,"retry_verified":True,"negative":tests,"persistent_public_fingerprints":{x:y["fingerprint"] for x,y in q.items()}},sort_keys=True))
if __name__=="__main__":
    {"sync":run,"audit":audit_run}[sys.argv[1]](sys.argv[2])
