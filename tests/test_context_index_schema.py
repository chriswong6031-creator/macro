"""
CXI-1 schema tests.

Uses tmp_path only — never touches real data/, site/, or .context-index/.
"""

import json
import sqlite3

import pytest

from engine.context_index.schema import (
    SCHEMA_VERSION,
    drop_and_recreate,
    get_meta,
    open_db,
    schema_version_matches,
    set_meta,
)


def test_open_creates_tables(tmp_path):
    conn = open_db(tmp_path)
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "documents" in tables
    assert "chunks" in tables
    assert "meta" in tables
    conn.close()


def test_fts_table_exists(tmp_path):
    conn = open_db(tmp_path)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
    ).fetchone()
    assert row is not None, "chunks_fts virtual table missing"
    conn.close()


def test_meta_roundtrip(tmp_path):
    conn = open_db(tmp_path)
    set_meta(conn, "schema_version", "1")
    conn.commit()
    assert get_meta(conn, "schema_version") == "1"
    assert get_meta(conn, "nonexistent") is None
    conn.close()


def test_schema_version_matches(tmp_path):
    conn = open_db(tmp_path)
    assert not schema_version_matches(conn)
    set_meta(conn, "schema_version", str(SCHEMA_VERSION))
    conn.commit()
    assert schema_version_matches(conn)
    conn.close()


def test_drop_and_recreate(tmp_path):
    conn = open_db(tmp_path)
    # Insert something
    conn.execute(
        "INSERT INTO documents (document_id, source_uri, content_hash, authority_class)"
        " VALUES ('abc', 'repo://x', 'h', 'A3')"
    )
    conn.commit()
    count_before = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    assert count_before == 1

    drop_and_recreate(conn)
    count_after = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    assert count_after == 0
    conn.close()


def test_document_id_constraint(tmp_path):
    conn = open_db(tmp_path)
    conn.execute(
        "INSERT INTO documents (document_id, source_uri, content_hash, authority_class)"
        " VALUES ('d1', 'repo://a', 'h1', 'A2')"
    )
    conn.commit()
    # Duplicate document_id should fail
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO documents (document_id, source_uri, content_hash, authority_class)"
            " VALUES ('d1', 'repo://b', 'h2', 'A2')"
        )
        conn.commit()
    conn.close()


def test_fts_insert_trigger(tmp_path):
    """Insert a chunk and verify FTS can find it."""
    conn = open_db(tmp_path)
    conn.execute(
        "INSERT INTO documents (document_id, source_uri, content_hash, authority_class, path, title)"
        " VALUES ('d1', 'repo://test.md', 'h', 'A3', 'test.md', 'Test Doc')"
    )
    conn.execute(
        "INSERT INTO chunks (chunk_id, document_id, ordinal, locator, text)"
        " VALUES ('c1', 'd1', 0, 'test.md#intro', 'Hello retrieval world')"
    )
    conn.commit()

    rows = conn.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'retrieval'"
    ).fetchall()
    assert len(rows) >= 1, "FTS did not index the chunk text"
    conn.close()


def test_fts_delete_trigger(tmp_path):
    """Delete a chunk and verify FTS no longer finds it."""
    conn = open_db(tmp_path)
    conn.execute(
        "INSERT INTO documents (document_id, source_uri, content_hash, authority_class)"
        " VALUES ('d1', 'repo://test.md', 'h', 'A3')"
    )
    conn.execute(
        "INSERT INTO chunks (chunk_id, document_id, ordinal, locator, text)"
        " VALUES ('c1', 'd1', 0, 'test.md#intro', 'unique_token_xyz')"
    )
    conn.commit()

    # Verify FTS finds it
    found = conn.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'unique_token_xyz'"
    ).fetchall()
    assert len(found) >= 1

    # Delete the chunk
    conn.execute("DELETE FROM chunks WHERE chunk_id='c1'")
    conn.commit()

    gone = conn.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'unique_token_xyz'"
    ).fetchall()
    assert len(gone) == 0, "FTS still returns deleted chunk"
    conn.close()


def test_fts_delete_clears_title_and_symbol(tmp_path):
    """
    Finding #10: FTS delete trigger must pass original title/path/symbol so that
    phantom postings are not left behind.  After chunk deletion, MATCH on
    title/symbol must return nothing.
    """
    conn = open_db(tmp_path)
    conn.execute(
        "INSERT INTO documents (document_id, source_uri, content_hash, authority_class, path, title)"
        " VALUES ('d1', 'repo://sym_test.py', 'h', 'A2', 'sym_test.py', 'UniqueTitleZ')"
    )
    conn.execute(
        "INSERT INTO chunks (chunk_id, document_id, ordinal, locator, text, symbol)"
        " VALUES ('c1', 'd1', 0, 'sym_test.py#sym', 'bodytextZ', 'symZ')"
    )
    conn.commit()

    # Verify all three fields are findable before delete
    assert len(conn.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'bodytextZ'").fetchall()) >= 1
    assert len(conn.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'UniqueTitleZ'").fetchall()) >= 1
    assert len(conn.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'symZ'").fetchall()) >= 1

    conn.execute("DELETE FROM chunks WHERE chunk_id='c1'")
    conn.commit()

    # After delete, nothing should match
    assert len(conn.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'bodytextZ'").fetchall()) == 0, \
        "Phantom posting for text after delete"
    assert len(conn.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'UniqueTitleZ'").fetchall()) == 0, \
        "Phantom posting for title after delete"
    assert len(conn.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'symZ'").fetchall()) == 0, \
        "Phantom posting for symbol after delete"
    conn.close()


def test_authority_class_constraint(tmp_path):
    conn = open_db(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO documents (document_id, source_uri, content_hash, authority_class)"
            " VALUES ('d1', 'repo://x', 'h', 'INVALID')"
        )
        conn.commit()
    conn.close()
