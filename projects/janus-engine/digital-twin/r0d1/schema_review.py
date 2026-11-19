"""R0D1B: read only, never execute archive code."""
import json
import pathlib
import tarfile
import tempfile
import hashlib
from archive_audit import download, inspect, MD5
EXPECTED_SHA256 = "fdcf8d27c8d04e7f47db14039c366b79e12ccc7e00d789a198189be3c931db9a"
ROOT = "experiments/"
DOCS = ["00README","exp_aggregate_data.txt","pump_calibration.txt","exp08_production/experiment_example_figure.py","python/oxygenflux.py","python/aggregate_analysis.py","exp08_production/description.txt","exp08_production/analysis08.py","exp08_production/oxygen_production_without_fc.py","exp10/description.txt","exp10/analysis10.py","exp10/p_curves.py","exp09_fuelcell_calibration/description.txt","exp09_fuelcell_calibration/fc_performance.py","exp05_production/description.txt","exp05_production/O2_H2_match.py","exp03_volume_test/description.txt","exp01_fc_power/description.txt"]
def main():
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d)/"experiments.tgz"
        download(p)
        inventory = inspect(p, MD5)
        if inventory["sha256"] != EXPECTED_SHA256:
            raise ValueError("R0D1A sha256 mismatch")
        report = {"stage":"R0D1B_SCHEMA","source_sha256":EXPECTED_SHA256,"docs":{},"data_headers":{},"figure3_reproduced":False}
        with tarfile.open(p,"r:gz") as t:
            for name in DOCS:
                m=t.getmember(ROOT+name)
                if not m.isfile() or m.size > 50000:
                    raise ValueError("unexpected document")
                report["docs"][name] = t.extractfile(m).read().decode("utf-8",errors="replace")
            for m in t.getmembers():
                if m.isfile() and "/data" in m.name and m.name.endswith(".txt"):
                    with t.extractfile(m) as f:
                        report["data_headers"][m.name]=f.read(2048).decode("utf-8",errors="replace").splitlines()[:6]
        pathlib.Path("verified-experiments.tgz").write_bytes(p.read_bytes())
        pathlib.Path("schema-review.json").write_text(json.dumps(report,indent=2,ensure_ascii=True)+"\n")
        print("Schema review: ",len(report["docs"]),"documents,",len(report["data_headers"]),"data headers")
if __name__=="__main__":
    main()
