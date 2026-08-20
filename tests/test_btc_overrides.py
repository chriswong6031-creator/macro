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


# --------------------------------------------------------------------------- #
# W2 — Class-1 AUTO-RELEASE (owner D1): new-ATH structural invalidation
# --------------------------------------------------------------------------- #
_CLASS1_REGISTRY = [{
    "id": "midterm_blackout",
    "dof_cost": 4,
    "release_rules": [
        {"kind": "calendar"},
        {"kind": "structural_invalidation", "signal": "new_ath_close",
         "confirm_days": 5},
    ],
}]


def _release_scenario_close(idx: pd.DatetimeIndex,
                            breaks: list[float],
                            break_start: str) -> pd.Series:
    """Synthetic replay tape: prior ATH = 100 (set through 2025), bear at 50 into the
    2026 gate window, then the `breaks` closes from `break_start` onward, then back
    to 90 (below the broken ATH — exercises stickiness)."""
    close = pd.Series(50.0, index=idx)
    close.loc[:"2025-12-31"] = 100.0                       # historical ATH = 100
    start = pd.Timestamp(break_start)
    for k, v in enumerate(breaks):
        close.loc[start + pd.Timedelta(days=k)] = v
    close.loc[start + pd.Timedelta(days=len(breaks)):] = 90.0
    return close


def test_class1_release_after_exactly_five_confirm_closes() -> None:
    """The replay acceptance test (masterplan §5 W2): a synthetic new-ATH sequence
    inside the 2026 gate window releases the gate on EXACTLY the 5th consecutive
    confirm close — not the 1st, not the 4th — and the release is sticky for the
    remainder of the window even after price falls back below the broken ATH."""
    idx = pd.date_range("2025-06-01", "2026-12-31", freq="D")
    pure = _pure_alloc(idx)
    close = _release_scenario_close(idx, [101, 102, 103, 104, 105], "2026-08-01")
    result = OV.apply(pure, _acfg(enabled=True),
                      ctx={"close": close, "overrides": _CLASS1_REGISTRY})

    rel = result["override_released"].astype(bool)
    act = result["override_active"].astype(bool)
    # masked (gate holds) from Jan 1 through the 4th confirm close…
    assert act.loc["2026-01-01":"2026-08-04"].all()
    assert not rel.loc["2026-01-01":"2026-08-04"].any()
    assert result["alloc_optimal"].loc["2026-01-01":"2026-08-04"].eq(0.0).all()
    # …released ON the 5th confirm close (2026-08-05), final steps down to raw…
    assert rel.loc["2026-08-05"], "release must fire on the 5th consecutive confirm close"
    assert not act.loc["2026-08-05":"2026-11-02"].any()
    pd.testing.assert_series_equal(
        result["alloc_optimal"].loc["2026-08-05":],
        result["alloc_optimal_raw"].loc["2026-08-05":],
        check_names=False, obj="final must equal raw after the release")
    # …and STICKY through the window end although price fell back to 90 (< broken ATH).
    assert rel.loc["2026-08-06":"2026-11-02"].all(), "release must be sticky in-window"
    # outside the window the release state disarms (nothing left to release)
    assert not rel.loc["2026-11-03":].any()


def test_class1_failed_attempt_resets_and_does_not_release() -> None:
    """Four consecutive closes above the broken ATH followed by a close back below it
    must NOT release — 'consecutive' means consecutive; the counter resets."""
    idx = pd.date_range("2025-06-01", "2026-12-31", freq="D")
    pure = _pure_alloc(idx)
    close = _release_scenario_close(idx, [101, 102, 103, 104, 99, 101, 102], "2026-08-01")
    result = OV.apply(pure, _acfg(enabled=True),
                      ctx={"close": close, "overrides": _CLASS1_REGISTRY})
    assert not result["override_released"].astype(bool).any()
    # the gate keeps masking through the whole 2026 window
    assert result["alloc_optimal"].loc["2026-01-01":"2026-11-02"].eq(0.0).all()
    assert result["override_active"].astype(bool).loc["2026-01-01":"2026-11-02"].all()


def test_class1_requires_declared_rule_and_close() -> None:
    """No declared structural_invalidation rule (or no close series) -> W0 behavior:
    the gate holds through the window regardless of the tape. The registry is the
    ship switch (owner D1 recorded there), not the code."""
    idx = pd.date_range("2025-06-01", "2026-12-31", freq="D")
    pure = _pure_alloc(idx)
    close = _release_scenario_close(idx, [101, 102, 103, 104, 105], "2026-08-01")
    # W0-style string release_rules — structurally undeclared
    legacy = [{"id": "midterm_blackout", "dof_cost": 3,
               "release_rules": ["calendar: ~election day"]}]
    for ctx in (None,
                {"close": close},                                    # no registry
                {"overrides": _CLASS1_REGISTRY},                     # no close
                {"close": close, "overrides": legacy}):              # rule not declared
        result = OV.apply(pure, _acfg(enabled=True), ctx=ctx)
        assert not result["override_released"].astype(bool).any()
        assert result["alloc_optimal"].loc["2026-01-01":"2026-11-02"].eq(0.0).all()


def test_class1_no_release_state_outside_gate_windows() -> None:
    """A confirmed new-ATH sequence in a NON-gated year is a no-op: nothing to
    release, final == raw everywhere, override_released stays 0."""
    idx = pd.date_range("2024-01-01", "2025-12-31", freq="D")   # no midterm year
    pure = _pure_alloc(idx)
    close = pd.Series(100.0, index=idx)
    close.loc["2025-06-01":] = 120.0                            # sustained new ATH
    result = OV.apply(pure, _acfg(enabled=True),
                      ctx={"close": close, "overrides": _CLASS1_REGISTRY})
    assert not result["override_released"].astype(bool).any()
    assert not result["override_active"].astype(bool).any()
    pd.testing.assert_series_equal(result["alloc_optimal"], result["alloc_optimal_raw"],
                                   check_names=False)


def test_class1_ancient_ath_break_never_releases_later_windows() -> None:
    """Regression (live-tape bug): the spliced price history starts mid-2014, so an
    early SERIES-ATH break (2016-style) once confirmed must be CONSUMED — price then
    sitting above that long-ago broken reference for a decade must not read as
    'currently confirming' and spuriously release the 2018/2022/2026 gates."""
    idx = pd.date_range("2015-01-01", "2026-12-31", freq="D")
    pure = _pure_alloc(idx)
    close = pd.Series(100.0, index=idx)                     # series starts at 100
    close.loc["2015-06-01":"2015-06-05"] = [200.0, 201.0, 202.0, 203.0, 204.0]  # early break: fires 2015-06-05
    close.loc["2015-06-06":] = 150.0                        # above the OLD ref (100) forever after…
    result = OV.apply(pure, _acfg(enabled=True),
                      ctx={"close": close, "overrides": _CLASS1_REGISTRY})
    # …but no gate window may release: no NEW ATH ever prints again
    assert not result["override_released"].astype(bool).any()
    for probe in ("2018-06-01", "2022-06-01", "2026-06-01"):
        assert result.loc[probe, "alloc_optimal"] == 0.0, f"gate must hold on {probe}"
        assert bool(result.loc[probe, "override_active"])


def test_ath_invalidation_confirmed_unit() -> None:
    """Unit semantics of the confirm sequence: starts only on a genuine new-ATH close;
    a plateau above the BROKEN reference counts (no fresh record needed); a touch of
    the reference resets; missing closes reset; first bar can never fire. The confirm
    is a one-bar EVENT (fires on the Nth close, then the machine resets)."""
    idx = pd.date_range("2026-01-01", periods=12, freq="D")
    #       ATH plateau=100  break  holds above broken ref=100 (no fresh records)  dip   re-break (ref now 103)
    vals = [100, 100, 100,   103,   102.5, 102.4, 102.1, 102.05,                   99.0, 103.5, 104, 105]
    conf = OV.ath_invalidation_confirmed(pd.Series(vals, index=idx), confirm_days=5)
    # bars 3..7 are a 5-long sequence above the broken ATH (100): confirmed on bar 7
    assert not conf.iloc[:7].any()
    assert bool(conf.iloc[7])
    # bar 8 closes back below the reference: reset — not confirmed
    assert not conf.iloc[8:].any()   # the re-attempt (vs the raised ATH 103) only reaches streak 3
    # NaN breaks a sequence
    vals_nan = [100.0, 100.0, 100.0, 103.0, 104.0, np.nan, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0]
    conf_nan = OV.ath_invalidation_confirmed(pd.Series(vals_nan, index=idx), confirm_days=5)
    assert not conf_nan.iloc[:10].any()   # NaN at bar 5 killed the first sequence
    # sequence restarted at bar 6 (105 > ath 104): bars 6..10 = 5 consecutive -> bar 10
    assert bool(conf_nan.iloc[10])
    # a monotonically rising tape from bar 0 can only confirm from bar 5 (bar 0 has no prior ATH)
    rising = OV.ath_invalidation_confirmed(
        pd.Series(range(100, 112), index=idx, dtype=float), confirm_days=5)
    assert not rising.iloc[:5].any() and bool(rising.iloc[5])


def test_total_dof_sums_registry() -> None:
    assert OV.total_dof({"overrides": [{"dof_cost": 4}, {"dof_cost": 2}]}) == 6
    assert OV.total_dof({"overrides": [{}]}) == 1        # undeclared cost defaults to 1
    assert OV.total_dof({"overrides": []}) == 0
    assert OV.total_dof({}) == 0
    # the LIVE registry must charge the pre-committed cost (3 gate + 1 confirm window)
    assert OV.total_dof(config.load()["vector"]) >= 4


def test_cond_up_prob_zeroes_invalidated_markdown_tilt() -> None:
    """W2: a structurally INVALIDATED markdown leg must carry ZERO cycle tilt in the
    conditional up-probability (scripts/build_vector._cond_up_prob)."""
    from scripts.build_vector import _cond_up_prob
    idx = pd.date_range("2025-01-01", periods=400, freq="D")
    base = pd.DataFrame({
        "close": 100.0,
        "momentum_state": "bull",
        "cphase_phase": "markdown",
        "cphase_pct": 0.5,
        "cphase_status": "on_track",
    }, index=idx)
    cfg = {"prob_min_cell_n": 10, "prob_shrink_alpha": 5.0, "macro_tilt_pp": 5,
           "cycle_tilt_pp": 6, "cycle_top_zone": 0.85,
           "prob_floor": 0.05, "prob_ceil": 0.95}
    _, _, _, tilt_on_track = _cond_up_prob(base, cfg, 7)
    assert tilt_on_track == -6, "markdown outside the reversal zone tilts down by cycle_tilt_pp"
    inv = base.copy()
    inv["cphase_status"] = "invalidated"
    _, _, _, tilt_invalidated = _cond_up_prob(inv, cfg, 7)
    assert tilt_invalidated == 0, "an invalidated markdown leg has zero cycle authority"


if __name__ == "__main__":
    for fn in [
        test_parity_outside_blackout_windows,
        test_inside_window_final_zero_raw_nonzero,
        test_disabled_config_no_override,
        test_missing_config_no_override,
        test_columns_and_dtypes,
        test_output_index_identical_to_input,
        test_buy_lead_days_releases_gate_early,
        test_class1_release_after_exactly_five_confirm_closes,
        test_class1_failed_attempt_resets_and_does_not_release,
        test_class1_requires_declared_rule_and_close,
        test_class1_no_release_state_outside_gate_windows,
        test_class1_ancient_ath_break_never_releases_later_windows,
        test_ath_invalidation_confirmed_unit,
        test_total_dof_sums_registry,
        test_cond_up_prob_zeroes_invalidated_markdown_tilt,
    ]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all btc_overrides tests passed")
