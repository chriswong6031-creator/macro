"""Tests for scripts/backfill_options_flow.py (FL-A: FC-R4/R11).

Covers:
1. Idempotence: re-running the same day leaves no duplicate rows.
2. Schema-variant handling: _ensure_underlying works when `underlying` is absent.
3. Staleness-warning logic: _check_staleness emits ::warning on stale, not on fresh.
4. _discover_dates: file-selection priority (_all > u392_ > other).
5. Integration: a synthetic day processed end-to-end yields correct SUMMARY_KEYS.
6. CRITICAL: 1-row-per-contract (daily schema) — signed fields are NaN, not 0.0.
   This is the production schema of data/massive_options_day/*.parquet (daily
   per-contract aggregates). The reviewer confirmed all 9668 contract rows have
   min/median/max rows-per-contract = 1/1/1. With one row per contract,
   sign_volume()'s shift() is always NaN → tick=0 → signed_vol=0. The fix:
   _compute_magnitude_row() stores signed fields as NaN (explicit honest absence).
"""
from __future__ import annotations

import sys
import datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backfill_options_flow import (
    MAGNITUDE_KEYS,
    SIGNED_KEYS,
    SUMMARY_KEYS,
    _ensure_underlying,
    _compute_magnitude_row,
    _already_present,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _minute_df(sym: str = "SPY", n_rows: int = 20, seed: int = 42) -> pd.DataFrame:
    """Minimal synthetic MULTI-ROW minute-agg frame matching the massive_flatfiles
    schema. Each row is a different minute for the SAME contract — this is the format
    the live nightly collector produces and what sign_volume() is designed for."""
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


def _daily_df(sym: str = "SPY", n_contracts: int = 50, session: datetime.date = None,
              seed: int = 42) -> pd.DataFrame:
    """DAILY per-contract aggregate fixture — ONE row per contract with ONE window_start.

    This matches the PRODUCTION schema of data/massive_options_day/*.parquet as
    confirmed by the reviewer (verified against 2026-06-25_u392: 9668 contracts,
    rows-per-contract min/median/max = 1/1/1, all share the same window_start).

    With one row per contract, sign_volume()'s shift() is always NaN → tick=0
    → signed_vol=0. The backfill must store signed fields as NaN, never 0.0.
    """
    if session is None:
        session = datetime.date(2026, 6, 20)
    rng = np.random.default_rng(seed)
    # session start ns (simulate same window_start for all rows = daily aggregate marker)
    ws = int(pd.Timestamp(session).value)
    strikes = [200.0 + i * 5.0 for i in range(n_contracts)]
    is_calls = [i % 2 == 0 for i in range(n_contracts)]
    exp_date = session + datetime.timedelta(days=2)  # non-zerodte by default
    tickers = [
        f"O:{sym}{session.strftime('%y%m%d')}{'C' if c else 'P'}{int(k * 1000):08d}"
        for k, c in zip(strikes, is_calls)
    ]
    return pd.DataFrame({
        "ticker": tickers,
        "volume": rng.integers(100, 5000, n_contracts),
        "open": rng.uniform(1.0, 10.0, n_contracts),
        "close": rng.uniform(1.0, 10.0, n_contracts),
        "high": rng.uniform(5.0, 15.0, n_contracts),
        "low": rng.uniform(0.5, 2.0, n_contracts),
        "window_start": [ws] * n_contracts,  # identical for all rows = daily agg
        "transactions": rng.integers(1, 100, n_contracts),
        "underlying": [sym] * n_contracts,
        "expiry": pd.to_datetime([exp_date] * n_contracts),
        "is_call": is_calls,
        "strike": strikes,
    })


def _minute_df_no_underlying(sym: str = "SPY", n_rows: int = 20) -> pd.DataFrame:
    """Same as _minute_df but WITHOUT the `underlying` column — 2024-era schema variant."""
    df = _minute_df(sym=sym, n_rows=n_rows)
    return df.drop(columns=["underlying"])


# ── CRITICAL: 1-row-per-contract (daily schema) test ─────────────────────────

class TestDailySchemaSignedFieldsAreNaN:
    """Verify the production schema: daily per-contract aggregates produce NaN
    for signed fields, never 0.0 (which would poison trailing-window baselines).

    Root cause (from reviewer): sign_volume() uses shift() within each ticker to
    compute minute-over-minute price ticks. With ONE row per contract (the daily
    production schema), shift() always returns NaN → tick=0 → signed_vol=0.
    net_premium_mn = Σ(premium × sign(signed_vol)) = 0.0 for every contract.
    Storing 0.0 is worse than NaN because it survives dropna() and corrupts the
    baseline for both flare_persistence T2 witness and build_flow_leaders.
    """

    def test_signed_fields_are_nan_not_zero(self):
        """1-row-per-contract input MUST produce NaN (not 0.0) for SIGNED_KEYS."""
        session = datetime.date(2026, 6, 20)
        daily = _daily_df("AAPL", n_contracts=50, session=session)

        # Confirm this is a 1-row-per-contract frame (production schema)
        assert daily["ticker"].nunique() == len(daily), "Fixture must be 1 row per contract"
        assert daily["window_start"].nunique() == 1, "All rows share one window_start = daily agg"

        row = _compute_magnitude_row("AAPL", session, daily)
        assert row is not None, "_compute_magnitude_row must not return None on valid daily data"

        for col in SIGNED_KEYS:
            assert col in row.columns, f"Missing column: {col}"
            v = row[col].iloc[0]
            assert pd.isna(v), (
                f"SIGNED column '{col}' must be NaN for daily-schema input, got {v!r}. "
                f"Storing 0.0 would poison trailing-window baselines (flare_persistence T2, "
                f"build_flow_leaders net_premium_mn inflection). "
                f"Root cause: sign_volume() shift() is always NaN with 1 row/contract."
            )

    def test_magnitude_fields_are_valid_from_daily_data(self):
        """MAGNITUDE_KEYS must be non-null and numerically valid from daily data."""
        session = datetime.date(2026, 6, 20)
        daily = _daily_df("SPY", n_contracts=40, session=session)
        row = _compute_magnitude_row("SPY", session, daily)
        assert row is not None

        assert row["volume"].iloc[0] > 0, "volume must be positive"
        assert row["premium_mn"].iloc[0] > 0, "premium_mn must be positive (options have value)"
        pc = row["pc_ratio"].iloc[0]
        # pc_ratio can be None if no calls, but with balanced fixture it should be present
        if pc is not None:
            assert pc > 0, f"pc_ratio must be positive, got {pc}"
        zs = row["zerodte_share"].iloc[0]
        assert 0.0 <= zs <= 1.0, f"zerodte_share must be [0,1], got {zs}"

    def test_zerodte_share_is_nonzero_when_contracts_expire_on_session(self):
        """zerodte_share is correctly computed from expiry == session date (daily data)."""
        session = datetime.date(2026, 6, 20)
        # Create a mix: half contracts expire today (zerodte), half expire next week
        daily = _daily_df("NVDA", n_contracts=20, session=session)
        daily = daily.copy()
        daily.loc[:10, "expiry"] = pd.Timestamp(session)    # 11 zerodte contracts
        daily.loc[11:, "expiry"] = pd.Timestamp("2026-06-26")  # rest expire later

        row = _compute_magnitude_row("NVDA", session, daily)
        assert row is not None
        zs = row["zerodte_share"].iloc[0]
        # zerodte contracts are 0..10 = 11 out of 20; should be ~55% of volume
        assert zs > 0.3, f"Expected meaningful zerodte_share, got {zs}"

    def test_net_premium_mn_not_stored_as_zero(self):
        """Regression guard: net_premium_mn must be NaN (not 0.0) for daily-schema input.
        0.0 survives dropna() and would corrupt trailing baselines in both
        engine/flare_persistence.py (T2 witness) and scripts/build_flow_leaders.py."""
        session = datetime.date(2026, 6, 20)
        daily = _daily_df("META", n_contracts=30, session=session)
        row = _compute_magnitude_row("META", session, daily)
        assert row is not None

        npm = row["net_premium_mn"].iloc[0]
        # Must be NaN — not 0.0
        assert pd.isna(npm), (
            f"net_premium_mn must be NaN (not 0.0) for daily-schema input. "
            f"Got {npm!r}. Storing 0.0 poisons flare_persistence T2 witness baseline."
        )
        # Explicit check: definitely NOT the value 0.0
        assert npm != 0.0, "net_premium_mn must not be 0.0 (sentinel for sign collapse)"


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
        {"premium_mn": [100.0], "net_premium_mn": [None]},
        index=pd.to_datetime(["2026-01-02"])
    )
    with patch("scripts.backfill_options_flow.store") as mock_store:
        mock_store.read.return_value = existing
        result = _already_present("AAPL", datetime.date(2026, 1, 3))
    assert result is False


def test_already_present_returns_true_when_date_in_index_with_nan():
    """When the date IS in the index with NaN net_premium_mn, _already_present returns True.
    A NaN-valued row is the correctly-backfilled state — no overwrite needed."""
    existing = pd.DataFrame(
        {"premium_mn": [100.0, 110.0], "net_premium_mn": [np.nan, np.nan]},
        index=pd.to_datetime(["2026-01-02", "2026-01-03"])
    )
    with patch("scripts.backfill_options_flow.store") as mock_store:
        mock_store.read.return_value = existing
        result = _already_present("AAPL", datetime.date(2026, 1, 2))
    assert result is True


def test_already_present_returns_false_when_date_has_zero_net_premium():
    """When the stored row has net_premium_mn == 0.0 (sign-collapse sentinel from
    a prior buggy run), _already_present returns False to force an overwrite."""
    existing = pd.DataFrame(
        {"premium_mn": [100.0], "net_premium_mn": [0.0]},
        index=pd.to_datetime(["2026-01-02"])
    )
    with patch("scripts.backfill_options_flow.store") as mock_store:
        mock_store.read.return_value = existing
        result = _already_present("AAPL", datetime.date(2026, 1, 2))
    # 0.0 net_premium_mn = sign-collapse artifact → must overwrite
    assert result is False, (
        "_already_present must return False when net_premium_mn==0.0 so the "
        "corrective run can overwrite with NaN via overwrite_overlap=True"
    )


def test_idempotence_full_flow(tmp_path):
    """Re-running backfill for the same date+ticker (with NaN-correct data) must not
    create duplicate rows.

    Simulates: first call writes 1 row with NaN net_premium_mn (correctly backfilled);
    second call sees it via _already_present → True → skips.
    store.upsert called exactly once."""
    d = datetime.date(2026, 6, 20)
    sym = "SPY"
    # Use daily schema (production schema) for the fixture
    daily = _daily_df(sym, n_contracts=30, session=d)

    upsert_calls = []

    def fake_store_read(group, name):
        if upsert_calls:
            # After first upsert, return data with NaN (correctly backfilled)
            return pd.DataFrame(
                {"premium_mn": [100.0], "net_premium_mn": [np.nan]},
                index=pd.to_datetime([d])
            )
        return None

    def fake_store_upsert(group, name, sdf, outlier_col=None, overwrite_overlap=False):
        upsert_calls.append((group, name))
        return sdf

    with patch("scripts.backfill_options_flow.store") as mock_store:
        mock_store.read.side_effect = fake_store_read
        mock_store.upsert.side_effect = fake_store_upsert

        # First run: _already_present returns False → upsert fires
        sdf = _compute_magnitude_row(sym, d, daily)
        if sdf is not None:
            if not _already_present(sym, d):
                mock_store.upsert("options_flow", f"summary_{sym}", sdf,
                                  outlier_col=None, overwrite_overlap=True)

        # Second run: _already_present returns True (NaN is the correct state) → skip
        if not _already_present(sym, d):
            sdf2 = _compute_magnitude_row(sym, d, daily)
            if sdf2 is not None:
                mock_store.upsert("options_flow", f"summary_{sym}", sdf2,
                                  outlier_col=None, overwrite_overlap=True)

    assert len(upsert_calls) == 1, (
        f"Expected 1 upsert (idempotent), got {len(upsert_calls)}"
    )


# ── 3. _compute_magnitude_row: correct SUMMARY_KEYS output ───────────────────

def test_compute_magnitude_row_returns_correct_keys():
    """_compute_magnitude_row must return a 1-row DataFrame with all SUMMARY_KEYS columns."""
    d = datetime.date(2026, 6, 20)
    daily = _daily_df("SPY", n_contracts=40, session=d)
    sdf = _compute_magnitude_row("SPY", d, daily)
    assert sdf is not None, "Expected non-None: SPY daily data should yield a summary row"
    assert sdf.shape[0] == 1, "Should be exactly 1 row"
    for k in SUMMARY_KEYS:
        assert k in sdf.columns, f"Missing column: {k}"
    assert sdf.index[0] == pd.Timestamp(d)


def test_compute_magnitude_row_empty_input_returns_none():
    """When the day_df is empty, _compute_magnitude_row returns None."""
    d = datetime.date(2026, 6, 20)
    empty = pd.DataFrame()
    result = _compute_magnitude_row("SPY", d, empty)
    assert result is None


def test_compute_magnitude_row_volume_is_positive():
    """Volume in the summary row must be a positive integer (sanity check)."""
    d = datetime.date(2026, 6, 20)
    daily = _daily_df("NVDA", n_contracts=30, session=d)
    sdf = _compute_magnitude_row("NVDA", d, daily)
    assert sdf is not None
    assert sdf["volume"].iloc[0] > 0


def test_compute_magnitude_row_premium_mn_is_float():
    """premium_mn should be a float (not None) when data is present."""
    d = datetime.date(2026, 6, 20)
    daily = _daily_df("META", n_contracts=25, session=d)
    sdf = _compute_magnitude_row("META", d, daily)
    assert sdf is not None
    prem = sdf["premium_mn"].iloc[0]
    assert prem is not None and isinstance(float(prem), float)
    assert prem > 0


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

    df_small = _daily_df("SPY", n_contracts=5)
    df_large = _daily_df("SPY", n_contracts=100)

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

    df = _daily_df("SPY", n_contracts=10)
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
    df = _daily_df("SPY", n_contracts=5)
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
