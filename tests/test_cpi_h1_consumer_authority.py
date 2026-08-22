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

    @pytest.mark.parametrize("status", ["candidate", "retired", "superseded"])
    def test_class_conditional_check_extended_beyond_promoted_null(self, status):
        """Fable adjudication (2026-08-21, extending rulings 6+8): the
        neuralweb_context-vs-class-forbid check is matrix-driven, not
        hardcoded to promoted_null — the `candidates`, `retired`, and
        `superseded` classes in consumer_matrix.yml also forbid
        neuralweb_context, so a row of any of those statuses granting it
        must fail identically to the original 5 promoted_null rows."""
        row = _base_row(
            status=status,
            allowed_consumers=["neuralweb_context", "cycle_docs", "research_factory"],
        )
        with pytest.raises(ConsumerAuthorityError, match="neuralweb_context"):
            validate_consumer_vocabulary(row)

    @pytest.mark.parametrize("status", ["display", "confirmer", "scored"])
    def test_class_conditional_check_is_matrix_driven_not_promoted_null_only(self, status):
        """Direct proof the check reads the matrix rather than a hardcoded
        status set: the display/confirmer/scored classes do NOT forbid
        neuralweb_context in consumer_matrix.yml, so those statuses must
        still pass with it granted — only classes the matrix actually
        forbids it for (promoted_null, candidates, retired, superseded) may
        reject it."""
        row = _base_row(
            status=status,
            allowed_consumers=["neuralweb_context", "cycle_docs", "research_factory"],
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
# MAJOR-1 (Fable adjudication, 2026-08-21): close the allow-side money-path
# leak — a row may forbid a money-path token, never grant it; and
# allowed_consumers/forbidden_consumers must never overlap on any token
# (the matrix's own stated DISJOINT design principle).
# ─────────────────────────────────────────────────────────────────────────────

class TestAllowSideMoneyPathLeakFails:
    @pytest.mark.parametrize("token", sorted(UNIVERSAL_MONEY_PATH_FORBIDS))
    def test_money_path_token_in_allowed_consumers_fails(self, token):
        row = _base_row(
            allowed_consumers=["measurement_page", token],
            forbidden_consumers=sorted(UNIVERSAL_MONEY_PATH_FORBIDS),
        )
        with pytest.raises(ConsumerAuthorityError, match="money-path"):
            validate_consumer_vocabulary(row)

    def test_allowed_is_exactly_one_money_path_token_fails(self):
        """allowed=[position_sizing] — the exact case named in MAJOR-1."""
        row = _base_row(
            allowed_consumers=["position_sizing"],
            forbidden_consumers=sorted(UNIVERSAL_MONEY_PATH_FORBIDS),
        )
        with pytest.raises(ConsumerAuthorityError, match="money-path"):
            validate_consumer_vocabulary(row)

    def test_allowed_grants_board_rank_fails(self):
        """The exact case named in MAJOR-1: a row granting board_rank."""
        row = _base_row(
            allowed_consumers=["measurement_page", "board_rank"],
            forbidden_consumers=sorted(UNIVERSAL_MONEY_PATH_FORBIDS),
        )
        with pytest.raises(ConsumerAuthorityError, match="board_rank"):
            validate_consumer_vocabulary(row)

    def test_allowed_forbidden_overlap_on_non_money_path_token_fails(self):
        row = _base_row(
            allowed_consumers=["measurement_page", "cycle_docs"],
            forbidden_consumers=sorted(UNIVERSAL_MONEY_PATH_FORBIDS) + ["cycle_docs"],
        )
        with pytest.raises(ConsumerAuthorityError, match="overlap"):
            validate_consumer_vocabulary(row)

    def test_disjoint_allowed_and_forbidden_passes(self):
        row = _base_row(
            allowed_consumers=["measurement_page", "cycle_docs"],
            forbidden_consumers=sorted(UNIVERSAL_MONEY_PATH_FORBIDS),
        )
        validate_consumer_vocabulary(row)  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# MINOR-1 (Fable adjudication, 2026-08-21): an unknown/unmapped status must
# RAISE, never silently fall through as a vacuous empty class-forbid.
# ─────────────────────────────────────────────────────────────────────────────

class TestUnknownStatusRaises:
    def test_typo_status_raises(self):
        row = _base_row(status="promted_null")  # typo, not a real status
        with pytest.raises(ConsumerAuthorityError, match="no matching"):
            validate_consumer_vocabulary(row)

    def test_typo_status_does_not_silently_pass(self):
        """A typo'd status must not silently disable the class-conditional
        check — this reproduces exactly the vacuous-empty-set failure mode
        MINOR-1 exists to close: before the fix, class_forbidden_consumers()
        returned frozenset() for an unmapped status, so a promoted_null-like
        row misspelled as 'promted_null' with neuralweb_context granted
        would have PASSED instead of failing on either axis."""
        row = _base_row(
            status="promted_null",
            allowed_consumers=["neuralweb_context", "cycle_docs", "research_factory"],
        )
        with pytest.raises(ConsumerAuthorityError):
            validate_consumer_vocabulary(row)

    @pytest.mark.parametrize(
        "status",
        ["candidate", "display", "confirmer", "scored", "promoted_null", "retired", "superseded"],
    )
    def test_every_real_status_resolves_without_raising_on_class_lookup(self, status):
        """Sanity: every truths.py VALID_STATUSES value DOES map to a matrix
        class (including the candidate/candidates bridge) — the raise is for
        genuine typos/unregistered statuses only, not real ones.

        Uses cycle_docs, the one token every class's matrix allowed_consumers
        carries (CPI-H1.1 confirmed this stays true after the display/
        promoted_null envelope amendment) — this test is about status/class
        RESOLUTION, not the class-subset invariant, so it must not
        accidentally trip the HARD subset check tested separately below."""
        row = _base_row(status=status, allowed_consumers=["cycle_docs"])
        validate_consumer_vocabulary(row)  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# MINOR-2 (Fable adjudication, 2026-08-21): type-validate allowed_consumers/
# forbidden_consumers as lists of strings — reject None/bare-str with a sane
# message (a bare str used to iterate character-by-character, a silent and
# dangerous misparse).
# ─────────────────────────────────────────────────────────────────────────────

class TestTypeValidation:
    def test_allowed_consumers_none_raises(self):
        row = _base_row(allowed_consumers=None)
        with pytest.raises(ConsumerAuthorityError, match="allowed_consumers"):
            validate_consumer_vocabulary(row)

    def test_forbidden_consumers_none_raises(self):
        row = _base_row(forbidden_consumers=None)
        with pytest.raises(ConsumerAuthorityError, match="forbidden_consumers"):
            validate_consumer_vocabulary(row)

    def test_allowed_consumers_bare_string_raises(self):
        """A bare str like "measurement_page" is iterable char-by-char — the
        dangerous silent misparse this check exists to catch."""
        row = _base_row(allowed_consumers="measurement_page")
        with pytest.raises(ConsumerAuthorityError, match="allowed_consumers"):
            validate_consumer_vocabulary(row)

    def test_forbidden_consumers_bare_string_raises(self):
        row = _base_row(forbidden_consumers="board_rank")
        with pytest.raises(ConsumerAuthorityError, match="forbidden_consumers"):
            validate_consumer_vocabulary(row)

    def test_allowed_consumers_non_string_entries_raise(self):
        row = _base_row(allowed_consumers=["measurement_page", 42])
        with pytest.raises(ConsumerAuthorityError, match="allowed_consumers"):
            validate_consumer_vocabulary(row)

    def test_well_typed_lists_pass(self):
        row = _base_row(
            allowed_consumers=["measurement_page"],
            forbidden_consumers=sorted(UNIVERSAL_MONEY_PATH_FORBIDS),
        )
        validate_consumer_vocabulary(row)  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# CPI-H1.1 (Sol adjudication, 2026-08-21/22): the least-privilege class-
# subset invariant (CPI-H1 ruling 8) is promoted from WARN-tier advisory to
# HARD. Five Sol-mandated discriminating mutations for this heal:
#   (a) a future display-class row granting a registered-but-non-class
#       surface -> HARD fail
#   (b) a promoted_null row granting neuralweb_context -> HARD fail (also
#       covered structurally by TestPromotedNullNeuralwebContextFails above,
#       which now exercises the SAME general subset check, not a separate
#       neuralweb-only code path)
#   (c) CPI-008 granting sync_gauge_display -> pass
#   (d) all seven existing adjudicated rows validate -> pass (real registry)
#   (e) a money-path token on the allow side -> remains HARD fail (also
#       covered structurally by TestAllowSideMoneyPathLeakFails above)
# ─────────────────────────────────────────────────────────────────────────────

class TestClassSubsetInvariantIsHard:
    def test_a_future_display_row_granting_registered_non_class_surface_fails(self):
        """(a) A registered (canonical) token that is NOT in the display
        class's matrix allowed_consumers — e.g. lead_lag_interaction_layer,
        a narrow_forbidden-group surface never added to display's envelope
        — must HARD fail even though the token itself is a real, known
        surface (not an orphan)."""
        row = _base_row(
            status="display",
            allowed_consumers=["measurement_page", "lead_lag_interaction_layer"],
        )
        with pytest.raises(ConsumerAuthorityError, match="lead_lag_interaction_layer"):
            validate_consumer_vocabulary(row)

    def test_b_promoted_null_granting_neuralweb_context_fails(self):
        """(b) Explicit CPI-H1.1 restatement: a promoted_null row granting
        neuralweb_context fails under the general class-subset check (the
        matrix's promoted_null class allowed_consumers does not list
        neuralweb_context, amended or not)."""
        row = _base_row(
            status="promoted_null",
            allowed_consumers=["cycle_docs", "neuralweb_context"],
        )
        with pytest.raises(ConsumerAuthorityError, match="neuralweb_context"):
            validate_consumer_vocabulary(row)

    def test_c_promoted_null_granting_sync_gauge_display_passes(self):
        """(c) CPI-H1.1 envelope closure: promoted_null's amended matrix
        allowed_consumers now includes sync_gauge_display (CPI-008's real
        grant) — a synthetic row exercising exactly that grant must pass."""
        row = _base_row(
            status="promoted_null",
            allowed_consumers=["measurement_page", "sync_gauge_display"],
        )
        validate_consumer_vocabulary(row)  # must not raise

    @pytest.mark.needs_full_checkout("data")
    def test_c_real_cpi008_row_passes(self):
        """(c) End-to-end against the real registry: CPI-008's actual latest
        row (status=promoted_null, allowed_consumers includes
        sync_gauge_display) must validate clean."""
        rows = load_truths(TRUTHS_PATH)
        latest: dict[str, dict] = {}
        for row in rows:
            tid = row["truth_id"]
            if tid not in latest or row["version"] > latest[tid]["version"]:
                latest[tid] = row
        assert "CPI-008" in latest
        row = latest["CPI-008"]
        assert row["status"] == "promoted_null"
        assert "sync_gauge_display" in row["allowed_consumers"]
        validate_consumer_vocabulary(row)  # must not raise

    @pytest.mark.needs_full_checkout("data")
    def test_d_all_seven_adjudicated_rows_validate_clean(self):
        """(d) All seven CPI-H1-escalated rows (CPI-002/004/005/008/011/
        014/015, research/imce/IMCE_D1C_RELEASE_RECORD.md) validate clean
        against the amended class envelopes — the real registry rows, not
        synthetic reconstructions."""
        rows = load_truths(TRUTHS_PATH)
        latest: dict[str, dict] = {}
        for row in rows:
            tid = row["truth_id"]
            if tid not in latest or row["version"] > latest[tid]["version"]:
                latest[tid] = row
        seven_ids = {
            "CPI-002", "CPI-004", "CPI-005", "CPI-008",
            "CPI-011", "CPI-014", "CPI-015",
        }
        assert seven_ids <= set(latest), f"missing from registry: {seven_ids - set(latest)}"
        for tid in sorted(seven_ids):
            row = latest[tid]
            validate_consumer_vocabulary(row)  # must not raise, per-row

        errors = validate_registry([latest[tid] for tid in seven_ids])
        assert not errors, "\n".join(errors)

    def test_e_money_path_token_on_allow_side_still_hard_fails(self):
        """(e) Explicit CPI-H1.1 restatement: the allow-side money-path leak
        check (MAJOR-1) still fires ahead of / independently from the new
        class-subset check — a money-path token in allowed_consumers is
        never legal, on any status, class-subset amendments notwithstanding."""
        row = _base_row(
            status="display",
            allowed_consumers=["measurement_page", "board_rank"],
            forbidden_consumers=sorted(UNIVERSAL_MONEY_PATH_FORBIDS),
        )
        with pytest.raises(ConsumerAuthorityError, match="money-path"):
            validate_consumer_vocabulary(row)

    def test_class_subset_error_names_status_and_extra_tokens(self):
        """Sanity: the promoted HARD error message is legible — names the
        status and the offending token(s), not a generic failure."""
        row = _base_row(
            status="superseded",
            allowed_consumers=["cycle_docs", "measurement_page"],
        )
        with pytest.raises(ConsumerAuthorityError, match=r"superseded.*measurement_page"):
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

@pytest.mark.needs_full_checkout("data")
class TestFullHealedRegistryPasses:
    """Reads the real TRUTHS_PATH — absent in a sparse worktree (policy R8)."""

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

    def test_cn_downturn_candidate_row_healed_by_fable_adjudication(self):
        """Fable adjudication (2026-08-21): cycle_truth_cn_downturn_broken_
        trend_tail_candidate_v1's successor (originally v2, status=retired)
        was carrying neuralweb_context against the retired class's matrix
        forbid — the identical A2 F6 defect one class over from the five
        named promoted_null rows. The latest version must now be clean and
        least-privilege per the retired class contract."""
        rows = {r["truth_id"]: r for r in self._latest_versions()}
        tid = "cycle_truth_cn_downturn_broken_trend_tail_candidate_v1"
        assert tid in rows
        row = rows[tid]
        assert row["status"] == "retired"
        assert row["version"] >= 3
        assert "neuralweb_context" not in row["allowed_consumers"]
        # Least-privilege: healed to the retired class's own allowlist
        # (cycle_docs, research_factory) — not mechanically widened to keep
        # measurement_page just because an earlier version had it.
        assert set(row["allowed_consumers"]) == {"cycle_docs", "research_factory"}


# ─────────────────────────────────────────────────────────────────────────────
# Writer literal audit (Fable adjudication: ruling 10 is categorical, not
# limited to the originally-named script list)
# ─────────────────────────────────────────────────────────────────────────────

class TestNoWriterEmitsRetiredAliases:
    """No live writer script under scripts/ may emit a retired-alias literal
    into allowed_consumers/forbidden_consumers. Ruling 10 ("eliminate future
    writer emissions of retired aliases") is categorical per Fable
    adjudication — this test scans every writer script that constructs a
    truths.jsonl row, not just the originally-named four."""

    WRITER_SCRIPTS = [
        "seed_cycle_truths.py",
        "build_phase_clock_eval.py",
        "run_falsosc_trial_v1.py",
        "run_har1_eval.py",
        "apply_cycle_pattern_ix1_outcomes.py",
        "apply_cycle_pattern_lattice_batch2_outcomes.py",
        "apply_cycle_pattern_tr1_outcomes.py",
    ]

    @pytest.mark.parametrize("script_name", WRITER_SCRIPTS)
    def test_writer_script_has_no_retired_alias_literal(self, script_name):
        """Scoped to the CONTENTS of allowed_consumers:/forbidden_consumers:
        list literals only — a blanket file-wide substring scan for
        'display' would false-positive on the unrelated, legitimate
        `"status": "display"` field these same writers emit.

        BOUNDEDNESS (nit, Fable adjudication 2026-08-21): this is a literal-
        text regex match, not a static/AST analysis — it catches a hardcoded
        string token (single- or double-quoted) sitting inside an
        allowed_consumers:/forbidden_consumers: list literal in one of the
        7 scripts named in WRITER_SCRIPTS above. It would NOT catch a token
        built via string concatenation, an f-string, a variable, or a
        retired alias reintroduced by a writer script outside this named
        list. The 7-script scope mirrors ruling 10 as adjudicated (every
        script that currently constructs a truths.jsonl row) — adding a new
        writer script requires adding it to WRITER_SCRIPTS by hand.
        """
        import re

        text = (_REPO / "scripts" / script_name).read_text(encoding="utf-8")
        list_bodies = re.findall(
            r'["\'](?:allowed|forbidden)_consumers["\']\s*:\s*\[(.*?)\]', text, re.DOTALL
        )
        aliases = retired_aliases()
        for body in list_bodies:
            for alias in aliases:
                for quoted in (f'"{alias}"', f"'{alias}'"):
                    assert quoted not in body, (
                        f"scripts/{script_name} still emits retired alias {alias!r} "
                        f"inside an allowed/forbidden_consumers list literal "
                        f"(ruling 10, extended to every writer by Fable adjudication)"
                    )


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
    @pytest.mark.needs_full_checkout("data")
    def test_scan_registry_vocabulary_clean_on_real_registry(self):
        """Reads the real repo's data/cycle_pattern/truths.jsonl — absent in
        a sparse worktree (policy R8)."""
        sys.path.insert(0, str(_REPO / "scripts"))
        try:
            import check_cycle_pattern_authority as guard
            errors = guard.scan_registry_vocabulary(_REPO)
            assert not errors, "\n".join(errors)
        finally:
            sys.path.pop(0)

    def test_advisory_class_subset_function_retired(self):
        """CPI-H1.1: the WARN-tier advisory_class_subset_violations() /
        scan_registry_vocabulary_advisories() reporting path is retired —
        its check was promoted into validate_consumer_vocabulary() /
        scan_registry_vocabulary() rather than left standing as a second,
        shadowing WARN path for the same invariant."""
        import engine.cycle_pattern.consumer_authority as ca
        assert not hasattr(ca, "advisory_class_subset_violations")

        sys.path.insert(0, str(_REPO / "scripts"))
        try:
            import check_cycle_pattern_authority as guard
            assert not hasattr(guard, "scan_registry_vocabulary_advisories")
        finally:
            sys.path.pop(0)

    @pytest.mark.needs_full_checkout("data")
    def test_scan_registry_vocabulary_hard_check_covers_the_seven_adjudicated_rows(self):
        """CPI-H1.1: the 7 rows escalated at the CPI-H1 heal
        (research/imce/IMCE_D1C_RELEASE_RECORD.md) — CPI-002/004/005/008/
        011/014/015 — now validate clean under the HARD class-subset check
        via the CI-wired scan_registry_vocabulary(), the same function that
        used to also carry a WARN-tier advisory for exactly these rows."""
        sys.path.insert(0, str(_REPO / "scripts"))
        try:
            import check_cycle_pattern_authority as guard
            errors = guard.scan_registry_vocabulary(_REPO)
        finally:
            sys.path.pop(0)
        assert not errors, "\n".join(errors)

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
