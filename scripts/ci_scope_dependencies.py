#!/usr/bin/env python3
"""Shared, fail-closed dependency discovery for path-aware CI selection.

The trigger-closure guard and the CI pack selector ask the same static question:
which existing repository files can affect a named pytest suite?  This module owns
that answer so the two gates cannot quietly drift apart.

``direct_reads`` and ``closure`` intentionally preserve the trigger guard's
historic depth/provenance behaviour.  ``suite_dependency_closure`` is the wider
selector-facing API: it follows existing first-party Python imports to a fixed
point, includes the suite itself, and reports constructs that static analysis
cannot prove exact. A caller must either widen ownership across the opaque target
domain or keep that job always-on; ambiguity is never permission to skip work.
"""
from __future__ import annotations

import ast
import functools
import io
import re
import shlex
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

# Direct file execution must resolve this checkout's ``scripts`` package before
# any installed namesake.  The import-hygiene gate requires the unconditional
# pin because a conditional insertion can leave a foreign path at sys.path[0].
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from scripts.audit_unrun_tests import FIRST_PARTY, ROOT


# Keep this set identical to the former trigger-closure implementation.  ``data``
# is deliberately excluded there because nightly artifacts are not human-edited
# trigger subjects.
LITERAL_DIRS = tuple(FIRST_PARTY) + (
    "research", "tools", "config", "content", "templates", "contracts", "ops",
)
_PATH_LITERAL = re.compile(
    r"(?:" + "|".join(LITERAL_DIRS) + r")"
    r"/[\w./-]+\.[A-Za-z0-9_]{1,8}(?:#[\w.-]+)?"
)
_DATA_MARKER = re.compile(r"#\s*ci-trigger-closure:\s*data\b")
_SCAN_ROOTS = {
    "app", "admin", "collectors", "config", "content", "contracts", "data", "docs",
    "engine", "lib", "ops", "research", "scripts", "site", "templates",
    "tests", "tools", "worker",
}

# A code suffix must end a filename, not merely appear inside one.  The former
# substring test made ``.js`` match every ``*.json`` glob, so an artifact scan of
# a JSON directory was classified as a CODE traversal and claimed every Python
# file in eleven roots.  Measured 2026-08-11: that one character promoted 69
# json-only scans, including the hub modules 67 of the 181 legacy jobs import.
_CODE_SUFFIX_RE = re.compile(r"\.(?:py|js|mjs|cjs|ts|tsx|jsx)(?![A-Za-z0-9_])")

# Names that reach the filesystem.  A bare ``walk(...)`` is only ``os.walk`` when
# it was imported as such — ``engine/sector_intelligence/contracts.py`` defines a
# recursive JSON ``walk()`` that this classifier read as a tree scan and charged
# with four repository roots on 35 jobs.
_TRAVERSAL_LABELS = {
    "glob", "iglob", "rglob", "walk", "iterdir", "listdir", "scandir",
}
# Traversals that enumerate a directory wholesale: no filename pattern exists to
# constrain them, so they keep the full root claim.
_UNPATTERNED_TRAVERSALS = {"iterdir", "walk", "listdir", "scandir"}

# A traversal's PATTERN is statically legible even when its directory is not:
# ``d.glob("*.parquet")`` can only ever enumerate parquet files, wherever ``d``
# points, so a ``.json`` or ``.py`` edit cannot change what it returns.  The old
# classifier used the pattern only to pick a root SET and then claimed every file
# under those roots -- the single widest source of false ownership measured
# across the 181-job manifest (2026-08-11).
#
# The vocabulary is CLOSED on purpose: these are the artifact and code families
# this repository actually stores, so a derived scope stays reviewable and a
# stray extension cannot mint a pattern nobody expected.  An unlisted suffix
# stays UNCONSTRAINED -- the pre-existing behaviour -- so entries here can only
# ever narrow a claim, never widen one.
SCAN_SUFFIXES = frozenset({
    ".parquet", ".json", ".jsonl", ".ndjson", ".csv", ".tsv",
    ".yml", ".yaml", ".toml", ".md", ".txt", ".log",
    ".html", ".j2", ".css", ".js", ".mjs", ".py",
    ".png", ".svg", ".webp", ".woff2", ".gz", ".zip", ".pkl", ".sql", ".xml",
})
_SUFFIX_RE = re.compile(r"\.([A-Za-z0-9_]{1,8})$")


@dataclass(frozen=True)
class DependencyClosure:
    """Transitive existing-file closure plus reasons it cannot be trusted.

    ``files`` are canonical repository-relative POSIX paths and include the suite
    itself.  ``ambiguities`` is empty only when every traversed Python file was
    parseable and no opaque import/process/glob construct was observed.
    """

    files: tuple[str, ...]
    ambiguities: tuple[str, ...]

    @property
    def safe(self) -> bool:
        return not self.ambiguities


def _join_segments(node: ast.BinOp) -> tuple[ast.expr, list[str]] | None:
    """Flatten ``base / "a" / "b.py"`` into ``(base, ["a", "b.py"])``."""
    segments: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.BinOp) and isinstance(current.op, ast.Div):
        right = current.right
        if not (isinstance(right, ast.Constant) and isinstance(right.value, str)):
            return None
        segments.append(right.value)
        current = current.left
    if not segments:
        return None
    segments.reverse()
    return current, segments


def _mentions_file_dunder(node: ast.AST) -> bool:
    return any(
        isinstance(inner, ast.Name) and inner.id == "__file__"
        for inner in ast.walk(node)
    )


def _checkout_bases(tree: ast.Module) -> set[str]:
    """Module-level names bound to something derived from ``__file__``."""
    bases: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and _mentions_file_dunder(node.value):
            bases |= {target.id for target in node.targets if isinstance(target, ast.Name)}
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
            and _mentions_file_dunder(node.value)
        ):
            bases.add(node.target.id)
    return bases


def _docstring_ids(tree: ast.Module) -> set[int]:
    """Identities of Constant nodes that are docstrings, so prose is excluded."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        body = getattr(node, "body", None) or []
        first = body[0] if body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            out.add(id(first.value))
    return out


def _data_lines(source: str, tree: ast.Module) -> set[int]:
    """Lines a ``# ci-trigger-closure: data`` comment excludes from reads."""
    try:
        comments = [
            token.start[0]
            for token in tokenize.generate_tokens(io.StringIO(source).readline)
            if token.type == tokenize.COMMENT and _DATA_MARKER.search(token.string)
        ]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return set()
    if not comments:
        return set()

    literal_lines = {
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _PATH_LITERAL.fullmatch(node.value.strip())
    }
    statements = [node for node in ast.walk(tree) if isinstance(node, ast.stmt)]

    def span(node: ast.stmt) -> range:
        return range(node.lineno, (node.end_lineno or node.lineno) + 1)

    covered: set[int] = set()
    for line in comments:
        if line in literal_lines:
            covered.add(line)
            continue
        enclosing = [node for node in statements if line in span(node)]
        target = min(
            enclosing,
            key=lambda node: (node.end_lineno or node.lineno) - node.lineno,
            default=None,
        )
        if target is None:
            following = [node for node in statements if node.lineno > line]
            target = min(following, key=lambda node: node.lineno, default=None)
        if target is not None:
            covered |= set(span(target))
    return covered


def _resolve(module: str) -> list[str]:
    """Repository-relative files a dotted module can denote, existing only."""
    base = module.replace(".", "/")
    return [
        candidate
        for candidate in (f"{base}.py", f"{base}/__init__.py")
        if (ROOT / candidate).is_file()
    ]


def direct_reads(
    path: Path, *, collect_data: dict[str, str] | None = None
) -> dict[str, str]:
    """Return existing direct first-party reads with source-line provenance.

    This is the trigger-closure guard's established behaviour.  In particular,
    package ``__init__.py`` markers, prose/docstrings, synthetic tmp paths, missing
    paths, and explicitly data-marked literals are not returned.
    """
    files: dict[str, str] = {}

    def record(rel: str, kind: str, line: int) -> None:
        files.setdefault(rel, f"{kind} at line {line}")

    def excused(rel: str, kind: str, line: int) -> None:
        if collect_data is not None:
            collect_data.setdefault(rel, f"{kind} at line {line}")

    try:
        source = path.read_text(errors="ignore")
        tree = ast.parse(source)
    except SyntaxError:
        return files

    bases = _checkout_bases(tree)
    docstrings = _docstring_ids(tree)
    data_lines = _data_lines(source, tree)

    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module]
            if node.module.split(".")[0] in FIRST_PARTY:
                names += [f"{node.module}.{alias.name}" for alias in node.names]
        for name in names:
            if name.split(".")[0] in FIRST_PARTY:
                for rel in _resolve(name):
                    record(rel, "import", node.lineno)

        if isinstance(node, ast.Call) and node.args:
            func = node.func
            label = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            first = node.args[0]
            if (
                label == "import_module"
                and isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and first.value.split(".")[0] in FIRST_PARTY
            ):
                for rel in _resolve(first.value):
                    record(rel, "import_module", node.lineno)

        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            match = _PATH_LITERAL.fullmatch(node.value.strip())
            if match and (ROOT / match.group(0).split("#")[0]).is_file():
                rel = match.group(0).split("#")[0]
                if node.lineno in data_lines:
                    excused(rel, "path literal", node.lineno)
                else:
                    record(rel, "path literal", node.lineno)

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            chain = _join_segments(node)
            if chain is not None:
                base, segments = chain
                rooted = _mentions_file_dunder(base) or (
                    isinstance(base, ast.Name) and base.id in bases
                )
                joined = "/".join(segments)
                if (
                    rooted
                    and joined.split("/")[0] in LITERAL_DIRS
                    and (ROOT / joined).is_file()
                ):
                    if node.lineno in data_lines:
                        excused(joined, "path join", node.lineno)
                    else:
                        record(joined, "path join", node.lineno)

    kept = {rel: why for rel, why in files.items() if not rel.endswith("__init__.py")}
    if collect_data is not None:
        for rel in list(collect_data):
            if rel in kept or rel.endswith("__init__.py"):
                del collect_data[rel]
    return kept


def closure(
    start: Path,
    depth: int,
    cache: dict[str, dict[str, str]],
    data_cache: dict[str, dict[str, str]] | None = None,
) -> dict[str, str]:
    """Return reads reachable from ``start`` in at most ``depth`` hops."""
    def reads(path: Path) -> dict[str, str]:
        key = path.as_posix()
        if key not in cache:
            excused: dict[str, str] = {}
            cache[key] = direct_reads(path, collect_data=excused)
            if data_cache is not None:
                data_cache[key] = excused
        return cache[key]

    seen: dict[str, str] = {}
    frontier: list[tuple[Path, int, str]] = [(start, 0, "")]
    while frontier:
        current, level, via = frontier.pop()
        for rel, why in reads(current).items():
            if rel in seen:
                continue
            seen[rel] = why if not via else f"{why} of {via}"
            if level + 1 < depth and rel.endswith(".py"):
                frontier.append((ROOT / rel, level + 1, rel))
    return seen


def _relative_import_modules(rel: str, node: ast.ImportFrom) -> list[str]:
    """Resolve one ``from .`` import against the file's real package.

    Relative imports are common in ``admin/`` and ``app/``.  Ignoring them would
    let a change to (for example) ``admin/config_store.py`` skip a suite that
    imports ``admin.ai_cost`` and reaches the store through ``from . import``.
    Python's level is one-based: one dot keeps the current package, two dots pop
    one package component, and so on.
    """
    package = list(Path(rel).parent.parts)
    pops = node.level - 1
    if pops > len(package):
        return []
    if pops:
        package = package[:-pops]
    if node.module:
        package.extend(node.module.split("."))
    if not package:
        return []
    base = ".".join(package)
    return [base, *(f"{base}.{alias.name}" for alias in node.names)]


def _all_existing_import_reads(rel: str, tree: ast.Module) -> set[str]:
    """Resolve absolute and relative imports from any repository package."""
    out: set[str] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                names = _relative_import_modules(rel, node)
            elif node.module:
                names = [node.module]
                names += [f"{node.module}.{alias.name}" for alias in node.names]
        for name in names:
            out.update(_resolve(name))
        if isinstance(node, ast.Call) and node.args:
            label = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", "")
            )
            first = node.args[0]
            if (
                label in {"import_module", "__import__"}
                and isinstance(first, ast.Constant)
                and isinstance(first.value, str)
            ):
                out.update(_resolve(first.value))
    return out


def _traversal_provenance(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Names that prove a bare traversal call really is ``os``/``glob``.

    Returns the names imported FROM ``os``/``glob`` and the names bound to a
    module-local callable.  A bare name in neither set is treated as a traversal,
    because an unknown callable must not be assumed inert.
    """
    imported: set[str] = set()
    local: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in {"os", "glob", "os.path"}:
            imported.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name in _TRAVERSAL_LABELS
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in _TRAVERSAL_LABELS:
                local.add(node.name)
        elif isinstance(node, ast.Assign):
            local.update(
                target.id
                for target in node.targets
                if isinstance(target, ast.Name) and target.id in _TRAVERSAL_LABELS
            )
    return imported, local


def _is_traversal_call(node: ast.Call, imported: set[str], local: set[str]) -> bool:
    """Whether this call really reaches the filesystem."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in _TRAVERSAL_LABELS
    name = getattr(func, "id", "")
    if name not in _TRAVERSAL_LABELS:
        return False
    return name in imported or name not in local


def _pattern_suffix(value: str) -> str | None:
    """The filename suffix a glob pattern can yield, when it is literal.

    The last component must actually be a PATTERN. A fixed name such as
    ``glob("v1.2")`` names one entry that may well be a directory, and reading
    its ``.2`` as a file kind would under-claim everything inside it.
    """
    tail = value.replace("\\", "/").rsplit("/", 1)[-1]
    if not any(char in tail for char in "*?["):
        return None
    match = _SUFFIX_RE.search(tail)
    if not match:
        return None
    suffix = f".{match.group(1)}"
    return suffix if suffix in SCAN_SUFFIXES else None


def _literal_pattern(node: ast.expr) -> str | None:
    """The literal tail of a glob pattern argument, if it has one.

    ``str(base / "holdings" / "*" / "*.parquet")`` and f-strings both end in the
    constant that bounds the filename, so the tail is what is read here.
    """
    while True:
        if isinstance(node, ast.Call) and node.args and (
            getattr(node.func, "id", "") in {"str", "fspath"}
            or getattr(node.func, "attr", "") in {"as_posix", "__str__"}
        ):
            node = node.args[0]
            continue
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            node = node.right
            continue
        break
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr) and node.values:
        tail = node.values[-1]
        if isinstance(tail, ast.Constant) and isinstance(tail.value, str):
            return tail.value
    return None


def _traversal_suffixes(node: ast.Call) -> frozenset[str]:
    """Suffixes this traversal can enumerate; empty means unconstrained.

    ``iterdir``/``walk``/``listdir``/``scandir`` enumerate a directory wholesale
    and take no filename pattern, so they are never constrained here.
    """
    func = node.func
    label = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if label in _UNPATTERNED_TRAVERSALS or not node.args:
        return frozenset()
    suffixes: list[str] = []
    for argument in node.args:
        raw = _literal_pattern(argument)
        suffix = _pattern_suffix(raw) if raw is not None else None
        if suffix is None:
            return frozenset()
        suffixes.append(suffix)
    return frozenset(suffixes)


def _source_ambiguities(path: Path, tree: ast.Module) -> set[str]:
    """Opaque edges that require an always-on job instead of a guessed scope."""
    findings: set[str] = set()
    subprocess_modules: set[str] = {"subprocess"}
    subprocess_calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    subprocess_modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            subprocess_calls.update(alias.asname or alias.name for alias in node.names)

    rel = path.relative_to(ROOT).as_posix()
    docstrings = _docstring_ids(tree)
    module_scan_roots: set[str] = set()
    for candidate in ast.walk(tree):
        if (
            isinstance(candidate, ast.Constant)
            and isinstance(candidate.value, str)
            and id(candidate) not in docstrings
        ):
            value = candidate.value.strip().replace("\\", "/").lstrip("./")
            first = value.split("/", 1)[0]
            if first in _SCAN_ROOTS:
                module_scan_roots.add(first)
        elif isinstance(candidate, ast.Name) and candidate.id.lower() in {
            "data_dir", "data_root",
        }:
            module_scan_roots.add("data")
        elif isinstance(candidate, ast.Attribute) and candidate.attr.lower() in {
            "data_dir", "data_root",
        }:
            module_scan_roots.add("data")
    imported_traversals, local_traversals = _traversal_provenance(tree)
    module_has_code_scan = False
    for candidate in ast.walk(tree):
        if not isinstance(candidate, ast.Call):
            continue
        if not _is_traversal_call(candidate, imported_traversals, local_traversals):
            continue
        strings = [
            inner.value.lower()
            for inner in ast.walk(candidate)
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str)
        ]
        if any(_CODE_SUFFIX_RE.search(value) for value in strings):
            module_has_code_scan = True

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        label = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        first = node.args[0] if node.args else None
        if label in {"import_module", "__import__"} and not (
            isinstance(first, ast.Constant) and isinstance(first.value, str)
        ):
            findings.add(f"{rel}:{node.lineno}: dynamic import")
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in subprocess_modules
        ) or (isinstance(func, ast.Name) and func.id in subprocess_calls):
            roots = set(module_scan_roots)
            if roots:
                findings.add(
                    f"{rel}:{node.lineno}: subprocess roots={','.join(sorted(roots))}"
                )
            else:
                findings.add(f"{rel}:{node.lineno}: subprocess invocation")
        if _is_traversal_call(node, imported_traversals, local_traversals):
            strings = [
                inner.value.lower()
                for inner in ast.walk(node)
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str)
            ]
            if module_scan_roots:
                kind = f"filesystem roots={','.join(sorted(module_scan_roots))}"
            elif module_has_code_scan or any(
                _CODE_SUFFIX_RE.search(value) for value in strings
            ):
                kind = "filesystem code traversal"
            elif strings:
                kind = "filesystem artifact traversal"
            else:
                kind = "filesystem glob"
            suffixes = _traversal_suffixes(node)
            if suffixes:
                kind += f" suffixes={','.join(sorted(suffixes))}"
            findings.add(f"{rel}:{node.lineno}: {kind}")
    return findings


@functools.lru_cache(maxsize=None)
def _selector_file_analysis(rel: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Cache one immutable checkout file's selector-facing static analysis.

    A manifest names more than a thousand suites whose transitive closures share
    the same engine/lib modules.  Without this per-file cache, deriving scopes
    reparses those shared modules hundreds of times and costs minutes before any
    test starts.  A GitHub job's checkout is immutable for the life of the process,
    so caching by canonical repository path is exact.
    """
    path = ROOT / rel
    try:
        tree = ast.parse(path.read_text(errors="ignore"))
    except SyntaxError as exc:
        return (), (f"{rel}:{exc.lineno or 0}: syntax error",)
    reads = set(direct_reads(path)) | _all_existing_import_reads(rel, tree)
    return tuple(sorted(reads)), tuple(sorted(_source_ambiguities(path, tree)))


def pytest_invocation_ambiguities(command: str) -> tuple[str, ...]:
    """Report pytest command shapes whose suite inventory is not explicit.

    Directory targets are load-bearing here: ``pytest tests/`` discovers a
    runtime-dependent set, so no static per-suite closure may be used to skip it.
    """
    try:
        tokens = shlex.split(command, comments=False, posix=True)
    except ValueError as exc:
        return (f"unparseable pytest invocation: {exc}",)

    start: int | None = None
    for index, token in enumerate(tokens):
        if token == "pytest":
            start = index + 1
            break
        if token == "-m" and index + 1 < len(tokens) and tokens[index + 1] == "pytest":
            start = index + 2
            break
    if start is None:
        return ()

    findings: set[str] = set()
    for token in tokens[start:]:
        if token.startswith("-"):
            continue
        target = token.split("::", 1)[0]
        if any(char in target for char in "*$?[]{}"):
            findings.add(f"dynamic pytest target {token!r}")
            continue
        candidate = ROOT / target
        if candidate.is_dir():
            findings.add(f"directory pytest target {token!r}")
    return tuple(sorted(findings))


def suite_dependency_closure(
    suite: str | Path, *, pytest_command: str | None = None
) -> DependencyClosure:
    """Return a suite's transitive existing repo-file closure and ambiguities.

    Import cycles terminate through ``visited``.  Existing imports from every
    repository package are followed, including shared helpers under ``tests/``;
    third-party imports resolve to no repository file and are ignored.  Any
    ambiguity is evidence for an always-on/full run, not a partial scope.
    """
    path = Path(suite)
    if not path.is_absolute():
        path = ROOT / path
    try:
        rel = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return DependencyClosure((), (f"suite is outside repository: {path}",))
    if not path.is_file():
        return DependencyClosure((), (f"suite does not exist: {rel}",))

    files: set[str] = {rel}
    ambiguities: set[str] = set()
    frontier = [path]
    visited: set[str] = set()
    while frontier:
        current = frontier.pop()
        current_rel = current.relative_to(ROOT).as_posix()
        if current_rel in visited:
            continue
        visited.add(current_rel)
        reads_raw, ambiguity_raw = _selector_file_analysis(current_rel)
        ambiguities.update(ambiguity_raw)
        reads = set(reads_raw)
        for dependency in reads:
            dependency_path = ROOT / dependency
            if not dependency_path.is_file():
                continue
            files.add(dependency)
            if dependency.endswith(".py") and dependency not in visited:
                frontier.append(dependency_path)

    if pytest_command is not None:
        ambiguities.update(pytest_invocation_ambiguities(pytest_command))
    return DependencyClosure(tuple(sorted(files)), tuple(sorted(ambiguities)))
