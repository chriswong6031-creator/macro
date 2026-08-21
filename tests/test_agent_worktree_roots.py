"""The agent worktree-root list is duplicated in three places; pin them in step.

A repository serving several agent fleets accumulates one checkout root per fleet.
Each root has to be declared three times, and each declaration does a different job:

* ``.gitignore`` — keeps the root out of every session's ``git status``.
* ``config/worktree_gc.json`` ``roots`` — makes the root DELETABLE by the GC, and
  walkable by ``scan_orphans``. Registered worktrees are classified from
  ``git worktree list`` either way, so a missing root does not dent the report —
  it fails later and quietly, at the belt in ``apply_deletions`` that refuses any
  target ``outside configured roots``.
* ``ship_loop_guard.AGENT_WORKTREE_ROOTS`` — excludes another fleet's churn from
  this session's dirty gate.

Drift is silent and each miss fails differently, which is why it went unnoticed
twice. Measured 2026-08-11: ``.codex/worktrees/`` was declared in NONE of the three
while holding 55 live checkouts, so it surfaced as untracked dirt in every session,
could be classified SAFE by the GC and then refused at deletion, and false-blocked a
session at Stop over a Codex tree it could neither commit nor delete. ``.claire/worktrees/``
was in the guard and the GC but not ``.gitignore``.

Home-dir roots (``~/...``) are deliberately out of scope: they are outside the
repository, so neither ``.gitignore`` nor the ship-loop guard can see them.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GC_CONFIG = REPO_ROOT / "config" / "worktree_gc.json"
GITIGNORE = REPO_ROOT / ".gitignore"
GUARD = REPO_ROOT / ".claude" / "hooks" / "ship_loop_guard.py"


def _in_repo_gc_roots() -> set[str]:
    """The GC's repo-relative roots, normalised to a trailing slash."""
    config = json.loads(GC_CONFIG.read_text(encoding="utf-8"))
    roots = config["roots"]
    assert isinstance(roots, list) and roots, "worktree_gc.json declares no roots"
    return {f"{root.rstrip('/')}/" for root in roots if not root.startswith("~")}


def _gitignore_roots() -> set[str]:
    """Every ignore rule that names a worktree root, normalised the same way."""
    found = set()
    for line in GITIGNORE.read_text(encoding="utf-8").splitlines():
        rule = line.strip()
        if not rule or rule.startswith("#"):
            continue
        bare = rule.lstrip("/")
        if bare.endswith("worktrees/") or bare.rstrip("/").endswith("-worktrees"):
            found.add(f"{bare.rstrip('/')}/")
    return found


def _guard_roots() -> set[str]:
    """``AGENT_WORKTREE_ROOTS`` as the guard itself defines it."""
    spec = importlib.util.spec_from_file_location("_ship_loop_guard_roots", GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return set(module.AGENT_WORKTREE_ROOTS)


def test_every_in_repo_gc_root_is_git_ignored() -> None:
    """A swept root that is not ignored is untracked dirt in every session."""
    missing = sorted(_in_repo_gc_roots() - _gitignore_roots())
    assert not missing, (
        f"worktree roots swept by the GC but not git-ignored: {missing}. "
        "Add each to .gitignore beside the other agent worktree roots."
    )


def test_every_in_repo_gc_root_is_excluded_from_the_dirty_gate() -> None:
    """A swept root the guard cannot see false-blocks Stop on another fleet's work."""
    missing = sorted(_in_repo_gc_roots() - _guard_roots())
    assert not missing, (
        f"worktree roots swept by the GC but absent from "
        f"ship_loop_guard.AGENT_WORKTREE_ROOTS: {missing}. A session cannot commit "
        "or delete another fleet's checkout, so the gate is unsatisfiable without them."
    )


def test_every_guarded_root_is_reachable_by_the_gc() -> None:
    """The reverse miss: a root excluded from the gate but never swept leaks disk."""
    missing = sorted(_guard_roots() - _in_repo_gc_roots())
    assert not missing, (
        f"worktree roots excluded from the dirty gate but not swept by the GC: "
        f"{missing}. Add each to config/worktree_gc.json roots."
    )


@pytest.mark.parametrize(
    "root",
    [
        ".claude/worktrees/",
        ".claire/worktrees/",
        ".codex/worktrees/",
        ".codex-worktrees/",
        ".cursor/worktrees/",
        ".grok/worktrees/",
    ],
)
def test_known_fleet_roots_are_declared_everywhere(root: str) -> None:
    """Pin every in-repo fleet root so none silently drops out."""
    assert root in _in_repo_gc_roots(), f"{root} missing from config/worktree_gc.json"
    assert root in _gitignore_roots(), f"{root} missing from .gitignore"
    assert root in _guard_roots(), f"{root} missing from AGENT_WORKTREE_ROOTS"


def test_gc_config_still_declares_the_home_codex_root() -> None:
    """The home-dir root is out of the cross-check; make sure it was not dropped."""
    config = json.loads(GC_CONFIG.read_text(encoding="utf-8"))
    assert "~/.codex/worktrees" in config["roots"], (
        "the home-dir codex root is a DIFFERENT root from the in-repo "
        ".codex/worktrees and must stay declared"
    )


def test_gc_armed_state_matches_the_operator_ratification() -> None:
    """Arming is the operator's ratification act; no code change may do it.

    Until 2026-08-13 this test pinned ``armed is False`` — the anti-drive-by
    guard. The operator ratified arming on 2026-08-13 (chat order during the
    disk-pressure incident: 1.7Ti/1.8Ti used, two receipted runner ENOSPC
    crashes; the ratification text is recorded in the config's
    ``_armed_ratification`` key). The pin now holds the RATIFIED state, which
    keeps the original property: a session cannot flip this field either way
    without the change being loud, deliberate, and traceable to an operator
    order — a bare `"armed": false` diff with no ratification note reds here
    just like a bare `true` used to.
    """
    config = json.loads(GC_CONFIG.read_text(encoding="utf-8"))
    assert config["armed"] is True, (
        "config/worktree_gc.json armed was RATIFIED true by operator order "
        "2026-08-13 (see _armed_ratification in the config). Disarming is "
        "likewise an operator act — record it there and update this pin in "
        "the same commit, per research/WORKTREE_GC_POLICY.md"
    )
    assert "OPERATOR RATIFIED 2026-08-13" in config.get("_armed_ratification", ""), (
        "the armed flag must carry its ratification provenance"
    )
    assert config["min_age_days"] == 3, (
        "min_age_days 3 was part of the same 2026-08-13 ratification "
        "(at 7d the fleet's churn kept the gate permanently closed)"
    )
