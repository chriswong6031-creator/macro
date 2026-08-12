"""scripts/check_intelligence_registry.py — the engine-registry gate (Eval OS T1).

Enforces TWO house laws, deliberately split because they have different blast radii and
therefore must have different severities. Collapsing them into one entry would force one
severity, so either integrity ships too weak to protect the registry or the pre-existing
C-1 backlog reds main fleet-wide on arrival.

(A) governance.intelligence_registry_integrity — HARD, wired to pr_ci.
    Properties of the registry's OWN FILES only:
      * the committed structural projection differs from a fresh regeneration (drift)
      * regeneration is not idempotent
      * an overlay key outside the four-key allowlist, or a forbidden derived key
      * an overlay row for an engine_id the builder did not generate (orphan)
      * an unknown enum value, a missing required field, a null ledger
      * an exclusion with an empty or missing reason
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

WHY THE DRIFT COMPARISON IS A PROJECTION, NOT THE WHOLE FILE
-----------------------------------------------------------
`data/qledger/claims.jsonl` is append-only and `data/species/registry.json` moves
independently of any PR. Pinning the whole file by equality is a SCHEDULED red: the first
nightly row written to a currently-empty desk flips a field and reds every open PR. So the
HARD law compares `structural_projection()` — the file with `meta.volatile_fields` paths
stripped — and a stale corpus snapshot is a warn-tier content finding. The volatile set is
declared inside the artifact, so the projection is self-describing and this guard cannot
silently narrow it.

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
    audit_content,
    serialise,
    structural_projection,
    validate_overlay,
    validate_structure,
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

def check_integrity(root: Path) -> tuple[list[str], dict | None, bool]:
    """Returns (violations, committed_registry, corpus_complete)."""
    registry_path = root / REGISTRY_REL
    if not registry_path.exists():
        return ([], None, False)

    try:
        committed = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ([f"{REGISTRY_REL}: not valid JSON ({exc})"], None, False)

    violations = validate_structure(
        committed, valid_validation_statuses=VALID_VALIDATION_STATUSES
    )

    overlay_path = root / OVERLAY_REL
    overlay = (
        yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
        if overlay_path.exists()
        else None
    )
    violations += validate_overlay(
        overlay,
        [r.get("engine_id") for r in committed.get("engines") or []]
        + [r.get("engine_id") for r in committed.get("excluded") or []],
        valid_validation_statuses=VALID_VALIDATION_STATUSES,
    )

    # Drift + idempotence. Regenerating requires the derivation inputs; if a data store
    # is unreadable we say so and skip rather than reporting a false drift.
    regenerated, _ = build(root)
    corpus = regenerated["meta"]["corpus"]
    corpus_complete = bool(corpus["species_read"] and corpus["qledger_read"])

    if structural_projection(regenerated) != structural_projection(committed):
        violations.append(
            f"{REGISTRY_REL}: committed structural projection differs from a fresh "
            f"regeneration — HEAL: python3 scripts/build_intelligence_registry.py"
        )

    # Idempotence: the generator must be a function, not a process with memory.
    again, _ = build(root)
    if serialise(again) != serialise(regenerated):
        violations.append("generator is NOT idempotent: two consecutive builds differ")

    doc_path = root / DOC_REL
    expected_doc = render_doc(regenerated, audit_content(regenerated))
    if not doc_path.exists():
        violations.append(f"{DOC_REL}: missing — HEAL: python3 scripts/build_intelligence_registry.py")
    elif corpus_complete and doc_path.read_text(encoding="utf-8") != expected_doc:
        violations.append(
            f"{DOC_REL}: stale — HEAL: python3 scripts/build_intelligence_registry.py"
        )

    return (violations, committed, corpus_complete)


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
            "volatile_fields": ["validation_state"],
            "volatile_meta_keys": ["corpus"],
            "authority_order": ["display", "engine_input", "user_ranking", "gate_size"],
            "corpus": {"species_read": True, "qledger_read": True, "n_species": 0, "n_desks": 0},
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
                        "artifact_authority": "gate_size",
                    }
                ],
                "consumers": [],
                "output_class": "predictive",
                "output_class_reason": "curated: x",
                "authority": "gate_size",
                "authority_evidence": {
                    "rule": "a",
                    "artifact_id": "art-a",
                    "surfaces": [],
                    "completeness_flag": False,
                    "completeness_detail": [],
                },
                "ledger": "data/a_ledger.jsonl",
                "ledger_evidence": {
                    "rule": 1,
                    "desk": None,
                    "via": None,
                    "corpus_rows": None,
                    "corpus_checked": False,
                },
                "graded_by_design": "yes",
                "graded_by_design_source": "derived: has a ledger",
                "declared_horizon": {
                    "horizon_role": ["context"],
                    "horizon_d": None,
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
    codes = {f.code for f in audit_content(c1)}
    checks.append(("NEGATIVE — C-1: authority>display with a null evidence_ref is flagged", "AUTHORITY_WITHOUT_EVIDENCE" in codes))

    display_ok = copy.deepcopy(good)
    display_ok["engines"][0]["authority"] = "display"
    display_ok["engines"][0]["artifacts"][0]["artifact_authority"] = "display"
    display_ok["engines"][0]["evidence_ref"] = None
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

    empty_desk = copy.deepcopy(good)
    empty_desk["engines"][0]["ledger_evidence"] = {
        "rule": 2, "desk": "ghost_desk", "via": None, "corpus_rows": 0, "corpus_checked": True,
    }
    codes = {f.code for f in audit_content(empty_desk)}
    checks.append(("NEGATIVE — a registered qledger desk with zero rows is flagged", "LEDGER_DECLARED_BUT_EMPTY" in codes))

    unread = copy.deepcopy(good)
    unread["engines"][0]["ledger_evidence"] = {
        "rule": 2, "desk": "ghost_desk", "via": None, "corpus_rows": None, "corpus_checked": False,
    }
    codes = {f.code for f in audit_content(unread)}
    checks.append((
        "POSITIVE CONTROL — an UNREAD corpus is not reported as an empty desk "
        "('could not look' != 'looked and found nothing')",
        "LEDGER_DECLARED_BUT_EMPTY" not in codes,
    ))

    flag = copy.deepcopy(good)
    flag["engines"][0]["authority_evidence"]["completeness_flag"] = True
    flag["engines"][0]["authority_evidence"]["completeness_detail"] = ["art-a read by scripts/build_site.py"]
    codes = {f.code for f in audit_content(flag)}
    checks.append(("NEGATIVE — the scored_path_surfaces completeness flag is reported", "SCORED_PATH_SURFACES_INCOMPLETE" in codes))

    # ---- the projection must actually STRIP, and must not strip everything ----
    projected = structural_projection(good)
    checks.append((
        "structural projection strips the declared volatile field",
        "validation_state" not in projected["engines"][0],
    ))
    checks.append((
        "structural projection keeps the structural fields",
        projected["engines"][0].get("authority") == "gate_size"
        and projected["engines"][0].get("ledger") == "data/a_ledger.jsonl",
    ))
    volatile_only = copy.deepcopy(good)
    volatile_only["engines"][0]["validation_state"] = "validated"
    checks.append((
        "a volatile-only difference does NOT read as structural drift (no scheduled red)",
        structural_projection(volatile_only) == structural_projection(good),
    ))
    structural_diff = copy.deepcopy(good)
    structural_diff["engines"][0]["authority"] = "display"
    checks.append((
        "NEGATIVE — a STRUCTURAL difference IS caught by the projection",
        structural_projection(structural_diff) != structural_projection(good),
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

    violations, committed, corpus_complete = check_integrity(root)
    findings = audit_content(committed) if committed else []

    if args.json:
        print(
            json.dumps(
                {
                    "registry_absent": False,
                    "corpus_complete": corpus_complete,
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

    if not corpus_complete:
        print(
            f"::notice title={TITLE_A}::a data store could not be read — corpus-sourced "
            f"fields were NOT compared (this is 'could not look', not 'looked and clean')",
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
