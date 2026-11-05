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
CONFOUNDS = ['genre_mix_drift', 'reprint_date_contamination', 'edition_selection_bias',
             'prolific_author_selection', 'origin_composition_drift']


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


# Candidate definitions were informed by exploratory Discovery inspection.
# Screening is recorded privately and is not independent historical validation.
CANDIDATES = ['domains__SOCIAL_RANK_CONVENTION', 'domains__COMMUNICATION_INFORMATION',
              'domains__DISTANCE_TRAVEL', 'telephone', 'night', 'internal']
PUBLIC_WORK = ['work_id', 'author_key', 'year', 'decade', 'genre', 'origin',
               'n_editions', 'date_confidence', 'n_passages', 'passage_ids', 'sample_passage_ids']
PUBLIC_PASSAGE = ['passage_id', 'work_id', 'has_obstacle', 'domains', 'locus',
                  'failure_cause', 'night_function', 'technology_named', 'confidence']


def verify_controls(works, minimum=.03, bootstrap=400, seed=8301):
    """Author-cluster percentile intervals; no claim of confirmatory inference."""
    rng = np.random.default_rng(seed)
    authors = works.author_key.unique()
    # Weighted cluster bootstrap retains every observed era/genre cell when possible.
    reports = []
    for target in CANDIDATES:
        count = f'count__{target}'
        effect = contrast(works, count) if count in works else None
        draws = []
        if effect is not None and abs(effect) >= minimum:
            rates = works.assign(rate=works[count]/works.n_passages, late=works.year.ge(1876))
            codes = pd.Categorical(rates.author_key, categories=authors).codes
            cells = list(rates.groupby(['genre', 'late']).indices.values())
            for _ in range(bootstrap):
                weights = rng.multinomial(len(authors), np.full(len(authors), 1/len(authors)))[codes]
                means = [np.average(rates.rate.iloc[ix], weights=weights[ix])
                         if weights[ix].sum() else np.nan for ix in cells]
                if np.isfinite(means).all():
                    draws.append(float(np.mean(np.asarray(means)[1::2]-np.asarray(means)[::2])))
        ci = np.quantile(draws, [.025, .975]).tolist() if len(draws) >= bootstrap*.9 else None
        ready = bool(effect is not None and abs(effect) >= minimum and ci and ci[0]*ci[1] > 0)
        reports.append(dict(construct=target, effect=effect, ci=ci, minimum_effect=minimum,
                            author_clusters=len(authors), bootstrap_draws=len(draws), ready=ready))
    return reports


def assign_dates(works, rng, count=None, delta=None, confound=None):
    """Permute the observed year multiset; never duplicate a source work.

    A null's target is the date-randomization expectation (zero), not an
    assertion that a finite random permutation has precisely zero contrast.
    """
    f = works.copy()
    if confound:
        # Dates are associated with a measured nuisance, rather than copying rows.
        # Keep the SAME marginal years and SAME work/author/label panel in every arm.
        if confound == 'genre_mix_drift':
            nuisance = f.groupby('genre')[count].transform('mean')
        elif confound == 'reprint_date_contamination':
            nuisance = f.date_confidence.astype(str).map({'high': 0, 'medium': 1, 'low': 2}).fillna(1)
        elif confound == 'edition_selection_bias':
            nuisance = f.n_editions
        elif confound == 'prolific_author_selection':
            nuisance = f.groupby('author_key').work_id.transform('size')
        else:
            nuisance = f.origin.map({v: i for i, v in enumerate(sorted(f.origin.unique()))})
        # Noise avoids deterministic blocks, while preserving nuisance association.
        # A noisy partial permutation retains both eras in every genre.
        score = nuisance.rank(pct=True).to_numpy() + rng.normal(0, .8, len(f))
        order = np.argsort(score)
        f.loc[f.index[order], 'year'] = np.sort(works.year.to_numpy())
    else:
        for _, ix in f.groupby('genre').groups.items():
            g = works.loc[ix]
            years = rng.permutation(g.year.to_numpy())
            if delta is not None:
                # One passage/work makes rates binary. Choose disjoint early/late
                # outcome quotas, with the nearest attainable requested effect.
                positive = rng.permutation(g.index[g[count].eq(1)])
                negative = rng.permutation(g.index[g[count].eq(0)])
                ne, nl = int((years < 1876).sum()), int((years >= 1876).sum())
                if not ne or not nl:
                    raise ValueError('Insufficient era support')
                k = round((len(positive)/nl-delta)/(1/ne+1/nl))
                lower, upper = max(0, ne-len(negative)), min(ne, len(positive))
                if not lower <= k <= upper:
                    raise ValueError(f'Insufficient within-genre support for delta={delta}')
                early = np.r_[positive[:k], negative[:ne-k]]
                late = np.r_[positive[k:], negative[ne-k:]]
                f.loc[early, 'year'] = rng.permutation(years[years < 1876])
                f.loc[late, 'year'] = rng.permutation(years[years >= 1876])
            else:
                f.loc[ix, 'year'] = years
    f['decade'] = f.year.astype(int)//10*10
    return f


def blind(frame, labels, rng):
    """Allowlist both tables. Free text, quotes, paths, PG IDs and dates are excluded."""
    f = frame.copy()
    mappings = {}
    for column, prefix in [('work_id', 'w'), ('author_key', 'a')]:
        values = rng.permutation(f[column].unique())
        mappings[column] = {v: f'{prefix}{j:06d}' for j, v in enumerate(values)}
    chosen = labels[labels.passage_id.isin({p for ps in f.passage_ids for p in ps})].copy()
    mappings['passage_id'] = {v: f'p{j:06d}' for j, v in enumerate(rng.permutation(chosen.passage_id))}
    evidence = chosen[PUBLIC_PASSAGE].copy()
    for column in ['work_id', 'author_key']:
        f[column] = f[column].map(mappings[column])
    for column in ['work_id', 'passage_id']:
        evidence[column] = evidence[column].map(mappings[column])
    for col in ['passage_ids', 'sample_passage_ids']:
        f[col] = f[col].map(lambda ids: [mappings['passage_id'][p] for p in ids])
    f = f[PUBLIC_WORK + sorted(c for c in f if c.startswith('count__'))]
    f = f.iloc[rng.permutation(len(f))].reset_index(drop=True)
    f['row_id'] = [f'r{j:06d}' for j in range(len(f))]
    evidence = evidence.reset_index(drop=True)
    return f, evidence, mappings


def generate(labels_path, output, seed=1729, delta=.05, construct='auto', minimum_effect=.03,
             allow_unverified_positive=False):
    if not 0 < delta <= 1 or not 0 < minimum_effect <= 1:
        raise ValueError('delta/minimum_effect must be in (0,1]')
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output must be empty (prevent stale keys/corpora)')
    labels = pd.read_parquet(labels_path)
    missing = set(REQUIRED) - set(labels)
    if missing:
        raise ValueError(f'Missing columns: {sorted(missing)}')
    if not labels.year.between(1800, 1925).all() or not labels.year.mod(1).eq(0).all():
        raise ValueError('Years must be integer publication dates in 1800–1925')
    if not labels.split.eq('discovery').all():
        raise ValueError('Only Discovery labels are allowed')
    # Validate source metadata before sampling. Strata may differ among passages.
    validation = labels.copy()
    validation['stratum'] = 'pooled'
    aggregate(validation)
    rng = np.random.default_rng(seed)
    # Fixed source panel for all arms: equal size AND identical dependence structure,
    # passage counts, label availability and marginal year distributions.
    labels = labels.iloc[rng.permutation(len(labels))].drop_duplicates('work_id').copy()
    works, labels = aggregate(labels)
    checks = verify_controls(works, minimum_effect, seed=seed)
    ready = [r for r in checks if r['ready'] and (construct == 'auto' or r['construct'] == construct)]
    positive_status = 'ready'
    if not ready and allow_unverified_positive and construct != 'auto':
        # Keep a pre-named target; its empirical replays are generated but NOT scored
        # (status 'unsupported'), so injected shifts and nulls carry the evaluation.
        ready = [r for r in checks if r['construct'] == construct and r['effect'] is not None]
        positive_status = 'unsupported'
    if not ready:
        raise ValueError('No verified sizable positive control; weak/missing controls dropped')
    selected = max(ready, key=lambda r: abs(r['effect']))
    construct = selected['construct']
    count = f'count__{construct}'
    # All arm types use the same target; task metadata cannot reveal the arm.
    specs = [('known_positive', None, None)]*10
    specs += [('injected_shift', None, delta if i%2 == 0 else -delta) for i in range(10)]
    specs += [('confounded_null', c, None) for c in CONFOUNDS for _ in range(2)]
    rng.shuffle(specs)
    # Check feasibility before creating partial output.
    assign_dates(works, np.random.default_rng(seed), count=count, delta=delta)
    assign_dates(works, np.random.default_rng(seed), count=count, delta=-delta)
    output.mkdir(parents=True, exist_ok=True)
    (output/'private').mkdir(mode=0o700)
    dump(output/'private'/'control_validation.json', {'candidates': checks, 'selected': selected,
         'interpretation': 'Exploratory finite-panel empirical contrast, not established historical causality',
         'replicates': 'Ten correlated blinded replays of one panel; not independent phenomena'})
    source_sha256 = hashlib.sha256(Path(labels_path).read_bytes()).hexdigest()
    manifest = []
    for i, (kind, confound, signed_delta) in enumerate(specs):
        cid = f'corpus_{i+1:02d}'
        baseline = assign_dates(works, rng)
        if kind == 'known_positive':
            frame = works.copy()
        elif kind == 'injected_shift':
            frame = assign_dates(works, rng, count=count, delta=signed_delta)
        else:
            frame = assign_dates(works, rng, count=count, confound=confound)
        effect = contrast(frame, count)
        truth = 0.0 if confound else effect
        f, evidence, mappings = blind(frame, labels, rng)
        public = output/cid
        public.mkdir()
        # Plain encodings keep storage-size side channels from permutation/RLE.
        parquet_options = dict(index=False, compression=None, use_dictionary=False, write_statistics=False)
        f.to_parquet(public/'works.parquet', **parquet_options)
        evidence.to_parquet(public/'passages.parquet', **parquet_options)
        csv = f.copy()
        for col in ['passage_ids', 'sample_passage_ids']:
            csv[col] = csv[col].map(json.dumps)
        csv.to_csv(public/'works.csv', index=False)
        task = dict(corpus_id=cid, construct=construct, count_column=count,
                    denominator='n_passages', cutoff_year=1876,
                    estimand='equal-genre mean of equal-work late-minus-early passage rates')
        dump(public/'task.json', task)
        tolerance = float(np.mean([1/g.year.lt(1876).sum()+1/g.year.ge(1876).sum()
                                  for _, g in works.groupby('genre')]))/2
        unsupported = kind == 'known_positive' and positive_status != 'ready'
        key = {**task, 'kind': kind, 'seed': seed,
               'status': 'unsupported' if unsupported else 'ready',
               'reason': 'empirical contrast failed screening; replay is descriptive only' if unsupported else None,
               'true_effect': truth, 'observed_effect': effect, 'named_confound': confound,
               'target_delta': signed_delta, 'quantization_tolerance': tolerance,
               'baseline_effect': contrast(baseline, count) if confound else None,
               'baseline_expected_effect': 0.0 if confound else None,
               'generating_process': 'Empirical dated panel' if kind == 'known_positive' else
                   ('Within-genre disjoint binary quotas and real year permutations' if signed_delta else
                    'Zero-expected date randomization, then nuisance-associated date permutation'),
               'source_sha256': source_sha256}
        if confound:
            baseline.to_parquet(output/'private'/f'{cid}_baseline.parquet', index=False)
        dump(output/'private'/f'{cid}_mapping.json', mappings)
        dump(output/'private'/f'{cid}.json', key)
        manifest.append({'corpus_id': cid})
    dump(output/'manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('labels'); p.add_argument('output')
    p.add_argument('--seed', type=int, default=1729)
    p.add_argument('--delta', type=float, default=.05)
    p.add_argument('--construct', default='auto', help='Verified candidate target, shared across all arms')
    p.add_argument('--minimum-effect', type=float, default=.03)
    p.add_argument('--allow-unverified-positive', action='store_true',
                   help='With --construct: generate positive replays as unscored (unsupported) if screening fails')
    a = p.parse_args()
    generate(a.labels, a.output, a.seed, a.delta, a.construct, a.minimum_effect,
             a.allow_unverified_positive)
