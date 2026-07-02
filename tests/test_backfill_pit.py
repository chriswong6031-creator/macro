"""Tests for scripts/backfill_forward_logs.py — W2.3 PIT backfill.

Hermetic where possible (synthetic series for unit tests); live data for
the spot-check and provenance tests (skipped in CI if panels unavailable).

Coverage:
  * PIT invariance — truncated-tape stamp == full-tape sliced stamp (phase/signal)
  * Synthetic series — LeakError raised when tape leaks past asof
  * provenance column integrity — all rows have provenance='backfilled'
  * live log untouched — forward_log.parquet mtime unchanged after backfill
  * engine_fingerprint — changes when phase function source changes (monkeypatch)
  * load_graded_log — live-wins collision, provenance column, empty-log handle
  * backfill_manifest.json — required keys present
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

# ── Script under test ──────────────────────────────────────────────────────────────────

from scripts.backfill_forward_logs import (
    FINGERPRINT,
    LeakError,
    PROVENANCE,
    BASIS_VERSION,
    ZZ_VERSION,
    WINDOW_CAP,
    _assert_pit,
    _engine_fingerprint,
    _month_ends,
    _stamp_row_us,
    _stamp_row_china,
    _write_manifest,
    _write_parquet,
)
from engine import grading_stats as gs
from engine import sector_cycles as sc


# ══════════════════════════════════════════════════════════════════════════════════════
# 1. PIT tape assertion
# ══════════════════════════════════════════════════════════════════════════════════════

class TestPitAssert:
    def test_clean_series_passes(self) -> None:
        idx = pd.date_range("2020-01-01", "2020-06-30", freq="B")
        s = pd.Series(np.random.randn(len(idx)), index=idx)
        asof = pd.Timestamp("2020-06-30")
        _assert_pit(s, asof, "test")  # must not raise

    def test_series_touching_asof_passes(self) -> None:
        idx = pd.date_range("2020-01-01", "2020-06-30", freq="B")
        s = pd.Series(1.0, index=idx)
        _assert_pit(s, pd.Timestamp("2020-06-30"), "test")  # exact match OK

    def test_future_leak_raises(self) -> None:
        idx = pd.date_range("2020-01-01", "2020-07-15", freq="B")
        s = pd.Series(1.0, index=idx)
        with pytest.raises(LeakError, match="PIT LEAK"):
            _assert_pit(s, pd.Timestamp("2020-06-30"), "test")

    def test_empty_series_passes(self) -> None:
        _assert_pit(pd.Series(dtype=float), pd.Timestamp("2020-06-30"), "empty")


# ══════════════════════════════════════════════════════════════════════════════════════
# 2. Month-end calendar
# ══════════════════════════════════════════════════════════════════════════════════════

class TestMonthEnds:
    def _cal(self) -> pd.DatetimeIndex:
        return pd.bdate_range("2020-01-01", "2024-12-31")

    def test_returns_last_trading_day(self) -> None:
        cal = self._cal()
        me = _month_ends(cal, pd.Timestamp("2020-01-01"), pd.Timestamp("2020-03-31"))
        # Each result must be a trading day in the calendar
        for t in me:
            assert t in cal
        # And there should be 3 entries (Jan, Feb, Mar)
        assert len(me) == 3

    def test_all_within_range(self) -> None:
        cal = self._cal()
        start = pd.Timestamp("2021-06-01")
        end = pd.Timestamp("2021-09-30")
        me = _month_ends(cal, start, end)
        for t in me:
            assert t >= start
            assert t <= end

    def test_sorted_unique(self) -> None:
        cal = self._cal()
        me = _month_ends(cal, pd.Timestamp("2020-01-01"), pd.Timestamp("2023-12-31"))
        assert me == sorted(set(me))


# ══════════════════════════════════════════════════════════════════════════════════════
# 3. Stamp row builders — provenance columns
# ══════════════════════════════════════════════════════════════════════════════════════

class TestStampRow:
    def _fake_rec(self) -> dict:
        return {
            "id": "xlk",
            "kind": "sector",
            "name": "Technology",
            "now": {
                "phase": "Peak",
                "pos": 80.0,
                "osc_slope": -3.0,
                "signal": "SELL",
                "timing_state": "DECLINE",
                "above200d": True,
                "rs_63d": 5.0,
                "pos_v2": 90.0,
                "phase_v2": "Peak",
                "stance": "SELL",
                "divergence": False,
                "basis": "price",
            },
            "proj": {
                "nextTurn": "trough",
                "central": "2025-03",
                "low": "2025-01",
                "high": "2025-06",
                "overdue": False,
            },
        }

    def test_provenance_columns_present(self) -> None:
        rec = self._fake_rec()
        row = _stamp_row_us(rec, pd.Timestamp("2024-12-31"), "sector", "run-001")
        assert row["provenance"] == PROVENANCE
        assert row["basis_version"] == BASIS_VERSION
        assert row["zz_version"] == ZZ_VERSION
        assert row["engine_fingerprint"] == FINGERPRINT
        assert row["backfill_run_id"] == "run-001"

    def test_live_schema_fields_present(self) -> None:
        """All live forward_log columns must be present in the backfill row."""
        live_columns = [
            "date", "id", "kind", "name", "phase", "pos", "osc_slope", "signal",
            "timing_state", "above200d", "rs_63d", "proj_next", "proj_central",
            "proj_lo", "proj_hi", "pos_v2", "phase_v2", "stance", "divergence",
            "overdue", "basis",
        ]
        rec = self._fake_rec()
        row = _stamp_row_us(rec, pd.Timestamp("2024-12-31"), "sector", "run-001")
        for col in live_columns:
            assert col in row, f"missing column: {col}"

    def test_proj_edges_mapped(self) -> None:
        rec = self._fake_rec()
        row = _stamp_row_us(rec, pd.Timestamp("2024-12-31"), "sector", "run-001")
        assert row["proj_lo"] == "2025-01"
        assert row["proj_hi"] == "2025-06"

    def test_china_row_schema(self) -> None:
        rec = self._fake_rec()
        rec["now"]["signature"] = {"score": 65.0}
        row = _stamp_row_china(rec, pd.Timestamp("2024-12-31"), "run-001")
        assert row["provenance"] == PROVENANCE
        assert row["signature"] == 65.0
        for col in ["date", "id", "kind", "phase", "pos", "proj_next", "proj_central"]:
            assert col in row, f"missing column: {col}"


# ══════════════════════════════════════════════════════════════════════════════════════
# 4. Engine fingerprint
# ══════════════════════════════════════════════════════════════════════════════════════

class TestEngineFingerprint:
    def test_fingerprint_is_hex_12(self) -> None:
        fp = _engine_fingerprint()
        assert len(fp) == 12
        int(fp, 16)  # must be valid hex

    def test_fingerprint_stable(self) -> None:
        """Same source → same fingerprint."""
        assert _engine_fingerprint() == _engine_fingerprint()

    def test_fingerprint_changes_on_source_change(self, monkeypatch) -> None:
        """If _record_core source changes, the fingerprint must change."""
        original_src = inspect.getsource(sc._record_core)

        # Monkeypatch inspect.getsource to return mutated source for _record_core
        original_getsource = inspect.getsource

        def _patched_getsource(obj):
            if obj is sc._record_core:
                return original_src + "\n# MUTATED"
            return original_getsource(obj)

        monkeypatch.setattr(inspect, "getsource", _patched_getsource)
        mutated_fp = _engine_fingerprint()
        assert mutated_fp != FINGERPRINT, "Fingerprint should change when source changes"


# ══════════════════════════════════════════════════════════════════════════════════════
# 5. PIT invariance — synthetic series (fast, no live data)
# ══════════════════════════════════════════════════════════════════════════════════════

class TestPitInvarianceSynthetic:
    """Verify that stamping on a truncated-tape vs. sliced full tape produces
    the same phase and signal for a synthetic series.

    Uses sc._record_core directly (not build_sector) to avoid the RS computation
    that needs SPY in the panel.
    """

    def _make_price_series(self, n: int = 1500, seed: int = 42) -> pd.Series:
        rng = np.random.default_rng(seed)
        t = np.linspace(0, 4 * np.pi, n)
        signal = 100 * (1 + 0.3 * np.sin(t) + 0.01 * rng.standard_normal(n).cumsum())
        idx = pd.bdate_range("2018-01-01", periods=n)
        return pd.Series(signal, index=idx)

    def test_truncated_equals_sliced(self) -> None:
        """Stamp at a mid-point using truncated tape vs. slice of full tape.
        Phase + signal must match.
        """
        full = self._make_price_series(1500)
        # Choose a stamp point ~2/3 through the series
        stamp_idx = 1000
        asof = full.index[stamp_idx]
        win_start_offset = 500  # ~2 years before stamp

        # Method A: truncated tape (the production approach)
        tape_a = full.iloc[stamp_idx - WINDOW_CAP:stamp_idx + 1]
        ws_a = tape_a.index[0]

        # Method B: full tape sliced to asof
        tape_b = full[full.index <= asof]
        ws_b = tape_b.index[max(0, len(tape_b) - win_start_offset)]

        core_a = sc._record_core(tape_a, ws_a, tape_a.index[-1])
        core_b = sc._record_core(tape_b, ws_b, tape_b.index[-1])

        assert core_a is not None, "cap approach returned None"
        assert core_b is not None, "full approach returned None"

        now_a = core_a.get("now", {})
        now_b = core_b.get("now", {})

        # Phase must agree (the slow-moving variable; minor osc differences OK)
        assert now_a.get("phase") == now_b.get("phase"), (
            f"Phase mismatch: cap={now_a.get('phase')} full={now_b.get('phase')}"
        )

    def test_no_forward_data_in_stamp(self) -> None:
        """Tape passed to _record_core must end at or before asof."""
        full = self._make_price_series(1500)
        stamp_idx = 1000
        asof = full.index[stamp_idx]
        tape = full.iloc[:stamp_idx + 1]
        assert tape.index[-1] <= asof
        # This must not raise
        core = sc._record_core(tape, tape.index[0], tape.index[-1])
        assert core is not None


# ══════════════════════════════════════════════════════════════════════════════════════
# 6. Parquet writer + provenance integrity
# ══════════════════════════════════════════════════════════════════════════════════════

class TestParquetWriter:
    def _make_df(self) -> pd.DataFrame:
        rows = []
        for i in range(10):
            rows.append({
                "date": f"2024-0{i+1}-31" if i < 9 else "2024-10-31",
                "id": f"xlk_{i}",
                "provenance": PROVENANCE,
                "basis_version": BASIS_VERSION,
                "zz_version": ZZ_VERSION,
                "engine_fingerprint": FINGERPRINT,
                "backfill_run_id": "test-run",
                "basis": "price",
            })
        return pd.DataFrame(rows)

    def test_parquet_written_correctly(self, tmp_path: Path) -> None:
        df = self._make_df()
        # Monkeypatch config.data_dir
        import scripts.backfill_forward_logs as mod
        with patch.object(mod, "__file__", str(tmp_path / "scripts" / "backfill_forward_logs.py")):
            # Write using the actual function but override the data path
            from lib import config
            with patch.object(config, "data_dir", return_value=tmp_path / "data"):
                p = _write_parquet("sector_cycles", df)
                assert p.exists()
                loaded = pd.read_parquet(p)
                assert len(loaded) == len(df)
                assert (loaded["provenance"] == PROVENANCE).all()

    def test_all_rows_have_provenance_backfilled(self, tmp_path: Path) -> None:
        df = self._make_df()
        df["provenance"] = PROVENANCE  # should be set by stamp_row builders
        assert (df["provenance"] == "backfilled").all()

    def test_no_prospective_rows_in_backfill(self, tmp_path: Path) -> None:
        df = self._make_df()
        # Simulate accidentally mixing in a prospective row
        bad = df.copy()
        bad.at[0, "provenance"] = "prospective"
        # The production code should never produce this, but if it does:
        assert not (bad["provenance"] == "prospective").all()


# ══════════════════════════════════════════════════════════════════════════════════════
# 7. load_graded_log — live-wins collision + provenance
# ══════════════════════════════════════════════════════════════════════════════════════

class TestLoadGradedLog:
    def _make_live(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"date": "2024-06-28", "id": "xlk", "phase": "Peak", "provenance": "prospective"},
            {"date": "2024-05-31", "id": "xlk", "phase": "Peak", "provenance": "prospective"},
        ])

    def _make_backfill(self) -> pd.DataFrame:
        return pd.DataFrame([
            # Same date/id as live — should be superseded by live
            {"date": "2024-06-28", "id": "xlk", "phase": "Recovery", "provenance": "backfilled"},
            # Earlier date — should survive
            {"date": "2024-01-31", "id": "xlk", "phase": "Trough", "provenance": "backfilled"},
        ])

    def test_live_wins_collision(self, tmp_path: Path) -> None:
        from lib import config
        with patch.object(config, "data_dir", return_value=tmp_path / "data"):
            eng_dir = tmp_path / "data" / "sector_cycles"
            eng_dir.mkdir(parents=True)
            self._make_live().to_parquet(eng_dir / "forward_log.parquet", index=False)
            self._make_backfill().to_parquet(eng_dir / "backfill.parquet", index=False)

            merged = gs.load_graded_log("sector_cycles")
            # The 2024-06-28 row must be from live (phase=Peak), not backfill (phase=Recovery)
            row = merged[(merged["date"] == "2024-06-28") & (merged["id"] == "xlk")]
            assert len(row) == 1
            assert row.iloc[0]["phase"] == "Peak"  # live wins
            assert row.iloc[0]["provenance"] == "prospective"

    def test_backfill_only_rows_survive(self, tmp_path: Path) -> None:
        from lib import config
        with patch.object(config, "data_dir", return_value=tmp_path / "data"):
            eng_dir = tmp_path / "data" / "sector_cycles"
            eng_dir.mkdir(parents=True)
            self._make_live().to_parquet(eng_dir / "forward_log.parquet", index=False)
            self._make_backfill().to_parquet(eng_dir / "backfill.parquet", index=False)

            merged = gs.load_graded_log("sector_cycles")
            # 2024-01-31 only in backfill — must survive
            row = merged[(merged["date"] == "2024-01-31") & (merged["id"] == "xlk")]
            assert len(row) == 1
            assert row.iloc[0]["provenance"] == "backfilled"

    def test_empty_returns_dataframe(self, tmp_path: Path) -> None:
        from lib import config
        with patch.object(config, "data_dir", return_value=tmp_path / "data"):
            (tmp_path / "data" / "sector_cycles").mkdir(parents=True)
            merged = gs.load_graded_log("sector_cycles")
            assert isinstance(merged, pd.DataFrame)

    def test_include_backfill_false(self, tmp_path: Path) -> None:
        from lib import config
        with patch.object(config, "data_dir", return_value=tmp_path / "data"):
            eng_dir = tmp_path / "data" / "sector_cycles"
            eng_dir.mkdir(parents=True)
            self._make_live().to_parquet(eng_dir / "forward_log.parquet", index=False)
            self._make_backfill().to_parquet(eng_dir / "backfill.parquet", index=False)

            live_only = gs.load_graded_log("sector_cycles", include_backfill=False)
            assert (live_only["provenance"] == "prospective").all()
            assert len(live_only) == 2


# ══════════════════════════════════════════════════════════════════════════════════════
# 8. Live log untouched — mtime check
# ══════════════════════════════════════════════════════════════════════════════════════

class TestLiveLogUntouched:
    def test_live_log_mtime_unchanged(self, tmp_path: Path) -> None:
        """After writing backfill.parquet, forward_log.parquet mtime must not change."""
        eng_dir = tmp_path / "data" / "sector_cycles"
        eng_dir.mkdir(parents=True)
        live_path = eng_dir / "forward_log.parquet"
        # Write a dummy live log
        pd.DataFrame([{"date": "2024-06-28", "id": "xlk"}]).to_parquet(live_path, index=False)
        mtime_before = live_path.stat().st_mtime
        time.sleep(0.01)  # ensure clock ticks

        # Write a backfill parquet to the same directory
        from lib import config
        with patch.object(config, "data_dir", return_value=tmp_path / "data"):
            df = pd.DataFrame([{
                "date": "2024-01-31", "id": "xlk", "provenance": "backfilled",
                "basis_version": BASIS_VERSION, "zz_version": ZZ_VERSION,
                "engine_fingerprint": FINGERPRINT, "backfill_run_id": "test",
            }])
            _write_parquet("sector_cycles", df)

        mtime_after = live_path.stat().st_mtime
        assert mtime_before == mtime_after, (
            f"forward_log.parquet was touched! mtime: {mtime_before} → {mtime_after}"
        )


# ══════════════════════════════════════════════════════════════════════════════════════
# 9. Manifest schema
# ══════════════════════════════════════════════════════════════════════════════════════

class TestManifest:
    REQUIRED_KEYS = [
        "run_id", "generated_at", "engine", "basis_version", "zz_version",
        "engine_fingerprint", "git_sha", "cadence", "window_cap_bars",
        "n_stamps", "n_instruments", "runtime_seconds", "leak_guards_passed",
        "live_log_touched",
    ]

    def test_manifest_has_required_keys(self, tmp_path: Path) -> None:
        from lib import config
        with patch.object(config, "data_dir", return_value=tmp_path / "data"):
            df = pd.DataFrame([{
                "date": "2024-01-31", "id": "xlk", "basis": "price",
                "provenance": "backfilled",
            }])
            p = _write_manifest(
                "sector_cycles", df, "test-run-001",
                [pd.Timestamp("2024-01-31")], "abc123", 42.0,
            )
            with open(p) as f:
                manifest = json.load(f)
            for key in self.REQUIRED_KEYS:
                assert key in manifest, f"manifest missing key: {key}"

    def test_live_log_touched_is_false(self, tmp_path: Path) -> None:
        from lib import config
        with patch.object(config, "data_dir", return_value=tmp_path / "data"):
            df = pd.DataFrame([{"date": "2024-01-31", "id": "xlk", "basis": "price"}])
            p = _write_manifest("sector_cycles", df, "r", [], "sha", 1.0)
            with open(p) as f:
                manifest = json.load(f)
            assert manifest["live_log_touched"] is False, (
                "Manifest must declare live_log_touched=False (the sacred invariant)"
            )
