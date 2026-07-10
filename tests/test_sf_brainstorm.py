"""tests/test_sf_brainstorm.py — Unit tests for run_signal_foundry_brainstorm.py.

Tests:
  - Gate: SIGNAL_FOUNDRY_PAUSED unset → pack-only (awaiting_arming)
  - Gate: auto_loop false → pack-only (paused)
  - Gate: both open but no OAuth → degraded_pack_only
  - RF-16/SF-R12: numeric confidence stripping in skeptic output
  - SF-R7 two-key: blocklist reject → filed as screen_rejected
  - ISO-week idempotency: already-filed budget → no-op
  - Full path: LLM mocked, end-to-end file + lane_status

All LLM calls are mocked. No network.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_root(tmp_path: Path) -> Path:
    """Create a minimal repo root with required dirs and a minimal signal_foundry.yml."""
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "signal_foundry").mkdir(parents=True, exist_ok=True)
    (tmp_path / "engine").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)

    # Minimal config
    cfg_text = """\
auto_loop: false
budgets:
  filed_per_week: 5
  runs_per_week: 10
  run_wallclock_min: 30
models:
  generator: claude-sonnet-4-6
  skeptic: claude-opus-4-8
  compiler: claude-haiku-4-5-20251001
"""
    (tmp_path / "config" / "signal_foundry.yml").write_text(cfg_text)
    return tmp_path


def _make_root_auto_loop(tmp_path: Path) -> Path:
    """Config with auto_loop: true."""
    root = _make_root(tmp_path)
    cfg_text = """\
auto_loop: true
budgets:
  filed_per_week: 5
  runs_per_week: 10
  run_wallclock_min: 30
models:
  generator: claude-sonnet-4-6
  skeptic: claude-opus-4-8
  compiler: claude-haiku-4-5-20251001
"""
    (root / "config" / "signal_foundry.yml").write_text(cfg_text)
    return root


def _read_lane_status(root: Path) -> dict:
    p = root / "data" / "signal_foundry" / "lane_status.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def _read_candidates(root: Path) -> list[dict]:
    p = root / "data" / "signal_foundry" / "candidates.jsonl"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _read_governance(root: Path) -> list[dict]:
    p = root / "data" / "signal_foundry" / "governance.jsonl"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# Import the script under test
# ---------------------------------------------------------------------------

from scripts.run_signal_foundry_brainstorm import (
    _has_numeric_confidence,
    _validate_skeptic_findings,
    _is_paused,
    _current_iso_week,
    _count_filed_this_week,
    _build_sf_pack,
    main,
)


# ---------------------------------------------------------------------------
# Test: _has_numeric_confidence (RF-16/SF-R12)
# ---------------------------------------------------------------------------

class TestNumericConfidence:
    def test_flat_numeric_confidence_detected(self) -> None:
        obj = {"recommendation": "ADVISORY_KEEP", "confidence": 0.8}
        assert _has_numeric_confidence(obj) is True

    def test_nested_numeric_confidence_detected(self) -> None:
        obj = {"findings": [{"spec_id": "SF-0001", "confidence_score": 0.95}]}
        assert _has_numeric_confidence(obj) is True

    def test_categorical_only_not_detected(self) -> None:
        obj = {"recommendation": "ADVISORY_KEEP", "blockers": ["missing PIT plan"]}
        assert _has_numeric_confidence(obj) is False

    def test_string_confidence_not_detected(self) -> None:
        # String "confidence" value is not numeric
        obj = {"confidence": "high"}
        assert _has_numeric_confidence(obj) is False

    def test_prob_field_detected(self) -> None:
        obj = {"prob": 0.3}
        assert _has_numeric_confidence(obj) is True

    def test_empty_dict_clean(self) -> None:
        assert _has_numeric_confidence({}) is False

    def test_deep_nesting_detected(self) -> None:
        obj = {"a": {"b": {"c": {"d": {"score": 0.5}}}}}
        assert _has_numeric_confidence(obj) is True


# ---------------------------------------------------------------------------
# Test: _validate_skeptic_findings (RF-16)
# ---------------------------------------------------------------------------

class TestValidateSkepticFindings:
    def test_valid_keep_finding_passes(self) -> None:
        findings = [{"spec_id": "SF-0001", "recommendation": "ADVISORY_KEEP", "blockers": []}]
        valid, rejected = _validate_skeptic_findings(findings)
        assert len(valid) == 1
        assert len(rejected) == 0

    def test_numeric_confidence_finding_stripped(self) -> None:
        findings = [
            {"spec_id": "SF-0001", "recommendation": "ADVISORY_DROP",
             "confidence": 0.9, "blockers": ["circular definition"]}
        ]
        valid, rejected = _validate_skeptic_findings(findings)
        assert len(valid) == 0
        assert len(rejected) == 1
        assert "RF-16" in rejected[0]

    def test_mixed_findings_only_valid_pass(self) -> None:
        findings = [
            {"spec_id": "SF-0001", "recommendation": "ADVISORY_KEEP", "blockers": []},
            {"spec_id": "SF-0002", "recommendation": "ADVISORY_DROP",
             "confidence_score": 0.7, "blockers": ["look-ahead"]},
        ]
        valid, rejected = _validate_skeptic_findings(findings)
        assert len(valid) == 1
        assert valid[0]["spec_id"] == "SF-0001"
        assert len(rejected) == 1


# ---------------------------------------------------------------------------
# Test: _is_paused() fail-closed
# ---------------------------------------------------------------------------

class TestIsPaused:
    def test_unset_is_paused(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            # remove key if present
            env = {k: v for k, v in os.environ.items() if k != "SIGNAL_FOUNDRY_PAUSED"}
            with mock.patch.dict(os.environ, env, clear=True):
                assert _is_paused() is True

    def test_false_string_not_paused(self) -> None:
        with mock.patch.dict(os.environ, {"SIGNAL_FOUNDRY_PAUSED": "false"}):
            assert _is_paused() is False

    def test_true_string_paused(self) -> None:
        with mock.patch.dict(os.environ, {"SIGNAL_FOUNDRY_PAUSED": "true"}):
            assert _is_paused() is True

    def test_empty_string_paused(self) -> None:
        with mock.patch.dict(os.environ, {"SIGNAL_FOUNDRY_PAUSED": ""}):
            assert _is_paused() is True

    def test_case_insensitive_false(self) -> None:
        # Only exact lowercase 'false' arms; 'False' or 'FALSE' stay paused
        with mock.patch.dict(os.environ, {"SIGNAL_FOUNDRY_PAUSED": "False"}):
            # strip().lower() → 'false' → not paused
            assert _is_paused() is False

    def test_arbitrary_value_paused(self) -> None:
        with mock.patch.dict(os.environ, {"SIGNAL_FOUNDRY_PAUSED": "0"}):
            assert _is_paused() is True


# ---------------------------------------------------------------------------
# Test: Gate 1 — SIGNAL_FOUNDRY_PAUSED not 'false' → pack-only (awaiting_arming)
# ---------------------------------------------------------------------------

class TestGatePaused:
    def test_unset_paused_env_gives_pack_only(self, tmp_path: Path) -> None:
        root = _make_root_auto_loop(tmp_path)
        env = {k: v for k, v in os.environ.items() if k != "SIGNAL_FOUNDRY_PAUSED"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("scripts.run_signal_foundry_brainstorm._load_config",
                            return_value=_AUTO_LOOP_CFG):
                rc = main(["--root", str(root), "--trigger", "scheduled"])
        assert rc == 0
        status = _read_lane_status(root)
        assert status.get("status") == "awaiting_arming"

    def test_paused_true_gives_pack_only(self, tmp_path: Path) -> None:
        root = _make_root_auto_loop(tmp_path)
        with mock.patch.dict(os.environ, {"SIGNAL_FOUNDRY_PAUSED": "true"}):
            with mock.patch("scripts.run_signal_foundry_brainstorm._load_config",
                            return_value=_AUTO_LOOP_CFG):
                rc = main(["--root", str(root), "--trigger", "scheduled"])
        assert rc == 0
        status = _read_lane_status(root)
        assert status.get("status") == "awaiting_arming"

    def test_operator_trigger_bypasses_pause_gate(self, tmp_path: Path) -> None:
        """Operator trigger ignores SIGNAL_FOUNDRY_PAUSED (gate only applies to scheduled)."""
        root = _make_root_auto_loop(tmp_path)
        # Even with paused=true, operator trigger should not hit the pause gate.
        # It will still fail on auth (no providers), giving degraded_pack_only.
        with mock.patch.dict(os.environ, {"SIGNAL_FOUNDRY_PAUSED": "true"}):
            with mock.patch("scripts.run_signal_foundry_brainstorm._build_operator_providers",
                            return_value=[]):
                rc = main(["--root", str(root), "--trigger", "operator"])
        assert rc == 0
        status = _read_lane_status(root)
        # Should be degraded_pack_only from no-auth, NOT awaiting_arming
        assert status.get("status") == "degraded_pack_only"


# ---------------------------------------------------------------------------
# Test: Gate 2 — auto_loop false → pack-only (paused)
# ---------------------------------------------------------------------------

_AUTO_LOOP_FALSE_CFG = {
    "auto_loop": False,
    "budgets": {"filed_per_week": 5, "runs_per_week": 10, "run_wallclock_min": 30},
    "models": {
        "generator": "claude-sonnet-4-6",
        "skeptic": "claude-opus-4-8",
        "compiler": "claude-haiku-4-5-20251001",
    },
}


class TestGateAutoLoop:
    def test_auto_loop_false_gives_paused(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        with mock.patch.dict(os.environ, {"SIGNAL_FOUNDRY_PAUSED": "false"}):
            with mock.patch("scripts.run_signal_foundry_brainstorm._load_config",
                            return_value=_AUTO_LOOP_FALSE_CFG):
                rc = main(["--root", str(root), "--trigger", "scheduled"])
        assert rc == 0
        status = _read_lane_status(root)
        assert status.get("status") == "paused"


# ---------------------------------------------------------------------------
# Test: Gate 3 (ISO-week idempotency)
# ---------------------------------------------------------------------------

_AUTO_LOOP_CFG = {
    "auto_loop": True,
    "budgets": {"filed_per_week": 5, "runs_per_week": 10, "run_wallclock_min": 30},
    "models": {
        "generator": "claude-sonnet-4-6",
        "skeptic": "claude-opus-4-8",
        "compiler": "claude-haiku-4-5-20251001",
    },
}


class TestISOWeekIdempotency:
    def test_already_filed_budget_gives_noop(self, tmp_path: Path) -> None:
        root = _make_root_auto_loop(tmp_path)
        iso_week = _current_iso_week()
        # Pre-fill candidates.jsonl with 5 proposed rows this week (hits the budget)
        cands_path = root / "data" / "signal_foundry" / "candidates.jsonl"
        for i in range(5):
            row = {
                "id": f"SF-{i+1:04d}",
                "name": f"test-{i}",
                "status": "proposed",
                "iso_week": iso_week,
            }
            with cands_path.open("a") as fh:
                fh.write(json.dumps(row) + "\n")

        with mock.patch.dict(os.environ, {"SIGNAL_FOUNDRY_PAUSED": "false"}):
            with mock.patch("scripts.run_signal_foundry_brainstorm._load_config",
                            return_value=_AUTO_LOOP_CFG):
                rc = main(["--root", str(root), "--trigger", "scheduled"])
        assert rc == 0
        status = _read_lane_status(root)
        # Should be idempotent skip (status=full, not paused/awaiting)
        assert status.get("status") == "full"
        assert "idempotent" in status.get("reason", "").lower()


# ---------------------------------------------------------------------------
# Test: Gate 4 — both gates open but no OAuth → degraded_pack_only
# ---------------------------------------------------------------------------

class TestGateNoAuth:
    def test_no_oauth_gives_degraded(self, tmp_path: Path) -> None:
        root = _make_root_auto_loop(tmp_path)
        with mock.patch.dict(os.environ, {"SIGNAL_FOUNDRY_PAUSED": "false"}):
            with mock.patch("scripts.run_signal_foundry_brainstorm._load_config",
                            return_value=_AUTO_LOOP_CFG):
                with mock.patch("scripts.run_signal_foundry_brainstorm._build_scheduled_providers",
                                return_value=[]):
                    rc = main(["--root", str(root), "--trigger", "scheduled"])
        assert rc == 0
        status = _read_lane_status(root)
        assert status.get("status") == "degraded_pack_only"


# ---------------------------------------------------------------------------
# Test: SF-R7 two-key screen — blocklist reject → screen_rejected in candidates.jsonl
# ---------------------------------------------------------------------------

class TestTwoKeyScreen:
    def test_screen_rejected_spec_filed_as_screen_rejected(self, tmp_path: Path) -> None:
        """A compiled spec that fails the screen goes into candidates.jsonl as screen_rejected."""
        root = _make_root_auto_loop(tmp_path)

        # A spec with empty data — will fail gate 1 (no data path)
        bad_spec = {
            "id": "SF-9001",
            "name": "insider-timing-signal",
            "thesis": "insider timing predicts returns",
            "mechanism": "insider trading",
            "data": [],  # no data — gate 1 fail
            "feature": {"pipeline": []},
            "target": {"path": "data/yahoo/SPY.parquet", "kind": "excess_return", "horizon_d": 21},
            "universe": "single_series",
            "baseline": "",  # no baseline — gate 4 fail
            "gates": {"min_t_hac": 2.0, "fdr_q": 0.10, "dsr": 0.90},
            "orthogonality_note": "distinct from momentum",
            "evidence_note": "prior literature",
            "registered_at": "2026-07-10",
        }

        gen_output = json.dumps([bad_spec])
        skep_output = json.dumps([{
            "spec_id": "SF-9001",
            "recommendation": "ADVISORY_KEEP",
            "blockers": [],
        }])
        comp_output = json.dumps([bad_spec])

        def _fake_llm_call(providers, system, user, max_tokens, context):
            if context == "sf_generator":
                return (gen_output, None, "oauth", {})
            elif context == "sf_skeptic":
                return (skep_output, None, "oauth", {})
            elif context == "sf_compiler":
                return (comp_output, None, "oauth", {})
            return (None, "unknown context", None, {})

        fake_providers = [{"name": "oauth", "model": "claude-sonnet-4-6"}]

        # Use operator trigger (avoids PAUSED env gate) with full provider waterfall
        with mock.patch("scripts.run_signal_foundry_brainstorm._build_operator_providers",
                        return_value=fake_providers):
            with mock.patch("scripts.run_signal_foundry_brainstorm._llm_call",
                            side_effect=_fake_llm_call):
                # Do NOT mock screen_candidate — use real screen so it rejects bad spec
                rc = main(["--root", str(root), "--trigger", "operator"])

        assert rc == 0
        candidates = _read_candidates(root)
        # Must have at least one screen_rejected row
        rejected = [c for c in candidates if c.get("status") == "screen_rejected"]
        assert len(rejected) >= 1, f"expected screen_rejected, got: {candidates}"


# ---------------------------------------------------------------------------
# Test: full path — mock LLM, spec passes screen → proposed
# ---------------------------------------------------------------------------

class TestFullPath:
    def test_admitted_spec_filed_as_proposed(self, tmp_path: Path) -> None:
        """A spec that passes the screen is filed with status='proposed'."""
        root = _make_root_auto_loop(tmp_path)
        iso_week = _current_iso_week()

        # A minimal spec with enough fields to pass the screen
        # We mock screen_candidate to always admit
        good_spec = {
            "id": "SF-0001",
            "name": "credit-spread-predictor",
            "name_zh": "信用利差预测",
            "thesis": "Widening credit spreads predict negative excess equity returns.",
            "mechanism": "risk-off contagion from credit to equity",
            "seed_provenance": {"source": "causal_mechanisms.jsonl", "ref": "edge-001"},
            "data": [{"path": "data/fred/BAMLH0A0HYM2.parquet", "column": "value", "pit": "lagged"}],
            "feature": {"pipeline": [["zscore", {"window": 252}], ["lag", {"n": 1}]]},
            "target": {"path": "data/yahoo/SPY.parquet", "kind": "excess_return", "horizon_d": 21},
            "universe": "single_series",
            "baseline": "buy_and_hold",
            "gates": {"min_t_hac": 2.0, "fdr_q": 0.10, "dsr": 0.90},
            "horizon_role": "swing",
            "orthogonality_note": "distinct from price momentum",
            "evidence_note": "Gilchrist & Zakrajsek (2012) excess bond premium",
            "registered_at": "2026-07-10",
        }

        gen_output = json.dumps([good_spec])
        skep_output = json.dumps([{
            "spec_id": "SF-0001",
            "recommendation": "ADVISORY_KEEP",
            "blockers": [],
        }])
        comp_output = json.dumps([good_spec])

        def _fake_llm_call(providers, system, user, max_tokens, context):
            if context == "sf_generator":
                return (gen_output, None, "oauth", {"input_tokens": 100, "output_tokens": 200})
            elif context == "sf_skeptic":
                return (skep_output, None, "oauth", {})
            elif context == "sf_compiler":
                return (comp_output, None, "oauth", {})
            return (None, "unknown", None, {})

        fake_providers = [{"name": "oauth", "model": "claude-sonnet-4-6"}]

        # Mock screen_candidate to admit
        admit_result = {
            "admit": True,
            "verdict": "admitted",
            "reasons": [],
            "gates_passed": ["data_path_tracked", "pit_plan", "sample_5y",
                             "baseline_named", "novelty", "orthogonality_noted", "evidence_noted"],
            "gates_failed": [],
            "construction_hash": "abc123",
        }

        with mock.patch("scripts.run_signal_foundry_brainstorm._build_operator_providers",
                        return_value=fake_providers):
            with mock.patch("scripts.run_signal_foundry_brainstorm._llm_call",
                            side_effect=_fake_llm_call):
                with mock.patch("scripts.run_signal_foundry_brainstorm.screen_candidate",
                                return_value=admit_result):
                    rc = main(["--root", str(root), "--trigger", "operator"])

        assert rc == 0
        candidates = _read_candidates(root)
        proposed = [c for c in candidates if c.get("status") == "proposed"]
        assert len(proposed) >= 1

        gov = _read_governance(root)
        events = [g for g in gov if g.get("event") == "sf_llm_proposed"]
        assert len(events) >= 1

        status = _read_lane_status(root)
        assert status.get("status") == "full"

    def test_dry_run_does_not_write_candidates(self, tmp_path: Path) -> None:
        """Dry-run mode builds the pack and runs LLM chain but does not write candidates.jsonl."""
        root = _make_root_auto_loop(tmp_path)

        good_spec = {
            "id": "SF-0001",
            "name": "dry-run-test",
            "thesis": "test thesis",
            "mechanism": "test mechanism",
            "data": [{"path": "data/fred/test.parquet", "column": "value", "pit": "lagged"}],
            "feature": {"pipeline": [["zscore", {"window": 252}]]},
            "target": {"path": "data/yahoo/SPY.parquet", "kind": "excess_return", "horizon_d": 21},
            "universe": "single_series",
            "baseline": "buy_and_hold",
            "gates": {"min_t_hac": 2.0, "fdr_q": 0.10, "dsr": 0.90},
            "orthogonality_note": "distinct",
            "evidence_note": "test",
            "registered_at": "2026-07-10",
        }
        gen_output = json.dumps([good_spec])
        skep_output = json.dumps([{"spec_id": "SF-0001", "recommendation": "ADVISORY_KEEP", "blockers": []}])
        comp_output = json.dumps([good_spec])

        def _fake_llm_call(providers, system, user, max_tokens, context):
            mapping = {
                "sf_generator": gen_output,
                "sf_skeptic": skep_output,
                "sf_compiler": comp_output,
            }
            return (mapping.get(context), None, "oauth", {})

        fake_providers = [{"name": "oauth", "model": "claude-sonnet-4-6"}]
        admit_result = {"admit": True, "verdict": "admitted", "reasons": [],
                        "gates_passed": [], "gates_failed": [], "construction_hash": "x"}

        with mock.patch("scripts.run_signal_foundry_brainstorm._build_operator_providers",
                        return_value=fake_providers):
            with mock.patch("scripts.run_signal_foundry_brainstorm._llm_call",
                            side_effect=_fake_llm_call):
                with mock.patch("scripts.run_signal_foundry_brainstorm.screen_candidate",
                                return_value=admit_result):
                    rc = main(["--root", str(root), "--trigger", "operator", "--dry-run"])

        assert rc == 0
        candidates_path = root / "data" / "signal_foundry" / "candidates.jsonl"
        # dry_run → candidates.jsonl should NOT exist
        assert not candidates_path.exists()

    def test_governance_written_to_sf_not_neuralweb(self, tmp_path: Path) -> None:
        """Governance events go to data/signal_foundry/governance.jsonl, not neuralweb."""
        root = _make_root_auto_loop(tmp_path)

        good_spec = {
            "id": "SF-0001",
            "name": "gov-test",
            "thesis": "t",
            "mechanism": "m",
            "data": [{"path": "data/fred/test.parquet", "column": "value", "pit": "lagged"}],
            "feature": {"pipeline": [["zscore", {"window": 252}]]},
            "target": {"path": "data/yahoo/SPY.parquet", "kind": "excess_return", "horizon_d": 21},
            "universe": "single_series",
            "baseline": "buy_and_hold",
            "gates": {"min_t_hac": 2.0, "fdr_q": 0.10, "dsr": 0.90},
            "orthogonality_note": "ok",
            "evidence_note": "ok",
            "registered_at": "2026-07-10",
        }
        gen_output = json.dumps([good_spec])
        skep_output = json.dumps([{"spec_id": "SF-0001", "recommendation": "ADVISORY_KEEP", "blockers": []}])
        comp_output = json.dumps([good_spec])

        def _fake_llm_call(providers, system, user, max_tokens, context):
            mapping = {"sf_generator": gen_output, "sf_skeptic": skep_output, "sf_compiler": comp_output}
            return (mapping.get(context), None, "oauth", {})

        fake_providers = [{"name": "oauth", "model": "claude-sonnet-4-6"}]
        admit_result = {"admit": True, "verdict": "admitted", "reasons": [],
                        "gates_passed": [], "gates_failed": [], "construction_hash": "y"}

        with mock.patch("scripts.run_signal_foundry_brainstorm._build_operator_providers",
                        return_value=fake_providers):
            with mock.patch("scripts.run_signal_foundry_brainstorm._llm_call",
                            side_effect=_fake_llm_call):
                with mock.patch("scripts.run_signal_foundry_brainstorm.screen_candidate",
                                return_value=admit_result):
                    rc = main(["--root", str(root), "--trigger", "operator"])

        assert rc == 0
        sf_gov = root / "data" / "signal_foundry" / "governance.jsonl"
        nw_gov = root / "data" / "neuralweb" / "governance.jsonl"
        assert sf_gov.exists(), "signal_foundry/governance.jsonl should exist"
        assert not nw_gov.exists(), "neuralweb/governance.jsonl must NOT be written by Foundry (SF-R10)"
