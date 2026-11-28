#!/usr/bin/env python3
"""Exact counterexamples and source-gated admission, not a physics experiment."""
import hashlib,json,pathlib,subprocess
from fractions import Fraction as F
from itertools import product
ROOT=pathlib.Path("registry/uap")
P=ROOT/"JANUS-UAP-TACHYON-R1.1-CARRIER-IDENTIFIABILITY-PREREG-2026-11-28-v1.0.json"
O=ROOT/"JANUS-UAP-TACHYON-R1.1-CARRIER-IDENTIFIABILITY-RESULT-2026-11-28-v1.0.json"
pr=json.loads(P.read_text(encoding="utf-8"))
src=pr["source_commit"]
def git(*a):return subprocess.check_output(["git",*a])
data={};provenance={}
for k,path in pr["inputs"].items():
    raw=git("show",src+":"+path)
    data[k]=json.loads(raw)
    provenance[k]={"path":path,"git_blob_sha":git("rev-parse",src+":"+path).decode().strip(),"sha256":hashlib.sha256(raw).hexdigest()}
tests=[]
def check(name,condition,details):
    tests.append({"id":name,"pass":bool(condition),"details":details})
    if not condition:raise AssertionError(name)
def joint(direction,q):
    # A and B are observed bits, not simulated spacetime measurements.
    r={(a,b):F(0) for a,b in product((0,1),repeat=2)}
    for u,n in product((0,1),repeat=2):
        prob=F(1,2)*(q if n else 1-q)
        a,b=(u,u^n) if direction=="forward" else (u^n,u)
        r[a,b]+=prob
    return r
def ser(d):return {str(k):str(v) for k,v in d.items()}
qs=[F(0),F(1,8),F(1,4),F(1,2)]
laws=[{"noise":str(q),"joint":ser(joint("forward",q)),"equal":joint("forward",q)==joint("reverse",q)} for q in qs]
check("COMMON_CAUSE_VS_REVERSE",all(x["equal"] for x in laws),laws)
# Leakage has target B copied to A before recorded release; hypothetical retro model has same equation.
leak=joint("reverse",F(1,8));hypothetical=joint("reverse",F(1,8))
check("LEAKAGE_VS_FUTURE_INFORMATION",leak==hypothetical,{"joint":ser(leak),"meaning":"same observed distribution; not independent evidence"})
allbits=list(product((0,1),repeat=2));selected=[x for x in allbits if x[0]==x[1]]
check("SELECTION_CAN_FAKE_PERFECT_MATCH",len(selected)==2 and all(a==b for a,b in selected),{"unselected_accuracy":str(F(2,4)),"selected_accuracy":str(F(2,2)),"retained_fraction":str(F(2,4))})
# Two generative explanations of one identical A/B/C observation.
artifact=(0,1,0);sky=(0,1,0)
check("SINGLE_DETECTOR_NONIDENTIFIABLE",artifact==sky,{"artifact":artifact,"sky":sky,"note":"synthetic detector hit is not sky origin"})
# An independent simultaneous sensor, if modeled as working and sensitive, can break this toy pair only.
artifact2=(artifact,(0,0,0));sky2=(sky,(0,1,0))
check("INDEPENDENT_DETECTOR_TOY_POSITIVE_CONTROL",artifact2!=sky2,{"artifact":artifact2,"sky":sky2,"assumption":"second sensor independent, calibrated and sensitive; not universal discriminator"})
c=299792458
def interval(distance_min_m,tlo_ns,thi_ns,paired=False,front=False,calibrated=False):
    if not(paired and front and calibrated) or tlo_ns>thi_ns or distance_min_m<0:return "HOLD_MISSING_MEASUREMENT"
    # Exact worst case over a conservative rectangular uncertainty set.
    # No direction inference if time interval overlaps zero.
    limit=F(c)*max(abs(tlo_ns),abs(thi_ns))/10**9
    if F(distance_min_m)>limit:return "SPACELIKE_INTERVAL_CANDIDATE_ONLY"
    return "NOT_ROBUSTLY_SPACELIKE"
# Ordinary d=3m; actual delay approx 10.01 ns, recorded 1 ns due to clock offset.
uncal=interval(3,1,1,True,True,False)
corrected=interval(3,9,12,True,True,True)
check("CLOCK_OFFSET_COUNTEREXAMPLE",uncal=="HOLD_MISSING_MEASUREMENT" and corrected=="NOT_ROBUSTLY_SPACELIKE",{"distance_min_m":3,"recorded_delta_ns":1,"calibrated_interval_ns":[9,12],"uncalibrated":uncal,"calibrated":corrected})
ideal=interval(3,1,2,True,True,True)
check("SPACELIKE_TOY_POSITIVE_CONTROL",ideal=="SPACELIKE_INTERVAL_CANDIDATE_ONLY",{"distance_min_m":3,"delta_ns":[1,2],"status":ideal,"carrier_identified":False})
# M2/M3 may be observationally equal if no independent carrier observable is specified.
m2=joint("reverse",F(1,4));m3=joint("reverse",F(1,4))
check("GENERIC_VS_TACHYON_NONIDENTIFIABLE",m2==m3,{"joint":ser(m2),"carrier_specific_response":None})
def admit(g):
    required=("provenance","sensitivity","prospective","timing","physical_interaction","specific_prediction","independent_carrier_measurement","replication","paired_uap_event")
    missing=[k for k in required if g.get(k) is not True]
    return {"status":"HOLD" if missing else "ELIGIBLE_FOR_INDEPENDENT_MODEL_REVIEW_NOT_PROVEN","missing":missing}
names=("provenance","sensitivity","prospective","timing","physical_interaction","specific_prediction","independent_carrier_measurement","replication","paired_uap_event")
# Exhaustive Boolean gate masks, no positive carrier claim even for all true.
masks=0;holds=0;eligible=0
for v in product((False,True),repeat=len(names)):
    r=admit(dict(zip(names,v)));masks+=1
    assert (r["status"]!="HOLD")==all(v)
    holds+=r["status"]=="HOLD";eligible+=r["status"]!="HOLD"
check("FAIL_CLOSED_ALL_GATE_MASKS",masks==512 and holds==511 and eligible==1,{"masks":masks,"holds":holds,"eligible_for_review_only":eligible})
t1=data["t1"]["t1_result"];t2=data["t2"]["t2b_ztf_prepointed"];d=data["deutsch"]["new_blinded_future_test"]
check("SOURCE_NULLS_PRESERVED",t1["isolated_B_event_candidates"]==0 and t1["fully_sensitivity_adjudicable_trials"]==8 and t2["isolated_b_candidates"]==0 and t2["fully_qualified_abc_absence_trials"]==20 and d["after"]["correct_bits"]==131 and d["after"]["total_bits"]==256 and data["cross"]["comparison"]["empirical_physical_link_count"]==0,{"T1":{"qualified":8,"unresolved":t1["unresolved_trials"]},"T2":{"qualified_trials":20,"qualified_unique_b_clusters":t2["fully_qualified_abc_absence_unique_b_clusters"],"unresolved":t2["unresolved_trials"]},"Deutsch":{"bits":131,"total":256,"p":d["after"]["binomial_one_sided_pvalue"],"brier":d["after"]["brier"]},"FAA":{"status":data["faa"]["faa"]["status"],"row":data["faa"]["faa"]["candidate_rows"][0]["row_number"]}})
# Source classification, no independently calibrated emission/reception pairs.
admissions=[
 {"lane":"TOPA","source":"topa","status":"ARCHIVE_PROVENANCE_ONLY","physical_observable":False},
 {"lane":"EYE","source":"geo","status":"WITNESS_LOCALITY_AND_TIME_NOT_OBJECT_TRACK","physical_observable":False},
 {"lane":"RETINA","source":"t1+t2","status":"NEGATIVE_INCOMPLETE_REPLICATIONS_NOT_CARRIER_DATA","physical_observable":False},
 {"lane":"TACHYON","source":"deutsch+sha+trav","status":"NO_DEMONSTRATED_FUTURE_INFORMATION_OR_PHYSICAL_CHANNEL","physical_observable":False},
 {"lane":"ORDINARY_CONTROL","source":"faa","status":"OFFICIAL_UAS_REPORT_NOT_CARRIER_MEASUREMENT","physical_observable":False}]
out={"schema":"janus.uap_tachyon.carrier_identifiability.result.v1.0","status":"SYNTHETIC_ENGINEERING_PASS__EMPIRICAL_IDENTIFIABILITY_HOLD","authority_changed":False,"source_commit":src,"protocol_sha256":hashlib.sha256(P.read_bytes()).hexdigest(),"source_provenance":provenance,"tests":tests,"test_pass_count":sum(t["pass"] for t in tests),"test_count":len(tests),"synthetic_gate_masks":masks,"source_admissions":admissions,"empirical_carrier_specific_observables":0,"empirical_uap_carrier_pairs":0,"admitted_physical_claim":False,"carrier_gate":"H4_BLOCKED_NO_EXCLUSIVE_CALIBRATED_PREDICTION","uap_bridge_gate":"H5_BLOCKED_NO_PAIRED_MEASUREMENT","actual_organ_integration":"NOT_EXECUTED__REGISTRY_ADAPTERS_AND_CONTRACTS_ONLY","next_gate":pr["next_empirical_gate"],"limits":["Exact equality is for constructed examples, not proof of universal indistinguishability.","Tests are designed fixtures and assertions, not a blind independent empirical examination.","All-true Boolean mask is only eligible for review; not sufficient to prove a physical theory.","No novel tachyon detector model or operational experiment performed."]}
O.write_text(json.dumps(out,ensure_ascii=True,indent=2,allow_nan=False)+"\n",encoding="utf-8")
assert json.loads(O.read_text())["test_pass_count"]==len(tests)
print(json.dumps({"status":out["status"],"passed":out["test_pass_count"],"tests":len(tests),"masks":masks,"holds":holds,"eligible_review_only":eligible,"empirical_carrier_specific_observables":0,"empirical_uap_carrier_pairs":0}))
