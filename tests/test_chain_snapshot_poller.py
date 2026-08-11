"""tests/test_chain_snapshot_poller.py — hermetic tests for the U-CHAIN lane.

All tests are network-free: the terminal is mocked via monkeypatching
(collectors.thetadata._get_csv), same pattern as tests/test_thetadata.py.
No writes outside tmp_path (MM_DATA_GUARD).

Test coverage:
  1. Collector: snapshot_greeks / snapshot_open_interest parse the verbatim
     v3 snapshot CSV headers (measured 2026-07-16) into normalized frames —
     snapshot_ts from response timestamps, right C/P, dollar-float strikes,
     full-row API dedup, INERT None on terminal failure.
  2. Poller: first-order dedup on the contract key, then second-order join on
     exact contract key + snapshot_ts (no row multiplication; missing or
     clock-mismatched second-order degrades to NaN columns).
  3. Poller: sweep-bucket derivation (ET wall time floored to cadence grid).
  4. Poller: universe cap logic (22 anchors + top_names, anchors first).
  5. Poller: per-day parquet append dedup on (contract key, snapshot_bucket);
     unreadable existing frame → quarantine-rename (bytes preserved), never
     overwritten; quarantine-rename failure → raise, never write.
  6. Poller: RTH gate 09:35-16:00 ET + pre-RTH wait (injected clock).
  7. Producer receipt: strict schema/state, kill-point recovery, frozen-root
     retries, elapsed-bucket terminalization, writer locking, and durability
     order. No test contacts the live terminal or performs historical replay.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import plistlib
import stat
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from engine import chain_snapshot_completion as bucket_completion
from scripts.chain_snapshot_poller import (
    CONTRACT_KEY,
    SECOND_ORDER_JOIN_COLS,
    _pre_rth_wait_sec,
    _resolve_universe,
    _within_rth,
    _atomic_install_parquet,
    _aware_vendor_clocks,
    _frame_content_sha256,
    _max_concurrent,
    append_day_parquet,
    derive_bucket,
    join_orders,
    run_managed_sweep,
)

FIXTURES = Path(__file__).parent / "fixtures" / "thetadata"
ET = ZoneInfo("America/New_York")

# 2026-07-15 is a Wednesday; 2026-07-18 is a Saturday.
WED = dict(year=2026, month=7, day=15, tzinfo=ET)
SAT = dict(year=2026, month=7, day=18, tzinfo=ET)


def _mock_fixture(monkeypatch, name: str):
    """Patch collectors.thetadata._get_csv to return a fixture CSV frame."""
    from collectors import thetadata as td

    csv_bytes = (FIXTURES / name).read_bytes()

    def _mock_get_csv(session, path, params):
        return pd.read_csv(io.BytesIO(csv_bytes), low_memory=False)

    monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
    return td


# ── 1. Collector: snapshot parsing ─────────────────────────────────────────────

class TestSnapshotGreeksParsing:
    """snapshot_greeks: verbatim v3 snapshot CSV → normalized DataFrame."""

    def test_first_order_parse(self, monkeypatch):
        td = _mock_fixture(monkeypatch, "snapshot_greeks_first_response.csv")
        df = td.snapshot_greeks("SPY", order="first")
        assert df is not None and not df.empty
        assert set(df.columns).issuperset(
            {"root", "expiration", "strike", "right", "snapshot_ts",
             "bid", "ask", "delta", "theta", "vega", "rho",
             "implied_vol", "iv_error", "underlying_price"})
        assert set(df["right"]) == {"C", "P"}
        assert pd.api.types.is_datetime64_any_dtype(df["snapshot_ts"])
        assert pd.api.types.is_datetime64_any_dtype(df["expiration"])
        # v3 strikes are dollar floats — 766.000 = $766.00, no divisor
        assert set(df["strike"]) == {766.0, 750.0}

    def test_first_order_api_duplicate_dropped(self, monkeypatch):
        """Fixture carries one byte-identical duplicate row (v3 API dedup law)."""
        td = _mock_fixture(monkeypatch, "snapshot_greeks_first_response.csv")
        df = td.snapshot_greeks("SPY", order="first")
        # 4 fixture rows, 1 full-row duplicate → 3 normalized rows
        assert len(df) == 3

    def test_second_order_parse(self, monkeypatch):
        td = _mock_fixture(monkeypatch, "snapshot_greeks_second_response.csv")
        df = td.snapshot_greeks("SPY", order="second")
        assert df is not None and len(df) == 3
        assert set(df.columns).issuperset(
            {"root", "expiration", "strike", "right", "snapshot_ts",
             "gamma", "vanna", "charm", "vomma", "veta"})
        assert pd.api.types.is_numeric_dtype(df["gamma"])

    def test_snapshot_ts_from_response_not_wall_clock(self, monkeypatch):
        td = _mock_fixture(monkeypatch, "snapshot_greeks_first_response.csv")
        df = td.snapshot_greeks("SPY", order="first")
        # Fixture timestamps are 2026-07-16T16:14:59.* — must round-trip exactly
        assert df["snapshot_ts"].dt.date.astype(str).eq("2026-07-16").all()

    def test_bad_order_raises(self):
        from collectors import thetadata as td
        with pytest.raises(ValueError):
            td.snapshot_greeks("SPY", order="third")

    def test_terminal_failure_returns_none(self, monkeypatch):
        from collectors import thetadata as td
        monkeypatch.setattr(td, "_get_csv", lambda session, path, params: None)
        assert td.snapshot_greeks("SPY", order="first") is None

    def test_stream_truncated_returns_none(self, monkeypatch):
        from collectors import thetadata as td

        def _boom(session, path, params):
            raise td._StreamTruncated("mid-stream failure")

        monkeypatch.setattr(td, "_get_csv", _boom)
        assert td.snapshot_greeks("SPY", order="first") is None

    def test_empty_response_returns_empty(self, monkeypatch):
        from collectors import thetadata as td
        monkeypatch.setattr(td, "_get_csv",
                            lambda session, path, params: pd.DataFrame())
        df = td.snapshot_greeks("SPY", order="first")
        assert df is not None and df.empty


class TestSnapshotOpenInterest:
    """snapshot_open_interest: timestamp-FIRST header (unlike greeks) parses by name."""

    def test_parse(self, monkeypatch):
        td = _mock_fixture(monkeypatch, "snapshot_oi_response.csv")
        df = td.snapshot_open_interest("SPY")
        assert df is not None and len(df) == 3
        assert set(df.columns).issuperset(
            {"root", "expiration", "strike", "right", "snapshot_ts",
             "open_interest"})
        assert set(df["right"]) == {"C", "P"}
        assert pd.api.types.is_numeric_dtype(df["open_interest"])
        # OI snapshot stamped ~06:30 ET (EOD t-1 positions — OI timing law)
        assert pd.api.types.is_datetime64_any_dtype(df["snapshot_ts"])

    def test_terminal_failure_returns_none(self, monkeypatch):
        from collectors import thetadata as td
        monkeypatch.setattr(td, "_get_csv", lambda session, path, params: None)
        assert td.snapshot_open_interest("SPY") is None


# ── 2. Poller: first+second order join ─────────────────────────────────────────

def _first_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "root":        ["SPY", "SPY"],
        "expiration":  pd.to_datetime(["2026-07-24", "2026-07-24"]),
        "strike":      [766.0, 750.0],
        "right":       ["P", "C"],
        "snapshot_ts": pd.to_datetime(["2026-07-16T16:14:59.907"] * 2),
        "bid":         [14.33, 5.10],
        "ask":         [17.51, 5.30],
        "delta":       [-0.9063, 0.5012],
        "theta":       [-0.05, -0.21],
        "vega":        [18.5, 22.1],
        "rho":         [-15.2, 8.5],
        "epsilon":     [14.8, -3.2],
        "lambda":      [-42.6, 70.1],
        "implied_vol": [0.1036, 0.1101],
        "iv_error":    [0.0, 0.0001],
        "underlying_price": [749.97, 749.97],
    })


def _second_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "root":        ["SPY"],
        "expiration":  pd.to_datetime(["2026-07-24"]),
        "strike":      [766.0],
        "right":       ["P"],
        "snapshot_ts": pd.to_datetime(["2026-07-16T16:14:59.907"]),
        "gamma":       [0.0145],
        "vanna":       [2.1523],
        "charm":       [-5.4841],
        "vomma":       [315.175],
        "veta":        [1226.5342],
    })


def _oi_frame() -> pd.DataFrame:
    first = _first_frame()[CONTRACT_KEY + ["snapshot_ts"]].copy()
    first["open_interest"] = [100, 200]
    return first


class TestJoinOrders:
    def test_join_adds_second_order_cols(self):
        out = join_orders(_first_frame(), _second_frame())
        assert len(out) == 2
        assert set(SECOND_ORDER_JOIN_COLS).issubset(out.columns)
        matched = out[(out["strike"] == 766.0) & (out["right"] == "P")]
        assert matched["gamma"].iloc[0] == pytest.approx(0.0145)

    def test_missing_contract_in_second_gives_nan(self):
        out = join_orders(_first_frame(), _second_frame())
        unmatched = out[(out["strike"] == 750.0) & (out["right"] == "C")]
        assert unmatched["gamma"].isna().all()
        # First-order values untouched by the join
        assert unmatched["delta"].iloc[0] == pytest.approx(0.5012)

    def test_second_none_degrades_to_nan_columns(self):
        out = join_orders(_first_frame(), None)
        assert len(out) == 2
        for col in SECOND_ORDER_JOIN_COLS:
            assert out[col].isna().all()

    def test_duplicate_contract_in_second_does_not_multiply_rows(self):
        second = pd.concat([_second_frame(), _second_frame()], ignore_index=True)
        out = join_orders(_first_frame(), second)
        assert len(out) == 2

    def test_duplicate_contract_in_first_deduped(self):
        first = pd.concat([_first_frame(), _first_frame()], ignore_index=True)
        out = join_orders(first, _second_frame())
        assert len(out) == 2

    @pytest.mark.parametrize("offset_us", [-1, 1])
    def test_second_order_clock_mismatch_by_one_microsecond_is_unavailable(
        self, offset_us,
    ):
        first = _first_frame().iloc[[0]].copy()
        second = _second_frame().copy()
        second["snapshot_ts"] += pd.to_timedelta(offset_us, unit="us")
        out = join_orders(first, second)
        assert out[SECOND_ORDER_JOIN_COLS].isna().all().all()

    def test_second_order_exact_contract_clock_is_retained(self):
        first = _first_frame().iloc[[0]].copy()
        out = join_orders(first, _second_frame())
        assert out["gamma"].iloc[0] == pytest.approx(0.0145)


# ── 3. Poller: sweep-bucket derivation ─────────────────────────────────────────

class TestDeriveBucket:
    def test_floor_to_cadence_grid(self):
        assert derive_bucket(datetime(hour=9, minute=35, **WED), 15) == "09:30"
        assert derive_bucket(datetime(hour=9, minute=45, **WED), 15) == "09:45"
        assert derive_bucket(datetime(hour=16, minute=0, **WED), 15) == "16:00"
        assert derive_bucket(datetime(hour=10, minute=14, **WED), 15) == "10:00"

    def test_same_interval_same_bucket(self):
        """Re-run inside one interval lands in the same bucket (dedup works)."""
        a = derive_bucket(datetime(hour=9, minute=36, **WED), 15)
        b = derive_bucket(datetime(hour=9, minute=44, **WED), 15)
        assert a == b == "09:30"

    def test_cadence_one_minute(self):
        assert derive_bucket(datetime(hour=9, minute=37, **WED), 1) == "09:37"

    @pytest.mark.parametrize("invalid", [True, "15", 15.9, 0, 20, 60, 1440])
    def test_invalid_cadence_rejected_without_coercion(self, invalid):
        with pytest.raises(bucket_completion.BucketStateError, match="exact integers"):
            derive_bucket(datetime(hour=9, minute=37, **WED), invalid)


# ── 4. Poller: universe cap logic ──────────────────────────────────────────────

class TestResolveUniverse:
    def test_anchors_plus_top_names_cap(self, monkeypatch):
        fake_gex = [f"N{i:04d}" for i in range(300)]
        monkeypatch.setattr("engine.options_universe.gex_symbols",
                            lambda cfg=None: fake_gex)
        roots = _resolve_universe({"top_names": 128})
        assert len(roots) == 22 + 128
        # Anchors take the first slots
        assert roots[0] == "SPY"
        assert roots[:22] == [
            "SPY", "QQQ", "IWM", "GLD", "SLV", "TLT", "HYG", "XLF", "XLE",
            "XLU", "XLK", "XLV", "XLI", "XLB", "XLY", "XLP", "XLRE",
            "KRE", "SMH", "XBI", "ARKK", "DIA",
        ]

    def test_anchor_overlap_not_duplicated(self, monkeypatch):
        # gex list repeating an anchor must not double it
        monkeypatch.setattr("engine.options_universe.gex_symbols",
                            lambda cfg=None: ["SPY", "AAPL", "MSFT"])
        roots = _resolve_universe({"top_names": 128})
        assert roots.count("SPY") == 1
        assert "AAPL" in roots and "MSFT" in roots

    def test_top_names_config_driven(self, monkeypatch):
        fake_gex = [f"N{i:04d}" for i in range(300)]
        monkeypatch.setattr("engine.options_universe.gex_symbols",
                            lambda cfg=None: fake_gex)
        assert len(_resolve_universe({"top_names": 5})) == 22 + 5

    def test_gex_failure_degrades_to_anchors(self, monkeypatch):
        def _boom(cfg=None):
            raise RuntimeError("membership file missing")
        monkeypatch.setattr("engine.options_universe.gex_symbols", _boom)
        roots = _resolve_universe({"top_names": 128})
        assert len(roots) == 22


# ── 5. Poller: per-day parquet append + dedup ──────────────────────────────────

def _bucket_frame(bucket: str, strikes: list[float]) -> pd.DataFrame:
    n = len(strikes)
    return pd.DataFrame({
        "root":            ["SPY"] * n,
        "expiration":      pd.to_datetime(["2026-07-24"] * n),
        "strike":          strikes,
        "right":           ["C"] * n,
        "snapshot_ts":     pd.to_datetime(["2026-07-16T16:14:59"] * n),
        "snapshot_bucket": [bucket] * n,
        "delta":           [0.5] * n,
    })


class TestAppendDayParquet:
    def test_first_write_and_idempotent_rerun(self, tmp_path):
        p = tmp_path / "2026-07-16.parquet"
        added, total, q = append_day_parquet(p, _bucket_frame("09:30", [750.0, 766.0]))
        assert (added, total, q) == (2, 2, [])
        # Same bucket re-run → dedup on (contract key, snapshot_bucket): no-op
        added, total, q = append_day_parquet(p, _bucket_frame("09:30", [750.0, 766.0]))
        assert (added, total, q) == (0, 2, [])

    def test_new_bucket_appends(self, tmp_path):
        p = tmp_path / "2026-07-16.parquet"
        append_day_parquet(p, _bucket_frame("09:30", [750.0]))
        added, total, _ = append_day_parquet(p, _bucket_frame("09:45", [750.0]))
        assert (added, total) == (1, 2)
        stored = pd.read_parquet(p)
        assert sorted(stored["snapshot_bucket"]) == ["09:30", "09:45"]

    def test_existing_rows_win(self, tmp_path):
        """Dedup keep='first' after existing-then-new concat: earlier rows win."""
        p = tmp_path / "2026-07-16.parquet"
        first = _bucket_frame("09:30", [750.0])
        append_day_parquet(p, first)
        rerun = _bucket_frame("09:30", [750.0])
        rerun["delta"] = [0.9]   # same key, different value — must NOT replace
        append_day_parquet(p, rerun)
        stored = pd.read_parquet(p)
        assert len(stored) == 1
        assert stored["delta"].iloc[0] == pytest.approx(0.5)

    def test_empty_frame_is_noop(self, tmp_path):
        p = tmp_path / "2026-07-16.parquet"
        added, total, q = append_day_parquet(p, pd.DataFrame())
        assert (added, total, q) == (0, 0, [])
        assert not p.exists()

    def test_unreadable_existing_quarantined_never_overwritten(self, tmp_path):
        """Unverified-destructive guard: an existing day frame that fails to
        read must be quarantine-renamed aside (bytes preserved), never
        replaced silently by the current sweep's rows."""
        p = tmp_path / "2026-07-16.parquet"
        corrupt = b"not a parquet file"
        p.write_bytes(corrupt)
        added, total, q = append_day_parquet(p, _bucket_frame("09:45", [750.0]))
        assert (added, total) == (1, 1)
        # Quarantine file name surfaced (→ _meta.json) and bytes preserved
        assert len(q) == 1 and q[0].startswith("2026-07-16.corrupt-")
        assert (tmp_path / q[0]).read_bytes() == corrupt
        # Fresh frame holds only the current sweep
        stored = pd.read_parquet(p)
        assert stored["snapshot_bucket"].tolist() == ["09:45"]

    def test_quarantine_rename_failure_raises_never_writes(self, tmp_path, monkeypatch):
        """If even the quarantine rename fails, the append must raise (caught
        by _sweep_root's INERT handler → root marked failed) rather than
        overwrite the unreadable frame."""
        p = tmp_path / "2026-07-16.parquet"
        corrupt = b"not a parquet file"
        p.write_bytes(corrupt)

        def _no_rename(self, target):
            raise OSError("EPERM: rename blocked")

        monkeypatch.setattr(Path, "rename", _no_rename)
        with pytest.raises(OSError):
            append_day_parquet(p, _bucket_frame("09:45", [750.0]))
        # Original bytes untouched, no tmp leftovers from a partial write
        assert p.read_bytes() == corrupt
        assert list(tmp_path.iterdir()) == [p]

    def test_quarantine_name_is_recovered_after_post_rename_kill(
        self, tmp_path, monkeypatch,
    ):
        from scripts import chain_snapshot_poller as poller

        p = tmp_path / "2026-07-16.parquet"
        p.write_bytes(b"not parquet")
        real_confirm = poller._confirm_file_durable
        killed = False

        def kill_after_visible(path):
            nonlocal killed
            if not killed and ".corrupt-" in path.name:
                killed = True
                raise OSError("kill after quarantine rename")
            return real_confirm(path)

        monkeypatch.setattr(poller, "_confirm_file_durable", kill_after_visible)
        with pytest.raises(OSError, match="kill after quarantine rename"):
            append_day_parquet(p, _bucket_frame("09:45", [750.0]))
        quarantines = list(tmp_path.glob("2026-07-16.corrupt-*.parquet"))
        assert not p.exists() and len(quarantines) == 1

        monkeypatch.setattr(poller, "_confirm_file_durable", real_confirm)
        added, total, recovered = append_day_parquet(
            p, _bucket_frame("09:45", [750.0]),
        )
        assert (added, total) == (1, 1)
        assert recovered == [quarantines[0].name]


# ── 6. Poller: RTH gate ────────────────────────────────────────────────────────

class TestRthGate:
    def test_within_window(self):
        assert _within_rth(datetime(hour=9, minute=35, **WED))
        assert _within_rth(datetime(hour=12, minute=0, **WED))
        assert _within_rth(datetime(hour=16, minute=0, **WED))

    def test_outside_window(self):
        assert not _within_rth(datetime(hour=9, minute=30, **WED))   # pre-window
        assert not _within_rth(datetime(hour=16, minute=1, **WED))   # post-close
        assert not _within_rth(datetime(hour=12, minute=0, **SAT))   # weekend

    def test_pre_rth_wait_from_0930_fire(self):
        # launchd fires 06:30 PT = 09:30 ET → wait ~5 min for the 09:35 start
        wait = _pre_rth_wait_sec(datetime(hour=9, minute=30, **WED))
        assert 0 < wait <= 5 * 60 + 1

    def test_no_wait_when_too_early_or_inside_or_weekend(self):
        assert _pre_rth_wait_sec(datetime(hour=8, minute=0, **WED)) == 0
        assert _pre_rth_wait_sec(datetime(hour=10, minute=0, **WED)) == 0
        assert _pre_rth_wait_sec(datetime(hour=9, minute=30, **SAT)) == 0

    def test_holiday_and_real_early_close_with_close_bucket_grace(self):
        # 2026-07-03 is the observed Independence Day closure.
        assert not _within_rth(datetime(2026, 7, 3, 10, 0, tzinfo=ET))
        # Friday after Thanksgiving is a 13:00 ET close.  The close bucket gets
        # the legacy sub-minute admission grace, never a later bucket.
        assert _within_rth(datetime(2026, 11, 27, 13, 0, 59, 999999, tzinfo=ET))
        assert not _within_rth(datetime(2026, 11, 27, 13, 1, 0, tzinfo=ET))
        assert _within_rth(datetime(2026, 7, 2, 16, 0, 59, 999999, tzinfo=ET))
        assert not _within_rth(datetime(2026, 7, 2, 16, 1, 0, tzinfo=ET))

    def test_window_start_is_actual_session_open_plus_five(self, monkeypatch):
        from scripts import chain_snapshot_poller as poller

        custom_open = datetime(2026, 7, 2, 10, 0, tzinfo=ET)
        custom_close = datetime(2026, 7, 2, 16, 0, tzinfo=ET)
        window = lambda _session: (custom_open, custom_close)
        monkeypatch.setattr(poller, "session_window_et", window)
        monkeypatch.setattr(bucket_completion, "session_window_et", window)
        assert not poller._within_rth(datetime(2026, 7, 2, 10, 4, 59, tzinfo=ET))
        assert poller._within_rth(datetime(2026, 7, 2, 10, 5, 0, tzinfo=ET))
        bucket_completion.validate_current_bucket(
            SESSION,
            "10:00",
            15,
            datetime(2026, 7, 2, 10, 5, 0, tzinfo=ET),
        )


class TestWallGridSchedule:
    @pytest.mark.parametrize(
        ("close_hour", "close_minute"),
        [(16, 0), (13, 0)],
    )
    def test_grid_sequence_includes_regular_and_early_close(
        self, close_hour, close_minute,
    ):
        from scripts import chain_snapshot_poller as poller

        current = datetime(2026, 7, 2, 9, 35, tzinfo=ET)
        close = current.replace(hour=close_hour, minute=close_minute)
        starts = [current]
        while current < close:
            current += timedelta(
                seconds=poller._seconds_to_next_wall_grid(current, 15),
            )
            starts.append(current)
        assert starts[-1] == close

    def test_pending_retry_is_fast_but_never_sleeps_past_bucket_edge(self):
        from scripts import chain_snapshot_poller as poller

        inside = datetime(2026, 7, 2, 9, 36, tzinfo=ET)
        assert poller._seconds_to_next_wall_grid(inside, 15, pending=True) == 30
        near_edge = datetime(2026, 7, 2, 9, 44, 59, 900000, tzinfo=ET)
        delay = poller._seconds_to_next_wall_grid(near_edge, 15, pending=True)
        assert 0 < delay <= 0.1


class TestSourceCompletionEvidence:
    @pytest.mark.parametrize("second", [None, pd.DataFrame()])
    def test_none_or_empty_second_endpoint_is_terminal_ineligible_but_chain_lands(
        self, tmp_path, monkeypatch, second,
    ):
        from collectors import thetadata as td
        from scripts import chain_snapshot_poller as poller

        chain_path = tmp_path / "SPY" / "2026-07-16.parquet"
        oi_path = tmp_path / "SPY" / "2026-07-16_oi.parquet"
        monkeypatch.setattr(poller, "day_parquet_path", lambda *_args: chain_path)
        monkeypatch.setattr(poller, "oi_parquet_path", lambda *_args: oi_path)
        monkeypatch.setattr(
            td,
            "snapshot_greeks",
            lambda _root, order: _first_frame() if order == "first" else second,
        )
        monkeypatch.setattr(td, "snapshot_open_interest", lambda _root: _oi_frame())

        result = poller._sweep_root("SPY", "2026-07-16", "12:00", True)
        assert result["error"] is None
        assert any("second_order snapshot" in item for item in result["completion_errors"])
        assert chain_path.exists()
        assert pd.read_parquet(chain_path)[SECOND_ORDER_JOIN_COLS].isna().all().all()
        with pytest.raises(bucket_completion.BucketStateError, match="incomplete source evidence"):
            bucket_completion.build_completion_summary(("SPY",), [result])

    @pytest.mark.parametrize("oi", [None, pd.DataFrame()])
    def test_none_or_empty_oi_is_terminal_ineligible_but_chain_lands(
        self, tmp_path, monkeypatch, oi,
    ):
        from collectors import thetadata as td
        from scripts import chain_snapshot_poller as poller

        chain_path = tmp_path / "SPY" / "2026-07-16.parquet"
        oi_path = tmp_path / "SPY" / "2026-07-16_oi.parquet"
        monkeypatch.setattr(poller, "day_parquet_path", lambda *_args: chain_path)
        monkeypatch.setattr(poller, "oi_parquet_path", lambda *_args: oi_path)
        monkeypatch.setattr(
            td,
            "snapshot_greeks",
            lambda _root, order: _first_frame() if order == "first" else _second_frame(),
        )
        monkeypatch.setattr(td, "snapshot_open_interest", lambda _root: oi)

        result = poller._sweep_root("SPY", "2026-07-16", "12:00", True)
        assert result["error"] is None
        assert any("open_interest snapshot" in item for item in result["completion_errors"])
        assert chain_path.exists() and not oi_path.exists()
        with pytest.raises(bucket_completion.BucketStateError, match="incomplete source evidence"):
            bucket_completion.build_completion_summary(("SPY",), [result])

    @pytest.mark.parametrize(
        "raw",
        [
            pd.Timestamp("2026-07-02T09:36:00.000000100"),
            pd.Timestamp("2026-07-02T09:36:00.000000900"),
        ],
    )
    def test_submicrosecond_vendor_clocks_are_rejected(self, raw):
        with pytest.raises(RuntimeError, match="exact to UTC microseconds"):
            _aware_vendor_clocks(pd.DataFrame({"snapshot_ts": [raw]}))

    def test_exact_microsecond_vendor_clock_is_preserved(self):
        clocks = _aware_vendor_clocks(pd.DataFrame({
            "snapshot_ts": [pd.Timestamp("2026-07-02T09:36:00.123456")],
        }))
        assert bucket_completion.utc_microseconds(clocks[0]) == (
            "2026-07-02T13:36:00.123456Z"
        )


# ── 7. Producer-owned durable bucket completion state ─────────────────────────

SESSION = "2026-07-02"


def _root_result(root: str, *, failed: bool = False, rows: int = 2) -> dict:
    return {
        "root": root,
        "rows": 0 if failed else rows,
        "total_rows": 0 if failed else rows,
        "oi_rows": 0 if failed else 1,
        "oi_total_rows": 0 if failed else 1,
        "error": "source failed" if failed else None,
        "completion_errors": [],
        "bucket_rows": 0 if failed else rows,
        "bucket_content_sha256": None if failed else "a" * 64,
        "parquet_sha256": None if failed else "b" * 64,
        "oi_parquet_sha256": None if failed else "c" * 64,
        "first_vendor_min_at": None if failed else "2026-07-02T13:35:00.000001Z",
        "first_vendor_max_at": None if failed else "2026-07-02T13:35:00.000002Z",
        "first_prebucket_rows": 0,
        "first_at_or_after_bucket_rows": 0 if failed else rows,
        "second_clock_matched_rows": 0 if failed else rows,
        "second_clock_unmatched_rows": 0,
        "quarantined": [],
        "oi_quarantined": [],
    }


def _sweep_summary(roots: list[str], *, failed: set[str] | None = None) -> dict:
    failed = failed or set()
    results = [_root_result(root, failed=root in failed) for root in roots]
    return {
        "bucket": "09:30",
        "universe_n": len(roots),
        "roots_ok": len(roots) - len(failed),
        "roots_failed": len(failed),
        "completion_roots_ok": len(roots) - len(failed),
        "completion_roots_failed": len(failed),
        "rows_appended": sum(row["rows"] for row in results),
        "rows_total": sum(row["total_rows"] for row in results),
        "oi_rows": sum(row["oi_rows"] for row in results),
        "oi_total_rows": sum(row["oi_total_rows"] for row in results),
        "sweep_sec": 0.1,
        "errors": [f"{root}: source failed" for root in sorted(failed)],
        "completion_errors": [],
        "quarantined": [],
        "_root_results": results,
    }


def _clock(*values: datetime):
    clocks = iter(values)
    return lambda: next(clocks)


def _records(receipt_root: Path, session: str = SESSION) -> list[dict]:
    return [
        json.loads(line)
        for line in (receipt_root / f"{session}.jsonl").read_text().splitlines()
    ]


def _patch_receipt_root(monkeypatch, tmp_path: Path) -> Path:
    from scripts import chain_snapshot_poller as poller

    root = tmp_path / "receipts"
    monkeypatch.setattr(poller, "_receipt_root", lambda: root)
    return root


def _complete_packet(monkeypatch, tmp_path: Path) -> dict:
    _patch_receipt_root(monkeypatch, tmp_path)
    captured: list[dict] = []
    summary = run_managed_sweep(
        ["SPY"], SESSION, "09:30", {"cadence_min": 15},
        now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
        now_fn=_clock(
            datetime(2026, 7, 2, 13, 36, 0, 100001, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 13, 36, 0, 100002, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 13, 36, 0, 100003, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 13, 36, 0, 100004, tzinfo=timezone.utc),
        ),
        sweep_fn=lambda roots, *_args: _sweep_summary(roots),
        completion_hook=captured.append,
    )
    assert summary["receipt_state"] == "complete"
    assert len(captured) == 1
    return captured[0]


def _patch_memory_publication_cursor(monkeypatch, publisher):
    holder: dict[str, dict | None] = {"cursor": None, "scan_cursor": None}

    def advance(_out_dir, packet, *, prefix_packets, activation_session):
        state = bucket_completion.validate_completion_packet(packet)
        holder["cursor"] = {
            "activation_session": activation_session,
            "session_date": state.intent["session_date"],
            "snapshot_bucket": state.intent["bucket"],
            "bucket_id": state.intent["bucket_id"],
            "availability_receipt_id": state.availability["receipt_id"],
            "completion_packet_sha256": hashlib.sha256(
                bucket_completion.canonical_bytes(packet)
            ).hexdigest(),
            **publisher.publication_prefix_receipt(prefix_packets),
        }

    def advance_scan(
        _out_dir,
        *,
        activation_session,
        from_session,
        to_session,
        sealed_session,
        sealed_ledger_sha256,
        sealed_packets,
    ):
        assert from_session >= activation_session
        holder["scan_cursor"] = {
            "activation_session": activation_session,
            "scan_session": to_session,
            "sealed_session": sealed_session,
            "sealed_ledger_sha256": sealed_ledger_sha256,
            "sealed_complete_count": len(sealed_packets),
        }

    monkeypatch.setattr(
        publisher, "read_publication_cursor", lambda _out_dir: holder["cursor"],
    )
    monkeypatch.setattr(
        publisher,
        "read_publication_scan_cursor",
        lambda _out_dir: holder["scan_cursor"],
    )
    monkeypatch.setattr(publisher, "advance_publication_cursor", advance)
    monkeypatch.setattr(
        publisher, "advance_publication_scan_cursor", advance_scan,
    )
    monkeypatch.setattr(
        publisher,
        "publication_scan_cursor_matches",
        lambda _out_dir, _cursor, _packets: True,
    )
    return holder


class TestBucketCompletionState:
    @pytest.mark.parametrize("history_sessions", [3, 80])
    def test_bounded_completion_window_decodes_only_two_sessions(
        self, tmp_path, monkeypatch, history_sessions,
    ):
        root = _patch_receipt_root(monkeypatch, tmp_path)
        sessions: list[str] = []
        candidate = date(2026, 1, 2)
        while len(sessions) < history_sessions:
            if bucket_completion.nyse_calendar.is_session(candidate):
                sessions.append(candidate.isoformat())
            candidate += timedelta(days=1)
        for session in sessions:
            local = datetime.combine(
                date.fromisoformat(session),
                datetime.min.time(),
                tzinfo=ET,
            ).replace(hour=9, minute=36)
            run_managed_sweep(
                ["SPY"], session, "09:30", {"cadence_min": 15},
                now=local,
                now_fn=lambda local=local: local.astimezone(timezone.utc),
                sweep_fn=lambda roots, *_args: _sweep_summary(
                    roots, failed={"SPY"},
                ),
            )

        decoded: list[str] = []
        real_decode = bucket_completion.decode_ledger

        def decode(raw, path):
            decoded.append(path.stem)
            return real_decode(raw, path)

        monkeypatch.setattr(bucket_completion, "decode_ledger", decode)
        with bucket_completion.BucketCompletionStore(root) as store:
            packets, receipts, has_more = store.complete_packets_from(
                sessions[0], max_sessions=2, require_start=True,
            )
        assert packets == []
        assert [item["session_date"] for item in receipts] == sessions[:2]
        assert decoded == sessions[:2]
        assert has_more is (history_sessions > 2)

    def test_bounded_window_rejects_nonterminal_tail_before_unread_ledger(
        self, tmp_path, monkeypatch,
    ):
        root = _patch_receipt_root(monkeypatch, tmp_path)
        pending_session = "2026-07-06"
        run_managed_sweep(
            ["SPY"], pending_session, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 6, 9, 36, tzinfo=ET),
            now_fn=lambda: datetime(
                2026, 7, 6, 13, 36, 0, 100001, tzinfo=timezone.utc,
            ),
            sweep_fn=lambda roots, *_args: _sweep_summary(roots, failed={"SPY"}),
        )
        (root / "2026-07-07.jsonl").write_bytes(b"")
        with bucket_completion.BucketCompletionStore(root) as store:
            with pytest.raises(
                bucket_completion.BucketStateError,
                match="nonterminal receipt session precedes a later ledger",
            ):
                store.complete_packets_from(
                    pending_session, max_sessions=1, require_start=True,
                )

    def test_exact_durability_and_clock_order(self, tmp_path, monkeypatch):
        root = _patch_receipt_root(monkeypatch, tmp_path)
        root.mkdir()
        (root / ".writer.lock").write_bytes(b"")
        order: list[str] = []
        real_fsync = bucket_completion.os.fsync

        def fsync_spy(fd: int) -> None:
            mode = os.fstat(fd).st_mode
            if stat.S_ISDIR(mode):
                order.append("directory_fsync")
            else:
                raw = os.pread(fd, os.fstat(fd).st_size, 0)
                if b'"kind":"availability"' in raw:
                    order.append("availability_fsync")
                elif b'"kind":"decision"' in raw:
                    order.append("decision_fsync")
                elif b'"kind":"intent"' in raw:
                    order.append("intent_fsync")
            real_fsync(fd)

        times = iter([
            datetime(2026, 7, 2, 13, 36, 0, 111111, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 13, 36, 0, 222222, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 13, 36, 1, 333333, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 13, 36, 2, 444444, tzinfo=timezone.utc),
        ])

        def clock():
            value = next(times)
            names = [
                "intent_clock", "source_admission_clock", "decision_clock",
                "availability_clock",
            ]
            order.append(names[len([item for item in order if item.endswith("_clock")])])
            return value

        def sweep(roots, session, bucket, cfg):
            order.extend(["source_begin", "parquet_durable"])
            return _sweep_summary(roots)

        monkeypatch.setattr(bucket_completion.os, "fsync", fsync_spy)
        summary = run_managed_sweep(
            ["SPY"], SESSION, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
            now_fn=clock,
            sweep_fn=sweep,
            completion_hook=lambda _packet: order.append("hook"),
        )
        assert summary["receipt_state"] == "complete"
        assert order.index("intent_clock") < order.index("intent_fsync")
        assert order.index("intent_fsync") < order.index("source_begin")
        assert order.index("source_admission_clock") < order.index("source_begin")
        assert order.index("parquet_durable") < order.index("decision_clock")
        assert order.index("decision_clock") < order.index("decision_fsync")
        assert order.index("decision_fsync") < order.index("availability_clock")
        assert order.index("availability_clock") < order.index("availability_fsync")
        assert order.index("availability_fsync") < order.index("hook")

    def test_intent_fsync_failure_makes_zero_source_calls_and_reuses_intent(
        self, tmp_path, monkeypatch,
    ):
        root = _patch_receipt_root(monkeypatch, tmp_path)
        root.mkdir()
        (root / ".writer.lock").write_bytes(b"")
        real_fsync = bucket_completion.os.fsync
        fail_once = True
        source_calls = 0

        def fsync_spy(fd: int) -> None:
            nonlocal fail_once
            if fail_once and not stat.S_ISDIR(os.fstat(fd).st_mode):
                fail_once = False
                raise OSError("simulated intent fsync failure")
            real_fsync(fd)

        def sweep(roots, session, bucket, cfg):
            nonlocal source_calls
            source_calls += 1
            return _sweep_summary(roots)

        clock = _clock(
            datetime(2026, 7, 2, 13, 36, 0, 123456, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 13, 36, 1, 123456, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 13, 36, 2, 123456, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 13, 36, 3, 123456, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 13, 36, 4, 123456, tzinfo=timezone.utc),
        )
        monkeypatch.setattr(bucket_completion.os, "fsync", fsync_spy)
        with pytest.raises(OSError, match="intent fsync failure"):
            run_managed_sweep(
                ["SPY"], SESSION, "09:30", {"cadence_min": 15},
                now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
                now_fn=clock, sweep_fn=sweep,
            )
        assert source_calls == 0
        first_intent = _records(root)[0]

        summary = run_managed_sweep(
            ["SPY"], SESSION, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 37, tzinfo=ET),
            now_fn=clock, sweep_fn=sweep,
        )
        assert summary["receipt_state"] == "complete"
        assert source_calls == 1
        assert _records(root)[0] == first_intent

    def test_partial_sweep_retries_frozen_roots_despite_config_drift(
        self, tmp_path, monkeypatch,
    ):
        from scripts import chain_snapshot_poller as poller

        monkeypatch.setattr(poller, "REPO_ROOT", tmp_path)
        drift_a = tmp_path / "configured-data-a"
        drift_b = tmp_path / "configured-data-b"
        configured_data_dir = {"value": str(drift_a)}
        monkeypatch.setattr(
            poller.config,
            "load",
            lambda: {"storage": {"data_dir": configured_data_dir["value"]}},
        )
        root = poller._receipt_root_path()
        expected_out_root = tmp_path / "data" / "chain_snapshots"
        calls: list[tuple[list[str], str, Path]] = []

        def partial(roots, session, bucket, cfg):
            calls.append((list(roots), bucket, poller._out_root()))
            return _sweep_summary(roots, failed={"QQQ"})

        summary = run_managed_sweep(
            ["SPY", "QQQ"], SESSION, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
            now_fn=lambda: datetime(2026, 7, 2, 13, 36, 0, 111111, tzinfo=timezone.utc),
            sweep_fn=partial,
        )
        assert summary["receipt_state"] == "intent_pending"
        assert [row["kind"] for row in _records(root)] == ["intent"]
        configured_data_dir["value"] = str(drift_b)

        def recovered(roots, session, bucket, cfg):
            calls.append((list(roots), bucket, poller._out_root()))
            return _sweep_summary(roots)

        summary = run_managed_sweep(
            ["MSFT"], SESSION, "09:35", {"cadence_min": 5},
            now=datetime(2026, 7, 2, 9, 37, tzinfo=ET),
            now_fn=_clock(
                datetime(2026, 7, 2, 13, 37, 1, 111111, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 37, 2, 111111, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 37, 3, 111111, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 37, 4, 111111, tzinfo=timezone.utc),
            ),
            sweep_fn=recovered,
        )
        assert summary["receipt_state"] == "complete"
        assert calls == [
            (["SPY", "QQQ"], "09:30", expected_out_root),
            (["SPY", "QQQ"], "09:30", expected_out_root),
        ]
        assert root == expected_out_root / "_bucket_receipts"
        assert not drift_a.exists() and not drift_b.exists()
        intent, decision, availability = _records(root)
        assert intent["roots"] == ["SPY", "QQQ"]
        assert intent["cadence_min"] == 15
        assert decision["completion"]["roots"] == intent["roots"]
        assert availability["decision_at"] == decision["decision_at"]

    def test_decision_only_crash_recovers_exact_clocks_without_source_retry(
        self, tmp_path, monkeypatch,
    ):
        root = _patch_receipt_root(monkeypatch, tmp_path)
        source_calls = 0

        def sweep(roots, session, bucket, cfg):
            nonlocal source_calls
            source_calls += 1
            return _sweep_summary(roots)

        calls = 0

        def crashing_clock():
            nonlocal calls
            calls += 1
            if calls == 1:
                return datetime(2026, 7, 2, 13, 36, 0, 111111, tzinfo=timezone.utc)
            if calls == 2:
                return datetime(2026, 7, 2, 13, 36, 0, 222222, tzinfo=timezone.utc)
            if calls == 3:
                return datetime(2026, 7, 2, 13, 36, 1, 333333, tzinfo=timezone.utc)
            raise RuntimeError("crash after decision")

        with pytest.raises(RuntimeError, match="crash after decision"):
            run_managed_sweep(
                ["SPY"], SESSION, "09:30", {"cadence_min": 15},
                now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
                now_fn=crashing_clock, sweep_fn=sweep,
            )
        before = _records(root)
        assert [row["kind"] for row in before] == ["intent", "decision"]

        summary = run_managed_sweep(
            ["SPY"], SESSION, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 37, tzinfo=ET),
            now_fn=lambda: datetime(
                2026, 7, 2, 13, 37, 0, 333333, tzinfo=timezone.utc,
            ),
            sweep_fn=lambda *_args: pytest.fail("decision recovery must not call source"),
        )
        after = _records(root)
        assert summary["receipt_state"] == "decision_recovered"
        assert source_calls == 1
        assert after[:2] == before
        assert after[2]["decision_at"] == before[1]["decision_at"]

    def test_later_same_session_decision_recovery_records_honest_availability(
        self, tmp_path, monkeypatch,
    ):
        root = _patch_receipt_root(monkeypatch, tmp_path)
        clock_calls = 0

        def decision_crash_clock():
            nonlocal clock_calls
            clock_calls += 1
            if clock_calls == 1:
                return datetime(2026, 7, 2, 13, 44, 0, 100001, tzinfo=timezone.utc)
            if clock_calls == 2:
                return datetime(2026, 7, 2, 13, 44, 0, 100002, tzinfo=timezone.utc)
            if clock_calls == 3:
                return datetime(2026, 7, 2, 13, 44, 1, 100003, tzinfo=timezone.utc)
            raise RuntimeError("decision-only kill point")

        with pytest.raises(RuntimeError, match="decision-only kill point"):
            run_managed_sweep(
                ["SPY"], SESSION, "09:30", {"cadence_min": 15},
                now=datetime(2026, 7, 2, 9, 44, tzinfo=ET),
                now_fn=decision_crash_clock,
                sweep_fn=lambda roots, *_args: _sweep_summary(roots),
            )
        decision = _records(root)[1]
        current_source: list[str] = []

        def current(roots, session, bucket, cfg):
            current_source.extend(roots)
            result = _sweep_summary(roots)
            result["bucket"] = bucket
            return result

        summary = run_managed_sweep(
            ["QQQ"], SESSION, "09:45", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 46, tzinfo=ET),
            now_fn=_clock(
                datetime(2026, 7, 2, 13, 46, 0, 100001, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 46, 0, 100002, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 46, 0, 100003, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 46, 0, 100004, tzinfo=timezone.utc),
            ),
            sweep_fn=current,
        )
        records = _records(root)
        assert [row["kind"] for row in records] == [
            "intent", "decision", "availability",
        ]
        assert summary["receipt_state"] == "decision_recovered"
        assert records[2]["decision_receipt_id"] == decision["receipt_id"]
        assert records[2]["availability_at"] == "2026-07-02T13:46:00.100002Z"
        assert current_source == []

    def test_availability_fsync_uncertain_retry_reconfirms_without_duplicate(
        self, tmp_path, monkeypatch,
    ):
        root = _patch_receipt_root(monkeypatch, tmp_path)
        root.mkdir()
        (root / ".writer.lock").write_bytes(b"")
        real_fsync = bucket_completion.os.fsync
        failed = False
        source_calls = 0

        def fsync_spy(fd: int) -> None:
            nonlocal failed
            mode = os.fstat(fd).st_mode
            raw = b"" if stat.S_ISDIR(mode) else os.pread(fd, os.fstat(fd).st_size, 0)
            if not failed and b'"kind":"availability"' in raw:
                failed = True
                raise OSError("availability fsync uncertain")
            real_fsync(fd)

        def sweep(roots, session, bucket, cfg):
            nonlocal source_calls
            source_calls += 1
            return _sweep_summary(roots)

        monkeypatch.setattr(bucket_completion.os, "fsync", fsync_spy)
        with pytest.raises(OSError, match="availability fsync uncertain"):
            run_managed_sweep(
                ["SPY"], SESSION, "09:30", {"cadence_min": 15},
                now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
                now_fn=_clock(
                    datetime(2026, 7, 2, 13, 36, 0, 111111, tzinfo=timezone.utc),
                    datetime(2026, 7, 2, 13, 36, 0, 222222, tzinfo=timezone.utc),
                    datetime(2026, 7, 2, 13, 36, 1, 333333, tzinfo=timezone.utc),
                    datetime(2026, 7, 2, 13, 36, 2, 444444, tzinfo=timezone.utc),
                ),
                sweep_fn=sweep,
            )
        visible = _records(root)
        assert [row["kind"] for row in visible] == ["intent", "decision", "availability"]

        summary = run_managed_sweep(
            ["SPY"], SESSION, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 37, tzinfo=ET),
            now_fn=lambda: datetime(
                2026, 7, 2, 13, 37, 0, 555555, tzinfo=timezone.utc,
            ),
            sweep_fn=lambda *_args: pytest.fail("complete replay must skip source"),
        )
        assert summary["receipt_state"] == "complete_skip"
        assert source_calls == 1
        assert _records(root) == visible

    def test_elapsed_partial_terminalizes_without_backfill_then_runs_current_bucket(
        self, tmp_path, monkeypatch,
    ):
        root = _patch_receipt_root(monkeypatch, tmp_path)

        run_managed_sweep(
            ["SPY", "QQQ"], SESSION, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
            now_fn=lambda: datetime(2026, 7, 2, 13, 36, 0, 111111, tzinfo=timezone.utc),
            sweep_fn=lambda roots, *_args: _sweep_summary(roots, failed={"QQQ"}),
        )
        current_calls: list[tuple[list[str], str]] = []

        def current(roots, session, bucket, cfg):
            current_calls.append((list(roots), bucket))
            result = _sweep_summary(roots)
            result["bucket"] = bucket
            return result

        summary = run_managed_sweep(
            ["MSFT"], SESSION, "09:45", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 46, tzinfo=ET),
            now_fn=_clock(
                datetime(2026, 7, 2, 13, 46, 0, 100001, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 46, 0, 100002, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 46, 0, 100003, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 46, 0, 100004, tzinfo=timezone.utc),
            ),
            sweep_fn=current,
        )
        assert summary["receipt_state"] == "complete"
        assert current_calls == [(["MSFT"], "09:45")]
        records = _records(root)
        assert [row["kind"] for row in records] == [
            "intent", "incomplete", "intent", "decision", "availability",
        ]
        assert records[1]["reason"] == "bucket_window_elapsed"
        assert records[1]["decision_receipt_id"] is None

    def test_prior_session_pending_terminalizes_as_session_elapsed(
        self, tmp_path, monkeypatch,
    ):
        root = _patch_receipt_root(monkeypatch, tmp_path)
        run_managed_sweep(
            ["SPY"], SESSION, "15:45", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 15, 46, tzinfo=ET),
            now_fn=lambda: datetime(2026, 7, 2, 19, 46, 0, 111111, tzinfo=timezone.utc),
            sweep_fn=lambda roots, *_args: _sweep_summary(roots, failed={"SPY"}),
        )
        called: list[str] = []

        def friday(roots, session, bucket, cfg):
            called.extend(roots)
            result = _sweep_summary(roots)
            result["bucket"] = bucket
            return result

        run_managed_sweep(
            ["QQQ"], "2026-07-06", "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 6, 9, 36, tzinfo=ET),
            now_fn=_clock(
                datetime(2026, 7, 6, 13, 36, 0, 100001, tzinfo=timezone.utc),
                datetime(2026, 7, 6, 13, 36, 0, 100002, tzinfo=timezone.utc),
                datetime(2026, 7, 6, 13, 36, 0, 100003, tzinfo=timezone.utc),
                datetime(2026, 7, 6, 13, 36, 0, 100004, tzinfo=timezone.utc),
            ),
            sweep_fn=friday,
        )
        assert called == ["QQQ"]
        old_records = _records(root, SESSION)
        assert [row["kind"] for row in old_records] == ["intent", "incomplete"]
        assert old_records[-1]["reason"] == "session_elapsed"

    def test_concurrent_writer_waits_and_second_skips_completed_source(
        self, tmp_path, monkeypatch,
    ):
        _patch_receipt_root(monkeypatch, tmp_path)
        entered = threading.Event()
        release = threading.Event()
        source_calls = 0
        source_guard = threading.Lock()

        def sweep(roots, session, bucket, cfg):
            nonlocal source_calls
            with source_guard:
                source_calls += 1
            entered.set()
            assert release.wait(timeout=5)
            return _sweep_summary(roots)

        now = datetime(2026, 7, 2, 9, 36, tzinfo=ET)
        durable_now = lambda: datetime(
            2026, 7, 2, 13, 36, 0, 123456, tzinfo=timezone.utc,
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(
                run_managed_sweep, ["SPY"], SESSION, "09:30", {"cadence_min": 15},
                now=now, now_fn=durable_now, sweep_fn=sweep,
            )
            assert entered.wait(timeout=5)
            second = pool.submit(
                run_managed_sweep, ["SPY"], SESSION, "09:30", {"cadence_min": 15},
                now=now, now_fn=durable_now, sweep_fn=sweep,
            )
            assert not second.done()
            release.set()
            assert first.result(timeout=5)["receipt_state"] == "complete"
            assert second.result(timeout=5)["receipt_state"] == "complete_skip"
        assert source_calls == 1

    @pytest.mark.parametrize(
        "raw",
        [
            b'{"kind":"intent"}',
            b'{"kind":"intent","kind":"intent"}\n',
            b'{"value":NaN}\n',
            b'\n',
        ],
    )
    def test_corrupt_receipt_state_fails_closed_before_source(
        self, tmp_path, monkeypatch, raw,
    ):
        root = _patch_receipt_root(monkeypatch, tmp_path)
        root.mkdir()
        (root / f"{SESSION}.jsonl").write_bytes(raw)
        with pytest.raises(bucket_completion.BucketStateError):
            run_managed_sweep(
                ["SPY"], SESSION, "09:30", {"cadence_min": 15},
                now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
                now_fn=lambda: datetime(
                    2026, 7, 2, 13, 36, 0, 123456, tzinfo=timezone.utc,
                ),
                sweep_fn=lambda *_args: pytest.fail("corrupt state must block source"),
            )

    def test_hook_failure_is_loud_but_source_and_receipt_stay_complete(
        self, tmp_path, monkeypatch, caplog,
    ):
        root = _patch_receipt_root(monkeypatch, tmp_path)
        source_calls = 0

        def sweep(roots, session, bucket, cfg):
            nonlocal source_calls
            source_calls += 1
            return _sweep_summary(roots)

        def broken_hook(_packet):
            raise RuntimeError("future core offline")

        with caplog.at_level("ERROR"):
            summary = run_managed_sweep(
                ["SPY"], SESSION, "09:30", {"cadence_min": 15},
                now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
                now_fn=_clock(
                    datetime(2026, 7, 2, 13, 36, 0, 100001, tzinfo=timezone.utc),
                    datetime(2026, 7, 2, 13, 36, 0, 100002, tzinfo=timezone.utc),
                    datetime(2026, 7, 2, 13, 36, 0, 100003, tzinfo=timezone.utc),
                    datetime(2026, 7, 2, 13, 36, 0, 100004, tzinfo=timezone.utc),
                ),
                sweep_fn=sweep,
                completion_hook=broken_hook,
            )
        assert summary["receipt_state"] == "complete"
        assert summary["roots_failed"] == 0
        assert summary["completion_hook_error"] == "future core offline"
        assert "post-availability completion hook failed" in caplog.text
        assert [row["kind"] for row in _records(root)] == [
            "intent", "decision", "availability",
        ]

        repaired: list[dict] = []
        retry = run_managed_sweep(
            ["SPY"], SESSION, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 37, tzinfo=ET),
            now_fn=lambda: datetime(
                2026, 7, 2, 13, 37, 0, 999999, tzinfo=timezone.utc,
            ),
            sweep_fn=lambda *_args: pytest.fail("completed retry cannot call source"),
            completion_hook=repaired.append,
        )
        assert retry["receipt_state"] == "complete_skip"
        assert source_calls == 1 and len(repaired) == 1

    def test_partial_sweep_never_calls_completion_hook(self, tmp_path, monkeypatch):
        _patch_receipt_root(monkeypatch, tmp_path)
        summary = run_managed_sweep(
            ["SPY"], SESSION, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
            now_fn=_clock(
                datetime(2026, 7, 2, 13, 36, 0, 100001, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 36, 0, 100002, tzinfo=timezone.utc),
            ),
            sweep_fn=lambda roots, *_args: _sweep_summary(roots, failed={"SPY"}),
            completion_hook=lambda _packet: pytest.fail(
                "partial source sweep cannot publish"
            ),
        )
        assert summary["receipt_state"] == "intent_pending"

    def test_receipts_validate_against_governed_schema(self, tmp_path, monkeypatch):
        jsonschema = pytest.importorskip("jsonschema")
        root = _patch_receipt_root(monkeypatch, tmp_path)
        run_managed_sweep(
            ["spy", "QQQ", "SPY"], SESSION, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
            now_fn=_clock(
                datetime(2026, 7, 2, 13, 36, 0, 100001, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 36, 0, 100002, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 36, 0, 100003, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 36, 0, 100004, tzinfo=timezone.utc),
            ),
            sweep_fn=lambda roots, *_args: _sweep_summary(roots),
        )
        schema_path = Path(__file__).parents[1] / (
            "contracts/options/chain_snapshots.bucket_completion.v1.schema.json"
        )
        schema = json.loads(schema_path.read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker(),
        )
        for record in _records(root):
            validator.validate(record)
        intent, decision, availability = _records(root)
        assert intent["roots"] == ["SPY", "QQQ"]
        assert decision["intent_receipt_id"] == intent["receipt_id"]
        assert availability["decision_receipt_id"] == decision["receipt_id"]
        assert decision["completion"]["result_sha256"]
        root_result = decision["completion"]["root_results"][0]
        assert root_result["bucket_rows"] > 0
        assert "first_prebucket_rows" in root_result
        assert "first_at_or_after_bucket_rows" in root_result
        assert "second_clock_matched_rows" in root_result
        assert "second_clock_unmatched_rows" in root_result

    def test_root_canonicalization_rejects_path_like_dot_components(self):
        with pytest.raises(bucket_completion.BucketStateError, match="invalid canonical"):
            bucket_completion.canonical_roots([".."])

    def test_invalid_cadence_relabel_cannot_append_over_valid_prefix(
        self, tmp_path, monkeypatch,
    ):
        root = _patch_receipt_root(monkeypatch, tmp_path)
        run_managed_sweep(
            ["SPY"], SESSION, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
            now_fn=_clock(
                datetime(2026, 7, 2, 13, 36, 0, 100001, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 36, 0, 100002, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 36, 0, 100003, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 36, 0, 100004, tzinfo=timezone.utc),
            ),
            sweep_fn=lambda roots, *_args: _sweep_summary(roots),
        )
        prefix = (root / f"{SESSION}.jsonl").read_bytes()
        with pytest.raises(bucket_completion.BucketStateError, match="exact integers"):
            run_managed_sweep(
                ["QQQ"], SESSION, "09:00", {"cadence_min": 60},
                now=datetime(2026, 7, 2, 9, 46, tzinfo=ET),
                now_fn=lambda: datetime(
                    2026, 7, 2, 13, 46, 0, 100001, tzinfo=timezone.utc,
                ),
                sweep_fn=lambda *_args: pytest.fail("invalid append must precede source"),
            )
        assert (root / f"{SESSION}.jsonl").read_bytes() == prefix

    def test_fresh_intent_blocks_preexisting_target_bucket_without_source(
        self, tmp_path, monkeypatch,
    ):
        from scripts import chain_snapshot_poller as poller

        receipt_root = _patch_receipt_root(monkeypatch, tmp_path)
        data_root = tmp_path / "data"
        day = data_root / "SPY" / f"{SESSION}.parquet"
        day.parent.mkdir(parents=True)
        _bucket_frame("09:30", [750.0]).to_parquet(day, index=False)
        monkeypatch.setattr(poller, "_out_root", lambda: data_root)
        source_calls = 0

        def forbidden(*_args):
            nonlocal source_calls
            source_calls += 1
            raise AssertionError("fresh orphan bytes must block source")

        summary = run_managed_sweep(
            ["SPY"], SESSION, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
            now_fn=lambda: datetime(
                2026, 7, 2, 13, 36, 0, 123456, tzinfo=timezone.utc,
            ),
            sweep_fn=forbidden,
        )
        assert summary["receipt_state"] == "intent_blocked_preexisting"
        assert summary["preexisting_target_roots"] == ["SPY"]
        assert source_calls == 0
        assert _records(receipt_root)[0]["preexisting_target_roots"] == ["SPY"]

        retry = run_managed_sweep(
            ["SPY"], SESSION, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 37, tzinfo=ET),
            now_fn=lambda: datetime(
                2026, 7, 2, 13, 37, 0, 123456, tzinfo=timezone.utc,
            ),
            sweep_fn=forbidden,
        )
        assert retry["receipt_state"] == "intent_blocked_preexisting"
        assert source_calls == 0 and len(_records(receipt_root)) == 1

    def test_stale_prelock_clock_cannot_authorize_pending_source(
        self, tmp_path, monkeypatch,
    ):
        root = _patch_receipt_root(monkeypatch, tmp_path)
        run_managed_sweep(
            ["SPY"], SESSION, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 44, 59, tzinfo=ET),
            now_fn=lambda: datetime(
                2026, 7, 2, 13, 44, 59, tzinfo=timezone.utc,
            ),
            sweep_fn=lambda roots, *_args: _sweep_summary(roots, failed={"SPY"}),
        )
        with pytest.raises(bucket_completion.BucketStateError, match="current cadence bucket"):
            run_managed_sweep(
                ["SPY"], SESSION, "09:30", {"cadence_min": 15},
                now=datetime(2026, 7, 2, 9, 44, 59, tzinfo=ET),
                now_fn=lambda: datetime(
                    2026, 7, 2, 13, 46, 0, tzinfo=timezone.utc,
                ),
                sweep_fn=lambda *_args: pytest.fail("elapsed pending source forbidden"),
            )
        records = _records(root)
        assert [row["kind"] for row in records] == ["intent", "incomplete"]
        assert records[-1]["reason"] == "bucket_window_elapsed"

    @pytest.mark.parametrize(
        ("session", "bucket", "open_clock", "source_clock", "decision_clock", "available_clock"),
        [
            (
                "2026-07-02", "16:00",
                datetime(2026, 7, 2, 20, 0, 20, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 20, 0, 40, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 20, 10, 0, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 20, 11, 0, tzinfo=timezone.utc),
            ),
            (
                "2026-11-27", "13:00",
                datetime(2026, 11, 27, 18, 0, 20, tzinfo=timezone.utc),
                datetime(2026, 11, 27, 18, 0, 40, tzinfo=timezone.utc),
                datetime(2026, 11, 27, 18, 10, 0, tzinfo=timezone.utc),
                datetime(2026, 11, 27, 18, 11, 0, tzinfo=timezone.utc),
            ),
        ],
    )
    def test_admitted_close_source_may_finish_through_close_plus_twenty(
        self, tmp_path, monkeypatch, session, bucket, open_clock, source_clock,
        decision_clock, available_clock,
    ):
        _patch_receipt_root(monkeypatch, tmp_path)

        def sweep(roots, *_args):
            summary = _sweep_summary(roots)
            summary["bucket"] = bucket
            return summary

        summary = run_managed_sweep(
            ["SPY"], session, bucket, {"cadence_min": 15},
            now=open_clock.astimezone(ET),
            now_fn=_clock(open_clock, source_clock, decision_clock, available_clock),
            sweep_fn=sweep,
        )
        assert summary["receipt_state"] == "complete"
        assert summary["availability_at"] == bucket_completion.utc_microseconds(
            available_clock,
        )

    def test_regular_bucket_crossing_next_edge_terminalizes_after_source(
        self, tmp_path, monkeypatch,
    ):
        root = _patch_receipt_root(monkeypatch, tmp_path)
        summary = run_managed_sweep(
            ["SPY"], SESSION, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 44, 30, tzinfo=ET),
            now_fn=_clock(
                datetime(2026, 7, 2, 13, 44, 30, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 44, 59, tzinfo=timezone.utc),
                datetime(2026, 7, 2, 13, 45, 0, 100, tzinfo=timezone.utc),
            ),
            sweep_fn=lambda roots, *_args: _sweep_summary(roots),
        )
        assert summary["receipt_state"] == "decision_terminal_incomplete"
        assert [row["kind"] for row in _records(root)] == ["intent", "incomplete"]

    def test_availability_crossing_grid_edge_preserves_durable_decision(
        self, tmp_path, monkeypatch,
    ):
        root = _patch_receipt_root(monkeypatch, tmp_path)
        calls = 0

        def crash_after_decision():
            nonlocal calls
            calls += 1
            clocks = {
                1: datetime(2026, 7, 2, 13, 44, 50, tzinfo=timezone.utc),
                2: datetime(2026, 7, 2, 13, 44, 51, tzinfo=timezone.utc),
                3: datetime(2026, 7, 2, 13, 44, 59, 999900, tzinfo=timezone.utc),
            }
            if calls == 4:
                raise RuntimeError("availability edge kill")
            return clocks[calls]

        with pytest.raises(RuntimeError, match="availability edge kill"):
            run_managed_sweep(
                ["SPY"], SESSION, "09:30", {"cadence_min": 15},
                now=datetime(2026, 7, 2, 9, 44, 50, tzinfo=ET),
                now_fn=crash_after_decision,
                sweep_fn=lambda roots, *_args: _sweep_summary(roots),
            )
        summary = run_managed_sweep(
            ["SPY"], SESSION, "09:45", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 45, 0, 100, tzinfo=ET),
            now_fn=lambda: datetime(
                2026, 7, 2, 13, 45, 0, 100, tzinfo=timezone.utc,
            ),
            sweep_fn=lambda *_args: pytest.fail("decision recovery cannot call source"),
        )
        assert summary["receipt_state"] == "decision_recovered"
        records = _records(root)
        assert [row["kind"] for row in records] == [
            "intent", "decision", "availability",
        ]
        assert records[-1]["availability_at"].endswith("00.000100Z")

    @pytest.mark.parametrize("mode", ["future", "inverted"])
    def test_vendor_clock_future_or_inversion_rejects_decision(
        self, tmp_path, monkeypatch, mode,
    ):
        root = _patch_receipt_root(monkeypatch, tmp_path)

        def hostile(roots, *_args):
            summary = _sweep_summary(roots)
            result = summary["_root_results"][0]
            if mode == "future":
                result["first_vendor_max_at"] = "2026-07-02T13:37:00.000000Z"
            else:
                result["first_vendor_min_at"] = "2026-07-02T13:35:01.000000Z"
                result["first_vendor_max_at"] = "2026-07-02T13:35:00.000000Z"
            return summary

        with pytest.raises(bucket_completion.BucketStateError):
            run_managed_sweep(
                ["SPY"], SESSION, "09:30", {"cadence_min": 15},
                now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
                now_fn=lambda: datetime(
                    2026, 7, 2, 13, 36, 30, tzinfo=timezone.utc,
                ),
                sweep_fn=hostile,
            )
        assert [row["kind"] for row in _records(root)] == ["intent"]

    def test_wholly_prebucket_first_order_is_bound_as_evidence_not_freshness(
        self, tmp_path, monkeypatch,
    ):
        root = _patch_receipt_root(monkeypatch, tmp_path)

        def prior_close(roots, *_args):
            summary = _sweep_summary(roots)
            result = summary["_root_results"][0]
            result["first_vendor_min_at"] = "2026-07-01T20:00:00.000001Z"
            result["first_vendor_max_at"] = "2026-07-01T20:00:00.000002Z"
            result["first_prebucket_rows"] = result["bucket_rows"]
            result["first_at_or_after_bucket_rows"] = 0
            return summary

        summary = run_managed_sweep(
            ["SPY"], SESSION, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
            now_fn=lambda: datetime(
                2026, 7, 2, 13, 36, 30, tzinfo=timezone.utc,
            ),
            sweep_fn=prior_close,
        )
        assert summary["receipt_state"] == "complete"
        completion_row = _records(root)[1]["completion"]["root_results"][0]
        assert completion_row["first_prebucket_rows"] == 2
        assert completion_row["first_at_or_after_bucket_rows"] == 0

    def test_semantically_mutated_physical_json_is_rejected(self, tmp_path, monkeypatch):
        root = _patch_receipt_root(monkeypatch, tmp_path)
        run_managed_sweep(
            ["SPY"], SESSION, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
            now_fn=lambda: datetime(
                2026, 7, 2, 13, 36, 30, tzinfo=timezone.utc,
            ),
            sweep_fn=lambda roots, *_args: _sweep_summary(roots),
        )
        path = root / f"{SESSION}.jsonl"
        rows = _records(root)
        mutated = json.dumps(rows[0], sort_keys=False, separators=(", ", ": "))
        path.write_text(
            mutated + "\n" + "\n".join(
                bucket_completion.canonical_bytes(row).decode() for row in rows[1:]
            ) + "\n"
        )
        with pytest.raises(bucket_completion.BucketStateError, match="non-canonical physical"):
            run_managed_sweep(
                ["SPY"], SESSION, "09:30", {"cadence_min": 15},
                now=datetime(2026, 7, 2, 9, 37, tzinfo=ET),
                now_fn=lambda: datetime(
                    2026, 7, 2, 13, 37, tzinfo=timezone.utc,
                ),
                sweep_fn=lambda *_args: pytest.fail("corrupt receipt blocks source"),
            )


def test_options_structure_hook_is_default_off_and_makes_no_subprocess_call(
    monkeypatch,
):
    from scripts import chain_snapshot_poller as poller

    monkeypatch.setattr(
        poller.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("disabled hook cannot spawn publisher"),
    )
    assert poller._options_structure_completion_hook({"cadence_min": 15}) is None


def test_options_structure_hook_passes_exact_receipt_to_existing_builder(
    tmp_path, monkeypatch,
):
    from scripts import chain_snapshot_poller as poller
    from scripts import build_options_structure_intraday as publisher

    packet = _complete_packet(monkeypatch, tmp_path)
    seen: dict[str, object] = {}

    def run(command, **kwargs):
        seen["command"] = command
        seen.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout=b"ok\n", stderr=b"")

    monkeypatch.setattr(poller, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(poller.subprocess, "run", run)
    monkeypatch.setattr(
        publisher,
        "publication_acknowledged",
        lambda out_dir, received: out_dir == tmp_path / "data" / "options_structure_intraday_r2"
        and received == packet,
    )
    hook = poller._options_structure_completion_hook({
        "options_structure_r2": {
            "enabled": True,
            "activation_session": SESSION,
            "timeout_sec": 120,
        },
    })
    assert hook is not None
    hook(packet)
    assert seen["command"] == [
        poller.sys.executable,
        "-m",
        "scripts.build_options_structure_intraday",
        "--completion-packet-stdin",
        "--data-root",
        str(tmp_path / "data" / "chain_snapshots"),
        "--out-dir",
        str(tmp_path / "data" / "options_structure_intraday_r2"),
        "--publish",
    ]
    assert seen["cwd"] == tmp_path
    assert seen["timeout"] == 120
    assert seen["capture_output"] is True
    assert seen["check"] is False
    decoded = bucket_completion.strict_json_loads(seen["input"])
    assert decoded == packet
    assert bucket_completion.validate_completion_packet(decoded).status == "complete"


def test_options_structure_hook_timeout_is_loud(tmp_path, monkeypatch):
    from scripts import chain_snapshot_poller as poller

    packet = _complete_packet(monkeypatch, tmp_path)
    monkeypatch.setattr(poller, "REPO_ROOT", tmp_path)

    def timeout(command, **_kwargs):
        raise subprocess.TimeoutExpired(command, 120)

    monkeypatch.setattr(poller.subprocess, "run", timeout)
    hook = poller._options_structure_completion_hook({
        "options_structure_r2": {
            "enabled": True,
            "activation_session": SESSION,
            "timeout_sec": 120,
        },
    })
    assert hook is not None
    with pytest.raises(RuntimeError, match="exceeded 120s"):
        hook(packet)


def test_options_structure_hook_abstains_before_exact_activation_floor(
    tmp_path, monkeypatch,
):
    from scripts import chain_snapshot_poller as poller

    packet = _complete_packet(monkeypatch, tmp_path)
    monkeypatch.setattr(
        poller,
        "_run_options_structure_publisher",
        lambda *_args, **_kwargs: pytest.fail("pre-floor packet cannot publish"),
    )
    hook = poller._options_structure_completion_hook({
        "options_structure_r2": {
            "enabled": True,
            "activation_session": "2026-07-06",
            "timeout_sec": 120,
        },
    })
    assert hook is not None
    assert hook(packet) is None


@pytest.mark.parametrize(
    "block",
    [
        True,
        {"enabled": "yes"},
        {"enabled": True, "timeout_sec": 120},
        {"enabled": True, "activation_session": "2026-07-04"},
        {
            "enabled": True,
            "activation_session": SESSION,
            "timeout_sec": 120.0,
        },
        {
            "enabled": True,
            "activation_session": SESSION,
            "timeout_sec": 121,
        },
    ],
)
def test_options_structure_hook_config_fails_closed(block):
    from scripts import chain_snapshot_poller as poller

    with pytest.raises(ValueError, match="options_structure_r2"):
        poller._options_structure_completion_hook({"options_structure_r2": block})


def test_completed_receipt_catchup_is_durable_bounded_and_idempotent(
    tmp_path, monkeypatch,
):
    from scripts import build_options_structure_intraday as publisher
    from scripts import chain_snapshot_poller as poller

    packet = _complete_packet(monkeypatch, tmp_path)
    receipt_root = tmp_path / "receipts"
    monkeypatch.setattr(poller, "_receipt_root_path", lambda: receipt_root)
    acknowledged: set[str] = set()
    attempts = 0

    def is_acknowledged(_out_dir, candidate):
        return candidate["availability"]["receipt_id"] in acknowledged

    def publish(candidate):
        nonlocal attempts
        attempts += 1
        assert candidate == packet
        if attempts == 1:
            raise RuntimeError("transient R2 outage")
        acknowledged.add(candidate["availability"]["receipt_id"])

    monkeypatch.setattr(publisher, "publication_acknowledged", is_acknowledged)
    cursor = _patch_memory_publication_cursor(monkeypatch, publisher)
    first = poller._retry_unacknowledged_publications(
        publish, activation_session=SESSION,
    )
    assert first["attempted"] == 1
    assert first["acknowledged"] == 0
    assert first["remaining"] == 1
    assert first["deep_reproofs"] <= 2
    assert "transient R2 outage" in first["errors"][-1]

    second = poller._retry_unacknowledged_publications(
        publish, activation_session=SESSION,
    )
    assert second["attempted"] == 1
    assert second["acknowledged"] == 1
    assert second["remaining"] == 0

    third = poller._retry_unacknowledged_publications(
        publish, activation_session=SESSION,
    )
    assert third["complete_scanned"] == 1
    assert third["pending_before"] == 0
    assert third["attempted"] == 0
    assert attempts == 2

    changed_floor = poller._retry_unacknowledged_publications(
        lambda _packet: pytest.fail("activation drift cannot publish"),
        activation_session="2026-07-01",
    )
    assert changed_floor["remaining"] == 1
    assert "activation does not match" in changed_floor["errors"][0]


def test_ack_written_before_cursor_restart_advances_without_republication(
    tmp_path, monkeypatch,
):
    from scripts import build_options_structure_intraday as publisher
    from scripts import chain_snapshot_poller as poller

    packet = _complete_packet(monkeypatch, tmp_path)
    monkeypatch.setattr(
        poller, "_receipt_root_path", lambda: tmp_path / "receipts",
    )
    acknowledged = {packet["availability"]["receipt_id"]}
    monkeypatch.setattr(
        publisher,
        "publication_acknowledged",
        lambda _out_dir, candidate: (
            candidate["availability"]["receipt_id"] in acknowledged
        ),
    )
    cursor = _patch_memory_publication_cursor(monkeypatch, publisher)
    status = poller._retry_unacknowledged_publications(
        lambda _packet: pytest.fail("acknowledged packet must not republish"),
        activation_session=SESSION,
    )
    assert status["attempted"] == 0
    assert status["acknowledged"] == 1
    assert status["remaining"] == 0
    assert cursor["cursor"]["snapshot_bucket"] == "09:30"


def test_derivative_cursor_error_is_contained_and_suppresses_only_projection(
    tmp_path, monkeypatch,
):
    from scripts import build_options_structure_intraday as publisher
    from scripts import chain_snapshot_poller as poller

    _complete_packet(monkeypatch, tmp_path)
    monkeypatch.setattr(
        poller, "_receipt_root_path", lambda: tmp_path / "receipts",
    )
    monkeypatch.setattr(
        publisher,
        "read_publication_cursor",
        lambda _out_dir: {
            "activation_session": SESSION,
            "session_date": SESSION,
            "snapshot_bucket": "09:45",
            "bucket_id": "csb_absent",
            "availability_receipt_id": "csr_absent",
            "completion_packet_sha256": "0" * 64,
            "complete_prefix_count": 1,
            "complete_prefix_sha256": "1" * 64,
        },
    )
    status = poller._retry_unacknowledged_publications(
        lambda _packet: pytest.fail("bad cursor cannot invoke projection"),
        activation_session=SESSION,
    )
    assert status["remaining"] == 1
    assert status["attempted"] == 0
    assert "does not identify exactly one" in status["errors"][0]


def test_missing_scan_floor_ledger_suppresses_projection_not_source(
    tmp_path, monkeypatch,
):
    from scripts import build_options_structure_intraday as publisher
    from scripts import chain_snapshot_poller as poller

    _complete_packet(monkeypatch, tmp_path)
    receipt_root = tmp_path / "receipts"
    monkeypatch.setattr(poller, "_receipt_root_path", lambda: receipt_root)
    cursor = _patch_memory_publication_cursor(monkeypatch, publisher)
    cursor["scan_cursor"] = {
        "activation_session": SESSION,
        "scan_session": "2026-07-06",
        "sealed_session": SESSION,
        "sealed_ledger_sha256": hashlib.sha256(
            (receipt_root / f"{SESSION}.jsonl").read_bytes()
        ).hexdigest(),
        "sealed_complete_count": 1,
    }
    status = poller._retry_unacknowledged_publications(
        lambda _packet: pytest.fail("invalid scan floor cannot project"),
        activation_session=SESSION,
    )
    assert status["remaining"] == 1
    assert status["attempted"] == 0
    assert "scan cursor" in status["errors"][0]

    source_calls: list[str] = []

    def source(roots, *_args):
        source_calls.extend(roots)
        result = _sweep_summary(roots)
        result["bucket"] = "09:45"
        return result

    summary = run_managed_sweep(
        ["SPY"], SESSION, "09:45", {"cadence_min": 15},
        now=datetime(2026, 7, 2, 9, 46, tzinfo=ET),
        now_fn=_clock(
            datetime(2026, 7, 2, 13, 46, 0, 100001, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 13, 46, 0, 100002, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 13, 46, 0, 100003, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 13, 46, 0, 100004, tzinfo=timezone.utc),
        ),
        sweep_fn=source,
    )
    assert summary["receipt_state"] == "complete"
    assert source_calls == ["SPY"]


def test_missing_scan_cursor_recovers_from_activation_bound_delivery_cursor(
    tmp_path, monkeypatch,
):
    from scripts import build_options_structure_intraday as publisher
    from scripts import chain_snapshot_poller as poller

    first = _complete_packet(monkeypatch, tmp_path)
    later_session = "2026-07-06"
    captured: list[dict] = []
    run_managed_sweep(
        ["SPY"], later_session, "09:30", {"cadence_min": 15},
        now=datetime(2026, 7, 6, 9, 36, tzinfo=ET),
        now_fn=_clock(
            datetime(2026, 7, 6, 13, 36, 0, 100001, tzinfo=timezone.utc),
            datetime(2026, 7, 6, 13, 36, 0, 100002, tzinfo=timezone.utc),
            datetime(2026, 7, 6, 13, 36, 0, 100003, tzinfo=timezone.utc),
            datetime(2026, 7, 6, 13, 36, 0, 100004, tzinfo=timezone.utc),
        ),
        sweep_fn=lambda roots, *_args: _sweep_summary(roots),
        completion_hook=captured.append,
    )
    later = captured[0]
    monkeypatch.setattr(
        poller, "_receipt_root_path", lambda: tmp_path / "receipts",
    )
    acknowledged = {
        first["availability"]["receipt_id"],
        later["availability"]["receipt_id"],
    }
    monkeypatch.setattr(
        publisher,
        "publication_acknowledged",
        lambda _out_dir, packet: packet["availability"]["receipt_id"] in acknowledged,
    )
    cursor = _patch_memory_publication_cursor(monkeypatch, publisher)
    publisher.advance_publication_cursor(
        Path("unused"),
        later,
        prefix_packets=[later],
        activation_session=SESSION,
    )
    assert cursor["scan_cursor"] is None
    status = poller._retry_unacknowledged_publications(
        lambda _packet: pytest.fail("delivery cursor already covers the packet"),
        activation_session=SESSION,
    )
    assert status["errors"] == []
    assert status["remaining"] == 0
    assert status["deep_reproofs"] == 1


def test_completed_receipt_catchup_preserves_epoch_order_and_one_per_pass(
    tmp_path, monkeypatch,
):
    from scripts import build_options_structure_intraday as publisher
    from scripts import chain_snapshot_poller as poller

    _complete_packet(monkeypatch, tmp_path)
    run_managed_sweep(
        ["SPY"], SESSION, "09:45", {"cadence_min": 15},
        now=datetime(2026, 7, 2, 9, 46, tzinfo=ET),
        now_fn=_clock(
            datetime(2026, 7, 2, 13, 46, 0, 100001, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 13, 46, 0, 100002, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 13, 46, 0, 100003, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 13, 46, 0, 100004, tzinfo=timezone.utc),
        ),
        sweep_fn=lambda roots, *_args: {
            **_sweep_summary(roots),
            "bucket": "09:45",
        },
    )
    monkeypatch.setattr(
        poller, "_receipt_root_path", lambda: tmp_path / "receipts",
    )
    acknowledged: set[str] = set()
    published: list[str] = []

    def is_acknowledged(_out_dir, packet):
        return packet["availability"]["receipt_id"] in acknowledged

    def publish(packet):
        published.append(packet["intent"]["bucket"])
        acknowledged.add(packet["availability"]["receipt_id"])

    monkeypatch.setattr(publisher, "publication_acknowledged", is_acknowledged)
    cursor = _patch_memory_publication_cursor(monkeypatch, publisher)
    first = poller._retry_unacknowledged_publications(
        publish, activation_session=SESSION,
    )
    assert first["pending_before"] == 2
    assert first["attempted"] == 1
    assert first["remaining"] == 1
    assert first["deep_reproofs"] <= 2
    assert published == ["09:30"]

    second = poller._retry_unacknowledged_publications(
        publish, activation_session=SESSION,
    )
    assert second["pending_before"] == 1
    assert second["remaining"] == 0
    assert second["deep_reproofs"] <= 2
    assert published == ["09:30", "09:45"]

    with bucket_completion.BucketCompletionStore(tmp_path / "receipts") as store:
        packets, _receipts, _has_more = store.complete_packets_from(
            SESSION, max_sessions=1, require_start=True,
        )
    cursor["cursor"].update(publisher.publication_prefix_receipt([packets[-1]]))
    drift = poller._retry_unacknowledged_publications(
        lambda _packet: pytest.fail("changed prefix cannot publish"),
        activation_session=SESSION,
    )
    assert drift["remaining"] == 2
    assert "prefix changed" in drift["errors"][0]


def test_catchup_persists_progress_across_terminal_empty_session(
    tmp_path, monkeypatch,
):
    from scripts import build_options_structure_intraday as publisher
    from scripts import chain_snapshot_poller as poller

    first_packet = _complete_packet(monkeypatch, tmp_path)
    receipt_root = tmp_path / "receipts"
    empty_session = "2026-07-06"
    final_session = "2026-07-07"
    pending = run_managed_sweep(
        ["SPY"], empty_session, "09:30", {"cadence_min": 15},
        now=datetime(2026, 7, 6, 9, 36, tzinfo=ET),
        now_fn=lambda: datetime(
            2026, 7, 6, 13, 36, 0, 100001, tzinfo=timezone.utc,
        ),
        sweep_fn=lambda roots, *_args: _sweep_summary(roots, failed={"SPY"}),
    )
    assert pending["receipt_state"] == "intent_pending"
    captured: list[dict] = []
    run_managed_sweep(
        ["SPY"], final_session, "09:30", {"cadence_min": 15},
        now=datetime(2026, 7, 7, 9, 36, tzinfo=ET),
        now_fn=_clock(
            datetime(2026, 7, 7, 13, 36, 0, 100001, tzinfo=timezone.utc),
            datetime(2026, 7, 7, 13, 36, 0, 100002, tzinfo=timezone.utc),
            datetime(2026, 7, 7, 13, 36, 0, 100003, tzinfo=timezone.utc),
            datetime(2026, 7, 7, 13, 36, 0, 100004, tzinfo=timezone.utc),
        ),
        sweep_fn=lambda roots, *_args: _sweep_summary(roots),
        completion_hook=captured.append,
    )
    assert len(captured) == 1
    assert [row["kind"] for row in _records(receipt_root, empty_session)] == [
        "intent", "incomplete",
    ]

    monkeypatch.setattr(poller, "_receipt_root_path", lambda: receipt_root)
    acknowledged: set[str] = set()
    published: list[tuple[str, str]] = []

    def is_acknowledged(_out_dir, packet):
        return packet["availability"]["receipt_id"] in acknowledged

    def publish(packet):
        published.append((
            packet["intent"]["session_date"], packet["intent"]["bucket"],
        ))
        acknowledged.add(packet["availability"]["receipt_id"])

    monkeypatch.setattr(publisher, "publication_acknowledged", is_acknowledged)
    cursor = _patch_memory_publication_cursor(monkeypatch, publisher)
    first = poller._retry_unacknowledged_publications(
        publish, activation_session=SESSION,
    )
    assert first["acknowledged"] == 1
    assert published == [(SESSION, "09:30")]

    second = poller._retry_unacknowledged_publications(
        publish, activation_session=SESSION,
    )
    assert second["attempted"] == 0
    assert second["scan_advanced"] == 1
    assert second["remaining"] == 1
    assert cursor["scan_cursor"]["scan_session"] == empty_session

    third = poller._retry_unacknowledged_publications(
        publish, activation_session=SESSION,
    )
    assert third["acknowledged"] == 1
    assert third["remaining"] == 0
    assert published == [(SESSION, "09:30"), (final_session, "09:30")]
    assert first_packet["intent"]["session_date"] == SESSION

    cursor["scan_cursor"]["sealed_ledger_sha256"] = "0" * 64
    drift = poller._retry_unacknowledged_publications(
        lambda _packet: pytest.fail("corrupt scan binding cannot publish"),
        activation_session=SESSION,
    )
    assert drift["remaining"] == 1
    assert "ledger hash drifted" in drift["errors"][0]


def test_atomic_parquet_install_has_file_replace_directory_verify_order(
    tmp_path, monkeypatch,
):
    from scripts import chain_snapshot_poller as poller

    order: list[str] = []
    real_fsync = poller.os.fsync
    real_replace = poller.os.replace

    def fsync_spy(fd: int) -> None:
        order.append("directory_fsync" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file_fsync")
        real_fsync(fd)

    def replace_spy(source, target) -> None:
        order.append("replace")
        real_replace(source, target)

    monkeypatch.setattr(poller.os, "fsync", fsync_spy)
    monkeypatch.setattr(poller.os, "replace", replace_spy)
    path = tmp_path / "SPY" / "2026-07-02.parquet"
    installed = _atomic_install_parquet(path, _bucket_frame("09:30", [750.0]))
    assert len(installed) == 1
    # New directory durability syncs precede this suffix; the installed object
    # itself is file-fsynced before replace, then parent-fsynced and reverified.
    assert order[-5:] == [
        "file_fsync", "replace", "directory_fsync", "file_fsync", "directory_fsync",
    ]


def test_atomic_parquet_install_rejects_same_count_wrong_content(tmp_path, monkeypatch):
    real_to_parquet = pd.DataFrame.to_parquet

    def malicious_to_parquet(self, path, *args, **kwargs):
        wrong = self.copy()
        wrong["strike"] = 999.0
        wrong["snapshot_bucket"] = "09:15"
        return real_to_parquet(wrong, path, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_parquet", malicious_to_parquet)
    with pytest.raises(RuntimeError, match="content drift"):
        _atomic_install_parquet(
            tmp_path / "SPY" / f"{SESSION}.parquet",
            _bucket_frame("09:30", [750.0]),
            required_root="SPY",
            required_bucket="09:30",
        )


def test_content_digest_preserves_large_integer_identity_with_mixed_float():
    base = pd.DataFrame({
        "root": ["SPY"],
        "expiration": pd.to_datetime(["2026-07-24"]),
        "strike": [750.0],
        "right": ["C"],
        "snapshot_bucket": ["09:30"],
        "large_exact": pd.Series([2**53 + 1], dtype="int64"),
        "mixed_float": [0.5],
    })
    changed = base.copy()
    changed["large_exact"] = pd.Series([2**53 + 2], dtype="int64")
    assert _frame_content_sha256(base) != _frame_content_sha256(changed)


def test_completion_rejects_prior_aggregate_without_target_bucket_rows():
    result = _root_result("SPY", rows=0)
    result["total_rows"] = 100
    with pytest.raises(bucket_completion.BucketStateError, match="bucket_rows"):
        bucket_completion.build_completion_summary(("SPY",), [result])


def test_visible_directory_retry_reconfirms_target_and_parent(tmp_path, monkeypatch):
    target = tmp_path / "receipts"
    real_sync = bucket_completion._fsync_directory
    failed = False

    def fail_parent_once(path):
        nonlocal failed
        if path == tmp_path and target.exists() and not failed:
            failed = True
            raise OSError("parent fsync uncertain")
        return real_sync(path)

    monkeypatch.setattr(bucket_completion, "_fsync_directory", fail_parent_once)
    with pytest.raises(OSError, match="parent fsync uncertain"):
        bucket_completion.ensure_directory_durable(target)
    assert target.is_dir()

    calls = []

    def record(path):
        calls.append(path)
        return real_sync(path)

    monkeypatch.setattr(bucket_completion, "_fsync_directory", record)
    bucket_completion.ensure_directory_durable(target)
    assert target in calls and tmp_path in calls


def test_visible_intent_after_parent_fsync_error_is_reconfirmed_before_source(
    tmp_path, monkeypatch,
):
    receipt_root = _patch_receipt_root(monkeypatch, tmp_path)
    receipt_root.mkdir()
    (receipt_root / ".writer.lock").write_bytes(b"")
    real_sync = bucket_completion._fsync_directory
    root_syncs = 0
    source_calls = 0

    def fail_intent_parent(path):
        nonlocal root_syncs
        if path == receipt_root:
            root_syncs += 1
            if root_syncs == 2:
                raise OSError("intent parent fsync uncertain")
        return real_sync(path)

    def source(roots, *_args):
        nonlocal source_calls
        source_calls += 1
        return _sweep_summary(roots)

    monkeypatch.setattr(bucket_completion, "_fsync_directory", fail_intent_parent)
    with pytest.raises(OSError, match="intent parent fsync uncertain"):
        run_managed_sweep(
            ["SPY"], SESSION, "09:30", {"cadence_min": 15},
            now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
            now_fn=lambda: datetime(
                2026, 7, 2, 13, 36, tzinfo=timezone.utc,
            ),
            sweep_fn=source,
        )
    assert source_calls == 0 and [row["kind"] for row in _records(receipt_root)] == [
        "intent",
    ]

    confirmed = []

    def record_sync(path):
        confirmed.append(path)
        return real_sync(path)

    monkeypatch.setattr(bucket_completion, "_fsync_directory", record_sync)

    def current(roots, _session, bucket, _cfg):
        result = _sweep_summary(roots)
        result["bucket"] = bucket
        return result

    summary = run_managed_sweep(
        ["QQQ"], SESSION, "09:45", {"cadence_min": 15},
        now=datetime(2026, 7, 2, 9, 46, tzinfo=ET),
        now_fn=lambda: datetime(
            2026, 7, 2, 13, 46, tzinfo=timezone.utc,
        ),
        sweep_fn=current,
    )
    assert summary["receipt_state"] == "complete"
    assert receipt_root in confirmed
    assert [row["kind"] for row in _records(receipt_root)] == [
        "intent", "incomplete", "intent", "decision", "availability",
    ]


@pytest.mark.parametrize("invalid", [True, "1", 0, 2, 1.0])
def test_hard_max_concurrent_rejects_non_exact_one_before_receipt(
    tmp_path, monkeypatch, invalid,
):
    from scripts import chain_snapshot_poller as poller

    assert invalid != 1 or type(invalid) is not int
    with pytest.raises(ValueError, match="exact integer 1"):
        _max_concurrent({"max_concurrent": invalid})
    monkeypatch.setattr(
        poller, "_receipt_root", lambda: pytest.fail("invalid config cannot create receipt"),
    )
    with pytest.raises(ValueError, match="exact integer 1"):
        run_managed_sweep(
            ["SPY"], SESSION, "09:30",
            {"cadence_min": 15, "max_concurrent": invalid},
            now=datetime(2026, 7, 2, 9, 36, tzinfo=ET),
            sweep_fn=lambda *_args: pytest.fail("invalid config cannot call source"),
        )


def test_schema_annotations_and_runtime_reject_float_exact_integer_fields():
    schema = json.loads((Path(__file__).parents[1] / (
        "contracts/options/chain_snapshots.bucket_completion.v1.schema.json"
    )).read_text())
    cadence_schema = schema["$defs"]["intent"]["properties"]["cadence_min"]
    failed_schema = schema["$defs"]["completion"]["properties"]["roots_failed"]
    assert cadence_schema["type"] == "integer"
    assert cadence_schema["x-exact-json-integer"] is True
    assert failed_schema["type"] == "integer"
    assert failed_schema["x-exact-json-integer"] is True
    with pytest.raises(bucket_completion.BucketStateError, match="exact integers"):
        bucket_completion.validate_cadence_min(15.0)
    complete = bucket_completion.build_completion_summary(
        ("SPY",), [_root_result("SPY")],
    )
    complete["roots_failed"] = 0.0
    with pytest.raises(bucket_completion.BucketStateError, match="exact non-negative"):
        bucket_completion._validate_completion(complete, {"roots": ["SPY"]})


@pytest.mark.parametrize("bad_root", ["spy", "SPY "])
def test_installed_chain_rejects_noncanonical_root_and_poisoned_prior_row(
    tmp_path, bad_root,
):
    from scripts import chain_snapshot_poller as poller

    target = join_orders(_first_frame(), _second_frame())
    target["snapshot_bucket"] = "09:30"
    target["source"] = "chain_snapshot"
    prior = target.copy()
    prior["snapshot_bucket"] = "09:15"
    prior["root"] = bad_root
    path = tmp_path / "day.parquet"
    pd.concat([prior, target], ignore_index=True).to_parquet(path, index=False)
    with pytest.raises(RuntimeError, match="non-canonical or wrong root"):
        poller._chain_storage_evidence(path, "SPY", "09:30")


def test_installed_chain_rejects_missing_column_and_wrong_prior_source(tmp_path):
    from scripts import chain_snapshot_poller as poller

    target = join_orders(_first_frame(), _second_frame())
    target["snapshot_bucket"] = "09:30"
    target["source"] = "chain_snapshot"
    missing_path = tmp_path / "missing.parquet"
    target.drop(columns=["theta"]).to_parquet(missing_path, index=False)
    with pytest.raises(RuntimeError, match="missing W0a columns"):
        poller._chain_storage_evidence(missing_path, "SPY", "09:30")

    prior = target.copy()
    prior["snapshot_bucket"] = "09:15"
    prior["source"] = "wrong_lane"
    poison_path = tmp_path / "poison.parquet"
    pd.concat([prior, target], ignore_index=True).to_parquet(poison_path, index=False)
    with pytest.raises(RuntimeError, match="wrong source tag"):
        poller._chain_storage_evidence(poison_path, "SPY", "09:30")


@pytest.mark.parametrize(
    ("root", "source", "drop_column"),
    [("spy", "chain_snapshot", None), ("SPY ", "chain_snapshot", None),
     ("SPY", "wrong_lane", None), ("SPY", "chain_snapshot", "open_interest")],
)
def test_installed_oi_requires_exact_root_source_and_shape(
    root, source, drop_column,
):
    from scripts import chain_snapshot_poller as poller

    frame = _oi_frame()
    frame["root"] = root
    frame["source"] = source
    if drop_column is not None:
        frame = frame.drop(columns=[drop_column])
    with pytest.raises(RuntimeError):
        poller._validate_oi_frame(frame, "SPY")


def test_launchd_crash_recovery_and_installed_worktree_contract():
    plist_path = Path(__file__).parents[1] / (
        "ops/launchd/com.mastermind.chainsnapshots.plist"
    )
    payload = plistlib.loads(plist_path.read_bytes())
    assert payload["KeepAlive"] == {"SuccessfulExit": False}
    assert payload["ThrottleInterval"] == 60
    deploy = "/Users/chriswong/chainsnap-ops-wt"
    assert payload["WorkingDirectory"] == deploy
    assert payload["ProgramArguments"][0].startswith(f"{deploy}/")
    assert payload["ProgramArguments"][1] == f"{deploy}/.env"
    assert payload["EnvironmentVariables"]["PYTHONPATH"] == deploy
    assert all(
        "/Users/chriswong/flow-ops-wt" not in argument
        for argument in payload["ProgramArguments"]
    )


def test_runbook_pins_exact_clock_join_recovery_and_installed_reload_order():
    runbook = (Path(__file__).parents[1] / "ops/CHAIN_SNAPSHOTS_RUNBOOK.md").read_text()
    assert "`(root, expiration, strike, right, snapshot_ts)`" in runbook
    assert "non-null second Greek" in runbook
    assert "/Users/chriswong/chainsnap-ops-wt" in runbook
    assert "/Users/chriswong/flow-ops-wt/data/chain_snapshots" in runbook
    assert "standalone shallow clone" in runbook
    assert "exact symlink" in runbook
    rollout = runbook.split("trap restore_on_error EXIT", 1)[1].split(
        "ROLLOUT_COMMITTED=1", 1
    )[0]
    commands = [
        'launchctl bootout "$DOMAIN/$LABEL"',
        "git clone --depth 1",
        'ln -s "$STATE"',
        'cmp "$BEFORE_MANIFEST" "$VIA_DEPLOY_MANIFEST"',
        'plutil -lint "$NEW/ops/launchd/$LABEL.plist"',
        'install -m 644 "$DEPLOY/ops/launchd/$LABEL.plist"',
        'plutil -lint "$PLIST"',
        'launchctl bootstrap "$DOMAIN" "$PLIST"',
        'launchctl print "$DOMAIN/$LABEL" | grep -F "$DEPLOY"',
    ]
    positions = [rollout.index(command) for command in commands]
    assert positions == sorted(positions)
    assert "KeepAlive.SuccessfulExit=false" in runbook
    assert "relative-path, byte-size, and SHA-256" in runbook
    assert "producer is stopped" in runbook
    assert "Never copy or restore this state after the producer starts" in runbook
    assert "pgrep -f 'scripts[.]chain_snapshot_poller'" in runbook
    assert "Do not use `launchctl kickstart`" in runbook
    assert "restore_on_error" in runbook
    assert "rollout() (" in runbook
    assert "trap 'exit 130' INT" in runbook
    assert "trap 'exit 143' TERM" in runbook
    assert "set +e" in runbook
    assert "SWAPPED" not in runbook
    assert "ROLLBACK_STOPPED=1" in runbook
    assert "HARD MANUAL STOP: scheduler/PID still active" in runbook
    assert '"$PRIOR_DEPLOY_READY" -eq 1' in runbook
    assert 'merge-base --is-ancestor "$EXPECTED_MERGE" origin/main' in runbook
    assert 'test ! -L "$STATE"' in runbook
    assert 'for _ in $(seq 1 13)' in runbook

    live_runbook = (
        Path(__file__).parents[1] / "ops/LIVE_FLOW_RUNBOOK.md"
    ).read_text()
    normalized_live_runbook = " ".join(live_runbook.split())
    assert "| `chainsnap-ops-wt` | `com.mastermind.chainsnapshots` |" in live_runbook
    assert (
        "`liveflow-ops-wt` never owns or carries chain state"
        in normalized_live_runbook
    )
    assert (
        "exact `data/chain_snapshots` symlink to the physical authority"
        in live_runbook
    )


def test_chain_snapshot_runtime_ignore_covers_directory_and_deploy_symlink():
    ignore = (Path(__file__).parents[1] / ".gitignore").read_text().splitlines()
    assert "data/chain_snapshots" in ignore
    assert "data/chain_snapshots/" not in ignore


def _leave_close_decision_only(
    monkeypatch,
    tmp_path: Path,
    *,
    stable_repo_root: bool = False,
    session: str = SESSION,
    bucket: str = "16:00",
) -> Path:
    if stable_repo_root:
        from scripts import chain_snapshot_poller as poller

        monkeypatch.setattr(poller, "REPO_ROOT", tmp_path)
        root = poller._receipt_root_path()
    else:
        root = _patch_receipt_root(monkeypatch, tmp_path)
    calls = 0
    close_hour_utc = 18 if bucket == "13:00" else 20
    session_day = date.fromisoformat(session)

    def clock():
        nonlocal calls
        calls += 1
        values = {
            1: datetime.combine(
                session_day, datetime.min.time(), tzinfo=timezone.utc,
            ).replace(hour=close_hour_utc, second=20),
            2: datetime.combine(
                session_day, datetime.min.time(), tzinfo=timezone.utc,
            ).replace(hour=close_hour_utc, second=40),
            3: datetime.combine(
                session_day, datetime.min.time(), tzinfo=timezone.utc,
            ).replace(hour=close_hour_utc, minute=5),
        }
        if calls == 4:
            raise RuntimeError("crash after close decision")
        return values[calls]

    def sweep(roots, *_args):
        summary = _sweep_summary(roots)
        summary["bucket"] = bucket
        vendor_at = datetime.combine(
            session_day, datetime.min.time(), tzinfo=timezone.utc,
        ).replace(hour=close_hour_utc)
        for result in summary["_root_results"]:
            result["first_vendor_min_at"] = bucket_completion.utc_microseconds(
                vendor_at,
            )
            result["first_vendor_max_at"] = bucket_completion.utc_microseconds(
                vendor_at,
            )
        return summary

    with pytest.raises(RuntimeError, match="crash after close decision"):
        run_managed_sweep(
            ["SPY"], session, bucket, {"cadence_min": 15},
            now=datetime.combine(
                session_day, datetime.min.time(), tzinfo=ET,
            ).replace(
                hour=int(bucket.split(":")[0]),
                minute=int(bucket.split(":")[1]),
                second=20,
            ),
            now_fn=clock,
            sweep_fn=sweep,
        )
    assert [row["kind"] for row in _records(root, session)] == ["intent", "decision"]
    return root


def test_entrypoint_drains_close_decision_after_rth_without_theta(
    tmp_path, monkeypatch,
):
    from collectors import thetadata as td
    from scripts import build_options_structure_intraday as publisher
    from scripts import chain_snapshot_poller as poller

    root = _leave_close_decision_only(monkeypatch, tmp_path)
    now = datetime(2026, 7, 2, 16, 6, tzinfo=ET)
    published: list[dict] = []
    monkeypatch.setattr(poller, "_receipt_root_path", lambda: root)
    monkeypatch.setattr(poller, "_now_et", lambda: now)
    monkeypatch.setattr(
        poller,
        "_cfg",
        lambda: {
            "cadence_min": 15,
            "options_structure_r2": {
                "enabled": True,
                "activation_session": SESSION,
                "timeout_sec": 120,
            },
        },
    )
    acknowledged: set[str] = set()

    def publish(packet, **_kwargs):
        published.append(packet)
        acknowledged.add(packet["availability"]["receipt_id"])

    monkeypatch.setattr(poller, "_run_options_structure_publisher", publish)
    monkeypatch.setattr(
        publisher,
        "publication_acknowledged",
        lambda _out_dir, packet: packet["availability"]["receipt_id"] in acknowledged,
    )
    _patch_memory_publication_cursor(monkeypatch, publisher)
    monkeypatch.setattr(poller, "_write_meta", lambda *_args: None)
    monkeypatch.setattr(td, "reachable", lambda **_kwargs: pytest.fail("Theta forbidden"))
    assert poller.main(["--once", "--roots", "SPY"]) == 0
    records = _records(root)
    assert [row["kind"] for row in records] == ["intent", "decision", "availability"]
    assert records[-1]["availability_at"] == "2026-07-02T20:06:00.000000Z"
    assert len(published) == 1
    assert bucket_completion.validate_completion_packet(published[0]).status == "complete"


def test_entrypoint_drains_early_close_decision_into_acknowledged_publication(
    tmp_path, monkeypatch,
):
    from collectors import thetadata as td
    from scripts import build_options_structure_intraday as publisher
    from scripts import chain_snapshot_poller as poller

    session = "2026-11-27"
    root = _leave_close_decision_only(
        monkeypatch,
        tmp_path,
        session=session,
        bucket="13:00",
    )
    acknowledged: set[str] = set()
    published: list[dict] = []

    def publish(packet, **_kwargs):
        published.append(packet)
        acknowledged.add(packet["availability"]["receipt_id"])

    monkeypatch.setattr(poller, "_receipt_root_path", lambda: root)
    monkeypatch.setattr(
        poller,
        "_now_et",
        lambda: datetime(2026, 11, 27, 13, 6, tzinfo=ET),
    )
    monkeypatch.setattr(
        poller,
        "_cfg",
        lambda: {
            "cadence_min": 15,
            "options_structure_r2": {
                "enabled": True,
                "activation_session": session,
                "timeout_sec": 120,
            },
        },
    )
    monkeypatch.setattr(poller, "_run_options_structure_publisher", publish)
    monkeypatch.setattr(
        publisher,
        "publication_acknowledged",
        lambda _out_dir, packet: packet["availability"]["receipt_id"] in acknowledged,
    )
    _patch_memory_publication_cursor(monkeypatch, publisher)
    monkeypatch.setattr(poller, "_write_meta", lambda *_args: None)
    monkeypatch.setattr(td, "reachable", lambda **_kwargs: pytest.fail("Theta forbidden"))

    assert poller.main(["--rth-only", "--roots", "SPY"]) == 0
    assert [row["kind"] for row in _records(root, session)] == [
        "intent", "decision", "availability",
    ]
    assert len(published) == 1


def test_close_tail_publication_failure_is_retryable_and_exits_nonzero(
    tmp_path, monkeypatch,
):
    from collectors import thetadata as td
    from scripts import build_options_structure_intraday as publisher
    from scripts import chain_snapshot_poller as poller

    root = _leave_close_decision_only(monkeypatch, tmp_path)
    attempts = 0

    def fail(_packet, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("R2 unavailable")

    monkeypatch.setattr(poller, "_receipt_root_path", lambda: root)
    monkeypatch.setattr(
        poller, "_now_et", lambda: datetime(2026, 7, 2, 16, 6, tzinfo=ET),
    )
    monkeypatch.setattr(
        poller,
        "_cfg",
        lambda: {
            "cadence_min": 15,
            "options_structure_r2": {
                "enabled": True,
                "activation_session": SESSION,
                "timeout_sec": 120,
            },
        },
    )
    monkeypatch.setattr(poller, "_run_options_structure_publisher", fail)
    monkeypatch.setattr(
        publisher, "publication_acknowledged", lambda _out_dir, _packet: False,
    )
    monkeypatch.setattr(poller, "_write_meta", lambda *_args: None)
    monkeypatch.setattr(td, "reachable", lambda **_kwargs: pytest.fail("Theta forbidden"))

    assert poller.main(["--once", "--roots", "SPY"]) == 1
    assert attempts == 2
    assert [row["kind"] for row in _records(root)] == [
        "intent", "decision", "availability",
    ]


def test_entrypoint_real_root_decision_drain_precedes_malformed_yaml(
    tmp_path, monkeypatch,
):
    from collectors import thetadata as td
    from scripts import chain_snapshot_poller as poller

    root = _leave_close_decision_only(
        monkeypatch, tmp_path, stable_repo_root=True,
    )
    assert root == tmp_path / "data" / "chain_snapshots" / "_bucket_receipts"
    monkeypatch.setattr(
        poller, "_now_et", lambda: datetime(2026, 7, 2, 16, 6, tzinfo=ET),
    )
    monkeypatch.setattr(
        poller.config,
        "load",
        lambda: (_ for _ in ()).throw(RuntimeError("malformed yaml")),
    )
    monkeypatch.setattr(td, "reachable", lambda **_kwargs: pytest.fail("Theta forbidden"))
    assert poller.main(["--once", "--roots", "SPY"]) == 1
    assert [row["kind"] for row in _records(root)] == [
        "intent", "decision", "availability",
    ]
    assert (tmp_path / "data" / "chain_snapshots" / "_meta.json").is_file()


def test_entrypoint_terminalizes_close_intent_after_source_grace_without_theta(
    tmp_path, monkeypatch,
):
    from collectors import thetadata as td
    from scripts import chain_snapshot_poller as poller

    root = _patch_receipt_root(monkeypatch, tmp_path)

    def partial(roots, *_args):
        summary = _sweep_summary(roots, failed={"SPY"})
        summary["bucket"] = "16:00"
        return summary

    run_managed_sweep(
        ["SPY"], SESSION, "16:00", {"cadence_min": 15},
        now=datetime(2026, 7, 2, 16, 0, 20, tzinfo=ET),
        now_fn=lambda: datetime(
            2026, 7, 2, 20, 0, 30, tzinfo=timezone.utc,
        ),
        sweep_fn=partial,
    )
    monkeypatch.setattr(poller, "_receipt_root_path", lambda: root)
    monkeypatch.setattr(
        poller, "_now_et", lambda: datetime(2026, 7, 2, 16, 6, tzinfo=ET),
    )
    monkeypatch.setattr(poller, "_cfg", lambda: {"cadence_min": 15})
    monkeypatch.setattr(poller, "_write_meta", lambda *_args: None)
    monkeypatch.setattr(td, "reachable", lambda **_kwargs: pytest.fail("Theta forbidden"))
    assert poller.main(["--once", "--roots", "SPY"]) == 0
    records = _records(root)
    assert [row["kind"] for row in records] == ["intent", "incomplete"]
    assert records[-1]["reason"] == "bucket_window_elapsed"


def test_entrypoint_terminalizes_early_close_intent_without_stranding_tail(
    tmp_path, monkeypatch,
):
    from collectors import thetadata as td
    from scripts import chain_snapshot_poller as poller

    session = "2026-11-27"
    root = _patch_receipt_root(monkeypatch, tmp_path)

    def partial(roots, *_args):
        summary = _sweep_summary(roots, failed={"SPY"})
        summary["bucket"] = "13:00"
        return summary

    run_managed_sweep(
        ["SPY"], session, "13:00", {"cadence_min": 15},
        now=datetime(2026, 11, 27, 13, 0, 20, tzinfo=ET),
        now_fn=lambda: datetime(
            2026, 11, 27, 18, 0, 30, tzinfo=timezone.utc,
        ),
        sweep_fn=partial,
    )
    monkeypatch.setattr(poller, "_receipt_root_path", lambda: root)
    monkeypatch.setattr(
        poller, "_now_et", lambda: datetime(2026, 11, 27, 13, 6, tzinfo=ET),
    )
    monkeypatch.setattr(poller, "_cfg", lambda: {"cadence_min": 15})
    monkeypatch.setattr(poller, "_write_meta", lambda *_args: None)
    monkeypatch.setattr(td, "reachable", lambda **_kwargs: pytest.fail("Theta forbidden"))
    assert poller.main(["--rth-only", "--roots", "SPY"]) == 0
    records = _records(root, session)
    assert [row["kind"] for row in records] == ["intent", "incomplete"]


@pytest.mark.parametrize(
    ("clocks", "expected"),
    [
        (
            [
                datetime(2026, 7, 2, 9, 44, 50, tzinfo=ET),
                datetime(2026, 7, 2, 9, 44, 50, tzinfo=ET),
                datetime(2026, 7, 2, 9, 45, 0, 100, tzinfo=ET),
                datetime(2026, 7, 2, 9, 45, 0, 200, tzinfo=ET),
                datetime(2026, 7, 2, 16, 1, tzinfo=ET),
            ],
            ["09:30", "09:45"],
        ),
        (
            [
                datetime(2026, 7, 2, 15, 59, 50, tzinfo=ET),
                datetime(2026, 7, 2, 15, 59, 50, tzinfo=ET),
                datetime(2026, 7, 2, 16, 0, 0, 100, tzinfo=ET),
                datetime(2026, 7, 2, 16, 0, 0, 200, tzinfo=ET),
                datetime(2026, 7, 2, 16, 10, tzinfo=ET),
            ],
            ["15:45", "16:00"],
        ),
        (
            [
                datetime(2026, 11, 27, 12, 59, 50, tzinfo=ET),
                datetime(2026, 11, 27, 12, 59, 50, tzinfo=ET),
                datetime(2026, 11, 27, 13, 0, 0, 100, tzinfo=ET),
                datetime(2026, 11, 27, 13, 0, 0, 200, tzinfo=ET),
                datetime(2026, 11, 27, 13, 10, tzinfo=ET),
            ],
            ["12:45", "13:00"],
        ),
    ],
)
def test_entrypoint_immediately_iterates_advanced_grid_and_collects_close(
    tmp_path, monkeypatch, clocks, expected,
):
    from scripts import chain_snapshot_poller as poller

    clock_iter = iter(clocks)
    seen = []
    monkeypatch.setattr(poller, "_receipt_root_path", lambda: tmp_path / "missing")
    monkeypatch.setattr(poller, "_now_et", lambda: next(clock_iter))
    monkeypatch.setattr(poller, "_cfg", lambda: {"cadence_min": 15})
    monkeypatch.setattr(poller, "_write_meta", lambda *_args: None)
    monkeypatch.setattr(
        poller.time, "sleep", lambda *_args: pytest.fail("advanced grid must not sleep"),
    )

    def managed(_roots, _session, bucket, _cfg, **_kwargs):
        seen.append(bucket)
        summary = _sweep_summary(["SPY"])
        summary["bucket"] = bucket
        summary["receipt_state"] = "complete"
        return summary

    monkeypatch.setattr(poller, "run_managed_sweep", managed)
    assert poller.main(["--roots", "SPY"]) == 0
    assert seen == expected


def test_once_returns_nonzero_for_intent_pending(tmp_path, monkeypatch):
    from scripts import chain_snapshot_poller as poller

    now = datetime(2026, 7, 2, 9, 36, tzinfo=ET)
    monkeypatch.setattr(poller, "_receipt_root_path", lambda: tmp_path / "missing")
    monkeypatch.setattr(poller, "_now_et", lambda: now)
    monkeypatch.setattr(poller, "_cfg", lambda: {"cadence_min": 15})
    monkeypatch.setattr(poller, "_write_meta", lambda *_args: None)
    summary = _sweep_summary(["SPY"], failed={"SPY"})
    summary["receipt_state"] = "intent_pending"
    monkeypatch.setattr(poller, "run_managed_sweep", lambda *_args, **_kwargs: summary)
    assert poller.main(["--once", "--roots", "SPY"]) == 1


def test_config_loader_error_blocks_new_receipt_source_and_theta(tmp_path, monkeypatch):
    from collectors import thetadata as td
    from scripts import chain_snapshot_poller as poller

    absent = tmp_path / "absent"
    monkeypatch.setattr(poller, "_receipt_root_path", lambda: absent)
    monkeypatch.setattr(
        poller, "_cfg", lambda: (_ for _ in ()).throw(RuntimeError("bad yaml")),
    )
    monkeypatch.setattr(
        poller, "_receipt_root", lambda: pytest.fail("bad config cannot create receipt"),
    )
    monkeypatch.setattr(td, "reachable", lambda **_kwargs: pytest.fail("Theta forbidden"))
    assert poller.main(["--once", "--roots", "SPY"]) == 1
    assert not absent.exists()


@pytest.mark.parametrize("invalid_top", [True, "128", 12.5, -1])
def test_invalid_universe_config_blocks_intent_and_source(
    tmp_path, monkeypatch, invalid_top,
):
    from collectors import thetadata as td
    from scripts import chain_snapshot_poller as poller

    now = datetime(2026, 7, 2, 9, 36, tzinfo=ET)
    monkeypatch.setattr(poller, "_receipt_root_path", lambda: tmp_path / "missing")
    monkeypatch.setattr(poller, "_now_et", lambda: now)
    monkeypatch.setattr(
        poller, "_cfg", lambda: {"cadence_min": 15, "top_names": invalid_top},
    )
    monkeypatch.setattr(
        poller, "_receipt_root", lambda: pytest.fail("invalid universe cannot create intent"),
    )
    monkeypatch.setattr(td, "reachable", lambda **_kwargs: pytest.fail("Theta forbidden"))
    assert poller.main(["--once"]) == 1


def test_invalid_anchor_config_blocks_intent_and_source(tmp_path, monkeypatch):
    from scripts import chain_snapshot_poller as poller

    monkeypatch.setattr(poller, "_receipt_root_path", lambda: tmp_path / "missing")
    monkeypatch.setattr(
        poller, "_now_et", lambda: datetime(2026, 7, 2, 9, 36, tzinfo=ET),
    )
    monkeypatch.setattr(
        poller,
        "_cfg",
        lambda: {"cadence_min": 15, "etf_anchors": [".."], "top_names": 0},
    )
    monkeypatch.setattr(
        poller, "_receipt_root", lambda: pytest.fail("invalid anchors cannot create intent"),
    )
    assert poller.main(["--once"]) == 1


@pytest.mark.parametrize(
    "outside",
    [
        datetime(2026, 7, 2, 16, 1, tzinfo=ET),
        datetime(2026, 7, 3, 10, 0, tzinfo=ET),
        datetime(2026, 11, 27, 13, 1, tzinfo=ET),
    ],
)
def test_once_outside_real_live_bucket_never_calls_theta_or_receipt(
    tmp_path, monkeypatch, outside,
):
    from collectors import thetadata as td
    from scripts import chain_snapshot_poller as poller

    monkeypatch.setattr(
        poller,
        "_cfg",
        lambda: {
            "cadence_min": 15,
            "options_structure_r2": {
                "enabled": True,
                "activation_session": SESSION,
                "timeout_sec": 120,
            },
        },
    )
    monkeypatch.setattr(poller, "_now_et", lambda: outside)
    absent_receipts = tmp_path / "absent-receipts"
    monkeypatch.setattr(poller, "_receipt_root_path", lambda: absent_receipts)
    monkeypatch.setattr(td, "reachable", lambda **_kwargs: pytest.fail("Theta probe forbidden"))
    monkeypatch.setattr(
        poller, "_receipt_root", lambda: pytest.fail("receipt creation forbidden"),
    )
    monkeypatch.setattr(
        poller,
        "_run_options_structure_publisher",
        lambda *_args, **_kwargs: pytest.fail("closed session cannot publish"),
    )
    assert poller.main(["--once", "--roots", "SPY"]) == 0
    assert not absent_receipts.exists()


def test_main_intent_fsync_failure_precedes_theta_probe(tmp_path, monkeypatch):
    from collectors import thetadata as td
    from scripts import chain_snapshot_poller as poller

    receipt_root = tmp_path / "receipts"
    receipt_root.mkdir()
    (receipt_root / ".writer.lock").write_bytes(b"")
    monkeypatch.setattr(poller, "_cfg", lambda: {"cadence_min": 15})
    monkeypatch.setattr(
        poller, "_now_et", lambda: datetime(2026, 7, 2, 9, 36, tzinfo=ET),
    )
    monkeypatch.setattr(poller, "_receipt_root", lambda: receipt_root)
    theta_calls = 0

    def reachable(**_kwargs):
        nonlocal theta_calls
        theta_calls += 1
        return True

    real_fsync = bucket_completion.os.fsync
    fail_once = True

    def fail_intent(fd: int) -> None:
        nonlocal fail_once
        if fail_once and not stat.S_ISDIR(os.fstat(fd).st_mode):
            fail_once = False
            raise OSError("intent durability unavailable")
        real_fsync(fd)

    monkeypatch.setattr(td, "reachable", reachable)
    monkeypatch.setattr(bucket_completion.os, "fsync", fail_intent)
    assert poller.main(["--once", "--roots", "SPY"]) == 1
    assert theta_calls == 0
