"""tests/test_kernel_decisions.py — Neural Web W3 PR2: quarterly decision machinery.

Fixture-only: no live data reads. All data is constructed in-memory or written
to tmp_path. Tests are hermetic and deterministic.

Coverage:
  (1) Eligibility rule application — n_eff floor, ci_low not-None, staleness gate.
  (2) BH FDR math against a hand-computed 3-cell panel.
  (3) Refusal before FIRST_BATCH_DUE — cadence guard.
  (4) Register-before-evaluate order — assert ledger write precedes p-value computation.
  (5) Seed file shape — kernel_decisions.json has all required fields.
  (6) Sign test p-value correctness — hand-computed extreme cases.
  (7) Dry-run-on-fixtures accepts a fixture dir but rejects the real parquet path.
  (8) Empty estimates → null batch (no crash, seed shape).
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, call, patch

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers — construct minimal kernel_estimates fixture parquets
# ---------------------------------------------------------------------------

_EST_COLS = [
    "engine", "regime", "regime_col", "horizon",
    "n_raw", "n_eff", "mean_raw", "shrunken_ic",
    "reliability", "wilson_ci_low", "armed",
    "fill_basis_mode", "date_first", "date_last",
]


def _est_row(
    engine: str = "eng_a",
    regime: str = "__all__",
    horizon: int = 21,
    n_eff: int = 30,
    mean_raw: float = 0.03,
    shrunken_ic: float = 0.02,
    wilson_ci_low: float | None = 0.05,
    date_last: str = "2026-07-01",
    armed: bool = True,
    n_raw: int | None = None,
) -> dict:
    return {
        "engine": engine,
        "regime": regime,
        "regime_col": "quad_hard_label",
        "horizon": horizon,
        "n_raw": n_raw if n_raw is not None else n_eff,
        "n_eff": n_eff,
        "mean_raw": mean_raw,
        "shrunken_ic": shrunken_ic,
        "reliability": n_eff / (n_eff + 8.0),
        "wilson_ci_low": wilson_ci_low,
        "armed": armed,
        "fill_basis_mode": "next_bar",
        "date_first": "2024-01-01",
        "date_last": date_last,
    }


def _write_estimates(tmp_path: Path, rows: list[dict]) -> Path:
    out = tmp_path / "data" / "neuralweb"
    out.mkdir(parents=True, exist_ok=True)
    p = out / "kernel_estimates.parquet"
    df = pd.DataFrame(rows if rows else [], columns=_EST_COLS)
    for c in _EST_COLS:
        if c not in df.columns:
            df[c] = None
    df.to_parquet(p, index=False)
    # Also create the trial_ledger dir
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# (1) Eligibility rule application
# ---------------------------------------------------------------------------

class TestEligibilityRules:
    """Pre-registered decision rule: n_eff >= 25, ci_low notna, staleness <= 380d."""

    def _run(self, tmp_path: Path, rows: list[dict], now: str = "2026-10-01") -> dict:
        _write_estimates(tmp_path, rows)
        from scripts.run_kernel_decisions import _run_batch
        return _run_batch(tmp_path, dry_run=True, _now_override=now)

    def test_n_eff_floor_excludes_low_n(self, tmp_path):
        """Cells with n_eff < 25 are excluded from the batch."""
        rows = [
            _est_row(engine="e1", n_eff=24, wilson_ci_low=0.05),  # below floor
            _est_row(engine="e2", n_eff=25, wilson_ci_low=0.55),  # at floor → eligible
        ]
        result = self._run(tmp_path, rows)
        assert result["n_eligible"] == 1, (
            f"expected 1 eligible (n_eff=25), got {result['n_eligible']}"
        )

    def test_ci_low_none_excludes_cell(self, tmp_path):
        """Cells with wilson_ci_low=None are excluded (not enough data for CI)."""
        rows = [
            _est_row(engine="e_none", n_eff=30, wilson_ci_low=None),
            _est_row(engine="e_val", n_eff=30, wilson_ci_low=0.40),
        ]
        result = self._run(tmp_path, rows)
        assert result["n_eligible"] == 1

    def test_stale_data_excluded(self, tmp_path):
        """Cells with date_last more than 380d ago are excluded."""
        rows = [
            _est_row(engine="stale", n_eff=30, wilson_ci_low=0.4,
                     date_last="2024-01-01"),  # >380d before 2026-10-01
            _est_row(engine="fresh", n_eff=30, wilson_ci_low=0.4,
                     date_last="2026-07-01"),  # fresh
        ]
        result = self._run(tmp_path, rows)
        assert result["n_eligible"] == 1

    def test_all_criteria_met_eligible(self, tmp_path):
        """A cell meeting all three criteria is eligible."""
        rows = [_est_row(engine="good", n_eff=30, wilson_ci_low=0.45,
                         date_last="2026-07-01")]
        result = self._run(tmp_path, rows)
        assert result["n_eligible"] == 1


# ---------------------------------------------------------------------------
# (2) BH FDR math: hand-computed 3-cell panel
# ---------------------------------------------------------------------------

class TestBHFDRMath:
    """Verify BH FDR against a hand-computed panel."""

    def test_bh_survivors_match_hand_computation(self, tmp_path):
        """3-cell panel: hand-compute BH at alpha=0.10, verify survivors.

        Panel (sorted by p-value):
          cell_a: p=0.001 → q = 0.001 * 3/1 = 0.003 → reject
          cell_b: p=0.04  → q = min(1, 0.04 * 3/2) = 0.060 → reject
          cell_c: p=0.20  → q = min(1, 0.20 * 3/3) = 0.200 → do not reject

        The BH procedure (step-up): sort ascending; for rank i (1-based) of m:
          q_i = p_i * m/i; enforce monotone q (each q_i = min(q_i, q_{i+1}));
          reject if q_i <= alpha.

        So at alpha=0.10: cell_a (q=0.003) and cell_b (q=0.060) survive.
        """
        from engine.validation import benjamini_hochberg

        pvals = {"cell_a": 0.001, "cell_b": 0.04, "cell_c": 0.20}
        result = benjamini_hochberg(pvals, alpha=0.10)

        assert result["cell_a"]["reject"] is True, "cell_a (p=0.001) must survive BH"
        assert result["cell_b"]["reject"] is True, "cell_b (p=0.04) must survive BH"
        assert result["cell_c"]["reject"] is False, "cell_c (p=0.20) must not survive BH"

        # Verify q-values (with monotone enforcement)
        # After sort: cell_a (p=0.001, rank 1), cell_b (p=0.04, rank 2), cell_c (p=0.20, rank 3)
        # raw q: cell_c=0.20*(3/3)=0.20; cell_b=min(0.20, 0.04*(3/2))=min(0.20,0.06)=0.06
        #        cell_a=min(0.06, 0.001*(3/1))=min(0.06,0.003)=0.003
        assert abs(result["cell_a"]["q"] - 0.003) < 0.001
        assert abs(result["cell_b"]["q"] - 0.060) < 0.005
        assert abs(result["cell_c"]["q"] - 0.200) < 0.005

    def test_no_survivors_when_all_pvals_high(self, tmp_path):
        """No survivors when all p-values are above BH threshold."""
        from engine.validation import benjamini_hochberg

        pvals = {"c1": 0.30, "c2": 0.45, "c3": 0.80}
        result = benjamini_hochberg(pvals, alpha=0.10)
        assert not any(v["reject"] for v in result.values())

    def test_all_survivors_when_all_pvals_tiny(self, tmp_path):
        """All cells survive when all p-values are very small."""
        from engine.validation import benjamini_hochberg

        pvals = {"c1": 0.001, "c2": 0.002, "c3": 0.003}
        result = benjamini_hochberg(pvals, alpha=0.10)
        assert all(v["reject"] for v in result.values())


# ---------------------------------------------------------------------------
# (3) Refusal before FIRST_BATCH_DUE
# ---------------------------------------------------------------------------

class TestCadenceGuard:
    """Running before FIRST_BATCH_DUE must exit 1 with a clear message."""

    def test_refuses_before_batch_due(self, tmp_path, capsys):
        """_check_cadence exits 1 when today < FIRST_BATCH_DUE."""
        from scripts.run_kernel_decisions import _check_cadence, FIRST_BATCH_DUE

        with pytest.raises(SystemExit) as exc:
            _check_cadence(now_date_str="2026-07-04", dry_run=False)
        assert exc.value.code == 1

    def test_allows_on_batch_due_date(self):
        """_check_cadence passes when today == FIRST_BATCH_DUE."""
        from scripts.run_kernel_decisions import _check_cadence, FIRST_BATCH_DUE
        # Should not raise
        _check_cadence(now_date_str=FIRST_BATCH_DUE, dry_run=False)

    def test_allows_after_batch_due(self):
        """_check_cadence passes when today > FIRST_BATCH_DUE."""
        from scripts.run_kernel_decisions import _check_cadence
        _check_cadence(now_date_str="2027-01-01", dry_run=False)

    def test_dry_run_bypasses_cadence_guard(self, tmp_path):
        """--dry-run-on-fixtures bypasses the cadence guard."""
        from scripts.run_kernel_decisions import _check_cadence
        # Should not raise even though today is before FIRST_BATCH_DUE
        _check_cadence(now_date_str="2026-07-04", dry_run=True)

    def test_main_exits_1_before_batch_due(self, tmp_path, monkeypatch):
        """main() exits 1 when invoked before FIRST_BATCH_DUE."""
        # Patch today's date inside _check_cadence via date override
        import scripts.run_kernel_decisions as m
        monkeypatch.setattr(m, "FIRST_BATCH_DUE", "2099-10-01")
        # Without dry_run, this should exit 1
        from scripts.run_kernel_decisions import main
        rc = main([])
        assert rc == 1


# ---------------------------------------------------------------------------
# (4) Register-before-evaluate order
# ---------------------------------------------------------------------------

class TestRegisterBeforeEvaluate:
    """The ledger write must precede any p-value computation.

    We instrument log_declared_budget and the sign test to record call order,
    then verify that the ledger write happened before the first p-value call.
    """

    def test_ledger_write_precedes_pvalue_computation(self, tmp_path):
        """log_declared_budget is called before _sign_test_p_value in _run_batch."""
        _write_estimates(tmp_path, [
            _est_row(engine="ord_e", n_eff=30, wilson_ci_low=0.45,
                     date_last="2026-07-01"),
        ])

        call_log: list[str] = []

        import scripts.run_kernel_decisions as m

        orig_sign_test = m._sign_test_p_value
        orig_log_budget = None

        # We need to patch TrialLedger.log_declared_budget and _sign_test_p_value
        from engine import trial_ledger as tl

        class _RecordingLedger(tl.TrialLedger):
            def log_declared_budget(self, n, *, family=None, reason=None):
                call_log.append("ledger_write")
                return super().log_declared_budget(n, family=family, reason=reason)

        def _recording_sign_test(hits, n, h0=m.SIGN_TEST_H0):
            call_log.append("pvalue_compute")
            return orig_sign_test(hits, n, h0)

        import importlib

        with patch.object(tl, "TrialLedger", _RecordingLedger):
            with patch.object(m, "_sign_test_p_value", _recording_sign_test):
                m._run_batch(tmp_path, dry_run=True, _now_override="2026-10-01")

        # Find positions
        ledger_pos = next(
            (i for i, v in enumerate(call_log) if v == "ledger_write"), None
        )
        pvalue_pos = next(
            (i for i, v in enumerate(call_log) if v == "pvalue_compute"), None
        )

        assert ledger_pos is not None, "ledger_write never called"
        assert pvalue_pos is not None, "pvalue_compute never called"
        assert ledger_pos < pvalue_pos, (
            f"ANTI-PEEKING VIOLATED: ledger_write at position {ledger_pos}, "
            f"pvalue_compute at position {pvalue_pos}; ledger must write FIRST"
        )


# ---------------------------------------------------------------------------
# (5) Seed file shape
# ---------------------------------------------------------------------------

class TestSeedFileShape:
    """The committed kernel_decisions.json seed has the required fields."""

    def test_seed_file_required_fields(self):
        """data/neuralweb/kernel_decisions.json has all required fields."""
        seed_path = Path(__file__).resolve().parents[1] / "data" / "neuralweb" / "kernel_decisions.json"
        assert seed_path.exists(), f"seed file missing: {seed_path}"
        d = json.loads(seed_path.read_text())
        required = [
            "batch_id", "run_at", "alpha", "trial_family", "decision_rule",
            "n_eligible", "n_survivors", "survivors", "trial_ledger_ref",
            "next_batch_due", "note", "standing_law",
        ]
        for field in required:
            assert field in d, f"seed missing required field: {field}"

    def test_seed_file_null_batch(self):
        """Seed file batch_id and run_at must be null (no batch has run)."""
        seed_path = Path(__file__).resolve().parents[1] / "data" / "neuralweb" / "kernel_decisions.json"
        d = json.loads(seed_path.read_text())
        assert d["batch_id"] is None, "seed batch_id must be null"
        assert d["run_at"] is None, "seed run_at must be null"
        assert d["survivors"] == [], "seed survivors must be empty list"
        assert d["n_survivors"] == 0
        assert d["n_eligible"] == 0

    def test_seed_file_next_batch_due(self):
        """Seed file next_batch_due must match FIRST_BATCH_DUE."""
        from scripts.run_kernel_decisions import FIRST_BATCH_DUE
        seed_path = Path(__file__).resolve().parents[1] / "data" / "neuralweb" / "kernel_decisions.json"
        d = json.loads(seed_path.read_text())
        assert d["next_batch_due"] == FIRST_BATCH_DUE, (
            f"next_batch_due mismatch: {d['next_batch_due']} != {FIRST_BATCH_DUE}"
        )

    def test_seed_file_standing_law_present(self):
        """Seed file must contain the standing_law field (structural enforcement)."""
        seed_path = Path(__file__).resolve().parents[1] / "data" / "neuralweb" / "kernel_decisions.json"
        d = json.loads(seed_path.read_text())
        law = d.get("standing_law", "")
        assert "survivors[]" in law, "standing_law must reference survivors[]"
        assert "behavior-changing" in law, "standing_law must mention behavior-changing"


# ---------------------------------------------------------------------------
# (6) Sign test p-value correctness
# ---------------------------------------------------------------------------

class TestSignTestPValue:
    """Hand-computed extreme cases for the binomial sign test."""

    def test_all_hits_gives_tiny_pvalue(self):
        """All n outcomes positive: p-value should be near (0.5)^n."""
        from scripts.run_kernel_decisions import _sign_test_p_value
        n = 10
        p = _sign_test_p_value(n, n)
        # P(X >= 10 | Binomial(10, 0.5)) = 0.5^10 ≈ 0.000977
        expected = 0.5 ** n
        assert abs(p - expected) < 1e-4, f"expected ~{expected:.6f}, got {p:.6f}"

    def test_half_hits_gives_pvalue_near_half(self):
        """Half the outcomes positive: p ~= 0.5 (not significant)."""
        from scripts.run_kernel_decisions import _sign_test_p_value
        n = 20
        hits = 10
        p = _sign_test_p_value(hits, n)
        # P(X >= 10 | Binomial(20, 0.5)) = 0.5879... (symmetric, slightly above 0.5)
        assert 0.40 <= p <= 0.70, f"expected p near 0.5, got {p:.4f}"

    def test_zero_hits_gives_pvalue_one(self):
        """Zero positive outcomes: p = 1.0 (no evidence of edge)."""
        from scripts.run_kernel_decisions import _sign_test_p_value
        p = _sign_test_p_value(0, 20)
        assert p == 1.0

    def test_pvalue_in_unit_interval(self):
        """All p-values must be in [0, 1]."""
        from scripts.run_kernel_decisions import _sign_test_p_value
        for n in [1, 5, 10, 25, 50, 100]:
            for hits in [0, n // 4, n // 2, n]:
                p = _sign_test_p_value(hits, n)
                assert 0.0 <= p <= 1.0, f"p={p} out of [0,1] for hits={hits}, n={n}"

    def test_monotone_in_hits(self):
        """More hits → lower (or equal) p-value (monotone)."""
        from scripts.run_kernel_decisions import _sign_test_p_value
        n = 20
        pvals = [_sign_test_p_value(h, n) for h in range(n + 1)]
        for i in range(len(pvals) - 1):
            assert pvals[i] >= pvals[i + 1] - 1e-10, (
                f"p-value not monotone at hits={i}: p[{i}]={pvals[i]:.6f} < p[{i+1}]={pvals[i+1]:.6f}"
            )


# ---------------------------------------------------------------------------
# (7) Dry-run fixture path enforcement
# ---------------------------------------------------------------------------

class TestDryRunPathEnforcement:
    """--dry-run-on-fixtures must reject a fixture_dir that resolves to the real parquet."""

    def test_fixture_dir_same_as_real_raises(self, tmp_path):
        """_run_batch raises SystemExit(1) when fixture_dir resolves to the same
        kernel_estimates.parquet as the real repo root."""
        import scripts.run_kernel_decisions as m
        from scripts.run_kernel_decisions import _REAL_ESTIMATES_REL

        # Point fixture_dir and root at the SAME path so fixture_estimates == real_estimates
        # We do this by using the same directory for both root and fixture_dir.
        # First, create a valid estimates parquet in tmp_path so the file-exists check passes.
        _write_estimates(tmp_path, [_est_row()])
        # Use tmp_path as both root AND fixture_dir — they resolve to the same estimates file.
        with pytest.raises(SystemExit) as exc:
            m._run_batch(
                tmp_path,          # root
                dry_run=True,
                fixture_dir=tmp_path,  # fixture_dir == root → same parquet → rejected
            )
        assert exc.value.code == 1, (
            f"expected exit 1 when fixture_dir == root; got code={exc.value.code}"
        )

    def test_different_fixture_dir_accepted(self, tmp_path):
        """_run_batch accepts a fixture_dir that is different from the real root."""
        import scripts.run_kernel_decisions as m

        # real_root = some OTHER tmp directory (won't have the real parquet)
        real_root = tmp_path / "fake_root"
        real_root.mkdir()
        fixture_dir = tmp_path / "fixture"
        fixture_dir.mkdir()

        # Write estimates only in fixture_dir
        _write_estimates(fixture_dir, [_est_row(engine="fx", n_eff=30,
                                                 wilson_ci_low=0.4, date_last="2026-07-01")])

        # No real parquet in real_root — so the collision check passes
        # (real_root/_REAL_ESTIMATES_REL does not exist but fixture_dir has it)
        # _run_batch will detect non-collision and proceed to load fixture parquet
        result = m._run_batch(
            real_root,
            dry_run=True,
            fixture_dir=fixture_dir,
            _now_override="2026-10-01",
        )
        # Should succeed (1 eligible cell)
        assert result.get("n_eligible", 0) == 1


# ---------------------------------------------------------------------------
# (8) Empty estimates → null batch
# ---------------------------------------------------------------------------

class TestEmptyEstimates:
    """An empty kernel_estimates parquet produces a null batch without crashing."""

    def test_empty_estimates_writes_seed_shape(self, tmp_path):
        """Empty parquet → n_eligible=0, n_survivors=0, survivors=[]."""
        _write_estimates(tmp_path, [])
        from scripts.run_kernel_decisions import _run_batch
        result = _run_batch(tmp_path, dry_run=True, _now_override="2026-10-01")
        assert result.get("n_eligible", 0) == 0
        assert result.get("n_survivors", 0) == 0
        assert result.get("survivors", []) == []
