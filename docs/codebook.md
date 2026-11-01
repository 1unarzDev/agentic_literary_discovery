# Codebook v0.5: Plot obstacles (draft; v0.9 due Nov 5, frozen v1.0 Nov 8)

## The core question
**In this passage, is something standing in the way of what a character wants, in a way that matters for what happens next?**

A *plot obstacle* is anything that **blocks, delays, or endangers a character's goal** and plausibly shapes later events or decisions. All three conditions must hold:
1. **A character with a goal.** The goal can be explicit ("she longed to reach London") or clearly implied (escaping, marrying, learning a secret, saving someone).
2. **Something impeding it.** A thing, a person, a rule, a feeling, or a lack (of news, light, money).
3. **Narrative consequence.** The impediment is part of the action and not mere description. A storm described as scenery doesn't count. A storm that keeps the doctor from arriving does.

**Not obstacles:**
- A letter that is merely mentioned.
- A dark room described for atmosphere.
- A generic complaint ("times were hard").
- A narrator's essayistic reflection with no character goal at stake.

When the passage is too fragmentary to tell, choose `insufficient_context`.

## Fields

### `has_obstacle`: yes | no | insufficient_context

### `domain` (pick the 1–2 that best answer "what kind of thing is in the way?")
| Code | In the way is… | Examples |
|---|---|---|
| DISTANCE_TRAVEL | Physical distance, the difficulty or slowness of a journey, missed coaches or trains, impassable roads | "Forty miles of bad road lay between them"; she misses the last train |
| COMMUNICATION_INFORMATION | Messages that fail, are delayed, lost, intercepted, forged, unanswered or misread; secrets; ignorance of a key fact; mistaken identity | the letter under the carpet; the telegram that comes too late; a concealed will |
| DARKNESS_VISIBILITY | Not being able to see: night, fog, lack of light, concealment by darkness | lost on the moor at night; can't read the face in the gloom |
| ILLNESS_BODY_DEATH | Sickness, injury, weakness, pregnancy, death or dying | fever confines him; her father's death leaves her unprotected |
| MONEY_PROPERTY_LAW | Poverty, debt, inheritance and entail, contracts, courts, police, legal status | the entail; the debtors' prison; a will |
| SOCIAL_RANK_CONVENTION | Class, propriety, reputation, marriage rules, gender norms, family authority as *a rule* | "a governess cannot marry the heir"; scandal would ruin her |
| INTERPERSONAL_CONFLICT | A specific person actively opposing, deceiving, threatening or thwarting | the villain locks her in; a rival's plot |
| INNER_STATE | The character's own doubt, fear, pride, guilt, desire, conscience or indecision | he cannot bring himself to speak; her pride forbids it |
| NATURE_WEATHER | Storms, floods, snow, sea, wild terrain, animals | snowed in; the boat founders |
| OTHER | Something clearly an obstacle that fits none of the above | |

When several apply, pick the **proximate** one: the thing that, if removed, would let the character proceed. A villain who intercepts a letter is coded `COMMUNICATION_INFORMATION` (failure cause `intentional_withholding`) plus `INTERPERSONAL_CONFLICT`.

### `locus` (where the resistance comes from)
- **material_external**: physical world and infrastructure (distance, darkness, weather, illness, lost objects, technical failure).
- **social_institutional**: other people, rules, law, money, rank, convention, deliberate deception by others.
- **internal_psychological**: the character's own mind.

Default mapping:

| Domains | Locus |
|---|---|
| DISTANCE, DARKNESS, NATURE, ILLNESS | material |
| MONEY/LAW, SOCIAL_RANK, INTERPERSONAL | social |
| INNER_STATE | internal |
| COMMUNICATION | depends on the failure cause: infrastructure or accidental → material; withholding or misinterpretation by others → social; the character's own refusal to write or speak → internal |

**Override the default whenever the passage says otherwise.** For example, illness that is clearly hysteria or "nerves" may be internal. Record a one-word reason in `locus_reason`.

### Communication sub-fields (only when the domain is COMMUNICATION_INFORMATION)
- `failure_cause`:
  - `infrastructure`: slow post, no telegraph office, distance, closed office, the post hasn't come;
  - `accidental_loss`: lost, misdelivered, overlooked, arrives at the wrong time;
  - `intentional_withholding`: withheld, intercepted, burned, forged, deliberately unanswered, secret kept;
  - `misinterpretation`: message misunderstood, ambiguous, mistaken identity;
  - `success_resolution`: communication *removes* an obstacle (record this too; it is the counterpart);
  - `none`.
- `message_valence` (what the message carries, if one is present): catastrophic (death, illness, ruin, arrest, summons) | romantic | financial | practical | none.

### `technology_named`
The communication, travel or light technology that is **named and plot-relevant**: letter | note | telegram | telephone | messenger | railway | coach | steamship | carriage | horse | foot | gas | electric | candle | lamp | none.

### `night_function` (only if the passage happens at night or in darkness)
danger | concealment | intimacy | labor | leisure | none.

### `resolution_hint` (if the passage shows it)
by_technology | by_person | by_chance | unresolved | unknown.

### `obstacle_summary`
At most 15 words, **in plain modern English**, naming the obstacle generically (e.g., "lover's letter intercepted by jealous aunt"). No character names.

### `evidence_quote`
**Copy one exact sentence or clause from the passage** that shows the obstacle. It must appear verbatim. Do not paraphrase, fix spelling, or join separate sentences.

### `confidence`
0–1, how sure you are of `has_obstacle` and `domain`.

## Decision rules for hard cases
1. **Mention ≠ function.** "He sealed the letter" is not an obstacle. "The letter never reached her, and she married another" is.
2. **Reported past obstacles count** if they still shape the present action.
3. **Hypothetical obstacles** ("if the post should fail…") count only if a character acts on the fear.
4. **Dialogue counts.** A character explaining a barrier ("I cannot leave my father") is an obstacle.
5. **Comic obstacles count** the same as serious ones.
6. **Don't use outside knowledge** of the book. Judge from the passage and its context only.
