#!/bin/bash
# Isolated (bubblewrap) runs: reruns quarantined base sessions, then the confound-check condition.
set -u
cd /home/lunarz/agentic_literary_discovery
export UV_PROJECT_ENVIRONMENT="$PWD/bench/.venv" UV_CACHE_DIR="$PWD/bench/.uv-cache"
R=bench/runs/2026-11-04
run() {
  uv run --with pandas,numpy,pyarrow python -m bench.run_agents $R/pilot/generated $R/$1 --backend claude \
    --condition $2 --timeout 1200 --seeds 3 --concurrency 6 --resume --isolate \
    --temp-root $HOME/.cache/bench-agent-runs --extra-path $HOME/.cache/bench-agent-venv/bin >> $R/$1.log 2>&1
}
run claude_base base
echo base-resume-done
run claude_confound_check confound_check
echo cc-done
run claude_confound_check confound_check   # reruns infra_error/error only
echo chain-done
