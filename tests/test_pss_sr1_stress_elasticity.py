from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.research import pss_sr1_stress_elasticity as sr1


def test_fresh_low_anchor_cooldown_is_greedy_and_inclusive() -> None:
    close = np.arange(100, 200, dtype=float)
    close[60] = 90.0
    close[61] = 89.0
    close[81] = 88.5
    close[82] = 88.0

    anchors = sr1.fresh_low_anchors(close)

    assert anchors.tolist() == [60, 82]


def test_completed_pulse_is_stamped_on_first_nonshock_close() -> None:
    shock = np.array(
        [False, True, True, False, False, True, False, True, True, True],
        dtype=bool,
    )

    pulses = sr1.completed_pulses(shock)

    assert pulses == [sr1.Pulse(1, 2, 3), sr1.Pulse(5, 5, 6)]
    # The terminal run is not observable as complete without a following close.
    assert all(pulse.end != 9 for pulse in pulses)


def test_sector_shock_flags_are_prefix_invariant() -> None:
    rng = np.random.default_rng(9)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, 600)))
    full = sr1.sector_shocks(close)

    for cut in (300, 450):
        prefix = sr1.sector_shocks(close[:cut])
        np.testing.assert_array_equal(prefix, full[:cut])


def test_anchor_stats_use_only_sessions_before_anchor() -> None:
    rng = np.random.default_rng(71)
    n = 360
    sector_ret = rng.normal(-0.0002, 0.012, n)
    stock_ret = 1.2 * sector_ret + rng.normal(0, 0.004, n)
    sector = 100 * np.exp(np.cumsum(sector_ret))
    close = 80 * np.exp(np.cumsum(stock_ret))
    index = pd.bdate_range("2020-01-02", periods=n)
    ohlcv = pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
        },
        index=index,
    )
    anchor = 220

    before = sr1.anchor_stats(ohlcv, sector, anchor)
    altered = ohlcv.copy()
    altered.iloc[anchor:, altered.columns.get_loc("close")] *= 50
    sector_altered = sector.copy()
    sector_altered[anchor:] *= 0.02
    after = sr1.anchor_stats(altered, sector_altered, anchor)

    assert before is not None and after is not None
    assert before == after


def _sequence_inputs(b_stock_return: float, b_low: float = 90.2):
    n = 30
    close = np.full(n, 100.0)
    close[10] = 98.0
    close[11] = 90.5
    close[12:18] = 92.0
    low = np.full(n, 99.0)
    low[10] = 90.0
    low[18] = b_low
    stock_ret = np.zeros(n)
    stock_ret[10] = -0.02
    stock_ret[18] = b_stock_return
    sector_ret = np.zeros(n)
    sector_ret[[10, 18]] = -0.01
    pulses = [sr1.Pulse(10, 10, 11), sr1.Pulse(18, 18, 19)]
    stats = sr1.AnchorStats(
        beta=1.0,
        r2=0.6,
        sector_sigma=0.01,
        atr=1.0,
        sector20=-0.1,
    )
    return pulses, close, low, stock_ret, sector_ret, stats


def test_sequence_separates_treatment_from_geometry_control() -> None:
    treatment, reason = sr1.find_sequence(
        9, *_sequence_inputs(b_stock_return=-0.004)
    )
    control, control_reason = sr1.find_sequence(
        9, *_sequence_inputs(b_stock_return=-0.012)
    )
    broken, broken_reason = sr1.find_sequence(
        9, *_sequence_inputs(b_stock_return=-0.004, b_low=89.0)
    )

    assert reason == control_reason == broken_reason == "ok"
    assert treatment is not None and treatment["group"] == "sr1"
    assert treatment["treatment"]
    assert control is not None and control["group"] == "geometry_control"
    assert not control["treatment"]
    assert broken is not None and broken["group"] == "geometry_break"
    assert not broken["geometry"]


def test_competing_risk_retains_unresolved_and_breach_wins_tie() -> None:
    close = np.full(70, 100.0)
    low = np.full(70, 99.0)
    close[1] = 109.0
    low[1] = 89.0

    tied = sr1.competing_risk(close, low, action=0, breach_level=90.0)
    unresolved = sr1.competing_risk(
        np.full(70, 100.0),
        np.full(70, 99.0),
        action=0,
        breach_level=90.0,
    )

    assert tied == {
        "rebound8_first": False,
        "breach_first": True,
        "unresolved": False,
        "resolution_day": 1,
    }
    assert unresolved["unresolved"]
    assert not unresolved["rebound8_first"]
    assert not unresolved["breach_first"]


def _inference_events() -> pd.DataFrame:
    rows = []
    for pulse in range(40):
        for number in range(6):
            treatment = number < 3
            rows.append(
                {
                    "pulse_id": f"XLK:2024-01-{pulse + 1:02d}",
                    "b_start": pd.Timestamp("2024-01-01")
                    + pd.Timedelta(days=pulse),
                    "group": "sr1" if treatment else "geometry_control",
                    "mae": -2.0 if treatment else -10.0,
                    "tail10": not treatment,
                    "w5": treatment,
                    "called": treatment,
                    "rebound8_first": treatment,
                }
            )
    return pd.DataFrame(rows)


def test_within_pulse_permutation_preserves_counts_and_detects_effect() -> None:
    events = _inference_events()

    observed, null, counts = sr1.permuted_effects(
        events, "mae", n_perm=400, seed=33
    )

    assert observed == 8.0
    assert counts == [(3, 3)] * 40
    assert len(null) == 400
    assert (1 + np.sum(null >= observed)) / 401 < 0.05


def test_pulse_effects_are_equal_weighted_not_event_weighted() -> None:
    rows = [
        {
            "pulse_id": "A",
            "b_start": pd.Timestamp("2024-01-02"),
            "group": "sr1",
            "mae": 10.0,
        },
        {
            "pulse_id": "A",
            "b_start": pd.Timestamp("2024-01-02"),
            "group": "geometry_control",
            "mae": 0.0,
        },
        {
            "pulse_id": "B",
            "b_start": pd.Timestamp("2024-02-02"),
            "group": "geometry_control",
            "mae": 0.0,
        },
    ]
    rows.extend(
        {
            "pulse_id": "B",
            "b_start": pd.Timestamp("2024-02-02"),
            "group": "sr1",
            "mae": 0.0,
        }
        for _ in range(100)
    )
    effects = sr1.pulse_effects(pd.DataFrame(rows), "mae")

    assert effects.effect.mean() == 5.0


def test_past_alignment_never_backfills() -> None:
    source = pd.Series(
        [101.0, 102.0],
        index=pd.to_datetime(["2024-01-03", "2024-01-05"]),
    )
    target = pd.to_datetime(["2024-01-02", "2024-01-04", "2024-01-05"])

    aligned = sr1.align_past(source, target)

    assert np.isnan(aligned[0])
    assert aligned[1:].tolist() == [101.0, 102.0]
