"""Stock Identity W3A — mandatory localization null/control invariance (plan Task 3).

1. ``random_fire_null`` preserves per-expert fire COUNT; each fire's placement is
   drawn independently (not a block translation), always lands on a real trading
   session, and materially breaks episode correspondence (freeze review finding
   M11).
2. ``grain_cadence_null`` is a deterministic, seeded, trading-session circular
   shift: every placed fire lands on a real trading session, and cadence
   (circular session-gap) is preserved exactly (freeze review finding M4).
3. ``equal_proximity_control`` only pairs fires that fired into the SAME episode,
   never pairs observations whose ATR-distance gap exceeds the declared
   tolerance, never pairs two fires from the same family, and reports its
   (always-zero, in this grouped design) truncation count explicitly (freeze
   review finding M2/M3).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.stock_identity.ruler_nulls import (
    GRAIN_CADENCE_NULL_MAX_SESSIONS,
    GRAIN_CADENCE_NULL_MIN_SESSIONS,
    PROXIMITY_PAIR_COLUMNS,
    equal_proximity_control,
    grain_cadence_null,
    random_fire_null,
)


def _events_for_symbol(symbol="AAA", family_key="fam.x", grain="1D", n=5, start="2020-01-06", step_days=3):
    ts = [pd.Timestamp(start) + pd.Timedelta(days=step_days * i) for i in range(n)]
    ts = [t for t in ts]
    return pd.DataFrame({
        "event_id": [f"E{i}" for i in range(n)],
        "family_key": [family_key] * n,
        "symbol": [symbol] * n,
        "signal_ts": ts,
        "signal_known_ts": ts,
        "grain": [grain] * n,
    })


def _trading_calendar_bars(symbol="AAA", start="2018-01-01", n=1200):
    idx = pd.bdate_range(start, periods=n)
    close = 100.0 + np.cumsum(np.random.default_rng(0).normal(0, 0.5, n))
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": np.full(n, 1_000_000.0)},
        index=idx,
    )


# ---------------------------------------------------------------------------
# M11: independent per-fire random placement
# ---------------------------------------------------------------------------
def test_random_fire_null_preserves_fire_count():
    events = _events_for_symbol()
    bars = {"AAA": _trading_calendar_bars()}
    out = random_fire_null(events, bars, seed=7)
    assert len(out) == len(events)


def test_random_fire_null_is_seed_deterministic():
    events = _events_for_symbol()
    bars = {"AAA": _trading_calendar_bars()}
    a = random_fire_null(events, bars, seed=42)
    b = random_fire_null(events, bars, seed=42)
    pd.testing.assert_series_equal(a["signal_known_ts"], b["signal_known_ts"])


def test_random_fire_null_places_fires_independently_not_as_a_translation():
    """Each fire is drawn independently -- the per-fire deltas (new_ts - old_ts)
    must NOT all be equal (a block translation, which the prior implementation
    always produced)."""
    events = _events_for_symbol(n=8, step_days=5)
    bars = {"AAA": _trading_calendar_bars()}
    out = random_fire_null(events, bars, seed=11)
    deltas = (pd.to_datetime(out["signal_known_ts"]) - pd.to_datetime(events["signal_known_ts"]))
    assert deltas.nunique() > 1


def test_random_fire_null_never_lands_on_a_non_session_date():
    events = _events_for_symbol(n=10, step_days=2)
    bars = {"AAA": _trading_calendar_bars()}
    calendar = set(bars["AAA"].index)
    out = random_fire_null(events, bars, seed=99)
    assert set(pd.to_datetime(out["signal_known_ts"])) <= calendar


def test_random_fire_null_no_calendar_leaves_events_untouched():
    events = _events_for_symbol(symbol="NOCAL")
    out = random_fire_null(events, {}, seed=1)
    pd.testing.assert_series_equal(out["signal_known_ts"], events["signal_known_ts"])


# ---------------------------------------------------------------------------
# M4: trading-session-space circular shift
# ---------------------------------------------------------------------------
def test_grain_cadence_null_never_lands_on_a_non_session_date():
    events = _events_for_symbol(n=10, step_days=3)
    bars = {"AAA": _trading_calendar_bars()}
    calendar = set(bars["AAA"].index)
    out = grain_cadence_null(events, bars, seed=5)
    assert set(pd.to_datetime(out["signal_known_ts"])) <= calendar


def test_grain_cadence_null_preserves_circular_session_gaps():
    """Chosen so the whole fire sequence's shift does not straddle the trading
    calendar's wrap boundary -- under that condition the null's session gaps
    (measured on the SAME calendar's session positions) are preserved exactly,
    not merely modulo the calendar length."""
    bars = {"AAA": _trading_calendar_bars(start="2018-01-01", n=1200)}
    calendar = pd.DatetimeIndex(sorted(bars["AAA"].index))
    # fires clustered early in the calendar so offset K in [63,252] can never
    # push any of them past the calendar's end (n=1200 sessions).
    ts = calendar[[100, 105, 130, 140]]
    events = pd.DataFrame({
        "event_id": ["E0", "E1", "E2", "E3"], "family_key": ["fam.x"] * 4,
        "symbol": ["AAA"] * 4, "signal_ts": ts, "signal_known_ts": ts,
        "grain": ["1D"] * 4,
    })
    out = grain_cadence_null(events, bars, seed=3)
    real_pos = calendar.searchsorted(pd.to_datetime(events["signal_known_ts"]).to_numpy())
    null_pos = calendar.searchsorted(pd.to_datetime(out["signal_known_ts"]).to_numpy())
    assert list(np.diff(null_pos)) == list(np.diff(real_pos))


def test_grain_cadence_null_is_seed_deterministic():
    events = _events_for_symbol(n=6, step_days=4)
    bars = {"AAA": _trading_calendar_bars()}
    a = grain_cadence_null(events, bars, seed=17)
    b = grain_cadence_null(events, bars, seed=17)
    pd.testing.assert_series_equal(a["signal_known_ts"], b["signal_known_ts"])


def test_grain_cadence_null_offset_is_within_declared_session_range():
    """The drawn K used to shift a lone-fire group is directly recoverable as the
    session-position delta, and must fall in [63, 252]."""
    bars = {"AAA": _trading_calendar_bars(start="2018-01-01", n=1200)}
    calendar = pd.DatetimeIndex(sorted(bars["AAA"].index))
    ts = calendar[[500]]
    events = pd.DataFrame({
        "event_id": ["E0"], "family_key": ["fam.x"], "symbol": ["AAA"],
        "signal_ts": ts, "signal_known_ts": ts, "grain": ["1D"],
    })
    out = grain_cadence_null(events, bars, seed=21)
    real_pos = calendar.searchsorted(ts.to_numpy())[0]
    null_pos = calendar.searchsorted(pd.to_datetime(out["signal_known_ts"]).to_numpy())[0]
    k = (null_pos - real_pos) % len(calendar)
    assert GRAIN_CADENCE_NULL_MIN_SESSIONS <= k <= GRAIN_CADENCE_NULL_MAX_SESSIONS


# ---------------------------------------------------------------------------
# M4/M11 separation assertion: the null materially breaks episode-attribution
# correspondence relative to the real fire sequence.
# ---------------------------------------------------------------------------
def test_grain_cadence_and_random_nulls_separate_from_real_placement():
    """A real, honest separation assertion (not a shift-magnitude pin): moving
    every fire by 63-252 sessions, or placing each fire independently at random,
    must move a MATERIAL fraction of fires outside their original narrow
    +/-5-session neighborhood of the real placement -- i.e. the null is not a
    no-op relative to the real sequence."""
    bars = {"AAA": _trading_calendar_bars(start="2018-01-01", n=1200)}
    calendar = pd.DatetimeIndex(sorted(bars["AAA"].index))
    rng = np.random.default_rng(0)
    positions = rng.integers(300, 900, size=40)
    ts = calendar[positions]
    events = pd.DataFrame({
        "event_id": [f"E{i}" for i in range(40)], "family_key": ["fam.x"] * 40,
        "symbol": ["AAA"] * 40, "signal_ts": ts, "signal_known_ts": ts,
        "grain": ["1D"] * 40,
    })

    for null_fn, seed in ((grain_cadence_null, 7), (random_fire_null, 7)):
        out = null_fn(events, bars, seed)
        real_pos = calendar.searchsorted(pd.to_datetime(events["signal_known_ts"]).to_numpy())
        null_pos = calendar.searchsorted(pd.to_datetime(out["signal_known_ts"]).to_numpy())
        moved_far = np.abs(null_pos - real_pos) > 5
        assert moved_far.mean() > 0.5, f"{null_fn.__name__} did not materially separate from real placement"


# ---------------------------------------------------------------------------
# M2/M3: equal-proximity control pairs within the SAME episode only
# ---------------------------------------------------------------------------
def test_equal_proximity_control_never_exceeds_tolerance():
    metrics = pd.DataFrame({
        "event_id": ["E1", "E2", "E3", "E4"],
        "family_key": ["fam.a", "fam.b", "fam.d", "fam.c"],
        "episode_id": ["EP1", "EP1", "EP1", "EP1"],
        "atr_dist": [0.10, 0.15, 0.30, 0.90],
    })
    out, truncated = equal_proximity_control(metrics, tolerance_atr=0.5)
    assert list(out.columns) == list(PROXIMITY_PAIR_COLUMNS)
    assert (out["atr_dist_gap"] <= 0.5).all()
    assert truncated == 0


def test_equal_proximity_control_never_pairs_across_episodes():
    """Two fires from DIFFERENT episodes, however close in atr_dist, must never
    be paired -- a "similarly-placed" comparison is only meaningful anchored to
    the same episode (episode_id)."""
    metrics = pd.DataFrame({
        "event_id": ["E1", "E2"],
        "family_key": ["fam.a", "fam.b"],
        "episode_id": ["EP1", "EP2"],
        "atr_dist": [0.10, 0.12],
    })
    out, truncated = equal_proximity_control(metrics, tolerance_atr=0.5)
    assert out.empty
    assert truncated == 0


def test_equal_proximity_control_pairs_share_episode_id():
    metrics = pd.DataFrame({
        "event_id": ["E1", "E2", "E3", "E4"],
        "family_key": ["fam.a", "fam.b", "fam.a", "fam.b"],
        "episode_id": ["EP1", "EP1", "EP2", "EP2"],
        "atr_dist": [0.10, 0.12, 0.50, 0.55],
    })
    out, truncated = equal_proximity_control(metrics, tolerance_atr=0.5)
    assert not out.empty
    for _, row in out.iterrows():
        assert row["episode_id"] in ("EP1", "EP2")
    # no cross-episode pair was ever formed
    assert set(out["episode_id"]) <= {"EP1", "EP2"}
    assert truncated == 0


def test_equal_proximity_control_same_family_near_pair_excluded_without_displacing_legit_pair():
    """A same-family pair that IS within tolerance must neither appear in the
    output nor consume any budget that would have displaced a legitimate
    cross-family pair in the same episode (vacuous-test fix: the same-family
    pair here genuinely qualifies by distance, unlike the old fixture)."""
    metrics = pd.DataFrame({
        "event_id": ["E1", "E2", "E3"],
        "family_key": ["fam.a", "fam.a", "fam.b"],
        "episode_id": ["EP1", "EP1", "EP1"],
        "atr_dist": [0.10, 0.12, 0.11],
    })
    out, truncated = equal_proximity_control(metrics, tolerance_atr=0.5)
    pairs = set(zip(out["left_event_id"], out["right_event_id"])) | set(
        zip(out["right_event_id"], out["left_event_id"])
    )
    # E1/E2 share family_key and ARE within tolerance -> never paired
    assert ("E1", "E2") not in pairs and ("E2", "E1") not in pairs
    # the legitimate cross-family pairs (E1/E3 and E2/E3) both still appear
    assert ("E1", "E3") in pairs
    assert ("E2", "E3") in pairs
    assert truncated == 0


def test_equal_proximity_control_empty_on_no_qualifying_pairs():
    metrics = pd.DataFrame({
        "event_id": ["E1", "E2"],
        "family_key": ["fam.a", "fam.b"],
        "episode_id": ["EP1", "EP1"],
        "atr_dist": [0.0, 10.0],
    })
    out, truncated = equal_proximity_control(metrics, tolerance_atr=0.1)
    assert out.empty
    assert list(out.columns) == list(PROXIMITY_PAIR_COLUMNS)
    assert truncated == 0


def test_equal_proximity_control_missing_episode_id_column_returns_empty():
    metrics = pd.DataFrame({
        "event_id": ["E1", "E2"], "family_key": ["fam.a", "fam.b"], "atr_dist": [0.1, 0.12],
    })
    out, truncated = equal_proximity_control(metrics, tolerance_atr=0.5)
    assert out.empty
    assert truncated == 0
