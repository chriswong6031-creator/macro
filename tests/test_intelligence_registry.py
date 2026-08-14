"""tests/test_intelligence_registry.py — derivation tests for the T1 engine registry.

SYNTHETIC INPUT ONLY, WITH ONE DELIBERATE EXCEPTION
---------------------------------------------------
Every behavioural assertion here runs against a hand-built fixture. Nothing asserts on the
CONTENTS of config/synapse.yml, data/qledger/, data/species/ or config/qual_ladder.yml,
because none of those is stable: synapse.yml took 26 commits in 14 days and the claim store
is append-only. A test that pinned "site-us-standouts is user_ranking" or "C-1 is 21
engines" would red main the moment a sibling PR added an artifact — an event no PR author
on THIS lane caused. Two earlier rounds shipped exactly that scheduled red, first as a
committed artifact pinned by equality and then as counts pinned in this file.

The exception is §LIVE INPUTS at the bottom. Those tests run the builder over the real
tree and assert only that it does not crash and returns a WELL-FORMED structure — no count,
no name, no value. Two of them simulate the volatility directly: a synthetic claim append
and a synthetic synapse artifact, each asserting the derivation stays structurally valid.

Nothing here reads data/ from the worktree; the sparse-cone ladder is exercised through the
builder's own probes.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from engine.intelligence_registry import (
    AUTHORITY_ORDER,
    GRADED_DESCRIPTIVE,
    GRADED_EVIDENCE_NONE,
    GRADED_EVIDENCE_STRONG,
    GRADED_EVIDENCE_WEAK,
    GRADED_NOT_YET,
    GRADED_YES,
    LEDGER_NONE,
    OUTPUT_CLASSES,
    OVERLAY_ALLOWED_KEYS,
    OVERLAY_FORBIDDEN_KEYS,
    SCHEMA,
    DeskScan,
    audit_content,
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
)

REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fixtures — synthetic
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


def _codes(registry):
    return {f.code for f in audit_content(registry)}


# ---------------------------------------------------------------------------
# NOTHING IS COMMITTED — the architecture, asserted as a property of the repo
# ---------------------------------------------------------------------------

def test_no_generated_registry_artifact_is_tracked():
    """THE ROUND-3 ARCHITECTURE, AS A TEST. Two earlier rounds committed a generated
    data/intelligence_registry.json and a generated Markdown mirror and pinned them by
    equality against a 'stable' input. Both were scheduled fleet-wide reds; the pin merely
    RELOCATED between rounds (claims.jsonl -> synapse.yml, 13 and 26 commits in 14 days).
    There is no stable input on this repo to pin against, so nothing generated is tracked.
    """
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files", "data/intelligence_registry.json",
         "docs/MASTERMIND_INTELLIGENCE_REGISTRY.md"],
        cwd=REPO, capture_output=True, text=True, check=False,
    ).stdout.split()
    assert tracked == [], f"a generated registry artifact is tracked again: {tracked}"


def test_the_builder_has_no_check_equality_mode():
    """`--check` was the pin's executable form. Its absence is what makes the guard
    un-reddenable by a nightly append, so it is asserted rather than assumed."""
    import scripts.build_intelligence_registry as builder

    source = Path(builder.__file__).read_text(encoding="utf-8")
    assert '"--check"' not in source and "'--check'" not in source


def test_the_module_writes_no_files():
    import engine.intelligence_registry as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("write_text(", "open(", "os.makedirs", "mkdir("):
        assert forbidden not in source, f"the pure module performs I/O: {forbidden}"


# ---------------------------------------------------------------------------
# Unit of account — the partition must be TOTAL and DISJOINT
# ---------------------------------------------------------------------------

def test_engine_id_is_producer_then_owner_program():
    assert engine_id_for("engine/a.py", "prog") == "engine/a.py::prog"


def test_two_programs_on_one_producer_are_two_engines():
    synapse = _synapse({"a": _artifact(owner_program="p1"), "b": _artifact(owner_program="p2")})
    assert set(partition_artifacts(synapse)) == {"engine/a.py::p1", "engine/a.py::p2"}


def test_owner_program_span_counts_cross_program_producers():
    synapse = _synapse({"a": _artifact(owner_program="p1"), "b": _artifact(owner_program="p2")})
    registry = build_registry(synapse=synapse)
    assert {r["owner_program_span"] for r in registry["engines"]} == {2}


def test_the_partition_is_total_over_a_synthetic_corpus():
    synapse = _synapse(
        {
            "a": _artifact(),
            "b": _artifact(producer="engine/b.py"),
            "c": _artifact(producer="<MANUAL>"),
        }
    )
    registry = build_registry(synapse=synapse)
    assert registry["meta"]["n_artifacts"] == 3
    assert registry["meta"]["n_artifacts_mapped"] == 3
    assert validate_structure(registry) == []


def test_a_dropped_artifact_is_a_structural_violation():
    """The partition invariant must be able to FAIL, or it is decorative."""
    registry = build_registry(synapse=_synapse({"a": _artifact(), "b": _artifact(producer="engine/b.py")}))
    registry["engines"][0]["artifacts"] = []
    assert any("partition is not total" in v for v in validate_structure(registry))


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
    the census 378 -> 376 and gate_size 5 -> 4 with validate_overlay() and
    validate_structure() BOTH returning []. The most destructive of the four overlay keys
    was the least gated."""
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
    assert registry["excluded"][0]["would_be_authority"] == "gate_size"
    assert any("deletion hatch" in v for v in validate_structure(registry))


def test_an_evaluated_tier_cell_may_not_be_excluded_by_overlay():
    synapse = _synapse({"a": _artifact(tier="shadow", path="data/s.parquet")})
    registry = build_registry(synapse=synapse, overlay=_overlay(**_GOOD_EXCLUSION))
    assert any("deletion hatch" in v for v in validate_structure(registry))


def test_a_display_only_cell_MAY_be_excluded_by_overlay():
    """The refusal must not be a blanket ban — a genuine judgment exclusion of a
    decorative cell stays legal, otherwise the key is dead rather than gated."""
    registry = build_registry(synapse=_synapse({"a": _artifact()}), overlay=_overlay(**_GOOD_EXCLUSION))
    assert validate_structure(registry) == []


def test_a_DERIVED_placeholder_exclusion_is_exempt_from_the_authority_refusal():
    """A `<PLACEHOLDER>` token is not a repo module — there is no code to hold authority,
    so the refusal would be a false red."""
    registry = build_registry(synapse=_synapse({"a": _artifact(producer="<MANUAL>", tier="scored")}))
    assert registry["excluded"][0]["source"] == "derived"
    assert validate_structure(registry) == []


def test_an_excluded_cell_still_reports_its_content_findings():
    """BELT AND BRACES. Even if the hard refusal were bypassed, an exclusion must not buy
    silence — that is the mechanism that would deflate the C-1/C-2 backlog T1 exists for."""
    synapse = _synapse({"a": _artifact(tier="scored")})
    codes = _codes(build_registry(synapse=synapse, overlay=_overlay(**_GOOD_EXCLUSION)))
    assert "AUTHORITY_WITHOUT_EVIDENCE" in codes
    assert "OUTPUT_CLASS_MISSING" in codes
    assert "ENGINE_EXCLUDED_BY_OVERLAY" in codes


def test_an_exclusion_records_what_it_deletes():
    synapse = _synapse({"a": _artifact(tier="scored", path="data/x_ledger.jsonl")})
    row = build_registry(synapse=synapse, overlay=_overlay(**_GOOD_EXCLUSION))["excluded"][0]
    assert row["would_be_authority"] == "gate_size"
    assert row["would_be_tiers"] == ["scored"]
    assert row["would_be_ledger"] == "data/x_ledger.jsonl"
    assert row["would_be_output_class_reason"] == "required_but_uncurated"


# ---------------------------------------------------------------------------
# Authority — the C-2 fix
# ---------------------------------------------------------------------------

def test_rule_a_scored_tier_is_gate_size():
    assert derive_artifact_authority(_synapse({"a": _artifact(tier="scored")}))["a"]["authority"] == "gate_size"


def test_rule_b_scored_path_surfaces_is_user_ranking():
    """C-2 in miniature: an artifact that ORDERS a user-visible board carries the same
    `tier: display` as a decorative chip, so authority must be a different field."""
    synapse = _synapse({"a": _artifact(tier="display", scored_path_surfaces=["board_ordering"])})
    got = derive_artifact_authority(synapse)["a"]
    assert got["authority"] == "user_ranking" and got["rule"] == "b"
    assert synapse["artifacts"]["a"]["tier"] == "display", (
        "authority is a NEW field, not a rename of tier"
    )


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
    assert derive_artifact_authority(_synapse({"a": _artifact()}))["a"]["authority"] == "display"


def test_authority_does_not_promote_everything():
    """A derivation that promotes every artifact is as useless as one that promotes none."""
    synapse = _synapse({f"chip{i}": _artifact(path=f"site/c{i}.json") for i in range(20)})
    authority = derive_artifact_authority(synapse)
    assert {v["authority"] for v in authority.values()} == {"display"}


def test_engine_authority_is_the_max_over_its_artifacts():
    assert max_authority(["display", "gate_size", "engine_input"]) == "gate_size"
    assert max_authority(["display", "display"]) == "display"
    assert max_authority([]) == "display"


def test_authority_order_is_a_total_order_low_to_high():
    assert AUTHORITY_ORDER == ("display", "engine_input", "user_ranking", "gate_size")


def test_authority_is_attributable_to_a_rule_and_an_artifact():
    registry = build_registry(synapse=_synapse({"a": _artifact(tier="scored")}))
    evidence = registry["engines"][0]["authority_evidence"]
    assert evidence["rule"] == "a" and evidence["artifact_ids"] == ["a"]


def test_an_unattributable_authority_is_a_structural_violation():
    registry = build_registry(synapse=_synapse({"a": _artifact(tier="scored")}))
    registry["engines"][0]["authority_evidence"]["artifact_ids"] = []
    assert any("names no artifact" in v for v in validate_structure(registry))


def test_completeness_flag_proposes_but_never_promotes():
    """prophet-index: consumed by an Article-2 enforcer with no declared surfaces."""
    synapse = _synapse({"a": _artifact(consumers=["scripts/build_site.py"])})
    registry = build_registry(synapse=synapse, article2_modules=["scripts/build_site.py"])
    row = registry["engines"][0]
    assert row["authority_evidence"]["completeness_flag"] is True
    assert row["authority"] == "display", "the detector must NOT promote authority"


def test_an_unimportable_article2_table_is_a_NULL_not_an_empty_list():
    """`_article2_modules()` used to swallow the ImportError and return [], so 'the table
    could not be imported' rendered as 'no Article-2 modules exist' and every completeness
    finding silently disappeared."""
    registry = build_registry(synapse=_synapse({"a": _artifact()}), article2_modules=None)
    row = registry["engines"][0]
    assert row["authority_evidence"]["completeness_flag"] is None
    assert row["authority_evidence"]["completeness_detail"] is None
    assert "SCORED_PATH_SURFACES_UNCHECKED" in _codes(registry)


def test_the_builder_propagates_the_article2_null_rather_than_an_empty_list():
    import scripts.build_intelligence_registry as builder
    import inspect

    source = inspect.getsource(builder._article2_modules)
    assert "return None," in source, "the ImportError branch must return the null"
    assert "return [], " not in source and "return []," not in source


# ---------------------------------------------------------------------------
# evidence_ref — the C-1 fix
# ---------------------------------------------------------------------------

def test_evidence_ref_derives_from_qual_ladder_ref_not_from_the_overlay():
    synapse = _synapse({"a": _artifact(tier="scored", qual_ladder_ref="research/P.md")})
    registry = build_registry(
        synapse=synapse, qual_ladder_keys=set(), file_exists=lambda p: True
    )
    assert registry["engines"][0]["evidence_ref"] == ["research/P.md"]
    assert "evidence_ref" in OVERLAY_FORBIDDEN_KEYS


def test_authority_without_evidence_is_a_content_finding():
    registry = build_registry(synapse=_synapse({"a": _artifact(tier="scored")}))
    assert "AUTHORITY_WITHOUT_EVIDENCE" in _codes(registry)


def test_display_engine_without_evidence_is_not_a_finding():
    assert "AUTHORITY_WITHOUT_EVIDENCE" not in _codes(build_registry(synapse=_synapse({"a": _artifact()})))


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
    registry = build_registry(synapse=synapse, qual_ladder_keys=set(), file_exists=lambda p: True)
    row = registry["engines"][0]
    assert row["authority"] == "gate_size"
    assert row["evidence_ref"] == ["research/UNRELATED_DISPLAY_NOTE.md"], (
        "the union is non-empty — that is exactly the condition that used to silence C-1"
    )
    assert row["authority_evidence"]["unevidenced_artifacts"] == ["gate"]
    assert "AUTHORITY_WITHOUT_EVIDENCE" in _codes(registry)


def test_C1_gate_is_NOT_cleared_by_a_pointer_at_a_nonexistent_file():
    """A ref that resolves to neither a config/qual_ladder.yml key nor an existing repo
    FILE is a string, not evidence. Without this the C-1 backlog is drainable to zero
    without a single real prereg.

    The two states are DISJOINT CODES on purpose — 'no pointer' and 'pointer at nothing'
    need different heals — so what matters is that neither is silent and that the ref never
    rolls up into evidence_ref.
    """
    synapse = _synapse({"a": _artifact(tier="scored", qual_ladder_ref="lol/does_not_exist.md")})
    registry = build_registry(
        synapse=synapse, qual_ladder_keys={"altdata.action"}, file_exists=lambda p: False
    )
    row = registry["engines"][0]
    assert row["artifacts"][0]["qual_ladder_ref_resolution"] == "unresolved"
    assert row["evidence_ref"] is None, "an unresolvable ref must not roll up as evidence"
    assert "AUTHORITY_EVIDENCE_UNRESOLVABLE" in _codes(registry)


def test_the_three_evidence_states_are_disjoint_and_none_is_silent():
    """MISSING / UNRESOLVABLE / UNCHECKED are three buckets, one code each. The failure
    mode this pins is a ref landing in NO bucket — silently passing for evidence."""
    synapse = _synapse(
        {
            "missing": _artifact(tier="scored", path="data/m.json"),
            "broken": _artifact(tier="scored", path="data/b.json",
                                qual_ladder_ref="lol/nope.md", producer="engine/b.py"),
            "good": _artifact(tier="scored", path="data/g.json",
                              qual_ladder_ref="research/P.md", producer="engine/g.py"),
        }
    )
    files = {"research/P.md"}
    registry = build_registry(
        synapse=synapse, qual_ladder_keys=set(), file_exists=lambda p: p in files
    )
    by_id = {r["engine_id"]: r for r in registry["engines"]}
    assert by_id["engine/a.py::prog"]["authority_evidence"]["unevidenced_artifacts"] == ["missing"]
    assert by_id["engine/b.py::prog"]["authority_evidence"]["unresolvable_artifacts"] == ["broken"]
    assert by_id["engine/g.py::prog"]["evidence_ref"] == ["research/P.md"]

    findings = {(f.engine_id, f.code) for f in audit_content(registry)}
    assert ("engine/a.py::prog", "AUTHORITY_WITHOUT_EVIDENCE") in findings
    assert ("engine/b.py::prog", "AUTHORITY_EVIDENCE_UNRESOLVABLE") in findings
    # ...and the properly evidenced one is the POSITIVE CONTROL: no evidence finding at all.
    assert not any(
        eid == "engine/g.py::prog" and code.startswith("AUTHORITY_")
        for eid, code in findings
    )


@pytest.mark.parametrize("ref", ["research/", "research"])
def test_a_qual_ladder_ref_pointing_at_a_DIRECTORY_is_reported_not_accepted(ref):
    """A DIRECTORY IS NOT A PREREG. `git show HEAD:research` exits 0 on a tree, so the
    previous `path_exists` probe accepted any folder — which made the whole C-1 backlog
    drainable to zero by pointing every authority-bearing artifact at a directory.

    The probe injected here is FILE-ONLY: it answers True for a real prereg and False for
    a directory, exactly as the builder's git-ladder probe does.
    """
    files = {"research/PREREG.md"}
    synapse = _synapse({"a": _artifact(tier="scored", qual_ladder_ref=ref)})
    registry = build_registry(
        synapse=synapse, qual_ladder_keys=set(), file_exists=lambda p: p in files
    )
    assert registry["engines"][0]["artifacts"][0]["qual_ladder_ref_resolution"] == "unresolved"
    assert registry["engines"][0]["evidence_ref"] is None
    assert "AUTHORITY_EVIDENCE_UNRESOLVABLE" in _codes(registry)


def test_a_trailing_slash_ref_is_refused_even_by_a_lax_probe():
    """Defence in depth: a probe that wrongly answers True for a directory must not be
    able to launder one through."""
    assert resolve_qual_ladder_ref(
        "research/", qual_ladder_keys=set(), file_exists=lambda p: True
    ) == "unresolved"


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
        ref, qual_ladder_keys=keys, file_exists=lambda p: exists
    ) == expected


def test_resolve_qual_ladder_ref_without_a_probe_is_unchecked():
    assert resolve_qual_ladder_ref("research/P.md") == "unchecked"
    assert resolve_qual_ladder_ref("research/P.md", qual_ladder_keys={"x"}) == "unchecked"
    assert resolve_qual_ladder_ref(None) is None, "no ref at all is still None, not 'unchecked'"


def test_an_UNPROBED_ref_is_never_reported_as_unresolvable():
    """Sparse worktrees are the norm here. A builder that could not probe must say so,
    never accuse — 'could not look' is not 'looked and found nothing'."""
    synapse = _synapse({"a": _artifact(tier="scored", qual_ladder_ref="research/P.md")})
    registry = build_registry(synapse=synapse)  # no qual_ladder_keys, no file_exists
    assert registry["engines"][0]["artifacts"][0]["qual_ladder_ref_resolution"] == "unchecked"
    assert "AUTHORITY_EVIDENCE_UNRESOLVABLE" not in _codes(registry)


def test_an_UNCHECKED_ref_is_NOT_counted_as_evidence():
    """THE OTHER HALF. 'could not look' must not be banked as a pass either: an unprobed
    ref may not clear the C-1 gate, and it may not roll up into evidence_ref."""
    synapse = _synapse({"a": _artifact(tier="scored", qual_ladder_ref="research/P.md")})
    registry = build_registry(synapse=synapse)
    row = registry["engines"][0]
    assert row["evidence_ref"] is None, "an unprobed ref is not evidence"
    assert row["authority_evidence"]["unchecked_artifacts"] == ["a"]
    assert "AUTHORITY_EVIDENCE_UNCHECKED" in _codes(registry)


def test_the_C1_heal_names_EVERY_unevidenced_artifact_not_just_the_first():
    """The heal used to name `authority_evidence.artifact_id` — the first sorted winner —
    so on a multi-winner cell it pointed at the wrong artifact."""
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


# ---------------------------------------------------------------------------
# Ledger waterfall
# ---------------------------------------------------------------------------

def test_ledger_rule_1_is_a_store_shaped_ledger_named_path():
    synapse = _synapse({"a": _artifact(path="data/x_ledger.jsonl")})
    assert build_registry(synapse=synapse)["engines"][0]["ledger_evidence"]["rule"] == 1


def test_ledger_rule_2_resolves_the_desk_by_ast():
    synapse = _synapse({"a": _artifact()})
    registry = build_registry(
        synapse=synapse, desk_scans={"engine/a.py": DeskScan(True, ("mydesk",), False)}
    )
    row = registry["engines"][0]
    assert row["ledger"] == "qledger:mydesk"
    assert row["ledger_evidence"]["desk"] == "mydesk"


def test_ledger_rule_2_zero_row_desk_is_NAMED_not_hidden():
    """Deviation from the brief, deliberate: a zero-row desk keeps its structural
    attribution and is raised as a finding, rather than being silently demoted down the
    waterfall. A registered desk that has never been written is worth naming."""
    synapse = _synapse({"a": _artifact()})
    registry = build_registry(
        synapse=synapse,
        desk_scans={"engine/a.py": DeskScan(True, ("ghost",), False)},
        qledger_desk_rows={},
    )
    assert registry["engines"][0]["ledger"] == "qledger:ghost"
    assert "LEDGER_DECLARED_BUT_EMPTY" in _codes(registry)


def test_ledger_rule_2_unread_corpus_is_not_an_empty_desk():
    """'Could not look' must never render as 'looked and found nothing'."""
    synapse = _synapse({"a": _artifact()})
    registry = build_registry(
        synapse=synapse,
        desk_scans={"engine/a.py": DeskScan(True, ("ghost",), False)},
        qledger_desk_rows=None,
    )
    evidence = registry["engines"][0]["ledger_evidence"]
    assert evidence["corpus_checked"] is False and evidence["corpus_rows"] is None
    assert "LEDGER_DECLARED_BUT_EMPTY" not in _codes(registry)


def test_ledger_rule_3_shadow_tier_artifact():
    synapse = _synapse({"a": _artifact(tier="shadow", path="data/shadow.parquet")})
    assert build_registry(synapse=synapse)["engines"][0]["ledger_evidence"]["rule"] == 3


def test_ledger_rule_4_hops_to_a_SAME_PROGRAM_grader():
    """A program grading its own output — the one rule-4 shape that survived the
    2026-08-14 measurement (engine/experiments_registry.py::qualitative-intelligence hopping
    to engine/qledger.py::qualitative-intelligence)."""
    synapse = _synapse(
        {
            "board": _artifact(producer="scripts/build_x.py", owner_program="prog-a",
                               consumers=["scripts/grade_x.py"]),
            "grades": _artifact(producer="scripts/grade_x.py", owner_program="prog-a",
                                path="data/x_ledger/grades.parquet"),
        }
    )
    registry = build_registry(synapse=synapse)
    row = next(r for r in registry["engines"] if r["producer"] == "scripts/build_x.py")
    assert row["ledger_evidence"]["rule"] == 4
    assert row["ledger_evidence"]["via"] == "scripts/grade_x.py"
    assert row["ledger"] == "data/x_ledger/grades.parquet"


def test_rule_4_may_NOT_hop_across_a_program_boundary():
    """THE M2 DELETION. Rule 4 adopted ANY grader-shaped consumer's ledger, 'EVEN
    CROSS-PROGRAM'. Measured 2026-08-14 on the live corpus: 7 engines resolved by rule 4
    and SIX of the seven hops crossed a program boundary and were wrong — the nightly
    orchestrator engine/run.py::engine-fix was 'graded by' hk-canada's board ledger. A
    cross-program consumer must now leave the engine at rule 5, which says the honest
    thing: no ledger, 'no — not yet'."""
    synapse = _synapse(
        {
            "board": _artifact(producer="scripts/build_x.py", owner_program="prog-a",
                               consumers=["scripts/grade_x.py"]),
            "grades": _artifact(producer="scripts/grade_x.py", owner_program="prog-b",
                                path="data/x_ledger/grades.parquet"),
        }
    )
    registry = build_registry(synapse=synapse)
    row = next(r for r in registry["engines"] if r["producer"] == "scripts/build_x.py")
    assert row["ledger"] == LEDGER_NONE
    assert row["ledger_evidence"]["rule"] == 5
    assert row["graded_by_design"] == GRADED_NOT_YET


def test_rule_4_resolves_the_SAME_PROGRAM_cell_of_a_two_cell_grader():
    """THE ARBITRARY-PICK DEFECT. scripts/grade_us_board.py owns two cells writing two
    DIFFERENT stores, and the producer-keyed hop index kept whichever engine_id sorted
    first — so the hop was a coin flip dressed as a derivation. Keyed by
    (producer, owner_program) there is nothing left to arbitrate: only the consumer's cell
    inside the resolving engine's own program is visible at all."""
    synapse = _synapse(
        {
            "board": _artifact(producer="scripts/build_x.py", owner_program="prog-b",
                               consumers=["scripts/grade_x.py"]),
            "grades-a": _artifact(producer="scripts/grade_x.py", owner_program="prog-a",
                                  path="data/a_ledger/grades.parquet"),
            "grades-b": _artifact(producer="scripts/grade_x.py", owner_program="prog-b",
                                  path="data/b_ledger/grades.parquet"),
        }
    )
    registry = build_registry(synapse=synapse)
    row = next(
        r for r in registry["engines"]
        if r["engine_id"] == "scripts/build_x.py::prog-b"
    )
    assert row["ledger"] == "data/b_ledger/grades.parquet", (
        "the hop must land in the resolving engine's own program, never in the "
        "alphabetically-first cell of the same producer"
    )


def test_rule_4_cannot_hop_onto_a_python_module():
    """scripts/seed_us_sector_baskets.py::sector-pulse was "graded by"
    engine/demand_ledger.py — a Python module cannot hold a graded row."""
    synapse = _synapse(
        {
            "board": _artifact(producer="scripts/build_x.py", consumers=["engine/demand_ledger.py"]),
            "mod": _artifact(producer="engine/demand_ledger.py", owner_program="other",
                             path="engine/demand_ledger.py"),
        }
    )
    row = next(
        r for r in build_registry(synapse=synapse)["engines"]
        if r["producer"] == "scripts/build_x.py"
    )
    assert row["ledger"] == LEDGER_NONE


def test_ledger_rule_5_is_the_literal_string_none_never_null():
    assert build_registry(synapse=_synapse({"a": _artifact()}))["engines"][0]["ledger"] == LEDGER_NONE


def test_a_null_ledger_is_a_structural_violation():
    registry = build_registry(synapse=_synapse({"a": _artifact()}))
    registry["engines"][0]["ledger"] = None
    assert any("never be null" in v for v in validate_structure(registry))


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


def test_a_ledger_named_python_module_is_not_its_own_ledger():
    """A Python module cannot hold a graded row, so an engine/*_ledger.py producer with no
    store-shaped artifact must fall THROUGH the waterfall."""
    synapse = _synapse({"a": _artifact(producer="engine/x_ledger.py", path="site/chip.json")})
    row = build_registry(synapse=synapse)["engines"][0]
    assert row["ledger"] == LEDGER_NONE
    assert row["graded_by_design"] == GRADED_NOT_YET


def test_a_template_ledger_does_not_earn_graded_by_design_yes():
    """An unexpanded glob names a FAMILY of stores. It cannot be opened, so it is not
    evidence that grading happens — and it must not manufacture its own contradiction
    finding either."""
    synapse = _synapse({"a": _artifact(tier="shadow", path="data/oracle/fwd/<id>.jsonl")})
    registry = build_registry(synapse=synapse)
    row = registry["engines"][0]
    assert row["ledger"] == "data/oracle/fwd/<id>.jsonl"
    assert row["ledger_evidence"]["shape"] == "template"
    assert row["graded_by_design"] == GRADED_NOT_YET
    assert "GRADED_BY_DESIGN_CONTRADICTS_LEDGER" not in _codes(registry)


# ---------------------------------------------------------------------------
# graded_by_design — an HONESTLY LABELLED weak heuristic
# ---------------------------------------------------------------------------

def test_graded_yes_from_a_PATH_SUBSTRING_is_labelled_weak_and_enumerated():
    """THE KNOWN LIMIT, ASSERTED. Waterfall rules 1 and 4 resolve the ledger from a PATH
    substring (/ledger/ anywhere in a path, /grade|ledger/ on a consumer module name). A
    name is not proof that graded rows are written, so every `yes` reached that way is a
    GUESS — labelled `weak_path_heuristic` and enumerated by audit_content on every run,
    rather than described in prose or hand-listed (a hand list rots)."""
    synapse = _synapse({"a": _artifact(path="data/a_ledger.jsonl")})
    registry = build_registry(synapse=synapse)
    row = registry["engines"][0]
    assert row["graded_by_design"] == GRADED_YES
    assert row["graded_by_design_evidence"] == GRADED_EVIDENCE_WEAK
    assert "PATH" in row["graded_by_design_source"]
    assert "GRADED_BY_DESIGN_IS_HEURISTIC" in _codes(registry)


def test_rule_1_matches_a_DIRECTORY_component_and_the_disclosure_says_so():
    """THE M3 CORRECTION. `_LEDGER_PATH_RE` is unanchored, so `data/qledger/claims.jsonl`
    matches on its DIRECTORY. Measured 2026-08-14: 5 of the 35 live rule-1 matches are of
    exactly this shape and all 5 are real grading stores, so narrowing to the basename was
    rejected — every disclosure now says PATH, not FILENAME."""
    registry = build_registry(synapse=_synapse({"a": _artifact(path="data/qledger/claims.jsonl")}))
    row = registry["engines"][0]
    assert row["ledger_evidence"]["rule"] == 1
    assert row["graded_by_design_evidence"] == GRADED_EVIDENCE_WEAK
    assert "FILENAME" not in row["graded_by_design_source"].upper(), (
        "the disclosure claimed a filename match for a path that matches on its directory"
    )
    detail = next(
        f.detail for f in audit_content(registry)
        if f.code == "GRADED_BY_DESIGN_IS_HEURISTIC"
    )
    assert "FILENAME" not in detail.upper()


def test_graded_yes_from_a_DECLARATION_is_labelled_strong_and_not_enumerated():
    synapse = _synapse({"a": _artifact(tier="shadow", path="data/s.parquet")})
    registry = build_registry(synapse=synapse)
    row = registry["engines"][0]
    assert row["graded_by_design"] == GRADED_YES
    assert row["graded_by_design_evidence"] == GRADED_EVIDENCE_STRONG
    assert "GRADED_BY_DESIGN_IS_HEURISTIC" not in _codes(registry)


def test_graded_yes_from_an_AST_RESOLVED_desk_is_strong():
    synapse = _synapse({"a": _artifact()})
    registry = build_registry(
        synapse=synapse, desk_scans={"engine/a.py": DeskScan(True, ("d",), False)}
    )
    assert registry["engines"][0]["graded_by_design_evidence"] == GRADED_EVIDENCE_STRONG


def test_a_rule_4_hop_is_also_weak_because_it_matches_a_MODULE_NAME():
    """Same-program is a necessary condition, not a sufficient one: the hop still selects
    its target by grepping /grade|ledger/ over a MODULE NAME, so it stays weak."""
    synapse = _synapse(
        {
            "board": _artifact(producer="scripts/build_x.py", owner_program="prog-a",
                               consumers=["scripts/grade_x.py"]),
            "grades": _artifact(producer="scripts/grade_x.py", owner_program="prog-a",
                                path="data/x_ledger/grades.parquet"),
        }
    )
    registry = build_registry(synapse=synapse)
    row = next(r for r in registry["engines"] if r["producer"] == "scripts/build_x.py")
    assert row["graded_by_design_evidence"] == GRADED_EVIDENCE_WEAK


def test_the_graded_evidence_strength_is_a_REQUIRED_field():
    """A graded claim with no stated strength is the defect this labelling exists to fix,
    so its absence must be a structural violation rather than a missing nicety."""
    registry = build_registry(synapse=_synapse({"a": _artifact(path="data/a_ledger.jsonl")}))
    registry["engines"][0]["graded_by_design_evidence"] = "vibes"
    assert any("graded_by_design_evidence" in v for v in validate_structure(registry))


def test_the_module_docstring_discloses_the_weak_heuristic():
    """The limitation must be readable where the derivation lives, not only in a test."""
    import engine.intelligence_registry as mod

    doc = mod.__doc__ or ""
    assert "WEAK HEURISTIC" in doc.upper()
    assert "PATH SUBSTRING" in doc.upper()
    assert GRADED_EVIDENCE_WEAK in doc
    assert "weak_filename_heuristic" not in doc, (
        "the retired enum value must not survive in the disclosure it used to describe"
    )


def test_graded_descriptive_when_every_artifact_is_infrastructure():
    synapse = _synapse({"a": _artifact(tier="infrastructure")})
    row = build_registry(synapse=synapse)["engines"][0]
    assert row["graded_by_design"] == GRADED_DESCRIPTIVE
    assert row["graded_by_design_evidence"] == GRADED_EVIDENCE_NONE


def test_graded_default_names_the_gap_rather_than_excusing_it():
    assert build_registry(synapse=_synapse({"a": _artifact()}))["engines"][0]["graded_by_design"] == GRADED_NOT_YET


def test_overlay_may_make_the_one_legal_transition():
    overlay = {
        "schema_version": 1,
        "engines": {"engine/a.py::prog": {"graded_by_design": {"value": GRADED_DESCRIPTIVE, "reason": "r"}}},
    }
    registry = build_registry(synapse=_synapse({"a": _artifact()}), overlay=overlay)
    assert registry["engines"][0]["graded_by_design"] == GRADED_DESCRIPTIVE


def test_overlay_cannot_downgrade_a_graded_yes_engine():
    """The overlay may never write 'yes'; and it may not touch a row already 'yes'."""
    synapse = _synapse({"a": _artifact(path="data/x_ledger.jsonl")})
    overlay = {
        "schema_version": 1,
        "engines": {"engine/a.py::prog": {"graded_by_design": {"value": GRADED_DESCRIPTIVE, "reason": "r"}}},
    }
    assert build_registry(synapse=synapse, overlay=overlay)["engines"][0]["graded_by_design"] == GRADED_YES


# ---------------------------------------------------------------------------
# AST desk scan
# ---------------------------------------------------------------------------

def test_desk_scan_extracts_a_keyword_literal():
    scan = scan_producer_source("from engine.qledger import register\nregister(desk='alpha')\n")
    assert scan.imports_qledger and scan.desks == ("alpha",)


def test_desk_scan_extracts_a_dict_literal():
    src = 'from engine.qledger import register_batch\nregister_batch([{"desk": "beta"}])\n'
    assert scan_producer_source(src).desks == ("beta",)


def test_desk_scan_flags_an_unresolved_indirect_desk():
    scan = scan_producer_source("from engine.qledger import register\nD = 'x'\nregister(desk=D)\n")
    assert scan.desks == () and scan.unresolved is True


def test_desk_scan_ignores_a_module_that_does_not_import_qledger():
    assert scan_producer_source("register(desk='alpha')\n").imports_qledger is False


def test_desk_scan_survives_a_syntax_error():
    assert scan_producer_source("def broken(:\n").desks == ()


# ---------------------------------------------------------------------------
# output_class
# ---------------------------------------------------------------------------

def test_output_class_is_not_required_for_a_display_only_engine():
    row = build_registry(synapse=_synapse({"a": _artifact()}))["engines"][0]
    assert row["output_class"] is None
    assert row["output_class_reason"] == "not_required_display_only"


def test_output_class_is_required_once_the_evaluation_gate_trips():
    synapse = _synapse({"a": _artifact(tier="shadow", path="data/s.parquet")})
    assert build_registry(synapse=synapse)["engines"][0]["output_class_reason"] == "required_but_uncurated"


def test_a_graded_engine_still_needs_a_metric_contract():
    """26 engines with graded_by_design='yes' were recorded 'not_required_display_only'
    because the gate keyed on authority and tier but never on the derived ledger."""
    synapse = _synapse({"a": _artifact(tier="display", path="data/prophet/ledger.jsonl")})
    row = build_registry(synapse=synapse)["engines"][0]
    assert row["graded_by_design"] == GRADED_YES
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


def test_declared_horizon_d_comes_from_the_corpus_and_is_null_when_unread():
    synapse = _synapse({"a": _artifact()})
    scans = {"engine/a.py": DeskScan(True, ("d",), False)}
    read = build_registry(synapse=synapse, desk_scans=scans, qledger_desk_horizons={"d": [63, 5]})
    assert read["engines"][0]["declared_horizon"]["horizon_d"] == [5, 63]
    unread = build_registry(synapse=synapse, desk_scans=scans, qledger_desk_horizons=None)
    assert unread["engines"][0]["declared_horizon"]["horizon_d"] is None


# ---------------------------------------------------------------------------
# validation_state
# ---------------------------------------------------------------------------

def test_species_none_means_could_not_look_not_phase0():
    assert bind_species("data/x.jsonl", None)["validation_state"] is None


def test_an_unread_species_store_reports_null_unbound_not_empty():
    registry = build_registry(synapse=_synapse({"a": _artifact()}), species=None)
    assert registry["meta"]["unbound_species"] is None
    assert registry["meta"]["corpus"]["species_read"] is False
    assert all(r["validation_state"] is None for r in registry["engines"])
    assert "SPECIES_UNBOUND" not in _codes(registry)


def test_an_EMPTY_species_store_is_a_DIFFERENT_state_from_an_unread_one():
    """The two must not collapse: `phase0` asserts nothing, `None` says nothing was
    asserted. A helper defaulting `species=None` to `[]` erased the distinction inside the
    guard's own selftest harness (2026-08-12) and turned the control vacuous."""
    registry = build_registry(synapse=_synapse({"a": _artifact()}), species=[])
    assert registry["meta"]["unbound_species"] == []
    assert registry["meta"]["corpus"]["species_read"] is True
    assert all(r["validation_state"] == "phase0" for r in registry["engines"])


def test_single_bound_species_takes_its_status():
    species = [{"species_id": "S1", "validation_status": "validated",
                "ledger_binding": {"ledger": "us_board_ledger"}}]
    assert bind_species("data/us_board_ledger/grades.parquet", species)["validation_state"] == "validated"


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
        # The binding SHAPES seen live, as shapes rather than as a pinned inventory.
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


def test_unbound_species_are_NAMED_not_dropped():
    """The inverse of bind_species had no check at all: a species matching no engine was
    dropped in silence."""
    species = [{"species_id": "F3_ANTICHASE", "validation_status": "accruing",
                "ledger_binding": {"ledger": "no_such_ledger"}}]
    registry = build_registry(synapse=_synapse({"a": _artifact()}), species=species)
    assert [r["species_id"] for r in registry["meta"]["unbound_species"]] == ["F3_ANTICHASE"]
    assert "SPECIES_UNBOUND" in _codes(registry)


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


def test_the_shipped_overlay_is_structurally_valid_against_the_partition():
    """A live-input test that asserts SHAPE, not contents: whatever the overlay says, it
    must obey the four-key allowlist and name only cells the partition generates."""
    import yaml
    import scripts.build_intelligence_registry as builder

    overlay = yaml.safe_load(
        (REPO / "config" / "intelligence_registry_overlay.yml").read_text(encoding="utf-8")
    )
    _, report = builder.build(REPO)
    assert validate_overlay(overlay, report["cell_ids"]) == []


# ---------------------------------------------------------------------------
# Determinism
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


def test_the_schema_string_is_pinned():
    assert build_registry(synapse=_synapse({"a": _artifact()}))["schema"] == SCHEMA


# ---------------------------------------------------------------------------
# LIVE INPUTS — no crash, well-formed structure, and NOTHING pinned by content
# ---------------------------------------------------------------------------

def test_the_builder_runs_over_the_live_tree_and_returns_a_well_formed_view():
    """The ONLY live-input contract: it does not crash and the view is well-formed. No
    engine count, no artifact name and no finding count is asserted anywhere in this file —
    every one of those moves when a sibling PR touches config/synapse.yml."""
    import scripts.build_intelligence_registry as builder
    from engine.species_registry import VALID_VALIDATION_STATUSES

    builder._READ_CACHE.clear()
    registry, report = builder.build(REPO)
    assert registry["schema"] == SCHEMA
    assert isinstance(registry["engines"], list) and registry["engines"]
    assert validate_structure(
        registry, valid_validation_statuses=VALID_VALIDATION_STATUSES
    ) == []
    assert registry["meta"]["n_artifacts_mapped"] == registry["meta"]["n_artifacts"]
    assert isinstance(report["unreadable_inputs"], list)


def test_the_live_view_is_idempotent_within_one_snapshot():
    import scripts.build_intelligence_registry as builder

    builder._READ_CACHE.clear()
    first, _ = builder.build(REPO)
    second, _ = builder.build(REPO)
    assert serialise(first) == serialise(second)


def test_content_audit_is_pure_over_a_loaded_registry():
    import scripts.build_intelligence_registry as builder

    registry, _ = builder.build(REPO)
    assert audit_content(registry) == audit_content(registry)


# --- THE TWO VOLATILITY SIMULATIONS ---------------------------------------
#
# Neither event is caused by a PR author on this lane, and neither may invalidate
# anything. The registry is derived on demand and nothing is pinned by equality, so the
# assertion is that the DERIVATION stays structurally valid and the guard stays green —
# not that the bytes are unchanged (they are allowed to move; that is the whole point).

def _patched_read(monkeypatch, rel_to_patch, transform):
    """Point the builder at a MUTATED COPY of one input, as a nightly lane would."""
    import scripts.build_intelligence_registry as builder

    original = builder._read_tracked_uncached

    def patched(root, rel):
        text, source = original(root, rel)
        if rel == rel_to_patch and text is not None:
            text = transform(text)
        return text, source

    builder._READ_CACHE.clear()
    monkeypatch.setattr(builder, "_read_tracked_uncached", patched)
    return builder


def test_a_nightly_CLAIM_APPEND_invalidates_nothing(monkeypatch):
    """SIMULATION (a). `data/qledger/claims.jsonl` is append-only — 13 automated commits in
    14 days — and round 1 pinned a value derived from it by equality, so main went red
    daily for a property no PR author caused. Two appends at once: one more row on an
    existing desk, and a row opening a brand-new desk."""
    import scripts.build_intelligence_registry as builder
    from engine.species_registry import VALID_VALIDATION_STATUSES

    builder._READ_CACHE.clear()
    before, _ = builder.build(REPO)
    extra = [
        {"desk": "whitehouse", "horizon_d": 999, "direction": 1},
        {"desk": "brand_new_desk_2026", "horizon_d": 21, "direction": 1},
    ]
    try:
        _patched_read(
            monkeypatch,
            builder.CLAIMS_REL,
            lambda text: text + "".join(json.dumps(r) + "\n" for r in extra),
        )
        after, _ = builder.build(REPO)
    finally:
        builder._READ_CACHE.clear()

    # The append must be REAL, or this test proves nothing.
    assert after["meta"]["corpus"]["n_desks"] == before["meta"]["corpus"]["n_desks"] + 1

    assert validate_structure(
        after, valid_validation_statuses=VALID_VALIDATION_STATUSES
    ) == []
    assert {r["engine_id"] for r in after["engines"]} == {r["engine_id"] for r in before["engines"]}
    assert (
        sorted((f.code, f.engine_id) for f in audit_content(after))
        == sorted((f.code, f.engine_id) for f in audit_content(before))
    ), "a nightly claim append changed the finding set — that is a scheduled fleet-wide red"


def test_a_SIBLING_PR_adding_a_synapse_artifact_invalidates_nothing(monkeypatch):
    """SIMULATION (b). config/synapse.yml took 26 commits in 14 days, ALL inside the
    window; round 2 relocated the equality pin onto it and was refuted for that reason. A
    sibling PR registering a new SCORED artifact must leave this lane green: the view grows
    a row and a finding, and nothing is invalidated."""
    import scripts.build_intelligence_registry as builder
    from engine.species_registry import VALID_VALIDATION_STATUSES

    builder._READ_CACHE.clear()
    before, _ = builder.build(REPO)

    synthetic = (
        "\n"
        "  synthetic-sibling-scored-artifact:\n"
        "    path: data/synthetic_sibling/board.parquet\n"
        "    format: parquet\n"
        "    producer: engine/synthetic_sibling.py\n"
        "    owner_program: synthetic-sibling-program\n"
        "    cadence: daily-engine\n"
        "    storage: git\n"
        "    asof_field: asof\n"
        "    freshness_sla_hours: 24\n"
        "    schema: synthetic\n"
        "    tier: scored\n"
        "    horizon_role: context\n"
        "    consumers: []\n"
    )
    try:
        _patched_read(monkeypatch, builder.SYNAPSE_REL, lambda text: text + synthetic)
        after, _ = builder.build(REPO)
    finally:
        builder._READ_CACHE.clear()

    # The edit must be REAL, or this test proves nothing.
    new_ids = {r["engine_id"] for r in after["engines"]} - {r["engine_id"] for r in before["engines"]}
    assert new_ids == {"engine/synthetic_sibling.py::synthetic-sibling-program"}

    assert validate_structure(
        after, valid_validation_statuses=VALID_VALIDATION_STATUSES
    ) == []
    assert after["meta"]["n_artifacts_mapped"] == after["meta"]["n_artifacts"]
    # The new authority-bearing artifact is REPORTED, not silently absorbed.
    assert any(
        f.code == "AUTHORITY_WITHOUT_EVIDENCE"
        and f.engine_id == "engine/synthetic_sibling.py::synthetic-sibling-program"
        for f in audit_content(after)
    )


# ---------------------------------------------------------------------------
# Sparse-worktree correctness — "could not look" is never "looked and found nothing"
# ---------------------------------------------------------------------------

def test_producer_source_is_read_through_the_sparse_ladder(monkeypatch):
    """`_scan_producers` read the working tree only and skipped a missing file with a
    silent `continue`. Under a sparse cone that loses ledger-waterfall rule 2 and derives a
    structurally different registry than CI, with nothing in the log saying so."""
    import scripts.build_intelligence_registry as builder

    seen: list[str] = []
    original = builder.read_tracked

    def spy(root, rel):
        seen.append(rel.as_posix())
        return original(root, rel)

    monkeypatch.setattr(builder, "read_tracked", spy)
    builder._scan_producers(REPO, {"scripts/build_whitehouse.py"})
    assert "scripts/build_whitehouse.py" in seen, "the producer must go through read_tracked"


def test_an_unreadable_producer_is_COUNTED_not_silently_skipped():
    import scripts.build_intelligence_registry as builder

    scans, _, unreadable = builder._scan_producers(
        REPO, {"engine/this_module_does_not_exist_anywhere.py"}
    )
    assert unreadable == ["engine/this_module_does_not_exist_anywhere.py"]
    assert scans == {}


def test_the_species_store_is_read_through_the_git_ladder_in_a_sparse_worktree():
    """data/ is absent on disk in an agent worktree while ~39,900 data paths are tracked in
    HEAD. A disk-only read would silently derive validation_state='phase0' everywhere."""
    import scripts.build_intelligence_registry as builder

    species, source = builder._load_species(REPO)
    assert species is not None, "the species store must resolve through worktree OR HEAD"
    assert source in ("worktree", "git")


@pytest.mark.parametrize(
    "path,expected",
    [
        ("config/synapse.yml", True),
        ("research", False),                       # a directory is not a prereg
        ("research/lol_does_not_exist_anywhere.md", False),
        ("/etc/passwd", False),                    # absolute paths must never resolve
        ("../../../etc/passwd", False),            # nor traversal out of the repo
        ("", False),
    ],
)
def test_the_qual_ladder_probe_answers_FILE_IN_THIS_REPO_only(path, expected):
    """`root / "/etc/passwd"` is `/etc/passwd` under pathlib's absolute-operand rule, so
    the worktree half of the probe answered True for any absolute path on the machine —
    another way to drain the C-1 backlog without a prereg."""
    import scripts.build_intelligence_registry as builder

    assert builder._tracked_file_exists(REPO, path) is expected
