from __future__ import annotations
import argparse, copy, hashlib, json
from pathlib import Path
from datetime import datetime, timezone, timedelta
TZ=timezone(timedelta(hours=3))
def load(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--spec',required=True); ap.add_argument('--candidate-out',required=True); ap.add_argument('--canonical-out',required=True); ap.add_argument('--audit-out',required=True); a=ap.parse_args()
    s=load(a.spec); parent=load(s['parent_state']); c05=load(s['new_evidence']['R7_C0_5_corrective']); f1=load(s['new_evidence']['R7_F1_terminal_numeric_slot']); req=s['required']
    pf=parent.get('R7_first_probable_structural_function',{}); pg=parent.get('global_claim_ceiling_v2_30',{})
    ku=[x for x in c05.get('survivors',[]) if x.get('source_word_after_scoring')=='KU-RO' and x.get('role')==req['C0_5_KU_RO_role']]
    checks={
      'parent_v2_30':parent.get('version')=='v2.30' and parent.get('status')=='CURRENT_CANONICAL_RESEARCH_STATE',
      'parent_audit_pass':parent.get('canonicality',{}).get('canonicality_audit_status')=='CANONICALITY_AUDIT_PASS',
      'parent_probable_true':pg.get('probable_region_scoped_structural_function_established') is True,
      'parent_word':pf.get('source_word')==req['parent_probable_source_word'],
      'parent_function':pf.get('probable_structural_function_label')==req['parent_probable_function'],
      'parent_region':pf.get('region')==req['parent_scope_region'],
      'c05_status':c05.get('status')==req['C0_5_status'],
      'c05_family':c05.get('candidate_count')==req['C0_5_candidate_count'],
      'c05_survivors':c05.get('survivor_count')==req['C0_5_survivor_count'],
      'c05_ku_one':len(ku)==1,
      'c05_ku_n':len(ku)==1 and ku[0].get('corrected_eligible_occurrences')==req['C0_5_KU_RO_corrected_occurrences'],
      'c05_ku_hits':len(ku)==1 and ku[0].get('corrected_role_hits')==req['C0_5_KU_RO_corrected_hits'],
      'c05_ku_precision':len(ku)==1 and ku[0].get('corrected_role_precision')==req['C0_5_KU_RO_corrected_precision'],
      'c05_ku_q':len(ku)==1 and ku[0].get('BH_q')==req['C0_5_KU_RO_BH_q'],
      'c05_no_independent':c05.get('credit',{}).get('independent_confirmation_credit') is req['C0_5_independent_confirmation_credit'],
      'f1_status':f1.get('status')==req['F1_status'],
      'f1_signature':f1.get('candidate',{}).get('signature')==req['F1_signature'],
      'f1_events':f1.get('support',{}).get('target_events')==req['F1_target_events'],
      'f1_objects':f1.get('support',{}).get('target_physical_objects')==req['F1_target_physical_objects'],
      'f1_exchangeable_objects':f1.get('support',{}).get('exchangeable_target_objects')==req['F1_exchangeable_target_objects'],
      'f1_prevalence':f1.get('candidate',{}).get('target_prevalence_all_target_events')==req['F1_target_prevalence'],
      'f1_effect':f1.get('candidate',{}).get('object_weighted_effect')==req['F1_object_weighted_effect'],
      'f1_positive':f1.get('candidate',{}).get('positive_object_fraction')==req['F1_positive_object_fraction'],
      'f1_loo':f1.get('candidate',{}).get('leave_one_object_out_positive_fraction')==req['F1_LOO_positive_fraction'],
      'f1_fwer':f1.get('structure_destroying_null',{}).get('familywise_empirical_p')==req['F1_familywise_empirical_p'],
      'f1_label':f1.get('admission',{}).get('admitted_refinement_label')==req['F1_refinement_label'],
      'f1_admitted':f1.get('admission',{}).get('internal_post_F0_terminal_numeric_slot_refinement_established') is True,
      'f1_no_independent':f1.get('epistemic_gate',{}).get('independent_replication_established') is req['F1_independent_replication_established'],
      'f1_no_total':f1.get('epistemic_gate',{}).get('TOTAL_or_SUMMARY_semantic_function_established') is req['F1_TOTAL_or_SUMMARY_semantic_function_established'],
      'meaning_false':f1.get('epistemic_gate',{}).get('exact_word_meaning_established') is False,
      'translation_false':f1.get('epistemic_gate',{}).get('translation_established') is False,
      'decipherment_false':f1.get('epistemic_gate',{}).get('decipherment_established') is False,
    }
    if not all(checks.values()): raise SystemExit(json.dumps(checks,sort_keys=True))
    now=datetime.now(TZ).isoformat(); st=copy.deepcopy(parent)
    st.update({'artifact_uuid':'JANUS-LINEAR-A-RESEARCH-STATE-2026-08-16-v2.31','timestamp':now,'version':'v2.31','title':'JANUS Linear A canonical state after KU-RO nonsingleton corrective survival and terminal-numeric-slot internal refinement','status':'CURRENT_CANONICAL_RESEARCH_STATE'})
    st['canonicality']={'current_source_of_truth':True,'parent_state':s['parent_state'],'promotion_spec':a.spec,'promotion_prerequisites_pass':True,'history_is_not_deleted':True,'candidate_path':a.candidate_out,'canonicality_audit':a.audit_out,'canonicality_audit_status':'PENDING_UNTIL_AUDIT_EMITTED','promotion_rule_satisfied':True}
    st['R7_C0_5_boundary_confound_corrective']={'path':s['new_evidence']['R7_C0_5_corrective'],'evidence_sha256':digest(s['new_evidence']['R7_C0_5_corrective']),'status':c05['status'],'candidate_count':43,'survivor_count':2,'singleton_document_fraction':c05['confound_inventory']['singleton_document_fraction'],'singleton_row_fraction':c05['confound_inventory']['singleton_row_fraction'],'KU_RO':{'role':'ROW_HEADER','corrected_occurrences':ku[0]['corrected_eligible_occurrences'],'corrected_hits':ku[0]['corrected_role_hits'],'corrected_precision':ku[0]['corrected_role_precision'],'corrected_background':ku[0]['corrected_role_background_probability'],'BH_q':ku[0]['BH_q'],'regions':ku[0]['corrected_region_set'],'survives':True},'credit':'POSTHOC_CORRECTIVE_NO_INDEPENDENT_CONFIRMATION'}
    st['R7_F1_terminal_numeric_slot']={'path':s['new_evidence']['R7_F1_terminal_numeric_slot'],'evidence_sha256':digest(s['new_evidence']['R7_F1_terminal_numeric_slot']),'status':f1['status'],'target':'KU-RO','scope_region':'HT','signature':'N|END','post_F0_training_derived':True,'same_corpus_independent_confirmation':False,'target_prevalence':f1['candidate']['target_prevalence_all_target_events'],'object_weighted_effect':f1['candidate']['object_weighted_effect'],'positive_object_fraction':f1['candidate']['positive_object_fraction'],'LOO_positive_fraction':f1['candidate']['leave_one_object_out_positive_fraction'],'familywise_empirical_p':f1['structure_destroying_null']['familywise_empirical_p'],'internal_refinement_label':f1['admission']['admitted_refinement_label'],'internal_refinement_established':True}
    st['R7_first_probable_structural_function']['internal_post_F0_refinement']={'label':req['F1_refinement_label'],'scope':'HT_DEVELOPMENT_CORPUS_INTERNAL','independent_replication':False,'semantic_TOTAL_or_SUMMARY':False,'evidence_path':s['new_evidence']['R7_F1_terminal_numeric_slot']}
    road=[r for r in st.get('roadmap',[]) if r.get('id') not in {'R7_C0_5_NONSINGLETON_CORRECTIVE','R7_F1_TERMINAL_NUMERIC_SLOT','R7_G0_TERMINAL_NUMERIC_PAYLOAD_PROFILE'}]
    road.extend([{'id':'R7_C0_5_NONSINGLETON_CORRECTIVE','status':'DONE_POSTHOC_KU_RO_SURVIVES'}, {'id':'R7_F1_TERMINAL_NUMERIC_SLOT','status':'DONE_INTERNAL_REFINEMENT_ADMITTED_NOT_INDEPENDENT'}, {'id':'R7_G0_TERMINAL_NUMERIC_PAYLOAD_PROFILE','status':'READY_NOT_EXECUTED'}]); st['roadmap']=road
    replace_ids={x['id'] for x in s['next_atomic_requirements']}; st['next_atomic_requirements']=s['next_atomic_requirements']+[r for r in st.get('next_atomic_requirements',[]) if r.get('id') not in replace_ids]
    st['global_claim_ceiling_v2_31']={'probable_region_scoped_structural_function_established':True,'admitted_source_word':'KU-RO','admitted_probable_structural_function':'ROW-OPENING-LIKE','scope_region':'HT','nonsingleton_corrective_survival':True,'internal_post_F0_terminal_numeric_slot_refinement_established':True,'internal_refinement_label':req['F1_refinement_label'],'internal_refinement_independently_replicated':False,'TOTAL_or_SUMMARY_semantic_function_established':False,'universal_cross_region_function_established':False,'exact_word_meaning_established':False,'translation_established':False,'phonetic_value_established':False,'language_family_established':False,'new_anchor_established':False,'decipherment_established':False,'strict_R3B_replication_established':False,'allowed':s['claim_ceiling']['allowed'],'forbidden':s['claim_ceiling']['forbidden']}
    Path(a.candidate_out).write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    audit_checks={**checks,'version_v2_31':st['version']=='v2.31','probable_retained':st['global_claim_ceiling_v2_31']['probable_region_scoped_structural_function_established'] is True,'refinement_true':st['global_claim_ceiling_v2_31']['internal_post_F0_terminal_numeric_slot_refinement_established'] is True,'independent_false':st['global_claim_ceiling_v2_31']['internal_refinement_independently_replicated'] is False,'total_false':st['global_claim_ceiling_v2_31']['TOTAL_or_SUMMARY_semantic_function_established'] is False,'meaning_false2':st['global_claim_ceiling_v2_31']['exact_word_meaning_established'] is False,'decipherment_false2':st['global_claim_ceiling_v2_31']['decipherment_established'] is False}
    passed=all(audit_checks.values()); audit={'artifact_uuid':'JANUS-LINEAR-A-RESEARCH-STATE-CANONICALITY-AUDIT-2026-08-16-v2.31','version':'v2.31','status':'CANONICALITY_AUDIT_PASS' if passed else 'CANONICALITY_AUDIT_FAIL','executed_at':now,'promotion_spec':a.spec,'parent_state':s['parent_state'],'parent_sha256':digest(s['parent_state']),'C0_5_sha256':digest(s['new_evidence']['R7_C0_5_corrective']),'F1_sha256':digest(s['new_evidence']['R7_F1_terminal_numeric_slot']),'candidate_sha256':digest(a.candidate_out),'checks':audit_checks,'all_checks_pass':passed,'claim_ceiling':s['claim_ceiling']}
    Path(a.audit_out).write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not passed: return 2
    st['canonicality']['canonicality_audit_status']='CANONICALITY_AUDIT_PASS'; Path(a.canonical_out).write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'CANONICAL_V2_31_READY','source_word':'KU-RO','probable_function':'ROW-OPENING-LIKE','internal_refinement':req['F1_refinement_label'],'scope':'HT','independent_refinement_replication':False,'decipherment':False},ensure_ascii=False,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
