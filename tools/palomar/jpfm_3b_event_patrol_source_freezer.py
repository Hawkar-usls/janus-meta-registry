#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests

YEARS = (1955, 1956, 1957)
EVENT_BASE = 'https://www.ngdc.noaa.gov/stp/space-weather/solar-data/solar-features/solar-flares/h-alpha/events/'
PATROL_BASE = 'https://www.ngdc.noaa.gov/stp/space-weather/solar-data/solar-features/solar-flares/flare-patrol/patrol/'
UA = 'JANUS-JPFM-3B-event-patrol-freezer/1.0'


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def hrefs(html: str) -> list[str]:
    vals = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
    out = []
    for h in vals:
        if h.startswith('?') or h.startswith('/') or h.startswith('../') or h == '../':
            continue
        if h.endswith('/'):
            continue
        out.append(h)
    return sorted(set(out))


def freeze_tree(session: requests.Session, base: str, label: str) -> dict:
    years = []
    ordered_hash_parts = []
    for year in YEARS:
        index_url = urljoin(base, f'{year}/')
        r = session.get(index_url, timeout=120)
        r.raise_for_status()
        index_b = r.content
        names = hrefs(r.text)
        # Only freeze plain-data payloads; documentation/images are not mixed into the event corpus.
        data_names = [n for n in names if n.lower().endswith(('.txt', '.dat'))]
        if not data_names:
            raise RuntimeError(f'{label} {year}: no .txt/.dat files discovered; names={names[:20]}')
        files = []
        for name in data_names:
            u = urljoin(index_url, name)
            q = session.get(u, timeout=180)
            q.raise_for_status()
            b = q.content
            lines = b.decode('ascii', errors='replace').splitlines()
            h = sha256(b)
            ordered_hash_parts.append(f'{label}|{year}|{name}|{h}\n'.encode())
            files.append({
                'filename': name,
                'url': u,
                'sha256': h,
                'bytes': len(b),
                'lines': len(lines),
                'nonblank_lines': sum(bool(x.strip()) for x in lines),
                'line_length_census': {str(k): v for k, v in sorted(__import__('collections').Counter(len(x) for x in lines).items())},
                'first_nonblank_line_sha256': next((sha256(x.encode('ascii', errors='replace')) for x in lines if x.strip()), None),
                'last_nonblank_line_sha256': next((sha256(x.encode('ascii', errors='replace')) for x in reversed(lines) if x.strip()), None),
            })
        years.append({
            'year': year,
            'index_url': index_url,
            'index_sha256': sha256(index_b),
            'discovered_links': names,
            'data_file_count': len(files),
            'files': files,
        })
    return {
        'label': label,
        'base_url': base,
        'years': years,
        'combined_ordered_file_identity_sha256': sha256(b''.join(ordered_hash_parts)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    s = requests.Session(); s.headers['User-Agent'] = UA
    event = freeze_tree(s, EVENT_BASE, 'NOAA_HALPHA_EVENTS')
    patrol = freeze_tree(s, PATROL_BASE, 'NOAA_FLARE_PATROL')
    result = {
        'artifact_id': 'JANUS-PALOMAR-JPFM-3B-NOAA-EVENT-PATROL-SOURCE-FREEZE-v1.0',
        'status': 'SOURCE_BYTES_FROZEN__EVENT_AND_PATROL_SCHEMA_NOT_YET_ADMITTED',
        'years': list(YEARS),
        'event_archive': event,
        'patrol_archive': patrol,
        'design_role': {
            'events': 'Official NOAA grouped H-alpha event reference available from 1955 onward; candidate physical-event reference, pending schema validation.',
            'patrol': 'Observing-opportunity source for flare patrol from 1955 onward; required before treating no-event dates as negatives.',
            'pre_1955_policy': '1949-1954 merged station reports remain positive-report-only; no-report dates are not negative flare dates without an independent coverage source.',
            'training_validation_split_frozen_before_grouping_comparison': {
                'training_year': 1955,
                'validation_years': [1956, 1957]
            }
        },
        'outcome_blindness': {
            'bluebook_access': False,
            'poss1_access': False,
            'nuclear_calendar_access': False,
            'association_computed': False
        },
        'next_gate': 'Parse NOAA event and patrol schemas; use 1955 event groups to calibrate a deterministic station-report consolidation algorithm, freeze it, then measure recovery on held-out 1956-1957 before any Blue Book/POSS-I join.',
        'claim_ceiling': 'NOAA_EVENT_AND_PATROL_SOURCE_FREEZE_ONLY__NO_FLARE_ASSOCIATION_CLAIM'
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
