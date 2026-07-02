"""Tests for W1.3 — Dual-Basis Price Store.

Spec: research/cycle_masterplan/D4_SUBSTRATE.md §2 + §2.3 (invariance gate)
      research/cycle_masterplan/D4_SUBSTRATE.md §2.6 (read API)
"""
from __future__ import annotations

import datetime
import io
import textwrap

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_spy_frame(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """Synthetic SPY-like parquet with close + close_price + volume."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n)
    # TR grows slightly faster than price (simulating dividend reinvestment)
    price = 300.0 * np.cumprod(1 + rng.normal(0.0003, 0.01, n))
    # TR = price * cumulative dividend factor (grows ~5% pa relative to price)
    tr = price * np.linspace(1.0, 1.1, n)
    return pd.DataFrame({
        "close":       tr.astype("float64"),
        "close_price": price.astype("float64"),
        "volume":      rng.integers(1_000_000, 50_000_000, n).astype("float64"),
    }, index=idx)


def _make_xlu_frame(n: int = 500, seed: int = 7) -> pd.DataFrame:
    """XLU-like frame where price and TR diverge more FURTHER BACK in time.

    In real dividend-paying ETFs, the TR (Adj Close) has grown larger relative
    to the unadjusted price over the full history because all prior dividends
    have been reinvested.  At the most-recent date the ratio is 1.0 (today's
    price equals today's TR before any future dividend); further back in time
    the ratio is >1.0 (TR is higher because it includes all future-reinvested
    dividends back-adjusted into the series).  We model this by making the
    adjustment factor decrease from 1.14 (oldest) to 1.0 (newest).
    """
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2019-01-01", periods=n)
    price = 40.0 * np.cumprod(1 + rng.normal(0.0001, 0.008, n))
    # Adjustment factor: 1.14 at earliest date, 1.0 at latest date
    # (oldest history has accumulated the most dividend reinvestment)
    adj_factor = np.linspace(1.14, 1.0, n)
    tr = price * adj_factor
    return pd.DataFrame({
        "close":       tr.astype("float64"),
        "close_price": price.astype("float64"),
        "volume":      rng.integers(500_000, 20_000_000, n).astype("float64"),
    }, index=idx)


def _make_legacy_frame(n: int = 100, seed: int = 1) -> pd.DataFrame:
    """Pre-W1.3 frame: only close + volume (no close_price)."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-01", periods=n)
    close = 100.0 * np.cumprod(1 + rng.normal(0.0002, 0.01, n))
    return pd.DataFrame({
        "close":  close.astype("float64"),
        "volume": rng.integers(1_000_000, 10_000_000, n).astype("float64"),
    }, index=idx)


# ---------------------------------------------------------------------------
# T1 — Default-basis byte-identity
# ---------------------------------------------------------------------------

class TestDefaultBasisByteIdentity:
    """yahoo_closes() with no arg (basis='tr') returns the same close series
    as before W1.3.  We mock store.read to return a dual-column frame and
    assert only the 'close' column is returned."""

    def test_default_basis_returns_tr_column(self, tmp_path, monkeypatch):
        """yahoo_closes() default returns close (TR) — byte-identical to pre-W1.3."""
        spy_frame = _make_spy_frame()

        import lib.store as st
        monkeypatch.setattr(st, "read", lambda group, name: spy_frame if name == "SPY" else None)

        import lib.config as cfg
        monkeypatch.setattr(cfg, "load", lambda: {
            "yahoo": {"tickers": {"equity": ["SPY"]}},
        })

        from engine.inputs import yahoo_closes
        df = yahoo_closes()  # no basis arg → default "tr"
        assert "SPY" in df.columns
        pd.testing.assert_series_equal(df["SPY"], spy_frame["close"].rename("SPY"),
                                       check_names=False)

    def test_default_basis_ignores_close_price(self, tmp_path, monkeypatch):
        """Default call must NOT substitute close_price for close."""
        spy_frame = _make_spy_frame()

        import lib.store as st
        monkeypatch.setattr(st, "read", lambda g, n: spy_frame if n == "SPY" else None)

        import lib.config as cfg
        monkeypatch.setattr(cfg, "load", lambda: {
            "yahoo": {"tickers": {"equity": ["SPY"]}},
        })

        from engine.inputs import yahoo_closes
        df_tr = yahoo_closes(basis="tr")
        df_px = yahoo_closes(basis="price")

        # TR and price series must NOT be identical for a dividend-paying name
        assert not df_tr["SPY"].equals(df_px["SPY"]), \
            "TR and price series should differ for a dividend-paying name"


# ---------------------------------------------------------------------------
# T2 — Dual-column alignment
# ---------------------------------------------------------------------------

class TestDualColumnAlignment:
    """close and close_price share the same DatetimeIndex with no NaN holes
    introduced relative to close."""

    def test_same_index_no_nan_holes(self, monkeypatch):
        """close_price has the same DatetimeIndex as close, no extra NaNs."""
        xlu_frame = _make_xlu_frame()

        import lib.store as st
        monkeypatch.setattr(st, "read", lambda g, n: xlu_frame if n == "XLU" else None)

        import lib.config as cfg
        monkeypatch.setattr(cfg, "load", lambda: {
            "yahoo": {"tickers": {"equity": ["XLU"]}},
        })

        from engine.inputs import yahoo_closes
        df_tr = yahoo_closes(basis="tr")
        df_px = yahoo_closes(basis="price")

        assert df_tr.index.equals(df_px.index), "Indexes must be identical"
        # close_price must not have MORE NaNs than close
        tr_nan = df_tr["XLU"].isna().sum()
        px_nan = df_px["XLU"].isna().sum()
        assert px_nan <= tr_nan, f"close_price has more NaNs ({px_nan}) than close ({tr_nan})"


# ---------------------------------------------------------------------------
# T3 — Dividend-heavy ETF divergence grows back in time
# ---------------------------------------------------------------------------

class TestXluDivergenceGrowsBackInTime:
    """For XLU, |close - close_price| is larger further back in history
    (dividend reinvestment compounds)."""

    def test_divergence_grows_back_in_time(self, monkeypatch):
        """XLU close_price < close, and the gap is larger in early history."""
        xlu_frame = _make_xlu_frame(n=500)

        import lib.store as st
        monkeypatch.setattr(st, "read", lambda g, n: xlu_frame if n == "XLU" else None)

        import lib.config as cfg
        monkeypatch.setattr(cfg, "load", lambda: {
            "yahoo": {"tickers": {"equity": ["XLU"]}},
        })

        from engine.inputs import yahoo_closes
        df_tr = yahoo_closes(basis="tr")
        df_px = yahoo_closes(basis="price")

        gap = (df_tr["XLU"] - df_px["XLU"]).abs()

        # Gap at the first 10% of history must be greater than at the last 10%
        first_tenth = gap.iloc[:len(gap) // 10].mean()
        last_tenth = gap.iloc[-len(gap) // 10:].mean()
        assert first_tenth > last_tenth, (
            f"Expected divergence to grow back in time: "
            f"first_tenth={first_tenth:.4f} last_tenth={last_tenth:.4f}"
        )

        # close_price must not equal close for a dividend-heavy name
        # (at least some rows must differ — the dividend adjustment factor != 1.0
        # for the majority of the series)
        pct_different = (df_px["XLU"] != df_tr["XLU"]).mean()
        assert pct_different > 0.9, \
            f"close_price should differ from close (TR) for most of XLU history, got {pct_different:.2f}"


# ---------------------------------------------------------------------------
# T4 — Collector idempotence
# ---------------------------------------------------------------------------

class TestCollectorIdempotence:
    """Running the collector frame through upsert twice must add nothing."""

    def test_double_upsert_adds_nothing(self, tmp_path, monkeypatch):
        """A second upsert of the same frame leaves the parquet unchanged."""
        import lib.config as cfg
        monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)

        from lib import store as st
        frame = _make_spy_frame(n=50)

        # First upsert
        merged1 = st.upsert("yahoo", "SPY", frame, overwrite_overlap=True)
        # Second upsert of the same data
        merged2 = st.upsert("yahoo", "SPY", frame, overwrite_overlap=True)

        # Shape must not change
        assert merged1.shape == merged2.shape
        # Values must be identical
        pd.testing.assert_frame_equal(merged1, merged2)

    def test_incremental_upsert_appends_only_new(self, tmp_path, monkeypatch):
        """Upserting a newer window does not change older rows."""
        import lib.config as cfg
        monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)

        from lib import store as st
        old = _make_spy_frame(n=100)
        new_window = _make_spy_frame(n=30)
        # Shift the new window to be 80 bdays later (overlaps only last 20 of old)
        new_window.index = old.index[-10:].append(
            pd.bdate_range(old.index[-1] + datetime.timedelta(days=1), periods=20)
        )
        new_window.index.name = None

        st.upsert("yahoo", "SPY2", old, overwrite_overlap=True)
        merged = st.upsert("yahoo", "SPY2", new_window, overwrite_overlap=True)

        # All rows from old that are strictly before the new window's start
        old_kept = old[old.index < new_window.index[0]]
        assert len(merged) == len(old_kept) + len(new_window)


# ---------------------------------------------------------------------------
# T5 — Legacy parquet (no close_price) returns TR fallback gracefully
# ---------------------------------------------------------------------------

class TestLegacyFallback:
    """Pre-W1.3 parquets (no close_price column) must gracefully fall back
    to returning the TR close with a warning, not a KeyError."""

    def test_basis_price_falls_back_to_tr_on_legacy(self, monkeypatch, caplog):
        """basis='price' on a pre-backfill parquet returns close and logs a warning."""
        import logging
        legacy = _make_legacy_frame()

        import lib.store as st
        monkeypatch.setattr(st, "read", lambda g, n: legacy if n == "LEGACY" else None)

        import lib.config as cfg
        monkeypatch.setattr(cfg, "load", lambda: {
            "yahoo": {"tickers": {"test": ["LEGACY"]}},
        })

        from engine import inputs
        with caplog.at_level(logging.WARNING, logger="engine.inputs"):
            s = inputs._yahoo_close("LEGACY", basis="price")

        assert s is not None
        # Should have returned close column (TR fallback)
        pd.testing.assert_series_equal(s, legacy["close"])
        # .attrs must declare the degraded basis
        assert s.attrs.get("price_basis") == "tr_fallback"
        # A warning must have been logged
        assert any("close_price column absent" in r.message for r in caplog.records), \
            "Expected a warning about missing close_price column"

    def test_basis_tr_works_on_legacy(self, monkeypatch):
        """basis='tr' (default) always works even without close_price."""
        legacy = _make_legacy_frame()

        import lib.store as st
        monkeypatch.setattr(st, "read", lambda g, n: legacy)

        from engine.inputs import _yahoo_close
        s = _yahoo_close("LEGACY", basis="tr")
        assert s is not None
        pd.testing.assert_series_equal(s, legacy["close"])


# ---------------------------------------------------------------------------
# T6 — .attrs price_basis tagging
# ---------------------------------------------------------------------------

class TestAttrsPriceBasisTag:
    """_yahoo_close sets .attrs['price_basis'] on the returned Series."""

    def test_tr_tagged_tr(self, monkeypatch):
        frame = _make_spy_frame()

        import lib.store as st
        monkeypatch.setattr(st, "read", lambda g, n: frame)

        from engine.inputs import _yahoo_close
        s = _yahoo_close("SPY", basis="tr")
        assert s.attrs.get("price_basis") == "tr"

    def test_price_tagged_price(self, monkeypatch):
        frame = _make_spy_frame()

        import lib.store as st
        monkeypatch.setattr(st, "read", lambda g, n: frame)

        from engine.inputs import _yahoo_close
        s = _yahoo_close("SPY", basis="price")
        assert s.attrs.get("price_basis") == "price"
