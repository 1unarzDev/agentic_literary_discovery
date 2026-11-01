import pytest

from ald.evidence import (
    EXACT, FUZZY, HALLUCINATED, NORMALIZED, collect_quotes, normalize, normalize_with_map, verify_output,
    verify_quote,
)


def span(src, ev):
    return src[ev.start:ev.end]


# --- normalization ----------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("“Hello,” she said.", '"Hello," she said.'),
    ("‘Tis the season’s end", "'Tis the season's end"),
    ("don’t", "don't"),
    ("``Quoth he,'' said I", '"Quoth he," said I'),
    ("word—word", "word-word"),
    ("word--word", "word-word"),
    ("word---word", "word-word"),
    ("word — word", "word-word"),
    ("word -- word", "word-word"),
    ("1810–1820", "1810-1820"),
    ("well-known", "well-known"),
    ("exam-\nple", "example"),
    ("exam-\r\n   ple", "example"),
    ("It was _very_ odd.", "It was very odd."),
    ("two  spaces\tand\n\nlines", "two spaces and lines"),
    ("  padded  ", "padded"),
    ("ﬁne ﬂow", "fine flow"),            # NFKC ligatures
    ("café", "café"),            # NFKC composes combining accent
    ("non breaking", "non breaking"),
    ("soft­hyphen", "softhyphen"),
    ("zero​width", "zerowidth"),
    ("Ellipsis…", "Ellipsis..."),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_normalize_keep_hyphenation_mode():
    assert normalize("well-\nknown", join_hyphenation=False) == "well-known"
    assert normalize("well-\nknown", join_hyphenation=True) == "wellknown"


def test_normalize_is_case_sensitive():
    assert normalize("The Post") != normalize("the post")


def test_span_map_points_into_raw():
    raw = "A “quote”—and _more_."
    norm, spans = normalize_with_map(raw)
    assert len(spans) == len(norm)
    for i, ch in enumerate(norm):
        s, e = spans[i]
        assert 0 <= s < e <= len(raw)
    # Every normalized letter maps to the same raw letter.
    for i, ch in enumerate(norm):
        if ch.isalpha():
            assert raw[spans[i][0]:spans[i][1]] == ch


def test_normalize_deterministic():
    raw = "He said, “I’ll go—to-morrow.” " * 20
    assert normalize(raw) == normalize(raw)


# --- verify_quote: statuses ---------------------------------------------------

SRC = ("“My dear Mr. Bennet,” said his lady to him one day, “have you heard that "
       "Netherfield Park is let at last?”\n\nMr. Bennet replied that he had not.\n\n"
       "“_You_ want to tell me, and I have no objection to hearing it.”\n"
       "The letter came by the even-\ning post—too late,  too late--for the coach "
       "had gone.")


def test_exact():
    ev = verify_quote("Mr. Bennet replied that he had not.", SRC)
    assert ev.status == EXACT
    assert span(SRC, ev) == "Mr. Bennet replied that he had not."


def test_exact_strips_outer_whitespace():
    ev = verify_quote("  Mr. Bennet replied  ", SRC)
    assert ev.status == EXACT and span(SRC, ev) == "Mr. Bennet replied"


def test_exact_first_occurrence():
    src = "too late, too late"
    ev = verify_quote("too late", src)
    assert (ev.start, ev.end) == (0, 8)


def test_curly_quotes_normalized():
    q = '"My dear Mr. Bennet," said his lady'
    ev = verify_quote(q, SRC)
    assert ev.status == NORMALIZED
    assert span(SRC, ev) == "“My dear Mr. Bennet,” said his lady"


def test_italics_underscores():
    ev = verify_quote("You want to tell me, and I have no objection", SRC)
    assert ev.status == NORMALIZED
    # The span starts at the first matched character; the leading italics
    # marker is not part of the match, the interior one is.
    assert span(SRC, ev) == "You_ want to tell me, and I have no objection"


def test_line_break_hyphenation_joined():
    ev = verify_quote("came by the evening post", SRC)
    assert ev.status == NORMALIZED
    assert span(SRC, ev) == "came by the even-\ning post"


def test_line_break_compound_kept():
    src = "It was a well-\nknown fact."
    ev = verify_quote("a well-known fact", src)
    assert ev.status == NORMALIZED
    assert span(src, ev) == "a well-\nknown fact"


def test_em_dash_vs_double_hyphen():
    # Source has an em-dash and a '--'; quote swaps them.
    ev = verify_quote("evening post--too late, too late—for the coach", SRC)
    assert ev.status == NORMALIZED
    assert span(SRC, ev).endswith("for the coach")
    assert span(SRC, ev).startswith("even-\ning post")


def test_spaced_dash_vs_tight_dash():
    src = "She waited — and waited."
    assert verify_quote("She waited--and waited.", src).status == NORMALIZED
    assert verify_quote("She waited - and waited.", src).status == NORMALIZED


def test_double_spaces_and_newlines():
    ev = verify_quote("too late, too late", SRC)
    # raw has "too late,  too late" (two spaces)
    assert ev.status == NORMALIZED
    assert span(SRC, ev) == "too late,  too late"


def test_quote_across_paragraph_break():
    ev = verify_quote("let at last?\" Mr. Bennet replied", SRC)
    assert ev.status == NORMALIZED
    assert span(SRC, ev) == "let at last?”\n\nMr. Bennet replied"


def test_quote_wrapped_in_quotes_and_ellipsis():
    ev = verify_quote("\"...Mr. Bennet replied that he had not...\"", SRC)
    assert ev.status == EXACT
    assert span(SRC, ev) == "Mr. Bennet replied that he had not"


def test_case_sensitive_not_normalized():
    ev = verify_quote("MR. BENNET REPLIED THAT HE HAD NOT.", SRC)
    assert ev.status not in (EXACT, NORMALIZED)


def test_fuzzy_flag_one_typo():
    q = "Mr. Bennet replyed that he had not."
    ev = verify_quote(q, SRC)
    assert ev.status == FUZZY
    assert not ev.verified
    assert ev.score is not None and ev.score >= 95
    assert "Bennet" in span(SRC, ev)


def test_fuzzy_never_verified():
    ev = verify_quote("have you heard that Netherfeld Park is let at last?", SRC)
    assert ev.status == FUZZY and ev.verified is False


def test_hallucinated():
    ev = verify_quote("The telegram arrived from London at noon.", SRC)
    assert ev.status == HALLUCINATED
    assert ev.start is None and ev.end is None


def test_empty_quote_is_hallucinated():
    assert verify_quote("", SRC).status == HALLUCINATED
    assert verify_quote("   ", SRC).status == HALLUCINATED


def test_paraphrase_is_not_verified():
    ev = verify_quote("Mrs. Bennet asked whether he knew Netherfield was rented.", SRC)
    assert ev.status in (HALLUCINATED, FUZZY)
    assert not ev.verified


def test_offsets_are_code_points_with_astral_chars():
    src = "\U0001F600 emoji then the letter—lost."
    ev = verify_quote("the letter-lost.", src)
    assert ev.status == NORMALIZED
    assert span(src, ev) == "the letter—lost."


def test_deterministic_repeat():
    q = "evening post--too late"
    a = verify_quote(q, SRC)
    b = verify_quote(q, SRC)
    assert a == b


def test_combining_accent_offsets():
    src = "the café was closed"
    ev = verify_quote("café was", src)
    assert ev.status == NORMALIZED
    assert span(src, ev) == "café was"


def test_gutenberg_full_paragraph():
    src = ("“I cannot go,” said she, “without the letter—and Mr.\n"
           "Darcy’s carriage will not come till to-morrow.”")
    q = "\"I cannot go,\" said she, \"without the letter -- and Mr. Darcy's carriage will not come till to-morrow.\""
    ev = verify_quote(q, src)
    assert ev.status == NORMALIZED
    assert ev.start == 0 and ev.end == len(src)


# --- output walking ------------------------------------------------------------

def test_collect_quotes_nested():
    out = {"has_obstacle": "yes", "obstacles": [
        {"evidence_quote": "a"}, {"evidence_quote": ""}, {"evidence_quote": ["b", "c"]}], "x": {"evidence_quote": "d"}}
    assert collect_quotes(out) == ["a", "b", "c", "d"]


def test_verify_output():
    src = "The coach had gone."
    out = {"obstacles": [{"evidence_quote": "The coach had gone."}, {"evidence_quote": "A train left."}]}
    evs = verify_output(out, src)
    assert [e.status for e in evs] == [EXACT, HALLUCINATED]
    assert evs[0].to_json() == {"quote": "The coach had gone.", "start": 0, "end": 19, "status": "exact"}
