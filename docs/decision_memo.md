# Decision memo: what we will study, and why (2026-10-31, v1.1)

## The decision
**Lead with a humanities finding: how the obstacles of English fiction changed, 1800–1920.** Inside the same study, prove that the measurement is trustworthy, using benchmark corpora with known answers and a fixed set of falsification checks. Neither the benchmark (B) nor the falsification agent (C) becomes a standalone product.

## The question, in one sentence a teacher would recognize
For a story to move, something must stand in a character's way. As railways, the penny post, the telegraph and gaslight reshaped daily life, **did novelists swap obstacles of distance, darkness and slow news for obstacles of rules, people and the mind?**

## Why this question
1. **It is open as a measurement.** A targeted sweep of ACL Anthology, JCA, CHR, DH abstracts and Scholar found no study that measures *goal-blocking obstacles* by domain and locus across ~15k UK/US novels from 1800 to 1920 (`docs/novelty_matrix.md`).
2. **It tests named claims.** We put established critics' arguments to the test rather than claiming to discover something new:
   - the inward turn (Kahler);
   - postal and telegraphic plots (Menke, Thomas, Koehler);
   - the railway journey and the disenchanted night (Schivelbusch);
   - the night before artificial light (Ekirch).
3. **It answers an existing null result.** Radak et al. found *no* common rise in inner-life vocabulary. We ask whether inwardness rose in *what drives plots*, even if not in word counts. That distinction between mention and function is exactly what close reading teaches, and it is our H3.
4. **It is cheap to make broad.** One labeling pass over random passages measures every obstacle type at once. The three technology deep dives reuse the same labels.

## Why not lead with the alternatives
- **Benchmark (B):** DiscoveryBench, BLADE, HypoBench, D5, LSC-Eval and HypotheSAEs already use injected ground truth. Our narrower twist is *confounded* nulls built from real archive artifacts (genre drift, reprint dates, duplicates, memorized canon), which test whether AI agents overclaim. That becomes the AAAI workshop paper and the validation layer.
- **Falsification agent (C):** POPPER (ICML 2025) already exists. We run deterministic, pre-registered checks instead, and cite it.

## What we will *not* claim
- That we are "first" to compute conflict (Häußler & Gius 2023), to test the inward turn (Radak et al.), or to trace night in fiction (Kim et al. 2020).
- That technology *caused* any shift. Hinges are dated context. Claims are associational, within genre, and bounded to "fiction preserved in Project Gutenberg".

## What happens if nothing shifts
That is a publishable result: "a widely held story about the modern novel does not survive genre and archive controls, yet AI research agents confidently tell it anyway." The benchmark and the measurement validation stand on their own.

## Success criteria, in order
1. Human–model agreement high enough to trust (gate G2).
2. One to three findings that survive pre-registration, Holm correction, at least 7 of the 9 robustness checks, and replication.
3. For every finding, paired passages (1820s vs 1900s) vivid enough that an English teacher would quote them in class.
