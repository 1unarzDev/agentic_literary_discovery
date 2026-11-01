#!/bin/sh
# ald one-line installer for macOS and Linux. Safe to re-run.
#
#   curl -fsSL https://<coordinator>/install.sh | sh -s -- <INVITE> [--name NAME] [--no-service] [--no-work]
#
# The coordinator substitutes __COORDINATOR_URL__ when serving this file;
# otherwise pass --coordinator URL or set ALD_COORDINATOR.
set -eu

COORD="${ALD_COORDINATOR:-__COORDINATOR_URL__}"
INVITE="${INVITE:-}"
NAME="$(hostname 2>/dev/null || uname -n)"
DO_SERVICE=1
DO_WORK=1

while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="$2"; shift 2 ;;
    --coordinator) COORD="$2"; shift 2 ;;
    --no-service) DO_SERVICE=0; shift ;;
    --no-work) DO_WORK=0; shift ;;
    -h|--help) sed -n '2,8p' "$0" 2>/dev/null || true; exit 0 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) INVITE="$1"; shift ;;
  esac
done

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!! \033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mxx \033[0m %s\n' "$*" >&2; exit 1; }

# (Do not compare against the placeholder literally: the coordinator replaces every occurrence.)
case "$COORD" in http://*|https://*) ;; *) die "coordinator URL unknown: pass --coordinator URL or set ALD_COORDINATOR" ;; esac
COORD="${COORD%/}"
command -v curl >/dev/null 2>&1 || die "curl is required"
OS="$(uname -s)"

# 1. uv -----------------------------------------------------------------------
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  say "Installing uv (official Astral installer, user-local, no sudo)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
command -v uv >/dev/null 2>&1 || die "uv installation failed"

# 2. ald ----------------------------------------------------------------------
PING="$(curl -fsSL "$COORD/v1/ping")" || die "coordinator not reachable at $COORD"
WHEEL="$(printf '%s' "$PING" | sed -n 's/.*"wheel_url"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
LATEST="$(printf '%s' "$PING" | sed -n 's/.*"latest_client_version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
[ -n "$WHEEL" ] || die "/v1/ping did not return wheel_url"
CURRENT="$(ald version 2>/dev/null || true)"
if [ -n "$CURRENT" ] && [ "$CURRENT" = "$LATEST" ]; then
  say "ald $CURRENT already installed"
else
  say "Installing ald ${LATEST:-latest} with uv (Python 3.12)"
  uv tool install --force --python 3.12 "$WHEEL"
  uv tool update-shell >/dev/null 2>&1 || true
fi
command -v ald >/dev/null 2>&1 || die "ald not on PATH (try: export PATH=\"\$HOME/.local/bin:\$PATH\")"

# 3. Ollama -------------------------------------------------------------------
ollama_up() { curl -fsS -m 2 http://localhost:11434/api/version >/dev/null 2>&1; }
if ! command -v ollama >/dev/null 2>&1 && ! ollama_up && [ ! -d /Applications/Ollama.app ]; then
  if [ "$OS" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then
      say "Installing Ollama with Homebrew"
      brew install ollama
    else
      say "Installing Ollama.app from ollama.com (no Homebrew found)"
      TMP="$(mktemp -d)"
      curl -fsSL -o "$TMP/Ollama.zip" https://ollama.com/download/Ollama-darwin.zip
      ditto -x -k "$TMP/Ollama.zip" "$TMP"
      if [ -w /Applications ]; then mv "$TMP/Ollama.app" /Applications/; else mkdir -p "$HOME/Applications"; mv "$TMP/Ollama.app" "$HOME/Applications/"; fi
      rm -rf "$TMP"
    fi
  else
    say "Installing Ollama with the official script (https://ollama.com/install.sh)."
    say "It installs to /usr/local and creates a systemd service, so it will ask for your sudo password."
    curl -fsSL https://ollama.com/install.sh | sh
  fi
fi

if ! ollama_up; then
  say "Starting Ollama"
  if [ "$OS" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1 && brew list ollama >/dev/null 2>&1; then brew services start ollama >/dev/null
    elif [ -d /Applications/Ollama.app ]; then open -a Ollama
    elif [ -d "$HOME/Applications/Ollama.app" ]; then open -a "$HOME/Applications/Ollama.app"
    fi
  else
    if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files ollama.service >/dev/null 2>&1 \
       && systemctl is-enabled ollama >/dev/null 2>&1; then
      systemctl is-active ollama >/dev/null 2>&1 || warn "ollama.service is not active; start it with: sudo systemctl start ollama"
    else
      nohup ollama serve >/dev/null 2>&1 &
    fi
  fi
  i=0; while ! ollama_up && [ $i -lt 30 ]; do sleep 1; i=$((i+1)); done
  ollama_up || die "Ollama did not start; start it and re-run this script"
fi

# 4. join, models, benchmark ---------------------------------------------------
if [ -n "$INVITE" ]; then
  say "Joining $COORD as $NAME"
  ald join "$COORD" "$INVITE" --name "$NAME"
else
  warn "no INVITE given; skipping join (fine if this machine already joined)"
fi
say "Pulling and verifying the pinned models for this machine's tier"
ald setup --yes || warn "setup reported problems (see above)"
say "Benchmarking (~60 s)"
ald doctor --bench || warn "benchmark failed; work will auto-tune from scratch"

# 5. background service + work -------------------------------------------------
if [ "$DO_SERVICE" = 1 ]; then
  say "Installing the background service (resumes after reboot)"
  ald service install
fi

say "Summary"
ald work --dry-run || true
ald status --local || true

if [ "$DO_SERVICE" = 1 ]; then
  say "ald work is running as a background service. Logs: 'ald service status'; stop: 'ald service uninstall'."
elif [ "$DO_WORK" = 1 ]; then
  say "Starting ald work (Ctrl-C uploads partial results and releases leases)"
  exec ald work --keep-awake
fi
