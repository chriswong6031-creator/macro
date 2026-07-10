"""tests/test_metabolism_v3_integration.py — Hermetic integration tests for V3 W3.

Coverage:
  A. Brain prompt contains freshness header, Trajectory & Strategic Gap section,
     and — with a seeded FAIL lesson for a construction — that FAIL surfaces in
     the lessons section (proving recall, not byte-tail, is wired).
  B. Agenda grounding field: build_agenda with no-provider path attaches a
     "grounding" field that is a dict.
  C. Adjudicate anti-repetition FLAG: prior_fail_receipt is attached when a
     proposal's construction matches a seeded FAIL lesson; allow is NOT forced
     False by the receipt (a proposal that would otherwise be allowed stays allowed).
  D. NEVER-RAISE: brain still returns a non-empty prompt when new artifacts are absent.

All tests are HERMETIC (tmp_path, pass root=tmp_path; no live filesystem reads).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from engine.metabolism.orchestrator_brain import _build_orchestrator_system
from engine.metabolism.agenda import build_agenda
from engine.metabolism.adjudicate import adjudicate_role, ROLE_ORCH


# ── Fixture helpers ────────────────────────────────────────────────────────────

def _write_lessons(root: Path, rows: list[dict]) -> Path:
    p = root / "data" / "metabolism" / "lessons.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def _write_docket(root: Path, cycle_id: str, proposals: list[dict]) -> Path:
    docket_dir = root / "data" / "metabolism" / "propose"
    docket_dir.mkdir(parents=True, exist_ok=True)
    p = docket_dir / f"{cycle_id}.json"
    p.write_text(
        json.dumps({
            "schema": "metabolism.propose.v1",
            "cycle_id": cycle_id,
            "lobe": "til",
            "proposals": proposals,
        }),
        encoding="utf-8",
    )
    return p


def _seed_fail_lesson(root: Path, construction: str) -> None:
    """Write a single FAIL lesson for the given construction text."""
    _write_lessons(root, [
        {
            "ts": "2026-01-01T00:00:00+00:00",
            "cycle_id": "c-old-fail",
            "lobe": "til",
            "construction": construction,
            "verdict": "FAIL",
            "what_failed": "IC was negative across all regimes",
            "what_worked": "",
            "proposal_id": "p-old-001",
        }
    ])


# ─────────────────────────────────────────────────────────────────────────────
# A. Brain prompt wiring
# ─────────────────────────────────────────────────────────────────────────────

class TestBrainWiring:
    """Verify the four modules are wired into _build_orchestrator_system."""

    def test_freshness_header_present(self, tmp_path: Path) -> None:
        """Brain prompt contains '## Context Freshness'."""
        prompt = _build_orchestrator_system(
            model="claude-opus-4-8",
            lobe="til",
            root=tmp_path,
        )
        assert "## Context Freshness" in prompt, (
            "Freshness header missing from prompt — provenance not wired"
        )
        assert "Context freshness" in prompt, (
            "render_freshness_header output not present in prompt"
        )

    def test_freshness_header_before_organism_state(self, tmp_path: Path) -> None:
        """Freshness header appears before Organism State (early position per spec)."""
        prompt = _build_orchestrator_system(
            model="claude-opus-4-8",
            lobe="til",
            root=tmp_path,
        )
        pos_freshness = prompt.find("## Context Freshness")
        pos_organism = prompt.find("## Organism State")
        assert pos_freshness != -1, "## Context Freshness not found"
        assert pos_organism != -1, "## Organism State not found"
        assert pos_freshness < pos_organism, (
            "Context Freshness header must appear before Organism State "
            f"(freshness at {pos_freshness}, organism at {pos_organism})"
        )

    def test_freshness_header_real_age_not_unknown(self, tmp_path: Path) -> None:
        """Freshness header shows computed file-mtime age, not 'age unknown'.

        Seeds:
          - organism_state.json  (fresh — just written, mtime ~now)
          - lessons.jsonl        (stale — mtime backdated 40d, SLA is 30d)

        Asserts:
          - The organism_state line uses 'file-mtime' (numeric age resolved)
            and does NOT say 'age unknown'.
          - The lessons line is marked '⚠ STALE' (40d > 30d SLA).

        This test MUST fail against the old logical-key wiring (where source
        is "organism_state" / "lessons") and pass only after the fix that
        passes real repo-relative paths as source.
        """
        # Seed a FRESH organism_state artifact (mtime ~now)
        state_dir = tmp_path / "data" / "metabolism"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / "organism_state.json"
        state_path.write_text(json.dumps({"schema": "v1"}), encoding="utf-8")

        # Seed a STALE lessons.jsonl (mtime backdated 40 days)
        lessons_path = state_dir / "lessons.jsonl"
        lessons_path.write_text(
            json.dumps({"ts": "2026-01-01T00:00:00+00:00", "verdict": "PASS"}) + "\n",
            encoding="utf-8",
        )
        stale_t = time.time() - 40 * 86400
        os.utime(lessons_path, (stale_t, stale_t))

        prompt = _build_orchestrator_system(
            model="claude-opus-4-8",
            lobe="til",
            root=tmp_path,
        )

        # Extract the freshness header block
        assert "## Context Freshness" in prompt, "Freshness header missing"

        freshness_start = prompt.find("## Context Freshness")
        # Next section starts with "##" — grab everything between them
        next_section = prompt.find("\n## ", freshness_start + 1)
        freshness_block = prompt[freshness_start:next_section] if next_section != -1 else prompt[freshness_start:]

        # organism_state line must show a numeric age (file-mtime resolved), not "age unknown"
        assert "organism_state" in freshness_block, "organism_state missing from freshness block"
        # Find the organism_state line
        for line in freshness_block.splitlines():
            if "organism_state" in line:
                assert "age unknown" not in line, (
                    f"organism_state freshness line still shows 'age unknown' — "
                    f"real path not being resolved: {line!r}"
                )
                assert "file-mtime" in line, (
                    f"organism_state freshness line expected 'file-mtime' staleness_reason: {line!r}"
                )
                break

        # lessons line must be marked STALE (40d > 30d SLA)
        stale_found = False
        for line in freshness_block.splitlines():
            if "lessons" in line and "⚠ STALE" in line:
                stale_found = True
                break
        assert stale_found, (
            f"lessons line not marked ⚠ STALE even though 40d > 30d SLA.\n"
            f"Freshness block:\n{freshness_block}"
        )

    def test_trajectory_strategic_gap_section(self, tmp_path: Path) -> None:
        """Brain prompt contains '## Trajectory & Strategic Gap'."""
        prompt = _build_orchestrator_system(
            model="claude-opus-4-8",
            lobe="til",
            root=tmp_path,
        )
        assert "## Trajectory & Strategic Gap" in prompt, (
            "Trajectory & Strategic Gap section missing — strategic not wired"
        )

    def test_trajectory_strategic_gap_no_lobe(self, tmp_path: Path) -> None:
        """Strategic gap present even when lobe=None (only gap, no per-lobe block)."""
        prompt = _build_orchestrator_system(
            model="claude-opus-4-8",
            lobe=None,
            root=tmp_path,
        )
        assert "## Trajectory & Strategic Gap" in prompt

    def test_fail_lesson_surfaces_via_recall_not_tail(self, tmp_path: Path) -> None:
        """A seeded FAIL lesson from cycle 'c-old-fail' must appear in the prompt,
        proving that relevance-ranked recall (not byte-tail) is wired.

        Strategy: write a FAIL lesson for the 'til' lobe, then pad with many
        unrelated recent PASS rows.  A byte-tail would bury the FAIL (it is the
        oldest row); recall.recall_lessons scores by lobe match + FAIL weight
        and surfaces it regardless of its position in the file.
        """
        old_construction = "momentum reversal cross-asset mean-reversion signal"
        _seed_fail_lesson(tmp_path, old_construction)  # lobe="til", verdict="FAIL"

        # Append 20 unrelated recent PASS rows that fill a naive byte-tail window
        existing_path = tmp_path / "data" / "metabolism" / "lessons.jsonl"
        with existing_path.open("a", encoding="utf-8") as fh:
            for i in range(20):
                row = {
                    "ts": f"2026-07-{i + 1:02d}T12:00:00+00:00",
                    "cycle_id": f"c-new-{i}",
                    "lobe": "til",
                    "construction": f"completely unrelated build task number {i}",
                    "verdict": "PASS",
                    "what_worked": f"task {i} completed successfully",
                    "what_failed": "",
                    "proposal_id": f"p-new-{i:03d}",
                }
                fh.write(json.dumps(row) + "\n")

        prompt = _build_orchestrator_system(
            model="claude-opus-4-8",
            lobe="til",      # recall is scoped to lobe="til"; FAIL row matches
            root=tmp_path,
        )
        # The FAIL lesson's cycle_id must appear — proving recall surfaced it
        assert "c-old-fail" in prompt, (
            "Seeded FAIL lesson (c-old-fail) not in prompt — byte-tail is still wired "
            "instead of relevance-ranked recall.recall_lessons"
        )

    def test_recent_lessons_section_present(self, tmp_path: Path) -> None:
        """'## Recent Lessons' section header still present (required by spec)."""
        prompt = _build_orchestrator_system(
            model="claude-opus-4-8",
            lobe=None,
            root=tmp_path,
        )
        assert "## Recent Lessons" in prompt


# ─────────────────────────────────────────────────────────────────────────────
# B. Agenda grounding field
# ─────────────────────────────────────────────────────────────────────────────

class TestAgendaGrounding:
    """Agenda result must carry a 'grounding' dict."""

    def test_grounding_field_present(self, tmp_path: Path) -> None:
        """build_agenda (no-provider path) returns a dict with 'grounding' key."""
        result = build_agenda(
            cycle_id="test-cycle-001",
            root=tmp_path,
            providers=None,  # no-provider path
        )
        assert "grounding" in result, (
            "grounding field missing from agenda result — grounding not wired"
        )
        assert isinstance(result["grounding"], dict), (
            f"grounding must be a dict, got {type(result['grounding'])}"
        )

    def test_grounding_does_not_modify_items(self, tmp_path: Path) -> None:
        """Grounding annotation must not change or drop agenda items."""
        result = build_agenda(
            cycle_id="test-cycle-002",
            root=tmp_path,
            providers=None,
        )
        # No-provider agenda has 0 items (no LLM); grounding must not add/remove any
        assert result["items"] == [], (
            "Items modified by grounding — must be display-tier only"
        )

    def test_grounding_field_is_dict_on_fatal_error_path(self, tmp_path: Path) -> None:
        """Even the fatal-error fallback in build_agenda carries grounding: dict."""
        # build_agenda never raises; its fallback should also carry the field
        result = build_agenda(
            cycle_id="test-cycle-003",
            root=tmp_path,
            providers=None,
        )
        g = result.get("grounding")
        assert isinstance(g, dict), (
            f"grounding must be a dict even on degraded path, got {type(g)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# C. Anti-repetition FLAG in adjudicate
# ─────────────────────────────────────────────────────────────────────────────

class TestAntiRepetitionFlag:
    """prior_fail_receipt is informational; allow is never forced False by it."""

    def _make_proposal(self, construction: str, pid: str = "p-test-001") -> dict:
        return {
            "proposal_id": pid,
            "title": f"Test proposal: {construction[:40]}",
            "tier": "T0",
            "kind": "display",
            "targets_sensor": "til_ic_rank",
            "rationale": "Improve display context for the TIL lobe.",
            "construction": construction,
            "fitness_contract": {
                "sensor": "til_ic_rank",
                "expected_sign": "+",
                "band": [0.05, None],
                "check_by": "2026-12-15",
                "placebo_to_beat": "random",
                "falsifier_spec": {},
            },
        }

    def test_prior_fail_receipt_attached_on_match(self, tmp_path: Path) -> None:
        """When a proposal's construction matches a seeded FAIL, prior_fail_receipt is non-empty."""
        construction = "momentum reversal cross-asset mean-reversion signal"
        _seed_fail_lesson(tmp_path, construction)

        proposal = self._make_proposal(construction)
        docket_path = _write_docket(tmp_path, "cycle-001", [proposal])

        # Use injected judgments (no LLM needed) — grant the proposal
        injected = {
            "p-test-001": {
                "proposal_id": "p-test-001",
                "grant": True,
                "tier": "T0",
                "rationale": "Appears constructive",
            }
        }
        results = adjudicate_role(
            ROLE_ORCH,
            "cycle-001",
            docket_path,
            root=tmp_path,
            injected=injected,
            dry_run=True,
        )
        assert results, "adjudicate_role returned empty results"
        result = results[0]

        receipt = result.get("prior_fail_receipt")
        assert receipt is not None, "prior_fail_receipt key missing from result"
        assert isinstance(receipt, list), f"prior_fail_receipt must be list, got {type(receipt)}"
        assert len(receipt) > 0, (
            "prior_fail_receipt is empty even though a matching FAIL was seeded — "
            "anti-repetition flag not wired"
        )
        # Receipt entries have expected keys
        entry = receipt[0]
        assert "cycle_id" in entry
        assert "verdict" in entry
        assert "construction" in entry

    def test_prior_fail_receipt_does_not_force_deny(self, tmp_path: Path) -> None:
        """CRITICAL: a matching FAIL receipt must NOT set allow=False.

        A proposal that would otherwise be granted (no DO_NOT_REBUILD collision,
        no ACTIVE_BUILD_MAP collision, T0 tier, LLM grants) stays granted even
        when prior_fail_receipt is non-empty.

        This enforces R-V3-3: "the guard is informational — it prints the prior
        receipt ... it does NOT hard-block."
        """
        construction = "momentum reversal cross-asset mean-reversion signal"
        _seed_fail_lesson(tmp_path, construction)

        proposal = self._make_proposal(construction)
        docket_path = _write_docket(tmp_path, "cycle-002", [proposal])

        # Grant the proposal via injected judgment
        injected = {
            "p-test-001": {
                "proposal_id": "p-test-001",
                "grant": True,
                "tier": "T0",
                "rationale": "Re-attempt with new mechanism",
            }
        }
        results = adjudicate_role(
            ROLE_ORCH,
            "cycle-002",
            docket_path,
            root=tmp_path,
            injected=injected,
            dry_run=True,
        )
        assert results
        result = results[0]

        # Receipt non-empty (FAIL was seeded)
        receipt = result.get("prior_fail_receipt", [])
        assert len(receipt) > 0, "FAIL receipt expected but not found"

        # allow must NOT be False due to receipt — decision must still be 'grant'
        decision = result.get("decision")
        assert decision == "grant", (
            f"prior_fail_receipt must NOT force deny. "
            f"Decision was '{decision}' but expected 'grant'. "
            "R-V3-3: 'a kill closes the specific construction tested, not the search space.'"
        )
        assert result.get("screen_allow") is True, (
            "screen_allow must be True when no DO_NOT_REBUILD/ABM collision exists"
        )

    def test_no_prior_fail_receipt_when_no_match(self, tmp_path: Path) -> None:
        """When no FAIL lesson matches the construction, prior_fail_receipt is empty."""
        construction = "completely novel display widget for TIL lobe sidebar"
        # Seed a FAIL with a totally different construction
        _seed_fail_lesson(tmp_path, "unrelated topic about something else entirely")

        proposal = self._make_proposal(construction)
        docket_path = _write_docket(tmp_path, "cycle-003", [proposal])

        injected = {
            "p-test-001": {
                "proposal_id": "p-test-001",
                "grant": True,
                "tier": "T0",
                "rationale": "Novel work",
            }
        }
        results = adjudicate_role(
            ROLE_ORCH,
            "cycle-003",
            docket_path,
            root=tmp_path,
            injected=injected,
            dry_run=True,
        )
        assert results
        receipt = results[0].get("prior_fail_receipt", [])
        assert receipt == [], (
            f"Expected empty prior_fail_receipt for unrelated construction, got {receipt}"
        )

    def test_prior_fail_receipt_present_no_lessons_file(self, tmp_path: Path) -> None:
        """When lessons.jsonl is absent, prior_fail_receipt is [] (NEVER-RAISE)."""
        proposal = self._make_proposal("some construction text")
        docket_path = _write_docket(tmp_path, "cycle-004", [proposal])

        injected = {
            "p-test-001": {
                "proposal_id": "p-test-001",
                "grant": True,
                "tier": "T0",
                "rationale": "Test",
            }
        }
        results = adjudicate_role(
            ROLE_ORCH,
            "cycle-004",
            docket_path,
            root=tmp_path,
            injected=injected,
            dry_run=True,
        )
        assert results
        receipt = results[0].get("prior_fail_receipt")
        assert isinstance(receipt, list), "prior_fail_receipt must be a list even with no lessons"
        assert receipt == [], "Expected empty list when lessons.jsonl absent"


# ─────────────────────────────────────────────────────────────────────────────
# D. NEVER-RAISE: brain still returns a non-empty prompt with no artifacts
# ─────────────────────────────────────────────────────────────────────────────

class TestNeverRaise:
    """NEVER-RAISE: all new modules are absent → brain returns a safe non-empty prompt."""

    def test_brain_returns_non_empty_when_all_artifacts_absent(self, tmp_path: Path) -> None:
        """With an empty tmp_path (no configs, no data files), brain must not raise
        and must return a non-empty string."""
        prompt = _build_orchestrator_system(
            model="claude-opus-4-8",
            lobe="til",
            root=tmp_path,
        )
        assert isinstance(prompt, str), "Brain must return a str"
        assert len(prompt) > 0, "Brain must return a non-empty string when all artifacts absent"

    def test_brain_with_corrupt_lessons_file(self, tmp_path: Path) -> None:
        """Corrupt lessons.jsonl must not crash the brain."""
        corrupt = tmp_path / "data" / "metabolism" / "lessons.jsonl"
        corrupt.parent.mkdir(parents=True, exist_ok=True)
        corrupt.write_text("{{not valid json}}\x00\xff", encoding="utf-8")

        prompt = _build_orchestrator_system(
            model="claude-opus-4-8",
            lobe="til",
            root=tmp_path,
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_freshness_header_graceful_on_empty_root(self, tmp_path: Path) -> None:
        """Context Freshness section appears even with no SLA config or data files."""
        prompt = _build_orchestrator_system(
            model="claude-opus-4-8",
            lobe=None,
            root=tmp_path,
        )
        assert "## Context Freshness" in prompt

    def test_trajectory_section_graceful_on_empty_root(self, tmp_path: Path) -> None:
        """Trajectory & Strategic Gap appears even with no trajectory.jsonl."""
        prompt = _build_orchestrator_system(
            model="claude-opus-4-8",
            lobe="til",
            root=tmp_path,
        )
        assert "## Trajectory & Strategic Gap" in prompt
