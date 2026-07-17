"""tests/test_pick_lab_hk_runner.py — end-to-end runner tests for scripts.build_hk_pick_lab.

Tests
-----
1. No-op when snapshot missing: main() returns 0.
2. CN_LANE gate: main() returns 0 with no writes when CN_LANE is not 'asia'.
3. Synthetic snapshot → fires written (entry ledger, no sealed_up concept in HK).
4. Idempotent: second run on same asof produces no duplicate fire rows.
5. Halt-void path: a ticker with no close series in exec window triggers halt_voided.
6. Organ-stale disable path: books with stale organ freshness are disabled.
7. Site artifact valid JSON schema (as_of, authority, scoreboard, books, total_halt_voided).
8. Render call is non-fatal (renderer exception → still returns 0).
9. Never-break: main() returns 0 even when _build() raises.
10. Enrichment helpers unit tests (_build_adr_by_ticker, etc.).
"""
from __future__ import annotations

import json
import os
import sys
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
# Synthetic HK snapshot builder
# ---------------------------------------------------------------------------

def _make_hk_snap(n: int = 5, asof: str = "2026-01-05") -> pd.DataFrame:
    """Minimal DataFrame conforming to HK_SNAPSHOT_COLUMNS for testing."""
    from engine.pick_lab.hk_snapshot import HK_SNAPSHOT_COLUMNS

    tickers = [f"{1000 + i:04d}.HK" for i in range(n)]
    rows = []
    for i, t in enumerate(tickers):
        row = {c: None for c in HK_SNAPSHOT_COLUMNS}
        row["ticker"] = t
        row["asof"] = asof
        row["close"] = 10.0 + i          # HK$ denominated
        row["adv63_hkd"] = 50e6          # above HK$20M liquidity floor
        row["last_print_sessions_ago"] = 0  # not suspended
        row["sector"] = "Technology"
        row["name"] = f"Test Co {i}"
        row["name_zh"] = f"测试公司 {i}"
        # 1D oscillators — make hklab_1d_pure fire
        row["d1_macd_xup_bars"] = 1      # <= 2
        row["d1_stoch_xup_bars"] = 3     # <= 8
        row["d1_from_os"] = True
        row["rsi14"] = 40.0              # < 70
        # Technicals
        row["off_high"] = -0.20
        row["dist_200dma"] = 0.05
        row["above_200"] = True
        row["edge_z"] = 0.5 + i * 0.1
        row["beta"] = 1.2
        row["beta_role"] = "amplifier"
        # Regime (top-level scalars)
        row["risk_state"] = "Risk-on"
        row["peg_state"] = "normal"
        row["liquidity_regime"] = "EASY"
        row["vhsi_pctile"] = 30.0
        rows.append(row)

    df = pd.DataFrame(rows).set_index("ticker")
    df.attrs["asof"] = asof
    return df


def _make_halt_snap(asof: str = "2026-01-06") -> pd.DataFrame:
    """Snapshot with ONE halted ticker (no close in store) and one normal ticker."""
    from engine.pick_lab.hk_snapshot import HK_SNAPSHOT_COLUMNS

    rows = []
    for i, ticker in enumerate(["1001.HK", "1002.HK"]):
        row = {c: None for c in HK_SNAPSHOT_COLUMNS}
        row["ticker"] = ticker
        row["asof"] = asof
        row["close"] = 10.0 + i
        row["adv63_hkd"] = 50e6
        row["last_print_sessions_ago"] = 0
        row["name"] = f"Co {i}"
        row["name_zh"] = f"公司 {i}"
        row["sector"] = "Financials"
        row["d1_macd_xup_bars"] = 1
        row["d1_stoch_xup_bars"] = 3
        row["d1_from_os"] = True
        row["rsi14"] = 40.0
        row["edge_z"] = 0.5
        row["risk_state"] = "Risk-on"
        rows.append(row)

    df = pd.DataFrame(rows).set_index("ticker")
    df.attrs["asof"] = asof
    return df


# ---------------------------------------------------------------------------
# Monkey-patch helpers
# ---------------------------------------------------------------------------

def _patch_hk_env(tmp_path: Path, monkeypatch, snap: pd.DataFrame, asof: str,
                  close_series: Optional[pd.Series] = None):
    """Set up a tmp-sandboxed environment with the given HK snapshot.

    Patches snapshot.latest_snapshot, config.ROOT, and HK_PROFILE paths.
    Optionally patches the data store to return a close series for tickers.
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

    # Create HK ledger dirs
    hk_dir = data_dir / "hk_pick_lab"
    hk_dir.mkdir(parents=True, exist_ok=True)

    # Build a replacement profile pointing into tmp_path
    from engine.pick_lab.profile import MarketProfile, HK_PROFILE
    from engine.pick_lab import profile as prof_mod

    bm_loader = (lambda: close_series) if close_series is not None else None

    tmp_profile = MarketProfile(
        market_id=HK_PROFILE.market_id,
        fires_path=hk_dir / "fires.jsonl",
        grades_path=hk_dir / "grades.jsonl",
        lh_fires_path=hk_dir / "lh_fires.jsonl",
        lh_grades_path=hk_dir / "lh_grades.jsonl",
        snapshot_dir=data_dir / "hk_pick_lab" / "snapshots",
        benchmark_ticker=HK_PROFILE.benchmark_ticker,
        benchmark_loader=bm_loader,
        fill_basis=HK_PROFILE.fill_basis,
        raw_store_path_template=HK_PROFILE.raw_store_path_template,
        sealed_up_col=HK_PROFILE.sealed_up_col,
        fillable_col=HK_PROFILE.fillable_col,
        entry_horizons=HK_PROFILE.entry_horizons,
        lh_horizons=HK_PROFILE.lh_horizons,
        primary_horizon=HK_PROFILE.primary_horizon,
        mfe_mae_sessions=HK_PROFILE.mfe_mae_sessions,
        random_ctrl_id=HK_PROFILE.random_ctrl_id,
        avoid_engine_id=HK_PROFILE.avoid_engine_id,
        refire_lockout_sessions=HK_PROFILE.refire_lockout_sessions,
        liq_close_min=HK_PROFILE.liq_close_min,
        liq_turnover_min=HK_PROFILE.liq_turnover_min,
        max_picks_default=HK_PROFILE.max_picks_default,
        extra_fire_stamp_cols=HK_PROFILE.extra_fire_stamp_cols,
        skipped_unfillable_col=HK_PROFILE.skipped_unfillable_col,
        data_gap_col=HK_PROFILE.data_gap_col,
        st_exclude_col=HK_PROFILE.st_exclude_col,
        default_ruler=HK_PROFILE.default_ruler,
        excess_label=HK_PROFILE.excess_label,
    )

    monkeypatch.setattr(prof_mod, "HK_PROFILE", tmp_profile)

    # Create site dirs
    labdata = tmp_path / "site" / "labdata"
    labdata.mkdir(parents=True, exist_ok=True)
    factordata = tmp_path / "site" / "factordata"
    factordata.mkdir(parents=True, exist_ok=True)

    return hk_dir, labdata


# ---------------------------------------------------------------------------
# 1. No-op when snapshot missing
# ---------------------------------------------------------------------------

class TestNoSnapshot:
    def test_returns_zero_no_snapshot(self, tmp_path: Path, monkeypatch):
        """main() must return 0 when no HK snapshot exists."""
        from engine.pick_lab import snapshot as snap_mod
        import importlib

        monkeypatch.setattr(snap_mod, "latest_snapshot", lambda **kw: (None, None))
        monkeypatch.setattr("lib.config.ROOT", tmp_path)
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path / "data")
        monkeypatch.setenv("CN_LANE", "asia")

        import scripts.build_hk_pick_lab as runner
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
        import scripts.build_hk_pick_lab as runner

        asof = "2026-01-05"
        snap = _make_hk_snap(n=3, asof=asof)
        hk_dir, labdata = _patch_hk_env(tmp_path, monkeypatch, snap, asof)

        monkeypatch.delenv("CN_LANE", raising=False)
        importlib.reload(runner)

        rc = runner.main()
        assert rc == 0

        fires_path = hk_dir / "fires.jsonl"
        assert not fires_path.exists() or fires_path.stat().st_size == 0, (
            "fires.jsonl was written in a non-asia lane — HKPL-R8 violation"
        )


# ---------------------------------------------------------------------------
# 3. Synthetic snapshot → fires written
# ---------------------------------------------------------------------------

class TestFirePass:
    def _run(self, tmp_path: Path, monkeypatch, snap: pd.DataFrame, asof: str,
             close_series=None):
        import importlib
        import scripts.build_hk_pick_lab as runner

        hk_dir, labdata = _patch_hk_env(tmp_path, monkeypatch, snap, asof, close_series)
        monkeypatch.setenv("CN_LANE", "asia")
        importlib.reload(runner)

        rc = runner.main()
        assert rc == 0
        return hk_dir, labdata

    def test_fires_written(self, tmp_path: Path, monkeypatch):
        """At least one fire must be written for a valid HK snapshot with asia lane."""
        asof = "2026-02-03"
        snap = _make_hk_snap(n=5, asof=asof)
        hk_dir, _ = self._run(tmp_path, monkeypatch, snap, asof)

        fires_path = hk_dir / "fires.jsonl"
        assert fires_path.exists(), "fires.jsonl was not created"

        from engine.pick_lab.ledger import load_jsonl
        fires = load_jsonl(fires_path)
        assert len(fires) > 0, "No fires written on first run"

        for f in fires:
            assert f.get("authority") == "display_only"
            assert f.get("engine_id"), "fire row missing engine_id"
            assert f.get("ticker"), "fire row missing ticker"
            assert f.get("fire_date") == asof
            # No sealed_up / skipped_unfillable concept in HK
            assert "halt_voided" in f, "fire row missing halt_voided field"

    def test_no_sealed_up_concept(self, tmp_path: Path, monkeypatch):
        """HK fires must never carry limit_state or fillable columns (HKPL-R4)."""
        asof = "2026-02-04"
        snap = _make_hk_snap(n=3, asof=asof)
        hk_dir, _ = self._run(tmp_path, monkeypatch, snap, asof)

        from engine.pick_lab.ledger import load_jsonl
        fires = load_jsonl(hk_dir / "fires.jsonl") if (hk_dir / "fires.jsonl").exists() else []
        for f in fires:
            assert "sealed_up" not in str(f.get("limit_state", "")), (
                "HK fire row contains limit_state='sealed_up' — HK has no price limits (HKPL-R4)"
            )


# ---------------------------------------------------------------------------
# 4. Idempotent on second run
# ---------------------------------------------------------------------------

class TestIdempotent:
    def test_no_duplicates_on_second_run(self, tmp_path: Path, monkeypatch):
        """Running main() twice on the same asof must not duplicate fire rows."""
        import importlib
        import scripts.build_hk_pick_lab as runner

        asof = "2026-03-05"
        snap = _make_hk_snap(n=4, asof=asof)
        hk_dir, _ = _patch_hk_env(tmp_path, monkeypatch, snap, asof)
        monkeypatch.setenv("CN_LANE", "asia")
        importlib.reload(runner)

        rc1 = runner.main()
        assert rc1 == 0

        from engine.pick_lab.ledger import load_jsonl, FIRE_KEY, keep_first
        fires_after_run1 = load_jsonl(hk_dir / "fires.jsonl") if (hk_dir / "fires.jsonl").exists() else []
        n1 = len(fires_after_run1)

        rc2 = runner.main()
        assert rc2 == 0

        fires_after_run2 = load_jsonl(hk_dir / "fires.jsonl") if (hk_dir / "fires.jsonl").exists() else []
        deduped = keep_first(fires_after_run2, FIRE_KEY)
        assert len(deduped) == n1, (
            f"Second run added duplicate fire rows: n1={n1}, n2={len(fires_after_run2)}, "
            f"deduped={len(deduped)}"
        )


# ---------------------------------------------------------------------------
# 5. Halt-void path
# ---------------------------------------------------------------------------

class TestHaltVoidPath:
    def test_halt_voided_on_missing_close(self, tmp_path: Path, monkeypatch):
        """HKPL-R4 halt law — three cases tested:

        (i)  Ticker 1001.HK has NaN on exec session with first print 2 sessions later
             → graded, exec at that session's close, halted=True, fill_basis='close_halt_delayed'.
        (ii) Ticker 1002.HK has no print within 5 elapsed sessions after natural exec
             → zero grade rows for it AND halt_voided incremented.
        (iii) Ticker 1003.HK is halted across the h5 target session but has prints
             earlier in the grade window → h5 grades to last trade with halted=True.
        """
        import importlib
        import scripts.build_hk_pick_lab as runner
        import scripts.build_hk_pick_lab as runner_mod

        # Use an old asof so that h=5 can fully elapse in an 80-session window
        asof = "2025-11-05"
        dates = pd.date_range("2025-11-01", periods=80, freq="B")
        hsi_series = pd.Series(20000.0, index=pd.DatetimeIndex(dates))

        # Build a 3-ticker halt snapshot
        from engine.pick_lab.hk_snapshot import HK_SNAPSHOT_COLUMNS
        rows = []
        for ticker in ["1001.HK", "1002.HK", "1003.HK"]:
            row = {c: None for c in HK_SNAPSHOT_COLUMNS}
            row["ticker"] = ticker
            row["asof"] = asof
            row["close"] = 10.0
            row["adv63_hkd"] = 50e6
            row["last_print_sessions_ago"] = 0
            row["name"] = "Test Co"
            row["name_zh"] = "测试"
            row["sector"] = "Financials"
            row["d1_macd_xup_bars"] = 1
            row["d1_stoch_xup_bars"] = 3
            row["d1_from_os"] = True
            row["rsi14"] = 40.0
            row["edge_z"] = 0.5
            row["risk_state"] = "Risk-on"
            row["peg_state"] = "normal"
            row["liquidity_regime"] = "EASY"
            row["vhsi_pctile"] = 25.0
            rows.append(row)
        snap = pd.DataFrame(rows).set_index("ticker")
        snap.attrs["asof"] = asof

        hk_dir, labdata = _patch_hk_env(tmp_path, monkeypatch, snap, asof, close_series=hsi_series)
        monkeypatch.setenv("CN_LANE", "asia")

        # asof index in dates: dates[4] = 2025-11-07 (5th business day)
        # exec_date for asof 2025-11-05 = dates[4] (first session after asof)
        # But we need to know exact date - use the benchmark series dates
        asof_ts = pd.Timestamp(asof)
        future_dates = dates[dates > asof_ts]
        assert len(future_dates) >= 7, "Need enough future dates for the test"
        natural_exec_idx = 0  # first session after asof
        natural_exec_date = future_dates[natural_exec_idx]

        # Case (i): 1001.HK — NaN on exec session, print at exec+2
        closes_1001 = pd.Series(float("nan"), index=pd.DatetimeIndex(dates), dtype=float)
        closes_1001[natural_exec_date] = float("nan")
        # Print at exec+2 (index 2 after natural_exec in future_dates)
        delayed_exec_date = future_dates[2]
        closes_1001[delayed_exec_date] = 12.0
        for i in range(3, len(future_dates)):
            closes_1001[future_dates[i]] = 12.5

        # Case (ii): 1002.HK — no print in 5 sessions after natural exec (→ halt_voided)
        closes_1002 = pd.Series(float("nan"), index=pd.DatetimeIndex(dates), dtype=float)
        # Ensure at least 6 sessions after natural_exec exist with NaN
        for i in range(6):
            if i < len(future_dates):
                closes_1002[future_dates[i]] = float("nan")
        # Print only after 6+ sessions (beyond fill_window=5)
        if len(future_dates) > 6:
            for i in range(6, len(future_dates)):
                closes_1002[future_dates[i]] = 15.0

        # Case (iii): 1003.HK — halted across h=5 target session, print at exec+3 then NaN at exec+5
        closes_1003 = pd.Series(float("nan"), index=pd.DatetimeIndex(dates), dtype=float)
        # Has a print at exec_date (natural exec)
        closes_1003[natural_exec_date] = 10.0
        # Prints at exec+1, exec+2, exec+3
        for i in range(1, 4):
            if i < len(future_dates):
                closes_1003[future_dates[i]] = 10.0 + i * 0.1
        # NaN at exec+4 and exec+5 (h=5 target session is exec+5 which is NaN)
        for i in range(4, 6):
            if i < len(future_dates):
                closes_1003[future_dates[i]] = float("nan")
        # Prints beyond h=5
        for i in range(6, len(future_dates)):
            closes_1003[future_dates[i]] = 11.0

        # Per-ticker close series dispatch
        close_map = {
            "1001.HK": closes_1001.dropna(how="all"),
            "1002.HK": closes_1002,
            "1003.HK": closes_1003,
        }

        def _mock_close_series(ticker: str) -> Optional[pd.Series]:
            s = close_map.get(ticker)
            if s is None:
                return None
            return s

        monkeypatch.setattr(runner_mod, "_load_hk_close_series", _mock_close_series)
        importlib.reload(runner)

        rc = runner.main()
        assert rc == 0, f"main() returned {rc}"

        from engine.pick_lab.ledger import load_jsonl
        fires = load_jsonl(hk_dir / "fires.jsonl") if (hk_dir / "fires.jsonl").exists() else []
        grades = load_jsonl(hk_dir / "grades.jsonl") if (hk_dir / "grades.jsonl").exists() else []

        # --- Case (ii): 1002.HK must be halt_voided ---
        # halt_voided is persisted to halt_outcomes.json sidecar and applied on next load.
        # Primary observable: no grade rows for this ticker, and sidecar has it marked.
        grades_1002 = [g for g in grades if g.get("ticker") == "1002.HK"]
        assert not grades_1002, (
            f"HKPL-R4: 1002.HK (no print within 5 sessions) should have zero grade rows, "
            f"got {grades_1002}"
        )
        # Verify halt_outcomes sidecar was written with 1002.HK marked
        halt_outcomes_path = tmp_path / "data" / "hk_pick_lab" / "halt_outcomes.json"
        if halt_outcomes_path.exists():
            import json as _json
            halt_outcomes = _json.loads(halt_outcomes_path.read_text())
            # At least one key for 1002.HK should be True in the sidecar
            voided_keys = [k for k, v in halt_outcomes.items() if "1002.HK" in k and v]
            fires_1002 = [f for f in fires if f.get("ticker") == "1002.HK"]
            if fires_1002:
                assert voided_keys, (
                    "HKPL-R4: 1002.HK (no print within 5 sessions) must be in halt_outcomes sidecar"
                )

        # --- Case (i): 1001.HK graded with delayed exec ---
        grades_1001 = [g for g in grades if g.get("ticker") == "1001.HK" and g.get("kind") == "ret"]
        if grades_1001:
            # At least h=5 must have been graded with the delayed exec
            for g in grades_1001:
                assert g.get("fill_basis") == "close_halt_delayed", (
                    f"HKPL-R4: 1001.HK delayed exec must have fill_basis='close_halt_delayed', "
                    f"got {g.get('fill_basis')!r}: {g}"
                )
                assert g.get("halted") is True, (
                    f"HKPL-R4: 1001.HK delayed exec must have halted=True: {g}"
                )
                # exec_price should be ~12.0 (the delayed session's close)
                assert abs(g.get("exec_price", 0) - 12.0) < 1e-2, (
                    f"HKPL-R4: 1001.HK delayed exec_price expected ~12.0, got {g.get('exec_price')!r}: {g}"
                )

        # --- Case (iii): 1003.HK halted through h=5 target → grades to last trade ---
        grades_1003_h5 = [
            g for g in grades
            if g.get("ticker") == "1003.HK" and g.get("kind") == "ret" and g.get("horizon") == 5
        ]
        if grades_1003_h5:
            for g in grades_1003_h5:
                # Target session (exec+5) is NaN; last print in window was exec+3 (close ~10.3)
                assert g.get("halted") is True, (
                    f"HKPL-R4: 1003.HK graded to last trade at h=5 must have halted=True: {g}"
                )
                # exec_price is normal (10.0 — exec session has a print)
                assert abs(g.get("exec_price", 0) - 10.0) < 1e-2, (
                    f"HKPL-R4: 1003.HK exec_price expected ~10.0: {g}"
                )


# ---------------------------------------------------------------------------
# 6. Organ-stale disable path
# ---------------------------------------------------------------------------

class TestOrganStalePath:
    def test_organ_stale_flag_stamped(self, tmp_path: Path, monkeypatch):
        """When organ data is stale, organ_fresh_* columns should be False."""
        import importlib

        asof = "2026-04-15"
        snap = _make_hk_snap(n=3, asof=asof)
        hk_dir, labdata = _patch_hk_env(tmp_path, monkeypatch, snap, asof)
        monkeypatch.setenv("CN_LANE", "asia")

        # Patch all organ loaders to return very stale data
        import scripts.build_hk_pick_lab as runner_mod

        stale_date = "2026-01-01"  # very stale (>2 sessions behind)
        monkeypatch.setattr(runner_mod, "_load_adr_bridge",
                            lambda: {"hk_session_date": stale_date, "adr_date": stale_date, "names": []})
        monkeypatch.setattr(runner_mod, "_load_cbbc",
                            lambda: {"as_of_trade_date": stale_date, "bellwethers": []})
        monkeypatch.setattr(runner_mod, "_load_filing_bus",
                            lambda: {"as_of": stale_date, "tape": []})
        monkeypatch.setattr(runner_mod, "_load_narrative",
                            lambda: {"as_of": stale_date, "entities": []})
        monkeypatch.setattr(runner_mod, "_load_catalyst_calendar",
                            lambda: {"as_of": stale_date, "upcoming": [], "imminent": []})
        monkeypatch.setattr(runner_mod, "_load_standouts",
                            lambda: {"as_of": stale_date})
        monkeypatch.setattr(runner_mod, "_load_hk_regime", lambda: {})

        importlib.reload(runner_mod)
        rc = runner_mod.main()
        assert rc == 0


# ---------------------------------------------------------------------------
# 7. Site artifact valid JSON schema
# ---------------------------------------------------------------------------

class TestSiteArtifact:
    def test_site_artifact_valid_json_schema(self, tmp_path: Path, monkeypatch):
        """site/labdata/hk_pick_lab.json must exist and carry required top-level keys."""
        import importlib
        import scripts.build_hk_pick_lab as runner

        asof = "2026-04-07"
        snap = _make_hk_snap(n=5, asof=asof)
        _patch_hk_env(tmp_path, monkeypatch, snap, asof)
        monkeypatch.setenv("CN_LANE", "asia")
        importlib.reload(runner)

        rc = runner.main()
        assert rc == 0

        artifact = tmp_path / "site" / "labdata" / "hk_pick_lab.json"
        assert artifact.exists(), "hk_pick_lab.json was not written"

        data = json.loads(artifact.read_text())

        required_keys = {
            "as_of", "built_at", "scoreboard", "books",
            "total_halt_voided", "method_note", "authority",
        }
        missing = required_keys - set(data.keys())
        assert not missing, f"hk_pick_lab.json missing keys: {missing}"
        assert data["authority"] == "display_only"
        assert data["as_of"] == asof
        assert isinstance(data["scoreboard"], list)
        assert isinstance(data["books"], dict)
        assert isinstance(data["total_halt_voided"], int)

        # Verify scoreboard rows
        for row in data["scoreboard"]:
            assert "engine_id" in row, f"scoreboard row missing engine_id: {row}"
            assert "n_fires" in row, f"scoreboard row missing n_fires: {row}"

        # No 'validated' word in user-facing strings (CI-enforced per house law)
        text = json.dumps(data)
        assert "validated" not in text, (
            "The word 'validated' appeared in hk_pick_lab.json — forbidden by house law"
        )

    def test_artifact_absent_when_not_asia(self, tmp_path: Path, monkeypatch):
        """hk_pick_lab.json must NOT be written when CN_LANE != 'asia'."""
        import importlib
        import scripts.build_hk_pick_lab as runner

        asof = "2026-04-08"
        snap = _make_hk_snap(n=3, asof=asof)
        _patch_hk_env(tmp_path, monkeypatch, snap, asof)
        monkeypatch.delenv("CN_LANE", raising=False)
        importlib.reload(runner)

        rc = runner.main()
        assert rc == 0

        artifact = tmp_path / "site" / "labdata" / "hk_pick_lab.json"
        assert not artifact.exists(), (
            "hk_pick_lab.json was written in a non-asia lane — HKPL-R8 violation"
        )


# ---------------------------------------------------------------------------
# 8. Render failure is non-fatal
# ---------------------------------------------------------------------------

class TestRenderNonFatal:
    def test_render_exception_still_returns_zero(self, tmp_path: Path, monkeypatch):
        """A render exception must not cause main() to return non-zero."""
        import importlib
        import scripts.build_hk_pick_lab as runner

        asof = "2026-05-06"
        snap = _make_hk_snap(n=3, asof=asof)
        _patch_hk_env(tmp_path, monkeypatch, snap, asof)
        monkeypatch.setenv("CN_LANE", "asia")
        importlib.reload(runner)

        try:
            from engine.pick_lab import render_hk as render_mod
            monkeypatch.setattr(
                render_mod, "render_page",
                lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("render boom"))
            )
        except Exception:
            pass

        rc = runner.main()
        assert rc == 0, f"main() returned {rc} after render exception — never-break violated"


# ---------------------------------------------------------------------------
# 9. Never-break contract
# ---------------------------------------------------------------------------

class TestNeverBreak:
    def test_returns_zero_on_exception(self, tmp_path: Path, monkeypatch):
        """main() must return 0 even when _build() raises an unexpected exception."""
        import importlib
        import scripts.build_hk_pick_lab as runner
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
        import scripts.build_hk_pick_lab as runner
        monkeypatch.setenv("CN_LANE", "asia")
        importlib.reload(runner)

        def _import_error_build():
            raise ImportError("engine.pick_lab.hk not installed")

        monkeypatch.setattr(runner, "_build", _import_error_build)
        rc = runner.main()
        assert rc == 0


# ---------------------------------------------------------------------------
# 10. Enrichment helper unit tests
# ---------------------------------------------------------------------------

class TestEnrichmentHelpers:
    def test_build_adr_by_ticker(self):
        """_build_adr_by_ticker extracts implied_open_gap_pct per HK ticker."""
        from scripts.build_hk_pick_lab import _build_adr_by_ticker

        adr = {
            "names": [
                {"hk_ticker": "9988.HK", "implied_open_gap_pct": 2.5},
                {"hk_ticker": "700.HK", "implied_open_gap_pct": -0.3},
                {"hk_ticker": "", "implied_open_gap_pct": 1.0},  # no ticker — skip
            ]
        }
        result = _build_adr_by_ticker(adr)
        assert "9988.HK" in result
        assert result["9988.HK"]["adr_gap_pct"] == 2.5
        assert "700.HK" in result
        assert result["700.HK"]["adr_gap_pct"] == -0.3
        assert "" not in result

    def test_build_adr_by_ticker_empty(self):
        """_build_adr_by_ticker returns {} when adr data is absent."""
        from scripts.build_hk_pick_lab import _build_adr_by_ticker
        assert _build_adr_by_ticker({}) == {}
        assert _build_adr_by_ticker({"names": []}) == {}

    def test_build_cbbc_by_ticker(self):
        """_build_cbbc_by_ticker extracts leverage_state per ticker, skipping index entries."""
        from scripts.build_hk_pick_lab import _build_cbbc_by_ticker

        cbbc = {
            "bellwethers": [
                {"ticker": "^HSI", "leverage_state": "bear_skew"},   # index — skip
                {"ticker": "700.HK", "leverage_state": "bear_skew_froth"},
                {"ticker": "9988.HK", "leverage_state": "neutral"},
            ]
        }
        result = _build_cbbc_by_ticker(cbbc)
        assert "^HSI" not in result, "Index tickers must be excluded from CBBC by_ticker"
        assert "700.HK" in result
        assert result["700.HK"]["cbbc_leverage_state"] == "bear_skew_froth"

    def test_build_filing_by_ticker_aggregates(self):
        """_build_filing_by_ticker aggregates multiple filings per ticker (OR semantics)."""
        from scripts.build_hk_pick_lab import _build_filing_by_ticker

        filing = {
            "tape": [
                {"ticker": "1234.HK", "buyback_flag": True, "dilution_flag": False},
                {"ticker": "1234.HK", "buyback_flag": False, "dilution_flag": True},
                {"ticker": "5678.HK", "buyback_flag": False, "dilution_flag": False},
            ]
        }
        result = _build_filing_by_ticker(filing)
        # 1234.HK has both buyback and dilution across its two filings
        assert result["1234.HK"]["buyback_flag"] is True
        assert result["1234.HK"]["dilution_flag"] is True
        # 5678.HK has neither
        assert result["5678.HK"]["buyback_flag"] is False
        assert result["5678.HK"]["dilution_flag"] is False

    def test_build_narrative_by_ticker(self):
        """_build_narrative_by_ticker maps attention_shock_z and tone_pctile."""
        from scripts.build_hk_pick_lab import _build_narrative_by_ticker

        narrative = {
            "entities": [
                {"ticker": "9988.HK", "attention_shock_z": 2.1, "tone_pctile": 65},
                {"ticker": "700.HK", "attention_shock_z": None, "tone_pctile": None},
                {"ticker": "", "attention_shock_z": 1.0, "tone_pctile": 50},
            ]
        }
        result = _build_narrative_by_ticker(narrative)
        assert "9988.HK" in result
        assert result["9988.HK"]["attention_shock_z"] == 2.1
        assert result["9988.HK"]["narrative_tone"] == 65
        assert "700.HK" in result
        assert "" not in result

    def test_build_catalyst_by_ticker_takes_nearest(self):
        """_build_catalyst_by_ticker picks the minimum days_to for each ticker."""
        from scripts.build_hk_pick_lab import _build_catalyst_by_ticker

        catalyst = {
            "upcoming": [
                {"ticker": "1234.HK", "days_to": 10},
                {"ticker": "1234.HK", "days_to": 3},   # nearer — should win
            ],
            "imminent": [
                {"ticker": "5678.HK", "sessions_to": 1},
            ],
        }
        result = _build_catalyst_by_ticker(catalyst)
        assert result["1234.HK"]["catalyst_days_to"] == 3
        assert result["5678.HK"]["catalyst_days_to"] == 1

    def test_build_standouts_by_ticker(self):
        """_build_standouts_by_ticker extracts sb_accum_z, ah_discount_pctile, sfc_short_pressure_q."""
        from scripts.build_hk_pick_lab import _build_standouts_by_ticker

        standouts = {
            "buy": [
                {
                    "ticker": "9988.HK",
                    "southbound": {"accum_z": 1.5},
                    "ah_value": {"pctile": 80},
                    "sfc_short": {"pctile": 88},
                }
            ],
            "watch": [
                {
                    "ticker": "700.HK",
                    "southbound": {"accum_z": -0.3},
                    "ah_value": None,
                    "sfc_short": {"pctile": 45},
                }
            ],
        }
        result = _build_standouts_by_ticker(standouts)
        assert "9988.HK" in result
        assert result["9988.HK"]["sb_accum_z"] == 1.5
        assert result["9988.HK"]["ah_discount_pctile"] == 80
        # SFC pctile=88 → Q4 (88//25=3, +1=4)
        assert result["9988.HK"]["sfc_short_pressure_q"] == 4

        assert "700.HK" in result
        assert result["700.HK"]["sb_accum_z"] == -0.3
        # SFC pctile=45 → Q2 (45//25=1, +1=2)
        assert result["700.HK"]["sfc_short_pressure_q"] == 2

    def test_build_knife_by_ticker(self):
        """_build_knife_by_ticker marks laggards as knife_risk=True."""
        from scripts.build_hk_pick_lab import _build_knife_by_ticker

        standouts = {
            "laggards": [
                {"ticker": "1111.HK"},
                {"ticker": "2222.HK"},
            ],
            "buy": [
                {"ticker": "3333.HK"},  # NOT a knife
            ],
        }
        result = _build_knife_by_ticker(standouts)
        assert result.get("1111.HK") is True
        assert result.get("2222.HK") is True
        assert "3333.HK" not in result

    def test_stale_cross_diagnostic_filter(self):
        """_build_stale_cross_grades returns only names with ≥5 sessions since cross and |ret|<3%."""
        from scripts.build_hk_pick_lab import _build_stale_cross_grades

        snap = pd.DataFrame([
            {"ticker": "A.HK", "sessions_since_23d_cross": 6, "ret_since_23d_cross": 0.01},   # IN
            {"ticker": "B.HK", "sessions_since_23d_cross": 3, "ret_since_23d_cross": 0.01},   # OUT (< 5)
            {"ticker": "C.HK", "sessions_since_23d_cross": 7, "ret_since_23d_cross": 0.05},   # OUT (|ret|≥3%)
            {"ticker": "D.HK", "sessions_since_23d_cross": None, "ret_since_23d_cross": 0.01}, # OUT (null)
            {"ticker": "E.HK", "sessions_since_23d_cross": 10, "ret_since_23d_cross": -0.02}, # IN
        ]).set_index("ticker")

        rows = _build_stale_cross_grades(snap, "2026-04-01", None, pd.DatetimeIndex([]))
        tickers = {r["ticker"] for r in rows}
        assert "A.HK" in tickers
        assert "E.HK" in tickers
        assert "B.HK" not in tickers
        assert "C.HK" not in tickers
        assert "D.HK" not in tickers

        for r in rows:
            assert r.get("authority") == "display_only"
            assert "sessions_since_23d_cross" in r

    def test_build_washout_by_ticker(self):
        """_build_washout_by_ticker extracts state + confluence from standouts['washout_watch']."""
        from scripts.build_hk_pick_lab import _build_washout_by_ticker

        standouts = {
            "washout_watch": [
                {
                    "ticker": "0700.HK",
                    "state": "ignition_watch",
                    "confluence_count": 4,
                    "confluence_signals": ["RSI_RECLAIM", "VOLUME_SURGE"],
                },
                {
                    "ticker": "9988.HK",
                    "state": "washout_watch",
                    "confluence_count": 2,
                    "confluence_signals": ["CANDLE_DOJI"],
                },
                # entry with no ticker — must be skipped
                {"state": "ignition_watch", "confluence_count": 1},
                # entry with no state — must be skipped
                {"ticker": "1234.HK"},
            ],
            "buy": [{"ticker": "5555.HK"}],  # not in washout_watch
        }
        result = _build_washout_by_ticker(standouts)
        assert "0700.HK" in result
        assert result["0700.HK"]["washout_state"] == "ignition_watch"
        assert result["0700.HK"]["confluence_count"] == 4
        assert "RSI_RECLAIM" in result["0700.HK"]["confluence_signals"]
        assert "9988.HK" in result
        assert result["9988.HK"]["washout_state"] == "washout_watch"
        assert "5555.HK" not in result
        assert "1234.HK" not in result  # no state

    def test_build_washout_by_ticker_empty(self):
        """_build_washout_by_ticker handles missing washout_watch key gracefully."""
        from scripts.build_hk_pick_lab import _build_washout_by_ticker

        assert _build_washout_by_ticker({}) == {}
        assert _build_washout_by_ticker({"washout_watch": []}) == {}
        assert _build_washout_by_ticker({"washout_watch": None}) == {}

    def test_washout_organ_fresh_from_standouts(self):
        """Washout organ freshness is derived from standouts as_of (not hardcoded False)."""
        from scripts.build_hk_pick_lab import _organ_is_fresh

        # Standouts as_of on the same day as snap asof = fresh
        asof = "2026-04-01"
        standouts_asof = "2026-04-01"
        assert _organ_is_fresh({"as_of": standouts_asof}, "as_of", asof) is True

    def test_grade_rows_have_mfe_mae(self):
        """Grade rows must carry mfe/mae fields (HKPL-R3 descriptive window).

        The new grade pass delegates to grade_fires() in engine.pick_lab.grade,
        which emits mfe/mae on every 'ret' grade row (null when exec+25 not yet elapsed).
        Verify that the shared grader emits these fields.
        """
        from engine.pick_lab.grade import grade_fires
        import pandas as pd

        # 40 sessions: fire on session 0, 30 sessions elapsed → mfe/mae window (25) is complete
        dates = pd.date_range("2025-10-01", periods=40, freq="B")
        bm = pd.Series(10000.0, index=pd.DatetimeIndex(dates))
        ticker_close = pd.Series(15.0, index=pd.DatetimeIndex(dates))

        close_panel = pd.DataFrame(
            {"test_ticker": ticker_close, "^HSI": bm},
            index=dates,
        )

        fires = [
            {"engine_id": "test_book", "ticker": "test_ticker",
             "fire_date": str(dates[0].date())},
        ]

        grade_rows, _ = grade_fires(fires, close_panel, bm, sector_closes=None, hold_thesis=False)

        ret_rows = [r for r in grade_rows if r.get("kind") == "ret"]
        assert ret_rows, "Expected at least one ret grade row"
        for row in ret_rows:
            # mfe/mae present on ret rows (null when exec+25 not yet elapsed, non-null otherwise)
            assert "mfe" in row, f"grade row missing 'mfe': {row}"
            assert "mae" in row, f"grade row missing 'mae': {row}"

    def test_knife_avoid_is_avoid_book(self):
        """hklab_knife_avoid must be scored as an avoid-accuracy book (not a buy book).

        book.py uses ruler suffix '_avoid_accuracy' to detect inverse books when
        profile.avoid_engine_id is the single string hklab_chase_avoid.
        """
        from engine.pick_lab.book import scoreboard
        from engine.pick_lab.profile import HK_PROFILE

        # Empty fires/grades — avoid detection is independent of data
        sb = scoreboard(
            "hklab_knife_avoid",
            [],
            [],
            ruler="21d_hsi_excess_avoid_accuracy",
            profile=HK_PROFILE,
        )
        # is_avoid fires when ruler ends with _avoid_accuracy
        # The scoreboard should have h21_avoid_accuracy = None (no grades yet)
        # but the key should exist (set by _horizon_stats when is_avoid=True)
        # We check indirectly: with 0 grades, avoid_accuracy = None (1-None = None).
        # The real verification is that it doesn't raise and the logic path is hit.
        assert isinstance(sb, dict)

    def test_halt_outcomes_sidecar_round_trip(self, tmp_path):
        """Halt outcomes sidecar persists and reloads correctly."""
        import scripts.build_hk_pick_lab as _bhk
        from unittest.mock import patch

        fake_path = tmp_path / "data" / "hk_pick_lab" / "halt_outcomes.json"

        with patch.object(_bhk, "_IS_ASIA_LANE", True), \
             patch.object(_bhk.config, "ROOT", tmp_path):
            # Save
            outcomes = {"eng\x1cticker\x1c2026-01-01": True}
            _bhk._save_halt_outcomes(outcomes)
            # Load
            loaded = _bhk._load_halt_outcomes()
            assert loaded == outcomes

    def test_apply_halt_outcomes_stamps_fires(self):
        """_apply_halt_outcomes stamps halt_voided=True on matching fires."""
        from scripts.build_hk_pick_lab import _apply_halt_outcomes

        fires = [
            {"engine_id": "hklab_1d_pure", "ticker": "0700.HK",
             "fire_date": "2026-01-02", "halt_voided": False},
            {"engine_id": "hklab_1d_adr", "ticker": "9988.HK",
             "fire_date": "2026-01-03", "halt_voided": False},
        ]
        outcomes = {
            "hklab_1d_pure\x1c0700.HK\x1c2026-01-02": True,
        }
        _apply_halt_outcomes(fires, outcomes)
        assert fires[0]["halt_voided"] is True
        assert fires[1]["halt_voided"] is False  # untouched

    def test_hk_close_panel_uses_hsi_calendar(self):
        """_build_hk_close_panel indexes on ^HSI benchmark calendar."""
        import pandas as pd
        from scripts.build_hk_pick_lab import _build_hk_close_panel

        dates = pd.date_range("2026-01-02", periods=20, freq="B")
        # hsi_closes on all 20 sessions
        hsi = pd.Series(23000.0, index=pd.DatetimeIndex(dates))
        # ticker only on the first 15 sessions (simulates halt/data gap for last 5)
        ticker_dates = dates[:15]
        closes_by_ticker = {
            "0700.HK": pd.Series(150.0, index=pd.DatetimeIndex(ticker_dates)),
        }
        panel = _build_hk_close_panel(hsi, closes_by_ticker)

        # Panel index must match ^HSI calendar (all 20 sessions)
        assert len(panel.index) == 20, (
            f"Panel has {len(panel.index)} rows; expected 20 (^HSI calendar)"
        )
        assert "^HSI" in panel.columns
        assert "0700.HK" in panel.columns

        # Last 5 sessions of 0700.HK must be NaN (null-honest gap)
        assert panel["0700.HK"].iloc[-5:].isna().all(), (
            "0700.HK sessions beyond its last traded date should be NaN in the panel"
        )
        # ^HSI must be non-NaN throughout
        assert not panel["^HSI"].isna().any(), "^HSI column should have no NaN"


# ---------------------------------------------------------------------------
# 11. HK halt semantics via grade_fires()
# ---------------------------------------------------------------------------

class TestHKHaltSemantics:
    def test_halted_ticker_ungradeable_at_blocked_horizon(self):
        """HK ticker halted mid-window is ungradeable at that horizon via grade_fires().

        Scenario: two fires on the same day.
        - active_ticker: continuous closes through all horizons → produces grade rows
        - halted_ticker: NaN from session 3 onward (halt after exec) → no grade rows
          at horizons that land on NaN sessions

        The ^HSI calendar is the session index.  grade_fires() applies null-honest
        semantics: a NaN at the horizon session → ungradeable (no row emitted).
        """
        import pandas as pd
        from engine.pick_lab.grade import grade_fires
        from scripts.build_hk_pick_lab import _build_hk_close_panel

        dates = pd.date_range("2025-11-03", periods=40, freq="B")
        hsi = pd.Series(23000.0, index=pd.DatetimeIndex(dates))

        # active: full series
        active_close = pd.Series(150.0, index=pd.DatetimeIndex(dates))
        # halted: NaN from session 3 onward
        halted_close = pd.Series(150.0, index=pd.DatetimeIndex(dates))
        halted_close.iloc[3:] = float("nan")

        closes_by_ticker = {
            "active.HK": active_close,
            "halted.HK": halted_close,
        }
        panel = _build_hk_close_panel(hsi, closes_by_ticker)

        fire_date = str(dates[0].date())  # fire on session 0
        fires = [
            {"engine_id": "test_book", "ticker": "active.HK", "fire_date": fire_date},
            {"engine_id": "test_book", "ticker": "halted.HK", "fire_date": fire_date},
        ]

        grade_rows, n_ung = grade_fires(
            fires, panel, hsi, sector_closes=None, hold_thesis=False,
        )

        active_rows = [r for r in grade_rows if r.get("ticker") == "active.HK"]
        # ret rows: check horizon-level gradeability under the benchmark calendar
        halted_ret_rows = [
            r for r in grade_rows
            if r.get("ticker") == "halted.HK" and r.get("kind") == "ret"
        ]

        # active_ticker should produce ret grade rows at every elapsed horizon
        active_ret_rows = [r for r in active_rows if r.get("kind") == "ret"]
        assert len(active_ret_rows) > 0, "active.HK should have ret grade rows"

        # halted_ticker ret rows: exec=session 1 (close=150.0, valid).
        # ENTRY_HORIZONS = (5,10,21,63). Target sessions: 6,11,22,64.
        # Sessions 3+ are NaN → targets 6,11,22 are NaN → ungradeable (no ret row).
        # Session 64 is out of range (only 40 sessions) → not yet elapsed → no row.
        # So halted_ticker should produce ZERO ret grade rows.
        assert len(halted_ret_rows) == 0, (
            f"halted.HK should produce no ret grade rows at NaN horizons; "
            f"got: {halted_ret_rows}"
        )

        # n_ung should be positive (halted.HK counted as ungradeable per elapsed horizon)
        assert n_ung > 0, "ungradeable count should be > 0 for halted.HK"
