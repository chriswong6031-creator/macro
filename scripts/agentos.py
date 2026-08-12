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

Subcommands:
    validate          schema + referential integrity over agentos/ (Phase 0)
    status            materialize agent_os_state.v1 + docs/AGENT_OS_STATE.md (Phase 2)
    brief             CEO brief (Phase 2; spec in research/MASTERMIND_CEO_BRIEF_SPEC.md)
    compile-context   bounded cited bundle for a workstream (Phase 3)

Usage::

    python3 scripts/agentos.py validate
    python3 scripts/agentos.py validate --root agentos --quiet
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
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

STALE_DISCOVERY_DAYS = 90
STALE_WORKSTREAM_DAYS = 30


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
    """Extract bare keys from a list of ``PREFIX:KEY`` citations."""
    out: list[str] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.startswith(f"{prefix}:"):
                out.append(item.split(":", 1)[1].strip())
    elif isinstance(value, str) and value.startswith(f"{prefix}:"):
        out.append(value.split(":", 1)[1].strip())
    return out


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
    for field in ("key", "title", "objective", "status", "program",
                  "repos", "owner", "class", "blast_radius", "ambiguity",
                  "waves", "next_action", "created", "updated"):
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

    status = rec.get("status")
    blocked_by = rec.get("blocked_by") or []
    if status == "blocked" and not blocked_by:
        out.append(Problem(path, "blocked-without-cause",
                           "status is 'blocked' but blocked_by is empty", hard=True))
    if blocked_by and status != "blocked":
        out.append(Problem(path, "cause-without-blocked",
                           f"blocked_by is set but status is {status!r}", hard=True))

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
            out.append(
                Problem(path, "active-but-complete",
                        "status is 'active' but every wave is done/dropped", hard=True)
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
    # legitimate entry may be cross-repo ("terminal:app/x.tsx") or a not-yet-created path.
    for entry in rec.get("artifacts") or []:
        if not isinstance(entry, str) or ":" in entry or any(c in entry for c in "*?["):
            continue
        if not (_ROOT / entry).exists():
            out.append(Problem(path, "phantom-artifact",
                               f"artifacts entry {entry!r} does not exist", hard=False))
    for entry in rec.get("owns_paths") or []:
        if not isinstance(entry, str) or ":" in entry:
            continue
        # Check the static prefix directory, i.e. everything before the first glob segment.
        parts: list[str] = []
        for segment in entry.split("/"):
            if any(c in segment for c in "*?["):
                break
            parts.append(segment)
        stem = "/".join(parts)
        if stem and not (_ROOT / stem).exists():
            out.append(Problem(path, "phantom-owns-path",
                               f"owns_paths entry {entry!r} has no existing base {stem!r}",
                               hard=False))

    updated = _as_date(rec.get("updated"))
    if updated and status == "active":
        age = (_dt.date.today() - updated).days
        if age > STALE_WORKSTREAM_DAYS:
            out.append(Problem(path, "stale-workstream",
                               f"active but not updated for {age}d", hard=False))
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

    for key, rec in ws.items():
        here = path_of("WS", key)
        for dep in _refs(rec.get("depends_on"), "WS"):
            if dep not in ws:
                out.append(Problem(here, "dangling-ref",
                                   f"depends_on references unknown WS:{dep}", hard=True))
        for ref in _refs(rec.get("decisions"), "DEC") + [
            d for d in (rec.get("decisions") or []) if isinstance(d, str) and ":" not in d
        ]:
            if ref not in dec:
                out.append(Problem(here, "dangling-ref",
                                   f"decisions references unknown DEC:{ref}", hard=True))
        for ref in _refs(rec.get("discoveries"), "DSC") + [
            d for d in (rec.get("discoveries") or []) if isinstance(d, str) and ":" not in d
        ]:
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
        for old in _refs(rec.get("supersedes"), "DEC") + [
            d for d in (rec.get("supersedes") or []) if isinstance(d, str) and ":" not in d
        ]:
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

    # Citation counts drive discovery GC.
    cited: dict[str, int] = {k: 0 for k in dsc}
    for rec in list(ws.values()) + list(dec.values()):
        for ref in _refs(rec.get("discoveries"), "DSC") + [
            d for d in (rec.get("discoveries") or []) if isinstance(d, str) and ":" not in d
        ]:
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


# ---------------------------------------------------------------- commands


def cmd_validate(args: argparse.Namespace) -> int:
    store = Path(args.root) if args.root else _DEFAULT_STORE
    if not store.exists():
        # Fail-OPEN: an absent store is a not-yet-adopted repo, not a broken one.
        print(f"::warning title=agentos::no agentos/ store at {store} — nothing to validate",
              flush=True)
        return 0

    programs = _load_programs()
    if programs is None:
        print("::warning title=agentos::config/mastermind_programs.yml unreadable — "
              "program keys not validated (fail-open join)", flush=True)

    problems: list[Problem] = []
    records: dict[str, dict[str, Any]] = {}
    paths: dict[str, Path] = {}
    counts = {"workstreams": 0, "decisions": 0, "discoveries": 0}

    specs = (
        ("workstreams", "WS", "WS-", check_workstream),
        ("decisions", "DEC", "DEC-", check_decision),
        ("discoveries", "DSC", "DSC-", check_discovery),
    )
    for folder, prefix, fileprefix, checker in specs:
        directory = store / folder
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            if not path.name.startswith(fileprefix):
                problems.append(
                    Problem(path, "bad-filename",
                            f"{folder}/ files must start with '{fileprefix}'", hard=True)
                )
                continue
            try:
                rec, _body = parse_record(path)
            except ValueError as exc:
                problems.append(Problem(path, "unparseable", str(exc), hard=True))
                continue
            counts[folder] += 1
            key = rec.get("key")
            if isinstance(key, str) and key:
                ident = f"{prefix}/{key}"
                if ident in records:
                    problems.append(
                        Problem(path, "duplicate-key",
                                f"key {key!r} already defined at {paths[ident]}", hard=True)
                    )
                else:
                    records[ident] = rec
                    paths[ident] = path
            problems.extend(
                checker(rec, path, programs) if checker is check_workstream else checker(rec, path)
            )

    problems.extend(check_references(records, paths))

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
        f"{counts['discoveries']} discoveries) — "
        f"{len(hard)} error(s), {len(warn)} warning(s)"
    )
    print(summary, flush=True)
    return 1 if hard else 0


def _not_yet(phase: str, doc: str) -> int:
    """A stub must be unmistakably a stub — never a silent success."""
    print(f"::warning title=agentos::not implemented until {phase}; see {doc}", flush=True)
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    return _not_yet("Phase 2", "research/MASTERMIND_AGENT_OS_V1_IMPLEMENTATION_PLAN.md")


def cmd_brief(_args: argparse.Namespace) -> int:
    return _not_yet("Phase 2", "research/MASTERMIND_CEO_BRIEF_SPEC.md")


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

    for name, func, helptext in (
        ("status", cmd_status, "materialize agent_os_state.v1 (Phase 2)"),
        ("brief", cmd_brief, "CEO brief (Phase 2)"),
        ("compile-context", cmd_compile_context, "context bundle (Phase 3)"),
    ):
        node = sub.add_parser(name, help=helptext)
        node.add_argument("--workstream", help="workstream key")
        node.set_defaults(func=func)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
