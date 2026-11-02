# Author identity v2, split repair, canon measure and primary-population flags (v1, 2026-11-02)

Status: **defined before the Nov 5 audit draw.** Everything here uses metadata only: PG RDF, Wikidata/Wikipedia,
LCSH, bookshelves and workcheck. No label from either split was read to build it. The Confirmation queue analysis
in §4 reads job status rows and shard passage ids, never result blobs.

Code: `pipeline/pg_rdf.py`, `pipeline/wikidata_authors.py`, `pipeline/author_identity.py`,
`pipeline/build_works_v2.py`, `pipeline/split_v2_map.py`. Tests: `tests/test_works_v2.py`.
Outputs (not committed): `data/work/works_v2.parquet`, `data/work/canon.parquet`, `data/work/agent_wikidata.parquet`,
`data/work/pg_rdf_{ebooks,agents}.parquet`, `data/work/split_v2_queue_report.csv`.

Rebuild:
```
uv run python -I pipeline/pg_rdf.py data/raw/rdf/rdf-files.tar.bz2
uv run python -I pipeline/wikidata_authors.py          # cached under data/raw/wikidata_cache/
uv run python -I pipeline/build_works_v2.py --report
uv run python -I pipeline/split_v2_map.py queue-report
```

## 0. Sources and snapshots

| Source | Snapshot | Use |
|---|---|---|
| PG RDF catalog `rdf-files.tar.bz2` | `Last-Modified: Sun, 01 Nov 2026 15:35:50 GMT`, fetched 2026-11-02 04:58 UTC, 126,843,104 bytes; 79,718 ebooks, 36,935 agents | agent ids, aliases, birth/death, `pgterms:webpage`, `pgterms:downloads` |
| Wikidata | fetched 2026-11-02 (SPARQL P1938 + `wbgetentities` + `wbsearchentities`), raw responses in `data/raw/wikidata_cache/` | QID, Wikipedia sitelinks, P31/P569/P570 |
| Wikipedia, "List of Stratemeyer Syndicate series" and "Stratemeyer Syndicate" | wikitext fetched 2026-11-02, `data/raw/stratemeyer_src/` | Syndicate house-name list |
| ELTeC-eng `ELTeC-eng_metadata.tsv` (COST-ELTeC/ELTeC-eng, master) | fetched 2026-11-02, 100 novels | external validation only |

`pgterms:downloads` is PG's **downloads in the last 30 days** at the snapshot. It is a present-day popularity
signal, not a historical one.

Wikimedia note: `query.wikidata.org` returned **403** to the User-Agent `ald-research (github.com/1unarzDev/agentic_literary_discovery) python-httpx`, because its robot policy wants `client/version (contact) library/version`.
The UA used is `ald-research/0.1 (https://github.com/1unarzDev/agentic_literary_discovery; ald-research) httpx/<v>`.
Requests are spaced at least 1.05 s apart, entities are fetched in batches of 50, and every response is cached.

## 1. Author identity v2 and split repair

**Author agent of a work.** This is the canonical edition's first `dcterms:creator` (PG "Author"), else its first
`marcrel:aut`, else its first agent in any role (the editor or compiler of an anthology). Every corpus pg_id is in the
RDF; 244 works have no Author role and fall back to that editor or compiler.

**Author group.** A group is a connected component of PG agents under four kinds of edge:

| Edge | Rule | Works whose group came from it |
|---|---|---|
| E1 | PG "see also" links: `pgterms:webpage` = `ebooks/author/<id>`, PG's own pseudonym ↔ person links | 383 |
| E2 | Same Wikidata QID (§2.2) | 51 |
| E3 | Identical normalised name **and** identical birth and death years (duplicate PG records) | 0 after E1/E2 |
| E4 | Stratemeyer Syndicate (list below) → `syndicate:stratemeyer` | 472 |

- Placeholder agents (Anonymous, Unknown, Various) form no edge. Each of their works is a singleton (`work:<id>`, 82 works). Under v1 they were one "anonymous" cluster of unrelated works.
- House names match on the agent's own name. An alias counts only for an undated (pseudonym) record. A dated real writer who used a house name, such as St. George Rathborne (alias "Harrison Adams"), is joined only through PG's E1 links.

**Stratemeyer Syndicate house names (E4).** These are the credited authors of Syndicate series, from Deidre Johnson,
*Stratemeyer Pseudonyms and Series Books* (Greenwood, 1982), as tabulated in Wikipedia's "List of Stratemeyer
Syndicate series". Edward Stratemeyer is included, together with his pre-1905 personal pseudonyms Arthur M. Winfield and
Captain Ralph Bonehill.

The list: Victor Appleton, Victor Appleton II, Arthur M. Winfield, Captain Ralph Bonehill, Laura Lee Hope, Roy Rockwood,
Allen Chapman, Clarence Young, Margaret Penrose, Frank V. Webster, Lester Chadwick, Captain Quincy Allen, Graham B.
Forbes, Harrison Adams, Raymond Stone, Frederick Gordon, Alice B. Emerson, James Carson, Amy Bell Marlowe, Burbank L.
Todd, Helen Beecher Long, Gertrude W. Morrison, Roy Eliot Stokes, Frank A. Warner, Grace Brooks Hill, Richard Barnum,
Raymond Sperry Jr., Vance Barnum, Annie Roe Carr, Spencer Davenport, Brooks Henderley, Elmer Tracey Barnes, Charles
Amory Beach, Ruth Belmore Endicott, Janet D. Wheeler, Mabel C. Hawley, Ramy Allison White, Helen Louise Thorndyke,
Alice Dale Hardy, May Hollis Barton, Elmer A. Dawson, Nat Ridley Jr., James Cody Ferris, Franklin W. Dixon, Harry
Mason Roe, Philip A. Bartlett, Carolyn Keene, Richard H. Stone, Julia K. Duncan, Fenworth Moore, Clinton W. Locke,
Eugene Martin, Frances K. Judd, Francis Hunt, and the post-1930 names. The full list is in
`pipeline/author_identity.py:STRATEMEYER_HOUSE_NAMES`.

The Syndicate article's own PG cross-reference list (pseudonym → PG author id) agrees with these names. Some names are
deliberately left out:
- **Howard R. Garis** and **Mildred A. Wirt** were real ghostwriters. They enter the group only through PG's own links. PG files "Lester Chadwick" and "Raymond Sperry" under Garis's dates, so Garis's 47 works do join.
- **Nicholas Carter** was a Street & Smith house name, not a Syndicate one. Through E1 it forms its own cluster with Rathborne, Cox, Burton and others.

In the corpus, the Syndicate group has 519 works and 37 PG agents: 367 works were in v1 Discovery and 152 in v1 Confirmation.

**Split repair rule (registered).** A group whose works fall in both v1 splits goes **wholly to Discovery**, because
Discovery labels have already been examined. No work moves from Discovery to Confirmation. `split` (v1) is kept.

**Result.**
- 3,990 v1 author_keys become 4,010 v2 groups. The count rises because placeholder singletons replace the "anonymous" key and homonyms are separated.
- **345 works in 13 groups** (33 PG agents / 33 v1 keys) move Confirmation → Discovery.
- Confirmation goes from 7,407 to 7,062 works (2,024 groups). Discovery goes from 8,104 to 8,449 works (1,986 groups).

| Decade | ≤1840s | 1850 | 1860 | 1870 | 1880 | 1890 | 1900 | 1910 | 1920 | 1930 |
|---|---|---|---|---|---|---|---|---|---|---|
| works moved | 0 | 2 | 2 | 4 | 7 | 37 | 75 | 162 | 56 | 0 |
| groups moved | 0 | 1 | 1 | 2 | 2 | 4 | 8 | 6 | 6 | 0 |

By era: E 0, M 11, L 334. Of the primary_v2 works, M 11 and L 156 move.

| Group | Works moved | Linked via |
|---|---|---|
| Stratemeyer Syndicate | 152 | E4 (Chapman 28, Penrose 27, Emerson 24, Rockwood 19, Chadwick 16, Allen 8, Dixon 6, Beach 6, …) |
| Carolyn Wells (+ "Rowland Wright") | 50 | E1 |
| Rathborne / Nick Carter house cluster | 47 | E1 |
| James Otis (+ "Harry Prentice") | 40 | E1 |
| Molly Elliot Seawell (+ "Foxcroft Davis") | 25 | E1 |
| H. L. Sayler (+ "Elliott Whitney") | 13 | E1 |
| Dinah Craik | 10 | one Discovery work keyed v1 by its first-listed editor (Rossiter Johnson) has PG Author = Craik |
| Lounsberry / H. H. Lewis | 3 | E1 |
| 5 singletons (Lundsford, Cobb, Kenyon, Le Feuvre, P. MacDonald) | 5 | E1 |

**The review's key counts do not reproduce on the current `works.parquet`.** methods_review P8 says Alger has 10 keys,
Dickens 9 and Twain 5. In fact:
- Alger has **1** key (`algerhoratiojr`, all 99 works in Discovery).
- Dickens has 1 author key (`dickenscharles`, 35 works, all Confirmation). The other "Dickens" keys are anthologies where Dickens is a second-listed contributor, so they are other people's works.
- Twain has 1 key.

The real cross-half leakage is the pseudonym and house-name structure above, which v1 could not see.

## 2. Canon / prestige measure (pre-declared)

### 2.1 Downloads (a)
`downloads` is the canonical edition's `pgterms:downloads` (30-day, snapshot above). `author_downloads` sums this over
every PG ebook first-authored by an agent of the group.

### 2.2 Wikipedia presence (b)
Each PG agent is matched to Wikidata by, in order:
1. **P1938** ("Project Gutenberg author ID" = agent id), via one SPARQL query: 3,020 agents.
2. The agent's **Wikipedia `pgterms:webpage`**, resolved to `wikibase_item`: 51 agents.
3. **Name + years.** `wbsearchentities` on "First Last", accepted only if the item is human (P31=Q5), P569 is within ±1 year of the PG birth year, and P570 is within ±1 year of the PG death year when both are known: 136 of 458 candidates. Agents without a PG birth year are never name-matched.

Of the 4,016 corpus-relevant agents, 3,207 match and 809 do not. 92% of works have a sitelinks value (E 93%,
M 94%, L 92%).

`sitelinks` is the number of **Wikipedia language editions** (`<lang>wiki` keys, not Commons, Wikisource, Wikiquote and so on)
for the author's item. At group level it is the **maximum over the group's agents**, so a pseudonym inherits the real
person's value. Only **human** items count: corporate bodies such as "New York Public Library" (58) and collective
pseudonyms (Wikidata P1938 for "Victor Appleton" points at the *Tom Swift* item) are dropped. Unmatched groups
get no value and are treated as 0 for the binary.

### 2.3 Binary split: `canonical`
> **canonical ⇔ the author group's sitelinks ≥ K = 30, and the group is not a publisher's house name** (the Stratemeyer
> Syndicate, or a PG agent labelled "(House name)"). Everything else is "popular / mass-market or uncanonised".

**Choosing K.**
- K = 30 sits at about the 95th percentile of author groups (median 3, 90th percentile 19, 95th 34, 99th 93). It is the smallest round value that passes the coordinator's a-priori sanity list.
- At K = 20, Alger (28), Ballantyne (23), Braddon (22) and Yonge (21) would count as canonical.
- Alger's sitelinks reflect the "Horatio Alger myth" as an American cultural idiom, not literary prestige. That is a known weakness of a fame signal. **K was therefore chosen knowing where the sanity authors fall. It is not a blind threshold.** Because of this, the K-sensitivity below is part of the registered report.

**Sanity list (all pass).**
- Canonical: Austen 145, Eliot 92, Dickens 177, Hardy 92, H. James 76, and also Scott 98, Stevenson 101, Collins 52, Haggard 53, Trollope 41.
- Popular: Alger 28, Fenn 4, Henty 11, the Stratemeyer group (house name; max human sitelinks 10), Le Queux 8, Oppenheim 14.
- Borderline but popular at K = 30: Ballantyne 23, Braddon 22, Yonge 21, Mrs Oliphant 18. The literary review's "canonical" smoke-test list included Oliphant and Yonge, so this measure is stricter than that list.

**Face validity: 30 random author groups per side** (seed 20261102, `--report`):
- *Canonical (193 groups):*
  - Dickens 177, Woodrow Wilson 148, Theodore Roosevelt 146, Conan Doyle 122, Lewis Carroll 111, Burns 89, Thoreau 88;
  - Bram Stoker 83, E. R. Burroughs 74, Gertrude Stein 62, Spyri 62, Sherwood Anderson 54, Stephen Crane 51;
  - Matthew Arnold 50, Thornton Wilder 50, Dos Passos 48, e. e. cummings 47, Margaret Fuller 44, Sousa 42;
  - Ellen G. White 40, Arnold Bennett 39, E. Nesbit 39, Saki 38, Zane Grey 36, J. J. Astor 36, Orczy 36, Mencken 34;
  - J. W. Campbell 32, Emma Lazarus 32, Arthur Ransome 30.
- *Popular / other (3,735 groups):*
  - Edmond Hamilton 21, C. G. Leland 16, George Ade 13, J. F. Clarke 8, S. R. Crockett 7, H. N. Brailsford 7;
  - Hesba Stretton 6, Charles Egbert Craddock 4, F. Hardman 3, T. G. Marquis 3, Mrs Loudon 2, A. J. Church 2, E. S. Barrett 2;
  - "S. W." 1, C. Sotheran 1, Ridgwell Cullum 1, J. E. Le Rossignol 1, W. A. Leahy 0, L. R. Smith 0, R. P. Halleck 0;
  - M. Mather 0, W. J. Ferrar 0, C. C. Goodwin 0;
  - unmatched: J. Bowes, M. Douie, C. Shea, F. B. Harrison, L. J. Hamilton, M. Saltus, K. Stokes.

**Reading.**
- The popular side looks right: series, religious-tract, regional and pulp writers.
- The canonical side is "famous person", not "canonical novelist". Presidents, Sousa, Astor and Ellen G. White are famous for non-fiction or non-literary reasons. Each such group has 1 work in the corpus, so the work-level effect is small, but it is a limitation.
- Pulp and genre fame (Burroughs, Zane Grey, Orczy) is also canonical by this measure. The measure therefore captures *lasting cultural visibility*, which is closer to Bourdieu's consecration than to syllabus canon. It should be described that way.

**External check against ELTeC-eng `reprint-count`** (author groups matched by name and birth year, 50 groups). Of the
19 ELTeC "high" authors, 15 are canonical. Of the 31 "low" authors, 25 are popular. Agreement is 80%. ELTeC is used
only for this validation, and `eltec_reprint` is stored in canon.parquet. (c) has no verifiable public
Norton/Oxford list in machine-readable form, so it is not used.

**Sensitivity analyses (registered).**
- `canonical_dl`: top-decile work downloads, excluding house names. It overlaps poorly with `canonical`: 652 works are both, 1,344 are sitelinks-only and 877 are downloads-only. Downloads favour a few blockbusters and children's classics.
- K ∈ {20, 25, 40, 50}. Canonical share of primary_v2 works:

| K | E conf | E disc | M conf | M disc | L conf | L disc |
|---|---|---|---|---|---|---|
| 20 | .373 | .472 | .237 | .251 | .158 | .127 |
| 25 | .343 | .444 | .196 | .205 | .117 | .104 |
| **30** | **.333** | **.333** | **.182** | **.184** | **.092** | **.084** |
| 40 | .333 | .315 | .105 | .162 | .062 | .063 |
| 50 | .265 | .259 | .094 | .106 | .054 | .054 |

### 2.4 Continuous score: `canon_score`
`canon_score = 0.5 · pct_rank(log1p(sitelinks)) + 0.5 · pct_rank(log1p(downloads))`. Both percentile ranks are taken over all
15,511 corpus works, and missing sitelinks count as 0. House-name works are capped at 0.5. The score lies in (0, 1].

### 2.5 Canon share by decade (all works, metadata only, K = 30)

| Decade | 1800 | 1810 | 1820 | 1830 | 1840 | 1850 | 1860 | 1870 | 1880 | 1890 | 1900 | 1910 | 1920 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Discovery (n) | .50 (14) | .65 (31) | .54 (48) | .31 (71) | .23 (88) | .31 (199) | .26 (219) | .22 (381) | .13 (652) | .11 (1405) | .10 (1780) | .07 (2293) | .13 (1202) |
| Confirmation (n) | .00 (10) | .08 (13) | .38 (34) | .53 (62) | .51 (83) | .20 (202) | .23 (275) | .16 (361) | .12 (466) | .10 (999) | .11 (1537) | .13 (1844) | .13 (1110) |

The literary review's composition story holds on a proper covariate.
- The canonical share falls from about 1/3–1/2 before 1850 to about 1/10 after 1885, in both halves.
- The halves differ sharply decade by decade before 1850 (small n), but they agree at era level: E .333 and .333 in the primary set.

## 3. Primary-population flags (works_v2)

| Column | Definition |
|---|---|
| `era` | E 1800–1849, M 1850–1884, L 1885–1929 by `year`; else null |
| `historical_setting` | genre = historical; **or**, whatever the genre precedence, LCSH "Historical fiction" or "Biographical fiction"; or an LCSH "X -- History -- &lt;period&gt; -- Fiction" heading whose period ends ≥ 25 years before the work's year (the same `genre._history_period` rule, where a heading with no period counts); or the PG "Historical Novels/Fiction" shelf. 2,711 works (genre alone gives 1,505) |
| `juvenile` | genre = juvenile, or an LCSH juvenile heading: 4,684 |
| `date_verified` | null placeholder, filled by the early-date verification task |
| `wc_keep` | `workcheck_keep.keep` (null = no workcheck run); 857 are False |
| `primary_v2` | `in_primary_cap AND NOT historical_setting AND wc_keep is not False`: 8,949 works |
| `in_primary_cap_v2`, `primary_v2_capv2` | the same seeded 5-per-author-decade cap, applied to `author_group` (sensitivity; v1's cap is porous across pseudonyms): 8,725 works |

**primary_v2 counts, era × split_v2 × canonical**, with primary_v2_capv2 in parentheses where it differs:

| Era | Split | popular | canonical | all |
|---|---|---|---|---|
| E | confirmation | 68 | 34 | 102 |
| E | discovery | 72 | 36 | 108 |
| M | confirmation | 446 | 99 | 545 |
| M | discovery | 438 | 99 | 537 |
| L | confirmation | 3,179 (3,187) | 322 | 3,501 (3,509) |
| L | discovery | 3,700 (3,468) | 341 | 4,041 (3,809) |

The E era has about 34–36 canonical works per half, so a canon × era interaction in E rests on roughly 70 works.

## 4. Effects on the labeling queue

Coordinator D1 `jobs` status for split = confirmation (2026-11-02), joined to the local shard passage ids:

| Wave | Status | Passages | Already labelled | In moved works | Moved and labelled |
|---|---|---|---|---|---|
| v09b_w02_conf_rand_a | done (16 jobs) | 6,400 | 6,400 | 315 | **315** |
| v09b_w02_conf_rand_a | queued (200 jobs; 1 with a 368-passage partial) | 79,916 | 368 | 3,980 | **22** |
| v09b_w04_conf_enrich | queued | 113,379 | 0 | 5,588 | 0 |
| v09b_w06_conf_rand_b | queued | 87,516 | 0 | 4,383 | 0 |
| v09b_w07_cloze | queued | 22,167 | 0 | 1,127 | 0 |

Older Confirmation waves (`w0x_*`, `v09_*`) are closed with no results. Every live Confirmation shard contains some
moved passages. Per-job counts are in `data/work/split_v2_queue_report.csv`.

**Consequences.**
- The **337** already-labelled moved passages (315 + 22) are now Discovery data.
- The coordinator still files them under split = confirmation, so `/v1/admin/results` refuses them while the seal holds. To use them before unsealing, re-issue those passages (or their works) as a Discovery wave and treat the sealed copies as never read. Otherwise they become readable at the unseal.
- The **audit draw must use split_v2**: drop moved passages from the Confirmation frame. They are 4,295 of the 86,316 w02 passages.
- Sync and analysis code should call `pipeline.split_v2_map.SplitV2.load().reassign(df)`. It handles both `pg<id>_p<n>` passage ids and `w<id>_cz<n>` cloze ids.

## 5. Limitations
- Sitelinks measure present-day global fame. They reward Americana, pulp and non-fiction celebrity, and they favour authors with translated works.
- Downloads are a 30-day present-day signal.
- Neither is a historical-reception measure. Underwood-style periodical-review prestige would be the stronger next step.
- The author agent is the first-listed Author only. Co-authors and illustrators create no edges.
- E1 trusts PG's see-also links, including the long Nick Carter chain.
