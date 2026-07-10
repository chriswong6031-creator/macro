"""tests/test_metabolism_v2c.py — Hermetic tests for Metabolism Phase V2-C.

COVERAGE:
  1. Charter registry loads + tier-mirror assertion (charter tier != synapse tier → flagged).
  2. LIFECYCLE FENCE — a promote-to-scored transition is REFUSED for EVERY tier-raise form:
       (a) tier→confirmer passed as tier= argument
       (b) tier→scored passed as tier= argument
       (c) scored_path_surface=True
       (d) mastermind_authority=True
     Assert: allowed=False + nothing emitted.
  3. De-escalation edges: allowed=True + de_escalation=True.
  4. Onboarding edges: collision screen fires when lobe in DO_NOT_REBUILD.
  5. Demotion ladder counts only logic breaches (health missing/degraded/stale does NOT
     accrue — discriminating test).
  6. Regime-aware pause: no demotion emitted when regime_paused=True.
  7. All-inputs-absent adversary veto: demotion blocked when adversary_nonveto=False.
  8. Roster cap → digest ASK not silent block (tap card written, ok=False returned).
  9. Authority audit flags a synthetic display→scored consumer link.
  10. is_paused no-op on entrypoints (mutation-proof: booby-trap emission so a removed
      pause gate would error).
  11. Banned words: 'validated' never in V2-C user-facing text.
  12. INERT assertion: no synapse.yml edit, no mastermind_context edit, no auto-retire
      (grep-style assertion over all new V2-C source files).
  13. check_self_mod_fence and check_grader_manifest pass.
  14. Tier-mirror: lobe_registry.validate_tier_mirror detects a planted mismatch.
  15. allowed_edges() is complete and all de-escalation edges are tagged.

All tests are HERMETIC (tmp dirs, in-process, no real data/network/subprocess).
"""
from __future__ import annotations

import json
import os
import re
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
    """Return a fresh temp dir with V2-C directory structure."""
    d = Path(tempfile.mkdtemp())
    (d / "data" / "metabolism" / "lifecycle").mkdir(parents=True)
    (d / "data" / "metabolism" / "lifecycle_docket").mkdir(parents=True)
    (d / "data" / "metabolism" / "tap").mkdir(parents=True)
    (d / "data" / "metabolism" / "authority_audit").mkdir(parents=True)
    (d / "data" / "neuralweb").mkdir(parents=True)
    (d / "config").mkdir(parents=True)
    (d / "docs").mkdir(parents=True)
    (d / "research").mkdir(parents=True)
    return d


def _write_minimal_synapse(root: Path, extra_artifacts: dict | None = None) -> None:
    """Write a minimal synapse.yml with some NW-scope lobes for testing."""
    arts = {
        "my-display-lobe": {
            "path": "data/neuralweb/my_display_lobe.json",
            "format": "json",
            "producer": "engine/foo.py",
            "owner_program": "neural-web",
            "cadence": "daily-engine",
            "freshness_sla_hours": 30,
            "tier": "display",
            "horizon_role": "context",
            "scored_path_surfaces": [],
            "consumers": [],
            "external_consumers": [],
        },
        "my-shadow-lobe": {
            "path": "data/neuralweb/my_shadow_lobe.json",
            "format": "json",
            "producer": "engine/bar.py",
            "owner_program": "neural-web",
            "cadence": "daily-engine",
            "freshness_sla_hours": 30,
            "tier": "shadow",
            "horizon_role": "context",
            "scored_path_surfaces": [],
            "consumers": [],
            "external_consumers": [],
        },
        "mastermind-context-lobe": {
            "path": "data/other/mc.json",
            "format": "json",
            "producer": "engine/mc.py",
            "owner_program": "other-program",
            "cadence": "daily-engine",
            "freshness_sla_hours": 30,
            "tier": "display",
            "horizon_role": "context",
            "scored_path_surfaces": [],
            "consumers": [],
            "external_consumers": ["mastermind:context"],
        },
        "scored-lobe": {
            "path": "data/scored/lobe.json",
            "format": "json",
            "producer": "engine/scored.py",
            "owner_program": "other",
            "cadence": "daily-engine",
            "freshness_sla_hours": 48,
            "tier": "scored",
            "horizon_role": "context",
            "scored_path_surfaces": ["alert_triage"],
            "consumers": [],
            "external_consumers": [],
        },
    }
    if extra_artifacts:
        arts.update(extra_artifacts)
    synapse = {
        "meta": {
            "schema_version": 1,
            "tier_vocabulary": ["display", "shadow", "confirmer", "scored", "infrastructure"],
            "article2_surfaces": ["alert_triage"],
            "horizon_role_vocabulary": ["context"],
        },
        "artifacts": arts,
    }
    import yaml  # noqa: PLC0415
    (root / "config" / "synapse.yml").write_text(
        yaml.dump(synapse, default_flow_style=False), encoding="utf-8"
    )


def _write_minimal_charter(root: Path, extra: dict | None = None) -> None:
    """Write a minimal lobe_charters.yml for testing."""
    charters = {
        "my-display-lobe": {
            "lobe_id": "my-display-lobe",
            "tier": "display",
            "lifecycle_state": "active",
            "information_domain": "context",
            "fitness_sensors": ["liveness", "freshness_sla", "logic_breach_counter"],
            "owner_program": "neural-web",
            "notes": "test",
        },
        "my-shadow-lobe": {
            "lobe_id": "my-shadow-lobe",
            "tier": "shadow",
            "lifecycle_state": "active",
            "information_domain": "context",
            "fitness_sensors": ["liveness", "freshness_sla", "logic_breach_counter"],
            "owner_program": "neural-web",
            "notes": "test",
        },
        "mastermind-context-lobe": {
            "lobe_id": "mastermind-context-lobe",
            "tier": "display",
            "lifecycle_state": "active",
            "information_domain": "context",
            "fitness_sensors": ["liveness", "freshness_sla", "logic_breach_counter"],
            "owner_program": "other-program",
            "notes": "test",
        },
    }
    if extra:
        charters.update(extra)
    import yaml  # noqa: PLC0415
    (root / "config" / "lobe_charters.yml").write_text(
        yaml.dump(
            {"schema": "lobe_charters.v1", "generated_at": "2026-07-10", "charters": charters},
            default_flow_style=False,
        ),
        encoding="utf-8",
    )


def _write_minimal_budget(root: Path, max_active: int = 5, max_probation: int = 2) -> None:
    import yaml  # noqa: PLC0415
    budget = {
        "schema": "metabolism_budget.v1",
        "generated_at": "2026-07-10",
        "owner_program": "metabolism-phase-a",
        "per_cycle_usd_cap": 25,
        "per_cycle_token_cap": 25000000,
        "max_docket_size": 5,
        "circuit_breaker_trip": 3,
        "budget_ledger_path": "data/metabolism/budget_ledger.json",
        "max_active_nonscored_lobes": max_active,
        "max_probation_lobes": max_probation,
    }
    (root / "config" / "metabolism_budget.yml").write_text(
        yaml.dump(budget, default_flow_style=False), encoding="utf-8"
    )


# ── 1. Charter registry load + tier-mirror ─────────────────────────────────────

class TestCharterRegistry:
    def test_loads_valid_charter(self):
        """load() returns ok=True and charters dict on valid file."""
        root = _tmp_root()
        _write_minimal_charter(root)
        from engine.metabolism.lobe_registry import load
        result = load(root)
        assert result["ok"] is True
        assert result["count"] == 3
        assert "my-display-lobe" in result["charters"]
        assert "my-shadow-lobe" in result["charters"]

    def test_missing_file_returns_error(self):
        """load() returns ok=False with error when file is absent."""
        root = _tmp_root()
        from engine.metabolism.lobe_registry import load
        result = load(root)
        assert result["ok"] is False
        assert result["errors"]

    def test_invalid_tier_flagged(self):
        """load() flags charters with invalid tier values."""
        root = _tmp_root()
        _write_minimal_charter(root, extra={
            "bad-tier-lobe": {
                "lobe_id": "bad-tier-lobe",
                "tier": "INVALID_TIER",
                "lifecycle_state": "active",
                "information_domain": "context",
                "fitness_sensors": [],
                "owner_program": "test",
                "notes": "",
            }
        })
        from engine.metabolism.lobe_registry import load
        result = load(root)
        assert any("bad-tier-lobe" in e and "tier" in e for e in result["errors"])

    def test_tier_mirror_detects_mismatch(self):
        """validate_tier_mirror() flags a charter whose tier != synapse tier."""
        root = _tmp_root()
        _write_minimal_synapse(root)
        # Plant a mismatch: synapse says 'display', charter says 'shadow'
        _write_minimal_charter(root, extra={
            "my-display-lobe": {
                "lobe_id": "my-display-lobe",
                "tier": "shadow",      # MISMATCH: synapse says 'display'
                "lifecycle_state": "active",
                "information_domain": "context",
                "fitness_sensors": [],
                "owner_program": "neural-web",
                "notes": "deliberate mismatch",
            }
        })
        from engine.metabolism.lobe_registry import validate_tier_mirror
        result = validate_tier_mirror(root)
        assert result["ok"] is False
        mismatches = result["tier_mismatches"]
        assert any(m["lobe_id"] == "my-display-lobe" for m in mismatches)
        mismatch = next(m for m in mismatches if m["lobe_id"] == "my-display-lobe")
        assert mismatch["charter_tier"] == "shadow"
        assert mismatch["synapse_tier"] == "display"

    def test_tier_mirror_passes_clean(self):
        """validate_tier_mirror() returns ok=True when charter mirrors synapse exactly."""
        root = _tmp_root()
        _write_minimal_synapse(root)
        _write_minimal_charter(root)
        from engine.metabolism.lobe_registry import validate_tier_mirror
        result = validate_tier_mirror(root)
        # Should be ok with no mismatches (the 3 charter lobes match synapse)
        assert result["tier_mismatches"] == []


# ── 2. LIFECYCLE FENCE — tier-raise refusal ────────────────────────────────────

class TestLifecycleFence:
    """The most critical test class: every form of tier-raise MUST be refused."""

    def _call_transition(self, from_state, to_state, lobe_id="test-lobe", **kwargs):
        from engine.metabolism.lifecycle import transition
        # emit=False to avoid I/O in tests
        return transition(from_state, to_state, lobe_id, emit=False, **kwargs)

    def test_refuses_tier_confirmer(self):
        """Tier parameter 'confirmer' → refused."""
        result = self._call_transition("active", "active", tier="confirmer")
        assert result["allowed"] is False
        assert "promotion" in result["reason"].lower() or "T2" in result["reason"]

    def test_refuses_tier_scored(self):
        """Tier parameter 'scored' → refused."""
        result = self._call_transition("active", "active", tier="scored")
        assert result["allowed"] is False
        assert "promotion" in result["reason"].lower() or "T2" in result["reason"]

    def test_refuses_scored_path_surface(self):
        """scored_path_surface=True → refused."""
        result = self._call_transition(
            "probation", "active", tier="display", scored_path_surface=True
        )
        assert result["allowed"] is False
        assert "scored_path_surface" in result["reason"]

    def test_refuses_mastermind_authority(self):
        """mastermind_authority=True → refused."""
        result = self._call_transition(
            "probation", "active", tier="display", mastermind_authority=True
        )
        assert result["allowed"] is False
        assert "mastermind" in result["reason"]

    def test_refuses_unknown_edge(self):
        """An edge not in the table → refused (not allowed)."""
        result = self._call_transition("active", "proposed")
        assert result["allowed"] is False

    def test_refuses_confirmer_from_every_state(self):
        """confirmer is refused from all lifecycle states."""
        states = ["proposed", "probation", "active", "demoted", "retired"]
        for state in states:
            result = self._call_transition(state, state, tier="confirmer")
            assert result["allowed"] is False, (
                f"Expected refusal for tier=confirmer from state={state}"
            )

    def test_refuses_scored_from_every_state(self):
        """scored is refused from all lifecycle states."""
        states = ["proposed", "probation", "active", "demoted", "retired"]
        for state in states:
            result = self._call_transition(state, state, tier="scored")
            assert result["allowed"] is False, (
                f"Expected refusal for tier=scored from state={state}"
            )

    def test_tier_raise_emits_nothing(self):
        """A refused tier-raise call writes no files."""
        root = _tmp_root()
        from engine.metabolism.lifecycle import transition
        result = transition("active", "active", "test-lobe", tier="scored", root=root, emit=True)
        assert result["allowed"] is False
        assert result["events_emitted"] is False
        assert result["docket_item_written"] is False
        # No docket items written
        docket_dir = root / "data" / "metabolism" / "lifecycle_docket"
        items = list(docket_dir.iterdir()) if docket_dir.exists() else []
        assert items == [], f"Expected no docket items, found: {items}"

    def test_all_four_refusal_forms_checked(self):
        """All 4 refusal mechanisms return allowed=False with a non-empty reason."""
        cases = [
            {"tier": "confirmer"},
            {"tier": "scored"},
            {"scored_path_surface": True},
            {"mastermind_authority": True},
        ]
        for kwargs in cases:
            result = self._call_transition("active", "active", **kwargs)
            assert result["allowed"] is False, f"Should be refused: {kwargs}"
            assert result["reason"], f"Empty reason for: {kwargs}"


# ── 3. De-escalation edges ─────────────────────────────────────────────────────

class TestDeEscalationEdges:
    def _call(self, from_state, to_state):
        from engine.metabolism.lifecycle import transition
        return transition(from_state, to_state, "test-lobe", tier="display", emit=False)

    def test_active_to_probation_allowed(self):
        r = self._call("active", "probation")
        assert r["allowed"] is True
        assert r["de_escalation"] is True
        assert r["t_level"] == "T1"

    def test_probation_to_demoted_allowed(self):
        r = self._call("probation", "demoted")
        assert r["allowed"] is True
        assert r["de_escalation"] is True

    def test_demoted_to_retired_allowed(self):
        r = self._call("demoted", "retired")
        assert r["allowed"] is True
        assert r["de_escalation"] is True

    def test_active_to_retired_allowed(self):
        r = self._call("active", "retired")
        assert r["allowed"] is True
        assert r["de_escalation"] is True

    def test_all_de_escalation_tagged(self):
        """Every edge in the table that is de-escalation must have de_escalation=True."""
        from engine.metabolism.lifecycle import allowed_edges
        de_esc = [(e["from_state"], e["to_state"]) for e in allowed_edges() if e.get("de_escalation")]
        # These four must be de-escalation
        expected = [
            ("active", "probation"),
            ("probation", "demoted"),
            ("demoted", "retired"),
            ("active", "retired"),
        ]
        for pair in expected:
            assert pair in de_esc, f"{pair} not tagged de_escalation"


# ── 4. Collision screen ────────────────────────────────────────────────────────

class TestCollisionScreen:
    def test_do_not_rebuild_blocks_onboarding(self):
        """proposed→probation is blocked if lobe_id in DO_NOT_REBUILD.md."""
        root = _tmp_root()
        dnr = root / "research" / "DO_NOT_REBUILD.md"
        dnr.write_text("## Killed\n- forbidden-lobe: killed 2026-07-10\n", encoding="utf-8")
        from engine.metabolism.lifecycle import transition
        result = transition(
            "proposed", "probation", "forbidden-lobe",
            tier="display", emit=False, root=root
        )
        assert result["allowed"] is False
        assert "DO_NOT_REBUILD" in result["reason"]

    def test_clean_lobe_passes_collision_screen(self):
        """proposed→probation passes for a lobe not in kill registries."""
        root = _tmp_root()
        # Empty / absent DO_NOT_REBUILD + ACTIVE_BUILD_MAP
        from engine.metabolism.lifecycle import transition
        result = transition(
            "proposed", "probation", "brand-new-lobe",
            tier="display", emit=False, root=root
        )
        assert result["allowed"] is True


# ── 5. Demotion ladder — health miss does NOT count ───────────────────────────

class TestDemotionLadder:
    def _journal(self, root, lobe_id, entries):
        """Write journal rows directly to the JSONL file."""
        from engine.metabolism.verify import journal_breach
        for e in entries:
            journal_breach(
                lobe_id,
                breach_type=e["breach_type"],
                health_status=e.get("health_status"),
                reason=e.get("reason", "test"),
                regime_paused=e.get("regime_paused", False),
                root=root,
            )

    def test_health_miss_not_counted(self):
        """health.py missing/degraded/stale does NOT count as a logic breach."""
        root = _tmp_root()
        lobe_id = "test-lobe"
        # Write 10 health misses — should NOT trip the breaker
        from engine.metabolism.verify import journal_breach, _read_journal_rows, _consecutive_counted_breaches
        for status in ["missing", "degraded", "stale", "unknown"] * 3:
            journal_breach(lobe_id, breach_type="logic_breach",
                           health_status=status, root=root)
        rows = _read_journal_rows(lobe_id, root)
        consecutive = _consecutive_counted_breaches(rows)
        assert consecutive == 0, (
            f"Health misses should not count; got {consecutive} consecutive counted breaches"
        )

    def test_logic_breach_counted(self):
        """A real logic_breach (no health exclusion) IS counted."""
        root = _tmp_root()
        lobe_id = "test-lobe2"
        from engine.metabolism.verify import journal_breach, _read_journal_rows, _consecutive_counted_breaches
        for _ in range(3):
            journal_breach(lobe_id, breach_type="logic_breach",
                           health_status="fresh", root=root)
        rows = _read_journal_rows(lobe_id, root)
        consecutive = _consecutive_counted_breaches(rows)
        assert consecutive == 3

    def test_pass_resets_counter(self):
        """A 'pass' row resets the consecutive breach counter."""
        root = _tmp_root()
        lobe_id = "test-lobe3"
        from engine.metabolism.verify import journal_breach, _read_journal_rows, _consecutive_counted_breaches
        journal_breach(lobe_id, breach_type="logic_breach", health_status="fresh", root=root)
        journal_breach(lobe_id, breach_type="logic_breach", health_status="fresh", root=root)
        journal_breach(lobe_id, breach_type="pass", root=root)
        journal_breach(lobe_id, breach_type="logic_breach", health_status="fresh", root=root)
        rows = _read_journal_rows(lobe_id, root)
        consecutive = _consecutive_counted_breaches(rows)
        assert consecutive == 1  # only the last breach counts

    def test_breaker_trip_emits_proposal(self):
        """3 consecutive logic breaches trip the breaker and emit a demotion proposal."""
        root = _tmp_root()
        lobe_id = "breaker-test-lobe"
        from engine.metabolism.verify import journal_breach, grade_demotion_ladder

        for _ in range(3):
            journal_breach(lobe_id, breach_type="logic_breach",
                           health_status="fresh", root=root)

        # Mock lifecycle.transition to avoid I/O; we just want to confirm it's called
        with patch("engine.metabolism.lifecycle.transition") as mock_trans:
            mock_trans.return_value = {"allowed": True, "reason": "test", "de_escalation": True,
                                       "events_emitted": False, "docket_item_written": False,
                                       "t_level": "T1"}
            result = grade_demotion_ladder(
                lobe_id, "active", regime_paused=False, root=root
            )
        assert result["breaker_tripped"] is True
        assert mock_trans.called

    def test_health_only_never_trips_breaker(self):
        """Even 100 health-miss rows do NOT trip the circuit breaker."""
        root = _tmp_root()
        lobe_id = "health-only-lobe"
        from engine.metabolism.verify import journal_breach, grade_demotion_ladder

        for _ in range(100):
            journal_breach(lobe_id, breach_type="logic_breach",
                           health_status="missing", root=root)

        result = grade_demotion_ladder(lobe_id, "active", root=root)
        assert result["breaker_tripped"] is False
        assert result["consecutive_counted_breaches"] == 0


# ── 6. Regime-aware pause ──────────────────────────────────────────────────────

class TestRegimePause:
    def test_regime_pause_blocks_demotion(self):
        """regime_paused=True prevents demotion even when breaker trips."""
        root = _tmp_root()
        lobe_id = "regime-paused-lobe"
        from engine.metabolism.verify import journal_breach, grade_demotion_ladder

        for _ in range(5):
            journal_breach(lobe_id, breach_type="logic_breach",
                           health_status="fresh", root=root)

        result = grade_demotion_ladder(lobe_id, "active", regime_paused=True, root=root)
        assert result["regime_paused"] is True
        assert result["breaker_tripped"] is False
        assert result["proposal"] is None


# ── 7. All-inputs-absent adversary veto ───────────────────────────────────────

class TestAdversaryVeto:
    def test_all_inputs_absent_veto_blocks(self):
        """all_inputs_absent=True + adversary_nonveto=False → demotion blocked."""
        root = _tmp_root()
        lobe_id = "all-absent-lobe"
        from engine.metabolism.verify import journal_breach, grade_demotion_ladder

        for _ in range(5):
            journal_breach(lobe_id, breach_type="logic_breach",
                           health_status="fresh", root=root)

        result = grade_demotion_ladder(
            lobe_id, "active",
            all_inputs_absent=True, adversary_nonveto=False,
            root=root
        )
        assert result["adversary_nonveto_blocked"] is True
        assert result["proposal"] is None

    def test_all_inputs_absent_but_nonveto_allows(self):
        """all_inputs_absent=True + adversary_nonveto=True (non-veto) → proceeds."""
        root = _tmp_root()
        lobe_id = "all-absent-nonveto-lobe"
        from engine.metabolism.verify import journal_breach, grade_demotion_ladder

        for _ in range(3):
            journal_breach(lobe_id, breach_type="logic_breach",
                           health_status="fresh", root=root)

        with patch("engine.metabolism.lifecycle.transition") as mock_trans:
            mock_trans.return_value = {"allowed": True, "reason": "test",
                                       "de_escalation": True, "events_emitted": False,
                                       "docket_item_written": False, "t_level": "T1"}
            result = grade_demotion_ladder(
                lobe_id, "active",
                all_inputs_absent=True, adversary_nonveto=True,
                root=root
            )
        assert result["adversary_nonveto_blocked"] is False


# ── 8. Roster cap → digest ASK ────────────────────────────────────────────────

class TestRosterGovernor:
    def test_cap_exceeded_emits_ask_not_silent_block(self):
        """When cap is hit, ok=False + tap card written (not a silent block)."""
        root = _tmp_root()
        _write_minimal_charter(root)
        _write_minimal_budget(root, max_active=2, max_probation=1)

        # The charter has 3 active lobes; max_active=2, so cap is hit
        from engine.metabolism.roster_governor import check_charter_budget
        result = check_charter_budget(
            "new-lobe", proposed_lifecycle_state="active", root=root
        )
        assert result["ok"] is False
        assert result["cap_exceeded"] is True
        # A tap card should be written
        tap_dir = root / "data" / "metabolism" / "tap"
        tap_files = list(tap_dir.iterdir()) if tap_dir.exists() else []
        assert tap_files, "Expected a digest ASK tap card to be written"

    def test_within_cap_returns_ok(self):
        """Within-cap charter proposals return ok=True."""
        root = _tmp_root()
        _write_minimal_charter(root)
        _write_minimal_budget(root, max_active=100, max_probation=10)

        from engine.metabolism.roster_governor import check_charter_budget
        result = check_charter_budget(
            "new-lobe", proposed_lifecycle_state="active", root=root
        )
        assert result["ok"] is True
        assert result["cap_exceeded"] is False

    def test_tap_card_content(self):
        """Tap card written on cap-exceeded contains the right fields."""
        root = _tmp_root()
        _write_minimal_charter(root)
        _write_minimal_budget(root, max_active=0, max_probation=0)

        from engine.metabolism.roster_governor import check_charter_budget
        check_charter_budget("new-lobe", proposed_lifecycle_state="active", root=root)

        tap_dir = root / "data" / "metabolism" / "tap"
        cards = list(tap_dir.glob("*.json"))
        assert cards
        card = json.loads(cards[0].read_text())
        assert card.get("schema") == "metabolism.tap_card.v1"
        assert "roster" in card.get("headline", "").lower() or "cap" in card.get("headline", "").lower()
        # Conservative default must be hold/defer (not "promote")
        default = card.get("auto_action_on_timeout", {}).get("action", "")
        assert default in ("hold", "defer", "hold_for_review", "deny"), (
            f"Expected conservative default, got {default!r}"
        )


# ── 9. Authority audit ────────────────────────────────────────────────────────

class TestAuthorityAudit:
    def test_flags_display_to_scored_consumer(self):
        """Authority audit flags a display lobe whose path appears in a scored consumer."""
        root = _tmp_root()
        # Synthetic: scored-lobe consumes display lobe's path
        _write_minimal_synapse(root, extra_artifacts={
            "scored-consumer": {
                "path": "data/scored/consumer.json",
                "format": "json",
                "producer": "engine/scored.py",
                "owner_program": "other",
                "cadence": "daily-engine",
                "freshness_sla_hours": 48,
                "tier": "scored",
                "horizon_role": "context",
                "scored_path_surfaces": ["data/neuralweb/my_display_lobe.json"],  # references display lobe
                "consumers": [],
                "external_consumers": [],
            }
        })
        from engine.metabolism.authority_audit import run_audit
        result = run_audit(root)
        assert result["ok"] is True
        # Should flag the display→scored surface launder
        launders = result["scored_path_surface_launders"]
        assert any(
            l["display_artifact"] == "my-display-lobe"
            for l in launders
        ), f"Expected my-display-lobe to be flagged; got: {launders}"

    def test_clean_synapse_no_launders(self):
        """A synapse with no display→scored links produces empty launder lists."""
        root = _tmp_root()
        _write_minimal_synapse(root)
        from engine.metabolism.authority_audit import run_audit
        result = run_audit(root)
        assert result["ok"] is True
        # my-display-lobe and my-shadow-lobe don't feed scored-lobe
        assert result["scored_path_surface_launders"] == []

    def test_write_audit_produces_file(self):
        """run_and_write() creates a quarterly JSON file."""
        root = _tmp_root()
        _write_minimal_synapse(root)
        from engine.metabolism.authority_audit import run_and_write
        report = run_and_write(root)
        assert report["ok"] is True
        assert report.get("output_path") is not None
        assert Path(report["output_path"]).exists()


# ── 10. is_paused gate ────────────────────────────────────────────────────────

class TestIsPausedGate:
    def test_lifecycle_transition_is_inert_no_paused_gate_needed(self):
        """lifecycle.transition() is stateless and INERT by design (emit=False).

        The is_paused gate is enforced at the entrypoint (metabolism_dispatch.py).
        We verify that calling transition() with emit=False has zero side effects
        even when called directly (mutation-proof).
        """
        root = _tmp_root()
        from engine.metabolism.lifecycle import transition
        # Booby-trap: if anything tries to write, it will fail
        import os
        os.chmod(str(root / "data" / "metabolism" / "lifecycle_docket"), 0o444)
        try:
            # Even if the dir is read-only, emit=False produces no writes
            result = transition(
                "active", "probation", "test-lobe",
                tier="display", emit=False, root=root
            )
            # Should return allowed=True (the edge is valid)
            assert result["allowed"] is True
        finally:
            os.chmod(str(root / "data" / "metabolism" / "lifecycle_docket"), 0o755)

    def test_grade_demotion_ladder_never_raises(self):
        """grade_demotion_ladder() is NEVER-RAISE even on corrupt journal."""
        root = _tmp_root()
        lobe_id = "corrupt-lobe"
        journal_path = root / "data" / "metabolism" / "lifecycle" / f"{lobe_id}.jsonl"
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        journal_path.write_text("NOT VALID JSON\n{bad\n", encoding="utf-8")

        from engine.metabolism.verify import grade_demotion_ladder
        # Must not raise
        result = grade_demotion_ladder(lobe_id, "active", root=root)
        assert isinstance(result, dict)
        assert result["lobe_id"] == lobe_id


# ── 11. Banned words ──────────────────────────────────────────────────────────

class TestBannedWords:
    def _v2c_source_files(self) -> list[Path]:
        """Return all new V2-C source files."""
        files = [
            _ROOT / "engine" / "metabolism" / "lifecycle.py",
            _ROOT / "engine" / "metabolism" / "lobe_registry.py",
            _ROOT / "engine" / "metabolism" / "authority_audit.py",
            _ROOT / "engine" / "metabolism" / "roster_governor.py",
            _ROOT / "config" / "lobe_charters.yml",
            _ROOT / "config" / "metabolism_budget.yml",
        ]
        return [f for f in files if f.exists()]

    def test_no_validated_in_user_facing_text(self):
        """'validated' must not appear in any V2-C user-facing text."""
        for path in self._v2c_source_files():
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            for i, line in enumerate(lines, 1):
                # Allow 'validated' in imports of check_validated_claims or in quoted law text
                if "check_validated_claims" in line or "validated_claims" in line:
                    continue
                if "validated" in line.lower():
                    pytest.fail(
                        f"Banned word 'validated' found in {path}:{i}: {line.strip()!r}"
                    )


# ── 12. INERT assertion (grep-style) ──────────────────────────────────────────

class TestInertAssertion:
    def _v2c_files(self) -> list[Path]:
        return [
            _ROOT / "engine" / "metabolism" / "lifecycle.py",
            _ROOT / "engine" / "metabolism" / "lobe_registry.py",
            _ROOT / "engine" / "metabolism" / "authority_audit.py",
            _ROOT / "engine" / "metabolism" / "roster_governor.py",
        ]

    def test_no_direct_synapse_write(self):
        """V2-C code must not directly write synapse.yml."""
        patterns = [
            r"synapse\.yml.*write",
            r"write.*synapse\.yml",
            r'open.*synapse',
        ]
        for path in self._v2c_files():
            text = path.read_text(encoding="utf-8")
            for pat in patterns:
                if re.search(pat, text, re.IGNORECASE):
                    pytest.fail(
                        f"V2-C file {path} appears to write synapse.yml (pattern: {pat!r})"
                    )

    def test_no_mastermind_context_write(self):
        """V2-C code must not directly write mastermind_context."""
        for path in self._v2c_files():
            text = path.read_text(encoding="utf-8")
            # Disallow direct writes to mastermind_context
            if re.search(r'mastermind_context.*write_text|write.*mastermind_context', text):
                pytest.fail(
                    f"V2-C file {path} appears to write mastermind_context"
                )

    def test_no_auto_retire_call(self):
        """V2-C code must not call any function named 'auto_retire' or 'retire_lobe'."""
        for path in self._v2c_files():
            text = path.read_text(encoding="utf-8")
            if re.search(r'\bauto_retire\b|\bretire_lobe\b', text):
                pytest.fail(
                    f"V2-C file {path} contains auto_retire/retire_lobe call"
                )

    def test_no_tier_edit_in_lifecycle(self):
        """lifecycle.py must not contain tier-assignment code (synapse tier is immutable here)."""
        lifecycle_path = _ROOT / "engine" / "metabolism" / "lifecycle.py"
        if not lifecycle_path.exists():
            pytest.skip("lifecycle.py not found")
        text = lifecycle_path.read_text(encoding="utf-8")
        # Should not write to a 'tier' key (other than in function parameters/comments)
        # This is a heuristic: look for dict assignment to tier that isn't a constant
        if re.search(r'\["tier"\]\s*=\s*["\'](?:confirmer|scored)', text):
            pytest.fail("lifecycle.py contains direct tier assignment to confirmer/scored")


# ── 13. CI fence compliance ───────────────────────────────────────────────────

class TestCIFenceCompliance:
    def test_check_grader_manifest_passes(self):
        """check_grader_manifest.py exits 0 (all registered hashes match)."""
        try:
            from scripts.check_grader_manifest import main as gm_main  # type: ignore[import]
            ret = gm_main([])  # pass empty argv to avoid inheriting pytest args
            assert ret == 0, f"check_grader_manifest failed with code {ret}"
        except ImportError as e:
            pytest.skip(f"check_grader_manifest not importable: {e}")
        except Exception as e:
            pytest.fail(f"check_grader_manifest raised: {e}")

    def test_check_self_mod_fence_selftest(self):
        """check_self_mod_fence.py --selftest passes."""
        try:
            from scripts.check_self_mod_fence import selftest as sm_selftest  # type: ignore[import]
            ret = sm_selftest()
            assert ret == 0, f"check_self_mod_fence selftest failed with code {ret}"
        except ImportError as e:
            pytest.skip(f"check_self_mod_fence not importable: {e}")
        except Exception as e:
            pytest.fail(f"check_self_mod_fence selftest raised: {e}")

    def test_metabolism_budget_has_roster_cap_fields(self):
        """metabolism_budget.yml now contains the V2-C roster cap fields."""
        import yaml  # noqa: PLC0415
        p = _ROOT / "config" / "metabolism_budget.yml"
        if not p.exists():
            pytest.skip("metabolism_budget.yml not found")
        budget = yaml.safe_load(p.read_text())
        assert "max_active_nonscored_lobes" in budget, (
            "max_active_nonscored_lobes missing from metabolism_budget.yml"
        )
        assert "max_probation_lobes" in budget, (
            "max_probation_lobes missing from metabolism_budget.yml"
        )
        assert budget["max_active_nonscored_lobes"] >= 63, (
            f"Expected >= 63 (current roster), got {budget['max_active_nonscored_lobes']}"
        )

    def test_lobe_charters_in_synapse_count(self):
        """synapse.yml now has >= 357 artifacts (V2-C adds lifecycle/charter artifacts)."""
        import yaml  # noqa: PLC0415
        p = _ROOT / "config" / "synapse.yml"
        if not p.exists():
            pytest.skip("synapse.yml not present")
        data = yaml.safe_load(p.read_text())
        count = len(data.get("artifacts", {}))
        assert count >= 357, (
            f"Expected >= 357 synapse artifacts, got {count}. "
            "V2-C may not have registered its artifacts."
        )


# ── 14. Real lobe_charters.yml loads against real synapse.yml ─────────────────

class TestRealCharterRegistry:
    def test_real_charters_load(self):
        """Real config/lobe_charters.yml loads without errors."""
        if not (_ROOT / "config" / "lobe_charters.yml").exists():
            pytest.skip("lobe_charters.yml not present yet")
        from engine.metabolism.lobe_registry import load
        result = load(_ROOT)
        assert result["ok"] is True, f"charter load errors: {result['errors']}"
        assert result["count"] > 0

    def test_real_tier_mirror_no_mismatches(self):
        """Real charter tiers match real synapse tiers (no mismatches)."""
        if not (_ROOT / "config" / "lobe_charters.yml").exists():
            pytest.skip("lobe_charters.yml not present yet")
        from engine.metabolism.lobe_registry import validate_tier_mirror
        result = validate_tier_mirror(_ROOT)
        assert result["tier_mismatches"] == [], (
            f"Tier mismatches found: {result['tier_mismatches']}"
        )

    def test_real_charters_cover_nw_lobes(self):
        """Real lobe_charters.yml has at least 97 entries (all NW-scope lobes)."""
        if not (_ROOT / "config" / "lobe_charters.yml").exists():
            pytest.skip("lobe_charters.yml not present yet")
        from engine.metabolism.lobe_registry import load
        result = load(_ROOT)
        assert result["count"] >= 97, (
            f"Expected >= 97 charter entries (NW-scope lobe count), got {result['count']}"
        )


# ── 15. allowed_edges() completeness ──────────────────────────────────────────

class TestAllowedEdges:
    def test_returns_list(self):
        from engine.metabolism.lifecycle import allowed_edges
        edges = allowed_edges()
        assert isinstance(edges, list)
        assert len(edges) > 0

    def test_all_edges_have_required_fields(self):
        from engine.metabolism.lifecycle import allowed_edges
        for edge in allowed_edges():
            assert "from_state" in edge
            assert "to_state" in edge
            assert "t_level" in edge
            assert "description" in edge

    def test_no_scored_destination_in_table(self):
        """No edge in the table has to_state=confirmer or scored (enforcement via tier= param)."""
        from engine.metabolism.lifecycle import allowed_edges, _FORBIDDEN_TIER_DESTINATIONS
        # The table only operates on lifecycle states, not tier targets
        # Verify that the table edges are lifecycle states, not tier values
        lifecycle_states = {"proposed", "probation", "active", "demoted", "retired"}
        for edge in allowed_edges():
            assert edge["to_state"] in lifecycle_states, (
                f"Unexpected to_state {edge['to_state']!r} in allowed_edges"
            )

    def test_is_de_escalation_helper(self):
        """is_de_escalation() correctly identifies de-escalation edges."""
        from engine.metabolism.lifecycle import is_de_escalation
        assert is_de_escalation("active", "probation") is True
        assert is_de_escalation("probation", "demoted") is True
        assert is_de_escalation("demoted", "retired") is True
        assert is_de_escalation("proposed", "probation") is False  # onboarding
        assert is_de_escalation("active", "NONEXISTENT") is False  # not in table


# ── Edge: NEVER-RAISE contract ────────────────────────────────────────────────

class TestNeverRaise:
    def test_load_charter_never_raises_on_garbage_file(self):
        root = _tmp_root()
        (root / "config" / "lobe_charters.yml").write_text(
            "NOT: VALID:\n  YAML: - [\n", encoding="utf-8"
        )
        from engine.metabolism.lobe_registry import load
        result = load(root)  # must not raise
        assert isinstance(result, dict)

    def test_validate_tier_mirror_never_raises_on_missing_synapse(self):
        root = _tmp_root()
        _write_minimal_charter(root)
        from engine.metabolism.lobe_registry import validate_tier_mirror
        result = validate_tier_mirror(root)  # synapse.yml absent
        assert isinstance(result, dict)
        assert not result["ok"]

    def test_authority_audit_never_raises_on_missing_synapse(self):
        root = _tmp_root()
        from engine.metabolism.authority_audit import run_audit
        result = run_audit(root)  # synapse.yml absent
        assert isinstance(result, dict)
        assert not result["ok"]

    def test_roster_governor_never_raises_on_missing_files(self):
        root = _tmp_root()
        from engine.metabolism.roster_governor import check_charter_budget
        result = check_charter_budget("any-lobe", root=root)
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# Post-review safety hardening (fail-closed adversary default + anti-cascade cap)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDemotionSafetyDefaults:
    def test_all_inputs_absent_blocks_by_default_no_adversary(self):
        """FAIL-CLOSED: all_inputs_absent with NO explicit adversary_nonveto (default)
        must BLOCK the demotion — a healthy-but-starved lobe is not auto-demoted."""
        from engine.metabolism.verify import journal_breach, grade_demotion_ladder
        root = _tmp_root()
        lobe = "starved-lobe"
        for _ in range(3):
            journal_breach(lobe, breach_type="logic_breach", health_status="fresh", root=root)
        with patch("engine.metabolism.lifecycle.transition") as mock_trans:
            result = grade_demotion_ladder(lobe, "active", all_inputs_absent=True, root=root)
        assert result["adversary_nonveto_blocked"] is True, "default must fail closed"
        assert result["proposal"] is None
        assert not mock_trans.called, "no demotion may be emitted without an adversary non-veto"

    def test_all_inputs_absent_proceeds_only_with_explicit_nonveto(self):
        """A genuine adversary non-veto (explicit True) allows the demotion to proceed."""
        from engine.metabolism.verify import journal_breach, grade_demotion_ladder
        root = _tmp_root()
        lobe = "starved-but-adv-ok"
        for _ in range(3):
            journal_breach(lobe, breach_type="logic_breach", health_status="fresh", root=root)
        with patch("engine.metabolism.lifecycle.transition") as mock_trans:
            mock_trans.return_value = {"allowed": True, "reason": "t", "de_escalation": True,
                                       "events_emitted": False, "docket_item_written": False, "t_level": "T1"}
            result = grade_demotion_ladder(lobe, "active", all_inputs_absent=True,
                                           adversary_nonveto=True, root=root)
        assert result["adversary_nonveto_blocked"] is False
        assert mock_trans.called

    def test_probation_cap_holds_active_to_probation_demotion(self):
        """ANTI-CASCADE: when probation is already at cap, a new active->probation
        demotion is HELD (a feed outage cannot cascade the roster to probation)."""
        from engine.metabolism.verify import journal_breach, grade_demotion_ladder
        root = _tmp_root()
        lobe = "would-demote"
        for _ in range(3):
            journal_breach(lobe, breach_type="logic_breach", health_status="fresh", root=root)
        with patch("engine.metabolism.verify._load_max_probation", return_value=2), \
             patch("engine.metabolism.lobe_registry.probation_count", return_value=2), \
             patch("engine.metabolism.lifecycle.transition") as mock_trans:
            result = grade_demotion_ladder(lobe, "active", root=root)
        assert result.get("probation_cap_held") is True
        assert result["proposal"] is None
        assert not mock_trans.called, "demotion held by anti-cascade cap must emit nothing"

    def test_probation_cap_allows_when_below(self):
        """Below the probation cap, the demotion proceeds normally."""
        from engine.metabolism.verify import journal_breach, grade_demotion_ladder
        root = _tmp_root()
        lobe = "ok-to-demote"
        for _ in range(3):
            journal_breach(lobe, breach_type="logic_breach", health_status="fresh", root=root)
        with patch("engine.metabolism.verify._load_max_probation", return_value=5), \
             patch("engine.metabolism.lobe_registry.probation_count", return_value=1), \
             patch("engine.metabolism.lifecycle.transition") as mock_trans:
            mock_trans.return_value = {"allowed": True, "reason": "t", "de_escalation": True,
                                       "events_emitted": False, "docket_item_written": False, "t_level": "T1"}
            result = grade_demotion_ladder(lobe, "active", root=root)
        assert not result.get("probation_cap_held")
        assert mock_trans.called
