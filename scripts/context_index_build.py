#!/usr/bin/env python3
"""
CXI-1 build CLI.

Usage:
    python3 scripts/context_index_build.py [--rebuild]
    python3 scripts/context_index_build.py --status

Environment:
    MACRO_CONTEXT_INDEX_DIR   Override default .context-index/ dir (optional)

ABSOLUTE RULE: this script writes ONLY to .context-index/ (or the env override).
It must never write to data/, site/, or any other repo tree.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Resolve repo root (walk up from this script looking for .git)
_SCRIPT = Path(__file__).resolve()


def _find_repo_root() -> Path:
    candidate = _SCRIPT.parent
    for _ in range(10):
        if (candidate / ".git").exists():
            return candidate
        candidate = candidate.parent
    raise RuntimeError("Could not find repo root (no .git directory found)")


def _db_dir(repo_root: Path) -> Path:
    env_override = os.environ.get("MACRO_CONTEXT_INDEX_DIR", "").strip()
    if env_override:
        return Path(env_override)
    return repo_root / ".context-index"


def _config_path(repo_root: Path) -> Path:
    return repo_root / "config" / "context_index.yml"


def cmd_build(repo_root: Path, db_dir: Path, rebuild: bool) -> int:
    from engine.context_index.sources import load_config
    from engine.context_index.ingest import run_ingest
    from engine.context_index.health import build_health_report, format_health_json

    cfg_path = _config_path(repo_root)
    if not cfg_path.exists():
        print(f"ERROR: config not found at {cfg_path}", file=sys.stderr)
        return 1

    config = load_config(cfg_path)

    t0 = time.time()
    result = run_ingest(repo_root, db_dir, config, rebuild=rebuild)
    elapsed = time.time() - t0

    report = build_health_report(db_dir, ingest_result=result)
    report["build_wall_time_s"] = round(elapsed, 2)

    print(format_health_json(report))
    return 0


def cmd_status(repo_root: Path, db_dir: Path) -> int:
    from engine.context_index.health import build_health_report, format_health_json
    from engine.context_index.schema import open_db, get_meta
    import subprocess

    db_sqlite = db_dir / "shared.sqlite"
    if not db_sqlite.exists():
        print('{"error": "index not built — run context_index_build.py first"}')
        return 1

    report = build_health_report(db_dir)

    # Compare indexed SHA vs current HEAD
    try:
        cur_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(repo_root), timeout=5,
        ).stdout.strip()
    except Exception:
        cur_sha = ""

    report["current_git_sha"] = cur_sha
    report["index_stale"] = (
        bool(cur_sha) and bool(report["indexed_git_sha"])
        and cur_sha != report["indexed_git_sha"]
    )

    print(format_health_json(report))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="CXI-1 Context Index build CLI")
    parser.add_argument("--rebuild", action="store_true", help="Force full rebuild")
    parser.add_argument("--status", action="store_true", help="Print health JSON only")
    args = parser.parse_args()

    repo_root = _find_repo_root()
    # Add repo root to sys.path so `engine` package is importable
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    db_dir = _db_dir(repo_root)

    if args.status:
        return cmd_status(repo_root, db_dir)
    else:
        return cmd_build(repo_root, db_dir, rebuild=args.rebuild)


if __name__ == "__main__":
    sys.exit(main())
