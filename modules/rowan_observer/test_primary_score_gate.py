"""Synthetic adversarial tests: source pin, sign, units, all eight rows, no silent flip."""
import csv, hashlib, importlib.util, io, json, unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location("primary_score_gate",
    Path(__file__).with_name("primary_score_gate.py"))
g=importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

LABELS=(-2.9513259829873366,-2.3129026098944245,-1.4905599208892324,
        -.8445540655216376,-.3899916009181281,.0025466003782845,
        .4403790583360027,1.3228887174599038)

def data():
    metadata={
        "DMS_id":g.DMS_ID,
        "raw_DMS_phenotype_name":g.RAW_COL,
        "raw_DMS_directionality":"1",
        "raw_DMS_filename":g.RAW_NAME,
        "raw_DMS_mutant_column":"mut_type",
        "target_seq":g.WT,"seq_len":"64",
        "selection_type":"cDNA display proteolysis",
        "DMS_number_single_mutants":"1084",
    }
    fields=list(metadata)
    buf=io.StringIO();w=csv.DictWriter(buf,fieldnames=fields)
    w.writeheader();w.writerow(metadata);meta=buf.getvalue().encode()
    cases=[];p_rows=[];r_rows=[]
    for mut,score in zip(g.MUTATIONS,LABELS):
        seq=g.mutation_sequence(mut)
        cases.append({"mutation":mut,"published_processed_label":score})
        p_rows.append({"sequences":seq,"labels":score,"fold_id":"2"})
        r_rows.append({"mut_type":mut,"aa_seq":seq,"ddG_ML_float":score})
    def csv_data(rows,fields,delimiter=","):
        b=io.StringIO();w=csv.DictWriter(b,fieldnames=fields,delimiter=delimiter)
        w.writeheader();w.writerows(rows);return b.getvalue().encode()
    processed=csv_data(p_rows,["sequences","labels","fold_id"],"\t")
    raw=csv_data(r_rows,["mut_type","aa_seq",g.RAW_COL])
    receipt={"schema_id":"janus.meta_registry.rowan_evidence_receipt.v1",
             "original_public_data_sha256":hashlib.sha256(processed).hexdigest(),
             "cases":cases}
    return meta,processed,raw,receipt

class LabelGateTests(unittest.TestCase):
    def test_verified_sign_and_all_eight_raw_rows(self):
        m,p,r,receipt=data()
        with patch.object(g,"METADATA_BLOB_SHA",g.git_blob_sha(m)),\
             patch.object(g,"TSV_SHA",hashlib.sha256(p).hexdigest()):
            result=g.run(m,p,receipt,r)
        self.assertEqual(result["status"],"PASS_EXACT_EIGHT_RAW_PROCESSED_ROW_IDENTITY")
        self.assertEqual(result["score_direction"],"POSITIVE_IS_STABILIZING")
        self.assertEqual(len(result["raw_rows"]),8)
        self.assertEqual(result["new_rowan_provider_jobs"],0)

    def test_metadata_only_is_explicit_hold(self):
        m,p,r,receipt=data()
        with patch.object(g,"METADATA_BLOB_SHA",g.git_blob_sha(m)),\
             patch.object(g,"TSV_SHA",hashlib.sha256(p).hexdigest()):
            result=g.run(m,p,receipt)
        self.assertEqual(result["status"],"HOLD_RAW_ROW_IDENTITY_NOT_CHECKED")
        self.assertFalse(result["raw_rows_verified"])

    def test_rejects_reversed_direction(self):
        m,p,r,receipt=data()
        m=m.replace(b",1,",b",-1,")
        with patch.object(g,"METADATA_BLOB_SHA",g.git_blob_sha(m)):
            with self.assertRaisesRegex(g.GateHold,"METADATA_DRIFT_raw_DMS_directionality"):
                g.verify_metadata(m)

    def test_rejects_raw_label_transform(self):
        m,p,r,receipt=data()
        bad=r.replace(str(LABELS[-1]).encode(),b"0.2")
        with self.assertRaisesRegex(g.GateHold,"RAW_TO_PROCESSED_TRANSFORM_NOT_IDENTITY_E42H"):
            g.verify_raw(bad,dict(zip(g.MUTATIONS,LABELS)))

    def test_rejects_misbound_processed_score(self):
        m,p,r,receipt=data()
        receipt["cases"][-1]["published_processed_label"]=42
        with patch.object(g,"TSV_SHA",hashlib.sha256(p).hexdigest()):
            with self.assertRaisesRegex(g.GateHold,"ARCHIVED_TO_PROCESSED_ROW_MISMATCH"):
                g.verify_processed(p,receipt)

    def test_rejects_duplicate_raw_mutant(self):
        m,p,r,receipt=data()
        header,first,*rest=r.decode().splitlines()
        mutated="\n".join([header,first,first,*rest])+"\n"
        with self.assertRaisesRegex(g.GateHold,"RAW_MUTATION_NOT_UNIQUE"):
            g.verify_raw(mutated.encode(),dict(zip(g.MUTATIONS,LABELS)))

    def test_rejects_missing_primary_raw_mutant(self):
        m,p,r,receipt=data()
        lines=r.decode().splitlines()
        truncated="\n".join(lines[:-1])+"\n"
        with self.assertRaisesRegex(g.GateHold,"RAW_ASSAY_EIGHT_ROWS_NOT_FOUND"):
            g.verify_raw(truncated.encode(),dict(zip(g.MUTATIONS,LABELS)))

    def test_rejects_source_hash_drift(self):
        m,p,r,receipt=data()
        with self.assertRaisesRegex(g.GateHold,"PROCESSED_SHA256_DRIFT"):
            g.verify_processed(p,receipt)

if __name__=="__main__":unittest.main()
