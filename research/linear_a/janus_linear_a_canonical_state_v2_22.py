from __future__ import annotations
import argparse, copy, hashlib, json, pathlib
from datetime import datetime, timezone, timedelta
TZ=timezone(timedelta(hours=3))
def load(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def digest(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--spec',required=True); ap.add_argument('--candidate-out',required=True); ap.add_argument('--canonical-out',required=True); ap.add_argument('--audit-out',required=True); a=ap.parse_args()
    s=load(a.spec); parent=load(s['parent_state']); r5=load(s['new_evidence'][0]); r6=load(s['new_evidence'][1]); m=r5['aggregate_masked_word_prediction']; fam=r6['all_cross_fitted_candidates_after_scoring']
    ni=[x for x in fam if x.get('source_word_after_scoring')=='NI' and x.get('role')=='RIGHT_NUMERIC']
    pre={
      'parent_v2_21':parent.get('version')=='v2.21' and parent.get('status')=='CURRENT_CANONICAL_RESEARCH_STATE',
      'r5_status':r5.get('status')==s['required_statuses']['R5_0'],
      'r6_status':r6.get('status')==s['required_statuses']['R6_0'],
      'r5_masks':r5['admission'].get('actual_evaluable_masks')==224,
      'r5_B1_MRR':m['B1_DIRECTIONAL_WORD_CONTEXT_COUNT']['mean_reciprocal_rank']>m['B0_WORD_UNIGRAM']['mean_reciprocal_rank'],
      'r5_B1_top5':m['B1_DIRECTIONAL_WORD_CONTEXT_COUNT']['top5_accuracy']>m['B0_WORD_UNIGRAM']['top5_accuracy'],
      'r5_M1_MRR_not_better':m['M1_WORD_PPMI_SVD']['mean_reciprocal_rank']<=m['B0_WORD_UNIGRAM']['mean_reciprocal_rank'],
      'r5_no_role_analogies':r5['cross_fold_word_role_analogy'].get('CV_role_analogy_count')==0,
      'r6_family_2':r6.get('cross_fitted_candidate_family_size')==2,
      'r6_admitted_0':r6.get('admitted_role_candidate_count')==0,
      'ni_exactly_one':len(ni)==1,
      'ni_not_admitted':len(ni)==1 and ni[0].get('ROLE_CANDIDATE_ADMITTED') is False,
      'ni_rate_exact':len(ni)==1 and ni[0].get('heldout_adjacency_rate')==s['required_preserved_observations']['R6_NI_right_numeric_heldout_rate'],
      'ni_p_exact':len(ni)==1 and ni[0].get('p_value')==s['required_preserved_observations']['R6_NI_right_numeric_p'],
      'ni_q_exact':len(ni)==1 and ni[0].get('BH_q')==s['required_preserved_observations']['R6_NI_right_numeric_BH_q'],
      'no_decipherment_r5':r5['epistemic_gate'].get('decipherment_established') is False,
      'no_decipherment_r6':r6['epistemic_gate'].get('decipherment_established') is False,
    }
    if not all(pre.values()): raise SystemExit(json.dumps(pre,sort_keys=True))
    st=copy.deepcopy(parent); now=datetime.now(TZ).isoformat(); st.update({'artifact_uuid':'JANUS-LINEAR-A-RESEARCH-STATE-2026-08-14-v2.22','timestamp':now,'version':'v2.22','title':'JANUS Linear A canonical state after word-level benchmark and cross-fitted numeric-adjacency role audit','status':'CURRENT_CANONICAL_RESEARCH_STATE'})
    st['canonicality']={'current_source_of_truth':True,'parent_state':s['parent_state'],'promotion_spec':a.spec,'promotion_prerequisites_pass':True,'history_is_not_deleted':True,'candidate_path':a.candidate_out,'canonicality_audit':a.audit_out,'canonicality_audit_status':'PENDING_UNTIL_AUDIT_EMITTED','promotion_rule_satisfied':True}
    st['R5_word_level_discovery_lane']={'status':'R5_0_MIXED_PREDICTIVE_SIGNAL_COMBINED_GATE_NOT_ADMITTED','path':s['new_evidence'][0],'evidence_sha256':digest(s['new_evidence'][0]),'evaluable_masks':224,'B0_WORD_UNIGRAM':m['B0_WORD_UNIGRAM'],'B1_DIRECTIONAL_WORD_CONTEXT_COUNT':m['B1_DIRECTIONAL_WORD_CONTEXT_COUNT'],'M1_WORD_PPMI_SVD':m['M1_WORD_PPMI_SVD'],'CV_role_analogy_count':0,'word_level_role_structure_admitted':False}
    st['R6_numeric_adjacency_role_lane']={'status':'R6_0_NO_FDR_ADMITTED_ROLE_CANDIDATE','path':s['new_evidence'][1],'evidence_sha256':digest(s['new_evidence'][1]),'candidate_family_size':2,'admitted_candidate_count':0,'descriptive_near_threshold_patterns':[{'source_word':'NI','role':'RIGHT_NUMERIC','heldout_hits':ni[0]['heldout_numeric_hits'],'heldout_occurrences':ni[0]['heldout_occurrences'],'heldout_rate':ni[0]['heldout_adjacency_rate'],'p_value':ni[0]['p_value'],'BH_q':ni[0]['BH_q'],'selected_fold_count':ni[0]['selected_fold_count'],'numeric_bucket_distribution':ni[0]['numeric_bucket_distribution'],'region_set':ni[0]['region_set'],'classification':'DESCRIPTIVE_NEAR_THRESHOLD_NOT_ADMITTED'}]}
    road=[x for x in st.get('roadmap',[]) if x.get('id') not in {'R5_0_WORD_LEVEL_SELF_SUPERVISED_DISCOVERY','R6_0_NUMERIC_ADJACENCY_ROLES','R6_1_REGION_CONDITIONED_NULL_AUDIT'}]
    road += [{'id':'R5_0_WORD_LEVEL_SELF_SUPERVISED_DISCOVERY','status':'DONE_MIXED_COMBINED_GATE_NOT_ADMITTED'},{'id':'R6_0_NUMERIC_ADJACENCY_ROLES','status':'DONE_0_FDR_ADMITTED_NI_NEAR_THRESHOLD_PRESERVED'},{'id':'R6_1_REGION_CONDITIONED_NULL_AUDIT','status':'READY_POSTHOC_CORRECTIVE_NO_BLIND_CREDIT'}]; st['roadmap']=road
    st['next_atomic_requirements']=[{'id':'R6_1_REGION_CONDITIONED_NULL_AUDIT','action':s['next_atomic_requirements'][0]},{'id':'R3B_EXTERNAL_VALIDATION','action':s['next_atomic_requirements'][1]}]+[x for x in st.get('next_atomic_requirements',[]) if x.get('id') not in {'R5_0_WORD_LEVEL_SELF_SUPERVISED_DISCOVERY'}]
    st['global_claim_ceiling_v2_22']={'sign_level_context_structure_learned_cross_validated':True,'word_level_combined_role_structure_admitted':False,'numeric_role_candidate_admitted':False,'NI_right_numeric_pattern_descriptive_only':True,'NI_meaning_established':False,'translation_established':False,'phonetic_value_established':False,'grammatical_label_established':False,'new_anchor_established':False,'decipherment_established':False,'strict_R3B_replication_established':False,'allowed':s['claim_ceiling']['allowed'],'forbidden':s['claim_ceiling']['forbidden']}
    pathlib.Path(a.candidate_out).write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    checks={**pre,'version':st['version']=='v2.22','ni_descriptive':st['global_claim_ceiling_v2_22']['NI_right_numeric_pattern_descriptive_only'] is True,'ni_meaning_false':st['global_claim_ceiling_v2_22']['NI_meaning_established'] is False,'decipherment_false':st['global_claim_ceiling_v2_22']['decipherment_established'] is False,'r6_admitted_false':st['global_claim_ceiling_v2_22']['numeric_role_candidate_admitted'] is False}; passed=all(checks.values()); audit={'artifact_uuid':'JANUS-LINEAR-A-RESEARCH-STATE-CANONICALITY-AUDIT-2026-08-14-v2.22','version':'v2.22','status':'CANONICALITY_AUDIT_PASS' if passed else 'CANONICALITY_AUDIT_FAIL','executed_at':now,'promotion_spec':a.spec,'parent_state':s['parent_state'],'new_evidence':s['new_evidence'],'parent_sha256':digest(s['parent_state']),'R5_sha256':digest(s['new_evidence'][0]),'R6_sha256':digest(s['new_evidence'][1]),'candidate_sha256':digest(a.candidate_out),'checks':checks,'all_checks_pass':passed,'claim_ceiling':s['claim_ceiling']}; pathlib.Path(a.audit_out).write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not passed:return 2
    st['canonicality']['canonicality_audit_status']='CANONICALITY_AUDIT_PASS'; pathlib.Path(a.canonical_out).write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps({'status':'CANONICAL_V2_22_READY','NI_q':ni[0]['BH_q'],'numeric_role_admitted':False,'decipherment_established':False},indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
