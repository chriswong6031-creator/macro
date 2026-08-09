"""Every name in a module's ``__all__`` must actually be bound by the module.

``__all__`` is a promise about the module's public surface: ``from m import *``
fetches each listed name with ``getattr`` and raises ``AttributeError`` on the
first one the module never bound.  A stale entry is therefore dormant — it
costs nothing until the first wildcard import lands, at which point an
unrelated PR breaks with a traceback pointing at the importer, not at the
module that broke its promise.

Found live: ``collectors/sec_document_spine.py`` listed
``"document_with_retrieval"`` — a name defined in
``engine/fundamental_forensics/sec_document_spine.py`` that the collector
never imported (it imports the sibling ``with_document_retrievals``).  Nothing
in-repo wildcard-imports that module today, which is the only reason it never
fired.

The check is static (AST), on the same grounds as
``tests/test_gh_annotation_line_start.py``: importing every module under
``scripts/`` and ``engine/`` inside CI would execute import-time side effects
and pay the full dependency-load bill for a property that is visible in the
source.  The trade: names bound only at runtime (``globals()[k] = v``, a
``global`` rebind inside a function) are invisible here — add such a module to
``EXEMPT`` with a reason.  Modules whose ``__all__`` is built dynamically
(comprehensions, helper calls) or that use ``from x import *`` are skipped
rather than guessed at.

One deliberate carve-out: in a package ``__init__.py``, an ``__all__`` entry
naming an existing sibling submodule is legitimate even when the file never
imports it — ``from pkg import *`` imports the listed submodules through the
import machinery rather than ``getattr`` (live case: ``engine/press``, whose
``__all__`` is exactly its seven submodules).  Entries that are neither bound
nor real submodules stay offenders.

Run: .venv/bin/python -m pytest tests/test_all_exports_resolve.py -q
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Same scan surface as the annotation guard: every directory whose modules are
# importable production/pipeline code.  ``tests/`` is excluded on purpose.
SCAN_DIRS = ("scripts", "engine", "collectors", "app", "admin", "lib", "tools", "research")

# relpath -> reason.  For modules whose ``__all__`` names are bound only at
# runtime and thus invisible to a static scan.
EXEMPT: dict[str, str] = {}

_TRY_STAR = getattr(ast, "TryStar", ())


def _module_scope(stmts):
    """Yield every statement that executes in module scope.

    Descends into branch/loop/with/try bodies (module scope runs them) but not
    into function or class bodies (those bind only their own name).
    """
    for s in stmts:
        yield s
        if isinstance(s, (ast.If, ast.For, ast.AsyncFor, ast.While)):
            yield from _module_scope(s.body)
            yield from _module_scope(s.orelse)
        elif isinstance(s, (ast.With, ast.AsyncWith)):
            yield from _module_scope(s.body)
        elif isinstance(s, ast.Try) or (_TRY_STAR and isinstance(s, _TRY_STAR)):
            yield from _module_scope(s.body)
            for h in s.handlers:
                yield from _module_scope(h.body)
            yield from _module_scope(s.orelse)
            yield from _module_scope(s.finalbody)
        elif isinstance(s, ast.Match):
            for case in s.cases:
                yield from _module_scope(case.body)


def _target_names(target: ast.expr, into: set[str]) -> None:
    if isinstance(target, ast.Name):
        into.add(target.id)
    elif isinstance(target, ast.Starred):
        _target_names(target.value, into)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _target_names(elt, into)
    # Attribute/Subscript targets bind no new module-level name.


def _str_elts(node: ast.expr) -> list[str] | None:
    """String elements of a List/Tuple/Set literal, else None."""
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return None
    out: list[str] = []
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            out.append(elt.value)
        else:
            return None
    return out


def _resolve_names(node: ast.expr, literal_lists: dict[str, list[str]]) -> list[str] | None:
    """Resolve an ``__all__`` value to a list of strings, or None if dynamic.

    Handles literal lists/tuples, references to earlier literal-list module
    constants, and ``+`` unions of the above (the ``_BASE + _EXTRA`` idiom).
    """
    if isinstance(node, ast.Name):
        return literal_lists.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _resolve_names(node.left, literal_lists)
        right = _resolve_names(node.right, literal_lists)
        if left is None or right is None:
            return None
        return left + right
    return _str_elts(node)


def _stale_exports(
    tree: ast.Module, submodules: frozenset[str] = frozenset()
) -> list[str]:
    """Names promised by ``__all__`` that the module never statically binds.

    ``submodules`` holds the sibling submodule names when the scanned file is
    a package ``__init__.py`` — listed submodules are importable by
    ``from pkg import *`` without any binding in the file itself.  Empty when
    the module has no ``__all__``, builds it dynamically, or uses a star
    import (both make the bound set unknowable statically).
    """
    bound: set[str] = set()
    literal_lists: dict[str, list[str]] = {}
    entries: list[str] | None = None
    star_import = False
    dynamic = False

    statements = list(_module_scope(tree.body))
    for s in statements:
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(s.name)
        elif isinstance(s, ast.Import):
            for alias in s.names:
                bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(s, ast.ImportFrom):
            for alias in s.names:
                if alias.name == "*":
                    star_import = True
                else:
                    bound.add(alias.asname or alias.name)
        elif isinstance(s, ast.Assign):
            targets: set[str] = set()
            for t in s.targets:
                _target_names(t, targets)
            bound |= targets
            if "__all__" in targets:
                resolved = _resolve_names(s.value, literal_lists)
                if resolved is None:
                    dynamic = True
                else:
                    entries = resolved
            elif len(targets) == 1:
                elts = _str_elts(s.value)
                if elts is not None:
                    literal_lists[next(iter(targets))] = elts
        elif isinstance(s, ast.AnnAssign):
            if s.value is not None and isinstance(s.target, ast.Name):
                bound.add(s.target.id)
        elif isinstance(s, ast.AugAssign):
            if isinstance(s.target, ast.Name):
                bound.add(s.target.id)
                if s.target.id == "__all__":
                    resolved = _resolve_names(s.value, literal_lists)
                    if resolved is None:
                        dynamic = True
                    else:
                        entries = (entries or []) + resolved
        elif isinstance(s, (ast.For, ast.AsyncFor)):
            _target_names(s.target, bound)
        elif isinstance(s, (ast.With, ast.AsyncWith)):
            for item in s.items:
                if item.optional_vars is not None:
                    _target_names(item.optional_vars, bound)
        elif isinstance(s, ast.Try) or (_TRY_STAR and isinstance(s, _TRY_STAR)):
            for handler in s.handlers:
                if handler.name:
                    bound.add(handler.name)
        elif isinstance(s, ast.Expr) and isinstance(s.value, ast.Call):
            call = s.value
            if (
                isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "__all__"
            ):
                if call.func.attr in {"extend", "append"} and len(call.args) == 1:
                    arg = call.args[0]
                    if call.func.attr == "append":
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            entries = (entries or []) + [arg.value]
                        else:
                            dynamic = True
                    else:
                        resolved = _resolve_names(arg, literal_lists)
                        if resolved is None:
                            dynamic = True
                        else:
                            entries = (entries or []) + resolved
                else:
                    dynamic = True

    # Walrus targets in module-scope expressions also bind; collected leniently
    # (a NamedExpr nested in a lambda/comprehension over-counts, which can only
    # hide a defect, never invent one).
    for s in statements:
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for sub in ast.walk(s):
            if isinstance(sub, ast.NamedExpr) and isinstance(sub.target, ast.Name):
                bound.add(sub.target.id)

    if entries is None or star_import or dynamic:
        return []
    return [
        name for name in entries if name not in bound and name not in submodules
    ]


def test_every_all_entry_is_bound() -> None:
    offenders: list[str] = []
    for directory in SCAN_DIRS:
        base = ROOT / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if rel in EXEMPT:
                continue
            blob = path.read_bytes()
            if b"__all__" not in blob:
                continue
            try:
                tree = ast.parse(blob, filename=rel)
            except SyntaxError:
                continue  # unparsable files are another guard's problem
            submodules: frozenset[str] = frozenset()
            if path.name == "__init__.py":
                submodules = frozenset(
                    sib.stem if sib.suffix == ".py" else sib.name
                    for sib in path.parent.iterdir()
                    if (sib.suffix == ".py" and sib.name != "__init__.py")
                    or (sib.is_dir() and (sib / "__init__.py").is_file())
                )
            offenders.extend(
                f"{rel}: {name!r}" for name in _stale_exports(tree, submodules)
            )

    assert not offenders, (
        "__all__ lists a name the module never binds — `from m import *` would "
        "raise AttributeError. Either import/define the name or drop the entry; "
        "if the name is bound only at runtime, add the module to EXEMPT with a "
        "reason:\n  " + "\n  ".join(offenders)
    )
