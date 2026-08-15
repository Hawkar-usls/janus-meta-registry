#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import requests

NASA_URL='https://ntrs.nasa.gov/citations/19720015241'
CIA_AUTHORITY_URL='https://www.cia.gov/readingroom/document/cia-rdp88b00831r000100210004-6'
CIA_TRANSPORT_URL='https://www.cia.gov/readingroom/print/1450291'
UA='JANUS-JPFM-4A-human-made-source-freezer/1.2'


def sha256(b:bytes)->str:return hashlib.sha256(b).hexdigest()

def normalize_text(html:str)->str:
    x=re.sub(r'<script\b[^>]*>.*?</script>',' ',html,flags=re.I|re.S)
    x=re.sub(r'<style\b[^>]*>.*?</style>',' ',x,flags=re.I|re.S)
    x=re.sub(r'<[^>]+>',' ',x)
    return re.sub(r'\s+',' ',x).strip()

def fetch(session,url):
    r=session.get(url,timeout=180,allow_redirects=True);r.raise_for_status();b=r.content
    text=normalize_text(b.decode(r.encoding or 'utf-8',errors='replace'))
    return {'fetch_status':'FETCHED','url':url,'final_url':r.url,'http_status':r.status_code,'sha256':sha256(b),'bytes':len(b),'normalized_text_sha256':sha256(text.encode()),'normalized_text_chars':len(text),'text':text}

def fetch_fail_closed(session,url):
    try:return fetch(session,url)
    except requests.TooManyRedirects as e:
        return {'fetch_status':'REMOTE_BYTE_FREEZE_BLOCKED_REDIRECT_LOOP','url':url,'error_class':type(e).__name__,'sha256':None,'bytes':None,'text':''}
    except Exception as e:
        return {'fetch_status':'REMOTE_BYTE_FREEZE_BLOCKED','url':url,'error_class':type(e).__name__,'error':str(e)[:500],'sha256':None,'bytes':None,'text':''}

def marker(source,pat):return bool(re.search(pat,source.get('text',''),flags=re.I))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    s=requests.Session();s.headers.update({'User-Agent':UA,'Accept':'text/html,application/xhtml+xml'})
    nasa=fetch_fail_closed(s,NASA_URL);cia=fetch_fail_closed(s,CIA_TRANSPORT_URL)
    nasa_gates={
      'document_id_19720015241':marker(nasa,r'19720015241'),
      'report_nasa_tm_x_68822':marker(nasa,r'NASA[- ]TM[- ]X[- ]68822'),
      'scientifically_successful_selection':marker(nasa,r'scientifically successful rockets'),
      'starts_1947_03_07':marker(nasa,r'7 March 1947'),
      'ends_1971_12_31':marker(nasa,r'31 December 1971')
    }
    if nasa.get('fetch_status')!='FETCHED' or not all(nasa_gates.values()):
        raise RuntimeError('NASA source byte/marker gate failed '+repr({'status':nasa.get('fetch_status'),'markers':nasa_gates}))
    cia_gates={
      'document_number':marker(cia,r'CIA-RDP88B00831R000100210004-6'),
      'mission_1956_01_10':marker(cia,r'10 January 1956'),
      'eight_effective_first_day':marker(cia,r'Eight effective balloons'),
      'daily_launch_policy':marker(cia,r'balloons were launched dail'),
      'resume_1956_02_03':marker(cia,r'resumed on 3 February'),
      'statistics_cutoff_1956_03_05':marker(cia,r'cut-off date of 5 March 1956')
    }
    cia_fetch_ok=cia.get('fetch_status')=='FETCHED' and all(cia_gates.values())
    cia_blocked=cia.get('fetch_status') in {'REMOTE_BYTE_FREEZE_BLOCKED_REDIRECT_LOOP','REMOTE_BYTE_FREEZE_BLOCKED'}
    if not (cia_fetch_ok or cia_blocked):raise RuntimeError('CIA source state unexpected '+repr({'status':cia.get('fetch_status'),'markers':cia_gates}))
    result={
      'artifact_id':'JANUS-PALOMAR-JPFM-4A-HUMAN-MADE-SKY-SOURCE-FREEZE-v1.0',
      'status':'PARTIAL_PUBLIC_AUTHORITY_SOURCE_FREEZE__NASA_BYTES_FROZEN__CIA_REMOTE_BYTES_FAIL_CLOSED__NO_OUTCOME_JOIN',
      'sources':{
        'NASA_WDC_A_SOUNDING_ROCKET_CATALOGUE':{k:v for k,v in nasa.items() if k!='text'},
        'CIA_SAC_HISTORICAL_STUDY_62_VOL2':{
          **{k:v for k,v in cia.items() if k!='text'},
          'authority_record_url':CIA_AUTHORITY_URL,
          'transport_url_attempted':CIA_TRANSPORT_URL,
          'authority_semantics_binding':'See preregistered 4A acquisition gate; this source-freeze artifact does not pretend to have a CIA byte hash when the remote endpoint redirects indefinitely.'
        }
      },
      'authority_marker_gates':{'nasa':nasa_gates,'cia_remote_if_fetched':cia_gates},
      'population_semantics':{
        'rocket':'POSITIVE_EVENT_ONLY__SCIENTIFICALLY_SUCCESSFUL_SELECTION__NO_NEGATIVE_DATES',
        'balloon':'OPERATIONAL_OPPORTUNITY_TEXT_PRESENT_IN_AUTHORITY_RECORD__DAILY_ROW_COUNTS_PENDING'
      },
      'remote_freeze_disposition':{
        'nasa':'PASS_BYTE_AND_MARKER_FREEZE',
        'cia':'PASS_FAIL_CLOSED_REMOTE_BLOCK_RECORD' if cia_blocked else 'PASS_BYTE_AND_MARKER_FREEZE',
        'cia_byte_hash_admitted':bool(cia_fetch_ok)
      },
      'pdf_policy':{'pdfs_parsed':False,'note':'No unseen PDF content is inferred by this artifact.'},
      'outcome_blindness':{'bluebook_access':False,'poss1_access':False,'nuclear_calendar_access':False,'association_computed':False},
      'next_gate':'Acquire row-level launch/event manifests and explicit completeness/opportunity. CIA daily launch data remains blocked until source bytes or another official companion manifest can be frozen.',
      'claim_ceiling':'PARTIAL_SOURCE_FREEZE_ONLY__NO_HUMAN_MADE_EVENT_ASSOCIATION_CLAIM'
    }
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps(result,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
