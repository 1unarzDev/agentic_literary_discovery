"""Generate blinded work-level corpora; never synthesize passage text."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED = ('passage_id work_id author_key decade year genre origin split stratum '
            'has_obstacle domains locus failure_cause night_function technology_named '
            'confidence memorization_score n_editions date_confidence').split()
CATEGORICAL = ['has_obstacle', 'locus', 'failure_cause', 'night_function', 'technology_named']
CONFOUNDS = ['genre_mix_drift', 'reprint_date_contamination', 'duplicate_edition_amplification',
             'memorized_canon_oversampling', 'sparse_decade']


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def aggregate(labels):
    missing = set(REQUIRED) - set(labels)
    if missing:
        raise ValueError(f'Missing columns: {sorted(missing)}')
    labels = labels.copy()
    if labels[REQUIRED[:9]].isna().any().any() or labels.passage_id.duplicated().any():
        raise ValueError('Missing identifiers/metadata or duplicate passage IDs')
    labels['passage_id'] = labels.passage_id.astype(str)
    if labels.passage_id.duplicated().any():
        raise ValueError('duplicate passage IDs after string conversion')
    for col in ['year', 'decade', 'memorization_score', 'n_editions']:
        if not np.isfinite(pd.to_numeric(labels[col], errors='coerce')).all():
            raise ValueError(f'Invalid numeric {col}')
    for col in ['author_key', 'year', 'decade', 'genre', 'origin', 'split', 'stratum']:
        if labels.groupby('work_id')[col].nunique(dropna=False).gt(1).any():
            raise ValueError(f'Inconsistent work metadata: {col}')
    def domain_list(x):
        if isinstance(x, str):
            x = json.loads(x)
        if not isinstance(x, (list, tuple, np.ndarray)):
            raise ValueError('domains must be a list')
        return list(x)
    labels['domains'] = labels.domains.map(domain_list)
    flags = {}
    for col in CATEGORICAL:
        for value in sorted(labels[col].dropna().astype(str).unique()):
            flags[f'count__{col}__{value}'] = labels[col].astype(str).eq(value)
    for value in sorted({v for values in labels.domains for v in values}):
        flags[f'count__domains__{value}'] = labels.domains.map(lambda x: value in x) & labels.has_obstacle.eq('yes')
    flags['count__telephone'] = labels.technology_named.eq('telephone')
    flags['count__night'] = labels.night_function.notna() & ~labels.night_function.eq('none')
    flags['count__internal'] = labels.has_obstacle.eq('yes') & labels.locus.eq('internal_psychological')
    if 'epistolary_form' in labels:
        flags['count__epistolary'] = labels.epistolary_form.isin([True, 1, 'yes'])
    counts = pd.DataFrame(flags).astype(int)
    counts['work_id'] = labels.work_id
    works = labels.groupby('work_id', sort=True)[
        ['author_key', 'year', 'decade', 'genre', 'origin', 'split', 'stratum',
         'memorization_score', 'n_editions', 'date_confidence']].first()
    works = works.join(counts.groupby('work_id').sum())
    works['n_passages'] = labels.groupby('work_id').size()
    works['passage_ids'] = labels.groupby('work_id').passage_id.agg(list)
    # Pointers resolve against the original labels/text store; no fabricated text.
    works['sample_passage_ids'] = works.passage_ids.map(lambda x: x[:5])
    return works.reset_index(), labels


def contrast(frame, count, cutoff=1876):
    """Equal-work rates, late minus early, standardized to equal genre weights."""
    f = frame.assign(rate=frame[count] / frame.n_passages, late=frame.year >= cutoff)
    cells = f.groupby(['genre', 'late']).rate.mean().unstack()
    if False not in cells or True not in cells or cells.isna().any().any():
        return None
    return float((cells[True] - cells[False]).mean())


def dated(frame, year):
    f = frame.copy()
    f['year'], f['decade'] = year, year // 10 * 10
    return f


def inject(works, count, delta, slots, rng):
    """Mix actual low/high works within every genre; quantization <= 1/slots."""
    early, late = [], []
    for _, g in works.groupby('genre', sort=True):
        rates = g[count] / g.n_passages
        low, high = g.loc[rates.eq(rates.min())], g.loc[rates.eq(rates.max())]
        span = float(rates.max() - rates.min())
        if span < abs(delta):
            raise ValueError(f'Insufficient within-genre support for delta={delta}')
        k = round(abs(delta) / span * slots)
        a = low.iloc[rng.integers(len(low), size=slots)].reset_index(drop=True)
        b = pd.concat([low.iloc[rng.integers(len(low), size=slots-k)],
                       high.iloc[rng.integers(len(high), size=k)]], ignore_index=True)
        if delta < 0:
            a, b = b, a
        early.append(dated(a, 1840))
        late.append(dated(b, 1900))
    return pd.concat(early + late, ignore_index=True)


def null_corpus(works, count, confound, rng, slots):
    baseline = pd.concat([g.iloc[rng.integers(len(g), size=slots)]
                          for _, g in works.groupby('genre', sort=True)], ignore_index=True)
    early, late = dated(baseline, 1840), dated(baseline, 1900)
    f = pd.concat([early, late], ignore_index=True)
    rate = f[count] / f.n_passages
    is_late = f.year.ge(1876)
    if confound == 'genre_mix_drift':
        means = baseline.groupby('genre').apply(lambda g: (g[count]/g.n_passages).mean(), include_groups=False)
        if len(means) < 2 or means.max() == means.min():
            raise ValueError('Genre drift requires distinct genre base rates')
        mask = (is_late & f.genre.eq(means.idxmax())) | (~is_late & f.genre.eq(means.idxmin()))
        f = pd.concat([f, f[mask], f[mask], f[mask]], ignore_index=True)
    elif confound == 'reprint_date_contamination':
        mask = ~is_late & rate.gt(rate.median())
        f.loc[mask, ['year', 'decade']] = [1900, 1900]
    elif confound == 'duplicate_edition_amplification':
        mask = is_late & rate.gt(rate.median())
        f = pd.concat([f, f[mask], f[mask], f[mask]], ignore_index=True)
    elif confound == 'memorized_canon_oversampling':
        mask = is_late & f.memorization_score.ge(f.memorization_score.quantile(.75))
        f = pd.concat([f, f[mask], f[mask], f[mask]], ignore_index=True)
    else:
        f = pd.concat([early, late.iloc[[int(rng.integers(len(late)))]]], ignore_index=True)
    if f.equals(pd.concat([early, late], ignore_index=True)):
        raise ValueError(f'Cannot plant {confound} with available support')
    return f, baseline


def generate(labels_path, output, seed=1729, delta=.2, slots=100, construct='internal'):
    if not 0 < delta <= 1 or slots < 2:
        raise ValueError('delta must be in (0,1]; slots >= 2')
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output must be empty (prevent stale keys/corpora)')
    works, labels = aggregate(pd.read_parquet(labels_path))
    output.mkdir(parents=True, exist_ok=True)
    (output/'private').mkdir(mode=0o700)
    rng = np.random.default_rng(seed)
    specs = [('known_positive', x, None) for x in ['telephone']*4+['night']*3+['epistolary']*3]
    if f'count__{construct}' not in works:
        raise ValueError(f'Unknown injected construct: {construct}')
    specs += [('injected_shift', construct, None)]*10
    specs += [('confounded_null', 'internal', c) for c in CONFOUNDS for _ in range(2)]
    source_sha256 = hashlib.sha256(Path(labels_path).read_bytes()).hexdigest()
    manifest = []
    for i, (kind, construct, confound) in enumerate(specs):
        corpus_id = f'corpus_{i+1:02d}'
        count = f'count__{construct}'
        status, reason, truth = 'ready', None, None
        baseline = None
        cutoff = 1880 if construct == 'night' else 1876
        if kind == 'known_positive':
            f = works.iloc[rng.integers(len(works), size=len(works))].copy()
            expected = -1 if construct == 'epistolary' else 1
            effect = contrast(f, count, cutoff) if count in f else None
            if effect is None or effect * expected <= 0:
                status, reason = 'unsupported', 'Missing construct or unverified expected historical contrast'
            else:
                truth = effect
        elif kind == 'injected_shift':
            signed_delta = delta if i % 2 == 0 else -delta
            f = inject(works, count, signed_delta, slots, rng)
            truth = contrast(f, count)
        else:
            f, baseline = null_corpus(works, count, confound, rng, slots)
            truth = 0.0
        f = f.reset_index(drop=True)
        f['row_id'] = [f'{corpus_id}_{j:06d}' for j in range(len(f))]
        public = output/corpus_id
        public.mkdir()
        f.to_parquet(public/'works.parquet', index=False)
        csv = f.copy()
        for col in ['passage_ids', 'sample_passage_ids']:
            csv[col] = csv[col].map(json.dumps)
        csv.to_csv(public/'works.csv', index=False)
        ids = {p for values in f.passage_ids for p in values}
        evidence = labels[labels.passage_id.isin(ids)].copy()
        # All selected IDs, including support labels, are available for evidence verification.
        evidence = evidence.drop(columns=['year', 'decade'])
        evidence.to_parquet(public/'passages.parquet', index=False)
        task = {'corpus_id': corpus_id, 'construct': construct, 'count_column': count,
                'denominator': 'n_passages', 'cutoff_year': cutoff,
                'estimand': 'equal-genre mean of equal-work late-minus-early passage rates'}
        dump(public/'task.json', task)
        observed = contrast(f, count, cutoff) if count in f else None
        key = {**task, 'kind': kind, 'seed': seed, 'status': status, 'reason': reason,
               'true_effect': truth, 'observed_effect': observed, 'named_confound': confound,
               'target_delta': signed_delta if kind == 'injected_shift' else None,
               'quantization_tolerance': 1/slots,
               'generating_process': 'paired genre baseline followed by artifact' if confound else
                   ('within-genre low/high work mixtures with reassigned dates' if kind == 'injected_shift' else
                    'bootstrap of dated works; directional screen; empirical control, not historical proof'),
               'baseline_effect': 0.0 if confound else None,
               'source_sha256': source_sha256}
        if baseline is not None:
            baseline.to_parquet(output/'private'/f'{corpus_id}_baseline.parquet', index=False)
        dump(output/'private'/f'{corpus_id}.json', key)
        manifest.append({'corpus_id': corpus_id})
    dump(output/'manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('labels'); p.add_argument('output')
    p.add_argument('--seed', type=int, default=1729)
    p.add_argument('--delta', type=float, default=.2)
    p.add_argument('--slots', type=int, default=100)
    p.add_argument('--construct', default='internal', help='Injected count suffix, e.g. domains__INNER_STATE')
    a = p.parse_args()
    generate(a.labels, a.output, a.seed, a.delta, a.slots, a.construct)
