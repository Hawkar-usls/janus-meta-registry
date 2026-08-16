#!/usr/bin/env python3
"""JANUS SkayLUCIGate v0.1 — fail-closed LUCI scene/temporal evidence gate.

Algorithmic lineage only:
- Blind Eye/TMOS: instant evidence != memory; clear != artifact; stale data fails closed.
- Yaks Gate IR: independent IR channel; temporal guard; SHA-bound provenance.
Neither TMOS/PIR nor a 38-kHz IR LED is treated as an astronomical detector model.
"""
from __future__ import annotations
import argparse, hashlib, json, math, re, statistics
from datetime import datetime, timezone
from pathlib import Path

VERSION="0.1"
SCHEMA="janus.skay_luci_gate.result.v0.1"
QUALIFIED="QUALIFIED_NO_COUNTERPART"
CANDIDATE="COUNTERPART_CANDIDATE"
BRACKET_S=900.0
MIN_PERSISTENT=2
MIN_SNR=4.0
FWHM_RATIO=(0.70,1.35)
MAX_OFFSET_PSF=0.75
CLAIM_CEILING=("IR_SCENE_AND_TEMPORAL_CLASSIFICATION_ONLY__"
 "NO_COUNTERFACTUAL_PHYSICAL_RECONSTRUCTION_WITHOUT_SPECTRAL_THROUGHPUT_MODEL__"
 "NO_ANOMALY_OR_UAP_ORIGIN_CLAIM__NO_ETI_CLAIM__NO_CAUSALITY")
SAFE_EYE=("JANUS_EYE_MEMORY_DECAY","JANUS_EYE_MEMORY_ATTACK","JANUS_EYE_GHOST_DECAY",
 "JANUS_EYE_STALE_RELEASE_MS","JANUS_EYE_SENSOR_STALE_MS","JANUS_EYE_ARTIFACT_ATTACK",
 "JANUS_EYE_ARTIFACT_DECAY","JANUS_EYE_CLEAR_ATTACK","JANUS_EYE_CLEAR_DECAY","JANUS_TMOS_WARMUP_MS")
SAFE_YAKS=("YG_IR_CARRIER_HZ","YG_IR_AUTO_MS","YG_IR_SKY_MS","YG_IR_BURST_GUARD_MS","YG_IR_ESCAPE_MS")


def sha256_file(p:Path)->str:
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""): h.update(b)
 return h.hexdigest()


def _f(v,d=None):
 try:return float(v)
 except (TypeError,ValueError):return d


def _dt(s):
 s=str(s).strip(); s=s[:-1]+"+00:00" if s.endswith("Z") else s
 d=datetime.fromisoformat(s)
 return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def safe_macro_extract(text,names):
 out={}
 for n in names:
  m=re.search(rf"^\s*#define\s+{re.escape(n)}\s+([^\s/]+)",text,re.M)
  if m: out[n]=m.group(1)
 return out


def source_binding(path:Path|None,kind:str):
 if not path:return None
 text=path.read_text(errors="replace")
 return {"sha256":sha256_file(path),"bytes":path.stat().st_size,
  "safe_macros":safe_macro_extract(text,SAFE_EYE if kind=="eye" else SAFE_YAKS),
  "raw_text_embedded":False,
  "physical_role":"ALGORITHMIC_LINEAGE_ONLY__NOT_ASTRONOMICAL_CALIBRATION"}

TMOS_RE=re.compile(r"\[EYE\]\s+v2\.15A\s+TMOS\s+P/M=(\d)/(\d)\s+inst=(\d)/(\d).*?occ=([0-9.]+).*?clear=([0-9.]+)\s+artifact=([0-9.]+)\s+bad=(\d+)/(\d+)\s+err=(-?\d+)\s+validAgo=(\d+)ms")

def eye_log_summary(path:Path|None):
 if not path:return None
 rec=[]
 for line in path.read_text(errors="replace").splitlines():
  m=TMOS_RE.search(line)
  if m:
   g=m.groups(); rec.append({"p":int(g[2]),"m":int(g[3]),"occ":float(g[4]),"clear":float(g[5]),
    "artifact":float(g[6]),"bad":int(g[7])+int(g[8]),"err":int(g[9]),"age":int(g[10])})
 out={"sha256":sha256_file(path),"bytes":path.stat().st_size,"parsed_tmos_records":len(rec),
  "role":"HARDWARE_LOGIC_SELF_TEST_ONLY__NOT_ASTRONOMICAL_EVIDENCE"}
 if rec:
  n=len(rec); out.update({"instant_presence_fraction":sum(x["p"] for x in rec)/n,
   "instant_motion_fraction":sum(x["m"] for x in rec)/n,"artifact_max":max(x["artifact"] for x in rec),
   "bad_or_error_records":sum(1 for x in rec if x["bad"] or x["err"]),
   "valid_ago_ms_median":statistics.median(x["age"] for x in rec)})
 return out


def status(r): return str((r.get("recovery") or {}).get("status") or r.get("status") or "UNKNOWN")
def qualified(r): return status(r).startswith(QUALIFIED)
def candidate(r): return CANDIDATE in status(r)
def channel(r): return (str(r.get("instrument") or ""),str(r.get("filters") or ""))


def measurement(r):
 rec=r.get("recovery") or {}; ct=rec.get("counterpart_test") or {}; src=ct.get("source") or {}; gate=rec.get("overlap_frame_r1_gate") or {}
 ex,ey,mx,my=map(_f,(r.get("exact_x"),r.get("exact_y"),src.get("x"),src.get("y")))
 off=math.hypot(mx-ex,my-ey) if None not in (ex,ey,mx,my) else None
 native,fwhm=_f(gate.get("native_psf_median_fwhm_px")),_f(src.get("fwhm_geom_px"))
 ratio=fwhm/native if native and fwhm is not None else None; snr=_f(src.get("peak_snr"))
 pointlike=bool(snr is not None and snr>=MIN_SNR and ratio is not None and FWHM_RATIO[0]<=ratio<=FWHM_RATIO[1]
  and off is not None and native is not None and off<=max(3.0,MAX_OFFSET_PSF*native))
 return {"peak_snr":snr,"fwhm_geom_px":fwhm,"native_psf_fwhm_px":native,"fwhm_ratio":ratio,
  "elongation":_f(src.get("elongation")),"offset_px":off,"matched_control_count":ct.get("matched_control_count"),
  "morphology_status":ct.get("morphology_status"),"pointlike_under_v0_1_screen":pointlike}


def classify_candidate(rows,i):
 r=rows[i]; t=_dt(r["date_obs"]); ch=channel(r); src=str(r.get("src_id")); same=[]
 for j,x in enumerate(rows):
  if str(x.get("src_id"))!=src or channel(x)!=ch: continue
  dt=(_dt(x["date_obs"])-t).total_seconds()
  if abs(dt)<=BRACKET_S: same.append((j,dt,x))
 detections=[x for _,_,x in same if candidate(x)]
 before=[(d,x) for _,d,x in same if d<0 and qualified(x)]
 after=[(d,x) for _,d,x in same if d>0 and qualified(x)]
 bef=max(before,key=lambda z:z[0]) if before else None; aft=min(after,key=lambda z:z[0]) if after else None
 meas=measurement(r)
 if len(detections)>=MIN_PERSISTENT: temporal="MULTI_FRAME_COUNTERPART_CANDIDATE"; persistent=True
 elif bef and aft: temporal="BRACKETED_ONE_FRAME_IR_EVENT"; persistent=False
 else: temporal="UNREPLICATED_ONE_FRAME_IR_EVENT"; persistent=False
 scene=("MARGINAL_POINT_LIKE__CONTROLS_INSUFFICIENT" if meas["pointlike_under_v0_1_screen"] and (meas["matched_control_count"] or 0)<8
  else "POINT_LIKE_CANDIDATE" if meas["pointlike_under_v0_1_screen"] else "NON_POINTLIKE_OR_LOW_SNR_EVENT")
 return {"src_id":src,"file_name":r.get("file_name"),"date_obs":r.get("date_obs"),"instrument":r.get("instrument"),
  "filters":r.get("filters"),"measurement":meas,"scene_class":scene,"temporal_class":temporal,
  "persistent_counterpart_supported":persistent,
  "bracket":{"before_delta_s":bef[0] if bef else None,"before_file":bef[1].get("file_name") if bef else None,
   "after_delta_s":aft[0] if aft else None,"after_file":aft[1].get("file_name") if aft else None,
   "span_s":(aft[0]-bef[0]) if bef and aft else None},
  "interpretation":"A single frame may remain an event candidate, but temporal bracketing cannot establish a persistent counterpart."}


def source_summary(receipt,rows,total,parent_q):
 evidence=receipt.get("source_evidence") or {}; recovered=0; cand=[]; unresolved=[]; classes={}
 for src,e in evidence.items():
  q=int(e.get("parent_qualified",0))+int(e.get("new_qualified",0))+int(e.get("edge_recovered",0)); c=int(e.get("counterpart_candidates",0))
  if int(e.get("parent_qualified",0))==0 and int(e.get("new_qualified",0))+int(e.get("edge_recovered",0))>0: recovered+=1
  if c:cand.append(src)
  if not q and not c:unresolved.append(src)
  classes[src]={"qualified_no_counterpart_epochs_minimum":q,"candidate_count":c,
   "class":"QUALIFIED_ABSENCE_WITH_CANDIDATE_EVENT" if q and c else "QUALIFIED_ABSENCE" if q else "CANDIDATE_WITHOUT_QUALIFIED_ABSENCE" if c else "SENSITIVITY_UNRESOLVED"}
 unresolved=sorted(set(unresolved)|set(map(str,receipt.get("unresolved_sources") or [])))
 total=int(total or len({str(r.get('src_id')) for r in rows})); global_q=min(total,int(parent_q or 0)+recovered) if parent_q is not None else max(0,total-len(unresolved))
 return {"sources_total":total,"parent_sources_with_qualified_absence":int(parent_q or 0),
  "newly_recovered_previously_unresolved_sources":recovered,
  "sources_with_at_least_one_qualified_no_counterpart_epoch":global_q,
  "counterpart_candidate_sources":sorted(set(cand)),"fully_sensitivity_unresolved_sources":unresolved,
  "recovery_scope_source_classes":classes}


def analyze_receipt(path,total=None,parent_q=None):
 receipt=json.loads(path.read_text()); rows=list(receipt.get("untested_results") or []); rows.sort(key=lambda r:(str(r.get("src_id")),str(r.get("date_obs")),str(r.get("file_name"))))
 counts={}
 for r in rows: counts[status(r)]=counts.get(status(r),0)+1
 events=[classify_candidate(rows,i) for i,r in enumerate(rows) if candidate(r)]
 src=source_summary(receipt,rows,total,parent_q); persistent=any(x["persistent_counterpart_supported"] for x in events)
 unresolved=bool(src["fully_sensitivity_unresolved_sources"]); allq=src["sources_total"]>0 and src["sources_with_at_least_one_qualified_no_counterpart_epoch"]==src["sources_total"]
 gate=("BLOCKED_PERSISTENT_COUNTERPART_CANDIDATE" if persistent else
  "BLOCKED_SENSITIVITY_UNRESOLVED_AND_ONE_FRAME_EVENT_REQUIRES_ADJUDICATION" if unresolved and events else
  "BLOCKED_SENSITIVITY_UNRESOLVED" if unresolved else "BLOCKED_ONE_FRAME_EVENT_REQUIRES_ADJUDICATION" if events else
  "PASS_ALL_SOURCES_QUALIFIED_NO_PERSISTENT_COUNTERPART" if allq else "BLOCKED_INCOMPLETE_COVERAGE")
 return {"input":{"path_name":path.name,"sha256":sha256_file(path),"bytes":path.stat().st_size,"experiment_id":receipt.get("experiment_id"),
  "parent_qualified_negative_pairs_preserved_untouched":(receipt.get("parent") or {}).get("qualified_negative_pairs_preserved_untouched")},
  "row_accounting":{"rows":len(rows),"status_counts":dict(sorted(counts.items()))},"source_level":src,"candidate_events":events,
  "persistent_counterpart_established":persistent,"all_sources_sensitivity_qualified":allq,"gate_status":gate}


def build_result(receipt,eye_code=None,eye_log=None,yaks_code=None,total=None,parent_q=None):
 astro=analyze_receipt(receipt,total,parent_q)
 return {"schema":SCHEMA,"tool":"Janus_SkayLUCIGate","version":VERSION,"generated_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
  "status":astro["gate_status"],"claim_ceiling":CLAIM_CEILING,
  "design_lineage":{"blind_eye":source_binding(eye_code,"eye"),"blind_eye_log":eye_log_summary(eye_log),"yaks_gate":source_binding(yaks_code,"yaks"),
   "transfer_rule":"Evidence-management semantics only; astronomy classifications use LUCI evidence."},"astronomy":astro,
  "counterfactual_palomar_epoch_scene_model":{"status":"NOT_EXECUTED_IN_V0_1","reason":"Requires calibrated Palomar photometry/bandpass, SED/scenario ensemble, LUCI throughput+atmosphere, PSF and noise; v0.1 refuses to invent them."},
  "security":{"raw_embedded_source_copied_to_result":False,"credentials_or_local_network_values_copied":False,"source_identity":"SHA256_ONLY_PLUS_SAFE_MACROS"}}


def main():
 p=argparse.ArgumentParser(); p.add_argument("--receipt",type=Path,required=True); p.add_argument("--eye-code",type=Path); p.add_argument("--eye-log",type=Path); p.add_argument("--yaks-code",type=Path); p.add_argument("--source-total",type=int); p.add_argument("--parent-qualified-sources",type=int); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
 out=build_result(a.receipt,a.eye_code,a.eye_log,a.yaks_code,a.source_total,a.parent_qualified_sources); a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n")
 print(json.dumps({"status":out["status"],"output":str(a.output),"sha256":sha256_file(a.output)})); return 0 if out["status"].startswith("PASS") else 3
if __name__=="__main__": raise SystemExit(main())
