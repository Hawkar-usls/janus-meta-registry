from __future__ import annotations

import argparse, hashlib, json, pathlib, urllib.parse, urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser


class A(HTMLParser):
    def __init__(self):
        super().__init__(); self.hrefs=[]
    def handle_starttag(self, tag, attrs):
        if tag.lower()=='a':
            d=dict(attrs)
            if d.get('href'): self.hrefs.append(d['href'])


def h(b: bytes)->str: return hashlib.sha256(b).hexdigest()

def fetch(url:str):
    req=urllib.request.Request(url,headers={'User-Agent':'JANUS-Linear-A-metadata-route-discovery/0.1','Accept':'application/json,text/html;q=0.9,*/*;q=0.1'})
    with urllib.request.urlopen(req,timeout=60) as r:
        return getattr(r,'status',None),r.headers.get('Content-Type'),r.geturl(),r.read()

def urls_from_json(obj, allowed_keys):
    out=[]
    def walk(x,key=None):
        if isinstance(x,dict):
            for k,v in x.items(): walk(v,k)
        elif isinstance(x,list):
            for v in x: walk(v,key)
        elif isinstance(x,str) and x.startswith(('http://','https://')):
            kl=(key or '').lower()
            if kl in allowed_keys or 'pdf' in kl or 'landing' in kl or kl=='url': out.append((x,key))
    walk(obj); return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--spec',required=True); ap.add_argument('--out',required=True); args=ap.parse_args()
    spec=json.loads(pathlib.Path(args.spec).read_text(encoding='utf-8'))
    allowed={x.lower() for x in spec['discovery_contract']['allowed_location_fields']}
    kws=[x.lower() for x in spec['discovery_contract']['html_anchor_keywords']]
    results=[]
    for t in spec['targets']:
        discovered=[]; receipts=[]; failures=[]
        for u in t['metadata_urls']:
            try:
                st,ct,fu,b=fetch(u)
                receipts.append({'requested_url':u,'resolved_url':fu,'http_status':st,'content_type':ct,'byte_length':len(b),'sha256':h(b),'response_body_persisted':False,'content_inspected':False})
                c=(ct or '').lower()
                if 'json' in c or u.startswith(('https://api.openalex.org/','https://api.crossref.org/')):
                    try:
                        obj=json.loads(b.decode('utf-8'))
                        for x,k in urls_from_json(obj,allowed):
                            discovered.append({'url':x,'source_metadata_url':u,'mechanism':'JSON_LOCATION_FIELD','field':k})
                    except Exception as e:
                        failures.append({'metadata_url':u,'stage':'json_parse','exception_type':type(e).__name__,'message_sha256':h(str(e).encode())})
                else:
                    txt=b.decode('utf-8',errors='replace'); p=A(); p.feed(txt)
                    for href in p.hrefs:
                        absu=urllib.parse.urljoin(fu,href); low=absu.lower()
                        if any(k in low for k in kws) or low.split('?',1)[0].endswith('.pdf'):
                            discovered.append({'url':absu,'source_metadata_url':u,'mechanism':'HTML_ANCHOR_KEYWORD','field':None})
            except Exception as e:
                failures.append({'metadata_url':u,'stage':'fetch','exception_type':type(e).__name__,'message_sha256':h(str(e).encode())})
        for u in t.get('predeclared_delivery_candidate_urls',[]):
            discovered.append({'url':u,'source_metadata_url':'FROZEN_SPEC','mechanism':'PREDECLARED_DELIVERY_CANDIDATE','field':None})
        dd={}
        for x in discovered: dd.setdefault(x['url'],x)
        results.append({'candidate_id':t['candidate_id'],'metadata_receipts':receipts,'metadata_failures':failures,'discovered_routes':list(dd.values()),'discovered_route_count':len(dd),'newly_discovered_routes_followed':False})
    result={
      'artifact_uuid':'JANUS-LINEAR-A-R3B-0-STRICT-BLIND-EXTERNAL-ROUTE-DISCOVERY-RESULT-2026-08-14-v0.1',
      'version':'v0.1','node_type':'metadata_only_external_route_discovery_result','executed_at_utc':datetime.now(timezone.utc).isoformat(),
      'frozen_spec':args.spec,'status':'METADATA_ONLY_EXTERNAL_ROUTE_DISCOVERY_COMPLETE','candidate_results':results,
      'summary':{'candidate_count':len(results),'total_discovered_routes':sum(x['discovered_route_count'] for x in results),'newly_discovered_routes_followed':False,'source_content_inspected':False,'source_native_sign_readings_seen':False,'overlap_selected':False,'strict_r3b_replication_established':False},
      'all_checks_pass':len(results)==3 and all(not x['newly_discovered_routes_followed'] for x in results),
      'claim_ceiling':spec['claim_ceiling']
    }
    pathlib.Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'summary':result['summary'],'route_counts':{x['candidate_id']:x['discovered_route_count'] for x in results}},indent=2))
    return 0 if result['all_checks_pass'] else 2
if __name__=='__main__': raise SystemExit(main())
