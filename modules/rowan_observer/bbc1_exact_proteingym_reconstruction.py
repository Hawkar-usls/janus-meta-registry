#!/usr/bin/env python3
"""Exact BBC1 ProteinGym v1.0–v1.3 source-label reconstruction.

Group raw rows by terminal amino-acid sequence; mean ddG_ML_float per sequence;
drop the reference WT and binarize using the official metadata cutoff.
No ML fitting or Rowan API calls. All byte sources must match frozen identities.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,collections
from pathlib import Path

DMS_ID="BBC1_YEAST_Tsuboyama_2023_1TG0"
WT="EVPFKVVAQFPYKSDYEDDLNFEKDQEIIVTSVEDAEWYFGEYQDSNGDVIEGIFPKSFVAVQG"
EXPECTED_RAW_SHA256="d3003e040d984c0361da94a103c31fff4385498fdda36ff66480c3bdef19de2c"
EXPECTED_PROCESSED_SHA256="d258240a3ab7088f5ac331abf661611369d9a6a06cf7778ab4ae285b824cfdab"
EXPECTED_METADATA_GIT_BLOB_SHA="8d1ea9a19c0404b511cd24378b25c2a5f86f10e9"
EXPECTED_COUNT_RAW=2174
EXPECTED_COUNT_MUTANTS=2069
EXPECTED_CUTOFF="-1.271998543"
TOLERANCE=1e-10
EIGHT_MUTATIONS=("G53A","G48D","E27F","W38L","K13N","G64Q","Q44V","E42H")

class ReconciliationHold(ValueError):pass

def sha256(raw):
    return hashlib.sha256(raw).hexdigest()

def git_blob_sha(raw):
    return hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()

def numeric(v):
    try:v=float(v)
    except (ValueError,TypeError):raise ReconciliationHold("NON_NUMERIC_SCORE")
    if not math.isfinite(v):raise ReconciliationHold("NON_FINITE_SCORE")
    return v

def mutation_sequence(mut):
    n=int(mut[1:-1])-1
    if n not in range(len(WT)) or WT[n]!=mut[0]:raise ReconciliationHold("BAD_MUTATION_"+mut)
    return WT[:n]+mut[-1]+WT[n+1:]

def source_cutoff(metadata_bytes):
    if git_blob_sha(metadata_bytes)!=EXPECTED_METADATA_GIT_BLOB_SHA:
        raise ReconciliationHold("METADATA_BLOB_DRIFT")
    ref=[r for r in csv.DictReader(io.StringIO(metadata_bytes.decode("utf-8-sig")))
         if r.get("DMS_id")==DMS_ID]
    if len(ref)!=1:raise ReconciliationHold("METADATA_ASSAY_NOT_UNIQUE")
    row=ref[0]
    if (row.get("raw_DMS_phenotype_name")!="ddG_ML_float" or
        row.get("raw_DMS_directionality")!="1" or
        row.get("target_seq")!=WT or
        row.get("DMS_binarization_cutoff")!=EXPECTED_CUTOFF or
        row.get("DMS_binarization_method")!="median"):
        raise ReconciliationHold("METADATA_ASSAY_OR_TARGET_DRIFT")
    return numeric(row["DMS_binarization_cutoff"])

def reconstruct(raw_rows,processed_rows,cutoff):
    if not isinstance(raw_rows,list) or not isinstance(processed_rows,list):
        raise ReconciliationHold("ROWS_NOT_LISTS")
    byseq=collections.defaultdict(list)
    for r in raw_rows:
        seq=(r.get("aa_seq") or "").strip()
        if len(seq)!=64:raise ReconciliationHold("RAW_SEQUENCE_LENGTH_INVALID")
        byseq[seq].append({
            "original_mut_type":r.get("mut_type"),
            "original_name":r.get("name"),
            "ddG_ML_float":numeric(r.get("ddG_ML_float"))
        })
    if WT not in byseq:raise ReconciliationHold("WILDTYPE_MISSING")
    rows={}; aliases=[]; mismatched=[]; bad_bins=[]; direct_diffs=[]; missing_direct=[]; ambiguous_direct=[]
    sizes=collections.Counter()
    for r in processed_rows:
        mut=r.get("mutant")
        seq=r.get("mutated_sequence")
        if not isinstance(seq,str) or len(seq)!=64 or seq==WT:
            raise ReconciliationHold("BAD_PROCESSED_SEQUENCE_"+str(mut))
        if seq in rows:raise ReconciliationHold("DUPLICATED_PROCESSED_SEQUENCE")
        if not isinstance(mut,str) or not mut:raise ReconciliationHold("MUTANT_NAME_MISSING")
        if seq not in byseq:raise ReconciliationHold("PROCESSED_WITHOUT_RAW_"+mut)
        source=byseq[seq]
        mean=sum(x["ddG_ML_float"] for x in source)/len(source)
        expected=numeric(r.get("DMS_score"))
        error=expected-mean
        pred_bin=int(mean>=cutoff)
        try:provided_bin=int(r.get("DMS_score_bin"))
        except (TypeError,ValueError):raise ReconciliationHold("BIN_IS_NON_INTEGER")
        sizes[len(source)]+=1
        if abs(error)>TOLERANCE:mismatched.append((mut,error))
        if pred_bin!=provided_bin:bad_bins.append(mut)
        if len(source)>1:
            aliases.append({
                "mutant":mut,"sequence":seq,"n_raw_records":len(source),
                "raw_sources":source,"reconstructed_DMS_score":mean,
                "published_DMS_score":expected,
                "absolute_residual":abs(error)
            })
        direct=[x for x in source if x["original_mut_type"]==mut]
        if len(direct)==1:
            if abs(direct[0]["ddG_ML_float"]-expected)>TOLERANCE:
                direct_diffs.append(mut)
        elif not direct:missing_direct.append(mut)
        else:ambiguous_direct.append(mut)
        rows[seq]={"mutant":mut,"source_n":len(source),"predicted":mean,
                   "actual":expected,"DMS_score_bin":pred_bin}
    if mismatched:raise ReconciliationHold("MEAN_SCORE_RECONSTRUCTION_FAILED_"+str(mismatched[:3]))
    if bad_bins:raise ReconciliationHold("BINARY_SCORE_RECONSTRUCTION_FAILED_"+str(bad_bins[:3]))
    if set(rows)!=(set(byseq)-{WT}):
        raise ReconciliationHold("RAW_PROCESSED_SEQUENCE_SET_DIFFERENT")
    for mut in EIGHT_MUTATIONS:
        seq=mutation_sequence(mut)
        if seq not in rows or rows[seq]["mutant"]!=mut:
            raise ReconciliationHold("FROZEN_EIGHT_IDENTITY_DRIFT_"+mut)
    # Measured difference is explained by parallel raw constructs yielding same
    # final sequence. Do not infer that this is a biological effect.
    return {
        "schema_id":"janus.rowan.bbc1.exact_proteingym_source_reconstruction.v1",
        "status":"PASS_EXACT_REPRODUCTION_FOR_BBC1_V1_0_TO_V1_3",
        "method":"GROUP_BY_FULL_MUTATED_AMINO_ACID_SEQUENCE_MEAN_DDG_ML_FLOAT_EXCLUDE_WT",
        "formula":"DMS_score(sequence) = arithmetic mean of ddG_ML_float from all raw rows with identical aa_seq",
        "bin_rule":"DMS_score_bin = int(DMS_score >= reference DMS_binarization_cutoff)",
        "binarization_cutoff":cutoff,
        "original_raw_rows":len(raw_rows),
        "unique_raw_protein_sequences_including_wt":len(byseq),
        "wt_raw_records":len(byseq[WT]),
        "final_mutant_rows":len(rows),
        "all_numerical_scores_reproduced":len(rows),
        "all_binary_scores_reproduced":len(rows),
        "max_numeric_residual_tolerance":TOLERANCE,
        "multiplicity_distribution":{str(k):v for k,v in sorted(sizes.items())},
        "raw_sequence_duplicates_with_different_constructs":aliases,
        "alias_group_count":len(aliases),
        "earlier_exact_mut_type_comparison_numeric_differences":len(direct_diffs),
        "earlier_exact_mut_type_comparison_no_direct":len(missing_direct),
        "earlier_exact_mut_type_comparison_ambiguous_direct":len(ambiguous_direct),
        "earlier_diff_mutations":direct_diffs,
        "missing_direct_mutations":missing_direct,
        "ambiguous_direct_mutations":ambiguous_direct,
        "frozen_eight_summary":[{
            "mutant":mut,
            "n_raw_records":rows[mutation_sequence(mut)]["source_n"],
            "reconstructed_label":rows[mutation_sequence(mut)]["predicted"],
            "published_label":rows[mutation_sequence(mut)]["actual"],
            "raw_aliases":byseq[mutation_sequence(mut)]
        } for mut in EIGHT_MUTATIONS],
        "lineage_interpretation":"Independent reproduction of published ProteinGym BBC1 processed values, not authenticated original internal preprocessing source code.",
        "science_controls":{
            "source_reconciliation_for_BBC1":"PASS_NUMERIC_AND_BIN",
            "external_independent_blind_validation":"NOT_PERFORMED",
            "S2_frozen_train_and_holdout":"UNCHANGED",
            "boltz2_production_promotion":False,
            "new_rowan_jobs_authorized":False,
            "new_rowan_credits_spent":0,
        }
    }

def verify_files(raw_bytes,processed_bytes,metadata_bytes):
    if sha256(raw_bytes)!=EXPECTED_RAW_SHA256:raise ReconciliationHold("RAW_SHA256_DRIFT")
    if sha256(processed_bytes)!=EXPECTED_PROCESSED_SHA256:raise ReconciliationHold("PROCESSED_SHA256_DRIFT")
    cutoff=source_cutoff(metadata_bytes)
    raw_reader=csv.DictReader(io.StringIO(raw_bytes.decode("utf-8-sig")))
    proc_reader=csv.DictReader(io.StringIO(processed_bytes.decode("utf-8-sig")))
    if not {"aa_seq","ddG_ML_float","mut_type","name"} <= set(raw_reader.fieldnames or []):
        raise ReconciliationHold("RAW_SCHEMA_DRIFT")
    if not {"mutated_sequence","mutant","DMS_score","DMS_score_bin"} <= set(proc_reader.fieldnames or []):
        raise ReconciliationHold("PROCESSED_SCHEMA_DRIFT")
    raw=list(raw_reader);proc=list(proc_reader)
    if len(raw)!=EXPECTED_COUNT_RAW or len(proc)!=EXPECTED_COUNT_MUTANTS:
        raise ReconciliationHold("SOURCE_ROW_COUNT_DRIFT")
    output=reconstruct(raw,proc,cutoff)
    output["sources"]={
        "official_repository":"https://github.com/OATML-Markslab/ProteinGym",
        "reference_csv_git_blob_sha":EXPECTED_METADATA_GIT_BLOB_SHA,
        "raw_source_url":"https://marks.hms.harvard.edu/proteingym/ProteinGym_v1.3/substitutions_raw_DMS.zip",
        "raw_archive_member":"substitutions_raw_DMS/BBC1_YEAST_Tsuboyama_2023_1TG0.csv",
        "raw_member_sha256":EXPECTED_RAW_SHA256,
        "processed_source_url":"https://marks.hms.harvard.edu/proteingym/ProteinGym_v1.3/DMS_ProteinGym_substitutions.zip",
        "processed_archive_member":"DMS_ProteinGym_substitutions/BBC1_YEAST_Tsuboyama_2023_1TG0.csv",
        "processed_member_sha256":EXPECTED_PROCESSED_SHA256,
        "original_Tsuboyama_Zenodo":"https://zenodo.org/records/7992926",
        "author_full_zip_MD5_independently_verified":False
    }
    if (output["alias_group_count"]!=97 or
        output["multiplicity_distribution"]!={"1":1972,"2":97} or
        output["earlier_exact_mut_type_comparison_numeric_differences"]!=96 or
        output["earlier_exact_mut_type_comparison_no_direct"]!=10 or
        output["earlier_exact_mut_type_comparison_ambiguous_direct"]!=1 or
        output["wt_raw_records"]!=8):
        raise ReconciliationHold("COUNT_SIGNATURE_DRIFT")
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--raw-csv",type=Path,required=True)
    p.add_argument("--processed-csv",type=Path,required=True)
    p.add_argument("--metadata-csv",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        if args.output.exists():raise ReconciliationHold("OUTPUT_EXISTS")
        result=verify_files(args.raw_csv.read_bytes(),
                            args.processed_csv.read_bytes(),
                            args.metadata_csv.read_bytes())
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        print("BBC1_SOURCE_RECONSTRUCTION="+result["status"])
        print("RECONSTRUCTED="+str(result["final_mutant_rows"])+"/2069")
        print("ALIAS_GROUPS="+str(result["alias_group_count"]))
        print("PREVIOUS_96_DIFFS_RESOLVED="+str(result["earlier_exact_mut_type_comparison_numeric_differences"]))
        return 0
    except (OSError,ValueError,ReconciliationHold) as e:
        print("BBC1_SOURCE_RECONSTRUCTION=HOLD_"+str(e))
        return 2

if __name__=="__main__":raise SystemExit(main())
