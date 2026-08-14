import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "fo3_fos_james_state_diff_v0_1.py"
spec = importlib.util.spec_from_file_location("scanner", MODULE_PATH)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


def blob(*formids):
    out = bytearray(b"HEADER" + b"x" * 40)
    for fid in formids:
        out.extend(b"A" * 17)
        out.extend(fid.to_bytes(4, "little"))
        out.extend(b"B" * 19)
    return bytes(out)


def test_scan_finds_exact_little_endian_formid(tmp_path):
    p = tmp_path / "T1.fos"
    p.write_bytes(blob(scanner.ANCHORS["MQDadRef"]))
    r = scanner.scan_one(p)
    hit = r["patterns"]["MQDadRef"]["encodings"]["u32_little_endian"]
    assert hit["count"] == 1
    assert len(hit["context_sha256"]) == 1


def test_timeline_labels_raw_survival_without_structured_claim(tmp_path):
    paths = {}
    data = {
        "T0": blob(),
        "T1": blob(scanner.ANCHORS["MQ04DocRef"]),
        "T2": blob(scanner.ANCHORS["MQ04DocRef"]),
        "T3": blob(scanner.ANCHORS["MQ04DocRef"]),
    }
    for tp, b in data.items():
        p = tmp_path / f"{tp}.fos"
        p.write_bytes(b)
        paths[tp] = scanner.scan_one(p)
    t = scanner.summarize_timeline(paths)["MQ04DocRef"]
    assert t["appears_after_T0"] is True
    assert t["present_T1_and_T2"] is True
    assert t["raw_presence_survives_T3"] is True
    assert "NOT_STRUCTURED_PERSISTENCE" in t["classification"]


def test_negative_control_is_in_anchor_set():
    assert "MQ04PlayerContainerRef_NEGATIVE_CONTROL" in scanner.ANCHORS
