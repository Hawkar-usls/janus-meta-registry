"""R1.5: guard source-bound state, security and schedule in optimized workflow."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
FLOW = ROOT / ".github/workflows/janus-self-writer-real-operational-consumer.yml"
STATE = "ccb2f82edb0f1c61c460aa0a4521a9991e8d5eb2"
IMAGE = "python@sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b"
CODE_PATHS = ("/modules/autonomy_coder/", "/tests/test_real_operational_self_writer_consumer.py",
              "/data/autonomy_loop/LATEST.json")
STATE_PATHS = ("/STATE.json", "/MODULE_INDEX.json",
               "/attempts/", "/receipts/", "/self_modules/")


def check(text):
    critical = (
        "name: JANUS Self-Writer Real Operational Consumer",
        "  schedule:\n    - cron: '07 */6 * * *'",
        "  workflow_dispatch:", "  pull_request:",
        "  push:\n    branches: [main]",
        "permissions:\n  contents: read",
        "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
        "  group: janus-self-writer-real-consumer-${{ github.ref }}",
        "    runs-on: ubuntu-24.04",
        "    timeout-minutes: 12",
        "      - uses: actions/setup-python@v5",
        "          python-version: '3.12'",
        "      - name: Negative controls for genuine model-authored source and observation",
        "python -m unittest discover -s _code/tests -p test_real_operational_self_writer_consumer.py -v",
        "docker pull " + IMAGE,
        "test \"$(git -C _code rev-parse HEAD)\" = \"$GITHUB_SHA\"",
        "test \"$(git -C _state rev-parse HEAD)\" = " + STATE,
        "PYTHONPATH=_code/modules/autonomy_coder",
        "python _code/modules/autonomy_coder/real_operational_consumer.py",
        "--state _state", "--latest _code/data/autonomy_loop/LATEST.json",
        "--out runtime/real-operational-consumer/RECEIPT.json",
        "assert r['executed_in_networkless_oracle'] is True",
        "assert r['authority_delta']==0 and r['source_writeback'] is False",
        "assert r['installed_into_trusted_runtime'] is False",
        "      - uses: actions/upload-artifact@v4",
    )
    if any(x not in text for x in critical):
        raise ValueError("MISSING_RUNTIME_SAFETY_CONTRACT")
    if text.count("      - uses: actions/checkout@v4") != 2:
        raise ValueError("CHECKOUT_COUNT_CHANGED")
    if text.count("          persist-credentials: false") != 2:
        raise ValueError("CREDENTIALS_ESCALATION")
    if text.count("          sparse-checkout-cone-mode: false") != 2:
        raise ValueError("SPARSE_DISABLED")
    for path, paths in (("_code", CODE_PATHS), ("_state", STATE_PATHS)):
        expected = "".join("            " + line + "\n" for line in paths)
        if path == "_code":
            prefix = "          path: _code\n          persist-credentials: false\n          sparse-checkout: |\n"
        else:
            prefix = "          ref: " + STATE + "\n          path: _state\n          persist-credentials: false\n          sparse-checkout: |\n"
        if prefix + expected + "          sparse-checkout-cone-mode: false" not in text:
            raise ValueError("SPARSE_MISSING_REQUIRED_PATH")
    if ("pull_request_target:" in text or "workflow_run:" in text or
            "  contents: write" in text or "secrets." in text):
        raise ValueError("NEW_PRIVILEGE_OR_DANGEROUS_EVENT")
    if text.count("      - uses: actions/checkout@v4") != 2:
        raise ValueError("CHECKOUT_UNEXPECTED")


class ActionsCostR15Tests(unittest.TestCase):
    def test_baseline_contract_preserved(self):
        check(FLOW.read_text())

    def test_missing_provenance_tree_denied(self):
        src = FLOW.read_text()
        for name in CODE_PATHS + STATE_PATHS:
            modified = src.replace("            " + name + "\n", "", 1)
            with self.subTest(name=name), self.assertRaises(ValueError):
                check(modified)

    def test_source_and_permissions_tampering_denied(self):
        src = FLOW.read_text()
        edits = (
            ("  cancel-in-progress: ${{ github.event_name == 'pull_request' }}", "  cancel-in-progress: true"),
            ("persist-credentials: false", "persist-credentials: true"),
            ("  schedule:", "  removed_schedule:"),
            ("docker pull " + IMAGE, "docker pull python:latest"),
            ("  contents: read", "  contents: write"),
            ("ref: " + STATE, "ref: main"),
        )
        for old, new in edits:
            with self.subTest(old=old), self.assertRaises(ValueError):
                check(src.replace(old, new, 1))


if __name__ == "__main__":
    unittest.main()
