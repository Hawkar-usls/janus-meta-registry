"""Closed-source AST lowerer regression tests for model-intended real repair."""
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules/autonomy_coder"))
from typed_repair_lowerer import unwrap_exact_model_intent, OUTPUT_SOURCE, COMPILER_ID


class TypedModelRepairTests(unittest.TestCase):
    def test_both_actual_stronger_model_proposals_match_exact_typed_floor(self):
        actual_0 = ("import math\n\ndef floor_age_us(delta_us):\n"
                    "    return math.floor(delta_us / 1_000_000)\n")
        actual_1 = ("import math\n\ndef floor_age_us(delta_us):\n"
                    "    return math.floor(delta_us / 1e6)\n")
        for source in (actual_0, actual_1):
            with self.subTest(source=source):
                result = unwrap_exact_model_intent(source)
                self.assertEqual(result, OUTPUT_SOURCE)
                scope = {}
                # Tests execute only the fixed trusted compiler output, NEVER
                # the original model source containing an import.
                exec(compile(result, "<compiler-output>", "exec"),
                     {"__builtins__": {}}, scope)
                func = scope["floor_age_us"]
                for delta in (-10**16-1, -2000001, -1500000, -500000,
                              -1, 0, 1, 500000, 999999, 1000000,
                              1500000, 10**16+1):
                    self.assertEqual(func(delta), delta // 1000000)
        self.assertEqual(COMPILER_ID,
                         "janus.self_writer.typed_math_floor_to_integer_floor.v1")

    def test_lowerer_refuses_all_other_python_surface(self):
        valid = ("import math\ndef floor_age_us(delta_us):\n"
                 "    return math.floor(delta_us / 1000000)\n")
        attacks = [
            valid.replace("import math", "import os"),
            valid.replace("import math", "import math as m"),
            valid.replace("import math", "import math, os"),
            valid.replace("1000000", "1000"),
            valid.replace("1000000", "1000001"),
            valid.replace("math.floor", "math.ceil"),
            valid.replace("delta_us", "seconds"),
            valid + "\nprint('unexpected output')\n",
            valid.replace("    return", "    print('extra')\n    return"),
            valid.replace(" / ", " // "),
            valid.replace(" / ", " * "),
            valid.replace("return math.floor", "return eval"),
            valid.replace("def floor_age_us", "@property\ndef floor_age_us"),
            valid.replace("math.floor", "math.floor.__call__"),
            "def floor_age_us(delta_us):\n    return delta_us // 1000000\n",
        ]
        for attack in attacks:
            with self.subTest(attack=attack[:90]):
                with self.assertRaises((ValueError, SyntaxError)):
                    unwrap_exact_model_intent(attack)

    def test_compiled_sha_and_no_unsafe_source_evaluation(self):
        self.assertEqual(
            hashlib.sha256(OUTPUT_SOURCE.encode()).hexdigest(),
            hashlib.sha256(b"def floor_age_us(delta_us):\n"
                           b"    return delta_us // 1000000\n").hexdigest())
        source = Path(__file__).resolve().parents[1] / "modules/autonomy_coder/typed_repair_lowerer.py"
        script = source.read_text()
        self.assertIn("raw_model_source_admitted", script)
        self.assertIn('"main_write": False', script)
        self.assertIn('"auto_merge": False', script)
        self.assertIn("ORIGINAL_BUNDLE_SHA256", script)
        self.assertIn("ORIGINAL_VERDICT_SHA256", script)


if __name__ == "__main__":
    unittest.main()
