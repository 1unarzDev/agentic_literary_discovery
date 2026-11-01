"""Build the human-annotation queues (practice / cert / retake / teaching / audit) for the Worker's /annotate UI.

Registered design (docs/prereg.md v0.3 §3.4, §5.1):
  PRACTICE / CERT / RETAKE  20 + 20 + 20 Discovery items with reference answers
            (data/work/annotation/practice_ref.json), assigned to every non-expert annotator (not the
            expert). Needs no model labels (`practice` subcommand). The Worker gates practice -> cert ->
            audit/teaching, with one retake.
  TEACHING  ~60 Discovery items for the teaching annotator only: per-domain high-confidence prototypes
            (+ one early / one late cross-era prototype) and boundary cases (label vs alt_label
            disagreement, or confidence in [0.4, 0.7]). Practice/cert/retake passages excluded.
  AUDIT     draw_audit(lab_conf, teaching_authors, rng, n_target=1800, group_col="dgroup"), seed 20261105;
            audit.parquet and audit_frame.parquet (pi for every pool passage) persisted exactly as returned.
              deal     within each era: shuffle once, annotator k gets items k, k+K, k+2K, ... with the
                       round-robin offset carried across eras (totals differ by <= 1, every annotator
                       gets a random sample of every era and cell)
              expert   n_expert items (n_expert/3 per era) = simple random subsample of the audit within
                       era, assigned to the expert AND every non-expert annotator (drawn first; the
                       deal below runs over the remaining items so totals stay balanced)
              overlap  ~overlap_frac of the audit (non-expert items), per era, get a second annotator
                       drawn at random among the others, least-loaded first (balanced)
            Every audit item is labelled by >= 1 annotator, so roles do not change pi. No adjudication.

usage:
  uv run python -I analysis/build_annotation_queues.py practice [--annotators student,peer1,peer2,peer3]
  uv run python -I analysis/build_annotation_queues.py build LABELS.parquet [--alt ALT.parquet]
        [--annotators student,peer1,peer2,peer3] [--expert teacher] [--n-target 1800] [--overlap-frac 0.10]
        [--n-expert 30] [--n-teaching 60] [--teaching-annotator student] [--capacity 500] [--out DIR]

Uploaded items carry ONLY item_id, passage_id, text, ctx_before, ctx_after, set, assign (+ reference
for practice/cert/retake items): never model labels, title, author, date or decade.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.select_annotation import DOMAINS, SEED, domain_group, draw_audit, era, group, item_id  # noqa: E402

OUT = ROOT / "data/work/annotation"
PASSAGES = ROOT / "data/work/passages.parquet"
PRACTICE_REF = OUT / "practice_ref.json"
DEFAULT_ANNOTATORS = ["student", "peer1", "peer2", "peer3"]
ERAS = ["early_1800_1849", "mid_1850_1884", "late_1885_1920"]
CERT_SETS = ("practice", "cert", "retake")
ITEM_KEYS = ("item_id", "passage_id", "text", "ctx_before", "ctx_after", "set", "assign")
REF_KEYS = ("has_obstacle", "domain", "locus", "failure_cause")
TEXT_COLS = ["text", "ctx_before", "ctx_after"]
QUEUE_COLS = ["annotator", "item_id", "passage_id", "set", "role", "partner", "era"]


# ------------------------------------------------------------------ helpers
def _s(x) -> str:
    return "" if x is None or (isinstance(x, float) and np.isnan(x)) else str(x)


def _doms(x) -> list:
    return [] if x is None or (isinstance(x, float) and np.isnan(x)) else list(x)


def join_text(df: pd.DataFrame, passages_path: Path = PASSAGES) -> pd.DataFrame:
    """Fill text / ctx_before / ctx_after from passages.parquet for rows that lack them."""
    if all(c in df for c in TEXT_COLS) and not df[TEXT_COLS].isna().any().any():
        return df
    ids = list(dict.fromkeys(df.passage_id))
    p = pd.read_parquet(passages_path, columns=["passage_id", *TEXT_COLS], filters=[("passage_id", "in", ids)])
    out = df.drop(columns=[c for c in TEXT_COLS if c in df]).merge(p, on="passage_id", how="left")
    missing = out.text.isna().sum()
    if missing:
        raise SystemExit(f"{missing} passages have no text in {passages_path}")
    return out


def parse_practice_ref(ref: dict) -> pd.DataFrame:
    """practice_ref.json -> DataFrame(passage_id, set, reference). Accepts the v0.3 format
    {"practice": [...], "cert": [...], "retake": [...]} and the older {"items": [...]} (= practice)."""
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
        raise SystemExit(f"passage_id used twice in practice_ref.json: "
                         f"{df[df.passage_id.duplicated()].passage_id.tolist()}")
    return df


def load_practice(ref_path: Path, passages_path: Path = PASSAGES, passages: pd.DataFrame | None = None) -> pd.DataFrame:
    """practice_ref.json -> DataFrame(passage_id, set, reference, text, ctx_before, ctx_after)."""
    df = parse_practice_ref(json.loads(Path(ref_path).read_text(encoding="utf-8")))
    if passages is not None:
        df = df.merge(passages[["passage_id", *TEXT_COLS]], on="passage_id", how="left")
        if df.text.isna().any():
            raise SystemExit(f"practice passages missing text: {df[df.text.isna()].passage_id.tolist()}")
        return df
    return join_text(df, passages_path)


def practice_items(practice: pd.DataFrame, annotators: list[str]) -> list[dict]:
    return [{"item_id": item_id(r.passage_id), "passage_id": r.passage_id, "text": _s(r.text),
             "ctx_before": _s(r.ctx_before), "ctx_after": _s(r.ctx_after), "set": r.set,
             "assign": list(annotators), "reference": dict(r.reference)} for r in practice.itertuples()]


# ------------------------------------------------------------------ teaching
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


# ------------------------------------------------------------------ audit roles
def deal(audit: pd.DataFrame, annotators: list[str], rng: np.random.Generator) -> dict[str, str]:
    """Within each era: shuffle, then round-robin with the offset carried across eras."""
    owner, j = {}, 0
    for e in ERAS:
        ids = np.sort(audit.loc[audit.era == e, "passage_id"].values)
        for pid in rng.permutation(ids):
            owner[pid] = annotators[j % len(annotators)]
            j += 1
    return owner


def select_expert(audit: pd.DataFrame, n_expert: int, rng: np.random.Generator) -> list[str]:
    """Simple random subsample of the audit within each era: n_expert / 3 per era."""
    per = n_expert // len(ERAS)
    extra = n_expert - per * len(ERAS)
    out = []
    for i, e in enumerate(ERAS):
        ids = np.sort(audit.loc[audit.era == e, "passage_id"].values)
        k = min(per + (1 if i < extra else 0), len(ids))
        out += list(rng.choice(ids, size=k, replace=False))
    return out


def select_overlap(audit: pd.DataFrame, owner: dict, exclude: set, frac: float, annotators: list[str],
                   rng: np.random.Generator) -> dict[str, str]:
    """~frac of the audit, per era, get a second annotator drawn at random among the other annotators,
    restricted to the least-loaded ones (load = dealt + second codings; ties random) so second-codings
    and per-annotator totals stay balanced."""
    if len(annotators) < 2:
        return {}
    second = {}
    load = pd.Series(list(owner.values())).value_counts().reindex(annotators, fill_value=0).to_dict()
    for e in ERAS:
        n_era = int((audit.era == e).sum())
        ids = np.sort(audit.loc[(audit.era == e) & ~audit.passage_id.isin(exclude), "passage_id"].values)
        k = min(int(round(frac * n_era)), len(ids))
        for pid in rng.choice(ids, size=k, replace=False) if k else []:
            cand = [a for a in annotators if a != owner[pid]]
            m = min(load[a] for a in cand)
            b = str(rng.choice([a for a in cand if load[a] == m]))
            second[pid] = b
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


def prepare_labels(lab: pd.DataFrame, alt: pd.DataFrame | None = None) -> pd.DataFrame:
    lab = lab.copy()
    lab["era"] = lab.decade.map(era)
    lab["group"] = lab.apply(group, axis=1)
    lab["dgroup"] = lab.apply(domain_group, axis=1)
    if alt is not None:
        a = alt[["passage_id", "has_obstacle", "locus", "domains"]].add_prefix("alt_")
        lab = lab.merge(a, left_on="passage_id", right_on="alt_passage_id", how="left").drop(columns="alt_passage_id")
    return lab[lab.stratum.isin(["random", "enrich_comm", "enrich_mob", "enrich_dark"])].reset_index(drop=True)


def build_design(lab: pd.DataFrame, annotators: list[str] = DEFAULT_ANNOTATORS, expert: str = "teacher",
                 n_target: int = 1800, overlap_frac: float = 0.10, n_expert: int = 30, n_teaching: int = 60,
                 teaching_annotator: str = "student", practice: pd.DataFrame | None = None,
                 capacity: int | None = None, seed: int = SEED) -> Design:
    """`lab` = prepare_labels() output with text/ctx columns; `practice` = load_practice() output. Pure."""
    if expert in annotators:
        raise ValueError("expert must not also be a regular annotator")
    if teaching_annotator not in annotators:
        raise ValueError("teaching annotator must be one of the annotators")
    cert_ids = set(practice.passage_id) if practice is not None else set()

    teaching = select_teaching(lab, n_teaching, cert_ids)
    teaching_authors = set(teaching.author_key)

    # audit: one probability draw from the Confirmation half (pi untouched below)
    rng = np.random.default_rng(seed)
    lab_conf = lab[lab.split == "confirmation"]
    audit, frame = draw_audit(lab_conf, teaching_authors, rng, n_target=n_target, group_col="dgroup")
    audit = audit.reset_index(drop=True)
    if set(audit.passage_id) & cert_ids:
        raise ValueError("practice/cert/retake passage drawn into the audit (they must be Discovery)")

    arng = np.random.default_rng([seed, 1])
    exp_ids = select_expert(audit, n_expert, arng)
    owner = deal(audit[~audit.passage_id.isin(exp_ids)], annotators, arng)  # expert items go to everyone
    second = select_overlap(audit, owner, set(exp_ids), overlap_frac, annotators, arng)

    era_of = dict(zip(audit.passage_id, audit.era))
    rows = []
    exp_set = set(exp_ids)
    for pid in audit.passage_id:  # audit order is draw_audit's shuffled order
        e = era_of[pid]
        if pid in exp_set:
            rows += [(a, pid, "audit", "expert", None, e) for a in [*annotators, expert]]
        elif pid in second:
            a, b = owner[pid], second[pid]
            rows += [(a, pid, "audit", "overlap", b, e), (b, pid, "audit", "overlap", a, e)]
        else:
            rows.append((owner[pid], pid, "audit", "single", None, e))
    for r in teaching.itertuples():
        rows.append((teaching_annotator, r.passage_id, "teaching", "teaching", None, r.era))
    if practice is not None:
        for r in practice.itertuples():
            rows += [(a, r.passage_id, r.set, r.set, None, None) for a in annotators]

    queues = pd.DataFrame(rows, columns=[c for c in QUEUE_COLS if c != "item_id"])
    queues.insert(1, "item_id", queues.passage_id.map(item_id))
    if queues.duplicated(["annotator", "item_id"]).any():
        raise AssertionError("an annotator was assigned the same item twice")

    # items (whitelisted fields only), assign lists merged per item
    txt = pd.concat([audit[["passage_id", *TEXT_COLS]], teaching[["passage_id", *TEXT_COLS]]])
    txt = txt.drop_duplicates("passage_id").set_index("passage_id")
    items = practice_items(practice, annotators) if practice is not None else []
    for (pid, st), g in queues[~queues.set.isin(CERT_SETS)].groupby(["passage_id", "set"], sort=False):
        t = txt.loc[pid]
        items.append({"item_id": item_id(pid), "passage_id": pid, "text": _s(t.text), "ctx_before": _s(t.ctx_before),
                      "ctx_after": _s(t.ctx_after), "set": st, "assign": list(dict.fromkeys(g.annotator))})

    roles = [*CERT_SETS, "teaching", "expert", "overlap", "single"]
    per = queues.groupby(["annotator", "role"]).size().unstack(fill_value=0).reindex(columns=roles, fill_value=0)
    per["audit_total"] = per[["expert", "overlap", "single"]].sum(axis=1)
    aq = queues[queues.set == "audit"]
    per_era = aq.groupby(["annotator", "era"]).size().unstack(fill_value=0).reindex(columns=ERAS, fill_value=0)
    second_cnt = pd.Series(second).value_counts().reindex(annotators, fill_value=0)
    cells = (frame.groupby("audit_cell").agg(N=("passage_id", "size"), pi=("pi_audit", "first"))
             .join(audit.groupby("audit_cell").size().rename("n")).fillna({"n": 0}))
    warnings = []
    if capacity:
        for a in annotators:
            t = int(per.loc[a, "audit_total"])
            if abs(t - capacity) > 0.1 * capacity:
                warnings.append(f"{a}: {t} audit items vs capacity {capacity}")
    summary = {
        "seed": seed, "group_col": "dgroup", "annotators": annotators, "expert": expert,
        "teaching_annotator": teaching_annotator, "n_target": n_target, "overlap_frac": overlap_frac,
        "audit_drawn": int(len(audit)), "audit_pool": int(len(frame)), "n_teaching_authors": len(teaching_authors),
        "audit_by_era": audit.era.value_counts().reindex(ERAS, fill_value=0).astype(int).to_dict(),
        "n_expert": len(exp_ids), "expert_by_era": pd.Series([era_of[p] for p in exp_ids]).value_counts()
        .reindex(ERAS, fill_value=0).astype(int).to_dict(),
        "n_overlap": len(second), "overlap_by_era": pd.Series([era_of[p] for p in second]).value_counts()
        .reindex(ERAS, fill_value=0).astype(int).to_dict(),
        "second_codings_per_annotator": {a: int(v) for a, v in second_cnt.items()},
        "n_labels_audit": int(len(aq[aq.annotator != expert])),
        "n_teaching": int(len(teaching)),
        "teaching_reasons": teaching.t_reason.str.split("_").str[0].value_counts().to_dict(),
        "n_cert_sets": {s: int((practice.set == s).sum()) if practice is not None else 0 for s in CERT_SETS},
        "per_annotator": {a: {c: int(v) for c, v in r.items()} for a, r in per.iterrows()},
        "per_annotator_era": {a: {c: int(v) for c, v in r.items()} for a, r in per_era.iterrows()},
        "capacity": capacity, "warnings": warnings,
        "cells": {c: {"N": int(r.N), "n": int(r.n), "pi": float(r.pi)} for c, r in cells.iterrows()},
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
    print(f"seed={s['seed']} strata=era x {s['group_col']} n_target={s['n_target']} drawn={s['audit_drawn']} "
          f"{s['audit_by_era']} pool={s['audit_pool']} cells={len(s['cells'])} teaching_authors={s['n_teaching_authors']}")
    print(f"expert={s['n_expert']} {s['expert_by_era']}  overlap={s['n_overlap']} {s['overlap_by_era']} "
          f"second-codings={s['second_codings_per_annotator']}")
    print(f"non-expert audit labels={s['n_labels_audit']} teaching={s['n_teaching']} {s['teaching_reasons']} "
          f"cert sets={s['n_cert_sets']}")
    cols = [*CERT_SETS, "teaching", "expert", "overlap", "single", "audit_total"]
    print(f"{'annotator':<10}" + "".join(f"{c:>12}" for c in cols) + "".join(f"{e[:5]:>8}" for e in ERAS))
    for a, r in s["per_annotator"].items():
        pe = s["per_annotator_era"].get(a, {})
        print(f"{a:<10}" + "".join(f"{r.get(c, 0):>12}" for c in cols) + "".join(f"{pe.get(e, 0):>8}" for e in ERAS))
    for w in s["warnings"]:
        print(f"warning: {w}")


# ------------------------------------------------------------------ CLI
def cmd_practice(a: argparse.Namespace) -> None:
    p = load_practice(Path(a.ref), Path(a.passages))
    items = practice_items(p, a.annotators.split(","))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "practice_items.json").write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
    print(f"items={len(items)} {p.set.value_counts().to_dict()} assign={a.annotators} -> {out / 'practice_items.json'}")


def cmd_build(a: argparse.Namespace) -> None:
    lab = pd.read_parquet(a.labels)
    alt = pd.read_parquet(a.alt) if a.alt else None
    lab = join_text(prepare_labels(lab, alt), Path(a.passages))
    practice = None
    if not a.no_practice and Path(a.practice_ref).exists():
        practice = load_practice(Path(a.practice_ref), Path(a.passages))
    elif not a.no_practice:
        print(f"note: {a.practice_ref} not found, building without practice/cert/retake items", file=sys.stderr)
    d = build_design(lab, a.annotators.split(","), a.expert, a.n_target, a.overlap_frac, a.n_expert,
                     a.n_teaching, a.teaching_annotator, practice, a.capacity)
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
        p.add_argument("--out", default=str(OUT))
        p.add_argument("--passages", default=str(PASSAGES))
        if name == "practice":
            p.add_argument("--ref", default=str(PRACTICE_REF))
            p.set_defaults(fn=cmd_practice)
        else:
            p.add_argument("labels")
            p.add_argument("--alt")
            p.add_argument("--expert", default="teacher")
            p.add_argument("--n-target", type=int, default=1800)
            p.add_argument("--overlap-frac", type=float, default=0.10)
            p.add_argument("--n-expert", type=int, default=30)
            p.add_argument("--n-teaching", type=int, default=60)
            p.add_argument("--teaching-annotator", default="student")
            p.add_argument("--capacity", type=int, default=500, help="only used for a warning")
            p.add_argument("--practice-ref", default=str(PRACTICE_REF))
            p.add_argument("--no-practice", action="store_true")
            p.set_defaults(fn=cmd_build)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
