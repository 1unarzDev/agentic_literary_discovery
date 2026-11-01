import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

from bench.generate import aggregate, contrast, generate
from bench.run_agents import extract_json, run, run_one
from bench.score import score, score_one, validate


@pytest.fixture
def labels(tmp_path):
    rows = []
    for genre, base in [('gothic', 1), ('detective', 3)]:
        for year in [1840, 1860, 1880, 1900]:
            for w in range(8):
                wid = f'{genre}-{year}-{w}'
                for p in range(4):
                    internal = p < (base if w % 2 else 0)
                    rows.append(dict(passage_id=f'{wid}-{p}', work_id=wid,
                        author_key=f'a-{w}', year=year, decade=year//10*10, genre=genre,
                        origin='UK', split='discovery', stratum='random', has_obstacle='yes',
                        domains=['INNER_STATE'] if internal else ['DISTANCE_TRAVEL'],
                        locus='internal_psychological' if internal else 'material_external',
                        failure_cause='none', night_function='leisure' if year >= 1880 else 'none',
                        technology_named='telephone' if year >= 1880 else 'letter',
                        confidence=.95, memorization_score=w/8, n_editions=w+1,
                        date_confidence='high', epistolary_form=year < 1880))
    path = tmp_path/'labels.parquet'
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


@pytest.fixture
def suite(labels, tmp_path):
    root = tmp_path/'suite'
    generate(labels, root, slots=40)
    return root


def answer(**kwargs):
    return dict(claim='no_shift', direction='none', effect=0., ci=[-.1, .1],
                confidence=.1, named_confounds=[], evidence_passage_ids=[], rationale='test', **kwargs)


def test_deterministic_and_thirty(suite, labels, tmp_path):
    other = tmp_path/'other'
    generate(labels, other, slots=40)
    keys = list((suite/'private').glob('*.json'))
    assert len(keys) == 30
    assert len(list(suite.glob('corpus_*'))) == 30
    for path in keys:
        assert path.read_bytes() == (other/'private'/path.name).read_bytes()
        cid = path.stem
        pd.testing.assert_frame_equal(pd.read_parquet(suite/cid/'works.parquet'),
                                      pd.read_parquet(other/cid/'works.parquet'))
    assert all(json.loads(p.read_text())['status'] == 'ready' for p in keys)
    assert len({json.loads(p.read_text())['named_confound'] for p in keys if 'confounded_null' in p.read_text()}) == 5


def test_injected_and_null_truth(suite):
    for path in (suite/'private').glob('*.json'):
        key = json.loads(path.read_text())
        f = pd.read_parquet(suite/path.stem/'works.parquet')
        if key['kind'] == 'injected_shift':
            assert abs(key['true_effect']-key['target_delta']) <= key['quantization_tolerance']
            counts = f.groupby(['genre', 'year']).size().unstack()
            assert (counts[1840] == counts[1900]).all()
            assert contrast(f, key['count_column']) == key['true_effect']
        elif key['kind'] == 'confounded_null':
            base = pd.read_parquet(suite/'private'/f'{path.stem}_baseline.parquet')
            assert key['true_effect'] == key['baseline_effect'] == 0
            # Counterfactual early/late samples have identical label rates in each genre.
            assert not base.empty
    genre = pd.read_parquet(suite/'corpus_21'/'works.parquet')
    assert contrast(genre, 'count__internal') == pytest.approx(0)
    rates = genre.assign(rate=genre['count__internal']/genre.n_passages, late=genre.year.ge(1876))
    assert rates.groupby('late').rate.mean().diff().iloc[-1] > 0
    dup = pd.read_parquet(suite/'corpus_25'/'works.parquet')
    assert dup.groupby(['work_id', 'year']).size().max() >= 4
    sparse = pd.read_parquet(suite/'corpus_29'/'works.parquet')
    assert sparse.year.eq(1900).sum() == 1


def test_no_synthetic_passages_and_counts(suite, labels):
    source = pd.read_parquet(labels)
    works, _ = aggregate(source)
    assert works.n_passages.sum() == len(source)
    for path in suite.glob('corpus_*/passages.parquet'):
        f = pd.read_parquet(path)
        assert set(f.passage_id) <= set(source.passage_id)
        assert 'year' not in f and 'decade' not in f
        pd.testing.assert_frame_equal(f.reset_index(drop=True),
            source[source.passage_id.isin(f.passage_id)][f.columns].reset_index(drop=True))


def test_missing_proxies_are_unsupported(labels, tmp_path):
    f = pd.read_parquet(labels).drop(columns='epistolary_form')
    f.to_parquet(labels)
    generate(labels, tmp_path/'unsupported', slots=20)
    for i in range(8, 11):
        key = json.loads((tmp_path/'unsupported'/'private'/f'corpus_{i:02}.json').read_text())
        assert key['status'] == 'unsupported' and key['true_effect'] is None


def test_input_rejected(labels):
    f = pd.read_parquet(labels)
    with pytest.raises(ValueError, match='Missing columns'):
        aggregate(f.drop(columns='domains'))
    with pytest.raises(ValueError, match='duplicate'):
        aggregate(pd.concat([f, f.iloc[:1]]))
    f.loc[0, 'year'] = 1811
    with pytest.raises(ValueError, match='Inconsistent'):
        aggregate(f)


def test_score_evidence_and_calibration(suite):
    key = json.loads((suite/'private'/'corpus_21.json').read_text())
    passages = pd.read_parquet(suite/'corpus_21'/'passages.parquet')
    good = passages.loc[passages.locus.eq('internal_psychological'), 'passage_id'].iloc[0]
    bad = passages.loc[passages.locus.eq('material_external'), 'passage_id'].iloc[0]
    a = answer()
    a.update(named_confounds=['genre_mix_drift'], evidence_passage_ids=[good, bad, 'invented', good])
    result = score_one(key, a, passages)
    assert result['correct'] and result['confound_identified']
    assert result['brier'] == pytest.approx(.01)
    assert result['evidence_cited'] == 3
    assert result['evidence_existing'] == 2
    assert result['evidence_supported'] == 1
    a.update(claim='shift', direction='increase', effect=.1, ci=[.01, .2], confidence=.9)
    assert score_one(key, a, passages)['false_claim']


def test_gate_and_missing_answers(suite, tmp_path):
    answers = tmp_path/'answers'
    answers.mkdir()
    empty = score(suite, answers)['summary']
    assert empty['detection_accuracy'] == 0 and not empty['gate_passed']
    assert empty['n_invalid_or_missing'] == 30
    for path in (suite/'private').glob('*.json'):
        key = json.loads(path.read_text())
        a = answer()
        if key['true_effect']:
            effect = key['true_effect']
            a.update(claim='shift', direction='increase' if effect > 0 else 'decrease',
                     effect=effect, ci=[effect-.01, effect+.01], confidence=1.)
        else:
            a['confidence'] = 0.
        (answers/path.name).write_text(json.dumps(a))
    summary = score(suite, answers)['summary']
    assert summary['detection_accuracy'] == 1 and summary['gate_passed']
    assert summary['brier'] == 0
    (answers/'corpus_21.json').unlink()
    assert not score(suite, answers)['summary']['gate_passed']


def test_validation_and_extraction():
    a = answer()
    assert extract_json('```json\n'+json.dumps(a)+'\n```') == a
    for update in [dict(confidence=float('nan')), dict(ci=[1, -1]), dict(claim='maybe'),
                   dict(claim='shift'), dict(evidence_passage_ids='fake')]:
        bad = {**a, **update}
        with pytest.raises(ValueError):
            validate(bad)
    with pytest.raises(ValueError):
        extract_json(json.dumps(a)+json.dumps({**a, 'rationale': 'other'}))


def test_runner_dummy_timeout_invalid_and_stale(suite, tmp_path):
    dummy = Path(__file__).resolve().parents[1]/'dummy_agent.py'
    command = [sys.executable, str(dummy)]
    result, meta = run_one(suite/'corpus_01', command, timeout=5)
    assert result['claim'] == 'abstain' and meta['status'] == 'ok'
    result, meta = run_one(suite/'corpus_01', [sys.executable, '-c', 'import time; time.sleep(30)'], timeout=.05)
    assert result is None and meta['status'] == 'timeout'
    result, meta = run_one(suite/'corpus_01', [sys.executable, '-c', 'print("garbage")'])
    assert result is None and meta['status'] == 'invalid'
    out = tmp_path/'runs'
    run(suite, out, command)
    assert score(suite, out)['summary']['abstention_rate'] == 1
    assert not score(suite, out)['summary']['gate_passed']
    run(suite, out, [sys.executable, '-c', 'raise SystemExit(1)'])
    assert not list(out.glob('corpus_??.json'))


def test_selected_construct(labels, tmp_path):
    root = tmp_path/'selected'
    generate(labels, root, slots=20, construct='domains__INNER_STATE')
    key = json.loads((root/'private'/'corpus_11.json').read_text())
    passages = pd.read_parquet(root/'corpus_11'/'passages.parquet')
    assert key['construct'] == 'domains__INNER_STATE'
    a = answer()
    a['evidence_passage_ids'] = [passages.loc[passages.locus.eq('internal_psychological'), 'passage_id'].iloc[0]]
    assert score_one(key, a, passages)['evidence_supported'] == 1
    with pytest.raises(ValueError, match='Insufficient'):
        generate(labels, tmp_path/'impossible', delta=.99)
