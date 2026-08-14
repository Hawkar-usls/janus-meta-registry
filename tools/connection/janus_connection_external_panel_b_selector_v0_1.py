#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile

PANEL_A_REPOS = {
    "in-toto/in-toto-golang",
    "sigstore/cosign",
    "slsa-framework/slsa",
    "ossf/scorecard",
    "json-schema-org/JSON-Schema-Test-Suite",
    "CycloneDX/specification",
    "oasis-tcs/sarif-spec",
    "opencontainers/image-spec",
}

POSITIVE_TOKENS = ("result", "report", "output", "snapshot", "expected", "golden", "findings", "scan", "summary")
EXCLUDE_TOKENS = ("schema", "config", "package", "lock", "rules", "input")
MAX_PER_REPO = 3

REPOS = [
    {
        "repository": "aquasecurity/trivy",
        "governance_namespace": "aquasecurity",
        "commit": "d98911ea338b061f8bef0baeef85b35660013b32",
        "tree": "1dad95016da1b684a3ceae85025c07ec0e3c5767",
    },
    {
        "repository": "anchore/grype",
        "governance_namespace": "anchore",
        "commit": "b5fa92bbcbef655497e3be840a2f718380e2cdd3",
        "tree": "5d4856801c1a7982b7b259705910b40cc6e3d30d",
    },
    {
        "repository": "google/osv-scanner",
        "governance_namespace": "google",
        "commit": "567f3ea998f1241e60ec3ca9c4cc9e30809cd820",
        "tree": "5968611a8ff99c4cd3737ac8cd9ca7a3bb5a4fb4",
    },
    {
        "repository": "github/codeql-action",
        "governance_namespace": "github",
        "commit": "d97b3428e8eebbb1810cf454d6397886d136b4ba",
        "tree": "3b195125e2a320a144206c5ae78713f690b89524",
    },
    {
        "repository": "gitleaks/gitleaks",
        "governance_namespace": "gitleaks",
        "commit": "b58d3f102cf3a2c84cb7f923d05c25c9b1aed84b",
        "tree": "fa9b01773f4154a479b5667268616bb1dce84610",
        "canonicalization_note": "canonical repository identity used instead of historical zricethezav/gitleaks alias",
    },
    {
        "repository": "semgrep/semgrep",
        "governance_namespace": "semgrep",
        "commit": "cc97b5c47dacabe76be343ef981204b8c1f60e07",
        "tree": "e323b1125ddc4a4f5460d211c473c35dcb5d56e8",
    },
    {
        "repository": "trufflesecurity/trufflehog",
        "governance_namespace": "trufflesecurity",
        "commit": "bcfcf73aaf4759d4dadc2783177c245a02792318",
        "tree": "4c9c4c26e9a5699458830115130d8caca8230883",
    },
    {
        "repository": "bridgecrewio/checkov",
        "governance_namespace": "bridgecrewio",
        "commit": "5458c889320a19ccf2e2eed54beb4c661c70f67a",
        "tree": "c2d8bde2c800f7a36d8b04161df5dad4cd276a10",
    },
]

PRE_FREEZE_PROVISIONAL_NOT_USED = [
    {"repository":"aquasecurity/trivy","commit":"a65077ea4f0d0c88a70d2b74109cedf020d11474","tree":"1dad95016da1b684a3ceae85025c07ec0e3c5767","status":"PRE_FREEZE_PROVISIONAL_NOT_USED","reason":"superseded during single provenance correction epoch before body inspection"},
    {"repository":"anchore/grype","commit":"27fd4e59ce5c34b65301fc87ac4d6cc50ba8a8f6","tree":"5d4856809faab792661ca2374fc73f3c7e56a819","status":"PRE_FREEZE_PROVISIONAL_NOT_USED","reason":"commit/tree tuple failed Git object resolution before selection"},
    {"repository":"google/osv-scanner","commit":"bdc2a727104ee899935792a0fef75e4031c4e1bb","tree":"5968611a0161335ec169015b507b0932c83a1cbc","status":"PRE_FREEZE_PROVISIONAL_NOT_USED","reason":"tree tuple failed resolution during provenance correction epoch before selection"},
    {"repository":"github/codeql-action","commit":"83b18f69e55a3850bc249d9cec20f987c88bc44d","tree":"3b195125e5e7649ff166db3f5c868eda3cd1edb1","status":"PRE_FREEZE_PROVISIONAL_NOT_USED","reason":"superseded during single provenance correction epoch before body inspection"},
    {"repository":"gitleaks/gitleaks","commit":"209ed4dd1aa5dd1b90bf42bf3a2b958db64bd64b","tree":"fa9b0174d36e4edbcbaf1b5d072a61b895581b3e","status":"PRE_FREEZE_PROVISIONAL_NOT_USED","reason":"superseded during single provenance correction epoch before body inspection"},
    {"repository":"semgrep/semgrep","commit":"b4eaf2ccabe074eae1c7c7876cf99a518d5a2852","tree":"e323b112f9ebccd78ed3ec7a01a39726ff840ecb","status":"PRE_FREEZE_PROVISIONAL_NOT_USED","reason":"superseded during single provenance correction epoch before body inspection"},
    {"repository":"trufflesecurity/trufflehog","commit":"0f939a4383e10fb0e6fb711453ea113faf6a8938","tree":"4c9c4c26dd1ab08d04e5938b6c5e3df18f813cd2","status":"PRE_FREEZE_PROVISIONAL_NOT_USED","reason":"superseded during single provenance correction epoch before body inspection"},
    {"repository":"bridgecrewio/checkov","commit":"8f1a023d3787010b31f9d7d49021353ff6c58017","tree":"c2d8bde0650ad94e5f7afc686f4aa4ad1e04c156","status":"PRE_FREEZE_PROVISIONAL_NOT_USED","reason":"superseded during single provenance correction epoch before body inspection"},
]

def run(cmd, cwd=None):
    return subprocess.check_output(cmd, cwd=cwd, text=True, stderr=subprocess.STDOUT).strip()

def eligible(path: str) -> bool:
    p = path.lower()
    if not p.endswith(".json"):
        return False
    if not any(tok in p for tok in POSITIVE_TOKENS):
        return False
    if any(tok in p for tok in EXCLUDE_TOKENS):
        return False
    return True

def rank(repo: str, commit: str, path: str) -> str:
    return hashlib.sha256(f"{repo}@{commit}\n{path}".encode()).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    assert len(REPOS) == 8
    assert len({r["governance_namespace"] for r in REPOS}) == 8
    assert not ({r["repository"] for r in REPOS} & PANEL_A_REPOS)

    results = []
    with tempfile.TemporaryDirectory(prefix="panel-b-") as td:
        root = pathlib.Path(td)
        for i, r in enumerate(REPOS):
            work = root / f"r{i}"
            work.mkdir()
            run(["git", "init", "-q"], cwd=work)
            run(["git", "remote", "add", "origin", f"https://github.com/{r['repository']}.git"], cwd=work)
            # Metadata-only fetch: no checkout; partial clone excludes blob bodies.
            run(["git", "-c", "protocol.version=2", "fetch", "-q", "--depth=1", "--filter=blob:none", "origin", r["commit"]], cwd=work)
            actual_tree = run(["git", "rev-parse", f"{r['commit']}^{{tree}}"], cwd=work)
            if actual_tree != r["tree"]:
                raise SystemExit(f"TREE_MISMATCH {r['repository']} {actual_tree} != {r['tree']}")
            raw = run(["git", "ls-tree", "-r", r["commit"]], cwd=work)
            blobs = []
            for line in raw.splitlines():
                left, path = line.split("\t", 1)
                mode, typ, sha = left.split()
                if typ != "blob":
                    continue
                if eligible(path):
                    blobs.append({"path": path, "blob_sha": sha, "rank_sha256": rank(r["repository"], r["commit"], path)})
            blobs.sort(key=lambda x: (x["rank_sha256"], x["path"]))
            selected = blobs[:MAX_PER_REPO]
            results.append({
                **r,
                "commit_tree_verification": "PASS",
                "tree_universe_method": "git fetch --filter=blob:none --no-checkout + git ls-tree -r",
                "blob_bodies_fetched_by_selector": False,
                "eligible_count": len(blobs),
                "selected_count": len(selected),
                "selected": selected,
            })

    out = {
        "artifact_uuid": "JANUS-CONNECTION-EXTERNAL-PANEL-B-RESULT-RECORDS-SELECTION-2026-08-14-v0.1",
        "timestamp_local": "2026-08-14T16:19:00+03:00",
        "version": "v0.1",
        "status": "BODY_BLIND_EXTERNAL_PANEL_B_SELECTION_EXECUTED",
        "purpose": "Freeze a repository-external panel of machine-readable audit/result/verification JSON records before reading selected JSON bodies, for later testing of HIDDEN-001/002/003/006.",
        "relation_to_panel_a": "DISJOINT_EXTERNAL_CORPUS_SECOND_ATTEMPT; PANEL_A_IMMUTABLE_VALID_NEGATIVE",
        "source_class": "machine-readable audit/result/verification records represented as JSON paths in externally governed repositories",
        "selected_body_inspection_performed": False,
        "selection_used_json_values": False,
        "selection_used_json_titles": False,
        "selection_used_code_search": False,
        "selection_used_checkout": False,
        "selection_fetch_filter": "blob:none",
        "path_filter": {
            "extension": ".json",
            "positive_any": list(POSITIVE_TOKENS),
            "exclude_any": list(EXCLUDE_TOKENS),
            "max_selected_per_repository": MAX_PER_REPO,
            "rank": "SHA256(repository + '@' + commit + '\\n' + path)",
        },
        "panel_a_repositories_excluded": sorted(PANEL_A_REPOS),
        "pre_freeze_provisional_not_used": PRE_FREEZE_PROVISIONAL_NOT_USED,
        "repositories": results,
        "summary": {
            "repositories_frozen": len(results),
            "independent_governance_namespaces": len({r["governance_namespace"] for r in results}),
            "repositories_with_eligible_json": sum(r["eligible_count"] > 0 for r in results),
            "repositories_with_zero_eligible_json": sum(r["eligible_count"] == 0 for r in results),
            "eligible_json_total": sum(r["eligible_count"] for r in results),
            "selected_json_total": sum(r["selected_count"] for r in results),
            "all_commit_tree_verification_pass": all(r["commit_tree_verification"] == "PASS" for r in results),
            "all_selector_body_reads_false": all(r["blob_bodies_fetched_by_selector"] is False for r in results),
        },
        "immutability_rules": [
            "No selected record may be replaced after body inspection.",
            "A repository with zero eligible records remains part of the frozen panel and is not backfilled.",
            "Panel A remains unchanged regardless of Panel B outcome.",
            "Classification rubric must be committed before selected JSON bodies are opened.",
        ],
        "claim_ceiling": {
            "external_transport_established_by_selection": False,
            "selected_content_classification_performed": False,
            "destructive_rewire_authorized": False,
            "family_wide_connection_promotion": False,
            "scientific_novelty": False,
        },
    }
    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(out["summary"], sort_keys=True))

if __name__ == "__main__":
    main()
