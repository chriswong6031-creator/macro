"""Tests for scripts/build_polygon_universe.py.

Covers:
  * is_fresh() logic (mtime-based staleness)
  * build_gics_map() via patched _load_sp500_gics / _load_basket_gics
  * fetch_mcaps() — mocked _fetch_mcap; rate-limit bypass; checkpoint resume
  * build() end-to-end with patched internals (no real API, no real data files)
  * Null-honest: missing mcap → NaN in output, never invented
  * --dry-run: no file written

The real reference.parquet smoke tests run only when the file exists locally.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

import scripts.build_polygon_universe as m


# ---------------------------------------------------------------------------
# is_fresh
# ---------------------------------------------------------------------------

class TestIsFresh:
    def test_missing_returns_false(self, tmp_path):
        assert m.is_fresh(tmp_path / "nonexistent.parquet") is False

    def test_fresh_file_returns_true(self, tmp_path):
        p = tmp_path / "ref.parquet"
        p.write_bytes(b"x")
        assert m.is_fresh(p, stale_days=7) is True

    def test_stale_file_returns_false(self, tmp_path):
        p = tmp_path / "ref.parquet"
        p.write_bytes(b"x")
        old_mtime = time.time() - 8 * 86400
        os.utime(p, (old_mtime, old_mtime))
        assert m.is_fresh(p, stale_days=7) is False

    def test_exact_boundary_stale(self, tmp_path):
        """A file exactly stale_days old is treated as stale (< not <=)."""
        p = tmp_path / "ref.parquet"
        p.write_bytes(b"x")
        exact = time.time() - 7 * 86400
        os.utime(p, (exact, exact))
        assert m.is_fresh(p, stale_days=7) is False


# ---------------------------------------------------------------------------
# build_gics_map — patch the private loaders
# ---------------------------------------------------------------------------

class TestBuildGicsMap:
    def test_sp500_overrides_baskets(self, monkeypatch):
        """SP500 GICS takes priority over basket-derived label for same ticker."""
        monkeypatch.setattr(m, "_load_basket_gics",
                            lambda: {"AAPL": "WRONG", "JPM": "Financials"})
        monkeypatch.setattr(m, "_load_sp500_gics",
                            lambda: {"AAPL": "Information Technology", "NVDA": "Information Technology"})
        gics = m.build_gics_map()
        assert gics["AAPL"] == "Information Technology"   # SP500 wins
        assert gics["JPM"] == "Financials"                # basket only
        assert gics["NVDA"] == "Information Technology"   # SP500 only

    def test_basket_only_ticker_present(self, monkeypatch):
        monkeypatch.setattr(m, "_load_basket_gics", lambda: {"GS": "Financials"})
        monkeypatch.setattr(m, "_load_sp500_gics", lambda: {})
        gics = m.build_gics_map()
        assert gics["GS"] == "Financials"

    def test_empty_both(self, monkeypatch):
        monkeypatch.setattr(m, "_load_basket_gics", lambda: {})
        monkeypatch.setattr(m, "_load_sp500_gics", lambda: {})
        assert m.build_gics_map() == {}


# ---------------------------------------------------------------------------
# fetch_mcaps — mock _fetch_mcap; bypass rate-limit sleep
# ---------------------------------------------------------------------------

class TestFetchMcaps:
    def test_returns_known_caps(self, monkeypatch):
        monkeypatch.setattr(m, "_fetch_mcap", lambda t, k, base: {"AAPL": 4.6e12, "NVDA": 4.9e12}.get(t))
        monkeypatch.setattr(m, "_polygon_key", lambda: "fake")
        monkeypatch.setattr(time, "sleep", lambda _: None)
        caps = m.fetch_mcaps(["AAPL", "NVDA"], {})
        assert caps["AAPL"] == pytest.approx(4.6e12)
        assert caps["NVDA"] == pytest.approx(4.9e12)

    def test_skips_already_checkpointed(self, monkeypatch):
        call_log: list[str] = []

        def fake_fetch(ticker, key, base):
            call_log.append(ticker)
            return 1.0

        monkeypatch.setattr(m, "_fetch_mcap", fake_fetch)
        monkeypatch.setattr(m, "_polygon_key", lambda: "fake")
        monkeypatch.setattr(time, "sleep", lambda _: None)

        checkpoint = {"AAPL": 4.6e12}   # already fetched
        caps = m.fetch_mcaps(["AAPL", "NVDA"], checkpoint)
        assert "AAPL" not in call_log     # not re-fetched
        assert "NVDA" in call_log
        assert caps["AAPL"] == pytest.approx(4.6e12)

    def test_no_api_key_returns_checkpoint(self, monkeypatch):
        monkeypatch.setattr(m, "_polygon_key", lambda: None)
        existing = {"AAPL": 1e12}
        caps = m.fetch_mcaps(["AAPL", "NVDA"], existing)
        # returns the checkpoint unchanged (no new fetches)
        assert caps == existing

    def test_dry_run_no_http(self, monkeypatch):
        call_log: list[str] = []
        monkeypatch.setattr(m, "_fetch_mcap", lambda t, k, b: call_log.append(t) or 1.0)
        monkeypatch.setattr(m, "_polygon_key", lambda: "fake")
        caps = m.fetch_mcaps(["AAPL"], {}, dry_run=True)
        assert len(call_log) == 0      # no HTTP in dry_run
        assert caps == {}              # empty checkpoint (nothing to return)

    def test_none_value_preserved(self, monkeypatch):
        """Tickers where Polygon returns None (404) stay as None in output."""
        monkeypatch.setattr(m, "_fetch_mcap", lambda t, k, b: None)
        monkeypatch.setattr(m, "_polygon_key", lambda: "fake")
        monkeypatch.setattr(time, "sleep", lambda _: None)
        caps = m.fetch_mcaps(["ZZZZ"], {})
        assert caps["ZZZZ"] is None


# ---------------------------------------------------------------------------
# build() — end-to-end, fully mocked, no file I/O from data/
# ---------------------------------------------------------------------------

class TestBuild:
    def _patch(self, monkeypatch, tmp_path,
               gics=None, mcaps=None):
        """Patch all I/O so build() works with tmp_path and no real data."""
        if gics is None:
            gics = {"ALPH": "Information Technology", "BETA": "Financials"}
        if mcaps is None:
            mcaps = {"ALPH": 2.5e12, "BETA": 8e11}

        # Redirect cache + checkpoint to tmp_path
        cache_path = tmp_path / "reference.parquet"
        monkeypatch.setattr(m, "_cache_path", lambda: cache_path)
        monkeypatch.setattr(m, "_checkpoint_path", lambda: tmp_path / "ckpt.json")

        # Stub out GICS loading and mcap fetching
        monkeypatch.setattr(m, "build_gics_map", lambda: dict(gics))
        monkeypatch.setattr(m, "fetch_mcaps",
                            lambda tickers, checkpoint, dry_run=False:
                                {t: mcaps.get(t) for t in tickers} if not dry_run else checkpoint)
        # Stub checkpoint helpers
        monkeypatch.setattr(m, "_load_checkpoint", lambda: {})
        monkeypatch.setattr(m, "_save_checkpoint", lambda cp: None)

        return cache_path

    def test_output_parquet_written(self, tmp_path, monkeypatch):
        cache_path = self._patch(monkeypatch, tmp_path)
        m.build(force=True)
        assert cache_path.exists()
        df = pd.read_parquet(cache_path)
        assert "gics_sector" in df.columns
        assert "market_cap_usd" in df.columns
        assert "asof" in df.columns

    def test_sector_and_cap_values(self, tmp_path, monkeypatch):
        cache_path = self._patch(monkeypatch, tmp_path,
                                  gics={"ALPH": "Information Technology"},
                                  mcaps={"ALPH": 2.5e12})
        m.build(force=True)
        df = pd.read_parquet(cache_path)
        assert df.loc["ALPH", "gics_sector"] == "Information Technology"
        assert df.loc["ALPH", "market_cap_usd"] == pytest.approx(2.5e12)

    def test_fresh_cache_skips_rebuild(self, tmp_path, monkeypatch):
        """When cache is fresh and force=False, build() returns early without patched helpers."""
        # Write a stub fresh parquet
        stub = pd.DataFrame(
            {"gics_sector": ["Stub"], "market_cap_usd": [1.0], "asof": ["2025-01-01"]},
            index=pd.Index(["STUB"], name="ticker")
        )
        out_path = tmp_path / "reference.parquet"
        stub.to_parquet(out_path)

        monkeypatch.setattr(m, "_cache_path", lambda: out_path)
        gics_calls = []
        monkeypatch.setattr(m, "build_gics_map", lambda: gics_calls.append(1) or {})

        result = m.build(force=False)
        assert len(gics_calls) == 0, "build_gics_map should not be called when cache is fresh"
        assert "STUB" in result.index

    def test_force_flag_rebuilds_fresh_cache(self, tmp_path, monkeypatch):
        stub = pd.DataFrame(
            {"gics_sector": ["Stub"], "market_cap_usd": [1.0], "asof": ["2025-01-01"]},
            index=pd.Index(["STUB"], name="ticker")
        )
        out_path = tmp_path / "reference.parquet"
        stub.to_parquet(out_path)

        cache_path = self._patch(monkeypatch, tmp_path,
                                  gics={"ALPH": "Information Technology"},
                                  mcaps={"ALPH": 1e12})
        m.build(force=True)
        df = pd.read_parquet(cache_path)
        # Should contain ALPH (our stub), not STUB (old file)
        assert "ALPH" in df.index

    def test_dry_run_does_not_write(self, tmp_path, monkeypatch):
        cache_path = self._patch(monkeypatch, tmp_path)
        m.build(force=True, dry_run=True)
        assert not cache_path.exists(), "dry_run=True must not write the parquet"

    def test_null_honest_no_mcap(self, tmp_path, monkeypatch):
        """Names without market cap data have NaN market_cap_usd — never invented."""
        cache_path = self._patch(monkeypatch, tmp_path,
                                  gics={"ALPH": "Information Technology"},
                                  mcaps={"ALPH": None})
        m.build(force=True)
        df = pd.read_parquet(cache_path)
        assert df.loc["ALPH", "gics_sector"] == "Information Technology"
        assert pd.isna(df.loc["ALPH", "market_cap_usd"])

    def test_atomic_write_no_tmp_left_behind(self, tmp_path, monkeypatch):
        cache_path = self._patch(monkeypatch, tmp_path)
        m.build(force=True)
        tmp_files = list(tmp_path.glob("*.tmp.parquet"))
        assert len(tmp_files) == 0, f"Temp files left behind: {tmp_files}"


# ---------------------------------------------------------------------------
# Regex / us_like filter — hyphen-form tickers must not be dropped
# ---------------------------------------------------------------------------

class TestUsLikeFilter:
    """Regression lock for the BRK-B / BF-B filter bug.

    constituents.parquet stores class-B shares with hyphens; the us_like regex
    must pass them through so _fetch_mcap (which normalises '-' -> '.') runs.
    """

    def _us_like(self, tickers: list[str]) -> list[str]:
        import re
        return [t for t in tickers if re.match(r"^[A-Z]{1,5}([.\-][AB])?$", t)]

    def test_hyphen_class_b_passes(self):
        """BRK-B and BF-B must survive the filter (were silently dropped before fix)."""
        assert "BRK-B" in self._us_like(["BRK-B"])
        assert "BF-B" in self._us_like(["BF-B"])

    def test_dot_class_b_still_passes(self):
        """Dot-form (BRK.B) must continue to work."""
        assert "BRK.B" in self._us_like(["BRK.B"])

    def test_class_a_hyphen_passes(self):
        assert "BRK-A" in self._us_like(["BRK-A"])

    def test_plain_tickers_still_pass(self):
        for t in ["AAPL", "NVDA", "GOOGL", "MSFT", "BRK"]:
            assert t in self._us_like([t]), f"{t!r} should pass"

    def test_crypto_and_intl_still_rejected(self):
        """Non-US suffixes must still be filtered."""
        for bad in ["BTC-USD", "ETH-USD", "SPY.MX", "AAPL.L", "ZZZZ123"]:
            assert bad not in self._us_like([bad]), f"{bad!r} should be rejected"

    def test_build_includes_hyphen_tickers_in_mcap_fetch(self, monkeypatch, tmp_path):
        """End-to-end: BRK-B in GICS map must reach fetch_mcaps, not be filtered."""
        import scripts.build_polygon_universe as bpu

        fetched: list[str] = []

        def fake_fetch_mcaps(tickers, checkpoint, dry_run=False):
            fetched.extend(tickers)
            return {t: 1e11 for t in tickers}

        monkeypatch.setattr(bpu, "_cache_path", lambda: tmp_path / "ref.parquet")
        monkeypatch.setattr(bpu, "_checkpoint_path", lambda: tmp_path / "ckpt.json")
        monkeypatch.setattr(bpu, "build_gics_map",
                            lambda: {"BRK-B": "Financials", "BF-B": "Consumer Staples",
                                     "AAPL": "Information Technology"})
        monkeypatch.setattr(bpu, "fetch_mcaps", fake_fetch_mcaps)
        monkeypatch.setattr(bpu, "_load_checkpoint", lambda: {})
        monkeypatch.setattr(bpu, "_save_checkpoint", lambda cp: None)

        bpu.build(force=True)
        assert "BRK-B" in fetched, "BRK-B was filtered out before fetch_mcaps"
        assert "BF-B" in fetched, "BF-B was filtered out before fetch_mcaps"
        assert "AAPL" in fetched


# ---------------------------------------------------------------------------
# No-regress write guard
# ---------------------------------------------------------------------------

class TestNoRegressGuard:
    """build() must keep the existing cache when new data has materially fewer caps."""

    def _patch_base(self, monkeypatch, tmp_path, gics, mcaps):
        import scripts.build_polygon_universe as bpu
        cache_path = tmp_path / "reference.parquet"
        monkeypatch.setattr(bpu, "_cache_path", lambda: cache_path)
        monkeypatch.setattr(bpu, "_checkpoint_path", lambda: tmp_path / "ckpt.json")
        monkeypatch.setattr(bpu, "build_gics_map", lambda: dict(gics))
        monkeypatch.setattr(bpu, "fetch_mcaps",
                            lambda tickers, checkpoint, dry_run=False:
                                {t: mcaps.get(t) for t in tickers})
        monkeypatch.setattr(bpu, "_load_checkpoint", lambda: {})
        monkeypatch.setattr(bpu, "_save_checkpoint", lambda cp: None)
        return cache_path

    def test_guard_keeps_good_cache_on_degraded_run(self, monkeypatch, tmp_path):
        import scripts.build_polygon_universe as bpu
        import pandas as pd

        # Use realistic all-alpha tickers so they survive the us_like filter
        _NAMES = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA", "JPM", "V", "XOM"]
        good_gics = {t: "Financials" for t in _NAMES}
        good_mcaps = {t: float((i + 1) * 1e11) for i, t in enumerate(_NAMES)}
        cache_path = self._patch_base(monkeypatch, tmp_path, good_gics, good_mcaps)
        bpu.build(force=True)
        assert cache_path.exists()
        prev = pd.read_parquet(cache_path, columns=["market_cap_usd"])
        assert prev["market_cap_usd"].notna().sum() == len(_NAMES), "pre-condition: good cache"

        # Now simulate a degraded run: same GICS but all-null mcaps (no API key)
        monkeypatch.setattr(bpu, "build_gics_map", lambda: dict(good_gics))
        monkeypatch.setattr(bpu, "fetch_mcaps",
                            lambda tickers, checkpoint, dry_run=False:
                                {t: None for t in tickers})
        result = bpu.build(force=True)

        # Guard should have kept the good cache
        assert result["market_cap_usd"].notna().sum() == len(_NAMES), (
            "Guard should have kept the good cache, not overwritten with all-null")

    def test_guard_allows_write_when_no_prior_cache(self, monkeypatch, tmp_path):
        import scripts.build_polygon_universe as bpu

        gics = {"AAPL": "Information Technology"}
        cache_path = self._patch_base(monkeypatch, tmp_path, gics, {"AAPL": None})
        bpu.build(force=True)
        assert cache_path.exists(), "Should write even when all-null if no prior cache"

    def test_guard_allows_small_decrease(self, monkeypatch, tmp_path):
        """A <10% drop (e.g. delists) must not trigger the guard."""
        import scripts.build_polygon_universe as bpu
        import pandas as pd

        # Use realistic all-alpha tickers so they survive the us_like filter
        _NAMES = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA", "JPM", "V", "XOM"]
        good_gics = {t: "Financials" for t in _NAMES}
        good_mcaps = {t: float((i + 1) * 1e11) for i, t in enumerate(_NAMES)}
        cache_path = self._patch_base(monkeypatch, tmp_path, good_gics, good_mcaps)
        bpu.build(force=True)

        # 9 caps on re-run (one delist) — within 10% tolerance
        new_mcaps = {t: (v if i < 9 else None) for i, (t, v) in enumerate(good_mcaps.items())}
        monkeypatch.setattr(bpu, "build_gics_map", lambda: dict(good_gics))
        monkeypatch.setattr(bpu, "fetch_mcaps",
                            lambda tickers, checkpoint, dry_run=False:
                                {t: new_mcaps.get(t) for t in tickers})
        result = bpu.build(force=True)
        assert result["market_cap_usd"].notna().sum() == 9, (
            "A <10% drop should be allowed through the guard")


# ---------------------------------------------------------------------------
# Smoke-tests against the real reference.parquet (skipped in CI)
# ---------------------------------------------------------------------------

class TestRealParquet:
    _REF = Path(__file__).resolve().parents[1] / "data" / "polygon_universe" / "reference.parquet"

    @pytest.fixture(autouse=True)
    def skip_if_absent(self):
        if not self._REF.exists():
            pytest.skip("data/polygon_universe/reference.parquet not present")

    def test_schema(self):
        df = pd.read_parquet(self._REF)
        assert "gics_sector" in df.columns
        assert "market_cap_usd" in df.columns
        assert "asof" in df.columns

    def test_gics_coverage(self):
        df = pd.read_parquet(self._REF)
        non_null = df["gics_sector"].notna().sum()
        assert non_null >= 100, f"expected ≥100 GICS labels, got {non_null}"

    def test_spot_check_nvda(self):
        df = pd.read_parquet(self._REF)
        if "NVDA" not in df.index:
            pytest.skip("NVDA not in reference.parquet")
        assert df.loc["NVDA", "gics_sector"] == "Information Technology"
        assert df.loc["NVDA", "market_cap_usd"] > 1e11

    def test_spot_check_googl(self):
        df = pd.read_parquet(self._REF)
        if "GOOGL" not in df.index:
            pytest.skip("GOOGL not in reference.parquet")
        assert df.loc["GOOGL", "gics_sector"] == "Communication Services"

    def test_spot_check_jpm(self):
        df = pd.read_parquet(self._REF)
        if "JPM" not in df.index:
            pytest.skip("JPM not in reference.parquet")
        assert df.loc["JPM", "gics_sector"] == "Financials"

    def test_spot_check_xom(self):
        df = pd.read_parquet(self._REF)
        if "XOM" not in df.index:
            pytest.skip("XOM not in reference.parquet")
        assert df.loc["XOM", "gics_sector"] == "Energy"

    def test_mcap_coverage_above_90pct(self):
        df = pd.read_parquet(self._REF)
        non_null = df["market_cap_usd"].notna().sum()
        total = len(df)
        assert non_null / total > 0.9, (
            f"expected >90% market cap coverage, got {non_null}/{total}")

    def test_no_invented_sectors(self):
        """All non-null GICS labels must be canonical GICS sectors."""
        known = {
            "Information Technology", "Financials", "Health Care",
            "Consumer Discretionary", "Communication Services", "Industrials",
            "Consumer Staples", "Energy", "Utilities", "Real Estate", "Materials",
        }
        df = pd.read_parquet(self._REF)
        bad = set(df["gics_sector"].dropna().unique()) - known
        assert not bad, f"Non-GICS labels found: {bad}"
