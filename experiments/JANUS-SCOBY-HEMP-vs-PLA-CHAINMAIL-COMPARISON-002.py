#!/usr/bin/env python3
"""JANUS numerical scenario, not a material or ballistics model.

Reproduces:
 experiments/JANUS-SCOBY-HEMP-vs-PLA-CHAINMAIL-COMPARISON-002-2026-11-03.json
The old thickness is UNKNOWN; 1.3 mm is assumed only to compare envelopes.
Strength (MPa), puncture, impact and protective rating are NOT simulated.
"""
from itertools import product
import json

P = dict(Ebc=500, tbc=0.5, rhobc=1.5,
         Epla=2000, tpla=0.8, rhopla=1.24, phi=0.35,
         Eold=13000, rhoold=1.45, told=1.3)

def axial(q, Ebc=None, Epla=None):
    Ebc = P["Ebc"] if Ebc is None else Ebc
    Epla = P["Epla"] if Epla is None else Epla
    return Ebc*P["tbc"] + q*Epla*P["tpla"]*P["phi"]

def bend(b):
    return (P["Ebc"]*P["tbc"]**3 +
            b*P["Epla"]*P["tpla"]**3*P["phi"]) / 12

old_mass = P["rhoold"]*P["told"]
new_mass = P["rhobc"]*P["tbc"] + P["rhopla"]*P["tpla"]*P["phi"]
old_axial = P["Eold"]*P["told"]
old_bend = P["Eold"]*P["told"]**3/12
scenarios = [("MOBILE",.05,.01),("PARTIAL_INTERLOCK",.25,.1),
             ("LOCKED",.75,.6),("RIGID_GRID_CONTROL",.8,.85)]
rows = []
for name,q,b in scenarios:
    k,d = axial(q),bend(b)
    rows.append(dict(id=name,q=q,b=b,K_N_per_mm=round(k,6),
                     D_Nmm=round(d,6),K_over_old=round(k/old_axial,4),
                     D_over_old=round(d/old_bend,4)))
grid = [axial(q,ebc,epla)
        for ebc,epla,q in product([428,500,3000,13000,18600],
                                 [750,2000,2400],[0,.05,.25,.75,1])]
assert len(grid) == 75
assert round(new_mass,4) == 1.0972 and round(old_mass,3) == 1.885
assert rows[1]["K_N_per_mm"] == 390
assert round((1-new_mass/old_mass)*100,2) == 41.79
assert [r["K_N_per_mm"] for r in rows] == sorted(r["K_N_per_mm"] for r in rows)
assert [r["D_Nmm"] for r in rows] == sorted(r["D_Nmm"] for r in rows)
print(json.dumps({
    "status":"SCENARIO_ONLY_NOT_VALIDATED",
    "old":{"mass_kg_per_m2":old_mass,"K_N_per_mm":old_axial,"D_Nmm":old_bend},
    "new":{"mass_kg_per_m2":new_mass,"mass_reduction_percent":round((1-new_mass/old_mass)*100,2)},
    "cases":rows,"sensitivity":{"n":len(grid),"min_K":min(grid),"max_K":max(grid)},
    "not_measured":["tensile strength","impact","puncture","ballistics","SCOBY growth"]
},indent=2,ensure_ascii=False))
