#!/usr/bin/env python3
"""scripts/agentos.py — Agent OS record validator and view generator.

The Agent OS is the KNOWLEDGE plane: it records what work exists, what was decided,
what was learned, and what is next.  Architecture: research/MASTERMIND_AGENT_OS_ARCHITECTURE.md.

INVARIANT I1 — this tool NEVER decides whether something may run.  It has no gate, no
lease with teeth, no dispatch.  ``validate`` exits non-zero on a MALFORMED RECORD only;
it never fails because work is in a particular state.  If a change here would let Agent
OS block or start execution, that change belongs in Mastermind ``control_plane/``
(processes) or the Macro hook layer (sessions), not here.

INVARIANT I4 — fail-CLOSED on schema, fail-OPEN on join.  A malformed authored record
is a lie about the organization and stops the writer.  A missing *join* input (a sibling
repo absent, ``gh`` rate-limited, a stale active_builds.json) degrades the view with a
printed warning and exits 0 — the nightly must never red because of this script, exactly
as ``scripts/build_active_build_map.py`` already commits to.

WHERE THE HARD/SOFT LINE SITS, and why it moved.  ``validate`` runs unconditionally on
every PR in the fleet (``.github/ci/legacy-jobs.yml`` job ``self-mod-fence``, which
``infer_job_scopes()`` gives an empty path scope), over the WHOLE store — not over the
diff.  So a hard rule that keys on the *state* of the work is a fleet-wide fail-closed
gate on a knowledge record, which is invariant I1 turned operationally false.  It is also
reachable without anyone writing an invalid record: branch A sets W1 done, branch B sets
W2 dropped, both validate clean, ``git merge`` is clean, and the merged tree trips
``active-but-complete``.  The line is therefore drawn at MERGE REACHABILITY:

    HARD  — properties a clean textual merge of two individually-valid records cannot
            produce: frontmatter parse, enum membership, key/filename agreement,
            duplicate key, citation SHAPE, dangling reference, cycle.
    WARN  — everything that describes the STATE of the work: status vs wave rollup,
            blocked/blocked_by pairing, staleness, claim expiry, record-vs-execution
            disagreement.  These are reported by ``status`` and ``brief``, which is
            where a human reads them anyway.

ZERO NETWORK.  Nothing here calls ``gh``, ``requests``, or ``urllib``.  PR state comes
only from the local ``data/governance/active_builds.json`` written by the nightly ABM
sweep.  The 5,000/hr REST ``core`` bucket is shared with ``ship_loop_guard.py``, which
fails CLOSED when it is exhausted, so a status command that burned quota could block the
very Stop it was reporting on.  ``tests/test_agentos_status.py`` proves this at runtime
by running ``status`` with sockets disabled.

Subcommands:
    validate          schema + referential integrity over agentos/ (Phase 0)
    status            materialize agent_os_state.v1 + docs/AGENT_OS_STATE.md (Phase 2)
    brief             CEO brief (Phase 2; spec in research/MASTERMIND_CEO_BRIEF_SPEC.md)
    compile-context   bounded, cited context_bundle.v1 for a workstream or a task
                      (Phase 3; architecture §8).  Reads and cites; writes nothing.

Usage::

    python3 scripts/agentos.py validate
    python3 scripts/agentos.py validate --root agentos --quiet
    python3 scripts/agentos.py status
    python3 scripts/agentos.py status --dry-run
    python3 scripts/agentos.py brief --since 24h
    python3 scripts/agentos.py brief --full
    python3 scripts/agentos.py brief --json
    python3 scripts/agentos.py compile-context --workstream PROPHET-US-ENTRY-TIMING
    python3 scripts/agentos.py compile-context "fix prophet late entry" --text --budget 4000
"""
from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    print("::error title=agentos::PyYAML is required (pip install pyyaml)", flush=True)
    raise SystemExit(1)

_ROOT = Path(__file__).resolve().parent.parent
# Pinned at module scope, before any in-repo import.  Run as `python3 scripts/agentos.py`,
# sys.path[0] is scripts/, so `from scripts import ...` resolves against whatever `scripts`
# package the ambient PYTHONPATH offers first — the hijack `tests/test_check_script_import
# _pinning.py` builds a decoy repo to prove.  A pin inside the one function that imports
# runs too late to be a contract and reads as optional; this line is the contract.
sys.path.insert(0, str(_ROOT))
_DEFAULT_STORE = _ROOT / "agentos"
_PROGRAMS = _ROOT / "config" / "mastermind_programs.yml"

_ACTIVE_BUILDS = _ROOT / "data" / "governance" / "active_builds.json"
_STATE_JSON = _ROOT / "data" / "governance" / "agent_os_state.json"
_STATE_MD = _ROOT / "docs" / "AGENT_OS_STATE.md"
_BRIEF_MARK = _ROOT / "data" / "governance" / ".ceo_brief_last"

STATE_SCHEMA = "agent_os_state.v1"
BRIEF_SCHEMA = "ceo_brief.v1"
READINESS_SCHEMA = "agentos.readiness.v1"

# Sibling checkouts, resolved by walking up from this repo.  Macro is this checkout; the
# other two are separate clones under the shared project home.  Absent is NORMAL (I4).
SIBLING_DIRS = {"terminal": "charting-app", "mastermind": "Mastermind"}
SIBLING_ENV = {"terminal": "MACRO_TERMINAL_REPO", "mastermind": "MACRO_MASTERMIND_REPO"}
_STRATEGIC_STATE_REL = Path("config") / "strategic_state.yml"

KEY_RE = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)

WORKSTREAM_STATUS = {
    "proposed", "active", "blocked", "awaiting_ci",
    "awaiting_review", "done", "parked", "killed",
}
WAVE_STATUS = {"todo", "in_progress", "awaiting_ci", "done", "dropped"}
CLASSES = {"research", "build", "design", "adjudication", "mechanical"}
BLAST = {"reversible", "user_facing", "irreversible"}
AMBIGUITY = {"specified", "scoped", "open"}
# A typed intentional wait (R8-B1).  CLOSED on purpose: an open vocabulary would let
# each author mint a private reason, and "why is this still" would need a parser again.
WAIT_KINDS = {"natural_evidence", "external_dependency", "calendar_window", "external_action"}
WAIT_FIELDS = {"kind", "review_after", "condition"}
CONFIDENCE_DEC = {"high", "medium", "low"}
CONFIDENCE_DSC = {"verified", "probable", "suspected"}
REVERSIBILITY = {"easy", "costly", "one_way"}
DISCOVERY_KIND = {
    "architecture", "data", "landmine", "dead_code", "constraint", "runtime",
}
REPOS = {"macro", "terminal", "mastermind"}
HANDOFF_MODEL = {"fable", "opus", "sonnet", "haiku", "codex", "local", "sol"}
HANDOFF_ENDED = {"complete", "ci_handoff", "blocked", "context_budget", "crashed"}

# A provenance string must carry something a reader can RUN or OPEN.  Deliberately
# permissive: a shell-ish token, a `path:line`, a `#PR`, or a bare path with an
# extension.  It cannot judge whether the command is the right one and does not try.
PROVENANCE_RE = re.compile(
    r"(?:^|[\s(\"'`])(?:[a-z0-9_.-]+/)*[a-z0-9_.-]+\.[a-z0-9]{1,5}(?::\d+)?"   # path[:line]
    r"|#\d{2,6}"                                                                # #PR
    r"|\b(?:git|python3?|pytest|gh|grep|rg|jq|curl|ls|cat|make|npm|node|psql|"
    r"sqlite3|awk|sed|find|test|bash|sh)\b"                                     # command
    r"|\bhttps?://",
    re.IGNORECASE,
)
BANNED_HANDOFF_PHRASES = ("see above", "as discussed", "see the discussion above")
VERIFIED_FLOOR = "tests pass"

STALE_DISCOVERY_DAYS = 90
STALE_WORKSTREAM_DAYS = 30
DEFAULT_CLAIM_HOURS = 12


class Problem:
    """One validation finding.  ``hard`` findings fail the run; warnings do not."""

    __slots__ = ("path", "rule", "message", "hard")

    def __init__(self, path: Path, rule: str, message: str, *, hard: bool) -> None:
        self.path = path
        self.rule = rule
        self.message = message
        self.hard = hard

    def render(self, root: Path) -> str:
        try:
            rel = self.path.relative_to(root)
        except ValueError:
            rel = self.path
        return f"{rel}: [{self.rule}] {self.message}"


# ---------------------------------------------------------------- parsing


def parse_record(path: Path) -> tuple[dict[str, Any], str]:
    """Split a record into (frontmatter dict, body).  Raises ValueError when malformed."""
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("no YAML frontmatter block (expected a leading '---' fence)")
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise ValueError(f"malformed YAML frontmatter: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a mapping")
    return data, match.group(2)


def _load_programs() -> set[str] | None:
    """Known program keys, or None when the registry is unreadable (fail-open join)."""
    if not _PROGRAMS.exists():
        return None
    try:
        doc = yaml.safe_load(_PROGRAMS.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return None
    programs = doc.get("programs") if isinstance(doc, dict) else None
    if isinstance(programs, dict):
        return set(programs)
    if isinstance(programs, list):
        keys: set[str] = set()
        for item in programs:
            if isinstance(item, dict):
                key = item.get("key") or item.get("id") or item.get("name")
                if isinstance(key, str):
                    keys.add(key)
        return keys or None
    return None


# ---------------------------------------------------------------- helpers


def _require(
    rec: dict[str, Any], field: str, path: Path, out: list[Problem], *, rule: str = "required-field"
) -> bool:
    value = rec.get(field)
    if value is None or (isinstance(value, (str, list, dict)) and len(value) == 0):
        out.append(Problem(path, rule, f"missing required field '{field}'", hard=True))
        return False
    return True


def _enum(
    rec: dict[str, Any], field: str, allowed: set[str], path: Path, out: list[Problem]
) -> None:
    value = rec.get(field)
    if value is not None and value not in allowed:
        out.append(
            Problem(
                path,
                "bad-enum",
                f"'{field}' is {value!r}; allowed: {', '.join(sorted(allowed))}",
                hard=True,
            )
        )


def _date(rec: dict[str, Any], field: str, path: Path, out: list[Problem]) -> None:
    """Dates must be ISO-8601.  Relative strings are unreadable six months later."""
    value = rec.get(field)
    if value is None:
        return
    if isinstance(value, _dt.date):
        return
    if not isinstance(value, str) or not (ISO_DATE_RE.match(value) or ISO_TS_RE.match(value)):
        out.append(
            Problem(
                path,
                "bad-date",
                f"'{field}' must be ISO-8601 (YYYY-MM-DD or ...Z), got {value!r}",
                hard=True,
            )
        )


def _is_review_date(value: Any) -> bool:
    """``review_after`` is date-ONLY.  A timestamp reads as an instant something fires;
    this is the date a HUMAN looks again, so the finer resolution would be a lie."""
    if isinstance(value, _dt.datetime):
        return False
    if isinstance(value, _dt.date):
        return True
    if not isinstance(value, str) or not ISO_DATE_RE.match(value):
        return False
    try:
        # Shape is not enough: '2026-13-45' matches the pattern and is not a day.
        _dt.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _check_wait(rec: dict[str, Any], where: str, path: Path, out: list[Problem]) -> None:
    """Validate one authored ``wait`` — the same contract at workstream and wave scope.

    A wait says inactivity here is DELIBERATE and names the date its author will look
    again.  It is testimony, not machinery: nothing in this file schedules, wakes, gates
    or completes on it (I1), and ``condition`` is never parsed — it is opaque human
    context, read only by a reader.  Absence is never inferred to mean anything.
    """
    wait = rec.get("wait")
    if wait is None:
        return
    if not isinstance(wait, dict):
        out.append(Problem(path, "bad-wait", f"{where}'wait' must be a mapping", hard=True))
        return
    unknown = sorted(set(wait) - WAIT_FIELDS, key=str)
    if unknown:
        out.append(
            Problem(
                path,
                "bad-wait",
                f"{where}'wait' carries unknown field(s) "
                f"{', '.join(repr(name) for name in unknown)}; the contract is closed to "
                f"{', '.join(sorted(WAIT_FIELDS))}",
                hard=True,
            )
        )
    kind = wait.get("kind")
    if not isinstance(kind, str) or kind not in WAIT_KINDS:
        out.append(
            Problem(
                path,
                "bad-wait",
                f"{where}'wait.kind' is {kind!r}; allowed: {', '.join(sorted(WAIT_KINDS))}",
                hard=True,
            )
        )
    review_after = wait.get("review_after")
    if not _is_review_date(review_after):
        out.append(
            Problem(
                path,
                "bad-wait",
                f"{where}'wait.review_after' must be a date-only YYYY-MM-DD next-review "
                f"date, got {review_after!r}",
                hard=True,
            )
        )
    condition = wait.get("condition")
    if not isinstance(condition, str) or not condition.strip():
        out.append(
            Problem(
                path,
                "bad-wait",
                f"{where}'wait.condition' must be a non-empty string saying what the "
                f"author will look at",
                hard=True,
            )
        )


def _wait_row(rec: dict[str, Any]) -> dict[str, Any] | None:
    """Project an authored wait for JSON, or None when absent.

    YAML hands back ``review_after`` as a ``date`` OBJECT, which ``json.dumps`` refuses;
    normalizing to ISO text here is the whole transformation — no clock is read, no
    remaining time is computed, and nothing is re-derived from the condition.
    """
    wait = rec.get("wait")
    if not isinstance(wait, dict):
        return None
    review_after = wait.get("review_after")
    if isinstance(review_after, _dt.date):
        review_after = review_after.isoformat()
    return {
        "kind": str(wait.get("kind") or ""),
        "review_after": str(review_after or ""),
        "condition": str(wait.get("condition") or "").strip(),
    }


def _as_date(value: Any) -> _dt.date | None:
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, str):
        for pattern in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                return _dt.datetime.strptime(value, pattern).date()
            except ValueError:
                continue
    return None


def _refs(value: Any, prefix: str) -> list[str]:
    """Extract bare keys from a list of ``PREFIX:KEY`` citations.

    Silent on anything that is not that shape — callers that need the malformed
    entries too must use :func:`_citations`, which is the only form allowed in a
    record.  Kept as a thin wrapper so the graph builders read cleanly.
    """
    return _citations(value, prefix)[0]


def _citations(value: Any, prefix: str) -> tuple[list[str], list[str]]:
    """Split a citation field into ``(keys, malformed_entries)``.

    ONE citation shape exists — ``PREFIX:KEY``.  A bare ``KEY`` is malformed, and this
    is the function that says so.  It exists because the previous split behaviour was
    the single most expensive kind of defect available here: ``depends_on: [FOO]`` was
    silently DROPPED (0 errors, 0 warnings) while ``depends_on: ["WS:FOO"]`` hard-erred,
    so the workstream dependency graph that ``check_references`` walks for cycles — and
    that ``status`` now exposes as readiness — was quietly incomplete, with no
    signal that an edge was missing.  Readiness computed over a graph with dropped edges
    is wrong in a way nobody can see.
    """
    keys: list[str] = []
    malformed: list[str] = []
    items = value if isinstance(value, list) else ([value] if value is not None else [])
    for item in items:
        if not isinstance(item, str):
            malformed.append(repr(item))
            continue
        text = item.strip()
        if not text:
            continue
        if text.startswith(f"{prefix}:"):
            keys.append(text.split(":", 1)[1].strip())
        else:
            malformed.append(text)
    return keys, malformed


def _check_citations(
    rec: dict[str, Any], field: str, prefix: str, path: Path, out: list[Problem]
) -> list[str]:
    """Validate a citation field's SHAPE (hard) and return its resolved keys."""
    keys, malformed = _citations(rec.get(field), prefix)
    for entry in malformed:
        out.append(
            Problem(
                path,
                "bad-citation",
                f"'{field}' entry {entry!r} is not a {prefix}:KEY citation — one citation "
                f"shape exists, and a bare key resolves against nothing",
                hard=True,
            )
        )
    return keys


def _check_supersession(
    rec: dict[str, Any], prefix: str, path: Path, out: list[Problem]
) -> None:
    """``superseded_by`` must name exactly one ``PREFIX:KEY`` replacement, or be absent.

    The most expensive unvalidated field in the schema.  ``superseded_by`` is the ONE
    field that deletes a live record from every compiled bundle, and it was previously
    read by TRUTHINESS: ``superseded_by: "no"`` evicted a current decision from every
    bundle forever while ``validate`` exited 0, and ``false``/``0``/``""`` silently did
    not evict — the same field meaning two opposite things depending on how it was typed.
    Same one-citation-shape law as everything else (:func:`_citations`), and hard, because
    a record that vanishes from the bundle is invisible in exactly the place a reader
    would look for it.
    """
    if "superseded_by" not in rec:
        return
    value = rec.get("superseded_by")
    if value is None:
        return  # an explicitly cleared field is an ABSENT field, not a malformed one
    keys, malformed = _citations(value, prefix)
    if len(keys) == 1 and not malformed:
        return
    out.append(
        Problem(
            path,
            "bad-supersession",
            f"'superseded_by' is {value!r} — it must name exactly one {prefix}:KEY "
            f"replacement (or be absent).  This field EVICTS the record from every "
            f"compiled context bundle; a junk value evicts it silently",
            hard=True,
        )
    )


def repo_roots() -> dict[str, Path | None]:
    """Filesystem root per repo key, or None when that checkout is absent.

    ``_ROOT`` is the MACRO checkout only.  Resolving a Terminal record's paths against it
    produces two wrong answers, and the second is worse than the first: a false phantom
    warning for a path that exists in Terminal, and a silent PASS for a path that happens
    to exist in Macro at the same relative location.  Absent siblings are normal (I4) —
    the caller skips the check and says so, rather than guessing.
    """
    roots: dict[str, Path | None] = {"macro": _ROOT}
    for key, dirname in SIBLING_DIRS.items():
        override = os.environ.get(SIBLING_ENV[key])
        if override:
            candidate = Path(override).expanduser()
            roots[key] = candidate if candidate.exists() else None
            continue
        found: Path | None = None
        for parent in list(_ROOT.parents)[:6]:
            candidate = parent / dirname
            if candidate.is_dir():
                found = candidate
                break
        roots[key] = found
    return roots


def _home_repo(rec: dict[str, Any]) -> str:
    """The repo an unprefixed path in this record is relative to."""
    repos = rec.get("repos")
    if isinstance(repos, list) and repos:
        if "macro" in repos:
            return "macro"
        first = repos[0]
        if isinstance(first, str) and first in REPOS:
            return first
    return "macro"


def _resolve_path(entry: str, rec: dict[str, Any]) -> tuple[str, str] | None:
    """Split a record path entry into ``(repo_key, repo_relative_path)``.

    Returns None when the entry is not a repo-relative path at all (a URL, or a
    ``PREFIX:KEY`` citation that wandered into a path list).
    """
    if ":" in entry:
        prefix, rest = entry.split(":", 1)
        if prefix in REPOS:
            return prefix, rest.strip()
        return None
    return _home_repo(rec), entry


def _git(*args: str, cwd: Path | None = None) -> str | None:
    """Run a git command, returning stdout or None on any failure (fail-open).

    Local git only — never a fetch, never a network call.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd or _ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def git_dates(path: Path) -> tuple[str | None, str | None]:
    """``(created, updated)`` as ISO dates, derived from git history.

    DERIVED, NOT AUTHORED.  Hand-typed `created`/`updated` fields were the only verified
    concurrent-edit conflict site in the record schema (every session touching a record
    rewrites the same line), and they made staleness circular: the field that says "this
    record is fresh" is typed by the session claiming freshness.  git already knows.
    Returns ``(None, None)`` for an untracked or not-yet-committed record — which is the
    normal state of a record created in the current working tree.
    """
    try:
        rel = path.resolve().relative_to(_ROOT)
    except ValueError:
        return None, None
    updated = _git("log", "-1", "--format=%as", "--", str(rel))
    added = _git("log", "--diff-filter=A", "--format=%as", "--", str(rel))
    last = (updated or "").strip().splitlines()
    first = [ln for ln in (added or "").strip().splitlines() if ln]
    return (first[-1] if first else None), (last[0] if last else None)


def _cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """Return one cycle as a node list, or None.  Iterative DFS with an explicit stack."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {node: WHITE for node in graph}
    for start in list(graph):
        if colour[start] != WHITE:
            continue
        stack: list[tuple[str, Iterable[str]]] = [(start, iter(graph.get(start, ())))]
        trail = [start]
        colour[start] = GREY
        while stack:
            node, children = stack[-1]
            advanced = False
            for child in children:
                if child not in graph:
                    continue  # dangling refs are reported by their own rule
                if colour[child] == GREY:
                    return trail[trail.index(child):] + [child]
                if colour[child] == WHITE:
                    colour[child] = GREY
                    trail.append(child)
                    stack.append((child, iter(graph.get(child, ()))))
                    advanced = True
                    break
            if not advanced:
                colour[node] = BLACK
                stack.pop()
                if trail:
                    trail.pop()
    return None


# ---------------------------------------------------------------- per-type checks


def check_workstream(rec: dict[str, Any], path: Path, programs: set[str] | None) -> list[Problem]:
    out: list[Problem] = []
    # `created` / `updated` are DERIVED from git by the generator (see git_dates) and are
    # deliberately NOT required here — see the module docstring on the conflict site.
    for field in ("key", "title", "objective", "status", "program",
                  "repos", "owner", "class", "blast_radius", "ambiguity",
                  "waves", "next_action"):
        _require(rec, field, path, out)

    key = rec.get("key")
    if isinstance(key, str):
        if not KEY_RE.match(key):
            out.append(Problem(path, "bad-key", f"key {key!r} must be UPPER-KEBAB", hard=True))
        if path.stem != f"WS-{key}":
            out.append(
                Problem(path, "filename-mismatch",
                        f"filename must be 'WS-{key}.md'", hard=True)
            )

    _enum(rec, "status", WORKSTREAM_STATUS, path, out)
    _enum(rec, "class", CLASSES, path, out)
    _enum(rec, "blast_radius", BLAST, path, out)
    _enum(rec, "ambiguity", AMBIGUITY, path, out)
    _date(rec, "created", path, out)
    _date(rec, "updated", path, out)
    _check_wait(rec, "", path, out)

    repos = rec.get("repos")
    if isinstance(repos, list):
        for repo in repos:
            if repo not in REPOS:
                out.append(
                    Problem(path, "bad-repo",
                            f"unknown repo {repo!r}; allowed: {', '.join(sorted(REPOS))}",
                            hard=True)
                )

    program = rec.get("program")
    if programs is not None and isinstance(program, str) and program not in programs:
        out.append(
            Problem(path, "unknown-program",
                    f"program {program!r} not in config/mastermind_programs.yml", hard=True)
        )

    # Citation SHAPE is hard (a clean merge cannot invent one); the keys themselves are
    # resolved against the store in check_references.
    _check_citations(rec, "depends_on", "WS", path, out)
    _check_citations(rec, "decisions", "DEC", path, out)
    _check_citations(rec, "discoveries", "DSC", path, out)

    # STATE rules below are WARNINGS, not errors.  Each one is reachable from a clean
    # merge of two individually-valid records, and `validate` runs fleet-wide on every
    # PR over the whole store — see the module docstring.  `status` reports them.
    status = rec.get("status")
    blocked_by = rec.get("blocked_by") or []
    if status == "blocked" and not blocked_by:
        out.append(Problem(path, "blocked-without-cause",
                           "status is 'blocked' but blocked_by is empty", hard=False))
    if blocked_by and status != "blocked":
        out.append(Problem(path, "cause-without-blocked",
                           f"blocked_by is set but status is {status!r}", hard=False))

    waves = rec.get("waves")
    if isinstance(waves, list):
        if not waves:
            out.append(Problem(path, "no-waves", "at least one wave is required", hard=True))
        seen: set[str] = set()
        wave_graph: dict[str, list[str]] = {}
        for index, wave in enumerate(waves):
            where = f"wave[{index}]"
            if not isinstance(wave, dict):
                out.append(Problem(path, "bad-wave", f"{where} must be a mapping", hard=True))
                continue
            wid = wave.get("id")
            if not isinstance(wid, str) or not wid.strip() or wid != wid.strip():
                out.append(
                    Problem(
                        path,
                        "bad-wave",
                        f"{where} 'id' must be a non-empty string without surrounding whitespace",
                        hard=True,
                    )
                )
                continue
            if not wave.get("title"):
                out.append(Problem(path, "bad-wave", f"{where} ({wid}) missing 'title'", hard=True))
            if wid in seen:
                out.append(Problem(path, "duplicate-wave", f"duplicate wave id {wid!r}", hard=True))
            seen.add(wid)
            wstatus = wave.get("status")
            if wstatus not in WAVE_STATUS:
                out.append(
                    Problem(path, "bad-enum",
                            f"{where} ({wid}) status {wstatus!r}; allowed: "
                            f"{', '.join(sorted(WAVE_STATUS))}", hard=True)
                )
            _check_wait(wave, f"{where} ({wid}) ", path, out)
            deps = wave.get("depends_on") or []
            wave_graph[wid] = [d for d in deps if isinstance(d, str)]
        for wid, deps in wave_graph.items():
            for dep in deps:
                if dep not in seen:
                    out.append(
                        Problem(path, "dangling-wave-dep",
                                f"wave {wid!r} depends on unknown wave {dep!r}", hard=True)
                    )
        cycle = _cycle(wave_graph)
        if cycle:
            out.append(Problem(path, "wave-cycle",
                               "wave dependency cycle: " + " -> ".join(cycle), hard=True))
        if waves and status == "active" and all(
            isinstance(w, dict) and w.get("status") in {"done", "dropped"} for w in waves
        ):
            # WARNING, deliberately.  Reproduced end to end: branch A sets W1 done,
            # branch B sets W2 dropped, both validate clean, the textual merge is clean,
            # and the merged tree trips this rule — two green PRs and a red main, on a
            # check that runs unscoped on EVERY PR in the fleet.
            out.append(
                Problem(path, "active-but-complete",
                        "status is 'active' but every wave is done/dropped", hard=False)
            )

    claim = rec.get("claim")
    if isinstance(claim, dict):
        for field in ("by", "at", "expires"):
            if not claim.get(field):
                out.append(Problem(path, "bad-claim",
                                   f"claim missing '{field}'", hard=True))
        _date(claim, "at", path, out)
        _date(claim, "expires", path, out)
        expires = _as_date(claim.get("expires"))
        if expires and expires < _dt.date.today():
            out.append(
                Problem(path, "stale-claim",
                        f"claim by {claim.get('by')!r} expired {expires}; "
                        "reports as unclaimed (advisory only)", hard=False)
            )

    needs = rec.get("needs_ceo")
    if isinstance(needs, dict):
        for field in ("question", "recommendation"):
            if not needs.get(field):
                out.append(Problem(path, "bad-needs-ceo",
                                   f"needs_ceo missing '{field}'", hard=True))

    # Phantom citations: a record pointing at a path that does not exist sends the next
    # session hunting for a file that was never there.  WARNING tier, not hard, because a
    # path may legitimately not exist yet.  Each entry is resolved against ITS OWN repo
    # root — a Terminal record's paths are not Macro paths, and checking them against the
    # Macro checkout produces both false phantoms and silent false passes.
    roots = repo_roots()
    for field, rule in (("artifacts", "phantom-artifact"), ("owns_paths", "phantom-owns-path")):
        for entry in rec.get(field) or []:
            if not isinstance(entry, str):
                continue
            resolved = _resolve_path(entry, rec)
            if resolved is None:
                continue
            repo_key, rel = resolved
            root = roots.get(repo_key)
            if root is None:
                continue  # sibling checkout absent — unknowable, not wrong (I4)
            # Check the static prefix, i.e. everything before the first glob segment.
            parts: list[str] = []
            for segment in rel.split("/"):
                if any(c in segment for c in "*?["):
                    break
                parts.append(segment)
            stem = "/".join(parts)
            if not stem:
                continue
            if not (root / stem).exists():
                detail = f"{entry!r} does not exist" if stem == rel else \
                    f"{entry!r} has no existing base {stem!r}"
                out.append(
                    Problem(path, rule, f"{field} entry {detail} in repo {repo_key!r}",
                            hard=False)
                )
    return out


def check_decision(rec: dict[str, Any], path: Path) -> list[Problem]:
    out: list[Problem] = []
    for field in ("key", "question", "answer", "rationale", "alternatives",
                  "evidence", "affects", "confidence", "reversibility",
                  "decided_by", "decided_at"):
        _require(rec, field, path, out)

    key = rec.get("key")
    if isinstance(key, str):
        if not KEY_RE.match(key):
            out.append(Problem(path, "bad-key", f"key {key!r} must be UPPER-KEBAB", hard=True))
        if path.stem != f"DEC-{key}":
            out.append(Problem(path, "filename-mismatch",
                               f"filename must be 'DEC-{key}.md'", hard=True))

    _enum(rec, "confidence", CONFIDENCE_DEC, path, out)
    _enum(rec, "reversibility", REVERSIBILITY, path, out)
    _date(rec, "decided_at", path, out)
    _date(rec, "review_by", path, out)
    _check_supersession(rec, "DEC", path, out)
    # Same defect class as superseded_by, one field over: `_refs` silently drops a bare
    # key, so an unshaped `supersedes` entry used to skip the reciprocity check entirely.
    _check_citations(rec, "supersedes", "DEC", path, out)

    alts = rec.get("alternatives")
    if isinstance(alts, list):
        if not alts:
            out.append(
                Problem(path, "no-alternatives",
                        "at least one alternative is required; a decision with none is a "
                        "default — record it as option '(none considered)'", hard=True)
            )
        for index, alt in enumerate(alts):
            if not isinstance(alt, dict) or not alt.get("option") or not alt.get("why_not"):
                out.append(
                    Problem(path, "bad-alternative",
                            f"alternatives[{index}] needs both 'option' and 'why_not'", hard=True)
                )

    review_by = _as_date(rec.get("review_by"))
    if review_by and review_by < _dt.date.today():
        out.append(Problem(path, "review-overdue",
                           f"review_by {review_by} has passed", hard=False))
    return out


def check_discovery(rec: dict[str, Any], path: Path) -> list[Problem]:
    out: list[Problem] = []
    for field in ("key", "claim", "falsifier", "so_what", "kind",
                  "verified_at", "verified_by", "scope", "confidence"):
        _require(rec, field, path, out)

    key = rec.get("key")
    if isinstance(key, str):
        if not KEY_RE.match(key):
            out.append(Problem(path, "bad-key", f"key {key!r} must be UPPER-KEBAB", hard=True))
        if path.stem != f"DSC-{key}":
            out.append(Problem(path, "filename-mismatch",
                               f"filename must be 'DSC-{key}.md'", hard=True))

    _enum(rec, "kind", DISCOVERY_KIND, path, out)
    _enum(rec, "confidence", CONFIDENCE_DSC, path, out)
    _date(rec, "verified_at", path, out)
    _date(rec, "expires", path, out)
    _check_supersession(rec, "DSC", path, out)

    # The two admission gates, made STRUCTURAL rather than merely non-empty.  A
    # `_require` check passes on `falsifier: "no"` and `verified_by: vibes`, which is
    # exactly the record the gates exist to refuse.  Shape only — this cannot judge
    # whether the command is the RIGHT one, and does not pretend to.
    for field, rule in (("verified_by", "unprovable-verification"),
                        ("falsifier", "unfalsifiable-claim")):
        value = rec.get(field)
        if isinstance(value, str) and value.strip() and not PROVENANCE_RE.search(value):
            out.append(
                Problem(
                    path, rule,
                    f"'{field}' carries no runnable token — needs a command, a "
                    f"'file:line', or a '#PR' (README rule 4), got {value.strip()[:60]!r}",
                    hard=True,
                )
            )
    return out


def check_handoff(rec: dict[str, Any], path: Path) -> list[Problem]:
    """Handoff frontmatter — STATE_SCHEMA §4, quality floor in the handoff protocol.

    Handoffs were the whole G3 deliverable and were entirely unvalidated: a file of
    garbage dropped into ``agentos/handoffs/`` was not even COUNTED, so the plan's
    acceptance gate ("validate exits 0 on the full record set") was satisfiable by a
    store full of malformed handoffs.  Only the machine-checkable floor items are
    enforced here — the ones that require knowing what surprised you are not checkable
    and are not pretended to be.
    """
    out: list[Problem] = []
    for field in ("workstream", "session", "model", "mission", "state_before",
                  "changed", "verified", "unresolved", "next_actions",
                  "do_not_redo", "danger_areas", "ended_because"):
        _require(rec, field, path, out)

    # `unverified` must be PRESENT; an empty list is a valid, meaningful answer, so
    # _require (which rejects empty) is the wrong check for it.
    if "unverified" not in rec:
        out.append(
            Problem(path, "required-field",
                    "missing required field 'unverified' — an empty list is a valid "
                    "answer, its ABSENCE is not", hard=True)
        )

    _enum(rec, "model", HANDOFF_MODEL, path, out)
    _enum(rec, "ended_because", HANDOFF_ENDED, path, out)
    _check_citations(rec, "workstream", "WS", path, out)
    _check_citations(rec, "decisions", "DEC", path, out)
    _check_citations(rec, "discoveries", "DSC", path, out)

    verified = rec.get("verified")
    if isinstance(verified, list):
        for index, item in enumerate(verified):
            if not isinstance(item, dict) or not str(item.get("command") or "").strip():
                out.append(
                    Problem(path, "unbacked-verification",
                            f"verified[{index}] has no 'command' — '{VERIFIED_FLOOR}' is "
                            "the failure this list exists to make unwritable", hard=True)
                )
    changed = rec.get("changed")
    if isinstance(changed, list):
        for index, item in enumerate(changed):
            if not isinstance(item, dict) or not str(item.get("what") or "").strip():
                out.append(
                    Problem(path, "bad-changed-entry",
                            f"changed[{index}] needs both 'path' and 'what'", hard=True)
                )

    body = rec.get("_body", "")
    if isinstance(body, str):
        lowered = body.lower()
        for phrase in BANNED_HANDOFF_PHRASES:
            if phrase in lowered:
                out.append(
                    Problem(path, "context-free-handoff",
                            f"body says {phrase!r} — the next session cannot see 'above'",
                            hard=True)
                )
    return out


# ---------------------------------------------------------------- cross-record

# Rules :func:`check_references` attributes to the CITING record rather than to a record
# that is itself wrong.  They are JOIN failures, not schema failures, and invariant I4
# says a join fails OPEN: a valid workstream whose sibling was renamed in an in-flight PR
# still has a compilable state, and refusing to compile it hands the session nothing at
# all instead of a bundle with one named hole.  A record carrying only these is rendered;
# the problem travels with it as a `degraded` line, so it is visible rather than fatal.
# Record-LOCAL rules (bad-enum, required-field, bad-key, unparseable, bad-supersession, …)
# stay fatal for the compilation target — that record is a lie about the organization.
CROSS_RECORD_RULES = frozenset({
    "dangling-ref",
    "workstream-cycle",
    "unreciprocated-supersession",
})


def check_references(records: dict[str, dict[str, Any]], paths: dict[str, Path]) -> list[Problem]:
    """Referential integrity across the whole store: dangling refs, cycles, reciprocity."""
    out: list[Problem] = []
    ws = {k[3:]: v for k, v in records.items() if k.startswith("WS/")}
    dec = {k[4:]: v for k, v in records.items() if k.startswith("DEC/")}
    dsc = {k[4:]: v for k, v in records.items() if k.startswith("DSC/")}

    def path_of(prefix: str, key: str) -> Path:
        return paths[f"{prefix}/{key}"]

    hnd = {k[4:]: v for k, v in records.items() if k.startswith("HND/")}

    for key, rec in ws.items():
        here = path_of("WS", key)
        for dep in _refs(rec.get("depends_on"), "WS"):
            if dep not in ws:
                out.append(Problem(here, "dangling-ref",
                                   f"depends_on references unknown WS:{dep}", hard=True))
        for ref in _refs(rec.get("decisions"), "DEC"):
            if ref not in dec:
                out.append(Problem(here, "dangling-ref",
                                   f"decisions references unknown DEC:{ref}", hard=True))
        for ref in _refs(rec.get("discoveries"), "DSC"):
            if ref not in dsc:
                out.append(Problem(here, "dangling-ref",
                                   f"discoveries references unknown DSC:{ref}", hard=True))

    for key, rec in hnd.items():
        here = path_of("HND", key)
        for ref in _refs(rec.get("workstream"), "WS"):
            if ref not in ws:
                out.append(Problem(here, "dangling-ref",
                                   f"workstream references unknown WS:{ref}", hard=True))
        for ref in _refs(rec.get("decisions"), "DEC"):
            if ref not in dec:
                out.append(Problem(here, "dangling-ref",
                                   f"decisions references unknown DEC:{ref}", hard=True))
        for ref in _refs(rec.get("discoveries"), "DSC"):
            if ref not in dsc:
                out.append(Problem(here, "dangling-ref",
                                   f"discoveries references unknown DSC:{ref}", hard=True))

    graph = {key: _refs(rec.get("depends_on"), "WS") for key, rec in ws.items()}
    cycle = _cycle(graph)
    if cycle:
        # Reported on EVERY member, not just the entry node the DFS happened to start
        # from.  A cycle is a joint property of its members: attributing it to one
        # arbitrary endpoint left the other record reading clean, so a reader who opened
        # the sibling saw nothing wrong and `compile-context` treated two symmetric
        # records asymmetrically — one refused, one compiled.
        rendered = "workstream dependency cycle: " + " -> ".join(f"WS:{n}" for n in cycle)
        for node in dict.fromkeys(cycle):
            out.append(Problem(path_of("WS", node), "workstream-cycle", rendered, hard=True))

    # Supersession must be reciprocated, or provenance silently forks.
    for key, rec in dec.items():
        here = path_of("DEC", key)
        for old in _refs(rec.get("supersedes"), "DEC"):
            if old not in dec:
                out.append(Problem(here, "dangling-ref",
                                   f"supersedes unknown DEC:{old}", hard=True))
                continue
            back = dec[old].get("superseded_by")
            back_key = back.split(":", 1)[1] if isinstance(back, str) and ":" in back else back
            if back_key != key:
                out.append(
                    Problem(path_of("DEC", old), "unreciprocated-supersession",
                            f"DEC:{key} supersedes this record, but its superseded_by is "
                            f"{back!r}", hard=True)
                )

    # The other direction of the same edge, and DELIBERATELY ASYMMETRIC.  A replacement
    # that must EXIST is hard: `superseded_by` evicts this record from every bundle, and
    # evicting it in favour of a record nobody can open loses the reasoning outright.
    # Reciprocity from the replacement's side is only a WARNING, because a one-sided
    # `superseded_by` on the OLD record is how the schema itself documents supersession
    # (decision.schema.yml: "set on the OLD record") — the new record listing `supersedes`
    # is good practice, not a precondition for the old one being retired.
    for prefix, table in (("DEC", dec), ("DSC", dsc)):
        for key, rec in table.items():
            raw = rec.get("superseded_by")
            if raw is None:
                continue
            names, malformed = _citations(raw, prefix)
            if malformed or len(names) != 1:
                continue  # shape is check_decision/check_discovery's rule, already hard
            new = names[0]
            here = path_of(prefix, key)
            if new not in table:
                out.append(
                    Problem(here, "dangling-ref",
                            f"superseded_by names unknown {prefix}:{new} — this record is "
                            f"retired in favour of one that does not exist", hard=True)
                )
                continue
            if prefix == "DEC" and key not in _refs(table[new].get("supersedes"), "DEC"):
                out.append(
                    Problem(here, "one-sided-supersession",
                            f"{prefix}:{new} replaces this record, but does not list it "
                            f"under 'supersedes'", hard=False)
                )

    # Citation counts drive discovery GC.  HANDOFFS COUNT: a discovery cited only by a
    # handoff used to read as uncited and became a 90-day GC candidate, which is the
    # exact opposite of what the citation is for.  SHARED with the compiler through
    # `discovery_citation_counts` — two implementations of "is anything citing this?"
    # would eventually disagree, and the surface that dropped a finding the other still
    # counted would never say so.
    for key, count in discovery_citation_counts(records).items():
        if count:
            continue
        verified = _as_date(dsc[key].get("verified_at"))
        if verified and (_dt.date.today() - verified).days > STALE_DISCOVERY_DAYS:
            age = (_dt.date.today() - verified).days
            out.append(
                Problem(path_of("DSC", key), "uncited-discovery",
                        f"no citations and {age}d old — GC candidate (flagged, not deleted)",
                        hard=False)
            )
    return out


# ---------------------------------------------------------------- store loading


SPECS = (
    ("workstreams", "WS", "WS-", check_workstream),
    ("decisions", "DEC", "DEC-", check_decision),
    ("discoveries", "DSC", "DSC-", check_discovery),
    ("handoffs", "HND", "", check_handoff),
)


class Store:
    """Every parsed record in one place, so validate and status cannot disagree."""

    __slots__ = ("root", "records", "paths", "counts", "problems")

    def __init__(self, root: Path) -> None:
        self.root = root
        self.records: dict[str, dict[str, Any]] = {}
        self.paths: dict[str, Path] = {}
        self.counts = {"workstreams": 0, "decisions": 0, "discoveries": 0, "handoffs": 0}
        self.problems: list[Problem] = []

    def of_type(self, prefix: str) -> dict[str, dict[str, Any]]:
        marker = f"{prefix}/"
        return {k[len(marker):]: v for k, v in self.records.items() if k.startswith(marker)}


def load_store(root: Path, programs: set[str] | None) -> Store:
    """Parse and check every record under ``root``.  Never raises; never writes."""
    store = Store(root)
    for folder, prefix, fileprefix, checker in SPECS:
        directory = root / folder
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            if fileprefix and not path.name.startswith(fileprefix):
                store.problems.append(
                    Problem(path, "bad-filename",
                            f"{folder}/ files must start with '{fileprefix}'", hard=True)
                )
                continue
            try:
                rec, body = parse_record(path)
            except ValueError as exc:
                store.problems.append(Problem(path, "unparseable", str(exc), hard=True))
                continue
            rec["_body"] = body
            store.counts[folder] += 1
            # Handoffs are keyed by filename (<WS-KEY>-<date>), not by a `key` field.
            key = path.stem if prefix == "HND" else rec.get("key")
            if isinstance(key, str) and key:
                ident = f"{prefix}/{key}"
                if ident in store.records:
                    store.problems.append(
                        Problem(path, "duplicate-key",
                                f"key {key!r} already defined at {store.paths[ident]}",
                                hard=True)
                    )
                else:
                    store.records[ident] = rec
                    store.paths[ident] = path
            store.problems.extend(
                checker(rec, path, programs) if checker is check_workstream
                else checker(rec, path)
            )
    store.problems.extend(check_references(store.records, store.paths))
    return store


# ---------------------------------------------------------------- commands


def cmd_validate(args: argparse.Namespace) -> int:
    store_root = Path(args.root) if args.root else _DEFAULT_STORE
    if not store_root.exists():
        # Fail-OPEN: an absent store is a not-yet-adopted repo, not a broken one.
        print(f"::warning title=agentos::no agentos/ store at {store_root} — nothing to validate",
              flush=True)
        return 0

    programs = _load_programs()
    if programs is None:
        print("::warning title=agentos::config/mastermind_programs.yml unreadable — "
              "program keys not validated (fail-open join)", flush=True)

    store = load_store(store_root, programs)
    problems = store.problems
    counts = store.counts

    hard = [p for p in problems if p.hard]
    warn = [p for p in problems if not p.hard]

    for problem in warn:
        if not args.quiet:
            print(f"::warning title=agentos-{problem.rule}::{problem.render(_ROOT)}", flush=True)
    for problem in hard:
        print(f"::error title=agentos-{problem.rule}::{problem.render(_ROOT)}", flush=True)

    total = sum(counts.values())
    summary = (
        f"agentos: {total} records "
        f"({counts['workstreams']} workstreams, {counts['decisions']} decisions, "
        f"{counts['discoveries']} discoveries, {counts['handoffs']} handoffs) — "
        f"{len(hard)} error(s), {len(warn)} warning(s)"
    )
    print(summary, flush=True)
    return 1 if hard else 0


# ------------------------------------------------------- Phase 2: join inputs


class Degraded:
    """The list of inputs this run could NOT read, and what it cost.

    First-class on purpose (I4, brief §0.4): a view that silently omits an input it
    could not read is indistinguishable from a view where nothing is happening, and
    that is the single most dangerous failure available to this artifact.
    """

    __slots__ = ("items",)

    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        if message not in self.items:
            self.items.append(message)

    def __bool__(self) -> bool:
        return bool(self.items)


def load_active_builds(degraded: Degraded, path: Path | None = None) -> dict[str, Any] | None:
    """Read ``active_builds.v1``.  Absent/unreadable is NORMAL — warn and carry on.

    This is the ONLY source of PR state.  There is no `gh` fallback by design: PR
    freshness is inherited from the nightly ABM sweep, because the 5,000/hr REST bucket
    is shared with ``ship_loop_guard.py``, which fails CLOSED when it is exhausted.
    """
    target = path or _ACTIVE_BUILDS
    if not target.exists():
        degraded.add(
            f"{_rel(target)} absent — PR state unknown; wave/PR agreement unchecked "
            "(normal in a sparse worktree; the nightly writes it)"
        )
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        degraded.add(f"{_rel(target)} unreadable ({exc.__class__.__name__}) — PR state unknown")
        return None
    if not isinstance(data, dict) or data.get("schema") != "active_builds.v1":
        degraded.add(f"{_rel(target)} is not active_builds.v1 — PR state unknown")
        return None
    if data.get("open_prs_truncated"):
        degraded.add(
            "active_builds.v1 open_prs is TRUNCATED at the gh --limit cap — some open "
            "PRs are missing from the join, so a wave may read 'unknown' while its PR is open"
        )
    if data.get("merged_truncated"):
        degraded.add(
            "active_builds.v1 merged window is TRUNCATED — a merged PR may read 'unknown'"
        )
    return data


def _strategic_state_from_refs(
    root: Path, degraded: Degraded, label: str
) -> tuple[str, str] | None:
    """``(file text, ref name)`` read out of the sibling's LOCAL refs, or None.

    A checkout parked on a branch that predates the file still CARRIES it on
    `refs/remotes/origin/*` — the CLONE is current, only the working tree is behind
    (measured 2026-08-13: Mastermind's `master` sat 43 commits back, and the brief
    reported unknown P0 activity over a file the clone had all along).  The ref copy is
    already on disk, so reading it stays inside the zero-network contract; the
    alternative is discarding a join over which branch a sibling happens to be on.
    Both misses degrade, and they degrade DIFFERENTLY: a checkout with no readable
    refs is a different fact from a clone that genuinely predates the file.
    """
    walk = _git("for-each-ref", "--sort=-committerdate", "--count=25",
                "--format=%(refname:short)", "refs/heads", "refs/remotes", cwd=root)
    if walk is None:
        degraded.add(
            f"{label} absent — p0 ids unvalidated, p0_active unknown (not found in the "
            "Mastermind working tree, and the checkout has no readable git refs to fall "
            "back to)"
        )
        return None
    candidates: list[str] = []
    for ref in ("origin/HEAD", "origin/master", "origin/main", "master", "main",
                *(line.strip() for line in walk.splitlines())):
        if ref and ref not in candidates:
            candidates.append(ref)
    for ref in candidates:
        text = _git("show", f"{ref}:{_STRATEGIC_STATE_REL.as_posix()}", cwd=root)
        if text is not None:
            degraded.add(
                f"{label} absent from the working tree — read from local ref {ref} "
                "(stale Mastermind checkout; p0_active uses the ref copy)"
            )
            return text, ref
    degraded.add(
        f"{label} absent from the working tree and all local refs — p0 ids unvalidated, "
        "p0_active unknown (this Mastermind clone predates config/strategic_state.yml)"
    )
    return None


def load_p0(degraded: Degraded) -> dict[str, str] | None:
    """Active P0 objective ids from the Mastermind strategic state, or None if absent.

    The state lives in MASTERMIND, never here — a Macro-side copy read by a Mastermind
    runtime is the cross-repo authority hop `duplicate_control_planes` forbids.  Read
    only; nothing in this file decides anything from it.
    """
    root = repo_roots().get("mastermind")
    if root is None:
        degraded.add("Mastermind checkout not found — p0 ids unvalidated, p0_active unknown")
        return None
    target = root / _STRATEGIC_STATE_REL
    # Host paths are never printed into a COMMITTED artifact — the message names the
    # repo-relative file, so the generated view is the same sentence on every machine.
    label = f"mastermind:{_STRATEGIC_STATE_REL.as_posix()}"
    source = ""  # ` (from <ref>)`, so a ref-sourced degrade never reads as the worktree copy
    if target.exists():
        try:
            text = target.read_text(encoding="utf-8")
        except OSError as exc:
            degraded.add(f"{label} unreadable ({exc.__class__.__name__}) — p0 ids unvalidated")
            return None
    else:
        found = _strategic_state_from_refs(root, degraded, label)
        if found is None:
            return None
        text, ref = found
        source = f" (from {ref})"
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        degraded.add(
            f"{label}{source} unreadable ({exc.__class__.__name__}) — p0 ids unvalidated")
        return None
    rows = doc.get("p0") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        degraded.add(f"{label}{source} has no 'p0' list — p0 ids unvalidated")
        return None
    out: dict[str, str] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            out[row["id"]] = str(row.get("status") or "unknown")
    return out


def scan_worktrees(degraded: Degraded, *, deep: bool = False) -> dict[str, Any]:
    """Live checkout occupancy, via ``scripts/audit_stranded_work.py``.

    REUSED, not reimplemented: that module already knows how to read
    ``git worktree list --porcelain`` and how to filter generated output out of a dirty
    status, and it had zero callers.  Only its pure local-git helpers are used — its
    ``main()`` does a ``git fetch``, which is a network call and is never invoked here.

    ``deep`` adds the per-worktree uncommitted-source scan and is OFF by default because
    it costs one ``git status`` per checkout: measured 276 live worktrees on this host,
    most carrying a multi-GB ``data/`` tree, which put a plain ``brief`` past 120s. A CEO
    command nobody waits for is a CEO command nobody runs, so the expensive half is
    opt-in and its absence is stated rather than silently skipped.
    """
    try:
        # The repo-root pin is at module scope (see `_ROOT`), so `scripts` resolves here.
        from scripts import audit_stranded_work as stranded  # local import: optional dep
    except Exception as exc:  # pragma: no cover - import guard
        degraded.add(f"audit_stranded_work unavailable ({exc.__class__.__name__}) — "
                     "worktree occupancy unknown")
        return {"count": 0, "branches": [], "uncommitted": []}
    try:
        branches = stranded.worktree_branches()
    except Exception as exc:
        degraded.add(f"git worktree list failed ({exc.__class__.__name__}) — "
                     "worktree occupancy unknown")
        return {"count": 0, "branches": [], "uncommitted": []}
    uncommitted: list[dict[str, Any]] = []
    if deep:
        for branch in sorted(branches):
            try:
                dirty = stranded.dirty_source_paths(branches[branch])
            except Exception:
                continue
            if dirty:
                uncommitted.append({"branch": branch, "source_files": len(dirty)})
    else:
        degraded.add(
            f"uncommitted-work scan skipped over {len(branches)} worktrees "
            "(one `git status` each) — re-run with --scan-uncommitted for stranded work"
        )
    return {
        "count": len(branches),
        "branches": sorted(branches),
        "uncommitted": uncommitted,
    }


# ------------------------------------------------------- Phase 2: state model


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_ROOT))
    except ValueError:
        return str(path)


def _iso_z(moment: _dt.datetime) -> str:
    return moment.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_moment(text: str) -> _dt.datetime | None:
    """Parse the timestamp shapes the join inputs actually use."""
    cleaned = text.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        moment = _dt.datetime.fromisoformat(cleaned)
    except ValueError:
        try:
            moment = _dt.datetime.strptime(cleaned, "%Y-%m-%d")
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_dt.timezone.utc)
    return moment


def _wave_prs(wave: dict[str, Any]) -> list[int]:
    raw = wave.get("pr")
    if raw is None:
        return []
    values = raw if isinstance(raw, list) else [raw]
    return [int(v) for v in values if isinstance(v, (int, str)) and str(v).strip().isdigit()]


def _pr_index(builds: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
    index: dict[int, dict[str, Any]] = {}
    if not builds:
        return index
    for pr in builds.get("open_prs") or []:
        number = pr.get("number")
        if isinstance(number, int):
            index[number] = {"number": number, "state": "open",
                             "title": pr.get("title", ""),
                             "merged_at": None,
                             "is_draft": bool(pr.get("is_draft")),
                             "merge_state": pr.get("merge_state", "")}
    for pr in builds.get("recent_merged") or []:
        number = pr.get("number")
        if isinstance(number, int):
            index[number] = {"number": number, "state": "merged",
                             "title": pr.get("title", ""),
                             "merged_at": pr.get("merged_at"),
                             "is_draft": False,
                             "merge_state": "MERGED"}
    return index


def _owns_overlap(a: str, b: str) -> bool:
    """True when two globs could plausibly match a common path.

    Deliberately coarse — this feeds a WARNING that says "two workstreams both claim
    this area", and a coarse signal that a human checks beats a precise one nobody wrote.
    """
    if a == b:
        return True
    stem_a = a.split("*", 1)[0].rstrip("/")
    stem_b = b.split("*", 1)[0].rstrip("/")
    if stem_a and stem_b and (stem_a.startswith(stem_b) or stem_b.startswith(stem_a)):
        return True
    return fnmatch.fnmatch(stem_a, b) or fnmatch.fnmatch(stem_b, a)


def build_records(
    store: Store,
    *,
    now: _dt.datetime,
    builds: dict[str, Any] | None,
    p0_status: dict[str, str] | None,
    worktrees: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """The PURE half of ``status`` — records in, records out.

    Everything volatile (wall clock, worktree census, input ages, `degraded`) lives in
    the envelope the caller assembles, NOT here.  That partition is what makes the
    byte-identity test meaningful instead of vacuous: if `generated_at` were inside the
    compared region the test would need a frozen clock to say anything at all, and a
    frozen clock would hide real nondeterminism in the records themselves.
    """
    warnings: list[str] = []
    ws = store.of_type("WS")
    prs = _pr_index(builds)
    merged_days = (builds or {}).get("merged_days")
    merged_truncated = bool((builds or {}).get("merged_truncated"))
    live_branches = set(worktrees.get("branches") or [])

    out: list[dict[str, Any]] = []
    for key in sorted(ws):
        rec = ws[key]
        path = store.paths[f"WS/{key}"]
        created, updated = git_dates(path)
        status = rec.get("status")
        waves = [w for w in (rec.get("waves") or []) if isinstance(w, dict)]
        rollup = {name: 0 for name in sorted(WAVE_STATUS)}
        record_warnings: list[str] = []
        done_ids = {w.get("id") for w in waves if w.get("status") == "done"}

        wave_detail: list[dict[str, Any]] = []
        pr_rows: list[dict[str, Any]] = []
        for wave in waves:
            wstatus = wave.get("status")
            if wstatus in rollup:
                rollup[wstatus] += 1
            wave_prs = _wave_prs(wave)
            done_at: str | None = None
            for number in wave_prs:
                joined = prs.get(number)
                state = joined["state"] if joined else "unknown"
                merged_at = joined["merged_at"] if joined else None
                if state == "merged" and merged_at:
                    done_at = merged_at
                pr_rows.append({
                    "number": number, "state": state, "wave": wave.get("id"),
                    "merged_at": merged_at,
                })
                # THE record-vs-execution join.  Nothing else in the org performs it:
                # ABM knows PR state and never reads the record; the record knows the
                # intent and never reads the PR.  Both directions are warnings.
                if state == "merged" and wstatus not in {"done", "dropped"}:
                    record_warnings.append(
                        f"record_disagrees_with_execution: wave {wave.get('id')} is "
                        f"{wstatus!r} but PR #{number} is merged"
                    )
                elif state == "unknown" and builds is not None and not (
                    merged_truncated and wstatus == "done"
                ):
                    # Suppressed for a DONE wave when the merged window is truncated:
                    # absence carries no information there, and a warning that fires on
                    # every healthy record trains the reader to skip the section.
                    record_warnings.append(
                        f"record_disagrees_with_execution: wave {wave.get('id')} cites "
                        f"PR #{number}, absent from active_builds.v1 (may predate the "
                        f"{merged_days}d merged window — fail-open, verify by hand)"
                    )
            deps = [d for d in (wave.get("depends_on") or []) if isinstance(d, str)]
            wave_detail.append({
                "id": wave.get("id"),
                "title": wave.get("title"),
                "status": wstatus,
                "depends_on": deps,
                # Compatibility field for agent_os_state.v1 readers.  This is a
                # boolean projection of the local dependency graph, never a sort key.
                "deps_satisfied": all(d in done_ids for d in deps),
                "next_action": wave.get("next_action"),
                "prs": wave_prs,
                "done_at": done_at,
                "wait": _wait_row(wave),
            })

        if status == "active" and waves and all(
            w.get("status") in {"done", "dropped"} for w in waves
        ):
            record_warnings.append(
                "status is 'active' but every wave is done/dropped — roll the status forward"
            )
        blocked_by = [b for b in (rec.get("blocked_by") or []) if isinstance(b, str)]
        if status == "blocked" and not blocked_by:
            record_warnings.append("status is 'blocked' with no blocked_by cause")
        if blocked_by and status != "blocked":
            record_warnings.append(f"blocked_by is set but status is {status!r}")

        stale_days: int | None = None
        if updated:
            parsed = _as_date(updated)
            if parsed:
                stale_days = (now.date() - parsed).days
                if status == "active" and stale_days > STALE_WORKSTREAM_DAYS:
                    record_warnings.append(
                        f"active but its record has not been touched in git for {stale_days}d"
                    )

        claim_row: dict[str, Any] | None = None
        claim = rec.get("claim")
        if isinstance(claim, dict):
            expires = _as_date(claim.get("expires"))
            by = str(claim.get("by") or "")
            claim_row = {
                "by": by,
                "at": str(claim.get("at") or ""),
                "expires": str(claim.get("expires") or ""),
                "stale": bool(expires and expires < now.date()),
                # A claim naming a branch with no live worktree is a claim nobody is
                # holding.  This READS occupancy; it never enforces it (I1).
                "worktree_live": by in live_branches,
            }
            if claim_row["stale"]:
                record_warnings.append(f"claim by {by!r} expired {claim_row['expires']}")

        p0 = rec.get("p0")
        p0_active: bool | None = None
        if isinstance(p0, str) and p0:
            if p0_status is None:
                p0_active = None
            elif p0 not in p0_status:
                p0_active = False
                record_warnings.append(
                    f"p0 {p0!r} is not an objective in the Mastermind strategic state"
                )
            else:
                p0_active = p0_status[p0] == "active"

        needs = rec.get("needs_ceo")
        needs_row: dict[str, Any] | None = None
        if isinstance(needs, dict):
            blocked_waves = sum(
                1 for w in waves if w.get("status") in {"todo", "in_progress"}
            )
            needs_row = {
                "question": str(needs.get("question") or "").strip(),
                "options": [str(o).strip() for o in (needs.get("options") or [])],
                "recommendation": str(needs.get("recommendation") or "").strip(),
                "by_when": str(needs.get("by_when") or "") or None,
                "blocks_waves": blocked_waves,
            }

        out.append({
            "key": key,
            "title": str(rec.get("title") or "").strip(),
            "status": status,
            "program": rec.get("program"),
            "p0": p0 if isinstance(p0, str) else None,
            "p0_active": p0_active,
            "owner": rec.get("owner"),
            "class": rec.get("class"),
            "blast_radius": rec.get("blast_radius"),
            "repos": [r for r in (rec.get("repos") or []) if isinstance(r, str)],
            "next_action": str(rec.get("next_action") or "").strip(),
            "created": created,
            "updated": updated,
            "stale_days": stale_days,
            "depends_on": _refs(rec.get("depends_on"), "WS"),
            "blocked_by": blocked_by,
            "waves": rollup,
            "wait": _wait_row(rec),
            "wave_detail": wave_detail,
            "prs": pr_rows,
            "claim": claim_row,
            "needs_ceo": needs_row,
            "collisions": [],
            "warnings": record_warnings,
            "source": _rel(path),
        })

    # owns_paths collisions between workstreams that are both live.
    live = {"proposed", "active", "blocked", "awaiting_ci", "awaiting_review"}
    owns = {
        row["key"]: [g for g in (ws[row["key"]].get("owns_paths") or []) if isinstance(g, str)]
        for row in out if row["status"] in live
    }
    for row in out:
        mine = owns.get(row["key"]) or []
        for other_key in sorted(owns):
            if other_key == row["key"]:
                continue
            shared = sorted({
                a for a in mine for b in owns[other_key] if _owns_overlap(a, b)
            })
            if shared:
                row["collisions"].append({"with": other_key, "paths": shared})

    for row in out:
        for message in row["warnings"]:
            warnings.append(f"WS:{row['key']} — {message}")
    return out, warnings


def compute_readiness(
    records: list[dict[str, Any]], *, degraded: Iterable[str] = (),
    uncertain_workstreams: Iterable[str] = (),
) -> dict[str, Any]:
    """Return the non-ranked dependency envelope consumed by the canonical agenda.

    The record order is identity order, never priority order: workstream key, then the
    workstream record (``wave: null``), then wave id.  Only authored ``depends_on`` edges
    participate.  P0 alignment, unblock counts, claims, next actions, and titles are
    intentionally absent so this payload cannot become a second agenda by accident.
    """
    by_key = {row["key"]: row for row in records}
    uncertain = set(uncertain_workstreams)
    done_workstreams = {
        key for key, row in by_key.items()
        if row["status"] == "done" and key not in uncertain
    }
    items: list[dict[str, Any]] = []

    def _reason_for_workstream(
        key: str, status: Any, unmet: list[str], unavailable: list[str]
    ) -> tuple[str, str, str]:
        if key in uncertain:
            return (
                "unknown", "status_unknown",
                f"Authored readiness source for WS:{key} is ambiguous or invalid.",
            )
        if status == "done":
            return "done", "status_done", "Authored workstream status is done."
        if status == "killed":
            return (
                "done", "status_done",
                "Authored workstream status is killed; it is terminal and not actionable.",
            )
        if status in {"active", "awaiting_ci", "awaiting_review"}:
            return (
                "in_progress", "status_in_progress",
                f"Authored workstream status is {status}.",
            )
        if status in {"blocked", "parked"}:
            return (
                "blocked", "workstream_blocked",
                f"Authored workstream status is {status}.",
            )
        if status == "proposed":
            if unavailable:
                return (
                    "unknown", "status_unknown",
                    f"Declared dependency sources are unavailable: {', '.join(unavailable)}.",
                )
            if unmet:
                return (
                    "blocked", "unmet_dependencies",
                    f"Waiting for declared dependencies: {', '.join(unmet)}.",
                )
            return "ready", "dependencies_satisfied", "All declared dependencies are done."
        return "unknown", "status_unknown", f"Authored workstream status is {status!r}."

    def _reason_for_wave(
        key: str, status: Any, parent_status: Any, unmet: list[str],
        unavailable: list[str],
    ) -> tuple[str, str, str]:
        if key in uncertain:
            return (
                "unknown", "status_unknown",
                f"Authored readiness source for WS:{key} is ambiguous or invalid.",
            )
        if status in {"done", "dropped"}:
            return "done", "status_done", f"Authored wave status is {status}."
        if status in {"in_progress", "awaiting_ci"}:
            return "in_progress", "status_in_progress", f"Authored wave status is {status}."
        if status == "todo":
            if unavailable:
                return (
                    "unknown", "status_unknown",
                    f"Declared dependency sources are unavailable: {', '.join(unavailable)}.",
                )
            if unmet:
                return (
                    "blocked", "unmet_dependencies",
                    f"Waiting for declared dependencies: {', '.join(unmet)}.",
                )
            if parent_status in {"blocked", "parked", "killed"}:
                return (
                    "blocked", "workstream_blocked",
                    f"Parent workstream status is {parent_status}.",
                )
            if parent_status == "done":
                return (
                    "unknown", "status_unknown",
                    "Parent workstream is done while this wave remains todo.",
                )
            if parent_status in {"proposed", "active", "awaiting_ci", "awaiting_review"}:
                return "ready", "dependencies_satisfied", "All declared dependencies are done."
        return "unknown", "status_unknown", f"Authored wave status is {status!r}."

    for row in records:
        key = row["key"]
        ws_dependencies = sorted({f"WS:{dep}" for dep in row["depends_on"]})
        ws_unavailable = sorted(
            dep for dep in ws_dependencies
            if dep.split(":", 1)[1] not in by_key
            or dep.split(":", 1)[1] in uncertain
        )
        graph_unmet = sorted(
            dep for dep in ws_dependencies if dep.split(":", 1)[1] not in done_workstreams
        )
        # Terminal records retain graph provenance but have no remaining action to
        # unblock, so an inherited unfinished edge is not an unmet readiness condition.
        ws_unmet = [] if row["status"] in {"done", "killed"} else graph_unmet
        state, reason_code, reason = _reason_for_workstream(
            key, row["status"], ws_unmet, ws_unavailable
        )
        items.append({
            "workstream": key,
            "wave": None,
            "state": state,
            "reason_code": reason_code,
            "reason": reason,
            "depends_on": ws_dependencies,
            "unmet_dependencies": ws_unmet,
            "source": row["source"],
        })

        done_waves = {
            str(wave["id"])
            for wave in row["wave_detail"]
            if wave["status"] == "done"
        }
        known_waves = {str(wave["id"]) for wave in row["wave_detail"]}
        for wave in row["wave_detail"]:
            local_dependencies = {
                f"WS:{key}#{dep}" for dep in wave["depends_on"]
            }
            dependencies = sorted(set(ws_dependencies) | local_dependencies)
            unavailable = sorted(
                set(ws_unavailable) | {
                    ref for ref in local_dependencies
                    if ref.split("#", 1)[1] not in known_waves
                }
            )
            unmet = sorted(
                set(ws_unmet) | {
                    ref for ref in local_dependencies
                    if ref.split("#", 1)[1] not in done_waves
                }
            )
            if wave["status"] in {"done", "dropped"}:
                unmet = []
            state, reason_code, reason = _reason_for_wave(
                key, wave["status"], row["status"], unmet, unavailable
            )
            items.append({
                "workstream": key,
                "wave": wave["id"],
                "state": state,
                "reason_code": reason_code,
                "reason": reason,
                "depends_on": dependencies,
                "unmet_dependencies": unmet,
                "source": row["source"],
            })

    items.sort(key=lambda item: (
        item["workstream"], item["wave"] is not None, item["wave"] or ""
    ))
    return {
        "schema": READINESS_SCHEMA,
        "records": items,
        "degraded": sorted(set(degraded)),
    }


def readiness_producer_issues(store: Store) -> tuple[list[str], set[str]]:
    """Return degradation receipts and workstream identities whose truth is uncertain.

    PR state, P0 context, and worktree occupancy enrich the parent status/brief but do
    not participate in the dependency graph.  Mirroring their health here would make a
    complete readiness feed look incomplete.  A hard problem attached to a workstream
    file is different: the view either excludes that source or retains one ambiguous
    duplicate, so the affected identity must be explicit in the independently consumed
    envelope.
    """
    authoring_root = (store.root / "workstreams").resolve()
    items: set[str] = set()
    affected: set[str] = set()
    for problem in store.problems:
        if not problem.hard:
            continue
        try:
            problem.path.resolve().relative_to(authoring_root)
        except ValueError:
            continue
        items.add(f"record excluded (malformed): {problem.render(_ROOT)}")
        # A duplicate may live in a differently named copy, so frontmatter is the
        # identity authority.  An unparseable source has no frontmatter truth; its
        # canonical WS filename is the best bounded fallback for dependent records.
        key: str | None = None
        try:
            rec, _body = parse_record(problem.path)
            raw_key = rec.get("key")
            if isinstance(raw_key, str) and raw_key:
                key = raw_key
        except (OSError, ValueError):
            stem = problem.path.stem
            if stem.startswith("WS-") and len(stem) > 3:
                key = stem[3:]
        if key:
            affected.add(key)
    return sorted(items), affected


def build_state(
    store: Store,
    *,
    now: _dt.datetime,
    degraded: Degraded,
    builds: dict[str, Any] | None,
    p0_status: dict[str, str] | None,
    worktrees: dict[str, Any],
) -> dict[str, Any]:
    """Assemble ``agent_os_state.v1`` — envelope plus the pure records section."""
    records, warnings = build_records(
        store, now=now, builds=builds, p0_status=p0_status, worktrees=worktrees
    )
    readiness_issues, uncertain_workstreams = readiness_producer_issues(store)
    for problem in store.problems:
        if not problem.hard:
            warnings.append(problem.render(_ROOT))

    age_hours: float | None = None
    stamp: str | None = None
    if builds:
        stamp = str(builds.get("generated_at") or "")
        moment = _parse_moment(stamp) if stamp else None
        if moment:
            age_hours = round((now - moment).total_seconds() / 3600.0, 1)
            if age_hours > 36:
                degraded.add(
                    f"active_builds.v1 is {age_hours:.0f}h old — PR state predates the "
                    "last nightly sweep"
                )

    return {
        "schema": STATE_SCHEMA,
        "generator": "scripts/agentos.py status",
        # ---- envelope: volatile, excluded from the byte-identity comparison ----
        "generated_at": _iso_z(now),
        "inputs": {
            "workstreams": store.counts["workstreams"],
            "decisions": store.counts["decisions"],
            "discoveries": store.counts["discoveries"],
            "handoffs": store.counts["handoffs"],
            "active_builds": f"{_rel(_ACTIVE_BUILDS)}@{stamp}" if stamp else None,
            "active_builds_age_hours": age_hours,
            "worktrees": worktrees.get("count", 0),
            "uncommitted_worktrees": worktrees.get("uncommitted") or [],
            "degraded": degraded.items,
        },
        # ---- pure function of the authored records + join inputs ----
        "workstreams": records,
        "needs_ceo": [
            # `workstream`, matching blocked/finished/readiness and the documented
            # ceo_brief.v1 envelope.  It emitted `key` here alone, so the one section the
            # CEO acts on was the one whose shape diverged from its own spec.
            {"workstream": row["key"], **row["needs_ceo"], "source": row["source"]}
            for row in records if row["needs_ceo"]
        ],
        "readiness": compute_readiness(
            records,
            # This envelope travels independently to the agenda.  It therefore names
            # defects in its own authored graph, not unrelated parent-view joins.
            degraded=readiness_issues,
            uncertain_workstreams=uncertain_workstreams,
        ),
        "warnings": warnings,
    }


PURE_SECTIONS = ("schema", "generator", "workstreams", "needs_ceo", "warnings")


def pure_section(state: dict[str, Any]) -> dict[str, Any]:
    """The part of the state that must be byte-identical run over run."""
    pure = {name: state[name] for name in PURE_SECTIONS if name in state}
    readiness = state.get("readiness")
    if isinstance(readiness, dict):
        # All three envelope fields are graph-pure: readiness degradation is restricted
        # to invalid workstream authoring and never mirrors volatile auxiliary joins.
        pure["readiness"] = readiness
    return pure


def _dump_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


DO_NOT_EDIT = (
    "<!-- GENERATED — DO NOT EDIT BY HAND. Regenerate with `python3 scripts/agentos.py "
    "status`. Authored truth lives in agentos/; this file is derived (invariant I3). "
    "Advisory only: it reports state and gates nothing (invariant I1). -->"
)


def render_state_markdown(state: dict[str, Any]) -> str:
    """Human mirror of ``agent_os_state.v1`` — same data, same command, no new logic."""
    lines: list[str] = [DO_NOT_EDIT, "", "# Agent OS state", ""]
    inputs = state["inputs"]
    counts: dict[str, int] = {}
    for row in state["workstreams"]:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    rollup = " · ".join(f"{counts[k]} {k}" for k in sorted(counts)) or "no workstreams"
    hours = inputs["active_builds_age_hours"]
    age_cell = "—" if hours is None else f"{hours}h"
    lines += [
        f"Generated: {state['generated_at']}  |  {len(state['workstreams'])} workstreams "
        f"({rollup})",
        "",
        "| Input | Value |",
        "|---|---|",
        f"| active_builds | {inputs['active_builds'] or '_absent_'} |",
        f"| active_builds age | {age_cell} |",
        f"| worktrees | {inputs['worktrees']} |",
        f"| records | {inputs['workstreams']} WS · {inputs['decisions']} DEC · "
        f"{inputs['discoveries']} DSC · {inputs['handoffs']} handoffs |",
        "",
    ]
    if inputs["degraded"]:
        lines += ["## Degraded inputs", ""]
        lines += [f"- {item}" for item in inputs["degraded"]]
        lines.append("")

    lines += ["## Workstreams", "",
              "| Key | Status | Owner | Program | Waves | PRs | Next action |",
              "|---|---|---|---|---|---|---|"]
    for row in state["workstreams"]:
        waves = " ".join(f"{k}:{v}" for k, v in row["waves"].items() if v)
        prs = " ".join(f"#{p['number']}({p['state']})" for p in row["prs"]) or "—"
        lines.append(
            f"| [`WS:{row['key']}`]({_md_link(row['source'])}) | {row['status']} | "
            f"{row['owner']} | {row['program']} | {waves or '—'} | {prs} | "
            f"{_md_cell(row['next_action'])} |"
        )
    lines.append("")

    if state["needs_ceo"]:
        lines += ["## Needs a CEO ruling", ""]
        for item in state["needs_ceo"]:
            when = f" · wanted by {item['by_when']}" if item["by_when"] else ""
            lines.append(
                f"- **WS:{item['workstream']}** — {_md_cell(item['question'])}"
                f" (blocks {item['blocks_waves']} wave(s){when}) — `{item['source']}`"
            )
        lines.append("")

    if state["warnings"]:
        lines += ["## Warnings", ""]
        lines += [f"- {_md_cell(w)}" for w in state["warnings"]]
        lines.append("")
    return "\n".join(lines)


def _md_cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def _md_link(path: str) -> str:
    return "../" + path if not path.startswith("../") else path


def cmd_status(args: argparse.Namespace) -> int:
    """Materialize agent_os_state.v1 + docs/AGENT_OS_STATE.md.  ALWAYS exits 0.

    I1: this writes two files and returns 0.  It has no gate, no dispatch, and no caller
    that reads its output to decide what may run.
    """
    store_root = Path(args.root) if args.root else _DEFAULT_STORE
    degraded = Degraded()
    now = _parse_moment(args.now) if args.now else _dt.datetime.now(_dt.timezone.utc)
    if now is None:
        print(f"::warning title=agentos::--now {args.now!r} unparseable — using wall clock",
              flush=True)
        now = _dt.datetime.now(_dt.timezone.utc)

    if not store_root.exists():
        print(f"::warning title=agentos::no agentos/ store at {store_root} — "
              "nothing to report; existing outputs left untouched", flush=True)
        return 0

    programs = _load_programs()
    store = load_store(store_root, programs)
    hard = [p for p in store.problems if p.hard]
    if hard:
        # Fail-OPEN on the VIEW: a malformed record is `validate`'s business, and it will
        # red the writer's own PR.  Refusing to report here would mean one bad record
        # blanks the whole CEO's picture — the exact silent-omission failure I4 exists
        # for.  The record is skipped from the join and named in `degraded`.
        for problem in hard:
            degraded.add(f"record excluded (malformed): {problem.render(_ROOT)}")
            store.records = {k: v for k, v in store.records.items()
                             if store.paths.get(k) != problem.path}

    builds = load_active_builds(degraded, Path(args.active_builds) if args.active_builds else None)
    p0_status = load_p0(degraded)
    worktrees = scan_worktrees(degraded, deep=args.scan_uncommitted)

    state = build_state(store, now=now, degraded=degraded, builds=builds,
                        p0_status=p0_status, worktrees=worktrees)
    payload = _dump_json(state)
    markdown = render_state_markdown(state)

    if args.dry_run:
        sys.stdout.write(payload)
    else:
        for target, text in ((Path(args.json_out) if args.json_out else _STATE_JSON, payload),
                             (Path(args.md_out) if args.md_out else _STATE_MD, markdown)):
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
            except OSError as exc:
                # Fail-OPEN, and DO NOT touch what is already there.
                print(f"::warning title=agentos::could not write {target} ({exc}) — "
                      "existing output left untouched", flush=True)

    for item in degraded.items:
        print(f"::warning title=agentos-degraded::{item}", flush=True)
    print(
        f"agentos status: {len(state['workstreams'])} workstreams · "
        f"{len(state['needs_ceo'])} needing a ruling · "
        f"{len(state['readiness']['records'])} readiness record(s) · "
        f"{len(state['warnings'])} warning(s) · "
        f"{len(degraded.items)} degraded input(s)",
        flush=True,
    )
    return 0


# -------------------------------------------------------- Phase 2: CEO brief


RULE = "━" * 68
CAP_NEEDS_CEO = 5
CAP_BLOCKED = 5
CAP_FINISHED = 8


def _overflow(out: list[str], total: int, shown: int, noun: str) -> None:
    """Name what a cap dropped.  Silent truncation is the defect this exists to prevent.

    A brief that prints 5 of 7 blocked workstreams and says nothing reads exactly like a
    brief where only 5 are blocked — the CEO cannot tell, and the two dropped items are
    invisible rather than deprioritized.  The architecture forbids this for compiled
    context bundles for the same reason; the brief is held to its own rule.
    """
    if total > shown:
        out.append(f"    … +{total - shown} more {noun} (--full)")


def _recommended_option(options: list[str], recommendation: str) -> str | None:
    """Which option the recommendation designates, or None when it is not unambiguous.

    Marking the wrong option here is the single worst thing this brief can do: the CEO
    acts on the arrow.  A substring test (``option in recommendation``) marks the REJECTED
    option whenever the prose names it to reject it — "Ship now, rejecting Wait for the
    nightly" marks both.  So the rule is deliberately strict: the recommendation must
    OPEN with the option text, and exactly one option may qualify.  Ambiguous prose gets
    no arrow at all, and the reader falls through to the Recommendation block below —
    which is honest, where a confident wrong arrow is not.
    """
    if not recommendation:
        return None

    def _norm(text: str) -> str:
        return " ".join((text or "").split()).rstrip(".").casefold()

    head = _norm(recommendation)
    hits = [opt for opt in options if opt and head.startswith(_norm(opt))]
    return hits[0] if len(hits) == 1 else None


def _since_window(text: str | None, now: _dt.datetime) -> tuple[_dt.datetime, str]:
    """Resolve ``--since`` into ``(cutoff, how_it_was_resolved)``."""
    if text:
        cleaned = text.strip().lower()
        if cleaned == "overnight":
            return now - _dt.timedelta(hours=12), "overnight (12h)"
        match = re.fullmatch(r"(\d+)\s*([hd])", cleaned)
        if match:
            amount = int(match.group(1))
            delta = _dt.timedelta(hours=amount) if match.group(2) == "h" else \
                _dt.timedelta(days=amount)
            return now - delta, f"the last {cleaned}"
        moment = _parse_moment(text)
        if moment:
            return moment, f"{text.strip()}"
        print(f"::warning title=agentos::--since {text!r} unparseable — using 24h", flush=True)
        return now - _dt.timedelta(hours=24), "the last 24h"
    if _BRIEF_MARK.exists():
        try:
            moment = _parse_moment(_BRIEF_MARK.read_text(encoding="utf-8"))
        except OSError:
            moment = None
        if moment:
            return moment, "your last check-in"
    return now - _dt.timedelta(hours=24), "the last 24h (no check-in recorded yet)"


def build_brief(
    state: dict[str, Any], *, now: _dt.datetime, since: _dt.datetime, since_label: str
) -> dict[str, Any]:
    """``ceo_brief.v1`` — a pure projection of ``agent_os_state.v1``.

    One generator, many renderers (P7): the text form and the JSON form are both built
    from this, so a transport added later re-derives none of the logic.
    """
    records = state["workstreams"]
    by_status: dict[str, int] = {}
    for row in records:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1

    finished: list[dict[str, Any]] = []
    for row in records:
        for wave in row["wave_detail"]:
            if wave["status"] != "done":
                continue
            moment = _parse_moment(wave["done_at"]) if wave["done_at"] else None
            if moment is None or moment < since:
                continue
            finished.append({
                "workstream": row["key"], "wave": wave["id"], "title": wave["title"],
                "prs": wave["prs"], "done_at": wave["done_at"], "source": row["source"],
            })
    finished.sort(key=lambda f: (f["done_at"] or "", f["workstream"]), reverse=True)

    blocked = [
        # `record_stale_days`, NOT days-blocked: it is days since the record file was last
        # committed (git_dates), which is all we can derive without an authored
        # `blocked_since` or an -S walk for the transition into `status: blocked`.  Naming it
        # `blocked_days` and ordering "longest blocked first" claimed a measurement nobody
        # took — a record edited yesterday for an unrelated reason read as freshly blocked.
        {"workstream": row["key"], "title": row["title"], "blocked_by": row["blocked_by"],
         "record_stale_days": row["stale_days"], "source": row["source"]}
        for row in records if row["status"] == "blocked"
    ]
    blocked.sort(key=lambda b: (-(b["record_stale_days"] or 0), b["workstream"]))

    needs = sorted(
        state["needs_ceo"],
        key=lambda n: (n["by_when"] or "9999-99-99", -n["blocks_waves"], n["workstream"]),
    )

    claims = [row for row in records if row["claim"]]
    running = {
        "active": by_status.get("active", 0),
        "awaiting_ci": by_status.get("awaiting_ci", 0),
        "awaiting_review": by_status.get("awaiting_review", 0),
        "blocked": by_status.get("blocked", 0),
        "proposed": by_status.get("proposed", 0),
        "open_prs": sum(1 for row in records for pr in row["prs"] if pr["state"] == "open"),
        "stale_claims": sum(1 for row in claims if row["claim"]["stale"]),
        "claims_without_worktree": sum(
            1 for row in claims
            if not row["claim"]["stale"] and not row["claim"]["worktree_live"]
        ),
    }

    return {
        "schema": BRIEF_SCHEMA,
        "generated_at": _iso_z(now),
        "since": _iso_z(since),
        "since_label": since_label,
        "counts": {
            "total": len(records),
            "active": by_status.get("active", 0),
            "awaiting_ci": by_status.get("awaiting_ci", 0),
            "blocked": by_status.get("blocked", 0),
            "done_in_window": len(finished),
        },
        "inputs": {
            "active_builds_age_hours": state["inputs"]["active_builds_age_hours"],
            "worktrees": state["inputs"]["worktrees"],
            "degraded": state["inputs"]["degraded"],
        },
        "needs_ceo": needs,
        "blocked": blocked,
        "finished": finished,
        "running": running,
        "readiness": state["readiness"],
        "warnings": state["warnings"],
    }


def _wrap(text: str, width: int, indent: str) -> list[str]:
    words = str(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(indent + current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(indent + current)
    return lines


def render_brief(brief: dict[str, Any], *, full: bool, state: dict[str, Any]) -> str:
    """The ~15-line CEO view.  Suppression, not summarization (spec §0)."""
    counts = brief["counts"]
    inputs = brief["inputs"]
    out: list[str] = []
    generated = _parse_moment(brief["generated_at"])
    started = _parse_moment(brief["since"])
    hours = ""
    if generated and started:
        hours = f", {int((generated - started).total_seconds() // 3600)}h ago"
    out.append(f"MASTERMIND STATUS — {brief['generated_at'][:16].replace('T', ' ')} UTC")
    out.append(f"since {brief['since_label']} "
               f"({brief['since'][:16].replace('T', ' ')} UTC{hours})")
    out.append("")
    out.append(
        f"  {counts['total']} workstreams:  {counts['active']} active · "
        f"{counts['awaiting_ci']} awaiting CI · {counts['blocked']} blocked · "
        f"{counts['done_in_window']} done this window"
    )
    age = inputs["active_builds_age_hours"]
    age_text = "active_builds MISSING" if age is None else f"active_builds {age:.0f}h old"
    out.append(f"  Inputs: {age_text} · {inputs['worktrees']} worktrees")
    if inputs["degraded"]:
        # Never suppressed, never below the fold: a brief that hides an input it could
        # not read looks exactly like a brief where nothing is happening.
        out.append(f"  ⚠ DEGRADED ({len(inputs['degraded'])}) — this brief is incomplete:")
        for item in inputs["degraded"]:
            out.extend(_wrap(item, 62, "      "))
    out.append("")

    out.append(f"━━ WHAT NEEDS YOU {RULE[:51]}")
    out.append("")
    if not brief["needs_ceo"]:
        out.append(" Nothing needs you.")
    for index, item in enumerate(brief["needs_ceo"][:CAP_NEEDS_CEO], start=1):
        blocks = (f" — {item['blocks_waves']} unfinished wave(s)"
                  if item["blocks_waves"] else "")
        out.append(f" {index}. WS:{item['workstream']}{blocks}")
        out.extend(_wrap(item["question"], 62, "    "))
        marked = _recommended_option(item["options"], item["recommendation"])
        for letter, option in zip("ABCDEFGH", item["options"]):
            mark = "  ← recommended" if option == marked else ""
            out.append(f"      {letter}) {_md_cell(option)}{mark}")
        if item["recommendation"]:
            # Its own block, at the item indent — nested under the last option it reads
            # as that option's rationale, which is the opposite of a recommendation.
            out.append("    Recommendation:")
            out.extend(_wrap(item["recommendation"], 58, "      "))
        if item["by_when"]:
            out.append(f"    Wanted by {item['by_when']}")
        out.append(f"    → {item['source']}")
    overflow = len(brief["needs_ceo"]) - CAP_NEEDS_CEO
    if overflow > 0:
        out.append(f"    … +{overflow} more awaiting a ruling (--full)")
    out.append("")

    if brief["blocked"]:
        out.append(f"━━ BLOCKED {RULE[:57]}")
        out.append("")
        cap = len(brief["blocked"]) if full else CAP_BLOCKED
        for item in brief["blocked"][:cap]:
            out.append(f" • WS:{item['workstream']} — {item['title']}")
            for cause in item["blocked_by"]:
                out.extend(_wrap(cause, 62, "   "))
        _overflow(out, len(brief["blocked"]), cap, "blocked")
        out.append("")

    if brief["finished"]:
        out.append(f"━━ FINISHED ({brief['since_label']}) {RULE[:44]}")
        out.append("")
        cap = len(brief["finished"]) if full else CAP_FINISHED
        for item in brief["finished"][:cap]:
            prs = " ".join(f"#{n}" for n in item["prs"]) or "—"
            out.append(f" ✅ WS:{item['workstream']} {item['wave']} — "
                       f"{_md_cell(item['title'] or '')}  {prs}")
        _overflow(out, len(brief["finished"]), cap, "finished")
        out.append("")

    running = brief["running"]
    out.append(f"━━ RUNNING (no action needed) {RULE[:39]}")
    out.append("")
    out.append(
        f" {running['active']} active · {running['awaiting_ci']} awaiting CI · "
        f"{running['awaiting_review']} awaiting review · {running['proposed']} proposed."
    )
    out.append(
        f" {running['open_prs']} open PR(s) cited by a wave. "
        f"{running['stale_claims']} stale claim(s); "
        f"{running['claims_without_worktree']} claim(s) with no live worktree."
    )
    out.append("                                     → agentos.py brief --full")
    out.append("")

    if full:
        out.append(f"━━ FULL DETAIL {RULE[:53]}")
        out.append("")
        out.append("Claim notes are ADVISORY — an author's note in git, not live "
                   "activity. Live worker/job state is the Executive OS runtime "
                   "(control_plane/); occupancy evidence is `git worktree list`.")
        out.append("")
        for row in state["workstreams"]:
            claim = row["claim"]
            claim_text = "no claim note"
            if claim:
                claim_text = f"claim note: {claim['by']}"
                if claim["stale"]:
                    claim_text += " (EXPIRED)"
                elif not claim["worktree_live"]:
                    claim_text += " (no live worktree)"
            out.append(
                f" {row['key']:<28} {row['status']:<16} {row['owner']:<12} {claim_text}"
            )
            out.extend(_wrap(f"next: {row['next_action']}", 60, "      "))
            for collision in row["collisions"]:
                out.extend(_wrap(
                    f"collision with WS:{collision['with']} on "
                    f"{', '.join(collision['paths'])}", 60, "      ⚠ "))
        out.append("")
        if brief["warnings"]:
            out.append(" Hygiene warnings:")
            for warning in brief["warnings"]:
                out.extend(_wrap(warning, 62, "   - "))
            out.append("")
    elif brief["warnings"]:
        out.append(f" {len(brief['warnings'])} hygiene warning(s) — agentos.py brief --full")
        out.append("")
    return "\n".join(out) + "\n"


def cmd_brief(args: argparse.Namespace) -> int:
    """The CEO view.  ALWAYS exits 0 — see the spec's §6 failure table."""
    store_root = Path(args.root) if args.root else _DEFAULT_STORE
    degraded = Degraded()
    now = _parse_moment(args.now) if args.now else _dt.datetime.now(_dt.timezone.utc)
    if now is None:
        now = _dt.datetime.now(_dt.timezone.utc)

    if not store_root.exists():
        print(f"::warning title=agentos::no agentos/ store at {store_root} — no brief",
              flush=True)
        return 0

    store = load_store(store_root, _load_programs())
    for problem in [p for p in store.problems if p.hard]:
        degraded.add(f"record excluded (malformed): {problem.render(_ROOT)}")
        store.records = {k: v for k, v in store.records.items()
                         if store.paths.get(k) != problem.path}

    builds = load_active_builds(degraded, Path(args.active_builds) if args.active_builds else None)
    state = build_state(store, now=now, degraded=degraded, builds=builds,
                        p0_status=load_p0(degraded),
                        worktrees=scan_worktrees(degraded, deep=args.scan_uncommitted))

    since, since_label = _since_window(args.since, now)
    brief = build_brief(state, now=now, since=since, since_label=since_label)

    if args.json:
        sys.stdout.write(_dump_json(brief))
    else:
        sys.stdout.write(render_brief(brief, full=args.full, state=state))

    if not args.no_remember:
        try:
            _BRIEF_MARK.parent.mkdir(parents=True, exist_ok=True)
            _BRIEF_MARK.write_text(_iso_z(now) + "\n", encoding="utf-8")
        except OSError:
            pass  # a check-in marker that cannot be written is not a reason to fail
    return 0


# ================================================== Phase 3: context compilation
#
# `compile-context` answers ONE question — "what does a session picking up this work
# need to know?" — and answers it by WALKING the record graph, never by guessing.  It
# reads, resolves, filters, ranks, compiles and cites.  It cannot schedule, assign,
# lease, gate, arm, or mutate anything (I1), and it writes NOTHING: stdout only.  The
# exit code carries schema truth, never work state — 1 only when a caller NAMES a
# workstream that is unknown or malformed (fail-closed on schema, I4); a missing join,
# an unresolvable free-text task, and an ambiguous one all exit 0 with the reason
# printed, because degrading honestly is the whole point of a context bundle.
#
# RETRIEVAL IS BORROWED, NOT REBUILT (architecture §8; plan §Phase 3 explicit non-goal).
# Free text goes through `engine.context_index.packet.build_packet` — the same index
# `scripts/context_index_query.py search` uses — and its hits only ever VOTE for a
# workstream.  Nothing a search returns becomes bundle CONTENT; content comes from the
# graph walk alone.  That is what makes "records from other programs are excluded"
# structural rather than a relevance threshold nobody can audit, and it is why there is
# no vector store, no embedding, and no second scorer here.
#
# EXCLUSION IS BY FIELD, NOT BY RELEVANCE.  A superseded decision, an expired discovery,
# an older handoff and a malformed record are dropped because a field says so, and each
# one is NAMED in `excluded` with the reason.  A bundle that silently omits is
# indistinguishable from a bundle where the thing never existed — the same failure the
# CEO brief's overflow line exists to prevent, one tier up.

BUNDLE_SCHEMA = "context_bundle.v1"
BUNDLE_BUDGET_DEFAULT = 8000      # architecture §8: "capped (default ~8k tokens)"
BUNDLE_BUDGET_MIN = 500           # a floor, so --budget 0 cannot render an empty bundle
BUNDLE_CHARS_PER_TOKEN = 4        # packet.py's convention, mirrored not imported
SEARCH_MAX_RESULTS = 20           # mirrors context_index_query.py `search`

_KILL_REGISTRY = _ROOT / "config" / "compiled_kill_registry.yml"
_CONTEXT_INDEX_ENV = "MACRO_CONTEXT_INDEX_DIR"
_CONTEXT_INDEX_DIR = _ROOT / ".context-index"
_CONTEXT_INDEX_CONFIG = _ROOT / "config" / "context_index.yml"
_CONTEXT_INDEX_CONFIG_REL = "config/context_index.yml"
_MACRO_PROJECT = "macro-dashboard"
_MACRO_DB = "shared.sqlite"
_DNR_SOURCE = "research/DO_NOT_REBUILD.md"
_PROGRAMS_REL = "config/mastermind_programs.yml"
# Record repo key -> the project this repo is registered as in the index config.
_INDEX_PROJECTS = {
    "macro": _MACRO_PROJECT, "terminal": "terminal", "mastermind": "mastermind",
}
POINTER_AUTHORITY_DEFAULT = "A3"

EXCERPT_WORKSTREAM_BODY = 700
EXCERPT_DECISION = 1200
EXCERPT_DISCOVERY = 700
EXCERPT_HANDOFF = 1600
# Landmines and do_not_redo lines are one-liners BY CONVENTION, not by rule, and the
# always-include set does not check.  A 2,280-char entry rendered whole used to be the
# only unbounded thing in a bundle that advertises itself as bounded; capped, its head
# still renders and `_clip`'s ellipsis says it was cut.  The resulting overrun, if any,
# is NAMED in `degraded` — see the packer.
EXCERPT_CONSTRAINT = 400

DNR_RE = re.compile(r"DNR:([A-Z0-9][A-Z0-9-]*)")
WS_MENTION_RE = re.compile(r"\bWS[-:]([A-Z0-9][A-Z0-9-]*)\b")
HANDOFF_DATE_RE = re.compile(r"-(\d{4}-\d{2}-\d{2})$")

# Presentation order IS authority order, and the framings are the contract (WP-E): a
# receiving session must be able to tell, without reading the architecture, that a
# discovery is evidence and a DNR row is law.  A bundle that lists them as peers is how
# an LLM ends up "deciding" a kill row is outdated.
SECTIONS: tuple[tuple[str, str, str], ...] = (
    (
        "higher_law",
        "HIGHER LAW — outranks every Agent OS record below",
        "DNR rows, the company P0 objective, and the owning program row. Nothing in "
        "this bundle may be read as overriding these.",
    ),
    (
        "workstream",
        "WORKSTREAM STATE (authoritative for state, not for permission)",
        "What the work is and where it stands. Agent OS records work; it never decides "
        "whether work may run (invariant I1).",
    ),
    (
        "decisions",
        "DECISIONS (institutional reasoning — do not override higher law)",
        "Current decisions only. Superseded records are named under EXCLUDED with the "
        "key that replaced them; they are never co-equal here.",
    ),
    (
        "discoveries",
        "DISCOVERIES (evidence, not policy)",
        "Fresh findings only. Expired, superseded, and uncited-and-stale discoveries "
        "are excluded by field, not by relevance.",
    ),
    (
        "handoff",
        "LATEST HANDOFF (transfer state, not strategy)",
        "Where the last session stopped. Only the latest survives — older handoffs are "
        "excluded rather than merged into a composite nobody wrote.",
    ),
    (
        "artifacts",
        "ARTIFACTS (pointers — read the primary source)",
        "Paths only. A record points at prose; it never absorbs it.",
    ),
)

# Packing priority, highest first.  `workstream_block` is the "never split the top
# result" analog from packet._pack_results: without it the bundle can answer nothing.
PACK_ORDER = (
    "workstream_block", "higher_law", "handoff", "decisions",
    "discoveries", "dependency", "artifacts",
)
_PACK_SECTION = {
    "workstream_block": "workstream",
    "dependency": "workstream",
    "higher_law": "higher_law",
    "handoff": "handoff",
    "decisions": "decisions",
    "discoveries": "discoveries",
    "artifacts": "artifacts",
}


def _estimate_tokens(text: str) -> int:
    """Chars/4, the same conservative ratio packet.py uses.

    Deliberately a local four-liner rather than an import: ``--workstream`` mode must
    never touch ``engine/``, and a token estimator is not worth coupling the knowledge
    plane to the retrieval package for.
    """
    return max(1, len(text) // BUNDLE_CHARS_PER_TOKEN)


def _flat(value: Any) -> str:
    """Collapse an authored YAML value to one readable line, deterministically."""
    if isinstance(value, dict):
        return "; ".join(f"{k}={_flat(value[k])}" for k in sorted(value))
    # A `!!set` is legal YAML and `safe_load` returns a real ``set``, which the list
    # branch below does not catch.  Falling through to ``str(value)`` printed Python's
    # set repr in PER-PROCESS hash order, so two runs of the same command over the same
    # store rendered different bytes — the one wobble the determinism guarantee cannot
    # absorb, because it is invisible until someone diffs two bundles.
    if isinstance(value, (set, frozenset)):
        return " | ".join(_flat(item) for item in sorted(value, key=str))
    if isinstance(value, list):
        return " | ".join(_flat(item) for item in value)
    return " ".join(str(value).split())


def _clip(text: str, limit: int) -> str:
    """Cap an excerpt and SAY that it was capped — a silent cut reads as the whole."""
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)].rstrip() + "…"


def _fields(rec: dict[str, Any], fields: tuple[tuple[str, str], ...]) -> str:
    """Render ``(label, field)`` pairs that are present, in the given order."""
    lines: list[str] = []
    for label, name in fields:
        value = rec.get(name)
        if value is None or (isinstance(value, (str, list, dict)) and len(value) == 0):
            continue
        lines.append(f"{label}: {_flat(value)}")
    return "\n".join(lines)


def _bundle_item(
    *, kind: str, key: str | None, path: str, locator: str, authority_class: str,
    status: str, updated: str | None, excerpt: str, why: str,
) -> dict[str, Any]:
    """One cited line of testimony.  Every field here exists so the reader can OPEN it."""
    return {
        "kind": kind,
        "key": key,
        "path": path,
        "locator": locator,
        "authority_class": authority_class,
        "status": status,
        "updated": updated,
        "excerpt": excerpt,
        "why_included": why,
    }


def _glob_match(pattern: str, path: str) -> bool:
    """``pathlib``-style glob match: ``*`` never crosses ``/``; ``**`` spans any depth.

    ``fnmatch`` alone is wrong here: its ``*`` matches ``/`` too, so ``config/*.yml``
    would claim ``config/nested/deep.yml`` — a file the index does NOT put in that source
    — and the pointer would carry a rank the corpus never gave it.  Segment-wise, so the
    semantics are the ones ``Path.glob`` (and therefore the index builder) uses.
    """
    return _glob_segments(pattern.split("/"), path.split("/"))


def _glob_segments(pattern: list[str], parts: list[str]) -> bool:
    if not pattern:
        return not parts
    head, rest = pattern[0], pattern[1:]
    if head == "**":
        return any(_glob_segments(rest, parts[index:]) for index in range(len(parts) + 1))
    if not parts:
        return False
    return fnmatch.fnmatchcase(parts[0], head) and _glob_segments(rest, parts[1:])


# Parsed ONCE per process: `(projects, error)`.  `None` until first read.
_INDEX_CONFIG_CACHE: tuple[dict[str, dict[str, list[Any]]], str | None] | None = None


def _index_config() -> tuple[dict[str, dict[str, list[Any]]], str | None]:
    """``config/context_index.yml`` reduced to ``{project: {sources, deny}}``.

    Plain ``yaml.safe_load``, never an ``engine`` import — ``--workstream`` mode must run
    in a checkout where ``engine/`` was never checked out (see ``_default_search``).
    Cached for the process: a bundle asks this once per artifact, and re-reading a 420-line
    config per pointer is pure waste.
    """
    global _INDEX_CONFIG_CACHE
    if _INDEX_CONFIG_CACHE is not None:
        return _INDEX_CONFIG_CACHE
    projects: dict[str, dict[str, list[Any]]] = {}
    error: str | None = None
    try:
        doc = yaml.safe_load(_CONTEXT_INDEX_CONFIG.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        doc = None
        error = f"{_CONTEXT_INDEX_CONFIG_REL} unreadable ({exc.__class__.__name__})"
    raw = doc.get("projects") if isinstance(doc, dict) else None
    if error is None and not isinstance(raw, dict):
        error = f"{_CONTEXT_INDEX_CONFIG_REL} has no 'projects' mapping"
    for name, spec in (raw or {}).items():
        if not isinstance(spec, dict):
            continue
        sources: list[tuple[str, str]] = []
        for source in spec.get("sources") or []:
            if not isinstance(source, dict):
                continue
            klass = source.get("authority_class")
            for root in source.get("roots") or []:
                if isinstance(root, str) and isinstance(klass, str):
                    sources.append((root, klass))
        deny = [row for row in (spec.get("deny") or []) if isinstance(row, str)]
        projects[str(name)] = {"sources": sources, "deny": deny}
    _INDEX_CONFIG_CACHE = (projects, error)
    return _INDEX_CONFIG_CACHE


def _pointer_authority(repo_key: str, path: str, degraded: Degraded) -> str:
    """Authority class of a pointed-at file, RESOLVED FROM the index config.

    Authority is the corpus registration's to give, and three hardcoded suffix rules gave
    a different answer from the file that owns the question: `research/DO_NOT_REBUILD.md`
    rendered as A3 as an artifact pointer while the SAME bundle carried its rows as A1
    `dnr` items, `CLAUDE.md` was demoted A0 -> A3, and a Macro-shaped rule was applied to
    Terminal and Mastermind paths that the config ranks under their own source lists.

    First matching source WINS, in list order — the same first-source-wins shape the
    index's own discovery dedup uses, and the reason `research/DO_NOT_REBUILD.md` (A1,
    listed early) does not fall through to `repo-research` (A3, listed late).  A denied
    path is not in the corpus at all, so it gets the neutral default rather than the rank
    of a source that never indexed it.  Fail-OPEN to the default with a `degraded` line:
    an unreadable config is a join failure (I4), never a reason to refuse a pointer.
    """
    projects, error = _index_config()
    if error:
        degraded.add(f"{error} — pointer authority defaulted to {POINTER_AUTHORITY_DEFAULT}")
        return POINTER_AUTHORITY_DEFAULT
    project = _INDEX_PROJECTS.get(repo_key)
    spec = projects.get(project or "")
    if spec is None:
        degraded.add(
            f"{_CONTEXT_INDEX_CONFIG_REL} has no project for repo {repo_key!r} — "
            f"pointer authority defaulted to {POINTER_AUTHORITY_DEFAULT}"
        )
        return POINTER_AUTHORITY_DEFAULT
    if any(_glob_match(rule, path) for rule in spec["deny"]):
        return POINTER_AUTHORITY_DEFAULT
    for root, klass in spec["sources"]:
        if _glob_match(root, path):
            return klass
    return POINTER_AUTHORITY_DEFAULT


def _glob_entry(entry: str, rec: dict[str, Any]) -> tuple[str, str] | None:
    """``(repo, glob)`` for an ``affects``/``scope`` entry that is a path glob, else None.

    Both schemas declare path globs as first-class — decision.schema.yml `affects`:
    "WS:<KEY>, program keys, or path globs"; discovery.schema.yml `scope`: "repos,
    programs, or path globs" — and the walk used to read only the first two forms, so a
    decision that declared its blast radius the way the schema invites was silently
    dropped by the compiler that exists to surface it.

    A `PREFIX:KEY` citation is not a glob.  A `repo:path` prefix IS one, resolved against
    THAT repo, because a Terminal path and a Macro path can spell the same string and mean
    different files.  Bare repo names are stripped by the caller BEFORE this and that
    strip is load-bearing: `_owns_overlap` is prefix-coarse, so the entry `terminal` would
    overlap `terminal/components/**` and re-attach the repo-wide scope the walk refuses.
    """
    text = (entry or "").strip()
    if not text:
        return None
    if ":" in text and text.split(":", 1)[0] not in REPOS:
        return None
    return _resolve_path(text, rec)


def _owned_globs(rec: dict[str, Any]) -> list[tuple[str, str]]:
    """The target's ``owns_paths``, resolved to ``(repo, glob)`` in authored order."""
    resolved: list[tuple[str, str]] = []
    for entry in rec.get("owns_paths") or []:
        if not isinstance(entry, str) or not entry.strip():
            continue
        pair = _resolve_path(entry.strip(), rec)
        if pair is not None:
            resolved.append(pair)
    return resolved


def _owned_overlap(entry: str, source: dict[str, Any], owned: list[tuple[str, str]]) -> str | None:
    """The first ``owns_paths`` glob this ``affects``/``scope`` entry overlaps, or None."""
    pair = _glob_entry(entry, source)
    if pair is None:
        return None
    repo, glob = pair
    for owns_repo, owns_glob in owned:
        if owns_repo == repo and _owns_overlap(glob, owns_glob):
            return owns_glob
    return None


def _supersession(
    rec: dict[str, Any], prefix: str, known: dict[str, dict[str, Any]]
) -> tuple[str | None, Any]:
    """``(replacement_key, raw)`` — evict ONLY on a citation that is shaped AND resolves.

    ``superseded_by`` is the one field that deletes a live record from every bundle, and
    it used to be read by TRUTHINESS: ``"no"`` evicted a current decision, ``false``,
    ``0`` and ``""`` did not, and a citation naming a record nobody can open evicted just
    the same.  Eviction now requires exactly one well-shaped citation that RESOLVES in the
    store; every other present value returns ``(None, raw)`` so the caller keeps the
    record and says why.  Losing the reasoning is the expensive direction — a retained
    record with a loud note is recoverable, a silently deleted one is not.
    """
    raw = rec.get("superseded_by")
    if raw is None:
        return None, None
    keys, malformed = _citations(raw, prefix)
    if len(keys) == 1 and not malformed and keys[0] in known:
        return keys[0], raw
    return None, raw


def _item_cost(item: dict[str, Any]) -> int:
    """What one bundle item costs a READER — the whole item, not just its excerpt.

    Measured: costing `excerpt` alone under-reported the JSON payload by 1.9x-6.5x,
    because every item also ships its path, locator, why_included, kind, key, status and
    authority_class — the fields that make it citable, which is most of a short item.  A
    budget that only prices the prose is a budget the caller cannot use to size a context
    window.  `_seq` is the packer's internal ordering handle and is stripped before the
    bundle is emitted, so it must not be priced.
    """
    payload = {name: value for name, value in item.items() if name != "_seq"}
    return _estimate_tokens(json.dumps(payload, ensure_ascii=False))


def _repo_sha() -> str:
    """Local HEAD.  Reuses ``_git`` — no new subprocess site, no network."""
    return (_git("rev-parse", "HEAD") or "").strip()


def _normalize_ws_key(raw: str) -> str:
    """``WS:KEY``/``WS-KEY``/``KEY`` all name the same record."""
    text = (raw or "").strip()
    for prefix in ("WS:", "WS-"):
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def discovery_citation_counts(records: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Inbound ``DSC:`` citations per discovery, from every WS/DEC/HND in the store.

    FACTORED, not reimplemented.  ``check_references`` uses this to flag a 90-day GC
    candidate and the compiler uses it to decide whether a discovery is still fresh; two
    independent implementations of "is anything citing this?" would eventually disagree,
    and the disagreement would be invisible — one surface would drop a finding the other
    still flagged as live.  HANDOFFS COUNT, which is the non-obvious half: a discovery
    whose only reader is a handoff is cited, not orphaned.
    """
    dsc = sorted(k[4:] for k in records if k.startswith("DSC/"))
    counts = {key: 0 for key in dsc}
    for ident, rec in records.items():
        if not ident.startswith(("WS/", "DEC/", "HND/")):
            continue
        for ref in _refs(rec.get("discoveries"), "DSC"):
            if ref in counts:
                counts[ref] += 1
    return counts


# ---------------------------------------------------- Phase 3: target resolution


def _default_search(query: str) -> dict[str, Any] | None:
    """Query the existing context index.  ``None`` when there is no index to query.

    Wired exactly as ``context_index_query.py search`` wires it — same db dir, same
    project map, same mode — because a compiler that retrieved differently from the CLI
    would answer differently from the CLI, and nobody would know which was right.  The
    import is LAZY on purpose: ``--workstream`` mode must be able to run in a checkout
    where ``engine/`` is not even present.
    """
    raw = os.environ.get(_CONTEXT_INDEX_ENV, "").strip()
    db_dir = Path(raw) if raw else _CONTEXT_INDEX_DIR
    if not (db_dir / _MACRO_DB).exists():
        return None
    from engine.context_index.packet import build_packet  # local: never on the WS path

    return build_packet(
        query=query,
        db_dir=db_dir,
        project_db_map={_MACRO_PROJECT: _MACRO_DB},
        repo_root_map={_MACRO_PROJECT: _ROOT},
        mode="research",
        max_results=SEARCH_MAX_RESULTS,
    )


def _search_packet(
    query: str,
    search_fn: Callable[[str], dict[str, Any] | None] | None,
    degraded: Degraded,
) -> dict[str, Any] | None:
    """Run the retrieval seam and surface everything it could not promise."""
    fn = search_fn or _default_search
    try:
        packet = fn(query)
    except Exception as exc:  # fail-OPEN: retrieval is a join, not a schema (I4)
        degraded.add(
            f"context index query failed ({exc.__class__.__name__}) — "
            "context index unavailable — pass --workstream"
        )
        return None
    if not isinstance(packet, dict):
        return None
    if packet.get("index_stale"):
        # packet.py's first absolute rule: index_stale must be VISIBLE.  A bundle
        # compiled off a stale index can miss a record written this morning.
        degraded.add(
            "context index is STALE (indexed sha != repo HEAD) — a record written since "
            "the last build is not retrievable; rebuild with scripts/context_index_build.py"
        )
    if packet.get("no_answer_reason"):
        degraded.add(f"context index returned no answer: {packet['no_answer_reason']}")
    return packet


def _vote_for_paths(
    packet: dict[str, Any], store: Store
) -> dict[str, int]:
    """Map search hits onto workstream votes.  INTEGER weights, deterministic order.

    A retrieved path votes for the workstreams it BELONGS to, resolved through the same
    citation graph the walk uses: a decision votes for every workstream that cites it and
    every workstream it declares it affects; a discovery for its citers and its declared
    scope; a handoff for its workstream; any other path for the workstreams that own or
    cite it.  Ranks, never float scores — a fused score copied into a second ranker is a
    number that looks meaningful and is not comparable across queries.
    """
    ws = store.of_type("WS")
    dec = store.of_type("DEC")
    dsc = store.of_type("DSC")
    hnd = store.of_type("HND")

    cite_dec: dict[str, set[str]] = {}
    cite_dsc: dict[str, set[str]] = {}
    for key in sorted(ws):
        for ref in _refs(ws[key].get("decisions"), "DEC"):
            cite_dec.setdefault(ref, set()).add(key)
        for ref in _refs(ws[key].get("discoveries"), "DSC"):
            cite_dsc.setdefault(ref, set()).add(key)

    def owners(path: str) -> list[str]:
        name = path.rsplit("/", 1)[-1]
        if not name.endswith(".md"):
            name = ""
        stem = name[:-3] if name else ""
        if path.startswith("agentos/workstreams/") and stem.startswith("WS-"):
            key = stem[3:]
            return [key] if key in ws else []
        if path.startswith("agentos/decisions/") and stem.startswith("DEC-"):
            key = stem[4:]
            hits = set(cite_dec.get(key, ()))
            rec = dec.get(key)
            if rec:
                hits |= {k for k in _refs(rec.get("affects"), "WS") if k in ws}
            return sorted(hits)
        if path.startswith("agentos/discoveries/") and stem.startswith("DSC-"):
            key = stem[4:]
            hits = set(cite_dsc.get(key, ()))
            rec = dsc.get(key)
            if rec:
                hits |= {k for k in _refs(rec.get("scope"), "WS") if k in ws}
            return sorted(hits)
        if path.startswith("agentos/handoffs/") and stem:
            rec = hnd.get(stem)
            keys = _refs(rec.get("workstream"), "WS") if rec else []
            if not keys:
                match = HANDOFF_DATE_RE.search(stem)
                if match:
                    keys = [stem[: match.start()]]
            return sorted({k for k in keys if k in ws})
        hits: set[str] = set()
        for key in sorted(ws):
            rec = ws[key]
            for entry in rec.get("artifacts") or []:
                if isinstance(entry, str):
                    resolved = _resolve_path(entry, rec)
                    if resolved and resolved[0] == "macro" and resolved[1] == path:
                        hits.add(key)
            for entry in rec.get("owns_paths") or []:
                if isinstance(entry, str):
                    resolved = _resolve_path(entry, rec)
                    if resolved and resolved[0] == "macro" and fnmatch.fnmatch(
                        path, resolved[1]
                    ):
                        hits.add(key)
        return sorted(hits)

    votes: dict[str, int] = {}
    for index, result in enumerate(packet.get("results") or []):
        weight = SEARCH_MAX_RESULTS - index
        if weight <= 0:
            break
        path = str(result.get("path") or "")
        if not path:
            continue
        for key in owners(path):
            votes[key] = votes.get(key, 0) + weight
    return votes


def _candidate_rows(
    ws: dict[str, dict[str, Any]], keys: Iterable[str], votes: dict[str, int], why: str
) -> list[dict[str, Any]]:
    return [
        {
            "key": f"WS:{key}",
            "title": _flat(ws[key].get("title")),
            "score": votes.get(key, 0),
            "why": why,
        }
        for key in keys
    ]


def _resolve_target(
    store: Store,
    *,
    workstream: str | None,
    task: str | None,
    search_fn: Callable[[str], dict[str, Any] | None] | None,
    degraded: Degraded,
) -> dict[str, Any]:
    """Which workstream is this about?  Degrade honestly rather than guess.

    Four outcomes, and the last two are FEATURES: `explicit` and `cited-key` are exact,
    `search` is a decisive vote, `ambiguous` means two plausible answers and the caller
    must say which — a compiler that picked one would hand a session a confident bundle
    about the wrong work, which is worse than no bundle at all.
    """
    ws = store.of_type("WS")
    everything = _candidate_rows(
        ws, sorted(ws), {}, "no workstream could be resolved — every one is a candidate"
    )

    if workstream is not None:
        key = _normalize_ws_key(workstream)
        if key in ws:
            return {"key": key, "resolution": "explicit", "candidates": [],
                    "no_answer_reason": None}
        return {"key": None, "resolution": "explicit", "candidates": everything,
                "no_answer_reason": f"unknown workstream WS:{key}"}

    if not ws:
        # Nothing to resolve AGAINST.  Short-circuited before retrieval on purpose: a
        # search whose every hit must then map onto an empty workstream table can only
        # return "unresolved", so running it spends a query to reach a known answer.
        return {"key": None, "resolution": "unresolved", "candidates": [],
                "no_answer_reason": "the record store holds no workstreams — there is "
                                    "nothing to compile context from"}

    text = task or ""
    cited = sorted({m for m in WS_MENTION_RE.findall(text) if m in ws})
    if len(cited) == 1:
        return {"key": cited[0], "resolution": "cited-key", "candidates": [],
                "no_answer_reason": None}
    if len(cited) > 1:
        named = ", ".join(f"WS:{k}" for k in cited)
        return {
            "key": None, "resolution": "ambiguous",
            "candidates": _candidate_rows(ws, cited, {}, "named by key in the task text"),
            "no_answer_reason": f"the task text names {named} — pick one with --workstream",
        }

    packet = _search_packet(text, search_fn, degraded)
    if packet is None:
        degraded.add("context index unavailable — pass --workstream")
        return {"key": None, "resolution": "unresolved", "candidates": everything,
                "no_answer_reason": "context index unavailable — no workstream could be "
                                    "resolved from free text; pass --workstream"}

    votes = _vote_for_paths(packet, store)
    if not votes:
        return {"key": None, "resolution": "unresolved", "candidates": everything,
                "no_answer_reason": "no search result maps to a workstream — pass "
                                    "--workstream"}
    ranked = sorted(votes.items(), key=lambda item: (-item[1], item[0]))
    if len(ranked) == 1 or ranked[0][1] >= 2 * ranked[1][1]:
        return {"key": ranked[0][0], "resolution": "search", "candidates": [],
                "no_answer_reason": None}
    top, second = ranked[0], ranked[1]
    return {
        "key": None,
        "resolution": "ambiguous",
        "candidates": _candidate_rows(
            ws, [k for k, _ in ranked], votes, "ranked by context-index votes"
        ),
        "no_answer_reason": (
            f"WS:{top[0]} ({top[1]}) does not outrank WS:{second[0]} ({second[1]}) by "
            "2x — pick one with --workstream"
        ),
    }


# --------------------------------------------------------- Phase 3: higher law


def _load_kill_rows(degraded: Degraded) -> dict[str, dict[str, Any]] | None:
    """Compiled DNR rows by key, or None when unreadable (fail-open join)."""
    if not _KILL_REGISTRY.exists():
        degraded.add(f"{_rel(_KILL_REGISTRY)} absent — DNR citations unresolved")
        return None
    try:
        doc = yaml.safe_load(_KILL_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        degraded.add(
            f"{_rel(_KILL_REGISTRY)} unreadable ({exc.__class__.__name__}) — "
            "DNR citations unresolved"
        )
        return None
    entries = doc.get("entries") if isinstance(doc, dict) else None
    if not isinstance(entries, list):
        degraded.add(f"{_rel(_KILL_REGISTRY)} has no 'entries' list — DNR unresolved")
        return None
    return {
        str(row["key"]): row
        for row in entries
        if isinstance(row, dict) and isinstance(row.get("key"), str)
    }


def _load_program_row(program: str, degraded: Degraded) -> dict[str, Any] | None:
    """The owning program's registry row, or None (fail-open join)."""
    if not _PROGRAMS.exists():
        degraded.add(f"{_PROGRAMS_REL} absent — program context omitted")
        return None
    try:
        doc = yaml.safe_load(_PROGRAMS.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        degraded.add(
            f"{_PROGRAMS_REL} unreadable ({exc.__class__.__name__}) — program omitted"
        )
        return None
    programs = doc.get("programs") if isinstance(doc, dict) else None
    row = programs.get(program) if isinstance(programs, dict) else None
    if not isinstance(row, dict):
        degraded.add(f"{_PROGRAMS_REL} has no row for program {program!r} — omitted")
        return None
    return row


PROGRAM_EXCERPT_FIELDS = (
    ("name", "name"),
    ("description", "description"),
    ("purpose", "purpose"),
    ("strategic role", "strategic_role"),
    ("lifecycle", "lifecycle_state"),
)


def _higher_law_items(
    rec: dict[str, Any], key: str, *, degraded: Degraded
) -> list[dict[str, Any]]:
    """DNR rows, the P0 objective, and the program row — everything that outranks."""
    items: list[dict[str, Any]] = []

    prose = list(rec.get("do_not_redo") or []) + list(rec.get("landmines") or [])
    cited = sorted({
        token for entry in prose if isinstance(entry, str)
        for token in DNR_RE.findall(entry)
    })
    rows = _load_kill_rows(degraded) if cited else None
    for token in cited:
        row = (rows or {}).get(token)
        if row is None:
            # Fail-OPEN and LOUD.  An unresolvable DNR citation is a real problem for the
            # reader, but it is the registry's problem, not a reason to refuse a bundle.
            degraded.add(
                f"DNR:{token} cited by WS:{key} does not resolve in "
                f"{_rel(_KILL_REGISTRY)} — cite it as DNR:<KEY>, never by row number"
            )
            continue
        items.append(_bundle_item(
            kind="dnr",
            key=f"DNR:{token}",
            path=_DNR_SOURCE,
            locator=f"{_DNR_SOURCE}#{token}",
            authority_class="A1",
            status=str(row.get("verdict") or "unknown"),
            updated=None,
            excerpt=_fields(row, (("topic", "topic"), ("verdict", "verdict"),
                                  ("source", "source"), ("section", "section_name"))),
            why=f"cited as DNR:{token} in WS:{key} do_not_redo/landmines",
        ))

    p0 = rec.get("p0")
    if isinstance(p0, str) and p0:
        p0_status = load_p0(degraded)
        label = f"mastermind:{_STRATEGIC_STATE_REL.as_posix()}"
        if p0_status is None:
            pass  # load_p0 already said why; P0 context stays unknown (I4)
        elif p0 not in p0_status:
            degraded.add(
                f"p0 {p0!r} on WS:{key} is not an objective in {label} — P0 context omitted"
            )
        else:
            items.append(_bundle_item(
                kind="p0",
                key=None,
                path=label,
                locator=f"{label}#p0.{p0}",
                authority_class="A1",
                status=p0_status[p0],
                updated=None,
                excerpt=f"P0 objective: {p0}\nstatus: {p0_status[p0]}",
                why=f"WS:{key} declares p0: {p0}",
            ))

    program = rec.get("program")
    if isinstance(program, str) and program:
        row = _load_program_row(program, degraded)
        if row is not None:
            items.append(_bundle_item(
                kind="program",
                key=None,
                path=_PROGRAMS_REL,
                locator=f"{_PROGRAMS_REL}#programs.{program}",
                authority_class="A1",
                status=str(row.get("lifecycle_state") or "unknown"),
                updated=None,
                excerpt=_fields(row, PROGRAM_EXCERPT_FIELDS),
                why=f"WS:{key} belongs to program {program}",
            ))
    return items


# --------------------------------------------------- Phase 3: workstream block


def _wave_line(wave: dict[str, Any], prs: dict[int, dict[str, Any]]) -> str:
    bits = [f"{wave.get('id')} {_flat(wave.get('title'))} — {wave.get('status')}"]
    deps = [d for d in (wave.get("depends_on") or []) if isinstance(d, str)]
    if deps:
        bits.append("deps: " + ", ".join(deps))
    for number in _wave_prs(wave):
        joined = prs.get(number)
        # Fail-OPEN on the PR join: "unknown" is an honest answer, and it is the normal
        # one in a sparse worktree where data/governance/ was never checked out.
        bits.append(f"PR #{number} {joined['state'].upper() if joined else 'unknown'}")
    wait = _wait_row(wave)
    if wait:
        bits.append(
            f"wait: {wait['kind']} · review_after: {wait['review_after']} · "
            f"condition: {_flat(wait['condition'])}"
        )
    if wave.get("next_action"):
        bits.append("next: " + _flat(wave["next_action"]))
    return " · ".join(bits)


def _workstream_excerpt(
    rec: dict[str, Any], prs: dict[int, dict[str, Any]]
) -> str:
    lines = [f"objective: {_flat(rec.get('objective'))}"]
    lines.append(
        f"status: {rec.get('status')} · class: {rec.get('class')} · "
        f"blast_radius: {rec.get('blast_radius')} · ambiguity: {rec.get('ambiguity')}"
    )
    lines.append(
        f"owner: {rec.get('owner')} · program: {rec.get('program')} · "
        f"repos: {_flat(rec.get('repos'))}"
    )
    if rec.get("owns_paths"):
        lines.append(f"owns_paths: {_flat(rec.get('owns_paths'))}")
    waves = [w for w in (rec.get("waves") or []) if isinstance(w, dict)]
    if waves:
        lines.append("waves:")
        lines.extend(f"  {_wave_line(wave, prs)}" for wave in waves)
    if rec.get("blocked_by"):
        lines.append(f"blocked_by: {_flat(rec.get('blocked_by'))}")
    wait = _wait_row(rec)
    if wait:
        # DECLARED, never inferred, and never executed: the reader is told this quiet is
        # deliberate and when its author looks again.  `condition` is reproduced as
        # authored (flattened to one line, never parsed) — reading it is a human's job.
        lines.append(
            f"wait (DECLARED INTENTIONAL INACTIVITY — schedules nothing, gates nothing): "
            f"{wait['kind']} · review_after: {wait['review_after']} · "
            f"condition: {_flat(wait['condition'])}"
        )
    needs = rec.get("needs_ceo")
    if isinstance(needs, dict):
        lines.append(f"needs_ceo: {_flat(needs.get('question'))}")
        if needs.get("recommendation"):
            lines.append(f"  recommendation: {_flat(needs.get('recommendation'))}")
    claim = rec.get("claim")
    if isinstance(claim, dict):
        # ADVISORY, and labelled so in the bundle itself.  Chairman ruling C2: a claim
        # note is an author's note in git, never evidence that anyone is working now.
        lines.append(
            f"claim (ADVISORY — an author's note in git, blocks nothing, proves no live "
            f"activity): by {claim.get('by')}, expires {claim.get('expires')}"
        )
    lines.append(f"next_action: {_flat(rec.get('next_action'))}")
    body = _clip(rec.get("_body", ""), EXCERPT_WORKSTREAM_BODY)
    if body:
        lines += ["", "--- record body (excerpt) ---", body]
    return "\n".join(lines)


# ------------------------------------------------------------ Phase 3: the walk


def compile_bundle(
    store: Store,
    *,
    workstream: str | None = None,
    task: str | None = None,
    now: _dt.datetime,
    budget: int = BUNDLE_BUDGET_DEFAULT,
    builds: dict[str, Any] | None = None,
    degraded: Degraded | None = None,
    search_fn: Callable[[str], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Compile ``context_bundle.v1``.  Pure read; never writes, never gates.

    ``budget`` caps the bundle, with one documented exception: the workstream block and
    HIGHER LAW are always included, so ``token_estimate`` may exceed ``token_budget`` when
    — and only when — those two ALONE exceed it.  Constraint-class context is not tradable
    against pointer-class context; see the packer for why.

    ``search_fn`` is the retrieval seam: ``None`` means the real context index (see
    ``_default_search``).  It exists so a test can inject a packet without a built index
    and so the fail-open path has somewhere to fail to — production always uses the index.
    """
    degraded = degraded if degraded is not None else Degraded()
    budget = max(BUNDLE_BUDGET_MIN, int(budget))
    target = _resolve_target(
        store, workstream=workstream, task=task, search_fn=search_fn, degraded=degraded
    )

    envelope: dict[str, Any] = {
        "schema": BUNDLE_SCHEMA,
        "target": {
            "workstream": f"WS:{target['key']}" if target["key"] else None,
            "task": task,
            "resolution": target["resolution"],
            "candidates": target["candidates"],
            # Additive, and null when the target declares none — absence of a wait is
            # never read as a claim that the work is unattended.
            "wait": None,
        },
        "generated_at": _iso_z(now),
        "repo_sha": _repo_sha(),
        "token_budget": budget,
        "token_estimate": 0,
        "sections": [],
        "excluded": [],
        "omitted_due_to_budget": [],
        "degraded": list(degraded.items),
        "no_answer_reason": target["no_answer_reason"],
    }
    if target["key"] is None:
        # Sections stay EMPTY.  A bundle that guessed a workstream and filled itself in
        # would be indistinguishable from one that knew.
        return envelope

    key = target["key"]
    ws_all = store.of_type("WS")
    dec_all = store.of_type("DEC")
    dsc_all = store.of_type("DSC")
    hnd_all = store.of_type("HND")
    rec = ws_all[key]
    envelope["target"]["wait"] = _wait_row(rec)
    ws_path = store.paths[f"WS/{key}"]
    program = rec.get("program") if isinstance(rec.get("program"), str) else None
    prs = _pr_index(builds)
    # Record-LOCAL hard problems only.  A sibling whose own frontmatter is wrong is a lie
    # and is refused; a sibling whose only fault is a citation that does not resolve is a
    # JOIN failure and fails open (see CROSS_RECORD_RULES) — it is rendered, with the
    # unresolved half named in `degraded`.  Dropping it instead would delete a valid
    # decision from the bundle because some THIRD record was renamed.
    hard_paths = {
        problem.path for problem in store.problems
        if problem.hard and problem.rule not in CROSS_RECORD_RULES
    }

    excluded: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = {name: [] for name in PACK_ORDER}
    order = [0]

    def emit(pack: str, item: dict[str, Any]) -> None:
        item["_seq"] = order[0]
        order[0] += 1
        groups[pack].append(item)

    def drop(kind: str, ident: str | None, path: Path | str, reason: str) -> None:
        excluded.append({
            "kind": kind,
            "key": ident,
            "path": _rel(path) if isinstance(path, Path) else path,
            "reason": reason,
        })

    def malformed(kind: str, ident: str, path: Path) -> bool:
        """A record any hard Problem targets is a lie; it is NAMED, never rendered."""
        if path not in hard_paths:
            return False
        drop(kind, ident, path, "malformed record — excluded from the walk")
        degraded.add(f"record excluded (malformed): {_rel(path)} — {ident}")
        return True

    # ---- higher law (never dropped by budget) ------------------------------
    for item in _higher_law_items(rec, key, degraded=degraded):
        emit("higher_law", item)

    # ---- workstream state (never dropped by budget) ------------------------
    _, ws_updated = git_dates(ws_path)
    emit("workstream_block", _bundle_item(
        kind="workstream",
        key=f"WS:{key}",
        path=_rel(ws_path),
        locator=f"{_rel(ws_path)}#frontmatter",
        authority_class="A4",
        status=str(rec.get("status") or "unknown"),
        updated=ws_updated,
        excerpt=_workstream_excerpt(rec, prs),
        why="the compilation target",
    ))
    for field, label in (("landmines", "landmine"), ("do_not_redo", "settled — do not redo")):
        for entry in rec.get(field) or []:
            if not isinstance(entry, str) or not entry.strip():
                continue
            emit("workstream_block", _bundle_item(
                kind="constraint",
                key=f"WS:{key}",
                path=_rel(ws_path),
                locator=f"{_rel(ws_path)}#{field}",
                authority_class="A4",
                status=label,
                updated=ws_updated,
                excerpt=f"[{label.upper()}] {_clip(_flat(entry), EXCERPT_CONSTRAINT)}",
                why=f"{field} declared on WS:{key}",
            ))

    # ---- dependency stubs: depth 1, never their subtrees --------------------
    for dep in sorted(_refs(rec.get("depends_on"), "WS")):
        dep_rec = ws_all.get(dep)
        if dep_rec is None:
            drop("dependency", f"WS:{dep}", "—", "dangling depends_on — no such record")
            continue
        dep_path = store.paths[f"WS/{dep}"]
        if malformed("dependency", f"WS:{dep}", dep_path):
            continue
        _, dep_updated = git_dates(dep_path)
        emit("dependency", _bundle_item(
            kind="dependency",
            key=f"WS:{dep}",
            path=_rel(dep_path),
            locator=f"{_rel(dep_path)}#frontmatter",
            authority_class="A4",
            status=str(dep_rec.get("status") or "unknown"),
            updated=dep_updated,
            excerpt=(
                f"{_flat(dep_rec.get('title'))}\n"
                f"status: {dep_rec.get('status')}\n"
                f"next_action: {_flat(dep_rec.get('next_action'))}"
            ),
            why=f"WS:{key} depends_on WS:{dep} (stub only — open the record for its waves)",
        ))

    # ---- decisions ---------------------------------------------------------
    # `owns_paths` is the third declared form of `affects`/`scope` (both schemas say so),
    # and the only one that needs a match rather than an equality test.
    owned = _owned_globs(rec)
    cited_dec = set(_refs(rec.get("decisions"), "DEC"))
    reasons: dict[str, list[str]] = {}
    for ref in sorted(cited_dec):
        reasons.setdefault(ref, []).append(f"cited by WS:{key}")
    for dec_key in sorted(dec_all):
        # A bare repo name is stripped FIRST and stays stripped: it would otherwise reach
        # the glob matcher and attach every decision in a repo to every workstream in it.
        affects = [str(a).strip() for a in (dec_all[dec_key].get("affects") or [])
                   if isinstance(a, str) and str(a).strip() not in REPOS]
        if f"WS:{key}" in affects:
            reasons.setdefault(dec_key, []).append(f"declares affects WS:{key}")
        if program and program in affects:
            reasons.setdefault(dec_key, []).append(f"declares affects program {program}")
        for entry in affects:
            hit = _owned_overlap(entry, dec_all[dec_key], owned)
            if hit is not None:
                reasons.setdefault(dec_key, []).append(
                    f"affects paths this workstream owns ({entry} ~ {hit})"
                )
    rows: list[dict[str, Any]] = []
    for dec_key in sorted(reasons):
        dec_rec = dec_all.get(dec_key)
        if dec_rec is None:
            drop("decision", f"DEC:{dec_key}", "—", "dangling citation — no such record")
            continue
        dec_path = store.paths[f"DEC/{dec_key}"]
        if malformed("decision", f"DEC:{dec_key}", dec_path):
            continue
        replacement, raw = _supersession(dec_rec, "DEC", dec_all)
        if replacement is not None:
            # NEVER co-equal.  Supersession is the whole reason both records survive; a
            # bundle that listed them side by side would undo it.
            drop("decision", f"DEC:{dec_key}", dec_path, f"superseded_by DEC:{replacement}")
            continue
        if raw is not None:
            degraded.add(
                f"DEC:{dec_key} carries unresolvable superseded_by {raw!r} — retained; "
                f"fix the record"
            )
        supersedes = _refs(dec_rec.get("supersedes"), "DEC")
        note = ("\n[supersedes " + ", ".join(f"DEC:{s}" for s in supersedes) + "]"
                if supersedes else "")
        body = _fields(dec_rec, (("question", "question"), ("answer", "answer"),
                                 ("rationale", "rationale")))
        _, dec_updated = git_dates(dec_path)
        rows.append({
            "_date": str(_as_date(dec_rec.get("decided_at")) or ""),
            "item": _bundle_item(
                kind="decision",
                key=f"DEC:{dec_key}",
                path=_rel(dec_path),
                locator=f"{_rel(dec_path)}#frontmatter",
                authority_class="A3",
                status=str(dec_rec.get("confidence") or "unknown"),
                updated=dec_updated,
                excerpt=_clip(body, EXCERPT_DECISION - len(note)) + note,
                why="; ".join(reasons[dec_key]),
            ),
        })
    rows.sort(key=lambda row: row["item"]["key"])
    rows.sort(key=lambda row: row["_date"], reverse=True)
    for row in rows:
        emit("decisions", row["item"])

    # ---- discoveries -------------------------------------------------------
    citations = discovery_citation_counts(store.records)
    cited_dsc = set(_refs(rec.get("discoveries"), "DSC"))
    dsc_reasons: dict[str, list[str]] = {}
    for ref in sorted(cited_dsc):
        dsc_reasons.setdefault(ref, []).append(f"cited by WS:{key}")
    for dsc_key in sorted(dsc_all):
        # A repo-wide scope (`macro`) does NOT qualify: it would attach every finding in
        # the repo to every workstream in it, which is the opposite of a bounded bundle.
        # The strip runs BEFORE glob matching and is load-bearing there — `_owns_overlap`
        # is prefix-coarse, so an unstripped `terminal` overlaps `terminal/components/**`
        # and the repo-wide attach comes back through the path door.
        scope = [str(s).strip() for s in (dsc_all[dsc_key].get("scope") or [])
                 if isinstance(s, str) and str(s).strip() not in REPOS]
        if key in scope or f"WS:{key}" in scope:
            dsc_reasons.setdefault(dsc_key, []).append(f"scoped to WS:{key}")
        if program and program in scope:
            dsc_reasons.setdefault(dsc_key, []).append(f"scoped to program {program}")
        for entry in scope:
            hit = _owned_overlap(entry, dsc_all[dsc_key], owned)
            if hit is not None:
                dsc_reasons.setdefault(dsc_key, []).append(
                    f"scoped to paths this workstream owns ({entry} ~ {hit})"
                )
    rows = []
    for dsc_key in sorted(dsc_reasons):
        dsc_rec = dsc_all.get(dsc_key)
        if dsc_rec is None:
            drop("discovery", f"DSC:{dsc_key}", "—", "dangling citation — no such record")
            continue
        dsc_path = store.paths[f"DSC/{dsc_key}"]
        if malformed("discovery", f"DSC:{dsc_key}", dsc_path):
            continue
        replacement, raw = _supersession(dsc_rec, "DSC", dsc_all)
        if replacement is not None:
            drop("discovery", f"DSC:{dsc_key}", dsc_path, f"superseded_by DSC:{replacement}")
            continue
        if raw is not None:
            degraded.add(
                f"DSC:{dsc_key} carries unresolvable superseded_by {raw!r} — retained; "
                f"fix the record"
            )
        # RULING (2026-08-13): an explicit `expires` date is the AUTHOR'S hard freshness
        # boundary and evicts regardless of citation.  The schema's "if never cited"
        # clause modifies the 90-day DEFAULT below, not an explicit date — a finding whose
        # author wrote "this is untrue after May" does not become true again because
        # someone cited it.  Citation instead buys VISIBILITY: a target that cites an
        # expired discovery is told so, because to that reader the exclusion looks like
        # the finding never existed.
        expires = _as_date(dsc_rec.get("expires"))
        if expires and expires < now.date():
            drop("discovery", f"DSC:{dsc_key}", dsc_path, f"expired {expires}")
            if dsc_key in cited_dsc:
                degraded.add(
                    f"DSC:{dsc_key} cited by this workstream but expired {expires} — "
                    f"re-verify or supersede"
                )
            continue
        verified = _as_date(dsc_rec.get("verified_at"))
        age = (now.date() - verified).days if verified else None
        if not citations.get(dsc_key, 0) and age is not None and age > STALE_DISCOVERY_DAYS:
            drop("discovery", f"DSC:{dsc_key}", dsc_path, f"uncited and {age}d old")
            continue
        _, dsc_updated = git_dates(dsc_path)
        rows.append({
            "_date": str(verified or ""),
            "item": _bundle_item(
                kind="discovery",
                key=f"DSC:{dsc_key}",
                path=_rel(dsc_path),
                locator=f"{_rel(dsc_path)}#frontmatter",
                authority_class="A3",
                status=str(dsc_rec.get("confidence") or "unknown"),
                updated=dsc_updated,
                excerpt=_clip(_fields(dsc_rec, (("claim", "claim"), ("so what", "so_what"),
                                                ("falsifier", "falsifier"))),
                              EXCERPT_DISCOVERY),
                why="; ".join(dsc_reasons[dsc_key]),
            ),
        })
    rows.sort(key=lambda row: row["item"]["key"])
    rows.sort(key=lambda row: row["_date"], reverse=True)
    for row in rows:
        emit("discoveries", row["item"])

    # ---- handoff: the LATEST only ------------------------------------------
    mine: list[str] = [
        stem for stem in sorted(hnd_all)
        if key in _refs(hnd_all[stem].get("workstream"), "WS")
    ]

    def handoff_rank(stem: str) -> tuple[str, str]:
        match = HANDOFF_DATE_RE.search(stem)
        return (match.group(1) if match else "", stem)

    if mine:
        latest = max(mine, key=handoff_rank)
        for stem in mine:
            hnd_path = store.paths[f"HND/{stem}"]
            if stem != latest:
                drop("handoff", stem, hnd_path, f"older_handoff (latest: {latest})")
                continue
            if malformed("handoff", stem, hnd_path):
                continue
            _, hnd_updated = git_dates(hnd_path)
            emit("handoff", _bundle_item(
                kind="handoff",
                key=f"WS:{key}",
                path=_rel(hnd_path),
                locator=f"{_rel(hnd_path)}#frontmatter",
                authority_class="A4",
                status=str(hnd_all[stem].get("ended_because") or "unknown"),
                updated=hnd_updated,
                excerpt=_clip(
                    _fields(hnd_all[stem], (
                        ("mission", "mission"), ("state before", "state_before"),
                        ("next actions", "next_actions"), ("do not redo", "do_not_redo"),
                        ("danger areas", "danger_areas"), ("unresolved", "unresolved"),
                    )),
                    EXCERPT_HANDOFF,
                ),
                why=f"latest handoff for WS:{key} ({stem})",
            ))

    # ---- artifacts: pointers, never absorbed prose -------------------------
    roots = repo_roots()
    for entry in rec.get("artifacts") or []:
        if not isinstance(entry, str) or not entry.strip():
            continue
        resolved = _resolve_path(entry.strip(), rec)
        if resolved is None:
            # NAMED, not skipped.  A `PREFIX:KEY` citation or a URL that wandered into
            # `artifacts` is an authoring mistake, and a bundle that drops it silently
            # reads exactly like a record that never listed it.
            degraded.add(f"artifact entry not a repo path — skipped: {entry.strip()}")
            continue
        repo_key, rel = resolved
        shown = rel if repo_key == "macro" else f"{repo_key}:{rel}"
        root = roots.get(repo_key)
        if root is None:
            note = f"repo {repo_key!r} is not checked out — existence unknown"
        elif (root / rel).exists():
            note = "present on disk"
        else:
            note = "NOT FOUND on disk (it may not exist yet)"
        emit("artifacts", _bundle_item(
            kind="artifact",
            key=None,
            path=shown,
            locator=shown,
            authority_class=_pointer_authority(repo_key, rel, degraded),
            status=note,
            updated=None,
            excerpt=f"pointer — {note}. Open the primary source; this bundle does not "
                    f"quote it.",
            why=f"listed in WS:{key} artifacts",
        ))

    # ---- budget ------------------------------------------------------------
    # Selection happens BEFORE rendering, over the already-filtered items, so JSON and
    # --text can never disagree about what made the cut.  Greedy in packing priority, the
    # same shape as packet._pack_results: an item that does not fit is NAMED and packing
    # continues, because a later smaller item still helps the reader.
    #
    # CONSTRAINT-CLASS CONTEXT IS NEVER TRADED FOR POINTER-CLASS CONTEXT.  Greedy-with-
    # continuation alone empties HIGHER LAW while ARTIFACTS still renders — the cheap tail
    # fits in the change left over by the expensive head — and a bundle whose entire job is
    # to tell a cold session which constraints may not be violated must not lose them to a
    # cap while keeping file paths.  So `higher_law` joins `workstream_block` in the
    # always-include set.  That set is bounded PER ENTRY (every excerpt is `_clip`ped, the
    # constraints at EXCERPT_CONSTRAINT) and LINEAR in what the record declares — a
    # workstream with forty landmines has forty always-included items — plus at most the
    # DNR rows it cites, one P0 row and one program row.  It is NOT bounded small by
    # construction, and pretending it was is how an unbounded overrun would have shipped
    # unnoticed: any resulting overrun is NAMED in `degraded` below, which is the signal.
    # DEGENERATE-BUDGET EXCEPTION: `token_estimate` may exceed `token_budget` only through
    # the always-include set and the accounting tails; every other pack is capped.
    ordered = [item for pack in PACK_ORDER for item in groups[pack]]
    always = {id(item) for item in groups["workstream_block"] + groups["higher_law"]}
    selected: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    used = 0
    always_cost = 0
    for rank, item in enumerate(ordered):
        cost = _item_cost(item)
        if id(item) in always or used + cost <= budget:
            selected.append(item)
            used += cost
            if id(item) in always:
                always_cost += cost
            continue
        omitted.append({
            "kind": item["kind"], "key": item["key"], "path": item["path"],
            "tokens": cost, "rank": rank,
        })

    # Membership by IDENTITY, not equality: two items can carry byte-identical content
    # (two landmines that say the same thing), and `in selected` would then admit the
    # wrong one — or both — under dict `__eq__`.
    chosen = {id(item) for item in selected}
    by_section: dict[str, list[dict[str, Any]]] = {}
    for pack in PACK_ORDER:
        for item in groups[pack]:
            if id(item) in chosen:
                by_section.setdefault(_PACK_SECTION[pack], []).append(item)
    for items in by_section.values():
        items.sort(key=lambda item: item["_seq"])
    for item in ordered:
        item.pop("_seq", None)

    # The TAILS are payload too.  `excluded`, `omitted_due_to_budget`, `degraded` and the
    # candidate list all ship in the bundle a caller pays for, and pricing only the items
    # is how a "1,000-token" bundle arrives as 6,500 tokens of JSON.  They are priced but
    # never PACKED against: the omission list grows as packing omits, so feeding it back
    # into the packing loop is circular.  The report is the honest layer — packing bounds
    # what it can bound, and `token_estimate` then states the whole payload.
    tails = _estimate_tokens(json.dumps({
        "excluded": excluded,
        "omitted_due_to_budget": omitted,
        "degraded": list(degraded.items),
        "candidates": target["candidates"],
    }, ensure_ascii=False))
    used += tails
    if used > budget:
        # The SIGNAL for every overrun, whatever caused it — an always-included set larger
        # than the cap, or accounting tails that outgrew it.  Neither is droppable, so the
        # only honest response is to say so; a bare number in the header reads as a bug.
        degraded.add(
            f"token_estimate {used} exceeds token_budget {budget} — "
            f"always-included constraint context ({always_cost}) + packed items "
            f"({used - tails - always_cost}) + accounting tails ({tails}); the "
            f"always-included set and the tails are never dropped, so raise --budget"
        )

    envelope["token_estimate"] = used
    envelope["sections"] = [
        {"id": ident, "title": title, "authority_note": note,
         "items": by_section.get(ident, [])}
        for ident, title, note in SECTIONS
    ]
    envelope["excluded"] = excluded
    envelope["omitted_due_to_budget"] = omitted
    # Re-read at the end: the walk itself degrades (an unresolvable DNR row, an absent
    # sibling), and a snapshot taken at envelope time would drop exactly those.
    envelope["degraded"] = list(degraded.items)
    return envelope


# ------------------------------------------------------ Phase 3: text rendering


def render_bundle(bundle: dict[str, Any]) -> str:
    """The readable form.  Same selected set as the JSON — one compiler, two renderers."""
    target = bundle["target"]
    # A header that prints an estimate ABOVE the budget with no comment reads as an
    # arithmetic bug.  It is not — see the packer — so the header points at the DEGRADED
    # block that names the overrun and its composition.
    overrun = (" — OVER BUDGET, see DEGRADED"
               if bundle["token_estimate"] > bundle["token_budget"] else "")
    out: list[str] = [
        f"=== CONTEXT BUNDLE — {target['workstream'] or 'NO WORKSTREAM RESOLVED'} ===",
        f"task: {target['task'] or '—'}",
        f"resolution: {target['resolution']}",
        f"generated: {bundle['generated_at']}  ·  repo_sha: {bundle['repo_sha'][:12]}",
        f"budget: {bundle['token_budget']} tokens  ·  estimate: "
        f"{bundle['token_estimate']} tokens{overrun}",
        "",
    ]
    if bundle["no_answer_reason"]:
        out += _wrap(f"NO ANSWER: {bundle['no_answer_reason']}", 76, "") + [""]
    for candidate in target["candidates"]:
        out.append(f"  candidate {candidate['key']} (score {candidate['score']}) — "
                   f"{candidate['title']}")
    if target["candidates"]:
        out.append("")

    for section in bundle["sections"]:
        out.append(f"━━ {section['title']} {RULE[:max(0, 72 - len(section['title']))]}")
        out.extend(_wrap(section["authority_note"], 74, "   "))
        out.append("")
        if not section["items"]:
            out += ["   (nothing in this section)", ""]
            continue
        for item in section["items"]:
            cite = f"{item['key']} · {item['path']}" if item["key"] else item["path"]
            out.append(f" [{item['authority_class']} · {item['status']}] {cite}")
            out.extend(_wrap(f"why: {item['why_included']}", 70, "     "))
            for line in item["excerpt"].splitlines():
                out.extend(_wrap(line, 70, "     ") or [""])
            out.append("")

    # Always printed, never suppressed — the omission list IS the honesty of the bundle.
    out.append(f"━━ EXCLUDED ({len(bundle['excluded'])}) {RULE[:56]}")
    for row in bundle["excluded"] or []:
        out.append(f" • {row['key'] or row['kind']} · {row['path']} — {row['reason']}")
    if not bundle["excluded"]:
        out.append(" (nothing excluded)")
    out.append("")
    out.append(f"━━ OMITTED — BUDGET ({len(bundle['omitted_due_to_budget'])}) {RULE[:48]}")
    for row in bundle["omitted_due_to_budget"] or []:
        out.append(f" • {row['key'] or row['kind']} · {row['path']} — "
                   f"{row['tokens']} tokens (rank {row['rank']})")
    if not bundle["omitted_due_to_budget"]:
        out.append(" (nothing omitted — the bundle fits its budget)")
    out.append("")
    out.append(f"━━ DEGRADED ({len(bundle['degraded'])}) {RULE[:56]}")
    for message in bundle["degraded"] or []:
        wrapped = _wrap(message, 70, "   ")
        out.append(" • " + wrapped[0].lstrip() if wrapped else " • ")
        out.extend(wrapped[1:])
    if not bundle["degraded"]:
        out.append(" (every input read cleanly)")
    out.append("")
    return "\n".join(out)


def cmd_compile_context(args: argparse.Namespace) -> int:
    """Bounded, cited context for one workstream.  Writes nothing; stdout only.

    Exit 1 is reserved for the fail-CLOSED case: a caller NAMED a workstream that does not
    exist, that has no store to live in, or whose OWN record is malformed.  That is a
    caller error and a lie about the organization, and compiling around it would hand back
    a bundle for work the store cannot describe.  A CROSS-RECORD problem is not that
    (CROSS_RECORD_RULES): a dangling citation, a dependency cycle and an unreciprocated
    supersession are attributed to the citing record, so a valid workstream whose sibling
    was renamed in an in-flight PR used to be refused outright — the bundle degrades
    around them instead, and each one is named.  Everything else exits 0 with the reason
    in the bundle.

    No GitHub annotations on the success path, deliberately: stdout carries the bundle
    and must stay parseable.  Degraded inputs are a FIELD of the bundle, printed by both
    renderers and never suppressed.
    """
    if bool(args.task) == bool(args.workstream):
        args._parser.error(
            "give exactly one of a free-text task or --workstream <KEY>"
        )

    store_root = Path(args.root) if args.root else _DEFAULT_STORE
    degraded = Degraded()
    now = _parse_moment(args.now) if args.now else _dt.datetime.now(_dt.timezone.utc)
    if now is None:
        degraded.add(f"--now {args.now!r} unparseable — the wall clock was used instead")
        now = _dt.datetime.now(_dt.timezone.utc)

    if not store_root.exists():
        # Asymmetric, and deliberately so.  Naming `--workstream X` against a store that
        # does not exist is the same caller error as naming a workstream that does not
        # exist, and gets the same exit 1.  Free text asked a QUESTION, and "there is no
        # record store here" is an honest answer to it — a not-yet-adopted repo is a
        # normal state (the same fail-open `validate` takes), so it exits 0 saying so.
        if args.workstream:
            print(f"::error title=agentos-compile::no agentos/ store at {store_root} — "
                  f"cannot compile WS:{_normalize_ws_key(args.workstream)}", flush=True)
            return 1
        degraded.add(f"no agentos/ store at {store_root} — nothing to compile")
        store = Store(store_root)
    else:
        store = load_store(store_root, _load_programs())

    if args.workstream:
        key = _normalize_ws_key(args.workstream)
        ident = f"WS/{key}"
        if ident not in store.records:
            print(f"::error title=agentos-compile::unknown workstream WS:{key} — "
                  f"no record at {store_root}/workstreams/WS-{key}.md", flush=True)
            for problem in store.problems:
                if problem.hard and problem.path.stem == f"WS-{key}":
                    print(f"::error title=agentos-{problem.rule}::"
                          f"{problem.render(_ROOT)}", flush=True)
            return 1
        target_path = store.paths[ident]
        mine = [p for p in store.problems if p.hard and p.path == target_path]
        fatal = [p for p in mine if p.rule not in CROSS_RECORD_RULES]
        if fatal:
            for problem in fatal:
                print(f"::error title=agentos-{problem.rule}::{problem.render(_ROOT)}",
                      flush=True)
            print(f"::error title=agentos-compile::WS:{key} is malformed — fix the record "
                  "before compiling context from it (fail-closed on schema, I4)",
                  flush=True)
            return 1
        for problem in mine:
            if problem.rule in CROSS_RECORD_RULES:
                # Not fatal, and not invisible either: the compile proceeds, and the
                # unresolved half travels with the bundle it degraded.
                degraded.add(
                    f"cross-record problem on WS:{key} — [{problem.rule}] "
                    f"{problem.message}; the bundle compiles around it"
                )

    builds = load_active_builds(
        degraded, Path(args.active_builds) if args.active_builds else None
    )
    bundle = compile_bundle(
        store,
        workstream=args.workstream,
        task=args.task,
        now=now,
        budget=args.budget,
        builds=builds,
        degraded=degraded,
    )
    # Mirrors context_index_query.py exactly: machines get the default, humans opt in, and
    # `--json --text` together resolves to JSON in BOTH tools rather than one each way.
    as_json = args.json or not args.text
    sys.stdout.write(_dump_json(bundle) if as_json else render_bundle(bundle))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agentos", description="Agent OS record validator and view generator."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="schema + referential integrity over agentos/")
    p_validate.add_argument("--root", help="store root (default: <repo>/agentos)")
    p_validate.add_argument("--quiet", action="store_true", help="suppress warnings")
    p_validate.set_defaults(func=cmd_validate)

    p_status = sub.add_parser("status", help="materialize agent_os_state.v1 (Phase 2)")
    p_status.add_argument("--root", help="store root (default: <repo>/agentos)")
    p_status.add_argument("--active-builds", help="active_builds.v1 path override")
    p_status.add_argument("--json-out", help="agent_os_state.json path override")
    p_status.add_argument("--md-out", help="AGENT_OS_STATE.md path override")
    p_status.add_argument("--now", help="freeze the clock (ISO-8601) — reproducibility")
    p_status.add_argument("--scan-uncommitted", action="store_true",
                          help="also scan every worktree for uncommitted source work")
    p_status.add_argument("--dry-run", action="store_true",
                          help="print the JSON, write nothing")
    p_status.set_defaults(func=cmd_status)

    p_brief = sub.add_parser("brief", help="CEO brief (Phase 2)")
    p_brief.add_argument("--root", help="store root (default: <repo>/agentos)")
    p_brief.add_argument("--active-builds", help="active_builds.v1 path override")
    p_brief.add_argument("--since", help="1h | 24h | 7d | overnight | YYYY-MM-DD")
    p_brief.add_argument("--full", action="store_true", help="include autonomous detail")
    p_brief.add_argument("--json", action="store_true", help="emit ceo_brief.v1")
    p_brief.add_argument("--now", help="freeze the clock (ISO-8601) — reproducibility")
    p_brief.add_argument("--scan-uncommitted", action="store_true",
                         help="also scan every worktree for uncommitted source work")
    p_brief.add_argument("--no-remember", action="store_true",
                         help="do not record this invocation as the last check-in")
    p_brief.set_defaults(func=cmd_brief)

    p_ctx = sub.add_parser(
        "compile-context",
        help="bounded, cited context_bundle.v1 for a workstream or a task (Phase 3)",
    )
    p_ctx.add_argument("task", nargs="?",
                       help="free-text task; resolved via the context index")
    p_ctx.add_argument("--workstream",
                       help="workstream key — KEY, WS-KEY and WS:KEY are all accepted")
    p_ctx.add_argument("--budget", type=int, default=BUNDLE_BUDGET_DEFAULT,
                       help=f"token budget (default {BUNDLE_BUDGET_DEFAULT}, "
                            f"floor {BUNDLE_BUDGET_MIN})")
    p_ctx.add_argument("--text", action="store_true", help="human-readable output")
    p_ctx.add_argument("--json", action="store_true",
                       help="emit context_bundle.v1 (the default; accepted for symmetry)")
    p_ctx.add_argument("--root", help="store root (default: <repo>/agentos)")
    p_ctx.add_argument("--active-builds", help="active_builds.v1 path override")
    p_ctx.add_argument("--now", help="freeze the clock (ISO-8601) — reproducibility")
    # The subparser is carried on the namespace so the command can raise a real usage
    # error for "both or neither", which argparse cannot express between a positional
    # and an option.
    p_ctx.set_defaults(func=cmd_compile_context, _parser=p_ctx)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
