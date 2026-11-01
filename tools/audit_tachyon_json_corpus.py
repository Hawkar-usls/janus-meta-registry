#!/usr/bin/env python3
"""Search every tracked/current JSON for the JANUS tachyon research family.

No guessed results from GitHub's incomplete code-search indexing. Enumerates
the actual checked-out repository, reads every .json file's bytes and reports
matches with source SHA256. Invalid JSON is still searchable and explicitly
flagged. JSONL (different format) is inventoried separately, never conflated.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re

DIRECT = re.compile(r"(?:tachyon|tahyon|tachi?on|tachyons?|тахион|тахіон|тах[её]он|тахіон)", re.I)
CONTEXT = re.compile(r"(?:retrocausal(?:ity)?|retrocausation|ретрокауз\w*|ретропричин\w*|advanced.time|future.to.past)", re.I)
STATUS = ("status", "authority", "claim_ceiling", "admitted_claim",
          "epistemic_contract", "negative_results_and_counterevidence")
MAX_PREVIEW = 3


def safe_extract(doc):
    if not isinstance(doc, dict):
        return {}
    return {
        key: (str(doc[key])[:350] if not isinstance(doc[key], (dict, list)) else
              json.dumps(doc[key], ensure_ascii=False)[:350])
        for key in STATUS if key in doc
    }


def check_file(path: Path, root: Path):
    rel = path.relative_to(root).as_posix()
    raw = path.read_bytes()
    try:
        content = raw.decode("utf-8-sig")
        bad_encoding = None
    except UnicodeDecodeError as e:
        content = raw.decode("utf-8", errors="replace")
        bad_encoding = str(e)
    direct = list(DIRECT.finditer(content))
    context = list(CONTEXT.finditer(content))
    path_direct = DIRECT.search(rel) is not None
    if not direct and not context and not path_direct:
        return None
    parsed, parse_error = None, None
    if path.suffix.lower() == ".json" and bad_encoding is None:
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError) as e:
            parse_error = str(e)[:220]
    elif bad_encoding:
        parse_error = "UTF8_ERROR: " + bad_encoding[:200]
    snippets = []
    for match in direct[:MAX_PREVIEW]:
        before = content[max(0,match.start()-70):match.start()]
        after = content[match.end():match.end()+85]
        snippets.append({
            "term":match.group(),
            "line":content.count("\n",0,match.start())+1,
            "context":(before+"["+match.group()+"]"+after).replace("\r"," ").replace("\n"," ")[:250],
        })
    return {
        "path":rel,
        "format":path.suffix.lower(),
        "bytes":len(raw),
        "sha256":sha256(raw).hexdigest(),
        "path_term":path_direct,
        "direct_term_occurrences":len(direct),
        "retrocausal_context_occurrences":len(context),
        "direct_previews":snippets,
        "json_parse_status":"PASS" if parsed is not None else ("NOT_JSONL_PARSED" if path.suffix.lower()==".jsonl" else "INVALID"),
        "parse_error":parse_error,
        "metadata":safe_extract(parsed)
    }


def build_inventory(root: Path, *, include_jsonl:bool=True):
    direct, contextual, errors = [], [], []
    scanned = Counter()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.relative_to(root).parts:
            continue
        if path.suffix.lower() not in ((".json",".jsonl") if include_jsonl else (".json",)):
            continue
        scanned[path.suffix.lower()] += 1
        try:
            record = check_file(path, root)
        except OSError as e:
            errors.append({"path":path.relative_to(root).as_posix(),"error":str(e)})
            continue
        if record is None:
            continue
        if record["direct_term_occurrences"]>0 or record["path_term"]:
            direct.append(record)
        else:
            contextual.append(record)
    return {
        "schema":"JANUS-TACHYON-FULL-JSON-CORPUS-INVENTORY-v1",
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "source":{
            "repo":"Hawkar-usls/janus-meta-registry",
            "github_sha":os.getenv("GITHUB_SHA","local"),
            "github_run_id":os.getenv("GITHUB_RUN_ID","local"),
            "method":"recurse ALL checkout .json and .jsonl raw UTF8 bytes; match filename and contents; invalid JSON still searched",
        },
        "scope":{"extensions":[".json",".jsonl"] if include_jsonl else [".json"],
                 "direct_pattern":DIRECT.pattern,
                 "context_pattern":CONTEXT.pattern,
                 "sha256_per_file":True,
                 "cannot_claim_historical_git_versions_or_unmounted_nas_files":True},
        "totals":{
            "scanned_by_extension":dict(scanned),
            "direct_match_files":len(direct),
            "direct_json_files":sum(r["format"]==".json" for r in direct),
            "direct_jsonl_files":sum(r["format"]==".jsonl" for r in direct),
            "context_only_match_files":len(contextual),
            "read_errors":len(errors),
            "direct_term_instances":sum(r["direct_term_occurrences"] for r in direct)
        },
        "direct_matches":direct,
        "retrocausal_context_only":contextual,
        "read_errors":errors,
        "caveats":[
            "Full scan of current checkout only. Branch history/other repositories and NAS are not exhaustively scanned.",
            "A matching term in JSON does not establish empirical tachyon detection, retrocausal signaling or quantum advantage.",
            "The JSON/JSONL parsing status is independently recorded rather than assuming every historical artifact is well formed.",
            "The direct match list includes any match in filename OR actual contents; contextual retrocausal-only mentions are kept separate."
        ]
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,default=Path("."))
    ap.add_argument("--out",type=Path,default=Path("evidence/tachyon-inventory.json"))
    ap.add_argument("--json-only",action="store_true")
    args=ap.parse_args()
    out=build_inventory(args.root.resolve(),include_jsonl=not args.json_only)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"schema":out["schema"],"totals":out["totals"],
                      "direct_paths":[r["path"] for r in out["direct_matches"]],
                      "context_only_paths":[r["path"] for r in out["retrocausal_context_only"]][:40]},
                     ensure_ascii=False))
    if out["read_errors"]:
        raise SystemExit("Some JSON files could not be read. See report.")


if __name__=="__main__":
    main()
