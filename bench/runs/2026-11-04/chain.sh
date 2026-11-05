#!/bin/bash
# Orchestration used for the 2026-11-04 study (staging outside the repo, on disk).
set -u
cd /home/lunarz/agentic_literary_discovery
export UV_PROJECT_ENVIRONMENT="$PWD/bench/.venv" UV_CACHE_DIR="$PWD/bench/.uv-cache"
R=bench/runs/2026-11-04
until ! pgrep -f "python -m bench.run_agents.*claude_base" >/dev/null; do sleep 10; done
quarantine() {  # sessions that saw environment I/O failures are not agent behaviour
  for f in $(grep -lis "quota\|No space left" $R/$1/seed*/*.run.json); do
    b=${f%.run.json}; d=$R/quarantine/$(dirname ${f#$R/}); mkdir -p $d; mv $b.run.json $d/; mv $b.json $d/ 2>/dev/null; echo "quarantined $b"
  done
}
run() {
  uv run --with pandas,numpy,pyarrow python -m bench.run_agents $R/pilot/generated $R/$1 --backend claude \
    --condition $2 --timeout 1200 --seeds 3 --concurrency 6 --resume \
    --temp-root $HOME/.cache/bench-agent-runs --extra-path /tmp/bench-agent-venv/bin >> $R/$1.log 2>&1
}
quarantine claude_base
run claude_base base
quarantine claude_base
run claude_confound_check confound_check
quarantine claude_confound_check
run claude_confound_check confound_check
quarantine claude_base; run claude_base base
echo chain-done
