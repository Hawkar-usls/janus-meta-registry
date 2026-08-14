#!/usr/bin/env python3
"""Reconcile independent annotations.js source-lineage transports and size metric."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

EXPECTED_STATUS = "HASH_LINEAGE_ADMITTED_BYTE_COUNT_CLASSIFIED_AS_PUBLISHED_METADATA_CONFLICT"
EXPECTED_BLOB = "db2661cc680f90120cb8a60d4e5b8a3e0c3e0092"
EXPECTED_SHA = "7ce1f87a98827d059a732cc00506c635b4d5f65b2d0e2f1592fc2b67827758cd"
EXPECTED_BYTES = 2239932
EXPECTED_PATH_COMMITS = 59
EXPECTED_UNIQUE_BLOBS = 59
EXPECTED_LATEST_COMMIT = "6d5a7ba8fc3338bf161dc11ad98d663a6795f9f0"
PUBLISHED_NUMERIC_SIZE = 2201442


def g(obj: dict[str, Any], *path: str) -> Any:
    cur: Any = obj
    for key in path:
        cur = cur[key]
    return cur


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--git-history',required=True)
    ap.add_argument('--api-history',required=True)
    ap.add_argument('--size-metric',required=True)
    ap.add_argument('--output',required=True)
    args=ap.parse_args()

    git=json.load(open(args.git_history,encoding='utf-8'))
    api=json.load(open(args.api_history,encoding='utf-8'))
    size=json.load(open(args.size_metric,encoding='utf-8'))

    checks={
      'git_status':git.get('status')==EXPECTED_STATUS,
      'api_status':api.get('status')==EXPECTED_STATUS,
      'historical_blob_equal':g(git,'historical_commit_observation','git_blob_sha')==g(api,'historical_commit_observation','git_blob_sha')==EXPECTED_BLOB,
      'historical_sha_equal':g(git,'historical_commit_observation','sha256')==g(api,'historical_commit_observation','sha256')==EXPECTED_SHA,
      'historical_bytes_equal':g(git,'historical_commit_observation','bytes')==g(api,'historical_commit_observation','decoded_bytes')==EXPECTED_BYTES,
      'path_commit_count_equal':g(git,'path_history','path_change_commit_count')==g(api,'path_history','path_change_commit_count')==EXPECTED_PATH_COMMITS,
      'unique_blob_count_equal':g(git,'path_history','unique_blob_count')==g(api,'path_history','unique_blob_count')==EXPECTED_UNIQUE_BLOBS,
      'latest_commit_equal':g(git,'path_history','latest_path_change','commit')==g(api,'path_history','latest_path_change','commit')==EXPECTED_LATEST_COMMIT,
      'latest_blob_equal':g(git,'path_history','latest_path_change','git_blob_sha')==g(api,'path_history','latest_path_change','git_blob_sha')==EXPECTED_BLOB,
      'latest_blob_same_as_historical_git':g(git,'path_history','latest_path_blob_same_as_historical_commit') is True,
      'latest_blob_same_as_historical_api':g(api,'path_history','latest_path_blob_same_as_historical') is True,
      'no_both_match_git':len(g(git,'path_history','revisions_matching_both_published_fields'))==0,
      'no_both_match_api':len(g(api,'path_history','revisions_matching_both_published_fields'))==0,
      'api_history_complete':g(api,'path_history','complete_under_frozen_pagination_rule') is True,
      'size_status':size.get('status')=='MATCHES_FULL_UNICODE_CHARACTER_COUNT',
      'raw_bytes_not_published_numeric':g(size,'measurements','raw_utf8_bytes')!=PUBLISHED_NUMERIC_SIZE,
      'full_unicode_codepoints_equal_published':g(size,'measurements','full_unicode_codepoints')==PUBLISHED_NUMERIC_SIZE,
      'unique_predeclared_size_match':size.get('matching_measurements')==['full_unicode_codepoints'],
      'author_implementation_not_inferred':g(size,'interpretation','author_measurement_implementation_inferred') is False,
    }
    lineage_keys=[k for k in checks if k not in {'size_status','raw_bytes_not_published_numeric','full_unicode_codepoints_equal_published','unique_predeclared_size_match','author_implementation_not_inferred'}]
    lineage_ok=all(checks[k] for k in lineage_keys)
    size_ok=all(checks[k] for k in ['size_status','raw_bytes_not_published_numeric','full_unicode_codepoints_equal_published','unique_predeclared_size_match','author_implementation_not_inferred'])
    if lineage_ok and size_ok:
        status='MULTI_TRANSPORT_RECONCILED_CHARACTER_COUNT_EXPLANATION_EXACT'
    elif not lineage_ok:
        status='TRANSPORT_DISAGREEMENT'
    else:
        status='SIZE_METRIC_UNRESOLVED'

    result={
      'artifact_uuid':'JANUS-LINEAR-A-R3C-1E-ANNOTATION-MULTI-TRANSPORT-RECONCILIATION-RESULT-2026-08-14-v0.1',
      'version':'v0.1','node_type':'multi_verifier_reconciliation_result','status':status,
      'frozen_spec':'data/JANUS-LINEAR-A-R3C-1E-ANNOTATION-MULTI-TRANSPORT-RECONCILIATION-SPEC-2026-08-14-v0.1.json',
      'inputs':{
        'git_history':args.git_history,
        'api_history':args.api_history,
        'size_metric':args.size_metric,
      },
      'checks':checks,
      'lineage_reconciliation_pass':lineage_ok,
      'size_metric_reconciliation_pass':size_ok,
      'reconciled_source_observation':{
        'git_blob_sha':EXPECTED_BLOB,
        'raw_utf8_bytes':EXPECTED_BYTES,
        'sha256':EXPECTED_SHA,
        'path_change_commit_count':EXPECTED_PATH_COMMITS,
        'unique_blob_count':EXPECTED_UNIQUE_BLOBS,
        'latest_path_change_commit':EXPECTED_LATEST_COMMIT,
        'published_numeric_size':PUBLISHED_NUMERIC_SIZE,
        'published_numeric_size_exact_measurement':'full_unicode_codepoints',
      },
      'epistemic_interpretation':{
        'repository_lineage_reproduced_by_two_transports':lineage_ok,
        'published_numeric_size_exactly_explained_by_decoded_character_count':size_ok,
        'published_label_Bytes_equals_raw_UTF8_bytes':False,
        'author_measurement_implementation_inferred':False,
        'intentional_mislabel_claimed':False,
        'byte_exact_Briakos_annotation_source_claimed':False,
        'reason_byte_exact_not_claimed':'The thesis exposes only a 32-bit SHA-256 prefix and a numeric field labelled Bytes that does not equal raw UTF-8 bytes, even though repository lineage and the exact character-count match strongly identify the historical candidate.',
      },
      'claim_ceiling':{
        'metadata_and_repository_lineage_only':True,
        'Briakos_419_scope_inference':False,
        'R3B_effect':'NONE','new_anchor':False,'decipherment':False,
      },
    }
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':status,'lineage_ok':lineage_ok,'size_ok':size_ok,'failed_checks':[k for k,v in checks.items() if not v]},sort_keys=True))

if __name__=='__main__': main()
