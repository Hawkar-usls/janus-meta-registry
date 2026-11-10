#!/usr/bin/env python3
"""JANUS Unified Memory v2: isolated current-tree JSON/FTS/graph index.
Sources are read-only; SQLite is disposable, never an authority for JSON provenance.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

SCHEMA = "janus.unified_memory.v2.isolated"
EXCLUDE = "assets/hrain-full-memory/"
ROOT_URL = "https://github.com/Hawkar-usls/janus-meta-registry/blob/"
RAW_URL = "https://raw.githubusercontent.com/Hawkar-usls/janus-meta-registry/"
SHA40 = re.compile(r"^[a-f0-9]{40}$")

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL)

def files(root: Path) -> tuple[list[str], int]:
    names = sorted(p.decode("utf-8") for p in git(root, "ls-files", "--cached", "-z").split(b"\0") if p.endswith(b".json"))
    selected = [p for p in names if not p.startswith(EXCLUDE)]
    return selected, len(names) - len(selected)

def head(root: Path) -> str:
    result = git(root, "rev-parse", "HEAD").decode().strip()
    if not SHA40.fullmatch(result):
        raise ValueError("SOURCE_HEAD_HOLD")
    return result

def connect(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(path), timeout=30)
    c.execute("PRAGMA foreign_keys=ON")
    c.executescript("""
      CREATE TABLE metadata(k TEXT PRIMARY KEY, v TEXT NOT NULL);
      CREATE TABLE documents(
        id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, sha256 TEXT NOT NULL,
        bytes INTEGER NOT NULL, namespace TEXT NOT NULL, title TEXT NOT NULL,
        parse_status TEXT NOT NULL, body TEXT NOT NULL, source_url TEXT NOT NULL);
      CREATE INDEX idx_doc_sha ON documents(sha256);
      CREATE INDEX idx_doc_ns ON documents(namespace);
      CREATE VIRTUAL TABLE docs_fts USING fts5(path,title,body,content='documents',content_rowid='id');
      CREATE TABLE edges(
        source_id INTEGER NOT NULL REFERENCES documents(id),
        target_id INTEGER NOT NULL REFERENCES documents(id),
        kind TEXT NOT NULL, pointer TEXT NOT NULL,
        PRIMARY KEY(source_id,target_id,kind,pointer));
      CREATE INDEX idx_edge_dst ON edges(target_id);
    """)
    return c

def strings(value, pointer="", level=0):
    if level > 40:
        return
    if isinstance(value, str):
        yield pointer or "/", value
    elif isinstance(value, dict):
        for k, child in value.items():
            key = str(k).replace("~", "~0").replace("/", "~1")
            yield from strings(child, pointer + "/" + key, level + 1)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from strings(child, pointer + "/" + str(i), level + 1)

def link_target(value: str, ids: dict[str, int]):
    if value in ids:
        return value, "EXPLICIT_PATH"
    if value.startswith(ROOT_URL):
        tail = value[len(ROOT_URL):]
    elif value.startswith(RAW_URL):
        tail = value[len(RAW_URL):]
    else:
        return None
    parts = tail.split("/", 1)
    if len(parts) != 2 or not (SHA40.fullmatch(parts[0]) or parts[0] in ("main", "master")):
        return None
    path = unquote(urlsplit("https://source.invalid/" + parts[1]).path.lstrip("/"))
    if path in ids:
        return path, "EXPLICIT_URL"
    return None

def build(root: Path, out: Path) -> dict:
    root = root.resolve()
    out = out.resolve()
    if not (root / ".git").exists():
        raise ValueError("GIT_CHECKOUT_REQUIRED")
    if out.is_relative_to(root):
        raise ValueError("INDEX_INSIDE_SOURCE_FORBIDDEN")
    if out.exists():
        raise FileExistsError("OUTPUT_MUST_NOT_EXIST")
    selected, excluded = files(root)
    version = head(root)
    for name in selected:
        if not (root / name).is_file():
            raise ValueError("TRACKED_FILE_MISSING:" + name)
    out.parent.mkdir(parents=True, exist_ok=True)
    c = connect(out)
    parse_ok = 0
    malformed = 0
    manifest = []
    try:
        for number, name in enumerate(selected, 1):
            raw = (root / name).read_bytes()
            try:
                body = raw.decode("utf-8")
                parsed = json.loads(body)
                status = "OK"
                parse_ok += 1
            except (UnicodeError, ValueError, TypeError):
                body = raw.decode("utf-8", "replace")
                parsed = None
                status = "MALFORMED"
                malformed += 1
            title = str(parsed.get("title") or parsed.get("artifact_id") or parsed.get("name") or Path(name).stem) if isinstance(parsed, dict) else Path(name).stem
            namespace = name.split("/", 1)[0] if "/" in name else "(root)"
            digest = sha(raw)
            c.execute("INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?)", (number, name, digest, len(raw), namespace, title[:240], status, body, ROOT_URL + version + "/" + name))
            c.execute("INSERT INTO docs_fts(rowid,path,title,body) VALUES(?,?,?,?)", (number, name, title[:240], body))
            manifest.append((name, digest, len(raw)))
        ids = {name:i for i,name in enumerate(selected,1)}
        for number, name in enumerate(selected, 1):
            try:
                parsed = json.loads((root / name).read_text(encoding="utf-8"))
            except (UnicodeError, ValueError, TypeError):
                continue
            for ptr, value in strings(parsed):
                hit = link_target(value, ids)
                if hit is None or hit[0] == name:
                    continue
                c.execute("INSERT OR IGNORE INTO edges VALUES(?,?,?,?)", (number, ids[hit[0]], hit[1], ptr[:1024]))
        relations = c.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        payload = {
            "schema":SCHEMA, "source_commit":version, "total_tracked_json":len(selected)+excluded,
            "excluded_self_export_json":excluded, "indexed_json":len(selected),
            "parsed_json":parse_ok,"malformed_json":malformed,
            "explicit_relations":relations, "source_manifest_sha256":sha(json.dumps(manifest, separators=(",",":"), ensure_ascii=False).encode()),
            "coverage_complete":True, "read_only":True, "historical_git_included":False,
            "scientific_authority_granted":False
        }
        c.executemany("INSERT INTO metadata VALUES(?,?)", [(k,json.dumps(v,ensure_ascii=False)) for k,v in payload.items()])
        c.commit()
        return payload
    finally:
        c.close()

def view(db: Path):
    if not db.is_file():
        raise FileNotFoundError("INDEX_NOT_FOUND")
    return sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=15)

def verify(root: Path, db: Path) -> dict:
    c = view(db)
    try:
        if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLITE_INTEGRITY_HOLD")
        meta = {k:json.loads(v) for k,v in c.execute("SELECT k,v FROM metadata")}
        selected, excluded = files(root)
        rows = c.execute("SELECT path,sha256,bytes FROM documents ORDER BY path").fetchall()
        if meta.get("source_commit") != head(root):
            raise ValueError("HEAD_DRIFT")
        if len(rows) != len(selected) or [r[0] for r in rows] != selected:
            raise ValueError("COVERAGE_MISMATCH")
        if meta["excluded_self_export_json"] != excluded:
            raise ValueError("EXCLUSION_MISMATCH")
        manifest=[]
        for path,digest,length in rows:
            raw = (root / path).read_bytes()
            if sha(raw) != digest or len(raw) != length:
                raise ValueError("SHA256_MISMATCH:" + path)
            manifest.append((path,digest,length))
        if sha(json.dumps(manifest, separators=(",",":"), ensure_ascii=False).encode()) != meta["source_manifest_sha256"]:
            raise ValueError("MANIFEST_DIGEST_MISMATCH")
        if c.execute("SELECT COUNT(*) FROM docs_fts").fetchone()[0] != len(rows):
            raise ValueError("FTS_COVERAGE_MISMATCH")
        if c.execute("SELECT COUNT(*) FROM edges").fetchone()[0] != meta["explicit_relations"]:
            raise ValueError("EDGE_COVERAGE_MISMATCH")
        return {**meta, "sqlite_integrity":"PASS", "sha256_integrity":"PASS", "fts_rows":len(rows)}
    finally:
        c.close()

def search(db: Path, phrase: str, limit: int=10):
    c = view(db)
    c.row_factory = sqlite3.Row
    try:
        return [dict(x) for x in c.execute("""
            SELECT d.path,d.title,d.namespace,d.sha256,d.source_url,
              snippet(docs_fts,2,'[',']','...',18) excerpt
            FROM docs_fts JOIN documents d ON d.id=docs_fts.rowid
            WHERE docs_fts MATCH ? ORDER BY rank LIMIT ?""", (phrase, min(100,max(1,limit))))]
    finally:
        c.close()

def export(db: Path, path: Path):
    if path.exists():
        raise FileExistsError("EXPORT_MUST_NOT_EXIST")
    c = view(db)
    c.row_factory = sqlite3.Row
    try:
        meta = {k:json.loads(v) for k,v in c.execute("SELECT k,v FROM metadata")}
        nodes = [dict(x) for x in c.execute("SELECT id,path,title,namespace,sha256,parse_status,source_url FROM documents ORDER BY path")]
        edges = [{"source":s,"target":t,"kind":k,"pointer":p} for s,t,k,p in c.execute("SELECT source_id,target_id,kind,pointer FROM edges ORDER BY source_id,target_id,kind,pointer")]
        blob = {"schema":"janus.unified_memory.hrain_readonly_projection.v1", "read_only":True,
                "source_commit":meta["source_commit"], "coverage":meta,"nodes":nodes,"links":edges}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(blob, ensure_ascii=False, separators=(",",":"))+"\n",encoding="utf-8")
        return {"nodes":len(nodes),"links":len(edges),"bytes":path.stat().st_size,"source_commit":meta["source_commit"]}
    finally:
        c.close()

def rebuild_verify(root: Path, db: Path):
    original=verify(root,db)
    with tempfile.TemporaryDirectory(prefix="janus-v2-recovery-") as td:
        rebuilt=Path(td)/"rebuild.sqlite"
        build(root,rebuilt)
        second=verify(root,rebuilt)
        if original!=second:
            raise ValueError("REBUILD_NOT_IDENTICAL")
        return {"recovery":"PASS", "indexed_json":second["indexed_json"],"source_manifest_sha256":second["source_manifest_sha256"]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("build","verify","search","rebuild-verify","export"))
    p.add_argument("--registry-root",type=Path)
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--query",default="SCOBY")
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    if a.action in ("build","verify","rebuild-verify") and not a.registry_root:
        p.error("--registry-root required")
    if a.action=="build": result=build(a.registry_root,a.db)
    elif a.action=="verify": result=verify(a.registry_root,a.db)
    elif a.action=="rebuild-verify": result=rebuild_verify(a.registry_root,a.db)
    elif a.action=="search": result=search(a.db,a.query)
    else:
        if not a.output:p.error("--output required")
        result=export(a.db,a.output)
    print(json.dumps(result,sort_keys=True,ensure_ascii=False))
if __name__=="__main__":
    main()
