#!/usr/bin/env python3
"""Targeted OONI raw-measurement harvester for the TSPU/DPI-DNA audit.

Passive/open-data only. It does not probe target networks. It queries OONI's public
Measurements API at a deliberately modest rate, downloads a bounded sample of raw
measurement JSON, and emits normalized failure/event extracts plus cryptographic hashes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

API = "https://api.ooni.io/api/v1"
UA = "janus-meta-registry-dpi-dna-audit/1.0 (+passive-open-data-research)"
OUT = Path(os.environ.get("DPI_DNA_OUT", "dpi-dna-raw-harvest"))
MAX_RAW_PER_CASE = int(os.environ.get("MAX_RAW_PER_CASE", "30"))
REQUEST_DELAY = float(os.environ.get("OONI_REQUEST_DELAY", "0.35"))

CASES = [
    {
        "id": "kg_as50223_megacom_tiktok_2024",
        "role": "KNOWN_PROTEI_DPI_NETWORK",
        "query": {
            "probe_cc": "KG",
            "probe_asn": "AS50223",
            "test_name": "web_connectivity",
            "domain": "www.tiktok.com",
            "since": "2024-04-18T00:00:00",
            "until": "2024-04-30T23:59:59",
            "limit": "100",
            "order": "asc",
        },
    },
    {
        "id": "cu_as27725_signal_11j_2021",
        "role": "CUBA_PROTEST_TLS_RST_CANDIDATE",
        "query": {
            "probe_cc": "CU",
            "probe_asn": "AS27725",
            "test_name": "signal",
            "since": "2021-07-11T00:00:00",
            "until": "2021-07-16T23:59:59",
            "limit": "100",
            "order": "asc",
        },
    },
    {
        "id": "cu_as27725_web_11j_2021",
        "role": "CUBA_PROTEST_WEB_TLS_CANDIDATE",
        "query": {
            "probe_cc": "CU",
            "probe_asn": "AS27725",
            "test_name": "web_connectivity",
            "since": "2021-07-11T00:00:00",
            "until": "2021-07-16T23:59:59",
            "limit": "100",
            "order": "asc",
        },
        "preferred_domains": [
            "signal.org", "telegram.org", "whatsapp.com", "facebook.com",
            "instagram.com", "youtube.com", "tiktok.com"
        ],
    },
    {
        "id": "cu_as27725_2017_rst_blockpage_controls",
        "role": "CUBA_2017_DPI_RST_REFERENCE",
        "queries": [
            {
                "probe_cc": "CU", "probe_asn": "AS27725", "test_name": "web_connectivity",
                "input": url, "since": "2017-05-29T00:00:00", "until": "2017-06-10T23:59:59",
                "limit": "100", "order": "asc"
            }
            for url in [
                "http://martinoticias.com",
                "http://www.cubaencuentro.com",
                "http://www.voanews.com",
                "http://www.14ymedio.com/",
                "http://www.directorio.org",
            ]
        ],
    },
]

FAILURE_RE = re.compile(
    r"(connection[_ -]?reset|timeout|generic_timeout_error|eof|ssl|tls|dns_|nxdomain|"
    r"network_unreachable|host_unreachable|connection_refused|broken_pipe|io_error)", re.I
)
INTERESTING_KEYS = {
    "failure", "operation", "address", "endpoint", "transaction_id", "t", "num_bytes",
    "proto", "protocol", "tags", "network", "blocking", "accessible", "status",
    "signal_backend_status", "signal_backend_failure", "tcp_connect", "network_events",
    "tls_handshakes", "queries", "requests"
}


def http_json(url: str) -> tuple[Any, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        body = r.read()
    time.sleep(REQUEST_DELAY)
    return json.loads(body), body


def list_measurements(query: dict[str, str]) -> list[dict[str, Any]]:
    url = API + "/measurements?" + urllib.parse.urlencode(query)
    obj, _ = http_json(url)
    return obj.get("results", [])


def recursively_extract(obj: Any, path: str = "$") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        if "failure" in obj and obj.get("failure") not in (None, False, ""):
            events.append({k: obj.get(k) for k in obj.keys() if k in INTERESTING_KEYS})
            failures.append({"path": path + ".failure", "value": obj.get("failure")})
        for k, v in obj.items():
            p = f"{path}.{k}"
            if isinstance(v, str) and FAILURE_RE.search(v):
                failures.append({"path": p, "value": v})
            f2, e2 = recursively_extract(v, p)
            failures.extend(f2)
            events.extend(e2)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            f2, e2 = recursively_extract(v, f"{path}[{i}]")
            failures.extend(f2)
            events.extend(e2)
    return failures, events


def normalize_measurement(case_id: str, meta: dict[str, Any], raw: dict[str, Any], raw_bytes: bytes) -> dict[str, Any]:
    failures, events = recursively_extract(raw.get("test_keys", raw))
    # Deduplicate identical path/value records caused by nested captures.
    seen = set()
    dedup_failures = []
    for f in failures:
        key = (f.get("path"), json.dumps(f.get("value"), sort_keys=True, default=str))
        if key not in seen:
            seen.add(key)
            dedup_failures.append(f)
    measurement_uid = raw.get("measurement_uid") or raw.get("id")
    return {
        "case_id": case_id,
        "measurement_uid": measurement_uid,
        "report_id": meta.get("report_id") or raw.get("report_id"),
        "measurement_url": meta.get("measurement_url"),
        "measurement_start_time": meta.get("measurement_start_time") or raw.get("measurement_start_time"),
        "probe_cc": raw.get("probe_cc") or meta.get("probe_cc"),
        "probe_asn": raw.get("probe_asn") or meta.get("probe_asn"),
        "probe_network_name": raw.get("probe_network_name"),
        "test_name": raw.get("test_name") or meta.get("test_name"),
        "test_version": raw.get("test_version"),
        "input": raw.get("input") if "input" in raw else meta.get("input"),
        "anomaly": meta.get("anomaly"),
        "confirmed": meta.get("confirmed"),
        "failure_flag": meta.get("failure"),
        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "test_keys_top_level": sorted(list((raw.get("test_keys") or {}).keys())),
        "failure_observations": dedup_failures[:250],
        "failure_event_objects": events[:100],
    }


def main() -> None:
    raw_root = OUT / "raw"
    norm_root = OUT / "normalized"
    raw_root.mkdir(parents=True, exist_ok=True)
    norm_root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "schema": "hawkar.tspu.dpi_dna.raw_harvest.v1",
        "source": "OONI public Measurements API",
        "passive_only": True,
        "request_policy": {"max_raw_per_case": MAX_RAW_PER_CASE, "delay_seconds": REQUEST_DELAY},
        "cases": {},
        "pcap_status": {
            "ooni": "RAW_JSON_AVAILABLE; PCAP_NOT_NORMALLY_INCLUDED_IN_PUBLIC_MEASUREMENT_BODY",
            "tspu_imc2022": "PAPER_DESCRIBES_PACKET_LEVEL_EXPERIMENTS; PUBLIC_PCAP_NOT_CONFIRMED_BY_THIS_RUN",
        },
    }

    for case in CASES:
        cid = case["id"]
        metas: list[dict[str, Any]] = []
        queries = case.get("queries") or [case["query"]]
        query_errors = []
        for q in queries:
            try:
                metas.extend(list_measurements(q))
            except Exception as exc:
                query_errors.append({"query": q, "error": repr(exc)})

        # Stable dedup by raw measurement URL.
        dedup: dict[str, dict[str, Any]] = {}
        for m in metas:
            u = m.get("measurement_url") or (m.get("report_id", "") + "|" + str(m.get("input")))
            dedup[u] = m
        metas = list(dedup.values())

        preferred = case.get("preferred_domains", [])
        if preferred:
            def score(m: dict[str, Any]) -> tuple[int, str]:
                inp = str(m.get("input") or "").lower()
                hit = any(d in inp for d in preferred)
                return (0 if hit else 1, str(m.get("measurement_start_time") or ""))
            metas.sort(key=score)

        selected = metas[:MAX_RAW_PER_CASE]
        normalized: list[dict[str, Any]] = []
        raw_dir = raw_root / cid
        raw_dir.mkdir(parents=True, exist_ok=True)
        fetch_errors = []

        for idx, meta in enumerate(selected):
            url = meta.get("measurement_url")
            if not url:
                fetch_errors.append({"meta": meta, "error": "NO_MEASUREMENT_URL"})
                continue
            try:
                raw, raw_bytes = http_json(url)
                rid = raw.get("measurement_uid") or raw.get("report_id") or f"sample-{idx:03d}"
                safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(rid))[:160]
                (raw_dir / f"{safe}.json").write_bytes(raw_bytes)
                normalized.append(normalize_measurement(cid, meta, raw, raw_bytes))
            except Exception as exc:
                fetch_errors.append({"measurement_url": url, "error": repr(exc)})

        (norm_root / f"{cid}.json").write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n")
        failures = Counter()
        test_versions = Counter()
        inputs = Counter()
        for n in normalized:
            test_versions[str(n.get("test_version"))] += 1
            inputs[str(n.get("input"))] += 1
            for f in n.get("failure_observations", []):
                failures[str(f.get("value"))] += 1

        manifest["cases"][cid] = {
            "role": case["role"],
            "queries": queries,
            "listed_measurements": len(metas),
            "selected_for_raw_fetch": len(selected),
            "raw_fetched": len(normalized),
            "query_errors": query_errors,
            "fetch_errors": fetch_errors,
            "failure_value_counts": failures.most_common(50),
            "test_version_counts": test_versions.most_common(),
            "top_inputs": inputs.most_common(30),
        }

    (OUT / "DPI-DNA-RAW-HARVEST-MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
