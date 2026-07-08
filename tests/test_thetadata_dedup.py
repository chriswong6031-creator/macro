"""tests/test_thetadata_dedup.py — hermetic tests for the ThetaData EOD dedup fix.

Covers:
  1. Collector parse: _normalize_eod_df drops full-row API duplicates and logs count.
  2. Collector: bulk_eod returns deduped DataFrame when API returns dup rows.
  3. Writer idempotency: writing the same year twice (via _write_parquet_atomic) produces
     no dups in the output parquet.
  4. Repair script (scripts/repair_thetadata_dedup):
       a. dry-run: reports correct dup counts, no files written.
       b. apply: rewrites dup files atomically, resulting parquets have 0 dups.
       c. clean files: not touched by --apply.
  5. Store reader: _load_parquets emits WARN and drops dups from a dup-containing parquet.
  6. Audit script: dup-rate spot-check emits WARN on a store with high dup rate.
"""
from __future__ import annotations

import io
import logging
import os
import sys
from pathlib import Path
from datetime import date

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── fixture helpers ──────────────────────────────────────────────────────────

def _make_eod_df(n_rows: int = 4, *, with_dups: bool = False) -> pd.DataFrame:
    """Build a minimal normalized EOD DataFrame (post-_normalize_eod_df columns).

    Generates n_rows DISTINCT rows (unique strikes 580+i*2.5).
    If with_dups=True, every row is duplicated once (mimicking the API bug).
    """
    strikes = [580.0 + i * 2.5 for i in range(n_rows)]
    rights = ["C" if i % 2 == 0 else "P" for i in range(n_rows)]
    dates = pd.to_datetime([
        "2026-01-02" if i < n_rows // 2 + 1 else "2026-01-03" for i in range(n_rows)
    ])
    base = pd.DataFrame({
        "root": ["SPY"] * n_rows,
        "expiration": pd.to_datetime(["2026-01-17"] * n_rows),
        "strike": strikes,
        "right": rights,
        "date": dates,
        "open": [1.0] * n_rows,
        "high": [2.0] * n_rows,
        "low": [0.5] * n_rows,
        "close": [1.5] * n_rows,
        "volume": [100] * n_rows,
        "count": [10] * n_rows,
        "bid": [1.4] * n_rows,
        "ask": [1.6] * n_rows,
    })
    if with_dups:
        return pd.concat([base, base], ignore_index=True)
    return base


def _make_raw_csv_with_dups(n_rows: int = 2) -> bytes:
    """Build a raw v3 EOD CSV with n_rows DISTINCT unique rows, each duplicated once.

    The rows differ by strike (580+i*2.5) and right (alternating CALL/PUT) so they
    are byte-distinct after normalization.  Each unique row appears twice (API bug sim).
    """
    header = "symbol,expiration,strike,right,last_trade,open,high,low,close,volume,count,bid,ask"
    unique_rows = [
        f"SPY,2026-01-17,{580.0 + i * 2.5:.3f},{'CALL' if i % 2 == 0 else 'PUT'},"
        f"2026-01-02 16:00:00,1.0,2.0,0.5,1.5,100,10,1.4,1.6"
        for i in range(n_rows)
    ]
    # Each unique row duplicated once (simulating API bug)
    lines = [header] + [r for row in unique_rows for r in [row, row]]
    return "\n".join(lines).encode()


def _plant_dup_parquet(path: Path, n_unique: int = 3) -> None:
    """Write a parquet with n_unique rows, each duplicated once."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df = _make_eod_df(n_unique, with_dups=True)
    df.to_parquet(path, index=False)


def _plant_clean_parquet(path: Path, n_rows: int = 3) -> None:
    """Write a parquet with no duplicates."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df = _make_eod_df(n_rows, with_dups=False)
    df.to_parquet(path, index=False)


# ── 1. Collector: _normalize_eod_df drops API dups ─────────────────────────

class TestNormalizeEodDfDedup:
    """_normalize_eod_df removes full-row duplicates from the API response."""

    def test_drops_full_row_dups(self):
        """Input with 2x duplicate rows → output has no dups."""
        from collectors.thetadata import _normalize_eod_df

        raw = pd.read_csv(io.BytesIO(_make_raw_csv_with_dups(n_rows=2)), low_memory=False)
        # raw has 4 rows: 2 unique rows, each appearing twice
        assert len(raw) == 4

        result = _normalize_eod_df(raw, "SPY")
        # After dedup: 2 unique rows
        assert not result.duplicated().any(), "deduped df should have no full-row dups"
        assert len(result) == 2

    def test_clean_df_unchanged(self):
        """A DataFrame with no dups is returned unchanged (no rows dropped)."""
        from collectors.thetadata import _normalize_eod_df

        raw = pd.read_csv(io.BytesIO(_make_raw_csv_with_dups(n_rows=1)), low_memory=False)
        # raw has 2 rows: 1 unique row appearing twice — BUT: we'll use the clean path
        clean_csv = (
            "symbol,expiration,strike,right,last_trade,open,high,low,close,volume,count,bid,ask\n"
            "SPY,2026-01-17,580.000,CALL,2026-01-02 16:00:00,1.0,2.0,0.5,1.5,100,10,1.4,1.6\n"
            "SPY,2026-01-17,582.500,CALL,2026-01-02 16:00:00,1.0,2.0,0.5,1.5,100,10,1.4,1.6\n"
        )
        raw_clean = pd.read_csv(io.BytesIO(clean_csv.encode()), low_memory=False)
        result = _normalize_eod_df(raw_clean, "SPY")
        assert len(result) == 2
        assert not result.duplicated().any()

    def test_logs_dup_count(self, caplog):
        """When dups are dropped, an INFO log line is emitted with the count."""
        from collectors.thetadata import _normalize_eod_df

        raw = pd.read_csv(io.BytesIO(_make_raw_csv_with_dups(n_rows=3)), low_memory=False)
        # 3 unique rows × 2 = 6 raw rows; 3 dups dropped
        assert len(raw) == 6

        with caplog.at_level(logging.INFO, logger="collectors.thetadata"):
            result = _normalize_eod_df(raw, "SPY")

        assert len(result) == 3
        assert any("API duplicates" in r.message or "duplicates" in r.message.lower()
                   for r in caplog.records), \
            f"Expected dup-count log; got: {[r.message for r in caplog.records]}"

    def test_no_log_when_no_dups(self, caplog):
        """Clean input produces no dup-related log lines."""
        from collectors.thetadata import _normalize_eod_df

        clean_csv = (
            "symbol,expiration,strike,right,last_trade,open,high,low,close,volume,count,bid,ask\n"
            "SPY,2026-01-17,580.000,CALL,2026-01-02 16:00:00,1.0,2.0,0.5,1.5,100,10,1.4,1.6\n"
        )
        raw = pd.read_csv(io.BytesIO(clean_csv.encode()), low_memory=False)

        with caplog.at_level(logging.INFO, logger="collectors.thetadata"):
            _normalize_eod_df(raw, "SPY")

        dup_logs = [r for r in caplog.records if "duplicates" in r.message.lower()]
        assert not dup_logs, f"No dup logs expected on clean input; got: {dup_logs}"


# ── 2. Collector: bulk_eod deduped end-to-end ───────────────────────────────

class TestBulkEodApiDedup:
    """bulk_eod() returns a deduped DataFrame even when the API response has dups."""

    def test_bulk_eod_deduped_on_dup_api_response(self, monkeypatch):
        """bulk_eod with exp=0 (wildcard) → dup API response → clean output."""
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        dup_csv = _make_raw_csv_with_dups(n_rows=2)  # 4 raw rows, 2 unique

        def _mock_concurrent_windows(path, base_params, start, end, *, root, **kw):
            return pd.read_csv(io.BytesIO(dup_csv), low_memory=False)

        monkeypatch.setattr(td, "_concurrent_windows", _mock_concurrent_windows)
        df = td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 31))

        assert df is not None
        assert not df.empty
        assert not df.duplicated().any(), "bulk_eod output must be free of full-row dups"
        assert len(df) == 2  # 4 raw → 2 unique


# ── 2b. Collector: OI + greeks normalize dedup (2026-07-07 fix) ─────────────

def _make_raw_oi_csv_with_dups(n_rows: int = 2) -> bytes:
    """Raw v3 OI CSV: n_rows distinct rows, each duplicated once (API bug sim)."""
    header = "symbol,expiration,strike,right,timestamp,open_interest"
    unique_rows = [
        f"SPY,2026-01-17,{580.0 + i * 2.5:.3f},{'CALL' if i % 2 == 0 else 'PUT'},"
        f"2026-01-02T06:30:16.218,{1000 + i}"
        for i in range(n_rows)
    ]
    lines = [header] + [r for row in unique_rows for r in [row, row]]
    return "\n".join(lines).encode()


def _make_raw_greeks_csv_with_dups(n_rows: int = 2) -> bytes:
    """Raw v3 greeks/eod CSV: n_rows distinct rows, each duplicated once."""
    header = ("symbol,expiration,strike,right,timestamp,delta,implied_vol,"
              "underlying_price,bid,ask")
    unique_rows = [
        f"SPY,2026-01-17,{580.0 + i * 2.5:.3f},{'CALL' if i % 2 == 0 else 'PUT'},"
        f"2026-01-02 16:00:00,0.5,0.2,585.0,1.4,1.6"
        for i in range(n_rows)
    ]
    lines = [header] + [r for row in unique_rows for r in [row, row]]
    return "\n".join(lines).encode()


class TestNormalizeOiDfDedup:
    """_normalize_oi_df removes full-row duplicates (same API bug as EOD)."""

    def test_drops_full_row_dups(self):
        from collectors.thetadata import _normalize_oi_df

        raw = pd.read_csv(io.BytesIO(_make_raw_oi_csv_with_dups(n_rows=2)), low_memory=False)
        assert len(raw) == 4
        result = _normalize_oi_df(raw)
        assert not result.duplicated().any(), "deduped OI df should have no full-row dups"
        assert len(result) == 2

    def test_logs_dup_count(self, caplog):
        from collectors.thetadata import _normalize_oi_df

        raw = pd.read_csv(io.BytesIO(_make_raw_oi_csv_with_dups(n_rows=3)), low_memory=False)
        with caplog.at_level(logging.INFO, logger="collectors.thetadata"):
            result = _normalize_oi_df(raw)
        assert len(result) == 3
        assert any("duplicates" in r.message.lower() for r in caplog.records)

    def test_bulk_open_interest_deduped_on_dup_api_response(self, monkeypatch):
        """bulk_open_interest with exp=0 (wildcard) → dup API response → clean output."""
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        dup_csv = _make_raw_oi_csv_with_dups(n_rows=2)

        def _mock_concurrent_windows(path, base_params, start, end, *, root, **kw):
            return pd.read_csv(io.BytesIO(dup_csv), low_memory=False)

        monkeypatch.setattr(td, "_concurrent_windows", _mock_concurrent_windows)
        df = td.bulk_open_interest("SPY", 0, date(2026, 1, 1), date(2026, 1, 31))

        assert df is not None
        assert not df.empty
        assert not df.duplicated().any(), "bulk_open_interest output must be dedup-clean"
        assert len(df) == 2


class TestNormalizeGreeksDfDedup:
    """_normalize_greeks_df removes full-row duplicates (same API bug as EOD)."""

    def test_drops_full_row_dups(self):
        from collectors.thetadata import _normalize_greeks_df

        raw = pd.read_csv(io.BytesIO(_make_raw_greeks_csv_with_dups(n_rows=2)),
                          low_memory=False)
        assert len(raw) == 4
        result = _normalize_greeks_df(raw, order=1)
        assert not result.duplicated().any(), "deduped greeks df should have no full-row dups"
        assert len(result) == 2

    def test_bulk_greeks_deduped_on_dup_api_response(self, monkeypatch):
        """bulk_greeks with exp=0 (wildcard) → dup API response → clean output."""
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        dup_csv = _make_raw_greeks_csv_with_dups(n_rows=2)

        def _mock_concurrent_windows(path, base_params, start, end, *, root, **kw):
            return pd.read_csv(io.BytesIO(dup_csv), low_memory=False)

        monkeypatch.setattr(td, "_concurrent_windows", _mock_concurrent_windows)
        df = td.bulk_greeks("SPY", 0, date(2026, 1, 1), date(2026, 1, 31), order=1)

        assert df is not None
        assert not df.empty
        assert not df.duplicated().any(), "bulk_greeks output must be dedup-clean"
        assert len(df) == 2


# ── 3. Writer idempotency ────────────────────────────────────────────────────

class TestWriterIdempotency:
    """Writing the same DataFrame twice via _write_parquet_atomic → no dups."""

    def test_write_same_year_twice_no_dups(self, tmp_path):
        """Two calls to _write_parquet_atomic with the same df → one copy, no dups."""
        from scripts.backfill_thetadata_eod import _write_parquet_atomic

        dest = tmp_path / "eod" / "SPY" / "2026.parquet"
        dest.parent.mkdir(parents=True)
        df = _make_eod_df(3)

        _write_parquet_atomic(df, dest)
        _write_parquet_atomic(df, dest)  # second write — must OVERWRITE, not append

        result = pd.read_parquet(dest)
        assert len(result) == len(df), (
            f"Second write must overwrite, not append; got {len(result)} rows (expected {len(df)})"
        )
        assert not result.duplicated().any()

    def test_atomic_tmp_cleaned_up_on_success(self, tmp_path):
        """After a successful write, no .tmp file is left behind."""
        from scripts.backfill_thetadata_eod import _write_parquet_atomic

        dest = tmp_path / "test.parquet"
        df = _make_eod_df(2)
        _write_parquet_atomic(df, dest)

        tmp = dest.with_suffix(".tmp")
        assert not tmp.exists(), "tmp file should be removed after successful replace"
        assert dest.exists()


# ── 4. Repair script ─────────────────────────────────────────────────────────

class TestRepairScript:
    """repair_thetadata_dedup scans and optionally repairs dup parquets."""

    def test_dry_run_reports_dups_no_changes(self, tmp_path):
        """--dry-run reports dup counts but does NOT modify files."""
        from scripts.repair_thetadata_dedup import run

        store = tmp_path / "thetadata_eod"
        dup_path = store / "eod" / "SPY" / "2018.parquet"
        _plant_dup_parquet(dup_path, n_unique=4)  # 4 unique rows × 2 = 8 rows

        mtime_before = os.path.getmtime(dup_path)
        result = run(store=store, apply=False)

        assert result["ok"]
        assert not result["apply"]
        assert result["files_with_dups"] == 1
        assert result["total_dup_rows"] == 4  # 4 dups (not 8; duplicated() counts the extras)
        assert result["files_repaired"] == 0  # dry-run: no repairs
        # File must not have been modified
        assert os.path.getmtime(dup_path) == mtime_before, "dry-run must not modify files"

    def test_apply_rewrites_dup_file_atomically(self, tmp_path):
        """--apply rewrites the dup parquet; result has 0 dups and correct row count."""
        from scripts.repair_thetadata_dedup import run

        store = tmp_path / "thetadata_eod"
        dup_path = store / "eod" / "SPY" / "2018.parquet"
        _plant_dup_parquet(dup_path, n_unique=4)  # 8 rows, 4 dups

        result = run(store=store, apply=True)

        assert result["ok"]
        assert result["apply"]
        assert result["files_repaired"] == 1
        assert result["rows_removed"] == 4

        repaired = pd.read_parquet(dup_path)
        assert len(repaired) == 4, f"Expected 4 unique rows; got {len(repaired)}"
        assert not repaired.duplicated().any()

    def test_apply_leaves_clean_files_untouched(self, tmp_path):
        """--apply does not modify files that have 0 dups."""
        from scripts.repair_thetadata_dedup import run

        store = tmp_path / "thetadata_eod"
        clean_path = store / "eod" / "QQQ" / "2020.parquet"
        _plant_clean_parquet(clean_path, n_rows=3)

        mtime_before = os.path.getmtime(clean_path)
        result = run(store=store, apply=True)

        assert result["ok"]
        assert result["files_with_dups"] == 0
        assert result["files_repaired"] == 0
        assert os.path.getmtime(clean_path) == mtime_before

    def test_apply_no_tmp_file_after_success(self, tmp_path):
        """No .tmp file is left behind after a successful atomic repair."""
        from scripts.repair_thetadata_dedup import run

        store = tmp_path / "thetadata_eod"
        dup_path = store / "eod" / "SPY" / "2018.parquet"
        _plant_dup_parquet(dup_path, n_unique=2)

        run(store=store, apply=True)

        tmp = dup_path.with_suffix(".tmp")
        assert not tmp.exists()

    def test_missing_store_returns_error(self, tmp_path):
        """Non-existent store path returns ok=False with an error message."""
        from scripts.repair_thetadata_dedup import run

        result = run(store=tmp_path / "nonexistent_store", apply=False)
        assert not result["ok"]
        assert "error" in result
        assert result["files_scanned"] == 0

    def test_scan_multiple_tiers(self, tmp_path):
        """Scan covers eod, oi, greeks tiers when all are present."""
        from scripts.repair_thetadata_dedup import run

        store = tmp_path / "thetadata_eod"
        for tier in ("eod", "oi", "greeks"):
            p = store / tier / "SPY" / "2020.parquet"
            _plant_dup_parquet(p, n_unique=2)

        result = run(store=store, apply=False)

        assert result["files_scanned"] == 3
        assert result["files_with_dups"] == 3


# ── 5. Store reader: defensive dedup on load ─────────────────────────────────

class TestStoreReaderDefensiveDedup:
    """_load_parquets drops dups from on-disk parquets and emits WARN."""

    def test_load_drops_dups_from_disk(self, tmp_path, caplog):
        """A parquet with dups loaded via _load_parquets returns deduped DataFrame."""
        from engine.thetadata_store import _load_parquets, _PARQUET_CACHE
        _PARQUET_CACHE.clear()

        store = tmp_path
        dup_path = store / "eod" / "SPY" / "2018.parquet"
        _plant_dup_parquet(dup_path, n_unique=4)  # 8 rows on disk

        with caplog.at_level(logging.WARNING, logger="engine.thetadata_store"):
            df = _load_parquets("eod", "SPY", [2018], store=str(store))

        assert len(df) == 4, f"Expected 4 unique rows; got {len(df)}"
        assert not df.duplicated().any()

        # WARN log must be present
        warn_records = [r for r in caplog.records if "duplicates" in r.message.lower()
                        and r.levelno >= logging.WARNING]
        assert warn_records, f"Expected WARN log; got: {[r.message for r in caplog.records]}"

    def test_load_clean_parquet_no_warn(self, tmp_path, caplog):
        """A clean parquet produces no WARN log."""
        from engine.thetadata_store import _load_parquets, _PARQUET_CACHE
        _PARQUET_CACHE.clear()

        store = tmp_path
        clean_path = store / "eod" / "SPY" / "2020.parquet"
        _plant_clean_parquet(clean_path, n_rows=3)

        with caplog.at_level(logging.WARNING, logger="engine.thetadata_store"):
            df = _load_parquets("eod", "SPY", [2020], store=str(store))

        assert len(df) == 3
        warn_records = [r for r in caplog.records
                        if "duplicates" in r.message.lower() and r.levelno >= logging.WARNING]
        assert not warn_records, f"Unexpected WARN on clean parquet: {warn_records}"

    def test_cache_stores_deduped_frame(self, tmp_path, caplog):
        """After first load, cache holds the deduped frame; second call emits no new WARN."""
        from engine.thetadata_store import _load_parquets, _PARQUET_CACHE
        _PARQUET_CACHE.clear()

        store = tmp_path
        dup_path = store / "eod" / "SPY" / "2018.parquet"
        _plant_dup_parquet(dup_path, n_unique=3)

        with caplog.at_level(logging.WARNING, logger="engine.thetadata_store"):
            df1 = _load_parquets("eod", "SPY", [2018], store=str(store))

        warn_count_after_first = sum(
            1 for r in caplog.records
            if "duplicates" in r.message.lower() and r.levelno >= logging.WARNING
        )
        assert warn_count_after_first == 1

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="engine.thetadata_store"):
            df2 = _load_parquets("eod", "SPY", [2018], store=str(store))

        # Second call hits cache → no new WARN
        warn_count_after_second = sum(
            1 for r in caplog.records
            if "duplicates" in r.message.lower() and r.levelno >= logging.WARNING
        )
        assert warn_count_after_second == 0
        assert len(df1) == len(df2) == 3
        _PARQUET_CACHE.clear()


# ── 6. Audit dup-rate spot-check ─────────────────────────────────────────────

class TestAuditDupSpotCheck:
    """_dup_rate_spot_check and audit() detect high dup rate and emit WARN."""

    def test_spot_check_detects_high_dup_rate(self, tmp_path):
        """_dup_rate_spot_check returns files_above_threshold when dup rate is high."""
        from scripts.audit_thetadata_accrual import _dup_rate_spot_check, DUP_WARN_THRESHOLD

        store = tmp_path / "thetadata_eod"
        dup_path = store / "eod" / "SPY" / "2018.parquet"
        _plant_dup_parquet(dup_path, n_unique=4)  # 50% dup rate >> threshold

        result = _dup_rate_spot_check(store, n_sample=10, threshold=DUP_WARN_THRESHOLD, seed=42)

        assert result["files_sampled"] == 1
        assert len(result["files_above_threshold"]) == 1
        assert result["max_dup_rate"] > DUP_WARN_THRESHOLD

    def test_spot_check_clean_store_no_above_threshold(self, tmp_path):
        """_dup_rate_spot_check on a clean store reports no files above threshold."""
        from scripts.audit_thetadata_accrual import _dup_rate_spot_check, DUP_WARN_THRESHOLD

        store = tmp_path / "thetadata_eod"
        clean_path = store / "eod" / "SPY" / "2020.parquet"
        _plant_clean_parquet(clean_path, n_rows=5)

        result = _dup_rate_spot_check(store, n_sample=10, threshold=DUP_WARN_THRESHOLD, seed=42)

        assert result["files_above_threshold"] == []
        assert result["max_dup_rate"] == 0.0

    def test_audit_warns_on_high_dup_rate(self, tmp_path):
        """audit() emits a DUP RATE HIGH warning when dup-rate check fires."""
        import json
        from scripts.audit_thetadata_accrual import audit

        # Build a minimal valid steady-state store with dup parquets
        store = tmp_path / "thetadata_eod"
        dup_path = store / "eod" / "SPY" / "2018.parquet"
        _plant_dup_parquet(dup_path, n_unique=4)

        # Write required metadata
        (store / "_backfill_state.json").write_text(
            json.dumps({"version": 1, "completed": {"SPY": ["2018"]}})
        )
        (store / "_manifest.json").write_text(
            json.dumps({"store": "thetadata_eod", "n_roots": 1,
                        "per_root": {"SPY": {"completed_years": ["2018"], "n_years": 1}},
                        "updated_at": None})
        )

        result = audit(data_root=tmp_path)

        dup_warns = [w for w in result["warnings"] if "DUP" in w.upper()]
        assert dup_warns, (
            f"Expected DUP RATE HIGH warning in audit; got warnings: {result['warnings']}"
        )
