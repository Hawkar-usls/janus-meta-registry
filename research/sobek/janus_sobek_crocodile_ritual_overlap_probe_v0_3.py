#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ledger', required=True)
    ap.add_argument('--out')
    args = ap.parse_args()

    ledger = load(args.ledger)
    ws = ledger['witnesses']
    strict = [w for w in ws if w['strict_overlap_eligible']]

    def yes(w, key):
        return w['features'].get(key) is True

    sobek = [w for w in strict if yes(w, 'sobek_named')]
    repel = [w for w in strict if yes(w, 'crocodile_repelling_explicit')]
    both = [w for w in strict if yes(w, 'sobek_named') and yes(w, 'crocodile_repelling_explicit')]
    sobek_only = [w for w in strict if yes(w, 'sobek_named') and not yes(w, 'crocodile_repelling_explicit')]
    repel_only = [w for w in strict if yes(w, 'crocodile_repelling_explicit') and not yes(w, 'sobek_named')]
    neither = [w for w in strict if not yes(w, 'sobek_named') and not yes(w, 'crocodile_repelling_explicit')]
    horus = [w for w in strict if yes(w, 'horus_named')]
    wedjat = [w for w in strict if yes(w, 'wedjat_or_eye_of_horus_named')]
    sobek_horus = [w for w in strict if yes(w, 'sobek_horus_cooperation')]
    horus_wedjat_defense = [w for w in strict if w['lane'] in {'CROCODILE_REPELLING','AQUATIC_THREAT_PROTECTION'} and (yes(w,'horus_named') or yes(w,'wedjat_or_eye_of_horus_named'))]

    result = {
        'artifact_uuid': 'JANUS-SOBEK-CROCODILE-RITUAL-OVERLAP-RESULT-2026-08-16-v0.3',
        'version': 'v0.3',
        'timestamp_date': '2026-08-16',
        'status': 'PARALLEL_SYSTEMS_WITH_HORUS_WEDJAT_BRIDGE_EXPLICIT_SOBEK_REPELLING_INTERSECTION_NOT_OBSERVED',
        'gate_id': ledger['gate_id'],
        'ledger': args.ledger,
        'strict_full_passage_counts': {
            'eligible_witnesses': len(strict),
            'sobek_named': len(sobek),
            'crocodile_repelling_explicit': len(repel),
            'sobek_and_crocodile_repelling_same_witness': len(both),
            'sobek_named_without_crocodile_repelling': len(sobek_only),
            'crocodile_repelling_without_sobek_named': len(repel_only),
            'neither': len(neither),
            'horus_named': len(horus),
            'wedjat_or_eye_of_horus_named': len(wedjat),
            'sobek_horus_positive_cooperation': len(sobek_horus),
            'horus_or_wedjat_in_defensive_lane': len(horus_wedjat_defense)
        },
        'strict_witness_ids': {
            'sobek_named': [w['id'] for w in sobek],
            'crocodile_repelling_explicit': [w['id'] for w in repel],
            'intersection': [w['id'] for w in both],
            'horus_or_wedjat_in_defensive_lane': [w['id'] for w in horus_wedjat_defense],
            'sobek_horus_positive_cooperation': [w['id'] for w in sobek_horus]
        },
        'supplementary_witnesses': {
            'title_only_or_manuscript_record_ids': [w['id'] for w in ws if not w['strict_overlap_eligible']],
            'anti_crocodile_title_only': [w['id'] for w in ws if not w['strict_overlap_eligible'] and w['features'].get('crocodile_repelling_explicit') is True],
            'sobek_cult_manuscript_record': [w['id'] for w in ws if not w['strict_overlap_eligible'] and w['features'].get('sobek_positive_identity_or_cult') is True]
        },
        'bridge_map': {
            'ANTI_CROCODILE_TO_HORUS': 'METTERNICH_INCANTATION_10 explicitly asks Horus to repel crocodiles on the river.',
            'AQUATIC_PROTECTION_TO_WEDJAT': 'METTERNICH_INCANTATION_5 explicitly places the Eye of Horus in protection of the person on the water.',
            'SOBEK_TO_HORUS': 'BD113_CT158 explicitly makes Sobek lord of the marsh assist in recovering the scattered hands of Horus.',
            'DIRECT_SOBEK_TO_CROCODILE_REPELLING': 'NOT_OBSERVED_IN_STRICT_FULL_PASSAGE_SAMPLE'
        },
        'interpretation': {
            'primary': 'In the six strict full-passage witnesses, no text both names Sobek and explicitly uses him to repel crocodiles. The anti-crocodile/aquatic-danger lane instead contains Horus and the Eye of Horus, while Sobek appears in transformation, mythic cooperation and water/power contexts.',
            'model': 'The current sample therefore favors PARALLEL_BUT_CONNECTED_SYSTEMS over a simple SOBEK_COMMANDS_CROCODILES model. The strongest observed connector is Horus/Wedjat and shared water/power context, not an explicit ritual command from Sobek to crocodiles.',
            'limit': 'This is a targeted source-audited corpus, not an exhaustive census. Zero observed direct overlap cannot establish that no such Sobek-based crocodile-repelling text ever existed.'
        },
        'next_gate': {
            'id': 'SOBEK_CROCODILE_RITUAL_COEXISTENCE_PRIMARY_TEXT_R2',
            'requirements': [
                'expand to at least 30 independently located Egyptian textual witnesses',
                'separate funerary, healing, temple/cult, literary and administrative genres',
                'freeze search terms and admission rules before reading candidate outcomes',
                'include at least 10 crocodile-repelling or crocodile-danger texts and 10 explicit Sobek cult/identity texts',
                'record exact text locator, date range, provenance and translation edition',
                'score explicit Sobek plus crocodile-control co-occurrence without semantic inference',
                'hold out one genre or chronological group before estimating overlap'
            ]
        },
        'claim_firewall': ledger['claim_firewall'] + [
            'NO_STATISTICAL_INDEPENDENCE_CLAIM_FROM_SIX_CURATED_FULL_PASSAGE_WITNESSES',
            'NO_SOBEK_COMMANDS_CROCODILES_CLAIM_WITHOUT_EXPLICIT_TEXT'
        ]
    }

    expected = {
        'eligible_witnesses': 6,
        'sobek_named': 3,
        'crocodile_repelling_explicit': 2,
        'sobek_and_crocodile_repelling_same_witness': 0,
        'sobek_named_without_crocodile_repelling': 3,
        'crocodile_repelling_without_sobek_named': 2,
        'neither': 1,
        'horus_named': 3,
        'wedjat_or_eye_of_horus_named': 1,
        'sobek_horus_positive_cooperation': 1,
        'horus_or_wedjat_in_defensive_lane': 2
    }
    if result['strict_full_passage_counts'] != expected:
        raise SystemExit(f'Frozen count mismatch: {result["strict_full_passage_counts"]!r} != {expected!r}')

    text = json.dumps(result, indent=2, ensure_ascii=False) + '\n'
    if args.out:
        Path(args.out).write_text(text, encoding='utf-8')
    print(text, end='')


if __name__ == '__main__':
    main()
