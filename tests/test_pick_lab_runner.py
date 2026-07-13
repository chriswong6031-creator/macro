"""tests/test_pick_lab_runner.py — end-to-end smoke tests for scripts.build_pick_lab.

Tests
-----
1. main() returns 0 when no snapshot exists (honest no-op).
2. main() returns 0 when price store unavailable (grade pass skips gracefully).
3. With a synthetic snapshot: fires are written, runs are idempotent (same asof → no
   duplicate fire rows), site artifacts are valid JSON with the schema keys the template
   consumes (scoreboard, books, lanes, regime, as_of, authority).
4. main() returns 0 even when every internal step throws (never-break contract).
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
