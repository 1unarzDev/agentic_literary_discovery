# Volunteering a computer to ALD

ALD labels passages of 19th- and early-20th-century fiction with open-weight language models. Your computer runs
one fixed, pinned model locally through [Ollama](https://ollama.com). It downloads small batches of passages,
labels them, and uploads the results. Nothing else on your computer is read or uploaded.

You need an **invite code** (single use) from the project admin.

## Install: one command

The installer is fully automatic and never asks questions. It is safe to run again; a re-run upgrades in place.

**Windows 10/11** (PowerShell; use *Run as administrator* if you can, see below):

```powershell
$env:INVITE = "YOUR-INVITE-CODE"; iwr -useb https://ald-coordinator.lunarzdev.workers.dev/install.ps1 | iex
```

**macOS (Apple Silicon or Intel) and Linux** (Terminal):

```sh
curl -fsSL https://ald-coordinator.lunarzdev.workers.dev/install.sh | sh -s -- YOUR-INVITE-CODE
```

Optional settings:

- A display name: Windows `$env:ALD_NAME = "my-desktop"` before the command; macOS/Linux `... | sh -s -- CODE --name my-desktop`.
- Linux only, `--system-ollama`: install Ollama with its official script as a system service in `/usr/local`.
  This uses `sudo` and may ask for your password. Without it, Ollama goes in `~/.local/ollama`, needs no sudo,
  and ald starts and stops it.
- macOS/Linux, `--gpu-lock /path/to/lockfile`: share the GPU with other programs. The lock is an advisory
  `flock`, compatible with `flock /path/to/lockfile <cmd>`. The background service then runs
  `ald work --gpu-lock …`. The install-time benchmark is skipped if the lock is busy.

## What the installer does (5-30 minutes, most of it downloading models)

1. Installs [uv](https://docs.astral.sh/uv/) for your user only. uv installs `ald` with its own Python 3.12.
2. Installs Ollama if it is missing:
   - Windows: `winget`, falling back to the official silent installer. No admin rights needed.
   - macOS: Homebrew if you have it, otherwise `Ollama.app` from ollama.com.
   - Linux: user-local, or the official script with `--system-ollama`.
3. Joins the project with your invite (`ald join`).
4. Detects your GPU and picks a **tier**, which decides which tasks your machine can take:

   | GPU memory | tier | tasks |
   |---|---|---|
   | ≥ 23.5 GB | t24 | all |
   | ≥ 15.5 GB | t16 | all |
   | ≥ 11.5 GB (e.g. RTX 3060 12 GB) | t12 | label, workcheck, cloze, alt_label, embed |
   | ≥ 7.5 GB | t8 | workcheck, embed |
   | none | cpu | embed |

   Apple Silicon counts about 65% of unified memory as GPU memory.
5. Sets Ollama's settings for your tier (`OLLAMA_NUM_PARALLEL`, `OLLAMA_FLASH_ATTENTION=1`,
   `OLLAMA_KEEP_ALIVE=30m`) and restarts Ollama:
   - Windows: user environment variables.
   - macOS: `launchctl setenv`.
   - Linux: `~/.config/ald/ollama.env`, or a systemd drop-in for a system Ollama.
6. Downloads the pinned models (about 3-20 GB depending on tier) and checks their exact digests.
7. Runs a short benchmark (`ald doctor --bench`). It prints your passages per hour and an ETA for your share.
8. Installs a background service that runs `ald work`:
   - Windows: Scheduled Task `ald-worker`. From an **Administrator** PowerShell it starts at boot and keeps
     running after you sign out. From a normal PowerShell it runs while you are signed in.
   - macOS: LaunchAgent `org.ald.worker`. It runs while you are logged in.
   - Linux: systemd user service `ald-worker`. With lingering enabled, which the installer tries without a
     password, it also runs at boot.

While it works, ald keeps the computer from going to sleep:
- Windows: `SetThreadExecutionState`.
- macOS: `caffeinate`.
- Linux: `systemd-inhibit`.

When it is idle or stopped, the model unloads from GPU memory after 30 minutes.

## Checking on it

The installer ends with `SUCCESS: ald is installed and working in the background` once it has confirmed that the
worker process is running and has reached the coordinator. If it ends with `FAILED`, re-run the same command,
then send the output to the project admin.

```sh
ald status              # one screen: running?, keep-awake, power, tier/GPU, model on-GPU %, current job and
                        #   progress, passages/h, disk, pending uploads, version / update available
ald status --watch      # the same, refreshed every 5 s (Ctrl-C to quit)
ald config              # settings menu (see below)
ald service status      # the OS view of the background service
ald doctor              # hardware, tier, Ollama, coordinator, bandwidth (add --bench to re-benchmark)
```

Example of `ald status` (RTX 3060, Windows):

```text
╭──────────────────────────── ald status - COLLIN ────────────────────────────╮
│ Worker       working  pid 28372 (service)                                    │
│ Coordinator  https://ald-coordinator.lunarzdev.workers.dev  last contact 20s │
│ Keep-awake   held                                                            │
│ Power        desktop (no battery)                                            │
│ Tier / GPU   t12  NVIDIA GeForce RTX 3060 (12.0 GB)                          │
│ Ollama       gemma4:12b-it-q4_K_M 100% on GPU                                │
│ Job          w01_disc_rand_a_disc_00181 (label) ██████░░░░ 60%  ETA 6m       │
│ Version      0.1.6  (latest)                                                 │
╰──────────────────────────────────────────────────────────────────────────────╯
```

The full output is in `docs/screenshots/ald_status.txt` (and `.svg`).

Logs are in the ald data folder (`ald status` prints its path), under `logs/worker.log`:
- Windows: `%LOCALAPPDATA%\ald\logs\worker.log`
- Linux: `~/.local/share/ald/logs/worker.log`
- macOS: `~/Library/Application Support/ald/logs/worker.log`

Updates install themselves. The worker checks for a new version every 5-10 minutes and upgrades between
batches. No action needed. The background service restarts the worker if it ever exits: Windows retries every
minute and re-triggers every 10 minutes; launchd uses KeepAlive; systemd uses `Restart=always`.

## Settings (`ald config`)

`ald config` opens a small menu. `ald config show` and `ald config set KEY VALUE` do the same from scripts.
The background service reads these settings every time it starts, so you never edit the task or unit by hand.
After saving, the menu offers to restart the worker.

| key | meaning |
|---|---|
| `name` | display name |
| `disk_budget_gb` | disk ald may use (default 10 GB; it always leaves 20 GB free) |
| `active_hours` | work only in this daily window, e.g. `22:00-07:00` |
| `max_concurrency` | upper bound for the auto-tuned number of parallel requests (default 8) |
| `stages` | only take these stages, e.g. `label,workcheck` |
| `gpu_lock` | share the GPU with other programs (Linux/macOS) |
| `auto_update` | `yes` / `no` |
| `keep_awake` | `no` lets the computer sleep while working |

## Stopping, pausing, uninstalling

- **Pause only at night / by day:** `ald config set active_hours 22:00-07:00 --restart`.
- **Pause now:** `ald service uninstall` stops the worker and removes the background service. Work in progress
  is uploaded as partial results and handed back. To resume, run the install command again; it skips what is
  already installed and needs no new invite, or run `ald service install`.
- **Run by hand instead:** `ald work` (Ctrl-C uploads partial results and stops), or `ald work --hours 3` or
  `ald work --until 07:00`.
- **Uninstall completely:**
  1. `ald service uninstall`
  2. `uv tool uninstall ald`
  3. Delete the ald config and data folders:
     - Windows: `%LOCALAPPDATA%\ald`
     - Linux: `~/.config/ald` and `~/.local/share/ald`
     - macOS: `~/Library/Application Support/ald`
  4. Optional: remove the models with `ollama rm <model>` (see `ollama list`), and uninstall Ollama:
     - Windows: Settings > Apps.
     - macOS: delete `Ollama.app`, or `brew uninstall ollama`.
     - Linux: `rm -rf ~/.local/ollama ~/.ollama`.
  5. On Windows, optionally remove the user variables `OLLAMA_NUM_PARALLEL`, `OLLAMA_FLASH_ATTENTION` and
     `OLLAMA_KEEP_ALIVE`.

## Notes

- **Keep the machine plugged in.** On battery, ald stops taking new work below 30% charge.
- **Laptops:**
  - Closing the lid may still put the machine to sleep, depending on your power settings. Keep it open, or set
    "when I close the lid: do nothing" while plugged in.
    - On macOS, closing the lid always sleeps unless an external display is attached.
    - On Linux, ald asks logind to ignore the lid switch while it works.
  - Sleep never loses work: unfinished batches are uploaded or handed back when the machine wakes.
- **Games and other GPU programs:** ald uses most of your GPU memory while it works. Stop it with
  `ald service uninstall`, or schedule it with `ald work --until HH:MM`.
- **Sharing a GPU with other programs on Linux/macOS:** `ald work --gpu-lock /path/to/lockfile` takes an
  advisory `flock` before each batch and frees the GPU between batches when another process is waiting.
- **Disk:** ald keeps at least 20 GB free on the disk it uses, and stays within 10 GB by default
  (`ald work --disk-budget-gb N` changes the budget).
- **Network:** about 2-4 MB per batch of ~400 passages, plus the one-time model download.
- **Privacy:**
  - Uploaded: model outputs for the passages you were sent, plus speed statistics.
  - Recorded at join: your machine's display name, OS, GPU model, and memory sizes.
