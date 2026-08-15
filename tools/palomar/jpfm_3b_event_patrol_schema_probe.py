#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

import requests

FREEZE = Path('data/JANUS-PALOMAR-JPFM-3B-NOAA-EVENT-PATROL-SOURCE-FREEZE-v1.0.json')
PATROL_DOC_URL = 'https://www.ngdc.noaa.gov/stp/space-weather/solar-data/solar-features/solar-flares/flare-patrol/patrol/documentation/patrol_format.txt'
UA = 'JANUS-JPFM-3B-event-patrol-schema-probe/1.0'


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def fetch_verified(s: requests.Session, info: dict) -> list[str]:
    r = s.get(info['url'], timeout=180); r.raise_for_status(); b = r.content
    if sha256(b) != info['sha256']:
        raise RuntimeError(f'hash mismatch: {info["url"]}')
    return b.decode('ascii', errors='replace').splitlines()


def sample_by_length(lines: list[str], n=8):
    out = {}
    for L in sorted(set(map(len, lines))):
        rows = [x for x in lines if len(x) == L][:n]
        out[str(L)] = [
            {
                'raw': x,
                'sha256': sha256(x.encode('ascii', errors='replace')),
                'prefix2': x[:2],
                'prefix5': x[:5],
                'suffix10': x[-10:],
            }
            for x in rows
        ]
    return out


def structure(lines: list[str]) -> dict:
    return {
        'rows': len(lines),
        'length_census': {str(k): v for k, v in sorted(collections.Counter(map(len, lines)).items())},
        'prefix2_by_length': {
            str(L): dict(collections.Counter(x[:2] for x in lines if len(x) == L).most_common())
            for L in sorted(set(map(len, lines)))
        },
        'prefix5_by_length_top20': {
            str(L): collections.Counter(x[:5] for x in lines if len(x) == L).most_common(20)
            for L in sorted(set(map(len, lines)))
        },
        'samples_by_length': sample_by_length(lines),
    }


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', type=Path, required=True); args = ap.parse_args()
    freeze_b = FREEZE.read_bytes(); freeze = json.loads(freeze_b)
    s = requests.Session(); s.headers['User-Agent'] = UA
    doc = s.get(PATROL_DOC_URL, timeout=120); doc.raise_for_status(); doc_b = doc.content
    doc_text = doc_b.decode('ascii', errors='replace')
    event_years, patrol_years = [], []
    for y in freeze['event_archive']['years']:
        f = y['files'][0]
        event_years.append({'year': y['year'], 'source_sha256': f['sha256'], **structure(fetch_verified(s, f))})
    for y in freeze['patrol_archive']['years']:
        f = y['files'][0]
        patrol_years.append({'year': y['year'], 'source_sha256': f['sha256'], **structure(fetch_verified(s, f))})
    result = {
        'artifact_id': 'JANUS-PALOMAR-JPFM-3B-NOAA-EVENT-PATROL-SCHEMA-PROBE-v1.0',
        'status': 'OUTCOME_BLIND_SCHEMA_PROBE__NO_ASSOCIATION_COMPUTED',
        'source_freeze_path': str(FREEZE),
        'source_freeze_sha256': sha256(freeze_b),
        'patrol_format_documentation': {
            'url': PATROL_DOC_URL,
            'sha256': sha256(doc_b),
            'bytes': len(doc_b),
            'text': doc_text,
        },
        'event_years': event_years,
        'patrol_years': patrol_years,
        'outcome_blindness': {
            'bluebook_access': False,
            'poss1_access': False,
            'nuclear_calendar_access': False,
            'association_computed': False,
        },
        'next_gate': 'Define event and patrol parsers from the observed stable record geometries and documentation; do not inspect any Blue Book/POSS-I outcome until parser and coverage admission are frozen.',
        'claim_ceiling': 'NOAA_EVENT_PATROL_SOURCE_STRUCTURE_ONLY__NO_FLARE_ASSOCIATION_CLAIM',
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
