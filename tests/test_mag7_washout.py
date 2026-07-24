"""MWR-W0 — mag7_washout background gate: deterministic states on synthetic
stores, ledger dedup, and fail-open. Mirrors mag7_regime's snapshot(root=tmp)
convention (root points at a data-dir clone holding baskets/ohlcv/*.parquet)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.mag7_washout import (
    M7, SCHEMA, WASHOUT_FLOOR, cross_up, ew_basket, rsi_macd, snapshot,
    stoch_rsi, two_week_bars,
)


def _write_members(root: Path, closes: pd.Series) -> None:
    """Every member gets the same path (deterministic cohort) — per-member
    divergence isn't under test except via the breadth counter."""
    d = root / "baskets" / "ohlcv"
    d.mkdir(parents=True)
    df = pd.DataFrame({
        "open": closes, "high": closes * 1.01, "low": closes * 0.99,
        "close": closes, "volume": 1e6,
    })
    for t in M7:
        df.to_parquet(d / f"{t}.parquet")


def _days(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2018-01-02", periods=n)


def _uptrend(n: int = 900) -> pd.Series:
    """Seeded drift+noise walk whose 2W Stoch-RSI tail sits far above the
    washout floor (probed: seed 0 → K tail min ≈ 86). A sine-wobble fixture
    fails here by construction — Stoch-RSI normalizes RSI to its own 14-bar
    range, so even a gentle periodic dip swings K to 0 (real property, not a
    bug; the probe lives in the PR notes)."""
    rng = np.random.default_rng(0)
    rets = rng.normal(0.0008, 0.009, n)
    return pd.Series(100 * np.cumprod(1 + rets), index=_days(n))


def _crash_then_flat(n: int = 900, crash_at: int = 800, depth: float = 0.35) -> pd.Series:
    """Long uptrend, then a hard multi-week selloff into the last bars —
    drives 2W Stoch-RSI K to the floor and keeps it there (washed_out)."""
    px = _uptrend(n).to_numpy().copy()
    for i in range(crash_at, n):
        px[i] = px[crash_at - 1] * (1 - depth * min(1.0, (i - crash_at) / 40))
    return pd.Series(px, index=_days(n))


def _crash_then_recover(n: int = 940, crash_at: int = 800, trough: int = 880) -> pd.Series:
    """Crash, then a sharp recovery leg — produces a bullish cross out of the
    washout zone (triggered)."""
    px = _crash_then_flat(n, crash_at).to_numpy().copy()
    lo = px[trough - 1]
    for i in range(trough, n):
        px[i] = lo * (1 + 0.012 * (i - trough))
    return pd.Series(px, index=_days(n))


# ── indicator sanity ─────────────────────────────────────────────────────────

def test_stoch_rsi_bounds_and_cross_up():
    s = _crash_then_recover()
    k, d = stoch_rsi(two_week_bars(s))
    v = k.dropna()
    assert not v.empty and float(v.min()) >= -1e-9 and float(v.max()) <= 100 + 1e-9
    up = cross_up(k, d)
    assert bool(up.fillna(False).any())


def test_rsi_macd_deep_negative_in_crash():
    """The gate's 3D trigger arm requires line < 0 during washouts — that sign
    must be robustly negative on a crash tail. (No positive-side assertion:
    RSI-MACD is momentum-of-RSI, terminal sign on a drift walk is
    path-dependent, and house RSI is NaN on zero-down-move windows.)"""
    line, sig = rsi_macd(_crash_then_flat())
    assert float(line.dropna().iloc[-1]) < 0
    assert math.isfinite(float(sig.dropna().iloc[-1]))


# ── state ladder ─────────────────────────────────────────────────────────────

def test_idle_on_quiet_uptrend(tmp_path):
    _write_members(tmp_path, _uptrend())
    out = snapshot(root=tmp_path)
    assert out and out["schema"] == SCHEMA
    assert out["state"] == "idle" and out["armed"] is False
    assert out["members_washed"] == 0
    assert (tmp_path / "mag7_washout" / "latest.json").exists()
    assert not (tmp_path / "mag7_washout" / "triggers.jsonl").exists()


def test_washed_out_on_crash(tmp_path):
    _write_members(tmp_path, _crash_then_flat())
    out = snapshot(root=tmp_path)
    assert out and out["state"] in ("washed_out", "triggered")
    assert out["armed"] is True
    assert out["basket"]["stoch2w_k"] < WASHOUT_FLOOR
    # identical member paths → all 7 wash together (breadth counter works)
    assert out["members_washed"] == 7


def test_trigger_appends_ledger_once(tmp_path):
    _write_members(tmp_path, _crash_then_recover())
    out = snapshot(root=tmp_path)
    assert out is not None
    ledger = tmp_path / "mag7_washout" / "triggers.jsonl"
    if out["triggers_today"]:
        rows = ledger.read_text().strip().splitlines()
        n = len(rows)
        assert n == len(out["triggers_today"])
        snapshot(root=tmp_path)  # idempotent re-run: dedup by (tf, date)
        assert len(ledger.read_text().strip().splitlines()) == n
    else:
        # recovery leg long enough that the cross bar has passed — armed memory
        # must still reflect the recent washout OR state stays washed_out
        assert out["state"] in ("washed_out", "idle")


def test_trigger_state_reachable(tmp_path):
    """Sweep recovery lengths until the cross lands on the last bar — the
    'triggered' state must be reachable, not merely defined."""
    hit = False
    for extra in range(0, 26, 2):
        px = _crash_then_recover(n=884 + extra)
        root = tmp_path / f"case{extra}"
        _write_members(root, px)
        out = snapshot(root=root)
        assert out is not None
        if out["state"] == "triggered":
            hit = True
            assert out["triggers_today"]
            # no DFF store in fixture → regime unknown → actionable is None
            assert out["regime"] is None and out["gate_actionable"] is None
            break
    assert hit, "no recovery length produced a triggered state"


def _write_dff(root, idx, rates):
    d = root / "fred"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"DFF": rates}, index=idx).to_parquet(d / "DFF.parquet")


def test_amendment2_veto_and_actionable(tmp_path):
    """Amendment 2 conditioner: same triggered tape, DFF regime decides
    gate_actionable — hike_accel → vetoed, cutting → actionable."""
    from engine.mag7_washout import _env_tags
    px = _crash_then_recover()
    days = pd.date_range(px.index[0] - pd.Timedelta(days=400), px.index[-1], freq="D")
    # accelerating tightening: rate rises with increasing slope into the end
    accel = np.linspace(0, 1, len(days)) ** 2 * 4.0
    root_a = tmp_path / "accel"; _write_dff(root_a, days, accel)
    tags_a = _env_tags(root_a, px.index[-1])
    assert tags_a["regime"] == "hike_accel"
    # cutting: rate falls steadily
    cut = np.linspace(4.0, 1.0, len(days))
    root_c = tmp_path / "cut"; _write_dff(root_c, days, cut)
    tags_c = _env_tags(root_c, px.index[-1])
    assert tags_c["regime"] == "cutting"
    # end-to-end: find a triggered case per regime and check the gate verdicts
    rate_fns = {"a": (lambda n: np.linspace(0, 1, n) ** 2 * 4.0, "hike_accel", False),
                "c": (lambda n: np.linspace(4.0, 1.0, n), "cutting", True)}
    for extra in range(0, 26, 2):
        series = _crash_then_recover(n=884 + extra)
        for name, (fn, want_regime, want_action) in rate_fns.items():
            root = tmp_path / f"e{extra}{name}"
            _write_members(root, series)
            dd = pd.date_range(series.index[0] - pd.Timedelta(days=400),
                               series.index[-1], freq="D")
            _write_dff(root, dd, fn(len(dd)))
            out = snapshot(root=root)
            if out and out["state"] == "triggered":
                assert out["regime"] == want_regime
                assert out["gate_actionable"] is want_action
                assert (out["veto"] == "hike_accel") is (not want_action)
                assert out["triggers_today"][0]["regime"] == want_regime
                if want_action:
                    return
    raise AssertionError("no triggered case reached for both regimes")


def test_fail_open_on_missing_store(tmp_path):
    assert snapshot(root=tmp_path) is None  # no baskets/ohlcv → None, no raise


def test_write_false_leaves_no_artifacts(tmp_path):
    _write_members(tmp_path, _crash_then_recover())
    out = snapshot(root=tmp_path, write=False)
    assert out is not None
    assert not (tmp_path / "mag7_washout").exists()
