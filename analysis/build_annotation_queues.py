"""Build the human-annotation queues for the Worker's /annotate UI.

SEAL: the builder never reads Confirmation model labels. The labels file is read with a row filter
that keeps Discovery passages only (Confirmation rows are dropped by id before any label column is
loaded); the Confirmation audit pool is built from METADATA only (passages.parquet + works +
genre.parquet) and drawn with select_annotation.draw_audit_metadata (prereg v0.5: era(year) x genre
[x canonical when a `canonical` column is present in works / works_v2], metadata_only). N_cell is never
printed or written to the summary; design_summary.json carries cell_table_hash(frame) instead.

Split: data/work/works_v2.parquet when it exists: split_v2, author identity = author_group (carried in
the `author_key` column downstream), Confirmation pool restricted to primary_v2 works, and passages
reassigned with pipeline.split_v2_map.SplitV2 (moved passages follow their work's split_v2). Otherwise
the current works.parquet split with a loud warning in the summary. canonical comes from
data/work/canon.parquet (strata era x genre x canonical; --no-canonical for era x genre).

Roles / queues (parameters recorded in design_summary.json; final numbers fixed in prereg v0.5):
  REVIEW    the 60 practice/cert/retake passages for the expert reader (expert1) to review and
            adjudicate (set "review", different opaque item ids: salt "review:"). Emitted only by the
            `practice` subcommand (practice_items.json); queues.parquet records them, ann_items.json does not,
            so expert1's ann_items.json entries are exactly their audit items (offline export-expert).
  PRACTICE / CERT / RETAKE  20 + 20 + 20 Discovery items with references, for the peers only.
  TEACHING  ~60 Discovery items (model-label prototypes + boundary cases) for the teaching annotator.
  AUDIT     draw_audit_metadata(pool_conf minus teaching authors, rng, n_target) (legacy fallback:
            draw_audit(..., group_col=--group-col)),
            audit.parquet + audit_frame.parquet persisted exactly as returned (+ expert columns below).
            Every audit item is dealt to exactly one peer, so no role below changes pi.
              deal      within each era shuffled and dealt round-robin to the peers, offset carried
                        across eras (totals differ by <= 1)
              overlap   ~overlap_frac of the audit per era gets a second, randomly chosen peer
                        (least-loaded first); partner = the other peer
              expert    NESTED stratified subsample: within each audit cell a seeded SRS of
                        n_e = floor(expert_frac * n_cell + 0.5) items (>= 1 when n_cell >= 2), labelled by
                        expert1 in addition to their peer; audit.parquet / queues.parquet carry
                        pi_expert_given_audit = n_e / n_cell (data/ only; per-cell numbers never printed).
                        Expert rows: role "expert", partner = the dealt peer.
              teacher   n_teacher items from the expert subsample, random within era (3/3/2), also
                        labelled by the teacher (descriptive only; role "teacher" on the teacher's rows)
            No adjudication of audit labels.

usage:
  uv run python -I analysis/build_annotation_queues.py practice      # practice/cert/retake + review items
  uv run python -I analysis/build_annotation_queues.py build DISCOVERY_LABELS.parquet [--alt ALT.parquet]
        [--annotators student,peer1,peer2,peer3] [--expert-reader expert1] [--teacher teacher]
        [--n-target 1800] [--group-col COL (legacy)] [--overlap-frac 0.10] [--expert-frac 0.5]
        [--n-teacher 8] [--n-teaching 60] [--teaching-annotator student]
        [--works ...] [--works-v2 ...] [--genre ...] [--canon ...] [--no-canonical] [--passages ...] [--out DIR]

Uploaded items carry ONLY item_id, passage_id, text, ctx_before, ctx_after, set, assign (+ reference
for practice/cert/retake/review): never model labels, title, author, date or decade.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import analysis.select_annotation as sa  # noqa: E402
from analysis.select_annotation import DOMAINS, SEED, draw_audit, era, item_id  # noqa: E402

HAS_METADATA_DRAW = hasattr(sa, "draw_audit_metadata")  # registered v0.5 seal-safe draw


def era_of_year(year) -> np.ndarray:
    """Audit-era labels: select_annotation.era_by_year (v0.5, year cuts) when available, else decade eras."""
    if hasattr(sa, "era_by_year"):
        return sa.era_by_year(np.asarray(year, dtype=float))
    return np.array([era(int(y // 10 * 10)) for y in np.asarray(year, dtype=float)], dtype=object)


def cell_table_hash(frame: pd.DataFrame) -> str:
    if hasattr(sa, "cell_table_hash"):
        return sa.cell_table_hash(frame)
    t = frame.groupby("audit_cell").agg(N=("passage_id", "size"), pi=("pi_audit", "first")).reset_index()
    return hashlib.sha256(t.sort_values("audit_cell").to_csv(index=False).encode()).hexdigest()

OUT = ROOT / "data/work/annotation"
PASSAGES = ROOT / "data/work/passages.parquet"
WORKS = ROOT / "data/work/works.parquet"
WORKS_V2 = ROOT / "data/work/works_v2.parquet"
GENRE = ROOT / "data/work/genre.parquet"
CANON = ROOT / "data/work/canon.parquet"
PRACTICE_REF = OUT / "practice_ref.json"
DEFAULT_ANNOTATORS = ["student", "peer1", "peer2", "peer3"]
ERA_ORDER = ["E_1800_1849", "M_1850_1884", "L_1885_1929", "early_1800_1849", "mid_1850_1884", "late_1885_1920"]
CERT_SETS = ("practice", "cert", "retake")
ITEM_KEYS = ("item_id", "passage_id", "text", "ctx_before", "ctx_after", "set", "assign")
REF_KEYS = ("has_obstacle", "domain", "locus", "failure_cause")
TEXT_COLS = ["text", "ctx_before", "ctx_after"]
QUEUE_COLS = ["annotator", "item_id", "passage_id", "set", "role", "partner", "era"]
ROLES = ["review", *CERT_SETS, "teaching", "teacher", "expert", "overlap", "single"]


# ------------------------------------------------------------------ helpers
def _s(x) -> str:
    return "" if x is None or (isinstance(x, float) and np.isnan(x)) else str(x)


def _doms(x) -> list:
    return [] if x is None or (isinstance(x, float) and np.isnan(x)) else list(x)


def review_item_id(pid: str) -> str:
    """Opaque id for the expert's review copy of a practice/cert/retake passage (ids are global)."""
    return "it_" + hashlib.sha256(f"{SEED}:review:{pid}".encode()).hexdigest()[:12]


def eras_in(values) -> list[str]:
    """Distinct era labels in chronological order."""
    u = set(pd.Series(values).dropna())
    return [e for e in ERA_ORDER if e in u] + sorted(u - set(ERA_ORDER))


def era_quota(n: int, avail: dict[str, int], eras: list[str] | None = None) -> dict[str, int]:
    """Split n over the eras as evenly as possible (remainder to the earlier eras: 8 -> 3/3/2), capped
    by availability, with any shortfall re-dealt to eras that still have items."""
    ERAS = eras or eras_in(list(avail))
    q = {e: n // len(ERAS) + (1 if i < n % len(ERAS) else 0) for i, e in enumerate(ERAS)}
    q = {e: min(v, avail.get(e, 0)) for e, v in q.items()}
    short = n - sum(q.values())
    while short > 0:
        spare = [e for e in ERAS if avail.get(e, 0) > q[e]]
        if not spare:
            break
        for e in spare:
            if short == 0:
                break
            q[e] += 1
            short -= 1
    return q


def sample_by_era(df: pd.DataFrame, n: int, rng: np.random.Generator, eras: list[str]) -> list[str]:
    """Era-balanced simple random sample of passage_ids (within-era SRS)."""
    ERAS = eras
    q = era_quota(n, df.era.value_counts().to_dict(), eras)
    out = []
    for e in ERAS:
        ids = np.sort(df.loc[df.era == e, "passage_id"].values)
        if q[e]:
            out += [str(x) for x in rng.choice(ids, size=q[e], replace=False)]
    return out


def read_text(passages_path: Path, ids: list[str]) -> pd.DataFrame:
    return pd.read_parquet(passages_path, columns=["passage_id", *TEXT_COLS], filters=[("passage_id", "in", list(ids))])


# ------------------------------------------------------------------ split / inputs (metadata only)
@dataclass
class SplitInfo:
    """Resolved split + author identity per work, and the passage-level reassignment.

    v2 (works_v2.parquet present): split = split_v2, author identity = author_group (stored in the
    `author_key` column so every downstream use, including draw_audit's author filter, sees it),
    primary = primary_v2; passages are reassigned with pipeline.split_v2_map.SplitV2 (by pg id), so
    passages of moved works follow their work's split_v2. v1 fallback: works.parquet split/author_key."""
    works: pd.DataFrame                      # work_id, decade, year, split, author_key, primary
    mapper: object | None = None             # SplitV2 or None
    warning: str | None = None
    source: str = "works.split (OLD)"
    author_source: str = "works.author_key (OLD)"

    def assign(self, df: pd.DataFrame) -> pd.DataFrame:
        """Passage-level frame (passage_id [, work_id]) -> + work_id, split (resolved)."""
        out = df.drop(columns=[c for c in ("split",) if c in df])
        if self.mapper is not None:
            r = self.mapper.reassign(out[["passage_id"]])
            out = out.drop(columns=[c for c in ("work_id",) if c in out])
            out["work_id"] = r.work_id_v2.values
            out["split"] = r.split_v2.values
            return out
        if "work_id" not in out:
            raise ValueError("v1 split needs a work_id column")
        return out.merge(self.works[["work_id", "split"]], on="work_id", how="left")


def resolve_works(works: pd.DataFrame, works_v2: pd.DataFrame | None, mapper=None) -> SplitInfo:
    w = works[[c for c in ("work_id", "decade", "year", "split", "author_key") if c in works]].copy()
    if "year" not in w:
        w["year"] = w.decade + 5.0
    if works_v2 is None:
        return SplitInfo(w.assign(primary=True), None,
                         "WARNING: data/work/works_v2.parquet not found; using the OLD works.parquet split and "
                         "author_key. Re-run once split_v2 exists.")
    need = {"work_id", "split_v2", "author_group"}
    if need - set(works_v2):
        raise SystemExit(f"works_v2 lacks {need - set(works_v2)}")
    v2 = works_v2[["work_id", "split_v2", "author_group",
                   *(["primary_v2"] if "primary_v2" in works_v2 else []),
                   *[c for c in ("decade", "year") if c in works_v2]]]
    w = w.drop(columns=[c for c in ("split", "author_key", "decade", "year") if c in w and (c in v2 or c in ("split", "author_key"))])
    w = w.merge(v2, on="work_id", how="right")
    if "year" not in w:
        w["year"] = w.decade + 5.0
    w = w.rename(columns={"split_v2": "split", "author_group": "author_key"})
    w["primary"] = w.pop("primary_v2").fillna(False).astype(bool) if "primary_v2" in w else True
    if mapper is None:
        from pipeline.split_v2_map import SplitV2
        cols = [c for c in ("pg_id", "work_id", "split", "split_v2") if c in works_v2]
        mapper = SplitV2.from_frame(works_v2[cols]) if len(cols) == 4 else None
    return SplitInfo(w, mapper, None, "works_v2.split_v2 (+ split_v2_map passage reassignment)"
                     if mapper is not None else "works_v2.split_v2 (by work_id)", "works_v2.author_group")


def confirmation_pool(passages: pd.DataFrame, split: SplitInfo, genre: pd.DataFrame | None,
                      canon: pd.DataFrame | None = None, group_col: str = "genre") -> pd.DataFrame:
    """Confirmation random-stratum pool from metadata only (no labels): resolved split == confirmation,
    primary works only (primary_v2), stratum random. Columns: passage_id, work_id, author_key (=
    author_group under v2), decade, year, era, split, stratum, genre [, canonical]."""
    p = split.assign(passages[["passage_id", "work_id", "stratum"]])
    p = p[(p.split == "confirmation") & (p.stratum == "random")]
    p = p.drop(columns="split").merge(split.works, on="work_id", how="inner")
    p = p[p.primary.astype(bool)].drop(columns="primary").copy()
    p["era"] = era_of_year(p.year.values)
    if genre is not None:
        p = p.merge(genre[["work_id", "genre"]], on="work_id", how="left")
        p["genre"] = p.genre.fillna("unknown")
    if canon is not None:
        p = p.merge(canon[["work_id", "canonical"]], on="work_id", how="left")
        p["canonical"] = p.canonical.astype("boolean").fillna(False).astype(bool)
    if group_col not in p:
        raise SystemExit(f"--group-col {group_col!r} is not a metadata column of the pool ({list(p.columns)})")
    p[group_col] = p[group_col].astype(str)
    return p.reset_index(drop=True)


def read_discovery_labels(path: Path, split: SplitInfo, passage_work: pd.DataFrame | None = None) -> tuple[pd.DataFrame, int]:
    """Read ONLY Discovery rows of a labels file. Rows are classified from passage_id / work_id alone
    (resolved split), then read back with a parquet row filter, so Confirmation label columns are never loaded."""
    cols = pq.ParquetFile(path).schema_arrow.names
    ids = pd.read_parquet(path, columns=[c for c in ("passage_id", "work_id") if c in cols])
    if "work_id" not in ids and split.mapper is None:
        if passage_work is None:
            raise SystemExit("labels file has no work_id; pass passages to map passage_id -> work_id")
        ids = ids.merge(passage_work, on="passage_id", how="left")
    ids = split.assign(ids)
    keep = ids[ids.split == "discovery"].passage_id
    dropped = len(ids) - len(keep)
    if len(keep):
        lab = pd.read_parquet(path, filters=[("passage_id", "in", list(keep))])
    else:
        lab = pq.ParquetFile(path).schema_arrow.empty_table().to_pandas()
    return lab, dropped


def prepare_discovery(lab: pd.DataFrame, split: SplitInfo, alt: pd.DataFrame | None = None) -> pd.DataFrame:
    """Discovery labels with resolved split / author_key (author_group) / decade / era."""
    lab = lab.drop(columns=[c for c in ("split", "author_key", "decade", "year", "canonical") if c in lab])
    lab = split.assign(lab)
    lab = lab[lab.split == "discovery"].drop(columns="split")
    lab = lab.merge(split.works.drop(columns="primary"), on="work_id", how="inner")
    lab["era"] = lab.decade.map(era)          # teaching prototypes (decade eras, as in select_annotation)
    lab["q_era"] = era_of_year(lab.year.values)  # audit-era label for queues.parquet
    if alt is not None:
        a = alt[alt.passage_id.isin(lab.passage_id)][["passage_id", "has_obstacle", "locus", "domains"]].add_prefix("alt_")
        lab = lab.merge(a, left_on="passage_id", right_on="alt_passage_id", how="left").drop(columns="alt_passage_id")
    return lab[lab.stratum.isin(["random", "enrich_comm", "enrich_mob", "enrich_dark"])].reset_index(drop=True)


# ------------------------------------------------------------------ practice / review
def parse_practice_ref(ref: dict) -> pd.DataFrame:
    """practice_ref.json -> DataFrame(passage_id, set, reference). Accepts {"practice","cert","retake"}
    and the older {"items": [...]} (= practice)."""
    lists = {s: ref.get(s, []) for s in CERT_SETS}
    if not any(lists.values()) and "items" in ref:
        lists["practice"] = ref["items"]
    rows = []
    for st, entries in lists.items():
        for it in entries:
            r = it["reference"]
            rows.append({"passage_id": it["passage_id"], "set": st,
                         "reference": {**{k: r.get(k) for k in REF_KEYS}, "rationale": it.get("rationale", "")}})
    df = pd.DataFrame(rows, columns=["passage_id", "set", "reference"])
    if df.passage_id.duplicated().any():
        raise SystemExit(f"passage_id used twice in practice_ref.json: {df[df.passage_id.duplicated()].passage_id.tolist()}")
    return df


def load_practice(ref_path: Path, passages_path: Path = PASSAGES) -> pd.DataFrame:
    df = parse_practice_ref(json.loads(Path(ref_path).read_text(encoding="utf-8")))
    df = df.merge(read_text(passages_path, df.passage_id.tolist()), on="passage_id", how="left")
    if df.text.isna().any():
        raise SystemExit(f"practice passages missing text: {df[df.text.isna()].passage_id.tolist()}")
    return df


def practice_items(practice: pd.DataFrame, annotators: list[str], expert_reader: str | None) -> list[dict]:
    """practice/cert/retake items for the peers + a review copy of each for the expert reader."""
    items = []
    for r in practice.itertuples():
        base = {"passage_id": r.passage_id, "text": _s(r.text), "ctx_before": _s(r.ctx_before),
                "ctx_after": _s(r.ctx_after)}
        items.append({"item_id": item_id(r.passage_id), **base, "set": r.set, "assign": list(annotators),
                      "reference": dict(r.reference)})
    if expert_reader:
        for r in practice.itertuples():
            items.append({"item_id": review_item_id(r.passage_id), "passage_id": r.passage_id, "text": _s(r.text),
                          "ctx_before": _s(r.ctx_before), "ctx_after": _s(r.ctx_after), "set": "review",
                          "assign": [expert_reader], "reference": dict(r.reference)})
    return items


# ------------------------------------------------------------------ teaching (Discovery labels only)
def select_teaching(lab: pd.DataFrame, n_teaching: int, exclude: set) -> pd.DataFrame:
    """Discovery-only teaching set, in the spirit of select_annotation.main, scaled to n_teaching.

    ~60% prototypes: per domain, the top-confidence early and late prototype (cross-era), then a
    seeded draw from the 12 highest-confidence agreements with verified quotes; rest boundary cases.
    """
    d = lab[(lab.split == "discovery") & ~lab.passage_id.isin(exclude)]
    has_alt = "alt_has_obstacle" in d
    per_dom = max(1, int(round(0.6 * n_teaching / len(DOMAINS))))
    proto = []
    for dom in DOMAINS:
        c = d[(d.has_obstacle == "yes") & d.domains.map(lambda x: dom in _doms(x))
              & d.quote_status.isin(["exact", "normalized"])]
        if has_alt:
            c = c[(c.alt_has_obstacle == "yes") & c.alt_domains.map(lambda x: dom in _doms(x))]
        c = c.sort_values(["confidence", "passage_id"], ascending=[False, True])
        picked = []
        for e in ("early_1800_1849", "late_1885_1920"):
            if len(picked) < per_dom:
                picked.append(c[c.era == e].head(1).assign(t_reason=f"crossera_{dom}"))
        got = pd.concat(picked) if picked else c.iloc[0:0]
        top = c[~c.passage_id.isin(got.passage_id)].head(12)
        k = min(per_dom - len(got), len(top))
        if k > 0:
            got = pd.concat([got, top.sample(n=k, random_state=SEED).assign(t_reason=f"proto_{dom}")])
        proto.append(got)
    proto = pd.concat(proto).drop_duplicates("passage_id").head(n_teaching)
    if has_alt:
        bnd = d[d.alt_has_obstacle.notna() & ((d.has_obstacle != d.alt_has_obstacle) | (d.locus != d.alt_locus))]
    else:
        bnd = d.iloc[0:0]
    bnd = pd.concat([bnd, d[d.confidence.between(0.4, 0.7)]]).drop_duplicates("passage_id")
    bnd = bnd[~bnd.passage_id.isin(proto.passage_id)].sort_values("passage_id")
    k = min(n_teaching - len(proto), len(bnd))
    bnd = bnd.sample(n=k, random_state=SEED).assign(t_reason="boundary")
    return pd.concat([proto, bnd], ignore_index=True)


# ------------------------------------------------------------------ audit roles (metadata + randomness only)
def deal(items: pd.DataFrame, annotators: list[str], rng: np.random.Generator,
         eras: list[str] | None = None) -> dict[str, str]:
    """Within each era: shuffle, then round-robin with the offset carried across eras."""
    owner, j = {}, 0
    for e in eras or eras_in(items.era):
        for pid in rng.permutation(np.sort(items.loc[items.era == e, "passage_id"].values)):
            owner[str(pid)] = annotators[j % len(annotators)]
            j += 1
    return owner


def select_overlap(items: pd.DataFrame, owner: dict, frac: float, annotators: list[str],
                   rng: np.random.Generator, eras: list[str]) -> dict[str, str]:
    """~frac of the dealt items, per era, get a second peer: random among the least-loaded other
    peers (load = dealt + second codings; ties random), so second codings and totals stay balanced."""
    if len(annotators) < 2:
        return {}
    second = {}
    load = pd.Series(list(owner.values()), dtype=object).value_counts().reindex(annotators, fill_value=0).to_dict()
    for e in eras:
        ids = np.sort(items.loc[items.era == e, "passage_id"].values)
        k = min(int(round(frac * len(ids))), len(ids))
        for pid in (rng.choice(ids, size=k, replace=False) if k else []):
            cand = [a for a in annotators if a != owner[pid]]
            m = min(load[a] for a in cand)
            b = str(rng.choice([a for a in cand if load[a] == m]))
            second[str(pid)] = b
            load[b] += 1
    return second


# ------------------------------------------------------------------ design
@dataclass
class Design:
    teaching: pd.DataFrame
    audit: pd.DataFrame
    frame: pd.DataFrame
    queues: pd.DataFrame
    items: list[dict]
    summary: dict = field(default_factory=dict)


def call_draw_audit(pool: pd.DataFrame, teaching_authors: set, rng: np.random.Generator, n_target: int,
                    group_col: str | None = None, use_canon: bool = True) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Registered v0.5 draw (select_annotation.draw_audit_metadata: era(year) x genre [x canonical],
    metadata_only) when available and group_col is None; else draw_audit with a metadata group_col.
    Teaching authors (author_key = author_group under v2) are removed from the pool first (pi = 0)."""
    pool = pool[~pool.author_key.isin(teaching_authors)]
    if HAS_METADATA_DRAW and group_col is None:
        canon = use_canon and "canonical" in pool
        if not canon:
            pool = pool.drop(columns=[c for c in ("canonical",) if c in pool])
        kw = {"use_canon": canon} if "use_canon" in inspect.signature(sa.draw_audit_metadata).parameters else {}
        a, f = sa.draw_audit_metadata(pool, rng, n_target, **kw)
        return a, f, "draw_audit_metadata: era(year) x genre" + (" x canonical" if canon else "")
    gc = group_col or "genre"
    kw = {"n_target": n_target}
    if "group_col" in inspect.signature(draw_audit).parameters:
        kw["group_col"] = gc
    if "metadata_only" in inspect.signature(draw_audit).parameters:
        kw["metadata_only"] = True
    a, f = draw_audit(pool, set(), rng, **kw)
    return a, f, f"draw_audit: era x {gc} (metadata)"


def select_expert_nested(audit: pd.DataFrame, frac: float, rng: np.random.Generator) -> pd.DataFrame:
    """Nested stratified expert subsample: within each audit cell, a simple random subsample of
    n_e = floor(frac * n_cell + 0.5) items, at least 1 when n_cell >= 2 (capped at n_cell).
    Returns audit + is_expert, expert_cell_n (n_e), pi_expert_given_audit (= n_e / n_cell)."""
    sel, ne = set(), {}
    for cell in sorted(audit.audit_cell.unique()):
        ids = np.sort(audit.loc[audit.audit_cell == cell, "passage_id"].values)
        n = len(ids)
        k = int(np.floor(frac * n + 0.5))
        if n >= 2:
            k = max(k, 1)
        k = min(k, n)
        ne[cell] = k
        if k:
            sel |= {str(x) for x in rng.choice(ids, size=k, replace=False)}
    n_cell = audit.groupby("audit_cell").passage_id.transform("size")
    e_n = audit.audit_cell.map(ne)
    return audit.assign(is_expert=audit.passage_id.isin(sel), expert_cell_n=e_n.astype(int),
                        pi_expert_given_audit=(e_n / n_cell).astype(float))


def build_design(pool: pd.DataFrame, disc: pd.DataFrame, annotators: list[str] = DEFAULT_ANNOTATORS,
                 expert_reader: str = "expert1", teacher: str = "teacher", n_target: int = 1800,
                 group_col: str | None = None, overlap_frac: float = 0.10, expert_frac: float = 0.5,
                 n_teacher: int = 8, n_teaching: int = 60,
                 teaching_annotator: str = "student", practice: pd.DataFrame | None = None,
                 get_text: Callable[[list[str]], pd.DataFrame] | None = None, split_warning: str | None = None,
                 use_canon: bool = True, split_source: str = "works.split (OLD)",
                 author_source: str = "works.author_key (OLD)", extra_warnings: list[str] | None = None,
                 seed: int = SEED) -> Design:
    """Pure. `pool` = confirmation_pool() (metadata only), `disc` = prepare_discovery() (Discovery labels).
    `get_text(ids)` returns passage_id + text/ctx for audit items lacking text in `pool`."""
    if {expert_reader, teacher} & set(annotators) or expert_reader == teacher:
        raise ValueError("expert reader, teacher and peers must be distinct")
    if teaching_annotator not in annotators:
        raise ValueError("teaching annotator must be one of the annotators")
    if (disc.split != "discovery").any():
        raise ValueError("teaching labels must be Discovery only")
    cert_ids = set(practice.passage_id) if practice is not None else set()
    warnings = ([split_warning] if split_warning else []) + list(extra_warnings or [])
    leaked = cert_ids & set(pool.passage_id)
    if leaked:
        warnings.append(f"WARNING: {len(leaked)} practice/cert/retake passages are in the Confirmation pool "
                        f"under the current split; they were removed from the pool (pi = 0)")
        pool = pool[~pool.passage_id.isin(leaked)]

    teaching = select_teaching(disc, n_teaching, cert_ids)
    teaching_authors = set(teaching.author_key)

    rng = np.random.default_rng(seed)
    audit, frame, strata = call_draw_audit(pool, teaching_authors, rng, n_target, group_col, use_canon)
    audit = audit.reset_index(drop=True)
    ERAS = eras_in(audit.era)
    if not {"text"} <= set(audit) and get_text is not None:
        audit = audit.merge(get_text(audit.passage_id.tolist()), on="passage_id", how="left")

    arng = np.random.default_rng([seed, 1])
    audit = select_expert_nested(audit, expert_frac, arng)       # P(expert | audit) per cell, nested
    exp_ids = set(audit.passage_id[audit.is_expert])
    teacher_ids = set(sample_by_era(audit[audit.is_expert], n_teacher, arng, ERAS))
    owner = deal(audit, annotators, arng, ERAS)                  # every audit item -> exactly one peer
    second = select_overlap(audit, owner, overlap_frac, annotators, arng, ERAS)

    era_of = dict(zip(audit.passage_id, audit.era))
    rows = []
    for pid in audit.passage_id:  # draw_audit's shuffled order
        e, a = era_of[pid], owner[pid]
        if pid in second:
            b = second[pid]
            rows += [(a, pid, "audit", "overlap", b, e), (b, pid, "audit", "overlap", a, e)]
        else:
            rows.append((a, pid, "audit", "single", None, e))
        if pid in exp_ids:
            rows.append((expert_reader, pid, "audit", "expert", a, e))   # partner = the dealt peer
        if pid in teacher_ids:
            rows.append((teacher, pid, "audit", "teacher", None, e))
    for r in teaching.itertuples():
        rows.append((teaching_annotator, r.passage_id, "teaching", "teaching", None, r.q_era))
    if practice is not None:
        for r in practice.itertuples():
            rows += [(a, r.passage_id, r.set, r.set, None, None) for a in annotators]
            rows.append((expert_reader, r.passage_id, "review", "review", None, None))

    queues = pd.DataFrame(rows, columns=[c for c in QUEUE_COLS if c != "item_id"])
    queues.insert(1, "item_id", [review_item_id(p) if s == "review" else item_id(p)
                                 for p, s in zip(queues.passage_id, queues.set)])
    pe = dict(zip(audit.passage_id, audit.pi_expert_given_audit))
    queues["pi_expert_given_audit"] = [pe.get(p) if s == "audit" else None for p, s in zip(queues.passage_id, queues.set)]
    if queues.duplicated(["annotator", "item_id"]).any() or queues.drop_duplicates(["item_id", "set"]).item_id.duplicated().any():
        raise AssertionError("duplicate assignment or item id reused across sets")

    txt = pd.concat([audit[["passage_id", *TEXT_COLS]], teaching[["passage_id", *TEXT_COLS]]])
    txt = txt.drop_duplicates("passage_id").set_index("passage_id")
    if txt.text.isna().any():
        raise ValueError("audit/teaching items without text")
    # review items live only in practice_items.json (`practice` subcommand), so that the expert's
    # entries in ann_items.json are exactly their audit items (pipeline/offline_annotation.py export-expert)
    items = practice_items(practice, annotators, None) if practice is not None else []
    for (pid, st), g in queues[queues.set.isin(["audit", "teaching"])].groupby(["passage_id", "set"], sort=False):
        t = txt.loc[pid]
        items.append({"item_id": item_id(pid), "passage_id": pid, "text": _s(t.text), "ctx_before": _s(t.ctx_before),
                      "ctx_after": _s(t.ctx_after), "set": st, "assign": list(dict.fromkeys(g.annotator))})

    people = [*annotators, expert_reader, teacher]
    per = (queues.groupby(["annotator", "role"]).size().unstack(fill_value=0)
           .reindex(index=people, columns=ROLES, fill_value=0))
    aq = queues[queues.set == "audit"]
    per["audit_total"] = aq.groupby("annotator").size().reindex(people, fill_value=0)
    per_era = aq.groupby(["annotator", "era"]).size().unstack(fill_value=0).reindex(index=people, columns=ERAS, fill_value=0)
    by_era = lambda ids: pd.Series([era_of[p] for p in ids], dtype=object).value_counts().reindex(ERAS, fill_value=0).astype(int).to_dict()
    # N_cell / n_cell / n_e per cell are never printed or written to the summary (prereg v0.5)
    summary = {
        "seed": seed, "strata": strata, "group_col": group_col, "eras": ERAS,
        "n_cells": int(frame.audit_cell.nunique()), "cell_table_hash": cell_table_hash(frame),
        "split_source": split_source, "author_identity": author_source,
        "canonical_used": strata.endswith("x canonical"),
        "annotators": annotators, "expert_reader": expert_reader, "teacher": teacher,
        "teaching_annotator": teaching_annotator,
        "params": {"n_target": n_target, "overlap_frac": overlap_frac, "expert_frac": expert_frac,
                   "expert_rule": "n_e = floor(frac * n_cell + 0.5), >= 1 when n_cell >= 2",
                   "n_teacher": n_teacher, "n_teaching": n_teaching},
        "pi_note": ("roles do not change pi: every audit item is dealt to exactly one peer; the expert subsample "
                    "is nested within audit cells with P(expert | audit) = pi_expert_given_audit (audit.parquet)"),
        "n_target": n_target, "audit_drawn": int(len(audit)), "audit_pool": int(len(frame)),
        "n_teaching_authors": len(teaching_authors), "audit_by_era": by_era(audit.passage_id),
        "n_expert": len(exp_ids), "expert_by_era": by_era(exp_ids),
        "expert_per_peer": pd.Series([owner[p] for p in exp_ids], dtype=object).value_counts()
        .reindex(annotators, fill_value=0).astype(int).to_dict(),
        "n_teacher_items": len(teacher_ids), "teacher_by_era": by_era(teacher_ids),
        "n_overlap": len(second), "overlap_by_era": by_era(second),
        "second_codings_per_annotator": pd.Series(list(second.values()), dtype=object).value_counts()
        .reindex(annotators, fill_value=0).astype(int).to_dict(),
        "n_peer_labels_audit": int(aq.annotator.isin(annotators).sum()),
        "n_teaching": int(len(teaching)),
        "teaching_reasons": teaching.t_reason.str.split("_").str[0].value_counts().to_dict(),
        "n_cert_sets": {s: int((practice.set == s).sum()) if practice is not None else 0 for s in CERT_SETS},
        "per_annotator": {a: {c: int(v) for c, v in r.items()} for a, r in per.iterrows()},
        "per_annotator_era": {a: {c: int(v) for c, v in r.items()} for a, r in per_era.iterrows()},
        "warnings": warnings,
    }
    return Design(teaching, audit, frame, queues, items, summary)


def write_design(d: Design, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    d.teaching.to_parquet(out / "teaching.parquet", index=False)
    d.audit.to_parquet(out / "audit.parquet", index=False)
    d.frame.to_parquet(out / "audit_frame.parquet", index=False)
    d.queues.to_parquet(out / "queues.parquet", index=False)
    (out / "ann_items.json").write_text(json.dumps({"items": d.items}, ensure_ascii=False), encoding="utf-8")
    (out / "design_summary.json").write_text(json.dumps(d.summary, indent=2), encoding="utf-8")


def print_summary(s: dict) -> None:
    for w in s["warnings"]:
        print(w)
    print(f"split={s['split_source']} authors={s['author_identity']} canonical used={'yes' if s['canonical_used'] else 'no'}")
    print(f"seed={s['seed']} strata={s['strata']} n_target={s['n_target']} "
          f"drawn={s['audit_drawn']} {s['audit_by_era']} pool={s['audit_pool']} cells={s['n_cells']} "
          f"teaching_authors={s['n_teaching_authors']}")
    print(f"expert (nested, frac {s['params']['expert_frac']})={s['n_expert']} {s['expert_by_era']} "
          f"per dealt peer {s['expert_per_peer']}  teacher={s['n_teacher_items']} {s['teacher_by_era']}")
    print(f"peer overlap={s['n_overlap']} {s['overlap_by_era']} second-codings={s['second_codings_per_annotator']} "
          f"peer audit labels={s['n_peer_labels_audit']} teaching={s['n_teaching']} cert sets={s['n_cert_sets']}")
    cols = [*ROLES, "audit_total"]
    short = {"audit_total": "audit"}
    print(f"{'':<9}" + "".join(f"{short.get(c, c):>10}" for c in cols) + "".join(f"{e[:5]:>7}" for e in s["eras"]))
    for a, r in s["per_annotator"].items():
        pe = s["per_annotator_era"].get(a, {})
        print(f"{a:<9}" + "".join(f"{r.get(c, 0):>10}" for c in cols) + "".join(f"{pe.get(e, 0):>7}" for e in s["eras"]))


# ------------------------------------------------------------------ CLI
def load_inputs(a: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, SplitInfo]:
    """(pool, discovery labels, split). Metadata from passages / works(_v2) / genre / canon; labels:
    Discovery rows only (resolved split, passage-level reassignment)."""
    wcols = pq.ParquetFile(a.works).schema_arrow.names
    works = pd.read_parquet(a.works, columns=[c for c in ("work_id", "decade", "year", "split", "author_key") if c in wcols])
    v2 = None
    if Path(a.works_v2).exists():
        v2cols = pq.ParquetFile(a.works_v2).schema_arrow.names
        v2 = pd.read_parquet(a.works_v2, columns=[c for c in ("pg_id", "work_id", "split", "split_v2", "author_group",
                                                              "primary_v2", "decade", "year") if c in v2cols])
    split = resolve_works(works, v2)
    passages = pd.read_parquet(a.passages, columns=["passage_id", "work_id", "stratum"])
    genre = pd.read_parquet(a.genre, columns=["work_id", "genre"]) if Path(a.genre).exists() else None
    canon = None
    if not a.no_canonical and Path(a.canon).exists():
        canon = pd.read_parquet(a.canon, columns=["work_id", "canonical"])
    pool = confirmation_pool(passages, split, genre, canon, a.group_col or "genre")
    pw = passages[["passage_id", "work_id"]]
    lab, dropped = read_discovery_labels(Path(a.labels), split, pw)
    if dropped:
        print(f"notice: dropped {dropped} non-Discovery rows from {a.labels} unread (labels sealed)")
    alt = None
    if a.alt:
        alt, _ = read_discovery_labels(Path(a.alt), split, pw)
    disc = prepare_discovery(lab, split, alt)
    if not all(c in disc for c in TEXT_COLS):
        disc = disc.merge(read_text(Path(a.passages), disc.passage_id.tolist()), on="passage_id", how="left")
    return pool, disc, split


def practice_split_warnings(practice: pd.DataFrame | None, split: SplitInfo, passages: pd.DataFrame | None = None) -> list[str]:
    if practice is None:
        return []
    df = practice[["passage_id"]]
    if split.mapper is None and passages is not None:
        df = df.merge(passages[["passage_id", "work_id"]], on="passage_id", how="left")
    if split.mapper is None and "work_id" not in df:
        return []
    bad = split.assign(df).query("split != 'discovery'").passage_id.tolist()
    return [f"WARNING: practice/cert/retake passages not in Discovery under the active split: {bad}"] if bad else []


def cmd_practice(a: argparse.Namespace) -> None:
    p = load_practice(Path(a.ref), Path(a.passages))
    items = practice_items(p, a.annotators.split(","), a.expert_reader)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "practice_items.json").write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
    cnt = pd.Series([i["set"] for i in items]).value_counts().to_dict()
    print(f"items={len(items)} {cnt} peers={a.annotators} review->{a.expert_reader} -> {out / 'practice_items.json'}")


def cmd_build(a: argparse.Namespace) -> None:
    pool, disc, split = load_inputs(a)
    practice = None
    if not a.no_practice and Path(a.practice_ref).exists():
        practice = load_practice(Path(a.practice_ref), Path(a.passages))
    elif not a.no_practice:
        print(f"note: {a.practice_ref} not found, building without practice/cert/retake/review items", file=sys.stderr)
    d = build_design(pool, disc, a.annotators.split(","), a.expert_reader, a.teacher, a.n_target, a.group_col,
                     a.overlap_frac, a.expert_frac, a.n_teacher, a.n_teaching,
                     a.teaching_annotator, practice, lambda ids: read_text(Path(a.passages), ids), split.warning,
                     not a.no_canonical, split.source, split.author_source,
                     practice_split_warnings(practice, split, pd.read_parquet(a.passages, columns=["passage_id", "work_id"])
                                             if split.mapper is None else None))
    write_design(d, Path(a.out))
    print_summary(d.summary)
    print(f"wrote teaching/audit/audit_frame/queues.parquet, ann_items.json ({len(d.items)} items), "
          f"design_summary.json -> {a.out}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("practice", "build"):
        p = sub.add_parser(name)
        p.add_argument("--annotators", default=",".join(DEFAULT_ANNOTATORS))
        p.add_argument("--expert-reader", default="expert1")
        p.add_argument("--out", default=str(OUT))
        p.add_argument("--passages", default=str(PASSAGES))
        if name == "practice":
            p.add_argument("--ref", default=str(PRACTICE_REF))
            p.set_defaults(fn=cmd_practice)
        else:
            p.add_argument("labels", help="model labels; only Discovery rows are ever read")
            p.add_argument("--alt")
            p.add_argument("--teacher", default="teacher")
            p.add_argument("--n-target", type=int, default=1800)
            p.add_argument("--group-col", default=None,
                           help="legacy draw_audit with this METADATA column (default: the registered "
                                "draw_audit_metadata, era(year) x genre [x canonical])")
            p.add_argument("--overlap-frac", type=float, default=0.10)
            p.add_argument("--expert-frac", type=float, default=0.5,
                           help="nested expert subsample: fraction of each audit cell (seeded)")
            p.add_argument("--n-teacher", type=int, default=8)
            p.add_argument("--n-teaching", type=int, default=60)
            p.add_argument("--teaching-annotator", default="student")
            p.add_argument("--works", default=str(WORKS))
            p.add_argument("--works-v2", default=str(WORKS_V2))
            p.add_argument("--genre", default=str(GENRE))
            p.add_argument("--canon", default=str(CANON), help="work_id -> canonical (pre-declared canon measure)")
            p.add_argument("--no-canonical", action="store_true", help="stratify era x genre only")
            p.add_argument("--practice-ref", default=str(PRACTICE_REF))
            p.add_argument("--no-practice", action="store_true")
            p.set_defaults(fn=cmd_build)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
