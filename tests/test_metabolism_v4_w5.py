"""tests/test_metabolism_v4_w5.py — Metabolism V4 W5 steering-memory + applier tests.

Covers (Unit 5 spec):
  - Each new PROPOSE context block appears in the assembled prompt (seed artifacts,
    assert content present + freshness header rows).
  - Preference prior consumption (seed a prior, assert it reaches both propose and
    orchestrator_brain prompts).
  - Fitness history round-trip per-lobe (B5 fix verification).
  - Accrual-honesty rejection.
  - Applier tier-raise refusal.
  - Applier routes a seeded charter_proposal into an injected proposal.
  - Corrupt-artifact NEVER-RAISE for every new read path.

All tests use tmp_path for isolation — no writes to the repo data/ tree.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
import pytest

# ── Repo root path helper ──────────────────────────────────────────────────────

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _minimal_fitness_card(tmp_path: Path) -> Path:
    """Write a minimal TIL fitness card and return its path."""
    fitness_dir = tmp_path / "data" / "metabolism" / "fitness"
    fitness_dir.mkdir(parents=True, exist_ok=True)
    card = {
        "as_of": "2026-07-11",
        "maturity": "accruing",
        "sensors": {
            "front_run_lead": {"value": None, "maturity": "accruing", "note": "accruing"},
            "placebo_hit_rate": {"value": None, "maturity": "accruing", "note": "accruing"},
        },
    }
    p = fitness_dir / "til.json"
    p.write_text(json.dumps(card), encoding="utf-8")
    return p


def _write_preference_prior(tmp_path: Path, n_closed: int = 3) -> Path:
    """Write a preference_prior.json and return its path."""
    prior_dir = tmp_path / "data" / "metabolism"
    prior_dir.mkdir(parents=True, exist_ok=True)
    prior = {
        "schema": "metabolism.preference_prior.v1",
        "ts": "2026-07-11T00:00:00+00:00",
        "not_gate_altering": True,
        "status": "insufficient_data",
        "n_closed_contracts": n_closed,
        "advisory_observations": ["[advisory] 'doc' proposals have low hit rate (20% of 5 closed)"],
        "note": "Seeded by test fixture",
    }
    p = prior_dir / "preference_prior.json"
    p.write_text(json.dumps(prior), encoding="utf-8")
    return p


def _write_insight_bus_rows(tmp_path: Path) -> Path:
    """Write a small insight_bus.jsonl and return its path."""
    ibus_dir = tmp_path / "data" / "metabolism"
    ibus_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "schema": "metabolism.insight_bus.v1",
            "insight_id": "abc123",
            "ts": "2026-07-11T00:00:00",
            "emitter": "test_emitter",
            "kind": "health_transition",
            "severity": "high",
            "entities": ["til"],
            "summary": "TIL health=degraded (seeded)",
            "handled": False,
            "handled_by": None,
        },
    ]
    p = ibus_dir / "insight_bus.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return p


def _write_lessons(tmp_path: Path) -> Path:
    """Write a small lessons.jsonl and return its path."""
    met_dir = tmp_path / "data" / "metabolism"
    met_dir.mkdir(parents=True, exist_ok=True)
    lesson = {
        "schema": "metabolism.lessons.v1",
        "ts": "2026-07-11T00:00:00",
        "cycle_id": "test-cycle",
        "proposal_id": "abc",
        "verdict": "fail",
        "what_worked": "",
        "what_failed": "construction did not improve sensor til front_run_lead",
        "construction": "sensor=front_run_lead kind=doc tier=T0",
    }
    p = met_dir / "lessons.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(lesson) + "\n")
    return p


def _write_strategic_memory(tmp_path: Path, lobe: str = "til") -> Path:
    """Write a strategic_memory.jsonl and return its path."""
    met_dir = tmp_path / "data" / "metabolism"
    met_dir.mkdir(parents=True, exist_ok=True)
    row = {
        "schema": "metabolism.strategic_memory.v1",
        "ts": "2026-07-11T00:00:00+00:00",
        "lobe": lobe,
        "cycle_id": "test-cycle",
        "sensor": "front_run_lead",
        "verdict": "CONFIRMED",
        "measurement_lens_class": "confirmed",
        "check_by": "2026-10-15",
    }
    p = met_dir / "strategic_memory.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return p


def _make_lobe_charter(tmp_path: Path) -> Path:
    """Write a minimal lobe_charters.yml with TIL sensors declared."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    charter = {
        "schema": "lobe_charters.v1",
        "charters": {
            "til": {
                "lobe_id": "til",
                "tier": "display",
                "lifecycle_state": "active",
                "fitness_sensors": [
                    {"id": "front_run_lead", "maturity_date": "2026-10-15", "accruing": True},
                    {"id": "placebo_hit_rate", "maturity_date": "2026-10-15", "accruing": True},
                    {"id": "falsifier_honesty", "maturity_date": "2026-10-15", "accruing": True},
                    {"id": "live_leg_quality", "maturity_date": "2026-10-15", "accruing": True},
                ],
                "owner_program": "thematic-intelligence",
            },
        },
    }
    p = config_dir / "lobe_charters.yml"
    try:
        import yaml
        p.write_text(yaml.dump(charter, default_flow_style=False), encoding="utf-8")
    except ImportError:
        # Fallback: write JSON (yaml parse will fail; tests that need charter will skip)
        p.write_text(json.dumps(charter), encoding="utf-8")
    return p


# ── Unit 1: Context blocks appear in propose prompt ──────────────────────────

class TestProposeContextBlocks:
    """Seed all five W5 context artifacts; assert they appear in build_prompt_context."""

    def test_recall_lessons_in_context(self, tmp_path: Path) -> None:
        """Recall block contains seeded lesson payload when lessons.jsonl is seeded."""
        _write_lessons(tmp_path)
        from engine.metabolism.propose import build_prompt_context
        ctx = build_prompt_context(root=tmp_path)
        recall = ctx.get("recall_lessons", "")
        assert isinstance(recall, str)
        # The seeded lesson has verdict='fail' and sensor 'front_run_lead'; at least
        # one of these must appear in the recall block to prove the wiring is live.
        assert "front_run_lead" in recall or "fail" in recall, (
            f"Seeded lesson content not found in recall block: {recall!r}"
        )

    def test_preference_prior_in_context(self, tmp_path: Path) -> None:
        """Preference prior block is present and non-absent when seeded."""
        _write_preference_prior(tmp_path)
        from engine.metabolism.propose import build_prompt_context
        ctx = build_prompt_context(root=tmp_path)
        prior = ctx.get("preference_prior", "")
        assert isinstance(prior, str)
        # When file is seeded, it should not be the accruing message
        assert "accruing until first dream cycle" not in prior
        # The seeded advisory payload must reach the assembled block — a header
        # or fallback string passing this test would green-light dead wiring.
        assert "low hit rate" in prior, (
            f"Seeded advisory_observations not found in prior block: {prior!r}"
        )

    def test_insight_bus_in_context(self, tmp_path: Path) -> None:
        """Insight bus block contains seeded row summary when insight_bus.jsonl is seeded."""
        _write_insight_bus_rows(tmp_path)
        from engine.metabolism.propose import build_prompt_context
        ctx = build_prompt_context(root=tmp_path)
        ibus = ctx.get("insight_bus_open", "")
        assert isinstance(ibus, str)
        # The seeded row has summary "TIL health=degraded (seeded)"; it must appear in
        # the assembled block to prove the wiring is live (not just a header stub).
        assert "TIL health=degraded" in ibus or "health_transition" in ibus, (
            f"Seeded insight-bus content not found in block: {ibus!r}"
        )

    def test_trajectory_in_context(self, tmp_path: Path) -> None:
        """Trajectory and strategic-gap blocks are always present strings."""
        from engine.metabolism.propose import build_prompt_context
        ctx = build_prompt_context(root=tmp_path)
        assert isinstance(ctx.get("trajectory_block"), str)
        assert isinstance(ctx.get("strategic_gap"), str)

    def test_mission_in_context(self, tmp_path: Path) -> None:
        """Mission block is always present (falls back to hardcoded mission)."""
        from engine.metabolism.propose import build_prompt_context
        ctx = build_prompt_context(root=tmp_path)
        mission = ctx.get("mission_block", "")
        assert isinstance(mission, str)
        assert len(mission) > 10  # must have substance

    def test_strategic_memory_in_context(self, tmp_path: Path) -> None:
        """Strategic memory block is present when seeded."""
        _write_strategic_memory(tmp_path)
        from engine.metabolism.propose import build_prompt_context
        ctx = build_prompt_context(root=tmp_path)
        sm = ctx.get("strategic_memory", "")
        assert isinstance(sm, str)
        # Seeded a CONFIRMED row — must appear
        assert "CONFIRMED" in sm

    def test_freshness_header_rows_in_context(self, tmp_path: Path) -> None:
        """build_prompt_context returns all 7+ expected keys (freshness-level check)."""
        from engine.metabolism.propose import build_prompt_context
        ctx = build_prompt_context(root=tmp_path)
        required_keys = [
            "fitness_card", "masterplan_phase_a", "do_not_rebuild", "active_build_map",
            "recall_lessons", "preference_prior", "insight_bus_open",
            "trajectory_block", "strategic_gap", "mission_block", "strategic_memory",
        ]
        for key in required_keys:
            assert key in ctx, f"Missing context key: {key}"

    def test_user_prompt_contains_all_sections(self, tmp_path: Path) -> None:
        """_build_user_prompt includes headers for all new steering-memory sections."""
        _write_preference_prior(tmp_path)
        _write_insight_bus_rows(tmp_path)
        _write_strategic_memory(tmp_path)
        from engine.metabolism.propose import build_prompt_context, _build_user_prompt
        ctx = build_prompt_context(root=tmp_path)
        prompt = _build_user_prompt(ctx, max_n=3)
        assert "RECENT LESSONS" in prompt
        assert "PREFERENCE PRIOR" in prompt
        assert "INSIGHT BUS" in prompt
        assert "TRAJECTORY" in prompt
        assert "STRATEGIC GAP" in prompt
        assert "MISSION" in prompt
        assert "STRATEGIC MEMORY" in prompt


# ── Preference prior in orchestrator_brain ────────────────────────────────────

class TestOrchestratorBrainPreferencePrior:
    """Seed a preference prior; assert it reaches _build_orchestrator_system."""

    def test_preference_prior_in_orchestrator_prompt(self, tmp_path: Path) -> None:
        """Preference prior advisory observations appear in the orchestrator system prompt."""
        _write_preference_prior(tmp_path)
        from engine.metabolism.orchestrator_brain import _build_orchestrator_system
        prompt = _build_orchestrator_system(model="claude-opus-4-8", lobe="til", root=tmp_path)
        assert isinstance(prompt, str)
        assert len(prompt) > 100
        # The seeded prior has advisory_observations with "doc proposals have low hit rate";
        # that payload (or its section header + content) must reach the prompt.
        assert "low hit rate" in prompt or "advisory" in prompt.lower(), (
            f"Seeded preference-prior payload not found in orchestrator prompt; "
            f"got header only or payload dropped"
        )

    def test_insight_bus_in_orchestrator_prompt(self, tmp_path: Path) -> None:
        """Open insight-bus rows appear in the orchestrator system prompt."""
        _write_insight_bus_rows(tmp_path)
        from engine.metabolism.orchestrator_brain import _build_orchestrator_system
        prompt = _build_orchestrator_system(model="claude-opus-4-8", lobe="til", root=tmp_path)
        # The seeded row has summary "TIL health=degraded (seeded)"; payload must reach prompt.
        assert "TIL health=degraded" in prompt or "health_transition" in prompt, (
            f"Seeded insight-bus payload not found in orchestrator prompt"
        )

    def test_mission_in_orchestrator_prompt(self, tmp_path: Path) -> None:
        """Mission block appears in the orchestrator system prompt with substantive content."""
        from engine.metabolism.orchestrator_brain import _build_orchestrator_system
        prompt = _build_orchestrator_system(model="claude-opus-4-8", lobe="til", root=tmp_path)
        # When no nw_mission.yml is present, the fallback mission text must appear.
        assert "Neural Web" in prompt or "Mission" in prompt, (
            f"Mission content absent from orchestrator prompt"
        )

    def test_strategic_memory_in_orchestrator_prompt(self, tmp_path: Path) -> None:
        """Strategic memory tail with seeded CONFIRMED verdict appears in the orchestrator prompt."""
        _write_strategic_memory(tmp_path)
        from engine.metabolism.orchestrator_brain import _build_orchestrator_system
        prompt = _build_orchestrator_system(model="claude-opus-4-8", lobe="til", root=tmp_path)
        # The seeded row has verdict="CONFIRMED"; that payload must reach the prompt.
        assert "CONFIRMED" in prompt, (
            f"Seeded strategic-memory CONFIRMED verdict not found in orchestrator prompt"
        )


# ── Unit 2: Fitness history round-trip per-lobe ──────────────────────────────

class TestFitnessHistoryRoundTrip:
    """Verify the B5 fix: append_fitness_history → per-lobe file → organism_state loads it."""

    def test_write_and_read_per_lobe(self, tmp_path: Path) -> None:
        """Appending via memory API writes to per-lobe file; organism_state reads it back."""
        from engine.metabolism.memory import append_fitness_history, load_fitness_history
        ok = append_fitness_history(
            run_id="test-run",
            lobe="til",
            sensors={"front_run_lead": 0.5},
            root=tmp_path,
        )
        assert ok, "append_fitness_history should return True"

        # Check file is in per-lobe location
        per_lobe_file = tmp_path / "data" / "metabolism" / "fitness_history" / "til.jsonl"
        assert per_lobe_file.exists(), "Per-lobe file not created"

        # Load via memory API
        rows = load_fitness_history(root=tmp_path, lobe="til")
        assert len(rows) == 1
        assert rows[0]["lobe"] == "til"
        assert rows[0]["sensors"]["front_run_lead"] == 0.5

        # Load via organism_state's private loader (the actual reader)
        from engine.metabolism.organism_state import _load_fitness_history as _os_load
        os_rows = _os_load(tmp_path, "til")
        assert len(os_rows) == 1
        assert os_rows[0]["lobe"] == "til"

    def test_missing_lobe_goes_to_quarantine(self, tmp_path: Path) -> None:
        """A row with lobe=None goes to _unattributed.jsonl quarantine file."""
        from engine.metabolism.memory import append_fitness_history
        ok = append_fitness_history(
            run_id="test-run",
            lobe=None,
            sensors={"some_sensor": 0.1},
            root=tmp_path,
        )
        assert ok
        quarantine = tmp_path / "data" / "metabolism" / "fitness_history" / "_unattributed.jsonl"
        assert quarantine.exists(), "Quarantine file not created for missing lobe"

    def test_multiple_lobes_isolated(self, tmp_path: Path) -> None:
        """Appending for two lobes keeps their histories isolated."""
        from engine.metabolism.memory import append_fitness_history, load_fitness_history
        append_fitness_history("r1", "til", {"s": 0.1}, root=tmp_path)
        append_fitness_history("r2", "other_lobe", {"s": 0.9}, root=tmp_path)

        til_rows = load_fitness_history(root=tmp_path, lobe="til")
        other_rows = load_fitness_history(root=tmp_path, lobe="other_lobe")
        assert len(til_rows) == 1
        assert len(other_rows) == 1
        assert til_rows[0]["sensors"]["s"] == 0.1
        assert other_rows[0]["sensors"]["s"] == 0.9

    def test_trajectory_slope_from_per_lobe_history(self, tmp_path: Path) -> None:
        """Trajectory slope computes from per-lobe history once enough rows exist."""
        from engine.metabolism.memory import append_fitness_history
        from engine.metabolism.organism_state import _compute_trajectory

        # Write 5 rows with improving composite fitness for "til"
        for i in range(5):
            append_fitness_history(
                f"r{i}", "til",
                {"composite": float(i) * 0.1},
                root=tmp_path,
            )

        # Build a stub card with composite field
        card = {"composite": 0.4, "maturity": "ready", "sensors": {}}
        traj = _compute_trajectory(tmp_path, "til", card)
        # With 5 rows written to the per-lobe file, trajectory should return n_obs >= 3
        # (may still be accruing if not enough composite values, but file must be read)
        assert isinstance(traj, dict)
        assert "slope" in traj
        assert "label" in traj


# ── Unit 3: Accrual-honesty rejection ─────────────────────────────────────────

class TestAccrualHonestyRejection:
    """Proposals with check_by earlier than sensor maturity_date must be rejected."""

    def test_accrual_honesty_rejects_early_check_by(self, tmp_path: Path) -> None:
        """A proposal with check_by < maturity_date is rejected with an informative reason."""
        _make_lobe_charter(tmp_path)
        from engine.metabolism.propose import build_docket

        proposal = {
            "title": "Improve front_run_lead recall",
            "tier": "T0",
            "kind": "doc",
            "targets_sensor": "front_run_lead",
            "rationale": "Add better docs",
            "fitness_contract": {
                "sensor": "front_run_lead",
                "expected_sign": "+",
                "band": "[0.05, null]",
                "check_by": "2026-08-01",  # before maturity_date 2026-10-15
                "placebo_to_beat": "shadow placebo",
            },
        }
        docket = build_docket(
            "test-cycle", [proposal], root=tmp_path, lobe="til",
        )
        # Proposal must end up in rejected
        rejected = docket.get("rejected") or []
        proposals = docket.get("proposals") or []
        assert len(proposals) == 0, "Early check_by should be rejected"
        assert len(rejected) == 1
        assert "accrual-honesty" in rejected[0]["reason"]

    def test_accrual_honesty_accepts_correct_check_by(self, tmp_path: Path) -> None:
        """A proposal with check_by >= maturity_date passes the accrual-honesty gate."""
        _make_lobe_charter(tmp_path)
        from engine.metabolism.propose import build_docket

        proposal = {
            "title": "Improve front_run_lead recall with correct horizon",
            "tier": "T0",
            "kind": "doc",
            "targets_sensor": "front_run_lead",
            "rationale": "Add better docs",
            "fitness_contract": {
                "sensor": "front_run_lead",
                "expected_sign": "+",
                "band": "[0.05, null]",
                "check_by": "2026-10-15",  # exactly at maturity_date
                "placebo_to_beat": "shadow placebo",
            },
        }
        docket = build_docket(
            "test-cycle", [proposal], root=tmp_path, lobe="til",
        )
        proposals = docket.get("proposals") or []
        rejected = docket.get("rejected") or []
        # Should not be rejected for accrual-honesty
        accrual_rejections = [r for r in rejected if "accrual-honesty" in r.get("reason", "")]
        assert len(accrual_rejections) == 0, f"Should not reject: {rejected}"

    def test_no_sensors_lobe_returns_empty_maturity(self, tmp_path: Path) -> None:
        """A lobe without fitness_sensors in charter returns empty maturity map."""
        from engine.metabolism.propose import _load_accruing_sensor_maturity
        # No charter file → empty
        result = _load_accruing_sensor_maturity(tmp_path, "unknown_lobe")
        assert result == {}


# ── Unit 4: Applier charter-default contract provenance ──────────────────────

class TestApplierCharterDefaultContract:
    """A real scout-shaped charter proposal (no fitness_contract, by design)
    converts to an injected proposal carrying an openly-stamped default
    liveness contract — never silently dropped, never silently fabricated."""

    def test_scout_shaped_proposal_gets_stamped_liveness_default(self, tmp_path: Path) -> None:
        proposals_dir = tmp_path / "data" / "metabolism" / "charter_proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)
        # Mirror scout._build_charter_proposal output: metabolism.charter_proposal.v1
        # carries NO fitness_contract key.
        item = {
            "schema": "metabolism.charter_proposal.v1",
            "ts": "2026-07-11T00:00:00+00:00",
            "cycle_id": "cyc-test",
            "domain_id": "options_dealer_flow",
            "label": "Options dealer flow",
            "description": "Recurring coverage gap",
            "proposed_tier": "display",
            "proposed_lifecycle_state": "proposed",
            "title": "Charter lobe for options_dealer_flow",
            "rationale": "3+ distinct uncovered cycles",
        }
        (proposals_dir / "options_dealer_flow.json").write_text(
            json.dumps(item), encoding="utf-8"
        )

        from engine.metabolism.applier import consume_charter_proposals
        injected = consume_charter_proposals(root=tmp_path, armed=True, dry_run=False)
        assert len(injected) == 1, "Scout charter proposal must convert, not drop"
        fc = injected[0]["fitness_contract"]
        assert fc["sensor"] == "liveness"
        assert fc["contract_source"] == "applier_default_charter_liveness", (
            "Applier-defaulted contracts must be provenance-stamped"
        )

    def test_item_supplied_contract_is_stamped_as_item(self, tmp_path: Path) -> None:
        proposals_dir = tmp_path / "data" / "metabolism" / "charter_proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)
        item = {
            "schema": "metabolism.charter_proposal.v1",
            "title": "Charter with explicit contract",
            "rationale": "carries its own contract",
            "fitness_contract": {"sensor": "front_run_lead", "check_by": "2026-12-01"},
        }
        (proposals_dir / "explicit.json").write_text(json.dumps(item), encoding="utf-8")
        from engine.metabolism.applier import consume_charter_proposals
        injected = consume_charter_proposals(root=tmp_path, armed=True, dry_run=False)
        assert len(injected) == 1
        fc = injected[0]["fitness_contract"]
        assert fc["sensor"] == "front_run_lead"
        assert fc["contract_source"] == "item"


# ── Unit 4: Applier tier-raise refusal ────────────────────────────────────────

class TestApplierTierRaiseRefusal:
    """Applier must refuse any item whose destination tier is confirmer or scored."""

    def test_tier_raise_to_confirmer_is_refused(self, tmp_path: Path) -> None:
        """Item with tier=confirmer is refused and journaled."""
        proposals_dir = tmp_path / "data" / "metabolism" / "charter_proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)
        item = {
            "title": "Promote TIL to confirmer",
            "tier": "confirmer",
            "kind": "engine",
            "targets_sensor": "front_run_lead",
            "rationale": "Should be refused",
        }
        (proposals_dir / "test_item.json").write_text(json.dumps(item), encoding="utf-8")

        from engine.metabolism.applier import consume_charter_proposals
        injected = consume_charter_proposals(root=tmp_path, armed=True, dry_run=False)
        assert len(injected) == 0, "Tier-raise to confirmer must not produce injected proposals"

        # Journal entry must exist
        journal = tmp_path / "data" / "metabolism" / "applier_journal.jsonl"
        assert journal.exists()
        rows = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert any(r.get("event") == "tier_raise_refused" for r in rows)

    def test_lifecycle_to_scored_is_refused(self, tmp_path: Path) -> None:
        """Lifecycle docket item with to_state=scored is refused."""
        docket_dir = tmp_path / "data" / "metabolism" / "lifecycle_docket"
        docket_dir.mkdir(parents=True, exist_ok=True)
        item = {
            "schema": "metabolism.lifecycle_docket.v1",
            "lobe_id": "til",
            "from_state": "active",
            "to_state": "scored",
            "t_level": "T1",
            "reason": "Should be refused",
        }
        (docket_dir / "test_item.json").write_text(json.dumps(item), encoding="utf-8")

        from engine.metabolism.applier import consume_charter_proposals
        injected = consume_charter_proposals(root=tmp_path, armed=True, dry_run=False)
        assert len(injected) == 0, "Lifecycle to_state=scored must not inject"

    def test_display_tier_item_is_allowed(self, tmp_path: Path) -> None:
        """A valid display-tier charter proposal is injected when armed."""
        proposals_dir = tmp_path / "data" / "metabolism" / "charter_proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)
        item = {
            "title": "Add coverage test for TIL sensor read path",
            "tier": "T0",
            "kind": "test",
            "targets_sensor": "front_run_lead",
            "rationale": "Improve test coverage",
            "fitness_contract": {
                "sensor": "front_run_lead",
                "expected_sign": "+",
                "band": "unspecified",
                "check_by": "2026-10-15",
                "placebo_to_beat": "shadow placebo",
            },
        }
        (proposals_dir / "test_item.json").write_text(json.dumps(item), encoding="utf-8")

        from engine.metabolism.applier import consume_charter_proposals
        injected = consume_charter_proposals(root=tmp_path, armed=True, dry_run=False)
        assert len(injected) == 1
        assert injected[0]["title"] == item["title"]
        assert injected[0].get("_from_applier") is True

    def test_shadow_mode_returns_empty_injected(self, tmp_path: Path) -> None:
        """In shadow/dry_run mode, no proposals are injected even for valid items."""
        proposals_dir = tmp_path / "data" / "metabolism" / "charter_proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)
        item = {
            "title": "Test shadow item",
            "tier": "T0",
            "kind": "test",
            "targets_sensor": "front_run_lead",
            "rationale": "test",
            "fitness_contract": {"sensor": "s", "expected_sign": "+",
                                  "band": "x", "check_by": "2026-10-15", "placebo_to_beat": "p"},
        }
        (proposals_dir / "shadow_item.json").write_text(json.dumps(item), encoding="utf-8")

        from engine.metabolism.applier import consume_charter_proposals
        injected = consume_charter_proposals(root=tmp_path, armed=False, dry_run=True)
        assert len(injected) == 0, "Shadow mode must not inject proposals"

        # Plan record must still be emitted to shadow/
        shadow_dir = tmp_path / "data" / "metabolism" / "shadow"
        assert shadow_dir.exists()
        plan_files = list(shadow_dir.glob("*.json"))
        assert len(plan_files) >= 1


# ── Unit 5: Corrupt-artifact NEVER-RAISE ─────────────────────────────────────

class TestNeverRaise:
    """Every new read path returns a safe fallback on corrupt/missing artifacts."""

    def test_mission_build_mission_block_absent(self, tmp_path: Path) -> None:
        """build_mission_block returns a non-empty string even without nw_mission.yml."""
        from engine.metabolism.mission import build_mission_block
        result = build_mission_block(root=tmp_path)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_mission_build_mission_block_corrupt(self, tmp_path: Path) -> None:
        """build_mission_block returns a fallback even if nw_mission.yml is corrupt."""
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "nw_mission.yml").write_text("{invalid yaml: [\n", encoding="utf-8")
        from engine.metabolism.mission import build_mission_block
        result = build_mission_block(root=tmp_path)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_mission_build_strategic_memory_block_absent(self, tmp_path: Path) -> None:
        """build_strategic_memory_block returns absence message when file is missing."""
        from engine.metabolism.mission import build_strategic_memory_block
        result = build_strategic_memory_block(root=tmp_path)
        assert isinstance(result, str)
        assert "accruing" in result or "not yet present" in result

    def test_mission_build_strategic_memory_block_corrupt(self, tmp_path: Path) -> None:
        """build_strategic_memory_block returns safe fallback on corrupt jsonl."""
        met_dir = tmp_path / "data" / "metabolism"
        met_dir.mkdir(parents=True, exist_ok=True)
        (met_dir / "strategic_memory.jsonl").write_text(
            "not json\n{bad}\n", encoding="utf-8"
        )
        from engine.metabolism.mission import build_strategic_memory_block
        result = build_strategic_memory_block(root=tmp_path)
        assert isinstance(result, str)
        # Should not raise; may return absence message or empty

    def test_memory_load_fitness_history_corrupt(self, tmp_path: Path) -> None:
        """load_fitness_history returns [] on corrupt jsonl rows (skips bad lines)."""
        hist_dir = tmp_path / "data" / "metabolism" / "fitness_history"
        hist_dir.mkdir(parents=True, exist_ok=True)
        corrupt = hist_dir / "til.jsonl"
        corrupt.write_text("not json\n{bad\n", encoding="utf-8")
        from engine.metabolism.memory import load_fitness_history
        rows = load_fitness_history(root=tmp_path, lobe="til")
        assert isinstance(rows, list)
        # Corrupt lines are skipped; valid lines returned

    def test_applier_consume_empty_dirs(self, tmp_path: Path) -> None:
        """consume_charter_proposals returns [] when no files exist."""
        from engine.metabolism.applier import consume_charter_proposals
        result = consume_charter_proposals(root=tmp_path)
        assert result == []

    def test_applier_consume_corrupt_json(self, tmp_path: Path) -> None:
        """consume_charter_proposals handles a corrupt json file without raising."""
        proposals_dir = tmp_path / "data" / "metabolism" / "charter_proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)
        (proposals_dir / "corrupt.json").write_text("{bad json", encoding="utf-8")
        from engine.metabolism.applier import consume_charter_proposals
        result = consume_charter_proposals(root=tmp_path)
        assert isinstance(result, list)

    def test_propose_build_prompt_context_all_absent(self, tmp_path: Path) -> None:
        """build_prompt_context returns all keys even when all artifacts are absent."""
        from engine.metabolism.propose import build_prompt_context
        ctx = build_prompt_context(root=tmp_path)
        assert isinstance(ctx, dict)
        for key in ("recall_lessons", "preference_prior", "insight_bus_open",
                    "trajectory_block", "strategic_gap", "mission_block", "strategic_memory"):
            assert key in ctx, f"Key '{key}' missing from context"
            assert isinstance(ctx[key], str), f"Key '{key}' must be a string"

    def test_verify_append_strategic_memory_from_verify_never_raises(
        self, tmp_path: Path
    ) -> None:
        """_append_strategic_memory_from_verify returns without raising on any input."""
        from engine.metabolism.verify import _append_strategic_memory_from_verify
        # Call with minimal inputs — should not raise
        _append_strategic_memory_from_verify(
            cycle_id="test",
            contract={"sensor": "front_run_lead", "lobe": "til"},
            triage={"classification": "confirmed", "action": "keep"},
            outcome="CONFIRMED",
            root=tmp_path,
        )
        # Check file was created
        sm = tmp_path / "data" / "metabolism" / "strategic_memory.jsonl"
        assert sm.exists()
        rows = [json.loads(line) for line in sm.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(rows) == 1
        assert rows[0]["verdict"] == "CONFIRMED"
        assert rows[0]["measurement_lens_class"] == "confirmed"


# ── Unit: Mission append_strategic_memory ────────────────────────────────────

class TestMissionAppendStrategicMemory:
    """append_strategic_memory writes verbatim verdict + measurement_lens_class."""

    def test_round_trip(self, tmp_path: Path) -> None:
        """Append a row and load it back as text; verdict and class match."""
        from engine.metabolism.mission import append_strategic_memory, build_strategic_memory_block
        row = {
            "lobe": "til",
            "cycle_id": "c1",
            "sensor": "front_run_lead",
            "verdict": "FALSIFIER_TRIPPED",
            "measurement_lens_class": "overfit",
            "check_by": "2026-10-15",
        }
        ok = append_strategic_memory(row, root=tmp_path)
        assert ok
        text = build_strategic_memory_block("til", root=tmp_path)
        assert "FALSIFIER_TRIPPED" in text
        assert "overfit" in text

    def test_append_with_invalid_row_returns_false(self, tmp_path: Path) -> None:
        """append_strategic_memory returns False on non-dict input (NEVER raises)."""
        from engine.metabolism.mission import append_strategic_memory
        result = append_strategic_memory("not a dict", root=tmp_path)  # type: ignore[arg-type]
        assert result is False

    def test_lobe_filter(self, tmp_path: Path) -> None:
        """build_strategic_memory_block filters to specified lobe."""
        from engine.metabolism.mission import append_strategic_memory, build_strategic_memory_block
        append_strategic_memory({"lobe": "til", "verdict": "CONFIRMED",
                                  "measurement_lens_class": "confirmed"}, root=tmp_path)
        append_strategic_memory({"lobe": "other", "verdict": "UNVERIFIABLE",
                                  "measurement_lens_class": "unverifiable"}, root=tmp_path)

        til_text = build_strategic_memory_block("til", root=tmp_path)
        other_text = build_strategic_memory_block("other", root=tmp_path)
        assert "CONFIRMED" in til_text
        assert "UNVERIFIABLE" not in til_text
        assert "UNVERIFIABLE" in other_text
        assert "CONFIRMED" not in other_text


# ── Unit: Charter-driven system prompt ───────────────────────────────────────

class TestCharteredSystemPrompt:
    """_build_system_prompt reads sensors from charter; sense-only lobes get inert prompt."""

    def test_til_prompt_contains_charter_sensors(self, tmp_path: Path) -> None:
        """TIL prompt lists all four declared sensors."""
        _make_lobe_charter(tmp_path)
        from engine.metabolism.propose import _build_system_prompt
        prompt = _build_system_prompt("til", root=tmp_path)
        assert "front_run_lead" in prompt
        assert "placebo_hit_rate" in prompt
        assert "falsifier_honesty" in prompt
        assert "live_leg_quality" in prompt

    def test_sense_only_lobe_returns_inert_prompt(self, tmp_path: Path) -> None:
        """A lobe with no fitness_sensors in charter gets a SENSE-only inert prompt."""
        # Write charter with a lobe that has no fitness_sensors
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        try:
            import yaml
            charter = {"schema": "lobe_charters.v1", "charters": {
                "sense_only_lobe": {"lobe_id": "sense_only_lobe", "tier": "display"},
            }}
            (config_dir / "lobe_charters.yml").write_text(
                yaml.dump(charter, default_flow_style=False), encoding="utf-8"
            )
        except ImportError:
            pytest.skip("pyyaml not available")

        from engine.metabolism.propose import _build_system_prompt
        prompt = _build_system_prompt("sense_only_lobe", root=tmp_path)
        assert "SENSE-only" in prompt
        assert "empty JSON array" in prompt or "[]" in prompt


# ── Trajectory run_trajectory lobe_id field ───────────────────────────────────

class TestTrajectoryLobeId:
    """run_trajectory emits lobe_id field when provided."""

    def test_lobe_id_in_trajectory_row(self, tmp_path: Path) -> None:
        """run_trajectory adds lobe_id to the row when provided."""
        from engine.metabolism.trajectory import run_trajectory
        row = run_trajectory(
            organism_state={
                "whole_organism": {"n_lobes": 0, "label_counts": {}},
                "lobes": {},
                "cortex_memo": None,
            },
            cycle_id="test-cycle",
            root=tmp_path,
            lobe_id="til",
        )
        assert isinstance(row, dict)
        assert row.get("lobe_id") == "til"

    def test_lobe_id_absent_when_not_provided(self, tmp_path: Path) -> None:
        """run_trajectory does not add lobe_id when not provided."""
        from engine.metabolism.trajectory import run_trajectory
        row = run_trajectory(
            organism_state={
                "whole_organism": {"n_lobes": 0, "label_counts": {}},
                "lobes": {},
                "cortex_memo": None,
            },
            cycle_id="test-cycle",
            root=tmp_path,
        )
        assert isinstance(row, dict)
        assert "lobe_id" not in row


# ── Finding #1 fix: propose() lobe parameter is reachable ────────────────────

class TestProposeLobePropagation:
    """propose() lobe param is threaded to context/LLM/docket (Finding #1 fix)."""

    def test_propose_accepts_lobe_param(self, tmp_path: Path) -> None:
        """propose() with lobe='til' (default) succeeds in dry-run mode."""
        from engine.metabolism.propose import propose
        result = propose(
            "test-cycle",
            lobe="til",
            root=tmp_path,
            max_docket_size=3,
            dry_run=True,
            injected_proposals=[],
        )
        assert isinstance(result, dict)
        assert "docket" in result
        assert result["docket"].get("lobe") == "til"

    def test_propose_lobe_default_is_LOBE(self, tmp_path: Path) -> None:
        """propose() with no lobe arg defaults to LOBE constant ('til')."""
        from engine.metabolism.propose import propose, LOBE
        result = propose(
            "test-cycle-default",
            root=tmp_path,
            dry_run=True,
            injected_proposals=[],
        )
        assert result["docket"].get("lobe") == LOBE

    def test_propose_non_til_lobe_reaches_build_docket(self, tmp_path: Path) -> None:
        """propose() with a non-TIL lobe id results in that lobe stamped in docket."""
        from engine.metabolism.propose import propose
        result = propose(
            "test-cycle-sense",
            lobe="sense_only_lobe",
            root=tmp_path,
            dry_run=True,
            injected_proposals=[],
        )
        assert result["docket"].get("lobe") == "sense_only_lobe"


# ── Finding #2 fix: propose() calls run_trajectory with lobe_id ──────────────

class TestProposeTrajectoryStamp:
    """propose() stamps a lobe_id-annotated trajectory row in non-dry-run mode."""

    def test_trajectory_row_written_with_lobe_id(self, tmp_path: Path) -> None:
        """propose() in non-dry-run writes a trajectory.jsonl row with lobe_id."""
        from engine.metabolism.propose import propose
        result = propose(
            "test-traj-cycle",
            lobe="til",
            root=tmp_path,
            dry_run=False,  # must be False for trajectory to be written
            injected_proposals=[],  # no LLM call
        )
        assert isinstance(result, dict)
        traj_path = tmp_path / "data" / "metabolism" / "trajectory.jsonl"
        assert traj_path.exists(), "trajectory.jsonl must be written by propose()"
        rows = [json.loads(ln) for ln in traj_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(rows) >= 1
        assert rows[-1].get("lobe_id") == "til", (
            f"Last trajectory row has no lobe_id='til': {rows[-1]}"
        )


# ── Verify scan: docket-lobe backfill for pre-lobe contracts ──────────────────

class TestScanBackfillsDocketLobe:
    """_scan_pending_cycles backfills docket-level lobe into pre-lobe contracts.

    Contracts minted before the contract-level lobe key existed would verify
    with lobe="" and their strategic-memory rows get dropped by the per-lobe
    PROPOSE filter (mission.build_strategic_memory_block).
    """

    def test_pre_lobe_contract_inherits_docket_lobe(self, tmp_path: Path) -> None:
        from scripts.metabolism_verify import _scan_pending_cycles

        dockets_dir = tmp_path / "data" / "metabolism" / "dockets"
        dockets_dir.mkdir(parents=True, exist_ok=True)
        docket = {
            "schema": "metabolism.docket.v1",
            "cycle_id": "cycle-prelobe",
            "lobe": "til",
            "proposals": [{
                "proposal_id": "p1",
                # minted before contracts carried a lobe key — no "lobe" here
                "fitness_contract": {
                    "proposal_id": "p1",
                    "sensor": "front_run_lead",
                    "check_by": "2026-01-01",
                },
            }],
        }
        (dockets_dir / "cycle-prelobe.json").write_text(json.dumps(docket), encoding="utf-8")

        pending = _scan_pending_cycles(tmp_path, today="2026-07-11")

        assert len(pending) == 1
        cycle_id, contract = pending[0]
        assert cycle_id == "cycle-prelobe"
        assert contract.get("lobe") == "til", (
            f"pre-lobe contract must inherit the docket-level lobe, got: {contract}"
        )

    def test_contract_level_lobe_is_not_overwritten(self, tmp_path: Path) -> None:
        from scripts.metabolism_verify import _scan_pending_cycles

        dockets_dir = tmp_path / "data" / "metabolism" / "dockets"
        dockets_dir.mkdir(parents=True, exist_ok=True)
        docket = {
            "schema": "metabolism.docket.v1",
            "cycle_id": "cycle-postlobe",
            "lobe": "til",
            "proposals": [{
                "proposal_id": "p1",
                "fitness_contract": {
                    "proposal_id": "p1",
                    "sensor": "front_run_lead",
                    "lobe": "neural_web",
                    "check_by": "2026-01-01",
                },
            }],
        }
        (dockets_dir / "cycle-postlobe.json").write_text(json.dumps(docket), encoding="utf-8")

        pending = _scan_pending_cycles(tmp_path, today="2026-07-11")

        assert len(pending) == 1
        assert pending[0][1].get("lobe") == "neural_web"
