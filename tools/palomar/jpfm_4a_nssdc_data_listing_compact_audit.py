#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

SOURCE=Path('data/JANUS-PALOMAR-JPFM-4A-NSSDC-DATA-LISTING-ROCKET-LINEAGE-PROBE-v1.0.json')
TERMS=['rocket','sounding rocket','rocket file','ROCKET System','master directory','online','near-line','offline','WDC-A']
ACCESS_WORDS=('online','on-line','near-line','master directory','anonymous','ndads','nodis','ftp','http','www')
ROCKET_WORDS=('rocket','sounding rocket')

def flatten_context(ctx:dict)->str:
    return ' '.join(str(x.get('text','')) for x in ctx.get('lines',[])).lower()

def contexts_for(doc:dict,term:str)->list[dict]:
    v=(doc.get('term_contexts') or {}).get(term,[])
    return v if isinstance(v,list) else []

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    src=json.loads(SOURCE.read_text())
    docs=[]
    for d in src['documents']:
        counts={t:len(contexts_for(d,t)) for t in TERMS}
        rocket_contexts=[]
        for term in ('rocket','sounding rocket','rocket file','ROCKET System'):
            rocket_contexts.extend(contexts_for(d,term))
        access_contexts=[]
        for term in ('master directory','online','near-line','offline'):
            access_contexts.extend(contexts_for(d,term))
        rocket_access=[flatten_context(c) for c in rocket_contexts if any(w in flatten_context(c) for w in ACCESS_WORDS)]
        access_rocket=[flatten_context(c) for c in access_contexts if any(w in flatten_context(c) for w in ROCKET_WORDS)]
        request_listing=[]
        for c in rocket_contexts+contexts_for(d,'WDC-A'):
            txt=flatten_context(c)
            if 'listings of rocket experiments' in txt or 'rocket launchings and experiments flown' in txt:
                request_listing.append(txt)
        docs.append({
          'year_label':d['year_label'],'document_id':d['document_id'],'title':d.get('title'),
          'fulltext_sha256':(d.get('fulltext') or {}).get('sha256'),
          'term_hit_counts':counts,
          'rocket_to_public_electronic_access_context_hits':len(set(rocket_access)),
          'public_electronic_access_to_rocket_context_hits':len(set(access_rocket)),
          'historical_request_or_listing_language_hits':len(set(request_listing)),
          'direct_public_rocket_product_identifier_found_in_probed_contexts':bool(rocket_access or access_rocket),
          'request_listing_examples':sorted(set(request_listing))[:3]
        })
    any_public=any(d['direct_public_rocket_product_identifier_found_in_probed_contexts'] for d in docs)
    result={
      'artifact_id':'JANUS-PALOMAR-JPFM-4A-NSSDC-ROCKET-PUBLIC-DESCENDANT-COMPACT-AUDIT-v1.0',
      'experiment_id':'JPFM-4A','date':dt.date.today().isoformat(),
      'status':'COMPACT_REVIEW_OF_FROZEN_NSSDC_DATA_LISTING_PROBE__NO_OUTCOME_JOIN',
      'source_path':str(SOURCE),
      'documents':docs,
      'aggregate':{
        'direct_public_rocket_product_identifier_found_in_probed_contexts':any_public,
        'disposition':'PUBLIC_ROCKET_PRODUCT_DESCENDANT_IDENTIFIER_FOUND_IN_PROBED_CONTEXTS' if any_public else 'PUBLIC_ROCKET_PRODUCT_DESCENDANT_NOT_IDENTIFIED_IN_PROBED_OFFICIAL_LISTING_CONTEXTS',
        'scope_warning':'This is not proof that no public descendant exists. It states only that no direct rocket↔electronic-access/product identifier was found in the frozen literal contexts probed from the 1978, 1980 and 1994 official NSSDC Data Listings.'
      },
      'outcome_blindness':{'bluebook_access':False,'poss1_access':False,'nuclear_calendar_access':False,'association_computed':False},
      'current_authority_changed':False,
      'claim_ceiling':'PUBLIC_DESCENDANT_SEARCH_AUDIT_ONLY__NO_ROCKET_EVENT_OR_ASSOCIATION_CLAIM'
    }
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True),encoding='utf-8');print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
