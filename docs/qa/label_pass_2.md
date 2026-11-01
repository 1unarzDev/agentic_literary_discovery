# Label QA pass 2: w01 discovery, pin `2c86999f` (2026-11-01)

**Sample.** I drew 90 items:

```
analysis/qa_sample.py --stage label --n 90 --seed 2
```

- **Population:** 1,361 rows (data/work/qa/label_20261101T012008.*).
- **By era:** 11 items from 1800–1849 (population ≈ 33), 23 from 1850–1884 (≈ 200), and 56 from 1885–1929 (≈ 1,128). The early era of w01 is thin.
- **Risk items:** 40/90 are oversampled risk items (bad quote, low confidence). All rates below marked "w" are **design-weighted** (N_h/n_h). The rest are raw counts in the sample.

**Reference.** I read every passage and its context as a reader of English literature, applying codebook v0.5. Per-item verdicts, reference domains and loci, and notes are in `docs/qa/label_pass_2_ref.csv`.

**Caveats.**
- These are one reviewer's judgments, not human gold. Expect ±5 points of reviewer noise on borderline "mild" cases.
- Per-era n is small, especially 1800–1849 with 10 fiction items. Treat era differences as hypotheses.

## 1. Headline numbers

| | 1800–1849 | 1850–1884 | 1885–1929 | All |
|---|---|---|---|---|
| Model `has_obstacle = yes` (population) | ≈ 0.85–0.88 | ≈ 0.85–0.88 | ≈ 0.85–0.88 | 0.876 (1192/1361) |
| **TRUE obstacle rate**, fiction (w) | 0.72 | 0.77 | 0.70 | **0.71** |
| has_obstacle accuracy (w) | 0.88 | 0.85 | 0.75 | |
| Precision of "yes" (w) | 0.85 | 0.84 | 0.76 | **0.77** |
| Recall of true obstacles | 7/7 | 14/14 | 37/38 | 0.98 |
| False "yes" (raw) | 3/10 | 7/21 | 15/53 | **25/84** |
| Primary domain right, among true obstacles (strict) | 5/7 | 9/14 | 23/38 | 37/59 (63%); +12 partly right |
| **Locus right**, among true obstacles | 7/7 (w 1.00) | 11/14 (w 0.78) | 32/38 (w 0.92) | 50/59 (w 0.90) |
| Non-fiction leakage (works) | 1/11 | 1/23 | 3/56 | 5/90 |

**Answer to the coordinator: yes, the model over-labels, by about 15 points, in every era.**
- The true obstacle rate is about 0.71, not 0.88.
- Recall is near 1, so the errors are almost all false yeses.
- The excess is not obviously era-specific. The late era has the most false yeses (15/53), driven by mild-discomfort and description cases in popular and juvenile fiction.

## 2. Error patterns (n = 90)

| # | Pattern | Count/90 (era: E/M/L) | Example passage_id + quote | Proposed fix |
|---|---|---|---|---|
| 1 | **Over-labelling mild discomfort**: shyness, fatigue, nervousness, a momentary absence, which the character goes ahead despite | 9 (1/2/6) | pg8938_p00080 *Zenobia*: "Certainly they are not of such strength that I do not gladly seize upon the favor thus extended". pg42427_p00188: "Barbara was not there." | E1 |
| 2 | **Over-labelling description or essayistic narration**: labour procedure, hunting anecdote, deathbed tableau, narrator's survey | 6 (1/1/4) | pg42409_p00042: "This operation, involving the greatest amount of labor in the whole of the cutting-in". pg70827_p00126 (narrator's valedictory) | E1 |
| 3 | **Label taken from CONTEXT**: the passage has no obstacle, or a different one, and the obstacle appears only in ctx_before/ctx_after | 6 (0/2/4) | pg62794_p00032 (the tramps' plan is only in CONTEXT AFTER). pg72918_p00157 (ILLNESS taken from CONTEXT BEFORE) | E1 (context-only rule), E2 template markers |
| 4 | **Banter, flirtation, comic dialogue disagreement** as an obstacle | 3 (0/1/2) | pg32152_p00026 (widow and bachelor banter). pg65172_p00030: "It might excite comment if we drove up to the door." | E1 + negative few-shot |
| 5 | **SOCIAL_RANK_CONVENTION misused** (19 RANK codings, **12 wrong**: 7 are false yeses, 5 are a person's opposition, money or pride) | 8 tagged + 4 in false yeses (0/2/6) | pg39453_p00124: a woman manoeuvring a man away from a rival was coded RANK. pg16373_p00025: a reception the husband dislikes was coded RANK | E3 |
| 6 | **Locus default applied against the passage** | 5 among true obstacles (0/1/4); 9 locus errors in all | pg21748_p00174: massacre by slavers coded ILLNESS → material (should be social). pg48986_p00077: a steer blocking the road coded INTERPERSONAL → social (should be material). pg21813_p00112: a chief's pride coded social (should be internal) | E4 |
| 7 | **COMM failure_cause wrong** | 5/11 judged COMM items (2/1/2) | pg56658_p00039: "the secret has been quite lost for four hundred years" coded intentional_withholding (should be accidental_loss). pg32082_p00010: the telegraph is too long and costly (should be infrastructure). pg24210_p00400: fc set without the COMM domain | E5 + post-hoc fix P-a |
| 8 | **DARKNESS_VISIBILITY missed** when not-seeing is the obstacle | 2 (0/1/1) | pg16958_p00141: "As the night was dark, and the road the animals took in their furious course was not known" was coded NATURE+DISTANCE. pg72362_p00029: "he could not see the road immediately beneath him" | E6 |
| 9 | **night_function wrong** (concealment used for danger, or for a scene that is not at night) | 2/10 non-none items in the sample | pg62304_p00096 (terror in the dark coded concealment). pg42692_p00050 (not night) | E6 |
| 10 | **Non-fiction leakage**: Hazlitt, Yeats, Clarke, *Ornithology of Shakespeare*, Pyle's pirate history | 5 (1/1/3) | pg11068_p00015 Hazlitt on Bentham: labelled yes, COMM | Workcheck rule (now catches 4/5) |
| 11 | **Quote verbatim but not diagnostic** | 4/60 true obstacles | pg8939_p00064: "I might have been a criminal or an escaped embezzler." (the obstacle is the money he needs to marry) | E1(b) |
| 12 | **Picks a minor obstacle over the plot obstacle** | 2 | pg4922_p00011: seasickness chosen over captivity at sea | E1(b) |
| 13 | Under-label | 1 | pg61262_p00040, Poirot exposition (borderline) | none |

**The obstacle summaries are also weak.** `locus_reason` is **never filled**: 0 of 1,361 rows. Locus overrides are therefore unauditable. The schema should make it required when the locus differs from the default (see E4).

### SOCIAL_RANK_CONVENTION vs INTERPERSONAL_CONFLICT
Raw counts of domain mentions in the sample:

| Domain | Model, all yes (84) | Reference, true obstacles (60) |
|---|---|---|
| SOCIAL_RANK_CONVENTION | 19 | 9 |
| INTERPERSONAL_CONFLICT | 25 | 22 |
| COMMUNICATION_INFORMATION | 11 | 16 |
| ILLNESS_BODY_DEATH | 14 | 8 |
| DARKNESS_VISIBILITY | 3 | 5 |
| DISTANCE_TRAVEL | 8 | 5 |

RANK is **inflated about 2×**. Its 27% share in the population is not credible.
- About half of the excess comes from false yeses: dances, receptions, bedtimes, "conventions".
- The other half is a specific person's will or scheming, which belongs under INTERPERSONAL.

COMMUNICATION, on the other hand, is under-coded. Secrets, slander and missing information get absorbed into INNER, INTERPERSONAL or RANK.

## 3. Locus by era (H1)

| Era | Model locus, all yes (w): material / social / internal | Corrected, true obstacles only (w): material / social / internal |
|---|---|---|
| 1800–1849 (n 10 → 7) | 0.11 / 0.79 / 0.11 | 0.09 / 0.91 / 0.00 |
| 1850–1884 (n 21 → 14) | 0.20 / 0.70 / 0.11 | 0.03 / 0.86 / 0.11 |
| 1885–1929 (n 53 → 38) | 0.28 / 0.61 / 0.11 | 0.30 / 0.58 / 0.12 |
| All | 0.27 / 0.62 / 0.11 | 0.25 / 0.64 / 0.12 |

- **Overall, the errors roughly cancel.** False yeses have about the same locus mix (0.28 / 0.60 / 0.12) as true obstacles. Locus mistakes on true obstacles also go both ways: 5 over-assigned to social, 4 under-assigned.
- **The model's material-locus rise across eras survives correction, and looks steeper.** The corrected mid-era material share drops to 0.03, because the mid-era false yeses were mostly material: ILLNESS and NATURE description. This sample cannot estimate that well (n = 14). Re-check it on the w03 enrichment sample before reading anything into it.
- **The errors I found are not era-specific misreadings of archaic social-convention passages.** In fact the early era was the most accurate. Archaic and dialect diction (Maclaren's Scots, Uncle Remus, Marryat) was read correctly. The late-era problems are adventure and juvenile fiction:
  - animals coded INTERPERSONAL;
  - violence coded ILLNESS → material;
  - forest reverie coded NATURE.
- **Epistolary passages:** 2 of 3 were over-labelled (Pansy's letter, James's travel letter comic but defensible).

## 4. Quote failures (whole population: 130 / 1,192 obstacle rows = 10.9%)
Each failure was classified automatically against the passage and its context (`rapidfuzz` plus subsequence tests).

| Category | n | Share | Fix |
|---|---|---|---|
| **Quote copied wholly from CONTEXT** (before or after) | 76 | 58% | E2 rule + template markers |
| **Quote straddles the passage boundary** (passages often start or end mid-sentence) | 27 | 21% | E2, plus salvage P-b |
| Words dropped from the middle, or two speakers joined | 12 | 9% | E2 |
| Stitched with "..." | 7 | 5% | E2 |
| Dialect, spelling or casing edits | 3 | 2% | none (keep the fuzzy flag) |
| Paraphrase | 2 | 2% | E2 |
| Fabricated (not in passage or context) | 3 | 2% | E2 |

- **A quote from context is a red flag for the label, not only for the quote.** Of the 18 quote-from-context items in the sample, 6 (33%) also took their *label* from context (pattern 3).
- **The "19% hallucinated" figure in the raw table is inflated by a sync artefact.** 159 of the 265 "hallucinated" statuses belong to `has_obstacle = no` rows whose quote is "none".

## 5. Proposed changes for v0.9, in priority order by hypothesis impact
The exact text is implemented as variant `v09a` in `analysis/qa_ab.py` (built from the production prompt in the registry, read-only). Few-shot examples come only from passages reviewed here, with exact quotes. Those two passages are excluded from A/B scoring and must not enter the human audit set.

### E1: three-part test and an extended "not obstacles" list (H1 and every prevalence estimate; targets 18–21 of the 25 false yeses)
```diff
 When the passage is too fragmentary to tell, choose `insufficient_context`.
+**Three-part test (apply before answering yes).** Say to yourself: (a) WHO wants WHAT; (b) WHAT, inside the PASSAGE,
+stops, delays or endangers it; (c) WHERE the passage shows it changing what the character can do or what happens.
+If you cannot point to (b) and (c) inside the PASSAGE, answer `no`.
+**Also not obstacles:** mild discomfort, shyness, fatigue or nervousness that the character goes ahead despite; banter,
+teasing or flirtation; a character merely wondering or speculating; procedural or technical description of work, hunting
+or travel in which nothing goes wrong; a scene in which the goal is achieved and no impediment remains; an obstacle that
+appears only in CONTEXT BEFORE/AFTER.
```
Also add hard-case rule 7:
```diff
+7. **Comic, epistolary and dialect passages** follow the same three-part test; a letter-writer's reflections are not an
+   obstacle unless the letter reports something blocking a goal.
```
Few-shot examples, appended after the hard-case rules:
```diff
+1. "Certainly they are not of such strength that I do not gladly seize upon the favor thus extended, and count myself
+   honored and happy." — The speaker is shy of meeting a queen but goes ahead gladly. Nothing impedes him → no.  [pg8938_p00080]
+2. "And Bart, deciding that his sister's whims had already imposed far too many restrictions upon both his own activities
+   and Carver's, carefully refrained from delivering the message." → yes, COMMUNICATION_INFORMATION,
+   intentional_withholding, social_institutional.  [pg72909_p00168]
```

### E3: narrow SOCIAL_RANK_CONVENTION (H1 domain mix; 12/19 RANK codings wrong)
```diff
-| SOCIAL_RANK_CONVENTION | Class, propriety, reputation, marriage rules, gender norms, family authority as *a rule* | ... |
+| SOCIAL_RANK_CONVENTION | Class, propriety, reputation, marriage rules, gender norms, family authority as *a rule*: the
+  barrier would stop anyone in that position, not just this character with this person. A particular person's wishes,
+  dislike, schemes or commands are INTERPERSONAL_CONFLICT; a party, dress or etiquette that is merely present is not an
+  obstacle | ... |
```

### E4: locus follows the proximate source (H1; 9 locus errors)
```diff
 **Override the default whenever the passage says otherwise.** For example, illness that is clearly hysteria or "nerves" may be internal.
+Locus follows the *proximate source*, not the domain: death or injury inflicted by people is social; animals and terrain
+are material; the blocked character's own pride, fear or conscience is internal even when the domain is SOCIAL_RANK_CONVENTION.
```
Schema change (orchestrator): make `locus_reason` required and non-empty when the locus differs from the default mapping. It is never filled today.

### E5: failure_cause consistency and definitions (H2a)
**This is the biggest H2a risk.** In the population, **98 of 115 COMM rows (85%) are `intentional_withholding`**, and 41 obstacle rows carry a non-none failure_cause without the COMM domain. In the sample, 5 of 11 COMM items had the wrong cause.
```diff
   - `none`.
+- failure_cause and message_valence must be `none` unless COMMUNICATION_INFORMATION is in `domains`. A secret forgotten
+  or lost over time is `accidental_loss`; the cost, length or slowness of post or telegraph is `infrastructure`;
+  `intentional_withholding` needs someone who deliberately keeps or intercepts the message or fact.
```

### E6: DARKNESS_VISIBILITY and night_function (H2c)
In the population, **`concealment` is 111 of 140 non-none night_function values**, but only 40 rows carry DARKNESS. 37 of the 111 concealment rows have at most one night or dark word in the passage. The model is using concealment to mean "secrecy".
```diff
-| DARKNESS_VISIBILITY | Not being able to see: night, fog, lack of light, concealment by darkness |
+| DARKNESS_VISIBILITY | Not being able to see: night, fog, lack of light, concealment by darkness or terrain. Include it
+  whenever not-seeing is what stops the character, even if weather or terrain causes it |
-danger | concealment | intimacy | labor | leisure | none.
+danger | concealment | intimacy | labor | leisure | none. `concealment` = someone hides or moves unseen thanks to the dark;
+`danger` = the dark exposes someone to harm or terror. Use `none` if the scene is not at night or in darkness.
```

### E2: quotes and passage boundaries (G1 quote gate, and label-from-context)
```diff
-evidence_quote must be copied verbatim: 8-30 consecutive words from PASSAGE, unchanged.
+evidence_quote must be copied verbatim: 8-30 consecutive words that lie ENTIRELY inside PASSAGE, unchanged. Never quote
+CONTEXT BEFORE/AFTER. If the key sentence begins before the PASSAGE starts or runs past its end, copy only the part inside
+PASSAGE. Never use '...', never drop words, never join two sentences or two speakers.
```
User template:
```diff
-CONTEXT BEFORE (orientation only):\n{ctx_before}\n\nPASSAGE:\n{text}\n\nCONTEXT AFTER (orientation only):\n{ctx_after}
+CONTEXT BEFORE (orientation only; never quote it):\n{ctx_before}\n\n=== PASSAGE START (judge and quote ONLY this) ===\n{text}
+\n=== PASSAGE END ===\n\nCONTEXT AFTER (orientation only; never quote it):\n{ctx_after}
```

### Pipeline-side fixes (no new pin, no relabelling)
- **P-a.** At analysis time, force `failure_cause` and `message_valence` to `none` when COMM is not in `domains` (41 rows). Treat `night_function` as valid only when the passage has night or dark lexis or a DARKNESS domain; run H2c both ways as a sensitivity check.
- **P-b.** In `sync_results`, set `quote_status = 'n/a'` for rows where has_obstacle ≠ yes. Add a `trimmed` status in `verify_quote`: when a quote straddles the boundary, accept it if at least 8 consecutive words of it lie inside the passage. That recovers about 27 rows.
- **P-c.** Carry a `quote_from_context` flag. Run every confirmatory model with those rows excluded, as a sensitivity check, since a third of them have context-derived labels.
- **P-d.** Apply `workcheck_keep.parquet` (catalog rule) before w03/w05, and filter already-labelled rows from excluded works at analysis time. The rule now catches Hazlitt, Yeats and Clarke. I added the LCSH "-- Knowledge --" / "in literature" headings today, which catches *Ornithology of Shakespeare* (pass 1 unchanged: 0/185 fiction wrongly excluded, 0/12 non-fiction kept). Pyle's mixed fiction-and-fact *Book of Pirates* stays.

### Not proposed
- No change to the DISTANCE_TRAVEL definition (H2b). There were no clear DISTANCE errors, but **there was no early-era DISTANCE item in the sample at all**. H2b's early era cannot be QA'd from w01; it needs the w03 enrichment sample.
- No change for archaic diction or irony: no era-specific misreading was found.

## 6. A/B (prepared, NOT run)
The GPU belongs to another agent until 10:05, so I did not run the A/B. The kit is ready:
```
uv run --with pandas,rapidfuzz python -I analysis/qa_ab.py build          # done: data/work/label_ab_qa2/
flock /tmp/aacv_gpu.lock uv run python -I analysis/bench_label_ab.py run --dir data/work/label_ab_qa2 --variant v0   --par 4 --tag qa2
flock /tmp/aacv_gpu.lock uv run python -I analysis/bench_label_ab.py run --dir data/work/label_ab_qa2 --variant v09a --par 4 --tag qa2
uv run --with pandas,rapidfuzz python -I analysis/qa_ab.py score
```

Baseline already scored (`v0_synced`, the production outputs; 84 fiction items, few-shot items excluded, not design-weighted):

| has_acc | yes precision | yes recall | domain overlap | locus | RANK share of yes | quote in passage |
|---|---|---|---|---|---|---|
| 0.738 | 0.734 | 0.983 | 0.862 | 0.845 | 0.228 | 0.494 (sample oversampled bad quotes) |

**Adopt v09a only if every one of these holds:**
- has_obstacle accuracy rises by at least 0.08, with recall still at least 0.93;
- the RANK share of yeses is at or below 0.15;
- quote-in-passage is at least 0.97 on the fresh v0 rerun comparison;
- locus does not fall by more than 0.03;
- passages per hour stay at 70% or more of v0's. The system prompt grows from 6.7k to 9.6k characters, so the prefix cache matters here.

Also run both variants on the 60-passage bench set (`bench_label_ab.py build`'s passages) as an untouched check.

## 7. Date and metadata issues seen (for the date audit)
- pg51665 *Tippoo Sultaun* is dated 1880; it was published in 1840, so it belongs in the early era, not mid.
- pg2869 James, *The Point of View* is dated 1886; it was published in 1882, so mid era, not late.
- pg8938 *Zenobia* is dated 1827; it was published in 1837. This is harmless for era assignment.

Exemplars and cross-era pairs are in `docs/qa/exemplar_candidates.md`.
