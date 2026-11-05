"""Deterministic non-agentic baseline: the task's estimand + author-cluster bootstrap.

Run in the staged working directory (public files only), e.g. through run_agents:
  --command "python bench/baseline.py"
Claims a shift iff the 95% percentile interval excludes zero. No confound checks.
"""
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


def estimate(works, count, cutoff, draws=1000, seed=0):
    f = works.assign(rate=works[count]/works.n_passages, late=works.year >= cutoff)
    cells = list(f.groupby(['genre', 'late']).indices.values())  # (g,False),(g,True),...
    rates = f.rate.to_numpy()
    def stat(weights):
        means = [np.average(rates[ix], weights=weights[ix]) if weights[ix].sum() else np.nan
                 for ix in cells]
        means = np.asarray(means)
        return float(np.mean(means[1::2]-means[::2]))
    point = stat(np.ones(len(f)))
    authors, codes = np.unique(f.author_key.to_numpy(), return_inverse=True)
    rng = np.random.default_rng(seed)
    boot = []
    for _ in range(draws):
        w = rng.multinomial(len(authors), np.full(len(authors), 1/len(authors)))[codes]
        value = stat(w)
        if np.isfinite(value):
            boot.append(value)
    lo, hi = np.quantile(boot, [.025, .975])
    p_pos = float(np.mean(np.asarray(boot) > 0))
    return point, [float(min(lo, point)), float(max(hi, point))], p_pos


def main(directory='.'):
    d = Path(directory)
    task = json.loads((d/'task.json').read_text())
    works = pd.read_parquet(d/'works.parquet')
    effect, ci, p_pos = estimate(works, task['count_column'], task['cutoff_year'])
    shift = ci[0] > 0 or ci[1] < 0
    answer = {
        'claim': 'shift' if shift else 'no_shift',
        'direction': ('increase' if effect > 0 else 'decrease') if shift else 'none',
        'effect': effect, 'ci': ci,
        # Two-sided bootstrap evidence against zero, used as P(shift) for Brier.
        'confidence': float(2*max(p_pos, 1-p_pos)-1),
        'named_confounds': [], 'evidence_passage_ids': [],
        'rationale': 'Equal-genre, equal-work late-minus-early rate; 1000-draw author-cluster bootstrap.'}
    print(json.dumps(answer))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.')
