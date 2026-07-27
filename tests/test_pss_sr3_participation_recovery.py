from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.research import pss_sr3_participation_feasibility as feasibility
from scripts.research import pss_sr3_participation_recovery as sr3


def test_greedy_anchor_cooldown_excludes_following_21_sessions() -> None:
    candidate = np.zeros(90, dtype=bool)
    candidate[[10, 11, 31, 32, 54]] = True

    anchors = feasibility.greedy_anchors(candidate)

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

    breadth, count = feasibility.ex_self_breadth(new_low, valid, "A")

    assert count.tolist() == [2.0, 2.0]
    assert breadth.tolist() == [0.5, 1.0]


def test_first_subject_recovery_stamps_first_complete_held_window() -> None:
    close = np.full(60, 90.0)
    low = np.full(60, 89.8)
    close[14:17] = [90.6, 90.7, 91.2]
    low[14:17] = [90.1, 90.2, 90.4]
    close[17] = 91.4
    low[17] = 90.6

    action = feasibility.first_subject_recovery(
        close,
        low,
        anchor=10,
        atr_anchor=1.0,
        reference_low=90.0,
    )

    assert action == 16


def test_subject_recovery_skips_failed_window_and_uses_first_valid_window() -> None:
    close = np.full(60, 90.0)
    low = np.full(60, 89.8)
    close[14:17] = [90.6, 90.7, 91.2]
    low[14:17] = [90.1, 89.4, 90.4]
    close[20:23] = [90.6, 90.8, 91.1]
    low[20:23] = [90.1, 90.2, 90.3]

    action = feasibility.first_subject_recovery(
        close,
        low,
        anchor=10,
        atr_anchor=1.0,
        reference_low=90.0,
    )

    assert action == 22


def _peer_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    index = pd.bdate_range("2024-01-02", periods=30)
    columns = ["SUBJECT", *[f"P{i:02d}" for i in range(20)]]
    close = pd.DataFrame(100.0, index=index, columns=columns)
    low = pd.DataFrame(99.0, index=index, columns=columns)
    atr = pd.DataFrame(1.0, index=index, columns=columns)
    close.loc[index[10:13], columns] = 101.0
    return close, low, atr


def test_peer_recovery_requires_level_and_positive_five_day_trend() -> None:
    close, low, atr = _peer_frames()

    minima, reason = feasibility.peer_recovery_minima(
        close,
        low,
        atr,
        sym="SUBJECT",
        anchor=5,
        action=12,
    )

    assert reason == "ok"
    assert minima is not None
    assert minima["level_0.50"] == 1.0
    assert minima["joint_5"] == 1.0


def test_peer_recovery_excludes_subject_from_label() -> None:
    close, low, atr = _peer_frames()
    close.loc[close.index[10:13], "SUBJECT"] = 50.0

    minima, reason = feasibility.peer_recovery_minima(
        close,
        low,
        atr,
        sym="SUBJECT",
        anchor=5,
        action=12,
    )

    assert reason == "ok"
    assert minima is not None
    assert minima["joint_5"] == 1.0


def test_final_nested_control_holds_passive_level_recovery_constant() -> None:
    rows = []
    for active, level, number in (
        (0.70, 0.80, 0),
        (0.60, 0.75, 1),
        (0.30, 0.80, 2),
        (0.20, 0.70, 3),
        (0.20, 0.30, 4),
    ):
        rows.append(
            {
                "sym": f"S{number}",
                "sector": "Energy",
                "anchor_date": pd.Timestamp("2024-01-02"),
                "date": pd.Timestamp("2024-01-15"),
                "month": "2024-01",
                "era": "VAL",
                "severity_band": "p2",
                "delay_band": "d1",
                "close_depth_atr": 1.2,
                "peer_recovery_min_level_0.50": level,
                "peer_recovery_min_joint_5": active,
            }
        )
    paths = pd.DataFrame(rows)

    result = feasibility.summarize_final_nested(paths)

    assert result["paths"] == 4
    assert result["treatments"] == 2
    assert result["controls"] == 2
    assert result["weak_excluded"] == 1


def test_frozen_group_boundaries_are_disjoint() -> None:
    assert sr3.classify_path(level_min=0.49, active_min=0.99) == "weak_level"
    assert sr3.classify_path(level_min=0.50, active_min=0.49) == "level_control"
    assert sr3.classify_path(level_min=0.50, active_min=0.50) == "sr3"


def test_event_outcomes_start_after_action_and_breach_wins_same_day() -> None:
    index = pd.bdate_range("2024-01-02", periods=110)
    ohlcv = pd.DataFrame(
        {
            "open": np.full(len(index), 100.0),
            "high": np.full(len(index), 101.0),
            "low": np.full(len(index), 99.0),
            "close": np.full(len(index), 100.0),
        },
        index=index,
    )
    action = 40
    ohlcv.loc[index[action + 1], ["close", "low"]] = [108.0, 89.0]
    metrics = {
        "mae63": np.full(len(index), np.nan),
        "prox": np.full(len(index), np.nan),
        "tdt": np.full(len(index), np.nan),
    }
    metrics["mae63"][action] = -11.0
    metrics["prox"][action] = 2.0
    metrics["tdt"][action] = 1.0
    path = pd.Series(
        {
            "sym": "TEST",
            "sector": "Energy",
            "anchor_date": index[30],
            "formation_confirm": index[33],
            "date": index[action],
            "month": "2024-02",
            "era": "VAL",
            "atr_anchor": 1.0,
            "reference_low": 90.0,
            "anchor_breadth": 0.2,
            "peer_peak": 0.3,
            "peer_recovery_min_level_0.50": 0.8,
            "peer_recovery_min_joint_5": 0.7,
            "delay": 7,
            "close_depth_atr": 1.4,
            "severity_band": "p1",
            "delay_band": "d1",
        }
    )

    event = sr3.event_row(path, ohlcv, metrics)

    assert event is not None
    assert event["mae"] == -11.0
    assert event["prox"] == 2.0
    assert event["breach_first"]
    assert not event["rebound8_first"]
    assert event["resolution_day"] == 1


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
                        "era": "VAL",
                        "severity_band": "p2",
                        "delay_band": "d1",
                        "group": "sr3" if treatment else "level_control",
                        "is_sr3": treatment,
                        "mae": -2.0 if treatment else -10.0,
                        "tail10": not treatment,
                        "w5": treatment,
                        "called": treatment,
                        "rebound8_first": treatment,
                        "breach_first": not treatment,
                        "close_depth_atr": 1.25,
                    }
                )
    weak = rows[0].copy()
    weak.update(
        {
            "sym": "WEAK",
            "group": "weak_level",
            "is_sr3": False,
            "mae": 999.0,
        }
    )
    rows.append(weak)
    return pd.DataFrame(rows)


def test_inference_tape_keeps_first_name_month_and_excludes_weak_level() -> None:
    events = _inference_events()
    duplicate = events.iloc[[0]].copy()
    duplicate["date"] = duplicate["date"] + pd.Timedelta(days=5)
    duplicate["mae"] = 99.0
    combined = pd.concat([events, duplicate], ignore_index=True)

    tape = sr3.inference_tape(combined)

    row = tape[
        (tape.sym == events.iloc[0].sym)
        & (tape.month == events.iloc[0].month)
    ]
    assert len(row) == 1
    assert row.iloc[0].mae == -2.0
    assert "WEAK" not in set(tape["sym"])


def test_sparse_inference_slice_returns_empty_effects_without_crashing() -> None:
    sparse = _inference_events().iloc[[0]].copy()

    tape = sr3.inference_tape(sparse)
    effects = sr3.stratum_effects(sparse, "mae")

    assert tape.empty
    assert "stratum" in tape
    assert effects.empty


def test_permutation_preserves_stratum_counts_and_detects_effect() -> None:
    observed, null, counts = sr3.permuted_effects(
        _inference_events(),
        "mae",
        n_perm=500,
        seed=12,
    )

    assert observed == 8.0
    assert counts == [(4, 4)] * 40
    assert len(null) == 500
    assert (1 + np.sum(null >= observed)) / 501 < 0.05


def test_binary_effects_are_rates_not_medians() -> None:
    effects = sr3.stratum_effects(_inference_events(), "w5")

    assert len(effects) == 40
    assert (effects["effect"] == 100.0).all()


def test_moving_block_ci_is_deterministic() -> None:
    effects = sr3.stratum_effects(_inference_events(), "mae")

    first = sr3.moving_block_ci(effects, n_boot=100, seed=8)
    second = sr3.moving_block_ci(effects, n_boot=100, seed=8)

    assert first == second
    assert first[0] == first[1] == 8.0


def test_shipped_event_tape_respects_frozen_labels_and_is_complete() -> None:
    events = pd.read_parquet(sr3.OUT_EVENTS)

    expected = np.where(
        events["level_min"].to_numpy() < sr3.LEVEL_FLOOR,
        "weak_level",
        np.where(
            events["active_min"].to_numpy() >= sr3.ACTIVE_FLOOR,
            "sr3",
            "level_control",
        ),
    )

    assert len(events) == 6_294
    assert events["group"].value_counts().to_dict() == {
        "level_control": 2_916,
        "sr3": 2_065,
        "weak_level": 1_313,
    }
    assert np.array_equal(events["group"].to_numpy(), expected)
    assert (events["anchor_date"] <= events["formation_confirm"]).all()
    assert (events["formation_confirm"] < events["date"]).all()
    assert events[["mae", "prox", "tdt"]].notna().all().all()
