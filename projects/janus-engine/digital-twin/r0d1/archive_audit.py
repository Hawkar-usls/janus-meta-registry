"""R0D1 provenance and inventory only. Never execute external archive code."""
import argparse
import hashlib
import io
import json
import pathlib
import tarfile
import tempfile
import urllib.request

URL = "https://zenodo.org/records/12784504/files/experiments.tgz?download=1"
MD5 = "113b7be70d4c4364f464ccc9e9c3a5cf"
MAX_DOWNLOAD = 32 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
MAX_FILES = 10000

def download(path):
    with urllib.request.urlopen(URL, timeout=60) as response, path.open("wb") as out:
        total = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DOWNLOAD:
                raise ValueError("download exceeds bound")
            out.write(chunk)

def inspect(path, expected_md5):
    raw = path.read_bytes()
    if len(raw) > MAX_DOWNLOAD:
        raise ValueError("archive exceeds bound")
    md5 = hashlib.md5(raw, usedforsecurity=False).hexdigest()
    if md5 != expected_md5:
        raise ValueError("archive checksum mismatch")
    members, seen, expanded = [], set(), 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r|gz") as archive:
        for m in archive:
            if len(members) >= MAX_FILES:
                raise ValueError("member count exceeds bound")
            name = pathlib.PurePosixPath(m.name)
            if name.is_absolute() or ".." in name.parts or str(name) in seen:
                raise ValueError("unsafe or duplicate member")
            seen.add(str(name))
            if not (m.isfile() or m.isdir()):
                raise ValueError("non-regular archive member")
            expanded += m.size
            if expanded > MAX_EXPANDED:
                raise ValueError("expanded archive exceeds bound")
            row = {"path": str(name), "bytes": m.size, "kind": "file" if m.isfile() else "directory"}
            if m.isfile():
                f = archive.extractfile(m)
                h = hashlib.sha256()
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
                row["sha256"] = h.hexdigest()
            members.append(row)
    return {"archive_bytes": len(raw), "md5": md5,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "member_count": len(members), "expanded_bytes": expanded,
            "members": members}

def self_test():
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "fixture.tgz"
        def fixture(name):
            with tarfile.open(p, "w:gz") as t:
                m = tarfile.TarInfo(name)
                m.size = 3
                t.addfile(m, io.BytesIO(b"abc"))
            return hashlib.md5(p.read_bytes(), usedforsecurity=False).hexdigest()
        digest = fixture("experiment/data.csv")
        assert inspect(p, digest)["members"][0]["sha256"] == hashlib.sha256(b"abc").hexdigest()
        for bad_name, wrong_digest in [("experiment/data.csv", True), ("../escape", False)]:
            digest = fixture(bad_name)
            try:
                inspect(p, "0"*32 if wrong_digest else digest)
            except ValueError:
                pass
            else:
                raise AssertionError("invalid archive accepted")
    return {"status": "PASS", "checks": 3, "evidence": "SYNTHETIC_SOFTWARE_TEST_ONLY"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--self-test-only", action="store_true")
    args = parser.parse_args()
    result = {"stage": "R0D1A", "source_doi": "10.5281/zenodo.12784504",
              "paper_doi": "10.1002/advs.202410358", "source_url": URL,
              "self_test": self_test(), "physical_janus_runs": 0,
              "figure3_reproduced": False, "run008_modified": False}
    if args.self_test_only:
        result["status"] = "PASS_SOFTWARE_TEST_ONLY"
    else:
        try:
            with tempfile.TemporaryDirectory() as d:
                path = args.archive or pathlib.Path(d) / "experiments.tgz"
                if args.archive is None:
                    download(path)
                result["inventory"] = inspect(path, MD5)
            result["status"] = "PASS_ARCHIVE_PROVENANCE_ONLY"
        except Exception as exc:
            result["status"] = "BLOCKED_ARCHIVE_ACQUISITION_OR_VALIDATION"
            result["error"] = f"{type(exc).__name__}: {exc}"
    args.output.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k,v in result.items() if k != "inventory"}, ensure_ascii=True))
    if result["status"].startswith("BLOCKED"):
        raise SystemExit(1)

if __name__ == "__main__":
    main()
