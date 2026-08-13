"""Shared refusal for guards that would otherwise pass VACUOUSLY on a sparse tree.

This module is a LIBRARY and carries no shebang on purpose: it is imported by the
guards, never executed. `tests/test_check_script_import_pinning.py` treats a
shebang (or a `__main__` guard) as the mark of an entry script and then requires a
top-level `sys.path.insert(0, <repo root>)` before any repo-package import —
because `python3 scripts/foo.py` puts `scripts/`, not the repo root, on `sys.path`.
The importing guards already carry that pin; a library that is only ever imported
must not repeat it, since a module-level `sys.path` mutation is a side effect on
every import for no benefit.

WHY THIS EXISTS
---------------
Session worktrees are sparse by default (policy R8, `scripts/worktree_sparse.py`):
`data/`, `site/`, `mockups/` and `verify_shots/` are omitted from the cone, which
takes a checkout from ~3.8 GiB to ~348 MiB. Every guard in `scripts/` that
enumerates its own work set by WALKING one of those trees then finds nothing, and
an empty offender list is indistinguishable from a clean one — so it prints its
affirmative OK and exits 0. Measured in a sparse worktree on 2026-08-13, all seven
of these reported a pass over an empty tree:

    check_site_js            "OK — all standalone JS bundles under site/ parse cleanly."
    check_nav_gap            "OK — every menu page under site/ keeps a ≥14px top gap."
    check_nav_mega           "OK — every shared-nav page carries the Research mega-menu."
    check_badge_passport     "OK: site dir <abs>/site absent (nothing rendered yet)."
    check_cycle_consistency  "CYCLE-CONSISTENCY: PASS — 0 same-tape group(s) agree…"
    check_ms_board_coherence "ms-board coherence: OK (0 page(s) scanned)"
    check_ohlc_basis_coherence "…nothing to check" (and it WRITES its marker first)

`check_template_site_sync._sparse_refusal` was the first fix of this shape; this
module is that idea made shared and made CONDITIONAL.

THE REFUSAL IS CONDITIONAL ON AN EMPTY RESULT SET — NOT ON SPARSENESS
---------------------------------------------------------------------
A blanket entry-guard ("refuse whenever site/ is not materialized") would be the
wrong fix twice over: it would red a run that legitimately inspected items in a
partially-materialized tree, and it would say nothing about a full checkout that
honestly found zero. Only the CONJUNCTION is evidence of a lie:

    checked ZERO items  AND  a tree this guard reads is sparse-omitted  ->  refuse

Both halves matter. Zero items in a FULL checkout is an honest zero and still
passes. A non-empty run in a sparse tree found real work and still passes.

FAIL-SAFE IN THE OTHER DIRECTION
--------------------------------
Every failure mode of the detector answers None (proceed normally): the profile
module missing (this can land before or after #5531), git unavailable, an
unreadable HEAD, or a target directory that is not one of this checkout's
top-level trees at all — which is how a guard pointed at a tmp_path in a test
stays inert. The detector may never be the thing that breaks a guard.

Callers own their own human-readable line and exit code; this module emits the
GitHub annotation and hands back the remedy text.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def tree_name(path: str | Path, root: str | Path | None = None) -> str | None:
    """The top-level tree ``path`` sits in, relative to ``root`` — else None.

    Guards take their target directory as an argument and tests point them at a
    ``tmp_path``. Only a target that really is one of THIS checkout's top-level
    trees can be sparse-omitted, so anything outside ``root`` (or ``root``
    itself) answers None and the sparse check stays inert.
    """
    base = Path(root or ROOT)
    try:
        rel = Path(path).resolve().relative_to(base.resolve())
    except (ValueError, OSError, RuntimeError):
        return None
    return rel.parts[0] if rel.parts else None


def trees_for(*paths, root: str | Path | None = None) -> list[str]:
    """The distinct top-level trees ``paths`` live in — a guard's ``needed`` list.

    Derived from the paths the guard was actually pointed at, never hard-coded,
    so redirecting a guard at a scratch directory redirects the sparse check too.
    """
    names = set()
    for p in paths:
        name = tree_name(p, root)
        if name is not None:
            names.add(name)
    return sorted(names)


def sparse_refusal(needed, root: str | Path | None = None) -> str | None:
    """Remedy line iff a tree in ``needed`` is sparse-omitted; else None."""
    try:
        from scripts.worktree_sparse import missing_dirs, remedy_line
    except Exception:  # noqa: BLE001 — never let the detector break the guard
        return None
    try:
        absent = [d for d in missing_dirs(Path(root or ROOT)) if d in set(needed)]
    except Exception:  # noqa: BLE001 — git missing, unreadable HEAD, hung fs
        return None
    return remedy_line(absent) if absent else None


def refuse_if_vacuous(checked_count: int, needed, slug: str,
                      root: str | Path | None = None) -> str | None:
    """The refusal message when ``checked_count`` is 0 AND a needed tree is omitted.

    Returns None when the caller should proceed normally — which is every case
    except the one this module exists for. On a refusal the GitHub annotation is
    emitted here (a bare ``print``, never a logger: a prefixed record is dropped
    by GitHub, see CLAUDE.md) and the caller prints its own line and exits
    non-zero.
    """
    if checked_count:
        return None
    remedy = sparse_refusal(needed, root)
    if not remedy:
        return None
    msg = (f"checked 0 item(s) and would have reported a PASS, but {remedy}. "
           f"An empty tree is not a clean tree — refusing rather than greening.")
    print(f"::error title={slug}::{msg}", flush=True)
    return msg
