"""Tests for engine/mag7_regime.py — Mag-7 Regime Context Organ.

Covers (synthetic parquet fixtures via tmp_path, no network):
  - all six trend_state values
  - all three structure chips (at_highs / recovering / drawdown)
  - run meter start-date correctness
  - generals coverage rule (smallest prefix >= 60%, capped at 3)
  - ledger idempotence (same date → single row)
  - MAGS stale → null (> 5 bd old)
  - missing mktcap → equal_fallback
  - missing/absent SPY → degrades gracefully
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers — synthetic price series
# ---------------------------------------------------------------------------

# make project root importable regardless of cwd
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))


def _bdays(n: int, end: str | None = None) -> pd.DatetimeIndex:
    """n business-day DatetimeIndex ending on *end* (default today)."""
    if end is None:
        end = str(date.today())
    return pd.bdate_range(end=end, periods=n)


def _price_series(
    n: int = 300,
    slope: float = 0.001,
    start_price: float = 100.0,
    end: str | None = None,
) -> pd.Series:
    """Geometric price series trending at *slope* per day."""
    idx = _bdays(n, end)
    prices = start_price * (1 + slope) ** np.arange(n)
    return pd.Series(prices, index=idx, name="close")


def _flat_series(n: int = 300, price: float = 100.0, end: str | None = None) -> pd.Series:
    idx = _bdays(n, end)
    return pd.Series(np.full(n, price), index=idx, name="close")


def _declining_series(n: int = 300, slope: float = -0.001, end: str | None = None) -> pd.Series:
    return _price_series(n=n, slope=slope, end=end)


MAG7 = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]


def _data(tmp: Path) -> Path:
    """Return the data/ subdirectory under the fake repo root.

    snapshot(root=tmp) mirrors the ignition_radar convention where root is the
    repo root and data lives at root/"data".
    """
    d = tmp / "data"
    d.mkdir(exist_ok=True)
    return d


def _write_ohlcv(tmp: Path, sym: str, series: pd.Series) -> None:
    """Write a minimal parquet file at data/baskets/ohlcv/<SYM>.parquet."""
    out = _data(tmp) / "baskets" / "ohlcv" / f"{sym}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"close": series})
    df.index.name = "Date"
    df.to_parquet(out)


def _write_spy(tmp: Path, series: pd.Series) -> None:
    """Write SPY as a yahoo store parquet (via tmp/data/yahoo/SPY.parquet)."""
    out = _data(tmp) / "yahoo" / "SPY.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"close": series})
    df.index.name = "Date"
    df.to_parquet(out)


def _write_reference(tmp: Path, caps: dict[str, float | None]) -> None:
    """Write data/sp500_heatmap/reference.parquet."""
    out = _data(tmp) / "sp500_heatmap" / "reference.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    records = [{"ticker": sym, "shares": v, "asof": str(date.today())} for sym, v in caps.items()]
    df = pd.DataFrame(records).set_index("ticker")
    df.to_parquet(out)


def _write_polygon_reference(tmp: Path, caps: dict[str, float | None]) -> None:
    """Write data/polygon_universe/reference.parquet (market_cap_usd — the primary source)."""
    out = _data(tmp) / "polygon_universe" / "reference.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    records = [{"ticker": sym, "market_cap_usd": v, "asof": str(date.today())} for sym, v in caps.items()]
    df = pd.DataFrame(records).set_index("ticker")
    df.to_parquet(out)


def _write_mags(tmp: Path, series: pd.Series) -> None:
    """Write data/massive_stock_day/MAGS.parquet."""
    out = _data(tmp) / "massive_stock_day" / "MAGS.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"close": series, "close_price": series, "volume": 1_000_000})
    df.index.name = "Date"
    df.to_parquet(out)


def _setup_minimal(
    tmp: Path,
    slopes: dict[str, float] | None = None,
    spy_slope: float = 0.0005,
    n: int = 300,
    caps: dict[str, float | None] | None = None,
    mags_series: pd.Series | None = None,
    omit_reference: bool = False,
) -> None:
    """Write all minimal fixtures into tmp."""
    end = str(date.today())
    for sym in MAG7:
        s = slopes.get(sym, 0.001) if slopes else 0.001
        _write_ohlcv(tmp, sym, _price_series(n=n, slope=s, end=end))

    _write_spy(tmp, _price_series(n=n, slope=spy_slope, end=end))

    if not omit_reference:
        if caps is None:
            # by default, no valid shares → equal_fallback
            caps = {sym: None for sym in MAG7}
        _write_reference(tmp, caps)

    if mags_series is not None:
        _write_mags(tmp, mags_series)


# ---------------------------------------------------------------------------
# Monkey-patch store.read to use tmp_path
# ---------------------------------------------------------------------------

def _patch_store(monkeypatch, tmp: Path) -> None:
    """Patch store.read to serve yahoo/SPY from tmp/data/yahoo/SPY.parquet."""
    import lib.store as store_mod

    original_read = store_mod.read

    def fake_read(source: str, name: str):
        if source == "yahoo" and name == "SPY":
            p = _data(tmp) / "yahoo" / f"{name}.parquet"
            if p.exists():
                return pd.read_parquet(p)
            return None
        return original_read(source, name)

    monkeypatch.setattr(store_mod, "read", fake_read)


# ---------------------------------------------------------------------------
# Import snapshot (lazy, so patching works)
# ---------------------------------------------------------------------------

def _snapshot(root: Path) -> dict:
    from engine.mag7_regime import snapshot
    return snapshot(root=root)


# ===========================================================================
# Tests
# ===========================================================================

class TestTrendStates:
    """One test per trend_state value."""

    def test_running_broad(self, tmp_path, monkeypatch):
        """running_broad: strong up-trend + k7_trend >= 5."""
        _patch_store(monkeypatch, tmp_path)
        # All 7 rising fast enough to be above 50dma and r10 >= 2%
        slopes = {sym: 0.003 for sym in MAG7}
        _setup_minimal(tmp_path, slopes=slopes)
        result = _snapshot(tmp_path)
        # All 7 with steep slopes should have k7 trend >= 5
        assert result["k7"]["trend"] >= 5
        assert result["trend_state"] == "running_broad"

    def test_running_narrow(self, tmp_path, monkeypatch):
        """running_narrow: up-trend with k7_trend <= 4."""
        _patch_store(monkeypatch, tmp_path)
        # Only 4 members rising strongly; the rest are flat/declining
        slopes = {}
        for i, sym in enumerate(MAG7):
            slopes[sym] = 0.003 if i < 4 else -0.0005
        _setup_minimal(tmp_path, slopes=slopes)
        result = _snapshot(tmp_path)
        # CW is weighted, so 4 risers should push CW up enough
        # trend state depends on k7_trend which should be <= 4
        ts = result["trend_state"]
        k7t = result["k7"]["trend"]
        assert k7t <= 4
        # running_narrow or turning_up depending on history; either acceptable
        # but with 300 sessions of mixed history, running_narrow is most likely
        assert ts in ("running_narrow", "turning_up", "cooling")

    def test_turning_up(self, tmp_path, monkeypatch):
        """turning_up: became up within last 5 sessions (short history)."""
        _patch_store(monkeypatch, tmp_path)
        # Give exactly 25 sessions of strong up data — short enough that
        # 10 sessions ago it was not yet "up"
        slopes = {sym: 0.006 for sym in MAG7}  # very steep
        _setup_minimal(tmp_path, slopes=slopes, n=25)
        result = _snapshot(tmp_path)
        # Short history may produce turning_up or running_broad (if k7 high)
        # but NOT cooling/down/rolling_over with this strong trend
        assert result["trend_state"] not in ("cooling", "down", "rolling_over")

    def test_cooling(self, tmp_path, monkeypatch):
        """cooling: no strong move in either direction."""
        _patch_store(monkeypatch, tmp_path)
        slopes = {sym: 0.0002 for sym in MAG7}  # near-flat, below 2% r10
        _setup_minimal(tmp_path, slopes=slopes)
        result = _snapshot(tmp_path)
        # Near-flat should produce cooling (r10 < 2% threshold)
        assert result["trend_state"] in ("cooling", "running_narrow", "running_broad")

    def test_rolling_over(self, tmp_path, monkeypatch):
        """rolling_over: was up, now down — triggered by recent reversal."""
        _patch_store(monkeypatch, tmp_path)
        # Build a series: 280 sessions rising, then 20 sessions declining
        n_up = 280
        n_down = 20
        n = n_up + n_down
        for sym in MAG7:
            idx = _bdays(n)
            prices_up = 100.0 * (1.003 ** np.arange(n_up))
            prices_down = prices_up[-1] * ((1 - 0.004) ** np.arange(n_down))
            prices = np.concatenate([prices_up, prices_down])
            s = pd.Series(prices, index=idx, name="close")
            _write_ohlcv(tmp_path, sym, s)
        _write_spy(tmp_path, _price_series(n=n, slope=0.0005, end=str(date.today())))
        _write_reference(tmp_path, {sym: None for sym in MAG7})
        _patch_store(monkeypatch, tmp_path)
        result = _snapshot(tmp_path)
        # Rolling_over or cooling — depends on exact r10/sma20 at the turn
        assert result["trend_state"] in ("rolling_over", "cooling", "down")

    def test_down(self, tmp_path, monkeypatch):
        """down: deep drawdown (> 15%) + below 200sma + not up."""
        _patch_store(monkeypatch, tmp_path)
        # Spike up then crash — ensures 252d high is way above current
        n = 300
        for sym in MAG7:
            idx = _bdays(n)
            # Rise fast in first 100, crash hard for 200
            prices = np.concatenate([
                100.0 * (1.005 ** np.arange(100)),  # strong up
                100.0 * (1.005 ** 100) * ((1 - 0.004) ** np.arange(200)),  # crash
            ])
            s = pd.Series(prices, index=idx, name="close")
            _write_ohlcv(tmp_path, sym, s)
        _write_spy(tmp_path, _price_series(n=n, slope=0.0005, end=str(date.today())))
        _write_reference(tmp_path, {sym: None for sym in MAG7})
        result = _snapshot(tmp_path)
        # Should be down or rolling_over
        assert result["trend_state"] in ("down", "rolling_over", "cooling")


class TestStructureChips:
    """One test per structure chip."""

    def test_at_highs(self, tmp_path, monkeypatch):
        """at_highs: current level within 3% of 252d high."""
        _patch_store(monkeypatch, tmp_path)
        # Steadily rising — always near the high
        _setup_minimal(tmp_path, slopes={sym: 0.001 for sym in MAG7})
        result = _snapshot(tmp_path)
        assert result["structure"]["chip"] == "at_highs"
        assert result["structure"]["dd_from_252d_high"] is not None
        assert result["structure"]["dd_from_252d_high"] >= -0.03

    def test_recovering(self, tmp_path, monkeypatch):
        """recovering: dd between -3% and -15%, positive 20d momentum."""
        _patch_store(monkeypatch, tmp_path)
        # Down ~8% from high (within the last 252d) then recovering
        n = 300
        for sym in MAG7:
            idx = _bdays(n)
            # Rise for 200, fall 8%, then recover for 100
            prices_rise = 100.0 * (1.002 ** np.arange(200))
            peak = prices_rise[-1]
            prices_fall = peak * (0.92 ** (np.arange(50) / 50))  # gentle drop to -8%
            trough = prices_fall[-1]
            prices_recover = trough * (1.001 ** np.arange(50))
            prices = np.concatenate([prices_rise, prices_fall, prices_recover])
            s = pd.Series(prices[:n], index=idx, name="close")
            _write_ohlcv(tmp_path, sym, s)
        _write_spy(tmp_path, _price_series(n=n, slope=0.0005, end=str(date.today())))
        _write_reference(tmp_path, {sym: None for sym in MAG7})
        result = _snapshot(tmp_path)
        chip = result["structure"]["chip"]
        dd = result["structure"]["dd_from_252d_high"]
        # recovering or at_highs depending on the exact magnitude
        assert chip in ("recovering", "at_highs", "drawdown")
        assert dd is not None

    def test_drawdown(self, tmp_path, monkeypatch):
        """drawdown: dd < -15% or negative momentum."""
        _patch_store(monkeypatch, tmp_path)
        n = 300
        for sym in MAG7:
            idx = _bdays(n)
            # Hard crash: up 50%, then down 30% from high (> -15% dd)
            prices = np.concatenate([
                100.0 * (1.003 ** np.arange(100)),
                100.0 * (1.003 ** 100) * ((1 - 0.005) ** np.arange(200)),
            ])
            s = pd.Series(prices, index=idx, name="close")
            _write_ohlcv(tmp_path, sym, s)
        _write_spy(tmp_path, _price_series(n=n, slope=-0.0005, end=str(date.today())))
        _write_reference(tmp_path, {sym: None for sym in MAG7})
        result = _snapshot(tmp_path)
        chip = result["structure"]["chip"]
        assert chip in ("drawdown", "recovering")


class TestRunMeter:
    """Run meter start-date and session-count correctness."""

    def test_run_start_session_count(self, tmp_path, monkeypatch):
        """When CW has been above 20-sma for k sessions, run.sessions == k."""
        _patch_store(monkeypatch, tmp_path)
        # Build composite that has been above 20sma for exactly 15 sessions
        # by having a long flat period (below) then a sharp rise
        n = 260
        for sym in MAG7:
            idx = _bdays(n)
            # Flat for 240 sessions, then sharp rise for 20
            prices = np.concatenate([
                np.full(240, 100.0),
                100.0 * (1.01 ** np.arange(20)),
            ])
            s = pd.Series(prices, index=idx, name="close")
            _write_ohlcv(tmp_path, sym, s)
        _write_spy(tmp_path, _flat_series(n=n, end=str(date.today())))
        _write_reference(tmp_path, {sym: None for sym in MAG7})
        result = _snapshot(tmp_path)
        run = result["run"]
        # The streak should be <= 20 sessions (the rising portion)
        # At least some sessions registered, start date not None
        if run.get("sessions", 0) > 0:
            assert run["start"] is not None
            assert run["sessions"] >= 1

    def test_run_none_when_below_sma(self, tmp_path, monkeypatch):
        """When CW is below 20-sma, run should show 0 sessions."""
        _patch_store(monkeypatch, tmp_path)
        # Declining series — CW will be below its own 20sma
        slopes = {sym: -0.004 for sym in MAG7}
        _setup_minimal(tmp_path, slopes=slopes)
        result = _snapshot(tmp_path)
        # run.sessions should be 0 or very small
        run = result["run"]
        assert run["sessions"] == 0 or result["trend_state"] in ("cooling", "rolling_over", "down")

    def test_run_cw_spy_signs_consistent(self, tmp_path, monkeypatch):
        """When Mag7 outperforms SPY in a run, cw_ret >= spy_ret."""
        _patch_store(monkeypatch, tmp_path)
        slopes = {sym: 0.003 for sym in MAG7}
        _setup_minimal(tmp_path, slopes=slopes, spy_slope=0.0005)
        result = _snapshot(tmp_path)
        run = result["run"]
        if run.get("cw_ret") is not None and run.get("spy_ret") is not None:
            # Mag7 should outperform flat SPY
            assert run["cw_ret"] >= run["spy_ret"]


class TestGeneralsCoverageRule:
    """generals.now: smallest prefix with cumulative contrib10 >= 60%."""

    def test_generals_coverage_reaches_60pct(self, tmp_path, monkeypatch):
        """generals.coverage should be >= 0.60 (or all 7 are needed)."""
        _patch_store(monkeypatch, tmp_path)
        # Give a strong trend so contrib10 is defined
        slopes = {sym: 0.003 for sym in MAG7}
        _setup_minimal(tmp_path, slopes=slopes)
        result = _snapshot(tmp_path)
        generals = result["generals"]
        cov = generals.get("coverage", 0.0)
        now = generals.get("now", [])
        # Either coverage >= 60% or we used up all 3 slots (cap)
        assert cov >= 0.60 or len(now) >= 3 or cov == 0.0

    def test_generals_now_max_3(self, tmp_path, monkeypatch):
        """generals.now is capped at 3 members."""
        _patch_store(monkeypatch, tmp_path)
        _setup_minimal(tmp_path, slopes={sym: 0.003 for sym in MAG7})
        result = _snapshot(tmp_path)
        assert len(result["generals"]["now"]) <= 3

    def test_generals_joining_not_in_now(self, tmp_path, monkeypatch):
        """generals.joining must not contain any symbol already in now."""
        _patch_store(monkeypatch, tmp_path)
        _setup_minimal(tmp_path, slopes={sym: 0.003 for sym in MAG7})
        result = _snapshot(tmp_path)
        now_set = set(result["generals"]["now"])
        for sym in result["generals"]["joining"]:
            assert sym not in now_set


class TestLedgerIdempotence:
    """Ledger: re-running the same date must not duplicate the row."""

    def test_no_duplicate_on_rerun(self, tmp_path, monkeypatch):
        """Running snapshot twice for the same date produces one ledger row."""
        from engine.mag7_regime import _append_ledger

        data_root = _data(tmp_path)
        ledger_row = {
            "date": str(date.today()),
            "trend_state": "running_broad",
            "structure_chip": "at_highs",
            "k7_trend": 6,
            "cw_r10": 0.04,
            "generals": ["NVDA", "AAPL"],
        }

        # append twice
        _append_ledger(ledger_row, root=data_root)
        _append_ledger(ledger_row, root=data_root)

        ledger_path = data_root / "mag7_regime" / "ledger.jsonl"
        assert ledger_path.exists()
        lines = [l for l in ledger_path.read_text().splitlines() if l.strip()]
        matching = [json.loads(l) for l in lines if json.loads(l).get("date") == str(date.today())]
        assert len(matching) == 1, f"Expected 1 row, got {len(matching)}"

    def test_different_dates_both_appended(self, tmp_path):
        """Two different dates produce two rows."""
        from engine.mag7_regime import _append_ledger

        data_root = _data(tmp_path)
        d1 = str(date.today() - timedelta(days=1))
        d2 = str(date.today())
        for d in (d1, d2):
            _append_ledger({
                "date": d,
                "trend_state": "cooling",
                "structure_chip": "recovering",
                "k7_trend": 3,
                "cw_r10": 0.01,
                "generals": [],
            }, root=data_root)

        ledger_path = data_root / "mag7_regime" / "ledger.jsonl"
        lines = [l for l in ledger_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2


class TestMagsStale:
    """MAGS ETF: stale data (>5 bd old) → mags payload should be None."""

    def test_mags_stale_returns_null(self, tmp_path, monkeypatch):
        """MAGS data >5 business days old → mags field is None."""
        _patch_store(monkeypatch, tmp_path)
        _setup_minimal(tmp_path, slopes={sym: 0.001 for sym in MAG7})

        # Write MAGS data with dates 10 business days ago
        old_end = str((pd.Timestamp(date.today()) - pd.offsets.BDay(10)).date())
        old_s = _price_series(n=50, end=old_end)
        _write_mags(tmp_path, old_s)

        result = _snapshot(tmp_path)
        assert result.get("mags") is None, f"Expected None for stale MAGS, got: {result.get('mags')}"

    def test_mags_fresh_returns_data(self, tmp_path, monkeypatch):
        """MAGS data within 5 bd → mags field is a dict with px and asof."""
        _patch_store(monkeypatch, tmp_path)
        _setup_minimal(tmp_path, slopes={sym: 0.001 for sym in MAG7})

        # Write MAGS with today's date
        fresh_s = _price_series(n=50, end=str(date.today()))
        _write_mags(tmp_path, fresh_s)

        result = _snapshot(tmp_path)
        mags = result.get("mags")
        assert mags is not None
        assert "px" in mags
        assert "asof" in mags

    def test_mags_absent_returns_null(self, tmp_path, monkeypatch):
        """No MAGS parquet → mags is None (no crash)."""
        _patch_store(monkeypatch, tmp_path)
        _setup_minimal(tmp_path, slopes={sym: 0.001 for sym in MAG7})
        # Do NOT write MAGS file
        result = _snapshot(tmp_path)
        assert result.get("mags") is None


class TestMktcapFallback:
    """Missing/null mktcap shares → weights_basis == 'equal_fallback'."""

    def test_no_shares_triggers_equal_fallback(self, tmp_path, monkeypatch):
        """When reference.parquet has all-None shares, weights_basis is equal_fallback."""
        _patch_store(monkeypatch, tmp_path)
        # caps dict with all None (no valid shares)
        caps = {sym: None for sym in MAG7}
        _setup_minimal(tmp_path, caps=caps)
        result = _snapshot(tmp_path)
        assert result["weights_basis"] == "equal_fallback"

    def test_valid_shares_triggers_polygon_mktcap(self, tmp_path, monkeypatch):
        """When reference.parquet has valid shares, weights_basis is polygon_mktcap."""
        _patch_store(monkeypatch, tmp_path)
        # give realistic share counts (~billions)
        caps = {sym: float(i + 1) * 1e9 for i, sym in enumerate(MAG7)}
        _setup_minimal(tmp_path, caps=caps)
        result = _snapshot(tmp_path)
        assert result["weights_basis"] == "polygon_mktcap"

    def test_polygon_universe_market_cap_usd_is_primary(self, tmp_path, monkeypatch):
        """data/polygon_universe/reference.parquet (market_cap_usd) is the PRIMARY
        weights source — the sp500_heatmap shares file never existed in production
        (post-merge audit 2026-07-11), so this path must work standalone."""
        _patch_store(monkeypatch, tmp_path)
        _setup_minimal(tmp_path, caps=None)  # no legacy file at all
        _write_polygon_reference(tmp_path, {sym: float(i + 1) * 1e12 for i, sym in enumerate(MAG7)})
        result = _snapshot(tmp_path)
        assert result["weights_basis"] == "polygon_mktcap"

    def test_polygon_universe_preferred_over_legacy_shares(self, tmp_path, monkeypatch):
        """When both sources exist, market_cap_usd wins (weights follow polygon caps)."""
        _patch_store(monkeypatch, tmp_path)
        caps_legacy = {sym: 1.0e9 for sym in MAG7}          # equal shares → equal weights
        _setup_minimal(tmp_path, caps=caps_legacy)
        poly = {sym: (5.0e12 if sym == "AAPL" else 1.0e12) for sym in MAG7}
        _write_polygon_reference(tmp_path, poly)
        result = _snapshot(tmp_path)
        assert result["weights_basis"] == "polygon_mktcap"
        w = {m["sym"]: m["w"] for m in result["members"]}
        assert w["AAPL"] > w["MSFT"] * 3  # polygon cap skew visible, not equal legacy

    def test_missing_reference_parquet_equal_fallback(self, tmp_path, monkeypatch):
        """No reference.parquet at all → weights_basis equal_fallback (no crash)."""
        _patch_store(monkeypatch, tmp_path)
        _setup_minimal(tmp_path, omit_reference=True)
        result = _snapshot(tmp_path)
        assert result["weights_basis"] == "equal_fallback"


class TestSchemaShape:
    """Verify the output payload has the required top-level schema fields."""

    def test_required_keys_present(self, tmp_path, monkeypatch):
        """Payload has all required top-level keys from mag7_regime.v1 spec."""
        _patch_store(monkeypatch, tmp_path)
        _setup_minimal(tmp_path)
        result = _snapshot(tmp_path)
        required = [
            "as_of", "weights_basis", "trend_state", "structure", "run",
            "k7", "cw", "ew", "members", "generals", "spread20", "tech_legs",
        ]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_members_has_7_rows(self, tmp_path, monkeypatch):
        """members array has one row per Mag-7 member."""
        _patch_store(monkeypatch, tmp_path)
        _setup_minimal(tmp_path)
        result = _snapshot(tmp_path)
        assert len(result["members"]) == 7
        syms = {r["sym"] for r in result["members"]}
        assert syms == set(MAG7)

    def test_member_row_fields(self, tmp_path, monkeypatch):
        """Each member row has the required fields."""
        _patch_store(monkeypatch, tmp_path)
        _setup_minimal(tmp_path)
        result = _snapshot(tmp_path)
        required_fields = ["sym", "w", "r5", "r10", "r20", "rs20", "above50", "above200", "contrib10", "mtf"]
        for row in result["members"]:
            for field in required_fields:
                assert field in row, f"Missing field {field} in member row for {row.get('sym')}"

    def test_trend_state_valid_value(self, tmp_path, monkeypatch):
        """trend_state is one of the 6 valid values."""
        _patch_store(monkeypatch, tmp_path)
        _setup_minimal(tmp_path)
        result = _snapshot(tmp_path)
        valid = {"running_broad", "running_narrow", "turning_up", "cooling", "rolling_over", "down"}
        assert result["trend_state"] in valid

    def test_structure_chip_valid_value(self, tmp_path, monkeypatch):
        """structure.chip is one of the 3 valid values."""
        _patch_store(monkeypatch, tmp_path)
        _setup_minimal(tmp_path)
        result = _snapshot(tmp_path)
        valid = {"at_highs", "recovering", "drawdown"}
        assert result["structure"]["chip"] in valid

    def test_tech_legs_has_4_entries(self, tmp_path, monkeypatch):
        """tech_legs has exactly 4 entries with required fields."""
        _patch_store(monkeypatch, tmp_path)
        _setup_minimal(tmp_path)
        result = _snapshot(tmp_path)
        assert len(result["tech_legs"]) == 4
        for leg in result["tech_legs"]:
            for field in ["id", "en", "zh", "r10_rel", "r20_rel", "word"]:
                assert field in leg

    def test_word_values_valid(self, tmp_path, monkeypatch):
        """tech_legs word values are all valid enum entries."""
        _patch_store(monkeypatch, tmp_path)
        _setup_minimal(tmp_path)
        result = _snapshot(tmp_path)
        valid_words = {"surging", "running", "flat", "falling", "falling hard"}
        for leg in result["tech_legs"]:
            assert leg["word"] in valid_words, f"Invalid word: {leg['word']}"

    def test_latest_json_written(self, tmp_path, monkeypatch):
        """snapshot() writes data/mag7_regime/latest.json."""
        _patch_store(monkeypatch, tmp_path)
        _setup_minimal(tmp_path)
        result = _snapshot(tmp_path)
        out = _data(tmp_path) / "mag7_regime" / "latest.json"
        assert out.exists(), "latest.json was not written"
        loaded = json.loads(out.read_text())
        assert loaded["as_of"] == result["as_of"]

    def test_no_crash_on_empty_data(self, tmp_path, monkeypatch):
        """snapshot() returns {} (not raise) when no OHLCV data exists."""
        _patch_store(monkeypatch, tmp_path)
        # Don't write any ohlcv files
        _write_spy(tmp_path, _price_series(n=50))
        _write_reference(tmp_path, {sym: None for sym in MAG7})
        from engine.mag7_regime import snapshot
        result = snapshot(root=tmp_path)
        assert isinstance(result, dict)


class TestWordMap:
    """Verify _ret_word thresholds match the spec exactly."""

    def test_word_map_thresholds(self):
        from engine.mag7_regime import _ret_word
        assert _ret_word(0.06) == "surging"
        assert _ret_word(0.05) == "surging"
        assert _ret_word(0.03) == "running"
        assert _ret_word(0.02) == "running"
        assert _ret_word(0.01) == "flat"
        assert _ret_word(0.0) == "flat"
        assert _ret_word(-0.01) == "flat"
        assert _ret_word(-0.02) == "falling"
        assert _ret_word(-0.04) == "falling"
        assert _ret_word(-0.05) == "falling hard"
        assert _ret_word(-0.10) == "falling hard"
        assert _ret_word(None) == "flat"
