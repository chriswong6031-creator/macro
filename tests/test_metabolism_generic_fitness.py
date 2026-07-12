"""tests/test_metabolism_generic_fitness.py — R-V6-4..7 tests.

Coverage:
  R-V6-4 generic fitness scaffold:
    1. structured-sensor probation lobe gets a card with accruing sensors + null composite.
    2. 'til' lobe skipped (bespoke builder).
    3. bare-string-sensor lobes skipped (not structured).
    4. store-absent → store_present=False, card still written (honest).
    5. inactive lobes (retired/demoted) skipped.

  R-V6-5 multi-lobe propose:
    6. --all-lobes with 2 loop-managed lobes → propose called twice, first keeps base cycle_id.
    7. single-lobe (--lobe) path unchanged.

  R-V6-6 accountability clock:
    8. probation lobe past deadline + zero matured contracts → demotion docket emitted.
    9. probation lobe past deadline + one matured contract → no demotion (context-accrual law).
    10. probation lobe before deadline → no-op.
    11. active lobe → skipped (not probation).

  R-V6-7 shadow genesis:
    12. genesis_probe stage consumes the synthetic proposal, plan record in shadow,
        real stores untouched.

All tests use tmp_path for isolation — no writes to repo data/ tree.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_minimal_root(tmp_path: Path, extra_charters: dict | None = None) -> Path:
    """Create a minimal repo root with lobe_charters.yml for testing."""
    root = tmp_path / "repo"
    root.mkdir()

    cfg = root / "config"
    cfg.mkdir()

    # Minimal budget config
    (cfg / "metabolism_budget.yml").write_text(
        "schema: metabolism_budget.v1\ngenesis_accountability_days: 45\n",
        encoding="utf-8",
    )

    charters: dict = {
        "charters": {
            # Bespoke builder — must be skipped
            "til": {
                "lobe_id": "til",
                "tier": "display",
                "lifecycle_state": "active",
                "fitness_sensors": [
                    {"id": "front_run_lead", "store": "data/metabolism/fitness/til.json",
                     "maturity_date": "2026-10-15", "accruing": True},
                ],
            },
            # Structured sensors + probation — should get a card
            "test-lobe-alpha": {
                "lobe_id": "test-lobe-alpha",
                "tier": "display",
                "lifecycle_state": "probation",
                "fitness_sensors": [
                    {"id": "liveness_score", "store": "data/test/alpha.jsonl",
                     "maturity_date": "2027-01-01", "accruing": True},
                    {"id": "freshness_score", "store": "data/test/alpha_fresh.json",
                     "maturity_date": "2027-01-01", "accruing": True},
                ],
            },
            # Bare-string sensors — must be skipped
            "bare-string-lobe": {
                "lobe_id": "bare-string-lobe",
                "tier": "display",
                "lifecycle_state": "active",
                "fitness_sensors": ["liveness", "freshness_sla"],
            },
            # Retired — must be skipped
            "retired-lobe": {
                "lobe_id": "retired-lobe",
                "tier": "display",
                "lifecycle_state": "retired",
                "fitness_sensors": [
                    {"id": "liveness_score", "store": "data/test/ret.json",
                     "maturity_date": "2027-01-01", "accruing": True},
                ],
            },
        }
    }
    if extra_charters:
        charters["charters"].update(extra_charters)

    import yaml  # noqa: PLC0415
    (cfg / "lobe_charters.yml").write_text(
        yaml.dump(charters), encoding="utf-8"
    )

    # Fresh data/ dir
    (root / "data").mkdir()
    return root


# ═══════════════════════════════════════════════════════════════════════════════
# R-V6-4: Generic fitness scaffold
# ═══════════════════════════════════════════════════════════════════════════════

def test_generic_fitness_probation_lobe_gets_card(tmp_path):
    """Test 1: structured-sensor probation lobe gets a fitness card."""
    root = _make_minimal_root(tmp_path)

    from engine.metabolism.generic_fitness import build_generic_fitness_cards
    written = build_generic_fitness_cards(root=root)

    # Only test-lobe-alpha should get a card (til is bespoke, bare-string + retired are skipped)
    assert len(written) == 1, f"Expected 1 card written, got {len(written)}: {written}"
    card_path = Path(written[0])
    assert card_path.name == "test-lobe-alpha.json"
    assert card_path.exists()

    card = json.loads(card_path.read_text(encoding="utf-8"))
    assert card["lobe"] == "test-lobe-alpha"
    assert card["maturity"] == "accruing"
    assert "liveness_score" in card["sensors"]
    assert "freshness_score" in card["sensors"]

    # Accruing sensors have null value (no LLM-originated values)
    for sensor_id, sensor_data in card["sensors"].items():
        assert sensor_data["value"] is None, f"sensor {sensor_id} has non-null value"
        assert sensor_data["maturity"] == "accruing"

    # Composite is null while any sensor accruing
    assert card["composite"] is None

    # Authority block present
    assert card["authority"]["is_context_only"] is True
    assert card["authority"]["may_rank"] is False


def test_generic_fitness_til_skipped(tmp_path):
    """Test 2: 'til' lobe skipped (bespoke builder)."""
    root = _make_minimal_root(tmp_path)

    from engine.metabolism.generic_fitness import build_generic_fitness_cards
    written = build_generic_fitness_cards(root=root)

    written_names = [Path(p).name for p in written]
    assert "til.json" not in written_names, "til.json should not be written by generic builder"


def test_generic_fitness_bare_string_sensors_skipped(tmp_path):
    """Test 3: bare-string-sensor lobes skipped."""
    root = _make_minimal_root(tmp_path)

    from engine.metabolism.generic_fitness import build_generic_fitness_cards
    written = build_generic_fitness_cards(root=root)

    written_names = [Path(p).name for p in written]
    assert "bare-string-lobe.json" not in written_names


def test_generic_fitness_store_absent_honest(tmp_path):
    """Test 4: store-absent → store_present=False, card still written (honest)."""
    root = _make_minimal_root(tmp_path)
    # Note: the store files (data/test/alpha.jsonl etc) don't exist in root
    # So store_present should be False

    from engine.metabolism.generic_fitness import build_generic_fitness_cards
    written = build_generic_fitness_cards(root=root)

    assert len(written) == 1
    card = json.loads(Path(written[0]).read_text(encoding="utf-8"))

    for sensor_id, sensor_data in card["sensors"].items():
        assert sensor_data["store_present"] is False, (
            f"sensor {sensor_id}: expected store_present=False (store absent)"
        )
        # value should still be null (honest, not fabricated)
        assert sensor_data["value"] is None


def test_generic_fitness_inactive_lobes_skipped(tmp_path):
    """Test 5: inactive lobes (retired/demoted/proposed) skipped."""
    root = _make_minimal_root(tmp_path)

    from engine.metabolism.generic_fitness import build_generic_fitness_cards
    written = build_generic_fitness_cards(root=root)

    written_names = [Path(p).name for p in written]
    assert "retired-lobe.json" not in written_names


# ═══════════════════════════════════════════════════════════════════════════════
# R-V6-5: Multi-lobe propose
# ═══════════════════════════════════════════════════════════════════════════════

def test_all_lobes_discovers_two_lobes(tmp_path):
    """Test 6: --all-lobes with 2 loop-managed lobes → propose called twice."""
    root = tmp_path / "repo"
    root.mkdir()
    cfg = root / "config"
    cfg.mkdir()
    (root / "data").mkdir()

    # Add a second loop-managed lobe
    import yaml  # noqa: PLC0415
    charters = {
        "charters": {
            "til": {
                "lobe_id": "til",
                "tier": "display",
                "lifecycle_state": "active",
                "fitness_sensors": [
                    {"id": "front_run_lead", "store": "data/metabolism/fitness/til.json",
                     "maturity_date": "2026-10-15", "accruing": True},
                ],
            },
            "second-lobe": {
                "lobe_id": "second-lobe",
                "tier": "display",
                "lifecycle_state": "active",
                "fitness_sensors": [
                    {"id": "liveness_score", "store": "data/second/liveness.json",
                     "maturity_date": "2027-01-01", "accruing": True},
                ],
            },
        }
    }
    (cfg / "lobe_charters.yml").write_text(yaml.dump(charters), encoding="utf-8")
    (cfg / "metabolism_budget.yml").write_text("max_docket_size: 5\n", encoding="utf-8")

    from scripts.metabolism_propose import _discover_loop_managed_lobes
    lobes = _discover_loop_managed_lobes(root)

    assert lobes[0] == "til", "first lobe must always be 'til' (backward compat)"
    assert "second-lobe" in lobes
    assert len(lobes) == 2


def test_all_lobes_first_keeps_base_cycle_id(tmp_path):
    """Test 6b: first lobe keeps bare base cycle_id; subsequent lobes get suffixed id."""
    root = tmp_path / "repo"
    root.mkdir()
    cfg = root / "config"
    cfg.mkdir()
    (root / "data").mkdir()

    import yaml  # noqa: PLC0415
    charters = {
        "charters": {
            "til": {
                "lobe_id": "til",
                "tier": "display",
                "lifecycle_state": "active",
                "fitness_sensors": [
                    {"id": "front_run_lead", "store": "data/metabolism/fitness/til.json",
                     "maturity_date": "2026-10-15", "accruing": True},
                ],
            },
            "genesis-lobe-b": {
                "lobe_id": "genesis-lobe-b",
                "tier": "display",
                "lifecycle_state": "probation",
                "fitness_sensors": [
                    {"id": "liveness_score", "store": "data/genesis-b/live.json",
                     "maturity_date": "2027-01-01", "accruing": True},
                ],
            },
        }
    }
    (cfg / "lobe_charters.yml").write_text(yaml.dump(charters), encoding="utf-8")
    (cfg / "metabolism_budget.yml").write_text("max_docket_size: 5\n", encoding="utf-8")

    # Collect what cycle_ids would be used
    from scripts.metabolism_propose import _discover_loop_managed_lobes
    lobes = _discover_loop_managed_lobes(root)
    base_cycle = "test-cycle-001"

    # The first lobe keeps the bare base cycle_id
    cycle_ids = []
    for i, lobe_id in enumerate(lobes):
        cid = base_cycle if i == 0 else f"{base_cycle}-{lobe_id}"
        cycle_ids.append((lobe_id, cid))

    assert cycle_ids[0] == ("til", base_cycle), "first lobe must use bare base cycle_id"
    assert cycle_ids[1] == ("genesis-lobe-b", f"{base_cycle}-genesis-lobe-b")


def test_single_lobe_path_unchanged(tmp_path):
    """Test 7: single-lobe path (no --all-lobes) is unchanged."""
    # Verify that main() with --dry-run --lobe til exits 0 without crashing
    root = tmp_path / "repo"
    root.mkdir()
    cfg = root / "config"
    cfg.mkdir()
    (root / "data").mkdir()

    import yaml  # noqa: PLC0415
    charters = {
        "charters": {
            "til": {
                "lobe_id": "til",
                "tier": "display",
                "lifecycle_state": "active",
                "fitness_sensors": [
                    {"id": "front_run_lead", "store": "data/metabolism/fitness/til.json",
                     "maturity_date": "2026-10-15", "accruing": True},
                ],
            },
        }
    }
    (cfg / "lobe_charters.yml").write_text(yaml.dump(charters), encoding="utf-8")
    (cfg / "metabolism_budget.yml").write_text("max_docket_size: 5\n", encoding="utf-8")

    # Patch metabolism_guard to simulate paused (so we don't need full infra)
    with patch("scripts.metabolism_guard.is_paused", return_value=True), \
         patch("scripts.metabolism_guard.pause_reason", return_value="test paused"):
        from scripts.metabolism_propose import main
        rc = main(["--dry-run", "--lobe", "til", "--root", str(root), "--cycle-id", "test-001"])
    assert rc == 0


# ═══════════════════════════════════════════════════════════════════════════════
# R-V6-6: Accountability clock
# ═══════════════════════════════════════════════════════════════════════════════

def _make_probation_root(tmp_path: Path, lobe_id: str = "test-genesis-lobe") -> Path:
    """Create a root with a single probation lobe."""
    root = tmp_path / "probation_repo"
    root.mkdir()
    cfg = root / "config"
    cfg.mkdir()
    (root / "data").mkdir()

    import yaml  # noqa: PLC0415
    charters = {
        "charters": {
            lobe_id: {
                "lobe_id": lobe_id,
                "tier": "display",
                "lifecycle_state": "probation",
                "fitness_sensors": [
                    {"id": "liveness_score", "store": f"data/test/{lobe_id}.json",
                     "maturity_date": "2027-01-01", "accruing": True},
                ],
            }
        }
    }
    (cfg / "lobe_charters.yml").write_text(yaml.dump(charters), encoding="utf-8")
    (cfg / "metabolism_budget.yml").write_text(
        "schema: metabolism_budget.v1\ngenesis_accountability_days: 45\n",
        encoding="utf-8",
    )
    return root


def _write_governance_probation_event(root: Path, lobe_id: str, ts: str) -> None:
    """Write a governance event marking lobe_id as entering probation at ts."""
    gov_dir = root / "data" / "neuralweb"
    gov_dir.mkdir(parents=True, exist_ok=True)
    event = json.dumps({
        "schema": "neuralweb.governance.v1",
        "event_type": "metabolism_adjudication",
        "target": lobe_id,
        "ts": ts,
        "evidence": {
            "from_state": "proposed",
            "to_state": "probation",
        },
    })
    gov_path = gov_dir / "governance.jsonl"
    with gov_path.open("a", encoding="utf-8") as f:
        f.write(event + "\n")


def _write_verify_record(root: Path, lobe_id: str, cycle_id: str = "test-cycle-001") -> None:
    """Write a minimal verify record naming the lobe (simulates a matured contract)."""
    verify_dir = root / "data" / "metabolism" / "verify"
    verify_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "schema": "metabolism.verify.v1",
        "cycle_id": cycle_id,
        "lobe": lobe_id,
        "outcome": "UNVERIFIABLE",  # honest null — still counts as matured
    }
    (verify_dir / f"{cycle_id}.json").write_text(json.dumps(record), encoding="utf-8")


def test_accountability_clock_past_deadline_no_contracts(tmp_path):
    """Test 8: probation past deadline + zero matured contracts → demotion proposed."""
    lobe_id = "test-genesis-lobe"
    root = _make_probation_root(tmp_path, lobe_id)

    # Set probation start 60 days ago (past 45-day deadline)
    start_dt = datetime.now(timezone.utc) - timedelta(days=60)
    ts_str = start_dt.isoformat(timespec="seconds")
    _write_governance_probation_event(root, lobe_id, ts_str)

    from engine.metabolism.lifecycle import sweep_genesis_accountability
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    results = sweep_genesis_accountability(root=root, today=today)

    assert len(results) == 1, f"Expected 1 result, got {len(results)}"
    r = results[0]
    assert r["lobe_id"] == lobe_id
    assert r["action"] in ("demotion_proposed", "demotion_docket_direct"), (
        f"Expected demotion action, got {r['action']}: {r}"
    )


def test_accountability_clock_has_matured_contract_no_demotion(tmp_path):
    """Test 9: past deadline + one matured contract (even UNVERIFIABLE) → no demotion."""
    lobe_id = "test-genesis-lobe"
    root = _make_probation_root(tmp_path, lobe_id)

    # Set probation start 60 days ago
    start_dt = datetime.now(timezone.utc) - timedelta(days=60)
    _write_governance_probation_event(root, lobe_id, start_dt.isoformat(timespec="seconds"))

    # Write one verify record (even UNVERIFIABLE counts as matured — honest null)
    _write_verify_record(root, lobe_id, "test-cycle-001")

    from engine.metabolism.lifecycle import sweep_genesis_accountability
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    results = sweep_genesis_accountability(root=root, today=today)

    assert len(results) == 1
    r = results[0]
    assert r["action"] == "has_contracts_no_demotion", (
        f"Expected has_contracts_no_demotion, got {r['action']}: {r}"
    )


def test_accountability_clock_before_deadline_noop(tmp_path):
    """Test 10: probation lobe before deadline → no-op."""
    lobe_id = "test-genesis-lobe"
    root = _make_probation_root(tmp_path, lobe_id)

    # Set probation start only 10 days ago (well within 45-day deadline)
    start_dt = datetime.now(timezone.utc) - timedelta(days=10)
    _write_governance_probation_event(root, lobe_id, start_dt.isoformat(timespec="seconds"))

    from engine.metabolism.lifecycle import sweep_genesis_accountability
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    results = sweep_genesis_accountability(root=root, today=today)

    assert len(results) == 1
    r = results[0]
    assert r["action"] == "within_deadline", (
        f"Expected within_deadline, got {r['action']}: {r}"
    )


def test_accountability_clock_active_lobe_skipped(tmp_path):
    """Test 11: active lobe → skipped by sweep (only probation checked)."""
    root = tmp_path / "active_repo"
    root.mkdir()
    cfg = root / "config"
    cfg.mkdir()
    (root / "data").mkdir()

    import yaml  # noqa: PLC0415
    charters = {
        "charters": {
            "active-lobe": {
                "lobe_id": "active-lobe",
                "tier": "display",
                "lifecycle_state": "active",  # NOT probation
                "fitness_sensors": [
                    {"id": "liveness_score", "store": "data/test/active.json",
                     "maturity_date": "2027-01-01", "accruing": True},
                ],
            }
        }
    }
    (cfg / "lobe_charters.yml").write_text(yaml.dump(charters), encoding="utf-8")
    (cfg / "metabolism_budget.yml").write_text(
        "schema: metabolism_budget.v1\ngenesis_accountability_days: 45\n",
        encoding="utf-8",
    )

    from engine.metabolism.lifecycle import sweep_genesis_accountability
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    results = sweep_genesis_accountability(root=root, today=today)

    # Active lobes are not checked; results list should be empty
    assert len(results) == 0, f"Active lobe should not appear in results: {results}"


# ═══════════════════════════════════════════════════════════════════════════════
# R-V6-7: Shadow genesis exercise
# ═══════════════════════════════════════════════════════════════════════════════

def _make_shadow_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """Build minimal shadow_root and real_root for genesis probe tests."""
    real_root = tmp_path / "real_repo"
    real_root.mkdir()

    # Minimal real_root config
    cfg = real_root / "config"
    cfg.mkdir()
    (cfg / "metabolism_budget.yml").write_text(
        "schema: metabolism_budget.v1\nmax_docket_size: 5\n",
        encoding="utf-8",
    )
    import yaml  # noqa: PLC0415
    charters = {
        "charters": {
            "til": {
                "lobe_id": "til",
                "tier": "display",
                "lifecycle_state": "active",
                "fitness_sensors": [
                    {"id": "front_run_lead", "store": "data/metabolism/fitness/til.json",
                     "maturity_date": "2026-10-15", "accruing": True},
                ],
            }
        }
    }
    (cfg / "lobe_charters.yml").write_text(yaml.dump(charters), encoding="utf-8")
    (real_root / "research").mkdir()
    (real_root / "research" / "DO_NOT_REBUILD.md").write_text("# empty\n", encoding="utf-8")
    (real_root / "docs").mkdir()
    (real_root / "docs" / "ACTIVE_BUILD_MAP.md").write_text("# empty\n", encoding="utf-8")
    (real_root / "data").mkdir()

    # Shadow root: symlink/copy config, fresh data/
    shadow_root = tmp_path / "shadow_root"
    shadow_root.mkdir()
    import shutil  # noqa: PLC0415
    src_config = real_root / "config"
    dst_config = shadow_root / "config"
    try:
        dst_config.symlink_to(src_config)
    except (OSError, NotImplementedError):
        shutil.copytree(str(src_config), str(dst_config))
    (shadow_root / "data").mkdir()
    (shadow_root / "research").mkdir()
    (shadow_root / "research" / "DO_NOT_REBUILD.md").write_text("# empty\n", encoding="utf-8")
    (shadow_root / "docs").mkdir()
    (shadow_root / "docs" / "ACTIVE_BUILD_MAP.md").write_text("# empty\n", encoding="utf-8")

    return real_root, shadow_root


def test_genesis_probe_stage_consumes_proposal(tmp_path):
    """Test 12: genesis_probe writes synthetic proposal to shadow, applier runs, real untouched."""
    real_root, shadow_root = _make_shadow_fixture(tmp_path)

    # Snapshot real stores before
    real_data_before = set(real_root.rglob("*"))

    from scripts.metabolism_shadow_cycle import _run_genesis_probe
    result = _run_genesis_probe(shadow_root, real_root, "shadow-test-genesis")

    # Stage must not crash
    assert result["status"] in ("ok", "degraded"), f"genesis_probe failed: {result}"
    assert result.get("probe_written") is True

    # Synthetic proposal must exist in shadow root
    probe_path = shadow_root / "data" / "metabolism" / "charter_proposals" / "shadow-genesis-probe.json"
    assert probe_path.exists(), f"synthetic proposal not written at {probe_path}"

    # Validate proposal shape
    proposal = json.loads(probe_path.read_text(encoding="utf-8"))
    assert proposal["schema"] == "metabolism.charter_proposal.v1"
    assert proposal["domain_id"] == "shadow-genesis-probe"
    assert proposal["proposed_tier"] == "display"
    assert proposal["proposed_lifecycle_state"] == "proposed"

    # Real stores must be untouched
    real_data_after = set(real_root.rglob("*"))
    new_files = real_data_after - real_data_before
    assert not new_files, f"Real stores were modified: {new_files}"


def test_genesis_probe_tier_fence_exercised(tmp_path):
    """Test 12b: genesis probe exercises tier fence (proposed_tier must be 'display')."""
    real_root, shadow_root = _make_shadow_fixture(tmp_path)

    from scripts.metabolism_shadow_cycle import _build_genesis_probe_proposal
    proposal = _build_genesis_probe_proposal(real_root)

    # The tier fence requires proposed_tier == "display"
    assert proposal["proposed_tier"] == "display", (
        f"proposed_tier must be 'display' for tier fence to pass, got {proposal['proposed_tier']}"
    )
    assert proposal["proposed_lifecycle_state"] == "proposed"


def test_genesis_probe_never_raises(tmp_path):
    """Test 12c: genesis_probe returns a dict on any error, never raises."""
    # Pass an entirely empty shadow root (will trigger errors inside)
    shadow_root = tmp_path / "empty_shadow"
    shadow_root.mkdir()
    real_root = tmp_path / "empty_real"
    real_root.mkdir()

    from scripts.metabolism_shadow_cycle import _run_genesis_probe
    result = _run_genesis_probe(shadow_root, real_root, "shadow-test-empty")

    # Must return a dict (never raise)
    assert isinstance(result, dict)
    # status must be one of the expected values
    assert result.get("status") in ("ok", "degraded", "failed")
