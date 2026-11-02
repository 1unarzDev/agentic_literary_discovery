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
  uv run python -I pipeline/annotators.py adjudicate [--from-parquet ... | --from-offline [PATH|GLOB]]
                                                      # -> practice_ref_adjudicated.json

progress: queue done/total, cert rounds (Worker status + local recompute vs practice_ref.json), median s/item,
agreement with the expert (grad; --rename expert1=grad) on all nested expert items (overall + by era), with peer partners (+ pooled overlap kappa
by era via analysis.stats.annotators), and vs the teacher on the teacher items (descriptive only).
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
REF_KEYS = ("has_obstacle", "domain", "locus", "failure_cause")
CERT_SETS = ("practice", "cert", "retake")
CERT_KAPPA, CERT_OBS = 0.60, 0.75  # Worker gate: locus4 kappa >= 0.60 AND obstacle agreement >= 0.75
LOCUS4 = {"material_external": "material", "social_institutional": "social", "internal_psychological": "internal"}
ERA_DECADE = {"early_1800_1849": 1820, "mid_1850_1884": 1870, "late_1885_1920": 1900,
              "E_1800_1849": 1820, "M_1850_1884": 1870, "L_1885_1929": 1900}  # proxy decades for dsl._era
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


def _pairs(act: pd.DataFrame, queues: pd.DataFrame, name: str, role: str) -> pd.DataFrame:
    """name's active labels merged with the partner's on items where queues has (name, role, partner)."""
    q = queues[(queues.annotator == name) & (queues.role == role)]
    mine = act[act.annotator == name]
    parts = []
    for partner, g in q.groupby("partner"):
        p = act[(act.annotator == partner) & act.item_id.isin(g.item_id)]
        m = mine[mine.item_id.isin(g.item_id)].merge(p, on="item_id", suffixes=("_a", "_b"))
        parts.append(m.merge(g[["item_id", "era"]].rename(columns={"era": "q_era"}), on="item_id", how="left"))
    cols = [f"{f}_{s}" for f in FIELDS for s in "ab"] + ["q_era"]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)


def _expert_pairs(act: pd.DataFrame, queues: pd.DataFrame, name: str, expert: str) -> pd.DataFrame:
    """Peer `name` vs the expert on every nested expert item the peer was assigned (dealt or second coding)."""
    exp_items = set(queues[(queues.annotator == expert) & (queues.role == "expert")].item_id)
    q = queues[(queues.annotator == name) & (queues.set == "audit") & queues.item_id.isin(exp_items)]
    mine = act[(act.annotator == name) & act.item_id.isin(q.item_id)]
    ex = act[(act.annotator == expert) & act.item_id.isin(q.item_id)]
    m = mine.merge(ex, on="item_id", suffixes=("_a", "_b"))
    return m.merge(q[["item_id", "era"]].rename(columns={"era": "q_era"}), on="item_id", how="left")


def parse_rename(spec: str | None) -> dict:
    """'expert1=grad,a=b' -> {'expert1': 'grad', 'a': 'b'}."""
    out = {}
    for part in (spec or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def apply_rename(df: pd.DataFrame | None, mapping: dict, cols=("annotator", "partner")) -> pd.DataFrame | None:
    if df is None or not mapping:
        return df
    df = df.copy()
    for c in cols:
        if c in df:
            df[c] = df[c].map(lambda x: mapping.get(x, x) if isinstance(x, str) else x)
    return df


def rename_status(status: dict | None, mapping: dict) -> dict | None:
    if not status or not mapping:
        return status
    return {**status, "annotators": [{**a, "name": mapping.get(a["name"], a["name"])} for a in status.get("annotators", [])]}


def stats_by_era(m: pd.DataFrame) -> dict:
    """{'all': {...}, era: {...}} of agreement on FIELDS for a merged pair table."""
    out = {"all": {f: agreement(m[f"{f}_a"], m[f"{f}_b"]) for f in FIELDS} | {"n": len(m)}}
    for e, g in m.groupby("q_era"):
        out[e] = {f: agreement(g[f"{f}_a"], g[f"{f}_b"]) for f in FIELDS} | {"n": len(g)}
    return out


def teacher_comparison(act: pd.DataFrame, queues: pd.DataFrame, teacher: str = "teacher") -> dict:
    """Descriptive only: every other labeller assigned a teacher item vs the teacher on those items."""
    t_ids = set(queues[(queues.annotator == teacher) & (queues.role == "teacher")].item_id)
    t = act[(act.annotator == teacher) & act.item_id.isin(t_ids)]
    out = {}
    for name in dict.fromkeys(queues[queues.item_id.isin(t_ids)].annotator):
        if name == teacher:
            continue
        mine = act[(act.annotator == name) & act.item_id.isin(t_ids)]
        out[name] = pair_stats(mine, t)
    return out


def overlap_report(act: pd.DataFrame, queues: pd.DataFrame, expert_reader: str = "grad") -> pd.DataFrame:
    """Pooled pairwise peer-overlap kappa (locus 4-cat and obstacle), overall and by era, via
    analysis.stats.annotators.overlap_agreement (era from queues.parquet)."""
    from analysis.stats import annotators as A
    ov = queues[queues.role == "overlap"]
    h = act[act.set.eq("audit") & act.set_index(["annotator", "item_id"]).index.isin(
        ov.set_index(["annotator", "item_id"]).index)]
    if not len(h):
        return pd.DataFrame(columns=["subset", "n_pairs", "kappa_locus", "kappa_obstacle"])
    eras = ov.drop_duplicates("passage_id")[["passage_id", "era"]]
    lab = eras.assign(decade=eras.era.map(ERA_DECADE).fillna(1900).astype(int))
    loc = A.overlap_agreement(h, lab, expert_reader, target="locus")
    obs = A.overlap_agreement(h, lab, expert_reader, target="obstacle")
    out = loc.merge(obs[["subset", "kappa_obstacle"]], on="subset", how="left")
    # relabel dsl's decade eras back to the queue's era labels
    from analysis.stats.dsl import _era
    back = {str(_era(np.array([d]))[0]): e for e, d in ERA_DECADE.items() if e in set(eras.era)}
    return out.assign(subset=out.subset.map(lambda x: back.get(x, x)))


def progress_table(labels: pd.DataFrame, queues: pd.DataFrame | None = None, status: dict | None = None,
                   practice_ref: dict | None = None, expert_reader: str = "grad",
                   teacher: str = "teacher") -> list[dict]:
    """One dict per labeller: queue done/total, median seconds, cert rounds (peers), agreement with
    the expert on all nested expert items (overall + by era), with peer partners, and vs the teacher."""
    act = active(labels)
    names = []
    if status:
        names = [s["name"] for s in status.get("annotators", [])]
    for src in (queues.annotator if queues is not None else [], act.annotator):
        names += [n for n in dict.fromkeys(src) if n not in names]
    ref = ref_frame(practice_ref) if practice_ref else None
    tcmp = teacher_comparison(act, queues, teacher) if queues is not None else {}
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
        peer = name not in (expert_reader, teacher)
        if ref is not None and peer:
            row["cert_local"] = cert_scores(mine, ref)
        if queues is not None and peer:
            row["vs_expert"] = stats_by_era(_expert_pairs(act, queues, name, expert_reader))
            row["vs_partners"] = stats_by_era(_pairs(act, queues, name, "overlap"))
        if name in tcmp:
            row["vs_teacher"] = tcmp[name]
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
        for key, lab in (("vs_expert", "vs expert   "), ("vs_partners", "vs partners ")):
            if key in r:
                lines.append(f"{'':<10}   {lab} {_fmt_agr(r[key]['all'])}")
                for e, s in r[key].items():
                    if e != "all":
                        lines.append(f"{'':<10}     {e:<16} {_fmt_agr(s)}")
        if "vs_teacher" in r:
            lines.append(f"{'':<10}   vs teacher (descriptive) {_fmt_agr(r['vs_teacher'])}")
    if ov is not None and len(ov):
        lines.append("peer overlap kappa (pooled pairs):")
        for o in ov.itertuples():
            lines.append(f"  {o.subset:<16} pairs={o.n_pairs:<4} locus4 k {_k(o.kappa_locus)}  obstacle k {_k(o.kappa_obstacle)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------- adjudication of references
def _norm(v):
    if v is None or v is pd.NA or (isinstance(v, float) and np.isnan(v)):
        return None
    return None if isinstance(v, str) and v in ("", "nan", "None") else v


def review_decisions_online(labels: pd.DataFrame, ref: dict, expert_reader: str = "grad") -> dict:
    """passage_id -> {"label": {...}, "note", "decision": None} from expert1's active set=="review" Worker labels."""
    from analysis.build_annotation_queues import parse_practice_ref, review_item_id
    act = active(labels)
    rev = act[(act.set == "review") & (act.annotator == expert_reader)].set_index("item_id")
    out = {}
    for pid in parse_practice_ref(ref).passage_id:
        iid = review_item_id(pid)
        if iid in rev.index:
            r = rev.loc[iid]
            out[pid] = {"label": {k: _norm(r[k]) for k in REF_KEYS}, "note": _norm(r.get("note")), "decision": None}
    return out


OFFLINE_HAS = {"cant_tell": "insufficient_context"}


def load_offline_returns(spec: str, expert_reader: str | None = None, rename: dict | None = None) -> pd.DataFrame:
    """Returned answer-key file(s) from pipeline/offline_annotation.py: imported parquet
    (returned_key_*.parquet: KEY_COLS + passage_id + set) by path or glob; a raw CSV/JSONL return is
    validated with offline_annotation.validate and mapped back with its private item map. Later files win."""
    import glob as _glob
    paths = sorted(_glob.glob(spec), key=lambda x: (Path(x).stat().st_mtime, x)) if any(ch in spec for ch in "*?[") else [spec]
    if not paths:
        raise SystemExit(f"no offline returns match {spec}")
    frames = []
    for p in map(Path, paths):
        if p.suffix == ".parquet":
            df = pd.read_parquet(p)
        else:
            from pipeline import offline_annotation as oa
            df, errs = oa.validate(p)
            if errs:
                raise SystemExit(f"{p}: {len(errs)} problem(s):\n" + "\n".join(errs[:20]))
            m = oa.load_map()
            df["passage_id"] = df.item_id.map(lambda i: m[i]["passage_id"])
            df["set"] = df.item_id.map(lambda i: m[i]["set"])
        if "decision" not in df:
            raise SystemExit(f"{p} is not an answer-key return (no decision column)")
        frames.append(df.assign(_src=str(p)))
    df = pd.concat(frames, ignore_index=True)
    df = apply_rename(df, rename or {}, ("annotator",))
    if expert_reader and "annotator" in df and (df.annotator == expert_reader).any():
        df = df[df.annotator == expert_reader]
    return df.drop_duplicates("passage_id", keep="last")


def review_decisions_offline(df: pd.DataFrame) -> dict:
    """passage_id -> {"label", "note", "decision"} from a returned answer key (decision agree|correct;
    'agree' rows carry no answer fields; cant_tell -> insufficient_context)."""
    out = {}
    for r in df.itertuples():
        dec = str(r.decision).strip()
        lab = None
        if dec == "correct":
            h = _norm(str(r.has_obstacle).strip())
            lab = {"has_obstacle": OFFLINE_HAS.get(h, h),
                   **{k: _norm(str(getattr(r, k)).strip()) for k in ("domain", "locus", "failure_cause")}}
        out[r.passage_id] = {"label": lab, "note": _norm(str(getattr(r, "note", "") or "").strip()), "decision": dec}
    return out


def adjudicate(ref: dict, labels: pd.DataFrame | None = None, expert_reader: str = "grad",
               decisions: dict | None = None) -> tuple[dict, pd.DataFrame]:
    """practice_ref.json + expert1's review (Worker labels, or `decisions` from an offline return) ->
    adjudicated practice_ref (same format): reference = expert1's answer; rationale += 'Expert correction:
    <note>' when it differs; per item "review": {"verdict": agree|corrected|pending, "original": {...}}."""
    if decisions is None:
        decisions = review_decisions_online(labels, ref, expert_reader)
    out = {k: v for k, v in ref.items() if k not in ("items", *CERT_SETS)}
    out["version"] = f"{ref.get('version', '')}+adjudicated"
    lists = {s: ref.get(s, []) for s in CERT_SETS}
    if not any(lists.values()) and "items" in ref:
        lists["practice"] = ref["items"]
    rows = []
    for st, entries in lists.items():
        new = []
        for it in entries:
            orig = {k: _norm(it["reference"].get(k)) for k in REF_KEYS}
            e = dict(it)
            d = decisions.get(it["passage_id"])
            if d is None:
                e["review"] = {"verdict": "pending", "original": orig}
            else:
                lab = orig if d["decision"] == "agree" or d["label"] is None else d["label"]
                same = lab == orig
                e["reference"] = lab
                rat = it.get("rationale", "")
                if not same:
                    note = d.get("note")
                    rat = (rat + " " if rat else "") + (f"Expert correction: {note}" if note else "Expert correction.")
                e["rationale"] = rat
                e["review"] = {"verdict": "agree" if same else "corrected", "original": orig, "reviewer": expert_reader}
            new.append(e)
            rows.append({"set": st, "verdict": e["review"]["verdict"]})
        out[st] = new
    return out, pd.DataFrame(rows, columns=["set", "verdict"])


# ---------------------------------------------------------------------------- offline returns (packets)
OFFLINE_RETURNS = ANN / "offline/returned_*.parquet"
OFFLINE_SET = {"B1_practice": "practice", "B2_check": "cert", "B3_second_check": "retake"}


def _glob_paths(spec: str | Path) -> list[Path]:
    import glob as _glob
    spec = str(spec)
    paths = _glob.glob(spec) if any(ch in spec for ch in "*?[") else ([spec] if Path(spec).exists() else [])
    return sorted(map(Path, paths), key=lambda p: (p.stat().st_mtime, p.name))


def load_offline_labels(spec: str | Path = OFFLINE_RETURNS, rename: dict | None = None) -> pd.DataFrame:
    """Imported LABEL returns (pipeline/offline_annotation.py import -> returned_expert_*.parquet: item_id,
    annotator, has_obstacle, domain, locus, failure_cause, evidence, note, seconds, passage_id, set) ->
    the flattened label schema (LABEL_COLS + locus4/obstacle/domains). Answer-key returns (a `decision`
    column) are skipped. cant_tell -> insufficient_context; packet sets B1/B2/B3 -> practice/cert/retake;
    item_id is the queue id (select_annotation.item_id(passage_id)) so roles join from queues.parquet;
    `created` orders returns (file mtime, then row), so the latest return per annotator x passage wins."""
    from analysis.select_annotation import item_id
    rows = []
    for k, p in enumerate(_glob_paths(spec)):
        df = pd.read_parquet(p)
        if "decision" in df.columns:
            continue
        for j, r in enumerate(df.to_dict("records")):
            h = _norm(str(r.get("has_obstacle", "")).strip())
            st = str(r.get("set", "audit"))
            rows.append({"label_id": f"{p.stem}:{j}", "item_id": item_id(r["passage_id"]), "passage_id": r["passage_id"],
                         "set": OFFLINE_SET.get(st, st), "annotator": str(r.get("annotator", "")).strip(),
                         "has_obstacle": OFFLINE_HAS.get(h, h),
                         "domain": _norm(str(r.get("domain", "")).strip()), "locus": _norm(str(r.get("locus", "")).strip()),
                         "failure_cause": _norm(str(r.get("failure_cause", "")).strip()),
                         "note": _norm(str(r.get("note", "")).strip()), "evidence_text": _norm(str(r.get("evidence", "")).strip()),
                         "seconds_spent": r.get("seconds"), "created": k * 1_000_000 + j, "undone": False,
                         "practice": OFFLINE_SET.get(st) == "practice", "offline_item_id": r.get("item_id"),
                         "source_file": p.name})
    df = pd.DataFrame(rows, columns=[*LABEL_COLS, "offline_item_id", "source_file"])
    df["seconds_spent"] = pd.to_numeric(df.seconds_spent.replace("", None), errors="coerce")
    df["created"] = df.created.astype("int64")
    return apply_rename(add_constructs(df), rename or {})


def offline_human_labels(labels: pd.DataFrame, queues: pd.DataFrame | None, audit: pd.DataFrame | None,
                         frame: pd.DataFrame, all_sets: bool = False) -> tuple[pd.DataFrame, dict]:
    """Analysis file (one row per annotator x passage, latest return wins) in the human_labels schema:
    + role, partner, era (queues.parquet), audit_cell, pi_audit (audit_frame.parquet), weight,
    pi_expert_given_audit, is_expert (audit.parquet). Non-audit sets are dropped unless all_sets.
    Audit rows whose passage is not in the audit frame are dropped with a count."""
    rep = {"n_rows_in": int(len(labels))}
    act = active(labels)
    rep["n_duplicates_replaced"] = int(len(labels) - len(act))
    rep["by_set"] = act.set.value_counts().to_dict()
    df = act if all_sets else act[act.set == "audit"]
    df = attach_roles(df, queues)
    fr = frame[["passage_id", "audit_cell", "pi_audit"]].drop_duplicates("passage_id")
    in_frame = df.passage_id.isin(fr.passage_id)
    bad = (df.set == "audit") & ~in_frame
    rep["n_dropped_not_in_frame"] = int(bad.sum())
    df = df[~bad].merge(fr, on="passage_id", how="left")
    if audit is not None:
        cols = [c for c in ("weight", "pi_expert_given_audit", "is_expert", "era") if c in audit]
        a = audit[["passage_id", *cols]].drop_duplicates("passage_id").rename(columns={"era": "audit_era"})
        df = df.merge(a, on="passage_id", how="left")
        if "audit_era" in df:
            df["era"] = df.era.where(df.era.notna(), df.audit_era) if "era" in df else df.audit_era
            df = df.drop(columns="audit_era")
    rep["n_unassigned"] = int(((df.set == "audit") & df.role.isna()).sum()) if "role" in df else 0
    rep["n_rows_out"] = int(len(df))
    rep["by_annotator"] = df.annotator.value_counts().to_dict()
    return df.reset_index(drop=True), rep


def _load_parquet(p: str | Path | None) -> pd.DataFrame | None:
    return pd.read_parquet(p) if p and Path(p).exists() else None


def _practice_ref_for_progress(a: argparse.Namespace) -> dict | None:
    """Adjudicated key (what the offline checks are scored against) if present, else practice_ref.json."""
    for p in (getattr(a, "key", None), a.practice_ref):
        if p and Path(p).exists():
            return json.loads(Path(p).read_text(encoding="utf-8"))
    return None


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
    mp = parse_rename(a.rename)
    out = Path(a.out)
    if a.from_offline:
        frame = _load_parquet(a.frame)
        if frame is None:
            raise SystemExit(f"{a.frame} missing: the audit frame is needed to validate and weight the labels")
        labels = load_offline_labels(a.from_offline, mp)
        if not len(labels):
            raise SystemExit(f"no imported label returns match {a.from_offline}")
        df, r = offline_human_labels(labels, apply_rename(load_queues(Path(a.queues)), mp), _load_parquet(a.audit),
                                     frame, a.all_sets)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, index=False)
        print(f"offline returns: {r['n_rows_in']} rows, {r['n_duplicates_replaced']} superseded by a later return; "
              f"by set {r['by_set']}")
        if r["n_dropped_not_in_frame"]:
            print(f"WARNING: dropped {r['n_dropped_not_in_frame']} audit rows whose passage is not in the audit frame")
        if r["n_unassigned"]:
            print(f"WARNING: {r['n_unassigned']} audit rows were not assigned to that annotator in queues.parquet")
        print(f"wrote {r['n_rows_out']} rows ({'all sets' if a.all_sets else 'audit only'}) by annotator "
              f"{r['by_annotator']} -> {out}")
        return
    with client() as c:
        rows = request(c, "GET", "/v1/admin/ann_labels").json()["labels"]
    df = attach_roles(apply_rename(flatten_labels(rows), mp), apply_rename(load_queues(Path(a.queues)), mp))
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"exported {len(df)} labels ({int((~df.undone).sum())} active) -> {out}")


def fetch_labels(a: argparse.Namespace) -> tuple[pd.DataFrame, dict | None]:
    """Labels (+ ann_status for progress), with the --rename mapping (default expert1=grad) applied."""
    mp = parse_rename(getattr(a, "rename", None))
    if getattr(a, "from_offline", None) and a.cmd == "progress":
        return load_offline_labels(a.from_offline, mp), None
    if getattr(a, "from_parquet", None):
        return apply_rename(pd.read_parquet(a.from_parquet), mp), None
    with client() as c:
        labels = flatten_labels(request(c, "GET", "/v1/admin/ann_labels").json()["labels"])
        status = request(c, "GET", "/v1/admin/ann_status").json() if a.cmd == "progress" else None
    return apply_rename(labels, mp), rename_status(status, mp)


def _expert_name(a: argparse.Namespace) -> str:
    return parse_rename(a.rename).get(a.expert_reader, a.expert_reader)


def cmd_progress(a: argparse.Namespace) -> None:
    queues = apply_rename(load_queues(Path(a.queues)), parse_rename(a.rename))
    labels, status = fetch_labels(a)
    ref = _practice_ref_for_progress(a)
    ex = _expert_name(a)
    rows = progress_table(labels, queues, status, ref, ex, a.teacher)
    ov = overlap_report(active(labels), queues, ex) if queues is not None else None
    print(format_progress(rows, ov))


def cmd_adjudicate(a: argparse.Namespace) -> None:
    ref = json.loads(Path(a.practice_ref).read_text(encoding="utf-8"))
    if a.from_offline:
        dec = review_decisions_offline(load_offline_returns(a.from_offline, _expert_name(a), parse_rename(a.rename)))
        out, summ = adjudicate(ref, None, _expert_name(a), decisions=dec)
        print(f"source: offline return {a.from_offline} ({len(dec)} reviewed passages)")
    else:
        labels, _ = fetch_labels(a)
        out, summ = adjudicate(ref, labels, _expert_name(a))
    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    tab = summ.groupby(["set", "verdict"]).size().unstack(fill_value=0)
    for st in CERT_SETS:
        if st in tab.index:
            print(f"{st:<9} " + "  ".join(f"{v}={int(n)}" for v, n in tab.loc[st].items()))
    tot = summ.verdict.value_counts().to_dict()
    print(f"total agree={tot.get('agree', 0)} corrected={tot.get('corrected', 0)} pending={tot.get('pending', 0)} -> {p}")


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
    p.add_argument("--from-offline", nargs="?", const=str(OFFLINE_RETURNS),
                   help="build from imported offline label returns (path or glob, default %(const)s) instead of the Worker")
    p.add_argument("--audit", default=str(ANN / "audit.parquet"))
    p.add_argument("--frame", default=str(ANN / "audit_frame.parquet"))
    p.add_argument("--all-sets", action="store_true", help="keep practice/cert/retake/teaching rows (flagged by `set`)")
    p.add_argument("--rename", default="expert1=grad", help="annotator renames for the analysis, a=b[,c=d]")
    p.set_defaults(fn=cmd_export)
    p = sub.add_parser("progress")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--from-parquet")
    src.add_argument("--from-offline", nargs="?", const=str(OFFLINE_RETURNS),
                     help="imported offline label returns (path or glob, default %(const)s)")
    p.add_argument("--key", default=str(ANN / "practice_ref_adjudicated.json"),
                   help="key the checks are scored against (falls back to --practice-ref)")
    p.add_argument("--queues", default=str(ANN / "queues.parquet"))
    p.add_argument("--practice-ref", default=str(ANN / "practice_ref.json"))
    p.add_argument("--expert-reader", default="expert1", help="Worker name of the expert (before --rename)")
    p.add_argument("--teacher", default="teacher")
    p.add_argument("--rename", default="expert1=grad", help="annotator renames for the analysis, a=b[,c=d]")
    p.set_defaults(fn=cmd_progress)
    p = sub.add_parser("adjudicate", help="expert1's review labels -> practice_ref_adjudicated.json")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--from-parquet", help="exported human_labels.parquet instead of the Worker")
    src.add_argument("--from-offline", nargs="?", const=str(ANN / "offline/returned_key_*.parquet"),
                     help="offline answer-key return(s): path or glob (default %(const)s); "
                          "a raw CSV/JSONL is validated with pipeline/offline_annotation.py")
    p.add_argument("--practice-ref", default=str(ANN / "practice_ref.json"))
    p.add_argument("--out", default=str(ANN / "practice_ref_adjudicated.json"))
    p.add_argument("--expert-reader", default="expert1", help="Worker name of the expert (before --rename)")
    p.add_argument("--rename", default="expert1=grad", help="annotator renames for the analysis, a=b[,c=d]")
    p.set_defaults(fn=cmd_adjudicate)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
