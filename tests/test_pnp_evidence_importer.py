"""Offline tests for append-only JANUS PNP evidence importer."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("pnp_importer",ROOT/"modules"/"pnp_evidence_importer"/"bridge.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

FUND=b"P_VS_NP = OPEN\n2^s * 3^r\n"
TOPA=b'{"status":"REFUTED_FOR_CURRENT_POLICY0A"}'
SHA="a"*40
T_SHA="b"*40
B_SHA="c"*40
D_SHA="d"*40

def make_context():
    bundle={
        "schema":"janus.pnp.content_evidence_bundle.v1",
        "status":"BOUNDED_SOURCE_CONTENT_REPLAYED",
        "p_vs_np":"OPEN",
        "fundamentum":{"repository":"Hawkar-usls/Janus-Fundamentum",
                        "source_commit":SHA,"path":"docs/CURRENT_RESEARCH_STATUS.md",
                        "sha256":m.sha(FUND),"independent_finite_replay":{"general_theorem_proved":False}},
        "topa":{"repository":"Hawkar-usls/TOPA","source_commit":T_SHA,
                "path":"data/TOPA-P-VS-NP-ISSUE-211-REFUTATION-FINAL-2026-08-24-v1.0.json",
                "sha256":m.sha(TOPA),"source_reported_result":"REFUTED_FOR_CURRENT_POLICY0A",
                "global_p_vs_np_result":"OPEN",
                "independent_finite_replay":{"full_policy0a_replay_executed":False}},
        "beetle":{"source_commit":B_SHA,"source_context_sha256":"f"*64,
                  "last_processed_sequence":84,"last_processing_receipt_sha256":"e"*64,
                  "independent_source_truth_established":False},
        "authority":{"scientific_promotion":False,"autonomous_merge":False}
    }
    bundle["bundle_sha256"]=m.hash_obj(bundle)
    supervisor={
        "status":"ACTIVE_FAIL_CLOSED","promotion_barrier":"BLOCKED",
        "autonomous_merge":False,"fundamentum_mutation":False,
        "scientific_claim_promotion":False,"p_vs_np_auto_promotion":False,
        "candidate_routes":[{"candidate_id":"A3","promotion_barrier":"BLOCKED",
                             "content_evidence_verification":"FINITE_ONLY_NO_PROMOTION"}],
        "content_evidence":{"bundle_sha256":bundle["bundle_sha256"],
                            "may_satisfy_promotion_gate":False,
                            "source_truth_independently_proven":False}
    }
    context={"schema":"janus.pnp_autoresearch_context.v1",
             "status":"ACTIVE_CANDIDATE_RESEARCH",
             "fundamentum":{"commit":SHA,"tracks":{"P_VS_NP":"OPEN"}},
             "content_evidence_bundle":bundle,
             "research_supervisor":supervisor,
             "authority":{"scientific_claim_promotion":False}}
    context["context_sha256"]=m.hash_obj(context)
    return context

class FakeFetch:
    def file(self,repo,commit,path):
        if repo=="Janus-Fundamentum":
            assert commit==SHA
            return FUND
        if repo=="TOPA":
            assert commit==T_SHA
            return TOPA
        if repo=="Janus-Demiurge" and commit==B_SHA:
            if path.endswith("CONTEXT.json"):
                ctx={"schema":"janus.beetle.runtime_context.v1",
                     "last_processed_sequence":84,
                     "capabilities":{"is_verified_evidence":False,
                                     "may_grant_mutation_authority":False}}
                ctx["context_sha256"]=m.hash_obj(ctx)
                return m.canonical(ctx)
            return m.canonical({"schema":"janus.beetle.processing_ack.v1",
                                 "last_sequence":84,"receipt_sha256":"e"*64})
        raise AssertionError((repo,commit,path))

class ImporterTests(unittest.TestCase):
    def test_accept_scope_and_no_promotion(self):
        ctx=make_context()
        bundle=m.check_context(ctx)
        self.assertEqual(bundle["p_vs_np"],"OPEN")
        self.assertFalse(bundle["authority"]["scientific_promotion"])

    def test_digest_and_claim_mutations_rejected(self):
        for change in ("claim","authority","hash"):
            x=make_context()
            if change=="claim":
                x["fundamentum"]["tracks"]["P_VS_NP"]="PROVED"
            elif change=="authority":
                x["research_supervisor"]["candidate_routes"][0]["promotion_barrier"]="PASS"
            else:
                x["content_evidence_bundle"]["topa"]["source_reported_result"]="P_EQUALS_NP"
            with self.subTest(change=change),self.assertRaises(m.IntakeHold):
                m.check_context(x)

    def test_append_immutable_idempotent_and_history(self):
        ctx=make_context()
        record=m.build_record(ctx,D_SHA,{"fundamentum_bytes_rehashed":True},
                              "2026-11-01T00:00:00+00:00")
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            self.assertEqual(m.persist(root,record)["status"],"APPENDED_UNMODIFIED_HISTORY")
            journal=root/m.DEST/"HISTORY.jsonl"
            self.assertEqual(len(journal.read_text().splitlines()),1)
            again=copy.deepcopy(record)
            again["origin"]["commit"]="1"*40
            again["observed_at_utc"]="2026-11-01T02:00:00+00:00"
            self.assertEqual(m.persist(root,again)["status"],"IDEMPOTENT_NO_CHANGE")
            self.assertEqual(len(journal.read_text().splitlines()),1)
            changed=copy.deepcopy(record)
            changed["content_bundle_sha256"]="0"*64
            with self.assertRaises(m.IntakeHold):
                m.persist(root,changed)

    def test_primary_source_content_byte_tamper_rejected(self):
        x=make_context()["content_evidence_bundle"]
        class Corrupt(FakeFetch):
            def file(self,repo,commit,path):
                if repo=="TOPA":
                    return b"changed"
                return super().file(repo,commit,path)
        with self.assertRaises(m.IntakeHold):
            m.check_sources(Corrupt(),x)

    def test_beetle_context_hash_cannot_be_forged(self):
        bundle=make_context()["content_evidence_bundle"]
        class ValidBeetle(FakeFetch):
            def file(self,repo,commit,path):
                if repo=="Janus-Demiurge":
                    ctx={"schema":"janus.beetle.runtime_context.v1",
                         "last_processed_sequence":84,
                         "capabilities":{"is_verified_evidence":False,"may_grant_mutation_authority":False}}
                    ctx["context_sha256"]=m.hash_obj(ctx)
                    bundle["beetle"]["source_context_sha256"]=ctx["context_sha256"]
                    return m.canonical(ctx) if path.endswith("CONTEXT.json") else m.canonical({
                        "last_sequence":84,"receipt_sha256":"e"*64})
                return super().file(repo,commit,path)
        report=m.check_sources(ValidBeetle(),bundle)
        self.assertFalse(report["independent_source_truth_established"])

if __name__=="__main__":
    unittest.main()
