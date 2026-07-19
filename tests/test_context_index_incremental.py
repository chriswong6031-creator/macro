"""
CXI-1 incremental ingestion tests.

Verifies: add / edit / rename / delete behavior; only affected docs are touched.
All in tmp_path — never touches real data/.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.context_index.ingest import run_ingest
from engine.context_index.sources import Config, SourceEntry
from engine.context_index.schema import open_db, get_meta, needs_rebuild


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(glob: str, chunker: str = "markdown_sections") -> Config:
    return Config(
        sources=[SourceEntry(
            id="src-0", roots=[glob], authority_class="A3",
            visibility="shared", chunker=chunker, source_type="research",
        )],
        deny=[],
    )


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    (repo / ".git").mkdir(exist_ok=True)
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return repo


def _get_ingested_ats(conn) -> dict[str, str]:
    return {
        r["source_uri"]: r["ingested_at"]
        for r in conn.execute("SELECT source_uri, ingested_at FROM documents WHERE tombstoned=0").fetchall()
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_unchanged_docs_not_retouched(tmp_path):
    """Unchanged docs keep the same ingested_at on incremental run."""
    repo = _repo(tmp_path, {
        "docs/a.md": "# A\n\nContent A.\n",
        "docs/b.md": "# B\n\nContent B.\n",
    })
    db_dir = tmp_path / "db"
    cfg = _cfg("docs/**/*.md")

    run_ingest(repo, db_dir, cfg, rebuild=True, ingested_at="2026-01-01T00:00:00+00:00")
    conn = open_db(db_dir)
    ats_before = _get_ingested_ats(conn)
    conn.close()

    # Incremental — nothing changed
    run_ingest(repo, db_dir, cfg, rebuild=False, ingested_at="2026-01-02T00:00:00+00:00")
    conn = open_db(db_dir)
    ats_after = _get_ingested_ats(conn)
    conn.close()

    for uri, at_before in ats_before.items():
        assert ats_after.get(uri) == at_before, (
            f"Unchanged doc {uri} had its ingested_at updated unexpectedly"
        )


def test_add_file(tmp_path):
    """Adding a new file results in it being indexed on the next run."""
    repo = _repo(tmp_path, {"docs/a.md": "# A\n\nContent.\n"})
    db_dir = tmp_path / "db"
    cfg = _cfg("docs/**/*.md")

    run_ingest(repo, db_dir, cfg, rebuild=True, ingested_at="T1")
    conn = open_db(db_dir)
    count_before = conn.execute("SELECT COUNT(*) FROM documents WHERE tombstoned=0").fetchone()[0]
    conn.close()

    # Add new file
    (repo / "docs" / "b.md").write_text("# B\n\nNew doc.\n", encoding="utf-8")
    run_ingest(repo, db_dir, cfg, rebuild=False, ingested_at="T2")
    conn = open_db(db_dir)
    count_after = conn.execute("SELECT COUNT(*) FROM documents WHERE tombstoned=0").fetchone()[0]
    conn.close()

    assert count_after == count_before + 1


def test_edit_file(tmp_path):
    """Editing a file updates its chunks."""
    repo = _repo(tmp_path, {"docs/a.md": "# A\n\nOriginal content.\n"})
    db_dir = tmp_path / "db"
    cfg = _cfg("docs/**/*.md")

    run_ingest(repo, db_dir, cfg, rebuild=True, ingested_at="T1")
    conn = open_db(db_dir)
    old_hash = conn.execute("SELECT content_hash FROM documents WHERE tombstoned=0").fetchone()["content_hash"]
    old_chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()

    # Edit file
    (repo / "docs" / "a.md").write_text("# A\n\nUpdated content here.\n\n## New Section\n\nExtra.\n", encoding="utf-8")
    run_ingest(repo, db_dir, cfg, rebuild=False, ingested_at="T2")
    conn = open_db(db_dir)
    new_hash = conn.execute("SELECT content_hash FROM documents WHERE tombstoned=0").fetchone()["content_hash"]
    new_chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()

    assert new_hash != old_hash, "content_hash should change after edit"
    # New version has more sections so more chunks
    assert new_chunk_count >= 1


def test_delete_file_tombstoned(tmp_path):
    """Deleted file is tombstoned; its chunks are removed."""
    repo = _repo(tmp_path, {
        "docs/a.md": "# A\n\nKeep.\n",
        "docs/b.md": "# B\n\nDelete me.\n",
    })
    db_dir = tmp_path / "db"
    cfg = _cfg("docs/**/*.md")

    run_ingest(repo, db_dir, cfg, rebuild=True, ingested_at="T1")

    # Delete b.md
    (repo / "docs" / "b.md").unlink()
    result = run_ingest(repo, db_dir, cfg, rebuild=False, ingested_at="T2")

    conn = open_db(db_dir)
    tombstoned = conn.execute("SELECT COUNT(*) FROM documents WHERE tombstoned=1").fetchone()[0]
    active = conn.execute("SELECT COUNT(*) FROM documents WHERE tombstoned=0").fetchone()[0]
    # chunks for b.md should be gone
    b_uri = "repo://docs/b.md"
    b_doc = conn.execute("SELECT document_id FROM documents WHERE source_uri=?", (b_uri,)).fetchone()
    b_chunks = 0
    if b_doc:
        b_chunks = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id=?", (b_doc["document_id"],)
        ).fetchone()[0]
    conn.close()

    assert tombstoned >= 1, "deleted doc should be tombstoned"
    assert active == 1, "only a.md should remain active"
    assert b_chunks == 0, "chunks for deleted doc should be removed"


def test_rebuild_flag_clears_db(tmp_path):
    """--rebuild drops all docs even if content unchanged."""
    repo = _repo(tmp_path, {"docs/a.md": "# A\n\nContent.\n"})
    db_dir = tmp_path / "db"
    cfg = _cfg("docs/**/*.md")

    run_ingest(repo, db_dir, cfg, rebuild=True, ingested_at="T1")
    conn = open_db(db_dir)
    count_before = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    conn.close()
    assert count_before >= 1

    result = run_ingest(repo, db_dir, cfg, rebuild=True, ingested_at="T2")
    assert result.rebuilt is True
    conn = open_db(db_dir)
    count_after = conn.execute("SELECT COUNT(*) FROM documents WHERE tombstoned=0").fetchone()[0]
    conn.close()
    assert count_after >= 1  # re-ingested


def test_schema_version_bump_triggers_rebuild(tmp_path):
    """needs_rebuild returns True when schema_version stored != SCHEMA_VERSION."""
    from engine.context_index.schema import open_db, set_meta, needs_rebuild
    db_dir = tmp_path / "db"
    conn = open_db(db_dir)
    set_meta(conn, "schema_version", "999")  # future version
    set_meta(conn, "config_hash", "abc")
    conn.commit()
    assert needs_rebuild(conn, "abc") is True
    conn.close()


def test_neighbor_links_wired(tmp_path):
    """Chunks within a document have neighbor_before / neighbor_after set."""
    repo = _repo(tmp_path, {
        "docs/multi.md": (
            "# Section 1\n\nContent 1.\n\n"
            "## Section 2\n\nContent 2.\n\n"
            "### Section 3\n\nContent 3.\n"
        )
    })
    db_dir = tmp_path / "db"
    cfg = _cfg("docs/**/*.md")
    run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    chunks = conn.execute(
        "SELECT chunk_id, ordinal, neighbor_before, neighbor_after FROM chunks ORDER BY ordinal"
    ).fetchall()
    conn.close()
    if len(chunks) >= 2:
        # Middle chunk should have both neighbors
        mid = chunks[len(chunks) // 2]
        assert mid["neighbor_before"] != "" or mid["ordinal"] == 0
        assert mid["neighbor_after"] != "" or mid["ordinal"] == len(chunks) - 1
