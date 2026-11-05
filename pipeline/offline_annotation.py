"""Offline annotation round-trip for annotators who use their own software.

  export-key     -> data/work/annotation/offline/key_review_items.{jsonl,csv}   (60 practice/cert/retake items + draft key)
  export-expert  -> data/work/annotation/offline/expert_items.{jsonl,csv}        (from ann_items.json, role expert1)
  validate FILE  -> checks a returned CSV/JSONL against docs/expert_annotation_instructions.md, prints problems
  import FILE    -> validated rows -> data/work/annotation/offline/returned_<kind>.parquet (+ maps item_id back)

Items are BLIND: opaque item_id, passage + context only (no title/author/date/passage id).
The item_id -> passage_id map stays private in data/work/annotation/offline/_map.json (never sent out).

usage: uv run --with pandas,duckdb,pyarrow python -I pipeline/offline_annotation.py export-key
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ANN = ROOT / "data/work/annotation"
OFF = ANN / "offline"
MAP = OFF / "_map.json"
SALT = "offline-2026-11"

DOMAINS = ["DISTANCE_TRAVEL", "COMMUNICATION_INFORMATION", "DARKNESS_VISIBILITY", "ILLNESS_BODY_DEATH",
           "MONEY_PROPERTY_LAW", "SOCIAL_RANK_CONVENTION", "INTERPERSONAL_CONFLICT", "INNER_STATE",
           "NATURE_WEATHER", "OTHER"]
LOCI = ["material_external", "social_institutional", "internal_psychological"]
CAUSES = ["infrastructure", "accidental_loss", "intentional_withholding", "misinterpretation", "success_resolution", "none"]
HAS = ["yes", "no", "cant_tell"]
KEY_COLS = ["item_id", "annotator", "decision", "has_obstacle", "domain", "locus", "failure_cause", "evidence", "note", "seconds"]
EXP_COLS = ["item_id", "annotator", "has_obstacle", "domain", "locus", "failure_cause", "evidence", "note", "seconds"]


def oid(prefix: str, pid: str) -> str:
    return prefix + hashlib.sha256(f"{SALT}:{pid}".encode()).hexdigest()[:10]


def load_map() -> dict:
    return json.loads(MAP.read_text()) if MAP.exists() else {}


def save_map(m: dict) -> None:
    OFF.mkdir(parents=True, exist_ok=True)
    MAP.write_text(json.dumps(m, indent=1))


def passages(ids: list[str]) -> pd.DataFrame:
    con = duckdb.connect()
    con.execute("CREATE TEMP TABLE w(id VARCHAR)")
    con.executemany("INSERT INTO w VALUES (?)", [(i,) for i in ids])
    return con.execute(f"SELECT passage_id, text, ctx_before, ctx_after FROM read_parquet('{ROOT}/data/work/passages.parquet') "
                       "WHERE passage_id IN (SELECT id FROM w)").df()


def write_items(rows: list[dict], name: str, cols: list[str]) -> None:
    OFF.mkdir(parents=True, exist_ok=True)
    with open(OFF / f"{name}.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OFF / f"{name}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})
    print(f"wrote {len(rows)} items -> {OFF / name}.jsonl / .csv")


def export_key() -> None:
    ref = json.loads((ANN / "practice_ref.json").read_text())
    items = [(s, it) for s in ("practice", "cert", "retake") for it in ref[s]]
    tx = passages([it["passage_id"] for _, it in items]).set_index("passage_id")
    m = load_map()
    rows = []
    for k, (s, it) in enumerate(items, 1):
        i = oid("kr_", it["passage_id"])
        m[i] = {"passage_id": it["passage_id"], "set": f"key_{s}"}
        r = tx.loc[it["passage_id"]]
        d = it["reference"]
        rows.append({"item_id": i, "order": k, "ctx_before": r.ctx_before, "passage": r.text, "ctx_after": r.ctx_after,
                     "draft_has_obstacle": "cant_tell" if d.get("has_obstacle") == "insufficient_context" else d.get("has_obstacle"),
                     "draft_domain": d.get("domain") or "", "draft_locus": d.get("locus") or "",
                     "draft_failure_cause": d.get("failure_cause") or "", "draft_rationale": it.get("rationale", "")})
    save_map(m)
    write_items(rows, "key_review_items", ["item_id", "order", "ctx_before", "passage", "ctx_after", "draft_has_obstacle",
                                           "draft_domain", "draft_locus", "draft_failure_cause", "draft_rationale"])
    template(KEY_COLS, "key_review_RETURN_TEMPLATE.csv", [r["item_id"] for r in rows])


def export_expert(annotator: str = "expert1") -> None:
    src = ANN / "ann_items.json"
    if not src.exists():
        sys.exit("ann_items.json not built yet (built on Nov 5 by analysis/build_annotation_queues.py build)")
    items = [it for it in json.loads(src.read_text())["items"] if annotator in it.get("assign", [])]
    m = load_map()
    rows = []
    for k, it in enumerate(items, 1):
        i = oid("ex_", it["passage_id"])
        m[i] = {"passage_id": it["passage_id"], "set": it.get("set", "audit"), "server_item_id": it["item_id"]}
        rows.append({"item_id": i, "order": k, "ctx_before": it["ctx_before"], "passage": it["text"], "ctx_after": it["ctx_after"]})
    save_map(m)
    write_items(rows, "expert_items", ["item_id", "order", "ctx_before", "passage", "ctx_after"])
    template(EXP_COLS, "expert_RETURN_TEMPLATE.csv", [r["item_id"] for r in rows])


def template(cols: list[str], name: str, ids: list[str]) -> None:
    with open(OFF / name, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for i in ids:
            w.writerow({"item_id": i})


def read_any(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in (".jsonl", ".ndjson"):
        return pd.DataFrame([json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()])
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def validate(path: Path) -> tuple[pd.DataFrame, list[str]]:
    df = read_any(path).fillna("")
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()
    kind = "key" if "decision" in df.columns else "expert"
    need = KEY_COLS if kind == "key" else EXP_COLS
    errs = [f"missing column: {c}" for c in need if c not in df.columns and c not in ("evidence", "note", "seconds")]
    if errs:
        return df, errs
    m = load_map()
    for n, r in df.iterrows():
        row = f"row {n + 2} ({r.get('item_id', '?')})"
        if r["item_id"] not in m:
            errs.append(f"{row}: unknown item_id")
        if not r.get("annotator"):
            errs.append(f"{row}: annotator is empty")
        if kind == "key":
            if r["decision"] not in ("agree", "correct"):
                errs.append(f"{row}: decision must be agree or correct")
            if r["decision"] == "agree":
                continue
            if not r.get("note"):
                errs.append(f"{row}: a corrected answer needs a note")
        h, d, l, fc = r["has_obstacle"], r["domain"], r["locus"], r["failure_cause"]
        if h not in HAS:
            errs.append(f"{row}: has_obstacle must be one of {HAS}")
            continue
        if h == "yes":
            if d not in DOMAINS:
                errs.append(f"{row}: domain must be one of {DOMAINS}")
            if l not in LOCI:
                errs.append(f"{row}: locus must be one of {LOCI}")
            if d == "COMMUNICATION_INFORMATION" and fc not in CAUSES:
                errs.append(f"{row}: failure_cause required for COMMUNICATION_INFORMATION, one of {CAUSES}")
            if d != "COMMUNICATION_INFORMATION" and fc:
                errs.append(f"{row}: failure_cause only allowed when domain is COMMUNICATION_INFORMATION")
        elif d or l or fc:
            errs.append(f"{row}: leave domain/locus/failure_cause empty when has_obstacle is {h}")
        if r.get("seconds") and not r["seconds"].replace(".", "", 1).isdigit():
            errs.append(f"{row}: seconds must be a number")
    dup = df.item_id[df.item_id.duplicated()].unique()
    errs += [f"duplicate item_id: {i}" for i in dup]
    return df, errs


def import_file(path: Path) -> None:
    df, errs = validate(path)
    if errs:
        print("\n".join(errs[:50]))
        sys.exit(f"{len(errs)} problem(s); nothing imported")
    m = load_map()
    df["passage_id"] = df.item_id.map(lambda i: m[i]["passage_id"])
    df["set"] = df.item_id.map(lambda i: m[i]["set"])
    kind = "key" if "decision" in df.columns else "expert"
    out = OFF / f"returned_{kind}_{path.stem}.parquet"
    df.to_parquet(out, index=False)
    print(f"imported {len(df)} rows -> {out}")


# ------------------------------------------------------------------ packets (centralized offline handout)
PK = ANN / "packets"
LABEL_COLS = EXP_COLS  # same return format for every labelling task (peers, grad, teacher)


def _guide_core() -> str:
    g = (ROOT / "docs/annotator_guide.md").read_text(encoding="utf-8")
    g = g.split("<!--")[0] + g.split("-->", 1)[1] if "<!--" in g else g
    g = g.split("## How the work is organised")[0]
    g = g.replace("Keep it open in another tab while you work. The **Guide** link at the top of the labelling page brings you back here.",
                  "Keep it open while you work.")
    import re
    rep = [
        ("| # | Question | Answers | Keys |", "| # | Question | Answers | CSV column: codes |"),
        ("| Yes / No / Can't tell | <kbd>y</kbd> <kbd>n</kbd> <kbd>c</kbd> |", "| Yes / No / Can't tell | `has_obstacle`: `yes` `no` `cant_tell` |"),
        ("| one of 9 kinds, or Other | <kbd>1</kbd>–<kbd>9</kbd>, <kbd>o</kbd> |", "| one of 9 kinds, or Other | `domain`: one code from the cheat sheet |"),
        ("| 6 choices | <kbd>Shift</kbd>+<kbd>1</kbd>–<kbd>6</kbd> |", "| 6 choices | `failure_cause`: one code from the table below |"),
        ("| Material / Social / Inner | <kbd>m</kbd> <kbd>s</kbd> <kbd>i</kbd> |", "| Material / Social / Inner | `locus`: `material_external` `social_institutional` `internal_psychological` |"),
        ("Then press <kbd>Enter</kbd>. Highlighting evidence and writing a note are optional.", "Write the codes in your return file (one row per passage). Quoting evidence and writing a note are optional."),
        ("**Material** <kbd>m</kbd>", "**Material** (`material_external`)"),
        ("**Social** <kbd>s</kbd>", "**Social** (`social_institutional`)"),
        ("**Inner** <kbd>i</kbd>", "**Inner** (`internal_psychological`)"),
        ("on the real page you would see the whole passage", "in your item file you see the whole passage"),
        ("| Key | Kind | In the way is… | Usual source |", "| Code (`domain`) | Kind | In the way is… | Usual source |"),
        ("| Key | Cause | Example | Usual source |", "| Code (`failure_cause`) | Cause | Example | Usual source |"),
    ]
    for a, b in rep:
        g = g.replace(a, b)
    dom = {"1": "DISTANCE_TRAVEL", "2": "COMMUNICATION_INFORMATION", "3": "DARKNESS_VISIBILITY", "4": "ILLNESS_BODY_DEATH",
           "5": "MONEY_PROPERTY_LAW", "6": "SOCIAL_RANK_CONVENTION", "7": "INTERPERSONAL_CONFLICT", "8": "INNER_STATE",
           "9": "NATURE_WEATHER", "o": "OTHER"}
    head, sep, tail = g.partition("## Kinds of obstacle")
    for k, v in dom.items():
        tail = re.sub(rf"^\| {re.escape(k)} \|", f"| `{v}` |", tail, flags=re.M)
    g = head + sep + tail
    cau = ["infrastructure", "accidental_loss", "intentional_withholding", "misinterpretation", "success_resolution", "none"]
    for n, v in enumerate(cau, 1):
        g = g.replace(f"| Shift+{n} |", f"| `{v}` |")
    g = re.sub(r"\s*\(?<kbd>[^<]*</kbd>(\s*[+–,]\s*<kbd>[^<]*</kbd>)*\)?", "", g)
    g = g.replace("(only when you chose kind 2)", "(only when `domain` is `COMMUNICATION_INFORMATION`)").replace("(only for kind 2)", "(only for `COMMUNICATION_INFORMATION`)")
    return g.rstrip() + "\n"


def _write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_ALL, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})


def _write_items(dirp: Path, stem: str, rows: list[dict], cols: list[str], ret_cols: list[str], annotator: str) -> None:
    dirp.mkdir(parents=True, exist_ok=True)
    with open(dirp / f"{stem}_items.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({k: r.get(k, "") for k in cols}, ensure_ascii=False) + "\n")
    _write_csv(dirp / f"{stem}_items.csv", rows, cols)
    _write_csv(dirp / f"{stem}_RETURN.csv", [{"item_id": r["item_id"], "annotator": annotator} for r in rows], ret_cols)


ITEM_COLS = ["item_id", "order", "ctx_before", "passage", "ctx_after"]


def packets_skeleton(peers: list[str]) -> None:
    """Create the folder tree + all instruction files (safe to re-run)."""
    (PK / "returned").mkdir(parents=True, exist_ok=True)
    guide = _guide_core()
    # grad (expert)
    gd = PK / "grad"
    gd.mkdir(parents=True, exist_ok=True)
    (gd / "INSTRUCTIONS.md").write_text((ROOT / "docs/expert_annotation_instructions.md").read_text(encoding="utf-8"), encoding="utf-8")
    (gd / "GUIDE.md").write_text(guide, encoding="utf-8")
    for f in ("key_review_items.csv", "key_review_items.jsonl"):
        if (OFF / f).exists():
            (gd / f"A_{f}").write_bytes((OFF / f).read_bytes())
    if (OFF / "key_review_RETURN_TEMPLATE.csv").exists():
        t = (OFF / "key_review_RETURN_TEMPLATE.csv").read_text(encoding="utf-8").replace('"",', '"expert1",', 1)
        rows = list(csv.DictReader((OFF / "key_review_RETURN_TEMPLATE.csv").open(encoding="utf-8")))
        _write_csv(gd / "A_key_review_RETURN.csv", [{"item_id": r["item_id"], "annotator": "expert1"} for r in rows], KEY_COLS)
    # peers
    for name in peers:
        pd_ = PK / f"peer_{name}"
        pd_.mkdir(parents=True, exist_ok=True)
        (pd_ / "GUIDE.md").write_text(guide, encoding="utf-8")
        (pd_ / "INSTRUCTIONS.md").write_text(PEER_MD.replace("{NAME}", name), encoding="utf-8")
    # teacher
    td = PK / "teacher"
    td.mkdir(parents=True, exist_ok=True)
    (td / "INSTRUCTIONS.md").write_text(TEACHER_MD, encoding="utf-8")
    (td / "GUIDE.md").write_text(guide, encoding="utf-8")
    (PK / "README.md").write_text(README_MD.replace("{PEERS}", ", ".join(f"`peer_{p}/`" for p in peers)), encoding="utf-8")
    print("packets ready under", PK)


def export_practice(peers: list[str]) -> None:
    """After the grad's key review: practice (with answers file) + check items for every peer."""
    key = ANN / "practice_ref_adjudicated.json"
    if not key.exists():
        sys.exit("adjudicated key missing: import the grad's key review first (annotators.py adjudicate --from-offline)")
    k = json.loads(key.read_text())
    pick = lambda s: [it for it in k.get("items", k.get(s, [])) if it.get("set", s) == s] if "items" in k else k[s]
    sets = {"B1_practice": pick("practice"), "B2_check": pick("cert"), "B3_second_check": pick("retake")}
    m = load_map()
    for stem, items in sets.items():
        tx = passages([it["passage_id"] for it in items]).set_index("passage_id")
        rows = []
        for n, it in enumerate(items, 1):
            i = oid(stem[:2].lower() + "_", it["passage_id"])
            m[i] = {"passage_id": it["passage_id"], "set": stem}
            r = tx.loc[it["passage_id"]]
            ref = it.get("reference", {})
            rows.append({"item_id": i, "order": n, "ctx_before": r.ctx_before, "passage": r.text, "ctx_after": r.ctx_after,
                         "has_obstacle": "cant_tell" if ref.get("has_obstacle") == "insufficient_context" else ref.get("has_obstacle", ""),
                         "domain": ref.get("domain") or "", "locus": ref.get("locus") or "",
                         "failure_cause": ref.get("failure_cause") or "", "why": it.get("rationale", "")})
        for name in peers:
            d = PK / f"peer_{name}"
            _write_items(d, stem, rows, ITEM_COLS, LABEL_COLS, name)
            if stem == "B1_practice":
                _write_csv(d / "B1_practice_ANSWERS.csv", rows, ["item_id", "has_obstacle", "domain", "locus", "failure_cause", "why"])
    save_map(m)
    print("practice/check packets written for", peers)


def export_audit(role_dirs: dict[str, str]) -> None:
    """After the Nov 5 build: per-annotator main sets from ann_items.json ('assign' lists)."""
    src = ANN / "ann_items.json"
    if not src.exists():
        sys.exit("ann_items.json not built yet (analysis/build_annotation_queues.py build)")
    items = json.loads(src.read_text())["items"]
    m = load_map()
    for who, dname in role_dirs.items():
        # main sets = audit items only; practice/cert/retake come from export-practice (adjudicated key);
        # the student's teaching set goes to its own file.
        teaching = [it for it in items if who in it.get("assign", []) and it.get("set") == "teaching"]
        mine = [it for it in items if who in it.get("assign", []) and it.get("set") == "audit"]
        if teaching:
            trows = []
            for n, it in enumerate(teaching, 1):
                i = oid("t_", it["passage_id"])
                m[i] = {"passage_id": it["passage_id"], "set": "teaching", "server_item_id": it["item_id"]}
                trows.append({"item_id": i, "order": n, "ctx_before": it["ctx_before"], "passage": it["text"], "ctx_after": it["ctx_after"]})
            _write_items(PK / dname, "D_teaching", trows, ITEM_COLS, LABEL_COLS, who)
        rows = []
        for n, it in enumerate(mine, 1):
            i = oid("c_", it["passage_id"])
            m[i] = {"passage_id": it["passage_id"], "set": it.get("set", "audit"), "server_item_id": it["item_id"]}
            rows.append({"item_id": i, "order": n, "ctx_before": it["ctx_before"], "passage": it["text"], "ctx_after": it["ctx_after"]})
        stem = {"teacher": "T_main"}.get(who, "C_main")
        _write_items(PK / dname, stem, rows, ITEM_COLS, LABEL_COLS, who)
        print(f"{who}: {len(rows)} items -> {PK / dname}")
    save_map(m)


def score_check(path: Path) -> None:
    """Score a returned check file against the adjudicated key: locus kappa >= .60 and obstacle agreement >= .75 to pass."""
    df, errs = validate(path)
    if errs:
        print("\n".join(errs[:30]))
        sys.exit("fix the file first")
    m = load_map()
    k = json.loads((ANN / "practice_ref_adjudicated.json").read_text())
    allitems = k["items"] if "items" in k else [it for s in ("practice", "cert", "retake") for it in k[s]]
    ref = {it["passage_id"]: it.get("reference", {}) for it in allitems}
    a, b, la, lb = [], [], [], []
    for _, r in df.iterrows():
        rr = ref[m[r.item_id]["passage_id"]]
        h_ref = "cant_tell" if rr.get("has_obstacle") == "insufficient_context" else rr.get("has_obstacle")
        a.append(r.has_obstacle == "yes"); b.append(h_ref == "yes")
        la.append(r.locus or "none"); lb.append(rr.get("locus") or "none")
    agree = sum(x == y for x, y in zip(a, b)) / len(a)
    cats = sorted(set(la) | set(lb))
    po = sum(x == y for x, y in zip(la, lb)) / len(la)
    pe = sum((la.count(c) / len(la)) * (lb.count(c) / len(lb)) for c in cats)
    kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0
    ok = kappa >= 0.60 and agree >= 0.75
    print(f"obstacle agreement {agree:.2f} (need 0.75) | locus kappa {kappa:.2f} (need 0.60) -> {'PASS' if ok else 'NOT YET'}")


README_MD = """# Annotation packets: What Stands in the Way

Everything for human annotation lives in this one folder. No accounts and no links: every annotator works offline in any software they like (a spreadsheet, Label Studio, a text editor) and returns **one CSV file**.

## Folder layout

| Folder | Who | Contents |
|---|---|---|
| `grad/` | expert reader (grad student, anonymous: `expert1`) | `INSTRUCTIONS.md`, `GUIDE.md`, task A (key review) files now; task B (`C_main_*`) from Nov 5 |
| {PEERS} | student annotators | `INSTRUCTIONS.md`, `GUIDE.md`; practice and check files once the key review is done; main set from Nov 5 |
| `teacher/` | English teacher | `INSTRUCTIONS.md`, `GUIDE.md`; 8 passages (`T_main_*`) from Nov 5 |
| `returned/` | the student (you) | drop every returned CSV here |

## Files in each packet

| File | What it is |
|---|---|
| `*_items.csv` / `*_items.jsonl` | the passages to annotate: the source. Columns: `item_id`, `order`, `ctx_before`, `passage`, `ctx_after`. Judge only `passage`; the context is for orientation. Passages are public-domain fiction (Project Gutenberg) shown **without title, author, or date** on purpose. |
| `*_RETURN.csv` | the file to fill in and send back; every `item_id` is already listed |
| `B1_practice_ANSWERS.csv` | (peers only) reference answers with a short "why", to look at **after** answering each practice passage |

## Return format (all labelling tasks)

```
item_id,annotator,has_obstacle,domain,locus,failure_cause,evidence,note,seconds
```
- `has_obstacle`: `yes` | `no` | `cant_tell`
- if `yes`: `domain` (one of the 10 codes in GUIDE.md) and `locus` (`material_external` | `social_institutional` | `internal_psychological`)
- `failure_cause` only when `domain` is `COMMUNICATION_INFORMATION` (`infrastructure` | `accidental_loss` | `intentional_withholding` | `misinterpretation` | `success_resolution` | `none`)
- `evidence`, `note`, `seconds` are optional
- leave `domain`/`locus`/`failure_cause` empty when the answer is `no` or `cant_tell`

The grad's key review (task A) has one extra column, `decision` (`agree` | `correct`); see `grad/INSTRUCTIONS.md`.

## Workflow and dates

1. **Now:** the grad does task A (60 passages, about 1 hour), returns `A_key_review_RETURN.csv`.
2. **After the key review:** the peers get `B1_practice` (20, with answers to self-check), then `B2_check` (20, no answers). A check passes at obstacle agreement of at least 0.75 and locus kappa of at least 0.60. If it fails, `B3_second_check` is the retry.
3. **From Nov 5:** main sets (`C_main_*`) for the grad (about 900) and the peers who passed, plus the teacher's 8 (`T_main_*`). Return by **Nov 8**.

## For the student: commands (run from the repo root)

```
uv run --with pandas,duckdb,pyarrow python -I pipeline/offline_annotation.py validate data/work/annotation/packets/returned/<file>.csv
uv run --with pandas,duckdb,pyarrow python -I pipeline/offline_annotation.py import   data/work/annotation/packets/returned/<file>.csv
uv run python -I pipeline/annotators.py adjudicate --from-offline          # after the grad's key review
uv run --with pandas,duckdb,pyarrow python -I pipeline/offline_annotation.py export-practice <peer names...>
uv run --with pandas,duckdb,pyarrow python -I pipeline/offline_annotation.py score-check data/work/annotation/packets/returned/<check>.csv
uv run --with pandas,duckdb,pyarrow python -I pipeline/offline_annotation.py export-audit   # Nov 5, after the queue build
```
Privacy: `../offline/_map.json` links `item_id`s to books. Never send it to anyone.
"""

PEER_MD = """# Instructions for {NAME}

Thank you for helping with **What Stands in the Way**, a study of how obstacles in English fiction changed between 1800 and 1929.

1. **Read `GUIDE.md`** (about 10 minutes). It explains the one question you answer for each passage, with worked examples.
2. **Practice:** label the 20 passages in `B1_practice_items.csv`. After each one, compare with `B1_practice_ANSWERS.csv` (answers and a short "why"). Practice isn't scored; it's for learning.
3. **Check:** label `B2_check_items.csv` (20 passages) **without** looking anything up, and return `B2_check_RETURN.csv`. The main set unlocks if you mostly agree with the reference. If not, you get `B3_second_check` (20 new passages) for one more try.
4. **Main set:** `C_main_items.csv` (about 400 passages, from Nov 5). Return `C_main_RETURN.csv` by **Nov 8**. Partial returns are fine; send what you have.

**How to answer:** open the `*_items.csv` file (or `.jsonl`) in any software, and fill in the matching `*_RETURN.csv`, one row per `item_id`:
```
item_id,annotator,has_obstacle,domain,locus,failure_cause,evidence,note,seconds
```
- `annotator` is already filled with your name.
- `has_obstacle`: `yes` / `no` / `cant_tell`.
- If `yes`, fill `domain` (one code from the GUIDE cheat sheet) and `locus` (`material_external` / `social_institutional` / `internal_psychological`).
- `failure_cause` only for `COMMUNICATION_INFORMATION`.
- Leave the others empty for `no` / `cant_tell`. `evidence`, `note`, and `seconds` are optional.

Example:
```csv
item_id,annotator,has_obstacle,domain,locus,failure_cause,evidence,note,seconds
c_1a2b3c4d5e,{NAME},yes,NATURE_WEATHER,material_external,,"he was carried off by the torrent",,31
c_9f8e7d6c5b,{NAME},no,,,,,,18
```

**Important:**
- Judge only the `passage` column; `ctx_before` and `ctx_after` are context.
- Passages come without title, author, or date on purpose. Please don't search for them.
- About 30 seconds per passage. Work in sittings of 20 to 30 minutes.
- Some passages are also labelled by other people so we can measure agreement. That's normal, and it isn't a test of you.
- Don't discuss specific passages with the other annotators until everyone is finished.
"""

TEACHER_MD = """# Instructions for the teacher

Thank you! Your quick expert read is a reference point for the student annotators.

**What:** 8 short passages (about 350 words each) in `T_main_items.csv` (or `.jsonl`), available from Nov 5. About 5 to 10 minutes in total.

**The question for each passage:** *Is something standing in the way of what a character wants, in a way that matters for what happens next?* `GUIDE.md` has the one-page version and examples. The first two sections are enough.

**Return** `T_main_RETURN.csv`, one row per passage:
```
item_id,annotator,has_obstacle,domain,locus,failure_cause,evidence,note,seconds
```
- `has_obstacle`: `yes` / `no` / `cant_tell`
- if `yes`, a `domain` code (GUIDE cheat sheet) and a `locus`: `material_external` (world, body, place) / `social_institutional` (people, rules, money) / `internal_psychological` (the character's own mind)
- `failure_cause` only for `COMMUNICATION_INFORMATION`
- a `note` is very welcome whenever a passage doesn't fit the scheme

Passages are shown without title, author, or date on purpose; please judge them from the text alone.
"""


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "export-key":
        export_key()
    elif cmd == "export-expert":
        export_expert(sys.argv[2] if len(sys.argv) > 2 else "expert1")
    elif cmd == "validate":
        _, e = validate(Path(sys.argv[2]))
        print("\n".join(e) if e else "OK: file is valid")
    elif cmd == "import":
        import_file(Path(sys.argv[2]))
    elif cmd == "packets":
        packets_skeleton(sys.argv[2:] or ["peer1", "peer2", "peer3"])
    elif cmd == "export-practice":
        export_practice(sys.argv[2:] or ["peer1", "peer2", "peer3"])
    elif cmd == "export-audit":
        roles = {"expert1": "grad", "teacher": "teacher"}
        for d in sorted(PK.glob("peer_*")):
            roles[d.name[5:]] = d.name
        export_audit(roles)
    elif cmd == "score-check":
        score_check(Path(sys.argv[2]))
    else:
        print(__doc__)
