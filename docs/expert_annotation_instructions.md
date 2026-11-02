# Expert reader instructions: "What Stands in the Way"

Thank you for helping. You are the study's **expert reader**. Your labels are the reference that the student annotators and the AI model are measured against, so careful judgment matters more than speed.

The study asks whether the obstacles in English fiction (1800–1929) changed over time. You will read short passages (about 350 words each) and record whether something stands in a character's way.

You are blind by design. Passages come without title, author, or date. Please don't look them up, and judge each passage on its own text.

There are two tasks.

| Task | Items | Time | File you receive | File you return |
|---|---|---|---|---|
| **A. Answer-key review** (now) | 60 | ~45–60 min | `key_review_items.csv` (or `.jsonl`) | `key_review_RETURN.csv` |
| **B. Expert labels** (from Nov 5) | ~450 | ~4 h, in sittings | `expert_items.csv` (or `.jsonl`) | `expert_RETURN.csv` |

Each item has `ctx_before`, `passage`, and `ctx_after`. **Judge only the `passage`.** The context is there to orient you.

---

## The core question

> **Is something in this passage standing in the way of what a character wants, in a way that matters for what happens next?**

All three must hold:

1. **A goal.** A character wants something, stated or clearly implied (to escape, marry, learn a secret, arrive, save someone).
2. **An impediment.** Something blocks, delays, or endangers that goal: a thing, a person, a rule, a feeling, or a lack (of money, news, or light).
3. **Consequence.** The impediment is part of the action. A storm described as scenery does not count. A storm that keeps the doctor from arriving does.

**Not obstacles:**
- mere mention ("he sealed the letter");
- atmosphere;
- description or essay-like narration;
- banter;
- mild discomfort the character simply pushes through;
- an obstacle that appears only in the context and not in the passage.

When the passage is too fragmentary to decide, answer `cant_tell`.

## Fields

### `has_obstacle`
`yes` | `no` | `cant_tell`

### `domain` (only if `yes`)
What kind of thing is in the way? Choose **one**: the proximate obstacle, meaning the one that, if removed, would let the character go ahead.

| Code | In the way is… |
|---|---|
| `DISTANCE_TRAVEL` | distance; slow, hard, or missed journeys |
| `COMMUNICATION_INFORMATION` | messages lost, delayed, intercepted, forged, unanswered, misread; secrets; ignorance of a key fact |
| `DARKNESS_VISIBILITY` | not being able to see: night, fog, no light |
| `ILLNESS_BODY_DEATH` | sickness, injury, weakness, death |
| `MONEY_PROPERTY_LAW` | poverty, debt, inheritance, contracts, courts, police |
| `SOCIAL_RANK_CONVENTION` | a *rule* that would stop anyone in that position: class, propriety, marriage rules, gender norms |
| `INTERPERSONAL_CONFLICT` | a specific person actively opposing, deceiving, or threatening |
| `INNER_STATE` | the character's own doubt, fear, pride, guilt, desire, or conscience |
| `NATURE_WEATHER` | storms, floods, sea, terrain, animals |
| `OTHER` | clearly an obstacle, but none of the above |

### `locus` (only if `yes`)
Where does the resistance come from? Decide from the passage, not from the domain.

| Code | Meaning |
|---|---|
| `material_external` | the physical world, bodies, places, things, infrastructure |
| `social_institutional` | other people, rules, law, money, rank, convention |
| `internal_psychological` | the character's own mind |

The body is not the mind: illness is material, fear is internal.

### `failure_cause` (only if `domain` = `COMMUNICATION_INFORMATION`)
`infrastructure` (slow post, no telegraph, distance) | `accidental_loss` (lost or misdelivered) | `intentional_withholding` (withheld, intercepted, forged, secret kept) | `misinterpretation` | `success_resolution` (communication *removes* an obstacle) | `none`

### Optional fields
| Field | Contents |
|---|---|
| `evidence` | a short exact quote from the passage showing the obstacle |
| `note` | anything unusual |
| `seconds` | time spent, if your software records it |

---

## Return format

Return **one CSV file** (UTF-8, comma-separated, header row, quote fields that contain commas). JSON Lines with the same field names also works. A template with every `item_id` pre-filled is provided: `*_RETURN_TEMPLATE.csv`.

### Task A: answer-key review
Each item shows a draft answer (`draft_has_obstacle`, `draft_domain`, `draft_locus`, `draft_failure_cause`) and a `draft_rationale`. Your corrected answers become the official key used to train and certify the student annotators.

Columns:
```
item_id,annotator,decision,has_obstacle,domain,locus,failure_cause,evidence,note,seconds
```

| `decision` | When | What else to fill |
|---|---|---|
| `agree` | the draft is right | nothing else needed |
| `correct` | anything in the draft is wrong | fill **all** answer fields with *your* answer, and add a short `note` saying why |

Example:
```csv
item_id,annotator,decision,has_obstacle,domain,locus,failure_cause,evidence,note,seconds
kr_80c904d60a,expert1,agree,,,,,,,
kr_29fe0eec9d,expert1,correct,yes,INNER_STATE,internal_psychological,,"could not bring himself to speak",pride stops him; nobody forbids it,45
kr_aed9b26e89,expert1,correct,no,,,,,"description of a procedure; no goal blocked",30
```

### Task B: expert labels
There is no draft answer; label each passage yourself.

Columns:
```
item_id,annotator,has_obstacle,domain,locus,failure_cause,evidence,note,seconds
```

Example:
```csv
item_id,annotator,has_obstacle,domain,locus,failure_cause,evidence,note,seconds
ex_1a2b3c4d5e,expert1,yes,COMMUNICATION_INFORMATION,material_external,accidental_loss,"Missent to 'Cyrene'!",,38
ex_9f8e7d6c5b,expert1,no,,,,,,22
ex_0a1b2c3d4e,expert1,cant_tell,,,,,fragment of a list,15
```

### Rules the file is checked against
1. `annotator` is always `expert1`. It keeps you anonymous.
2. Use the codes exactly as written (lowercase or uppercase as shown).
3. When `has_obstacle` is `no` or `cant_tell`, leave `domain`, `locus`, and `failure_cause` **empty**.
4. When `has_obstacle` is `yes`, `domain` and `locus` are required.
5. `failure_cause` is filled **only** when `domain` is `COMMUNICATION_INFORMATION`, and is required then.
6. Each `item_id` appears once. Unfinished items can simply be left out and sent later.

Partial returns are welcome. Send what you have, and we will merge later batches.

## Hard cases

| Situation | Decision |
|---|---|
| A reported past obstacle still shapes the scene | counts |
| A hypothetical obstacle ("if the post should fail…") | counts only if a character acts on the fear |
| A character explains a barrier in dialogue ("I cannot leave my father") | counts |
| A comic obstacle | counts, same as a serious one |
| A villain intercepts a letter | `COMMUNICATION_INFORMATION` + `intentional_withholding`, locus social |
| A rule that would stop anyone vs one person's wish | the rule is `SOCIAL_RANK_CONVENTION`; the person is `INTERPERSONAL_CONFLICT` |
| Several obstacles | pick the proximate one (if it were removed, the character could go ahead) |

Questions, or a passage that breaks the scheme? Put it in `note`. Those notes are some of the most useful feedback we get.
