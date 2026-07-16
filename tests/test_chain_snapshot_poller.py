"""tests/test_chain_snapshot_poller.py — hermetic tests for the U-CHAIN lane.

All tests are network-free: the terminal is mocked via monkeypatching
(collectors.thetadata._get_csv), same pattern as tests/test_thetadata.py.
No writes outside tmp_path (MM_DATA_GUARD).

Test coverage:
  1. Collector: snapshot_greeks / snapshot_open_interest parse the verbatim
     v3 snapshot CSV headers (measured 2026-07-16) into normalized frames —
     snapshot_ts from response timestamps, right C/P, dollar-float strikes,
     full-row API dedup, INERT None on terminal failure.
  2. Poller: join of first+second order frames on the contract key (no row
     multiplication; missing second-order degrades to NaN columns).
  3. Poller: sweep-bucket derivation (ET wall time floored to cadence grid).
  4. Poller: universe cap logic (22 anchors + top_names, anchors first).
  5. Poller: per-day parquet append dedup on (contract key, snapshot_bucket);
     unreadable existing frame → quarantine-rename (bytes preserved), never
     overwritten; quarantine-rename failure → raise, never write.
  6. Poller: RTH gate 09:35-16:00 ET + pre-RTH wait (injected clock).
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from scripts.chain_snapshot_poller import (
    CONTRACT_KEY,
    SECOND_ORDER_JOIN_COLS,
    _pre_rth_wait_sec,
    _resolve_universe,
    _within_rth,
    append_day_parquet,
    derive_bucket,
    join_orders,
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
        "implied_vol": [0.1036, 0.1101],
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

    def test_invalid_cadence_clamped(self):
        # cadence 0 must not divide-by-zero; clamps to 1-minute grid
        assert derive_bucket(datetime(hour=9, minute=37, **WED), 0) == "09:37"


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
        assert (added, total, q) == (2, 2, None)
        # Same bucket re-run → dedup on (contract key, snapshot_bucket): no-op
        added, total, q = append_day_parquet(p, _bucket_frame("09:30", [750.0, 766.0]))
        assert (added, total, q) == (0, 2, None)

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
        assert (added, total, q) == (0, 0, None)
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
        assert q is not None and q.startswith("2026-07-16.corrupt-")
        assert (tmp_path / q).read_bytes() == corrupt
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
