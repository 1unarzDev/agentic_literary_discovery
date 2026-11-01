# Submission checklists

Checked **2026-10-31**. `[Rule]` denotes a verified instruction from the linked venue; `[Advice]` a recommendation; `[UNVERIFIED]` an unresolved requirement. See [fit_report.md](fit_report.md) for policy excerpts, fit, and overlap analysis. Recheck live CFPs before submission.

## Deadlines: do not use one November 20 cutoff

| Action | Venue deadline | UTC equivalent | America/Chicago |
|---|---|---|---|
| SRW mentorship | Nov 16, 2026, 23:59 AoE | Nov 17, 11:59 | Nov 17, 05:59 CST |
| AAAI submission | Nov 20, 2026, 06:00 UTC | Nov 20, 06:00 | Nov 20, 00:00 CST |
| DH short submission | Nov 20, 2026, 23:59 AoE | Nov 21, 11:59 | Nov 21, 05:59 CST |
| SRW paper + status proof | Jan 11, 2027, 23:59 AoE | Jan 12, 11:59 | Jan 12, 05:59 CST |

Sources: [AAAI dates](https://eval-ai-scientists.github.io/aaai27/#dates), [DH dates](https://dh2027.adho.org/call-for-proposals/), [SRW dates](https://naacl27-srw.github.io/#dates). Times converted from the stated UTC/AoE rules; **AAAI closes almost 30 hours before DH**. Submit early; midnight Chicago is the start of November 20.

## AAAI: benchmark resource/artifact

- [ ] [Rule] Select the correct paper category. Resource/artifact requires the artifact with the submission; position is an alternative for an emerging argument. Full research is 6–8 pages, not the planned short format. [CFP](https://eval-ai-scientists.github.io/aaai27/#submissions).
- [ ] [Rule] Use the [AAAI-27 author kit ZIP](https://aaai.org/authorkit27/), official two-column format, anonymous PDF, [OpenReview workshop portal](https://openreview.net/group?id=AAAI.org/2027/Workshop/EvalAIScientists).
- [ ] [Rule] Keep resource/artifact text within 2–4 pages. [UNVERIFIED] Short-track reference/appendix exclusions; stay within four total pages unless clarified. Kit contents were not retrieved, so inspect them before drafting.
- [ ] [Rule] Compare systems at matched compute/token budget or explain why infeasible. [Advice] Report actual usage, reruns, seeds, and failures as well as caps.
- [ ] [Rule] Supply an executable, documented artifact. [Advice] Anonymous README, dependency versions, one-command small run, null generator, planted effects, scoring rubric, example traces, and key-free replay of saved outputs.
- [ ] [Advice] Main sections: Abstract; Evaluation Problem; Controlled Corpus Construction; Agents and Scoring; Results; Limitations and Release. Include an AI-use disclosure under the [AAAI AI-systems policy](https://aaai.org/aaai-publications/aaai-publication-policies-guidelines/).
- [ ] [UNVERIFIED] No named Limitations/Ethics section or workshop-specific reproducibility checklist was found in the CFP. Do not automatically import main technical-track submission rules.
- [ ] [Advice] Make ground truth claim-specific: shuffled time, confounded association, and planted causal/associational signal are different conditions. Report false attribution and detection power separately.
- [ ] [Rule] Anonymize PDF metadata, supplement, repository ownership, logs, and self-citations as needed for double-blind review. [Advice] Preserve a private author version and a separate anonymous artifact.
- [ ] [Rule] Check the other venue's permission before overlapping submission. Non-archival is not unilateral authorization.
- [ ] [Rule] Arrange one registered in-person presenter for February 22, 2027. Budget this before choosing the venue; another coauthor may present. Camera-ready January 15; acceptance December 2. [Workshop](https://eval-ai-scientists.github.io/aaai27/).

**Recommended four-page plan (advice):** 0.5 problem/contribution; 1 null construction and claim rubric; 0.75 agent protocol/budget; 1 results and validity checks; 0.75 limitations, artifact, and references. Adjust only after confirming reference exclusions. If no measured results exist, frame a position paper honestly and remove empirical claims from the title/abstract.

## DH2027: literary interpretation, short paper

- [ ] [Rule] Submit through [ConfTool](https://www.conftool.pro/dh2027/). Select short paper; normal track unless technical infrastructure is the actual contribution. [CFP](https://dh2027.adho.org/call-for-proposals/).
- [ ] [Rule] English PDF, **1,000–1,250 words**. Captions included; table contents/references/disclosure excluded. Extra tables/figures permitted in appendix. No page limit found.
- [ ] [Rule] Include author identities: review is open in both directions. [Advice] Maintain a separate file from anonymous AAAI/SRW drafts.
- [ ] [Rule] Include literature review, citations, and reference list. Use a consistent style; no prescribed reference style. [FAQ](https://dh2027.adho.org/dh-2027-faq/).
- [ ] [Rule] Disclose GenAI use for **research and submission preparation**, including cascade labels and assistance used to develop the paper. [Advice] State models/versions, roles, checks, and human responsibility. Do not describe LLM annotations as human annotations.
- [ ] [Advice] Include question + literary stakes; obstacle definition; sampling and human validation; one main analysis; concrete passage contrasts; interpretation and limits. No named Limitations/Ethics heading is required by the checked CFP/FAQ.
- [ ] [Advice] Use one figure connecting obstacle prevalence/locus to time with uncertainty, plus a keyword-versus-function contrast if space permits. Clearly label preliminary versus completed evidence.
- [ ] [Advice] Address rubric: scholarship, advance, method/rationale, diversity, clarity. The posted percentages sum to 90%; no missing score should be invented.
- [ ] [Advice] Bound the claim to sampled UK/US Gutenberg novels and passage context. Separate historical associations from causal claims about railways, postal infrastructure, or electrification.
- [ ] [UNVERIFIED] Obtain a ruling on substantial overlap with SRW, whose submission occurs before DH decisions. The Book of Abstracts is a publication; it is not explicitly declared non-archival.
- [ ] [Rule] Prepare for a typical 10-minute presentation. [Advice] Check partly hybrid arrangements and any age-specific registration details when available. Publication is the short abstract, not an invitation to supply a later full proceedings paper. [FAQ](https://dh2027.adho.org/dh-2027-faq/).

**Suggested 1,200-word allocation (advice):** 180 literary question/prior work; 240 concepts/corpus; 220 annotation and validation; 280 findings and captions; 180 interpretation; 100 limitations. References and AI disclosure separately. A null or mixed finding can be informative; do not force every confirmatory hypothesis into the abstract.

## NAACL 2027 SRW: full measurement study

- [ ] [Rule] Request optional mentorship via [SRW's mentee link](https://naacl27-srw.github.io/#mentoring) by November 16. A complete paper is unnecessary. Matching November 23; mentorship is not anonymous or a submission decision.
- [ ] [Rule] Choose **research paper**; PhD thesis proposal is inappropriate for the high-school author. High-school students are explicitly welcomed. [SRW](https://naacl27-srw.github.io/).
- [ ] [Rule] Prepare first-author student ID, enrollment certificate, transcript, or other accepted proof. Upload separately by January 11; never embed proof in the anonymous paper/supplement. Non-student coauthors are permitted.
- [ ] [Rule] Use [ACL templates](https://github.com/acl-org/acl-style-files) and [formatting guidance](https://acl-org.github.io/ACLPUB/formatting.html). English PDF; long 8 or short 4 content pages; references/appendices unlimited. Long camera-ready up to 9; short up to 5. Recommended here: long.
- [ ] [Rule] Submit directly to SRW OpenReview by January 11; portal forthcoming as of this check. Do not substitute an ARR submission/commitment. [SRW submission route](https://naacl27-srw.github.io/#cfp).
- [ ] [Rule] Choose archival/non-archival at submission. Non-archival cannot become archival after acceptance and cannot later be reused at another SRW. [Advice] Prefer archival if this is the intended full publication and overlap is cleared; otherwise assess future publication plans first.
- [ ] [Rule] Disclose overlapping work and prior non-archival versions in the form. [UNVERIFIED] Resolve the exact DH/AAAI overlap under final SRW rules; do not assume non-archival removes all restrictions.
- [ ] [Rule] Double-blind paper and supplement, with third-person self-citation and no acknowledgments or identifying status proof. [Advice] Use review mode with line numbers and scrub PDF metadata.
- [ ] [Advice] Main sections: Introduction; Related Work; Obstacle Definition and Annotation; Corpus/Sampling; Models and Cascade; Validation; Historical Analysis; Discussion/Conclusion; Limitations; Ethical Considerations; References; Appendices.
- [ ] [UNVERIFIED] SRW does not explicitly adopt all ARR section/checklist rules. Include Limitations and Ethical Considerations, conservatively inside 8 pages, until exemption confirmed. Prepare responsible-NLP answers and AI-use disclosure for the eventual submission form. [SRW policies](https://naacl27-srw.github.io/author-guidelines.html), [ARR guidance](https://aclrollingreview.org/cfp).
- [ ] [Rule] Document data origins, sampling, permissions, and applicable human-participant safeguards. Supplement is optional for reviewers: main evidence must be self-contained. [Detailed SRW policies](https://naacl27-srw.github.io/author-guidelines.html).
- [ ] [Advice] Include human-held-out validation by period/domain/locus, disagreement analysis, keyword baseline, direct-model baseline, cascade cost/quality, and uncertainty for downstream trends. Keep prompt tuning separate from confirmatory evaluation.
- [ ] [Advice] Release annotation manual, IDs/offsets, metadata decisions, deduplication rules, prompts, model dates, code, and permissible data. Do not assume US public-domain status proves unrestricted global redistribution.
- [ ] [Advice] Budget around **2 pages** question/related work, **2** task/data, **2** validation, **1** historical analysis, **1** discussion/limits/ethics. Put prompts and secondary analyses after references; do not hide core validation there.
- [ ] [Rule] Recheck final policies, presentation arrangements, and support. Current SRW dates: notification March 8, camera-ready March 15; conference June 1–5, exact SRW date TBD. Remote options/support are not yet promised. [SRW dates and FAQ](https://naacl27-srw.github.io/).

## Final research-integrity pass (advice for all three)

- [ ] Every result corresponds to a completed run; every citation exists and supports its sentence.
- [ ] Confirmatory tests are distinguished from exploratory analyses; no post-result hypothesis selection is described as preregistered.
- [ ] Denominators are explicit: per passage, per novel, per obstacle, or conditional locus share. Uncertainty respects repeated authors/books and annotation error.
- [ ] Shared contributions, data, and prior versions are declared consistently across papers. No overlapping submission is treated as approved merely because it has a different title.
- [ ] Final filenames, author identities, metadata, and repository links match the venue's review model.
