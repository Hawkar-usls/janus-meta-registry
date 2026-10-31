"""Synthetic preflight tests: never open a historic JANUS database."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

S=Path(__file__).resolve().parents[1]/"scripts"/"legacy_sqlite_wal_header_preflight.py"
spec=importlib.util.spec_from_file_location("preflight",S)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def make_db(page=4096):
    b=bytearray(100);b[:16]=b"SQLite format 3\x00"
    b[16:18]=(1 if page==65536 else page).to_bytes(2,"big")
    return bytes(b)
def make_wal(page=4096):
    b=bytearray(32)
    b[:4]=(0x377f0682).to_bytes(4,"big")
    b[4:8]=(3007000).to_bytes(4,"big")
    b[8:12]=page.to_bytes(4,"big")
    return bytes(b)

class WALMetadataTests(unittest.TestCase):
    def test_valid_header_is_not_recovery_proof(self):
        result=m.inspect_headers(make_db(),make_wal(),300_000_000,32+100*(4096+24))
        self.assertEqual(result["status"],"HEADER_AND_FRAME_LAYOUT_PLAUSIBLE_ONLY")
        self.assertEqual(result["potential_wal_frames"],100)
        self.assertFalse(result["recovery_proven"])
        self.assertFalse(result["safe_to_auto_replace_primary_db"])
        self.assertEqual(result["rows_scanned"],0)
    def test_truncated_and_incomplete_frames_hold(self):
        self.assertEqual(m.inspect_headers(b"x",b"y",1,1)["status"],"HOLD_TRUNCATED_HEADER")
        for size in (31,33,32+4096,32+4120*10+1):
            with self.subTest(size=size):
                self.assertEqual(m.inspect_headers(make_db(),make_wal(),4096,size)["status"],"HOLD_FORMAT_OR_ALIGNMENT")
    def test_changed_page_size_and_bad_magic_hold(self):
        self.assertEqual(m.inspect_headers(make_db(),make_wal(8192),100,32+8216)["status"],"HOLD_FORMAT_OR_ALIGNMENT")
        bad=b"x"*16+make_db()[16:]
        self.assertEqual(m.inspect_headers(bad,make_wal(),100,32+4120)["status"],"HOLD_FORMAT_OR_ALIGNMENT")
    def test_read_only_small_fixture(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t)
            db=d/"test.db";wal=d/"test.db-wal"
            db.write_bytes(make_db())
            wal.write_bytes(make_wal()+bytes(4096+24))
            before=(db.read_bytes(),wal.read_bytes())
            result=m.probe(db,wal)
            self.assertEqual(result["potential_wal_frames"],1)
            self.assertEqual((db.read_bytes(),wal.read_bytes()),before)

if __name__=="__main__":
    unittest.main()
