#!/usr/bin/env python3
import argparse, hashlib, json, pathlib, re

EXCLUDE_EXACT = {
    'registry/myth_busted/FALLOUT-3-VAULT112A-PUBLIC-DERIVED-POD-ROLE-ANCHOR-HARDENING-v2.4.json',
    'data/JANUS-LINEAR-A-SIGLA-DOCUMENT-IDENTITY-BRIDGE-RESULT-2026-08-14-v0.1.json',
    'registry/myth_busted/MATHERSHIP-BIRTHDAY-EXACT-ASSET-LINEAGE-FORENSICS-v3.2.json',
    'registry/experimental/JANUS-GENESIS-INFINITE-FACES-POST-COMPROMISE-TEMPORAL-ROOT-RECOVERY-v3.5.json',
}
SEARCH_KEY_FRAGMENTS = ('search','scan','enumerat','query','lookup','candidate','match','detect','inspect','audit')
BOUNDARY_KEY_FRAGMENTS = ('coverage','complete','scope','authoritative','source','gate','claim','result','status','evidence','unresolved','unknown','absence','negative','failure')


def key_paths(obj, prefix=''):
    out=[]
    if isinstance(obj, dict):
        for k,v in obj.items():
            p=f'{prefix}.{k}' if prefix else str(k)
            out.append(p.lower())
            out.extend(key_paths(v,p))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(key_paths(v,prefix+'[]'))
    return out


def family_stem(path):
    s=path.lower()
    s=re.sub(r'v\d+(?:[._-]\d+)*','v#',s)
    s=re.sub(r'20\d{2}[-_]?\d{2}[-_]?\d{2}','date',s)
    s=re.sub(r'\d+','#',s)
    s=re.sub(r'[-_]+','-',s)
    return s


def role(path):
    p=path.lower()
    if '/connections/' in p or 'janus-connection' in p: return 'CONNECTION'
    if p.endswith('.sha256.json') or 'sha256' in pathlib.Path(p).name: return 'INTEGRITY'
    if 'semantic' in pathlib.Path(p).name: return 'SEMANTIC_COMPANION'
    return 'PRIMARY'


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo-root',default='.')
    ap.add_argument('--out',required=True)
    ap.add_argument('--panel-size',type=int,default=16)
    args=ap.parse_args()
    root=pathlib.Path(args.repo_root)
    eligible=[]; seen=0; parsed=0
    for p in sorted(root.rglob('*.json')):
        rel=p.relative_to(root).as_posix()
        if '.git' in p.parts or rel.startswith('out/'):
            continue
        seen+=1
        if rel in EXCLUDE_EXACT or role(rel)!='PRIMARY':
            continue
        try:
            obj=json.loads(p.read_text(encoding='utf-8-sig'))
            parsed+=1
        except Exception:
            continue
        kp=key_paths(obj)
        sk=sorted({frag for frag in SEARCH_KEY_FRAGMENTS if any(frag in x for x in kp)})
        bk=sorted({frag for frag in BOUNDARY_KEY_FRAGMENTS if any(frag in x for x in kp)})
        if not sk or not bk:
            continue
        # Selection uses key names only. Values/titles/status text are never read here.
        stem=family_stem(rel)
        h=hashlib.sha256(('H006-HELDOUT-V0.1\0'+stem+'\0'+rel).encode()).hexdigest()
        eligible.append({'path':rel,'family_stem':stem,'sha256_raw':hashlib.sha256(p.read_bytes()).hexdigest(),
                         'search_key_classes':sk,'boundary_key_classes':bk,'selection_hash':h})
    eligible.sort(key=lambda x:x['selection_hash'])
    selected=[]; families=set()
    for x in eligible:
        if x['family_stem'] in families: continue
        selected.append(x); families.add(x['family_stem'])
        if len(selected)>=args.panel_size: break
    out={
      'schema':'janus.connection.hidden006_heldout_selection.v0.1',
      'artifact_uuid':'JANUS-CONNECTION-HIDDEN006-HELDOUT-SELECTION-2026-08-14-V0.1',
      'status':'FROZEN_STRUCTURE_ONLY_SELECTION',
      'selector_version':'0.1',
      'selector_semantics':{
        'reads_json_values':False,
        'reads_titles':False,
        'reads_status_values':False,
        'reads_key_names':True,
        'eligibility':'at least one generic search/enumeration key fragment AND one generic boundary/evidence/gate key fragment',
        'ordering':'SHA256(H006-HELDOUT-V0.1 || family_stem || path)',
        'one_record_per_family_stem':True,
        'formulation_sources_excluded':sorted(EXCLUDE_EXACT),
        'connection_family_excluded':True,
        'integrity_derivatives_excluded':True,
        'semantic_companions_excluded':True
      },
      'corpus':{'json_seen':seen,'json_parsed_for_keys':parsed,'eligible_key_topology_records':len(eligible)},
      'panel_size_requested':args.panel_size,
      'panel_size_selected':len(selected),
      'selected':selected,
      'claim_ceiling':{
        'body_outcomes_inspected_by_selector':False,
        'heldout_classification_executed':False,
        'hidden006_validated':False
      }
    }
    pathlib.Path(args.out).parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(args.out).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'PASS_H006_STRUCTURE_ONLY_SELECTION','seen':seen,'eligible':len(eligible),'selected':len(selected),'out':args.out}))

if __name__=='__main__': main()
