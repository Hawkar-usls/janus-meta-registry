#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import requests

FREEZE=Path('data/JANUS-PALOMAR-JPFM-3B-NOAA-EVENT-PATROL-SOURCE-FREEZE-v1.0.json')
START=dt.date(1955,1,1)
END=dt.date(1957,4,28)
UA='JANUS-JPFM-3B-event-patrol-parser/1.0'

def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()

def fetch(s, info):
    r=s.get(info['url'],timeout=180); r.raise_for_status(); b=r.content
    if sha(b)!=info['sha256']: raise RuntimeError('source hash mismatch '+info['url'])
    return b.decode('ascii',errors='replace').splitlines()

def hhmm(x:str):
    x=x.strip()
    if not x:return None
    if not x.isdigit():return None
    v=int(x); h=v//100; m=v%100
    if v==2400:return 1440
    if not(0<=h<=23 and 0<=m<=59):return None
    return h*60+m

def ymd6(s:str)->dt.date|None:
    if len(s)!=6 or not s.isdigit():return None
    try:return dt.date(1900+int(s[:2]),int(s[2:4]),int(s[4:6]))
    except ValueError:return None

def union_minutes(intervals):
    if not intervals:return 0
    xs=sorted((max(0,a),min(1440,b)) for a,b in intervals if b>a)
    if not xs:return 0
    total=0; a,b=xs[0]
    for c,d in xs[1:]:
        if c<=b:b=max(b,d)
        else: total+=b-a; a,b=c,d
    total+=b-a
    return total

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',type=Path,required=True); a=ap.parse_args()
    fb=FREEZE.read_bytes(); freeze=json.loads(fb); s=requests.Session();s.headers['User-Agent']=UA
    event_rows=[]; event_short=[]; event_invalid=[]
    for y in freeze['event_archive']['years']:
        lines=fetch(s,y['files'][0])
        for line in lines:
            if len(line)==88:
                # Legacy event file detailed row: stable source structure observed for 1955-57.
                # Only date and first onset field are admitted here; severity/position remain unparsed.
                date=ymd6(line[10:16]); onset=hhmm(line[16:20]); qualifier=line[20:21]
                if date is None or date.year!=y['year']:
                    event_invalid.append({'year':y['year'],'raw_sha256':sha(line.encode()),'date_slice':line[10:16]});continue
                event_rows.append({'date':date,'onset_minute_utc':onset,'onset_qualifier':qualifier.strip() or None,'raw_sha256':sha(line.encode())})
            elif len(line)==27:
                event_short.append({'year':y['year'],'raw_sha256':sha(line.encode()),'raw':line})
            else:
                event_invalid.append({'year':y['year'],'raw_sha256':sha(line.encode()),'reason':'unexpected_length','length':len(line)})
    if event_invalid:
        raise RuntimeError('event detailed-row parser gate failed: '+repr(event_invalid[:5]))

    by_day=Counter(r['date'] for r in event_rows)
    patrol_by_day=defaultdict(list); patrol_rows=0; patrol_bad=[]; station_days=defaultdict(set)
    for y in freeze['patrol_archive']['years']:
        lines=fetch(s,y['files'][0])
        for line in lines:
            if len(line)!=80 or line[:2]!='13':
                patrol_bad.append({'year':y['year'],'sha256':sha(line.encode()),'prefix':line[:2],'length':len(line)});continue
            date=ymd6(line[6:12]); station=line[76:80].strip(); patrol_rows+=1
            if date is None or date.year!=y['year']:
                patrol_bad.append({'year':y['year'],'sha256':sha(line.encode()),'date_slice':line[6:12]});continue
            station_days[date].add(station)
            for i in range(8):
                st=hhmm(line[12+8*i:16+8*i]); en=hhmm(line[16+8*i:20+8*i])
                if st is None or en is None: continue
                if en>=st:
                    patrol_by_day[date].append((st,en))
                else:
                    patrol_by_day[date].append((st,1440))
                    patrol_by_day[date+dt.timedelta(days=1)].append((0,en))
    if patrol_bad:
        raise RuntimeError('patrol parser gate failed: '+repr(patrol_bad[:5]))

    days=[]; d=START
    while d<=END:
        cov=union_minutes(patrol_by_day.get(d,[])); n=by_day.get(d,0)
        days.append({'date':d.isoformat(),'coverage_minutes_union_utc':cov,'coverage_fraction':cov/1440.0,'stations_reporting_patrol':len(station_days.get(d,set())),'flare_event_records':n,'any_flare_event':int(n>0)})
        d+=dt.timedelta(days=1)
    thresholds=[0,180,360,720,1080,1200,1320,1380,1440]
    coverage_summary={}
    for t in thresholds:
        eligible=[x for x in days if x['coverage_minutes_union_utc']>=t]
        coverage_summary[str(t)]={
          'eligible_days':len(eligible),
          'eligible_fraction':len(eligible)/len(days),
          'event_days':sum(x['any_flare_event'] for x in eligible),
          'event_records':sum(x['flare_event_records'] for x in eligible)
        }
    result={
      'artifact_id':'JANUS-PALOMAR-JPFM-3B-NOAA-EVENT-PATROL-PARSER-RUN-001',
      'status':'SOURCE_ONLY_EVENT_DATE_AND_PATROL_COVERAGE_PARSED__NO_EXTERNAL_OUTCOME_JOIN',
      'source_freeze':str(FREEZE),'source_freeze_sha256':sha(fb),
      'inference_candidate_window':[START.isoformat(),END.isoformat()],
      'event_parser':{
        'detailed_record_length':88,'date_slice_zero_based':'[10:16] YYMMDD','onset_slice_zero_based':'[16:20] HHMM',
        'detailed_records_all_1955_1957':len(event_rows),'unique_event_dates_all_1955_1957':len(by_day),
        'short_27_records_not_used_as_physical_events':len(event_short),
        'severity_position_not_parsed_in_v1':True
      },
      'patrol_parser':{
        'official_data_code':'13','record_length':80,'rows_all_1955_1957':patrol_rows,
        'up_to_8_start_end_pairs':True,'cross_midnight_intervals_split_between_dates':True,
        'daily_opportunity':'union of all station patrol intervals in UTC'
      },
      'coverage_threshold_diagnostics_source_only':coverage_summary,
      'study_days':days,
      'outcome_blindness':{'bluebook_access':False,'poss1_access':False,'nuclear_calendar_access':False,'association_computed':False},
      'next_gate':'Freeze a primary minimum daily patrol coverage threshold and sensitivity thresholds using only this source-only coverage distribution; then preregister JPFM-3C before joining Blue Book/POSS-I.',
      'claim_ceiling':'SOLAR_EVENT_DATE_AND_PATROL_OPPORTUNITY_ONLY__NO_STARLIKE_OR_POSS_ASSOCIATION_CLAIM'
    }
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps(result,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
