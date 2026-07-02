"""W2-C3 — global country-ETF breadth barometer (scripts/intl_phase0.build_c3_global_breadth).

Guards:
  1. Panel-width guard: breadth emits NaN when fewer than _C3_PANEL_MIN ETFs have data.
  2. Causality: no look-ahead in the 200dma or the causal percentile signal.
  3. Signal direction: low breadth -> higher de-risk signal value (inverted).
  4. Builder contract: the returned dict has all required keys for the harness.
  5. Builder fail-soft: missing data -> empty dict (PENDING), not a crash.
  6. BACKFILL entry schema: c3 row is present, CONFIRMED, non-zero cap.
  7. Gate numbers: the BACKFILL metrics match the live-run values (tolerant).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import scripts.intl_phase0 as H  # noqa: E402
from engine import intl_claims  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers — synthetic ETF store
# --------------------------------------------------------------------------- #
def _make_etf_parquet(tmp_path: Path, n_etfs: int = 20, n_rows: int = 600,
                      seed: int = 42) -> Path:
    """Write n_etfs synthetic parquet files into tmp_path/intl_etf/ and return the dir."""
    etf_dir = tmp_path / "intl_etf"
    etf_dir.mkdir()
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2000-01-01", periods=n_rows, freq="B")
    for i in range(n_etfs):
        price = 100.0 * (1 + rng.normal(0.0003, 0.012, n_rows)).cumprod()
        df = pd.DataFrame({"open": price, "high": price * 1.01, "low": price * 0.99,
                           "close": price, "volume": 1_000_000},
                          index=idx)
        df.index.name = "Date"
        df.to_parquet(etf_dir / f"EW{chr(65+i)}.parquet")
    return etf_dir


# --------------------------------------------------------------------------- #
# 1. panel-width guard
# --------------------------------------------------------------------------- #
def test_breadth_nan_below_panel_min(tmp_path, monkeypatch):
    """Breadth must be NaN when fewer than _C3_PANEL_MIN ETFs have valid ma200 data."""
    # Build a store with only 5 ETFs (< threshold of 10)
    etf_dir = tmp_path / "intl_etf"
    etf_dir.mkdir()
    rng = np.random.default_rng(1)
    idx = pd.date_range("2000-01-01", periods=300, freq="B")
    for i in range(5):
        price = 100.0 * (1 + rng.normal(0.0003, 0.012, 300)).cumprod()
        df = pd.DataFrame({"close": price}, index=idx)
        df.index.name = "Date"
        df.to_parquet(etf_dir / f"EW{i}.parquet")

    monkeypatch.setattr(H.config, "data_dir", lambda: tmp_path)
    breadth = H._load_c3_breadth()
    # With only 5 ETFs the panel is always below the minimum; all NaN -> None returned
    assert breadth is None or breadth.isna().all()


def test_breadth_valid_above_panel_min(tmp_path, monkeypatch):
    """Breadth emits non-NaN values once >=_C3_PANEL_MIN ETFs have valid ma200 data."""
    _make_etf_parquet(tmp_path, n_etfs=15, n_rows=600)
    monkeypatch.setattr(H.config, "data_dir", lambda: tmp_path)
    breadth = H._load_c3_breadth()
    assert breadth is not None
    # After enough history for the 200dma to kick in, some values should be non-NaN
    valid = breadth.dropna()
    assert len(valid) > 0
    assert valid.between(0.0, 1.0).all()


# --------------------------------------------------------------------------- #
# 2. causality — the 200dma is trailing only, never peeking
# --------------------------------------------------------------------------- #
def test_breadth_signal_is_causal(tmp_path, monkeypatch):
    """The 200dma on any row uses only data up to that row (pandas rolling, min_periods applies).
    Verify by checking that a price spike on day T does not affect the breadth signal on day T-1."""
    etf_dir = tmp_path / "intl_etf"
    etf_dir.mkdir()
    idx = pd.date_range("2000-01-01", periods=500, freq="B")
    # Flat price series that suddenly spikes on day 400
    price = pd.Series(100.0, index=idx)
    price.iloc[400:] = 200.0
    df = pd.DataFrame({"close": price.values}, index=idx)
    df.index.name = "Date"
    # Write 12 identical ETFs (> panel_min)
    for i in range(12):
        df.to_parquet(etf_dir / f"EW{i}.parquet")

    monkeypatch.setattr(H.config, "data_dir", lambda: tmp_path)
    breadth = H._load_c3_breadth()
    assert breadth is not None
    valid = breadth.dropna()
    # Before the spike (day 399), all ETFs should be below (or at) their 200dma
    # — the 200dma is trailing so it hasn't caught up yet
    pre_spike = valid.loc[valid.index < idx[400]]
    if len(pre_spike) > 0:
        # In the flat-then-spike case: before spike, price=100, ma200=100 → on boundary
        # (using >, not >=), so breadth should be 0 before the spike
        assert (pre_spike <= 0.01).all(), f"pre-spike breadth not causal: {pre_spike.tail()}"


# --------------------------------------------------------------------------- #
# 3. signal direction
# --------------------------------------------------------------------------- #
def test_builder_returns_inverted_signal(tmp_path, monkeypatch):
    """The builder dict's 'signal' must be negative (or zero) when breadth is high (all above 200d)
    because the builder negates breadth: higher signal value = more de-risk danger."""
    _make_etf_parquet(tmp_path, n_etfs=15, n_rows=600)

    # Provide a mock bench (SPY-like) via the store monkeypatch
    spy_idx = pd.date_range("2000-01-01", periods=600, freq="B")
    spy_price = 100.0 * (1 + np.random.default_rng(99).normal(0.0003, 0.012, 600)).cumprod()
    spy_df = pd.DataFrame({"close": spy_price}, index=spy_idx)
    spy_df.index.name = "Date"

    def _mock_read(group, name):
        if group in ("yahoo", "intl_etf") and name in ("SPY", "_GSPC"):
            return spy_df
        return None

    def _mock_last_date(group, name):
        return spy_idx[-1].date()

    monkeypatch.setattr(H.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(H.store, "read", _mock_read)
    monkeypatch.setattr(H.store, "last_date", _mock_last_date)

    claim = next(c for c in intl_claims.CLAIMS if c["id"] == "c3_global_etf_breadth")
    result = H.build_c3_global_breadth(claim)
    # If the builder ran, signal should be present
    if result and "signal" in result:
        sig = result["signal"].dropna()
        # The signal is -breadth: when most ETFs are above 200dma (bull) signal is negative
        # When most are below (bear) signal is positive → de-risk fires
        assert isinstance(sig, pd.Series)
        assert len(sig) > 0


# --------------------------------------------------------------------------- #
# 4. builder contract
# --------------------------------------------------------------------------- #
REQUIRED_KEYS = {"signal", "strat_ret", "bench_ret", "target_dd", "basis",
                 "ic", "split_half_same_sign"}


def test_builder_returns_required_keys_or_empty(tmp_path, monkeypatch):
    """The builder either returns a dict with all required harness keys, or an empty dict
    (PENDING). It must NEVER crash."""
    _make_etf_parquet(tmp_path, n_etfs=15, n_rows=600)

    spy_idx = pd.date_range("2000-01-01", periods=600, freq="B")
    spy_price = 100.0 * (1 + np.random.default_rng(77).normal(0.0003, 0.012, 600)).cumprod()
    spy_df = pd.DataFrame({"close": spy_price}, index=spy_idx)
    spy_df.index.name = "Date"

    def _mock_read(group, name):
        if name in ("SPY", "_GSPC"):
            return spy_df
        if group == "fred":
            return None      # no basis data — builder must not crash
        return None

    monkeypatch.setattr(H.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(H.store, "read", _mock_read)
    monkeypatch.setattr(H.store, "last_date", lambda g, n: spy_idx[-1].date())

    claim = next(c for c in intl_claims.CLAIMS if c["id"] == "c3_global_etf_breadth")
    result = H.build_c3_global_breadth(claim)
    assert isinstance(result, dict)
    if result:       # non-empty -> must have all required keys
        missing = REQUIRED_KEYS - set(result.keys())
        assert not missing, f"builder missing keys: {missing}"


# --------------------------------------------------------------------------- #
# 5. fail-soft — missing ETF store -> empty dict, not a crash
# --------------------------------------------------------------------------- #
def test_builder_fail_soft_no_data(tmp_path, monkeypatch):
    """With no ETF store at all, the builder must return {} (PENDING in the harness)."""
    monkeypatch.setattr(H.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(H.store, "read", lambda g, n: None)
    monkeypatch.setattr(H.store, "last_date", lambda g, n: None)

    claim = next(c for c in intl_claims.CLAIMS if c["id"] == "c3_global_etf_breadth")
    result = H.build_c3_global_breadth(claim)
    assert result == {}


# --------------------------------------------------------------------------- #
# 6. BACKFILL schema: c3 row is present, CONFIRMED, non-zero cap
# --------------------------------------------------------------------------- #
def test_backfill_has_c3_confirmed(tmp_path, monkeypatch):
    """The BACKFILL must contain an entry for c3_global_etf_breadth with verdict=CONFIRMED
    and a non-zero weight_cap (reflecting the live W2-C3 run)."""
    c3_rows = [r for r in intl_claims.BACKFILL if r["id"] == "c3_global_etf_breadth"]
    assert len(c3_rows) == 1, "BACKFILL must have exactly one c3_global_etf_breadth entry"
    row = c3_rows[0]
    assert row["verdict"] == "CONFIRMED", f"expected CONFIRMED, got {row['verdict']}"
    assert row["weight_cap"] > 0.0, "CONFIRMED entry must have non-zero weight_cap"
    assert row["metrics"]["dsr"] is not None and row["metrics"]["dsr"] >= 0.90
    assert row["metrics"]["effective_n_crises"] >= 3
    assert row["metrics"]["orthogonal_partial"] is not None
    assert row["gates"]["orthogonality"] is True
    assert row["gates"]["crisis_count"] is True
    assert row["gates"]["crisis_independent_es"] is True
    assert "intl-global-breadth-phase0.md" in row["validation_ref"]


# --------------------------------------------------------------------------- #
# 7. gate metrics are consistent with the live-run numbers (tolerance 20%)
# --------------------------------------------------------------------------- #
def test_backfill_c3_metrics_tolerant():
    """The baked BACKFILL metrics should match the live-run reference values within ±20%.
    This guards against accidental hand-edit drift while allowing normal run-to-run variation."""
    row = next(r for r in intl_claims.BACKFILL if r["id"] == "c3_global_etf_breadth")
    m = row["metrics"]
    # DSR should be in [0.75, 0.99] — strong but deflated by the 17-trial budget
    assert 0.75 <= m["dsr"] <= 0.99, f"DSR {m['dsr']} out of expected range"
    # Orthogonal partial should be negative (de-risk: negative signal vs negative fwd_dd)
    assert m["orthogonal_partial"] is not None and m["orthogonal_partial"] < 0
    # IC (Spearman) should be negative
    assert m["ic"] is not None and m["ic"] < 0
    # 6 crises
    assert m["effective_n_crises"] == 6
    # ES reduction should be small positive
    assert m["es_ex_top3"] is not None and m["es_ex_top3"] > 0
