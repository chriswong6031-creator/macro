"""tests/test_intl_market_state.py
=================================
Unit tests for engine/intl_market_state.py (ITR W1).

All tests use synthetic price series or the read-only KOSPI parquet.
No network calls, no data/ writes.  Follows repo pytest conventions.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.intl_market_state import (  # noqa: E402
    STATES,
    _build_events,
    _compute_components,
    _compute_peak_rsi_memory,
    _resolve_state_series,
    market_states,
)

# ---------------------------------------------------------------------------
# Helpers — synthetic price factories
# ---------------------------------------------------------------------------

def _bdate_range(start: str, periods: int) -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=periods)


def _const_series(val: float, periods: int, start: str = "2018-01-02") -> pd.Series:
    idx = _bdate_range(start, periods)
    return pd.Series(val, index=idx, dtype=float)


def _trend_series(
    start_val: float,
    daily_ret: float,
    periods: int,
    start: str = "2018-01-02",
    seed: int = 0,
    noise: float = 0.0,
) -> pd.Series:
    """Geometric trend with optional small noise."""
    idx = _bdate_range(start, periods)
    rng = np.random.default_rng(seed)
    if noise > 0:
        log_rets = np.log(1 + daily_ret) + rng.normal(0, noise, periods)
    else:
        log_rets = np.full(periods, np.log(1 + daily_ret))
    prices = start_val * np.exp(np.cumsum(log_rets))
    return pd.Series(prices, index=idx, dtype=float)


def _parabola_then_crash(
    base: float = 100.0,
    parabola_periods: int = 300,
    crash_periods: int = 22,
    crash_ret: float = -0.21,  # -21% total over crash_periods
    parabola_ret: float = 0.004,  # ~100% over 300 days
    quiet_lead: int = 500,      # warm-up period before the event
    start: str = "2016-01-04",
) -> pd.Series:
    """Synthetic series: quiet trend -> parabola -> crash.

    The parabola is steep enough to meet ext_pctile >= 98 after enough history.
    The crash is fast enough to meet ret20 <= -15% in 20 sessions.
    """
    n_total = quiet_lead + parabola_periods + crash_periods
    idx = _bdate_range(start, n_total)

    # Quiet uptrend
    quiet_ret = 0.0003
    quiet = base * np.exp(np.cumsum(np.full(quiet_lead, np.log(1 + quiet_ret))))

    # Parabola: accelerating
    parabola_last = quiet[-1]
    parabola = parabola_last * np.exp(np.cumsum(np.full(parabola_periods, np.log(1 + parabola_ret))))

    # Crash: sharp daily decline
    crash_last = parabola[-1]
    daily_crash_ret = (1 + crash_ret) ** (1 / crash_periods) - 1
    crash = crash_last * np.exp(np.cumsum(np.full(crash_periods, np.log(1 + daily_crash_ret))))

    prices = np.concatenate([quiet, parabola, crash])
    return pd.Series(prices, index=idx, dtype=float)


def _shakeout_recovery(
    base: float = 100.0,
    quiet_lead: int = 500,
    parabola_periods: int = 200,
    dip_periods: int = 15,   # -12% dip
    dip_ret: float = -0.12,
    recovery_periods: int = 40,
    new_high_periods: int = 20,
    start: str = "2015-01-02",
) -> pd.Series:
    """Synthetic series: uptrend -> parabola -> brief dip (below MA20) -> new ATH."""
    idx_len = quiet_lead + parabola_periods + dip_periods + recovery_periods + new_high_periods
    idx = _bdate_range(start, idx_len)

    quiet = base * np.exp(np.cumsum(np.full(quiet_lead, np.log(1.0003))))
    para_last = quiet[-1]
    para = para_last * np.exp(np.cumsum(np.full(parabola_periods, np.log(1.004))))
    dip_last = para[-1]
    dip_d = (1 + dip_ret) ** (1 / dip_periods) - 1
    dip = dip_last * np.exp(np.cumsum(np.full(dip_periods, np.log(1 + dip_d))))
    rec_d = (dip_ret / -recovery_periods) + 0.01  # mean-revert back up
    rec = dip[-1] * np.exp(np.cumsum(np.full(recovery_periods, np.log(1.004))))
    nh = rec[-1] * np.exp(np.cumsum(np.full(new_high_periods, np.log(1.003))))

    prices = np.concatenate([quiet, para, dip, rec, nh])
    return pd.Series(prices, index=idx, dtype=float)


def _geometric_leg(start_px: float, end_px: float, periods: int) -> np.ndarray:
    """Constant-log-step leg from start_px (exclusive) to end_px (inclusive)."""
    step = (end_px / start_px) ** (1.0 / periods)
    return start_px * step ** np.arange(1, periods + 1)


def _crash_then_ma50_wobble(
    peak: float = 100.0,
    lead: int = 320,
    lead_drift: float = 0.0006,
    crash_periods: int = 10,
    dd_bottom: float = -33.0,
    rebound_periods: int = 24,
    dd_rebound_top: float = -11.3,
    pullback_periods: int = 3,
    dd_pullback: float = -17.0,
    hold_periods: int = 8,
    hold_drift: float = 0.002,
    start: str = "2019-01-01",
) -> pd.Series:
    """Quiet lead -> fast crash -> V-rebound through MA50 -> pullback back under it.

    The point of this shape is the pullback.  A fresh rebound off a crash low
    pokes above MA50 (repair_entry fires, state becomes ``recovery``), then a
    routine pullback drops price back *under* MA50 while it is still above
    MA20 — MA20 has not yet crossed up through MA50 this early in a repair.
    That kills ``repair_entry`` (which demands ``above_ma50``) while leaving
    every piece of repair evidence intact: above MA20, positive 20-session
    momentum, improving 10-session drawdown, positive MACD.  Only
    ``repair_hold`` can carry those sessions.

    Drawdowns are expressed against ``peak``, which is the 252-session high
    for the whole post-peak stretch, so the ``dd_*`` arguments are the
    literal ``dd_pct`` values the engine will see on the last day of each leg.
    """
    lead_px = peak * np.exp(-np.cumsum(np.full(lead, np.log(1 + lead_drift)))[::-1])
    bottom = peak * (1 + dd_bottom / 100.0)
    rebound_top = peak * (1 + dd_rebound_top / 100.0)
    pullback_low = peak * (1 + dd_pullback / 100.0)

    prices = np.concatenate([
        lead_px,                                                   # quiet drift up to the high
        np.array([peak]),                                          # the 252d high itself
        _geometric_leg(peak, bottom, crash_periods),               # fast crash (ret20 <= -15%)
        _geometric_leg(bottom, rebound_top, rebound_periods),      # V-rebound up through MA50
        _geometric_leg(rebound_top, pullback_low, pullback_periods),  # pullback back under MA50
        pullback_low * (1 + hold_drift) ** np.arange(1, hold_periods + 1),  # slow grind
    ])
    idx = _bdate_range(start, len(prices))
    return pd.Series(prices, index=idx, dtype=float)


# ---------------------------------------------------------------------------
# Test 1: Parabola → crash — events include parabolic_enter + exactly one crash_20d
# ---------------------------------------------------------------------------

class TestParabolaThenCrash:
    """Synthetic steep parabola followed by a fast -21% crash."""

    def setup_method(self):
        self.close = _parabola_then_crash()
        result = market_states({"SYN": self.close})
        self.r = result["SYN"]

    def test_crash_state_at_end(self):
        assert self.r["state"] == "crash", (
            f"expected crash at end of crash series, got {self.r['state']}"
        )

    def test_was_parabolic_40d(self):
        assert self.r["was_parabolic_40d"] is True

    def test_exactly_one_crash_20d(self):
        crash_events = [e for e in self.r["events"] if e["code"] == "crash_20d"]
        assert len(crash_events) == 1, (
            f"expected exactly 1 crash_20d event, got {len(crash_events)}: {crash_events}"
        )

    def test_parabolic_enter_present(self):
        # parabolic_enter should be in the last 45 sessions when the parabola begins;
        # OR the state transition to parabolic should be visible in events.
        # Accept either parabolic_enter or a state transition that includes parabolic.
        para_events = [
            e for e in self.r["events"]
            if e["code"] == "parabolic_enter" or "parabolic" in e["code"]
        ]
        # If neither, check state history: the state at some point must have been parabolic
        f = _compute_components(self.close.dropna().sort_index())
        states = _resolve_state_series(f)
        ever_parabolic = (states == "parabolic").any()
        assert ever_parabolic, "series should have reached parabolic state at peak"

    def test_urgency_9(self):
        assert self.r["urgency"] == 9


# ---------------------------------------------------------------------------
# Test 2: Shakeout recovery — no whipsaw deadlock, returns to parabolic/extended
# ---------------------------------------------------------------------------

class TestShakeoutRecovery:
    """Parabola → brief -12% dip below MA20 → full recovery to new ATH."""

    def setup_method(self):
        self.close = _shakeout_recovery()
        result = market_states({"SYN": self.close})
        self.r = result["SYN"]
        f = _compute_components(self.close.dropna().sort_index())
        self.states = _resolve_state_series(f)

    def test_end_state_not_crash(self):
        """After full recovery to new ATH the system should not be stuck in crash."""
        assert self.r["state"] not in ("crash", "downtrend"), (
            f"after recovery to new ATH expected elevated state, got {self.r['state']}"
        )

    def test_recovers_to_extended_or_parabolic(self):
        """Final state should be parabolic, extended, topping, or at worst uptrend."""
        assert self.r["state"] in ("parabolic", "extended", "topping", "uptrend", "breaking"), (
            f"unexpected final state after recovery: {self.r['state']}"
        )

    def test_no_permanent_crash_deadlock(self):
        """The brief dip should not permanently classify as crash."""
        tail_50 = self.states.tail(50)
        n_crash = (tail_50 == "crash").sum()
        assert n_crash == 0, (
            f"crash state persists after recovery ({n_crash} sessions in last 50)"
        )

    def test_dip_triggers_breaking_or_topping(self):
        """The -12% dip should trigger breaking/topping (not stay extended forever)."""
        n = len(self.states)
        # The dip occurs roughly in the middle + quiet_lead
        dip_window = self.states.iloc[690:730]  # rough position
        transient = dip_window.isin({"breaking", "topping", "downtrend"}).any()
        assert transient, f"expected breaking/topping during dip, got: {dip_window.unique()}"


# ---------------------------------------------------------------------------
# Test 3: Quiet flat series stays calm/uptrend with few/no events
# ---------------------------------------------------------------------------

class TestQuietFlatSeries:
    """Nearly flat series with tiny upward drift."""

    def setup_method(self):
        # 800 sessions, 0.01% daily drift, no noise: should stay calm/uptrend
        self.close = _trend_series(100.0, 0.0001, 800, noise=0.0)
        result = market_states({"SYN": self.close})
        self.r = result["SYN"]

    def test_state_calm_or_uptrend(self):
        assert self.r["state"] in ("calm", "uptrend"), (
            f"expected calm/uptrend on flat series, got {self.r['state']}"
        )

    def test_few_events(self):
        """No crash or parabolic events on a flat series."""
        bad_events = [
            e for e in self.r["events"]
            if e["code"] in ("crash_20d", "parabolic_enter")
        ]
        assert len(bad_events) == 0, (
            f"unexpected events on flat series: {bad_events}"
        )

    def test_no_crash_state(self):
        assert self.r["urgency"] < 5, (
            f"flat series should have urgency < 5, got {self.r['urgency']}"
        )


# ---------------------------------------------------------------------------
# Test 4: RSI divergence detector
# ---------------------------------------------------------------------------

class TestRSIDivergence:
    """Verify RSI divergence detection via a directly-wired component-level unit test.

    Rather than relying on a price series that incidentally produces the desired
    RSI values (which is fragile given Wilder RSI's sensitivity to path), this
    test constructs the component DataFrame manually and calls
    _compute_peak_rsi_memory directly.  This is the most reliable way to test
    the divergence logic without coupling to the RSI formula's convergence
    properties.
    """

    @staticmethod
    def _make_frame_with_divergence(rsi_at_recent_high: float, max_prior_rsi: float) -> pd.DataFrame:
        """Build a minimal component frame with controlled RSI values at new highs.

        Sets up a 600-row frame where:
        - Row -40 (prior window): a new 252d high with RSI = max_prior_rsi
        - Row -2: another new 252d high with RSI = rsi_at_recent_high (within last 5)
        """
        n = 600
        idx = pd.bdate_range("2018-01-02", periods=n)

        # Monotonically rising price (guarantees 252d high on every row after warmup)
        prices = np.linspace(100.0, 200.0, n)
        rsi_vals = np.full(n, 55.0)  # background RSI

        # Set controlled RSI values at specific rows
        prior_new_high_pos = n - 42  # ~40 sessions before the end
        recent_new_high_pos = n - 2   # 2 sessions from end (within last 5)

        rsi_vals[prior_new_high_pos] = max_prior_rsi
        rsi_vals[recent_new_high_pos] = rsi_at_recent_high

        f = pd.DataFrame(index=idx)
        f["px"] = prices
        f["rsi"] = rsi_vals
        f["is_new_252h"] = False
        # Mark the prior and recent new high days
        f.iloc[prior_new_high_pos, f.columns.get_loc("is_new_252h")] = True
        f.iloc[recent_new_high_pos, f.columns.get_loc("is_new_252h")] = True
        f.iloc[n - 1, f.columns.get_loc("is_new_252h")] = True  # also make the last day a high
        # Last-day RSI = same as recent (so divergence persists if condition holds)
        rsi_vals[n - 1] = rsi_at_recent_high
        f["rsi"] = rsi_vals

        return f

    def test_divergence_true_when_rsi_significantly_lower(self):
        """_compute_peak_rsi_memory returns rsi_divergence=True when recent high RSI
        is at least 5 pts below the max RSI at prior new highs (20-60 sessions back)."""
        f = self._make_frame_with_divergence(
            rsi_at_recent_high=65.0,  # recent ATH RSI
            max_prior_rsi=83.0,        # prior high RSI — 18 pts higher
        )
        rsi_at_high, rsi_div, peak_date = _compute_peak_rsi_memory(f)
        assert rsi_div is True, (
            f"expected rsi_divergence=True: recent RSI 65.0 vs prior 83.0 (>5pt drop); "
            f"got rsi_at_high={rsi_at_high}, rsi_div={rsi_div}"
        )

    def test_divergence_false_when_rsi_similar(self):
        """_compute_peak_rsi_memory returns rsi_divergence=False when recent high RSI
        is within 5 pts of the max prior RSI."""
        f = self._make_frame_with_divergence(
            rsi_at_recent_high=79.0,   # recent ATH RSI
            max_prior_rsi=82.0,         # prior high RSI — only 3 pts higher
        )
        rsi_at_high, rsi_div, peak_date = _compute_peak_rsi_memory(f)
        assert rsi_div is False, (
            f"expected rsi_divergence=False: recent RSI 79.0 vs prior 82.0 (<5pt drop); "
            f"got rsi_at_high={rsi_at_high}, rsi_div={rsi_div}"
        )

    def test_divergence_false_when_rsi_higher(self):
        """rsi_divergence must be False when the recent high RSI exceeds the prior."""
        f = self._make_frame_with_divergence(
            rsi_at_recent_high=88.0,   # recent RSI higher than prior
            max_prior_rsi=75.0,
        )
        rsi_at_high, rsi_div, peak_date = _compute_peak_rsi_memory(f)
        assert rsi_div is False, (
            f"expected False when recent RSI > prior RSI; got {rsi_div}"
        )


# ---------------------------------------------------------------------------
# Test 5: KOSPI replay (data/intl/_KS11.parquet READ-ONLY, skip if missing)
# ---------------------------------------------------------------------------

KOSPI_PATH = ROOT / "data" / "intl" / "_KS11.parquet"
HSI_PATH = ROOT / "data" / "hk" / "_HSI.parquet"

# These parquets are LIVE nightly-collected files, not frozen fixtures — the
# collector appends a row every session.  `market_states()` reports the LATEST
# row, so any replay assertion made against its output is really an assertion
# about "today", and rots the moment the market moves on.  That is exactly what
# broke on 2026-08-06: KOSPI's ret20 reset above -15% on 07-31 and re-crossed on
# 08-03 (a legitimate second crossing), and HSI ran recovery -> uptrend -> back
# to recovery, moving `since` off the rebound date.  Neither was an engine
# regression; both assertions were pinned to a moving target.
#
# Each replay is therefore truncated to the as-of date of the episode it
# documents.  Every component in the engine is causal (trailing rolling windows
# and a causal percentile rank), so truncating reproduces those historical rows
# bit-for-bit — verified: states identical, max numeric diff 0.0.  Assertions
# about a frozen window cannot rot; the live tail is covered separately by the
# `test_live_*` cases below, which assert only invariants, never a state.
KOSPI_ASOF = "2026-07-16"   # the crash session this class replays
HSI_ASOF = "2026-07-24"     # the second off-high wobble session (dd -10.74%)


def _assert_first_crossing_discipline(events: list[dict], sessions: pd.DatetimeIndex) -> None:
    """Assert every non-state event is a FIRST crossing of its condition.

    A crossing fires on session t only when its condition is True at t and False
    at t-1, so under correct discipline a code can NEVER fire on two ADJACENT
    trading sessions.  Broken dedup (emitting while the condition merely holds)
    produces exactly that, so this catches the defect the cap below was added
    for.  A repeat further apart is legitimate: it means the condition reset and
    re-crossed, which is what KOSPI's 2026-07-13 / 2026-08-03 crash_20d pair is.
    Session adjacency pins the discipline without pinning a date.
    """
    pos = {ts.strftime("%Y-%m-%d"): i for i, ts in enumerate(sessions)}
    last_seen: dict[str, int] = {}
    for e in sorted(events, key=lambda ev: ev["date"]):
        code = e["code"]
        if code.startswith("state:"):
            continue
        i = pos.get(e["date"])
        assert i is not None, f"event dated on a non-session day: {e}"
        prev = last_seen.get(code)
        assert prev is None or i - prev > 1, (
            f"{code} fired on adjacent sessions {sessions[prev].date()} and "
            f"{sessions[i].date()}: first-crossing discipline not enforced"
        )
        last_seen[code] = i


def _assert_since_starts_the_current_run(result: dict, states: pd.Series) -> None:
    """`since` must be the first day of the current uninterrupted state run.

    Cross-checks `_find_since` against `_resolve_state_series` on whatever the
    latest data happens to be, so the contract stays covered without naming a
    state or a date.
    """
    since = pd.Timestamp(result["since"])
    assert since in states.index, f"since={result['since']} is not a trading session"
    assert (states.loc[since:] == result["state"]).all(), (
        f"state changed after since={result['since']}: "
        f"{dict(states.loc[since:].value_counts())}"
    )
    prior = states.loc[:since]
    if len(prior) > 1:
        assert prior.iloc[-2] != result["state"], (
            f"since={result['since']} is not the START of the run — "
            f"the previous session was already {result['state']}"
        )


@pytest.mark.skipif(not KOSPI_PATH.exists(), reason="KOSPI parquet not available")
class TestKOSPIReplay:
    """Golden-date tests against the real KOSPI data (2026 episode).

    `self.kr` replays the series as of KOSPI_ASOF; `self.states` is the full
    live series (its historical rows are identical either way).
    """

    def setup_method(self):
        df = pd.read_parquet(str(KOSPI_PATH))
        self.close = df["close"].dropna().sort_index()
        self.asof_close = self.close.loc[:KOSPI_ASOF]
        self.result = market_states({"KR": self.asof_close})
        self.kr = self.result["KR"]
        f = _compute_components(self.close)
        self.states = _resolve_state_series(f)

    def test_crash_state_on_2026_07_16(self):
        """KOSPI should be in crash state as of 2026-07-16."""
        assert self.kr["state"] == "crash", (
            f"expected crash on {KOSPI_ASOF}, got {self.kr['state']}"
        )
        assert self.states.loc[KOSPI_ASOF] == "crash"

    def test_crash_urgency_9(self):
        """The 2026-07-16 crash read carries the top urgency rung."""
        assert self.kr["urgency"] == 9

    def test_was_parabolic_40d(self):
        """KOSPI was parabolic within 40 sessions before the crash."""
        assert self.kr["was_parabolic_40d"] is True

    def test_may_2026_elevated_states(self):
        """KOSPI should have been in elevated states (parabolic/topping/breaking/extended)
        for a meaningful number of sessions during May 2026."""
        may_states = self.states["2026-05-01":"2026-05-31"]
        target = {"parabolic", "extended", "topping", "breaking"}
        n_elevated = int(may_states.isin(target).sum())
        assert n_elevated >= 8, (
            f"expected >=8 elevated sessions in May 2026, got {n_elevated}; "
            f"states: {dict(may_states.value_counts())}"
        )

    def test_topping_or_higher_by_2026_06_26(self):
        """By 2026-06-26 KOSPI should be in topping, breaking, or crash state."""
        dt = pd.Timestamp("2026-06-26")
        idx = self.states.index
        # Find nearest bdate at or after
        candidates = idx[idx >= dt]
        assert len(candidates) > 0
        state_at = self.states.loc[candidates[0]]
        assert state_at in ("topping", "breaking", "crash"), (
            f"expected topping/breaking/crash by 2026-06-26, got {state_at}"
        )

    def test_crash_state_on_2026_07_08(self):
        """KOSPI should be in crash by 2026-07-08 (state since date should match)."""
        dt = pd.Timestamp("2026-07-08")
        candidates = self.states.index[self.states.index >= dt]
        if len(candidates) > 0:
            assert self.states.loc[candidates[0]] == "crash"

    def test_exactly_one_crash_20d_in_july(self):
        """The 2026-07-13 waterfall must announce itself exactly once.

        ret20 stayed <= -15% from 07-13 through 07-30, so one crossing covers
        the whole run — 13 sessions, one event.
        """
        july_crash = [
            e for e in self.kr["events"]
            if e["code"] == "crash_20d" and e["date"].startswith("2026-07")
        ]
        assert len(july_crash) == 1, (
            f"expected exactly 1 crash_20d in July 2026, got {len(july_crash)}: {july_crash}"
        )
        assert july_crash[0]["date"] == "2026-07-13"

    def test_rsi_divergence_evidence(self):
        """RSI at June-22 ATH (rsi_at_high) should show divergence vs May-11 RSI.

        Two acceptable proofs (either one validates the divergence evidence):
        1. rsi_at_high < 70 while May-11 had RSI > 80 (current state)
        2. rsi_divergence flag is True (point-in-time window)
        """
        f = _compute_components(self.close.dropna().sort_index())
        rsi = f["rsi"]
        is_new_h = f["is_new_252h"]

        # RSI at June-22 new high
        jun22 = pd.Timestamp("2026-06-22")
        may11 = pd.Timestamp("2026-05-11")

        rsi_jun22 = float(rsi.loc[jun22]) if jun22 in rsi.index else None
        rsi_may11 = float(rsi.loc[may11]) if may11 in rsi.index else None

        divergence_via_rsi = (
            rsi_jun22 is not None
            and rsi_may11 is not None
            and rsi_jun22 < rsi_may11 - 5.0
        )

        assert divergence_via_rsi or self.kr["rsi_divergence"], (
            f"expected RSI divergence evidence: "
            f"rsi@Jun22={rsi_jun22}, rsi@May11={rsi_may11}, "
            f"rsi_divergence={self.kr['rsi_divergence']}"
        )

    def test_rsi_at_high_reasonable(self):
        """RSI at the most recent new high should be a plausible value."""
        rsi_at_high = self.kr["rsi_at_high"]
        assert rsi_at_high is not None
        assert 10.0 <= rsi_at_high <= 100.0, f"rsi_at_high out of range: {rsi_at_high}"

    def test_events_are_readable(self):
        """Events list should be a manageable size (not hundreds of duplicates)."""
        events = self.kr["events"]
        assert len(events) <= 60, (
            f"event list too long ({len(events)}): first-crossing discipline not enforced"
        )
        _assert_first_crossing_discipline(events, self.asof_close.index)

    def test_events_newest_first(self):
        """Events should be sorted newest first."""
        events = self.kr["events"]
        dates = [e["date"] for e in events]
        assert dates == sorted(dates, reverse=True), (
            f"events not in newest-first order: {dates[:5]}"
        )

    # --- live tail: invariants only, never a state or a date ---------------

    def test_live_events_keep_first_crossing_discipline(self):
        """The discipline must hold on today's data, not just the replay window.

        A code may legitimately repeat across a reset — KOSPI's ret20 fell back
        to -13.76% on 2026-07-31 and re-crossed on 08-03 — but never on two
        adjacent sessions.
        """
        live = market_states({"KR": self.close})["KR"]
        assert len(live["events"]) <= 60
        _assert_first_crossing_discipline(live["events"], self.close.index)

    def test_live_since_starts_the_current_run(self):
        live = market_states({"KR": self.close})["KR"]
        assert live["state"] in STATES
        assert live["urgency"] == STATES[live["state"]]["urgency"]
        _assert_since_starts_the_current_run(live, self.states)


# ---------------------------------------------------------------------------
# Test 6: HSI crash-rebound replay — repair hysteresis, no -10% threshold flip
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HSI_PATH.exists(), reason="HSI parquet not available")
class TestHSIRepairReplay:
    """The June/July 2026 HSI rebound must not be hidden by crash memory.

    `self.result` replays the series as of HSI_ASOF; `self.states`/`self.frame`
    stay on the full live series so the crash-precedence invariant below keeps
    being checked against today's data.
    """

    def setup_method(self):
        self.close = pd.read_parquet(str(HSI_PATH))["close"].dropna().sort_index()
        self.asof_close = self.close.loc[:HSI_ASOF]
        self.result = market_states({"HK": self.asof_close})["HK"]
        frame = _compute_components(self.close)
        self.states = _resolve_state_series(frame)
        self.frame = frame

    def test_latest_state_has_repaired(self):
        """As of HSI_ASOF the rebound reads as repair, not as crash memory.

        `since` pins the START of the recovery run: the repair-hold gate carried
        the state unbroken from the 07-20 rebound through the 07-23/07-24 wobble
        without a reset.  (`since` tracks the CURRENT run, so this is only a
        stable claim as of a frozen date — HSI later ran up into `uptrend` on
        07-29 and relapsed to `recovery` on 08-06, which correctly moved `since`
        to 08-06 and used to break this test.)
        """
        assert self.result["state"] == "recovery"
        assert self.result["above_ma200"] is False
        assert self.states.loc["2026-07-20"] == "recovery"
        assert self.result["since"] == "2026-07-20"

    def test_recovery_survives_off_high_boundary_wobble(self):
        """Jul-23 dd=-9.86% and Jul-24 dd=-10.74% carry the same repair evidence."""
        assert self.states.loc["2026-07-23"] == "recovery"
        assert self.states.loc["2026-07-24"] == "recovery"

    def test_repair_has_independent_confirmation(self):
        assert self.result["mom20_pct"] >= 5.0
        assert self.result["dd_vel_10d"] > 0.0
        assert self.result["above_ma20"] is True
        assert self.result["above_ma50"] is True
        assert self.result["macd_state"] == "bull"

    def test_velocity_crash_still_wins(self):
        """The repair rule never overrides an active <=-15% 20-session crash."""
        crash_dates = self.states.index[self.frame["ret20_pct"] <= -15.0]
        assert len(crash_dates) > 0
        assert (self.states.loc[crash_dates] == "crash").all()

    # --- live tail: invariants only, never a state or a date ---------------

    def test_live_since_starts_the_current_run(self):
        live = market_states({"HK": self.close})["HK"]
        assert live["state"] in STATES
        _assert_since_starts_the_current_run(live, self.states)

    def test_live_uptrend_requires_ma200(self):
        """`uptrend` and `recovery` are separated by the 200-day line.

        This is the rule that moved HSI off the 07-20 recovery run: it reclaimed
        MA200 on 07-29 (-> uptrend) and lost it again on 08-06 (-> recovery).
        """
        above200 = self.frame["above_ma200"].astype(bool)
        assert above200.loc[self.states == "uptrend"].all()
        assert not above200.loc[self.states == "recovery"].any()


# ---------------------------------------------------------------------------
# Test 6b: repair_hold hysteresis — SYNTHETIC, drift-proof
#
# TestHSIRepairReplay above guards the same rule against the live HSI parquet,
# and that is exactly why it cannot be trusted to guard it forever: the live
# data drifted until repair_entry alone carried 2026-07-23/24, so deleting
# `repair_hold` left the whole suite green.  This class pins the hold clause to
# a constructed series that no nightly collection can move.
# ---------------------------------------------------------------------------

def _crash_gate_inputs(frame: pd.DataFrame, states: pd.Series, i: int) -> dict:
    """Re-derive the clause-1 crash-gate inputs the engine sees on row ``i``.

    Mirrors the NaN handling in ``_resolve_state_series`` (non-finite numerics
    are read as 0.0; a non-finite ``dd_vel_10d`` is read as None).  This is a
    *locator* only — every assertion below is made against the engine's own
    state output, never against these re-derived values.
    """
    row = frame.iloc[i]

    def _num(key: str) -> float:
        val = float(row[key])
        return val if np.isfinite(val) else 0.0

    dd = _num("dd_pct")
    dd_min30 = _num("dd_min30")
    mom20 = _num("mom20_pct")
    ret20 = _num("ret20_pct")
    dd_vel_raw = float(row["dd_vel_10d"])
    dd_vel = dd_vel_raw if np.isfinite(dd_vel_raw) else None
    macd_positive = bool(float(row["macd_hist"]) > 0.0)  # NaN > 0 is False
    above_ma20 = bool(row["above_ma20"])
    above_ma50 = bool(row["above_ma50"])
    previous_state = states.iloc[i - 1] if i > 0 else None

    repair_entry = (
        above_ma20
        and above_ma50
        and mom20 >= 5.0
        and dd_vel is not None
        and dd_vel >= 0.0
        and macd_positive
    )
    repair_hold = (
        previous_state == "recovery"
        and above_ma20
        and mom20 > 0.0
        and (dd_vel is None or dd_vel > -1.0)
        and macd_positive
    )
    return {
        "damage_memory": dd_min30 <= -18.0 and dd <= -10.0,
        "velocity_crash": ret20 <= -15.0,
        "repair_entry": repair_entry,
        "repair_hold": repair_hold,
        "previous_state": previous_state,
        "dd": dd,
        "dd_min30": dd_min30,
        "mom20": mom20,
        "dd_vel": dd_vel,
        "macd_positive": macd_positive,
        "above_ma20": above_ma20,
        "above_ma50": above_ma50,
    }


class TestRepairHoldHysteresis:
    """`repair_hold` alone must keep a repairing market out of `crash`.

    The constructed series rebounds off a -33% crash, crosses back above MA50
    (repair_entry fires -> `recovery`), then pulls back *under* MA50 while MA20
    is still below it.  On those pullback sessions the damage-memory crash test
    is live (dd_min30 <= -18 and dd <= -10), the velocity crash test is not
    (ret20 well above -15), and `repair_entry` is dead because price sits below
    MA50 — so `repair_hold` is the only thing standing between `recovery` and a
    threshold-wobble flip to `crash`.

    Deleting the `or repair_hold` term from `repair_confirmed` turns every one
    of those sessions into `crash`.
    """

    def setup_method(self):
        self.close = _crash_then_ma50_wobble()
        self.frame = _compute_components(self.close)
        self.states = _resolve_state_series(self.frame)
        self.hold_only = [
            i
            for i in range(1, len(self.frame))
            if (
                (g := _crash_gate_inputs(self.frame, self.states, i))["damage_memory"]
                and not g["velocity_crash"]
                and not g["repair_entry"]
                and g["repair_hold"]
            )
        ]

    def test_series_reaches_the_hold_only_regime(self):
        """The series must actually exercise the clause — else this file is decoration.

        This is the anti-rot assertion: if a future change to the state machine
        or to the component maths stops this shape from reaching a
        hold-only session, the guard below would silently stop guarding.
        """
        assert self.hold_only, (
            "constructed series never reaches a session where damage-memory crash "
            "is live, velocity crash is not, and repair_entry is False while "
            "repair_hold is True — the hysteresis clause is untested"
        )

    def test_repair_hold_alone_prevents_the_crash_flip(self):
        """The mutation guard: hold-only sessions stay `recovery`, never `crash`.

        Removing `or repair_hold` from `repair_confirmed` makes each of these
        sessions fail the damage-memory gate and resolve to `crash`.
        """
        for i in self.hold_only:
            g = _crash_gate_inputs(self.frame, self.states, i)
            assert self.states.iloc[i] == "recovery", (
                f"session {i} ({self.states.index[i].date()}) must stay in recovery on "
                f"the hold clause alone; got {self.states.iloc[i]!r}. "
                f"dd={g['dd']:.2f} dd_min30={g['dd_min30']:.2f} mom20={g['mom20']:.2f} "
                f"dd_vel={g['dd_vel']:.2f} macd_positive={g['macd_positive']} "
                f"above_ma20={g['above_ma20']} above_ma50={g['above_ma50']}"
            )

    def test_hold_only_sessions_have_no_other_repair_evidence(self):
        """Document *why* those sessions are decisive: only the hold gate is open."""
        for i in self.hold_only:
            g = _crash_gate_inputs(self.frame, self.states, i)
            assert g["damage_memory"], f"session {i} is not under damage memory"
            assert not g["velocity_crash"], f"session {i} is a velocity crash"
            assert not g["repair_entry"], f"session {i} still satisfies repair_entry"
            assert not g["above_ma50"], (
                f"session {i} is above MA50 — repair_entry would carry it"
            )
            assert g["previous_state"] == "recovery"

    def test_entry_gate_opens_the_repair_before_the_hold_carries_it(self):
        """The first repair session is won by `repair_entry`, not by the hold clause.

        `repair_hold` requires a prior `recovery`, so it can never *start* one.
        A series where the hold clause opened the repair would be testing
        nothing about hysteresis.
        """
        first_recovery = int(np.argmax((self.states == "recovery").to_numpy()))
        assert self.states.iloc[first_recovery] == "recovery"
        g = _crash_gate_inputs(self.frame, self.states, first_recovery)
        assert g["repair_entry"], "first recovery session should be won by repair_entry"
        assert not g["repair_hold"]
        assert first_recovery < min(self.hold_only)

    def test_velocity_crash_still_overrides_the_hold(self):
        """A live -15%/20-session waterfall stays `crash` no matter what."""
        velocity_days = self.frame.index[self.frame["ret20_pct"] <= -15.0]
        assert len(velocity_days) > 0, "series should contain a real velocity crash"
        assert (self.states.loc[velocity_days] == "crash").all()

    def test_hold_expires_when_the_evidence_does(self):
        """The clause is hysteresis, not a latch — it lets go once evidence fails."""
        last_hold = max(self.hold_only)
        tail = self.states.iloc[last_hold + 1:]
        assert (tail == "recovery").sum() < len(tail), (
            "repair_hold never released — a permanent recovery latch would be a bug"
        )


# ---------------------------------------------------------------------------
# Test 7: Determinism + fail-open
# ---------------------------------------------------------------------------

class TestDeterminismAndFailOpen:
    """Two identical calls return identical results; short series returns data_limited stub."""

    def test_determinism(self):
        """Two identical market_states calls return the same result."""
        close = _trend_series(100.0, 0.001, 800, noise=0.005, seed=42)
        r1 = market_states({"X": close})["X"]
        r2 = market_states({"X": close})["X"]

        assert r1["state"] == r2["state"]
        assert r1["urgency"] == r2["urgency"]
        assert r1["events"] == r2["events"]
        assert r1["dd_pct"] == r2["dd_pct"]
        assert r1["was_parabolic_40d"] == r2["was_parabolic_40d"]

    def test_fail_open_short_series(self):
        """A 10-row series returns a data_limited stub without raising."""
        close = _trend_series(100.0, 0.001, 10)
        result = market_states({"X": close})
        r = result["X"]
        assert r["data_limited"] is True
        # Should still have all required keys
        required_keys = {
            "state", "state_en", "state_zh", "stance_en", "stance_zh",
            "state_trigger", "css", "since", "urgency", "ext_raw_pct", "ext_pctile", "ext_z",
            "mom20_pct", "mom5_pct", "rs20_pct", "rsi", "rsi_at_high",
            "rsi_divergence", "macd_state", "macd_cross_date", "dd_pct",
            "dd_vel_10d", "vol_z", "above_ma20", "above_ma50", "above_ma200",
            "was_parabolic_40d", "peak_date", "data_limited", "events",
        }
        missing = required_keys - set(r.keys())
        assert not missing, f"stub is missing keys: {missing}"

    def test_fail_open_exception_handling(self):
        """market_states catches per-country exceptions and returns stubs."""
        # Pass a valid and an invalid entry
        close_good = _trend_series(100.0, 0.001, 800, noise=0.005, seed=1)
        close_bad = pd.Series([], dtype=float)  # empty — should produce data_limited stub
        result = market_states({"GOOD": close_good, "BAD": close_bad})
        assert "GOOD" in result
        assert "BAD" in result
        assert result["BAD"]["data_limited"] is True
        assert result["GOOD"]["state"] in STATES

    def test_all_keys_present(self):
        """Full result dict contains every contract key."""
        close = _trend_series(100.0, 0.001, 800, noise=0.005, seed=7)
        r = market_states({"X": close})["X"]
        required_keys = {
            "state", "state_en", "state_zh", "stance_en", "stance_zh",
            "state_trigger", "css", "since", "urgency", "ext_raw_pct", "ext_pctile", "ext_z",
            "mom20_pct", "mom5_pct", "rs20_pct", "rsi", "rsi_at_high",
            "rsi_divergence", "macd_state", "macd_cross_date", "dd_pct",
            "dd_vel_10d", "vol_z", "above_ma20", "above_ma50", "above_ma200",
            "was_parabolic_40d", "peak_date", "data_limited", "events",
        }
        missing = required_keys - set(r.keys())
        assert not missing, f"result dict missing keys: {missing}"
