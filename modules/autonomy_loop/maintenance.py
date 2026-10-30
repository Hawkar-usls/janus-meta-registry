"""Reviewed metadata-only maintenance handlers. No issue/model text is executable."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import re

OWNER = "Hawkar-usls"
ALLOWED_REPOS = {"janus-meta-registry", "aura-oracle-tg", "Janus-Demiurge", "janus-lapis",
                 "Hrain", "iNaiHR", "Janus_Genesis", "TOPA", "Janus", "Janus-Cosmos"}
SHA = re.compile(r"^[0-9a-f]{40}$")
class Hold(ValueError):
    pass
def canon(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
def digest(x):
    return hashlib.sha256(canon(x)).hexdigest()
def encode(x):
    return json.dumps(x, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False).encode() + b"\n"
def trusted(root, filename):
    path = Path(__file__).resolve().parents[2] / "modules/rowan_observer" / filename
    spec = importlib.util.spec_from_file_location("janus_reviewed_" + path.stem, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

def reconcile(root, data, clean):
    """Only own immutable coordination metadata and its bounded latest pointer."""
    receipt = clean(data["canonical"], data["aura"], data["council"])
    run = receipt["sources"]["meta_canonical_run"]
    fingerprint = receipt["source_binding_sha256"]
    if type(run) is not int or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise Hold("INVALID_COORDINATION_IDENTITY")
    base = Path(root) / "data/rowan/coordination"
    latest = base / "LATEST_COORDINATION_STATE.json"
    if latest.exists():
        existing = json.loads(latest.read_bytes())
        if existing.get("meta_canonical_run", 0) > run:
            raise Hold("COORDINATION_ROLLBACK_DENIED")
    out = base / "receipts" / f"ROWAN-COUNCIL-{run}-{fingerprint[:16]}.json"
    content = encode(receipt)
    if out.exists() and out.read_bytes() != content:
        raise Hold("IMMUTABLE_COORDINATION_CONFLICT")
    created = not out.exists()
    out.parent.mkdir(parents=True, exist_ok=True)
    if created:
        out.write_bytes(content)
    pointer = {"schema_id": "janus.meta_registry.rowan_council_state.v1",
               "meta_canonical_run": run, "source_binding_sha256": fingerprint,
               "receipt_path": out.relative_to(root).as_posix(),
               "next_question": receipt["observation"]["demiurge_next_question"],
               "scientific_status": "HYPOTHESES_ONLY_NOT_BIOLOGICAL_DISCOVERY"}
    changed = not latest.exists() or latest.read_bytes() != encode(pointer)
    if changed:
        latest.write_bytes(encode(pointer))
    return {"status": "UPDATED_COORDINATION" if created or changed else "IDLE_COORDINATION_CURRENT",
            "source_run": run, "receipt_path": out.relative_to(root).as_posix(),
            "source_binding_sha256": fingerprint, "metadata_changed": created or changed,
            "source_code_changed": False}

def full_cohort(root, client):
    witness = trusted(root, "ecosystem_sync_witness.py")
    specs = {}
    for name, url_path in witness.URLS.items():
        owner, repo, ref, path = url_path.split("/", 3)
        if owner != OWNER or repo not in ALLOWED_REPOS or ref != "main":
            raise Hold("WITNESS_SOURCE_OUTSIDE_REVIEWED_SCOPE")
        specs[name] = (repo, ref, path)
    for repo, ref, _ in specs.values():
        client.pin(repo, ref)
    raw, data, pins = {}, {}, {}
    def read(name, repo, commit, path, text=False):
        content, sha, blob = client.raw_file(repo, commit, path)
        raw[name] = content
        data[name] = content.decode("utf-8") if text else json.loads(content)
        pins[name] = {"repository": OWNER + "/" + repo, "commit_sha": commit,
                      "path": path, "content_sha256": sha, "blob_sha": blob}
    for name, (repo, ref, path) in specs.items():
        read(name, repo, client.pin(repo, ref), path, name in ("hrain", "inaihr"))
    pointer = data["pointer"].get("receipt_path")
    cosmos = data["cosmos"].get("receipt_path")
    if not isinstance(pointer, str) or not witness.RECEIPT.fullmatch(pointer):
        raise Hold("UNTRUSTED_COORDINATION_RECEIPT")
    if not isinstance(cosmos, str) or not witness.COSMOS_RECEIPT.fullmatch(cosmos):
        raise Hold("UNTRUSTED_COSMOS_RECEIPT")
    read("receipt", "janus-meta-registry", client.pin("janus-meta-registry", "main"), pointer)
    read("cosmos_receipt", "Janus-Cosmos", client.pin("Janus-Cosmos", "main"), cosmos)
    result = witness.verify(data, raw)
    proof = {"schema": "janus.autonomy.p02_cohort.v1", "status": "PASS_SOURCE_COHORT_ONLY",
             "sources": pins, "witness": result, "authority_delta": 0,
             "runtime_execution_attested": False, "full_issue_162_acceptance": False}
    proof["proof_sha256"] = digest(proof)
    return proof

def verify_cohort(root, client, proof):
    witness = trusted(root, "ecosystem_sync_witness.py")
    raw, data = {}, {}
    expected_names = set(witness.URLS) | {"receipt", "cosmos_receipt"}
    if proof.get("schema") != "janus.autonomy.p02_cohort.v1" or set(proof.get("sources", {})) != expected_names:
        raise Hold("P02_PROOF_SOURCE_SET")
    if proof.get("status") != "PASS_SOURCE_COHORT_ONLY" or proof.get("authority_delta") != 0 or proof.get("full_issue_162_acceptance") is not False:
        raise Hold("P02_AUTHORITY_PROMOTION")
    for name, info in proof["sources"].items():
        repo = info.get("repository", "").removeprefix(OWNER + "/")
        if repo not in ALLOWED_REPOS or not SHA.fullmatch(info.get("commit_sha", "")):
            raise Hold("P02_UNAPPROVED_SOURCE")
        if name in witness.URLS:
            _, expected_repo, _, expected_path = witness.URLS[name].split("/", 3)
            if (repo, info.get("path")) != (expected_repo, expected_path):
                raise Hold("P02_SOURCE_REBINDING")
        elif name == "receipt":
            if repo != "janus-meta-registry" or not witness.RECEIPT.fullmatch(info.get("path", "")):
                raise Hold("P02_RECEIPT_PATH")
        elif repo != "Janus-Cosmos" or not witness.COSMOS_RECEIPT.fullmatch(info.get("path", "")):
            raise Hold("P02_COSMOS_PATH")
        body, sha, blob = client.raw_file(repo, info["commit_sha"], info["path"])
        if (sha, blob) != (info.get("content_sha256"), info.get("blob_sha")):
            raise Hold("P02_EXACT_BYTES_CHANGED")
        raw[name] = body
        data[name] = body.decode("utf-8") if name in ("hrain", "inaihr") else json.loads(body)
    actual = witness.verify(data, raw)
    if digest(actual) != digest(proof.get("witness")):
        raise Hold("P02_WITNESS_REPLAY_MISMATCH")
    unsigned = dict(proof)
    signature = unsigned.pop("proof_sha256", None)
    if signature != digest(unsigned):
        raise Hold("P02_PROOF_DIGEST")
    return {"status": "PASS_SOURCE_COHORT_ONLY", "proof_sha256": signature,
            "canonical_run": actual["canonicalRun"], "authority_delta": 0,
            "full_issue_162_acceptance": False}

def execute(root, client, sources, previous):
    accepted = previous.get("accepted_phases", {})
    if (not isinstance(accepted, dict) or set(accepted) - {"P0.1", "P0.2"} or
        not isinstance(accepted.get("P0.1"), dict) or
        accepted["P0.1"].get("status") != "PASS_STATUS_CAPTURE_ONLY"):
        return {"status": "WAIT_P01_ACCEPTANCE", "metadata_changed": False}
    result = {"status": "WAIT_UPSTREAM_SOURCE_COHORT", "metadata_changed": False}
    try:
        data = {}
        for key in ("canonical", "aura", "council"):
            if sources[key].get("status") != "OBSERVED":
                raise Hold("REQUIRED_SOURCE_UNAVAILABLE")
            data[key] = sources[key]["data"]
        ingest = trusted(root, "coordination_ingest.py")
        result = reconcile(root, data, ingest.clean)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        result["hold_class"] = type(exc).__name__
    try:
        result["p02_proof"] = full_cohort(root, client)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        result["cohort_status"] = "WAIT_INDEPENDENT_SOURCE_COHORT"
        reason = str(exc)
        result["cohort_hold"] = reason if re.fullmatch(r"[A-Z0-9_]{1,100}", reason) else type(exc).__name__
    return result
