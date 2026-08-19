"""Contracts for the canonical three-repository Mastermind semantic map."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts import build_mastermind_system_map as system_map

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "config" / "mastermind_programs.yml"
SYNAPSE = REPO_ROOT / "config" / "synapse.yml"
LOBE_CHARTERS = REPO_ROOT / "config" / "lobe_charters.yml"
GENERATED_MAP = REPO_ROOT / "docs" / "MASTERMIND_SYSTEM_MAP.md"


@pytest.fixture(scope="module")
def model() -> system_map.BuildModel:
    return system_map.validate_and_build_model(
        system_map.load_yaml(REGISTRY),
        system_map.load_yaml(SYNAPSE, reject_duplicates=False),
        system_map.load_yaml(LOBE_CHARTERS, reject_duplicates=False),
        allow_generated_output_missing=False,
    )


def _owner_values(records: object) -> set[str]:
    if not isinstance(records, Mapping):
        return set()
    return {
        owner
        for record in records.values()
        if isinstance(record, Mapping)
        and isinstance((owner := record.get("owner_program")), str)
        and owner
    }


def _all_keys(value: object) -> set[str]:
    if isinstance(value, Mapping):
        return {
            str(key)
            for key in value
        } | {
            nested
            for item in value.values()
            for nested in _all_keys(item)
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return {nested for item in value for nested in _all_keys(item)}
    return set()


def test_real_registry_is_valid_and_covers_the_complete_census(model):
    registry = model.registry
    assert registry["schema"] == "mastermind_programs.v1"
    assert set(registry["repositories"]) == {"macro", "terminal", "mastermind"}
    # 59 -> 60: Grey Deer GD-0A (#5963) landed grey-deer-risk-intelligence
    # (records-only program registration; freeze research/grey_deer/, 2026-08-19).
    assert len(registry["programs"]) == 60
    assert len(registry["product_surfaces"]) == 16
    assert len(registry["cross_repo_contracts"]) == 17
    assert {
        repository: len(domains)
        for repository, domains in registry["repository_domain_coverage"].items()
    } == {"macro": 6, "terminal": 12, "mastermind": 13}

    raw_owners = _owner_values(model.synapse.get("artifacts")) | _owner_values(
        model.lobe_charters.get("charters")
    )
    # 98 -> 99: GMI W1b (#5343) made gmi-theme-graph a raw synapse owner
    # (theme-graph-nodes/edges/evidence); disposition row added in the same change.
    assert len(raw_owners) == 99
    assert raw_owners == set(registry["owner_program_dispositions"])
    assert raw_owners == {
        owner for repository, owner in model.dispositions if repository == "macro"
    }


def test_unresolved_owner_splits_are_explicit(model):
    unresolved = {
        owner
        for (repository, owner), record in model.dispositions.items()
        if repository == "macro"
        and record.get("disposition") in {"unresolved", "unresolved_split"}
    }
    assert unresolved == {"codex-b5", "engine-fix", "hk-canada"}


def test_renderer_is_current_deterministic_and_read_only(model):
    before = {path: path.read_bytes() for path in (REGISTRY, SYNAPSE, LOBE_CHARTERS)}
    first = system_map.render_markdown(model)
    second = system_map.render_markdown(model)
    assert first == second
    assert GENERATED_MAP.read_text(encoding="utf-8") == first
    assert {path: path.read_bytes() for path in before} == before


def test_optional_deep_audit_state_does_not_change_generated_bytes(model):
    alternate_validation_state = replace(
        model,
        validated_repositories=frozenset(model.registry["repositories"]),
    )
    assert system_map.render_markdown(alternate_validation_state) == system_map.render_markdown(
        model
    )


def test_curated_registry_rejects_duplicate_keys(tmp_path):
    duplicate = tmp_path / "duplicate.yml"
    duplicate.write_text(
        "schema: mastermind_programs.v1\nschema: duplicate\n", encoding="utf-8"
    )
    with pytest.raises(system_map.DuplicateKeyError, match="duplicate YAML key 'schema'"):
        system_map.load_yaml(duplicate)


def test_invalid_kind_and_unknown_relation_target_fail_closed(model):
    registry = copy.deepcopy(model.registry)
    first_program = next(iter(registry["programs"].values()))
    first_program["kind"] = "ontology_cosplay"
    first_program["relationships"] = {"consumes_from": ["missing-program"]}
    bad_source = system_map.LoadedYaml(
        path=REGISTRY,
        data=registry,
        sha256="synthetic",
    )
    with pytest.raises(system_map.ValidationError) as exc_info:
        system_map.validate_and_build_model(
            bad_source,
            system_map.load_yaml(SYNAPSE, reject_duplicates=False),
            system_map.load_yaml(LOBE_CHARTERS, reject_duplicates=False),
            allow_generated_output_missing=False,
        )
    message = str(exc_info.value)
    assert "ontology_cosplay" in message
    assert "missing-program" in message


def test_repository_baselines_are_full_exact_pins(model):
    registry = copy.deepcopy(model.registry)
    registry["meta"]["repository_baselines"]["terminal"] = "not-a-sha"
    bad_source = system_map.LoadedYaml(
        path=REGISTRY,
        data=registry,
        sha256="synthetic",
    )
    with pytest.raises(system_map.ValidationError, match="40-hex commit SHA"):
        system_map.validate_and_build_model(
            bad_source,
            system_map.load_yaml(SYNAPSE, reject_duplicates=False),
            system_map.load_yaml(LOBE_CHARTERS, reject_duplicates=False),
            allow_generated_output_missing=False,
        )


def test_deep_audit_requires_baseline_on_remote_default_branch(tmp_path, monkeypatch):
    baseline = "a" * 40

    def fake_git(_root, *args):
        if args == ("rev-parse", "--show-toplevel"):
            return SimpleNamespace(returncode=0, stdout=str(tmp_path))
        if args == ("remote", "get-url", "origin"):
            return SimpleNamespace(
                returncode=0,
                stdout="https://github.com/mastermindx-market-intelligence/macro.git\n",
            )
        if args == ("symbolic-ref", "--short", "refs/remotes/origin/HEAD"):
            return SimpleNamespace(returncode=0, stdout="origin/main\n")
        if args == ("cat-file", "-e", f"{baseline}^{{commit}}"):
            return SimpleNamespace(returncode=0, stdout="")
        if args == ("merge-base", "--is-ancestor", baseline, "HEAD"):
            return SimpleNamespace(returncode=0, stdout="")
        if args == ("merge-base", "--is-ancestor", baseline, "origin/main"):
            return SimpleNamespace(returncode=1, stdout="")
        raise AssertionError(args)

    monkeypatch.setattr(system_map, "_git_result", fake_git)
    errors = system_map._Errors()
    system_map._validate_repository_git_state(
        {
            "macro": {
                "github": "mastermindx-market-intelligence/macro",
                "default_branch": "main",
            }
        },
        {"macro": baseline},
        {"macro": tmp_path},
        {"macro"},
        errors,
    )
    assert any("not an ancestor of origin/main" in error for error in errors.items)


def test_semantic_registry_does_not_duplicate_machine_authority_flags(model):
    forbidden = {
        "can_score",
        "can_rank",
        "can_gate",
        "can_size",
        "can_trade",
        "can_execute",
    }
    assert not (_all_keys(model.registry) & forbidden)


def test_generated_map_answers_the_cross_repository_orientation_questions(model):
    markdown = system_map.render_markdown(model)
    required_facts = (
        "## Project Topology",
        "## Truth Organization and Reasoning Sequence",
        "## Architecture Overview",
        "## Program Cards",
        "## Typed Relations",
        "## Decision Boundaries",
        "## Product Map",
        "## Cross-Repo Contracts",
        "## Raw Owner Coverage",
        "## Sibling Repository Domain Coverage",
        "## Unresolved Items and Provenance",
        "Seven-book paper-only portfolio operating system",
        "Own interactive charts, panes, drawings, indicators",
        "Basket participation and group breadth",
        "Per-name residual-shock, price-pressure, and washout evidence",
        "Terminal owns validation, UI composition, and its local flow_score_v1",
        "without importing unrestricted upstream authority",
        "excludes per-position cost_basis, entry_price, current_price, shares",
        "`gmi-theme-graph` | `extends` | `conceptual` | `thematic-intelligence`",
        "Known architecture and contract unresolveds",
        "non-binding semantic posture summaries",
        "`docs/PROJECT_ACTIVE_BUILD_MAP.md`",
        "`research/DO_NOT_REBUILD.md`",
        "Audited baseline",
    )
    missing = [fact for fact in required_facts if fact not in markdown]
    assert not missing, f"generated map cannot answer required orientation facts: {missing}"


def test_theme_dislocation_and_runtime_edges_keep_distinct_owners(model):
    programs = model.registry["programs"]
    group_reads = programs["group-reads"]
    assert group_reads["canonical_docs"] == [
        {"repo": "macro", "path": "research/GROUP_READS_MASTERPLAN_BY_FABLE.md"}
    ]
    assert group_reads["implementation"][0]["roots"] == [
        "engine/group_pulse.py",
        "engine/group_earnings.py",
        "engine/group_linked_outsiders.py",
        "data/group_pulse/",
    ]
    assert programs["gmi-theme-graph"]["implementation"] == []
    assert "engine/dislocation.py" in programs["market-regime-risk"]["implementation"][0][
        "roots"
    ]
    assert "engine/options_dislocation.py" in programs["options-intelligence"][
        "implementation"
    ][0]["roots"]
    assert "terminal-signal-layer" not in programs["neural-web"]["relationships"].get(
        "feeds_context_to", []
    )


def test_relationship_modes_and_product_delivery_are_visible(model):
    markdown = system_map.render_markdown(model)
    assert "`operating-cortex` | `coordinates_with` | `planned` | `market-memory`" in markdown
    assert "`market-memory` | `feeds_context_to` | `research_adapter` | `research-factory`" in markdown
    assert "`neural-web` | `feeds_context_to` | `contracted` | `terminal-charting`" in markdown
    assert "No live Market Memory adapter" in markdown
    product_rows = [line for line in markdown.splitlines() if line.startswith("| `portfolio-public-snapshot`")]
    assert len(product_rows) == 1
    assert "aggregate simulated performance" in product_rows[0]
    assert "`macro` (`product_host`)" in product_rows[0]
    assert "`mastermind` (`publisher`)" in product_rows[0]
    assert "`mastermind:bridge/macro_snapshot.py`" in product_rows[0]


def test_runtime_relationship_proof_and_authority_sources_fail_closed(model):
    registry = copy.deepcopy(model.registry)
    registry["programs"]["operating-cortex"]["relationships"]["coordinates_with"] = [
        {
            "target": "market-memory",
            "mode": "implemented",
            "evidence_refs": ["macro:definitely/not/a/real/path.py"],
        }
    ]
    bad_source = system_map.LoadedYaml(path=REGISTRY, data=registry, sha256="synthetic")
    with pytest.raises(system_map.ValidationError, match="referenced path does not exist"):
        system_map.validate_and_build_model(
            bad_source,
            system_map.load_yaml(SYNAPSE, reject_duplicates=False),
            system_map.load_yaml(LOBE_CHARTERS, reject_duplicates=False),
            allow_generated_output_missing=False,
        )

    registry = copy.deepcopy(model.registry)
    contracted = registry["programs"]["neural-web"]["relationships"]["feeds_context_to"][-1]
    contracted["contract"] = "macro-terminal-options-prophet"
    bad_source = system_map.LoadedYaml(path=REGISTRY, data=registry, sha256="synthetic")
    with pytest.raises(system_map.ValidationError, match="not endpoint-bound"):
        system_map.validate_and_build_model(
            bad_source,
            system_map.load_yaml(SYNAPSE, reject_duplicates=False),
            system_map.load_yaml(LOBE_CHARTERS, reject_duplicates=False),
            allow_generated_output_missing=False,
        )

    registry = copy.deepcopy(model.registry)
    registry["programs"]["operating-cortex"]["relationships"]["coordinates_with"] = [
        {
            "target": "market-memory",
            "mode": "conceptual",
            "contract": "terminal-auth-entitlement",
        }
    ]
    bad_source = system_map.LoadedYaml(path=REGISTRY, data=registry, sha256="synthetic")
    with pytest.raises(
        system_map.ValidationError,
        match="contract may only be declared by a contracted relationship",
    ):
        system_map.validate_and_build_model(
            bad_source,
            system_map.load_yaml(SYNAPSE, reject_duplicates=False),
            system_map.load_yaml(LOBE_CHARTERS, reject_duplicates=False),
            allow_generated_output_missing=False,
        )

    registry = copy.deepcopy(model.registry)
    registry["programs"]["operating-cortex"]["relationships"]["coordinates_with"] = [
        {
            "target": "market-memory",
            "mode": "planned",
            "note": "No runtime claim.",
            "evidence_refs": ["macro:engine/neuralweb/cortex.py"],
        }
    ]
    bad_source = system_map.LoadedYaml(path=REGISTRY, data=registry, sha256="synthetic")
    with pytest.raises(
        system_map.ValidationError,
        match="evidence_refs may only be declared by implemented or research_adapter",
    ):
        system_map.validate_and_build_model(
            bad_source,
            system_map.load_yaml(SYNAPSE, reject_duplicates=False),
            system_map.load_yaml(LOBE_CHARTERS, reject_duplicates=False),
            allow_generated_output_missing=False,
        )

    registry = copy.deepcopy(model.registry)
    del registry["programs"]["prophet-us"]["decision_boundary"]["authority_sources"]
    bad_source = system_map.LoadedYaml(path=REGISTRY, data=registry, sha256="synthetic")
    with pytest.raises(system_map.ValidationError, match="requires explicit authority sources"):
        system_map.validate_and_build_model(
            bad_source,
            system_map.load_yaml(SYNAPSE, reject_duplicates=False),
            system_map.load_yaml(LOBE_CHARTERS, reject_duplicates=False),
            allow_generated_output_missing=False,
        )


def test_known_unresolveds_and_chf_ontology_are_explicit(model):
    registry = copy.deepcopy(model.registry)
    registry["meta"]["known_unresolveds"] = "not-a-list"
    bad_source = system_map.LoadedYaml(path=REGISTRY, data=registry, sha256="synthetic")
    with pytest.raises(system_map.ValidationError, match="known_unresolveds: must be a list"):
        system_map.validate_and_build_model(
            bad_source,
            system_map.load_yaml(SYNAPSE, reject_duplicates=False),
            system_map.load_yaml(LOBE_CHARTERS, reject_duplicates=False),
            allow_generated_output_missing=False,
        )

    programs = model.registry["programs"]
    assert programs["causal-hypothesis-factory"]["ontology_status"] == {
        "classification": "program_not_lobe",
        "consumes_lobe_cap": False,
        "source": {
            "repo": "macro",
            "path": "research/CAUSAL_HYPOTHESIS_FACTORY_MASTERPLAN_BY_FABLE.md",
        },
        "conflict_note": "Nine raw lobe-charter rows still carry this owner label and remain an explicit operational-registry contradiction.",
    }
    assert "causal-hypothesis-factory" not in programs["research-factory"][
        "relationships"
    ].get("contains", [])
    assert all(
        implementation["repo"] != "terminal"
        for implementation in programs["price-pressure"]["implementation"]
    )
    markdown = system_map.render_markdown(model)
    assert "Classification: `program_not_lobe`" in markdown
    assert "Contradictory raw lobe-charter rows: **9**" in markdown


def test_context_index_existing_globs_cover_all_new_durable_artifacts():
    context_index = yaml.safe_load(
        (REPO_ROOT / "config" / "context_index.yml").read_text(encoding="utf-8")
    )
    strings: set[str] = set()

    def collect(value: object) -> None:
        if isinstance(value, str):
            strings.add(value)
        elif isinstance(value, Mapping):
            for item in value.values():
                collect(item)
        elif isinstance(value, Sequence):
            for item in value:
                collect(item)

    collect(context_index)
    assert {"config/*.yml", "docs/**/*.md", "research/**/*.md"} <= strings

    macro_sources = context_index["projects"]["macro-dashboard"]["sources"]
    active_build_source = next(
        source for source in macro_sources if source["id"] == "repo-active-build-map"
    )
    assert active_build_source["authority_class"] == "A4"
    assert set(active_build_source["roots"]) == {
        "docs/ACTIVE_BUILD_MAP.md",
        "docs/PROJECT_ACTIVE_BUILD_MAP.md",
    }
