"""Tests for engine/btc_overrides.py — the Override-Registry apply layer.

Run: python -m pytest tests/test_btc_overrides.py -q
     or  python tests/test_btc_overrides.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import btc_overrides as OV  # noqa: E402
from engine import btc_signals as S  # noqa: E402
from lib import config  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _pure_alloc(idx: pd.DatetimeIndex) -> pd.DataFrame:
    """Pure allocation frame on a fully-invested synthetic setup (strong momentum,
    zero risk, no gate).  Conviction and brake disabled so every bar is 1.0."""
    mom = pd.Series(1.0, index=idx)
    risk = pd.Series(0.0, index=idx)
    base_cfg = {**config.load()["vector"]["allocation"],
                "conviction_sizing": False, "drawdown_brake": False,
                "bottom_overlay": False, "midterm_gate": {"enabled": False}}
    return S.allocation(mom, risk, base_cfg)


def _acfg(enabled: bool, buy_lead_days: int = 0) -> dict:
    """Build a minimal allocation-section config with midterm_gate."""
    base = {**config.load()["vector"]["allocation"],
            "conviction_sizing": False, "drawdown_brake": False,
            "bottom_overlay": False}
    base["midterm_gate"] = {"enabled": enabled, "buy_lead_days": buy_lead_days}
    return base


# --------------------------------------------------------------------------- #
# 1. Parity — outside blackout windows final == raw
# --------------------------------------------------------------------------- #
def test_parity_outside_blackout_windows() -> None:
    """Every bar OUTSIDE the midterm window must have final == raw."""
    # span a non-midterm year (2021 is odd — never gated) plus post-vote 2022 tail
    idx = pd.date_range("2021-01-01", "2022-12-31", freq="D")
    pure = _pure_alloc(idx)
    result = OV.apply(pure, _acfg(enabled=True))

    alloc_cols = [c for c in result.columns if c.startswith("alloc_")
                  and not c.endswith("_raw")]
    # 2021 is never gated; 2022 post-vote (from Nov 8) is also not gated
    non_gated = result.loc[
        (result.index.year == 2021) |
        ((result.index.year == 2022) & (result.index >= pd.Timestamp("2022-11-08")))
    ]
    for col in alloc_cols:
        pd.testing.assert_series_equal(
            non_gated[col].reset_index(drop=True),
            non_gated[f"{col}_raw"].reset_index(drop=True),
            check_names=False,
            obj=f"{col} vs {col}_raw outside window",
        )
    assert not non_gated["override_active"].any(), \
        "override_active must be False outside the blackout window"


# --------------------------------------------------------------------------- #
# 2. Inside windows: final == 0, raw follows the engine
# --------------------------------------------------------------------------- #
def test_inside_window_final_zero_raw_nonzero() -> None:
    """Inside the 2022 midterm window: final alloc_* == 0, *_raw > 0."""
    idx = pd.date_range("2022-01-01", "2023-01-31", freq="D")
    pure = _pure_alloc(idx)
    result = OV.apply(pure, _acfg(enabled=True))

    blackout = result.loc["2022-01-01":"2022-11-07"]
    alloc_cols = [c for c in result.columns if c.startswith("alloc_")
                  and not c.endswith("_raw")]
    for col in alloc_cols:
        assert blackout[col].eq(0.0).all(), \
            f"{col} must be 0.0 inside the 2022 blackout"
        assert (blackout[f"{col}_raw"] > 0).all(), \
            f"{col}_raw must be > 0 inside the 2022 blackout (pure engine)"

    assert blackout["override_active"].all(), \
        "override_active must be True inside the 2022 blackout"
    assert (blackout["override_id"] == "midterm_blackout").all(), \
        "override_id must be 'midterm_blackout' inside the 2022 blackout"

    # post-vote: gate released, final == raw again
    post_vote = result.loc["2022-11-08":]
    for col in alloc_cols:
        pd.testing.assert_series_equal(
            post_vote[col].reset_index(drop=True),
            post_vote[f"{col}_raw"].reset_index(drop=True),
            check_names=False,
            obj=f"{col} post-vote parity",
        )


# --------------------------------------------------------------------------- #
# 3. Disabled config -> final == raw everywhere, override_active all False
# --------------------------------------------------------------------------- #
def test_disabled_config_no_override() -> None:
    """With midterm_gate.enabled=False the override must be a no-op."""
    idx = pd.date_range("2022-01-01", "2022-12-31", freq="D")
    pure = _pure_alloc(idx)
    result = OV.apply(pure, _acfg(enabled=False))

    alloc_cols = [c for c in result.columns if c.startswith("alloc_")
                  and not c.endswith("_raw")]
    for col in alloc_cols:
        pd.testing.assert_series_equal(
            result[col].reset_index(drop=True),
            result[f"{col}_raw"].reset_index(drop=True),
            check_names=False,
            obj=f"{col} disabled gate: final must equal raw",
        )
    assert not result["override_active"].any(), \
        "override_active must be all False when gate is disabled"
    assert (result["override_id"] == "").all(), \
        "override_id must be '' when gate is disabled"


def test_missing_config_no_override() -> None:
    """With no midterm_gate key the override must be a no-op."""
    idx = pd.date_range("2022-01-01", "2022-12-31", freq="D")
    pure = _pure_alloc(idx)
    cfg_no_gate = {**config.load()["vector"]["allocation"],
                   "conviction_sizing": False, "drawdown_brake": False,
                   "bottom_overlay": False}
    cfg_no_gate.pop("midterm_gate", None)
    result = OV.apply(pure, cfg_no_gate)

    assert not result["override_active"].any()
    assert (result["override_id"] == "").all()


# --------------------------------------------------------------------------- #
# 4. Column presence and dtype stability
# --------------------------------------------------------------------------- #
def test_columns_and_dtypes() -> None:
    """Output must carry _raw twins plus override_active (bool) and override_id (str)."""
    idx = pd.date_range("2022-06-01", "2022-06-30", freq="D")
    pure = _pure_alloc(idx)
    result = OV.apply(pure, _acfg(enabled=True))

    alloc_cols = [c for c in pure.columns if c.startswith("alloc_")]
    for col in alloc_cols:
        assert col in result.columns, f"final column {col} missing"
        assert f"{col}_raw" in result.columns, f"raw column {col}_raw missing"

    assert "override_active" in result.columns
    assert "override_id" in result.columns

    # dtype checks — override_active is int8 (not Python bool) so it round-trips
    # through parquet without dtype drift and supports arithmetic in numeric checks.
    assert result["override_active"].dtype == np.dtype("int8"), \
           "override_active must be int8 dtype"
    assert result["override_id"].dtype == object or \
           pd.api.types.is_string_dtype(result["override_id"]), \
           "override_id must be string dtype"


def test_output_index_identical_to_input() -> None:
    """The output frame must have the same DatetimeIndex as the input."""
    idx = pd.date_range("2026-01-01", "2026-12-31", freq="D")
    pure = _pure_alloc(idx)
    result = OV.apply(pure, _acfg(enabled=True))
    pd.testing.assert_index_equal(result.index, pure.index)


def test_buy_lead_days_releases_gate_early() -> None:
    """buy_lead_days=14 must release the gate 14 days before election day."""
    idx = pd.date_range("2022-10-01", "2022-12-31", freq="D")
    pure = _pure_alloc(idx)
    result_0 = OV.apply(pure, _acfg(enabled=True, buy_lead_days=0))
    result_14 = OV.apply(pure, _acfg(enabled=True, buy_lead_days=14))

    # 2022 election day = Nov 8; with 14-day lead gate opens Oct 25
    # Oct 26 should be gated with buy_lead_days=0 but NOT with buy_lead_days=14
    oct26 = pd.Timestamp("2022-10-26")
    assert result_0.loc[oct26, "override_active"], \
        "2022-10-26 should still be gated with buy_lead_days=0"
    assert not result_14.loc[oct26, "override_active"], \
        "2022-10-26 should NOT be gated with buy_lead_days=14"


if __name__ == "__main__":
    for fn in [
        test_parity_outside_blackout_windows,
        test_inside_window_final_zero_raw_nonzero,
        test_disabled_config_no_override,
        test_missing_config_no_override,
        test_columns_and_dtypes,
        test_output_index_identical_to_input,
        test_buy_lead_days_releases_gate_early,
    ]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all btc_overrides tests passed")
