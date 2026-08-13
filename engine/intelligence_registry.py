"""engine/intelligence_registry.py — the Mastermind engine registry (Eval OS T1).

WHY THIS EXISTS
---------------
Mastermind has four registries and none of them counts ENGINES. ``config/synapse.yml``
counts ARTIFACTS (642 of them), ``data/species/registry.json`` counts setup SPECIES (27),
``research/DO_NOT_REBUILD.md`` counts KILLS, and ``data/qledger/`` counts CLAIMS. There is
no row per *intelligence-producing capability*, so there is nothing to hang a scorecard on
(T7), nothing to roll up into a CEO view (T8), and nothing for tier routing to read (T12).

Two measured defects motivated this module (both reproduced live 2026-08-12):

  C-1  Four of the five ``tier: scored`` artifacts carry NO ``qual_ladder_ref``. Things
       holding rank/size/gate authority do not point at the prereg that earned it.

  C-2  synapse ``tier`` does not express authority over a HUMAN. ``site-us-standouts``
       (the Prophet board that orders what a paying user sees) and ``prophet-index`` are
       both ``tier: display`` — the same value a decorative chip carries.

THE UNIT OF ACCOUNT
-------------------
``engine = (producer, owner_program)``, id ``f"{producer}::{owner_program}"``.
Measured: 642 artifacts partition into 385 cells, totally and disjointly — every artifact
belongs to exactly one engine. Chosen over the alternatives after measuring homogeneity:
only 32/385 cells (8.3%) mix ``tier`` and only 8/385 (2.1%) mix ``horizon_role``.

A DERIVED ON-DEMAND VIEW — NOTHING IS COMMITTED
-----------------------------------------------
THE REGISTRY IS NOT A FILE. Two previous rounds committed a generated
``data/intelligence_registry.json`` plus a generated Markdown mirror and pinned them by
equality against a "stable" input. Both pins were scheduled fleet-wide reds, because there
is no stable input to pin against — measured on this repo 2026-08-12:

  * ``config/synapse.yml``        26 commits, ALL 26 inside the last 14 days (~1.9/day)
  * ``data/qledger/claims.jsonl`` 13 commits in the last 14 days (append-only)
  * ``data/species/registry.json`` 1 commit — and that ONE is a SHALLOW-CLONE ARTIFACT
    (``git rev-parse --is-shallow-repository`` is true; only 1126 commits are reachable),
    so it is not evidence of stability at all. Round 2 treated it as stable and was wrong.

So nothing generated is committed, there is no drift guard, no ``--check`` equality mode,
and no stable-vs-volatile field split (that split existed ONLY to make a pin safe).
Consumers — T7's scorecard, T8's CEO view, T12's tier routing — call
:func:`build_registry` and get the view in memory, or run
``scripts/build_intelligence_registry.py --json`` and read it off stdout. Corpus-derived
fields are simply present in the view; nothing pins them, so nothing reds.

DERIVED, NOT AUTHORED (``DNR:KILL-PARALLEL-KNOWLEDGE-BASE``)
-------------------------------------------------------------
The spine is a pure function of canonical sources: ``config/synapse.yml``, an AST scan of
producer source, ``config/qual_ladder.yml``, ``data/species/`` and ``data/qledger/``. A
hand-authored engine list is the KILLED pattern. Only three fields are curated, each
because no canonical source encodes them, and they live in a four-key overlay whose key
allowlist is enforced mechanically by ``scripts/check_intelligence_registry.py`` — that
allowlist IS the executable form of the DNR row.

``authority`` and ``evidence_ref`` are NOT curated, against the recommendation of three
census reports. ``_REQUIRED_ARTIFACT_KEYS`` (engine/neuralweb/synapse.py:52) is a
required-key set, not an exact-key set, so a hand-typed ``authority:`` key in synapse.yml
would land as unenforced free text — reproducing the exact defect class C-1 and C-2 are
instances of, one field later.

KNOWN LIMIT — ``graded_by_design`` IS A WEAK HEURISTIC, AND SAYS SO
-------------------------------------------------------------------
``graded_by_design: "yes"`` means "the ledger waterfall resolved a store-shaped path", and
TWO of the four waterfall rules resolve that path from a FILENAME SUBSTRING: rule 1 accepts
any artifact path matching ``/ledger/i`` and rule 4 hops to any consumer whose module name
matches ``/grade|ledger/i``. A filename is not proof that graded rows are written, so every
``yes`` reached that way is a GUESS, and some of those guesses are wrong on live rows.

This module does not hide that and does not hand-maintain a list of the wrong ones (a
hand list rots). Every engine carries ``graded_by_design_evidence``:

  ``strong``                  — rule 2 (the producer statically imports ``engine.qledger``
                                and a desk literal resolves by AST) or rule 3 (an artifact
                                declares tier shadow/scored/confirmer, which synapse's own
                                ``meta.tier_vocabulary`` defines as claim-registered and
                                graded).
  ``weak_filename_heuristic`` — rule 1 or rule 4. The claim rests on a filename.
  ``none``                    — no ledger resolved; the value is not ``yes``.

:func:`audit_content` emits ``GRADED_BY_DESIGN_IS_HEURISTIC`` for every ``yes`` standing on
the weak evidence, so the known-wrong candidates are ENUMERATED on every run rather than
described in prose. T7 must not treat a weak ``yes`` as gradeability. Mirrored in
``config/house_law_checks.yml`` known_limits.

WHAT THIS MODULE IS
-------------------
Pure functions over already-loaded objects. It reads no files and writes no files. File
I/O and the sparse-worktree ladder live in ``scripts/build_intelligence_registry.py``; the
structural validator lives in ``scripts/check_intelligence_registry.py``. Where a
derivation needs the filesystem — resolving a ``qual_ladder_ref`` against a repo path —
the probe is INJECTED (``file_exists``) so the caller can route it through the git ladder
rather than through ``os.path.exists``, which goes blind on a sparse cone.

Per house epistemics a null never blocks: absent inputs produce ``None`` sentinels that
render as "could not look", never as "looked and found nothing". That is why an unprobed
``qual_ladder_ref`` resolves to ``"unchecked"`` and never to ``"unresolved"`` — and why
``"unchecked"`` is NOT counted as evidence by the C-1 gate either.
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

SCHEMA = "intelligence_registry.v1"

ENGINE_ID_SEP = "::"

# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------

# §2 of research/MASTERMIND_INTELLIGENCE_CATALOG.md. The class selects the metric
# contract, which is why "win rate" cannot be the universal metric.
OUTPUT_CLASSES = frozenset({
    "predictive",
    "ranking",
    "classification_state",
    "detection_event",
    "descriptive",
    "salience",
    "generative",
})

# Total order, ascending. MAX is taken at the engine level because UNDER-statement is the
# dangerous direction — C-2 is an under-statement defect.
AUTHORITY_ORDER: tuple[str, ...] = ("display", "engine_input", "user_ranking", "gate_size")
AUTHORITIES = frozenset(AUTHORITY_ORDER)
_AUTHORITY_RANK = {name: i for i, name in enumerate(AUTHORITY_ORDER)}

#: The rules :func:`derive_artifact_authority` may cite. An authority value that names no
#: rule is not attributable, which ``validate_structure`` refuses.
AUTHORITY_RULES = frozenset({"a", "b", "c", "d"})

GRADED_YES = "yes"
GRADED_DESCRIPTIVE = "no — descriptive"
GRADED_NOT_YET = "no — not yet"
GRADED_BY_DESIGN_VALUES = frozenset({GRADED_YES, GRADED_DESCRIPTIVE, GRADED_NOT_YET})

#: How much the ``graded_by_design`` value is worth. See the module docstring.
GRADED_EVIDENCE_STRONG = "strong"
GRADED_EVIDENCE_WEAK = "weak_filename_heuristic"
GRADED_EVIDENCE_NONE = "none"
GRADED_EVIDENCE_VALUES = frozenset({
    GRADED_EVIDENCE_STRONG, GRADED_EVIDENCE_WEAK, GRADED_EVIDENCE_NONE,
})

#: Ledger waterfall rules whose ledger came from a FILENAME SUBSTRING, not from a
#: declaration. A ``graded_by_design: yes`` standing on one of these is a guess.
_WEAK_LEDGER_RULES = frozenset({1, 4})

LEDGER_NONE = "none"

# Mirrors data/species/registry.json's own convention; never null.
VALIDATION_STATE_DEFAULT = "phase0"

# Ascending "claim of proven validity". min() over this order is the conservative pick
# when several species bind to one ledger. phase0 and the terminal states all assert no
# validity, so they sort first; phase0 wins ties because it asserts the least of all.
_VALIDATION_CONSERVATISM: tuple[str, ...] = (
    "phase0", "falsified", "retired", "accruing", "validated",
)

# Tiers that synapse's own meta.tier_vocabulary describes as carrying weight.
_TIER_WEIGHTED = frozenset({"scored", "confirmer"})
# Tiers that are claim-registered and graded (shadow) or weighted.
_TIER_EVALUATED = frozenset({"shadow", "scored", "confirmer"})

# Placeholder producer tokens, mirroring engine/neuralweb/synapse.py:58. These are
# exempted from the producer-exists check there and are not engines here.
_PLACEHOLDER_RE = re.compile(r"<[A-Z_]+>")

# ---------------------------------------------------------------------------
# Overlay contract — the executable form of DNR:KILL-PARALLEL-KNOWLEDGE-BASE
# ---------------------------------------------------------------------------

#: The ONLY four keys an overlay row may carry. A curated field that later becomes
#: derivable must be DELETED from this set in the same PR that adds its derivation.
OVERLAY_ALLOWED_KEYS = frozenset({
    "output_class",
    "graded_by_design",
    "validation_state",
    "not_an_engine",
})

#: Fields the overlay may NEVER write, named explicitly so the refusal reads as a law
#: rather than as an omission.
OVERLAY_FORBIDDEN_KEYS = frozenset({
    "engine_id", "producer", "artifacts", "consumers", "owner_program",
    "owner_program_span", "authority", "authority_evidence", "ledger",
    "ledger_evidence", "declared_horizon", "evidence_ref",
})

#: The single graded_by_design transition the overlay may make. It may never write
#: 'yes' (that must be earned by a real ledger) nor 'no — not yet' (the safe default is
#: not a claim).
OVERLAY_GRADED_TRANSITION = (GRADED_NOT_YET, GRADED_DESCRIPTIVE)

#: Terminal states the overlay may ratify, each requiring a DNR citation.
OVERLAY_TERMINAL_STATES = frozenset({"falsified", "retired"})

#: Minimum length of a ``not_an_engine`` reason. "nah" removed a gate_size engine with
#: every law green (reproduced 2026-08-12); a census deletion has to carry an argument.
NOT_AN_ENGINE_MIN_REASON_CHARS = 40

#: Artifact tiers that make a cell authority-bearing regardless of the derived roll-up.
#: A curated exclusion may never remove a cell holding one — see ``validate_structure``.
EXCLUSION_FORBIDDEN_TIERS = frozenset({"scored", "confirmer", "shadow"})

# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

SEVERITY_STRUCTURE = "structure"   # refusals — a PR-caused defect in the derivation
SEVERITY_CONTENT = "content"       # pre-existing conditions of the corpus

FINDING_CODES = (
    "AUTHORITY_WITHOUT_EVIDENCE",
    "AUTHORITY_EVIDENCE_UNRESOLVABLE",
    "AUTHORITY_EVIDENCE_UNCHECKED",
    "OUTPUT_CLASS_MISSING",
    "GRADED_BY_DESIGN_CONTRADICTS_LEDGER",
    "GRADED_BY_DESIGN_IS_HEURISTIC",
    "SCORED_PATH_SURFACES_INCOMPLETE",
    "SCORED_PATH_SURFACES_UNCHECKED",
    "SPECIES_UNBOUND",
    "LEDGER_DECLARED_BUT_EMPTY",
    "ENGINE_EXCLUDED_BY_OVERLAY",
)


@dataclass(frozen=True)
class Finding:
    """One registry finding. `severity` selects which house law owns it."""

    code: str
    severity: str
    engine_id: str
    detail: str


# ---------------------------------------------------------------------------
# qual_ladder_ref resolution — "a pointer at nothing" is not evidence
# ---------------------------------------------------------------------------

#: The four resolution states. ``unchecked`` is the epistemic null: the resolver was not
#: given the inputs it needs, so it did not look. It must never be reported as a failure —
#: and it must never be counted as evidence either (see :func:`build_registry`).
QUAL_LADDER_RESOLUTIONS = ("qual_ladder_key", "repo_path", "unresolved", "unchecked")

#: The two resolutions that actually constitute evidence.
QUAL_LADDER_RESOLVED = frozenset({"qual_ladder_key", "repo_path"})


def resolve_qual_ladder_ref(
    ref: Any,
    *,
    qual_ladder_keys: Iterable[str] | None = None,
    file_exists: Callable[[str], bool] | None = None,
) -> str | None:
    """Resolve one ``qual_ladder_ref`` value. ``None`` means there was no ref at all.

    The live corpus mixes exactly two legal shapes and BOTH are checkable (measured over
    all 10 refs in ``config/synapse.yml``, 2026-08-12): 9 are keys in
    ``config/qual_ladder.yml`` and 1 is a repo path that exists
    (``research/RECLAIM_VETO_CONDITIONAL_PREREG.md``).

    ``file_exists`` MUST answer "is there a FILE at this path", never "does this path
    exist". A DIRECTORY is not a prereg: a ref of ``research/`` resolved clean under the
    previous ``path_exists`` probe (``git show HEAD:research`` exits 0 on a tree), so the
    C-1 backlog was drainable to zero by pointing every authority-bearing artifact at a
    folder. The probe is INJECTED so this module stays file-free and so the caller can
    route it through the sparse-worktree git ladder — a bare ``os.path.isfile`` would go
    blind on a sparse cone and silently call a real prereg missing.

    SCOPE: resolvability is not adequacy. A resolvable pointer does not prove the document
    it names pre-registers anything — that judgment is T7's backlog drain. This guarantees
    only that the pointer is a real file or a real ladder key.
    """
    text = str(ref).strip() if ref is not None else ""
    if not text:
        return None
    if qual_ladder_keys is None or file_exists is None:
        return "unchecked"
    if text in set(qual_ladder_keys):
        return "qual_ladder_key"
    if text.endswith("/"):
        # A trailing slash is unambiguously a directory; refuse it without a probe so the
        # refusal holds even for a probe that is laxer than it should be.
        return "unresolved"
    if file_exists(text):
        return "repo_path"
    return "unresolved"


# ---------------------------------------------------------------------------
# Producer source scanning (pure over source text)
# ---------------------------------------------------------------------------

_QLEDGER_IMPORT_RE = re.compile(
    r"(?:from\s+engine\.qledger\s+import|from\s+engine\s+import\s+qledger|"
    r"import\s+engine\.qledger|from\s+\.qledger\s+import|from\s+\.\s+import\s+qledger)"
)

_DESK_CALLERS = frozenset({"register", "register_batch", "make_claim"})


@dataclass(frozen=True)
class DeskScan:
    """Result of scanning one producer's source for qledger desk literals."""

    imports_qledger: bool
    desks: tuple[str, ...]
    #: True when a desk= keyword was present but its value was not a string literal
    #: (e.g. `desk=QLEDGER_DESK` in engine/flip_confirmation.py). Silent
    #: under-attribution otherwise, so the builder counts it out loud.
    unresolved: bool


def scan_producer_source(source: str) -> DeskScan:
    """Extract qledger desk literals from one producer's source, by AST.

    Structural only — nothing here depends on prose, comments, or identifier spelling
    beyond the call name. A ``desk=`` keyword whose value is not a string literal sets
    ``unresolved`` rather than being silently dropped.
    """
    imports = bool(_QLEDGER_IMPORT_RE.search(source))
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return DeskScan(imports_qledger=imports, desks=(), unresolved=imports)

    desks: set[str] = set()
    unresolved = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name in _DESK_CALLERS:
                for kw in node.keywords:
                    if kw.arg != "desk":
                        continue
                    if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        desks.add(kw.value.value)
                    else:
                        unresolved = True
        # Dict literals of the shape {"desk": "..."} — the make_claim payload form.
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "desk":
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        desks.add(value.value)
                    else:
                        unresolved = True

    return DeskScan(
        imports_qledger=imports,
        desks=tuple(sorted(desks)),
        unresolved=unresolved and not desks,
    )


# ---------------------------------------------------------------------------
# Cell partition
# ---------------------------------------------------------------------------

def engine_id_for(producer: str, owner_program: str) -> str:
    """The engine id. Total and disjoint over synapse artifacts by construction."""
    return f"{producer}{ENGINE_ID_SEP}{owner_program}"


def placeholder_reason(producer: str) -> str | None:
    """Return a DERIVED not_an_engine reason for a placeholder/frozen producer, else None.

    The five placeholder tokens are already exempted from the producer-exists check by
    ``engine/neuralweb/synapse.py`` ``_PLACEHOLDER_RE``; the empty producer is the frozen
    ``options-signal-campaigns`` artifact whose own notes read "No active producer may
    advance it".
    """
    if producer == "":
        return "derived: empty producer token — no code advances this artifact"
    if _PLACEHOLDER_RE.search(producer):
        return f"derived: placeholder producer token {producer!r} — not a repo module"
    return None


def partition_artifacts(synapse: Mapping[str, Any]) -> dict[str, list[str]]:
    """Return {engine_id: [artifact_id, ...]} over every synapse artifact.

    The partition is TOTAL and DISJOINT: every artifact lands in exactly one cell,
    including the placeholder cells that are later marked ``not_an_engine``. Nothing is
    dropped silently — that is the invariant the structural validator checks.
    """
    artifacts = synapse.get("artifacts") or {}
    cells: dict[str, list[str]] = {}
    for artifact_id, entry in artifacts.items():
        if not isinstance(entry, dict):
            continue
        eid = engine_id_for(entry.get("producer") or "", entry.get("owner_program") or "")
        cells.setdefault(eid, []).append(artifact_id)
    return {k: sorted(v) for k, v in sorted(cells.items())}


# ---------------------------------------------------------------------------
# Authority derivation (fixes C-2)
# ---------------------------------------------------------------------------

def derive_artifact_authority(
    synapse: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Per-artifact authority + the rule that produced it.

    First hit wins:

      (a) ``tier in {scored, confirmer}`` -> ``gate_size``. Definitional: synapse
          ``meta.tier_vocabulary`` defines ``scored`` as carrying weight.
      (b) ``scored_path_surfaces`` non-empty -> ``user_ranking``. This is the C-2 fix:
          ``site-us-standouts`` declares ``['board_ordering', 'top_setups']`` and
          therefore separates from a decorative display chip.
      (c) ``tier in {shadow, scored, confirmer}`` AND the artifact is consumed by the
          PRODUCER OF a (a)/(b) artifact, exactly one hop -> ``engine_input``.
      (d) else ``display``.

    Every rule is structural — enum membership, list non-emptiness, one graph hop. Nothing
    depends on prose. The rule letter is carried on every artifact and every engine so the
    authority value is ATTRIBUTABLE: ``validate_structure`` refuses a registry whose
    authority does not name the rule and the artifact that produced it.
    """
    artifacts = synapse.get("artifacts") or {}
    out: dict[str, dict[str, Any]] = {}

    # Pass 1 — rules (a) and (b), which need no graph.
    for artifact_id, entry in artifacts.items():
        if not isinstance(entry, dict):
            continue
        tier = entry.get("tier")
        surfaces = list(entry.get("scored_path_surfaces") or [])
        if tier in _TIER_WEIGHTED:
            out[artifact_id] = {"authority": "gate_size", "rule": "a", "surfaces": surfaces}
        elif surfaces:
            out[artifact_id] = {"authority": "user_ranking", "rule": "b", "surfaces": surfaces}

    # The producers of everything rules (a)/(b) promoted — the one-hop target set.
    authority_producers = {
        (artifacts[aid].get("producer") or "")
        for aid in out
        if isinstance(artifacts.get(aid), dict)
    }
    authority_producers.discard("")

    # Pass 2 — rule (c), then (d).
    for artifact_id, entry in artifacts.items():
        if not isinstance(entry, dict) or artifact_id in out:
            continue
        tier = entry.get("tier")
        consumers = set(entry.get("consumers") or [])
        if tier in _TIER_EVALUATED and consumers & authority_producers:
            out[artifact_id] = {
                "authority": "engine_input",
                "rule": "c",
                "surfaces": [],
                "hop_to": sorted(consumers & authority_producers),
            }
        else:
            out[artifact_id] = {"authority": "display", "rule": "d", "surfaces": []}

    return out


def max_authority(values: Iterable[str]) -> str:
    """Engine authority = MAX over its artifacts on the total order."""
    best = "display"
    for value in values:
        if _AUTHORITY_RANK.get(value, 0) > _AUTHORITY_RANK[best]:
            best = value
    return best


# ---------------------------------------------------------------------------
# Ledger waterfall
# ---------------------------------------------------------------------------

_LEDGER_PATH_RE = re.compile(r"ledger", re.IGNORECASE)
_GRADER_RE = re.compile(r"grade|ledger", re.IGNORECASE)

#: A grading ledger is a STORE. Without this test, engines earned ``graded_by_design:
#: yes`` from a "ledger" that could not hold a graded row — an ``engine/*_ledger.py``
#: SELF-REFERENCE, a charter CONFIG, a rule-4 hop landing on a ``.py`` module, and
#: unexpanded template globs (all measured 2026-08-12).
_STORE_SUFFIXES = frozenset({".jsonl", ".parquet", ".json", ".csv", ".db", ".sqlite"})

#: Glob/template tokens. A path carrying one names a FAMILY of stores, not a store — it
#: cannot be opened, so it cannot be evidence that grading happens.
_TEMPLATE_TOKEN_RE = re.compile(r"[*?]|<[^>]*>|\{[^}]*\}")

LEDGER_SHAPE_STORE = "store"
LEDGER_SHAPE_TEMPLATE = "template"
LEDGER_SHAPE_NOT_A_STORE = "not_a_store"


def ledger_shape(path: str | None) -> str:
    """Classify a candidate ledger path. Structural — extension, trailing slash, globs.

    A DIRECTORY path (trailing ``/``) is a store: ``data/metabolism/agenda/`` is a real
    store location that holds graded rows, and 5 live engines declare their ledger that
    way. Refusing it would be the shrink-direction failure this tightening exists to avoid
    — a detector that goes blind reads exactly like a detector getting stricter.
    """
    text = str(path or "").strip()
    if not text:
        return LEDGER_SHAPE_NOT_A_STORE
    if _TEMPLATE_TOKEN_RE.search(text):
        return LEDGER_SHAPE_TEMPLATE
    if text.endswith("/"):
        return LEDGER_SHAPE_STORE
    suffix = text[text.rfind("."):] if "." in text.rsplit("/", 1)[-1] else ""
    return LEDGER_SHAPE_STORE if suffix.lower() in _STORE_SUFFIXES else LEDGER_SHAPE_NOT_A_STORE


def _store_shaped(path: str | None) -> bool:
    """True for a path that could actually hold graded rows (store or store template)."""
    return ledger_shape(path) in (LEDGER_SHAPE_STORE, LEDGER_SHAPE_TEMPLATE)


def _cell_ledger_paths(artifact_entries: Sequence[Mapping[str, Any]]) -> list[str]:
    """Rule-1 candidates: store-shaped artifact paths whose FILENAME contains 'ledger'.

    This is the weak half of the waterfall — see the module docstring. It is retained
    because it is right far more often than it is wrong, and it is LABELLED
    (``graded_by_design_evidence = weak_filename_heuristic``) rather than trusted.
    """
    return sorted(
        {
            str(e.get("path"))
            for e in artifact_entries
            if e.get("path")
            and _LEDGER_PATH_RE.search(str(e.get("path")))
            and _store_shaped(e.get("path"))
        }
    )


def derive_ledger(
    *,
    producer: str,
    artifact_entries: Sequence[Mapping[str, Any]],
    desk_scan: DeskScan | None,
    producer_ledger_index: Mapping[str, str],
) -> dict[str, Any]:
    """Resolve the engine's grading ledger. Waterfall, first hit wins. Never null.

    1. the cell writes a ``*ledger*`` path THAT IS STORE-SHAPED -> that path.  **WEAK**
    2. producer statically imports ``engine.qledger`` and a desk literal resolves by AST
       -> ``qledger:<desk>``.                                                 **strong**
    3. any artifact in the cell is tier shadow/scored/confirmer AND its path is
       store-shaped -> that artifact path.                                    **strong**
    4. a grader-shaped consumer that is itself the producer of a store-shaped ledger
       artifact, EVEN CROSS-PROGRAM -> that consumer's ledger path.           **WEAK**
    5. else the literal string ``'none'``, mirroring data/species/registry.json's own
       ``ledger_binding`` convention.

    Rules 1 and 4 match on a FILENAME SUBSTRING, so a ``graded_by_design: yes`` they
    produce is a guess. The strength is recorded per engine and enumerated by
    :func:`audit_content`; see the module docstring's known-limit section.

    DEVIATION, deliberate: the brief made rule 2 conditional on the desk having >0 rows in
    ``data/qledger/claims.jsonl``, demoting a zero-row desk down the waterfall. That would
    SILENTLY hide the very gap it detected, so the desk resolves structurally here and a
    zero-row desk is raised by :func:`audit_content` as ``LEDGER_DECLARED_BUT_EMPTY``.
    Measured 2026-08-12: exactly ONE engine resolves a desk at all
    (``scripts/build_whitehouse.py::whitehouse-desk``) and ZERO desks are empty, so the
    finding fires on nothing today — a tripwire whose condition has not occurred.
    """
    # Rule 1
    ledger_paths = _cell_ledger_paths(artifact_entries)
    if ledger_paths:
        return {"ledger": ledger_paths[0], "rule": 1, "desk": None}

    # Rule 2
    if desk_scan is not None and desk_scan.imports_qledger and desk_scan.desks:
        desk = desk_scan.desks[0]
        return {"ledger": f"qledger:{desk}", "rule": 2, "desk": desk}

    # Rule 3
    graded = sorted(
        {
            str(e.get("path"))
            for e in artifact_entries
            if e.get("tier") in _TIER_EVALUATED and e.get("path") and _store_shaped(e.get("path"))
        }
    )
    if graded:
        return {"ledger": graded[0], "rule": 3, "desk": None}

    # Rule 4 — one hop out to a grader that itself owns a ledger.
    consumers: set[str] = set()
    for entry in artifact_entries:
        consumers.update(entry.get("consumers") or [])
    consumers.discard(producer)
    for consumer in sorted(consumers):
        if not _GRADER_RE.search(consumer):
            continue
        hop = producer_ledger_index.get(consumer)
        if hop and hop != LEDGER_NONE:
            return {"ledger": hop, "rule": 4, "desk": None, "via": consumer}

    # Rule 5
    return {"ledger": LEDGER_NONE, "rule": 5, "desk": None}


# ---------------------------------------------------------------------------
# Species binding
# ---------------------------------------------------------------------------

def _species_tokens(binding: str) -> list[str]:
    """Split a species ledger_binding.ledger string into matchable tokens.

    Values seen live: ``'us_board_ledger'``, ``'us_board_ledger + china_standout_track'``,
    ``'data/trial_ledger.jsonl'``, and ``'none — research verdicts only (...)'``. A
    binding that begins ``none`` binds to nothing.
    """
    text = (binding or "").strip()
    if not text or text.lower().startswith("none"):
        return []
    parts = [p.strip() for p in text.split("+")]
    return [p for p in parts if p and not p.lower().startswith("none")]


def species_token_matches_ledger(token: str, engine_ledger: str) -> bool:
    """Anchored match of one species token against one engine ledger.

    A token binds when it equals the whole ledger, equals one PATH SEGMENT of it, equals
    the basename with its extension removed, or equals a resolved ``qledger:<desk>`` desk.

    The previous rule was an unanchored bidirectional substring — the same fuzzy-matching
    class the overlay comment correctly refuses for DNR-to-engine mapping, applied to the
    validation_state axis. SHRINK-DIRECTION CONTROL: 5 engines bind species today and all
    5 survive this rule; ``tests/test_intelligence_registry.py`` pins the fixture set BY
    NAME, because a matcher that quietly binds fewer things is a detector going blind, not
    a detector getting stricter.
    """
    token = (token or "").strip()
    ledger = (engine_ledger or "").strip()
    if not token or not ledger:
        return False
    if token == ledger:
        return True
    if ledger.startswith("qledger:"):
        return token == ledger.split(":", 1)[1]
    segments = ledger.split("/")
    # segments[1:] — the leading segment is the store ROOT ("data", "site"), shared by
    # thousands of paths. A token equal to it would bind one species to every engine.
    if token in segments[1:]:
        return True
    base = segments[-1]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    return token == stem


def bind_species(
    engine_ledger: str,
    species: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Bind species rows to an engine by matching ledger_binding.ledger.

    Returns the derived validation_state plus the evidence set. ``species is None`` means
    the store could not be read — the caller must render that as "could not look", never
    as "looked and found nothing".
    """
    if species is None:
        return {"validation_state": None, "bound": None, "reason": "species_store_absent"}
    if engine_ledger == LEDGER_NONE:
        return {"validation_state": VALIDATION_STATE_DEFAULT, "bound": [], "reason": "no_ledger"}

    bound: list[dict[str, str]] = []
    for row in species:
        binding = ((row.get("ledger_binding") or {}).get("ledger")) or ""
        for token in _species_tokens(binding):
            if species_token_matches_ledger(token, engine_ledger):
                bound.append(
                    {
                        "species_id": str(row.get("species_id")),
                        "validation_status": str(row.get("validation_status")),
                    }
                )
                break

    if not bound:
        return {"validation_state": VALIDATION_STATE_DEFAULT, "bound": [], "reason": "no_species_bound"}

    statuses = {b["validation_status"] for b in bound}
    for candidate in _VALIDATION_CONSERVATISM:
        if candidate in statuses:
            return {
                "validation_state": candidate,
                "bound": sorted(bound, key=lambda b: b["species_id"]),
                "reason": "least_advanced_of_bound" if len(bound) > 1 else "single_species",
            }
    return {"validation_state": VALIDATION_STATE_DEFAULT, "bound": bound, "reason": "unknown_status"}


# ---------------------------------------------------------------------------
# Registry construction
# ---------------------------------------------------------------------------

def build_registry(
    *,
    synapse: Mapping[str, Any],
    overlay: Mapping[str, Any] | None = None,
    desk_scans: Mapping[str, DeskScan] | None = None,
    article2_modules: Iterable[str] | None = (),
    species: Sequence[Mapping[str, Any]] | None = None,
    qual_ladder_keys: Iterable[str] | None = None,
    file_exists: Callable[[str], bool] | None = None,
    qledger_desk_rows: Mapping[str, int] | None = None,
    qledger_desk_horizons: Mapping[str, Sequence[int]] | None = None,
) -> dict[str, Any]:
    """Build the whole registry view. Pure — no file I/O, deterministic, sorted throughout.

    NOTHING here is written to disk by anyone. There is no committed artifact, no drift
    guard and no equality pin, so corpus-derived values (``ledger_evidence.corpus_rows``,
    ``declared_horizon.horizon_d``) are simply part of the view.

    Every optional input has an epistemic null:

      ``species is None``            -> ``validation_state: None`` ("could not look"),
                                        never ``phase0``.
      ``qual_ladder_keys``/``file_exists`` absent -> resolution ``"unchecked"``, never
                                        ``"unresolved"`` — and ``unchecked`` is NOT
                                        counted as evidence by the C-1 gate.
      ``article2_modules is None``   -> the scored_path_surfaces completeness detector did
                                        not run; the flag is ``None``, not ``False``.
      ``qledger_desk_rows is None``  -> ``corpus_rows: None`` and ``corpus_checked:
                                        False``.
    """
    artifacts: Mapping[str, Any] = synapse.get("artifacts") or {}
    overlay_rows: Mapping[str, Any] = (overlay or {}).get("engines") or {}
    desk_scans = desk_scans or {}
    article2 = None if article2_modules is None else frozenset(article2_modules)
    ladder_keys = None if qual_ladder_keys is None else set(qual_ladder_keys)

    cells = partition_artifacts(synapse)
    artifact_authority = derive_artifact_authority(synapse)

    # owner_program span per producer — makes the 15 cross-program utility producers
    # visible rather than silently collapsed by the demotion of owner_program to a
    # grouping dimension.
    span: dict[str, set[str]] = {}
    for entry in artifacts.values():
        if isinstance(entry, dict):
            span.setdefault(entry.get("producer") or "", set()).add(entry.get("owner_program") or "")

    # First pass over cells to build producer -> ledger index, needed by waterfall rule 4.
    # Store-shaped only, and NEVER the producer module itself — a rule-4 hop that lands on
    # a `.py` file is how `scripts/seed_us_sector_baskets.py::sector-pulse` came to be
    # "graded by" engine/demand_ledger.py.
    producer_ledger_index: dict[str, str] = {}
    for eid, artifact_ids in cells.items():
        producer = eid.split(ENGINE_ID_SEP, 1)[0]
        entries = [artifacts[a] for a in artifact_ids]
        paths = _cell_ledger_paths(entries)
        if paths:
            producer_ledger_index.setdefault(producer, paths[0])

    engines: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    bound_species_ids: set[str] = set()

    for eid, artifact_ids in cells.items():
        producer, owner_program = eid.split(ENGINE_ID_SEP, 1)
        entries = [artifacts[a] for a in artifact_ids]
        row_overlay = overlay_rows.get(eid) or {}

        # --- artifacts (unit of EVIDENCE) ---------------------------------
        # DERIVED BEFORE ANY EXCLUSION DECISION, so an exclusion can describe what it
        # deletes. The first version hit `continue` here, and a 3-character
        # `not_an_engine` reason then removed a gate_size engine with every law green.
        artifact_rows = []
        for aid in artifact_ids:
            entry = artifacts[aid]
            auth = artifact_authority.get(aid, {"authority": "display", "rule": "d"})
            ref = entry.get("qual_ladder_ref")
            artifact_rows.append(
                {
                    "id": aid,
                    "path": entry.get("path"),
                    "tier": entry.get("tier"),
                    "horizon_role": entry.get("horizon_role"),
                    "freshness_sla_hours": entry.get("freshness_sla_hours"),
                    "storage": entry.get("storage"),
                    "scored_path_surfaces": sorted(entry.get("scored_path_surfaces") or []),
                    "qual_ladder_ref": ref,
                    "qual_ladder_ref_resolution": resolve_qual_ladder_ref(
                        ref, qual_ladder_keys=ladder_keys, file_exists=file_exists
                    ),
                    "artifact_authority": auth["authority"],
                    "artifact_authority_rule": auth["rule"],
                }
            )

        # --- authority + evidence -----------------------------------------
        authority = max_authority(r["artifact_authority"] for r in artifact_rows)
        winners = [r for r in artifact_rows if r["artifact_authority"] == authority] or [
            artifact_rows[0]
        ]

        # Completeness flag — PROPOSES, never promotes. The measured prophet-index case:
        # consumed by an Article-2 enforcer module while declaring no scored_path_surfaces.
        # `article2 is None` means the module table could not be imported: the detector did
        # not run, so the flag is None ("could not look"), never False.
        completeness: list[str] | None
        if article2 is None:
            completeness = None
        else:
            completeness = []
            for aid in artifact_ids:
                entry = artifacts[aid]
                if entry.get("scored_path_surfaces"):
                    continue
                hits = sorted(set(entry.get("consumers") or []) & article2)
                if hits:
                    completeness.append(
                        f"{aid} read by {', '.join(hits)} with no scored_path_surfaces"
                    )

        # THE C-1 GATE INPUT, AT THE ARTIFACT LEVEL, IN THREE DISJOINT BUCKETS. A cell-wide
        # union clears on ANY sibling's ref, so an unevidenced gate_size artifact went
        # unflagged whenever a decorative `display` sibling carried a pointer (reproduced
        # live 2026-08-12 on scripts/build_basket_washout_state.py::blocked-entry-override).
        # `unchecked` is its OWN bucket and is NOT evidence: a ref nobody probed cannot
        # count as the prereg that earned authority.
        above_display = [r for r in artifact_rows if r["artifact_authority"] != "display"]
        unevidenced = sorted(
            r["id"] for r in above_display if not r["qual_ladder_ref"]
        )
        unresolvable = sorted(
            r["id"]
            for r in artifact_rows
            if r["qual_ladder_ref"] and r["qual_ladder_ref_resolution"] == "unresolved"
        )
        unchecked = sorted(
            r["id"]
            for r in above_display
            if r["qual_ladder_ref"] and r["qual_ladder_ref_resolution"] == "unchecked"
        )

        authority_evidence = {
            # ATTRIBUTION. The value names the rule AND every artifact that produced it —
            # a singular `artifact_id` named only the first sorted winner, so on
            # multi-winner cells the prescribed heal pointed at the wrong artifact.
            "rule": winners[0]["artifact_authority_rule"],
            "artifact_ids": sorted(r["id"] for r in winners),
            "surfaces": sorted({s for r in winners for s in r["scored_path_surfaces"]}),
            "completeness_flag": None if completeness is None else bool(completeness),
            "completeness_detail": None if completeness is None else sorted(completeness),
            "unevidenced_artifacts": unevidenced,
            "unresolvable_artifacts": unresolvable,
            "unchecked_artifacts": unchecked,
        }

        # --- ledger -------------------------------------------------------
        ledger_info = derive_ledger(
            producer=producer,
            artifact_entries=entries,
            desk_scan=desk_scans.get(producer),
            producer_ledger_index=producer_ledger_index,
        )
        ledger = ledger_info["ledger"]
        desk = ledger_info.get("desk")
        shape = None if ledger == LEDGER_NONE or desk else ledger_shape(ledger)
        ledger_evidence = {
            "rule": ledger_info["rule"],
            "desk": desk,
            "via": ledger_info.get("via"),
            "shape": shape,
            # Corpus-derived, and that is FINE — nothing pins this view.
            "corpus_checked": bool(desk) and qledger_desk_rows is not None,
            "corpus_rows": (
                None
                if desk is None or qledger_desk_rows is None
                else int(qledger_desk_rows.get(desk, 0))
            ),
        }

        # --- graded_by_design ---------------------------------------------
        # A TEMPLATE ledger names a family of stores, not a store. It cannot be opened, so
        # it is not evidence that grading happens — 'no — not yet' says exactly that.
        if ledger != LEDGER_NONE and shape != LEDGER_SHAPE_TEMPLATE:
            graded = GRADED_YES
            if ledger_info["rule"] in _WEAK_LEDGER_RULES:
                graded_evidence = GRADED_EVIDENCE_WEAK
                graded_source = (
                    f"derived by WEAK FILENAME HEURISTIC (ledger waterfall rule "
                    f"{ledger_info['rule']}): a path/module NAME matching /ledger|grade/ "
                    f"resolved to {ledger!r}. A filename is not proof that graded rows are "
                    f"written — treat as a candidate, not as gradeability"
                )
            else:
                graded_evidence = GRADED_EVIDENCE_STRONG
                graded_source = (
                    f"derived (ledger waterfall rule {ledger_info['rule']}): "
                    + (
                        f"the producer registers qledger desk {desk!r} by AST"
                        if desk
                        else "an artifact DECLARES tier shadow/scored/confirmer, which "
                        "synapse's tier_vocabulary defines as claim-registered and graded"
                    )
                )
        elif shape == LEDGER_SHAPE_TEMPLATE:
            graded = GRADED_NOT_YET
            graded_evidence = GRADED_EVIDENCE_NONE
            graded_source = (
                "derived: the resolved ledger is an unexpanded template path, not a store "
                "that can be opened"
            )
        elif all(e.get("tier") == "infrastructure" for e in entries):
            graded = GRADED_DESCRIPTIVE
            graded_evidence = GRADED_EVIDENCE_NONE
            graded_source = (
                "derived: every artifact is tier=infrastructure (operational rail, not a "
                "signal)"
            )
        else:
            graded = GRADED_NOT_YET
            graded_evidence = GRADED_EVIDENCE_NONE
            graded_source = "derived: no ledger and not purely infrastructure"
        overlay_graded = (row_overlay.get("graded_by_design") or {}).get("value")
        if overlay_graded and graded == OVERLAY_GRADED_TRANSITION[0]:
            graded = overlay_graded
            graded_evidence = GRADED_EVIDENCE_NONE
            graded_source = "curated: " + str(
                (row_overlay.get("graded_by_design") or {}).get("reason") or ""
            )

        # --- output_class --------------------------------------------------
        # `or ledger != LEDGER_NONE`: keying only on authority and tier exempted 26 engines
        # the registry itself marks graded_by_design='yes' — including
        # scripts/build_prophet.py::momoedge — as "not_required_display_only". An
        # Evaluation OS whose unit of account is the metric contract cannot declare the
        # contract not required for a graded engine.
        gate_tripped = (
            authority != "display"
            or any(e.get("tier") in _TIER_EVALUATED for e in entries)
            or ledger != LEDGER_NONE
        )
        overlay_class = (row_overlay.get("output_class") or {}).get("value")
        if overlay_class:
            output_class = overlay_class
            output_class_reason = "curated: " + str(
                (row_overlay.get("output_class") or {}).get("rationale") or ""
            )
        else:
            output_class = None
            output_class_reason = (
                "required_but_uncurated" if gate_tripped else "not_required_display_only"
            )

        # --- declared_horizon ---------------------------------------------
        roles = sorted({e.get("horizon_role") for e in entries if e.get("horizon_role")})
        declared_horizon = {
            "horizon_role": roles,
            "horizon_role_homogeneous": len(roles) <= 1,
            "horizon_d": (
                None
                if desk is None or qledger_desk_horizons is None
                else (sorted({int(h) for h in (qledger_desk_horizons.get(desk) or [])}) or None)
            ),
        }

        # --- validation_state ---------------------------------------------
        binding = bind_species(ledger, species)
        validation_state = binding["validation_state"]
        for entry_bound in binding["bound"] or []:
            bound_species_ids.add(entry_bound["species_id"])
        validation_evidence: dict[str, Any] = {
            "bound_species": binding["bound"],
            "reason": binding["reason"],
        }
        overlay_validation = row_overlay.get("validation_state") or {}
        if overlay_validation.get("value") in OVERLAY_TERMINAL_STATES:
            validation_state = overlay_validation["value"]
            validation_evidence = {
                "bound_species": binding["bound"],
                "reason": "curated_terminal_ratification",
                "dnr_key": overlay_validation.get("dnr_key"),
                "ratified_by": overlay_validation.get("ratified_by"),
                "date": overlay_validation.get("date"),
            }

        # --- evidence_ref (fixes C-1) -------------------------------------
        # A roll-up of the RESOLVED refs in the cell — resolved, not merely present: an
        # `unchecked` or `unresolved` ref is not evidence. Deliberately NOT the gate input
        # (see authority_evidence.unevidenced_artifacts above).
        refs = sorted(
            {
                str(e["qual_ladder_ref"])
                for e in artifact_rows
                if e["qual_ladder_ref"]
                and e["qual_ladder_ref_resolution"] in QUAL_LADDER_RESOLVED
            }
        )
        evidence_ref = refs or None

        # --- not_an_engine, decided LAST so the exclusion can describe itself ----
        derived_exclusion = placeholder_reason(producer)
        curated_exclusion = row_overlay.get("not_an_engine")
        if derived_exclusion or curated_exclusion:
            reason = derived_exclusion or (curated_exclusion or {}).get("reason")
            excluded.append(
                {
                    "engine_id": eid,
                    "producer": producer,
                    "owner_program": owner_program,
                    "artifacts": artifact_ids,
                    "reason": reason,
                    "source": "derived" if derived_exclusion else "curated",
                    # What the overlay is DELETING. validate_structure() refuses a curated
                    # exclusion whose would_be_authority is above display, and
                    # audit_content() still reports every CURATED exclusion at ANY
                    # authority, so the backlog cannot be deflated by an exclusion.
                    "would_be_authority": authority,
                    "would_be_tiers": sorted({str(r["tier"]) for r in artifact_rows}),
                    "would_be_artifact_authorities": sorted(
                        {r["artifact_authority"] for r in artifact_rows}
                    ),
                    "would_be_ledger": ledger,
                    "would_be_output_class_reason": output_class_reason,
                    "would_be_unevidenced_artifacts": unevidenced,
                    "would_be_unresolvable_artifacts": unresolvable,
                }
            )
            continue

        engines.append(
            {
                "engine_id": eid,
                "producer": producer,
                "owner_program": owner_program,
                "owner_program_span": len(span.get(producer) or {owner_program}),
                "artifacts": artifact_rows,
                "consumers": sorted(
                    {c for e in entries for c in (e.get("consumers") or [])} - {producer}
                ),
                "output_class": output_class,
                "output_class_reason": output_class_reason,
                "authority": authority,
                "authority_evidence": authority_evidence,
                "ledger": ledger,
                "ledger_evidence": ledger_evidence,
                "graded_by_design": graded,
                "graded_by_design_evidence": graded_evidence,
                "graded_by_design_source": graded_source,
                "declared_horizon": declared_horizon,
                "validation_state": validation_state,
                "validation_state_evidence": validation_evidence,
                "evidence_ref": evidence_ref,
            }
        )

    engines.sort(key=lambda r: r["engine_id"])
    excluded.sort(key=lambda r: r["engine_id"])

    n_artifacts = sum(1 for e in artifacts.values() if isinstance(e, dict))
    covered = sum(len(r["artifacts"]) for r in engines) + sum(len(r["artifacts"]) for r in excluded)

    # THE INVERSE OF bind_species. A species whose ledger_binding matches no engine was
    # dropped in complete silence. Measured 2026-08-12: 2 of 27 species are unbound and
    # BOTH are `accruing` — either an understated engine or an orphaned species, a fact
    # worth naming either way.
    if species is None:
        unbound: list[dict[str, str]] | None = None
    else:
        unbound = sorted(
            (
                {
                    "species_id": str(row.get("species_id")),
                    "validation_status": str(row.get("validation_status")),
                }
                for row in species
                if str(row.get("species_id")) not in bound_species_ids
                and _species_tokens(((row.get("ledger_binding") or {}).get("ledger")) or "")
            ),
            key=lambda r: r["species_id"],
        )

    return {
        "schema": SCHEMA,
        "meta": {
            "unit_of_account": "engine = (producer, owner_program) from config/synapse.yml",
            "engine_id_format": "{producer}::{owner_program}",
            "derived_on_demand": True,
            "n_engines": len(engines),
            "n_excluded": len(excluded),
            "n_artifacts": n_artifacts,
            "n_artifacts_mapped": covered,
            "authority_order": list(AUTHORITY_ORDER),
            "unbound_species": unbound,
            "corpus": {
                "qledger_read": qledger_desk_rows is not None,
                "n_desks": None if qledger_desk_rows is None else len(qledger_desk_rows),
                "species_read": species is not None,
                "qual_ladder_read": ladder_keys is not None and file_exists is not None,
                "article2_read": article2 is not None,
            },
        },
        "engines": engines,
        "excluded": excluded,
    }


# ---------------------------------------------------------------------------
# Content audit — what the view SAYS about the corpus
# ---------------------------------------------------------------------------

def audit_content(registry: Mapping[str, Any]) -> list[Finding]:
    """Findings about the CORPUS the registry describes.

    Every one of these is a PRE-EXISTING CONDITION no PR author caused, which is why the
    owning house law is warn-tier and only exits non-zero under ``--strict``. Wiring them
    hard on arrival would red main fleet-wide for a property nobody introduced — a gate
    that fires fleet-wide on first wiring gets routed around instead of obeyed.
    """
    findings: list[Finding] = []

    # EXCLUDED ROWS ARE AUDITED TOO — and a CURATED exclusion is audited at EVERY
    # authority, not only above display. Restricting the audit to would_be_authority >
    # display left a hole: a curated `not_an_engine` on a display-or-below cell silently
    # removed its OUTPUT_CLASS_MISSING / unresolvable-ref findings from the backlog. Every
    # curated exclusion is now itself a finding, so the deflation is visible even when the
    # deleted cell had nothing else to say.
    for row in registry.get("excluded") or []:
        eid = row.get("engine_id", "?")
        curated = row.get("source") == "curated"
        if curated:
            findings.append(
                Finding(
                    "ENGINE_EXCLUDED_BY_OVERLAY",
                    SEVERITY_CONTENT,
                    eid,
                    f"removed from the census by config/intelligence_registry_overlay.yml "
                    f"— would_be_authority={row.get('would_be_authority')!r}, "
                    f"would_be_tiers={row.get('would_be_tiers')}, "
                    f"would_be_ledger={row.get('would_be_ledger')!r}. An exclusion "
                    f"SHRINKS the backlog this registry exists to produce, so it is "
                    f"reported every run: {row.get('reason')}",
                )
            )
        if not curated and row.get("would_be_authority") in (None, "display"):
            # A DERIVED placeholder exclusion of a display cell has nothing to hide.
            continue
        if row.get("would_be_unevidenced_artifacts"):
            findings.append(
                Finding(
                    "AUTHORITY_WITHOUT_EVIDENCE",
                    SEVERITY_CONTENT,
                    eid,
                    f"EXCLUDED ({row.get('source')}) but would hold "
                    f"authority={row.get('would_be_authority')} — unevidenced artifact(s): "
                    f"{', '.join(row['would_be_unevidenced_artifacts'])}. HEAL: add "
                    f"qual_ladder_ref to config/synapse.yml for each",
                )
            )
        if row.get("would_be_unresolvable_artifacts"):
            findings.append(
                Finding(
                    "AUTHORITY_EVIDENCE_UNRESOLVABLE",
                    SEVERITY_CONTENT,
                    eid,
                    f"EXCLUDED ({row.get('source')}) but carries qual_ladder_ref(s) that "
                    f"resolve to nothing: "
                    f"{', '.join(row['would_be_unresolvable_artifacts'])}",
                )
            )
        if row.get("would_be_output_class_reason") == "required_but_uncurated":
            findings.append(
                Finding(
                    "OUTPUT_CLASS_MISSING",
                    SEVERITY_CONTENT,
                    eid,
                    f"EXCLUDED ({row.get('source')}) but would trip the evaluation gate "
                    f"with no output_class — the metric contract is undefined",
                )
            )

    for row in registry.get("engines") or []:
        eid = row.get("engine_id", "?")
        evidence = row.get("authority_evidence") or {}

        # C-1 — authority with no pointer to the prereg that earned it. Gated on the
        # per-ARTIFACT list, never on the cell-wide evidence_ref union.
        if evidence.get("unevidenced_artifacts"):
            findings.append(
                Finding(
                    "AUTHORITY_WITHOUT_EVIDENCE",
                    SEVERITY_CONTENT,
                    eid,
                    f"authority={row.get('authority')} but "
                    f"{len(evidence['unevidenced_artifacts'])} artifact(s) above display "
                    f"carry no qual_ladder_ref — HEAL: add qual_ladder_ref to "
                    f"config/synapse.yml for "
                    f"{', '.join(evidence['unevidenced_artifacts'])}",
                )
            )

        # "No pointer" and "pointer at nothing" need different heals, so they are
        # different codes. A ref resolving to neither a config/qual_ladder.yml key nor an
        # existing FILE is not evidence — it is a string. A DIRECTORY is a string too.
        if evidence.get("unresolvable_artifacts"):
            findings.append(
                Finding(
                    "AUTHORITY_EVIDENCE_UNRESOLVABLE",
                    SEVERITY_CONTENT,
                    eid,
                    "qual_ladder_ref present but resolves to neither a "
                    "config/qual_ladder.yml key nor an existing repo FILE (a directory is "
                    "not a prereg): "
                    + "; ".join(
                        f"{a['id']} -> {a.get('qual_ladder_ref')!r}"
                        for a in row.get("artifacts") or []
                        if a.get("id") in set(evidence["unresolvable_artifacts"])
                    ),
                )
            )

        # THE EPISTEMIC NULL, REPORTED RATHER THAN BANKED. An unprobed ref is not evidence.
        if evidence.get("unchecked_artifacts"):
            findings.append(
                Finding(
                    "AUTHORITY_EVIDENCE_UNCHECKED",
                    SEVERITY_CONTENT,
                    eid,
                    f"authority={row.get('authority')} and a qual_ladder_ref is present, "
                    f"but the resolver had no inputs so it was never probed — this is "
                    f"'could not look', NOT evidence: "
                    f"{', '.join(evidence['unchecked_artifacts'])}",
                )
            )

        if row.get("output_class_reason") == "required_but_uncurated":
            findings.append(
                Finding(
                    "OUTPUT_CLASS_MISSING",
                    SEVERITY_CONTENT,
                    eid,
                    "engine trips the evaluation gate but no output_class is curated — "
                    "the metric contract is undefined",
                )
            )

        # THE HEURISTIC DISCLOSURE, ENUMERATED PER ENGINE. `graded_by_design: yes` reached
        # by ledger waterfall rule 1 or 4 rests on a FILENAME SUBSTRING, not on a
        # declaration. These are the known-wrong CANDIDATES, listed mechanically so the
        # list cannot rot; a hand-maintained list of wrong rows would.
        if (
            row.get("graded_by_design") == GRADED_YES
            and row.get("graded_by_design_evidence") == GRADED_EVIDENCE_WEAK
        ):
            findings.append(
                Finding(
                    "GRADED_BY_DESIGN_IS_HEURISTIC",
                    SEVERITY_CONTENT,
                    eid,
                    f"graded_by_design='yes' rests on a FILENAME SUBSTRING (ledger "
                    f"waterfall rule {(row.get('ledger_evidence') or {}).get('rule')} "
                    f"resolved {row.get('ledger')!r}) — a candidate, not proof that graded "
                    f"rows are written. T7 must not count this as gradeability",
                )
            )

        # Reachable when this audit runs against a HAND-EDITED or externally supplied view:
        # a row claiming an engine is ungraded while its ledger says otherwise. A TEMPLATE
        # ledger is not a contradiction — 'no — not yet' is the CORRECT value there.
        if (
            row.get("graded_by_design") in (GRADED_NOT_YET, GRADED_DESCRIPTIVE)
            and row.get("ledger") not in (LEDGER_NONE, None)
            and (row.get("ledger_evidence") or {}).get("shape") != LEDGER_SHAPE_TEMPLATE
        ):
            findings.append(
                Finding(
                    "GRADED_BY_DESIGN_CONTRADICTS_LEDGER",
                    SEVERITY_CONTENT,
                    eid,
                    f"graded_by_design={row.get('graded_by_design')!r} but "
                    f"ledger={row.get('ledger')!r}",
                )
            )

        if evidence.get("completeness_flag") is None:
            findings.append(
                Finding(
                    "SCORED_PATH_SURFACES_UNCHECKED",
                    SEVERITY_CONTENT,
                    eid,
                    "the Article-2 module table could not be imported, so the "
                    "scored_path_surfaces completeness detector did not run — 'could not "
                    "look', not 'looked and found nothing'",
                )
            )
        elif evidence.get("completeness_flag"):
            findings.append(
                Finding(
                    "SCORED_PATH_SURFACES_INCOMPLETE",
                    SEVERITY_CONTENT,
                    eid,
                    "; ".join(evidence.get("completeness_detail") or []),
                )
            )

        # A registered qledger desk with zero rows in the live claim corpus. `corpus_rows`
        # is None when the corpus could not be read, which must not read as zero.
        ledger_evidence = row.get("ledger_evidence") or {}
        if (
            ledger_evidence.get("desk")
            and ledger_evidence.get("corpus_checked")
            and ledger_evidence.get("corpus_rows") == 0
        ):
            findings.append(
                Finding(
                    "LEDGER_DECLARED_BUT_EMPTY",
                    SEVERITY_CONTENT,
                    eid,
                    f"registers qledger desk {ledger_evidence['desk']!r} but the claim "
                    f"corpus holds zero rows for it",
                )
            )

    for row in (registry.get("meta") or {}).get("unbound_species") or []:
        findings.append(
            Finding(
                "SPECIES_UNBOUND",
                SEVERITY_CONTENT,
                f"species:{row.get('species_id')}",
                f"species {row.get('species_id')!r} (validation_status="
                f"{row.get('validation_status')!r}) declares a ledger_binding that matches "
                f"no engine ledger — either an engine's validation_state is understated or "
                f"the species is orphaned",
            )
        )

    findings.sort(key=lambda f: (f.code, f.engine_id))
    return findings


# ---------------------------------------------------------------------------
# Structural validation
# ---------------------------------------------------------------------------

_REQUIRED_ENGINE_KEYS = frozenset({
    "engine_id", "producer", "owner_program", "owner_program_span", "artifacts",
    "consumers", "output_class", "output_class_reason", "authority",
    "authority_evidence", "ledger", "ledger_evidence", "graded_by_design",
    "graded_by_design_evidence", "graded_by_design_source", "declared_horizon",
    "validation_state", "validation_state_evidence", "evidence_ref",
})

#: An exclusion must SAY WHAT IT DELETES. Without these the excluded rows are opaque and
#: the refusal below has nothing to read.
_REQUIRED_EXCLUDED_KEYS = frozenset({
    "engine_id", "producer", "owner_program", "artifacts", "reason", "source",
    "would_be_authority", "would_be_tiers", "would_be_artifact_authorities",
    "would_be_ledger", "would_be_output_class_reason", "would_be_unevidenced_artifacts",
    "would_be_unresolvable_artifacts",
})


def validate_overlay(
    overlay: Mapping[str, Any] | None,
    known_engine_ids: Iterable[str],
    *,
    valid_validation_statuses: Iterable[str] = (),
) -> list[str]:
    """Validate the curated overlay. Returns violation strings; empty means clean.

    The four-key allowlist is the executable form of ``DNR:KILL-PARALLEL-KNOWLEDGE-BASE``:
    without it the overlay silently becomes the hand-authored engine list that row forbids.

    ORPHAN RULE — an overlay row keyed by an engine_id the partition did not generate is a
    violation, not a warning. Otherwise the overlay accumulates rows for deleted engines
    and becomes a shadow store of dead state; orphan detection is also the tripwire for a
    producer file being deleted and its engine vanishing unnoticed.
    """
    violations: list[str] = []
    if overlay is None:
        return violations
    if not isinstance(overlay, dict):
        return ["overlay is not a mapping"]

    if "schema_version" not in overlay:
        violations.append("overlay: missing schema_version")

    rows = overlay.get("engines")
    if rows is None:
        return violations
    if not isinstance(rows, dict):
        return violations + ["overlay.engines is not a mapping"]

    known = set(known_engine_ids)
    terminal_ok = set(valid_validation_statuses) or set(OVERLAY_TERMINAL_STATES)

    for eid, row in rows.items():
        if eid not in known:
            violations.append(
                f"overlay: orphan row {eid!r} — no such engine (deleted producer, or a "
                f"stale hand-authored entry)"
            )
        if not isinstance(row, dict):
            violations.append(f"overlay[{eid}]: row is not a mapping")
            continue

        for key in row:
            if key in OVERLAY_FORBIDDEN_KEYS:
                violations.append(
                    f"overlay[{eid}]: key {key!r} is DERIVED and may never be curated "
                    f"(DNR:KILL-PARALLEL-KNOWLEDGE-BASE)"
                )
            elif key not in OVERLAY_ALLOWED_KEYS:
                violations.append(
                    f"overlay[{eid}]: key {key!r} is outside the four-key allowlist "
                    f"{sorted(OVERLAY_ALLOWED_KEYS)}"
                )

        oc = row.get("output_class")
        if oc is not None:
            if not isinstance(oc, dict) or oc.get("value") not in OUTPUT_CLASSES:
                violations.append(
                    f"overlay[{eid}]: output_class.value must be one of {sorted(OUTPUT_CLASSES)}"
                )
            elif not str(oc.get("rationale") or "").strip():
                violations.append(f"overlay[{eid}]: output_class requires a non-empty rationale")

        gd = row.get("graded_by_design")
        if gd is not None:
            if not isinstance(gd, dict) or gd.get("value") != OVERLAY_GRADED_TRANSITION[1]:
                violations.append(
                    f"overlay[{eid}]: graded_by_design may only write "
                    f"{OVERLAY_GRADED_TRANSITION[1]!r} (never {GRADED_YES!r} — that must be "
                    f"earned by a real ledger — and never {GRADED_NOT_YET!r}, the safe default)"
                )
            elif not str(gd.get("reason") or "").strip():
                violations.append(f"overlay[{eid}]: graded_by_design requires a non-empty reason")

        vs = row.get("validation_state")
        if vs is not None:
            # ONE predicate, not a chain. Intersecting OVERLAY_TERMINAL_STATES with the
            # live species vocabulary keeps the cross-check — if engine/species_registry.py
            # ever drops 'falsified' or 'retired', the overlay may no longer ratify it.
            ratifiable = set(OVERLAY_TERMINAL_STATES) & terminal_ok
            if not isinstance(vs, dict) or vs.get("value") not in ratifiable:
                violations.append(
                    f"overlay[{eid}]: validation_state may only ratify "
                    f"{sorted(ratifiable)} (terminal states that are also valid species "
                    f"statuses)"
                )
            else:
                violations += _citation_violations(eid, "terminal validation_state", vs)

        nae = row.get("not_an_engine")
        if nae is not None:
            # CITATION PARITY WITH validation_state. `not_an_engine` is the most
            # destructive of the four keys — it deletes a whole engine from the census —
            # and it used to be the LEAST gated: a 3-character reason removed a gate_size
            # engine with every law green.
            if not isinstance(nae, dict):
                violations.append(f"overlay[{eid}]: not_an_engine must be a mapping")
            else:
                reason = str(nae.get("reason") or "").strip()
                if not reason:
                    violations.append(
                        f"overlay[{eid}]: not_an_engine requires a non-empty reason — "
                        f"nothing is ever excluded silently"
                    )
                elif len(reason) < NOT_AN_ENGINE_MIN_REASON_CHARS:
                    violations.append(
                        f"overlay[{eid}]: not_an_engine reason is {len(reason)} chars — "
                        f"deleting an engine from the census requires at least "
                        f"{NOT_AN_ENGINE_MIN_REASON_CHARS}, so the argument is on the "
                        f"record and not a shrug"
                    )
                violations += _citation_violations(eid, "not_an_engine", nae, require_dnr=False)

    return violations


def _citation_violations(
    eid: str, label: str, block: Mapping[str, Any], *, require_dnr: bool = True
) -> list[str]:
    """Shared citation contract: who ratified it, when, and under which standing kill."""
    out: list[str] = []
    required = ("dnr_key", "ratified_by", "date") if require_dnr else ("ratified_by", "date")
    for field in required:
        if not str(block.get(field) or "").strip():
            out.append(f"overlay[{eid}]: {label} requires {field!r}")
    key = str(block.get("dnr_key") or "")
    if key and not key.startswith("DNR:"):
        out.append(
            f"overlay[{eid}]: dnr_key {key!r} must be cited as DNR:<KEY> "
            f"(row numbers shift on every append)"
        )
    return out


def validate_structure(
    registry: Mapping[str, Any],
    *,
    valid_validation_statuses: Iterable[str] = (),
) -> list[str]:
    """Validate the registry view's own structure. Returns violations; empty = clean.

    INVARIANTS ONLY. There is no committed artifact to compare against, so this never
    checks drift, staleness or byte equality — the four things it does check are:

      1. the partition is TOTAL and DISJOINT (every synapse artifact maps to exactly one
         engine or to exactly one explicit exclusion);
      2. every enum value is in vocabulary and no required field is missing;
      3. AUTHORITY IS ATTRIBUTABLE — every engine's authority names the rule and the
         artifact(s) that produced it, and those artifacts really carry it;
      4. an exclusion says what it deletes, and a CURATED exclusion may not remove an
         authority-bearing or evaluated cell.
    """
    violations: list[str] = []

    if registry.get("schema") != SCHEMA:
        violations.append(f"schema must be {SCHEMA!r}, got {registry.get('schema')!r}")

    meta = registry.get("meta")
    if not isinstance(meta, dict):
        return violations + ["meta block is missing or not a dict"]

    engines = registry.get("engines")
    excluded = registry.get("excluded")
    if not isinstance(engines, list) or not isinstance(excluded, list):
        return violations + ["engines/excluded must be lists"]

    statuses = set(valid_validation_statuses)
    seen_ids: set[str] = set()
    artifact_owner: dict[str, str] = {}

    for row in engines:
        eid = row.get("engine_id", "?")
        if eid in seen_ids:
            violations.append(f"{eid}: duplicate engine_id")
        seen_ids.add(eid)

        missing = _REQUIRED_ENGINE_KEYS - set(row)
        if missing:
            violations.append(f"{eid}: missing required field(s) {sorted(missing)}")
            continue

        if row["authority"] not in AUTHORITIES:
            violations.append(f"{eid}: authority {row['authority']!r} not in {sorted(AUTHORITIES)}")
        if row["graded_by_design"] not in GRADED_BY_DESIGN_VALUES:
            violations.append(
                f"{eid}: graded_by_design {row['graded_by_design']!r} not in "
                f"{sorted(GRADED_BY_DESIGN_VALUES)}"
            )
        if row["graded_by_design_evidence"] not in GRADED_EVIDENCE_VALUES:
            violations.append(
                f"{eid}: graded_by_design_evidence "
                f"{row['graded_by_design_evidence']!r} not in "
                f"{sorted(GRADED_EVIDENCE_VALUES)} — a graded claim must state how strong "
                f"its evidence is"
            )
        if row["output_class"] is not None and row["output_class"] not in OUTPUT_CLASSES:
            violations.append(f"{eid}: output_class {row['output_class']!r} not in {sorted(OUTPUT_CLASSES)}")
        if row["ledger"] in (None, ""):
            violations.append(f"{eid}: ledger must never be null — use {LEDGER_NONE!r}")
        if statuses and row["validation_state"] is not None and row["validation_state"] not in statuses:
            violations.append(
                f"{eid}: validation_state {row['validation_state']!r} not in {sorted(statuses)}"
            )
        if row["engine_id"] != engine_id_for(row["producer"], row["owner_program"]):
            violations.append(f"{eid}: engine_id does not match producer::owner_program")

        artifact_authorities: dict[str, str] = {}
        for artifact in row["artifacts"] or []:
            aid = artifact.get("id")
            if aid in artifact_owner:
                violations.append(
                    f"{eid}: artifact {aid!r} also mapped to {artifact_owner[aid]!r} — "
                    f"the partition must be disjoint"
                )
            else:
                artifact_owner[aid] = eid
            if artifact.get("artifact_authority") not in AUTHORITIES:
                violations.append(
                    f"{eid}: artifact {aid!r} authority {artifact.get('artifact_authority')!r} "
                    f"is not a valid authority"
                )
            if artifact.get("artifact_authority_rule") not in AUTHORITY_RULES:
                violations.append(
                    f"{eid}: artifact {aid!r} authority is not ATTRIBUTABLE — rule "
                    f"{artifact.get('artifact_authority_rule')!r} is not one of "
                    f"{sorted(AUTHORITY_RULES)}"
                )
            artifact_authorities[str(aid)] = str(artifact.get("artifact_authority"))

        # ATTRIBUTION. An authority value nobody can trace to a rule and an artifact is a
        # bare assertion, which is the defect class C-1 and C-2 are instances of.
        evidence = row.get("authority_evidence")
        if not isinstance(evidence, dict):
            violations.append(f"{eid}: authority_evidence is missing or not a mapping")
        else:
            if evidence.get("rule") not in AUTHORITY_RULES:
                violations.append(
                    f"{eid}: authority {row['authority']!r} names no derivation rule "
                    f"(authority_evidence.rule={evidence.get('rule')!r})"
                )
            named = list(evidence.get("artifact_ids") or [])
            if not named:
                violations.append(
                    f"{eid}: authority {row['authority']!r} names no artifact — an "
                    f"authority value must say which artifact produced it"
                )
            for aid in named:
                if aid not in artifact_authorities:
                    violations.append(
                        f"{eid}: authority_evidence names artifact {aid!r}, which is not in "
                        f"this engine"
                    )
                elif artifact_authorities[aid] != row["authority"]:
                    violations.append(
                        f"{eid}: authority_evidence names artifact {aid!r} "
                        f"({artifact_authorities[aid]}) for engine authority "
                        f"{row['authority']!r} — the attribution does not hold"
                    )

    for row in excluded:
        eid = row.get("engine_id", "?")
        if not str(row.get("reason") or "").strip():
            violations.append(f"{eid}: excluded with an empty reason — nothing is excluded silently")

        missing_exclusion = _REQUIRED_EXCLUDED_KEYS - set(row)
        if missing_exclusion:
            violations.append(
                f"{eid}: excluded row is missing required field(s) "
                f"{sorted(missing_exclusion)} — an exclusion must describe what it deletes"
            )
        elif row.get("source") == "curated":
            # THE OVERLAY IS NOT A DELETION HATCH. It can only fire on a hand-edit to
            # config/intelligence_registry_overlay.yml, so it is PR-caused by construction.
            # DERIVED exclusions are exempt — a `<PLACEHOLDER>` token is not a repo module
            # and has no code that could hold authority.
            tiers = set(row.get("would_be_tiers") or [])
            if row.get("would_be_authority") not in (None, "display"):
                violations.append(
                    f"{eid}: an authority-bearing cell may not be excluded by overlay "
                    f"(would_be_authority={row.get('would_be_authority')!r}) — the overlay "
                    f"is not a deletion hatch"
                )
            elif tiers & EXCLUSION_FORBIDDEN_TIERS:
                violations.append(
                    f"{eid}: an evaluated cell may not be excluded by overlay "
                    f"(would_be_tiers={sorted(tiers & EXCLUSION_FORBIDDEN_TIERS)}) — the "
                    f"overlay is not a deletion hatch"
                )

        for aid in row.get("artifacts") or []:
            if aid in artifact_owner:
                violations.append(f"{eid}: excluded artifact {aid!r} also mapped to {artifact_owner[aid]!r}")
            else:
                artifact_owner[aid] = eid

    n_artifacts = meta.get("n_artifacts")
    if isinstance(n_artifacts, int) and len(artifact_owner) != n_artifacts:
        violations.append(
            f"partition is not total: {len(artifact_owner)} artifacts mapped but "
            f"meta.n_artifacts={n_artifacts} — an artifact was dropped silently"
        )

    return violations


def serialise(registry: Mapping[str, Any]) -> str:
    """Deterministic JSON text. Trailing newline so the output is a well-formed text file."""
    return json.dumps(registry, indent=2, ensure_ascii=False) + "\n"
