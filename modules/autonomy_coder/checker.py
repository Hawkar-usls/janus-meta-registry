"""Independent behavioral oracle. This file executes only in a networkless container."""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import random
import sys
sys.path.insert(0, str(Path(__file__).parent))
from policy import TASKS, validate_source

def cases(task, seed):
    r = random.Random(seed)
    if task == "retry_delay":
        return [((a, c), min(c, 2 ** a)) for a in range(13) for c in (1, 2, 3, 7, 30, 255, 900)] + [((a := r.randrange(13), c := r.randrange(1, 901)), min(c, 2 ** a)) for _ in range(200)]
    if task == "clamp":
        rows = []
        for _ in range(300):
            low, high = sorted([r.randrange(-10000, 10001), r.randrange(-10000, 10001)])
            value = r.randrange(-10000, 10001)
            rows.append(((value, low, high), min(high, max(low, value))))
        return rows
    if task in ("stable_unique", "all_equal"):
        rows = []
        for _ in range(300):
            values = [r.choice(["", "a", "b", "a/b", "0"]) if task == "stable_unique" else r.randrange(-2, 3) for _ in range(r.randrange(65))]
            expected = list(dict.fromkeys(values)) if task == "stable_unique" else len(set(values)) <= 1
            rows.append(((values,), expected))
        rows += [(([],), [] if task == "stable_unique" else True)]
        return rows
    if task == "pending_count":
        return [((p := r.randrange(100001), c := r.randrange(100001)), max(0, p - c)) for _ in range(300)]
    if task == "is_fresh":
        return [((a, m), 0 <= a <= m) for m in (0, 1, 100, 10000) for a in (-1, 0, 1, m, m + 1)] + [((a := r.randrange(-10000, 10001), m := r.randrange(10001)), 0 <= a <= m) for _ in range(250)]
    if task == "chunk_count":
        return [((n, size), (n + size - 1) // size) for n in (0, 1, 2, 999, 1000, 100000) for size in (1, 2, 3, 1000)] + [((n := r.randrange(100001), size := r.randrange(1, 1001)), (n + size - 1) // size) for _ in range(250)]
    if task == "bounded_batch":
        return [((n := r.randrange(-100, 10001), limit := r.randrange(1001)), max(0, min(n, limit))) for _ in range(300)]
    if task == "safe_ratio":
        return [((n, d), n / d if d else 0.0) for n in (-1000, -1, 0, 1, 1000) for d in (-1000, -1, 0, 1, 1000)] + [((n := r.randrange(-1000, 1001), d := r.randrange(-1000, 1001)), n / d if d else 0.0) for _ in range(250)]
    if task == "common_prefix":
        rows = []
        for _ in range(300):
            left = "".join(r.choice("abc/") for _ in range(r.randrange(65)))
            right = left[:r.randrange(len(left) + 1)] + "".join(r.choice("abc/") for _ in range(r.randrange(65)))
            right = right[:64]
            i = 0
            while i < min(len(left), len(right)) and left[i] == right[i]:
                i += 1
            rows.append(((left, right), left[:i]))
        return rows
    raise ValueError("UNKNOWN_ORACLE")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=TASKS, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--call")
    args = parser.parse_args()
    code = validate_source(args.source.read_text(), args.task)
    namespace = {}
    exec(compile(code, "generated_extension.py", "exec"), namespace)
    fn = namespace[args.task]
    count = 0
    for inputs, expected in cases(args.task, args.seed):
        actual_inputs = copy.deepcopy(inputs)
        result = fn(*actual_inputs)
        if actual_inputs != inputs or result != expected or (type(expected) in (bool, int, list, str) and type(result) is not type(expected)):
            raise ValueError("BEHAVIOR_OR_MUTATION_MISMATCH")
        count += 1
    result = {"status": "PASS_PURE_FUNCTION_ONLY", "cases": count}
    if args.call:
        result["value"] = fn(*json.loads(args.call))
    print(json.dumps(result, allow_nan=False))

if __name__ == "__main__":
    main()
