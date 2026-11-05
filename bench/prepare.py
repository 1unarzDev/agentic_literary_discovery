"""Read-only v0.9 Discovery adapter; never open the database for writing."""
import argparse
import json
from pathlib import Path
import duckdb
import pandas as pd


def prepare(database, works_path, genres_path, passages_path, output):
    # Parameterized paths; only Discovery identifiers enter the returned frame.
    with duckdb.connect(':memory:') as con:
        escaped = str(database).replace("'", "''")
        con.execute(f"ATTACH '{escaped}' AS source (READ_ONLY)")
        con.read_parquet(str(works_path)).create_view('bench_works')
        con.read_parquet(str(genres_path)).create_view('bench_genres')
        con.read_parquet(str(passages_path)).create_view('bench_passages')
        frame = con.sql("""
            SELECT r.passage_id, r.output_json, p.work_id, p.stratum,
                   w.author_key, w.year, w.origin_locc AS origin, w.n_editions,
                   w.date_confidence, g.genre
            FROM source.results r JOIN bench_passages p USING (passage_id)
            JOIN (SELECT * FROM bench_works QUALIFY row_number() OVER
                  (PARTITION BY work_id ORDER BY pg_id) = 1) w ON p.work_id=w.work_id
            JOIN bench_genres g ON p.work_id=g.work_id
            WHERE r.stage='label' AND starts_with(r.pin_hash, '41ca3c7d')
              AND r.valid_schema AND r.error IS NULL
              AND NOT coalesce(r.is_dup_twin, false)
              AND w.split='discovery' AND p.split='discovery'
              AND w.year BETWEEN 1800 AND 1925
            QUALIFY row_number() OVER (PARTITION BY r.passage_id ORDER BY r.created DESC,
                                      r.output_json) = 1
            ORDER BY r.passage_id
        """).df()
    values = pd.json_normalize(frame.pop('output_json').map(json.loads))
    for field, default in [('domains', None), ('locus', 'none'), ('failure_cause', 'none'),
                           ('night_function', 'none'), ('technology_named', 'none')]:
        column = values.get(field, pd.Series(None, index=frame.index, dtype=object))
        frame[field] = column.map(lambda x: x if isinstance(x, list) else []) if field == 'domains' else column.fillna(default)
    frame['has_obstacle'] = values.has_obstacle
    frame['confidence'] = values.confidence
    frame['split'] = 'discovery'
    frame['decade'] = frame.year.astype(int)//10*10
    frame['memorization_score'] = 0.0  # Not measured; no memory-based control is generated.
    frame.origin = frame.origin.fillna('unknown')
    frame.date_confidence = frame.date_confidence.fillna('unknown')
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output, index=False)
    return frame


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database', default='data/work/ald.duckdb')
    p.add_argument('--works', default='data/work/works.parquet')
    p.add_argument('--genres', default='data/work/genre.parquet')
    p.add_argument('--passages', default='data/work/passages.parquet')
    p.add_argument('--output', default='bench/pilot/labels.parquet')
    a = p.parse_args()
    f = prepare(a.database, a.works, a.genres, a.passages, a.output)
    print(json.dumps({'passages': len(f), 'works': f.work_id.nunique(), 'strata': f.stratum.value_counts().to_dict()}))
