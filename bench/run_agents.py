"""Run a configured CLI in a fresh working directory, without staging hidden keys."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import tempfile
import time

try:
    from .score import validate
except ImportError:
    from score import validate

COMMANDS = {'claude': ['claude', '-p', '{prompt}'],
            'codex': ['codex', 'exec', '--skip-git-repo-check', '{prompt}']}


def extract_json(stdout):
    # Accept fenced JSON and CLI event/wrapper output only when exactly one valid
    # answer object is present. Never silently select a partial or conflicting answer.
    decoder = json.JSONDecoder()
    found = []
    for i, char in enumerate(stdout):
        if char != '{':
            continue
        try:
            obj, _ = decoder.raw_decode(stdout[i:])
            validate(obj)
        except (ValueError, TypeError):
            continue
        if obj not in found:
            found.append(obj)
    if len(found) != 1:
        raise ValueError('Expected exactly one valid JSON answer')
    return found[0]


def run_one(corpus, command, timeout=300, token_budget=8000, temp_root=None):
    started = time.monotonic()
    prompt = Path(__file__).with_name('agent_task.md').read_text()
    prompt = prompt.replace('8,000-token', f'{token_budget:,}-token')
    if temp_root is None:
        temp_root = Path(__file__).resolve().parent / '.agent-tmp'
    Path(temp_root).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bench-agent-', dir=temp_root) as tmp:
        for name in ['works.parquet', 'works.csv', 'passages.parquet', 'task.json']:
            shutil.copy2(Path(corpus)/name, Path(tmp)/name)
        Path(tmp, 'TASK.md').write_text(prompt)
        args = [part.replace('{prompt}', prompt).replace('{token_budget}', str(token_budget)) for part in command]
        env = os.environ.copy()
        env['BENCH_TOKEN_BUDGET'] = str(token_budget)
        proc = subprocess.Popen(args, cwd=tmp, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
            return None, {'status': 'timeout', 'stdout': stdout, 'stderr': stderr,
                          'elapsed': time.monotonic()-started, 'token_budget': token_budget,
                          'token_budget_enforcement': 'prompt_only'}
        meta = {'status': 'ok', 'returncode': proc.returncode, 'stdout': stdout, 'stderr': stderr,
                'elapsed': time.monotonic()-started, 'token_budget': token_budget,
                'token_budget_enforcement': 'prompt_only'}
        try:
            if proc.returncode:
                raise ValueError(f'CLI exited {proc.returncode}')
            answer_file = Path(tmp)/'answer.json'
            answer = extract_json(answer_file.read_text() if answer_file.exists() else stdout)
        except ValueError as exc:
            meta.update(status='invalid', error=str(exc))
            answer = None
        return answer, meta


def run(root, output, command, timeout=300, token_budget=8000, temp_root=None):
    root, output = Path(root), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for item in json.loads((root/'manifest.json').read_text()):
        cid = item['corpus_id']
        destination = output/f'{cid}.json'
        # A failed repeat must not leave a successful old answer to be scored.
        destination.unlink(missing_ok=True)
        answer, meta = run_one(root/cid, command, timeout, token_budget, temp_root)
        (output/f'{cid}.run.json').write_text(json.dumps(meta, indent=2)+'\n')
        if answer is not None:
            destination.write_text(json.dumps(answer, indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root'); p.add_argument('output')
    p.add_argument('--backend', choices=COMMANDS, default='codex')
    p.add_argument('--command', help='Shell-quoted argv template; {prompt} and {token_budget} supported; no shell execution')
    p.add_argument('--timeout', type=float, default=300)
    p.add_argument('--token-budget', type=int, default=8000)
    a = p.parse_args()
    if a.timeout <= 0 or a.token_budget <= 0:
        p.error('timeout and token budget must be positive')
    run(a.root, a.output, shlex.split(a.command) if a.command else COMMANDS[a.backend], a.timeout, a.token_budget)
