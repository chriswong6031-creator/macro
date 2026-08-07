"""The delayed-chain session holes must be DISCLOSED, never computed across.

Postmortem 2026-08-06. `putcall`/`gex*` are one-row-per-session snapshots of a
live-only endpoint, so they carry permanent holes (collectors/cboe.py
KNOWN_PERMANENT_GAPS: 2026-07-27, 07-30, 08-03, 08-04). Every reader that treats
"the previous row" as "the previous session" was quietly wrong for a week:

  * engine.alerts.gex_flip_cross compares iloc[-2] vs iloc[-1] and reads as an
    OVERNIGHT event — with the holes, those two rows were 07-31 and 08-05.
  * build_market_structure._build_gamma_block counted "days in this state" in ROWS,
    so a six-session stretch rendered "2 days" on the board's regime panel.

House law: nulls printed, never hidden. These tests pin the disclosure, and each
one is written so that reverting the fix makes it fail (a test that passes on the
old row-counting code would pin nothing).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from lib import nyse_calendar

# ── calendar primitives ──────────────────────────────────────────────────────

def test_sessions_strictly_between_is_empty_only_for_adjacent_sessions():
    # 2026-07-31 Fri -> 2026-08-05 Wed spans 08-03 Mon and 08-04 Tue.
    assert nyse_calendar.sessions_strictly_between(date(2026, 7, 31), date(2026, 8, 5)) == [
        date(2026, 8, 3), date(2026, 8, 4)]
    # Adjacent sessions, a weekend in between, equal, and inverted all read "no gap".
    assert nyse_calendar.sessions_strictly_between(date(2026, 8, 4), date(2026, 8, 5)) == []
    assert nyse_calendar.sessions_strictly_between(date(2026, 7, 31), date(2026, 8, 3)) == []
    assert nyse_calendar.sessions_strictly_between(date(2026, 8, 5), date(2026, 8, 5)) == []
    assert nyse_calendar.sessions_strictly_between(date(2026, 8, 5), date(2026, 8, 3)) == []


def test_missing_sessions_accepts_an_index_and_ignores_non_session_rows():
    """A pandas Index must not be truth-tested (it raises), and a fabricated weekend
    row must never be able to satisfy a real session's absence (#3721 class)."""
    idx = pd.DatetimeIndex(["2026-07-31", "2026-08-01", "2026-08-05"])  # 08-01 is a Saturday
    assert nyse_calendar.missing_sessions(idx, date(2026, 7, 31), date(2026, 8, 5)) == [
        date(2026, 8, 3), date(2026, 8, 4)]
    assert nyse_calendar.missing_sessions(None, date(2026, 8, 4), date(2026, 8, 5)) == [
        date(2026, 8, 4), date(2026, 8, 5)]


# ── gex_flip_cross: an alert that reads as overnight must say when it is not ──

def _gex_frame(dates: list[str]) -> pd.DataFrame:
    """Two rows whose net GEX changes sign — the alert always fires on these."""
    return pd.DataFrame(
        {"net_gex_bn": [5.0, -5.0], "spot_vs_flip_pct": [1.0, 1.0]},
        index=pd.DatetimeIndex(dates))


@pytest.fixture()
def _alerts(monkeypatch):
    from engine import alerts
    monkeypatch.setattr(alerts.config, "load", lambda: {
        "alerts": {"gex_flip_cross": True, "gex_net_deadband_bn": 1.0,
                   "gex_flip_pct_deadband": 0.25}})
    return alerts


def test_flip_cross_across_a_hole_discloses_the_span(_alerts, monkeypatch):
    monkeypatch.setattr(_alerts.store, "read",
                        lambda g, n: _gex_frame(["2026-07-31", "2026-08-05"]))
    a = _alerts.gex_flip_cross(pd.DataFrame(), pd.DataFrame())
    assert a is not None, "the sign change itself is real and must still fire"
    assert "not overnight" in a.message, (
        f"a 4-session span presented as an overnight flip is the defect; got {a.message!r}")
    assert "2026-08-03" in a.message and "2026-08-04" in a.message, (
        "the unobserved sessions must be named, not merely counted")
    assert "并非隔夜发生" in a.message_zh, "the ZH surface owes the same disclosure"


def test_flip_cross_on_adjacent_sessions_says_nothing_extra(_alerts, monkeypatch):
    """The healthy path must stay clean — a disclosure that fires always is noise."""
    monkeypatch.setattr(_alerts.store, "read",
                        lambda g, n: _gex_frame(["2026-08-04", "2026-08-05"]))
    a = _alerts.gex_flip_cross(pd.DataFrame(), pd.DataFrame())
    assert a is not None
    assert "not overnight" not in a.message and "sessions" not in a.message
    assert "并非隔夜发生" not in a.message_zh


# ── board regime panel: "days in this state" must count sessions, not rows ───

def _write_gex_spx(tmp_path: Path, dates: list[str], regime: str = "short") -> Path:
    d = tmp_path / "cboe"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {"net_gex_bn": [-3.0] * len(dates), "gamma_regime": [regime] * len(dates),
         "gamma_flip": [5000.0] * len(dates), "spot": [4900.0] * len(dates),
         "dist_to_flip_pct": [-2.0] * len(dates)},
        index=pd.DatetimeIndex(dates),
    ).to_parquet(d / "gex_SPX.parquet")
    return tmp_path


def test_days_in_regime_counts_sessions_and_names_the_unobserved_ones(tmp_path):
    """THE REGRESSION. Rows 07-29, 07-31, 08-05 all in the same regime: the old code
    rendered "3 days in this state" for a stretch six sessions long."""
    import scripts.build_market_structure as bms
    _write_gex_spx(tmp_path, ["2026-07-29", "2026-07-31", "2026-08-05"])
    blk = bms._build_gamma_block(tmp_path)
    assert blk["days_in_regime"] == 6, (
        f"07-29..08-05 inclusive is 6 NYSE sessions; row-counting gave 3. "
        f"got {blk['days_in_regime']}")
    assert blk["days_in_regime_observed"] == 3
    assert blk["coverage"]["missing_in_regime"] == ["2026-07-30", "2026-08-03", "2026-08-04"]
    assert blk["coverage"]["complete"] is False


def test_hole_free_store_is_unchanged_and_reports_complete(tmp_path, monkeypatch):
    """On a healthy store session-span and row-count agree, so this only ever
    corrects a lie — it must not move a number that was already right."""
    import scripts.build_market_structure as bms
    monkeypatch.setattr(bms.nyse_calendar, "expected_last_session", lambda *a, **k: date(2026, 8, 5))
    _write_gex_spx(tmp_path, ["2026-08-03", "2026-08-04", "2026-08-05"])
    blk = bms._build_gamma_block(tmp_path)
    assert blk["days_in_regime"] == 3 == blk["days_in_regime_observed"]
    assert blk["coverage"]["missing_in_regime"] == []
    assert blk["coverage"]["missing_recent"] == []
    assert blk["coverage"]["complete"] is True


def test_gamma_block_null_path_still_carries_the_coverage_key(tmp_path):
    """Consumers must be able to read `coverage` unconditionally."""
    import scripts.build_market_structure as bms
    assert "coverage" in bms._build_gamma_block(tmp_path)


# ── the salvage selector that stops the holes being self-inflicted ───────────

def test_salvage_selector_covers_the_declared_chain_family_and_nothing_else():
    """Scope is the whole safety argument: cor1m/skew/vvix/vix_futures re-fetch full
    history every night and MUST stay behind the collectors gate, so a glob over
    data/cboe/ would turn a narrow carve-out into the forbidden bulk commit."""
    from collectors.cboe import CHAIN_FAMILY_SERIES
    from scripts.ci.chain_snapshot_salvage import _chain_snapshot_files
    assert _chain_snapshot_files() == tuple(
        f"data/cboe/{s}.parquet" for s in CHAIN_FAMILY_SERIES)
    joined = " ".join(_chain_snapshot_files())
    for refetched in ("cor1m", "cor3m", "skew", "vvix", "vix_futures", "vix_curve",
                      "vix1d", "dspx", "vixeq"):
        assert refetched not in joined, f"{refetched} re-fetches history; must not be salvaged"


def test_salvage_drops_a_torn_or_non_session_tipped_parquet(tmp_path):
    """A collectors step that died mid-write can leave a torn file; and a snapshot
    tipping on a non-session is the #3721 shape that poisons every iloc[-1] reader.
    Neither may be published by the salvage path."""
    from scripts.ci.chain_snapshot_salvage import select_salvageable
    d = tmp_path / "data" / "cboe"
    d.mkdir(parents=True)
    pd.DataFrame({"index_pc_ratio": [1.0]},
                 index=pd.DatetimeIndex(["2026-08-05"])).to_parquet(d / "putcall.parquet")
    pd.DataFrame({"net_gex_bn": [1.0]},
                 index=pd.DatetimeIndex(["2026-08-01"])).to_parquet(d / "gex.parquet")  # Saturday
    (d / "gex_SPX.parquet").write_bytes(b"not a parquet")                               # torn
    got = select_salvageable(tmp_path)
    assert got == ["data/cboe/putcall.parquet"], (
        f"only the session-tipped, readable snapshot is salvageable; got {got}")


def test_registered_gaps_name_their_cause_and_distinguish_the_two_classes():
    """The 07-27 entry taught a week of readers to blame the CBOE CDN, and most of
    the lost sessions were in fact collected fine and dropped by our own pipeline.
    Every registered gap must say which it was, or the registry misdirects again."""
    from collectors.cboe import KNOWN_PERMANENT_GAPS
    for d in (date(2026, 7, 27), date(2026, 7, 30), date(2026, 8, 3), date(2026, 8, 4)):
        assert d in KNOWN_PERMANENT_GAPS, f"{d} was observed missing and must be registered"
        why = KNOWN_PERMANENT_GAPS[d]
        assert any(k in why for k in ("SOURCE loss", "COMMIT loss", "MIXED")), (
            f"{d} must be classified source-vs-commit; got {why[:80]!r}")
    assert "COMMIT loss" in KNOWN_PERMANENT_GAPS[date(2026, 8, 4)]
    assert "SOURCE loss" in KNOWN_PERMANENT_GAPS[date(2026, 7, 30)]
