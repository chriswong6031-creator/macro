"""tests/test_pick_lab_cn_runner.py — end-to-end runner tests for scripts.build_china_pick_lab.

Tests
-----
1. No-op when snapshot missing: main() returns 0.
2. CN_LANE gate: main() returns 0 with no writes when CN_LANE is not 'asia'.
3. Synthetic snapshot → fires written (entry ledger with sealed_up exclusion).
4. Idempotent: second run on same asof produces no duplicate fire rows.
5. sealed_up fires excluded (skipped_unfillable counter incremented).
6. Site artifact valid JSON schema (as_of, authority, scoreboard, books, total_skipped_unfillable).
7. Render call is non-fatal (renderer exception → still returns 0).
8. Never-break: main() returns 0 even when _build() raises.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Repo root on sys.path
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Synthetic CN snapshot builder
# ---------------------------------------------------------------------------

def _make_cn_snap(n: int = 5, asof: str = "2026-01-05") -> pd.DataFrame:
    """Minimal DataFrame conforming to CN_SNAPSHOT_COLUMNS for testing."""
    from engine.pick_lab.cn_snapshot import CN_SNAPSHOT_COLUMNS

    tickers = [f"{100000 + i:06d}.SS" for i in range(n)]
    rows = []
    for i, t in enumerate(tickers):
        row = {c: None for c in CN_SNAPSHOT_COLUMNS}
        row["ticker"] = t
        row["asof"] = asof
        row["close"] = 10.0 + i           # above ¥2 floor
        row["turnover_20d"] = 50e6        # above ¥30M floor
        row["sector"] = "Information Technology"
        row["board"] = "main"
        row["is_st"] = False
        row["fillable"] = True
        row["limit_state"] = "open"
        row["chase_veto"] = False
        row["t_plus_one_risk"] = "normal"
        # Reversal data (makes cnlab_rev_pure fire)
        row["rev_deepest_quintile"] = True
        row["rev_3m_sector_rank"] = i + 1
        row["rev_sector_n"] = n
        row["rev_3m"] = -0.10 - i * 0.02
        row["rev_z"] = 2.0 + i * 0.1
        # 1D oscillators (makes cnlab_1d_pure fire)
        row["d1_macd_xup_bars"] = 1      # <= 2
        row["d1_kd_xup_bars"] = 3        # <= 8
        row["d1_from_os"] = True
        row["rsi_10"] = 40.0             # < 70
        row["d1_k"] = 20.0
        row["d1_d"] = 18.0
        row["d1_macd"] = 0.1
        row["d1_sig"] = 0.05
        row["above_ma120"] = True
        row["dd_pct_2y"] = 0.30
        row["lowvol_tercile"] = "low"
        rows.append(row)

    df = pd.DataFrame(rows).set_index("ticker")
    df.attrs["asof"] = asof
    return df


def _make_sealed_cn_snap(asof: str = "2026-01-06") -> pd.DataFrame:
    """Snapshot with ONE sealed_up ticker and one normal ticker."""
    from engine.pick_lab.cn_snapshot import CN_SNAPSHOT_COLUMNS

    rows = []
    for i, (ticker, sealed) in enumerate([("000001.SZ", True), ("000002.SZ", False)]):
        row = {c: None for c in CN_SNAPSHOT_COLUMNS}
        row["ticker"] = ticker
        row["asof"] = asof
        row["close"] = 10.0 + i
        row["turnover_20d"] = 50e6
        row["sector"] = "Financials"
        row["board"] = "main"
        row["is_st"] = False
        row["limit_state"] = "sealed_up" if sealed else "open"
        row["fillable"] = not sealed
        row["chase_veto"] = False
        row["t_plus_one_risk"] = "normal"
        row["rev_deepest_quintile"] = True
        row["rev_3m_sector_rank"] = 1
        row["rev_sector_n"] = 2
        row["rev_3m"] = -0.20
        row["rev_z"] = 3.0
        rows.append(row)

    df = pd.DataFrame(rows).set_index("ticker")
    df.attrs["asof"] = asof
    return df


# ---------------------------------------------------------------------------
# Monkey-patch helpers
# ---------------------------------------------------------------------------

def _patch_cn_env(tmp_path: Path, monkeypatch, snap: pd.DataFrame, asof: str):
    """Set up a tmp-sandboxed environment with the given CN snapshot.

    CN_PROFILE is a frozen dataclass — we cannot set its path fields directly.
    Instead we monkey-patch ledger.append_fires / load_fires / append_grades /
    load_grades to redirect to our tmp paths by capturing the 'profile' keyword
    and swapping the profile's path fields at call time via a replacement profile.
    """
    from engine.pick_lab import snapshot as snap_mod

    # Redirect latest_snapshot to return our synthetic snap
    monkeypatch.setattr(
        snap_mod, "latest_snapshot",
        lambda **kw: (snap, asof),
    )
    monkeypatch.setattr(snap_mod, "write_snapshot", lambda *a, **kw: 0)

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("lib.config.ROOT", tmp_path)
    monkeypatch.setattr("lib.config.data_dir", lambda: data_dir)

    # Create CN ledger dirs
    cn_dir = data_dir / "china_pick_lab"
    cn_dir.mkdir(parents=True, exist_ok=True)

    # Build a replacement profile that points paths into tmp_path.
    # CN_PROFILE is frozen; we construct a new MarketProfile with overridden paths.
    from engine.pick_lab.profile import MarketProfile, CN_PROFILE
    tmp_profile = MarketProfile(
        market_id=CN_PROFILE.market_id,
        fires_path=cn_dir / "fires.jsonl",
        grades_path=cn_dir / "grades.jsonl",
        lh_fires_path=cn_dir / "lh_fires.jsonl",
        lh_grades_path=cn_dir / "lh_grades.jsonl",
        snapshot_dir=data_dir / "china_pick_lab" / "snapshots",
        benchmark_ticker=CN_PROFILE.benchmark_ticker,
        benchmark_loader=None,   # no live store in tests
        fill_basis=CN_PROFILE.fill_basis,
        raw_store_path_template=str(data_dir / "china_stocks_raw" / "{ticker}.parquet"),
        sealed_up_col=CN_PROFILE.sealed_up_col,
        fillable_col=CN_PROFILE.fillable_col,
        entry_horizons=CN_PROFILE.entry_horizons,
        lh_horizons=CN_PROFILE.lh_horizons,
        primary_horizon=CN_PROFILE.primary_horizon,
        mfe_mae_sessions=CN_PROFILE.mfe_mae_sessions,
        random_ctrl_id=CN_PROFILE.random_ctrl_id,
        avoid_engine_id=CN_PROFILE.avoid_engine_id,
        refire_lockout_sessions=CN_PROFILE.refire_lockout_sessions,
        liq_close_min=CN_PROFILE.liq_close_min,
        liq_turnover_min=CN_PROFILE.liq_turnover_min,
        max_picks_default=CN_PROFILE.max_picks_default,
        extra_fire_stamp_cols=CN_PROFILE.extra_fire_stamp_cols,
        skipped_unfillable_col=CN_PROFILE.skipped_unfillable_col,
        data_gap_col=CN_PROFILE.data_gap_col,
        st_exclude_col=CN_PROFILE.st_exclude_col,
        default_ruler=CN_PROFILE.default_ruler,
        excess_label=CN_PROFILE.excess_label,
    )

    # Patch the CN_PROFILE singleton used by the runner module
    from engine.pick_lab import profile as prof_mod
    monkeypatch.setattr(prof_mod, "CN_PROFILE", tmp_profile)

    # Create site dirs
    labdata = tmp_path / "site" / "labdata"
    labdata.mkdir(parents=True, exist_ok=True)
    factordata = tmp_path / "site" / "factordata"
    factordata.mkdir(parents=True, exist_ok=True)
    chinastatedata = tmp_path / "site" / "chinastatedata"
    chinastatedata.mkdir(parents=True, exist_ok=True)

    return cn_dir, labdata


# ---------------------------------------------------------------------------
# 1. No-op when snapshot missing
# ---------------------------------------------------------------------------

class TestNoSnapshot:
    def test_returns_zero_no_snapshot(self, tmp_path: Path, monkeypatch):
        """main() must return 0 when no CN snapshot exists."""
        from engine.pick_lab import snapshot as snap_mod
        import scripts.build_china_pick_lab  # noqa: F401 — ensure module loaded

        monkeypatch.setattr(snap_mod, "latest_snapshot", lambda **kw: (None, None))
        monkeypatch.setattr("lib.config.ROOT", tmp_path)
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path / "data")
        monkeypatch.setenv("CN_LANE", "asia")

        # Reload to pick up env change
        import importlib
        import scripts.build_china_pick_lab as runner
        importlib.reload(runner)

        rc = runner.main()
        assert rc == 0


# ---------------------------------------------------------------------------
# 2. CN_LANE gate: no writes when CN_LANE != 'asia'
# ---------------------------------------------------------------------------

class TestLaneGate:
    def test_no_writes_when_not_asia(self, tmp_path: Path, monkeypatch):
        """main() must return 0 and write NO ledger rows when CN_LANE != 'asia'."""
        import importlib
        import scripts.build_china_pick_lab as runner

        asof = "2026-01-05"
        snap = _make_cn_snap(n=3, asof=asof)
        cn_dir, labdata = _patch_cn_env(tmp_path, monkeypatch, snap, asof)

        # Unset CN_LANE
        monkeypatch.delenv("CN_LANE", raising=False)

        # Reload to pick up env change
        importlib.reload(runner)

        rc = runner.main()
        assert rc == 0

        # Ledger files must NOT exist (no writes in non-asia lane)
        fires_path = cn_dir / "fires.jsonl"
        assert not fires_path.exists() or fires_path.stat().st_size == 0, (
            "fires.jsonl was written in a non-asia lane — CNPL-R8 violation"
        )


# ---------------------------------------------------------------------------
# 3. With synthetic snapshot: fires written; sealed_up excluded
# ---------------------------------------------------------------------------

class TestFirePass:
    def _run(self, tmp_path: Path, monkeypatch, snap: pd.DataFrame, asof: str):
        import importlib
        import scripts.build_china_pick_lab as runner

        cn_dir, labdata = _patch_cn_env(tmp_path, monkeypatch, snap, asof)
        monkeypatch.setenv("CN_LANE", "asia")
        importlib.reload(runner)

        rc = runner.main()
        assert rc == 0
        return cn_dir, labdata

    def test_fires_written(self, tmp_path: Path, monkeypatch):
        """At least one fire must be written for a valid CN snapshot with asia lane."""
        asof = "2026-02-03"
        snap = _make_cn_snap(n=5, asof=asof)
        cn_dir, _ = self._run(tmp_path, monkeypatch, snap, asof)

        fires_path = cn_dir / "fires.jsonl"
        assert fires_path.exists(), "fires.jsonl was not created"

        from engine.pick_lab.ledger import load_jsonl
        fires = load_jsonl(fires_path)
        assert len(fires) > 0, "No fires written on first run"

        for f in fires:
            assert f.get("authority") == "display_only"
            assert f.get("engine_id"), "fire row missing engine_id"
            assert f.get("ticker"), "fire row missing ticker"
            assert f.get("fire_date") == asof

    def test_sealed_up_excluded(self, tmp_path: Path, monkeypatch):
        """sealed_up tickers must NOT appear in fires.jsonl (CNPL-R4)."""
        asof = "2026-02-04"
        snap = _make_sealed_cn_snap(asof=asof)
        cn_dir, _ = self._run(tmp_path, monkeypatch, snap, asof)

        from engine.pick_lab.ledger import load_jsonl
        fires = load_jsonl(cn_dir / "fires.jsonl") if (cn_dir / "fires.jsonl").exists() else []

        sealed_ticker = "000001.SZ"
        for f in fires:
            assert f.get("ticker") != sealed_ticker, (
                f"sealed_up ticker {sealed_ticker} appeared in fires.jsonl — CNPL-R4 violation"
            )


# ---------------------------------------------------------------------------
# 4. Idempotent on second run
# ---------------------------------------------------------------------------

class TestIdempotent:
    def test_no_duplicates_on_second_run(self, tmp_path: Path, monkeypatch):
        """Running main() twice on the same asof must not duplicate fire rows."""
        import importlib
        import scripts.build_china_pick_lab as runner

        asof = "2026-03-05"
        snap = _make_cn_snap(n=4, asof=asof)
        cn_dir, _ = _patch_cn_env(tmp_path, monkeypatch, snap, asof)
        monkeypatch.setenv("CN_LANE", "asia")
        importlib.reload(runner)

        rc1 = runner.main()
        assert rc1 == 0

        from engine.pick_lab.ledger import load_jsonl, FIRE_KEY, keep_first
        fires_after_run1 = load_jsonl(cn_dir / "fires.jsonl") if (cn_dir / "fires.jsonl").exists() else []
        n1 = len(fires_after_run1)

        rc2 = runner.main()
        assert rc2 == 0

        fires_after_run2 = load_jsonl(cn_dir / "fires.jsonl") if (cn_dir / "fires.jsonl").exists() else []
        deduped = keep_first(fires_after_run2, FIRE_KEY)
        assert len(deduped) == n1, (
            f"Second run added duplicate fire rows: n1={n1}, n2={len(fires_after_run2)}, "
            f"deduped={len(deduped)}"
        )


# ---------------------------------------------------------------------------
# 5. Site artifact valid JSON schema
# ---------------------------------------------------------------------------

class TestSiteArtifact:
    def test_site_artifact_valid_json_schema(self, tmp_path: Path, monkeypatch):
        """site/labdata/china_pick_lab.json must exist and carry required top-level keys."""
        import importlib
        import scripts.build_china_pick_lab as runner

        asof = "2026-04-07"
        snap = _make_cn_snap(n=5, asof=asof)
        _patch_cn_env(tmp_path, monkeypatch, snap, asof)
        monkeypatch.setenv("CN_LANE", "asia")
        importlib.reload(runner)

        rc = runner.main()
        assert rc == 0

        artifact = tmp_path / "site" / "labdata" / "china_pick_lab.json"
        assert artifact.exists(), "china_pick_lab.json was not written"

        data = json.loads(artifact.read_text())

        required_keys = {
            "as_of", "built_at", "scoreboard", "books",
            "total_skipped_unfillable", "method_note", "authority",
        }
        missing = required_keys - set(data.keys())
        assert not missing, f"china_pick_lab.json missing keys: {missing}"
        assert data["authority"] == "display_only"
        assert data["as_of"] == asof
        assert isinstance(data["scoreboard"], list)
        assert isinstance(data["books"], dict)
        assert isinstance(data["total_skipped_unfillable"], int)

        for row in data["scoreboard"]:
            assert "engine_id" in row, f"scoreboard row missing engine_id: {row}"
            assert "n_fires" in row, f"scoreboard row missing n_fires: {row}"

    def test_artifact_absent_when_not_asia(self, tmp_path: Path, monkeypatch):
        """china_pick_lab.json must NOT be written when CN_LANE != 'asia'."""
        import importlib
        import scripts.build_china_pick_lab as runner

        asof = "2026-04-08"
        snap = _make_cn_snap(n=3, asof=asof)
        _patch_cn_env(tmp_path, monkeypatch, snap, asof)
        monkeypatch.delenv("CN_LANE", raising=False)
        importlib.reload(runner)

        rc = runner.main()
        assert rc == 0

        artifact = tmp_path / "site" / "labdata" / "china_pick_lab.json"
        assert not artifact.exists(), (
            "china_pick_lab.json was written in a non-asia lane — CNPL-R8 violation"
        )


# ---------------------------------------------------------------------------
# 6. Render failure is non-fatal
# ---------------------------------------------------------------------------

class TestRenderNonFatal:
    def test_render_exception_still_returns_zero(self, tmp_path: Path, monkeypatch):
        """A render exception must not cause main() to return non-zero."""
        import importlib
        import scripts.build_china_pick_lab as runner

        asof = "2026-05-06"
        snap = _make_cn_snap(n=3, asof=asof)
        _patch_cn_env(tmp_path, monkeypatch, snap, asof)
        monkeypatch.setenv("CN_LANE", "asia")
        importlib.reload(runner)

        # Patch render_page to raise
        try:
            from engine.pick_lab import render_cn as render_mod
            monkeypatch.setattr(render_mod, "render_page", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("render boom")))
        except Exception:
            pass

        rc = runner.main()
        assert rc == 0, f"main() returned {rc} after render exception — never-break violated"


# ---------------------------------------------------------------------------
# 7. Never-break contract
# ---------------------------------------------------------------------------

class TestNeverBreak:
    def test_returns_zero_on_exception(self, tmp_path: Path, monkeypatch):
        """main() must return 0 even when _build() raises an unexpected exception."""
        import importlib
        import scripts.build_china_pick_lab as runner
        monkeypatch.setenv("CN_LANE", "asia")
        importlib.reload(runner)

        def _exploding_build():
            raise RuntimeError("simulated catastrophic failure")

        monkeypatch.setattr(runner, "_build", _exploding_build)
        rc = runner.main()
        assert rc == 0, f"main() returned {rc} after exception — never-break violated"

    def test_returns_zero_on_import_error(self, tmp_path: Path, monkeypatch):
        """main() returns 0 even when engine.pick_lab modules raise ImportError."""
        import importlib
        import scripts.build_china_pick_lab as runner
        monkeypatch.setenv("CN_LANE", "asia")
        importlib.reload(runner)

        def _import_error_build():
            raise ImportError("engine.pick_lab.cn not installed")

        monkeypatch.setattr(runner, "_build", _import_error_build)
        rc = runner.main()
        assert rc == 0


# ---------------------------------------------------------------------------
# 8. Grade pass: shared grade_fires() via benchmark-calendar panel
# ---------------------------------------------------------------------------

def _make_cn_grade_env(tmp_path: Path, monkeypatch, asof: str):
    """Build a CN test environment with raw OHLC and a CSI300 benchmark series.

    Returns (cn_dir, raw_dir, bm_series, dates).
    """
    raw_dir = tmp_path / "data" / "china_stocks_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2025-11-01", periods=80, freq="B")
    for ticker in ["100000.SS", "100001.SS"]:
        df = pd.DataFrame({
            "open": 10.0, "close": 10.5, "high": 11.0, "low": 9.5, "volume": 1e6,
        }, index=dates)
        df.to_parquet(raw_dir / f"{ticker}.parquet")

    snap = _make_cn_snap(n=2, asof=asof)
    cn_dir, labdata = _patch_cn_env(tmp_path, monkeypatch, snap, asof)

    from engine.pick_lab.profile import MarketProfile, CN_PROFILE
    from engine.pick_lab import profile as prof_mod

    bm_series = pd.Series(10000.0, index=pd.DatetimeIndex(dates))

    tmp_profile2 = MarketProfile(
        market_id=prof_mod.CN_PROFILE.market_id,
        fires_path=cn_dir / "fires.jsonl",
        grades_path=cn_dir / "grades.jsonl",
        lh_fires_path=cn_dir / "lh_fires.jsonl",
        lh_grades_path=cn_dir / "lh_grades.jsonl",
        snapshot_dir=cn_dir / "snapshots",
        benchmark_ticker=CN_PROFILE.benchmark_ticker,
        benchmark_loader=lambda: bm_series,
        fill_basis="close",
        raw_store_path_template=str(raw_dir / "{ticker}.parquet"),
        sealed_up_col=CN_PROFILE.sealed_up_col,
        fillable_col=CN_PROFILE.fillable_col,
        entry_horizons=CN_PROFILE.entry_horizons,
        lh_horizons=CN_PROFILE.lh_horizons,
        primary_horizon=CN_PROFILE.primary_horizon,
        mfe_mae_sessions=CN_PROFILE.mfe_mae_sessions,
        random_ctrl_id=CN_PROFILE.random_ctrl_id,
        avoid_engine_id=CN_PROFILE.avoid_engine_id,
        refire_lockout_sessions=CN_PROFILE.refire_lockout_sessions,
        liq_close_min=CN_PROFILE.liq_close_min,
        liq_turnover_min=CN_PROFILE.liq_turnover_min,
        max_picks_default=CN_PROFILE.max_picks_default,
        extra_fire_stamp_cols=CN_PROFILE.extra_fire_stamp_cols,
        skipped_unfillable_col=CN_PROFILE.skipped_unfillable_col,
        data_gap_col=CN_PROFILE.data_gap_col,
        st_exclude_col=CN_PROFILE.st_exclude_col,
        default_ruler=CN_PROFILE.default_ruler,
        excess_label=CN_PROFILE.excess_label,
    )
    monkeypatch.setattr(prof_mod, "CN_PROFILE", tmp_profile2)
    return cn_dir, raw_dir, bm_series, dates


class TestGradePassPanel:
    def test_grade_hl2_fill_basis_with_raw_ohlc(self, tmp_path: Path, monkeypatch):
        """CNPL-R4: when raw OHLC is present, exec_price = (H+L)/2 and fill_basis='hl2'.

        The test environment writes high=11.0, low=9.5 for every session.
        Expected exec_price = (11.0 + 9.5) / 2 = 10.25.
        fill_basis must be 'hl2'.
        """
        import importlib

        asof = "2025-11-05"  # old date so horizon can elapse within the 80-day window
        cn_dir, raw_dir, bm_series, dates = _make_cn_grade_env(tmp_path, monkeypatch, asof)

        monkeypatch.setenv("CN_LANE", "asia")
        import scripts.build_china_pick_lab as runner
        importlib.reload(runner)

        rc = runner.main()
        assert rc == 0

        from engine.pick_lab.ledger import load_jsonl
        grades = load_jsonl(cn_dir / "grades.jsonl") if (cn_dir / "grades.jsonl").exists() else []

        # Must have produced at least some grade rows (asof is old enough)
        assert grades, "Expected grade rows with raw OHLC present"

        ret_rows = [g for g in grades if g.get("kind") == "ret"]
        assert ret_rows, "Expected ret-kind grade rows"

        for g in ret_rows:
            # CNPL-R4: fill price = (H+L)/2 when raw OHLC present
            assert g.get("fill_basis") == "hl2", (
                f"CNPL-R4: fill_basis expected 'hl2' when raw OHLC present, "
                f"got {g.get('fill_basis')!r}: {g}"
            )
            # exec_price must be the hl2 value: (11.0 + 9.5) / 2 = 10.25
            assert abs(g.get("exec_price", 0) - 10.25) < 1e-3, (
                f"CNPL-R4: exec_price expected ~10.25 (hl2), got {g.get('exec_price')!r}: {g}"
            )
            assert g.get("benchmark_ticker") is not None, (
                f"grade row missing benchmark_ticker: {g}"
            )
            assert g.get("authority") == "display_only"

    def test_grade_close_fallback_when_raw_ohlc_absent(self, tmp_path: Path, monkeypatch):
        """CNPL-R4 fallback: when raw OHLC is absent, fill_basis='close' (panel close used).

        We set up one ticker WITH raw OHLC (expects hl2) and delete/skip one without.
        This test writes no raw OHLC at all so every ticker falls back to close.
        """
        import importlib

        asof = "2025-11-05"
        raw_dir = tmp_path / "data" / "china_stocks_raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        dates = pd.date_range("2025-11-01", periods=80, freq="B")

        # Write raw OHLC WITHOUT high/low columns — forces close fallback
        for ticker in ["100000.SS", "100001.SS"]:
            df = pd.DataFrame({
                "open": 10.0, "close": 10.5, "volume": 1e6,
            }, index=dates)
            df.to_parquet(raw_dir / f"{ticker}.parquet")

        snap = _make_cn_snap(n=2, asof=asof)
        cn_dir, labdata = _patch_cn_env(tmp_path, monkeypatch, snap, asof)

        from engine.pick_lab.profile import MarketProfile, CN_PROFILE
        from engine.pick_lab import profile as prof_mod

        bm_series = pd.Series(10000.0, index=pd.DatetimeIndex(dates))
        tmp_profile2 = MarketProfile(
            market_id=prof_mod.CN_PROFILE.market_id,
            fires_path=cn_dir / "fires.jsonl",
            grades_path=cn_dir / "grades.jsonl",
            lh_fires_path=cn_dir / "lh_fires.jsonl",
            lh_grades_path=cn_dir / "lh_grades.jsonl",
            snapshot_dir=cn_dir / "snapshots",
            benchmark_ticker=CN_PROFILE.benchmark_ticker,
            benchmark_loader=lambda: bm_series,
            fill_basis="close",
            raw_store_path_template=str(raw_dir / "{ticker}.parquet"),
            sealed_up_col=CN_PROFILE.sealed_up_col,
            fillable_col=CN_PROFILE.fillable_col,
            entry_horizons=CN_PROFILE.entry_horizons,
            lh_horizons=CN_PROFILE.lh_horizons,
            primary_horizon=CN_PROFILE.primary_horizon,
            mfe_mae_sessions=CN_PROFILE.mfe_mae_sessions,
            random_ctrl_id=CN_PROFILE.random_ctrl_id,
            avoid_engine_id=CN_PROFILE.avoid_engine_id,
            refire_lockout_sessions=CN_PROFILE.refire_lockout_sessions,
            liq_close_min=CN_PROFILE.liq_close_min,
            liq_turnover_min=CN_PROFILE.liq_turnover_min,
            max_picks_default=CN_PROFILE.max_picks_default,
            extra_fire_stamp_cols=CN_PROFILE.extra_fire_stamp_cols,
            skipped_unfillable_col=CN_PROFILE.skipped_unfillable_col,
            data_gap_col=CN_PROFILE.data_gap_col,
            st_exclude_col=CN_PROFILE.st_exclude_col,
            default_ruler=CN_PROFILE.default_ruler,
            excess_label=CN_PROFILE.excess_label,
        )
        monkeypatch.setattr(prof_mod, "CN_PROFILE", tmp_profile2)

        monkeypatch.setenv("CN_LANE", "asia")
        import scripts.build_china_pick_lab as runner
        importlib.reload(runner)

        rc = runner.main()
        assert rc == 0

        from engine.pick_lab.ledger import load_jsonl
        grades = load_jsonl(cn_dir / "grades.jsonl") if (cn_dir / "grades.jsonl").exists() else []

        ret_rows = [g for g in grades if g.get("kind") == "ret"]
        assert ret_rows, "Expected ret-kind grade rows"

        for g in ret_rows:
            # No H/L in raw OHLC — must fall back to close
            assert g.get("fill_basis") == "close", (
                f"CNPL-R4 fallback: fill_basis expected 'close' when H/L absent, "
                f"got {g.get('fill_basis')!r}: {g}"
            )
            # exec_price from panel close = 10.5
            assert abs(g.get("exec_price", 0) - 10.5) < 1e-3, (
                f"CNPL-R4 fallback: exec_price expected ~10.5 (close), got {g.get('exec_price')!r}: {g}"
            )
            assert g.get("benchmark_ticker") is not None

    def test_grade_excess_spy_uses_csi300(self, tmp_path: Path, monkeypatch):
        """ret_excess_spy is computed against CSI300 (the CN benchmark)."""
        import importlib

        asof = "2025-11-05"
        cn_dir, raw_dir, bm_series, dates = _make_cn_grade_env(tmp_path, monkeypatch, asof)

        monkeypatch.setenv("CN_LANE", "asia")
        import scripts.build_china_pick_lab as runner
        importlib.reload(runner)

        rc = runner.main()
        assert rc == 0

        from engine.pick_lab.ledger import load_jsonl
        grades = load_jsonl(cn_dir / "grades.jsonl") if (cn_dir / "grades.jsonl").exists() else []

        # When benchmark series is flat (10000), excess = ret_abs (flat benchmark → ret_abs - 0)
        for g in grades:
            if g.get("ret_abs") is not None and g.get("ret_excess_spy") is not None:
                # Flat benchmark: ret_excess_spy should approximately equal ret_abs
                diff = abs(g["ret_abs"] - g["ret_excess_spy"])
                assert diff < 1e-4, (
                    f"ret_excess_spy should equal ret_abs for flat benchmark; "
                    f"got ret_abs={g['ret_abs']}, ret_excess_spy={g['ret_excess_spy']}"
                )


# ---------------------------------------------------------------------------
# 10. Halt semantics: NaN close mid-window grades as ungradeable
# ---------------------------------------------------------------------------

class TestCNHaltSemantics:
    def test_halted_ticker_grades_ungradeable_at_blocked_horizon(self, tmp_path: Path, monkeypatch):
        """A CN ticker with NaN closes mid-window grades as ungradeable at those horizons.

        Scenario: two fires on the same day.
        - normal_ticker: continuous closes throughout the window → grades at h=5
        - halted_ticker: closes go NaN after exec_date → ungradeable at h=5 (no close)

        The benchmark (CSI300) calendar is continuous; halted_ticker's NaN sessions
        are represented as NaN in the panel — grade.py's null-honest handling
        marks it ungradeable (no grade row emitted).
        """
        import importlib
        import numpy as np
        from engine.pick_lab.grade import grade_fires
        from scripts.build_china_pick_lab import _build_cn_close_panel

        # 40 benchmark sessions
        dates = pd.date_range("2025-11-03", periods=40, freq="B")
        csi300 = pd.Series(10000.0, index=pd.DatetimeIndex(dates))

        # normal_ticker: full close series
        close_normal = pd.Series(15.0, index=pd.DatetimeIndex(dates))

        # halted_ticker: NaN from session 2 onward (simulates halt immediately after exec)
        close_halted = pd.Series(15.0, index=pd.DatetimeIndex(dates))
        close_halted.iloc[2:] = float("nan")  # halted from position 2 onward

        raw_by_ticker = {
            "normal_ticker": pd.DataFrame({"close": close_normal, "high": close_normal + 0.5, "low": close_normal - 0.5}, index=dates),
            "halted_ticker": pd.DataFrame({"close": close_halted, "high": close_halted + 0.5, "low": close_halted - 0.5}, index=dates),
        }

        close_panel, high_panel, low_panel = _build_cn_close_panel(csi300, raw_by_ticker)

        fire_date = str(dates[0].date())  # fire on session 0
        fires = [
            {"engine_id": "test_book", "ticker": "normal_ticker", "fire_date": fire_date},
            {"engine_id": "test_book", "ticker": "halted_ticker", "fire_date": fire_date},
        ]

        grade_rows, n_ung = grade_fires(
            fires,
            close_panel,
            csi300,
            sector_closes=None,
            hold_thesis=False,
        )

        # normal_ticker should produce ret grade rows at every elapsed horizon
        normal_ret_rows = [
            r for r in grade_rows
            if r.get("ticker") == "normal_ticker" and r.get("kind") == "ret"
        ]
        assert len(normal_ret_rows) > 0, "normal_ticker should have ret grade rows"

        # halted_ticker ret rows: exec=session 1 (close=15.0, valid).
        # ENTRY_HORIZONS = (5,10,21,63). Target sessions: 6,11,22,64.
        # close_halted is NaN from iloc[2] onward → sessions 2+ are NaN.
        # Targets 6,11,22 are NaN → ungradeable (no ret row).
        # Session 64 out of range (40 sessions) → not yet elapsed → no row.
        # halted_ticker should produce ZERO ret grade rows.
        halted_ret_rows = [
            r for r in grade_rows
            if r.get("ticker") == "halted_ticker" and r.get("kind") == "ret"
        ]
        assert len(halted_ret_rows) == 0, (
            f"halted_ticker should produce no ret grade rows (NaN closes from session 2); "
            f"got: {halted_ret_rows}"
        )

        # n_ung should be > 0 (halted_ticker counted as ungradeable per elapsed horizon)
        assert n_ung > 0, "ungradeable count should be > 0 for the halted ticker"


# ---------------------------------------------------------------------------
# 9. Enrichment helpers unit tests
# ---------------------------------------------------------------------------

class TestEnrichmentHelpers:
    def test_build_microstructure_by_ticker(self):
        """_build_microstructure_by_ticker extracts limit_state and fillable per ticker."""
        from scripts.build_china_pick_lab import _build_microstructure_by_ticker

        ms = {
            "name_packets": [
                {
                    "ticker": "000001.SZ",
                    "limit_state": "sealed_up",
                    "fillable": False,
                    "chase_veto": {"flag": True, "reason": "limit_up"},
                    "t_plus_one_risk": "high",
                },
                {
                    "ticker": "000002.SZ",
                    "limit_state": "open",
                    "fillable": True,
                    "chase_veto": {"flag": False, "reason": None},
                    "t_plus_one_risk": "normal",
                },
            ]
        }
        result = _build_microstructure_by_ticker(ms)
        assert "000001.SZ" in result
        assert result["000001.SZ"]["limit_state"] == "sealed_up"
        assert result["000001.SZ"]["fillable"] is False
        assert result["000001.SZ"]["chase_veto"] is True
        assert "000002.SZ" in result
        assert result["000002.SZ"]["fillable"] is True
        assert result["000002.SZ"]["chase_veto"] is False

    def test_build_ths_membership_basic(self):
        """_build_ths_membership returns theme_basket for member tickers."""
        from scripts.build_china_pick_lab import _build_ths_membership

        ths = {
            "baskets": [
                {
                    "id": "basket_ai",
                    "name": "AI Chips",
                    "perf": {"20d": 1.15},
                    "members": [
                        {"symbol": "688361.SS", "ret_20d": 1.10},
                        {"symbol": "000001.SZ", "ret_20d": 1.05},
                    ],
                }
            ]
        }
        result = _build_ths_membership(ths)
        assert "688361.SS" in result
        assert result["688361.SS"]["theme_basket"] == "AI Chips"
        assert result["688361.SS"]["theme_breadth_pct"] is not None

    def test_build_ths_membership_empty(self):
        """_build_ths_membership returns {} when THS data is absent."""
        from scripts.build_china_pick_lab import _build_ths_membership

        assert _build_ths_membership({}) == {}
        assert _build_ths_membership({"baskets": []}) == {}

    def test_build_microstructure_by_ticker_empty(self):
        """_build_microstructure_by_ticker returns {} when microstructure absent."""
        from scripts.build_china_pick_lab import _build_microstructure_by_ticker

        assert _build_microstructure_by_ticker({}) == {}
        assert _build_microstructure_by_ticker({"name_packets": []}) == {}

    def test_ths_membership_scale_matches_book_thresholds(self):
        """End-to-end: _build_ths_membership output must be on 0..100 scale.

        Regression test for the breadth_pct / rank scale mismatch (finding: enrichment
        was emitting 0..1 fractions while book config uses 80.0/50 thresholds).
        A 4/5-positive basket must yield breadth_pct=80.0 (not 0.8), and the
        bottom-ranked member must yield rank=0.0 (not 0.0 on a 0..1 scale is the
        same, but the top member must yield 100.0 not 1.0).
        Feeding the result through the cnlab_theme_laggard book must produce picks
        when breadth >= 80 and member rank <= 50 (bottom half).
        """
        import numpy as np
        from scripts.build_china_pick_lab import _build_ths_membership
        from engine.pick_lab.cn import _book_cn_theme_laggard
        from engine.pick_lab.registry_cn import CN_REGISTRY

        ths = {
            "baskets": [
                {
                    "id": "basket_semi",
                    "name": "Semiconductors",
                    "perf": {"20d": 1.05},
                    "members": [
                        # 4 of 5 are positive → breadth = 80%
                        {"symbol": "688361.SS", "ret_20d": 1.10},
                        {"symbol": "688396.SS", "ret_20d": 1.08},
                        {"symbol": "688008.SS", "ret_20d": 1.05},
                        {"symbol": "688012.SS", "ret_20d": 1.02},
                        {"symbol": "300700.SZ", "ret_20d": 0.97},  # negative → not positive
                    ],
                }
            ]
        }
        result = _build_ths_membership(ths)

        # Scale check: breadth_pct must be 80.0, NOT 0.8
        breadth = result["688361.SS"]["theme_breadth_pct"]
        assert breadth is not None
        assert breadth > 1.0, (
            f"theme_breadth_pct={breadth} looks like a 0..1 fraction; "
            "enrichment must emit percent-scale values (0..100) to match book threshold 80.0"
        )
        assert abs(breadth - 80.0) < 0.01, f"Expected 80.0, got {breadth}"

        # Rank scale: the worst performer (rank 0) must be 0.0, best must be 100.0
        # 300700.SZ has ret_20d=0.97 (lowest) → rank index 0 → percentile 0.0
        rank_worst = result["300700.SZ"]["theme_member_ret21_rank"]
        rank_best = result["688361.SS"]["theme_member_ret21_rank"]
        assert rank_worst is not None and rank_best is not None
        assert rank_worst < rank_best, "Worst performer should have lower rank"
        assert rank_best > 1.0, (
            f"theme_member_ret21_rank={rank_best} looks like 0..1 fraction; "
            "must be percent-scale (0..100) to match book threshold le(50)"
        )

        # End-to-end book pass: cnlab_theme_laggard must fire when breadth=80 and rank<=50
        theme_book = next(b for b in CN_REGISTRY if b["engine_id"] == "cnlab_theme_laggard")
        # Build a minimal snapshot DataFrame with a laggard ticker (rank in bottom half)
        # 300700.SZ has rank=0.0 → in bottom half → should appear as a laggard pick
        snap = pd.DataFrame([
            {
                "ticker": "300700.SZ",
                "theme_breadth_pct": result["300700.SZ"]["theme_breadth_pct"],
                "theme_member_ret21_rank": result["300700.SZ"]["theme_member_ret21_rank"],
                "chase_veto": False,
                "name": "Test Co",
                "name_zh": "测试",
                "sector": "Technology",
                "close": 15.0,
                "dd_pct_2y": 25.0,
                "rev_3m": -0.12,
            }
        ]).set_index("ticker")
        picks = _book_cn_theme_laggard(snap, theme_book)
        assert len(picks) > 0, (
            "cnlab_theme_laggard produced zero picks for a ticker with "
            f"breadth={result['300700.SZ']['theme_breadth_pct']:.1f} "
            f"and rank={result['300700.SZ']['theme_member_ret21_rank']:.1f} — "
            "scale mismatch (book threshold: breadth>=80, rank<=50)"
        )
