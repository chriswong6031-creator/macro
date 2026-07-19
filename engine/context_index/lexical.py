"""
CXI-2 lexical retriever — FTS5/BM25 over chunks_fts per in-scope project DB.

Returns ranked list of result dicts:
  {chunk_id, document_id, source_uri, locator, path, authority_class, status,
   visibility, project, rank, raw_score, why}

Query sanitization: user input → safe FTS5 MATCH expression.
Column weights: text=1.0, title=4.0, path=3.0, headings=2.0, symbol=4.0.
Post-rank transparent modifiers (not score fusion):
  - A0/A1 authority bump (shift rank up)
  - A4 recency flag (tag only, no rank change)

stdlib + sqlite3 only.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# FTS5 query sanitization
# ---------------------------------------------------------------------------

_FTS5_OPERATORS = re.compile(r'\b(AND|OR|NOT)\b')
_FTS5_SPECIAL = re.compile(r'[(){}\[\]^*"\'\\]')

# Token shapes that look like identifiers we should preserve as-is quoted
_IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_.]*$')


def _sanitize_fts5(query: str) -> str:
    """
    Convert free-text user query into a safe FTS5 MATCH expression.

    Strategy:
      1. Strip FTS5 operators and special chars that could cause syntax errors.
      2. Extract individual tokens.
      3. Wrap each token in double quotes (exact phrase match).
      4. Build: "<tok1>" OR "<tok2>" OR ... OR "<tok1> <tok2>" (phrase variant).
    """
    if not query or not query.strip():
        return ""

    # Remove FTS5 boolean operators
    text = _FTS5_OPERATORS.sub(" ", query)
    # Replace special FTS5 chars with spaces
    text = _FTS5_SPECIAL.sub(" ", text)

    tokens = [t for t in text.split() if len(t) >= 2]
    if not tokens:
        return ""

    # Escape any double-quotes remaining inside tokens (shouldn't be any after above)
    safe_tokens = [t.replace('"', '') for t in tokens]
    safe_tokens = [t for t in safe_tokens if t]

    if not safe_tokens:
        return ""

    # Individual token terms: "tok"
    parts = [f'"{t}"' for t in safe_tokens]

    # Phrase variant: "tok1 tok2 ..." (only if > 1 token)
    if len(safe_tokens) > 1:
        phrase = " ".join(safe_tokens)
        parts.append(f'"{phrase}"')

    return " OR ".join(parts)


# ---------------------------------------------------------------------------
# BM25 column weights
# BM25() returns a negative score (more negative = better match).
# FTS5 column order in chunks_fts: text, title, path, headings, symbol
# ---------------------------------------------------------------------------

# bm25(chunks_fts, weight_text, weight_title, weight_path, weight_headings, weight_symbol)
_BM25_WEIGHTS = "1.0, 4.0, 3.0, 2.0, 4.0"

# ---------------------------------------------------------------------------
# Authority bump: A0/A1 results get a positional boost (lower rank wins)
# ---------------------------------------------------------------------------

_HIGH_AUTH = {"A0", "A1"}
_BUMP_SLOTS = 10  # authority bump is applied before returning


def _open_project_db(db_dir: Path, db_file: str) -> Optional[sqlite3.Connection]:
    """Open a project DB by filename; return None if absent."""
    db_path = db_dir / db_file
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def search_project(
    db_path: Path,
    fts5_query: str,
    project_key: str,
    top_n: int = 50,
) -> list[dict]:
    """
    Run FTS5 search against one project DB.  Returns up to top_n raw results.

    Each result dict: {chunk_id, document_id, source_uri, locator, path,
                       authority_class, status, visibility, project,
                       rank, raw_score, why}
    """
    if not db_path.exists():
        return []
    if not fts5_query:
        return []

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        return _run_fts5(conn, fts5_query, project_key, top_n)
    finally:
        conn.close()


def _run_fts5(
    conn: sqlite3.Connection,
    fts5_query: str,
    project_key: str,
    top_n: int,
) -> list[dict]:
    """Execute the FTS5 MATCH query and join to documents."""
    try:
        rows = conn.execute(
            f"""
            SELECT
                c.chunk_id,
                c.document_id,
                c.locator,
                c.heading_path,
                c.symbol,
                d.source_uri,
                d.path,
                d.authority_class,
                -- For kill-registry rows, chunk.symbol carries the per-row status;
                -- fall back to document-level status for other docs.
                CASE
                  WHEN c.symbol IN ('forbidden','killed','deferred','superseded','unknown')
                  THEN c.symbol
                  ELSE d.status
                END AS status,
                d.visibility,
                bm25(chunks_fts, {_BM25_WEIGHTS}) AS bm25_score
            FROM chunks_fts
            JOIN chunks c ON c.rowid = chunks_fts.rowid
            JOIN documents d ON d.document_id = c.document_id
            WHERE chunks_fts MATCH ?
              AND d.tombstoned = 0
            ORDER BY bm25_score
            LIMIT ?
            """,
            (fts5_query, top_n * 2),  # fetch extra to allow authority re-sorting
        ).fetchall()
    except sqlite3.OperationalError:
        # Malformed query or missing table — return empty
        return []

    results = []
    for rank_0, row in enumerate(rows):
        results.append({
            "chunk_id": row["chunk_id"],
            "document_id": row["document_id"],
            "source_uri": row["source_uri"],
            "locator": row["locator"],
            "path": row["path"] or "",
            "authority_class": row["authority_class"] or "A3",
            "status": row["status"] or "active",
            "visibility": row["visibility"] or "shared",
            "project": project_key,
            "rank": rank_0 + 1,
            "raw_score": float(row["bm25_score"]),
            "why": "fts5_bm25",
            "heading_path": row["heading_path"] or "[]",
            "symbol": row["symbol"] or "",
        })

    # Authority bump: float A0/A1 to top slots without changing score
    high = [r for r in results if r["authority_class"] in _HIGH_AUTH]
    rest = [r for r in results if r["authority_class"] not in _HIGH_AUTH]
    reordered = high + rest

    # Re-assign rank
    for i, r in enumerate(reordered):
        r["rank"] = i + 1

    return reordered[:top_n]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def lexical_search(
    query: str,
    db_dir: Path,
    project_db_map: dict[str, str],   # project_key → db_filename
    top_n: int = 50,
) -> list[dict]:
    """
    Search all projects in project_db_map.  Returns merged list sorted by rank
    (per-project rank used as-is; caller does fusion across projects).

    project_db_map example: {"macro-dashboard": "shared.sqlite", "terminal": "terminal.sqlite"}
    """
    fts5_query = _sanitize_fts5(query)
    if not fts5_query:
        return []

    all_results: list[dict] = []
    for project_key, db_file in project_db_map.items():
        db_path = db_dir / db_file
        project_results = search_project(db_path, fts5_query, project_key, top_n)
        all_results.extend(project_results)

    return all_results
