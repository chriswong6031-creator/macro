"""Stock Identity W3A — mandatory localization null/control invariance (plan Task 3).

1. ``random_fire_null`` is count- AND dwell-matched (freeze §4.3 item 1;
   M11-regression fix): every expert's fire COUNT and its inter-fire gap
   MULTISET are both preserved (the gap sequence is permuted and re-anchored,
   not drawn independently), every placed ``signal_ts`` lands on a real trading
   session, each event's own stamp lag is preserved exactly, and the null
   materially breaks episode correspondence.
2. ``grain_cadence_null`` (Ruling 3, SI-W3A-RULER-V1 PR-3 seal law) is a
   deterministic, seeded, trading-session BASE shift (multiple of the group's
   own grain period) PLUS an independent, bounded (<=4 session) per-fire snap
   to that fire's own original weekday: every non-``"unestimable"`` row lands
   on a real trading session carrying its own original weekday EXACTLY, each
   event's own stamp lag (``signal_known_ts - signal_ts``) is preserved
   exactly, and the group's chronological fire order is preserved. This is
   explicitly NOT dwell-matched (only ``random_fire_null``, null #1, carries
   the exact count/dwell law) -- the per-fire snap is a declared, bounded gap
   perturbation. A group whose snap would collide or invert chronological
   order, or that has no lawful same-weekday target for some fire, is marked
   ``cadence_null_state == "unestimable"`` and left untouched.
3. ``equal_proximity_control`` only pairs fires that fired into the SAME
   episode AND SAME grain (M3-minor added grain to the group key), never pairs
   observations whose ATR-distance gap exceeds the declared tolerance, never
   pairs two fires from the same family, and reports its (always-zero, in this
   grouped design) truncation count explicitly (freeze review finding M2/M3).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.stock_identity.ruler_nulls import (
    GRAIN_CADENCE_NULL_MAX_SESSIONS,
    GRAIN_CADENCE_NULL_MIN_SESSIONS,
    GRAIN_CADENCE_SNAP_BOUND_SESSIONS,
    GRAIN_PERIOD_SESSIONS,
    PROXIMITY_PAIR_COLUMNS,
    equal_proximity_control,
    grain_cadence_null,
    grain_cadence_null_summary,
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


def _trading_calendar_bars_with_holidays(symbol="AAA", start="2018-01-01", n=1200, seed=20260828):
    """A REAL-shaped trading calendar: a plain business-day range with a
    synthetic holiday dropped ~once every 5 weeks (25 business days) -- never
    on a fixed weekday, so the calendar's own periodic phase genuinely breaks
    (weekday-phase MAJOR fix, delta-review third pass discriminating fixture).
    A holiday-FREE ``pd.bdate_range`` (the prior discriminating test's fixture)
    makes every 5-session shift trivially weekday-preserving, since session
    count and calendar weeks coincide exactly with no gaps -- that coincidence
    is exactly what let the M4-regression fix's own test pass despite not
    actually verifying weekday agreement. This fixture removes it."""
    idx_full = pd.bdate_range(start, periods=n + n // 15 + 20)
    rng = np.random.default_rng(seed)
    drop_mask = np.zeros(len(idx_full), dtype=bool)
    i = 0
    while i < len(idx_full):
        i += 25  # ~5 weeks of business days
        if i < len(idx_full):
            offset = int(rng.integers(-2, 3))
            drop_idx = min(max(i + offset, 0), len(idx_full) - 1)
            drop_mask[drop_idx] = True
    idx = idx_full[~drop_mask][:n]
    close = 100.0 + np.cumsum(np.random.default_rng(1).normal(0, 0.5, len(idx)))
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": np.full(len(idx), 1_000_000.0)},
        index=idx,
    )


# ---------------------------------------------------------------------------
# M11: count/dwell-matched random fire placement (freeze §4.3 item 1;
# M11-regression fix)
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


def test_random_fire_null_preserves_the_inter_fire_gap_multiset():
    """M11-regression discriminating test (dwell-matched): the MULTISET of
    session gaps between consecutive fires (sorted by signal_ts) must be
    preserved EXACTLY -- only the anchor and the gaps' ORDER may change. The
    prior (independent-uniform-placement) implementation destroys this
    multiset entirely and fails this test."""
    events = _events_for_symbol(n=8, step_days=5)
    bars = {"AAA": _trading_calendar_bars()}
    calendar = pd.DatetimeIndex(sorted(bars["AAA"].index))
    out = random_fire_null(events, bars, seed=11)

    def _gaps(ts_col):
        pos = np.sort(calendar.searchsorted(pd.to_datetime(ts_col).to_numpy()))
        return sorted(np.diff(pos).tolist())

    assert _gaps(out["signal_ts"]) == _gaps(events["signal_ts"])


def test_random_fire_null_does_not_degenerate_to_a_single_block_translation():
    """The re-anchored, gap-permuted placement must not collapse to a uniform
    per-fire delta (a pure block translation) -- the per-fire deltas
    (new_ts - old_ts) must NOT all be equal."""
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
    assert set(pd.to_datetime(out["signal_ts"])) <= calendar


def test_random_fire_null_no_calendar_leaves_events_untouched():
    events = _events_for_symbol(symbol="NOCAL")
    out = random_fire_null(events, {}, seed=1)
    pd.testing.assert_series_equal(out["signal_known_ts"], events["signal_known_ts"])


def test_random_fire_null_preserves_stamp_lag_exactly():
    """Each event's own stamp lag (signal_known_ts - signal_ts) must be
    preserved EXACTLY as a timedelta, identically to grain_cadence_null."""
    bars = {"AAA": _trading_calendar_bars(start="2018-01-01", n=1200)}
    calendar = pd.DatetimeIndex(sorted(bars["AAA"].index))
    signal_ts = calendar[[200, 210, 220]]
    lags = [pd.Timedelta(days=0), pd.Timedelta(days=1), pd.Timedelta(hours=6)]
    known_ts = [s + l for s, l in zip(signal_ts, lags)]
    events = pd.DataFrame({
        "event_id": ["E0", "E1", "E2"], "family_key": ["fam.x"] * 3, "symbol": ["AAA"] * 3,
        "signal_ts": signal_ts, "signal_known_ts": known_ts, "grain": ["1D"] * 3,
    })
    out = random_fire_null(events, bars, seed=9)
    orig_lag = pd.to_datetime(events["signal_known_ts"]) - pd.to_datetime(events["signal_ts"])
    new_lag = pd.to_datetime(out["signal_known_ts"]) - pd.to_datetime(out["signal_ts"])
    pd.testing.assert_series_equal(
        orig_lag.reset_index(drop=True), new_lag.reset_index(drop=True), check_names=False,
    )


# ---------------------------------------------------------------------------
# M4: trading-session-space circular shift
# ---------------------------------------------------------------------------
def test_grain_cadence_null_never_lands_on_a_non_session_date():
    events = _events_for_symbol(n=10, step_days=3)
    bars = {"AAA": _trading_calendar_bars()}
    calendar = set(bars["AAA"].index)
    out = grain_cadence_null(events, bars, seed=5)
    assert set(pd.to_datetime(out["signal_known_ts"])) <= calendar


def test_grain_cadence_null_is_seed_deterministic():
    events = _events_for_symbol(n=6, step_days=4)
    bars = {"AAA": _trading_calendar_bars()}
    a = grain_cadence_null(events, bars, seed=17)
    b = grain_cadence_null(events, bars, seed=17)
    pd.testing.assert_series_equal(a["signal_known_ts"], b["signal_known_ts"])


def test_grain_cadence_null_base_shift_is_within_declared_session_range():
    """Ruling 3: the SHARED BASE shift K (before the per-fire weekday snap) is
    directly reconstructible from the published ``snap_sessions`` column as
    ``null_pos - snap_sessions - real_pos``, and must fall in [63, 252] -- the
    per-fire snap layered on top (<=4 sessions) is a SEPARATE, declared
    perturbation and is deliberately excluded from this bound (the prior
    design's test measured the fully-realized shift, which no longer equals
    the base K once a bounded snap is added)."""
    bars = {"AAA": _trading_calendar_bars(start="2018-01-01", n=1200)}
    calendar = pd.DatetimeIndex(sorted(bars["AAA"].index))
    ts = calendar[[500]]
    events = pd.DataFrame({
        "event_id": ["E0"], "family_key": ["fam.x"], "symbol": ["AAA"],
        "signal_ts": ts, "signal_known_ts": ts, "grain": ["1D"],
    })
    out = grain_cadence_null(events, bars, seed=21)
    assert out["cadence_null_state"].iloc[0] == "applied"
    real_pos = calendar.searchsorted(ts.to_numpy())[0]
    null_pos = calendar.searchsorted(pd.to_datetime(out["signal_known_ts"]).to_numpy())[0]
    snap = int(out["snap_sessions"].iloc[0])
    base_k = (null_pos - snap - real_pos) % len(calendar)
    assert GRAIN_CADENCE_NULL_MIN_SESSIONS <= base_k <= GRAIN_CADENCE_NULL_MAX_SESSIONS


def test_grain_cadence_null_base_shift_is_a_multiple_of_the_grain_period():
    """The BASE shift K (reconstructed by subtracting the published
    ``snap_sessions``) must be a MULTIPLE of the group's own grain period in
    sessions (GRAIN_PERIOD_SESSIONS) -- this is what preserves cadence PHASE
    at the base-shift stage, before the per-fire snap. A weekly (grain='W',
    period 5) group's base K must be a multiple of 5."""
    bars = {"AAA": _trading_calendar_bars(start="2018-01-01", n=1200)}
    calendar = pd.DatetimeIndex(sorted(bars["AAA"].index))
    ts = calendar[[500]]
    events = pd.DataFrame({
        "event_id": ["E0"], "family_key": ["fam.x"], "symbol": ["AAA"],
        "signal_ts": ts, "signal_known_ts": ts, "grain": ["W"],
    })
    period = GRAIN_PERIOD_SESSIONS["W"]
    for seed in range(10):
        out = grain_cadence_null(events, bars, seed=seed)
        if out["cadence_null_state"].iloc[0] != "applied":
            continue
        real_pos = calendar.searchsorted(ts.to_numpy())[0]
        null_pos = calendar.searchsorted(pd.to_datetime(out["signal_ts"]).to_numpy())[0]
        snap = int(out["snap_sessions"].iloc[0])
        base_k = (null_pos - snap - real_pos) % len(calendar)
        assert base_k % period == 0, f"seed {seed}: base_k={base_k} is not a multiple of {period}"


def test_grain_cadence_null_preserves_weekday_for_every_non_unestimable_row():
    """Ruling 3 discriminating test: proved on a REAL-shaped calendar carrying
    synthetic holidays (not a holiday-free ``pd.bdate_range``, where a
    period-multiple offset is trivially weekday-preserving because session
    count and calendar weeks coincide exactly with no gaps). Every row whose
    ``cadence_null_state == "applied"`` must land EXACTLY on its own original
    weekday -- the per-fire snap makes this achievable regardless of how the
    holiday-perturbed calendar warps the shared base shift."""
    bars = {"AAA": _trading_calendar_bars_with_holidays(start="2018-01-01", n=1200)}
    calendar = pd.DatetimeIndex(sorted(bars["AAA"].index))
    fridays = calendar[calendar.weekday == 4]
    fridays = fridays[calendar.searchsorted(fridays) < 200][:10]
    events = pd.DataFrame({
        "event_id": [f"E{i}" for i in range(len(fridays))],
        "family_key": ["fam.w"] * len(fridays), "symbol": ["AAA"] * len(fridays),
        "signal_ts": fridays, "signal_known_ts": fridays, "grain": ["W"] * len(fridays),
    })
    out = grain_cadence_null(events, bars, seed=13)
    applied = out.loc[out["cadence_null_state"] == "applied"]
    assert len(applied) > 0
    assert set(pd.to_datetime(applied["signal_ts"]).dt.weekday) == {4}
    assert applied["phase_preserved"].fillna(False).astype(bool).all()


def test_grain_cadence_null_snap_sessions_within_declared_bound():
    """Every published ``snap_sessions`` value must respect the declared
    :data:`GRAIN_CADENCE_SNAP_BOUND_SESSIONS` bound (4)."""
    bars = {"AAA": _trading_calendar_bars_with_holidays(start="2018-01-01", n=1200)}
    calendar = pd.DatetimeIndex(sorted(bars["AAA"].index))
    fridays = calendar[calendar.weekday == 4][:60]
    events = pd.DataFrame({
        "event_id": [f"E{i}" for i in range(len(fridays))],
        "family_key": ["fam.w"] * len(fridays), "symbol": ["AAA"] * len(fridays),
        "signal_ts": fridays, "signal_known_ts": fridays, "grain": ["W"] * len(fridays),
    })
    for seed in range(8):
        out = grain_cadence_null(events, bars, seed=seed)
        applied = out.loc[out["cadence_null_state"] == "applied"]
        if applied.empty:
            continue
        snaps = applied["snap_sessions"].astype(int)
        assert snaps.abs().max() <= GRAIN_CADENCE_SNAP_BOUND_SESSIONS


def test_grain_cadence_null_preserves_chronological_order_when_applied():
    """Within an ``"applied"`` group, the NEW positions (in the group's own
    original chronological order) must be strictly increasing -- the same
    invariant the collision/inversion check enforces before a group is ever
    marked ``"applied"``."""
    bars = {"AAA": _trading_calendar_bars(start="2018-01-01", n=1200)}
    calendar = pd.DatetimeIndex(sorted(bars["AAA"].index))
    ts = calendar[[100, 105, 130, 140, 175]]
    events = pd.DataFrame({
        "event_id": [f"E{i}" for i in range(5)], "family_key": ["fam.x"] * 5,
        "symbol": ["AAA"] * 5, "signal_ts": ts, "signal_known_ts": ts,
        "grain": ["1D"] * 5,
    })
    out = grain_cadence_null(events, bars, seed=3)
    assert (out["cadence_null_state"] == "applied").all()
    orig_pos = calendar.searchsorted(pd.to_datetime(events["signal_ts"]).to_numpy())
    new_pos = calendar.searchsorted(pd.to_datetime(out["signal_ts"]).to_numpy())
    order = np.argsort(orig_pos, kind="stable")
    assert np.all(np.diff(new_pos[order]) > 0)


def test_grain_cadence_null_dense_cluster_marks_group_unestimable():
    """Ruling 3's typed-refusal path: a dense, wide weekly-grain group on a
    holiday-perturbed calendar (20 fires across 400 sessions) can produce a
    snap collision/inversion for at least one seed -- that group must be
    marked ``cadence_null_state == "unestimable"`` for EVERY row and left
    completely UNTOUCHED (original signal_ts/signal_known_ts preserved, no
    phase_preserved/snap_sessions value), never a forced or partially-broken
    shift."""
    bars = {"AAA": _trading_calendar_bars_with_holidays(start="2018-01-01", n=1200)}
    calendar = pd.DatetimeIndex(sorted(bars["AAA"].index))
    fridays = calendar[calendar.weekday == 4]
    fridays = fridays[calendar.searchsorted(fridays) < 400][:20]
    events = pd.DataFrame({
        "event_id": [f"E{i}" for i in range(len(fridays))],
        "family_key": ["fam.w"] * len(fridays), "symbol": ["AAA"] * len(fridays),
        "signal_ts": fridays, "signal_known_ts": fridays, "grain": ["W"] * len(fridays),
    })
    found = False
    for seed in range(60):
        out = grain_cadence_null(events, bars, seed=seed)
        if (out["cadence_null_state"] == "unestimable").all():
            found = True
            pd.testing.assert_series_equal(
                out["signal_ts"].reset_index(drop=True), events["signal_ts"].reset_index(drop=True),
                check_names=False,
            )
            pd.testing.assert_series_equal(
                out["signal_known_ts"].reset_index(drop=True), events["signal_known_ts"].reset_index(drop=True),
                check_names=False,
            )
            assert out["phase_preserved"].isna().all()
            assert out["snap_sessions"].isna().all()
            break
    assert found, "expected at least one seed in range(60) to produce a collision/inversion on this dense cluster"


def test_grain_cadence_null_no_calendar_state_is_typed():
    events = _events_for_symbol(symbol="NOCAL")
    out = grain_cadence_null(events, {}, seed=1)
    assert (out["cadence_null_state"] == "no_calendar").all()
    pd.testing.assert_series_equal(out["signal_known_ts"], events["signal_known_ts"])


def test_grain_cadence_null_summary_reports_gap_distortion_stats():
    bars = {"AAA": _trading_calendar_bars_with_holidays(start="2018-01-01", n=1200)}
    calendar = pd.DatetimeIndex(sorted(bars["AAA"].index))
    fridays = calendar[calendar.weekday == 4]
    fridays = fridays[calendar.searchsorted(fridays) < 200][:10]
    events = pd.DataFrame({
        "event_id": [f"E{i}" for i in range(len(fridays))],
        "family_key": ["fam.w"] * len(fridays), "symbol": ["AAA"] * len(fridays),
        "signal_ts": fridays, "signal_known_ts": fridays, "grain": ["W"] * len(fridays),
    })
    out = grain_cadence_null(events, bars, seed=13)
    summary = grain_cadence_null_summary(out)
    assert summary["n_rows"] == len(events)
    assert summary["n_rows_applied"] + summary["n_rows_unestimable"] + summary["n_rows_no_calendar"] == len(events)
    if summary["n_rows_applied"] > 0:
        assert summary["snap_sessions_abs_max"] is not None
        assert summary["snap_sessions_abs_max"] <= GRAIN_CADENCE_SNAP_BOUND_SESSIONS


def test_grain_cadence_null_preserves_stamp_lag_exactly():
    """M4-regression: each event's own stamp lag (signal_known_ts - signal_ts)
    must be preserved EXACTLY as a timedelta -- the prior implementation
    collapsed both columns to the SAME shifted value, destroying the lag."""
    bars = {"AAA": _trading_calendar_bars(start="2018-01-01", n=1200)}
    calendar = pd.DatetimeIndex(sorted(bars["AAA"].index))
    signal_ts = calendar[[200, 210, 220]]
    lags = [pd.Timedelta(days=0), pd.Timedelta(days=1), pd.Timedelta(hours=6)]
    known_ts = [s + l for s, l in zip(signal_ts, lags)]
    events = pd.DataFrame({
        "event_id": ["E0", "E1", "E2"], "family_key": ["fam.x"] * 3, "symbol": ["AAA"] * 3,
        "signal_ts": signal_ts, "signal_known_ts": known_ts, "grain": ["1D"] * 3,
    })
    out = grain_cadence_null(events, bars, seed=9)
    orig_lag = pd.to_datetime(events["signal_known_ts"]) - pd.to_datetime(events["signal_ts"])
    new_lag = pd.to_datetime(out["signal_known_ts"]) - pd.to_datetime(out["signal_ts"])
    pd.testing.assert_series_equal(
        orig_lag.reset_index(drop=True), new_lag.reset_index(drop=True), check_names=False,
    )


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
        "grain": ["daily", "daily", "daily", "daily"],
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
        "grain": ["daily", "daily"],
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
        "grain": ["daily", "daily", "daily", "daily"],
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
        "grain": ["daily", "daily", "daily"],
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
        "grain": ["daily", "daily"],
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


def test_equal_proximity_control_missing_grain_column_returns_empty():
    """M3-minor: `grain` is now a required column for the same reason
    `episode_id` is -- a caller that omits it never silently gets a
    grain-blind (and therefore over-inclusive) pairing."""
    metrics = pd.DataFrame({
        "event_id": ["E1", "E2"], "family_key": ["fam.a", "fam.b"],
        "episode_id": ["EP1", "EP1"], "atr_dist": [0.1, 0.12],
    })
    out, truncated = equal_proximity_control(metrics, tolerance_atr=0.5)
    assert out.empty
    assert truncated == 0


def test_equal_proximity_control_pair_rows_carry_the_scoping_grain():
    """NIT (delta-review third pass): each output pair row must carry the
    ``grain`` that scoped it (the shared (episode_id, grain) group key), so a
    reader of the pair output alone can see which cadence bucket produced it
    without rejoining ``metrics``."""
    metrics = pd.DataFrame({
        "event_id": ["E1", "E2", "E3", "E4"],
        "family_key": ["fam.a", "fam.b", "fam.a", "fam.b"],
        "episode_id": ["EP1", "EP1", "EP1", "EP1"],
        "grain": ["daily", "daily", "weekly", "weekly"],
        "atr_dist": [0.10, 0.12, 0.50, 0.55],
    })
    out, truncated = equal_proximity_control(metrics, tolerance_atr=0.5)
    assert "grain" in out.columns
    assert not out.empty
    for _, row in out.iterrows():
        # the pair's OWN grain column must equal the grain BOTH its fires
        # actually carried in the input metrics -- never blank/mismatched.
        left_grain = metrics.loc[metrics["event_id"] == row["left_event_id"], "grain"].iloc[0]
        right_grain = metrics.loc[metrics["event_id"] == row["right_event_id"], "grain"].iloc[0]
        assert row["grain"] == left_grain == right_grain
    assert set(out["grain"]) <= {"daily", "weekly"}


def test_equal_proximity_control_never_pairs_across_grains_m3_minor():
    """Discriminating test for M3-minor: two fires in the SAME episode with
    DIFFERENT grains, however close in atr_dist, must never be paired -- a
    daily-cadence fire and a weekly-cadence fire are measured over different
    windows, so they are not a genuine "similarly-placed" comparison. The prior
    (pre-M3-minor) implementation grouped by episode_id alone and would have
    paired these."""
    metrics = pd.DataFrame({
        "event_id": ["E1", "E2"],
        "family_key": ["fam.a", "fam.b"],
        "episode_id": ["EP1", "EP1"],
        "grain": ["daily", "weekly"],
        "atr_dist": [0.10, 0.12],
    })
    out, truncated = equal_proximity_control(metrics, tolerance_atr=0.5)
    assert out.empty
    assert truncated == 0
