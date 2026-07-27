"""Every `from lib.nyse_calendar import X` in the repo must name a real attribute.

WHY THIS EXISTS: `scripts/build_flow_leaders.py` and `scripts/build_leader_radar.py`
both imported `trading_dates_between` — a function lib/nyse_calendar.py has never
defined — from INSIDE a `try: ... except Exception: return False` block. The
ImportError fired on every call, was swallowed, and both freshness SLAs returned
"fresh" for every input for as long as they existed. Nothing caught it: the builders
exit 0 by design, the log line was `log.debug`, and both predicates' tests asserted
only `isinstance(result, bool)`.

A function-local import inside a broad `except` is invisible to import-time errors,
to linters that only resolve module-level imports, and to any test that exercises
the swallowing path. This test resolves the names statically instead, so a typo'd
or removed calendar helper fails here rather than degrading silently into a
permanently-false gate.

Run:
    python -m pytest tests/test_nyse_calendar_import_names.py -q
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from lib import nyse_calendar

REPO = Path(__file__).resolve().parent.parent
_SKIP_DIRS = {".git", ".claude", "node_modules", "__pycache__", ".venv", "venv", "site"}

MODULE = "lib.nyse_calendar"


def _python_files() -> list[Path]:
    out: list[Path] = []
    for p in REPO.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in p.relative_to(REPO).parts):
            continue
        out.append(p)
    return out


def _imported_names() -> list[tuple[Path, int, str]]:
    """Every (file, lineno, name) imported by name from lib.nyse_calendar."""
    found: list[tuple[Path, int, str]] = []
    for path in _python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue  # not our gate to enforce
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == MODULE:
                for alias in node.names:
                    if alias.name != "*":
                        found.append((path, node.lineno, alias.name))
    return found


def test_calendar_import_sites_were_found():
    """Guard the guard: an empty sweep would make every assertion below vacuous."""
    names = _imported_names()
    assert names, f"no `from {MODULE} import ...` sites found — the AST sweep is broken"


def test_every_imported_calendar_name_exists():
    missing = [
        f"{path.relative_to(REPO)}:{lineno} imports `{name}`"
        for path, lineno, name in _imported_names()
        if not hasattr(nyse_calendar, name)
    ]
    assert not missing, (
        f"{MODULE} does not define these imported names:\n  "
        + "\n  ".join(missing)
    )


@pytest.mark.parametrize(
    "name",
    ["is_session", "last_session_on_or_before", "expected_last_session",
     "session_date", "sessions_between", "sessions_behind"],
)
def test_public_calendar_api_present(name: str):
    """The helpers freshness gates are built on must not silently disappear."""
    assert callable(getattr(nyse_calendar, name, None)), f"{MODULE}.{name} missing"
