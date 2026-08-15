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
RCAT_URL='https://www.planet4589.com/space/gcat/tsv/cat/rcat.tsv'
LAUNCH_SHA='88286af94cc1955d741ceaeb30303441d93392abd56f78ac1517c68a9c95737c'
RCAT_SHA='c64e75a3ea3ee5f7969d842590d2ac0ab5a6e9b16648e57ab43778f353c97602'
UA='JANUS-JPFM-4A-GCAT-missing-control-discrepancy/1.0 (+source-only; no-outcome-join)'

CONTROLS=[
 {'id':'ALBERT_IV_V2','date':'1949-12-12','family':'V-2','tokens':['Albert IV','Albert','monkey']},
 {'id':'AEROBEE_PATRICIA_MIKE_MICE','date':'1952-05-22','family':'Aerobee','tokens':['Patricia','Mike','Mildred','Albert','monkey','mice']},
]

def sha256(b:bytes)->str:return hashlib.sha256(b).hexdigest()

def parse_tsv(raw:bytes)->list[dict[str,str]]:
    text=raw.decode('utf-8-sig',errors='replace')
    return [dict(r) for r in csv.DictReader(io.StringIO(text),delimiter='\t') if any(str(v or '').strip() for v in r.values())]

def parse_date(s:str):
    s=(s or '').strip()
    for fmt,pat in [('%Y %b %d',r'^(\d{4}\s+[A-Za-z]{3}\s+\d{1,2})'),('%Y %b %d',r'^(\d{4}\s+[A-Za-z]{3}\s+\d{1,2})')]:
        m=re.match(pat,s)
        if m:
            try:return dt.datetime.strptime(m.group(1),'%Y %b %d').date()
            except ValueError:return None
    return None

def family_match(family:str,row:dict)->bool:
    hay=' '.join(str(row.get(k) or '') for k in ('LV_Type','Variant','Flight','Flight_ID','Name','PLName','Bus','AltNames')).lower()
    if family=='V-2':return 'v-2' in hay or 'v2' in re.sub(r'[^a-z0-9]','',hay) or 'a-4' in hay
    if family=='Aerobee':return 'aerobee' in hay
    return family.lower() in hay

def brief_launch(r:dict)->dict:
    keys=['#Launch_Tag','Launch_Date','LV_Type','Variant','Flight_ID','Flight','Mission','Launch_Site','Launch_Pad','Agency','LaunchCode','FailCode','Category','LTCite','Cite','Notes']
    return {k:(r.get(k) or '').strip() for k in keys}

def brief_rcat(r:dict)->dict:
    keys=['#JCAT','Launch_Tag','Piece','Type','Name','PLName','LDate','SDate','DDate','Owner','Manufacturer','Bus','Apogee','AltNames']
    return {k:(r.get(k) or '').strip() for k in keys}

def row_text(r:dict)->str:return ' '.join(str(v or '') for v in r.values()).lower()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    s=requests.Session();s.headers.update({'User-Agent':UA,'Accept':'text/tab-separated-values,*/*'})
    lr=s.get(LAUNCH_URL,timeout=180);lr.raise_for_status();lb=lr.content
    rr=s.get(RCAT_URL,timeout=180);rr.raise_for_status();rb=rr.content
    if sha256(lb)!=LAUNCH_SHA:raise RuntimeError('launch.tsv changed from frozen schema probe')
    if sha256(rb)!=RCAT_SHA:raise RuntimeError('rcat.tsv changed from frozen schema probe')
    launches=parse_tsv(lb);rcat=parse_tsv(rb)
    launch_dates=[]
    for r in launches:
        d=parse_date(r.get('Launch_Date',''))
        if d:launch_dates.append((d,r))
    rcat_dates=[]
    for r in rcat:
        d=parse_date(r.get('LDate',''))
        if d:rcat_dates.append((d,r))
    results=[]
    for c in CONTROLS:
        target=dt.date.fromisoformat(c['date'])
        exact=[r for d,r in launch_dates if d==target]
        near7=[r for d,r in launch_dates if abs((d-target).days)<=7 and family_match(c['family'],r)]
        near30=[r for d,r in launch_dates if abs((d-target).days)<=30 and family_match(c['family'],r)]
        rexact=[r for d,r in rcat_dates if d==target]
        rnear30=[r for d,r in rcat_dates if abs((d-target).days)<=30 and family_match(c['family'],r)]
        token_launch={}
        token_rcat={}
        for token in c['tokens']:
            q=token.lower()
            token_launch[token]=[brief_launch(r) for r in launches if q in row_text(r)][:20]
            token_rcat[token]=[brief_rcat(r) for r in rcat if q in row_text(r)][:20]
        results.append({
          'control_id':c['id'],'official_date':c['date'],'vehicle_family':c['family'],
          'launch_exact_date_rows':[brief_launch(r) for r in exact[:50]],
          'launch_family_rows_within_7d':[brief_launch(r) for r in near7[:50]],
          'launch_family_rows_within_30d':[brief_launch(r) for r in near30[:100]],
          'rcat_exact_ldate_rows':[brief_rcat(r) for r in rexact[:50]],
          'rcat_family_rows_within_30d':[brief_rcat(r) for r in rnear30[:100]],
          'token_matches_launch':token_launch,'token_matches_rcat':token_rcat,
          'diagnostic_counts':{
            'launch_exact_date_rows':len(exact),'launch_family_within_7d':len(near7),'launch_family_within_30d':len(near30),
            'rcat_exact_ldate_rows':len(rexact),'rcat_family_within_30d':len(rnear30),
            'token_match_rows_launch':{k:len(v) for k,v in token_launch.items()},
            'token_match_rows_rcat':{k:len(v) for k,v in token_rcat.items()}
          }
        })
    result={
      'artifact_id':'JANUS-PALOMAR-JPFM-4A-GCAT-MISSING-OFFICIAL-CONTROL-DISCREPANCY-v1.0',
      'experiment_id':'JPFM-4A','date':dt.date.today().isoformat(),
      'status':'SOURCE_DISCREPANCY_AUDIT_EXECUTED__GCAT_4_OF_6_GATE_REMAINS_FAILED',
      'bindings':{'launch_url':LAUNCH_URL,'launch_sha256':LAUNCH_SHA,'rcat_url':RCAT_URL,'rcat_sha256':RCAT_SHA,'crossvalidation':'data/JANUS-PALOMAR-JPFM-4A-GCAT-OFFICIAL-POSITIVE-EVENT-CROSSVALIDATION-v1.0.json'},
      'official_control_reverification':{
        'authority':'NASA primary public history source reverified independently after GCAT gate failure',
        'albert_iv':'1949-12-12 White Sands V-2',
        'patricia_mike':'1952-05-22 Holloman Aerobee',
        'rule':'This audit does not alter the pre-frozen official control dates or the required 6/6 cross-validation gate.'
      },
      'controls':results,
      'admission':{
        'gcat_as_complete_or_replacement_manifest':'REJECTED_BY_PRE_FROZEN_6_OF_6_GATE',
        'gcat_as_partial_independent_curated_locator':'REMAINS_POSSIBLE_WITH_EXPLICIT_PARTIAL_LABEL',
        'posthoc_rescue_of_6_of_6_gate':False,
        'negative_day_semantics':False
      },
      'outcome_blindness':{'bluebook_access':False,'poss1_access':False,'nuclear_calendar_access':False,'association_computed':False},
      'current_authority_changed':False,
      'claim_ceiling':'SOURCE_DISCREPANCY_LOCALIZATION_ONLY__NO_GCAT_COMPLETENESS_AND_NO_HUMAN_MADE_ASSOCIATION_CLAIM'
    }
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True),encoding='utf-8');print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
