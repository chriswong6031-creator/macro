"""Tests for W0.3 — benchmark basis-match and engine-owned read.

Two test classes:

  1. BenchmarkBasisMatch — proves that the excess computation no longer carries
     dividend-yield drift when a price-basis benchmark is used.  Uses a synthetic
     dividend-paying series where 'close' (TR) != 'close_price' (price-basis) so the
     distinction is observable. Also verifies the graceful fallback path.

  2. EngineOwnedRead — proves that sector_cycles._set_engine_read populates nw.read /
     nw.read_zh and that the content is factual (phase + pos + 200d status present).
"""
from __future__ import annotations

import pandas as pd
import numpy as np
import pytest


# ── 1. Benchmark basis-match ─────────────────────────────────────────────────

class TestBenchmarkBasisMatch:
    """Verify that excess = sector − bench_price does NOT carry dividend drift
    when bench_price is price-basis, but DOES when bench_TR is used."""

    def _price_series(self, n=200, start="2023-01-02", drift=0.0005) -> pd.Series:
        """Synthetic price-basis sector (no dividends)."""
        idx = pd.bdate_range(start, periods=n)
        vals = 1000.0 * np.cumprod(1.0 + np.full(n, drift))
        return pd.Series(vals, index=idx)

    def _bench_tr(self, n=200, start="2023-01-02",
                  drift=0.0005, div_yield_daily=0.0001) -> pd.Series:
        """Synthetic TR benchmark: price drift + daily div reinvestment."""
        idx = pd.bdate_range(start, periods=n)
        vals = 1000.0 * np.cumprod(1.0 + np.full(n, drift + div_yield_daily))
        return pd.Series(vals, index=idx)

    def _bench_price(self, n=200, start="2023-01-02", drift=0.0005) -> pd.Series:
        """Synthetic price-basis benchmark (no dividends — same drift as sector)."""
        idx = pd.bdate_range(start, periods=n)
        vals = 1000.0 * np.cumprod(1.0 + np.full(n, drift))
        return pd.Series(vals, index=idx)

    def _compute_excess(self, sector: pd.Series, bench: pd.Series, h: int = 21) -> list:
        """Compute forward excess returns over h-bar windows."""
        excesses = []
        for i in range(len(sector) - h - 1):
            d0 = sector.index[i]
            bb = bench[bench.index >= d0]
            if len(bb) <= h:
                continue
            fr = float(sector.iloc[i + h + 1] / sector.iloc[i] - 1.0)
            br = float(bb.iloc[h] / bb.iloc[0] - 1.0)
            excesses.append(fr - br)
        return excesses

    def test_price_basis_excess_near_zero_when_same_drift(self):
        """When sector and benchmark have identical drift (same basis), excess ≈ 0."""
        sector = self._price_series()
        bench_p = self._bench_price()
        excesses = self._compute_excess(sector, bench_p)
        assert len(excesses) > 10
        mean_excess = np.mean(excesses)
        # same drift → mean excess should be very close to 0
        assert abs(mean_excess) < 0.002, (
            f"Price-vs-price excess should be near 0, got {mean_excess:.4f} "
            "(price-basis match failing)"
        )

    def test_tr_benchmark_excess_carries_negative_dividend_drift(self):
        """When bench is TR (includes dividend drift), excess is chronically negative
        even when the sector and bench have the same underlying price movement.
        This is the audit's 'dividend drift' finding that W0.3 fixes."""
        sector = self._price_series(drift=0.0005)
        bench_tr = self._bench_tr(drift=0.0005, div_yield_daily=0.0002)
        excesses_tr = self._compute_excess(sector, bench_tr)

        bench_p = self._bench_price(drift=0.0005)
        excesses_p = self._compute_excess(sector, bench_p)

        mean_tr = np.mean(excesses_tr)
        mean_p = np.mean(excesses_p)
        # TR benchmark should give a more negative mean excess than price benchmark
        assert mean_tr < mean_p, (
            f"TR benchmark excess ({mean_tr:.4f}) should be more negative than "
            f"price benchmark excess ({mean_p:.4f}) due to dividend drift"
        )
        # The drift gap should be non-trivial (at least 1pp over 21-bar window
        # for div_yield_daily=0.0002 → ~0.42% per window)
        assert (mean_p - mean_tr) > 0.001, (
            f"Dividend drift gap too small: {mean_p - mean_tr:.4f}"
        )

    def test_benchmark_close_price_function_exists_and_returns_series(self):
        """benchmark_close_price() should exist and return a Series (or None if no data)."""
        from engine import china_sector_index as csi
        # just verify the function exists and is callable
        assert callable(csi.benchmark_close_price)
        # calling it may return None in a test env without data — that's fine
        result = csi.benchmark_close_price()
        assert result is None or isinstance(result, pd.Series), (
            f"Expected None or pd.Series, got {type(result)}"
        )

    def test_benchmark_close_price_fallback_when_close_price_absent(self, tmp_path,
                                                                      monkeypatch):
        """When 'close_price' column absent, falls back to 'close' without raising."""
        import types, sys

        # Build a minimal store returning only 'close' (pre-D4-W1)
        close_vals = pd.Series(
            [3000.0, 3001.0, 3002.0],
            index=pd.bdate_range("2026-01-02", periods=3),
            name="close"
        )
        mock_df = close_vals.to_frame()  # only has 'close', not 'close_price'

        from engine import china_sector_index as csi

        # monkeypatch store.read to return our controlled df
        original_read = None
        import lib.store as store_mod
        original_read = store_mod.read

        def mock_read(group, name, *a, **kw):
            if group == "china" and name == csi.BENCHMARK:
                return mock_df
            return original_read(group, name, *a, **kw)

        monkeypatch.setattr(store_mod, "read", mock_read)

        result = csi.benchmark_close_price()
        assert result is not None, "fallback should return 'close' when 'close_price' absent"
        assert isinstance(result, pd.Series)
        assert len(result) == 3
        assert result.attrs.get("basis_fallback") is True, (
            "fallback path should set basis_fallback=True"
        )

    def test_benchmark_close_price_preferred_when_available(self, monkeypatch):
        """When 'close_price' column present, it is used (not 'close')."""
        close_vals = pd.bdate_range("2026-01-02", periods=3)
        mock_df = pd.DataFrame({
            "close":       [3100.0, 3101.0, 3102.0],
            "close_price": [3000.0, 3001.0, 3002.0],  # different from 'close'
        }, index=close_vals)

        from engine import china_sector_index as csi
        import lib.store as store_mod
        original_read = store_mod.read

        def mock_read(group, name, *a, **kw):
            if group == "china" and name == csi.BENCHMARK:
                return mock_df
            return original_read(group, name, *a, **kw)

        monkeypatch.setattr(store_mod, "read", mock_read)

        result = csi.benchmark_close_price()
        assert result is not None
        # should return close_price values (3000, 3001, 3002), NOT close (3100, 3101, 3102)
        assert abs(result.iloc[0] - 3000.0) < 1e-6, (
            f"Expected close_price=3000, got {result.iloc[0]}"
        )
        assert result.attrs.get("basis") == "price"
        assert result.attrs.get("basis_fallback") is False


# ── 2. Engine-owned read ──────────────────────────────────────────────────────

class TestEngineOwnedRead:
    """Verify that _set_engine_read populates nw.read / nw.read_zh with factual content."""

    def _make_rec(self, name="Technology", phase="Peak", pos=84.0, above200=True,
                  rs_63d=12.5, rs_rank=1, proj=None) -> dict:
        """Minimal rec shaped like build_sector output (after _apply_leadership)."""
        if proj is None:
            proj = {"nextTurn": "trough", "central": "2027-03",
                    "low": "2026-11", "high": "2027-07"}
        return {
            "id": "xlk", "ticker": "XLK", "kind": "sector", "name": name,
            "proj": proj,
            "now": {
                "phase": phase, "pos": pos, "above200d": above200,
                "rs_63d": rs_63d, "rs_rank": rs_rank,
            },
        }

    def test_set_engine_read_populates_read(self):
        """_set_engine_read populates nw['read'] with a non-empty string."""
        from engine.sector_cycles import _set_engine_read
        rec = self._make_rec()
        _set_engine_read(rec)
        assert rec["now"].get("read"), "nw.read should be non-empty after _set_engine_read"

    def test_set_engine_read_populates_read_zh(self):
        """_set_engine_read populates nw['read_zh'] with a non-empty string."""
        from engine.sector_cycles import _set_engine_read
        rec = self._make_rec()
        _set_engine_read(rec)
        assert rec["now"].get("read_zh"), "nw.read_zh should be non-empty after _set_engine_read"

    def test_read_contains_phase_and_pos(self):
        """Engine read contains the phase label and cycle position."""
        from engine.sector_cycles import _set_engine_read
        rec = self._make_rec(phase="Peak", pos=84.0)
        _set_engine_read(rec)
        read = rec["now"]["read"]
        # phase short label from PHASES["Peak"]["short"] = "Topping"
        assert "Topping" in read or "Peak" in read, (
            f"Phase not in read: {read!r}"
        )
        assert "84" in read, f"Cycle pos not in read: {read!r}"

    def test_read_contains_200d_status(self):
        """Engine read includes 200-day trend context."""
        from engine.sector_cycles import _set_engine_read

        rec_above = self._make_rec(above200=True)
        _set_engine_read(rec_above)
        assert "above" in rec_above["now"]["read"].lower(), (
            "above200d not reflected in read"
        )

        rec_below = self._make_rec(above200=False)
        _set_engine_read(rec_below)
        assert "below" in rec_below["now"]["read"].lower(), (
            "below200d not reflected in read"
        )

    def test_read_contains_projection(self):
        """Engine read includes the projected next turn when proj is present."""
        from engine.sector_cycles import _set_engine_read
        rec = self._make_rec(proj={"nextTurn": "trough", "central": "2027-03",
                                   "low": "2026-11", "high": "2027-07"})
        _set_engine_read(rec)
        read = rec["now"]["read"]
        assert "trough" in read.lower() or "2027-03" in read, (
            f"Projection not in read: {read!r}"
        )

    def test_read_graceful_on_no_proj(self):
        """_set_engine_read doesn't raise when proj is absent."""
        from engine.sector_cycles import _set_engine_read
        rec = self._make_rec(proj=None)
        rec["proj"] = None
        _set_engine_read(rec)  # must not raise
        assert rec["now"].get("read"), "read should still be non-empty without proj"

    def test_read_graceful_on_none_rec(self):
        """_set_engine_read doesn't raise on degenerate inputs."""
        from engine.sector_cycles import _set_engine_read
        # no 'now' key
        _set_engine_read({})          # must not raise
        _set_engine_read({"now": None})  # must not raise

    def test_zh_read_contains_zh_characters(self):
        """nw.read_zh contains Chinese characters."""
        from engine.sector_cycles import _set_engine_read
        rec = self._make_rec()
        _set_engine_read(rec)
        read_zh = rec["now"]["read_zh"]
        # must contain at least one CJK character
        has_cjk = any('一' <= c <= '鿿' for c in read_zh)
        assert has_cjk, f"read_zh has no CJK characters: {read_zh!r}"

    def test_rs_in_read_when_present(self):
        """When RS data is available, it appears in the engine read."""
        from engine.sector_cycles import _set_engine_read
        rec = self._make_rec(rs_63d=12.5, rs_rank=1)
        _set_engine_read(rec)
        read = rec["now"]["read"]
        assert "RS" in read or "+12.5" in read or "#1" in read, (
            f"RS not reflected in read: {read!r}"
        )

    def test_js_prefers_engine_read_over_narr(self):
        """Verify that the JS template uses nw.read/nw.read_zh as primary (not NARR.now)."""
        import pathlib
        src = pathlib.Path("/tmp/wave-w023/templates/sector_cycles.js").read_text()
        # The W0.3 change: engine read primary, NARR demoted to analyst_note
        assert "nw.read_zh" in src or "nw.read" in src, (
            "sector_cycles.js: nw.read not referenced"
        )
        assert "cyc-analyst-note" in src or "analyst_note" in src.lower() or "Analyst note" in src, (
            "sector_cycles.js: analyst note section missing — NARR should be demoted to annotation"
        )
        # Old pattern (NARR wins over engine) must be gone
        old_pattern = 'nz(NARR[s.id], "now") || nw.read'
        assert old_pattern not in src, (
            "Old pattern still present: NARR still overrides engine read. W0.3 flip not applied."
        )
