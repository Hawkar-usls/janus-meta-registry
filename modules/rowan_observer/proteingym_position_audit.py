#!/usr/bin/env python3
"""Offline full-BBC1 comparison: OFFICIAL processed ProteinGym vs RAW mirror.

Never calls Rowan, modifies weights or retroactively redefines S2 test targets.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,collections,math,statistics,zipfile
from pathlib import Path
PROCESSED_ARCHIVE_SHA="3a83766254ac9ac9984ec25cb73c6e010ea4418f5e35f143933e6b6e6473b921"
PROCESSED_ENTRY_SHA="d258240a3ab7088f5ac331abf661611369d9a6a06cf7778ab4ae285b824cfdab"
MIRROR_SHA="72621b29b9ea84e89cabc97c5854ce9a6de19a9a517fd1f6414f250156d4de03"
ASSAY="BBC1_YEAST_Tsuboyama_2023_1TG0"
REFERENCE_ENTRY="DMS_ProteinGym_substitutions/"+ASSAY+".csv"
RAW_MIRROR_COMMIT="b8319fa062ed22d86b329cddd40418234df7f1d8"
class GateHold(ValueError):pass
def sha(raw):return hashlib.sha256(raw).hexdigest()
def groups_from_raw(raw_text):
    groups=collections.defaultdict(list)
    for raw in raw_text.splitlines():
        if not raw:continue
        record=json.loads(raw)
        if record.get("dataset_id")!="proteingym_raw":raise GateHold("RAW_MIRROR_DATASET_ID_DRIFT")
        row=record.get("row",{})
        if not isinstance(row,dict):raise GateHold("RAW_MIRROR_INVALID_ROW")
        mut=row.get("mut_type")
        if isinstance(mut,str):
            groups[mut].append(row)
    return groups
def compare(processed_rows,raw_rows):
    raw_groups=groups_from_raw(raw_rows)
    n_match=n_diff=0;missing=[];multi=[];differences=[]
    for p in processed_rows:
        matched=[x for x in raw_groups.get(p["mutant"],[])
            if x.get("aa_seq")==p.get("mutated_sequence")]
        if not matched:
            missing.append(p["mutant"]);continue
        if len(matched)!=1:
            multi.append(p["mutant"]);continue
        try:
            before=float(matched[0]["ddG_ML_float"])
            after=float(p["DMS_score"])
        except (ValueError,KeyError,TypeError):raise GateHold("SCORE_NOT_NUMERIC")
        if not math.isfinite(before) or not math.isfinite(after):raise GateHold("NONFINITE_SCORE")
        diff=after-before
        if abs(diff)<=1e-9:n_match+=1
        else:
            n_diff+=1
            m=p["mutant"]
            pos="".join(x for x in m if x.isdigit())
            differences.append({"mutation":m,"position":int(pos) if pos else None,
                "processed":after,"raw":before,"processed_minus_raw":diff})
    counter=collections.Counter(x["position"] for x in differences)
    if n_match+n_diff+len(missing)+len(multi)!=len(processed_rows):
        raise GateHold("COUNT_ACCOUNTING_DRIFT")
    return {
        "schema_id":"janus.rowan.bbc1.proteingym_processed_raw_full_position_audit.v1",
        "status":"HOLD_NONTRIVIAL_POSITION_SPECIFIC_SCORE_DIFFERENCES" if n_diff else "MATCHED",
        "assay_id":ASSAY,
        "official_processed_archive_url":"https://marks.hms.harvard.edu/proteingym/ProteinGym_v1.3/DMS_ProteinGym_substitutions.zip",
        "official_processed_archive_sha256":PROCESSED_ARCHIVE_SHA,
        "official_processed_entry_path":REFERENCE_ENTRY,
        "official_processed_entry_sha256":PROCESSED_ENTRY_SHA,
        "raw_mirror_revision":RAW_MIRROR_COMMIT,
        "raw_mirror_sha256":MIRROR_SHA,
        "processed_rows":len(processed_rows),"matching":n_match,
        "different_numeric":n_diff,"missing_exact_sequence":len(missing),
        "ambiguous_multiple_raw_matches":len(multi),
        "missing_mutations":missing,"ambiguous_mutations":multi,
        "numeric_difference_positions":{str(k):v for k,v in sorted(counter.items())},
        "difference_absolute_median":statistics.median(abs(x["processed_minus_raw"]) for x in differences) if differences else None,
        "difference_absolute_max":max(abs(x["processed_minus_raw"]) for x in differences) if differences else None,
        "W38L":next((x for x in differences if x["mutation"]=="W38L"),None),
        "discrepant_rows":differences,
        "biological_mechanism_proven":False,
        "processing_transformation_algorithm_identified":False,
        "new_rowan_jobs":0,"new_rowan_credits":0,"model_weights_changed":False,
    }
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--official-zip",required=True,type=Path)
    ap.add_argument("--raw-mirror-jsonl",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    try:
        if a.output.exists():raise GateHold("IMMUTABLE_OUTPUT_EXISTS")
        if sha(a.official_zip.read_bytes())!=PROCESSED_ARCHIVE_SHA:
            raise GateHold("OFFICIAL_ZIP_SHA_DRIFT")
        raw=a.raw_mirror_jsonl.read_bytes()
        if sha(raw)!=MIRROR_SHA:raise GateHold("RAW_MIRROR_SHA_DRIFT")
        with zipfile.ZipFile(a.official_zip) as z:
            content=z.read(REFERENCE_ENTRY)
        if sha(content)!=PROCESSED_ENTRY_SHA:raise GateHold("OFFICIAL_BBC1_ENTRY_SHA_DRIFT")
        rdr=csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        output=compare(list(rdr),raw.decode("utf-8-sig"))
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(output,indent=2,allow_nan=False)+"\n",encoding="utf8")
        print("ROWAN_POSITION_AUDIT="+output["status"])
        for key in ("processed_rows","matching","different_numeric","missing_exact_sequence","ambiguous_multiple_raw_matches"):
            print(key+"="+str(output[key]))
        print("POSITION_COUNTS="+json.dumps(output["numeric_difference_positions"]))
        return 2 if output["status"].startswith("HOLD") else 0
    except (GateHold,OSError,ValueError,KeyError) as ex:
        print("ROWAN_POSITION_AUDIT=HOLD_"+str(ex))
        return 2
if __name__=="__main__":raise SystemExit(main())
