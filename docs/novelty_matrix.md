# Novelty matrix (v1.1, 2026-10-31)

Sources: the Claude verification agents plus the Codex sweep (`research/lit/novelty_sweep.md`, `refs.bib`, `critic_theses.md`). Each row has its link in those files. Anything marked UNVERIFIED there stays unverified here.

## Claim discipline (binding for all drafts)
**Never write:**
- "first computational history of conflict" (precedents: Häußler & Gius, CHR 2023; Christou & Tsoumakas 2025; "Modeling Conflict", JCA)
- "first quantified test of the inward turn" (precedents: Radak et al., *Mapping the Inner Lives*; Palkó 2025; Conroy, *Before the Inward Turn*)
- "first measurement of lighting-era change in fiction" (precedent: Kim, Pethe & Skiena 2020)

**May write, if results hold:** "the first corpus-scale measurement of *what blocks characters' goals* (obstacle domain and locus) across ~15k UK/US novels, 1800–1925, validated against human readers with verified evidence spans".

**Kahler's thesis:** it covers narrative up to about 1800. H1 *extends and operationalizes* it; we do not say it tests his own proposition.

**Menke and Thomas:** they *motivate* H2a. The directional prediction is ours (`critic_theses.md`).

## Closest prior work

| Work | What it does | Overlap | Our distinction |
|---|---|---|---|
| Radak et al. (*Mapping the Inner Lives*, PMC10682596) | Multilingual test of the inward turn via inner-life vocabulary; finds no common increase | **H1: high** | We measure the *function* of interiority (the inner state as what blocks the plot), not inner-life word rates. A lexical null alongside a functional shift (or null) is itself an H3-style result. |
| Palkó 2025; Conroy | Inward turn in Hungarian corpora and the early novel | H1: med | English UK/US corpus, plot function |
| Häußler & Gius, CHR 2023 (217 German novels); Christou & Tsoumakas 2025; JCA "Modeling Conflict" | Operationalize and measure conflict | H1/H2: med | Conflict ≠ goal-blocking obstacle typology. We add a material/social/internal locus and technology hinges. |
| Piper, "What do characters do?" (JCLS 2024) | Embodied character action | H1: low-med | Different construct |
| Kim, Pethe & Skiena, EMNLP 2020 | Time-of-day trends | H2c: med | Night's *function* as an obstacle; their trend serves as a known positive |
| N-gramming the railway (German fiction; Cambridge *Distant Readings*) | Railway lexis in fiction | **H2b: med-high (needs full-text read)** | Function rather than n-grams; English corpus |
| Menke 2008; Golden 2009; Thomas 2012; Koehler 2016 | Postal/telegraphic close reading | H2a: med | Corpus-scale test with counterexamples |
| Schivelbusch, *Railway Journey* / *Disenchanted Night*; Ekirch, *At Day's Close*; Carter 2001 | Cultural history of travel and light | Motivation | Testable consequences in fiction |
| DesireDB (2017); TACL 2024 narrative elements; LitVISTA (ACL 2026) | Goals, desires and narrative datasets | Method: med | Historical-trend inference, not detection |
| DiscoveryBench, BLADE, HypoBench, D5, HypotheSAEs, LSC-Eval | Synthetic ground truth for discovery | Benchmark: high | Confounded nulls built from real literary-history artifacts; we evaluate *overclaiming* |
| POPPER (ICML 2025) | Agentic falsification | C: high | Not claimed; deterministic battery |
| DSL (Egami et al. 2023); PPI (Angelopoulos et al. 2023) | Valid inference with LLM labels | Method | Adopted |
| Chang et al., *Speak, Memory* (2023); Bamman, Underwood et al., CHR 2024 | Memorization; LLM validity | Controls | Adopted |

## Open novelty checks
- N1-b: read the railway n-gram chapter in full before claiming anything for H2b.
- N1-c: read the Radak et al. method and results; cite their null result in the introduction as motivation for functional measurement.
- N1-d: read the Christou & Tsoumakas 2025 scope (diachronic relational arcs).
