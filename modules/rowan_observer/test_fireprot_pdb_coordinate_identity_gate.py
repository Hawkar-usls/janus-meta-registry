"""Pure PDB-format, archived-source & label-isolation tests, no provider access."""
from __future__ import annotations
import importlib.util,io,json,hashlib,zipfile,unittest
from pathlib import Path
from unittest import mock
p=Path(__file__).with_name("fireprot_pdb_coordinate_identity_gate.py")
s=importlib.util.spec_from_file_location("fireprot_pdb_coordinate_identity_gate",p)
g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
WT="ACDEFGHIKLMNPQRSTVWYACDEFGHIKL"
AA3={"A":"ALA","C":"CYS","D":"ASP","E":"GLU","F":"PHE","G":"GLY",
     "H":"HIS","I":"ILE","K":"LYS","L":"LEU","M":"MET","N":"ASN",
     "P":"PRO","Q":"GLN","R":"ARG","S":"SER","T":"THR","V":"VAL",
     "W":"TRP","Y":"TYR"}

def atom(i,aa,chain="A"):
    return f"ATOM  {i:5d}  CA  {AA3[aa]:>3s} {chain}{i:4d}    {i*1.0:8.3f}{0.:8.3f}{0.:8.3f}{1.:6.2f}{50.:6.2f}           C\n"

def fixture(mutate=None):
    domains=[];zipbuf=io.BytesIO()
    with zipfile.ZipFile(zipbuf,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for j in range(10):
            pid=f"{j:04}"
            member=f"fireprot_upload/pdbs/{pid}.pdb"
            seq=WT
            content="".join(atom(i+1,a) for i,a in enumerate(seq)).encode()
            if mutate is not None and j==0:
                content=mutate(content)
            z.writestr(member,content)
            variants=[]
            for pos in range(20):
                wt=seq[pos];alt="A" if wt!="A" else "C"
                altseq=seq[:pos]+alt+seq[pos+1:]
                variants.append({"mutation":f"{wt}{pos+1}{alt}",
                    "pdb_position_zero_based":pos,"wild_type_residue":wt,
                    "mutant_residue":alt,
                    "mutant_sequence_sha256":g.digest(altseq.encode("ascii"))})
            domains.append({"pdb_id":pid,"pdb_chain":"A",
                "pdb_member":member,"pdb_member_sha256":g.digest(content),
                "wildtype_sequence":seq,"wildtype_sha256":g.digest(seq.encode("ascii")),
                "variants":variants})
    manifest=json.dumps({"domains":domains}).encode()
    archive=zipbuf.getvalue()
    return manifest,archive

def checked(manifest,archive):
    with mock.patch.object(g,"MANIFEST_SHA256",g.digest(manifest)),\
         mock.patch.object(g,"ARCHIVE_SHA256",g.digest(archive)),\
         mock.patch.object(g,"ARCHIVE_MD5",hashlib.md5(archive).hexdigest()):
        return g.audit(manifest,archive)

class FireProtPDBIdentity(unittest.TestCase):
    def test_exact_pdb_atom_construction(self):
        content="".join(atom(i+1,a) for i,a in enumerate(WT)).encode()
        self.assertEqual(g.extract_pdb_sequences(content),{"A":WT})
    def test_all_ten_and_two_hundred_identity_pass(self):
        m,a=fixture()
        out=checked(m,a)
        self.assertEqual(out["safe_single_chain_external_wt_count"],10)
        self.assertEqual(out["source_mutant_records_reproduced_without_labels"],200)
        self.assertFalse(out["structural_calibration_or_prediction_validated"])
    def test_missing_pdb_residue_is_fail_closed_not_reindexed(self):
        m,a=fixture(lambda _:("".join(atom(i+1,c) for i,c in enumerate(WT) if i!=11)).encode())
        out=checked(m,a)
        self.assertEqual(out["pdbs"][0]["curated_vs_coordinate_identity"],"AUTHOR_PDB_SEQUENCE_NOT_EXACT_COORDINATE_MAP")
        self.assertFalse(out["pdbs"][0]["safe_single_chain_boltz_wt_technical_pilot"])
    def test_unexpected_chain_fails_identity(self):
        m,a=fixture(lambda content:content.replace(b" A",b" B"))
        out=checked(m,a)
        self.assertFalse(out["pdbs"][0]["safe_single_chain_boltz_wt_technical_pilot"])
    def test_pdb_hash_drift_blocks(self):
        m,a=fixture()
        decoded=json.loads(m);decoded["domains"][0]["pdb_member_sha256"]="0"*64
        alt=json.dumps(decoded).encode()
        with self.assertRaisesRegex(g.IdentityHold,"PDB_MEMBER_SHA_DRIFT"):
            checked(alt,a)
    def test_bad_mutation_position_blocks(self):
        m,a=fixture()
        decoded=json.loads(m);decoded["domains"][0]["variants"][0]["pdb_position_zero_based"]=999
        alt=json.dumps(decoded).encode()
        with self.assertRaisesRegex(g.IdentityHold,"MUTATION_POSITION_INVALID"):
            checked(alt,a)
    def test_duplicate_conflicting_residue_blocks(self):
        self.assertRaisesRegex(g.IdentityHold,"PDB_RESIDUE_IDENTITY_CONFLICT",
            g.extract_pdb_sequences,(atom(1,"A")+atom(1,"Y")).encode())
    def test_raw_dataset_hash_drift_blocks(self):
        m,a=fixture()
        with self.assertRaisesRegex(g.IdentityHold,"FROZEN_MANIFEST_SHA_DRIFT"):
            g.audit(m,a)
        with mock.patch.object(g,"MANIFEST_SHA256",g.digest(m)):
            with self.assertRaisesRegex(g.IdentityHold,"FIREPROT_ARCHIVE_SHA_DRIFT"):
                g.audit(m,a)
    def test_public_archive_no_outcome_read(self):
        m,a=fixture()
        out=checked(m,a)
        self.assertFalse(out["published_experimental_labels_accessed"])
        self.assertEqual(out["rowan_paid_calls"],0)
        self.assertEqual(out["FireProt_210_boltz_inferences"],0)
        self.assertFalse(out["production_promotion"])
if __name__=="__main__":unittest.main()
