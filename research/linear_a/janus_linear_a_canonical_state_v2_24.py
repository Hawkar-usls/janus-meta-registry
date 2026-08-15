from __future__ import annotations
import argparse, copy, hashlib, json, pathlib
from datetime import datetime, timezone, timedelta
TZ=timezone(timedelta(hours=3))
def load(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def digest(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--spec',required=True);ap.add_argument('--candidate-out',required=True);ap.add_argument('--canonical-out',required=True);ap.add_argument('--audit-out',required=True);a=ap.parse_args()
    s=load(a.spec);parent=load(s['parent_state']);ev=load(s['new_evidence']);req=s['required']
    pre={
      'parent_v2_23':parent.get('version')=='v2.23' and parent.get('status')=='CURRENT_CANONICAL_RESEARCH_STATE',
      'status_exact':ev.get('status')==s['required_status'],
      'regions_exact':ev['region_selection'].get('selected_regions')==req['selected_regions'],
      'masks_exact':ev['admission'].get('actual_aggregate_evaluable_masks')==req['aggregate_evaluable_masks'],
      'regions_both_exact':ev['admission'].get('actual_regions_where_both_context_models_beat_unigram_MRR')==req['regions_where_both_context_models_beat_unigram_MRR'],
      'transfer_admitted':ev['admission'].get('cross_region_transfer_admitted') is req['cross_region_transfer_admitted'],
      'heldout_not_trained':ev['leakage_firewall'].get('heldout_region_documents_used_for_training') is False,
      'selection_no_metrics':ev['leakage_firewall'].get('heldout_metrics_used_for_region_selection') is False,
      'translation_false':ev['epistemic_gate'].get('translation_established') is False,
      'phonetic_false':ev['epistemic_gate'].get('phonetic_value_established') is False,
      'anchor_false':ev['epistemic_gate'].get('new_anchor_established') is False,
      'decipherment_false':ev['epistemic_gate'].get('decipherment_established') is False,
      'r3b_false':ev['epistemic_gate'].get('R3B_external_replication_established') is False,
    }
    if not all(pre.values()): raise SystemExit(json.dumps(pre,sort_keys=True))
    st=copy.deepcopy(parent);now=datetime.now(TZ).isoformat();st.update({'artifact_uuid':'JANUS-LINEAR-A-RESEARCH-STATE-2026-08-15-v2.24','timestamp':now,'version':'v2.24','title':'JANUS Linear A canonical state after cross-region self-supervised transfer admission','status':'CURRENT_CANONICAL_RESEARCH_STATE'})
    st['canonicality']={'current_source_of_truth':True,'parent_state':s['parent_state'],'promotion_spec':a.spec,'promotion_prerequisites_pass':True,'history_is_not_deleted':True,'candidate_path':a.candidate_out,'canonicality_audit':a.audit_out,'canonicality_audit_status':'PENDING_UNTIL_AUDIT_EMITTED','promotion_rule_satisfied':True}
    st['R4_cross_region_transfer_lane']={'path':s['new_evidence'],'status':ev['status'],'evidence_sha256':digest(s['new_evidence']),'selected_regions':ev['region_selection']['selected_regions'],'aggregate_evaluable_masks':ev['admission']['actual_aggregate_evaluable_masks'],'regions_where_both_context_models_beat_unigram_MRR':ev['admission']['actual_regions_where_both_context_models_beat_unigram_MRR'],'aggregate_metrics':ev['aggregate_transfer'],'cross_region_transfer_admitted':True}
    road=[x for x in st.get('roadmap',[]) if x.get('id') not in {'R4_3_CROSS_REGION_TRANSFER','R7_0_FORMULA_SLOT_COMPLETION'}];road.append({'id':'R4_3_CROSS_REGION_TRANSFER','status':'DONE_ADMITTED_HT_KH_PH_COMPLETE_REGION_HOLDOUT'});road.append({'id':'R7_0_FORMULA_SLOT_COMPLETION','status':'READY_NOT_EXECUTED'});st['roadmap']=road
    st['next_atomic_requirements']=[{'id':'R7_0_FORMULA_SLOT_COMPLETION','action':s['next_atomic_requirement']}]+[x for x in st.get('next_atomic_requirements',[]) if x.get('id') not in {'INTERNAL_DISCOVERY_NEXT','R7_0_FORMULA_SLOT_COMPLETION'}]
    st['global_claim_ceiling_v2_24']={'sign_level_context_structure_learned_cross_validated':True,'cross_region_internal_context_structure_transfer_established':True,'semantic_equivalence_established':False,'translation_established':False,'phonetic_value_established':False,'language_family_established':False,'new_anchor_established':False,'decipherment_established':False,'strict_R3B_replication_established':False,'allowed':s['claim_ceiling']['allowed'],'forbidden':s['claim_ceiling']['forbidden']}
    pathlib.Path(a.candidate_out).write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    checks={**pre,'version_v2_24':st['version']=='v2.24','transfer_true':st['global_claim_ceiling_v2_24']['cross_region_internal_context_structure_transfer_established'] is True,'semantics_false':st['global_claim_ceiling_v2_24']['semantic_equivalence_established'] is False,'decipherment_false2':st['global_claim_ceiling_v2_24']['decipherment_established'] is False};passed=all(checks.values());audit={'artifact_uuid':'JANUS-LINEAR-A-RESEARCH-STATE-CANONICALITY-AUDIT-2026-08-15-v2.24','version':'v2.24','status':'CANONICALITY_AUDIT_PASS' if passed else 'CANONICALITY_AUDIT_FAIL','executed_at':now,'promotion_spec':a.spec,'parent_state':s['parent_state'],'new_evidence':s['new_evidence'],'parent_sha256':digest(s['parent_state']),'evidence_sha256':digest(s['new_evidence']),'candidate_sha256':digest(a.candidate_out),'checks':checks,'all_checks_pass':passed,'claim_ceiling':s['claim_ceiling']};pathlib.Path(a.audit_out).write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not passed:return 2
    st['canonicality']['canonicality_audit_status']='CANONICALITY_AUDIT_PASS';pathlib.Path(a.canonical_out).write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':'CANONICAL_V2_24_READY','cross_region_transfer_established':True,'decipherment_established':False},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
