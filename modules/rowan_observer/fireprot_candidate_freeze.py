#!/usr/bin/env python3
"""JANUS Rowan external FireProt candidate selection, no outcome-label output.

This is a *retrospective public benchmark candidate*, not a true blind
experiment: public labels exist in the source archive. It cannot authorize
model promotion or Rowan credits.

Source selection is based only on identifier, sequence, variant, PDB, InterPro,
publication DOI and per-PDB count; ddG and dTm are explicitly forbidden in
authored artifacts. Pure deterministic SHA ordering precludes outcome filtering.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,io,json,re,zipfile
from pathlib import Path

ARCHIVE_SHA256="b1403d86b43307f3a7dfc95ff6b72386c64068e8be1191bc7685d37bc8d654b2"
PUBLISHED_ARCHIVE_MD5="25cf04760665946b54b768eb7b6dfd1d"
ARCHIVE_URL="https://zenodo.org/records/8169289"
ARCHIVE_DOI="10.5281/zenodo.8169289"
HOMOLOGUE_FREE="fireprot_upload/csvs/splits/fireprot_homologue_free.csv"
MIN_DOMAINS=10
MIN_VARIANTS=20
AA=set("ACDEFGHIKLMNPQRSTVWY")
BBC1="EVPFKVVAQFPYKSDYEDDLNFEKDQEIIVTSVEDAEWYFGEYQDSNGDVIEGIFPKSFVAVQG"
SELECTION_SEED="JANUS_ROWAN_FIREPROT_HF_v1_no_labels_2026-10-26"
FORBIDDEN={"ddg","dtm","label","target","fitness","measured_value","score","experiment_ddg","dg"}

class GateHold(ValueError): pass

def sha(x):return hashlib.sha256(x).hexdigest()

def canonical(obj):
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")

def rows_to_manifest(rows,structures):
    groups=collections.defaultdict(dict)
    group_info={}
    rejects=collections.Counter()
    for r in rows:
        pid=(r.get("pdb_id_corrected") or "").strip().upper()
        seq=(r.get("pdb_sequence") or "").strip().upper()
        wt=(r.get("wild_type") or "").strip().upper()
        alt=(r.get("mutation") or "").strip().upper()
        pos=(r.get("pdb_position") or "").strip()
        chain=(r.get("chain") or "").strip()
        doi=(r.get("publication_doi") or "").strip()
        uid=(r.get("uniprot_id") or "").strip()
        interpro=set(x.strip() for x in (r.get("interpro_families") or "").split("|") if x.strip())
        name="fireprot_upload/pdbs/"+pid+".pdb"
        if (not pid or name not in structures or not seq or len(seq)>400 or len(seq)<30
            or any(x not in AA for x in seq) or seq==BBC1):
            rejects["sequence_or_pdb"]+=1;continue
        if (len(wt)!=1 or len(alt)!=1 or wt not in AA or alt not in AA
            or wt==alt or not pos.isdecimal()):
            rejects["mutation"]+=1;continue
        pos=int(pos)
        if pos not in range(len(seq)) or seq[pos]!=wt:
            rejects["position_or_residue_mismatch"]+=1;continue
        if not doi or not uid or not interpro:
            rejects["provenance_incomplete"]+=1;continue
        if not chain:
            rejects["missing_chain"]+=1;continue
        variant=f"{wt}{pos+1}{alt}"
        key=(pos,wt,alt)
        item={"mutation":variant,"pdb_position_zero_based":pos,
              "wild_type_residue":wt,"mutant_residue":alt,
              "experiment_id":str(r.get("experiment_id") or ""),
              "publication_doi":doi}
        # Deterministic tie-breaking among repeat measurements, independent of outcome.
        old=groups[pid].get(key)
        if old is None or (item["publication_doi"],item["experiment_id"]) < (old["publication_doi"],old["experiment_id"]):
            groups[pid][key]=item
        info=group_info.get(pid)
        if info is None:
            group_info[pid]={"wt_sequence":seq,"uniprot_id":uid,"interpro":sorted(interpro),
                             "chain":chain,"pdb_member":name}
        elif info["wt_sequence"]!=seq or info["uniprot_id"]!=uid or info["chain"]!=chain:
            raise GateHold("MULTIPLE_WT_SEQUENCES_OR_UNIPROTS_"+pid)
    candidates=[]
    for pid,variants in groups.items():
        info=group_info[pid]
        if len(variants)<MIN_VARIANTS:continue
        candidates.append((pid,len(variants),info,set(info["interpro"]),variants))
    # No domain ranking by labels, outcomes, model scores, publications or pH.
    candidates.sort(key=lambda a:(-a[1],a[0]))
    selected=[]
    used_interpro=set()
    used_uniprot=set()
    used_sequences=set()
    for pid,n,info,families,variants in candidates:
        if families & used_interpro or info["uniprot_id"] in used_uniprot or info["wt_sequence"] in used_sequences:
            continue
        selected.append((pid,info,variants,n))
        used_interpro.update(families)
        used_uniprot.add(info["uniprot_id"])
        used_sequences.add(info["wt_sequence"])
        if len(selected)>=MIN_DOMAINS:break
    if len(selected)!=MIN_DOMAINS:raise GateHold("INSUFFICIENT_DISTINCT_PDB_FAMILIES")
    domains=[]
    for pid,info,variants,n in selected:
        salted=lambda k:sha((SELECTION_SEED+"|"+pid+"|"+str(k)).encode("utf8"))
        ranked=sorted(variants.items(),key=lambda kv:salted(kv[0]))
        fixed=sorted([x for _,x in ranked[:MIN_VARIANTS]],
                     key=lambda x:(x["pdb_position_zero_based"],x["mutant_residue"]))
        for v in fixed:
            i=v["pdb_position_zero_based"]
            if info["wt_sequence"][i]!=v["wild_type_residue"]:
                raise GateHold("SELECTED_VARIANT_RESIDUE_MISMATCH")
            mutant_sequence=(info["wt_sequence"][:i]+v["mutant_residue"]+info["wt_sequence"][i+1:])
            v["mutant_sequence_sha256"]=sha(mutant_sequence.encode("ascii"))
        member=info["pdb_member"]
        domains.append({
            "pdb_id":pid,"pdb_chain":info["chain"],
            "pdb_member":member,"pdb_member_sha256":sha(structures[member]),
            "uniprot_id":info["uniprot_id"],
            "interpro_families":info["interpro"],
            "wildtype_sequence":info["wt_sequence"],
            "wildtype_sha256":sha(info["wt_sequence"].encode("ascii")),
            "eligible_unique_variant_count":n,
            "frozen_variant_count":len(fixed),
            "variants":fixed
        })
    assert len(domains)==10 and sum(len(d["variants"]) for d in domains)==200
    return domains,dict(rejects),len(candidates)

def assert_no_outcomes(obj):
    if isinstance(obj,dict):
        for k,v in obj.items():
            if k.lower() in FORBIDDEN:raise GateHold("LABEL_FIELD_LEAK_"+k)
            assert_no_outcomes(v)
    if isinstance(obj,list):
        for v in obj:assert_no_outcomes(v)

def build(archive_bytes):
    if sha(archive_bytes)!=ARCHIVE_SHA256:
        raise GateHold("FIREPROT_ZENODO_SOURCE_SHA_DRIFT")
    import hashlib
    if hashlib.md5(archive_bytes).hexdigest()!=PUBLISHED_ARCHIVE_MD5:
        raise GateHold("FIREPROT_ZENODO_MD5_DRIFT")
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as z:
        if HOMOLOGUE_FREE not in z.namelist():
            raise GateHold("HOMOLOGUE_FREE_CSV_MISSING")
        raw=z.read(HOMOLOGUE_FREE)
        rdr=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        for key in ("pdb_sequence","pdb_id_corrected","pdb_position","wild_type","mutation","interpro_families","publication_doi"):
            if key not in (rdr.fieldnames or []):
                raise GateHold("REQUIRED_COLUMN_MISSING_"+key)
        # Values of ddG/dTm are NEVER exported, ranked, filtered or logged.
        rows=list(rdr)
        structures={n:z.read(n) for n in z.namelist() if n.lower().endswith(".pdb")}
    domains,rejected,candidate_count=rows_to_manifest(rows,structures)
    manifest={
        "schema_id":"janus.rowan.external_fireprot_label_quarantined_input.v1",
        "status":"FROZEN_PUBLIC_METADATA_ONLY_LABELS_NOT_PART_OF_INPUT",
        "honest_experiment_type":"RETROSPECTIVE_PUBLIC_DATASET_NOT_TRUE_BLIND_NO_INDEPENDENT_CUSTODIAN",
        "selection_date_utc":"2026-10-26",
        "source":{
            "name":"ThermoMPNN FireProt PDB Dataset",
            "doi":ARCHIVE_DOI,
            "zenodo_record":ARCHIVE_URL,
            "zip_name":"fireprot_upload.zip",
            "zip_sha256":ARCHIVE_SHA256,
            "zip_published_md5":PUBLISHED_ARCHIVE_MD5,
            "zip_licence":"NEEDS_REVIEW",
            "source_paper_doi":"10.1073/pnas.2314853121",
            "homologue_free_member":HOMOLOGUE_FREE,
            "homologue_free_member_sha256":sha(raw),
            "previous_Megascale_bbc1_source_not_reused":True,
            "homologue_free_provenance":"ThermoMPNN authors' MMseqs2 25-percent homology exclusion relative to their Megascale set, not independent Boltz2 contamination audit."
        },
        "selection":{
            "seed":SELECTION_SEED,
            "procedure":"Filter single canonical mutations whose positions match a 30..400-aa all-canonical PDB WT sequence with DOI and UniProt+InterPro+chain; dedupe variant by (position,WT,ALT), select first DOI/experiment lexicographically; sort eligible PDBs by decreasing variant count and PDB name; greedily choose 10 with disjoint InterPro family IDs and UniProt; choose 20 variants/PDB with SHA256(seed|pdb|(position,WT,ALT)) sorted; no outcome features.",
            "min_domains":MIN_DOMAINS,"variants_per_domain":MIN_VARIANTS,
            "min_total_variants":200,"eligible_domain_count":candidate_count,
            "source_row_rejection_counts":rejected,
            "no_label_based_selection":True,
            "source_metadata_not_a_substitute_for_new_experimental_blind_custodian":True
        },
        "units_and_sign":{
            "source_reported_ddG_definition":"mutant-minus-WT in dataset as labeled by curators",
            "source_unit":"kcal/mol",
            "source_sign_to_bbc1":"NOT_YET_ATTESTED_FOR_EACH_PRIMARY_ASSAY",
            "model_positive_sign":"stabilizing",
            "predeclared_sign_orientation_hypothesis":"ThermoMPNN usage convention: negative ΔΔG is stabilizing, so candidate mapping to positive-stabilizing is label_s2 = -ddG_source; MUST be verified against original curated experiment/definitions before scoring.",
            "heterogeneous_publication_methods":"REQUIRES_AUDIT"
        },
        "inference":{
            "frozen_shadow_model_path":"data/rowan/feedback/FEEDBACK-RUN40236409772-38e04b8f73a81a21.json",
            "frozen_shadow_model_sha256":"52e0d6e75d603f0596ac7938715e45fccaf38835fac0ed110176128e33d86cf3",
            "status":"NOT_RUN_NO_COMPARABLE_BOLTZ2_CONFIDENCE_FEATURES",
            "requirements":["same provider version and settings for WT and 200 mutants","all 210 structural confidence receipts pinned before any label unlock","no new Rowan credits, unless separately preapproved","no training, recalibration, or heldout adjustment"]
        },
        "safety":{
            "labels_in_input_manifest":False,
            "no_model_predictions_fabricated":True,
            "no_public_score_to_claim_true_blind":True,
            "boltz2_production_promotion":False,
            "new_rowan_jobs":0,
            "rowan_credits_spent":0
        },
        "domains":domains
    }
    # Unlike prediction receipt, source metadata records are not in themselves a scientific trial.
    assert_no_outcomes(manifest)
    return manifest

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--zip",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    try:
        if a.out.exists():raise GateHold("OUTPUT_ALREADY_EXISTS")
        manifest=build(a.zip.read_bytes())
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(json.dumps(manifest,indent=2,allow_nan=False)+"\n",encoding="utf8")
        print("JANUS_FIREPROT_INPUT_FREEZE=PASS_METADATA_ONLY")
        print("DOMAINS",len(manifest["domains"]))
        print("VARIANTS",sum(len(x["variants"]) for x in manifest["domains"]))
        print("PDB_IDS"," ".join(x["pdb_id"] for x in manifest["domains"]))
        return 0
    except (GateHold,ValueError,OSError) as e:
        print("JANUS_FIREPROT_INPUT_FREEZE=HOLD_"+str(e))
        return 2
if __name__=="__main__":raise SystemExit(main())
