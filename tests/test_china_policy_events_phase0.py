"""Tests for scripts/china_policy_events_phase0.py.

Coverage:
  1. Event count integrity: RRR eases = 26, LPR cuts = 15
  2. Same-date episode merge (no duplicates within family)
  3. PIT anchor: entry strictly AFTER event date, never on it
  4. Sector-relative math: sector_car - shcomp_car
  5. No-lookahead fixture: outcome window does not overlap event date
  6. Suspension rule: drops episodes with no valid price in SUSP_MAX sessions

NO live network calls. Synthetic fixtures only. Tracked parquets are never
written in tests.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# ── Helpers to build synthetic price series ───────────────────────────────────

def _make_price_series(
    n: int = 100,
    start: str = "2010-01-04",
    start_price: float = 100.0,
    freq: str = "B",
) -> pd.Series:
    """Build a business-day price series (geometric random walk with seed)."""
    rng = np.random.default_rng(42)
    idx = pd.bdate_range(start, periods=n)
    rets = rng.normal(0, 0.01, n)
    prices = start_price * np.cumprod(1 + rets)
    return pd.Series(prices, index=idx)


def _make_cal(series: pd.Series) -> pd.DatetimeIndex:
    return series.index


# ── Import helpers from the script under test ─────────────────────────────────

from scripts.china_policy_events_phase0 import (
    car_for_event,
    compute_car_series,
    determine_verdict,
    load_events,
    next_trading_day,
    sector_relative_car,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Event count integrity
# ─────────────────────────────────────────────────────────────────────────────

def test_event_counts_match_prereg():
    """F-A must have 26 episodes, F-B must have 15. These are prereg requirements."""
    events = load_events()
    assert len(events["FA"]) == 26, (
        f"F-A RRR eases: expected 26, got {len(events['FA'])}"
    )
    assert len(events["FB"]) == 15, (
        f"F-B LPR cuts: expected 15, got {len(events['FB'])}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Same-date episode merge (no duplicate dates within a family)
# ─────────────────────────────────────────────────────────────────────────────

def test_no_duplicate_episode_dates():
    """Each family's event dates must be unique (same-date merge applied)."""
    events = load_events()
    for fam, dates in events.items():
        assert len(dates) == len(set(dates)), (
            f"Family {fam} has duplicate episode dates: {dates[dates.duplicated()]}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: PIT anchor — entry strictly AFTER event date
# ─────────────────────────────────────────────────────────────────────────────

def test_pit_anchor_strictly_after_event():
    """next_trading_day must return a date strictly after the given date."""
    prices = _make_price_series(50)
    cal = _make_cal(prices)

    # Use first trading day as event date
    event = cal[0]  # This IS a trading day
    entry = next_trading_day(event, cal)
    assert entry is not None
    assert entry > event, (
        f"PIT violation: entry {entry} is not strictly after event {event}"
    )


def test_pit_anchor_on_non_trading_day():
    """When event is a non-trading day, entry should be the first bar after it."""
    prices = _make_price_series(50, start="2010-01-04")
    cal = _make_cal(prices)

    # Saturday 2010-01-02 (before first bar)
    sat = pd.Timestamp("2010-01-02")
    entry = next_trading_day(sat, cal)
    assert entry is not None
    assert entry > sat


def test_car_entry_excludes_event_close():
    """CAR window starts from first bar AFTER event, so event-day close is not included."""
    prices = _make_price_series(100)
    cal = _make_cal(prices)

    # Set event = index 5; entry should be index 6
    event = cal[5]
    entry_expected = cal[6]

    # Compute CAR manually
    h = 10
    car = car_for_event(event, prices, h, cal)
    assert car is not None

    # Manually compute from index 6 (not 5)
    sub = prices.iloc[6: 6 + h + 1]
    expected_car = float(np.log(sub.iloc[-1] / sub.iloc[0]))
    assert abs(car - expected_car) < 1e-10, (
        f"CAR mismatch: got {car}, expected {expected_car}. "
        "Likely including event-day close."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Sector-relative math
# ─────────────────────────────────────────────────────────────────────────────

def test_sector_relative_car_math():
    """sector_relative_car = sector_car - shcomp_car, not sector_car alone."""
    # Build deterministic prices
    n = 80
    cal = pd.bdate_range("2015-01-05", periods=n)
    sector = pd.Series(np.linspace(100, 120, n), index=cal)  # +20% linear
    market = pd.Series(np.linspace(100, 115, n), index=cal)  # +15% linear

    event = cal[0]
    h = 20

    sector_car = car_for_event(event, sector, h, cal)
    market_car = car_for_event(event, market, h, cal)
    rel_car = sector_relative_car(event, sector, market, h, cal)

    assert sector_car is not None
    assert market_car is not None
    assert rel_car is not None

    expected = sector_car - market_car
    assert abs(rel_car - expected) < 1e-12, (
        f"Relative CAR math wrong: got {rel_car}, expected {expected}"
    )
    # Sector outperforms market -> relative CAR should be positive
    assert rel_car > 0, "Sector outperformed market but relative CAR is not positive"


def test_sector_relative_car_zero_when_equal():
    """If sector == market, relative CAR is zero."""
    n = 60
    cal = pd.bdate_range("2015-01-05", periods=n)
    prices = pd.Series(np.linspace(100, 110, n), index=cal)
    event = cal[0]
    rel = sector_relative_car(event, prices, prices.copy(), 20, cal)
    assert rel is not None
    assert abs(rel) < 1e-10


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: No-lookahead — outcome window does not overlap event date
# ─────────────────────────────────────────────────────────────────────────────

def test_no_lookahead_in_car_window():
    """The outcome window must start from the bar AFTER event, not before."""
    n = 100
    cal = pd.bdate_range("2014-01-06", periods=n)

    # Build price that jumps on index 10 (the event day's CLOSE)
    prices_vals = [100.0] * n
    prices_vals[10] = 500.0  # huge spike on event close
    prices = pd.Series(prices_vals, index=cal)
    # Prices return to normal after the spike
    for i in range(11, n):
        prices_vals[i] = 100.0
    prices = pd.Series(prices_vals, index=cal)

    # Event is index 9 (the day before the spike)
    event = cal[9]  # entry should be cal[10] (the spike bar)
    # Since we enter at cal[10] and look forward, CAR includes spike -> normal
    # But event is cal[9], so entry=cal[10] is the spike close.
    # A lookahead violation would include cal[9] in the calculation.
    car = car_for_event(event, prices, 5, cal)
    # The spike is the ENTRY price (start of window), not a gain
    # So CAR from spike down to 100 should be NEGATIVE
    if car is not None:
        # Entry at cal[10]=500, horizon at cal[15]=100 → log(100/500) ≈ -1.6
        assert car < 0, (
            f"Lookahead suspected: spike should be the ENTRY price (loss), got CAR={car}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Suspension rule
# ─────────────────────────────────────────────────────────────────────────────

def test_suspension_drops_when_no_valid_price():
    """Episode should be None if no valid print within SUSP_MAX sessions after event."""
    from scripts.china_policy_events_phase0 import SUSP_MAX

    n = 50
    cal = pd.bdate_range("2016-01-04", periods=n)

    # NaN prices for SUSP_MAX+1 sessions after the intended entry
    prices_vals = np.ones(n) * 100.0
    event = cal[5]
    entry_pos = 6  # first bar after event
    for k in range(SUSP_MAX + 1):
        if entry_pos + k < n:
            prices_vals[entry_pos + k] = np.nan
    prices = pd.Series(prices_vals, index=cal)

    car = car_for_event(event, prices, 10, cal)
    assert car is None, (
        f"Expected None for suspended episode (no valid price within SUSP_MAX), got {car}"
    )


def test_suspension_uses_first_valid_within_susp_max():
    """If a valid price appears within SUSP_MAX sessions, episode should be included."""
    from scripts.china_policy_events_phase0 import SUSP_MAX

    n = 50
    cal = pd.bdate_range("2016-01-04", periods=n)
    prices = pd.Series(np.ones(n) * 100.0, index=cal)

    event = cal[5]
    entry_pos = 6
    # Make first 2 bars NaN, but 3rd is valid (within SUSP_MAX=5)
    prices.iloc[entry_pos] = np.nan
    prices.iloc[entry_pos + 1] = np.nan
    prices.iloc[entry_pos + 2] = 110.0  # valid within SUSP_MAX

    car = car_for_event(event, prices, 10, cal)
    # Should not be None
    assert car is not None, (
        "Episode should not be suspended when valid price appears within SUSP_MAX"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: compute_car_series episode aggregation
# ─────────────────────────────────────────────────────────────────────────────

def test_car_series_length_matches_usable_events():
    """compute_car_series should return as many episodes as have usable windows."""
    n = 100
    cal = pd.bdate_range("2015-01-05", periods=n)
    prices = pd.Series(np.linspace(100, 200, n), index=cal)

    # 3 event dates within panel, 1 after panel end (should be dropped)
    event_dates = pd.DatetimeIndex([cal[5], cal[20], cal[50], cal[-1] + pd.Timedelta(days=30)])

    cars, n_dropped = compute_car_series(event_dates, prices, None, 10, cal, "absolute")
    # The 3 in-panel events should produce CARs; the 1 after panel end is dropped
    assert len(cars) == 3
    assert n_dropped == 1


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: determine_verdict logic
# ─────────────────────────────────────────────────────────────────────────────

def test_verdict_blocked_power():
    """K < 8 -> BLOCKED-POWER."""
    stats = {"K": 5, "mean_car": 0.01, "hac": {"t": 3.0, "p": 0.01}, "dsr": None, "split_half": None}
    v = determine_verdict(stats, {}, "T1")
    assert v == "BLOCKED-POWER"


def test_verdict_no_go_wrong_sign():
    """Negative mean with sub-threshold t -> NO-GO."""
    stats = {
        "K": 20, "mean_car": -0.01,
        "hac": {"t": -0.5, "p": 0.6},
        "dsr": None, "split_half": None,
    }
    v = determine_verdict(stats, {}, "T1", hypothesized_sign=1.0)
    assert v == "NO-GO"


def test_verdict_kill_wrong_sign_significant():
    """Negative mean with significant t -> KILL."""
    stats = {
        "K": 25, "mean_car": -0.05,
        "hac": {"t": -2.5, "p": 0.01},
        "dsr": None, "split_half": None,
    }
    v = determine_verdict(stats, {}, "T1", hypothesized_sign=1.0)
    assert v == "KILL"


def test_verdict_accrue_right_sign_weak():
    """Right sign but sub-threshold -> ACCRUE."""
    stats = {
        "K": 20, "mean_car": 0.005,
        "hac": {"t": 0.5, "p": 0.6},
        "dsr": {"dsr": 0.1}, "split_half": {"same_sign": False},
    }
    v = determine_verdict(stats, {}, "T1", hypothesized_sign=1.0)
    assert v == "ACCRUE"


def test_verdict_go_all_gates_pass():
    """All gates pass -> GO."""
    stats = {
        "K": 30, "mean_car": 0.05,
        "hac": {"t": 2.5, "p": 0.012},
        "dsr": {"dsr": 0.95},
        "split_half": {"same_sign": True},
    }
    bh = {"T1": {"q": 0.08, "reject": True}}
    v = determine_verdict(stats, bh, "T1", hypothesized_sign=1.0)
    assert v == "GO"


# ─────────────────────────────────────────────────────────────────────────────
# Test 9: Registry file has ACCRUE entries (not tracked parquets)
# ─────────────────────────────────────────────────────────────────────────────

def test_registry_has_accrue_entries():
    """After the study runs, registry_seed.json must contain the 3 ACCRUE entries."""
    import json
    import pathlib
    reg = json.loads(pathlib.Path("data/experiments/registry_seed.json").read_text())
    ids = {e["id"] for e in reg["experiments"]}
    assert "china-policy-events-fa-banks-rel" in ids
    assert "china-policy-events-fb-banks-rel" in ids
    assert "china-policy-events-fb-restate-rel" in ids


# ─────────────────────────────────────────────────────────────────────────────
# Test 10: Results JSON exists and has expected structure
# ─────────────────────────────────────────────────────────────────────────────

def test_results_json_structure():
    """Results JSON must exist and contain the 6 gated trial keys."""
    import json
    import pathlib
    r = json.loads(pathlib.Path("data/experiments/china_policy_events_results.json").read_text())
    assert "gated_trials" in r
    assert "bh_fdr" in r
    assert "verdicts" in r
    expected_keys = {
        "T1_FA_SHCOMP", "T2_FA_banks_rel", "T3_FA_restate_rel",
        "T4_FB_SHCOMP", "T5_FB_banks_rel", "T6_FB_restate_rel",
    }
    assert expected_keys.issubset(set(r["gated_trials"].keys()))


def test_results_json_verdicts_are_valid():
    """All verdicts must be valid vocabulary."""
    import json
    import pathlib
    valid = {"GO", "ACCRUE", "NO-GO", "KILL", "BLOCKED-DATA", "BLOCKED-POWER", "EXPLORATORY", "DESCRIPTIVE"}
    r = json.loads(pathlib.Path("data/experiments/china_policy_events_results.json").read_text())
    for key, verdict in r["verdicts"].items():
        assert verdict in valid, f"Invalid verdict for {key}: {verdict}"
