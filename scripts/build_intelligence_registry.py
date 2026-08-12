"""scripts/build_intelligence_registry.py — generate the Mastermind engine registry (T1).

Regenerates ``data/intelligence_registry.json`` and ``docs/MASTERMIND_INTELLIGENCE_REGISTRY.md``
from canonical sources. The spine is DERIVED — a hand-authored engine list is the pattern
``DNR:KILL-PARALLEL-KNOWLEDGE-BASE`` forbids — so this script, not a human, owns every
field except the four the overlay may carry. Derivation logic lives in
:mod:`engine.intelligence_registry` (pure functions); this file is the I/O shell.

Inputs
------
  config/synapse.yml                     the artifact census; source of the cell partition
  config/intelligence_registry_overlay.yml  the four-key curated overlay
  engine/*_ledger.py                     the ledger-module inventory (globbed, not listed)
  <producer sources>                     AST-scanned for qledger desk literals
  scripts/check_synapse_reads.py         _ENTRY_ARTICLE2_MODULES, imported not copied
  data/species/registry.json             lifecycle states (SPARSE-TOLERANT)
  data/qledger/claims.jsonl              desk row counts + declared horizons (SPARSE-TOLERANT)

THE SPARSE-WORKTREE LADDER
--------------------------
Agent worktrees here have NO ``data/`` on disk while ~39,900 data paths are tracked in
HEAD. A builder that read only from disk would silently derive ``ledger='none'`` and
``validation_state='phase0'`` for every engine, and the drift gate would then enshrine
that empty registry as correct. So every data read tries the working tree first, then
``git show HEAD:<path>``, and records which succeeded. If BOTH fail the registry records
``corpus.species_read = false`` / ``qledger_read = false`` and this script REFUSES to
write unless ``--allow-partial`` is passed — "could not look" must never render as
"looked and found nothing" (CLAUDE.md §Epistemics).

Usage
-----
  python3 scripts/build_intelligence_registry.py            # regenerate in place
  python3 scripts/build_intelligence_registry.py --check     # exit 1 on drift, write nothing
  python3 scripts/build_intelligence_registry.py --stdout    # print JSON, write nothing
  python3 scripts/build_intelligence_registry.py --proposals PATH  # write review proposals

Proposals are NEVER auto-written into the registry or the overlay. ``output_class``
selects the metric contract, and a wrong metric contract is worse than a null one, so the
derived proposal goes to a review file a human ratifies.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from engine.intelligence_registry import (  # noqa: E402
    DeskScan,
    audit_content,
    audit_corpus,
    build_registry,
    partition_artifacts,
    placeholder_reason,
    scan_producer_source,
    serialise,
    volatile_view,
)

REGISTRY_REL = Path("data") / "intelligence_registry.json"
OVERLAY_REL = Path("config") / "intelligence_registry_overlay.yml"
DOC_REL = Path("docs") / "MASTERMIND_INTELLIGENCE_REGISTRY.md"
SYNAPSE_REL = Path("config") / "synapse.yml"
QUAL_LADDER_REL = Path("config") / "qual_ladder.yml"
SPECIES_REL = Path("data") / "species" / "registry.json"
CLAIMS_REL = Path("data") / "qledger" / "claims.jsonl"


# ---------------------------------------------------------------------------
# Sparse-tolerant reads
# ---------------------------------------------------------------------------

#: In-process read cache. The gate builds the registry TWICE (drift + idempotence) and
#: ``data/qledger/claims.jsonl`` is 45k rows behind a ``git show`` in sparse worktrees;
#: without this the guard pays for it four times. Caching within one invocation is also
#: the correct semantics — a build must be a function of one snapshot of its inputs.
_READ_CACHE: dict[tuple[str, str], tuple[str | None, str]] = {}


def read_tracked(root: Path, rel: Path) -> tuple[str | None, str]:
    """Return (text, source) for a tracked path. source is 'worktree' | 'git' | 'absent'.

    Never raises on absence — the caller decides what an unreadable store means, and it
    must never mean "empty".
    """
    cache_key = (str(root), rel.as_posix())
    if cache_key in _READ_CACHE:
        return _READ_CACHE[cache_key]
    result = _read_tracked_uncached(root, rel)
    _READ_CACHE[cache_key] = result
    return result


def _read_tracked_uncached(root: Path, rel: Path) -> tuple[str | None, str]:
    on_disk = root / rel
    if on_disk.exists():
        try:
            return on_disk.read_text(encoding="utf-8"), "worktree"
        except OSError:
            pass
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{rel.as_posix()}"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout, "git"
    except (OSError, subprocess.SubprocessError):
        pass
    return None, "absent"


def _load_species(root: Path) -> tuple[list[dict] | None, str]:
    text, source = read_tracked(root, SPECIES_REL)
    if text is None:
        return None, source
    try:
        return list(json.loads(text).get("species") or []), source
    except (json.JSONDecodeError, AttributeError):
        return None, "unparseable"


def _load_qledger(root: Path) -> tuple[dict[str, int] | None, dict[str, list[int]] | None, str]:
    """Desk row counts and declared horizons from the claim corpus."""
    text, source = read_tracked(root, CLAIMS_REL)
    if text is None:
        return None, None, source
    rows: Counter[str] = Counter()
    horizons: dict[str, set[int]] = defaultdict(set)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        desk = record.get("desk")
        if not desk:
            continue
        rows[desk] += 1
        horizon = record.get("horizon_d")
        if isinstance(horizon, int):
            horizons[desk].add(horizon)
    return dict(rows), {k: sorted(v) for k, v in horizons.items()}, source


# ---------------------------------------------------------------------------
# Derivation inputs sourced from the repo tree
# ---------------------------------------------------------------------------

def _ledger_modules(root: Path) -> list[str]:
    """The ``engine/*_ledger.py`` inventory — GLOBBED, never listed.

    A hard-coded count rots the moment a ledger module is added or renamed; the brief's
    "26 modules" was already wrong (14 match ``engine/*_ledger.py`` on this tree).

    SPARSE-SAFE: the working-tree glob is unioned with ``git ls-files``, because a sparse
    cone that excludes ``engine/`` would otherwise report the inventory as EMPTY and
    silently change every ledger derivation — "could not look" rendered as "looked and
    found nothing", one directory over from where this module documents the same trap.
    """
    found = {p.relative_to(root).as_posix() for p in (root / "engine").glob("*_ledger.py")}
    try:
        result = subprocess.run(
            ["git", "ls-files", "engine/*_ledger.py"],
            cwd=root, capture_output=True, text=True, check=False,
        )
        if result.returncode == 0:
            found |= {line.strip() for line in result.stdout.splitlines() if line.strip()}
    except (OSError, subprocess.SubprocessError):
        pass
    return sorted(found)


def _scan_producers(
    root: Path, producers: set[str]
) -> tuple[dict[str, DeskScan], list[str], list[str]]:
    """AST-scan every producer for qledger desk literals.

    Returns (scans, unresolved_desk_producers, UNREADABLE_producers).

    Producer source goes through ``read_tracked()`` like every data read. The first
    version read the working tree only and skipped a missing file with a silent
    ``continue``: under a sparse cone that loses ledger-waterfall rule 2 for those
    producers and builds a STRUCTURALLY different registry than CI — which the byte-exact
    drift gate then reports as drift, with no annotation saying a producer could not be
    read. Unreadable producers are now COUNTED and announced.
    """
    scans: dict[str, DeskScan] = {}
    unresolved: list[str] = []
    unreadable: list[str] = []
    for producer in sorted(producers):
        rel = producer.split(":")[0].strip()
        source, origin = read_tracked(root, Path(rel))
        if source is None:
            unreadable.append(producer)
            continue
        scan = scan_producer_source(source)
        if scan.imports_qledger:
            scans[producer] = scan
            if scan.unresolved:
                unresolved.append(producer)
    return scans, unresolved, unreadable


def _qual_ladder_keys(root: Path) -> tuple[set[str] | None, str]:
    """The field keys of ``config/qual_ladder.yml`` — one half of ref resolution."""
    text, source = read_tracked(root, QUAL_LADDER_REL)
    if text is None:
        return None, source
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None, "unparseable"
    return (set(data) if isinstance(data, dict) else set()), source


def _make_path_exists(root: Path):
    """A repo-path probe that goes through the SPARSE LADDER, not through os.path.exists.

    ``data/`` is absent on disk in agent worktrees while tracked in HEAD. A disk-only
    probe would call a real prereg missing and fire AUTHORITY_EVIDENCE_UNRESOLVABLE on it
    — reproducing, inside the fix, the exact bug class the fix exists to close.
    """

    def probe(candidate: str) -> bool:
        text = str(candidate).strip()
        if not text or text.startswith("/") or ".." in text.split("/"):
            return False
        return read_tracked(root, Path(text))[0] is not None

    return probe


def _article2_modules() -> list[str]:
    """Import the Article-2 module table rather than copying it.

    ``_ARTICLE2_MAP`` is already hand-duplicated verbatim in
    ``scripts/check_synapse_reads.py`` and ``scripts/check_research_factory_authority.py``
    and the copies can drift. A third copy here would make the authority derivation's own
    input the parallel-store problem this design exists to avoid, so we import.
    """
    try:
        from scripts.check_synapse_reads import _ENTRY_ARTICLE2_MODULES
    except Exception:  # pragma: no cover - import shape is stable in-repo
        return []
    return sorted(_ENTRY_ARTICLE2_MODULES)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the registry and a report dict. Pure-ish: reads, does not write.

    Every input goes through :func:`read_tracked`. ``config/synapse.yml`` and the overlay
    used to be read with a bare ``read_text`` that RAISES rather than falling back to the
    git ladder — a sparse cone excluding ``config/`` crashed the builder instead of saying
    it could not look.

    The report distinguishes STABLE readability (``stable_complete``) from corpus
    readability. Only the former can invalidate a write: the committed artifact carries no
    corpus-derived field, so an unreadable ``data/qledger/`` is a ::notice, not a refusal.
    """
    synapse_text, synapse_source = read_tracked(root, SYNAPSE_REL)
    if synapse_text is None:
        raise SystemExit(
            f"FATAL: {SYNAPSE_REL} is readable from neither the worktree nor HEAD — "
            f"there is nothing to derive from."
        )
    synapse = yaml.safe_load(synapse_text)

    overlay_text, overlay_source = read_tracked(root, OVERLAY_REL)
    overlay = yaml.safe_load(overlay_text) if overlay_text is not None else None

    species, species_source = _load_species(root)
    desk_rows, desk_horizons, qledger_source = _load_qledger(root)
    ladder_keys, ladder_source = _qual_ladder_keys(root)

    producers = {
        (entry.get("producer") or "")
        for entry in (synapse.get("artifacts") or {}).values()
        if isinstance(entry, dict)
    }
    # Placeholder tokens (`<MANUAL>`, `<HAND_MAINTAINED>`, …) are not repo modules — they
    # are already excluded cells. Counting them "unreadable" would make every checkout
    # partial and refuse every write.
    scannable = {p for p in producers if p and placeholder_reason(p) is None}
    desk_scans, unresolved, unreadable = _scan_producers(root, scannable)

    registry = build_registry(
        synapse=synapse,
        overlay=overlay,
        ledger_modules=_ledger_modules(root),
        desk_scans=desk_scans,
        article2_modules=_article2_modules(),
        species=species,
        qual_ladder_keys=ladder_keys,
        path_exists=None if ladder_keys is None else _make_path_exists(root),
    )

    report = {
        "synapse_source": synapse_source,
        "overlay_source": overlay_source,
        "species_source": species_source,
        "qledger_source": qledger_source,
        "qual_ladder_source": ladder_source,
        "unresolved_desk_producers": sorted(unresolved),
        "unreadable_producers": sorted(unreadable),
        "n_ledger_modules": len(_ledger_modules(root)),
        "n_desk_scans": len(desk_scans),
        # The cell set BEFORE any exclusion. The overlay's orphan rule validates against
        # this, not against the committed registry's own ids — otherwise a `not_an_engine`
        # row creates the excluded row that proves it is not an orphan.
        "cell_ids": sorted(partition_artifacts(synapse)),
        # STABLE inputs only. species is stable (data/species/registry.json has ONE commit
        # in the repo's history and no automated writer); qledger is NOT an input to the
        # committed artifact at all any more.
        "stable_complete": species is not None and ladder_keys is not None and not unreadable,
        "qledger_read": desk_rows is not None,
        "qledger_desk_rows": desk_rows,
        "qledger_desk_horizons": desk_horizons,
    }
    return registry, report


# ---------------------------------------------------------------------------
# Generated documentation
# ---------------------------------------------------------------------------

def render_doc(registry: dict[str, Any], findings: list) -> str:
    """Render the generated doc.

    CONTRACT: every value here is a pure function of ``registry`` (stable) and of
    ``audit_content`` (stable). NOTHING corpus-derived may enter this text. The doc is
    pinned BYTE-FOR-BYTE by the HARD law, so one corpus-sourced number in it re-creates
    the append-only scheduled red the artifact was cleaned up to remove — which is exactly
    what the deleted line
    ``Corpus read on the last regeneration: species=... (n=27), qledger=... (n_desks=13)``
    did. ``tests/test_intelligence_registry.py`` mutation-tests this: rendering against a
    mutated volatile view must produce byte-identical text.
    """
    meta = registry["meta"]
    engines = registry["engines"]
    excluded = registry["excluded"]

    by_authority = Counter(r["authority"] for r in engines)
    by_graded = Counter(r["graded_by_design"] for r in engines)
    by_validation = Counter(str(r["validation_state"]) for r in engines)
    by_ledger_rule = Counter(r["ledger_evidence"]["rule"] for r in engines)
    by_finding = Counter(f.code for f in findings)

    lines: list[str] = []
    add = lines.append
    add("# Mastermind Intelligence Registry")
    add("")
    add(
        "> GENERATED — do not edit. Regenerate with "
        "`python3 scripts/build_intelligence_registry.py`."
    )
    add(
        "> Source of record: `data/intelligence_registry.json`. Curated overlay: "
        "`config/intelligence_registry_overlay.yml`."
    )
    add("")
    add(
        "One row per intelligence **engine** — the unit of account the Evaluation OS "
        "scorecard (T7), the CEO view (T8) and tier routing (T12) all hang on."
    )
    add("")
    add("## Unit of account")
    add("")
    add(f"`{meta['unit_of_account']}`, id `{meta['engine_id_format']}`.")
    add("")
    add(
        f"**{meta['n_engines']} engines** over **{meta['n_artifacts']} synapse artifacts** "
        f"({meta['n_excluded']} cells excluded as `not_an_engine`). The partition is total "
        f"and disjoint: every artifact belongs to exactly one engine, which is the "
        f"invariant `scripts/check_intelligence_registry.py` enforces."
    )
    add("")
    add("### What this unit gets wrong")
    add("")
    mixed_tier = sum(
        1 for r in engines if len({a["tier"] for a in r["artifacts"]}) > 1
    )
    singletons = sum(1 for r in engines if len(r["artifacts"]) == 1)
    add(
        f"1. **{mixed_tier} of {meta['n_engines']} engines mix artifact tiers**, so the "
        f"engine-level `authority` roll-up (a MAX) OVERSTATES authority for the low-tier "
        f"siblings inside those cells. Understatement is the dangerous direction — C-2 is "
        f"an understatement defect — but this is a real inaccuracy. **A consumer acting "
        f"per-artifact must read `artifacts[].artifact_authority`, never the engine "
        f"roll-up.**"
    )
    add(
        f"2. **{singletons} of {meta['n_engines']} engines are singletons.** For those rows "
        f"\"engine\" is really \"artifact\"; the registry is artifact-shaped at the tail."
    )
    add(
        "3. **It does not answer \"which code do I fix\".** A producer spanning several "
        "programs yields several engines, so a code-level regression in one file surfaces "
        "as several independent rows. `owner_program_span` makes those visible."
    )
    add("")
    add("## Distributions")
    add("")
    add("| Dimension | Value | Engines |")
    add("|---|---|---|")
    for value, count in sorted(by_authority.items(), key=lambda kv: -kv[1]):
        add(f"| authority | `{value}` | {count} |")
    for value, count in sorted(by_graded.items(), key=lambda kv: -kv[1]):
        add(f"| graded_by_design | {value} | {count} |")
    for value, count in sorted(by_validation.items(), key=lambda kv: -kv[1]):
        add(f"| validation_state | `{value}` | {count} |")
    for value, count in sorted(by_ledger_rule.items()):
        add(f"| ledger waterfall rule | {value} | {count} |")
    add("")
    add("## Content findings (law `epistemics.engine_authority_evidence`, warn-tier)")
    add("")
    if not findings:
        add("None.")
    else:
        add("| Code | Engines |")
        add("|---|---|")
        for code, count in sorted(by_finding.items()):
            add(f"| `{code}` | {count} |")
    add("")
    add(
        "These are PRE-EXISTING CONDITIONS of the corpus, not regressions any PR author "
        "caused. That is why the owning law is warn-tier and exits non-zero only under "
        "`--strict`."
    )
    add("")
    add("### C-1 — authority above `display` with no evidence pointer")
    add("")
    c1 = [f for f in findings if f.code == "AUTHORITY_WITHOUT_EVIDENCE"]
    if not c1:
        add("None — every engine above `display` authority carries an `evidence_ref`.")
    else:
        add("| Engine | Authority | Unevidenced artifacts | Heal |")
        add("|---|---|---|---|")
        by_id = {r["engine_id"]: r for r in engines}
        for finding in c1:
            row = by_id.get(finding.engine_id)
            if row is None:  # an EXCLUDED cell that would have held authority
                excl = next(r for r in excluded if r["engine_id"] == finding.engine_id)
                names = ", ".join(f"`{a}`" for a in excl["would_be_unevidenced_artifacts"])
                add(
                    f"| `{finding.engine_id}` (EXCLUDED) | `{excl['would_be_authority']}` | "
                    f"{names} | add `qual_ladder_ref` to `config/synapse.yml` |"
                )
                continue
            names = ", ".join(
                f"`{a}`" for a in row["authority_evidence"]["unevidenced_artifacts"]
            )
            add(
                f"| `{finding.engine_id}` | `{row['authority']}` | {names} | add "
                f"`qual_ladder_ref` to `config/synapse.yml` for each |"
            )
        add("")
        add(
            "The prescribed heal fills `qual_ladder_ref` in `config/synapse.yml` — it "
            "repairs the canonical source rather than papering over the gap in a side file. "
            "The finding is gated on the PER-ARTIFACT list, never on the cell-wide "
            "`evidence_ref` union: a union clears on any sibling's pointer, including a "
            "decorative `display` sibling's, so healing one artifact would close a finding "
            "while an authority-bearing sibling stayed bare."
        )
    add("")
    add("## Excluded cells")
    add("")
    if not excluded:
        add("None.")
    else:
        add("| Engine id | Source | Would-be authority | Reason |")
        add("|---|---|---|---|")
        for row in excluded:
            add(
                f"| `{row['engine_id']}` | {row['source']} | "
                f"`{row['would_be_authority']}` | {row['reason']} |"
            )
        add("")
        add(
            "An exclusion is DERIVED FIRST and excluded second, so it records what it "
            "deletes. A **curated** exclusion whose `would_be_authority` is above "
            "`display`, or whose cell holds a `scored`/`confirmer`/`shadow` artifact, is a "
            "HARD violation — the overlay is not a deletion hatch. Excluded rows are also "
            "still audited for content findings, so an exclusion cannot deflate the "
            "backlog."
        )
    add("")
    add("## Engines above `display` authority")
    add("")
    add("| Engine | Authority | Rule | Ledger | Graded by design | Evidence |")
    add("|---|---|---|---|---|---|")
    for row in engines:
        if row["authority"] == "display":
            continue
        refs = ", ".join(row["evidence_ref"]) if row["evidence_ref"] else "**null**"
        add(
            f"| `{row['engine_id']}` | `{row['authority']}` | "
            f"{row['authority_evidence']['rule']} | `{row['ledger']}` | "
            f"{row['graded_by_design']} | {refs} |"
        )
    add("")
    add("## Field provenance")
    add("")
    add("| Field | Derived from | Curated? |")
    add("|---|---|---|")
    add("| `engine_id`, `producer`, `owner_program`, `owner_program_span` | `config/synapse.yml` cell key | no |")
    add("| `artifacts`, `consumers` | `config/synapse.yml` | no |")
    add("| `authority`, `authority_evidence` | `tier` + `scored_path_surfaces` + one consumer hop | no |")
    add("| `evidence_ref` | `qual_ladder_ref` | no |")
    add("| `ledger`, `ledger_evidence` | ledger-module glob, AST desk scan, tier, consumer hop | no |")
    add("| `declared_horizon` | `horizon_role` + qledger `horizon_d` | no |")
    add("| `graded_by_design` | a STORE-shaped `ledger` + all-infrastructure test | overlay may make ONE transition |")
    add("| `validation_state` | `data/species/registry.json` | overlay may ratify terminal states only |")
    add("| `output_class` | — (no canonical source encodes it) | yes, required only when the evaluation gate trips |")
    add("| `not_an_engine` | placeholder/frozen producers | yes, for judgment exclusions |")
    add("")
    add(
        "`authority` and `evidence_ref` are deliberately NOT curated. "
        "`_REQUIRED_ARTIFACT_KEYS` (`engine/neuralweb/synapse.py:52`) is a required-key "
        "set, not an exact-key set, so a hand-typed `authority:` key in `synapse.yml` "
        "would land as unenforced free text next to the already-unenforced "
        "`scored_path_surfaces` — reproducing the exact defect class C-1 and C-2 are "
        "instances of, one field later."
    )
    add("")
    add("## Why this file carries no corpus-derived value")
    add("")
    add(
        "`data/qledger/claims.jsonl` is APPEND-ONLY — 13 automated commits in 14 days. Any "
        "field derived from it goes stale on its own, with no code change. Pinning such a "
        "field by equality in a committed artifact is a SCHEDULED fleet-wide red: main "
        "reds daily for a property no PR author caused, and a guard that reds the fleet "
        "for nobody's fault gets routed around instead of obeyed."
    )
    add("")
    add(
        "So the committed artifact carries **none** of them. These paths are computed at "
        "READ time by `engine.intelligence_registry.volatile_view()` and are never "
        "serialised — `assert_no_volatile()` makes their absence a HARD violation:"
    )
    add("")
    for path in meta["volatile_fields_excluded"]:
        add(f"- `{path}`")
    for key in meta["volatile_meta_keys_excluded"]:
        add(f"- `meta.{key}`")
    add("")
    add(
        "Everything that remains moves only when a PR moves it: `config/synapse.yml`, "
        "`config/qual_ladder.yml`, `data/species/registry.json` (ONE commit in the repo's "
        "history, no automated writer), the producer set, the `engine/*_ledger.py` "
        "inventory, or the overlay. That is what makes ONE byte-exact comparison both "
        "sound and complete, and what makes `hard` severity legitimate: every heal is a "
        "single command on the PR that caused it."
    )
    add("")
    add(
        "There is deliberately **no nightly regeneration lane**, and one must not be added. "
        "A nightly rewrite of a git-tracked JSON this size would push a storm into the wire "
        "lanes for zero information, and the heal would be valid only until the next "
        "append. The fix is that nothing an automated lane can move lives in the file."
    )
    add("")
    if meta.get("unbound_species") is None:
        add(
            "`meta.unbound_species` is **null** — the species store could not be read. "
            "That is \"could not look\", not \"looked and found nothing\"."
        )
    elif not meta["unbound_species"]:
        add("Every registered species binds to at least one engine ledger.")
    else:
        add(
            "**Unbound species** — a species whose `ledger_binding` matches no engine "
            "ledger. Either an engine's `validation_state` is understated, or the species "
            "is orphaned; both are worth naming."
        )
        add("")
        add("| Species | validation_status |")
        add("|---|---|")
        for row in meta["unbound_species"]:
            add(f"| `{row['species_id']}` | `{row['validation_status']}` |")
    add("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Proposals (review only — never auto-written)
# ---------------------------------------------------------------------------

def derive_proposals(registry: dict[str, Any], desk_directions: dict[str, Counter]) -> list[dict]:
    """A CURATION WORKSHEET for every gate-tripping engine with no output_class.

    Two rules can propose a class honestly, and only two:
      * a resolved qledger desk whose claims are majority ``direction == 0`` is
        ``salience``, otherwise ``predictive`` (the direction profile IS the class);
      * an all-infrastructure cell is ``descriptive`` (synapse's own tier_vocabulary
        calls infrastructure an operational rail, not a signal).

    MEASURED 2026-08-12: those two rules cover **0 of the 88** engines that need a class —
    only one engine in the whole registry resolves a qledger desk, and no gate-tripping
    cell is all-infrastructure. So this file is mostly a worksheet, not an oracle, and it
    says so per row rather than emitting a confident null.

    Nothing else is guessed. `horizon_role` is the obvious-looking third rule and it is
    REFUTED: vector-calibration is `horizon_role=context` AND `tier=scored` AND validated,
    so context does not imply descriptive. output_class selects the metric contract, and a
    wrong metric contract is worse than a null one — so the worksheet carries the EVIDENCE
    a human needs (tiers, authority, ledger, horizons, artifact paths) instead of a
    fabricated answer. Proposals are NEVER written into the registry or the overlay.
    """
    proposals: list[dict] = []
    for row in registry["engines"]:
        if row["output_class_reason"] != "required_but_uncurated":
            continue
        desk = row["ledger_evidence"].get("desk")
        tiers = sorted({a["tier"] for a in row["artifacts"]})
        if desk and desk in desk_directions:
            counts = desk_directions[desk]
            proposal = "salience" if counts[0] >= sum(counts.values()) / 2 else "predictive"
            basis = f"qledger desk {desk!r} direction profile {dict(counts)}"
        elif tiers == ["infrastructure"]:
            proposal, basis = "descriptive", "every artifact is tier=infrastructure"
        else:
            proposal = None
            basis = (
                "NO DERIVABLE BASIS — needs human judgment. Neither derivation applies: "
                f"no qledger desk resolved (ledger rule {row['ledger_evidence']['rule']}) "
                f"and the cell is not all-infrastructure (tiers={tiers})."
            )
        proposals.append(
            {
                "engine_id": row["engine_id"],
                "proposed_output_class": proposal,
                "basis": basis,
                # Evidence for the curator — this is the point of the file when the
                # derivations cannot answer.
                "authority": row["authority"],
                "tiers": tiers,
                "ledger": row["ledger"],
                "declared_horizon": row["declared_horizon"],
                "evidence_ref": row["evidence_ref"],
                "artifacts": [
                    {"id": a["id"], "path": a["path"], "tier": a["tier"]}
                    for a in row["artifacts"]
                ],
            }
        )
    return proposals


def _desk_directions(root: Path) -> dict[str, Counter]:
    text, _ = read_tracked(root, CLAIMS_REL)
    if text is None:
        return {}
    out: dict[str, Counter] = defaultdict(Counter)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        desk = record.get("desk")
        if desk:
            out[desk][record.get("direction")] += 1
    return dict(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true", help="exit 1 on drift; write nothing")
    parser.add_argument("--stdout", action="store_true", help="print the JSON; write nothing")
    parser.add_argument("--proposals", type=Path, help="write output_class proposals here")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="write even when a data store could not be read (records the gap)",
    )
    args = parser.parse_args()
    root: Path = args.root

    registry, report = build(root)
    findings = audit_content(registry)
    volatile = volatile_view(
        registry,
        qledger_desk_rows=report["qledger_desk_rows"],
        qledger_desk_horizons=report["qledger_desk_horizons"],
    )
    corpus_findings = audit_corpus(registry, volatile)
    text = serialise(registry)

    # Only the STABLE inputs can invalidate a write. The committed artifact carries no
    # corpus-derived field, so an unreadable data/qledger/ costs a ::notice, not a refusal.
    partial = not report["stable_complete"]

    if args.stdout:
        print(text, end="")
        return 0

    # ---- report (stdout, always) -------------------------------------------
    meta = registry["meta"]
    print(
        f"intelligence registry: {meta['n_engines']} engines over {meta['n_artifacts']} "
        f"synapse artifacts ({meta['n_artifacts_mapped']} mapped, "
        f"{meta['n_excluded']} cells excluded)",
        flush=True,
    )
    print(
        f"  inputs: synapse={report['synapse_source']} overlay={report['overlay_source']} "
        f"species={report['species_source']} qledger={report['qledger_source']} "
        f"qual_ladder={report['qual_ladder_source']} "
        f"ledger_modules={report['n_ledger_modules']} qledger_producers={report['n_desk_scans']}",
        flush=True,
    )

    # THE VOLATILE VIEW — computed here, printed here, written NOWHERE. This is the
    # information the committed artifact deliberately does not carry.
    graded_desks = {
        eid: state for eid, state in volatile["engines"].items() if state["corpus_checked"]
    }
    print(
        f"  volatile view (READ TIME, never committed): qledger_read="
        f"{volatile['corpus']['qledger_read']} n_desks={volatile['corpus']['n_desks']} "
        f"engines_with_a_resolved_desk={len(graded_desks)}",
        flush=True,
    )
    for eid, state in sorted(graded_desks.items()):
        print(
            f"    {eid}: corpus_rows={state['corpus_rows']} horizon_d={state['horizon_d']}",
            flush=True,
        )
    for finding in corpus_findings:
        print(f"  [{finding.code}] {finding.engine_id}: {finding.detail}", flush=True)

    print("  excluded (machine-readable, no silent drops):", flush=True)
    reasons = Counter(r["reason"] for r in registry["excluded"])
    for reason, count in sorted(reasons.items()):
        print(f"    {count:>3}  {reason}", flush=True)

    authority_counts = Counter(r["authority"] for r in registry["engines"])
    print(f"  authority: {dict(sorted(authority_counts.items()))}", flush=True)
    graded_counts = Counter(r["graded_by_design"] for r in registry["engines"])
    print(f"  graded_by_design: {dict(sorted(graded_counts.items()))}", flush=True)

    missing_evidence = [f for f in findings if f.code == "AUTHORITY_WITHOUT_EVIDENCE"]
    print(f"  MISSING EVIDENCE REPORT (C-1) — {len(missing_evidence)} engine(s):", flush=True)
    for finding in missing_evidence:
        print(f"    {finding.engine_id}: {finding.detail}", flush=True)

    other = Counter(f.code for f in findings if f.code != "AUTHORITY_WITHOUT_EVIDENCE")
    for code, count in sorted(other.items()):
        print(f"  {code}: {count}", flush=True)

    if report["unresolved_desk_producers"]:
        # Silent under-attribution, not an error — counted rather than invisible.
        print(
            f"::notice title=intelligence-registry::{len(report['unresolved_desk_producers'])} "
            f"producer(s) import engine.qledger but their desk literal did not resolve by "
            f"AST: {', '.join(report['unresolved_desk_producers'])}",
            flush=True,
        )

    if report["unreadable_producers"]:
        # Bare print, line-start, flushed — CLAUDE.md §"GitHub annotations must START the
        # line". Silent-skip here would manufacture a false structural drift with nothing
        # in the log explaining it.
        print(
            f"::notice title=intelligence-registry::{len(report['unreadable_producers'])} "
            f"producer(s) readable from NEITHER the worktree nor HEAD, so their desk scan "
            f"was skipped — this is 'could not look', not 'no desk': "
            f"{', '.join(report['unreadable_producers'])}",
            flush=True,
        )

    for name, ok in (
        ("species", report["species_source"] not in ("absent", "unparseable")),
        ("config/qual_ladder.yml", report["qual_ladder_source"] not in ("absent", "unparseable")),
    ):
        if not ok:
            print(
                f"::notice title=intelligence-registry::{name} could not be read — the "
                f"fields it feeds are NULL, not empty",
                flush=True,
            )
    if not report["qledger_read"]:
        print(
            "::notice title=intelligence-registry::the claim corpus could not be read — "
            "the READ-TIME volatile view is null, not empty (the committed artifact is "
            "unaffected: it carries no corpus-derived field)",
            flush=True,
        )

    if args.proposals:
        proposals = derive_proposals(registry, _desk_directions(root))
        args.proposals.parent.mkdir(parents=True, exist_ok=True)
        args.proposals.write_text(json.dumps(proposals, indent=2) + "\n", encoding="utf-8")
        print(f"  proposals written: {len(proposals)} -> {args.proposals}", flush=True)

    # ---- write / check ------------------------------------------------------
    registry_path = root / REGISTRY_REL
    doc_path = root / DOC_REL
    doc_text = render_doc(registry, findings)

    if args.check:
        if partial:
            # A comparison against a registry we could not fully derive is not a clean
            # result, it is no result. Reporting drift here would be a false red; reporting
            # green would be "looked and it was clean" when we never looked.
            print(
                "::notice title=intelligence-registry::a STABLE input could not be read, "
                "so --check compared nothing — this is 'could not look', not 'no drift'",
                flush=True,
            )
            return 0
        drift = False
        for path, expected in ((registry_path, text), (doc_path, doc_text)):
            actual = path.read_text(encoding="utf-8") if path.exists() else None
            if actual != expected:
                print(f"DRIFT: {path} differs from regenerated output", flush=True)
                drift = True
        return 1 if drift else 0

    if partial and not args.allow_partial:
        print(
            "REFUSING TO WRITE: a STABLE input (config/synapse.yml, config/qual_ladder.yml, "
            "data/species/registry.json, or a producer source file) could not be read, so "
            "committed fields would be null. Writing now would enshrine 'could not look' "
            "as 'looked and found nothing'. Pass --allow-partial to override deliberately.",
            flush=True,
        )
        return 2

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(text, encoding="utf-8")
    doc_path.write_text(doc_text, encoding="utf-8")
    print(f"  wrote {registry_path} and {doc_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
