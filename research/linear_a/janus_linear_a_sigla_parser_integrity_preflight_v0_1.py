#!/usr/bin/env python3
"""JANUS Linear A SigLA full-universe parser-integrity preflight v0.1.

Technical admission gate only. It validates the frozen SigLA database asset, then attempts the
complete 686-document identity bridge without replacement. It cross-checks source-native
reported word count, machine seq-pattern anchors, and (for positive pages) the independently
validated word-N <-> index-word-N.html ordinal relation. It does NOT compute any candidate,
role, recurrence, permutation, significance, transliteration reveal, or semantic score.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

import janus_linear_a_sigla_inventory_audit as inv
import janus_linear_a_sigla_structural_schema_probe_v0_1 as structural

SPEC_PATH = "data/JANUS-LINEAR-A-SIGLA-PARSER-INTEGRITY-PREFLIGHT-SPEC-2026-08-14-v0.1.json"
BRIDGE_RESULT_NAME = "JANUS-LINEAR-A-SIGLA-DOCUMENT-IDENTITY-BRIDGE-RESULT-2026-08-14-v0.1.json"
EXPECTED_BRIDGE_COUNT = 686
REQUIRED_DB_SHA = "cc624f148fd84c94fd2910b0adf92ecace25f52f9175664122bdf8384a8f1b9d"
REQUIRED_DB_BYTES = 2516528
REQUIRED_SCRIPTS = {"../../database.js", "../../sigilWeb.bc.js"}
REQUIRED_STYLESHEET = "../../style.css"
REQUIRED_CLASSES = {"document-metadata", "document-view"}
SEQ_PREFIX = "../../search-sequence.html#"
SEQ_MARKER = "word-match @ !seq-pattern:"
POPUP_RE = re.compile(r"^word-([0-9]+)$")
SVG_HREF_RE = re.compile(r"(?:^|/)index-word-([0-9]+)\.html$")
WORD_COUNT_RE = re.compile(r"\b([0-9]+)\s+words?\b", flags=re.I)
SKIP_VISIBLE_TAGS = {"script", "style"}


class InterfaceParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors = []
        self.scripts = []
        self.stylesheets = []
        self.classes = set()
        self.visible_parts = []
        self._anchor = None
        self._skip_depth = 0

    @staticmethod
    def norm(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        amap = dict(attrs)
        if tag in SKIP_VISIBLE_TAGS:
            self._skip_depth += 1
        for cls in (amap.get("class") or "").split():
            if cls:
                self.classes.add(cls)
        if tag == "a":
            self._anchor = {"href": amap.get("href") or "", "parts": []}
        elif tag == "script":
            src = amap.get("src")
            if src:
                self.scripts.append(src)
        elif tag == "link":
            rel = {x.lower() for x in (amap.get("rel") or "").split()}
            href = amap.get("href")
            if "stylesheet" in rel and href:
                self.stylesheets.append(href)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "a" and self._anchor is not None:
            self.anchors.append({
                "href": self._anchor["href"],
                "text": self.norm(" ".join(self._anchor["parts"])),
            })
            self._anchor = None
        if tag in SKIP_VISIBLE_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0 and data:
            self.visible_parts.append(data)
        if self._anchor is not None and data:
            self._anchor["parts"].append(data)


def find_unique(root: Path, filename: str) -> Path:
    matches = list(root.rglob(filename))
    if len(matches) != 1:
        raise SystemExit(f"ARTIFACT_FILE_RESOLUTION_FAIL:{filename}:{len(matches)}")
    return matches[0]


def safe_snapshot_name(bridge_key: str) -> str:
    suffix = hashlib.sha256(bridge_key.encode("utf-8")).hexdigest()[:16]
    return f"SIGLA-parser-preflight-{suffix}.html"


def fetch_once(url: str, timeout: int):
    try:
        status, final_url, content_type, body = inv.fetch_bytes(url, timeout=timeout)
        return {
            "transport_ok": True,
            "http_status": status,
            "final_url": final_url,
            "content_type": content_type,
            "body": body,
            "error_class": None,
            "error_message": None,
        }
    except urllib.error.HTTPError as exc:
        return {
            "transport_ok": True,
            "http_status": exc.code,
            "final_url": getattr(exc, "url", url),
            "content_type": exc.headers.get("Content-Type") if exc.headers else None,
            "body": b"",
            "error_class": "HTTPError",
            "error_message": str(exc),
        }
    except Exception as exc:  # transport exception: one frozen retry is allowed
        return {
            "transport_ok": False,
            "http_status": None,
            "final_url": None,
            "content_type": None,
            "body": b"",
            "error_class": type(exc).__name__,
            "error_message": str(exc),
        }


def fetch_with_policy(url: str, timeout: int, retries: int):
    attempts = []
    for attempt in range(retries + 1):
        got = fetch_once(url, timeout)
        attempts.append({k: v for k, v in got.items() if k != "body"})
        if got["transport_ok"]:
            got["attempts"] = attempts
            return got
        if attempt < retries:
            time.sleep(0.25)
    got["attempts"] = attempts
    return got


def ancestor_has_tag(node, tag: str, stop) -> bool:
    cur = node.parent
    while cur is not None and cur is not stop:
        if cur.tag == tag:
            return True
        cur = cur.parent
    return False


def extract_sequences(anchors):
    sequences = []
    malformed_marker_anchors = 0
    for anchor in anchors:
        href = anchor.get("href") or ""
        if not href.startswith(SEQ_PREFIX):
            continue
        if SEQ_MARKER not in href:
            continue
        tail = href.split(SEQ_MARKER, 1)[1]
        if "//" not in tail:
            malformed_marker_anchors += 1
            continue
        seq = tail.split("//", 1)[0]
        if not seq:
            malformed_marker_anchors += 1
            continue
        sequences.append(seq)
    return sequences, malformed_marker_anchors


def structural_counts(html_text: str):
    parser = structural.TreeParser()
    parser.feed(html_text)
    nodes = list(structural.walk(parser.root))
    containers = [n for n in nodes if "document-view" in n.classes]
    if len(containers) != 1:
        return {
            "document_view_container_count": len(containers),
            "popup_word_count": None,
            "svg_word_anchor_count": None,
            "word_class_element_count": None,
            "popup_ids": [],
            "svg_hrefs": [],
            "strict_ordinal_relation": False,
        }
    container = containers[0]
    under = list(structural.walk(container))
    word_nodes = [n for n in under if "word" in n.classes]
    popup = [
        n for n in under
        if n.tag == "span" and {"popup", "word"}.issubset(set(n.classes))
    ]
    svg_word = [
        n for n in under
        if n.tag == "a" and "word" in n.classes and ancestor_has_tag(n, "svg", container)
    ]
    popup_ids = [n.attrs.get("id") or "" for n in popup]
    svg_hrefs = [n.attrs.get("href") or "" for n in svg_word]
    popup_matches = [POPUP_RE.fullmatch(x) for x in popup_ids]
    svg_matches = [SVG_HREF_RE.search(x) for x in svg_hrefs]
    popup_full = bool(popup_ids) and all(m is not None for m in popup_matches)
    svg_full = bool(svg_hrefs) and all(m is not None for m in svg_matches)
    popup_ord = [m.group(1) for m in popup_matches if m is not None]
    svg_ord = [m.group(1) for m in svg_matches if m is not None]
    expected = [str(i) for i in range(len(popup_ord))]
    strict = (
        popup_full
        and svg_full
        and len(set(popup_ord)) == len(popup_ord)
        and len(set(svg_ord)) == len(svg_ord)
        and popup_ord == svg_ord
        and popup_ord == expected
    )
    return {
        "document_view_container_count": 1,
        "popup_word_count": len(popup),
        "svg_word_anchor_count": len(svg_word),
        "word_class_element_count": len(word_nodes),
        "popup_ids": popup_ids,
        "svg_hrefs": svg_hrefs,
        "strict_ordinal_relation": strict,
    }


def evaluate_document(item, timeout: int, retries: int, snapshot_dir: Path | None):
    key = item["bridge_key"]
    sigla_id = item["sigla_id"]
    encoded = urllib.parse.quote(sigla_id, safe="")
    requested = f"https://sigla.phis.me/document/{encoded}/index-word.html"
    got = fetch_with_policy(requested, timeout, retries)
    body = got.pop("body")
    base = {
        "bridge_key": key,
        "sigla_id": sigla_id,
        "requested_url": requested,
        "attempts": got["attempts"],
        "http_status": got["http_status"],
        "final_url": got["final_url"],
        "content_type": got["content_type"],
        "content_length_bytes": len(body),
        "content_sha256": hashlib.sha256(body).hexdigest() if body else None,
        "snapshot_filename": None,
        "visible_transliteration_stored": False,
        "raw_sequence_list_stored": False,
    }
    if not got["transport_ok"] or got["http_status"] != 200 or not body:
        base.update({
            "state": "NOT_EVALUABLE_FETCH_OR_INTERFACE",
            "interface_failures": ["transport_or_http"],
        })
        return base

    if snapshot_dir is not None:
        name = safe_snapshot_name(key)
        (snapshot_dir / name).write_bytes(body)
        base["snapshot_filename"] = name

    html_text = body.decode("utf-8", errors="replace")
    ip = InterfaceParser()
    ip.feed(html_text)
    visible = ip.norm(" ".join(ip.visible_parts))
    sign_view_count = sum(1 for a in ip.anchors if a["text"] == "[sign view]")
    missing_scripts = sorted(REQUIRED_SCRIPTS - set(ip.scripts))
    missing_classes = sorted(REQUIRED_CLASSES - ip.classes)
    missing_style = REQUIRED_STYLESHEET not in set(ip.stylesheets)
    st = structural_counts(html_text)
    interface_failures = []
    if sign_view_count < 1:
        interface_failures.append("missing_sign_view_anchor")
    if missing_scripts:
        interface_failures.append("missing_required_scripts")
    if missing_style:
        interface_failures.append("missing_required_stylesheet")
    if missing_classes:
        interface_failures.append("missing_required_classes")
    if st["document_view_container_count"] != 1:
        interface_failures.append("document_view_container_count_not_one")

    base.update({
        "interface": {
            "sign_view_anchor_count": sign_view_count,
            "missing_required_scripts": missing_scripts,
            "missing_required_stylesheet": missing_style,
            "missing_required_classes": missing_classes,
            "document_view_container_count": st["document_view_container_count"],
        }
    })
    if interface_failures:
        base.update({
            "state": "NOT_EVALUABLE_FETCH_OR_INTERFACE",
            "interface_failures": interface_failures,
        })
        return base

    count_matches = WORD_COUNT_RE.findall(visible)
    if len(count_matches) != 1:
        base.update({
            "state": "FAIL_REPORTED_COUNT_PARSE",
            "reported_count_match_count": len(count_matches),
        })
        return base
    reported = int(count_matches[0])
    sequences, malformed = extract_sequences(ip.anchors)
    sequence_receipt = hashlib.sha256(
        json.dumps(sequences, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    base.update({
        "reported_word_count": reported,
        "seq_pattern_anchor_count": len(sequences),
        "malformed_seq_pattern_marker_anchor_count": malformed,
        "sequence_list_sha256": sequence_receipt,
        "structure": {
            "popup_word_count": st["popup_word_count"],
            "svg_word_anchor_count": st["svg_word_anchor_count"],
            "word_class_element_count": st["word_class_element_count"],
            "strict_ordinal_relation": st["strict_ordinal_relation"],
        },
    })

    if malformed or len(sequences) != reported:
        base["state"] = "FAIL_SEQUENCE_COUNT_MISMATCH"
        return base

    if reported == 0:
        if st["popup_word_count"] != 0 or st["svg_word_anchor_count"] != 0:
            base["state"] = "FAIL_ZERO_WORD_STRUCTURE_LEAK"
        else:
            base["state"] = "PASS_ZERO_WORD"
        return base

    if st["popup_word_count"] != reported or st["svg_word_anchor_count"] != reported:
        base["state"] = "FAIL_POSITIVE_WORD_STRUCTURE_COUNT"
        return base
    if not st["strict_ordinal_relation"]:
        base["state"] = "FAIL_STRICT_ORDINAL_RELATION"
        return base
    base["state"] = "PASS_POSITIVE_WORD"
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge-artifact-root", required=True)
    ap.add_argument("--spec", default=SPEC_PATH)
    ap.add_argument("--out", required=True)
    ap.add_argument("--snapshot-dir", default=None)
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    if spec.get("status") != "FROZEN_BEFORE_686_DOCUMENT_VALIDATION":
        raise SystemExit("SPEC_STATUS_FAIL")
    if spec.get("scientific_claim_bearing") is not False:
        raise SystemExit("SPEC_CLAIM_FLAG_FAIL")
    if spec["frozen_universe"]["document_count"] != EXPECTED_BRIDGE_COUNT:
        raise SystemExit("SPEC_UNIVERSE_COUNT_FAIL")

    bridge_path = find_unique(Path(args.bridge_artifact_root), BRIDGE_RESULT_NAME)
    bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
    pairs = bridge.get("bridge", {}).get("matched_pairs") or []
    if len(pairs) != EXPECTED_BRIDGE_COUNT:
        raise SystemExit(f"BRIDGE_COUNT_FAIL:{len(pairs)}")
    universe = [
        {"bridge_key": p["bridge_key"], "sigla_id": p["sigla_id"]}
        for p in pairs
    ]
    if len({x["bridge_key"] for x in universe}) != EXPECTED_BRIDGE_COUNT:
        raise SystemExit("BRIDGE_KEY_UNIQUENESS_FAIL")

    # Source asset canary is checked before any document request.
    try:
        db_status, db_final, db_type, db_body = inv.fetch_bytes(
            spec["frozen_sigla_asset_gate"]["url"],
            timeout=spec["network_policy"]["request_timeout_seconds"],
        )
        db_error = None
    except Exception as exc:
        db_status, db_final, db_type, db_body = None, None, None, b""
        db_error = f"{type(exc).__name__}:{exc}"
    db_sha = hashlib.sha256(db_body).hexdigest() if db_body else None
    db_gate = (
        db_status == 200
        and len(db_body) == REQUIRED_DB_BYTES
        and db_sha == REQUIRED_DB_SHA
    )

    result_base = {
        "artifact_uuid": "JANUS-LINEAR-A-SIGLA-PARSER-INTEGRITY-PREFLIGHT-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "title": "JANUS Linear A SigLA full-universe parser-integrity preflight result",
        "node_type": "technical_parser_integrity_admission_result",
        "scientific_claim_bearing": False,
        "frozen_spec": {"path": SPEC_PATH},
        "source_asset_gate": {
            "requested_url": spec["frozen_sigla_asset_gate"]["url"],
            "http_status": db_status,
            "final_url": db_final,
            "content_type": db_type,
            "bytes": len(db_body),
            "sha256": db_sha,
            "required_bytes": REQUIRED_DB_BYTES,
            "required_sha256": REQUIRED_DB_SHA,
            "pass": db_gate,
            "error": db_error,
        },
        "universe": {
            "document_count": EXPECTED_BRIDGE_COUNT,
            "sampling": "NONE_FULL_FROZEN_UNIVERSE",
            "replacement_used": False,
            "mwenge_transcription_content_accessed": False,
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not db_gate:
        result = {
            **result_base,
            "status": "BLOCKED_SOURCE_ASSET_CANARY_FAIL",
            "documents": [],
            "summary": {
                "attempted_document_count": 0,
                "interface_evaluable_count": 0,
                "pass_document_count": 0,
                "deterministic_mismatch_count": 0,
                "parser_integrity_success_fraction_of_686": 0.0,
                "R3A_4_scoring_admitted": False,
            },
            "claim_ceiling": {
                "full_universe_sigla_parser_integrity_validated": False,
                "R3A_4_scoring_admitted": False,
                "external_transcription_replication_established": False,
                "new_lexical_anchor_established": False,
                "decipherment_established": False,
                "promotion": "BLOCKED",
            },
        }
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result["summary"], sort_keys=True))
        return

    snapshot_dir = Path(args.snapshot_dir) if args.snapshot_dir else None
    if snapshot_dir is not None:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
    max_workers = spec["network_policy"]["maximum_concurrent_document_fetches"]
    timeout = spec["network_policy"]["request_timeout_seconds"]
    retries = spec["network_policy"]["automatic_retry_count"]

    rows_by_key = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {
            pool.submit(evaluate_document, item, timeout, retries, snapshot_dir): item["bridge_key"]
            for item in universe
        }
        for future in concurrent.futures.as_completed(future_map):
            key = future_map[future]
            try:
                rows_by_key[key] = future.result()
            except Exception as exc:
                rows_by_key[key] = {
                    "bridge_key": key,
                    "sigla_id": next(x["sigla_id"] for x in universe if x["bridge_key"] == key),
                    "state": "NOT_EVALUABLE_FETCH_OR_INTERFACE",
                    "unexpected_worker_error": f"{type(exc).__name__}:{exc}",
                    "visible_transliteration_stored": False,
                    "raw_sequence_list_stored": False,
                }

    # Preserve frozen bridge order, not thread completion order.
    rows = [rows_by_key[x["bridge_key"]] for x in universe]
    states = Counter(x["state"] for x in rows)
    not_eval = states["NOT_EVALUABLE_FETCH_OR_INTERFACE"]
    interface_evaluable = EXPECTED_BRIDGE_COUNT - not_eval
    pass_count = states["PASS_ZERO_WORD"] + states["PASS_POSITIVE_WORD"]
    deterministic_fail_states = [
        "FAIL_REPORTED_COUNT_PARSE",
        "FAIL_SEQUENCE_COUNT_MISMATCH",
        "FAIL_ZERO_WORD_STRUCTURE_LEAK",
        "FAIL_POSITIVE_WORD_STRUCTURE_COUNT",
        "FAIL_STRICT_ORDINAL_RELATION",
    ]
    mismatch_count = sum(states[x] for x in deterministic_fail_states)
    pass_fraction = pass_count / EXPECTED_BRIDGE_COUNT
    readiness = (
        pass_count >= spec["readiness_gate_inherited_from_frozen_R3A_4"]["minimum_parse_success_documents"]
        and pass_fraction >= spec["readiness_gate_inherited_from_frozen_R3A_4"]["minimum_parse_success_fraction_of_686"]
        and mismatch_count == 0
    )

    result = {
        **result_base,
        "status": "PREFLIGHT_EXECUTED_ADMITTED" if readiness else "PREFLIGHT_EXECUTED_BLOCKED",
        "documents": rows,
        "summary": {
            "attempted_document_count": EXPECTED_BRIDGE_COUNT,
            "state_counts": dict(sorted(states.items())),
            "interface_evaluable_count": interface_evaluable,
            "not_evaluable_count": not_eval,
            "pass_zero_word_count": states["PASS_ZERO_WORD"],
            "pass_positive_word_count": states["PASS_POSITIVE_WORD"],
            "pass_document_count": pass_count,
            "deterministic_mismatch_count": mismatch_count,
            "parser_integrity_success_fraction_of_686": pass_fraction,
            "minimum_parse_success_documents": spec["readiness_gate_inherited_from_frozen_R3A_4"]["minimum_parse_success_documents"],
            "minimum_parse_success_fraction_of_686": spec["readiness_gate_inherited_from_frozen_R3A_4"]["minimum_parse_success_fraction_of_686"],
            "R3A_4_scoring_admitted": readiness,
        },
        "blindness_receipt": {
            "positional_role_scores_computed": False,
            "candidate_recurrence_scores_computed": False,
            "permutation_tests_computed": False,
            "visible_transliteration_stored": False,
            "raw_sequence_lists_stored": False,
            "per_document_exact_sequence_list_sha256_stored": True,
        },
        "epistemic_gate": {
            "full_universe_sigla_parser_integrity_validated": readiness,
            "R3A_4_scoring_admitted": readiness,
            "cross_digitization_content_replication_established": False,
            "external_transcription_replication_established": False,
            "new_lexical_anchor_established": False,
            "decipherment_established": False,
            "promotion": "NO_PROMOTION",
        },
        "required_next": (
            [
                "Execute the already frozen R3A_4 SigLA-native blind role discovery without changing its scientific thresholds or partitions.",
                "Carry this preflight result as a parser-integrity admission receipt, not as a lexical or decipherment claim.",
            ]
            if readiness
            else [
                "Do not execute R3A_4 scoring.",
                "Inspect the retained deterministic mismatch/fetch taxonomy and version any parser correction separately without lowering scientific thresholds.",
            ]
        ),
        "claim_ceiling": {
            "full_universe_sigla_parser_integrity_validated": readiness,
            "R3A_4_scoring_admitted": readiness,
            "cross_digitization_content_replication_established": False,
            "external_transcription_replication_established": False,
            "new_lexical_anchor_established": False,
            "decipherment_established": False,
            "promotion": "BLOCKED",
        },
    }
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
