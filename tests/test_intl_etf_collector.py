"""Tests for collectors/intl_etf.py — country-ETF total-return substrate (W0-1).

Covers:
- cold-start triggers max-history fetch
- warm store uses incremental window
- new tickers on warm store deep-seed only the new ones
- full OHLCV (all five columns) are stored, not close-only
- fail-closed coverage gate rejects low-coverage batches
- overwrite_overlap=True is set (auto_adjust=True seam safety)
- stale_after_days=8 (weekly cadence)
- universe constant matches declared 23-ticker set
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors import intl_etf as ie   # noqa: E402
from collectors.intl_etf import TICKERS  # noqa: E402
from lib import config                   # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_ohlcv(batch: list[str], n: int = 120) -> pd.DataFrame:
    """Minimal yfinance group_by='ticker' MultiIndex OHLCV frame."""
    idx = pd.date_range("2000-01-01", periods=n, freq="B")
    cols = pd.MultiIndex.from_product(
        [batch, ["Open", "High", "Low", "Close", "Volume"]]
    )
    data = [[100.0] * len(cols)] * n
    return pd.DataFrame(data, index=idx, columns=cols)


def _patched_adapter(monkeypatch, tmp_path) -> tuple[ie.IntlEtfAdapter, dict]:
    """Build an adapter with yf.download monkeypatched; return (adapter, seen)."""
    seen: dict = {"calls": []}

    def fake_download(batch, period, **kw):
        seen["calls"].append((period, list(batch)))
        seen["period"] = period
        return _fake_ohlcv(list(batch))

    monkeypatch.setattr(ie.yf, "download", fake_download)
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return ie.IntlEtfAdapter(), seen


def _seed_store(tmp_path: Path, tickers: list[str] | None = None) -> None:
    """Simulate a warm store: write a minimal parquet for every ticker.

    Values MUST match _fake_ohlcv's 100.0 closes — the adjustment-basis guard
    (store.basis_shifted) compares the incremental window against stored closes
    on the overlap dates, and a mismatched fixture reads as a re-based series
    (triggering a period='max' re-pull the warm-store assertions don't expect)."""
    tickers = tickers if tickers is not None else TICKERS
    store_dir = tmp_path / "intl_etf"
    store_dir.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range("2000-01-01", periods=10, freq="B")
    df = pd.DataFrame({"open": 100.0, "high": 100.0, "low": 100.0,
                        "close": 100.0, "volume": 100.0}, index=idx)
    for t in tickers:
        df.to_parquet(store_dir / f"{t}.parquet")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_universe_size():
    """Universe must contain exactly 23 tickers — the canonical set in the spec."""
    assert len(TICKERS) == 23, f"Expected 23 tickers, got {len(TICKERS)}"
    assert len(set(TICKERS)) == len(TICKERS), "Duplicate tickers in TICKERS"


def test_cold_store_seeds_full_history(tmp_path, monkeypatch):
    adapter, seen = _patched_adapter(monkeypatch, tmp_path)
    frames = adapter.fetch(full_history=False)
    # Cold store (no intl_etf dir) must trigger period='max'.
    assert seen["period"] == "max", "cold store must use period='max'"
    assert len(frames) > 0


def test_warm_store_uses_incremental(tmp_path, monkeypatch):
    adapter, seen = _patched_adapter(monkeypatch, tmp_path)
    _seed_store(tmp_path)   # fully warm
    adapter.fetch(full_history=False)
    # All calls should use the incremental period, never 'max'.
    periods = [p for p, _ in seen["calls"]]
    assert all(p != "max" for p in periods), \
        f"warm store should not trigger max fetch; got {periods}"


def test_full_history_flag_forces_max(tmp_path, monkeypatch):
    adapter, seen = _patched_adapter(monkeypatch, tmp_path)
    _seed_store(tmp_path)   # store is warm but flag overrides
    adapter.fetch(full_history=True)
    assert seen["period"] == "max", "--full-history must force period='max'"


def test_new_ticker_deep_seeds_on_warm_store(tmp_path, monkeypatch):
    """A new ticker added to TICKERS after the store is warm gets a max backfill."""
    adapter, seen = _patched_adapter(monkeypatch, tmp_path)
    # Seed all but the last ticker.
    _seed_store(tmp_path, TICKERS[:-1])
    missing = TICKERS[-1]
    adapter.fetch(full_history=False)

    max_batches = [b for p, b in seen["calls"] if p == "max"]
    assert max_batches, f"new ticker {missing!r} must trigger a max deep-seed"
    assert any(missing in b for b in max_batches), \
        f"{missing!r} must be in the max batch"


def test_ohlcv_columns_present(tmp_path, monkeypatch):
    """Stored frames must have all five OHLCV columns, not close-only."""
    adapter, _ = _patched_adapter(monkeypatch, tmp_path)
    frames = adapter.fetch(full_history=False)
    for ticker, df in frames.items():
        for col in ("open", "high", "low", "close", "volume"):
            assert col in df.columns, \
                f"OHLCV column {col!r} missing for {ticker}"


def test_coverage_gate_fail_closed(tmp_path, monkeypatch):
    """If < COVERAGE_THRESHOLD fraction return data, the batch must be rejected."""
    # Only return data for 1 ticker regardless of the batch.
    def sparse_download(batch, period, **kw):
        # Return a frame for only the first ticker in the batch.
        return _fake_ohlcv([batch[0]])

    monkeypatch.setattr(ie.yf, "download", sparse_download)
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    adapter = ie.IntlEtfAdapter()

    with pytest.raises(RuntimeError, match="coverage gate FAIL"):
        adapter.fetch(full_history=False)


def test_overwrite_overlap_set():
    """Adapter must declare overwrite_overlap=True for auto_adjust seam safety."""
    adapter = ie.IntlEtfAdapter()
    assert adapter.overwrite_overlap is True, \
        "overwrite_overlap must be True for dividend-adjusted total-return series"


def test_stale_after_days_weekly():
    """stale_after_days should be >= 7 to match weekly cadence."""
    adapter = ie.IntlEtfAdapter()
    assert adapter.stale_after_days >= 7, \
        f"stale_after_days={adapter.stale_after_days} too tight for weekly collector"


def test_group_is_intl_etf():
    """group must be 'intl_etf' so data lands in data/intl_etf/."""
    adapter = ie.IntlEtfAdapter()
    assert adapter.group == "intl_etf"


def test_adr_sensors_in_yahoo_config():
    """config.yml must declare yahoo.tickers.adr_sensors with the 7 ADRs."""
    cfg = config.load()
    adr = cfg["yahoo"]["tickers"].get("adr_sensors", [])
    expected = {"ASML", "LVMUY", "BHP", "RIO", "VALE", "HSBC", "SONY"}
    got = set(adr)
    assert got == expected, f"adr_sensors mismatch: expected {expected}, got {got}"


def test_adr_sensors_have_extra_names():
    """Each ADR sensor must have a name+sector entry in stock_search.extra_names."""
    cfg = config.load()
    extra_names = cfg["stock_search"].get("extra_names", {})
    for ticker in ["ASML", "LVMUY", "BHP", "RIO", "VALE", "HSBC", "SONY"]:
        assert ticker in extra_names, \
            f"{ticker} missing from stock_search.extra_names"
        entry = extra_names[ticker]
        assert "name" in entry and "sector" in entry, \
            f"{ticker} extra_names entry incomplete: {entry}"


def test_tsm_not_duplicated_in_adr_sensors():
    """TSM already lives in stock_search.extra_tickers — must not be in adr_sensors."""
    cfg = config.load()
    adr = cfg["yahoo"]["tickers"].get("adr_sensors", [])
    assert "TSM" not in adr, \
        "TSM already in stock_search.extra_tickers; don't duplicate in adr_sensors"
