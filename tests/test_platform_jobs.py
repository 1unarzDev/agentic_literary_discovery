import pytest

from pipeline.platform_jobs import check_jobs, outputs_for, panel_section, rc_job


def _job(split, **kw):
    return rc_job(job_id="v09b_x", stage="label", wave="v09b", split=split, pin_hash="a" * 64, shard_sha256="b" * 64,
                  shard_size=10, n_items=400, campaign="v09b", purpose="Label a shard.", est_seconds=600, **kw)


def test_confirmation_always_sealed():
    j = _job("confirmation", dup_group="v09b_0412")
    assert j["outputs"] == {"class": "sealed", "seal_id": "ald-confirmation-v09"}
    assert j["anti_affinity"] == {"keys": ["dup:v09b_0412"], "scope": "host"}
    assert _job("discovery")["outputs"] == {"class": "summary"}
    with pytest.raises(ValueError):
        _job("confirmation", seal_id=None)
    with pytest.raises(ValueError):
        outputs_for("other")
    check_jobs([_job("confirmation"), _job("discovery")])
    bad = _job("confirmation")
    bad["outputs"] = {"class": "summary"}
    with pytest.raises(ValueError):
        check_jobs([bad])


def test_sealed_panel_wording():
    panel_section(kind="progress", title="Confirmation progress", body={"done": 12000, "target": 80000}, concerns_sealed=True)
    with pytest.raises(ValueError):
        panel_section(kind="table", title="Confirmation", body={"done": 1}, concerns_sealed=True)
    with pytest.raises(ValueError):
        panel_section(kind="progress", title="Confirmation", body={"flag_rate": 0.2}, concerns_sealed=True)
    panel_section(kind="table", title="Discovery quality", body={"quote_ok": 0.9}, concerns_sealed=False)
