"""Tests for engine/cycle_pattern/consumer_authority.py — CPI-H1 heal.

Covers the five Sol-mandated discriminating tests for the CPI-H1
consumer-authority heal (research/imce/IMCE_D1C_RELEASE_RECORD.md), plus
supporting coverage for the canonical matrix and the CI-wired registry scan
extension in scripts/check_cycle_pattern_authority.py.

Each discriminating test below is required to actually FAIL on the stated
bad input and PASS on the healed equivalent — not merely exist.

  1. An orphan token (not in the canonical matrix) must FAIL validation.
  2. A promoted_null row granting neuralweb_context must FAIL.
  3. A row missing any universal money-path forbid must FAIL.
  4. A writer attempting hazard_baseline_override must FAIL.
  5. Every existing legal (latest-version) row must PASS after its
     versioned heal — run the validator over the full healed registry.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine.cycle_pattern.consumer_authority import (  # noqa: E402
    ConsumerAuthorityError,
    UNIVERSAL_MONEY_PATH_FORBIDS,
    canonical_tokens,
    retired_aliases,
    validate_consumer_vocabulary,
    validate_registry,
)
from engine.cycle_pattern.truths import (  # noqa: E402
    TRUTHS_PATH,
    append_truth,
    load_truths,
    validate_truth,
)


def _base_row(**overrides) -> dict:
    """A minimal, otherwise-canonical truth row for isolated vocabulary tests."""
    row = {
        "truth_id": "TEST-CPI-H1-001",
        "version": 1,
        "status": "candidate",
        "owner_program": "cycle-intelligence",
        "statement": "Synthetic test row for CPI-H1 consumer-authority tests.",
        "effect_class": "null",
        "scope": {"families": ["us_sector"], "regions": ["US"], "sample": "synthetic"},
        "target": "synthetic_target",
        "evidence_refs": [],
        "n_summary": "n=1 synthetic",
        "ci_summary": "synthetic",
        "era_stability": "unknown",
        "pit_class": "pit_pure",
        "allowed_consumers": ["measurement_page", "research_factory"],
        "forbidden_consumers": [
            "board_rank",
            "oracle_escalation",
            "sector_central_direction_score",
            "position_sizing",
        ],
        "falsifiers": ["synthetic falsifier"],
        "monitoring": {"metric": None, "cadence": "annual", "auto_demote_rule": None},
        "created": "2026-08-21",
        "last_reviewed": "2026-08-21",
        "next_review_due": "2027-08-21",
        "notes": "synthetic",
    }
    row.update(overrides)
    return row


# ─────────────────────────────────────────────────────────────────────────────
# Discriminating test 1: orphan token must FAIL
# ─────────────────────────────────────────────────────────────────────────────

class TestOrphanTokenFails:
    def test_orphan_allowed_token_fails(self):
        row = _base_row(allowed_consumers=["not_a_real_surface_xyz", "research_factory"])
        with pytest.raises(ConsumerAuthorityError, match="orphan token"):
            validate_consumer_vocabulary(row)

    def test_orphan_forbidden_token_fails(self):
        row = _base_row(
            forbidden_consumers=[
                "board_rank", "oracle_escalation",
                "sector_central_direction_score", "position_sizing",
                "not_a_real_surface_xyz",
            ]
        )
        with pytest.raises(ConsumerAuthorityError, match="orphan token"):
            validate_consumer_vocabulary(row)

    def test_orphan_token_passes_on_canonical_row(self):
        """Sanity: a fully canonical row does NOT raise."""
        row = _base_row()
        validate_consumer_vocabulary(row)  # must not raise

    def test_retired_alias_gets_specific_message_not_generic_orphan(self):
        """A known retired alias (e.g. measurement_surface) gets a 'use X
        instead' message distinguishing it from a true unknown orphan."""
        row = _base_row(allowed_consumers=["measurement_surface", "research_factory"])
        with pytest.raises(ConsumerAuthorityError, match="retired alias"):
            validate_consumer_vocabulary(row)


# ─────────────────────────────────────────────────────────────────────────────
# Discriminating test 2: promoted_null granting neuralweb_context must FAIL
# ─────────────────────────────────────────────────────────────────────────────

class TestPromotedNullNeuralwebContextFails:
    def test_promoted_null_with_neuralweb_context_fails(self):
        row = _base_row(
            status="promoted_null",
            allowed_consumers=["neuralweb_context", "cycle_docs", "research_factory"],
        )
        with pytest.raises(ConsumerAuthorityError, match="neuralweb_context"):
            validate_consumer_vocabulary(row)

    def test_display_with_neuralweb_context_passes(self):
        """Sanity: neuralweb_context IS legal for a non-promoted_null status
        (e.g. display) — the rule is status-scoped, not a blanket ban on the
        token (A2 F6: it is a canonical, matrix-listed token)."""
        row = _base_row(
            status="display",
            allowed_consumers=["neuralweb_context", "cycle_docs", "research_factory"],
        )
        validate_consumer_vocabulary(row)  # must not raise

    def test_promoted_null_without_neuralweb_context_passes(self):
        row = _base_row(
            status="promoted_null",
            allowed_consumers=["cycle_docs", "research_factory"],
        )
        validate_consumer_vocabulary(row)  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# Discriminating test 3: missing universal money-path forbid must FAIL
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingUniversalForbidFails:
    @pytest.mark.parametrize("dropped", sorted(UNIVERSAL_MONEY_PATH_FORBIDS))
    def test_missing_each_universal_token_fails(self, dropped):
        forbidden = sorted(UNIVERSAL_MONEY_PATH_FORBIDS - {dropped})
        row = _base_row(forbidden_consumers=forbidden)
        with pytest.raises(ConsumerAuthorityError, match="universal money-path"):
            validate_consumer_vocabulary(row)

    def test_all_four_present_passes(self):
        row = _base_row(forbidden_consumers=sorted(UNIVERSAL_MONEY_PATH_FORBIDS))
        validate_consumer_vocabulary(row)  # must not raise

    def test_cpi011_style_seeding_omission_reproduced_and_fails(self):
        """A2 finding F5: CPI-011 originally shipped without
        sector_central_direction_score in forbidden_consumers. Reproducing
        that exact (now-healed) shape must still fail today."""
        row = _base_row(forbidden_consumers=["board_rank", "oracle_escalation", "position_sizing"])
        with pytest.raises(ConsumerAuthorityError, match="sector_central_direction_score"):
            validate_consumer_vocabulary(row)


# ─────────────────────────────────────────────────────────────────────────────
# Discriminating test 4: a writer attempting hazard_baseline_override must FAIL
# ─────────────────────────────────────────────────────────────────────────────

class TestHazardBaselineOverrideFails:
    def test_hazard_baseline_override_in_allowed_consumers_fails(self):
        """The latent build_phase_clock_eval.py token (A2 finding F1) — never
        fired in a live row, but must be rejected outright if a writer ever
        attempts to mint it (CPI-H1 ruling 4)."""
        row = _base_row(allowed_consumers=["measurement_page", "hazard_baseline_override"])
        with pytest.raises(ConsumerAuthorityError, match="hazard_baseline_override"):
            validate_consumer_vocabulary(row)

    def test_hazard_baseline_override_via_append_truth_fails(self, tmp_path):
        """End-to-end: append_truth() (the real writer entry point) must
        reject a row minting hazard_baseline_override — not just the
        standalone validator function."""
        p = tmp_path / "truths.jsonl"
        real_ref = "research/cycle_masterplan/W04_KEYSTONE_VERDICT.md"
        row = _base_row(
            truth_id="TEST-HBO-001",
            evidence_refs=[real_ref],
            allowed_consumers=["measurement_page", "hazard_baseline_override"],
        )
        with pytest.raises(ValueError, match="hazard_baseline_override"):
            append_truth(row, p)
        # Nothing was written — reject means reject.
        assert not p.exists() or p.read_text() == ""

    def test_other_cpi016_retired_tokens_also_fail(self):
        """The other three orphan tokens CPI-016 used to mint
        (forward_allocation, signal_generation — both retired outright per
        ruling 4) must also fail."""
        for token in ("forward_allocation", "signal_generation"):
            row = _base_row(
                forbidden_consumers=sorted(UNIVERSAL_MONEY_PATH_FORBIDS) + [token]
            )
            with pytest.raises(ConsumerAuthorityError, match="retired alias"):
                validate_consumer_vocabulary(row)


# ─────────────────────────────────────────────────────────────────────────────
# Discriminating test 5: every existing legal row passes after its heal
# ─────────────────────────────────────────────────────────────────────────────

class TestFullHealedRegistryPasses:
    def _latest_versions(self) -> list[dict]:
        rows = load_truths(TRUTHS_PATH)
        latest: dict[str, dict] = {}
        for row in rows:
            tid = row["truth_id"]
            if tid not in latest or row["version"] > latest[tid]["version"]:
                latest[tid] = row
        return list(latest.values())

    def test_full_healed_registry_passes(self):
        rows = self._latest_versions()
        assert len(rows) >= 27, f"expected >= 27 distinct truth_ids, got {len(rows)}"
        errors = validate_registry(rows)
        assert not errors, "healed registry has consumer-vocabulary errors:\n" + "\n".join(errors)

    def test_healed_rows_carry_the_universal_forbid_floor(self):
        for row in self._latest_versions():
            forbidden = set(row.get("forbidden_consumers", []))
            missing = UNIVERSAL_MONEY_PATH_FORBIDS - forbidden
            assert not missing, f"{row['truth_id']}: missing universal forbid(s) {sorted(missing)}"

    def test_no_retired_alias_survives_in_latest_versions(self):
        aliases = set(retired_aliases())
        for row in self._latest_versions():
            tokens = set(row.get("allowed_consumers", [])) | set(row.get("forbidden_consumers", []))
            hit = tokens & aliases
            assert not hit, f"{row['truth_id']}: latest version still carries retired alias(es) {sorted(hit)}"

    def test_cpi011_now_carries_all_four_universal_forbids(self):
        """A2 finding F5 heal check: CPI-011's forgotten
        sector_central_direction_score is present on the latest version."""
        rows = {r["truth_id"]: r for r in self._latest_versions()}
        assert "CPI-011" in rows
        assert UNIVERSAL_MONEY_PATH_FORBIDS <= set(rows["CPI-011"]["forbidden_consumers"])

    def test_cpi016_no_longer_orphaned(self):
        """A2 finding F1 heal check: CPI-016 no longer carries its private
        display/display_only/forward_allocation/signal_generation vocabulary."""
        rows = {r["truth_id"]: r for r in self._latest_versions()}
        assert "CPI-016" in rows
        row = rows["CPI-016"]
        canon = canonical_tokens()
        tokens = set(row["allowed_consumers"]) | set(row["forbidden_consumers"])
        assert tokens <= canon, f"CPI-016 still has non-canonical tokens: {tokens - canon}"

    def test_f6_promoted_null_rows_no_longer_grant_neuralweb_context(self):
        """A2 finding F6 heal check: the five named promoted_null rows no
        longer grant neuralweb_context."""
        f6_ids = {
            "cycle_truth_ft1_breadth_hazard_null_v1",
            "cycle_truth_ft4_structure_hazard_null_v1",
            "cycle_truth_ft2_credit_hazard_null_v1",
            "cycle_truth_cn_downturn_broken_trend_tail_null_v1",
            "cycle_truth_ix1_index_transfer_null_v1",
        }
        rows = {r["truth_id"]: r for r in self._latest_versions()}
        for tid in f6_ids:
            assert tid in rows, f"expected {tid} in registry"
            assert rows[tid]["status"] == "promoted_null"
            assert "neuralweb_context" not in rows[tid]["allowed_consumers"], (
                f"{tid}: still grants neuralweb_context after F6 heal"
            )

    def test_registry_history_is_append_only_v1_rows_unchanged(self):
        """The heal must never rewrite a historical line — the original v1
        row for every healed truth_id must still be present, byte-identical
        in its allowed/forbidden_consumers, alongside the new healed
        version."""
        rows = load_truths(TRUTHS_PATH)
        v1_cpi001 = next(r for r in rows if r["truth_id"] == "CPI-001" and r["version"] == 1)
        assert v1_cpi001["allowed_consumers"] == [
            "measurement_surface", "honesty_display", "research_factory",
        ], "historical CPI-001 v1 row must remain unmutated (append-only)"


# ─────────────────────────────────────────────────────────────────────────────
# Wiring: validate_truth() reuses this module (not a second implementation)
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateTruthWiring:
    def test_validate_truth_rejects_orphan_token(self):
        row = _base_row(allowed_consumers=["not_a_real_surface_xyz"])
        with pytest.raises(ValueError, match="orphan token"):
            validate_truth(row, check_refs_exist=False)

    def test_validate_truth_check_consumer_vocabulary_false_skips_check(self):
        """Historical-row re-validation callers may opt out (used by
        test_seeded_truths_all_valid for non-latest versions)."""
        row = _base_row(allowed_consumers=["measurement_surface"])
        validate_truth(row, check_refs_exist=False, check_consumer_vocabulary=False)


# ─────────────────────────────────────────────────────────────────────────────
# CI-wired registry scan extension (scripts/check_cycle_pattern_authority.py)
# ─────────────────────────────────────────────────────────────────────────────

class TestCIWiredRegistryScan:
    def test_scan_registry_vocabulary_clean_on_real_registry(self):
        sys.path.insert(0, str(_REPO / "scripts"))
        try:
            import check_cycle_pattern_authority as guard
            errors = guard.scan_registry_vocabulary(_REPO)
            assert not errors, "\n".join(errors)
        finally:
            sys.path.pop(0)

    def test_scan_registry_vocabulary_catches_planted_orphan(self, tmp_path):
        import json
        sys.path.insert(0, str(_REPO / "scripts"))
        try:
            import check_cycle_pattern_authority as guard
            bad_path = tmp_path / "truths.jsonl"
            row = _base_row(truth_id="PLANTED-001", allowed_consumers=["totally_orphan_token"])
            bad_path.write_text(json.dumps(row) + "\n")
            errors = guard.scan_registry_vocabulary(_REPO, path=bad_path)
            assert errors, "planted orphan token must be caught by the CI-wired scan"
            assert any("orphan token" in e for e in errors)
        finally:
            sys.path.pop(0)

    def test_main_exits_nonzero_on_planted_registry_violation(self, tmp_path, monkeypatch):
        """End-to-end: main() must exit 1 when the registry scan is dirty,
        proving the CI wiring (not just the underlying function)."""
        import json
        sys.path.insert(0, str(_REPO / "scripts"))
        try:
            import check_cycle_pattern_authority as guard
            bad_root = tmp_path / "fake_repo"
            (bad_root / "data" / "cycle_pattern").mkdir(parents=True)
            row = _base_row(truth_id="PLANTED-002", allowed_consumers=["totally_orphan_token_2"])
            (bad_root / "data" / "cycle_pattern" / "truths.jsonl").write_text(
                json.dumps(row) + "\n"
            )
            monkeypatch.setattr(sys, "argv", ["check_cycle_pattern_authority.py", "--root", str(bad_root)])
            rc = guard.main()
            assert rc == 1, "main() must exit 1 when the registry vocabulary scan finds a violation"
        finally:
            sys.path.pop(0)
