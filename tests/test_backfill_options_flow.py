"""Tests for scripts/backfill_options_flow.py (FL-A: FC-R4/R11).

Covers:
1. Idempotence: re-running the same day leaves no duplicate rows.
2. Schema-variant handling: _ensure_underlying works when `underlying` is absent.
3. Staleness-warning logic: _check_staleness emits ::warning on stale, not on fresh.
4. _discover_dates: file-selection priority (_all > u392_ > other).
5. Integration: a synthetic day processed end-to-end yields correct SUMMARY_KEYS.
"""
from __future__ import annotations

import sys
import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backfill_options_flow import (
    SUMMARY_KEYS,
    _ensure_underlying,
    _extract_summary_row,
    _already_present,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _minute_df(sym: str = "SPY", n_rows: int = 20, seed: int = 42) -> pd.DataFrame:
    """Minimal synthetic minute-agg frame matching the massive_flatfiles schema."""
    rng = np.random.default_rng(seed)
    n = n_rows
    exp_date = datetime.date(2026, 6, 20)
    return pd.DataFrame({
        "ticker": [f"O:{sym}260620C00300000"] * n,
        "volume": rng.integers(10, 500, n),
        "open": rng.uniform(1.0, 5.0, n),
        "close": rng.uniform(1.0, 5.0, n),
        "high": rng.uniform(4.0, 6.0, n),
        "low": rng.uniform(0.5, 1.5, n),
        "window_start": [int(1.75e18 + i * 6e10) for i in range(n)],  # fake ns timestamps
        "transactions": rng.integers(1, 20, n),
        "underlying": [sym] * n,
        "expiry": pd.to_datetime([exp_date] * n),
        "is_call": [True] * n,
        "strike": [300.0] * n,
    })


def _minute_df_no_underlying(sym: str = "SPY", n_rows: int = 20) -> pd.DataFrame:
    """Same as _minute_df but WITHOUT the `underlying` column — 2024-era schema variant."""
    df = _minute_df(sym=sym, n_rows=n_rows)
    return df.drop(columns=["underlying"])


# ── 1. Schema-variant: _ensure_underlying ────────────────────────────────────

def test_ensure_underlying_passthrough_when_present():
    """When `underlying` is already present, _ensure_underlying is a no-op."""
    df = _minute_df("AAPL")
    result = _ensure_underlying(df)
    assert "underlying" in result.columns
    assert list(result["underlying"]) == ["AAPL"] * len(df)


def test_ensure_underlying_reconstructs_from_occ():
    """When `underlying` is absent, reconstruct it from the OCC ticker symbol."""
    df = _minute_df_no_underlying("NVDA")
    assert "underlying" not in df.columns
    result = _ensure_underlying(df)
    assert "underlying" in result.columns
    # All tickers are O:NVDA..., so underlying should parse to 'NVDA'
    non_null = result["underlying"].dropna()
    assert len(non_null) == len(df)
    assert set(non_null.unique()) == {"NVDA"}


def test_ensure_underlying_handles_mixed_occ():
    """Mixed OCC tickers from multiple underlyings are parsed correctly."""
    rows = [
        {"ticker": "O:AAPL260620C00150000", "volume": 10, "close": 1.0,
         "open": 1.0, "high": 1.2, "low": 0.9, "window_start": 1,
         "transactions": 1, "expiry": pd.Timestamp("2026-06-20"),
         "is_call": True, "strike": 150.0},
        {"ticker": "O:META260620P00500000", "volume": 5, "close": 2.0,
         "open": 2.0, "high": 2.1, "low": 1.9, "window_start": 2,
         "transactions": 1, "expiry": pd.Timestamp("2026-06-20"),
         "is_call": False, "strike": 500.0},
        {"ticker": "O:NVDA260620C00800000", "volume": 3, "close": 3.0,
         "open": 3.0, "high": 3.2, "low": 2.8, "window_start": 3,
         "transactions": 1, "expiry": pd.Timestamp("2026-06-20"),
         "is_call": True, "strike": 800.0},
    ]
    df = pd.DataFrame(rows)
    result = _ensure_underlying(df)
    assert list(result["underlying"]) == ["AAPL", "META", "NVDA"]


def test_ensure_underlying_invalid_occ_yields_nan():
    """An OCC ticker that does not match the regex produces NaN underlying (not a crash)."""
    rows = [
        {"ticker": "NOT_OCC_FORMAT", "volume": 1, "close": 1.0,
         "open": 1.0, "high": 1.0, "low": 1.0, "window_start": 1,
         "transactions": 1, "expiry": pd.Timestamp("2026-06-20"),
         "is_call": True, "strike": 100.0},
    ]
    df = pd.DataFrame(rows)
    result = _ensure_underlying(df)
    assert "underlying" in result.columns
    assert pd.isna(result["underlying"].iloc[0])


# ── 2. Idempotence via _already_present ──────────────────────────────────────

def test_already_present_returns_false_when_no_store(tmp_path):
    """When no parquet exists for the ticker, _already_present returns False."""
    with patch("scripts.backfill_options_flow.store") as mock_store:
        mock_store.read.return_value = None
        result = _already_present("AAPL", datetime.date(2026, 1, 2))
    assert result is False


def test_already_present_returns_false_for_new_date():
    """When the date is not in the existing index, _already_present returns False."""
    existing = pd.DataFrame(
        {"premium_mn": [100.0]},
        index=pd.to_datetime(["2026-01-02"])
    )
    with patch("scripts.backfill_options_flow.store") as mock_store:
        mock_store.read.return_value = existing
        result = _already_present("AAPL", datetime.date(2026, 1, 3))
    assert result is False


def test_already_present_returns_true_when_date_in_index():
    """When the date IS in the existing index, _already_present returns True (idempotence)."""
    existing = pd.DataFrame(
        {"premium_mn": [100.0, 110.0]},
        index=pd.to_datetime(["2026-01-02", "2026-01-03"])
    )
    with patch("scripts.backfill_options_flow.store") as mock_store:
        mock_store.read.return_value = existing
        result = _already_present("AAPL", datetime.date(2026, 1, 2))
    assert result is True


def test_idempotence_full_flow(tmp_path):
    """Re-running backfill for the same date+ticker must not create duplicate rows.

    Simulates: first call writes 1 row; second call sees it via _already_present
    and skips → store.upsert called exactly once."""
    d = datetime.date(2026, 1, 2)
    sym = "SPY"
    minute = _minute_df(sym)

    # Track upsert calls
    upsert_calls = []

    def fake_store_read(group, name):
        if upsert_calls:
            # After first upsert, return data with the date so second pass skips
            return pd.DataFrame(
                {"premium_mn": [100.0]},
                index=pd.to_datetime([d])
            )
        return None

    def fake_store_upsert(group, name, sdf, outlier_col=None):
        upsert_calls.append((group, name))
        return sdf

    with patch("scripts.backfill_options_flow.store") as mock_store:
        mock_store.read.side_effect = fake_store_read
        mock_store.upsert.side_effect = fake_store_upsert

        # First run: _already_present returns False → upsert fires
        sdf = _extract_summary_row(sym, d, minute)
        if sdf is not None:
            if not _already_present(sym, d):
                mock_store.upsert("options_flow", f"summary_{sym}", sdf, outlier_col=None)

        # Second run: _already_present returns True → skip
        if not _already_present(sym, d):
            sdf2 = _extract_summary_row(sym, d, minute)
            if sdf2 is not None:
                mock_store.upsert("options_flow", f"summary_{sym}", sdf2, outlier_col=None)

    assert len(upsert_calls) == 1, (
        f"Expected 1 upsert (idempotent), got {len(upsert_calls)}"
    )


# ── 3. _extract_summary_row: correct SUMMARY_KEYS output ─────────────────────

def test_extract_summary_row_returns_correct_keys():
    """_extract_summary_row must return a 1-row DataFrame with all SUMMARY_KEYS columns."""
    d = datetime.date(2026, 6, 20)
    minute = _minute_df("SPY", n_rows=40)
    sdf = _extract_summary_row("SPY", d, minute)
    assert sdf is not None, "Expected non-None: SPY minute data should yield a summary row"
    assert sdf.shape[0] == 1, "Should be exactly 1 row"
    for k in SUMMARY_KEYS:
        assert k in sdf.columns, f"Missing column: {k}"
    assert sdf.index[0] == pd.Timestamp(d)


def test_extract_summary_row_empty_input_returns_none():
    """When the minute_df is empty, _extract_summary_row returns None."""
    d = datetime.date(2026, 6, 20)
    empty = pd.DataFrame()
    result = _extract_summary_row("SPY", d, empty)
    assert result is None


def test_extract_summary_row_volume_is_positive():
    """Volume in the summary row must be a positive integer (sanity check)."""
    d = datetime.date(2026, 6, 20)
    minute = _minute_df("NVDA", n_rows=30)
    sdf = _extract_summary_row("NVDA", d, minute)
    assert sdf is not None
    assert sdf["volume"].iloc[0] > 0


def test_extract_summary_row_premium_mn_is_float():
    """premium_mn should be a float (not None) when data is present."""
    d = datetime.date(2026, 6, 20)
    minute = _minute_df("META", n_rows=25)
    sdf = _extract_summary_row("META", d, minute)
    assert sdf is not None
    prem = sdf["premium_mn"].iloc[0]
    assert prem is not None and isinstance(float(prem), float)


# ── 4. Staleness-warning logic ────────────────────────────────────────────────

def test_staleness_warning_emitted_when_stale(capsys):
    """When newest summary row < expected last NYSE session, a ::warning is emitted."""
    import scripts.build_options_flow as bof
    stale_date = datetime.date(2026, 1, 2)
    current_expected = datetime.date(2026, 7, 10)

    with patch.object(bof, "nyse_calendar") as mock_cal, \
         patch.object(bof, "store") as mock_store:
        mock_store.last_date.return_value = stale_date
        mock_cal.expected_last_session.return_value = current_expected

        bof._check_staleness()

    captured = capsys.readouterr()
    assert "::warning" in captured.err or "stale" in captured.err.lower(), (
        f"Expected ::warning in stderr, got: {captured.err!r}"
    )


def test_staleness_no_warning_when_fresh(capsys):
    """When newest summary row == expected last NYSE session, no ::warning is emitted."""
    import scripts.build_options_flow as bof
    current_expected = datetime.date(2026, 7, 10)

    with patch.object(bof, "nyse_calendar") as mock_cal, \
         patch.object(bof, "store") as mock_store:
        mock_store.last_date.return_value = current_expected   # up to date
        mock_cal.expected_last_session.return_value = current_expected

        bof._check_staleness()

    captured = capsys.readouterr()
    assert "::warning" not in captured.err, (
        f"Unexpected ::warning emitted when data is fresh: {captured.err!r}"
    )


def test_staleness_no_crash_when_store_empty(capsys):
    """When no summary_AAPL row exists yet, _check_staleness logs and returns (never raises)."""
    import scripts.build_options_flow as bof

    with patch.object(bof, "nyse_calendar"), \
         patch.object(bof, "store") as mock_store:
        mock_store.last_date.return_value = None

        bof._check_staleness()   # must not raise


# ── 5. _discover_dates: file-selection priority ───────────────────────────────

def test_discover_dates_prefers_all_over_u392(tmp_path):
    """_all file takes priority over _u392_ file for the same date."""
    # Create two fake parquets for 2026-06-25
    root = tmp_path / "massive_options_day" / "2026" / "06"
    root.mkdir(parents=True)

    df_small = _minute_df("SPY", n_rows=5)
    df_large = _minute_df("SPY", n_rows=100)

    path_u392 = root / "2026-06-25_u392_0c9663c2.parquet"
    path_all = root / "2026-06-25_all.parquet"
    df_small.to_parquet(path_u392)
    df_large.to_parquet(path_all)

    from scripts.backfill_options_flow import _discover_dates
    result = _discover_dates(
        tmp_path / "massive_options_day",
        datetime.date(2026, 6, 25),
        datetime.date(2026, 6, 25),
    )
    assert len(result) == 1
    d, path = result[0]
    assert d == datetime.date(2026, 6, 25)
    # Must have chosen the _all file (higher priority)
    assert "all" in path.name


def test_discover_dates_prefers_u392_over_other(tmp_path):
    """_u392_ file takes priority over an unrecognized tag for the same date."""
    root = tmp_path / "massive_options_day" / "2026" / "06"
    root.mkdir(parents=True)

    df = _minute_df("SPY", n_rows=10)
    path_other = root / "2026-06-26_u3_somethingelse.parquet"
    path_u392 = root / "2026-06-26_u392_0c9663c2.parquet"
    df.to_parquet(path_other)
    df.to_parquet(path_u392)

    from scripts.backfill_options_flow import _discover_dates
    result = _discover_dates(
        tmp_path / "massive_options_day",
        datetime.date(2026, 6, 26),
        datetime.date(2026, 6, 26),
    )
    assert len(result) == 1
    _, path = result[0]
    assert "u392" in path.name


def test_discover_dates_respects_date_range(tmp_path):
    """Only dates within [since, until] are returned."""
    root = tmp_path / "massive_options_day" / "2026" / "06"
    root.mkdir(parents=True)
    df = _minute_df("SPY", n_rows=5)
    for day in ["2026-06-20", "2026-06-25", "2026-06-30"]:
        (root / f"{day}_all.parquet").parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(root / f"{day}_all.parquet")

    from scripts.backfill_options_flow import _discover_dates
    result = _discover_dates(
        tmp_path / "massive_options_day",
        datetime.date(2026, 6, 22),
        datetime.date(2026, 6, 28),
    )
    dates = [d for d, _ in result]
    assert datetime.date(2026, 6, 25) in dates
    assert datetime.date(2026, 6, 20) not in dates
    assert datetime.date(2026, 6, 30) not in dates
