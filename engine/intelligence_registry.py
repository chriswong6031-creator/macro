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

WHAT THIS MODULE IS
-------------------
Pure functions over already-loaded objects. It reads no files and writes no files, so it
is cheap to test with synthetic input and cannot be broken by a store-layout change. File
I/O and the sparse-worktree ladder live in ``scripts/build_intelligence_registry.py``; the
CI gate lives in ``scripts/check_intelligence_registry.py``.

Per house epistemics a null never blocks: absent inputs produce ``None`` sentinels that
render as "could not look", never as "looked and found nothing".
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

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

# ---------------------------------------------------------------------------
# Volatile fields — why the drift gate is split in two
# ---------------------------------------------------------------------------

#: Dotted paths inside an engine row whose value is sourced from an APPEND-ONLY or
#: nightly-mutated data store (data/qledger/, data/species/). A byte-equality gate over
#: these is a scheduled red: the moment a nightly lane writes the first row of a desk
#: that currently has none, every open PR goes red for a property nobody introduced
#: (the append-only-store-pinned-by-equality trap). So the HARD drift law compares the
#: STRUCTURAL PROJECTION — this file with these paths stripped — and a stale corpus
#: snapshot is a WARN-tier content finding instead.
VOLATILE_ENGINE_PATHS: tuple[str, ...] = (
    "declared_horizon.horizon_d",
    "ledger_evidence.corpus_rows",
    "ledger_evidence.corpus_checked",
    "validation_state",
    "validation_state_evidence",
)

#: Top-level registry keys that are likewise corpus-sourced.
VOLATILE_META_KEYS: tuple[str, ...] = ("corpus",)

# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

SEVERITY_INTEGRITY = "integrity"   # law A — hard
SEVERITY_CONTENT = "content"       # law B — warn

FINDING_CODES = (
    # law B (content, warn) — pre-existing conditions of the corpus
    "AUTHORITY_WITHOUT_EVIDENCE",
    "OUTPUT_CLASS_MISSING",
    "GRADED_BY_DESIGN_CONTRADICTS_LEDGER",
    "SCORED_PATH_SURFACES_INCOMPLETE",
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


def _cell_ledger_paths(artifact_entries: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted(
        {
            str(e.get("path"))
            for e in artifact_entries
            if e.get("path") and _LEDGER_PATH_RE.search(str(e.get("path")))
        }
    )


def derive_ledger(
    *,
    producer: str,
    artifact_entries: Sequence[Mapping[str, Any]],
    ledger_modules: frozenset[str],
    desk_scan: DeskScan | None,
    producer_ledger_index: Mapping[str, str],
    qledger_desk_rows: Mapping[str, int] | None,
) -> dict[str, Any]:
    """Resolve the engine's grading ledger. Waterfall, first hit wins. Never null.

    1. producer is an ``engine/*_ledger.py`` module, or the cell writes a ``*ledger*``
       path -> that path.
    2. producer statically imports ``engine.qledger`` and a desk literal resolves by AST
       -> ``qledger:<desk>``.
    3. any artifact in the cell is tier shadow/scored/confirmer -> that artifact path
       (synapse tier_vocabulary defines shadow as "computed + claim-registered + graded
       nightly").
    4. a grader-shaped consumer that is itself the producer of a ledger artifact, EVEN
       CROSS-PROGRAM -> that consumer's ledger path. This hop is what catches
       ``us-stocks-prebreakout``, graded by ``scripts/grade_us_board.py`` which lives
       under ``owner_program=setup-species``.
    5. else the literal string ``'none'``, mirroring data/species/registry.json's own
       ``ledger_binding`` convention.

    DEVIATION FROM THE BRIEF, deliberate: the brief made rule 2 conditional on the desk
    having >0 rows in ``data/qledger/claims.jsonl``, demoting a zero-row desk down the
    waterfall. That would (i) make ``ledger`` a function of an append-only store, so a
    nightly lane writing a desk's first row would flip the field and red every open PR
    on the byte-drift gate, and (ii) SILENTLY hide the very gap it detected. Instead the
    desk resolves structurally and the row count is recorded as EVIDENCE, with a
    zero-row desk raised as the ``LEDGER_DECLARED_BUT_EMPTY`` content finding — measured
    live on ``engine/basket_turn_cohort.py`` (desk ``basket_turn``) and
    ``collectors/special_situations.py`` (desk ``extraction_8k``). A registered desk that
    has never been written is a fact worth naming, not one worth burying.
    """
    # Rule 1
    ledger_paths = _cell_ledger_paths(artifact_entries)
    if producer in ledger_modules or ledger_paths:
        path = ledger_paths[0] if ledger_paths else producer
        return {"ledger": path, "rule": 1, "desk": None}

    # Rule 2
    if desk_scan is not None and desk_scan.imports_qledger and desk_scan.desks:
        desk = desk_scan.desks[0]
        rows = None if qledger_desk_rows is None else int(qledger_desk_rows.get(desk, 0))
        return {
            "ledger": f"qledger:{desk}",
            "rule": 2,
            "desk": desk,
            "corpus_rows": rows,
            "corpus_checked": qledger_desk_rows is not None,
        }

    # Rule 3
    graded = sorted(
        {
            str(e.get("path"))
            for e in artifact_entries
            if e.get("tier") in _TIER_EVALUATED and e.get("path")
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
            if token in engine_ledger or engine_ledger in token:
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
    qledger_desk_rows: Mapping[str, int] | None = None,
    qledger_desk_horizons: Mapping[str, Sequence[int]] | None = None,
) -> dict[str, Any]:
    """Build the whole registry. Pure — no file I/O, deterministic, sorted throughout.

    ``species`` / ``qledger_desk_rows`` / ``qledger_desk_horizons`` may be ``None``,
    meaning the store was not readable. That is recorded as a first-class flag; it never
    renders as an empty result.
    """
    artifacts: Mapping[str, Any] = synapse.get("artifacts") or {}
    overlay_rows: Mapping[str, Any] = (overlay or {}).get("engines") or {}
    ledger_module_set = frozenset(ledger_modules)
    desk_scans = desk_scans or {}
    article2 = frozenset(article2_modules)

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
    producer_ledger_index: dict[str, str] = {}
    for eid, artifact_ids in cells.items():
        producer = eid.split(ENGINE_ID_SEP, 1)[0]
        entries = [artifacts[a] for a in artifact_ids]
        paths = _cell_ledger_paths(entries)
        if producer in ledger_module_set or paths:
            producer_ledger_index.setdefault(producer, paths[0] if paths else producer)

    engines: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for eid, artifact_ids in cells.items():
        producer, owner_program = eid.split(ENGINE_ID_SEP, 1)
        entries = [artifacts[a] for a in artifact_ids]
        row_overlay = overlay_rows.get(eid) or {}

        # --- not_an_engine ------------------------------------------------
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
                }
            )
            continue

        # --- artifacts (unit of EVIDENCE) ---------------------------------
        artifact_rows = []
        for aid in artifact_ids:
            entry = artifacts[aid]
            auth = artifact_authority.get(aid, {"authority": "display", "rule": "d", "surfaces": []})
            artifact_rows.append(
                {
                    "id": aid,
                    "path": entry.get("path"),
                    "tier": entry.get("tier"),
                    "horizon_role": entry.get("horizon_role"),
                    "freshness_sla_hours": entry.get("freshness_sla_hours"),
                    "storage": entry.get("storage"),
                    "scored_path_surfaces": sorted(entry.get("scored_path_surfaces") or []),
                    "qual_ladder_ref": entry.get("qual_ladder_ref"),
                    "artifact_authority": auth["authority"],
                }
            )

        # --- authority + evidence -----------------------------------------
        authority = max_authority(r["artifact_authority"] for r in artifact_rows)
        winner = next(
            (r for r in artifact_rows if r["artifact_authority"] == authority),
            artifact_rows[0],
        )
        winner_rule = artifact_authority.get(winner["id"], {}).get("rule", "d")

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

        authority_evidence = {
            "rule": winner_rule,
            "artifact_id": winner["id"],
            "surfaces": winner["scored_path_surfaces"],
            "completeness_flag": bool(completeness),
            "completeness_detail": sorted(completeness),
        }

        # --- ledger -------------------------------------------------------
        scan = desk_scans.get(producer)
        ledger_info = derive_ledger(
            producer=producer,
            artifact_entries=entries,
            ledger_modules=ledger_module_set,
            desk_scan=scan,
            producer_ledger_index=producer_ledger_index,
            qledger_desk_rows=qledger_desk_rows,
        )
        ledger = ledger_info["ledger"]
        ledger_evidence = {
            "rule": ledger_info["rule"],
            "desk": ledger_info.get("desk"),
            "via": ledger_info.get("via"),
            "corpus_rows": ledger_info.get("corpus_rows"),
            "corpus_checked": ledger_info.get("corpus_checked", False),
        }

        # --- graded_by_design ---------------------------------------------
        if ledger != LEDGER_NONE:
            graded = GRADED_YES
            graded_source = "derived: has a ledger"
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
        gate_tripped = authority != "display" or any(
            e.get("tier") in _TIER_EVALUATED for e in entries
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
        roles = sorted({e.get("horizon_role") for e in entries if e.get("horizon_role")})
        desk = ledger_evidence["desk"]
        if qledger_desk_horizons is None or desk is None:
            horizon_d = None
        else:
            horizon_d = sorted({int(h) for h in (qledger_desk_horizons.get(desk) or [])}) or None
        declared_horizon = {
            "horizon_role": roles,
            "horizon_d": horizon_d,
            "horizon_role_homogeneous": len(roles) <= 1,
        }

        # --- validation_state ---------------------------------------------
        binding = bind_species(ledger, species)
        validation_state = binding["validation_state"]
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
        refs = sorted({str(e["qual_ladder_ref"]) for e in artifact_rows if e["qual_ladder_ref"]})
        evidence_ref = refs or None

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

    return {
        "schema": SCHEMA,
        "meta": {
            "unit_of_account": "engine = (producer, owner_program) from config/synapse.yml",
            "engine_id_format": "{producer}::{owner_program}",
            "n_engines": len(engines),
            "n_excluded": len(excluded),
            "n_artifacts": n_artifacts,
            "n_artifacts_mapped": covered,
            "volatile_fields": list(VOLATILE_ENGINE_PATHS),
            "volatile_meta_keys": list(VOLATILE_META_KEYS),
            "authority_order": list(AUTHORITY_ORDER),
            "corpus": {
                "species_read": species is not None,
                "qledger_read": qledger_desk_rows is not None,
                "n_species": None if species is None else len(species),
                "n_desks": None if qledger_desk_rows is None else len(qledger_desk_rows),
            },
        },
        "engines": engines,
        "excluded": excluded,
    }


# ---------------------------------------------------------------------------
# Content audit (law B — warn)
# ---------------------------------------------------------------------------

def audit_content(registry: Mapping[str, Any]) -> list[Finding]:
    """Content findings about the CORPUS, not about the registry's own files.

    Every one of these is a PRE-EXISTING CONDITION no PR author caused, which is why the
    owning house law is warn-tier and only exits non-zero under ``--strict``. Wiring them
    hard on arrival would red main fleet-wide for a property nobody introduced — the
    failure mode ``epistemics.qledger_metric_validity`` documents in its own notes.
    """
    findings: list[Finding] = []
    for row in registry.get("engines") or []:
        eid = row.get("engine_id", "?")

        # C-1 — authority without a pointer to the prereg that earned it.
        if row.get("authority") != "display" and not row.get("evidence_ref"):
            findings.append(
                Finding(
                    "AUTHORITY_WITHOUT_EVIDENCE",
                    SEVERITY_CONTENT,
                    eid,
                    f"authority={row.get('authority')} but evidence_ref is null — "
                    f"HEAL: add qual_ladder_ref to config/synapse.yml for "
                    f"{row.get('authority_evidence', {}).get('artifact_id')}",
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
        if row.get("graded_by_design") in (GRADED_NOT_YET, GRADED_DESCRIPTIVE) and row.get(
            "ledger"
        ) not in (LEDGER_NONE, None):
            findings.append(
                Finding(
                    "GRADED_BY_DESIGN_CONTRADICTS_LEDGER",
                    SEVERITY_CONTENT,
                    eid,
                    f"graded_by_design={row.get('graded_by_design')!r} but "
                    f"ledger={row.get('ledger')!r} — a stale or hand-edited registry row",
                )
            )

        evidence = row.get("authority_evidence") or {}
        if evidence.get("completeness_flag"):
            findings.append(
                Finding(
                    "SCORED_PATH_SURFACES_INCOMPLETE",
                    SEVERITY_CONTENT,
                    eid,
                    "; ".join(evidence.get("completeness_detail") or []),
                )
            )

        ledger_evidence = row.get("ledger_evidence") or {}
        if (
            ledger_evidence.get("corpus_checked")
            and ledger_evidence.get("desk")
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
            if not isinstance(vs, dict) or vs.get("value") not in OVERLAY_TERMINAL_STATES:
                violations.append(
                    f"overlay[{eid}]: validation_state may only ratify "
                    f"{sorted(OVERLAY_TERMINAL_STATES)}"
                )
            elif vs.get("value") not in terminal_ok:
                violations.append(
                    f"overlay[{eid}]: validation_state {vs.get('value')!r} is not a valid "
                    f"species status"
                )
            else:
                for field in ("dnr_key", "ratified_by", "date"):
                    if not str(vs.get(field) or "").strip():
                        violations.append(
                            f"overlay[{eid}]: terminal validation_state requires {field!r}"
                        )
                key = str(vs.get("dnr_key") or "")
                if key and not key.startswith("DNR:"):
                    violations.append(
                        f"overlay[{eid}]: dnr_key {key!r} must be cited as DNR:<KEY> "
                        f"(row numbers shift on every append)"
                    )

        nae = row.get("not_an_engine")
        if nae is not None:
            if not isinstance(nae, dict) or not str(nae.get("reason") or "").strip():
                violations.append(
                    f"overlay[{eid}]: not_an_engine requires a non-empty reason — nothing "
                    f"is ever excluded silently"
                )

    return violations


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


# ---------------------------------------------------------------------------
# Serialisation + the structural projection the HARD drift law compares
# ---------------------------------------------------------------------------

def _strip_path(obj: Any, dotted: str) -> None:
    head, _, rest = dotted.partition(".")
    if not isinstance(obj, dict) or head not in obj:
        return
    if rest:
        _strip_path(obj[head], rest)
    else:
        obj.pop(head, None)


def structural_projection(registry: Mapping[str, Any]) -> dict[str, Any]:
    """The registry with every corpus-sourced (volatile) field stripped.

    This is what the HARD drift law compares. Comparing the FULL file byte-for-byte would
    be a scheduled red: ``data/qledger/claims.jsonl`` is append-only and
    ``data/species/registry.json`` moves independently, so the first nightly row written
    to a currently-empty desk would flip a field and red every open PR for a property
    nobody introduced. The volatile set is declared in ``meta.volatile_fields`` inside the
    artifact itself, so the projection is self-describing and a guard cannot silently
    narrow it.
    """
    clone = json.loads(json.dumps(registry))
    meta = clone.get("meta")
    if isinstance(meta, dict):
        for key in VOLATILE_META_KEYS:
            meta.pop(key, None)
    for row in clone.get("engines") or []:
        for dotted in VOLATILE_ENGINE_PATHS:
            _strip_path(row, dotted)
    return clone


def serialise(registry: Mapping[str, Any]) -> str:
    """Deterministic JSON text. Trailing newline so the file is a well-formed text file."""
    return json.dumps(registry, indent=2, ensure_ascii=False) + "\n"
