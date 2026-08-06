"""Unit tests for the W8 Ignition Layer stand-in detectors.

Every detector is exercised on SYNTHETIC series with a matched pair per sensor: one case
that MUST NOT fire (the leg under test is the only thing missing) and one that MUST. The
must-not-fire cases are the point — they pin each leg individually, so a leg that has
silently died shows up as a detector that fires when it should not, or as a fire count
that has gone to zero.

Charter: research/PROPHET_US_IGNITION_LAYER_W8_BY_FABLE.md
Instrument: research/prophet_us_audit/ignition_standins.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.prophet_us_audit import ignition_standins as ig


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------
def _vol_then_quiet(k: int = 0, breakout: bool = False, n_vol: int = 300,
                    n_rise: int = 60, n_quiet: int = 40, seed: int = 7):
    """A volatile era, then a DETERMINISTIC rise, then a tight range-bound coil, optionally
    ending in a release.

    Three eras, each load-bearing:
      * volatile — gives the quiet era's ATR something to sit in the bottom quartile OF;
      * rise     — deterministic, so `close > 50dMA` and `50dMA rising` hold for EVERY
                   synthetic name regardless of seed. Without it a random walk decides the
                   uptrend leg by coin flip and the laggard members land below their 50dMA,
                   which the detector then correctly refuses to call a coil;
      * quiet    — the coil itself.
    """
    rng = np.random.default_rng(seed + k)
    steps = rng.normal(0.0, 0.030, n_vol)
    px = list(100 * np.exp(np.cumsum(steps)))
    for _ in range(n_rise):                       # deterministic uptrend into the coil
        px.append(px[-1] * 1.004)
    base = px[-1]
    for i in range(n_quiet - 1):
        px.append(base * (1 + 0.0008 * np.sin(i / 2.0 + k)))
    px.append(base * 1.15 if breakout else base * (1 + 0.0008 * np.sin((n_quiet - 1) / 2.0 + k)))
    close = np.array(px)
    high, low = close * 1.001, close * 0.999
    cut = n_vol + n_rise                          # wide intrabar range everywhere but the coil
    high[:cut] = close[:cut] * 1.02
    low[:cut] = close[:cut] * 0.98
    return close, high, low


def _one_name(breakout: bool):
    c, h, l = _vol_then_quiet(breakout=breakout)
    idx = pd.bdate_range("2023-01-02", periods=len(c))
    f = lambda a: pd.DataFrame({"T": a}, index=idx)      # noqa: E731
    return f(c), f(h), f(l)


def _basket(n_break: int, n_total: int = 8):
    idx = None
    C, H, L = {}, {}, {}
    for k in range(n_total):
        c, h, l = _vol_then_quiet(k=k, breakout=k < n_break, seed=11)
        if idx is None:
            idx = pd.bdate_range("2023-01-02", periods=len(c))
        t = f"M{k}"
        C[t], H[t], L[t] = c, h, l
    f = lambda d: pd.DataFrame(d, index=idx)             # noqa: E731
    members = [{"ticker": f"M{k}", "added": None, "removed": None} for k in range(n_total)]
    return f(C), f(H), f(L), {"tb": {"members": members}}


def _rank_panel(jump: float, mover: str = "N0", n: int = 140, N: int = 20):
    """N names on fixed distinct drifts (so cross-sectional ranks are stable), with one
    mover ramped over 5 sessions. `jump` sets how far up the ranking the mover travels."""
    idx = pd.bdate_range("2023-01-02", periods=n)
    px = pd.DataFrame({f"N{i}": 100 * np.exp(np.arange(n) * 0.0004 * i) for i in range(N)},
                      index=idx)
    s = px[mover].to_numpy().copy()
    s[120:] *= np.concatenate([np.linspace(1, 1 + jump, 5), np.full(n - 125, 1 + jump)])
    px[mover] = s
    return px


def _insider_panel(rows):
    return pd.DataFrame(
        [{"ticker": t, "filing_date": pd.Timestamp(d), "rptownercik": p, "is_buy": b}
         for t, d, p, b in rows])


# ---------------------------------------------------------------------------
# S-COIL
# ---------------------------------------------------------------------------
def test_coil_compression_that_never_expands_does_not_fire():
    """The must-not-fire case: a genuine, long compression with no release bar.

    Both preceding legs are proven live by the diagnostics (compression days > 0 and the
    >=10-session run satisfied), so a zero event count here isolates the release leg — it
    is not a detector that simply never fires.
    """
    close, high, low = _one_name(breakout=False)
    r = ig.coil_events(close, high, low)
    assert r["diag"]["compressed_name_days"] > 0, "compression leg is dead, test is vacuous"
    assert r["diag"]["comp_run_name_days"] > 0, "the >=10-session run leg never satisfied"
    assert r["diag"]["events"] == 0
    assert not bool(r["events"].to_numpy().any())


def test_coil_release_bar_fires():
    close, high, low = _one_name(breakout=True)
    r = ig.coil_events(close, high, low)
    assert r["diag"]["events"] == 1
    fired = r["events"]["T"]
    assert bool(fired.iloc[-1]), "the release bar is the last bar and must be the event"


def test_coil_event_and_control_are_disjoint():
    """A name-day is either the compressed release or the gate-matched control, never both
    — otherwise the matched delta would compare a cohort with itself."""
    close, high, low = _one_name(breakout=True)
    r = ig.coil_events(close, high, low)
    overlap = (r["events"] & r["controls"]).to_numpy().sum()
    assert int(overlap) == 0
    assert r["diag"]["gate_matched_controls"] > 0, "control arm is empty, delta is undefined"


def test_coil_compression_is_read_before_the_release_bar():
    """PIT guard: the release bar's own range must not enter the ATR window that admits it.

    Verified structurally — the compressed state one bar BEFORE the event is what gates it.
    """
    close, high, low = _one_name(breakout=True)
    compressed = ig.coil_compression(close, high, low)
    run = compressed.rolling(ig.COMP_LOOKBACK).sum() >= ig.COMP_MIN
    r = ig.coil_events(close, high, low)
    pos = int(np.nonzero(r["events"]["T"].to_numpy())[0][0])
    assert bool(run["T"].iloc[pos - 1]), "event fired without the PRIOR bar being armed"


# ---------------------------------------------------------------------------
# S-RANKVEL
# ---------------------------------------------------------------------------
def test_rankvel_acceleration_into_level_fires():
    px = _rank_panel(jump=0.55, mover="N2")
    r = ig.rankvel_events(px)
    assert int(r["events"]["N2"].to_numpy().sum()) > 0
    assert r["diag"]["events"] > 0


def test_rankvel_acceleration_without_level_does_not_fire():
    """Must-not-fire: the acceleration leg PASSES (delta well above the +20pt bar) but the
    mover lands below p70, so the level leg alone suppresses the event."""
    px = _rank_panel(jump=0.20, mover="N0")
    r = ig.rankvel_events(px)
    pct, prev = r["pct"]["N0"].iloc[124], r["pct"]["N0"].iloc[119]
    assert (pct - prev) >= ig.VEL_MIN, "acceleration leg not exercised — test is vacuous"
    assert pct < ig.RS_LEVEL
    assert int(r["events"]["N0"].to_numpy().sum()) == 0


def test_rankvel_level_without_acceleration_does_not_fire():
    """The inverse guard: names sitting high in the ranking that never accelerated must not
    fire, or the sensor is just measuring the level it claims to differentiate from."""
    px = _rank_panel(jump=0.0)
    r = ig.rankvel_events(px)
    top = "N19"
    assert r["pct"][top].iloc[-1] >= ig.RS_LEVEL, "top name is not at level — test vacuous"
    assert int(r["events"][top].to_numpy().sum()) == 0


def test_rankvel_level_matched_pool_is_populated():
    px = _rank_panel(jump=0.55, mover="N2")
    r = ig.rankvel_events(px)
    assert r["diag"]["level_matched_pool"] > 0, "no level-matched controls — delta undefined"


# ---------------------------------------------------------------------------
# S-THRUST-LAG
# ---------------------------------------------------------------------------
def test_thrust_with_coiled_laggard_fires():
    close, high, low, baskets = _basket(n_break=5)
    r = ig.thrust_lag_events(close, high, low, baskets)
    assert r["diag"]["thrust_events"] == 1
    assert r["diag"]["candidates_coiled_laggard"] >= 1
    assert r["diag"]["control_already_moved"] >= 1


def test_thrust_without_laggards_yields_no_candidates():
    """Must-not-fire: the theme thrusts, but every member has already moved above its own
    20d high, so there is no coiled laggard left to be a candidate."""
    close, high, low, baskets = _basket(n_break=8)
    r = ig.thrust_lag_events(close, high, low, baskets)
    assert r["diag"]["thrust_events"] == 1, "thrust leg is dead — test is vacuous"
    assert r["diag"]["candidates_coiled_laggard"] == 0


def test_thrust_requires_minimum_members():
    """A basket thinner than MIN_MEMBERS is unreadable and must be skipped, not scored on
    two names."""
    close, high, low, _ = _basket(n_break=5)
    thin = {"tb": {"members": [{"ticker": "M0", "added": None, "removed": None},
                               {"ticker": "M1", "added": None, "removed": None}]}}
    r = ig.thrust_lag_events(close, high, low, thin)
    assert r["diag"]["baskets_read"] == 0


def test_thrust_honors_pit_removal():
    """A member removed before the thrust must not count toward the member fraction."""
    close, high, low, baskets = _basket(n_break=5)
    day = str(close.index[-1].date())
    for mem in baskets["tb"]["members"]:
        if mem["ticker"] in {"M0", "M1"}:
            mem["removed"] = "2023-06-01"
    r = ig.thrust_lag_events(close, high, low, baskets)
    active = ig.active_members(baskets["tb"], close.index[-1], set(close.columns))
    assert "M0" not in active and "M1" not in active
    assert day  # membership resolution is date-driven, asserted above
    assert r["diag"]["baskets_read"] == 1


# ---------------------------------------------------------------------------
# S-INSIDER
# ---------------------------------------------------------------------------
def test_insider_two_distinct_buyers_cluster():
    panel = _insider_panel([
        ("AAA", "2024-01-05", "cik-1", True),
        ("AAA", "2024-02-10", "cik-2", True),
    ])
    ev = ig.insider_cluster_events(panel, "is_buy", "filing_date", "rptownercik", "ticker")
    assert len(ev) == 1
    assert ev.iloc[0]["ticker"] == "AAA"
    assert ev.iloc[0]["date"] == pd.Timestamp("2024-02-10"), \
        "the event must be stamped on the SECOND buyer's filing date"
    assert int(ev.iloc[0]["n_buyers"]) == 2


def test_insider_single_buyer_repeated_is_not_a_cluster():
    """Must-not-fire: one insider buying four times is not two distinct buyers. This is the
    exact leg that a naive transaction-count reader (context_api._insider_dim does not
    dedupe by insider) would get wrong."""
    panel = _insider_panel([("AAA", d, "cik-1", True) for d in
                            ("2024-01-05", "2024-01-15", "2024-02-01", "2024-02-20")])
    ev = ig.insider_cluster_events(panel, "is_buy", "filing_date", "rptownercik", "ticker")
    assert len(ev) == 0


def test_insider_buyers_outside_the_window_do_not_cluster():
    panel = _insider_panel([
        ("AAA", "2024-01-05", "cik-1", True),
        ("AAA", "2024-06-20", "cik-2", True),      # ~167 days later, outside 60d
    ])
    ev = ig.insider_cluster_events(panel, "is_buy", "filing_date", "rptownercik", "ticker")
    assert len(ev) == 0


def test_insider_sells_are_not_buys():
    panel = _insider_panel([
        ("AAA", "2024-01-05", "cik-1", False),
        ("AAA", "2024-01-20", "cik-2", False),
    ])
    ev = ig.insider_cluster_events(panel, "is_buy", "filing_date", "rptownercik", "ticker")
    assert len(ev) == 0


def test_insider_cluster_does_not_double_count_one_episode():
    """A third buyer inside the same window must not mint a second event."""
    panel = _insider_panel([
        ("AAA", "2024-01-05", "cik-1", True),
        ("AAA", "2024-01-20", "cik-2", True),
        ("AAA", "2024-02-01", "cik-3", True),
    ])
    ev = ig.insider_cluster_events(panel, "is_buy", "filing_date", "rptownercik", "ticker")
    assert len(ev) == 1
    assert ev.iloc[0]["date"] == pd.Timestamp("2024-01-20")


# ---------------------------------------------------------------------------
# intersection — regression test for the lookahead defect found in the first run
# ---------------------------------------------------------------------------
def _grid(n=40):
    idx = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame({"T": np.arange(n, dtype=float)}, index=idx)


def test_intersection_is_stamped_when_the_second_sensor_fires():
    close = _grid()
    a = pd.DataFrame({"date": [close.index[10]], "ticker": ["T"]})
    b = pd.DataFrame({"date": [close.index[13]], "ticker": ["T"]})
    out = ig.intersection_cohort({"A": a, "B": b}, close, window=5)
    assert len(out) == 1
    assert out.iloc[0]["date"] == close.index[13], \
        "intersection must be stamped on the day the SECOND sensor fires"


def test_intersection_window_is_backward_only():
    """The defect this pins: a symmetric +/- window stamped the cohort BEFORE the second
    sensor fired, selecting names with future information. No intersection row may ever
    predate the later of its two sensor fires."""
    close = _grid()
    a = pd.DataFrame({"date": [close.index[10]], "ticker": ["T"]})
    b = pd.DataFrame({"date": [close.index[13]], "ticker": ["T"]})
    out = ig.intersection_cohort({"A": a, "B": b}, close, window=5)
    assert (out["date"] >= close.index[13]).all()


def test_intersection_requires_two_distinct_sensors():
    close = _grid()
    a = pd.DataFrame({"date": [close.index[10], close.index[12]], "ticker": ["T", "T"]})
    out = ig.intersection_cohort({"A": a}, close, window=5)
    assert len(out) == 0


def test_intersection_respects_the_window():
    """Fires further apart than the window never become an intersection."""
    close = _grid()
    a = pd.DataFrame({"date": [close.index[5]], "ticker": ["T"]})
    b = pd.DataFrame({"date": [close.index[30]], "ticker": ["T"]})
    out = ig.intersection_cohort({"A": a, "B": b}, close, window=5)
    assert len(out) == 0


# ---------------------------------------------------------------------------
# constants pinned to the charter
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,expected", [
    ("PCT_MAX", 0.25), ("COMP_MIN", 10), ("BREAK_WIN", 21),
    ("VEL_MIN", 0.20), ("RS_LEVEL", 0.70),
    ("THRUST_LO", 0.30), ("THRUST_HI", 0.50), ("THRUST_WIN", 5),
    ("CLUSTER_N", 2), ("CLUSTER_WIN", 60),
])
def test_constants_match_the_charter(name, expected):
    assert getattr(ig, name) == expected
