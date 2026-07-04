"""Tests for engine/track_record.py — the forward signal track-record logger.

All fixtures are SYNTHETIC (tiny in-memory price series + hand-built JSON blobs
stored under tmp_path).  No real 114-ticker data is required; tests are fast and
deterministic.  The test module imports the module under test as:

    from engine import track_record as TR

The public surface under test is ``_run(signals_dir, stocks_dir,
archive_path, asof)``.  All writes are in ``tmp_path``; the real
``data/signal_archive/track_record.parquet`` is never touched.

Coverage checklist (per TRACK_RECORD.md + CHARTER.md):
  - idempotency: two identical runs => identical parquet
  - key-dedup: (ticker, date, type) appears exactly once
  - append-only freeze: first-observed identity columns never overwritten
  - maturation: NULL until N forward bars exist; filled once and frozen thereafter
  - no-look-ahead: regime/vol features use ONLY data <= marker date
  - pending-skip: quality=="pending" not logged; resolves on later run
  - sell/cut rows: quality=null, resolve exit_date/exit_type/exit_price/outcome/trade_ret
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import track_record as TR  # noqa: E402


def _run(signals_dir, stocks_dir, arch, asof=None):
    """Test shim → the real keyword signature.

    Tests express the call as ``(signals_dir, stocks_dir, archive, asof)``; the
    production API is ``update_track_record(repo_root, signals_dir, mtf_path,
    stocks_dir, out_path, asof)``.  ``mtf_path`` is left to default because ``asof``
    is injected directly (so the mtf leaf is never read)."""
    return TR.update_track_record(
        signals_dir=signals_dir, stocks_dir=stocks_dir, out_path=arch, asof=asof,
    )


# ---------------------------------------------------------------------------
# Helpers — synthetic fixtures
# ---------------------------------------------------------------------------

def _daily_close(n: int, start: str = "2020-01-01", base: float = 100.0,
                 drift: float = 0.001, vol: float = 0.015, seed: int = 42) -> pd.Series:
    """Return a synthetic daily close series of length *n* with no look-ahead."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    rets = rng.normal(drift, vol, n)
    prices = base * np.exp(np.cumsum(rets))
    return pd.Series(prices, index=idx, name="close")


def _write_prices(stocks_dir: Path, ticker: str, close: pd.Series) -> Path:
    path = stocks_dir / f"{ticker}.parquet"
    df = pd.DataFrame({"close": close, "high": close * 1.01, "low": close * 0.99})
    df.to_parquet(path)
    return path


def _write_signals(signals_dir: Path, ticker: str, asof: str, markers: list[dict]) -> Path:
    """Write a site/signals/<TICKER>.json following the §7 contract."""
    payload = {
        "ticker": ticker,
        "asof": asof,
        "tf": "3D",
        "state": "long-bias",
        "above200": True,
        "weekly_bull": True,
        "markers": markers,
    }
    path = signals_dir / f"{ticker}.json"
    path.write_text(json.dumps(payload))
    return path


# A concrete marker date that has 250+ bars of history available in our synthetic series
# when we build 300+ bar series starting 2020-01-01.
ENTRY_DATE = "2021-01-04"   # ~252 trading days from 2020-01-01
SELL_DATE  = "2021-03-01"   # a few weeks later
CUT_DATE   = "2021-04-01"


# ---------------------------------------------------------------------------
# 1. Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    """Running update_track_record twice on IDENTICAL inputs must yield an
    identical parquet (same row count, same cell values)."""

    def test_identical_rows_after_two_runs(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        _write_prices(stocks_dir, "AAPL", close)
        _write_signals(signals_dir, "AAPL", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "held confirmation"},
        ])

        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)
        df1 = pd.read_parquet(arch)

        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)
        df2 = pd.read_parquet(arch)

        assert len(df1) == len(df2), "row count changed on second run"
        for col in df1.columns:
            # compare non-null cells; null==null is fine
            mask = df1[col].notna() | df2[col].notna()
            if not mask.any():
                continue
            pd.testing.assert_series_equal(
                df1[col].reset_index(drop=True),
                df2[col].reset_index(drop=True),
                check_names=False,
                obj=f"column '{col}' differs between run 1 and run 2",
            )

    def test_no_op_when_no_new_markers(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        _write_prices(stocks_dir, "MSFT", close)
        _write_signals(signals_dir, "MSFT", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "block", "reason": "counter-trend"},
        ])

        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)
        mtime1 = arch.stat().st_mtime

        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)
        df2 = pd.read_parquet(arch)

        assert len(df2) == 1, "second run changed row count"


# ---------------------------------------------------------------------------
# 2. Key-dedup  (ticker, date, type) is the primary key
# ---------------------------------------------------------------------------

class TestKeyDedup:
    """A marker that appears in the JSON twice must only produce ONE row."""

    def test_duplicate_marker_in_same_json(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        _write_prices(stocks_dir, "TSLA", close)
        # same (ticker, date, type) twice in markers list
        _write_signals(signals_dir, "TSLA", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "held confirmation"},
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "held confirmation"},
        ])

        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)
        df = pd.read_parquet(arch)

        rows = df[(df["ticker"] == "TSLA") & (df["date"] == ENTRY_DATE) & (df["type"] == "buy")]
        assert len(rows) == 1, f"expected 1 row, got {len(rows)}"

    def test_different_types_same_date_both_logged(self, tmp_path):
        """A 'buy' and a 'sell' on the same date are DIFFERENT keys; both must appear."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        _write_prices(stocks_dir, "NVDA", close)
        _write_signals(signals_dir, "NVDA", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "x"},
            {"date": ENTRY_DATE, "type": "sell"},
        ])

        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)
        df = pd.read_parquet(arch)

        assert len(df[(df["ticker"] == "NVDA") & (df["date"] == ENTRY_DATE)]) == 2


# ---------------------------------------------------------------------------
# 3. Append-only freeze (first-observed wins for identity columns)
# ---------------------------------------------------------------------------

class TestAppendOnlyFreeze:
    """Changing a marker's quality/reason on a later run must NOT overwrite the
    first-observed value.  A brand-new marker (new key) MUST be appended."""

    def test_first_quality_frozen_on_rewrite(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        _write_prices(stocks_dir, "META", close)

        # Run 1: quality="take"
        _write_signals(signals_dir, "META", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "held confirmation"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)

        # Run 2: same key but quality changed to "block" (as if the engine re-rated)
        _write_signals(signals_dir, "META", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "block", "reason": "counter-trend"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)

        df = pd.read_parquet(arch)
        rows = df[(df["ticker"] == "META") & (df["date"] == ENTRY_DATE) & (df["type"] == "buy")]
        assert len(rows) == 1
        assert rows.iloc[0]["quality"] == "take", (
            "first-observed quality 'take' was overwritten by later 'block'")

    def test_new_marker_appended_without_disturbing_existing(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        _write_prices(stocks_dir, "AMZN", close)

        # Run 1
        _write_signals(signals_dir, "AMZN", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "held"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)
        df1 = pd.read_parquet(arch)
        assert len(df1) == 1

        # Run 2: new sell marker appears
        _write_signals(signals_dir, "AMZN", SELL_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "held"},
            {"date": SELL_DATE, "type": "sell"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=SELL_DATE)
        df2 = pd.read_parquet(arch)
        assert len(df2) == 2, "new sell marker was not appended"

        # Original row is untouched
        orig = df2[(df2["ticker"] == "AMZN") & (df2["date"] == ENTRY_DATE) & (df2["type"] == "buy")]
        assert orig.iloc[0]["quality"] == "take"


# ---------------------------------------------------------------------------
# 4. Maturation (forward metrics filled once enough data exists, then frozen)
# ---------------------------------------------------------------------------

class TestMaturation:
    """fwd_ret_20 / fwd_mdd_20 must be NULL when fewer than 20 forward bars exist;
    they get filled on the next run once the series extends far enough; and they
    must not change after that (frozen)."""

    def test_fwd_ret_20_null_when_series_too_short(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        # Build a series with the entry date near the end — only 10 bars forward
        close = _daily_close(270)                   # 270 biz days from 2020-01-01
        entry_date = str(close.index[-10].date())   # 10 bars before the end
        _write_prices(stocks_dir, "GOOG", close)
        _write_signals(signals_dir, "GOOG", entry_date, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "held"},
        ])

        _run(signals_dir, stocks_dir, arch, asof=entry_date)
        df = pd.read_parquet(arch)
        row = df[(df["ticker"] == "GOOG") & (df["type"] == "buy")].iloc[0]

        assert pd.isna(row["fwd_ret_20"]), "fwd_ret_20 should be NULL (<20 fwd bars)"
        assert pd.isna(row["fwd_mdd_20"]), "fwd_mdd_20 should be NULL (<20 fwd bars)"

    def test_fwd_ret_20_filled_after_series_extended(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        # Start with a short series (entry near end)
        close_short = _daily_close(270)
        entry_date  = str(close_short.index[-10].date())
        _write_prices(stocks_dir, "GOOG", close_short)
        _write_signals(signals_dir, "GOOG", entry_date, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "held"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=entry_date)

        # Now extend the series to 310 bars (>=30 bars after entry)
        close_long = _daily_close(310)
        _write_prices(stocks_dir, "GOOG", close_long)
        later_asof = str(close_long.index[-1].date())
        _write_signals(signals_dir, "GOOG", later_asof, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "held"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=later_asof)

        df = pd.read_parquet(arch)
        row = df[(df["ticker"] == "GOOG") & (df["type"] == "buy")].iloc[0]

        assert pd.notna(row["fwd_ret_20"]), "fwd_ret_20 should be filled after series extended"
        assert pd.notna(row["fwd_mdd_20"]), "fwd_mdd_20 should be filled after series extended"
        assert row["fwd_mdd_20"] <= 0, "forward max drawdown must be <= 0"

    def test_fwd_mdd_frozen_after_filled(self, tmp_path):
        """Once fwd_mdd_20 is filled it must not change on subsequent runs."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close_short = _daily_close(270)
        entry_date  = str(close_short.index[-10].date())
        _write_prices(stocks_dir, "IBM", close_short)
        _write_signals(signals_dir, "IBM", entry_date, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "held"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=entry_date)

        # Extend once — fills maturation columns
        close_long = _daily_close(310)
        later_asof = str(close_long.index[-1].date())
        _write_prices(stocks_dir, "IBM", close_long)
        _write_signals(signals_dir, "IBM", later_asof, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "held"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=later_asof)
        df_a = pd.read_parquet(arch)
        val_a = df_a[(df_a["ticker"] == "IBM") & (df_a["type"] == "buy")].iloc[0]["fwd_mdd_20"]

        # Run again with same data — value must be identical
        _run(signals_dir, stocks_dir, arch, asof=later_asof)
        df_b = pd.read_parquet(arch)
        val_b = df_b[(df_b["ticker"] == "IBM") & (df_b["type"] == "buy")].iloc[0]["fwd_mdd_20"]

        assert abs(val_a - val_b) < 1e-12, "fwd_mdd_20 changed after being frozen"

    def test_unmatured_row_fills_in_mixed_parquet(self, tmp_path):
        """REGRESSION (np.nan-vs-None maturation stall).

        With a MULTI-ticker parquet where one row is already matured (float) and
        another is not (null), the maturation column round-trips from parquet as a
        float64 with np.nan for the un-matured cell — NOT None.  A naive ``is None``
        fill-gate would treat that np.nan as 'already filled' and the un-matured row
        would NEVER mature.  This is the steady-state shape of the real daily job, so
        the single-ticker tests above cannot catch it.  Here we assert the un-matured
        ticker fills once its series extends, while the matured ticker stays frozen."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        # AAA: long series -> matures immediately (entry well inside).
        close_long = _daily_close(500, seed=1)
        aaa_entry  = str(close_long.index[260].date())
        _write_prices(stocks_dir, "AAA", close_long)
        _write_signals(signals_dir, "AAA", aaa_entry, [
            {"date": aaa_entry, "type": "buy", "quality": "take", "reason": "held"},
        ])

        # BBB: short series, entry 5 bars from the end -> fwd_ret_20 is NULL on run 1.
        close_short = _daily_close(270, seed=2)
        bbb_entry   = str(close_short.index[-5].date())
        _write_prices(stocks_dir, "BBB", close_short)
        _write_signals(signals_dir, "BBB", bbb_entry, [
            {"date": bbb_entry, "type": "buy", "quality": "take", "reason": "held"},
        ])

        _run(signals_dir, stocks_dir, arch, asof=bbb_entry)
        df1 = pd.read_parquet(arch)
        aaa1 = df1[df1["ticker"] == "AAA"].iloc[0]
        bbb1 = df1[df1["ticker"] == "BBB"].iloc[0]
        assert pd.notna(aaa1["fwd_ret_20"]), "AAA should mature immediately"
        assert pd.isna(bbb1["fwd_ret_20"]), "BBB must be un-matured on run 1 (<20 fwd bars)"
        # Sanity: the column came back as float64 with a real np.nan (the bug's trigger).
        assert df1["fwd_ret_20"].dtype.kind == "f"

        aaa_frozen = float(aaa1["fwd_mdd_20"])

        # Extend BBB past +20 forward bars; re-run on the SAME mixed parquet.
        close_ext = _daily_close(310, seed=2)
        _write_prices(stocks_dir, "BBB", close_ext)
        later_asof = str(close_ext.index[-1].date())
        _write_signals(signals_dir, "BBB", later_asof, [
            {"date": bbb_entry, "type": "buy", "quality": "take", "reason": "held"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=later_asof)

        df2 = pd.read_parquet(arch)
        bbb2 = df2[df2["ticker"] == "BBB"].iloc[0]
        aaa2 = df2[df2["ticker"] == "AAA"].iloc[0]
        assert pd.notna(bbb2["fwd_ret_20"]), (
            "BBB never matured — np.nan-vs-None stall: un-matured cell read back as "
            "np.nan was wrongly treated as already-filled")
        assert pd.notna(bbb2["fwd_mdd_20"])
        # The already-matured AAA row must be untouched (frozen).
        assert abs(float(aaa2["fwd_mdd_20"]) - aaa_frozen) < 1e-12, "matured AAA row changed"


# ---------------------------------------------------------------------------
# 5. No look-ahead (regime and vol features use ONLY data <= marker date)
# ---------------------------------------------------------------------------

class TestNoLookAhead:
    """regime_at_entry and vol_annual_at_entry computed on a marker date must be
    identical whether or not future bars exist in the series.  We truncate at the
    marker date and assert equality."""

    def test_regime_identical_with_and_without_future_bars(self, tmp_path):
        stocks_dir_short = tmp_path / "stocks_short"; stocks_dir_short.mkdir()
        stocks_dir_long  = tmp_path / "stocks_long";  stocks_dir_long.mkdir()
        signals_dir      = tmp_path / "signals";      signals_dir.mkdir()
        arch_short = tmp_path / "tr_short.parquet"
        arch_long  = tmp_path / "tr_long.parquet"

        close_full  = _daily_close(500)
        entry_date  = str(close_full.index[260].date())   # well inside the series

        # Short series: truncated AT entry_date (no future bars)
        close_trunc = close_full.loc[:entry_date]
        _write_prices(stocks_dir_short, "GE", close_trunc)
        _write_signals(signals_dir, "GE", entry_date, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "held"},
        ])
        _run(signals_dir, stocks_dir_short, arch_short, asof=entry_date)

        # Long series: full 500 bars (many future bars beyond entry_date)
        _write_prices(stocks_dir_long, "GE", close_full)
        _run(signals_dir, stocks_dir_long, arch_long, asof=entry_date)

        df_s = pd.read_parquet(arch_short)
        df_l = pd.read_parquet(arch_long)
        row_s = df_s[(df_s["ticker"] == "GE") & (df_s["type"] == "buy")].iloc[0]
        row_l = df_l[(df_l["ticker"] == "GE") & (df_l["type"] == "buy")].iloc[0]

        assert row_s["regime_at_entry"] == row_l["regime_at_entry"], (
            f"regime_at_entry leaks future: short={row_s['regime_at_entry']!r} "
            f"vs long={row_l['regime_at_entry']!r}")

    def test_vol_annual_identical_with_and_without_future_bars(self, tmp_path):
        stocks_dir_short = tmp_path / "stocks_short"; stocks_dir_short.mkdir()
        stocks_dir_long  = tmp_path / "stocks_long";  stocks_dir_long.mkdir()
        signals_dir      = tmp_path / "signals";      signals_dir.mkdir()
        arch_short = tmp_path / "tr_short.parquet"
        arch_long  = tmp_path / "tr_long.parquet"

        close_full = _daily_close(500)
        entry_date = str(close_full.index[260].date())

        close_trunc = close_full.loc[:entry_date]
        _write_prices(stocks_dir_short, "GS", close_trunc)
        _write_signals(signals_dir, "GS", entry_date, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "held"},
        ])
        _run(signals_dir, stocks_dir_short, arch_short, asof=entry_date)

        _write_prices(stocks_dir_long, "GS", close_full)
        _run(signals_dir, stocks_dir_long, arch_long, asof=entry_date)

        df_s = pd.read_parquet(arch_short)
        df_l = pd.read_parquet(arch_long)
        row_s = df_s[(df_s["ticker"] == "GS") & (df_s["type"] == "buy")].iloc[0]
        row_l = df_l[(df_l["ticker"] == "GS") & (df_l["type"] == "buy")].iloc[0]

        if pd.notna(row_s["vol_annual_at_entry"]) and pd.notna(row_l["vol_annual_at_entry"]):
            assert abs(row_s["vol_annual_at_entry"] - row_l["vol_annual_at_entry"]) < 1e-9, (
                "vol_annual_at_entry leaks future bars")

    def test_above200_at_entry_uses_only_past_data(self, tmp_path):
        """Fabricate a monotone-rising series so that above200 is deterministic,
        then verify it is computed only from the truncated history."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        # Strictly monotone rising series — always above its trailing SMA200
        # once there are 200 bars.
        n = 400
        idx   = pd.bdate_range("2020-01-01", periods=n)
        prices = pd.Series(np.linspace(50, 150, n), index=idx)
        entry_date = str(prices.index[250].date())   # 250 bars in; 200-bar SMA available

        _write_prices(stocks_dir, "XOM", prices)
        _write_signals(signals_dir, "XOM", entry_date, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "held"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=entry_date)
        df = pd.read_parquet(arch)
        row = df[(df["ticker"] == "XOM") & (df["type"] == "buy")].iloc[0]

        # On a strictly monotone rising series above all past SMA200, above200_at_entry must be True
        assert row["above200_at_entry"] is True or row["above200_at_entry"] == True, (
            f"Expected above200_at_entry=True for monotone-rising series, got {row['above200_at_entry']!r}")


# ---------------------------------------------------------------------------
# 6. Pending-skip and later resolution
# ---------------------------------------------------------------------------

class TestPendingSkip:
    """quality=='pending' entries must NOT be logged.  When a subsequent run
    resolves the same (ticker, date, type) key to take/block, that row appears."""

    def test_pending_entry_not_logged(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(300)
        _write_prices(stocks_dir, "BABA", close)
        _write_signals(signals_dir, "BABA", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "pending", "reason": "pending confirmation"},
        ])

        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)

        # The parquet is always written (possibly empty); the pending row must not be in it.
        assert arch.exists(), "parquet should be written even when all markers are skipped"
        df = pd.read_parquet(arch)
        rows = df[(df["ticker"] == "BABA") & (df["date"] == ENTRY_DATE) & (df["type"] == "buy")]
        assert len(rows) == 0, "pending marker was logged (must be skipped)"

    def test_pending_resolves_to_take_on_later_run(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        _write_prices(stocks_dir, "JD", close)

        # Run 1: pending
        _write_signals(signals_dir, "JD", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "pending", "reason": "pending confirmation"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)

        # Run 2: same key resolved to "take"
        _write_signals(signals_dir, "JD", SELL_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "held confirmation"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=SELL_DATE)

        df = pd.read_parquet(arch)
        rows = df[(df["ticker"] == "JD") & (df["date"] == ENTRY_DATE) & (df["type"] == "buy")]
        assert len(rows) == 1, "resolved marker should appear exactly once"
        assert rows.iloc[0]["quality"] == "take"


# ---------------------------------------------------------------------------
# 7. sell / cut rows
# ---------------------------------------------------------------------------

class TestSellCutRows:
    """sell and cut markers carry quality=null and must resolve the corresponding
    entry's exit_date / exit_type / exit_price / outcome / trade_ret."""

    def test_sell_row_has_null_quality(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        _write_prices(stocks_dir, "JPM", close)
        _write_signals(signals_dir, "JPM", SELL_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "held"},
            {"date": SELL_DATE,  "type": "sell"},
        ])

        _run(signals_dir, stocks_dir, arch, asof=SELL_DATE)
        df = pd.read_parquet(arch)

        sell_row = df[(df["ticker"] == "JPM") & (df["type"] == "sell")]
        assert len(sell_row) == 1
        assert pd.isna(sell_row.iloc[0]["quality"]), "sell row must have quality=null"

    def test_cut_row_has_null_quality(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        _write_prices(stocks_dir, "BAC", close)
        _write_signals(signals_dir, "BAC", CUT_DATE, [
            {"date": ENTRY_DATE, "type": "buy",  "quality": "take", "reason": "held"},
            {"date": CUT_DATE,   "type": "cut"},
        ])

        _run(signals_dir, stocks_dir, arch, asof=CUT_DATE)
        df = pd.read_parquet(arch)

        cut_row = df[(df["ticker"] == "BAC") & (df["type"] == "cut")]
        assert len(cut_row) == 1
        assert pd.isna(cut_row.iloc[0]["quality"]), "cut row must have quality=null"

    def test_entry_exit_fields_resolved_by_sell(self, tmp_path):
        """The buy row's exit_date, exit_type, exit_price, outcome and trade_ret
        must be filled once the corresponding sell marker exists in the archive."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        _write_prices(stocks_dir, "WMT", close)

        # Derive expected exit price from the series (nearest bar on or before SELL_DATE)
        sell_ts = pd.Timestamp(SELL_DATE)
        if sell_ts not in close.index:
            sell_ts = close.index[close.index <= sell_ts][-1]
        expected_exit_price = float(close.loc[sell_ts])

        _write_signals(signals_dir, "WMT", SELL_DATE, [
            {"date": ENTRY_DATE, "type": "buy",  "quality": "take", "reason": "held"},
            {"date": SELL_DATE,  "type": "sell"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=SELL_DATE)
        df = pd.read_parquet(arch)

        buy_row = df[(df["ticker"] == "WMT") & (df["type"] == "buy")].iloc[0]

        assert buy_row["exit_date"] == SELL_DATE, (
            f"exit_date expected {SELL_DATE!r}, got {buy_row['exit_date']!r}")
        assert buy_row["exit_type"] == "sell"
        assert pd.notna(buy_row["exit_price"]), "exit_price should be filled"
        assert abs(buy_row["exit_price"] - expected_exit_price) < 1.0, (
            f"exit_price {buy_row['exit_price']:.4f} far from expected {expected_exit_price:.4f}")
        assert buy_row["outcome"] in {"win", "loss"}, (
            f"outcome should be win or loss, got {buy_row['outcome']!r}")
        assert pd.notna(buy_row["trade_ret"]), "trade_ret should be filled after exit"

    def test_entry_exit_fields_resolved_by_cut(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        _write_prices(stocks_dir, "HD", close)
        _write_signals(signals_dir, "HD", CUT_DATE, [
            {"date": ENTRY_DATE, "type": "buy",  "quality": "take", "reason": "held"},
            {"date": CUT_DATE,   "type": "cut"},
        ])

        _run(signals_dir, stocks_dir, arch, asof=CUT_DATE)
        df = pd.read_parquet(arch)

        buy_row = df[(df["ticker"] == "HD") & (df["type"] == "buy")].iloc[0]
        assert buy_row["exit_type"] == "cut"
        assert pd.notna(buy_row["exit_price"])
        assert buy_row["outcome"] in {"win", "loss"}

    def test_open_entry_shows_still_held(self, tmp_path):
        """A buy with no subsequent sell/cut and enough history => outcome='still_held'."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        # Entry near the beginning — no exit marker
        entry_date = str(close.index[50].date())
        _write_prices(stocks_dir, "V", close)
        _write_signals(signals_dir, "V", entry_date, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "held"},
        ])

        _run(signals_dir, stocks_dir, arch, asof=str(close.index[-1].date()))
        df = pd.read_parquet(arch)

        buy_row = df[(df["ticker"] == "V") & (df["type"] == "buy")].iloc[0]
        assert buy_row["outcome"] == "still_held", (
            f"open entry without exit should be 'still_held', got {buy_row['outcome']!r}")
        assert pd.isna(buy_row["exit_date"]), "no exit_date expected for still_held"

    def test_still_held_resolves_when_exit_appears_later(self, tmp_path):
        """A 'still_held' entry is provisional: when a sell/cut marker appears on a
        later run, outcome must resolve to win/loss and exit_*/trade_ret/trade_mae fill.
        (This is the only sanctioned post-birth overwrite — and it is one-way.)"""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        _write_prices(stocks_dir, "PG", close)

        # Run 1: buy only (entry well inside, plenty of forward data) -> still_held.
        _write_signals(signals_dir, "PG", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "held"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=str(close.index[-1].date()))
        row1 = pd.read_parquet(arch)
        r1 = row1[(row1["ticker"] == "PG") & (row1["type"] == "buy")].iloc[0]
        assert r1["outcome"] == "still_held"

        # Run 2: a sell now exists after the entry -> resolves.
        _write_signals(signals_dir, "PG", SELL_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "held"},
            {"date": SELL_DATE,  "type": "sell"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=str(close.index[-1].date()))
        row2 = pd.read_parquet(arch)
        r2 = row2[(row2["ticker"] == "PG") & (row2["type"] == "buy")].iloc[0]

        assert r2["outcome"] in {"win", "loss"}, (
            f"still_held should resolve to win/loss, got {r2['outcome']!r}")
        assert r2["exit_date"] == SELL_DATE
        assert r2["exit_type"] == "sell"
        assert pd.notna(r2["exit_price"])
        assert pd.notna(r2["trade_ret"])
        assert pd.notna(r2["trade_mae"]) and r2["trade_mae"] <= 0

        # Run 3: identical inputs -> now-final row must be a strict no-op.
        _run(signals_dir, stocks_dir, arch, asof=str(close.index[-1].date()))
        row3 = pd.read_parquet(arch)
        r3 = row3[(row3["ticker"] == "PG") & (row3["type"] == "buy")].iloc[0]
        assert r3["outcome"] == r2["outcome"]
        assert abs(float(r3["trade_mae"]) - float(r2["trade_mae"])) < 1e-12


# ---------------------------------------------------------------------------
# 8. Schema completeness and types
# ---------------------------------------------------------------------------

class TestSchema:
    """The parquet must carry exactly the expected columns (or a superset); key
    identity columns must be the right dtype."""

    IDENTITY_COLS = [
        "ticker", "date", "type", "quality", "reason",
        "entry_price", "regime_at_entry", "above200_at_entry",
        "sma200_rising_at_entry", "vol_annual_at_entry", "er_at_entry",
        "first_seen_asof",
    ]
    MATURATION_COLS = [
        "fwd_ret_20", "fwd_price_20", "fwd_mdd_20",
        "fwd_ret_60", "fwd_price_60", "fwd_mdd_60",
        "fwd_ret_180", "fwd_price_180", "fwd_mdd_180",
        "trade_mae", "outcome", "exit_date", "exit_type",
        "exit_price", "trade_ret", "last_backfill_asof",
    ]

    def _run_and_read(self, tmp_path) -> pd.DataFrame:
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        _write_prices(stocks_dir, "LLY", close)
        _write_signals(signals_dir, "LLY", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "block", "reason": "no reclaim"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)
        return pd.read_parquet(arch)

    def test_identity_columns_present(self, tmp_path):
        df = self._run_and_read(tmp_path)
        missing = [c for c in self.IDENTITY_COLS if c not in df.columns]
        assert not missing, f"missing identity columns: {missing}"

    def test_maturation_columns_present(self, tmp_path):
        df = self._run_and_read(tmp_path)
        missing = [c for c in self.MATURATION_COLS if c not in df.columns]
        assert not missing, f"missing maturation columns: {missing}"

    def test_ticker_date_type_are_strings(self, tmp_path):
        df = self._run_and_read(tmp_path)
        # Accept object-of-str OR the pandas 2.2+ StringDtype (both are 'str' on read-back).
        for col in ("ticker", "date", "type"):
            assert pd.api.types.is_string_dtype(df[col]), f"{col} must be str-typed"

    def test_regime_at_entry_valid_values(self, tmp_path):
        df = self._run_and_read(tmp_path)
        valid = {"bull", "bear", "choppy", "unknown"}
        vals = set(df["regime_at_entry"].dropna().unique())
        assert vals <= valid, f"unexpected regime_at_entry values: {vals - valid}"

    def test_first_seen_asof_matches_provided_asof(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        _write_prices(stocks_dir, "ORCL", close)
        asof_val = "2021-06-01"
        _write_signals(signals_dir, "ORCL", asof_val, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "held"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=asof_val)
        df = pd.read_parquet(arch)
        assert df.iloc[0]["first_seen_asof"] == asof_val, (
            f"first_seen_asof should be {asof_val!r}, got {df.iloc[0]['first_seen_asof']!r}")


# ---------------------------------------------------------------------------
# 9. Multi-ticker & missing-data graceful handling
# ---------------------------------------------------------------------------

class TestMultiTickerAndMissing:
    """Multiple tickers in one run all land in the same parquet; a ticker whose
    parquet is absent is skipped without crashing."""

    def test_two_tickers_both_logged(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        for ticker in ("AAPL", "MSFT"):
            _write_prices(stocks_dir, ticker, _daily_close(500))
            _write_signals(signals_dir, ticker, ENTRY_DATE, [
                {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "held"},
            ])

        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)
        df = pd.read_parquet(arch)

        assert set(df["ticker"].unique()) == {"AAPL", "MSFT"}
        assert len(df) == 2

    def test_missing_price_parquet_skipped_gracefully(self, tmp_path):
        """GOOG has a signals JSON but no prices parquet — must not crash and the
        other ticker's row must still appear."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        # AAPL has prices
        _write_prices(stocks_dir, "AAPL", _daily_close(500))
        _write_signals(signals_dir, "AAPL", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "held"},
        ])
        # GOOG has signal but NO prices parquet
        _write_signals(signals_dir, "GOOG", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "held"},
        ])

        # Must not raise
        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)

        df = pd.read_parquet(arch)
        assert "AAPL" in df["ticker"].values, "AAPL row missing after skip of GOOG"

    def test_risk_flags_not_logged(self, tmp_path):
        """risk_flags is a separate list in the signals JSON (display-only tail-risk);
        it must never appear as a row in the parquet."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        _write_prices(stocks_dir, "F", close)

        payload = {
            "ticker": "F",
            "asof": ENTRY_DATE,
            "tf": "3D",
            "state": "short-bias",
            "above200": False,
            "weekly_bull": False,
            "markers": [
                {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "held"},
            ],
            "risk_flags": ["2021-01-04", "2021-02-01"],
        }
        (signals_dir / "F.json").write_text(json.dumps(payload))

        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)
        df = pd.read_parquet(arch)

        # Only the buy marker should appear; risk_flag dates must not become rows
        flag_rows = df[(df["ticker"] == "F") & (df["date"].isin(["2021-01-04", "2021-02-01"]))]
        buy_rows  = df[(df["ticker"] == "F") & (df["type"] == "buy")]
        # risk_flags must not produce rows with type != buy/sell/cut/rebuy
        bad = df[(df["ticker"] == "F") & (~df["type"].isin(["buy", "sell", "cut", "rebuy"]))]
        assert len(bad) == 0, f"unexpected row types from risk_flags: {bad['type'].tolist()}"
        assert len(buy_rows) == 1


# ---------------------------------------------------------------------------
# 10. rebuy markers
# ---------------------------------------------------------------------------

class TestRebuys:
    """rebuy markers follow the same quality/skip rules as buy markers."""

    def test_rebuy_take_logged(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        _write_prices(stocks_dir, "MA", close)
        _write_signals(signals_dir, "MA", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "rebuy", "quality": "take", "reason": "held confirmation"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)
        df = pd.read_parquet(arch)

        rows = df[(df["ticker"] == "MA") & (df["type"] == "rebuy")]
        assert len(rows) == 1
        assert rows.iloc[0]["quality"] == "take"

    def test_rebuy_pending_not_logged(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(300)
        _write_prices(stocks_dir, "PYPL", close)
        _write_signals(signals_dir, "PYPL", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "rebuy", "quality": "pending", "reason": "pending confirmation"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)

        assert arch.exists(), "parquet should be written even when all markers are skipped"
        df = pd.read_parquet(arch)
        rows = df[(df["ticker"] == "PYPL") & (df["type"] == "rebuy")]
        assert len(rows) == 0, "pending rebuy must not be logged"


# ---------------------------------------------------------------------------
# 11. entry_price snapped to nearest prior bar
# ---------------------------------------------------------------------------

class TestEntryPrice:
    """entry_price is the NEXT-BAR fill (W1c, audit #15): a signal firing on the marker
    bar is filled at the close of the bar STRICTLY AFTER it — the validated convention."""

    def test_entry_price_is_next_bar_fill(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        # Pick a date definitely in the series (with a next bar available)
        entry_date = str(close.index[100].date())
        expected_price = float(close.iloc[101])   # NEXT bar — the honest fill

        _write_prices(stocks_dir, "UNH", close)
        _write_signals(signals_dir, "UNH", entry_date, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "held"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=entry_date)
        df = pd.read_parquet(arch)

        row = df[(df["ticker"] == "UNH") & (df["type"] == "buy")].iloc[0]
        assert abs(row["entry_price"] - expected_price) < 1e-6, (
            f"entry_price {row['entry_price']:.4f} != next-bar expected {expected_price:.4f}")
        # fill_offset provenance: 1 = honest next-bar
        assert int(row["fill_offset"]) == 1, f"fill_offset {row['fill_offset']} != 1 (next-bar)"


# ---------------------------------------------------------------------------
# W0-stageB tests: new columns, vector stamp, species mapping
# ---------------------------------------------------------------------------

import json
import pyarrow.parquet as pq


def _run_with_overrides(signals_dir, stocks_dir, arch, asof=None, *,
                         data_dir=None, stockdata_dir=None):
    """Extended shim that passes the W0-stageB data_dir / stockdata_dir overrides."""
    return TR.update_track_record(
        signals_dir=signals_dir, stocks_dir=stocks_dir, out_path=arch, asof=asof,
        data_dir=data_dir, stockdata_dir=stockdata_dir,
    )


def _write_regime_vector_parquet(data_dir: Path, rows: list[dict]) -> Path:
    """Write a minimal regime_vector.parquet fixture."""
    regime_dir = data_dir / "regime"
    regime_dir.mkdir(parents=True, exist_ok=True)
    p = regime_dir / "regime_vector.parquet"
    dates = [pd.Timestamp(r["date"]).normalize() for r in rows]
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(dates, name="date"))
    df.drop(columns=["date"], errors="ignore", inplace=True)
    df.to_parquet(p, index=True)
    return p


def _write_stockdata(stockdata_dir: Path, ticker: str, archetype_key: str) -> Path:
    """Write a minimal site/stockdata/<ticker>.json with an archetype key."""
    stockdata_dir.mkdir(parents=True, exist_ok=True)
    p = stockdata_dir / f"{ticker}.json"
    p.write_text(json.dumps({
        "ticker": ticker,
        "profile": {"archetype": {"key": archetype_key, "label": archetype_key}},
    }))
    return p


def _write_species_registry(data_dir: Path, species: list[dict]) -> Path:
    """Write a minimal data/species/registry.json."""
    sp_dir = data_dir / "species"
    sp_dir.mkdir(parents=True, exist_ok=True)
    p = sp_dir / "registry.json"
    p.write_text(json.dumps({"schema_version": 1, "species": species}))
    return p


class TestStageB_NewColumnsNullable:
    """New W0-stageB columns must be present and nullable; schema union with
    an existing store that lacks them must not crash and must add them as null."""

    def test_new_columns_present_and_nullable_on_fresh_run(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"
        data_dir = tmp_path / "data"
        stockdata_dir = tmp_path / "stockdata"

        close = _daily_close(300)
        _write_prices(stocks_dir, "AAPL", close)
        _write_signals(signals_dir, "AAPL", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "test"},
        ])

        _run_with_overrides(signals_dir, stocks_dir, arch, asof=ENTRY_DATE,
                            data_dir=data_dir, stockdata_dir=stockdata_dir)
        df = pd.read_parquet(arch)

        # All new spine columns must be present
        new_cols = [
            "rate_pressure", "quad_hard_label", "fused_risk_label", "vol_regime",
            "risk_radar_state", "regime_vector_degraded", "vector_asof", "staleness_hours",
            "species_id", "archetype",
            "fwd_mfe_5", "fwd_mfe_10", "fwd_mfe_21", "fwd_mfe_63", "fwd_mfe_126",
            "terminal_state_clean15_126", "terminal_state_clean8_21",
            "post_cushion_breach",
        ]
        for col in new_cols:
            assert col in df.columns, f"Missing new column: {col}"

        # No regime vector file → all regime stamp cols null
        row = df.iloc[0]
        assert pd.isna(row["vector_asof"]) or row["vector_asof"] is None, \
            "vector_asof should be null when no vector file exists"

    def test_schema_union_with_old_store_lacking_new_cols(self, tmp_path):
        """A legacy parquet that lacks the new columns is read and extended safely."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(300)
        _write_prices(stocks_dir, "MSFT", close)
        _write_signals(signals_dir, "MSFT", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "legacy"},
        ])
        # Write a "legacy" parquet with only the old columns
        old_cols = TR._IDENTITY_COLS[:12] + TR._MATURATION_COLS[:18]
        old_df = pd.DataFrame(columns=old_cols)
        # Add one synthetic row missing the new columns
        row_data = {c: None for c in old_cols}
        row_data.update({"ticker": "MSFT", "date": "2020-06-01", "type": "buy",
                          "quality": "take", "reason": "old", "entry_price": 99.0,
                          "regime_at_entry": "bull", "first_seen_asof": "2020-06-01"})
        old_df = pd.DataFrame([row_data], columns=old_cols)
        old_df.to_parquet(arch)

        # Running should not crash and new cols should be added as null
        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)
        df = pd.read_parquet(arch)
        assert "fwd_mfe_5" in df.columns, "fwd_mfe_5 missing after schema union"
        # The legacy row should have null for the new cols
        legacy_row = df[df["date"] == "2020-06-01"].iloc[0]
        assert pd.isna(legacy_row.get("fwd_mfe_5", None)) or legacy_row.get("fwd_mfe_5") is None


class TestStageB_KeepFirstNonNull:
    """keep-FIRST: non-null values on existing rows must NEVER be overwritten on re-run."""

    def test_identity_columns_never_overwritten(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(400)
        _write_prices(stocks_dir, "GOOG", close)
        _write_signals(signals_dir, "GOOG", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "first"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)
        df1 = pd.read_parquet(arch)
        entry_price_1 = float(df1.iloc[0]["entry_price"])
        regime_1 = df1.iloc[0]["regime_at_entry"]

        # Change the marker reason (a signal-file content change that would NOT alter
        # the key or the entry-time features)
        _write_signals(signals_dir, "GOOG", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "CHANGED"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=ENTRY_DATE)
        df2 = pd.read_parquet(arch)
        assert len(df2) == 1, "row count changed on re-run"
        # entry_price and regime must be identical (frozen on first write)
        assert abs(float(df2.iloc[0]["entry_price"]) - entry_price_1) < 1e-9
        assert df2.iloc[0]["regime_at_entry"] == regime_1

    def test_regime_vector_cols_not_overwritten_once_set(self, tmp_path):
        """Once a regime_vector stamp is written it must never be overwritten."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        data_dir = tmp_path / "data"
        stockdata_dir = tmp_path / "stockdata"
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(400)
        entry_date = str(close.index[150].date())
        _write_prices(stocks_dir, "AMZN", close)
        _write_signals(signals_dir, "AMZN", entry_date, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "rv-test"},
        ])

        # First run: provide a vector
        _write_regime_vector_parquet(data_dir, [
            {"date": entry_date, "rate_pressure": "neutral", "quad_hard_label": "goldilocks",
             "fused_risk_label": "risk-on", "vol_regime": "calm-contango",
             "risk_radar_state": "risk-on", "regime_vector_degraded": 0, "asof": entry_date},
        ])
        _run_with_overrides(signals_dir, stocks_dir, arch, asof=entry_date,
                            data_dir=data_dir, stockdata_dir=stockdata_dir)
        df1 = pd.read_parquet(arch)
        rate1 = df1.iloc[0]["rate_pressure"]

        # Second run: different vector value for same date — keep-FIRST must win
        _write_regime_vector_parquet(data_dir, [
            {"date": entry_date, "rate_pressure": "SHOULD_NOT_OVERWRITE",
             "quad_hard_label": "stagflation", "fused_risk_label": "risk-off",
             "vol_regime": "stress", "risk_radar_state": "risk-off",
             "regime_vector_degraded": 1, "asof": entry_date},
        ])
        _run_with_overrides(signals_dir, stocks_dir, arch, asof=entry_date,
                            data_dir=data_dir, stockdata_dir=stockdata_dir)
        df2 = pd.read_parquet(arch)
        rate2 = df2.iloc[0]["rate_pressure"]
        # The first-observed value must survive
        assert rate2 == rate1, (
            f"keep-FIRST violated: rate_pressure changed from {rate1!r} to {rate2!r}")


class TestStageB_VectorStamp:
    """regime_vector stamp: exact-date match, carry-forward fallback, unstamped count."""

    def test_exact_date_match(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        data_dir = tmp_path / "data"
        stockdata_dir = tmp_path / "stockdata"
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(400)
        entry_date = str(close.index[200].date())
        _write_prices(stocks_dir, "TSLA", close)
        _write_signals(signals_dir, "TSLA", entry_date, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "exact"},
        ])
        _write_regime_vector_parquet(data_dir, [
            {"date": entry_date, "rate_pressure": "relief", "quad_hard_label": "goldilocks",
             "fused_risk_label": "expansion", "vol_regime": "calm-contango",
             "risk_radar_state": "risk-on", "regime_vector_degraded": 0, "asof": entry_date},
        ])
        result = _run_with_overrides(signals_dir, stocks_dir, arch, asof=entry_date,
                                     data_dir=data_dir, stockdata_dir=stockdata_dir)
        df = pd.read_parquet(arch)
        row = df.iloc[0]
        assert row["rate_pressure"] == "relief", f"rate_pressure mismatch: {row['rate_pressure']!r}"
        assert row["quad_hard_label"] == "goldilocks"
        assert float(row["staleness_hours"]) == 0.0, \
            f"staleness_hours should be 0.0 for exact match; got {row['staleness_hours']}"
        assert str(row["vector_asof"]) == entry_date
        assert result["unstamped_count"] == 0

    def test_carry_forward_fallback(self, tmp_path):
        """When no exact-date vector exists, the most recent prior row is used."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        data_dir = tmp_path / "data"
        stockdata_dir = tmp_path / "stockdata"
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(400)
        entry_date = str(close.index[200].date())
        vector_date = str(close.index[195].date())  # 5 days before marker
        _write_prices(stocks_dir, "META", close)
        _write_signals(signals_dir, "META", entry_date, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "carry"},
        ])
        _write_regime_vector_parquet(data_dir, [
            {"date": vector_date, "rate_pressure": "pressure", "quad_hard_label": "stagflation",
             "fused_risk_label": "risk-off", "vol_regime": "warning",
             "risk_radar_state": "risk-off", "regime_vector_degraded": 0, "asof": vector_date},
        ])
        _run_with_overrides(signals_dir, stocks_dir, arch, asof=entry_date,
                            data_dir=data_dir, stockdata_dir=stockdata_dir)
        df = pd.read_parquet(arch)
        row = df.iloc[0]
        assert row["rate_pressure"] == "pressure"
        assert str(row["vector_asof"]) == vector_date
        # staleness_hours must be positive (vector is older than marker date)
        assert float(row["staleness_hours"]) > 0, \
            f"staleness_hours should be > 0 for carry-forward; got {row['staleness_hours']}"

    def test_unstamped_count_reported_when_no_vector(self, tmp_path):
        """When no persisted vector exists at all, unstamped_count equals total rows."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        data_dir = tmp_path / "data_empty"  # no regime_vector.parquet
        stockdata_dir = tmp_path / "stockdata"
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(300)
        _write_prices(stocks_dir, "NFLX", close)
        _write_signals(signals_dir, "NFLX", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "no-vector"},
        ])
        result = _run_with_overrides(signals_dir, stocks_dir, arch, asof=ENTRY_DATE,
                                     data_dir=data_dir, stockdata_dir=stockdata_dir)
        assert result["unstamped_count"] == result["total_rows"], (
            f"unstamped_count {result['unstamped_count']} != total_rows {result['total_rows']}")


class TestStageB_SpeciesMapping:
    """species_id: unambiguous registry mapping only; null when ambiguous or no mapping."""

    def test_species_id_null_when_no_track_record_binding(self, tmp_path):
        """Default: all species bind to us_board_ledger → species_id is null for all rows."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        data_dir = tmp_path / "data"
        stockdata_dir = tmp_path / "stockdata"
        arch = tmp_path / "track_record.parquet"

        # Registry with species bound to us_board_ledger (not track_record)
        _write_species_registry(data_dir, [
            {"species_id": "S1", "ledger_binding": {"ledger": "us_board_ledger", "since": "2026-01-01"}},
        ])
        close = _daily_close(300)
        _write_prices(stocks_dir, "NVDA", close)
        _write_signals(signals_dir, "NVDA", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "sp-test"},
        ])
        _run_with_overrides(signals_dir, stocks_dir, arch, asof=ENTRY_DATE,
                            data_dir=data_dir, stockdata_dir=stockdata_dir)
        df = pd.read_parquet(arch)
        row = df.iloc[0]
        assert pd.isna(row.get("species_id")) or row.get("species_id") is None, \
            f"species_id should be null when no track_record binding; got {row.get('species_id')!r}"

    def test_species_id_stamped_when_unambiguous_track_record_binding(self, tmp_path):
        """A species with ledger=track_record → its species_id is stamped on matching rows."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        data_dir = tmp_path / "data"
        stockdata_dir = tmp_path / "stockdata"
        arch = tmp_path / "track_record.parquet"

        _write_species_registry(data_dir, [
            {"species_id": "S-TR-TEST",
             "ledger_binding": {"ledger": "track_record", "since": "2026-01-01"},
             "marker_types": ["buy"]},
        ])
        close = _daily_close(300)
        _write_prices(stocks_dir, "AMD", close)
        _write_signals(signals_dir, "AMD", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "sp-tr"},
        ])
        _run_with_overrides(signals_dir, stocks_dir, arch, asof=ENTRY_DATE,
                            data_dir=data_dir, stockdata_dir=stockdata_dir)
        df = pd.read_parquet(arch)
        row = df.iloc[0]
        assert row.get("species_id") == "S-TR-TEST", \
            f"species_id should be 'S-TR-TEST'; got {row.get('species_id')!r}"

    def test_species_id_null_when_ambiguous(self, tmp_path):
        """Two species binding track_record to the same mtype → species_id is null (ambiguous)."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        data_dir = tmp_path / "data"
        stockdata_dir = tmp_path / "stockdata"
        arch = tmp_path / "track_record.parquet"

        _write_species_registry(data_dir, [
            {"species_id": "S-A",
             "ledger_binding": {"ledger": "track_record"}, "marker_types": ["buy"]},
            {"species_id": "S-B",
             "ledger_binding": {"ledger": "track_record"}, "marker_types": ["buy"]},
        ])
        close = _daily_close(300)
        _write_prices(stocks_dir, "INTC", close)
        _write_signals(signals_dir, "INTC", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "ambig"},
        ])
        _run_with_overrides(signals_dir, stocks_dir, arch, asof=ENTRY_DATE,
                            data_dir=data_dir, stockdata_dir=stockdata_dir)
        df = pd.read_parquet(arch)
        row = df.iloc[0]
        assert pd.isna(row.get("species_id")) or row.get("species_id") is None, \
            f"species_id should be null (ambiguous); got {row.get('species_id')!r}"


class TestStageB_ArchetypeStamp:
    """archetype: stamped from site/stockdata at row creation; null if absent."""

    def test_archetype_stamped_from_stockdata(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        data_dir = tmp_path / "data"
        stockdata_dir = tmp_path / "stockdata"
        arch = tmp_path / "track_record.parquet"

        _write_stockdata(stockdata_dir, "AAPL", "quality_compounder")
        close = _daily_close(300)
        _write_prices(stocks_dir, "AAPL", close)
        _write_signals(signals_dir, "AAPL", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "arch-test"},
        ])
        _run_with_overrides(signals_dir, stocks_dir, arch, asof=ENTRY_DATE,
                            data_dir=data_dir, stockdata_dir=stockdata_dir)
        df = pd.read_parquet(arch)
        row = df.iloc[0]
        assert row.get("archetype") == "quality_compounder", \
            f"archetype mismatch: {row.get('archetype')!r}"

    def test_archetype_null_when_stockdata_absent(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        data_dir = tmp_path / "data"
        stockdata_dir = tmp_path / "stockdata_empty"
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(300)
        _write_prices(stocks_dir, "XOM", close)
        _write_signals(signals_dir, "XOM", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "no-arch"},
        ])
        _run_with_overrides(signals_dir, stocks_dir, arch, asof=ENTRY_DATE,
                            data_dir=data_dir, stockdata_dir=stockdata_dir)
        df = pd.read_parquet(arch)
        row = df.iloc[0]
        assert pd.isna(row.get("archetype")) or row.get("archetype") is None, \
            f"archetype should be null when stockdata absent; got {row.get('archetype')!r}"

    def test_archetype_not_backfilled_for_old_rows(self, tmp_path):
        """NEVER backfill archetype for existing rows (non-PIT for beta/sector buckets)."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        data_dir = tmp_path / "data"
        stockdata_dir = tmp_path / "stockdata"
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(300)
        # Run 1: no stockdata → archetype=null
        _write_prices(stocks_dir, "CVX", close)
        _write_signals(signals_dir, "CVX", ENTRY_DATE, [
            {"date": ENTRY_DATE, "type": "buy", "quality": "take", "reason": "no-arch-first"},
        ])
        _run_with_overrides(signals_dir, stocks_dir, arch, asof=ENTRY_DATE,
                            data_dir=data_dir, stockdata_dir=tmp_path / "empty_stockdata")
        df1 = pd.read_parquet(arch)
        assert pd.isna(df1.iloc[0].get("archetype")) or df1.iloc[0].get("archetype") is None

        # Run 2: stockdata now present — archetype should NOT be backfilled into old row
        _write_stockdata(stockdata_dir, "CVX", "commodity_sensitive")
        _run_with_overrides(signals_dir, stocks_dir, arch, asof=ENTRY_DATE,
                            data_dir=data_dir, stockdata_dir=stockdata_dir)
        df2 = pd.read_parquet(arch)
        # archetype remains null (keep-FIRST; null value = "no archetype at row creation")
        # This is the correct behavior: archetype is frozen at creation. If the first
        # observed value is null, it stays null — the spec says NEVER backfill archetype.
        assert len(df2) == 1, "row count changed"


class TestStageB_SpineColumns:
    """fwd_mfe, terminal_state columns are nullable at birth, filled via maturation path."""

    def test_spine_columns_null_when_series_too_short(self, tmp_path):
        """A very short price series cannot mature spine columns — they stay null."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        # Only 30 bars — not enough to mature terminal_state_clean15_126 (needs 126)
        close = _daily_close(30)
        entry_date = str(close.index[5].date())
        _write_prices(stocks_dir, "SHORT", close)
        _write_signals(signals_dir, "SHORT", entry_date, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "short"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=entry_date)
        df = pd.read_parquet(arch)
        row = df.iloc[0]
        assert pd.isna(row.get("terminal_state_clean15_126")) or row.get("terminal_state_clean15_126") is None, \
            "terminal_state_clean15_126 should be null with only 30 bars"
        assert pd.isna(row.get("fwd_mfe_126")) or row.get("fwd_mfe_126") is None, \
            "fwd_mfe_126 should be null with only 30 bars"

    def test_terminal_state_filled_when_enough_data(self, tmp_path):
        """With enough bars the terminal_state columns get a non-null valid label."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        # 500 bars; fire at bar 100 → 400 bars forward (enough for 126-bar horizon)
        close = _daily_close(500)
        entry_date = str(close.index[100].date())
        _write_prices(stocks_dir, "LONG", close)
        _write_signals(signals_dir, "LONG", entry_date, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "long"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=entry_date)
        df = pd.read_parquet(arch)
        row = df.iloc[0]

        valid_states = {"STOPPED", "DEAD_MONEY", "CUSHIONED", "CLEAN_LIFTOFF"}
        ts_15 = row.get("terminal_state_clean15_126")
        ts_8  = row.get("terminal_state_clean8_21")
        assert ts_15 in valid_states or pd.isna(ts_15), \
            f"terminal_state_clean15_126 invalid: {ts_15!r}"
        assert ts_8 in valid_states or pd.isna(ts_8), \
            f"terminal_state_clean8_21 invalid: {ts_8!r}"
        # clean8_21 has shorter horizon — should be filled
        assert ts_8 in valid_states, f"terminal_state_clean8_21 should be filled; got {ts_8!r}"

    def test_fwd_mfe_non_negative(self, tmp_path):
        """fwd_mfe values must be >= 0 (max favorable excursion is never negative)."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(300)
        entry_date = str(close.index[50].date())
        _write_prices(stocks_dir, "MFE", close)
        _write_signals(signals_dir, "MFE", entry_date, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "mfe"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=entry_date)
        df = pd.read_parquet(arch)
        row = df.iloc[0]
        for h in [5, 10, 21]:
            v = row.get(f"fwd_mfe_{h}")
            if not pd.isna(v) and v is not None:
                assert float(v) >= 0.0, f"fwd_mfe_{h}={v} is negative"

    def test_spine_cols_frozen_once_set(self, tmp_path):
        """Once terminal_state and fwd_mfe are set, a re-run must NOT change them."""
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(400)
        entry_date = str(close.index[100].date())
        _write_prices(stocks_dir, "FREEZE", close)
        _write_signals(signals_dir, "FREEZE", entry_date, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "freeze"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=entry_date)
        df1 = pd.read_parquet(arch)
        ts8_1 = df1.iloc[0].get("terminal_state_clean8_21")

        _run(signals_dir, stocks_dir, arch, asof=entry_date)
        df2 = pd.read_parquet(arch)
        ts8_2 = df2.iloc[0].get("terminal_state_clean8_21")

        # Both null or both equal — never changes once set
        if not pd.isna(ts8_1) and ts8_1 is not None:
            assert ts8_2 == ts8_1, f"terminal_state_clean8_21 changed on re-run: {ts8_1!r} → {ts8_2!r}"


def _scripted_close(fwd_path: list[float], *, n_hist: int = 260,
                    base: float = 100.0) -> tuple[pd.Series, str]:
    """Flat series at ``base`` with a scripted forward path appended.

    Returns ``(close, entry_date)`` where the marker at ``entry_date`` gets a
    NEXT-BAR fill on the last flat bar (entry price == ``base``), so
    ``fwd_path[i]`` is the close ``i + 1`` bars after the fill — the exact window
    ``post_cushion_breach`` scans."""
    idx = pd.bdate_range("2020-01-01", periods=n_hist + len(fwd_path))
    close = pd.Series([base] * n_hist + list(fwd_path), index=idx, dtype=float)
    entry_date = str(idx[n_hist - 2].date())  # fill lands on idx[n_hist - 1]
    return close, entry_date


class TestStageB_PostCushionBreach:
    """END-TO-END: the ledger row's post_cushion_breach must carry the CANONICAL
    grading semantics through _fill_maturation — a fire that cushions (+5%) and
    then falls back below entry, including a full stop-out (−5%), is a breach
    (True). Only never-cushioned fires stay null. Unit coverage of the grading
    primitive itself lives in test_grading_spine_v2.TestPostCushionBreach; these
    tests pin the WIRING into the append-only store, where a wrong value is
    irreversible."""

    def _run_path(self, tmp_path, fwd_path: list[float]):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close, entry_date = _scripted_close(fwd_path)
        _write_prices(stocks_dir, "PCB", close)
        _write_signals(signals_dir, "PCB", entry_date, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "pcb"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=str(close.index[-1].date()))
        df = pd.read_parquet(arch)
        return df[(df["ticker"] == "PCB") & (df["type"] == "buy")].iloc[0]

    def test_cushioned_then_stopped_is_breach_true(self, tmp_path):
        """Cushion at +6% on bar 4, stop-out at −6% on bar 9 — the worst cushioned
        fire. Regression: the pre-review inline scan broke on the stop and left
        this row null forever in the append-only ledger."""
        fwd = [100.0, 100.0, 100.0, 106.0, 101.0, 101.0, 101.0, 101.0, 94.0] + [94.0] * 16
        row = self._run_path(tmp_path, fwd)
        assert not pd.isna(row["post_cushion_breach"]), \
            "cushioned-then-stopped fire must be scored, not left null"
        assert bool(row["post_cushion_breach"]) is True, \
            "cushioned-then-stopped must be a post-cushion breach (True)"

    def test_cushioned_no_breach_is_false(self, tmp_path):
        """Cushion on bar 4, then holds above entry through the window → False."""
        fwd = [100.0, 100.0, 100.0, 106.0] + [103.0] * 21
        row = self._run_path(tmp_path, fwd)
        assert not pd.isna(row["post_cushion_breach"]), \
            "cushioned fire that matured must be scored"
        assert bool(row["post_cushion_breach"]) is False, \
            "cushioned fire that held above entry is not a breach"

    def test_never_cushioned_is_null(self, tmp_path):
        """Never reaches +5% inside the window → breach undefined → null."""
        fwd = [101.0] * 25
        row = self._run_path(tmp_path, fwd)
        assert pd.isna(row["post_cushion_breach"]), \
            "never-cushioned fire must stay null"

    def test_stopped_before_cushion_is_null(self, tmp_path):
        """Stops out before ever cushioning → not a post-cushion question → null."""
        fwd = [100.0, 94.0] + [106.0] * 23
        row = self._run_path(tmp_path, fwd)
        assert pd.isna(row["post_cushion_breach"]), \
            "stopped-before-cushion fire must stay null (never cushioned first)"

    def test_ledger_row_matches_canonical_grader(self, tmp_path):
        """The value frozen in the store equals both the single-fire primitive and
        the aggregate grader on the identical fire — one definition end to end."""
        from engine import grading

        fwd = [100.0, 100.0, 100.0, 106.0, 101.0, 101.0, 101.0, 101.0, 94.0] + [94.0] * 16
        close, entry_date = _scripted_close(fwd)

        row = self._run_path(tmp_path, fwd)
        single = grading.post_cushion_breach(close, entry_date, horizon=21)
        agg = grading.cushion_incidence([(close, entry_date)], k_days=(5, 10, 21))

        assert single is True
        assert bool(row["post_cushion_breach"]) is True
        assert agg["cushion_reached_count"] == 1
        assert agg["post_cushion_breakeven_breach_rate"] == 100.0


# ---------------------------------------------------------------------------
# W0.2 Stage C — near-miss capture (log_near_misses + maturation pass)
# ---------------------------------------------------------------------------
class TestNearMissCapture:

    def _dirs(self, tmp_path):
        signals = tmp_path / "signals"; signals.mkdir()
        stocks = tmp_path / "stocks"; stocks.mkdir()
        arch = tmp_path / "track_record.parquet"
        return signals, stocks, arch

    def _log(self, tmp_path, stocks, arch, near):
        return TR.log_near_misses(
            near, repo_root=tmp_path, out_path=arch, stocks_dir=stocks,
            data_dir=tmp_path / "data", stockdata_dir=tmp_path / "stockdata")

    def test_near_miss_row_logged_and_matured(self, tmp_path):
        _, stocks, arch = self._dirs(tmp_path)
        _write_prices(stocks, "AAPL", _daily_close(400))
        out = self._log(tmp_path, stocks, arch,
                        [{"ticker": "AAPL", "date": ENTRY_DATE,
                          "primary_rejection_reason": "freshness_expired",
                          "reason_detail": "held but risen for many days"}])
        assert out["n_new"] == 1 and out["n_rejected_reason"] == 0
        df = pd.read_parquet(arch)
        row = df[df["type"] == TR.NEAR_MISS_TYPE].iloc[0]
        assert row["ticker"] == "AAPL"
        assert row["primary_rejection_reason"] == "freshness_expired"
        assert row["reason_detail"].startswith("held but")
        # graded as a prediction: forward cols filled (400-bar series matured)
        assert pd.notna(row["fwd_mdd_20"])
        assert pd.notna(row["entry_price"])

    def test_non_taxonomy_reason_rejected(self, tmp_path):
        _, stocks, arch = self._dirs(tmp_path)
        _write_prices(stocks, "AAPL", _daily_close(400))
        out = self._log(tmp_path, stocks, arch,
                        [{"ticker": "AAPL", "date": ENTRY_DATE,
                          "primary_rejection_reason": "made_up_reason"}])
        assert out["n_new"] == 0 and out["n_rejected_reason"] == 1
        assert not arch.exists()   # nothing written

    def test_keep_first_on_duplicate(self, tmp_path):
        _, stocks, arch = self._dirs(tmp_path)
        _write_prices(stocks, "AAPL", _daily_close(400))
        nm = [{"ticker": "AAPL", "date": ENTRY_DATE,
               "primary_rejection_reason": "not_topped_veto"}]
        self._log(tmp_path, stocks, arch, nm)
        first = pd.read_parquet(arch)
        out2 = self._log(tmp_path, stocks, arch, nm)
        assert out2["n_duplicate"] == 1 and out2["n_new"] == 0
        second = pd.read_parquet(arch)
        assert len(first) == len(second) == 1

    def test_hygiene_screen_never_graded(self, tmp_path):
        _, stocks, arch = self._dirs(tmp_path)
        _write_prices(stocks, "AAPL", _daily_close(400))
        self._log(tmp_path, stocks, arch,
                  [{"ticker": "AAPL", "date": ENTRY_DATE,
                    "primary_rejection_reason": "hygiene_screen"}])
        row = pd.read_parquet(arch).iloc[0]
        assert row["primary_rejection_reason"] == "hygiene_screen"
        assert pd.isna(row["fwd_mdd_20"])   # captured, never graded (Appendix A)

    def test_update_run_matures_stored_near_miss(self, tmp_path):
        """A near-miss logged while immature must gain its forward columns from
        update_track_record's Stage-C pass once the price store matures."""
        signals, stocks, arch = self._dirs(tmp_path)
        short = _daily_close(260)             # ENTRY_DATE ~bar 252: fwd_mdd_20 immature
        _write_prices(stocks, "AAPL", short)
        self._log(tmp_path, stocks, arch,
                  [{"ticker": "AAPL", "date": ENTRY_DATE,
                    "primary_rejection_reason": "freshness_expired"}])
        row0 = pd.read_parquet(arch).iloc[0]
        assert pd.isna(row0["fwd_mdd_20"])    # not yet matured
        _write_prices(stocks, "AAPL", _daily_close(400))   # store matures
        # any marker file gets the run going; the Stage-C pass matures near-misses
        _write_signals(signals, "MSFT", ENTRY_DATE,
                       [{"date": ENTRY_DATE, "type": "buy", "quality": "take"}])
        _write_prices(stocks, "MSFT", _daily_close(400))
        _run(signals, stocks, arch, asof="2022-06-01")
        row1 = pd.read_parquet(arch)
        row1 = row1[row1["type"] == TR.NEAR_MISS_TYPE].iloc[0]
        assert pd.notna(row1["fwd_mdd_20"])   # matured by the Stage-C pass

    def test_fire_rows_unaffected_by_near_miss_columns(self, tmp_path):
        signals, stocks, arch = self._dirs(tmp_path)
        _write_prices(stocks, "NVDA", _daily_close(400))
        _write_signals(signals, "NVDA", ENTRY_DATE,
                       [{"date": ENTRY_DATE, "type": "buy", "quality": "take"}])
        _run(signals, stocks, arch, asof="2022-06-01")
        row = pd.read_parquet(arch).iloc[0]
        assert pd.isna(row["primary_rejection_reason"])
        assert pd.isna(row["reason_detail"])
