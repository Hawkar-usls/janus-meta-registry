#!/usr/bin/env python3
import json
from pathlib import Path

P = Path('registry/connections/CURRENT.json')
d = json.loads(P.read_text(encoding='utf-8'))

# Preserve historical/current structures and mutate only the authority fields advanced by Panel B.
d['authority_rule'] = (
    "Use JANUS-CONNECTION-v2.0 for interpretation, dependency collapse, scoring and promotion semantics. "
    "Preserve all historical scans/results as immutable discovery history. Connection-family artifacts are always accounted "
    "in the corpus manifest but have zero independent-support weight for discovering or validating Connection patterns. "
    "ALL_JSON claims are snapshot-scoped. A valid negative held-out or external panel must be retained and may not be replaced "
    "post hoc with a more favorable panel. Fixture-level external structural recurrence is not repository-external transport "
    "when a frozen actual-execution/audit-result requirement is unmet. Internal held-out transport does not imply organizational "
    "independence, repository-external transport, external replication, causal law, human-blindness measurement or scientific novelty."
)

ed = d['exhaustive_discovery']['latest_completed_parent_snapshot']
ed.update({
    'snapshot_commit': '3d9bb311d1b475d09b4ada1446bed865cbeb6076',
    'workflow_run_id': 31805684208,
    'job_id': 94783915248,
    'artifact_id': 9221055606,
    'artifact_zip_sha256': '5a9a6908df06213d53096ee49b65f11ec742dadca89a7853c232d8d385d2e996',
    'json_seen': 953,
    'parsed_structurally': 939,
    'raw_fallback_only': 14,
    'pair_candidates': 18533,
    'operator_motifs': 5955,
    'higher_order_motif_pairs': 302,
    'boolean_tensions': 17,
    'exhaustive_accounting': 'PASS_953_OF_953',
})

# Panel A is intentionally untouched.
d['external_panel_B'] = {
    'purpose': 'Repository-external result-record transport attempt for HIDDEN-001/002/003/006, disjoint from Panel A and frozen before selected JSON body inspection.',
    'relation_to_panel_A': 'DISJOINT_SUCCESSOR_EXPERIMENT; PANEL_A_IMMUTABLE_VALID_NEGATIVE',
    'selection': 'data/JANUS-CONNECTION-EXTERNAL-PANEL-B-RESULT-RECORDS-SELECTION-2026-08-14-v0.1.json',
    'selection_commit': '069d93e6311c89de222ef3583b67d0e7a1ea52ad',
    'selector': 'tools/connection/janus_connection_external_panel_b_selector_v0_1.py',
    'selector_commit': 'f5400a37d48dc4512767cbf98c0358950b919c45',
    'selector_workflow': '.github/workflows/connection-external-panel-b-selector.yml',
    'selector_workflow_commit': '335420417bfe275ecb86cb61ae9025cbeb9e2968',
    'selector_run_id': 31805010695,
    'selector_job_id': 94781721209,
    'selector_artifact_id': 9220784882,
    'selector_artifact_zip_sha256': 'e44e6e36ac215cbac4454c29023f401fd3feff02d82139aba69dfba06f801483',
    'selection_method': 'git fetch --filter=blob:none --no-checkout plus git ls-tree -r; deterministic SHA256 path ranking; no selected JSON body reads during selection',
    'repositories_frozen': 8,
    'independent_governance_namespaces': 8,
    'repositories_with_selected_json': 7,
    'repositories_retained_with_zero_eligible_json': 1,
    'eligible_json_total': 654,
    'selected_json_total': 21,
    'selected_blob_verification': 'PASS_21_OF_21',
    'panel_replacement_after_inspection': False,
    'rubric_changed_after_inspection': False,
    'rubric': 'data/JANUS-CONNECTION-EXTERNAL-PANEL-B-RUBRIC-2026-08-14-v0.1.json',
    'rubric_commit': '65414345c55eb26b3b92ec8f28ed487b6b670943',
    'result': 'data/JANUS-CONNECTION-EXTERNAL-PANEL-B-RESULT-2026-08-14-v0.1.json',
    'result_commit': 'ce200f131278d602139597ed45245b906eb40ebf',
    'result_status': 'EXECUTED_MIXED_EXTERNAL_RECURRENCE_NO_EXTERNAL_TRANSPORT_PROMOTION',
    'semantic_classification_mode': 'RUBRIC_BOUND_MODEL_ASSISTED_MANUAL_CLASSIFICATION; NOT_INDEPENDENT_HUMAN_BLIND_RATING',
    'record_class_counts': {
        'ACTUAL_EXECUTION_AUDIT_RESULT': 0,
        'EXPECTED_GOLDEN_FIXTURE': 16,
        'STRUCTURAL_OR_PARSER_FIXTURE': 5,
        'OTHER_MACHINE_READABLE_RECORD': 0,
    },
    'selector_quality_findings': [
        'Frozen substring token expected also matched path segment unexpected; retained as a post-freeze selector-class-purity finding, not repaired.',
        'Frozen substring token scan also matched ordinary directory scanners; retained as a post-freeze selector-class-purity finding, not repaired.'
    ],
    'HIDDEN-001': {
        'strong_repositories': 0, 'weak_repositories': 1, 'contradiction_repositories': 0,
        'not_applicable_repositories': 7, 'actual_output_supporting_repositories': 0,
        'outcome': 'EXTERNAL_PANEL_B_NOT_TRANSPORTED', 'repository_external_transport': False,
    },
    'HIDDEN-002': {
        'strong_repositories': 4, 'weak_repositories': 1, 'contradiction_repositories': 0,
        'not_applicable_repositories': 3, 'actual_output_supporting_repositories': 0,
        'outcome': 'EXTERNAL_RECURRENCE_OBSERVED_NOT_TRANSPORT_PROMOTED',
        'threshold_failure': 'Frozen minimum of two supporting ACTUAL_EXECUTION_AUDIT_RESULT repositories was not met.',
        'repository_external_transport': False,
    },
    'HIDDEN-003': {
        'strong_repositories': 0, 'weak_repositories': 0, 'contradiction_repositories': 0,
        'not_applicable_repositories': 8, 'actual_output_supporting_repositories': 0,
        'outcome': 'EXTERNAL_PANEL_B_NOT_TRANSPORTED', 'repository_external_transport': False,
    },
    'HIDDEN-006': {
        'strong_repositories': 0, 'weak_repositories': 1, 'contradiction_repositories': 0,
        'not_applicable_repositories': 7, 'actual_output_supporting_repositories': 0,
        'outcome': 'EXTERNAL_PANEL_B_NOT_TRANSPORTED', 'repository_external_transport': False,
    },
    'patterns_promoted_to_external_transport': [],
    'destructive_rewire_authorized': False,
    'destructive_rewire_executed': False,
    'destructive_rewire_reason': 'No pattern passed the complete predeclared Panel B transport threshold; rewire cannot rescue a threshold failure.',
    'verifier': 'tools/connection/janus_connection_external_panel_b_verifier_v0_1.py',
    'verifier_commit': 'f10bd0b6fdbb7d0328c47fe8c1d770725bf9833d',
    'verifier_workflow': '.github/workflows/connection-external-panel-b-verifier.yml',
    'verifier_workflow_commit': '067e1bffe8ba36de7fbc3061f3ddeaccf1fe1271',
    'verifier_run_id': 31805624443,
    'verifier_job_id': 94783718898,
    'verifier_artifact_id': 9221025849,
    'verifier_artifact_zip_sha256': 'cb7a257e2e791c981acdc5fd3186468d4975d545c91dd26e74d8f07cbe0a82c7',
    'verification_receipt': 'data/JANUS-CONNECTION-EXTERNAL-PANEL-B-VERIFICATION-RECEIPT-2026-08-14-v0.1.json',
    'verification_receipt_commit': '3d9bb311d1b475d09b4ada1446bed865cbeb6076',
    'mechanical_verification': 'PASS_EXTERNAL_PANEL_B_MECHANICAL_VERIFICATION',
}

reg = d['hidden_pattern_register']
reg['HIDDEN-001_NON_TRANSITIVE_EVIDENCE_BINDING_LADDER'].update({
    'repository_external_transport': False,
    'external_panel_B': 'EXTERNAL_PANEL_B_NOT_TRANSPORTED_WEAK_ONE_REPOSITORY',
})
reg['HIDDEN-002_AMBIGUITY_IS_A_FIRST_CLASS_STATE'].update({
    'repository_external_transport': False,
    'external_panel_B': 'EXTERNAL_RECURRENCE_OBSERVED_NOT_TRANSPORT_PROMOTED',
    'external_structural_recurrence_panel_B': True,
    'external_panel_B_support': {'strong_repositories':4,'weak_repositories':1,'contradiction_repositories':0,'actual_output_supporting_repositories':0},
})
reg['HIDDEN-003_FIRST_BREAK_LOCALIZATION_GENERALIZATION'].update({
    'repository_external_transport': False,
    'external_panel_B': 'EXTERNAL_PANEL_B_NOT_TRANSPORTED_ALL_EIGHT_NOT_APPLICABLE',
})
reg['HIDDEN-006_NEGATIVE_CLAIM_REQUIRES_CLOSED_SEARCH_UNIVERSE'].update({
    'external_transport': False,
    'external_panel_B': 'EXTERNAL_PANEL_B_NOT_TRANSPORTED_WEAK_ONE_REPOSITORY',
})

cc = d['current_claim_ceiling']
cc.update({
    'latest_all_json_snapshot': 'PASS_953_OF_953_AT_3d9bb311d1b475d09b4ada1446bed865cbeb6076',
    'external_panel_B_executed': True,
    'external_panel_B_result': 'MIXED_EXTERNAL_RECURRENCE_NO_TRANSPORT_PROMOTION',
    'external_structural_recurrence_hidden_002_panel_B': True,
    'repository_external_transport_hidden_001': False,
    'repository_external_transport_hidden_002': False,
    'repository_external_transport_hidden_003': False,
    'repository_external_transport_hidden_006': False,
    'repository_external_transport_any_hidden': False,
    'external_replication': 'NOT_CONFIRMED',
    'family_wide_connection_promotion': 'BLOCKED',
})

ps = d['promotion_scope']
ps.update({
    'HIDDEN-001': 'HELDOUT_TRANSPORT_STRONG_INTERNAL_REWIRE_SURVIVAL_EXTERNAL_PANELS_A_AND_B_NOT_TRANSPORTED',
    'HIDDEN-002': 'HELDOUT_TRANSPORT_STRONG_INTERNAL_REWIRE_SURVIVAL_PLUS_EXTERNAL_STRUCTURAL_RECURRENCE_PANEL_B_NOT_TRANSPORT_PROMOTED',
    'HIDDEN-003': 'HELDOUT_TRANSPORT_STRONG_INTERNAL_REWIRE_SURVIVAL_EXTERNAL_PANELS_A_AND_B_NOT_TRANSPORTED',
    'HIDDEN-006': 'HELDOUT_REFINEMENT_STRONG_INTERNAL_COVERAGE_RELATION_CALIBRATED_EXTERNAL_PANEL_B_NOT_TRANSPORTED',
    'family_wide_promotion': 'BLOCKED',
})

d['next_required_gate'] = {
    'name': 'EXTERNAL_PANEL_C_ACTUAL_RUN_ARTIFACTS',
    'reason': 'Panel B is immutable and established strong fixture-level external recurrence for HIDDEN-002, but the frozen actual-execution/audit-result requirement was 0/2. The next experiment must target actual externally produced run/audit artifacts by explicit API provenance rather than path substrings; it is not a replacement or repair of Panel B.',
    'requirements': [
        'preserve Panel A valid negative and Panel B mixed result unchanged',
        'freeze independent external repositories/workflows/runs and exact artifact identities before downloading result bodies',
        'select actual CI/run/audit result artifacts through explicit API provenance rather than filename substring discovery',
        'use path-segment or token-boundary matching only if paths are needed, with the rule frozen before inspection',
        'do not reuse Panel B records to satisfy Panel C independent-repository threshold counts',
        'freeze HIDDEN-001/002/003/006 classification semantics and transport thresholds before artifact-body inspection',
        'retain failed, empty, skipped, partial and NOT_APPLICABLE run records',
        'dependency-collapse multiple artifacts from the same governance repository/workflow family',
        'execute destructive rewiring only after a pattern independently reaches its frozen actual-run support threshold',
        'preserve exact run IDs, commit SHAs, job IDs, artifact IDs/digests and any unavailable/expired artifact states'
    ],
    'promotion_boundary': 'Only successful transport through frozen externally produced actual run/audit artifacts may advance a tested pattern to REPOSITORY_EXTERNAL_TRANSPORT. External replication still requires independent analysis/verifier implementation; population prevalence, causal law and scientific novelty remain separate gates.'
}

P.write_text(json.dumps(d, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(json.dumps({
    'status': 'PASS_CURRENT_PANEL_B_SURGICAL_SYNC',
    'panel_b_promoted': d['external_panel_B']['patterns_promoted_to_external_transport'],
    'h2_external_recurrence': d['external_panel_B']['HIDDEN-002']['outcome'],
    'next_gate': d['next_required_gate']['name'],
    'latest_snapshot': d['current_claim_ceiling']['latest_all_json_snapshot'],
}, sort_keys=True))
