from __future__ import annotations
import argparse, copy, hashlib, json, pathlib
from datetime import datetime, timezone, timedelta
TZ=timezone(timedelta(hours=3))
def load(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def digest(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--spec',required=True);ap.add_argument('--candidate-out',required=True);ap.add_argument('--canonical-out',required=True);ap.add_argument('--audit-out',required=True);a=ap.parse_args()
    s=load(a.spec);parent=load(s['parent_state']);ev=load(s['new_evidence']);req=s['required'];adm=ev.get('admitted_candidates',[])
    k=[x for x in adm if x.get('source_word')==req['source_word'] and x.get('source_role')==req['source_role']]
    pre={
      'parent_v2_29':parent.get('version')=='v2.29' and parent.get('status')=='CURRENT_CANONICAL_RESEARCH_STATE',
      'status_exact':ev.get('status')==s['required_status'],
      'admitted_one':ev.get('admitted_candidate_count')==req['admitted_candidate_count'] and len(adm)==1,
      'ku_ro_one':len(k)==1,
      'function_exact':len(k)==1 and k[0].get('probable_structural_function_label')==req['probable_structural_function_label'],
      'region_exact':len(k)==1 and k[0].get('scope_region')==req['scope_region'],
      'scope_exact':len(k)==1 and k[0].get('scope')==req['scope'],
      'c0_rate_exact':len(k)==1 and k[0].get('C0_heldout_match_rate')==req['C0_heldout_match_rate'],
      'c0_q_exact':len(k)==1 and k[0].get('C0_BH_q')==req['C0_BH_q'],
      'c2_null_exact':len(k)==1 and k[0].get('C2_null_mean_match_rate')==req['C2_null_mean_match_rate'],
      'c2_q_exact':len(k)==1 and k[0].get('C2_BH_q')==req['C2_BH_q'],
      'd0_n_exact':len(k)==1 and k[0].get('D0_occurrences')==req['D0_occurrences'],
      'd0_hits_exact':len(k)==1 and k[0].get('D0_matches')==req['D0_matches'],
      'd0_objects_exact':len(k)==1 and k[0].get('D0_physical_objects')==req['D0_physical_objects'],
      'd0_null_exact':len(k)==1 and k[0].get('D0_null_mean_match_rate')==req['D0_null_mean_match_rate'],
      'd0_q_exact':len(k)==1 and k[0].get('D0_BH_q')==req['D0_BH_q'],
      'c1_universal_false':len(k)==1 and k[0].get('C1_universal_cross_region_survival') is req['C1_universal_cross_region_survival'],
      'cross_region_false':len(k)==1 and k[0].get('cross_region_generalization_established') is req['cross_region_generalization_established'],
      'meaning_false':len(k)==1 and k[0].get('exact_word_meaning_established') is req['exact_word_meaning_established'],
      'translation_false':len(k)==1 and k[0].get('translation_established') is req['translation_established'],
      'probable_region_true':ev['epistemic_gate'].get('probable_region_scoped_structural_function_established') is True,
      'universal_false':ev['epistemic_gate'].get('universal_cross_region_function_established') is False,
      'phonetic_false':ev['epistemic_gate'].get('phonetic_value_established') is False,
      'language_false':ev['epistemic_gate'].get('language_family_established') is False,
      'anchor_false':ev['epistemic_gate'].get('new_anchor_established') is False,
      'decipherment_false':ev['epistemic_gate'].get('decipherment_established') is False,
      'r3b_false':ev['epistemic_gate'].get('R3B_external_replication_established') is False,
      'family_unchanged':ev.get('candidate_family_changed') is False,
    }
    if not all(pre.values()): raise SystemExit(json.dumps(pre,sort_keys=True))
    x=k[0];st=copy.deepcopy(parent);now=datetime.now(TZ).isoformat();st.update({'artifact_uuid':'JANUS-LINEAR-A-RESEARCH-STATE-2026-08-15-v2.30','timestamp':now,'version':'v2.30','title':'JANUS Linear A canonical state after first region-scoped probable structural-function admission','status':'CURRENT_CANONICAL_RESEARCH_STATE'})
    st['canonicality']={'current_source_of_truth':True,'parent_state':s['parent_state'],'promotion_spec':a.spec,'promotion_prerequisites_pass':True,'history_is_not_deleted':True,'candidate_path':a.candidate_out,'canonicality_audit':a.audit_out,'canonicality_audit_status':'PENDING_UNTIL_AUDIT_EMITTED','promotion_rule_satisfied':True}
    lane=st.setdefault('R7_formula_role_lane',{});lane['R7_C3']={'path':s['new_evidence'],'status':ev['status'],'evidence_sha256':digest(s['new_evidence']),'admitted_candidate_count':1,'admitted':{'source_word':'KU-RO','source_role':'ROW_FIRST_LEXICAL','probable_structural_function_label':'ROW-OPENING-LIKE','scope_region':'HT','scope':'DOMINANT_REGION_ONLY','C0_heldout_match_rate':x['C0_heldout_match_rate'],'C0_BH_q':x['C0_BH_q'],'C2_null_mean_match_rate':x['C2_null_mean_match_rate'],'C2_BH_q':x['C2_BH_q'],'D0_occurrences':x['D0_occurrences'],'D0_matches':x['D0_matches'],'D0_match_rate':x['D0_match_rate'],'D0_documents':x['D0_documents'],'D0_physical_objects':x['D0_physical_objects'],'D0_null_mean_match_rate':x['D0_null_mean_match_rate'],'D0_BH_q':x['D0_BH_q'],'D0_status_strata':x['D0_status_strata'],'C1_universal_cross_region_survival':False,'cross_region_generalization_established':False,'exact_word_meaning_established':False,'translation_established':False,'claim':x['claim']}};lane['status']='FIRST_REGION_SCOPED_PROBABLE_STRUCTURAL_FUNCTION_ADMITTED_KU_RO_HT_ROW_OPENING_LIKE'
    road=[r for r in st.get('roadmap',[]) if r.get('id') not in {'R7_D0_REGION_SCOPED_OBJECT_STATUS_VALIDATION','R7_C3_PROBABLE_FUNCTION_ADMISSION','R7_C3_UNIVERSAL','R7_EXTERNAL_FROZEN_FUNCTION_VALIDATION'}];road.extend([{'id':'R7_D0_REGION_SCOPED_OBJECT_STATUS_VALIDATION','status':'DONE_ONE_SURVIVOR_KU_RO'},{'id':'R7_C3_PROBABLE_FUNCTION_ADMISSION','status':'DONE_ADMITTED_KU_RO_HT_ROW_OPENING_LIKE'},{'id':'R7_C3_UNIVERSAL','status':'BLOCKED_C1_CROSS_REGION_NOT_ESTABLISHED'},{'id':'R7_EXTERNAL_FROZEN_FUNCTION_VALIDATION','status':'READY_WHEN_LAWFUL_INDEPENDENT_BYTES_ARRIVE'}]);st['roadmap']=road
    st['next_atomic_requirements']=[{'id':'R7_EXTERNAL_FROZEN_FUNCTION_VALIDATION','action':s['next_atomic_requirements'][1]},{'id':'R7_OTHER_FUNCTIONAL_ROLES','action':s['next_atomic_requirements'][2]}]+[r for r in st.get('next_atomic_requirements',[]) if r.get('id') not in {'R7_D0_REGION_SCOPED_OBJECT_STATUS_VALIDATION','R7_EXTERNAL_FROZEN_FUNCTION_VALIDATION','R7_OTHER_FUNCTIONAL_ROLES'}]
    st['R7_first_probable_structural_function']={'established':True,'scope':'REGION_SCOPED','region':'HT','source_word':'KU-RO','source_role':'ROW_FIRST_LEXICAL','probable_structural_function_label':'ROW-OPENING-LIKE','evidence_path':s['new_evidence'],'frozen_hypothesis_for_future_external_test':True,'cross_region_generalization_established':False,'exact_word_meaning_established':False,'translation_established':False}
    st['global_claim_ceiling_v2_30']={'probable_region_scoped_structural_function_established':True,'admitted_source_word':'KU-RO','admitted_structural_function':'ROW-OPENING-LIKE','admitted_scope_region':'HT','universal_cross_region_function_established':False,'exact_word_meaning_established':False,'translation_established':False,'phonetic_value_established':False,'language_family_established':False,'new_anchor_established':False,'decipherment_established':False,'strict_R3B_replication_established':False,'allowed':s['claim_ceiling']['allowed'],'forbidden':s['claim_ceiling']['forbidden']}
    pathlib.Path(a.candidate_out).write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    checks={**pre,'version_v2_30':st['version']=='v2.30','probable_true':st['global_claim_ceiling_v2_30']['probable_region_scoped_structural_function_established'] is True,'word_exact':st['global_claim_ceiling_v2_30']['admitted_source_word']=='KU-RO','function_exact2':st['global_claim_ceiling_v2_30']['admitted_structural_function']=='ROW-OPENING-LIKE','region_exact2':st['global_claim_ceiling_v2_30']['admitted_scope_region']=='HT','universal_false2':st['global_claim_ceiling_v2_30']['universal_cross_region_function_established'] is False,'meaning_false2':st['global_claim_ceiling_v2_30']['exact_word_meaning_established'] is False,'translation_false2':st['global_claim_ceiling_v2_30']['translation_established'] is False,'decipherment_false2':st['global_claim_ceiling_v2_30']['decipherment_established'] is False};passed=all(checks.values())
    audit={'artifact_uuid':'JANUS-LINEAR-A-RESEARCH-STATE-CANONICALITY-AUDIT-2026-08-15-v2.30','version':'v2.30','status':'CANONICALITY_AUDIT_PASS' if passed else 'CANONICALITY_AUDIT_FAIL','executed_at':now,'promotion_spec':a.spec,'parent_state':s['parent_state'],'new_evidence':s['new_evidence'],'parent_sha256':digest(s['parent_state']),'evidence_sha256':digest(s['new_evidence']),'candidate_sha256':digest(a.candidate_out),'checks':checks,'all_checks_pass':passed,'claim_ceiling':s['claim_ceiling']};pathlib.Path(a.audit_out).write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not passed:return 2
    st['canonicality']['canonicality_audit_status']='CANONICALITY_AUDIT_PASS';pathlib.Path(a.canonical_out).write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':'CANONICAL_V2_30_READY','source_word':'KU-RO','function':'ROW-OPENING-LIKE','scope':'HT','universal':False,'decipherment':False},ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
