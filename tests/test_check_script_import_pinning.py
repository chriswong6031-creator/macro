"""Entry scripts run by FILE PATH must resolve repo imports from THIS repo.

THE BUG THIS PINS
-----------------
``python3 scripts/check_x.py`` puts ``<repo>/scripts`` at ``sys.path[0]`` and the
repo root NOWHERE.  Every top-level repo import (``scripts.*``, ``engine.*``,
``lib.*``, ``collectors.*``) then resolves from whatever AMBIENT entries the host
carries: a sibling repo's editable install, a caller's ``PYTHONPATH``, a stray
site-packages directory.  Observed 2026-08-08 on a dev host — a sister repo's
editable install served a foreign ``scripts`` package, and
``scripts/check_government_revenue_projection.py`` both failed to import its own
module AND (with that path earlier on ``sys.path``) EXECUTED another
repository's ``build_government_revenue.py`` from inside a CI guard.

THE FIX IS A PAIR — both halves are required:

  1. every entry script pins its own repo root at ``sys.path[0]``::

         _ROOT = Path(__file__).resolve().parent.parent     # scripts/ci/ -> parents[2]
         sys.path.insert(0, str(_ROOT))

  2. ``scripts/__init__.py`` exists, so ``scripts`` is a REGULAR package.
     Without it ``scripts`` is a PEP 420 namespace portion, and
     ``PathFinder._get_spec`` keeps walking past namespace portions until it hits
     a REGULAR package — so a foreign ``scripts/__init__.py`` from a LATER
     ``sys.path`` entry beats our pin at position 0.

TEETH
-----
T0  scripts/__init__.py exists and is docstring-only.
T1  static: every check_*/ci script that imports repo packages carries the pin,
    ahead of any top-level repo import.
T1b static: the pin is the ONLY sys.path mutation in a guard-family file.  A
    call-time insert (check_live_worker.py once carried `sys.path.insert(0, ".")`
    inside a function) reorders resolution AFTER the pin ran and is invisible
    to T3, which execs only up to the pin — so the shape is banned outright.
T2  baseline: the wider scripts/** entry-script population may only SHRINK.
T3  dynamic: simulate bare invocation against a hostile decoy tree and prove
    every member of the check_*/ci family still resolves its repo imports from
    its own repo root.  This covers already-pinned members too.
T4  end-to-end: the named script that broke, run for real against the decoy.

The decoy is built here, in tmp_path.  Nothing in this file depends on the dev
host's ``.pth`` — CI runners do not have it, and the decoy is a harsher
adversary than that finder anyway (it is on ``sys.path``, which is consulted
BEFORE any appended meta-path finder).

Regenerate the T2 baseline with::

    python3 tests/test_check_script_import_pinning.py --emit-baseline
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "script_import_pin_baseline.txt"

#: Top-level import targets that live in THIS repo.
REPO_PACKAGES = frozenset({
    "admin", "app", "collectors", "engine", "lib", "research", "scripts",
    "tests", "verify_shots",
})

PIN_IDIOM = (
    "    _ROOT = Path(__file__).resolve().parent.parent   "
    "# scripts/ci/* -> parents[2]\n"
    "    sys.path.insert(0, str(_ROOT))"
)

_HIJACK = 'raise SystemExit("HIJACKED " + __file__)\n'


# ---------------------------------------------------------------------------
# classifier (self-contained on purpose: importing a helper from scripts/ would
# be the very import shape under test)
# ---------------------------------------------------------------------------
_SRC_CACHE: dict[Path, str] = {}
_PARSE_CACHE: dict[Path, tuple[str, ast.Module]] = {}


def _read(path: Path) -> str:
    if path not in _SRC_CACHE:
        _SRC_CACHE[path] = path.read_text(encoding="utf-8")
    return _SRC_CACHE[path]


def _parse(path: Path) -> tuple[str, ast.Module]:
    if path not in _PARSE_CACHE:
        src = _read(path)
        _PARSE_CACHE[path] = (src, ast.parse(src, filename=str(path)))
    return _PARSE_CACHE[path]


def _is_entry_script(src: str, tree: ast.Module) -> bool:
    """Shebang, or a top-level ``if __name__ == ...`` guard."""
    if src.startswith("#!"):
        return True
    for node in tree.body:
        if isinstance(node, ast.If):
            test = node.test
            if (isinstance(test, ast.Compare)
                    and isinstance(test.left, ast.Name)
                    and test.left.id == "__name__"):
                return True
    return False


def _strong_pin(tree: ast.Module) -> tuple[int | None, int | None]:
    """First top-level ``sys.path.insert(0, <derived from __file__>)``.

    Returns ``(lineno, body_index)`` or ``(None, None)``.  "Derived from
    ``__file__``" is transitive: the inserted expression names ``__file__``
    directly, or names a top-level variable whose own assignment was rooted in
    ``__file__`` (``_HERE = Path(__file__)...`` / ``_ROOT = _HERE.parent`` is a
    real idiom here).  A conditional (``if root not in sys.path:``) or
    in-function insert is NOT a strong pin: it is not guaranteed to run, and a
    root already present further down ``sys.path`` still loses to a foreign
    package ahead of it.
    """
    file_derived: set[str] = set()

    def _names(node: ast.AST) -> set[str]:
        return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}

    for index, node in enumerate(tree.body):
        if isinstance(node, ast.Assign):
            if _names(node.value) & (file_derived | {"__file__"}):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        file_derived.add(target.id)
            continue
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
            continue
        call = node.value
        func = call.func
        if not (isinstance(func, ast.Attribute) and func.attr == "insert"):
            continue
        owner = func.value
        if not (isinstance(owner, ast.Attribute) and owner.attr == "path"
                and isinstance(owner.value, ast.Name) and owner.value.id == "sys"):
            continue
        if len(call.args) < 2:
            continue
        position = call.args[0]
        if not (isinstance(position, ast.Constant) and position.value == 0):
            continue
        if _names(call.args[1]) & (file_derived | {"__file__"}):
            return node.lineno, index
    return None, None


def _iter_statements(tree: ast.Module):
    """Every statement in the module, without descending into expressions.

    ``ast.walk`` over scripts/** visits ~3M nodes and costs ~5s; an import only
    ever appears in a statement list, which is a couple of percent of that.
    """
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        yield node
        for field in ("body", "orelse", "finalbody", "handlers", "cases"):
            children = getattr(node, field, None)
            if isinstance(children, list):
                stack.extend(children)


def _repo_imports(tree: ast.Module) -> tuple[list[str], list[tuple[int, str]], bool]:
    """``(packages imported anywhere, top-level (lineno, pkg) pairs, uses relative)``."""
    top_level_ids = {id(node) for node in tree.body}
    every: set[str] = set()
    top: list[tuple[int, str]] = []
    relative = False
    for node in _iter_statements(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in REPO_PACKAGES:
                    every.add(root)
                    if id(node) in top_level_ids:
                        top.append((node.lineno, root))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative = True
                continue
            root = (node.module or "").split(".")[0]
            if root in REPO_PACKAGES:
                every.add(root)
                if id(node) in top_level_ids:
                    top.append((node.lineno, root))
    return sorted(every), sorted(top), relative


def _rel(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def _iter_scripts(pattern: str) -> list[Path]:
    return sorted(
        p for p in REPO_ROOT.glob(pattern)
        if p.is_file() and "__pycache__" not in p.parts
    )


def _guarded_family() -> list[Path]:
    """The CI-guard family: ``scripts/check_*.py`` + ``scripts/ci/*.py``."""
    return sorted(set(_iter_scripts("scripts/check_*.py"))
                  | set(_iter_scripts("scripts/ci/*.py")))


#: Cheap superset prefilters, so the T2 sweep parses ~90 of 1,100+ files rather
#: than all of them (a full parse of scripts/** costs ~7s; the budget is 15s for
#: the module).  Both patterns are deliberately GENEROUS — false positives only
#: cost a parse, and the exact AST classifier below has the final say.  A
#: top-level main guard always starts at column 0, and an import keyword always
#: sits on the same line as its module name (a backslash continuation between
#: the two is the one shape these miss; T1 parses the guard family unfiltered).
_ENTRY_RE = re.compile(r"^if\b.*__name__", re.M)
_REPO_IMPORT_RE = re.compile(
    r"(?:\bfrom|\bimport)\s+(?:" + "|".join(sorted(REPO_PACKAGES)) + r")\b")


def _affected(path: Path) -> bool:
    """Entry script that imports repo packages without an effective pin."""
    try:
        src = _read(path)
    except UnicodeDecodeError:
        return False
    if not (src.startswith("#!") or _ENTRY_RE.search(src)):
        return False
    if not _REPO_IMPORT_RE.search(src):
        return False
    try:
        src, tree = _parse(path)
    except (SyntaxError, UnicodeDecodeError):
        return False
    if not _is_entry_script(src, tree):
        return False
    packages, top, relative = _repo_imports(tree)
    if relative or not packages:
        # A relative import cannot run bare at all; nothing to pin.
        return False
    pin_line, _ = _strong_pin(tree)
    if pin_line is None:
        return True
    first_top = min((lineno for lineno, _ in top), default=None)
    return first_top is not None and first_top < pin_line


def _affected_entry_scripts() -> list[str]:
    return sorted(_rel(p) for p in _iter_scripts("scripts/**/*.py") if _affected(p))


# ---------------------------------------------------------------------------
# decoy
# ---------------------------------------------------------------------------
def _build_decoy(root: Path) -> Path:
    """A hostile repo look-alike: REGULAR packages that abort if imported."""
    decoy = root / "decoy"
    (decoy / "scripts").mkdir(parents=True, exist_ok=True)
    # A REGULAR `scripts` package is the harshest adversary: a namespace
    # `scripts` in this repo would lose to it from ANY sys.path position.
    (decoy / "scripts" / "__init__.py").write_text("", encoding="utf-8")
    (decoy / "scripts" / "build_government_revenue.py").write_text(
        _HIJACK, encoding="utf-8")
    for package in ("engine", "lib", "collectors"):
        (decoy / package).mkdir(parents=True, exist_ok=True)
        (decoy / package / "__init__.py").write_text(_HIJACK, encoding="utf-8")
    return decoy


def _subprocess_env(decoy: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(decoy)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


# ---------------------------------------------------------------------------
# T0 — the package marker
# ---------------------------------------------------------------------------
def test_scripts_is_a_regular_package_and_the_marker_is_inert():
    init = REPO_ROOT / "scripts" / "__init__.py"
    assert init.is_file(), (
        "scripts/__init__.py is missing.  Without it `scripts` is a PEP 420 "
        "namespace portion, and a foreign REGULAR `scripts` package wins from "
        "any later sys.path entry — even against a pin at position 0."
    )
    body = ast.parse(init.read_text(encoding="utf-8")).body
    offenders = [
        ast.dump(node)[:80] for node in body
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str))
    ]
    assert not offenders, (
        "scripts/__init__.py must hold a docstring and nothing else — it is "
        "imported implicitly by every `scripts.*` import in the repo, including "
        f"inside CI guards.  Executable statements found: {offenders}"
    )


# ---------------------------------------------------------------------------
# T1 — static, hard
# ---------------------------------------------------------------------------
def test_guard_family_pins_its_repo_root():
    missing: list[str] = []
    late: list[str] = []
    for path in _guarded_family():
        _src, tree = _parse(path)
        packages, top, _relative = _repo_imports(tree)
        if not packages:
            continue
        pin_line, _ = _strong_pin(tree)
        if pin_line is None:
            missing.append(f"{_rel(path)} (imports {', '.join(packages)})")
            continue
        early = [f"line {lineno}: {pkg}" for lineno, pkg in top if lineno < pin_line]
        if early:
            late.append(f"{_rel(path)} pin at line {pin_line}, but {'; '.join(early)}")
    assert not missing and not late, (
        "Scripts run by file path must pin their own repo root before importing "
        "anything from this repo.  Add, after the stdlib imports and BEFORE the "
        "first repo import (repo imports below it take `# noqa: E402`):\n\n"
        f"{PIN_IDIOM}\n\n"
        + ("no strong pin:\n  " + "\n  ".join(missing) + "\n" if missing else "")
        + ("repo import ahead of the pin:\n  " + "\n  ".join(late) if late else "")
    )


def _sys_path_mutations(tree: ast.Module) -> list[tuple[int, str]]:
    """Every statement that mutates ``sys.path``, as ``(lineno, source kind)``.

    Covers method calls (``insert``/``append``/``extend``/``remove``/``pop``),
    assignment and augmented assignment to ``sys.path`` or a slice/index of it.
    Read-only uses (iteration, membership tests) are not mutations.
    """
    def _is_sys_path(node: ast.AST) -> bool:
        return (isinstance(node, ast.Attribute) and node.attr == "path"
                and isinstance(node.value, ast.Name) and node.value.id == "sys")

    mutations: list[tuple[int, str]] = []
    for node in _iter_statements(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if (isinstance(func, ast.Attribute)
                    and func.attr in {"insert", "append", "extend", "remove", "pop"}
                    and _is_sys_path(func.value)):
                mutations.append((node.lineno, f"sys.path.{func.attr}(...)"))
        elif isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                base = target.value if isinstance(target, ast.Subscript) else target
                if _is_sys_path(base):
                    mutations.append((node.lineno, "assignment to sys.path"))
    return mutations


def test_guard_family_has_no_call_time_sys_path_mutation():
    """The pin must be the ONLY sys.path mutation — anywhere in the file.

    A mutation below the pin (or inside a function, running at call time)
    reorders resolution after the pin already won, and T3 cannot see it: the
    dynamic probe execs each file only UP TO its pin.  check_live_worker.py
    carried exactly this hole (`sys.path.insert(0, ".")` before a lazy
    `scripts.*` import: whoever's cwd held a `scripts` package won).
    """
    offenders: list[str] = []
    for path in _guarded_family():
        _src, tree = _parse(path)
        pin_line, _ = _strong_pin(tree)
        for lineno, kind in _sys_path_mutations(tree):
            if pin_line is not None and lineno == pin_line:
                continue
            offenders.append(f"{_rel(path)}:{lineno}: {kind}")
    assert not offenders, (
        "Guard-family scripts may mutate sys.path exactly once: the repo-root "
        "pin.  Any other mutation (a call-time insert, an append, a conditional "
        "re-pin) reorders import resolution after the pin and can hand repo "
        "imports to a foreign tree — and the dynamic probe cannot see it.\n\n"
        "Delete the mutation; the module-level pin already covers lazy "
        "imports.\n\n  " + "\n  ".join(sorted(offenders))
    )


# ---------------------------------------------------------------------------
# T2 — baseline, shrink-only
# ---------------------------------------------------------------------------
def test_unpinned_entry_scripts_only_shrink():
    baseline = {
        line.strip() for line in
        BASELINE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    current = set(_affected_entry_scripts())
    added = sorted(current - baseline)
    assert not added, (
        "New entry scripts import repo packages with no repo-root pin.  Add the "
        "pin, never extend the baseline; prune entries you fix.\n\n"
        f"{PIN_IDIOM}\n\nunpinned and not in the baseline:\n  "
        + "\n  ".join(added)
    )


# ---------------------------------------------------------------------------
# T3 — dynamic: bare invocation against the decoy
# ---------------------------------------------------------------------------
def test_bare_invocation_resolves_repo_imports_from_this_repo(tmp_path):
    decoy = _build_decoy(tmp_path)
    neutral = tmp_path / "neutral"
    neutral.mkdir()
    results_path = tmp_path / "t3.json"
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--resolve-probe",
         str(decoy), str(results_path)],
        cwd=str(neutral), env=_subprocess_env(decoy),
        capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, (
        f"resolve probe crashed (rc={proc.returncode})\n"
        f"stdout:\n{proc.stdout[-4000:]}\nstderr:\n{proc.stderr[-4000:]}"
    )
    results = json.loads(results_path.read_text(encoding="utf-8"))
    canary = "scripts/check_government_revenue_projection.py"
    assert results["checked"] >= 10 and canary in results["probed"], (
        f"probe covered {results['checked']} files and "
        f"{'did' if canary in results['probed'] else 'did NOT'} include {canary} "
        "— the family glob or the repo-import classifier is broken, so this test "
        "proves nothing."
    )
    assert not results["failures"], (
        "Under a bare `python3 scripts/<name>.py` invocation these files resolve "
        "a repo import to a FOREIGN tree.  Each one would import — and execute — "
        "another repository's code from inside a CI guard.\n\n"
        f"{PIN_IDIOM}\n\n(and scripts/__init__.py must exist, or the pin loses to "
        "a foreign REGULAR `scripts` package)\n\n  "
        + "\n  ".join(results["failures"])
    )


# ---------------------------------------------------------------------------
# T4 — end to end, the script that broke
# ---------------------------------------------------------------------------
def test_named_guard_runs_clean_under_a_hostile_pythonpath(tmp_path):
    decoy = _build_decoy(tmp_path)
    proc = subprocess.run(
        [sys.executable, "scripts/check_government_revenue_projection.py", "--help"],
        cwd=str(REPO_ROOT), env=_subprocess_env(decoy),
        capture_output=True, text=True, timeout=120,
    )
    combined = proc.stdout + proc.stderr
    assert "HIJACKED" not in combined, (
        "the guard EXECUTED the decoy's build_government_revenue.py:\n" + combined[:2000]
    )
    assert proc.returncode == 0, (
        f"rc={proc.returncode}\nstdout:\n{proc.stdout[:2000]}\n"
        f"stderr:\n{proc.stderr[:2000]}"
    )
    assert "usage" in proc.stdout, proc.stdout[:2000]


# ---------------------------------------------------------------------------
# subprocess mode (T3 driver) + baseline emitter
# ---------------------------------------------------------------------------
def _resolve_probe(decoy: Path, results_path: Path) -> int:
    """Simulate `python3 <file>` for every guard-family member, in one process.

    For each file: rebuild sys.path as a bare invocation would (own directory
    first, then the hostile decoy, then the stdlib tail — no repo root, no cwd),
    purge repo packages from sys.modules, execute the file's top-level
    statements UP TO AND INCLUDING its pin, then assert every repo package it
    imports resolves inside this repo.
    """
    import importlib
    import importlib.util

    original_path = list(sys.path)
    tests_dir = Path(__file__).resolve().parent
    tail = []
    for entry in original_path:
        if not entry:
            continue
        resolved = Path(entry).resolve()
        if resolved in (decoy, REPO_ROOT, tests_dir) or REPO_ROOT in resolved.parents:
            continue
        tail.append(entry)

    failures: list[str] = []
    skipped: list[str] = []
    probed: list[str] = []

    for path in _guarded_family():
        _src, tree = _parse(path)
        packages, _top, _relative = _repo_imports(tree)
        if not packages:
            continue
        rel = _rel(path)
        probed.append(rel)
        _pin_line, pin_index = _strong_pin(tree)
        if pin_index is None:
            failures.append(f"{rel}: no strong pin at all")
            continue

        sys.path[:] = [str(path.parent), str(decoy)] + tail
        for name in list(sys.modules):
            root = name.split(".")[0]
            if root in REPO_PACKAGES:
                del sys.modules[name]

        prefix = ast.Module(body=tree.body[:pin_index + 1], type_ignores=[])
        namespace = {
            "__file__": str(path),
            "__name__": "_pin_probe_",
            "__package__": None,
            "__doc__": None,
            "__builtins__": __builtins__,
        }
        try:
            exec(compile(prefix, str(path), "exec"), namespace)  # noqa: S102
        except ModuleNotFoundError as exc:
            if (exc.name or "").split(".")[0] in REPO_PACKAGES:
                failures.append(f"{rel}: pin prefix failed on repo import: {exc}")
            else:
                skipped.append(f"{rel}: third-party module {exc.name!r} unavailable")
            continue
        except BaseException as exc:  # noqa: BLE001 - SystemExit is the hijack signal
            failures.append(f"{rel}: pin prefix raised {type(exc).__name__}: {exc}")
            continue

        importlib.invalidate_caches()
        for package in packages:
            try:
                spec = importlib.util.find_spec(package)
            except BaseException as exc:  # noqa: BLE001
                failures.append(f"{rel}: find_spec({package!r}) raised "
                                f"{type(exc).__name__}: {exc}")
                continue
            if spec is None:
                failures.append(f"{rel}: {package!r} does not resolve at all")
                continue
            locations = [str(Path(p).resolve())
                         for p in (spec.submodule_search_locations or [])]
            origin = str(Path(spec.origin).resolve()) if spec.origin else None
            if package == "scripts":
                expected = str(REPO_ROOT / "scripts" / "__init__.py")
                if origin != expected or locations != [str(REPO_ROOT / "scripts")]:
                    failures.append(
                        f"{rel}: 'scripts' resolved to origin={origin} "
                        f"locations={locations} (expected the REGULAR package "
                        f"{expected})")
                continue
            foreign = [p for p in locations
                       if Path(p) != REPO_ROOT and REPO_ROOT not in Path(p).parents]
            if origin is not None and REPO_ROOT not in Path(origin).parents:
                foreign.append(origin)
            if foreign:
                failures.append(
                    f"{rel}: {package!r} resolved OUTSIDE this repo -> {foreign}")

    sys.path[:] = original_path
    results_path.write_text(
        json.dumps({"checked": len(probed), "probed": probed,
                    "failures": failures, "skipped": skipped}, indent=2),
        encoding="utf-8",
    )
    print(f"probed {len(probed)} files · {len(failures)} failures · "
          f"{len(skipped)} skipped")
    for line in skipped:
        print(f"  skipped: {line}")
    return 0


def _main(argv: list[str]) -> int:
    if argv[1:2] == ["--resolve-probe"]:
        return _resolve_probe(Path(argv[2]).resolve(), Path(argv[3]))
    if argv[1:2] == ["--emit-baseline"]:
        print("\n".join(_affected_entry_scripts()))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
