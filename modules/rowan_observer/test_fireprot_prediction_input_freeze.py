"""Pure no-label tests of FireProt input freeze and zero-baseline commitment."""
from __future__ import annotations
import hashlib,importlib.util,json,unittest
from pathlib import Path
from unittest import mock

BASE=Path(__file__).resolve().parent
def load(name):
    spec=importlib.util.spec_from_file_location(name,BASE/(name+".py"))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
pick=load("fireprot_candidate_freeze")
zero=load("fireprot_freeze_zero_reference")
AA="ACDEFGHIKLMNPQRSTVWY"

def synthetic():
    rows=[];structures={}
    for ix in range(10):
        seq=(AA*2)
        # Distinct 40-amino-acid WT identities, no outcome dependence.
        seq=seq[:30]+AA[ix]+seq[31:]
        pid=f"T{ix:03}"
        structures[f"fireprot_upload/pdbs/{pid}.pdb"]=f"HEADER {pid}".encode()
        for pos in range(20):
            wt=seq[pos];alt="A" if wt!="A" else "C"
            row={"pdb_id_corrected":pid,"pdb_sequence":seq,"pdb_position":str(pos),
                 "wild_type":wt,"mutation":alt,"chain":"A",
                 "publication_doi":f"10.1234/test.{ix}","uniprot_id":f"U{ix}",
                 "interpro_families":f"IPR{ix:06d}",
                 "experiment_id":f"TST-{ix}-{pos}","ddG":str(ix*1000+pos),
                 "dTm":str(-ix*1000-pos)}
            rows.append(row)
    return rows,structures

def dummy_manifest():
    rows,structures=synthetic()
    domains,rejects,count=pick.rows_to_manifest(rows,structures)
    return {"schema_id":zero.SCHEMA,
      "honest_experiment_type":"RETROSPECTIVE_PUBLIC_DATASET_NOT_TRUE_BLIND_NO_INDEPENDENT_CUSTODIAN",
      "source":{"zip_sha256":zero.EXPECTED_DATASET_SHA},
      "inference":{"frozen_shadow_model_sha256":zero.EXPECTED_MODEL_SHA},
      "safety":{"new_rowan_jobs":0},
      "domains":domains}

class FireProtGateTests(unittest.TestCase):
    def test_200_variants_selected_from_ten_distinct_families(self):
        m=dummy_manifest()
        self.assertEqual(len(m["domains"]),10)
        preds=zero.validate_manifest(m)
        self.assertEqual(len(preds),200)
        self.assertTrue(all(v["predicted_delta_delta_G_kcal_per_mol"]==0 for v in preds))
    def test_selection_independent_of_available_outcome_values(self):
        rows,structures=synthetic()
        a,_,_=pick.rows_to_manifest(rows,structures)
        for row in rows:row["ddG"]=str(99999999.0);row["dTm"]="NA"
        b,_,_=pick.rows_to_manifest(rows,structures)
        self.assertEqual(pick.canonical(a),pick.canonical(b))
    def test_no_public_outcome_embedded(self):
        m=dummy_manifest()
        pick.assert_no_outcomes(m)
        m["domains"][0]["variants"][0]["ddG"]=9
        with self.assertRaisesRegex(pick.GateHold,"LABEL_FIELD_LEAK"):
            pick.assert_no_outcomes(m)
    def test_frozen_model_sha_required(self):
        m=dummy_manifest();m["inference"]["frozen_shadow_model_sha256"]="0"*64
        with self.assertRaisesRegex(zero.FreezeHold,"FROZEN_SHADOW_DIGEST_DRIFT"):
            zero.validate_manifest(m)
    def test_missing_protein_variant_blocks(self):
        m=dummy_manifest();m["domains"][0]["variants"].pop()
        with self.assertRaisesRegex(zero.FreezeHold,"VARIANT_COUNT_NOT_20"):
            zero.validate_manifest(m)
    def test_modified_mutant_digest_blocks(self):
        m=dummy_manifest();m["domains"][0]["variants"][0]["mutant_sequence_sha256"]="0"*64
        with self.assertRaisesRegex(zero.FreezeHold,"MUTANT_SEQUENCE_SHA_DRIFT"):
            zero.validate_manifest(m)
    def test_wildtype_digest_check(self):
        m=dummy_manifest();m["domains"][0]["wildtype_sha256"]="0"*64
        with self.assertRaisesRegex(zero.FreezeHold,"WILDTYPE_SEQUENCE_SHA_DRIFT"):
            zero.validate_manifest(m)
    def test_no_false_shadow_model_predictions(self):
        m=dummy_manifest();receipt=zero.freeze(m,"ab"*32)
        self.assertFalse(receipt["shadow_features_computed"])
        self.assertTrue(receipt["public_source_is_retrospective"])
        self.assertEqual(receipt["n_mutations"],200)
        self.assertEqual(receipt["new_rowan_jobs"],0)
    def test_no_blind_claim_accepted(self):
        m=dummy_manifest()
        m["honest_experiment_type"]="TRUE_INDEPENDENT_BLIND"
        with self.assertRaisesRegex(zero.FreezeHold,"MISSING_NONBLIND_DISCLOSURE"):
            zero.freeze(m,"ab"*32)
    def test_source_archive_checksum_required(self):
        with self.assertRaisesRegex(pick.GateHold,"FIREPROT_ZENODO_SOURCE_SHA_DRIFT"):
            pick.build(b"not a zip")
    def test_duplicate_wildtype_sequence_skipped(self):
        rows,structures=synthetic()
        # Give two PDBs identical amino-acid sequence, otherwise separate family.
        for row in rows:
            if row["pdb_id_corrected"]=="T001":
                row["pdb_sequence"]=next(x["pdb_sequence"] for x in rows if x["pdb_id_corrected"]=="T000")
                pos=int(row["pdb_position"]);row["wild_type"]=row["pdb_sequence"][pos]
        with self.assertRaisesRegex(pick.GateHold,"INSUFFICIENT_DISTINCT_PDB_FAMILIES"):
            pick.rows_to_manifest(rows,structures)

if __name__=="__main__":unittest.main()
