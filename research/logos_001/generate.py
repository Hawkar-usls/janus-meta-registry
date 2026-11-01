"""JANUS-LOGOS-001: reproducible superstable parameter-ladder experiment.

Pure research computation; no scheduler, AI service, paid job or site effects.
Requires mpmath>=1.3.0. Reference constants are only used for post-hoc scoring.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import mpmath as mp

MAPS={
 'logistic': {'kind':'quadratic','seed':'2','upper':'4','formula':'r*x*(1-x)'},
 'sine': {'kind':'quadratic','seed':'0.5','upper':'1','formula':'a*sin(pi*x)'},
 'quartic': {'kind':'quartic','seed':'1','upper':'2','formula':'1-a*x^4','start_n':1},
}

def iterate(map_id, a, steps):
    x=mp.mpf('0.5') if map_id in ('logistic','sine') else mp.mpf('0')
    for _ in range(steps):
        if map_id=='logistic': x=a*x*(1-x)
        elif map_id=='sine': x=a*mp.sin(mp.pi*x)
        else: x=1-a*x**4
    return x

def residual(map_id, a, n):
    c=mp.mpf('0') if map_id=='quartic' else mp.mpf('0.5')
    return iterate(map_id,a,2**n)-c

def bisection(map_id, n, lo, hi, rounds=205):
    flo=residual(map_id,lo,n)
    fhi=residual(map_id,hi,n)
    if flo*fhi>=0: raise RuntimeError('No sign bracket')
    for _ in range(rounds):
        mid=(lo+hi)/2
        fm=residual(map_id,mid,n)
        if fm==0:return mid
        if fm*flo>0:lo,flo=mid,fm
        else:hi,fhi=mid,fm
    return (lo+hi)/2

def next_root(map_id,n,previous,prior_gap,upper):
    # Search first sign-changing root above the previous superstable parameter.
    # The source reference delta is NOT used for prediction or root finding.
    margin=mp.mpf('1e-14') if prior_gap is None else prior_gap*mp.mpf('1e-6')
    if prior_gap is None: end=upper
    else: end=min(upper,previous+prior_gap*mp.mpf('0.9'))
    if previous+margin>=end:raise RuntimeError('Empty scan')
    left=previous+margin
    fleft=residual(map_id,left,n)
    for k in range(1,501):
        right=previous+margin+(end-previous-margin)*mp.mpf(k)/500
        fright=residual(map_id,right,n)
        if fleft*fright<0:
            root=bisection(map_id,n,left,right)
            if abs(residual(map_id,root,n))>mp.mpf('1e-40'):
                raise RuntimeError('Root residual too large')
            if n>0 and abs(residual(map_id,root,n-1))<mp.mpf('1e-25'):
                raise RuntimeError('Period not primitive')
            return root
        left,fleft=right,fright
    raise RuntimeError(f'No next root for {map_id} n={n} interval=({previous},{end})')

def compute(depth):
    mp.mp.dps=85
    output={}
    for name,cfg in MAPS.items():
        start_n=cfg.get('start_n',0)
        arr=[mp.mpf(cfg['seed'])]
        for n in range(start_n+1,depth+1):
            gap=arr[-1]-arr[-2] if len(arr)>1 else None
            arr.append(next_root(name,n,arr[-1],gap,mp.mpf(cfg['upper'])))
        ratios=[(arr[i-1]-arr[i-2])/(arr[i]-arr[i-1]) for i in range(2,len(arr))]
        output[name]={
          'critical_order':cfg['kind'],'map_formula':cfg['formula'],
          'superstable_parameters':[mp.nstr(a,68) for a in arr],
          'ratios':[mp.nstr(a,48) for a in ratios],
          'final_ratio':mp.nstr(ratios[-1],48),
          'last_root_residuals':[mp.nstr(abs(residual(name,arr[i],i+start_n)),6) for i in range(len(arr))],
          'n_last':depth,'n_first':start_n,
        }
    return output

def main():
    p=argparse.ArgumentParser();p.add_argument('--depth',type=int,default=8);p.add_argument('--out',default='result.json');a=p.parse_args()
    if not 5<=a.depth<=10:raise SystemExit('depth must be between 5 and 10')
    maps=compute(a.depth)
    experiment={
      'experiment':'JANUS-LOGOS-001', 'subexperiment':'FEIGENBAUM_3_FAMILY_REPLICATION_R0',
      'protocol_version':'1.0.0', 'data_class':'DETERMINISTIC_NUMERICAL_SIMULATION',
      'state':'NUMERICAL_RUN_DONE__INDEPENDENT_WITNESS_PENDING',
      'preregistration_note':'This fixed plan is committed with code for future reruns; first local exploratory run occurred before repository freeze and is not prospectively preregistered.',
      'dps':85,'depth':a.depth,
      'methods':{'root':'superstable critical orbit f^(2^n)(c)=c; outward scan and sign-bisection','estimate':'(a_(n-1)-a_(n-2))/(a_n-a_(n-1))','external_reference_use':'scoring_only_not_search'},
      'hypothesis':{'positive':'Two distinct smooth quadratic-maximum maps converge to same Feigenbaum delta','negative':'Quartic critical map does not converge to quadratic Feigenbaum delta'},
      'known_literature_references':{'quadratic_delta':'4.66920160910299067185','quartic_delta':'7.284686217073','used_in_root_search':False},
      'map_data':maps,
      'limits':['Numerical replication of known universality, not a new physical law.','Maps are deterministic and not independent physical experimental apparatus.','Scientific result does not demonstrate metaphysical God Code hypothesis.','Symbolic regression and agent-count ablation remain NOT_RUN.'],
      'sources':['https://mathworld.wolfram.com/FeigenbaumConstant.html','https://www.sciencedirect.com/science/article/pii/S100757042030160X']
    }
    raw=json.dumps(experiment,indent=2,ensure_ascii=False)+'\n'
    Path(a.out).write_text(raw,encoding='utf-8')
    print(json.dumps({'result_path':a.out,'final_ratios':{k:v['final_ratio'] for k,v in maps.items()},'depth':a.depth},indent=2))
if __name__=='__main__':main()
