#!/usr/bin/env python3
"""Resolve a workflow step's effective shell source, seeing through extraction.

WHY THIS EXISTS
---------------
daily.yml sits against GitHub's silent ~512,000-byte workflow processing cap
(2026-08-12 incident: the nightly stranded jobless for ~3h with no error
anywhere — see tests/test_workflow_file_size.py).  The only way to shrink the
file without deleting load-bearing documentation is to extract inline
``run: |`` bodies to ``scripts/ci/<name>.sh``.

But three guards read those bodies STRAIGHT OUT OF THE YAML:

* ``scripts/check_dag_conformance.py`` extracts ``run_py`` / ``brun`` /
  ``python -m`` module invocations and diffs them against ``config/dag.yml``.
* ``tests/test_push_conflict_guard.py`` censuses steps that pull with
  ``--autostash`` and broad-add ``site/``, and asserts a floor plus a
  GATE_REQUIRED membership list.
* ``tests/test_render_options_workspace_scope.py`` asserts on the engine job's
  raw text ordering.

Extracting a body would make it vanish from all three — measured: moving the
two engine blocks out drops 83 modules (``engine.run``, ``scripts.build_site``,
...) from the engine lane, and moving the standout-audit commit step out
deletes a GATE_REQUIRED census member.  Those guards would not fail loudly;
the DAG one would, but the census would simply go BLIND, which is the exact
silent-coverage-loss failure its own comments warn about.

This module is the single seam that keeps extraction invisible to all three.
Every consumer calls ``resolve_run_source`` and gets back the shell source that
step actually executes, whether it lives inline or in a script file.

THE MARKER CONTRACT
-------------------
An extracted script declares its provenance in its first ``MARKER_SCAN_LINES``
lines with the literal ``MARKER`` string.  That marker is what makes the
indirection resolvable, so it is mandatory for anything extracted from now on.

FAIL-CLOSED, ALWAYS
-------------------
A missing file, or a ``scripts/ci`` script with no marker that is not a known
pre-existing helper, RAISES.  It never returns ``run`` unchanged as a
"safe default" and never returns an empty string: silently returning nothing
is precisely the blindness this module exists to prevent — the guard would
report zero modules / zero census members and read GREEN.

The ``LEGACY_UNMARKED`` allowlist pins the four ``scripts/ci`` helpers that
predate this contract.  They are invoked as whole-step bodies today
(``nightly_timings_finish.sh`` ×18 steps, ``public_render.sh`` ×1) or sourced
from inside other bodies (``push_retry.sh``, ``strip_conflict_markers.sh``),
they were never extracted verbatim from a workflow, and their contents are not
step source.  They pass through unchanged, which is what keeps this module a
strict no-op until the first marked script appears.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = [
    "LEGACY_UNMARKED",
    "MARKER",
    "MARKER_SCAN_LINES",
    "WorkflowRunSourceError",
    "resolve_run_source",
    "resolved_workflow_text",
]

#: Literal provenance marker an extracted script must carry.
MARKER = "EXTRACTED-VERBATIM-FROM: .github/workflows/daily.yml"

#: How many leading lines of a script are scanned for :data:`MARKER`.
MARKER_SCAN_LINES = 5

#: ``scripts/ci`` helpers that predate the marker contract and are NOT
#: extracted step bodies.  Pass through unchanged (zero parse delta).
LEGACY_UNMARKED = frozenset(
    {
        "nightly_timings_finish.sh",
        "public_render.sh",
        "push_retry.sh",
        "strip_conflict_markers.sh",
    }
)

# A step body that is EXACTLY one `bash scripts/ci/<name>.sh [args...]` call.
# [ \t] (never \s) is load-bearing: \s matches newlines, so a multi-line body
# whose FIRST line is such a call would false-positive as a pure indirection
# and the rest of the body would be silently discarded.
_BASH_CALL_RE = re.compile(r"bash (scripts/ci/[A-Za-z0-9_.-]+\.sh)(?:[ \t]+\S+)*")


class WorkflowRunSourceError(RuntimeError):
    """An indirection that cannot be resolved. Never swallow this."""


def resolve_run_source(run: str, repo_root: Path) -> str:
    """Return the shell source a workflow step effectively runs.

    ``run`` is a step's ``run:`` value. If it is exactly one
    ``bash scripts/ci/<name>.sh [args...]`` invocation and that script carries
    the provenance :data:`MARKER`, the script's text is returned — so callers
    that pattern-match shell source keep seeing what they saw before the body
    was extracted. Every other ``run`` value is returned unchanged.

    Raises:
        WorkflowRunSourceError: the referenced script is missing, or it is a
            ``scripts/ci`` script with no marker and no
            :data:`LEGACY_UNMARKED` entry (a future extraction that forgot the
            marker — fail closed rather than go blind).
    """
    if not isinstance(run, str):
        return run

    stripped = run.strip()
    # Multi-line bodies are never a pure indirection; bail before the regex so
    # a body that merely BEGINS with such a call can't be mistaken for one.
    if "\n" in stripped:
        return run

    match = _BASH_CALL_RE.fullmatch(stripped)
    if match is None:
        return run

    rel = match.group(1)
    script = Path(repo_root) / rel
    if not script.is_file():
        raise WorkflowRunSourceError(
            f"workflow step invokes {rel!r} but that file does not exist under "
            f"{repo_root}. A guard that reads step bodies would silently see an "
            "empty body here; refusing to resolve."
        )

    text = script.read_text(encoding="utf-8")
    head = text.splitlines()[:MARKER_SCAN_LINES]
    if any(MARKER in line for line in head):
        return text

    if script.name in LEGACY_UNMARKED:
        return run

    raise WorkflowRunSourceError(
        f"{rel} is invoked as a whole workflow step body but carries no "
        f"{MARKER!r} line in its first {MARKER_SCAN_LINES} lines, and is not a "
        "known pre-existing helper. Add the marker (see this module's "
        "docstring) so DAG conformance and the push-conflict census can still "
        "read the body; otherwise extracting it makes those guards go blind."
    )


_RUN_CALL_LINE_RE = re.compile(
    r"^(?P<indent>[ \t]*)run:[ \t]+(?P<call>bash[ \t]+scripts/ci/[^\n]*?)[ \t]*$"
)


def resolved_workflow_text(wf_path: Path, repo_root: Path) -> str:
    """The workflow file's text with every extracted body spliced back IN PLACE.

    Many guards read a workflow with a plain ``path.read_text()`` and then assert
    on ORDER — ``text.index(a) < text.index(b)``, a regex sweep for ``brun``
    slugs, a proximity bound between two calls. Those reads are positional, so
    handing them a concatenation of run bodies would not preserve what they
    measure.

    This returns the file verbatim except that each ``run: bash
    scripts/ci/<name>.sh`` line is replaced by that script's body, indented under
    where the call sat. Document order is therefore identical to the
    pre-extraction file and index-based assertions keep their meaning.

    Same fail-closed contract as :func:`resolve_run_source`.
    """
    text = Path(wf_path).read_text(encoding="utf-8")
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        match = _RUN_CALL_LINE_RE.match(line.rstrip("\n"))
        if match is None:
            out.append(line)
            continue
        resolved = resolve_run_source(match.group("call"), repo_root)
        if resolved.strip() == match.group("call").strip():
            out.append(line)  # legacy helper — leave the call as written
            continue
        pad = match.group("indent") + "  "
        for body_line in resolved.splitlines():
            out.append(f"{pad}{body_line}\n" if body_line.strip() else "\n")
    return "".join(out)
