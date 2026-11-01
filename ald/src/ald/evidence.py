"""Deterministic verification of model-quoted evidence against the raw passage.

Status ladder (first that applies wins):

* ``exact``        the quote (whitespace-trimmed) is a raw substring of the passage.
* ``normalized``   the quote matches after both sides are normalized
                   (see :func:`normalize`); offsets are mapped back to raw text.
* ``fuzzy_flag``   rapidfuzz ``partial_ratio`` >= 95 on the normalized forms.
                   Offsets are reported for inspection but this is NEVER verified.
* ``hallucinated`` nothing matched; offsets are ``None``.

All offsets are Python ``str`` indices (Unicode code points) into the raw
passage text, half-open ``[start, end)``.

Normalization (applied identically to quote and source, case-sensitive):

1. NFKC per grapheme cluster (base char + combining marks).
2. Soft hyphens and zero-width characters are dropped; NBSP etc. become spaces.
3. Curly / low / prime quotes become ``'`` or ``"``; the TeX-ish ```` `` ```` and
   ``''`` pairs become ``"``.
4. Gutenberg italics markers ``_`` are dropped.
5. Dashes: every dash run (hyphen, em/en/figure dashes, ``--``, ``---``,
   spaced hyphens), together with its surrounding whitespace, becomes a single
   ``-``. So ``word—word``, ``word -- word``, ``word — word`` and ``word-word``
   are all ``word-word``.
   Line-break hyphenation (letter, one short hyphen, whitespace containing a
   newline, letter) is ambiguous: ``exam-\\nple`` is "example" but
   ``well-\\nknown`` is "well-known". Normalization therefore has two modes:
   ``join_hyphenation=True`` drops the hyphen and the break, ``False`` keeps a
   ``-``. :func:`verify_quote` tries both modes for the source and the quote.
6. Runs of whitespace collapse to a single space; leading/trailing trimmed.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, asdict
from typing import Any, Iterable

from rapidfuzz import fuzz

EXACT = "exact"
NORMALIZED = "normalized"
FUZZY = "fuzzy_flag"
HALLUCINATED = "hallucinated"
VERIFIED_STATUSES = frozenset({EXACT, NORMALIZED})

FUZZY_THRESHOLD = 95.0

_SINGLE_QUOTES = "‘’‚‛′‵ʼʻ`´"
_DOUBLE_QUOTES = "“”„‟″‶«»‹›"
# Short hyphens (may be intra-word) vs. long dashes (always punctuation).
_SHORT_HYPHENS = "-‐‑"
_LONG_DASHES = "‒–—―−⸺⸻﹘﹣－"
_DASHES = _SHORT_HYPHENS + _LONG_DASHES
_DROP = "­​‌‍⁠﻿_"
_TRIM_CHARS = " \"'.…"  # stripped from quote ends as a fallback candidate


@dataclass(frozen=True)
class Evidence:
    quote: str
    start: int | None
    end: int | None
    status: str
    score: float | None = None

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        if d["score"] is None:
            d.pop("score")
        return d

    @property
    def verified(self) -> bool:
        return self.status in VERIFIED_STATUSES


def _clusters(text: str) -> Iterable[tuple[int, int]]:
    """Yield [start, end) spans of base char + following combining marks."""
    n = len(text)
    i = 0
    while i < n:
        j = i + 1
        while j < n and unicodedata.combining(text[j]):
            j += 1
        yield i, j
        i = j


def _stage1(text: str) -> list[tuple[str, int, int]]:
    """NFKC + character mapping. Returns (char, raw_start, raw_end) triples."""
    out: list[tuple[str, int, int]] = []
    for s, e in _clusters(text):
        piece = unicodedata.normalize("NFKC", text[s:e])
        for ch in piece:
            if ch in _DROP:
                continue
            if ch in _SINGLE_QUOTES:
                ch = "'"
            elif ch in _DOUBLE_QUOTES:
                ch = '"'
            elif ch.isspace():
                ch = "\n" if ch in "\n\r  \x0b\x0c\x85" else " "
            out.append((ch, s, e))
    # `` and '' -> "
    merged: list[tuple[str, int, int]] = []
    i = 0
    while i < len(out):
        ch, s, e = out[i]
        if ch in "'" and i + 1 < len(out) and out[i + 1][0] == ch and text[s:e] in ("'", "`") \
                and text[out[i + 1][1]:out[i + 1][2]] == text[s:e]:
            merged.append(('"', s, out[i + 1][2]))
            i += 2
            continue
        merged.append((ch, s, e))
        i += 1
    return merged


def _stage2(chars: list[tuple[str, int, int]], raw: str, join: bool) -> list[tuple[str, int, int]]:
    """Hyphen/dash handling and whitespace collapse."""
    out: list[tuple[str, int, int]] = []
    n = len(chars)
    i = 0

    def raw_char(k: int) -> str:
        return raw[chars[k][1]:chars[k][2]]

    while i < n:
        ch, s, e = chars[i]
        is_dash = ch == "-" or raw_char(i) in _DASHES or ch in _DASHES
        if is_dash:
            j = i
            while j < n and (chars[j][0] == "-" or chars[j][0] in _DASHES):
                j += 1
            short = (j - i) == 1 and raw_char(i) in _SHORT_HYPHENS
            prev_alpha = bool(out) and out[-1][0].isalpha()
            # Look past whitespace after the run.
            k = j
            saw_newline = False
            while k < n and chars[k][0] in " \n":
                saw_newline |= chars[k][0] == "\n"
                k += 1
            next_alpha = k < n and chars[k][0].isalpha()
            if join and short and prev_alpha and next_alpha and saw_newline:
                # Line-break hyphenation: drop hyphen + break.
                i = k
                continue
            # Punctuation dash: absorb surrounding whitespace into one '-'.
            while out and out[-1][0] == " ":
                out.pop()
            out.append(("-", s, chars[j - 1][2]))
            i = k
            continue
        if ch in " \n":
            j = i
            while j < n and chars[j][0] in " \n":
                j += 1
            if out and out[-1][0] != "-" and j < n:
                out.append((" ", s, chars[j - 1][2]))
            i = j
            continue
        out.append((ch, s, e))
        i += 1
    return out


def normalize_with_map(text: str, join_hyphenation: bool = True) -> tuple[str, list[tuple[int, int]]]:
    """Normalize ``text``; return (normalized, spans) where spans[i] is the raw
    [start, end) span that produced normalized char i."""
    chars = _stage2(_stage1(text), text, join_hyphenation)
    norm = "".join(c for c, _, _ in chars)
    spans = [(s, e) for _, s, e in chars]
    return norm, spans


def normalize(text: str, join_hyphenation: bool = True) -> str:
    return normalize_with_map(text, join_hyphenation)[0]


def _map_back(spans: list[tuple[int, int]], i: int, j: int) -> tuple[int, int]:
    """Map normalized [i, j) to raw [start, end)."""
    return spans[i][0], spans[j - 1][1]


def _candidates(quote: str) -> list[str]:
    q = quote.strip()
    cands = [q]
    trimmed = q.strip(_TRIM_CHARS + "“”‘’")
    if trimmed and trimmed != q:
        cands.append(trimmed)
    return cands


def verify_quote(quote: str, source: str, fuzzy_threshold: float = FUZZY_THRESHOLD) -> Evidence:
    """Locate ``quote`` in ``source`` (the raw passage text)."""
    if quote is None or not str(quote).strip():
        return Evidence(quote=quote or "", start=None, end=None, status=HALLUCINATED)
    quote = str(quote)
    cands = _candidates(quote)

    # 1. exact raw substring
    for q in cands:
        idx = source.find(q)
        if idx >= 0:
            return Evidence(quote=quote, start=idx, end=idx + len(q), status=EXACT)

    # 2. normalized substring (both hyphenation modes, source and quote)
    variants = [normalize_with_map(source, True), normalize_with_map(source, False)]
    norm_cands: list[str] = []
    for q in cands:
        for mode in (True, False):
            nq = normalize(q, mode).strip(" ")
            if nq and nq not in norm_cands:
                norm_cands.append(nq)
    for norm_src, spans in variants:
        for nq in norm_cands:
            idx = norm_src.find(nq)
            if idx >= 0:
                s, e = _map_back(spans, idx, idx + len(nq))
                return Evidence(quote=quote, start=s, end=e, status=NORMALIZED)
    norm_src, spans = variants[0]

    # 3. fuzzy (flag only)
    if norm_src and norm_cands:
        best = None
        for nq in norm_cands:
            al = fuzz.partial_ratio_alignment(nq, norm_src)
            if al is None:
                continue
            if best is None or al.score > best[0].score:
                best = (al, nq)
        if best is not None and best[0].score >= fuzzy_threshold:
            al = best[0]
            # rapidfuzz reports src_* for the first argument (the quote) and
            # dest_* for the second (the normalized source).
            ds, de = al.dest_start, al.dest_end
            if de > ds:
                s, e = _map_back(spans, ds, de)
            else:
                s, e = None, None
            return Evidence(quote=quote, start=s, end=e, status=FUZZY, score=round(al.score, 2))

    return Evidence(quote=quote, start=None, end=None, status=HALLUCINATED)


def collect_quotes(output: Any, keys: Iterable[str] = ("evidence_quote",)) -> list[str]:
    """Walk a model output and collect every string under one of ``keys``
    (string or list of strings), in document order."""
    keys = tuple(keys)
    found: list[str] = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k in keys:
                    if isinstance(v, str):
                        if v.strip():
                            found.append(v)
                    elif isinstance(v, list):
                        found.extend(x for x in v if isinstance(x, str) and x.strip())
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(output)
    return found


def verify_output(output: Any, source: str, keys: Iterable[str] = ("evidence_quote",)) -> list[Evidence]:
    return [verify_quote(q, source) for q in collect_quotes(output, keys)]
