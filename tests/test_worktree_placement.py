"""Session worktrees are planted under the checkout the SESSION was launched in.

THE DEFECT THIS PINS
--------------------
``.claude/hooks/worktree_create_sparse.py`` derived its destination from
``git rev-parse --git-common-dir``. That command answers with the MAIN working
tree's ``.git`` from EVERY checkout of a clone, so ``common.parent`` is a
constant per clone — it cannot vary with where the session was launched. On this
host that constant is ``Macro Dashboard``, the one folder the workspace law tells
every session never to open, so every Claude worktree landed there however the
operator started the session. Nothing else in the fleet had the bug: Codex,
Cursor and Grok place worktrees relative to the session's own donor checkout,
which is exactly why the symptom read as "Claude-exclusive".

The paired half is ``scripts/worktree_gc.py``. Its configured roots are
repo-RELATIVE and were expanded under the primary alone, so a tree planted beside
a second checkout matched no root: invisible to ``in_scope``, absent from the
report, and refused at the deletion belt as "outside configured roots". Moving
placement without moving the sweep would have made every new tree unreclaimable —
on a host that has already hit ENOSPC twice.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts import worktree_gc as wgc

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = REPO_ROOT / ".claude" / "hooks" / "worktree_create_sparse.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("_worktree_create_sparse", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _git(cwd: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    assert p.returncode == 0, f"git {' '.join(args)} failed: {p.stderr}"
    return p.stdout.strip()


@pytest.fixture()
def clone(tmp_path: Path) -> dict:
    """A clone with TWO checkouts: the primary and a designated local root.

    This is the real topology — ``macro-main`` is a linked worktree of
    ``Macro Dashboard``, not a second clone — and it is the topology in which
    ``--git-common-dir`` and ``--show-toplevel`` disagree.
    """
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   capture_output=True, check=True)
    primary = tmp_path / "primary"
    primary.mkdir()
    _git(primary, "init", "-b", "main")
    _git(primary, "config", "user.email", "t@t")
    _git(primary, "config", "user.name", "t")
    (primary / "config").mkdir()
    (primary / "config" / "sparse_worktree.json").write_text(
        json.dumps({"enabled": False, "exclude_dirs": []}), encoding="utf-8")
    (primary / "README.md").write_text("hello\n", encoding="utf-8")
    _git(primary, "add", "-A")
    _git(primary, "commit", "-m", "init")
    _git(primary, "remote", "add", "origin", str(origin))
    _git(primary, "push", "-u", "origin", "main")
    local_root = tmp_path / "local-root"
    _git(primary, "worktree", "add", "-b", "local-root", str(local_root), "main")
    return {"primary": primary, "origin": origin, "local_root": local_root}


# ── placement: the hook ──────────────────────────────────────────────────────

def test_common_dir_is_the_same_from_both_checkouts(clone: dict) -> None:
    """The premise: the OLD derivation could not distinguish the two checkouts."""
    from_primary = _git(clone["primary"], "rev-parse", "--path-format=absolute",
                        "--git-common-dir")
    from_local = _git(clone["local_root"], "rev-parse", "--path-format=absolute",
                      "--git-common-dir")
    assert Path(from_primary).resolve() == Path(from_local).resolve()
    assert Path(from_local).parent.resolve() == clone["primary"].resolve()


def test_hook_plants_under_the_session_checkout(clone: dict) -> None:
    """End-to-end: a session launched in the local root gets its tree there."""
    env = {k: v for k, v in os.environ.items() if k != "MACRO_LOCAL_ROOT"}
    payload = json.dumps({"name": "placement-probe", "cwd": str(clone["local_root"])})
    proc = subprocess.run(["python3", str(HOOK_PATH)], input=payload,
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    dest = Path(proc.stdout.strip())
    assert dest == clone["local_root"] / ".claude" / "worktrees" / "placement-probe"
    assert dest.is_dir()
    # The regression, stated as an assertion: NOT under the primary checkout.
    with pytest.raises(ValueError):
        dest.resolve().relative_to(clone["primary"].resolve())
    registered = _git(clone["primary"], "worktree", "list", "--porcelain")
    assert str(dest.resolve()) in registered.replace(str(dest), str(dest.resolve()))


def test_spawn_inside_a_session_worktree_plants_a_sibling_not_a_child(clone: dict) -> None:
    """Nesting would hide the child from the GC's depth-1 orphan scan."""
    inside = clone["local_root"] / ".claude" / "worktrees" / "some-session"
    common = clone["primary"] / ".git"
    host = hook.resolve_host(inside, common, clone["primary"])
    assert host == clone["local_root"]


def test_climb_out_of_a_home_dir_root_falls_back_to_the_primary(clone: dict) -> None:
    """``~/.codex/worktrees/<name>/<checkout>`` is owned by a home dir, not a checkout."""
    outside = Path.home() / ".codex" / "worktrees" / "some-task" / "Macro Dashboard"
    host = hook.resolve_host(outside, clone["primary"] / ".git", clone["primary"])
    assert host == clone["primary"]


def test_macro_local_root_is_the_operator_override(clone: dict, monkeypatch) -> None:
    monkeypatch.setenv("MACRO_LOCAL_ROOT", str(clone["local_root"]))
    host = hook.resolve_host(clone["primary"], clone["primary"] / ".git", clone["primary"])
    assert host == clone["local_root"].resolve()


def test_macro_local_root_pointing_elsewhere_is_ignored(clone: dict, monkeypatch,
                                                        tmp_path: Path) -> None:
    """A stale override must not silently redirect spawns out of the repository."""
    stranger = tmp_path / "not-a-checkout"
    stranger.mkdir()
    monkeypatch.setenv("MACRO_LOCAL_ROOT", str(stranger))
    host = hook.resolve_host(clone["local_root"], clone["primary"] / ".git",
                             clone["primary"])
    assert host == clone["local_root"]


@pytest.mark.parametrize("root", [
    ".claude/worktrees/", ".claire/worktrees/", ".codex/worktrees/",
    ".codex-worktrees/", ".cursor/worktrees/", ".grok/worktrees/",
])
def test_every_fleet_root_is_climbed_out_of(root: str) -> None:
    owner = Path("/repo")
    assert hook.climb_out_of_session_root(owner / root / "tree") == owner


# ── sweep: the GC ────────────────────────────────────────────────────────────

def test_relative_roots_expand_under_every_host() -> None:
    hosts = [Path("/primary"), Path("/local-root")]
    roots = wgc.expand_roots(hosts, [".claude/worktrees", "~/.codex/worktrees"])
    assert Path("/primary/.claude/worktrees") in roots
    assert Path("/local-root/.claude/worktrees") in roots
    assert sum(1 for r in roots if str(r).endswith(".codex/worktrees")) == 1


def test_expand_roots_still_accepts_a_single_host() -> None:
    assert wgc.expand_roots(Path("/primary"), [".claude/worktrees"]) == [
        Path("/primary/.claude/worktrees")]


def test_a_session_tree_is_never_treated_as_a_host() -> None:
    """Otherwise the sweeper expands roots inside the trees it is reclaiming."""
    registered = [
        wgc.Worktree(path=Path("/primary/.claude/worktrees/a")),
        wgc.Worktree(path=Path("/local-root")),
    ]
    hosts = wgc.host_checkouts(Path("/primary"), registered, [".claude/worktrees"])
    assert Path("/local-root") in hosts
    assert Path("/primary/.claude/worktrees/a") not in hosts


def test_worktree_beside_a_second_checkout_is_swept(clone: dict, tmp_path: Path,
                                                    monkeypatch) -> None:
    """The whole point: a tree the sweeper cannot SEE it can never reclaim."""
    tree = clone["local_root"] / ".claude" / "worktrees" / "stale"
    tree.parent.mkdir(parents=True)
    _git(clone["primary"], "worktree", "add", "-b", "stale", str(tree), "main")

    registered = wgc.parse_worktree_list(
        _git(clone["primary"], "worktree", "list", "--porcelain"))
    hosts = wgc.host_checkouts(clone["primary"], registered, [".claude/worktrees"])
    roots = wgc.expand_roots(hosts, [".claude/worktrees"])
    in_scope = [w for w in registered if any(wgc._under(w.path, r) for r in roots)]
    assert [w.path.resolve() for w in in_scope] == [tree.resolve()]

    orphan_dir = clone["local_root"] / ".claude" / "worktrees" / "unregistered"
    orphan_dir.mkdir()
    orphans = wgc.scan_orphans(hosts, roots, registered)
    assert [o.path.resolve() for o in orphans] == [orphan_dir.resolve()]


def test_the_deletion_belt_refuses_a_host_checkout(clone: dict) -> None:
    """Deleting the designated local root would destroy every sibling worktree."""
    host = wgc.Worktree(path=clone["local_root"], verdict="SAFE_MERGED", proof="test")
    summary = wgc.apply_deletions(
        clone["primary"], [host], {"armed": True, "max_delete_per_run": 10},
        roots=[clone["local_root"]], dry_run=True, hosts=[clone["local_root"]])
    assert summary["deleted"] == []
    assert any("host checkout" in e for e in summary["errors"])
