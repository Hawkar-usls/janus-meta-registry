#!/usr/bin/env python3
import json
from pathlib import Path

p=Path('data/JANUS-WEDJAT-DUAL-ANATOMICAL-ANNOTATION-PILOT-2026-08-15-v0.11.json')
r=json.loads(p.read_text(encoding='utf-8'))
assert r['status']=='DUAL_ALGORITHMIC_ANATOMICAL_PROXY_PILOT_COMPLETED_HUMAN_INDEPENDENT_ANNOTATOR_GATE_OPEN'
assert r['synthesis']['replicated']=='UPPER_EYE_EYEBROW_LAYER_EYE_FAMILY_AFFINITY'
assert r['synthesis']['human_gate']=='OPEN'
u=r['component_results']['EYEBROW_UPPER_EYE']
assert u['median_A_B_mask_iou'] > 0.60
assert u['annotator_A_eye_family_aggregate_ranks']['D007'] <= 15
assert u['annotator_B_eye_family_aggregate_ranks']['D008A'] <= 10
assert u['annotator_B_eye_family_aggregate_ranks']['D008'] <= 15
pupil=r['component_results']['PUPIL']
assert pupil['annotator_B_D012_aggregate_rank'] <= 10
assert pupil['annotator_A_D012_aggregate_rank'] > 100
assert pupil['median_A_B_mask_iou'] < 0.01
assert 'TWO_ALGORITHMS_ARE_NOT_TWO_INDEPENDENT_HUMAN_ANNOTATORS' in r['claim_firewall']
assert 'NO_FRACTION_BINARY_ASCII_PYTHON_OR_HIDDEN_MESSAGE_PROMOTION' in r['claim_firewall']

q=Path('data/JANUS-WEDJAT-BLIND-HUMAN-ANATOMICAL-ANNOTATION-PROTOCOL-2026-08-15-v0.12.json')
p=json.loads(q.read_text(encoding='utf-8'))
assert p['status']=='PREREGISTERED_TWO_HUMAN_ANNOTATOR_GATE_NOT_YET_EXECUTED'
assert p['blind_packet']['minimum_annotators']==2
assert p['promotion_rules']['ANCIENT_TEXT_OR_HIDDEN_MESSAGE']=='FORBIDDEN_FROM_THIS_PROTOCOL'
assert p['promotion_rules']['HISTORICAL_FRACTION_MAPPING']=='NOT_ESTABLISHED_BY_THIS_PROTOCOL'
print('PASS: v0.11 frozen pilot and v0.12 human-annotation claim firewall')
