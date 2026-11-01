# Data quality and coverage protocol (v1, 2026-10-31)

Goal: every trend we report reflects a change *in the fiction*, not in what the archive happened to keep. Each item below is a pipeline stage or a gate, and each one is logged in `data/manifests/quality_report.md`.

## A. Work-level filtering (one pass per work, done before any passage labeling)
1. **Fiction and originality check** (new stage `workcheck`, on the screen-tier model, about 15k calls). The model reads the first ~1,500 words after the front matter and the work's catalog subjects, then answers:
   - `is_narrative_fiction` (novel / novella / story collection / not fiction: essay, history, sermon, travel, drama, verse);
   - `is_translation`;
   - `is_juvenile`;
   - `is_abridged_or_excerpt`;
   - `setting_period` (contemporary / historical / future / unknown).

   We drop non-fiction and translations. Juvenile works are kept, flagged, and analyzed as their own genre stratum. Validation: hand-check 60 works (G0).
2. **Text quality.** Measure:
   - non-ASCII rate;
   - the share of very short lines (verse or tables);
   - the share of all-caps lines (indexes or ads);
   - repeated-line rate (running headers);
   - boilerplate residue.

   Works above the thresholds are excluded. PG texts are proofread, so we expect less than 2% of works to fail.
3. **Length.** A work needs at least 15k words. Story collections are kept as works with a `collection` flag.
4. **Dedup** (done). MinHash plus author/title keys collapse editions, abridgements and multi-volume splits into a single `work_id`. The canonical edition is chosen by best date confidence, then longest text. Multi-volume works (e.g., "Vol. 1 of 3") are merged by title key.

## B. Dates (the most important variable)
- pg-dates gives an LLM-estimated year. We keep `date_confidence`:
  - **high**: the year appears in the first/last pages and Open Library agrees within 5 years;
  - **medium**: only one of those holds;
  - **low**: neither holds;
  - **conflict**: the year is impossible given the author's lifespan, so the work is dropped.
- **The primary analysis uses high + medium.** Low-confidence works enter only as a sensitivity check (battery item 4).
- Hand-check 60 works stratified by decade, against title pages or Wikidata P577. The pass bar is ≥ 85% within ±5 years.
- **Reprint guard:** the publication year must be ≤ author's death + 10. Posthumous first editions need a recorded date source.
- **Setting vs publication:** `setting_period` keeps historical novels (e.g., Scott, Thackeray's *Esmond*) out of the contemporary-trend estimate. They are analyzed separately.

## C. Coverage and composition (how we improve on prior studies)
Prior large-scale studies usually plot raw rates over an archive whose composition shifts across decades. We add five things:
1. **Author caps.** At most **5 works per author per decade** in the primary analysis, chosen at random with a fixed seed. One prolific author (e.g., a dime-novel writer or Mrs. Oliphant) can't then drive a decade. Uncapped results run as a sensitivity check.
2. **Composition decomposition.** Each decade-to-decade change in an obstacle share is split into a **within-genre (and within-origin) change** and a **composition shift**, meaning the change in the genre mix itself (shift-share / Oaxaca-style). We headline the within-genre component. For example, "more telegram plots" that come only from a rise in detective fiction would show up as composition, not as change.
3. **Fixed-composition reweighting.** Trends are also shown post-stratified to a constant genre × origin mix (the pooled 1840–1900 mix), next to the raw trend.
4. **Design weights.** Passages are drawn at random within each work (24 per work), with enrichment strata recorded at known inclusion probabilities. Prevalence estimates are then unbiased for each work, and work-level weights mean long novels don't dominate.
5. **Denominators everywhere.** Every figure shows the number of works and the number of authors for each decade.

## D. Coverage gaps (stated honestly, with mitigation)
- **PG is thin before 1830** (about 60–130 works per decade). Gate G0 requires at least 60 works and 30 authors per decade in each split half. Otherwise the confirmatory window starts in 1830, and 1800–1829 is reported descriptively, with ELTeC and any additions.
- **Canonical bias.** PG over-represents canonical and popular works. Per-work memorization (name-cloze) scores measure canonicity directly. We report "canon vs. long tail" contrasts and the drop-top-memorized battery item.
- **UK vs US** origin comes from LoCC plus Wikidata. `unknown` origin is kept in pooled models and excluded from origin contrasts.
- **Phase 2 (after Nov 20).** Request HathiTrust/HTRC access to public-domain full text for 1800–1830 to fill the early gap. Use HTRC Extracted Features 2.0 (17M volumes) to compare lexical trends for H3.

## E. Efficiency passes
- Text is cleaned once and segmentation is cached. Passages are stored with offsets and sha256, so they are never recomputed.
- The work-level checks above run *before* passage sharding, so no passage from an excluded work is sent to the GPUs. Expected saving: 10–20% of compute.
- The screen stage filters passages without obstacles before the expensive label stage.
- Adaptive stopping closes a decade × stratum cell once the precision target is reached.
