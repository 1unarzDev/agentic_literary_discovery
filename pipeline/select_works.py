"""Select candidate English fiction works 1800-1925 from the PG catalog + pg-dates.

Outputs:
  data/manifests/candidates_v1.parquet  (one row per PG ebook, with date provenance)
  data/manifests/rsync_files_v1.txt     (paths for rsync --files-from against gutenberg-epub)
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CAT = ROOT / "data/catalog"
OUT = ROOT / "data/manifests"

YEAR_MIN, YEAR_MAX = 1795, 1930  # margin around 1800-1925 study window
TRANSLATION_LOCC = re.compile(r"^(PA|PB|PC|PD|PF|PG|PH|PJ|PK|PL|PM|PQ|PT)")
EXCLUDE_SUBJ = re.compile(r"Poetry|Poems|Drama|Plays|Translations into English|Sermons|Essays|Juvenile poetry", re.I)
FICTION_SUBJ = re.compile(r"Fiction|Short stories|Novel|Romances|Tales|Detective and mystery stories|Adventure stories|Love stories|Ghost stories", re.I)


def parse_life(authors: str) -> tuple[float | None, float | None]:
    m = re.search(r"(\d{3,4})\??\s*-\s*(\d{3,4})", str(authors))
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r"(\d{4})-\s*(?:;|$)", str(authors))
    return (float(m.group(1)), None) if m else (None, None)


def to_year(x) -> float | None:
    try:
        v = float(str(x).strip())
        return v if 1000 < v < 2100 else None
    except ValueError:
        return None


def main() -> None:
    cat = pd.read_csv(CAT / "pg_catalog.csv")
    cat = cat[(cat.Type == "Text") & (cat.Language == "en")].copy()
    subj = cat.Subjects.fillna("")
    locc = cat.LoCC.fillna("")
    is_fic = subj.str.contains(FICTION_SUBJ) | locc.str.match(r"^(PR|PS|PZ)")
    keep = is_fic & ~locc.str.match(TRANSLATION_LOCC) & ~subj.str.contains(EXCLUDE_SUBJ)
    # "Translator" credits in Authors also indicate translation
    keep &= ~cat.Authors.fillna("").str.contains(r"\[Translator\]")
    c = cat[keep].rename(columns={"Text#": "pg_id"})

    best = pd.read_csv(CAT / "pgdates/_best-performance__LLM_first_last_gemma.csv",
                       usecols=["Book_ID", "Result"]).rename(columns={"Book_ID": "pg_id", "Result": "year_llm"})
    best["year_llm"] = best.year_llm.map(to_year)
    filt = pd.read_csv(CAT / "pgdates/Filtered_Corpus.csv",
                       usecols=["id", "ol_est", "is_mentioned_in_first_or_last_pages", "n_tokens", "super_genres"]
                       ).rename(columns={"id": "pg_id"})
    c = c.merge(best, on="pg_id", how="left").merge(filt, on="pg_id", how="left")

    life = c.Authors.map(parse_life)
    c["author_birth"] = [b for b, _ in life]
    c["author_death"] = [d for _, d in life]

    def confidence(r) -> str:
        y = r.year_llm
        if y is None or pd.isna(y):
            return "none"
        ok_life = True
        if pd.notna(r.author_birth) and y < r.author_birth + 12:
            ok_life = False
        if pd.notna(r.author_death) and y > r.author_death + 10:
            ok_life = False
        if not ok_life:
            return "conflict"
        ol_agree = pd.notna(r.ol_est) and abs(float(r.ol_est) - y) <= 5
        if r.is_mentioned_in_first_or_last_pages == 1 and ol_agree:
            return "high"
        if r.is_mentioned_in_first_or_last_pages == 1 or ol_agree:
            return "medium"
        return "low"

    c["date_confidence"] = c.apply(confidence, axis=1)
    c["year"] = c.year_llm
    c = c[c.year.between(YEAR_MIN, YEAR_MAX) & c.date_confidence.isin(["high", "medium", "low"])]
    c["origin_locc"] = locc.reindex(c.index).str[:2].map({"PR": "UK", "PS": "US"}).fillna("unknown")
    c["decade"] = (c.year // 10 * 10).astype(int)
    OUT.mkdir(parents=True, exist_ok=True)
    c.to_parquet(OUT / "candidates_v1.parquet", index=False)
    with open(OUT / "rsync_files_v1.txt", "w", encoding="utf-8", newline="\n") as f:
        for i in sorted(c.pg_id.astype(int)):
            f.write(f"{i}/pg{i}.txt\n")
    print(len(c), "candidate works")
    print(c.date_confidence.value_counts().to_string())
    print(pd.crosstab(c.decade, c.origin_locc).to_string())


if __name__ == "__main__":
    main()
