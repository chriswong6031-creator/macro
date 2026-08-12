"""scripts/check_intelligence_registry.py — the engine-registry gate (Eval OS T1).

Enforces TWO house laws, deliberately split because they have different blast radii and
therefore must have different severities. Collapsing them into one entry would force one
severity, so either integrity ships too weak to protect the registry or the pre-existing
C-1 backlog reds main fleet-wide on arrival.

(A) governance.intelligence_registry_integrity — HARD, wired to pr_ci.
    Properties of the registry's OWN FILES only:
      * the committed file differs BYTE-FOR-BYTE from a fresh regeneration (drift)
      * regeneration is not idempotent
      * a corpus-derived path is present in the committed file at all (assert_no_volatile)
      * an overlay key outside the four-key allowlist, or a forbidden derived key
      * an overlay row for a cell the partition does not contain (orphan)
      * a curated `not_an_engine` exclusion of an AUTHORITY-BEARING cell
      * an unknown enum value, a missing required field, a null ledger
      * an exclusion with an empty reason, or one that does not say what it deletes
      * an artifact mapping to zero or more than one engine
    Every one of these is green by construction on the PR that generates the file, and
    none can be tripped by a pre-existing corpus condition. HARD is legitimate precisely
    because the blast radius is the registry itself.

(B) epistemics.engine_authority_evidence — WARN, wired to the SAME job, exit 0 by
    default, non-zero only under --strict.
    CONTENT findings about the CORPUS:
      * authority > display with evidence_ref == null (C-1)
      * output_class missing on an engine that trips the evaluation gate
      * graded_by_design contradicting a resolved ledger
      * the scored_path_surfaces completeness flag (prophet-index)
      * a registered qledger desk with zero rows in the claim corpus
    These are PRE-EXISTING CONDITIONS no PR author caused. Wiring them hard on arrival
    would red main fleet-wide for a property nobody introduced, which is exactly how a
    gate gets routed around instead of obeyed — the failure mode the sibling precedent
    epistemics.qledger_metric_validity documents in its own notes.

    warn was chosen over the precedent's manual + ci_wiring:[]. VALID_SEVERITIES permits
    empty ci_wiring only for manual/discipline/known_spurious, so `manual` means the audit
    never runs against the real corpus unless a human remembers. `warn` requires real
    wiring, so the C-1 backlog is visible as ::warning annotations on every PR and the
    count is trackable. PROMOTION PLAN: promote (B) to hard with --strict in the same PR
    that drives the authority>display evidence_ref backlog to zero, owned by T7 of
    research/MASTERMIND_INTELLIGENCE_OS_V1_PLAN.md. An upgrade needs no ruling; a
    downgrade does.

WHY THE DRIFT COMPARISON IS ONE BYTE-EXACT COMPARISON
-----------------------------------------------------
`data/qledger/claims.jsonl` is APPEND-ONLY, so any committed field derived from it is a
SCHEDULED fleet-wide red — it goes stale with no code change and reds main daily for a
property no PR author caused.

The first design tried to survive that by comparing a STRUCTURAL PROJECTION: the file with
the corpus-derived paths stripped before comparing. That was unsound twice over. (i) The
CI-wired test `tests/test_check_intelligence_registry.py::test_builder_check_mode_reports_no_drift`
asserts `build_intelligence_registry.py --check` exits 0, and `--check` compares the WHOLE
file — so the scheduled red came straight back in through the test the projection was
supposed to protect. (ii) A gate that strips a field before comparing it is BLIND to a
hand-edit of that field; `validation_state` — the display-only-until-validated axis — was
tamperable with the guard reporting byte-identical output.

Both are fixed at the source: the committed artifact carries NO corpus-derived field.
Volatile values are computed at read time by `volatile_view()`, `assert_no_volatile()`
makes their PRESENCE a hard violation, and this guard makes ONE byte-exact comparison that
is now both sound and complete. There is deliberately no nightly regeneration lane — the
answer is that nothing an automated lane can move lives in the file.

Annotations are emitted with a bare `print` and `flush=True` per CLAUDE.md §"GitHub
annotations must START the line" — a logger would prefix the line and GitHub would
silently drop it.

Usage
-----
  python3 scripts/check_intelligence_registry.py             # both laws, (B) advisory
  python3 scripts/check_intelligence_registry.py --strict    # (B) also exits non-zero
  python3 scripts/check_intelligence_registry.py --json
  python3 scripts/check_intelligence_registry.py --selftest

An ABSENT registry or an unreadable data store exits 0 with a ::notice. Sparse agent
worktrees have no data/ on disk while the paths are tracked in HEAD, so "I could not look"
must never render as "I looked and it was clean" (CLAUDE.md §Epistemics).
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.intelligence_registry import (  # noqa: E402
    SCHEMA,
    assert_no_volatile,
    audit_content,
    audit_corpus,
    resolve_qual_ladder_ref,
    serialise,
    validate_overlay,
    validate_structure,
    volatile_view,
)
from engine.species_registry import VALID_VALIDATION_STATUSES  # noqa: E402
from scripts.build_intelligence_registry import (  # noqa: E402
    DOC_REL,
    OVERLAY_REL,
    REGISTRY_REL,
    build,
    render_doc,
)

import yaml  # noqa: E402

TITLE_A = "intelligence-registry-integrity"
TITLE_B = "engine-authority-evidence"


# ---------------------------------------------------------------------------
# Law A — integrity (hard)
# ---------------------------------------------------------------------------

def check_integrity(root: Path) -> tuple[list[str], dict | None, dict | None]:
    """Returns (violations, committed_registry, report).

    ONE byte-exact comparison, in both directions, because the committed artifact carries
    no corpus-derived field. The first version compared a STRUCTURAL PROJECTION — the file
    with the volatile paths stripped — which was unsound twice: the CI-wired
    ``--check`` test still pinned the WHOLE file (so the append-only scheduled red came
    back through the test), and stripping a field before comparing it made a hand-edit of
    that field invisible. Absence is now ASSERTED by ``assert_no_volatile`` inside
    ``validate_structure``, so byte-exact is both sound and complete.
    """
    registry_path = root / REGISTRY_REL
    if not registry_path.exists():
        return ([], None, None)

    try:
        committed = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ([f"{REGISTRY_REL}: not valid JSON ({exc})"], None, None)

    violations = validate_structure(
        committed, valid_validation_statuses=VALID_VALIDATION_STATUSES
    )

    regenerated, report = build(root)

    overlay_path = root / OVERLAY_REL
    overlay = (
        yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
        if overlay_path.exists()
        else None
    )
    # ORPHAN CHECK AGAINST THE FRESH CELL SET, not against the committed registry's own
    # ids. Feeding it `engines + excluded` from the committed file let a `not_an_engine`
    # row SELF-LEGITIMATE: the row created the excluded entry that proved it was not an
    # orphan. partition_artifacts() is pre-exclusion, so it cannot be gamed that way.
    violations += validate_overlay(
        overlay,
        report["cell_ids"],
        valid_validation_statuses=VALID_VALIDATION_STATUSES,
    )

    if not report["stable_complete"]:
        # "Could not look" is not "looked and it was clean". Skipping is the only honest
        # option — a comparison against a registry we could not fully derive would report
        # a false drift, and the natural "fix" for a false red is to weaken the gate.
        return (violations, committed, report)

    if serialise(regenerated) != serialise(committed):
        violations.append(
            f"{REGISTRY_REL}: committed file differs from a fresh regeneration — "
            f"HEAL: python3 scripts/build_intelligence_registry.py"
        )

    # Idempotence: the generator must be a function, not a process with memory.
    again, _ = build(root)
    if serialise(again) != serialise(regenerated):
        violations.append("generator is NOT idempotent: two consecutive builds differ")

    doc_path = root / DOC_REL
    expected_doc = render_doc(regenerated, audit_content(regenerated))
    if not doc_path.exists():
        violations.append(f"{DOC_REL}: missing — HEAL: python3 scripts/build_intelligence_registry.py")
    elif doc_path.read_text(encoding="utf-8") != expected_doc:
        violations.append(
            f"{DOC_REL}: stale — HEAL: python3 scripts/build_intelligence_registry.py"
        )

    return (violations, committed, report)


# ---------------------------------------------------------------------------
# Selftest — NEGATIVE CONTROLS BOTH WAYS
# ---------------------------------------------------------------------------

def _good_registry() -> dict:
    """A minimal, structurally valid registry. The POSITIVE control."""
    return {
        "schema": SCHEMA,
        "meta": {
            "unit_of_account": "engine = (producer, owner_program)",
            "engine_id_format": "{producer}::{owner_program}",
            "n_engines": 1,
            "n_excluded": 1,
            "n_artifacts": 2,
            "n_artifacts_mapped": 2,
            "volatile_fields_excluded": [
                "declared_horizon.horizon_d",
                "ledger_evidence.corpus_rows",
                "ledger_evidence.corpus_checked",
            ],
            "volatile_meta_keys_excluded": ["corpus"],
            "authority_order": ["display", "engine_input", "user_ranking", "gate_size"],
            "unbound_species": [],
        },
        "engines": [
            {
                "engine_id": "engine/a.py::prog",
                "producer": "engine/a.py",
                "owner_program": "prog",
                "owner_program_span": 1,
                "artifacts": [
                    {
                        "id": "art-a",
                        "path": "data/a.json",
                        "tier": "scored",
                        "horizon_role": "context",
                        "freshness_sla_hours": 24,
                        "storage": "git",
                        "scored_path_surfaces": [],
                        "qual_ladder_ref": "research/PREREG.md",
                        "qual_ladder_ref_resolution": "repo_path",
                        "artifact_authority": "gate_size",
                    }
                ],
                "consumers": [],
                "output_class": "predictive",
                "output_class_reason": "curated: x",
                "authority": "gate_size",
                "authority_evidence": {
                    "rule": "a",
                    "artifact_ids": ["art-a"],
                    "surfaces": [],
                    "completeness_flag": False,
                    "completeness_detail": [],
                    "unevidenced_artifacts": [],
                    "unresolvable_artifacts": [],
                },
                "ledger": "data/a_ledger.jsonl",
                "ledger_evidence": {
                    "rule": 1,
                    "desk": None,
                    "via": None,
                    "shape": "store",
                },
                "graded_by_design": "yes",
                "graded_by_design_source": "derived: has a ledger",
                "declared_horizon": {
                    "horizon_role": ["context"],
                    "horizon_role_homogeneous": True,
                },
                "validation_state": "phase0",
                "validation_state_evidence": {"bound_species": [], "reason": "no_species_bound"},
                "evidence_ref": ["research/PREREG.md"],
            }
        ],
        "excluded": [
            {
                "engine_id": "<MANUAL>::prog",
                "producer": "<MANUAL>",
                "owner_program": "prog",
                "artifacts": ["art-b"],
                "reason": "derived: placeholder producer token",
                "source": "derived",
                "would_be_authority": "display",
                "would_be_tiers": ["display"],
                "would_be_artifact_authorities": ["display"],
                "would_be_ledger": "none",
                "would_be_output_class_reason": "not_required_display_only",
                "would_be_unevidenced_artifacts": [],
            }
        ],
    }


def _selftest() -> int:
    """Prove the validator rejects each bad registry AND accepts a good one.

    Both directions are required. A validator that flags everything is as useless as one
    that flags nothing — the sibling precedent
    scripts/check_qledger_metric_validity.py --selftest makes the same argument.
    """
    checks: list[tuple[str, bool]] = []
    statuses = VALID_VALIDATION_STATUSES

    # ---- POSITIVE CONTROL: a good registry must produce ZERO violations ----
    good = _good_registry()
    checks.append(
        ("POSITIVE CONTROL — a valid registry is accepted", validate_structure(good, valid_validation_statuses=statuses) == [])
    )
    checks.append(
        ("POSITIVE CONTROL — a valid registry raises no content findings", audit_content(good) == [])
    )
    checks.append(
        ("POSITIVE CONTROL — an empty overlay is accepted",
         validate_overlay({"schema_version": 1, "engines": {}}, ["engine/a.py::prog"]) == [])
    )

    # ---- NEGATIVE CONTROLS: each mutation must be REJECTED ----
    def rejects(label: str, mutate) -> None:
        bad = copy.deepcopy(good)
        mutate(bad)
        violations = validate_structure(bad, valid_validation_statuses=statuses)
        checks.append((label, bool(violations)))

    def _set_bad_authority(r):
        r["engines"][0]["authority"] = "supreme_overlord"

    def _set_bad_graded(r):
        r["engines"][0]["graded_by_design"] = "sort of"

    def _set_bad_output_class(r):
        r["engines"][0]["output_class"] = "vibes"

    def _set_bad_status(r):
        r["engines"][0]["validation_state"] = "totally_proven"

    def _null_ledger(r):
        r["engines"][0]["ledger"] = None

    def _drop_field(r):
        r["engines"][0].pop("evidence_ref")

    def _empty_exclusion_reason(r):
        r["excluded"][0]["reason"] = "   "

    def _duplicate_artifact(r):
        clone = copy.deepcopy(r["engines"][0])
        clone["engine_id"] = "engine/b.py::prog"
        clone["producer"] = "engine/b.py"
        r["engines"].append(clone)

    def _drop_artifact(r):
        r["engines"][0]["artifacts"] = []

    def _bad_schema(r):
        r["schema"] = "something.else"

    def _mismatched_id(r):
        r["engines"][0]["engine_id"] = "engine/z.py::prog"

    def _commit_a_volatile_path(r):
        # THE SCHEDULED-RED TRIPWIRE. corpus_rows is a function of the append-only claim
        # store; a committed copy of it reds every open PR on the next nightly append.
        r["engines"][0]["ledger_evidence"]["corpus_rows"] = 88

    def _commit_a_volatile_meta_key(r):
        r["meta"]["corpus"] = {"qledger_read": True, "n_desks": 13}

    def _commit_a_volatile_horizon(r):
        r["engines"][0]["declared_horizon"]["horizon_d"] = [5, 21]

    def _curated_exclusion_of_an_authority_cell(r):
        row = r["excluded"][0]
        row["source"] = "curated"
        row["reason"] = "judgment call: this is a rail, not an intelligence engine at all"
        row["would_be_authority"] = "gate_size"

    def _curated_exclusion_of_a_scored_cell(r):
        row = r["excluded"][0]
        row["source"] = "curated"
        row["reason"] = "judgment call: this is a rail, not an intelligence engine at all"
        row["would_be_tiers"] = ["scored"]

    def _exclusion_that_does_not_say_what_it_deletes(r):
        r["excluded"][0].pop("would_be_authority")

    rejects("NEGATIVE — unknown authority enum", _set_bad_authority)
    rejects("NEGATIVE — unknown graded_by_design value", _set_bad_graded)
    rejects("NEGATIVE — unknown output_class", _set_bad_output_class)
    rejects("NEGATIVE — unknown validation_state", _set_bad_status)
    rejects("NEGATIVE — null ledger (must be the literal 'none')", _null_ledger)
    rejects("NEGATIVE — missing required field", _drop_field)
    rejects("NEGATIVE — exclusion with an empty reason", _empty_exclusion_reason)
    rejects("NEGATIVE — one artifact mapped to TWO engines", _duplicate_artifact)
    rejects("NEGATIVE — an artifact dropped from the partition", _drop_artifact)
    rejects("NEGATIVE — wrong schema string", _bad_schema)
    rejects("NEGATIVE — engine_id not equal to producer::owner_program", _mismatched_id)
    rejects(
        "NEGATIVE — a corpus-derived ledger_evidence.corpus_rows is COMMITTED "
        "(the append-only scheduled red)",
        _commit_a_volatile_path,
    )
    rejects("NEGATIVE — a corpus-derived meta.corpus block is COMMITTED", _commit_a_volatile_meta_key)
    rejects("NEGATIVE — a corpus-derived declared_horizon.horizon_d is COMMITTED", _commit_a_volatile_horizon)
    rejects(
        "NEGATIVE — a CURATED exclusion of an authority-bearing cell (the overlay is not "
        "a deletion hatch)",
        _curated_exclusion_of_an_authority_cell,
    )
    rejects("NEGATIVE — a CURATED exclusion of a tier=scored cell", _curated_exclusion_of_a_scored_cell)
    rejects(
        "NEGATIVE — an exclusion that does not record what it deletes",
        _exclusion_that_does_not_say_what_it_deletes,
    )

    # The same exclusion is LEGAL when derived — a <PLACEHOLDER> token is not a repo
    # module and has no code that could hold authority.
    derived_authority = copy.deepcopy(good)
    derived_authority["excluded"][0]["would_be_authority"] = "gate_size"
    checks.append((
        "POSITIVE CONTROL — a DERIVED placeholder exclusion is not refused by the "
        "authority rule",
        validate_structure(derived_authority, valid_validation_statuses=statuses) == [],
    ))

    # ---- overlay negative controls ----
    known = ["engine/a.py::prog"]

    def overlay_rejects(label: str, overlay: dict) -> None:
        checks.append((label, bool(validate_overlay(overlay, known))))

    overlay_rejects(
        "NEGATIVE — overlay key outside the four-key allowlist",
        {"schema_version": 1, "engines": {"engine/a.py::prog": {"notes": "hi"}}},
    )
    overlay_rejects(
        "NEGATIVE — overlay writing a DERIVED field (authority)",
        {"schema_version": 1, "engines": {"engine/a.py::prog": {"authority": "gate_size"}}},
    )
    overlay_rejects(
        "NEGATIVE — overlay writing a DERIVED field (ledger)",
        {"schema_version": 1, "engines": {"engine/a.py::prog": {"ledger": "data/x.jsonl"}}},
    )
    overlay_rejects(
        "NEGATIVE — orphan overlay row for an unknown engine_id",
        {"schema_version": 1, "engines": {"engine/ghost.py::prog": {"not_an_engine": {"reason": "x"}}}},
    )
    overlay_rejects(
        "NEGATIVE — overlay claiming graded_by_design='yes'",
        {"schema_version": 1, "engines": {"engine/a.py::prog": {"graded_by_design": {"value": "yes", "reason": "r"}}}},
    )
    overlay_rejects(
        "NEGATIVE — overlay writing the safe default 'no — not yet'",
        {"schema_version": 1, "engines": {"engine/a.py::prog": {"graded_by_design": {"value": "no — not yet", "reason": "r"}}}},
    )
    overlay_rejects(
        "NEGATIVE — graded_by_design override with no reason",
        {"schema_version": 1, "engines": {"engine/a.py::prog": {"graded_by_design": {"value": "no — descriptive"}}}},
    )
    overlay_rejects(
        "NEGATIVE — output_class with no rationale",
        {"schema_version": 1, "engines": {"engine/a.py::prog": {"output_class": {"value": "predictive"}}}},
    )
    overlay_rejects(
        "NEGATIVE — output_class outside the 7-class vocabulary",
        {"schema_version": 1, "engines": {"engine/a.py::prog": {"output_class": {"value": "vibes", "rationale": "r"}}}},
    )
    overlay_rejects(
        "NEGATIVE — terminal validation_state with no DNR citation",
        {"schema_version": 1, "engines": {"engine/a.py::prog": {"validation_state": {"value": "falsified", "ratified_by": "x", "date": "2026-08-12"}}}},
    )
    overlay_rejects(
        "NEGATIVE — DNR citation by row number instead of DNR:<KEY>",
        {"schema_version": 1, "engines": {"engine/a.py::prog": {"validation_state": {"value": "falsified", "dnr_key": "row 42", "ratified_by": "x", "date": "2026-08-12"}}}},
    )
    overlay_rejects(
        "NEGATIVE — overlay promoting a NON-terminal validation_state",
        {"schema_version": 1, "engines": {"engine/a.py::prog": {"validation_state": {"value": "validated", "dnr_key": "DNR:X", "ratified_by": "x", "date": "2026-08-12"}}}},
    )
    overlay_rejects(
        "NEGATIVE — not_an_engine with an empty reason",
        {"schema_version": 1, "engines": {"engine/a.py::prog": {"not_an_engine": {"reason": ""}}}},
    )
    # CENSUS-DELETION HATCH. `not_an_engine: {reason: "nah"}` used to remove an
    # authority-bearing engine with both laws green (reproduced 2026-08-12: 378 -> 376
    # engines, gate_size 5 -> 4, findings 109 -> 106, validate_overlay() == []). The most
    # destructive of the four keys was the least gated; it now matches validation_state.
    overlay_rejects(
        "NEGATIVE — not_an_engine with a 3-character reason (the census-deletion hatch)",
        {"schema_version": 1, "engines": {"engine/a.py::prog": {"not_an_engine": {
            "reason": "nah", "ratified_by": "someone", "date": "2026-08-12"}}}},
    )
    overlay_rejects(
        "NEGATIVE — not_an_engine with a real reason but NO ratified_by/date",
        {"schema_version": 1, "engines": {"engine/a.py::prog": {"not_an_engine": {
            "reason": "this cell is an operational rail with no intelligence output at all"}}}},
    )
    overlay_rejects(
        "NEGATIVE — not_an_engine citing a DNR row by number instead of DNR:<KEY>",
        {"schema_version": 1, "engines": {"engine/a.py::prog": {"not_an_engine": {
            "reason": "this cell is an operational rail with no intelligence output at all",
            "dnr_key": "row 42", "ratified_by": "operator", "date": "2026-08-12"}}}},
    )
    checks.append((
        "POSITIVE CONTROL — a fully cited not_an_engine exclusion is accepted",
        validate_overlay(
            {"schema_version": 1, "engines": {"engine/a.py::prog": {"not_an_engine": {
                "reason": "this cell is an operational rail with no intelligence output at all",
                "dnr_key": "DNR:KILL-EXAMPLE", "ratified_by": "operator", "date": "2026-08-12"}}}},
            known,
        ) == [],
    ))
    # Issue-12 branch, now REACHABLE: with a restricted status set the overlay may not
    # ratify a terminal state species_registry.py no longer recognises.
    checks.append((
        "NEGATIVE — terminal ratification of a state the species registry no longer has",
        bool(validate_overlay(
            {"schema_version": 1, "engines": {"engine/a.py::prog": {"validation_state": {
                "value": "falsified", "dnr_key": "DNR:X", "ratified_by": "x", "date": "2026-08-12"}}}},
            known,
            valid_validation_statuses=["phase0", "accruing", "validated", "retired"],
        )),
    ))

    # ---- overlay POSITIVE controls: legal curation must be ACCEPTED ----
    checks.append((
        "POSITIVE CONTROL — a legal output_class ratification is accepted",
        validate_overlay(
            {"schema_version": 1, "engines": {"engine/a.py::prog": {"output_class": {"value": "ranking", "rationale": "orders a user-visible board"}}}},
            known,
        ) == [],
    ))
    checks.append((
        "POSITIVE CONTROL — the one legal graded_by_design transition is accepted",
        validate_overlay(
            {"schema_version": 1, "engines": {"engine/a.py::prog": {"graded_by_design": {"value": "no — descriptive", "reason": "reconciliation only"}}}},
            known,
        ) == [],
    ))
    checks.append((
        "POSITIVE CONTROL — a fully cited terminal ratification is accepted",
        validate_overlay(
            {"schema_version": 1, "engines": {"engine/a.py::prog": {"validation_state": {"value": "retired", "dnr_key": "DNR:KILL-EXAMPLE", "ratified_by": "operator", "date": "2026-08-12"}}}},
            known,
        ) == [],
    ))

    # ---- content-audit controls (law B) ----
    c1 = copy.deepcopy(good)
    c1["engines"][0]["evidence_ref"] = None
    c1["engines"][0]["artifacts"][0]["qual_ladder_ref"] = None
    c1["engines"][0]["artifacts"][0]["qual_ladder_ref_resolution"] = None
    c1["engines"][0]["authority_evidence"]["unevidenced_artifacts"] = ["art-a"]
    codes = {f.code for f in audit_content(c1)}
    checks.append(("NEGATIVE — C-1: an authority-bearing artifact with no prereg pointer is flagged", "AUTHORITY_WITHOUT_EVIDENCE" in codes))

    # THE BLOCKER. A union over the cell clears on ANY sibling's ref, so a gate_size
    # artifact with no pointer went unflagged whenever a decorative `display` sibling
    # carried one. Reproduced live 2026-08-12 on
    # scripts/build_basket_washout_state.py::blocked-entry-override.
    sibling = copy.deepcopy(good)
    row = sibling["engines"][0]
    row["artifacts"][0]["qual_ladder_ref"] = None
    row["artifacts"][0]["qual_ladder_ref_resolution"] = None
    row["artifacts"].append({
        "id": "art-decorative", "path": "site/chip.json", "tier": "display",
        "horizon_role": "context", "freshness_sla_hours": 24, "storage": "git",
        "scored_path_surfaces": [], "qual_ladder_ref": "research/UNRELATED_DISPLAY_NOTE.md",
        "qual_ladder_ref_resolution": "repo_path", "artifact_authority": "display",
    })
    row["evidence_ref"] = ["research/UNRELATED_DISPLAY_NOTE.md"]  # the union is NON-empty
    row["authority_evidence"]["unevidenced_artifacts"] = ["art-a"]
    codes = {f.code for f in audit_content(sibling)}
    checks.append((
        "NEGATIVE — C-1 fires even when a DISPLAY sibling's ref makes evidence_ref non-null",
        "AUTHORITY_WITHOUT_EVIDENCE" in codes,
    ))

    # "No pointer" and "pointer at nothing" are different defects with different heals.
    unresolvable = copy.deepcopy(good)
    unresolvable["engines"][0]["artifacts"][0]["qual_ladder_ref"] = "lol/does_not_exist.md"
    unresolvable["engines"][0]["artifacts"][0]["qual_ladder_ref_resolution"] = "unresolved"
    unresolvable["engines"][0]["authority_evidence"]["unresolvable_artifacts"] = ["art-a"]
    unresolvable["engines"][0]["authority_evidence"]["unevidenced_artifacts"] = ["art-a"]
    codes = {f.code for f in audit_content(unresolvable)}
    checks.append((
        "NEGATIVE — a qual_ladder_ref pointing at a NON-EXISTENT file is reported",
        "AUTHORITY_EVIDENCE_UNRESOLVABLE" in codes and "AUTHORITY_WITHOUT_EVIDENCE" in codes,
    ))

    checks.append((
        "POSITIVE CONTROL — a ref that IS a config/qual_ladder.yml key resolves",
        resolve_qual_ladder_ref(
            "altdata.action", qual_ladder_keys={"altdata.action"}, path_exists=lambda p: False
        ) == "qual_ladder_key",
    ))
    checks.append((
        "POSITIVE CONTROL — a ref that IS an existing repo path resolves",
        resolve_qual_ladder_ref(
            "research/PREREG.md", qual_ladder_keys=set(), path_exists=lambda p: True
        ) == "repo_path",
    ))
    checks.append((
        "NEGATIVE — a ref that is neither a ladder key nor an existing path is 'unresolved'",
        resolve_qual_ladder_ref(
            "lol/nope.md", qual_ladder_keys={"altdata.action"}, path_exists=lambda p: False
        ) == "unresolved",
    ))
    checks.append((
        "POSITIVE CONTROL — an UNPROBED ref is 'unchecked', never 'unresolved' "
        "('could not look' != 'looked and found nothing')",
        resolve_qual_ladder_ref("research/PREREG.md") == "unchecked",
    ))

    # An EXCLUDED cell that would have held authority still reports its findings —
    # otherwise a three-word overlay reason silently deflates the backlog T1 exists for.
    hatched = copy.deepcopy(good)
    hatched["excluded"][0].update({
        "source": "curated",
        "would_be_authority": "gate_size",
        "would_be_unevidenced_artifacts": ["art-b"],
        "would_be_output_class_reason": "required_but_uncurated",
    })
    codes = {f.code for f in audit_content(hatched)}
    checks.append((
        "NEGATIVE — an EXCLUDED authority-bearing cell still reports C-1 and the missing "
        "metric contract (an exclusion cannot buy silence)",
        "AUTHORITY_WITHOUT_EVIDENCE" in codes and "OUTPUT_CLASS_MISSING" in codes,
    ))

    unbound = copy.deepcopy(good)
    unbound["meta"]["unbound_species"] = [
        {"species_id": "F3_ANTICHASE", "validation_status": "accruing"}
    ]
    codes = {f.code for f in audit_content(unbound)}
    checks.append(("NEGATIVE — a species bound to no engine ledger is named", "SPECIES_UNBOUND" in codes))

    could_not_look = copy.deepcopy(good)
    could_not_look["meta"]["unbound_species"] = None
    codes = {f.code for f in audit_content(could_not_look)}
    checks.append((
        "POSITIVE CONTROL — an UNREAD species store reports no unbound species "
        "('could not look' != 'looked and found nothing')",
        "SPECIES_UNBOUND" not in codes,
    ))

    display_ok = copy.deepcopy(good)
    display_ok["engines"][0]["authority"] = "display"
    display_ok["engines"][0]["artifacts"][0]["artifact_authority"] = "display"
    display_ok["engines"][0]["evidence_ref"] = None
    display_ok["engines"][0]["authority_evidence"]["unevidenced_artifacts"] = []
    codes = {f.code for f in audit_content(display_ok)}
    checks.append(("POSITIVE CONTROL — a display engine with no evidence_ref is NOT flagged", "AUTHORITY_WITHOUT_EVIDENCE" not in codes))

    oc = copy.deepcopy(good)
    oc["engines"][0]["output_class"] = None
    oc["engines"][0]["output_class_reason"] = "required_but_uncurated"
    codes = {f.code for f in audit_content(oc)}
    checks.append(("NEGATIVE — missing output_class on a gate-tripping engine is flagged", "OUTPUT_CLASS_MISSING" in codes))

    quiet = copy.deepcopy(good)
    quiet["engines"][0]["output_class"] = None
    quiet["engines"][0]["output_class_reason"] = "not_required_display_only"
    codes = {f.code for f in audit_content(quiet)}
    checks.append(("POSITIVE CONTROL — a display-only engine with no output_class is NOT flagged", "OUTPUT_CLASS_MISSING" not in codes))

    stale = copy.deepcopy(good)
    stale["engines"][0]["graded_by_design"] = "no — not yet"
    codes = {f.code for f in audit_content(stale)}
    checks.append(("NEGATIVE — graded_by_design contradicting a real ledger is flagged", "GRADED_BY_DESIGN_CONTRADICTS_LEDGER" in codes))

    # The corpus half — computed at READ time, never from the committed file.
    desk_reg = copy.deepcopy(good)
    desk_reg["engines"][0]["ledger"] = "qledger:ghost_desk"
    desk_reg["engines"][0]["ledger_evidence"] = {
        "rule": 2, "desk": "ghost_desk", "via": None, "shape": None,
    }
    codes = {
        f.code
        for f in audit_corpus(desk_reg, volatile_view(desk_reg, qledger_desk_rows={}))
    }
    checks.append(("NEGATIVE — a registered qledger desk with zero rows is flagged", "LEDGER_DECLARED_BUT_EMPTY" in codes))

    codes = {
        f.code
        for f in audit_corpus(desk_reg, volatile_view(desk_reg, qledger_desk_rows=None))
    }
    checks.append((
        "POSITIVE CONTROL — an UNREAD corpus is not reported as an empty desk "
        "('could not look' != 'looked and found nothing')",
        "LEDGER_DECLARED_BUT_EMPTY" not in codes,
    ))
    codes = {
        f.code
        for f in audit_corpus(
            desk_reg, volatile_view(desk_reg, qledger_desk_rows={"ghost_desk": 88})
        )
    }
    checks.append((
        "POSITIVE CONTROL — a desk WITH rows is not flagged as empty",
        "LEDGER_DECLARED_BUT_EMPTY" not in codes,
    ))
    checks.append((
        "the corpus audit never reads the committed file — a written corpus_rows is "
        "ignored, because it is not supposed to be there at all",
        audit_corpus(desk_reg, None) == [],
    ))

    flag = copy.deepcopy(good)
    flag["engines"][0]["authority_evidence"]["completeness_flag"] = True
    flag["engines"][0]["authority_evidence"]["completeness_detail"] = ["art-a read by scripts/build_site.py"]
    codes = {f.code for f in audit_content(flag)}
    checks.append(("NEGATIVE — the scored_path_surfaces completeness flag is reported", "SCORED_PATH_SURFACES_INCOMPLETE" in codes))

    # ---- the ABSENCE contract, in both directions ----
    checks.append((
        "POSITIVE CONTROL — a clean registry carries no corpus-derived path",
        assert_no_volatile(good) == [],
    ))
    for label, mutate in (
        ("ledger_evidence.corpus_rows", _commit_a_volatile_path),
        ("meta.corpus", _commit_a_volatile_meta_key),
        ("declared_horizon.horizon_d", _commit_a_volatile_horizon),
    ):
        dirty = copy.deepcopy(good)
        mutate(dirty)
        checks.append((
            f"NEGATIVE — assert_no_volatile catches a committed {label}",
            bool(assert_no_volatile(dirty)),
        ))

    # THE TAMPER THAT USED TO BE INVISIBLE. validation_state is the
    # display-only-until-validated axis; the old projection STRIPPED it before comparing,
    # so a hand-edit to "validated" produced byte-identical guard output. It is stable
    # (data/species/registry.json has one commit ever and no automated writer), so it is
    # now committed and equality-guarded like anything else.
    tampered = copy.deepcopy(good)
    tampered["engines"][0]["validation_state"] = "validated"
    checks.append((
        "NEGATIVE — a hand-edited validation_state is a REAL difference, not a stripped one",
        serialise(tampered) != serialise(good) and assert_no_volatile(tampered) == [],
    ))

    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}", flush=True)
        ok = ok and passed
    print(
        f"selftest: {'PASS' if ok else 'FAIL'} "
        f"({sum(1 for _, p in checks if p)}/{len(checks)})",
        flush=True,
    )
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--strict", action="store_true", help="law (B) also exits non-zero")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return _selftest()

    root: Path = args.root
    registry_path = root / REGISTRY_REL

    if not registry_path.exists():
        if args.json:
            print(
                json.dumps(
                    {"registry_absent": True, "integrity": None, "content": None}, indent=2
                ),
                flush=True,
            )
        else:
            print(
                f"::notice title={TITLE_A}::registry absent, not audited: {registry_path}",
                flush=True,
            )
        return 0

    violations, committed, report = check_integrity(root)
    findings = audit_content(committed) if committed else []
    if committed and report:
        # The corpus half runs against the LIVE claim store, computed fresh — it is never
        # read from the committed file, because nothing corpus-derived is in there.
        findings = findings + audit_corpus(
            committed,
            volatile_view(
                committed,
                qledger_desk_rows=report["qledger_desk_rows"],
                qledger_desk_horizons=report["qledger_desk_horizons"],
            ),
        )
        findings.sort(key=lambda f: (f.code, f.engine_id))
    stable_complete = bool(report and report["stable_complete"])

    if args.json:
        print(
            json.dumps(
                {
                    "registry_absent": False,
                    "stable_complete": stable_complete,
                    "qledger_read": bool(report and report["qledger_read"]),
                    "integrity": violations,
                    "content": [
                        {"code": f.code, "engine_id": f.engine_id, "detail": f.detail}
                        for f in findings
                    ],
                },
                indent=2,
            ),
            flush=True,
        )
        return 1 if violations else 0

    for violation in violations:
        # Bare print, line-start, flushed — see module docstring.
        print(f"::error title={TITLE_A}::{violation}", flush=True)

    # ANNOTATION BUDGET. 154 findings on the 2026-08-12 corpus; emitting one annotation
    # each would bury the actionable ones and train readers to ignore the lane — the same
    # way a fleet-wide red gets routed around. So C-1 (the defect this registry exists to
    # surface, and the one with a concrete named heal) is annotated PER ENGINE, and every
    # other code is annotated ONCE with its count. Full detail always goes to stdout, so
    # nothing is hidden — only re-ranked.
    per_engine = [f for f in findings if f.code == "AUTHORITY_WITHOUT_EVIDENCE"]
    aggregated: dict[str, int] = {}
    for finding in findings:
        if finding.code != "AUTHORITY_WITHOUT_EVIDENCE":
            aggregated[finding.code] = aggregated.get(finding.code, 0) + 1

    for finding in per_engine:
        print(
            f"::warning title={TITLE_B}::[{finding.code}] {finding.engine_id}: {finding.detail}",
            flush=True,
        )
    for code, count in sorted(aggregated.items()):
        print(
            f"::warning title={TITLE_B}::[{code}] {count} engine(s) — detail in "
            f"{DOC_REL.as_posix()} and on stdout below",
            flush=True,
        )
    for finding in findings:
        if finding.code != "AUTHORITY_WITHOUT_EVIDENCE":
            print(f"  [{finding.code}] {finding.engine_id}: {finding.detail}", flush=True)

    if not stable_complete:
        print(
            f"::notice title={TITLE_A}::a STABLE input could not be read, so the drift "
            f"comparison was SKIPPED (this is 'could not look', not 'looked and clean')",
            flush=True,
        )
    elif report and not report["qledger_read"]:
        print(
            f"::notice title={TITLE_A}::the claim corpus could not be read — the read-time "
            f"corpus audit is NULL, not empty. The drift comparison is unaffected: the "
            f"committed artifact carries no corpus-derived field",
            flush=True,
        )

    n_engines = len(committed.get("engines") or []) if committed else 0
    print(
        f"intelligence registry: {n_engines} engines, {len(violations)} integrity "
        f"violation(s), {len(findings)} content finding(s)",
        flush=True,
    )

    if violations:
        return 1
    if args.strict and findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
