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
    compile-context   bounded cited bundle for a workstream (Phase 3)

Usage::

    python3 scripts/agentos.py validate
    python3 scripts/agentos.py validate --root agentos --quiet
    python3 scripts/agentos.py status
    python3 scripts/agentos.py status --dry-run
    python3 scripts/agentos.py brief --since 24h
    python3 scripts/agentos.py brief --full
    python3 scripts/agentos.py brief --json
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
from typing import Any, Iterable

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    print("::error title=agentos::PyYAML is required (pip install pyyaml)", flush=True)
    raise SystemExit(1)

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_STORE = _ROOT / "agentos"
_PROGRAMS = _ROOT / "config" / "mastermind_programs.yml"

_ACTIVE_BUILDS = _ROOT / "data" / "governance" / "active_builds.json"
_STATE_JSON = _ROOT / "data" / "governance" / "agent_os_state.json"
_STATE_MD = _ROOT / "docs" / "AGENT_OS_STATE.md"
_BRIEF_MARK = _ROOT / "data" / "governance" / ".ceo_brief_last"

STATE_SCHEMA = "agent_os_state.v1"
BRIEF_SCHEMA = "ceo_brief.v1"

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
CONFIDENCE_DEC = {"high", "medium", "low"}
CONFIDENCE_DSC = {"verified", "probable", "suspected"}
REVERSIBILITY = {"easy", "costly", "one_way"}
DISCOVERY_KIND = {
    "architecture", "data", "landmine", "dead_code", "constraint", "runtime",
}
REPOS = {"macro", "terminal", "mastermind"}
HANDOFF_MODEL = {"fable", "opus", "sonnet", "haiku", "codex", "local"}
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
    that ``status`` now walks for readiness — was quietly incomplete, with no
    signal that an edge was missing.  A ranking computed over a graph with dropped edges
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
            if not wid:
                out.append(Problem(path, "bad-wave", f"{where} missing 'id'", hard=True))
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
        out.append(
            Problem(path_of("WS", cycle[0]), "workstream-cycle",
                    "workstream dependency cycle: " + " -> ".join(f"WS:{n}" for n in cycle),
                    hard=True)
        )

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

    # Citation counts drive discovery GC.  HANDOFFS COUNT: a discovery cited only by a
    # handoff used to read as uncited and became a 90-day GC candidate, which is the
    # exact opposite of what the citation is for.
    cited: dict[str, int] = {k: 0 for k in dsc}
    for rec in list(ws.values()) + list(dec.values()) + list(hnd.values()):
        for ref in _refs(rec.get("discoveries"), "DSC"):
            if ref in cited:
                cited[ref] += 1
    for key, count in cited.items():
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


def _not_yet(phase: str, doc: str) -> int:
    """A stub must be unmistakably a stub — never a silent success."""
    print(f"::warning title=agentos::not implemented until {phase}; see {doc}", flush=True)
    return 0


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


def load_p0(degraded: Degraded) -> dict[str, str] | None:
    """Active P0 objective ids from the Mastermind strategic state, or None if absent.

    The state lives in MASTERMIND, never here — a Macro-side copy read by a Mastermind
    runtime is the cross-repo authority hop `duplicate_control_planes` forbids.  Read
    only; nothing in this file decides anything from it.
    """
    root = repo_roots().get("mastermind")
    if root is None:
        degraded.add("Mastermind checkout not found — p0 ids unvalidated, P0 ranking neutral")
        return None
    target = root / _STRATEGIC_STATE_REL
    # Host paths are never printed into a COMMITTED artifact — the message names the
    # repo-relative file, so the generated view is the same sentence on every machine.
    label = f"mastermind:{_STRATEGIC_STATE_REL.as_posix()}"
    if not target.exists():
        degraded.add(
            f"{label} absent — p0 ids unvalidated, P0 ranking neutral "
            "(this Mastermind checkout predates config/strategic_state.yml)"
        )
        return None
    try:
        doc = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        degraded.add(f"{label} unreadable ({exc.__class__.__name__}) — p0 ids unvalidated")
        return None
    rows = doc.get("p0") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        degraded.add(f"{label} has no 'p0' list — p0 ids unvalidated")
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
        if str(_ROOT) not in sys.path:
            # Run as `python3 scripts/agentos.py`, sys.path[0] is scripts/, so the
            # `scripts` package is not importable without this.
            sys.path.insert(0, str(_ROOT))
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

    # Wave-level dependents, for the UNBLOCKED section's unblock count.
    out: list[dict[str, Any]] = []
    for key in sorted(ws):
        rec = ws[key]
        path = store.paths[f"WS/{key}"]
        created, updated = git_dates(path)
        status = rec.get("status")
        waves = [w for w in (rec.get("waves") or []) if isinstance(w, dict)]
        rollup = {name: 0 for name in sorted(WAVE_STATUS)}
        record_warnings: list[str] = []

        dependents: dict[str, int] = {}
        for wave in waves:
            for dep in wave.get("depends_on") or []:
                if isinstance(dep, str):
                    dependents[dep] = dependents.get(dep, 0) + 1
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
                "deps_satisfied": all(d in done_ids for d in deps),
                "unblocks": dependents.get(wave.get("id"), 0),
                "next_action": wave.get("next_action"),
                "prs": wave_prs,
                "done_at": done_at,
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


def compute_unblocked(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Waves whose dependencies are satisfied, ranked per CEO brief spec §3.

    THIS IS NOT AN ASSIGNMENT AND NOT A QUEUE (I1, and brief §6 "CEO becomes the
    dispatcher").  It ranks work that is *unblocked*; nothing consumes it to decide what
    to run, and nothing is assigned to anyone.  See DEC:AGENTOS-START-NEXT-VS-AGENDA for
    why this is a readiness view and NOT a second copy of the org's ranked work queue —
    `brain/improvement_agenda.py` owns that concept and this must never impersonate it.

    Order: (1) deps satisfied [filter]; (2) active P0 alignment; (3) unblock count;
    (4) unclaimed; then key/wave id so the output is stable and arguable.
    """
    done_ws = {r["key"] for r in records if r["status"] == "done"}
    blocked_states = {"blocked", "parked", "killed", "done"}
    candidates: list[dict[str, Any]] = []
    for row in records:
        if row["status"] in blocked_states:
            continue
        if any(dep not in done_ws for dep in row["depends_on"]):
            continue
        claimed = bool(row["claim"] and not row["claim"]["stale"])
        for wave in row["wave_detail"]:
            if wave["status"] != "todo" or not wave["deps_satisfied"]:
                continue
            candidates.append({
                "workstream": row["key"],
                "wave": wave["id"],
                "title": wave["title"],
                "p0": row["p0"],
                "p0_active": bool(row["p0_active"]),
                "unblocks": wave["unblocks"],
                "claimed": claimed,
                "next_action": wave["next_action"] or row["next_action"],
                "source": row["source"],
            })
    candidates.sort(
        key=lambda c: (
            0 if c["p0_active"] else 1,
            -c["unblocks"],
            1 if c["claimed"] else 0,
            c["workstream"],
            str(c["wave"]),
        )
    )
    return candidates


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
            # `workstream`, matching blocked/finished/unblocked and the documented
            # ceo_brief.v1 envelope.  It emitted `key` here alone, so the one section the
            # CEO acts on was the one whose shape diverged from its own spec.
            {"workstream": row["key"], **row["needs_ceo"], "source": row["source"]}
            for row in records if row["needs_ceo"]
        ],
        "unblocked": compute_unblocked(records),
        "warnings": warnings,
    }


PURE_SECTIONS = ("schema", "generator", "workstreams", "needs_ceo", "unblocked", "warnings")


def pure_section(state: dict[str, Any]) -> dict[str, Any]:
    """The part of the state that must be byte-identical run over run."""
    return {name: state[name] for name in PURE_SECTIONS if name in state}


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

    if state["unblocked"]:
        lines += ["## Unblocked work (readiness, not assignment)", ""]
        for item in state["unblocked"]:
            lines.append(
                f"- `WS:{item['workstream']}` {item['wave']} — {_md_cell(item['title'] or '')}"
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
        f"{len(state['needs_ceo'])} needing a ruling · {len(state['unblocked'])} unblocked "
        f"wave(s) · {len(state['warnings'])} warning(s) · "
        f"{len(degraded.items)} degraded input(s)",
        flush=True,
    )
    return 0


# -------------------------------------------------------- Phase 2: CEO brief


RULE = "━" * 68
CAP_NEEDS_CEO = 5
CAP_BLOCKED = 5
CAP_FINISHED = 8
CAP_START_NEXT = 3


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

# The brief is a READINESS view, not the company's ranked work queue.  Charter P7 gives
# that concept to Mastermind `brain/improvement_agenda.py`, and two ranked lists that
# disagree is exactly the failure P7 exists to prevent — so the brief SAYS SO in prose
# rather than quietly presenting a rival ordering.  Recorded as DEC:AGENTOS-START-NEXT-
# VS-AGENDA and escalated as conflict C3.
UNBLOCKED_SCOPE = (
    "READINESS, NOT PRIORITY — which waves CAN start because their dependencies are "
    "satisfied. brain/improvement_agenda.py is the SOLE canonical answer to 'what "
    "should we do next?' (Chairman ruling C3, 2026-08-12; Charter P7). Agent OS owns "
    "dependency/readiness computation only. This section is INTERIM: readiness is to "
    "be fed into the agenda as an input, and this list retired once that lands — see "
    "DEC:AGENTOS-READINESS-FEEDS-THE-AGENDA."
)


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
        "unblocked": state["unblocked"],
        "unblocked_scope": UNBLOCKED_SCOPE,
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

    out.append(f"━━ UNBLOCKED — READY TO START {RULE[:37]}")
    out.append("")
    out.extend(_wrap(UNBLOCKED_SCOPE, 64, " "))
    out.append("")
    if not brief["unblocked"]:
        out.append(" Nothing is unblocked.")
    cap_next = len(brief["unblocked"]) if full else CAP_START_NEXT
    for index, item in enumerate(brief["unblocked"][:cap_next], start=1):
        p0 = f" · P0 {item['p0']}" if item["p0_active"] else ""
        unblocks = f" · unblocks {item['unblocks']}" if item["unblocks"] else ""
        claimed = " · CLAIMED" if item["claimed"] else ""
        out.append(f" {index}. WS:{item['workstream']} {item['wave']} — "
                   f"{_md_cell(item['title'] or '')}")
        out.append(f"    {item['source']}{p0}{unblocks}{claimed}")
    _overflow(out, len(brief["unblocked"]), cap_next, "ready to start")
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


def cmd_compile_context(_args: argparse.Namespace) -> int:
    return _not_yet("Phase 3", "research/MASTERMIND_AGENT_OS_ARCHITECTURE.md")


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

    p_ctx = sub.add_parser("compile-context", help="context bundle (Phase 3)")
    p_ctx.add_argument("--workstream", help="workstream key")
    p_ctx.set_defaults(func=cmd_compile_context)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
