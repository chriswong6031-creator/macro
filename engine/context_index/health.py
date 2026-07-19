"""
CXI-1 health report.

Returns JSON with per-source document/chunk counts, tombstone count,
denied/symlink/tripwire counts from a prior IngestResult, DB size, and meta.

PRIVACY: never emits file paths of denied/tripwired files, never emits chunk text.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .schema import get_meta, open_db


def build_health_report(
    db_dir: Path,
    ingest_result=None,  # IngestResult | None
) -> dict:
    """
    Build and return the health JSON dict.

    ingest_result is optional; if provided, denied/symlink/tripwire counts
    come from the live run.  If None, only DB-resident counts are reported.
    """
    conn = open_db(db_dir)

    # Per-source document + chunk counts
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

    db_path = db_dir / "shared.sqlite"
    db_size_bytes = db_path.stat().st_size if db_path.exists() else 0

    indexed_git_sha = get_meta(conn, "indexed_git_sha") or ""
    built_at = get_meta(conn, "built_at") or ""

    conn.close()

    report: dict = {
        "total_docs": total_docs,
        "total_chunks": total_chunks,
        "tombstone_count": tombstone_count,
        "db_size_bytes": db_size_bytes,
        "indexed_git_sha": indexed_git_sha,
        "built_at": built_at,
        "source_stats": source_stats,
    }

    if ingest_result is not None:
        report["denied_count"] = ingest_result.denied_count
        report["symlink_skip_count"] = ingest_result.symlink_skips
        report["tripwire_skip_count"] = ingest_result.tripwire_skips
        report["rebuilt"] = ingest_result.rebuilt

    return report


def format_health_json(report: dict) -> str:
    return json.dumps(report, indent=2)
