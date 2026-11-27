import json,sys,hashlib
from pathlib import Path
from collections import defaultdict
HERE=Path(__file__).resolve().parent
P=json.loads((HERE/"protocol.json").read_text())
root=Path(sys.argv[1]); groups=defaultdict(list); allrows=[]; input_hashes={}
for kind in P["artifacts"]:
    folder=root/("r4b10-evaluation-"+kind)
    files=list(folder.rglob("trials.json")); results=list(folder.rglob("result.json"))
    assert len(files)==len(results)==1,(kind,files,results)
    f=files[0];r=json.loads(results[0].read_text());a=json.loads(f.read_text())
    assert r["mode"]=="evaluate" and r["kind"]==kind and r["seed"]==652931
    assert len(a)==P["required_rows_per_kind"] and all(x["kind"]==kind for x in a)
    assert len({(x["sub"],x["i"],x["noise"],x["missing"]) for x in a})==len(a)
    assert sum(x["sub"]!="stationary" for x in a)==P["required_nonstationary_per_kind"]
    input_hashes[kind]=dict(trials_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),result_sha256=hashlib.sha256(results[0].read_bytes()).hexdigest(),protocol_sha256=r["protocol_sha256"])
    for x in a:
        route=x["route"]
        status=("abstained" if route=="unknown" else ("correct" if kind==route else "incorrect")) if kind in ("iid","long_memory","narrowband") else ("untrained_unknown" if route=="unknown" else "untrained_known")
        for key in ((kind,status),(kind,x["sub"],x["noise"],x["missing"],status),("ALL",status)):groups[key].append(x)
        allrows.append(x)
assert len(allrows)==5400
assert len({x["protocol_sha256"] for x in input_hashes.values()})==1
def summary(a):
    out=dict(n=len(a),nonstationary=sum(x["sub"]!="stationary" for x in a),positive=sum(x["sub"]=="positive" for x in a))
    for m in P["methods"]:
        out[m]=dict(covered=sum(x[m]["truth_included"] is True for x in a),not_covered=sum(x[m]["truth_included"] is False for x in a),DSS=sum(x[m]["label"]=="DSS" for x in a),AMBIGUOUS=sum(x[m]["label"]=="AMBIGUOUS" for x in a),REJECT=sum(x[m]["label"]=="REJECT" for x in a),correct_DSS=sum(x["sub"]=="positive" and x["correct_params"] and x[m]["label"]=="DSS" for x in a),false_DSS=sum(x["sub"]!="positive" and x[m]["label"]=="DSS" for x in a))
    out["conditional_global_label_disagreements"]=sum(x["conditional"]["label"]!=x["global"]["label"] for x in a)
    out["conditional_global_coverage_disagreements"]=sum(x["conditional"]["truth_included"]!=x["global"]["truth_included"] for x in a)
    return out
d=dict(id=P["id"],source_run=P["source_run"],input_hashes=input_hashes,overall=summary(allrows),cells=[dict(key=list(k),**summary(a)) for k,a in groups.items()],scientific_hold=True,limitations=["Retrospective paired data, not independent observations.","Identical thresholds make routing causality untestable here.","Tangent/orthogonal not trained classes; UNKNOWN is not a verified correct noise identification."])
out=Path("r4b10a-output");out.mkdir(exist_ok=True);(out/"result.json").write_text(json.dumps(d,indent=2)+"\n")
print("R4B10A_RESULT",json.dumps({**d,"cells":[x for x in d["cells"] if len(x["key"])==2]},separators=(",",":")),flush=True)
