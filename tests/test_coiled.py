"""Tests for engine/coiled.py — synthetic data only, no network/file I/O.

Spec: research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md §8 ledger (2026-07-01)
      research/entry_timing/WAVE2_REPORT.md
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

# ── path bootstrap for direct test invocation ────────────────────────────────
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import coiled  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_series(values, start="2015-01-02", freq="B"):
    idx = pd.bdate_range(start=start, periods=len(values), freq="B")
    return pd.Series(values, index=idx, dtype=float)


def _noisy(n, base=100.0, sigma=0.5, seed=42):
    rng = np.random.default_rng(seed)
    log_r = rng.normal(0, sigma / 100, n)
    prices = base * np.cumprod(1 + log_r)
    return _make_series(prices)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. washout_ctx
# ═══════════════════════════════════════════════════════════════════════════════

class TestWashoutCtx:
    def test_true_after_crash(self):
        """Series rises to 100, crashes >35%, then chops flat for 40 bars."""
        # build: 250 bars rising to 100, then crash 36%, then 40 bars of chop
        rise = list(np.linspace(50, 100, 250))
        crash = [100 * (1 - 0.36 * (i / 30)) for i in range(30)]  # 30-bar decline
        chop = [crash[-1] * (1 + 0.001 * ((-1) ** i)) for i in range(40)]
        prices = rise + crash + chop
        c = _make_series(prices)
        result = coiled.washout_ctx(c)
        assert result is True, f"Expected True for crash series, got {result}"

    def test_false_monotone_uptrend(self):
        """Monotone uptrend: no washout possible."""
        prices = np.linspace(10, 200, 400)
        c = _make_series(prices)
        result = coiled.washout_ctx(c)
        assert result is False, f"Expected False for monotone uptrend, got {result}"

    def test_none_insufficient_bars(self):
        """Fewer than 308 bars returns None."""
        c = _noisy(200)
        result = coiled.washout_ctx(c)
        assert result is None, f"Expected None for short series, got {result}"

    def test_never_raises(self):
        """Should never raise regardless of input."""
        for n in [0, 1, 50, 308]:
            c = _noisy(n) if n > 0 else pd.Series([], dtype=float)
            try:
                coiled.washout_ctx(c)
            except Exception as e:
                pytest.fail(f"washout_ctx raised on n={n}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. weekly_d_last
# ═══════════════════════════════════════════════════════════════════════════════

class TestWeeklyDLast:
    def test_float_in_range_on_400_bars(self):
        """400 bars of noisy data -> float in [0, 100]."""
        c = _noisy(400, sigma=1.0)
        result = coiled.weekly_d_last(c)
        assert result is not None, "Expected a float, got None"
        assert isinstance(result, float)
        assert 0.0 <= result <= 100.0, f"D value {result} out of [0, 100]"

    def test_none_on_50_bars(self):
        """50 bars is far below 60 weekly bars -> None."""
        c = _noisy(50)
        result = coiled.weekly_d_last(c)
        assert result is None, f"Expected None on 50 bars, got {result}"

    def test_never_raises(self):
        for n in [0, 5, 50, 200, 400]:
            c = _noisy(n) if n > 0 else pd.Series([], dtype=float)
            try:
                coiled.weekly_d_last(c)
            except Exception as e:
                pytest.fail(f"weekly_d_last raised on n={n}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. cohort_fractions
# ═══════════════════════════════════════════════════════════════════════════════

class TestCohortFractions:
    def _make_sector_map(self, tickers, sector):
        return {t: sector for t in tickers}

    def test_fraction_7_peers_3_below_30(self):
        """8-ticker sector; focal ticker excluded from its own peers -> 7 peers, 3 below 30.
        Expected frac = 3/7 ≈ 0.4286."""
        tickers = ["A", "B", "C", "D", "E", "F", "G", "H"]
        # B, C, D below 30; E, F, G, H >= 30; A is the focal ticker (d=50, irrelevant)
        latest_d = {"A": 50.0, "B": 25.0, "C": 20.0, "D": 28.0,
                    "E": 45.0, "F": 60.0, "G": 70.0, "H": 80.0}
        sector_of = self._make_sector_map(tickers, "Tech")
        result = coiled.cohort_fractions(latest_d, sector_of)
        frac_A = result.get("A")
        assert frac_A is not None, "Expected a fraction for A, got None"
        expected = 3 / 7
        assert abs(frac_A - expected) < 1e-9, f"Expected {expected:.6f}, got {frac_A:.6f}"

    def test_none_when_fewer_than_5_peers(self):
        """3-ticker sector with d values: only 2 peers -> None (min_peers=5)."""
        latest_d = {"X": 20.0, "Y": 25.0, "Z": 80.0}
        sector_of = {"X": "A", "Y": "A", "Z": "A"}
        result = coiled.cohort_fractions(latest_d, sector_of)
        assert result.get("X") is None, f"Expected None with 2 peers, got {result.get('X')}"

    def test_self_excluded(self):
        """Ticker A has d=5 (below 30). When counting A's peers, A itself is excluded."""
        # 6 tickers, sector S; A has d=5, rest have d=80. Without self-exclusion A would
        # count toward its own fraction.  With self-exclusion: 5 peers, all d=80 -> frac=0
        tickers = ["A", "B", "C", "D", "E", "F"]
        latest_d = {t: 80.0 for t in tickers}
        latest_d["A"] = 5.0
        sector_of = self._make_sector_map(tickers, "S")
        result = coiled.cohort_fractions(latest_d, sector_of)
        # A's peers = B..F (5 peers), all d=80 >= 30 -> frac = 0.0
        assert result.get("A") == 0.0, f"Expected 0.0, got {result.get('A')}"
        # B's peers include A (d=5 < 30) and 4 others (d=80) -> frac = 1/5
        assert abs(result.get("B") - 1 / 5) < 1e-9, f"B frac unexpected: {result.get('B')}"

    def test_none_sector_not_in_map(self):
        """Ticker with None sector -> None fraction."""
        latest_d = {"X": 20.0, "Y": 25.0, "Z": 30.0}
        sector_of = {"X": None, "Y": "S", "Z": "S"}
        result = coiled.cohort_fractions(latest_d, sector_of)
        assert result.get("X") is None

    def test_never_raises(self):
        try:
            coiled.cohort_fractions({}, {})
            coiled.cohort_fractions({"A": None}, {"A": None})
        except Exception as e:
            pytest.fail(f"cohort_fractions raised: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. assess
# ═══════════════════════════════════════════════════════════════════════════════

class TestAssess:
    def test_bonus_zero_when_not_coiled(self):
        r = coiled.assess(washout=False, cohort_frac=0.6, div=True)
        assert r["coiled"] is False
        assert r["star"] is False
        assert r["bonus"] == 0.0

    def test_bonus_zero_when_no_cohort(self):
        r = coiled.assess(washout=True, cohort_frac=None, div=True)
        assert r["coiled"] is False
        assert r["bonus"] == 0.0

    def test_bonus_coiled_only(self):
        """washout=True, cohort>=0.40, div=False -> coiled only, bonus=COILED_BONUS."""
        r = coiled.assess(washout=True, cohort_frac=0.50, div=False)
        assert r["coiled"] is True
        assert r["star"] is False
        assert abs(r["bonus"] - coiled.COILED_BONUS) < 1e-9, f"bonus={r['bonus']}"

    def test_bonus_star(self):
        """washout=True, cohort>=0.40, div=True -> star, bonus=COILED_BONUS+STAR_EXTRA."""
        r = coiled.assess(washout=True, cohort_frac=0.50, div=True)
        assert r["coiled"] is True
        assert r["star"] is True
        expected = coiled.COILED_BONUS + coiled.STAR_EXTRA
        assert abs(r["bonus"] - expected) < 1e-9, f"bonus={r['bonus']}, expected={expected}"
        assert abs(expected - 0.40) < 1e-9, "COILED+STAR should be 0.40"

    def test_json_safe(self):
        """assess() output must survive json.dumps with allow_nan=False."""
        for washout, cohort, div in [
            (None, None, False),
            (True, 0.5, True),
            (False, 0.0, False),
            (True, None, True),
        ]:
            r = coiled.assess(washout, cohort, div)
            try:
                json.dumps(r, allow_nan=False)
            except (ValueError, TypeError) as e:
                pytest.fail(f"json.dumps failed for assess({washout},{cohort},{div}): {e}")

    def test_washout_none_propagates(self):
        r = coiled.assess(washout=None, cohort_frac=0.8, div=True)
        assert r["coiled"] is False
        assert r["washout_ctx"] is None

    def test_cohort_threshold_boundary(self):
        """cohort_frac=0.40 is exactly at threshold -> coiled=True."""
        r = coiled.assess(washout=True, cohort_frac=0.40, div=False)
        assert r["coiled"] is True
        """cohort_frac=0.399 is just below -> coiled=False."""
        r2 = coiled.assess(washout=True, cohort_frac=0.399, div=False)
        assert r2["coiled"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 5. bull_div
# ═══════════════════════════════════════════════════════════════════════════════

class TestBullDiv:
    def test_returns_bool(self):
        """Must return a bool on any input."""
        for n in [30, 100, 300]:
            c = _noisy(n)
            r = coiled.bull_div(c)
            assert isinstance(r, bool), f"Expected bool, got {type(r)} for n={n}"

    def test_does_not_raise_short_series(self):
        """Should not raise on 30-bar series."""
        c = _noisy(30)
        try:
            coiled.bull_div(c)
        except Exception as e:
            pytest.fail(f"bull_div raised on 30 bars: {e}")

    def test_does_not_raise_monotone(self):
        """Should not raise on monotone uptrend."""
        c = _make_series(np.linspace(10, 200, 300))
        try:
            coiled.bull_div(c)
        except Exception as e:
            pytest.fail(f"bull_div raised on monotone series: {e}")

    def test_does_not_raise_v_shape(self):
        """Should not raise on V-shape series."""
        down = np.linspace(100, 50, 100)
        up = np.linspace(50, 120, 150)
        c = _make_series(np.concatenate([down, up]))
        try:
            coiled.bull_div(c)
        except Exception as e:
            pytest.fail(f"bull_div raised on V-shape: {e}")

    def test_deterministic_divergence_case(self):
        """Craft a series where price makes a lower low at the second trough,
        but the 3D stoch D is higher at the second trough (bullish divergence).

        Construction:
          Phase 1 (300 bars): oscillating uptrend (sine+trend) — gives RSI real
                              variation so StochRSI's hi/lo window is non-trivial;
                              a monotone uptrend pins RSI at 100 and makes stoch
                              denominator zero for all warmup bars.
          Phase 2 (20 bars):  decline to 62 (approaching L1)
          L1 (1 bar):         price=60 — deep oversold (D(3D) ≈ 0 after a long decline)
          Phase 3 (20 bars):  recovery to 100 — oscillator gets time to partially recover
          Phase 4 (20 bars):  second decline to 43 (approaching L2)
          L2 (1 bar):         price=40 < 60 (price lower low)
          Phase 5 (8 bars):   recovery to 58 — provides the >5 confirmation bars needed
                              for L2 to qualify as a confirmed swing low (w=5)

        Mechanism for divergence:
          At L1=60, price fell a long way and D(3D) ≈ 0 (deeply pinned).
          Phase 3 gives the oscillator time to recover toward mid-range before Phase 4.
          Phase 4 is the same length but starts from 100 (vs 200 at Phase 2 onset),
          so the RSI has already started recovering; it doesn't pin as low at L2.
          Result: D(3D) at L2 > D(3D) at L1 despite price[L2] < price[L1].

        Verified empirically: with this construction, swing lows land at daily positions
        ~320 (L1=60) and ~361 (L2=40) in a 370-bar series. Both within the last 120 bars.
        d3 at L1 ≈ 0.0, d3 at L2 ≈ 54.2 → stoch divergence fires True.
        """
        n_warmup = 300
        t = np.linspace(0, 4 * np.pi, n_warmup)  # 2 full sine cycles over the warmup
        end_warmup_price = 100 + 50 * 1.0         # final warmup level ≈ 150
        warmup = 100 + 50 * np.arange(n_warmup) / n_warmup + 15 * np.sin(t)

        dec1    = np.linspace(warmup[-1], 62, 20)
        trough1 = np.array([60.0])               # L1: single minimum at 60
        rec1    = np.linspace(62, 100, 20)        # oscillator recovers during this phase
        dec2    = np.linspace(100, 43, 20)        # second decline (same length)
        trough2 = np.array([40.0])               # L2: lower low (40 < 60)
        rec2    = np.linspace(43, 58, 8)          # 8 bars — gives >5 confirmation bars

        prices = np.concatenate([warmup, dec1, trough1, rec1, dec2, trough2, rec2])
        c = _make_series(prices, start="2010-01-04")

        result = coiled.bull_div(c)
        assert result is True, (
            "Expected bull_div=True for crafted divergence series. "
            "price[L2]=40 < price[L1]=60 (price LL) AND d3(3D) at L2 > d3(3D) at L1 "
            "(stoch HL after oscillator partial recovery during Phase 3). "
            "n=370, L1≈320, L2≈361, d3[L1]≈0, d3[L2]≈54."
        )
