#!/usr/bin/env python3
"""Regression fence: no anonymous canonical-Macro GitHub-distribution dependency
may reappear in executable/config code (Sol Day-6 AMENDMENT clause E,
DEC:B1-MACRO-PRIVATE-CUTOVER).

Before the cutover, the ``macro`` repository was PUBLIC, and several builders
and templates read data straight off GitHub's anonymous distribution surfaces
for it: ``raw.githubusercontent.com``, the ``<owner>.github.io`` Pages mirror,
the ``cdn.jsdelivr.net/gh`` CDN, and the ``api.github.com/repos/.../contents``
read API — plus plain ``git clone``/``fetch``/``ls-remote`` against an
unauthenticated ``https://github.com/<owner>/macro`` URL. Once the repo goes
private every one of those 404s (or, worse, silently starts serving stale
public-fork history), so clause E's census "cannot end as a one-time grep": a
future PR that reintroduces any of those constructions must fail CI.

CANONICAL MACRO OWNERS (same project; the second is the pre-rename alias) —
``mastermindx-market-intelligence`` and ``chriswong6031-creator`` — and repo
name ``macro``. Every banned shape below is keyed on those two strings, so an
unrelated third-party GitHub URL (``raw.githubusercontent.com/google/fonts/...``,
``cdn.jsdelivr.net/npm/@supabase/supabase-js@2/...``, someone else's
``api.github.com/repos/<owner>/<repo>``, ...) is untouched by construction —
this fence must never become "ban all GitHub URLs".

BANNED SHAPES
    1. raw.githubusercontent.com/<owner>/macro/...
    2. <owner>.github.io/macro...                  (GitHub Pages mirror)
    3. cdn.jsdelivr.net/gh/<owner>/macro...
    4. https://github.com/<owner>/macro(.git)?      when used as a bare
       clone/fetch/ls-remote target
    5. api.github.com/repos/<owner>/macro/(contents|git/blobs|git/trees)
    6. git@github.com:chriswong6031-creator/macro(.git)? or the
       equivalent ssh:// Git transport (old-owner executable/config target)

Shapes 1, 2, 3, and 5 are keyed on HOST + OWNER + REPO alone: those hosts have
no legitimate use once bound to the macro owner/repo other than pointing at
its (now-private) anonymous data-distribution surface, so ANY string literal
containing the prefix is flagged, wherever it sits in the file and regardless
of how it is later used — this is exactly what lets a MULTILINE/ASSEMBLED
construction (a module constant holding the host+owner+repo prefix, joined
with a ``{commit}``/path variable at the call site) get caught: the constant's
own literal text already contains the banned prefix, so a whole-file text scan
finds it without needing to trace the join.

Shape 4 is different: ``github.com/<owner>/macro`` by itself is also the
ordinary web URL for the repo's issue/PR/blob pages (see
``engine/quant_lab/specs.py``'s ``.../blob/main/...`` citation links or
``engine/stock_identity/pilot.py``'s ``.../pull/5660`` reference) — those are
citations for a human reader, not a data dependency, and must NOT be flagged.
The distinguishing signal this module uses is structural, not semantic: a
*bare* repository URL — ``https://github.com/<owner>/macro``,
optionally with a trailing ``.git`` and/or a single trailing ``/``, followed
immediately by a quote, whitespace, or end of string, with NO further path
segment — has no legitimate use other than as a clone/fetch/ls-remote target
(nobody links a human to a bare repo-root URL with `.git` on the end). Any
literal carrying a further path segment (``/blob/...``, ``/pull/...``,
``/tree/...``, ...) is a citation and is left alone.

ASSEMBLED CONSTRUCTIONS / LIMITS OF THIS DETECTOR
    The primary detector is a whole-file text/regex scan, which already
    subsumes the "module constant + join at the call site" shape (see above).
    For ``.py`` files this module ADDITIONALLY walks the AST looking for a
    ``subprocess.run``/``Popen``/``check_output``/``check_call`` call whose
    argv is a list/tuple literal containing ``"git"`` plus one of
    ``"clone"``/``"fetch"``/``"ls-remote"``, where another argv element is
    either a string literal carrying a banned prefix (already caught by the
    text scan; kept here for AST completeness) or a bare ``Name`` that is
    bound, anywhere at module level in the SAME file, to a string constant
    carrying a banned prefix (the "argument built from a name bound to a
    banned prefix" case). This is a best-effort SAME-FILE heuristic, not a
    full interprocedural dataflow analysis: it will not follow a banned
    constant across an import, through a dict/list of urls indexed at
    runtime, or through string formatting whose pieces are computed outside
    the module. A determined author can still construct a banned fetch this
    detector cannot see (see the module's own GAPS in its build report).
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

ALLOWLIST_PATH = REPO_ROOT / "config" / "macro_anon_dependency_allowlist.json"

# ---------------------------------------------------------------------------
# Canonical identity
# ---------------------------------------------------------------------------
CANONICAL_OWNERS: tuple[str, ...] = (
    "mastermindx-market-intelligence",
    "chriswong6031-creator",
)
CANONICAL_REPO = "macro"

_OWNER_ALT = "(?:" + "|".join(re.escape(o) for o in CANONICAL_OWNERS) + ")"
_REPO = re.escape(CANONICAL_REPO)
_OLD_OWNER = re.escape("chriswong6031-creator")

# ---------------------------------------------------------------------------
# Shape regexes — see module docstring for the reasoning behind each.
# ---------------------------------------------------------------------------
_SHAPE_PATTERNS: dict[str, re.Pattern[str]] = {
    "raw_githubusercontent": re.compile(
        rf"raw\.githubusercontent\.com/{_OWNER_ALT}/{_REPO}\b",
        re.IGNORECASE,
    ),
    "github_pages_mirror": re.compile(
        rf"{_OWNER_ALT}\.github\.io/{_REPO}\b",
        re.IGNORECASE,
    ),
    "jsdelivr_gh": re.compile(
        rf"cdn\.jsdelivr\.net/gh/{_OWNER_ALT}/{_REPO}\b",
        re.IGNORECASE,
    ),
    "api_contents_read": re.compile(
        rf"api\.github\.com/repos/{_OWNER_ALT}/{_REPO}/(?:contents|git/blobs|git/trees)\b",
        re.IGNORECASE,
    ),
    # Bare repo-root URL only — see docstring. No further path segment allowed.
    "clone_fetch_target": re.compile(
        rf"https://github\.com/{_OWNER_ALT}/{_REPO}"
        rf"(?![\w-])"          # not "macro-something" / "macrofoo"
        rf"(?:\.git)?"
        rf"/?"
        rf"(?=[\"'\s]|$)",     # nothing but a quote/whitespace/EOF follows
        re.IGNORECASE,
    ),
    # github.com serves BYTES on four sub-paths, so a repo-root-only rule (shape
    # 4) leaves them open: `/archive/...` is the whole tree as a tarball/zip,
    # `/raw/<ref>/<path>` is raw.githubusercontent under a different hostname,
    # `/releases/download/...` is an attached asset, and `/blob/...?raw=1`
    # bypasses the HTML view. Deliberately NOT matched, because they are
    # citations rather than data reads: /pull/, /issues/, /commit/, /compare/,
    # /tree/, and a plain /blob/ with no raw query.
    "anonymous_download_path": re.compile(
        rf"https://github\.com/{_OWNER_ALT}/{_REPO}/"
        rf"(?:archive/|raw/|releases/download/|blob/[^\"'\s]*[?&]raw=)",
        re.IGNORECASE,
    ),
    # Transport only: reject the retired personal owner when the string is an
    # executable/config Git remote, while keeping its PR/commit citations and
    # unrelated repositories lawful.
    "wrong_owner_transport": re.compile(
        rf"(?:git@github\.com:{_OLD_OWNER}/{_REPO}(?:\.git)?/?|"
        rf"ssh://git@github\.com/{_OLD_OWNER}/{_REPO}(?:\.git)?/?)"
        rf"(?=[\"'\s]|$)",
        re.IGNORECASE,
    ),
}

# Any banned shape's host+owner+repo prefix, used by the AST same-file
# heuristic to recognize a module-level constant as "bound to a banned
# prefix" even when it does not itself satisfy the stricter shape-4 rule
# (e.g. a constant that is later concatenated with more path). Built as the
# alternation of the five shape patterns themselves so it can never drift
# from them.
_ANY_BANNED_PREFIX = re.compile(
    "|".join(
        pattern.pattern
        for shape, pattern in _SHAPE_PATTERNS.items()
        if shape != "wrong_owner_transport"
    ),
    re.IGNORECASE,
)

_GIT_FETCH_VERBS = {"clone", "fetch", "ls-remote"}
_SUBPROCESS_FUNCS = {"run", "Popen", "check_output", "check_call"}

SCAN_EXTENSIONS = frozenset(
    {".py", ".sh", ".js", ".ts", ".tsx", ".mjs", ".yml", ".yaml", ".json", ".toml", ".j2", ".html"}
)

# Root-relative directory prefixes excluded from the walk (a guard's own
# tests, docs, and research/audit prose must be free to NAME the banned
# strings — that is not a live dependency). "worktrees" is matched at any
# depth because a sparse session worktree can nest under any directory.
EXCLUDE_ROOT_PREFIXES = (
    "research/",
    "agentos/",
    "docs/",
    "mockups/",
    "data/",
    "site/",
    "verify_shots/",
    "tests/",
    ".git/",
)

SESSION_WORKTREE_ROOT_PREFIXES = (
    ".claude/worktrees/",
    ".claire/worktrees/",
    ".codex/worktrees/",
    ".codex-worktrees/",
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    shape: str
    snippet: str
    allowlisted: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class AllowlistEntry:
    path: str
    reason: str
    reviewed_by: str


def _load_allowlist(root: Path) -> dict[str, AllowlistEntry]:
    allow_path = root / "config" / "macro_anon_dependency_allowlist.json"
    if not allow_path.is_file():
        return {}
    try:
        raw = json.loads(allow_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, AllowlistEntry] = {}
    for entry in raw.get("entries", []):
        path = entry.get("path")
        if not path:
            continue
        out[path] = AllowlistEntry(
            path=path,
            reason=entry.get("reason", ""),
            reviewed_by=entry.get("reviewed_by", ""),
        )
    return out


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _snippet_at(text: str, start: int, end: int, width: int = 90) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end].strip()
    return line[:width]


def _text_scan(text: str) -> list[tuple[str, int, str]]:
    """Whole-file scan for the four host-keyed shapes plus the bare clone URL.

    Returns (shape, line, snippet) triples. This is deliberately NOT
    line-by-line: scanning the whole file text means a module constant that
    holds a banned prefix is caught even though the {commit}/path suffix is
    only appended later, at a different call site.
    """
    hits: list[tuple[str, int, str]] = []
    for shape, pattern in _SHAPE_PATTERNS.items():
        for m in pattern.finditer(text):
            hits.append((shape, _line_of(text, m.start()), _snippet_at(text, m.start(), m.end())))
    return hits


def _module_level_banned_constants(tree: ast.Module) -> dict[str, int]:
    """Name -> lineno for every module-level ``NAME = "<literal w/ banned prefix>"``."""
    out: dict[str, int] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        text_val = None
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            text_val = value.value
        elif isinstance(value, ast.JoinedStr):
            # f-string: only the literal pieces are checkable statically.
            text_val = "".join(
                v.value for v in value.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str)
            )
        if text_val and _ANY_BANNED_PREFIX.search(text_val):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.lineno
    return out


def _call_func_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _string_literal_of(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _ast_subprocess_scan(text: str, banned_constants: dict[str, int]) -> list[tuple[str, int, str]]:
    """Flag ``subprocess.run(["git", "clone"/"fetch"/"ls-remote", ...])``-shaped
    calls whose argv references a banned host/owner/repo prefix either as a
    literal or via a module-level constant bound to one (see module docstring
    for what this heuristic does and does not catch).
    """
    hits: list[tuple[str, int, str]] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return hits
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_func_name(node) not in _SUBPROCESS_FUNCS:
            continue
        if not node.args:
            continue
        argv_node = node.args[0]
        if not isinstance(argv_node, (ast.List, ast.Tuple)):
            continue
        elts = argv_node.elts
        literal_strs = [_string_literal_of(e) for e in elts]
        has_git = any(s == "git" for s in literal_strs)
        has_verb = any(s in _GIT_FETCH_VERBS for s in literal_strs)
        if not (has_git and has_verb):
            continue
        for elt in elts:
            lit = _string_literal_of(elt)
            if lit and _ANY_BANNED_PREFIX.search(lit):
                hits.append(("clone_fetch_target", node.lineno, "subprocess argv literal carries banned prefix"))
                continue
            if isinstance(elt, ast.Name) and elt.id in banned_constants:
                hits.append((
                    "clone_fetch_target",
                    node.lineno,
                    f"subprocess argv built from {elt.id!r} (bound at line {banned_constants[elt.id]})",
                ))
    return hits


def find_anonymous_macro_dependencies(text: str, path: str) -> list[Finding]:
    """Detect banned-shape occurrences in ``text`` (a single file's contents).

    ``path`` is the file's (repo-relative, forward-slash) path — used only for
    reporting and to decide whether the Python-specific AST pass applies. This
    function does no file I/O and is safe to call on synthetic strings, which
    is how ``tests/test_macro_anon_dependency_guard.py`` self-tests it.
    """
    seen: set[tuple[str, int]] = set()
    findings: list[Finding] = []
    for shape, line, snippet in _text_scan(text):
        key = (shape, line)
        if key in seen:
            continue
        seen.add(key)
        findings.append(Finding(path=path, line=line, shape=shape, snippet=snippet))

    if path.endswith(".py"):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None
        if tree is not None:
            banned_constants = _module_level_banned_constants(tree)
            for shape, line, snippet in _ast_subprocess_scan(text, banned_constants):
                key = (shape, line)
                if key in seen:
                    continue
                seen.add(key)
                findings.append(Finding(path=path, line=line, shape=shape, snippet=snippet))

    return sorted(findings, key=lambda f: (f.line, f.shape))


def _is_excluded(rel_posix: str) -> bool:
    if rel_posix.endswith(".md"):
        return True
    # Only the four documented repo-root session directories are foreign
    # revisions. An ordinary tracked directory whose name happens to contain
    # "worktrees" remains in scope and must not become an evasion surface.
    if rel_posix.startswith(SESSION_WORKTREE_ROOT_PREFIXES):
        return True
    return any(rel_posix.startswith(prefix) for prefix in EXCLUDE_ROOT_PREFIXES)


def _iter_scan_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in SCAN_EXTENSIONS:
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if _is_excluded(rel):
            continue
        yield path, rel


def _walk(root: Path, allowlist: dict[str, AllowlistEntry]) -> list[Finding]:
    findings: list[Finding] = []
    for abspath, rel in _iter_scan_files(root):
        try:
            text = abspath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not text:
            continue
        for finding in find_anonymous_macro_dependencies(text, rel):
            entry = allowlist.get(rel)
            if entry is not None:
                findings.append(
                    Finding(
                        path=finding.path,
                        line=finding.line,
                        shape=finding.shape,
                        snippet=finding.snippet,
                        allowlisted=True,
                        reason=entry.reason,
                    )
                )
            else:
                findings.append(finding)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="Repository root to walk (default: this checkout's root).",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    allowlist = _load_allowlist(root)
    findings = _walk(root, allowlist)
    blocking = [f for f in findings if not f.allowlisted]
    allowlisted = [f for f in findings if f.allowlisted]

    for f in allowlisted:
        print(
            f"::notice title=macro-anon-dependency-allowlisted::{f.path}:{f.line} "
            f"[{f.shape}] {f.snippet} (allowlisted: {f.reason})",
            flush=True,
        )
    for f in blocking:
        print(
            f"::error title=macro-anon-dependency::{f.path}:{f.line} "
            f"[{f.shape}] anonymous canonical-Macro GitHub dependency: {f.snippet}",
            flush=True,
        )

    if blocking:
        print(
            f"::error title=macro-anon-dependency::{len(blocking)} blocking finding(s) "
            f"({len(allowlisted)} allowlisted, reported above but not blocking)",
            flush=True,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
