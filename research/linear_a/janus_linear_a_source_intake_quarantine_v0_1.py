#!/usr/bin/env python3
"""Generic fail-closed, non-executing external-source intake for JANUS Linear A.

This gate records original byte identity and archive metadata/hashes before any
source-specific scientific interpretation. Archive members are never extracted
to the filesystem and never executed. Member payloads may only be streamed for
SHA-256 hashing.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import stat
import tarfile
import tempfile
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

RUNNER_ID = "JANUS-LINEAR-A-SOURCE-INTAKE-QUARANTINE-v0.1"
SPEC_PATH = "data/JANUS-LINEAR-A-SOURCE-INTAKE-QUARANTINE-SPEC-2026-08-14-v0.1.json"
DEFAULT_MAX_ENTRY = 268435456
DEFAULT_MAX_TOTAL = 2147483648
DEFAULT_MAX_RATIO = 200.0
STREAM_CHUNK = 1024 * 1024
CODE_LIKE_EXTENSIONS = {
    ".exe", ".dll", ".com", ".msi", ".scr", ".sys",
    ".py", ".pyc", ".pyo", ".js", ".mjs", ".cjs", ".sh",
    ".bat", ".cmd", ".ps1", ".jar", ".class", ".vbs", ".wsf",
}
SUPPORTED_ARCHIVE_SUFFIXES = {
    ".zip": "ZIP",
    ".tar": "TAR",
    ".tar.gz": "TAR_GZ",
    ".tgz": "TGZ",
    ".tar.bz2": "TAR_BZ2",
    ".tar.xz": "TAR_XZ",
}
UNSUPPORTED_CONTAINER_SUFFIXES = {".rar": "RAR", ".7z": "7Z", ".dmg": "DMG", ".iso": "ISO"}
WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


def sha256_path(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    total = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(STREAM_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            h.update(chunk)
    return h.hexdigest(), total


def sha256_stream(stream: BinaryIO, expected_size: int, max_entry: int) -> tuple[str | None, int, str | None]:
    if expected_size > max_entry:
        return None, 0, "DECLARED_ENTRY_SIZE_EXCEEDS_LIMIT"
    h = hashlib.sha256()
    total = 0
    while True:
        chunk = stream.read(STREAM_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_entry:
            return None, total, "STREAMED_ENTRY_SIZE_EXCEEDS_LIMIT"
        h.update(chunk)
    if expected_size >= 0 and total != expected_size:
        return None, total, f"STREAMED_SIZE_MISMATCH:declared={expected_size}:observed={total}"
    return h.hexdigest(), total, None


def suffix_container_class(name: str) -> str:
    lower = name.lower()
    for suffix, cls in sorted(SUPPORTED_ARCHIVE_SUFFIXES.items(), key=lambda x: len(x[0]), reverse=True):
        if lower.endswith(suffix):
            return cls
    for suffix, cls in UNSUPPORTED_CONTAINER_SUFFIXES.items():
        if lower.endswith(suffix):
            return cls
    return "RAW_FILE"


def _path_flags(name: str) -> list[str]:
    flags: list[str] = []
    normalized = name.replace("\\", "/")
    if normalized.startswith("/"):
        flags.append("ABSOLUTE_PATH")
    if normalized.startswith("//") or name.startswith("\\\\"):
        flags.append("WINDOWS_UNC_PATH")
    if WINDOWS_DRIVE.match(name):
        flags.append("WINDOWS_DRIVE_PATH")
    parts = PurePosixPath(normalized).parts
    if ".." in parts:
        flags.append("PARENT_DIRECTORY_TRAVERSAL")
    return flags


def _code_like(name: str, unix_mode: int | None = None) -> bool:
    suffix = Path(name).suffix.lower()
    executable_bit = False
    if isinstance(unix_mode, int):
        executable_bit = bool(unix_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    return suffix in CODE_LIKE_EXTENSIONS or executable_bit


def _final_status(flags: list[str], limit_exceeded: bool) -> str:
    if limit_exceeded:
        return "QUARANTINE_HOLD_HASHING_LIMIT_EXCEEDED"
    if flags:
        return "QUARANTINE_HOLD_UNSAFE_ARCHIVE_STRUCTURE"
    return "SAFE_ARCHIVE_INVENTORY_COMPLETE_CONTENT_UNINSPECTED"


def inventory_zip(path: Path, *, max_entry: int, max_total: int, max_ratio: float) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    global_flags: list[str] = []
    total_declared = 0
    limit_exceeded = False
    try:
        zf = zipfile.ZipFile(path, "r")
    except Exception as exc:
        return {
            "status": "QUARANTINE_HOLD_UNSAFE_ARCHIVE_STRUCTURE",
            "archive_error": f"ZIP_OPEN_ERROR:{type(exc).__name__}:{exc}",
            "entries": [],
            "global_flags": ["ARCHIVE_OPEN_FAILURE"],
        }
    with zf:
        name_counts = Counter(info.filename for info in zf.infolist())
        for index, info in enumerate(zf.infolist()):
            total_declared += info.file_size
            flags = _path_flags(info.filename)
            encrypted = bool(info.flag_bits & 0x1)
            if encrypted:
                flags.append("ZIP_ENCRYPTED_ENTRY")
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(unix_mode)
            is_symlink = file_type == stat.S_IFLNK
            if is_symlink:
                flags.append("SYMLINK_ENTRY")
            ratio = None
            if info.file_size > 0:
                ratio = info.file_size / max(1, info.compress_size)
                if ratio > max_ratio:
                    flags.append("SUSPICIOUS_COMPRESSION_RATIO")
            if info.file_size > max_entry:
                flags.append("DECLARED_ENTRY_SIZE_EXCEEDS_LIMIT")
                limit_exceeded = True
            if total_declared > max_total:
                flags.append("CUMULATIVE_DECLARED_SIZE_EXCEEDS_LIMIT")
                limit_exceeded = True
            digest = None
            observed_bytes = None
            hash_error = None
            if not encrypted and not is_symlink and info.file_size <= max_entry and total_declared <= max_total and not info.is_dir():
                try:
                    with zf.open(info, "r") as stream:
                        digest, observed_bytes, hash_error = sha256_stream(stream, info.file_size, max_entry)
                except Exception as exc:
                    hash_error = f"ENTRY_STREAM_ERROR:{type(exc).__name__}:{exc}"
                    flags.append("ENTRY_STREAM_FAILURE")
            elif info.is_dir():
                observed_bytes = 0
            row = {
                "entry_index": index,
                "name": info.filename,
                "declared_uncompressed_bytes": info.file_size,
                "declared_compressed_bytes": info.compress_size,
                "compression_type": info.compress_type,
                "compression_ratio": ratio,
                "crc32": f"{info.CRC:08x}",
                "encrypted": encrypted,
                "directory": info.is_dir(),
                "unix_mode": unix_mode,
                "symlink": is_symlink,
                "duplicate_name_count": name_counts[info.filename],
                "code_or_executable_like": _code_like(info.filename, unix_mode),
                "sha256": digest,
                "observed_stream_bytes": observed_bytes,
                "hash_error": hash_error,
                "flags": sorted(set(flags)),
            }
            entries.append(row)
            global_flags.extend(flags)
    return {
        "status": _final_status(sorted(set(global_flags)), limit_exceeded),
        "archive_format": "ZIP",
        "entry_count": len(entries),
        "declared_total_uncompressed_bytes": total_declared,
        "duplicate_entry_name_count": sum(1 for n in Counter(e["name"] for e in entries).values() if n > 1),
        "code_or_executable_like_entry_count": sum(1 for e in entries if e["code_or_executable_like"]),
        "all_regular_file_payload_hashes_present": all(
            e["directory"] or e["symlink"] or e["encrypted"] or e["sha256"] is not None
            for e in entries
        ),
        "entries": entries,
        "global_flags": sorted(set(global_flags)),
    }


def inventory_tar(path: Path, *, max_entry: int, max_total: int, max_ratio: float) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    global_flags: list[str] = []
    total_declared = 0
    limit_exceeded = False
    try:
        tf = tarfile.open(path, "r:*")
    except Exception as exc:
        return {
            "status": "QUARANTINE_HOLD_UNSAFE_ARCHIVE_STRUCTURE",
            "archive_error": f"TAR_OPEN_ERROR:{type(exc).__name__}:{exc}",
            "entries": [],
            "global_flags": ["ARCHIVE_OPEN_FAILURE"],
        }
    with tf:
        members = tf.getmembers()
        name_counts = Counter(m.name for m in members)
        for index, member in enumerate(members):
            flags = _path_flags(member.name)
            is_symlink = member.issym()
            is_hardlink = member.islnk()
            is_special = member.ischr() or member.isblk() or member.isfifo()
            if is_symlink:
                flags.append("SYMLINK_ENTRY")
            if is_hardlink:
                flags.append("HARDLINK_ENTRY")
            if is_special:
                flags.append("SPECIAL_FILESYSTEM_NODE")
            if member.isfile():
                total_declared += member.size
                if member.size > max_entry:
                    flags.append("DECLARED_ENTRY_SIZE_EXCEEDS_LIMIT")
                    limit_exceeded = True
                if total_declared > max_total:
                    flags.append("CUMULATIVE_DECLARED_SIZE_EXCEEDS_LIMIT")
                    limit_exceeded = True
            digest = None
            observed_bytes = None
            hash_error = None
            if member.isfile() and member.size <= max_entry and total_declared <= max_total:
                try:
                    stream = tf.extractfile(member)
                    if stream is None:
                        hash_error = "ENTRY_STREAM_UNAVAILABLE"
                        flags.append("ENTRY_STREAM_FAILURE")
                    else:
                        with stream:
                            digest, observed_bytes, hash_error = sha256_stream(stream, member.size, max_entry)
                except Exception as exc:
                    hash_error = f"ENTRY_STREAM_ERROR:{type(exc).__name__}:{exc}"
                    flags.append("ENTRY_STREAM_FAILURE")
            elif member.isdir():
                observed_bytes = 0
            row = {
                "entry_index": index,
                "name": member.name,
                "declared_uncompressed_bytes": member.size,
                "directory": member.isdir(),
                "regular_file": member.isfile(),
                "symlink": is_symlink,
                "hardlink": is_hardlink,
                "special_node": is_special,
                "link_target": member.linkname if (is_symlink or is_hardlink) else None,
                "unix_mode": member.mode,
                "duplicate_name_count": name_counts[member.name],
                "code_or_executable_like": _code_like(member.name, member.mode),
                "sha256": digest,
                "observed_stream_bytes": observed_bytes,
                "hash_error": hash_error,
                "flags": sorted(set(flags)),
            }
            entries.append(row)
            global_flags.extend(flags)
    return {
        "status": _final_status(sorted(set(global_flags)), limit_exceeded),
        "archive_format": "TAR",
        "entry_count": len(entries),
        "declared_total_uncompressed_bytes": total_declared,
        "duplicate_entry_name_count": sum(1 for n in Counter(e["name"] for e in entries).values() if n > 1),
        "code_or_executable_like_entry_count": sum(1 for e in entries if e["code_or_executable_like"]),
        "all_regular_file_payload_hashes_present": all(
            (not e["regular_file"]) or e["sha256"] is not None
            for e in entries
        ),
        "entries": entries,
        "global_flags": sorted(set(global_flags)),
    }


def quarantine(path: Path, *, max_entry: int = DEFAULT_MAX_ENTRY, max_total: int = DEFAULT_MAX_TOTAL, max_ratio: float = DEFAULT_MAX_RATIO) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {
            "artifact_uuid": "JANUS-LINEAR-A-SOURCE-INTAKE-QUARANTINE-RESULT-v0.1",
            "version": "v0.1",
            "node_type": "generic_external_source_intake_quarantine_result",
            "status": "QUARANTINE_INPUT_MISSING_OR_UNREADABLE",
            "runner_id": RUNNER_ID,
            "input_path_basename": path.name,
            "scientific_content_inspected": False,
            "code_executed": False,
            "archive_extracted_to_filesystem": False,
        }
    top_sha, top_bytes = sha256_path(path)
    cls = suffix_container_class(path.name)
    base = {
        "artifact_uuid": "JANUS-LINEAR-A-SOURCE-INTAKE-QUARANTINE-RESULT-v0.1",
        "version": "v0.1",
        "node_type": "generic_external_source_intake_quarantine_result",
        "runner_id": RUNNER_ID,
        "spec": SPEC_PATH,
        "input_path_basename": path.name,
        "sha256": top_sha,
        "bytes": top_bytes,
        "detected_container_class": cls,
        "limits": {
            "max_entry_uncompressed_bytes": max_entry,
            "max_total_uncompressed_bytes": max_total,
            "max_compression_ratio": max_ratio,
        },
        "scientific_content_inspected": False,
        "code_executed": False,
        "archive_extracted_to_filesystem": False,
        "original_input_bytes_mutated": False,
        "source_provenance_admitted": False,
        "R3B_effect": "NONE",
        "new_anchor": False,
        "decipherment": False,
    }
    if cls in UNSUPPORTED_CONTAINER_SUFFIXES.values():
        return {**base, "status": "QUARANTINE_HOLD_UNSUPPORTED_CONTAINER", "inventory": None}
    if cls == "RAW_FILE":
        return {**base, "status": "SAFE_RAW_FILE_IDENTITY_COMPLETE_CONTENT_UNINSPECTED", "inventory": None, "code_or_executable_like": _code_like(path.name)}
    if cls == "ZIP":
        inv = inventory_zip(path, max_entry=max_entry, max_total=max_total, max_ratio=max_ratio)
    else:
        inv = inventory_tar(path, max_entry=max_entry, max_total=max_total, max_ratio=max_ratio)
    return {**base, "status": inv.pop("status"), "inventory": inv}


def self_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        safe_zip = root / "safe.zip"
        with zipfile.ZipFile(safe_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("data/master.csv", "a,b\n1,2\n")
            z.writestr("code/tool.py", "print('never executed')\n")
            z.writestr("data/master.csv", "a,b\n3,4\n")
        safe = quarantine(safe_zip, max_entry=1024*1024, max_total=1024*1024, max_ratio=200.0)
        assert safe["status"] == "SAFE_ARCHIVE_INVENTORY_COMPLETE_CONTENT_UNINSPECTED", safe
        assert safe["inventory"]["duplicate_entry_name_count"] == 1
        assert safe["inventory"]["code_or_executable_like_entry_count"] == 1
        assert safe["inventory"]["all_regular_file_payload_hashes_present"] is True

        bad_zip = root / "bad.zip"
        with zipfile.ZipFile(bad_zip, "w") as z:
            z.writestr("../escape.txt", "x")
        bad = quarantine(bad_zip)
        assert bad["status"] == "QUARANTINE_HOLD_UNSAFE_ARCHIVE_STRUCTURE"
        assert "PARENT_DIRECTORY_TRAVERSAL" in bad["inventory"]["global_flags"]

        limit_zip = root / "limit.zip"
        with zipfile.ZipFile(limit_zip, "w", compression=zipfile.ZIP_STORED) as z:
            z.writestr("big.bin", b"x" * 64)
        limited = quarantine(limit_zip, max_entry=32, max_total=1024, max_ratio=200.0)
        assert limited["status"] == "QUARANTINE_HOLD_HASHING_LIMIT_EXCEEDED"

        raw = root / "fixture.csv"
        raw.write_text("x\n", encoding="utf-8")
        raw_result = quarantine(raw)
        assert raw_result["status"] == "SAFE_RAW_FILE_IDENTITY_COMPLETE_CONTENT_UNINSPECTED"

        unsupported = root / "fixture.rar"
        unsupported.write_bytes(b"not-a-rar-needed-for-suffix-test")
        unsupported_result = quarantine(unsupported)
        assert unsupported_result["status"] == "QUARANTINE_HOLD_UNSUPPORTED_CONTAINER"

        safe_hashes = [e["sha256"] for e in safe["inventory"]["entries"] if not e["directory"]]
        return {
            "runner_id": RUNNER_ID,
            "safe_zip_inventory_pass": True,
            "safe_zip_entry_count": safe["inventory"]["entry_count"],
            "duplicate_name_preserved": True,
            "code_like_entry_flagged_not_executed": True,
            "safe_member_hashes_present": all(isinstance(h, str) and len(h) == 64 for h in safe_hashes),
            "path_traversal_rejected": True,
            "hashing_limit_fail_closed": True,
            "raw_file_identity_pass": True,
            "unsupported_container_fail_closed": True,
            "scientific_content_inspected": False,
            "code_executed": False,
            "archive_extracted_to_filesystem": False,
            "R3B_effect": "NONE",
            "decipherment": False,
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("self-test")
    p = sub.add_parser("quarantine")
    p.add_argument("path")
    p.add_argument("--out", required=True)
    p.add_argument("--max-entry-bytes", type=int, default=DEFAULT_MAX_ENTRY)
    p.add_argument("--max-total-uncompressed-bytes", type=int, default=DEFAULT_MAX_TOTAL)
    p.add_argument("--max-compression-ratio", type=float, default=DEFAULT_MAX_RATIO)
    args = ap.parse_args()
    if args.cmd == "self-test":
        print(json.dumps(self_test(), ensure_ascii=False, indent=2, sort_keys=True))
        return
    result = quarantine(
        Path(args.path),
        max_entry=args.max_entry_bytes,
        max_total=args.max_total_uncompressed_bytes,
        max_ratio=args.max_compression_ratio,
    )
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "sha256": result.get("sha256"), "bytes": result.get("bytes")}, sort_keys=True))


if __name__ == "__main__":
    main()
