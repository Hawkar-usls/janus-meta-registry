#!/usr/bin/env python3
"""JANUS synthetic regeneration E01: ABSTRACT model, NOT human physiology.

Zero external dependencies. 11 presets x 256 paired seeded simulations.
Ticks, parameters, outputs are dimensionless. Does not model actual tissue,
tumors, treatments, or probabilities of human regeneration.
"""
import json, random, statistics, math, hashlib, argparse

VERSION="1.0.0"
N=256
STEPS=100
SCENARIOS={
 "human_scarring_like": dict(immune=.32,nerve=.67,pattern=.24,matrix=.36,progenitor_drive=.52,growth_brake=.94),
 "matrix_only": dict(immune=.32,nerve=.67,pattern=.24,matrix=.82,progenitor_drive=.52,growth_brake=.94),
 "immune_matrix": dict(immune=.78,nerve=.67,pattern=.24,matrix=.82,progenitor_drive=.52,growth_brake=.94),
 "pattern_only": dict(immune=.32,nerve=.67,pattern=.84,matrix=.36,progenitor_drive=.52,growth_brake=.94),
 "progenitor_only": dict(immune=.32,nerve=.67,pattern=.24,matrix=.36,progenitor_drive=.86,growth_brake=.94),
 "combined_bounded": dict(immune=.82,nerve=.86,pattern=.86,matrix=.84,progenitor_drive=.72,growth_brake=.92),
 "ablate_immune": dict(immune=.08,nerve=.86,pattern=.86,matrix=.84,progenitor_drive=.72,growth_brake=.92),
 "ablate_nerve": dict(immune=.82,nerve=.08,pattern=.86,matrix=.84,progenitor_drive=.72,growth_brake=.92),
 "ablate_pattern": dict(immune=.82,nerve=.86,pattern=.08,matrix=.84,progenitor_drive=.72,growth_brake=.92),
 "ablate_matrix": dict(immune=.82,nerve=.86,pattern=.86,matrix=.08,progenitor_drive=.72,growth_brake=.92),
 "unbounded_growth": dict(immune=.82,nerve=.86,pattern=.86,matrix=.84,progenitor_drive=.98,growth_brake=.10),
}
DOIS=[
 "10.1073/pnas.1300290110",
 "10.1016/j.devcel.2024.05.002",
 "10.1038/s41467-025-59497-5",
 "10.1038/s41536-025-00441-y",
 "10.1016/j.mtbio.2025.102443",
 "10.1038/s41536-026-00461-2",
]
def clamp(x):
    return max(0.,min(1.,x))

def run(params,seed):
    r=random.Random(seed)
    keys=("scar_form","scar_remodel","progenitor_activation","progenitor_loss","organize","dysregulate")
    k={name:r.uniform(.78,1.22) for name in keys}
    f,b,t,u=.09,.07,.03,0.
    for _ in range(STEPS):
        m,n,p,e,g,c=[params[x] for x in ("immune","nerve","pattern","matrix","progenitor_drive","growth_brake")]
        # ASSUMPTION BY CONSTRUCTION: cooperative multiplicative factors.
        d_f=.020*k["scar_form"]*(1-t)*(1-.72*m)*(1-.55*e)-.027*k["scar_remodel"]*m*e*f
        d_b=.074*k["progenitor_activation"]*g*m*n*p*e*(1-f)*(1-b)-.012*k["progenitor_loss"]*b
        d_t=.18*k["organize"]*b*n*p*e*(1-f)*(1-t)
        d_u=.029*k["dysregulate"]*g*(1-c)*(b+.10)-.017*c*u
        f,b,t,u=map(clamp,(f+d_f,b+d_b,t+d_t,u+d_u))
    return dict(organized_tissue_proxy=t,fibrosis_proxy=f,progenitor_proxy=b,
                dysregulation_proxy=u,net_index=t-.5*f-u)

def summary(vals):
    mean=statistics.mean(vals)
    sd=statistics.stdev(vals)
    return dict(mean=round(mean,5),sd=round(sd,5),min=round(min(vals),5),
                max=round(max(vals),5),mc_sem=round(sd/math.sqrt(len(vals)),6))

def compute():
    all_runs={name:[run(params,seed) for seed in range(N)] for name,params in SCENARIOS.items()}
    metrics=("organized_tissue_proxy","fibrosis_proxy","progenitor_proxy","dysregulation_proxy","net_index")
    totals={name:{m:summary([r[m] for r in vals]) for m in metrics} for name,vals in all_runs.items()}
    baseline=all_runs["human_scarring_like"]
    paired={name:{m:summary([b[m]-a[m] for a,b in zip(baseline,vals)]) for m in metrics}
            for name,vals in all_runs.items() if name!="human_scarring_like"}
    checks=dict(deterministic_replay=run(SCENARIOS["combined_bounded"],23)==run(SCENARIOS["combined_bounded"],23),
                states_bounded=all(0<=r[m]<=1 for vals in all_runs.values() for r in vals for m in metrics[:-1]),
                ablations_reduce_organized_tissue_in_this_model=all(
                  totals[name]["organized_tissue_proxy"]["mean"]<totals["combined_bounded"]["organized_tissue_proxy"]["mean"]
                  for name in ("ablate_immune","ablate_nerve","ablate_pattern","ablate_matrix")),
                lower_growth_brake_increases_dysregulation_in_this_model=
                  totals["unbounded_growth"]["dysregulation_proxy"]["mean"]>
                  totals["combined_bounded"]["dysregulation_proxy"]["mean"])
    return dict(
      schema="janus.synthetic_regeneration_model_result.v1", experiment_id="JANUS-REGEN-NEWTON-2026-11-09-E01",
      status="SYNTHETIC_EXECUTED_NOT_BIOLOGICALLY_VALIDATED",model_version=VERSION,
      mathematical_time_ticks=STEPS,samples_per_scenario=N,total_runs=N*len(SCENARIOS),
      scenario_params=SCENARIOS,parameter_heterogeneity="Six independent uniform multipliers [0.78,1.22], paired by seed across scenarios",
      initial_states=dict(fibrosis=.09,progenitor=.07,organized_tissue=.03,dysregulation=0),
      summaries=totals,paired_difference_vs_human_scarring_like=paired,internal_checks=checks,
      literature_dois=DOIS,
      interpretation="Dimensionless toy results ONLY. No quantitative applicability to human tissues or therapies. Equations impose cooperation by construction.",
      caveats=[
         "Neither quantitative parameters nor time are biologically calibrated.",
         "Regenerative index is not a percentage of a human organ or a probability.",
         "Dysregulation penalty is not clinical tumor risk.",
         "Synthetic seed variability is not biological uncertainty.",
         "An apparent synergy here is a consequence partly encoded in model equations.",
         "No humans, animals, genome edits or wet-lab interventions were used."
      ])

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",default="janus_regeneration_E01_results.json")
    args=ap.parse_args()
    payload=compute()
    data=json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    with open(args.output,"w",encoding="utf-8") as f:
        f.write(data)
    print(json.dumps(dict(file=args.output,sha256=hashlib.sha256(data.encode()).hexdigest(),
                          checks=payload["internal_checks"],
                          summary={k:{m:v[m]["mean"] for m in ("organized_tissue_proxy","fibrosis_proxy","dysregulation_proxy")}
                                   for k,v in payload["summaries"].items()}),indent=2))
