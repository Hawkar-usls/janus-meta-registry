"""Synthetic fail-closed tests of historic NAS A18 integrity checker."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/"scripts"/"legacy_release_manifest_audit.py"
spec=importlib.util.spec_from_file_location("legacy_release_manifest_audit",SCRIPT)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def entry(p: str, b: bytes):
    return {"path":p,"sha256":hashlib.sha256(b).hexdigest(),"size":len(b)}

class HistoricalManifestTests(unittest.TestCase):
    def test_valid_complete_release(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/"sub").mkdir()
            (root/"sub"/"file.json").write_bytes(b'{"pass":true}')
            proof=mod.audit({"files":[entry("sub/file.json",b'{"pass":true}')]},root)
            self.assertEqual(proof["status"],"PASS")
            self.assertEqual(proof["matched"],1)
            self.assertFalse(proof["runtime_execution_authorized"])

    def test_missing_and_replaced_file_hold(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/"one").write_bytes(b"replaced")
            manifest={"files":[entry("one",b"original"),entry("gone",b"gone")]}
            proof=mod.audit(manifest,root)
            self.assertEqual(proof["status"],"HOLD")
            self.assertEqual(proof["modified"],1)
            self.assertEqual(proof["missing"],1)

    def test_unsafe_names_and_duplicate_records_hold(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/"ok").write_bytes(b"x")
            manifest={"files":[entry("ok",b"x"),entry("ok",b"x"),
                               entry("../escape",b"x"),entry("/absolute",b"x"),
                               entry("sub/../ok",b"x")]}
            proof=mod.audit(manifest,root)
            self.assertEqual(proof["matched"],1)
            self.assertEqual(proof["unsafe"],4)
            self.assertEqual(proof["status"],"HOLD")

    def test_no_unbounded_file_reads(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            b=b"z"*200
            (root/"large").write_bytes(b)
            proof=mod.audit({"files":[entry("large",b)]},root,max_bytes=64)
            self.assertEqual(proof["oversize"],1)
            self.assertEqual(proof["status"],"HOLD")

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/"a").write_bytes(b"small")
            try:
                (root/"alias").symlink_to(root/"a")
            except OSError:
                self.skipTest("No symlinks on this host")
            proof=mod.audit({"files":[entry("alias",b"small")]},root)
            self.assertEqual(proof["unsafe"],1)
            self.assertEqual(proof["matched"],0)

    def test_empty_or_invalid_manifest_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            self.assertEqual(mod.audit({"files":[]},root)["status"],"HOLD")
            with self.assertRaisesRegex(ValueError,"MANIFEST_ENTRIES_INVALID"):
                mod.audit({"files":"bad"},root)

if __name__=="__main__":
    unittest.main()
