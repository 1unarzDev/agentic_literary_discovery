import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

from bench.generate import aggregate, contrast, generate
from bench.run_agents import extract_json, run, run_one
from bench.score import score, score_one, validate


@pytest.fixture(scope='module')
def labels(tmp_path_factory):
    root = tmp_path_factory.mktemp('source')
    rows = []
    for genre in ['gothic', 'detective']:
        for year in range(1800, 1926):
            for w in range(4):
                wid = f'pg-{genre}-{year}-{w}'
                for p in range(2):
                    target = w < (3 if year < 1876 else 1)
                    rows.append(dict(passage_id=f'{wid}-{p}', work_id=wid,
                        author_key=f'Famous Author {year}-{w}', year=year, decade=year//10*10,
                        genre=genre, origin='UK' if w%2 else 'US', split='discovery',
                        stratum='random', has_obstacle='yes',
                        domains=['SOCIAL_RANK_CONVENTION'] if target else ['INNER_STATE'],
                        locus='social_institutional' if target else 'internal_psychological',
                        failure_cause='none', night_function='none', technology_named='none',
                        confidence=.95, memorization_score=0., n_editions=w+1,
                        date_confidence='high' if w%2 else 'low', title='An Identifiable Title',
                        text='Identifying quote from a novel', evidence_quote='Name',
                        pg_id=1234, source_path='/source/pg1234.txt'))
    path = root/'labels.parquet'
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


@pytest.fixture(scope='module')
def suite(labels, tmp_path_factory):
    root = tmp_path_factory.mktemp('suite')/'generated'
    generate(labels, root)
    return root


def keys(suite):
    return [json.loads((suite/'private'/f"{x['corpus_id']}.json").read_text())
            for x in json.loads((suite/'manifest.json').read_text())]


def find_key(suite, kind, confound=None):
    return next(k for k in keys(suite) if k['kind'] == kind and
                (confound is None or k['named_confound'] == confound))


def answer(**kwargs):
    return dict(claim='no_shift', direction='none', effect=0., ci=[-.1, .1],
                confidence=.1, named_confounds=[], evidence_passage_ids=[], rationale='test', **kwargs)


def test_deterministic_and_thirty(suite, labels, tmp_path):
    other = tmp_path/'other'
    generate(labels, other)
    assert len(keys(suite)) == 30
    assert len(list(suite.glob('corpus_*'))) == 30
    for key in keys(suite):
        cid = key['corpus_id']
        assert (suite/'private'/f'{cid}.json').read_bytes() == (other/'private'/f'{cid}.json').read_bytes()
        assert (suite/cid/'works.parquet').read_bytes() == (other/cid/'works.parquet').read_bytes()
    assert all(k['status'] == 'ready' for k in keys(suite))
    assert [k['kind'] for k in keys(suite)] != sorted(k['kind'] for k in keys(suite))


def test_injected_and_null_truth(suite):
    for key in keys(suite):
        f = pd.read_parquet(suite/key['corpus_id']/'works.parquet')
        assert f.work_id.is_unique
        assert f.groupby('work_id').year.nunique().max() == 1
        if key['kind'] == 'injected_shift':
            assert abs(key['true_effect']-key['target_delta']) <= key['quantization_tolerance']+1e-12
            assert contrast(f, key['count_column']) == key['true_effect']
        elif key['kind'] == 'confounded_null':
            base = pd.read_parquet(suite/'private'/f"{key['corpus_id']}_baseline.parquet")
            assert key['true_effect'] == key['baseline_expected_effect'] == 0
            assert key['baseline_effect'] == contrast(base, key['count_column'])
            assert base.work_id.is_unique
        else:
            assert abs(key['true_effect']) >= .03


def test_no_identifying_metadata_or_synthetic_passages(suite, labels):
    source = pd.read_parquet(labels).set_index('passage_id')
    for key in keys(suite):
        cid = key['corpus_id']
        mapping = json.loads((suite/'private'/f'{cid}_mapping.json').read_text())
        reverse = {v:k for k,v in mapping['passage_id'].items()}
        f = pd.read_parquet(suite/cid/'passages.parquet')
        assert not set(['year','decade','text','title','author_key','pg_id','source_path','evidence_quote','split','stratum']) & set(f)
        assert f.passage_id.str.fullmatch(r'p[0-9]{6}').all()
        w = pd.read_parquet(suite/cid/'works.parquet')
        assert w.work_id.str.fullmatch(r'w[0-9]{6}').all()
        assert w.author_key.str.fullmatch(r'a[0-9]{6}').all()
        assert w.n_passages.eq(1).all() and len(f) == len(w)
        for row in f.itertuples():
            original = source.loc[reverse[row.passage_id]]
            assert list(row.domains) == list(original.domains)
            assert row.locus == original.locus
        assert set(p for ids in w.passage_ids for p in ids) == set(f.passage_id)


def test_structure_classifier_and_year_distribution(suite):
    from bench.leak_audit import features, classifier_accuracy, audit
    x, y = features(suite)
    assert audit(suite)['varying_features'] == []
    assert classifier_accuracy(x, y) <= 1/3 + 1e-12
    # Verify the audit has power to catch a deliberately restored size leak.
    leaky = x.copy()
    leaky['rows'] = pd.Categorical(y).codes*100+100
    assert classifier_accuracy(leaky, y) > .9
    reference = None
    for key in keys(suite):
        f = pd.read_parquet(suite/key['corpus_id']/'works.parquet')
        histogram = f.year.value_counts().sort_index()
        assert len(histogram) == 126 and histogram.index.min() == 1800 and histogram.index.max() == 1925
        if reference is not None:
            pd.testing.assert_series_equal(histogram, reference)
        reference = histogram


def test_weak_controls_dropped_and_missing_rejected(labels, tmp_path):
    from bench.generate import verify_controls
    w, _ = aggregate(pd.read_parquet(labels))
    reports = verify_controls(w)
    assert not next(r for r in reports if r['construct'] == 'telephone')['ready']
    assert next(r for r in reports if r['construct'] == 'domains__SOCIAL_RANK_CONVENTION')['ready']
    with pytest.raises(ValueError, match='No verified'):
        generate(labels, tmp_path/'weak', construct='telephone')
    assert not (tmp_path/'weak').exists()


def test_prompt_has_no_checklist():
    from bench.generate import CONFOUNDS
    prompt = (Path(__file__).resolve().parents[1]/'agent_task.md').read_text().lower()
    assert not any(c in prompt for c in CONFOUNDS)
    assert not any(c in prompt for c in ['memorization', 'reprint', 'duplicate', 'sparse', 'inspect genre', 'repeated editions'])
    assert 'alternative explanations' in prompt


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
    key = find_key(suite, 'confounded_null', 'genre_mix_drift')
    passages = pd.read_parquet(suite/key['corpus_id']/'passages.parquet')
    good = passages.loc[passages.locus.eq('social_institutional'), 'passage_id'].iloc[0]
    bad = passages.loc[passages.locus.eq('internal_psychological'), 'passage_id'].iloc[0]
    a = answer()
    a.update(named_confounds=['genre_mix_drift'], evidence_passage_ids=[good, bad, 'invented', good])
    result = score_one(key, a, passages)
    assert result['correct'] and result['confound_identified']
    freeform = {**a, 'named_confounds': ['Changing genre composition']}
    assert score_one(key, freeform, passages)['confound_identified']
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
    for key in keys(suite):
        path = Path(key['corpus_id']+'.json')
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
    (answers/(find_key(suite, 'confounded_null')['corpus_id']+'.json')).unlink()
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
    generate(labels, root, construct='domains__SOCIAL_RANK_CONVENTION')
    assert all(k['construct'] == 'domains__SOCIAL_RANK_CONVENTION' for k in keys(root))
    with pytest.raises(ValueError, match='Insufficient'):
        generate(labels, tmp_path/'impossible', delta=.99)


def test_confirmation_rejected(labels, tmp_path):
    f = pd.read_parquet(labels)
    f.loc[0, 'split'] = 'confirmation'
    path = tmp_path/'unsealed.parquet'
    f.to_parquet(path)
    with pytest.raises(ValueError, match='Only Discovery'):
        generate(path, tmp_path/'bad')


def test_adapter_discovery_pin_dedup_and_read_only(tmp_path):
    import duckdb
    import hashlib
    from bench.prepare import prepare
    database = tmp_path/'source.duckdb'
    works_path, genres_path, passages_path = [tmp_path/f'{name}.parquet'
                                             for name in ['works', 'genre', 'passages']]
    pd.DataFrame([
        dict(work_id='source1', pg_id=1, author_key='Real Name', year=1841,
             origin_locc='UK', n_editions=1, date_confidence='high', split='discovery'),
        dict(work_id='source2', pg_id=2, author_key='Other Name', year=1901,
             origin_locc='US', n_editions=1, date_confidence='high', split='confirmation'),
    ]).to_parquet(works_path)
    pd.DataFrame([dict(work_id=w,genre='novel') for w in ['source1','source2']]).to_parquet(genres_path)
    pd.DataFrame([dict(passage_id=p, work_id=w, stratum='random',split=split)
                  for p,w,split in [('pg1_p1','source1','discovery'),
                                     ('pg2_p1','source2','confirmation')]]).to_parquet(passages_path)
    rows = []
    for passage, created, pin, stage, twin, error, confidence in [
        ('pg1_p1','1','41ca3c7d-valid','label',False,None,.7),
        ('pg1_p1','2','41ca3c7d-valid','label',False,None,.9),
        ('pg1_p1','3','wrong-pin','label',False,None,.1),
        ('pg1_p1','4','41ca3c7d-valid','label',True,None,.2),
        ('pg1_p1','5','41ca3c7d-valid','other',False,None,.3),
        ('pg1_p1','6','41ca3c7d-valid','label',False,'failed',.4),
        ('pg2_p1','7','41ca3c7d-valid','label',False,None,.5),
    ]:
        rows.append(dict(passage_id=passage, created=created, pin_hash=pin, stage=stage,
                         is_dup_twin=twin, error=error, valid_schema=True,
                         output_json=json.dumps(dict(has_obstacle='no',confidence=confidence))))
    result_rows = pd.DataFrame(rows)
    with duckdb.connect(str(database)) as con:
        con.execute('create table results as select * from result_rows')
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    out = prepare(database, works_path, genres_path, passages_path, tmp_path/'labels.parquet')
    assert len(out) == 1 and out.iloc[0].confidence == .9
    assert out.iloc[0].domains == [] and out.split.eq('discovery').all()
    assert 'output_json' not in out and 'text' not in out
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_unverified_positive_is_generated_but_unscored(labels, tmp_path):
    root = tmp_path/'unverified'
    with pytest.raises(ValueError, match='No verified'):
        generate(labels, tmp_path/'strict', construct='domains__SOCIAL_RANK_CONVENTION', minimum_effect=.99)
    generate(labels, root, construct='domains__SOCIAL_RANK_CONVENTION', minimum_effect=.99,
             allow_unverified_positive=True)
    ks = keys(root)
    assert {k['status'] for k in ks if k['kind'] == 'known_positive'} == {'unsupported'}
    assert {k['status'] for k in ks if k['kind'] != 'known_positive'} == {'ready'}
    assert score(root, tmp_path/'none')['summary']['n_eligible'] == 20


def test_claude_stream_events_parsed(suite, tmp_path):
    from bench.run_agents import parse_events
    a = answer()
    events = [{'type': 'system', 'subtype': 'init', 'model': 'm-1', 'tools': ['Bash']},
              {'type': 'assistant', 'message': {'content': [
                  {'type': 'tool_use', 'name': 'Bash', 'input': {'command': 'python -c 1'}}]}},
              {'type': 'result', 'result': 'Here:\n```json\n'+json.dumps(a)+'\n```',
               'total_cost_usd': .1, 'usage': {'output_tokens': 5}, 'num_turns': 2}]
    final, summary = parse_events('\n'.join(map(json.dumps, events)))
    assert extract_json(final) == a
    assert summary['model'] == 'm-1' and summary['n_tool_calls'] == 1 and summary['total_cost_usd'] == .1
    script = tmp_path/'fake.py'
    script.write_text('import json,sys\n' + ''.join(f'print({json.dumps(json.dumps(e))})\n' for e in events))
    result, meta = run_one(suite/'corpus_01', [sys.executable, str(script)], timeout=20)
    assert result == a and meta['summary']['num_turns'] == 2
