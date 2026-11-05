"""Run a configured CLI in a fresh working directory, without staging hidden keys."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
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

# Claude: stream-json is a superset of `--output-format json` (its final `result`
# event carries the same usage/cost/model fields) and also exposes tool calls,
# which are summarized for process-level checks. Safe mode skips CLAUDE.md,
# memory, skills, hooks and MCP; only local file/shell tools are available.
COMMANDS = {
    'claude': ['claude', '-p', '{prompt}', '--output-format', 'stream-json', '--verbose',
               '--safe-mode', '--strict-mcp-config', '--no-session-persistence',
               '--tools', 'Bash,Read,Write,Edit,Glob,Grep',
               '--allowedTools', 'Bash,Read,Write,Edit,Glob,Grep',
               '--disallowedTools', 'WebFetch,WebSearch,Agent'],
    'codex': ['codex', 'exec', '--skip-git-repo-check', '--json', '{prompt}'],
}

# Second condition: an explicit process instruction (a mitigation prompt). It names
# the public metadata columns but neither the arm nor any answer string.
CONDITIONS = {
    'base': '',
    'confound_check': (
        '\nBefore claiming any shift, check for composition and dating artifacts: test '
        'whether the assigned years are associated with other work metadata (genre, '
        'origin, n_editions, date_confidence, author productivity), and whether the '
        'contrast survives stratification or adjustment for them and restriction to '
        'well-dated works. Claim a shift only if it survives these checks; otherwise '
        'answer no_shift or abstain, and name the artifact in named_confounds.\n'),
}

# Environment of the parent agent session must not leak into child sessions.
STRIP_PREFIXES = ('CLAUDECODE', 'CLAUDE_CODE_', 'CLAUDE_EFFORT', 'CLAUDE_PID', 'AI_AGENT')


INFRA_MARKERS = ('Disk quota exceeded', 'No space left on device', 'EDQUOT')


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


def parse_events(stdout):
    """Summarize Claude stream-json / Codex --json events: final text, usage, tool calls."""
    events = []
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith('{'):
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
    if not events:
        return None, {}
    summary, tools, final = {}, [], None
    for e in events:
        if e.get('type') == 'result':  # Claude final event
            final = e.get('result')
            summary.update({k: e.get(k) for k in ['duration_ms', 'duration_api_ms', 'num_turns',
                            'total_cost_usd', 'usage', 'modelUsage', 'is_error', 'subtype']})
        elif e.get('type') == 'system' and e.get('subtype') == 'init':
            summary.update(model=e.get('model'), cli_version=e.get('claude_code_version'),
                           tools_available=e.get('tools'))
        elif e.get('type') == 'assistant':
            for block in e.get('message', {}).get('content', []):
                if block.get('type') == 'tool_use':
                    inp = block.get('input', {})
                    text = inp.get('command') or inp.get('file_path') or inp.get('pattern') or json.dumps(inp)
                    tools.append({'tool': block.get('name'), 'input': str(text)[:1500]})
        elif e.get('type') == 'item.completed':  # Codex exec --json
            item = e.get('item', {})
            if item.get('type') in ('agent_message', 'assistant_message'):
                final = item.get('text', final)
            elif item.get('type') == 'command_execution':
                tools.append({'tool': 'shell', 'input': str(item.get('command'))[:1500]})
        elif e.get('type') == 'turn.completed':
            usage = summary.setdefault('usage', {})
            for k, v in (e.get('usage') or {}).items():
                usage[k] = usage.get(k, 0) + v
        elif e.get('type') == 'thread.started':
            summary['thread_id'] = e.get('thread_id')
    summary['tool_calls'] = tools
    summary['n_tool_calls'] = len(tools)
    return final, summary


def child_env(token_budget, extra_path=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith(STRIP_PREFIXES)}
    env['BENCH_TOKEN_BUDGET'] = str(token_budget)
    if extra_path:
        env['PATH'] = f"{extra_path}{os.pathsep}{env.get('PATH', '')}"
    return env


def run_one(corpus, command, timeout=300, token_budget=8000, temp_root=None,
            condition='base', extra_path=None, isolate=False):
    started = time.monotonic()
    prompt = Path(__file__).with_name('agent_task.md').read_text()
    prompt = prompt.replace('8,000-token', f'{token_budget:,}-token') + CONDITIONS[condition]
    if temp_root is None:
        temp_root = Path(__file__).resolve().parent / '.agent-tmp'
    Path(temp_root).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bench-agent-', dir=temp_root) as tmp:
        for name in ['works.parquet', 'works.csv', 'passages.parquet', 'task.json']:
            shutil.copy2(Path(corpus)/name, Path(tmp)/name)
        Path(tmp, 'TASK.md').write_text(prompt)
        args = [part.replace('{prompt}', prompt).replace('{token_budget}', str(token_budget)) for part in command]
        env = child_env(token_budget, extra_path)
        if isolate:
            # Private /tmp per session (no shared scratch paths, no host tmpfs quota);
            # mask the repository (keys), other sessions' staging dirs and CLI transcripts.
            repo = Path(__file__).resolve().parents[1]
            mask = [str(repo), str(Path(temp_root).resolve()), str(Path.home()/'.claude'/'projects')]
            args = ['bwrap', '--dev-bind', '/', '/', '--tmpfs', '/tmp'] + \
                   [x for m in mask if Path(m).exists() for x in ('--tmpfs', m)] + \
                   ['--bind', tmp, tmp, '--chdir', tmp, '--die-with-parent', '--'] + args
            env['TMPDIR'] = env['CLAUDE_CODE_TMPDIR'] = '/tmp'
        else:
            # Child CLI scratch space (tool outputs) lives beside the staging dirs.
            scratch = Path(temp_root)/'.cli-tmp'
            scratch.mkdir(exist_ok=True)
            env['TMPDIR'] = env['CLAUDE_CODE_TMPDIR'] = str(scratch)
        proc = subprocess.Popen(args, cwd=tmp, env=env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, start_new_session=True)
        base = {'condition': condition, 'token_budget': token_budget, 'isolated': isolate,
                'token_budget_enforcement': 'prompt_only', 'workdir': tmp}
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
            final, summary = parse_events(stdout)
            return None, {**base, 'status': 'timeout', 'elapsed': time.monotonic()-started,
                          'summary': summary, 'stdout_tail': stdout[-4000:], 'stderr': stderr[-4000:]}
        final, summary = parse_events(stdout)
        meta = {**base, 'status': 'ok', 'returncode': proc.returncode,
                'elapsed': time.monotonic()-started, 'summary': summary,
                'final_text': final if final is not None else stdout[-20000:],
                'stderr': stderr[-4000:]}
        try:
            if proc.returncode:
                raise ValueError(f'CLI exited {proc.returncode}')
            answer_file = Path(tmp)/'answer.json'
            candidates = [answer_file.read_text()] if answer_file.exists() else []
            candidates += [final] if isinstance(final, str) else []
            candidates += [stdout]
            answer, error = None, None
            for text in candidates:
                try:
                    answer = extract_json(text)
                    break
                except ValueError as exc:
                    error = exc
            if answer is None:
                raise error or ValueError('No answer')
        except ValueError as exc:
            meta.update(status='invalid', error=str(exc))
            answer = None
        # Environment failures (not agent behaviour) are discarded so --resume reruns them.
        if any(marker in stdout for marker in INFRA_MARKERS) or (
                proc.returncode and re.search(r'API Error: 5\d\d', str(final) + stdout[-4000:])):
            meta.update(status='infra_error', discarded_answer=answer,
                        error='environment I/O failure seen in session')
            answer = None
        return answer, meta


def run(root, output, command, timeout=300, token_budget=8000, temp_root=None,
        condition='base', seeds=(None,), concurrency=1, corpora=None, extra_path=None,
        resume=False, isolate=False):
    root, output = Path(root), Path(output)
    ids = [item['corpus_id'] for item in json.loads((root/'manifest.json').read_text())]
    if corpora:
        ids = [c for c in ids if c in set(corpora)]
    jobs = []
    for seed in seeds:
        out = output if seed is None else output/f'seed{seed}'
        out.mkdir(parents=True, exist_ok=True)
        for cid in ids:
            log = out/f'{cid}.run.json'
            if resume and log.exists() and json.loads(log.read_text()).get('status') not in ('error', 'infra_error'):
                continue  # completed earlier; invalid/timeout runs are agent outcomes, not rerun
            # A failed repeat must not leave a successful old answer to be scored.
            (out/f'{cid}.json').unlink(missing_ok=True)
            jobs.append((cid, out))

    def work(job):
        cid, out = job
        try:
            answer, meta = run_one(root/cid, command, timeout, token_budget, temp_root,
                                   condition, extra_path, isolate)
        except Exception as exc:  # e.g. staging I/O errors; keep the other jobs running
            answer, meta = None, {'condition': condition, 'status': 'error', 'error': repr(exc),
                                  'elapsed': 0.0}
        meta['corpus_id'] = cid
        (out/f'{cid}.run.json').write_text(json.dumps(meta, indent=2)+'\n')
        if answer is not None:
            (out/f'{cid}.json').write_text(json.dumps(answer, indent=2)+'\n')
        print(f"{out.name}/{cid}: {meta['status']} {meta['elapsed']:.0f}s", flush=True)
        return meta['status']

    if concurrency <= 1:
        return [work(j) for j in jobs]
    with ThreadPoolExecutor(concurrency) as pool:
        return list(pool.map(work, jobs))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root'); p.add_argument('output')
    p.add_argument('--backend', choices=COMMANDS, default='codex')
    p.add_argument('--command', help='Shell-quoted argv template; {prompt} and {token_budget} supported; no shell execution')
    p.add_argument('--timeout', type=float, default=300)
    p.add_argument('--token-budget', type=int, default=8000)
    p.add_argument('--condition', choices=CONDITIONS, default='base')
    p.add_argument('--seeds', type=int, default=0, help='Independent repeats; 0 writes directly to output')
    p.add_argument('--concurrency', type=int, default=1)
    p.add_argument('--corpora', nargs='*', help='Subset of corpus IDs')
    p.add_argument('--temp-root', help='Staging root; keep it outside the repository')
    p.add_argument('--extra-path', help='Directory prepended to PATH (e.g. analysis venv bin)')
    p.add_argument('--resume', action='store_true', help='Skip corpora that already have a valid answer')
    p.add_argument('--isolate', action='store_true',
                   help='bubblewrap: private /tmp; mask repo, other staging dirs and ~/.claude/projects')
    a = p.parse_args()
    if a.timeout <= 0 or a.token_budget <= 0 or a.concurrency <= 0:
        p.error('timeout, token budget and concurrency must be positive')
    run(a.root, a.output, shlex.split(a.command) if a.command else COMMANDS[a.backend],
        a.timeout, a.token_budget, a.temp_root, a.condition,
        tuple(range(1, a.seeds+1)) if a.seeds else (None,), a.concurrency, a.corpora, a.extra_path,
        a.resume, a.isolate)
