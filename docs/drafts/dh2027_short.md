# Two Fictions: What Stands in the Way in English Novels, 1800–1929

*DH2027 short paper, DRAFT 0.1 (2026-11-04). Body ≈ 1,240 words, excluding title, notes and references. Exploratory numbers come from `docs/pilot_analysis_2_two_fictions.md`. Placeholders marked ⟦…⟧ are filled after the Confirmation unseal (Nov 9–11).*

---

## The question

Every English class teaches that stories run on conflict: a character against nature, against society, against self. The triad is a schoolroom simplification. It is cruder than Greimas's opponent or Ryan's conflicting possible worlds. But it asks a real question: when a character wants something, *what stands in the way?* Consider two passages from Project Gutenberg:

> "You are not my son's equal in refinement or education." (Charlotte M. Brame, *Dora Thorne*, 1884)

> "he was carried off by the torrent" (Edward Stratemeyer, *The Rover Boys on a Tour*, 1916)

In the first, the obstacle is a person enforcing a social rule. In the second, it is a river.

In "Modern Fiction" (1919), Virginia Woolf called the leading novelists of her day "materialists", concerned "not with the spirit but with the body." Critics have since spoken of an "inward turn" in the novel. Both claims are about *the novel*. But which novels? The fiction that survives on syllabi and the fiction people actually read may be different worlds of trouble.

We test a claim we call **two fictions**: canonical and non-canonical novels differ in where their obstacles come from. The archive itself is part of the object here, not a nuisance to control away (Bode 2018; Moretti 2000). Project Gutenberg preserves the canon of the 1820s and the mass market of the 1900s. Any trend through time is therefore partly a change in *which* fiction survives.

## Method

**Corpus.** The corpus is 15,511 English-language works of fiction dated 1800–1929 from Project Gutenberg, about 1.1 billion words. Duplicates and non-fiction were removed, and genres were assigned from Library of Congress subject headings.
- Authors are clustered by Gutenberg agent ID. Pseudonyms are merged, including the Stratemeyer Syndicate's house names.
- Every work catalogued before 1854 had its first-edition date checked against bibliographies. Of the 566 dates we could resolve, 41% of catalog years were wrong, and 23% were off by more than five years.
- Unresolvable dates, works outside the window, translations, placeholder "1900" dates and historical novels are excluded from the primary population. So are works beyond five per author per decade, which keeps prolific writers from dominating.

**Canonicity** is fixed in advance from metadata only. A work counts as canonical if its author's Wikidata entry has articles in at least 30 Wikipedia languages. By that measure, 30–37% of the primary works from 1800–1849 are canonical, and 9% of those from 1885–1929.

**Labels.** We sample random 350-word passages. A 12-billion-parameter open model, running on volunteers' computers, reads each passage and records:
- whether it contains an obstacle to a character's goal;
- the obstacle's *locus*: material (the world, the body), social (people, rules, institutions) or internal (the character's own mind);
- an exact supporting quotation from the passage.

We check each quotation against the source text, and every example in this paper was re-verified that way.

**Humans and the seal.** Model labels are not ground truth. We split the corpus by author into two halves.
- **Discovery** is open. It is where we found the two-fictions pattern.
- **Confirmation** labels are encrypted to an offline key, and nobody has read them.

Before unsealing, we pre-registered one primary test (OSF ⟦hash⟧):
- the estimand is the canonical minus non-canonical difference in material and internal shares;
- the test is a two-sided Wald test with author-clustered errors.

Human labels come from a stratified audit of about 1,820 Confirmation passages, drawn from metadata alone. Student annotators label all of them. A graduate-student expert, blind to the hypotheses, labels a nested half of about 900. Design-based supervised learning then corrects the model's errors toward the expert's judgement (Egami et al. 2023).

## Exploratory results (Discovery half; raw model labels; not yet corrected by humans)

We analysed 46,684 passages from 4,240 works. Seventy-two percent of passages contain an obstacle, and the rate is the same for canonical and non-canonical works (71% vs 72%). **The two fictions are equally full of trouble. They differ in what kind.**

Canonical works give a smaller share of their obstacles to the material world and a larger share to the mind:
- **Material share:** 0.165 vs 0.212 overall. Weighting the era gaps equally by works, the gap is **−3.9 percentage points** (95% author-cluster bootstrap CI −6.9 to −0.8).
- **Internal share:** 0.157 vs 0.118, a gap of **+3.6 points** (+0.9 to +6.4).
- **Social share:** about two-thirds of obstacles in both groups.

The gap is largest at mid-century. For 1850–84 it is −9.7 points of material share. A Trollope heroine's obstacle is often herself: "And who had closed the gates? Her own hands had done it" (*Rachel Ray*, 1863). After 1885 the gap shrinks to −3.1 points.

The aggregate trend through time is small. From 1850–84 to 1885–1929, the material share rises by 0.9 points (CI includes zero). Of that rise, 0.7 points come from the canonical share of the archive halving (19% to 9%). Within each group, we detect no change.

So the "outward turn" a naive reading of the archive suggests is mostly a change in *which* novels survive.

Three findings temper this.
1. **After 1885, the gap is a children's-book gap.** Remove works catalogued as juvenile and the late material shares are identical (0.172 vs 0.173). Boys' adventure is where rivers and storms stand in the way.
2. **A second model does not reproduce the gap.** On a 3,459-passage overlap, a different open model (Qwen) finds no canonical material gap. But it also calls 60% fewer passages obstacles, so the two models disagree about the construct itself.
3. **"Canonical" here means famous today.** That includes Conan Doyle, Haggard and Edgar Wallace alongside Henry James.

## Confirmatory result (to be filled after the unseal)

⟦On the sealed half (N = 4,048 works; E 87, M 538, L 3,423), the expert-corrected canonical − non-canonical difference is Δ_material = ⟦…⟧ (95% CI ⟦…⟧) and Δ_internal = ⟦…⟧ (⟦…⟧), Wald p = ⟦…⟧. Verdict under the registered rule: ⟦supported: class / unstable / null (MDE ≈ 9 points)⟧. Peer–expert κ = ⟦…⟧; model–expert κ by era = ⟦…⟧.⟧

We report the result whatever it is. Our exploratory gap (about 4 points) is below the registered design's minimum detectable effect (about 9 points), so a null result is a live possibility. A null would mean that, measured this way, the canon and the mass market differ less in their *kinds* of trouble than the literary-historical story assumes.

## Limitations

- **Construct.** The locus triad is a teaching device. The model's locus closely follows the obstacle's domain, and boundary cases are hard. Is fatigue body or mind? Is an assault on a mountain path material or social?
- **Canonicity.** Present-day Wikipedia fame is a weak proxy for historical prestige.
- **Archive.** Gutenberg reflects volunteers' tastes. Our "mass market" is the part of it someone chose to digitize.
- **Evidence status.** The exploratory numbers are raw model labels. Early dates were checked by an AI agent against cited bibliographies and still await a human sign-off.
- **Our own position.** The first author, a high-school student, designed the study and annotates. The expert who anchors the estimate does not know the hypotheses.

## Why it matters for teaching

The schoolroom triad becomes something students can count, argue about and check. Every number here traces back to passages a reader can open. Whether or not the sealed test confirms the pattern, the exercise shows how much a literary-historical "trend" can depend on which books survive.

---

### References (short form)
Bode, K. (2018). *A World of Fiction*. Bourdieu, P. (1992/1996). *The Rules of Art*. Egami, N., et al. (2023). Using imperfect surrogates for downstream inference (DSL). *NeurIPS*. Greimas, A. J. (1966). *Sémantique structurale*. Kahler, E. (1970/1973). *The Inward Turn of Narrative*. Moretti, F. (2000). The slaughterhouse of literature. *MLQ* 61(1). Ryan, M.-L. (1991). *Possible Worlds, Artificial Intelligence, and Narrative Theory*. Underwood, T., & Sellers, J. (2016). The longue durée of literary prestige. *MLQ* 77(3). Woolf, V. (1919/1925). Modern Fiction. In *The Common Reader*.

### Notes for co-authors (delete before submission)
- Check the Woolf wording against the 1925 *Common Reader* text. The draft quotes "materialists" and "not with the spirit but with the body" from memory.
- Figure: `analysis/figs/tf_pilot.png`. The CfP decides whether a short paper may carry one figure.
- If TF is null, retitle around the composition finding: "Which fiction? The archive behind an outward turn".
