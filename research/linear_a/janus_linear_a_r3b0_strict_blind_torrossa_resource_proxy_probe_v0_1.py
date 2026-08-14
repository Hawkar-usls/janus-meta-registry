from __future__ import annotations
import argparse, hashlib, json, pathlib, urllib.request
from datetime import datetime, timezone

def H(b:bytes)->str:return hashlib.sha256(b).hexdigest()

def fetch(url:str):
    req=urllib.request.Request(url,headers={'User-Agent':'JANUS-Linear-A-Torrossa-blind-probe/0.1','Accept':'application/pdf,application/octet-stream;q=0.9,*/*;q=0.1'})
    with urllib.request.urlopen(req,timeout=60) as r:
        return getattr(r,'status',None),r.headers.get('Content-Type'),r.geturl(),r.read()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--spec',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    spec=json.loads(pathlib.Path(a.spec).read_text(encoding='utf-8'))
    rows=[]
    for x in spec['routes']:
        try:
            st,ct,fu,b=fetch(x['url'])
            pdf=b.startswith(b'%PDF-')
            rows.append({'candidate_id':x['candidate_id'],'requested_url':x['url'],'resolved_url':fu,'http_status':st,'content_type':ct,'byte_length':len(b),'sha256':H(b),'pdf_magic':b[:5].decode('ascii',errors='replace'),'classification':'PRECONTENT_EXACT_PDF_BYTES_SEALED' if st==200 and pdf else 'FETCHED_NONPDF_RESPONSE_NOT_ADMITTED','body_persisted':False,'body_parsed':False,'pdf_text_extraction':False,'pdf_rendering':False,'ocr':False})
        except Exception as e:
            rows.append({'candidate_id':x['candidate_id'],'requested_url':x['url'],'classification':'NETWORK_OR_TRANSPORT_FAILURE_NOT_ADMITTED','exception_type':type(e).__name__,'message_sha256':H(str(e).encode())})
    sealed=[r['candidate_id'] for r in rows if r['classification']=='PRECONTENT_EXACT_PDF_BYTES_SEALED']
    out={'artifact_uuid':'JANUS-LINEAR-A-R3B-0-STRICT-BLIND-TORROSSA-RESOURCE-PROXY-PROBE-RESULT-2026-08-14-v0.1','version':'v0.1','node_type':'precontent_opaque_byte_probe_result','executed_at_utc':datetime.now(timezone.utc).isoformat(),'frozen_spec':a.spec,'status':'TORROSSA_PRECONTENT_BYTE_SEAL_OBTAINED' if sealed else 'TORROSSA_PRECONTENT_BYTE_SEAL_NOT_OBTAINED','probe_results':rows,'summary':{'route_count':2,'sealed_candidate_count':len(sealed),'sealed_candidates':sealed,'source_content_inspected':False,'source_native_sign_readings_seen':False,'overlap_selected':False,'strict_r3b_replication_established':False},'all_checks_pass':len(rows)==2,'claim_ceiling':spec['claim_ceiling']}
    pathlib.Path(a.out).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':out['status'],'summary':out['summary'],'classifications':{r['candidate_id']:r['classification'] for r in rows}},indent=2))
    return 0
if __name__=='__main__':raise SystemExit(main())
