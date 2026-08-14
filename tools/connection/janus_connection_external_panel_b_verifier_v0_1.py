#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

ORDER = {"NOT_APPLICABLE":0, "WEAK":1, "STRONG":2, "CONTRADICTION":3}
PATTERNS = ["HIDDEN-001","HIDDEN-002","HIDDEN-003","HIDDEN-006"]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def collapse(values):
    return max(values, key=lambda x: ORDER[x]) if values else "NOT_APPLICABLE"


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--selection', required=True)
    ap.add_argument('--rubric', required=True)
    ap.add_argument('--result', required=True)
    args=ap.parse_args()
    s=load(args.selection); r=load(args.rubric); x=load(args.result)

    assert s['status']=='BODY_BLIND_EXTERNAL_PANEL_B_SELECTION_EXECUTED'
    assert r['status']=='FROZEN_BEFORE_SELECTED_BODY_INSPECTION'
    assert x['selected_records_expected']==x['selected_records_inspected']==21
    assert x['records_replaced_after_inspection']==0
    assert x['blob_sha_verification']=='PASS_21_OF_21'

    selected={}
    for repo in s['repositories']:
        for rec in repo['selected']:
            key=(repo['repository'], rec['path'])
            assert key not in selected
            selected[key]=rec['blob_sha']
    assert len(selected)==21

    observed={}
    repo_rows={}
    for repo in x['repositories']:
        repo_name=repo['repository']
        repo_rows[repo_name]=repo
        for rec in repo['records']:
            key=(repo_name, rec['path'])
            assert key not in observed
            observed[key]=rec['blob_sha']
            assert rec['record_class'] in r['record_classification']
            assert set(rec['classifications'])==set(PATTERNS)
            assert all(v in ORDER for v in rec['classifications'].values())
    assert observed==selected

    selected_repos={q['repository'] for q in s['repositories']}
    assert set(repo_rows)==selected_repos

    # Recompute repository collapse, with contradiction overriding support.
    for repo_name, repo in repo_rows.items():
        for p in PATTERNS:
            vals=[rec['classifications'][p] for rec in repo['records']]
            c=collapse(vals)
            assert repo['collapse'][p]==c, (repo_name,p,c,repo['collapse'][p])

    threshold=r['transport_threshold']['requirements']
    recomputed={}
    for p in PATTERNS:
        strong=weak=contra=na=0
        actual_support=0
        for repo_name, repo in repo_rows.items():
            c=repo['collapse'][p]
            strong += c=='STRONG'
            weak += c=='WEAK'
            contra += c=='CONTRADICTION'
            na += c=='NOT_APPLICABLE'
            if c in ('STRONG','WEAK'):
                if any(rec['record_class']=='ACTUAL_EXECUTION_AUDIT_RESULT' and rec['classifications'][p] in ('STRONG','WEAK') for rec in repo['records']):
                    actual_support += 1
        supporting=strong+weak
        passes=(
            strong >= threshold['strong_independent_repositories_min'] and
            supporting >= threshold['total_supporting_independent_repositories_min'] and
            supporting-strong >= threshold['additional_weak_or_strong_repository_min'] and
            contra <= threshold['contradiction_repositories_max'] and
            actual_support >= threshold['actual_execution_audit_result_supporting_repositories_min']
        )
        if passes:
            outcome='EXTERNAL_TRANSPORT_SUPPORTED_PANEL_B'
        elif strong >= 2:
            outcome='EXTERNAL_RECURRENCE_OBSERVED_NOT_TRANSPORT_PROMOTED'
        else:
            outcome='EXTERNAL_PANEL_B_NOT_TRANSPORTED'
        recomputed[p]={
            'strong_repositories':strong,
            'weak_repositories':weak,
            'contradiction_repositories':contra,
            'not_applicable_repositories':na,
            'actual_output_supporting_repositories':actual_support,
            'outcome':outcome,
        }
        declared=x['pattern_summary'][p]
        for k,v in recomputed[p].items():
            assert declared[k]==v, (p,k,v,declared[k])

    promoted=[p for p in PATTERNS if recomputed[p]['outcome']=='EXTERNAL_TRANSPORT_SUPPORTED_PANEL_B']
    assert promoted==x['transport_threshold_result']['patterns_promoted_to_EXTERNAL_TRANSPORT_SUPPORTED_PANEL_B']
    assert promoted==[]
    assert x['transport_threshold_result']['destructive_rewire_authorized'] is False
    assert x['transport_threshold_result']['destructive_rewire_executed'] is False
    assert x['claim_ceiling']['repository_external_transport_any_hidden'] is False
    assert x['claim_ceiling']['external_structural_recurrence_hidden_002'] is True
    assert x['claim_ceiling']['family_wide_connection_promotion'] is False

    print(json.dumps({
        'status':'PASS_EXTERNAL_PANEL_B_MECHANICAL_VERIFICATION',
        'selected_records':len(selected),
        'repositories':len(repo_rows),
        'recomputed':recomputed,
        'promoted':promoted,
    }, sort_keys=True))

if __name__=='__main__':
    main()
