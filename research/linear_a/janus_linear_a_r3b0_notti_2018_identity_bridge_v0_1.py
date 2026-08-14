from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import urllib.request
from datetime import datetime, timezone

BASE = "https://raw.githubusercontent.com/mwenge/lineara.xyz/{commit}/items/{path}.html"


def fetch_text(url: str) -> tuple[int | None, bytes, str | None]:
    req = urllib.request.Request(url, headers={"User-Agent":"JANUS-Linear-A-identity-bridge/0.1"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return getattr(resp, "status", None), resp.read(), resp.headers.get("Content-Type")


def normalized(s: str) -> str:
    return re.sub(r"\s+", "", s).upper()


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--out", required=True)
    args=ap.parse_args()
    spec_path=pathlib.Path(args.spec)
    inv_path=pathlib.Path(args.inventory)
    out_path=pathlib.Path(args.out)
    spec=json.loads(spec_path.read_text(encoding="utf-8"))
    inv=json.loads(inv_path.read_text(encoding="utf-8"))
    commit=spec["reference"]["commit"]

    raw_inventory="\n".join(x["raw_line"] for x in inv["selected_lines"])
    inv_norm=normalized(raw_inventory)

    alias_expected={
        "THEtab.4":"THE7",
        "THEtab.6":"THE8",
        "THEtab.5":"THE9",
        "THEfr.1":"THE10",
        "THEfr.2":"THE11",
        "THEfr.3":"THE12",
    }
    fetch_cache={}
    bridge=[]
    for candidate in spec["predeclared_bridge_candidates"]:
        ref=candidate["reference_id"]
        url=BASE.format(commit=commit, path=ref)
        if ref not in fetch_cache:
            status,data,ctype=fetch_text(url)
            text=data.decode("utf-8", errors="replace")
            fetch_cache[ref]={
                "url":url,"http_status":status,"content_type":ctype,"bytes":len(data),
                "sha256":hashlib.sha256(data).hexdigest(),"text":text,
            }
        rec=fetch_cache[ref]
        canonical_ok=normalized(ref) in normalized(rec["text"])
        if candidate["basis"] == "EXACT_CANONICAL_NAME":
            alias_ok=True
            source_presence=normalized(candidate["notti_id"]) in inv_norm
        else:
            expected_alias=alias_expected[ref]
            alias_ok=normalized(expected_alias) in normalized(rec["text"])
            if candidate["notti_id"] == "THE7":
                source_presence=("THE7-12" in inv_norm and "THE7A" in inv_norm and "THE7B" in inv_norm)
            else:
                source_presence=normalized(candidate["notti_id"]) in inv_norm
        bridge.append({
            **candidate,
            "reference_url":rec["url"],
            "reference_http_status":rec["http_status"],
            "reference_bytes":rec["bytes"],
            "reference_sha256":rec["sha256"],
            "source_inventory_presence":source_presence,
            "reference_canonical_presence":canonical_ok,
            "required_alias_presence":alias_ok,
            "bridge_pass":bool(rec["http_status"]==200 and source_presence and canonical_ok and alias_ok),
        })

    collision_url=BASE.format(commit=commit, path="THEZb15")
    status,data,ctype=fetch_text(collision_url)
    collision_text=data.decode("utf-8", errors="replace")
    collision={
        "reference_id":"THEZb15",
        "reference_url":collision_url,
        "http_status":status,
        "bytes":len(data),
        "sha256":hashlib.sha256(data).hexdigest(),
        "contains_alias_THEZb14":normalized("THEZb14") in normalized(collision_text),
        "contains_name_THEZb15":normalized("THEZb15") in normalized(collision_text),
        "notti_inventory_contains_distinct_THEZb14":normalized("THEZb14") in inv_norm,
        "notti_inventory_contains_distinct_THEZb15":normalized("THEZb15") in inv_norm,
        "classification":"UNRESOLVED_ALIAS_COLLISION_NO_SILENT_MAPPING",
    }
    collision["collision_proved"] = all([
        collision["http_status"]==200,
        collision["contains_alias_THEZb14"],collision["contains_name_THEZb15"],
        collision["notti_inventory_contains_distinct_THEZb14"],collision["notti_inventory_contains_distinct_THEZb15"],
    ])

    subrows={
        "THE7A_present": "THE7A" in inv_norm,
        "THE7B_present": "THE7B" in inv_norm,
        "classification":"SUBROW_OF_BRIDGED_DOCUMENT_NOT_STANDALONE_ID",
    }
    subrows["pass"] = subrows["THE7A_present"] and subrows["THE7B_present"]

    checks={
        "inventory_prerequisite_pass":inv["status"]=="ALL_THE_LINES_INVENTORIED_NONBLIND_NO_COMPARISON" and inv["all_checks_pass"] is True,
        "all_13_bridges_pass":len(bridge)==13 and all(x["bridge_pass"] for x in bridge),
        "collision_proved_and_unresolved":collision["collision_proved"] and collision["classification"]=="UNRESOLVED_ALIAS_COLLISION_NO_SILENT_MAPPING",
        "THE7_subrows_preserved":subrows["pass"],
        "reading_comparison_not_performed":spec["rules"]["reading_comparison_performed"] is False,
    }
    passed=all(checks.values())
    result={
        "artifact_uuid":"JANUS-LINEAR-A-R3B-0-NOTTI-2018-IDENTITY-BRIDGE-RESULT-2026-08-14-v0.1",
        "version":"v0.1",
        "node_type":"alternate_editorial_identity_bridge_result",
        "status":"IDENTITY_BRIDGE_13_PASS_ZB14_ZB15_COLLISION_PRESERVED" if passed else "IDENTITY_BRIDGE_NONPASS",
        "executed_at_utc":datetime.now(timezone.utc).isoformat(),
        "frozen_spec":str(spec_path).replace("\\","/"),
        "inventory":str(inv_path).replace("\\","/"),
        "reference":spec["reference"],
        "bridged_identities":bridge,
        "unresolved_alias_collision":collision,
        "THE7_subrows":subrows,
        "summary":{
            "bridged_identity_count":sum(1 for x in bridge if x["bridge_pass"]),
            "expected_bridge_count":13,
            "unresolved_collision_source_rows":["THEZB14","THEZB15"],
            "standalone_mapping_for_collision_created":False,
            "reading_comparison_performed":False,
        },
        "checks":checks,
        "all_checks_pass":passed,
        "next_atomic_requirement":"Extract complete source reading spans for all 13 bridged identities plus unresolved rows, freeze representation-normalization contract, then compare every bridged document against exact reference without resolving the Zb14/Zb15 collision by guesswork.",
        "claim_ceiling":spec["claim_ceiling"],
    }
    out_path.parent.mkdir(parents=True,exist_ok=True)
    out_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"summary":result["summary"],"checks":checks},indent=2))
    return 0 if passed else 2

if __name__=="__main__":
    raise SystemExit(main())
