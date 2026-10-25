#!/usr/bin/env python3
"""Evidence-only partial-range read of the author-published BBC1 CSV in Zenodo ZIP.

No Rowan credentials, chemistry workflow, training, or payments. As this is a
PARTIAL ZIP read, ZIP central-directory CRC and Zenodo archive MD5 are recorded
as SOURCE DECLARATIONS, not represented as fully verified hashes.
"""
from __future__ import annotations
import csv,hashlib,io,json,re,argparse
from pathlib import Path

ZENODO_URL="https://zenodo.org/records/7992926/files/Processed_K50_dG_datasets.zip?download=1"
ZENODO_RECORD="https://zenodo.org/records/7992926"
ARCHIVE_LENGTH=1013678473
ARCHIVE_PUBLISHED_MD5="f7e8c553efee734cf161ee6f2b0a09cf"
ENTRY="Processed_K50_dG_datasets/Tsuboyama2023_Dataset2_Dataset3_20230416.csv"
ENTRY_CRC=0x9ac87977
ENTRY_COMPRESSED=209854627
ENTRY_UNCOMPRESSED=697658024
ASSAY_ID="BBC1_YEAST_Tsuboyama_2023_1TG0"
WT="EVPFKVVAQFPYKSDYEDDLNFEKDQEIIVTSVEDAEWYFGEYQDSNGDVIEGIFPKSFVAVQG"
MUTATIONS=("G53A","G48D","E27F","W38L","K13N","G64Q","Q44V","E42H")
PROCESSED_SHA256="ca355a655381c95fe899d61a406251e0cd17d68bbabe287651d526fdeb821f87"
RECEIPT_SHA256="c7f0ffb81e490d6dd555d1b6b073838ec0ed9fffd9c6fe6551b781023aaeeb06"
OFFICIAL_PROCESSED_BBC1_SHA256="d258240a3ab7088f5ac331abf661611369d9a6a06cf7778ab4ae285b824cfdab"

class Hold(Exception): pass
def mutation_sequence(m):
    if not re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWY]\d+[ACDEFGHIKLMNPQRSTVWY]",m):
        raise Hold("INVALID_MUTATION_FORMAT")
    i=int(m[1:-1])-1
    if i not in range(len(WT)) or WT[i]!=m[0]:raise Hold("MUTATION_NOT_IN_WT")
    return WT[:i]+m[-1]+WT[i+1:]

def verify_receipt(blob):
    if hashlib.sha256(blob).hexdigest()!=RECEIPT_SHA256:raise Hold("RECEIPT_PIN_DRIFT")
    r=json.loads(blob)
    if r.get("schema_id")!="janus.meta_registry.rowan_evidence_receipt.v1" or r.get("original_public_data_sha256")!=PROCESSED_SHA256:
        raise Hold("RECEIPT_SCHEMA_OR_SOURCE_DRIFT")
    cases=r.get("cases")
    if not isinstance(cases,list) or len(cases)!=8:raise Hold("RECEIPT_COUNT_DRIFT")
    if [x.get("mutation") for x in cases]!=list(MUTATIONS):raise Hold("RECEIPT_MUTATION_DRIFT")
    return {x["mutation"]:float(x["published_processed_label"]) for x in cases}

def compare_rows(rows, processed):
    seen={};count=0
    for i,row in enumerate(rows,1):
        if row.get("WT_name")!="1TG0.pdb" or row.get("mut_type") not in MUTATIONS:continue
        mut=row["mut_type"]
        if row.get("aa_seq")!=mutation_sequence(mut):raise Hold("AUTHOR_SEQUENCE_DRIFT_"+mut)
        if mut in seen:raise Hold("AUTHOR_DUPLICATE_MUTATION_"+mut)
        try:
            from math import isfinite
            v=float(row["ddG_ML"])
            if not isfinite(v):raise ValueError("not finite")
        except (KeyError,TypeError,ValueError):raise Hold("AUTHOR_NONFINITE_SCORE_"+mut)
        seen[mut]={"mutation":mut,"csv_data_row_1_based":i,"author_ddG_ML":v,
                   "author_dG_ML":row.get("dG_ML"),"author_aa_seq":row["aa_seq"],
                   "author_WT_name":"1TG0.pdb","author_mut_type":mut}
    if set(seen)!=set(MUTATIONS):raise Hold("AUTHOR_MISSING_ROWS_"+",".join(sorted(set(MUTATIONS)-set(seen))))
    comparison=[]
    for mut in MUTATIONS:
        v=seen[mut]["author_ddG_ML"];w=processed[mut]
        comparison.append({**seen[mut],"processed_frozen_label":w,"processed_minus_author":w-v,
                           "exact_match_1e_9":abs(w-v)<=1e-9})
    disagreements=[x["mutation"] for x in comparison if not x["exact_match_1e_9"]]
    return {
        "schema_id":"janus.rowan.bbc1.author_zenodo_2023_eight_row_comparison.v1",
        "status":"HOLD_AUTHOR_PROCESSED_LABEL_DISCREPANCY" if disagreements else "EIGHT_AUTHOR_LABELS_MATCH",
        "author_record":ZENODO_RECORD,"author_zip_range_url":ZENODO_URL,
        "author_zip_published_md5":ARCHIVE_PUBLISHED_MD5,
        "author_zip_md5_independently_verified":False,
        "zip_length_expected":ARCHIVE_LENGTH,
        "zip_member_path":ENTRY,"member_compressed_bytes":ENTRY_COMPRESSED,
        "member_uncompressed_bytes":ENTRY_UNCOMPRESSED,
        "member_declared_crc32":f"{ENTRY_CRC:08x}","member_crc32_fully_verified":False,
        "study_assay":ASSAY_ID,"source_column_author":"ddG_ML",
        "source_column_ProteinGym":"ddG_ML_float",
        "source_metadata_sign":1,"target_unit":"kcal/mol",
        "processed_tsv_sha256":PROCESSED_SHA256,
        "archived_8of8_receipt_file_sha256":RECEIPT_SHA256,
        "official_ProteinGym_processed_BBC1_entry_sha256":OFFICIAL_PROCESSED_BBC1_SHA256,
        "n_matching":8-len(disagreements),"n_mismatches":len(disagreements),
        "mismatch_mutations":disagreements,
        "comparisons":comparison,
        "scope":"DIRECT_PARTIAL_HTTPS_RANGE_EXTRACTION_AUTHOR_CSV_NO_FULL_ARCHIVE_DIGEST",
        "inference":"Do not infer a version-transformation algorithm from these rows alone.",
        "prior_shadow_weights_changed":False,"rowan_credits_spent":0,
        "new_rowan_jobs":0,"production_promotion":False,
    }

def audit_live(receipt):
    import requests,zipfile
    class HttpRange(io.RawIOBase):
        def __init__(self):
            self.session=requests.Session()
            head=self.session.head(ZENODO_URL,timeout=30)
            head.raise_for_status()
            self.total=int(head.headers.get("Content-Length","0"))
            if self.total!=ARCHIVE_LENGTH:raise Hold("ZENODO_ZIP_LENGTH_DRIFT")
            self.pos=0;self.start=0;self.cache=b"";self.bytes=0;self.requests=0
        def readable(self):return True
        def seekable(self):return True
        def tell(self):return self.pos
        def seek(self,n,whence=0):
            dest=(n if whence==0 else self.pos+n if whence==1 else self.total+n)
            if dest<0 or dest>self.total:raise Hold("INVALID_ZIP_SEEK")
            self.pos=dest;return dest
        def read(self,n=-1):
            if n<0:n=self.total-self.pos
            if n==0:return b""
            result=bytearray()
            while n:
                if not self.start<=self.pos<self.start+len(self.cache):
                    st=self.pos;en=min(self.total-1,st+max(n,524288)-1)
                    resp=self.session.get(ZENODO_URL,headers={"Range":f"bytes={st}-{en}"},timeout=90)
                    resp.raise_for_status()
                    if resp.status_code!=206 or resp.headers.get("Content-Range")!=f"bytes {st}-{en}/{self.total}":
                        raise Hold("SERVER_DID_NOT_HONOR_EXACT_RANGE")
                    if len(resp.content)!=en-st+1:raise Hold("ZIP_RANGE_LENGTH_DRIFT")
                    self.start=st;self.cache=resp.content
                    self.bytes+=len(resp.content);self.requests+=1
                take=min(n,self.start+len(self.cache)-self.pos)
                result.extend(self.cache[self.pos-self.start:self.pos-self.start+take])
                self.pos+=take;n-=take
            return bytes(result)
    reader=HttpRange()
    with zipfile.ZipFile(reader) as z:
        inf=z.getinfo(ENTRY)
        if (inf.CRC,inf.compress_size,inf.file_size)!=(ENTRY_CRC,ENTRY_COMPRESSED,ENTRY_UNCOMPRESSED):
            raise Hold("ZIP_ENTRY_METADATA_DRIFT")
        seen_rows=[];inside=False
        # The 2023 dataset stores 1TG0 mutations contiguously, by row/name.
        # Continue to the end of the 1TG0 block and require all eight identities.
        with z.open(inf) as fh:
            items=csv.DictReader(io.TextIOWrapper(fh,encoding="utf-8-sig",newline=""))
            if not {"WT_name","mut_type","aa_seq","ddG_ML"} <= set(items.fieldnames or []):
                raise Hold("ORIGINAL_CSV_SCHEMA_DRIFT")
            for idx,row in enumerate(items,1):
                if row.get("WT_name")=="1TG0.pdb":
                    inside=True
                elif inside:break
                if row.get("mut_type") in MUTATIONS and row.get("WT_name")=="1TG0.pdb":
                    row["_original_csv_row"]=idx
                    seen_rows.append(row)
    # Avoid representing only the subset as a global uniqueness guarantee.
    report=compare_rows(seen_rows,receipt)
    for i,x in enumerate(report["comparisons"]):
        x["csv_data_row_1_based"]=int(seen_rows[next(j for j,y in enumerate(seen_rows) if y["mut_type"]==x["mutation"])]["_original_csv_row"])
    report["zip_byte_ranges_downloaded"]=reader.bytes
    report["zip_range_http_requests"]=reader.requests
    report["uniqueness_scope"]="CONTIGUOUS_AUTHOR_1TG0_BLOCK_ONLY"
    return report

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--receipt",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    try:
        if args.output.exists():raise Hold("OUTPUT_ALREADY_EXISTS")
        pred=verify_receipt(args.receipt.read_bytes())
        report=audit_live(pred)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        print("JANUS_ZENODO_BBC1="+report["status"])
        print("MATCHED="+str(report["n_matching"])+" MISMATCHES="+str(report["n_mismatches"]))
        return 2 if report["n_mismatches"] else 0
    except (Hold,OSError,ValueError,KeyError) as exc:
        print("JANUS_ZENODO_BBC1=HOLD_"+str(exc))
        return 2

if __name__=="__main__":raise SystemExit(main())
