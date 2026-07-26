"""A GitHub Actions annotation must START its line — so it can never go through logging.

GitHub only parses a workflow command (``::warning ...``, ``::error ...``,
``::notice ...``) when ``::`` is the first thing on the line.  Every builder in
this repo configures logging with a prefixing format — ``"%(levelname)s %(message)s"``
and friends — so ``log.warning("::warning title=x::…")`` emits::

    WARNING ::warning title=x::…

and GitHub silently drops it.  The call looks like an alarm in code review, runs
without error, and produces NOTHING in the Actions summary.  That is the worst
possible failure mode for a fail-soft: the builder ships degraded output and the
only signal it was supposed to raise does not exist.

This has now shipped dead at least five separate times (#3487, #3515, #3563,
#3570, and #3562 — which merged a fresh one on 2026-07-26, the same day the
others were being fixed).  Hence a guard rather than another one-off repair.

The fix is always the same: emit the annotation with a bare ``print`` to stdout,
and keep a ``log.*`` line (with ``exc_info`` where there is a traceback worth
having) when the human-readable log deserves more detail than the annotation.

Run: .venv/bin/python -m pytest tests/test_gh_annotation_line_start.py -q
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Directories whose modules execute inside a GitHub Actions step (nightly
# builders, engines, collectors, checks).  ``tests/`` is excluded on purpose: a
# test may legitimately build an annotation string to assert on it.
SCAN_DIRS = ("scripts", "engine", "collectors", "app", "admin", "lib", "tools", "research")

LEVELS = {"debug", "info", "warning", "error", "critical", "exception"}

# Modules that never run inside an Actions step, so a "::" prefix in their log
# message is dead decoration rather than a dropped annotation.  Removing the
# prefix there is a separate, deliberate change to production request paths.
EXEMPT: dict[str, str] = {
    "engine/neuralweb/brain_gateway.py": "FastAPI request path (app/main.py) — VPS runtime, not CI",
    "engine/research_vault/download_quota.py": "FastAPI request path (app/research.py) — VPS runtime",
    "engine/research_vault/view_ratelimit.py": "FastAPI request path (app/research.py) — VPS runtime",
}


def _annotation_head(node: ast.expr) -> str | None:
    """The leading literal of a string or f-string argument, if it starts with '::'."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value if node.value.startswith("::") else None
    if isinstance(node, ast.JoinedStr) and node.values:
        head = node.values[0]
        if isinstance(head, ast.Constant) and isinstance(head.value, str) \
           and head.value.startswith("::"):
            return head.value
    return None


def _candidates() -> list[Path]:
    """Files worth parsing — cheap byte prefilter keeps the whole guard ~1s."""
    out = []
    for d in SCAN_DIRS:
        for p in (ROOT / d).rglob("*.py"):
            try:
                blob = p.read_bytes()
            except OSError:
                continue
            if b'("::' in blob or b"('::" in blob or b'(f"::' in blob or b"(f'::" in blob:
                out.append(p)
    return out


def _offenders() -> list[tuple[str, int, str]]:
    found = []
    for path in _candidates():
        rel = path.relative_to(ROOT).as_posix()
        if rel in EXEMPT:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr not in LEVELS:
                continue
            head = _annotation_head(node.args[0])
            if head is not None:
                found.append((rel, node.lineno, head.splitlines()[0][:70]))
    return sorted(found)


def test_no_annotation_goes_through_a_logger():
    offenders = _offenders()
    assert not offenders, (
        "GitHub annotation routed through a logger — it will NEVER appear in the "
        "Actions summary, because logging prefixes the line and GitHub only parses "
        "'::' at column 0.\n"
        "Emit it with a bare print(..., flush=True) instead (keep a plain log.* line "
        "for humans if the detail is worth it):\n\n"
        + "\n".join(f"  {f}:{n}  {msg}" for f, n, msg in offenders)
    )


def test_exempt_entries_still_exist_and_still_offend():
    """An exemption that no longer applies must be deleted, not left to rot."""
    stale = []
    for rel, why in EXEMPT.items():
        path = ROOT / rel
        if not path.exists():
            stale.append(f"{rel}: file is gone ({why})")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        hit = any(
            isinstance(n, ast.Call) and n.args
            and isinstance(n.func, ast.Attribute) and n.func.attr in LEVELS
            and _annotation_head(n.args[0]) is not None
            for n in ast.walk(tree)
        )
        if not hit:
            stale.append(f"{rel}: no longer has an annotation-shaped log call — drop the exemption")
    assert not stale, "EXEMPT is out of date:\n" + "\n".join(f"  {s}" for s in stale)


def test_guard_catches_a_planted_offender(tmp_path):
    """Selftest: the matcher must actually fire, including on f-string messages."""
    src = (
        'import logging\n'
        'log = logging.getLogger("x")\n'
        'log.warning("::warning title=t::plain")\n'
        'log.error(f"::error::{1}")\n'
        'print("::notice::this one is fine")\n'
    )
    tree = ast.parse(src)
    hits = [
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Call) and n.args
        and isinstance(n.func, ast.Attribute) and n.func.attr in LEVELS
        and _annotation_head(n.args[0]) is not None
    ]
    assert hits == [3, 4], f"matcher missed a planted offender: {hits}"
