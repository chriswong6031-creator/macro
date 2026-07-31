"""No undefined name may reach the publisher's dispatch loop.

TWICE IN ONE DAY (2026-07-30) a gate shipped green while referencing a name that
does not exist:

  * `counters["quarantined_bare_cashtag"] = ...` — a dict defined nowhere;
  * `OB.transition(...)` — a module alias that exists in a different file.

Both sat in the bare-cashtag / unknown-cashtag branches, and both would have
raised NameError the FIRST time the gate actually fired. The dispatch loop has no
try/except around it, so the exception escapes `main()`: not a missed post, a
total publish outage, on the exact code path written to protect the account.

They shipped green because every test aimed at those gates exercised the PURE
PREDICATE (`_bare_cashtag_post`, `_unknown_cashtags`) and never walked the loop
that calls it. A branch whose body no test enters is a branch the interpreter has
never parsed for names.

This is the cheap structural guard: bind-before-use across the whole module. It
would have caught both in under a second.
"""
from __future__ import annotations

import ast
import builtins
from pathlib import Path

import pytest

TARGETS = [
    "scripts/marketing_publisher.py",
    "engine/marketing/content_studio.py",
    "engine/marketing/copywriter.py",
    "engine/marketing/copy_auditor.py",
    "engine/marketing/breaking_relevance.py",
    "scripts/hot_tape_radar.py",
]


def _module_bindings(tree: ast.Module) -> set[str]:
    """Every name bound at module scope: imports, defs, classes, assignments."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                out.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            out.add(node.id)
        elif isinstance(node, ast.Global):
            out.update(node.names)
    return out


def _own_bindings(fn: ast.AST) -> set[str]:
    """Names bound by THIS function itself.

    Does not descend into nested functions/lambdas — those get their own scope
    and inherit this one, which is how Python actually resolves names. An
    earlier version flattened everything and then reported every CLOSURE
    variable and every LAMBDA parameter as undefined: 11 false positives and
    zero real ones, which is worse than no check at all.
    """
    out: set[str] = set()
    args = getattr(fn, "args", None)
    if args is not None:
        for group in (args.posonlyargs, args.args, args.kwonlyargs):
            out.update(a.arg for a in group)
        for extra in (args.vararg, args.kwarg):
            if extra is not None:
                out.add(extra.arg)

    def _walk(node: ast.AST, *, top: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.add(child.name)          # the def's NAME is bound here...
                continue                      # ...its body is a separate scope
            if isinstance(child, ast.Lambda):
                continue                      # lambda params belong to the lambda
            if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
                out.add(child.id)
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                for a in child.names:
                    out.add((a.asname or a.name).split(".")[0])
            elif isinstance(child, ast.ExceptHandler) and child.name:
                out.add(child.name)
            elif isinstance(child, ast.Global):
                out.update(child.names)
            _walk(child, top=False)

    _walk(fn, top=True)
    return out


def _check_scope(node: ast.AST, inherited: set[str], rel: str,
                 fname: str, offenders: list[str]) -> None:
    """Recursive scope walk: a nested function inherits its parents' names."""
    scope = inherited | _own_bindings(node)
    for child in ast.iter_child_nodes(node):
        _visit(child, scope, rel, fname, offenders)


def _visit(node: ast.AST, scope: set[str], rel: str,
           fname: str, offenders: list[str]) -> None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        _check_scope(node, scope, rel, node.name, offenders)
        return
    if isinstance(node, ast.Lambda):
        _check_scope(node, scope, rel, f"{fname}:<lambda>", offenders)
        return
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
        if node.id not in scope:
            offenders.append(
                f"{rel}:{node.lineno} reads undefined '{node.id}' in {fname}()")
    for child in ast.iter_child_nodes(node):
        _visit(child, scope, rel, fname, offenders)


@pytest.mark.parametrize("rel", TARGETS)
def test_every_name_read_is_bound_somewhere(rel):
    path = Path(rel)
    if not path.exists():
        pytest.skip(f"{rel} absent in this checkout")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    known = _module_bindings(tree) | set(dir(builtins)) | {
        "__file__", "__name__", "__doc__", "__spec__", "__package__"}

    offenders: list[str] = []
    for fn in tree.body:
        _visit(fn, known, rel, "<module>", offenders)
    assert not offenders, (
        "undefined name(s) — these raise NameError the first time the branch "
        "runs:\n  " + "\n  ".join(sorted(set(offenders))[:20])
    )


def test_the_guard_actually_catches_the_bug_it_was_written_for():
    """A guard that cannot fail is decoration. Feed it the real defect.

    This is the exact shape that shipped twice on 2026-07-30: a quarantine
    branch calling a module alias that exists in a different file.
    """
    src = (
        "import logging\n"
        "def main(items, live, root):\n"
        "    for it in items:\n"
        "        if it:\n"
        "            OB.transition(it, 'quarantined', root=root)\n"
        "            continue\n"
        "    return 0\n"
    )
    tree = ast.parse(src)
    known = _module_bindings(tree) | set(dir(builtins))
    offenders: list[str] = []
    for fn in tree.body:
        _visit(fn, known, "<synthetic>", "<module>", offenders)
    assert any("OB" in o for o in offenders), offenders


def test_the_guard_does_not_flag_closures_or_lambdas():
    """The false positives that made the first version useless."""
    src = (
        "def outer(rows, cfg):\n"
        "    def inner(x):\n"
        "        return cfg.get(x)\n"
        "    best = sorted(rows, key=lambda kv: -kv[1])\n"
        "    return [inner(r) for r in best]\n"
    )
    tree = ast.parse(src)
    known = _module_bindings(tree) | set(dir(builtins))
    offenders: list[str] = []
    for fn in tree.body:
        _visit(fn, known, "<synthetic>", "<module>", offenders)
    assert offenders == [], offenders
