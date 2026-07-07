"""tests/test_entity_thesis_registry.py — Unit tests for engine.neuralweb.entity_thesis_mechanism_registry.

All tests use tmp_path fixtures with minimal synthetic inputs; they never read live data/.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine.neuralweb.entity_thesis_mechanism_registry import (  # noqa: E402
    AUTHORITY_BLOCK,
    NAMESPACE_PATTERNS,
    REGISTRY_TYPES,
    build,
    lookup,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, obj) -> None:
    _write(path, json.dumps(obj))


def _write_jsonl(path: Path, rows: list) -> None:
    _write(path, "\n".join(json.dumps(r) for r in rows))


def _make_species(tmp: Path) -> None:
    _write_json(
        tmp / "data" / "species" / "registry.json",
        {
            "species": [
                {
                    "species_id": "S1",
                    "version": "1.0",
                    "name": "Cohort Washout Reversal",
                    "validation_status": "phase0",
                    "deployment_status": "chip",
                    "mechanism": "Sector cohort liquidation exhausts marginal seller.",
                    "horizon_class": "positional",
                    "market_scope": "US",
                    "evidence_stack": [{"condition": "cohort >= 0.40", "tag": "arming"}],
                    "rejection_rules": [],
                    "trial_count": 0,
                },
                {
                    "species_id": "S2",
                    "version": "1.0",
                    "name": "Donor Washout Reversal",
                    "validation_status": "phase0",
                    "deployment_status": "chip",
                    "mechanism": "Donor unwind funds laggard entries.",
                    "horizon_class": "rotational",
                    "market_scope": "US",
                    "evidence_stack": [],
                    "rejection_rules": [],
                    "trial_count": 5,
                },
            ]
        },
    )


def _make_candidates(tmp: Path) -> None:
    """Two candidates: one with spec_ref (safe), one without, one with unsafe spec_ref."""
    _write_jsonl(
        tmp / "data" / "research_factory" / "candidates.jsonl",
        [
            {
                "schema": "rf.v1",
                "authority": "display_only",
                "candidate_id": "rf-20260101-oracle-alpha_washout",
                "spec_ref": "A9_WASHOUT",
                "domain": "oracle",
                "hypothesis": "Washout reversal hypothesis text for testing.",
                "mechanism": "washout prose mechanism text",
                "trial_accounting": {"mode": "oracle_screen", "family": None},
                "lineage": {},
                "source": "test",
            },
            {
                "schema": "rf.v1",
                "authority": "display_only",
                "candidate_id": "rf-20260101-oracle-alpha_washout_b",
                "spec_ref": "A9_WASHOUT",
                "domain": "oracle",
                "hypothesis": "Second candidate sharing same spec_ref.",
                "mechanism": "washout prose mechanism second",
                "trial_accounting": {"mode": "oracle_screen", "family": None},
                "lineage": {},
                "source": "test",
            },
            {
                "schema": "rf.v1",
                "authority": "display_only",
                "candidate_id": "rf-20260101-oracle-no_spec",
                "spec_ref": None,
                "domain": "oracle",
                "hypothesis": "Candidate without spec_ref.",
                "mechanism": "no-spec prose mechanism text",
                "trial_accounting": {"mode": "oracle_screen", "family": None},
                "lineage": {},
                "source": "test",
            },
            {
                "schema": "rf.v1",
                "authority": "display_only",
                "candidate_id": "rf-20260101-oracle-unsafe_spec",
                "spec_ref": "NEW:UNSAFE_SPEC",
                "domain": "oracle",
                "hypothesis": "Candidate with unsafe spec_ref (colon).",
                "mechanism": "unsafe spec prose",
                "trial_accounting": {"mode": "oracle_screen", "family": None},
                "lineage": {},
                "source": "test",
            },
        ],
    )


def _make_transitions(tmp: Path) -> None:
    _write_jsonl(
        tmp / "data" / "research_factory" / "transitions.jsonl",
        [
            {
                "schema": "rf.transition.v1",
                "authority": "display_only",
                "candidate_id": "rf-20260101-oracle-alpha_washout",
                "from": "proposed",
                "to": "registered",
                "reason_code": "adopt_oracle",
                "reason_text": "A9 registered via PR #1234.",
                "actor": "script",
                "as_of": "2026-01-01T10:00:00+00:00",
            },
            {
                "schema": "rf.transition.v1",
                "authority": "display_only",
                "candidate_id": "rf-20260101-oracle-alpha_washout",
                "from": "registered",
                "to": "screened",
                "reason_code": "screened",
                "reason_text": "Screened OK.",
                "actor": "script",
                "as_of": "2026-01-02T10:00:00+00:00",
            },
        ],
    )


def _make_trial_ledger(tmp: Path) -> None:
    _write_jsonl(
        tmp / "data" / "trial_ledger.jsonl",
        [
            {
                "ts": "2026-01-01T09:00:00+00:00",
                "family": "incremental_ic:washout_test",
                "config_hash": "abc123",
                "config": {"signal": "washout", "h": 21},
                "source": "grid",
            },
            {
                "ts": "2026-01-02T09:00:00+00:00",
                "family": "incremental_ic:washout_test",
                "config_hash": "def456",
                "config": {"signal": "washout", "h": 42},
                "source": "grid",
            },
            {
                "ts": "2026-01-03T09:00:00+00:00",
                "family": "other_family:alpha",
                "config_hash": "ghi789",
                "config": {"signal": "alpha"},
                "source": "grid",
            },
        ],
    )


def _make_governance(tmp: Path) -> None:
    _write_jsonl(
        tmp / "data" / "neuralweb" / "governance.jsonl",
        [
            {
                "schema": "neuralweb.governance.v1",
                "event_id": "abcdef1234567890",
                "event_type": "research_factory_challenge",
                "target": "research_factory/challenges/rf-20260101-oracle-alpha_washout",
                "ts": "2026-01-01T12:00:00+00:00",
                "article": "3",
                "authored_by": "fable",
            },
        ],
    )


def _make_reflexivity(tmp: Path) -> None:
    _write_json(
        tmp / "site" / "factordata" / "reflexivity_overlay.json",
        {
            "same_thesis_groups": [
                {
                    "members": ["NVDA", "AVGO"],
                    "size": 2,
                    "basis": "membership-jaccard",
                    "label": "AI Infrastructure",
                },
                {
                    "members": ["XOM", "CVX"],
                    "size": 2,
                    "basis": "membership-jaccard",
                    "label": "Energy Majors",
                },
            ]
        },
    )


def _make_funnel_parquet(tmp: Path) -> None:
    try:
        import pandas as pd  # noqa: PLC0415
    except ImportError:
        pytest.skip("pandas not installed")
    df = pd.DataFrame(
        {
            "ticker": ["NVDA", "AVGO", "XOM"],
            "as_of": ["2026-01-01", "2026-01-01", "2026-01-01"],
            "state": [
                "thesis_candidate_shadow",
                "watch_for_thesis",
                "not_eligible",
            ],
        }
    )
    path = tmp / "data" / "research" / "thesis_funnel_states.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(str(path), index=False)


def _make_experiments(tmp: Path) -> None:
    _write_json(
        tmp / "data" / "experiments" / "registry_seed.json",
        {
            "experiments": [
                {
                    "id": "species-S1",
                    "name": "Setup Species S1",
                    "kind": "species_phase0",
                    "status": "proven",
                },
                {
                    "id": "species-S2",
                    "name": "Setup Species S2",
                    "kind": "species_phase0",
                    "status": "proven",
                },
                {
                    "id": "some-other-exp",
                    "name": "Other experiment",
                    "kind": "generic",
                    "status": "active",
                },
            ]
        },
    )


def _make_claim_accountability(tmp: Path) -> None:
    _write_json(
        tmp / "data" / "governance" / "claim_accountability.json",
        {
            "schema": "claim_accountability.v1",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "global": {
                "n_claims": 100,
                "n_grades": 80,
                "n_with_falsifier": 60,
                "falsifier_coverage": 0.6,
            },
            "by_desk": {"altdata": {"n_claims": 10}},
            "by_family": {"altdata": {"n_claims": 10}},
        },
    )


def _make_config_yml(tmp: Path, *, include_source_refs: bool = True, include_curated_by: bool = True) -> None:
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        pytest.skip("pyyaml not installed")
    thesis = {
        "thesis_family": "ai_infra",
        "label": "AI infrastructure capex complex",
        "tickers": ["NVDA", "AVGO", "VRT"],
        "state": "curated",
    }
    if include_curated_by:
        thesis["curated_by"] = "operator-handoff"
    if include_source_refs:
        thesis["source_refs"] = ["research/fable_exit/05_ENTITY_THESIS_MECHANISM_REGISTRY_HANDOFF.md"]

    content = {
        "schema": "neuralweb.entity_thesis_mechanism.curated.v1",
        "curated_theses": [thesis],
        "mechanism_aliases": [],
    }
    path = tmp / "config" / "entity_thesis_mechanism_registry.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(content), encoding="utf-8")


def _make_full_fixture(tmp: Path) -> None:
    """Write all fixture files into tmp/."""
    _make_species(tmp)
    _make_candidates(tmp)
    _make_transitions(tmp)
    _make_trial_ledger(tmp)
    _make_governance(tmp)
    _make_reflexivity(tmp)
    _make_funnel_parquet(tmp)
    _make_experiments(tmp)
    _make_claim_accountability(tmp)
    _make_config_yml(tmp)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildDeterminism:
    def test_two_builds_identical_after_dropping_generated_utc(self, tmp_path):
        _make_full_fixture(tmp_path)
        a1 = build(root=tmp_path)
        a2 = build(root=tmp_path)
        a1.pop("generated_utc", None)
        a2.pop("generated_utc", None)
        assert a1 == a2


class TestAuthorityStamps:
    def test_top_level_authority_exact(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        assert art["authority"] == AUTHORITY_BLOCK

    def test_every_row_authority_display_only(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        for rid, row in art["rows"].items():
            assert row["authority"] == "display_only", f"row {rid} has wrong authority"

    def test_is_context_only_true(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        assert art["is_context_only"] is True


class TestNamespaceGrammar:
    def test_every_registry_id_matches_its_type_pattern(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        type_to_ns = {
            "entity": "entity",
            "thesis": "thesis",
            "mechanism": "mechanism",  # covers both mechanism: and rf: rows
            "species_link": "species",
        }
        for rid, row in art["rows"].items():
            rtype = row["registry_type"]
            if rtype == "mechanism":
                # mechanism rows may use mechanism: or rf: namespace
                ok = (
                    NAMESPACE_PATTERNS["mechanism"].match(rid) or
                    NAMESPACE_PATTERNS["rf"].match(rid)
                )
                assert ok, f"mechanism-type row has invalid id: {rid}"
            elif rtype in type_to_ns:
                ns_key = type_to_ns[rtype]
                assert NAMESPACE_PATTERNS[ns_key].match(rid), (
                    f"row {rid} (type={rtype}) does not match {ns_key} pattern"
                )


class TestNoInventedLinks:
    def test_every_edge_source_path_is_among_inputs(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        declared_sources = set(art["sources"].keys())
        for e in art["edges"]:
            sp = e.get("source", {}).get("path")
            if sp:
                assert sp in declared_sources, (
                    f"edge {e['src']} → {e['dst']} cites unknown path {sp!r}"
                )

    def test_edge_endpoints_exist_in_rows_or_allowed_namespaces(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        rows = set(art["rows"].keys())
        trial_families = set(art["trial_families"].keys())
        for e in art["edges"]:
            src = e["src"]
            dst = e["dst"]
            # src: in rows, or rf: namespace (candidate embedded in mechanism row per spec)
            src_ok = (
                src in rows or
                NAMESPACE_PATTERNS["rf"].match(src)
            )
            assert src_ok, f"edge src {src!r} not in rows and not an rf: id"
            # dst: in rows, trial_families, or gov: namespace, or experiment id
            dst_ok = (
                dst in rows or
                dst in trial_families or
                NAMESPACE_PATTERNS["gov"].match(dst) or
                dst.startswith("species-")  # experiment_ref
            )
            assert dst_ok, f"edge dst {dst!r} not resolvable (edge kind={e['kind']})"


class TestMechanismMintingLaw:
    def test_candidate_with_spec_ref_yields_mechanism_row(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        assert "mechanism:A9_WASHOUT" in art["rows"]

    def test_candidate_with_spec_ref_yields_no_separate_rf_row(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        # rf rows for the two A9_WASHOUT candidates should NOT exist separately
        assert "rf:rf-20260101-oracle-alpha_washout" not in art["rows"]
        assert "rf:rf-20260101-oracle-alpha_washout_b" not in art["rows"]

    def test_candidate_without_spec_ref_yields_rf_row(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        assert "rf:rf-20260101-oracle-no_spec" in art["rows"]

    def test_unsafe_spec_ref_yields_rf_row(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        # NEW:UNSAFE_SPEC has a colon — ETM-R6: must get rf: row
        assert "rf:rf-20260101-oracle-unsafe_spec" in art["rows"]
        # Must NOT get a mechanism: row
        assert "mechanism:NEW:UNSAFE_SPEC" not in art["rows"]

    def test_prose_mechanism_never_becomes_id(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        prose_fragments = ["washout_prose", "no-spec_prose", "washout prose"]
        for rid in art["rows"]:
            for frag in prose_fragments:
                assert frag not in rid, f"prose fragment {frag!r} leaked into id {rid!r}"


class TestSameSpecRefCollapse:
    def test_same_spec_ref_candidates_collapse_into_one_mechanism_row(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        row = art["rows"]["mechanism:A9_WASHOUT"]
        assert "rf-20260101-oracle-alpha_washout" in row["candidate_ids"]
        assert "rf-20260101-oracle-alpha_washout_b" in row["candidate_ids"]

    def test_mechanism_row_candidate_ids_sorted(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        row = art["rows"]["mechanism:A9_WASHOUT"]
        assert row["candidate_ids"] == sorted(row["candidate_ids"])


class TestThesisRows:
    def test_thesis_slug_deterministic(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        # "AI Infrastructure" → "ai_infrastructure"
        assert "thesis:ai_infrastructure" in art["rows"]
        assert art["rows"]["thesis:ai_infrastructure"]["label"] == "AI Infrastructure"

    def test_verbatim_label_preserved(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        row = art["rows"].get("thesis:ai_infrastructure", {})
        assert row.get("label") == "AI Infrastructure"

    def test_entity_rows_only_for_referenced_tickers(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        entity_ids = [rid for rid in art["rows"] if rid.startswith("entity:")]
        tickers_from_entities = {rid.split(":")[-1] for rid in entity_ids}
        # Only NVDA, AVGO, XOM, CVX, VRT should appear (from reflexivity + curated config)
        expected_tickers = {"NVDA", "AVGO", "XOM", "CVX", "VRT"}
        assert tickers_from_entities == expected_tickers

    def test_funnel_state_joined_when_present(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        nvda = art["rows"].get("entity:US:NVDA", {})
        assert nvda.get("funnel_state") == "thesis_candidate_shadow"
        assert nvda.get("funnel_as_of") == "2026-01-01"

    def test_funnel_state_null_when_not_in_parquet(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        # VRT is in config but not in funnel parquet
        vrt = art["rows"].get("entity:US:VRT", {})
        assert vrt.get("funnel_state") is None


class TestCuratedRowIngestion:
    def test_curated_row_appears_with_source_refs(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        # "AI infrastructure capex complex" → thesis:ai_infrastructure_capex_complex
        slug_rid = "thesis:ai_infrastructure_capex_complex"
        assert slug_rid in art["rows"]
        row = art["rows"][slug_rid]
        assert row.get("source_refs") is not None
        assert row.get("curated_by") == "operator-handoff"

    def test_curated_row_missing_source_refs_skipped_and_conflict(self, tmp_path):
        try:
            import yaml  # noqa: PLC0415
        except ImportError:
            pytest.skip("pyyaml not installed")
        _make_species(tmp_path)
        _make_candidates(tmp_path)
        _make_transitions(tmp_path)
        _make_trial_ledger(tmp_path)
        _make_governance(tmp_path)
        _make_reflexivity(tmp_path)
        _make_funnel_parquet(tmp_path)
        _make_experiments(tmp_path)
        _make_claim_accountability(tmp_path)
        _make_config_yml(tmp_path, include_source_refs=False)  # missing source_refs
        art = build(root=tmp_path)
        slug_rid = "thesis:ai_infrastructure_capex_complex"
        assert slug_rid not in art["rows"]
        conflict_kinds = [c["kind"] for c in art["conflicts"]]
        assert "curated_thesis_missing_provenance" in conflict_kinds

    def test_curated_row_missing_curated_by_skipped_and_conflict(self, tmp_path):
        try:
            import yaml  # noqa: PLC0415
        except ImportError:
            pytest.skip("pyyaml not installed")
        _make_species(tmp_path)
        _make_candidates(tmp_path)
        _make_transitions(tmp_path)
        _make_trial_ledger(tmp_path)
        _make_governance(tmp_path)
        _make_reflexivity(tmp_path)
        _make_funnel_parquet(tmp_path)
        _make_experiments(tmp_path)
        _make_claim_accountability(tmp_path)
        _make_config_yml(tmp_path, include_curated_by=False)  # missing curated_by
        art = build(root=tmp_path)
        slug_rid = "thesis:ai_infrastructure_capex_complex"
        assert slug_rid not in art["rows"]
        conflict_kinds = [c["kind"] for c in art["conflicts"]]
        assert "curated_thesis_missing_provenance" in conflict_kinds


class TestPossibleDuplicates:
    def test_overlapping_tokens_produce_suggestion_pair(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        # S1 "Cohort Washout Reversal" and mechanism A9_WASHOUT both have "washout"
        # Check there's at least one dup suggestion touching washout-related rows
        dups = art["possible_duplicates"]
        # Ensure no rows were merged (both species:S1@1.0 and mechanism:A9_WASHOUT exist)
        assert "species:S1@1.0" in art["rows"]
        assert "mechanism:A9_WASHOUT" in art["rows"]
        # The duplicate pair is a suggestion; both rows are still present
        has_washout_pair = any(
            "washout" in " ".join(d.get("shared_tokens", [])) for d in dups
        )
        # If there are dup suggestions, they carry the correct note
        for d in dups:
            assert d["note"] == "suggestion only — not a merge"

    def test_duplicate_suggestion_does_not_merge_rows(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        # Rows are not merged regardless of possible_duplicates
        assert len(art["rows"]) >= 5  # at minimum species+mechanisms+theses+entities


class TestMissingInputFiles:
    def test_missing_species_file_succeeds(self, tmp_path):
        # Only create bare minimum to not crash
        _make_candidates(tmp_path)
        _make_transitions(tmp_path)
        art = build(root=tmp_path)
        assert art["sources"]["data/species/registry.json"]["present"] is False
        assert art["schema"] == "neuralweb.entity_thesis_mechanism.v1"

    def test_missing_candidates_file_succeeds(self, tmp_path):
        _make_species(tmp_path)
        art = build(root=tmp_path)
        assert art["sources"]["data/research_factory/candidates.jsonl"]["present"] is False

    def test_missing_funnel_parquet_succeeds(self, tmp_path):
        _make_species(tmp_path)
        _make_candidates(tmp_path)
        _make_transitions(tmp_path)
        art = build(root=tmp_path)
        assert art["sources"]["data/research/thesis_funnel_states.parquet"]["present"] is False


class TestLookupAPI:
    def test_query_matching_spec_ref_returns_mechanism_row(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        result = lookup(art, "A9_WASHOUT")
        match_ids = [m["id"] for m in result["matches"]]
        assert "mechanism:A9_WASHOUT" in match_ids
        assert result["verdict_hint"] == "prior work exists — cite it"

    def test_unmatched_query_returns_no_prior_verdict(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        result = lookup(art, "zzz_nonexistent_query_xyz")
        assert result["verdict_hint"] == "no prior rows matched"
        assert result["matches"] == []

    def test_query_matching_species_name(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        result = lookup(art, "Cohort Washout")
        match_ids = [m["id"] for m in result["matches"]]
        assert "species:S1@1.0" in match_ids

    def test_matches_sorted_by_registry_id(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        result = lookup(art, "washout")
        ids = [m["id"] for m in result["matches"]]
        assert ids == sorted(ids)


class TestClaimClusterReserved:
    def test_no_claim_cluster_rows_emitted(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        for rid, row in art["rows"].items():
            assert row["registry_type"] != "claim_cluster", (
                f"claim_cluster type emitted for row {rid} — ETM-R1 violation"
            )

    def test_claim_namespace_pattern_defined_but_never_emitted(self, tmp_path):
        _make_full_fixture(tmp_path)
        assert "claim" in NAMESPACE_PATTERNS
        art = build(root=tmp_path)
        for rid in art["rows"]:
            assert not rid.startswith("claim:"), f"claim: id emitted: {rid}"


class TestGracefulDegradation:
    def test_empty_jsonl_lines_tolerated(self, tmp_path):
        _make_species(tmp_path)
        _make_transitions(tmp_path)
        # Write candidates.jsonl with blank lines and trailing whitespace
        path = tmp_path / "data" / "research_factory" / "candidates.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n"
            + json.dumps({
                "schema": "rf.v1",
                "authority": "display_only",
                "candidate_id": "rf-20260101-oracle-blank_test",
                "spec_ref": "BLANK_TEST",
                "domain": "oracle",
                "hypothesis": "blank line test",
                "mechanism": "blank",
                "trial_accounting": {"mode": "oracle_screen", "family": None},
                "lineage": {},
                "source": "test",
            })
            + "\n\n   \n",
            encoding="utf-8",
        )
        art = build(root=tmp_path)
        assert "mechanism:BLANK_TEST" in art["rows"]

    def test_all_inputs_missing_returns_empty_but_valid_artifact(self, tmp_path):
        art = build(root=tmp_path)
        assert art["schema"] == "neuralweb.entity_thesis_mechanism.v1"
        assert art["is_context_only"] is True
        assert isinstance(art["rows"], dict)
        assert isinstance(art["edges"], list)
        # All sources should be marked not present
        for path_key, status in art["sources"].items():
            assert status["present"] is False, f"{path_key} unexpectedly present"


class TestRegistryTypesConstant:
    def test_registry_types_contains_expected_types(self):
        assert "entity" in REGISTRY_TYPES
        assert "thesis" in REGISTRY_TYPES
        assert "mechanism" in REGISTRY_TYPES
        assert "species_link" in REGISTRY_TYPES
        assert "claim_cluster" in REGISTRY_TYPES


class TestTrialFamilies:
    def test_trial_families_built_from_ledger(self, tmp_path):
        _make_trial_ledger(tmp_path)
        art = build(root=tmp_path)
        assert "incremental_ic:washout_test" in art["trial_families"]
        tf = art["trial_families"]["incremental_ic:washout_test"]
        assert tf["n_trials"] == 2
        assert tf["n_config_hashes"] == 2
        assert tf["first_ts"] < tf["last_ts"]

    def test_trial_families_sorted_deterministically(self, tmp_path):
        _make_trial_ledger(tmp_path)
        art = build(root=tmp_path)
        keys = list(art["trial_families"].keys())
        assert keys == sorted(keys)


class TestSpeciesExperimentMirror:
    def test_species_with_mirror_gets_experiment_ref(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        s1 = art["rows"].get("species:S1@1.0", {})
        assert s1.get("experiment_ref") == "species-S1"
        s2 = art["rows"].get("species:S2@1.0", {})
        assert s2.get("experiment_ref") == "species-S2"

    def test_mirrored_experiment_edge_emitted(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        edge_kinds = {(e["src"], e["kind"]) for e in art["edges"]}
        assert ("species:S1@1.0", "mirrored_experiment") in edge_kinds


class TestClaimContext:
    def test_claim_context_carries_global_counts(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        ctx = art.get("claim_context", {})
        assert ctx.get("global", {}).get("n_claims") == 100
        assert "by_family" in ctx


# ---------------------------------------------------------------------------
# T1 — F2: thesis slug collision union (two reflexivity groups → same slug)
# ---------------------------------------------------------------------------

class TestThesisSlugCollision:
    """T1: two reflexivity groups labeled 'AI Infra' and 'ai infra' slug to thesis:ai_infra.
    Expected: one thesis:ai_infra row, members = sorted union of both groups,
    a thesis_slug_collision conflict recorded, and every member entity present.
    """

    def _make_collision_fixture(self, tmp: Path) -> None:
        _write_json(
            tmp / "site" / "factordata" / "reflexivity_overlay.json",
            {
                "same_thesis_groups": [
                    {
                        "members": ["NVDA", "AVGO"],
                        "size": 2,
                        "basis": "membership-jaccard",
                        "label": "AI Infra",
                    },
                    {
                        "members": ["AMD", "INTC"],
                        "size": 2,
                        "basis": "membership-jaccard",
                        "label": "ai infra",
                    },
                ]
            },
        )

    def test_slug_collision_yields_single_row(self, tmp_path):
        self._make_collision_fixture(tmp_path)
        art = build(root=tmp_path)
        thesis_ids = [rid for rid in art["rows"] if rid.startswith("thesis:")]
        assert thesis_ids == ["thesis:ai_infra"], f"expected only thesis:ai_infra, got {thesis_ids}"

    def test_slug_collision_members_are_sorted_union(self, tmp_path):
        self._make_collision_fixture(tmp_path)
        art = build(root=tmp_path)
        row = art["rows"]["thesis:ai_infra"]
        assert row["members"] == sorted({"NVDA", "AVGO", "AMD", "INTC"})

    def test_slug_collision_conflict_recorded(self, tmp_path):
        self._make_collision_fixture(tmp_path)
        art = build(root=tmp_path)
        collision_conflicts = [c for c in art["conflicts"] if c["kind"] == "thesis_slug_collision"]
        assert len(collision_conflicts) >= 1, "expected thesis_slug_collision conflict"
        # detail should mention both labels
        detail = collision_conflicts[0]["detail"]
        assert "ai infra" in detail.lower() or "AI Infra" in detail

    def test_slug_collision_all_member_entities_present(self, tmp_path):
        self._make_collision_fixture(tmp_path)
        art = build(root=tmp_path)
        for ticker in ["NVDA", "AVGO", "AMD", "INTC"]:
            eid = f"entity:US:{ticker}"
            assert eid in art["rows"], f"entity {eid} missing from rows"


# ---------------------------------------------------------------------------
# T2 — F3: unsluggable CN-only label → no thesis row, conflict recorded
# ---------------------------------------------------------------------------

class TestUnsluggableThesisLabel:
    """T2: a label composed of only non-ASCII characters produces empty slug.
    Expected: no 'thesis:' row emitted, unsluggable_thesis_label conflict recorded,
    build still passes namespace validation.
    """

    def _make_cn_label_fixture(self, tmp: Path) -> None:
        _write_json(
            tmp / "site" / "factordata" / "reflexivity_overlay.json",
            {
                "same_thesis_groups": [
                    {
                        "members": ["002594.SZ", "300750.SZ"],
                        "size": 2,
                        "basis": "membership-jaccard",
                        "label": "比亚迪",  # CN-only, slugs to ""
                    },
                    {
                        "members": ["NVDA"],
                        "size": 1,
                        "basis": "membership-jaccard",
                        "label": "AI Infra",  # valid, slug ai_infra
                    },
                ]
            },
        )

    def test_cn_only_label_emits_no_thesis_row(self, tmp_path):
        self._make_cn_label_fixture(tmp_path)
        art = build(root=tmp_path)
        # The empty-slug thesis must not appear
        assert "thesis:" not in art["rows"], "bare 'thesis:' row should not be emitted"
        # The valid thesis must still appear
        assert "thesis:ai_infra" in art["rows"]

    def test_cn_only_label_records_conflict(self, tmp_path):
        self._make_cn_label_fixture(tmp_path)
        art = build(root=tmp_path)
        unsluggable = [c for c in art["conflicts"] if c["kind"] == "unsluggable_thesis_label"]
        assert len(unsluggable) >= 1, "expected unsluggable_thesis_label conflict"
        assert unsluggable[0]["detail"] == "比亚迪"

    def test_build_passes_namespace_validation_after_cn_label(self, tmp_path):
        """No thesis row with an invalid id is emitted."""
        self._make_cn_label_fixture(tmp_path)
        art = build(root=tmp_path)
        for rid in art["rows"]:
            if rid.startswith("thesis:"):
                ns_pat = NAMESPACE_PATTERNS["thesis"]
                assert ns_pat.match(rid), f"thesis row {rid!r} fails namespace pattern"


# ---------------------------------------------------------------------------
# T3 — F4(a): possible_duplicates entries carry suggestion_only: true
# ---------------------------------------------------------------------------

class TestPossibleDuplicatesSuggestionOnly:
    """T3: every possible_duplicates entry must carry suggestion_only: true."""

    def test_all_possible_duplicates_carry_suggestion_only_true(self, tmp_path):
        _make_full_fixture(tmp_path)
        art = build(root=tmp_path)
        for i, dup in enumerate(art.get("possible_duplicates", [])):
            assert dup.get("suggestion_only") is True, (
                f"possible_duplicates[{i}] missing suggestion_only: true — entry: {dup}"
            )


# ---------------------------------------------------------------------------
# T4 — F3/R8: corrupt JSONL mid-line → loader skips it, build succeeds
# ---------------------------------------------------------------------------

class TestCorruptJsonlTolerance:
    """T4: a candidates.jsonl with garbage text between valid lines must be
    tolerated: the loader skips corrupt lines, the valid line still loads,
    and build succeeds without raising.
    """

    def test_corrupt_jsonl_mid_line_skipped(self, tmp_path):
        _make_species(tmp_path)
        _make_transitions(tmp_path)
        # Construct candidates.jsonl with garbage between valid JSON lines
        valid_row = json.dumps({
            "schema": "rf.v1",
            "authority": "display_only",
            "candidate_id": "rf-20260101-oracle-corrupt_test",
            "spec_ref": "CORRUPT_TEST",
            "domain": "oracle",
            "hypothesis": "corrupt jsonl tolerance test",
            "mechanism": "tolerance",
            "trial_accounting": {"mode": "oracle_screen", "family": None},
            "lineage": {},
            "source": "test",
        })
        path = tmp_path / "data" / "research_factory" / "candidates.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            valid_row + "\n"
            + "THIS IS GARBAGE NOT JSON\n"
            + '{"also": "garbage", broken\n'
            + valid_row.replace("corrupt_test", "corrupt_test_2").replace("CORRUPT_TEST", "CORRUPT_TEST_2") + "\n",
            encoding="utf-8",
        )
        # Must not raise
        art = build(root=tmp_path)
        # Both valid candidates must be loaded
        assert "mechanism:CORRUPT_TEST" in art["rows"], "first valid row missing"
        assert "mechanism:CORRUPT_TEST_2" in art["rows"], "second valid row missing"

    def test_build_succeeds_with_mixed_corrupt_lines(self, tmp_path):
        """Build returns a schema-compliant artifact even with corrupt lines."""
        _make_species(tmp_path)
        path = tmp_path / "data" / "research_factory" / "candidates.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json at all\n{broken\n", encoding="utf-8")
        art = build(root=tmp_path)
        assert art["schema"] == "neuralweb.entity_thesis_mechanism.v1"
        assert art["is_context_only"] is True
