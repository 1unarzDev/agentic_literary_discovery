"""Self-check for one blind labelling batch (used by the labelling agents; reads the packet only).

usage: python3 -I analysis/claude_ref_check.py data/work/claude_ref/in/batch_07.txt data/work/claude_ref/batch_07.jsonl
Checks: every packet item labelled exactly once, enum values, and that each evidence_quote for a
"yes" is an exact substring of that item's PASSAGE (between the START/END markers).
"""
import json
import re
import sys

LOCI = {"material_external", "social_institutional", "internal_psychological"}
DOMS = {"DISTANCE_TRAVEL", "COMMUNICATION_INFORMATION", "DARKNESS_VISIBILITY", "ILLNESS_BODY_DEATH",
        "MONEY_PROPERTY_LAW", "SOCIAL_RANK_CONVENTION", "INTERPERSONAL_CONFLICT", "INNER_STATE",
        "NATURE_WEATHER", "OTHER"}
FC = {"none", "infrastructure", "accidental_loss", "intentional_withholding", "misinterpretation",
      "success_resolution"}
CLAR = {"vivid", "clear", "borderline"}


def packet(path):
    txt = open(path, encoding="utf-8").read()
    items = {}
    for blk in txt.split("##### ITEM ")[1:]:
        iid = blk.split("\n", 1)[0].strip()
        m = re.search(r"=== PASSAGE START \(judge and quote ONLY this\) ===\n(.*?)\n=== PASSAGE END ===", blk, re.S)
        items[iid] = m.group(1)
    return items


def main(pk, out):
    items = packet(pk)
    seen, errs = set(), []
    for n, line in enumerate(open(out, encoding="utf-8"), 1):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except Exception as e:
            errs.append(f"line {n}: bad JSON {e}")
            continue
        i = d.get("item_id")
        if i not in items:
            errs.append(f"line {n}: unknown item_id {i}")
            continue
        if i in seen:
            errs.append(f"{i}: duplicate")
        seen.add(i)
        h = d.get("has_obstacle")
        if h not in ("yes", "no", "insufficient_context"):
            errs.append(f"{i}: has_obstacle {h!r}")
        if h == "yes":
            if d.get("locus") not in LOCI:
                errs.append(f"{i}: locus {d.get('locus')!r}")
            doms = d.get("domains") or []
            if not (1 <= len(doms) <= 2) or any(x not in DOMS for x in doms):
                errs.append(f"{i}: domains {doms!r}")
            fc = d.get("failure_cause", "none")
            if fc not in FC or (fc != "none") != ("COMMUNICATION_INFORMATION" in doms):
                errs.append(f"{i}: failure_cause {fc!r} vs domains {doms!r}")
            if d.get("clarity") not in CLAR:
                errs.append(f"{i}: clarity {d.get('clarity')!r}")
            q = d.get("evidence_quote") or ""
            if q not in items[i]:
                errs.append(f"{i}: QUOTE NOT VERBATIM IN PASSAGE: {q[:80]!r}")
            elif not (6 <= len(q.split()) <= 20):
                errs.append(f"{i}: quote has {len(q.split())} words (need 6-20)")
        if not d.get("rationale"):
            errs.append(f"{i}: no rationale")
    missing = sorted(set(items) - seen)
    if missing:
        errs.append(f"missing items: {missing}")
    print(f"{len(seen)}/{len(items)} items labelled; {len(errs)} problems")
    for e in errs:
        print("  " + e)
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main(*sys.argv[1:3])
