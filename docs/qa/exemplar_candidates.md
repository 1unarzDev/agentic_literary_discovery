# Exemplar candidates (strong-indicator passages)

These come from QA-reviewed **discovery** passages only. Quotes are verbatim from the passage, with line breaks collapsed. Use them for the human teaching set and for the paper's passage cards. Status codes:
- ✔ = the model was right;
- ✎ = the model mislabelled it. These make good teaching items: the label shown is the corrected one.

**Do not use them for human-audit scoring.**
- **Reserved:** pg8938_p00080 and pg72909_p00168 are the few-shot examples in the v09a prompt candidate. Keep them out of every evaluation set.
- **Teaching items:** keep teaching-set passages out of the audit sample (`analysis/select_annotation.py` should exclude these IDs).

Years are as catalogued; see the date notes in label_pass_2.md.

## Positive prototypes by domain

| Domain | Era | passage_id | Work | Quote | Note |
|---|---|---|---|---|---|
| SOCIAL_RANK_CONVENTION | 1800–49 | pg47312_p01011 | Reynolds, *Mysteries of London* (1846) | "how insuperable is the barrier which divides us _now_!" | commoner learns his beloved is a princess ✔ |
| SOCIAL_RANK + INTERPERSONAL | 1850–84* | pg51665_p00221 | Taylor, *Tippoo Sultaun* (cat. 1880; pub. 1840) | "if we did not receive her kindly, he would send us both home to our parents" | household rule of co-wives enforced by threat ✔ |
| COMMUNICATION / intentional_withholding (forgery) | 1800–49 | pg33973_p00007 | Reeve, *The Mysterious Wanderer* (1807) | "the crafty villain effectually screened himself from punishment by the evidence of his two servants" | forged deeds, perjured witnesses ✔ |
| COMMUNICATION / intentional_withholding | 1885–1929 | pg45022_p00051 | Alger, *Bernard Brooks' Adventures* (1903) | "I must get the boy out of the city. This man may tell him too much." | guardian hides an inheritance ✔ |
| COMMUNICATION / intentional_withholding | 1885–1929 | pg72909_p00168 | Evarts, *Tumbleweeds* (1923) | "carefully refrained from delivering the message" | **reserved (few-shot)** ✔ |
| COMMUNICATION / accidental_loss | 1885–1929 | pg57603_p00048 | Richards, *A Daughter of Jehu* (1918) | "Missent to 'Cyrene'!" | misdelivered letter; the aunt arrives today ✔ (H2a prototype) |
| COMMUNICATION / accidental_loss | 1885–1929 | pg56658_p00039 | Barclay, *Danny Again* (1920) | "But now nobody knows where it is; the secret has been quite lost for four hundred years" | ✎ model said intentional_withholding |
| DARKNESS_VISIBILITY / night danger | 1800–49 | pg13405_p00371 | Marryat, *Monsieur Violet* (1836) | "especially as the darkness would render it more difficult to take a certain aim" | panther hunt at nightfall ✔ (H2c early) |
| DARKNESS_VISIBILITY | 1850–84 | pg16958_p00141 | Quigley, *The Cross and the Shamrock* (1853) | "As the night was dark, and the road the animals took in their furious course was not known" | night search fails ✎ model said NATURE+DISTANCE |
| DARKNESS_VISIBILITY / fog, concealment | 1885–1929 | pg17789_p00141 | Parrish, *Molly McDonald* (1912) | "This mist became so thick that the men could scarcely see a hundred yards in any direction" | pursuit hidden by fog ✔ |
| DARKNESS_VISIBILITY (terrain, not night) | 1885–1929 | pg72362_p00029 | Weedon, *The Golden Story Book* (1900) | "he could not see the road immediately beneath him" | general cannot see the enemy column; a drummer raises the alarm ✎ model said DISTANCE+NATURE |
| DISTANCE_TRAVEL | 1885–1929 | pg70867_p00128 | Comfort, *Somewhere South in Sonora* (1925) | "Forty miles around would have been simple to the twenty they had made before sundown that day--a waterless fight all the way." | the mare finds water by_chance ✔ |
| DISTANCE_TRAVEL + MONEY | 1850–84 | pg2306_p00138 | Harris, *Uncle Remus* (1881) | "Whar's yo' ticket?" | emigrants with no ticket or provisions ✔ (dialect) |
| DISTANCE_TRAVEL (comic, infrastructure) | 1885–1929* | pg2869_p00031 | James, *The Point of View* (cat. 1886; pub. 1882) | "There are, on the other hand, no cabs and no porters" | epistolary; traveller hauls his own tub ✎ MONEY dropped |
| NATURE_WEATHER | 1800–49 | pg8223_p00110 | Brown, *Edgar Huntly* (1804) | "To preserve myself, I was obliged to loose my hold of my burden, and it fell into the gulf." | gust on a log bridge defeats the errand ✔ |
| NATURE_WEATHER | 1885–1929 | pg36179_p00173 | Stratemeyer, *Rover Boys on a Tour* (1916) | "he was carried off by the torrent" | bridge collapses in flood ✔ |
| NATURE_WEATHER | 1885–1929 | pg60811_p00124 | Janvier, *In Great Waters* (1901) | "a change of wind was coming before mid-day, and that pretty soon after the wind shifted it would be blowing a gale" | ✔ |
| ILLNESS_BODY_DEATH | 1850–84 | pg43325_p00138 | Hocking, *Her Benny* (1880) | "The doctor shook his head when he came, but held out no hope of recovery." | ✔ |
| ILLNESS + NATURE | 1885–1929 | pg7179_p00132 | Maclaren, *Beside the Bonnie Brier Bush* (1901) | "nane but a richt-hearted man wud hae riskit the Tochty in flood" | Scots dialect; surgeon fords the flood to operate ✔ |
| MONEY_PROPERTY_LAW | 1850–84 | pg28381_p00023 | Alger, *Ben, the Luggage Boy* (1876) | "But the price was ten cents, and of course it was entirely beyond his means." | ✔ |
| MONEY_PROPERTY_LAW + INTERPERSONAL | 1885–1929 | pg21270_p00049 | Alger, *Five Hundred Dollars* (1889) | "He would have been but for the interference of a meddlesome young lawyer" | false theft charge ✔ |
| INTERPERSONAL_CONFLICT | 1885–1929 | pg69587_p00005 | Laut, *The Quenchless Light* (1924) | "Stop him!—stop him!—slave!—slave!—runaway slave!" | pursuit; resolved by_chance ✔ |
| INTERPERSONAL_CONFLICT (comic) | 1800–49 | pg21549_p00263 | Marryat, *Jacob Faithful* (1834) | "Mr Winterbottom was carried up the river very much against his inclination" | ✔ |
| INNER_STATE | 1850–84 | pg6059_p00226 | Simms, *Confession* (1856) | "If that damning doubt were not there!--that wild fear, that fatal, soul-petrifying suspicion!" | jealousy ✔ |
| INNER_STATE | 1885–1929 | pg44633_p00309 | MacFarlane, *Held to Answer* (1916) | "he was still under the spell of his fear,--and could not see himself as yet doing one thing to weaken the pressure upon his benefactor" | ✔ |
| INNER_STATE (pride vs rank) | 1885–1929 | pg21813_p00112 | Ballantyne, *The Madman and the Pirate* (1888) | "I, a chief and a descendant of chiefs, stoop to ask, to beg, my slaves to become Christians?" | ✎ locus should be internal |

\* catalogued era; the true publication date puts it in the earlier era.

## Cross-era pairs (for passage cards)

| Contrast | Earlier | Later |
|---|---|---|
| **H2a, forms of communication failure** | pg33973_p00007 (1807): forged deeds and perjury | pg57603_p00048 (1918): letter "Missent to 'Cyrene'" (postal infrastructure, accidental) |
| **H2c, darkness** | pg13405_p00371 (1836): nightfall spoils a hunter's aim | pg17789_p00141 (1912): fog conceals a cavalry pursuit |
| **Nature as obstacle** | pg8223_p00110 (1804): gust on a log bridge | pg36179_p00173 (1916): car swept off a broken bridge in flood |
| **Rank as barrier** | pg47312_p01011 (1846): commoner and princess | none clean yet in late w01. Late RANK codings were mostly wrong; look in w03 |
| **Inner state** | pg6059_p00226 (1856): jealous suspicion | pg44633_p00309 (1916): fear prevents a confession |
| **Money** | pg28381_p00023 (1876): ten cents beyond his means | pg21270_p00049 (1889): theft charge, trial |

## Hard negatives (teach "no")

| passage_id | Why it is not an obstacle |
|---|---|
| pg8938_p00080 (1827, *Zenobia*) | Shyness the speaker goes ahead despite. **Reserved (few-shot).** |
| pg4955_p00039 (1875, *Leah Mordecai*) | "it is no trial for me to forego the pleasures that are so alluring to you": the barrier is explicitly denied |
| pg42409_p00042 (1902, *Sea Stories*) | Whaling procedure: "This operation, involving the greatest amount of labor in the whole of the cutting-in". Description only |
| pg42427_p00188 (1910) | "Barbara was not there.": a momentary absence at a party |
| pg32152_p00026 (1908, *The Widow*) | Flirtatious banter |
| pg62794_p00032 (1920, *Toto*) | The obstacle (a burglary plan) is only in CONTEXT AFTER |

## Gaps
There are no early-era (1800–1849) DISTANCE_TRAVEL or COMMUNICATION/infrastructure prototypes yet. These are the core of H2b and H2a. Target them in the w03 enrichment QA (enrich_mob / enrich_comm strata).
