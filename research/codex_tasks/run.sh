#!/usr/bin/env bash
# usage: run.sh <task-name>   (runs codex exec on research/codex_tasks/<task>.md, logs to research/codex_tasks/logs/)
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p research/codex_tasks/logs
export CODEX_LB_API_KEY="$(awk '$1=="set" && $3=="CODEX_LB_API_KEY"{ $1=$2=$3=""; sub(/^ +/,""); gsub(/^["\x27]|["\x27]$/,""); print }' "$HOME/.config/caelestia/.env.secrets")"
[ -n "$CODEX_LB_API_KEY" ] || { echo "no key"; exit 1; }
t="$1"
cat research/codex_tasks/COMMON.md research/codex_tasks/"$t".md | codex exec -C "$PWD" --skip-git-repo-check - > research/codex_tasks/logs/"$t".log 2>&1
echo "done $t"
