"""Free, reproducible real-label adapter -> generation -> dummy -> scoring pilot."""
import argparse
import json
from pathlib import Path
import sys
import time

from .generate import dump, generate
from .leak_audit import audit
from .prepare import prepare
from .run_agents import run
from .score import score


def pilot(output):
    root = Path(output)
    if root.exists() and any(root.iterdir()):
        raise ValueError('Pilot output must be empty')
    root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    f = prepare('data/work/ald.duckdb', 'data/work/works.parquet',
                'data/work/genre.parquet', 'data/work/passages.parquet', root/'labels.parquet')
    adapted = time.monotonic()
    generate(root/'labels.parquet', root/'generated')
    generated = time.monotonic()
    leak = audit(root/'generated')
    dump(root/'leak_audit.json', leak)
    audited = time.monotonic()
    run(root/'generated', root/'answers', [sys.executable, str(Path(__file__).with_name('dummy_agent.py').resolve())])
    ran = time.monotonic()
    scores = score(root/'generated', root/'answers')
    dump(root/'scores.json', scores)
    elapsed = time.monotonic()-started
    logs = [json.loads(p.read_text()) for p in (root/'answers').glob('*.run.json')]
    task_bytes = len(Path(__file__).with_name('agent_task.md').read_bytes())
    report = dict(source_passages=len(f), source_works=int(f.work_id.nunique()),
                  source_strata=f.stratum.value_counts().to_dict(),
                  adapter_seconds=adapted-started, generate_seconds=generated-adapted,
                  audit_seconds=audited-generated, runner_seconds=ran-audited,
                  total_seconds=elapsed, n_runs=len(logs),
                  statuses={s:sum(l['status']==s for l in logs) for s in {l['status'] for l in logs}},
                  summed_agent_seconds=sum(l['elapsed'] for l in logs),
                  prompt_utf8_bytes=task_bytes,
                  dummy_stdout_utf8_bytes=sum(len(l['stdout'].encode()) for l in logs),
                  paid_calls=0, score=scores['summary'], leak_audit=leak)
    dump(root/'summary.json', report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', default='bench/pilot')
    pilot(p.parse_args().output)
