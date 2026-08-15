#!/usr/bin/env python3
"""JANUS Record Drift full-surface runner v0.2.1.

Hotfix for v0.2 journal creation lookup: never use git --follow for unique
append-only journal paths. Git rename similarity can otherwise trace a newly
created journal file into a similar older journal and produce a false R9.
Historical v0.2 output is intentionally retained unchanged.
"""
from pathlib import Path
import full_surface_runner as core


def exact_path_creation_commit(path):
    x = core.git(
        "log",
        "--diff-filter=A",
        "--format=%H",
        "-n",
        "1",
        "--",
        path,
        check=False,
    )
    return x or None


# Replace only the faulty resolver. All v0.2 instrumentation remains frozen.
core.creation_commit = exact_path_creation_commit
core.RUNNER = Path(__file__).resolve()

if __name__ == "__main__":
    core.main()
