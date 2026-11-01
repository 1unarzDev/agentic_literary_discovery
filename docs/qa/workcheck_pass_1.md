# Workcheck QA pass 1 (2026-10-31)

**Scope.** All 200 synced workcheck results: pin `dddc85a5c85b…`, job `w00_workcheck_disc_00028`, split = discovery, qwen3.5:4b, codebook v0.5. The review used the opening text the worker saw (from the discovery shard) plus the catalog Title, Subjects, LoCC and Bookshelves.

**What was reviewed.**
- **85 works were read closely.** These are the first 35 works and every work where the catalog and the model disagreed on form, translation or juvenile status.
- **The other 115 were not read closely.** They have unambiguous LCSH "… -- Fiction" headings, and I spot-checked about 10 of them. Their reference label is "novel per catalog".

Reference labels are in `docs/qa/workcheck_pass_1_ref.csv` (work_id and labels only, no text). The packet is `data/work/qa/workcheck_20261031T232420.md`, made with `analysis/qa_sample.py --stage workcheck --n 60 --seed 1`.

## Headline
The 4B workcheck model has effectively collapsed to a constant answer: **novel, not translated, contemporary, confidence 0.95**.
- 198 of 200 works are labelled `novel_or_novella`.
- `confidence` is 0.95 for 198 works and 0.99 for 2. **It carries no information, so no confidence threshold is possible.**

The catalog alone separates fiction from non-fiction better than the model does.

## Error estimates (n = 200; 95% Wilson CIs)

| Field / error | Count | Rate (CI) | Consequence |
|---|---|---|---|
| **False "novel" on non-fiction or verse** | 10/12 | 0.83 (0.55–0.95) | Non-fiction leaks into labelling. Leaked works are ~5% of all works. |
| **False non-fiction on real fiction** (would wrongly exclude a work) | 0/185 | 0.00 (0–0.020) | None seen. The model is conservative because it almost never says non-fiction. |
| `story_collection` recall | 0/20 | 0.00 (0–0.16) | Every collection is called a novel. Harmless for keep/drop, but useless as a covariate. |
| `is_translation` = true | 5/200, all false positives | precision 0/5; FP rate 0.025 (0.011–0.057) | Excluding on this flag would wrongly drop 2.5% of works. The discovery catalog has 0 translator credits. |
| `is_juvenile` disagreements with reference | 9/200 | 0.045 (0.024–0.083) | Usable, but no better than the catalog (PZ class or "Juvenile fiction"). |
| `setting_period` = historical_past, for works with "History -- … -- Fiction" subjects | 2/34 | recall 0.06 (0.02–0.19) | Unusable. *Boscobel* (1651), *Tara* (17th c.), *Sir Quixote* (1680s) and *Red Caps and Lilies* (1792) are all called "contemporary". |
| `setting_place` vs geographic LCSH, where unambiguous | agrees on 13/87 | 0.15 | Noise. 101/200 are labelled `continental_europe`, including *Stover at Yale*, *The Intrusions of Peggy* and *The Ladies Lindores*. |
| `form` exact match | 165/200 | 0.83 | This equals the novel base rate. |

### Typical failures
- **Non-fiction called "novel":**
  - w45523 / w45610, Harkins's author biographies;
  - w46426, *Ruskin Relics*;
  - w47420, *Unaddressed Letters* (essays);
  - w47424, *The Shakespearean Myth*;
  - w46497 / w46636, Jessie Weston's Arthurian scholarship;
  - w46801, *The Hardy Country* (travel);
  - w47150, *A Book of Burlesque* (criticism);
  - w45241, *Popular British Ballads* (verse).
- **Non-fiction the model did catch** (2 of 12): w45328 (travel) and w45353 (literary history).
- **Translation false positives:**
  - w45927, *Seets i' Paris*: Yorkshire dialect was read as a translation;
  - w45556, *Pappina*;
  - w46152, *The Last Ditch*;
  - w46841, *Rejected of Men*;
  - w45907, the Dulac picture-book.
  - Foreign settings or subject matter seem to trigger the flag.

### Root causes
1. **The prompt defines nothing.**
   - Only `novel_or_novella` gets a definition.
   - TITLE and BOOKSHELVES are not passed. The title alone ("…and Other Stories", "Famous Authors", "Ballads") would have fixed most of the errors.
2. **The input text is mostly front matter.** 88% of openings begin with a table of contents, title page or ads. The reason is in `make_jobs.workcheck_items`: its regex anchors on the first "CHAPTER" in the first 40k characters, and that is usually the TOC entry.
3. **A 4B model without thinking can't calibrate.** `confidence` is a constant.

### Data issue found
w45523 (*Famous Authors (Men)*) and w45610 (*Little Pilgrimages Among the Men Who Have Written Famous Books*) are the same book under two PG titles. The openings are identical and the word counts are 44,206 vs 44,337. **This is a dedup miss in the work_root step.** It doesn't matter here, because both are non-fiction and excluded, but the same kind of retitled duplicate may exist among the novels.

## Exclusion rule (implemented: `analysis/workcheck_rule.py`)
This writes `data/work/workcheck_keep.parquet` (work_id, keep, reason, form_model, catalog_signal, model_translation). `keep` is a nullable bool:
- `None` means there is no workcheck result yet;
- `make_jobs.py --exclude-from-workcheck` drops only rows where keep is False.

I made `make_jobs.py` NA-safe for this: `wc.keep.astype("boolean").eq(False)`. Before that, `~wc.keep` raised an error on a None.

**The catalog signal** comes from the LCSH headings (split on ";"), checked heading by heading, with PG Bookshelves as a weaker fallback. It takes one of these values: fiction | collection | mixed | fiction_shelf | unclear | nonfiction_shelf | nonfiction | verse.

Decision order:
1. No result, or a schema failure → `keep=None`.
2. The catalog credits a translator, or has a "Translat…" subject → **drop**. The model's `is_translation` is ignored and recorded only in `reason`.
3. The catalog says `nonfiction`, `verse` or `nonfiction_shelf` → **drop**, whatever the model says.
4. The model says a non-fiction form:
   - if the catalog says fiction, collection or fiction_shelf → **keep** (override, to protect real novels);
   - otherwise → **drop**.
5. The model says novel_or_novella, story_collection or single_short_story → **keep**.
6. The model says `other` → keep only if the catalog is fiction-like.

**Confidence is not used** (see above).

On the 197 non-borderline works in pass 1:
- **0/185 real fiction wrongly excluded;**
- **0/12 non-fiction wrongly kept.**
- This is an in-sample check. The regexes were tuned on this sample plus 25 random works from each catalog class across all discovery works, so expect a few percent error out of sample.
- Two borderline types were left out of the scoring and are kept by the rule: the "Our Little … Cousin" informational juveniles (w45750, w45995) and *Stories from Wagner* (w47139, opera synopses, which the rule drops).

**Effect on all 8,038 in-range discovery works (`--catalog-fallback`):**
- 406 works (5.1%) are dropped on catalog evidence alone.
- In 25-work random draws, the dropped works are biographies, criticism, letters, travel, ballads and juvenile non-fiction. **None was a novel.**
- **Recommendation:** run `workcheck_rule.py --catalog-fallback` now, before pushing more label waves, rather than waiting for workcheck to finish on every work. The model adds nothing to the keep/drop decision today.

Known soft spots (reason strings make them easy to audit):
- `mixed` (28 works) is kept. It includes *The Celtic Twilight*, grail scholarship, and a *Henry Esmond* + essays compilation.
- Folk-tale and legend collections are kept as `collection`. For a sensitivity analysis, drop `catalog_signal == "collection"` together with the LCSH heading "Folklore".

## Proposed changes (batch for v0.9; workcheck only, so relabelling is cheap at about 8k items on the 8 GB tier)
These are low priority, because the catalog rule already handles keep/drop. Re-run workcheck only if we want `juvenile` and `setting_period` as covariates. A catalog proxy for period exists: the "History -- … -- Fiction" heading or the "Historical Novels" shelf.

1. **Item builder** (`make_jobs.workcheck_items`): skip the TOC. Start at the *last* line-initial `CHAPTER I`/`Chapter 1`/`I.` heading in the first 40k characters that is followed by at least 50 words of prose. Then take 1,200 words. Prepend the first 150 words of the file (title page) separately, labelled `TITLE PAGE:`.
2. **User template.** Change it to:
   ```diff
   -CATALOG SUBJECTS: {subjects}\n\nOPENING TEXT:\n{text}
   +TITLE: {title}\nCATALOG SUBJECTS: {subjects}\nCATALOG SHELVES: {bookshelves}\n\nOPENING TEXT:\n{text}
   ```
3. **System template.** Add these definitions after the existing first sentence:
   ```diff
   +Forms: novel_or_novella = one continuous story with recurring characters; story_collection = separate stories
   +(a CONTENTS list of unrelated titles, or a title with "and Other Stories", "Tales", "Sketches");
   +essay_or_nonfiction / history_or_biography / travel = factual prose about real people, places or literature,
   +even if it retells plots. Catalog headings ending "-- Fiction" or "Juvenile fiction" indicate fiction;
   +"Biography", "History and criticism", "Description and travel", "Texts" indicate non-fiction.
   +is_translation: true ONLY if the text or title says "translated" / "from the French" etc. Dialect is not translation.
   +setting_period: historical_past if the story is set more than ~30 years before publication (dates, historical
   +persons, "in the year 1651"). setting_place: use catalog place headings; else unknown.
   +confidence: below 0.6 when the opening is only front matter.
   ```
4. Either drop `setting_place` from the schema or ignore it in the analysis. Use catalog geography instead.

**Before adopting:** run the A/B on the same 200 works (see `docs/qa_protocol.md`). Adopt only if false non-fiction on real fiction stays at 0/185, and non-fiction recall reaches at least 8/12 or translation false positives fall to 1 or fewer.
