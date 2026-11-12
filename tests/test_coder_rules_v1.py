"""Offline tested binding of curated, locally reviewed JANUS coder rules."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules/autonomy_coder"))
import author
from policy import digest


class RulesTests(TestCase):
    def test_curated_python_reference_is_data_not_executable(self):
        rules = author.load_coder_rules()
        self.assertEqual(rules["schema"], "janus.autonomous_coder.rules.v1")
        self.assertEqual(rules["execution_mode"], "PROPOSE_VERIFY_ISOLATED")
        self.assertEqual(len(rules["authoring_rules"]), 9)
        self.assertTrue(any("no trailing whitespace" in x for x in rules["authoring_rules"]))
        self.assertFalse(rules["autonomy_boundaries"]["untrusted_side_effects"])
        self.assertEqual(rules["autonomy_boundaries"]["security_grant_delta"], 0)
        self.assertEqual(rules["reported_personal_python_fork"], "NOT_IDENTIFIED_IN_CURRENT_REPO_INVENTORY")
        self.assertEqual(len(digest(rules)), 64)

    def test_corrupt_rules_file_fails_closed(self):
        with TemporaryDirectory() as temp:
            p = Path(temp) / "rules.json"
            p.write_text(json.dumps({"schema": "untrusted", "authoring_rules": []}))
            with patch.object(author, "RULES_FILE", p):
                with self.assertRaises(ValueError):
                    author.load_coder_rules()
