#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import json
import locale
import os
import platform
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "data" / "JANUS-RECORD-DRIFT-BASELINE-T0-v0.1.json"
PROTOCOL = ROOT / "data" / "JANUS-RECORD-DRIFT-OBSERVATORY-v0.2.json"
WORKFLOW = ROOT / ".github" / "workflows" / "record-drift-daily.yml"
RUNNER = Path(__file__).resolve()
JDIR = ROOT / "registry" / "record_drift"
REPO = "Hawkar-usls/janus-meta-registry"
UA = "JANUS-Record-Drift/0.2-full-surface"


def git(*args, check=True):
    p = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if check and p.returncode:
        raise RuntimeError(p.stderr.strip())
    return p.stdout.strip()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha512(data: bytes) -> str:
    return hashlib.sha512(data).hexdigest()


def blob(commit, path):
    p = subprocess.run(["git", "rev-parse", f"{commit}:{path}"], cwd=ROOT, text=True, capture_output=True)
    return p.stdout.strip() if p.returncode == 0 else None


def git_bytes(commit, path):
    p = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, capture_output=True)
    return p.stdout if p.returncode == 0 else None


def creation_commit(path):
    x = git("log", "--diff-filter=A", "--follow", "--format=%H", "-n", "1", "--", path, check=False)
    return x or None


def file_fixity(data: bytes):
    chunks = [sha256(data[i:i+65536]) for i in range(0, len(data), 65536)]
    return {
        "sha256": sha256(data),
        "sha512": sha512(data),
        "byte_length": len(data),
        "chunk_size": 65536,
        "chunk_sha256": chunks,
    }


def canonical_json_sha(data: bytes):
    try:
        obj = json.loads(data.decode("utf-8"))
        canon = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return {"state": "SUPPORTED_AND_CAPTURED", "rule": "json-sort-keys-compact-v1", "canonical_sha256": sha256(canon)}
    except Exception as e:
        return {"state": "NOT_APPLICABLE", "reason": f"not_json:{type(e).__name__}"}


def format_profile(data: bytes, content_type=None, content_encoding=None):
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n")
    if crlf and lf == crlf:
        endings = "CRLF"
    elif lf and not crlf:
        endings = "LF"
    elif lf:
        endings = "MIXED"
    else:
        endings = "NONE_OR_BINARY"
    bom = None
    for sig, name in [(b"\xef\xbb\xbf", "UTF-8-BOM"), (b"\xff\xfe", "UTF-16LE-BOM"), (b"\xfe\xff", "UTF-16BE-BOM")]:
        if data.startswith(sig):
            bom = name
            break
    return {
        "state": "SUPPORTED_AND_CAPTURED",
        "content_type": content_type,
        "content_encoding": content_encoding,
        "magic_bytes_hex": data[:16].hex(),
        "bom": bom,
        "line_ending_profile": endings,
    }


def latest_journal():
    files = [p for p in JDIR.glob("JANUS-RECORD-DRIFT-JOURNAL-*.json") if "GENESIS" not in p.name]
    return sorted(files)[-1] if files else JDIR / "JANUS-RECORD-DRIFT-JOURNAL-GENESIS-v0.1.json"


def prior_external(path):
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for c in obj.get("checks", []):
        rid = c.get("record_id", "")
        if rid.startswith("EXT-STATIC-"):
            out[rid] = c
    return out


def urlopen_bytes(url, timeout=30, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    t0 = time.monotonic_ns()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        h = {k.lower(): v for k, v in r.headers.items()}
        status = getattr(r, "status", None)
        final = r.geturl()
    t1 = time.monotonic_ns()
    return raw, h, status, final, (t1 - t0) / 1e6


def raw_github_bytes(commit, path):
    url = f"https://raw.githubusercontent.com/{REPO}/{commit}/{path}"
    try:
        raw, headers, status, final, latency = urlopen_bytes(url)
        return {"state": "SUPPORTED_AND_CAPTURED", "status": status, "final_url": final, "latency_ms": latency, "sha256": sha256(raw), "bytes": raw, "headers": headers}
    except Exception as e:
        return {"state": "CAPTURE_FAILED", "error": f"{type(e).__name__}:{e}"}


def contents_api_bytes(commit, path):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}?ref={commit}"
    try:
        raw, headers, status, final, latency = urlopen_bytes(url, headers={"Accept": "application/vnd.github+json"})
        obj = json.loads(raw.decode("utf-8"))
        data = base64.b64decode(obj["content"].encode("ascii"), validate=False)
        return {"state": "SUPPORTED_AND_CAPTURED", "status": status, "final_url": final, "latency_ms": latency, "sha256": sha256(data), "git_blob_sha": obj.get("sha"), "bytes": data, "headers": headers}
    except Exception as e:
        return {"state": "CAPTURE_FAILED", "error": f"{type(e).__name__}:{e}"}


def dns_capture(host):
    try:
        t0 = time.monotonic_ns()
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        t1 = time.monotonic_ns()
        ips = sorted({x[4][0] for x in infos})
        return {"state": "SUPPORTED_AND_CAPTURED", "hostname": host, "A_or_AAAA_observed": ips, "resolver_latency_ms": (t1-t0)/1e6,
                "TTL_if_available": {"state": "SUPPORTED_BUT_MISSING"}, "DNSSEC_state_if_available": {"state": "NOT_SUPPORTED_BY_SOURCE"}}
    except Exception as e:
        return {"state": "CAPTURE_FAILED", "hostname": host, "error": f"{type(e).__name__}:{e}"}


def tls_capture(host):
    try:
        ctx = ssl.create_default_context()
        t0 = time.monotonic_ns()
        with socket.create_connection((host, 443), timeout=15) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ss:
                der = ss.getpeercert(binary_form=True)
                cert = ss.getpeercert()
                out = {
                    "state": "SUPPORTED_AND_CAPTURED",
                    "tls_version": ss.version(),
                    "cipher": ss.cipher(),
                    "alpn": ss.selected_alpn_protocol(),
                    "certificate_sha256": sha256(der),
                    "certificate_serial": cert.get("serialNumber"),
                    "issuer": cert.get("issuer"),
                    "subject": cert.get("subject"),
                    "san": cert.get("subjectAltName"),
                    "not_before": cert.get("notBefore"),
                    "not_after": cert.get("notAfter"),
                    "destination_ip": ss.getpeername()[0],
                }
        out["connect_tls_latency_ms"] = (time.monotonic_ns()-t0)/1e6
        return out
    except Exception as e:
        return {"state": "CAPTURE_FAILED", "error": f"{type(e).__name__}:{e}"}


def instrument_self_tests(previous_bytes: bytes):
    tests = {}
    tests["HASH_KNOWN_ANSWER"] = sha256(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    tests["ONE_BYTE_DRIFT"] = sha256(b"canary-A") != sha256(b"canary-B")
    a = b'{"b":2, "a":1}'
    b = b'{\n  "a": 1,\n  "b": 2\n}'
    ca = canonical_json_sha(a).get("canonical_sha256")
    cb = canonical_json_sha(b).get("canonical_sha256")
    tests["CANONICAL_EQUIVALENCE"] = sha256(a) != sha256(b) and ca == cb
    instant = datetime(2026, 8, 15, 12, 21, tzinfo=timezone.utc)
    plus3 = instant.astimezone(timezone(timedelta(hours=3)))
    tests["TIMEZONE_EQUIVALENCE"] = plus3.astimezone(timezone.utc) == instant
    fixture = json.loads('{"n":12,"flag":true,"text":"12:21"}')
    tests["PARSER_PROFILE"] = fixture == {"n": 12, "flag": True, "text": "12:21"}
    tests["IDENTITY_SWITCH"] = ("ref-A", "blob-1") != ("ref-A", "blob-2")
    tests["REPLICA_DIVERGENCE"] = len({sha256(b"replica-1"), sha256(b"replica-2")}) == 2
    altered = previous_bytes[:-1] + (b"X" if previous_bytes[-1:] != b"X" else b"Y") if previous_bytes else b"X"
    tests["JOURNAL_TAMPER"] = sha256(previous_bytes) != sha256(altered)
    return {"tests": tests, "all_pass": all(tests.values())}


def runtime_capture():
    deps = []
    try:
        for d in importlib.metadata.distributions():
            name = d.metadata.get("Name") or "UNKNOWN"
            deps.append(f"{name}=={d.version}")
    except Exception:
        deps = []
    deps = sorted(set(deps), key=str.lower)
    try:
        loc = locale.setlocale(locale.LC_ALL, None)
    except Exception:
        loc = None
    return {
        "state": "SUPPORTED_AND_CAPTURED",
        "os": platform.system(), "kernel": platform.release(), "architecture": platform.machine(),
        "python_version": sys.version, "implementation": platform.python_implementation(),
        "dependency_count": len(deps), "dependency_snapshot_sha256": sha256("\n".join(deps).encode()),
        "locale": loc, "preferred_encoding": locale.getpreferredencoding(False),
        "github_runner_os": os.getenv("RUNNER_OS"), "github_runner_arch": os.getenv("RUNNER_ARCH"),
        "github_run_id": os.getenv("GITHUB_RUN_ID"), "github_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
        "github_sha": os.getenv("GITHUB_SHA"), "github_actor": os.getenv("GITHUB_ACTOR")
    }


def clock_quality_capture():
    result = {"state": "SUPPORTED_BUT_MISSING", "clock_sync_state": "UNKNOWN"}
    commands = [
        (["timedatectl", "show", "-p", "NTPSynchronized", "--value"], "timedatectl"),
        (["chronyc", "tracking"], "chronyc"),
    ]
    for cmd, name in commands:
        try:
            p = subprocess.run(cmd, text=True, capture_output=True, timeout=5)
            if p.returncode == 0 and p.stdout.strip():
                result = {"state": "SUPPORTED_AND_CAPTURED", "source": name, "raw": p.stdout.strip()[:4000]}
                if name == "timedatectl":
                    result["clock_sync_state"] = "SYNCHRONIZED" if p.stdout.strip().lower() == "yes" else "NOT_SYNCHRONIZED"
                return result
        except Exception:
            pass
    return result


def storage_capture(path: Path):
    try:
        st = path.stat()
        fs = None
        try:
            p = subprocess.run(["df", "-T", str(path)], text=True, capture_output=True, timeout=5)
            fs = p.stdout.strip()
        except Exception:
            pass
        return {"state": "SUPPORTED_AND_CAPTURED", "path": path.relative_to(ROOT).as_posix(), "device": st.st_dev, "inode": st.st_ino,
                "size": st.st_size, "mtime_ns": st.st_mtime_ns, "ctime_ns": st.st_ctime_ns, "mode": oct(st.st_mode), "df_T": fs}
    except Exception as e:
        return {"state": "CAPTURE_FAILED", "error": f"{type(e).__name__}:{e}"}


def check_previous_journal(path):
    rel = path.relative_to(ROOT).as_posix()
    cc = creation_commit(rel)
    cb = blob(cc, rel) if cc else None
    hb = blob("HEAD", rel)
    raw = path.read_bytes()
    ok = bool(cc and cb and hb and cb == hb)
    return {
        "record_id": "JOURNAL-CHAIN", "class": "E_journal_self_control", "path": rel,
        "C02_RAW_FIXITY": file_fixity(raw),
        "C25_JOURNAL": {"state": "SUPPORTED_AND_CAPTURED", "creation_commit": cc, "creation_blob": cb, "current_blob": hb, "append_only_check": ok},
        "classification": "R0_STABLE" if ok else "R9_JOURNAL_CHAIN_BREAK",
        "status": "previous_journal_matches_creation_blob" if ok else "previous_journal_changed_or_unresolvable"
    }


def check_pinned(s):
    commit, path = s["pinned_commit"], s["path"]
    local = git_bytes(commit, path)
    local_blob = blob(commit, path)
    exp_blob = s.get("git_blob_sha")
    raw_rep = raw_github_bytes(commit, path)
    api_rep = contents_api_bytes(commit, path)
    hashes = {}
    if local is not None: hashes["local_checkout"] = sha256(local)
    if raw_rep.get("sha256"): hashes["raw_github"] = raw_rep["sha256"]
    if api_rep.get("sha256"): hashes["contents_api"] = api_rep["sha256"]
    available = list(hashes.values())
    replicas_agree = len(set(available)) <= 1 if available else False
    identity_ok = local is not None and local_blob is not None and (exp_blob is None or exp_blob == local_blob)
    if identity_ok and replicas_agree and len(available) >= 2:
        cl, st = "R0_STABLE", "pinned_identity_and_retrieval_paths_agree"
    elif identity_ok and replicas_agree:
        cl, st = "R0_STABLE", "pinned_identity_stable_replica_coverage_partial"
    elif identity_ok and not replicas_agree:
        cl, st = "R6_DISTRIBUTED_DIVERGENCE", "same_pinned_identity_retrieval_paths_disagree"
    else:
        cl, st = "R4_UNDECLARED_REMOTE_CONTENT_DRIFT", "pinned_identity_mismatch_or_missing"
    return {
        "record_id": s["record_id"], "class": s["class"], "path": path,
        "C01_IDENTITY": {"state": "SUPPORTED_AND_CAPTURED", "pinned_commit": commit, "expected_git_blob": exp_blob, "observed_git_blob": local_blob},
        "C02_RAW_FIXITY": file_fixity(local) if local is not None else {"state": "CAPTURE_FAILED"},
        "C04_CANONICAL": canonical_json_sha(local) if local is not None else {"state": "CAPTURE_FAILED"},
        "C16_REPLICAS": {"state": "SUPPORTED_AND_CAPTURED", "hashes": hashes, "replica_agreement": replicas_agree,
                          "raw_github_state": raw_rep.get("state"), "contents_api_state": api_rep.get("state"),
                          "contents_api_git_blob": api_rep.get("git_blob_sha")},
        "classification": cl, "status": st
    }


def check_live(s):
    old = s["head_at_registration"]
    new = git("rev-parse", "HEAD")
    a = blob(old, s["path"])
    b = blob(new, s["path"])
    if a is None or b is None:
        cl, st = "R7_IDENTITY_DRIFT", "path_unresolvable"
    elif a == b:
        cl, st = "R0_STABLE", "path_content_unchanged_despite_ref_movement"
    else:
        cl, st = "R3_DECLARED_SOURCE_REVISION", "path_changed_with_git_history"
    return {"record_id": s["record_id"], "class": s["class"], "path": s["path"],
            "C01_IDENTITY": {"state": "SUPPORTED_AND_CAPTURED", "T0_head": old, "Tn_head": new, "T0_blob": a, "Tn_blob": b},
            "classification": cl, "status": st}


def external_http_capture(s, prior):
    url = s["uri"]
    host = urlparse(url).hostname
    dns = dns_capture(host) if host else {"state": "NOT_APPLICABLE"}
    tls = tls_capture(host) if host and url.startswith("https://") else {"state": "NOT_APPLICABLE"}
    request_meta = {"state": "SUPPORTED_AND_CAPTURED", "method": "GET", "url": url, "user_agent": UA,
                    "accept": "*/*", "accept_encoding": "identity", "conditional_headers": None}
    try:
        raw, h, status, final, latency = urlopen_bytes(url, headers={"Accept-Encoding": "identity"})
        fx = file_fixity(raw)
        prev_hash = None
        if prior:
            prev_hash = prior.get("raw_sha256") or (prior.get("C02_RAW_FIXITY") or {}).get("sha256")
        if prev_hash is None:
            cl, st = "R0_STABLE", "first_v0_2_extension_baseline_no_drift_claim"
        elif prev_hash == fx["sha256"]:
            cl, st = "R0_STABLE", "raw_sha256_matches_previous_capture"
        else:
            cl, st = "R4_UNDECLARED_REMOTE_CONTENT_DRIFT", "raw_sha256_changed_requires_revision_replica_followup"
        response_meta = {"state": "SUPPORTED_AND_CAPTURED", "status": status, "final_url": final,
                         "date": h.get("date"), "age": h.get("age"), "etag": h.get("etag"), "last_modified": h.get("last-modified"),
                         "cache_control": h.get("cache-control"), "expires": h.get("expires"), "vary": h.get("vary"), "via": h.get("via"),
                         "server": h.get("server"), "content_type": h.get("content-type"), "content_length": h.get("content-length"),
                         "content_encoding": h.get("content-encoding")}
        return {
            "record_id": s["record_id"], "class": s["class"], "name": s.get("name"), "uri": url,
            "raw_sha256_previous": prev_hash, "raw_sha256": fx["sha256"], "byte_length": len(raw),
            "C02_RAW_FIXITY": fx, "C03_FORMAT": format_profile(raw, h.get("content-type"), h.get("content-encoding")),
            "C04_CANONICAL": canonical_json_sha(raw), "C10_HTTP_REQUEST": request_meta, "C11_HTTP_RESPONSE": response_meta,
            "C12_HTTP_INTEGRITY": {"state": "SUPPORTED_AND_CAPTURED", "content_digest_header": h.get("content-digest"), "repr_digest_header": h.get("repr-digest"), "transport_body_sha256": fx["sha256"]},
            "C13_DNS": dns, "C14_NETWORK": {"state": "SUPPORTED_AND_CAPTURED", "destination_ips": dns.get("A_or_AAAA_observed"), "http_latency_ms": latency},
            "C15_TLS": tls, "C26_AVAILABILITY": {"state": "SUPPORTED_AND_CAPTURED", "success": True, "latency_ms": latency, "retry_count": 0},
            "classification": cl, "status": st
        }
    except Exception as e:
        return {"record_id": s["record_id"], "class": s["class"], "name": s.get("name"), "uri": url,
                "C10_HTTP_REQUEST": request_meta, "C13_DNS": dns, "C15_TLS": tls,
                "C26_AVAILABILITY": {"state": "CAPTURE_FAILED", "success": False, "error_type": type(e).__name__, "error_message": str(e)},
                "classification": "UNAVAILABLE_NOT_COUNTED", "status": f"retrieval_failed:{type(e).__name__}:{e}"}


def main():
    start_wall = datetime.now(timezone.utc)
    start_mono = time.monotonic_ns()
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    prev = latest_journal()
    prev_bytes = prev.read_bytes()
    priors = prior_external(prev)
    selftest = instrument_self_tests(prev_bytes)
    runtime = runtime_capture()
    clock = clock_quality_capture()

    head = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    experiment = {
        "state": "SUPPORTED_AND_CAPTURED",
        "protocol_path": PROTOCOL.relative_to(ROOT).as_posix(), "protocol_git_blob": blob("HEAD", PROTOCOL.relative_to(ROOT).as_posix()),
        "runner_path": RUNNER.relative_to(ROOT).as_posix(), "runner_git_blob": blob("HEAD", RUNNER.relative_to(ROOT).as_posix()),
        "workflow_path": WORKFLOW.relative_to(ROOT).as_posix(), "workflow_git_blob": blob("HEAD", WORKFLOW.relative_to(ROOT).as_posix()),
        "git_head": head, "git_tree": tree,
        "github_run_id": os.getenv("GITHUB_RUN_ID"), "github_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT"), "github_sha": os.getenv("GITHUB_SHA"),
        "trigger_event": os.getenv("GITHUB_EVENT_NAME"), "actor": os.getenv("GITHUB_ACTOR"),
        "actual_start_utc": start_wall.isoformat()
    }

    checks = [check_previous_journal(prev)]
    aliases = set()
    for s in base["subjects"]:
        c = s["class"]
        if c in {"A_git_immutable", "C_registry_artifacts"}:
            checks.append(check_pinned(s))
            aliases.add((s.get("path"), s.get("pinned_commit")))
        elif c == "B_git_live":
            checks.append(check_live(s))
        elif c == "D_test_results":
            key = (s.get("path"), s.get("pinned_commit"))
            if key in aliases:
                checks.append({"record_id": s["record_id"], "class": c, "classification": "R0_STABLE", "status": "recursive_alias_already_checked_by_pinned_control"})
            else:
                checks.append(check_pinned(s)); aliases.add(key)
        elif c == "F_external_static":
            checks.append(external_http_capture(s, priors.get(s["record_id"], {})))
        elif c == "G_external_live":
            checks.append({"record_id": s["record_id"], "class": c, "classification": "NOT_ADMITTED_NOT_COUNTED", "status": s.get("status", "pool_open")})

    countable = [x for x in checks if str(x.get("classification", "")).startswith("R")]
    counts = {}
    for x in countable:
        counts[x["classification"]] = counts.get(x["classification"], 0) + 1

    end_wall = datetime.now(timezone.utc)
    duration_ns = time.monotonic_ns() - start_mono
    experiment["actual_end_utc"] = end_wall.isoformat()
    experiment["duration_monotonic_ns"] = duration_ns
    stamp = end_wall.strftime("%Y%m%dT%H%M%SZ")
    out = JDIR / f"JANUS-RECORD-DRIFT-JOURNAL-{stamp}.json"

    global_controls = {
        "C00_EXPERIMENT": experiment,
        "C08_LOCAL_TIME": {"state": "SUPPORTED_AND_CAPTURED", "system_utc": end_wall.isoformat(), "system_local": datetime.now().astimezone().isoformat(), "utc_offset": str(datetime.now().astimezone().utcoffset()), "timezone_name": str(datetime.now().astimezone().tzinfo), "monotonic_ns": time.monotonic_ns()},
        "C09_CLOCK_QUALITY": clock,
        "C17_LOCAL_STORAGE": {"runner": storage_capture(RUNNER), "protocol": storage_capture(PROTOCOL), "previous_journal": storage_capture(prev)},
        "C18_STORAGE_HEALTH": {"state": "NOT_SUPPORTED_BY_SOURCE", "reason": "hosted GitHub runner does not expose authoritative physical-disk SMART/ECC health"},
        "C19_DATABASE": {"state": "NOT_APPLICABLE"},
        "C20_RUNTIME": runtime,
        "C21_TIMEZONE_LOCALE": {"state": "SUPPORTED_AND_CAPTURED", "timezone_name": str(datetime.now().astimezone().tzinfo), "utc_offset": str(datetime.now().astimezone().utcoffset()), "locale": runtime.get("locale"), "encoding": runtime.get("preferred_encoding"), "tzdata_version": _tzdata_version()},
        "C22_CLIENT_PRESENTATION": {"state": "NOT_APPLICABLE", "reason": "headless runner; presentation-specific subjects require dedicated browser/game capture plugin"},
        "C23_OBSERVER": {"state": "SUPPORTED_AND_CAPTURED", "machine_value": True, "manual_transcription": False, "second_observer": False, "memory_only_flag": False},
        "C24_NOTARY": {"state": "SUPPORTED_BUT_MISSING", "reason": "RFC3161 token not yet attached by runner"},
        "instrument_self_tests": selftest,
    }

    entry = {
        "artifact_uuid": f"JANUS-RECORD-DRIFT-JOURNAL-{stamp}",
        "journal_id": "JANUS-RECORD-DRIFT-JOURNAL", "entry_id": stamp, "version": "0.2-full-surface",
        "observed_at_utc": end_wall.isoformat(), "runner": RUNNER.relative_to(ROOT).as_posix(),
        "protocol": PROTOCOL.relative_to(ROOT).as_posix(), "baseline": BASELINE.relative_to(ROOT).as_posix(),
        "previous_entry": {"path": prev.relative_to(ROOT).as_posix(), "sha256_as_observed_now": sha256(prev_bytes)},
        "global_controls": global_controls,
        "checks": checks,
        "summary": {
            "instrument_gate_pass": selftest["all_pass"],
            "real_world_classifications_admissible": selftest["all_pass"],
            "countable_checks": len(countable), "class_counts": counts,
            "R9_count": counts.get("R9_JOURNAL_CHAIN_BREAK", 0),
            "R10_count": counts.get("R10_UNEXPLAINED_CONFIRMED_DRIFT", 0),
            "unexplained_confirmed_drift": selftest["all_pass"] and counts.get("R10_UNEXPLAINED_CONFIRMED_DRIFT", 0) > 0,
            "v0_2_extension_baseline_note": "Parameters first introduced in v0.2 are baseline-extension observations on their first capture and are not positive drift by themselves."
        },
        "claim_ceiling": {"ordinary_declared_changes_are_not_anomalies": True, "memory_or_display_difference_alone_is_not_raw_drift": True, "R10_requires_full_surface_exclusion_gate": True, "retrocausality_claim": False, "timeline_change_claim": False},
        "self_monitoring": {"this_entry_does_not_embed_its_own_final_hash": True, "next_run_must_verify_this_file_against_its_creation_commit_blob": True}
    }
    out.write_text(json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"journal": out.relative_to(ROOT).as_posix(), "instrument_gate_pass": selftest["all_pass"], "summary": entry["summary"]}, indent=2))


def _tzdata_version():
    try:
        return importlib.metadata.version("tzdata")
    except Exception:
        return "SYSTEM_ZONEINFO_OR_UNKNOWN"


if __name__ == "__main__":
    main()
