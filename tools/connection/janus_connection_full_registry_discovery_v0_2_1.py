#!/usr/bin/env python3
"""Fail-closed hotfix launcher for full-registry discovery v0.2.

The v0.2 CI run failed after computation because the local variable name `os`
(operator similarity) shadowed the imported `os` module before snapshot binding.
This launcher preserves v0.2 as historical failed code, applies an explicit,
auditable source patch in memory, and executes the corrected engine as v0.2.1.
No scoring rule or corpus-selection rule is changed.
"""
from pathlib import Path
import os, sys, tempfile

base=Path(__file__).with_name('janus_connection_full_registry_discovery_v0_2.py')
src=base.read_text(encoding='utf-8')
replacements={
    'a,b=ds[i],ds[j]; os=cos(ov[i],on[i],ov[j],on[j]);':'a,b=ds[i],ds[j]; op_sim=cos(ov[i],on[i],ov[j],on[j]);',
    'if os<.045:continue':'if op_sim<.045:continue',
    'contrast=max(0,os-cs); hidden=max(0,1-min(1,cs/.58)); rarity=min(1,rw/24)':'contrast=max(0,op_sim-cs); hidden=max(0,1-min(1,cs/.58)); rarity=min(1,rw/24)',
    'base=.47*os+.19*contrast+.12*hidden+.12*rarity+.10*substantive_struct':'base=.47*op_sim+.19*contrast+.12*hidden+.12*rarity+.10*substantive_struct',
    '"operator_similarity":round(os,8)':'"operator_similarity":round(op_sim,8)',
    '"operator_minus_content":round(os-cs,8)':'"operator_minus_content":round(op_sim-cs,8)',
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
