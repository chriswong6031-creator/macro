"""The alarm site/flowdata/desk.json did not have.

The desk declared ``cadence: "daily"`` and sat 12 days stale — its A-share legs
pinned at 2026-07-24 while southbound advanced to 08-05 beside them — and
nothing anywhere went red. The artifact was rewritten nightly, so every
mtime-, existence- and "did the builder run" check read healthy; the only
consumer that checks freshness (engine/cn_theme_tape, 7-day budget) responded by
silently dropping its flow chips, which is indistinguishable from "no flow today".

Upstream, the same outage reported 'ok' ten nights running because
ChinaTushareAdapter's only series is a heartbeat stamped ``utcnow()`` — fresh by
construction, so the collector framework's freshness machinery could never see
the frozen ``data/tushare/*.parquet`` stores behind it.

These tests are built to fail on that class of defect:
  · a partial freeze (one dead leg among healthy siblings) must be flagged
  · a market holiday (every leg frozen together) must NOT be flagged
  · a TOTAL freeze must still be caught — the case the relative gate is blind to
  · a deliberately discontinued leg must never cry wolf
  · a collector run that collected nothing must not report itself healthy
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from lib import desk_guard


# ── the shape that shipped: a partial freeze among healthy siblings ────────────

def _real_desk_shape() -> dict:
    """site/flowdata/desk.json as it stood on 2026-08-05, trimmed to the stamps."""
    return {
        "aggregate:southbound": {"key": "southbound", "live": True, "as_of": "2026-08-05"},
        # northbound: discontinued upstream 2024-08-16, surfaced historical-only
        "aggregate:northbound": {"key": "northbound", "live": False,
                                 "as_of": "2024-08-16", "frozen_since": "2024-08-16"},
        "ashare_names": {"cadence": "daily", "as_of": "2026-07-24"},
        "ashare_sectors": {"cadence": "daily", "as_of": "2026-07-24"},
        "hk_names": {"as_of": "2026-08-04"},
    }


def test_the_shipped_desk_flags_both_frozen_ashare_legs():
    """The actual 2026-08-05 payload must produce a finding for each dead leg."""
    found = desk_guard.stale_legs(_real_desk_shape(), today=date(2026, 8, 5))
    flagged = {f["leg"] for f in found}
    assert flagged == {"ashare_names", "ashare_sectors"}, (
        f"expected both A-share legs flagged, got {sorted(flagged)}")
    for f in found:
        assert f["reason"] == "lagging"
        assert f["lag_days"] == 12, f"southbound is 08-05, leg is 07-24 → 12d, got {f}"
        assert f["age_days"] == 12


def test_discontinued_northbound_is_never_flagged():
    """A leg frozen ON PURPOSE must not fire, or the alarm becomes background noise.

    Northbound aggregate net disclosure ended 2024-08-16 under the Stock Connect
    home-market rule. It is ~2 years stale and always will be.
    """
    found = desk_guard.stale_legs(_real_desk_shape(), today=date(2026, 8, 5))
    assert not [f for f in found if "northbound" in f["leg"]]


@pytest.mark.parametrize("marker", [{"live": False}, {"frozen_since": "2024-08-16"}])
def test_either_discontinued_marker_suppresses_a_leg(marker):
    legs = {"fresh": {"as_of": "2026-08-05"},
            "dead": {"as_of": "2020-01-01", **marker}}
    assert desk_guard.stale_legs(legs, today=date(2026, 8, 5)) == []


# ── the false positive that would have killed the alarm: market holidays ──────

def test_a_market_holiday_freezes_every_leg_and_must_not_fire():
    """Golden Week closes the mainland ~8 calendar days. Every leg stops together.

    A naive wall-clock-only gate fires on all of them; this is the reason the
    primary gate is RELATIVE. The gap between legs stays 0 while the whole desk
    waits for the market to reopen.
    """
    legs = {"ashare_names": {"cadence": "daily", "as_of": "2026-09-30"},
            "ashare_sectors": {"cadence": "daily", "as_of": "2026-09-30"},
            "aggregate:southbound": {"live": True, "as_of": "2026-09-30"}}
    # Oct 7 — the last day of the closure, 7 days after the final close.
    assert desk_guard.stale_legs(legs, today=date(2026, 10, 7)) == []


# ── the case a purely relative gate cannot see ────────────────────────────────

def test_total_freeze_is_caught_by_the_wall_clock_backstop():
    """Every leg frozen at the SAME old date agrees with itself — lag is 0 for all.

    A self-relative freshness gate is structurally blind here, which is exactly
    how the heartbeat upstream reported 'ok' for ten nights. The backstop is what
    makes the guard see a total outage.
    """
    legs = {"ashare_names": {"cadence": "daily", "as_of": "2026-06-01"},
            "ashare_sectors": {"cadence": "daily", "as_of": "2026-06-01"},
            "aggregate:southbound": {"live": True, "as_of": "2026-06-01"}}
    found = desk_guard.stale_legs(legs, today=date(2026, 8, 5))
    assert [f["reason"] for f in found] == ["desk_frozen"], (
        "a desk where EVERY leg froze must still be flagged")
    assert found[0]["age_days"] == 65


def test_backstop_does_not_fire_inside_its_budget():
    """The backstop must clear a real holiday closure, or it is the noise source."""
    legs = {"a": {"as_of": "2026-09-30"}, "b": {"as_of": "2026-09-30"}}
    assert desk_guard.stale_legs(legs, today=date(2026, 10, 9)) == []      # 9d — inside
    assert desk_guard.stale_legs(legs, today=date(2026, 10, 11)) != []     # 11d — outside


# ── a guard that goes quiet when its input changes shape ──────────────────────

def test_unparseable_as_of_is_reported_not_skipped():
    """Silently skipping an unreadable stamp turns the alarm off without saying so."""
    legs = {"good": {"as_of": "2026-08-05"},
            "broken": {"as_of": "2026/07/24"}}
    found = desk_guard.stale_legs(legs, today=date(2026, 8, 5))
    assert [f["reason"] for f in found] == ["unreadable"]
    assert found[0]["leg"] == "broken"


def test_leg_without_an_as_of_key_is_skipped():
    """Not every leg stamps one; the caller chooses what to pass."""
    legs = {"stamped": {"as_of": "2026-08-05"}, "unstamped": {"n": 3}}
    assert desk_guard.stale_legs(legs, today=date(2026, 8, 5)) == []


def test_a_healthy_desk_is_silent():
    legs = {"aggregate:southbound": {"live": True, "as_of": "2026-08-05"},
            "ashare_names": {"cadence": "daily", "as_of": "2026-08-05"},
            "ashare_sectors": {"cadence": "daily", "as_of": "2026-08-04"},
            "hk_names": {"as_of": "2026-08-04"}}
    assert desk_guard.stale_legs(legs, today=date(2026, 8, 5)) == []


def test_lag_budget_boundary_is_inclusive():
    """4d lag passes, 5d fails — the budget is a max, not a threshold to exceed."""
    legs = {"fresh": {"as_of": "2026-08-05"}, "trailing": {"as_of": "2026-08-01"}}
    assert desk_guard.stale_legs(legs, today=date(2026, 8, 5)) == []
    legs["trailing"]["as_of"] = "2026-07-31"
    assert [f["leg"] for f in desk_guard.stale_legs(legs, today=date(2026, 8, 5))] == ["trailing"]


# ── the annotation must actually reach the Actions summary ───────────────────

def test_builder_emits_a_column_zero_annotation(capsys):
    """Bare print at column 0 with flush — a logger call is swallowed by its prefix.

    Asserts the LINE START, not the wording: the defect this pins is an
    annotation GitHub never parses, which is invisible to any message-text check.
    """
    from scripts import build_flow_velocity as bfv

    today = date.today()
    snap = {
        "aggregate": [{"key": "southbound", "live": True, "as_of": str(today)}],
        "ashare_names": {"cadence": "daily", "as_of": str(today - timedelta(days=12))},
        "ashare_sectors": {"cadence": "daily", "as_of": str(today - timedelta(days=12))},
    }
    found = bfv._warn_if_stale(snap)
    assert len(found) == 2

    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    ann = [ln for ln in lines if ln.startswith("::")]
    assert len(ann) == 2, f"expected 2 column-zero annotations, got {lines}"
    for ln in ann:
        assert ln.startswith("::warning title=flow-velocity-stale::"), ln


def test_builder_is_silent_on_a_healthy_desk(capsys):
    from scripts import build_flow_velocity as bfv

    today = date.today()
    snap = {
        "aggregate": [{"key": "southbound", "live": True, "as_of": str(today)},
                      {"key": "northbound", "live": False, "as_of": "2024-08-16",
                       "frozen_since": "2024-08-16"}],
        "ashare_names": {"cadence": "daily", "as_of": str(today)},
        "ashare_sectors": {"cadence": "daily", "as_of": str(today - timedelta(days=1))},
    }
    assert bfv._warn_if_stale(snap) == []
    assert not [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]


def test_leg_map_flattens_the_payloads_two_shapes():
    """aggregate is a LIST of channels; the rest are single dicts."""
    from scripts import build_flow_velocity as bfv

    legs = bfv._leg_map({
        "aggregate": [{"key": "southbound", "as_of": "2026-08-05"}],
        "ashare_names": {"as_of": "2026-07-24"},
        "hk_names": {"as_of": "2026-08-04"},
        "seats_by_ticker": {"600000.SS": {}},     # not a leg — carries no as_of
    })
    assert set(legs) == {"aggregate:southbound", "ashare_names", "hk_names"}


# ── upstream: a collector that collected nothing must not report healthy ──────

def test_zero_collection_run_reports_stale_and_annotates(capsys):
    """The heartbeat is stamped utcnow(), so only its VALUES can reveal an outage.

    This is the 2026-07-27 → 08-05 signature: token present, all seven modules
    returning 0, adapter reporting 'ok' every night while every store sat frozen.
    """
    pd = pytest.importorskip("pandas")
    from collectors.china_tushare import ChinaTushareAdapter

    adapter = ChinaTushareAdapter.__new__(ChinaTushareAdapter)
    dead = pd.DataFrame([{m: 0.0 for m in ("tushare_valuation", "tushare_moneyflow",
                                           "tushare_history")}],
                        index=[pd.Timestamp("2026-08-05")])
    assert adapter.fetch_result_status({"run_log": dead}) == "stale"


def test_a_collecting_run_still_reports_ok():
    """One live module is enough — status must stay None (runner derives 'ok')."""
    pd = pytest.importorskip("pandas")
    from collectors.china_tushare import ChinaTushareAdapter

    adapter = ChinaTushareAdapter.__new__(ChinaTushareAdapter)
    alive = pd.DataFrame([{"tushare_valuation": 5526.0, "tushare_moneyflow": 5910.0,
                           "tushare_history": 0.0}],
                         index=[pd.Timestamp("2026-08-05")])
    assert adapter.fetch_result_status({"run_log": alive}) is None


def test_a_failed_module_does_not_read_as_collection():
    """-1.0 is the exception marker, not a row count — it must not mask an outage."""
    pd = pytest.importorskip("pandas")
    from collectors.china_tushare import ChinaTushareAdapter

    adapter = ChinaTushareAdapter.__new__(ChinaTushareAdapter)
    broken = pd.DataFrame([{"tushare_valuation": -1.0, "tushare_moneyflow": 0.0}],
                          index=[pd.Timestamp("2026-08-05")])
    assert adapter.fetch_result_status({"run_log": broken}) == "stale"
