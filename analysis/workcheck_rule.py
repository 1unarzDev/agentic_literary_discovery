"""Turn workcheck results (+ catalog metadata) into data/work/workcheck_keep.parquet.

Output columns: work_id, keep (nullable bool), reason, form_model, catalog_signal, model_translation.
pipeline/make_jobs.py --exclude-from-workcheck drops only rows with keep == False;
keep = None means "no usable workcheck result yet" (unknown), and such works are NOT excluded.

Rule (QA pass 1, docs/qa/workcheck_pass_1.md). The workcheck model (qwen3.5:4b, prompt v0.5)
labels ~all works novel_or_novella with a constant confidence of 0.95, so:
  * its `confidence` is NOT used (no information; thresholds impossible);
  * its `is_translation` is NOT used to exclude (0/5 precision in pass 1); only a catalog
    translator credit / "Translations" subject excludes;
  * a model non-fiction call excludes only when the catalog has no fiction heading
    (protects real novels from false exclusion);
  * catalog subject headings that are clearly non-fiction / verse exclude even when the model says
    novel (the model missed 10/12 non-fiction works).
Kept forms: novel_or_novella, story_collection, single_short_story (and model 'other' if the
catalog says fiction).

usage: uv run --with pandas,duckdb,pyarrow python -I analysis/workcheck_rule.py [--eval docs/qa/workcheck_pass_1_ref.csv]
       [--catalog-fallback] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data/work"
OUT = WORK / "workcheck_keep.parquet"

KEEP_FORMS = {"novel_or_novella", "story_collection", "single_short_story"}
NONFIC_FORMS = {"essay_or_nonfiction", "history_or_biography", "travel", "religious", "drama", "verse"}

# --- catalog heuristics (LCSH subject headings are ';'-separated; Bookshelves are PG categories)
FIC = re.compile(r"(?<!\w)[Ff]iction(?!al)|[Ss]tories|\bTales\b|[Ff]airy tales|\bLegends\b|Folklore|Dime novels"
                 r"|Penny dreadfuls|Bildungsromans|Satire|Romances(?!.*History and criticism)|Fables|Parables|Novels")
NON = re.compile(r"History and criticism|Biography|Description and travel|Juvenile literature|Authorship|Criticism"
                 r"|\bletters\b|Correspondence|Sermons|Essays|Addresses|Speeches|Handbooks|Textbooks|Etiquette"
                 r"|Cookery|Diaries|Memoirs|Voyages and travels(?!.*[Ff]iction)|-- Knowledge --|[Ii]n literature\b")
WEAK_NON = re.compile(r"Juvenile literature")  # LoC uses it for children's non-fiction, but also animal/moral tales
VERSE = re.compile(r"Poetry|Poems|Ballads|Verse|Drama(?!.*[Ff]iction)|Plays\b|Songs")
COLL = re.compile(r"Short stories|Children's stories|\bTales\b|Legends|Folklore|Fairy tales|Anthologies")
FSHELF = re.compile(r"Category: Novels|Category: Short Stories")
NSHELF = re.compile(r"Biographies|Poetry|Essays, Letters|Travel Writing|History - |Philosophy|Religion|Science"
                    r"|Politics|Drama|Cooking|Art\b")
TRANS = re.compile(r"[Tt]ranslat")


def _heads(s) -> list[str]:
    return [h.strip() for h in str(s or "").split(";") if h.strip()]


def catalog_signal(subjects, shelves, title) -> str:
    """fiction | collection | mixed | fiction_shelf | unclear | nonfiction_shelf | nonfiction | verse"""
    hs = _heads(subjects)
    shelves, title = str(shelves or ""), str(title or "")
    fic = [h for h in hs if FIC.search(h) and not NON.search(h) and not VERSE.search(h)]
    non = [h for h in hs if NON.search(h) and not FIC.search(h)]
    ver = [h for h in hs if VERSE.search(h) and not FIC.search(h)]
    coll = (any(COLL.search(h) for h in hs) or bool(re.search(r"[Ss]tories|\bTales\b|Sketches", title))
            or "Short Stories" in shelves)
    fshelf, nshelf = bool(FSHELF.search(shelves)), bool(NSHELF.search(shelves))
    if fic and not (non or ver):
        return "collection" if coll else "fiction"
    if (non or ver) and not fic:
        if non and all(WEAK_NON.search(h) for h in non) and not ver and fshelf:
            return "mixed"  # e.g. juvenile "literature" shelved as Novels / Short Stories
        return "verse" if ver and not non else "nonfiction"
    if fic:
        return "mixed"
    if fshelf and not nshelf:
        return "fiction_shelf"
    if nshelf and not fshelf:
        return "nonfiction_shelf"
    return "unclear"


def catalog_translation(subjects, authors) -> bool:
    return bool(TRANS.search(str(subjects or ""))) or "[Translator]" in str(authors or "")


def decide(form: str | None, valid, model_tr, cat: str, cat_tr: bool,
           catalog_fallback: bool = False) -> tuple[object, str]:
    if form is None:
        if catalog_fallback and (cat_tr or cat in ("nonfiction", "verse", "nonfiction_shelf")):
            return False, "no_workcheck;catalog_" + ("translation" if cat_tr else cat)
        return None, "no_workcheck"
    if valid is False:
        return None, "schema_fail"
    note = ";model_translation_ignored" if model_tr and not cat_tr else ""
    if cat_tr:
        return False, "catalog_translation"
    if cat in ("nonfiction", "verse", "nonfiction_shelf"):
        return False, f"catalog_{cat}" + ("+model" if form in NONFIC_FORMS else "")
    if form in NONFIC_FORMS:
        if cat in ("fiction", "collection", "fiction_shelf"):
            return True, f"model_{form}_overridden_by_catalog_{cat}" + note
        return False, f"model_{form}+catalog_{cat}"
    if form in KEEP_FORMS:
        return True, f"{form};catalog_{cat}" + note
    # model 'other' (or unknown enum)
    if cat in ("fiction", "collection", "fiction_shelf", "mixed"):
        return True, f"model_{form};catalog_{cat}" + note
    return False, f"model_{form}+catalog_{cat}"


def build(catalog_fallback: bool = False) -> pd.DataFrame:
    w = pd.read_parquet(WORK / "works.parquet",
                        columns=["work_id", "Title", "Authors", "Subjects", "Bookshelves", "split", "decade"])
    w = w[w.decade.between(1800, 1920)].copy()  # catalog rule applies to both splits (metadata is not sealed)
    con = duckdb.connect(str(WORK / "ald.duckdb"), read_only=True)
    r = con.execute("SELECT passage_id, valid_schema, output_json, created FROM results WHERE stage='workcheck'").df()
    con.close()
    r = r.sort_values("created").drop_duplicates("passage_id", keep="last")  # newest pin wins
    r["work_id"] = r.passage_id.str.replace(r"_wc$", "", regex=True)
    outs = [json.loads(x) if x else None for x in r.output_json]
    r["form_model"] = [(o or {}).get("form") if isinstance(o, dict) else None for o in outs]
    r["model_translation"] = [bool((o or {}).get("is_translation")) if isinstance(o, dict) else None for o in outs]
    m = w.merge(r[["work_id", "valid_schema", "form_model", "model_translation"]], on="work_id", how="left")
    m["catalog_signal"] = [catalog_signal(s, b, t) for s, b, t in zip(m.Subjects, m.Bookshelves, m.Title)]
    cat_tr = [catalog_translation(s, a) for s, a in zip(m.Subjects, m.Authors)]
    dec = [decide(f if isinstance(f, str) else None, v if v is not None and v == v else None, mt, c, ct,
                  catalog_fallback)
           for f, v, mt, c, ct in zip(m.form_model, m.valid_schema, m.model_translation, m.catalog_signal, cat_tr)]
    m["keep"] = pd.array([d[0] for d in dec], dtype="boolean")
    m["reason"] = [d[1] for d in dec]
    return m[["work_id", "keep", "reason", "form_model", "catalog_signal", "model_translation"]]


def evaluate(out: pd.DataFrame, ref_path: str) -> None:
    ref = pd.read_csv(ref_path)
    e = ref.merge(out, on="work_id")
    e = e[e.keep_ref != "borderline"]
    truth = e.keep_ref == "yes"
    pred = e.keep.astype("boolean")
    print(f"eval on {len(e)} works (borderline excluded):")
    print("  real-fiction wrongly excluded:", int((truth & (pred == False)).sum()), "/", int(truth.sum()))  # noqa: E712
    print("  non-fiction wrongly kept:     ", int((~truth & (pred == True)).sum()), "/", int((~truth).sum()))  # noqa: E712
    model_novel = e.form_model.isin(KEEP_FORMS)
    print("  [model alone] non-fiction labelled keep-form:", int((~truth & model_novel).sum()), "/", int((~truth).sum()),
          "| fiction labelled non-fiction:", int((truth & ~model_novel).sum()), "/", int(truth.sum()))
    print(pd.crosstab(e.keep_ref, e.reason.str.split(";").str[0]).T.to_string())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", default=None, help="reference CSV (work_id, keep_ref yes/no/borderline)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--catalog-fallback", action="store_true",
                    help="works with no workcheck result: exclude on clear catalog non-fiction/verse/translation "
                         "(default: keep=None, unknown)")
    a = ap.parse_args()
    out = build(a.catalog_fallback)
    print("works:", len(out), "| keep:", out.keep.value_counts(dropna=False).to_dict())
    print(out.reason.str.split(";").str[0].value_counts().head(20).to_string())
    if a.eval:
        evaluate(out, a.eval)
    if not a.dry_run:
        out.to_parquet(OUT, index=False)
        print("wrote", OUT)


if __name__ == "__main__":
    main()
