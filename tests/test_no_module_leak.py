"""No test may leave sys.modules poisoned for the rest of the pytest process.

A test that evicts a module — or rebinds a name to a different module object —
and does not put the original back breaks LATER tests in OTHER files.  Because
the damage is process-wide, it only surfaces when the collected file set happens
to put culprit and victim in one invocation, so the failure set moves as files
are added and the whole thing reads as "that flaky batch thing".  That is what
lets a genuine regression hide.

Measured instance (2026-08-06).  ``tests/test_admin_live_runs.py
::test_probe_bot_no_requests_lib`` popped ``requests`` out of ``sys.modules``
and THEN called ``monkeypatch.setitem(sys.modules, "requests", None)``.  Because
monkeypatch snapshots the mapping at call time it recorded "key absent", and its
teardown — which runs after the test body — DELETED the key, silently undoing
the test's own ``finally``-block restore.  The next ``import requests``
re-executed ``requests/__init__.py`` against still-cached submodules, producing a
module with ``.session`` but no ``.sessions``; the victim was
``tests/test_capital_structure_share_count_materializer.py``, three files later,
dying on ``requests.sessions.Session``.

Two independent layers keep it fixed, and both are exercised here:
  * a RUNTIME tripwire in tests/conftest.py (MM_MODULE_GUARD) that catches any
    eviction or rebind, whatever idiom produced it; and
  * a STATIC scan for the specific pop-then-monkeypatch idiom, which fires at
    authoring time even in a pack where culprit and victim never co-run.
"""
from __future__ import annotations

import ast
import importlib
import os
import sys
import types
from pathlib import Path

import pytest

from tests.conftest import _module_identities, _module_leaks

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

_PROBE = "___mm_module_leak_probe___"


@pytest.fixture
def probe():
    """A throwaway module registered under a name nothing else uses."""
    mod = types.ModuleType(_PROBE)
    sys.modules[_PROBE] = mod
    try:
        yield mod
    finally:
        sys.modules.pop(_PROBE, None)


# ---------------------------------------------------------------------------
# 1. the trap itself — pinned so the next author meets it as an executable fact
# ---------------------------------------------------------------------------

def test_monkeypatch_setitem_after_a_pop_deletes_the_key_at_undo(probe):
    """THE BUG.  monkeypatch snapshots at CALL time, so a preceding pop makes
    its undo a delete — and undo runs after the test body, so it wins over any
    finally-block restore."""
    mp = pytest.MonkeyPatch()
    popped = sys.modules.pop(_PROBE)
    mp.setitem(sys.modules, _PROBE, None)  # records "key absent"
    sys.modules[_PROBE] = popped           # the test's own finally-block restore
    mp.undo()                              # ...and monkeypatch runs last
    assert _PROBE not in sys.modules, (
        "pytest changed monkeypatch.setitem semantics: a setitem recorded after "
        "a pop no longer deletes the key at undo. Re-read the conftest "
        "MM_MODULE_GUARD note — the guard stays useful either way, but this "
        "file's explanation of the 2026-08-06 requests eviction is now stale."
    )


def test_monkeypatch_setitem_without_a_pop_restores_the_original(probe):
    """THE FIX.  setitem alone is enough to make `import name` raise ImportError,
    and it restores the real module afterwards."""
    mp = pytest.MonkeyPatch()
    mp.setitem(sys.modules, _PROBE, None)
    with pytest.raises(ImportError):
        importlib.import_module(_PROBE)
    mp.undo()
    assert sys.modules[_PROBE] is probe


def test_re_importing_an_evicted_package_loses_its_submodule_attributes():
    """Why the eviction was fatal rather than merely untidy.

    Re-executing a package's __init__ against still-cached submodules binds only
    the NAMES its from-imports list.  Nothing re-runs the submodule loader that
    sets the attribute on the fresh parent, so `requests.sessions` vanishes while
    `requests.session` — a name `from .sessions import Session, session` binds
    directly — survives.  That asymmetry is the whole failure.
    """
    requests = pytest.importorskip("requests")
    assert hasattr(requests, "sessions"), (
        "`requests` is ALREADY poisoned at this point in the session — some "
        "earlier test evicted it from sys.modules. Run with the MM_MODULE_GUARD "
        "banner to see which one."
    )

    saved = sys.modules.pop("requests")
    try:
        fresh = importlib.import_module("requests")
        assert fresh is not saved
        assert not hasattr(fresh, "sessions")   # the submodule attribute is gone
        assert hasattr(fresh, "session")        # the from-imported name is not
    finally:
        sys.modules["requests"] = saved


# ---------------------------------------------------------------------------
# 2. the runtime tripwire — armed, and able to see each shape of leak
# ---------------------------------------------------------------------------

def test_the_module_guard_is_armed_in_this_session(request):
    """Defining the guard is not the same as it running.

    This asserts the baseline exists in the CONFIG of whatever pack is executing
    right now, so a conftest refactor that drops the hook wiring cannot leave the
    guard registered-but-dark.
    """
    if os.environ.get("MM_MODULE_GUARD", "").strip().lower() == "off":
        pytest.skip("guard deliberately disabled via MM_MODULE_GUARD=off")
    assert hasattr(request.config, "_mm_module_baseline"), (
        "tests/conftest.py no longer arms MM_MODULE_GUARD: pytest_collection_finish "
        "did not set config._mm_module_baseline. Every sys.modules leak is invisible "
        "again until this is restored."
    )


def test_guard_reports_an_eviction():
    before = {"a": 1, "b": 2}
    assert _module_leaks(before, {"b": 2}) == ["evicted  a"]


def test_guard_reports_a_rebind_to_a_different_object():
    leaks = _module_leaks({"a": 1}, {"a": 999})
    assert len(leaks) == 1 and leaks[0].startswith("rebound  a")


def test_guard_ignores_additions():
    """Importing a module for the first time is what tests do, not a leak."""
    assert _module_leaks({"a": 1}, {"a": 1, "new": 2}) == []


def test_guard_scopes_to_inherited_names_only():
    """A name the test file MINTED is its own scratch space, not shared state.

    tests/test_capital_structure_share_count_r2_operator.py loads the operator
    script under the synthetic name ``_share_count_r2_operator_test`` once per
    test, so it rebinds that key every time — and nothing outside that file can
    hold a stale reference to it. Without this scoping the guard reported five
    of its tests as leaks, which is how a guard gets switched off.
    """
    before, after = {"shared": 1, "minted": 1}, {"shared": 2, "minted": 2}
    both = _module_leaks(before, after)
    assert len(both) == 2, "unscoped, the helper still sees every rebind"
    scoped = _module_leaks(before, after, inherited={"shared"})
    assert len(scoped) == 1 and scoped[0].startswith("rebound  shared")


def test_guard_scoping_is_a_stated_trade_off_not_total_coverage():
    """The cost of that scoping, pinned so nobody reads the guard as exhaustive.

    A module first imported mid-session — absent when collection finished — is
    outside the runtime guard's scope even when a test evicts it. That gap is
    why the static scan above exists as a SECOND layer: it catches the
    pop-then-monkeypatch idiom by reading source, whatever the runtime pairing.
    """
    leaks = _module_leaks({"late": 1}, {}, inherited=set())
    assert leaks == [], (
        "scoping changed: mid-session imports are now in scope. That is a "
        "strictly better guard — but re-check the r2_operator suites for the "
        "synthetic-name false positive this scoping was added to remove."
    )


def test_guard_ignores_importlib_reload(tmp_path, monkeypatch):
    """reload() re-executes a module IN PLACE, so key and identity both survive.

    The repo leans on reload() in ~40 files; a guard that flagged it would be
    reverted within a day, which is the same as no guard at all.  Reloads a
    throwaway module written for this test rather than a live one — the point is
    reload's semantics, and reloading something the session depends on to prove a
    guard is quiet would be its own cross-test hazard.
    """
    name = "___mm_reload_probe___"
    (tmp_path / f"{name}.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    mod = importlib.import_module(name)
    try:
        before = _module_identities()
        reloaded = importlib.reload(mod)
        assert reloaded is mod, "reload() is supposed to mutate in place"
        assert _module_leaks(before, _module_identities()) == []
    finally:
        sys.modules.pop(name, None)


def test_guard_sees_a_real_eviction_of_a_real_module(probe):
    """End to end through the same helpers the conftest hook uses."""
    before = _module_identities()
    del sys.modules[_PROBE]
    try:
        assert _module_leaks(before, _module_identities()) == [f"evicted  {_PROBE}"]
    finally:
        sys.modules[_PROBE] = probe


# ---------------------------------------------------------------------------
# 3. the static scan — catches the idiom even where culprit and victim never
#    share a pytest invocation
# ---------------------------------------------------------------------------

def _is_sys_modules(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "modules"
        and isinstance(node.value, ast.Name)
        and node.value.id in {"sys", "_sys"}
    )


def _drops_a_sys_modules_key(node: ast.AST) -> bool:
    """`sys.modules.pop(...)` or `del sys.modules[...]`."""
    if isinstance(node, ast.Call):
        f = node.func
        return isinstance(f, ast.Attribute) and f.attr == "pop" and _is_sys_modules(f.value)
    if isinstance(node, ast.Delete):
        return any(
            isinstance(t, ast.Subscript) and _is_sys_modules(t.value) for t in node.targets
        )
    return False


def _monkeypatches_sys_modules(node: ast.AST) -> bool:
    """`monkeypatch.setitem(sys.modules, ...)` / `mp.setitem(sys.modules, ...)`."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "setitem"
        and bool(node.args)
        and _is_sys_modules(node.args[0])
    )


# The ONE function allowed to contain the idiom, because demonstrating it IS its
# job. Keyed on (path, function name) rather than a substring so a rename cannot
# silently widen the hole; test_the_exemption_still_resolves pins that it exists.
_DEMONSTRATION = (Path("tests/test_no_module_leak.py"),
                  "test_monkeypatch_setitem_after_a_pop_deletes_the_key_at_undo")


def _offenders() -> list[str]:
    found = []
    for path in sorted(TESTS.glob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):  # pragma: no cover — unreadable file
            continue
        rel = path.relative_to(ROOT)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if (rel, fn.name) == _DEMONSTRATION:
                continue
            body = list(ast.walk(fn))
            drops = [n for n in body if _drops_a_sys_modules_key(n)]
            patches = [n for n in body if _monkeypatches_sys_modules(n)]
            if drops and patches:
                found.append(
                    f"{rel}:{min(n.lineno for n in drops + patches)} in {fn.name}()"
                )
    return found


def test_the_exemption_still_resolves():
    """A stale exemption is a hole. If the demonstration is renamed or moved, this
    goes red rather than quietly excusing a function that no longer exists."""
    path, name = _DEMONSTRATION
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    assert any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
        for n in ast.walk(tree)
    ), f"the sole scan exemption names {path}::{name}, which no longer exists"


def test_no_test_pops_a_sys_modules_key_then_monkeypatches_it():
    """The 2026-08-06 idiom, banned by construction.

    Within one function, dropping a sys.modules key and then handing the same
    mapping to monkeypatch means monkeypatch's undo deletes the key. There is no
    correct version of this pairing: setitem alone already does the job, and the
    key must still be present for monkeypatch to have something to restore.
    """
    offenders = _offenders()
    assert not offenders, (
        "these tests drop a sys.modules key AND monkeypatch the same mapping in one "
        "function, so monkeypatch's undo DELETES the key after the test body has "
        "already restored it — poisoning every later test in the process:\n  "
        + "\n  ".join(offenders)
        + "\n\nDrop the pop/del. `monkeypatch.setitem(sys.modules, name, None)` alone "
        "already makes `import name` raise ImportError, and it restores the real "
        "module at teardown."
    )
