"""Coverage-continuity audit for the massive_stock_day store (scripts/audit_massive_store).

Pins the 2026-07-03 incident tripwire: ground truth is the anchor parquets — a
planted interior hole fails, a manifest claiming freshness the anchors can't back
fails, staleness only flags, and a checkout without the heavy store (CI runners)
is skipped, never failed.  Synthetic stores in tmp dirs; cfg thresholds passed
explicitly so repo config drift can't move these tests.

Also pins the 2026-07-29 windowing + annotation contract: continuity fails only INSIDE
the trailing massive_recent_window_bdays window — a gap deeper in history flags instead,
because a full-history run can be the artifact of a stale/mid-backfill state snapshot or
a remainder the capped incremental is still chipping, and neither says anything about
tonight's feed.  And every fail/stale/nightly-skip emits a bare-print GitHub annotation
at column 0 — the house rule from tests/test_gh_annotation_line_start.py, asserted here
on capsys output so a regression to log.* is caught by content, not just by the AST guard.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from scripts import audit_common, audit_massive_store as ams

ASOF = date(2026, 7, 3)

CFG = dict(audit_common.quality_cfg())
CFG.update({"massive_min_files": 3, "massive_max_gap_bdays": 5,
            "massive_stale_bdays": 5, "massive_manifest_ahead_bdays": 2,
            "massive_recent_window_bdays": 90})


def _annotations(out: str, prefix: str) -> list[str]:
    """Captured stdout lines that START with `prefix` — GitHub only parses a workflow
    command at column 0, so the startswith IS the assertion that matters.  Takes the
    already-read text because capsys.readouterr() drains the buffer."""
    return [ln for ln in out.splitlines() if ln.startswith(prefix)]


def _bars(end: str, periods: int = 120) -> pd.DataFrame:
    idx = pd.bdate_range(end=end, periods=periods)
    df = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
                       "volume": 1_000_000, "transactions": 10_000}, index=idx)
    df.index.name = "date"
    return df


def _store(tmp_path: Path, end: str = "2026-07-02", hole: tuple[str, str] | None = None,
           manifest_latest: str | None = "auto", drop_anchor: str | None = None,
           periods: int = 120) -> Path:
    """Build a synthetic store: all five anchors + a manifest.  `hole` drops the
    bars in [start, stop] from EVERY anchor (a whole-market day hole, like the
    incident).  manifest_latest='auto' matches the content; a date string plants a
    lying manifest; None omits the manifest.  `periods` widens the history when a test
    needs bars OLDER than the continuity window (120 bdays back from 2026-07-02 reaches
    2026-01-16; the window opens 2026-02-27)."""
    d = tmp_path / "massive_stock_day"
    d.mkdir(parents=True)
    for t in ams.ANCHORS:
        if t == drop_anchor:
            continue
        df = _bars(end, periods)
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


# --- windowed continuity + annotations (2026-07-29) --------------------------


def test_in_window_hole_fails_and_annotates(tmp_path, capsys):
    # A ~3-week whole-market hole inside the trailing 90-bday window (which opens
    # 2026-02-27 for ASOF=2026-07-03): a live defect. Fails AND says so at column 0.
    doc = _run(_store(tmp_path, hole=("2026-05-11", "2026-05-29")), tmp_path)
    assert doc["universes"][0]["n_failed"] == len(ams.ANCHORS)
    lines = _annotations(capsys.readouterr().out, "::error")
    assert len(lines) == 1
    assert lines[0].startswith("::error title=massive_store audit::")
    assert "member(s) failed" in lines[0]


def test_hole_older_than_the_window_flags_but_does_not_fail(tmp_path, capsys):
    # The same gap shape, entirely behind the window. A full-history run can be the
    # artifact of a stale/mid-backfill state snapshot or a remainder the capped
    # incremental is still chipping — neither is tonight's feed, so it must stay
    # REPORTED and abort nothing.
    doc = _run(_store(tmp_path, hole=("2025-11-03", "2025-12-05"), periods=200), tmp_path)
    u = doc["universes"][0]
    assert u["n_failed"] == 0
    gaps = [f for f in u["flags"] if f["kind"] == "historical_gap"]
    assert len(gaps) == len(ams.ANCHORS)
    assert "older than the 90-business-day continuity window" in gaps[0]["detail"]
    assert _annotations(capsys.readouterr().out, "::error") == []


def test_gap_straddling_the_window_start_still_fails(tmp_path):
    # The naive slice (bars >= window_start) would see a clean run of recent bars and
    # miss this entirely; the audit keeps the last bar BEFORE the window as a left
    # anchor precisely so a hole that ENDS inside the window is still measured.
    doc = _run(_store(tmp_path, hole=("2026-02-02", "2026-04-10"), periods=200), tmp_path)
    u = doc["universes"][0]
    assert u["n_failed"] == len(ams.ANCHORS)
    assert all("coverage hole" in f["reasons"][0] for f in u["failed"])


def test_stale_tip_flags_and_annotates(tmp_path, capsys):
    doc = _run(_store(tmp_path, end="2026-06-12"), tmp_path)
    out = capsys.readouterr().out
    assert doc["universes"][0]["n_failed"] == 0
    lines = _annotations(out, "::warning")
    assert len(lines) == 1
    assert lines[0].startswith("::warning title=massive_store stale::")
    assert "2026-06-12" in lines[0]
    assert _annotations(out, "::error") == []


def test_nightly_skip_annotates(tmp_path, capsys, monkeypatch):
    # On the nightly lane the store IS supposed to be here (daily.yml restores it), so
    # a skip means the restore failed and the store did not advance tonight.
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    doc = _run(tmp_path, tmp_path)
    assert doc["universes"][0]["skipped"]
    lines = _annotations(capsys.readouterr().out, "::warning")
    assert len(lines) == 1
    assert lines[0].startswith("::warning title=massive_store audit skipped::")


def test_off_lane_skip_stays_silent(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    doc = _run(tmp_path, tmp_path)
    assert doc["universes"][0]["skipped"]
    assert capsys.readouterr().out.strip() == ""


def test_exit_code_is_one_only_on_a_content_fail(tmp_path):
    clean = _run(_store(tmp_path / "a"), tmp_path / "a")
    assert ams.exit_code(clean) == 0
    stale = _run(_store(tmp_path / "b", end="2026-06-12"), tmp_path / "b")
    assert ams.exit_code(stale) == 0          # staleness is a warning, not a gate
    skipped = _run(tmp_path / "c", tmp_path / "c")
    assert ams.exit_code(skipped) == 0        # nor is an absent store
    failed = _run(_store(tmp_path / "d", hole=("2026-05-11", "2026-05-29")), tmp_path / "d")
    assert ams.exit_code(failed) == 1
