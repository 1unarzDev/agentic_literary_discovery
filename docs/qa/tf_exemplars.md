# TWO FICTIONS exemplars for paper passage cards (Discovery only, 2026-11-04)

**Source:** the Claude reference-label set (`docs/claude_reference_analysis.md`, `analysis/claude_ref.py exemplars`).
- **Pool:** random Discovery passages from the registered primary set (`primary_v2_capv2`) that Claude rated `has_obstacle = yes` with clarity "vivid". There were 116 candidates (`data/work/claude_ref/exemplar_candidates.jsonl`).
- **Selection:** 10 canonical and 10 popular, chosen by hand to cover each era (E 1800–49, M 1850–84, L 1885–1929) and each locus within each field.
- **Internal is rare:** only 6 "vivid" internal obstacles were in the pool (4 canonical, 2 popular). Two of the cards here are internal in each field.
- **No Confirmation passage was read.**

**Verification.**
- Every **evidence quote** is the codebook-format quote (6–20 consecutive words), checked as an exact substring of the PASSAGE text in `data/work/passages.parquet`.
- Every **card excerpt** is a verbatim, longer span of the same passage that contains the quote, extended to sentence boundaries where the passage allows. It was checked as an exact substring too. Whitespace and line breaks are collapsed to single spaces for display.
- Some card excerpts stop mid-sentence because the passage itself ends there (e.g. Melville).

**Caveats.**
- **Loci and readings** are Claude's (an LLM reference, not human gold). The "Gemma v0.9 locus" column shows the production label for the same passage. Only 1 of the 20 differs: Gaskell *North and South*, which Claude reads as material (the Sunday post, infrastructure) and Gemma as social.
- **Excluded on purpose:** collections that are folklore or non-literary famous authors (Bulfinch, Groome, Yeats's *Irish Fairy Tales*, Ellen G. White). They are in the primary set, but they make poor illustrations of the canon/mass contrast.
- **Years** are `year_v2` (else catalog `year`). Several are edition or collection dates rather than first publication. *Seven Little Australians* (1894), *Mr. Crewe's Career* (1908), *Waifs and Strays* (1917) and *The Prophet of the Great Smoky Mountains* (1885) all remain in the L era. Check dates before printing.
- **"Canonical"** is the pre-declared metadata measure (author sitelinks ≥ 30, `docs/canon_measure.md` §2.3). Yonge (21 sitelinks) and Alger are therefore popular, and Churchill (the American novelist) is popular.

## Canonical works (canonical = True)

| # | Era | Locus (Claude) | Work (PG id), author, year | Passage id | Domains (failure_cause) | Gemma v0.9 locus |
|---|---|---|---|---|---|---|
| 1 | E | material | *Pride and Prejudice* (pg1342), Austen, Jane, 1813 | `pg1342_p00039` | NATURE_WEATHER, ILLNESS_BODY_DEATH | material |
| 2 | E | social | *Jane Eyre: An Autobiography* (pg1260), Brontë, Charlotte, 1847 | `pg1260_p00336` | MONEY_PROPERTY_LAW, INTERPERSONAL_CONFLICT | social |
| 3 | E | social | *Sense and Sensibility* (pg21839), Austen, Jane, 1811 | `pg21839_p00160` | INTERPERSONAL_CONFLICT, COMMUNICATION_INFORMATION (intentional_withholding) | social |
| 4 | M | material | *The Two Destinies* (pg1624), Collins, Wilkie, 1859 | `pg1624_p00115` | DARKNESS_VISIBILITY, NATURE_WEATHER | material |
| 5 | M | material | *North and South* (pg4276), Gaskell, Elizabeth Cleghorn, 1855 | `pg4276_p00318` | COMMUNICATION_INFORMATION (infrastructure) | social |
| 6 | M | internal | *The Grey Woman and other Tales* (pg28636), Gaskell, Elizabeth Cleghorn, 1865 | `pg28636_p00036` | INNER_STATE | internal |
| 7 | M | social | *The Piazza Tales* (pg15859), Melville, Herman, 1856 | `pg15859_p00119` | INTERPERSONAL_CONFLICT | social |
| 8 | L | material | *King Solomon's Mines* (pg2166), Haggard, H. Rider (Henry Rider), 1885 | `pg2166_p00214` | DARKNESS_VISIBILITY | material |
| 9 | L | internal | *Waifs and strays [part 1]* (pg2295), Henry, O., 1906 | `pg2295_p00051` | INNER_STATE, COMMUNICATION_INFORMATION (misinterpretation) | internal |
| 10 | L | social | *The Mayor of Casterbridge* (pg143), Hardy, Thomas, 1886 | `pg143_p00241` | COMMUNICATION_INFORMATION, INTERPERSONAL_CONFLICT (intentional_withholding) | social |

1. **Austen, *Pride and Prejudice***. Proximate source: heavy rain keeps her away.
   - Evidence quote (codebook, 6–20 words): “The rain continued the whole evening without intermission;”
   - Card excerpt (verbatim, full sentence): “The rain continued the whole evening without intermission; Jane certainly could not come back.”
   - Reading: Jane wants to go and return / horses refused, then rain and a cold / she cannot come back and falls ill at Netherfield.

2. **Brontë, *Jane Eyre: An Autobiography***. Proximate source: living wife bars marriage.
   - Evidence quote (codebook, 6–20 words): “leave the church: there will be no wedding to-day.””
   - Card excerpt (verbatim, full sentence): “Wood, close your book and take off your surplice; John Green (to the clerk), leave the church: there will be no wedding to-day.” The man obeyed.”
   - Reading: Rochester wants to marry / Mason testifies his wife lives / the wedding is stopped.

3. **Austen, *Sense and Sensibility***. Proximate source: Willoughby coldly rebuffs her.
   - Evidence quote (codebook, 6–20 words): “But have you not received my notes?" cried Marianne in the wildest”
   - Card excerpt (verbatim, full sentence): “"But have you not received my notes?" cried Marianne in the wildest anxiety.”
   - Reading: Marianne wants Willoughby's love / he coldly ignores her and her letters / she nearly faints.

4. **Collins, *The Two Destinies***. Proximate source: dense mist; lost on moor.
   - Evidence quote (codebook, 6–20 words): “We are surrounded by dripping white mist so dense that we”
   - Card excerpt (verbatim, full sentence): “We are surrounded by dripping white mist so dense that we become invisible to one another at a distance of half a dozen yards.”
   - Reading: Travellers want to ride through Shetland / fog hides the way among bogs / they are lost and halted

5. **Gaskell, *North and South***. Proximate source: Sunday post delays letters.
   - Evidence quote (codebook, 6–20 words): “intervened, and interfered with their London letters; and on Tuesday”
   - Card excerpt (verbatim, full sentence): “The Sunday post intervened, and interfered with their London letters; and on Tuesday Margaret was surprised and disheartened to find that there was still no letter.”
   - Reading: Margaret and her father want news of Frederick / the Sunday post delays letters and none arrives / they are left in anxious uncertainty.

6. **Gaskell, *The Grey Woman and other Tales***. Proximate source: terror of the corpse paralyses her.
   - Evidence quote (codebook, 6–20 words): “Now, now was my time, if ever; and yet I could not move.”
   - Card excerpt (verbatim, full sentence): “Now, now was my time, if ever; and yet I could not move. It was not my cramped and stiffened joints that crippled me, it was the sensation of that dead man’s close presence.”
   - Reading: Narrator wants to escape the room; terror of the dead man's presence freezes her until Amante's voice breaks the spell.

7. **Melville, *The Piazza Tales***. Proximate source: pirates plot murder on ship.
   - Evidence quote (codebook, 6–20 words): “words, the servant, a dagger in his hand, was seen on the”
   - Card excerpt (verbatim, full sentence): “Here, in apparent verification of the words, the servant, a dagger in his hand, was seen on the”
   - Reading: Delano wants to depart safely / a murderous plot and armed servant / he seizes Don Benito and orders the crew to row for their lives

8. **Haggard, *King Solomon's Mines***. Proximate source: darkness, last matches, unknown tunnels.
   - Evidence quote (codebook, 6–20 words): “make out any more, the match burnt my fingers and went out.”
   - Card excerpt (verbatim, full sentence): “Before we could make out any more, the match burnt my fingers and went out. Then arose the delicate question of which way to go.”
   - Reading: The trapped men seek an escape; darkness and dwindling matches leave them groping blindly through a labyrinth.

9. **Henry, *Waifs and strays [part 1]***. Proximate source: pride keeps him from seeking her.
   - Evidence quote (codebook, 6–20 words): “large pride and hurt vanity kept him from seeking her.”
   - Card excerpt (verbatim, full sentence): “His large pride and hurt vanity kept him from seeking her. Two evenings later they met at a dinner.”
   - Reading: Trysdale awaits her answer to his proposal / only an uncomprehended cactus arrives and his pride stops him asking / they drift apart.

10. **Hardy, *The Mayor of Casterbridge***. Proximate source: Henchard holds her old letters.
   - Evidence quote (codebook, 6–20 words): ““No, I shall not destroy them,” murmured Henchard, putting the letters”
   - Card excerpt (verbatim, full sentence): ““No, I shall not destroy them,” murmured Henchard, putting the letters away.”
   - Reading: Lucetta wants her past kept from her husband / Henchard reads her letters and refuses to destroy them / she sits in terrified suspense


## Popular works (canonical = False)

| # | Era | Locus (Claude) | Work (PG id), author, year | Passage id | Domains (failure_cause) | Gemma v0.9 locus |
|---|---|---|---|---|---|---|
| 1 | E | material | *City Crimes; Or, Life in New York and Boston* (pg27732), Thompson, George, 1849 | `pg27732_p00108` | OTHER, ILLNESS_BODY_DEATH | material |
| 2 | E | social | *Modern Flirtations: A Novel* (pg43358), Sinclair, Catherine, 1841 | `pg43358_p00254` | SOCIAL_RANK_CONVENTION, INTERPERSONAL_CONFLICT | social |
| 3 | E | social | *The book of Saint Nicholas* (pg71404), Paulding, James Kirke, 1836 | `pg71404_p00044` | INTERPERSONAL_CONFLICT, MONEY_PROPERTY_LAW | social |
| 4 | M | material | *Lady Hester; Or, Ursula's Narrative* (pg4659), Yonge, Charlotte M. (Charlotte Mary), 1860 | `pg4659_p00073` | ILLNESS_BODY_DEATH | material |
| 5 | M | internal | *The Pig Brother, and Other Fables and Stories* (pg43336), Richards, Laura Elizabeth Howe, 1881 | `pg43336_p00033` | INNER_STATE, OTHER | internal |
| 6 | M | social | *Rough and Ready; Or, Life Among the New York Newsboys* (pg55142), Alger, Horatio, Jr., 1869 | `pg55142_p00072` | INTERPERSONAL_CONFLICT | social |
| 7 | L | material | *Colorado Jim* (pg27453), Goodchild, George, 1922 | `pg27453_p00058` | NATURE_WEATHER, INNER_STATE | material |
| 8 | L | material | *Seven Little Australians* (pg4731), Turner, Ethel, 1915 | `pg4731_p00120` | ILLNESS_BODY_DEATH, DISTANCE_TRAVEL | material |
| 9 | L | internal | *The Prophet of the Great Smoky Mountains* (pg35619), Craddock, Charles Egbert, 1901 | `pg35619_p00112` | INNER_STATE | internal |
| 10 | L | social | *Mr. Crewe's Career — Complete* (pg3684), Churchill, Winston, 1901 | `pg3684_p00206` | MONEY_PROPERTY_LAW, INTERPERSONAL_CONFLICT | social |

1. **Thompson, *City Crimes; Or, Life in New York and Boston***. Proximate source: safe door springs shut.
   - Evidence quote (codebook, 6–20 words): “inside of the door there was no means of turning back that spring.”
   - Card excerpt (verbatim, full sentence): “The immense mass of iron swung heavingly upon its hinges, and closed with a sharp _click_; the spring held it fast, and on the inside of the door there was no means of turning back that spring. Like lightning the awful conviction flashed through the burglar's mind that he was _entombed alive_!”
   - Reading: Burglar wants to escape with loot / the safe locks him in, air runs out / he faces suffocation.

2. **Sinclair, *Modern Flirtations: A Novel***. Proximate source: aunt scorns nameless suitor.
   - Evidence quote (codebook, 6–20 words): “Rather than have my niece united to a nameless outcast, living”
   - Card excerpt (verbatim, full sentence): “"Rather than have my niece united to a nameless outcast, living upon the bounty of Sir Arthur Dunbar, or of connections who are probably disgraced by his existence, I would prefer seeing you married to the Twopenny Postman, for he at least is independent, and has something."”
   - Reading: Henry hopes to win Caroline; her aunt's contempt for his namelessness and want of prospects crushes his hopes.

3. **Paulding, *The book of Saint Nicholas***. Proximate source: father refuses pardon and visit.
   - Evidence quote (codebook, 6–20 words): “but the governor, after a sore struggle, denied her”
   - Card excerpt (verbatim, full sentence): “She sent to her father for permission to see him before he died, but the governor, after a sore struggle, denied her request.”
   - Reading: Blandina wants her condemned husband saved and to see him / governor father refuses / she collapses in despair.

4. **Yonge, *Lady Hester; Or, Ursula's Narrative***. Proximate source: fatal internal bleeding.
   - Evidence quote (codebook, 6–20 words): “Dear Trevor lay white with sobbing breath and closed eyes, the cloths”
   - Card excerpt (verbatim, full sentence): “Dear Trevor lay white with sobbing breath and closed eyes, the cloths and mattress soaked through and through with blood.”
   - Reading: They want to save shot Trevor / internal bleeding, nothing can be done / they can only keep him still as he dies.

5. **Richards, *The Pig Brother, and Other Fables and Stories***. Proximate source: habit makes the words slip.
   - Evidence quote (codebook, 6–20 words): “afraid to open his lips, for whenever he did the words would slip out”
   - Card excerpt (verbatim, full sentence): “he was afraid to open his lips, for whenever he did the words would slip out in spite of him.”
   - Reading: Chimborazo wants to stop saying 'Oh dear'; his habit makes him say it, filling the magic bell-punch; it is punched to the end and flies away.

6. **Alger, *Rough and Ready; Or, Life Among the New York Newsboys***. Proximate source: stepfather seizes and drags her.
   - Evidence quote (codebook, 6–20 words): “He seized her by the shoulder, and began to push her along.”
   - Card excerpt (verbatim, full sentence): “He seized her by the shoulder, and began to push her along. "I don't want to go," said Rose, crying.”
   - Reading: Rose wants to stay with Rufie / her stepfather seizes and drags her off / she is kidnapped until a policeman intervenes.

7. **Goodchild, *Colorado Jim***. Proximate source: terror on climb, then blizzard.
   - Evidence quote (codebook, 6–20 words): “They arrived at the summit at the same moment as the blizzard.”
   - Card excerpt (verbatim, full sentence): “They arrived at the summit at the same moment as the blizzard. She saw a whirling mass of snow, heard a roar like ten thousand demons let loose, and felt the strong grip of Jim pulling her down on the snow.”
   - Reading: Angela and Jim must cross the Chilcoot; her fear halts her and a blizzard pins them down on the summit.

8. **Turner, *Seven Little Australians***. Proximate source: broken back, help miles away.
   - Evidence quote (codebook, 6–20 words): “He thought of all that might happen before he brought help, and dare”
   - Card excerpt (verbatim, full sentence): “He thought of all that might happen before he brought help, and dare not leave her unprepared.”
   - Reading: They want to save Judy / broken back and doctor miles away / Meg left alone to watch her dying.

9. **Craddock, *The Prophet of the Great Smoky Mountains***. Proximate source: his doubts overwhelm his faith.
   - Evidence quote (codebook, 6–20 words): “As it was, there was no fight left in him. He closed the book with a”
   - Card excerpt (verbatim, full sentence): “As it was, there was no fight left in him. He closed the book with a sudden impulse.”
   - Reading: Kelsey means to preach; doubts overwhelm him, so he closes the book and confesses lost faith.

10. **Churchill, *Mr. Crewe's Career — Complete***. Proximate source: committees bottle up his bills.
   - Evidence quote (codebook, 6–20 words): “that his bills for the emancipation of the State were prisoners in”
   - Card excerpt (verbatim, full sentence): “His eyes were open now, and he saw men and things political as they were; he knew that his bills for the emancipation of the State were prisoners in the maw of the dragon, and not likely to see the light of law.”
   - Reading: Crewe wants his bills reported / Bascom and Botcher's committees stall them / he demands daily, without result.
