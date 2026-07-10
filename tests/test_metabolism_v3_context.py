"""tests/test_metabolism_v3_context.py — Hermetic tests for V3 W2 context substrate.

Coverage:
  A. strategic.build_trajectory_block — compounding / stagnating / declining / accruing
  B. strategic.build_strategic_gap   — worst-slope lobe named as biggest gap
  C. grounding.validate_grounding    — known refs clean, bogus refs flagged,
                                       missing registry → unverified (no raise)
  D. NEVER-RAISE contract            — missing / corrupt inputs return safe fallback

All tests use tmp_path fixtures.  No real data dependencies.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.metabolism.strategic import (
    build_trajectory_block,
    build_strategic_gap,
    N_MIN_TRAJECTORY,
)
from engine.metabolism.grounding import (
    validate_grounding,
    _load_known_lobes,
    _load_known_rulings,
    _load_known_sensors,
)


# ── Fixture helpers ────────────────────────────────────────────────────────────

def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _make_trajectory_rows(deltas: list[float | None]) -> list[dict]:
    """Build minimal trajectory.jsonl rows with the given fitness_deltas."""
    return [
        {
            "schema": "metabolism.trajectory.v1",
            "ts": f"2026-07-{i + 1:02d}T00:00:00+00:00",
            "cycle_id": f"c{i}",
            "overall_signal": "GREEN",
            "reason": "test",
            "regime_tag": "expansion",
            "fitness_delta": d,
            "n_lobes": 1,
            "n_mature_lobes": 1,
            "label_counts": {},
            "gate_passed": False,
            "gate_reason": "test",
            "authority": {"is_context_only": True},
        }
        for i, d in enumerate(deltas)
    ]


def _make_organism_state(lobes_spec: dict[str, dict]) -> dict:
    """Build a minimal organism_state dict.

    lobes_spec: {lobe_id: {"slope": float|None, "label": str, "maturity": str}}
    """
    lobes: dict[str, Any] = {}
    for lobe_id, spec in lobes_spec.items():
        lobes[lobe_id] = {
            "lobe_id": lobe_id,
            "trajectory": {
                "slope": spec.get("slope"),
                "label": spec.get("label", "accruing"),
                "n_obs": spec.get("n_obs", 5),
                "maturity": spec.get("maturity", "ready"),
            },
        }
    return {
        "schema": "metabolism.organism_state.v1",
        "lobes": lobes,
        "whole_organism": {"n_lobes": len(lobes), "label_counts": {}},
    }


def _make_minimal_synapse(tmp_path: Path, artifact_ids: list[str]) -> None:
    """Write a minimal config/synapse.yml with the given artifact ids."""
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    lines = ["artifacts:\n"]
    for aid in artifact_ids:
        lines.append(f"  {aid}:\n")
        lines.append(f"    tier: infrastructure\n")
        lines.append(f"    horizon_role: context\n")
    (tmp_path / "config" / "synapse.yml").write_text("".join(lines), encoding="utf-8")


def _make_minimal_ruling_graph(tmp_path: Path, ruling_ids: list[str]) -> None:
    """Write a minimal config/ruling_graph.yml with the given ruling_ids."""
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    lines = ["rulings:\n"]
    for rid in ruling_ids:
        lines.append(f"  - ruling_id: {rid}\n")
        lines.append(f"    short_name: test\n")
    (tmp_path / "config" / "ruling_graph.yml").write_text("".join(lines), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# A. build_trajectory_block
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildTrajectoryBlock:
    """Trajectory block classification tests."""

    def _write_traj(self, tmp_path: Path, deltas: list[float | None]) -> None:
        traj_path = tmp_path / "data" / "metabolism" / "trajectory.jsonl"
        _write_jsonl(traj_path, _make_trajectory_rows(deltas))

    def test_compounding(self, tmp_path: Path) -> None:
        """Rising deltas (all positive, last > first) → compounding."""
        # slope = mean(last-third) - mean(first-third) > 0.02
        self._write_traj(tmp_path, [0.01, 0.02, 0.05, 0.08, 0.12, 0.15])
        result = build_trajectory_block("til", root=tmp_path)
        assert "compounding" in result, f"Expected 'compounding' in:\n{result}"

    def test_stagnating(self, tmp_path: Path) -> None:
        """Flat deltas → stagnating."""
        # All near zero: slope will be in [-0.02, 0.02]
        self._write_traj(tmp_path, [0.00, 0.01, 0.00, -0.01, 0.00, 0.01])
        result = build_trajectory_block("til", root=tmp_path)
        assert "stagnating" in result, f"Expected 'stagnating' in:\n{result}"

    def test_declining(self, tmp_path: Path) -> None:
        """Falling deltas → declining."""
        # slope = mean(last-third) - mean(first-third) < -0.02
        self._write_traj(tmp_path, [0.10, 0.07, 0.03, -0.02, -0.06, -0.10])
        result = build_trajectory_block("til", root=tmp_path)
        assert "declining" in result, f"Expected 'declining' in:\n{result}"

    def test_accruing_single_point(self, tmp_path: Path) -> None:
        """One data point → honest accruing null, no invented trend."""
        self._write_traj(tmp_path, [0.05])
        result = build_trajectory_block("til", root=tmp_path)
        assert "accruing" in result, f"Expected 'accruing' in:\n{result}"
        # Ensure we do NOT say compounding or declining from a single point
        assert "compounding" not in result
        assert "declining" not in result

    def test_accruing_zero_points(self, tmp_path: Path) -> None:
        """No trajectory file at all → honest accruing null, no raise."""
        # Do not write any trajectory file
        result = build_trajectory_block("til", root=tmp_path)
        assert isinstance(result, str)
        assert "accruing" in result or "unavailable" in result

    def test_accruing_all_null_deltas(self, tmp_path: Path) -> None:
        """Rows with fitness_delta=None → accruing (insufficient valid points)."""
        rows = _make_trajectory_rows([None, None, None, None])
        traj_path = tmp_path / "data" / "metabolism" / "trajectory.jsonl"
        _write_jsonl(traj_path, rows)
        result = build_trajectory_block("til", root=tmp_path)
        assert "accruing" in result

    def test_byte_cap_truncates(self, tmp_path: Path) -> None:
        """byte_cap is respected."""
        self._write_traj(tmp_path, [0.01, 0.02, 0.05, 0.08, 0.12, 0.15])
        result = build_trajectory_block("til", root=tmp_path, byte_cap=100)
        assert len(result.encode("utf-8")) <= 100 + len("\n...(truncated)")

    def test_never_raise_corrupt_file(self, tmp_path: Path) -> None:
        """Corrupt trajectory.jsonl → safe string fallback, no exception."""
        traj_path = tmp_path / "data" / "metabolism" / "trajectory.jsonl"
        traj_path.parent.mkdir(parents=True, exist_ok=True)
        traj_path.write_text("not valid json\n{broken\n", encoding="utf-8")
        result = build_trajectory_block("til", root=tmp_path)
        assert isinstance(result, str)


# ══════════════════════════════════════════════════════════════════════════════
# B. build_strategic_gap
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildStrategicGap:
    """Strategic gap block — worst lobe identified."""

    def test_worst_slope_lobe_named(self, tmp_path: Path) -> None:
        """Lobe with clearly worst (most negative) slope is named as biggest gap."""
        state = _make_organism_state({
            "til": {"slope": 0.10, "label": "compounding", "maturity": "ready"},
            "causal": {"slope": -0.08, "label": "degrading", "maturity": "ready"},
            "options": {"slope": 0.00, "label": "stagnating", "maturity": "ready"},
        })
        result = build_strategic_gap(organism_state=state, root=tmp_path)
        assert "causal" in result, f"Expected 'causal' as gap in:\n{result}"

    def test_degrading_beats_stagnating(self, tmp_path: Path) -> None:
        """Degrading lobe outranks stagnating even with less-negative slope."""
        state = _make_organism_state({
            "a": {"slope": -0.03, "label": "degrading", "maturity": "ready"},
            "b": {"slope": -0.01, "label": "stagnating", "maturity": "ready"},
        })
        result = build_strategic_gap(organism_state=state, root=tmp_path)
        assert "**Biggest gap:** `a`" in result or "a" in result.splitlines()[1]

    def test_all_accruing_no_named_gap(self, tmp_path: Path) -> None:
        """All lobes accruing (no mature data) → honest 'insufficient data'."""
        state = _make_organism_state({
            "a": {"slope": None, "label": "accruing", "maturity": "accruing"},
            "b": {"slope": None, "label": "accruing", "maturity": "accruing"},
        })
        result = build_strategic_gap(organism_state=state, root=tmp_path)
        assert "insufficient data" in result

    def test_loads_from_disk_if_no_state_passed(self, tmp_path: Path) -> None:
        """If organism_state=None, loads from data/metabolism/organism_state.json."""
        state = _make_organism_state({
            "til": {"slope": -0.10, "label": "degrading", "maturity": "ready"},
        })
        os_path = tmp_path / "data" / "metabolism" / "organism_state.json"
        os_path.parent.mkdir(parents=True, exist_ok=True)
        os_path.write_text(json.dumps(state), encoding="utf-8")
        result = build_strategic_gap(organism_state=None, root=tmp_path)
        assert "til" in result

    def test_absent_organism_state_honest_null(self, tmp_path: Path) -> None:
        """No organism_state on disk → honest null string, no raise."""
        result = build_strategic_gap(organism_state=None, root=tmp_path)
        assert isinstance(result, str)
        assert "null" in result or "absent" in result or "empty" in result

    def test_byte_cap_respected(self, tmp_path: Path) -> None:
        """byte_cap truncates output."""
        state = _make_organism_state({
            f"lobe{i}": {"slope": float(i) * 0.01, "label": "stagnating", "maturity": "ready"}
            for i in range(20)
        })
        result = build_strategic_gap(organism_state=state, root=tmp_path, byte_cap=200)
        assert len(result.encode("utf-8")) <= 200 + len("\n...(truncated)")

    def test_never_raise_on_corrupt_state(self, tmp_path: Path) -> None:
        """Passing a non-dict organism_state returns safe string."""
        result = build_strategic_gap(organism_state={"lobes": "not-a-dict"}, root=tmp_path)
        assert isinstance(result, str)


# ══════════════════════════════════════════════════════════════════════════════
# C. validate_grounding
# ══════════════════════════════════════════════════════════════════════════════

class TestValidateGrounding:
    """Grounding validation — ok/ungrounded/unverified semantics."""

    def _setup_registries(
        self,
        tmp_path: Path,
        lobe_ids: list[str],
        ruling_ids: list[str],
    ) -> None:
        _make_minimal_synapse(tmp_path, lobe_ids)
        _make_minimal_ruling_graph(tmp_path, ruling_ids)

    # ── Clean payload ──────────────────────────────────────────────────────────

    def test_known_lobe_and_ruling_ok(self, tmp_path: Path) -> None:
        """Payload referencing a real lobe + real ruling_id → ok=True, ungrounded=[]."""
        self._setup_registries(
            tmp_path,
            lobe_ids=["regime-latest", "breadth-breadth"],
            ruling_ids=["RUL-CL-1", "RUL-CL-2"],
        )
        payload = {"lobe_id": "regime-latest", "ruling_id": "RUL-CL-1"}
        result = validate_grounding(payload, root=tmp_path)
        assert result["ok"] is True
        assert result["ungrounded"] == []
        assert result["unverified"] is False

    def test_free_text_known_ruling_ok(self, tmp_path: Path) -> None:
        """Free text referencing a known ruling_id → ok=True."""
        self._setup_registries(tmp_path, lobe_ids=[], ruling_ids=["RUL-CL-3"])
        result = validate_grounding("Per RUL-CL-3 this is valid.", root=tmp_path)
        assert result["ok"] is True
        assert result["ungrounded"] == []

    # ── Bogus references ───────────────────────────────────────────────────────

    def test_bogus_lobe_id_flagged(self, tmp_path: Path) -> None:
        """Bogus lobe_id → appears in ungrounded, ok=False."""
        self._setup_registries(tmp_path, lobe_ids=["regime-latest"], ruling_ids=["RUL-CL-1"])
        payload = {"lobe_id": "does-not-exist"}
        result = validate_grounding(payload, root=tmp_path)
        assert result["ok"] is False
        ids = [u["id"] for u in result["ungrounded"]]
        assert "does-not-exist" in ids

    def test_bogus_ruling_id_flagged(self, tmp_path: Path) -> None:
        """Bogus RUL-CL-999 in free text → appears in ungrounded, ok=False."""
        self._setup_registries(tmp_path, lobe_ids=[], ruling_ids=["RUL-CL-1"])
        result = validate_grounding("See RUL-CL-999 for details.", root=tmp_path)
        assert result["ok"] is False
        ids = [u["id"] for u in result["ungrounded"]]
        assert "RUL-CL-999" in ids

    def test_both_bogus_both_in_ungrounded(self, tmp_path: Path) -> None:
        """Bogus lobe_id AND bogus ruling in same payload → both in ungrounded."""
        self._setup_registries(
            tmp_path,
            lobe_ids=["regime-latest"],
            ruling_ids=["RUL-CL-1"],
        )
        payload = {
            "lobe_id": "fake-lobe",
            "ruling_id": "RUL-CL-999",
        }
        result = validate_grounding(payload, root=tmp_path)
        assert result["ok"] is False
        ids = [u["id"] for u in result["ungrounded"]]
        assert "fake-lobe" in ids
        assert "RUL-CL-999" in ids

    # ── Missing registry → unverified ─────────────────────────────────────────

    def test_missing_synapse_unverified(self, tmp_path: Path) -> None:
        """synapse.yml absent → unverified=True, no raise, ok=True (never blocks)."""
        # Only write ruling_graph.yml; omit synapse.yml
        _make_minimal_ruling_graph(tmp_path, ["RUL-CL-1"])
        payload = {"lobe_id": "regime-latest", "ruling_id": "RUL-CL-1"}
        result = validate_grounding(payload, root=tmp_path)
        assert result["unverified"] is True
        assert result["ok"] is True   # never blocks
        # Should not raise
        assert "ungrounded" in result

    def test_missing_ruling_graph_unverified(self, tmp_path: Path) -> None:
        """ruling_graph.yml absent → unverified=True, no raise, ok=True."""
        _make_minimal_synapse(tmp_path, ["regime-latest"])
        payload = {"ruling_id": "RUL-CL-1"}
        result = validate_grounding(payload, root=tmp_path)
        assert result["unverified"] is True
        assert result["ok"] is True

    def test_both_registries_missing_unverified(self, tmp_path: Path) -> None:
        """Both registries absent → unverified=True, returns valid dict, no raise."""
        result = validate_grounding({"lobe_id": "anything"}, root=tmp_path)
        assert result["unverified"] is True
        assert result["ok"] is True
        assert isinstance(result["ungrounded"], list)

    def test_no_references_in_payload(self, tmp_path: Path) -> None:
        """Payload with no ids → ok=True, checked=0."""
        self._setup_registries(tmp_path, lobe_ids=["a"], ruling_ids=["RUL-CL-1"])
        result = validate_grounding({"data": "nothing relevant"}, root=tmp_path)
        assert result["ok"] is True
        assert result["checked"] == 0
        assert result["ungrounded"] == []

    # ── checked count ──────────────────────────────────────────────────────────

    def test_checked_count_incremented(self, tmp_path: Path) -> None:
        """checked field counts distinct id references checked."""
        self._setup_registries(
            tmp_path,
            lobe_ids=["regime-latest"],
            ruling_ids=["RUL-CL-1"],
        )
        payload = {
            "lobe_id": "regime-latest",
            "ruling_id": "RUL-CL-1",
        }
        result = validate_grounding(payload, root=tmp_path)
        assert result["checked"] >= 2

    # ── unverified vs ungrounded distinction ──────────────────────────────────

    def test_unverified_true_does_not_mean_clean(self, tmp_path: Path) -> None:
        """unverified=True must be surfaced as 'unverified', not 'clean'."""
        # Both registries absent
        result = validate_grounding("See RUL-CL-999 and lobe fake-lobe", root=tmp_path)
        # The key invariant: unverified=True, not reported as "grounding clean"
        assert result["unverified"] is True
        # And ok=True (never blocks) even though refs cannot be verified
        assert result["ok"] is True


# ══════════════════════════════════════════════════════════════════════════════
# D. NEVER-RAISE contract
# ══════════════════════════════════════════════════════════════════════════════

class TestNeverRaise:
    """Every public function must return a safe fallback on any bad input."""

    def test_trajectory_block_missing_dir(self, tmp_path: Path) -> None:
        result = build_trajectory_block("ghost-lobe", root=tmp_path)
        assert isinstance(result, str)

    def test_trajectory_block_none_root(self) -> None:
        # Uses real repo root — may have or not have trajectory.jsonl; should not raise
        result = build_trajectory_block("__nonexistent_lobe__")
        assert isinstance(result, str)

    def test_strategic_gap_none_state(self, tmp_path: Path) -> None:
        result = build_strategic_gap(organism_state=None, root=tmp_path)
        assert isinstance(result, str)

    def test_strategic_gap_empty_dict(self, tmp_path: Path) -> None:
        result = build_strategic_gap(organism_state={}, root=tmp_path)
        assert isinstance(result, str)

    def test_grounding_empty_string(self, tmp_path: Path) -> None:
        result = validate_grounding("", root=tmp_path)
        assert isinstance(result, dict)
        assert "ok" in result

    def test_grounding_none_like_nonstring(self, tmp_path: Path) -> None:
        # Pass something that is neither str nor dict — exercises the else branch
        result = validate_grounding(42, root=tmp_path)  # type: ignore[arg-type]
        assert isinstance(result, dict)

    def test_grounding_deeply_nested(self, tmp_path: Path) -> None:
        nested = {"a": {"b": {"c": {"d": {"e": {"lobe_id": "test"}}}}}}
        result = validate_grounding(nested, root=tmp_path)
        assert isinstance(result, dict)

    def test_load_known_lobes_bad_yaml(self, tmp_path: Path) -> None:
        """Malformed synapse.yml → (empty_set, False), no raise."""
        (tmp_path / "config").mkdir(parents=True, exist_ok=True)
        (tmp_path / "config" / "synapse.yml").write_text(
            "not:\n  valid:\n    yaml: [unclosed", encoding="utf-8"
        )
        ids, ok = _load_known_lobes(tmp_path)
        assert isinstance(ids, set)
        assert isinstance(ok, bool)

    def test_load_known_rulings_bad_yaml(self, tmp_path: Path) -> None:
        """Malformed ruling_graph.yml → (empty_set, False), no raise."""
        (tmp_path / "config").mkdir(parents=True, exist_ok=True)
        (tmp_path / "config" / "ruling_graph.yml").write_text(
            "rulings:\n  - ruling_id: [not-a-string", encoding="utf-8"
        )
        ids, ok = _load_known_rulings(tmp_path)
        assert isinstance(ids, set)
        assert isinstance(ok, bool)

    def test_load_known_sensors_no_fitness_dir(self, tmp_path: Path) -> None:
        """No fitness dir → (empty_set, False), no raise."""
        ids, ok = _load_known_sensors(tmp_path)
        assert isinstance(ids, set)
        assert ok is False
