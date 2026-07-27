"""Every first-party `from X import Y` in the repo must resolve to something real.

WHY THIS EXISTS
---------------
macro#3779: `scripts/build_flow_leaders.py` and `scripts/build_leader_radar.py` both
imported `trading_dates_between` — a function `lib/nyse_calendar.py` has never
defined — from INSIDE a `try: ... except Exception: return False` block.  The
ImportError fired on every call, was swallowed, and two ">2 NYSE sessions stale"
SLAs returned "fresh" for every input for as long as they existed.

That PR shipped an AST guard covering `lib.nyse_calendar` alone.  Generalising the
same sweep across every first-party module found five more of the identical defect,
in three distinct shapes:

  engine/neuralweb/brief_context.py  ×3   `from engine import config`
        → no engine/config.py; the `except` substituted a __file__ parent-walk that
          only coincidentally equals lib.config.ROOT.  Invisible until the checkout
          moves.
  engine/pick_lab/profile.py         ×2   `from engine.data_store import store`
  scripts/build_hk_pick_lab.py       ×1   (same)
        → no engine/data_store.py; the store is `lib.store`.  Both HK and CN
          pick-lab benchmark loaders returned None unconditionally, forever.
  scripts/check_*.py, engine/alert_triage.py ×4  `from lib.logging import get_logger`
        → no lib/logging.py and no get_logger anywhere; the stdlib fallback was the
          only branch ever taken.
  tests/test_factor_contradictions.py     `from scripts.build_factor_panel import _dna_class`
        → real name is `_classify_dna`; the test skipped on every run since it landed.
  tests/test_china_participation.py       `from engine.china_participation import _TAPE_PATH`
        → no such name; sat behind a flag no caller ever set.

WHAT MAKES THIS CLASS INVISIBLE
-------------------------------
A function-local import inside a broad `except` is invisible to import-time errors,
to linters that only resolve module-level imports, and to any test that exercises
the swallowing path.  The surviving tests assert shape, not value — `isinstance(x,
bool)`, `callable(loader)`, `pytest.skip(...)` — all of which stay green while the
guarded behaviour is permanently degraded.

So this resolves the names STATICALLY.  No first-party module is imported: the
sweep is pure `ast` + `pathlib`, which keeps it runnable in the pytest-only CI lane
and immune to whatever import side effects the target modules carry.

FALSE-POSITIVE HANDLING (the reason this can be repo-wide rather than scoped)
----------------------------------------------------------------------------
  * `from pkg import submodule`  — resolved against the filesystem, not the AST.
  * names bound inside `if` / `try` / `for` / `while` / `with` at module scope —
    collected by descending into those bodies (including `except`/`else`/`finally`).
  * `if TYPE_CHECKING:` blocks — same mechanism.
  * a target module containing `from x import *` or a module-level `__getattr__`
    (PEP 562) — cannot be resolved statically, so its importers are skipped rather
    than guessed at.
  * genuinely dynamic cases — `_ALLOWED_UNRESOLVED` below, which is EMPTY today.

At the commit that introduced this file the sweep reports exactly zero findings
across all first-party roots, so it lands repo-wide with no allowlist.

Run:
    python -m pytest tests/test_first_party_import_names.py -q
"""
from __future__ import annotations

import ast
import os
from functools import lru_cache
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Top-level importable roots owned by this repo.  A `from <root>...` import is ours
# to resolve; anything else is a third-party package and out of scope.
FIRST_PARTY_ROOTS = frozenset({
    "admin", "app", "collectors", "engine", "lib", "scripts", "tests", "tools", "worker",
})

_SKIP_DIRS = frozenset({
    ".git", ".claude", ".venv", "venv", "__pycache__", "node_modules",
    "site", "data", "reports", "verify_shots",
})

# Import sites that cannot be resolved statically and are known-good.
# Format: (repo-relative path, module, name).  Keep this empty if you possibly can —
# every entry is a place this guard has stopped guarding.  Add a comment saying why.
_ALLOWED_UNRESOLVED: frozenset[tuple[str, str, str]] = frozenset()


# ---------------------------------------------------------------------------
# Static resolution
# ---------------------------------------------------------------------------

def _python_files(root: Path) -> list[Path]:
    """*.py under root, pruning _SKIP_DIRS without descending into them."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                out.append(Path(dirpath) / fn)
    return sorted(out)


@lru_cache(maxsize=None)
def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return None


def _module_file(root: Path, module: str) -> Path | None:
    """Filesystem file backing a dotted module name, if any."""
    base = root / Path(*module.split("."))
    for cand in (base.with_suffix(".py"), base / "__init__.py"):
        if cand.is_file():
            return cand
    return None


def _is_package_dir(root: Path, module: str) -> bool:
    return (root / Path(*module.split("."))).is_dir()


def _is_submodule(root: Path, module: str, name: str) -> bool:
    """`from pkg import name` where name is a module, not an attribute."""
    base = root / Path(*module.split("."))
    return (base / f"{name}.py").is_file() or (base / name / "__init__.py").is_file()


@lru_cache(maxsize=None)
def _module_scope_names(path: Path) -> tuple[frozenset[str], bool]:
    """Names bound at module scope, and whether the module is statically opaque.

    Descends into `if` / `try` / `for` / `while` / `with` bodies (a name bound in a
    conditional branch is still a module attribute) but NOT into function or class
    bodies (those bind locals, not module attributes).
    """
    tree = _parse(path)
    if tree is None:
        return frozenset(), True  # not this guard's job to enforce parseability

    names: set[str] = set()
    opaque = False

    def bind(target: ast.expr) -> None:
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                bind(elt)
        elif isinstance(target, ast.Starred):
            bind(target.value)

    def walk(body: list[ast.stmt]) -> None:
        nonlocal opaque
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    bind(t)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                bind(node.target)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    names.add(a.asname or a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if a.name == "*":
                        opaque = True  # re-exports we cannot enumerate
                    else:
                        names.add(a.asname or a.name)
            elif isinstance(node, (ast.If, ast.Try, ast.While, ast.With,
                                   ast.For, ast.AsyncFor, ast.AsyncWith)):
                walk(node.body)
                walk(getattr(node, "orelse", []))
                walk(getattr(node, "finalbody", []))
                for handler in getattr(node, "handlers", []):
                    walk(handler.body)

    walk(tree.body)
    if "__getattr__" in names:
        opaque = True  # PEP 562 dynamic module attributes
    return frozenset(names), opaque


def _resolve_module(node: ast.ImportFrom, path: Path, root: Path) -> str | None:
    """Absolute dotted module for an ImportFrom, resolving relative levels."""
    if node.level == 0:
        return node.module
    pkg_parts = list(path.relative_to(root).parts[:-1])
    up = node.level - 1
    if up:
        if up > len(pkg_parts):
            return None
        pkg_parts = pkg_parts[:-up]
    return ".".join(pkg_parts + ([node.module] if node.module else []))


@lru_cache(maxsize=None)
def _sweep(root: Path) -> tuple[tuple[str, ...], tuple[str, ...], int]:
    """Return (missing modules, missing names, number of import sites checked).

    Memoised: each test below sweeps a distinct root (the repo, or its own tmp_path),
    so the repo-wide pass runs once for the whole file rather than once per test.
    """
    missing_modules: list[str] = []
    missing_names: list[str] = []
    checked = 0

    for path in _python_files(root):
        tree = _parse(path)
        if tree is None:
            continue
        rel = path.relative_to(root).as_posix()

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = _resolve_module(node, path, root)
            if not module or module.split(".")[0] not in FIRST_PARTY_ROOTS:
                continue

            aliases = [a.name for a in node.names if a.name != "*"]
            if not aliases:
                continue

            mod_file = _module_file(root, module)
            if mod_file is None:
                # A package dir with no __init__.py can still host submodules.
                if _is_package_dir(root, module):
                    for name in aliases:
                        checked += 1
                        if _is_submodule(root, module, name):
                            continue
                        if (rel, module, name) in _ALLOWED_UNRESOLVED:
                            continue
                        missing_names.append(
                            f"{rel}:{node.lineno} — `from {module} import {name}`: "
                            f"{module} has no submodule or attribute `{name}`"
                        )
                    continue
                checked += len(aliases)
                missing_modules.append(
                    f"{rel}:{node.lineno} — `from {module} import "
                    f"{', '.join(aliases)}`: module {module} does not exist"
                )
                continue

            names, opaque = _module_scope_names(mod_file)
            if opaque:
                continue  # star-import or __getattr__ — not statically resolvable

            for name in aliases:
                checked += 1
                if name in names or _is_submodule(root, module, name):
                    continue
                if (rel, module, name) in _ALLOWED_UNRESOLVED:
                    continue
                missing_names.append(
                    f"{rel}:{node.lineno} — `from {module} import {name}`: "
                    f"{mod_file.relative_to(root).as_posix()} defines no `{name}`"
                )

    # Tuples: the lru_cache hands the SAME object to every caller.
    return tuple(missing_modules), tuple(missing_names), checked


# ---------------------------------------------------------------------------
# Guard the guard — a vacuous sweep would make every assertion below pass
# ---------------------------------------------------------------------------

def test_sweep_checks_a_meaningful_number_of_sites():
    """A broken walker would report zero findings AND zero work. Pin the work."""
    _, _, checked = _sweep(REPO)
    assert checked > 200, (
        f"only {checked} first-party import names resolved — the AST sweep is broken "
        "or _SKIP_DIRS has swallowed the source tree"
    )


def test_sweep_flags_a_known_bad_import(tmp_path):
    """Synthesise the #3779 defect and assert this guard catches it."""
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "__init__.py").write_text("")
    (tmp_path / "lib" / "cal.py").write_text("def is_session(d):\n    return True\n")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "builder.py").write_text(
        "def _check_stale(d):\n"
        "    try:\n"
        "        from lib.cal import trading_dates_between\n"
        "        return bool(trading_dates_between(d))\n"
        "    except Exception:\n"
        "        return False\n"
    )
    missing_modules, missing_names, _ = _sweep(tmp_path)
    assert not missing_modules
    assert len(missing_names) == 1, missing_names
    assert "trading_dates_between" in missing_names[0]


def test_sweep_flags_a_missing_module(tmp_path):
    """`from engine import config` where engine/config.py does not exist."""
    (tmp_path / "engine").mkdir()
    (tmp_path / "engine" / "__init__.py").write_text("")
    (tmp_path / "engine" / "user.py").write_text(
        "def f():\n"
        "    from engine.data_store import store\n"
        "    return store\n"
    )
    missing_modules, missing_names, _ = _sweep(tmp_path)
    assert len(missing_modules) == 1, missing_modules
    assert "engine.data_store" in missing_modules[0]


@pytest.mark.parametrize("source,should_flag", [
    # legitimate — submodule import
    ("from lib import sub", False),
    # legitimate — name bound inside a try at module scope
    ("from lib.cal import MAYBE", False),
    # legitimate — name bound inside an `if` at module scope
    ("from lib.cal import CONDITIONAL", False),
    # legitimate — name bound in an except handler
    ("from lib.cal import FALLBACK", False),
    # legitimate — aliased import re-export
    ("from lib.cal import aliased", False),
    # legitimate — class and async def
    ("from lib.cal import Thing", False),
    ("from lib.cal import go", False),
    # the real thing
    ("from lib.cal import nope", True),
])
def test_no_false_positives_on_conditional_definitions(tmp_path, source, should_flag):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "__init__.py").write_text("")
    (tmp_path / "lib" / "sub.py").write_text("")
    (tmp_path / "lib" / "cal.py").write_text(
        "import os as _os\n"
        "try:\n"
        "    MAYBE = 1\n"
        "except Exception:\n"
        "    FALLBACK = 2\n"
        "else:\n"
        "    OTHER = 3\n"
        "if _os.name == 'posix':\n"
        "    CONDITIONAL = 4\n"
        "from json import dumps as aliased\n"
        "class Thing:\n"
        "    pass\n"
        "async def go():\n"
        "    pass\n"
    )
    (tmp_path / "user.py").write_text(f"def f():\n    {source}\n    return 1\n")

    missing_modules, missing_names, _ = _sweep(tmp_path)
    assert not missing_modules
    assert bool(missing_names) is should_flag, (source, missing_names)


def test_star_import_makes_a_module_opaque_rather_than_noisy(tmp_path):
    """A module that re-exports via `*` must not produce phantom findings."""
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "__init__.py").write_text("")
    (tmp_path / "lib" / "cal.py").write_text("from os.path import *\n")
    (tmp_path / "user.py").write_text("from lib.cal import join\n")
    _, missing_names, _ = _sweep(tmp_path)
    assert not missing_names


def test_module_getattr_makes_a_module_opaque(tmp_path):
    """PEP 562 modules resolve attributes at runtime — do not guess."""
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "__init__.py").write_text("")
    (tmp_path / "lib" / "cal.py").write_text("def __getattr__(name):\n    return 1\n")
    (tmp_path / "user.py").write_text("from lib.cal import anything\n")
    _, missing_names, _ = _sweep(tmp_path)
    assert not missing_names


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def test_every_first_party_import_resolves():
    missing_modules, missing_names, _ = _sweep(REPO)
    problems = list(missing_modules) + list(missing_names)
    assert not problems, (
        "first-party imports that cannot resolve (each one is an ImportError waiting "
        "to be swallowed by an `except`):\n  " + "\n  ".join(problems)
    )
