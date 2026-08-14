"""scripts/check_intelligence_registry.py — the engine-registry structural validator (T1).

WHAT THIS IS
------------
A PURE STRUCTURAL VALIDATOR over a registry it derives IN MEMORY. There is no committed
``data/intelligence_registry.json`` and no generated Markdown mirror, so this script has no
drift comparison, no ``--check`` equality mode and no "stale artifact" violation. It cannot
be reddened by an event no PR author caused: nothing it reads is pinned by equality.

Two earlier rounds shipped exactly that pin — first against ``data/qledger/claims.jsonl``
(append-only, 13 commits in 14 days), then against ``config/synapse.yml`` (26 commits in 14
days, ALL of them inside the window). Both were scheduled fleet-wide reds. The third input
that looked stable, ``data/species/registry.json`` with "one commit in its whole history",
was a SHALLOW-CLONE artifact — ``git rev-parse --is-shallow-repository`` is true here and
only 1126 commits are reachable, so that count was never evidence. There is no stable input
to pin against, so nothing is pinned.

THE INVARIANTS (law ``epistemics.engine_authority_evidence``)
------------------------------------------------------------
  1. PARTITION — every synapse artifact maps to exactly one engine or to exactly one
     explicit ``not_an_engine`` exclusion that records what it deletes.
  2. OVERLAY — no key outside the four-key allowlist, no DERIVED key, no orphan row, no
     ``graded_by_design: yes`` assertion, and no removal of an authority-bearing or
     evaluated cell via ``not_an_engine``.
  3. ATTRIBUTION — every authority value names the derivation rule AND the artifact(s)
     that produced it, and those artifacts really carry that authority.
  4. C-1 — every artifact above ``display`` authority whose ``qual_ladder_ref`` is MISSING
     or UNRESOLVABLE is REPORTED. ``unchecked`` (the resolver had no inputs) is its own
     bucket and is never counted as evidence.

FAIL CLOSED
-----------
A previous round printed "0 integrity violation(s)" when it could not read its inputs —
"I could not look" rendered as "I looked and it was clean", in the one line a CI reader
sees. The summary line here ALWAYS carries an ``inputs=`` clause; when anything was
unreadable it reads ``inputs=INCOMPLETE`` and NAMES what was missed.

AN INCOMPLETE READ EXITS NON-ZERO ON EVERY RUN, WITH OR WITHOUT ``--strict`` (ruling
2026-08-14). It is a RUN-LEVEL defect — the guard failed to do its job — not a condition of
the corpus, so it is not the kind of thing an advisory tier exists to soften. Making it
conditional on a flag nobody passes in CI meant the fail-closed channel printed a warning
and returned success, which is the same green a clean run returns. Structural violations
exit non-zero for the same reason: they are properties of the derivation and of the
hand-edited overlay, green by construction on arrival, so they cannot fire fleet-wide for
nobody's fault. ``--strict`` keeps its own distinct meaning — content FINDINGS also red —
and stays reserved for T7's promotion era.

SEVERITY
--------
Registered at ``warn``, not ``hard``, deliberately — see the entry's notes in
``config/house_law_checks.yml``. The dominant output is the pre-existing C-1 backlog, and a
gate that reds the fleet on first wiring for a condition nobody introduced gets routed
around instead of obeyed. ``--strict`` is the promotion lever T7 pulls once the backlog is
drained. That leniency covers FINDINGS only: a run that could not read its inputs is not a
lenient case, it is a run that did not happen.

Annotations are emitted with a bare ``print`` and ``flush=True`` per CLAUDE.md §"GitHub
annotations must START the line" — a logger would prefix the line and GitHub would silently
drop it.

Usage
-----
  python3 scripts/check_intelligence_registry.py            # violations OR an INCOMPLETE
                                                            #   input set exit 1
  python3 scripts/check_intelligence_registry.py --strict   # content findings also exit 1
  python3 scripts/check_intelligence_registry.py --json
  python3 scripts/check_intelligence_registry.py --selftest
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.intelligence_registry import (  # noqa: E402
    audit_content,
    build_registry,
    resolve_qual_ladder_ref,
    validate_overlay,
    validate_structure,
)
from engine.species_registry import VALID_VALIDATION_STATUSES  # noqa: E402
from scripts import build_intelligence_registry as builder  # noqa: E402
from scripts.build_intelligence_registry import build  # noqa: E402

TITLE = "engine-authority-evidence"


# ---------------------------------------------------------------------------
# Selftest fixture — the C-1 derivation runs FOR REAL against it
# ---------------------------------------------------------------------------
#
# The negative controls below go through build_registry(), NOT through a hand-written
# registry dict with `unevidenced_artifacts` pre-filled. A control whose input already
# contains the answer cannot fail when the derivation that computes the answer is deleted
# — the house's "a receipt derived from what it checks cannot fail" trap. Deleting the
# `unevidenced` computation in engine/intelligence_registry.py makes --selftest FAIL.

_FIXTURE_SYNAPSE: dict[str, Any] = {
    "artifacts": {
        # An authority-bearing artifact with NO prereg pointer — the C-1 exemplar.
        "gate-art": {
            "producer": "engine/a.py", "owner_program": "prog", "tier": "scored",
            "path": "data/a_ledger.jsonl", "horizon_role": "context",
            "freshness_sla_hours": 24, "storage": "git", "consumers": [],
            "qual_ladder_ref": None,
        },
        # A DECORATIVE sibling in the same cell that DOES carry a ref. A cell-wide union
        # would clear the finding on this alone; the per-artifact gate must not.
        "chip-art": {
            "producer": "engine/a.py", "owner_program": "prog", "tier": "display",
            "path": "site/chip.json", "horizon_role": "context",
            "freshness_sla_hours": 24, "storage": "git", "consumers": [],
            "qual_ladder_ref": "research/UNRELATED_DISPLAY_NOTE.md",
        },
        # A scored artifact whose ref points at a DIRECTORY. Not a prereg.
        "dir-ref-art": {
            "producer": "engine/c.py", "owner_program": "prog", "tier": "scored",
            "path": "data/c.json", "horizon_role": "context",
            "freshness_sla_hours": 24, "storage": "git", "consumers": [],
            "qual_ladder_ref": "research/",
        },
        # The same defect without the trailing slash — the probe must answer "not a file".
        "dir-ref-art-bare": {
            "producer": "engine/d.py", "owner_program": "prog", "tier": "scored",
            "path": "data/d.json", "horizon_role": "context",
            "freshness_sla_hours": 24, "storage": "git", "consumers": [],
            "qual_ladder_ref": "research",
        },
        # A properly evidenced authority-bearing artifact — the positive control.
        "good-art": {
            "producer": "engine/e.py", "owner_program": "prog", "tier": "scored",
            "path": "data/e.json", "horizon_role": "context",
            "freshness_sla_hours": 24, "storage": "git", "consumers": [],
            "qual_ladder_ref": "research/PREREG.md",
        },
        # A placeholder producer — the DERIVED exclusion.
        "manual-art": {
            "producer": "<MANUAL>", "owner_program": "prog", "tier": "display",
            "path": "site/manual.json", "horizon_role": "context",
            "freshness_sla_hours": 24, "storage": "git", "consumers": [],
        },
    }
}

#: A FILE-ONLY probe. ``research/`` and ``research`` are directories and must answer False;
#: that is the whole point of the tightening from ``path_exists`` to ``file_exists``.
_FIXTURE_FILES = frozenset({"research/PREREG.md", "research/UNRELATED_DISPLAY_NOTE.md"})


#: DEFAULT-VS-NULL SENTINEL. ``None`` is a MEANINGFUL value for several build_registry
#: inputs — it is the epistemic null, "the store could not be read". A helper that spells
#: its default as ``None`` cannot express that value at all: `_fixture_registry(species=None)`
#: silently became `species=[]`, so the control asserting that an UNREAD species store
#: reports a NULL validation_state was handed a store that HAD been read and found empty.
#: The harness was performing the exact substitution the assertion exists to forbid. The
#: sentinel keeps "argument omitted" and "argument is the null" distinguishable.
_DEFAULT = object()


def _fixture_registry(
    *,
    synapse: dict[str, Any] | None = None,
    overlay: dict[str, Any] | None = None,
    qual_ladder_keys: Any = _DEFAULT,
    file_exists: Any = _DEFAULT,
    species: Any = _DEFAULT,
    qledger_desk_rows: Any = _DEFAULT,
) -> dict[str, Any]:
    """Derive the fixture registry FOR REAL. Every selftest control starts here.

    Every keyword defaults to ``_DEFAULT``, never to ``None``, so a caller can pass the
    epistemic null through to :func:`build_registry` unchanged.
    """
    if qual_ladder_keys is _DEFAULT:
        qual_ladder_keys = frozenset()
    if file_exists is _DEFAULT:
        # The probe is only supplied alongside a ladder-key set; when the caller asked for
        # the unprobed state (`qual_ladder_keys=None`) it must stay unprobed.
        file_exists = (
            None if qual_ladder_keys is None else (lambda p: p in _FIXTURE_FILES)
        )
    return build_registry(
        synapse=synapse if synapse is not None else _FIXTURE_SYNAPSE,
        overlay=overlay,
        article2_modules=(),
        species=[] if species is _DEFAULT else species,
        qual_ladder_keys=qual_ladder_keys,
        file_exists=file_exists,
        qledger_desk_rows=None if qledger_desk_rows is _DEFAULT else qledger_desk_rows,
    )


def _codes(registry: dict[str, Any]) -> set[str]:
    return {f.code for f in audit_content(registry)}


def _codes_for(registry: dict[str, Any], engine_id: str) -> set[str]:
    return {f.code for f in audit_content(registry) if f.engine_id == engine_id}


# ---------------------------------------------------------------------------
# Fixture ROOT — ONE fixture source, shared by --selftest and by the test suites
# ---------------------------------------------------------------------------
#
# The in-memory fixtures above exercise the DERIVATION. Everything that is a property of
# FILE I/O — the sparse-worktree ladder, the fail-closed channel, the exit code, a
# malformed store — needs a real directory, so this writes the smallest root that reads
# COMPLETE. A control then flips exactly one input and can attribute the result to that
# flip.
#
# The suites IMPORT this rather than growing their own copy. Two fixture corpora is how
# two definitions of "a complete input set" drift apart, and the one that drifts is
# always the one the gate is not run against.
#
# It also gives the suites a C-1 finding and a derived exclusion BY CONSTRUCTION, which is
# what let the live-corpus assertions move off config/synapse.yml: a test that needs "at
# least one unevidenced authority artifact" must not be asking the live tree for one — the
# C-1 backlog is the thing T7 exists to DRAIN, and draining it would have reddened the lane
# that reported it.

#: Everything a caller needs to address the fixture without re-deriving the ids.
FIXTURE_PRODUCER = "engine/fixture_gate.py"
FIXTURE_PROGRAM = "fixture-prog"
FIXTURE_ENGINE_ID = f"{FIXTURE_PRODUCER}::{FIXTURE_PROGRAM}"
FIXTURE_EXCLUDED_ENGINE_ID = f"<MANUAL>::{FIXTURE_PROGRAM}"

#: One authority-bearing artifact with NO qual_ladder_ref (the C-1 exemplar) and one
#: placeholder-producer artifact (the DERIVED exclusion, which is what makes the
#: pre-exclusion cell partition observably different from the built engine ids).
_FIXTURE_ROOT_SYNAPSE = """\
meta:
  schema_version: 1
artifacts:
  fixture-gate:
    path: data/fixture_gate.json
    format: json
    producer: engine/fixture_gate.py
    owner_program: fixture-prog
    cadence: daily-engine
    storage: git
    asof_field: asof
    freshness_sla_hours: 24
    schema: fixture
    tier: scored
    horizon_role: context
    consumers: []
  fixture-manual-chip:
    path: site/fixture_manual.json
    format: json
    producer: <MANUAL>
    owner_program: fixture-prog
    cadence: manual
    storage: git
    asof_field: asof
    freshness_sla_hours: 24
    schema: fixture
    tier: display
    horizon_role: context
    consumers: []
"""

_FIXTURE_ROOT_CLAIMS = '{"desk": "fixture_desk", "horizon_d": 21, "direction": 1}\n'
_FIXTURE_ROOT_OVERLAY = "schema_version: 1\nengines: {}\n"
_FIXTURE_ROOT_QUAL_LADDER = "fixture.ladder:\n  note: a fixture prereg ladder key\n"
_FIXTURE_ROOT_SPECIES = '{"species": []}\n'
_FIXTURE_ROOT_PRODUCER_SOURCE = '"""Fixture producer. Imports no qledger, registers no desk."""\n'


def write_fixture_root(
    root: Path,
    *,
    synapse: str | None = None,
    claims: str | None = None,
    overlay: str | None = None,
    qual_ladder: str | None = None,
    species: str | None = None,
) -> Path:
    """Materialise a COMPLETE fixture root at ``root`` and return it.

    Every input is overridable AS TEXT, because the states worth controlling for are
    exactly the ones no object can express: bytes that do not parse. Passing ``""`` writes
    an empty file (a real state); the default is used only when the argument is omitted.

    ``root`` should be a fresh directory. The builder caches reads per ``(root, rel)``
    within a process, so reusing one directory for two variants would serve the first
    variant's text to the second — a control that silently tests nothing.
    """
    root.mkdir(parents=True, exist_ok=True)
    files = {
        "config/synapse.yml": _FIXTURE_ROOT_SYNAPSE if synapse is None else synapse,
        "config/intelligence_registry_overlay.yml": (
            _FIXTURE_ROOT_OVERLAY if overlay is None else overlay
        ),
        "config/qual_ladder.yml": (
            _FIXTURE_ROOT_QUAL_LADDER if qual_ladder is None else qual_ladder
        ),
        "data/species/registry.json": _FIXTURE_ROOT_SPECIES if species is None else species,
        "data/qledger/claims.jsonl": _FIXTURE_ROOT_CLAIMS if claims is None else claims,
        FIXTURE_PRODUCER: _FIXTURE_ROOT_PRODUCER_SOURCE,
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


@contextlib.contextmanager
def fixture_root(**overrides: str):
    """A throwaway fixture root, for callers with no tmp_path of their own."""
    with tempfile.TemporaryDirectory(prefix="t1-fixture-") as tmp:
        yield write_fixture_root(Path(tmp) / "repo", **overrides)


def _run_on_fixture(argv: list[str], **overrides: str) -> tuple[int, str]:
    """Run the CLI against a throwaway fixture root; return (exit code, stdout)."""
    with fixture_root(**overrides) as root:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main([*argv, "--root", str(root)])
        return rc, buf.getvalue()


def _selftest() -> int:
    """Prove the validator rejects each bad registry AND accepts a good one.

    Both directions are required. A validator that flags everything is as useless as one
    that flags nothing — the sibling precedent
    ``scripts/check_qledger_metric_validity.py --selftest`` makes the same argument.
    """
    checks: list[tuple[str, bool]] = []
    statuses = VALID_VALIDATION_STATUSES
    good = _fixture_registry()

    def add(label: str, passed: bool) -> None:
        checks.append((label, bool(passed)))

    # ---- POSITIVE CONTROLS -------------------------------------------------
    add(
        "POSITIVE CONTROL — a derived registry is structurally valid",
        validate_structure(good, valid_validation_statuses=statuses) == [],
    )
    add(
        "POSITIVE CONTROL — an empty overlay is accepted",
        validate_overlay({"schema_version": 1, "engines": {}}, ["engine/a.py::prog"]) == [],
    )
    add(
        "POSITIVE CONTROL — an evidenced authority artifact raises no C-1",
        "AUTHORITY_WITHOUT_EVIDENCE" not in _codes_for(good, "engine/e.py::prog"),
    )

    # ---- C-1, DERIVED (delete the derivation and these FAIL) ---------------
    add(
        "NEGATIVE — C-1: an authority-bearing artifact with no qual_ladder_ref is flagged",
        "AUTHORITY_WITHOUT_EVIDENCE" in _codes_for(good, "engine/a.py::prog"),
    )
    add(
        "NEGATIVE — C-1 fires even though a DISPLAY sibling in the same cell carries a ref "
        "(a cell-wide union would have cleared it)",
        good_row(good, "engine/a.py::prog")["evidence_ref"] is not None
        and "AUTHORITY_WITHOUT_EVIDENCE" in _codes_for(good, "engine/a.py::prog"),
    )
    add(
        "NEGATIVE — C-1 names the UNEVIDENCED artifact, not the cell",
        good_row(good, "engine/a.py::prog")["authority_evidence"]["unevidenced_artifacts"]
        == ["gate-art"],
    )
    add(
        "POSITIVE CONTROL — a DISPLAY-only engine with no ref raises no C-1",
        "AUTHORITY_WITHOUT_EVIDENCE"
        not in {
            f.code
            for f in audit_content(good)
            if f.engine_id in {r["engine_id"] for r in good["engines"]
                               if r["authority"] == "display"}
        },
    )

    # ---- A DIRECTORY IS NOT A PREREG ---------------------------------------
    add(
        "NEGATIVE — a qual_ladder_ref pointing at a DIRECTORY ('research/') is reported, "
        "not accepted as evidence",
        "AUTHORITY_EVIDENCE_UNRESOLVABLE" in _codes_for(good, "engine/c.py::prog")
        and good_row(good, "engine/c.py::prog")["evidence_ref"] is None,
    )
    add(
        "NEGATIVE — a directory ref with NO trailing slash ('research') is reported too",
        "AUTHORITY_EVIDENCE_UNRESOLVABLE" in _codes_for(good, "engine/d.py::prog")
        and good_row(good, "engine/d.py::prog")["evidence_ref"] is None,
    )
    add(
        "NEGATIVE — resolve_qual_ladder_ref refuses a directory even when the probe says "
        "the path exists",
        resolve_qual_ladder_ref(
            "research/", qual_ladder_keys=set(), file_exists=lambda p: True
        ) == "unresolved",
    )
    add(
        "POSITIVE CONTROL — a ref that IS a config/qual_ladder.yml key resolves",
        resolve_qual_ladder_ref(
            "altdata.action", qual_ladder_keys={"altdata.action"}, file_exists=lambda p: False
        ) == "qual_ladder_key",
    )
    add(
        "POSITIVE CONTROL — a ref that IS an existing repo FILE resolves",
        resolve_qual_ladder_ref(
            "research/PREREG.md", qual_ladder_keys=set(), file_exists=lambda p: True
        ) == "repo_path",
    )

    # ---- 'unchecked' IS NOT EVIDENCE ---------------------------------------
    unprobed = _fixture_registry(qual_ladder_keys=None, file_exists=None)
    add(
        "POSITIVE CONTROL — an UNPROBED ref is 'unchecked', never 'unresolved' "
        "('could not look' != 'looked and found nothing')",
        resolve_qual_ladder_ref("research/PREREG.md") == "unchecked",
    )
    add(
        "NEGATIVE — an UNCHECKED ref on an authority artifact is REPORTED, not banked as "
        "evidence",
        "AUTHORITY_EVIDENCE_UNCHECKED" in _codes_for(unprobed, "engine/e.py::prog")
        and good_row(unprobed, "engine/e.py::prog")["evidence_ref"] is None,
    )

    # ---- graded_by_design honesty ------------------------------------------
    add(
        "NEGATIVE — a graded_by_design='yes' resting on a PATH SUBSTRING is labelled weak "
        "and enumerated",
        good_row(good, "engine/a.py::prog")["graded_by_design"] == "yes"
        and good_row(good, "engine/a.py::prog")["graded_by_design_evidence"]
        == "weak_path_heuristic"
        and "GRADED_BY_DESIGN_IS_HEURISTIC" in _codes_for(good, "engine/a.py::prog"),
    )
    add(
        "POSITIVE CONTROL — a graded_by_design='yes' earned by a DECLARED evaluated tier "
        "is 'strong' and is NOT enumerated as a heuristic",
        good_row(good, "engine/e.py::prog")["graded_by_design_evidence"] == "strong"
        and "GRADED_BY_DESIGN_IS_HEURISTIC" not in _codes_for(good, "engine/e.py::prog"),
    )

    # ---- the completeness detector's epistemic null ------------------------
    unimported = build_registry(
        synapse=_FIXTURE_SYNAPSE,
        article2_modules=None,
        species=[],
        qual_ladder_keys=set(),
        file_exists=lambda p: p in _FIXTURE_FILES,
    )
    add(
        "NEGATIVE — an unimportable Article-2 module table reports "
        "SCORED_PATH_SURFACES_UNCHECKED instead of silently finding nothing",
        "SCORED_PATH_SURFACES_UNCHECKED" in _codes(unimported),
    )
    add(
        "POSITIVE CONTROL — an importable (empty) table does NOT report it",
        "SCORED_PATH_SURFACES_UNCHECKED" not in _codes(good),
    )

    # ---- the corpus half ---------------------------------------------------
    desk_syn = copy.deepcopy(_FIXTURE_SYNAPSE)
    desk_reg = _fixture_registry(synapse=desk_syn, qledger_desk_rows={})
    for row in desk_reg["engines"]:
        row["ledger"] = "qledger:ghost_desk"
        row["ledger_evidence"] = {
            "rule": 2, "desk": "ghost_desk", "via": None, "shape": None,
            "corpus_checked": True, "corpus_rows": 0,
        }
    add(
        "NEGATIVE — a registered qledger desk with zero rows in the claim corpus is flagged",
        "LEDGER_DECLARED_BUT_EMPTY" in _codes(desk_reg),
    )
    unread = copy.deepcopy(desk_reg)
    for row in unread["engines"]:
        row["ledger_evidence"].update({"corpus_checked": False, "corpus_rows": None})
    add(
        "POSITIVE CONTROL — an UNREAD corpus is not reported as an empty desk "
        "('could not look' != 'looked and found nothing')",
        "LEDGER_DECLARED_BUT_EMPTY" not in _codes(unread),
    )

    # ---- species binding ---------------------------------------------------
    unbound = _fixture_registry(
        species=[{
            "species_id": "F3_ANTICHASE", "validation_status": "accruing",
            "ledger_binding": {"ledger": "no_such_ledger"},
        }]
    )
    add(
        "NEGATIVE — a species bound to no engine ledger is named",
        "SPECIES_UNBOUND" in _codes(unbound),
    )
    could_not_look = _fixture_registry(species=None)
    add(
        "POSITIVE CONTROL — an UNREAD species store reports no unbound species and a NULL "
        "validation_state",
        # `species_read is False` and `unbound_species is None` are asserted FIRST and are
        # not redundant: they are what distinguishes "could not look" from "looked and
        # found nothing" at the source. Without them the control passed vacuously when the
        # harness quietly substituted an EMPTY species list for the null (the shape of the
        # 2026-08-12 failure), because an empty store also yields zero unbound species.
        could_not_look["meta"]["corpus"]["species_read"] is False
        and could_not_look["meta"]["unbound_species"] is None
        and "SPECIES_UNBOUND" not in _codes(could_not_look)
        and all(r["validation_state"] is None for r in could_not_look["engines"]),
    )
    looked_and_found_nothing = _fixture_registry(species=[])
    add(
        "NEGATIVE — an EMPTY species store is NOT the same state as an unread one "
        "(phase0 asserts nothing; None says nothing was asserted)",
        looked_and_found_nothing["meta"]["corpus"]["species_read"] is True
        and looked_and_found_nothing["meta"]["unbound_species"] == []
        and all(
            r["validation_state"] == "phase0"
            for r in looked_and_found_nothing["engines"]
        ),
    )

    # ---- structural negative controls --------------------------------------
    def rejects(label: str, mutate) -> None:
        bad = copy.deepcopy(good)
        mutate(bad)
        add(label, bool(validate_structure(bad, valid_validation_statuses=statuses)))

    rejects("NEGATIVE — unknown authority enum",
            lambda r: r["engines"][0].__setitem__("authority", "supreme_overlord"))
    rejects("NEGATIVE — unknown graded_by_design value",
            lambda r: r["engines"][0].__setitem__("graded_by_design", "sort of"))
    rejects("NEGATIVE — unknown graded_by_design_evidence value",
            lambda r: r["engines"][0].__setitem__("graded_by_design_evidence", "vibes"))
    rejects("NEGATIVE — unknown output_class",
            lambda r: r["engines"][0].__setitem__("output_class", "vibes"))
    rejects("NEGATIVE — unknown validation_state",
            lambda r: r["engines"][0].__setitem__("validation_state", "totally_proven"))
    rejects("NEGATIVE — null ledger (must be the literal 'none')",
            lambda r: r["engines"][0].__setitem__("ledger", None))
    rejects("NEGATIVE — missing required field",
            lambda r: r["engines"][0].pop("evidence_ref"))
    rejects("NEGATIVE — wrong schema string",
            lambda r: r.__setitem__("schema", "something.else"))
    rejects("NEGATIVE — engine_id not equal to producer::owner_program",
            lambda r: r["engines"][0].__setitem__("engine_id", "engine/z.py::prog"))
    rejects("NEGATIVE — an artifact dropped from the partition",
            lambda r: r["engines"][0].__setitem__("artifacts", []))
    rejects("NEGATIVE — exclusion with an empty reason",
            lambda r: r["excluded"][0].__setitem__("reason", "   "))
    rejects("NEGATIVE — an exclusion that does not record what it deletes",
            lambda r: r["excluded"][0].pop("would_be_authority"))

    def _duplicate_artifact(r):
        clone = copy.deepcopy(r["engines"][0])
        clone["engine_id"] = "engine/zz.py::prog"
        clone["producer"] = "engine/zz.py"
        r["engines"].append(clone)

    rejects("NEGATIVE — one artifact mapped to TWO engines", _duplicate_artifact)

    # ATTRIBUTION — an authority nobody can trace to a rule and an artifact.
    rejects("NEGATIVE — authority that names NO derivation rule",
            lambda r: r["engines"][0]["authority_evidence"].__setitem__("rule", None))
    rejects("NEGATIVE — authority that names NO artifact",
            lambda r: r["engines"][0]["authority_evidence"].__setitem__("artifact_ids", []))
    rejects("NEGATIVE — authority attributed to an artifact that is not in the engine",
            lambda r: r["engines"][0]["authority_evidence"].__setitem__(
                "artifact_ids", ["not-in-this-engine"]))
    rejects("NEGATIVE — an artifact whose own authority names no rule",
            lambda r: r["engines"][0]["artifacts"][0].pop("artifact_authority_rule"))

    def _misattributed(r):
        row = next(e for e in r["engines"] if e["authority"] != "display")
        row["authority_evidence"]["artifact_ids"] = [
            a["id"] for a in row["artifacts"] if a["artifact_authority"] != row["authority"]
        ] or ["chip-art"]

    rejects(
        "NEGATIVE — authority attributed to an artifact that does not carry it",
        _misattributed,
    )

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

    rejects(
        "NEGATIVE — a CURATED exclusion of an authority-bearing cell (the overlay is not a "
        "deletion hatch)",
        _curated_exclusion_of_an_authority_cell,
    )
    rejects("NEGATIVE — a CURATED exclusion of a tier=scored cell",
            _curated_exclusion_of_a_scored_cell)

    derived_authority = copy.deepcopy(good)
    derived_authority["excluded"][0]["would_be_authority"] = "gate_size"
    add(
        "POSITIVE CONTROL — a DERIVED placeholder exclusion is not refused by the "
        "authority rule",
        validate_structure(derived_authority, valid_validation_statuses=statuses) == [],
    )

    # A CURATED exclusion of a DISPLAY cell is legal — but it must still be REPORTED, or
    # the overlay deflates the backlog silently for everything at or below display.
    hatched = copy.deepcopy(good)
    hatched["excluded"][0].update({
        "source": "curated",
        "would_be_authority": "display",
        "would_be_output_class_reason": "required_but_uncurated",
    })
    add(
        "NEGATIVE — a CURATED exclusion of a DISPLAY cell is still reported "
        "(ENGINE_EXCLUDED_BY_OVERLAY) and its would-be findings survive",
        "ENGINE_EXCLUDED_BY_OVERLAY" in _codes(hatched)
        and "OUTPUT_CLASS_MISSING" in _codes_for(hatched, "<MANUAL>::prog"),
    )
    quiet = copy.deepcopy(good)
    add(
        "POSITIVE CONTROL — a DERIVED placeholder exclusion is not reported as an overlay "
        "deletion",
        "ENGINE_EXCLUDED_BY_OVERLAY" not in _codes(quiet),
    )

    # ---- overlay negative controls -----------------------------------------
    known = ["engine/a.py::prog"]

    def overlay_rejects(label: str, overlay: dict) -> None:
        add(label, bool(validate_overlay(overlay, known)))

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
    # THE CENSUS-DELETION HATCH. `not_an_engine: {reason: "nah"}` once removed an
    # authority-bearing engine with every law green.
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
    add(
        "POSITIVE CONTROL — a fully cited not_an_engine exclusion is accepted",
        validate_overlay(
            {"schema_version": 1, "engines": {"engine/a.py::prog": {"not_an_engine": {
                "reason": "this cell is an operational rail with no intelligence output at all",
                "dnr_key": "DNR:KILL-EXAMPLE", "ratified_by": "operator", "date": "2026-08-12"}}}},
            known,
        ) == [],
    )
    add(
        "NEGATIVE — terminal ratification of a state the species registry no longer has",
        bool(validate_overlay(
            {"schema_version": 1, "engines": {"engine/a.py::prog": {"validation_state": {
                "value": "falsified", "dnr_key": "DNR:X", "ratified_by": "x", "date": "2026-08-12"}}}},
            known,
            valid_validation_statuses=["phase0", "accruing", "validated", "retired"],
        )),
    )
    add(
        "POSITIVE CONTROL — a legal output_class ratification is accepted",
        validate_overlay(
            {"schema_version": 1, "engines": {"engine/a.py::prog": {"output_class": {"value": "ranking", "rationale": "orders a user-visible board"}}}},
            known,
        ) == [],
    )
    add(
        "POSITIVE CONTROL — the one legal graded_by_design transition is accepted",
        validate_overlay(
            {"schema_version": 1, "engines": {"engine/a.py::prog": {"graded_by_design": {"value": "no — descriptive", "reason": "reconciliation only"}}}},
            known,
        ) == [],
    )
    add(
        "POSITIVE CONTROL — a fully cited terminal ratification is accepted",
        validate_overlay(
            {"schema_version": 1, "engines": {"engine/a.py::prog": {"validation_state": {"value": "retired", "dnr_key": "DNR:KILL-EXAMPLE", "ratified_by": "operator", "date": "2026-08-12"}}}},
            known,
        ) == [],
    )

    # ---- the OVERLAY may not buy silence, end to end -----------------------
    excl_overlay = {
        "schema_version": 1,
        "engines": {
            "engine/e.py::prog": {"not_an_engine": {
                "reason": "judgment call: this cell is an operational rail, not an engine",
                "ratified_by": "operator", "date": "2026-08-12"}}
        },
    }
    deflated = _fixture_registry(overlay=excl_overlay)
    add(
        "NEGATIVE — an overlay exclusion of an AUTHORITY-BEARING cell is a structural "
        "violation (derived first, excluded second, so the refusal can see it)",
        bool(validate_structure(deflated, valid_validation_statuses=statuses)),
    )

    # ---- THE FIXTURE ROOT: a real build, over real files -------------------
    #
    # Everything below runs the BUILDER against a directory. These are the controls the
    # in-memory fixtures structurally cannot carry — a store that opens and does not
    # parse, an exit code, a line in the log body.
    with fixture_root() as clean_root:
        clean_registry, clean_report = build(clean_root)
    add(
        "POSITIVE CONTROL — the fixture ROOT reads COMPLETE (so any INCOMPLETE below is "
        "attributable to the one input that control flipped)",
        clean_report["inputs_complete"] is True and clean_report["unreadable_inputs"] == [],
    )
    add(
        "POSITIVE CONTROL — the fixture root derives its C-1 exemplar and its DERIVED "
        "exclusion by construction",
        "AUTHORITY_WITHOUT_EVIDENCE" in _codes_for(clean_registry, FIXTURE_ENGINE_ID)
        and [r["engine_id"] for r in clean_registry["excluded"]]
        == [FIXTURE_EXCLUDED_ENGINE_ID],
    )

    # ---- A MALFORMED STORE IS INCOMPLETE, NEVER "ZERO ROWS" ----------------
    #
    # The reader swallowed a json.JSONDecodeError per line and returned whatever parsed,
    # so a store of pure garbage and a store that was read cleanly and held no desk rows
    # produced the SAME report. Blank lines and `#` comments stay skippable.
    malformed_claims = (
        '{"desk": "fixture_desk", "horizon_d": 21}\n'
        "\n"
        "# a comment line, skippable and uncounted\n"
        "{not json at all\n"
        '{"desk": "fixture_desk", "horizon_d": 63}\n'
        '{"desk": "fixture_desk", truncated…\n'
    )
    rc_malformed, out_malformed = _run_on_fixture([], claims=malformed_claims)
    add(
        "NEGATIVE — a claims store with 2 unparseable lines reads INCOMPLETE and NAMES "
        "the store with the count (not 'zero rows')",
        "inputs=INCOMPLETE" in out_malformed
        and "claims.jsonl (2 unparseable line(s) of 4)" in out_malformed,
    )
    add(
        "NEGATIVE — a partially blind run exits NON-ZERO with NO --strict flag "
        "(an incomplete read is a RUN-level defect, not a corpus condition)",
        rc_malformed != 0,
    )
    with fixture_root(claims=malformed_claims) as partial_root:
        _, partial_report = build(partial_root)
    add(
        "POSITIVE CONTROL — the rows that DID parse are KEPT under disclosed partial "
        "blindness (the null law represents the gap; it does not delete the readable half)",
        partial_report["sources"][str(builder.CLAIMS_REL)].endswith(
            "(2 unparseable line(s))"
        ),
    )
    rc_clean, out_clean = _run_on_fixture([])
    add(
        "POSITIVE CONTROL — a fully valid claims store raises NO false alarm",
        rc_clean == 0 and "inputs=complete" in out_clean,
    )
    with fixture_root(claims='[1, 2, 3]\n{"desk": "fixture_desk"}\n') as list_root:
        _, list_report = build(list_root)
    add(
        "NEGATIVE — a line that is VALID JSON but not an object (a bare list) is counted "
        "unparseable, not skipped as a row with no desk",
        any(
            "claims.jsonl (1 unparseable line(s) of 2)" in name
            for name in list_report["unreadable_inputs"]
        ),
    )

    # ---- A DOCUMENT THAT READS BUT DOES NOT PARSE --------------------------
    rc_bad_synapse, out_bad_synapse = _run_on_fixture([], synapse="{unclosed: [mapping\n")
    add(
        "NEGATIVE — a synapse.yml that READS but does not parse is NOT CHECKED and exits "
        "non-zero, never a bare traceback",
        rc_bad_synapse != 0 and "NOT CHECKED" in out_bad_synapse,
    )
    rc_list_synapse, out_list_synapse = _run_on_fixture([], synapse="- a\n- b\n")
    add(
        "NEGATIVE — a synapse.yml that parses to a LIST is NOT CHECKED too (a mapping is "
        "the only shape a partition can be derived from)",
        rc_list_synapse != 0 and "NOT CHECKED" in out_list_synapse,
    )
    with fixture_root(overlay="{unclosed: [mapping\n") as bad_overlay_root:
        _, bad_overlay_report = build(bad_overlay_root)
    add(
        "NEGATIVE — an unparseable overlay is treated as ABSENT and NAMED, with "
        "sources='unparseable' (never an empty overlay, never a traceback)",
        str(builder.OVERLAY_REL) in bad_overlay_report["unreadable_inputs"]
        and bad_overlay_report["sources"][str(builder.OVERLAY_REL)] == "unparseable",
    )
    with fixture_root(overlay="- not\n- a mapping\n") as list_overlay_root:
        _, list_overlay_report = build(list_overlay_root)
    add(
        "NEGATIVE — an overlay that parses to a LIST is named the same way",
        str(builder.OVERLAY_REL) in list_overlay_report["unreadable_inputs"],
    )
    with fixture_root(overlay="") as empty_overlay_root:
        _, empty_overlay_report = build(empty_overlay_root)
    add(
        "POSITIVE CONTROL — an EMPTY overlay file is READ, not unreadable ('no curated "
        "rows' is what it honestly says)",
        empty_overlay_report["inputs_complete"] is True,
    )
    with fixture_root(qual_ladder="- not\n- a mapping\n") as bad_ladder_root:
        _, bad_ladder_report = build(bad_ladder_root)
    add(
        "NEGATIVE — a qual_ladder that parses to a NON-DICT is the NULL, not zero keys "
        "(zero keys would resolve every ref against nothing and ACCUSE it)",
        str(builder.QUAL_LADDER_REL) in bad_ladder_report["unreadable_inputs"],
    )

    # ---- THE C-1 BACKLOG SURVIVES A TERMINAL ------------------------------
    add(
        "NEGATIVE — C-1 rows are printed as PLAIN STDOUT lines, not annotation-only (the "
        "law's primary deliverable must survive a terminal and a grep of the log body)",
        any(
            line.startswith(f"  [AUTHORITY_WITHOUT_EVIDENCE] {FIXTURE_ENGINE_ID}:")
            for line in out_clean.splitlines()
        ),
    )

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


def good_row(registry: dict[str, Any], engine_id: str) -> dict[str, Any]:
    """The engine row with this id. Raises if absent — a missing row is a real failure."""
    return next(r for r in registry["engines"] if r["engine_id"] == engine_id)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Run the gate. ``argv`` is injectable so the fail-closed path can be exercised
    in-process by a test — a blind run is the one behaviour a subprocess cannot easily be
    put into without deleting a real input."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "content FINDINGS also exit non-zero (reserved for T7's promotion era). An "
            "INCOMPLETE input set exits non-zero on EVERY run, with or without this flag."
        ),
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    root: Path = args.root

    try:
        registry, report = build(root)
    except SystemExit as exc:
        # config/synapse.yml is readable from neither the worktree nor HEAD, or it reads
        # and does not parse as a YAML mapping. Nothing could be derived, so nothing was
        # checked — say that, never a clean count, and never a bare traceback.
        message = str(exc)
        if args.json:
            print(
                json.dumps(
                    {
                        "inputs_complete": False,
                        "unreadable_inputs": ["config/synapse.yml"],
                        "violations": None,
                        "findings": None,
                        "detail": message,
                    },
                    indent=2,
                ),
                flush=True,
            )
        else:
            print(f"::error title={TITLE}::{message}", flush=True)
            print(
                "intelligence registry: NOT CHECKED — config/synapse.yml is unreadable or "
                "unparseable, so 0 violations would be 'I could not look' dressed as 'I "
                "looked and it was clean'. inputs=INCOMPLETE (config/synapse.yml)",
                flush=True,
            )
        return 1

    violations = validate_structure(
        registry, valid_validation_statuses=VALID_VALIDATION_STATUSES
    )
    # ORPHAN CHECK AGAINST THE PRE-EXCLUSION CELL SET. Feeding it the built registry's own
    # ids would let a `not_an_engine` row SELF-LEGITIMATE: the row creates the excluded
    # entry that proves it is not an orphan.
    violations += validate_overlay(
        report["overlay"],
        report["cell_ids"],
        valid_validation_statuses=VALID_VALIDATION_STATUSES,
    )
    findings = audit_content(registry)
    incomplete = report["unreadable_inputs"]

    if args.json:
        print(
            json.dumps(
                {
                    "inputs_complete": report["inputs_complete"],
                    "unreadable_inputs": incomplete,
                    "n_engines": registry["meta"]["n_engines"],
                    "violations": violations,
                    "findings": [
                        {"code": f.code, "engine_id": f.engine_id, "detail": f.detail}
                        for f in findings
                    ],
                },
                indent=2,
            ),
            flush=True,
        )
        # An INCOMPLETE read reds unconditionally — see the module docstring's FAIL CLOSED
        # section. --strict adds ONLY the content findings.
        return 1 if violations or incomplete or (args.strict and findings) else 0

    for violation in violations:
        print(f"::error title={TITLE}::{violation}", flush=True)

    # ANNOTATION BUDGET. Hundreds of findings, one annotation each, would bury the
    # actionable ones and train readers to ignore the lane — the same way a fleet-wide red
    # gets routed around. C-1 (the defect this registry exists to surface, and the one with
    # a concrete named heal) is annotated PER ENGINE; every other code is annotated ONCE
    # with its count, with full detail on stdout. Nothing is hidden, only re-ranked.
    per_engine = [f for f in findings if f.code == "AUTHORITY_WITHOUT_EVIDENCE"]
    aggregated: dict[str, int] = {}
    for finding in findings:
        if finding.code != "AUTHORITY_WITHOUT_EVIDENCE":
            aggregated[finding.code] = aggregated.get(finding.code, 0) + 1

    for finding in per_engine:
        print(
            f"::warning title={TITLE}::[{finding.code}] {finding.engine_id}: {finding.detail}",
            flush=True,
        )
    for code, count in sorted(aggregated.items()):
        print(
            f"::warning title={TITLE}::[{code}] {count} engine(s) — detail on stdout below",
            flush=True,
        )
    # EVERY finding also goes to stdout, C-1 INCLUDED. The annotation budget re-ranks what
    # GitHub renders; it must not decide what the LOG contains. C-1 is the law's primary
    # deliverable, and it was annotation-only — invisible to a terminal run, to `| grep`,
    # and to anyone reading the raw job log rather than the Actions summary.
    for finding in findings:
        print(f"  [{finding.code}] {finding.engine_id}: {finding.detail}", flush=True)

    if incomplete:
        print(
            f"::warning title={TITLE}::COULD NOT LOOK — {len(incomplete)} input(s) "
            f"unreadable: {', '.join(incomplete)}. The fields they feed are NULL, not "
            f"empty",
            flush=True,
        )

    # THE SUMMARY LINE — the one line a CI reader sees. It always carries `inputs=`, so a
    # run that could not read its inputs can never be mistaken for a clean run.
    inputs_clause = (
        "inputs=complete"
        if report["inputs_complete"]
        else f"inputs=INCOMPLETE ({len(incomplete)} unreadable: {', '.join(incomplete[:4])}"
             + (", …)" if len(incomplete) > 4 else ")")
    )
    print(
        f"intelligence registry: {registry['meta']['n_engines']} engines, "
        f"{len(violations)} structural violation(s), {len(findings)} content finding(s), "
        f"{inputs_clause}",
        flush=True,
    )

    # Mirrors the --json return above, deliberately in the same shape so the two modes
    # cannot drift into disagreeing about what a failing run is.
    if violations or incomplete:
        return 1
    if args.strict and findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
