# Related-work verification notes

Checked 2026-11-04. Every item below was fetched and read during this pass. "Full text" means I read the body of the paper (method and results sections), not only the abstract. Numbers are copied from the source. Relation statements are our positioning, not claims made by the cited authors. Bib keys refer to `research/lit/refs.bib`.

Our study, for reference: LLM-labelled (Gemma/Qwen cascade with verified evidence quotes) measurement of plot-obstacle/conflict types across Project Gutenberg English fiction over time, with a canon measure; DSL inference with expert-anchored gold labels; pre-registered and sealed. Side lesson: LLM agents in open-ended discovery benchmarks "narrate noise".

---

## 1. Radak et al., Mapping the Inner Lives (Open Research Europe 3:128) — `radak2024inner`

- **Fetched:** https://pmc.ncbi.nlm.nih.gov/articles/PMC10682596/ (full text, first ~100k of ~105k chars); Crossref for DOI 10.12688/openreseurope.16290.2. Version 2, 20 Mar 2024 (v1 23 Aug 2023). Ten authors (Radak, Burnard, Francois, Hilger, Jannidis, Palkó, Patras, Preminger, Santos, Schöch).
- **Measured:** the "inward turn" hypothesis, proxied by the share of inner-life ("mental") verb tokens among all verb tokens per novel. Six categories (perception, physiology, affect, volition/ability, cognition, moral judgement/obligation). The 3 most frequent verbs per category were picked by language experts.
- **Corpus:** ELTeC level-2 corpora for 1840–1920, 100 novels per language (58 for Norwegian). Ten languages claimed, nine in Table 1 (Serbian only preliminary). Extended corpora: Portuguese 1840–1949 (233), German 1760–1920 (1,147), French 1750–2000 (1,086).
- **Method:** no parsing. Polynomial fits, decade boxplots, density plots, and Mann–Whitney U comparing 1840–69 with 1890–1919.
- **Findings:** slight upward trends for English and Hungarian, downward for French, Norwegian, Portuguese and Slovenian. The authors: "the density plots and tests for statistical significance do not detect any differences of statistical significance". Subsets by category, canonicity and gender also show nothing significant. In the extended French corpus there is a significant *decline* (1750–99 vs 1950–99), especially for affect verbs. Among canonical novels, "Only in the English data do we see exactly the upwards trend we expected." Their conclusion: "the data do not confirm the original hypothesis of a rising trend". Possible reasons they give: the window is too short, the canon/non-canon mix, and confounding by narrative technique (showing vs telling, free indirect discourse).
- **Relation to us:** the closest prior test of an *internal* turn, with a null result. We differ in measuring the *function* of internal states as obstacles (person-vs-self), not their lexical frequency. We use a validated LLM labeller with gold-standard correction, not a fixed verb list. Their finding that English canonical novels alone show the expected rise directly motivates our canon measure: canon composition can manufacture a trend.

## 2. Häußler & Gius, Operationalizing and Measuring Conflict in German Novels (CHR 2023) — `haeussler2023conflict`

- **Fetched:** https://ceur-ws.org/Vol-3558/paper5179.pdf (full text via pdftotext). CEUR Vol-3558, pp. 426–440.
- **Measured:** social conflict following Glasl. Conflict needs (i) *incompatibility* in perceiving, thinking, feeling or wanting between agents and (ii) *impairment* of what the agent wants. Only incompatibility was annotated. Impairment is explicitly left to future work.
- **Corpus:** German Romantic corpus (115 novels, d-RoRo) plus Realism/Naturalism (102 novels, from d-Prose 1870–1920).
- **Method:** (a) manual sentence-level annotation of 1,000 random sentences by two annotators; (b) SentiArt-style word2vec scores using label-word poles (conflict vs harmony from Dornseiff; conflict vs resolution from a prior annotation study), averaged per sentence.
- **Findings:** inter-annotator Cohen's kappa = 0.325. Gold standard has 107 incompatibility sentences out of 1,000. Embedding vs manual labels: precision 0.11, recall 0.61, F1 0.19 at threshold 0; F1 0.15 at Q3 (0.19 and 0.11 for the resolution variant). Conflict values rise during the Romantic period, described as preliminary and needing inspection. In Lucinde, conflict correlates with valence at r = −0.85. The authors call the correlation between the two approaches "low".
- **Relation to us:** the closest historical computational *conflict* precedent, so we must not claim "first computational history of conflict". We differ in (i) operationalising impairment (an obstacle to a goal), which they left for future work; (ii) a typed taxonomy (person/nature/society/self/technology) instead of a scalar; (iii) English Gutenberg fiction at larger scale; (iv) evidence-quoted LLM labels with gold-corrected inference. Their low kappa and low F1 are a useful baseline for how hard the construct is.

## 3. Smeets, De Pourcq & van den Bosch, Modeling Conflict (JCA 6(3), 2021) — `smeets2021conflict`

- **Fetched:** https://culturalanalytics.org/article/24722 (blocked by the Anubis bot wall, no content); https://pure.knaw.nl/portal/en/publications/modeling-conflict-representations-of-social-groups-in-present-day/ (metadata and abstract); Crossref for DOI 10.22148/001c.24722 (vol 6, issue 3, 2021-06-09). **Abstract only.**
- **Measured:** character–character conflict as a narrative mechanism, linked to social groups. Two computational models (dyadic and triadic), drawing on narratology, conflict studies and network theory.
- **Corpus:** 170 present-day Dutch novels, with case readings of Koubaa's *De Brooklynclub* (2012) and de Winter's *VSV* (2012).
- **Findings (abstract):** "lower educated characters are more dominant in dyadic conflicts"; "the majority of triadic conflicts exist in a state of social balance".
- **Relation to us:** shows that conflict can be modelled computationally, but only as person-vs-person social-network conflict in a synchronic contemporary corpus. We cover non-interpersonal obstacle types and a diachronic trend. Method details (how conflict edges are detected) are UNVERIFIED because the full text was not read.

## 4. Christou & Tsoumakas, Relational arcs as narrative structure (Computational Humanities Research 2, e2) — `christou2025arcs`

- **Fetched:** Cambridge Core article page (full text up to a truncated conclusion; figures were placeholders); Crossref. Online 19 Dec 2025; volume 2 (2026), article e2; CC BY.
- **Measured:** trajectories of character relations across narrative time, grouped into relation families: Kinship, Romance, Alliance, Enmity, Rivalry, Authority, Moral–Symbolic (the text says "six" in places but lists seven).
- **Corpus:** ARF dataset of 96 English Project Gutenberg novels, about 1850–1950, balanced by author gender and topic. 95,475 windows, >120,000 relation mentions. Six genre groupings derived from Gutenberg tags.
- **Method:** GPT-4o extracts ⟨e1, r, e2⟩ triples from 5-sentence sliding windows using a 48-relation, 11-entity ontology. Books split into 20 bins. MAD change points. OLS by decade with a Poisson/NB GLM robustness check. k-means (k=4) on z-normalised arcs.
- **Findings:** the largest adversarial (Enmity) crest is in the final bin, about 0.11 per chunk, "co-occurring with renewed alliance and kinship". Diachronically, Alliance rises, Kinship declines and partly rebounds, Enmity increases late in the period, and Romance declines gently. The authors read this as a shift "from kin-structured plots toward plots organized by companionship and group action". "Decline" is the most common arc shape. In the visible text the diachronic slopes are qualitative, with no coefficients. The authors acknowledge that the LLM annotations "introduce both stochastic noise and interpretive bias", and the paper has no gold-standard correction.
- **Relation to us:** the closest prior on corpus and method: LLM extraction, English Gutenberg fiction, a diachronic claim. The differences: they count relations (ties), not obstacles to goals or obstacle type. Their 96 novels are small for decade-level trends. They use uncorrected LLM labels with no design-based inference or pre-registration, which is exactly the gap DSL with expert gold labels addresses.

## 5. Youngman & Carmichael, N-Gramming the Railway in Nineteenth-Century German Fiction (in *Distant Readings*, 2014) — `youngman2014railway`

- **Fetched:** Cambridge Core chapter page (metadata and opening summary). The full text is **paywalled** ("Get access"). Chapter 11, pp. 285–300, eds. Erlin & Tatlock, Boydell & Brewer, online 5 Apr 2014. No chapter DOI is shown on the page. Searches found no open copy. The H-Net review returned 403 and the De Gruyter chapter page returned 405.
- **What I saw:** the opening summary only discusses the epistemology of big data and IT in the humanities (Humphreys, Shaviro). The page does not describe the corpus, the n-gram source (it does not say whether Google Books is used), or any findings.
- **Relation to us:** cite only as a topical precedent for computational study of railway/technology in 19th-century fiction. Corpus, method and findings are **UNVERIFIED**. Do not attribute any result to it, and do not claim our person-vs-technology measurement is the first computational treatment of technology in fiction without reading the full text.

## 6. Kim, Pethe & Skiena, What time is it? Temporal Analysis of Novels (EMNLP 2020) — `kim2020time`

- **Fetched:** https://aclanthology.org/2020.emnlp-main.730.pdf (full text); Crossref. pp. 9076–9086, DOI 10.18653/v1/2020.emnlp-main.730. Title and venue as the user guessed: confirmed.
- **Measured:** the clock time (hour of day) of each passage of a novel.
- **Corpus:** 52,183 deduplicated books from Project Gutenberg (10,489) and HathiTrust (97,772 before deduplication; English fiction filtered following Underwood). 12.04% of books contain no clock times.
- **Method:** regex/SUTime extraction of hourly phrases; an AM/PM classifier (86.3% accuracy); 24-class BERT time-of-day classifier (average error 2.27 h); dynamic-programming segmentation, which beats the noon baseline by about 2 h. Annotators disagree by 1.85 h on *Gatsby*.
- **Findings:** "the fraction of events taking place past 10 P.M jumps past 1880 - coincident with the advent of the electric light bulb and city lights". Afternoon references rise, dinner hours (6–9 pm) and 8–9 am fall. **Historical grouping uses author birth year in 20-year bins, not publication date,** and only Gutenberg books are used for that analysis. The electric-light reading is the authors' interpretation, with no causal test.
- **Relation to us:** a direct precedent for a Gutenberg-scale diachronic measurement that links a literary trend to technological modernity. Our design improves on two weaknesses visible here: dating (we audit publication dates, and they use author birth year) and inference (we use gold-corrected confidence intervals; they report descriptive shares).

## 7. Underwood, Bamman & Lee, The Transformation of Gender in English-Language Fiction (JCA 3(2), 2018) — `underwood2018gender`

- **Fetched:** author preprint https://osf.io/fr9bk/download (full text; the PDF header carries the JCA DOI 10.22148/16.019); Illinois Experts record; Crossref (vol 3, issue 2, 2018-02-13). culturalanalytics.org was blocked by the bot wall and the IDEALS PDF returned 403/HTML.
- **Measured:** (a) how distinctly gendered character descriptions are over time; (b) women's share of authorship and of character space.
- **Corpus:** 104,000 works of fiction, mostly from HathiTrust, 1703–2009 (focus 1780–2007), checked against the Chicago Novel Corpus (1880–1989) and a Publishers Weekly sample.
- **Method:** BookNLP character clustering and gender inference (women: 94.7% precision / 83.1% recall; men: 91.3% / 85.7%). Per-decade regularised classifiers predict character gender from the words attached to each character (15 models per decade, 1,600 characters each, median of about 54 words per character). Bootstrap confidence bands.
- **Findings:** gender becomes less predictable from characterisation from about 1850 onward (accuracy falls from about 76% to about 66% over 230 years). Women's share of fiction authorship "drops by half (from roughly 50% of titles to roughly 25%) as we move from 1850 to 1950". The share of female characters also falls.
- **Relation to us:** the template for large-scale diachronic measurement of a narrative property in English fiction. It also shows that corpus composition (library collecting, authorship) drives trends, which supports our canon measure and composition controls. Our construct is plot obstacles, not characterisation, and our labels come from an LLM with gold correction rather than BookNLP plus classifier accuracy.

## 8. Bamman, Chang, Lucy & Zhou, On Classification with Large Language Models in Cultural Analytics (CHR 2024) — `bamman2024classification` (new)

- **Fetched:** https://arxiv.org/pdf/2410.12029 (full text); https://ceur-ws.org/Vol-3834/ (TOC: pp. 494–527, paper119.pdf; eds. Haverals, Koolen, Thompson).
- **Measured:** how classification is used in cultural analytics (a six-way typology), and how prompted and fine-tuned LLMs compare with supervised models on ten public tasks.
- **Data:** ten English datasets: atypical animacy, emotion, folktales (ATU), genre (Gutenberg, LoC subjects), haiku, Hippocorpus, literary time (Underwood), narrativity, technological strangeness, stream of consciousness. Splits are stratified by author, genre or title.
- **Method:** logistic/ridge regression, BERT, RoBERTa, fine-tuned Llama 3 8B, and few-shot GPT-4o, Llama 3 70B and Mixtral 8x22B. Membership-inference memorisation check.
- **Findings:** prompted LLMs are "competitive with traditional supervised models for established tasks, but perform less well on de novo tasks". Examples: on folktales GPT-4o scores 0.838 vs RoBERTa 0.616; on strangeness GPT-4o scores 0.564 vs BERT 0.879; on literary time GPT-4o reaches ρ = 0.485 vs RoBERTa 0.782. They see little evidence that memorisation drives the folktale result.
- **Relation to us:** our obstacle-type labelling is closer to a *de novo* construct than an established one. That predicts that zero-shot LLM labels will be noisy and argues for expert gold labels plus bias-corrected inference rather than trusting raw LLM accuracy. Our cascade with evidence quotes and DSL correction is a response to this result.

## 9. Chang, Cramer, Soni & Bamman, Speak, Memory (EMNLP 2023) — `chang2023speak` (new)

- **Fetched:** https://arxiv.org/pdf/2305.00118 (full text, v2); https://aclanthology.org/2023.emnlp-main.453/ (pp. 7312–7327, DOI 10.18653/v1/2023.emnlp-main.453).
- **Measured:** which books ChatGPT and GPT-4 have memorised, using name-cloze membership inference (the human baseline is 0%).
- **Corpus:** 571 works of fiction from 1749–2020, including 91 pre-1923 LitBank (Gutenberg) novels, Pulitzer nominees, bestsellers, Black-authored and Global Anglophone fiction, and genre fiction.
- **Findings:** GPT-4 name-cloze accuracy is highest for pre-1923 LitBank (0.244) and SF/fantasy (0.235), and low for Global (0.020) and BBIP/BCALA (0.017). Top memorised titles are public-domain canon (*Alice*: 0.98). Memorisation tracks how often a book appears on the web. Downstream, predicting year of first publication from a 250-word passage has MAE 0.6 y (GPT-4) on the most memorised decile vs 14.5 y on the least (ChatGPT: 3.3 vs 29.8). Spearman ρ between memorisation and error is −0.39 (ChatGPT) and −0.37 (GPT-4).
- **Relation to us:** a central validity threat. Canonical Gutenberg novels are exactly what LLMs have memorised, so LLM labels may track plot knowledge or canonicity rather than passage evidence. This motivates (i) our canon measure as a covariate and stratifier, (ii) requiring verified evidence quotes from the passage, and (iii) expert gold labels sampled across canon strata so DSL corrects canon-dependent label error. It also warns against using LLMs to date texts.

## 10. Egami, Hinck, Stewart & Wei, Design-based Supervised Learning (NeurIPS 2023) — `egami2023dsl`

- **Fetched:** https://arxiv.org/pdf/2306.04746 (full text, v3, which states NeurIPS 2023). The existing bib URL is the NeurIPS proceedings page.
- **Measured/method:** downstream regression or moment estimation using imperfect LLM surrogate labels. DSL fits g(Q, X) on a gold subset and builds doubly-robust pseudo-outcomes Ỹ = ĝ + (R/π)(Y − ĝ) using a *known* gold-sampling probability π. It is validated on 18 datasets.
- **Findings:** surrogate-only estimation is biased and gives invalid confidence intervals "even with high surrogate accuracy of 80–90%". In their simulation, a 90%-accurate surrogate gives 95% CI coverage of only about 40%. DSL keeps asymptotic unbiasedness and nominal coverage "even when surrogates are arbitrarily biased", with RMSE comparable to prediction-only alternatives.
- **Relation to us:** our inference engine, a foundation rather than a novelty claim. Our contributions are applying it to literary-historical trend estimation with expert-anchored gold labels, documenting π by design (stratified by decade and canon), and pre-registering the estimand.

## 11. Angelopoulos, Bates, Fannjiang, Jordan & Zrnic, Prediction-Powered Inference (Science 382(6671):669–674, 2023) — `angelopoulos2023ppi`

- **Fetched:** https://arxiv.org/pdf/2301.09633 (full text, v4); Crossref for the journal metadata (the Science and PubMed pages did not load: cookie wall).
- **Method:** combine many ML predictions with a small gold sample (a "rectifier" correction) to get valid confidence intervals and p-values for means, quantiles, and linear/logistic regression coefficients, with no assumptions on the predictor. More accurate predictions give narrower intervals.
- **Findings:** demonstrated on proteomics (AlphaFold), galaxy classification, genomics, remote sensing, census and ecology. PPI needs fewer labelled examples than classical inference to reject a null at the 95% level (their Table 2: n = 316 vs 799 for AlphaFold; 189 vs 449 for galaxies).
- **Relation to us:** an alternative to DSL. Cite it as the general framework. The core PPI results assume i.i.d. labelled and unlabelled data; the paper also gives extensions for distribution shift and non-i.i.d. settings. We use DSL because it builds in known, non-uniform gold-sampling probabilities and covariate-dependent correction (X = year, canon). Neither framework validates the obstacle construct itself.

## 12. Piper, So & Bamman, Narrative Theory for Computational Narrative Understanding (EMNLP 2021) — `piper2021narrative`

- **Fetched:** https://aclanthology.org/2021.emnlp-main.26.pdf (full text); Crossref (pp. 298–311).
- **Content:** a position paper. It proposes a minimal model of narrativity ("Someone tells someone somewhere that someone did something(s) [to someone] somewhere at some time for some reason") and reviews NLP work on agents, events, structure, temporality, space and perspective. It urges document-level work to target "disequilibrium" and "change of state" rather than Labov's most-reportable event. It asks how family relations changed historically "with respect to questions of size, hierarchy, and conflict", and lists narrative-type classification for cultural-evolution questions as a major challenge.
- **Findings:** none empirical.
- **Relation to us:** theoretical grounding. Obstacles and conflict operationalise the disequilibrium and agent-goal ("for some reason") components they call for, applied to the historical question they pose.

## 13. Discovery benchmarks (side lesson: agents "narrate noise")

### 13a. DiscoveryBench (Majumder et al., ICLR 2025) — `majumder2025discoverybench`
- **Fetched:** https://arxiv.org/pdf/2407.01725 (full text, v1); ICLR 2025 proceedings page (confirms venue and authors).
- 264 real tasks from published papers across 6 domains, plus 903 synthetic tasks. Each task gives a dataset, metadata and a natural-language goal. Scored with a hypothesis match score over context, variables and relations.
- "even the best system scores only 25%". The domain split is uneven: biology 0%, engineering 7%, economics 25%, sociology 23%.
- **Relation:** it evaluates recovery of a known gold hypothesis. It does not test whether agents *abstain* when no effect exists or when an apparent trend is a composition artefact. That gap is what our noise-narration lesson addresses.

### 13b. BLADE (Gu et al., Findings of EMNLP 2024) — `gu2024blade`
- **Fetched:** https://aclanthology.org/2024.findings-emnlp.815.pdf (full text; pp. 13936–13971).
- 12 datasets and research questions with ground truth from independent analyses by expert analysts (11 recruited experts). Evaluates the choice of conceptual variables, transformations and statistical models against a space of justifiable decisions.
- LMs are "often limited to basic analyses". Coverage@10 is below 13% for statistical models with conceptual variables and below 27% for operationalisations. GPT-4o produces executable analyses 96% of the time. LMs hallucinate data columns (the soccer example). ReAct agents improve coverage.
- **Relation:** the closest precedent for judging the *analysis decisions* of agents. It scores coverage of justifiable analyses, not overclaiming on null or confounded data.

### 13c. HypoBench (Liu, Huang, Hu, Zhou & Tan, arXiv 2504.11524) — `liu2025hypobench`
- **Fetched:** https://arxiv.org/pdf/2504.11524 (full text, v2 dated 10 Feb 2026). **Peer-reviewed venue UNVERIFIED.** Search found only arXiv citations.
- 7 real and 5 synthetic tasks, 194 datasets. Four LLMs crossed with six hypothesis-generation methods. Metrics: utility, generalisability, hypothesis discovery rate (HDR).
- At base difficulty the best HDR is 93.8%. As difficulty rises (noise, distractors, subtlety), the best recovers only 38.8%, and below 30% in some settings.
- **Relation:** synthetic ground truth with controlled noise and distractors is close to our null-control idea. Its endpoint is recovery, though, not penalising confident claims on noise.

### 13d. D5 (Zhong, Zhang, Li, Ahn, Klein & Steinhardt, NeurIPS 2023) — `zhong2023d5`
- **Fetched:** https://arxiv.org/pdf/2302.14233 (full text, v2, which states NeurIPS 2023).
- The task: given a goal and two corpora, output a natural-language predicate describing how they differ. Evaluated on SynD5 (known synthetic differences) and OpenD5 (675 open problems across business, social science, humanities, ML and health).
- The goal-conditioned system is correct 12% more often on SynD5 and produces relevant discoveries 31% more often on OpenD5. The authors warn that it "discovers correlation rather than causation" and that outputs should be treated "with caution". Its datasets include time-period corpus splits.
- **Relation:** the closest prior for corpus-difference discovery, including diachronic splits. Our lesson adds that agents produce confident causal narratives for differences that are noise or composition effects. D5 flags this risk in its limitations but does not measure it.

### 13e. POPPER (Huang, Jin, Li, Li, Candès & Leskovec, ICML 2025) — `huang2025popper`
- **Fetched:** https://arxiv.org/pdf/2502.09858 (full text); PMLR v267 pp. 25372–25437 (confirmed).
- LLM agents design falsification experiments on measurable implications of a free-form hypothesis. Sequential e-value aggregation gives Type-I error control (evaluated at α = 0.1). An LLM relevance checker guards against irrelevant tests. Tested across six domains.
- Reports "robust error control, high power". Comparable to human scientists on complex biological hypotheses "while reducing time by 10 folds".
- **Relation:** the closest prior for *controlling false discoveries* by agents. The guarantee holds only if each agent-designed test is valid and actually implied by the hypothesis. Our noise-narration finding concerns the narrative layer that sits outside such tests, plus pre-registration and sealing as the human-side analogue.

---

## Verification status

| # | Work | Bib key | Status | Source actually read |
|---|------|---------|--------|----------------------|
| 1 | Radak et al. 2024 | radak2024inner | Verified, full text | PMC10682596 + Crossref |
| 2 | Häußler & Gius 2023 | haeussler2023conflict | Verified, full text | ceur-ws Vol-3558 paper5179.pdf |
| 3 | Smeets et al. 2021 | smeets2021conflict | Abstract only | KNAW Pure + Crossref (JCA bot-walled) |
| 4 | Christou & Tsoumakas 2025 | christou2025arcs | Verified, full text (conclusion truncated) | Cambridge Core + Crossref |
| 5 | Youngman & Carmichael 2014 | youngman2014railway | Metadata + opening summary only (paywalled); content UNVERIFIED | Cambridge Core chapter page |
| 6 | Kim, Pethe & Skiena 2020 | kim2020time | Verified, full text | ACL Anthology PDF + Crossref |
| 7 | Underwood, Bamman & Lee 2018 | underwood2018gender | Verified, full text (author preprint) | OSF fr9bk + Illinois Experts + Crossref |
| 8 | Bamman et al. CHR 2024 | bamman2024classification | Verified, full text | arXiv 2410.12029 + CEUR Vol-3834 TOC |
| 9 | Chang et al. 2023 | chang2023speak | Verified, full text | arXiv 2305.00118 + ACL Anthology |
| 10 | Egami et al. 2023 | egami2023dsl | Verified, full text | arXiv 2306.04746 v3 |
| 11 | Angelopoulos et al. 2023 | angelopoulos2023ppi | Verified, full text (arXiv); journal metadata via Crossref | arXiv 2301.09633 v4 + Crossref |
| 12 | Piper, So & Bamman 2021 | piper2021narrative | Verified, full text | ACL Anthology PDF + Crossref |
| 13a | DiscoveryBench | majumder2025discoverybench | Verified, full text | arXiv 2407.01725 + ICLR page |
| 13b | BLADE | gu2024blade | Verified, full text | ACL Anthology PDF + Crossref |
| 13c | HypoBench | liu2025hypobench | Verified, full text; venue UNVERIFIED (preprint) | arXiv 2504.11524 v2 |
| 13d | D5 | zhong2023d5 | Verified, full text | arXiv 2302.14233 v2 |
| 13e | POPPER | huang2025popper | Verified, full text | arXiv 2502.09858 + PMLR page |

## Could not verify

- **Youngman & Carmichael (2014):** the corpus, n-gram source, method and findings. Paywalled on Cambridge Core, and no open copy or review text was reachable. No chapter DOI is shown on the Cambridge page. A De Gruyter DOI exists by pattern for other chapters but was **not** confirmed for this chapter and is not used.
- **Smeets et al. (2021):** methods and results beyond the abstract. culturalanalytics.org is behind a bot wall, so the conflict-detection procedure is unverified.
- **HypoBench:** any peer-reviewed venue. Cite as an arXiv preprint.
- **Christou & Tsoumakas:** the end of the conclusion and any numeric diachronic coefficients (the fetched text was truncated, and the diachronic trends are given qualitatively in the part read).
- **Angelopoulos et al.:** the Science publisher page itself (403/cookie wall). Journal metadata comes from Crossref, content from the authors' arXiv v4.
- **Underwood et al.:** the journal-hosted version (bot wall). Content was read from the authors' OSF preprint, which carries the journal DOI.
