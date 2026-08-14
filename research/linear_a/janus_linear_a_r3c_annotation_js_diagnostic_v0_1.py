#!/usr/bin/env python3
"""Non-evaluating annotations.js strict-JSON failure diagnostic."""
from __future__ import annotations
import argparse, hashlib, json, re, unicodedata
from pathlib import Path

MARKER = "var wordAnnotations"

def esc(s: str) -> str:
    return s.encode('unicode_escape').decode('ascii')

def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument('--source',required=True); ap.add_argument('--output',required=True); args=ap.parse_args()
    p=Path(args.source); raw=p.read_bytes(); text=raw.decode('utf-8')
    m=text.find(MARKER); start=text.find('[',m+len(MARKER)); end=text.rfind(']')
    payload=text[start:end+1]
    result={
      'artifact_uuid':'JANUS-LINEAR-A-R3C-1E-ANNOTATION-JS-DIAGNOSTIC-RESULT-2026-08-14-v0.1',
      'version':'v0.1','node_type':'source_grammar_diagnostic','status':'UNSET',
      'source':{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'published_bytes_match':len(raw)==2201442,'published_sha256_prefix_match':hashlib.sha256(raw).hexdigest().startswith('7ce1f87a')},
      'safety':{'javascript_executed':False,'eval_used':False,'identity_scoring_performed':False},
      'claim_ceiling':{'diagnostic_only':True,'Briakos_scope_inference':False,'R3B_effect':'NONE','decipherment':False}
    }
    try:
        json.loads(payload)
    except json.JSONDecodeError as e:
        lines=payload.splitlines(); lo=max(1,e.lineno-5); hi=min(len(lines),e.lineno+5)
        before=payload[max(0,e.pos-500):e.pos]; after=payload[e.pos:min(len(payload),e.pos+500)]; nearby=before+after
        result.update({
          'status':'FIRST_STRICT_JSON_BREAK_LOCALIZED',
          'json_error':{'message':e.msg,'line':e.lineno,'column':e.colno,'character_offset':e.pos},
          'error_character':esc(payload[e.pos] if e.pos<len(payload) else ''),
          'surrounding_lines':[{'line':n,'escaped':esc(lines[n-1])} for n in range(lo,hi+1)],
          'context_escaped':esc(nearby),
          'lexical_candidates':{
            'trailing_comma_candidate':bool(re.search(r',\s*[}\]]',nearby)),
            'js_codepoint_escape_candidate':bool(re.search(r'\\u\{[0-9A-Fa-f]{1,6}\}',nearby)),
            'undefined_candidate':bool(re.search(r'\bundefined\b',nearby)),
            'single_quote_nearby':"'" in nearby,
            'line_comment_nearby':'//' in nearby,
            'block_comment_nearby':'/*' in nearby or '*/' in nearby,
          }
        })
    else:
        result['status']='STRICT_JSON_PARSE_SUCCESS_UNEXPECTED'
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True,sort_keys=True))
if __name__=='__main__': main()
