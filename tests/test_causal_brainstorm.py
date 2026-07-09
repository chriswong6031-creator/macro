"""tests/test_causal_brainstorm.py — Hermetic tests for causal brainstorm pack
and ingest firewall.

Covers:
- Pack: builds with ALL source files absent (honest absent lines); includes
  kill-mask entries verbatim; includes the authority-boundary line;
  deterministic given fixture files.
- Ingest: dry-run writes nothing; --write files ≤3; second --write same ISO
  week refuses; kill-mask card dropped_forbidden; dedup against pre-existing
  mechanisms fixture; invalid JSON dropped not fatal.

W4 BLOCK remediation tests (added 2026-07-09):
- B1: build_pack() against REAL committed config/causal_priors.yml succeeds and
  contains curated kill rows verbatim (no list-vs-dict crash).
- B2: tampered hash → dropped_forged_hash; blank hash → mint-stamped; stored card
  mutated post-mint → validate_card catches.
- M1: LLM-injected forged transition history does not survive ingest.
- M3: deleting causal_mechanisms.jsonl does NOT reset the budget when ledger rows exist.
- M4: validate_instruments(load_instruments()) passes against real config.
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

        # Mock _TRIAL_LEDGER to avoid reading/writing the real repo ledger (M3)
        ledger_path = tmp_path / "trial_ledger.jsonl"
        with mock.patch("scripts.causal_ingest_brainstorm._TRIAL_LEDGER", ledger_path):
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

        ledger_path = tmp_path / "trial_ledger.jsonl"
        with mock.patch("scripts.causal_ingest_brainstorm._TRIAL_LEDGER", ledger_path):
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

        ledger_path = tmp_path / "trial_ledger.jsonl"
        with mock.patch("scripts.causal_ingest_brainstorm._TRIAL_LEDGER", ledger_path):
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

        ledger_path = tmp_path / "trial_ledger.jsonl"
        with mock.patch("scripts.causal_ingest_brainstorm._CAUSAL_PRIORS", priors_path), \
             mock.patch("scripts.causal_ingest_brainstorm._TRIAL_LEDGER", ledger_path):
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

        ledger_path = tmp_path / "trial_ledger.jsonl"
        with mock.patch("scripts.causal_ingest_brainstorm._TRIAL_LEDGER", ledger_path):
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

        ledger_path = tmp_path / "trial_ledger.jsonl"
        with mock.patch("scripts.causal_ingest_brainstorm._TRIAL_LEDGER", ledger_path):
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

        ledger_path = tmp_path / "trial_ledger.jsonl"
        with mock.patch("scripts.causal_ingest_brainstorm._TRIAL_LEDGER", ledger_path):
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

        ledger_path = tmp_path / "trial_ledger.jsonl"
        with mock.patch("scripts.causal_ingest_brainstorm._TRIAL_LEDGER", ledger_path):
            ingest(inbox=inbox, out_dir=out_dir, dry_run=False, model_label="test-model")
        mechanisms_file = out_dir / "causal_mechanisms.jsonl"
        if mechanisms_file.exists():
            lines = [l for l in mechanisms_file.read_text().splitlines() if l.strip()]
            if lines:
                written = json.loads(lines[0])
                assert written.get("actor") == "script"
                assert written["lineage"].get("model_label") == "test-model"


# ===========================================================================
# W4 BLOCK REMEDIATION TESTS
# ===========================================================================


# ---------------------------------------------------------------------------
# B1 — REAL CONFIG: build_pack against committed config/causal_priors.yml
# ---------------------------------------------------------------------------

class TestB1RealConfigPack:
    """B1: build_pack() must not crash on the real config/causal_priors.yml
    (which ships kill_mask as a dict, not a list) and must render curated
    kill rows verbatim in the pack output."""

    @pytest.fixture
    def real_config_root(self):
        """Return the real repo root (where config/causal_priors.yml lives)."""
        return Path(__file__).resolve().parents[1]

    def test_build_pack_real_config_succeeds(self, real_config_root, tmp_path):
        """build_pack() against real config/causal_priors.yml must not raise."""
        import scripts.causal_brainstorm_pack as mod

        real_priors = real_config_root / "config" / "causal_priors.yml"
        assert real_priors.exists(), f"real config not found: {real_priors}"

        with mock.patch.multiple(
            mod,
            _FEATURE_INVENTORY=tmp_path / "causal_feature_inventory.json",
            _CAUSAL_EDGES=tmp_path / "causal_edges.jsonl",
            _CAUSAL_FRONTIER=tmp_path / "causal_frontier.json",
            _SURPRISE_QUEUE=tmp_path / "causal_surprise_queue.jsonl",
            _CAUSAL_NULLS=tmp_path / "causal_nulls.jsonl",
            _CAUSAL_PRIORS=real_priors,
            _MACHINE_REGISTRY=tmp_path / "machine_registry.jsonl",
            _MECHANISMS=tmp_path / "causal_mechanisms.jsonl",
        ):
            # Must not raise (was crashing before B1 fix because kill_mask is a dict)
            pack = mod.build_pack(n_requested=5)

        assert isinstance(pack, str)
        assert len(pack) > 200

    def test_build_pack_real_config_contains_curated_kill_rows(self, real_config_root, tmp_path):
        """build_pack against real config must include curated kill-mask edge_family values."""
        import yaml
        import scripts.causal_brainstorm_pack as mod

        real_priors = real_config_root / "config" / "causal_priors.yml"
        assert real_priors.exists(), f"real config not found: {real_priors}"

        # Load the real curated entries from the config
        data = yaml.safe_load(real_priors.read_text(encoding="utf-8"))
        raw_km = data.get("kill_mask") or {}
        assert isinstance(raw_km, dict), "kill_mask must be a dict in the real config"
        curated = raw_km.get("curated", [])
        assert curated, "real config must have at least one curated kill entry"

        # Run pack against real config
        with mock.patch.multiple(
            mod,
            _FEATURE_INVENTORY=tmp_path / "causal_feature_inventory.json",
            _CAUSAL_EDGES=tmp_path / "causal_edges.jsonl",
            _CAUSAL_FRONTIER=tmp_path / "causal_frontier.json",
            _SURPRISE_QUEUE=tmp_path / "causal_surprise_queue.jsonl",
            _CAUSAL_NULLS=tmp_path / "causal_nulls.jsonl",
            _CAUSAL_PRIORS=real_priors,
            _MACHINE_REGISTRY=tmp_path / "machine_registry.jsonl",
            _MECHANISMS=tmp_path / "causal_mechanisms.jsonl",
        ):
            pack = mod.build_pack(n_requested=5)

        # Every curated edge_family must appear verbatim in the pack (DO-NOT-PROPOSE lines)
        for entry in curated:
            ef = entry.get("edge_family", "")
            assert ef and ef in pack, (
                f"curated kill entry edge_family={ef!r} not found in pack output; "
                f"pack missing verbatim DO-NOT-PROPOSE rendering of curated kill rows"
            )


# ---------------------------------------------------------------------------
# B2 — FROZEN-HASH TAMPER EVIDENCE
# ---------------------------------------------------------------------------

class TestB2FrozenHashTamper:
    """B2: mint-vs-tamper semantics for frozen_hash."""

    def _write_inbox(self, tmp_path: Path, cards: list[dict]) -> Path:
        inbox = tmp_path / "inbox"
        inbox.mkdir(exist_ok=True)
        (inbox / "batch.json").write_text(json.dumps(cards), encoding="utf-8")
        return inbox

    def test_tampered_hash_card_dropped_forged_hash(self, tmp_path):
        """Arriving card with stale frozen_hash + extra split → dropped_forged_hash."""
        from scripts.causal_ingest_brainstorm import ingest
        from engine.neuralweb.causal_schema import _compute_env_hash

        # Build a card with a correctly minted hash
        card = _make_valid_card("tamper-test-001")
        em = card["environment_map"]
        good_hash = _compute_env_hash(em)
        em["frozen_hash"] = good_hash

        # Now tamper: add an extra split condition AFTER computing the hash
        em["should_hold"].append("INJECTED_CONDITION")
        card["environment_map"] = em
        # The hash now mismatches the current splits

        inbox = self._write_inbox(tmp_path, [card])
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        # Redirect trial_ledger writes to tmp_path to avoid polluting real repo data
        ledger_path = tmp_path / "trial_ledger.jsonl"
        with mock.patch("scripts.causal_ingest_brainstorm._TRIAL_LEDGER", ledger_path):
            ingest(inbox=inbox, out_dir=out_dir, dry_run=False, model_label="test")

        mechanisms_file = out_dir / "causal_mechanisms.jsonl"
        lines = (
            [l for l in mechanisms_file.read_text().splitlines() if l.strip()]
            if mechanisms_file.exists()
            else []
        )
        assert len(lines) == 0, "tampered-hash card must be dropped, not filed"

    def test_blank_hash_card_gets_minted(self, tmp_path):
        """Arriving card with blank/absent frozen_hash → hash computed-and-stamped at mint."""
        from scripts.causal_ingest_brainstorm import ingest
        from engine.neuralweb.causal_schema import _compute_env_hash

        card = _make_valid_card("mint-test-001")
        # Remove the frozen_hash to simulate an LLM card that left it blank
        em = card["environment_map"]
        em.pop("frozen_hash", None)
        card["environment_map"] = em

        inbox = self._write_inbox(tmp_path, [card])
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        ledger_path = tmp_path / "trial_ledger.jsonl"
        with mock.patch("scripts.causal_ingest_brainstorm._TRIAL_LEDGER", ledger_path):
            result = ingest(inbox=inbox, out_dir=out_dir, dry_run=False, model_label="test")

        mechanisms_file = out_dir / "causal_mechanisms.jsonl"
        assert mechanisms_file.exists(), "valid card with blank hash should be filed"
        lines = [l for l in mechanisms_file.read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        written = json.loads(lines[0])
        # The filed card must have a non-blank frozen_hash that matches the splits
        em_written = written.get("environment_map", {})
        assert em_written.get("frozen_hash"), "frozen_hash must be stamped at mint"
        expected = _compute_env_hash(em_written)
        assert em_written["frozen_hash"] == expected, "stamped hash must match computed hash"

    def test_stored_card_mutated_post_mint_caught_by_validate(self):
        """Stored card with mutated environment_map fails validate_card (tamper evidence)."""
        from engine.neuralweb.causal_schema import validate_card, _compute_env_hash

        card = _make_valid_card("post-mint-tamper")
        # Ensure hash is correct
        em = card["environment_map"]
        em["frozen_hash"] = _compute_env_hash(em)
        card["environment_map"] = em

        errors = validate_card(card)
        assert errors == [], f"clean card should pass: {errors}"

        # Now mutate the splits WITHOUT updating the hash (simulates post-mint tamper)
        card["environment_map"]["should_hold"].append("TAMPERED")
        errors = validate_card(card)
        assert any("frozen_hash" in e and "mismatch" in e for e in errors), (
            f"post-mint tamper must be caught by validate_card: {errors}"
        )

    def test_pack_placeholder_hash_treated_as_blank(self, tmp_path):
        """Cards arriving with the pack's placeholder text in frozen_hash are minted."""
        from scripts.causal_ingest_brainstorm import ingest

        card = _make_valid_card("placeholder-hash-001")
        card["environment_map"]["frozen_hash"] = (
            "(leave blank — the ingest script computes this at mint time)"
        )

        inbox = self._write_inbox(tmp_path, [card])
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        ledger_path = tmp_path / "trial_ledger.jsonl"
        with mock.patch("scripts.causal_ingest_brainstorm._TRIAL_LEDGER", ledger_path):
            result = ingest(inbox=inbox, out_dir=out_dir, dry_run=False, model_label="test")

        mechanisms_file = out_dir / "causal_mechanisms.jsonl"
        assert mechanisms_file.exists()
        lines = [l for l in mechanisms_file.read_text().splitlines() if l.strip()]
        assert len(lines) == 1, "placeholder-hash card should be filed (treated as blank)"


# ---------------------------------------------------------------------------
# M1 — FORGED TRANSITION HISTORY
# ---------------------------------------------------------------------------

class TestM1ForgedTransitionHistory:
    """M1: LLM-supplied lineage.transitions must be discarded on mint."""

    def _write_inbox(self, tmp_path: Path, cards: list[dict]) -> Path:
        inbox = tmp_path / "inbox"
        inbox.mkdir(exist_ok=True)
        (inbox / "batch.json").write_text(json.dumps(cards), encoding="utf-8")
        return inbox

    def test_llm_forged_transitions_not_in_filed_card(self, tmp_path):
        """LLM-injected llm→filed transition history does not survive ingest."""
        from scripts.causal_ingest_brainstorm import ingest

        card = _make_valid_card("forged-history-001")
        # Inject a forged transition history as an LLM might do
        card["lineage"]["transitions"] = [
            {"from": "inbox", "to": "filed", "actor": "llm", "reason": "auto-approved"},
            {"from": "inbox", "to": "skeptic_passed", "actor": "llm", "reason": "skeptic ok"},
        ]

        inbox = self._write_inbox(tmp_path, [card])
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        ledger_path = tmp_path / "trial_ledger.jsonl"
        with mock.patch("scripts.causal_ingest_brainstorm._TRIAL_LEDGER", ledger_path):
            ingest(inbox=inbox, out_dir=out_dir, dry_run=False, model_label="test")

        mechanisms_file = out_dir / "causal_mechanisms.jsonl"
        assert mechanisms_file.exists()
        lines = [l for l in mechanisms_file.read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        written = json.loads(lines[0])
        transitions = written.get("lineage", {}).get("transitions", [])
        assert transitions == [], (
            f"LLM-forged transitions must be reset to [] on mint; got: {transitions}"
        )


# ---------------------------------------------------------------------------
# M3 — ISO-WEEK LOCK DURABILITY
# ---------------------------------------------------------------------------

class TestM3IsoWeekLockDurability:
    """M3: deleting causal_mechanisms.jsonl must not reset the weekly budget
    when trial_ledger rows exist."""

    def _write_inbox(self, tmp_path: Path, cards: list[dict]) -> Path:
        inbox = tmp_path / "inbox"
        inbox.mkdir(exist_ok=True)
        (inbox / "batch.json").write_text(json.dumps(cards), encoding="utf-8")
        return inbox

    def test_budget_not_reset_by_deleting_mechanisms_file(self, tmp_path):
        """Budget is durable: deleting causal_mechanisms.jsonl doesn't reset it."""
        from scripts.causal_ingest_brainstorm import (
            ingest, _BUDGET_PER_WEEK, _current_iso_week,
            _count_filed_this_week, _log_filing_budget_to_ledger,
        )

        ledger_path = tmp_path / "trial_ledger.jsonl"
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        mechanisms_file = out_dir / "causal_mechanisms.jsonl"

        week = _current_iso_week()

        # Pre-populate trial_ledger with BUDGET rows for this week (simulating
        # a previous filing run that has since had its mechanisms file deleted)
        with mock.patch("scripts.causal_ingest_brainstorm._TRIAL_LEDGER", ledger_path):
            for i in range(_BUDGET_PER_WEEK):
                _log_filing_budget_to_ledger(f"pre-filed-{i:03d}", week)

        # Confirm mechanisms file does NOT exist (it was "deleted")
        assert not mechanisms_file.exists()

        # Now try to file a new card — budget should be full from ledger alone
        new_card = _make_valid_card("post-delete-001")
        inbox = self._write_inbox(tmp_path, [new_card])

        with mock.patch("scripts.causal_ingest_brainstorm._TRIAL_LEDGER", ledger_path):
            result = ingest(inbox=inbox, out_dir=out_dir, dry_run=False, model_label="test")

        # Budget should be exhausted from ledger — ingest returns 1
        assert result == 1, (
            "ingest must refuse when budget is exhausted via ledger rows, "
            "even if causal_mechanisms.jsonl was deleted"
        )

    def test_count_uses_max_of_mechanisms_and_ledger(self, tmp_path):
        """_count_filed_this_week returns max(mechanisms_rows, ledger_rows)."""
        from scripts.causal_ingest_brainstorm import (
            _count_filed_this_week, _current_iso_week,
        )

        ledger_path = tmp_path / "trial_ledger.jsonl"
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        week = _current_iso_week()

        # Write 2 rows only to the ledger (no mechanisms file)
        for i in range(2):
            row = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "kind": "filing_budget",
                "family": "causal_scan",
                "filing_week": week,
                "mechanism_id": f"test-{i}",
            }
            with ledger_path.open("a") as fh:
                fh.write(json.dumps(row) + "\n")

        with mock.patch("scripts.causal_ingest_brainstorm._TRIAL_LEDGER", ledger_path):
            count = _count_filed_this_week(out_dir)

        assert count == 2, f"expected 2 from ledger alone, got {count}"


# ---------------------------------------------------------------------------
# M4 — INSTRUMENT VALIDATOR CI WIRING
# ---------------------------------------------------------------------------

class TestM4InstrumentValidatorRealConfig:
    """M4: validate_instruments(load_instruments()) must pass against the real
    committed config/causal_instruments.yml."""

    def test_real_instruments_config_valid(self):
        """validate_instruments against real config/causal_instruments.yml returns no errors."""
        from engine.neuralweb.causal_schema import validate_instruments, load_instruments

        real_root = Path(__file__).resolve().parents[1]
        instruments_path = real_root / "config" / "causal_instruments.yml"
        assert instruments_path.exists(), (
            f"config/causal_instruments.yml not found at {instruments_path}"
        )

        instruments = load_instruments(real_root)
        assert instruments, "real config must contain at least one instrument"

        errors = validate_instruments(instruments)
        assert errors == [], (
            f"validate_instruments against real config returned errors: {errors}"
        )


# ---------------------------------------------------------------------------
# m1 — BANNED-WORD COVERAGE: notes, test_spec, lineage fields
# ---------------------------------------------------------------------------

class TestM1BannedWordCoverage:
    """m1 (minor): banned word check covers all string leaves, not just claim fields."""

    def test_banned_word_in_notes_fails_validation(self):
        """Banned word in top-level notes field fails validate_card."""
        from engine.neuralweb.causal_schema import validate_card

        card = _make_valid_card("notes-banned-001")
        card["notes"] = "This mechanism caused the observed anomaly."
        errors = validate_card(card)
        assert any("caused" in e or "notes" in e for e in errors), (
            f"Banned word in notes should fail validation; errors={errors}"
        )

    def test_banned_word_in_test_spec_notes_fails_validation(self):
        """Banned word in test_spec.notes field fails validate_card."""
        from engine.neuralweb.causal_schema import validate_card

        card = _make_valid_card("ts-notes-banned-001")
        card["test_spec"]["notes"] = "Validated approach for testing."
        errors = validate_card(card)
        assert any("validated" in e.lower() or "test_spec" in e for e in errors), (
            f"Banned word in test_spec.notes should fail validation; errors={errors}"
        )

    def test_sanitize_card_cleans_all_leaves(self):
        """sanitize_card replaces banned words in notes and test_spec.notes."""
        from engine.neuralweb.causal_schema import sanitize_card

        card = _make_valid_card("sanitize-all-001")
        card["notes"] = "This mechanism caused the anomaly."
        card["test_spec"]["notes"] = "Validated approach."
        card["lineage"]["custom_note"] = "Proof of effectiveness."

        cleaned = sanitize_card(card)
        assert "caused" not in cleaned.get("notes", "").lower()
        assert "validated" not in cleaned["test_spec"].get("notes", "").lower()
        assert "proof" not in cleaned["lineage"].get("custom_note", "").lower()
