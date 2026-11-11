"""Offline provenance and hostile-source tests for JANUS public intake."""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlsplit
import zipfile

from tools.janus_public_source_intake import (
    ARCHIVE_LIMIT, GDELT_MANIFEST, GDELT_MASTER, GDELT_ZIP_RE, SCHEMA,
    IntakeError, collect, digest, gdelt_manifest_row, gdelt_master_fallback,
    get_gdelt, sample_gkg_zip,
    safe_url, validate_receipt, write_new,
)

GKG_URL="https://data.gdeltproject.org/gdeltv2/20261111144500.gkg.csv.zip"

def make_gkg():
    raw=b"\t".join([b"source"]*27)+b"\n"
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("20261111144500.gkg.csv",raw)
    return buf.getvalue()

def fixture():
    z=make_gkg()
    manifest=(
        f"120 0123456789abcdef0123456789abcdef http://data.gdeltproject.org/gdeltv2/20261111144500.export.CSV.zip\n"
        f"140 0123456789abcdef0123456789abcdef http://data.gdeltproject.org/gdeltv2/20261111144500.mentions.CSV.zip\n"
        f"{len(z)} {hashlib.md5(z,usedforsecurity=False).hexdigest()} "
        f"http://data.gdeltproject.org/gdeltv2/20261111144500.gkg.csv.zip\n"
    ).encode()
    def fake(url,limit):
        if url==GDELT_MANIFEST:return manifest
        if url==GKG_URL:return z
        host=urlsplit(url).hostname
        if host=="ru.wikipedia.org":
            return json.dumps({"query":{"pages":[{"title":"Замедление времени",
                "fullurl":"https://ru.wikipedia.org/wiki/Замедление_времени"}]}}).encode()
        if host=="api.openalex.org":
            return json.dumps({"results":[{"title":"Causality in quantum systems",
                "doi":"https://doi.org/10.1234/demo","publication_date":"2022-01-01"}]}).encode()
        if host=="api.github.com":
            return json.dumps({"workflow_runs":[{"id":43038783896,
                "head_sha":"2b9cc8c0e28f1922f51c2f0d645d58072499e9af",
                "status":"completed","conclusion":"success"}]}).encode()
        raise AssertionError("unknown fixed API URL "+url)
    return fake


class PublicIntake(unittest.TestCase):
    def test_synthetic_four_source_receipt(self):
        record=collect(fetch=fixture(),at="2026-11-11T15:00:00+00:00")
        self.assertEqual(record["schema"],SCHEMA)
        self.assertEqual(record["source_count_success"],4)
        self.assertEqual(record["source_count_attempted"],4)
        self.assertEqual(record["sources"]["gdelt_gkg"]["sample"]["first_row_field_count"],27)
        self.assertEqual(record["sources"]["gdelt_gkg"]["compressed_bytes"],len(make_gkg()))
        self.assertTrue(record["sources"]["gdelt_gkg"]["source_manifest_md5_verified"])
        self.assertIsNotNone(record["sources"]["wikipedia"]["article_metadata"])
        self.assertEqual(record["sources"]["tachyon_action"]["run_id"],43038783896)
        self.assertFalse(record["training_permitted"])
        self.assertFalse(record["factual_claims_verified"])
        validate_receipt(record)

    def test_stable_digest_idempotent_append_only_write(self):
        a=collect(fetch=fixture(),at="2026-11-11T15:00:00+00:00")
        b=collect(fetch=fixture(),at="2026-11-12T15:00:00+00:00")
        self.assertEqual(a["record_id"],b["record_id"])
        with tempfile.TemporaryDirectory() as t:
            path,first=write_new(a,Path(t))
            before=path.read_bytes()
            again,status=write_new(b,Path(t))
            self.assertEqual(path,again)
            self.assertIn("NEW",first)
            self.assertEqual(status,"ALREADY_ARCHIVED_NO_OVERWRITE")
            self.assertEqual(path.read_bytes(),before)

    def test_corrupt_sha_rejected(self):
        a=collect(fetch=fixture())
        a["training_permitted"]=True
        with self.assertRaisesRegex(IntakeError,"QUARANTINE_BYPASS"):
            validate_receipt(a)
        b=collect(fetch=fixture())
        b["sources"]["gdelt_gkg"]["compressed_bytes"]=123456
        with self.assertRaisesRegex(IntakeError,"RECEIPT_SHA_MISMATCH"):
            validate_receipt(b)

    def test_untrusted_host_and_local_file_urls_rejected(self):
        for url in (
            "http://localhost/secrets",
            "https://127.0.0.1/metadata",
            "https://evil.example/gdeltv2/20261111144500.gkg.csv.zip",
            "https://data.gdeltproject.org/gdeltv2/private.zip",
            "file:///home/user/private.json",
        ):
            with self.subTest(url=url):
                self.assertFalse(safe_url(url))
        self.assertTrue(safe_url(GKG_URL))
        self.assertIsNotNone(GDELT_ZIP_RE.fullmatch(GKG_URL))

    def test_malicious_manifest_host_rejected(self):
        text=(
            "1000 0123456789abcdef0123456789abcdef "
            "http://evil.example/gdeltv2/20261111144500.gkg.csv.zip"
        )
        with self.assertRaisesRegex(IntakeError,"GDELT_GKG_ENTRY_MISSING"):
            gdelt_manifest_row(text.encode())

    def test_manifest_source_size_cap(self):
        text=(
            f"{ARCHIVE_LIMIT+1} 0123456789abcdef0123456789abcdef "
            "http://data.gdeltproject.org/gdeltv2/20261111144500.gkg.csv.zip"
        )
        with self.assertRaisesRegex(IntakeError,"EXCEEDS_BOUNDED_BUDGET"):
            gdelt_manifest_row(text.encode())

    def test_malformed_gkg_cannot_enter_quarantine(self):
        with self.assertRaisesRegex(IntakeError,"GDELT_ZIP_INVALID"):
            sample_gkg_zip(b"not a zip")
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,"w") as z:
            z.writestr("bad.gkg.csv",b"not\t27\tfields\n")
        with self.assertRaisesRegex(IntakeError,"GDELT_GKG_ROW_SHAPE"):
            sample_gkg_zip(buf.getvalue())

    def test_official_master_fallback_once_on_latest_404(self):
        latest="20261111144500"
        previous="20261111143000"
        prior_url=f"https://data.gdeltproject.org/gdeltv2/{previous}.gkg.csv.zip"
        z=make_gkg()
        raw=(
            "incomplete first line\n"
            +f"{len(z)} {hashlib.md5(z,usedforsecurity=False).hexdigest()} "
             f"http://data.gdeltproject.org/gdeltv2/{previous}.gkg.csv.zip\n"
            +f"{len(z)} {hashlib.md5(z,usedforsecurity=False).hexdigest()} "
             f"http://data.gdeltproject.org/gdeltv2/{latest}.gkg.csv.zip\n"
        ).encode()
        manifest=(f"{len(z)} {hashlib.md5(z,usedforsecurity=False).hexdigest()} "
                  f"http://data.gdeltproject.org/gdeltv2/{latest}.gkg.csv.zip\n").encode()
        calls=[]
        def fake(url,limit):
            calls.append(url)
            if url==GDELT_MANIFEST:return manifest
            if url==GDELT_MASTER:return raw
            if url==prior_url:return z
            if latest in url:raise IntakeError("UPSTREAM_HTTP_404")
            raise AssertionError("unexpected outbound call")
        outcome=get_gdelt(fake)
        self.assertTrue(outcome["latest_advertised_gkg_url_returned_404"])
        self.assertTrue(outcome["fallback_from_official_master_tail"])
        self.assertEqual(outcome["gkg_url"],prior_url)
        self.assertEqual(outcome["manifest_url"],GDELT_MASTER)
        self.assertTrue(outcome["source_manifest_md5_verified"])
        self.assertEqual(len(calls),4)
        self.assertEqual(calls.count(GDELT_MASTER),1)

    def test_master_tail_rejects_invented_or_stale_batch(self):
        old="20261001140000"
        invalid=(f"partial\n10 0123456789abcdef0123456789abcdef "
                 f"https://data.gdeltproject.org/gdeltv2/{old}.gkg.csv.zip\n").encode()
        with self.assertRaisesRegex(IntakeError,"NO_MANIFESTED_PRIOR_GKG_BATCH"):
            gdelt_master_fallback(invalid,"20261111144500")
        spoof=(b"partial\n120 0123456789abcdef0123456789abcdef "
               b"https://evil.example/gdeltv2/20261111143000.gkg.csv.zip\n")
        with self.assertRaisesRegex(IntakeError,"NO_MANIFESTED_PRIOR_GKG_BATCH"):
            gdelt_master_fallback(spoof,"20261111144500")

    def test_checksum_mismatch_never_falls_silently(self):
        z=make_gkg()
        latest="20261111144500"
        manifest=(f"{len(z)} {'0'*32} "
                  f"http://data.gdeltproject.org/gdeltv2/{latest}.gkg.csv.zip\n").encode()
        def fake(url,limit):
            if url==GDELT_MANIFEST:return manifest
            if url.endswith(".gkg.csv.zip"):return z
            raise AssertionError("must never use fallback for integrity error")
        with self.assertRaisesRegex(IntakeError,"GDELT_ZIP_MANIFEST_MD5_MISMATCH"):
            get_gdelt(fake)

    def test_only_404_uses_fallback_not_rate_limit(self):
        z=make_gkg()
        latest="20261111144500"
        manifest=(f"{len(z)} {hashlib.md5(z,usedforsecurity=False).hexdigest()} "
                  f"http://data.gdeltproject.org/gdeltv2/{latest}.gkg.csv.zip\n").encode()
        calls=[]
        def fake(url,limit):
            calls.append(url)
            if url==GDELT_MANIFEST:return manifest
            raise IntakeError("UPSTREAM_HTTP_429")
        with self.assertRaisesRegex(IntakeError,"UPSTREAM_HTTP_429"):
            get_gdelt(fake)
        self.assertNotIn(GDELT_MASTER,calls)

    def test_one_provider_unavailable_while_others_preserved(self):
        good=fixture()
        def degraded(url,limit):
            if "api.openalex.org" in url:
                raise IntakeError("UPSTREAM_HTTP_429")
            return good(url,limit)
        r=collect(fetch=degraded)
        self.assertEqual(r["source_count_success"],3)
        self.assertEqual(r["sources"]["openalex"]["status"],"PROVIDER_UNAVAILABLE")
        self.assertEqual(r["sources"]["openalex"]["reason"],"UPSTREAM_HTTP_429")
        self.assertEqual(r["sources"]["gdelt_gkg"]["status"],"PUBLIC_GKG_BATCH_STRUCTURALLY_READABLE")
        validate_receipt(r)

    def test_all_failed_is_not_false_claim_receipt(self):
        def blocked(url,limit):raise IntakeError("UPSTREAM_HTTP_429")
        with self.assertRaisesRegex(IntakeError,"ALL_PUBLIC_SOURCES_UNAVAILABLE"):
            collect(fetch=blocked)

    def test_model_indexes_must_exclude_quarantine(self):
        from EYE.training.train_eye_registry import EXCLUDED_PREFIXES, iter_files
        self.assertIn("data/observations/public_source_quarantine/", EXCLUDED_PREFIXES)
        self.assertIn("data/observations/public_source_quality/", EXCLUDED_PREFIXES)
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/"data/observations/public_source_quarantine"
            directory.mkdir(parents=True)
            (directory/"JANUS-PUBLIC-SOURCES-test.json").write_text("{}")
            quality=Path(root)/"data/observations/public_source_quality"
            quality.mkdir(parents=True)
            (quality/"JANUS-R3-QUALITY-test.json").write_text("{}")
            (Path(root)/"allowed.json").write_text("{}")
            included={p.relative_to(root).as_posix() for p in iter_files(Path(root))}
            self.assertEqual(included,{"allowed.json"})

if __name__=="__main__":
    unittest.main()
