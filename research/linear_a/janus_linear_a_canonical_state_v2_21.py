from __future__ import annotations
import argparse, copy, hashlib, json, pathlib
from datetime import datetime, timezone, timedelta
TZ=timezone(timedelta(hours=3))
def load(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def digest(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--spec',required=True); ap.add_argument('--candidate-out',required=True); ap.add_argument('--canonical-out',required=True); ap.add_argument('--audit-out',required=True); a=ap.parse_args()
    s=load(a.spec); parent=load(s['parent_state']); ev=load(s['new_evidence'])
    pre={
      'parent_v2_20':parent.get('version')=='v2.20' and parent.get('status')=='CURRENT_CANONICAL_RESEARCH_STATE',
      'evidence_status':ev.get('status')==s['required_evidence_status'],
      'summary_exact':all(ev['summary'].get(k)==v for k,v in s['required_summary'].items()),
      'candidate_count_4':ev.get('candidate_count')==4,
      'all_four_fail':all(x.get('FUNCTIONAL_SUBSTITUTION_GATE_PASS') is False for x in ev.get('pair_results',[])),
      'labels_not_scoring':ev['leakage_firewall'].get('source_labels_used_for_scoring') is False,
      'no_semantics':ev['epistemic_gate'].get('semantic_equivalence_established') is False,
      'no_decipherment':ev['epistemic_gate'].get('decipherment_established') is False,
      'R3B_untouched':ev['leakage_firewall'].get('R3B_blind_eligibility_affected') is False,
    }
    if not all(pre.values()): raise SystemExit(json.dumps(pre,sort_keys=True))
    st=copy.deepcopy(parent); now=datetime.now(TZ).isoformat(); st.update({'artifact_uuid':'JANUS-LINEAR-A-RESEARCH-STATE-2026-08-14-v2.21','timestamp':now,'version':'v2.21','title':'JANUS Linear A canonical state after strict R4-2 sign-level substitution-frame negative','status':'CURRENT_CANONICAL_RESEARCH_STATE'})
    st['canonicality']={'current_source_of_truth':True,'parent_state':s['parent_state'],'promotion_spec':a.spec,'promotion_prerequisites_pass':True,'history_is_not_deleted':True,'candidate_path':a.candidate_out,'canonicality_audit':a.audit_out,'canonicality_audit_status':'PENDING_UNTIL_AUDIT_EMITTED','promotion_rule_satisfied':True}
    lane=st.setdefault('R4_self_supervised_discovery_lane',{})
    lane['R4_2']={'path':s['new_evidence'],'status':ev['status'],'evidence_sha256':digest(s['new_evidence']),'candidate_count':4,'pairs_passing_exact_functional_substitution_gate':0,'interpretation':'R4-1 broad contextual analogy does not establish exact sign-level slot substitution under R4-2.'}
    lane['status']='R4_1_CONTEXT_STRUCTURE_ADMITTED_R4_2_EXACT_SIGN_SUBSTITUTION_NEGATIVE'
    road=[x for x in st.get('roadmap',[]) if x.get('id') not in {'R4_2_FUNCTIONAL_SUBSTITUTION_FRAMES','R5_0_WORD_LEVEL_SELF_SUPERVISED_DISCOVERY'}]
    road += [{'id':'R4_2_FUNCTIONAL_SUBSTITUTION_FRAMES','status':'DONE_STRICT_NEGATIVE_0_OF_4'},{'id':'R5_0_WORD_LEVEL_SELF_SUPERVISED_DISCOVERY','status':'READY_NOT_EXECUTED'}]; st['roadmap']=road
    st['next_atomic_requirements']=[{'id':'R5_0_WORD_LEVEL_SELF_SUPERVISED_DISCOVERY','action':s['next_atomic_requirement']}]+[x for x in st.get('next_atomic_requirements',[]) if x.get('id')!='R4_2_FUNCTIONAL_SUBSTITUTION_FRAMES']
    st['global_claim_ceiling_v2_21']={'internal_context_structure_learned_cross_validated':True,'exact_sign_level_functional_substitution_established':False,'semantic_equivalence_established':False,'translation_established':False,'phonetic_value_established':False,'new_anchor_established':False,'decipherment_established':False,'strict_R3B_replication_established':False,'allowed':s['claim_ceiling']['allowed'],'forbidden':s['claim_ceiling']['forbidden']}
    pathlib.Path(a.candidate_out).write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    checks={**pre,'version':st['version']=='v2.21','r4_2_negative':st['R4_self_supervised_discovery_lane']['R4_2']['pairs_passing_exact_functional_substitution_gate']==0,'R5_ready':any(x.get('id')=='R5_0_WORD_LEVEL_SELF_SUPERVISED_DISCOVERY' and x.get('status')=='READY_NOT_EXECUTED' for x in st['roadmap']),'decipherment_false':st['global_claim_ceiling_v2_21']['decipherment_established'] is False}
    passed=all(checks.values()); audit={'artifact_uuid':'JANUS-LINEAR-A-RESEARCH-STATE-CANONICALITY-AUDIT-2026-08-14-v2.21','version':'v2.21','status':'CANONICALITY_AUDIT_PASS' if passed else 'CANONICALITY_AUDIT_FAIL','executed_at':now,'promotion_spec':a.spec,'parent_state':s['parent_state'],'new_evidence':s['new_evidence'],'parent_sha256':digest(s['parent_state']),'evidence_sha256':digest(s['new_evidence']),'candidate_sha256':digest(a.candidate_out),'checks':checks,'all_checks_pass':passed,'claim_ceiling':s['claim_ceiling']}; pathlib.Path(a.audit_out).write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not passed:return 2
    st['canonicality']['canonicality_audit_status']='CANONICALITY_AUDIT_PASS'; pathlib.Path(a.canonical_out).write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps({'status':'CANONICAL_V2_21_READY','audit':audit['status'],'R4_2_pairs_pass':0,'decipherment_established':False},indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
