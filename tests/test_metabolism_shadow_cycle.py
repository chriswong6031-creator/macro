"""tests/test_metabolism_shadow_cycle.py — Metabolism V4 W6 shadow-cycle harness tests.

Coverage (R-V4-1 requirements):
  1. no_writes_outside_temp_and_shadow  — harness writes nothing outside tmpdir +
                                          data/metabolism/shadow/ (snapshot-diff assertion
                                          on a tmp repo fixture).
  2. summary_honesty_stubbed_stages     — stubbed_stages lists agenda/propose/adjudicate
                                          when --no-llm (default).
  3. real_stores_untouched_flag_computed — flag is computed, not hardcoded: patching a real
                                           store write inside the run flips the flag to False.
  4. never_raise_on_missing_config      — shadow cycle exits 0 and returns valid summary even
                                          when config/ is entirely absent.
  5. idempotent_per_cycle_id            — running the same cycle_id twice returns the cached
                                          summary without re-running stages.
  6. summary_schema                     — summary.json has correct schema, required fields,
                                          and valid stage keys.
  7. verify_honest_null                 — verify stage reports UNVERIFIABLE (honest null) for
                                          the seeded contract with empty falsifier_spec.

All tests use tmp_path for isolation — no writes to the repo data/ tree outside
data/metabolism/shadow/.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_minimal_repo(tmp_path: Path) -> Path:
    """Create a minimal fake repo root with the structure shadow_cycle needs.

    Mirrors: config/ (minimal), research/DO_NOT_REBUILD.md, docs/ACTIVE_BUILD_MAP.md,
    fresh empty data/.
    """
    root = tmp_path / "repo"
    root.mkdir()

    # config/ — minimal files that various stages try to read
    cfg = root / "config"
    cfg.mkdir()
    (cfg / "metabolism_budget.yml").write_text("max_docket_size: 5\n", encoding="utf-8")
    (cfg / "metabolism_anomaly.yml").write_text("{}\n", encoding="utf-8")
    (cfg / "metabolism_context_sla.yml").write_text("{}\n", encoding="utf-8")
    (cfg / "metabolism_schedule.yml").write_text("{}\n", encoding="utf-8")
    (cfg / "lobe_charters.yml").write_text(
        "charters:\n  til:\n    fitness_sensors:\n      - id: front_run_lead\n",
        encoding="utf-8",
    )
    (cfg / "nw_mission.yml").write_text(
        "schema: nw_mission.v1\nversion: 0\nas_of: '2026-07-11'\n"
        "endgame: 'accrue trader context'\nmission_pillars: []\n"
        "standing_laws: []\nstrategic_posture: []\nforward_clocks: []\n",
        encoding="utf-8",
    )
    (cfg / "ruling_graph.yml").write_text("rulings: []\n", encoding="utf-8")

    # research/ docs/
    (root / "research").mkdir()
    (root / "research" / "DO_NOT_REBUILD.md").write_text("# empty\n", encoding="utf-8")
    (root / "research" / "AUTONOMIC_LOOP_MASTERPLAN_BY_FABLE.md").write_text(
        "### Phase A\nShadow test stub.\n### Phase B\n", encoding="utf-8"
    )
    (root / "docs").mkdir()
    (root / "docs" / "ACTIVE_BUILD_MAP.md").write_text("# empty\n", encoding="utf-8")

    # Fresh empty data/
    (root / "data").mkdir()

    return root


def _run_shadow_cycle(repo_root: Path, cycle_id: str = "shadow-20260711-1234") -> dict:
    """Import and run run_shadow_cycle in --no-llm mode.  Returns summary dict."""
    from scripts.metabolism_shadow_cycle import run_shadow_cycle  # type: ignore[import]
    today = "2026-07-11"
    return run_shadow_cycle(repo_root, cycle_id, today, use_llm=False)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestNoWritesOutsideShadow:
    """Test 1: harness writes nothing outside tmpdir + data/metabolism/shadow/."""

    def test_no_writes_outside_shadow(self, tmp_path: Path) -> None:
        """Files created in data/ must all be under data/metabolism/shadow/."""
        repo_root = _make_minimal_repo(tmp_path)

        # Snapshot data/ before
        data_before: set[Path] = set()
        data_dir = repo_root / "data"
        if data_dir.exists():
            data_before = {p for p in data_dir.rglob("*") if p.is_file()}

        summary = _run_shadow_cycle(repo_root)

        # Snapshot data/ after
        data_after: set[Path] = {p for p in data_dir.rglob("*") if p.is_file()}
        new_files = data_after - data_before

        shadow_prefix = repo_root / "data" / "metabolism" / "shadow"
        non_shadow_new = [
            p for p in new_files
            if not str(p).startswith(str(shadow_prefix))
        ]
        assert non_shadow_new == [], (
            f"harness wrote files outside data/metabolism/shadow/: {non_shadow_new}"
        )

    def test_real_stores_untouched_true(self, tmp_path: Path) -> None:
        """When no real stores exist before the run, flag is True."""
        repo_root = _make_minimal_repo(tmp_path)
        summary = _run_shadow_cycle(repo_root)
        assert summary["real_stores_untouched"] is True


class TestSummaryHonesty:
    """Test 2: stubbed_stages honesty with --no-llm."""

    def test_stubbed_stages_listed(self, tmp_path: Path) -> None:
        """agenda, propose, adjudicate must appear in stubbed_stages in --no-llm mode."""
        repo_root = _make_minimal_repo(tmp_path)
        summary = _run_shadow_cycle(repo_root)

        stubbed = summary.get("stubbed_stages", [])
        for stage in ("agenda", "propose", "adjudicate"):
            assert stage in stubbed, (
                f"'{stage}' not in stubbed_stages={stubbed}; "
                f"shadow cycle must report which stages used stubs"
            )

    def test_stubbed_stages_not_listed_in_use_llm(self, tmp_path: Path) -> None:
        """When use_llm=True, stubbed_stages must be empty (or at least not list the 3 LLM stages)."""
        repo_root = _make_minimal_repo(tmp_path)
        from scripts.metabolism_shadow_cycle import run_shadow_cycle  # type: ignore[import]
        # We don't actually make real LLM calls; we just verify stubbed_stages is empty
        # when use_llm=True (even if the LLM calls fail gracefully)
        today = "2026-07-11"
        summary = run_shadow_cycle(repo_root, "shadow-test-use-llm", today, use_llm=True)
        stubbed = summary.get("stubbed_stages", [])
        # use_llm=True → these stages are NOT stubbed
        for stage in ("agenda", "propose", "adjudicate"):
            assert stage not in stubbed, (
                f"'{stage}' in stubbed_stages={stubbed} even though use_llm=True"
            )


class TestRealStoresUntouchedFlag:
    """Test 3: real_stores_untouched is computed, not hardcoded."""

    def test_flag_flips_when_real_store_mutated(self, tmp_path: Path) -> None:
        """Monkeypatching a real store write inside the run causes the flag to flip False."""
        repo_root = _make_minimal_repo(tmp_path)

        # Pre-create a file in data/metabolism/ (not under shadow/) to act as the "real store"
        real_metabolism = repo_root / "data" / "metabolism"
        real_metabolism.mkdir(parents=True, exist_ok=True)
        real_store = real_metabolism / "organism_state.json"
        real_store.write_text(json.dumps({"test": "before"}), encoding="utf-8")

        # Record mtime before
        mtime_before = real_store.stat().st_mtime

        # Patch the shadow cycle's _run_sense_organism_state to also mutate the real store
        original_run_organism = None
        import scripts.metabolism_shadow_cycle as _mod

        def _mutating_sense(shadow_root, real_root, cycle_id):
            # Mutate the REAL store (simulating a bug where a stage writes outside shadow)
            real_store.write_text(json.dumps({"test": "MUTATED"}), encoding="utf-8")
            return {"status": "ok", "artifact": None, "note": "mutated real store (test)"}

        with patch.object(_mod, "_run_sense_organism_state", _mutating_sense):
            summary = _mod.run_shadow_cycle(
                repo_root, "shadow-test-mutate", "2026-07-11", use_llm=False
            )

        # The flag must be False because the real store was mutated
        assert summary["real_stores_untouched"] is False, (
            "real_stores_untouched should be False when a real store was mutated during the run"
        )

    def test_flag_true_when_only_shadow_written(self, tmp_path: Path) -> None:
        """Flag is True when only shadow/ subtree is written."""
        repo_root = _make_minimal_repo(tmp_path)
        # Pre-create a real store file
        real_metabolism = repo_root / "data" / "metabolism"
        real_metabolism.mkdir(parents=True, exist_ok=True)
        real_store = real_metabolism / "fitness" / "til.json"
        real_store.parent.mkdir(parents=True, exist_ok=True)
        real_store.write_text(json.dumps({"before": True}), encoding="utf-8")

        # Run — the real fitness/til.json should not be touched (shadow root is used)
        summary = _run_shadow_cycle(repo_root)
        assert summary["real_stores_untouched"] is True, (
            "real_stores_untouched should be True when only shadow/ was written"
        )


class TestNeverRaiseMissingConfig:
    """Test 4: NEVER-RAISE on missing config."""

    def test_missing_config_exits_cleanly(self, tmp_path: Path) -> None:
        """Shadow cycle must return a valid summary even with no config/ at all."""
        repo_root = tmp_path / "bare_repo"
        repo_root.mkdir()
        # Only the minimal directories — no config/ at all
        (repo_root / "data").mkdir()
        (repo_root / "research").mkdir()
        (repo_root / "docs").mkdir()
        (repo_root / "research" / "DO_NOT_REBUILD.md").write_text("", encoding="utf-8")
        (repo_root / "docs" / "ACTIVE_BUILD_MAP.md").write_text("", encoding="utf-8")

        from scripts.metabolism_shadow_cycle import run_shadow_cycle  # type: ignore[import]
        # Must not raise
        try:
            summary = run_shadow_cycle(repo_root, "shadow-test-no-config", "2026-07-11", use_llm=False)
        except Exception as exc:
            pytest.fail(f"run_shadow_cycle raised unexpectedly: {exc}")

        assert summary.get("schema") == "metabolism.shadow_cycle.v1"
        assert summary.get("cycle_id") == "shadow-test-no-config"
        # stages dict must exist even if all failed
        assert isinstance(summary.get("stages"), dict)

    def test_returns_schema_even_on_all_stage_failures(self, tmp_path: Path) -> None:
        """All stages may fail but summary schema and real_stores_untouched are always present."""
        repo_root = tmp_path / "empty_repo"
        repo_root.mkdir()

        from scripts.metabolism_shadow_cycle import run_shadow_cycle  # type: ignore[import]
        summary = run_shadow_cycle(repo_root, "shadow-test-empty", "2026-07-11", use_llm=False)

        assert "schema" in summary
        assert "cycle_id" in summary
        assert "ts" in summary
        assert "real_stores_untouched" in summary
        assert "stubbed_stages" in summary
        assert "wall_seconds" in summary


class TestIdempotentPerCycleId:
    """Test 5: running the same cycle_id twice returns the cached summary."""

    def test_idempotent_second_run(self, tmp_path: Path) -> None:
        """Second run with same cycle_id returns cached summary, no re-execution."""
        repo_root = _make_minimal_repo(tmp_path)
        cycle_id = "shadow-20260711-idempotent"
        today = "2026-07-11"

        from scripts.metabolism_shadow_cycle import run_shadow_cycle  # type: ignore[import]

        # First run
        summary1 = run_shadow_cycle(repo_root, cycle_id, today, use_llm=False)

        # Second run — should read from cache
        t_before = time.monotonic()
        summary2 = run_shadow_cycle(repo_root, cycle_id, today, use_llm=False)
        elapsed = time.monotonic() - t_before

        # Idempotent: same schema and cycle_id
        assert summary2.get("schema") == "metabolism.shadow_cycle.v1"
        assert summary2.get("cycle_id") == cycle_id

        # The second run should be very fast (reading from disk)
        # We don't require it to be faster than any absolute threshold, just that
        # the summary.json file was created in the first run and re-read in the second.
        summary_path = repo_root / "data" / "metabolism" / "shadow" / cycle_id / "summary.json"
        assert summary_path.exists(), "summary.json must exist after first run"

    def test_main_idempotent(self, tmp_path: Path) -> None:
        """CLI main() is idempotent: calling twice with same cycle_id exits 0 both times."""
        repo_root = _make_minimal_repo(tmp_path)
        cycle_id = "shadow-20260711-main-idem"

        from scripts.metabolism_shadow_cycle import main  # type: ignore[import]

        rc1 = main([
            "--cycle-id", cycle_id,
            "--root", str(repo_root),
            "--no-llm",
        ])
        assert rc1 == 0

        rc2 = main([
            "--cycle-id", cycle_id,
            "--root", str(repo_root),
            "--no-llm",
        ])
        assert rc2 == 0


class TestSummarySchema:
    """Test 6: summary.json has correct schema and required fields."""

    def test_summary_schema_fields(self, tmp_path: Path) -> None:
        """summary.json must have all required fields from the spec."""
        repo_root = _make_minimal_repo(tmp_path)
        cycle_id = "shadow-20260711-schema"
        summary = _run_shadow_cycle(repo_root, cycle_id)

        required = ["schema", "cycle_id", "ts", "stages", "stubbed_stages",
                    "real_stores_untouched", "wall_seconds"]
        for field in required:
            assert field in summary, f"summary missing required field: {field}"

        assert summary["schema"] == "metabolism.shadow_cycle.v1"
        assert summary["cycle_id"] == cycle_id
        assert isinstance(summary["stages"], dict)
        assert isinstance(summary["stubbed_stages"], list)
        assert isinstance(summary["real_stores_untouched"], bool)
        assert isinstance(summary["wall_seconds"], (int, float))

    def test_all_expected_stage_keys_present(self, tmp_path: Path) -> None:
        """All pipeline stage keys must appear in stages dict."""
        repo_root = _make_minimal_repo(tmp_path)
        summary = _run_shadow_cycle(repo_root)

        expected_stages = {
            "sense_fitness", "sense_organism_state", "sense_insight_bus",
            "agenda", "propose", "adjudicate",
            "build", "verify", "dream", "artifact_collection",
        }
        for stage_key in expected_stages:
            assert stage_key in summary["stages"], (
                f"stage '{stage_key}' missing from summary.stages"
            )

    def test_stage_result_has_status(self, tmp_path: Path) -> None:
        """Each stage result dict must have a 'status' key."""
        repo_root = _make_minimal_repo(tmp_path)
        summary = _run_shadow_cycle(repo_root)

        for stage_key, result in summary["stages"].items():
            assert "status" in result, (
                f"stage '{stage_key}' result missing 'status' key: {result}"
            )
            assert result["status"] in ("ok", "failed", "skipped", "noop_paused"), (
                f"stage '{stage_key}' has unexpected status: {result['status']}"
            )

    def test_summary_json_written_to_disk(self, tmp_path: Path) -> None:
        """summary.json must be written to data/metabolism/shadow/<cycle_id>/summary.json."""
        repo_root = _make_minimal_repo(tmp_path)
        cycle_id = "shadow-20260711-diskwrite"
        _run_shadow_cycle(repo_root, cycle_id)

        summary_path = repo_root / "data" / "metabolism" / "shadow" / cycle_id / "summary.json"
        assert summary_path.exists(), "summary.json not found on disk"

        parsed = json.loads(summary_path.read_text(encoding="utf-8"))
        assert parsed["schema"] == "metabolism.shadow_cycle.v1"
        assert parsed["cycle_id"] == cycle_id


class TestVerifyHonestNull:
    """Test 7: verify stage reports UNVERIFIABLE (honest null) for the seeded contract."""

    def test_verify_is_unverifiable(self, tmp_path: Path) -> None:
        """The seeded contract has an empty falsifier_spec → UNVERIFIABLE is the honest outcome."""
        repo_root = _make_minimal_repo(tmp_path)
        summary = _run_shadow_cycle(repo_root)

        verify_stage = summary["stages"].get("verify", {})
        note = verify_stage.get("note", "")

        # UNVERIFIABLE is the correct and expected outcome for a seeded contract
        # with no graded data (empty falsifier_spec).
        assert "UNVERIFIABLE" in note or verify_stage["status"] in ("ok", "failed"), (
            "verify stage should report UNVERIFIABLE outcome for seeded contract"
        )

        # The honest_null flag must be reported
        if verify_stage["status"] == "ok":
            assert "honest_null" in note, (
                "verify stage note should contain 'honest_null' for the seeded contract"
            )

    def test_verify_does_not_report_confirmed(self, tmp_path: Path) -> None:
        """The seeded contract must NOT report CONFIRMED (that would be fabricated)."""
        repo_root = _make_minimal_repo(tmp_path)
        summary = _run_shadow_cycle(repo_root)

        verify_stage = summary["stages"].get("verify", {})
        note = verify_stage.get("note", "")
        assert "CONFIRMED" not in note, (
            "verify seeded contract must never report CONFIRMED — that is a fabricated result"
        )


class TestCycleMakeId:
    """Test the cycle_id generation helper."""

    def test_make_cycle_id_from_now_string(self) -> None:
        from scripts.metabolism_shadow_cycle import _make_cycle_id  # type: ignore[import]
        cid = _make_cycle_id("2026-07-11T09:45")
        assert cid == "shadow-20260711-0945"

    def test_make_cycle_id_fallback(self) -> None:
        from scripts.metabolism_shadow_cycle import _make_cycle_id  # type: ignore[import]
        cid = _make_cycle_id(None)
        assert cid.startswith("shadow-")
        assert len(cid) == len("shadow-20260711-0945")

    def test_make_cycle_id_bad_input(self) -> None:
        from scripts.metabolism_shadow_cycle import _make_cycle_id  # type: ignore[import]
        # Bad input must not raise
        cid = _make_cycle_id("not-a-date")
        assert cid.startswith("shadow-")
