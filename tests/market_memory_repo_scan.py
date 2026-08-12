"""One shared read+parse of the production Python tree, per pytest process.

Six market-memory writer-exclusivity checks each prove that exactly one
sanctioned CLI calls a given store writer, and each of them used to walk
``app/``, ``engine/`` and ``scripts/`` on its own — 2,636 files, 70 MB, read and
``ast.parse``d nine separate times.  That was ~100s of the
``market-memory-contract`` job's ~9:20, all of it the same work.

This module does that read+parse ONCE, lazily, and hands back the small
structural facts the checks actually interrogate.  It is deliberately a
*fact* provider, not a *policy* provider: every allowlist, every function name,
every "is this an offender" predicate and every assertion stays in the test
that owns it.  Adding a consumer here must never move a rule out of a test.

Why derived name sets rather than the parsed trees themselves: retaining 2,636
``ast.Module`` objects for the life of the session measures at ~2.8 GB RSS on
this tree (and re-walking them per query still costs ~3.9s a pass).  Extracting
the callee/import names and dropping each tree keeps the whole session under
~200 MB and turns every subsequent query into a dict lookup.

Immutability is load-bearing.  Consumers share one cache, so everything handed
out is a tuple, a ``frozenset`` or a read-only mapping view — a consumer that
wants to filter has to build its own container.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, NamedTuple

ROOT = Path(__file__).resolve().parents[1]

#: The production trees the writer-exclusivity checks police, in the order they
#: have always been walked.  Widening this set widens every consumer at once —
#: it is not a knob, it mirrors the ``(ROOT / "app", ROOT / "engine",
#: ROOT / "scripts")`` tuple the checks each used to spell out.
PRODUCTION_TREES = ("app", "engine", "scripts")


class CalleeNames(NamedTuple):
    """Names appearing in callee position anywhere in one module.

    ``direct`` is every ``f`` in ``f(...)`` (``ast.Call`` over ``ast.Name``);
    ``attribute`` is every ``f`` in ``anything.f(...)`` (``ast.Call`` over
    ``ast.Attribute``).  The two stay separate so a consumer keeps the exact
    ``ast.Name``/``ast.Attribute`` discrimination it wrote by hand.  A callee
    that is neither — ``f()()``, ``(lambda: 1)()`` — contributes to neither,
    as it did in the hand-written walks.
    """

    direct: frozenset[str]
    attribute: frozenset[str]


class ImportNames(NamedTuple):
    """Names appearing in import position anywhere in one module.

    ``imported`` is every ``alias.name`` under ``import ...``; ``from_modules``
    is every ``ImportFrom.module`` (``""`` for a bare relative ``from . import
    x``, matching the ``node.module or ""`` the check spells out);
    ``from_names`` is every ``alias.name`` under ``from ... import ...``.
    """

    imported: frozenset[str]
    from_modules: frozenset[str]
    from_names: frozenset[str]


_EMPTY_CALLEES = CalleeNames(frozenset(), frozenset())
_EMPTY_IMPORTS = ImportNames(frozenset(), frozenset(), frozenset())


class _Scan(NamedTuple):
    paths: tuple[Path, ...]
    callees: Mapping[Path, CalleeNames]
    imports: Mapping[Path, ImportNames]


@lru_cache(maxsize=1)
def _scan() -> _Scan:
    """Read and parse every production module once.  Lazy; first caller pays."""
    paths: list[Path] = []
    callees: dict[Path, CalleeNames] = {}
    imports: dict[Path, ImportNames] = {}
    for parent in (ROOT / tree for tree in PRODUCTION_TREES):
        for path in parent.rglob("*.py"):
            paths.append(path)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            direct: set[str] = set()
            attribute: set[str] = set()
            imported: set[str] = set()
            from_modules: set[str] = set()
            from_names: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    called = node.func
                    if isinstance(called, ast.Name):
                        direct.add(called.id)
                    elif isinstance(called, ast.Attribute):
                        attribute.add(called.attr)
                elif isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    from_modules.add(node.module or "")
                    from_names.update(alias.name for alias in node.names)
            callees[path] = CalleeNames(frozenset(direct), frozenset(attribute))
            imports[path] = ImportNames(
                frozenset(imported), frozenset(from_modules), frozenset(from_names)
            )
    return _Scan(
        paths=tuple(paths),
        callees=MappingProxyType(callees),
        imports=MappingProxyType(imports),
    )


def production_python_paths() -> tuple[Path, ...]:
    """Every ``*.py`` under the production trees, absolute, walk order preserved.

    Exactly the union ``(ROOT / "app", ROOT / "engine", ROOT / "scripts")``
    each yielded from ``rglob("*.py")``, concatenated in that order.
    """
    return _scan().paths


def callee_names(path: Path) -> CalleeNames:
    """Callee names in ``path``; empty for a path outside the production trees."""
    return _scan().callees.get(path, _EMPTY_CALLEES)


def import_names(path: Path) -> ImportNames:
    """Import names in ``path``; empty for a path outside the production trees."""
    return _scan().imports.get(path, _EMPTY_IMPORTS)
