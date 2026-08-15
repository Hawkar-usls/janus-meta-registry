#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from pathlib import Path

import requests

FREEZE = Path('data/JANUS-PALOMAR-JPFM-3B-NOAA-HALPHA-SOURCE-FREEZE-v1.0.json')
UA = 'JANUS-JPFM-3B-schema-probe/1.0'


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def valid_hhmm(s: str) -> bool:
    s = s.strip()
    if not s:
        return True
    if not re.fullmatch(r'\d{4}', s):
        return False
    hh, mm = int(s[:2]), int(s[2:])
    return 0 <= hh <= 23 and 0 <= mm <= 59


def probe_line(line: str, year: int) -> dict:
    pad = line.ljust(100)
    code = pad[0:2]
    station_code = pad[2:5]
    yy, mm, dd = pad[5:7], pad[7:9], pad[9:11]
    start, end, maximum = pad[13:17], pad[18:22], pad[23:27]
    importance, brightness, completeness = pad[34:35], pad[35:36], pad[36:37]
    station_abbr = pad[67:71]
    grouping = pad[95:100]
    date_ok = False
    try:
        y = 1900 + int(yy)
        m, d = int(mm), int(dd)
        import datetime as dt
        dt.date(y, m, d)
        date_ok = (y == year)
    except Exception:
        pass
    return {
        'code': code,
        'station_code': station_code,
        'yy_mm_dd': [yy, mm, dd],
        'date_matches_file_year': date_ok,
        'start': start,
        'end': end,
        'maximum': maximum,
        'time_fields_syntactically_valid': all(valid_hhmm(x) for x in (start, end, maximum)),
        'importance': importance,
        'brightness': brightness,
        'completeness': completeness,
        'station_abbr': station_abbr,
        'grouping': grouping,
        'grouping_numeric_or_blank': (not grouping.strip()) or grouping.strip().isdigit(),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    freeze_bytes = FREEZE.read_bytes()
    freeze = json.loads(freeze_bytes)
    session = requests.Session()
    session.headers['User-Agent'] = UA
    years = []
    for f in freeze['files']:
        year = int(f['year'])
        r = session.get(f['url'], timeout=120)
        r.raise_for_status()
        b = r.content
        if sha256(b) != f['sha256']:
            raise RuntimeError(f'{year}: frozen source hash mismatch')
        text = b.decode('ascii', errors='replace')
        lines = text.splitlines()
        if len(lines) != int(f['lines']):
            raise RuntimeError(f'{year}: line-count drift {len(lines)} != {f["lines"]}')
        length_census = collections.Counter(len(x) for x in lines)
        prefix2 = collections.Counter(x[:2] for x in lines)
        prefix1 = collections.Counter(x[:1] for x in lines)
        probes = [probe_line(x, year) for x in lines]
        date_ok = sum(p['date_matches_file_year'] for p in probes)
        time_ok = sum(p['time_fields_syntactically_valid'] for p in probes)
        group_ok = sum(p['grouping_numeric_or_blank'] for p in probes)
        grouping_nonblank = sum(bool(p['grouping'].strip()) for p in probes)
        station_codes = collections.Counter(p['station_code'] for p in probes)
        stations_abbr = collections.Counter(p['station_abbr'].strip() for p in probes if p['station_abbr'].strip())
        years.append({
            'year': year,
            'source_sha256': f['sha256'],
            'rows': len(lines),
            'line_length_census': {str(k): v for k, v in sorted(length_census.items())},
            'prefix2_census': dict(sorted(prefix2.items())),
            'prefix1_census': dict(sorted(prefix1.items())),
            'date_matches_file_year_rows': date_ok,
            'date_match_fraction': date_ok / len(lines) if lines else None,
            'time_fields_syntactically_valid_rows': time_ok,
            'time_valid_fraction': time_ok / len(lines) if lines else None,
            'grouping_numeric_or_blank_rows': group_ok,
            'grouping_nonblank_rows': grouping_nonblank,
            'unique_station_codes_at_cols_3_5': len(station_codes),
            'top_station_codes': station_codes.most_common(12),
            'unique_station_abbr_at_cols_68_71': len(stations_abbr),
            'top_station_abbr': stations_abbr.most_common(12),
            'sample_rows': [
                {
                    'raw': lines[i],
                    'raw_sha256': sha256(lines[i].encode('ascii', errors='replace')),
                    'probe': probes[i],
                }
                for i in range(min(3, len(lines)))
            ],
        })
    out = {
        'artifact_id': 'JANUS-PALOMAR-JPFM-3B-NOAA-HALPHA-SCHEMA-PROBE-v1.0',
        'status': 'OUTCOME_BLIND_SCHEMA_PROBE__NO_ASSOCIATION_COMPUTED',
        'source_freeze_path': str(FREEZE),
        'source_freeze_sha256': sha256(freeze_bytes),
        'documentation_contract_tested': {
            'candidate_schema': 'NOAA H-alpha data-code 31 fixed-width station-report fields; grouping at columns 96-100',
            'warning': 'NOAA documentation explicitly states 1955-1974 need extensive editing to match later records; pre-1955 applicability is not assumed.',
            'probe_is_not_schema_admission': True,
        },
        'years': years,
        'outcome_blindness': {
            'bluebook_access': False,
            'poss1_access': False,
            'nuclear_calendar_access': False,
            'association_computed': False,
        },
        'next_gate': 'Use observed year-specific structure to define explicit parser eras; validate date/time/station semantics and grouping reliability before physical flare consolidation.',
        'claim_ceiling': 'SOURCE_STRUCTURE_ONLY__NO_FLARE_EVENT_OR_ASSOCIATION_CLAIM',
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
