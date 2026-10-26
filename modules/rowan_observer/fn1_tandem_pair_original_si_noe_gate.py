#!/usr/bin/env python3
"""Read-only, no-inference audit of original Smith et al 2000 FNII tandem NMR SI.

Only a *small manually checked subset* of experimental 15N relaxation and
1H-15N heteronuclear NOE data is retained in the registry. Does not redistribute
copyrighted original PDF; use its frozen figshare URL and MD5/SHA256 to inspect.

This NOE is a local NH *dynamics* observable, NOT a two-proton NOESY distance
constraint. It cannot identify a unique interdomain 3D orientation.
"""
from __future__ import annotations
from decimal import Decimal
from pathlib import Path
from collections import Counter
import hashlib
import json
import sys

SOURCE=Path(__file__).resolve().parents[2]/"data/rowan/provenance/ROWAN-FN1-ISOLATED-FNII-PAIR-SMITH2000-ORIGINAL-15N-SI-2026-10-26-v1.json"
AA3={"Ser":"S","Asn":"N","Gly":"G","Glu":"E","Pro":"P","Cys":"C","Val":"V","Leu":"L","Phe":"F","Thr":"T","Tyr":"Y","Arg":"R","Gln":"Q","Asp":"D","His":"H","Trp":"W","Lys":"K","Met":"M","Ile":"I","Ala":"A"}
LINK={61,62,63,64,66,69}
CORE={52,53,70,71}
MISSING={59,60,65,67,68}

class Hold(ValueError): pass

def D(value):
    if isinstance(value,bool):
        raise Hold("INVALID_BOOL_NUMBER")
    return Decimal(str(value))

def avg(arr):
    return sum((D(x) for x in arr),Decimal("0"))/len(arr)

def q(value):
    return format(value.quantize(Decimal("0.000001")),"f")

def run(obj):
    if obj.get("schema_id")!="janus.rowan.fn1_isolated_fnii_pair_original_author_supplement_relaxation_2000.v1":
        raise Hold("SOURCE_SCHEMA_DRIFT")
    a=obj["archived_author_supplement"]
    if (a["publisher_supplied_md5"]!="9688224d4c5e395bc233fb10972417b2"
        or a["independently_computed_md5"]!=a["publisher_supplied_md5"]
        or a["independently_computed_sha256"]!="b426ae59845e3bc944dc968619911ef99d59a54e1b5ca8020ea9027caa103f3e"
        or a["file_size_bytes"]!=189468 or a["figshare_file_id"]!=5670336):
        raise Hold("ORIGINAL_PUBLISHER_PDF_HASH_OR_SIZE_DRIFT")
    seq=obj["exact_target_mapping"]["modeled_FN1_sequence"]
    if len(seq)!=109 or hashlib.sha256(seq.encode("ascii")).hexdigest()!=obj["exact_target_mapping"]["modeled_sequence_sha256"]:
        raise Hold("FN1_109AA_SOURCE_IDENTITY_DRIFT")
    rows=obj["selected_real_rows_table_III"]
    if len(rows)!=10:
        raise Hold("SELECTED_SOURCE_ROW_COUNT_DRIFT")
    indices=[r["si_residue"] for r in rows]
    if len(set(indices))!=len(indices) or set(indices)!=(LINK|CORE):
        raise Hold("SOURCE_ROW_IDENTITY_OR_PRESPECIFIED_SELECTION_DRIFT")
    if set(obj["quantitative_scope"]["available_linker_residue_set_author_indices"])!=LINK:
        raise Hold("OBSERVED_LINKER_SET_DRIFT")
    if set(obj["quantitative_scope"]["not_reported_linker_author_indices"])!=MISSING:
        raise Hold("MISSING_LINKER_SET_DRIFT")
    if set(obj["quantitative_scope"]["flanking_core_indices_author"])!=CORE:
        raise Hold("CORE_REFERENCE_SET_DRIFT")
    for r in rows:
        si=r["si_residue"]
        model_pos=si-9
        if not 1<=model_pos<=109 or seq[model_pos-1]!=AA3.get(r["residue"]):
            raise Hold("SI_TO_ROWAN_EXACT_SEQUENCE_MAP_FAILED_"+str(si))
        if (si in LINK)!=(r["category"]=="OBSERVED_INTERDOMAIN_LINKER"):
            raise Hold("FROZEN_DOMAIN_CATEGORY_DRIFT_"+str(si))
        if si in {52,53} and r["category"]!="FIRST_FNII_CORE_NEAR_LINKER":
            raise Hold("FIRST_FNII_CORE_CATEGORY_DRIFT")
        if si in {70,71} and r["category"]!="SECOND_FNII_CORE_NEAR_LINKER":
            raise Hold("SECOND_FNII_CORE_CATEGORY_DRIFT")
        if D(r["T1_ms"])<=0 or D(r["T2_ms"])<=0 or D(r["NOE_uncertainty"])<=0 or not Decimal("-2")<D(r["het_NOE"])<Decimal("2"):
            raise Hold("INVALID_EXPERIMENTAL_RELAXATION_ENTRY")
    linker=[D(r["het_NOE"]) for r in rows if r["si_residue"] in LINK]
    core=[D(r["het_NOE"]) for r in rows if r["si_residue"] in CORE]
    first_two=[D(r["het_NOE"]) for r in rows if r["si_residue"] in {61,62}]
    linker_sorted=sorted(linker)
    return {
       "schema_id":"janus.rowan.fn1_isolated_fnii_original_author_si_subset_noe_descriptive_zero_credit_v1",
       "source_doi":"10.1021/bi000427i.s001",
       "source_archive_url":"https://acs.figshare.com/articles/journal_contribution/3584433",
       "source_pdf_sha256":a["independently_computed_sha256"],
       "source_page_indices_1based":[3,4],
       "status":"PASS_MANUALLY_VERIFIED_ORIGINAL_NMR_SI_SELECTED_DATA_AUDIT",
       "NMR_observable":"steady_state_heteronuclear_1H_15N_NOE_ratio_not_1H_1H_distance_NOE",
       "rowan_seq_to_table_III":"SI_author_residue_one_based = Rowan_predicted_109aa_one_based + 9",
       "linker_11_residues_model_positions_one_based":[50,60],
       "linker_observed_author_residues":sorted(LINK),
       "linker_missing_author_residues":sorted(MISSING),
       "linker_NOE_observed_count":len(linker),
       "linker_NOE_mean":q(avg(linker)),
       "linker_NOE_median":q((linker_sorted[2]+linker_sorted[3])/2),
       "linker_NOE_min":q(min(linker)),
       "linker_NOE_max":q(max(linker)),
       "Val61_Leu62_mean_NOE":q(avg(first_two)),
       "flanking_four_NOE_mean":q(avg(core)),
       "flanking_author_residue_indices":sorted(CORE),
       "posthoc_subset_only":True,
       "not_full_relaxation_table":True,
       "no_significance_inference":True,
       "NOE_cannot_define_interdomain_distance_or_unique_angle":True,
       "new_rowan_jobs":0,"new_rowan_credits":0,
       "source_figshare_pdf_republished":False,
       "no_training_or_model_promotion":True
    }

def main():
    try:
        data=json.loads(SOURCE.read_text(encoding="utf8"))
        print(json.dumps(run(data),indent=2,sort_keys=True,allow_nan=False))
        return 0
    except Hold as e:
        print("JANUS_FN1_SI=HOLD_"+str(e))
        return 2
    except Exception:
        print("JANUS_FN1_SI=HOLD_UNEXPECTED_DATA_ERROR")
        return 3

if __name__=="__main__":
    sys.exit(main())
