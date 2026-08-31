#!/usr/bin/env python3
"""Passive raw OONI endpoint-matrix harvest for MegaCom/AS50223 TikTok blocking.

Purpose: avoid projecting a country-level majority mechanism onto one ASN/endpoint.
This script queries public OONI measurements only; it sends no probes to MegaCom or TikTok.
"""
from __future__ import annotations
import hashlib, json, os, re, time, urllib.parse, urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

API="https://api.ooni.io/api/v1"
UA="janus-megacom-endpoint-matrix/1.0 (+passive-open-data-research)"
OUT=Path(os.environ.get("MEGACOM_MATRIX_OUT","megacom-tiktok-endpoint-matrix"))
PER_DOMAIN=int(os.environ.get("PER_DOMAIN","8"))
DELAY=float(os.environ.get("OONI_REQUEST_DELAY","0.35"))
DOMAINS=[
 "www.tiktok.com","m.tiktok.com","tiktok.com","tiktokv.com",
 "api.tiktokv.com","api-h2.tiktokv.com","api21-h2.tiktokv.com",
 "ib.tiktokv.com","tiktokcdn.com","v16.tiktokcdn.com","v19.tiktokcdn.com"
]
BASE_QUERY={
 "probe_cc":"KG","probe_asn":"AS50223","test_name":"web_connectivity",
 "since":"2024-04-18T00:00:00","until":"2024-04-30T23:59:59",
 "limit":"100","order":"asc"
}

def get(url:str):
 req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
 with urllib.request.urlopen(req,timeout=45) as r: b=r.read()
 time.sleep(DELAY)
 return json.loads(b),b

def listm(domain:str):
 q=dict(BASE_QUERY); q["domain"]=domain
 o,_=get(API+"/measurements?"+urllib.parse.urlencode(q))
 return o.get("results",[])

def classify(raw:dict[str,Any])->dict[str,Any]:
 tk=raw.get("test_keys") or {}
 qs=tk.get("queries") or []
 dns_fail=[q.get("failure") for q in qs if q.get("failure")]
 tcp=tk.get("tcp_connect") or []
 tls=tk.get("tls_handshakes") or []
 events=tk.get("network_events") or []
 tls_fail=[h.get("failure") for h in tls if h.get("failure")]
 ev_fail=[(e.get("operation"),e.get("failure"),e.get("t")) for e in events if e.get("failure")]
 writes=[(e.get("num_bytes"),e.get("t")) for e in events if e.get("operation")=="write"]
 seq=[]
 for e in events:
  op=e.get("operation")
  if op in {"connect","tls_handshake_start","write","read","tls_handshake_done"}:
   seq.append({k:e.get(k) for k in ("operation","failure","t","num_bytes","address","proto") if k in e})
 return {
  "measurement_start_time":raw.get("measurement_start_time"),
  "measurement_uid":raw.get("measurement_uid"),
  "input":raw.get("input"),
  "test_version":raw.get("test_version"),
  "blocking":tk.get("blocking"),"accessible":tk.get("accessible"),
  "dns_experiment_failure":tk.get("dns_experiment_failure"),
  "dns_failures":dns_fail,
  "tcp_attempts":len(tcp),
  "tcp_successes":sum(1 for x in tcp if (x.get("status") or {}).get("success") is True),
  "tls_handshakes":len(tls),
  "tls_failures":tls_fail,
  "event_failures":ev_fail,
  "writes":writes,
  "event_sequence":seq[:100],
  "control_dns":((tk.get("control") or {}).get("dns")),
 }

def main():
 (OUT/"raw").mkdir(parents=True,exist_ok=True)
 matrix={"schema":"hawkar.tspu.megacom_tiktok_endpoint_matrix.v1","passive_only":True,
         "probe_asn":"AS50223","period":"2024-04-18..2024-04-30","domains":{},
         "interpretation_rule":"Only endpoints with direct raw TCP/TLS evidence may contribute to a TLS fingerprint; DNS-only failures are a different mechanism."}
 for dom in DOMAINS:
  try: metas=listm(dom)
  except Exception as e:
   matrix["domains"][dom]={"list_error":repr(e)}; continue
  # unique URLs, bounded sample
  uniq={m.get("measurement_url") or str(i):m for i,m in enumerate(metas)}
  metas=list(uniq.values())[:PER_DOMAIN]
  rows=[]; rdir=OUT/"raw"/re.sub(r"[^A-Za-z0-9_.-]","_",dom); rdir.mkdir(parents=True,exist_ok=True)
  for i,m in enumerate(metas):
   u=m.get("measurement_url")
   if not u: continue
   try:
    raw,b=get(u); rid=raw.get("measurement_uid") or raw.get("report_id") or str(i)
    fn=re.sub(r"[^A-Za-z0-9_.-]","_",str(rid))[:180]+".json"
    (rdir/fn).write_bytes(b)
    row=classify(raw); row["raw_sha256"]=hashlib.sha256(b).hexdigest(); rows.append(row)
   except Exception as e: rows.append({"measurement_url":u,"fetch_error":repr(e)})
  dns=Counter(); tls=Counter(); block=Counter(); seqtypes=Counter()
  for r in rows:
   if r.get("fetch_error"): continue
   if r.get("dns_experiment_failure"): dns[str(r["dns_experiment_failure"])]+=1
   for x in r.get("tls_failures",[]): tls[str(x)]+=1
   block[str(r.get("blocking"))]+=1
   if r.get("tls_handshakes",0)>0: seqtypes["REACHED_TLS"]+=1
   elif r.get("tcp_attempts",0)>0: seqtypes["REACHED_TCP_NOT_TLS"]+=1
   else: seqtypes["NO_TCP_TLS"]+=1
  matrix["domains"][dom]={
   "listed":len(uniq),"raw_fetched":sum(1 for r in rows if not r.get("fetch_error")),
   "dns_failure_counts":dns.most_common(),"tls_failure_counts":tls.most_common(),
   "blocking_counts":block.most_common(),"stage_counts":seqtypes.most_common(),"measurements":rows
  }
 (OUT/"MEGACOM-TIKTOK-ENDPOINT-MATRIX.json").write_text(json.dumps(matrix,indent=2,ensure_ascii=False)+"\n")
 print(json.dumps({d:{k:v for k,v in x.items() if k!="measurements"} for d,x in matrix["domains"].items()},indent=2,ensure_ascii=False))
if __name__=="__main__": main()
