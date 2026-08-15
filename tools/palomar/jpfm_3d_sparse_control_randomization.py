#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import itertools
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ADMISSION=Path('data/JANUS-PALOMAR-JPFM-3D-SPARSE-CONTROL-RANDOMIZATION-ADMISSION-v1.0.json')
SOLAR=Path('data/JANUS-PALOMAR-JPFM-3B-NOAA-EVENT-PATROL-PARSER-RUN-001.json')
START=dt.date(1955,7,1); END=dt.date(1957,4,28)

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise RuntimeError(f'cannot import {path}')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
base=loadmod('jpfm2d',HERE/'jpfm_open_reconstruction_temporal.py')
decomp=loadmod('jpfm2e',HERE/'jpfm_schedule_confound_decomposition.py')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def solar_rows(threshold):
    s=json.loads(SOLAR.read_text())
    out=[]
    for r in s['study_days']:
        d=dt.date.fromisoformat(r['date'])
        if START<=d<=END and int(r['coverage_minutes_union_utc'])>=threshold:
            out.append({'date':d,'flare':int(r['any_flare_event']),'coverage':int(r['coverage_minutes_union_utc'])})
    return out

def palomar_nights():
    s0,tiles,repairs,wcs,hashes=base.read_release_tables()
    plates=sorted(tiles.plate_id.dropna().astype(str).unique())
    headers=base.fetch_all_headers(plates)
    allp,_=base.build_plate_table(s0,tiles,repairs,wcs,headers)
    allp['date_obj']=pd.to_datetime(allp.date_obs).dt.date
    p=allp[(allp.date_obj>=START)&(allp.date_obj<=END)].copy().drop(columns=['date_obj'])
    n=decomp.aggregate_nights_extended(p)
    return n,hashes,len(p)

def build_cohort(nights,threshold):
    sm={r['date'].isoformat():r for r in solar_rows(threshold)}
    d=nights[nights.date_obs.astype(str).isin(sm)].copy().reset_index(drop=True)
    d['flare']=[sm[x]['flare'] for x in d.date_obs.astype(str)]
    d['coverage']=[sm[x]['coverage'] for x in d.date_obs.astype(str)]
    d['year']=pd.to_datetime(d.date_obs).dt.year.astype(int)
    return d

def rate_stat(d,labels=None):
    lab=d.flare.to_numpy(dtype=int) if labels is None else np.asarray(labels,dtype=int)
    y=d.candidate_count.to_numpy(dtype=float);o=d.tile_count.to_numpy(dtype=float)
    if lab.sum()==0 or (1-lab).sum()==0:return None
    rf=float(y[lab==1].sum()/o[lab==1].sum());rn=float(y[lab==0].sum()/o[lab==0].sum())
    if rf<=0 or rn<=0:return None
    return {'rate_flare':rf,'rate_nonflare':rn,'rate_ratio':float(rf/rn),'log_rate_ratio':float(math.log(rf/rn))}

def exact_year_stratified(d):
    groups=[]; observed_nonflare=[]
    for year,g in d.groupby('year',sort=True):
        idx=list(g.index);k=int((g.flare==0).sum())
        groups.append((int(year),idx,k,list(itertools.combinations(idx,k))))
        observed_nonflare.extend(g.index[g.flare==0].tolist())
    n_assign=1
    for _,_,_,c in groups:n_assign*=len(c)
    if n_assign>2000000:raise RuntimeError(f'exact assignment space too large: {n_assign}')
    obs=rate_stat(d)
    if obs is None:raise RuntimeError('observed statistic undefined')
    null=[]
    for choices in itertools.product(*(g[3] for g in groups)):
        nf=set(itertools.chain.from_iterable(choices));labels=np.ones(len(d),dtype=int)
        for i in nf:labels[i]=0
        s=rate_stat(d,labels)
        if s is not None:null.append(s['log_rate_ratio'])
    arr=np.asarray(null,dtype=float);z=obs['log_rate_ratio']
    return {
      'observed':obs,
      'year_strata':[{'year':y,'n_nights':len(idx),'n_nonflare':k,'assignments':len(c)} for y,idx,k,c in groups],
      'total_exact_assignments':int(len(arr)),
      'null_mean_log_rr':float(arr.mean()),'null_sd_log_rr':float(arr.std(ddof=1)) if len(arr)>1 else 0.0,
      'p_lower_negative':float(np.sum(arr<=z)/len(arr)),
      'p_upper_positive':float(np.sum(arr>=z)/len(arr)),
      'p_two_sided_abs_log_rr':float(np.sum(np.abs(arr)>=abs(z))/len(arr)),
      'null_min_log_rr':float(arr.min()),'null_max_log_rr':float(arr.max())
    }

def influence(d):
    out=[]
    controls=d.index[d.flare==0].tolist()
    for i in controls:
        q=d.drop(index=i).reset_index(drop=True);s=rate_stat(q)
        out.append({'removed_control_date':str(d.loc[i,'date_obs']),'removed_candidate_count':int(d.loc[i,'candidate_count']),
                    'removed_tile_count':int(d.loc[i,'tile_count']),'remaining':s})
    return out

def run_threshold(nights,t):
    d=build_cohort(nights,t)
    exact=exact_year_stratified(d);inf=influence(d)
    stable=bool(exact['p_lower_negative']<0.05 and inf and all(x['remaining'] is not None and x['remaining']['rate_ratio']<1 for x in inf))
    return {'coverage_minutes':t,'n_nights':len(d),'flare_nights':int(d.flare.sum()),'nonflare_nights':int((d.flare==0).sum()),
            'night_rows':[{'date':str(r.date_obs),'candidate_count':int(r.candidate_count),'tile_count':int(r.tile_count),'flare':int(r.flare),'coverage':int(r.coverage)} for r in d.itertuples()],
            'exact_year_stratified':exact,'leave_one_nonflare_control_out':inf,'negative_pattern_retained_under_gate':stable}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.parent.mkdir(parents=True,exist_ok=True)
    adm=json.loads(ADMISSION.read_text())
    if adm['status']!='PREREGISTERED_POST_3C_IDENTIFIABILITY_REPAIR_BEFORE_3D_OUTCOME':raise RuntimeError('admission status mismatch')
    print('[1/3] reconstruct fixed Palomar nights',flush=True);nights,hashes,nplates=palomar_nights()
    print('[2/3] exact 720-minute primary randomization',flush=True);primary=run_threshold(nights,720)
    print('[3/3] frozen 360-minute sensitivity',flush=True);sens=run_threshold(nights,360)
    retained=bool(primary['negative_pattern_retained_under_gate'])
    result={'artifact_id':'JANUS-PALOMAR-JPFM-3D-SPARSE-CONTROL-RANDOMIZATION-RUN-001','experiment_id':'JPFM-3D','date':dt.date.today().isoformat(),'status':'EXECUTED',
      'epistemic_role':adm['epistemic_role'],'claim_ceiling':'FINITE_SAMPLE_IDENTIFIABILITY_REPAIR_ONLY__NO_SOLAR_CAUSALITY',
      'bindings':{'admission':str(ADMISSION),'admission_sha256':sha(ADMISSION),'solar_parser':str(SOLAR),'solar_parser_sha256':sha(SOLAR),'poss_release_hashes':hashes,'palomar_plates_in_scope':nplates},
      'primary_720':primary,'sensitivity_360':sens,
      'aggregate_verdict':{'negative_pattern_retained':retained,'code':'NEGATIVE_HALPHA_POSS_PATTERN_RETAINED_AFTER_SPARSE_CONTROL_REPAIR' if retained else 'NEGATIVE_HALPHA_POSS_PATTERN_NOT_RETAINED_AFTER_SPARSE_CONTROL_REPAIR'},
      'current_authority_changed':False}
    a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8');print(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))
if __name__=='__main__':main()
