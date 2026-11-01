"""Human-annotation admin for the ALD coordinator's /annotate UI.

Reads the admin config from ~/.config/ald-admin.json ({"url", "admin_token"}; override with
ALD_ADMIN_CONFIG); the admin token is never printed. Annotator tokens are stored in
~/.config/ald-annotators.json (chmod 600; override with ALD_ANNOTATORS_CONFIG) and only links are
printed, and only on explicit request (`links`, or `create --print-links`).

  uv run python -I pipeline/annotators.py create student peer1 peer2 peer3 teacher [--rotate] [--print-links]
  uv run python -I pipeline/annotators.py links [NAME...]
  uv run python -I pipeline/annotators.py upload data/work/annotation/practice_items.json
  uv run python -I pipeline/annotators.py upload data/work/annotation/ann_items.json
  uv run python -I pipeline/annotators.py export
  uv run python -I pipeline/annotators.py progress [--from-parquet data/work/annotation/human_labels.parquet]

progress: queue done/total, cert rounds (Worker status + local recompute vs practice_ref.json), median s/item,
expert agreement + the registered exclusion flag (analysis.stats.annotators), overlap kappa overall and by era.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ANN = ROOT / "data/work/annotation"
UA = "ald-annotators/1.0 (+agentic_literary_discovery)"
CHUNK = 250
FIELDS = ("has_obstacle", "domain", "locus4")
CERT_SETS = ("practice", "cert", "retake")
CERT_KAPPA, CERT_OBS = 0.60, 0.75  # Worker gate: locus4 kappa >= 0.60 AND obstacle agreement >= 0.75
LOCUS4 = {"material_external": "material", "social_institutional": "social", "internal_psychological": "internal"}
ERA_DECADE = {"early_1800_1849": 1820, "mid_1850_1884": 1870, "late_1885_1920": 1900}
LABEL_COLS = ["label_id", "item_id", "passage_id", "set", "annotator", "has_obstacle", "domain", "locus",
              "failure_cause", "note", "evidence_text", "seconds_spent", "created", "undone", "practice"]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------- config / http
def admin_cfg() -> tuple[str, str]:
    p = Path(os.environ.get("ALD_ADMIN_CONFIG", Path.home() / ".config/ald-admin.json"))
    cfg = json.loads(p.read_text(encoding="utf-8"))
    return cfg["url"].rstrip("/"), cfg["admin_token"]


def ann_cfg_path() -> Path:
    return Path(os.environ.get("ALD_ANNOTATORS_CONFIG", Path.home() / ".config/ald-annotators.json"))


def load_ann_cfg() -> dict:
    p = ann_cfg_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_ann_cfg(cfg: dict) -> None:
    p = ann_cfg_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def client() -> httpx.Client:
    url, tok = admin_cfg()
    return httpx.Client(base_url=url, timeout=120,
                        headers={"Authorization": f"Bearer {tok}", "User-Agent": UA})


def request(c: httpx.Client, method: str, path: str, attempts: int = 4, ok_status: tuple = (), **kw) -> httpx.Response:
    """HTTP call with retries on network errors, 429 and 5xx. Exits on other >= 400 unless in ok_status."""
    for i in range(attempts):
        try:
            r = c.request(method, path, **kw)
        except httpx.TransportError as e:
            if i == attempts - 1:
                raise SystemExit(f"{method} {path}: {type(e).__name__}: {e}")
            time.sleep(2 ** i)
            continue
        if (r.status_code >= 500 or r.status_code == 429) and i < attempts - 1:
            time.sleep(2 ** i)
            continue
        if r.status_code >= 400 and r.status_code not in ok_status:
            raise SystemExit(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
        return r
    raise AssertionError("unreachable")


# ---------------------------------------------------------------------------- pure helpers
def chunks(items: list, n: int = CHUNK) -> list[list]:
    return [items[i:i + n] for i in range(0, len(items), n)]


def norm_domain(d):
    if isinstance(d, (list, tuple, np.ndarray)):
        return d[0] if len(d) else None
    return d if d not in ("",) else None


def add_constructs(df: pd.DataFrame) -> pd.DataFrame:
    """locus4 = none / material / social / internal (none = has_obstacle != "yes"); obstacle = yes vs not-yes;
    domains = [domain] list column (the analysis code's schema)."""
    yes = df.has_obstacle.values == "yes"
    loc = df.locus.map(LOCUS4).fillna("none").values
    return df.assign(locus4=np.where(yes, loc, "none"), obstacle=np.where(yes, "yes", "not_yes"),
                     domains=[[d] if isinstance(d, str) and d else [] for d in df.domain])


def flatten_labels(rows: list[dict]) -> pd.DataFrame:
    out = []
    for r in rows:
        lab = r.get("label") or {}
        out.append({"label_id": r.get("id"), "item_id": r.get("item_id"), "passage_id": r.get("passage_id"),
                    "set": r.get("set"), "annotator": r.get("annotator"),
                    "has_obstacle": lab.get("has_obstacle"), "domain": norm_domain(lab.get("domain")),
                    "locus": lab.get("locus"), "failure_cause": lab.get("failure_cause"), "note": lab.get("note"),
                    "evidence_text": r.get("evidence_text"), "seconds_spent": r.get("seconds_spent"),
                    "created": r.get("created"), "undone": bool(r.get("undone", False)),
                    "practice": bool(r.get("practice", False))})
    df = pd.DataFrame(out, columns=LABEL_COLS)
    df["seconds_spent"] = pd.to_numeric(df.seconds_spent, errors="coerce")
    return add_constructs(df)


def attach_roles(df: pd.DataFrame, queues: pd.DataFrame | None) -> pd.DataFrame:
    if queues is None:
        return df.assign(role=None, partner=None, era=None)
    cols = [c for c in ("role", "partner", "era") if c in queues]
    q = queues[["annotator", "item_id", *cols]].drop_duplicates(["annotator", "item_id"])
    out = df.drop(columns=[c for c in cols if c in df]).merge(q, on=["annotator", "item_id"], how="left")
    return out if "era" in out else out.assign(era=None)


def active(df: pd.DataFrame) -> pd.DataFrame:
    """Non-undone labels; if an annotator has several active labels for an item keep the latest."""
    a = df[~df.undone.astype(bool)]
    a = a.sort_values(["created", "label_id"], kind="stable").drop_duplicates(["annotator", "item_id"], keep="last")
    return a if "locus4" in a else add_constructs(a)


def _cat(x) -> str:
    return "<null>" if x is None or (isinstance(x, float) and np.isnan(x)) else str(x)


def cohen_kappa(a, b) -> float:
    a = [_cat(x) for x in a]
    b = [_cat(x) for x in b]
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    cats = set(a) | set(b)
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    if pe >= 1.0:
        return 1.0 if po == 1.0 else float("nan")
    return (po - pe) / (1 - pe)


def agreement(a, b) -> dict:
    """Percent agreement + Cohen's kappa; null (e.g. no domain when has_obstacle=no) is its own category."""
    a, b = list(a), list(b)
    n = len(a)
    pct = sum(_cat(x) == _cat(y) for x, y in zip(a, b)) / n if n else float("nan")
    return {"n": n, "pct": pct, "kappa": cohen_kappa(a, b)}


def pair_stats(left: pd.DataFrame, right: pd.DataFrame, fields=FIELDS) -> dict:
    m = left.merge(right, on="item_id", suffixes=("_a", "_b"))
    return {f: agreement(m[f"{f}_a"], m[f"{f}_b"]) for f in fields} | {"n": len(m)}


def ref_frame(ref: dict) -> pd.DataFrame:
    """practice_ref.json -> item_id, set, reference fields (+ locus4 / obstacle)."""
    from analysis.build_annotation_queues import parse_practice_ref
    from analysis.select_annotation import item_id
    p = parse_practice_ref(ref)
    df = pd.DataFrame([{"item_id": item_id(r.passage_id), "set": r.set, **{k: r.reference.get(k) for k in
                        ("has_obstacle", "domain", "locus", "failure_cause")}} for r in p.itertuples()],
                      columns=["item_id", "set", "has_obstacle", "domain", "locus", "failure_cause"])
    return add_constructs(df)


def cert_scores(mine: pd.DataFrame, ref: pd.DataFrame) -> dict:
    """Per round (practice / cert / retake), the Worker's gate statistics recomputed locally:
    binary obstacle agreement (yes vs not-yes) and 4-category locus kappa vs the reference."""
    out = {}
    for st in CERT_SETS:
        r = ref[ref.set == st]
        if not len(r):
            continue
        m = mine[mine.item_id.isin(r.item_id)].merge(r, on="item_id", suffixes=("_a", "_b"))
        obs = agreement(m.obstacle_a, m.obstacle_b)["pct"]
        kap = cohen_kappa(m.locus4_a, m.locus4_b)
        out[st] = {"n": len(r), "done": len(m), "obs_agree": obs, "locus_kappa": kap,
                   "passed": (len(m) == len(r) and obs >= CERT_OBS and kap >= CERT_KAPPA) if st != "practice" else None,
                   "fc": agreement(m.failure_cause_a, m.failure_cause_b)["pct"] if len(m) else float("nan")}
    return out


def expert_report(act: pd.DataFrame, queues: pd.DataFrame, expert: str = "teacher") -> pd.DataFrame:
    """Registered exclusion statistics (analysis.stats.annotators): locus 4-category and obstacle kappa vs
    the expert on the expert items, n_expert_items, and the flag kappa_locus < 0.40 or n < 20."""
    from analysis.stats import annotators as A
    exp_items = set(queues[queues.role == "expert"].item_id)
    h = act[act.item_id.isin(exp_items) & (act.set == "audit")]
    names = [a for a in dict.fromkeys(queues.annotator) if a != expert]
    rep = A.expert_agreement(h, expert) if (h.annotator == expert).any() else pd.DataFrame(
        columns=["annotator", "n_expert_items", "kappa_locus", "kappa_obstacle"])
    rep = rep.set_index("annotator").reindex(names)
    rep["n_expert_items"] = rep.n_expert_items.fillna(0).astype(int)
    rep["flag_exclude"] = rep.index.isin(A.exclusions(rep.reset_index().fillna({"kappa_locus": -1})))
    return rep.reset_index().rename(columns={"index": "annotator"})


def overlap_report(act: pd.DataFrame, queues: pd.DataFrame, expert: str = "teacher") -> pd.DataFrame:
    """Pooled pairwise overlap kappa (locus 4-cat and obstacle), overall and by era, via
    analysis.stats.annotators.overlap_agreement (era from queues.parquet)."""
    from analysis.stats import annotators as A
    ov = queues[queues.role == "overlap"]
    h = act[act.set.eq("audit") & act.set_index(["annotator", "item_id"]).index.isin(
        ov.set_index(["annotator", "item_id"]).index)]
    if not len(h):
        return pd.DataFrame(columns=["subset", "n_pairs", "kappa_locus", "kappa_obstacle"])
    eras = ov.drop_duplicates("passage_id")[["passage_id", "era"]]
    lab = eras.assign(decade=eras.era.map(ERA_DECADE).fillna(1900).astype(int))
    loc = A.overlap_agreement(h, lab, expert, target="locus")
    obs = A.overlap_agreement(h, lab, expert, target="obstacle")
    return loc.merge(obs[["subset", "kappa_obstacle"]], on="subset", how="left")


def progress_table(labels: pd.DataFrame, queues: pd.DataFrame | None = None, status: dict | None = None,
                   practice_ref: dict | None = None, expert: str = "teacher") -> list[dict]:
    """One dict per annotator: queue done/total, median seconds, cert rounds, expert/overlap agreement."""
    act = active(labels)
    names = []
    if status:
        names = [s["name"] for s in status.get("annotators", [])]
    for src in (queues.annotator if queues is not None else [], act.annotator):
        names += [n for n in dict.fromkeys(src) if n not in names]
    ref = ref_frame(practice_ref) if practice_ref else None
    exp = expert_report(act, queues, expert).set_index("annotator") if queues is not None else None
    out = []
    for name in names:
        row: dict = {"annotator": name, "queues": {}}
        mine = act[act.annotator == name]
        if status:
            s = next((s for s in status["annotators"] if s["name"] == name), None)
            if s:
                row["queues"] = {q["queue"]: (q["done"], q["total"]) for q in s["queues"]}
                if s.get("cert"):
                    row["cert"] = s["cert"]
        elif queues is not None:
            for st, g in queues[queues.annotator == name].groupby("set"):
                row["queues"][st] = (int(g.item_id.isin(mine.item_id).sum()), len(g))
        work = mine[~mine.practice.astype(bool) & mine.set.isin(["audit", "teaching"])]
        row["median_s"] = float(work.seconds_spent.median()) if len(work) else float("nan")
        if ref is not None and name != expert:
            row["cert_local"] = cert_scores(mine, ref)
        if name != expert and queues is not None:
            exp_items = set(queues[queues.role == "expert"].item_id)
            t = act[(act.annotator == expert) & act.item_id.isin(exp_items)]
            row["expert_agr"] = pair_stats(mine[mine.item_id.isin(exp_items)], t)
            if exp is not None and name in exp.index:
                row["expert_rule"] = exp.loc[name].to_dict()
            ov = queues[(queues.annotator == name) & (queues.role == "overlap")]
            parts = []
            for partner, g in ov.groupby("partner"):
                p = act[(act.annotator == partner) & act.item_id.isin(g.item_id)]
                parts.append(mine[mine.item_id.isin(g.item_id)].merge(p, on="item_id", suffixes=("_a", "_b")))
            m = pd.concat(parts) if parts else pd.DataFrame(columns=[f"{f}_{s}" for f in FIELDS for s in "ab"])
            row["overlap_agr"] = {f: agreement(m[f"{f}_a"], m[f"{f}_b"]) for f in FIELDS} | {"n": len(m)}
        out.append(row)
    return out


def _k(x) -> str:
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.2f}"


def _fmt_agr(s: dict | None) -> str:
    if not s or not s.get("n"):
        return "-"
    parts = []
    for f, short in (("has_obstacle", "obs"), ("domain", "dom"), ("locus4", "loc4")):
        if f in s:
            parts.append(f"{short} {s[f]['pct']:.0%}/k{_k(s[f]['kappa'])}")
    return f"n={s['n']} " + " ".join(parts)


def _fmt_cert(r: dict) -> list[str]:
    lines = []
    if "cert" in r:
        c = r["cert"]
        rounds = "; ".join(f"{x.get('round')} {x.get('done')}/{x.get('n')} obs {_k(x.get('obs_agree'))} "
                           f"locus k {_k(x.get('locus_kappa'))} {'PASS' if x.get('passed') else 'fail' if x.get('passed') is False else ''}"
                           for x in c.get("rounds", []))
        lines.append(f"cert (worker) {c.get('status')}" + (f": {rounds}" if rounds else ""))
    for st, x in r.get("cert_local", {}).items():
        res = "" if x["passed"] is None else (" PASS" if x["passed"] else " not passed")
        lines.append(f"{st:<8} (local) {x['done']}/{x['n']} obs {_k(x['obs_agree'])} locus4 k {_k(x['locus_kappa'])}{res}")
    return lines


def format_progress(rows: list[dict], ov: pd.DataFrame | None = None) -> str:
    lines = []
    for r in rows:
        q = "  ".join(f"{k} {d}/{t}" for k, (d, t) in sorted(r["queues"].items()))
        med = "-" if np.isnan(r["median_s"]) else f"{r['median_s']:.0f}s"
        lines.append(f"{r['annotator']:<10} {q or '(no queues)'}  median/item {med}")
        for ln in _fmt_cert(r):
            lines.append(f"{'':<10}   {ln}")
        if "expert_agr" in r:
            e = r.get("expert_rule", {})
            flag = " FLAG: exclusion rule (k_locus<0.40 or n<20; provisional until done)" if e.get("flag_exclude") else ""
            lines.append(f"{'':<10}   vs expert    {_fmt_agr(r['expert_agr'])}  rule: n={e.get('n_expert_items', 0)} "
                         f"k_locus {_k(e.get('kappa_locus'))} k_obs {_k(e.get('kappa_obstacle'))}{flag}")
        if "overlap_agr" in r:
            lines.append(f"{'':<10}   vs partners  {_fmt_agr(r['overlap_agr'])}")
    if ov is not None and len(ov):
        lines.append("overlap kappa (pooled pairs, expert items excluded):")
        for o in ov.itertuples():
            lines.append(f"  {o.subset:<16} pairs={o.n_pairs:<4} locus4 k {_k(o.kappa_locus)}  obstacle k {_k(o.kappa_obstacle)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------- commands
def cmd_create(a: argparse.Namespace) -> None:
    url, _ = admin_cfg()
    cfg = load_ann_cfg()
    with client() as c:
        for name in a.names:
            r = request(c, "POST", "/v1/admin/annotators", json={"name": name, "rotate": a.rotate}, ok_status=(409,))
            if r.status_code == 409:
                have = " (token already stored locally)" if name in cfg else " (NOT stored locally: use --rotate)"
                print(f"exists  {name}{have}")
                continue
            tok = r.json()["token"]
            cfg[name] = {"token": tok, "link": f"{url}/annotate/{tok}", "annotator_id": r.json().get("annotator_id")}
            save_ann_cfg(cfg)
            if a.print_links:
                print(f"created {name} -> {cfg[name]['link']}")
            else:
                print(f"created {name} -> link saved to {ann_cfg_path()}")
    print(f"guide: {url}/annotate/guide")


def cmd_links(a: argparse.Namespace) -> None:
    cfg = load_ann_cfg()
    for name in a.names or sorted(cfg):
        print(f"{name:<10} {cfg[name]['link'] if name in cfg else '(no stored link)'}")
    print(f"guide: {admin_cfg()[0]}/annotate/guide")


def cmd_upload(a: argparse.Namespace) -> None:
    items = json.loads(Path(a.items).read_text(encoding="utf-8"))["items"]
    tot = {"inserted": 0, "skipped_existing": 0, "assignments_added": 0}
    with client() as c:
        for i, ch in enumerate(chunks(items)):
            r = request(c, "POST", "/v1/admin/ann_items", json={"items": ch}).json()
            for k in tot:
                tot[k] += int(r.get(k, 0))
            print(f"  chunk {i + 1}: {len(ch)} items {r}", file=sys.stderr)
    print(f"uploaded {len(items)} items: " + " ".join(f"{k}={v}" for k, v in tot.items()))


def load_queues(p: Path) -> pd.DataFrame | None:
    return pd.read_parquet(p) if p.exists() else None


def cmd_export(a: argparse.Namespace) -> None:
    with client() as c:
        rows = request(c, "GET", "/v1/admin/ann_labels").json()["labels"]
    df = attach_roles(flatten_labels(rows), load_queues(Path(a.queues)))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"exported {len(df)} labels ({int((~df.undone).sum())} active) -> {out}")


def cmd_progress(a: argparse.Namespace) -> None:
    queues = load_queues(Path(a.queues))
    status = None
    if a.from_parquet:
        labels = pd.read_parquet(a.from_parquet)
    else:
        with client() as c:
            labels = flatten_labels(request(c, "GET", "/v1/admin/ann_labels").json()["labels"])
            status = request(c, "GET", "/v1/admin/ann_status").json()
    ref = json.loads(Path(a.practice_ref).read_text(encoding="utf-8")) if Path(a.practice_ref).exists() else None
    rows = progress_table(labels, queues, status, ref, a.expert)
    ov = overlap_report(active(labels), queues, a.expert) if queues is not None else None
    print(format_progress(rows, ov))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="ALD human-annotation admin")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create")
    p.add_argument("names", nargs="+")
    p.add_argument("--rotate", action="store_true", help="issue a new token (the old one stops working)")
    p.add_argument("--print-links", action="store_true")
    p.set_defaults(fn=cmd_create)
    p = sub.add_parser("links")
    p.add_argument("names", nargs="*")
    p.set_defaults(fn=cmd_links)
    p = sub.add_parser("upload")
    p.add_argument("items")
    p.set_defaults(fn=cmd_upload)
    p = sub.add_parser("export")
    p.add_argument("--out", default=str(ANN / "human_labels.parquet"))
    p.add_argument("--queues", default=str(ANN / "queues.parquet"))
    p.set_defaults(fn=cmd_export)
    p = sub.add_parser("progress")
    p.add_argument("--from-parquet")
    p.add_argument("--queues", default=str(ANN / "queues.parquet"))
    p.add_argument("--practice-ref", default=str(ANN / "practice_ref.json"))
    p.add_argument("--expert", default="teacher")
    p.set_defaults(fn=cmd_progress)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
