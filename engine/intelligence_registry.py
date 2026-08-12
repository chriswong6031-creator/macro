"""engine/intelligence_registry.py — the Mastermind engine registry (Eval OS T1).

WHY THIS EXISTS
---------------
Mastermind has four registries and none of them counts ENGINES. ``config/synapse.yml``
counts ARTIFACTS (642 of them), ``data/species/registry.json`` counts setup SPECIES (27),
``research/DO_NOT_REBUILD.md`` counts KILLS, and ``data/qledger/`` counts CLAIMS. There is
no row per *intelligence-producing capability*, so there is nothing to hang a scorecard on
(T7), nothing to roll up into a CEO view (T8), and nothing for tier routing to read (T12).

Two measured defects motivated this module (both reproduced live 2026-08-12):

  C-1  Four of the five ``tier: scored`` artifacts carry NO ``qual_ladder_ref`` —
       ``vector-calibration``, ``hazard-model``, ``vol-regime-gate`` and
       ``vol-regime-basket-overlay-gate``. Things holding rank/size/gate authority do not
       point at the prereg that earned it. Only ``site-basket-washout-state`` does.

  C-2  synapse ``tier`` does not express authority over a HUMAN. ``site-us-standouts``
       (the Prophet board that orders what a paying user sees) and ``prophet-index`` are
       both ``tier: display`` — the same value a decorative chip carries.

THE UNIT OF ACCOUNT
-------------------
``engine = (producer, owner_program)``, id ``f"{producer}::{owner_program}"``.
Measured: 642 artifacts partition into 385 cells, totally and disjointly — every artifact
belongs to exactly one engine. Chosen over the alternatives after measuring homogeneity:
only 32/385 cells (8.3%) mix ``tier`` and only 8/385 (2.1%) mix ``horizon_role``.

  - ``producer`` alone (366 rows) bundles ``site-us-standouts`` (the C-2 artifact) with
    ``pick-lab-snapshots`` (infrastructure) and ``stock-personality-forward-ledger``
    (shadow) under one authority value — 15 producers span >1 program.
  - ``owner_program`` alone (99 rows) elevates free text to identity: it has no enum in
    ``meta``, no check in ``validate_registry()`` and no filesystem anchor.
  - the artifact (642 rows) is the only fully authority-homogeneous partition, and is
    retained here as the unit of EVIDENCE (``engine["artifacts"]``) — but ``output_class``
    and ``graded_by_design`` are properties of a capability, not of a JSON file.

DERIVED, NOT AUTHORED (``DNR:KILL-PARALLEL-KNOWLEDGE-BASE``)
-------------------------------------------------------------
The spine is a pure function of canonical sources: ``config/synapse.yml``, the
``engine/*_ledger.py`` inventory, an AST scan of producer source, ``data/species/``
and ``data/qledger/``. A hand-authored engine list is the KILLED pattern. Only three
fields are curated, each because no canonical source encodes them, and they live in a
four-key overlay whose key allowlist is enforced mechanically by
``scripts/check_intelligence_registry.py`` — that allowlist IS the executable form of the
DNR row.

Notably ``authority`` and ``evidence_ref`` are NOT curated, against the recommendation of
three census reports. ``_REQUIRED_ARTIFACT_KEYS`` (engine/neuralweb/synapse.py:52) is a
required-key set, not an exact-key set, so a hand-typed ``authority:`` key in synapse.yml
would land as unenforced free text sitting next to the already-unenforced
``scored_path_surfaces`` — reproducing the exact defect class C-1 and C-2 are instances
of, one field later. Instead both derive from fields synapse ALREADY carries, so the C-1
heal repairs the canonical source rather than papering over it in a side file.

STABLE vs VOLATILE — THE ONE STRUCTURAL DECISION
------------------------------------------------
:func:`build_registry` emits ONLY fields whose sources move via a PR. Anything derived
from the append-only claim corpus is computed at read time by :func:`volatile_view` and
never serialised, and its presence in a committed file is a hard violation
(:func:`assert_no_volatile`). The long argument is in the volatile block below; the short
version is that a committed field derived from an append-only store is a scheduled
fleet-wide red, and a guard that reds the fleet for nobody's fault gets routed around
instead of obeyed.

Two audits, matching that split: :func:`audit_content` (STABLE — safe to render into a
byte-pinned doc) and :func:`audit_corpus` (needs the live corpus — stdout and annotations
only, never a committed artifact).

WHAT THIS MODULE IS
-------------------
Pure functions over already-loaded objects. It reads no files and writes no files, so it
is cheap to test with synthetic input and cannot be broken by a store-layout change. File
I/O and the sparse-worktree ladder live in ``scripts/build_intelligence_registry.py``; the
CI gate lives in ``scripts/check_intelligence_registry.py``. Where a derivation needs the
filesystem — resolving a ``qual_ladder_ref`` against a repo path — the probe is INJECTED
(``path_exists``) so the caller can route it through the git ladder rather than through
``os.path.exists``, which goes blind on a sparse cone.

Per house epistemics a null never blocks: absent inputs produce ``None`` sentinels that
render as "could not look", never as "looked and found nothing". That is why an unprobed
``qual_ladder_ref`` resolves to ``"unchecked"`` and never to ``"unresolved"``.
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

GRADED_YES = "yes"
GRADED_DESCRIPTIVE = "no — descriptive"
GRADED_NOT_YET = "no — not yet"
GRADED_BY_DESIGN_VALUES = frozenset({GRADED_YES, GRADED_DESCRIPTIVE, GRADED_NOT_YET})

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
#: both laws green (reproduced 2026-08-12); a census deletion has to carry an argument.
NOT_AN_ENGINE_MIN_REASON_CHARS = 40

#: Artifact tiers that make a cell authority-bearing regardless of the derived roll-up.
#: A curated exclusion may never remove a cell holding one — see ``validate_structure``.
EXCLUSION_FORBIDDEN_TIERS = frozenset({"scored", "confirmer", "shadow"})

# ---------------------------------------------------------------------------
# Volatile fields — WHY THE COMMITTED ARTIFACT CARRIES NONE OF THEM
# ---------------------------------------------------------------------------
#
# ``data/qledger/claims.jsonl`` is APPEND-ONLY: 13 automated commits in 14 days, named
# things like "whitehouse: alert update 2026-08-11T21:04Z". Any field derived from it goes
# stale on its own, with no code change. Pinning such a field by equality in a committed
# artifact is the house's "append-only store pinned by equality is a scheduled red" trap:
# main reds daily for a property no PR author caused, and a guard that reds the fleet for
# nobody's fault gets routed around instead of obeyed.
#
# The FIRST design of this module tried to survive that by comparing a STRUCTURAL
# PROJECTION — the committed file with the volatile paths stripped before comparing. That
# was unsound twice over: (i) the CI-wired test asserted ``--check`` (a byte comparison of
# the WHOLE file) exits 0, so the scheduled red came straight back through the test; and
# (ii) a gate that strips a field before comparing it is BLIND to a hand-edit of that
# field, which is exactly how a tamper of ``validation_state`` — the
# display-only-until-validated axis — became invisible.
#
# So: the committed artifact carries NO corpus-derived field at all. Volatile values are
# computed at READ time by :func:`volatile_view` and never serialised. The committed file
# is therefore identical to its own projection, one byte-exact comparison is sound, and
# the guard ASSERTS the absence of these paths (:func:`assert_no_volatile`) instead of
# stripping them.
#
# THERE IS NO REGENERATION LANE, AND ONE MUST NOT BE ADDED. ``grep -rn
# build_intelligence_registry .github/`` returns nothing; a nightly that rewrote a ~750 KB
# git-tracked JSON would add a push storm to the wire lanes for zero information, and the
# heal would be valid only until the next append. The answer is not to automate the
# regeneration — it is that nothing an automated lane can move lives in the file.

#: Dotted paths that MUST NOT appear in a committed engine row. Not a strip list — an
#: assertion. Each is a pure function of the append-only claim corpus.
VOLATILE_ENGINE_PATHS: tuple[str, ...] = (
    "declared_horizon.horizon_d",
    "ledger_evidence.corpus_rows",
    "ledger_evidence.corpus_checked",
)

#: Top-level ``meta`` keys that must likewise never be committed.
#:
#: ``validation_state`` and ``validation_state_evidence`` were in the volatile set and are
#: NOT any more. ``data/species/registry.json`` has ONE commit in the whole repo history
#: and no automated writer (``engine/species_registry.py::save`` has zero non-test
#: callers), so it moves only via a PR — which makes those two fields STABLE, committed,
#: and equality-guarded. That is the point: a hand-edit of a validity claim is now
#: structural drift, not an invisible write.
VOLATILE_META_KEYS: tuple[str, ...] = ("corpus",)

# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

SEVERITY_INTEGRITY = "integrity"   # law A — hard
SEVERITY_CONTENT = "content"       # law B — warn

FINDING_CODES = (
    # law B (content, warn) — pre-existing conditions of the corpus
    "AUTHORITY_WITHOUT_EVIDENCE",
    "AUTHORITY_EVIDENCE_UNRESOLVABLE",
    "OUTPUT_CLASS_MISSING",
    "GRADED_BY_DESIGN_CONTRADICTS_LEDGER",
    "SCORED_PATH_SURFACES_INCOMPLETE",
    "SPECIES_UNBOUND",
    # computed at READ time from the live corpus (audit_corpus), never from the file
    "LEDGER_DECLARED_BUT_EMPTY",
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
#: given the inputs it needs, so it did not look. It must never be reported as a failure.
QUAL_LADDER_RESOLUTIONS = ("qual_ladder_key", "repo_path", "unresolved", "unchecked")


def resolve_qual_ladder_ref(
    ref: Any,
    *,
    qual_ladder_keys: Iterable[str] | None = None,
    path_exists: Callable[[str], bool] | None = None,
) -> str | None:
    """Resolve one ``qual_ladder_ref`` value. ``None`` means there was no ref at all.

    The live corpus mixes exactly two legal shapes and BOTH are checkable (measured over
    all 10 refs in ``config/synapse.yml``, 2026-08-12): 9 are keys in
    ``config/qual_ladder.yml`` (``altdata.signal_score`` ×4, ``china_intel.news_dir`` ×3,
    ``altdata.action`` ×2) and 1 is a repo path that exists
    (``research/RECLAIM_VETO_CONDITIONAL_PREREG.md``).

    ``path_exists`` is INJECTED so this module stays pure and file-free — and so the
    caller can route the probe through the sparse-worktree git ladder. A bare
    ``os.path.exists`` would go blind on a sparse cone and silently call a real prereg
    missing, reproducing the "could not look rendered as looked and found nothing" bug
    inside the fix for it.

    SCOPE: resolvability is not adequacy. A resolvable pointer does not prove the document
    it names pre-registers anything — that judgment is T7's backlog drain. This guarantees
    only that the pointer is real.
    """
    text = str(ref).strip() if ref is not None else ""
    if not text:
        return None
    if qual_ladder_keys is None or path_exists is None:
        return "unchecked"
    if text in set(qual_ladder_keys):
        return "qual_ladder_key"
    if path_exists(text):
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
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "desk"
                ):
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
    dropped silently — that is the invariant the integrity law checks.
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
          ``meta.tier_vocabulary`` defines ``scored`` as carrying weight. This alone
          catches ``vol-regime-gate`` and ``vol-regime-basket-overlay-gate``.
      (b) ``scored_path_surfaces`` non-empty -> ``user_ranking``. This is the C-2 fix:
          ``site-us-standouts`` declares ``['board_ordering', 'top_setups']`` and
          therefore separates from a decorative display chip.
      (c) ``tier in {shadow, scored, confirmer}`` AND the artifact is consumed by the
          PRODUCER OF a (a)/(b) artifact, exactly one hop -> ``engine_input``.
      (d) else ``display``.

    Every rule is structural — enum membership, list non-emptiness, one graph hop.
    Nothing depends on prose. A keyword-window scan of engine source was rejected as an
    unmeasured detector whose two target artifacts rule (a) already catches definitionally.
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

#: A grading ledger is a STORE. Measured 2026-08-12: without this test, 6-7 of the 112
#: ``graded_by_design: yes`` engines had a "ledger" that could not hold a graded row —
#: three ``engine/*_ledger.py`` SELF-REFERENCES (the ``else producer`` fallback deleted
#: below), a charter CONFIG (``config/lobe_charters.yml``), a rule-4 hop that landed on a
#: ``.py`` module, and two UNEXPANDED template globs. An evaluability claim derived from a
#: filename substring is exactly the unearned claim ``OVERLAY_GRADED_TRANSITION`` refuses
#: to let the overlay write by hand.
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
    ledger_modules: frozenset[str],
    desk_scan: DeskScan | None,
    producer_ledger_index: Mapping[str, str],
) -> dict[str, Any]:
    """Resolve the engine's grading ledger. Waterfall, first hit wins. Never null.

    1. the cell writes a ``*ledger*`` path THAT IS STORE-SHAPED -> that path.
    2. producer statically imports ``engine.qledger`` and a desk literal resolves by AST
       -> ``qledger:<desk>``.
    3. any artifact in the cell is tier shadow/scored/confirmer AND its path is
       store-shaped -> that artifact path (synapse tier_vocabulary defines shadow as
       "computed + claim-registered + graded nightly").
    4. a grader-shaped consumer that is itself the producer of a store-shaped ledger
       artifact, EVEN CROSS-PROGRAM -> that consumer's ledger path. This hop is what
       catches ``us-stocks-prebreakout``, graded by ``scripts/grade_us_board.py`` which
       lives under ``owner_program=setup-species``.
    5. else the literal string ``'none'``, mirroring data/species/registry.json's own
       ``ledger_binding`` convention.

    THE ``else producer`` FALLBACK IS DELETED (2026-08-12). Rule 1 used to read
    ``path = ledger_paths[0] if ledger_paths else producer``, so an ``engine/*_ledger.py``
    module with no ledger-shaped artifact became its OWN ledger and earned
    ``graded_by_design: yes`` — a Python module cannot hold a graded row. Three engines
    were self-referencing that way. A ledger module with no store now falls through to
    rules 3-5 like anything else. ``ledger_modules`` is retained as an INPUT because rule
    1 is still the right home for a module that does write one.

    DEVIATION FROM THE BRIEF, deliberate: the brief made rule 2 conditional on the desk
    having >0 rows in ``data/qledger/claims.jsonl``, demoting a zero-row desk down the
    waterfall. That would (i) make ``ledger`` a function of an APPEND-ONLY store, so a
    nightly lane writing a desk's first row would flip a committed field and red every
    open PR on the byte-drift gate, and (ii) SILENTLY hide the very gap it detected. So
    the desk resolves structurally here and the row count is computed at READ time by
    :func:`volatile_view`, with a zero-row desk raised by :func:`audit_corpus` as
    ``LEDGER_DECLARED_BUT_EMPTY``. That deviation is load-bearing for the whole drift
    design and stays. Its honest measurement (2026-08-12, live corpus): exactly ONE engine
    resolves a desk at all — ``scripts/build_whitehouse.py::whitehouse-desk``, 88 rows —
    and ZERO desks are empty, so the finding fires on nothing today. A zero-firing
    detector over a live corpus is not dead code; it is a tripwire whose condition has not
    occurred. (An earlier version of this docstring cited
    ``engine/basket_turn_cohort.py`` and ``collectors/special_situations.py`` as measured
    firings. Neither module is a synapse producer, so neither can ever be an engine row:
    that citation was fabricated and has been deleted.)
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

    The previous rule was an unanchored bidirectional substring
    (``token in engine_ledger or engine_ledger in token``) — the same fuzzy-matching class
    the overlay comment correctly refuses for DNR-to-engine mapping, applied to the
    validation_state axis. SHRINK-DIRECTION CONTROL: 5 engines bind species today and all
    5 survive this rule; ``tests/test_intelligence_registry.py`` pins that exact set BY
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
    ledger_modules: Iterable[str] = (),
    desk_scans: Mapping[str, DeskScan] | None = None,
    article2_modules: Iterable[str] = (),
    species: Sequence[Mapping[str, Any]] | None = None,
    qual_ladder_keys: Iterable[str] | None = None,
    path_exists: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Build the whole registry. Pure — no file I/O, deterministic, sorted throughout.

    Every field emitted here is STABLE: it moves only when a PR moves ``config/synapse.yml``,
    ``config/qual_ladder.yml``, ``data/species/registry.json``, the producer set, the
    repo's ledger-module inventory, or the overlay. NOTHING derived from the append-only
    claim corpus is emitted — see the volatile-fields block at the top of this module and
    :func:`volatile_view`, which computes those at read time.

    ``species`` may be ``None``, meaning the store was not readable; that renders as
    ``validation_state: None`` ("could not look"), never as ``phase0``. Likewise
    ``qual_ladder_keys`` / ``path_exists`` absent yields resolution ``"unchecked"`` rather
    than ``"unresolved"`` — the builder must not accuse a ref it never probed.
    """
    artifacts: Mapping[str, Any] = synapse.get("artifacts") or {}
    overlay_rows: Mapping[str, Any] = (overlay or {}).get("engines") or {}
    ledger_module_set = frozenset(ledger_modules)
    desk_scans = desk_scans or {}
    article2 = frozenset(article2_modules)
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
        # DERIVED BEFORE ANY EXCLUSION DECISION. The first version hit `continue` here, so
        # nothing ever knew WHAT was being deleted: a 3-character `not_an_engine` reason
        # removed a gate_size engine and both laws stayed green. An exclusion must be
        # self-describing, which means the row has to exist before it can be excluded.
        artifact_rows = []
        for aid in artifact_ids:
            entry = artifacts[aid]
            auth = artifact_authority.get(aid, {"authority": "display", "rule": "d", "surfaces": []})
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
                        ref, qual_ladder_keys=ladder_keys, path_exists=path_exists
                    ),
                    "artifact_authority": auth["authority"],
                }
            )

        # --- authority + evidence -----------------------------------------
        authority = max_authority(r["artifact_authority"] for r in artifact_rows)
        winners = [r for r in artifact_rows if r["artifact_authority"] == authority] or [
            artifact_rows[0]
        ]
        winner_rule = artifact_authority.get(winners[0]["id"], {}).get("rule", "d")

        # Completeness flag — PROPOSES, never promotes. The measured prophet-index case:
        # consumed by an Article-2 enforcer module while declaring no scored_path_surfaces.
        completeness: list[str] = []
        for aid in artifact_ids:
            entry = artifacts[aid]
            if entry.get("scored_path_surfaces"):
                continue
            hits = sorted(set(entry.get("consumers") or []) & article2)
            if hits:
                completeness.append(f"{aid} read by {', '.join(hits)} with no scored_path_surfaces")

        # THE C-1 GATE INPUT, AT THE ARTIFACT LEVEL. `evidence_ref` below keeps its union
        # semantics because a roll-up is useful, but it is NO LONGER what the gate reads:
        # a union clears on ANY sibling's ref, so an unevidenced gate_size artifact went
        # unflagged whenever a decorative `display` sibling carried a pointer. Reproduced
        # live 2026-08-12 on scripts/build_basket_washout_state.py::blocked-entry-override.
        unevidenced = sorted(
            r["id"]
            for r in artifact_rows
            if r["artifact_authority"] != "display"
            and (not r["qual_ladder_ref"] or r["qual_ladder_ref_resolution"] == "unresolved")
        )
        unresolvable = sorted(
            r["id"]
            for r in artifact_rows
            if r["qual_ladder_ref"] and r["qual_ladder_ref_resolution"] == "unresolved"
        )

        authority_evidence = {
            "rule": winner_rule,
            # PLURAL. The singular `artifact_id` named only the first sorted winner, so on
            # the two multi-winner cells the prescribed heal pointed at the wrong artifact
            # — for scripts/build_stock_library.py::us-stocks-prebreakout it named
            # site-signal-gate rather than site-us-standouts, the artifact the entire C-2
            # defect statement is about.
            "artifact_ids": sorted(r["id"] for r in winners),
            "surfaces": sorted({s for r in winners for s in r["scored_path_surfaces"]}),
            "completeness_flag": bool(completeness),
            "completeness_detail": sorted(completeness),
            "unevidenced_artifacts": unevidenced,
            "unresolvable_artifacts": unresolvable,
        }

        # --- ledger -------------------------------------------------------
        scan = desk_scans.get(producer)
        ledger_info = derive_ledger(
            producer=producer,
            artifact_entries=entries,
            ledger_modules=ledger_module_set,
            desk_scan=scan,
            producer_ledger_index=producer_ledger_index,
        )
        ledger = ledger_info["ledger"]
        ledger_evidence = {
            "rule": ledger_info["rule"],
            "desk": ledger_info.get("desk"),
            "via": ledger_info.get("via"),
            "shape": None if ledger == LEDGER_NONE or ledger_info.get("desk") else ledger_shape(ledger),
        }

        # --- graded_by_design ---------------------------------------------
        # A TEMPLATE ledger (`options_structure/structural/<ROOT>.json`) names a family of
        # stores, not a store. It cannot be opened, so it is not evidence that grading
        # happens — it is a gap worth naming, which is what 'no — not yet' says.
        if ledger != LEDGER_NONE and ledger_evidence["shape"] != LEDGER_SHAPE_TEMPLATE:
            graded = GRADED_YES
            graded_source = "derived: has a ledger"
        elif ledger_evidence["shape"] == LEDGER_SHAPE_TEMPLATE:
            graded = GRADED_NOT_YET
            graded_source = (
                "derived: the resolved ledger is an unexpanded template path, not a store "
                "that can be opened"
            )
        elif all(e.get("tier") == "infrastructure" for e in entries):
            graded = GRADED_DESCRIPTIVE
            graded_source = "derived: every artifact is tier=infrastructure (operational rail, not a signal)"
        else:
            graded = GRADED_NOT_YET
            graded_source = "derived: no ledger and not purely infrastructure"
        overlay_graded = (row_overlay.get("graded_by_design") or {}).get("value")
        if overlay_graded and graded == OVERLAY_GRADED_TRANSITION[0]:
            graded = overlay_graded
            graded_source = "curated: " + str((row_overlay.get("graded_by_design") or {}).get("reason") or "")

        # --- output_class --------------------------------------------------
        # `or ledger != LEDGER_NONE` added 2026-08-12. Keying only on authority and tier
        # exempted 26 engines the registry itself marks graded_by_design='yes' — including
        # scripts/build_prophet.py::momoedge (ledger=data/prophet/ledger.jsonl), recorded
        # as "not_required_display_only". An Evaluation OS whose unit of account is the
        # metric contract cannot declare the contract not required for a graded engine.
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
        elif gate_tripped:
            output_class = None
            output_class_reason = "required_but_uncurated"
        else:
            output_class = None
            output_class_reason = "not_required_display_only"

        # --- declared_horizon ---------------------------------------------
        # `horizon_d` is NOT here: it is a function of the append-only claim corpus, so it
        # is computed at read time by volatile_view(). See the volatile block up top.
        roles = sorted({e.get("horizon_role") for e in entries if e.get("horizon_role")})
        declared_horizon = {
            "horizon_role": roles,
            "horizon_role_homogeneous": len(roles) <= 1,
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
        # A roll-up of the RESOLVABLE refs in the cell. Useful to read; deliberately NOT
        # the gate input any more (see authority_evidence.unevidenced_artifacts above).
        refs = sorted(
            {
                str(e["qual_ladder_ref"])
                for e in artifact_rows
                if e["qual_ladder_ref"] and e["qual_ladder_ref_resolution"] != "unresolved"
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
                    # audit_content() still counts these rows, so the C-1/C-2 backlog this
                    # registry exists to produce cannot be deflated by an exclusion.
                    "would_be_authority": authority,
                    "would_be_tiers": sorted({str(r["tier"]) for r in artifact_rows}),
                    "would_be_artifact_authorities": sorted(
                        {r["artifact_authority"] for r in artifact_rows}
                    ),
                    "would_be_ledger": ledger,
                    "would_be_output_class_reason": output_class_reason,
                    "would_be_unevidenced_artifacts": unevidenced,
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
    # dropped in complete silence — nothing in this module, the guard, or the doc named it.
    # Measured 2026-08-12: 2 of 27 species are unbound and BOTH are `accruing`
    # (F3_ANTICHASE, EI-F1D-RW). validation_state is the axis the display-only-until-
    # validated law hangs on, so an unbound accruing species is either an understated
    # engine or an orphaned species — a fact worth naming either way, exactly the argument
    # this module already makes for LEDGER_DECLARED_BUT_EMPTY.
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
            "n_engines": len(engines),
            "n_excluded": len(excluded),
            "n_artifacts": n_artifacts,
            "n_artifacts_mapped": covered,
            # Declared here as an ABSENCE contract: these paths are computed at read time
            # and must never appear in this file. assert_no_volatile() enforces it.
            "volatile_fields_excluded": list(VOLATILE_ENGINE_PATHS),
            "volatile_meta_keys_excluded": list(VOLATILE_META_KEYS),
            "authority_order": list(AUTHORITY_ORDER),
            "unbound_species": unbound,
        },
        "engines": engines,
        "excluded": excluded,
    }


# ---------------------------------------------------------------------------
# The volatile view — computed at READ time, never serialised
# ---------------------------------------------------------------------------

def volatile_view(
    registry: Mapping[str, Any],
    *,
    qledger_desk_rows: Mapping[str, int] | None = None,
    qledger_desk_horizons: Mapping[str, Sequence[int]] | None = None,
) -> dict[str, Any]:
    """Corpus-derived values for a registry, computed FRESH from the live claim corpus.

    This is everything the committed artifact deliberately does not carry. T7/T8 consumers
    call it; the builder prints it; nothing writes it to disk. ``qledger_desk_rows is
    None`` means the corpus could not be read, which renders as ``corpus_checked: False``
    and ``corpus_rows: None`` — "could not look", never "looked and found nothing".
    """
    checked = qledger_desk_rows is not None
    engines: dict[str, dict[str, Any]] = {}
    for row in registry.get("engines") or []:
        desk = (row.get("ledger_evidence") or {}).get("desk")
        if desk is None:
            rows = None
            horizon_d = None
        else:
            rows = None if qledger_desk_rows is None else int(qledger_desk_rows.get(desk, 0))
            horizon_d = (
                None
                if qledger_desk_horizons is None
                else (sorted({int(h) for h in (qledger_desk_horizons.get(desk) or [])}) or None)
            )
        engines[str(row.get("engine_id"))] = {
            "corpus_rows": rows,
            "corpus_checked": checked and desk is not None,
            "horizon_d": horizon_d,
        }
    return {
        "corpus": {
            "qledger_read": checked,
            "n_desks": None if qledger_desk_rows is None else len(qledger_desk_rows),
        },
        "engines": engines,
    }


# ---------------------------------------------------------------------------
# Content audit (law B — warn)
# ---------------------------------------------------------------------------

def audit_content(registry: Mapping[str, Any]) -> list[Finding]:
    """STABLE content findings about the CORPUS, not about the registry's own files.

    Every one of these is a PRE-EXISTING CONDITION no PR author caused, which is why the
    owning house law is warn-tier and only exits non-zero under ``--strict``. Wiring them
    hard on arrival would red main fleet-wide for a property nobody introduced — the
    failure mode ``epistemics.qledger_metric_validity`` documents in its own notes.

    Every finding here is a function of the COMMITTED artifact alone, so the rendered doc
    can carry their counts without becoming a scheduled red. The one corpus-dependent
    finding (``LEDGER_DECLARED_BUT_EMPTY``) lives in :func:`audit_corpus`.
    """
    findings: list[Finding] = []

    # EXCLUDED ROWS ARE AUDITED TOO. `audit_content` used to iterate `engines` only, so a
    # `not_an_engine` overlay row silenced every finding for that cell — the backlog this
    # registry exists to produce could be deflated by a three-word reason string. Belt and
    # braces with the HARD refusal in validate_structure(): even if that were bypassed, an
    # exclusion cannot buy silence.
    for row in registry.get("excluded") or []:
        eid = row.get("engine_id", "?")
        if row.get("would_be_authority") in (None, "display"):
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

        # C-1 — authority without a RESOLVABLE pointer to the prereg that earned it.
        # Gated on the per-ARTIFACT list, not on the cell-wide evidence_ref union: the
        # union clears on any sibling's ref, including a decorative display sibling's.
        if evidence.get("unevidenced_artifacts"):
            findings.append(
                Finding(
                    "AUTHORITY_WITHOUT_EVIDENCE",
                    SEVERITY_CONTENT,
                    eid,
                    f"authority={row.get('authority')} but "
                    f"{len(evidence['unevidenced_artifacts'])} artifact(s) above display "
                    f"carry no resolvable qual_ladder_ref — HEAL: add qual_ladder_ref to "
                    f"config/synapse.yml for "
                    f"{', '.join(evidence['unevidenced_artifacts'])}",
                )
            )

        # "No pointer" and "pointer at nothing" need different heals, so they are
        # different codes. A ref that resolves to neither a config/qual_ladder.yml key nor
        # an existing repo path is not evidence — it is a string.
        if evidence.get("unresolvable_artifacts"):
            findings.append(
                Finding(
                    "AUTHORITY_EVIDENCE_UNRESOLVABLE",
                    SEVERITY_CONTENT,
                    eid,
                    "qual_ladder_ref present but resolves to neither a "
                    "config/qual_ladder.yml key nor an existing repo path: "
                    + "; ".join(
                        f"{a['id']} -> {a.get('qual_ladder_ref')!r}"
                        for a in row.get("artifacts") or []
                        if a.get("id") in set(evidence["unresolvable_artifacts"])
                    ),
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

        # Unreachable in a FRESHLY DERIVED registry by construction (graded_by_design is
        # 'yes' whenever a ledger resolves, and the overlay may only transition
        # 'no — not yet' -> 'no — descriptive', which requires ledger == 'none'). It is
        # reachable — and load-bearing — when this audit runs against the COMMITTED file,
        # which is what the gate does: it catches a stale or hand-edited registry claiming
        # an engine is ungraded while its ledger says otherwise.
        # A TEMPLATE ledger is not a contradiction: `no — not yet` is the CORRECT value
        # for a path that names a family of stores rather than a store, and the derivation
        # says exactly that in graded_by_design_source. Without this exemption the
        # template rule would manufacture its own finding.
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
                    f"ledger={row.get('ledger')!r} — a stale or hand-edited registry row",
                )
            )

        if evidence.get("completeness_flag"):
            findings.append(
                Finding(
                    "SCORED_PATH_SURFACES_INCOMPLETE",
                    SEVERITY_CONTENT,
                    eid,
                    "; ".join(evidence.get("completeness_detail") or []),
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


def audit_corpus(
    registry: Mapping[str, Any], volatile: Mapping[str, Any] | None
) -> list[Finding]:
    """Content findings that require the LIVE claim corpus, computed at read time.

    Split out of :func:`audit_content` on purpose. These values move with an append-only
    store, so anything derived from them must never reach a committed artifact or a
    committed doc — the moment it does, the finding count is pinned by equality and every
    open PR reds on the next nightly append.
    """
    findings: list[Finding] = []
    if not volatile:
        return findings
    per_engine = volatile.get("engines") or {}
    for row in registry.get("engines") or []:
        eid = row.get("engine_id", "?")
        desk = (row.get("ledger_evidence") or {}).get("desk")
        state = per_engine.get(eid) or {}
        if desk and state.get("corpus_checked") and state.get("corpus_rows") == 0:
            findings.append(
                Finding(
                    "LEDGER_DECLARED_BUT_EMPTY",
                    SEVERITY_CONTENT,
                    eid,
                    f"registers qledger desk {desk!r} but the claim corpus holds zero rows "
                    f"for it",
                )
            )
    findings.sort(key=lambda f: (f.code, f.engine_id))
    return findings


# ---------------------------------------------------------------------------
# Integrity validation (law A — hard)
# ---------------------------------------------------------------------------

_REQUIRED_ENGINE_KEYS = frozenset({
    "engine_id", "producer", "owner_program", "owner_program_span", "artifacts",
    "consumers", "output_class", "output_class_reason", "authority",
    "authority_evidence", "ledger", "ledger_evidence", "graded_by_design",
    "graded_by_design_source", "declared_horizon", "validation_state",
    "validation_state_evidence", "evidence_ref",
})

#: An exclusion must SAY WHAT IT DELETES. Without these the excluded rows are opaque and
#: the hard refusal below has nothing to read.
_REQUIRED_EXCLUDED_KEYS = frozenset({
    "engine_id", "producer", "owner_program", "artifacts", "reason", "source",
    "would_be_authority", "would_be_tiers", "would_be_artifact_authorities",
    "would_be_ledger", "would_be_output_class_reason", "would_be_unevidenced_artifacts",
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

    ORPHAN RULE — an overlay row keyed by an engine_id the builder did not generate is a
    HARD error, not a warning. Otherwise the overlay accumulates rows for deleted engines
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
            # ONE predicate, not a chain. The old `elif vs.get('value') not in terminal_ok`
            # branch was DEAD: OVERLAY_TERMINAL_STATES is a subset of
            # VALID_VALIDATION_STATUSES, so the preceding test already rejected everything
            # it could have caught. Intersecting the two keeps the live cross-check — if
            # engine/species_registry.py ever drops 'falsified' or 'retired', the overlay
            # may no longer ratify it — without a branch no test can reach.
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
            # engine with both laws green. It now demands what a terminal ratification
            # demands, plus a reason long enough to be an argument rather than a shrug.
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
    """Validate the registry's own structure. Returns violation strings; empty = clean.

    Properties of the registry FILE only — every one is green by construction on the PR
    that generates it, and none can be tripped by a pre-existing corpus condition. That
    is what makes ``hard`` severity legitimate here: the blast radius is the registry.
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
            # THE OVERLAY IS NOT A DELETION HATCH. This is legitimately HARD: it can only
            # fire on a hand-edit to config/intelligence_registry_overlay.yml, so it is
            # PR-caused by construction, and it ships GREEN (the overlay is `engines: {}`).
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

    violations += assert_no_volatile(registry)

    return violations


# ---------------------------------------------------------------------------
# Serialisation + the structural projection the HARD drift law compares
# ---------------------------------------------------------------------------

def _has_path(obj: Any, dotted: str) -> bool:
    head, _, rest = dotted.partition(".")
    if not isinstance(obj, dict) or head not in obj:
        return False
    return _has_path(obj[head], rest) if rest else True


def assert_no_volatile(registry: Mapping[str, Any]) -> list[str]:
    """Violations for every corpus-derived path present in a COMMITTED registry.

    This replaces the old ``structural_projection()``, which STRIPPED these paths before
    comparing. Stripping was unsound in both directions: it left the byte-equality pin in
    place through the CI-wired ``--check`` test (so the append-only scheduled red survived
    anyway), and it made the guard blind to a hand-edit of any stripped field. Asserting
    the ABSENCE instead means the committed file is identical to its own projection, so
    ONE byte-exact comparison is both sound and complete.
    """
    violations: list[str] = []
    meta = registry.get("meta")
    if isinstance(meta, dict):
        for key in VOLATILE_META_KEYS:
            if key in meta:
                violations.append(
                    f"meta.{key} is corpus-derived and must not be committed — it is "
                    f"computed at read time by volatile_view()"
                )
    for row in registry.get("engines") or []:
        for dotted in VOLATILE_ENGINE_PATHS:
            if _has_path(row, dotted):
                violations.append(
                    f"{row.get('engine_id', '?')}: {dotted} is derived from the "
                    f"APPEND-ONLY claim corpus and must not be committed — pinning it by "
                    f"equality is a scheduled fleet-wide red"
                )
    return violations


def serialise(registry: Mapping[str, Any]) -> str:
    """Deterministic JSON text. Trailing newline so the file is a well-formed text file."""
    return json.dumps(registry, indent=2, ensure_ascii=False) + "\n"
