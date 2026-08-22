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

1. Session worktree already — run ``auto`` (idempotent; preserves ``add site``).
2. Macro host checkout that is not a session worktree — mint a sparse linked
   worktree under the donor's ``.warp/worktrees/<name>/`` using
   ``git worktree add --no-checkout`` (Claude's pre-checkout shape). Never
   write a pointer file into that checkout: it is a git tree and the pointer
   would be dirt.
3. Anything else — no-op. Never sparsify the occupied primary or the operator
   local root.

Stdout prints ``WORKSPACE=<path>`` when a session tree is the workspace so a
Warp skill/agent can ``cd`` there. Progress goes to stderr.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HOOK = "WarpSessionStart"
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
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


def worktree_name(cwd: Path, payload: dict) -> str:
    env_session = os.environ.get("WARP_TERMINAL_SESSION_UUID", "").strip()
    if env_session:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", env_session).strip("-")[:40]
        if slug and SAFE_NAME.match(slug):
            return f"warp-{slug}"
    session = payload.get("sessionId") or payload.get("session_id") or ""
    if isinstance(session, str) and session:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", session).strip("-")[:40]
        if slug and SAFE_NAME.match(slug):
            return f"warp-{slug}"
    for part in reversed(cwd.parts):
        if part.startswith("warp-") and SAFE_NAME.match(part):
            return part
    return "warp-session"


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

    if ws.is_session_worktree(cwd):
        log(f"session worktree already; running auto in {cwd}")
        rc = ws.auto_profile(cwd)
        if rc == 0:
            emit_workspace(cwd)
        return 0

    existing = cwd / POINTER_NAME
    if existing.is_file():
        pointed = Path(existing.read_text(encoding="utf-8").strip())
        if pointed.is_dir() and ws.is_session_worktree(pointed):
            log(f"reusing pointer {pointed}")
            rc = ws.auto_profile(pointed)
            if rc == 0:
                emit_workspace(pointed)
            return 0

    if not is_macro_checkout(cwd) or not is_git_checkout(cwd):
        log("not a Macro host checkout; leaving workspace unchanged")
        return 0

    name = worktree_name(cwd, payload)
    dest = donor / ".warp" / "worktrees" / name
    branch = f"warp/{name}"
    log(f"minting sparse worktree {dest} off origin/main")
    rc = ws.mint_session_worktree(
        donor, dest, branch=branch, base="refs/remotes/origin/main", fetch=True,
    )
    if rc == 0:
        write_pointer(cwd, dest)
        emit_workspace(dest)
        log(f"workspace -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
