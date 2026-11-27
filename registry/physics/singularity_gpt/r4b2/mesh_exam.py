"""Second preregistered uniform-grid prediction, no AMR."""
import json,sys,hashlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"r4a2"))
from diagnostic_lib import run
P=json.loads((HERE/"protocol.json").read_text());c=P["fixed"]
OUT=Path("r4b2-output");OUT.mkdir(exist_ok=True)
r,x=run(c["A"],c["r0"],c["w"],c["R"],c["n"],c["checkpoints"]);q=r["checkpoints"][-1];ref=P["reference"]
result={"case":r,"C_prediction":c["C_prediction"],"C_error":abs(q["peak_compactness"]-c["C_prediction"]),"C_gate":abs(q["peak_compactness"]-c["C_prediction"])<=c["C_absolute_tolerance"],"R_prediction_conditional":c["R_prediction_conditional_second_order"],"R_relative_prediction_error":abs(q["max_central_abs_Ricci"]-c["R_prediction_conditional_second_order"])/c["R_prediction_conditional_second_order"],"R_relative_change_from_24576":abs(q["max_central_abs_Ricci"]-ref["R"])/ref["R"],"mass_gate":q["mass_drift"]<c["mass_budget"],"resolution_gate":q["min_central_Ricci_length_over_h"]>=c["min_cells"],"observed_cells_exponent":float(np.log2(q["min_central_Ricci_length_over_h"]/ref["cells"])),"scientific_hold":True,"amr_implemented":False,"production_changed":False,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest()}
result["R_gate"]=result["R_relative_prediction_error"]<=c["R_prediction_relative_tolerance"]
(OUT/"result.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n");np.savez_compressed(OUT/"trace.npz",trace=x)
print("R4B2_MESH_RESULT",json.dumps(result,allow_nan=False),flush=True)
