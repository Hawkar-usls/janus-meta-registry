#!/usr/bin/env python3
"""Metadata-only preflight for an offline SQLite DB + WAL pair.

Reads exactly a 100-byte DB header and 32-byte WAL header. Never opens SQLite,
loads rows, checkpoints WAL, writes a file, or claims recoverability.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

MAGICS={0x377f0682,0x377f0683}
VALID_PAGES={512,1024,2048,4096,8192,16384,32768,65536}

def inspect_headers(db: bytes, wal: bytes, db_size: int, wal_size: int) -> dict:
    if len(db)<100 or len(wal)<32:
        return {"status":"HOLD_TRUNCATED_HEADER","recovery_proven":False}
    db_ok=db[:16]==b"SQLite format 3\x00"
    db_page=int.from_bytes(db[16:18],"big")
    if db_page==1:
        db_page=65536
    wal_magic=int.from_bytes(wal[:4],"big")
    wal_version=int.from_bytes(wal[4:8],"big")
    wal_page=int.from_bytes(wal[8:12],"big")
    wal_format_ok=wal_magic in MAGICS and wal_version==3007000
    page_match=db_page==wal_page and wal_page in VALID_PAGES
    frame=wal_page+24 if wal_page in VALID_PAGES else 0
    aligned=frame>0 and wal_size>=32 and (wal_size-32)%frame==0
    status=("HEADER_AND_FRAME_LAYOUT_PLAUSIBLE_ONLY"
            if db_ok and wal_format_ok and page_match and aligned
            else "HOLD_FORMAT_OR_ALIGNMENT")
    return {"schema":"janus.sqlite_wal.metadata_preflight.v1",
            "status":status,"db_bytes":db_size,"wal_bytes":wal_size,
            "db_magic_ok":db_ok,"wal_magic_ok":wal_magic in MAGICS,
            "wal_version_ok":wal_version==3007000,
            "page_size_matches":page_match,"frame_aligned":aligned,
            "potential_wal_frames":(wal_size-32)//frame if aligned else None,
            "rows_scanned":0,"wal_checkpoint_performed":False,
            "recovery_proven":False,"safe_to_auto_replace_primary_db":False}

def probe(db_path:Path, wal_path:Path)->dict:
    if db_path.is_symlink() or wal_path.is_symlink():
        raise ValueError("REFUSE_SYMLINK_SOURCE")
    if not db_path.is_file() or not wal_path.is_file():
        raise ValueError("PAIR_INCOMPLETE")
    with db_path.open("rb") as handle:db=handle.read(100)
    with wal_path.open("rb") as handle:wal=handle.read(32)
    return inspect_headers(db,wal,db_path.stat().st_size,wal_path.stat().st_size)

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("--db",type=Path,required=True)
    a.add_argument("--wal",type=Path,required=True)
    args=a.parse_args()
    result=probe(args.db,args.wal)
    print(json.dumps(result,sort_keys=True))
    return 0 if result["status"]=="HEADER_AND_FRAME_LAYOUT_PLAUSIBLE_ONLY" else 2

if __name__=="__main__":
    raise SystemExit(main())
