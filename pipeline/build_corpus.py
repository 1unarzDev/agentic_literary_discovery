"""Clean PG texts, dedup works, assign author-level splits, segment, sample passages, write shards.

Stages (each idempotent, outputs under data/work/):
  clean   -> data/work/clean/<pg_id>.txt  + manifest columns (sha256, n_words, quality)
  dedup   -> work_id assignment (MinHash over normalized word shingles + author/title key)
  split   -> discovery / confirmation by author hash, stratified
  passages-> data/work/passages.parquet (random backbone + enrichment, with offsets)
Run: uv run python -I pipeline/build_corpus.py all
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/pg"
WORK = ROOT / "data/work"
MAN = ROOT / "data/manifests"
SEED = 20261031
PASSAGE_WORDS = 350
RANDOM_PER_WORK = 24
ENRICH_CAP = 8  # per domain per work
MIN_WORDS = 15000  # novels / substantial fiction only (drop short pamphlets)

START_RE = re.compile(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", re.I | re.S)
END_RE = re.compile(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK", re.I)


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def clean_one(pg_id: int) -> dict | None:
    p = RAW / str(pg_id) / f"pg{pg_id}.txt"
    if not p.exists():
        return None
    raw = p.read_text(encoding="utf-8", errors="replace")
    m = START_RE.search(raw)
    body = raw[m.end():] if m else raw
    e = END_RE.search(body)
    body = body[: e.start()] if e else body
    body = body.replace("\r\n", "\n").strip()
    # drop transcriber/produced-by preamble lines at the very start
    body = re.sub(r"\A(?:.*(?:Produced by|Transcribed|E-text prepared|transcriber).*\n)+", "", body, flags=re.I)
    words = body.split()
    n = len(words)
    if n == 0:
        return None
    nonascii = sum(1 for ch in body[:200000] if ord(ch) > 127 and not unicodedata.category(ch).startswith("P"))
    out = WORK / "clean" / f"{pg_id}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8", newline="\n")
    norm = " ".join(w.lower() for w in re.findall(r"[A-Za-z]+", body))
    lines = [l for l in body.split("\n") if l.strip()]
    nl = max(1, len(lines))
    short = sum(1 for l in lines if len(l.split()) <= 3) / nl
    caps = sum(1 for l in lines if l.isupper() and len(l) > 8) / nl
    from collections import Counter
    lc = Counter(l.strip() for l in lines if len(l.strip()) > 10)
    repeated = sum(c for c in lc.values() if c >= 5) / nl
    return {
        "short_line_rate": short, "caps_line_rate": caps, "repeated_line_rate": repeated,
        "pg_id": pg_id,
        "text_sha256": sha(raw),
        "normalized_sha256": sha(norm),
        "n_words": n,
        "nonascii_rate": nonascii / max(1, min(len(body), 200000)),
        "minhash": minhash(norm),
    }


def minhash(norm: str, k: int = 64) -> list[int]:
    toks = norm.split()
    # sample shingles from 3 regions to be fast but robust to front/back matter differences
    idx = list(range(0, max(1, len(toks) - 5), max(1, len(toks) // 3000)))
    sh = {" ".join(toks[i : i + 5]) for i in idx}
    if not sh:
        return [0] * k
    hs = np.array([int(hashlib.blake2b(s.encode(), digest_size=8).hexdigest(), 16) & 0xFFFFFFFFFFFF for s in sh], dtype=np.uint64)
    rng = np.random.default_rng(SEED)
    a = rng.integers(1, 2**31 - 1, size=k, dtype=np.uint64)
    b = rng.integers(0, 2**31 - 1, size=k, dtype=np.uint64)
    prime = np.uint64(2**61 - 1)
    mins = ((hs[None, :] * a[:, None] + b[:, None]) % prime).min(axis=1)
    return [int(x) for x in mins]


def stage_clean() -> pd.DataFrame:
    cand = pd.read_parquet(MAN / "candidates_v1.parquet")
    ids = cand.pg_id.astype(int).tolist()
    with ProcessPoolExecutor() as ex:
        rows = [r for r in ex.map(clean_one, ids, chunksize=64) if r]
    q = pd.DataFrame(rows)
    df = cand.merge(q, on="pg_id", how="inner")
    df.to_parquet(WORK / "cleaned.parquet", index=False)
    print("cleaned", len(df), "of", len(cand))
    return df


def author_key(a: str) -> str:
    a = str(a).split(";")[0]
    a = re.sub(r"\[.*?\]|\d{3,4}\??-?|\(.*?\)", "", a)
    return re.sub(r"[^a-z]", "", a.lower())


def title_key(t: str) -> str:
    t = str(t).split("\n")[0].lower()
    t = re.sub(r"^(the|a|an)\s+", "", t)
    t = re.sub(r"[:;,(].*$", "", t)
    return re.sub(r"[^a-z]", "", t)[:40]


QUALITY = {"short_line_rate": 0.35, "caps_line_rate": 0.05, "repeated_line_rate": 0.05, "nonascii_rate": 0.02}
AUTHOR_CAP_PER_DECADE = 5


def stage_dedup(df: pd.DataFrame) -> pd.DataFrame:
    n0 = len(df)
    df = df[df.n_words >= MIN_WORDS].copy()
    bad = np.zeros(len(df), dtype=bool)
    for k, thr in QUALITY.items():
        bad |= (df[k] > thr).to_numpy()
    df["quality_fail"] = bad
    print(f"length filter kept {len(df)}/{n0}; quality failures {bad.sum()}")
    df = df[~df.quality_fail].copy()
    df["author_key"] = df.Authors.map(author_key)
    df["title_key"] = df.Title.map(title_key)
    # union-find over (a) identical author+title, (b) minhash jaccard >= 0.5 within LSH buckets
    parent = {i: i for i in df.pg_id}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[max(rx, ry)] = min(rx, ry)

    for _, g in df.groupby(["author_key", "title_key"]):
        ids = g.pg_id.tolist()
        for o in ids[1:]:
            union(ids[0], o)
    mh = {r.pg_id: np.array(r.minhash, dtype=np.uint64) for r in df.itertuples()}
    buckets: dict = {}
    for pid, m in mh.items():
        for band in range(16):
            buckets.setdefault((band, tuple(m[band * 4 : band * 4 + 4])), []).append(pid)
    for ids in buckets.values():
        if 1 < len(ids) < 50:
            for o in ids[1:]:
                if (mh[ids[0]] == mh[o]).mean() >= 0.5:
                    union(ids[0], o)
    df["work_root"] = df.pg_id.map(find)
    # canonical edition per work: highest date confidence, then longest
    conf_rank = {"high": 0, "medium": 1, "low": 2}
    df["_cr"] = df.date_confidence.map(conf_rank)
    df = df.sort_values(["work_root", "_cr", "n_words"], ascending=[True, True, False])
    df["n_editions"] = df.groupby("work_root").pg_id.transform("count")
    canon = df.drop_duplicates("work_root").copy()
    canon["work_id"] = "w" + canon.work_root.astype(str)
    canon = canon.drop(columns=["_cr", "minhash"])
    canon.to_parquet(WORK / "works.parquet", index=False)
    print("works after dedup", len(canon), "(editions collapsed:", int((df.n_editions > 1).sum()), ")")
    return canon


def stage_split(w: pd.DataFrame) -> pd.DataFrame:
    # author-level split, stratified by modal decade x origin of author's works
    a = w.groupby("author_key").agg(decade=("decade", lambda s: int(s.mode().iloc[0])),
                                    origin=("origin_locc", lambda s: s.mode().iloc[0]),
                                    n=("work_id", "count")).reset_index()
    a["h"] = a.author_key.map(lambda k: int(hashlib.sha256(f"{SEED}:{k}".encode()).hexdigest(), 16))
    a = a.sort_values(["decade", "origin", "h"])
    a["rank"] = a.groupby(["decade", "origin"]).cumcount()
    a["split"] = np.where(a["rank"] % 2 == 0, "discovery", "confirmation")
    w = w.merge(a[["author_key", "split"]], on="author_key")
    # author cap: primary analysis uses <= AUTHOR_CAP_PER_DECADE works per author-decade (seeded); others kept for sensitivity
    w["_r"] = w.work_id.map(lambda k: int(hashlib.sha256(f"{SEED}:cap:{k}".encode()).hexdigest()[:12], 16))
    w["cap_rank"] = w.sort_values("_r").groupby(["author_key", "decade"]).cumcount().reindex(w.index)
    w["in_primary_cap"] = w.cap_rank < AUTHOR_CAP_PER_DECADE
    w = w.drop(columns=["_r"])
    w.to_parquet(WORK / "works.parquet", index=False)
    tab = w.groupby(["decade", "split"]).agg(works=("work_id", "count"), authors=("author_key", "nunique")).unstack()
    print(tab.to_string())
    return w


WORD_RE = re.compile(r"\S+")


def load_lexicon() -> dict[str, re.Pattern]:
    # Seed lexicon; replaced by research/history/lexicon.yaml terms when available.
    seeds = {
        "enrich_comm": r"\b(letters?|epistles?|missives?|billets?|notes?\s+(?:from|to)|post(?:-office|man|mark|age)?|penny post|mail(?:-coach|bag)?|couriers?|express|messengers?|telegra(?:m|ms|ph|phed)|wired?\b|cablegram|despatch(?:es)?|dispatch(?:es)?|telephon\w*|rang (?:him |her |me )?up)\b",
        "enrich_mob": r"\b(coach(?:es|man)?|stage-coach|post-chaise|chaise|diligence|railway|rail-road|railroad|trains?|engine-driver|station|carriages?|steamers?|steam-?ship|packet-boat|packet|omnibus|cab|motor-?car)\b",
        "enrich_dark": r"\b(candles?|lamps?|lanterns?|gas-?light|gas-lamps?|gas\b|link-?boy|electric light|darkness|dark night|moonless|pitch[- ]dark|torch(?:es)?|night)\b",
    }
    return {k: re.compile(v, re.I) for k, v in seeds.items()}


def segment_work(args) -> list[dict]:
    pg_id, work_id, decade, split = args
    text = (WORK / "clean" / f"{pg_id}.txt").read_text(encoding="utf-8")
    spans = [(m.start(), m.end()) for m in WORD_RE.finditer(text)]
    n = len(spans)
    starts = list(range(0, n - PASSAGE_WORDS // 2, PASSAGE_WORDS))
    segs = []
    for i, s in enumerate(starts):
        e = min(n, s + PASSAGE_WORDS)
        segs.append((i, spans[s][0], spans[e - 1][1]))
    # skip front/back 3% (title pages, ads, indexes)
    lo, hi = int(len(segs) * 0.03), int(len(segs) * 0.97)
    body = segs[lo:hi] if hi - lo > 10 else segs
    rng = np.random.default_rng(int(hashlib.sha256(f"{SEED}:{work_id}".encode()).hexdigest()[:12], 16))
    chosen: dict[int, str] = {}
    pick = rng.choice(len(body), size=min(RANDOM_PER_WORK, len(body)), replace=False)
    for j in pick:
        chosen[body[j][0]] = "random"
    lex = load_lexicon()
    enrich_counts = {}
    for stratum, rx in lex.items():
        hits = [b for b in body if b[0] not in chosen and len(rx.findall(text, b[1], b[2])) >= 2]
        enrich_counts[stratum] = len(hits)
        if hits:
            sel = rng.choice(len(hits), size=min(ENRICH_CAP, len(hits)), replace=False)
            for j in sel:
                chosen[hits[j][0]] = stratum
    out = []
    by_idx = {s[0]: s for s in segs}
    eligible_n = len(body)
    for idx, stratum in sorted(chosen.items()):
        _, a, b = by_idx[idx]
        prev = by_idx.get(idx - 1)
        nxt = by_idx.get(idx + 1)
        ptxt = text[a:b]
        n_hits = enrich_counts.get(stratum, eligible_n)
        incl = (min(RANDOM_PER_WORK, eligible_n) / eligible_n) if stratum == "random" else (min(ENRICH_CAP, n_hits) / max(1, n_hits))
        out.append({
            "passage_id": f"pg{pg_id}_p{idx:05d}", "work_id": work_id, "pg_id": pg_id, "decade": int(decade),
            "split": split, "stratum": stratum, "char_start": a, "char_end": b,
            "text": ptxt,
            "ctx_before": text[prev[1]:prev[2]][-900:] if prev else "",
            "ctx_after": text[nxt[1]:nxt[2]][:600] if nxt else "",
            "text_sha256": sha(ptxt), "inclusion_prob": incl, "n_eligible": eligible_n,
            "n_stratum_hits": n_hits,
        })
    return out


def stage_passages(w: pd.DataFrame) -> pd.DataFrame:
    w = w[w.decade.between(1800, 1920)]
    args = list(zip(w.pg_id.astype(int), w.work_id, w.decade, w.split))
    rows = []
    with ProcessPoolExecutor() as ex:
        for r in ex.map(segment_work, args, chunksize=16):
            rows.extend(r)
    p = pd.DataFrame(rows)
    p.to_parquet(WORK / "passages.parquet", index=False)
    print("passages", len(p))
    print(p.groupby(["split", "stratum"]).size().unstack().to_string())
    return p


def main(stage: str) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    if stage in ("clean", "all"):
        df = stage_clean()
    else:
        df = pd.read_parquet(WORK / "cleaned.parquet")
    if stage in ("dedup", "all"):
        w = stage_dedup(df)
        w = stage_split(w)
    else:
        w = pd.read_parquet(WORK / "works.parquet")
    if stage in ("passages", "all"):
        stage_passages(w)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
