import importlib.util
import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "janus_unified_memory.py"
spec = importlib.util.spec_from_file_location("janus_unified_memory_v2", TARGET)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class UnifiedMemoryIsolatedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "registry"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Sandbox"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "sandbox@example.invalid"], check=True)
        (self.root/"research").mkdir()
        (self.root/"research/a.json").write_text('{"title":"SCOBY skin","ref":"research/b.json","details":"Biocellulose"}',encoding="utf-8")
        (self.root/"research/b.json").write_text('{"title":"SCOBY strength","value":"elastic modulus"}',encoding="utf-8")
        (self.root/"bad.json").write_text('{broken',encoding="utf-8")
        (self.root/"assets/hrain-full-memory").mkdir(parents=True)
        (self.root/"assets/hrain-full-memory/manifest.json").write_text('{}',encoding="utf-8")
        subprocess.run(["git","-C",str(self.root),"add","."],check=True)
        subprocess.run(["git","-C",str(self.root),"commit","-qm","fixture"],check=True)
        self.db = Path(self.tmp.name)/"index.sqlite"
    def tearDown(self):
        self.tmp.cleanup()
    def test_complete_import_fts_links(self):
        p=m.build(self.root,self.db)
        self.assertEqual((p["indexed_json"],p["excluded_self_export_json"],p["malformed_json"],p["explicit_relations"]),(3,1,1,1))
        self.assertEqual(m.verify(self.root,self.db)["sqlite_integrity"],"PASS")
        self.assertEqual(len(m.search(self.db,"Biocellulose")),1)
        self.assertEqual(len(m.search(self.db,"elastic")),1)
    def test_recovery_without_overwriting_corrupt_db(self):
        original=m.build(self.root,self.db)
        self.assertEqual(m.rebuild_verify(self.root,self.db)["recovery"],"PASS")
        self.db.write_bytes(b"broken-cache")
        with self.assertRaises(sqlite3.DatabaseError):
            m.verify(self.root,self.db)
        other=Path(self.tmp.name)/"rebuilt.sqlite"
        self.assertEqual(m.build(self.root,other),original)
        self.assertEqual(self.db.read_bytes(),b"broken-cache")
    def test_sha256_detects_modification(self):
        m.build(self.root,self.db)
        (self.root/"research/b.json").write_text('{"changed":true}',encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"SHA256_MISMATCH"):
            m.verify(self.root,self.db)
    def test_untracked_json_remains_outside_index(self):
        (self.root/"private.json").write_text('{"secret":"sensitive-placeholder"}',encoding="utf-8")
        p=m.build(self.root,self.db)
        self.assertEqual(p["indexed_json"],3)
        self.assertFalse(m.search(self.db,"sensitive-placeholder"))
    def test_read_only_projection_and_safety(self):
        m.build(self.root,self.db)
        target=Path(self.tmp.name)/"graph.json"
        summary=m.export(self.db,target)
        graph=json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual((summary["nodes"],summary["links"]),(3,1))
        self.assertTrue(graph["read_only"])
        self.assertFalse(graph["coverage"]["scientific_authority_granted"])
        with self.assertRaises(FileExistsError):
            m.build(self.root,self.db)
        with self.assertRaisesRegex(ValueError,"INDEX_INSIDE_SOURCE_FORBIDDEN"):
            m.build(self.root,self.root/"test.sqlite")

if __name__ == "__main__":
    unittest.main()
