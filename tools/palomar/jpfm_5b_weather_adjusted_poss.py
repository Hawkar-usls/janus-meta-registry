#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from statsmodels.discrete.discrete_model import Logit, NegativeBinomial

HERE=Path(__file__).resolve().parent
ADMISSION=Path('data/JANUS-PALOMAR-JPFM-5B-WEATHER-ADJUSTED-POSS-ADMISSION-v1.0.json')
WEATHER_SOURCE=Path('data/JANUS-PALOMAR-JPFM-5A-LOCAL-WEATHER-SOURCE-INTAKE-v1.0.json')

def loadmod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    if s is None or s.loader is None:raise RuntimeError(f'cannot import {path}')
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
base=loadmod('jpfm2d',HERE/'jpfm_open_reconstruction_temporal.py')
decomp=loadmod('jpfm2e',HERE/'jpfm_schedule_confound_decomposition.py')

def sha(b):return hashlib.sha256(b).hexdigest()
def shaf(p):return sha(p.read_bytes())

def fetch_weather():
    meta=json.loads(WEATHER_SOURCE.read_text());sel=meta['selected_station'];src=meta['selected_station_source']
    r=requests.get(sel['data_url'],headers={'User-Agent':'JANUS-JPFM-5B-weather/1.0'},timeout=180);r.raise_for_status();b=r.content
    if sha(b)!=src['gzip_sha256']:raise RuntimeError('weather gzip hash mismatch')
    raw=gzip.decompress(b)
    if sha(raw)!=src['csv_sha256']:raise RuntimeError('weather csv hash mismatch')
    cols=['station_id','date','element','value','mflag','qflag','sflag','obs_time']
    d=pd.read_csv(io.BytesIO(raw),header=None,names=cols,dtype=str)
    d=d[d.element=='PRCP'].copy();d['date_dt']=pd.to_datetime(d.date,format='%Y%m%d',errors='coerce')
    d['value_num']=pd.to_numeric(d.value,errors='coerce');d['qclean']=d.qflag.fillna('').astype(str).str.strip().eq('')
    d=d[d.qclean & d.date_dt.notna() & d.value_num.notna()].copy()
    d['wet_day']=(d.value_num>0).astype(int);d['prcp_mm']=d.value_num/10.0
    if d.date_dt.duplicated().any():raise RuntimeError('duplicate QA-clean PRCP date')
    return d[['date_dt','wet_day','prcp_mm','value_num','mflag','sflag','obs_time']],{'station_id':sel['station_id'],'station_name':sel['name'],'data_url':sel['data_url'],'gzip_sha256':sha(b),'csv_sha256':sha(raw),'qa_clean_prcp_dates':len(d)}

def reconstruct_nights():
    s0,tiles,repairs,wcs,hashes=base.read_release_tables();plates=sorted(tiles.plate_id.dropna().astype(str).unique());headers=base.fetch_all_headers(plates)
    allp,_=base.build_plate_table(s0,tiles,repairs,wcs,headers);allp['date_obj']=pd.to_datetime(allp.date_obs).dt.date
    p=allp[(allp.date_obj>=base.STUDY_START)&(allp.date_obj<=base.STUDY_END)].copy().drop(columns=['date_obj'])
    n=decomp.aggregate_nights_extended(p)
    gfz,gmeta=decomp.fetch_gfz_daily();n=n.merge(gfz[['date_obs','daily_Ap','max_kp']],on='date_obs',how='left',validate='one_to_one')
    moon,mmeta=decomp.fetch_usno_moon(n.date_obs.astype(str));n=n.merge(moon[['date_obs','lunar_illumination_fraction']],on='date_obs',how='left',validate='one_to_one')
    return n,{'poss_release_hashes':hashes,'plates':len(p),'observed_nights':len(n),'gfz':gmeta,'moon':mmeta}

def align_weather_dates(dates,weather,lag_days):
    w=weather.set_index('date_dt')[['wet_day','prcp_mm']]
    rows=[]
    for x in pd.to_datetime(pd.Series(dates)):
        wd=x+pd.Timedelta(days=lag_days)
        if wd in w.index:
            r=w.loc[wd];rows.append((int(r.wet_day),float(r.prcp_mm),wd.strftime('%Y-%m-%d')))
        else:rows.append((None,None,wd.strftime('%Y-%m-%d')))
    return rows

def schedule_fit(nights,weather,lag_days):
    observed=set(nights.date_obs.astype(str));rows=[];d=base.STUDY_START
    while d<=base.STUDY_END:
        x=pd.Timestamp(d.isoformat());a=align_weather_dates([x],weather,lag_days)[0]
        if a[0] is not None:rows.append({'date':x,'observed':int(d.isoformat() in observed),'wet_day':a[0],'weather_date':a[2]})
        d+=dt.timedelta(days=1)
    q=pd.DataFrame(rows);dates=q.date
    X=pd.DataFrame({'intercept':np.ones(len(q)),'wet_day':q.wet_day.astype(float)})
    X=pd.concat([X,pd.get_dummies(dates.dt.month,prefix='month',drop_first=True,dtype=float).reset_index(drop=True),pd.get_dummies(dates.dt.year,prefix='year',drop_first=True,dtype=float).reset_index(drop=True)],axis=1)
    res=Logit(q.observed.astype(float).to_numpy(),X.astype(float).to_numpy()).fit(disp=0,maxiter=1000)
    idx=list(X.columns).index('wet_day');beta=float(res.params[idx]);ci=np.asarray(res.conf_int(),float)[idx]
    return {'status':'OK','n_calendar_days_with_qa_clean_prcp':len(q),'observed_nights_in_model':int(q.observed.sum()),'wet_calendar_days':int(q.wet_day.sum()),
            'beta':beta,'se':float(res.bse[idx]),'p_two_sided':float(res.pvalues[idx]),'odds_ratio':float(math.exp(beta)),'or_ci95':[float(math.exp(ci[0])),float(math.exp(ci[1]))]}

def rate_fit(nights,weather,lag_days):
    d=nights.copy().reset_index(drop=True);aligned=align_weather_dates(d.date_obs,weather,lag_days);d['wet_day']=[x[0] for x in aligned];d['prcp_mm']=[x[1] for x in aligned];d['weather_date']=[x[2] for x in aligned]
    d=d[d.wet_day.notna()].copy().reset_index(drop=True);d['wet_day']=d.wet_day.astype(int)
    if d.wet_day.nunique()<2:return {'status':'NO_WET_DRY_VARIATION','n':len(d)}
    X,scalers=decomp.calendar_design(d,'wet_day','M6_GEOMAGNETIC_FULL')
    # decomp uses a generic historical name for the tested binary exposure; rename semantically in output only.
    y=d.candidate_count.astype(float).to_numpy();opp=d.tile_count.astype(float).to_numpy()
    res=NegativeBinomial(y,X.astype(float).to_numpy(),offset=np.log(opp),loglike_method='nb2').fit(disp=0,maxiter=1500)
    names=list(X.columns)+['alpha'];idx=names.index('nuclear_window');beta=float(res.params[idx]);ci=np.asarray(res.conf_int(),float)[idx]
    a=d[d.wet_day==1];b=d[d.wet_day==0];ra=float(a.candidate_count.sum()/a.tile_count.sum());rb=float(b.candidate_count.sum()/b.tile_count.sum())
    vals=[beta,float(res.bse[idx]),float(res.pvalues[idx]),float(ci[0]),float(ci[1]),ra,rb,float(res.params[-1])]
    if not all(np.isfinite(vals)):
        return {'status':'MODEL_NONFINITE_INFERENCE_FAIL_CLOSED','n':len(d),'wet_nights':int(d.wet_day.sum()),'dry_nights':int((d.wet_day==0).sum())}
    return {'status':'OK','n':len(d),'wet_nights':int(d.wet_day.sum()),'dry_nights':int((d.wet_day==0).sum()),'beta':beta,'se':float(res.bse[idx]),'p_two_sided':float(res.pvalues[idx]),
            'irr':float(math.exp(beta)),'irr_ci95':[float(math.exp(ci[0])),float(math.exp(ci[1]))],'rate_wet':ra,'rate_dry':rb,'crude_rate_ratio':float(ra/rb),
            'alpha':float(res.params[-1]),'aic':float(res.aic),'scalers':scalers,'mean_prcp_mm_wet_nights':float(a.prcp_mm.mean()) if len(a) else None}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.parent.mkdir(parents=True,exist_ok=True)
    adm=json.loads(ADMISSION.read_text())
    if adm['status']!='PREREGISTERED_BEFORE_WEATHER_TO_POSS_OUTCOME_JOIN':raise RuntimeError('admission gate')
    print('[1/4] hash-gate official NCEI station data',flush=True);weather,wmeta=fetch_weather()
    print('[2/4] reconstruct public POSS observed-night cohort',flush=True);nights,pmeta=reconstruct_nights()
    print('[3/4] primary previous-day weather alignment',flush=True);primary={'schedule':schedule_fit(nights,weather,-1),'rate':rate_fit(nights,weather,-1)}
    print('[4/4] frozen same-date sensitivity',flush=True);sens={'schedule':schedule_fit(nights,weather,0),'rate':rate_fit(nights,weather,0)}
    p1=primary['schedule'].get('p_two_sided',1.0);p2=primary['rate'].get('p_two_sided',1.0)
    if p2<.05:code='WET_DAY_CANDIDATE_RATE_ASSOCIATION_DETECTED__ACQUISITION_QUALITY_ONLY'
    elif p1<.05:code='WET_DAY_OBSERVING_SCHEDULE_ASSOCIATION_ONLY__NO_RESIDUAL_RATE_ASSOCIATION'
    else:code='NO_DETECTED_PRIMARY_WET_DAY_SCHEDULE_OR_RATE_ASSOCIATION'
    result={'artifact_id':'JANUS-PALOMAR-JPFM-5B-WEATHER-ADJUSTED-POSS-RUN-001','experiment_id':'JPFM-5B','date':'2026-08-15','status':'EXECUTED',
      'claim_ceiling':'LOCAL_DAILY_PRECIPITATION_ACQUISITION_AND_RATE_ASSOCIATION_ONLY__PRCP_IS_NOT_CLOUD_COVER__NO_ORIGIN_CLAIM',
      'bindings':{'admission':str(ADMISSION),'admission_sha256':shaf(ADMISSION),'weather_source':str(WEATHER_SOURCE),'weather_source_sha256':shaf(WEATHER_SOURCE),'weather':wmeta,'poss':pmeta},
      'primary_alignment':{'weather_lag_days_relative_to_poss_utc_date':-1,**primary},'same_date_sensitivity':{'weather_lag_days_relative_to_poss_utc_date':0,**sens},
      'aggregate_verdict':{'code':code,'primary_schedule_p':p1,'primary_rate_p':p2},
      'interpretation_boundaries':['PRCP>0 is measured daily precipitation, not cloud fraction.','Missing/QA-bad weather is excluded, not dry.','Candidate-rate model includes only actually observed Palomar nights.','Same-date sensitivity cannot rescue the primary alignment.'],
      'current_authority_changed':False}
    a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8');print(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))
if __name__=='__main__':main()
