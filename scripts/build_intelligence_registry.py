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
    build_registry,
    scan_producer_source,
    serialise,
)

REGISTRY_REL = Path("data") / "intelligence_registry.json"
OVERLAY_REL = Path("config") / "intelligence_registry_overlay.yml"
DOC_REL = Path("docs") / "MASTERMIND_INTELLIGENCE_REGISTRY.md"
SYNAPSE_REL = Path("config") / "synapse.yml"
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
    """
    return sorted(p.relative_to(root).as_posix() for p in (root / "engine").glob("*_ledger.py"))


def _scan_producers(root: Path, producers: set[str]) -> tuple[dict[str, DeskScan], list[str]]:
    scans: dict[str, DeskScan] = {}
    unresolved: list[str] = []
    for producer in sorted(producers):
        path = root / producer.split(":")[0].strip()
        if not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scan = scan_producer_source(source)
        if scan.imports_qledger:
            scans[producer] = scan
            if scan.unresolved:
                unresolved.append(producer)
    return scans, unresolved


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
    """Build the registry and a report dict. Pure-ish: reads, does not write."""
    synapse = yaml.safe_load((root / SYNAPSE_REL).read_text(encoding="utf-8"))

    overlay_path = root / OVERLAY_REL
    overlay = (
        yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
        if overlay_path.exists()
        else None
    )

    species, species_source = _load_species(root)
    desk_rows, desk_horizons, qledger_source = _load_qledger(root)

    producers = {
        (entry.get("producer") or "")
        for entry in (synapse.get("artifacts") or {}).values()
        if isinstance(entry, dict)
    }
    desk_scans, unresolved = _scan_producers(root, {p for p in producers if p})

    registry = build_registry(
        synapse=synapse,
        overlay=overlay,
        ledger_modules=_ledger_modules(root),
        desk_scans=desk_scans,
        article2_modules=_article2_modules(),
        species=species,
        qledger_desk_rows=desk_rows,
        qledger_desk_horizons=desk_horizons,
    )

    report = {
        "species_source": species_source,
        "qledger_source": qledger_source,
        "unresolved_desk_producers": sorted(unresolved),
        "n_ledger_modules": len(_ledger_modules(root)),
        "n_desk_scans": len(desk_scans),
    }
    return registry, report


# ---------------------------------------------------------------------------
# Generated documentation
# ---------------------------------------------------------------------------

def render_doc(registry: dict[str, Any], findings: list) -> str:
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
        add("| Engine | Authority | Heal |")
        add("|---|---|---|")
        for finding in c1:
            row = next(r for r in engines if r["engine_id"] == finding.engine_id)
            add(
                f"| `{finding.engine_id}` | `{row['authority']}` | add `qual_ladder_ref` to "
                f"`config/synapse.yml` for `{row['authority_evidence']['artifact_id']}` |"
            )
        add("")
        add(
            "The prescribed heal fills `qual_ladder_ref` in `config/synapse.yml` — it "
            "repairs the canonical source rather than papering over the gap in a side file."
        )
    add("")
    add("## Excluded cells")
    add("")
    if not excluded:
        add("None.")
    else:
        add("| Engine id | Source | Reason |")
        add("|---|---|---|")
        for row in excluded:
            add(f"| `{row['engine_id']}` | {row['source']} | {row['reason']} |")
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
    add("| `graded_by_design` | `ledger` + all-infrastructure test | overlay may make ONE transition |")
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
    add("## Volatile fields and the split drift law")
    add("")
    add(
        "`data/qledger/claims.jsonl` is append-only and `data/species/registry.json` moves "
        "independently of any PR. A byte-equality gate over fields sourced from them would "
        "be a scheduled red — the first nightly row written to a currently-empty desk would "
        "flip a field and red every open PR. So the HARD law "
        "(`governance.intelligence_registry_integrity`) compares the STRUCTURAL PROJECTION "
        "(this file with the volatile paths stripped), and a stale corpus snapshot is a "
        "warn-tier content finding instead."
    )
    add("")
    add("Volatile paths, declared in `meta.volatile_fields` so the projection is self-describing:")
    add("")
    for path in meta["volatile_fields"]:
        add(f"- `{path}`")
    add("")
    corpus = meta["corpus"]
    add(
        f"Corpus read on the last regeneration: species={corpus['species_read']} "
        f"(n={corpus['n_species']}), qledger={corpus['qledger_read']} "
        f"(n_desks={corpus['n_desks']})."
    )
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
    text = serialise(registry)

    corpus = registry["meta"]["corpus"]
    partial = not (corpus["species_read"] and corpus["qledger_read"])

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
        f"  inputs: species={report['species_source']} qledger={report['qledger_source']} "
        f"ledger_modules={report['n_ledger_modules']} qledger_producers={report['n_desk_scans']}",
        flush=True,
    )

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

    if partial:
        for name, ok in (("species", corpus["species_read"]), ("qledger", corpus["qledger_read"])):
            if not ok:
                print(
                    f"::notice title=intelligence-registry::{name} store could not be read "
                    f"— corpus-sourced fields are NULL, not empty",
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
        drift = False
        for path, expected in ((registry_path, text), (doc_path, doc_text)):
            actual = path.read_text(encoding="utf-8") if path.exists() else None
            if actual != expected:
                print(f"DRIFT: {path} differs from regenerated output", flush=True)
                drift = True
        return 1 if drift else 0

    if partial and not args.allow_partial:
        print(
            "REFUSING TO WRITE: a data store could not be read, so corpus-sourced fields "
            "would be null. Writing now would enshrine 'could not look' as 'looked and "
            "found nothing'. Pass --allow-partial to override deliberately.",
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
