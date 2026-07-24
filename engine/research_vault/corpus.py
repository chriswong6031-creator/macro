"""research_vault.corpus — standalone FTS5 search index (corpus.sqlite).

Full-text search over research documents: title + summary + BODY + institution.
The API loads this DB from R2 into the VPS with a TTL cache for read-only queries.

House law CXI-R23: this is a SEPARATE corpus that only borrows the *code* from
``engine/context_index`` — it NEVER imports, opens, or queries the CXI databases,
and PDFs are NEVER added as CXI sources. The FTS5 contentless-table + trigger
pattern is copied from ``context_index/schema.py`` and the BM25 query + sanitizer
from ``context_index/lexical.py``.

Column weights (masterplan §8): title=4, summary=3, body=1.
Facets (institution, date) are indexed columns on the ``documents`` table →
compound ``WHERE`` alongside the FTS ``MATCH``. stdlib + sqlite3 only.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

# ---------------------------------------------------------------------------
# DDL — contentless FTS5 + sync triggers (copied idiom: context_index/schema.py)
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

_DDL = """
-- Rollback-journal (single-file) mode, NOT WAL: the corpus is written in one
-- hourly batch then the WHOLE .sqlite file is published to R2, so every commit
-- must land in the main file (no -wal/-shm sidecars whose writes would be lost
-- when only the main file is uploaded). Read-only API access needs no WAL.
PRAGMA journal_mode=DELETE;

-- Public-safe document metadata + the body text kept ONLY for search (never in
-- the catalog). rowid links to the contentless FTS table below.
CREATE TABLE IF NOT EXISTS documents (
    rowid          INTEGER PRIMARY KEY,
    doc_id         TEXT UNIQUE NOT NULL,
    title          TEXT,
    summary        TEXT,
    institution    TEXT,
    side           TEXT,
    published_at   TEXT,
    published_date TEXT,          -- YYYY-MM-DD facet (compound WHERE)
    body           TEXT
);

CREATE INDEX IF NOT EXISTS idx_rv_docs_inst ON documents(institution);
CREATE INDEX IF NOT EXISTS idx_rv_docs_date ON documents(published_date);

-- FTS5 contentless table; triggers below maintain all postings explicitly (same
-- reasoning as CXI: avoids the external-content rebuild/integrity-check path).
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title,
    summary,
    body,
    institution,
    content=''
);

CREATE TRIGGER IF NOT EXISTS rv_docs_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, title, summary, body, institution)
    VALUES (new.rowid, new.title, new.summary, new.body, new.institution);
END;

CREATE TRIGGER IF NOT EXISTS rv_docs_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, summary, body, institution)
    VALUES ('delete', old.rowid,
            COALESCE(old.title, ''), COALESCE(old.summary, ''),
            COALESCE(old.body, ''), COALESCE(old.institution, ''));
END;

CREATE TRIGGER IF NOT EXISTS rv_docs_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, summary, body, institution)
    VALUES ('delete', old.rowid,
            COALESCE(old.title, ''), COALESCE(old.summary, ''),
            COALESCE(old.body, ''), COALESCE(old.institution, ''));
    INSERT INTO documents_fts(rowid, title, summary, body, institution)
    VALUES (new.rowid, new.title, new.summary, new.body, new.institution);
END;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# bm25(documents_fts, w_title, w_summary, w_body, w_institution) — §8 weights.
_BM25_WEIGHTS = "4.0, 3.0, 1.0, 2.0"

_EXCERPT_LEN = 240

# Per-document body-text cap. The corpus ships to R2 and is pulled whole by the
# API, so unbounded body text (40-page PDFs ≈ 100KB+ each) would balloon the
# .sqlite into hundreds of MB across a multi-thousand-doc backfill. 60KB keeps
# roughly the first 15-25 pages searchable — headline/thesis/core argument —
# while bounding the file. Raise deliberately if deep-tail search matters more
# than transfer size.
BODY_MAX_CHARS = 60_000


# ---------------------------------------------------------------------------
# FTS5 query sanitization (copied idiom: context_index/lexical._sanitize_fts5)
# ---------------------------------------------------------------------------

_FTS5_OPERATORS = re.compile(r"\b(AND|OR|NOT)\b")
_FTS5_SPECIAL = re.compile(r"[(){}\[\]^*\"'\\]")


def sanitize_fts5(query: str) -> str:
    """Free-text user query → safe FTS5 MATCH expression.

    Strips FTS5 boolean operators + special chars, wraps each token as an exact
    phrase, ORs them, and adds a full-phrase variant when >1 token. Returns ''
    for empty/degenerate input (caller must then return no results, not MATCH '').
    """
    if not query or not query.strip():
        return ""
    text = _FTS5_OPERATORS.sub(" ", query)
    text = _FTS5_SPECIAL.sub(" ", text)
    tokens = [t for t in text.split() if len(t) >= 2]
    safe = [t.replace('"', "") for t in tokens]
    safe = [t for t in safe if t]
    if not safe:
        return ""
    parts = [f'"{t}"' for t in safe]
    if len(safe) > 1:
        parts.append('"' + " ".join(safe) + '"')
    return " OR ".join(parts)


# ---------------------------------------------------------------------------
# open / build
# ---------------------------------------------------------------------------

def open_db(path: str | Path) -> sqlite3.Connection:
    """Open (or create) corpus.sqlite, apply DDL, stamp schema version."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    conn.execute(
        "INSERT INTO meta(key,value) VALUES('schema_version',?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------

def upsert(conn: sqlite3.Connection, item: dict, body_text: str) -> None:
    """Insert/replace one document's searchable row.

    ``item`` is a normalized sidecar item (see sidecar.normalize). ``body_text``
    is the pdftotext-extracted body ('' when extraction failed — the row is still
    searchable by title/summary). Delete-then-insert keeps the FTS postings in
    sync via the triggers (a bare REPLACE would not fire the delete trigger for
    the old body). Never raises on a benign duplicate.
    """
    doc_id = item.get("id") or ""
    title = item.get("title") or ""
    summary = " • ".join(item.get("summary_points") or [])
    institution = item.get("institution") or ""
    side = item.get("side") or ""
    published_at = item.get("published_at") or ""
    published_date = published_at[:10] if len(published_at) >= 10 else ""
    body = (body_text or "")[:BODY_MAX_CHARS]

    conn.execute("DELETE FROM documents WHERE doc_id=?", (doc_id,))
    conn.execute(
        """INSERT INTO documents
           (doc_id, title, summary, institution, side, published_at, published_date, body)
           VALUES (?,?,?,?,?,?,?,?)""",
        (doc_id, title, summary, institution, side, published_at, published_date, body),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

def _excerpt(text: str, limit: int = _EXCERPT_LEN) -> str:
    text = " ".join((text or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")


def search(
    conn: sqlite3.Connection,
    q: str,
    institution: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """FTS5 BM25 search with optional institution + date-range facets.

    Returns ranked rows (best first) as dicts:
      {id, title, institution, side, published_at, summary, excerpt, rank}.
    The excerpt is drawn from the summary when present, else the body. Facet-only
    queries (empty ``q`` but an institution/date filter) are supported via a plain
    metadata scan. Returns [] on empty/degenerate input. Never raises.
    """
    fts = sanitize_fts5(q)
    where: list[str] = []
    params: list = []

    if institution:
        where.append("d.institution = ?")
        params.append(institution)
    if date_from:
        where.append("d.published_date >= ?")
        params.append(date_from[:10])
    if date_to:
        where.append("d.published_date <= ?")
        params.append(date_to[:10])

    try:
        if fts:
            sql = f"""
                SELECT d.doc_id, d.title, d.institution, d.side, d.published_at,
                       d.summary, d.body,
                       bm25(documents_fts, {_BM25_WEIGHTS}) AS score
                FROM documents_fts
                JOIN documents d ON d.rowid = documents_fts.rowid
                WHERE documents_fts MATCH ?
                {(' AND ' + ' AND '.join(where)) if where else ''}
                ORDER BY score
                LIMIT ?
            """
            rows = conn.execute(sql, [fts, *params, limit]).fetchall()
        else:
            # No text query: facet-only listing (newest first).
            if not where:
                return []
            sql = f"""
                SELECT d.doc_id, d.title, d.institution, d.side, d.published_at,
                       d.summary, d.body, 0.0 AS score
                FROM documents d
                WHERE {' AND '.join(where)}
                ORDER BY d.published_at DESC
                LIMIT ?
            """
            rows = conn.execute(sql, [*params, limit]).fetchall()
    except sqlite3.OperationalError:
        # Malformed MATCH or missing table — degrade to empty.
        return []

    out: list[dict] = []
    for r in rows:
        summary = r["summary"] or ""
        out.append({
            "id": r["doc_id"],
            "title": r["title"] or "",
            "institution": r["institution"] or "",
            "side": r["side"] or "",
            "published_at": r["published_at"] or "",
            "summary": summary,
            "excerpt": _excerpt(summary or r["body"]),
            "rank": float(r["score"]),
        })
    return out


def institutions(conn: sqlite3.Connection) -> list[str]:
    """Distinct institutions present in the corpus (sorted)."""
    rows = conn.execute(
        "SELECT DISTINCT institution FROM documents WHERE institution <> '' ORDER BY institution"
    ).fetchall()
    return [r["institution"] for r in rows]
