"""Coverage-continuity audit for the massive_stock_day store (scripts/audit_massive_store).

Pins the 2026-07-03 incident tripwire: ground truth is the anchor parquets — a
planted interior hole fails, a manifest claiming freshness the anchors can't back
fails, staleness only flags, and a checkout without the heavy store (CI runners)
is skipped, never failed.  Synthetic stores in tmp dirs; cfg thresholds passed
explicitly so repo config drift can't move these tests.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts import audit_common, audit_massive_store as ams

ASOF = date(2026, 7, 3)

CFG = dict(audit_common.quality_cfg())
CFG.update({"massive_min_files": 3, "massive_max_gap_bdays": 5,
            "massive_stale_bdays": 5, "massive_manifest_ahead_bdays": 2})


def _bars(end: str, periods: int = 120) -> pd.DataFrame:
    idx = pd.bdate_range(end=end, periods=periods)
    df = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
                       "volume": 1_000_000, "transactions": 10_000}, index=idx)
    df.index.name = "date"
    return df


def _store(tmp_path: Path, end: str = "2026-07-02", hole: tuple[str, str] | None = None,
           manifest_latest: str | None = "auto", drop_anchor: str | None = None) -> Path:
    """Build a synthetic store: all five anchors + a manifest.  `hole` drops the
    bars in [start, stop] from EVERY anchor (a whole-market day hole, like the
    incident).  manifest_latest='auto' matches the content; a date string plants a
    lying manifest; None omits the manifest."""
    d = tmp_path / "massive_stock_day"
    d.mkdir(parents=True)
    for t in ams.ANCHORS:
        if t == drop_anchor:
            continue
        df = _bars(end)
        if hole:
            df = df[(df.index < hole[0]) | (df.index > hole[1])]
        df.to_parquet(d / f"{t}.parquet")
    if manifest_latest is not None:
        latest = end if manifest_latest == "auto" else manifest_latest
        (d / "_manifest.json").write_text(json.dumps(
            {"store": "massive_stock_day", "n_tickers": 5, "latest_date": latest}))
    return tmp_path


def _run(data_dir: Path, tmp_path: Path, cfg: dict = CFG) -> dict:
    return ams.run(cfg=cfg, asof=ASOF, out_dir=tmp_path / "quality", data_dir=data_dir)


def test_clean_store_passes(tmp_path):
    doc = _run(_store(tmp_path), tmp_path)
    u = doc["universes"][0]
    assert not u["skipped"] and u["n_failed"] == 0
    assert doc["fail_pct"] == 0.0


def test_interior_hole_fails_continuity(tmp_path):
    # A ~3-week whole-market hole (the incident, scaled down) must trip every anchor.
    doc = _run(_store(tmp_path, hole=("2026-05-11", "2026-05-29")), tmp_path)
    u = doc["universes"][0]
    assert u["n_failed"] == len(ams.ANCHORS)
    assert all("coverage hole" in f["reasons"][0] for f in u["failed"])
    assert doc["fail_pct"] > 5.0        # would abort the collect gate


def test_holiday_scale_gaps_pass(tmp_path):
    # A 2-bday closure (e.g. holiday + an ad-hoc closure) stays under the limit.
    doc = _run(_store(tmp_path, hole=("2026-06-18", "2026-06-19")), tmp_path)
    assert doc["universes"][0]["n_failed"] == 0


def test_lying_manifest_fails(tmp_path):
    # Content ends 2026-03-12 but the manifest claims 2026-06-30 — the incident
    # signature (freshness the anchors cannot back).
    doc = _run(_store(tmp_path, end="2026-03-12", manifest_latest="2026-06-30"), tmp_path)
    u = doc["universes"][0]
    reasons = {f["name"]: f["reasons"] for f in u["failed"]}
    assert "_manifest" in reasons
    assert "cannot back" in reasons["_manifest"][0]


def test_stale_store_flags_but_does_not_fail(tmp_path):
    # Honest manifest + old content: staleness is a FLAG (suite convention).
    doc = _run(_store(tmp_path, end="2026-06-12"), tmp_path)
    u = doc["universes"][0]
    assert u["n_failed"] == 0
    assert any(f["kind"] == "stale" for f in u["flags"])


def test_missing_anchor_fails(tmp_path):
    doc = _run(_store(tmp_path, drop_anchor="IWM"), tmp_path)
    u = doc["universes"][0]
    assert any(f["name"] == "IWM" for f in u["failed"])


def test_absent_manifest_flags(tmp_path):
    doc = _run(_store(tmp_path, manifest_latest=None), tmp_path)
    u = doc["universes"][0]
    assert u["n_failed"] == 0
    assert any(f["name"] == "_manifest" for f in u["flags"])


def test_absent_store_skipped(tmp_path):
    doc = _run(tmp_path, tmp_path)      # no massive_stock_day dir at all
    u = doc["universes"][0]
    assert u["skipped"] and u["n_failed"] == 0 and doc["n"] == 0


def test_partial_checkout_skipped(tmp_path):
    # A CI runner checkout: just the committed JSON stubs, no parquets.
    d = tmp_path / "massive_stock_day"
    d.mkdir()
    (d / "_manifest.json").write_text("{}")
    doc = _run(tmp_path, tmp_path, cfg={**CFG, "massive_min_files": 100})
    assert doc["universes"][0]["skipped"]


def test_writes_audit_json(tmp_path):
    _run(_store(tmp_path), tmp_path)
    out = json.loads((tmp_path / "quality" / "massive_store_audit.json").read_text())
    assert out["audit"] == "massive_stock_day"
