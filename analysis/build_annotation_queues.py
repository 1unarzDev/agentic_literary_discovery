"""Build the human-annotation queues for the Worker's /annotate UI.

SEAL: the builder never reads Confirmation model labels. The labels file is read with a row filter
that keeps Discovery passages only (Confirmation rows are dropped by id before any label column is
loaded); the Confirmation audit pool is built from METADATA only (passages.parquet + works +
genre.parquet) and drawn with select_annotation.draw_audit_metadata (prereg v0.5: era(year) x genre
[x canonical when a `canonical` column is present in works / works_v2], metadata_only). N_cell is never
printed or written to the summary; design_summary.json carries cell_table_hash(frame) instead.

Split: data/work/works_v2.parquet (split_v2, author_key by work_id) when it exists, otherwise the
current works.parquet split with a loud warning in the summary.

Roles / queues (parameters recorded in design_summary.json; final numbers fixed in prereg v0.5):
  REVIEW    the 60 practice/cert/retake passages for the expert reader (expert1) to review and
            adjudicate (set "review", different opaque item ids: salt "review:").
  PRACTICE / CERT / RETAKE  20 + 20 + 20 Discovery items with references, for the peers only.
  TEACHING  ~60 Discovery items (model-label prototypes + boundary cases) for the teaching annotator.
  AUDIT     draw_audit_metadata(pool_conf minus teaching authors, rng, n_target) (legacy fallback:
            draw_audit(..., group_col=--group-col)),
            audit.parquet + audit_frame.parquet persisted exactly as returned. Every audit item gets
            >= 1 label, so no role below changes pi.
              teacher         n_teacher items, random within era (3/3/2), labelled by the teacher,
                              expert1 and every peer (descriptive comparison only)
              expert_only     n_expert_extra items reserved (era-balanced, random) for expert1 only
              deal            the rest: within each era shuffled and dealt round-robin to the peers,
                              offset carried across eras (totals differ by <= 1)
              overlap         ~overlap_frac of the dealt items per era get a second, randomly chosen
                              peer (least-loaded first); partner = the other peer
              expert_overlap  n_expert_overlap dealt single items (era-balanced, spread over peers)
                              also labelled by expert1; partner = the peer / expert1
            No adjudication of audit labels.

usage:
  uv run python -I analysis/build_annotation_queues.py practice      # practice/cert/retake + review items
  uv run python -I analysis/build_annotation_queues.py build DISCOVERY_LABELS.parquet [--alt ALT.parquet]
        [--annotators student,peer1,peer2,peer3] [--expert-reader expert1] [--teacher teacher]
        [--n-target 1800] [--group-col COL (legacy)] [--overlap-frac 0.10] [--expert-overlap 100]
        [--expert-extra 350] [--n-teacher 8] [--n-teaching 60] [--teaching-annotator student]
        [--works ...] [--works-v2 ...] [--genre ...] [--passages ...] [--out DIR]

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
PRACTICE_REF = OUT / "practice_ref.json"
DEFAULT_ANNOTATORS = ["student", "peer1", "peer2", "peer3"]
ERA_ORDER = ["E_1800_1849", "M_1850_1884", "L_1885_1929", "early_1800_1849", "mid_1850_1884", "late_1885_1920"]
CERT_SETS = ("practice", "cert", "retake")
ITEM_KEYS = ("item_id", "passage_id", "text", "ctx_before", "ctx_after", "set", "assign")
REF_KEYS = ("has_obstacle", "domain", "locus", "failure_cause")
TEXT_COLS = ["text", "ctx_before", "ctx_after"]
QUEUE_COLS = ["annotator", "item_id", "passage_id", "set", "role", "partner", "era"]
ROLES = ["review", *CERT_SETS, "teaching", "teacher", "expert_only", "expert_overlap", "overlap", "single"]


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
def resolve_works(works: pd.DataFrame, works_v2: pd.DataFrame | None) -> tuple[pd.DataFrame, str | None]:
    """work_id -> split, author_key, decade. Uses split_v2 (and its author_key) when works_v2 is given."""
    w = works[[c for c in ("work_id", "decade", "year", "split", "author_key", "canonical") if c in works]].copy()
    if "year" not in w:
        w["year"] = w.decade + 5.0
    if works_v2 is None:
        return w, ("WARNING: data/work/works_v2.parquet not found; using the OLD works.parquet split and "
                   "author_key. Re-run once split_v2 exists.")
    v2 = works_v2[["work_id", "split_v2", *[c for c in ("author_key", "canonical") if c in works_v2]]]
    w = w.drop(columns=["split"] + [c for c in ("author_key", "canonical") if c in v2 and c in w])
    w = w.merge(v2, on="work_id", how="inner")
    return w.rename(columns={"split_v2": "split"}), None


def confirmation_pool(passages: pd.DataFrame, works: pd.DataFrame, genre: pd.DataFrame | None,
                      group_col: str = "genre") -> pd.DataFrame:
    """Confirmation random-stratum pool from metadata only (no labels): passage_id, work_id,
    author_key, decade, era, split, stratum, <group_col>."""
    p = passages[["passage_id", "work_id", "stratum"]].merge(works, on="work_id", how="inner")
    p = p[(p.split == "confirmation") & (p.stratum == "random")].copy()
    p["era"] = era_of_year(p.year.values)
    if genre is not None:
        p = p.merge(genre[["work_id", "genre"]], on="work_id", how="left")
        p["genre"] = p.genre.fillna("unknown")
    if group_col not in p:
        raise SystemExit(f"--group-col {group_col!r} is not a metadata column of the pool ({list(p.columns)})")
    p[group_col] = p[group_col].astype(str)
    return p.reset_index(drop=True)


def read_discovery_labels(path: Path, disc_works: set, passage_work: pd.DataFrame | None = None) -> tuple[pd.DataFrame, int]:
    """Read ONLY Discovery rows of a labels file. Confirmation rows are dropped by id (passage_id /
    work_id) via a parquet row filter, so their label columns are never loaded."""
    cols = pq.ParquetFile(path).schema_arrow.names
    if "work_id" in cols:
        ids = pd.read_parquet(path, columns=["passage_id", "work_id"])
    else:
        if passage_work is None:
            raise SystemExit("labels file has no work_id; pass passages to map passage_id -> work_id")
        ids = pd.read_parquet(path, columns=["passage_id"]).merge(passage_work, on="passage_id", how="left")
    keep = ids[ids.work_id.isin(disc_works)].passage_id
    dropped = len(ids) - len(keep)
    if len(keep):
        lab = pd.read_parquet(path, filters=[("passage_id", "in", list(keep))])
    else:
        lab = pq.ParquetFile(path).schema_arrow.empty_table().to_pandas()
    return lab, dropped


def prepare_discovery(lab: pd.DataFrame, works: pd.DataFrame, alt: pd.DataFrame | None = None) -> pd.DataFrame:
    """Discovery labels with split / author_key / decade / era from the resolved works table."""
    lab = lab.drop(columns=[c for c in ("split", "author_key", "decade", "year", "canonical") if c in lab])
    lab = lab.merge(works, on="work_id", how="inner")
    lab = lab[lab.split == "discovery"].copy()
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


def select_expert_overlap(items: pd.DataFrame, owner: dict, n: int, annotators: list[str],
                          rng: np.random.Generator, eras: list[str]) -> list[str]:
    """n single-coded dealt items, era-balanced, spread evenly over the peers within each era."""
    q = era_quota(n, items.era.value_counts().to_dict(), eras)
    out = []
    for e in eras:
        by_peer = {a: list(rng.permutation(np.sort(items.loc[(items.era == e) &
                   (items.passage_id.map(owner) == a), "passage_id"].values))) for a in annotators}
        start = int(rng.integers(len(annotators)))
        i = 0
        while q[e] > 0 and any(by_peer.values()):
            a = annotators[(start + i) % len(annotators)]
            i += 1
            if by_peer[a]:
                out.append(str(by_peer[a].pop()))
                q[e] -= 1
    return out


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
                    group_col: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Registered v0.5 draw (select_annotation.draw_audit_metadata: era(year) x genre [x canonical],
    metadata_only) when available and group_col is None; else draw_audit with a metadata group_col.
    Teaching authors are removed from the pool first (pi = 0 for them)."""
    pool = pool[~pool.author_key.isin(teaching_authors)]
    if HAS_METADATA_DRAW and group_col is None:
        canon = "canonical" in pool
        a, f = sa.draw_audit_metadata(pool, rng, n_target)
        return a, f, "draw_audit_metadata: era(year) x genre" + (" x canonical" if canon else "")
    gc = group_col or "genre"
    kw = {"n_target": n_target}
    if "group_col" in inspect.signature(draw_audit).parameters:
        kw["group_col"] = gc
    if "metadata_only" in inspect.signature(draw_audit).parameters:
        kw["metadata_only"] = True
    a, f = draw_audit(pool, set(), rng, **kw)
    return a, f, f"draw_audit: era x {gc} (metadata)"


def build_design(pool: pd.DataFrame, disc: pd.DataFrame, annotators: list[str] = DEFAULT_ANNOTATORS,
                 expert_reader: str = "expert1", teacher: str = "teacher", n_target: int = 1800,
                 group_col: str | None = None, overlap_frac: float = 0.10, n_expert_overlap: int = 100,
                 n_expert_extra: int = 350, n_teacher: int = 8, n_teaching: int = 60,
                 teaching_annotator: str = "student", practice: pd.DataFrame | None = None,
                 get_text: Callable[[list[str]], pd.DataFrame] | None = None, split_warning: str | None = None,
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
    warnings = [split_warning] if split_warning else []
    leaked = cert_ids & set(pool.passage_id)
    if leaked:
        warnings.append(f"WARNING: {len(leaked)} practice/cert/retake passages are in the Confirmation pool "
                        f"under the current split; they were removed from the pool (pi = 0)")
        pool = pool[~pool.passage_id.isin(leaked)]

    teaching = select_teaching(disc, n_teaching, cert_ids)
    teaching_authors = set(teaching.author_key)

    rng = np.random.default_rng(seed)
    audit, frame, strata = call_draw_audit(pool, teaching_authors, rng, n_target, group_col)
    audit = audit.reset_index(drop=True)
    ERAS = eras_in(audit.era)
    if not {"text"} <= set(audit) and get_text is not None:
        audit = audit.merge(get_text(audit.passage_id.tolist()), on="passage_id", how="left")

    arng = np.random.default_rng([seed, 1])
    teacher_ids = sample_by_era(audit, n_teacher, arng, ERAS)
    rest = audit[~audit.passage_id.isin(teacher_ids)]
    exonly_ids = sample_by_era(rest, n_expert_extra, arng, ERAS)
    dealt = rest[~rest.passage_id.isin(exonly_ids)]
    owner = deal(dealt, annotators, arng, ERAS)
    second = select_overlap(dealt, owner, overlap_frac, annotators, arng, ERAS)
    singles = dealt[~dealt.passage_id.isin(second)]
    exov_ids = set(select_expert_overlap(singles, owner, n_expert_overlap, annotators, arng, ERAS))

    era_of = dict(zip(audit.passage_id, audit.era))
    t_set, x_set = set(teacher_ids), set(exonly_ids)
    rows = []
    for pid in audit.passage_id:  # draw_audit's shuffled order
        e = era_of[pid]
        if pid in t_set:
            rows += [(a, pid, "audit", "teacher", None, e) for a in [*annotators, expert_reader, teacher]]
        elif pid in x_set:
            rows.append((expert_reader, pid, "audit", "expert_only", None, e))
        elif pid in second:
            a, b = owner[pid], second[pid]
            rows += [(a, pid, "audit", "overlap", b, e), (b, pid, "audit", "overlap", a, e)]
        elif pid in exov_ids:
            a = owner[pid]
            rows += [(a, pid, "audit", "expert_overlap", expert_reader, e),
                     (expert_reader, pid, "audit", "expert_overlap", a, e)]
        else:
            rows.append((owner[pid], pid, "audit", "single", None, e))
    for r in teaching.itertuples():
        rows.append((teaching_annotator, r.passage_id, "teaching", "teaching", None, r.q_era))
    if practice is not None:
        for r in practice.itertuples():
            rows += [(a, r.passage_id, r.set, r.set, None, None) for a in annotators]
            rows.append((expert_reader, r.passage_id, "review", "review", None, None))

    queues = pd.DataFrame(rows, columns=[c for c in QUEUE_COLS if c != "item_id"])
    queues.insert(1, "item_id", [review_item_id(p) if s == "review" else item_id(p)
                                 for p, s in zip(queues.passage_id, queues.set)])
    if queues.duplicated(["annotator", "item_id"]).any() or queues.drop_duplicates(["item_id", "set"]).item_id.duplicated().any():
        raise AssertionError("duplicate assignment or item id reused across sets")

    txt = pd.concat([audit[["passage_id", *TEXT_COLS]], teaching[["passage_id", *TEXT_COLS]]])
    txt = txt.drop_duplicates("passage_id").set_index("passage_id")
    if txt.text.isna().any():
        raise ValueError("audit/teaching items without text")
    items = practice_items(practice, annotators, expert_reader) if practice is not None else []
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
    # N_cell is never printed or written (prereg v0.5): only the number of cells and the table hash
    summary = {
        "seed": seed, "strata": strata, "group_col": group_col, "eras": ERAS,
        "n_cells": int(frame.audit_cell.nunique()), "cell_table_hash": cell_table_hash(frame),
        "split_source": "works_v2.split_v2" if not split_warning else "works.split (OLD)",
        "annotators": annotators, "expert_reader": expert_reader, "teacher": teacher,
        "teaching_annotator": teaching_annotator,
        "params": {"n_target": n_target, "overlap_frac": overlap_frac, "n_expert_overlap": n_expert_overlap,
                   "n_expert_extra": n_expert_extra, "n_teacher": n_teacher, "n_teaching": n_teaching},
        "pi_note": "expert_only / overlap / teacher roles do not change pi: every audit item gets >= 1 label",
        "n_target": n_target, "audit_drawn": int(len(audit)), "audit_pool": int(len(frame)),
        "n_teaching_authors": len(teaching_authors), "audit_by_era": by_era(audit.passage_id),
        "n_teacher_items": len(teacher_ids), "teacher_by_era": by_era(teacher_ids),
        "n_expert_only": len(exonly_ids), "expert_only_by_era": by_era(exonly_ids),
        "n_expert_overlap": len(exov_ids), "expert_overlap_by_era": by_era(exov_ids),
        "expert_overlap_per_peer": pd.Series([owner[p] for p in exov_ids], dtype=object).value_counts()
        .reindex(annotators, fill_value=0).astype(int).to_dict(),
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
    print(f"seed={s['seed']} strata={s['strata']} split={s['split_source']} n_target={s['n_target']} "
          f"drawn={s['audit_drawn']} {s['audit_by_era']} pool={s['audit_pool']} cells={s['n_cells']} "
          f"teaching_authors={s['n_teaching_authors']}")
    print(f"teacher={s['n_teacher_items']} {s['teacher_by_era']}  expert_only={s['n_expert_only']} "
          f"{s['expert_only_by_era']}  expert_overlap={s['n_expert_overlap']} {s['expert_overlap_by_era']} "
          f"per peer {s['expert_overlap_per_peer']}")
    print(f"peer overlap={s['n_overlap']} {s['overlap_by_era']} second-codings={s['second_codings_per_annotator']} "
          f"peer audit labels={s['n_peer_labels_audit']} teaching={s['n_teaching']} cert sets={s['n_cert_sets']}")
    cols = [*ROLES, "audit_total"]
    short = {"expert_overlap": "x_overlap", "expert_only": "x_only", "audit_total": "audit"}
    print(f"{'':<9}" + "".join(f"{short.get(c, c):>10}" for c in cols) + "".join(f"{e[:5]:>7}" for e in s["eras"]))
    for a, r in s["per_annotator"].items():
        pe = s["per_annotator_era"].get(a, {})
        print(f"{a:<9}" + "".join(f"{r.get(c, 0):>10}" for c in cols) + "".join(f"{pe.get(e, 0):>7}" for e in s["eras"]))


# ------------------------------------------------------------------ CLI
def load_inputs(a: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, str | None]:
    """(pool, discovery labels, split warning). Metadata from passages/works/genre; labels: Discovery rows only."""
    wcols = pq.ParquetFile(a.works).schema_arrow.names
    works = pd.read_parquet(a.works, columns=[c for c in ("work_id", "decade", "year", "split", "author_key", "canonical") if c in wcols])
    v2 = pd.read_parquet(a.works_v2) if Path(a.works_v2).exists() else None
    works, warn = resolve_works(works, v2)
    passages = pd.read_parquet(a.passages, columns=["passage_id", "work_id", "stratum"])
    genre = pd.read_parquet(a.genre, columns=["work_id", "genre"]) if Path(a.genre).exists() else None
    pool = confirmation_pool(passages, works, genre, a.group_col or "genre")
    disc_works = set(works[works.split == "discovery"].work_id)
    lab, dropped = read_discovery_labels(Path(a.labels), disc_works, passages[["passage_id", "work_id"]])
    if dropped:
        print(f"notice: dropped {dropped} non-Discovery rows from {a.labels} unread (labels sealed)")
    alt = None
    if a.alt:
        alt, _ = read_discovery_labels(Path(a.alt), disc_works, passages[["passage_id", "work_id"]])
    disc = prepare_discovery(lab, works, alt)
    if not all(c in disc for c in TEXT_COLS):
        disc = disc.merge(read_text(Path(a.passages), disc.passage_id.tolist()), on="passage_id", how="left")
    return pool, disc, warn


def cmd_practice(a: argparse.Namespace) -> None:
    p = load_practice(Path(a.ref), Path(a.passages))
    items = practice_items(p, a.annotators.split(","), a.expert_reader)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "practice_items.json").write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
    cnt = pd.Series([i["set"] for i in items]).value_counts().to_dict()
    print(f"items={len(items)} {cnt} peers={a.annotators} review->{a.expert_reader} -> {out / 'practice_items.json'}")


def cmd_build(a: argparse.Namespace) -> None:
    pool, disc, warn = load_inputs(a)
    practice = None
    if not a.no_practice and Path(a.practice_ref).exists():
        practice = load_practice(Path(a.practice_ref), Path(a.passages))
    elif not a.no_practice:
        print(f"note: {a.practice_ref} not found, building without practice/cert/retake/review items", file=sys.stderr)
    d = build_design(pool, disc, a.annotators.split(","), a.expert_reader, a.teacher, a.n_target, a.group_col,
                     a.overlap_frac, a.expert_overlap, a.expert_extra, a.n_teacher, a.n_teaching,
                     a.teaching_annotator, practice, lambda ids: read_text(Path(a.passages), ids), warn)
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
            p.add_argument("--expert-overlap", type=int, default=100)
            p.add_argument("--expert-extra", type=int, default=350)
            p.add_argument("--n-teacher", type=int, default=8)
            p.add_argument("--n-teaching", type=int, default=60)
            p.add_argument("--teaching-annotator", default="student")
            p.add_argument("--works", default=str(WORKS))
            p.add_argument("--works-v2", default=str(WORKS_V2))
            p.add_argument("--genre", default=str(GENRE))
            p.add_argument("--practice-ref", default=str(PRACTICE_REF))
            p.add_argument("--no-practice", action="store_true")
            p.set_defaults(fn=cmd_build)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
