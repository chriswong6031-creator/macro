"""Contract-pinned tests for the BioCatalyst point-in-time theme rollup adapter.

These tests are hermetic: no network, no source activation, no service start.
They pin the two things this lane exists to protect — that the point-in-time
plane can never contribute a fact that was not knowable at ``as_of``, and that
the coverage disclosure prints the honest (today: zero) point-in-time share
instead of rounding a dark plane up into looking covered.

The BioCatalyst CI lanes install no pandas, so nothing here may import it. The
``engine/theme_clinical`` consumption seam is tested from
``tests/test_theme_clinical.py``, which runs in a lane that has pandas.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from engine.biocatalyst.theme_rollup_pit import (
    BINDING_REVIEW_STATE,
    STORE_COLUMNS,
    THEME_ROLLUP_PIT_CONTRACT_ID,
    ThemeRollupPitError,
    build_theme_rollup_pit,
    floor_fraction,
    load_modality_theme_map,
    pit_rollup_rows,
    pit_row_counts_by_modality,
    provenance_label,
    theme_coverage_disclosure,
    theme_rollup_pit_semantic_issues,
    validate_theme_rollup_pit,
)
from engine.biocatalyst.trials import build_trial_snapshot
from engine.sector_intelligence import canonical_json_sha256, validate_contract
from engine.sector_intelligence.contracts import ContractValidationError


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIXTURE = (
    ROOT
    / "data"
    / "biocatalyst"
    / "fixtures"
    / "clinicaltrials"
    / "trial_source_snapshot.after.v1.valid.json"
)
AS_OF = "2026-08-07T00:00:00Z"


# ---------------------------------------------------------------------------
# Hermetic fixture construction
# ---------------------------------------------------------------------------

def _source(
    *,
    sponsor_class: str = "INDUSTRY",
    phases: list[str] | None = None,
    retrieved_at: str = "2026-08-01T15:00:04Z",
    snapshot_suffix: str = "a",
    brief_title: str | None = None,
    posted_day: str | None = None,
) -> dict:
    source = json.loads(SOURCE_FIXTURE.read_text(encoding="utf-8"))
    protocol = source["canonical_study"]["protocolSection"]
    protocol["designModule"]["phases"] = list(phases if phases is not None else ["PHASE2"])
    protocol["sponsorCollaboratorsModule"] = {
        "leadSponsor": {"name": "Northstar Biopharma", "class": sponsor_class}
    }
    if brief_title is not None:
        protocol["identificationModule"]["briefTitle"] = brief_title
    # The registry posts its update before the snapshot is retrieved; the
    # contract binds the posted date to the hashed study, so it moves with the
    # clock rather than being patched on the envelope alone.
    posted_day = posted_day or retrieved_at[:10]
    protocol["statusModule"]["lastUpdatePostDateStruct"] = {
        "date": posted_day,
        "type": "ACTUAL",
    }
    digest = canonical_json_sha256(source["canonical_study"])
    nct_id = source["nct_id"]
    source["canonical_content_sha256"] = digest
    source["source_record_ref"] = f"src:ctgov:{nct_id}:sha256:{digest}"
    source["raw_object_key"] = f"biocatalyst/raw/clinicaltrials/v2/{nct_id}/{digest}.json"
    source["source_snapshot_id"] = f"{source['source_snapshot_id']}_{snapshot_suffix}"
    source["retrieved_at"] = retrieved_at
    source["first_seen_at"] = retrieved_at
    source["source_dataset_timestamp_raw"] = f"{posted_day}T09:00:00"
    source["source_last_update_posted_at"] = posted_day
    source["source_published_at"] = posted_day
    source["transaction_from"] = retrieved_at
    validate_contract(source, repo_root=ROOT)
    return source


def _snapshot(*, source_version_ordinal: int = 1, **kwargs) -> dict:
    return build_trial_snapshot(
        _source(**kwargs), source_version_ordinal=source_version_ordinal
    )


def _binding(snapshot: dict, modality_id: str = "glp1_named_agents") -> dict:
    return {
        "nct_id": snapshot["nct_id"],
        "modality_id": modality_id,
        "study_first_post_date": "2025-02-11",
        "source_record_ref": snapshot["source_record_ref"],
        "binding_review_state": BINDING_REVIEW_STATE,
    }


def _legacy_counts(default: int = 100) -> dict[str, int]:
    modality_theme, _ = load_modality_theme_map(ROOT)
    return {modality_id: default for modality_id in modality_theme}


def _build(snapshots, bindings, *, as_of: str = AS_OF, legacy=None) -> dict:
    return build_theme_rollup_pit(
        snapshots,
        membership_bindings=bindings,
        as_of=as_of,
        legacy_modality_counts=_legacy_counts() if legacy is None else legacy,
        repo_root=ROOT,
    )


def _theme(document: dict, theme_id: str) -> dict:
    return next(t for t in document["themes"] if t["theme_id"] == theme_id)


# ---------------------------------------------------------------------------
# The mechanism: store-shaped rows the live theme layer already consumes
# ---------------------------------------------------------------------------

def test_rollup_rows_carry_the_legacy_store_column_shape_plus_a_plane_label() -> None:
    # The literal is the legacy store's column list. Parity with the collector's
    # own STORE_COLS is pinned in tests/test_theme_clinical.py, which runs in a
    # lane that can import pandas; this lane cannot.
    assert STORE_COLUMNS == (
        "modality_id", "theme_id", "nct_id", "study_first_post_date", "year_month",
        "phases_raw", "phase1", "phase2", "phase3", "enrollment_target",
        "sponsor_class", "ingest_date", "vocabulary_version",
    )

    snapshot = _snapshot()
    document = _build([snapshot], [_binding(snapshot)])

    rows = pit_rollup_rows(document)
    assert len(rows) == 1
    assert set(rows[0]) == set(STORE_COLUMNS) | {"provenance_plane"}
    assert rows[0]["provenance_plane"] == "biocatalyst_pit"
    assert rows[0]["theme_id"] == "glp1_obesity"
    assert rows[0]["year_month"] == "2025-02"
    assert rows[0]["phases_raw"] == "PHASE2"
    assert rows[0]["phase2"] is True
    assert rows[0]["phase3"] is False
    assert rows[0]["sponsor_class"] == "INDUSTRY"


def test_built_rollup_passes_its_own_contract_and_stays_context_only() -> None:
    snapshot = _snapshot()
    document = _build([snapshot], [_binding(snapshot)])

    assert document["contract_id"] == THEME_ROLLUP_PIT_CONTRACT_ID
    validate_theme_rollup_pit(document, repo_root=ROOT)
    authority = document["authority"]
    assert authority["is_context_only"] is True
    assert authority["may_rank"] is False
    assert authority["may_gate"] is False
    assert authority["may_size"] is False
    assert authority["may_escalate"] is False
    assert "fused_obs_z" in authority["fused_obs_z_fence"]
    assert "originate_signal" in authority["forbidden_uses"]
    assert "rank_security" in authority["forbidden_uses"]


def test_row_counts_are_addressable_by_theme_and_modality() -> None:
    snapshot = _snapshot()
    document = _build([snapshot], [_binding(snapshot)])
    assert pit_row_counts_by_modality(document) == {
        ("glp1_obesity", "glp1_named_agents"): 1
    }


# ---------------------------------------------------------------------------
# Point-in-time law
# ---------------------------------------------------------------------------

def test_a_snapshot_knowable_only_after_as_of_is_excluded_and_counted() -> None:
    future = _snapshot(retrieved_at="2026-09-01T00:00:00Z")
    document = _build([future], [_binding(future)])

    assert document["rows"] == []
    assert document["excluded"]["not_knowable_at_as_of"] == 1
    assert _theme(document, "glp1_obesity")["n_studies_pit"] == 0


def test_a_snapshot_knowable_exactly_at_as_of_is_admitted() -> None:
    edge = _snapshot(retrieved_at=AS_OF)
    document = _build([edge], [_binding(edge)])

    assert len(document["rows"]) == 1
    assert document["excluded"]["not_knowable_at_as_of"] == 0


def test_the_latest_knowable_version_wins_and_the_superseded_one_is_counted() -> None:
    # A re-poll that found no registry change: same record, two retrievals.
    first = _snapshot(
        retrieved_at="2026-07-01T00:00:00Z", posted_day="2026-07-01", snapshot_suffix="a"
    )
    second = _snapshot(
        retrieved_at="2026-08-02T00:00:00Z",
        posted_day="2026-07-01",
        snapshot_suffix="b",
        source_version_ordinal=2,
    )
    document = _build([first, second], [_binding(first)])

    assert len(document["rows"]) == 1
    assert document["rows"][0]["source_version_ordinal"] == 2
    assert document["rows"][0]["knowledge_cutoff"] == "2026-08-02T00:00:00Z"
    assert document["excluded"]["superseded_by_later_knowable_version"] == 1


def test_a_later_version_cannot_leak_backwards_across_as_of() -> None:
    early = _snapshot(
        retrieved_at="2026-07-01T00:00:00Z", posted_day="2026-07-01", snapshot_suffix="a"
    )
    late = _snapshot(
        retrieved_at="2026-08-02T00:00:00Z",
        posted_day="2026-07-01",
        snapshot_suffix="b",
        source_version_ordinal=2,
    )
    document = _build([early, late], [_binding(early)], as_of="2026-07-15T00:00:00Z")

    assert len(document["rows"]) == 1
    assert document["rows"][0]["source_version_ordinal"] == 1
    assert document["rows"][0]["knowledge_cutoff"] == "2026-07-01T00:00:00Z"
    assert document["excluded"]["not_knowable_at_as_of"] == 1
    assert document["excluded"]["superseded_by_later_knowable_version"] == 0


def test_a_changed_record_leaves_the_rollup_until_its_binding_is_re_reviewed() -> None:
    reviewed = _snapshot(posted_day="2026-07-01", retrieved_at="2026-07-02T00:00:00Z")
    changed = _snapshot(
        posted_day="2026-08-01",
        retrieved_at="2026-08-02T00:00:00Z",
        snapshot_suffix="b",
        source_version_ordinal=2,
        brief_title="Amended protocol title",
    )
    assert changed["source_record_ref"] != reviewed["source_record_ref"]

    document = _build([changed], [_binding(reviewed)])
    assert document["rows"] == []
    assert document["excluded"]["binding_evidence_mismatch"] == 1


# ---------------------------------------------------------------------------
# Membership authority — nothing is inferred
# ---------------------------------------------------------------------------

def test_an_unbound_nct_is_never_given_a_theme() -> None:
    snapshot = _snapshot()
    document = _build([snapshot], [])

    assert document["rows"] == []
    assert document["excluded"]["unbound_nct"] == 1


def test_a_binding_that_does_not_match_its_evidence_is_dropped() -> None:
    snapshot = _snapshot()
    binding = _binding(snapshot)
    binding["source_record_ref"] = "src:ctgov:NCT00000001:sha256:" + "0" * 64
    document = _build([snapshot], [binding])

    assert document["rows"] == []
    assert document["excluded"]["binding_evidence_mismatch"] == 1


def test_a_non_industry_sponsor_is_excluded_like_the_legacy_store_filter() -> None:
    snapshot = _snapshot(sponsor_class="NIH")
    document = _build([snapshot], [_binding(snapshot)])

    assert document["rows"] == []
    assert document["excluded"]["non_industry_sponsor"] == 1


def test_an_unreviewed_binding_state_is_refused_outright() -> None:
    snapshot = _snapshot()
    binding = _binding(snapshot)
    binding["binding_review_state"] = "llm_suggested"
    with pytest.raises(ThemeRollupPitError):
        _build([snapshot], [binding])


def test_a_modality_outside_the_reviewed_config_is_refused() -> None:
    snapshot = _snapshot()
    binding = _binding(snapshot, modality_id="invented_modality")
    document = _build([snapshot], [binding])

    assert document["rows"] == []
    assert document["excluded"]["unmapped_modality"] == 1


# ---------------------------------------------------------------------------
# Honest coverage disclosure
# ---------------------------------------------------------------------------

def test_an_empty_plane_prints_zero_coverage_for_every_theme() -> None:
    document = _build([], [])

    assert document["rows"] == []
    assert document["themes"]
    for theme in document["themes"]:
        assert theme["n_studies_pit"] == 0
        assert theme["pit_backed_fraction"] == 0.0
        assert theme["provenance"] == "legacy_theme_store"
        assert theme["coverage_note"]
        assert theme["coverage_note_zh"]


def test_the_coverage_fraction_is_floored_and_never_rounded_up() -> None:
    # 2/3 rounds UP to 0.666667 at six decimals; the contract floors it.
    assert floor_fraction(2, 3) == 0.666666
    assert round(2 / 3, 6) == 0.666667
    assert floor_fraction(1, 3) == 0.333333
    assert floor_fraction(1, 10_000_000) == 0.0
    assert floor_fraction(0, 0) == 0.0
    assert floor_fraction(5, 5) == 1.0


def test_coverage_is_computed_from_real_counts_at_both_levels() -> None:
    snapshot = _snapshot()
    legacy = _legacy_counts()
    legacy["glp1_named_agents"] = 99
    legacy["glp1_incretin_mechanism"] = 100
    document = _build([snapshot], [_binding(snapshot)], legacy=legacy)

    theme = _theme(document, "glp1_obesity")
    assert theme["n_studies_pit"] == 1
    assert theme["n_studies_legacy"] == 199
    assert theme["n_studies_total"] == 200
    assert theme["pit_backed_fraction"] == floor_fraction(1, 200)
    assert theme["provenance"] == "mixed"
    named = next(
        m for m in theme["modalities"] if m["modality_id"] == "glp1_named_agents"
    )
    assert named["n_studies_pit"] == 1
    assert named["n_studies_legacy"] == 99
    assert named["pit_backed_fraction"] == floor_fraction(1, 100)


def test_a_missing_legacy_denominator_is_refused_rather_than_read_as_full_coverage() -> None:
    snapshot = _snapshot()
    legacy = _legacy_counts()
    legacy.pop("glp1_incretin_mechanism")
    with pytest.raises(ThemeRollupPitError, match="glp1_incretin_mechanism"):
        _build([snapshot], [_binding(snapshot)], legacy=legacy)


def test_provenance_labels_name_the_producing_plane() -> None:
    assert provenance_label(0, 0) == "none"
    assert provenance_label(0, 5) == "legacy_theme_store"
    assert provenance_label(5, 0) == "biocatalyst_pit"
    assert provenance_label(5, 5) == "mixed"


def test_theme_coverage_disclosure_is_addressable_by_theme_id() -> None:
    document = _build([], [])
    disclosure = theme_coverage_disclosure(document)
    assert set(disclosure) == {"glp1_obesity", "diagnostics_lifesci", "medical_devices"}
    assert disclosure["glp1_obesity"]["pit_backed_fraction"] == 0.0


def test_disclosure_text_makes_no_affirmative_validated_claim() -> None:
    document = _build([], [])
    text = json.dumps(document, ensure_ascii=False)
    negated = re.sub(r"\b(un|not|no|non)-?validated\b", "", text, flags=re.IGNORECASE)
    assert "validated" not in negated.lower()


# ---------------------------------------------------------------------------
# Semantic validation is fail-closed
# ---------------------------------------------------------------------------

def _mutated(document: dict) -> dict:
    return json.loads(json.dumps(document))


def test_a_row_knowable_only_after_as_of_fails_semantic_validation() -> None:
    snapshot = _snapshot()
    document = _mutated(_build([snapshot], [_binding(snapshot)]))
    document["rows"][0]["knowledge_cutoff"] = "2026-12-31T00:00:00Z"

    codes = {issue.code for issue in theme_rollup_pit_semantic_issues(document)}
    assert "theme_rollup_pit.row_not_knowable" in codes
    with pytest.raises(ContractValidationError):
        validate_theme_rollup_pit(document, repo_root=ROOT)


def test_an_overstated_pit_count_fails_semantic_validation() -> None:
    snapshot = _snapshot()
    document = _mutated(_build([snapshot], [_binding(snapshot)]))
    theme = next(t for t in document["themes"] if t["theme_id"] == "glp1_obesity")
    theme["n_studies_pit"] = 500
    theme["n_studies_total"] = theme["n_studies_pit"] + theme["n_studies_legacy"]

    codes = {issue.code for issue in theme_rollup_pit_semantic_issues(document)}
    assert "theme_rollup_pit.theme_pit_count" in codes


def test_a_rounded_up_coverage_fraction_fails_semantic_validation() -> None:
    snapshot = _snapshot()
    document = _mutated(_build([snapshot], [_binding(snapshot)]))
    theme = next(t for t in document["themes"] if t["theme_id"] == "glp1_obesity")
    theme["pit_backed_fraction"] = 1.0

    codes = {issue.code for issue in theme_rollup_pit_semantic_issues(document)}
    assert "theme_rollup_pit.theme_fraction" in codes


def test_an_unlabelled_row_fails_semantic_validation() -> None:
    snapshot = _snapshot()
    document = _mutated(_build([snapshot], [_binding(snapshot)]))
    document["rows"][0]["provenance_plane"] = "legacy_theme_store"

    codes = {issue.code for issue in theme_rollup_pit_semantic_issues(document)}
    assert "theme_rollup_pit.row_provenance" in codes


def test_a_raised_authority_flag_fails_semantic_validation() -> None:
    snapshot = _snapshot()
    document = _mutated(_build([snapshot], [_binding(snapshot)]))
    document["authority"]["may_rank"] = True

    codes = {issue.code for issue in theme_rollup_pit_semantic_issues(document)}
    assert "theme_rollup_pit.authority" in codes
    with pytest.raises(ContractValidationError):
        validate_theme_rollup_pit(document, repo_root=ROOT)


def test_a_tampered_payload_fails_its_own_hash() -> None:
    snapshot = _snapshot()
    document = _mutated(_build([snapshot], [_binding(snapshot)]))
    document["rows"][0]["enrollment_target"] = 999_999

    codes = {issue.code for issue in theme_rollup_pit_semantic_issues(document)}
    assert "theme_rollup_pit.hash" in codes


def test_duplicate_membership_bindings_are_refused() -> None:
    snapshot = _snapshot()
    binding = _binding(snapshot)
    with pytest.raises(ThemeRollupPitError, match="duplicate"):
        _build([snapshot], [binding, dict(binding)])
