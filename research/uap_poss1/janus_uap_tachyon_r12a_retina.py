#!/usr/bin/env python3
import hashlib, importlib.util, json, os, pathlib, subprocess, sys
import numpy as np
from sklearn.metrics import roc_auc_score
root=pathlib.Path.cwd()
p=root/"registry/uap/JANUS-UAP-TACHYON-R1.2A-RETINA-NATIVE-CONTRACT-2026-11-28-v1.0.json"
o=root/"registry/uap/JANUS-UAP-TACHYON-R1.2A-RETINA-NATIVE-RESULT-2026-11-28-v1.0.json"
pr=json.loads(p.read_text()); n=pr["native"]; exam=pr["frozen_exam"]
folder=pathlib.Path("/tmp/janus-r12a-cosmos")
def cmd(*args):return subprocess.check_output(args,text=True).strip()
folder.mkdir(exist_ok=True)
cmd("git","init","-q",str(folder))
cmd("git","-C",str(folder),"fetch","--depth=1","https://github.com/"+n["repo"]+".git",n["commit"])
cmd("git","-C",str(folder),"checkout","--detach","FETCH_HEAD")
assert cmd("git","-C",str(folder),"rev-parse","HEAD")==n["commit"]
for k in ("code","protocol"):
    assert cmd("git","-C",str(folder),"rev-parse","HEAD:"+n[k])==n[k+"_blob"]
    assert cmd("git","hash-object",str(folder/n[k]))==n[k+"_blob"]
os.chdir(folder)
spec=importlib.util.spec_from_file_location("native_retina",folder/n["code"])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert not set(exam["seeds"]) & set(m.S["split"]["development_seeds"]+m.S["split"]["heldout_seeds"])
def digest(c):return hashlib.sha256(np.ascontiguousarray(c).tobytes()).hexdigest()
def score_adapter(cube,df,dt,roles,source_kind,role_verified=False):
    if source_kind not in ("SYNTHETIC_GENERATOR","AUTHENTICATED_RADIO_CUBE"):
        return {"status":"HOLD_INCOMPATIBLE_SOURCE","native_executed":False}
    if not role_verified or roles!=n["input"]["roles"]:
        return {"status":"HOLD_ROLE_PROVENANCE","native_executed":False}
    if not isinstance(cube,np.ndarray) or cube.shape!=tuple(n["input"]["shape"]) or not np.all(np.isfinite(cube)) or not np.isfinite(df) or not np.isfinite(dt) or df<=0 or dt<=0:
        return {"status":"HOLD_ARRAY_OR_AXIS","native_executed":False}
    before=digest(cube)
    bank,params=banks[(df,dt)] if (df,dt) in banks else m.templates(df,dt)
    q=m.score(cube,bank,params,df)
    assert all(np.isfinite(v) for v in q.values())
    assert before==digest(cube)
    return {"status":"NATIVE_SHADOW_SCORE","native_executed":True,"source_sha256":before,"native_score":q,"actual_veto":False,"carrier_identified":False}
contexts=[tuple(x) for x in exam["contexts_hz_s"]];banks={x:m.templates(*x) for x in contexts}
rows=[]; parity=0
for seed in exam["seeds"]:
    rng=np.random.default_rng(seed)
    for kind in exam["classes"]:
        for i in range(exam["examples_per_class_per_seed"]):
            df,dt=contexts[int(rng.integers(len(contexts)))]
            cube=m.generate(rng,kind,df,dt,True)
            r=score_adapter(cube,df,dt,n["input"]["roles"],"SYNTHETIC_GENERATOR",True)
            assert r["native_executed"] and not r["actual_veto"] and not r["carrier_identified"]
            if kind==exam["classes"][0] and i==0:
                bank,params=banks[(df,dt)]
                assert r["native_score"]==m.score(cube,bank,params,df);parity+=1
            rows.append({"seed":seed,"class":kind,"index":i,"df_hz":df,"dt_s":dt,"positive":kind.startswith("target_"),**r})
    print("NATIVE_RETINA_SEED",seed,flush=True)
assert len(rows)==288 and parity==3
df,dt=contexts[0];dummy=np.zeros((4,16,49))
bad=[score_adapter(dummy,df,dt,n["input"]["roles"],s,False) for s in ("CHIME_CATALOG","GWOSC_STRAIN","FAA_REPORT")]
bad.append(score_adapter(dummy,df,dt,["ON"]*4,"AUTHENTICATED_RADIO_CUBE",False))
bad.append(score_adapter(np.zeros((4,15,49)),df,dt,n["input"]["roles"],"SYNTHETIC_GENERATOR",True))
assert all(not r["native_executed"] for r in bad)
def metrics(rr):
    y=[r["positive"] for r in rr];a={}
    for k in ("physical","fixed"):
        scores=[r["native_score"][k] for r in rr]; t=exam["thresholds"][k];kept=[v>=t for v in scores]
        a[k]={"auc":float(roc_auc_score(y,scores)),"shadow_tp":sum(z and q for z,q in zip(y,kept)),"shadow_fp":sum(not z and q for z,q in zip(y,kept)),"weak_kept":sum(r["class"]=="target_weak" and q for r,q in zip(rr,kept))}
    a["paired_positive_losses_physical_vs_fixed"]=sum(r["positive"] and r["native_score"]["fixed"]>=exam["thresholds"]["fixed"] and r["native_score"]["physical"]<exam["thresholds"]["physical"] for r in rr)
    a["positive_count"]=sum(y);a["negative_count"]=len(y)-sum(y);a["weak_total"]=sum(r["class"]=="target_weak" for r in rr)
    return a
out={"schema":"janus.uap_tachyon.retina_native.result.v1","status":"NATIVE_RADIO_SCORER_EXECUTED__SYNTHETIC_ADAPTER_PASS__REAL_AND_CARRIER_HOLD","source_commit":pr["parent_commit"],"contract_sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"native_commit":n["commit"],"native_code_blob":n["code_blob"],"native_protocol_blob":n["protocol_blob"],"native_score_calls":len(rows),"direct_parity_checks":parity,"unchanged_input_count":len(rows),"incompatible_rejections":bad,"metrics":metrics(rows),"per_seed":{str(s):metrics([r for r in rows if r["seed"]==s]) for s in exam["seeds"]},"rows":rows,"actual_vetoes":0,"production_changed":False,"real_radio_groups":0,"carrier_observables":0,"independent_physical_exam":False,"next":"Acquire authenticated native ON/OFF/repeat radio observations and independent calibrated detector response; do not transpose or invent roles from FRB catalogs or gravitational-wave strains."}
o.write_text(json.dumps(out,ensure_ascii=True,indent=2,allow_nan=False)+"\n")
assert json.loads(o.read_text())["native_score_calls"]==288
print(json.dumps({k:v for k,v in out.items() if k not in ("rows","incompatible_rejections")},sort_keys=True))
