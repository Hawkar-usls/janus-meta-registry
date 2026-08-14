#!/usr/bin/env python3
"""Metadata-only disambiguation of Briakos annotations.js reported size."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from janus_linear_a_r3c_annotation_parser_validation_v0_1 import extract_array

EXPECTED_SHA = "7ce1f87a98827d059a732cc00506c635b4d5f65b2d0e2f1592fc2b67827758cd"
PUBLISHED = 2201442


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument('--source',required=True); ap.add_argument('--output',required=True); args=ap.parse_args()
    p=Path(args.source); raw=p.read_bytes(); text=raw.decode('utf-8')
    if hashlib.sha256(raw).hexdigest()!=EXPECTED_SHA:
        raise SystemExit('SOURCE_SHA_MISMATCH')
    payload,boundary=extract_array(text)
    end=boundary['payload_end_source_offset_inclusive']
    i=end+1
    while i < len(text) and text[i].isspace():
        # Freeze requires the semicolon immediately following the matching array,
        # but allows whitespace between array close and semicolon.
        i+=1
    semicolon_index=i if i < len(text) and text[i]==';' else None
    declaration_chars=(semicolon_index+1) if semicolon_index is not None else None
    declaration_bytes=(len(text[:semicolon_index+1].encode('utf-8')) if semicolon_index is not None else None)
    full_chars=len(text)
    terminal_lf=text.endswith('\n')
    terminal_crlf=text.endswith('\r\n')
    minus_one_lf=(len(text[:-1]) if terminal_lf else None)
    minus_one_crlf=(len(text[:-2]) if terminal_crlf else None)
    measurements={
      'raw_utf8_bytes':len(raw),
      'full_unicode_codepoints':full_chars,
      'minus_one_terminal_LF_codepoints':minus_one_lf,
      'minus_one_terminal_CRLF_codepoints':minus_one_crlf,
      'wordAnnotations_declaration_through_semicolon_codepoints':declaration_chars,
      'wordAnnotations_declaration_through_semicolon_utf8_bytes':declaration_bytes,
    }
    matches=[k for k,v in measurements.items() if v==PUBLISHED]
    if 'full_unicode_codepoints' in matches:
        status='MATCHES_FULL_UNICODE_CHARACTER_COUNT'
    elif 'wordAnnotations_declaration_through_semicolon_codepoints' in matches:
        status='MATCHES_DECLARATION_CHARACTER_COUNT'
    elif 'minus_one_terminal_LF_codepoints' in matches or 'minus_one_terminal_CRLF_codepoints' in matches:
        status='MATCHES_TERMINAL_NEWLINE_NORMALIZED_CHARACTER_COUNT'
    else:
        status='NO_PREDECLARED_SIZE_METRIC_MATCH'
    result={
      'artifact_uuid':'JANUS-LINEAR-A-R3C-1E-ANNOTATION-SIZE-METRIC-DISAMBIGUATION-RESULT-2026-08-14-v0.1',
      'version':'v0.1','node_type':'metadata_metric_disambiguation_result','status':status,
      'frozen_spec':'data/JANUS-LINEAR-A-R3C-1E-ANNOTATION-SIZE-METRIC-DISAMBIGUATION-SPEC-2026-08-14-v0.1.json',
      'source':{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'unicode_codepoints':full_chars},
      'published':{'label':'Bytes','value':PUBLISHED,'sha256_prefix':'7ce1f87a'},
      'boundary':boundary,
      'semicolon_source_character_offset':semicolon_index,
      'terminal':{'has_LF':terminal_lf,'has_CRLF':terminal_crlf,'last_escaped':text[-8:].encode('unicode_escape').decode('ascii')},
      'measurements':measurements,
      'matching_measurements':matches,
      'interpretation':{
        'exact_character_count_explanation_present':bool(matches),
        'author_measurement_implementation_inferred':False,
        'unit_label_mismatch_called_proven':False,
        'blind_credit':False,
      },
      'claim_ceiling':{'metadata_only':True,'Briakos_scope_inference':False,'R3B_effect':'NONE','new_anchor':False,'decipherment':False},
    }
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':status,'measurements':measurements,'matches':matches},sort_keys=True))
if __name__=='__main__': main()
