# Venue fit: literary obstacles, AI research agents, and student NLP research

Research date: **2026-10-31**. Primary sources were checked by web search and page retrieval. **UNVERIFIED** means the cited sources do not establish the claim, not that the claim is false. Recommendations and predicted reviewer objections are analysis, not organizer statements. Exact excerpts below are short; the policy tables summarize the remaining clauses and identify their source sections. No results from this project have been assumed.

## Decisions

| Venue | Fit and recommended contribution | Decision |
|---|---|---|
| AAAI-27 Effective and Efficient Evaluation for AI Scientists | Strong for the confounded-null benchmark; weak for a standalone literary history study. Evaluate research agents' warranted inference, not just passage classification. | Target **resource/artifact, 2–4 pages**, if a runnable benchmark is ready; otherwise an honestly framed position paper. |
| DH2027 short paper | Strong for a humanistic question with interpretable evidence, validation, and close reading. | Target **1,000–1,250 words** and one principal finding or unresolved test. This is an extended abstract, not an ACL-style short paper. |
| NAACL 2027 SRW | Strong conditional fit for student-led cultural analytics with an evaluated NLP contribution. High-school eligibility is explicit. | Request mentorship by **November 16**; target a **long research paper, 8 content pages**, in January. Choose archival/non-archival deliberately. |

Venue policies: [AAAI workshop](https://eval-ai-scientists.github.io/aaai27/), [DH CFP](https://dh2027.adho.org/call-for-proposals/), [SRW CFP and guidelines](https://naacl27-srw.github.io/). These are fit judgments, not acceptance probabilities.

## A. AAAI-27 workshop: verified policy and exact excerpts

From the workshop's **Call for papers** and **Submission details**:

> “Submissions should directly address the evaluation of autonomous scientific discovery.”
>
> “Non-archival, authors retain full rights”

From AAAI's official **workshop listing**, under this workshop's Submission Guidelines:

> “Resource and artifact papers (2-4 pages): A released benchmark, harness, corpus, or tool, submitted together with the artifact.”

Sources: [workshop CFP](https://eval-ai-scientists.github.io/aaai27/#submissions), [AAAI listing, workshop entry](https://aaai.org/conference/aaai/aaai-27/aaai-27-workshop-program-list/). Locate the workshop title in the official listing.

| Requested item | Verified rule / boundary |
|---|---|
| Topics | Measurement validity, research-agent benchmarks, judge calibration, power, leakage, ranking sensitivity, and reproducibility are in scope. |
| Formats and limits | Full 6–8 pages; position, resource/artifact, reproduction/negative-result 2–4. References excluded explicitly for full papers; exclusion for the short categories and appendix allowances are **UNVERIFIED**. |
| Template/anonymity | Official AAAI-27 two-column kit; anonymous PDF; double-blind review. |
| Review | At least two reviews, third on disagreement. Artifact papers: execution and documentation; reproduction reports: reporting rigor, no novelty requirement. Comparisons need matched compute/token budgets or explanation. |
| Eligibility | No degree/student/age restriction stated; explicit high-school permission **UNVERIFIED**. Do not apply doctoral-consortium eligibility rules. |
| Dual submission | Other submissions welcome only where the other venue permits them. |
| Attendance | At least one author must register and present in person; virtual presentation unavailable. |

Table source: [workshop CFP, Topics of interest through Important dates](https://eval-ai-scientists.github.io/aaai27/). Template: [official AAAI-27 author kit ZIP](https://aaai.org/authorkit27/), linked from [AAAI-27](https://aaai.org/conference/aaai/aaai-27/). The kit URL was verified, but its contents could not be inspected because direct retrieval returned 403; internal kit requirements remain **UNVERIFIED**.

**LLM disclosure.** The workshop page has no separate disclosure clause. AAAI's broader publication policy says:

> “its role is properly documented in the manuscript”

That policy covers AI use in developing AAAI-affiliated publications, denies AI authorship, and makes authors accountable for all content. Apply it conservatively to this non-archival workshop: disclose labeling, agent experiments, code assistance, and manuscript assistance, without identifying authors. Whether a particular submission-form field is required is **UNVERIFIED**. [AAAI publication policies, AI-systems policy](https://aaai.org/aaai-publications/aaai-publication-policies-guidelines/).

**Best title:** *Plausible Stories from Null Corpora: Do AI Scientist Agents Overclaim Literary-Historical Trends?*

**Best argument:** a fluent historical explanation is not evidence of valid discovery. Controlled corpora expose whether agents distinguish description, association, and causal explanation when literary-historical narratives are readily available. Make literature the demanding test domain and inference validity the general contribution.

**Recommended evidence, not CFP requirements:**

1. Define each task's estimand and permitted claim. A confounded corpus may contain a real marginal trend: calling every trend a false positive would invalidate the benchmark. Distinguish association detection from unsupported causal attribution.
2. Include date-shuffled controls, confounded mixtures with known construction, and planted effects. Describe what each manipulation preserves and destroys. Randomization creates a design-based null; it does not prove that the original books have no historical signal.
3. Score claims, evidence citations, uncertainty, confound detection, and abstention. Measure false discoveries alongside sensitivity to planted effects so a system cannot win by refusing every claim.
4. Run repeated seeds/corpora, with a simple statistical workflow and a non-agentic LLM baseline. Compare agents under matched budgets; log tokens, model versions, prompts, tool traces, and cost.
5. Validate scoring against blinded human judgments on a subset. Separate labeler error, analyst error, and judge error; using one LLM family for all three creates correlated failure.

**Likely reviewer objections:** an instruction-following chatbot is labeled an autonomous scientist without a research workflow; the null is not actually null for the scored claim; the judge rewards cautious language rather than correctness; only a single handpicked failure is shown; the artifact needs private keys/data without a documented replay path. For the resource track, a promised later release does not meet the published artifact description. A new benchmark is not automatically a reproduction report merely because its agents fail.

## B. DH2027 short paper: verified policy and exact excerpts

From the CFP's **Submission and presentation formats**:

> “Short papers (1000-1250 words)”
>
> “Authors need to disclose any use of generative AI when performing their research or when preparing their submission.”

Source: [DH2027 CFP](https://dh2027.adho.org/call-for-proposals/), also [ADHO's official CFP republication](https://adho.org/2026/10/07/cfp-adho-invites-submissions-for-its-annual-conference-dh2027-at-the-university-of-galway-ireland-from-june-28-to-july-3-2027/). The conference-hosted page was readable through direct HTTP retrieval despite failures in the browser tool.

| Requested item | Verified rule / boundary |
|---|---|
| Topics | Broad DH scope; direct engagement with the Creativity theme is optional. Creative methods/interpretation is a plausible connection. |
| Format | Short papers suit experiments, exploratory research, work in progress, and early tools; typical presentation 10 minutes. |
| Counting | Captions count; table contents, references, and GenAI disclosure do not. Additional tables/figures may go in an appendix. No page limit stated. |
| Template | Initial PDF only; no mandated initial template located. |
| Anonymity | Open review: author and reviewer identities disclosed to each other. Do not anonymize. |
| Eligibility | No educational-level restriction located; explicit high-school clause **UNVERIFIED**. |
| Publication | Short contributions appear in the Book of Abstracts. Only long papers enter the separate Anthology of Computers and the Humanities proceedings. Calling the short track formally non-archival is **UNVERIFIED**. |
| Dual submission | No explicit cross-venue rule found in CFP/FAQ: **UNVERIFIED**. Multiple DH proposals are allowed; this is not permission for cross-venue duplicate submission. |

Sources: [DH CFP](https://dh2027.adho.org/call-for-proposals/), [FAQ: submission process, publication, and presentation limits](https://dh2027.adho.org/dh-2027-faq/). FAQ also allows a consistent field-appropriate reference style and describes partly hybrid participation. It does not promise a substantially longer final short paper.

**Review criteria.** All formats need a cited literature review and a complete account adequate to assess the contribution. Short papers may report anticipated outcomes, but identify them as anticipated. The published rubric lists background/references 20%; advance beyond existing work 20%; method and rationale 20%; diversity of topics/perspectives and recognition of relevant scholarship 15%; structure/clarity 15%. These displayed weights total **90%, not 100%**; the CFP does not explain the discrepancy. Do not invent a missing criterion or normalize it. [DH CFP, Note on Review Expectations and Review Process and Criteria](https://dh2027.adho.org/call-for-proposals/).

From the FAQ's anonymity answer:

> “DH2027 uses an open review process.”

No named Limitations or Ethics section is prescribed in the checked CFP/FAQ. A concise limitations paragraph is still advisable. [DH FAQ](https://dh2027.adho.org/dh-2027-faq/).

**Best title before results:** *What Stands in the Way: Testing the Inward Turn of Obstacles in English Fiction, 1800–1925*.

If results support H1, a possible result-led title is *From Material Barriers to Inner Conflict? Plot Obstacles in English Fiction, 1800–1925*. Keep the question mark unless the evidence warrants a stronger assertion. Avoid claiming that modernity or railways caused a shift from a year trend alone.

**Best argument:** narratological function is a different historical object from vocabulary. A railway can be mentioned without obstructing action; a letter can obstruct a plot through intentional withholding rather than failed infrastructure. Place H3 and passage examples beside one focused historical test, ideally H1. Use the supplied Kahler/Menke/Golden/Thomas/Koehler/Kim leads only after checking the actual publications; their bibliographic details were not independently audited in this venue report.

**Likely reviewer expectations and pitfalls:**

- Define an obstacle relative to a character's goal; distinguish it from setting, theme, generic adversity, and an event with no impeded action. Short random passages may lack the goal/outcome context needed to infer plot function. Test a context-window expansion on a subset and call the primary estimate passage-level obstacle representation.
- Explain why internal, social, and material loci answer a scholarly question. Intentional withholding is not automatically internal: mechanism, domain, and locus are different axes.
- Combine a plot-function-versus-keyword example with close reading of the historical pattern and a counterexample. Let annotation disagreement expose interpretive ambiguity rather than treating literature as undisputed labels.
- Qualify the corpus: digitization, public-domain survival, metadata dates, country assignment, genre, author repetition, reprints, and duplicate editions can change period composition. Project Gutenberg English novels are not a representative sample of all English fiction.
- Validate accuracy across periods and classes. A model's changing difficulty with historical prose can mimic an inward turn. Report passage prevalence and conditional shares separately; a larger internal share can arise from fewer material obstacles.
- The general short-paper track fits better than Technical Track unless software sustainability/reuse is the principal claim. Do not spend the abstract narrating an agent architecture at the expense of literary interpretation.

These are project-specific recommendations inferred from the rubric and precedents below, not additional organizer rules.

## C. NAACL 2027 SRW: verified policy and exact excerpts

From **Welcome** and **Archival and Non-Archival Tracks**:

> “including high school, undergraduate, MSc/MA, and PhD students”
>
> “submissions marked as non-archival cannot be changed to archival after acceptance.”

Source: [SRW CFP](https://naacl27-srw.github.io/).

| Requested item | Verified rule / boundary |
|---|---|
| Topics | Broad NLP/CL, including text mining, stylistic analysis, resources, evaluation, and LLMs/agents. |
| Categories | Research papers may be completed or preliminary work. Thesis proposals are for PhD students; use research-paper category here. |
| Length/template | 8-page long or 4-page short content; unlimited references/appendices; accepted versions gain one content page. English PDF, official ACL templates. |
| Anonymity | Double-blind for both archival choices; remove identifying information and anonymize supplementary materials. |
| Eligibility | First author is a current student or did the work as a student. Coauthors need not be students. Submit status proof separately by January 11. |
| Archival choice | Archival accepted papers enter SRW proceedings. Non-archival work can go elsewhere later, except another SRW, subject to destination policies. |
| Dual submission | Disclose related/overlapping submissions and earlier non-archival versions. Archival submissions must satisfy ACL/NAACL/other-venue policies. Flexibility for non-archival submissions explicitly remains subject to final policy. |
| Route/review | Direct OpenReview submission; link forthcoming; no ARR commitment track currently planned. No detailed SRW scoring rubric published on checked pages. |

Sources: [SRW CFP, Author Guidelines, FAQs](https://naacl27-srw.github.io/); [detailed author policies](https://naacl27-srw.github.io/author-guidelines.html). Mentorship is optional, permits ideas without a full draft, and does not substitute for submission or guarantee acceptance.

**AI disclosure and research ethics.** SRW warns against undisclosed generated material, false citations, concealed authorship, and fabricated results; precise disclosure placement is deferred to final policy. Its detailed policies require documenting dataset sources, sampling, permissions, and relevant human-participant safeguards. They also say:

> “your paper must be self-contained: it is optional for reviewers to look at the supplementary material.”

Source: [SRW detailed author policies, Optional Supplementary Materials](https://naacl27-srw.github.io/author-guidelines.html).

**Limitations/Ethics distinction:** the checked SRW pages do not explicitly mandate a named Limitations section or exempt it from the content limit. **SRW-specific mandate/exemption: UNVERIFIED.** NAACL main-track rules adopt ARR's named Limitations requirement; ARR also requires a responsible-NLP checklist and AI-assistance disclosures. These are useful preparation guidance, not proof that every ARR administrative rule applies to direct SRW submissions. Include Limitations and Ethical Considerations; budget them inside 8 pages unless SRW confirms exclusions. [NAACL main CFP](https://2027.naacl.org/calls/main_conference_papers/), [ARR CFP, Limitations and assistance policy](https://aclrollingreview.org/cfp).

**Best title:** *What Stands in the Way: Validating LLM-Based Measurement of Plot Obstacles in English Fiction, 1800–1925*.

**Best argument:** the contribution is a validated, reusable method for measuring narrative impediments, with literary history as a substantive evaluation. H3 supplies an NLP motivation: lexical proxies may fail to identify narrative function. Keep the confounded-null benchmark as a bounded robustness component or cite the separate workshop paper; do not duplicate its contribution as the main SRW novelty.

**Reviewer expectations (inference):** task definition and annotation guidance; independent human validation; meaningful baselines; macro/per-class and period-stratified results; cost/accuracy tradeoffs for the cascade; reproducible prompts/data provenance; cautious downstream inference. The [ARR review form](https://aclrollingreview.org/reviewform) emphasizes soundness, support for claims, reproducibility, and resource utility, including impact on narrow communities. It is an adjacent expectation guide, **not a verified SRW review form**.

**Likely pitfalls:** LLM labels treated as ground truth; no held-out human sample; aggregate accuracy hiding rare intentional-withholding cases; tuning prompts against confirmatory outcomes; large numbers of correlated passages mistaken for independent novels; a familiar classifier applied without a new insight/resource; an eight-page paper trying to fully establish all five hypotheses plus a benchmark. Establish label validity first, then show what historical claims survive uncertainty.

## Cross-venue overlap and publication strategy

**Do not treat three titles as three distinct contributions.** Shared data can support distinct papers, but repeated primary claims/results require disclosure and may still be disallowed.

| Pair | What is established | Recommended action |
|---|---|---|
| AAAI + DH, both November | AAAI allows overlap only with other-venue permission; DH cross-venue rule not located. | Submit distinct benchmark and historical contributions. For meaningful overlap, obtain DH clarification before treating simultaneous review as allowed. |
| AAAI November → SRW January | AAAI notification December 2 and non-archival status make an earlier workshop version potentially compatible; this is not automatic permission. | Disclose/cite the workshop version and distinguish SRW contributions. Confirm final SRW policy if extending it substantially. |
| DH November → SRW January | DH decisions expected February, so review periods overlap. Book-of-Abstracts publication does not establish an abstract exception at SRW. | Request a policy ruling for the actual DH abstract/SRW paper overlap. If not allowed, choose a venue or withdraw the conflicting submission before proceeding. |

Policy sources: [AAAI workshop](https://eval-ai-scientists.github.io/aaai27/), [DH CFP](https://dh2027.adho.org/call-for-proposals/), [DH FAQ](https://dh2027.adho.org/dh-2027-faq/), [SRW originality policy](https://naacl27-srw.github.io/#author-guidelines). **The plan to submit all three is not yet policy-cleared.** Do not infer permission from silence, open review, publication length, or a non-archival option.

Proposed contribution boundary: AAAI owns **agent inference failures under controlled corpus construction**; DH owns **one literary-historical interpretation with textual evidence**; SRW owns **validated obstacle measurement and its reliability for historical analysis**. Share provenance and cite versions transparently. Do not promise that this boundary guarantees eligibility: organizers assess substantive overlap.

## Remaining policy questions

1. AAAI: do references fall outside the 2–4-page artifact limit, and what appendix/checklist rules apply? A four-page total PDF is the conservative fallback.
2. DH: does this particular extended abstract/full-SRW-paper pair satisfy originality and concurrent-review rules? Is there any additional registration rule for an under-18 presenter? Author eligibility is not the same as travel/bursary eligibility.
3. SRW: final disclosure/checklist requirements, named-section exclusions, exact overlap treatment for DH Book-of-Abstracts material, and the public non-archival AAAI version. Also recheck presentation/support instructions when announced.

These are clarification topics for later author action; no organizers were contacted during this research.

## Accepted-paper precedents

The evidence list below distinguishes exact requested tracks from adjacent venues. Similar accepted work illustrates plausible framing, not a reliable estimate of acceptance odds. Artifact availability and main-text length are marked unknown where only a landing page/abstract was verified.

## AI scientist evaluation: adjacent workshops, not a verified earlier edition of the target workshop

1. **Does Less Hallucination Mean Less Creativity? An Empirical Investigation in LLMs** — AAAI 2026 AI for Scientific Research (AI4Research), acceptance confirmed by [author paper record](https://arxiv.org/abs/2512.11509) and [official Outstanding Paper Award](https://ai4research-workshop.github.io/2026/#paper-awards). Compares three hallucination interventions across model families/scales and two creativity tasks. Fit lesson: isolate a measurable reliability tradeoff and include multiple interventions; scientific discovery motivates the evaluation without requiring a new scientist agent. Actual page length/code release **UNVERIFIED**. Adjacent precedent, not literary history or confounded nulls.
2. **ML-Bench: Evaluating Large Language Models and Agents for Machine Learning Tasks on Repository-Level Code** — ICLR 2025 Agentic AI for Science, oral, listed in [official accepted program](https://iclragenticai.github.io/#accepted_papers) and [author project page](https://zefan-cai.github.io/research/ml-bench/). Author page links workshop PDF, code, data and website; 9,641 annotated examples across 18 repositories. Fit lesson: distinguish executable agent performance from plausible generated text; document environment and feedback. Actual workshop length **UNVERIFIED**; current arXiv results may differ from workshop version. Adjacent benchmark, not false literary inference.
3. **Automatic Scientific Claims Verification with Pruned Evidence Graph** — ICLR 2025 Agentic AI for Science, poster, [official accepted list](https://iclragenticai.github.io/#accepted_papers), [workshop PDF](https://openreview.net/pdf/fdabb5a1deedbe653fef46e6f5a83bb52d396d5e.pdf). Fit lesson: claim verification itself is an accepted scientific-agent contribution. The PDF search extract confirms its workshop heading; full PDF access hit OpenReview browser verification, so actual length, experimental details and artifact release **UNVERIFIED**. Weakest methodological match of these three.

These workshops are related precedents, **not evidence that the specific AAAI-27 evaluation workshop has a prior edition**. No verified NeurIPS accepted-paper predecessor was established in this search; do not convert a NeurIPS CFP into an accepted-paper example.

## Digital Humanities

The [official DH2025 program](https://dh2025.adho.org/wp-content/uploads/2026/01/Digital-Humanities-Conference-2025-ConfTool-Pro-Printout.pdf) verifies the following four short-paper placements. SP means short-paper session; the two author institutions independently describe items 4 and 5 as short papers. Do not infer a page limit from a presentation slot.

4. **They crossed the valley of Catamarca: A study of narrative space in novel openings** — DH2025, SP-01; [official program](https://dh2025.adho.org/wp-content/uploads/2026/01/Digital-Humanities-Conference-2025-ConfTool-Pro-Printout.pdf), [data and code](https://zenodo.org/records/15858792), [research-team confirmation](https://www.canspin.uni-rostock.de/en/news/). Particularly close spatial/narrative operationalization. Fit lesson: bound the unit of analysis (openings) and show a concrete literary question with reusable data/code. Abstract length **UNVERIFIED**.
5. **Strictly Speaking: Character Attribution in Literary Dialogue with Language Models** — DH2025, SP-09; [official program](https://dh2025.adho.org/wp-content/uploads/2026/01/Digital-Humanities-Conference-2025-ConfTool-Pro-Printout.pdf), [institutional announcement explicitly identifying short paper](https://ischool.illinois.edu/news-events/news/2025/07/ischool-present-research-digital-humanities-2025-conference). Fit lesson (title-level inference): language-model annotation of literary discourse fits when attached to a recognizable textual task. Exact length, performance and public artifacts **UNVERIFIED**.
6. **Investigating Conceptual Plasticity: On Detecting a Re-Conceptualization of Focalization with Large Language Models** — DH2025, SP-33; [official program](https://dh2025.adho.org/wp-content/uploads/2026/01/Digital-Humanities-Conference-2025-ConfTool-Pro-Printout.pdf), [ADHO conference-paper record/PDF](https://zenodo.org/records/16994537). Fit lesson (title-level inference): make the stability and operationalization of a narratological concept the methodological question; this is close to “what counts as an obstacle?” The record supplies a public abstract PDF. Length and separate code/data release **UNVERIFIED**.
7. **Automated Extraction of Character Features in Fiction: Comparing Bert-based Models and Large Language Models on Fanfiction in English and Chinese** — DH2025, SP-33; [official program](https://dh2025.adho.org/wp-content/uploads/2026/01/Digital-Humanities-Conference-2025-ConfTool-Pro-Printout.pdf). Fit lesson (title-level inference): a comparison between annotation methods, tied to literary features and language/domain variation, is viable short-paper framing. Exact length, results and artifacts **UNVERIFIED**.
8. **A Computational Exploration of the Narrative Functions of Poetry in Chinese Qing Vernacular Fiction (1644-1911)** — DH2024, accepted paper in the [conference-linked abstract application](https://dh24-abstracts.netlify.app/assets/ma_rongqian_a_computational_exploration_of_the_narrative_fun); [official program page linking that application](https://dh2024.adho.org/index.html%3Fp%3D102.html). **Short-paper track UNVERIFIED**; accepted conference-paper status verified. Exceptionally close: literary function labels rather than mentions; 360 poems/18 novels; LLM extraction and five narrative categories; model evaluation and confusion matrices. Fit lesson: modest pilot with explicit failure analysis can contribute to DH. The abstract identifies inadequate context and a single annotator as limitations. Public annotated-data/code release and exact abstract length **UNVERIFIED**.

9. **A Meta-Benchmark on Plot Annotation of Literary and Historiographical Texts with Large Language Models** — Florentina Armaselu, DH2026, **verified short paper**. The [official ADHO Book of Abstracts](https://zenodo.org/records/22638575) supplies [TEI XML](https://zenodo.org/api/records/22638575/files/DH2026_BookOfAbstracts_v2.xml/content): locate `ARMASELU_Florentina_A_Meta_Benchmark_on_Plot_Annotation_of_L.xml`; its ConfTool subcategory is Short Paper. The study compares annotation, model evaluation, and rebuttal using literary/historiographical texts, including Gutenberg short stories, with a human meta-evaluator. Its appendices provide prompts and assessment material; separate runnable code/data release and exact abstract length **UNVERIFIED**. Fit lesson: narrative annotation can be framed as an evaluation problem with interpretive uncertainty, multiple judges, and transparent protocols. This is the closest bridge between our benchmark and humanities components. Its Freytag-stage task differs from obstacle function; explain that distinction rather than claiming plot annotation itself is new.

## Genuine SRW computational humanities papers

10. **Towards Layered Events and Schema Representations in Long Documents** — NAACL 2021 SRW, pp. 32–39 (8 pages); [official Anthology record and PDF](https://aclanthology.org/2021.naacl-srw.5/). Thesis proposal about literary event extraction and schemas at multiple granularities. Fit lesson: narrative structure can be the NLP research problem, and a defensible representation matters beyond surface counting. Not evidence for current thesis-track or high-school eligibility. Code/data release **UNVERIFIED**.
11. **Fact from Fiction: Finding Serialized Novels in Newspapers** — ACL 2025 SRW, pp. 695–707 (13 pages); [official record/PDF](https://aclanthology.org/2025.acl-srw.45/). Nineteenth-century Danish corpus, 1,394 manually labeled articles, feature/embedding classification and interpretable analysis. Closest SRW model for this project: historical corpus + validated annotation + substantive discourse question. Fit lesson: show the new dataset/task and measurement evidence before the cultural claim. Public data/code release **UNVERIFIED** from record alone.
12. **Dr. Livingstone, I presume? Polishing of foreign character identification in literary texts** — NAACL 2022 SRW, pp. 123–128 (6 pages); [official record/PDF](https://aclanthology.org/2022.naacl-srw.16/). Compares methods for aligning character-name forms in translated English–Finnish literature. Fit lesson: a simple, resource-light baseline may be the strongest result; expensive LLMs require comparison with simpler methods. Public artifacts **UNVERIFIED**.
13. **Authorship Attribution of Late 19th Century Novels using GAN-BERT** — ACL 2023 SRW, pp. 310–320 (11 pages); [official record/PDF](https://aclanthology.org/2023.acl-srw.44/). Collated English novel dataset, imbalance/sampling experiments and historical authorship motivation. Fit lesson: period-specific humanities data can support an SRW contribution when coupled with explicit modeling and evaluation. Adjacent classification task, not narrative function. Public release **UNVERIFIED**.
14. **Forged-GAN-BERT: Authorship Attribution for LLM-Generated Forged Novels** — EACL 2024 SRW, pp. 325–337 (13 pages); [official record/PDF](https://aclanthology.org/2024.eacl-srw.26/). Evaluates literary text authenticity using generated negatives, model comparisons and alternative prompting. Fit lesson: controlled synthetic literary material can create an evaluation task, but its validity must be tested. It evaluates forgery, not scientific overclaiming; no evidence that its generated text is an appropriate historical null. Public artifacts **UNVERIFIED**.
15. **Cross-Genre Learning for Old English Poetry POS Tagging** — ACL 2025 SRW, pp. 708–724 (17 pages); [official record/PDF](https://aclanthology.org/2025.acl-srw.46/). Two annotated corpora, two tag sets and cross-genre experiments; adding source-genre data is not uniformly helpful. Fit lesson: make genre/period transfer a measured source of annotation error. Adjacent historical NLP, not a literary-historical finding. Public artifacts **UNVERIFIED** from record alone.

## Practical synthesis (recommendation, not CFP policy)

- AAAI benchmark: emulate ML-Bench's executable checks and the hallucination paper's controlled interventions. Null generation, known ground truth, claim scoring, repeated runs and costs should be the contribution. Literary history supplies a demanding testbed.
- DH: emulate the narrative-function pilot and Catamarca's bounded spatial question. One interpretable finding plus closely read examples and measurement validation will be stronger than all hypotheses compressed together.
- SRW: emulate Fact from Fiction's sequence: corpus problem → gold annotation → model/baseline evaluation → historical analysis. Add genre/time-slice error analysis, as the cross-genre precedent warns against assuming stable annotation quality.
- Acceptance precedents establish topical plausibility, not guaranteed acceptance, identical formats, review criteria, eligibility or permission for duplicate submissions.
