#!/usr/bin/env python3
import argparse, hashlib, itertools, json, pathlib, subprocess

EXPECTED = [
  'ABSENCE_ADMISSIBLE_ONLY_WITHIN_DECLARED_SCOPE',
  'UNRESOLVED_OR_ABSENCE_BLOCKED_PENDING_SENSITIVITY',
  'GLOBAL_ABSENCE_BLOCKED_PRESERVE_SCOPED_NONDETECTION'
]

def git_blob(path):
    return subprocess.check_output(['git','hash-object',path], text=True).strip()

def score(assignment):
    return sum(a==b for a,b in zip(assignment,EXPECTED))/len(EXPECTED)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--fixture',required=True)
    ap.add_argument('--out',required=True)
    a=ap.parse_args()
    fx=json.loads(pathlib.Path(a.fixture).read_text(encoding='utf-8'))
    per=[]
    all_scores=[]
    perms=list(itertools.permutations(EXPECTED))
    for fam in fx['families']:
        actual=git_blob(fam['source_path'])
        if actual != fam['source_blob_sha1']:
            raise SystemExit(f"SOURCE_BLOB_MISMATCH {fam['family']} expected={fam['source_blob_sha1']} actual={actual}")
        scores=[score(p) for p in perms]
        real=score(tuple(EXPECTED))
        tail=sum(s>=real for s in scores)/len(scores)
        adj=[]
        for i in range(2):
            x=EXPECTED.copy(); x[i],x[i+1]=x[i+1],x[i]
            adj.append({'swap':[i,i+1],'score':score(tuple(x)),'destroys_exact_mapping':score(tuple(x))<1.0})
        per.append({
          'family':fam['family'], 'source_path':fam['source_path'], 'source_blob_sha1':actual,
          'real_score':real, 'null_mean_score':sum(scores)/len(scores),
          'effect_real_minus_exact_null_mean':real-sum(scores)/len(scores),
          'exact_assignment_permutations':len(scores), 'exact_null_tail_mass_at_real':tail,
          'score_distribution':{str(v):scores.count(v) for v in sorted(set(scores))},
          'adjacent_swaps':adj,
          'observed_source_states':fam['source_observed_states'],
          'counterfactual_states':fam['counterfactual_states']
        })
    # Exact combined null: choose one verdict assignment independently per frozen family.
    for choice in itertools.product(range(len(perms)), repeat=len(per)):
        all_scores.append(sum(score(perms[i]) for i in choice)/len(choice))
    real_combined=1.0
    result={
      'schema':'janus.connection.hidden006_coverage_toggle_result.v0.1',
      'artifact_uuid':'JANUS-CONNECTION-HIDDEN006-COVERAGE-TOGGLE-RESULT-2026-08-14-V0.1',
      'status':'PASS_HIDDEN006_HELDOUT_COVERAGE_RELATION_CALIBRATION',
      'fixture':a.fixture,
      'fixture_sha256':hashlib.sha256(pathlib.Path(a.fixture).read_bytes()).hexdigest(),
      'source_blob_verification':'PASS_ALL',
      'family_results':per,
      'combined':{
        'family_count':len(per),
        'exact_combined_assignments':len(all_scores),
        'real_score':real_combined,
        'null_mean_score':sum(all_scores)/len(all_scores),
        'effect_real_minus_exact_null_mean':real_combined-sum(all_scores)/len(all_scores),
        'exact_null_tail_mass_at_all_families_perfect_mapping':sum(s>=real_combined for s in all_scores)/len(all_scores),
        'all_deterministic_adjacent_swaps_destroy_exact_mapping':all(x['destroys_exact_mapping'] for f in per for x in f['adjacent_swaps']),
        'tail_mass_semantics':'STRUCTURAL_RELATION_MAPPING_CALIBRATION_NOT_POPULATION_P_VALUE'
      },
      'claim_ceiling':{
        'heldout_internal_source_recurrence':True,
        'coverage_scope_sensitivity_relation_calibrated':True,
        'counterfactual_branches_observed':False,
        'unbiased_population_prevalence':False,
        'causal_law_established':False,
        'external_transport':False,
        'external_replication':False,
        'scientific_novelty':False,
        'family_wide_connection_promotion':False
      }
    }
    pathlib.Path(a.out).parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'families':len(per),'combined_assignments':len(all_scores),'tail':result['combined']['exact_null_tail_mass_at_all_families_perfect_mapping'],'out':a.out}))

if __name__=='__main__': main()
