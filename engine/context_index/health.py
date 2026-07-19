"""
CXI-1b health report (multi-project).

Returns JSON with per-project document/chunk/tripwire counts, absent_projects list
(keys only — no paths), DB size, and meta.

PRIVACY: never emits file paths of denied/tripwired files, never emits chunk text,
never emits external file paths or text in health output.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from .schema import get_meta


def _open_ro(db_path: Path) -> Optional[sqlite3.Connection]:
    """Open a DB read-only; return None if the file does not exist."""
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _project_health(db_path: Path, proj_result=None) -> dict:
    """Build health block for one project's DB file."""
    conn = _open_ro(db_path)
    if conn is None:
        return {"error": "db not built"}

    rows = conn.execute(
        """
        SELECT d.source_type, d.authority_class,
               COUNT(DISTINCT d.document_id) as doc_count,
               COUNT(c.chunk_id) as chunk_count
        FROM documents d
        LEFT JOIN chunks c ON c.document_id = d.document_id
        WHERE d.tombstoned = 0
        GROUP BY d.source_type, d.authority_class
        ORDER BY d.authority_class, d.source_type
        """
    ).fetchall()

    source_stats: list[dict] = []
    for r in rows:
        source_stats.append({
            "source_type": r["source_type"],
            "authority_class": r["authority_class"],
            "doc_count": r["doc_count"],
            "chunk_count": r["chunk_count"],
        })

    total_docs = conn.execute(
        "SELECT COUNT(*) as n FROM documents WHERE tombstoned=0"
    ).fetchone()["n"]
    total_chunks = conn.execute("SELECT COUNT(*) as n FROM chunks").fetchone()["n"]
    tombstone_count = conn.execute(
        "SELECT COUNT(*) as n FROM documents WHERE tombstoned=1"
    ).fetchone()["n"]

    db_size_bytes = db_path.stat().st_size if db_path.exists() else 0

    indexed_git_sha = get_meta(conn, "indexed_git_sha") or ""
    built_at = get_meta(conn, "built_at") or ""

    conn.close()

    block: dict = {
        "total_docs": total_docs,
        "total_chunks": total_chunks,
        "tombstone_count": tombstone_count,
        "db_size_bytes": db_size_bytes,
        "indexed_git_sha": indexed_git_sha,
        "built_at": built_at,
        "source_stats": source_stats,
    }

    if proj_result is not None:
        block["denied_count"] = proj_result.denied_count
        block["symlink_skip_count"] = proj_result.symlink_skips
        block["tripwire_skip_count"] = proj_result.tripwire_skips
        block["rebuilt"] = proj_result.rebuilt

    return block


def build_health_report(
    db_dir: Path,
    ingest_result=None,   # IngestResult | None
    config=None,          # Config | None — if provided, per-project blocks use correct db names
) -> dict:
    """
    Build and return the health JSON dict.

    Per-project blocks under "projects" key.
    Aggregates rolled up at top level for backwards-compat with single-project callers.
    absent_projects: list of project keys only (no paths — CXI-R13 privacy).
    """
    # Determine project → db_file mapping
    # If config provided: use exact project.db_file names.
    # Fallback: just look for known db files in db_dir.
    proj_db_map: dict[str, str] = {}
    absent: list[str] = []

    if config is not None and hasattr(config, "projects") and hasattr(config, "absent_projects"):
        # MultiProjectConfig (v2)
        for proj in config.projects:
            proj_db_map[proj.key] = proj.db_file
        absent = list(config.absent_projects)
    elif config is not None:
        # Legacy Config(sources, deny) — single macro-dashboard project
        proj_db_map["macro-dashboard"] = "shared.sqlite"
    else:
        # Heuristic: discover sqlite files in db_dir
        for f in sorted(db_dir.glob("*.sqlite")):
            stem = f.stem
            if stem == "shared":
                proj_db_map["macro-dashboard"] = f.name
            else:
                proj_db_map[stem] = f.name

    # Build per-project health blocks
    project_blocks: dict[str, dict] = {}
    for proj_key, db_name in proj_db_map.items():
        proj_result = None
        if ingest_result is not None and proj_key in ingest_result.projects:
            proj_result = ingest_result.projects[proj_key]
        project_blocks[proj_key] = _project_health(db_dir / db_name, proj_result)

    # Aggregate totals
    total_docs = sum(b.get("total_docs", 0) for b in project_blocks.values())
    total_chunks = sum(b.get("total_chunks", 0) for b in project_blocks.values())
    tombstone_count = sum(b.get("tombstone_count", 0) for b in project_blocks.values())
    db_size_bytes = sum(b.get("db_size_bytes", 0) for b in project_blocks.values())

    # For backwards-compat: top-level fields from the "macro-dashboard" project (or first)
    md_block = project_blocks.get("macro-dashboard", {})
    indexed_git_sha = md_block.get("indexed_git_sha", "")
    built_at = md_block.get("built_at", "")

    report: dict = {
        "total_docs": total_docs,
        "total_chunks": total_chunks,
        "tombstone_count": tombstone_count,
        "db_size_bytes": db_size_bytes,
        "indexed_git_sha": indexed_git_sha,
        "built_at": built_at,
        # Legacy field: macro-dashboard source stats for backwards-compat
        "source_stats": md_block.get("source_stats", []),
        # Multi-project fields
        "projects": project_blocks,
        "absent_projects": absent,
    }

    if ingest_result is not None:
        report["denied_count"] = ingest_result.denied_count
        report["symlink_skip_count"] = ingest_result.symlink_skips
        report["tripwire_skip_count"] = ingest_result.tripwire_skips
        report["rebuilt"] = ingest_result.rebuilt

    return report


def format_health_json(report: dict) -> str:
    return json.dumps(report, indent=2)
