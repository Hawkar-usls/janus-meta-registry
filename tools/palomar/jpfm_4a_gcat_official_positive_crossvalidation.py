#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import re
from pathlib import Path

import requests

LAUNCH_URL='https://www.planet4589.com/space/gcat/tsv/launch/launch.tsv'
SITES_URL='https://www.planet4589.com/space/gcat/tsv/tables/sites.tsv'
LP_URL='https://www.planet4589.com/space/gcat/tsv/tables/lp.tsv'
FROZEN_LAUNCH_SHA='88286af94cc1955d741ceaeb30303441d93392abd56f78ac1517c68a9c95737c'
BUMPER=Path('data/JANUS-PALOMAR-JPFM-4A-BUMPER-FINAL-CAPE-PHASE-MANIFEST-v1.0.json')
BIOMED=Path('data/JANUS-PALOMAR-JPFM-4A-US-BIOMEDICAL-ROCKET-POSITIVE-EVENT-MANIFEST-v1.0.json')
START=dt.date(1949,11,19); END=dt.date(1957,4,28)
UA='JANUS-JPFM-4A-GCAT-official-positive-crossvalidation/1.0 (+source-only; no-outcome-join)'

def sha256(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def norm(s:str)->str:return re.sub(r'[^a-z0-9]+','',s.lower())

def fetch(s,url):
    r=s.get(url,timeout=180,allow_redirects=True);r.raise_for_status();return r,r.content

def parse_tsv(raw:bytes):
    lines=raw.decode('utf-8-sig',errors='replace').splitlines()
    if not lines or '\t' not in lines[0]:raise RuntimeError('TSV header missing')
    reader=csv.DictReader(io.StringIO('\n'.join(lines)),delimiter='\t')
    return [dict(r) for r in reader if any(str(v or '').strip() for v in r.values())]

def parse_launch_date(s:str):
    s=(s or '').strip()
    m=re.match(r'^(\d{4})\s+([A-Za-z]{3})\s+(\d{1,2})(?:\s|$)',s)
    if not m:return None
    try:return dt.datetime.strptime(f'{m.group(1)} {m.group(2)} {int(m.group(3)):02d}','%Y %b %d').date()
    except ValueError:return None

def expected_events():
    b=json.loads(BUMPER.read_text());m=json.loads(BIOMED.read_text());out=[]
    for e in b['events']:
        if e['status']=='LAUNCHED':
            out.append({'source':'BUMPER_OFFICIAL_MANIFEST','event_id':e['round'].replace(' ','_'),'date':e['date'],'vehicle_expected':'Bumper','location_expected':e.get('location') or b.get('campaign_scope',{}).get('location')})
    for e in m['events']:
        if e['status'].startswith('LAUNCHED'):
            out.append({'source':'NASA_BIOMEDICAL_OFFICIAL_MANIFEST','event_id':e['event_id'],'date':e['date'],'vehicle_expected':e['vehicle'],'location_expected':e['location']})
    return out

def vehicle_ok(expected:str,got:str):
    e=norm(expected);g=norm(got)
    if e=='v2':return 'v2' in g or 'a4' in g
    if e.startswith('aerobee'):return 'aerobee' in g
    if e.startswith('bumper'):return 'bumper' in g
    return e in g or g in e

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    s=requests.Session();s.headers.update({'User-Agent':UA,'Accept':'text/tab-separated-values,*/*'})
    lr,lb=fetch(s,LAUNCH_URL);sr,sb=fetch(s,SITES_URL);pr,pb=fetch(s,LP_URL)
    if sha256(lb)!=FROZEN_LAUNCH_SHA:raise RuntimeError('GCAT launch.tsv changed after source freeze')
    launches=parse_tsv(lb);sites=parse_tsv(sb);lps=parse_tsv(pb)
    by_date={}
    study=[]
    for row in launches:
        tag=(row.get('#Launch_Tag') or '').strip()
        if tag.startswith('#'):continue
        d=parse_launch_date(row.get('Launch_Date',''))
        if d:
            by_date.setdefault(d.isoformat(),[]).append(row)
            if START<=d<=END:study.append(row)
    controls=[]
    for exp in expected_events():
        rows=by_date.get(exp['date'],[])
        matches=[r for r in rows if vehicle_ok(exp['vehicle_expected'],r.get('LV_Type',''))]
        controls.append({
          **exp,
          'gcat_exact_date_rows':len(rows),
          'gcat_vehicle_family_matches':len(matches),
          'matched':bool(matches),
          'matching_rows':[{k:(r.get(k) or '').strip() for k in ['#Launch_Tag','Launch_Date','LV_Type','Variant','Flight_ID','Flight','Mission','Launch_Site','Launch_Pad','Agency','LaunchCode','FailCode','Category','LTCite','Cite','Notes']} for r in matches[:10]],
          'all_date_rows_brief':[{k:(r.get(k) or '').strip() for k in ['#Launch_Tag','Launch_Date','LV_Type','Launch_Site','Agency','LaunchCode','FailCode','LTCite']} for r in rows[:20]]
        })
    passed=sum(c['matched'] for c in controls);total=len(controls)
    result={
      'artifact_id':'JANUS-PALOMAR-JPFM-4A-GCAT-OFFICIAL-POSITIVE-EVENT-CROSSVALIDATION-v1.0',
      'experiment_id':'JPFM-4A','date':dt.date.today().isoformat(),
      'status':'GCAT_INDEPENDENT_CURATED_DERIVATIVE_CROSSVALIDATED_AGAINST_PREEXISTING_OFFICIAL_POSITIVE_EVENTS' if passed==total else 'GCAT_CROSSVALIDATION_INCOMPLETE_FAIL_CLOSED',
      'epistemic_role':'SOURCE_ONLY_CROSSVALIDATION__NOT_BLUEBOOK_OR_POSS_OUTCOME_ANALYSIS',
      'bindings':{
        'gcat_launch_url':LAUNCH_URL,'gcat_launch_sha256':sha256(lb),'gcat_launch_bytes':len(lb),
        'gcat_sites_url':SITES_URL,'gcat_sites_sha256':sha256(sb),'gcat_sites_bytes':len(sb),
        'gcat_launch_points_url':LP_URL,'gcat_launch_points_sha256':sha256(pb),'gcat_launch_points_bytes':len(pb),
        'bumper_manifest_path':str(BUMPER),'bumper_manifest_sha256':sha256(BUMPER.read_bytes()),
        'biomedical_manifest_path':str(BIOMED),'biomedical_manifest_sha256':sha256(BIOMED.read_bytes())
      },
      'schema_counts':{'launch_rows_total':len(launches),'site_rows_total':len(sites),'launch_point_rows_total':len(lps),'launch_rows_with_parseable_date_in_study_window':len(study)},
      'preexisting_official_controls':controls,
      'validation':{'controls_total':total,'controls_matched_exact_date_and_vehicle_family':passed,'all_controls_pass':passed==total,'scrub_control_policy':'The 1950-07-19 Bumper scrub is intentionally not required because this gate validates launched-event representation, not attempt/scrub completeness.'},
      'population_boundary':{
        'gcat_role':'INDEPENDENT_CURATED_DERIVATIVE_CANDIDATE_SOURCE',
        'nasa_authority_replaced':False,
        'negative_day_semantics_admitted':False,
        'absence_from_gcat_means':'UNKNOWN_FOR_JANUS_UNTIL_COMPLETENESS_SCOPE_IS_FROZEN_AND_VALIDATED',
        'next_gate':'If all controls pass, freeze a study-window GCAT rocket candidate manifest with explicit inclusion/exclusion rules, site resolution, provenance fields and no outcome access before JPFM-4B.'
      },
      'outcome_blindness':{'bluebook_access':False,'poss1_access':False,'nuclear_calendar_access':False,'association_computed':False},
      'current_authority_changed':False,
      'claim_ceiling':'GCAT_DERIVATIVE_SOURCE_CROSSVALIDATION_ONLY__NO_HUMAN_MADE_EVENT_ASSOCIATION_CLAIM'
    }
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True),encoding='utf-8');print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
