#!/usr/bin/env python3
"""Reproduce toy scenario sensitivities. Not physical data, FEM or strength predictions."""
E_BC,t_BC,E_PLA,t_PLA,phi = 500.0,0.5,2000.0,0.8,0.35
K0 = E_BC*t_BC
KP = E_PLA*t_PLA*phi
D0 = E_BC*t_BC**3/12
DP = E_PLA*t_PLA**3*phi/12
scenarios = [
    ("BC_ONLY",0,0),
    ("BC_PLUS_NASA_MOBILE",.05,.01),
    ("BC_PLUS_NASA_PARTIAL_INTERLOCK",.25,.10),
    ("BC_PLUS_NASA_STRONG_LOCK",.75,.60),
    ("BC_PLUS_RIGID_LATTICE",.80,.85),
]
def normalized(q,b):
    return round((K0+q*KP)/K0,3),round((D0+b*DP)/D0,3)
for name,q,b in scenarios:
    print(name, *normalized(q,b))
for q in [0,.05,.25,.50,.75,1]:
    for b in [0,.01,.10,.30,.60,1]:
        assert all(v>=1 for v in normalized(q,b))
