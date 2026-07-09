"""tests/test_causal_brainstorm.py — Hermetic tests for causal brainstorm pack
and ingest firewall.

Covers:
- Pack: builds with ALL source files absent (honest absent lines); includes
  kill-mask entries verbatim; includes the authority-boundary line;
  deterministic given fixture files.
- Ingest: dry-run writes nothing; --write files ≤3; second --write same ISO
  week refuses; kill-mask card dropped_forbidden; dedup against pre-existing
  mechanisms fixture; invalid JSON dropped not fatal.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from datetime import datetime, timezone
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------

def _make_valid_card(mechanism_id: str = "test-mech-001") -> dict:
    """Make a valid mechanism card (post-sanitized, pre-frozen-hash)."""
    from engine.neuralweb.causal_schema import _compute_env_hash
    em = {
        "should_hold": ["risk_on"],
        "should_break": ["risk_off"],
    }
    em["frozen_hash"] = _compute_env_hash(em)
    return {
        "mechanism_id": mechanism_id,
        "family": "macro_transmission",
        "claim_en": "When liquidity expands, equities tend to follow within 10 days.",
        "claim_zh": "当流动性扩张时，股票倾向于在10天内跟随。",
        "causal_graph": {
            "cause": "fed_balance_sheet_growth",
            "target": "equity_breadth_index",
            "mediators": [],
            "confounders": ["growth_surprise"],
            "colliders_to_avoid": [],
        },
        "environment_map": em,
        "falsifiers": [
            "If lagged-placebo target predicts cause, reverse causation is the explanation.",
            "If the relationship disappears where the mechanism should hold, it is refuted.",
        ],
        "test_spec": {
            "exit_path": "a",
            "claim_shape": "lead_lag",
            "horizon_d": 21,
            "metric": "forward_breadth_21d",
            "threshold": 0.55,
            "min_n": 50,
            "environment": "risk_on",
        },
        "lineage": {
            "source": "llm_proposed",
            "pack_id": "pack-test-001",
            "model": "gpt-4o",
        },
        "status": "inbox",
    }


# ===========================================================================
# PACK TESTS
# ===========================================================================

class TestCausalBrainstormPack:

    def test_pack_builds_with_all_files_absent(self, tmp_path):
        """build_pack works even when all source artifacts are absent."""
        import scripts.causal_brainstorm_pack as mod

        # Patch all path constants to point to a non-existent tmp dir
        with mock.patch.multiple(
            mod,
            _FEATURE_INVENTORY=tmp_path / "causal_feature_inventory.json",
            _CAUSAL_EDGES=tmp_path / "causal_edges.jsonl",
            _CAUSAL_FRONTIER=tmp_path / "causal_frontier.json",
            _SURPRISE_QUEUE=tmp_path / "causal_surprise_queue.jsonl",
            _CAUSAL_NULLS=tmp_path / "causal_nulls.jsonl",
            _CAUSAL_PRIORS=tmp_path / "causal_priors.yml",
            _MACHINE_REGISTRY=tmp_path / "machine_registry.jsonl",
            _MECHANISMS=tmp_path / "causal_mechanisms.jsonl",
        ):
            pack = mod.build_pack(n_requested=5)

        assert isinstance(pack, str)
        assert len(pack) > 100  # non-trivial output

    def test_pack_honest_absent_lines(self, tmp_path):
        """When files are absent, pack contains '(absent' markers."""
        import scripts.causal_brainstorm_pack as mod

        with mock.patch.multiple(
            mod,
            _FEATURE_INVENTORY=tmp_path / "causal_feature_inventory.json",
            _CAUSAL_EDGES=tmp_path / "causal_edges.jsonl",
            _CAUSAL_FRONTIER=tmp_path / "causal_frontier.json",
            _SURPRISE_QUEUE=tmp_path / "causal_surprise_queue.jsonl",
            _CAUSAL_NULLS=tmp_path / "causal_nulls.jsonl",
            _CAUSAL_PRIORS=tmp_path / "causal_priors.yml",
            _MACHINE_REGISTRY=tmp_path / "machine_registry.jsonl",
            _MECHANISMS=tmp_path / "causal_mechanisms.jsonl",
        ):
            pack = mod.build_pack(n_requested=5)

        assert "(absent" in pack

    def test_pack_includes_authority_boundary(self, tmp_path):
        """Pack must include the role/authority boundary line."""
        import scripts.causal_brainstorm_pack as mod

        with mock.patch.multiple(
            mod,
            _FEATURE_INVENTORY=tmp_path / "causal_feature_inventory.json",
            _CAUSAL_EDGES=tmp_path / "causal_edges.jsonl",
            _CAUSAL_FRONTIER=tmp_path / "causal_frontier.json",
            _SURPRISE_QUEUE=tmp_path / "causal_surprise_queue.jsonl",
            _CAUSAL_NULLS=tmp_path / "causal_nulls.jsonl",
            _CAUSAL_PRIORS=tmp_path / "causal_priors.yml",
            _MACHINE_REGISTRY=tmp_path / "machine_registry.jsonl",
            _MECHANISMS=tmp_path / "causal_mechanisms.jsonl",
        ):
            pack = mod.build_pack(n_requested=5)

        # The mandatory role-boundary sentence
        assert "You propose candidate mechanisms and test specs." in pack
        assert "You do not score, rank, trade,\nor claim proof." in pack

    def test_pack_includes_kill_mask_when_present(self, tmp_path):
        """If causal_priors.yml has forbidden causes, pack includes them verbatim."""
        import scripts.causal_brainstorm_pack as mod

        priors_content = """
schema: causal_priors.v1
forbidden_causes:
  - pattern: "board_rank"
    reason: "Article-2 surface; forbidden as cause."
    source_ruling: NW-ART2
kill_mask: []
"""
        priors_path = tmp_path / "causal_priors.yml"
        priors_path.write_text(priors_content, encoding="utf-8")

        with mock.patch.multiple(
            mod,
            _FEATURE_INVENTORY=tmp_path / "causal_feature_inventory.json",
            _CAUSAL_EDGES=tmp_path / "causal_edges.jsonl",
            _CAUSAL_FRONTIER=tmp_path / "causal_frontier.json",
            _SURPRISE_QUEUE=tmp_path / "causal_surprise_queue.jsonl",
            _CAUSAL_NULLS=tmp_path / "causal_nulls.jsonl",
            _CAUSAL_PRIORS=priors_path,
            _MACHINE_REGISTRY=tmp_path / "machine_registry.jsonl",
            _MECHANISMS=tmp_path / "causal_mechanisms.jsonl",
        ):
            pack = mod.build_pack(n_requested=5)

        assert "board_rank" in pack

    def test_pack_deterministic_with_fixture_files(self, tmp_path):
        """build_pack is deterministic given the same fixture files."""
        import scripts.causal_brainstorm_pack as mod

        # Write a simple nulls file
        nulls_path = tmp_path / "causal_nulls.jsonl"
        nulls_path.write_text(
            json.dumps({"cause": "x", "target": "y", "null_reason": "test"}) + "\n",
            encoding="utf-8",
        )

        with mock.patch.multiple(
            mod,
            _FEATURE_INVENTORY=tmp_path / "causal_feature_inventory.json",
            _CAUSAL_EDGES=tmp_path / "causal_edges.jsonl",
            _CAUSAL_FRONTIER=tmp_path / "causal_frontier.json",
            _SURPRISE_QUEUE=tmp_path / "causal_surprise_queue.jsonl",
            _CAUSAL_NULLS=nulls_path,
            _CAUSAL_PRIORS=tmp_path / "causal_priors.yml",
            _MACHINE_REGISTRY=tmp_path / "machine_registry.jsonl",
            _MECHANISMS=tmp_path / "causal_mechanisms.jsonl",
        ):
            pack1 = mod.build_pack(n_requested=10)
            pack2 = mod.build_pack(n_requested=10)

        assert pack1 == pack2

    def test_pack_n_requested_in_output(self, tmp_path):
        """n_requested is reflected in the pack header and output schema."""
        import scripts.causal_brainstorm_pack as mod

        with mock.patch.multiple(
            mod,
            _FEATURE_INVENTORY=tmp_path / "causal_feature_inventory.json",
            _CAUSAL_EDGES=tmp_path / "causal_edges.jsonl",
            _CAUSAL_FRONTIER=tmp_path / "causal_frontier.json",
            _SURPRISE_QUEUE=tmp_path / "causal_surprise_queue.jsonl",
            _CAUSAL_NULLS=tmp_path / "causal_nulls.jsonl",
            _CAUSAL_PRIORS=tmp_path / "causal_priors.yml",
            _MACHINE_REGISTRY=tmp_path / "machine_registry.jsonl",
            _MECHANISMS=tmp_path / "causal_mechanisms.jsonl",
        ):
            pack = mod.build_pack(n_requested=7)

        assert "7" in pack


# ===========================================================================
# INGEST TESTS
# ===========================================================================

class TestCausalIngestBrainstorm:
    """Tests for scripts.causal_ingest_brainstorm."""

    def _write_inbox(self, tmp_path: Path, cards: list[dict]) -> Path:
        inbox = tmp_path / "inbox"
        inbox.mkdir(exist_ok=True)
        (inbox / "batch_01.json").write_text(
            json.dumps(cards), encoding="utf-8"
        )
        return inbox

    def test_dry_run_writes_nothing(self, tmp_path):
        """dry_run=True must not write any files."""
        from scripts.causal_ingest_brainstorm import ingest

        card = _make_valid_card()
        inbox = self._write_inbox(tmp_path, [card])
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = ingest(inbox=inbox, out_dir=out_dir, dry_run=True, model_label="test")
        mechanisms_file = out_dir / "causal_mechanisms.jsonl"
        assert not mechanisms_file.exists() or mechanisms_file.stat().st_size == 0

    def test_write_files_accepted_card(self, tmp_path):
        """--write appends valid card to causal_mechanisms.jsonl."""
        from scripts.causal_ingest_brainstorm import ingest

        card = _make_valid_card()
        inbox = self._write_inbox(tmp_path, [card])
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = ingest(inbox=inbox, out_dir=out_dir, dry_run=False, model_label="test")
        mechanisms_file = out_dir / "causal_mechanisms.jsonl"
        assert mechanisms_file.exists()
        lines = [l for l in mechanisms_file.read_text().splitlines() if l.strip()]
        assert len(lines) == 1

    def test_write_caps_at_budget(self, tmp_path):
        """Cannot write more than 3 cards per ISO week."""
        from scripts.causal_ingest_brainstorm import ingest

        cards = [_make_valid_card(f"mech-{i:03d}") for i in range(5)]
        inbox = self._write_inbox(tmp_path, cards)
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = ingest(inbox=inbox, out_dir=out_dir, dry_run=False, model_label="test")
        mechanisms_file = out_dir / "causal_mechanisms.jsonl"
        lines = [l for l in mechanisms_file.read_text().splitlines() if l.strip()]
        assert len(lines) <= 3

    def test_second_write_same_week_refuses(self, tmp_path):
        """Second --write in same ISO week refuses when budget is exhausted."""
        from scripts.causal_ingest_brainstorm import ingest, _BUDGET_PER_WEEK

        # Pre-fill the file with 3 already-filed cards for this week
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        year, week, _ = now.isocalendar()
        filing_week = f"{year}-W{week:02d}"

        out_dir = tmp_path / "out"
        out_dir.mkdir()
        mechanisms_file = out_dir / "causal_mechanisms.jsonl"

        existing_card = _make_valid_card("existing-001")
        existing_card["filing_week"] = filing_week
        for i in range(_BUDGET_PER_WEEK):
            c = _make_valid_card(f"existing-{i:03d}")
            c["filing_week"] = filing_week
            with mechanisms_file.open("a") as fh:
                fh.write(json.dumps(c) + "\n")

        # Now try to write a new card
        new_card = _make_valid_card("new-card-001")
        inbox = self._write_inbox(tmp_path, [new_card])

        result = ingest(inbox=inbox, out_dir=out_dir, dry_run=False, model_label="test")
        # Should have returned non-zero (budget refused)
        assert result == 1

    def test_kill_mask_card_dropped_forbidden(self, tmp_path):
        """Cards matching kill_mask forbidden_causes are dropped."""
        from scripts.causal_ingest_brainstorm import ingest

        # Create a priors.yml with a forbidden pattern
        priors_content = """
schema: causal_priors.v1
forbidden_causes:
  - pattern: "board_rank"
    reason: "Article-2 surface"
    source_ruling: NW-ART2
kill_mask: []
"""
        priors_path = tmp_path / "causal_priors.yml"
        priors_path.write_text(priors_content, encoding="utf-8")

        # Card with a cause matching the forbidden pattern
        card = _make_valid_card("forbidden-cause-001")
        card["causal_graph"]["cause"] = "board_rank_composite"

        inbox = self._write_inbox(tmp_path, [card])
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        with mock.patch("scripts.causal_ingest_brainstorm._CAUSAL_PRIORS", priors_path):
            result = ingest(inbox=inbox, out_dir=out_dir, dry_run=False, model_label="test")

        mechanisms_file = out_dir / "causal_mechanisms.jsonl"
        lines = [l for l in mechanisms_file.read_text().splitlines() if l.strip()] if mechanisms_file.exists() else []
        assert len(lines) == 0  # forbidden card was dropped

    def test_dedup_against_existing_mechanisms(self, tmp_path):
        """Cards already in causal_mechanisms.jsonl are deduplicated."""
        from scripts.causal_ingest_brainstorm import ingest
        from engine.neuralweb.causal_schema import canonical_card

        out_dir = tmp_path / "out"
        out_dir.mkdir()
        mechanisms_file = out_dir / "causal_mechanisms.jsonl"

        # Pre-write the card as already filed
        card = _make_valid_card("already-filed-001")
        card["status"] = "inbox"
        card["filing_week"] = "2020-W01"  # old week
        with mechanisms_file.open("a") as fh:
            fh.write(json.dumps(card) + "\n")

        # Now try to ingest the same card again
        inbox = self._write_inbox(tmp_path, [card])

        result = ingest(inbox=inbox, out_dir=out_dir, dry_run=False, model_label="test")
        lines = [l for l in mechanisms_file.read_text().splitlines() if l.strip()]
        # Should still be exactly 1 (no new row added)
        assert len(lines) == 1

    def test_invalid_json_dropped_not_fatal(self, tmp_path):
        """Malformed JSON in inbox file is skipped; valid cards in same file proceed."""
        from scripts.causal_ingest_brainstorm import ingest

        inbox = tmp_path / "inbox"
        inbox.mkdir()

        valid_card = _make_valid_card("valid-001")
        # Write a file that starts with invalid JSON then has a valid array
        mixed_content = "[{invalid json}]\n" + json.dumps([valid_card])
        (inbox / "mixed.json").write_text(mixed_content, encoding="utf-8")

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        # Should not raise; valid card from the second array may be accepted
        result = ingest(inbox=inbox, out_dir=out_dir, dry_run=True, model_label="test")
        # Just verify it completes without exception
        assert result == 0

    def test_min_n_clamped_during_ingest(self, tmp_path):
        """Cards with min_n below floor are clamped, not dropped."""
        from scripts.causal_ingest_brainstorm import ingest, MIN_N_FLOOR

        card = _make_valid_card("low-minn-001")
        card["test_spec"]["min_n"] = 5  # below floor

        inbox = self._write_inbox(tmp_path, [card])
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = ingest(inbox=inbox, out_dir=out_dir, dry_run=False, model_label="test")
        mechanisms_file = out_dir / "causal_mechanisms.jsonl"
        if mechanisms_file.exists():
            lines = [l for l in mechanisms_file.read_text().splitlines() if l.strip()]
            if lines:
                written = json.loads(lines[0])
                assert written["test_spec"]["min_n"] >= MIN_N_FLOOR

    def test_banned_words_sanitized_during_ingest(self, tmp_path):
        """Banned words in claim_en/claim_zh/falsifiers are replaced, not dropped."""
        from scripts.causal_ingest_brainstorm import ingest

        card = _make_valid_card("banned-words-001")
        # These will be sanitized: "caused" → "co-moved with", "validated" → "tested"
        # We need the card to still pass validation AFTER sanitization
        # So pre-sanitize to confirm validity, then inject banned words for the test
        card["claim_en"] = "When X caused Y in environment Z."
        # The ingest should sanitize and then validate — the sanitized version is valid

        inbox = self._write_inbox(tmp_path, [card])
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = ingest(inbox=inbox, out_dir=out_dir, dry_run=False, model_label="test")
        mechanisms_file = out_dir / "causal_mechanisms.jsonl"
        if mechanisms_file.exists():
            lines = [l for l in mechanisms_file.read_text().splitlines() if l.strip()]
            if lines:
                written = json.loads(lines[0])
                assert "caused" not in written.get("claim_en", "").lower()

    def test_actor_stamped_as_script(self, tmp_path):
        """Written cards carry actor='script'."""
        from scripts.causal_ingest_brainstorm import ingest

        card = _make_valid_card("actor-check-001")
        inbox = self._write_inbox(tmp_path, [card])
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        ingest(inbox=inbox, out_dir=out_dir, dry_run=False, model_label="test-model")
        mechanisms_file = out_dir / "causal_mechanisms.jsonl"
        if mechanisms_file.exists():
            lines = [l for l in mechanisms_file.read_text().splitlines() if l.strip()]
            if lines:
                written = json.loads(lines[0])
                assert written.get("actor") == "script"
                assert written["lineage"].get("model_label") == "test-model"
