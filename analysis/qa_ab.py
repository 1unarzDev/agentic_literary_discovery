"""A/B a label-prompt change on a frozen QA sample, scored against the QA reviewer's reference.

  build  write data/work/label_ab_qa2/{variants.json,passages.jsonl,ref.jsonl}
         variants: v0   = production label prompt (registry/models.v1.json, read-only)
                   v09a = v0 + the label_pass_2 proposed edits (docs/qa/label_pass_2.md, E1-E6)
  run    use the existing harness (GPU; obey the lock):
           flock /tmp/aacv_gpu.lock uv run python -I analysis/bench_label_ab.py run \
               --dir data/work/label_ab_qa2 --variant v0   --par 4 --tag qa2
           flock /tmp/aacv_gpu.lock uv run python -I analysis/bench_label_ab.py run \
               --dir data/work/label_ab_qa2 --variant v09a --par 4 --tag qa2
  score  uv run --with pandas,rapidfuzz python -I analysis/qa_ab.py score
         (few-shot source passages are excluded from scoring)

Reference = docs/qa/label_pass_2_ref.csv (passage_id, truth, ref_domains, ref_locus).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/work/label_ab_qa2"
REF = ROOT / "docs/qa/label_pass_2_ref.csv"
FEWSHOT_IDS = {"pg8938_p00080", "pg72909_p00168"}  # used as few-shot examples in v09a -> never scored

# ---------------------------------------------------------------- the proposed edits (keep in sync with label_pass_2.md)
E1_TEST = """
**Three-part test (apply before answering yes).** Say to yourself: (a) WHO wants WHAT; (b) WHAT, inside the PASSAGE, stops, delays or endangers it; (c) WHERE the passage shows it changing what the character can do or what happens. If you cannot point to (b) and (c) inside the PASSAGE, answer `no`.

**Also not obstacles:** mild discomfort, shyness, fatigue or nervousness that the character goes ahead despite; banter, teasing or flirtation; a character merely wondering or speculating; procedural or technical description of work, hunting or travel in which nothing goes wrong; a scene in which the goal is achieved and no impediment remains; an obstacle that appears only in CONTEXT BEFORE/AFTER.
"""
E3_RANK = ("| SOCIAL_RANK_CONVENTION | Class, propriety, reputation, marriage rules, gender norms, family authority as *a rule* "
           "| \"a governess cannot marry the heir\"; scandal would ruin her |")
E3_RANK_NEW = ("| SOCIAL_RANK_CONVENTION | Class, propriety, reputation, marriage rules, gender norms, family authority as *a rule*: "
               "the barrier would stop anyone in that position, not just this character with this person. A particular person's "
               "wishes, dislike, schemes or commands are INTERPERSONAL_CONFLICT; a party, dress or etiquette that is merely present is not an obstacle "
               "| \"a governess cannot marry the heir\"; scandal would ruin her |")
E4_LOCUS = ("**Override the default whenever the passage says otherwise.** For example, illness that is clearly hysteria or "
            "\"nerves\" may be internal.")
E4_LOCUS_NEW = (E4_LOCUS + " Locus follows the *proximate source*, not the domain: death or injury inflicted by people is "
                "social; animals and terrain are material; the blocked character's own pride, fear or conscience is internal even "
                "when the domain is SOCIAL_RANK_CONVENTION.")
E5_FC = "  - `none`."
E5_FC_NEW = ("  - `none`.\n- failure_cause and message_valence must be `none` unless COMMUNICATION_INFORMATION is in `domains`. "
             "A secret forgotten or lost over time is `accidental_loss`; the cost, length or slowness of post or telegraph is "
             "`infrastructure`; `intentional_withholding` needs someone who deliberately keeps or intercepts the message or fact.")
E6_DARK = "| DARKNESS_VISIBILITY | Not being able to see: night, fog, lack of light, concealment by darkness |"
E6_DARK_NEW = ("| DARKNESS_VISIBILITY | Not being able to see: night, fog, lack of light, concealment by darkness or terrain. "
               "Include it whenever not-seeing is what stops the character, even if weather or terrain causes it |")
E6_NIGHT = "danger | concealment | intimacy | labor | leisure | none."
E6_NIGHT_NEW = ("danger | concealment | intimacy | labor | leisure | none. `concealment` = someone hides or moves unseen "
                "thanks to the dark; `danger` = the dark exposes someone to harm or terror. Use `none` if the scene is not at night or in darkness.")
E2_TAIL_OLD = "evidence_quote must be copied verbatim: 8-30 consecutive words from PASSAGE, unchanged."
E2_TAIL_NEW = ("evidence_quote must be copied verbatim: 8-30 consecutive words that lie ENTIRELY inside PASSAGE, unchanged. "
               "Never quote CONTEXT BEFORE/AFTER. If the key sentence begins before the PASSAGE starts or runs past its end, copy "
               "only the part inside PASSAGE. Never use '...', never drop words, never join two sentences or two speakers.")
FEWSHOT = """

## Two worked examples (from the corpus)
1. "Certainly they are not of such strength that I do not gladly seize upon the favor thus extended, and count myself honored and happy." — The speaker is shy of meeting a queen but goes ahead gladly. Nothing impedes him → `has_obstacle: no`.
2. "And Bart, deciding that his sister's whims had already imposed far too many restrictions upon both his own activities and Carver's, carefully refrained from delivering the message." → `yes`, COMMUNICATION_INFORMATION, failure_cause `intentional_withholding`, locus `social_institutional`.
"""
USER_NEW = ("CONTEXT BEFORE (orientation only; never quote it):\n{ctx_before}\n\n"
            "=== PASSAGE START (judge and quote ONLY this) ===\n{text}\n=== PASSAGE END ===\n\n"
            "CONTEXT AFTER (orientation only; never quote it):\n{ctx_after}")


def v09a_system(sys0: str) -> str:
    s = sys0
    for old, new in [(E3_RANK, E3_RANK_NEW), (E4_LOCUS, E4_LOCUS_NEW), (E5_FC, E5_FC_NEW), (E6_DARK, E6_DARK_NEW),
                     (E6_NIGHT, E6_NIGHT_NEW), (E2_TAIL_OLD, E2_TAIL_NEW)]:
        assert s.count(old) == 1, f"anchor not unique/absent: {old[:60]}"
        s = s.replace(old, new)
    anchor = "When the passage is too fragmentary to tell, choose `insufficient_context`."
    assert s.count(anchor) == 1
    s = s.replace(anchor, E1_TEST.strip() + "\n\n" + anchor)
    anchor2 = "6. **Don't use outside knowledge** of the book. Judge from the passage and its context only."
    assert s.count(anchor2) == 1
    s = s.replace(anchor2, anchor2 + "\n7. **Comic, epistolary and dialect passages** follow the same three-part test; a letter-writer's reflections are not an obstacle unless the letter reports something blocking a goal." + FEWSHOT)
    return s


def build() -> None:
    reg = json.loads((ROOT / "registry/models.v1.json").read_text(encoding="utf-8"))
    st = reg["stages"]["label"]
    v0 = dict(system=st["system_template"], schema=st["schema"], user=st["user_template"],
              num_ctx=st["num_ctx"], num_predict=st["num_predict"])
    v1 = dict(v0, system=v09a_system(st["system_template"]), user=USER_NEW)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "variants.json").write_text(json.dumps({"v0": v0, "v09a": v1}, indent=1, ensure_ascii=False), encoding="utf-8")
    qa = sorted((ROOT / "data/work/qa").glob("label_*.jsonl"))
    src = Path(sys.argv[2]) if len(sys.argv) > 2 else qa[-1]
    rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    with open(OUT / "passages.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({k: r[k] for k in ("passage_id", "text", "ctx_before", "ctx_after")} | {"era": r["era"]},
                               ensure_ascii=False) + "\n")
    print("variants v0/v09a; system chars", len(v0["system"]), "->", len(v1["system"]), "| passages", len(rows), "from", src.name)


def score() -> None:
    import pandas as pd
    sys.path.insert(0, str(ROOT / "ald/src"))
    from ald.evidence import verify_quote
    ref = pd.read_csv(REF, keep_default_na=False).set_index("passage_id")
    ps = {json.loads(l)["passage_id"]: json.loads(l) for l in (OUT / "passages.jsonl").read_text(encoding="utf-8").splitlines()}
    rows = []
    for f in sorted((OUT / "runs").glob("*.jsonl")):
        lines = f.read_text(encoding="utf-8").splitlines()
        meta = json.loads(lines[0])["meta"]
        for l in lines[1:]:
            r = json.loads(l)
            pid = r["id"]
            if pid in FEWSHOT_IDS or pid not in ref.index or ref.loc[pid, "truth"] == "nonfic":
                continue
            try:
                o = json.loads(r["content"])
            except Exception:  # noqa: BLE001
                o = {}
            t = ref.loc[pid]
            yes = o.get("has_obstacle") == "yes"
            doms = set(o.get("domains") or [])
            refd = set(t.ref_domains.split(";")) if t.ref_domains else set()
            q = o.get("evidence_quote") or ""
            qs = verify_quote(q, ps[pid]["text"]).status if (yes and q) else None
            rows.append({"variant": meta["variant"], "pph": meta["pph"], "pid": pid, "era": ps[pid]["era"],
                         "truth_yes": t.truth == "yes", "pred_yes": yes,
                         "dom_ok": bool(doms & refd) if (yes and t.truth == "yes") else None,
                         "locus_ok": (o.get("locus") == t.ref_locus) if (yes and t.truth == "yes") else None,
                         "is_rank": "SOCIAL_RANK_CONVENTION" in doms,
                         "quote_ok": qs in ("exact", "normalized") if qs else None})
    d = pd.DataFrame(rows)
    if d.empty:
        raise SystemExit("no runs yet")
    g = d.groupby("variant")
    out = pd.DataFrame({
        "n": g.size(), "pph": g.pph.first(),
        "yes_rate": g.pred_yes.mean(), "has_acc": g.apply(lambda x: (x.pred_yes == x.truth_yes).mean()),
        "yes_precision": g.apply(lambda x: x[x.pred_yes].truth_yes.mean()),
        "yes_recall": g.apply(lambda x: x[x.truth_yes].pred_yes.mean()),
        "dom_ok": g.dom_ok.apply(lambda s: s.dropna().mean()), "locus_ok": g.locus_ok.apply(lambda s: s.dropna().mean()),
        "rank_share_of_yes": g.apply(lambda x: x[x.pred_yes].is_rank.mean()),
        "quote_in_passage": g.quote_ok.apply(lambda s: s.dropna().mean())}).round(3)
    print(out.T.to_string())
    print("\nhas_obstacle accuracy by era:")
    print(d.assign(acc=d.pred_yes == d.truth_yes).pivot_table(index="era", columns="variant", values="acc").round(2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "score"])
    ap.add_argument("src", nargs="?")
    a = ap.parse_args()
    build() if a.cmd == "build" else score()


if __name__ == "__main__":
    main()
