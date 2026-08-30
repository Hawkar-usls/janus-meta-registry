from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "research/site/janus_hrain_full_memory_export.py"
spec = importlib.util.spec_from_file_location("janus_hrain_full_memory_export", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_memory_classes_keep_database_and_infrastructure_distinct():
    assert module.memory_class("data/X.json") == "REGISTRY_OBJECT"
    assert module.memory_class("registry/Y.json") == "REGISTRY_OBJECT"
    assert module.memory_class("research/topic/Z.md") == "RESEARCH_OBJECT"
    assert module.memory_class(".janus/JANUS_ORGANISM_LINK.json") == "SYSTEM_CONTRACT"
    assert module.memory_class(".github/workflows/x.yml") == "AUTOMATION"
    assert module.memory_class("assets/site.js") == "PRESENTATION_ASSET"
    assert module.memory_class("research/site/tool.py") == "TOOLING"


def test_full_current_catalog_accounts_for_every_tracked_blob(tmp_path):
    output = tmp_path / "full-memory"
    manifest = module.build_catalog(output_root=output, shard_size=37)
    module.validate_catalog(output, manifest)

    coverage = manifest["coverage"]
    assert coverage["coverage_complete"] is True
    assert coverage["tracked_blob_count"] == coverage["cataloged_blob_count"] + coverage["generated_self_export_exclusion_count"]
    assert manifest["mode"] == "FULL_CURRENT"
    assert manifest["historical_lineage_included"] is False
    assert manifest["authority"]["read_only"] is True
    assert manifest["authority"]["scientific_authority_granted"] is False

    objects = []
    for shard_meta in manifest["sharding"]["shards"]:
        shard = json.loads((output / "shards" / Path(shard_meta["path"]).name).read_text(encoding="utf-8"))
        objects.extend(shard["objects"])

    paths = [item["path"] for item in objects]
    assert paths == sorted(paths)
    assert len(paths) == len(set(paths))
    assert "PROJECT_STATUS.json" in paths
    assert "data/JANUS-HRAIN-META-REGISTRY-BRIDGE-v1.1.json" in paths
    assert all(not path.startswith(module.GENERATED_PREFIX) for path in paths)


def test_catalog_digest_is_deterministic_for_same_repository_state(tmp_path):
    first = module.build_catalog(output_root=tmp_path / "a", shard_size=53)
    second = module.build_catalog(output_root=tmp_path / "b", shard_size=53)
    assert first["source_commit"] == second["source_commit"]
    assert first["catalog_digest"] == second["catalog_digest"]
    assert first["coverage"] == second["coverage"]
    assert first["statistics"] == second["statistics"]
