from __future__ import annotations

import pathlib
import runpy
import sys


def main() -> None:
    here = pathlib.Path(__file__).resolve()
    repo_root = here.parents[2]
    target = here.with_name("janus_linear_a_r3b0_notti_2018_sign_id_conformance_corrective_v0_1_1.py")
    sys.path.insert(0, str(repo_root))
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
