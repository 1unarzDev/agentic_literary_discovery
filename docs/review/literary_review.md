# Peer review: the humanistic case for "What Stands in the Way" (2026-11-01)

**Reviewer stance.** I review as a literary historian of the nineteenth- and early-twentieth-century Anglo-American
novel. I care about narratology and the distant-reading debates (Moretti, Underwood, Piper). I am not reviewing the
statistics or the pipeline.

**What I read.** I read the decision memo, plan §1–3, codebook v0.9, the novelty matrix, critic theses, the novelty
sweep, pilot analysis 1, QA pass 2, the exemplar candidates, the annotator guide and the showcase page.

**What I checked in the data.** I looked at the v0.9 labels (pin `41ca3c7d`: 8,706 random-backbone Discovery passages,
6,290 of them obstacles), joined to text and works metadata. I read 44 passages in full: 16 from 1800–49, 14 from
1850–84 and 14 from 1885–1929, drawn with seed 11. I also ran a few cross-tabs. All of those numbers are **raw model
labels**, and nobody should cite them as results. I use them only to show where the framing is exposed.

**Bottom line.** The project has a real, teachable idea: read for *function*, not for words. It also has an
unusually honest validation culture. But as framed, it is set up to produce a finding about **Project Gutenberg's
shelves** rather than about the novel. The construct is closer to the schoolroom "types of conflict" than to any
narratology. And the headline hypothesis (Kahler, an inward turn of obstacles) is tested in the one place it is least
likely to show up. These problems can all be fixed. Several of the fixes are more interesting than the original plan.

---

## 1. Ranked problems

### P1 (critical): the "outward" pattern looks like a canon-to-series-fiction composition artifact, not a historical change

**Evidence.** I flagged a crude "canonical author" set: about 30 names, including Scott, Austen, Thackeray, Trollope,
Gaskell, the Brontës, Eliot, Collins, Oliphant, Yonge, Hardy, James, Stevenson, Gissing and Wharton. These are raw v0.9
labels.

| Era | Canonical share of obstacle passages | Material share, canonical | Material share, everyone else |
|---|---|---|---|
| 1800–49 | 31% (55) | 0.06 | 0.21 |
| 1850–84 | 22% (181) | 0.09 | 0.22 |
| 1885–1929 | **3.8%** (201 of 5,290) | 0.08 | 0.22 |

- Inside each group the material share is **flat**.
- The aggregate rise (0.16 → 0.19 → 0.21) is reproduced almost exactly by the collapse of the canonical share. For
  1800–49: 0.31 × 0.06 + 0.69 × 0.21 ≈ 0.16.
- The same holds after dropping LCSH-juvenile and adventure: canonical 0.06 / 0.08 / 0.07, others 0.20 / 0.17 / 0.15.
  The others actually *fall*.
- The most-sampled authors overall are Fenn, "Laura Lee Hope" (the Stratemeyer Syndicate's Bobbsey Twins), Alger,
  Henty, Ballantyne, Stratemeyer, Le Queux and Oppenheim.

The 8-class LCSH genre variable cannot see this, which is why pilot analysis 1 found a +0.3 pp composition term.
Cataloguers tag *Tom Swift* as juvenile, but they do not tag Le Queux, Oppenheim, Bindloss or Fenn's adult serials as
anything. Gutenberg preserves the **canon** of the 1820s and the **mass market** of the 1900s, because volunteers
digitize what they loved as children and what they were assigned. The pilot's "outward turn" therefore compares Scott
with the Stratemeyer Syndicate. Moretti's "slaughterhouse of literature" runs in reverse here: in the early decades the
archive *is* the survivors.

**Fix.**
1. Add a work-level **prestige/canonicity covariate** before the confirmatory freeze. Options:
   - Wikidata sitelink count, or presence in the ODNB/ANB;
   - inclusion in a reviewed-in-periodicals sample, after Underwood & Sellers's prestige work;
   - presence in the Chicago Novel Corpus;
   - a name-cloze memorization score, which the plan already wants.
2. Report every locus trend **within prestige strata**, and add a shift-share term for it.
3. Treat my author list as a smoke test, not a variable. It is ad hoc, and the canonical late-era n is only 201.

If the pattern survives a proper covariate, it becomes a far stronger finding. If it does not, the composition finding
*is* the paper (see R1).

### P2 (high): the construct is the schoolroom "conflict" triad, operating at the wrong scale for "plot"

**Evidence.**
- The locus triad (material / social / internal) is, in all but name, the English-class taxonomy of *man vs nature /
  man vs society / man vs self*. That is a strength for teachers, who will recognize it at once, but it is not a
  narratological construct, and reviewers in narrative theory will say so.
- The narratological concepts the project gestures at all live at the level of the **story**:
  - Greimas's *opponent* is an actantial role defined against a subject–object axis across the whole narrative.
  - Propp's functions (lack, villainy, struggle, difficult task) are positions in a sequence.
  - Bremond's "possibilities" of degradation and improvement are branching points in a process.
  - Ryan's conflict model is a clash between characters' private worlds.
- The project codes **random 350-word windows**, so the construct it measures is *local resistance*. 72% of windows
  qualify, in every era (0.70 / 0.72 / 0.72). A cat under a kitchen table (*Bobbsey Twins at the County Fair*, 1922),
  bone dust making Ahab's carpenter sneeze (*Moby-Dick*, labelled ILLNESS + night "intimacy"), "I am engaged to Lady
  Glenmore" (*The Exclusives*, 1830), and a "rugged road" followed for six miles (*The Rival Trappers*) all count the
  same as Lady Earle telling Dora Thorne "You are not my son's equal".
- At that density the label is closer to Baroni's *tellability* or to suspense than to "what stands in the way" of a
  plot.

**Fix.** Do not rebuild the taxonomy. The codebook is frozen and the human gold is in flight. Three changes are enough:
1. **Rename and theorize the unit.** Call it "scene-level obstacle" or "local impediment". Add one paragraph placing it
   against Greimas, Propp, Bremond and Ryan, and say plainly that the triad is the pedagogical conflict typology made
   operational. That is a selling point for the teacher audience.
2. **Add a salience flag** in the cheap second pass described under R2: "would a one-paragraph plot summary of this
   chapter mention this obstacle?" Report every trend for salient obstacles only, as a sensitivity.
3. **Stop calling it "plot"** in claims unless the obstacle recurs across passages of the same work. Work-level
   aggregation, such as the dominant locus per work, is closer to what critics mean.

### P3 (high): the H1 test of the "inward turn" is close to a strawman, and the instrument undercounts inwardness

**Evidence, on the theory side.**
- Kahler's argument ends around 1800. The memo admits this.
- Woolf's "Modern Fiction" (1919/1925) does not predict that the *average* novel turns inward. It complains that
  Wells, Bennett and Galsworthy are **"materialists"**. A materialist Edwardian mainstream is exactly what the late PG
  corpus (Le Queux, Oppenheim, Henty, Stratemeyer) should look like *if Woolf is right*.
- The modernist inward turn (Richardson, Joyce, Woolf, Sinclair) falls after 1915, where the US public-domain cut-off
  thins PG to almost nothing.
- Critics locate the inward turn in **representation**: free indirect discourse, Cohn's *Transparent Minds*, psycho-
  narration. They do not locate it in obstacle *location*. A Jamesian obstacle is usually a misreading of other minds
  (Strether), which this codebook calls social or COMMUNICATION.

**Evidence, on the instrument side.** The codebook makes internal obstacles hard to see.
- **Personification is read literally.** *Rebecca Mary* (1920): "But Duty barred her way, grim and stern" is coded
  INTERPERSONAL, social.
- **Guilt is coded as its occasion.** *Idolatry* (1874): "every honest motive forbade it" is coded as "murder of her
  protector", social.
- **Psychology is coded as institution.** In Galsworthy's *Tatterdemalion* (1920), a fisherman's claustrophobic
  homesickness is coded SOCIAL_RANK ("the French system would not send a man to convalescence for … home-sickness").
- **Deliberation that ends in a decision is excluded.** In Benson's *Oddsfish!* (1914), a conscience forbids spying for
  advancement, and the label is "no". The "goal achieved, no impediment left" exclusion removes the classic shape of an
  inner struggle, which is overcome within the scene.
- **Fear of a person goes to social.** 752 obstacle rows have pride, fear, guilt, doubt, duty or hesitation in
  `locus_reason` or `obstacle_summary`, and **420 of them are coded social**. The proximate-source rule sends "fear of
  X" to whoever X is. That is defensible, but it means "internal" measures only self-generated resistance, a narrow
  slice of what critics call interiority.
- **Even the friendliest genres show nothing.** In domestic/realist and romance, internal is 0.20 / 0.18 / 0.17 across
  eras.

**Fix.**
1. Reframe H1 as a test of the **popular** novel against the critical story. Do not claim to test Kahler or Woolf.
   - Make Woolf's "materialists" the named foil, with an explicit prediction that the mainstream stays material and
     social.
   - Report the inward-turn literature's actual object, interiority *representation*, as context, citing Radak et al.'s
     null.
2. Before the human gold freezes, add two **annotator-guide** notes that do not need a new model pin:
   - personified virtues and passions ("Duty", "Pride") are internal;
   - a struggle resolved inside the passage still counts if the passage dramatizes the resistance.
   Measure model-versus-human disagreement on exactly these cases. DSL will then correct toward the human construct.
3. Keep the 2-df two-sided test the pilot recommends.

### P4 (high): `resolution_hint` is dead in v0.9, which blocks the most promising redirection

**Evidence.**
- Under pin `41ca3c7d`, `resolution_hint` = "unknown" in **6,290 of 6,290** obstacle rows. The v0.9 codebook text
  says only "resolution_hint: only if the passage shows it, else unknown". It never lists the categories (by person,
  by chance, by technology, unresolved), so the model never uses them.
- Under v0.5 (pin `2c86999f`), the counts were 1,312 unresolved, 175 by person, 32 by chance and 5 by technology.
- A 350-word random window rarely contains the resolution anyway. In *Guy Mannering* (Scott, 1815), the passage where
  creditors "recognise Bertram's right" closes the novel's inheritance plot, and the codebook correctly says "no".

**Fix.** Do not expect resolution data from the backbone. Any resolution study needs a targeted forward-reading pass
(see R3). Either restore the enum definitions in the codebook text at the v1.0 freeze or delete the field, so the
paper does not report a field that was never really measured.

### P5 (medium-high): the taxonomy hides the obstacles Victorianists care most about

**Evidence.** The ten domains are organized by *substance* (distance, darkness, money), not by the **plot types** that
organize nineteenth-century fiction.
- **Marriage and courtship plots** are split between RANK and INTERPERSONAL. The codebook's rule ("a particular
  person's wishes are INTERPERSONAL, a rule that would stop anyone is RANK") is unstable at precisely the point that
  matters. Lady Earle *is* the class rule speaking. The model codes *The Fair Maid of Perth*'s father's veto as RANK,
  against its own codebook.
- **Inheritance, wills and entail** share MONEY_PROPERTY_LAW with ten-cent poverty and police arrests. *The Secret
  Dispatch*'s forged death-bed will is a prototype, but it cannot be counted separately.
- **Religion and conscience** (the crisis of faith, Dissent, Catholic disabilities such as Diana Vernon's "nets and
  toils" in *Rob Roy*) have no home. About 8% of summaries touch them.
- **Empire and race** have no home either. African and Native American figures are coded INTERPERSONAL (*Jasper Lyle*'s
  "wizard"), and enslaved flight is coded INTERPERSONAL. That is a choice the paper must own, and probably interrogate.
- **Time and deadline** (the race against the clock, the will that must be found before the reading) has no home.
- **War** is folded into INTERPERSONAL.

**Fix.** Leave the domain list alone. Add a **post-hoc, text-only "plot-type" code** derived from `obstacle_summary`,
`locus_reason` and `evidence_quote`. Every v0.9 obstacle row now has a non-empty summary and locus_reason. The code
would have these values:
- marriage/courtship;
- inheritance/property transfer;
- class mobility;
- religion/conscience;
- empire/race;
- crime/justice;
- war;
- deadline;
- none.

It can be done by a small model or by keyword plus human audit. It costs no GPU-scale relabel, and it lets the paper
speak the field's language.

### P6 (medium): the technology hinges cannot carry the paper

**Evidence.**
- 115 of 6,290 v0.9 obstacles (1.8%) name a technology.
- Many of these are wrong: "telegram" for a missing porter, "steamship" for deep snow, "letter" for Mr Grey forbidding
  travel in *Can You Forgive Her?*, "carriage" for a character's weakness.
- `night_function` is non-none in only 4–6% of obstacles, and `failure_cause` is non-none in about 14%.
- Random windows seldom land on the telegram scene, so the enrichment strata, not the backbone, are where H2a–c live.

**Fix.**
- Demote the hinges from the title and the opening. Keep them as dated context, and keep H3 (mention ≠ function) as
  the methodological contribution.
- The showcase's "machines are almost never the obstacle" is a good *observation*. Phrase it as "in a random page of
  fiction, a machine is almost never what blocks anyone", not as "novelists kept putting people in the way". The
  enrichment data may yet show the telegram plot that Menke and Koehler describe.

### P7 (medium): reading quality on my 44-passage sample

**Evidence.**
- About 30 of the 44 passages are labelled "yes". By my reading, about 18 of those are defensible.
- About 7 are false or trivial yeses: the sneeze, the cat, the polite excuse, the rugged road, O. Henry's hypochondriac
  read straight, *Jasper Lyle*'s wizard, and the Harry Fenimore "indecision".
- About 5 have a misread locus, and the errors cluster on inwardness (P3). One goes the other way: the *Five Little
  Peppers* delirium is coded internal, but the body is material.
- *A Marriage in High Life* (1828) shows the silver-fork novel's real obstacle, the reputation Mrs Osterley's gibe
  threatens. The model coded it as coachmen blocking a carriage, DISTANCE + "infrastructure" + technology "carriage".
- Irony, comedy and personification are the model's blind spots. These are period-*independent*, but genre- and
  prestige-*dependent*, which feeds P1.
- The early-era "no" labels (Scott, G. P. R. James, Porter) were mostly right.

**Fix.** Make the teacher's 30-passage reference set include irony, personification and resolved-deliberation items,
and report per-genre human–model agreement.

### P8 (low-medium): presentation issues a teacher or reviewer will notice

- The showcase calls all 15,511 works "novels". They include story collections, a book of one-syllable moral tales
  (Bakewell) and fairy stories. Say "works of fiction".
- The showcase's within-genre reassurance ("not just the flood of adventure stories") is undercut by P1. Soften it
  until the prestige check is run.
- The epigraph is dated 1799, outside the 1800–1929 window. Correcting the date was right, but choose an in-window
  epigraph or note the anomaly.
- "Distant reading" framing is absent. Moretti (*Graphs, Maps, Trees*; "The Slaughterhouse of Literature"), Underwood
  (*Distant Horizons*), Bode (*A World of Fiction*, on the archive as an object that must be modelled) and Piper
  (*Enumerations*) should be the paper's interlocutors, especially for P1. Bode's argument that digitized collections
  are themselves historical artifacts is the natural citation.

---

## 2. Redirection ideas, ranked by novelty × interest × feasibility

### R1 (recommended lead): "Two fictions": the obstacles of the canon and of the circulating mass

**Claim to test.** Across 1800–1929, novels that became canonical locate resistance in **people and rules** (about 80–90%
social, under 10% material). The mass market keeps **the world itself** (weather, distance, animals, wounds) as the
antagonist at about 20%, and this gap is stable rather than a trend.

**Why it is a finding.** It turns the confound into the result. It directly tests Woolf's "materialists" charge. It
speaks to Moretti, Underwood and Bode on what the archive is. And it gives the inward-turn debate a sociological
answer: the "turn" is a difference between literary *fields*, in Bourdieu's restricted versus large-scale production,
not a movement through time.

**Data.**
- Existing fields: `locus`, `domains` and `has_obstacle` from v0.9, plus `works.Authors`.
- New: a prestige covariate (Wikidata sitelinks, ODNB/ANB, reviewed-in-periodicals lists). No relabelling is needed.
- The Chicago corpus and ELTeC-eng give a canon-leaning replication.

**What an English teacher finds striking.** "The books on your syllabus and the books your great-grandparents actually
read are different universes of trouble. In Trollope a person stands in the way. In Henty a river does." The pairing
writes itself: Lady Earle's "You are not my son's equal" (*Dora Thorne*, 1883–4, interestingly a mass-market
best-seller) against the Rover Boys "carried off by the torrent" (1916).

**Feasibility:** high, within days. **Novelty:** medium-high. Underwood & Sellers measured prestige in diction, not plot
function. **Risk:** the canon/mass line blurs (Braddon, Collins, Haggard, Stevenson). That is itself discussable.

### R2: "Who stands in the way?": the opponent's role, gender and authority

**Claim to test.** The social obstacle has a *face*, and its face changes. Examples:
- the matriarch or aunt as enforcer of class endogamy (Lady Catherine, Mrs Reed, Lady Earle);
- the father's veto against the guardian's or trustee's;
- the shift from persons to impersonal systems ("A system recognises only causes which you can see", Galsworthy).

**Data.**
- The existing v0.9 fields `domains` (INTERPERSONAL, RANK, MONEY_PROPERTY_LAW), `locus_reason`, `obstacle_summary` and
  `evidence_quote` already name the opponent in most rows: 4,341 social obstacles.
- Raw summary keyword rates suggest how much signal there is. Female opponent terms appear in about 22–25% of social
  rows, male terms in 19–25%, and an explicit parental or marriage veto in about 4% (247 rows).
- One cheap text-only pass would add opponent role (parent, guardian, spouse, rival, servant, official, institution,
  crowd, colonized or racialized other), opponent gender, and "acting for: self / a rule / an institution".
- This pass also cleanly fixes the RANK/INTERPERSONAL instability in P5, by separating the *agent* from the *norm*.

**What a Victorianist finds striking.**
- A measured answer to "how wicked are aunts?"
- When the obstacle stops being a person and becomes a system: Chancery, the Circumlocution Office, the military board.
- Whether women novelists cast women or men as the obstacle. Author gender can come from Wikidata.
- It connects to Underwood, Bamman & Lee on gendered characterization, which asked about characters but not about
  opponents.

**Feasibility:** medium (about one day of pass plus audit). **Novelty:** high.

### R3: "Providence, chance and persons": how obstacles are overcome

**Claim to test.** There is a named critical thesis: Thomas Vargish's *The Providential Aesthetic in Victorian Fiction*
(1985) and Hilary Dannenberg's *Coincidence and Counterfactuality* (2008) describe a decline of providential and
coincidental resolution. On that account, chance turns malign in Hardy and modernism refuses resolution. The test is
whether obstacles are increasingly overcome by characters' own agency or by institutions, and less by chance or
providence.

**Data.**
- `resolution_hint` is unusable (P4), so this needs a new forward-reading pass: for a sample of salient obstacles, read
  the next 1–3 passages, or the chapter end, and code the resolution as chance or coincidence, providence, another
  person, the character's own action, an institution or law, technology, death, or unresolved.
- The v0.5 counts (32 chance, 175 person) show the model can make the distinction when the passage contains the
  resolution.
- Raw summaries mention chance, fate or providence in 2.8% of rows in 1800–49 and 1.2% after. That is suggestive and
  tiny.

**What an English teacher finds striking.** "Deus ex machina" becomes a number. It also asks whether the *machine*
(telegram, train) replaces the *deus*, which is the honest way to bring the technology hinges back.

**Feasibility:** low-medium. It needs a new sampled pass, about 2k obstacles, and its own human check. **Novelty:**
highest. It tests a specific, citable thesis that has never been counted. I would pre-register it for the January paper,
not for November.

### R4 (cheap add-on to R1 or R2): genre-specific stories via the plot-type code (P5)

**Data.** Use the post-hoc plot-type code to trace three things:
- the **marriage plot** inside domestic and romance: does the parental veto give way to inner hesitation, a New Woman
  shift?
- the **inheritance plot** (forged wills, missing heirs) from Gothic and Scott to Alger and Le Queux;
- **empire** obstacles in adventure fiction 1880–1914 (Haggard, Henty, Ballantyne).

**Feasibility:** high. **Interest:** high for teachers and Victorianists. **Novelty:** medium. Use it to supply passage
cards, not confirmatory tests.

**Recommended package.**
- For November (NAACL SRW, DH2027): make **R1** the core claim, with **R2** as the second finding. Keep H3 as the
  method contribution and the technology hinges as a short, honest null.
- For January: add **R3**.
- H1 stays registered (two-sided) but moves out of the headline.

---

## 3. How to open the paper

Open in the classroom, not with Kahler. Every English student learns that stories run on conflict: person against
nature, against society, against self. This paper makes that schoolroom triad measurable, and it says plainly where the
triad sits relative to Greimas's opponent and Ryan's conflicting worlds. Then put two passages side by side.

> "You are not my son's equal in refinement or education." (*Dora Thorne*)

> "he was carried off by the torrent" (*The Rover Boys on a Tour*)

Ask the question Woolf asked in 1919, when she called the novelists of her day "materialists": what did the fiction
people actually read put in its characters' way, and is it the same fiction critics have in mind when they speak of an
"inward turn"? State the answer as a claim about two fictions, the canon that survives on syllabi and the mass that
survives on Project Gutenberg, measured from tens of thousands of passages read for function rather than for keywords.
Present the archive (Bode, Moretti) as part of the object of study, not a nuisance to be controlled away. Only then
introduce the railway, the penny post and gaslight, as the modern conditions under which, strikingly, the machine almost
never became the obstacle.
