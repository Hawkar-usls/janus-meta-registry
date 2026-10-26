#!/usr/bin/env python3
"""Fail-closed PDB coordinate & sequence identity for frozen FireProt 10x20.

No ddG / dTm / experimental outcome columns are opened, parsed or exported.
This is a SOURCE IDENTITY preflight only, not protein-stability validation.
Original author PDB parser reference:
Kuhlman-Lab/ThermoMPNN/protein_mpnn_utils.py parse_PDB_biounits,
and preprocessing/2_seqalign_fireprot_dataset.py.
Raw ATOM residues within each chain are expanded through missing integer
residue numbers with X placeholders; chains concatenate in author order.
Uncertain chain, insertion code or sequence identity => HOLD, not auto-fix.
"""
from __future__ import annotations
import argparse,hashlib,io,json,re,zipfile
from collections import defaultdict
from pathlib import Path

MANIFEST_SHA256="9a44fd6c01afca2b21990b0f4364cb3dbf89ad61686295f55005f86001ce7b92"
ARCHIVE_SHA256="b1403d86b43307f3a7dfc95ff6b72386c64068e8be1191bc7685d37bc8d654b2"
ARCHIVE_MD5="25cf04760665946b54b768eb7b6dfd1d"
PDB_ID_RE=re.compile(r"^[A-Z0-9]{4}$")
AA3=dict(zip("ALA ARG ASN ASP CYS GLU GLN GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL".split(),
             "A R N D C E Q G H I L K M F P S T W Y V".split()))
# FireProt authors treat this HETATM as ATOM MET.
AA3["MSE"]="M"
AUTHOR_CHAIN_ORDER="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
class IdentityHold(ValueError):pass
def digest(b):return hashlib.sha256(b).hexdigest()

def extract_pdb_sequences(pdb_bytes):
    """Non-executable fixed-column PDB text parser, finite and source constrained."""
    if len(pdb_bytes)>5_000_000:raise IdentityHold("PDB_MEMBER_TOO_LARGE")
    chains=defaultdict(dict)
    residues=defaultdict(set)
    insertion_codes=defaultdict(set)
    seen_models=0
    for ln in pdb_bytes.decode("utf-8",errors="replace").splitlines():
        if ln.startswith("MODEL"):
            seen_models+=1
            if seen_models>1:break
        if ln.startswith("ENDMDL"):break
        if not (ln.startswith("ATOM  ") or (ln.startswith("HETATM") and ln[17:20]=="MSE")):
            continue
        if len(ln)<27:raise IdentityHold("PDB_LINE_TOO_SHORT")
        chain=ln[21]
        atom=ln[12:16].strip()
        # Every atom of a residue, not just CA, matches ProteinMPNN source parser.
        # Repeated altlocs are allowed only when the residue identity is the same.
        aa=AA3.get(ln[17:20])
        if aa is None:raise IdentityHold("UNSUPPORTED_PDB_RESIDUE_"+ln[17:20])
        number=ln[22:26].strip()
        try:resnum=int(number)
        except ValueError:raise IdentityHold("INVALID_PDB_RESIDUE_NUMBER")
        ins=ln[26].strip()
        if len(ins)>1:raise IdentityHold("INVALID_INSERTION_CODE")
        key=(resnum,ins)
        old=chains[chain].get(key)
        if old is not None and old!=aa:raise IdentityHold("PDB_RESIDUE_IDENTITY_CONFLICT")
        chains[chain][key]=aa
        residues[chain].add(resnum)
        insertion_codes[chain].add(key)
    if not chains:raise IdentityHold("NO_PROTEIN_ATOM_RECORDS")
    out={}
    for chain,observed in chains.items():
        nums=[p[0] for p in observed]
        if max(nums)-min(nums)>10000:raise IdentityHold("EXCESSIVE_PDB_RESIDUE_RANGE")
        s=[]
        for n in range(min(nums),max(nums)+1):
            ordered=sorted((ins,aa) for (num,ins),aa in observed.items() if num==n)
            if not ordered:s.append("X")
            else:
                for _,aa in ordered:s.append(aa)
        out[chain]="".join(s)
    return out

def audit(manifest_bytes,zip_bytes):
    if digest(manifest_bytes)!=MANIFEST_SHA256:raise IdentityHold("FROZEN_MANIFEST_SHA_DRIFT")
    if digest(zip_bytes)!=ARCHIVE_SHA256:raise IdentityHold("FIREPROT_ARCHIVE_SHA_DRIFT")
    import hashlib
    if hashlib.md5(zip_bytes).hexdigest()!=ARCHIVE_MD5:
        raise IdentityHold("FIREPROT_ARCHIVE_PUBLISHED_MD5_DRIFT")
    manifest=json.loads(manifest_bytes)
    domains=manifest.get("domains")
    if len(domains)!=10 or sum(len(d["variants"]) for d in domains)!=200:
        raise IdentityHold("FROZEN_10X20_SIZE_DRIFT")
    rows=[]
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        for dom in domains:
            pid=dom["pdb_id"]
            if not PDB_ID_RE.fullmatch(pid):raise IdentityHold("PDB_ID_NOT_SAFE")
            member=dom["pdb_member"]
            if member!=f"fireprot_upload/pdbs/{pid}.pdb":
                raise IdentityHold("PDB_MEMBER_NAME_DRIFT")
            if member not in archive.namelist():raise IdentityHold("MISSING_PDB_MEMBER_"+pid)
            pb=archive.read(member)
            if digest(pb)!=dom["pdb_member_sha256"]:
                raise IdentityHold("PDB_MEMBER_SHA_DRIFT_"+pid)
            chains=extract_pdb_sequences(pb)
            pdb_concat="".join(chains[key] for key in AUTHOR_CHAIN_ORDER if key in chains)
            target=dom["wildtype_sequence"]
            if digest(target.encode("ascii"))!=dom["wildtype_sha256"]:
                raise IdentityHold("PDB_SOURCE_WT_SHA_DRIFT_"+pid)
            # Original protein_mpnn_utils.py may have additional numeric chain names.
            if any(k not in AUTHOR_CHAIN_ORDER for k in chains):
                raise IdentityHold("NONSTANDARD_PDB_CHAIN_ID_"+pid)
            match_type=("SINGLE_CHAIN_EXACT" if len(chains)==1 and target==pdb_concat else
                        "MULTICHAIN_CONCAT_EXACT_NOT_SINGLE_CHAIN" if target==pdb_concat else
                        "AUTHOR_PDB_SEQUENCE_NOT_EXACT_COORDINATE_MAP")
            correct=0
            for v in dom["variants"]:
                pos=v["pdb_position_zero_based"]
                if type(pos) is not int or not 0<=pos<len(target):
                    raise IdentityHold("MUTATION_POSITION_INVALID_"+pid)
                if target[pos]!=v["wild_type_residue"]:
                    raise IdentityHold("MUTATION_WT_RESIDUE_DRIFT_"+pid)
                mutated=target[:pos]+v["mutant_residue"]+target[pos+1:]
                if digest(mutated.encode("ascii"))!=v["mutant_sequence_sha256"]:
                    raise IdentityHold("MUTANT_SEQUENCE_SHA_DRIFT_"+pid)
                correct+=1
            # A portable Boltz single-chain WT requires exact coordinate chain
            # correspondence, not just a curated matching mutation index.
            permitted=match_type=="SINGLE_CHAIN_EXACT"
            rows.append({
                "pdb_id":pid,"frozen_pdb_member_sha256":digest(pb),
                "expected_wt_sequence_sha256":digest(target.encode("ascii")),
                "pdb_chains":{key:{"length":len(s),"sha256":digest(s.encode("ascii")),
                                   "unmodeled_gap_placeholders":s.count("X")}
                              for key,s in sorted(chains.items())},
                "pdb_concatenated_length":len(pdb_concat),
                "pdb_concatenated_sha256":digest(pdb_concat.encode("ascii")),
                "curated_vs_coordinate_identity":match_type,
                "frozen_20_mutation_sequences_verified":correct,
                "safe_single_chain_boltz_wt_technical_pilot":permitted
            })
    return {
      "schema_id":"janus.rowan.fireprot.pdb_coordinate_identity_gate.v1",
      "science_status":"METADATA_ONLY_PDB_COORDINATE_AUDIT_NOT_A_BLIND_EXPERIMENT",
      "source_manifest_sha256":MANIFEST_SHA256,
      "source_zip_sha256":ARCHIVE_SHA256,
      "original_author_parser":"Kuhlman-Lab/ThermoMPNN protein_mpnn_utils.py parse_PDB_biounits",
      "author_alignment_followup":"Kuhlman-Lab/ThermoMPNN preprocessing/2_seqalign_fireprot_dataset.py",
      "source_mutant_records_reproduced_without_labels":200,
      "pdbs":rows,
      "safe_single_chain_external_wt_count":sum(r["safe_single_chain_boltz_wt_technical_pilot"] for r in rows),
      "structural_calibration_or_prediction_validated":False,
      "published_experimental_labels_accessed":False,
      "rowan_paid_calls":0,
      "FireProt_210_boltz_inferences":0,
      "shadow_model_modified":False,
      "production_promotion":False,
      "next_action":"For an exact single-chain PDB-aligned source, freeze a metadata-only WT structural pilot; do not access published mutant outcomes, run 210 jobs or claim stability prediction. Any multi-chain or sequence mismatch requires explicit review rather than auto-correction."
    }

def main():
    ap=argparse.ArgumentParser()
    for key in ("manifest","archive","out"):
        ap.add_argument("--"+key,required=True,type=Path)
    a=ap.parse_args()
    try:
        if a.out.exists():raise IdentityHold("IMMUTABLE_RECEIPT_EXISTS")
        result=audit(a.manifest.read_bytes(),a.archive.read_bytes())
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf8")
        print("ROWAN_FIREPROT_PDB_COORDINATE_GATE=METADATA_AUDIT_COMPLETE")
        print("IDENTICAL_SINGLE_CHAIN_PDB",result["safe_single_chain_external_wt_count"],"/10")
        return 0
    except (OSError,IdentityHold,ValueError,zipfile.BadZipFile) as exc:
        print("ROWAN_FIREPROT_PDB_COORDINATE_GATE=HOLD_"+str(exc))
        return 2
if __name__=="__main__":raise SystemExit(main())
