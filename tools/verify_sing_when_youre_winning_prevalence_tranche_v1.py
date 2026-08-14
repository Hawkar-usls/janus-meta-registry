#!/usr/bin/env python3
import json
from collections import Counter
from pathlib import Path

P = Path('data/JANUS-SING-WHEN-YOURE-WINNING-SPORTS-MVP-PREVALENCE-TRANCHE-01-v1.0.json')
d = json.loads(P.read_text(encoding='utf-8'))
errors = []
controls = d['controls']
ids = [x['id'] for x in controls]
if len(ids) != len(set(ids)):
    errors.append('duplicate control ids')

resolved = [x for x in controls if x['chain_outcome_receipt'] is not None]
pending = [x for x in controls if x['chain_outcome_receipt'] is None]
full = [x for x in resolved if x['chain_outcome_receipt'] is True]
first_break = Counter(x['first_break_physical_outcome'] for x in resolved)
exact5 = [x for x in resolved if x.get('visible_same_subject_instances') == 5]
exact5_full = [x for x in exact5 if x['chain_outcome_receipt'] is True]

for x in resolved:
    derived = bool(x['source_physical_subject'] and x['one_world'] and x['receipt_outcome_bearing'])
    if derived != x['chain_outcome_receipt']:
        errors.append(f"{x['id']}: chain mismatch")
    expected = 'NONE' if derived else ('SOURCE' if not x['source_physical_subject'] else ('WORLD' if not x['one_world'] else 'RECEIPT'))
    if x['first_break_physical_outcome'] != expected:
        errors.append(f"{x['id']}: first-break mismatch expected {expected}")

c = d['derived_counts']
checks = {
    'records': len(controls),
    'resolved_records': len(resolved),
    'pending_source_count': len(pending),
    'full_chain_resolved': len(full),
    'world_break_resolved': first_break['WORLD'],
    'source_break_resolved': first_break['SOURCE'],
    'receipt_break_resolved': first_break['RECEIPT'],
    'exactly_five_visible_resolved': len(exact5),
    'exactly_five_full_chain_resolved': len(exact5_full),
}
for k, v in checks.items():
    if c.get(k) != v:
        errors.append(f'derived_counts.{k}: stored={c.get(k)!r} derived={v!r}')

# Anti-rescue / falsification preservation.
lebron = next(x for x in controls if x['id'] == 'MP-001')
if not (lebron['visible_same_subject_instances'] == 5 and lebron['chain_outcome_receipt'] is True):
    errors.append('LeBron exact-five full-chain counterexample must be preserved')
if d['diagnostic_result']['existence_uniqueness_of_full_chain'] != 'FALSIFIED':
    errors.append('full-chain existence uniqueness must remain falsified')
if d['diagnostic_result']['existence_uniqueness_of_exactly_five'] != 'FALSIFIED':
    errors.append('exact-five uniqueness must remain falsified')
if d['epistemic_ceiling']['population_prevalence_claim'] is not False:
    errors.append('population prevalence claim ceiling must remain false')

out = {
    'artifact_id': d['artifact_id'],
    'records': len(controls),
    'resolved': len(resolved),
    'pending': len(pending),
    'full_chain': len(full),
    'first_break': dict(sorted(first_break.items())),
    'exactly_five': len(exact5),
    'exactly_five_full_chain': len(exact5_full),
    'errors': errors,
    'ok': not errors,
}
print(json.dumps(out, indent=2, sort_keys=True))
raise SystemExit(0 if not errors else 1)
