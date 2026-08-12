"""tests/test_intelligence_registry.py — derivation tests for the T1 engine registry.

Covers engine/intelligence_registry.py's pure functions with synthetic input, plus the
two defect fixtures the registry exists to fix (C-1, C-2) asserted against the LIVE
config/synapse.yml. Nothing here touches data/ — the corpus-sourced fields are exercised
with injected values so the suite runs identically in a sparse agent worktree and in CI.
"""
from __future__ import annotations

import copy
import json
from collections import Counter
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
    VOLATILE_META_KEYS,
    assert_no_volatile,
    audit_content,
    audit_corpus,
    bind_species,
    build_registry,
    derive_artifact_authority,
    engine_id_for,
    ledger_shape,
    max_authority,
    partition_artifacts,
    placeholder_reason,
    resolve_qual_ladder_ref,
    scan_producer_source,
    serialise,
    species_token_matches_ledger,
    validate_overlay,
    validate_structure,
    volatile_view,
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
    overlay = {"schema_version": 1, "engines": {"engine/a.py::prog": {"not_an_engine": {"reason": ""}}}}
    assert validate_overlay(overlay, ["engine/a.py::prog"])


# ---------------------------------------------------------------------------
# `not_an_engine` is not a census-deletion hatch
# ---------------------------------------------------------------------------

_GOOD_EXCLUSION = {
    "reason": "this cell is an operational rail with no intelligence output at all",
    "dnr_key": "DNR:KILL-EXAMPLE",
    "ratified_by": "operator",
    "date": "2026-08-12",
}


def _overlay(**row):
    return {"schema_version": 1, "engines": {"engine/a.py::prog": {"not_an_engine": row}}}


def test_a_three_character_reason_can_no_longer_delete_an_engine():
    """MEASURED 2026-08-12 before the fix: two `not_an_engine: {reason: "nah"}` rows took
    the census 378 -> 376, gate_size 5 -> 4, findings 109 -> 106, with validate_overlay()
    and validate_structure() BOTH returning []. The most destructive of the four overlay
    keys was the least gated."""
    assert validate_overlay(_overlay(reason="nah"), ["engine/a.py::prog"])


def test_a_curated_exclusion_needs_the_same_citation_as_a_terminal_ratification():
    for missing in ("ratified_by", "date"):
        row = dict(_GOOD_EXCLUSION)
        row.pop(missing)
        violations = validate_overlay(_overlay(**row), ["engine/a.py::prog"])
        assert any(missing in v for v in violations), missing


def test_a_curated_exclusion_may_not_cite_a_DNR_row_by_number():
    row = dict(_GOOD_EXCLUSION, dnr_key="row 42")
    assert any("DNR:<KEY>" in v for v in validate_overlay(_overlay(**row), ["engine/a.py::prog"]))


def test_a_fully_cited_curated_exclusion_is_accepted():
    assert validate_overlay(_overlay(**_GOOD_EXCLUSION), ["engine/a.py::prog"]) == []


def test_an_authority_bearing_cell_may_not_be_excluded_by_overlay():
    """THE HARD REFUSAL. Even with a perfect citation, the overlay is not a deletion
    hatch: it may not remove a cell that would hold authority over a human."""
    synapse = _synapse({"a": _artifact(tier="scored")})
    registry = build_registry(synapse=synapse, overlay=_overlay(**_GOOD_EXCLUSION))
    assert registry["meta"]["n_engines"] == 0 and registry["meta"]["n_excluded"] == 1
    row = registry["excluded"][0]
    assert row["would_be_authority"] == "gate_size"
    violations = validate_structure(registry)
    assert any("deletion hatch" in v for v in violations), violations


def test_an_evaluated_tier_cell_may_not_be_excluded_by_overlay():
    synapse = _synapse({"a": _artifact(tier="shadow", path="data/s.parquet")})
    registry = build_registry(synapse=synapse, overlay=_overlay(**_GOOD_EXCLUSION))
    assert any("deletion hatch" in v for v in validate_structure(registry))


def test_a_display_only_cell_MAY_be_excluded_by_overlay():
    """The refusal must not be a blanket ban — a genuine judgment exclusion of a
    decorative cell stays legal, otherwise the key is dead rather than gated."""
    synapse = _synapse({"a": _artifact()})
    registry = build_registry(synapse=synapse, overlay=_overlay(**_GOOD_EXCLUSION))
    assert validate_structure(registry) == []


def test_a_DERIVED_placeholder_exclusion_is_exempt_from_the_authority_refusal():
    """A `<PLACEHOLDER>` token is not a repo module — there is no code to hold authority,
    so the refusal would be a false red."""
    synapse = _synapse({"a": _artifact(producer="<MANUAL>", tier="scored")})
    registry = build_registry(synapse=synapse)
    assert registry["excluded"][0]["source"] == "derived"
    assert validate_structure(registry) == []


def test_an_excluded_cell_still_reports_its_content_findings():
    """BELT AND BRACES. Even if the hard refusal were bypassed, an exclusion must not buy
    silence — that is the mechanism that would deflate the C-1/C-2 backlog T1 exists for."""
    synapse = _synapse({"a": _artifact(tier="scored")})
    registry = build_registry(synapse=synapse, overlay=_overlay(**_GOOD_EXCLUSION))
    codes = {f.code for f in audit_content(registry)}
    assert "AUTHORITY_WITHOUT_EVIDENCE" in codes
    assert "OUTPUT_CLASS_MISSING" in codes


def test_an_exclusion_records_what_it_deletes():
    synapse = _synapse({"a": _artifact(tier="scored", path="data/x_ledger.jsonl")})
    row = build_registry(synapse=synapse, overlay=_overlay(**_GOOD_EXCLUSION))["excluded"][0]
    assert row["would_be_authority"] == "gate_size"
    assert row["would_be_tiers"] == ["scored"]
    assert row["would_be_ledger"] == "data/x_ledger.jsonl"
    assert row["would_be_output_class_reason"] == "required_but_uncurated"


def test_the_live_overlay_carries_ZERO_curated_exclusions(live_registry):
    """THE RATCHET. Derived (placeholder) exclusions are fine; the FIRST curated one must
    be a deliberate reviewed act rather than a diff nobody reads."""
    curated = [r for r in live_registry["excluded"] if r["source"] == "curated"]
    assert curated == [], curated
    assert all(r["source"] == "derived" for r in live_registry["excluded"])


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


def test_C1_gate_is_NOT_cleared_by_a_display_siblings_reference():
    """THE BLOCKER. `evidence_ref` is the UNION of qual_ladder_ref over the cell, so an
    unevidenced gate_size artifact went unflagged whenever ANY sibling — including a
    decorative display one — carried any ref. Reproduced live on
    scripts/build_basket_washout_state.py::blocked-entry-override 2026-08-12."""
    synapse = _synapse(
        {
            "gate": _artifact(tier="scored", path="data/gate.json"),           # no ref
            "chip": _artifact(tier="display", path="site/chip.json",
                              qual_ladder_ref="research/UNRELATED_DISPLAY_NOTE.md"),
        }
    )
    registry = build_registry(
        synapse=synapse, qual_ladder_keys=set(), path_exists=lambda p: True
    )
    row = registry["engines"][0]
    assert row["authority"] == "gate_size"
    assert row["evidence_ref"] == ["research/UNRELATED_DISPLAY_NOTE.md"], (
        "the union is non-empty — that is exactly the condition that used to silence C-1"
    )
    assert row["authority_evidence"]["unevidenced_artifacts"] == ["gate"]
    assert "AUTHORITY_WITHOUT_EVIDENCE" in {f.code for f in audit_content(registry)}


def test_C1_gate_is_NOT_cleared_by_a_pointer_at_a_nonexistent_file():
    """A ref that resolves to neither a config/qual_ladder.yml key nor an existing repo
    path is a string, not evidence. Without this the C-1 backlog is drainable to zero
    without a single real prereg."""
    synapse = _synapse({"a": _artifact(tier="scored", qual_ladder_ref="lol/does_not_exist.md")})
    registry = build_registry(
        synapse=synapse, qual_ladder_keys={"altdata.action"}, path_exists=lambda p: False
    )
    row = registry["engines"][0]
    assert row["artifacts"][0]["qual_ladder_ref_resolution"] == "unresolved"
    assert row["evidence_ref"] is None, "an unresolvable ref must not roll up as evidence"
    codes = {f.code for f in audit_content(registry)}
    assert "AUTHORITY_WITHOUT_EVIDENCE" in codes
    assert "AUTHORITY_EVIDENCE_UNRESOLVABLE" in codes, (
        "'no pointer' and 'pointer at nothing' need different heals"
    )


@pytest.mark.parametrize(
    "ref,keys,exists,expected",
    [
        (None, set(), False, None),
        ("", set(), False, None),
        ("   ", set(), False, None),
        ("altdata.action", {"altdata.action"}, False, "qual_ladder_key"),
        ("research/P.md", set(), True, "repo_path"),
        ("lol/nope.md", {"altdata.action"}, False, "unresolved"),
    ],
)
def test_resolve_qual_ladder_ref(ref, keys, exists, expected):
    assert resolve_qual_ladder_ref(
        ref, qual_ladder_keys=keys, path_exists=lambda p: exists
    ) == expected


def test_resolve_qual_ladder_ref_without_a_probe_is_unchecked():
    assert resolve_qual_ladder_ref("research/P.md") == "unchecked"
    assert resolve_qual_ladder_ref("research/P.md", qual_ladder_keys={"x"}) == "unchecked"
    assert resolve_qual_ladder_ref(None) is None, "no ref at all is still None, not 'unchecked'"


def test_an_UNPROBED_ref_is_never_reported_as_unresolvable():
    """Sparse worktrees are the norm here. A builder that could not probe must say so,
    never accuse — 'could not look' is not 'looked and found nothing'."""
    synapse = _synapse({"a": _artifact(tier="scored", qual_ladder_ref="research/P.md")})
    registry = build_registry(synapse=synapse)  # no qual_ladder_keys, no path_exists
    assert registry["engines"][0]["artifacts"][0]["qual_ladder_ref_resolution"] == "unchecked"
    assert "AUTHORITY_EVIDENCE_UNRESOLVABLE" not in {f.code for f in audit_content(registry)}


def test_the_C1_heal_names_EVERY_unevidenced_artifact_not_just_the_first():
    """The heal used to name `authority_evidence.artifact_id` — the first sorted winner —
    so for us-stocks-prebreakout it named site-signal-gate rather than site-us-standouts,
    the artifact the whole C-2 defect statement is about."""
    synapse = _synapse(
        {
            "site-signal-gate": _artifact(scored_path_surfaces=["board_ordering"], path="site/g.json"),
            "site-us-standouts": _artifact(scored_path_surfaces=["top_setups"], path="site/s.json"),
        }
    )
    registry = build_registry(synapse=synapse)
    row = registry["engines"][0]
    assert row["authority_evidence"]["artifact_ids"] == ["site-signal-gate", "site-us-standouts"]
    detail = next(
        f.detail for f in audit_content(registry) if f.code == "AUTHORITY_WITHOUT_EVIDENCE"
    )
    assert "site-us-standouts" in detail and "site-signal-gate" in detail


def test_live_C1_and_resolvability_counts_are_pinned(live_registry):
    """The honest before/after. The artifact-level gate and the resolvability probe were
    both measured to add ZERO findings on arrival — which is what let them ship without
    reddening the fleet. Pinned so a future change to either has to state its own count."""
    findings = audit_content(live_registry)
    c1 = [f for f in findings if f.code == "AUTHORITY_WITHOUT_EVIDENCE"]
    unresolvable = [f for f in findings if f.code == "AUTHORITY_EVIDENCE_UNRESOLVABLE"]
    assert len(c1) == 21, [f.engine_id for f in c1]
    assert unresolvable == [], "all 10 live qual_ladder_ref values resolved on 2026-08-12"
    resolutions = Counter(
        a["qual_ladder_ref_resolution"]
        for r in live_registry["engines"]
        for a in r["artifacts"]
        if a["qual_ladder_ref"]
    )
    assert resolutions == Counter({"qual_ladder_key": 9, "repo_path": 1}), resolutions


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
    )
    row = registry["engines"][0]
    assert row["ledger"] == "qledger:mydesk"
    # The ROW COUNT is not here. It is a function of an append-only store, so committing
    # it would pin a nightly-moving value by equality — a scheduled fleet-wide red.
    assert "corpus_rows" not in row["ledger_evidence"]
    view = volatile_view(registry, qledger_desk_rows={"mydesk": 7})
    assert view["engines"]["engine/a.py::prog"]["corpus_rows"] == 7


def test_ledger_rule_2_zero_row_desk_is_NAMED_not_hidden():
    """Deviation from the brief, deliberate: a zero-row desk keeps its structural
    attribution and is raised as a finding, rather than being silently demoted down the
    waterfall. A registered desk that has never been written is worth naming."""
    from engine.intelligence_registry import DeskScan

    synapse = _synapse({"a": _artifact()})
    registry = build_registry(
        synapse=synapse,
        desk_scans={"engine/a.py": DeskScan(True, ("ghost",), False)},
    )
    assert registry["engines"][0]["ledger"] == "qledger:ghost"
    codes = {
        f.code for f in audit_corpus(registry, volatile_view(registry, qledger_desk_rows={}))
    }
    assert "LEDGER_DECLARED_BUT_EMPTY" in codes


def test_ledger_rule_2_unread_corpus_is_not_an_empty_desk():
    """'Could not look' must never render as 'looked and found nothing'."""
    from engine.intelligence_registry import DeskScan

    synapse = _synapse({"a": _artifact()})
    registry = build_registry(
        synapse=synapse,
        desk_scans={"engine/a.py": DeskScan(True, ("ghost",), False)},
    )
    view = volatile_view(registry, qledger_desk_rows=None)
    state = view["engines"]["engine/a.py::prog"]
    assert state["corpus_checked"] is False and state["corpus_rows"] is None
    assert audit_corpus(registry, view) == []


# ---------------------------------------------------------------------------
# The ledger must be a STORE, not any path with 'ledger' in its name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path,shape",
    [
        ("data/x_ledger.jsonl", "store"),
        ("data/metabolism/agenda/", "store"),
        ("data/x/board.parquet", "store"),
        ("engine/demand_ledger.py", "not_a_store"),
        ("config/lobe_charters.yml", "not_a_store"),
        ("options_structure/structural/<ROOT>.json", "template"),
        ("capital_structure/share_counts/v2/generations/*/ledger.json", "template"),
        ("", "not_a_store"),
    ],
)
def test_ledger_shape_classification(path, shape):
    assert ledger_shape(path) == shape


def test_a_ledger_module_with_no_store_is_not_its_own_ledger():
    """The deleted `else producer` fallback. A Python module cannot hold a graded row, so
    an engine/*_ledger.py producer with no ledger-shaped artifact must fall THROUGH."""
    synapse = _synapse({"a": _artifact(producer="engine/x_ledger.py", path="site/chip.json")})
    row = build_registry(synapse=synapse, ledger_modules=["engine/x_ledger.py"])["engines"][0]
    assert row["ledger"] == LEDGER_NONE
    assert row["graded_by_design"] == GRADED_NOT_YET


def test_rule_4_cannot_hop_onto_a_python_module():
    """scripts/seed_us_sector_baskets.py::sector-pulse was "graded by" engine/demand_ledger.py."""
    synapse = _synapse(
        {
            "board": _artifact(producer="scripts/build_x.py", consumers=["engine/demand_ledger.py"]),
            "mod": _artifact(
                producer="engine/demand_ledger.py", owner_program="other",
                path="engine/demand_ledger.py",
            ),
        }
    )
    row = next(
        r for r in build_registry(
            synapse=synapse, ledger_modules=["engine/demand_ledger.py"]
        )["engines"] if r["producer"] == "scripts/build_x.py"
    )
    assert row["ledger"] == LEDGER_NONE


def test_a_template_ledger_does_not_earn_graded_by_design_yes():
    """An unexpanded glob names a FAMILY of stores. It cannot be opened, so it is not
    evidence that grading happens — and it must not manufacture its own contradiction
    finding either."""
    synapse = _synapse({"a": _artifact(tier="shadow", path="data/oracle/fwd/<id>.jsonl")})
    row = build_registry(synapse=synapse)["engines"][0]
    assert row["ledger"] == "data/oracle/fwd/<id>.jsonl"
    assert row["ledger_evidence"]["shape"] == "template"
    assert row["graded_by_design"] == GRADED_NOT_YET
    assert "GRADED_BY_DESIGN_CONTRADICTS_LEDGER" not in {f.code for f in audit_content(build_registry(synapse=synapse))}


def test_a_graded_engine_still_needs_a_metric_contract():
    """26 engines with graded_by_design='yes' were recorded 'not_required_display_only'
    because the gate keyed on authority and tier but never on the derived ledger."""
    synapse = _synapse({"a": _artifact(tier="display", path="data/prophet/ledger.jsonl")})
    row = build_registry(synapse=synapse)["engines"][0]
    assert row["graded_by_design"] == GRADED_YES
    assert row["output_class_reason"] == "required_but_uncurated"


def test_the_graded_yes_engines_that_LOST_their_ledger_are_pinned_by_name(live_registry):
    """SHRINK-DIRECTION CONTROL. graded_by_design='yes' moved 112 -> 106 when the store
    test landed. A detector that quietly shrinks is a detector going blind, so the exact
    set that moved is pinned: five non-stores plus one .py rule-4 hop."""
    by_id = {r["engine_id"]: r for r in live_registry["engines"]}
    for eid, expected_ledger in (
        ("engine/metabolism/lobe_registry.py::metabolism-phase-v2c", LEDGER_NONE),
        ("scripts/seed_us_sector_baskets.py::sector-pulse", LEDGER_NONE),
        ("engine/neuralweb/reflexes.py::neural-web", "data/reflexes/<NAME>/firings.jsonl"),
        ("engine/options_structure.py::momoedge", "options_structure/structural/<ROOT>.json"),
        (
            "scripts/materialize_capital_structure_share_counts.py::capital-structure-intelligence",
            "capital_structure/share_counts/v2/generations/*/ledger.json",
        ),
        ("scripts/oracle_reversion_forward_ledger.py::oracle", "data/oracle/reversion_forward/<compound_id>.jsonl"),
    ):
        assert by_id[eid]["ledger"] == expected_ledger, eid
        assert by_id[eid]["graded_by_design"] != GRADED_YES, eid

    # And the three engine/*_ledger.py SELF-REFERENCES now resolve a REAL store rather
    # than their own source file — they must NOT have been shrunk away.
    for eid, expected in (
        ("engine/altdata_ledger.py::qualitative-intelligence", "data/altdata/theses.jsonl"),
        ("engine/demand_ledger.py::qualitative-intelligence", "data/demand_chain/theses.jsonl"),
        ("engine/cn_reversal_sleeve_ledger.py::china-alpha", "data/cn_reversal_sleeve_track/sleeve.parquet"),
    ):
        assert by_id[eid]["ledger"] == expected, eid
        assert by_id[eid]["graded_by_design"] == GRADED_YES, eid


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


def test_declared_horizon_d_is_computed_at_READ_time_not_committed():
    from engine.intelligence_registry import DeskScan

    synapse = _synapse({"a": _artifact()})
    registry = build_registry(
        synapse=synapse, desk_scans={"engine/a.py": DeskScan(True, ("d",), False)}
    )
    assert "horizon_d" not in registry["engines"][0]["declared_horizon"]
    view = volatile_view(registry, qledger_desk_horizons={"d": [63, 5]})
    assert view["engines"]["engine/a.py::prog"]["horizon_d"] == [5, 63]


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


@pytest.mark.parametrize(
    "token,ledger,expected",
    [
        # The 5 live binds, by shape. All must survive the anchoring.
        ("us_board_ledger", "data/us_board_ledger/retro_grades.parquet", True),
        ("china_standout_track", "data/china_standout_track/board.parquet", True),
        ("data/trial_ledger.jsonl", "data/trial_ledger.jsonl", True),
        ("trial_ledger", "data/trial_ledger.jsonl", True),
        ("whitehouse", "qledger:whitehouse", True),
        # ...and the over-binding the unanchored substring rule allowed.
        ("board", "data/us_board_ledger/retro_grades.parquet", False),
        ("ledger", "data/anything_ledger.jsonl", False),
        # the store ROOT is not a binding token — it would bind one species to everything
        ("data", "data/x/y.parquet", False),
        ("site", "site/factordata/x.json", False),
    ],
)
def test_species_binding_is_anchored_not_substring(token, ledger, expected):
    """The old rule was `token in engine_ledger or engine_ledger in token` — the same
    fuzzy class the overlay comment correctly refuses for DNR-to-engine mapping."""
    assert species_token_matches_ledger(token, ledger) is expected


def test_the_live_species_binds_are_pinned_by_name(live_registry):
    """SHRINK-DIRECTION CONTROL for the anchoring above. A matcher that quietly binds
    fewer things reads exactly like a matcher getting stricter."""
    bound = {
        r["engine_id"]: sorted(b["species_id"] for b in r["validation_state_evidence"]["bound_species"])
        for r in live_registry["engines"]
        if r["validation_state_evidence"]["bound_species"]
    }
    assert set(bound) == {
        "engine/china_standout_track.py::china-alpha",              # 4 species
        "engine/trial_ledger.py::engine-fix",                       # 1
        "scripts/build_stock_library.py::us-stocks-prebreakout",    # 17
        "scripts/grade_us_board.py::setup-species",                 # 17
        "scripts/grade_us_board.py::standout-accountability",       # 17
    }, bound


def test_unbound_species_are_NAMED_not_dropped(live_registry):
    """The inverse of bind_species had no check at all: a species matching no engine was
    dropped in silence. Both live cases are `accruing`, on the axis the
    display-only-until-validated law hangs on."""
    unbound = live_registry["meta"]["unbound_species"]
    assert [r["species_id"] for r in unbound] == ["EI-F1D-RW", "F3_ANTICHASE"], unbound
    assert all(r["validation_status"] == "accruing" for r in unbound)
    assert len([f for f in audit_content(live_registry) if f.code == "SPECIES_UNBOUND"]) == 2


def test_an_unread_species_store_reports_null_unbound_not_empty():
    registry = build_registry(synapse=_synapse({"a": _artifact()}), species=None)
    assert registry["meta"]["unbound_species"] is None
    assert "SPECIES_UNBOUND" not in {f.code for f in audit_content(registry)}


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


def test_a_freshly_built_registry_carries_NO_corpus_derived_path():
    synapse = _synapse({"a": _artifact()})
    assert assert_no_volatile(build_registry(synapse=synapse)) == []


@pytest.mark.parametrize("dotted", VOLATILE_ENGINE_PATHS)
def test_assert_no_volatile_catches_each_declared_path(dotted):
    """The absence contract must be able to FAIL, path by path. A guard that asserts an
    absence it cannot detect is decorative."""
    registry = build_registry(synapse=_synapse({"a": _artifact()}))
    head, _, rest = dotted.partition(".")
    row = registry["engines"][0]
    if rest:
        row.setdefault(head, {})[rest] = 88
    else:
        row[head] = 88
    assert assert_no_volatile(registry) != []


@pytest.mark.parametrize("key", VOLATILE_META_KEYS)
def test_assert_no_volatile_catches_each_declared_meta_key(key):
    registry = build_registry(synapse=_synapse({"a": _artifact()}))
    registry["meta"][key] = {"anything": True}
    assert assert_no_volatile(registry) != []


def test_the_absence_contract_is_part_of_the_HARD_structural_validator():
    """Not a separate opt-in check — a committed corpus-derived field must red law A."""
    registry = build_registry(synapse=_synapse({"a": _artifact()}))
    registry["engines"][0]["ledger_evidence"]["corpus_rows"] = 88
    assert any("corpus_rows" in v for v in validate_structure(registry))


def test_validation_state_is_STABLE_and_therefore_equality_guarded():
    """It used to sit in VOLATILE_ENGINE_PATHS and be STRIPPED before comparing, so a
    hand-edit of the display-only-until-validated axis produced byte-identical guard
    output. data/species/registry.json has ONE commit in the repo's history and no
    automated writer, so it is stable and belongs in the comparison."""
    assert "validation_state" not in VOLATILE_ENGINE_PATHS
    assert "validation_state_evidence" not in VOLATILE_ENGINE_PATHS
    registry = build_registry(synapse=_synapse({"a": _artifact()}), species=[])
    tampered = copy.deepcopy(registry)
    tampered["engines"][0]["validation_state"] = "validated"
    assert serialise(tampered) != serialise(registry)


def test_the_absence_contract_is_declared_inside_the_artifact():
    registry = build_registry(synapse=_synapse({"a": _artifact()}))
    assert registry["meta"]["volatile_fields_excluded"] == list(VOLATILE_ENGINE_PATHS)
    assert registry["meta"]["volatile_meta_keys_excluded"] == list(VOLATILE_META_KEYS)


def test_the_committed_artifact_is_corpus_INDEPENDENT(live_synapse):
    """The load-bearing property the HARD drift law rests on, now stated as an identity
    rather than a projection: the builder is not even GIVEN the claim corpus, so no
    nightly append can move a byte of the committed file.

    Built against the LIVE synapse so this cannot pass on a toy fixture that happens to
    have no corpus-sourced values.
    """
    from engine.intelligence_registry import DeskScan
    import inspect

    scans = {"scripts/build_whitehouse.py": DeskScan(True, ("whitehouse",), False)}
    params = set(inspect.signature(build_registry).parameters)
    assert "qledger_desk_rows" not in params and "qledger_desk_horizons" not in params, (
        "the claim corpus must not be an input to the committed artifact at all"
    )
    registry = build_registry(synapse=live_synapse, desk_scans=scans)
    assert assert_no_volatile(registry) == []

    # ...and the read-time view genuinely moves with the corpus, so the information was
    # relocated rather than deleted.
    a = volatile_view(registry, qledger_desk_rows={"whitehouse": 88})
    b = volatile_view(registry, qledger_desk_rows={"whitehouse": 89})
    assert a != b


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
# THE SCHEDULED RED — a nightly corpus append must move NOTHING that is pinned
# ---------------------------------------------------------------------------

def _with_appended_claims(monkeypatch, extra_rows):
    """Point the builder at a corpus with `extra_rows` appended, as a nightly lane would."""
    import scripts.build_intelligence_registry as builder

    original = builder._read_tracked_uncached

    def patched(root, rel):
        text, source = original(root, rel)
        if rel == builder.CLAIMS_REL and text is not None:
            text = text + "".join(json.dumps(r) + "\n" for r in extra_rows)
        return text, source

    builder._READ_CACHE.clear()
    monkeypatch.setattr(builder, "_read_tracked_uncached", patched)
    return builder


def test_a_nightly_corpus_APPEND_stales_NOTHING_that_is_pinned(monkeypatch):
    """B-RED, the blocker. `data/qledger/claims.jsonl` is append-only — 13 automated
    commits in 14 days — and the committed registry used to carry `corpus_rows`, pinned by
    equality through `--check` and through the CI-wired
    tests/test_check_intelligence_registry.py::test_builder_check_mode_reports_no_drift.
    So main went red daily for a property no PR author caused.

    This simulates two nightly appends at once: one more row on the EXISTING whitehouse
    desk (the field that used to be pinned at 88), and a row opening a BRAND NEW desk (the
    field that used to be pinned at n_desks=13, and which the deleted doc line printed).
    Neither the artifact nor the doc may move by a single byte.
    """
    import scripts.build_intelligence_registry as builder

    builder._READ_CACHE.clear()
    before_registry, before_report = builder.build(REPO)
    before_doc = builder.render_doc(before_registry, audit_content(before_registry))

    try:
        _with_appended_claims(
            monkeypatch,
            [
                {"desk": "whitehouse", "horizon_d": 999, "direction": 1},
                {"desk": "brand_new_desk_2026", "horizon_d": 21, "direction": 1},
            ],
        )
        after_registry, after_report = builder.build(REPO)
        after_doc = builder.render_doc(after_registry, audit_content(after_registry))
    finally:
        builder._READ_CACHE.clear()

    # The append must be REAL, or this test proves nothing.
    assert (
        after_report["qledger_desk_rows"]["whitehouse"]
        == before_report["qledger_desk_rows"]["whitehouse"] + 1
    )
    assert len(after_report["qledger_desk_rows"]) == len(before_report["qledger_desk_rows"]) + 1

    assert serialise(after_registry) == serialise(before_registry), (
        "a nightly claim append moved the committed artifact — that is a scheduled "
        "fleet-wide red"
    )
    assert after_doc == before_doc, (
        "a nightly claim append moved the generated doc, which the HARD law pins "
        "byte-for-byte"
    )

    # The information is RELOCATED, not deleted: the read-time view sees the append.
    before_view = volatile_view(
        before_registry,
        qledger_desk_rows=before_report["qledger_desk_rows"],
        qledger_desk_horizons=before_report["qledger_desk_horizons"],
    )
    after_view = volatile_view(
        after_registry,
        qledger_desk_rows=after_report["qledger_desk_rows"],
        qledger_desk_horizons=after_report["qledger_desk_horizons"],
    )
    assert after_view != before_view


def test_a_species_promotion_DOES_move_the_artifact_because_it_is_PR_caused(monkeypatch):
    """The other direction, and the reason `hard` severity is legitimate. Registering a
    species is a PR-authored act on a store with ONE commit in the repo's history, so its
    heal is one command on the PR that caused it. A drift guard SHOULD catch that."""
    import scripts.build_intelligence_registry as builder

    builder._READ_CACHE.clear()
    before, _ = builder.build(REPO)
    original = builder._read_tracked_uncached

    def patched(root, rel):
        text, source = original(root, rel)
        if rel == builder.SPECIES_REL and text is not None:
            payload = json.loads(text)
            payload["species"].append(
                {
                    "species_id": "SYNTHETIC_TEST_SPECIES",
                    "validation_status": "accruing",
                    "ledger_binding": {"ledger": "us_board_ledger"},
                }
            )
            text = json.dumps(payload)
        return text, source

    try:
        builder._READ_CACHE.clear()
        monkeypatch.setattr(builder, "_read_tracked_uncached", patched)
        after, _ = builder.build(REPO)
    finally:
        builder._READ_CACHE.clear()

    assert serialise(after) != serialise(before)


# ---------------------------------------------------------------------------
# Sparse-worktree correctness — "could not look" is never "looked and found nothing"
# ---------------------------------------------------------------------------

def test_producer_source_is_read_through_the_sparse_ladder(monkeypatch):
    """`_scan_producers` read the working tree only and skipped a missing file with a
    silent `continue`. Under a sparse cone that loses ledger-waterfall rule 2 and builds a
    STRUCTURALLY different registry than CI — which the byte-exact gate then reports as
    drift, with nothing in the log saying a producer could not be read."""
    import scripts.build_intelligence_registry as builder

    seen: list[str] = []
    original = builder.read_tracked

    def spy(root, rel):
        seen.append(rel.as_posix())
        return original(root, rel)

    monkeypatch.setattr(builder, "read_tracked", spy)
    scans, unresolved, unreadable = builder._scan_producers(REPO, {"scripts/build_whitehouse.py"})
    assert "scripts/build_whitehouse.py" in seen, "the producer must go through read_tracked"
    assert "scripts/build_whitehouse.py" in scans


def test_an_unreadable_producer_is_COUNTED_not_silently_skipped():
    import scripts.build_intelligence_registry as builder

    scans, unresolved, unreadable = builder._scan_producers(
        REPO, {"engine/this_module_does_not_exist_anywhere.py"}
    )
    assert unreadable == ["engine/this_module_does_not_exist_anywhere.py"]
    assert scans == {}


def test_the_ledger_module_inventory_survives_a_sparse_cone():
    """A working-tree-only glob would report the inventory EMPTY under a sparse cone and
    silently change every ledger derivation."""
    import scripts.build_intelligence_registry as builder

    modules = builder._ledger_modules(REPO)
    assert len(modules) >= 14
    assert all(m.startswith("engine/") and m.endswith("_ledger.py") for m in modules)


def test_qual_ladder_ref_paths_are_probed_through_the_sparse_ladder():
    """os.path.exists() would call a tracked-but-absent prereg missing and fire
    AUTHORITY_EVIDENCE_UNRESOLVABLE on it — the exact bug class this fix closes,
    reproduced inside the fix."""
    import scripts.build_intelligence_registry as builder

    probe = builder._make_path_exists(REPO)
    assert probe("config/synapse.yml") is True
    assert probe("research/lol_does_not_exist_anywhere.md") is False
    assert probe("/etc/passwd") is False, "absolute paths must never resolve"
    assert probe("../../../etc/passwd") is False, "traversal must never resolve"


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
