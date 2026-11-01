import gzip
import json

import pytest

from ald.results import Checkpoint, JobStore, Outbox, decode_jsonl_gz, encode_jsonl_gz, sha256_bytes, write_jsonl_gz

LINES = [{"passage_id": f"p{i}", "output": {"q": "“quote”—"}, "valid_schema": True} for i in range(5)]


def test_roundtrip(tmp_path):
    data, sha = write_jsonl_gz(tmp_path / "r.jsonl.gz", LINES)
    assert decode_jsonl_gz((tmp_path / "r.jsonl.gz").read_bytes()) == LINES
    assert sha == sha256_bytes(data)


def test_deterministic_bytes():
    assert encode_jsonl_gz(LINES) == encode_jsonl_gz([dict(reversed(list(l.items()))) for l in LINES])


def test_utf8_and_lf():
    raw = gzip.decompress(encode_jsonl_gz(LINES))
    assert b"\r\n" not in raw and raw.endswith(b"\n")
    assert "—".encode("utf-8") in raw  # not ascii-escaped


def test_checkpoint_append_and_torn_tail(tmp_path):
    ck = Checkpoint(tmp_path / "j", fsync_every=2)
    for l in LINES[:3]:
        ck.append(l)
    ck.close()
    with open(ck.path, "ab") as f:
        f.write(b'{"passage_id": "p9", "outp')  # crash mid-write
    ck2 = Checkpoint(tmp_path / "j")
    assert set(ck2.load()) == {"p0", "p1", "p2"}
    ck2.append(LINES[3])
    ck2.close()
    assert set(Checkpoint(tmp_path / "j").load()) == {"p0", "p1", "p2", "p3"}


def test_jobstore_cache_keyed_by_pin(tmp_path):
    st = JobStore(tmp_path)
    st.write_meta("job:1", {"job_id": "job:1", "pin_hash": "P1"})
    ck = st.checkpoint("job:1")
    ck.append({"passage_id": "a", "pin_hash": "P1"})
    ck.append({"passage_id": "b", "pin_hash": "P1"})
    ck.close()
    assert ":" not in st.job_dir("job:1").name
    assert set(st.cached_lines("P1", {"a", "c"})) == {"a"}
    assert st.cached_lines("P2", {"a"}) == {}


class Err(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.status = status


def test_outbox_flush_ack_retry_reject(tmp_path):
    ob = Outbox(tmp_path)
    ob.add("j1", b"a", {"h": "1"}, partial=False, n_lines=1, created=1)
    ob.add("j2", b"b", {"h": "2"}, partial=True, n_lines=1, created=2)
    ob.add("j3", b"c", {"h": "3"}, partial=False, n_lines=1, created=3)
    calls = []

    def put(job_id, body, headers, partial):
        calls.append((job_id, partial))
        if job_id == "j2":
            raise Err(503)
        if job_id == "j3":
            raise Err(409)
        return {"status": "stored"}

    acked = []
    c = ob.flush(put, now=100.0, on_ack=lambda e, r: acked.append(e.job_id))
    assert c == {"acked": 1, "rejected": 1, "deferred": 1}
    assert calls[0] == ("j1", False)  # finals first
    assert acked == ["j1"]
    assert [e.job_id for e in ob.entries()] == ["j2"]
    assert (tmp_path / "outbox" / "rejected").exists()
    # j2 is backed off: not retried before next_attempt.
    before = len(calls)
    c = ob.flush(put, now=101.0)
    assert c["deferred"] == 1 and len(calls) == before
    c = ob.flush(lambda *a: {"status": "duplicate"}, now=10_000.0)
    assert c["acked"] == 1 and ob.entries() == []


def test_outbox_survives_restart(tmp_path):
    Outbox(tmp_path).add("j1", b"body", {"X": "1"}, partial=True, n_lines=3, created=1)
    es = Outbox(tmp_path).entries()
    assert len(es) == 1 and es[0].partial and es[0].blob.read_bytes() == b"body"


def test_outbox_network_error_stops_batch(tmp_path):
    ob = Outbox(tmp_path)
    for i in range(3):
        ob.add(f"j{i}", b"x%d" % i, {}, partial=False, n_lines=1, created=i)
    n = []

    def put(*a):
        n.append(1)
        raise ConnectionError("down")

    ob.flush(put, now=0, is_network_error=lambda e: isinstance(e, ConnectionError))
    assert len(n) == 1 and len(ob.entries()) == 3
