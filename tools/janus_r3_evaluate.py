"""JANUS-R3 continuous, conservative source-quality evaluation.

This is provenance, metadata, novelty and anti-poisoning evaluation, NOT
independent verification of scientific or journalistic claims. Training cannot
consume a quarantine receipt, even if this evaluator passes.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from tools.janus_public_source_intake import (
    canonical, digest, GDELT_ZIP_RE, SCHEMA as INTAKE_SCHEMA,
    validate_receipt, need,
)

SCHEMA="janus.r3.public_source_quality_review.v1"
DOI_RE=re.compile(r"^https://doi\.org/10\.\d{4,9}/[^\s?#]{2,250}$",re.I)
SHA256_RE=re.compile(r"^[a-f0-9]{64}$")
GITHUB_SHA_RE=re.compile(r"^[a-f0-9]{40}$")
ALLOWED_STATUSES=frozenset({
    "PUBLIC_GKG_BATCH_STRUCTURALLY_READABLE",
    "PUBLIC_ENCYCLOPEDIA_METADATA",
    "BIBLIOGRAPHIC_METADATA_ONLY",
    "PUBLIC_ACTION_RUN_METADATA_ONLY",
    "PROVIDER_UNAVAILABLE",
})

def fingerprinted_sources(record):
    """Validate metadata types, domain scopes and integrity; return unique IDs."""
    validate_receipt(record)
    sources=record["sources"]
    original={"gdelt_gkg","wikipedia","openalex","tachyon_action"}
    # Historical R3 v1 source receipts have four providers; do not invalidate
    # append-only records when a fifth provider is added.
    need(set(sources) in (original,original|{"ocean_action"}),
         "R3_UNEXPECTED_SOURCES")
    names=set()
    metrics={}
    for typ,item in sorted(sources.items()):
        need(isinstance(item,dict), "R3_SOURCE_NOT_OBJECT")
        status=item.get("status")
        need(status in ALLOWED_STATUSES,"R3_INVALID_SOURCE_STATUS")
        if status=="PROVIDER_UNAVAILABLE":
            need(re.fullmatch(r"[A-Z0-9_]{4,80}",item.get("reason","")) is not None,
                 "R3_BAD_PROVIDER_FAILURE")
            metrics[typ]={"status":status,"records":0,"integrity_passed":False}
            continue
        need(status=={
            "gdelt_gkg":"PUBLIC_GKG_BATCH_STRUCTURALLY_READABLE",
            "wikipedia":"PUBLIC_ENCYCLOPEDIA_METADATA",
            "openalex":"BIBLIOGRAPHIC_METADATA_ONLY",
            "tachyon_action":"PUBLIC_ACTION_RUN_METADATA_ONLY",
            "ocean_action":"PUBLIC_ACTION_RUN_METADATA_ONLY"
        }[typ],"R3_CROSS_SOURCE_STATUS_SPOOF")
        if typ=="gdelt_gkg":
            u=item.get("gkg_url","")
            need(isinstance(u,str) and GDELT_ZIP_RE.fullmatch(u) is not None,
                 "R3_GDELT_URL")
            need(item.get("source_manifest_md5_verified") is True,
                 "R3_GDELT_MANIFEST_CHECKSUM_MISSING")
            need(isinstance(item.get("compressed_bytes"),int) and
                 0<item["compressed_bytes"]<=9_000_000,"R3_GDELT_SIZE")
            need(SHA256_RE.fullmatch(item.get("zip_sha256","")) is not None,
                 "R3_GDELT_SHA256")
            need(item.get("sample",{}).get("first_row_field_count")==27,
                 "R3_GDELT_SCHEMA_27_COLUMNS")
            need(item.get("article_claims_independently_verified") is False,
                 "R3_GDELT_CANNOT_CLAIM_FACT_VERIFIED")
            names.add("gdelt-zip:"+item["zip_sha256"])
            count=1
        elif typ=="wikipedia":
            need(item.get("article_claims_independently_verified") is False,
                 "R3_WIKI_CANNOT_CLAIM_FACT_VERIFIED")
            data=item.get("article_metadata")
            need(isinstance(data,list) and 1<=len(data)<=3,"R3_WIKI_CARD_COUNT")
            for v in data:
                url=v.get("article_url","") if isinstance(v,dict) else ""
                p=urlsplit(url)
                need(p.scheme=="https" and p.hostname=="ru.wikipedia.org"
                     and p.path.startswith("/wiki/") and
                     p.username is None and p.password is None and
                     not p.fragment and isinstance(v.get("title"),str)
                     and 3<=len(v["title"])<=120,"R3_WIKI_CARD_URL")
                names.add("wikipedia:"+url)
            count=len(data)
        elif typ=="openalex":
            need(item.get("independent_scientific_review") is False,
                 "R3_BIBLIOGRAPHY_IS_NOT_REVIEW")
            data=item.get("papers")
            need(isinstance(data,list) and 1<=len(data)<=3,"R3_DOI_CARD_COUNT")
            for v in data:
                url=v.get("doi_url","") if isinstance(v,dict) else ""
                dt=v.get("publication_date")
                need(isinstance(url,str) and DOI_RE.fullmatch(url) is not None
                     and isinstance(v.get("title"),str)
                     and 3<=len(v["title"])<=250,"R3_INVALID_DOI_METADATA")
                if dt is not None:
                    need(isinstance(dt,str) and len(dt)==10,"R3_BAD_PUBLISH_DATE")
                    try: date.fromisoformat(dt)
                    except ValueError: need(False,"R3_BAD_PUBLISH_DATE")
                names.add("doi:"+url.lower())
            count=len(data)
        else:
            target={
                "tachyon_action":("Hawkar-usls/Demi_Head",
                                  "tachyon-r2h-parallel-research.yml"),
                "ocean_action":("Hawkar-usls/Janus-Demiurge",
                                "janus-ocean-meta-next.yml")
            }[typ]
            need((item.get("repository"),item.get("workflow"))==target,
                 "R3_ACTION_REPOSITORY_SPOOF")
            need(item.get("candidate_auto_promoted") is False and
                 item.get("scientific_quality_of_model_verified") is False,
                 "R3_ACTION_RUN_NOT_A_SCIENCE_PASS")
            need(type(item.get("run_id")) is int and
                 item["run_id"]>0 and GITHUB_SHA_RE.fullmatch(
                     str(item.get("head_sha",""))) is not None,
                 "R3_INVALID_RUN_PROVENANCE")
            if typ=="ocean_action":
                need(item.get("model_weights_or_metrics_independently_verified")
                     is False and
                     item.get("trained_on_unreviewed_r3_source_text") is False,
                     "R3_OCEAN_RUN_NOT_A_SCIENCE_PASS")
            names.add(typ+":github-run:"+str(item["run_id"])+":"+item["head_sha"])
            count=1
        metrics[typ]={"status":status,"records":count,
                      "integrity_passed":True}
    return names,metrics

def evaluate(record,history=()):
    source_ids,metrics=fingerprinted_sources(record)
    known=set()
    for prior in history:
        # The same exact source observation in history is a duplicate and
        # must contribute to the known set, never count as new material.
        ids,_=fingerprinted_sources(prior)
        known.update(ids)
    new_ids=source_ids-known
    # Count metadata novelty. This is a non-arbitrary comparison, NOT quality
    # of any asserted physical claim or permission to update model weights.
    report={
        "schema":SCHEMA,
        "source_record_id":record["record_id"],
        "source_receipt_sha256":record["receipt_sha256"],
        "source_digest_sha256":record["source_digest_sha256"],
        "source_statuses":metrics,
        "known_history_source_count":len(known),
        "unique_public_metadata_id_count":len(source_ids),
        "new_metadata_id_count":len(new_ids),
        "new_metadata_id_sha256":digest(canonical(sorted(new_ids))),
        "metadata_sources_with_integrity":sum(
            x["integrity_passed"] for x in metrics.values()),
        "unavailable_provider_count":sum(
            x["status"]=="PROVIDER_UNAVAILABLE" for x in metrics.values()),
        "review_decision":("NEW_METADATA_REQUIRES_CURATOR_REVIEW"
                           if new_ids else "NO_NEW_METADATA"),
        "metadata_integrity_checked":True,
        "article_claims_independently_verified":False,
        "news_claims_fact_checked":False,
        "scientific_knowledge_promoted":False,
        "model_training_authorized":False,
        "model_training_dispatched":False,
        "external_blind_science_evaluator_used":False,
        "neural_model_improved":False,
        "quarantine_isolated_from_EYE":True,
        "proposed_action":"HUMAN_REVIEW_ONLY",
    }
    report["quality_receipt_sha256"]=digest(canonical(report))
    return report

def validate_quality(report,record):
    need(report.get("schema")==SCHEMA,"R3_QUALITY_SCHEMA")
    need(report.get("source_record_id")==record["record_id"] and
         report.get("source_digest_sha256")==record["source_digest_sha256"] and
         report.get("source_receipt_sha256")==record["receipt_sha256"],
         "R3_SOURCE_RECEIPT_REFERENCE")
    for field in ("article_claims_independently_verified",
                  "news_claims_fact_checked","scientific_knowledge_promoted",
                  "model_training_authorized","model_training_dispatched",
                  "external_blind_science_evaluator_used","neural_model_improved"):
        need(report.get(field) is False,"R3_UNAUTHORIZED_PROMOTION")
    need(report.get("quality_receipt_sha256")==digest(canonical({
        k:v for k,v in report.items() if k!="quality_receipt_sha256"
    })),"R3_QUALITY_SHA_MISMATCH")

def from_directory(directory):
    base=Path(directory)
    if not base.exists():return []
    files=list(base.glob("JANUS-PUBLIC-SOURCES-*.json"))
    need(len(files)<=2000,"R3_HISTORY_FILE_BUDGET")
    return [json.loads(p.read_text(encoding="utf8")) for p in sorted(files)]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--history",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args()
    source=json.loads(Path(args.input).read_text(encoding="utf8"))
    report=evaluate(source,from_directory(args.history))
    validate_quality(report,source)
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,sort_keys=True,indent=2,
                              ensure_ascii=False)+"\n",encoding="utf8")
    print(json.dumps({"status":"R3_METADATA_QUALITY_REVIEW_ONLY",
                      "source_id":report["source_record_id"],
                      "new_metadata":report["new_metadata_id_count"],
                      "providers_up":report["metadata_sources_with_integrity"],
                      "providers_unavailable":report["unavailable_provider_count"],
                      "train":False},sort_keys=True))
if __name__=="__main__":
    main()
