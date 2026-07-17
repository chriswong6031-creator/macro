"""International performance/rotation engine tests (engine/intl_performance.py).

Synthetic closes (real config ticker names) exercise the USD-conversion math, the
exact equity/FX decomposition identity, the RRG quadrant logic and the correlation
matrix shape; a light smoke test runs the full panel against the committed store.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import intl_performance as P  # noqa: E402


def _synth_closes(n: int = 400, seed: int = 1) -> pd.DataFrame:
    idx = pd.bdate_range("2023-06-01", periods=n)
    rng = np.random.default_rng(seed)
    specs = {
        "^N225": 0.0006, "USDJPY=X": 0.0004,    # yen weakening (USD/JPY drifts up)
        "^KS11": 0.0005, "USDKRW=X": 0.0003,
        "^TWII": 0.0004, "USDTWD=X": 0.0001,
        "^FTSE": 0.0002, "GBPUSD=X": -0.0001,
        "^STOXX": 0.0003, "EURUSD=X": 0.00005,
    }
    cols = {}
    for t, dr in specs.items():
        r = rng.normal(dr, 0.008, n)
        cols[t] = pd.Series(100.0 * np.exp(np.cumsum(r)), index=idx)
    return pd.DataFrame(cols)


def test_usd_series_orientation():
    """USD/XXX pairs (fx_invert) DIVIDE; XXX/USD pairs MULTIPLY."""
    idx = pd.bdate_range("2024-01-01", periods=80)
    closes = pd.DataFrame({
        "^N225": pd.Series(30000.0, index=idx), "USDJPY=X": pd.Series(150.0, index=idx),   # JP: divide
        "^FTSE": pd.Series(8000.0, index=idx), "GBPUSD=X": pd.Series(1.25, index=idx),      # GB: multiply
    })
    jp = P.usd_series("JP", closes)
    gb = P.usd_series("GB", closes)
    assert abs(float(jp.iloc[-1]) - 200.0) < 1e-6      # 30000 / 150
    assert abs(float(gb.iloc[-1]) - 10000.0) < 1e-6    # 8000 * 1.25


def test_usd_decomposition_is_exact():
    """For every market & horizon: usd == local + fx (to within 1dp rounding)."""
    board = P.usd_leaderboard(_synth_closes())
    assert board, "leaderboard empty"
    for r in board:
        for h, x in r["returns"].items():
            assert abs(x["usd"] - (x["local"] + x["fx"])) <= 0.11, (r["cc"], h, x)


def test_local_leg_measured_on_usd_calendar():
    """Regression for the window-mismatch bug: the equity leg must be measured over
    the SAME dates as the USD leg even when the index and FX trade on different
    calendars (here FX skips Fridays, so its calendar is sparser than the index)."""
    idx_full = pd.bdate_range("2023-01-02", periods=420)       # Mon-Fri
    fx_idx = idx_full[idx_full.weekday != 4]                    # drop Fridays -> sparser
    rng = np.random.default_rng(7)
    n225 = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.008, len(idx_full)))), index=idx_full)
    jpy = pd.Series(150.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.006, len(fx_idx)))), index=fx_idx)
    closes = pd.concat([n225.rename("^N225"), jpy.rename("USDJPY=X")], axis=1)
    board = P.usd_leaderboard(closes)
    jp = next(r for r in board if r["cc"] == "JP")
    usd = P.usd_series("JP", closes)
    loc = P._local_aligned("JP", usd, closes)
    for h, n in (("3m", 63), ("12m", 252)):
        if h not in jp["returns"]:
            continue
        # the USD-leg and local-leg windows share endpoints (same calendar)
        assert usd.index[-1] == loc.index[-1]
        assert usd.index[-1 - n] == loc.index[-1 - n]
        # and the reported local return equals the index return over those exact dates
        expected = round((loc.iloc[-1] / loc.iloc[-1 - n] - 1.0) * 100.0, 1)
        assert abs(jp["returns"][h]["local"] - expected) <= 0.11


def test_leaderboard_sorted_desc_by_12m():
    board = P.usd_leaderboard(_synth_closes())
    vals = [r["returns"]["12m"]["usd"] for r in board if "12m" in r["returns"]]
    assert vals == sorted(vals, reverse=True)


def test_yen_weakness_is_a_drag():
    """With a strictly-rising USD/JPY, Japan's USD return must trail its local return."""
    idx = pd.bdate_range("2024-01-01", periods=300)
    arange = np.arange(300)
    closes = pd.DataFrame({
        "^N225": pd.Series(100.0 * 1.001 ** arange, index=idx),     # local index up +0.1%/d
        "USDJPY=X": pd.Series(150.0 * 1.0005 ** arange, index=idx),  # yen weakening every day
    })
    board = P.usd_leaderboard(closes)
    jp = next(r for r in board if r["cc"] == "JP")
    h = jp["returns"]["12m"]
    assert h["fx"] < 0 and h["usd"] < h["local"]


def test_relative_to_us_quadrants():
    closes = _synth_closes()
    bench = pd.Series(  # flat-ish US benchmark so intl up-drift reads as "leading"
        100.0 * np.exp(np.cumsum(np.random.default_rng(9).normal(0.0, 0.006, 400))),
        index=closes.index)
    rrg = P.relative_to_us(closes, bench=bench)
    assert rrg is not None and rrg["n"] >= 1
    valid = {"lead", "weak", "impr", "lag"}
    for row in rrg["rows"]:
        assert row["q"] in valid
        # quadrant must agree with the (level, momentum) coordinates it was placed by
        if row["q"] == "lead":
            assert row["rs_level"] >= 100 and row["rs_mom"] >= 0
        if row["q"] == "lag":
            assert row["rs_level"] < 100 and row["rs_mom"] < 0
    assert rrg["tilt"] in {"ex_us", "us", "mixed"}


def test_correlation_matrix_symmetry_and_diagonal():
    closes = _synth_closes()
    bench = pd.Series(100.0 * np.exp(np.cumsum(
        np.random.default_rng(3).normal(0.0003, 0.007, 400))), index=closes.index)
    cm = P.correlation_matrix(closes, bench=bench)
    assert cm is not None
    n = len(cm["order"])
    assert "US" in cm["order"]
    for i in range(n):
        assert cm["cells"][i][i] == 1.0                       # diagonal
        for j in range(n):
            a, b = cm["cells"][i][j], cm["cells"][j][i]
            if a is not None and b is not None:
                assert abs(a - b) < 1e-9                       # symmetric
            if a is not None:
                assert -1.0001 <= a <= 1.0001
    assert -1.0 <= cm["avg_offdiag"] <= 1.0


def test_risk_appetite_bounds():
    ra = P.risk_appetite(_synth_closes())
    assert ra is not None
    assert 0 <= ra["score"] <= 100
    assert ra["label_en"] in {"Risk-on", "Neutral", "Risk-off"}
    assert ra["tone"] in {"up", "flat", "down"}


def test_degrade_on_empty():
    empty = pd.DataFrame()
    assert P.usd_leaderboard(empty) == []
    assert P.correlation_matrix(empty, bench=None) is None or True  # must not raise


def test_global_read_is_bilingual_text():
    closes = _synth_closes()
    board = P.usd_leaderboard(closes)
    records = [{"cc": "JP", "name": "Japan", "name_zh": "日本", "quad_name": "Goldilocks"},
               {"cc": "GB", "name": "United Kingdom", "name_zh": "英国", "quad_name": "Reflation"}]
    gr = P.global_read(records, board, None, None)
    assert gr["en"] and gr["zh"]
    # quad label is plain-worded at composition (Design Doctrine Law 2; ITR W1) —
    # the raw "Goldilocks" token must NOT reach the glance tier
    assert "Goldilocks" not in gr["en"]
    assert "growth OK, inflation calm" in gr["en"]
    assert "增长尚可、通胀温和" in gr["zh"]


def test_performance_panel_smoke():
    """Full panel against the committed store — structure only (no network)."""
    panel = P.performance_panel()
    assert "leaderboard" in panel and "horizons" in panel
    assert {h["key"] for h in panel["horizons"]} >= {"1m", "3m", "12m", "ytd"}
    if panel["leaderboard"]:
        r = panel["leaderboard"][0]
        assert "returns" in r and "spark" in r
