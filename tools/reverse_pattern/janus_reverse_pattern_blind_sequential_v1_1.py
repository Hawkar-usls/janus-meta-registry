#!/usr/bin/env python3
"""Lexical hardening patch for JANUS blind sequential reverse-pattern audit.

v1.0 is preserved as the exact first-attempt implementation. v1.1 changes only
MIRROR_OR_SYMMETRY lexical admission: generic `two` / `ways` are removed because
the first CI receipt audit showed they can manufacture mirror evidence without
an explicit mirror/symmetry/bidirectional relation. All queue, status, repeat,
mirror/back-forth, negative-preservation and claim-ceiling rules remain unchanged.
"""
from __future__ import annotations

import sys

import janus_reverse_pattern_blind_sequential_v1_0 as base

base.VERSION = "1.1"
base.FAMILY_TERMS["MIRROR_OR_SYMMETRY"] = {
    "mirror",
    "mirrored",
    "symmetry",
    "symmetric",
    "bidirectional",
    "bidir",
    "twoway",
    "twoways",
}


def lexical_regression_test() -> None:
    """Prove generic cardinality/path wording cannot open the mirror gate."""
    base.self_test()
    two_only = base.phase1_features(
        {
            "operator": "EXACT_REVERSE_FORWARD",
            "counting_mode": "TWO_PATHS",
            "path_policy": "TWO_WAYS_AVAILABLE",
            "rollback": "EXACT_RETURN",
            "gate_status": "PASS",
            "identity_anchor": "SOURCE_PARENT",
        }
    )
    assert two_only["paired_reverse_forward"] is True
    assert two_only["mirror_gate"] is False, "generic TWO/WAYS reopened MIRROR gate"

    explicit = base.phase1_features(
        {
            "operator": "EXACT_BIDIRECTIONAL_REVERSE_FORWARD_MIRROR",
            "proof": "EXACT_WITNESS_VERIFIED",
            "identity_anchor": "SOURCE_PARENT",
            "gate_status": "PASS",
            "recovery": "RETURN_REPLAY",
        }
    )
    assert explicit["mirror_gate"] is True, "explicit mirror evidence stopped working"


if __name__ == "__main__":
    lexical_regression_test()
    base.main()
