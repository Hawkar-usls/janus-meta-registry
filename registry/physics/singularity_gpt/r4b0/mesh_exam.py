"""Frozen Richardson check and endpoint-resolution audit, no AMR."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"r4a2"))
from diagnostic_lib import run
P=json.loads((HERE/"protocol.json").read_text())
OUT=Path("r4b0-output");OUT.mkdir(exist_ok=True)
mode=sys.argv[1]
def write(n,d): (OUT/n).write_text(json.dumps(d,indent=2,allow_nan=False)+"\n")
def execute(cfg,A):
    r,x=run(A,cfg["r0"],cfg["w"],cfg["R"],cfg["n"],cfg["checkpoints"])
    return r,x
if mode=="fixed":
    cfg=P["fixed"];r,x=execute(cfg,cfg["A"]);np.savez_compressed(OUT/"trace.npz",trace=x)
    cp=r["checkpoints"][-1];p=cp["peak_compactness"]
    result={"case":r,"prediction":cfg["predicted_C"],"richardson_limit":cfg["richardson_limit"],"absolute_prediction_error":abs(p-cfg["predicted_C"]),"prediction_pass":abs(p-cfg["predicted_C"])<=cfg["C_tolerance"],"mass_budget_pass":cp["mass_drift"]<cfg["mass_budget"],"resolution_gate":cp["min_central_Ricci_length_over_h"]>=8,"class_agreement":r["status"]=="DISPERSAL_PROXY","cells_scaling_exponent":float(np.log2(cp["min_central_Ricci_length_over_h"]/10.366140822556378)),"reference_peak_Ricci_12288":1561.2975822765497}
elif mode.startswith("endpoint"):
    cfg=P["bracket"];i=int(mode[-1]);r,x=execute(cfg,cfg["A"][i]);np.savez_compressed(OUT/"trace.npz",trace=x);cp=r["checkpoints"][-1]
    result={"endpoint":i,"case":r,"mass_budget_pass":cp["mass_drift"]<cfg["mass_budget"],"resolution_gate":cp["min_central_Ricci_length_over_h"]>=cfg["min_cells"],"physical_threshold_established":False}
else:raise ValueError(mode)
result.update({"mode":mode,"amr_implemented":False,"scientific_hold":True,"production_changed":False,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest()})
write("result.json",result);print("R4B0_MESH_RESULT",json.dumps(result,allow_nan=False),flush=True)
