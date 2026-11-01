# Gate log

## G0: corpus coverage (2026-10-31, evaluated on works.parquet v1)

Build results:
- 19,113 texts cleaned.
- 17,033 met length (at least 15k words).
- 151 failed quality checks.
- **15,511 works** after dedup; 2,041 editions were collapsed.
- **607,623 passages**: 369k random backbone and 238k enrichment.

| Decade | Works conf/disc | Authors conf/disc | G0 (≥60 works, ≥30 authors per half) |
|---|---|---|---|
| 1800s | 10/14 | 10/10 | fail |
| 1810s | 13/31 | 10/15 | fail |
| 1820s | 34/48 | 22/28 | fail |
| 1830s | 62/71 | 25/33 | fail (authors) |
| 1840s | 83/88 | 44/38 | pass |
| 1850s–1920s | 197–2131 | 90–722 | pass |

**Decision (pre-registered before any labels were seen):**
- The confirmatory early era is **1800–1849 pooled**: about 200–250 works and about 100 authors per half. This replaces 1800–1839.
- The late era stays 1885–1929, and the mid era is 1850–1884.
- Decade-resolution trend curves start in the **1840s**. The 1800s–1830s appear descriptively, with their CIs.
- The study window is 1800–1929, since PG coverage extends through the 1920s. Sensitivity checks truncate at 1925.
- **H2b is affected.** The railway hinge (1830s–50s) sits partly inside the thin early era. H2b becomes **1800–1849 vs 1850–1884** for DISTANCE_TRAVEL prevalence, and it is flagged as the lowest-powered confirmatory test.
- Phase 2: a HathiTrust/HTRC request for public-domain fiction from 1800–1849, to strengthen the early era.

## Date issues flagged by QA pass 2 (for the date-gold rule, 2026-11-01)
- *Tippoo Sultaun* is catalogued 1880; it was first published 1840, which moves it into the early era.
- Henry James, *The Point of View*, is catalogued 1886; it was published 1882, which moves it into the mid era.
- *Zenobia* is off by about a decade but stays in the same era.
- Wilkie Collins, *"I Say No"*, is catalogued 1860; it was published 1884 (title-page scan).
