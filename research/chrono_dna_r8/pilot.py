"""R8 MITOSIS isolated synthetic transport. No production authority."""
import base64, hashlib, json, os, sqlite3, subprocess, tempfile, sys
from pathlib import Path
from collections import deque
ROOT=Path(__file__).resolve().parent
CAP="chrono.memory.graph.delta.r8.fixture"
N=32
ZERO="0"*64
def canon(x): return json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def sha(x): return hashlib.sha256(canon(x)).hexdigest()
def write(p,x): p.write_bytes(canon(x)+b"\n")
def read(p): return json.loads(p.read_bytes())
def require(ok,why):
    if not ok: raise ValueError(why)
def keypair(path):
    k=path/"private.pem"; p=path/"public.pem"
    subprocess.run(["openssl","genpkey","-algorithm","ED25519","-out",str(k)],check=True,capture_output=True)
    subprocess.run(["openssl","pkey","-in",str(k),"-pubout","-out",str(p)],check=True,capture_output=True)
    return k,p.read_text()
def crypt(body,key,signature=None):
    with tempfile.TemporaryDirectory() as td:
        d=Path(td); (d/"body").write_bytes(canon(body))
        if signature is None:
            cmd=["openssl","pkeyutl","-sign","-rawin","-inkey",str(key),"-in",str(d/"body")]
        else:
            (d/"pub").write_text(key); (d/"sig").write_bytes(base64.b64decode(signature,validate=True))
            cmd=["openssl","pkeyutl","-verify","-pubin","-rawin","-inkey",str(d/"pub"),"-in",str(d/"body"),"-sigfile",str(d/"sig")]
        r=subprocess.run(cmd,capture_output=True,timeout=5); require(r.returncode==0,"SIGNATURE")
        return base64.b64encode(r.stdout).decode() if signature is None else True
def signed(b,k): return {"body":b,"signature":crypt(b,k)}
def verify(p,pub):
    require(set(p)=={"body","signature"},"ENVELOPE")
    require(len(canon(p))<=16384,"SIZE"); crypt(p["body"],pub,p["signature"]); return p["body"]
def gh(edges): return sha({"n":N,"edges":sorted(map(list,edges))})
def initial(): return {(i,i+1) for i in range(N-1)}
def generate(out):
    out.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory() as td:
        key,pub=keypair(Path(td)); e=initial(); parent=ZERO; packets=[]
        for v in range(1,13):
            before=gh(e); ops=[["add",v-1,v+12],["del",v-1,v]]
            for op,u,w in ops:
                if op=="add": e.add((u,w))
                else: e.remove((u,w))
            body={"capability":CAP,"sender":"A","recipient":"B","id":f"R8-A-{v}","version":v,"parent":parent,"before":before,"after":gh(e),"ops":ops}
            p=signed(body,key); packets.append(p); parent=sha(body)
        fork=dict(packets[7]["body"]);fork["id"]="R8-A-fork";fork["parent"]=ZERO
        bad=dict(packets[4]["body"]);bad["id"]="R8-A-invalid";bad["ops"]=[["add",4,17],["del",31,0]]
        conflict=dict(packets[3]["body"]);conflict["id"]="R8-A-conflicting-v4";conflict["after"]=ZERO
        bundle={"schema":CAP,"public_key":pub,"packets":packets,"fork":signed(fork,key),"invalid":signed(bad,key),"conflict":signed(conflict,key),"initial":gh(initial()),"final":gh(e),"head":parent}
        write(out/"bundle.json",bundle)
    print(json.dumps({"status":"OUTBOX_CREATED","packets":len(packets),"bundle_sha256":sha(bundle),"final":bundle["final"]}))
class Node:
    def __init__(self,db,pub):
        self.db=sqlite3.connect(db);self.pub=pub
        with self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS head(v INTEGER,chain TEXT,g TEXT)")
            self.db.execute("CREATE TABLE IF NOT EXISTS edges(u INTEGER,w INTEGER,PRIMARY KEY(u,w))")
            self.db.execute("CREATE TABLE IF NOT EXISTS seen(id TEXT PRIMARY KEY)")
            if not self.db.execute("SELECT 1 FROM head").fetchone():
                self.db.execute("INSERT INTO head VALUES(0,?,?)",(ZERO,gh(initial())))
                self.db.executemany("INSERT INTO edges VALUES(?,?)",sorted(initial()))
    def snapshot(self):
        return (self.db.execute("SELECT * FROM head").fetchone(),tuple(self.db.execute("SELECT * FROM edges ORDER BY u,w")),tuple(self.db.execute("SELECT id FROM seen ORDER BY id")))
    def accept(self,p,inject=False):
        b=verify(p,self.pub)
        require(set(b)=={"capability","sender","recipient","id","version","parent","before","after","ops"} and b["capability"]==CAP and b["sender"]=="A" and b["recipient"]=="B","IDENTITY")
        require(type(b["version"]) is int and type(b["id"]) is str and type(b["ops"]) is list and 1<=len(b["ops"])<=4,"SCHEMA")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            (v,h,g),edges,seen=self.snapshot()
            require((b["id"],) not in seen,"REPLAY")
            require(b["version"]==v+1,"VERSION")
            require(b["parent"]==h,"PARENT");require(b["before"]==g,"BEFORE")
            for item in b["ops"]:
                require(type(item) is list and len(item)==3,"OP")
                op,u,w=item
                require(op in ("add","del") and type(u) is type(w) is int and 0<=u<N and 0<=w<N and u!=w,"OP")
                exists=self.db.execute("SELECT 1 FROM edges WHERE u=? AND w=?",(u,w)).fetchone()
                require(bool(exists)==(op=="del"),"EDGE")
                self.db.execute("INSERT INTO edges VALUES(?,?)" if op=="add" else "DELETE FROM edges WHERE u=? AND w=?",(u,w))
            e=tuple(self.db.execute("SELECT * FROM edges ORDER BY u,w")); require(gh(e)==b["after"],"AFTER")
            self.db.execute("INSERT INTO seen VALUES(?)",(b["id"],));self.db.execute("UPDATE head SET v=?,chain=?,g=?",(b["version"],sha(b),b["after"]))
            require(not inject,"INJECTED")
def audit(node):
    (_,_,g),e,_=node.snapshot();require(gh(e)==g,"GRAPH")
    a=[[] for _ in range(N)]
    for u,v in e:a[u].append(v)
    count=0
    for s in range(N):
        d={s:0};q=deque([s])
        while q:
            u=q.popleft()
            for v in a[u]:
                if v not in d:d[v]=d[u]+1;q.append(v)
        oracle=[N+1]*N;oracle[s]=0
        for _ in range(N-1):
            for u,v in e:oracle[v]=min(oracle[v],oracle[u]+1)
        require(all(d.get(v,N+1)==oracle[v] for v in range(N)),"ORACLE")
        count+=N
    return count
def receive(bundle_path,out,source_commit):
    bundle=read(bundle_path); require(bundle["schema"]==CAP and bundle["initial"]==gh(initial()),"GENESIS")
    require(len(bundle["packets"])==12,"COUNT");out.mkdir(parents=True,exist_ok=False)
    tests={};checked=0
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);db=root/"b.sqlite";node=Node(db,bundle["public_key"])
        packets=bundle["packets"]
        def reject(name,p,reason,**kw):
            before=node.snapshot()
            try:node.accept(p,**kw)
            except ValueError as e:require(str(e)==reason,"UNEXPECTED "+str(e))
            else:raise ValueError("UNEXPECTED ACCEPT "+name)
            require(node.snapshot()==before,"ROLLBACK");tests[name]=True
        for p in packets[:4]:node.accept(p);checked+=audit(node)
        node.db.close();node=Node(db,bundle["public_key"]);require(node.snapshot()[0][0]==4,"RESTART")
        tests["offline_restart"]=True
        reject("missing_versions",packets[7],"VERSION")
        reject("replay",packets[3],"REPLAY")
        reject("conflicting_version",bundle["conflict"],"VERSION")
        reject("invalid_mid_batch",bundle["invalid"],"EDGE")
        reject("transaction_rollback",packets[4],"INJECTED",inject=True)
        for p in packets[4:7]:node.accept(p);checked+=audit(node)
        reject("wrong_parent",bundle["fork"],"PARENT")
        tamper=json.loads(canon(packets[7]));tamper["body"]["after"]=ZERO
        reject("tampered",tamper,"SIGNATURE")
        for p in packets[7:]:node.accept(p);checked+=audit(node)
        node.db.close();node=Node(db,bundle["public_key"]);head,edges,seen=node.snapshot()
        require(head==(12,bundle["head"],bundle["final"]) and len(seen)==12,"CONVERGENCE")
        tests["converged_after_restart"]=True;reject("persistent_replay",packets[-1],"REPLAY")
        key,pub=keypair(root)
        ack={"capability":CAP,"type":"ACK","sender":"B","recipient":"A","source_commit":source_commit,"bundle_sha256":sha(bundle),"version":12,"head":head[1],"graph":head[2],"accepted":len(seen),"audited_distances":checked,"tests":tests,"action_authority":False}
        write(out/"ack.json",{"public_key":pub,"receipt":signed(ack,key)})
    print(json.dumps(ack,sort_keys=True))
def check(bundle_path,ack_path,source_commit):
    b=read(bundle_path);a=read(ack_path);r=verify(a["receipt"],a["public_key"])
    require(r["capability"]==CAP and r["type"]=="ACK" and r["sender"]=="B" and r["recipient"]=="A" and r["source_commit"]==source_commit and r["bundle_sha256"]==sha(b) and r["version"]==12 and r["accepted"]==12 and r["head"]==b["head"] and r["graph"]==b["final"] and r["audited_distances"]==12*N*N and len(r["tests"])==9 and all(r["tests"].values()) and r["action_authority"] is False,"ACK_BINDING")
    print(json.dumps({"status":"ACK_VERIFIED","graph":r["graph"],"source_commit":source_commit,"ack_sha256":sha(a)}))
if __name__=="__main__":
    mode=sys.argv[1]
    if mode=="generate":generate(Path(sys.argv[2]))
    elif mode=="receive":receive(Path(sys.argv[2]),Path(sys.argv[3]),sys.argv[4])
    elif mode=="check":check(Path(sys.argv[2]),Path(sys.argv[3]),sys.argv[4])
    else:raise ValueError("MODE")
