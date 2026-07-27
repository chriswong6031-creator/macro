from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.research import pss_sr2_peer_diffusion as sr2


def test_greedy_anchor_cooldown_excludes_following_21_sessions() -> None:
    candidate = np.zeros(90, dtype=bool)
    candidate[[10, 11, 31, 32, 54]] = True

    anchors = sr2.greedy_anchors(candidate)

    assert anchors.tolist() == [10, 32, 54]


def test_ex_self_breadth_removes_subject_from_both_sums() -> None:
    index = pd.bdate_range("2024-01-02", periods=2)
    new_low = pd.DataFrame(
        {"A": [True, False], "B": [True, True], "C": [False, True]},
        index=index,
    )
    valid = pd.DataFrame(
        {"A": [True, True], "B": [True, True], "C": [True, True]},
        index=index,
    )

    breadth, count = sr2.ex_self_breadth(new_low, valid, "A")

    assert count.tolist() == [2.0, 2.0]
    assert breadth.tolist() == [0.5, 1.0]


def test_ex_self_breadth_is_prefix_invariant() -> None:
    rng = np.random.default_rng(4)
    index = pd.bdate_range("2020-01-02", periods=500)
    close = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0, 0.02, (500, 20)), axis=0)),
        index=index,
        columns=[f"S{i}" for i in range(20)],
    )

    def calculate(frame: pd.DataFrame) -> pd.Series:
        prior = frame.shift(1).rolling(60, min_periods=60).min()
        valid = frame.notna() & prior.notna()
        new_low = frame.le(prior) & valid
        return sr2.ex_self_breadth(new_low, valid, "S0")[0]

    full = calculate(close)
    prefix = calculate(close.iloc[:350])

    pd.testing.assert_series_equal(prefix, full.iloc[:350])


def _path_inputs(
    breadth_window: tuple[float, float, float] = (0.10, 0.15, 0.20),
) -> tuple[np.ndarray, ...]:
    n = 100
    close = np.full(n, 100.0)
    low = np.full(n, 99.0)
    breadth = np.full(n, 0.05)
    peer_count = np.full(n, 20.0)
    atr = np.full(n, 1.0)
    close[10:15] = 90.0
    low[10:14] = [90.5, 90.2, 90.0, 90.3]
    breadth[10:14] = [0.30, 0.40, 0.35, 0.25]
    close[15] = 91.2
    low[17] = 90.2
    close[17] = 90.8
    breadth[15:18] = breadth_window
    return close, low, breadth, peer_count, atr


def test_find_path_classifies_persistent_treatment() -> None:
    path, reason = sr2.find_path(*_path_inputs(), anchor=10)

    assert reason == "ok"
    assert path is not None
    assert path.confirm == 13
    assert path.rebound == 15
    assert path.action == 17
    assert path.reference_low == 90.0
    assert path.peer_peak == 0.40
    assert path.diffusion_ratio == 0.50
    assert path.treatment
    assert not path.transient


def test_find_path_separates_transient_from_persistent_contraction() -> None:
    path, reason = sr2.find_path(
        *_path_inputs((0.30, 0.30, 0.10)),
        anchor=10,
    )

    assert reason == "ok"
    assert path is not None
    assert not path.treatment
    assert path.transient
    assert path.peer_breadth_b == 0.10
    assert path.peer_breadth_3max == 0.30


def test_find_path_does_not_replace_first_geometry_when_breadth_invalid() -> None:
    close, low, breadth, peers, atr = _path_inputs()
    peers[16] = 10
    low[20] = 90.1
    close[20] = 90.7

    path, reason = sr2.find_path(
        close, low, breadth, peers, atr, anchor=10
    )

    assert path is None
    assert reason == "retest_peer_count"


def test_find_path_uses_prior_only_frozen_atr() -> None:
    inputs = list(_path_inputs())
    first, _ = sr2.find_path(*inputs, anchor=10)
    inputs[-1][11:] = 50.0
    second, _ = sr2.find_path(*inputs, anchor=10)

    assert first is not None and second is not None
    assert first.atr == second.atr == 1.0


def test_competing_risk_retains_unresolved_and_breach_wins_tie() -> None:
    close = np.full(70, 100.0)
    low = np.full(70, 99.0)
    close[1] = 109.0
    low[1] = 89.0

    tied = sr2.competing_risk(close, low, action=0, breach_level=90.0)
    unresolved = sr2.competing_risk(
        np.full(70, 100.0),
        np.full(70, 99.0),
        action=0,
        breach_level=90.0,
    )

    assert tied["breach_first"]
    assert not tied["rebound8_first"]
    assert tied["resolution_day"] == 1
    assert unresolved["unresolved"]
    assert not unresolved["breach_first"]
    assert not unresolved["rebound8_first"]


def _inference_events() -> pd.DataFrame:
    rows = []
    sectors = ["Energy", "Financials", "Industrials", "Materials"]
    for month_number in range(1, 11):
        month = f"2024-{month_number:02d}"
        for sector in sectors:
            for number in range(8):
                treatment = number < 4
                rows.append(
                    {
                        "sym": f"{sector[:2]}-{month_number}-{number}",
                        "sector": sector,
                        "anchor_date": pd.Timestamp(f"{month}-02"),
                        "date": pd.Timestamp(f"{month}-10"),
                        "month": month,
                        "severity_band": "p2",
                        "delay_band": "d1",
                        "group": "sr2" if treatment else "geometry_control",
                        "is_sr2": treatment,
                        "is_transient": False,
                        "mae": -2.0 if treatment else -10.0,
                        "tail10": not treatment,
                        "w5": treatment,
                        "called": treatment,
                        "rebound8_first": treatment,
                        "breach_first": not treatment,
                        "close_depth_atr": 0.5,
                    }
                )
    return pd.DataFrame(rows)


def test_inference_tape_keeps_first_name_month() -> None:
    events = _inference_events()
    duplicate = events.iloc[[0]].copy()
    duplicate["date"] = duplicate["date"] + pd.Timedelta(days=5)
    duplicate["mae"] = 99.0
    combined = pd.concat([events, duplicate], ignore_index=True)

    tape = sr2.inference_tape(combined)

    row = tape[
        (tape.sym == events.iloc[0].sym)
        & (tape.month == events.iloc[0].month)
    ]
    assert len(row) == 1
    assert row.iloc[0].mae == -2.0


def test_permutation_preserves_stratum_counts_and_detects_effect() -> None:
    events = _inference_events()

    observed, null, counts = sr2.permuted_effects(
        events, "mae", n_perm=500, seed=12
    )

    assert observed == 8.0
    assert counts == [(4, 4)] * 40
    assert len(null) == 500
    assert (1 + np.sum(null >= observed)) / 501 < 0.05


def test_binary_effects_are_rates_not_medians_of_binary_rows() -> None:
    effects = sr2.stratum_effects(_inference_events(), "w5")

    assert len(effects) == 40
    assert (effects.effect == 100.0).all()


def test_moving_block_ci_moves_whole_months_and_is_deterministic() -> None:
    effects = sr2.stratum_effects(_inference_events(), "mae")

    first = sr2.moving_block_ci(effects, n_boot=100, seed=8)
    second = sr2.moving_block_ci(effects, n_boot=100, seed=8)

    assert first == second
    assert first[0] == first[1] == 8.0


def test_fixed_bands_pin_boundary_behavior() -> None:
    assert sr2.severity_band(0.15) == "p1"
    assert sr2.severity_band(0.30) == "p2"
    assert sr2.severity_band(0.50) == "p3"
    assert sr2.delay_band(15) == "d1"
    assert sr2.delay_band(16) == "d2"
    assert sr2.delay_band(27) == "d2"
    assert sr2.delay_band(28) == "d3"


def test_containment_grades_share_not_opportunity_confounded_density() -> None:
    events = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2022-01-03"] * 30 + ["2022-09-01"] * 10
            ),
            "is_sr2": [True] * 15
            + [False] * 15
            + [True] * 8
            + [False] * 2,
        }
    )

    result = sr2.containment(events)

    assert result["h1_opportunity_density"] > result["autumn_opportunity_density"]
    assert result["h1_share"] == 0.5
    assert result["autumn_share"] == 0.8
