# Codebook v0.9: Plot obstacles (v1.0 frozen Nov 8 after the human-gold check, Nov 6–8)

**The block below is, byte for byte, the codebook the model receives.** `pipeline/make_registry.py` reads it from this
file. Edit it here, and only here: any change creates a new pin, and every passage labelled under the old pin must be
relabelled. Human annotators apply the same text.

History:
- v0.5 is archived in `docs/codebook_v0.5.md`.
- v0.9 = v0.5 + QA pass-2 edits E1–E6 (`docs/qa/label_pass_2.md`) + the pilot-analysis locus rules (locus = proximate
  source, judged first, with a short reason) + the lean output format (`docs/perf_label_ab.md`).
- The decision rules and field definitions of v0.5 are all kept; the edits add tests and exclusions and narrow
  SOCIAL_RANK_CONVENTION, failure_cause and night_function.

```text
CODEBOOK v0.9: plot obstacles.

CORE QUESTION: in this passage, is something standing in the way of what a character wants, in a way that matters for what happens next?
has_obstacle is "yes" only if ALL three hold:
1. A character with a goal, explicit ("she longed to reach London") or clearly implied (escaping, marrying, learning a secret, saving someone).
2. Something impeding it: a thing, a person, a rule, a feeling, or a lack (of news, light, money).
3. Narrative consequence: the impediment is part of the action, not mere description. A storm as scenery does not count; a storm that keeps the doctor from arriving does.
THREE-PART TEST before answering yes: (a) WHO wants WHAT; (b) WHAT, inside the PASSAGE, stops, delays or endangers it; (c) WHERE the passage shows it changing what the character can do or what happens. If you cannot point to (b) and (c) inside the PASSAGE, answer "no".
NOT obstacles: a letter merely mentioned; a dark room described for atmosphere; a generic complaint ("times were hard"); a narrator's essayistic reflection with no character goal at stake; mild discomfort, shyness, fatigue or nervousness the character goes ahead despite; banter, teasing or flirtation; a character merely wondering or speculating; procedural description of work, hunting or travel in which nothing goes wrong; a goal achieved with no impediment left; an obstacle that appears only in CONTEXT BEFORE/AFTER.
"insufficient_context" when the passage is too fragmentary to tell; otherwise "no".

locus: the PROXIMATE SOURCE of the resistance, i.e. the thing that, if removed, would let the character proceed. Judge it from the passage first.
- material_external: physical world and infrastructure (distance, darkness, weather, terrain, animals, illness, lost objects, technical failure)
- social_institutional: other people, rules, law, money, rank, convention, deliberate deception or violence by others
- internal_psychological: only when the blocked character's own feeling, will or judgement is the barrier (pride, fear, guilt, conscience, indecision). The body is not the mind: sickness, injury, sleep or exhaustion is material_external
Typical pattern only, not a rule: DISTANCE, DARKNESS, NATURE, ILLNESS often material; MONEY/LAW, SOCIAL_RANK, INTERPERSONAL often social; INNER_STATE internal; COMMUNICATION: infrastructure or accident material, withholding or misreading by others social, the character's own refusal to write or speak internal. Follow the source, not the domain: death or injury inflicted by people is social; animals and terrain are material; the character's own pride, fear or conscience is internal even under SOCIAL_RANK_CONVENTION; illness that is clearly "nerves" may be internal.
locus_reason: at most 6 words naming that proximate source (e.g. "flooded ford", "father forbids the match", "fever keeps him abed", "her pride forbids asking").

domains: 1-2 codes answering "what kind of thing is in the way?"; if several apply, the proximate one first.
- DISTANCE_TRAVEL: distance, slow or difficult journeys, missed coaches or trains, impassable roads
- COMMUNICATION_INFORMATION: messages failed, delayed, lost, intercepted, forged, unanswered or misread; secrets; ignorance of a key fact; mistaken identity
- DARKNESS_VISIBILITY: not being able to see (night, fog, lack of light, concealment by darkness or terrain); use it whenever not-seeing is what stops the character, even if weather or terrain causes it
- ILLNESS_BODY_DEATH: sickness, injury, weakness, pregnancy, death or dying
- MONEY_PROPERTY_LAW: poverty, debt, inheritance and entail, wills, contracts, courts, police, legal status
- SOCIAL_RANK_CONVENTION: class, propriety, reputation, marriage rules, gender norms, family authority as a RULE that would stop anyone in that position. A particular person's wishes, dislike, schemes or commands are INTERPERSONAL_CONFLICT; a party, dress or etiquette that is merely present is not an obstacle
- INTERPERSONAL_CONFLICT: a specific person actively opposing, deceiving, threatening or thwarting
- INNER_STATE: the character's own doubt, fear, pride, guilt, desire, conscience or indecision
- NATURE_WEATHER: storms, floods, snow, sea, wild terrain, animals
- OTHER: clearly an obstacle that fits none of the above
A villain who intercepts a letter is COMMUNICATION_INFORMATION (failure_cause intentional_withholding) plus INTERPERSONAL_CONFLICT.

failure_cause and message_valence are "none" unless COMMUNICATION_INFORMATION is in domains.
- infrastructure: slow, long or costly post or telegraph, no telegraph office, distance, closed office, the post hasn't come
- accidental_loss: lost, misdelivered, overlooked, arrives at the wrong time; a secret forgotten or lost over time
- intentional_withholding: someone deliberately keeps, intercepts, burns, forges or leaves unanswered the message or fact
- misinterpretation: message misunderstood, ambiguous, mistaken identity
- success_resolution: communication removes an obstacle
message_valence (what the message carries): catastrophic (death, illness, ruin, arrest, summons) | romantic | financial | practical | none.
technology_named: the communication, travel or light technology that is named AND plot-relevant, else none.
night_function: "none" unless the scene is at night or in darkness. concealment = someone hides or moves unseen thanks to the dark; danger = the dark exposes someone to harm or terror; otherwise intimacy, labor or leisure.
resolution_hint: only if the passage shows it, else unknown.
obstacle_summary: at most 10 words, plain modern English, naming the obstacle generically, no character names (e.g. "lover's letter intercepted by jealous aunt").
evidence_quote: 6-20 consecutive words copied verbatim from INSIDE the PASSAGE START/END markers that show the obstacle; prefer a sentence well inside the PASSAGE, away from its first and last lines. Never quote the context; if the key sentence runs past a PASSAGE boundary, copy only the part inside. No "...", no dropped words, no joined sentences or speakers, no spelling fixes.
confidence: 0-1, how sure you are of has_obstacle and domains.

DECISION RULES FOR HARD CASES
- Mention is not function: "He sealed the letter" is not an obstacle; "The letter never reached her, and she married another" is.
- Reported past obstacles count if they still shape the present action.
- Hypothetical obstacles ("if the post should fail...") count only if a character acts on the fear.
- Dialogue counts: a character explaining a barrier ("I cannot leave my father") is an obstacle.
- Comic obstacles count the same as serious ones. Comic, epistolary and dialect passages follow the same three-part test; a letter-writer's reflections are not an obstacle unless the letter reports something blocking a goal.
- Judge ONLY from the PASSAGE (context is for orientation). No outside knowledge of the book.
EXAMPLES: "Certainly they are not of such strength that I do not gladly seize upon the favor thus extended, and count myself honored and happy." The speaker is shy of meeting a queen but goes ahead gladly -> no. "And Bart, deciding that his sister's whims had already imposed far too many restrictions upon both his own activities and Carver's, carefully refrained from delivering the message." -> yes, locus social_institutional, COMMUNICATION_INFORMATION, intentional_withholding.
```

## How the model sees it
- **System message:** `You are a careful literary annotator of nineteenth- and early-twentieth-century fiction. Apply this codebook exactly.` + a blank line + the block above + a blank line + `If has_obstacle is not "yes", output only has_obstacle and confidence. Return only JSON.`
- **User message:**
  ```text
  CONTEXT BEFORE (orientation only; never quote it):
  {ctx_before}
  
  === PASSAGE START (judge and quote ONLY this) ===
  {text}
  === PASSAGE END ===
  
  CONTEXT AFTER (orientation only; never quote it):
  {ctx_after}
  ```
  `ctx_before` is the last 900 characters before the passage; `ctx_after` is the next 600.
- **Output (JSON schema, `anyOf`):**
  - `has_obstacle = yes`: all of `has_obstacle, locus, locus_reason, domains (1–2), failure_cause, message_valence,
    technology_named, night_function, resolution_hint, obstacle_summary, evidence_quote, confidence`, in that order.
  - `no` / `insufficient_context`: only `has_obstacle, confidence`. Analysis reads the absent fields as domains [],
    locus none, sub-fields none, resolution_hint unknown, quote n/a.
- **Options:** temperature 0, seed 0, num_ctx 4096, num_predict 200.

## Notes for human annotators
- Fill the same fields in the same order. Decide **locus before domains**, from the proximate source of the
  resistance, and write the ≤6-word `locus_reason`. The domain→locus table is a typical pattern, not a rule.
- `evidence_quote` must lie entirely inside the PASSAGE. The pipeline accepts a quote that straddles the passage
  boundary when at least 6 of its words verify inside the passage ("trimmed").
