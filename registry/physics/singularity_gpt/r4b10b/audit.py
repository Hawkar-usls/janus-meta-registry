"""Engineering mutation witness. No original threshold or source is edited."""
import ast,copy,hashlib,json,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
P=json.loads((HERE/"protocol.json").read_text())
SRC=HERE.parent/"r4b10"/"examine.py"
ROOT=Path(sys.argv[1]).resolve()
def load(p):return json.loads(p.read_text())
def unique(folder,name):
    fs=list((ROOT/folder).rglob(name))
    assert len(fs)==1,(folder,name,fs)
    return fs[0]
def blob(p):
    b=p.read_bytes()
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
assert blob(SRC)==P["source_blob"]
assert blob(SRC.parent/"protocol.json")==P["source_protocol_blob"]
base_protocol=load(SRC.parent/"protocol.json")
source=ast.parse(SRC.read_text())
loops=[n for n in ast.walk(source) if isinstance(n,ast.For) and isinstance(n.target,ast.Tuple) and [getattr(x,"id",None) for x in n.target.elts]==["name","threshold"]]
assert len(loops)==1
loop=loops[0]
# Directly execute the exact original decision statements on a separating fixture.
frozen_fixture={"global_threshold":10.,"routes":{"iid":5.},"oracle":{"iid":5.}}
env=dict(frozen=frozen_fixture,rt="iid",kind="iid",grid=[-.012,0.,.012],scores=[8.,0.,8.],old={"stage":"PHASE","screen":True},ok=True,r={"grid_complete":True},est=0.,true=8.,c={"star":1.})
exec(compile(ast.Module(body=[copy.deepcopy(loop)],type_ignores=[]),str(SRC),"exec"),env)
fixture=env["r"]
assert fixture["global"]["label"]=="AMBIGUOUS" and fixture["global"]["truth_included"] is True
assert fixture["conditional"]["label"]=="DSS" and fixture["conditional"]["truth_included"] is False
# Rebuild frozen thresholds from the original calibration artifacts, not new simulations.
fp=unique("r4b10-thresholds","thresholds.json");rp=unique("r4b10-router","router.json")
for file,checksum in ((fp,"thresholds.sha256"),(rp,"router.sha256")):
    expected=unique(file.parent.name,checksum).read_text().split()[0]
    assert hashlib.sha256(file.read_bytes()).hexdigest()==expected
frozen=load(fp);router=load(rp);b=base_protocol["bank"];kinds=b["noise_types"]
nodes=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in {"q95","maximum","groups","thresholds"}]
env={"np":np,"B":b,"KINDS":kinds,"KNOWN":kinds[:3],"SHA":hashlib.sha256((SRC.parent/"protocol.json").read_bytes()).hexdigest()}
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SRC),"exec"),env)
cal=[]
for kind in kinds:
    a=load(unique("r4b10-calibration-"+kind,"calibration_rows.json"))
    assert a["seed"]==b["calibration_seed"] and a["protocol_sha256"]==env["SHA"]
    assert len(a["rows"])==720
    cal.extend(a["rows"])
assert len(cal)==3600
rebuilt=env["thresholds"](cal)
for key in ("global_threshold","routes","oracle","protocol_sha256","seed"):
    assert rebuilt[key]==frozen[key],key
for key in ("strata","route_cells"):
    assert sorted(json.dumps(x,sort_keys=True) for x in rebuilt[key])==sorted(json.dumps(x,sort_keys=True) for x in frozen[key]),key
fallback={}
for rt in kinds[:3]+["unknown"]:
    cells=[x for x in rebuilt["route_cells"] if x["route"]==rt]
    fallback[rt]=dict(cells=len(cells),sparse=sum(x["n"]<20 for x in cells),reason="unknown" if rt=="unknown" else ("sparse" if any(x["n"]<20 for x in cells) else ("no_cells" if not cells else "dense_max")),threshold=rebuilt["routes"][rt])
print("R4B10B_FIXTURE",json.dumps({"fixture":fixture,"fallback":fallback,"calibration_rows":len(cal)}),flush=True)
# Add mutation arms only to a copy of the original AST. Original evaluator and baseline arms unchanged.
assert isinstance(loop.iter,ast.Tuple)
for expr in ['("conditional_half", 0.5*frozen["global_threshold"] if rt=="iid" else frozen["routes"][rt])','("conditional_oracle", frozen["oracle"]["iid"] if rt=="iid" else frozen["routes"][rt])','("conditional_zero", 0.0 if rt=="iid" else frozen["routes"][rt])']:
    loop.iter.elts.append(ast.parse(expr,mode="eval").body)
ast.fix_missing_locations(source)
archive=load(unique("r4b10-evaluation-iid","trials.json"))
assert len(archive)==1080
sys.argv=[str(SRC),"evaluate","iid",str(rp),str(fp)]
exec(compile(source,str(SRC),"exec"),{"__file__":str(SRC),"__name__":"__main__"})
replayed=load(Path("r4b10-output/trials.json"))
assert len(replayed)==len(archive)
def key(x):return (x["sub"],x["i"],x["noise"],x["missing"])
a={key(x):x for x in archive};r={key(x):x for x in replayed}
assert a.keys()==r.keys() and len(r)==1080
originals=("global","conditional","oracle_noise_diagnostic")
baseline_mismatches=[]
for k,x in r.items():
    y=a[k]
    if any(x[f]!=y[f] for f in ("input_sha256","route")) or any(x[m]!=y[m] for m in originals):baseline_mismatches.append(list(k))
muts={}
for name,val in (("conditional_half",.5*frozen["global_threshold"]),("conditional_oracle",frozen["oracle"]["iid"]),("conditional_zero",0.)):
    routed=[x for x in replayed if x["route"]=="iid"]
    other=[x for x in replayed if x["route"]!="iid"]
    assert all(x[name]["threshold"]==val for x in routed)
    assert all(x[name]==x["conditional"] for x in other)
    muts[name]=dict(threshold=val,affected_rows=len(routed),unchanged_other_rows=len(other),label_changes=sum(x[name]["label"]!=x["conditional"]["label"] for x in routed),truth_inclusion_changes=sum(x[name]["truth_included"]!=x["conditional"]["truth_included"] for x in routed),positive_DSS=sum(x["sub"]=="positive" and x["correct_params"] and x[name]["label"]=="DSS" for x in routed),negative_DSS=sum(x["sub"]!="positive" and x[name]["label"]=="DSS" for x in routed))
d=dict(id=P["id"],status="PATH_WITNESS_PASS" if not baseline_mismatches else "REPLAY_MISMATCH_HOLD",fixture=fixture,calibration_rebuilt=True,fallback=fallback,replay_n=len(replayed),baseline_mismatches=baseline_mismatches,mutations=muts,scientific_hold=True,physical_use_authorized=False,limitations=["Artificial mutation thresholds are engineering witnesses only, not recalibration or admissible thresholds.","A half-threshold may not cross actual decision boundaries; controlled fixture tests a guaranteed crossing.","Full replay covers original IID evaluation only; calibration rebuild covers all noise families."])
out=Path("r4b10b-output");out.mkdir(exist_ok=True);(out/"result.json").write_text(json.dumps(d,indent=2)+"\n")
(out/"trials.json").write_text(json.dumps(replayed,separators=(",",":"))+"\n")
print("R4B10B_RESULT",json.dumps(d),flush=True)
assert not baseline_mismatches
