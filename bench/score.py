"""Strict answer validation and benchmark scoring (missing runs remain in denominator)."""
import argparse
import json
import math
import re
from pathlib import Path

import pandas as pd


def validate(answer):
    required = {'claim', 'direction', 'effect', 'ci', 'named_confounds',
                'evidence_passage_ids', 'rationale', 'confidence'}
    if not isinstance(answer, dict) or not required <= answer.keys():
        raise ValueError('Missing required answer fields')
    if answer['claim'] not in ['shift', 'no_shift', 'abstain']:
        raise ValueError('Invalid claim')
    if answer['direction'] not in ['increase', 'decrease', 'none', 'unknown']:
        raise ValueError('Invalid direction')
    def number(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
    if not number(answer['confidence']) or not 0 <= answer['confidence'] <= 1:
        raise ValueError('confidence must be P(shift), in [0,1]')
    if answer['effect'] is not None and not number(answer['effect']):
        raise ValueError('Invalid effect')
    ci = answer['ci']
    if ci is not None and (not isinstance(ci, list) or len(ci) != 2 or
                           not all(number(x) for x in ci) or ci[0] > ci[1]):
        raise ValueError('Invalid CI')
    if ci is not None and answer['effect'] is not None and not ci[0] <= answer['effect'] <= ci[1]:
        raise ValueError('CI must contain reported effect')
    if answer['claim'] == 'shift':
        if answer['effect'] is None or ci is None or answer['effect'] == 0:
            raise ValueError('Shift requires nonzero effect and CI')
        if answer['direction'] != ('increase' if answer['effect'] > 0 else 'decrease'):
            raise ValueError('Direction/effect mismatch')
    for col in ['named_confounds', 'evidence_passage_ids']:
        if not isinstance(answer[col], list) or not all(isinstance(x, str) for x in answer[col]):
            raise ValueError(f'{col} must be strings')
    if not isinstance(answer['rationale'], str):
        raise ValueError('Invalid rationale')
    return answer


# Free-form explanations are allowed: these rules are a reproducible heuristic,
# with human adjudication still needed for headline confound-identification rates.
CONFOUND_TERMS = {
    'genre_mix_drift': [('genre', 'composition'), ('genre', 'mix')],
    'reprint_date_contamination': [('reprint',), ('dating', 'confidence'), ('date', 'confidence')],
    'edition_selection_bias': [('edition', 'selection'), ('edition', 'bias'), ('edition', 'amplification')],
    'prolific_author_selection': [('prolific', 'author'), ('author', 'oversampling')],
    'origin_composition_drift': [('origin', 'composition'), ('national', 'composition')],
}


def identifies_confound(key, answer):
    name = key.get('named_confound')
    if not name:
        return False
    if name in answer['named_confounds']:
        return True
    text = ' '.join(answer['named_confounds']+[answer['rationale']]).lower()
    words = set(re.findall(r'[a-z]+', text))
    return any(all(term in words for term in terms) for terms in CONFOUND_TERMS.get(name, []))


def score_one(key, answer, passages):
    try:
        validate(answer)
        valid = True
    except (ValueError, TypeError):
        valid = False
    ready = key['status'] == 'ready'
    truth = key['true_effect']
    shift = ready and truth != 0
    direction = 'increase' if shift and truth > 0 else 'decrease'
    correct = valid and ready and ((shift and answer['claim'] == 'shift' and
                                    answer['direction'] == direction) or
                                   (not shift and answer['claim'] == 'no_shift'))
    existing = set(passages.passage_id.astype(str))
    if key['count_column'] == 'count__internal':
        support = passages.has_obstacle.eq('yes') & passages.locus.eq('internal_psychological')
    elif key['construct'] == 'telephone':
        support = passages.technology_named.eq('telephone')
    elif key['construct'] == 'night':
        support = passages.night_function.notna() & ~passages.night_function.eq('none')
    elif key['construct'].startswith('domains__'):
        domain = key['construct'].split('__', 1)[1]
        def has_domain(value):
            return domain in (json.loads(value) if isinstance(value, str) else value)
        support = passages.has_obstacle.eq('yes') & passages.domains.map(has_domain)
    elif '__' in key['construct'] and key['construct'].split('__', 1)[0] in passages:
        field, value = key['construct'].split('__', 1)
        support = passages[field].astype(str).eq(value)
    elif 'epistolary_form' in passages and key['construct'] == 'epistolary':
        support = passages.epistolary_form.isin([True, 1, 'yes'])
    else:
        support = pd.Series(False, index=passages.index)
    supporting = set(passages.loc[support, 'passage_id'].astype(str))
    ids = set(answer['evidence_passage_ids']) if valid else set()
    return {'corpus_id': key['corpus_id'], 'kind': key['kind'], 'eligible': ready,
            'valid_answer': valid, 'correct': bool(correct),
            'false_claim': bool(valid and answer['claim'] == 'shift' and key['kind'] == 'confounded_null'),
            'confound_identified': bool(valid and identifies_confound(key, answer)),
            'abstained': bool(valid and answer['claim'] == 'abstain'),
            'brier': (answer['confidence'] - int(shift))**2 if valid and ready else None,
            'evidence_cited': len(ids), 'evidence_existing': len(ids & existing),
            'evidence_supported': len(ids & supporting),
            'ci_covers_truth': bool(valid and ready and answer['ci'] is not None and
                                    answer['ci'][0] <= truth <= answer['ci'][1])}


def score(root, answers):
    root, answers = Path(root), Path(answers)
    rows = []
    for item in json.loads((root/'manifest.json').read_text()):
        cid = item['corpus_id']
        key = json.loads((root/'private'/f'{cid}.json').read_text())
        try:
            answer = json.loads((answers/f'{cid}.json').read_text())
        except (OSError, ValueError):
            answer = None
        rows.append(score_one(key, answer, pd.read_parquet(root/cid/'passages.parquet')))
    eligible = [r for r in rows if r['eligible']]
    nulls = [r for r in eligible if r['kind'] == 'confounded_null']
    injected = [r for r in eligible if r['kind'] == 'injected_shift']
    def mean(values):
        return sum(values)/len(values) if values else None
    cited = sum(r['evidence_cited'] for r in rows)
    calibration = [r['brier'] for r in eligible if r['brier'] is not None]
    summary = {
        'n_total': len(rows), 'n_eligible': len(eligible),
        'n_unsupported': len(rows)-len(eligible),
        'n_invalid_or_missing': sum(not r['valid_answer'] for r in rows),
        'detection_accuracy': mean([r['correct'] for r in eligible]),
        'false_claim_rate': mean([r['false_claim'] for r in nulls]),
        'confound_identification_rate': mean([r['confound_identified'] for r in nulls]),
        'abstention_rate': mean([r['abstained'] for r in eligible]),
        'brier': mean(calibration), 'n_calibrated': len(calibration),
        'evidence_existence_rate': sum(r['evidence_existing'] for r in rows)/cited if cited else None,
        'evidence_validity_rate': sum(r['evidence_supported'] for r in rows)/cited if cited else None,
        'ci_coverage': mean([r['ci_covers_truth'] for r in eligible]),
        'gate_passed': len(injected) == 10 and len(nulls) == 10 and
                       all(r['valid_answer'] for r in injected+nulls) and
                       sum(r['correct'] for r in injected) >= 8 and
                       sum(r['false_claim'] for r in nulls) <= 1,
    }
    return {'summary': summary, 'corpora': rows}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root'); p.add_argument('answers'); p.add_argument('--output')
    a = p.parse_args()
    result = json.dumps(score(a.root, a.answers), indent=2, allow_nan=False)
    if a.output:
        Path(a.output).write_text(result+'\n')
    else:
        print(result)
