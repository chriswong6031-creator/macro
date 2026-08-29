"""scripts/build_intelligence_registry.py — derive the Mastermind engine registry (T1).

THE REGISTRY IS A DERIVED ON-DEMAND VIEW. NOTHING HERE IS COMMITTED.
--------------------------------------------------------------------
This script writes no files. It builds the registry in memory from canonical sources and
prints it — a human report by default, the whole view as JSON under ``--json``. Consumers
(T7's scorecard, T8's CEO view, T12's tier routing) either import
:func:`build` / :func:`engine.intelligence_registry.build_registry` and hold the view in
memory, or read the JSON off stdout.

Two earlier rounds committed a generated ``data/intelligence_registry.json`` plus a
generated Markdown mirror and pinned them by equality. Both pins were scheduled fleet-wide
reds, because THERE IS NO STABLE INPUT TO PIN AGAINST on this repo. Measured on FULL
HISTORY 2026-08-14 (unshallowed clone, 11,971 commits reachable — the earlier 26/13 figures
were shallow-clone artifacts and understated the churn by 2.7x and 5.4x):

  ``config/synapse.yml``          69 commits in the trailing 14 days
  ``data/qledger/claims.jsonl``   70 commits in the trailing 14 days (append-only)
  ``data/species/registry.json``   1 commit in the trailing 14 days, 17 in its whole
                                   history, every one an adjudication PR

With no committed artifact there is no drift, no ``--check`` mode, no stale doc and no
stable-vs-volatile field split — the split existed only to make a pin safe.

TWO PLANES, TWO JURISDICTIONS (ruling 2026-08-14)
-------------------------------------------------
The churn figures above are not only an argument against pinning; they are the ownership
map. Six of this program's seven inputs move ONLY through a pull request — ``synapse.yml``,
the overlay, ``qual_ladder.yml``, the Article-2 module table, producer SOURCE, and
``data/species/registry.json`` (17 commits ever, all adjudication PRs, last #4358 on
2026-08-03). Exactly ONE is advanced by an automated lane: ``data/qledger/claims.jsonl``.

:data:`DATA_PLANE_INPUTS` is that distinction as data rather than as scattered
conditionals, and ``report['unreadable_by_plane']`` carries it to the caller, which decides
what each plane is allowed to red. See ``scripts/check_intelligence_registry.py`` §FAIL
CLOSED for the exit policy that consumes it.

Inputs (each may be unreadable; each unreadable one is NAMED, never silently defaulted)
--------------------------------------------------------------------------------------
  config/synapse.yml                     the artifact census; source of the cell partition
  config/intelligence_registry_overlay.yml  the four-key curated overlay
  <producer sources>                     AST-scanned for qledger desk literals
  scripts/check_synapse_reads.py         _ENTRY_ARTICLE2_MODULES, imported not copied
  config/qual_ladder.yml                 one half of qual_ladder_ref resolution
  data/species/registry.json             lifecycle states (SPARSE-TOLERANT)
  data/qledger/claims.jsonl              desk row counts + declared horizons (SPARSE-TOLERANT)

"Unreadable" includes PARTIAL: a store that opens but whose lines do not all parse is
partially blind, and the count lands in ``unreadable_inputs`` beside the wholly-absent
inputs. The rows that DID parse stay in the view — under the null law the incompleteness
must be REPRESENTED, not made to disappear along with the readable half. A document that
reads but does not PARSE (synapse, overlay, qual_ladder) is the same state as one that
could not be read: it is named, never defaulted, and never a traceback.

THE SPARSE-WORKTREE LADDER
--------------------------
Agent worktrees here have NO ``data/`` on disk while ~39,900 data paths are tracked in
HEAD. A builder that read only from disk would silently derive ``ledger='none'`` and
``validation_state='phase0'`` for every engine. So every read tries the working tree first,
then ``git show HEAD:<path>``, and records which succeeded. Whatever cannot be read lands
in ``report['unreadable_inputs']`` and the gate says so on its summary line — "I could not
look" must never render as "I looked and it was clean" (CLAUDE.md §Epistemics).

Usage
-----
  python3 scripts/build_intelligence_registry.py           # human report on stdout
  python3 scripts/build_intelligence_registry.py --json    # the whole view as JSON
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from engine.intelligence_registry import (  # noqa: E402
    DeskScan,
    audit_content,
    build_registry,
    partition_artifacts,
    placeholder_reason,
    scan_producer_source,
    serialise,
)

OVERLAY_REL = Path("config") / "intelligence_registry_overlay.yml"
SYNAPSE_REL = Path("config") / "synapse.yml"
QUAL_LADDER_REL = Path("config") / "qual_ladder.yml"
SPECIES_REL = Path("data") / "species" / "registry.json"
CLAIMS_REL = Path("data") / "qledger" / "claims.jsonl"

ARTICLE2_INPUT = "scripts/check_synapse_reads.py::_ENTRY_ARTICLE2_MODULES"

#: THE ONLY INPUT AN AUTOMATED LANE ADVANCES. Everything else this program reads moves
#: exclusively through a pull request, so a PR-lane gate may hold a PR author responsible
#: for it. ``data/qledger/claims.jsonl`` is appended by the nightly (70 commits in the 14
#: days to 2026-08-14, full history) and no PR author touches it, so its corruption is
#: REPORTED on every run and GATED only in the strict lane — see the exit policy in
#: ``scripts/check_intelligence_registry.py``. Membership is by the entry's leading path,
#: because a partial-blindness entry carries a count suffix.
DATA_PLANE_INPUTS = frozenset({str(CLAIMS_REL)})

#: Every input this program names, for the jurisdiction test: each must be classified.
ALL_NAMED_INPUTS = frozenset({
    str(SYNAPSE_REL), str(OVERLAY_REL), str(QUAL_LADDER_REL), str(SPECIES_REL),
    str(CLAIMS_REL), ARTICLE2_INPUT,
})


def input_plane(entry: str) -> str:
    """``'data'`` for a lane-advanced input, ``'pr'`` for everything else.

    Takes the REPORTED entry, count suffix and ``producer:`` prefix included, so the
    caller never has to strip anything to ask the question.
    """
    head = str(entry or "").split(" (", 1)[0]
    return "data" if head in DATA_PLANE_INPUTS else "pr"


class SynapseUnavailable(SystemExit):
    """``config/synapse.yml`` is unreadable or unparseable — nothing can be derived.

    A ``SystemExit`` subclass so running this module as a script still exits with the
    message, and a DISTINCT type so a caller's handler cannot misattribute an unrelated
    ``SystemExit`` — one raised at import time by a dependency, say — to the synapse.
    """


# ---------------------------------------------------------------------------
# Sparse-tolerant reads
# ---------------------------------------------------------------------------

#: In-process read cache. ``data/qledger/claims.jsonl`` is 45k rows behind a ``git show``
#: in sparse worktrees. Caching within one invocation is also the correct semantics — a
#: build must be a function of ONE snapshot of its inputs.
_READ_CACHE: dict[tuple[str, str], tuple[str | None, str]] = {}


def read_tracked(root: Path, rel: Path) -> tuple[str | None, str]:
    """Return (text, source) for a tracked FILE. source is 'worktree' | 'git' | 'absent'.

    Never raises on absence — the caller decides what an unreadable store means, and it
    must never mean "empty".
    """
    cache_key = (str(root), rel.as_posix())
    if cache_key not in _READ_CACHE:
        _READ_CACHE[cache_key] = _read_tracked_uncached(root, rel)
    return _READ_CACHE[cache_key]


def _read_tracked_uncached(root: Path, rel: Path) -> tuple[str | None, str]:
    on_disk = root / rel
    if on_disk.is_file():
        try:
            return on_disk.read_text(encoding="utf-8"), "worktree"
        except (OSError, UnicodeError):
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
    except (OSError, subprocess.SubprocessError, UnicodeError):
        pass
    return None, "absent"


def _is_repo_relative(root: Path, rel: str) -> bool:
    """True only for a path that stays inside ``root``. Purely lexical — no I/O, so it
    cannot be defeated by a path that does not exist yet, and it never follows a symlink
    to decide."""
    text = str(rel or "").strip()
    if not text:
        return False
    candidate = Path(text)
    # Lexical ONLY — deliberately no .resolve(). Resolving would follow symlinks, and a
    # checkout whose subdirectories are symlinks (an assembled test root, the ObsidianBrain
    # view pattern) would then report every real prereg as outside the repo — a detector
    # going blind, which reads exactly like a detector getting stricter.
    return not candidate.is_absolute() and ".." not in candidate.parts


def _tracked_file_exists(root: Path, rel: str) -> bool:
    """True when ``rel`` is a FILE IN THIS REPO, in the worktree or as a BLOB at HEAD.

    A DIRECTORY MUST ANSWER FALSE. ``git show HEAD:research`` exits 0 and prints a tree
    listing, so the previous probe accepted any folder — which made the C-1 backlog
    drainable to zero by pointing every authority-bearing artifact at a directory with no
    prereg in it at all. ``git cat-file -t`` distinguishes ``blob`` from ``tree``; the
    worktree half uses ``is_file()`` for the same reason.

    A PATH OUTSIDE THE REPO MUST ALSO ANSWER FALSE. ``root / "/etc/passwd"`` is
    ``/etc/passwd`` under pathlib's absolute-operand rule, so the worktree half answered
    True for any absolute path on the machine and the same C-1 backlog was drainable by
    pointing an authority-bearing artifact at a file no reviewer would ever see in a diff.
    ``..`` traversal is refused for the same reason — it only failed by accident of how
    deep an agent worktree happens to sit. The git half was never exposed (``git cat-file``
    resolves against the tree, not the filesystem); this closes the worktree half.
    """
    if not _is_repo_relative(root, rel):
        return False
    if (root / rel).is_file():
        return True
    try:
        result = subprocess.run(
            ["git", "cat-file", "-t", f"HEAD:{rel}"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "blob"


def _load_species(root: Path) -> tuple[list[dict] | None, str]:
    text, source = read_tracked(root, SPECIES_REL)
    if text is None:
        return None, source
    try:
        return list(json.loads(text).get("species") or []), source
    except (json.JSONDecodeError, AttributeError):
        return None, "unparseable"


@dataclass(frozen=True)
class QLedgerRead:
    """One read of the claim corpus, WITH ITS OWN BLINDNESS ACCOUNTED FOR.

    ``unparseable`` counts candidate lines the reader could not turn into a row — invalid
    JSON, or valid JSON that is not an object. Blank lines and ``#`` comments are not
    candidates and are never counted. ``considered`` is the number of candidate lines, so
    the pair is reportable as "n of m".

    The reader used to ``continue`` past a bad line, which made an UNREADABLE store
    indistinguishable from a store that was read successfully and held zero desk rows —
    "I could not look" rendered as "I looked and found nothing", the exact substitution
    CLAUDE.md §Epistemics forbids. The parsed rows are KEPT (display-tier accrual continues
    under disclosed partial blindness; the null law requires the incompleteness be
    REPRESENTED, not that the readable half be discarded) and the count is surfaced so the
    fail-closed channel can carry it.
    """

    rows: dict[str, int] | None
    horizons: dict[str, list[int]] | None
    source: str
    unparseable: int
    considered: int

    @property
    def source_label(self) -> str:
        """The provenance string for ``report['sources']`` — partial blindness included."""
        if not self.unparseable:
            return self.source
        return f"{self.source} ({self.unparseable} unparseable line(s))"


def _load_qledger(root: Path) -> QLedgerRead:
    """Desk row counts and declared horizons from the claim corpus."""
    text, source = read_tracked(root, CLAIMS_REL)
    if text is None:
        return QLedgerRead(None, None, source, 0, 0)
    rows: Counter[str] = Counter()
    horizons: dict[str, set[int]] = defaultdict(set)
    unparseable = 0
    considered = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        considered += 1
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            unparseable += 1
            continue
        if not isinstance(record, dict):
            # Valid JSON, wrong shape — a bare list or scalar carries no desk and cannot
            # be read as a claim. Counting it is what separates "the store is malformed"
            # from "the store has no rows for this desk".
            unparseable += 1
            continue
        desk = record.get("desk")
        if not desk:
            continue
        rows[desk] += 1
        horizon = record.get("horizon_d")
        if isinstance(horizon, int):
            horizons[desk].add(horizon)
    return QLedgerRead(
        dict(rows),
        {k: sorted(v) for k, v in horizons.items()},
        source,
        unparseable,
        considered,
    )


def _load_overlay(root: Path) -> tuple[dict[str, Any] | None, str, bool]:
    """Return (overlay, source, readable) for the curated overlay.

    An overlay that READS but does not parse — or parses to something that is not a
    mapping — is treated as ABSENT and NAMED, never as an empty overlay and never as a
    traceback. The distinction matters because an absent overlay silently means "no
    curated rows", which is exactly the value a broken overlay would fake.

    An EMPTY file is a different state and stays readable: ``yaml.safe_load("")`` is
    ``None``, the file was read, and "no curated rows" is what it honestly says.
    """
    text, source = read_tracked(root, OVERLAY_REL)
    if text is None:
        return None, source, False
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None, "unparseable", False
    if data is None:
        return None, source, True
    if not isinstance(data, dict):
        return None, "unparseable", False
    return data, source, True


def _qual_ladder_keys(root: Path) -> tuple[set[str] | None, str]:
    """The field keys of ``config/qual_ladder.yml`` — one half of ref resolution.

    A non-dict document is the NULL, not an empty key set: ``set()`` reads as "I looked
    and this ladder has zero keys", which would silently resolve every ``qual_ladder_ref``
    against nothing and report the refs as unresolvable rather than unchecked. Its
    siblings (:func:`_load_species`, :func:`_load_overlay`) already answer ``None`` here.
    """
    text, source = read_tracked(root, QUAL_LADDER_REL)
    if text is None:
        return None, source
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None, "unparseable"
    if not isinstance(data, dict):
        return None, "unparseable"
    return set(data), source


def _scan_producers(
    root: Path, producers: set[str]
) -> tuple[dict[str, DeskScan], list[str], list[str]]:
    """AST-scan every producer for qledger desk literals.

    Returns (scans, unresolved_desk_producers, UNREADABLE_producers). Producer source goes
    through the same ladder as every data read; an unreadable producer is COUNTED and
    announced rather than skipped with a silent ``continue``.
    """
    scans: dict[str, DeskScan] = {}
    unresolved: list[str] = []
    unreadable: list[str] = []
    for producer in sorted(producers):
        rel = producer.split(":")[0].strip()
        source, _ = read_tracked(root, Path(rel))
        if source is None:
            unreadable.append(producer)
            continue
        scan = scan_producer_source(source)
        if scan.imports_qledger:
            scans[producer] = scan
            if scan.unresolved:
                unresolved.append(producer)
    return scans, unresolved, unreadable


def _article2_modules() -> tuple[list[str] | None, str]:
    """Import the Article-2 module table rather than copying it.

    ``_ARTICLE2_MAP`` is already hand-duplicated verbatim in two other guards and the
    copies can drift; a third copy here would make the authority derivation's own input the
    parallel-store problem this design exists to avoid.

    RETURNS ``None`` ON FAILURE, NOT ``[]``. The previous version swallowed the ImportError
    and returned an empty list, so "the table could not be imported" rendered as "no
    Article-2 modules exist" and every completeness finding silently disappeared. The
    caller propagates the null and the audit reports SCORED_PATH_SURFACES_UNCHECKED.
    """
    try:
        from scripts.check_synapse_reads import _ENTRY_ARTICLE2_MODULES
    except Exception as exc:  # pragma: no cover - import shape is stable in-repo
        return None, f"unimportable ({type(exc).__name__}: {exc})"
    return sorted(_ENTRY_ARTICLE2_MODULES), "imported"


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the registry view and a report dict. Reads only; writes nothing, ever.

    ``report['unreadable_inputs']`` is the fail-closed channel: every input that could not
    be read lands there BY NAME, and the gate prints it on its summary line rather than
    printing a clean count it did not earn.
    """
    synapse_text, synapse_source = read_tracked(root, SYNAPSE_REL)
    if synapse_text is None:
        raise SynapseUnavailable(
            f"FATAL: {SYNAPSE_REL} is readable from neither the worktree nor HEAD — "
            f"there is nothing to derive from."
        )
    # A synapse that READS but does not parse is the same epistemic state as one that
    # could not be read at all: nothing can be derived. It must reach the caller as the
    # NOT CHECKED path, never as a bare YAMLError traceback (a traceback is a crash, and a
    # crashed gate is indistinguishable from an infrastructure failure in a job log).
    try:
        synapse = yaml.safe_load(synapse_text)
    except yaml.YAMLError as exc:
        raise SynapseUnavailable(
            f"FATAL: {SYNAPSE_REL} was read from {synapse_source} but does not parse as "
            f"YAML ({type(exc).__name__}) — there is nothing to derive from."
        ) from exc
    if not isinstance(synapse, dict):
        raise SynapseUnavailable(
            f"FATAL: {SYNAPSE_REL} was read from {synapse_source} but parses to "
            f"{type(synapse).__name__}, not a mapping — there is nothing to derive from."
        )

    overlay, overlay_source, overlay_ok = _load_overlay(root)

    species, species_source = _load_species(root)
    qledger = _load_qledger(root)
    desk_rows, desk_horizons = qledger.rows, qledger.horizons
    ladder_keys, ladder_source = _qual_ladder_keys(root)
    article2, article2_source = _article2_modules()

    producers = {
        (entry.get("producer") or "")
        for entry in (synapse.get("artifacts") or {}).values()
        if isinstance(entry, dict)
    }
    # Placeholder tokens (`<MANUAL>`, `<HAND_MAINTAINED>`, …) are not repo modules — they
    # are already excluded cells, so counting them "unreadable" would be a false alarm.
    scannable = {p for p in producers if p and placeholder_reason(p) is None}
    desk_scans, unresolved, unreadable_producers = _scan_producers(root, scannable)

    registry = build_registry(
        synapse=synapse,
        overlay=overlay,
        desk_scans=desk_scans,
        article2_modules=article2,
        species=species,
        qual_ladder_keys=ladder_keys,
        file_exists=(
            None if ladder_keys is None else (lambda p: _tracked_file_exists(root, p))
        ),
        qledger_desk_rows=desk_rows,
        qledger_desk_horizons=desk_horizons,
    )

    unreadable_inputs: list[str] = []
    for name, ok in (
        (str(OVERLAY_REL), overlay_ok),
        (str(QUAL_LADDER_REL), ladder_keys is not None),
        (str(SPECIES_REL), species is not None),
        (ARTICLE2_INPUT, article2 is not None),
    ):
        if not ok:
            unreadable_inputs.append(name)
    unreadable_inputs += [f"producer:{p}" for p in sorted(unreadable_producers)]
    # BOTH SHAPES of claim-store blindness: the whole store unreadable, and PARTIAL
    # blindness on a store that DID open. The rows that parsed stay in the view — the null
    # law requires the gap be REPRESENTED, not paid for with the readable half — but the
    # run is no longer entitled to call its inputs complete.
    if desk_rows is None:
        unreadable_inputs.append(str(CLAIMS_REL))
    elif qledger.unparseable:
        unreadable_inputs.append(
            f"{CLAIMS_REL} ({qledger.unparseable} unparseable line(s) of "
            f"{qledger.considered})"
        )

    # THE SPLIT IS A LOOKUP ON THE DECLARED TABLE, never a second copy of it. Classifying
    # inline — appending to two lists as the checks run — makes :data:`DATA_PLANE_INPUTS`
    # decoration: it can be emptied without changing a single exit code, so nothing can
    # ever prove it is the thing being obeyed. Routing every entry through
    # :func:`input_plane` makes the constant load-bearing, which is what lets a mutation of
    # the table fail a test.
    pr_plane_blind = [n for n in unreadable_inputs if input_plane(n) == "pr"]
    data_plane_blind = [n for n in unreadable_inputs if input_plane(n) == "data"]
    unreadable_inputs = pr_plane_blind + data_plane_blind

    report = {
        # THE JURISDICTION, carried to the caller rather than re-derived by it. Both lists
        # are also concatenated into `unreadable_inputs`, which stays the single answer to
        # "what could this run not read" — the split governs what may RED, never what is
        # REPORTED.
        "unreadable_by_plane": {"pr": pr_plane_blind, "data": data_plane_blind},
        "sources": {
            str(SYNAPSE_REL): synapse_source,
            str(OVERLAY_REL): overlay_source,
            str(SPECIES_REL): species_source,
            str(CLAIMS_REL): qledger.source_label,
            str(QUAL_LADDER_REL): ladder_source,
            "article2": article2_source,
        },
        "unresolved_desk_producers": sorted(unresolved),
        "unreadable_inputs": unreadable_inputs,
        "inputs_complete": not unreadable_inputs,
        "n_desk_scans": len(desk_scans),
        # The cell set BEFORE any exclusion. The overlay's orphan rule validates against
        # this, not against the built registry's ids — otherwise a `not_an_engine` row
        # creates the excluded row that proves it is not an orphan.
        "cell_ids": sorted(partition_artifacts(synapse)),
        "overlay": overlay,
    }
    return registry, report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="print the whole view as JSON")
    args = parser.parse_args()
    root: Path = args.root

    registry, report = build(root)

    if args.json:
        print(serialise(registry), end="")
        return 0

    findings = audit_content(registry)
    meta = registry["meta"]
    print(
        f"intelligence registry (DERIVED ON DEMAND, nothing committed): "
        f"{meta['n_engines']} engines over {meta['n_artifacts']} synapse artifacts "
        f"({meta['n_artifacts_mapped']} mapped, {meta['n_excluded']} cells excluded)",
        flush=True,
    )
    print(
        "  inputs: "
        + " ".join(f"{name}={src}" for name, src in sorted(report["sources"].items())),
        flush=True,
    )
    if report["unreadable_inputs"]:
        # Bare print, line-start, flushed — CLAUDE.md §"GitHub annotations must START the
        # line". A logger would prefix the line and GitHub would drop it silently.
        print(
            f"::notice title=intelligence-registry::COULD NOT LOOK — "
            f"{len(report['unreadable_inputs'])} input(s) unreadable, so the fields they "
            f"feed are NULL, not empty: {', '.join(report['unreadable_inputs'])}",
            flush=True,
        )
    if report["unresolved_desk_producers"]:
        print(
            f"::notice title=intelligence-registry::"
            f"{len(report['unresolved_desk_producers'])} producer(s) import engine.qledger "
            f"but their desk literal did not resolve by AST: "
            f"{', '.join(report['unresolved_desk_producers'])}",
            flush=True,
        )

    print("  excluded (machine-readable, no silent drops):", flush=True)
    for reason, count in sorted(Counter(r["reason"] for r in registry["excluded"]).items()):
        print(f"    {count:>3}  {reason}", flush=True)

    print(
        f"  authority: {dict(sorted(Counter(r['authority'] for r in registry['engines']).items()))}",
        flush=True,
    )
    print(
        f"  graded_by_design: "
        f"{dict(sorted(Counter(r['graded_by_design'] for r in registry['engines']).items()))}",
        flush=True,
    )
    print(
        f"  graded_by_design_evidence: "
        f"{dict(sorted(Counter(r['graded_by_design_evidence'] for r in registry['engines']).items()))}",
        flush=True,
    )

    c1 = [f for f in findings if f.code == "AUTHORITY_WITHOUT_EVIDENCE"]
    print(f"  MISSING EVIDENCE REPORT (C-1) — {len(c1)} engine(s):", flush=True)
    for finding in c1:
        print(f"    {finding.engine_id}: {finding.detail}", flush=True)

    for code, count in sorted(
        Counter(f.code for f in findings if f.code != "AUTHORITY_WITHOUT_EVIDENCE").items()
    ):
        print(f"  {code}: {count}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
