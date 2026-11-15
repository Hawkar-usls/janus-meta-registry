#!/usr/bin/env python3
"""Observed 24h cross-repository Sentinel schedule delivery witness.

Real GitHub Actions schedule runs only; never infer uptime from cron YAML,
workflow_dispatch, push, PR, a healthy GitHub API, or a successful self-test.
"""
from __future__ import annotations
import argparse,hashlib,json,os,urllib.request,urllib.error
from datetime import datetime,timedelta,timezone
from pathlib import Path

SCHEMA="janus.sentinel.crossrepo_cron24h/1.0"
WORKFLOW="janus-sentinel-mesh.yml"
DEPLOYED={
    "Hawkar-usls/Janus-Demiurge":"2026-11-15T15:20:15Z",
    "Hawkar-usls/Janus_Genesis":"2026-11-15T15:20:21Z",
    "Hawkar-usls/janus-meta-registry":"2026-11-15T15:20:26Z",
}
WINDOW=timedelta(hours=24)
EXPECTED=96 # four 15-minute slots per hour
MIN_SUCCESSES=77
MAX_GAP_SECONDS=45*60
PER_PAGE=100
MAX_PAGES=4

def require(ok,reason):
    if not ok:raise ValueError(reason)
def parse(s):
    require(type(s) is str and len(s)<50,"BAD_TIME")
    v=datetime.fromisoformat(s.replace("Z","+00:00"))
    require(v.tzinfo is not None,"NAIVE_TIME")
    return v.astimezone(timezone.utc)
def iso(t):
    return t.astimezone(timezone.utc).isoformat().replace("+00:00","Z")
def digest(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),
      ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def read_runs(repo,token,opener=urllib.request.urlopen):
    require(repo in DEPLOYED and type(token) is str and 16<len(token)<4096,
            "INVALID_READ_AUTHORITY")
    all_runs=[];complete=False
    for page in range(1,MAX_PAGES+1):
        url=("https://api.github.com/repos/"+repo+
             "/actions/workflows/"+WORKFLOW+
             f"/runs?per_page={PER_PAGE}&page={page}")
        req=urllib.request.Request(url,headers={
            "Authorization":"Bearer "+token,
            "Accept":"application/vnd.github+json",
            "User-Agent":"JANUS-Cron24h-Witness/1.0"})
        with opener(req,timeout=15) as rsp:
            require(rsp.status==200,"ACTIONS_INVENTORY_HTTP_ERROR")
            raw=rsp.read(500001)
        require(len(raw)<=500000,"INVENTORY_OVERSIZED")
        result=json.loads(raw)
        require(type(result) is dict and type(result.get("workflow_runs")) is list,
                "INVALID_ACTIONS_RUN_ARRAY")
        rows=result["workflow_runs"]
        require(len(rows)<=PER_PAGE,"PAGE_OVERFLOW")
        all_runs.extend(rows)
        if len(rows)<PER_PAGE:
            complete=True
            break
    require(len(all_runs)<=MAX_PAGES*PER_PAGE,"HISTORY_OVERFLOW")
    return all_runs,complete

def judge(repo,rows,now,*,page_complete=True):
    require(repo in DEPLOYED and now.tzinfo is not None and
            type(rows) is list and len(rows)<=MAX_PAGES*PER_PAGE,
            "INVALID_WINDOW_ARGUMENT")
    start=now-WINDOW
    if start<parse(DEPLOYED[repo]):
        return {"status":"HOLD_24H_NOT_ELAPSED_SINCE_DEPLOY",
                "hours_since_deploy":round((now-parse(DEPLOYED[repo])).total_seconds()/3600,2),
                "expected":EXPECTED,"observed_success":0,
                "no_uptime_proof":True}
    seen=set();sched=[];oldest=None
    for r in rows:
        require(type(r) is dict and type(r.get("id")) is int
                and r["id"]>0 and r["id"] not in seen
                and r.get("event") in
                     ("push","pull_request","schedule","workflow_dispatch","workflow_run")
                and type(r.get("created_at")) is str
                and r.get("status") in ("completed","queued","in_progress","waiting","pending","requested")
                and r.get("conclusion") in
                    (None,"success","failure","cancelled","timed_out","skipped","neutral"),
                "INVALID_ACTIONS_HISTORY")
        seen.add(r["id"])
        dt=parse(r["created_at"])
        require(dt<=now+timedelta(minutes=1),"FUTURE_RUN_CLOCK")
        oldest=dt if oldest is None else min(oldest,dt)
        if (r["event"]=="schedule" and r.get("head_branch")=="main"
                and start<=dt<=now):
            sched.append((dt,r))
    # If the page collection is saturated and we cannot see the start of the
    # 24-hour period, never mistake missing history for complete coverage.
    if not page_complete and (oldest is None or oldest>=start):
        return {"status":"HOLD_INCOMPLETE_GITHUB_HISTORY",
                "expected":EXPECTED,"observed_success":0,
                "no_uptime_proof":True}
    success=sorted(dt for dt,r in sched if r["status"]=="completed"
                   and r["conclusion"]=="success")
    failures=[r["id"] for dt,r in sched
              if r["status"]=="completed" and r["conclusion"]!="success"]
    boundaries=[start]+success+[now]
    worst=max((b-a).total_seconds() for a,b in zip(boundaries,boundaries[1:]))
    healthy=(len(success)>=MIN_SUCCESSES
             and worst<=MAX_GAP_SECONDS and not failures)
    return {"status":("PASS_OBSERVED_24H_SCHEDULE_DELIVERY"
                      if healthy else "HOLD_24H_DELIVERY_OR_RELIABILITY"),
            "window_start":iso(start),"window_end":iso(now),
            "expected":EXPECTED,"observed_schedule":len(sched),
            "observed_success":len(success),"failed_run_ids":failures[:20],
            "max_success_gap_seconds":round(worst,1),
            "threshold_min_success":MIN_SUCCESSES,
            "threshold_max_gap_seconds":MAX_GAP_SECONDS,
            "no_uptime_proof":not healthy,
            "github_outage_resilience_proven":False}

def evaluate(token,*,now=None,fetch=read_runs):
    now=now or datetime.now(timezone.utc)
    reports={}
    for repo in DEPLOYED:
        try:
            rows,complete=fetch(repo,token)
            reports[repo]=judge(repo,rows,now,page_complete=complete)
        except (ValueError,KeyError,TypeError,urllib.error.URLError,
                TimeoutError,OSError,json.JSONDecodeError) as err:
            reports[repo]={"status":"HOLD_SOURCE_OR_HISTORY_UNAVAILABLE",
                           "error_type":type(err).__name__,
                           "no_uptime_proof":True}
    good=all(r["status"]=="PASS_OBSERVED_24H_SCHEDULE_DELIVERY"
             for r in reports.values())
    report={"schema":SCHEMA,"observed_utc":iso(now),
            "status":("PASS_ALL_THREE_OBSERVED_24H_SCHEDULES" if good
                      else "HOLD_NOT_ALL_THREE_VERIFIED"),
            "repos":reports,"production_authority":False,
            "remote_code_executed":False,
            "crossrepo_recovery_proven":False,
            "github_wide_outage_survivable":False}
    return dict(report,receipt_sha256=digest(report))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    out=Path(a.out)
    require(not out.exists() and not out.is_symlink(),"NO_OVERWRITE")
    report=evaluate(os.environ.get("GH_READ_TOKEN",""))
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(report["status"],report["receipt_sha256"])
    f=os.environ.get("GITHUB_STEP_SUMMARY")
    if f:
        with open(f,"a") as summary:
            summary.write("### Sentinel three-repository real 24-hour cron audit\n")
            summary.write("Status: "+report["status"]+"\n")
            for repo,x in report["repos"].items():
                summary.write(repo+": "+x["status"]+"; observed successful schedules="+
                              str(x.get("observed_success",0))+"\n")
            summary.write("Cron YAML and push checks never prove schedule delivery.\n")
if __name__=="__main__":
    main()
