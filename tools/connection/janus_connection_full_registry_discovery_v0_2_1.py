#!/usr/bin/env python3
"""Versioned launcher for full-registry discovery v0.2.1.

The operator-similarity shadowing fix now lives in the v0.2 base engine. This
launcher applies only explicit v0.2.1 version and artifact identifiers in
memory, then executes the inherited engine. No scoring or corpus-selection
rule is changed.
"""
from pathlib import Path
import os, sys, tempfile

base=Path(__file__).with_name('janus_connection_full_registry_discovery_v0_2.py')
src=base.read_text(encoding='utf-8')
replacements={
    '"engine_version":VERSION':'"engine_version":"0.2.1"',
    'janus.connection.full_registry_discovery.v0_2':'janus.connection.full_registry_discovery.v0_2_1',
    'JANUS-CONNECTION-FULL-REGISTRY-DISCOVERY-2026-08-14-V0.2':'JANUS-CONNECTION-FULL-REGISTRY-DISCOVERY-2026-08-14-V0.2.1',
    'PASS_FULL_CORPUS_V0_2':'PASS_FULL_CORPUS_V0_2_1'
}
for old,new in replacements.items():
    count=src.count(old)
    if count!=1:
        raise SystemExit(f'PATCH_PRECONDITION_FAILED {old!r} count={count}')
    src=src.replace(old,new,1)
fd,tmp=tempfile.mkstemp(prefix='janus_connection_v021_',suffix='.py')
os.close(fd)
Path(tmp).write_text(src,encoding='utf-8')
os.execv(sys.executable,[sys.executable,tmp,*sys.argv[1:]])
