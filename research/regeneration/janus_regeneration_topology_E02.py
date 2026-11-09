#!/usr/bin/env python3
"""JANUS E02: structural/topology stress test of the UNCALIBRATED E01 toy model."""
import random, json, statistics, argparse
from janus_regeneration_v1 import SCENARIOS, clamp

N=128
TICKS=100
CASES=("human_scarring_like","combined_bounded","ablate_immune","ablate_nerve",
       "ablate_pattern","ablate_matrix","unbounded_growth")
TOPOLOGIES=("product","mean","bottleneck","geometric_mean")

def gate(values,mode):
    if mode=="product":
        value=1
        for x in values: value*=x
        return value
    if mode=="mean": return sum(values)/len(values)
    if mode=="bottleneck": return min(values)
    value=1
    for x in values: value*=x
    return value**(1/len(values))

def simulate(params,seed,mode):
    rng=random.Random(seed)
    names=("scar_form","scar_remodel","progenitor_activation",
           "progenitor_loss","organize","dysregulate")
    k={name:rng.uniform(.78,1.22) for name in names}
    f,b,t,u=.09,.07,.03,0.0
    m,n,p,e,g,c=[params[x] for x in ("immune","nerve","pattern","matrix",
                                      "progenitor_drive","growth_brake")]
    for _ in range(TICKS):
        d_f=.020*k["scar_form"]*(1-t)*(1-.72*m)*(1-.55*e)-.027*k["scar_remodel"]*m*e*f
        d_b=.074*k["progenitor_activation"]*g*gate((m,n,p,e),mode)*(1-f)*(1-b)-.012*k["progenitor_loss"]*b
        d_t=.18*k["organize"]*b*gate((n,p,e),mode)*(1-f)*(1-t)
        d_u=.029*k["dysregulate"]*g*(1-c)*(b+.10)-.017*c*u
        f,b,t,u=map(clamp,(f+d_f,b+d_b,t+d_t,u+d_u))
    return dict(organized_tissue_proxy=t,fibrosis_proxy=f,dysregulation_proxy=u)

def compute():
    data={}
    for mode in TOPOLOGIES:
        data[mode]={}
        for name in CASES:
            trials=[simulate(SCENARIOS[name],seed,mode) for seed in range(N)]
            data[mode][name]={key:round(statistics.mean([x[key] for x in trials]),5) for key in trials[0]}
    return dict(
        experiment_id="JANUS-REGEN-NEWTON-2026-11-09-E02",
        status="SYNTHETIC_NOT_BIOLOGICALLY_VALIDATED",
        cases=len(CASES),seeds_per_case=N,total_runs=N*len(CASES)*len(TOPOLOGIES),
        coupling_topologies=list(TOPOLOGIES),results=data,
        interpretation_limit="No evidence any coupling topology is biologically correct. Structural assumptions dominate some results.")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",default="janus_regeneration_E02_results.json")
    args=ap.parse_args()
    result=compute()
    with open(args.output,"w",encoding="utf-8") as f: json.dump(result,f,ensure_ascii=False,indent=2,sort_keys=True)
    print(json.dumps({"output":args.output,"total_runs":result["total_runs"],"couplings":list(TOPOLOGIES)}))
