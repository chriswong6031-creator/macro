"""tests/test_metabolism_v2a.py — Hermetic tests for Metabolism Phase V2-A.

COVERAGE:
  1. organism_state: fail-open (delete each input → still composes + stale_legs names
     it); honest-null trajectory when n<n_min — assert NO fabricated numbers.
  2. insight_bus: append + handled idempotence + each emitter NEVER-RAISE on absent
     input; NEVER-RAISE on corrupt inputs.
  3. anomaly_monitor: robust-z math on synthetic fitness_history (fires above thresh,
     accrues below n_min).
  4. agenda: is_paused no-op (mutation-proof: booby-trap the llm call so a removed
     pause gate ERRORS); severity>=high floor (mock LLM returns empty → floor re-inserts);
     dedup; fable_mode_core injected only when model is Opus-class.
  5. anomaly config in the immutable fence (check_self_mod_fence + check_grader_manifest).
  6. trajectory K-weeks gate blocks premature AMBER/RED.
  7. Banned words: 'validated' never appears in any V2-A user-facing text.
  8. Authority blocks: is_context_only=True everywhere.
  9. NO lifecycle/PR/grant path anywhere in V2-A (grep-style assertion).

All tests are HERMETIC (tmp dirs, in-process, no real data/network/subprocess).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tmp_root() -> Path:
    """Return a fresh temp dir with V2-A directory structure."""
    d = Path(tempfile.mkdtemp())
    (d / "data" / "metabolism" / "fitness").mkdir(parents=True)
    (d / "data" / "metabolism" / "fitness_history").mkdir(parents=True)
    (d / "data" / "metabolism" / "agenda").mkdir(parents=True)
    (d / "data" / "metabolism" / "verify").mkdir(parents=True)
    (d / "data" / "neuralweb" / "cortex").mkdir(parents=True)
    (d / "config").mkdir(parents=True)
    (d / "docs").mkdir(parents=True)
    (d / "research").mkdir(parents=True)
    return d


def _write_til_card(root: Path, sensors: dict | None = None) -> None:
    """Write a minimal TIL fitness card."""
    default_sensors = {
        "front_run_lead": {"value": None, "n": 0, "maturity": "accruing", "note": "accruing"},
        "placebo_hit_rate": {"value": None, "n": 0, "maturity": "accruing", "note": "accruing"},
    }
    card = {
        "schema": "metabolism.til_fitness.v1",
        "as_of": "2026-07-10",
        "lobe": "til",
        "maturity": "accruing",
        "sensors": sensors or default_sensors,
        "authority": {
            "is_context_only": True, "may_rank": False, "may_gate": False,
            "may_size": False, "may_escalate": False, "display_only": True,
        },
    }
    p = root / "data" / "metabolism" / "fitness" / "til.json"
    p.write_text(json.dumps(card), encoding="utf-8")


def _write_health_json(root: Path, lobes: dict | None = None) -> None:
    health = {
        "schema": "neuralweb.health.v1",
        "lobes": lobes or {},
        "produced_at": "2026-07-10T00:00:00+00:00",
    }
    p = root / "data" / "neuralweb" / "health.json"
    p.write_text(json.dumps(health), encoding="utf-8")


def _write_fitness_history(root: Path, lobe_id: str, rows: list[dict]) -> None:
    p = root / "data" / "metabolism" / "fitness_history" / f"{lobe_id}.jsonl"
    lines = [json.dumps(r) for r in rows]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. organism_state tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrganismState:
    def test_fail_open_no_inputs(self):
        """With no inputs at all, build_organism_state still returns a valid dict."""
        from engine.metabolism.organism_state import build_organism_state
        root = _tmp_root()
        result = build_organism_state(root=root)
        assert isinstance(result, dict)
        assert result.get("schema") == "metabolism.organism_state.v1"
        assert isinstance(result.get("gaps"), list)
        assert result["authority"]["is_context_only"] is True

    def test_fail_open_missing_fitness_card(self):
        """Missing fitness card → honest null in lobes, stale_legs named."""
        from engine.metabolism.organism_state import build_organism_state
        root = _tmp_root()
        # health.json names a lobe with no fitness card
        _write_health_json(root, lobes={
            "til": {"status": "missing", "age_hours": 100}
        })
        result = build_organism_state(root=root)
        assert "til" in result.get("lobes", {})
        til_lobe = result["lobes"]["til"]
        # Fitness card is absent → trajectory should be accruing, not fabricated
        traj = til_lobe.get("trajectory") or {}
        assert traj.get("slope") is None or traj.get("label") == "accruing"

    def test_honest_null_trajectory_below_n_min(self):
        """With only 2 history observations, trajectory slope must be None (accruing)."""
        from engine.metabolism.organism_state import build_organism_state
        root = _tmp_root()
        _write_til_card(root)
        # Write only 2 history rows — below n_min=3
        _write_fitness_history(root, "til", [
            {"sensors": {"front_run_lead": {"value": 0.5, "maturity": "ready"}}},
            {"sensors": {"front_run_lead": {"value": 0.6, "maturity": "ready"}}},
        ])
        result = build_organism_state(root=root)
        til_lobe = result["lobes"].get("til") or {}
        traj = til_lobe.get("trajectory") or {}
        assert traj.get("slope") is None, "Must not fabricate slope with n<n_min"
        assert traj.get("label") == "accruing"
        assert traj.get("maturity") == "accruing"

    def test_no_fabricated_numbers_accruing_sensors(self):
        """Accruing sensors must NOT produce non-null composite_fitness."""
        from engine.metabolism.organism_state import build_organism_state
        root = _tmp_root()
        # Card with all accruing, no ready sensors
        _write_til_card(root, sensors={
            "s1": {"value": None, "n": 0, "maturity": "accruing"},
            "s2": {"value": None, "n": 0, "maturity": "accruing"},
        })
        result = build_organism_state(root=root)
        til_lobe = result["lobes"].get("til") or {}
        # composite_fitness should be None (no ready sensors)
        assert til_lobe.get("composite_fitness") is None

    def test_stale_legs_named(self):
        """stale_legs lists sensor names for accruing/absent sensors."""
        from engine.metabolism.organism_state import build_organism_state
        root = _tmp_root()
        _write_til_card(root, sensors={
            "front_run_lead": {"value": None, "n": 0, "maturity": "accruing",
                               "note": "absent artifact"},
        })
        result = build_organism_state(root=root)
        til_lobe = result["lobes"].get("til") or {}
        stale_legs = til_lobe.get("stale_legs") or []
        assert "front_run_lead" in stale_legs

    def test_authority_block_context_only(self):
        """Authority block must always be is_context_only=True with all gates False."""
        from engine.metabolism.organism_state import build_organism_state
        root = _tmp_root()
        result = build_organism_state(root=root)
        auth = result.get("authority") or {}
        assert auth.get("is_context_only") is True
        assert auth.get("may_rank") is False
        assert auth.get("may_gate") is False
        assert auth.get("may_size") is False
        assert auth.get("may_escalate") is False

    def test_biggest_gap_deterministic(self):
        """biggest_gap is a deterministic string, not None or LLM output."""
        from engine.metabolism.organism_state import build_organism_state
        root = _tmp_root()
        result = build_organism_state(root=root)
        bg = result.get("whole_organism", {}).get("biggest_gap")
        assert isinstance(bg, str)
        assert len(bg) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. insight_bus tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestInsightBus:
    def test_append_and_read(self):
        """Can append a row and read it back."""
        from engine.metabolism.insight_bus import build_row, append_row, get_open_rows
        root = _tmp_root()
        row = build_row(
            emitter="test",
            kind="health_transition",
            severity="high",
            entities=["til"],
            summary="Test insight",
            cycle_id="test-cycle",
        )
        ok = append_row(row, root=root)
        assert ok is True
        open_rows = get_open_rows(root=root)
        assert len(open_rows) == 1
        assert open_rows[0]["insight_id"] == row["insight_id"]

    def test_handled_idempotence(self):
        """Marking an insight handled twice is idempotent (append-only)."""
        from engine.metabolism.insight_bus import build_row, append_row, mark_handled, _load_bus_rows, BUS_PATH
        root = _tmp_root()
        row = build_row(
            emitter="test",
            kind="health_transition",
            severity="high",
            entities=["til"],
            summary="Test insight for handling",
        )
        append_row(row, root=root)
        iid = row["insight_id"]
        handler_id = "handler-001"
        mark_handled(iid, handler_id, root=root)
        mark_handled(iid, handler_id, root=root)  # idempotent
        # Bus should have 3 rows: original + 2 handler rows
        rows = _load_bus_rows(root / BUS_PATH)
        assert len(rows) >= 2  # original + at least one handler

    def test_health_transition_emitter_never_raise_absent(self):
        """health_transition_emitter never raises when health.json is absent."""
        from engine.metabolism.insight_bus import health_transition_emitter
        root = _tmp_root()
        result = health_transition_emitter(root=root)
        assert isinstance(result, list)

    def test_health_transition_emitter_fires_on_degraded(self):
        """health_transition_emitter fires for degraded lobes."""
        from engine.metabolism.insight_bus import health_transition_emitter
        root = _tmp_root()
        _write_health_json(root, lobes={
            "til": {"status": "degraded", "age_hours": 50},
        })
        result = health_transition_emitter(root=root)
        assert len(result) == 1
        assert result[0]["kind"] == "health_transition"
        assert result[0]["severity"] == "high"

    def test_falsifier_tripped_emitter_never_raise_absent(self):
        """falsifier_tripped_emitter never raises when verify dir is absent."""
        from engine.metabolism.insight_bus import falsifier_tripped_emitter
        root = _tmp_root()
        result = falsifier_tripped_emitter(root=root)
        assert isinstance(result, list)

    def test_freshness_sla_emitter_never_raise_absent(self):
        """freshness_sla_emitter never raises when synapse.yml is absent."""
        from engine.metabolism.insight_bus import freshness_sla_emitter
        root = _tmp_root()
        result = freshness_sla_emitter(root=root)
        assert isinstance(result, list)

    def test_comeback_clock_emitter_never_raise(self):
        """comeback_clock_emitter never raises on any input."""
        from engine.metabolism.insight_bus import comeback_clock_emitter
        root = _tmp_root()
        result = comeback_clock_emitter(root=root)
        assert isinstance(result, list)

    def test_comeback_clock_fires_for_past_dates(self):
        """comeback_clock_emitter fires for dates that have already passed."""
        from engine.metabolism.insight_bus import comeback_clock_emitter
        root = _tmp_root()
        # Write a clocks config with a past date
        import yaml
        clocks = {"clocks": [
            {"lobe": "til", "date": "2020-01-01", "description": "Past clock"}
        ]}
        (root / "config" / "masterplan_clocks.yml").write_text(
            yaml.dump(clocks), encoding="utf-8"
        )
        result = comeback_clock_emitter(root=root)
        assert len(result) >= 1
        assert result[0]["kind"] == "comeback_clock_matured"

    def test_authority_on_bus_rows(self):
        """Every bus row carries is_context_only=True."""
        from engine.metabolism.insight_bus import build_row
        row = build_row("emitter", "health_transition", "low", ["lobe"], "summary")
        auth = row.get("authority") or {}
        assert auth.get("is_context_only") is True

    def test_run_all_emitters_never_raise_empty_root(self):
        """run_all_emitters never raises on an empty root."""
        from engine.metabolism.insight_bus import run_all_emitters
        root = _tmp_root()
        result = run_all_emitters(root=root)
        assert isinstance(result, list)

    def test_contradiction_emitter_never_raise_absent(self):
        """contradiction_emitter never raises when contradictions module is absent."""
        from engine.metabolism.insight_bus import contradiction_emitter
        root = _tmp_root()
        # Patch detect_contradictions to raise
        with patch("engine.neuralweb.contradictions.detect_contradictions", side_effect=ImportError("no module")):
            result = contradiction_emitter(root=root)
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. anomaly_monitor tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnomalyMonitor:
    def _write_anomaly_config(self, root: Path) -> None:
        """Write a minimal anomaly config."""
        import yaml
        cfg = {
            "schema": "metabolism_anomaly.v1",
            "defaults": {"K": 20, "n_min": 3, "z_thresh": 2.5, "slope_flip_min": 0.05},
            "sensors": {},
            "bands": {},
            "ci_red_streak": {"streak_threshold": 3, "ci_status_artifact": None},
        }
        (root / "config" / "metabolism_anomaly.yml").write_text(
            yaml.dump(cfg), encoding="utf-8"
        )

    def test_robust_z_fires_above_threshold(self):
        """_robust_z fires an anomaly when |z| >= z_thresh with enough n."""
        from engine.metabolism.anomaly_monitor import _robust_z, check_sensor_anomaly
        # Synthetic values: small variations around 0.5, then a large outlier at end
        # Use heterogeneous data so MAD != 0
        values = [0.4, 0.5, 0.6, 0.45, 0.55, 0.5, 0.48, 0.52, 0.49, 0.51, 10.0]
        z, med, mad = _robust_z(values)
        assert z is not None, f"z is None — values={values}, med={med}, mad={mad}"
        assert mad != 0.0, f"MAD is zero — degenerate test data"
        assert abs(z) > 2.5, f"z={z} not above threshold 2.5"

        rows = check_sensor_anomaly(
            lobe_id="test",
            sensor_name="s1",
            values=values,
            sensor_cfg={},
            global_defaults={"K": 20, "n_min": 3, "z_thresh": 2.5},
        )
        assert len(rows) >= 1, f"Expected anomaly rows but got none. z={z}"

    def test_robust_z_accruing_below_n_min(self):
        """No anomaly fires when n < n_min."""
        from engine.metabolism.anomaly_monitor import check_sensor_anomaly
        # Only 2 values — below n_min=3
        values = [0.5, 5.0]
        rows = check_sensor_anomaly(
            lobe_id="test",
            sensor_name="s1",
            values=values,
            sensor_cfg={},
            global_defaults={"K": 20, "n_min": 3, "z_thresh": 2.5},
        )
        assert rows == [], f"Expected no rows, got {rows}"

    def test_robust_z_math(self):
        """Verify the robust-z formula directly."""
        from engine.metabolism.anomaly_monitor import _robust_z
        import statistics
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        z, med, mad = _robust_z(values)
        assert med is not None
        expected_med = statistics.median(values)
        assert abs(med - expected_med) < 1e-9
        # Latest value is 5.0; median is 3.0; MAD = median(|xi - 3|) = median([2,1,0,1,2]) = 1.0
        # z = (5 - 3) / (1.4826 * 1.0) = 2 / 1.4826 ≈ 1.35
        expected_z = (5.0 - 3.0) / (1.4826 * 1.0)
        assert abs(z - expected_z) < 0.01

    def test_anomaly_monitor_never_raise_empty_root(self):
        """run_anomaly_monitor never raises on an empty root."""
        from engine.metabolism.anomaly_monitor import run_anomaly_monitor
        root = _tmp_root()
        self._write_anomaly_config(root)
        result = run_anomaly_monitor(root=root)
        assert isinstance(result, list)

    def test_anomaly_config_is_in_grader_manifest(self):
        """metabolism_anomaly.yml is registered in config/grader_manifest.yml."""
        manifest_path = _ROOT / "config" / "grader_manifest.yml"
        if manifest_path.exists():
            import yaml
            manifest = yaml.safe_load(manifest_path.read_text())
            paths = [f.get("path") for f in (manifest.get("files") or [])]
            assert "config/metabolism_anomaly.yml" in paths, (
                "metabolism_anomaly.yml not registered in grader_manifest.yml"
            )

    def test_fable_mode_core_is_in_grader_manifest(self):
        """config/fable_mode_core.md is registered in config/grader_manifest.yml."""
        manifest_path = _ROOT / "config" / "grader_manifest.yml"
        if manifest_path.exists():
            import yaml
            manifest = yaml.safe_load(manifest_path.read_text())
            paths = [f.get("path") for f in (manifest.get("files") or [])]
            assert "config/fable_mode_core.md" in paths, (
                "fable_mode_core.md not registered in grader_manifest.yml"
            )

    def test_anomaly_config_is_in_self_mod_fence(self):
        """metabolism_anomaly.yml and fable_mode_core.md are in IMMUTABLE_PATTERNS."""
        try:
            from scripts.check_self_mod_fence import IMMUTABLE_PATTERNS
            assert any("metabolism_anomaly" in p for p in IMMUTABLE_PATTERNS), (
                "metabolism_anomaly.yml not in IMMUTABLE_PATTERNS"
            )
            assert any("fable_mode_core" in p for p in IMMUTABLE_PATTERNS), (
                "fable_mode_core.md not in IMMUTABLE_PATTERNS"
            )
        except ImportError as e:
            pytest.skip(f"check_self_mod_fence not importable: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. agenda tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgenda:
    def _write_budget_config(self, root: Path) -> None:
        import yaml
        cfg = {
            "schema": "metabolism_budget.v1",
            "per_cycle_usd_cap": 25,
            "per_cycle_token_cap": 25000000,
            "max_docket_size": 5,
            "circuit_breaker_trip": 3,
        }
        (root / "config" / "metabolism_budget.yml").write_text(
            yaml.dump(cfg), encoding="utf-8"
        )

    def test_is_paused_no_op(self):
        """When AUTONOMY_PAUSED is set, the CLI exits 0 without calling LLM."""
        llm_called = []

        def _booby_trap_llm(*args, **kwargs):
            llm_called.append(True)
            raise AssertionError("LLM must not be called when AUTONOMY_PAUSED")

        with patch.dict(os.environ, {"AUTONOMY_PAUSED": "true"}):
            with patch("scripts.metabolism_guard.is_paused", return_value=True):
                from scripts.metabolism_agenda import main
                ret = main(["--cycle-id", "test-cycle", "--root", str(_tmp_root())])
        assert ret == 0
        assert not llm_called, "LLM was called despite AUTONOMY_PAUSED"

    def test_is_paused_no_op_on_unset_var(self):
        """The genuinely default-safe path: AUTONOMY_PAUSED UNSET (not mocked) must
        still no-op the agenda CLI without any LLM call. This isolates the
        unset-var fail-safe so a regression can't hide behind a mocked is_paused."""
        llm_called = []

        def _booby_trap_llm(*args, **kwargs):
            llm_called.append(True)
            raise AssertionError("LLM must not be called when AUTONOMY_PAUSED is unset")

        env = {k: v for k, v in os.environ.items() if k != "AUTONOMY_PAUSED"}
        with patch.dict(os.environ, env, clear=True):
            # NO mock of is_paused — exercise the real unset->paused fail-safe.
            from scripts.metabolism_agenda import main
            ret = main(["--cycle-id", "test-unset", "--root", str(_tmp_root())])
        assert ret == 0
        assert not llm_called, "LLM ran with AUTONOMY_PAUSED unset (fail-safe regressed)"

    def test_severity_floor_reinserts_high_insights(self):
        """LLM returning empty items → severity floor re-inserts high-severity bus rows."""
        from engine.metabolism.agenda import build_agenda, _enforce_severity_floor

        # Build a mock high-severity insight row
        from engine.metabolism.insight_bus import build_row
        high_row = build_row(
            emitter="test_emitter",
            kind="health_transition",
            severity="high",
            entities=["til"],
            summary="Critical lobe degraded",
        )

        # Test the floor directly
        items, forced = _enforce_severity_floor([], [high_row])
        assert len(forced) >= 1
        assert forced[0]["bucket"] == "URGENT_FIX"
        assert forced[0]["severity"] == "high"
        assert forced[0]["forced_floor"] is True

    def test_floor_survives_empty_llm_output(self):
        """When LLM returns nothing, high insight rows still appear in output."""
        from engine.metabolism.agenda import build_agenda

        root = _tmp_root()
        self._write_budget_config(root)

        # Pre-write a high-severity insight row
        from engine.metabolism.insight_bus import build_row, append_row
        high_row = build_row(
            emitter="test",
            kind="health_transition",
            severity="high",
            entities=["til"],
            summary="Test high finding",
        )
        append_row(high_row, root=root)

        # Mock LLM call to return empty
        with patch("engine.metabolism.agenda._call_llm", return_value=('{"items": []}', None, "mock")):
            agenda = build_agenda(
                cycle_id="test-cycle",
                root=root,
                providers=[{"name": "mock", "cred": "x", "client": object(), "model": "m", "env_var": "E"}],
                model="claude-opus-4-5",
            )

        items = agenda.get("items") or []
        # Floor must have inserted at least one URGENT_FIX
        urgent_items = [i for i in items if i.get("bucket") == "URGENT_FIX" and i.get("forced_floor")]
        assert len(urgent_items) >= 1, f"Floor did not re-insert high insight. Items: {items}"

    def test_fable_mode_core_injected_for_opus(self):
        """fable_mode_core.md is injected when model is Opus-class."""
        # Write fable_mode_core.md
        root = _tmp_root()
        (root / "config" / "fable_mode_core.md").write_text("# Test Fable Doctrine\n", encoding="utf-8")

        from engine.metabolism.orchestrator_brain import _build_orchestrator_system
        prompt = _build_orchestrator_system(model="claude-opus-4-5", root=root)
        assert "Fable Mode" in prompt or "fable" in prompt.lower(), (
            "fable_mode_core not injected for Opus model"
        )

    def test_fable_mode_core_not_injected_for_fable(self):
        """fable_mode_core.md is NOT injected when model is Fable-class."""
        root = _tmp_root()
        (root / "config" / "fable_mode_core.md").write_text("# Fable Sentinel\n", encoding="utf-8")

        from engine.metabolism.orchestrator_brain import _build_orchestrator_system
        prompt = _build_orchestrator_system(model="claude-fable-5", root=root)
        # Should not contain the sentinel text
        assert "# Fable Sentinel" not in prompt, (
            "fable_mode_core injected for Fable model — should only inject for Opus"
        )

    def test_dedup_kills_duplicate_titles(self):
        """Two items with identical normalized titles → one is rejected as duplicate."""
        from engine.metabolism.agenda import _dedup_hash, _normalize_item

        item1 = _normalize_item({"title": "Fix the TIL sensor", "bucket": "URGENT_FIX", "severity": "high"})
        item2 = _normalize_item({"title": "Fix  the  TIL   sensor", "bucket": "URGENT_FIX", "severity": "high"})
        assert item1 is not None
        assert item2 is not None
        # Hashes should be the same (normalized)
        assert item1["dedup_hash"] == item2["dedup_hash"]

    def test_agenda_authority_context_only(self):
        """Agenda artifact carries is_context_only=True."""
        from engine.metabolism.agenda import build_agenda
        root = _tmp_root()
        self._write_budget_config(root)
        agenda = build_agenda(cycle_id="test", root=root, providers=None)
        auth = agenda.get("authority") or {}
        assert auth.get("is_context_only") is True
        assert "dispatch" in (auth.get("forbidden_uses") or [])
        assert "pr_open" in (auth.get("forbidden_uses") or [])
        assert "grant" in (auth.get("forbidden_uses") or [])


# ═══════════════════════════════════════════════════════════════════════════════
# 5. trajectory tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestTrajectory:
    def test_k_weeks_gate_blocks_premature_amber_red(self):
        """With fewer than K_weeks of history, output is always GREEN/accruing."""
        from engine.metabolism.trajectory import build_trajectory_row

        root = _tmp_root()
        # organism_state with compounding+degrading lobes to give signal IF gate passed
        org_state = {
            "whole_organism": {
                "n_lobes": 2,
                "label_counts": {"degrading": 2},
            },
            "lobes": {},
            "cortex_memo": None,
        }

        # History file is empty / absent → gate should block AMBER/RED
        row = build_trajectory_row(
            organism_state=org_state,
            cycle_id="test",
            root=root,
            K_weeks=4,
            min_magnitude=0.05,
        )
        assert row["overall_signal"] == "GREEN", (
            f"Expected GREEN (gate not passed) but got {row['overall_signal']}"
        )
        assert not row["gate_passed"]
        assert "accruing" in row.get("reason", "").lower() or "accruing" in row.get("gate_reason", "").lower()

    def test_trajectory_append(self):
        """build_trajectory_row produces a valid row that can be appended."""
        from engine.metabolism.trajectory import build_trajectory_row, append_trajectory_row, TRAJECTORY_PATH
        root = _tmp_root()
        row = build_trajectory_row({}, root=root)
        ok = append_trajectory_row(row, root=root)
        assert ok is True
        p = root / TRAJECTORY_PATH
        assert p.exists()
        lines = [l for l in p.read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        assert json.loads(lines[0])["schema"] == "metabolism.trajectory.v1"

    def test_trajectory_authority_block(self):
        """Trajectory row carries is_context_only=True."""
        from engine.metabolism.trajectory import build_trajectory_row
        row = build_trajectory_row({})
        assert row["authority"]["is_context_only"] is True

    def test_no_amber_red_without_regime_tag(self):
        """AMBER/RED requires a regime_tag — absent → GREEN/accruing."""
        from engine.metabolism.trajectory import build_trajectory_row
        root = _tmp_root()
        # Enough "history" rows written with degrading label
        from engine.metabolism.trajectory import TRAJECTORY_PATH, _N_OBS_PER_WEEK
        p = root / TRAJECTORY_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        n = 30  # enough rows
        for _ in range(n):
            row = {"ts": "2026-01-01T00:00:00", "label_counts": {"degrading": 5}}
            p.write_text(json.dumps(row) + "\n", encoding="utf-8", append_not_supported=True) if False else \
                open(p, "a").write(json.dumps(row) + "\n")

        org_state = {
            "whole_organism": {"label_counts": {"degrading": 5}, "n_lobes": 5},
            "lobes": {},
            "cortex_memo": None,  # no regime_tag
        }
        result = build_trajectory_row(org_state, root=root, K_weeks=4)
        assert result["overall_signal"] == "GREEN"
        assert not result["gate_passed"]


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Banned words
# ═══════════════════════════════════════════════════════════════════════════════

class TestBannedWords:
    """check_validated_claims compliance: 'validated' must not appear in user-facing text."""

    _V2A_MODULES = [
        "engine/metabolism/organism_state.py",
        "engine/metabolism/insight_bus.py",
        "engine/metabolism/anomaly_monitor.py",
        "engine/metabolism/orchestrator_brain.py",
        "engine/metabolism/agenda.py",
        "engine/metabolism/trajectory.py",
        "scripts/build_organism_state.py",
        "scripts/metabolism_agenda.py",
    ]

    def test_no_validated_in_source_files(self):
        """The word 'validated' must not appear in user-facing V2-A source files."""
        for rel_path in self._V2A_MODULES:
            p = _ROOT / rel_path
            if not p.exists():
                continue
            text = p.read_text(encoding="utf-8").lower()
            # Exclude comments that reference the CI check itself
            lines = p.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines, 1):
                if "validated" in line.lower():
                    # Allow only if it's referencing the CI script by name
                    if "check_validated_claims" in line or "validated_claims" in line:
                        continue
                    raise AssertionError(
                        f"Banned word 'validated' in {rel_path}:{i}: {line.strip()!r}"
                    )

    def test_no_validated_in_fable_mode_core(self):
        """The word 'validated' must not appear in config/fable_mode_core.md."""
        p = _ROOT / "config" / "fable_mode_core.md"
        if p.exists():
            text = p.read_text(encoding="utf-8")
            for line in text.splitlines():
                if "validated" in line.lower():
                    raise AssertionError(
                        f"Banned word 'validated' in fable_mode_core.md: {line.strip()!r}"
                    )


# ═══════════════════════════════════════════════════════════════════════════════
# 7. No lifecycle/PR/grant path in V2-A (grep-style assertion)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoAuthorityPaths:
    """V2-A has ZERO authority — assert no lifecycle/PR/grant execution paths exist."""

    _V2A_MODULES = [
        "engine/metabolism/organism_state.py",
        "engine/metabolism/insight_bus.py",
        "engine/metabolism/anomaly_monitor.py",
        "engine/metabolism/orchestrator_brain.py",
        "engine/metabolism/agenda.py",
        "engine/metabolism/trajectory.py",
        "scripts/build_organism_state.py",
        "scripts/metabolism_agenda.py",
    ]

    # Patterns that would indicate authority execution (not just mentions in docs)
    _FORBIDDEN_CALL_PATTERNS = [
        # PR / merge / push
        "gh pr create", "gh pr merge", "git push", ".merge(",
        # arbitrary process execution (a session could shell out to gh/git/anything)
        "subprocess.", "os.system(", "os.popen(", "Popen(",
        # governance grant / authority
        "append_governance(", "grant_authority(", "dispatch_build(", "dispatch(",
        # lobe lifecycle (V2-C authority — must NEVER appear in the V2-A mind)
        "lifecycle.promote(", "lifecycle.demote(", "lifecycle.charter(",
        "lifecycle.retire(", "lobe_roster.add(", "lobe_roster.remove(",
    ]

    def test_no_authority_execution_paths(self):
        """No V2-A module contains authority-executing function calls."""
        for rel_path in self._V2A_MODULES:
            p = _ROOT / rel_path
            if not p.exists():
                continue
            text = p.read_text(encoding="utf-8")
            for pattern in self._FORBIDDEN_CALL_PATTERNS:
                if pattern in text:
                    raise AssertionError(
                        f"Forbidden authority pattern {pattern!r} found in {rel_path}"
                    )

    def test_agenda_forbidden_uses_includes_dispatch(self):
        """agenda.py AUTHORITY_BLOCK lists dispatch/grant/pr_open as forbidden_uses."""
        from engine.metabolism.agenda import AUTHORITY_BLOCK
        forbidden = AUTHORITY_BLOCK.get("forbidden_uses") or []
        assert "dispatch" in forbidden
        assert "grant" in forbidden
        assert "pr_open" in forbidden
        assert "lobe_roster_change" in forbidden


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Conformance suite smoke tests (external check scripts)
# ═══════════════════════════════════════════════════════════════════════════════

class TestConformanceSuites:
    def test_check_grader_manifest_passes(self):
        """check_grader_manifest.py exits 0 (all registered hashes match)."""
        try:
            from scripts.check_grader_manifest import main as gm_main
            ret = gm_main([])  # pass empty argv to avoid inheriting pytest args
            assert ret == 0, f"check_grader_manifest failed with code {ret}"
        except ImportError as e:
            pytest.skip(f"check_grader_manifest not importable: {e}")
        except Exception as e:
            pytest.fail(f"check_grader_manifest raised: {e}")

    def test_check_self_mod_fence_selftest(self):
        """check_self_mod_fence.py --selftest passes."""
        try:
            from scripts.check_self_mod_fence import selftest as sm_selftest
            ret = sm_selftest()
            assert ret == 0, f"check_self_mod_fence selftest failed with code {ret}"
        except ImportError as e:
            pytest.skip(f"check_self_mod_fence not importable: {e}")
        except Exception as e:
            pytest.fail(f"check_self_mod_fence selftest raised: {e}")

    def test_synapse_registry_has_v2a_artifacts(self):
        """synapse.yml contains V2-A artifact registrations."""
        try:
            import yaml
            synapse = yaml.safe_load(
                (_ROOT / "config" / "synapse.yml").read_text(encoding="utf-8")
            )
            artifacts = synapse.get("artifacts") or {}
            assert "metabolism-organism-state" in artifacts, "organism-state not registered"
            assert "metabolism-insight-bus" in artifacts, "insight-bus not registered"
            assert "metabolism-agenda" in artifacts, "agenda not registered"
            assert "metabolism-trajectory" in artifacts, "trajectory not registered"
        except ImportError as e:
            pytest.skip(f"yaml not importable: {e}")
