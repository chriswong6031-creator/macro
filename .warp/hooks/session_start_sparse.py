#!/usr/bin/env python3
"""Warp/Oz session hook — sparse session worktrees.

Claude has a pre-checkout ``WorktreeCreate`` hook. Codex and Cursor call
``scripts/worktree_sparse.py auto`` after their harness has already created a
linked worktree. Grok/AionUi mint under ``.grok/worktrees/`` from an empty
temp dir.

Warp has no documented SessionStart or WorktreeCreate event. Local Warp
sessions start in whichever folder the operator opened — usually the occupied
primary or the designated local root ``macro-main``, which is itself a linked
worktree and must never be sparsified. This script is the missing mint:

1. Same identity-bound conversation carrier — run ``auto`` (idempotent;
   preserves ``add site``).
2. Any Macro checkout without that identity-bound carrier — mint a sparse linked
   worktree under the donor's ``.warp/worktrees/<name>/`` using
   ``git worktree add --no-checkout`` (Claude's pre-checkout shape). Never
   write a pointer file into that checkout: it is a git tree and the pointer
   would be dirt.
3. A path or branch collision — fail closed without taking over the existing
   carrier. Anything else — no-op. Never sparsify the occupied primary or the
   operator local root.

Stdout prints ``WORKSPACE=<path>`` when a session tree is the workspace so a
Warp skill/agent can ``cd`` there. Progress goes to stderr.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

HOOK = "WarpSessionStart"
POINTER_NAME = ".session-worktree"
STUDIO_LOCAL_ROOT = Path("/Users/chriswong/Documents/Cluade/macro-main")
ORIGIN_MARKERS = ("mastermindx-market-intelligence/macro",)


def log(msg: str) -> None:
    print(f"{HOOK}: {msg}", file=sys.stderr, flush=True)


def emit_workspace(dest: Path) -> None:
    print(f"WORKSPACE={dest}", flush=True)


def _load_ws(donor: Path):
    import importlib.util

    here = Path(__file__).resolve()
    candidates = [
        donor / "scripts" / "worktree_sparse.py",
        STUDIO_LOCAL_ROOT / "scripts" / "worktree_sparse.py",
    ]
    if len(here.parents) >= 2 and here.parents[1].name == ".warp":
        candidates.append(here.parents[2] / "scripts" / "worktree_sparse.py")
    candidates.append(here.parent / "worktree_sparse.py")
    loaded = []
    for script in candidates:
        if not script.is_file():
            continue
        spec = importlib.util.spec_from_file_location("worktree_sparse", script)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded.append(module)
    if not loaded:
        raise RuntimeError("cannot load scripts/worktree_sparse.py")
    for module in loaded:
        if hasattr(module, "mint_session_worktree"):
            return module
    return loaded[0]


def _git_origin(root: Path) -> str:
    try:
        proc = __import__("subprocess").run(
            ("git", "-C", str(root), "remote", "get-url", "origin"),
            capture_output=True, text=True, timeout=15, check=False,
        )
    except Exception:  # noqa: BLE001
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def is_macro_checkout(root: Path) -> bool:
    origin = _git_origin(root)
    return any(marker in origin for marker in ORIGIN_MARKERS)


def is_git_checkout(root: Path) -> bool:
    return (root / ".git").exists()


def discover_donor(cwd: Path) -> Path | None:
    env = os.environ.get("MACRO_LOCAL_ROOT", "").strip()
    if env:
        candidate = Path(env)
        if candidate.is_dir() and is_macro_checkout(candidate):
            return candidate
    if STUDIO_LOCAL_ROOT.is_dir() and is_macro_checkout(STUDIO_LOCAL_ROOT):
        return STUDIO_LOCAL_ROOT
    if cwd.is_dir() and is_macro_checkout(cwd):
        return cwd
    return None


def worktree_name(payload: dict) -> tuple[str, bool]:
    """Return ``(carrier_name, identity_proven)`` for this Warp invocation.

    Only an unambiguous conversation/task identity can establish ownership.
    Terminal and session IDs are intentionally ignored: one terminal can host
    more than one agent conversation. The branch/path suffix is a SHA-256
    digest of the complete raw identity, so no sanitization/truncation collision
    and no raw identifier is written or logged.
    """
    candidates: list[object] = [
        payload.get("conversationId"),
        payload.get("conversation_id"),
        os.environ.get("WARP_CONVERSATION_ID", ""),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
            return f"warp-{digest}", True
    return f"warp-{uuid.uuid4().hex}", False


def _branch(root: Path) -> str:
    try:
        proc = __import__("subprocess").run(
            ("git", "-C", str(root), "branch", "--show-current"),
            capture_output=True, text=True, timeout=15, check=False,
        )
    except Exception:  # noqa: BLE001
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def can_reuse_carrier(ws, dest: Path, branch: str, identity_proven: bool) -> bool:
    """A path is reusable only when Warp positively bound it to this session."""
    return (
        identity_proven
        and dest.is_dir()
        and ws.is_session_worktree(dest)
        and _branch(dest) == branch
    )


def write_pointer(cwd: Path, dest: Path) -> None:
    """Write a pointer only when ``cwd`` is not a git checkout.

    Grok writes ``.session-worktree`` into an empty ``grok-temp-*`` directory.
    Warp sessions start inside a real checkout; a pointer there is dirt.
    """
    if is_git_checkout(cwd):
        return
    try:
        (cwd / POINTER_NAME).write_text(str(dest) + "\n", encoding="utf-8")
    except OSError as exc:
        log(f"could not write {POINTER_NAME}: {exc}")


def read_payload() -> dict:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def main() -> int:
    payload = read_payload()
    cwd_value = payload.get("cwd") or payload.get("workspaceRoot") or os.getcwd()
    if not isinstance(cwd_value, str) or not cwd_value:
        log("no cwd; nothing to do")
        return 0
    cwd = Path(cwd_value)
    donor = discover_donor(cwd)
    if donor is None:
        log("no Macro donor checkout; skipping")
        return 0
    try:
        ws = _load_ws(donor)
    except Exception as exc:  # noqa: BLE001 — session start must not fail the session
        log(f"could not load worktree_sparse.py: {exc}")
        return 0

    name, identity_proven = worktree_name(payload)
    branch = f"warp/{name}"
    dest = donor / ".warp" / "worktrees" / name

    if can_reuse_carrier(ws, dest, branch, identity_proven):
        log(f"reusing identity-bound session carrier {dest}")
        rc = ws.auto_profile(dest)
        if rc == 0:
            emit_workspace(dest)
        return rc

    if dest.exists():
        log(f"carrier collision at {dest}; refusing to take over an existing carrier")
        return 1

    if not is_macro_checkout(cwd) or not is_git_checkout(cwd):
        log("not a Macro host checkout; leaving workspace unchanged")
        return 0

    log(f"minting sparse worktree {dest} off origin/main")
    rc = ws.mint_session_worktree(
        donor, dest, branch=branch, base="refs/remotes/origin/main", fetch=True,
        reuse_existing=False, strict=True,
    )
    if rc == 0:
        if not dest.is_dir() or not ws.is_session_worktree(dest):
            log("mint reported success without creating a linked session carrier")
            return 1
        write_pointer(cwd, dest)
        emit_workspace(dest)
        log(f"workspace -> {dest}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
