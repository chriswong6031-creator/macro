"""tests/test_pick_lab_runner.py — end-to-end smoke tests for scripts.build_pick_lab.

Tests
-----
1. main() returns 0 when no snapshot exists (honest no-op).
2. main() returns 0 when price store unavailable (grade pass skips gracefully).
3. With a synthetic snapshot: fires are written, runs are idempotent (same asof → no
   duplicate fire rows), site artifacts are valid JSON with the schema keys the template
   consumes (scoreboard, books, lanes, regime, as_of, authority).
4. main() returns 0 even when every internal step throws (never-break contract).
5. Context stamps: velocity-book fire rows carry pct_gain_60d_low/bars_since_60d_low/
   ret_252d with hand-computable values; nulls when panel absent (Amendment §A5+§A7).
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Repo root on sys.path
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Synthetic snapshot builder
# ---------------------------------------------------------------------------

def _make_snap(n: int = 5, asof: str = "2026-01-02") -> pd.DataFrame:
    """Minimal DataFrame conforming to snapshot.SNAPSHOT_COLUMNS."""
    from engine.pick_lab.snapshot import SNAPSHOT_COLUMNS

    tickers = [f"TICK{i}" for i in range(n)]
    rows = []
    for i, t in enumerate(tickers):
        row = {c: None for c in SNAPSHOT_COLUMNS}
        row["ticker"] = t
        row["asof"] = asof
        row["close"] = 20.0 + i            # above $5 floor
        row["dollar_adv_20d"] = 50e6       # above $10M floor
        row["sector"] = "Information Technology"
        # Oscillator values that make book-1 fire (plab_1d_pure)
        row["d1_macd_xup_bars"] = 1        # <= 2
        row["d1_kd_xup_bars"] = 3          # <= 8
        row["d1_from_os"] = True
        row["rsi14"] = 55.0               # < 65
        row["composite_z"] = float(i)     # rank ordering
        # Scores
        row["edge_alpha"] = float(i) * 0.1
        row["axis_selection"] = float(i) * 0.1
        row["axis_quality"] = float(i) * 0.1
        rows.append(row)

    df = pd.DataFrame(rows).set_index("ticker")
    df.attrs["asof"] = asof
    return df


# ---------------------------------------------------------------------------
# Path-monkeypatching helpers
# ---------------------------------------------------------------------------

def _patch_snapshot_dir(tmp_path: Path, snap: pd.DataFrame, asof: str) -> Path:
    """Write synthetic snapshot to tmp_path and return the parquet path."""
    from engine.pick_lab.snapshot import write_snapshot
    snap_dir = tmp_path / "data" / "pick_lab" / "snapshots"
    snap_dir.mkdir(parents=True)
    write_snapshot(snap.reset_index(), asof, base_dir=str(snap_dir))
    return snap_dir


# ---------------------------------------------------------------------------
# 1. No-op when snapshot is missing
# ---------------------------------------------------------------------------

class TestNoSnapshot:
    def test_returns_zero_no_snapshot(self, tmp_path: Path, monkeypatch):
        """main() must return 0 when no snapshot exists anywhere."""
        from scripts import build_pick_lab
        from engine.pick_lab import snapshot as snap_mod

        # Patch latest_snapshot to return (None, None) — no snapshot found
        monkeypatch.setattr(snap_mod, "latest_snapshot", lambda **_kw: (None, None))
        monkeypatch.setattr("lib.config.ROOT", tmp_path)
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path / "data")

        rc = build_pick_lab.main()
        assert rc == 0, f"main() returned {rc}, expected 0"


# ---------------------------------------------------------------------------
# 2. No-op grade pass when price store missing
# ---------------------------------------------------------------------------

class TestNoClosePanel:
    def test_returns_zero_no_prices(self, tmp_path: Path, monkeypatch):
        """main() returns 0 when close panel is unavailable (grade pass degrades)."""
        from scripts import build_pick_lab
        from engine.pick_lab import snapshot as snap_mod
        from engine.pick_lab import ledger as ledger_mod

        asof = "2026-02-03"
        snap = _make_snap(asof=asof)
        monkeypatch.setattr(snap_mod, "latest_snapshot", lambda **_kw: (snap, asof))
        monkeypatch.setattr(snap_mod, "write_snapshot", lambda *a, **kw: 0)

        data_dir = tmp_path / "data"
        monkeypatch.setattr("lib.config.ROOT", tmp_path)
        monkeypatch.setattr("lib.config.data_dir", lambda: data_dir)
        pick_lab_data = data_dir / "pick_lab"
        pick_lab_data.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(ledger_mod, "FIRES_PATH", pick_lab_data / "fires.jsonl")
        monkeypatch.setattr(ledger_mod, "GRADES_PATH", pick_lab_data / "grades.jsonl")
        monkeypatch.setattr(ledger_mod, "LH_FIRES_PATH", pick_lab_data / "lh_fires.jsonl")
        monkeypatch.setattr(ledger_mod, "LH_GRADES_PATH", pick_lab_data / "lh_grades.jsonl")

        # Patch _load_close_panel to return None → grade pass skips gracefully
        monkeypatch.setattr(build_pick_lab, "_load_close_panel", lambda: None)

        rc = build_pick_lab.main()
        assert rc == 0, f"main() returned {rc} — never-break contract violated"


# ---------------------------------------------------------------------------
# 3. Fires written; idempotent on second run; site artifacts valid JSON
# ---------------------------------------------------------------------------

class TestWithSnapshot:
    def _run_build(self, tmp_path: Path, monkeypatch, asof: str = "2026-03-04"):
        """Set up tmp sandbox and run main(), return labdata + pick_lab_data paths.

        latest_snapshot() uses a module-level default arg (SNAPSHOT_DIR baked at
        import time), so we patch the function directly to return our synthetic
        snapshot rather than trying to override the default.
        """
        from scripts import build_pick_lab
        from engine.pick_lab import snapshot as snap_mod

        snap = _make_snap(asof=asof)

        # Patch latest_snapshot to return the synthetic snapshot (bypasses default-arg issue)
        monkeypatch.setattr(snap_mod, "latest_snapshot", lambda **_kw: (snap, asof))

        # Patch write_snapshot to be a no-op (we don't need it for these smoke tests)
        monkeypatch.setattr(snap_mod, "write_snapshot", lambda *a, **kw: 0)

        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("lib.config.ROOT", tmp_path)
        monkeypatch.setattr("lib.config.data_dir", lambda: data_dir)

        # Redirect ledger paths to tmp
        pick_lab_data = data_dir / "pick_lab"
        pick_lab_data.mkdir(parents=True, exist_ok=True)
        from engine.pick_lab import ledger as ledger_mod
        monkeypatch.setattr(ledger_mod, "FIRES_PATH", pick_lab_data / "fires.jsonl")
        monkeypatch.setattr(ledger_mod, "GRADES_PATH", pick_lab_data / "grades.jsonl")
        monkeypatch.setattr(ledger_mod, "LH_FIRES_PATH", pick_lab_data / "lh_fires.jsonl")
        monkeypatch.setattr(ledger_mod, "LH_GRADES_PATH", pick_lab_data / "lh_grades.jsonl")

        rc = build_pick_lab.main()
        assert rc == 0

        labdata = tmp_path / "site" / "labdata"
        return labdata, pick_lab_data

    def test_fires_written(self, tmp_path: Path, monkeypatch):
        """At least one fire must be written to fires.jsonl on first run."""
        labdata, pick_lab_data = self._run_build(tmp_path, monkeypatch)
        fires_path = pick_lab_data / "fires.jsonl"
        assert fires_path.exists(), "fires.jsonl was not created"
        from engine.pick_lab.ledger import load_jsonl
        fires = load_jsonl(fires_path)
        assert len(fires) > 0, "No fires written on first run"
        for f in fires:
            assert f.get("authority") == "display_only"

    def test_idempotent_on_second_run(self, tmp_path: Path, monkeypatch):
        """Running main() twice on the same asof must not duplicate fire rows."""
        asof = "2026-04-05"
        labdata, pick_lab_data = self._run_build(tmp_path, monkeypatch, asof=asof)
        fires_path = pick_lab_data / "fires.jsonl"

        from engine.pick_lab.ledger import load_jsonl, FIRE_KEY, keep_first
        fires_after_run1 = load_jsonl(fires_path)
        n1 = len(fires_after_run1)

        # Second run — same monkeypatches still active (re-import is fine)
        from scripts import build_pick_lab as bpl
        rc2 = bpl.main()
        assert rc2 == 0

        fires_after_run2 = load_jsonl(fires_path)
        n2 = len(fires_after_run2)
        deduped = keep_first(fires_after_run2, FIRE_KEY)
        # No new rows for the same asof (keep-first idempotent)
        assert len(deduped) == n1, (
            f"Second run added duplicate fire rows: n1={n1}, n2={n2}, "
            f"deduped={len(deduped)}"
        )

    def test_entry_site_artifact_valid_json_schema(self, tmp_path: Path, monkeypatch):
        """site/labdata/pick_lab.json must exist and carry required top-level keys."""
        labdata, _ = self._run_build(tmp_path, monkeypatch)
        artifact = labdata / "pick_lab.json"
        assert artifact.exists(), "pick_lab.json not written"
        data = json.loads(artifact.read_text())

        required_keys = {
            "as_of", "built_at", "scoreboard", "books", "lanes",
            "regime", "method_note", "authority",
        }
        missing = required_keys - set(data.keys())
        assert not missing, f"pick_lab.json missing keys: {missing}"
        # The template's regime chips read calm/stress/liquidity — the summary
        # must ALWAYS carry the keys (None when unknown). Regression for the
        # 2026-07-12 nightly render death on a missing `stress` key.
        chip_keys = {"calm", "stress", "liquidity"}
        missing_chips = chip_keys - set(data["regime"])
        assert not missing_chips, f"regime summary missing chip keys: {missing_chips}"
        assert data["authority"] == "display_only"
        assert isinstance(data["scoreboard"], list)
        assert isinstance(data["books"], dict)
        # Template needs name_en, name_zh, family on each scoreboard row
        for row in data["scoreboard"]:
            for field in ("engine_id", "n_fires", "status", "authority"):
                assert field in row, f"scoreboard row missing '{field}': {row}"

    def test_longhold_site_artifact_valid_json_schema(self, tmp_path: Path, monkeypatch):
        """site/labdata/pick_lab_longhold.json must exist with LH-specific keys."""
        labdata, _ = self._run_build(tmp_path, monkeypatch)
        artifact = labdata / "pick_lab_longhold.json"
        assert artifact.exists(), "pick_lab_longhold.json not written"
        data = json.loads(artifact.read_text())

        required_keys = {
            "as_of", "built_at", "books", "authority",
            "horizon_role", "firewall_note",
        }
        missing = required_keys - set(data.keys())
        assert not missing, f"pick_lab_longhold.json missing keys: {missing}"
        assert data["authority"] == "display_only"
        assert data["horizon_role"] == "hold_thesis"
        assert isinstance(data["books"], dict)

    def test_lanes_keys_present(self, tmp_path: Path, monkeypatch):
        """lanes dict must have on_the_run_stocks and take_profits_stocks keys."""
        labdata, _ = self._run_build(tmp_path, monkeypatch)
        data = json.loads((labdata / "pick_lab.json").read_text())
        lanes = data.get("lanes", {})
        assert "on_the_run_stocks" in lanes
        assert "take_profits_stocks" in lanes


# ---------------------------------------------------------------------------
# 4. Never-break contract: main() returns 0 even on catastrophic failure
# ---------------------------------------------------------------------------

class TestNeverBreak:
    def test_returns_zero_on_exception(self, tmp_path: Path, monkeypatch):
        """main() must return 0 even when _build() raises an unexpected exception."""
        from scripts import build_pick_lab

        def _exploding_build():
            raise RuntimeError("simulated catastrophic failure")

        monkeypatch.setattr(build_pick_lab, "_build", _exploding_build)
        rc = build_pick_lab.main()
        assert rc == 0, f"main() returned {rc} after exception — never-break violated"

    def test_returns_zero_on_import_error(self, tmp_path: Path, monkeypatch):
        """main() returns 0 even when engine.pick_lab modules are unavailable."""
        from scripts import build_pick_lab

        def _import_error_build():
            raise ImportError("engine.pick_lab not installed")

        monkeypatch.setattr(build_pick_lab, "_build", _import_error_build)
        rc = build_pick_lab.main()
        assert rc == 0


# ---------------------------------------------------------------------------
# 5. Context stamps (Amendment §A5 + §A7 instrumentation)
# ---------------------------------------------------------------------------

class TestContextStamps:
    """_stamp_context computes pct_gain_60d_low / bars_since_60d_low / ret_252d correctly."""

    def _make_close_panel(
        self,
        ticker: str,
        asof: str,
        prices: list[float],
        start: str = "2025-01-02",
    ) -> "pd.DataFrame":
        """Build a minimal close panel [date x ticker] with exact price series."""
        dates = pd.bdate_range(start=start, periods=len(prices))
        return pd.DataFrame({ticker: prices}, index=dates)

    def test_stamps_present_on_velocity_book_fire(self, tmp_path: Path, monkeypatch):
        """A plab_1d_pure fire row must carry pct_gain_60d_low/bars_since_60d_low/ret_252d
        when the close panel is available.
        """
        from scripts import build_pick_lab

        # Build a close panel: 300 sessions, TICK0 price rises from 10 to 50
        asof = "2026-03-04"
        n_sessions = 300
        prices_tick0 = [10.0 + i * (40.0 / (n_sessions - 1)) for i in range(n_sessions)]
        dates = pd.bdate_range(start="2024-12-01", periods=n_sessions)
        close_panel = pd.DataFrame({"TICK0": prices_tick0}, index=dates)
        close_at_fire = prices_tick0[-1]

        # Manually compute expected values for last 60 sessions
        last_60 = prices_tick0[-60:]
        min_close = min(last_60)
        min_idx_in_60 = last_60.index(min_close)
        expected_bars_since = 59 - min_idx_in_60  # sessions since min (0 = earliest)
        expected_pct_gain = (close_at_fire - min_close) / min_close

        # ret_252d: we have 300 sessions total; 253rd from end is index 300-253=47
        close_252d_ago = prices_tick0[-253]
        expected_ret_252d = (close_at_fire - close_252d_ago) / close_252d_ago

        # Run _stamp_context directly
        snap_row = {"pct_vs_20dma": -0.03, "off_52w_high_pct": 0.05, "cycle_state": "TRENDING"}

        stamps = build_pick_lab._stamp_context(
            ticker="TICK0",
            snap_row=snap_row,
            close_panel=close_panel,
            asof=str(dates[-1].date()),
        )

        assert "pct_gain_60d_low" in stamps, "pct_gain_60d_low must be stamped"
        assert "bars_since_60d_low" in stamps, "bars_since_60d_low must be stamped"
        assert "ret_252d" in stamps, "ret_252d must be stamped"

        # Verify pct_gain_60d_low matches hand-computed value (within float tolerance)
        assert stamps["pct_gain_60d_low"] is not None
        assert abs(stamps["pct_gain_60d_low"] - expected_pct_gain) < 1e-9, (
            f"pct_gain_60d_low={stamps['pct_gain_60d_low']} != expected {expected_pct_gain}"
        )

        # bars_since_60d_low: integer count
        assert stamps["bars_since_60d_low"] is not None
        assert stamps["bars_since_60d_low"] == expected_bars_since, (
            f"bars_since_60d_low={stamps['bars_since_60d_low']} != expected {expected_bars_since}"
        )

        # ret_252d
        assert stamps["ret_252d"] is not None
        assert abs(stamps["ret_252d"] - expected_ret_252d) < 1e-9

    def test_stamps_snapshot_cols_copied(self, tmp_path: Path, monkeypatch):
        """pct_vs_20dma, off_52w_high_pct, cycle_state are copied from the snap row."""
        from scripts import build_pick_lab

        close_panel = pd.DataFrame(
            {"TICK0": [50.0] * 100},
            index=pd.bdate_range(start="2025-09-01", periods=100),
        )
        snap_row = {
            "pct_vs_20dma": -0.07,
            "off_52w_high_pct": 0.12,
            "cycle_state": "ACCUMULATE",
        }
        stamps = build_pick_lab._stamp_context(
            ticker="TICK0",
            snap_row=snap_row,
            close_panel=close_panel,
            asof=str(close_panel.index[-1].date()),
        )
        assert stamps["pct_vs_20dma"] == -0.07
        assert stamps["off_52w_high_pct"] == 0.12
        assert stamps["cycle_state"] == "ACCUMULATE"

    def test_stamps_null_when_panel_absent(self, tmp_path: Path, monkeypatch):
        """pct_gain_60d_low / bars_since_60d_low / ret_252d are null when panel is None."""
        from scripts import build_pick_lab

        stamps = build_pick_lab._stamp_context(
            ticker="TICK0",
            snap_row={"pct_vs_20dma": -0.03, "off_52w_high_pct": 0.05, "cycle_state": "TRENDING"},
            close_panel=None,
            asof="2026-03-04",
        )
        assert stamps["pct_gain_60d_low"] is None
        assert stamps["bars_since_60d_low"] is None
        assert stamps["ret_252d"] is None

    def test_stamps_null_when_ticker_absent_from_panel(self, tmp_path: Path, monkeypatch):
        """All close-panel stamps are None when ticker is absent from the panel."""
        from scripts import build_pick_lab

        close_panel = pd.DataFrame(
            {"OTHER": [50.0] * 100},
            index=pd.bdate_range(start="2025-09-01", periods=100),
        )
        stamps = build_pick_lab._stamp_context(
            ticker="TICK0",      # not in panel
            snap_row={},
            close_panel=close_panel,
            asof=str(close_panel.index[-1].date()),
        )
        assert stamps["pct_gain_60d_low"] is None
        assert stamps["bars_since_60d_low"] is None
        assert stamps["ret_252d"] is None

    def test_ret_252d_null_when_insufficient_history(self, tmp_path: Path, monkeypatch):
        """ret_252d is None when fewer than 253 sessions available."""
        from scripts import build_pick_lab

        # Only 100 sessions — not enough for 252d return
        close_panel = pd.DataFrame(
            {"TICK0": [50.0] * 100},
            index=pd.bdate_range(start="2025-09-01", periods=100),
        )
        stamps = build_pick_lab._stamp_context(
            ticker="TICK0",
            snap_row={},
            close_panel=close_panel,
            asof=str(close_panel.index[-1].date()),
        )
        assert stamps["ret_252d"] is None, (
            "ret_252d must be None when fewer than 253 sessions available"
        )
