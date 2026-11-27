#!/usr/bin/env python3
"""SINGULARITY GPT R1: bounded CPU experiment, not a numerical GR solver."""
import hashlib, json, math, random, subprocess, os
from pathlib import Path
from collections import Counter
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
OUT=Path(os.environ.get("SINGULARITY_OUTPUT","singularity-r1-output"))
OUT.mkdir(parents=True,exist_ok=True)
torch.set_num_threads(2)
BLOCK=128
SEEDS=(1729,2718,3141)
def digest(b): return hashlib.sha256(b).hexdigest()
def canonical(d): return json.dumps(d,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
def write(name,d): (OUT/name).write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
def seed(s): random.seed(s); np.random.seed(s); torch.manual_seed(s)
bundle=json.loads((HERE/"corpus.json").read_text())
dossier=json.loads((ROOT/"registry/physics/JANUS_SPACETIME_CRITICAL_COLLAPSE_R1.json").read_text())
docs=[]
for x in bundle["local_sources"]:
    b=(ROOT/x["path"]).read_bytes()
    assert hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()==x["blob"],x["path"]
    docs.append((x["path"],x["category"],json.loads(b)))
for x in bundle["cosmos_documents"]: docs.append((x["path"],x["category"],x["document"]))
# Exclude every numerical row from the language corpus: numerical test has its own split.
docs.append(("critical-collapse-metadata","literature",{k:v for k,v in dossier.items() if k!="numerical_series"}))
# Family-level holdout: no QED R3A case or result used to train LM; related facts in
# other historical docs may remain. This measures corpus transfer, not blind physics.
def is_holdout(p): return "R3A" in p.upper() or "QED" in p.upper()
def to_bytes(x): return canonical({"evidence_category":x[1],"source":x[0],"document":x[2]})
train_docs=[x for x in docs if not is_holdout(x[0])]
test_docs=[x for x in docs if is_holdout(x[0])]
assert train_docs and test_docs
tr=[torch.tensor(list(to_bytes(x)),dtype=torch.long) for x in train_docs]
te=[torch.tensor(list(to_bytes(x)),dtype=torch.long) for x in test_docs]
class ByteTransformer(nn.Module):
    # JGPT-style causal byte transformer, fresh weights; no inherited checkpoint.
    def __init__(self):
        super().__init__()
        self.wte=nn.Embedding(256,64); self.wpe=nn.Embedding(BLOCK,64)
        self.transformer=nn.TransformerEncoder(nn.TransformerEncoderLayer(64,4,256,dropout=0,batch_first=True,norm_first=True,activation="gelu"),2,enable_nested_tensor=False)
        self.ln=nn.LayerNorm(64); self.head=nn.Linear(64,256,bias=False)
    def forward(self,x):
        n=x.shape[1]; z=self.wte(x)+self.wpe(torch.arange(n))[None]
        mask=torch.triu(torch.ones(n,n,dtype=torch.bool),diagonal=1)
        return self.head(self.ln(self.transformer(z,mask=mask)))
def batch(ds,rng,n=8):
    a=[];b=[]
    for _ in range(n):
        d=ds[rng.randrange(len(ds))]; k=rng.randrange(len(d)-BLOCK)
        a.append(d[k:k+BLOCK]);b.append(d[k+1:k+BLOCK+1])
    return torch.stack(a),torch.stack(b)
@torch.no_grad()
def lm_eval(m):
    m.eval(); total=0.; count=0
    for d in te:
        for k in range(0,len(d)-1,BLOCK):
            x=d[k:k+BLOCK];y=d[k+1:k+BLOCK+1];x=x[:len(y)]
            total+=F.cross_entropy(m(x[None]).reshape(-1,256),y,reduction="sum").item();count+=len(y)
    return total/count
# Numeric benchmark: contiguous D intervals held out across ALL series; no same-D leakage.
series=bundle["full_precision_series"]
names=list(series)
def hold(d): return 3.25<=d<=3.35 or 3.72<=d<=3.79 or 4.1<=d<=4.3
records=[]; train=[]; test=[]
for i,name in enumerate(names):
    rows=sorted(series[name]["rows"])
    assert all(math.isfinite(d) and math.isfinite(y) for d,y in rows)
    for d,y in rows: (test if hold(d) else train).append((i,d,y))
    records.extend((i,d,y) for d,y in rows)
assert len(records)==945 and train and test
assert not ({d for _,d,_ in train}&{d for _,d,_ in test})
stats={}
for i in range(len(names)):
    v=np.array([y for j,d,y in train if i==j]);stats[i]=(float(v.mean()),max(float(v.std()),1e-8))
def features(rows):
    xx=[]; yy=[]; ids=[]; bas=[]
    for i,d,y in rows:
        candidates=sorted((a,b) for j,a,b in train if j==i and a!=d)
        left=[p for p in candidates if p[0]<d][-2:]; right=[p for p in candidates if p[0]>d][:2]
        mu,sd=stats[i]; tokens=[[d-4.,0.,1.,0.]]
        for p in left+right: tokens.append([p[0]-4.,(p[1]-mu)/sd,0.,0.])
        while len(tokens)<5: tokens.append([0.,0.,0.,1.])
        xx.append(tokens);yy.append((y-mu)/sd);ids.append(i)
        if candidates: bas.append(float(np.interp(d,[p[0] for p in candidates],[p[1] for p in candidates])))
    return torch.tensor(xx,dtype=torch.float32),torch.tensor(yy,dtype=torch.float32),torch.tensor(ids),np.array(bas)
x,y,i,_=features(train); xt,yt,it,baseline=features(test)
class NumericalTransformer(nn.Module):
    def __init__(self):
        super().__init__()
        self.inp=nn.Linear(4,48);self.sid=nn.Embedding(len(names),48)
        self.enc=nn.TransformerEncoder(nn.TransformerEncoderLayer(48,4,96,dropout=0,batch_first=True,activation="gelu"),2,enable_nested_tensor=False)
        self.head=nn.Linear(48,1)
    def forward(self,x,i):
        return self.head(self.enc(self.inp(x)+self.sid(i)[:,None],src_key_padding_mask=x[:,:,3].bool())[:,0]).squeeze(-1)
def metrics(pred):
    out={}
    for j,name in enumerate(names):
        mask=np.array([i==j for i,_,_ in test]); truth=np.array([y for _,_,y in test])[mask]
        p=pred[mask]; q=baseline[mask]
        out[name]={"n":int(mask.sum()),"mae":float(np.mean(np.abs(p-truth))),"interpolation_mae":float(np.mean(np.abs(q-truth)))}
    return out
# Freeze receipts before optimization; no network data used by trainer.
manifest={"train_docs":[{"path":z[0],"category":z[1],"sha256":digest(to_bytes(z))} for z in train_docs],"test_docs":[{"path":z[0],"category":z[1],"sha256":digest(to_bytes(z))} for z in test_docs],"numeric_train_sha256":digest(canonical(train)),"numeric_test_sha256":digest(canonical(test)),"numeric_train":len(train),"numeric_test":len(test),"split":"D intervals [3.25,3.35], [3.72,3.79], [4.1,4.3]","seeds":SEEDS,"corpus_sha256":digest((HERE/"corpus.json").read_bytes()),"claim_ceiling":"Historical source replay and interpolation only; no astrophysical discovery or independent physics test."}
write("precommit.json",manifest)
counts=torch.ones(256,256,dtype=torch.float64)
for d in tr: counts.index_put_((d[:-1],d[1:]),torch.ones(len(d)-1,dtype=torch.float64),accumulate=True)
logp=(counts/counts.sum(1,keepdim=True)).log()
bigram=-sum(logp[d[:-1],d[1:]].sum().item() for d in te)/sum(len(d)-1 for d in te)
results=[]
for s in SEEDS:
    seed(s);m=ByteTransformer(); opt=torch.optim.AdamW(m.parameters(),lr=0.001)
    initial=lm_eval(m);m.train();rng=random.Random(s)
    for step in range(300):
        a,b=batch(tr,rng);loss=F.cross_entropy(m(a).reshape(-1,256),b.reshape(-1))
        if not torch.isfinite(loss): raise RuntimeError("nonfinite LM loss")
        opt.zero_grad();loss.backward();nn.utils.clip_grad_norm_(m.parameters(),1.,error_if_nonfinite=True);opt.step()
    final=lm_eval(m)
    torch.save(m.state_dict(),OUT/f"byte-{s}.pt")
    n=NumericalTransformer();op=torch.optim.AdamW(n.parameters(),lr=.002)
    for step in range(300):
        idx=torch.randint(len(x),(64,));loss=F.mse_loss(n(x[idx],i[idx]),y[idx])
        if not torch.isfinite(loss): raise RuntimeError("nonfinite numeric loss")
        op.zero_grad();loss.backward();nn.utils.clip_grad_norm_(n.parameters(),1.,error_if_nonfinite=True);op.step()
    n.eval()
    with torch.no_grad(): raw=n(xt,it).numpy()
    pred=np.array([v*stats[j][1]+stats[j][0] for v,(j,d,_) in zip(raw,test)])
    torch.save(n.state_dict(),OUT/f"numeric-{s}.pt")
    results.append({"seed":s,"byte_parameters":sum(p.numel() for p in m.parameters()),"numeric_parameters":sum(p.numel() for p in n.parameters()),"lm_initial_nll":initial,"lm_final_nll":final,"bigram_nll":bigram,"numeric":metrics(pred)})
    print(json.dumps(results[-1]),flush=True)
# Known relations are an explicit analytic check, not learned discovery.
ref=dossier["reference_values"]["D4"]; delta=ref["Delta"]; gamma=ref["gamma"]
analytic={"D":4,"Delta":delta,"gamma":gamma,"length_ratio":math.exp(-delta),"Ricci_scaling":math.exp(2*delta),"Kretschmann_scaling":math.exp(4*delta),"unstable_exponent":1/gamma}
# Different model families and negative control for unsupported promotion.
lm_win=all(z["lm_final_nll"]<z["bigram_nll"] for z in results)
numeric_win=all(all(v["mae"]<v["interpolation_mae"] for v in z["numeric"].values()) for z in results)
report={"status":"ENGINEERING_EXAM_COMPLETED__SCIENTIFIC_HOLD","lm_beats_bigram_all_seeds":lm_win,"numeric_beats_interpolation_all_series_all_seeds":numeric_win,"results":results,"analytic_reference_check":analytic,"precommit_sha256":digest((OUT/"precommit.json").read_bytes()),"git_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),"torch":torch.__version__,"weights_promoted":False,"astrophysical_detection":False,"quantum_firewall_confirmed":False,"retrocausality_proven":False,"independent_physics_test":False}
write("result.json",report)
print(json.dumps(report,indent=2))
