"""
CXI-1 schema: dataclasses, SQLite DDL, connection helpers, and migration.

SCHEMA_VERSION = 1.  A version bump triggers a full rebuild (see ingest.py).
No third-party deps — stdlib + sqlite3 only.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = 2  # bumped: chunks_fts changed from external-content to contentless

# ---------------------------------------------------------------------------
# Dataclasses (in-memory representations; no ORM overhead)
# ---------------------------------------------------------------------------


@dataclass
class Document:
    document_id: str          # sha256("doc:" + source_uri)[:24]
    source_uri: str           # repo://path or other stable URI
    source_type: str          # code|test|config|research|memory|ruling|git|pr|live
    authority_class: str      # A0..A5
    content_hash: str         # sha256 of raw file bytes
    path: str = ""
    title: str = ""
    project_ids: str = "[]"   # json list
    visibility: str = "shared"
    status: str = "active"
    git_sha: str = ""
    source_as_of: str = ""
    ingested_at: str = ""
    tombstoned: int = 0


@dataclass
class ChunkDraft:
    """Returned by every chunker before IDs are assigned."""
    locator: str              # path#heading-slug, path#symbol-qualname, etc.
    heading_path: list = field(default_factory=list)   # json-serialisable list
    symbol: str = ""
    text: str = ""


@dataclass
class Chunk:
    chunk_id: str             # sha256("chunk:" + document_id + ":" + locator)[:24]
    document_id: str
    ordinal: int
    locator: str
    text: str
    heading_path: str = "[]"  # json
    symbol: str = ""
    token_count: int = 0
    content_hash: str = ""
    neighbor_before: str = ""
    neighbor_after: str = ""


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS documents (
    rowid           INTEGER PRIMARY KEY,
    document_id     TEXT    UNIQUE NOT NULL,
    project_ids     TEXT    DEFAULT '[]',
    source_type     TEXT,
    source_uri      TEXT    UNIQUE NOT NULL,
    path            TEXT,
    title           TEXT,
    authority_class TEXT    CHECK(authority_class IN ('A0','A1','A2','A3','A4','A5')),
    visibility      TEXT    DEFAULT 'shared',
    status          TEXT    DEFAULT 'active',
    content_hash    TEXT    NOT NULL,
    git_sha         TEXT,
    source_as_of    TEXT,
    ingested_at     TEXT,
    tombstoned      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chunks (
    rowid           INTEGER PRIMARY KEY,
    chunk_id        TEXT    UNIQUE NOT NULL,
    document_id     TEXT    NOT NULL,
    ordinal         INTEGER,
    locator         TEXT    NOT NULL,
    heading_path    TEXT    DEFAULT '[]',
    symbol          TEXT,
    text            TEXT    NOT NULL,
    token_count     INTEGER,
    content_hash    TEXT,
    neighbor_before TEXT,
    neighbor_after  TEXT
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);

-- FTS5 contentless table; sync triggers below maintain all postings explicitly.
-- Using content='' avoids the broken external-content rebuild/integrity-check
-- (chunks lacks title/path/headings columns that chunks_fts references).
-- All inserts/deletes/updates supply the full column set via the triggers.
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    title,
    path,
    headings,
    symbol,
    content=''
);

-- Sync triggers
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text, title, path, headings, symbol)
    SELECT new.rowid,
           new.text,
           (SELECT title FROM documents WHERE document_id = new.document_id),
           (SELECT path  FROM documents WHERE document_id = new.document_id),
           new.heading_path,
           new.symbol;
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, title, path, headings, symbol)
    SELECT 'delete', old.rowid, old.text,
           COALESCE((SELECT title FROM documents WHERE document_id = old.document_id), ''),
           COALESCE((SELECT path  FROM documents WHERE document_id = old.document_id), ''),
           COALESCE(old.heading_path, ''),
           COALESCE(old.symbol, '');
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, title, path, headings, symbol)
    SELECT 'delete', old.rowid, old.text,
           COALESCE((SELECT title FROM documents WHERE document_id = old.document_id), ''),
           COALESCE((SELECT path  FROM documents WHERE document_id = old.document_id), ''),
           COALESCE(old.heading_path, ''),
           COALESCE(old.symbol, '');
    INSERT INTO chunks_fts(rowid, text, title, path, headings, symbol)
    SELECT new.rowid,
           new.text,
           (SELECT title FROM documents WHERE document_id = new.document_id),
           (SELECT path  FROM documents WHERE document_id = new.document_id),
           new.heading_path,
           new.symbol;
END;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def _db_path(db_dir: Path) -> Path:
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "shared.sqlite"


def open_db(db_dir: Path) -> sqlite3.Connection:
    """Open (or create) the shared SQLite DB; apply DDL; return connection."""
    conn = sqlite3.connect(_db_path(db_dir), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _apply_ddl(conn)
    return conn


def _apply_ddl(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def schema_version_matches(conn: sqlite3.Connection) -> bool:
    v = get_meta(conn, "schema_version")
    return v is not None and int(v) == SCHEMA_VERSION


def needs_rebuild(conn: sqlite3.Connection, config_hash: str) -> bool:
    """Return True if schema version or config hash has changed."""
    if not schema_version_matches(conn):
        return True
    stored_cfg = get_meta(conn, "config_hash")
    return stored_cfg != config_hash


def drop_and_recreate(conn: sqlite3.Connection) -> None:
    """Nuclear option: drop all tables/indexes/triggers, then recreate."""
    conn.executescript("""
        DROP TABLE IF EXISTS chunks_fts;
        DROP TRIGGER IF EXISTS chunks_ai;
        DROP TRIGGER IF EXISTS chunks_ad;
        DROP TRIGGER IF EXISTS chunks_au;
        DROP TABLE IF EXISTS chunks;
        DROP TABLE IF EXISTS documents;
        DROP TABLE IF EXISTS meta;
    """)
    _apply_ddl(conn)
