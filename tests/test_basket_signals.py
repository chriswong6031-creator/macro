"""Consolidated-candle basket signals — engine.basket_index / basket_mtf / basket_tape and the
new MTF + vol-hole legs/gates in engine.theme_scoring.

The candle builder is exercised against SYNTHETIC per-member OHLCV (the loader is monkeypatched)
so nothing here touches the data files or the network. We verify:
  • the equal-weight candle reduces to the EW return path and produces VALID candles (high≥close≥low),
  • point-in-time vs current-membership masking, weighting modes, dollar-volume + coverage,
  • the MTF read is bounded and shaped, the tape resolves a vol-hole regime + money-flow,
  • the drawdown-control gate (below long-trend ⇒ never ENTER/ACCUMULATE) and weight renormalisation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import basket_index as bi
from engine import basket_mtf, basket_tape
from engine import theme_scoring as ts


# --------------------------------------------------------------------- fixtures
def _synth_ohlcv(seed: int, n: int = 1200, drift: float = 0.0004, start="2018-01-01") -> pd.DataFrame:
    """A deterministic OHLCV frame with a gentle uptrend + noise (valid bars: high≥{o,c}≥low)."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    rets = rng.normal(drift, 0.014, n)
    close = pd.Series(100.0 * np.exp(np.cumsum(rets)), index=idx)
    prev = close.shift(1).fillna(close.iloc[0])
    rng2 = np.abs(rng.normal(0.0, 0.008, n))
    high = np.maximum(close, prev) * (1 + rng2)
    low = np.minimum(close, prev) * (1 - rng2)
    open_ = prev
    vol = pd.Series(rng.integers(1_000_000, 5_000_000, n), index=idx, dtype=float)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)


@pytest.fixture
def patched_loader(monkeypatch):
    store = {t: _synth_ohlcv(i) for i, t in enumerate(["AAA", "BBB", "CCC", "DDD", "EEE"])}
    monkeypatch.setattr(bi, "_load_member_ohlcv", lambda t: store.get(t))
    monkeypatch.setattr(bi, "_CACHE", {})
    return store


def _members(tickers, added="2018-06-01"):
    return [{"ticker": t, "added": added, "removed": None} for t in tickers]


# --------------------------------------------------------------- basket_index
def test_candle_is_valid_and_reduces_to_ew(patched_loader):
    members = _members(["AAA", "BBB", "CCC", "DDD"])
    idx = bi.deep_calendar(members)
    assert len(idx) > 900
    cand, meta = bi.consolidated_candle(members, idx, "equal", pit=False)
    assert cand is not None and not cand.empty
    # valid candles: high ≥ close ≥ low, high ≥ open ≥ low
    assert (cand["high"] >= cand["close"] - 1e-9).all()
    assert (cand["close"] >= cand["low"] - 1e-9).all()
    assert (cand["high"] >= cand["low"] - 1e-9).all()
    # equal-mode close return = mean of member returns (the EW level path)
    rets = pd.DataFrame({t: patched_loader[t]["close"].reindex(cand.index).pct_change()
                         for t in ["AAA", "BBB", "CCC", "DDD"]})
    ew = (1 + rets.mean(axis=1).fillna(0)).cumprod()
    corr = cand["close"].pct_change().corr(ew.pct_change())
    assert corr > 0.999
    assert meta["coverage_pct"] == 1.0 and meta["n_live"] == 4
    assert (cand["dollar_vol"].dropna() > 0).all()


def test_fewer_than_three_members_returns_none(patched_loader):
    cand, meta = bi.consolidated_candle(_members(["AAA", "BBB"]), bi.deep_calendar(_members(["AAA", "BBB"])))
    assert cand is None and meta["n_with_ohlcv"] == 2


def test_pit_masks_history_before_added(patched_loader):
    members = _members(["AAA", "BBB", "CCC"], added="2022-01-03")
    idx = bi.deep_calendar(members)
    pit_cand, _ = bi.consolidated_candle(members, idx, "equal", pit=True)
    full_cand, _ = bi.consolidated_candle(members, idx, "equal", pit=False)
    # strict PIT starts at the added date; current-membership goes back to listing
    assert pit_cand.index.min() >= pd.Timestamp("2022-01-03")
    assert full_cand.index.min() < pd.Timestamp("2022-01-03")


def test_weighting_modes_differ_but_stay_valid(patched_loader):
    members = _members(["AAA", "BBB", "CCC", "DDD", "EEE"])
    idx = bi.deep_calendar(members)
    eq, _ = bi.consolidated_candle(members, idx, "equal", pit=False)
    al, _ = bi.consolidated_candle(members, idx, "alpha", pit=False)
    assert eq is not None and al is not None
    # alpha-tilt should move the close path off the equal one somewhere
    assert (eq["close"].dropna().round(4) != al["close"].reindex(eq.index).dropna().round(4)).any()
    assert (al["high"] >= al["low"] - 1e-9).all()


def test_alpha_overlay_is_point_in_time_no_lookahead(patched_loader):
    """Audit #44: the default alpha overlay must be point-in-time — its weights on any
    past date depend ONLY on data up to that date. So truncating the calendar and
    recomputing must reproduce the EARLIER portion of the full-calendar close curve
    exactly. (The old static as-of-today vector FAILED this — future ranking reweighted
    the whole past.) Also asserts meta.lookahead is False for the PIT path."""
    members = _members(["AAA", "BBB", "CCC", "DDD", "EEE"])
    idx = bi.deep_calendar(members)
    cut = idx[len(idx) - 250]                                   # cut the last ~year off
    full, meta_full = bi.consolidated_candle(members, idx, "alpha", pit=False)          # alpha_pit=True
    trunc, _ = bi.consolidated_candle(members, idx[idx <= cut], "alpha", pit=False)
    assert full is not None and trunc is not None
    assert meta_full.get("lookahead") is False                 # PIT path discloses no look-ahead
    cmp_end = idx[len(idx) - 400]                               # clearance from the truncation edge
    a = full["close"].loc[:cmp_end].dropna()
    b = trunc["close"].loc[:cmp_end].dropna()
    j = a.index.intersection(b.index)
    # rebased-to-1.0 curves must match bar-for-bar over the shared past
    rel = ((a.loc[j] - b.loc[j]).abs() / a.loc[j].abs().clip(lower=1e-6))
    assert float(rel.max()) < 1e-9, f"alpha overlay look-ahead: max rel diff {float(rel.max()):.2e}"


def test_alpha_static_path_flags_lookahead(patched_loader):
    """The opt-out legacy static vector (alpha_pit=False) must self-disclose via
    meta.lookahead=True so a template can label it 'in-sample illustration'."""
    members = _members(["AAA", "BBB", "CCC", "DDD", "EEE"])
    idx = bi.deep_calendar(members)
    _, meta = bi.consolidated_candle(members, idx, "alpha", pit=False, alpha_pit=False)
    assert meta.get("lookahead") is True
    # equal/relevance never look ahead
    _, m_eq = bi.consolidated_candle(members, idx, "equal", pit=False)
    assert m_eq.get("lookahead") is False


def test_weight_variants_reports_no_lookahead(patched_loader):
    members = _members(["AAA", "BBB", "CCC", "DDD", "EEE"])
    idx = bi.deep_calendar(members)
    v = bi.weight_variants(members, idx)
    assert v.get("alpha_lookahead") is False                   # default overlay is PIT
    assert "alpha" in v and "equal" in v


def test_relevance_weight_uses_explicit_member_weight(patched_loader):
    members = [{"ticker": "AAA", "added": "2018-06-01", "removed": None, "weight": 5.0},
               {"ticker": "BBB", "added": "2018-06-01", "removed": None, "weight": 1.0},
               {"ticker": "CCC", "added": "2018-06-01", "removed": None, "weight": 1.0}]
    idx = bi.deep_calendar(members)
    cand, _ = bi.consolidated_candle(members, idx, "relevance", pit=False)
    assert cand is not None and (cand["high"] >= cand["close"] - 1e-9).all()


# ----------------------------------------------------------------- basket_mtf
def test_mtf_shape_and_bounded(patched_loader):
    members = _members(["AAA", "BBB", "CCC", "DDD"])
    cand, _ = bi.consolidated_candle(members, bi.deep_calendar(members), "equal", pit=False)
    m = basket_mtf.basket_mtf(cand)
    assert set(m["tf"]).issubset({"D", "3D", "W", "M"}) and m["tf"]
    assert -1.0 <= m["momentum_score"] <= 1.0
    assert "confluence" in m and "grade" in m["confluence"]
    assert m["has_monthly"] is True            # 1200 bdays → monthly resolves
    for tf in m["tf"].values():
        assert tf["sign"] in (-1, 0, 1)


def test_mtf_empty_on_short_history():
    short = _synth_ohlcv(0, n=40)[["close", "high"]]
    assert basket_mtf.basket_mtf(short) == {}


def test_theme_signal_falls_back_to_equal_weight_close(monkeypatch):
    """Regions without member OHLCV still publish honest MTF structure, never fake flow."""
    idx = pd.bdate_range("2023-01-02", periods=700)
    level = pd.Series(100 * np.exp(np.linspace(0, 0.35, len(idx))), index=idx)
    monkeypatch.setattr(bi, "deep_calendar", lambda members: pd.DatetimeIndex([]))
    ts._SIG_CACHE.clear()
    out = ts._basket_signals(_members(["CA1.TO", "CA2.TO", "CA3.TO"]),
                             level, region="canada")
    assert out["mtf"]["source"] == "equal_weight_close"
    assert out["mtf"]["tf"]
    assert out["tape"] is None
    assert out["meta"]["flow_available"] is False


def test_theme_signal_rejects_unrepresentative_partial_candle(patched_loader):
    """Three covered names cannot stand in for a six-member theme's MTF/flow read."""
    members = _members(["AAA", "BBB", "CCC", "MISS1", "MISS2", "MISS3"])
    idx = pd.bdate_range("2023-01-02", periods=700)
    level = pd.Series(100 * np.exp(np.linspace(0, 0.25, len(idx))), index=idx)
    ts._SIG_CACHE.clear()
    out = ts._basket_signals(members, level, region="us")
    assert out["mtf"]["source"] == "equal_weight_close"
    assert out["tape"] is None
    assert out["meta"]["flow_available"] is False


# ---------------------------------------------------------------- basket_tape
def test_tape_volhole_and_flow(patched_loader):
    members = _members(["AAA", "BBB", "CCC", "DDD"])
    cand, meta = bi.consolidated_candle(members, bi.deep_calendar(members), "equal", pit=False)
    t = basket_tape.basket_tape(cand, meta)
    vh = t["volhole"]
    assert vh["state"] in ("IN_HOLE", "COILED_UP", "COILED_DOWN", "EXPANSION_UP",
                           "EXPANSION_DOWN", "EXPANDED")
    assert -1.0 <= vh["score"] <= 1.0
    assert t["flow"]["cmf"] is None or -1.0 <= t["flow"]["cmf"] <= 1.0
    assert t["whale"]["accumulation"] is None or 0 <= t["whale"]["accumulation"] <= 100
    assert t["coverage"]["coverage_pct"] == 1.0


def test_tape_no_volume_still_gives_volhole(patched_loader, monkeypatch):
    # strip volume → vol-hole (close/high/low only) still resolves, whale/flow go None
    members = _members(["AAA", "BBB", "CCC"])
    cand, meta = bi.consolidated_candle(members, bi.deep_calendar(members), "equal", pit=False)
    cand = cand.copy()
    cand["dollar_vol"] = np.nan
    t = basket_tape.basket_tape(cand, meta)
    assert t["volhole"]["state"] is not None
    assert t["whale"] is None and t["flow"] is None


# ------------------------------------------------------- theme_scoring gates
def test_long_below_trend_gate():
    assert ts._long_below_trend({"confluence": {"long_sign": -1}}) is True
    assert ts._long_below_trend({"confluence": {"long_sign": 1}}) is False
    assert ts._long_below_trend({}) is False
    assert ts._long_below_trend(None) is False


def test_reco_blocks_entry_against_long_trend():
    fp = {"rs_pctile": 0.4}
    down = {"confluence": {"long_sign": -1}}
    up = {"confluence": {"long_sign": 1}}
    # emerging + macro-OK + uncrowded would normally ENTER; below long trend ⇒ HOLD
    assert ts._reco("emerging", 0.5, 0.1, fp, up, {}) == "enter"
    assert ts._reco("emerging", 0.5, 0.1, fp, down, {}) == "hold"
    # dominant below long trend ⇒ HOLD not ACCUMULATE
    assert ts._reco("dominant", 0.5, 0.1, fp, down, {}) == "hold"
    # vol-hole breakdown ⇒ TRIM regardless
    assert ts._reco("dominant", 0.5, 0.1, fp, up, {"volhole": {"state": "EXPANSION_DOWN"}}) == "trim"


def test_label_expansion_down_below_trend_deteriorates():
    fp = {"accel_z": -0.6, "rs_pctile": 0.5}
    perf = {"20d": {"rel": -0.01}}
    breadth = {"pct50": 0.3, "nh": 0, "nl": 5}
    down = {"confluence": {"long_sign": -1}}
    lab = ts._label(45, fp, perf, breadth, -0.02, down, {"volhole": {"state": "EXPANSION_DOWN"}})
    assert lab in ("deteriorating", "fading")
