import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("reviewed_eye", ROOT/"EYE/training/train_eye_registry.py")
eye = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(eye)
class GeneratedStatusFirewall(unittest.TestCase):
    def test_generated_roadmap_receipts_are_not_source_training_files(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root/"source.json").write_text('{"independent_source": true}')
            derived = root/"data/autonomy_loop/receipts"
            derived.mkdir(parents=True)
            (derived/"observation.json").write_text('{"status": "PASS"}')
            (derived.parent/"ROADMAP.md").write_text("An internally generated plan")
            names = {p.relative_to(root).as_posix() for p in eye.iter_files(root)}
            self.assertIn("source.json", names)
            self.assertFalse(any(p.startswith("data/autonomy_loop/") for p in names))
    def test_native_corpus_manifest_excludes_same_derivative_family(self):
        path = ROOT/"EYE/training/EYE-META-REGISTRY-TRAINING-MANIFEST-v1.0.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("data/autonomy_loop/", manifest["corpus_contract"]["excluded_generated_prefixes"])
        workflow = (ROOT/".github/workflows/eye-meta-registry-train.yml").read_text(encoding="utf-8")
        self.assertIn("'!data/autonomy_loop/**'", workflow)
if __name__ == "__main__":
    unittest.main()
