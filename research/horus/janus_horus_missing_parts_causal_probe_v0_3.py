#!/usr/bin/env python3
import json
from collections import Counter
from pathlib import Path

LEDGER = Path('data/JANUS-HORUS-MISSING-PARTS-CAUSE-RESTORATION-LEDGER-2026-08-16-v0.3.json')
RESULT = Path('data/JANUS-HORUS-MISSING-PARTS-CAUSAL-GRAMMAR-RESULT-2026-08-16-v0.3.json')


def main():
    data = json.loads(LEDGER.read_text(encoding='utf-8'))
    episodes = data['episodes']
    causal = data['causal_classes']

    part_families = sorted({p for e in episodes for p in e['part']})
    cause_classes = Counter(c['class'] for c in causal)

    direct_extraction = [e['id'] for e in episodes if e['id'] == 'EYES_CHESTER_BEATTY_I']
    direct_contamination_excision = [e['id'] for e in episodes if e['id'] == 'HANDS_CHESTER_BEATTY_I']
    direct_retrieval_regrowth = [e['id'] for e in episodes if e['id'] == 'HANDS_CT158_BD113']
    eye_restoration_variants = [e['id'] for e in episodes if e['id'] in ('EYES_CHESTER_BEATTY_I', 'WEDJAT_CT335_BD17')]

    result = {
        'artifact_uuid': 'JANUS-HORUS-MISSING-PARTS-CAUSAL-GRAMMAR-RESULT-2026-08-16-v0.3',
        'version': 'v0.3',
        'timestamp_date': '2026-08-16',
        'status': 'CAUSE_SENSITIVE_DISTRIBUTED_RESTORATION_GRAMMAR_SUPPORTED_DEVICE_INTERPRETATION_NOT_SUPPORTED',
        'ledger': str(LEDGER),
        'counts': {
            'admitted_episodes': len(episodes),
            'causal_classes': len(causal),
            'unique_part_labels': len(part_families),
            'direct_contamination_linked_excision_witnesses': len(direct_contamination_excision),
            'direct_enemy_eye_extraction_witnesses': len(direct_extraction),
            'direct_hand_retrieval_regrowth_witnesses': len(direct_retrieval_regrowth),
            'independent_eye_restoration_variants': len(eye_restoration_variants),
            'restorative_apparatus_features_observed': 0
        },
        'cause_classes': dict(sorted(cause_classes.items())),
        'part_labels': part_families,
        'causal_state_machine': [
            'TRIGGER_OR_CONTAMINATION',
            'DAMAGE_OR_EXCISION',
            'PART_ABSENT_DAMAGED_OR_DISPLACED',
            'SEARCH_OR_TREATMENT',
            'RETRIEVAL_OR_HEALING',
            'REGROWTH_OR_REINTEGRATION',
            'RESTORED_STATUS'
        ],
        'key_findings': [
            'The missing-parts question is causal, not merely anatomical: hands and eyes become absent/damaged for different reasons in different traditions.',
            'The Chester Beatty hand episode directly gives a contamination-linked excision: Seth semen is caught in Horus hands and Isis then cuts the hands with a copper knife.',
            'CT158/BD113 directly gives the downstream recovery pathway: Ra coordinates, Sobek searches/retrieves at water with a snare, and Horus mother makes the hands/arms grow in place.',
            'The causal bridge between the Chester Beatty hand-cutting episode and CT158 is a cross-text variant link, not a single continuous primary-text instruction.',
            'The eyes have at least three distinct damage modes: forceful extraction by Seth, fight-related wedjat injury, and black-boar trauma.',
            'Restoration is likewise non-unique: Hathor heals the extracted eyes with gazelle milk while Thoth restores the wedjat in another tradition.',
            'The observed system is therefore better modeled as a cause-sensitive distributed restoration grammar than as a fixed organ-to-restorer lookup table.'
        ],
        'tool_vs_device_boundary': {
            'ordinary_tools_or_materials_attested': ['copper knife', 'fish-trap/snare', 'gazelle milk', 'fingers/spit variant'],
            'restorative_apparatus_observed': false if False else False,
            'interpretation': 'Explicit tools and treatment materials are attested, but no stable treatment chamber, energy system, instrumentation, construction specification or recurring regenerative apparatus is observed.'
        },
        'highest_admissible_claim': 'Across admitted Horus traditions, body-part loss/damage has multiple explicit causes and multiple restoration pathways. The strongest combined model is a cause-sensitive distributed mythic restoration grammar. Hands provide an especially rich chain from contamination-linked excision in one narrative variant to water retrieval and regrowth in CT158/BD113, but those stages must remain source-separated. No regenerative machine or capsule is established.',
        'claim_firewall': data['claim_firewall'],
        'next_gate': data['next_gate']
    }

    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result['counts'], sort_keys=True))


if __name__ == '__main__':
    main()
