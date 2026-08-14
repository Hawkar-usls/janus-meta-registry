from __future__ import annotations

import argparse
import hashlib
import html
import json
import pathlib
import re
import unicodedata
import urllib.request
from datetime import datetime, timezone

from pypdf import PdfReader


def fetch_bytes(url: str) -> tuple[int | None, str | None, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent":"JANUS-Linear-A-sign-id-conformance/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return getattr(resp, "status", None), resp.headers.get("Content-Type"), resp.read()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strip_combining(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")


def canonical_sign(prefix: str, n: str) -> str:
    return f"{prefix.upper()}{int(n):03d}"


def source_sign_fragments(raw: str) -> list[dict]:
    clean = strip_combining(raw)
    out=[]
    rx=re.compile(r"\b(AB|A)\s*(\d{1,3}(?:\s*-\s*\d{1,3})*)", re.I)
    for m in rx.finditer(clean):
        prefix=m.group(1).upper()
        nums=re.findall(r"\d{1,3}",m.group(2))
        ids=[canonical_sign(prefix,n) for n in nums]
        raw_seg=raw[m.start():min(len(raw),m.end()+8)]
        out.append({
            "prefix":prefix,
            "normalized_numeric_segment":m.group(2),
            "sign_ids":ids,
            "uncertainty_or_damage_near_fragment": any(c in raw_seg for c in ["̣","[","]","•","?"]),
        })
    return out


def reference_sign_ids(item_html: str) -> list[str]:
    m=re.search(r"<transcribed-reading-unicode>.*?<reading-text>(.*?)</reading-text>.*?</transcribed-reading-unicode>", item_html, flags=re.S|re.I)
    if not m:
        return []
    block=html.unescape(m.group(1))
    ids=[]
    for ch in block:
        name=unicodedata.name(ch, "")
        mm=re.fullmatch(r"LINEAR A SIGN (AB\d{3}|A\d{3})", name)
        if mm:
            ids.append(mm.group(1))
    return ids


def levenshtein(a: list[str], b: list[str]) -> int:
    prev=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        cur=[i]
        for j,y in enumerate(b,1):
            cur.append(min(cur[-1]+1, prev[j]+1, prev[j-1]+(x!=y)))
        prev=cur
    return prev[-1]


def lcp(a: list[str], b: list[str]) -> int:
    n=0
    for x,y in zip(a,b):
        if x!=y: break
        n+=1
    return n


def row_id(line: str) -> str | None:
    if re.match(r"^THE\s+7[-–]12\b", line):
        return None
    m=re.match(r"^THE\s+Z([bBgG])\s+(\d+)\**\b",line)
    if m:
        return f"THEZ{m.group(1).upper()}{int(m.group(2))}"
    m=re.match(r"^THE\s+(\d+)([ab]?)\b",line,re.I)
    if m:
        return f"THE{int(m.group(1))}{m.group(2).upper()}"
    return None


def extract_rows(reader: PdfReader, regions: list[dict]) -> dict[str,str]:
    rows={}
    for reg in regions:
        lines=(reader.pages[int(reg["page"])-1].extract_text() or "").splitlines()
        subset=lines[int(reg["first_line"])-1:int(reg["last_line"])]
        current=None
        buf=[]
        for line in subset:
            rid=row_id(line)
            is_range=bool(re.match(r"^THE\s+7[-–]12\b",line))
            if rid is not None or is_range:
                if current is not None:
                    rows[current]="\n".join(buf)
                current=rid
                buf=[line] if rid is not None else []
            else:
                if current is not None:
                    buf.append(line)
        if current is not None:
            rows[current]="\n".join(buf)
    return rows


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--spec",required=True)
    ap.add_argument("--receipt",required=True)
    ap.add_argument("--bridge",required=True)
    ap.add_argument("--out",required=True)
    ap.add_argument("--pdf-tmp",required=True)
    args=ap.parse_args()
    spec_path=pathlib.Path(args.spec)
    spec=json.loads(spec_path.read_text(encoding="utf-8"))
    receipt=json.loads(pathlib.Path(args.receipt).read_text(encoding="utf-8"))
    bridge=json.loads(pathlib.Path(args.bridge).read_text(encoding="utf-8"))

    status,ctype,pdf=fetch_bytes(receipt["transport_receipt"]["url"])
    pdf_path=pathlib.Path(args.pdf_tmp)
    pdf_path.write_bytes(pdf)
    reader=PdfReader(str(pdf_path))
    if reader.is_encrypted:
        try: reader.decrypt("")
        except Exception: pass
    rows=extract_rows(reader,spec["source_table_regions"])

    source_docs={}
    for doc in spec["comparison_family"]["documents"]:
        if doc=="THE7":
            raw="\n".join(rows.get(x,"") for x in ["THE7A","THE7B"] if rows.get(x,""))
            source_row_ids=[x for x in ["THE7A","THE7B"] if x in rows]
        else:
            raw=rows.get(doc,"")
            source_row_ids=[doc] if doc in rows else []
        fragments=source_sign_fragments(raw)
        seq=[sid for frag in fragments for sid in frag["sign_ids"]]
        source_docs[doc]={
            "source_row_ids":source_row_ids,
            "raw_row_sha256":hashlib.sha256(raw.encode("utf-8")).hexdigest() if raw else None,
            "raw_row_character_count":len(raw),
            "source_fragments":fragments,
            "source_sign_ids":seq,
            "source_uncertainty_or_damage_present":any(f["uncertainty_or_damage_near_fragment"] for f in fragments),
        }

    bridge_map={x["notti_id"]:x for x in bridge["bridged_identities"]}
    results=[]
    reference_hash_checks=[]
    for doc in spec["comparison_family"]["documents"]:
        b=bridge_map[doc]
        hstatus,hctype,hbytes=fetch_bytes(b["reference_url"])
        hdigest=sha256(hbytes)
        hash_ok=hdigest==b["reference_sha256"]
        reference_hash_checks.append(hash_ok and hstatus==200)
        htext=hbytes.decode("utf-8",errors="replace")
        refseq=reference_sign_ids(htext)
        src=source_docs[doc]
        srcseq=src["source_sign_ids"]
        if not srcseq or not refseq:
            classification="NONCOMPARABLE_EMPTY_PARSED_SEQUENCE"
        elif srcseq==refseq:
            classification="EXACT_SIGN_ID_SEQUENCE_MATCH"
        else:
            classification="SIGN_ID_SEQUENCE_MISMATCH"
        results.append({
            "notti_id":doc,
            "reference_id":b["reference_id"],
            **src,
            "reference_html_sha256":hdigest,
            "reference_html_hash_matches_bridge_receipt":hash_ok,
            "reference_sign_ids":refseq,
            "source_sign_count":len(srcseq),
            "reference_sign_count":len(refseq),
            "longest_common_prefix_length":lcp(srcseq,refseq),
            "levenshtein_distance":levenshtein(srcseq,refseq) if srcseq or refseq else 0,
            "classification":classification,
        })

    counts={k:sum(1 for r in results if r["classification"]==k) for k in spec["comparison_family"]["classification"]}
    checks={
        "receipt_admitted":receipt["status"]=="EXACT_OPEN_PUBLISHER_BYTES_ADMITTED_CONTENT_VISIBLE_NONBLIND_RESCUE_WITNESS",
        "bridge_admitted":bridge["status"]=="IDENTITY_BRIDGE_13_PASS_ZB14_ZB15_COLLISION_PRESERVED",
        "fresh_pdf_http_200":status==200,
        "fresh_pdf_same_byte_length":len(pdf)==receipt["transport_receipt"]["byte_length"],
        "fresh_pdf_same_sha256":sha256(pdf)==receipt["transport_receipt"]["sha256"],
        "fresh_pdf_same_page_count":len(reader.pages)==receipt["transport_receipt"]["page_count"],
        "all_13_documents_present":len(results)==13 and {r["notti_id"] for r in results}==set(spec["comparison_family"]["documents"]),
        "all_reference_html_hashes_match_bridge":all(reference_hash_checks),
        "unresolved_Zb14_Zb15_not_compared":"THEZB14" not in {r["notti_id"] for r in results} and "THEZB15" not in {r["notti_id"] for r in results},
        "blind_novelty_credit_false":spec["contamination_and_claims"]["blind_novelty_credit"] is False,
        "phonetic_transliteration_not_used":spec["reference_sign_id_parser"]["phonetic_transliteration_used"] is False,
        "semantic_mapping_not_used":spec["reference_sign_id_parser"]["semantic_mapping_used"] is False,
        "decipherment_not_performed":spec["contamination_and_claims"]["decipherment_performed"] is False,
    }
    passed=all(checks.values())
    result={
        "artifact_uuid":"JANUS-LINEAR-A-R3B-0-NOTTI-2018-SIGN-ID-CONFORMANCE-RESULT-2026-08-14-v0.1",
        "version":"v0.1",
        "node_type":"nonblind_corrective_alternate_editorial_sign_id_conformance_result",
        "status":"EXECUTED_ALL_13_BRIDGED_DOCUMENTS_NONBLIND_SIGN_ID_CONFORMANCE" if passed else "SIGN_ID_CONFORMANCE_INFRASTRUCTURE_NONPASS",
        "executed_at_utc":datetime.now(timezone.utc).isoformat(),
        "frozen_spec":str(spec_path).replace("\\","/"),
        "source_receipt":{"byte_length":len(pdf),"sha256":sha256(pdf),"page_count":len(reader.pages),"http_status":status,"content_type":ctype},
        "representation_contract":{"source":"AB/A numeric sign IDs only","reference":"Unicode character names LINEAR A SIGN AB###/A### only","phonetic_values_used":False,"semantic_values_used":False},
        "document_results":results,
        "summary":{
            "family_size":len(results),
            "exact_match_count":counts["EXACT_SIGN_ID_SEQUENCE_MATCH"],
            "mismatch_count":counts["SIGN_ID_SEQUENCE_MISMATCH"],
            "noncomparable_count":counts["NONCOMPARABLE_EMPTY_PARSED_SEQUENCE"],
            "unresolved_identity_rows_excluded":["THEZB14","THEZB15"],
            "blind_novelty_credit":False,
        },
        "checks":checks,
        "all_checks_pass":passed,
        "claim_ceiling":spec["claim_ceiling"],
    }
    out=pathlib.Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"summary":result["summary"],"checks":checks},ensure_ascii=False,indent=2))
    return 0 if passed else 2

if __name__=="__main__":
    raise SystemExit(main())
