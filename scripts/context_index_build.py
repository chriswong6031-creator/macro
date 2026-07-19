#!/usr/bin/env python3
"""
CXI-1b build CLI (multi-project).

Usage:
    python3 scripts/context_index_build.py [--rebuild] [--project <key>]
    python3 scripts/context_index_build.py --status [--project <key>]

Environment:
    MACRO_CONTEXT_INDEX_DIR          Override default .context-index/ dir (optional)
    MACRO_CTX_TERMINAL_ROOT          Override terminal project root
    MACRO_CTX_MASTERMIND_ROOT        Override mastermind project root

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


def cmd_build(
    repo_root: Path,
    db_dir: Path,
    rebuild: bool,
    project_filter: str | None = None,
) -> int:
    from engine.context_index.sources import load_config
    from engine.context_index.ingest import run_ingest
    from engine.context_index.health import build_health_report, format_health_json

    cfg_path = _config_path(repo_root)
    if not cfg_path.exists():
        print(f"ERROR: config not found at {cfg_path}", file=sys.stderr)
        return 1

    config = load_config(cfg_path)

    if project_filter:
        known = {p.key for p in config.projects}
        if project_filter not in known and project_filter not in config.absent_projects:
            print(f"ERROR: unknown project key {project_filter!r}. Known: {sorted(known)}", file=sys.stderr)
            return 1

    t0 = time.time()
    result = run_ingest(repo_root, db_dir, config, rebuild=rebuild, project_filter=project_filter)
    elapsed = time.time() - t0

    report = build_health_report(db_dir, ingest_result=result, config=config)
    report["build_wall_time_s"] = round(elapsed, 2)

    if result.absent_projects:
        print(f"INFO: absent projects (skipped): {result.absent_projects}", file=sys.stderr)

    if project_filter:
        # Only print the requested project block (mirrors cmd_status behaviour)
        proj_block = report.get("projects", {}).get(project_filter)
        if proj_block is not None:
            print(format_health_json({project_filter: proj_block}))
        else:
            print(format_health_json(report))
    else:
        print(format_health_json(report))
    return 0


def cmd_status(
    repo_root: Path,
    db_dir: Path,
    project_filter: str | None = None,
) -> int:
    from engine.context_index.health import build_health_report, format_health_json
    from engine.context_index.sources import load_config
    import subprocess

    cfg_path = _config_path(repo_root)
    config = None
    if cfg_path.exists():
        try:
            config = load_config(cfg_path)
        except Exception:
            pass

    # Check that at least the macro-dashboard DB exists
    default_db = db_dir / "shared.sqlite"
    if not default_db.exists():
        print('{"error": "index not built — run context_index_build.py first"}')
        return 1

    report = build_health_report(db_dir, config=config)

    # Per-project SHA staleness check
    if config is not None:
        for proj in config.projects:
            try:
                cur_sha = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    capture_output=True, text=True, cwd=str(proj.root), timeout=5,
                ).stdout.strip()
            except Exception:
                cur_sha = ""
            proj_block = report["projects"].get(proj.key, {})
            indexed_sha = proj_block.get("indexed_git_sha", "")
            proj_block["current_git_sha"] = cur_sha
            proj_block["index_stale"] = (
                bool(cur_sha) and bool(indexed_sha) and cur_sha != indexed_sha
            )
    else:
        # Legacy single-project compat
        try:
            cur_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, cwd=str(repo_root), timeout=5,
            ).stdout.strip()
        except Exception:
            cur_sha = ""
        report["current_git_sha"] = cur_sha
        report["index_stale"] = (
            bool(cur_sha) and bool(report.get("indexed_git_sha"))
            and cur_sha != report.get("indexed_git_sha")
        )

    if project_filter and config is not None:
        # Only print the requested project block
        proj_block = report["projects"].get(project_filter)
        if proj_block is None:
            print(f'{{"error": "project {project_filter!r} not found in health report"}}')
            return 1
        print(format_health_json({project_filter: proj_block}))
    else:
        print(format_health_json(report))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="CXI-1b Context Index build CLI (multi-project)")
    parser.add_argument("--rebuild", action="store_true", help="Force full rebuild")
    parser.add_argument("--status", action="store_true", help="Print health JSON only")
    parser.add_argument("--project", metavar="KEY", default=None,
                        help="Only build/show status for this project key")
    args = parser.parse_args()

    repo_root = _find_repo_root()
    # Add repo root to sys.path so `engine` package is importable
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    db_dir = _db_dir(repo_root)

    if args.status:
        return cmd_status(repo_root, db_dir, project_filter=args.project)
    else:
        return cmd_build(repo_root, db_dir, rebuild=args.rebuild, project_filter=args.project)


if __name__ == "__main__":
    sys.exit(main())
