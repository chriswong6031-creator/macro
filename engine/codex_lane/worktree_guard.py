"""engine/codex_lane/worktree_guard.py — Worktree tamper-guard for codex sessions (D6).

Two never-raise functions:

    snapshot(root, protect) -> dict
        Captures git porcelain state + byte-copies of protect-files.

    restore(root, handle, allowed) -> list[str]
        Reverts any changes the session made outside `allowed`, byte-restores
        tampered protect-files, returns violation descriptions.

Protect list (both lanes):
    data/signal_foundry/candidates.jsonl
    data/signal_foundry/governance.jsonl
    data/signal_foundry/lane_status.json
    data/codex_lane/usage_state.json
    data/codex_lane/loop_journal.jsonl
    data/codex_lane/case_attempts.jsonl
    data/trial_ledger.jsonl
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

# Default protect list — both lanes wire this
DEFAULT_PROTECT = [
    "data/signal_foundry/candidates.jsonl",
    "data/signal_foundry/governance.jsonl",
    "data/signal_foundry/lane_status.json",
    "data/codex_lane/usage_state.json",
    "data/codex_lane/loop_journal.jsonl",
    "data/codex_lane/case_attempts.jsonl",
    "data/trial_ledger.jsonl",
]


def _run_porcelain_z(root: Path) -> list[tuple[str, str, str | None]]:
    """Run ``git status --porcelain -z`` and parse records.

    Returns a list of ``(xy, path, orig_path)`` tuples where:
    - ``xy`` is the two-character status code (e.g. ``"??"``, ``" M"``)
    - ``path`` is the primary (new) path
    - ``orig_path`` is the rename/copy source path, or ``None``

    NEVER raises — returns empty list on any error.
    """
    try:
        result = subprocess.run(  # noqa: S603
            ["git", "status", "--porcelain", "-z"],
            cwd=str(root),
            capture_output=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return []

        # -z output: NUL-terminated records; renames carry an extra NUL-terminated orig field
        raw = result.stdout  # bytes
        # Split on NUL — trailing NUL gives one empty token at the end
        tokens = raw.split(b"\x00")
        entries: list[tuple[str, str, str | None]] = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            i += 1
            if not token:
                continue
            # Each record: b"XY path" — first two bytes are XY, then a space, then path
            if len(token) < 4:
                continue
            xy = token[:2].decode("utf-8", errors="replace")
            path = token[3:].decode("utf-8", errors="replace")
            orig: str | None = None
            # Renames/copies: XY[0] in {R, C} means next token is the ORIGINAL path
            if xy[0] in ("R", "C") and i < len(tokens) and tokens[i]:
                orig = tokens[i].decode("utf-8", errors="replace")
                i += 1
            entries.append((xy, path, orig))
        return entries
    except Exception as exc:  # noqa: BLE001
        log.warning("worktree_guard._run_porcelain_z: failed (%s)", exc)
        return []


def _porcelain_key(xy: str, path: str) -> str:
    """Return a canonical string key for a porcelain entry (used in snapshot set)."""
    return f"{xy} {path}"


def _is_inside_root(candidate_path: Path, root_resolved: Path) -> bool:
    """Return True if *candidate_path* is inside *root_resolved*.

    Uses ``os.path.commonpath`` which is immune to path-prefix false-positives
    (e.g. ``/foo/bar`` would match ``/foo/bar2`` with a startswith check).
    Falls back to False on any exception (e.g. different Windows drives).
    """
    try:
        return os.path.commonpath([str(candidate_path), str(root_resolved)]) == str(root_resolved)
    except Exception:  # noqa: BLE001
        return False


def snapshot(root: Path, protect: list[str]) -> dict:
    """Capture git porcelain + byte-copies of existing protect-files.

    Returns:
        {
            "porcelain": set[str],       # set of "XY path" keys from porcelain -z output
            "copies": {rel: tmp_path},   # rel path -> tmp file path with copy
            "tmpdir": str,               # temp directory containing copies
        }

    NEVER raises. On any internal failure logs a warning and returns partial data.
    """
    handle: dict = {"porcelain": set(), "copies": {}, "tmpdir": ""}
    try:
        tmpdir = tempfile.mkdtemp(prefix="codex-guard-")
        handle["tmpdir"] = tmpdir

        # (a) git status --porcelain -z (NUL-delimited, no C-quoting of paths)
        try:
            entries = _run_porcelain_z(root)
            porcelain: set[str] = set()
            for xy, path, orig in entries:
                porcelain.add(_porcelain_key(xy, path))
                if orig is not None:
                    porcelain.add(_porcelain_key(xy, orig))
            handle["porcelain"] = porcelain
        except Exception as exc:  # noqa: BLE001
            log.warning("worktree_guard.snapshot: porcelain failed (%s); snapshot partial", exc)
            handle["porcelain"] = set()

        # (b) Copy each existing protect-file to tmpdir
        copies: dict[str, str] = {}
        for rel in protect:
            src = root / rel
            if src.exists():
                try:
                    dst = Path(tmpdir) / rel.replace("/", "_").replace("\\", "_")
                    shutil.copy2(str(src), str(dst))
                    copies[rel] = str(dst)
                except Exception as exc:  # noqa: BLE001
                    log.warning("worktree_guard.snapshot: could not copy %s (%s)", rel, exc)
        handle["copies"] = copies

    except Exception as exc:  # noqa: BLE001
        log.warning("worktree_guard.snapshot: unexpected error (%s); guard disabled", exc)

    return handle


def restore(root: Path, handle: dict, allowed: set[str]) -> list[str]:
    """Undo unauthorised changes made since snapshot().

    Steps:
    1. Re-run git status --porcelain. For each new entry (not in handle["porcelain"]):
       - If path is in `allowed` or is a protect-file path → skip (leave intact).
       - If tracked (XY starts with ' M'/'M '/'D '/etc.) → `git checkout -- <path>`.
       - If untracked ('??') and the resolved path is inside root → unlink.
    2. For each protect-file whose bytes now differ from the snapshot copy → byte-restore
       from the copy and record a violation.
    3. Remove tmpdir.

    Returns list of violation description strings (empty = clean).
    NEVER raises.
    """
    violations: list[str] = []
    try:
        prior_porcelain: set[str] = handle.get("porcelain", set())
        copies: dict[str, str] = handle.get("copies", {})
        tmpdir: str = handle.get("tmpdir", "")

        # Normalise allowed to a set of relative strings
        allowed_set: set[str] = set(allowed) if allowed else set()

        # Protect-file rel paths set for quick lookup
        protect_rels: set[str] = set(copies.keys())

        # Step 1 — re-run porcelain -z and revert new unauthorised entries
        try:
            root_resolved = root.resolve()
            entries = _run_porcelain_z(root)
            for xy, path, orig in entries:
                # Collect all paths this record touches
                paths_to_check = [path]
                if orig is not None:
                    paths_to_check.append(orig)

                for rel in paths_to_check:
                    key = _porcelain_key(xy, rel)
                    if key in prior_porcelain:
                        continue  # existed before snapshot — not new

                    if rel in allowed_set or rel in protect_rels:
                        continue  # allowed — leave it

                    # For untracked directories (porcelain reports "dir/"), also skip if any
                    # allowed path or protect-file lives inside that directory.
                    if rel.endswith("/") and (
                        any(a.startswith(rel) for a in allowed_set)
                        or any(p.startswith(rel) for p in protect_rels)
                    ):
                        continue  # directory contains allowed content — leave it

                    is_untracked = xy == "??"
                    if is_untracked:
                        # Resolve the parent directory only (never follow a symlink in rel itself)
                        try:
                            rel_path = Path(rel)
                            parent_resolved = (root / rel_path.parent).resolve()
                            candidate = parent_resolved / rel_path.name

                            if not _is_inside_root(candidate, root_resolved):
                                log.warning(
                                    "worktree_guard.restore: %s resolved outside root — skipping", rel
                                )
                                continue

                            # Untracked directory: remove the whole tree
                            if rel.endswith("/"):
                                if candidate.is_dir() and not candidate.is_symlink():
                                    shutil.rmtree(str(candidate), ignore_errors=True)
                                    violations.append(f"untracked_dir_removed:{rel}")
                            elif candidate.is_symlink():
                                # Unauthorized symlink — unlink without following
                                candidate.unlink()
                                violations.append(f"untracked_symlink_removed:{rel}")
                            elif candidate.is_file():
                                candidate.unlink()
                                violations.append(f"untracked_removed:{rel}")
                        except Exception as exc:  # noqa: BLE001
                            log.warning(
                                "worktree_guard.restore: could not remove untracked %s (%s)", rel, exc
                            )
                    else:
                        # Tracked change — restore via git checkout
                        try:
                            subprocess.run(  # noqa: S603
                                ["git", "checkout", "--", rel],
                                cwd=str(root),
                                capture_output=True,
                                text=True,
                                timeout=30,
                                check=False,
                            )
                            violations.append(f"tracked_reverted:{rel}")
                        except Exception as exc:  # noqa: BLE001
                            log.warning(
                                "worktree_guard.restore: checkout -- %s failed (%s)", rel, exc
                            )
        except Exception as exc:  # noqa: BLE001
            log.warning("worktree_guard.restore: re-porcelain failed (%s)", exc)

        # Step 2 — check protect-files for tampering
        for rel, tmp_path in copies.items():
            try:
                src = root / rel
                if not src.exists():
                    if Path(tmp_path).exists():
                        # File was deleted — restore from copy
                        src.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(tmp_path, str(src))
                        violations.append(f"protect_restored_deleted:{rel}")
                    continue
                current_bytes = src.read_bytes()
                orig_bytes = Path(tmp_path).read_bytes()
                if current_bytes != orig_bytes:
                    # Tampered — byte-restore from copy
                    src.write_bytes(orig_bytes)
                    violations.append(f"protect_restored_tampered:{rel}")
            except Exception as exc:  # noqa: BLE001
                log.warning("worktree_guard.restore: protect-file check failed for %s (%s)", rel, exc)

    except Exception as exc:  # noqa: BLE001
        log.warning("worktree_guard.restore: unexpected error (%s); returning partial violations", exc)

    # Step 3 — cleanup tmpdir
    try:
        tmpdir_val = handle.get("tmpdir", "")
        if tmpdir_val:
            shutil.rmtree(tmpdir_val, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("worktree_guard.restore: tmpdir cleanup failed (%s)", exc)

    return violations
