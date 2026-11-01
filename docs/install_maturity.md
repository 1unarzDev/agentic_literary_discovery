# Installer / worker maturity checklist

Status as of ald 0.1.7 (coordinator with migrations 0001-0003).

Legend:
- **PASS (live)**: verified on a real machine.
- **PASS (container)**: verified in a clean Ubuntu 24.04 container (non-root, no sudo, no systemd, no GPU).
- **PASS (unit)**: covered by tests only.
- **REVIEW**: code-reviewed, no hardware available.

| # | check | Windows 11 (COLLIN, RTX 3060) | Linux (4070 Ti S + container) | macOS |
|---|---|---|---|---|
| 1 | One-liner, never prompts, never hangs on stdin | PASS (live, over SSH and a one-shot task) | PASS (live + container: `curl \| sh`) | REVIEW (all children use `</dev/null`; brew `NONINTERACTIVE=1`) |
| 2 | uv installed user-local, ald with its own Python 3.12 | PASS (live) | PASS (live + container) | REVIEW |
| 3 | Ollama installed silently | PASS (live: winget `--source winget`, fallback `OllamaSetup.exe /VERYSILENT`) | PASS (container: user-local `~/.local/ollama`, no sudo; `.tar.zst` without zstd via Python 3.14) | REVIEW (brew if present, else `Ollama.app` to `/Applications` or `~/Applications`; Apple Silicon/Intel brew paths) |
| 4 | Ollama started and kept running by the worker | PASS (live: the tray app cannot start in session 0, so the worker falls back to `ollama serve`; also restarted after it died with an SSH session) | PASS (live) | REVIEW |
| 5 | Tier detection | PASS (live: 12 GB → t12, label allowed) | PASS (live: 16 GB → t16; container: cpu) | PASS (unit: Apple 65% of unified memory) |
| 6 | Pinned models pulled, digests verified, 100% on GPU | PASS (live: 5 models, `/api/ps` 100%) | PASS (live) | REVIEW |
| 7 | Tier Ollama settings (NUM_PARALLEL / FLASH_ATTENTION / KEEP_ALIVE) persisted, Ollama restarted | PASS (live: `setx`, NP 2→4 applied by an auto-update) | PASS (live: env compared via `/proc`, restarted; systemd drop-in via `sudo -n` only) | REVIEW (`launchctl setenv`, re-applied every start) |
| 8 | `ald doctor --bench` reports passages/h | PASS (live) | PASS (container; on the shared GPU the bench is skipped when `--gpu-lock` is busy) | REVIEW |
| 9 | Service installed; always rewritten on re-install | PASS (live: XML task). Settings: S4U from an admin shell; interactive task from a normal shell (verified non-elevated); PT0S, battery OK, restart 999/1 min, logon + boot + 10-min repeat triggers, IgnoreNew | PASS (live: systemd `--user`, `Restart=always`, linger enabled without a prompt) | PASS (unit: plist validated with `plistlib`; RunAtLoad, KeepAlive=true, ThrottleInterval 30, PATH incl. Homebrew) |
| 10 | Installer starts and verifies the worker (process alive + coordinator round trip), prints SUCCESS / FAILED | PASS (live) | PASS (live); container: clean `FAILED`, exit 1 when there is no systemd | REVIEW (`launchctl print` + `ald service verify`) |
| 11 | Survives logoff / reboot | PASS (live: S4U task runs in session 0 at boot with nobody signed in; trigger tested with `schtasks /Run`; reboot not tested, to avoid disrupting production) | PASS (live: linger=yes, unit enabled) | REVIEW (LaunchAgent: runs at login, not before) |
| 12 | Keep-awake while working | PASS (live: `powercfg /requests` lists `pythonw.exe` under SYSTEM; also held during the install) | PASS (live: `systemd-inhibit` sleep:idle:handle-lid-switch) | REVIEW (`caffeinate -i -m -s -w <pid>`; the lid still sleeps without an external display) |
| 13 | Leases jobs, uploads results | PASS (live: test wave and real waves) | PASS (live: waits for `--gpu-lock` before leasing) | REVIEW |
| 14 | Kill mid-shard → partial uploaded, job resumed with `skip_passage_ids` | PASS (live: 4/16 and 365/400 partials recovered, then resumed) | PASS (unit / e2e fakes) | PASS (unit) |
| 15 | Auto-update without intervention | PASS (live: 0.1.3→0.1.4 and 0.1.5→0.1.6 via the detached helper and task relaunch; the service definition refreshes itself) | PASS (live: 0.1.3→0.1.5 via exec; unit refreshed with `--gpu-lock` kept) | PASS (unit: plist refresh keeps args) |
| 16 | `ald status [--watch]`, `ald fleet [--watch]`, `ald config` | PASS (live; ASCII fallback on cp1252 consoles) | PASS (live) | REVIEW |
| 17 | Non-admin re-run after an admin install | PASS (live: keeps the admin-created task) | n/a | n/a |

Known limitations:
- Windows from a non-admin shell: the task runs only while the user is signed in.
- A reboot was not exercised on COLLIN (production box); only the boot trigger is registered.
- macOS: no hardware was available; everything is code review plus unit tests (plist validated with `plistlib`).
- Linux with a *system* `ollama.service`: tier settings need `sudo` once, and ald prints the exact command.
  The default user-local Ollama needs no sudo.
- Installing NVIDIA drivers on Linux always needs sudo. ald detects a GPU without a driver and says so; without
  a driver it runs the cpu tier.
