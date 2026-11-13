#!/usr/bin/env python3
"""ESSENCE v1.2 independent implementation of frozen expected-output checks.

This script lives in JANUS Meta Registry and NEVER imports the tested Genesis/
Demiurge candidate code. It checks the frozen cross-repository input corpus,
recomputes expected GPT ByteTokenizer and gene-name outputs from the published
behavioral specification, and independently checks two repository-specific
CI receipts. It cannot authenticate an external custodian or prove speed gains.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
FIX=ROOT/"data"/"JANUS-ESSENCE-V12-CROSSREPO-FROZEN-REAL-ALGO-CORPUS-2026-11-13.json"
GENESIS=ROOT/"data"/"essence"/"v12"/"CI_GENESIS_REAL_ALGORITHM_RECEIPT_2026-11-13.json"
DEMIURGE=ROOT/"data"/"essence"/"v12"/"CI_DEMIURGE_REAL_ALGORITHM_RECEIPT_2026-11-13.json"
CORPUS_BLOB="71f23a157a9849998dc9655bc6bdf15c08d9934a"
FREEZE_COMMIT="5fcd50ad7fc26f9e26aef6ff25ebcb42ef7c8f28"
SOURCE_BLOB="11e359e89d3946895b2e0d6817c54253f09dfed1"
BANK_BLOB="e7fe6f59591009df1905dbbf06b164d49e422660"
OWNER_REPOS=("Hawkar-usls/Janus_Genesis","Hawkar-usls/Janus-Demiurge")
PREFIXES=("JGPT1","MicroGPTSlime_quantized","MicroGPTSlime","MicroGPT",
          "CatGPT","FractalGPT","All_starsGPT","NonceMapGPT",
          "VacuumGPT","HoloGPT_TEST2","HoloGPT")
KNOWN=("MicroGPT","MicroGPTSlime","MicroGPTSlime_quantized","All_starsGPT",
       "CatGPT","FractalGPT","JGPT1","NonceMapGPT","LightGPT","WaterGPT",
       "AtomGPT","VacuumGPT","SHA256-GPT","IR_GPT_PhysicsLab","PIP-BOY GPT",
       "Physarious Movement Tachyon GPT v2","HoloGPT","HoloGPT_TEST2",
       "Yaksa+12","Physarum","GEX","Trinity")
GATES=("HOLD_SEMANTIC_REGRESSION","HOLD_PYTHON_MEMORY_REGRESSION",
       "HOLD_TIME_REGRESSION","HOLD_NO_REPRODUCIBLE_SPEED_GAIN",
       "RESEARCH_CANDIDATE_PENDING_INDEPENDENT_BLIND_REPLICATION")


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,
                      separators=(",",":"),allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def git_blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()


def load(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>100_000:
        raise ValueError("INVALID_OR_OVERSIZE_LOCAL_RECEIPT")
    return json.loads(path.read_text(encoding="utf-8"),
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))


def independent_gene_oracle(name):
    """Separately authored behavioral rule; no imported JANUS gene-bank code."""
    if not isinstance(name,str) or len(name)>120:
        return None
    if name in KNOWN:
        return name
    for prefix in PREFIXES:
        if name==prefix+".py" or name.startswith(prefix+"("):
            return prefix
    return None


def expected_frozen_outputs(corpus):
    if (not isinstance(corpus,dict)
        or corpus.get("schema")!="janus.essence.real_algorithm_cross_repo_holdout/1.2"
        or corpus.get("blinded") is not False
        or corpus.get("externally_independently_attested") is not False):
        raise ValueError("FROZEN_DATA_CLAIM_CONTRADICTION")
    texts=corpus.get("text_cases")
    names=corpus.get("gene_cases")
    if (not isinstance(texts,list) or not isinstance(names,list)
            or len(texts)!=31 or len(names)!=23
            or any(not isinstance(t,str) for t in texts+names)):
        raise ValueError("FROZEN_CASES_CHANGED")
    # Reference ByteTokenizer contract: UTF-8 text encodes to byte IDs;
    # BOS/EOS are >255 and therefore discarded by decoder. All valid strings
    # round-trip unchanged. This oracle does not execute actual model source.
    text_outputs=[]
    for text in texts:
        ids=[256]+list(text.encode("utf-8",errors="replace"))+[257]
        reconstructed=bytes(i for i in ids if 0<=i<256).decode("utf-8",errors="replace")
        text_outputs.append(reconstructed)
    gene_outputs=[independent_gene_oracle(name) for name in names]
    return {"tokenizer":digest(text_outputs),"gene_bank":digest(gene_outputs)}


def check_receipt(receipt,repo,expected,corpus):
    if (not isinstance(receipt,dict) or receipt.get("schema")!="janus.essence.real_algorithm_benchmark/1.2"
            or receipt.get("repository")!=repo
            or receipt.get("holdout_origin_repo")!="Hawkar-usls/janus-meta-registry"
            or receipt.get("holdout_origin_commit")!=FREEZE_COMMIT
            or receipt.get("holdout_git_blob_sha1")!=CORPUS_BLOB
            or receipt.get("holdout_blinded") is not False
            or receipt.get("independent_external_evaluator_attested") is not False
            or receipt.get("model_weights_updated") is not False
            or receipt.get("automatic_promotion") is not False
            or receipt.get("runtime_execution_authority") is not False
            or receipt.get("rollback_drill_not_production_deployment") is not True
            or receipt.get("candidates_executed_in_working_production") is not False
            or receipt.get("overall_gate")!="HOLD_EXTERNAL_BLIND_REPLICATION_AND_REAL_CHECKPOINT_REVIEW"):
        raise ValueError("FRAUDULENT_OR_INCOMPATIBLE_RECEIPT")
    if receipt.get("receipt_sha256")!=digest({k:v for k,v in receipt.items() if k!="receipt_sha256"}):
        raise ValueError("RECEIPT_SHA256_TAMPERED")
    for label,identity,count,oraclehash in (
        ("byte_tokenizer",SOURCE_BLOB,len(corpus["text_cases"]),expected["tokenizer"]),
        ("essence_gene_bank",BANK_BLOB,len(corpus["gene_cases"]),expected["gene_bank"])):
        lane=receipt.get(label)
        if (not isinstance(lane,dict) or lane.get("source_git_blob_sha1")!=identity
                or lane.get("case_count")!=count
                or lane.get("baseline_output_sha256")!=oraclehash
                or lane.get("candidate_output_sha256")!=oraclehash
                or lane.get("decision",{}).get("counterexample_count")!=0
                or lane["decision"].get("gate") not in GATES):
            raise ValueError("INDEPENDENT_ORACLE_OUTPUT_DISAGREEMENT")
        negative=lane.get("negative_control")
        if (not isinstance(negative,dict)
                or negative.get("candidate_held") is not True
                or negative.get("rollback_verified") is not True
                or negative.get("counterexample_count",0)<1
                or negative.get("baseline_output_sha256")!=oraclehash
                or negative.get("recovered_output_sha256")!=oraclehash
                or negative.get("production_weights_or_modules_changed") is not False):
            raise ValueError("INDEPENDENT_ORACLE_ROLLBACK_DISAGREEMENT")
        for metric_name in ("baseline_metrics","candidate_metrics"):
            m=lane.get(metric_name)
            if (not isinstance(m,dict)
                    or m.get("measurement_kind")!="LOCAL_WALL_CLOCK_PLUS_PYTHON_TRACEMALLOC_NOT_TOTAL_RSS"
                    or type(m.get("median_ns_per_call")) not in (float,int)
                    or not math.isfinite(m["median_ns_per_call"])
                    or m["median_ns_per_call"]<=0
                    or type(m.get("median_tracemalloc_python_peak_bytes")) is not int
                    or m["median_tracemalloc_python_peak_bytes"]<0):
                raise ValueError("INVALID_RESOURCE_MEASUREMENT")
    torch=receipt.get("transformer_forward")
    if not isinstance(torch,dict) or torch.get("status")!="NOT_RUN_TORCH_OPTIONAL_CI" or torch.get("weights_trained") is not False:
        raise ValueError("CI_DID_NOT_RUN_TORCH_USE_NO_FALSE_CLAIMS")
    return {"repository":repo,"receipt_sha256":receipt["receipt_sha256"],
            "tokenizer_oracle_sha256":expected["tokenizer"],
            "gene_bank_oracle_sha256":expected["gene_bank"],
            "tokenizer_wall_speed_ratio":receipt["byte_tokenizer"]["decision"]["median_wall_speed_ratio"],
            "gene_bank_wall_speed_ratio":receipt["essence_gene_bank"]["decision"]["median_wall_speed_ratio"],
            "tokenizer_gate":receipt["byte_tokenizer"]["decision"]["gate"],
            "gene_bank_gate":receipt["essence_gene_bank"]["decision"]["gate"],
            "negative_controls_rejected":True,"rollback_drills_replayed":True}


def verify_all():
    if git_blob(FIX.read_bytes())!=CORPUS_BLOB:
        raise ValueError("INDEPENDENT_FROZEN_CORPUS_GIT_BLOB_MISMATCH")
    corpus=load(FIX)
    expected=expected_frozen_outputs(corpus)
    origins=(load(GENESIS),load(DEMIURGE))
    findings=[check_receipt(item,repo,expected,corpus)
              for repo,item in zip(OWNER_REPOS,origins)]
    if (findings[0]["tokenizer_oracle_sha256"]!=findings[1]["tokenizer_oracle_sha256"]
            or findings[0]["gene_bank_oracle_sha256"]!=findings[1]["gene_bank_oracle_sha256"]):
        raise ValueError("REPOSITORIES_DISAGREE_ON_FROZEN_OUTPUTS")
    result={
        "schema":"janus.essence.cross_repo_witness/1.2",
        "status":"CROSS_REPO_FROZEN_OUTPUTS_REPRODUCED_NO_PRODUCTION_AUTHORITY",
        "origin":"INDEPENDENT_META_REGISTRY_ORACLE_IMPLEMENTATION",
        "frozen_registry_commit_sha":FREEZE_COMMIT,
        "frozen_registry_git_blob_sha1":CORPUS_BLOB,
        "text_cases":len(corpus["text_cases"]),
        "gene_cases":len(corpus["gene_cases"]),
        "checked_ci_receipts":findings,
        "production_authority":False,
        "independent_external_custodian_attestation":False,
        "blind_holdout":False,
        "statistically_replicated_speed_advantage":False,
        "production_checkpoint_rollback_demonstrated":False,
        "untrained_pytorch_model_performance_verified_here":False,
    }
    result["receipt_sha256"]=digest(result)
    return result


def selftest():
    result=verify_all()
    if len(result["checked_ci_receipts"])!=2: raise AssertionError("MISSING_REPO")
    corpus=load(FIX)
    expected=expected_frozen_outputs(corpus)
    good=load(GENESIS)
    for mutation in ("authority","oracle","rollback","provenance"):
        bad=copy.deepcopy(good)
        if mutation=="authority":bad["model_weights_updated"]=True
        if mutation=="oracle":bad["byte_tokenizer"]["candidate_output_sha256"]="0"*64
        if mutation=="rollback":bad["essence_gene_bank"]["negative_control"]["rollback_verified"]=False
        if mutation=="provenance":bad["holdout_git_blob_sha1"]="0"*40
        bad["receipt_sha256"]=digest({k:v for k,v in bad.items() if k!="receipt_sha256"})
        try:check_receipt(bad,OWNER_REPOS[0],expected,corpus)
        except ValueError:pass
        else:raise AssertionError("NEGATIVE_CONTROL_ACCEPTED_"+mutation)
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out")
    parser.add_argument("--selftest",action="store_true")
    args=parser.parse_args()
    if args.selftest:selftest()
    report=verify_all()
    if args.out:
        p=Path(args.out)
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,sort_keys=True))


if __name__=="__main__":
    main()
