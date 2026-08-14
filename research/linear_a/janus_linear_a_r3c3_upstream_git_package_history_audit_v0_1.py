#!/usr/bin/env python3
from __future__ import annotations
import argparse,collections,json,re,subprocess
from pathlib import Path
from typing import Any
SPEC='data/JANUS-LINEAR-A-R3C-3-UPSTREAM-GIT-PACKAGE-HISTORY-AUDIT-SPEC-2026-08-14-v0.1.json'

def git(repo:Path,*args:str)->str:
    return subprocess.check_output(['git','-C',str(repo),*args],text=True,encoding='utf-8',errors='strict')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('repo'); ap.add_argument('--out',required=True); a=ap.parse_args()
    s=json.load(open(SPEC,encoding='utf-8')); assert s['status']=='FROZEN_BEFORE_EXECUTION'
    repo=Path(a.repo)
    commits=[x for x in git(repo,'rev-list','--all','--topo-order','--reverse').splitlines() if x]
    rows=[]; tree_ids=[]; zip_occ=[]; direct=[]
    pat=re.compile(s['scope']['direct_filename_probe_regex'])
    for idx,c in enumerate(commits):
        meta=git(repo,'show','-s','--format=%ct%x00%P',c).strip().split('\x00')
        ts=int(meta[0]); parents=meta[1].split() if len(meta)>1 and meta[1] else []
        tree=git(repo,'rev-parse',f'{c}^{{tree}}').strip(); tree_ids.append(tree)
        entries=git(repo,'ls-tree','-r','-l','--full-tree',c).splitlines()
        zcount=0; dcount=0
        for line in entries:
            left,path=line.split('\t',1); parts=left.split();
            if len(parts)<4: continue
            mode,typ,sha,size=parts[:4]
            if typ!='blob': continue
            nbytes=None if size=='-' else int(size)
            if path.lower().endswith('.zip'):
                zcount+=1; zip_occ.append({'commit_index':idx,'commit':c,'timestamp_unix':ts,'path':path,'git_blob_sha1':sha,'declared_bytes':nbytes})
            elif pat.search(path):
                dcount+=1; direct.append({'commit_index':idx,'commit':c,'timestamp_unix':ts,'path':path,'git_blob_sha1':sha,'declared_bytes':nbytes})
        rows.append({'commit_index':idx,'commit':c,'timestamp_unix':ts,'parents':parents,'tree_sha1':tree,'zip_path_occurrences':zcount,'direct_uralic_named_nonarchive_paths':dcount})
    grouped=collections.defaultdict(list)
    for z in zip_occ: grouped[z['git_blob_sha1']].append(z)
    uniq=[]
    for sha,occ in sorted(grouped.items(),key=lambda kv:min(x['commit_index'] for x in kv[1])):
        paths=sorted({x['path'] for x in occ}); sizes=sorted({x['declared_bytes'] for x in occ})
        uniq.append({'git_blob_sha1':sha,'declared_bytes_values':sizes,'paths':paths,'occurrence_count':len(occ),'first_commit_index':min(x['commit_index'] for x in occ),'last_commit_index':max(x['commit_index'] for x in occ),'first_commit':min(occ,key=lambda x:x['commit_index'])['commit'],'last_commit':max(occ,key=lambda x:x['commit_index'])['commit']})
    result={'artifact_uuid':'JANUS-LINEAR-A-R3C-3-UPSTREAM-GIT-PACKAGE-HISTORY-AUDIT-RESULT-2026-08-14-v0.1','version':'v0.1','node_type':'public_git_history_package_metadata_audit_result','status':'UPSTREAM_GIT_PACKAGE_HISTORY_ENUMERATED','frozen_spec':SPEC,'repository':s['upstream_repository'],'summary':{'reachable_commit_count':len(commits),'unique_tree_count':len(set(tree_ids)),'zip_path_occurrence_count':len(zip_occ),'unique_zip_blob_count':len(uniq),'direct_uralic_named_nonarchive_path_occurrence_count':len(direct),'unique_direct_uralic_named_nonarchive_paths':len({x['path'] for x in direct})},'commits':rows,'unique_zip_blobs':uniq,'direct_uralic_named_nonarchive_paths':direct,'readiness_effect':{'public_package_blob_universe_enumerated':True,'unique_archive_blobs_available_for_followup_member_name_audit':len(uniq),'archive_internal_Uralic_presence_established':False,'paper_exact_2024_input_identity_admitted':False},'claim_ceiling':{'public_git_package_lineage_enumerated':True,'direct_git_tree_Uralic_name_presence_established':True,'archive_internal_Uralic_presence_established':False,'paper_exact_2024_input_identity_established':False,'published_2024_matches_reproduced':False,'language_family_relationship_established':False,'R3B_effect':'NONE','new_anchor':False,'decipherment':False}}
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],**result['summary'],'zip_blobs':[(x['git_blob_sha1'],x['declared_bytes_values'],x['paths']) for x in uniq],'direct_uralic_paths':sorted({x['path'] for x in direct})},ensure_ascii=False,sort_keys=True))
if __name__=='__main__': main()
