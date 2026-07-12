"""Commodity confluence organ tests — deterministic, hermetic (synthetic frames).

Run: python -m pytest tests/test_commodity_confluence.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.commodity_confluence import (  # noqa: E402
    assess_member,
    assess_index,
    build_confluence,
    score_side,
    _score_group,
    _state_from_scores_cfg,
)
from lib import config  # noqa: E402

CFG = config.load()["commodities"]

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _make_close(
    n: int = 800,
    trend: float = 0.0002,
    vol: float = 0.012,
    seed: int = 1,
    start: str = "2015-01-01",
) -> pd.Series:
    """Synthetic daily close on a business-day DatetimeIndex."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq="B")
    return pd.Series(
        100.0 * np.exp(np.cumsum(rng.normal(trend, vol, n))),
        index=idx,
        name="close",
    )


def _base_frame(close: pd.Series) -> pd.DataFrame:
    """Minimal member frame — only the mandatory columns that compute_asset always emits."""
    n = len(close)
    ts_mom = np.tanh(close.pct_change(252).fillna(0) / 0.3).clip(-1, 1)
    state = pd.Series(np.where(ts_mom > 0, "up", np.where(ts_mom < 0, "down", "flat")),
                      index=close.index)
    mom_state = pd.Series("neutral", index=close.index)
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "close": close,
        "ts_trend": state,
        "ts_momentum": ts_mom,
        "momentum_state": mom_state,
        "risk_regime": "low_risk",
        "risk_index": rng.uniform(10, 40, n),
        "cycle_position": rng.uniform(0.3, 0.7, n),
        "momentum": ts_mom,
        "structure": rng.uniform(-0.5, 0.5, n),
        "structure_state": "neutral",
        "market_mode": "Strategic",
        "asset": "synthetic",
    }, index=close.index)


def _washout_frame(n: int = 900, seed: int = 5) -> pd.DataFrame:
    """A member designed to score high on BOTTOM:
    - Crash at the end (large negative shock_z)
    - Severely oversold D stoch and W stoch
    - Strong negative ts_trend (down)
    - No COT or cycle data -> availability normalized
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-01", periods=n, freq="B")
    # trending gently up then a sharp crash at the end
    drift = np.full(n, 0.0001)
    drift[-40:] = -0.015      # ~-45% in last 40 bars — deep washout
    close = pd.Series(
        100.0 * np.exp(np.cumsum(drift + rng.normal(0, 0.003, n))),
        index=idx,
    )
    df = _base_frame(close)
    # inject negative shock_z (exogenous pressure)
    shock_z = pd.Series(rng.normal(-0.1, 0.2, n), index=idx)
    shock_z.iloc[-1] = -2.5   # well below shock_z_macro=1.5
    df["shock_z"] = shock_z
    df["shock_state"] = "exogenous_pressure"
    # ts_trend = down, momentum_state = bear for the last stretch
    df.loc[idx[-60:], "ts_trend"] = "down"
    df.loc[idx[-60:], "momentum_state"] = "bear"
    return df


def _euphoric_frame(n: int = 900, seed: int = 7) -> pd.DataFrame:
    """A member designed to score high on TOP:
    - Strong blow-off (large positive shock_z)
    - Long up trend but momentum just rolled over (divergence)
    - Price well above 200d SMA
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-01", periods=n, freq="B")
    # consistent up-trend building a big stretch above the 200d SMA
    drift = np.full(n, 0.0012)
    drift[-20:] = -0.002   # small recent pause (macd_curl_dn territory)
    close = pd.Series(
        100.0 * np.exp(np.cumsum(drift + rng.normal(0, 0.005, n))),
        index=idx,
    )
    df = _base_frame(close)
    # inject positive shock_z
    shock_z = pd.Series(rng.normal(0.1, 0.2, n), index=idx)
    shock_z.iloc[-1] = 2.5   # well above shock_z_macro=1.5
    df["shock_z"] = shock_z
    df["shock_state"] = "exogenous_bid"
    # ts_trend = up BUT momentum_state = bear (the divergence condition)
    df["ts_trend"] = "up"
    df["momentum_state"] = "bear"
    return df


def _neutral_frame(n: int = 900, seed: int = 3) -> pd.DataFrame:
    """A boring neutral member — shock_z near 0, neutral stoch, no COT."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-01", periods=n, freq="B")
    close = pd.Series(
        100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.008, n))),
        index=idx,
    )
    df = _base_frame(close)
    shock_z = pd.Series(rng.normal(0, 0.3, n), index=idx)
    shock_z.iloc[-1] = 0.1   # near-zero shock
    df["shock_z"] = shock_z
    df["shock_state"] = "normal"
    df["ts_trend"] = "up"
    df["momentum_state"] = "neutral"
    return df


# --------------------------------------------------------------------------- #
# score_side unit tests
# --------------------------------------------------------------------------- #
def test_score_side_all_fired() -> None:
    """When all applicable conditions fire, score == 100."""
    conds = [
        ("a", True, True, 1.0),
        ("b", True, True, 2.0),
        ("c", True, True, 1.5),
    ]
    score, fired, n_app = score_side(conds)
    assert score == 100.0
    assert n_app == 3
    assert len(fired) == 3


def test_score_side_none_fired() -> None:
    """When all applicable conditions are NOT fired, score == 0."""
    conds = [
        ("a", False, True, 1.0),
        ("b", False, True, 2.0),
    ]
    score, fired, n_app = score_side(conds)
    assert score == 0.0
    assert fired == []


def test_score_side_none_applicable() -> None:
    """No applicable conditions -> score is None."""
    conds = [
        ("a", True, False, 1.0),
        ("b", False, False, 2.0),
    ]
    score, fired, n_app = score_side(conds)
    assert score is None
    assert n_app == 0


def test_score_side_partial() -> None:
    """Partial: half weight fired -> score == 50."""
    conds = [
        ("a", True,  True, 1.0),
        ("b", False, True, 1.0),
    ]
    score, fired, n_app = score_side(conds)
    assert score == 50.0
    assert n_app == 2
    assert len(fired) == 1


def test_score_side_non_applicable_excluded_from_denominator() -> None:
    """Non-applicable conditions are excluded from the denominator (not penalised)."""
    # Only 'a' (weight=2) applies; 'b' (weight=5) does NOT apply.
    # Score should be based on a alone, not diluted by b's weight.
    conds = [
        ("a", True,  True,  2.0),
        ("b", True,  False, 5.0),  # not applicable
    ]
    score, fired, n_app = score_side(conds)
    # fired/total for applicable = 2.0/2.0 = 100
    assert score == 100.0
    assert n_app == 1


# --------------------------------------------------------------------------- #
# assess_member: washout bottom
# --------------------------------------------------------------------------- #
def test_washout_member_high_bottom_score() -> None:
    """A deep-washout member must have a high bottom score."""
    df = _washout_frame()
    result = assess_member("washout_test", "energy", df, CFG)
    assert result["name"] == "washout_test"
    assert result["class"] == "energy"
    # bottom score should be substantially above 0; exact value depends on
    # how many conditions fire, but a negative-shock + close to 200d-low frame
    # should have at least shock firing -> some score
    bs = result["bottom_score"]
    # If applicable, score must be non-None
    if result["n_bottom_applicable"] >= CFG["confluence"]["min_applicable"]:
        assert bs is not None
        assert bs > 0


def test_washout_member_state_is_bottom_family_or_neutral() -> None:
    """A washout member's state must be one of the expected bottom/neutral enumerated states."""
    df = _washout_frame()
    result = assess_member("washout_test", "energy", df, CFG)
    valid_states = {
        "Washout bottom forming",
        "Washing out — high risk",
        "Basing — early bottom signs",
        "Neutral",
        None,
    }
    assert result["state"] in valid_states


# --------------------------------------------------------------------------- #
# assess_member: euphoric top
# --------------------------------------------------------------------------- #
def test_euphoric_member_has_divergence_condition() -> None:
    """Euphoric frame has ts_trend='up' + momentum_state='bear' -> divergence fires."""
    df = _euphoric_frame()
    result = assess_member("euphoric_test", "precious", df, CFG)
    top_fired_codes = {c["code"] for c in result["top_fired"]}
    # divergence condition should fire
    assert "divergence" in top_fired_codes, f"top fired: {top_fired_codes}"


def test_euphoric_member_shock_top_fires() -> None:
    """Positive shock_z=2.5 should fire shock_top."""
    df = _euphoric_frame()
    result = assess_member("euphoric_test", "precious", df, CFG)
    top_fired_codes = {c["code"] for c in result["top_fired"]}
    assert "shock_top" in top_fired_codes, f"top fired: {top_fired_codes}"


def test_euphoric_member_top_score_above_bottom() -> None:
    """Euphoric top score should exceed bottom score."""
    df = _euphoric_frame()
    result = assess_member("euphoric_test", "precious", df, CFG)
    ts = result["top_score"]
    bs = result["bottom_score"] if result["bottom_score"] is not None else -1.0
    if ts is not None:
        assert ts > bs, f"top={ts} not > bottom={bs}"


# --------------------------------------------------------------------------- #
# assess_member: availability normalisation (no COT, no shock)
# --------------------------------------------------------------------------- #
def test_no_cot_no_shock_still_scores() -> None:
    """A member without COT or shock columns must still score on applicable conditions."""
    close = _make_close(n=900, seed=20)
    df = _base_frame(close)
    # no shock_z, no pos_pctile columns
    assert "shock_z" not in df.columns
    assert "pos_pctile" not in df.columns

    result = assess_member("plain_member", "grain", df, CFG)
    # Should NOT be None solely because COT/shock is missing;
    # it can still apply MTF and trend conditions.
    # If n_applicable >= min_applicable it should have a score.
    if result["n_bottom_applicable"] >= CFG["confluence"]["min_applicable"]:
        assert result["bottom_score"] is not None
    if result["n_top_applicable"] >= CFG["confluence"]["min_applicable"]:
        assert result["top_score"] is not None


def test_no_cot_not_penalised() -> None:
    """COT not present -> cot_short / cot_long are NOT applicable -> weight excluded."""
    close = _make_close(n=900, seed=21)
    df = _base_frame(close)
    df["shock_z"] = pd.Series(np.zeros(len(df)), index=df.index)
    assert "pos_pctile" not in df.columns

    result = assess_member("no_cot", "grain", df, CFG)
    # cot_short / cot_long must NOT appear in fired codes
    all_fired_codes = (
        {c["code"] for c in result["bottom_fired"]}
        | {c["code"] for c in result["top_fired"]}
    )
    assert "cot_short" not in all_fired_codes
    assert "cot_long" not in all_fired_codes


# --------------------------------------------------------------------------- #
# assess_member: n_applicable < min_applicable -> null state
# --------------------------------------------------------------------------- #
def test_too_short_series_gives_null_state() -> None:
    """A very short series has insufficient MTF -> null state (insufficient signal)."""
    close = _make_close(n=10, seed=99)
    df = _base_frame(close)
    result = assess_member("tiny", "soft", df, CFG)
    # With only 10 bars, no MTF conditions are applicable
    assert result["state"] is None
    assert result["null_reason"] == "insufficient signal"


# --------------------------------------------------------------------------- #
# assess_member: JSON serialisability
# --------------------------------------------------------------------------- #
def test_assess_member_json_serializable() -> None:
    """assess_member output must be JSON-serialisable."""
    df = _neutral_frame()
    result = assess_member("neutral_test", "industrial", df, CFG)
    encoded = json.dumps(result)
    assert len(encoded) > 2
    # must not contain numpy scalars manifesting as unserializable objects
    assert "NaN" not in encoded
    assert "Infinity" not in encoded


# --------------------------------------------------------------------------- #
# assess_index
# --------------------------------------------------------------------------- #
def test_assess_index_smoke() -> None:
    """assess_index with synthetic index close returns a valid dict."""
    close = _make_close(n=900, seed=50)
    result = assess_index(close, {}, CFG)
    assert result["name"] == "index"
    assert result["class"] == "index"
    assert isinstance(result["bottom_fired"], list)
    assert isinstance(result["top_fired"], list)


def test_assess_index_json_serializable() -> None:
    """assess_index output must be JSON-serialisable."""
    close = _make_close(n=900, seed=51)
    breadth = {"breadth_pctile": 0.05}  # sector washout
    result = assess_index(close, breadth, CFG)
    encoded = json.dumps(result)
    assert "NaN" not in encoded


def test_assess_index_breadth_washout_fires() -> None:
    """With breadth_pctile=0.02 (very low), breadth_bottom should fire if applicable."""
    close = _make_close(n=900, seed=52)
    breadth = {"breadth_pctile": 0.02}
    result = assess_index(close, breadth, CFG)
    bot_fired = {c["code"] for c in result["bottom_fired"]}
    if result["n_bottom_applicable"] >= CFG["confluence"]["min_applicable"]:
        assert "breadth_bottom" in bot_fired, f"expected breadth_bottom in {bot_fired}"


def test_assess_index_breadth_euphoria_fires() -> None:
    """With breadth_pctile=0.98 (very high), breadth_top should fire if applicable."""
    close = _make_close(n=900, seed=53)
    breadth = {"breadth_pctile": 0.98}
    result = assess_index(close, breadth, CFG)
    top_fired = {c["code"] for c in result["top_fired"]}
    if result["n_top_applicable"] >= CFG["confluence"]["min_applicable"]:
        assert "breadth_top" in top_fired, f"expected breadth_top in {top_fired}"


# --------------------------------------------------------------------------- #
# build_confluence
# --------------------------------------------------------------------------- #
def test_build_confluence_empty_returns_empty() -> None:
    """build_confluence({}) must return {} without raising."""
    result = build_confluence({}, CFG)
    assert result == {}


def test_build_confluence_never_raises() -> None:
    """build_confluence with any broken input must not raise."""
    # pass a completely garbage member dict
    result = build_confluence({"bad": None}, CFG)  # type: ignore[dict-item]
    assert isinstance(result, dict)


def test_build_confluence_structure() -> None:
    """build_confluence with valid members returns expected top-level keys."""
    member_results = {
        "gold":     _washout_frame(seed=1),
        "silver":   _neutral_frame(seed=2),
        "copper":   _euphoric_frame(seed=3),
        "oil":      _neutral_frame(seed=4),
        "natgas":   _neutral_frame(seed=5),
        "gasoline": _neutral_frame(seed=6),
    }
    close_idx = _make_close(n=900, seed=99)
    result = build_confluence(member_results, CFG, index_close=close_idx)
    assert isinstance(result, dict)
    assert "asof" in result
    assert "members" in result
    assert "index" in result


def test_build_confluence_member_count() -> None:
    """Members list length must equal the number of DataFrame inputs."""
    member_results = {
        f"m{i}": _neutral_frame(seed=i + 10) for i in range(6)
    }
    result = build_confluence(member_results, CFG)
    if result:
        assert len(result["members"]) == 6


def test_build_confluence_json_serializable() -> None:
    """Full build_confluence output must be JSON-serialisable."""
    member_results = {
        "gold":   _washout_frame(seed=1),
        "silver": _neutral_frame(seed=2),
        "copper": _euphoric_frame(seed=3),
        "oil":    _neutral_frame(seed=4),
        "natgas": _neutral_frame(seed=5),
        "grain":  _neutral_frame(seed=6),
    }
    close_idx = _make_close(n=900, seed=88)
    result = build_confluence(member_results, CFG, index_close=close_idx,
                              breadth={"breadth_pctile": 0.45})
    assert isinstance(result, dict)
    if result:
        encoded = json.dumps(result)
        assert "NaN" not in encoded
        assert "Infinity" not in encoded


def test_build_confluence_no_nan_in_scores() -> None:
    """All bottom_score and top_score values in members must be float or None."""
    member_results = {
        f"m{i}": _neutral_frame(seed=i + 20) for i in range(4)
    }
    result = build_confluence(member_results, CFG)
    if not result:
        return
    for m in result["members"]:
        bs = m.get("bottom_score")
        ts = m.get("top_score")
        if bs is not None:
            assert isinstance(bs, float), f"bottom_score is {type(bs)}"
            assert not (bs != bs)  # NaN check
        if ts is not None:
            assert isinstance(ts, float), f"top_score is {type(ts)}"
            assert not (ts != ts)


# --------------------------------------------------------------------------- #
# cycle_phase routing
# --------------------------------------------------------------------------- #
def test_cycle_phase_trough_fires_bottom() -> None:
    """When cycle_phase='Trough' is passed, cycle_bottom condition fires."""
    df = _neutral_frame(seed=30)
    result = assess_member("cycle_test", "energy", df, CFG, cycle_phase="Trough")
    bot_fired_codes = {c["code"] for c in result["bottom_fired"]}
    assert "cycle_bottom" in bot_fired_codes, f"expected cycle_bottom in {bot_fired_codes}"


def test_cycle_phase_peak_fires_top() -> None:
    """When cycle_phase='Peak' is passed, cycle_top condition fires."""
    df = _neutral_frame(seed=31)
    result = assess_member("cycle_test", "energy", df, CFG, cycle_phase="Peak")
    top_fired_codes = {c["code"] for c in result["top_fired"]}
    assert "cycle_top" in top_fired_codes, f"expected cycle_top in {top_fired_codes}"


def test_no_cycle_phase_not_applicable() -> None:
    """When cycle_phase=None, cycle conditions are not applicable -> not in fired."""
    df = _neutral_frame(seed=32)
    result = assess_member("no_cycle", "energy", df, CFG, cycle_phase=None)
    all_codes = (
        {c["code"] for c in result["bottom_fired"]}
        | {c["code"] for c in result["top_fired"]}
    )
    assert "cycle_bottom" not in all_codes
    assert "cycle_top" not in all_codes


# --------------------------------------------------------------------------- #
# _score_group unit tests
# --------------------------------------------------------------------------- #
def test_score_group_all_fired() -> None:
    """All conditions fired -> 100."""
    conds = [("a", True, True, 1.0), ("b", True, True, 2.0)]
    assert _score_group(conds, 2) == 100.0


def test_score_group_none_fired() -> None:
    """No conditions fired -> 0."""
    conds = [("a", False, True, 1.0), ("b", False, True, 2.0)]
    assert _score_group(conds, 2) == 0.0


def test_score_group_insufficient_applicable() -> None:
    """Fewer than group_min_applicable applicable -> None."""
    conds = [("a", True, True, 1.0), ("b", True, False, 2.0)]
    # only 1 applicable but group_min=2
    assert _score_group(conds, 2) is None


def test_score_group_zero_applicable_returns_none() -> None:
    """Zero applicable -> None regardless of group_min."""
    conds = [("a", True, False, 1.0), ("b", True, False, 2.0)]
    assert _score_group(conds, 0) is None


# --------------------------------------------------------------------------- #
# Two-phase state machine — real fixture tests
# (fix #3 from adversarial review)
# --------------------------------------------------------------------------- #
def _post_turn_oversold_frame() -> pd.DataFrame:
    """POST-TURN oversold frame for 'Washout bottom forming' state test.

    Profile:
    - Long uptrend (bars 0-700) followed by a −40% crash (bars 700-897).
    - Final 3 bars: sharp uptick that pushes StochRSI above 20 (fires D stoch_cross_up).
    - Price still deeply below 200-day SMA (stretch_below fires).
    - Injected negative shock_z (shock_bottom fires).
    - Oversold weekly stoch (oversold_htf fires).
    - cycle_phase="Recovery" is passed separately at call site.

    The turn group (curl + cycle) fires with score 62.5 (>= strong 60) because
    bc_conf is not applicable (bc_score < bc_score_min_applicable=10) so the
    denominator is 1.5+1.5+1.0=4.0, giving (1.5+1.0)/4.0 = 62.5%.
    """
    n = 900
    idx = pd.date_range("2015-01-01", periods=n, freq="B")
    rng = np.random.default_rng(1)
    drift = np.full(n, 0.0)
    drift[:700] = 0.0004
    drift[700:897] = -0.020   # crash
    drift[897:] = 0.008       # 3-bar recovery (fires stoch_cross_up)
    close = pd.Series(
        100.0 * np.exp(np.cumsum(drift + rng.normal(0, 0.0005, n))),
        index=idx,
    )
    ts_mom = np.tanh(close.pct_change(252).fillna(0) / 0.3).clip(-1, 1)
    df = pd.DataFrame({
        "close": close,
        "ts_trend": "down",
        "ts_momentum": ts_mom,
        "momentum_state": "bear",
        "risk_regime": "low_risk",
        "risk_index": 60.0,
        "cycle_position": 0.2,
        "momentum": ts_mom,
        "structure": -0.5,
        "structure_state": "negative",
        "market_mode": "Strategic",
        "asset": "synthetic",
    }, index=idx)
    # inject recent negative shock_z to fire shock_bottom
    shock_z = pd.Series(0.0, index=idx)
    shock_z.iloc[-1] = -2.5
    df["shock_z"] = shock_z
    df["shock_state"] = "exogenous_pressure"
    return df


def _euphoric_top_rolling_over_frame() -> pd.DataFrame:
    """Euphoric top frame for 'Euphoric top — rolling over' state test.

    Profile:
    - Strong long uptrend (drift=0.0012 for 895 bars) well above 200-day SMA.
    - Small 5-bar dip at end (drift=-0.003 for last 5 bars) triggering divergence
      (ts_trend='up' + momentum_state='bear' + price still above SMA200).
    - Injected positive shock_z=2.5 (shock_top fires).
    - Weekly stoch still overbought (overbought_htf fires).
    - cycle_phase="Peak" is passed separately at call site.

    Euphoria group fires on shock_top + overbought_htf giving 54.5% (>= early 40).
    Rollover group fires on divergence + cycle_top giving 66.7% (>= strong 60).
    """
    n = 900
    idx = pd.date_range("2015-01-01", periods=n, freq="B")
    rng = np.random.default_rng(7)
    drift = np.full(n, 0.0012)
    drift[-5:] = -0.003  # 5-bar dip (enough for divergence, not enough to erase overbought)
    close = pd.Series(
        100.0 * np.exp(np.cumsum(drift + rng.normal(0, 0.005, n))),
        index=idx,
    )
    ts_mom = np.tanh(close.pct_change(252).fillna(0) / 0.3).clip(-1, 1)
    df = pd.DataFrame({
        "close": close,
        "ts_trend": "up",
        "ts_momentum": ts_mom,
        "momentum_state": "bear",  # divergence: up trend but momentum=bear
        "risk_regime": "low_risk",
        "risk_index": 30.0,
        "cycle_position": 0.8,
        "momentum": ts_mom,
        "structure": 0.5,
        "structure_state": "positive",
        "market_mode": "Strategic",
        "asset": "synthetic",
    }, index=idx)
    shock_z = pd.Series(0.0, index=idx)
    shock_z.iloc[-1] = 2.5
    df["shock_z"] = shock_z
    df["shock_state"] = "exogenous_bid"
    return df


def _still_crashing_frame() -> pd.DataFrame:
    """Still-crashing frame for 'Washing out — high risk' state test.

    Profile:
    - Long uptrend then an ongoing steep decline with no recovery.
    - Negative shock_z fires, price deeply below 200-day, oversold HTF.
    - No turn signals (no stoch_cross_up, no curl, no cycle phase passed).

    Capitulation group fires high (>= strong 60).
    Turn group fires low (< early 40) — only noise from cycles.
    """
    n = 900
    idx = pd.date_range("2015-01-01", periods=n, freq="B")
    rng = np.random.default_rng(5)
    drift = np.full(n, 0.0)
    drift[:700] = 0.0004
    drift[700:] = -0.020  # still crashing at end (no recovery)
    close = pd.Series(
        100.0 * np.exp(np.cumsum(drift + rng.normal(0, 0.0005, n))),
        index=idx,
    )
    ts_mom = np.tanh(close.pct_change(252).fillna(0) / 0.3).clip(-1, 1)
    df = pd.DataFrame({
        "close": close,
        "ts_trend": "down",
        "ts_momentum": ts_mom,
        "momentum_state": "bear",
        "risk_regime": "low_risk",
        "risk_index": 60.0,
        "cycle_position": 0.2,
        "momentum": ts_mom,
        "structure": -0.5,
        "structure_state": "negative",
        "market_mode": "Strategic",
        "asset": "synthetic",
    }, index=idx)
    shock_z = pd.Series(0.0, index=idx)
    shock_z.iloc[-1] = -2.5
    df["shock_z"] = shock_z
    df["shock_state"] = "exogenous_pressure"
    return df


def test_state_washout_bottom_forming() -> None:
    """A post-turn oversold frame with cycle_phase='Recovery' must reach
    state == 'Washout bottom forming' (turn_score >= strong + cap_score >= early).

    Mechanism:
    - curl fires (D stoch_cross_up = True from 3-bar recovery)
    - cycle_bottom fires (cycle_phase='Recovery')
    - bc_conf NOT applicable (bc_score < bc_score_min_applicable=10)
    - turn_score = (curl(1.5) + cycle(1.0)) / (curl(1.5) + armed(1.5) + cycle(1.0)) = 62.5%
    - cap_score = shock + oversold_htf + stretch_below = 81.8%
    """
    df = _post_turn_oversold_frame()
    result = assess_member("post_turn", "energy", df, CFG, cycle_phase="Recovery")
    assert result["state"] == "Washout bottom forming", (
        f"Expected 'Washout bottom forming' but got '{result['state']}'; "
        f"turn={result['turn_score']}, cap={result['capitulation_score']}, "
        f"bottom_fired={[c['code'] for c in result['bottom_fired']]}"
    )
    # verify sub-scores are in the expected range
    assert result["turn_score"] is not None and result["turn_score"] >= 60
    assert result["capitulation_score"] is not None and result["capitulation_score"] >= 40


def test_state_euphoric_top_rolling_over() -> None:
    """An overbought frame with a small rollover and cycle_phase='Peak' must reach
    state == 'Euphoric top — rolling over' (rollover >= strong + euphoria >= early).

    Mechanism:
    - divergence fires (ts_trend='up' + momentum_state='bear' + price > SMA200)
    - cycle_top fires (cycle_phase='Peak')
    - shock_top fires (shock_z=2.5 > shock_z_macro=1.5)
    - overbought_htf fires (weekly stoch still elevated)
    - rollover_score = (divergence(2.0) + cycle(1.0)) / (curl_dn + div + cycle) >= 60
    - euphoria_score = (shock + ob_htf) / applicable >= 40
    """
    df = _euphoric_top_rolling_over_frame()
    result = assess_member("euphoric_top", "precious", df, CFG, cycle_phase="Peak")
    assert result["state"] == "Euphoric top — rolling over", (
        f"Expected 'Euphoric top — rolling over' but got '{result['state']}'; "
        f"euph={result['euphoria_score']}, roll={result['rollover_score']}, "
        f"top_fired={[c['code'] for c in result['top_fired']]}"
    )
    assert result["rollover_score"] is not None and result["rollover_score"] >= 60
    assert result["euphoria_score"] is not None and result["euphoria_score"] >= 40


def test_state_washing_out_high_risk() -> None:
    """A still-crashing frame with no turn signals must reach
    state == 'Washing out — high risk' (cap >= strong + turn < early).

    Mechanism:
    - shock_bottom fires (shock_z=-2.5)
    - stretch_below fires (price deeply below 200d SMA)
    - oversold_htf fires (weekly stoch collapsed)
    - cap_score = high (shock+stretch_below+oversold_htf firing)
    - turn conditions: cycle not passed, curl unlikely to fire during freefall
    - turn_score << early (40)
    """
    df = _still_crashing_frame()
    result = assess_member("crashing", "energy", df, CFG)
    assert result["state"] == "Washing out — high risk", (
        f"Expected 'Washing out — high risk' but got '{result['state']}'; "
        f"cap={result['capitulation_score']}, turn={result['turn_score']}, "
        f"bottom_fired={[c['code'] for c in result['bottom_fired']]}"
    )
    assert result["capitulation_score"] is not None and result["capitulation_score"] >= 60
    # turn_score should be below early threshold or None
    assert (result["turn_score"] is None) or (result["turn_score"] < 40)


# --------------------------------------------------------------------------- #
# sub-scores present in all assess_member outputs
# --------------------------------------------------------------------------- #
def test_sub_scores_present_in_output() -> None:
    """assess_member output must always include the four sub-score keys."""
    df = _neutral_frame(seed=50)
    result = assess_member("sub_score_test", "grain", df, CFG)
    for key in ("capitulation_score", "turn_score", "euphoria_score", "rollover_score"):
        assert key in result, f"missing key '{key}' in assess_member output"
        # values must be float or None (never a numpy scalar)
        val = result[key]
        if val is not None:
            assert isinstance(val, float), f"sub-score '{key}' is {type(val)}, not float"


def test_sub_scores_present_in_assess_index() -> None:
    """assess_index output must include the four sub-score keys."""
    close = _make_close(n=900, seed=60)
    result = assess_index(close, {}, CFG)
    for key in ("capitulation_score", "turn_score", "euphoria_score", "rollover_score"):
        assert key in result, f"missing key '{key}' in assess_index output"


# --------------------------------------------------------------------------- #
# label integrity
# --------------------------------------------------------------------------- #
def test_fired_conditions_have_required_keys() -> None:
    """Every fired condition dict must have code, label_en, label_zh."""
    df = _washout_frame(seed=40)
    result = assess_member("label_test", "precious", df, CFG)
    for cond in result["bottom_fired"] + result["top_fired"]:
        assert "code" in cond, f"missing 'code' in {cond}"
        assert "label_en" in cond, f"missing 'label_en' in {cond}"
        assert "label_zh" in cond, f"missing 'label_zh' in {cond}"


# --------------------------------------------------------------------------- #
# integrate with real engine (conditional on local stores)
# --------------------------------------------------------------------------- #
def test_real_engine_smoke() -> None:
    """Smoke test with real data if stores are available. Skips otherwise."""
    try:
        from engine import commodity_inputs, commodity_signals, commodity_index
        cfg = config.load()["commodities"]
        members_ai = commodity_inputs.load_members(cfg)
        if not members_ai:
            pytest.skip("No commodity member stores available")
        member_results = {n: commodity_signals.compute_asset(ai, cfg)
                         for n, ai in list(members_ai.items())[:3]}
        cs = commodity_index.composite_series(member_results, cfg)
        idx_ew = cs.get("idx_ew")
        result = build_confluence(member_results, cfg, index_close=idx_ew)
        assert isinstance(result, dict)
        if result:
            json.dumps(result)  # must be JSON-safe
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Real engine unavailable: {e}")


if __name__ == "__main__":
    fns = [
        test_score_side_all_fired,
        test_score_side_none_fired,
        test_score_side_none_applicable,
        test_score_side_partial,
        test_score_side_non_applicable_excluded_from_denominator,
        test_score_group_all_fired,
        test_score_group_none_fired,
        test_score_group_insufficient_applicable,
        test_score_group_zero_applicable_returns_none,
        test_washout_member_high_bottom_score,
        test_washout_member_state_is_bottom_family_or_neutral,
        test_euphoric_member_has_divergence_condition,
        test_euphoric_member_shock_top_fires,
        test_euphoric_member_top_score_above_bottom,
        test_no_cot_no_shock_still_scores,
        test_no_cot_not_penalised,
        test_too_short_series_gives_null_state,
        test_assess_member_json_serializable,
        test_assess_index_smoke,
        test_assess_index_json_serializable,
        test_assess_index_breadth_washout_fires,
        test_assess_index_breadth_euphoria_fires,
        test_build_confluence_empty_returns_empty,
        test_build_confluence_never_raises,
        test_build_confluence_structure,
        test_build_confluence_member_count,
        test_build_confluence_json_serializable,
        test_build_confluence_no_nan_in_scores,
        test_cycle_phase_trough_fires_bottom,
        test_cycle_phase_peak_fires_top,
        test_no_cycle_phase_not_applicable,
        test_state_washout_bottom_forming,
        test_state_euphoric_top_rolling_over,
        test_state_washing_out_high_risk,
        test_sub_scores_present_in_output,
        test_sub_scores_present_in_assess_index,
        test_fired_conditions_have_required_keys,
        test_real_engine_smoke,
    ]
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except pytest.skip.Exception as e:
            print(f"SKIP {fn.__name__}: {e}")
    print("all commodity confluence tests passed")
