"""Parse the official Project Gutenberg RDF catalog (rdf-files.tar.bz2) into two small Parquet tables.

The archive is untrusted downloaded data: it is streamed (never extracted to disk), every member must be a
regular file named ``cache/epub/<n>/pg<n>.rdf``, members over 2 MB or containing a DOCTYPE/ENTITY declaration
are skipped, and parsing uses the stdlib expat parser (libexpat >= 2.4 has billion-laughs protection).

Outputs (data/work/):
  pg_rdf_ebooks.parquet  pg_id, downloads, issued, title, creators (JSON list of [agent_id, role]),
                         first_author_agent
  pg_rdf_agents.parquet  agent_id, name, aliases (JSON list), birth, death, webpages (JSON list)

Run (from the repo root, never from inside data/raw/rdf):
  uv run python -I pipeline/pg_rdf.py data/raw/rdf/rdf-files.tar.bz2
"""
from __future__ import annotations

import json
import re
import sys
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/work"

NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dcterms": "http://purl.org/dc/terms/",
    "pgterms": "http://www.gutenberg.org/2009/pgterms/",
    "marcrel": "http://id.loc.gov/vocabulary/relators/",
}
RDF_ABOUT = f"{{{NS['rdf']}}}about"
RDF_RES = f"{{{NS['rdf']}}}resource"
MEMBER_RE = re.compile(r"^(?:\./)?cache/epub/(\d+)/pg\1\.rdf$")
AGENT_RE = re.compile(r"agents/(\d+)$")
MAX_BYTES = 2_000_000
# Roles that make an agent the work's author, in preference order. dcterms:creator is PG's "Author".
AUTHOR_ROLES = ("creator", "aut")


def _int(s: str | None) -> int | None:
    try:
        return int(str(s).strip())
    except (TypeError, ValueError):
        return None


def parse_rdf(data: bytes) -> tuple[dict, list[dict]] | None:
    """One pgNNN.rdf document -> (ebook row, [agent rows]). Returns None for unsafe/unparseable input."""
    if len(data) > MAX_BYTES or b"<!DOCTYPE" in data[:4096] or b"<!ENTITY" in data:
        return None
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    eb = root.find("pgterms:ebook", NS)
    if eb is None:
        return None
    m = re.search(r"ebooks/(\d+)$", eb.get(RDF_ABOUT, ""))
    if not m:
        return None
    pg_id = int(m.group(1))
    creators: list[list] = []
    agents: list[dict] = []
    for child in eb:
        tag = child.tag
        if tag.startswith(f"{{{NS['dcterms']}}}creator"):
            role = "creator"
        elif tag.startswith(f"{{{NS['marcrel']}}}"):
            role = tag.split("}", 1)[1]
        else:
            continue
        for ag in child.findall("pgterms:agent", NS):
            am = AGENT_RE.search(ag.get(RDF_ABOUT, ""))
            if not am:
                continue
            aid = int(am.group(1))
            creators.append([aid, role])
            agents.append({
                "agent_id": aid,
                "name": (ag.findtext("pgterms:name", default="", namespaces=NS) or "").strip(),
                "aliases": json.dumps([a.text.strip() for a in ag.findall("pgterms:alias", NS) if a.text]),
                "birth": _int(ag.findtext("pgterms:birthdate", namespaces=NS)),
                "death": _int(ag.findtext("pgterms:deathdate", namespaces=NS)),
                "webpages": json.dumps([w.get(RDF_RES) for w in ag.findall("pgterms:webpage", NS) if w.get(RDF_RES)]),
            })
    first = next((a for r in AUTHOR_ROLES for a, rr in creators if rr == r), None)
    row = {
        "pg_id": pg_id,
        "downloads": _int(eb.findtext("pgterms:downloads", namespaces=NS)),
        "issued": eb.findtext("dcterms:issued", default="", namespaces=NS),
        "title": (eb.findtext("dcterms:title", default="", namespaces=NS) or "").split("\n")[0][:300],
        "creators": json.dumps(creators),
        "first_author_agent": first,
    }
    return row, agents


def parse_archive(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    books, agents, skipped = [], {}, 0
    with tarfile.open(path, "r|bz2") as t:
        for mem in t:
            if not mem.isfile() or not MEMBER_RE.match(mem.name) or mem.size > MAX_BYTES:
                continue
            f = t.extractfile(mem)
            if f is None:
                continue
            res = parse_rdf(f.read())
            if res is None:
                skipped += 1
                continue
            row, ags = res
            books.append(row)
            for a in ags:
                agents.setdefault(a["agent_id"], a)
    print(f"parsed {len(books)} ebooks, {len(agents)} agents, skipped {skipped}")
    return pd.DataFrame(books), pd.DataFrame(list(agents.values()))


def main(argv: list[str]) -> None:
    src = Path(argv[1] if len(argv) > 1 else ROOT / "data/raw/rdf/rdf-files.tar.bz2")
    books, agents = parse_archive(src)
    OUT.mkdir(parents=True, exist_ok=True)
    books.to_parquet(OUT / "pg_rdf_ebooks.parquet", index=False)
    agents.to_parquet(OUT / "pg_rdf_agents.parquet", index=False)
    print("wrote", OUT / "pg_rdf_ebooks.parquet", OUT / "pg_rdf_agents.parquet")


if __name__ == "__main__":
    main(sys.argv)
