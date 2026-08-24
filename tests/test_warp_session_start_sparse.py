"""Regression coverage for Warp/Oz carrier ownership and minting."""
from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
from types import SimpleNamespace
from pathlib import Path

import pytest

from scripts import worktree_sparse as sparse

REPO_ROOT = Path(__file__).resolve().parents[1]
WARP_HOOK_PATH = REPO_ROOT / ".warp" / "hooks" / "session_start_sparse.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("_warp_session_start_sparse", WARP_HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.fixture()
def warp_clone(tmp_path: Path) -> dict[str, Path]:
    origin = tmp_path / "mastermindx-market-intelligence" / "macro" / "origin.git"
    origin.parent.mkdir(parents=True)
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True,
                   capture_output=True)
    donor = tmp_path / "macro-main"
    donor.mkdir()
    _git(donor, "init", "-b", "main")
    _git(donor, "config", "user.email", "warp@test")
    _git(donor, "config", "user.name", "warp")
    (donor / "config").mkdir()
    (donor / "config" / "sparse_worktree.json").write_text(
        json.dumps({"enabled": True, "exclude_dirs": ["site"]}), encoding="utf-8")
    (donor / "site").mkdir()
    (donor / "site" / "asset.txt").write_text("heavy\n", encoding="utf-8")
    (donor / "README.md").write_text("initial\n", encoding="utf-8")
    _git(donor, "add", "-A")
    _git(donor, "commit", "-m", "initial")
    _git(donor, "remote", "add", "origin", str(origin))
    _git(donor, "push", "-u", "origin", "main")
    return {"donor": donor, "origin": origin}


def _hook_for(monkeypatch, clone: dict[str, Path], payload: dict):
    module = _load_hook()
    monkeypatch.setattr(module, "STUDIO_LOCAL_ROOT", clone["donor"])
    monkeypatch.setattr(module, "ORIGIN_MARKERS", ("mastermindx-market-intelligence/macro",))
    monkeypatch.setattr(module, "_load_ws", lambda donor: sparse)
    monkeypatch.setattr(module, "read_payload", lambda: payload)
    return module


def _workspace(capsys) -> Path:
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("WORKSPACE=")]
    assert len(lines) == 1
    return Path(lines[0].split("=", 1)[1])


def _carrier_name(identity: str) -> str:
    return f"warp-{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"


def _no_workspace(capsys) -> None:
    assert "WORKSPACE=" not in capsys.readouterr().out


def test_identityless_start_uses_a_new_collision_resistant_carrier(monkeypatch) -> None:
    hook = _load_hook()
    values = iter(("a" * 32, "b" * 32, "c" * 32))
    monkeypatch.delenv("WARP_TERMINAL_SESSION_UUID", raising=False)
    monkeypatch.delenv("WARP_SESSION_ID", raising=False)
    monkeypatch.delenv("WARP_CONVERSATION_ID", raising=False)
    monkeypatch.setattr(hook.uuid, "uuid4", lambda: SimpleNamespace(hex=next(values)))

    first, first_proven = hook.worktree_name({})
    second, second_proven = hook.worktree_name({})
    assert (first, first_proven) == ("warp-" + "a" * 32, False)
    assert (second, second_proven) == ("warp-" + "b" * 32, False)
    assert first != "warp-session"
    monkeypatch.setenv("WARP_TERMINAL_SESSION_UUID", "terminal-only")
    monkeypatch.setenv("WARP_SESSION_ID", "terminal-session-only")
    third, third_proven = hook.worktree_name({})
    assert (third, third_proven) == ("warp-" + "c" * 32, False)


def test_conversation_identity_is_payload_first_and_digest_bound(monkeypatch) -> None:
    hook = _load_hook()
    monkeypatch.setenv("WARP_TERMINAL_SESSION_UUID", "shared-terminal")
    monkeypatch.setenv("WARP_SESSION_ID", "shared-terminal-session")
    monkeypatch.setenv("WARP_CONVERSATION_ID", "environment-conversation")
    identities = [
        "a/b",
        "a?b",
        "p" * 40 + "-first",
        "p" * 40 + "-second",
    ]
    names = [hook.worktree_name({"conversationId": identity}) for identity in identities]

    assert names == [(_carrier_name(identity), True) for identity in identities]
    assert len({name for name, _ in names}) == len(identities)
    assert hook.worktree_name({"conversationId": "payload-wins"}) == (
        _carrier_name("payload-wins"), True,
    )
    assert "payload-wins" not in _carrier_name("payload-wins")


def test_same_terminal_with_different_conversations_never_reuses(
    warp_clone: dict[str, Path], monkeypatch, capsys,
) -> None:
    donor = warp_clone["donor"]
    monkeypatch.setenv("WARP_TERMINAL_SESSION_UUID", "one-terminal")
    monkeypatch.setenv("WARP_SESSION_ID", "one-terminal-session")
    first_payload = {"cwd": str(donor), "conversationId": "conversation-a"}
    second_payload = {"cwd": str(donor), "conversationId": "conversation-b"}
    first_hook = _hook_for(monkeypatch, warp_clone, first_payload)
    assert first_hook.main() == 0
    first = _workspace(capsys)
    second_hook = _hook_for(monkeypatch, warp_clone, second_payload)
    assert second_hook.main() == 0
    second = _workspace(capsys)
    assert first == donor / ".warp" / "worktrees" / _carrier_name("conversation-a")
    assert second == donor / ".warp" / "worktrees" / _carrier_name("conversation-b")
    assert first != second


def test_new_warp_session_does_not_reuse_a_clean_divergent_legacy_carrier(
    warp_clone: dict[str, Path], monkeypatch, capsys,
) -> None:
    donor = warp_clone["donor"]
    monkeypatch.delenv("WARP_CONVERSATION_ID", raising=False)
    old = donor / ".warp" / "worktrees" / "warp-session"
    _git(donor, "worktree", "add", "-b", "warp/warp-session", str(old), "main")
    (old / "legacy.txt").write_text("old task\n", encoding="utf-8")
    _git(old, "add", "legacy.txt")
    _git(old, "commit", "-m", "old divergent task")
    old_head = _git(old, "rev-parse", "HEAD")
    old_bytes = (old / "legacy.txt").read_bytes()
    assert _git(old, "status", "--porcelain") == ""

    (donor / "README.md").write_text("current main\n", encoding="utf-8")
    _git(donor, "commit", "-am", "advance main")
    _git(donor, "push", "origin", "main")

    # This is the historical hole: Warp supplied no identity, so the old hook
    # selected the globally reusable ``warp-session`` carrier above.
    hook = _hook_for(monkeypatch, warp_clone, {"cwd": str(donor)})
    assert hook.main() == 0
    fresh = _workspace(capsys)

    assert fresh != old
    assert _git(old, "rev-parse", "HEAD") == old_head
    assert (old / "legacy.txt").read_bytes() == old_bytes
    assert _git(old, "status", "--porcelain") == ""
    assert _git(fresh, "rev-parse", "HEAD") == _git(donor, "rev-parse", "origin/main")
    assert _git(fresh, "merge", "--ff-only", "origin/main") == "Already up to date."
    assert "site" in sparse.missing_dirs(fresh)
    assert not sparse.sparse_enabled(donor)


def test_identity_bound_carrier_is_idempotent_and_preserves_add_site(
    warp_clone: dict[str, Path], monkeypatch, capsys,
) -> None:
    donor = warp_clone["donor"]
    payload = {"cwd": str(donor), "conversationId": "same-conversation"}
    hook = _hook_for(monkeypatch, warp_clone, payload)
    assert hook.main() == 0
    carrier = _workspace(capsys)
    assert sparse.add_dirs(["site"], root=carrier) == 0
    assert "site" not in sparse.missing_dirs(carrier)

    assert hook.main() == 0
    assert _workspace(capsys) == carrier
    assert "site" not in sparse.missing_dirs(carrier)
    registered = _git(donor, "worktree", "list", "--porcelain")
    assert registered.count(str(carrier)) == 1


def test_foreign_dirty_carrier_is_never_reset_or_stolen(
    warp_clone: dict[str, Path], monkeypatch, capsys,
) -> None:
    donor = warp_clone["donor"]
    old = donor / ".warp" / "worktrees" / "warp-session"
    _git(donor, "worktree", "add", "-b", "warp/warp-session", str(old), "main")
    (old / "uncommitted.txt").write_text("preserve me\n", encoding="utf-8")

    hook = _hook_for(monkeypatch, warp_clone, {
        "cwd": str(old), "conversationId": "new-owner",
    })
    assert hook.main() == 0
    fresh = _workspace(capsys)
    assert fresh != old
    assert (old / "uncommitted.txt").read_text(encoding="utf-8") == "preserve me\n"
    assert "?? uncommitted.txt" in _git(old, "status", "--porcelain")


def test_hook_propagates_fetch_failure_without_emitting_workspace(
    warp_clone: dict[str, Path], monkeypatch, capsys,
) -> None:
    donor = warp_clone["donor"]
    original_git = sparse._git
    payload = {"cwd": str(donor), "conversationId": "fetch-refused"}
    hook = _hook_for(monkeypatch, warp_clone, payload)
    fetch_dest = donor / ".warp" / "worktrees" / _carrier_name("fetch-refused")

    def fail_fetch(root: Path, *args: str):
        if args[:1] == ("fetch",):
            return None
        return original_git(root, *args)

    monkeypatch.setattr(sparse, "_git", fail_fetch)
    assert hook.main() == 1
    assert not fetch_dest.exists()
    _no_workspace(capsys)


def test_hook_propagates_missing_base_without_emitting_workspace(
    warp_clone: dict[str, Path], monkeypatch, capsys,
) -> None:
    donor = warp_clone["donor"]
    original_git = sparse._git
    payload = {"cwd": str(donor), "conversationId": "base-refused"}
    hook = _hook_for(monkeypatch, warp_clone, payload)
    dest = donor / ".warp" / "worktrees" / _carrier_name("base-refused")

    def missing_base(root: Path, *args: str):
        if args == ("rev-parse", "--verify", "refs/remotes/origin/main"):
            return None
        return original_git(root, *args)

    monkeypatch.setattr(sparse, "_git", missing_base)
    assert hook.main() == 1
    assert not dest.exists()
    _no_workspace(capsys)


def test_hook_propagates_disabled_profile_without_emitting_workspace(
    warp_clone: dict[str, Path], monkeypatch, capsys,
) -> None:
    donor = warp_clone["donor"]
    (donor / "config" / "sparse_worktree.json").write_text(
        json.dumps({"enabled": False, "exclude_dirs": ["site"]}),
        encoding="utf-8",
    )
    identity = "disabled-profile"
    payload = {"cwd": str(donor), "conversationId": identity}
    dest = donor / ".warp" / "worktrees" / _carrier_name(identity)
    hook = _hook_for(monkeypatch, warp_clone, payload)

    assert hook.main() == 1
    assert not dest.exists()
    _no_workspace(capsys)


def test_hook_propagates_destination_collision_without_emitting_workspace(
    warp_clone: dict[str, Path], monkeypatch, capsys,
) -> None:
    donor = warp_clone["donor"]
    payload = {"cwd": str(donor), "conversationId": "destination-collision"}
    dest = donor / ".warp" / "worktrees" / _carrier_name("destination-collision")
    _git(donor, "worktree", "add", "-b", "warp/foreign", str(dest), "main")
    foreign_head = _git(dest, "rev-parse", "HEAD")

    hook = _hook_for(monkeypatch, warp_clone, payload)
    assert hook.main() == 1
    assert _git(dest, "rev-parse", "HEAD") == foreign_head
    _no_workspace(capsys)


def test_hook_propagates_branch_collision_without_emitting_workspace(
    warp_clone: dict[str, Path], monkeypatch, capsys,
) -> None:
    donor = warp_clone["donor"]
    identity = "branch-collision"
    payload = {"cwd": str(donor), "conversationId": identity}
    name = _carrier_name(identity)
    branch_dest = donor / ".warp" / "worktrees" / name
    _git(donor, "branch", f"warp/{name}", "main")

    hook = _hook_for(monkeypatch, warp_clone, payload)
    assert hook.main() == 1
    assert not branch_dest.exists()
    _no_workspace(capsys)
