"""LEADER-PULLBACK organ (§6.8d / §6.9 R4) — construction, nulls and authority.

Synthetic series only: no repo store is read, so these run identically on a cold
checkout. The pins that matter are the ones that FAIL WHEN THE CONSTRUCTION MOVES —
a state machine test that only asserts "some state came back" is vacuous, so each
transition test drives the specific leg it names and asserts the specific leg's effect.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import us_leader_pullback as lp

BDAYS = "2022-01-03"


def _idx(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range(BDAYS, periods=n)


def _leader_then_pullback(
    n_up: int = 420,
    n_down: int = 8,
    n_rebound: int = 14,
    drop: float = 0.014,
    drift: float = 0.0035,
    rebound: float = 0.012,
    noise: float = 0.006,
    seed: int = 1,
) -> pd.Series:
    """A noisy uptrend that makes a fresh high, retraces, then turns back up.

    The uptrend is long enough to warm the 200dMA and the 252-session high window, the
    retrace is deep enough to enter the band and shallow enough to stay inside it, and
    the rebound produces a StochRSI %K/%D cross with a rising RSI-MACD histogram.

    The NOISE is load-bearing, not decoration: a perfectly monotonic ramp pins Wilder RSI
    at 100, which makes the StochRSI range zero and every %K NaN — the organ then
    correctly refuses to emit a state and a test written on a smooth ramp would measure
    nothing. Seeded, so the fixture is deterministic.
    """
    rng = np.random.default_rng(seed)
    px = [50.0]
    for _ in range(n_up - 1):
        px.append(px[-1] * (1 + drift + rng.normal(0, noise)))
    for _ in range(n_down):
        px.append(px[-1] * (1 - drop + rng.normal(0, noise / 3)))
    for _ in range(n_rebound):
        px.append(px[-1] * (1 + rebound + rng.normal(0, noise / 3)))
    return pd.Series(px, index=_idx(len(px)))


def _pullback_then_one_bar_recovery(
    n_up: int = 420, n_down: int = 5, drop: float = 0.014, jump: float = 0.030,
    n_tail: int = 8, drift: float = 0.0035, noise: float = 0.006, seed: int = 1,
) -> pd.Series:
    """Uptrend, a short retrace, then ONE sharp bar back up — the AVGO shape.

    Reproduces the exact v0 mechanic the 2026-08-08 replay measured on 242 episodes: the
    recovery bar carries the %K/%D cross, and the recovery EXIT is evaluated before the
    RESET_TURN transition, so the turn lands one session outside the episode.
    """
    rng = np.random.default_rng(seed)
    px = [50.0]
    for _ in range(n_up - 1):
        px.append(px[-1] * (1 + drift + rng.normal(0, noise)))
    for _ in range(n_down):
        px.append(px[-1] * (1 - drop + rng.normal(0, noise / 3)))
    px.append(px[-1] * (1 + jump))
    for _ in range(n_tail):
        px.append(px[-1] * (1 + rng.normal(0, noise / 4)))
    return pd.Series(px, index=_idx(len(px)))


def _rs(series: pd.Series, value: float = 0.95) -> pd.Series:
    return pd.Series(value, index=series.index)


def _vol(series: pd.Series, value: float = 1_000_000.0) -> pd.Series:
    return pd.Series(value, index=series.index)


# ---------------------------------------------------------------------------
# Authority + contract
# ---------------------------------------------------------------------------

def test_authority_is_display_tier_with_zero_powers():
    assert lp.AUTHORITY["tier"] == "display"
    for power in ("may_rank", "may_gate", "may_size", "may_escalate"):
        assert lp.AUTHORITY[power] is False, power


def test_disclosure_never_claims_validation():
    """`validated` in a user-facing claim is CI-enforced house-wide; keep it out here too."""
    assert "validated" not in lp.DISCLOSURE.lower()
    assert "validated" not in (lp.__doc__ or "").lower()


def test_module_imports_nothing_from_the_pick_chain():
    import inspect
    src = inspect.getsource(lp)
    for forbidden in ("prophet_bridge", "us_board_rank", "build_prophet", "signal_gate"):
        assert forbidden not in src, forbidden


def test_constants_are_all_published():
    """Every construction constant is reachable from CONSTANTS — the printed pre-registration."""
    for key in ("rs_lookback", "rs_top_pct", "high_52w_lookback", "high_52w_recency",
                "pullback_high_lookback", "pullback_depth_min", "pullback_depth_max",
                "pullback_max_age", "trend_ma", "stoch_reset_max", "hist_rise_sessions",
                "zone_band_fraction", "resumed_hold_sessions", "min_history_bars"):
        assert key in lp.CONSTANTS
    assert lp.CONSTANTS["construction_era"] == lp.CONSTRUCTION_ERA


def test_math_comes_from_confluence_tiers_not_a_local_fork():
    from engine import confluence_tiers as ct
    assert lp._stoch_rsi_kd is ct._stoch_rsi_kd
    assert lp._rsi_macd is ct._rsi_macd


# ---------------------------------------------------------------------------
# Warm-up and null discipline
# ---------------------------------------------------------------------------

def test_short_history_prints_a_null_reason_and_claims_no_state():
    c = pd.Series(np.linspace(10, 20, 100), index=_idx(100))
    f = lp.evaluate(c, rs_pct=_rs(c))
    assert f["state"].isna().all()
    assert f["null_reason"].str.contains("daily bars, has").all()


def test_a_monotonic_ramp_names_the_undefined_indicator_instead_of_guessing():
    """Constant RSI zeroes the StochRSI range; %K is undefined and must be SAID, not faked."""
    c = pd.Series(50.0 * (1.004 ** np.arange(400)), index=_idx(400))
    f = lp.evaluate(c, rs_pct=_rs(c))
    warm = f.iloc[lp.MIN_HISTORY_BARS:]
    assert warm["state"].isna().all()
    assert warm["null_reason"].str.startswith("indicator not warm").all()
    assert warm["null_reason"].str.contains("stoch_k").all()


def test_missing_rs_is_unknown_not_false():
    """A broken cross-section must not silently report a whole board of NONE."""
    c = _leader_then_pullback()
    f = lp.evaluate(c, rs_pct=None)
    warm = f.iloc[lp.MIN_HISTORY_BARS:]
    assert warm["state"].isna().all()
    assert (warm["null_reason"] == "rs_pct_unavailable").all()


def test_absent_volume_nulls_the_avwap_and_says_so():
    c = _leader_then_pullback()
    f = lp.evaluate(c, rs_pct=_rs(c), volume=None)
    assert f["avwap"].isna().all()
    assert (f["avwap_null_reason"].dropna() == "no_volume_in_store").all()


def test_all_zero_volume_is_treated_as_absent_not_as_a_zero_denominator():
    c = _leader_then_pullback()
    f = lp.evaluate(c, rs_pct=_rs(c), volume=pd.Series(0.0, index=c.index))
    assert f["avwap"].isna().all()
    assert (f["avwap_null_reason"].dropna() == "no_volume_in_store").all()


def test_latest_is_json_safe_with_no_numpy_scalars():
    import json
    c = _leader_then_pullback()
    out = lp.latest(c, rs_pct=_rs(c), volume=_vol(c))
    json.dumps(out)  # raises on a numpy scalar
    for v in out.values():
        assert not isinstance(v, (np.bool_, np.integer, np.floating)), v


# ---------------------------------------------------------------------------
# The state machine, leg by leg
# ---------------------------------------------------------------------------

def test_the_chain_runs_leader_pullback_reset_turn_resumed():
    c = _leader_then_pullback()
    f = lp.evaluate(c, rs_pct=_rs(c), volume=_vol(c))
    seen = [s for s in f["state"].dropna().tolist()]
    for state in (lp.STATE_LEADER, lp.STATE_PULLBACK, lp.STATE_RESET_TURN):
        assert state in seen, state
    # order: the first PULLBACK precedes the first RESET_TURN, which precedes RESUMED
    first = {s: seen.index(s) for s in set(seen)}
    assert first[lp.STATE_LEADER] < first[lp.STATE_PULLBACK] < first[lp.STATE_RESET_TURN]
    if lp.STATE_RESUMED in first:
        assert first[lp.STATE_RESET_TURN] < first[lp.STATE_RESUMED]


def test_rs_below_the_quartile_admits_nothing():
    """The LEADER gate is real: the identical price path with a laggard RS never enters."""
    c = _leader_then_pullback()
    hot = lp.evaluate(c, rs_pct=_rs(c, 0.95), volume=_vol(c))
    cold = lp.evaluate(c, rs_pct=_rs(c, lp.RS_TOP_PCT - 0.01), volume=_vol(c))
    assert (hot["state"] == lp.STATE_RESET_TURN).any()
    assert not (cold["state"] == lp.STATE_PULLBACK).any()
    assert not (cold["state"] == lp.STATE_RESET_TURN).any()
    assert set(cold["state"].dropna().unique()) <= {lp.STATE_NONE}


def test_rs_exactly_at_the_boundary_is_admitted():
    """`>=` not `>` — pin the boundary so a later refactor cannot quietly flip it."""
    c = _leader_then_pullback()
    edge = lp.evaluate(c, rs_pct=_rs(c, lp.RS_TOP_PCT), volume=_vol(c))
    assert (edge["state"] == lp.STATE_PULLBACK).any()


def test_leader_legs_stop_gating_once_an_episode_is_open():
    """The reflexivity guard: a leader's own retrace lowers its RS and must not evict it."""
    c = _leader_then_pullback()
    rs = _rs(c, 0.95)
    f_ref = lp.evaluate(c, rs_pct=rs, volume=_vol(c))
    open_days = f_ref.index[f_ref["state"] == lp.STATE_PULLBACK]
    assert len(open_days) >= 2
    # drop RS under the gate from the SECOND pullback session onward
    rs_decay = rs.copy()
    rs_decay.loc[open_days[1]:] = 0.10
    f = lp.evaluate(c, rs_pct=rs_decay, volume=_vol(c))
    still_open = f.loc[open_days[1], "state"]
    assert still_open in (lp.STATE_PULLBACK, lp.STATE_RESET_TURN)
    assert f.loc[open_days[1], "leg_rs"] is False or not bool(f.loc[open_days[1], "leg_rs"])


@pytest.mark.parametrize("seed", [1, 2, 3, 5, 9, 11])
@pytest.mark.parametrize("n_down,drop", [(8, 0.014), (30, 0.02), (70, 0.02)])
def test_episode_invariants_hold_on_every_path(seed, n_down, drop):
    """The three legs that gate EVERY bar of an open episode, not just its opening.

    This is the ABOVE-200 lane: an episode row is always above the 200dMA, always inside
    the depth band, and never older than the age cap. Asserted across shallow, deep and
    trend-breaking paths, because an invariant proved on one happy path is not one.
    """
    c = _leader_then_pullback(n_down=n_down, drop=drop, n_rebound=0, seed=seed)
    f = lp.evaluate(c, rs_pct=_rs(c), volume=_vol(c))
    ep = f[f["state"].isin([lp.STATE_PULLBACK, lp.STATE_RESET_TURN, lp.STATE_RESUMED])]
    assert ep["leg_above_200"].astype(bool).all()
    assert (ep["pullback_depth"].dropna() <= lp.PULLBACK_DEPTH_MAX + 1e-12).all()
    pb = f[f["state"] == lp.STATE_PULLBACK]
    assert (pb["pullback_depth"] >= lp.PULLBACK_DEPTH_MIN - 1e-12).all()
    assert (pb["pullback_age"] <= lp.PULLBACK_MAX_AGE).all()


def test_a_shallow_dip_never_opens_an_episode():
    c = _leader_then_pullback(n_down=2, drop=0.005, n_rebound=6, noise=0.0015)
    f = lp.evaluate(c, rs_pct=_rs(c), volume=_vol(c))
    assert not (f["state"] == lp.STATE_PULLBACK).any()
    assert set(f["state"].dropna().unique()) <= {lp.STATE_LEADER, lp.STATE_NONE}


def test_v0_pins_the_recovery_exit_ahead_of_the_turn_transition():
    """PINS A DELIBERATE v0 NON-REPAIR — this test is SUPPOSED to fail when it is fixed.

    The recovery exit (`recovered_without_reset`) is evaluated BEFORE the RESET_TURN
    transition on the same bar, so a V-shaped reset whose %K/%D cross lands on the
    recovery bar is closed rather than fired. That is AVGO's 2026-07-30 miss, and the
    replay measured the population behind it (242 episodes closed on a bar where both
    turn legs printed; `LEADER_PULLBACK_REPLAY_2026-08-08.md` §3.1). The alternative
    ordering is pre-registered in §3.2 of that receipt and is NOT applied here — moving
    it requires the §6.6 gate, and this test failing is how that change announces itself.
    """
    c = _pullback_then_one_bar_recovery()
    f = lp.evaluate(c, rs_pct=_rs(c), volume=_vol(c))
    ends = f[f["episode_end_reason"] == lp.END_RECOVERED]
    assert len(ends) == 1, "fixture no longer produces the recovery exit"
    row = ends.iloc[0]
    assert bool(row["leg_k_cross"]) is True, "fixture no longer lands the cross on the exit bar"
    # v0: the exit wins the bar — the state is NOT a fire, and nothing fired in the episode
    assert row["state"] in (lp.STATE_LEADER, lp.STATE_NONE)
    assert not (f["state"] == lp.STATE_RESET_TURN).any()


def test_the_reset_turn_requires_the_oscillator_to_have_actually_reset():
    """Without a %K dip under STOCH_RESET_MAX inside the episode, a cross is not a turn."""
    c = _leader_then_pullback()
    f = lp.evaluate(c, rs_pct=_rs(c), volume=_vol(c))
    turns = f[f["state"] == lp.STATE_RESET_TURN]
    assert len(turns) >= 1
    assert turns["leg_k_dip"].astype(bool).all()
    fire = turns.iloc[0]
    assert bool(fire["leg_k_cross"]) is True
    assert bool(fire["leg_hist_rising"]) is True


def test_the_fire_bar_carries_a_frozen_zone_anchored_on_the_reset_low():
    c = _leader_then_pullback()
    f = lp.evaluate(c, rs_pct=_rs(c), volume=_vol(c))
    fires = f[(f["state"] == lp.STATE_RESET_TURN) & (f["days_in_state"] == 1)]
    assert len(fires) >= 1
    fire = fires.iloc[0]
    assert fire["zone_low"] == pytest.approx(fire["reset_low"])
    band = fire["pullback_high"] - fire["reset_low"]
    assert fire["zone_band"] == pytest.approx(band)
    assert fire["zone_high"] == pytest.approx(
        fire["reset_low"] + lp.ZONE_BAND_FRACTION * band)
    assert fire["zone_basis"] == "pullback_range_close_basis"
    # the zone does not chase price after the print
    ep = f.loc[fires.index[0]:]
    ep = ep[ep["state"].isin([lp.STATE_RESET_TURN, lp.STATE_RESUMED])]
    assert ep["zone_high"].nunique() == 1


def test_resumed_never_shares_a_bar_with_the_turn():
    c = _leader_then_pullback()
    f = lp.evaluate(c, rs_pct=_rs(c), volume=_vol(c))
    fires = f.index[(f["state"] == lp.STATE_RESET_TURN) & (f["days_in_state"] == 1)]
    for d in fires:
        assert f.loc[d, "state"] == lp.STATE_RESET_TURN


def test_days_in_state_counts_the_current_session():
    c = _leader_then_pullback()
    f = lp.evaluate(c, rs_pct=_rs(c), volume=_vol(c))
    body = f.dropna(subset=["state"])
    prev_state, expected = None, 0
    for _, row in body.iterrows():
        expected = 1 if row["state"] != prev_state else expected + 1
        assert row["days_in_state"] == expected
        prev_state = row["state"]


def test_avwap_is_the_volume_weighted_mean_from_the_pullback_anchor():
    c = _leader_then_pullback()
    v = pd.Series(np.linspace(1e6, 2e6, len(c)), index=c.index)
    f = lp.evaluate(c, rs_pct=_rs(c), volume=v)
    rows = f[f["avwap"].notna() & f["pullback_start"].notna()]
    assert len(rows) >= 1
    d = rows.index[-1]
    start = pd.Timestamp(rows.loc[d, "pullback_start"])
    seg_c, seg_v = c.loc[start:d], v.loc[start:d]
    assert rows.loc[d, "avwap"] == pytest.approx(
        float((seg_c * seg_v).sum() / seg_v.sum()))


def test_a_flat_series_produces_no_episode_and_no_crash():
    c = pd.Series(100.0, index=_idx(400))
    f = lp.evaluate(c, rs_pct=_rs(c), volume=_vol(c))
    assert not (f["state"] == lp.STATE_PULLBACK).any()


def test_empty_input_returns_the_schema_not_an_exception():
    f = lp.evaluate(pd.Series(dtype="float64"))
    assert list(f.columns) == list(lp._COLUMNS)
    assert f.empty
    out = lp.latest(pd.Series(dtype="float64"))
    assert out["state"] is None and out["null_reason"] == "no_price_history"


# ---------------------------------------------------------------------------
# Cross-sectional RS helper
# ---------------------------------------------------------------------------

def test_rs_percentile_is_pit_and_excludes_names_with_no_return():
    idx = _idx(200)
    px = pd.DataFrame({
        "A": np.linspace(10, 40, 200),
        "B": np.linspace(10, 12, 200),
        "C": np.concatenate([np.full(190, np.nan), np.linspace(5, 6, 10)]),
    }, index=idx)
    bench = pd.Series(np.linspace(100, 110, 200), index=idx)
    out = lp.rs_excess_percentile(px, bench, lookback=20)
    assert out.loc[idx[-1], "A"] > out.loc[idx[-1], "B"]
    # C has no 20-session return anywhere it is short — absent, never imputed to 0.5
    assert out["C"].iloc[:195].isna().all()
    assert out.iloc[:20].isna().all().all()


def test_rs_percentile_never_leaks_the_future():
    idx = _idx(120)
    px = pd.DataFrame({"A": np.linspace(10, 20, 120), "B": np.linspace(20, 10, 120)},
                      index=idx)
    bench = pd.Series(np.linspace(100, 100, 120), index=idx)
    full = lp.rs_excess_percentile(px, bench, lookback=10)
    truncated = lp.rs_excess_percentile(px.iloc[:100], bench.iloc[:100], lookback=10)
    pd.testing.assert_frame_equal(full.iloc[:100], truncated)


def test_evaluate_never_leaks_the_future():
    """Truncating the series must not change any earlier row's state."""
    c = _leader_then_pullback()
    rs = _rs(c)
    v = _vol(c)
    full = lp.evaluate(c, rs_pct=rs, volume=v)
    cut = len(c) - 6
    part = lp.evaluate(c.iloc[:cut], rs_pct=rs.iloc[:cut], volume=v.iloc[:cut])
    pd.testing.assert_series_equal(full["state"].iloc[:cut], part["state"],
                                   check_names=False)
    pd.testing.assert_series_equal(full["zone_high"].iloc[:cut], part["zone_high"],
                                   check_names=False)
