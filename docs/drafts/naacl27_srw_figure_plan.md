# Figure plan: NAACL 2027 SRW long paper (draft v0.1, 2026-11-04)

One visual language for all figures: paper, ink and postal red (plan §6). Use the `dataviz` skill when building them.
Every trend figure shows **n works / n authors per bin** under the axis. Exploratory figures carry a corner tag:
"Discovery, raw model labels".

| # | Figure | Data source | Message (one sentence) | Status | Paper § |
|---|---|---|---|---|---|
| **1** | **The archive changes under you.** Canonical share of works by decade, Discovery and Confirmation as two lines, with works-per-decade bars beneath | `data/work/canon.parquet` + `works_v2.parquet` (metadata only; numbers in `docs/canon_measure.md` §2.5) | PG keeps the canon before 1850 and the mass market after 1885, so any aggregate trend mixes two populations. | Can build now (metadata only, seal-safe) | §3.4 |
| **2** | **Passage cards.** A 3 × 2 grid with one row per locus (material / social / internal) and columns canonical vs mass-market, each cell a verified evidence quote plus author, title and year. Example: *Middlemarch* "wild illusion … Mr. Casaubon" vs *Tom Swift* "caught in the coils" | v0.9 Discovery labels in `data/work/ald.duckdb` (`results`, quote_status exact/normalized only); candidates in handoff §5 and `docs/qa/exemplar_candidates.md` | The construct is readable: a reader can check every label against the text. | Can build now. Exclude *The Awakening* quote (its quote_status is `context`, not inside the passage) | §1, §6.2 |
| **3** | **Specification curve / multiverse.** Naive TF Δ_material and H1 Δ_material point estimates with CIs, one dot per specification (model × codebook × date source × genre standard × canon K × clustering), sorted, with an indicator matrix below; the DSL-corrected Confirmation estimate as a horizontal band | Discovery labels (Gemma `41ca3c7d`, Qwen `ca0c1188`, v0.5 `2c86999f`); Claude reference from `docs/claude_reference_analysis.md`; Confirmation band from `analysis/stats/out/confirmatory/` | How much the naive picture depends on the instrument, and where the human-corrected answer sits. | Discovery part can be built after `claude_reference_analysis.md` lands; band **after unseal** | §7.2 |
| **4** | **Registered result.** TF: canonical vs non-canonical standardized locus shares (three bars per group, or a ternary-style dot pair) with expert-anchored DSL CIs; H1 by era beside it, with the registered MDE drawn as a grey band | `analysis/stats/out/confirmatory/` (TF, H1, H1\|canon, H1\|non-canon) | The confirmatory answer, with its uncertainty and what the design could have detected. | **After unseal** | §6.1 |
| 5 (appendix) | **Power by lever.** TF MDE by expert-label budget and strata design (Table 1 as a dot plot) | `analysis/stats/out/power_final_extra.csv`, `levers.csv`; prereg §7.7 | Gold labels, not model accuracy, buy power under DSL. | Can build now | §5.3 |
| 6 (appendix) | **Throughput A/B.** Passages/h vs locus agreement for each prompt/server variant on the RTX 3060 | `docs/perf_label_ab.md` §2–3 | Context size and KV quantization roughly doubled throughput with no accuracy cost. | Can build now | §4.4 |
| 7 (appendix, optional) | **Agreement by era.** Model–expert and peer–expert κ (locus, has_obstacle) per era with CIs | Human audit labels (Nov 6–8) | Whether measurement quality is stable across the century, the key DSL-adjacent assumption for reading trends. | **After audit** | §4.5 |

## Tables (for reference)
- Table 1: power by lever (in text; prereg §7.7).
- Table 2: registered tests (after unseal).
- Table 3: exploratory canon × era locus shares (Discovery, raw).
- Table 4 (appendix): efficiency A/B.
- Table 5 (appendix): battery check results per test (after unseal).

## Budget
The main paper takes Figures 1–4 and Tables 1–3, about 1.6 pages. Figures 5–7 go in the appendix. If over length,
merge Figure 1 into a small inset of Figure 4.
