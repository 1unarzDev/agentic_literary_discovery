# ald performance report: label stage

**Setup.**
- Stage and model: label, `gemma4:12b-it-q4_K_M`, pinned prompt, `num_ctx` 8192, `num_predict` 400, temperature 0.
- Passages: the bundled sample passages (`ald/src/ald/data/sample_passages.jsonl`), about 350 words each, with context.
- Server: Ollama 0.40.13 on both machines.
- Throughput measured with `ald doctor --bench --stages label --levels 1,2,4,6,8 --seconds 300` (60 s per level; a
  level also waits for its in-flight requests).
- Convergence measured with `ald/tools/tune_check.py`: the worker's own `ConcurrencyTuner`, real Ollama, starting at
  c=1, 100 passages.
- `c` is the number of concurrent requests ald sends. `OLLAMA_NUM_PARALLEL` (NP) is the number of KV slots
  Ollama allocates at model load; requests beyond NP wait in Ollama's queue.

## Windows 11: RTX 3060 12 GB (COLLIN), tier t12

`OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KEEP_ALIVE=30m`. The ald worker was paused during the runs.
The model was 100% on GPU (`/api/ps`) in every run.

Passages/hour (gen tok/s in brackets; mean latency per passage):

| c | NP=2 (old t12 hint) | **NP=4 (new t12 hint)** | NP=8 |
|---|---|---|---|
| 1 | 1,435 (60 tok/s, 2.5 s) | 1,431 (60, 2.5 s) | 739 (31, 4.9 s) |
| 2 | 1,551 (65, 4.6 s) | 1,705 (71, 4.2 s) | 663 (29, 10.5 s) |
| 4 | 1,692 (71, 8.2 s) | **2,650 (110, 5.3 s)** | 971 (41, 14.1 s) |
| 6 | 1,701 (72, 12.0 s) | 2,689 (112, 7.8 s) | 868 (38, 24.2 s) |
| 8 | 1,719 (72, 15.2 s) | **2,841 (118, 9.6 s)** | 853 (37, 33.2 s) |
| VRAM used (nvidia-smi) | 10.6 / 12.0 GB | 11.3 / 12.0 GB | 11.7 / 12.0 GB |

Valid-schema rate was 1.0 and errors were 0 at every point.

Findings:
- **NP=4 is the best server setting for 12 GB.** It reaches about 2,650-2,840 passages/h, 1.65x the old NP=2 hint.
- **NP=8 is a trap on 12 GB.** It is 2-3x slower than NP=2 at every c, although Ollama reports the model 100% on
  GPU. With 11.7 GB of 12 GB in use, the Windows driver is evidently paging into shared system memory.
  ald must never set NP=8 on t12.
- With NP=4, c above 4 still helps a little (+7% at c=8) because Ollama's queue never runs dry between requests.
- **qwen3.5 stages (workcheck, alt_label, baseline_small) cannot run in parallel.** Ollama logs "model
  architecture does not currently support parallel requests" and loads them with `-np 1`. Their throughput is
  flat in c: workcheck about 1,900-2,000 passages/h, alt_label about 1,250-1,300/h on the 3060. This holds for
  every machine and tier.

Auto-tuner convergence, from c=1:

| server | trajectory (one digit per completed passage) | settled at | measured best |
|---|---|---|---|
| NP=2 | `1111111` then `2` x 93 | c=2 | c=2-8 within 10% (1,550-1,720/h) |
| NP=4 (tuner before the fix) | `1111111 22222222 33333333 44444444` then `3` x 69 | c=3 (~1,990/h) | c=4-8 (2,650-2,840/h) |

With NP=4 the tuner stopped one step short. Its first 8-completion window at c=4 still contained requests started
at c=3, so c=4 looked slower than c=3 (72.5 vs 75.6 tok/s), and the plateau rule reverted.

Two fixes, released in ald 0.1.5:
1. `ConcurrencyTuner` discards the first window after every change (`settle_windows=1`). There is a test that
   replays this 3060 case.
2. The VRAM fit model counts only Ollama's NP slots, not every in-flight request. Requests beyond NP queue in the
   server and cost no VRAM. Before this, the t12 cap was c=3, so c=4-8 was unreachable.

With both fixes the worker can reach c=4..8, where the plateau is flat; it starts from the benchmark's best level.

## Linux: RTX 4070 Ti SUPER 16 GB, tier t16

See the Linux section below. This machine shares its GPU with another study, so every run here waits on
`flock /tmp/aacv_gpu.lock`.

## Settings applied by the installer and `ald setup`

| setting | value | where |
|---|---|---|
| `OLLAMA_NUM_PARALLEL` | registry `tiers.<tier>.num_parallel_hint`: cpu 2, t6 2, t8 4, **t12 4** (was 2), t16 6, t24 8 | see below |
| `OLLAMA_FLASH_ATTENTION` | `1` on CUDA / Metal / ROCm | see below |
| `OLLAMA_KEEP_ALIVE` | `30m`; the client also sends `keep_alive: "30m"` on every request | see below |

Where each OS gets them:
- Windows: user environment variables (`setx`). Ollama is restarted with them: the tray app in a desktop session,
  `ollama.exe serve` in session 0.
- macOS: `launchctl setenv`. It is re-applied at every `ald work` start, because it does not survive a reboot.
  Ollama is restarted with `brew services restart`, or by quitting and reopening the app.
- Linux: `~/.config/ald/ollama.env`, used when ald starts its own `ollama serve`. A system `ollama.service`
  instead gets the drop-in `/etc/systemd/system/ollama.service.d/ald.conf`. That needs `sudo -n`; without it,
  ald prints the exact command.

Ollama is restarted only when its settings differ:
- Linux reads the running server's environment from `/proc`.
- On the other OSes a marker file records what was applied.

`ald work` re-checks the settings at every start.
