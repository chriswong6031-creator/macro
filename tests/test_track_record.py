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
    """entry_price is the daily close on the marker date (or nearest prior bar
    if the exact date is not in the price series — e.g. weekend/holiday)."""

    def test_entry_price_from_close_on_date(self, tmp_path):
        stocks_dir  = tmp_path / "stocks";  stocks_dir.mkdir()
        signals_dir = tmp_path / "signals"; signals_dir.mkdir()
        arch = tmp_path / "track_record.parquet"

        close = _daily_close(500)
        # Pick a date definitely in the series
        entry_date = str(close.index[100].date())
        expected_price = float(close.iloc[100])

        _write_prices(stocks_dir, "UNH", close)
        _write_signals(signals_dir, "UNH", entry_date, [
            {"date": entry_date, "type": "buy", "quality": "take", "reason": "held"},
        ])
        _run(signals_dir, stocks_dir, arch, asof=entry_date)
        df = pd.read_parquet(arch)

        row = df[(df["ticker"] == "UNH") & (df["type"] == "buy")].iloc[0]
        assert abs(row["entry_price"] - expected_price) < 1e-6, (
            f"entry_price {row['entry_price']:.4f} != expected {expected_price:.4f}")
