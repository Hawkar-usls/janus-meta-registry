from __future__ import annotations
import argparse, copy, hashlib, json, pathlib
from datetime import datetime, timezone, timedelta
TZ=timezone(timedelta(hours=3))
def load(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def digest(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--spec',required=True);ap.add_argument('--candidate-out',required=True);ap.add_argument('--canonical-out',required=True);ap.add_argument('--audit-out',required=True);a=ap.parse_args()
    s=load(a.spec);parent=load(s['parent_state']);ev=load(s['new_evidence']);req=s['required']
    selected=[x.get('train_selected_formula_candidates') for x in ev.get('per_fold',[])]
    pre={
      'parent_v2_24':parent.get('version')=='v2.24' and parent.get('status')=='CURRENT_CANONICAL_RESEARCH_STATE',
      'status_exact':ev.get('status')==s['required_status'],
      'family_zero':ev.get('cross_fitted_candidate_family_size')==req['cross_fitted_candidate_family_size'],
      'admitted_zero':ev.get('admitted_formula_slot_candidate_count')==req['admitted_formula_slot_candidate_count'],
      'five_folds':len(selected)==5,
      'all_fold_selected_zero':len(selected)==5 and all(x==req['all_folds_train_selected_formula_candidates'] for x in selected),
      'no_probable_function':ev['epistemic_gate'].get('probable_function_established') is req['probable_function_established'],
      'translation_false':ev['epistemic_gate'].get('translation_established') is False,
      'phonetic_false':ev['epistemic_gate'].get('phonetic_value_established') is False,
      'anchor_false':ev['epistemic_gate'].get('new_anchor_established') is False,
      'decipherment_false':ev['epistemic_gate'].get('decipherment_established') is req['decipherment_established'],
      'r3b_false':ev['epistemic_gate'].get('R3B_external_replication_established') is False,
      'no_manual_change':ev['leakage_firewall'].get('manual_candidate_addition_or_removal') is False,
    }
    if not all(pre.values()): raise SystemExit(json.dumps(pre,sort_keys=True))
    st=copy.deepcopy(parent);now=datetime.now(TZ).isoformat();st.update({'artifact_uuid':'JANUS-LINEAR-A-RESEARCH-STATE-2026-08-15-v2.25','timestamp':now,'version':'v2.25','title':'JANUS Linear A canonical state after exact all-certain formula-slot negative','status':'CURRENT_CANONICAL_RESEARCH_STATE'})
    st['canonicality']={'current_source_of_truth':True,'parent_state':s['parent_state'],'promotion_spec':a.spec,'promotion_prerequisites_pass':True,'history_is_not_deleted':True,'candidate_path':a.candidate_out,'canonicality_audit':a.audit_out,'canonicality_audit_status':'PENDING_UNTIL_AUDIT_EMITTED','promotion_rule_satisfied':True}
    st['R7_formula_role_lane']={'R7_0':{'path':s['new_evidence'],'status':ev['status'],'evidence_sha256':digest(s['new_evidence']),'cross_fitted_candidate_family_size':0,'admitted_formula_slot_candidate_count':0,'interpretation':'Exact all-certain two-sided formula frames were too sparse to produce a train-selected candidate under the frozen gate; this is not evidence that formulaic structure is absent.'},'status':'R7_0_EXACT_TWO_SIDED_NEGATIVE_R7_A_ANCHORED_ABSTRACTION_READY'}
    road=[x for x in st.get('roadmap',[]) if x.get('id') not in {'R7_0_FORMULA_SLOT_COMPLETION','R7_A_ANCHORED_FORMULA_FAMILY'}];road.append({'id':'R7_0_FORMULA_SLOT_COMPLETION','status':'DONE_STRICT_NEGATIVE_ZERO_TRAIN_CANDIDATES'});road.append({'id':'R7_A_ANCHORED_FORMULA_FAMILY','status':'READY_NOT_EXECUTED'});st['roadmap']=road
    st['next_atomic_requirements']=[{'id':'R7_A_ANCHORED_FORMULA_FAMILY','action':s['next_atomic_requirement']}]+[x for x in st.get('next_atomic_requirements',[]) if x.get('id') not in {'R7_0_FORMULA_SLOT_COMPLETION','R7_A_ANCHORED_FORMULA_FAMILY'}]
    st['global_claim_ceiling_v2_25']={'sign_level_context_structure_learned_cross_validated':True,'cross_region_internal_context_structure_transfer_established':True,'exact_two_sided_formula_slot_candidate_established':False,'probable_function_established':False,'word_meaning_established':False,'translation_established':False,'phonetic_value_established':False,'new_anchor_established':False,'decipherment_established':False,'strict_R3B_replication_established':False,'allowed':s['claim_ceiling']['allowed'],'forbidden':s['claim_ceiling']['forbidden']}
    pathlib.Path(a.candidate_out).write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    checks={**pre,'version_v2_25':st['version']=='v2.25','exact_formula_false':st['global_claim_ceiling_v2_25']['exact_two_sided_formula_slot_candidate_established'] is False,'probable_function_false':st['global_claim_ceiling_v2_25']['probable_function_established'] is False,'decipherment_false2':st['global_claim_ceiling_v2_25']['decipherment_established'] is False};passed=all(checks.values());audit={'artifact_uuid':'JANUS-LINEAR-A-RESEARCH-STATE-CANONICALITY-AUDIT-2026-08-15-v2.25','version':'v2.25','status':'CANONICALITY_AUDIT_PASS' if passed else 'CANONICALITY_AUDIT_FAIL','executed_at':now,'promotion_spec':a.spec,'parent_state':s['parent_state'],'new_evidence':s['new_evidence'],'parent_sha256':digest(s['parent_state']),'evidence_sha256':digest(s['new_evidence']),'candidate_sha256':digest(a.candidate_out),'checks':checks,'all_checks_pass':passed,'claim_ceiling':s['claim_ceiling']};pathlib.Path(a.audit_out).write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not passed:return 2
    st['canonicality']['canonicality_audit_status']='CANONICALITY_AUDIT_PASS';pathlib.Path(a.canonical_out).write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':'CANONICAL_V2_25_READY','R7_0_exact_formula_candidate':False,'decipherment_established':False},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
