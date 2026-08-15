#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import fisher_exact
from statsmodels.discrete.discrete_model import NegativeBinomial

HERE=Path(__file__).resolve().parent
ADMISSION=Path('data/JANUS-PALOMAR-JPFM-3C-HALPHA-CROSS-CHANNEL-ADMISSION-v1.0.json')
SOLAR=Path('data/JANUS-PALOMAR-JPFM-3B-NOAA-EVENT-PATROL-PARSER-RUN-001.json')
STAR=Path('data/JANUS-BLUEBOOK-STARLIKE-DAY-FREEZE-v1.0.json')
START=dt.date(1955,7,1); END=dt.date(1957,4,28); NPERM=50000

def loadmod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    if s is None or s.loader is None: raise RuntimeError('cannot import '+str(path))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
base=loadmod('jpfm2d',HERE/'jpfm_open_reconstruction_temporal.py')
decomp=loadmod('jpfm2e',HERE/'jpfm_schedule_confound_decomposition.py')

def shab(b):return hashlib.sha256(b).hexdigest()
def shaf(p):return shab(p.read_bytes())

def zscore(s):
    x=pd.to_numeric(s,errors='coerce').astype(float);med=float(x.median());x=x.fillna(med);mu=float(x.mean());sd=float(x.std(ddof=0))
    if not np.isfinite(sd) or sd==0:return pd.Series(np.zeros(len(x)),index=x.index),{'mean':mu,'median':med,'sd':sd}
    return (x-mu)/sd,{'mean':mu,'median':med,'sd':sd}

def eligible_solar(solar,threshold):
    rows=[]
    for r in solar['study_days']:
        d=dt.date.fromisoformat(r['date'])
        if START<=d<=END and int(r['coverage_minutes_union_utc'])>=threshold:
            rows.append({'date':d,'flare':int(r['any_flare_event']),'flare_records':int(r['flare_event_records']),'coverage':int(r['coverage_minutes_union_utc'])})
    return rows

def star_counts():
    j=json.loads(STAR.read_text());return {dt.date.fromisoformat(r['date']):int(r['count']) for r in j['event_days']}

def fisher_day(rows,stars):
    # [flare+star, flare+no], [no-flare+star, no-flare+no]
    tab=np.zeros((2,2),dtype=int)
    for r in rows:
        y=int(stars.get(r['date'],0)>0);tab[r['flare'],y]+=1
    table=[[int(tab[1,1]),int(tab[1,0])],[int(tab[0,1]),int(tab[0,0])]]
    odds,p=fisher_exact(table,alternative='two-sided')
    return {'table_flare_nonflare_by_starlike_none':table,'odds_ratio':float(odds) if np.isfinite(odds) else None,'p_two_sided':float(p),
            'eligible_days':len(rows),'flare_days':int(tab[1].sum()),'nonflare_days':int(tab[0].sum()),'starlike_days':int(tab[:,1].sum())}

def perm_day(rows,stars,seed=19550701):
    blocks=defaultdict(list)
    for r in rows:blocks[(r['date'].year,r['date'].month)].append(r)
    obs=sum(int(stars.get(r['date'],0)>0) for r in rows if r['flare'])
    rng=np.random.default_rng(seed);null=np.zeros(NPERM,dtype=np.int16)
    for rs in blocks.values():
        k=sum(r['flare'] for r in rs);vals=np.array([int(stars.get(r['date'],0)>0) for r in rs],dtype=np.int8)
        if k<=0:continue
        if k>=len(rs):null+=vals.sum();continue
        z=rng.random((NPERM,len(rs)));ix=np.argpartition(z,k-1,axis=1)[:,:k];null+=vals[ix].sum(axis=1)
    up=float((1+np.sum(null>=obs))/(NPERM+1));lo=float((1+np.sum(null<=obs))/(NPERM+1))
    return {'observed_starlike_on_flare_days':int(obs),'null_mean':float(null.mean()),'null_sd':float(null.std(ddof=1)),
            'p_upper_positive':up,'p_lower_negative':lo,'p_two_sided':float(min(1,2*min(up,lo))),'iterations':NPERM,'seed':seed}

def bh(pmap):
    vals=sorted((p,k) for k,p in pmap.items() if p is not None and np.isfinite(p));m=len(vals);q={};prev=1.0
    for rank in range(m,0,-1):
        p,k=vals[rank-1];v=min(prev,p*m/rank);q[k]=float(v);prev=v
    return q

def shift_exposure(rows,lag):
    eligible_dates={r['date'] for r in rows};flare_dates={r['date'] for r in rows if r['flare']}
    shifted={d+dt.timedelta(days=lag) for d in flare_dates}
    return {d:int(d in shifted) for d in eligible_dates}

def blue_lags(rows,stars):
    out={};p={}
    bydate={r['date']:r for r in rows}
    for lag in range(-3,4):
        exp=shift_exposure(rows,lag);rr=[]
        for d,e in exp.items():rr.append({'date':d,'flare':e})
        x=fisher_day(rr,stars);out[str(lag)]=x;p[str(lag)]=x['p_two_sided']
    q=bh(p)
    for k,v in q.items():out[k]['bh_q']=v
    return out

def build_nights():
    s0,tiles,repairs,wcs,hashes=base.read_release_tables();plates=sorted(tiles.plate_id.dropna().astype(str).unique());headers=base.fetch_all_headers(plates)
    allp,_=base.build_plate_table(s0,tiles,repairs,wcs,headers);allp['date_obj']=pd.to_datetime(allp.date_obs).dt.date
    p=allp[(allp.date_obj>=START)&(allp.date_obj<=END)].copy().drop(columns=['date_obj'])
    n=decomp.aggregate_nights_extended(p)
    gfz,gmeta=decomp.fetch_gfz_daily();n=n.merge(gfz[['date_obs','daily_Ap','max_kp']],on='date_obs',how='left',validate='one_to_one')
    moon,mmeta=decomp.fetch_usno_moon(n.date_obs.astype(str));n=n.merge(moon[['date_obs','lunar_illumination_fraction']],on='date_obs',how='left',validate='one_to_one')
    return n,{'release_hashes':hashes,'gfz':gmeta,'moon':mmeta,'plates':len(p)}

def fit_poss(n,solar_rows):
    sm={r['date'].isoformat():r for r in solar_rows};d=n[n.date_obs.astype(str).isin(sm)].copy().reset_index(drop=True)
    d['flare']=[sm[x]['flare'] for x in d.date_obs.astype(str)];d['solar_coverage_min']=[sm[x]['coverage'] for x in d.date_obs.astype(str)]
    if d.flare.nunique()<2:return {'status':'NO_EVENT_VARIATION','n':len(d)}
    X=pd.DataFrame({'intercept':np.ones(len(d)),'event':d.flare.astype(float)});dates=pd.to_datetime(d.date_obs)
    X=pd.concat([X,pd.get_dummies(dates.dt.month,prefix='month',drop_first=True,dtype=float).reset_index(drop=True),
                 pd.get_dummies(dates.dt.year,prefix='year',drop_first=True,dtype=float).reset_index(drop=True)],axis=1)
    scalers={}
    for src,dst in [('sky_ra_sin','sky_ra_sin_z'),('sky_ra_cos','sky_ra_cos_z'),('plate_dec_deg','dec_z'),('abs_galactic_b_deg','abs_gal_b_z'),
                    ('exposure_min','exposure_z'),('wcs_offset_arcsec','wcs_z'),('lunar_illumination_fraction','lunar_z'),('daily_Ap','Ap_z'),('max_kp','Kp_z')]:
        X[dst],scalers[src]=zscore(d[src])
    y=d.candidate_count.astype(float).to_numpy();opp=d.tile_count.astype(float).to_numpy()
    try:
        res=NegativeBinomial(y,X.astype(float).to_numpy(),offset=np.log(opp),loglike_method='nb2').fit(disp=0,maxiter=1500)
        names=list(X.columns)+['alpha'];idx=names.index('event');beta=float(res.params[idx]);ci=np.asarray(res.conf_int(),float)[idx]
        a=d[d.flare==1];b=d[d.flare==0];ra=float(a.candidate_count.sum()/a.tile_count.sum());rb=float(b.candidate_count.sum()/b.tile_count.sum())
        return {'status':'OK','n':len(d),'flare_nights':int(d.flare.sum()),'nonflare_nights':int((1-d.flare).sum()),'event_beta':beta,'event_se':float(res.bse[idx]),
                'p_two_sided':float(res.pvalues[idx]),'irr':float(math.exp(beta)),'irr_ci95':[float(math.exp(ci[0])),float(math.exp(ci[1]))],
                'crude_rate_flare':ra,'crude_rate_nonflare':rb,'crude_rate_ratio':float(ra/rb),'aic':float(res.aic),'alpha':float(res.params[-1]),'scalers':scalers}
    except Exception as e:
        return {'status':'MODEL_FAILURE_FAIL_CLOSED','n':len(d),'flare_nights':int(d.flare.sum()),'error':repr(e)}

def poss_lags(n,solar_rows):
    eligible={r['date'] for r in solar_rows};flare={r['date'] for r in solar_rows if r['flare']};out={};p={}
    for lag in range(-3,4):
        shifted=flare.copy();shifted={x+dt.timedelta(days=lag) for x in shifted}
        rows=[{'date':d,'flare':int(d in shifted),'coverage':720} for d in eligible]
        x=fit_poss(n,rows);out[str(lag)]=x
        if x.get('status')=='OK':p[str(lag)]=x['p_two_sided']
    q=bh(p)
    for k,v in q.items():out[k]['bh_q']=v
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.parent.mkdir(parents=True,exist_ok=True)
    adm=json.loads(ADMISSION.read_text());solar=json.loads(SOLAR.read_text());stars=star_counts()
    if adm['status']!='PREREGISTERED_BEFORE_HALPHA_TO_BLUEBOOK_OR_POSS_OUTCOME_JOIN':raise RuntimeError('admission gate')
    print('[1/5] source-qualified solar calendar',flush=True);primary=eligible_solar(solar,720)
    print('[2/5] Blue Book exact-day + blocked null',flush=True);blue={'exact_day':fisher_day(primary,stars),'permutation':perm_day(primary,stars),'lags':blue_lags(primary,stars)}
    print('[3/5] public POSS reconstruction + frozen nuisance sources',flush=True);nights,pmeta=build_nights()
    print('[4/5] POSS exact-day + lags and coverage sensitivities',flush=True);poss={'exact_day':fit_poss(nights,primary),'lags':poss_lags(nights,primary)}
    sens={}
    for t in (360,1080):
        rs=eligible_solar(solar,t);sens[str(t)]={'bluebook':{'exact_day':fisher_day(rs,stars),'permutation':perm_day(rs,stars,19550701+t)},'poss':fit_poss(nights,rs),'eligible_solar_days':len(rs)}
    bp=blue['permutation']['p_upper_positive'];pp=poss['exact_day'].get('p_two_sided',1.0);bdir=(blue['permutation']['observed_starlike_on_flare_days']>blue['permutation']['null_mean']);pdir=(poss['exact_day'].get('irr',1.0)>1)
    admitted=bool(bdir and pdir and bp<.05 and pp<.05)
    verdict='HALPHA_SHARED_CROSS_CHANNEL_PATTERN_ADMITTED' if admitted else 'NO_HALPHA_CROSS_CHANNEL_PATTERN_ADMITTED'
    result={'artifact_id':'JANUS-PALOMAR-JPFM-3C-HALPHA-CROSS-CHANNEL-RUN-001','experiment_id':'JPFM-3C','date':dt.date.today().isoformat(),'status':'EXECUTED',
      'claim_ceiling':'HALPHA_TEMPORAL_CROSS_CHANNEL_TEST_ONLY__NO_CAUSALITY_OR_SHARED_OBJECT_OR_ORIGIN_CLAIM',
      'bindings':{'admission':str(ADMISSION),'admission_sha256':shaf(ADMISSION),'solar_parser':str(SOLAR),'solar_parser_sha256':shaf(SOLAR),'starlike_freeze':str(STAR),'starlike_sha256':shaf(STAR),'poss':pmeta},
      'primary_coverage_minutes':720,'primary_solar_eligible_days':len(primary),'primary_flare_days':sum(r['flare'] for r in primary),
      'bluebook_primary':blue,'poss_primary':poss,'coverage_sensitivities':sens,
      'aggregate_verdict':{'code':verdict,'shared_pattern_admitted':admitted,'bluebook_positive_direction':bool(bdir),'poss_positive_direction':bool(pdir),'bluebook_positive_tail_p':bp,'poss_exact_p_two_sided':pp},
      'current_authority_changed':False}
    a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8');print(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))
if __name__=='__main__':main()
