"""Ratchet: no import-time logging.disable() in engine/, lib/, scripts/, research/.

``logging.disable()`` is PROCESS-GLOBAL state: executed at import time it mutes every
logger in the process for the rest of the run. Research/scripts CLIs that silence
themselves at module level therefore poison any process that merely *imports* them —
pytest collection, a guarded import from engine/ (donor.py -> tuning_harness, PR #1115),
a research harness importing a sibling — producing order-dependent test flakes. This has
bitten twice (research/signal_engine/walk_forward.py, then tuning_harness.py); this test
makes the third time a red build instead of a flake.

The rule: CLI silencers live under ``if __name__ == "__main__":`` (or inside a function),
never in straight-line module scope. Copy the comment idiom from
research/signal_engine/walk_forward.py. Anything else that runs at import — class bodies,
try/except, loops, non-__main__ ifs — counts as module level here, because it is.
"""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCAN_DIRS = ("engine", "lib", "scripts", "research")


def _is_main_guard(test: ast.expr) -> bool:
    """True for ``__name__ == "__main__"`` (either operand order)."""
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq)):
        return False
    operands = (test.left, *test.comparators)
    return (any(isinstance(o, ast.Name) and o.id == "__name__" for o in operands)
            and any(isinstance(o, ast.Constant) and o.value == "__main__" for o in operands))


def _is_logging_disable(call: ast.Call) -> bool:
    f = call.func
    return (isinstance(f, ast.Attribute) and f.attr == "disable"
            and isinstance(f.value, ast.Name) and f.value.id == "logging")


def _import_time_disables(node: ast.AST, hits: list[int]) -> None:
    """Collect line numbers of logging.disable() calls that execute at import time.

    Recurses through everything that runs on import (class bodies, try/except, loops,
    plain ifs) and stops at the two things that don't: function bodies and the body of
    an ``if __name__ == "__main__":`` guard (whose else-branch still runs on import).
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(child, ast.If) and _is_main_guard(child.test):
            for stmt in child.orelse:
                _import_time_disables(stmt, hits)
            continue
        if isinstance(child, ast.Call) and _is_logging_disable(child):
            hits.append(child.lineno)
        _import_time_disables(child, hits)


def _offenders() -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for d in _SCAN_DIRS:
        root = _ROOT / d
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (SyntaxError, UnicodeDecodeError):
                continue
            hits: list[int] = []
            _import_time_disables(tree, hits)
            if hits:
                out[path.relative_to(_ROOT).as_posix()] = hits
    return out


def test_no_module_level_logging_disable():
    offenders = _offenders()
    assert not offenders, (
        "logging.disable() at module level mutes every logger in the process for any "
        "importer (order-dependent pytest flakes — bitten twice: walk_forward.py, then "
        "tuning_harness.py in PR #1115). Move it (and its warnings.filterwarnings "
        "sibling) under `if __name__ == \"__main__\":` — copy the comment idiom from "
        f"research/signal_engine/walk_forward.py. Offenders (file: lines): {offenders}")


def test_checker_positive_control():
    """Guard the guard: a silently broken walker would make the lint pass forever."""
    src = textwrap.dedent("""
        import logging
        logging.disable(logging.CRITICAL)          # line 3: BAD, straight-line module scope
        class C:
            logging.disable(logging.CRITICAL)      # line 5: BAD, class bodies run on import
        try:
            logging.disable(logging.CRITICAL)      # line 7: BAD, try bodies run on import
        except Exception:
            pass
        if some_flag:
            logging.disable(logging.CRITICAL)      # line 11: BAD, non-__main__ if
        def f():
            logging.disable(logging.CRITICAL)      # ok: only runs when called
        if __name__ == "__main__":
            logging.disable(logging.CRITICAL)      # ok: the sanctioned CLI idiom
        else:
            logging.disable(logging.CRITICAL)      # line 17: BAD, else-branch runs on import
        if "__main__" == __name__:
            logging.disable(logging.CRITICAL)      # ok: reversed operands
    """)
    hits: list[int] = []
    _import_time_disables(ast.parse(src), hits)
    assert hits == [3, 5, 7, 11, 17], hits
