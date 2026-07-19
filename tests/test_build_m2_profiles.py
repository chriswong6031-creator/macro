"""Unit tests for scripts/build_m2_profiles.py.

Tests are structured so that engine.indicators_m2 is NOT required:
  - _build_ticker_record takes indicator functions as injected parameters.
  - All assertions against per-ticker logic use hand-built stubs.
  - should_recompute, _fingerprint, and _sessions_held are pure fns, no imports.

Integration tests that call the real engine.indicators_m2 fns are gated
behind pytest.importorskip("engine.indicators_m2") and run only when that
module is importable.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Import the script module
# ---------------------------------------------------------------------------
from scripts import build_m2_profiles as bmp


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 200, start: str = "2023-01-01") -> pd.DataFrame:
    """Return a minimal synthetic OHLCV DataFrame with n rows."""
    idx = pd.date_range(start, periods=n, freq="B", name="Date")
    base = np.linspace(100.0, 150.0, n)
    return pd.DataFrame(
        {
            "close": pd.Series(base, index=idx),
            "high": pd.Series(base + 2.0, index=idx),
            "low": pd.Series(base - 2.0, index=idx),
            "volume": pd.Series(np.full(n, 1_000_000.0), index=idx),
        }
    )


# ---------------------------------------------------------------------------
# Stub indicator functions
# ---------------------------------------------------------------------------

def _stub_avwap(df: pd.DataFrame, anchor) -> pd.Series:
    """Returns a constant series equal to the last close value (simple stub)."""
    last_close = float(df["close"].iloc[-1])
    return pd.Series(last_close, index=df.index)


def _stub_earnings_proxy(df: pd.DataFrame, lookback: int = 63) -> int | None:
    """Returns the positional index of the highest-volume bar in the tail."""
    tail = df.tail(lookback)
    if tail.empty:
        return None
    pos_in_tail = int(tail["volume"].values.argmax())
    return int(len(df) - len(tail) + pos_in_tail)


def _stub_week_avwap(df: pd.DataFrame) -> pd.Series:
    """Returns mid-price as a constant-valued series."""
    mid = float((df["close"] + df["high"] + df["low"]).iloc[-1] / 3.0)
    return pd.Series(mid, index=df.index)


def _stub_profile(df: pd.DataFrame, *, window: int = 126, bins: int = 24) -> dict | None:
    """Returns a synthetic volume profile centred around mean close."""
    tail = df.tail(window)
    poc = float(tail["close"].mean())
    va_low = poc * 0.97
    va_high = poc * 1.03
    return {
        "poc": poc,
        "va_low": va_low,
        "va_high": va_high,
        "total_volume": float(tail["volume"].sum()),
        "bin_edges": [va_low, poc, va_high],
        "bin_volumes": [1e6, 2e6, 1e6],
        "window_used": len(tail),
    }


# ---------------------------------------------------------------------------
# Tests — _fingerprint
# ---------------------------------------------------------------------------

class TestFingerprint:
    def test_same_inputs_same_fp(self):
        fp1 = bmp._fingerprint("2026-01-15", ["AAPL", "MSFT"], "m2.v1")
        fp2 = bmp._fingerprint("2026-01-15", ["AAPL", "MSFT"], "m2.v1")
        assert fp1 == fp2

    def test_different_date_different_fp(self):
        fp1 = bmp._fingerprint("2026-01-15", ["AAPL", "MSFT"], "m2.v1")
        fp2 = bmp._fingerprint("2026-01-16", ["AAPL", "MSFT"], "m2.v1")
        assert fp1 != fp2

    def test_different_ticker_set_different_fp(self):
        fp1 = bmp._fingerprint("2026-01-15", ["AAPL", "MSFT"], "m2.v1")
        fp2 = bmp._fingerprint("2026-01-15", ["AAPL", "GOOG"], "m2.v1")
        assert fp1 != fp2

    def test_different_version_different_fp(self):
        fp1 = bmp._fingerprint("2026-01-15", ["AAPL"], "m2.v1")
        fp2 = bmp._fingerprint("2026-01-15", ["AAPL"], "m2.v2")
        assert fp1 != fp2

    def test_fp_is_16_hex_chars(self):
        fp = bmp._fingerprint("2026-01-15", ["AAPL"], "m2.v1")
        assert len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)

    def test_order_of_ticker_list_preserved_in_src(self):
        # contract: caller passes sorted list; different order → different fp
        fp1 = bmp._fingerprint("2026-01-15", ["AAPL", "MSFT"], "m2.v1")
        fp2 = bmp._fingerprint("2026-01-15", ["MSFT", "AAPL"], "m2.v1")
        assert fp1 != fp2


# ---------------------------------------------------------------------------
# Tests — should_recompute
# ---------------------------------------------------------------------------

class TestShouldRecompute:
    _NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)
    _FP = "abc123def456abcd"

    def _meta(self, age_hours: float = 1.0, fp: str = _FP) -> dict:
        computed = self._NOW - timedelta(hours=age_hours)
        return {
            "fingerprint": fp,
            "computed_at": computed.isoformat(),
        }

    def test_no_existing_meta_always_recomputes(self):
        assert bmp.should_recompute(None, self._FP, self._NOW) is True

    def test_empty_meta_recomputes(self):
        assert bmp.should_recompute({}, self._FP, self._NOW) is True

    def test_force_always_recomputes(self):
        meta = self._meta(age_hours=0.1)
        assert bmp.should_recompute(meta, self._FP, self._NOW, force=True) is True

    def test_cache_hit_within_max_age(self):
        meta = self._meta(age_hours=12)   # 12h old < 3d
        assert bmp.should_recompute(meta, self._FP, self._NOW, max_age_d=3) is False

    def test_cache_miss_stale(self):
        meta = self._meta(age_hours=24 * 4)  # 4d old > 3d
        assert bmp.should_recompute(meta, self._FP, self._NOW, max_age_d=3) is True

    def test_cache_miss_fingerprint_mismatch(self):
        meta = self._meta(age_hours=1)
        assert bmp.should_recompute(meta, "different_fp_here_0000", self._NOW) is True

    def test_missing_computed_at_recomputes(self):
        meta = {"fingerprint": self._FP}
        assert bmp.should_recompute(meta, self._FP, self._NOW) is True

    def test_bad_computed_at_format_recomputes(self):
        meta = {"fingerprint": self._FP, "computed_at": "not-a-date"}
        assert bmp.should_recompute(meta, self._FP, self._NOW) is True

    def test_exact_max_age_boundary_is_cache_hit(self):
        meta = self._meta(age_hours=24 * 3)   # exactly 3d → still hit
        assert bmp.should_recompute(meta, self._FP, self._NOW, max_age_d=3) is False


# ---------------------------------------------------------------------------
# Tests — _sessions_held
# ---------------------------------------------------------------------------

class TestSessionsHeld:
    def test_all_above_returns_full_length(self):
        idx = pd.date_range("2026-01-01", periods=5, freq="B")
        close = pd.Series([110.0, 111.0, 112.0, 113.0, 114.0], index=idx)
        avwap = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
        assert bmp._sessions_held(close, avwap) == 5

    def test_none_above_returns_zero(self):
        idx = pd.date_range("2026-01-01", periods=5, freq="B")
        close = pd.Series([90.0, 91.0, 92.0, 93.0, 94.0], index=idx)
        avwap = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
        assert bmp._sessions_held(close, avwap) == 0

    def test_run_from_tail(self):
        # first 3 below, last 2 above → sessions_held = 2
        idx = pd.date_range("2026-01-01", periods=5, freq="B")
        close = pd.Series([90.0, 90.0, 90.0, 105.0, 106.0], index=idx)
        avwap = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
        assert bmp._sessions_held(close, avwap) == 2

    def test_broken_run_at_tail(self):
        # above, below, above → last bar above = 1
        idx = pd.date_range("2026-01-01", periods=3, freq="B")
        close = pd.Series([105.0, 95.0, 103.0], index=idx)
        avwap = pd.Series([100.0, 100.0, 100.0], index=idx)
        assert bmp._sessions_held(close, avwap) == 1

    def test_empty_series_returns_zero(self):
        assert bmp._sessions_held(pd.Series([], dtype=float), pd.Series([], dtype=float)) == 0

    def test_none_inputs_return_zero(self):
        assert bmp._sessions_held(None, None) == 0

    def test_single_bar_above(self):
        idx = pd.date_range("2026-01-01", periods=1, freq="B")
        close = pd.Series([110.0], index=idx)
        avwap = pd.Series([100.0], index=idx)
        assert bmp._sessions_held(close, avwap) == 1


# ---------------------------------------------------------------------------
# Tests — _build_ticker_record (stubbed indicator fns)
# ---------------------------------------------------------------------------

class TestBuildTickerRecord:
    def _record(self, df=None):
        if df is None:
            df = _make_ohlcv(200)
        return bmp._build_ticker_record(
            df,
            avwap_fn=_stub_avwap,
            earnings_proxy_fn=_stub_earnings_proxy,
            week_avwap_fn=_stub_week_avwap,
            profile_fn=_stub_profile,
        )

    def test_record_has_required_keys(self):
        rec = self._record()
        assert "as_of" in rec
        assert "close" in rec
        assert "vwap_w" in rec
        assert "profile" in rec
        assert "avwap" in rec

    def test_avwap_has_all_anchors(self):
        rec = self._record()
        avwap = rec["avwap"]
        assert "earnings_proxy" in avwap
        assert "ytd" in avwap
        assert "low_52w" in avwap

    def test_earnings_proxy_fields(self):
        rec = self._record()
        ep = rec["avwap"]["earnings_proxy"]
        assert "value" in ep
        assert "anchor_date" in ep
        assert "sessions_since" in ep
        assert "sessions_held" in ep
        assert "dist_pct" in ep

    def test_as_of_is_last_bar_date(self):
        df = _make_ohlcv(200, start="2024-01-01")
        rec = self._record(df)
        assert rec["as_of"] == str(df.index[-1].date())

    def test_close_rounded_to_4dp(self):
        rec = self._record()
        c = rec["close"]
        assert c is not None
        # round-trip: 4 decimal places max
        assert round(c, 4) == c

    def test_profile_poc_dist_pct_formula(self):
        df = _make_ohlcv(200)
        rec = self._record(df)
        prof = rec["profile"]
        assert prof is not None
        last_close = float(df["close"].iloc[-1])
        poc = prof["poc"]
        if poc:
            expected = round((last_close / poc - 1) * 100, 2)
            assert abs((prof["poc_dist_pct"] or 0) - expected) < 1e-6

    def test_in_value_area_is_bool_or_none(self):
        rec = self._record()
        iva = rec["profile"]["in_value_area"]
        assert iva is None or isinstance(iva, bool)

    def test_vwap_w_not_none_for_sufficient_data(self):
        rec = self._record(_make_ohlcv(200))
        assert rec["vwap_w"] is not None

    def test_ytd_anchor_date_is_first_bar_of_year(self):
        df = _make_ohlcv(300, start="2025-01-01")
        rec = bmp._build_ticker_record(
            df,
            avwap_fn=_stub_avwap,
            earnings_proxy_fn=_stub_earnings_proxy,
            week_avwap_fn=_stub_week_avwap,
            profile_fn=_stub_profile,
        )
        ytd = rec["avwap"]["ytd"]
        assert ytd["anchor_date"] is not None
        # anchor year must be a year present in the index
        year = int(ytd["anchor_date"][:4])
        assert year in df.index.year.unique()

    def test_profile_window_field_is_126(self):
        rec = self._record()
        assert rec["profile"]["window"] == 126

    def test_sessions_held_is_non_negative_int(self):
        rec = self._record()
        held = rec["avwap"]["earnings_proxy"]["sessions_held"]
        assert isinstance(held, int)
        assert held >= 0

    def test_null_profile_when_fn_returns_none(self):
        df = _make_ohlcv(200)
        rec = bmp._build_ticker_record(
            df,
            avwap_fn=_stub_avwap,
            earnings_proxy_fn=_stub_earnings_proxy,
            week_avwap_fn=_stub_week_avwap,
            profile_fn=lambda df, **kw: None,  # always returns None
        )
        assert rec["profile"] is None

    def test_null_earnings_proxy_when_fn_returns_none(self):
        df = _make_ohlcv(200)
        rec = bmp._build_ticker_record(
            df,
            avwap_fn=_stub_avwap,
            earnings_proxy_fn=lambda df, lookback=63: None,
            week_avwap_fn=_stub_week_avwap,
            profile_fn=_stub_profile,
        )
        ep = rec["avwap"]["earnings_proxy"]
        assert ep["value"] is None
        assert ep["sessions_held"] == 0


# ---------------------------------------------------------------------------
# Tests — _round_or_null
# ---------------------------------------------------------------------------

class TestRoundOrNull:
    def test_normal_float(self):
        assert bmp._round_or_null(3.14159, 4) == 3.1416

    def test_none_returns_none(self):
        assert bmp._round_or_null(None) is None

    def test_nan_returns_none(self):
        assert bmp._round_or_null(float("nan")) is None

    def test_inf_returns_none(self):
        assert bmp._round_or_null(float("inf")) is None

    def test_zero_is_not_null(self):
        assert bmp._round_or_null(0.0) == 0.0


# ---------------------------------------------------------------------------
# Integration tests — require engine.indicators_m2
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def m2():
    """Import engine.indicators_m2, skip module if not present."""
    return pytest.importorskip("engine.indicators_m2")


class TestRealIndicatorsM2:
    """Smoke-tests that run against the real engine module when available."""

    def test_build_record_with_real_fns(self, m2):
        df = _make_ohlcv(250)
        rec = bmp._build_ticker_record(
            df,
            avwap_fn=m2.anchored_vwap,
            earnings_proxy_fn=m2.earnings_proxy_anchor,
            week_avwap_fn=m2.week_anchored_vwap,
            profile_fn=m2.volume_profile,
        )
        # basic shape checks
        assert rec["as_of"] == str(df.index[-1].date())
        assert rec["close"] == bmp._round_or_null(float(df["close"].iloc[-1]), 4)
        assert "avwap" in rec
        assert "profile" in rec

    def test_anchored_vwap_nan_before_anchor(self, m2):
        df = _make_ohlcv(100)
        anchor = 50
        series = m2.anchored_vwap(df, anchor)
        assert pd.isna(series.iloc[:anchor]).all(), "expected NaN before anchor"
        assert not pd.isna(series.iloc[anchor]), "expected non-NaN at anchor"

    def test_earnings_proxy_returns_int_or_none(self, m2):
        df = _make_ohlcv(100)
        result = m2.earnings_proxy_anchor(df)
        assert result is None or isinstance(result, int)

    def test_volume_profile_returns_required_keys(self, m2):
        df = _make_ohlcv(200)
        prof = m2.volume_profile(df, window=126, bins=24)
        if prof is not None:
            for key in ("poc", "va_low", "va_high", "total_volume", "bin_edges",
                        "bin_volumes", "window_used"):
                assert key in prof, f"missing key: {key}"

    def test_week_anchored_vwap_same_length_as_input(self, m2):
        df = _make_ohlcv(150)
        series = m2.week_anchored_vwap(df)
        assert len(series) == len(df)
