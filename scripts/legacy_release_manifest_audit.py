#!/usr/bin/env python3
"""Read-only, local, bounded SHA-256 audit of a historical release manifest.

No NAS network actions, no execution of legacy payloads and no mutation.
The manifest is UNTRUSTED: paths are validated and symlinks are rejected.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_RECORDS = 2000

def audit(manifest: dict, root: Path, max_bytes: int = 131072) -> dict:
    entries=manifest.get("files")
    if not isinstance(entries,list) or len(entries)>MAX_RECORDS:
        raise ValueError("MANIFEST_ENTRIES_INVALID")
    if max_bytes < 1 or max_bytes > 16 * 1024 * 1024:
        raise ValueError("SIZE_BOUND_INVALID")
    root=root.resolve(strict=True)
    counts={"matched":0,"missing":0,"modified":0,"oversize":0,"unsafe":0}
    seen=set()
    for entry in entries:
        if not isinstance(entry,dict):
            counts["unsafe"]+=1
            continue
        name=entry.get("path")
        sha=entry.get("sha256")
        size=entry.get("size")
        if (not isinstance(name,str) or not name or len(name)>512
            or "\\" in name or "\x00" in name or name.startswith("/")
            or not HEX64.fullmatch(sha if isinstance(sha,str) else "")
            or type(size) is not int or size<0 or size>2**40):
            counts["unsafe"]+=1
            continue
        pure=PurePosixPath(name)
        if (pure.is_absolute() or any(x in ("..",".") for x in name.split("/"))
            or len(pure.parts)<1 or name in seen or "//" in name):
            counts["unsafe"]+=1
            continue
        seen.add(name)
        target=root
        escaped=False
        for p in pure.parts:
            target=target/p
            if target.is_symlink():
                escaped=True
                break
        if escaped:
            counts["unsafe"]+=1
            continue
        if not target.is_file():
            counts["missing"]+=1
            continue
        actual=target.stat().st_size
        if actual != size:
            counts["modified"]+=1
            continue
        if actual > max_bytes:
            counts["oversize"]+=1
            continue
        h=hashlib.sha256()
        with target.open("rb") as stream:
            while chunk:=stream.read(min(65536,max_bytes)):
                h.update(chunk)
        if h.hexdigest()==sha:
            counts["matched"]+=1
        else:
            counts["modified"]+=1
    total=len(entries)
    status=("PASS" if counts["matched"]==total and total>0 else "HOLD")
    return {"schema":"janus.legacy_release_manifest_audit.v1",
            "status":status,"manifest_entries":total,**counts,
            "runtime_execution_authorized":False,
            "external_dispatch_authorized":False}

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",required=True,type=Path)
    p.add_argument("--root",required=True,type=Path)
    p.add_argument("--max-bytes",type=int,default=131072)
    args=p.parse_args()
    result=audit(json.loads(args.manifest.read_text(encoding="utf-8-sig")),
                 args.root,args.max_bytes)
    print(json.dumps(result,sort_keys=True))
    return 0 if result["status"]=="PASS" else 2

if __name__=="__main__":
    raise SystemExit(main())
