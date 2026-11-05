"""Structural side-channel audit, excluding outcomes and intentional nuisance trends."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score


def features(root):
    rows, kinds = [], []
    for item in json.loads((Path(root)/'manifest.json').read_text()):
        cid = item['corpus_id']
        public = Path(root)/cid
        f = pd.read_parquet(public/'works.parquet')
        p = pd.read_parquet(public/'passages.parquet')
        years = f.year.value_counts(normalize=True)
        rows.append(dict(rows=len(f), works=f.work_id.nunique(), passages=len(p),
            authors=f.author_key.nunique(), years=f.year.nunique(), minimum_year=f.year.min(),
            maximum_year=f.year.max(), mean_year=f.year.mean(),
            year_entropy=float(-(years*np.log(years)).sum()),
            multiyear=f.groupby('work_id').year.nunique().gt(1).mean(),
            work_columns=len(f.columns), passage_columns=len(p.columns),
            missing_cells=int(f.isna().sum().sum()+p.isna().sum().sum()),
            works_bytes=(public/'works.parquet').stat().st_size,
            passages_bytes=(public/'passages.parquet').stat().st_size,
            csv_bytes=(public/'works.csv').stat().st_size))
        kinds.append(json.loads((Path(root)/'private'/f'{cid}.json').read_text())['kind'])
    return pd.DataFrame(rows), np.asarray(kinds)


def classifier_accuracy(x, y):
    folds = StratifiedKFold(5, shuffle=True, random_state=9)
    return float(cross_val_score(RandomForestClassifier(n_estimators=40, random_state=9),
                                 x, y, cv=folds).mean())


def audit(root):
    x, y = features(root)
    accuracy = classifier_accuracy(x, y)
    # Exact feature equality is stronger than non-significance on 30 observations.
    return dict(features=list(x.columns), varying_features=x.columns[x.nunique().gt(1)].tolist(),
                accuracy=accuracy, chance=1/3, n_corpora=len(y),
                scope='Marginal structure/storage only; excludes target effects and nuisance-year associations')


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root'); p.add_argument('--output')
    a = p.parse_args()
    result = json.dumps(audit(a.root), indent=2)+'\n'
    if a.output:
        Path(a.output).write_text(result)
    else:
        print(result)
