# Annotator guide: sources of the quoted examples

The guide (`docs/annotator_guide.md`, served at `/annotate/guide`) quotes Discovery-half passages
only (Project Gutenberg, public domain). Passage ids stay here, not on the annotator-facing page.
Quotes are exact except that typographic quotes/apostrophes are shown as straight ones
(checked against `data/work/passages.parquet`). None of these passages is in the practice,
check (cert) or retake sets, or in any audit draw (all Discovery).

| Guide section | passage_id | Reference | Why this example |
|---|---|---|---|
| Worked 1, letter never arrived | pg74270_p00130 | yes / COMMUNICATION / intentional_withholding / social | classic intercepted letter; also a past obstacle still shaping the scene |
| Worked 2, gale | pg21552_p00195 | yes / NATURE_WEATHER / material | weather blocks a rescue, consequence shown in-passage |
| Worked 3, coal mine | pg56756_p00110 | yes / DARKNESS_VISIBILITY / material | darkness as the obstacle itself (not atmosphere) |
| Worked 4, pride | pg71263_p00091 | yes / INNER_STATE / internal | nothing external in the way |
| Worked 5, station | pg3417_p00242 | yes / SOCIAL_RANK_CONVENTION / social | rank rule enforced by a parent (vs INTERPERSONAL) |
| Worked 6, mortgage | pg35985_p00211 | yes / MONEY_PROPERTY_LAW / social | obstacle reported inside a letter |
| Worked 7, Great Stone Face | pg7868_p00035 | no | description and a wish, nothing in the way |
| Worked 8, Latin deed | pg26315_p00025 | insufficient_context | unreadable for the annotator |
| Tricky, mention vs function | pg48249_p00013 | yes / DISTANCE_TRAVEL / material | mentioned letter vs missed train; telegram succeeds |
| Tricky, atmosphere | pg65143_p00050 | yes / DARKNESS_VISIBILITY / material | long fog description that does block a goal |
| Tricky, hypothetical | pg67654_p00121 | (prediction alone does not count) | "we'll be snowed up", nobody acts on it |
| Tricky, history-like | pg20791_p00150 | yes / NATURE_WEATHER / material | historical narration judged like fiction |
| Tricky, essay | pg8570_p00201 | no | reflection without a character's goal |
| Tricky, comic | pg25505_p00022 | yes / OTHER / material | comic predicament; also shows OTHER |
| Tricky, several obstacles | pg42886_p00057 | yes / DISTANCE_TRAVEL / material | illness motivates, telegram works, distance is proximate |

Practice, check and retake references (with rationales) live in
`data/work/annotation/practice_ref.json` (not in the repo).
