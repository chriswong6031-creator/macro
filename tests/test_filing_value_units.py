from datetime import date

import pandas as pd

from lib.filing_value_units import (
    infer_13f_value_multiplier,
    normalize_13f_snapshot,
)


def _frame(values, shares, *, period="2026-06-30"):
    return pd.DataFrame({
        "value_raw": values,
        "shares": shares,
        "sh_type": ["SH"] * len(values),
        "period_end": [period] * len(values),
    })


def test_pre_2023_values_are_thousands():
    frame = _frame([100, 200, 300], [10, 20, 30], period="2022-09-30")
    multiplier, reason = infer_13f_value_multiplier(frame, date(2022, 9, 30))
    assert multiplier == 1000.0
    assert reason == "sec-pre-2023-thousands"


def test_post_2023_dollar_filing_stays_dollars():
    frame = _frame(
        [1_163_018_908, 851_686_063, 683_897_616],
        [3_291_594, 3_573_408, 3_417_950],
    )
    multiplier, reason = infer_13f_value_multiplier(frame, "2026-06-30")
    assert multiplier == 1.0
    assert reason == "sec-nearest-dollar"


def test_post_2023_legacy_thousands_export_is_detected():
    # Real-shaped Aquamarine lines: the official XML reports 21,986 for a
    # position worth roughly $21.986m and 48,838 for one worth $48.838m.
    frame = _frame(
        [21_986, 48_838, 22_466, 19_993, 11_991, 11_865, 6_952],
        [65_000, 97_600, 30, 40_000, 27_000, 30_000, 11_500],
    )
    multiplier, reason = infer_13f_value_multiplier(frame, "2026-06-30")
    assert multiplier == 1000.0
    assert reason == "post-2023-legacy-thousands-compatibility"


def test_distressed_dollar_book_is_not_misclassified():
    # A genuine dollar-valued, debt/warrant-heavy portfolio can have low
    # per-share values; its reported book is already above the filing threshold.
    frame = _frame(
        [121_338_540, 72_128_938, 47_711_612, 3_725_292],
        [218_628_000, 151_915_000, 32_456_879, 4_853_800],
    )
    multiplier, _ = infer_13f_value_multiplier(frame, "2024-03-31")
    assert multiplier == 1.0


def test_legacy_snapshot_bridge_normalizes_once():
    frame = _frame(
        [21_986, 48_838, 22_466, 19_993],
        [65_000, 97_600, 30, 40_000],
    ).rename(columns={"value_raw": "value_usd"})
    normalized = normalize_13f_snapshot(frame)
    assert normalized["value_usd"].sum() == frame["value_usd"].sum() * 1000
    assert set(normalized["value_multiplier"]) == {1000.0}
    assert normalize_13f_snapshot(normalized).equals(normalized)
