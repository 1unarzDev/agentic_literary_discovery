# Feasibility and submission-strategy review (2026-11-01, 22:00 CST)

**Reviewer stance.** I review as a skeptical programme-committee member and project manager. The question is not
"is the science good?" (see `docs/review/literary_review.md` for that) but "what can this team *honestly finish and
claim* by Nov 19–20, and what must be cut to get there?"

**Read.** Plan v2 (§4.8, §8–9), `docs/prereg.md` v0.4, `research/venues/fit_report.md` and `checklists.md`,
`docs/gates.md`, `docs/perf_report.md`, `docs/perf_label_ab.md`, `docs/pilot_analysis_1.md`,
`data/work/monitor_latest.md`, `docs/install_maturity.md`, `bench/`, `pipeline/make_jobs.py`, `data/work/jobs_plan.json`
and the synced result batches.

**Ran.**
- `uv run --with pandas,numpy,pyarrow,pytest pytest bench -q`: **10 passed** (5–6 s).
- A smoke run of the benchmark on **real** labels: the 8,706 synced v0.9 Discovery passages (5,302 works), with a
  placeholder memorization score of 0, then `bench.generate`, `bench.run_agents` with the dummy agent, and `bench.score`.
  The adapter is a throwaway in `/tmp/bench_smoke/` and is not committed. Findings are in §2.

## 0. Bottom line

1. **The full queue cannot finish, and most of it is not needed before Nov 20.** About 588k label passages are
   queued. COLLIN alone delivers about 384k by Nov 17 even if nothing breaks. The Nov 20 papers need **one wave,
   w02 (Confirmation random, 12 per work)**, plus about 2.5k early-era passages and a *subset* of Discovery. Freeze
   everything else.
2. **Fix the queue order tonight.** w01 and w02 both sit at priority 20, and the coordinator picks randomly among
   equal priorities (`ORDER BY priority, random()`). As things stand, *neither* wave will be complete on Nov 5.
   Move w02 to priority 10.
3. **Do not relabel under v1.0 before Nov 20.** Register the v0.9 labels as the DSL predictor. DSL is valid for any
   predictor (prereg §5.1), so a relabel buys efficiency, not validity. On COLLIN a w02 relabel costs about 52 window
   hours, or 3–4 calendar days.
4. **The teacher's 15 minutes cannot carry what the prereg asks of the expert**: 30 expert items, an exclusion rule
   that needs ≥ 20 expert items per annotator, and the expert-nested sensitivity. Amend the prereg before
   registration (§4).
5. **AAAI: the benchmark runs, but as built it leaks the answer key.** In every confounded null, each work appears
   at both 1840 and 1900, so a null is identifiable from its structure alone. Every synthetic corpus has exactly two
   distinct years, and real author keys sit beside reassigned dates. This takes about a day to fix. It is
   compute-free. Make it a **conditional go**, gated on Nov 9 and on a confirmed in-person presenter.
6. **DH is the priority paper.** A confirmatory H1 result by Nov 20 is achievable *only* if w02 is done by Thursday,
   the annotators deliver about 1,000+ labels by Nov 8, nothing is relabelled, and the OSF registration lands
   Nov 9. Otherwise submit the honest fallback: measurement + human validation + an exploratory Discovery pattern,
   with the confirmatory test labelled as pending. DH explicitly allows anticipated outcomes.

---

## 1. Compute feasibility

### 1.1 Demand: what is in the queue and what is actually needed

| Item | Passages | Needed for | Verdict |
|---|---|---|---|
| **w02 conf_rand_a** (k < 12) | 86,316, none synced yet | **Audit draw (Nov 5)** and every confirmatory estimate | **P0. Priority 10, tonight** |
| Confirmation early-era rand_b (year < 1850, k ≥ 12; 212 works) | ~2,500 | Prereg §3.3: "every early work is labelled in full". E is H1's binding era | **P0. Add to w02 before the draw**; afterwards it can never enter the audit frame |
| **w01 disc_rand_a** | 95,948, of which 8.7k synced (the coordinator counts 38 label jobs done, ≤ 15k) | Benchmark input, DH exploratory figure, exemplars, power check | **P1, cut to about half the shards** (≈ 6 passages/work, ~48k in total, so ~35–40k remaining) |
| alt_label on the ~1,800 audit items | ~1.8k | Battery check 6 "+ every audit item" | P1 after the draw. qwen runs at `-np 1`, ~1,250/h, so about 1.5 h |
| cloze, Discovery works only | ~23k (half of w07) | Benchmark memorization confound; battery check 5 | **P2, only if AAAI is a go**. Otherwise defer |
| cloze, Confirmation half | ~23k | Battery check 5 | Defer past Nov 20 |
| baseline_small | 10,036 | SRW baselines (Jan) | Defer |
| **w03 / w04 enrichment** | 125,149 + 113,379 | Exemplars and descriptive deep dives only. **Not in the audit frame** (prereg §3.1 v0.3) | **Cut before Nov 20.** Mine passage cards from the random backbone |
| w05 disc_rand_b | 95,148 | Nothing before Nov 20 | Defer |
| **w06 conf_rand_b** | 87,516 | **Nothing confirmatory, ever, under the registered design.** Passages labelled after the Nov 5 draw have π = 0 and cannot enter the DSL estimand | Cut. Amend prereg §3.1 from "24 per work" to "12 per work (rand_a) + all early-era passages" |
| v1.0 relabel of w02 (+ Discovery) | 88k–135k | Efficiency only (DSL is valid for any g) | **Cut** unless G2 fails catastrophically (§5) |

**The minimum before Nov 20 is ~89k (P0), plus ~40k (P1), plus ≤ 25k (P2, conditional): about 130–155k passages.**
That is a quarter of the queue.

### 1.2 Supply: realistic throughput

Assumptions. Every number here is labelled as an assumption or as measured.
- **COLLIN**: 1,700/h is the planning rate in `perf_label_ab.md` §6. It is v0.9 measured at 1,800–2,000/h less ~10%
  ald overhead. 2,200/h is your figure and serves as the optimistic case. The "degraded" case applies 75%
  availability, because **COLLIN is silent right now inside its own Sunday 21:00–05:00 window** (last seen 20:39 CST,
  86 min of silence at 22:06). A worker that is merely idle still heartbeats, so this looks like sleep, a crash or a
  reboot. v0.9 has **not yet been shown at 1,700/h in production** on COLLIN: its last 24 h total was 4,528, mostly
  spent paused for the A/B.
- **COLLIN window hours from now** (schedule `mon-fri 21:00-05:00,07:00-15:00; sat-sun 21:00-05:00`, local):
  55 h to Thu Nov 5 07:00; 63 h to Thu 15:00; 98 h to the end of Sun Nov 8; 226 h to the end of Tue Nov 17.
- **innovation, part-time**: assumed 8 h/night from Tue Nov 3 at 3,400–4,000/h (bench 4,547–4,738 at c = 4–8; t16
  estimate 3,400–4,500).
- **Volunteers (2–4)**: assumed onboarded by Wed Nov 4. Only about half will have label-capable hardware: t6 cards
  cannot run label, and a 16 GB Mac manages ~200–350/h. So count 1–2 machines at 800–1,500/h for 10 h/day. Budget
  **zero** for Nov 5.

Cumulative label passages from Sun Nov 1, 22:00 CST:

| Scenario | by Thu Nov 5 07:00 | by Sun Nov 8 24:00 | by Tue Nov 17 24:00 |
|---|---|---|---|
| COLLIN only, degraded (1,700/h × 0.75) | ~70k | ~125k | ~288k |
| COLLIN only, realistic (1,700/h) | ~94k | ~167k | ~384k |
| COLLIN only, nominal (2,200/h) | ~121k | ~216k | ~497k |
| **+ innovation part-time** (add) | +54–64k | +150–176k | +400–470k |
| **+ 2–4 volunteers** (add; high variance) | +0–30k (plan 0) | +36–135k | +108–405k |

What follows from this:
- **P0 (~89k) on COLLIN only** needs about 52 window hours at 1,700/h (40 h at 2,200/h). That is done by ~Thu 02:00
  (Wed 06:00 at nominal), **provided w02 is moved ahead of w01 tonight**. In the degraded case it finishes Fri
  morning and **misses the Thursday draw**. Hence gate C1 (§5) and the fallback draw.
- **P0 + P1 (~130k)** on COLLIN only: Fri Nov 6 – Sat Nov 7. That is fine, because the benchmark and the DH figure
  need Discovery only from Nov 9.
- **The whole queue (~588k)** is out of reach by Nov 17 even with innovation part-time: about 384k + 400k only at the
  optimistic end, with no failures. It is also unnecessary. The monitor's 849 h ETA is the honest number for "label
  everything".
- **A v1.0 relabel** (~89k for w02 alone) after the Nov 8 freeze takes COLLIN until ~Nov 12–13. That collides with the
  unseal, the analysis and the writing. With innovation for two nights it is ~1.5 days. It is still not worth it
  (§1.3).
- Volunteers matter only after Nov 8. **Route them to non-confirmatory work** (the w01 subset, cloze, baseline_small)
  so that the confirmatory predictor for w02 comes from 1–2 known GPUs and backends. DSL stays valid with mixed
  backends, but fewer OS/backend κ questions reach the paper.

### 1.3 Direct answers

- **Is Confirmation random at 12 per work (w02) enough?** **Yes, for everything confirmatory.** Prereg §7.1(a)
  puts the perfect-label MDE floor at 4.7–5.4 pp for 12 passages against 3.4–4.0 pp for 24 (ICC 0.05). The DSL design
  MDE, by contrast, is about **17 pp material / 10 pp internal** (§7.5), set by annotator noise and the audit size, not
  by passages per work. Halving the passages costs roughly 1–1.5 pp on a 17 pp MDE. The rand_b half (w06) is useless
  confirmatorily anyway once the audit is drawn. *Before registering*, re-run `power.py --final --v04` at m = 12; the
  grid already supports `passages_per_work = 12`. The one exception is the early era: label all ~24 passages of its
  212 works (P0 above).
- **Is a smaller Discovery sample enough?** **Yes.** Discovery feeds the benchmark (today's 8.7k passages already
  generate all 30 corpora), the DH exploratory figure, exemplars and the power check. Labelling half of the w01
  shards gives a random ~6 passages per work over the whole half, which is ~25× the pilot's 1,361 passages. **Drop
  open discovery (§4.6) before Nov 20.** Promoting a candidate requires prereg text before registration on Nov 9,
  that is, clusters, an ideator/critic round and a written test within three days of annotation. It is the most
  cuttable item in the plan.
- **Is the enrichment wave necessary before Nov 20?** **No.** It is excluded from the audit frame by design. The
  random backbone (~89k Confirmation + ~48k Discovery passages) contains thousands of communication, travel and
  darkness obstacles for passage cards. If a specific card needs a period term, label a targeted ≤ 2k Discovery-only
  enrichment slice after Nov 9.
- **Is cloze needed now?** **No.** Memorization is a battery variable (check 5), not a registered model covariate
  (prereg §4). It is needed before Nov 20 only for the benchmark's `memorized_canon_oversampling` null, and
  `bench.generate` *requires* a finite `memorization_score`. Either run cloze on Discovery works after P1 (if AAAI
  is a go), or replace that confound with **prolific-author amplification**. The pilot found that 555 of 993 late
  obstacles come from authors with ≥ 10 PG works, so it is literary-historically real and needs no inference.

---

## 2. The AAAI benchmark paper

### 2.1 Does it exist and work?

**It exists, and it runs end to end.** Its pieces are `bench/generate.py` (215 lines), `run_agents.py` (Claude,
Codex and custom-command presets; per-corpus temp staging; timeouts), `score.py` (detection, false claims, confound
identification, Brier, evidence, CI coverage, gate) and 10 tests on synthetic fixtures (all pass). On real v0.9
Discovery labels I got:
- 30 corpora generated at δ = 0.2, 0.1 and 0.05 with no failures (38 MB);
- the dummy run plus scoring completed (26 eligible, 4 unsupported, gate correctly failed for an always-abstainer).

**But a reviewer, or a capable agent, will break it.** Found on the real-data suite:

| Problem | Evidence (smoke suite, δ = 0.05) | Fix |
|---|---|---|
| **Nulls are identifiable from structure.** "Identical copies to each era" means 100% of work_ids appear at two dates in the genre-drift and duplicate nulls (88% in reprint). In injected shifts it is 10%, in positives 0% | `corpus_21`: 722 works, 2,200 rows, share of work_ids at > 1 year = 1.00 | Draw **disjoint** genre-matched work sets per era (a within-genre permutation of real works' dates) instead of copies |
| **Synthetic corpora have exactly 2 distinct years** (1840, 1900); positives have 121 | `corpus_11`, `corpus_21`: `year ∈ {1840, 1900}` | Draw years from the real era-year distribution |
| **Real identities leak dates.** Real `author_key` (e.g. `ingrahamprentiss`, a dime novelist of the 1880s–1900s, placed at 1840) and `pg…` passage IDs, together with evidence quotes | `corpus_21/works.parquet`, `passages.parquet` | Re-key work, author and passage IDs per corpus. Keep quotes only if the paper wants text-reading agents, and then accept and discuss the leak |
| **Corpus size reveals kind** (positives 5,302 works; others 700–1,300) | manifest | Equalize sizes |
| **The positive controls are near-zero effects.** Telephone and night passage rates differ by 0.2–0.7 pp. Epistolary is a stub. One control is wrong-signed, so 4 of 10 are unsupported | keys `corpus_01`–`10` | Either drop the positives from the headline (use injected shifts as the sensitivity arm) or redefine them as rates conditional on obstacles. Do not call 0.4 pp a "known positive" |
| **The prompt names all five confounds.** It tests whether agents follow a checklist | `agent_task.md` | Add a **no-checklist ablation** arm. It is the most informative contrast |
| Memorization confound vacuous without cloze | placeholder gave effect 0 | Cloze on Discovery, or swap in prolific-author amplification (§1.3) |
| **The plan's gate is never run on "our pipeline".** The plan (§4.8) says the pipeline must pass ≥ 8/10 injected and ≤ 1/10 nulls *before H1–H3 are trusted*, but bench only evaluates agents | — | Add a deterministic baseline: the registered estimator (genre-standardized, author-clustered, dedup + date-confidence filter) on the 20 controlled corpora. This also answers the "matched non-agentic baseline" reviewer objection |
| **Licence**: positives retain pg-dates years (CC BY-NC, not redistributed per plan §4.1) | — | Release the generator + IDs; users fetch the dates themselves. Or use our own date-gold years |

One encouraging fact for the paper: in the reprint and duplicate nulls, the standardized *observed* effect is
**+15 to +17 pp** against injected shifts of ±5 pp. The traps are three times larger than the true signals, which is
exactly the regime where "plausible stories" should appear.

### 2.2 Minimum to run agents on 30 corpora by ~Nov 17

1. **Leak fixes + ID re-keying + year resampling + size equalization**: ~1 day of Codex work plus review, Nov 2–4.
   No GPU.
2. **Input adapter** from synced labels to the bench schema. My throwaway took 15 minutes; commit a real one.
   Regenerate on w01 once ≥ ~25k Discovery passages are in (Nov 6–7). Today's 8.7k already suffice for a pilot.
3. **Pilot**: 3 corpora × 2 backends × 1 seed (Nov 5–6) to confirm valid JSON, timeouts and token logging.
4. **Full run**: 26 eligible corpora × 2 backends (Claude, Codex) × 3 seeds, plus a no-checklist ablation on the 20
   controlled corpora × 1 backend × 3 seeds, plus the deterministic baseline. That is ~220 agent runs at 5–10 min
   each, so ~20–35 h serial, or ~1 day at 4 in parallel (Nov 10–12). Log tokens and cost per run. The runner does not
   enforce budgets (README), so use backend-native caps and report actual usage.
5. **Human check**: the student reads 30 rationales blind and marks confound identified yes/no, against the
   string-match scorer (~1 h, Nov 13).
6. **Anonymous artifact** with a README, key-free replay of saved outputs and no private keys (Nov 14–15).

**Realistic?** Yes, *if* Claude/Codex do steps 1–4 and 6 and the student does only step 5 and the writing. The
compute is not the constraint: the benchmark costs no inference beyond the w01 subset and the optional cloze. Student
attention and the presenter requirement are.

### 2.3 What would make it compelling

- A **false-claim rate on confounded nulls well above the ≤ 1/10 bar** for frontier agents, with seed-level
  uncertainty, *while* they detect ≥ 8/10 injected 5 pp shifts. Sensitivity and false claims must be reported
  together: abstaining always is not a win.
- **The no-checklist ablation**: how much of the agents' caution comes from the prompt's confound list.
- **A simple deterministic estimator beating the agents** at a matched budget.
- **Calibration** (Brier) and **confound naming** checked against human reading of the rationales.
- An honest negative is publishable too: "agents do not overclaim once confounds are named, but do without the
  list".

### 2.4 Is it worth doing?

**Conditional go.** For it: it is non-archival, compute-free, scored mechanically and owned by agents rather than the
student, and it is the only November deliverable whose results do not depend on the annotation and unseal chain.
Against it: the **in-person presentation (Feb 22) is mandatory**, and that means travel and registration for a minor;
it competes with DH for the student's last three days; and the current version would draw the reviewer objections
§2.1 lists. **Go only if** (a) a named in-person presenter and budget are confirmed by Nov 9, and (b) gate B1 passes
(§5). Otherwise **skip it**. Do not submit a results-free position paper as a consolation prize: it costs writing
time and earns little. DH comes first whenever the two collide.

---

## 3. DH2027 short paper

### 3.1 What can honestly be claimed by Nov 20

The critical path is: w02 complete (~Thu Nov 5) → audit draw → annotation (Nov 5–8) → G2 → OSF registration (Nov 9)
→ unseal → H1 (Nov 10–11). There is **no slack for a relabel, a late draw or slow annotators**. Given that:

- **Claim A, confirmatory (if every gate in §5 passes):** the *registered primary test* (H1, two-sided 2-df Wald) on
  the held-out Confirmation authors. Report its class (inward / outward / mixed / not detected) with both component
  CIs and the registered MDE. Constraints:
  - It is the **human-label construct of four student annotators**, not expert readers. The teacher validates
    nothing at scale and must not be described as having done so.
  - The plan's own definition of "supported" (Holm significance + ≥ 7/9 battery checks + replication, §4.7) **cannot
    be met by Nov 20.** Checks 5 (memorization), 6 (alternate family, beyond the audit items), 7 (segmentation) and 9
    (ELTeC/Chicago) need inference or data not scheduled. Say "the registered primary test rejects / does not
    reject", and list the robustness checks as pending. Do not say "supported".
  - H2a–c and H3 have MDEs of 35 / 5 / 5 pp against plausible effects of 1–2 pp (prereg §7.4), so they are expected
    nulls. Put them in an appendix table with their MDEs, not in the abstract.
- **Claim B, fallback (any gate fails):** the measurement design, the human validation (overlap κ, n), and an
  **exploratory, uncorrected** Discovery pattern: the M → L rise in the material share of obstacles, concentrated
  in an 1880s step, with no inward turn. The pilot's numbers are raw v0.5 labels and must be recomputed on v0.9 w01
  before quoting any figure. The confirmatory test is described as pre-registered and pending. DH's CFP allows
  anticipated outcomes if labelled as such.

**Pick A or B at gate G3 (Wed Nov 11, 20:00).** Draft B first, from Nov 9. It is the paper you will have regardless,
and A only changes one paragraph and the figure.

### 3.2 Draft claims (3–4 sentences; brackets are filled from the registered output only)

**A (confirmatory):**
> Literary historians have long argued that the novel turned inward, moving the obstacles to characters' desires from
> the material world into the mind (Kahler). We test this on held-out authors: ~7,400 English-language novels
> (1800–1929) in Project Gutenberg. An open-weight language model reads 12 random passages per novel for the obstacle
> that blocks a character's goal, and a probability sample of ~[N] passages read blind by four student annotators
> corrects the model's errors, so the estimates and confidence intervals refer to human readings, not machine labels.
> In a pre-registered test, the share of obstacles located in the material world [rose / fell / did not detectably
> change] between 1800–1849 and 1885–1929 ([Δ] pp, 95% CI [..]; detectable effect ≈ 17 pp), while internal,
> psychological obstacles [..], a pattern we classify as [inward / outward / mixed / not detected]. Paired passages
> from the 1820s and 1900s show what the measure counts, and why counting technology words is not the same as
> reading for plot function.

**B (fallback):**
> Literary historians have long argued that the novel turned inward, moving the obstacles to characters' desires from
> the material world into the mind (Kahler). We operationalize "plot obstacle" for corpus-scale reading of
> ~15,000 English-language novels (1800–1929) and validate an open-weight model's readings against [N] passages read
> blind by four student annotators (κ = [..]). In an exploratory half of the corpus, the uncorrected model labels show
> no inward turn: the share of material obstacles (nature, travel, darkness) rises by about [x] pp after 1880, in a
> single step rather than a trend. A pre-registered test on held-out authors, corrected toward the human readings,
> will be reported at the conference.

Both fit the checklist's ~280-word findings budget. Neither names railways or telegraphs as causes.

### 3.3 Policy actions this week (not optional)

- **Email the DH and SRW chairs by Tue Nov 3** about overlap between the DH abstract and the SRW paper. The fit report
  says the three-venue plan is "not yet policy-cleared". Their answers decide what DH may contain.
- **Send the SRW mentorship request on Mon Nov 9 or Tue Nov 10**, not on Nov 16. It needs no paper and takes about an
  hour, and the AoE deadline is Nov 17, 05:59 CST.

---

## 4. Risks and single points of failure

| Risk | Status / likelihood | Impact | Mitigation |
|---|---|---|---|
| **COLLIN down or asleep** | **Happening now**: silent 86 min inside its window. A reboot was never tested (install_maturity #11) | P0 misses Nov 5. COLLIN is the only label machine | Tonight: check over SSH (authorized), confirm the S4U task, `powercfg /requests`, Windows Update active hours. Ask the owner to **open the 05–07 and 15–21 gaps Nov 2–5** (+6 h/day, ~+35%). Alert on more than 20 min of silence |
| **innovation unavailable** | Paused indefinitely | No relabel insurance; Discovery slower | The plan assumes 0 h. Ask for **two fixed nights** (Nov 3–4, or Nov 9–10 as relabel insurance). Do not make any gate depend on it |
| **v0.9 slower in production than on the bench** | Not yet shown at 1,700/h | P0 slips a day | Gate C0 (Mon 07:00) on measured overnight throughput. ald §5 items 1, 2 and 4 (q8_0 KV, one num_ctx, tuner start) must be live on COLLIN |
| **Annotators flake** | High. 500 labels × ~1.5–2 min ≈ 12–17 h each over Thu–Sun, two of them school days | MDE grows ~1/√n: ~1,000 labels → ~12.5–16 pp (prereg R1) | Random balanced assignment makes early stopping valid (π recomputed per cell, §5.1.4). Set a **floor of 250 each** and a daily check. Recruit a **5th reserve** now. Each annotator's queue is a random sample of every cell, so *partial* queues still cover every cell |
| **Teacher: 15 minutes** | Certain | Prereg §3.4/§5.1 need 30 expert items, and the exclusion rule needs ≥ 20 per annotator. 15 min is ~6–8 passages | **Ask for 3 × 15 min** (Nov 6–9) to do the 30 items. If only 15 min: **amend the prereg before registration.** Exclusion becomes overlap-based (κ < 0.40 against the other annotators on ≥ 30 overlap items). Drop the expert-nested sensitivity (SE 17–30 pp, uninformative anyway). Spend the teacher's 15 min on the **DH draft and passage cards** (Nov 14) |
| **Student bandwidth** | High | Everything serializes through one person in a school week | The student does annotation (≤ 300), the rationale check, the voice and the final read. Claude/Codex do code, runs, figures and first drafts |
| **Draw needs Confirmation labels before registration** | By design | A seal question | The draw script reads only era and dgroup and emits IDs + π. Log it. Measure G2's LLM accuracy on Discovery teaching items before registration, and on the Confirmation audit only after the hash |
| **Overlap policy** (DH ↔ SRW) | Unresolved | A desk reject, or forced withdrawal later | Email the chairs (§3.3) |
| **AAAI presenter / travel** | Unconfirmed | Accepted but unpresentable | Confirm by Nov 9 or skip AAAI |
| **Benchmark leaks** | Confirmed (§2.1) | Reviewer rejection; agents game it | Fix before any agent run |
| **Date errors** | Ongoing (`docs/gates.md`, `research/date_audit/`) | E-era contrast attenuated (pilot §3 #4) | Freeze the date-gold rule *before* registration; high + medium only, as registered |
| **Coordinator** (D1 free-tier writes, Cron) | Low | Fleet stall | Per-shard index already in place; $5 plan if needed |

---

## 5. Revised schedule to Nov 20 (CST), with go/no-go gates

| When | Work | Gate |
|---|---|---|
| **Sun Nov 1, tonight** | **Re-prioritize**: w02 → 10; add Confirmation early-era rand_b (~2.5k) to it at 10; half of the w01 shards → 15, the rest → 60; w03–w06 → 90; cloze and baseline_small → 70. SSH into COLLIN and restore it | — |
| Mon Nov 2 | Prereg amendments drafted: 12 per work + early full; v0.9 = DSL predictor, no relabel; audit population = labelled w02 passages; teacher role and exclusion rule; battery checks by date; open discovery removed. Benchmark leak fixes (Codex). Volunteer onboarding onto non-confirmatory waves | **C0 (07:00):** COLLIN's overnight v0.9 rate ≥ 1,500/h? If < 1,200/h, plan the fallback draw now |
| Tue Nov 3 | Annotation UI dry run with peers (practice set). Chair emails. Bench adapter + 3-corpus pilot | — |
| **Wed Nov 4, 15:00** | — | **C1:** w02 ≥ 85% complete? **Yes** → full draw Thu 07:00. **No** → draw Thu 15:00 on the labelled subset. Shards are random passage subsets, so π stays known; register that population |
| Thu Nov 5 | Audit draw (seed 20261105); alt_label on the audit items; annotation starts in the evening; teacher session 1 | Draw script outputs only IDs + π |
| Fri Nov 6 – Sun Nov 8 | Annotation; teacher sessions 2–3; w01 subset finishes; cloze on Discovery if AAAI is still open; power re-run at m = 12 | **A1 (Sat 20:00):** ≥ 800 labels? **A2 (Sun 22:00):** ≥ 1,000 labels and each annotator ≥ 250? If not, extend annotation to Tue Nov 10, push the unseal, and DH → Claim B |
| **Mon Nov 9** | G2 (overlap κ ≥ 0.6 has_obstacle, ≥ 0.5 locus); codebook v1.0 := v0.9; **OSF registration**; SRW mentorship request; regenerate the bench on real Discovery | **G2** fails → merge categories per the prereg or DH → B. **B1 (AAAI):** leak fixes merged, suite regenerated, pilot runs valid, presenter confirmed? No → drop AAAI |
| Tue Nov 10 | Unseal; run the registered H1 (+ H2/H3, MDEs); deterministic battery checks 1–4 and 8. Bench full runs start | Unseal only with the OSF hash in `docs/prereg.md` |
| **Wed Nov 11, 20:00** | Statistician subagent audits the outputs | **G3:** H1 computed and audited → DH Claim A; otherwise Claim B |
| Thu Nov 12 – Sat Nov 14 | DH draft (B written from Nov 9; A paragraph swapped in); figure; passage cards from Discovery; bench scoring + human rationale check (Nov 13); **teacher reads the DH draft (Nov 14)** | — |
| Sun Nov 15 – Tue Nov 17 | AAAI 4-page draft + anonymized artifact (if B1 passed); DH revision; GenAI disclosures | **F1 (Tue 20:00):** figures and numbers frozen; every number traced to a registered run |
| Wed Nov 18 | Independent read of both drafts (claims vs runs, citations, word count) | — |
| **Thu Nov 19, 18:00** | **Submit AAAI** (the deadline is Fri Nov 20 00:00 CST = 06:00 UTC) | 6 h buffer |
| **Fri Nov 20, 18:00** | **Submit DH** (the deadline is Sat Nov 21 05:59 CST = Nov 20 AoE) | — |

### What is cut or deferred (summary)

- **Cut before Nov 20:** enrichment waves w03/w04; rand_b waves w05/w06, with w06 cut from confirmatory use
  permanently; the v1.0 relabel; open-discovery promotions; cloze on Confirmation; baseline_small; the ELTeC/Chicago
  replication; battery checks 5–7 and 9; the expert-nested sensitivity.
- **Reduced:** Discovery to ~half of w01; human annotation floors of 250 per annotator; the teacher to the DH draft
  plus (if granted) 30 expert items.
- **Conditional:** AAAI (gate B1 + presenter); cloze on Discovery (only for AAAI).
