"""Independent numerical witness for JANUS-LOGOS-001.

No imports from the generator. Recomputes all cycles using Python's float64
math implementation rather than the generating mpmath implementation.
This is a code-independent check, not an independent scientific laboratory.
"""
from __future__ import annotations
import argparse
import json
import math
import sys
from pathlib import Path

EXPECTED={'logistic':('quadratic',0),'sine':('quadratic',0),'quartic':('quartic',1)}
REFERENCE_QUADRATIC=4.66920160910299
REFERENCE_QUARTIC=7.284686217073

def _iterate(name,a,steps):
    x=0.0 if name=='quartic' else 0.5
    if name=='logistic':
        for _ in range(steps):x=a*x*(1.0-x)
    elif name=='sine':
        for _ in range(steps):x=a*math.sin(math.pi*x)
    else:
        for _ in range(steps):x=1.0-a*(x*x)*(x*x)
    return x

def verify(obj):
    assert obj['experiment']=='JANUS-LOGOS-001'
    assert obj['data_class']=='DETERMINISTIC_NUMERICAL_SIMULATION'
    assert obj['known_literature_references']['used_in_root_search'] is False
    maps=obj['map_data'];assert set(maps)==set(EXPECTED)
    evidence={}
    for name,(kind,n_first) in EXPECTED.items():
        m=maps[name];assert m['critical_order']==kind
        assert m['n_first']==n_first and m['n_last']==obj['depth']
        seq=[float(z) for z in m['superstable_parameters']]
        assert len(seq)==obj['depth']-n_first+1
        assert all(b>a for a,b in zip(seq,seq[1:])),name
        initial_c=0.0 if name=='quartic' else 0.5
        residuals=[]
        for n,a in enumerate(seq,start=n_first):
            error=abs(_iterate(name,a,2**n)-initial_c)
            assert math.isfinite(error) and error<1e-8,(name,n,'root',error)
            residuals.append(error)
            if n>n_first:
                primitive=abs(_iterate(name,a,2**(n-1))-initial_c)
                assert primitive>1e-5,(name,n,'primitive',primitive)
        ratios=[(seq[i-1]-seq[i-2])/(seq[i]-seq[i-1]) for i in range(2,len(seq))]
        reported=[float(x) for x in m['ratios']]
        assert len(reported)==len(ratios)
        assert all(abs(a-b)<2e-8 for a,b in zip(reported,ratios)),name
        assert abs(float(m['final_ratio'])-ratios[-1])<2e-8,name
        evidence[name]={'delta_estimate':ratios[-1],'max_float64_root_residual':max(residuals),'n_ladder':len(seq)}
    a,b,c=(evidence[k]['delta_estimate'] for k in ('logistic','sine','quartic'))
    assert abs(a-REFERENCE_QUADRATIC)<0.002,('logistic class',a)
    assert abs(b-REFERENCE_QUADRATIC)<0.002,('sine class',b)
    assert abs(a-b)<0.002,('cross-map agreement',a,b)
    assert abs(c-REFERENCE_QUARTIC)<0.005,('quartic reference',c)
    assert abs(c-a)>1,('quartic negative class rejection',c,a)
    return {'witness':'INDEPENDENT_FLOAT64_RECOMPUTATION',
            'verdict':'PASS_SCOPED_NUMERICAL_UNIVERSALITY_REPLICATION',
            'evidence':evidence,
            'scope':'KNOWN_PERIOD_DOUBLING_UNIVERSALITY_NOT_NEW_DISCOVERY_NOT_DIVINE_PROOF',
            'open_lanes':['SYMBOLIC_DISCOVERY','MULTI_AGENT_ABLATION','INDEPENDENT_LAB']}

def negative_tamper_tests(obj):
    # Verifier must reject a corrupted trajectory and a falsely relabeled control.
    corrupted=json.loads(json.dumps(obj))
    p=corrupted['map_data']['sine']['superstable_parameters']
    p[-1]=str(float(p[-1])+0.0001)
    try:verify(corrupted)
    except (AssertionError,ValueError,OverflowError):pass
    else:raise AssertionError('Tampered superstable parameter accepted')
    relabeled=json.loads(json.dumps(obj))
    relabeled['map_data']['quartic']['critical_order']='quadratic'
    try:verify(relabeled)
    except (AssertionError,ValueError):pass
    else:raise AssertionError('False quartic class label accepted')
    return {'tampered_root':'REJECTED','false_control_label':'REJECTED'}

def main():
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--self-test',action='store_true');p.add_argument('--out');args=p.parse_args()
    d=json.loads(Path(args.input).read_text(encoding='utf-8'))
    try:
        verdict=verify(d)
        if args.self_test:verdict['tamper_tests']=negative_tamper_tests(d)
    except Exception as ex:
        print(json.dumps({'verdict':'FAIL','error':str(ex)}),file=sys.stderr)
        raise SystemExit(1)
    raw=json.dumps(verdict,indent=2)+'\n'
    if args.out:Path(args.out).write_text(raw,encoding='utf-8')
    print(raw)
if __name__=='__main__':main()
