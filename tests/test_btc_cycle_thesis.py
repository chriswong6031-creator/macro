"""Tests for engine/btc_cycle_thesis.py — the BTC halving/midterm thesis MONITOR.

Pins the falsifier logic: prior-bear depths measured from price, the projected-bottom window,
and the four flags (dampening / timing / desync / structure) driving thesis_status. The whole
point is that the monitor flags the thesis BREAKING, so the breaking paths matter most.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import btc_cycle_thesis as ct

_CFG = {
    "cycle_clock": {"halving_dates": ["2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20"],
                    "cycle_len_d": 1458},
    "cycle_phase_clock": {"tops": ["2017-12-16", "2021-11-08", "2025-10-06"],
                          "bottoms": ["2015-01-14", "2018-12-15", "2022-11-21"],
                          "up_days": 1064, "down_days": 364},
}


def _series(low=40000.0, recover_to=70000.0, end="2027-03-01"):
    """Piecewise-linear BTC path through the real cycle pivots, with a tunable current-cycle
    low near the projected window (lets us test deep vs shallow / recovery vs still-falling)."""
    anchors = [("2016-01-01", 430), ("2017-12-16", 20000), ("2018-12-15", 3200),
               ("2021-11-08", 69000), ("2022-11-21", 16000), ("2025-10-06", 125000),
               ("2026-10-20", low), (end, recover_to)]
    idx = pd.date_range("2016-01-01", end, freq="D")
    xs = [pd.Timestamp(d).value for d, _ in anchors]
    ys = [float(v) for _, v in anchors]
    return pd.Series(np.interp([t.value for t in idx], xs, ys), index=idx)


def test_prior_bears_measured_from_price():
    m = ct.monitor(_series(), cfg=_CFG, asof="2026-06-28")
    assert m["ok"]
    depths = {b["bottom"]: b["depth"] for b in m["prior_bears"]}
    assert len(m["prior_bears"]) == 2                       # only COMPLETED bears (PIT)
    assert abs(depths["2018-12-15"] - (3200 / 20000 - 1)) < 0.02   # ~ −0.84
    assert abs(depths["2022-11-21"] - (16000 / 69000 - 1)) < 0.02  # ~ −0.77
    assert m["prior_bear_mean"] < -0.7


def test_early_state_is_intact_and_not_dampening():
    m = ct.monitor(_series(), cfg=_CFG, asof="2026-06-28")
    assert m["time_status"] == "early"
    assert m["in_window"] is False and m["accumulate"] is False
    assert m["dampening"] is False                          # mid-bear is not "shallower", just unfinished
    assert m["thesis_status"] == "intact"
    assert m["peak_date"] == "2025-10-06"
    assert m["drawdown_from_peak"] < 0
    # window opens ~360d after the top
    assert m["window_start"] == "2026-10-01" and m["window_end"][:7] == "2026-12"


def test_in_window_deep_drawdown_is_accumulation():
    m = ct.monitor(_series(low=40000), cfg=_CFG, asof="2026-11-01")
    assert m["in_window"] is True
    assert m["time_status"] == "in_window"
    assert m["accumulate"] is True                          # in window + deep dd, structure not invalidated
    assert m["dampening"] is False                          # −66% is in line with the ~−80% prior avg


def test_in_window_shallow_drawdown_flags_dampening_watch():
    m = ct.monitor(_series(low=62000), cfg=_CFG, asof="2026-11-01")
    assert m["in_window"] is True
    assert m["dampening"] is True
    assert m["thesis_status"] == "watch"
    assert any(f["key"] == "dampening" and f["level"] == "watch" for f in m["flags"])


def test_overdue_still_falling_breaks_thesis():
    # no recovery — price keeps grinding lower well past the window
    s = _series(low=45000, recover_to=28000, end="2027-06-01")
    m = ct.monitor(s, cfg=_CFG, asof="2027-03-01")
    assert m["time_status"] == "overdue"
    assert m["thesis_status"] == "breaking"
    assert any(f["key"] == "timing" and f["level"] == "alert" for f in m["flags"])


def test_desync_aligned_this_cycle():
    m = ct.monitor(_series(), cfg=_CFG, asof="2026-06-28")
    assert m["desync_months"] is not None and m["desync_months"] <= 4.0
    assert any(f["key"] == "desync" and f["level"] == "ok" for f in m["flags"])


def test_halving_window_derived_from_structure():
    """W2 (N8): the halving-anchored window/projection must come straight from the
    observed halving→bottom gaps in config — no invented constants, PIT-honest."""
    m = ct.monitor(_series(), cfg=_CFG, asof="2026-06-28")
    assert m["halving_bottom_gaps_d"] == [777, 889, 924]      # 2012→2015 / 2016→2018 / 2020→2022
    assert m["halving_window_start"] == "2026-06-06"          # 2024-04-20 + 777d
    assert m["halving_window_end"] == "2026-10-31"            # 2024-04-20 + 924d (worst case)
    assert m["halving_proj_bottom"] == "2026-09-26"           # 2024-04-20 + median 889d
    assert m["halving_overdue"] is False                      # window still open on 2026-06-28
    assert m["pivot_stale"] is False                          # no post-top ATH in the default path
    # the repaired desync now measures the HALVING clock vs the midterm calendar
    # (~Sep 26 vs Nov 4 2026 ≈ 1.3mo) — still aligned this cycle
    assert m["desync_months"] is not None and m["desync_months"] < 2.0


def test_halving_overdue_escalates_inside_gate_window():
    """W2 (N8): with price still pinned at the lows past the halving clock's worst
    historical case (2026-10-31), the timing falsifier must escalate to WATCH on
    2026-11-02 — INSIDE the midterm gate window (gate self-releases 2026-11-03).
    The old peak-anchored rule could not say anything before 2026-12-10."""
    s = _series(low=45000, recover_to=30000, end="2027-06-01")   # still falling
    m = ct.monitor(s, cfg=_CFG, asof="2026-11-02")
    assert m["halving_overdue"] is True
    assert m["time_status"] == "in_window"                       # peak window still open…
    timing = [f for f in m["flags"] if f["key"] == "timing"]
    assert len(timing) == 1 and timing[0]["level"] == "watch"    # …but the causal clock escalated
    assert m["thesis_status"] in ("watch", "breaking")


def test_halving_overdue_quiet_when_price_lifted_off():
    """No escalation when price has lifted off the lows — same date, recovery path."""
    m = ct.monitor(_series(low=40000, recover_to=70000), cfg=_CFG, asof="2026-11-02")
    assert m["halving_overdue"] is False
    timing = [f for f in m["flags"] if f["key"] == "timing"]
    assert len(timing) == 1 and timing[0]["level"] == "ok"


def test_pivot_staleness_alarm_fires_on_post_top_ath():
    """W2 (N8): a new all-time-high close set well AFTER the last recorded top means
    the hand-set pivot registry is stale — alert, thesis breaking until config is fixed."""
    anchors = [("2016-01-01", 430), ("2017-12-16", 20000), ("2018-12-15", 3200),
               ("2021-11-08", 69000), ("2022-11-21", 16000), ("2025-10-06", 125000),
               ("2026-03-01", 150000),                       # ATH ~5mo after the recorded top
               ("2026-06-20", 90000)]
    idx = pd.date_range("2016-01-01", "2026-06-28", freq="D")
    xs = [pd.Timestamp(d).value for d, _ in anchors]
    ys = [float(v) for _, v in anchors]
    s = pd.Series(np.interp([t.value for t in idx], xs, ys), index=idx)
    m = ct.monitor(s, cfg=_CFG, asof="2026-06-28")
    assert m["pivot_stale"] is True
    assert any(f["key"] == "pivot_staleness" and f["level"] == "alert" for f in m["flags"])
    assert m["thesis_status"] == "breaking"


def test_pivot_staleness_quiet_in_markup():
    """New ATHs during a markup leg (last pivot = a bottom) are EXPECTED — no alarm."""
    cfg = {"cycle_clock": _CFG["cycle_clock"],
           "cycle_phase_clock": {"tops": ["2017-12-16", "2021-11-08"],   # 2025 top not recorded yet
                                 "bottoms": ["2015-01-14", "2018-12-15", "2022-11-21"],
                                 "up_days": 1064, "down_days": 364}}
    m = ct.monitor(_series(), cfg=cfg, asof="2025-09-01")    # mid-markup, ATHs printing
    assert m["pivot_stale"] is False
    assert not any(f["key"] == "pivot_staleness" for f in m["flags"])


def test_short_history_degrades_gracefully():
    s = pd.Series(np.arange(100.0), index=pd.date_range("2026-01-01", periods=100, freq="D"))
    m = ct.monitor(s, cfg=_CFG)
    assert m["ok"] is False and "degraded_reason" in m


def test_never_raises_on_junk():
    assert ct.monitor(pd.Series(dtype=float), cfg={})["ok"] is False
    assert ct.monitor(None, cfg=_CFG)["ok"] is False
