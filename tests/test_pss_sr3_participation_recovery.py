from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.research import pss_sr3_participation_feasibility as sr3


def test_greedy_anchor_cooldown_excludes_following_21_sessions() -> None:
    candidate = np.zeros(90, dtype=bool)
    candidate[[10, 11, 31, 32, 54]] = True

    anchors = sr3.greedy_anchors(candidate)

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

    breadth, count = sr3.ex_self_breadth(new_low, valid, "A")

    assert count.tolist() == [2.0, 2.0]
    assert breadth.tolist() == [0.5, 1.0]


def test_first_subject_recovery_stamps_first_complete_held_window() -> None:
    close = np.full(60, 90.0)
    low = np.full(60, 89.8)
    close[14:17] = [90.6, 90.7, 91.2]
    low[14:17] = [90.1, 90.2, 90.4]
    close[17] = 91.4
    low[17] = 90.6

    action = sr3.first_subject_recovery(
        close,
        low,
        anchor=10,
        atr_anchor=1.0,
        reference_low=90.0,
    )

    assert action == 16


def test_subject_recovery_refuses_breach_and_does_not_use_later_path() -> None:
    close = np.full(60, 90.0)
    low = np.full(60, 89.8)
    close[14:17] = [90.6, 90.7, 91.2]
    low[14:17] = [90.1, 89.4, 90.4]
    close[20:23] = [90.6, 90.8, 91.1]
    low[20:23] = [90.1, 90.2, 90.3]

    action = sr3.first_subject_recovery(
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

    minima, reason = sr3.peer_recovery_minima(
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

    minima, reason = sr3.peer_recovery_minima(
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

    result = sr3.summarize_final_nested(paths)

    assert result["paths"] == 4
    assert result["treatments"] == 2
    assert result["controls"] == 2
    assert result["weak_excluded"] == 1
