"""Aggregate scored runs across seeds/conditions with corpus-cluster bootstrap CIs.

  python -m bench.analyze ROOT RUNS_DIR --output metrics.json [--figs bench/figs]

RUNS_DIR contains one directory per condition (e.g. claude_base/seed1, baseline).
CIs: two-stage bootstrap (resample corpora, then repeats within corpus), 5,000 draws.
"""
import argparse
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

from .score import identifies_confound, score_one

NUISANCE_COLUMNS = {
    'genre_mix_drift': [r'\bgenre\b'],
    'reprint_date_contamination': [r'date_confidence'],
    'edition_selection_bias': [r'n_editions'],
    'prolific_author_selection': [r'author_key'],
    'origin_composition_drift': [r'\borigin\b'],
}


def load_rows(root, runs):
    root, runs = Path(root), Path(runs)
    manifest = [x['corpus_id'] for x in json.loads((root/'manifest.json').read_text())]
    keys = {c: json.loads((root/'private'/f'{c}.json').read_text()) for c in manifest}
    passages = {c: pd.read_parquet(root/c/'passages.parquet') for c in manifest}
    rows = []
    for cond in sorted(p for p in runs.iterdir() if p.is_dir()):
        seed_dirs = sorted(p for p in cond.iterdir() if p.is_dir() and p.name.startswith('seed')) or [cond]
        for sd in seed_dirs:
            for c in manifest:
                meta_path = sd/f'{c}.run.json'
                if not meta_path.exists():
                    continue  # not run in this condition (e.g. subset)
                meta = json.loads(meta_path.read_text())
                try:
                    answer = json.loads((sd/f'{c}.json').read_text())
                except (OSError, ValueError):
                    answer = None
                r = score_one({**keys[c], 'status': 'ready'} if keys[c]['kind'] == 'known_positive'
                              else keys[c], answer, passages[c])
                s = meta.get('summary') or {}
                u = s.get('usage') or {}
                code = '\n'.join(t['input'] for t in s.get('tool_calls', []))
                workdir = meta.get('workdir') or '/nonexistent'
                # Any reference to the repo, home, private keys or parent dirs (cd into the
                # staging dir and /tmp/bench-agent-venv are expected).
                outside = re.findall(r'(/home/[^\s\'"]*|agentic_literary|private/|\.\./|~/)',
                                     code.replace(workdir, ''))
                if not meta.get('isolated'):  # host /tmp is shared between concurrent sessions
                    outside += re.findall(r'/tmp/(?!bench-agent-venv|claude-1000/)[\w.\-/]+', code.replace(workdir, ''))
                for name in NUISANCE_COLUMNS:  # would this artifact be "identified" here?
                    r[f'names__{name}'] = bool(answer is not None and r['valid_answer'] and
                                               identifies_confound({'named_confound': name}, answer))
                r.update(n_named_confounds=len(answer['named_confounds']) if r['valid_answer'] else None,
                         condition=cond.name, seed=sd.name, status=meta['status'],
                         confound=keys[c]['named_confound'], true_effect=keys[c]['true_effect'],
                         observed_effect=keys[c]['observed_effect'], scored=keys[c]['status'] == 'ready',
                         claim=answer['claim'] if answer else None,
                         confidence=answer['confidence'] if answer else None,
                         effect=answer['effect'] if answer else None,
                         minutes=meta['elapsed']/60, cost_usd=s.get('total_cost_usd'),
                         api_minutes=(s.get('duration_api_ms') or float('nan'))/60000,
                         input_tokens=sum(u.get(k, 0) or 0 for k in ['input_tokens', 'cache_read_input_tokens',
                                                                     'cache_creation_input_tokens']) if u else None,
                         output_tokens=u.get('output_tokens'), turns=s.get('num_turns'),
                         n_tool_calls=s.get('n_tool_calls'), model=s.get('model'),
                         outside_refs=';'.join(sorted(set(outside))), isolated=bool(meta.get('isolated')),
                         # Process-level: did the agent's code touch each nuisance column?
                         **{f'touched__{k}': bool(any(re.search(p, code) for p in v))
                            for k, v in NUISANCE_COLUMNS.items()})
                if keys[c]['kind'] == 'known_positive':  # unscored replay: descriptive only
                    r['correct'] = None
                rows.append(r)
    return pd.DataFrame(rows)


def boot(frame, value, draws=5000, seed=0):
    """Mean over runs, CI from resampling corpora then runs within corpus."""
    groups = [g[value].astype(float).to_numpy() for _, g in frame.groupby('corpus_id')]
    groups = [g[~np.isnan(g)] for g in groups]
    groups = [g for g in groups if len(g)]
    if not groups:
        return None
    rng = np.random.default_rng(seed)
    point = float(np.mean(np.concatenate(groups)))
    sizes = np.array([len(g) for g in groups])
    mat = np.full((len(groups), sizes.max()), np.nan)
    for i, g in enumerate(groups):
        mat[i, :len(g)] = g
    pick = rng.integers(0, len(groups), (draws, len(groups)))            # corpora
    k = sizes[pick]
    within = (rng.random((draws, len(groups), sizes.max())) * k[..., None]).astype(int)
    mask = np.arange(sizes.max())[None, None, :] < k[..., None]           # repeats within corpus
    values = mat[pick[..., None], within]
    stats = np.nansum(np.where(mask, values, 0), axis=(1, 2)) / mask.sum(axis=(1, 2))
    lo, hi = np.quantile(stats, [.025, .975])
    return {'mean': point, 'ci': [float(lo), float(hi)], 'n_runs': int(sum(map(len, groups))),
            'n_corpora': len(groups)}


def summarize(rows):
    out = {}
    for cond, f in rows.groupby('condition'):
        inj = f[f.kind == 'injected_shift']
        nul = f[f.kind == 'confounded_null']
        pos = f[f.kind == 'known_positive']
        scored = f[f.scored]
        f = f.assign(balanced=np.nan)
        cited = f.evidence_cited.sum()
        m = {
            'n_runs': len(f), 'n_valid': int(f.valid_answer.sum()),
            'statuses': f.status.value_counts().to_dict(),
            'models': sorted({x for x in f.model.dropna()}),
            'detection_injected': boot(inj, 'correct'),
            'false_claim_null': boot(nul, 'false_claim'),
            'false_claim_by_confound': {c: boot(g, 'false_claim') for c, g in nul.groupby('confound')},
            'confound_identified_null': boot(nul, 'confound_identified'),
            'confound_identified_by_confound': {c: boot(g, 'confound_identified') for c, g in nul.groupby('confound')},
            'nuisance_column_touched_null': boot(nul.assign(t=[r[f'touched__{r.confound}'] for _, r in nul.iterrows()]), 't')
                                            if len(nul) else None,
            'abstention_scored': boot(scored, 'abstained'),
            'brier_scored': boot(scored, 'brier'),
            'ci_covers_truth_injected': boot(inj, 'ci_covers_truth'),
            'positive_replay_shift_claim_rate': boot(pos.assign(s=pos.claim.eq('shift')), 's') if len(pos) else None,
            'evidence_cited_total': int(cited),
            'evidence_existence_rate': float(f.evidence_existing.sum()/cited) if cited else None,
            'evidence_validity_rate': float(f.evidence_supported.sum()/cited) if cited else None,
            'cost_usd_per_corpus': boot(f, 'cost_usd'),
            'cost_usd_total': float(f.cost_usd.sum()) if f.cost_usd.notna().any() else None,
            'minutes_per_corpus': boot(f, 'minutes'),
            'api_minutes_per_corpus': boot(f, 'api_minutes'),
            'input_tokens_per_corpus': boot(f, 'input_tokens'),
            'output_tokens_per_corpus': boot(f, 'output_tokens'),
            'tool_calls_per_corpus': boot(f, 'n_tool_calls'),
        }
        # Specificity of confound naming: own-arm naming rate vs. rate in all other corpora.
        m['confound_naming_specificity'] = {
            name: {'own_arm': float(f[f.confound == name][f'names__{name}'].mean()) if (f.confound == name).any() else None,
                   'other_corpora': float(f[f.confound != name][f'names__{name}'].mean())}
            for name in NUISANCE_COLUMNS}
        m['runs_with_outside_path_refs'] = int(f.outside_refs.astype(bool).sum())
        m['outside_path_refs'] = sorted({x for v in f.outside_refs for x in v.split(';') if x})
        m['n_isolated_runs'] = int(f.isolated.sum())
        m['named_confounds_per_answer_by_kind'] = f.groupby('kind').n_named_confounds.mean().to_dict()
        m['nuisance_touched_by_kind'] = {k: float(g[[c for c in g if c.startswith('touched__')]].mean(axis=1).mean())
                                         for k, g in f.groupby('kind')}
        # Balanced accuracy over the 20 scored corpora: 1 - false claim on nulls, detection on injected.
        bal = scored.assign(ok=np.where(scored.kind == 'injected_shift', scored.correct.astype(float),
                                        (~scored.false_claim).astype(float)))
        m['balanced_accuracy'] = boot(bal, 'ok')
        m['gate_pass_rate_by_seed'] = {
            s: bool(len(g[g.kind == 'injected_shift']) == 10 and g[g.kind == 'confounded_null'].shape[0] == 10 and
                    g[g.scored].valid_answer.all() and g[g.kind == 'injected_shift'].correct.sum() >= 8 and
                    g[g.kind == 'confounded_null'].false_claim.sum() <= 1)
            for s, g in f.groupby('seed')}
        out[cond] = m
    return out


def figures(rows, metrics, figdir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size': 7, 'axes.titlesize': 7.5, 'axes.labelsize': 7,
                         'xtick.labelsize': 6.5, 'ytick.labelsize': 6.5, 'legend.fontsize': 6.5,
                         'font.family': 'DejaVu Sans', 'axes.spines.top': False,
                         'axes.spines.right': False, 'axes.edgecolor': '#52514e',
                         'axes.linewidth': .6, 'xtick.color': '#52514e', 'ytick.color': '#52514e',
                         'savefig.dpi': 300})
    figdir = Path(figdir); figdir.mkdir(parents=True, exist_ok=True)
    style = {'claude_base': ('Agent', '#2a78d6', 'o'),
             'claude_confound_check': ('Agent + confound check', '#eb6834', 's'),
             'baseline': ('Estimator', '#1baf7a', 'D')}
    conds = [c for c in style if c in metrics]
    labels = {'genre_mix_drift': 'Genre\nmix', 'reprint_date_contamination': 'Reprint\ndates',
              'edition_selection_bias': 'Edition/\ncanon', 'prolific_author_selection': 'Prolific\nauthors',
              'origin_composition_drift': 'Origin\nmix'}
    order = list(labels)
    # (a) false-claim rate by confound type
    fig, ax = plt.subplots(figsize=(3.33, 2.2))
    width = .8/len(conds)
    for j, c in enumerate(conds):
        name, color, marker = style[c]
        xs, ys, lo, hi = [], [], [], []
        for i, k in enumerate(order + ['all']):
            b = metrics[c]['false_claim_null'] if k == 'all' else metrics[c]['false_claim_by_confound'].get(k)
            if not b:
                continue
            x = i + (j-(len(conds)-1)/2)*width + (.4 if k == 'all' else 0)
            xs.append(x); ys.append(b['mean']); lo.append(b['mean']-b['ci'][0]); hi.append(b['ci'][1]-b['mean'])
        ax.errorbar(xs, ys, yerr=[lo, hi], fmt=marker, ms=4, color=color, ecolor=color,
                    elinewidth=1, capsize=1.5, label=name, mec='white', mew=.5)
    ax.axhline(.1, color='#52514e', lw=.6, ls=(0, (3, 2)))
    ax.text(-.45, .115, 'gate ≤ 0.1', color='#52514e', fontsize=6, ha='left', va='bottom')
    ax.axvline(len(order)-.1, color='#d9d8d4', lw=.6)
    ax.set_xticks(list(range(len(order)))+[len(order)+.4])
    realized = rows[rows.kind == 'confounded_null'].groupby('confound').observed_effect.apply(
        lambda x: f'≤{100*x.abs().max():.1f}')
    ax.set_xticklabels([f'{labels[k]}\n{realized.get(k, "")}' for k in order]+['All\nnulls\n|Δ| pp'], rotation=0)
    ax.tick_params(axis='x', labelsize=6)
    ax.set_ylim(-.03, 1.03); ax.set_ylabel('False shift claims on nulls')
    ax.grid(axis='y', color='#ebeae6', lw=.5); ax.set_axisbelow(True)
    ax.legend(loc='lower center', bbox_to_anchor=(.5, 1.0), ncol=len(conds), frameon=False,
              handletextpad=.1, columnspacing=.6, borderaxespad=.1, fontsize=5.8)
    fig.tight_layout(pad=.3)
    fig.savefig(figdir/'false_claims_by_confound.pdf'); fig.savefig(figdir/'false_claims_by_confound.png')
    plt.close(fig)
    # (b) calibration: stated P(shift) vs realized standardized effect; accuracy vs cost
    fig, axes = plt.subplots(1, 2, figsize=(3.33, 1.85), gridspec_kw={'width_ratios': [1.25, 1]})
    ax = axes[0]
    rng = np.random.default_rng(1)
    for j, c in enumerate(conds):
        name, color, marker = style[c]
        g = rows[(rows.condition == c) & rows.confidence.notna()]
        x = 100*g.observed_effect.where(g.kind != 'confounded_null', g.observed_effect).to_numpy()
        x = x + (j-(len(conds)-1)/2)*.35 + rng.uniform(-.08, .08, len(x))
        hollow = (g.kind == 'confounded_null').to_numpy()
        ax.scatter(x[~hollow], g.confidence[~hollow], s=9, marker=marker, color=color, alpha=.75,
                   linewidths=0, zorder=3)
        ax.scatter(x[hollow], g.confidence[hollow], s=9, marker=marker, facecolors='white',
                   edgecolors=color, linewidths=.7, zorder=3)
    ax.axvspan(-2.7, 2.7, color='#f3f2ef', lw=0, zorder=0)
    ax.text(0, 1.06, 'nulls (hollow)', ha='center', va='bottom', fontsize=5.5, color='#52514e')
    ax.text(-5.0, 1.06, 'injected', ha='center', va='bottom', fontsize=5.5, color='#52514e')
    ax.text(5.1, 1.06, 'injected', ha='center', va='bottom', fontsize=5.5, color='#52514e')
    ax.set_xlim(-6.2, 6.2); ax.set_ylim(-.04, 1.04)
    ax.set_xlabel('Realized standardized effect (pp)'); ax.set_ylabel('Stated P(shift)')
    ax.set_title('Calibration', loc='left', pad=9)
    ax = axes[1]
    for c in conds:
        name, color, marker = style[c]
        b, cost = metrics[c]['balanced_accuracy'], metrics[c]['cost_usd_per_corpus']
        x = cost['mean'] if cost else 0.0
        ax.errorbar(x, b['mean'], yerr=[[b['mean']-b['ci'][0]], [b['ci'][1]-b['mean']]],
                    xerr=None if not cost else [[x-cost['ci'][0]], [cost['ci'][1]-x]],
                    fmt=marker, ms=4.5, color=color, elinewidth=1, capsize=1.5, mec='white', mew=.5,
                    label=name)
    ax.set_xlabel('USD per corpus'); ax.set_ylabel('Balanced accuracy')
    ax.set_ylim(.4, 1.02); ax.set_xlim(-.02, .2)
    ax.set_title('Accuracy vs. cost', loc='left', pad=9)
    for a in axes:
        a.grid(color='#ebeae6', lw=.5); a.set_axisbelow(True)
    handles, names = axes[1].get_legend_handles_labels()
    fig.legend(handles, names, loc='lower center', ncol=len(conds), frameon=False,
               bbox_to_anchor=(.5, -.02), handletextpad=.2, columnspacing=.8, fontsize=5.8)
    fig.tight_layout(pad=.3, rect=(0, .1, 1, 1))
    fig.savefig(figdir/'accuracy_vs_cost.pdf'); fig.savefig(figdir/'accuracy_vs_cost.png')
    plt.close(fig)


def table(metrics):
    """Markdown summary table (mean [95% CI]) for the paper."""
    def fmt(b, pct=True, digits=2):
        if not b:
            return '—'
        k = 100 if pct else 1
        d = 0 if pct else digits
        return f"{k*b['mean']:.{d}f} [{k*b['ci'][0]:.{d}f}, {k*b['ci'][1]:.{d}f}]"
    names = {'claude_base': 'Agent, base prompt', 'claude_confound_check': 'Agent, +confound check',
             'baseline': 'Deterministic estimator'}
    order = [c for c in names if c in metrics] + [c for c in metrics if c not in names]
    lines = ['| Metric | ' + ' | '.join(names.get(c, c) for c in order) + ' |',
             '|---|' + '---:|'*len(order)]
    spec = [('Runs (valid)', lambda m: f"{m['n_runs']} ({m['n_valid']})"),
            ('Injected shifts detected, %', lambda m: fmt(m['detection_injected'])),
            ('False shift claims on nulls, %', lambda m: fmt(m['false_claim_null'])),
            ('Abstention (scored corpora), %', lambda m: fmt(m['abstention_scored'])),
            ('Balanced accuracy, %', lambda m: fmt(m['balanced_accuracy'])),
            ('Brier loss', lambda m: fmt(m['brier_scored'], False, 3)),
            ('Confound "identified" (keyword), %', lambda m: fmt(m['confound_identified_null'])),
            ('Shift claims on real-date replays, %', lambda m: fmt(m['positive_replay_shift_claim_rate'])),
            ('Evidence IDs valid, %', lambda m: '—' if m['evidence_validity_rate'] is None else
                f"{100*m['evidence_validity_rate']:.0f} (n={m['evidence_cited_total']})"),
            ('USD / corpus', lambda m: fmt(m['cost_usd_per_corpus'], False, 3)),
            ('Input tokens / corpus (k)', lambda m: '—' if not m['input_tokens_per_corpus'] else
                f"{m['input_tokens_per_corpus']['mean']/1000:.1f}"),
            ('Output tokens / corpus (k)', lambda m: '—' if not m['output_tokens_per_corpus'] else
                f"{m['output_tokens_per_corpus']['mean']/1000:.1f}"),
            ('API minutes / corpus', lambda m: fmt(m['api_minutes_per_corpus'], False, 2)),
            ('Wall minutes / corpus', lambda m: fmt(m['minutes_per_corpus'], False, 2))]
    for label, f in spec:
        lines.append(f'| {label} | ' + ' | '.join(f(metrics[c]) for c in order) + ' |')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root'); p.add_argument('runs')
    p.add_argument('--output'); p.add_argument('--rows'); p.add_argument('--figs'); p.add_argument('--table')
    a = p.parse_args()
    rows = load_rows(a.root, a.runs)
    metrics = summarize(rows)
    text = json.dumps(metrics, indent=2, default=float)
    if a.output:
        Path(a.output).write_text(text+'\n')
    else:
        print(text)
    if a.rows:
        rows.to_csv(a.rows, index=False)
    if a.table:
        Path(a.table).write_text(table(metrics))
    if a.figs:
        figures(rows, metrics, a.figs)
