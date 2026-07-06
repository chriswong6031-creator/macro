"""Tests for scripts/audit_options_entry_coverage.py — NEXT3 W-OC options entry coverage audit.

Tests use synthetic fixtures (tmp_path) — no real data stores required.

Coverage:
  - Feature coverage from state.parquet (non-null counts, shares, ticker coverage)
  - Per-family stamp coverage + weekly fire counts from board ledger
  - Readiness forecast gating: <14 days post-W-C → forecast=unknown
  - Readiness forecast gating: >=14 days post-W-C → projected date or unknown
  - Absent-store cases: state absent, gate absent, ledger absent, all absent
  - Structural-null ledger: iv_rank_252, pin_risk gate, gamma_regime constancy
  - Consistency rows: BH test-count drift, stale as_of ages, accrual audit status
  - run_as_collect_step never raises
  - collect.py wiring: both audit_options_accrual and audit_options_entry_coverage wired
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

import scripts.audit_options_entry_coverage as aoc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state_parquet(path: Path, n: int = 5) -> pd.DataFrame:
    """Create a synthetic state.parquet with some nulls."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tickers = [f"TICK{i}" for i in range(n)]
    # Build gamma_regime: mix of 'long', 'short', None — always exactly n entries
    gamma: list = []
    for i in range(n):
        if i % 3 == 0:
            gamma.append("long")
        elif i % 3 == 1:
            gamma.append("short")
        else:
            gamma.append(None)
    df = pd.DataFrame({
        "as_of": ["2026-07-05"] * n,
        "ticker": tickers,
        "iv30": [20.0] * (n - 1) + [None],
        "iv_rank_252": [None] * n,         # always null (A9)
        "opex_days": [11] * n,
        "pin_risk": [None] * n,            # always null (opex_days>5)
        "gamma_regime": gamma,
        "gamma_regime_structurally_constant": [True] * n,
        "evidence_quality": ["full"] * n,
    })
    df.to_parquet(path, index=False)
    return df


def _make_gate_json(path: Path, n_cond: int = 5, n_base: int = 3) -> dict:
    """Create a synthetic gate.json."""
    path.parent.mkdir(parents=True, exist_ok=True)
    gate = {
        "schema": "options_entry.gate.v2",
        "generated_at": "2026-07-05 10:00 UTC",
        "scored": False,
        "status": "building_history",
        "n_ledger_rows": 100,
        "n_stamped_rows": 50,
        "fdr_family": {
            "alpha": 0.1,
            "method": "Benjamini-Hochberg",
            "family_size": 22,
            "description": "22 tests total",
        },
        "per_family_status": {
            "S-IVR": "building_history",
            "S-DOI": "building_history",
            "S-VOI": "building_history",
        },
        "tests": {
            "S-IVR": {"bucket": "S-IVR", "n_cond": 0, "n_base": 0, "ready": False,
                      "note": "null until A9 backfill"},
            "S-DOI": {"bucket": "S-DOI", "n_cond": 0, "n_base": 0, "ready": False,
                      "note": "no chain history"},
            "S-VOI": {"bucket": "S-VOI", "n_cond": n_cond, "n_base": n_base, "ready": False},
        },
    }
    path.write_text(json.dumps(gate))
    return gate


def _make_ledger_parquet(
    path: Path,
    n_rows: int = 10,
    has_opt_stamp: bool = True,
    as_of_dates: list[str] | None = None,
) -> pd.DataFrame:
    """Create a synthetic board ledger parquet with optional opt_ stamp columns."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if as_of_dates is None:
        # Default: all pre-W-C (before 2026-07-05)
        as_of_dates = ["2026-06-15"] * n_rows
    assert len(as_of_dates) == n_rows

    df = pd.DataFrame({
        "as_of": as_of_dates,
        "ticker": [f"T{i}" for i in range(n_rows)],
        "opt_gamma_regime": (["long"] * n_rows if has_opt_stamp else [None] * n_rows),
        "opt_iv30": ([25.0] * n_rows if has_opt_stamp else [None] * n_rows),
        "opt_voi_flag": ([True] * (n_rows // 2) + [None] * (n_rows - n_rows // 2) if has_opt_stamp else [None] * n_rows),
        "opt_iv_rank_252": [None] * n_rows,    # always null
        "opt_opex_days": [11] * n_rows,
        "opt_pin_risk": [None] * n_rows,
        "opt_doi_slope_5d": [None] * n_rows,
        "opt_ivspread_rel": [None] * n_rows,
        "opt_skew": [None] * n_rows,
        "opt_skew_5d_chg": [None] * n_rows,
    })
    df.to_parquet(path, index=False)
    return df


# ---------------------------------------------------------------------------
# Section 1: feature coverage
# ---------------------------------------------------------------------------

class TestFeatureCoverage:
    def test_non_null_counts_correct(self, tmp_path: Path) -> None:
        state_p = tmp_path / "data" / "options_entry" / "state.parquet"
        _make_state_parquet(state_p, n=5)
        df = pd.read_parquet(state_p)
        result = aoc._feature_coverage(df)

        assert result["n_rows"] == 5
        assert result["n_features"] > 0

        # iv30: 4 non-null out of 5
        iv30 = next(f for f in result["features"] if f["feature"] == "iv30")
        assert iv30["n_nonnull"] == 4
        assert abs(iv30["share_nonnull"] - 0.8) < 0.01

        # iv_rank_252: always null
        ivr = next(f for f in result["features"] if f["feature"] == "iv_rank_252")
        assert ivr["n_nonnull"] == 0
        assert ivr["share_nonnull"] == 0.0

    def test_ticker_coverage_tiers(self, tmp_path: Path) -> None:
        state_p = tmp_path / "data" / "options_entry" / "state.parquet"
        _make_state_parquet(state_p, n=10)
        df = pd.read_parquet(state_p)
        result = aoc._feature_coverage(df)

        tc = result["ticker_coverage"]
        assert "n_tickers" in tc
        assert tc["n_tickers"] == 10

    def test_empty_dataframe(self) -> None:
        df = pd.DataFrame({"ticker": [], "as_of": [], "iv30": []})
        result = aoc._feature_coverage(df)
        assert result["n_rows"] == 0
        # iv30 feature: n_nonnull=0, share=0.0
        iv30 = next((f for f in result["features"] if f["feature"] == "iv30"), None)
        assert iv30 is not None
        assert iv30["n_nonnull"] == 0
        assert iv30["share_nonnull"] == 0.0


# ---------------------------------------------------------------------------
# Section 2+3: family stamp coverage + readiness forecast
# ---------------------------------------------------------------------------

class TestFamilyStampCoverage:
    def _run_family_section(
        self,
        tmp_path: Path,
        n_ledger_rows: int = 20,
        has_opt_stamp: bool = True,
        as_of_dates: list[str] | None = None,
        n_cond: int = 5,
        today: date | None = None,
    ) -> list[dict]:
        gate_p = tmp_path / "data" / "options_entry" / "gate.json"
        ledger_p = tmp_path / "data" / "us_board_ledger" / "retro_grades.parquet"
        _make_gate_json(gate_p, n_cond=n_cond)
        if as_of_dates is None:
            as_of_dates = ["2026-06-15"] * n_ledger_rows
        _make_ledger_parquet(ledger_p, n_rows=n_ledger_rows, has_opt_stamp=has_opt_stamp,
                              as_of_dates=as_of_dates)
        ledger_df = pd.read_parquet(ledger_p)
        gate = json.loads(gate_p.read_text())
        ref_today = today or date(2026, 7, 6)
        return aoc._family_stamp_coverage(ledger_df, gate, ref_today)

    def test_families_emitted(self, tmp_path: Path) -> None:
        result = self._run_family_section(tmp_path)
        families = [r["family"] for r in result]
        assert "S-VOI" in families
        assert "S-IVR" in families
        assert "S-DOI" in families

    def test_n_cond_from_gate(self, tmp_path: Path) -> None:
        """n_cond should match what gate.json tests block reports."""
        result = self._run_family_section(tmp_path, n_cond=17)
        voi = next(r for r in result if r["family"] == "S-VOI")
        assert voi["n_cond"] == 17

    def test_forecast_unknown_when_insufficient_post_wc_history(self, tmp_path: Path) -> None:
        """All ledger rows pre-W-C → forecast must be 'unknown'."""
        result = self._run_family_section(
            tmp_path,
            as_of_dates=["2026-06-20"] * 20,
            today=date(2026, 7, 6),  # only 1 day post-W-C (< 14 day threshold)
        )
        for row in result:
            fc = row["readiness_forecast"]
            assert fc["forecast"] == "unknown", (
                f"Family {row['family']}: expected 'unknown' forecast but got {fc['forecast']!r}"
            )

    def test_forecast_projected_when_sufficient_post_wc_history(self, tmp_path: Path) -> None:
        """With post-W-C stamped fires and sufficient history → S-VOI gets a concrete date forecast.

        Fixture guarantees:
        - 30 post-W-C ledger rows spanning 2026-07-15 to 2026-08-01 (17 days > 14d threshold)
        - has_opt_stamp=True → opt_voi_flag non-null for n_rows//2 = 15 rows
        - n_cond=5 (< 30 readiness target) so already_ready is not triggered
        S-VOI maps to opt_voi_flag; cond_hit_share = 15/30 = 0.5 > 0 → forecast must be "date"
        with a concrete forecast_date string.
        """
        # Create ledger rows post-W-C spanning >=14 calendar days (2026-07-15 to 2026-08-01)
        post_wc_dates = ["2026-07-15"] * 20 + ["2026-08-01"] * 10
        ref_today = date(2026, 9, 1)  # 58 days after W-C cutoff (2026-07-05)
        result = self._run_family_section(
            tmp_path,
            n_ledger_rows=30,
            has_opt_stamp=True,
            as_of_dates=post_wc_dates,
            today=ref_today,
            n_cond=5,
        )
        # S-VOI uses opt_voi_flag — non-null for rows 0..14 (15 of 30 → hit_share=0.5)
        voi = next(r for r in result if r["family"] == "S-VOI")
        fc = voi["readiness_forecast"]
        assert fc["forecast"] == "date", (
            f"S-VOI with n_cond=5, 30 post-W-C fires, cond_hit_share=0.5 should yield "
            f"'date' forecast but got {fc!r}"
        )
        assert "forecast_date" in fc, (
            f"'date' forecast must include a 'forecast_date' key, got {fc!r}"
        )
        # forecast_date must be an ISO date string parseable by date.fromisoformat
        try:
            projected = date.fromisoformat(fc["forecast_date"])
        except (ValueError, TypeError) as exc:
            raise AssertionError(f"forecast_date {fc['forecast_date']!r} is not a valid ISO date: {exc}") from exc
        assert projected > ref_today, (
            f"Projected date {projected} must be in the future relative to ref_today {ref_today}"
        )

    def test_forecast_already_ready_when_n_cond_met(self, tmp_path: Path) -> None:
        """n_cond >= 30 → forecast = already_ready."""
        post_wc_dates = ["2026-07-20"] * 20
        ref_today = date(2026, 9, 1)
        result = self._run_family_section(
            tmp_path,
            n_ledger_rows=20,
            has_opt_stamp=True,
            as_of_dates=post_wc_dates,
            today=ref_today,
            n_cond=30,  # already met
        )
        voi = next(r for r in result if r["family"] == "S-VOI")
        fc = voi["readiness_forecast"]
        assert fc["forecast"] == "already_ready"

    def test_weekly_fires_keys_are_iso_week_strings(self, tmp_path: Path) -> None:
        result = self._run_family_section(tmp_path)
        for row in result:
            for key in row["weekly_fires"].keys():
                # Should look like "2026-W25" format
                assert "-W" in key, f"Unexpected weekly_fires key: {key!r}"


# ---------------------------------------------------------------------------
# Absent-store cases
# ---------------------------------------------------------------------------

class TestAbsentStores:
    def test_state_absent(self, tmp_path: Path) -> None:
        """state.parquet absent → run() completes; absent_stores contains state path."""
        gate_p = tmp_path / "data" / "options_entry" / "gate.json"
        ledger_p = tmp_path / "data" / "us_board_ledger" / "retro_grades.parquet"
        _make_gate_json(gate_p)
        _make_ledger_parquet(ledger_p)
        result = aoc.run(root=tmp_path, write=False)
        assert "data/options_entry/state.parquet" in result["absent_stores"]
        assert result["feature_coverage"]["absent"] is True

    def test_gate_absent(self, tmp_path: Path) -> None:
        """gate.json absent → run() completes; family_stamp_coverage is empty."""
        state_p = tmp_path / "data" / "options_entry" / "state.parquet"
        _make_state_parquet(state_p)
        result = aoc.run(root=tmp_path, write=False)
        assert "data/options_entry/gate.json" in result["absent_stores"]
        assert result["family_stamp_coverage"] == []

    def test_ledger_absent(self, tmp_path: Path) -> None:
        """Board ledger absent → run() completes; family_stamp_coverage entries have empty weekly_fires."""
        state_p = tmp_path / "data" / "options_entry" / "state.parquet"
        gate_p = tmp_path / "data" / "options_entry" / "gate.json"
        _make_state_parquet(state_p)
        _make_gate_json(gate_p)
        result = aoc.run(root=tmp_path, write=False)
        assert "data/us_board_ledger/retro_grades.parquet" in result["absent_stores"]
        # Each family should still be listed with an "unknown" forecast
        for fam in result["family_stamp_coverage"]:
            assert fam["readiness_forecast"]["forecast"] == "unknown"

    def test_all_absent(self, tmp_path: Path) -> None:
        """All inputs absent → run() completes with 3 absent_stores; no exceptions."""
        result = aoc.run(root=tmp_path, write=False)
        assert len(result["absent_stores"]) >= 2  # at least state and gate absent
        assert "schema" in result

    def test_absent_stores_no_write(self, tmp_path: Path) -> None:
        """With all stores absent, --check mode should not create coverage.json."""
        result = aoc.run(root=tmp_path, write=False)
        coverage_p = tmp_path / "data" / "options_entry" / "coverage.json"
        assert not coverage_p.exists()


# ---------------------------------------------------------------------------
# Write mode
# ---------------------------------------------------------------------------

class TestWriteMode:
    def _build_full_root(self, tmp_path: Path) -> Path:
        state_p = tmp_path / "data" / "options_entry" / "state.parquet"
        gate_p = tmp_path / "data" / "options_entry" / "gate.json"
        ledger_p = tmp_path / "data" / "us_board_ledger" / "retro_grades.parquet"
        _make_state_parquet(state_p)
        _make_gate_json(gate_p)
        _make_ledger_parquet(ledger_p)
        return tmp_path

    def test_coverage_json_written(self, tmp_path: Path) -> None:
        root = self._build_full_root(tmp_path)
        aoc.run(root=root, write=True)
        out = root / "data" / "options_entry" / "coverage.json"
        assert out.exists(), "coverage.json was not written"
        doc = json.loads(out.read_text())
        assert doc["schema"] == "options_entry_coverage.v1"
        assert "feature_coverage" in doc
        assert "family_stamp_coverage" in doc
        assert "structural_nulls" in doc
        assert "consistency" in doc

    def test_coverage_json_vintage_stamped(self, tmp_path: Path) -> None:
        root = self._build_full_root(tmp_path)
        result = aoc.run(root=root, write=True)
        assert "_stamp" in result
        stamp = result["_stamp"]
        assert "generated_at_utc" in stamp
        assert "as_of" in stamp

    def test_check_mode_no_write(self, tmp_path: Path) -> None:
        root = self._build_full_root(tmp_path)
        aoc.run(root=root, write=False)
        out = root / "data" / "options_entry" / "coverage.json"
        assert not out.exists()


# ---------------------------------------------------------------------------
# Structural-null ledger section
# ---------------------------------------------------------------------------

class TestStructuralNulls:
    def test_iv_rank_252_entry(self, tmp_path: Path) -> None:
        result = aoc._structural_nulls(tmp_path, date(2026, 7, 6))
        ivr = result["iv_rank_252"]
        assert "ruling A9" in ivr["root_cause"]
        assert ivr["null_share"] == 1.0
        assert "iv_rank_252" in ivr["columns"]

    def test_pin_risk_entry_with_opex_date(self, tmp_path: Path) -> None:
        result = aoc._structural_nulls(tmp_path, date(2026, 7, 6))
        pr = result["pin_risk"]
        assert "opex_days<=5" in pr["pin_risk_gate_condition"]
        assert "next_opex_date" in pr
        assert "current_opex_days" in pr
        assert pr["null_share"] == 1.0
        # next OPEX should be a valid ISO date string
        next_opex = date.fromisoformat(pr["next_opex_date"])
        assert next_opex >= date(2026, 7, 6)

    def test_gamma_regime_constancy_entry(self, tmp_path: Path) -> None:
        result = aoc._structural_nulls(tmp_path, date(2026, 7, 6))
        gr = result["gamma_regime_constancy"]
        assert "audit #29" in gr["caveat"]
        assert "gamma_regime" in gr["columns"]


# ---------------------------------------------------------------------------
# Consistency rows
# ---------------------------------------------------------------------------

class TestConsistencyRows:
    def _build_gate(self, tmp_path: Path) -> dict:
        gate_p = tmp_path / "data" / "options_entry" / "gate.json"
        return _make_gate_json(gate_p)

    def test_bh_test_count_drift_row_present(self, tmp_path: Path) -> None:
        gate = self._build_gate(tmp_path)
        rows = aoc._consistency_rows(gate, tmp_path, date(2026, 7, 6))
        drift = next(r for r in rows if r["check"] == "bh_test_count_drift")
        # gate.json family_size=22; registered=28; docstring=22
        assert drift["registry_registered"] == 28
        assert drift["gate_json_family_size"] == 22
        assert drift["validate_docstring_count"] == 22
        assert "W-OVC" in drift["note"] or "W-OVC" in drift["note"]

    def test_stale_asof_ages_row_present(self, tmp_path: Path) -> None:
        gate = self._build_gate(tmp_path)
        # Create state.parquet with a known old date
        state_p = tmp_path / "data" / "options_entry" / "state.parquet"
        _make_state_parquet(state_p)
        rows = aoc._consistency_rows(gate, tmp_path, date(2026, 7, 6))
        stale = next(r for r in rows if r["check"] == "stale_asof_ages")
        assert "sources" in stale
        sources = {s["source"]: s for s in stale["sources"]}
        assert "options_entry/state.parquet" in sources
        assert "options_entry/gate.json" in sources

    def test_accrual_audit_not_run_row(self, tmp_path: Path) -> None:
        """When options_accrual_audit.json absent → status=NOT_YET_RUN."""
        gate = self._build_gate(tmp_path)
        rows = aoc._consistency_rows(gate, tmp_path, date(2026, 7, 6))
        accrual = next(r for r in rows if r["check"] == "audit_options_accrual_last_run")
        assert accrual["status"] == "NOT_YET_RUN"

    def test_accrual_audit_present_row(self, tmp_path: Path) -> None:
        """When options_accrual_audit.json present → show its ok/fail_reasons."""
        gate = self._build_gate(tmp_path)
        quality_p = tmp_path / "data" / "quality" / "options_accrual_audit.json"
        quality_p.parent.mkdir(parents=True, exist_ok=True)
        audit_doc = {
            "generated_at": "2026-07-06T10:00:00+00:00",
            "ok": True,
            "fail_reasons": [],
            "warnings": [],
            "detail": {},
        }
        quality_p.write_text(json.dumps(audit_doc))
        rows = aoc._consistency_rows(gate, tmp_path, date(2026, 7, 6))
        accrual = next(r for r in rows if r["check"] == "audit_options_accrual_last_run")
        assert accrual["ok"] is True
        assert accrual["fail_reasons"] == []


# ---------------------------------------------------------------------------
# run_as_collect_step never raises
# ---------------------------------------------------------------------------

class TestCollectStepResilience:
    def test_never_raises_on_empty_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """With all stores absent, collect step must not raise."""
        def _patched_run(*args, **kwargs):
            return aoc.run(root=tmp_path, write=False)
        monkeypatch.setattr(aoc, "run", _patched_run)
        aoc.run_as_collect_step()  # must not raise

    def test_never_raises_on_broken_run(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Simulated crash inside run() must not propagate."""
        def _broken_run(*args, **kwargs):
            raise RuntimeError("simulated audit crash")
        monkeypatch.setattr(aoc, "run", _broken_run)
        aoc.run_as_collect_step()  # must not raise


# ---------------------------------------------------------------------------
# audit_options_accrual wrapper test
# ---------------------------------------------------------------------------

class TestAccrualWrapper:
    def test_run_as_collect_step_wired(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """audit_options_accrual.run_as_collect_step exists and is callable."""
        import scripts.audit_options_accrual as aoa
        assert hasattr(aoa, "run_as_collect_step"), (
            "audit_options_accrual.py must have run_as_collect_step (W-OC wiring)"
        )
        assert callable(aoa.run_as_collect_step)

    def test_run_as_collect_step_never_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """run_as_collect_step must not raise even when audit crashes."""
        import scripts.audit_options_accrual as aoa

        def _broken_audit(*args, **kwargs):
            raise RuntimeError("simulated accrual crash")

        monkeypatch.setattr(aoa, "audit", _broken_audit)
        aoa.run_as_collect_step()  # must not raise

    def test_run_as_collect_step_writes_audit_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When audit() returns ok=True, the collect step writes options_accrual_audit.json."""
        import scripts.audit_options_accrual as aoa
        from lib import config as _config

        monkeypatch.setattr(_config, "data_dir", lambda: tmp_path)
        # Patch _last_trading_day so chains are always fresh
        monkeypatch.setattr(aoa, "_last_trading_day", lambda ref=None: date(2026, 7, 2))
        # Create chains dir with a fresh file
        chains = tmp_path / "polygon_gex" / "chains"
        chains.mkdir(parents=True)
        pd.DataFrame({"x": [1]}).to_parquet(chains / "2026-07-02.parquet")
        monkeypatch.setenv("MASSIVE_S3_ACCESS_KEY_ID", "k")
        monkeypatch.setenv("MASSIVE_S3_SECRET_ACCESS_KEY", "s")
        monkeypatch.setenv("MASSIVE_S3_ENDPOINT", "https://x")

        aoa.run_as_collect_step()

        out = tmp_path / "quality" / "options_accrual_audit.json"
        assert out.exists(), "options_accrual_audit.json should be written by collect step"
        doc = json.loads(out.read_text())
        assert "ok" in doc
        assert "generated_at" in doc


# ---------------------------------------------------------------------------
# collect.py wiring smoke test
# ---------------------------------------------------------------------------

class TestCollectWiring:
    def test_collect_imports_opts_accrual(self) -> None:
        """collect.py must import and call audit_options_accrual.run_as_collect_step."""
        import ast
        from pathlib import Path
        collect_p = Path(__file__).resolve().parent.parent / "scripts" / "collect.py"
        src = collect_p.read_text()
        assert "audit_options_accrual" in src, (
            "audit_options_accrual not found in collect.py"
        )
        assert "run_as_collect_step" in src, (
            "run_as_collect_step not found in collect.py"
        )

    def test_collect_imports_opts_coverage(self) -> None:
        """collect.py must import and call audit_options_entry_coverage.run_as_collect_step."""
        from pathlib import Path
        collect_p = Path(__file__).resolve().parent.parent / "scripts" / "collect.py"
        src = collect_p.read_text()
        assert "audit_options_entry_coverage" in src, (
            "audit_options_entry_coverage not found in collect.py"
        )

    def test_opts_coverage_after_opts_accrual(self) -> None:
        """In collect.py, opts_coverage step must appear AFTER opts_accrual step."""
        from pathlib import Path
        collect_p = Path(__file__).resolve().parent.parent / "scripts" / "collect.py"
        src = collect_p.read_text()
        idx_accrual = src.find("audit_options_accrual")
        idx_coverage = src.find("audit_options_entry_coverage")
        assert idx_accrual != -1
        assert idx_coverage != -1
        assert idx_accrual < idx_coverage, (
            "audit_options_accrual step must appear before audit_options_entry_coverage in collect.py"
        )
