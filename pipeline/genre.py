"""Rule-based genre classes from LCSH Subjects and PG Bookshelves (plan §4.1, prereg §4).

Output: data/work/genre.parquet  (work_id, genre, genre_rule)

Metadata only: no labels are read, so the mapping is safe to run on both splits.

Classes (8):
  juvenile, collection, sensation_mystery, historical, adventure,
  domestic_realist, romance, other

Precedence (first matching rule wins; documented in docs/pilot_analysis_1.md §1):
  Tier 0  nonfiction_suspect: no fiction cue anywhere in Subjects/Bookshelves -> other.
          (workcheck will drop these; tagging them keeps them out of genre cells.)
  Tier 1  LCSH genre/form headings, in this order:
          juvenile > collection > sensation_mystery > historical > adventure
          > domestic_realist (form headings) > romance > other (sci-fi, humour, ...)
  Tier 2  PG bookshelves, same order (shelves are coarser and noisier than LCSH,
          so they only decide when LCSH names no genre).
  Tier 3  LCSH topical subjects typical of domestic/realist fiction
          (social life and customs, families, marriage, man-woman relationships, ...).
  Tier 4  residual: any other fiction -> domestic_realist ("general fiction"),
          tagged genre_rule='residual_general_fiction' so it can be split out.

Historical rule: an LCSH "... -- History -- <period> -- Fiction" heading counts as
historical only when the period ends >= 25 years before the work's year (otherwise
the novel is about its own time, e.g. an 1863 Civil War story or a 1917 war novel;
those fall through to adventure if a war heading is present).
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WORKS = ROOT / "data/work/works.parquet"
OUT = ROOT / "data/work/genre.parquet"

GENRES = ["juvenile", "collection", "sensation_mystery", "historical", "adventure",
          "domestic_realist", "romance", "other"]

I = re.I
# Tier 1: LCSH genre/form headings (matched against the full Subjects string).
LCSH_RULES: list[tuple[str, str, re.Pattern]] = [
    ("juvenile", "lcsh_juvenile", re.compile(r"juvenile|children's stories|fairy tales|school stories|nursery", I)),
    ("collection", "lcsh_short_stories", re.compile(r"short stories", I)),
    ("sensation_mystery", "lcsh_mystery_sensation", re.compile(
        r"detective|mystery|crime|criminals|murder|spy stories|suspense|thriller|sensationalism|"
        r"gothic|ghost stories|horror|paranormal|supernatural|private investigators", I)),
    ("historical", "lcsh_historical", re.compile(r"historical fiction|biographical fiction", I)),
    ("historical", "lcsh_history_period", None),  # special-cased, see _history_period
    ("adventure", "lcsh_adventure", re.compile(
        r"adventure stories|western stories|sea stories|war stories|dime novels|frontier and pioneer|"
        r"pirates|robinsonades|hunting stories|cowboys|outlaws|shipwrecks|survival|seafaring|"
        r"explorers|voyages and travels -- fiction|world war, 1914-1918|soldiers -- fiction|"
        r"indians of north america -- fiction|gold mines|klondike", I)),
    ("domestic_realist", "lcsh_domestic_form", re.compile(
        r"domestic fiction|bildungsrom|psychological fiction|didactic fiction|political fiction|"
        r"epistolary fiction|autobiographical fiction|diary fiction|feminist fiction", I)),
    ("romance", "lcsh_love", re.compile(r"love stories|romance fiction|romantic", I)),
    ("other", "lcsh_other_genre", re.compile(
        r"science fiction|fantasy|utopia|dystopia|humorous|humor|satire|christian fiction|"
        r"religious fiction|christmas stories|allegor|fables|legends|folklore|imaginary|"
        r"future|sports stories|baseball|football|college stories", I)),
]
# Tier 2: PG bookshelves (matched against the full Bookshelves string).
SHELF_RULES: list[tuple[str, str, re.Pattern]] = [
    ("juvenile", "shelf_children", re.compile(r"children", I)),
    ("collection", "shelf_short_stories", re.compile(r"short stories", I)),
    ("sensation_mystery", "shelf_crime_mystery", re.compile(r"crime|mystery|detective|horror|gothic", I)),
    ("historical", "shelf_historical", re.compile(r"historical novels|historical fiction", I)),
    ("adventure", "shelf_adventure", re.compile(r"adventure|western|pirates|world war i|civil war", I)),
    ("romance", "shelf_romance", re.compile(r"romance", I)),
    ("other", "shelf_other_genre", re.compile(r"science-fiction|science fiction|fantasy|humour|humor|christmas", I)),
]
# Tier 3: LCSH topical subjects typical of domestic/realist novels.
TOPICAL_DOMESTIC = re.compile(
    r"social life and customs|manners and customs|families|family|marriage|married people|"
    r"man-woman relationships|courtship|young women|mothers|fathers|daughters|sisters|"
    r"social classes|country life|city and town life|villages|clergy|governesses|inheritance|"
    r"upper class|middle class|working class|poor -- fiction|wealth", I)
FICTION_CUE = re.compile(r"fiction\b|\bstories\b|\btales\b|\bromances?\b|\bnovels?\b|\bfables\b|\blegends\b", I)

_CENTURY = re.compile(r"(\d{1,2})(?:st|nd|rd|th) century", I)
_YEAR = re.compile(r"\b(1[0-9]{3})\b")


def _period_end(subject: str) -> int | None:
    """Latest year named in an LCSH period subdivision (centuries -> end year)."""
    years = [int(y) for y in _YEAR.findall(subject)]
    years += [int(c) * 100 for c in _CENTURY.findall(subject)]
    return max(years) if years else None


def _history_period(subjects: str, year: float | None) -> bool:
    for s in subjects.split(";"):
        s = s.strip().lower()
        if "-- history" not in s or not s.endswith("fiction"):
            continue
        end = _period_end(s)
        if end is None:  # "X -- History -- Fiction" with no period: treat as historical
            return True
        if year is not None and end <= year - 25:
            return True
    return False


def classify(subjects: str | None, shelves: str | None, year: float | None = None) -> tuple[str, str]:
    subj = subjects if isinstance(subjects, str) else ""
    shelf = shelves if isinstance(shelves, str) else ""
    if not FICTION_CUE.search(subj) and not FICTION_CUE.search(shelf):
        return "other", "nonfiction_suspect"
    for genre, rule, pat in LCSH_RULES:
        if pat is None:
            if _history_period(subj, year):
                return genre, rule
        elif pat.search(subj):
            return genre, rule
    for genre, rule, pat in SHELF_RULES:
        if pat.search(shelf):
            return genre, rule
    if TOPICAL_DOMESTIC.search(subj):
        return "domestic_realist", "lcsh_topical_domestic"
    return "domestic_realist", "residual_general_fiction"


def build(works: pd.DataFrame) -> pd.DataFrame:
    out = [classify(s, b, None if pd.isna(y) else float(y))
           for s, b, y in zip(works.Subjects, works.Bookshelves, works.year)]
    return pd.DataFrame({"work_id": works.work_id.values,
                         "genre": [g for g, _ in out],
                         "genre_rule": [r for _, r in out]})


def main() -> None:
    works = pd.read_parquet(WORKS, columns=["work_id", "Subjects", "Bookshelves", "year"])
    g = build(works)
    g.to_parquet(OUT, index=False)
    print(g.genre.value_counts().to_string())
    print(g.genre_rule.value_counts().to_string())
    print(f"wrote {OUT} ({len(g)} works)")


if __name__ == "__main__":
    main()
