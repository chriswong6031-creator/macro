"""tests/test_intelligence_registry.py — derivation tests for the T1 engine registry.

Covers engine/intelligence_registry.py's pure functions with synthetic input, plus the
two defect fixtures the registry exists to fix (C-1, C-2) asserted against the LIVE
config/synapse.yml. Nothing here touches data/ — the corpus-sourced fields are exercised
with injected values so the suite runs identically in a sparse agent worktree and in CI.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine.intelligence_registry import (
    AUTHORITY_ORDER,
    GRADED_DESCRIPTIVE,
    GRADED_NOT_YET,
    GRADED_YES,
    LEDGER_NONE,
    OUTPUT_CLASSES,
    OVERLAY_ALLOWED_KEYS,
    OVERLAY_FORBIDDEN_KEYS,
    VOLATILE_ENGINE_PATHS,
    audit_content,
    bind_species,
    build_registry,
    derive_artifact_authority,
    engine_id_for,
    max_authority,
    partition_artifacts,
    placeholder_reason,
    scan_producer_source,
    serialise,
    structural_projection,
    validate_overlay,
    validate_structure,
)

REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _artifact(**over):
    base = {
        "path": "data/x.json",
        "format": "json",
        "producer": "engine/a.py",
        "owner_program": "prog",
        "cadence": "daily-engine",
        "storage": "git",
        "asof_field": "asof",
        "freshness_sla_hours": 24,
        "schema": "x",
        "tier": "display",
        "horizon_role": "context",
        "consumers": [],
    }
    base.update(over)
    return base


def _synapse(artifacts):
    return {"meta": {"schema_version": 1}, "artifacts": artifacts}


@pytest.fixture(scope="module")
def live_synapse():
    return yaml.safe_load((REPO / "config" / "synapse.yml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def live_registry():
    path = REPO / "data" / "intelligence_registry.json"
    if not path.exists():
        pytest.skip("data/intelligence_registry.json absent (sparse worktree)")
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Unit of account — the partition must be TOTAL and DISJOINT
# ---------------------------------------------------------------------------

def test_engine_id_is_producer_then_owner_program():
    assert engine_id_for("engine/a.py", "prog") == "engine/a.py::prog"


def test_partition_is_total_and_disjoint_on_the_live_registry(live_synapse):
    cells = partition_artifacts(live_synapse)
    mapped = [aid for ids in cells.values() for aid in ids]
    assert len(mapped) == len(live_synapse["artifacts"])
    assert len(set(mapped)) == len(mapped), "an artifact landed in two cells"


def test_two_programs_on_one_producer_are_two_engines():
    synapse = _synapse(
        {
            "a": _artifact(owner_program="p1"),
            "b": _artifact(owner_program="p2"),
        }
    )
    assert set(partition_artifacts(synapse)) == {"engine/a.py::p1", "engine/a.py::p2"}


def test_owner_program_span_counts_cross_program_producers():
    synapse = _synapse({"a": _artifact(owner_program="p1"), "b": _artifact(owner_program="p2")})
    registry = build_registry(synapse=synapse)
    assert {r["owner_program_span"] for r in registry["engines"]} == {2}


# ---------------------------------------------------------------------------
# Exclusions — nothing is dropped silently
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "producer",
    ["<MANUAL>", "<HAND_MAINTAINED>", "<MASTERMIND_EXTERNAL>",
     "<RESEARCH_FACTORY_MONITOR>", "<RESEARCH_FACTORY_INGEST>", ""],
)
def test_placeholder_producers_are_excluded_with_a_derived_reason(producer):
    reason = placeholder_reason(producer)
    assert reason and reason.startswith("derived:")


def test_real_producer_is_not_excluded():
    assert placeholder_reason("engine/a.py") is None


def test_excluded_cells_carry_their_artifacts_so_the_partition_stays_total():
    synapse = _synapse({"a": _artifact(producer="<MANUAL>"), "b": _artifact()})
    registry = build_registry(synapse=synapse)
    assert registry["meta"]["n_artifacts_mapped"] == 2
    assert registry["excluded"][0]["artifacts"] == ["a"]
    assert validate_structure(registry) == []


def test_curated_exclusion_requires_a_reason():
    synapse = _synapse({"a": _artifact()})
    overlay = {"schema_version": 1, "engines": {"engine/a.py::prog": {"not_an_engine": {"reason": ""}}}}
    assert validate_overlay(overlay, ["engine/a.py::prog"])


# ---------------------------------------------------------------------------
# Authority — the C-2 fix
# ---------------------------------------------------------------------------

def test_rule_a_scored_tier_is_gate_size():
    synapse = _synapse({"a": _artifact(tier="scored")})
    assert derive_artifact_authority(synapse)["a"]["authority"] == "gate_size"


def test_rule_b_scored_path_surfaces_is_user_ranking():
    synapse = _synapse({"a": _artifact(scored_path_surfaces=["board_ordering"])})
    got = derive_artifact_authority(synapse)["a"]
    assert got["authority"] == "user_ranking"
    assert got["rule"] == "b"


def test_rule_c_one_hop_into_an_authority_producer_is_engine_input():
    synapse = _synapse(
        {
            "gate": _artifact(producer="engine/gate.py", tier="scored"),
            "feed": _artifact(producer="engine/feed.py", tier="shadow", consumers=["engine/gate.py"]),
        }
    )
    assert derive_artifact_authority(synapse)["feed"]["authority"] == "engine_input"


def test_rule_c_requires_an_evaluated_tier_not_merely_a_hop():
    synapse = _synapse(
        {
            "gate": _artifact(producer="engine/gate.py", tier="scored"),
            "chip": _artifact(producer="engine/chip.py", tier="display", consumers=["engine/gate.py"]),
        }
    )
    assert derive_artifact_authority(synapse)["chip"]["authority"] == "display"


def test_rule_d_default_is_display():
    synapse = _synapse({"a": _artifact()})
    assert derive_artifact_authority(synapse)["a"]["authority"] == "display"


def test_engine_authority_is_the_max_over_its_artifacts():
    assert max_authority(["display", "gate_size", "engine_input"]) == "gate_size"
    assert max_authority(["display", "display"]) == "display"
    assert max_authority([]) == "display"


def test_authority_order_is_a_total_order_low_to_high():
    assert AUTHORITY_ORDER == ("display", "engine_input", "user_ranking", "gate_size")


def test_C2_site_us_standouts_is_not_plain_display(live_synapse):
    """Finding C-2: the Prophet board that orders what a paying user sees carried the
    same `tier: display` as a decorative chip. `authority` must separate them."""
    authority = derive_artifact_authority(live_synapse)
    assert authority["site-us-standouts"]["authority"] == "user_ranking"
    assert authority["site-us-standouts"]["rule"] == "b"
    assert live_synapse["artifacts"]["site-us-standouts"]["tier"] == "display", (
        "the synapse tier is still display — that is the point: authority is a DIFFERENT "
        "field, not a rename of tier"
    )


def test_C2_a_decorative_display_artifact_stays_display(live_synapse):
    authority = derive_artifact_authority(live_synapse)
    display = [a for a, v in authority.items() if v["authority"] == "display"]
    assert len(display) > 100, "authority must not promote everything"


def test_C2_the_two_vol_regime_gates_are_caught_definitionally(live_synapse):
    authority = derive_artifact_authority(live_synapse)
    for artifact_id in ("vol-regime-gate", "vol-regime-basket-overlay-gate"):
        assert authority[artifact_id]["authority"] == "gate_size"
        assert authority[artifact_id]["rule"] == "a", "rule (a) is definitional, not a scan"


def test_completeness_flag_proposes_but_never_promotes():
    """prophet-index: consumed by an Article-2 enforcer with no declared surfaces."""
    synapse = _synapse({"a": _artifact(consumers=["scripts/build_site.py"])})
    registry = build_registry(synapse=synapse, article2_modules=["scripts/build_site.py"])
    row = registry["engines"][0]
    assert row["authority_evidence"]["completeness_flag"] is True
    assert row["authority"] == "display", "the detector must NOT promote authority"


# ---------------------------------------------------------------------------
# evidence_ref — the C-1 fix
# ---------------------------------------------------------------------------

def test_C1_reproduces_on_the_live_registry(live_synapse):
    """Four of the five tier=scored artifacts carry no qual_ladder_ref."""
    scored = {
        aid: entry
        for aid, entry in live_synapse["artifacts"].items()
        if entry.get("tier") == "scored"
    }
    assert set(scored) == {
        "vector-calibration", "hazard-model", "vol-regime-gate",
        "vol-regime-basket-overlay-gate", "site-basket-washout-state",
    }
    without = {aid for aid, e in scored.items() if not e.get("qual_ladder_ref")}
    assert without == {
        "vector-calibration", "hazard-model", "vol-regime-gate",
        "vol-regime-basket-overlay-gate",
    }


def test_evidence_ref_derives_from_qual_ladder_ref_not_from_the_overlay():
    synapse = _synapse({"a": _artifact(tier="scored", qual_ladder_ref="research/P.md")})
    registry = build_registry(synapse=synapse)
    assert registry["engines"][0]["evidence_ref"] == ["research/P.md"]
    assert "evidence_ref" in OVERLAY_FORBIDDEN_KEYS


def test_authority_without_evidence_is_a_content_finding():
    synapse = _synapse({"a": _artifact(tier="scored")})
    registry = build_registry(synapse=synapse)
    codes = {f.code for f in audit_content(registry)}
    assert "AUTHORITY_WITHOUT_EVIDENCE" in codes


def test_display_engine_without_evidence_is_not_a_finding():
    synapse = _synapse({"a": _artifact()})
    registry = build_registry(synapse=synapse)
    codes = {f.code for f in audit_content(registry)}
    assert "AUTHORITY_WITHOUT_EVIDENCE" not in codes


# ---------------------------------------------------------------------------
# Ledger waterfall
# ---------------------------------------------------------------------------

def test_ledger_rule_1_ledger_module_producer():
    synapse = _synapse({"a": _artifact(producer="engine/x_ledger.py", path="data/x_ledger.jsonl")})
    registry = build_registry(synapse=synapse, ledger_modules=["engine/x_ledger.py"])
    assert registry["engines"][0]["ledger_evidence"]["rule"] == 1


def test_ledger_rule_2_resolves_the_desk_by_ast():
    from engine.intelligence_registry import DeskScan

    synapse = _synapse({"a": _artifact()})
    registry = build_registry(
        synapse=synapse,
        desk_scans={"engine/a.py": DeskScan(True, ("mydesk",), False)},
        qledger_desk_rows={"mydesk": 7},
    )
    row = registry["engines"][0]
    assert row["ledger"] == "qledger:mydesk"
    assert row["ledger_evidence"]["corpus_rows"] == 7


def test_ledger_rule_2_zero_row_desk_is_NAMED_not_hidden():
    """Deviation from the brief, deliberate: a zero-row desk keeps its structural
    attribution and is raised as a finding, rather than being silently demoted down the
    waterfall. A registered desk that has never been written is worth naming."""
    from engine.intelligence_registry import DeskScan

    synapse = _synapse({"a": _artifact()})
    registry = build_registry(
        synapse=synapse,
        desk_scans={"engine/a.py": DeskScan(True, ("ghost",), False)},
        qledger_desk_rows={},
    )
    assert registry["engines"][0]["ledger"] == "qledger:ghost"
    assert "LEDGER_DECLARED_BUT_EMPTY" in {f.code for f in audit_content(registry)}


def test_ledger_rule_2_unread_corpus_is_not_an_empty_desk():
    """'Could not look' must never render as 'looked and found nothing'."""
    from engine.intelligence_registry import DeskScan

    synapse = _synapse({"a": _artifact()})
    registry = build_registry(
        synapse=synapse,
        desk_scans={"engine/a.py": DeskScan(True, ("ghost",), False)},
        qledger_desk_rows=None,
    )
    row = registry["engines"][0]
    assert row["ledger_evidence"]["corpus_checked"] is False
    assert row["ledger_evidence"]["corpus_rows"] is None
    assert "LEDGER_DECLARED_BUT_EMPTY" not in {f.code for f in audit_content(registry)}


def test_ledger_rule_3_shadow_tier_artifact():
    synapse = _synapse({"a": _artifact(tier="shadow", path="data/shadow.parquet")})
    registry = build_registry(synapse=synapse)
    assert registry["engines"][0]["ledger_evidence"]["rule"] == 3


def test_ledger_rule_4_hops_cross_program_to_a_grader():
    synapse = _synapse(
        {
            "board": _artifact(
                producer="scripts/build_x.py",
                owner_program="prog-a",
                consumers=["scripts/grade_x.py"],
            ),
            "grades": _artifact(
                producer="scripts/grade_x.py",
                owner_program="prog-b",
                path="data/x_ledger/grades.parquet",
            ),
        }
    )
    registry = build_registry(synapse=synapse)
    row = next(r for r in registry["engines"] if r["producer"] == "scripts/build_x.py")
    assert row["ledger_evidence"]["rule"] == 4
    assert row["ledger_evidence"]["via"] == "scripts/grade_x.py"
    assert row["owner_program"] != "prog-b", "the hop must cross the program boundary"


def test_ledger_rule_5_is_the_literal_string_none_never_null():
    synapse = _synapse({"a": _artifact()})
    assert build_registry(synapse=synapse)["engines"][0]["ledger"] == LEDGER_NONE


def test_live_registry_never_has_a_null_ledger(live_registry):
    assert all(r["ledger"] for r in live_registry["engines"])


def test_us_stocks_prebreakout_binds_through_grade_us_board(live_registry):
    """The cross-program hop the unit of account was chosen to preserve."""
    row = next(
        r for r in live_registry["engines"]
        if r["engine_id"] == "scripts/build_stock_library.py::us-stocks-prebreakout"
    )
    assert row["ledger_evidence"]["rule"] == 4
    assert row["ledger_evidence"]["via"] == "scripts/grade_us_board.py"


# ---------------------------------------------------------------------------
# AST desk scan
# ---------------------------------------------------------------------------

def test_desk_scan_extracts_a_keyword_literal():
    src = "from engine.qledger import register\nregister(desk='alpha')\n"
    scan = scan_producer_source(src)
    assert scan.imports_qledger and scan.desks == ("alpha",)


def test_desk_scan_extracts_a_dict_literal():
    src = 'from engine.qledger import register_batch\nregister_batch([{"desk": "beta"}])\n'
    assert scan_producer_source(src).desks == ("beta",)


def test_desk_scan_flags_an_unresolved_indirect_desk():
    src = "from engine.qledger import register\nD = 'x'\nregister(desk=D)\n"
    scan = scan_producer_source(src)
    assert scan.desks == () and scan.unresolved is True


def test_desk_scan_ignores_a_module_that_does_not_import_qledger():
    assert scan_producer_source("register(desk='alpha')\n").imports_qledger is False


def test_desk_scan_survives_a_syntax_error():
    assert scan_producer_source("def broken(:\n").desks == ()


# ---------------------------------------------------------------------------
# graded_by_design — 100% populated, gap-naming defaults
# ---------------------------------------------------------------------------

def test_graded_yes_when_a_ledger_resolves():
    synapse = _synapse({"a": _artifact(producer="engine/x_ledger.py", path="data/x_ledger.jsonl")})
    registry = build_registry(synapse=synapse, ledger_modules=["engine/x_ledger.py"])
    assert registry["engines"][0]["graded_by_design"] == GRADED_YES


def test_graded_descriptive_when_every_artifact_is_infrastructure():
    synapse = _synapse({"a": _artifact(tier="infrastructure")})
    assert build_registry(synapse=synapse)["engines"][0]["graded_by_design"] == GRADED_DESCRIPTIVE


def test_graded_default_names_the_gap_rather_than_excusing_it():
    synapse = _synapse({"a": _artifact()})
    assert build_registry(synapse=synapse)["engines"][0]["graded_by_design"] == GRADED_NOT_YET


def test_graded_by_design_is_populated_for_every_live_row(live_registry):
    assert all(r["graded_by_design"] for r in live_registry["engines"])


def test_overlay_may_make_the_one_legal_transition():
    synapse = _synapse({"a": _artifact()})
    overlay = {
        "schema_version": 1,
        "engines": {"engine/a.py::prog": {"graded_by_design": {"value": GRADED_DESCRIPTIVE, "reason": "r"}}},
    }
    registry = build_registry(synapse=synapse, overlay=overlay)
    assert registry["engines"][0]["graded_by_design"] == GRADED_DESCRIPTIVE


def test_overlay_cannot_upgrade_a_graded_yes_engine():
    """The overlay may never write 'yes'; and it may not touch a row already 'yes'."""
    synapse = _synapse({"a": _artifact(producer="engine/x_ledger.py", path="data/x_ledger.jsonl")})
    overlay = {
        "schema_version": 1,
        "engines": {"engine/x_ledger.py::prog": {"graded_by_design": {"value": GRADED_DESCRIPTIVE, "reason": "r"}}},
    }
    registry = build_registry(synapse=synapse, overlay=overlay, ledger_modules=["engine/x_ledger.py"])
    assert registry["engines"][0]["graded_by_design"] == GRADED_YES


# ---------------------------------------------------------------------------
# output_class
# ---------------------------------------------------------------------------

def test_output_class_is_not_required_for_a_display_only_engine():
    synapse = _synapse({"a": _artifact()})
    row = build_registry(synapse=synapse)["engines"][0]
    assert row["output_class"] is None
    assert row["output_class_reason"] == "not_required_display_only"


def test_output_class_is_required_once_the_evaluation_gate_trips():
    synapse = _synapse({"a": _artifact(tier="shadow", path="data/s.parquet")})
    row = build_registry(synapse=synapse)["engines"][0]
    assert row["output_class_reason"] == "required_but_uncurated"


def test_output_class_vocabulary_is_the_seven_catalog_classes():
    assert OUTPUT_CLASSES == {
        "predictive", "ranking", "classification_state", "detection_event",
        "descriptive", "salience", "generative",
    }


# ---------------------------------------------------------------------------
# declared_horizon
# ---------------------------------------------------------------------------

def test_declared_horizon_flags_a_mixed_cell():
    synapse = _synapse(
        {
            "a": _artifact(horizon_role="context"),
            "b": _artifact(horizon_role="tactical_entry", path="data/y.json"),
        }
    )
    row = build_registry(synapse=synapse)["engines"][0]
    assert row["declared_horizon"]["horizon_role_homogeneous"] is False
    assert row["declared_horizon"]["horizon_role"] == ["context", "tactical_entry"]


def test_declared_horizon_d_comes_from_the_resolved_desk():
    from engine.intelligence_registry import DeskScan

    synapse = _synapse({"a": _artifact()})
    registry = build_registry(
        synapse=synapse,
        desk_scans={"engine/a.py": DeskScan(True, ("d",), False)},
        qledger_desk_rows={"d": 1},
        qledger_desk_horizons={"d": [63, 5]},
    )
    assert registry["engines"][0]["declared_horizon"]["horizon_d"] == [5, 63]


# ---------------------------------------------------------------------------
# validation_state
# ---------------------------------------------------------------------------

def test_species_none_means_could_not_look_not_phase0():
    assert bind_species("data/x.jsonl", None)["validation_state"] is None


def test_single_bound_species_takes_its_status():
    species = [{"species_id": "S1", "validation_status": "validated",
                "ledger_binding": {"ledger": "us_board_ledger"}}]
    got = bind_species("data/us_board_ledger/grades.parquet", species)
    assert got["validation_state"] == "validated"


def test_multiple_bound_species_take_the_least_advanced():
    species = [
        {"species_id": "S1", "validation_status": "validated", "ledger_binding": {"ledger": "us_board_ledger"}},
        {"species_id": "S2", "validation_status": "phase0", "ledger_binding": {"ledger": "us_board_ledger"}},
    ]
    got = bind_species("data/us_board_ledger/grades.parquet", species)
    assert got["validation_state"] == "phase0"
    assert len(got["bound"]) == 2, "the full set must be recorded as evidence"


def test_a_none_species_binding_binds_to_nothing():
    species = [{"species_id": "X", "validation_status": "falsified",
                "ledger_binding": {"ledger": "none — research verdicts only (pm0_runs)"}}]
    assert bind_species("data/x.jsonl", species)["bound"] == []


def test_no_ledger_defaults_to_phase0_which_asserts_nothing():
    assert bind_species(LEDGER_NONE, [])["validation_state"] == "phase0"


def test_overlay_terminal_ratification_is_applied():
    synapse = _synapse({"a": _artifact(tier="shadow", path="data/s.parquet")})
    overlay = {
        "schema_version": 1,
        "engines": {
            "engine/a.py::prog": {
                "validation_state": {
                    "value": "retired", "dnr_key": "DNR:KILL-X",
                    "ratified_by": "operator", "date": "2026-08-12",
                }
            }
        },
    }
    row = build_registry(synapse=synapse, overlay=overlay, species=[])["engines"][0]
    assert row["validation_state"] == "retired"
    assert row["validation_state_evidence"]["dnr_key"] == "DNR:KILL-X"


# ---------------------------------------------------------------------------
# Overlay contract — the executable form of DNR:KILL-PARALLEL-KNOWLEDGE-BASE
# ---------------------------------------------------------------------------

def test_overlay_allowlist_is_exactly_four_keys():
    assert OVERLAY_ALLOWED_KEYS == {
        "output_class", "graded_by_design", "validation_state", "not_an_engine",
    }


def test_derived_fields_are_all_forbidden_in_the_overlay():
    for field in ("authority", "evidence_ref", "ledger", "producer", "artifacts", "consumers"):
        assert field in OVERLAY_FORBIDDEN_KEYS
    assert not (OVERLAY_ALLOWED_KEYS & OVERLAY_FORBIDDEN_KEYS)


def test_shipped_overlay_is_valid_against_the_live_registry(live_registry):
    overlay = yaml.safe_load(
        (REPO / "config" / "intelligence_registry_overlay.yml").read_text(encoding="utf-8")
    )
    ids = [r["engine_id"] for r in live_registry["engines"]] + [
        r["engine_id"] for r in live_registry["excluded"]
    ]
    assert validate_overlay(overlay, ids) == []


# ---------------------------------------------------------------------------
# Determinism, idempotence, and the structural projection
# ---------------------------------------------------------------------------

def test_build_is_deterministic():
    synapse = _synapse({"b": _artifact(path="data/b.json"), "a": _artifact()})
    assert serialise(build_registry(synapse=synapse)) == serialise(build_registry(synapse=synapse))


def test_engines_are_sorted_by_engine_id():
    synapse = _synapse(
        {"a": _artifact(producer="engine/z.py"), "b": _artifact(producer="engine/a.py", path="data/b.json")}
    )
    ids = [r["engine_id"] for r in build_registry(synapse=synapse)["engines"]]
    assert ids == sorted(ids)


def test_structural_projection_strips_only_the_declared_volatile_paths():
    synapse = _synapse({"a": _artifact()})
    registry = build_registry(synapse=synapse)
    projected = structural_projection(registry)
    row = projected["engines"][0]
    assert "validation_state" not in row
    assert row["authority"] == "display" and row["ledger"] == LEDGER_NONE
    assert "corpus" not in projected["meta"]


def test_a_volatile_only_change_is_not_structural_drift():
    """Otherwise the drift gate is a SCHEDULED RED: data/qledger/claims.jsonl is
    append-only, so the first nightly row on an empty desk would red every open PR."""
    synapse = _synapse({"a": _artifact()})
    a = build_registry(synapse=synapse, species=[])
    b = build_registry(synapse=synapse, species=[])
    b["engines"][0]["validation_state"] = "validated"
    assert structural_projection(a) == structural_projection(b)


def test_a_structural_change_IS_drift():
    synapse = _synapse({"a": _artifact()})
    a = build_registry(synapse=synapse)
    b = build_registry(synapse=_synapse({"a": _artifact(tier="scored")}))
    assert structural_projection(a) != structural_projection(b)


def test_volatile_paths_are_declared_inside_the_artifact():
    synapse = _synapse({"a": _artifact()})
    assert build_registry(synapse=synapse)["meta"]["volatile_fields"] == list(VOLATILE_ENGINE_PATHS)


def test_structural_projection_is_corpus_INDEPENDENT(live_synapse):
    """The load-bearing property the HARD drift law rests on.

    A sparse agent worktree has no data/ on disk, and CI has the full checkout. If the
    structural projection moved with the corpus, the drift gate would report a false red
    in one of those two environments — and the natural "fix" would be to weaken the gate.
    Built against the LIVE synapse so this cannot pass on a toy fixture that happens to
    have no corpus-sourced values.
    """
    from engine.intelligence_registry import DeskScan

    scans = {"scripts/build_whitehouse.py": DeskScan(True, ("whitehouse",), False)}
    with_corpus = build_registry(
        synapse=live_synapse,
        desk_scans=scans,
        species=[{"species_id": "S1", "validation_status": "validated",
                  "ledger_binding": {"ledger": "us_board_ledger"}}],
        qledger_desk_rows={"whitehouse": 88},
        qledger_desk_horizons={"whitehouse": [5, 21]},
    )
    without_corpus = build_registry(synapse=live_synapse, desk_scans=scans)

    assert with_corpus != without_corpus, "the fixture must actually differ before projection"
    assert structural_projection(with_corpus) == structural_projection(without_corpus)


# ---------------------------------------------------------------------------
# scored_path_surfaces is the authority INPUT — it must be value-validated
# ---------------------------------------------------------------------------

def test_synapse_now_validates_scored_path_surfaces_values():
    """C-2's root cause was an unvalidated authority input. `authority: user_ranking`
    derives from this field, so an unchecked value here is the defect class, not the fix."""
    from engine.neuralweb.synapse import validate_registry

    reg = {
        "meta": {
            "schema_version": 1,
            "description": "x",
            "tier_vocabulary": {},
            "article2_surfaces": ["board_ordering", "top_setups"],
        },
        "artifacts": {
            "a": _artifact(producer="engine/neuralweb/synapse.py", scored_path_surfaces=["not_a_surface"]),
        },
    }
    violations = validate_registry(reg, root=REPO)
    assert any("scored_path_surfaces" in v for v in violations)


def test_synapse_accepts_a_valid_scored_path_surface():
    from engine.neuralweb.synapse import validate_registry

    reg = {
        "meta": {
            "schema_version": 1,
            "description": "x",
            "tier_vocabulary": {},
            "article2_surfaces": ["board_ordering", "top_setups"],
        },
        "artifacts": {
            "a": _artifact(producer="engine/neuralweb/synapse.py", scored_path_surfaces=["board_ordering"]),
        },
    }
    assert not [v for v in validate_registry(reg, root=REPO) if "scored_path_surfaces" in v]


def test_scored_path_surfaces_is_still_optional():
    """Requiring the key would demand it on all 642 artifacts and change the existing
    gate's behaviour for every open PR — validate-when-present only."""
    from engine.neuralweb.synapse import _REQUIRED_ARTIFACT_KEYS

    assert "scored_path_surfaces" not in _REQUIRED_ARTIFACT_KEYS


def test_every_live_scored_path_surface_is_a_declared_article2_surface(live_synapse):
    valid = set(live_synapse["meta"]["article2_surfaces"])
    for aid, entry in live_synapse["artifacts"].items():
        for surface in entry.get("scored_path_surfaces") or []:
            assert surface in valid, f"{aid}: {surface!r}"


# ---------------------------------------------------------------------------
# Live registry invariants
# ---------------------------------------------------------------------------

def test_live_registry_passes_its_own_structural_validator(live_registry):
    from engine.species_registry import VALID_VALIDATION_STATUSES

    assert validate_structure(
        live_registry, valid_validation_statuses=VALID_VALIDATION_STATUSES
    ) == []


def test_live_registry_maps_every_synapse_artifact_exactly_once(live_registry, live_synapse):
    seen = set()
    for row in live_registry["engines"]:
        for artifact in row["artifacts"]:
            assert artifact["id"] not in seen
            seen.add(artifact["id"])
    for row in live_registry["excluded"]:
        for aid in row["artifacts"]:
            assert aid not in seen
            seen.add(aid)
    assert seen == set(live_synapse["artifacts"])


def test_every_live_producer_maps_to_an_engine_or_an_exclusion(live_registry, live_synapse):
    producers = {e.get("producer", "") for e in live_synapse["artifacts"].values()}
    mapped = {r["producer"] for r in live_registry["engines"]} | {
        r["producer"] for r in live_registry["excluded"]
    }
    assert producers - mapped == set()


def test_every_live_exclusion_carries_a_non_empty_reason(live_registry):
    assert all(str(r["reason"]).strip() for r in live_registry["excluded"])
