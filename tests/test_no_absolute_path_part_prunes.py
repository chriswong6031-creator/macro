"""tests/test_no_absolute_path_part_prunes.py — a tree-walk must prune on the
path RELATIVE to its scan root, never on the absolute one.

THE DEFECT THIS CLOSES (#3802). test_press_workflow's kill-switch guard walked
the repo and pruned like this:

    for path in _REPO.rglob("*.yml"):
        if ".claude" in path.parts or "worktrees" in path.parts:
            continue

The exclusion is meant to skip NESTED checkouts. But house law puts every agent
session in a `.claude/worktrees/<name>/` worktree, so the scan root's OWN
absolute parts contain both tokens, the `continue` fired for every file, and the
guard scanned 0 of 130 .yml files. It read green in the one checkout everybody
works in and was real only in CI — the whole press suite passed locally at 177
tests while ci-pack-0 went red.

A prune on `<loopvar>.parts` is unsafe for the same reason anywhere: it tests
the WHOLE path, including the part above the scan root, which the caller does
not control. `path.relative_to(root).parts` tests only what was scanned.

This is a source lint, in the shape of tests/test_gh_annotation_line_start.py:
the defect is invisible at runtime (the guard passes — it just checks nothing),
so it has to be caught in the source. Stdlib only, so it runs in a minimal-deps
CI pack.
"""
from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# Directories whose Python is ours to hold to this rule.
_SCANNED = ("tests", "scripts", "engine", "admin", "app", "lib", "collectors",
            "tools", "worker")

# Calls that produce a filesystem walk.
_WALKS = frozenset({"rglob", "glob", "iterdir", "walk", "scandir"})

# Real exemptions only, each with a reason. Empty is the goal: every entry is a
# place this guard has stopped guarding.
_ALLOWED: frozenset[tuple[str, int]] = frozenset()


def _walk_loop_vars(tree: ast.AST) -> dict[str, ast.For]:
    """loop variable -> For node, for loops iterating a filesystem walk."""
    out: dict[str, ast.For] = {}
    for loop in [n for n in ast.walk(tree) if isinstance(n, ast.For)]:
        calls = [c for c in ast.walk(loop.iter) if isinstance(c, ast.Call)]
        walks = any(
            (isinstance(c.func, ast.Attribute) and c.func.attr in _WALKS)
            or (isinstance(c.func, ast.Name) and c.func.id in _WALKS)
            for c in calls)
        if walks and isinstance(loop.target, ast.Name):
            out[loop.target.id] = loop
    return out


def absolute_part_prunes(source: str) -> list[tuple[int, str, str]]:
    """(lineno, loop_var, token) for every `<tok> in <loopvar>.parts` inside a walk.

    Only a membership test against the RAW loop variable is reported. The
    correct forms — `tok in path.relative_to(root).parts`, or a `rel = path.
    relative_to(root)` bound first — compare against something other than the
    loop variable and are not flagged.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return []
    hits: list[tuple[int, str, str]] = []
    for var, loop in _walk_loop_vars(tree).items():
        for cmp in [n for n in ast.walk(loop) if isinstance(n, ast.Compare)]:
            if not any(isinstance(o, ast.In) for o in cmp.ops):
                continue
            for comparator in cmp.comparators:
                if (isinstance(comparator, ast.Attribute)
                        and comparator.attr == "parts"
                        and isinstance(comparator.value, ast.Name)
                        and comparator.value.id == var):
                    hits.append((cmp.lineno, var, ast.unparse(cmp.left)))
    return hits


def _python_files() -> list[Path]:
    out: list[Path] = []
    for d in _SCANNED:
        root = _ROOT / d
        if root.is_dir():
            out += [p for p in root.rglob("*.py")
                    if "__pycache__" not in p.relative_to(root).parts]
    return sorted(out)


def test_no_walk_prunes_on_absolute_path_parts():
    """Every filesystem walk prunes on the path relative to its scan root."""
    files = _python_files()
    # Non-vacuity: a lint that reads no source proves nothing (the very bug).
    assert len(files) > 500, (
        f"only {len(files)} python files discovered — this lint has gone "
        "vacuous; check _SCANNED and the __pycache__ prune above."
    )

    bad: list[str] = []
    for path in files:
        rel = str(path.relative_to(_ROOT))
        for lineno, var, tok in absolute_part_prunes(
                path.read_text(encoding="utf-8")):
            if (rel, lineno) in _ALLOWED:
                continue
            bad.append(f"{rel}:{lineno}  `{tok} in {var}.parts`")

    assert not bad, (
        "these walks prune on the ABSOLUTE path, so they also match anything "
        "above the scan root — in a `.claude/worktrees/<name>/` checkout that "
        "silently skips every file (#3802):\n  " + "\n  ".join(bad)
        + "\n\nUse the path relative to the scan root instead:\n"
          "    rel = path.relative_to(root)\n"
          "    if \"<token>\" in rel.parts:\n"
          "        continue"
    )


def test_the_lint_catches_the_defect_it_was_written_for():
    """Pinned against the ACTUAL #3802 source, so the lint cannot rot into a
    shape that no longer recognises the bug that motivated it."""
    buggy = (
        "for path in _REPO.rglob('*.yml'):\n"
        "    if '.claude' in path.parts or 'worktrees' in path.parts:\n"
        "        continue\n"
        "    hits.append(f'{path.relative_to(_REPO)}: x')\n"
    )
    found = absolute_part_prunes(buggy)
    assert len(found) == 2, f"expected both tokens flagged, got {found}"
    assert {tok for _, _, tok in found} == {"'.claude'", "'worktrees'"}

    # NOTE the trailing `path.relative_to(_REPO)` above: the real bug DID call
    # relative_to — for the message, not the prune. An earlier cut of this lint
    # treated "relative_to appears somewhere in the loop" as proof of safety and
    # missed the bug entirely. The prune itself is what must be relative.


def test_the_lint_accepts_the_correct_forms():
    """Both repairs pass, so the fix this guard demands is actually available."""
    bound_first = (
        "for path in _REPO.rglob('*.yml'):\n"
        "    rel = path.relative_to(_REPO)\n"
        "    if '.claude' in rel.parts:\n"
        "        continue\n"
    )
    assert not absolute_part_prunes(bound_first)

    inline = (
        "for f in sorted(d.rglob('*.py')):\n"
        "    if '__pycache__' in f.relative_to(d).parts:\n"
        "        continue\n"
    )
    assert not absolute_part_prunes(inline)

    # A .parts membership test OUTSIDE any filesystem walk is not this defect.
    unrelated = (
        "def f(p):\n"
        "    if '..' in p.parts:\n"
        "        raise ValueError\n"
    )
    assert not absolute_part_prunes(unrelated)
