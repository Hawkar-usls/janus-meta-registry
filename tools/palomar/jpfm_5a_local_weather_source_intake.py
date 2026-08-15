#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import requests

STATIONS_URL='https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt'
BY_STATION='https://www.ncei.noaa.gov/pub/data/ghcn/daily/by_station/{station}.csv.gz'
START=pd.Timestamp('1949-11-19');END=pd.Timestamp('1957-04-28')
PAL_LAT=33.3566666667;PAL_LON=-116.8625
UA='JANUS-JPFM-5A-weather-intake/1.0'


def sha(b):return hashlib.sha256(b).hexdigest()
def hav(lat1,lon1,lat2,lon2):
    r=6371.0;a,b,c,d=map(math.radians,[lat1,lon1,lat2,lon2]);q=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 2*r*math.asin(math.sqrt(q))

def parse_inventory(text):
    rows=[]
    for line in text.splitlines():
        if len(line)<71:continue
        try:
            rows.append({'station_id':line[0:11].strip(),'lat':float(line[12:20]),'lon':float(line[21:30]),'elev_m':float(line[31:37]),
                         'state':line[38:40].strip(),'name':line[41:71].strip(),'gsn':line[72:75].strip() if len(line)>=75 else '',
                         'hcn_crn':line[76:79].strip() if len(line)>=79 else '', 'wmo':line[80:85].strip() if len(line)>=85 else ''})
        except Exception:continue
    return rows

def station_candidates(rows):
    c=[r for r in rows if 'PALOMAR' in r['name'].upper()]
    for r in c:r['distance_to_palomar_km']=hav(PAL_LAT,PAL_LON,r['lat'],r['lon'])
    return sorted(c,key=lambda x:x['distance_to_palomar_km'])

def read_station_csv(b):
    raw=gzip.decompress(b)
    cols=['station_id','date','element','value','mflag','qflag','sflag','obs_time']
    d=pd.read_csv(io.BytesIO(raw),header=None,names=cols,dtype=str)
    d['date_dt']=pd.to_datetime(d.date,format='%Y%m%d',errors='coerce')
    d['value_num']=pd.to_numeric(d.value,errors='coerce')
    return d,raw

def coverage(d):
    w=d[(d.date_dt>=START)&(d.date_dt<=END)].copy()
    expected=(END-START).days+1
    out={}
    for el,g in w.groupby('element'):
        qblank=g.qflag.fillna('').astype(str).str.strip().eq('')
        valid=g.date_dt.notna() & g.value_num.notna() & qblank
        dates=set(g.loc[valid,'date_dt'].dt.strftime('%Y-%m-%d'))
        out[str(el)]={'rows':int(len(g)),'unique_dates_any':int(g.date_dt.nunique()),'valid_quality_blank_unique_dates':len(dates),
                      'coverage_fraction_of_study_days':len(dates)/expected,'quality_flag_census':dict(Counter(g.qflag.fillna('').astype(str)).most_common()),
                      'source_flag_census':dict(Counter(g.sflag.fillna('').astype(str)).most_common()),
                      'first_valid_date':min(dates) if dates else None,'last_valid_date':max(dates) if dates else None}
    all_dates=set(w.date_dt.dropna().dt.strftime('%Y-%m-%d'))
    return {'study_days':expected,'rows_in_window':int(len(w)),'dates_with_any_element':len(all_dates),'elements':out}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.parent.mkdir(parents=True,exist_ok=True)
    s=requests.Session();s.headers['User-Agent']=UA
    r=s.get(STATIONS_URL,timeout=180);r.raise_for_status();ib=r.content;rows=parse_inventory(ib.decode('ascii',errors='replace'));cands=station_candidates(rows)
    if not cands:raise RuntimeError('no PALOMAR candidates in official station inventory')
    probes=[];selected=None;selected_b=None;selected_raw=None;selected_df=None
    for c in cands:
        url=BY_STATION.format(station=c['station_id'])
        try:
            q=s.get(url,timeout=180);q.raise_for_status();b=q.content;d,raw=read_station_csv(b);cov=coverage(d)
            probe={**c,'data_url':url,'fetch_status':'OK','gzip_sha256':sha(b),'csv_sha256':sha(raw),'total_rows':len(d),'coverage':cov}
            probes.append(probe)
            if selected is None and cov['rows_in_window']>0:
                selected=probe;selected_b=b;selected_raw=raw;selected_df=d
        except Exception as e:
            probes.append({**c,'data_url':url,'fetch_status':'FAILED','error':repr(e)[:400]})
    if selected is None:raise RuntimeError('no PALOMAR-named official station has rows in study window')
    cov=selected['coverage']; essential={k:cov['elements'].get(k) for k in ['PRCP','TMAX','TMIN','SNOW','SNWD']}
    result={'artifact_id':'JANUS-PALOMAR-JPFM-5A-LOCAL-WEATHER-SOURCE-INTAKE-v1.0','date':'2026-08-15','status':'OUTCOME_BLIND_NCEI_STATION_SELECTED_AND_SOURCE_FROZEN',
      'inventory':{'url':STATIONS_URL,'sha256':sha(ib),'bytes':len(ib),'palomar_named_candidates':cands},
      'candidate_probes':probes,
      'selected_station':{k:v for k,v in selected.items() if k!='coverage'},
      'selected_station_source':{'gzip_sha256':sha(selected_b),'csv_sha256':sha(selected_raw),'gzip_bytes':len(selected_b),'csv_bytes':len(selected_raw)},
      'study_window':[START.strftime('%Y-%m-%d'),END.strftime('%Y-%m-%d')],'coverage':cov,'essential_element_summary':essential,
      'value_units_note':'GHCN-Daily native element units are preserved by source; conversion/interpretation is deferred to the preregistered analysis stage.',
      'hard_boundary':'Missing or quality-flagged values remain missing; PRCP is not cloud fraction and no weather-effect model is executed here.',
      'outcome_blindness':{'poss1_access':False,'bluebook_access':False,'nuclear_calendar_access':False,'association_computed':False},
      'next_gate':'Freeze whether PRCP/TMAX/TMIN coverage is adequate for JPFM-5B and define a low-dimensional weather adjustment conditional only on actually observed Palomar nights.',
      'current_authority_changed':False,'claim_ceiling':'NCEI_STATION_AND_COVERAGE_FREEZE_ONLY__NO_WEATHER_EFFECT_CLAIM'}
    a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps(result,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
