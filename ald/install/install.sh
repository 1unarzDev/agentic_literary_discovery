#!/bin/sh
# ald one-line installer for macOS and Linux. Safe to re-run. Never prompts.
#
#   curl -fsSL https://<coordinator>/install.sh | sh -s -- <INVITE> [--name NAME] [--no-service] [--no-work]
#                                                         [--system-ollama] [--gpu-lock PATH]
#
#   --system-ollama  Linux: install Ollama with the official script (system service in /usr/local; needs
#                    sudo and may ask for your password). Default: a user-local Ollama in ~/.local/ollama,
#                    no sudo, started and stopped by ald.
#   --gpu-lock PATH  share the GPU with other programs through flock(2) on PATH (see `ald work --help`).
#
# The coordinator substitutes __COORDINATOR_URL__ when serving this file;
# otherwise pass --coordinator URL or set ALD_COORDINATOR.
set -eu

COORD="${ALD_COORDINATOR:-__COORDINATOR_URL__}"
INVITE="${INVITE:-}"
NAME="${ALD_NAME:-$(hostname 2>/dev/null || uname -n)}"
DO_SERVICE=1
DO_WORK=1
SYSTEM_OLLAMA=0
GPU_LOCK=""

while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="$2"; shift 2 ;;
    --coordinator) COORD="$2"; shift 2 ;;
    --no-service) DO_SERVICE=0; shift ;;
    --no-work) DO_WORK=0; shift ;;
    --system-ollama) SYSTEM_OLLAMA=1; shift ;;
    --gpu-lock) GPU_LOCK="$2"; shift 2 ;;
    -h|--help) sed -n '2,13p' "$0" 2>/dev/null || true; exit 0 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) INVITE="$1"; shift ;;
  esac
done

if [ -t 1 ]; then B='\033[1;34m'; Y='\033[1;33m'; R='\033[1;31m'; N='\033[0m'; else B=''; Y=''; R=''; N=''; fi
say()  { printf "${B}==>${N} %s\n" "$*"; }
warn() { printf "${Y}!! ${N} %s\n" "$*" >&2; }
die()  { printf "${R}xx ${N} %s\n" "$*" >&2; exit 1; }
# Under `curl | sh` our stdin IS this script: no child may read it (or prompt on it).
run() { "$@" </dev/null; }

# (Do not compare against the placeholder literally: the coordinator replaces every occurrence.)
case "$COORD" in http://*|https://*) ;; *) die "coordinator URL unknown: pass --coordinator URL or set ALD_COORDINATOR" ;; esac
COORD="${COORD%/}"
command -v curl >/dev/null 2>&1 || die "curl is required"
OS="$(uname -s)"
ARCH="$(uname -m)"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/.local/ollama/bin:$PATH"
if [ "$OS" = "Darwin" ]; then
  # Homebrew is often missing from PATH in non-login shells (Apple Silicon: /opt/homebrew, Intel: /usr/local).
  for d in /opt/homebrew/bin /usr/local/bin; do [ -x "$d/brew" ] && PATH="$d:$PATH"; done
  export HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 HOMEBREW_NO_ENV_HINTS=1 NONINTERACTIVE=1
fi

# Keep the machine awake while installing (model downloads take a while; an upgrade stops the worker).
if [ "$OS" = "Darwin" ]; then
  caffeinate -i -m -w $$ </dev/null >/dev/null 2>&1 &
elif command -v systemd-inhibit >/dev/null 2>&1; then
  systemd-inhibit --what=sleep:idle --who=ald-install --why="installing ald" --mode=block \
    tail --pid=$$ -f /dev/null </dev/null >/dev/null 2>&1 &
fi

# 1. uv -----------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  say "Installing uv (official Astral installer, user-local, no sudo)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
command -v uv >/dev/null 2>&1 || die "uv installation failed"

# 2. ald ----------------------------------------------------------------------
PING="$(curl -fsSL "$COORD/v1/ping")" || die "coordinator not reachable at $COORD"
WHEEL="$(printf '%s' "$PING" | sed -n 's/.*"wheel_url"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
LATEST="$(printf '%s' "$PING" | sed -n 's/.*"latest_client_version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
[ -n "$WHEEL" ] || die "/v1/ping did not return wheel_url"
CURRENT="$(run ald version 2>/dev/null || true)"
if [ -n "$CURRENT" ] && [ "$CURRENT" = "$LATEST" ]; then
  say "ald $CURRENT already installed"
else
  say "Installing ald ${LATEST:-latest} with uv (Python 3.12)"
  run uv tool install --force --python 3.12 "$WHEEL"
  run uv tool update-shell >/dev/null 2>&1 || true
fi
command -v ald >/dev/null 2>&1 || die "ald not on PATH (try: export PATH=\"\$HOME/.local/bin:\$PATH\")"

# 3. Ollama -------------------------------------------------------------------
ollama_up() { curl -fsS -m 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1; }
have_ollama() {
  command -v ollama >/dev/null 2>&1 || ollama_up || [ -d /Applications/Ollama.app ] || [ -d "$HOME/Applications/Ollama.app" ]
}

# Linux, no sudo: the official release tarball unpacked into ~/.local/ollama (bin/ollama + lib/ollama).
install_ollama_user_linux() {
  case "$ARCH" in x86_64|amd64) A=amd64 ;; aarch64|arm64) A=arm64 ;; *) die "unsupported CPU architecture $ARCH" ;; esac
  DEST="$HOME/.local/ollama"
  mkdir -p "$DEST"
  fetch_extract() {  # $1 = file name without extension
    U="https://ollama.com/download/$1"
    if curl -fsIL "$U.tar.zst" >/dev/null 2>&1; then
      if command -v zstd >/dev/null 2>&1; then
        curl -fL --progress-bar "$U.tar.zst" | zstd -dc | tar -xf - -C "$DEST"
      else
        # No zstd binary: Python 3.14's tarfile reads .tar.zst (uv fetches that Python; no sudo).
        TMPF="$(mktemp)"
        curl -fL --progress-bar -o "$TMPF" "$U.tar.zst"
        run uv run --no-project --python 3.14 python -c \
          'import sys,tarfile; tarfile.open(sys.argv[1], "r:zst").extractall(sys.argv[2], filter="tar")' "$TMPF" "$DEST"
        rm -f "$TMPF"
      fi
    else
      curl -fL --progress-bar "$U.tgz" | tar -xzf - -C "$DEST"
    fi
  }
  say "Installing Ollama for this user in $DEST (no sudo)"
  fetch_extract "ollama-linux-$A"
  if [ -e /dev/kfd ] || command -v rocm-smi >/dev/null 2>&1; then
    say "AMD GPU detected: adding the ROCm runtime"
    fetch_extract "ollama-linux-$A-rocm" || warn "ROCm runtime download failed; Ollama will use the CPU"
  fi
  [ -x "$DEST/bin/ollama" ] || die "Ollama download failed"
}

if ! have_ollama; then
  if [ "$OS" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then
      say "Installing Ollama with Homebrew"
      run brew install ollama || die "brew install ollama failed"
    else
      say "Installing Ollama.app from ollama.com (Homebrew not found)"
      TMP="$(mktemp -d)"
      curl -fL --progress-bar -o "$TMP/Ollama.zip" https://ollama.com/download/Ollama-darwin.zip
      run ditto -x -k "$TMP/Ollama.zip" "$TMP"
      if [ -w /Applications ]; then rm -rf /Applications/Ollama.app; mv "$TMP/Ollama.app" /Applications/
      else mkdir -p "$HOME/Applications"; rm -rf "$HOME/Applications/Ollama.app"; mv "$TMP/Ollama.app" "$HOME/Applications/"; fi
      rm -rf "$TMP"
    fi
  elif [ "$SYSTEM_OLLAMA" = 1 ]; then
    say "Installing Ollama with the official script (system service in /usr/local; uses sudo)"
    curl -fsSL https://ollama.com/install.sh | sh || die "the official Ollama installer failed"
  else
    install_ollama_user_linux
  fi
fi
if ! command -v nvidia-smi >/dev/null 2>&1 && [ "$OS" = "Linux" ] && lspci 2>/dev/null | grep -qi nvidia; then
  warn "NVIDIA GPU found but no driver (nvidia-smi missing): ald will use the CPU tier. Installing the driver needs sudo"
  warn "(e.g. Ubuntu: sudo ubuntu-drivers install); re-run this installer afterwards."
fi
# `ald setup` (below) starts Ollama if needed, applies the tier's OLLAMA_* settings and restarts it.

# 4. join, models, benchmark ---------------------------------------------------
if [ -n "$INVITE" ]; then
  say "Joining $COORD as $NAME"
  run ald join "$COORD" "$INVITE" --name "$NAME" || die "join failed (is the invite valid and unused?)"
else
  warn "no INVITE given; skipping join (fine if this machine already joined)"
fi
say "Configuring Ollama, pulling and verifying the pinned models for this machine's tier"
run ald setup --yes || warn "setup reported problems (see above)"
say "Benchmarking (~1-2 min)"
run ald doctor --bench || warn "benchmark failed; work will auto-tune from scratch"

# 5. background service + work -------------------------------------------------
EXTRA=""
[ -n "$GPU_LOCK" ] && EXTRA="--gpu-lock $GPU_LOCK"
SERVICE_OK=0
if [ "$DO_SERVICE" = 1 ]; then
  say "Installing the background service (resumes after reboot)"
  if [ -n "$EXTRA" ]; then run ald service install --args "$EXTRA" || true; else run ald service install || true; fi
  sleep 3
  if [ "$OS" = "Darwin" ]; then
    launchctl print "gui/$(id -u)/org.ald.worker" >/dev/null 2>&1 && SERVICE_OK=1
  else
    systemctl --user is-active --quiet ald-worker.service 2>/dev/null && SERVICE_OK=1
    if [ "$SERVICE_OK" = 1 ]; then
      # Start at boot without an open login session (no password prompt: --no-ask-password).
      loginctl --no-ask-password enable-linger "$(id -un)" >/dev/null 2>&1 \
        || warn "could not enable lingering: the service runs while you are logged in (sudo loginctl enable-linger $(id -un) fixes that)"
    fi
  fi
  [ "$SERVICE_OK" = 1 ] || warn "the background service could not be started here (no systemd user session?)"
fi

say "Summary"
run ald work --dry-run || true
run ald status --local || true

if [ "$SERVICE_OK" = 1 ]; then
  say "ald work is running as a background service. Check: 'ald status --local'; logs: 'ald service status'; stop and remove: 'ald service uninstall'."
elif [ "$DO_WORK" = 1 ] && [ "$DO_SERVICE" = 0 ]; then
  say "Starting ald work (Ctrl-C uploads partial results and releases leases)"
  exec ald work --keep-awake $EXTRA </dev/null
else
  say "Start working with: ald work   (or: nohup ald work >/dev/null 2>&1 &)"
fi
