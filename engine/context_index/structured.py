"""
CXI-2 structured retriever — deterministic exact lookups, highest priority for governance.

Three lookup strategies (run in order; results merged by chunk_id):
  (a) Kill-registry rows: chunks of research/DO_NOT_REBUILD.md, filtered/boosted
      by term overlap with query; status from chunk.symbol.
  (b) Ruling-graph / compiled-kill-registry / synapse.yml: chunks by key-path/term match.
  (c) Exact symbol/path lookup: chunks WHERE symbol/path LIKE identifier-shaped tokens.

Returns same result dict shape as lexical.py.
stdlib + sqlite3 only.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Identifier extraction from query
# ---------------------------------------------------------------------------

# Tokens that look like code identifiers, YAML keys, paths, or CXI rule IDs
_IDENT_RE = re.compile(
    r'`([^`]+)`'                          # backtick-quoted
    r'|([A-Z]{2,}-[A-Z0-9-]{1,})'        # CXI-R1, MSP-W2, etc.
    r'|([a-z][a-z0-9_]{2,})'             # snake_case tokens ≥3 chars
    r'|([A-Z][a-zA-Z0-9]{2,})'           # CamelCase tokens
    r'|([\w/]+\.(?:py|yml|yaml|md|json|jsonl|ts|tsx|sql|sh))' # path-shaped
)


def _extract_identifiers(query: str) -> list[str]:
    """Extract identifier-shaped tokens from query text."""
    tokens = []
    for m in _IDENT_RE.finditer(query):
        tok = next(g for g in m.groups() if g is not None)
        if tok and len(tok) >= 2:
            tokens.append(tok)
    return list(dict.fromkeys(tokens))  # dedupe, preserve order


# ---------------------------------------------------------------------------
# Term overlap scoring
# ---------------------------------------------------------------------------

def _term_overlap(query_tokens: set[str], text: str) -> int:
    """Count how many query tokens appear (case-insensitive) in text."""
    text_lower = text.lower()
    return sum(1 for t in query_tokens if t.lower() in text_lower)


# ---------------------------------------------------------------------------
# Governance path patterns (docs that contain registry/ruling chunks)
# ---------------------------------------------------------------------------

_KILL_REGISTRY_PATHS = {
    "research/DO_NOT_REBUILD.md",
}
_RULING_PATHS = {
    "config/ruling_graph.yml",
    "config/compiled_kill_registry.yml",
    "config/synapse.yml",
    "docs/ACTIVE_BUILD_MAP.md",
}
_GOV_PATHS = _KILL_REGISTRY_PATHS | _RULING_PATHS

# Path substrings that identify adjudication and masterplan documents.
# In adjudication mode (Strategy D), we boost these by term overlap so that
# collision-replay queries surface the relevant masterplan alongside registry rows.
_ADJUDICATION_PATH_SUBSTRINGS = (
    "_MASTERPLAN_BY_FABLE",
    "_ADJUDICATION_BY_FABLE",
    "_CODEX_ADJUDICATION",
    "_RATIFIED",
)


def _row_to_result(row: sqlite3.Row, project_key: str, rank: int, why: str) -> dict:
    return {
        "chunk_id": row["chunk_id"],
        "document_id": row["document_id"],
        "source_uri": row["source_uri"],
        "locator": row["locator"],
        "path": row["path"] or "",
        "authority_class": row["authority_class"] or "A1",
        "status": row["status"] or "active",
        "visibility": row["visibility"] or "shared",
        "project": project_key,
        "rank": rank,
        "raw_score": float(rank),
        "why": why,
        "heading_path": row["heading_path"] or "[]",
        "symbol": row["symbol"] or "",
    }


# ---------------------------------------------------------------------------
# Strategy A: kill-registry rows
# ---------------------------------------------------------------------------

def _search_kill_registry(
    conn: sqlite3.Connection,
    query: str,
    query_tokens: set[str],
    project_key: str,
) -> list[dict]:
    """Return all chunks from DO_NOT_REBUILD.md, ranked by term overlap."""
    rows = conn.execute(
        """
        SELECT c.chunk_id, c.document_id, c.locator, c.heading_path, c.symbol,
               d.source_uri, d.path, d.authority_class, d.visibility,
               c.text,
               CASE
                 WHEN c.symbol IN ('forbidden','killed','deferred','superseded','unknown','active')
                 THEN c.symbol
                 ELSE d.status
               END AS status
        FROM chunks c
        JOIN documents d ON d.document_id = c.document_id
        WHERE d.path IN ('research/DO_NOT_REBUILD.md')
          AND d.tombstoned = 0
        """,
    ).fetchall()

    scored = []
    for row in rows:
        score = _term_overlap(query_tokens, row["text"])
        scored.append((score, row))

    # Sort: higher overlap first
    scored.sort(key=lambda x: -x[0])
    results = []
    for rank, (score, row) in enumerate(scored):
        if score == 0:
            continue  # no relevance
        r = _row_to_result(row, project_key, rank + 1, "kill_registry")
        # Override status from chunk.symbol (registry_rows chunker encodes it there)
        sym = row["symbol"] or ""
        if sym in ("forbidden", "killed", "deferred", "superseded", "unknown"):
            r["status"] = sym
        results.append(r)
    return results


# ---------------------------------------------------------------------------
# Strategy B: ruling-graph / synapse.yml / active-build-map chunks
# ---------------------------------------------------------------------------

def _search_governance_docs(
    conn: sqlite3.Connection,
    query: str,
    query_tokens: set[str],
    project_key: str,
) -> list[dict]:
    """Search chunks from governance path documents by term overlap."""
    ruling_paths_sql = ",".join(f"'{p}'" for p in _RULING_PATHS)
    rows = conn.execute(
        f"""
        SELECT c.chunk_id, c.document_id, c.locator, c.heading_path, c.symbol,
               d.source_uri, d.path, d.authority_class, d.visibility, d.status,
               c.text
        FROM chunks c
        JOIN documents d ON d.document_id = c.document_id
        WHERE d.path IN ({ruling_paths_sql})
          AND d.tombstoned = 0
        """,
    ).fetchall()

    scored = []
    for row in rows:
        score = _term_overlap(query_tokens, row["text"])
        if score > 0:
            scored.append((score, row))

    scored.sort(key=lambda x: -x[0])
    results = []
    for rank, (_, row) in enumerate(scored):
        results.append(_row_to_result(row, project_key, rank + 1, "governance_doc"))
    return results


# ---------------------------------------------------------------------------
# Strategy C: exact symbol / path lookup
# ---------------------------------------------------------------------------

def _search_identifiers(
    conn: sqlite3.Connection,
    identifiers: list[str],
    project_key: str,
) -> list[dict]:
    """Look up chunks by symbol or path LIKE the identifier tokens."""
    if not identifiers:
        return []

    results: list[dict] = []
    seen: set[str] = set()
    rank = 1

    for tok in identifiers:
        like_pat = f"%{tok}%"
        rows = conn.execute(
            """
            SELECT c.chunk_id, c.document_id, c.locator, c.heading_path, c.symbol,
                   d.source_uri, d.path, d.authority_class, d.visibility, d.status,
                   c.text
            FROM chunks c
            JOIN documents d ON d.document_id = c.document_id
            WHERE (c.symbol LIKE ? OR d.path LIKE ?)
              AND d.tombstoned = 0
            LIMIT 20
            """,
            (like_pat, like_pat),
        ).fetchall()

        for row in rows:
            if row["chunk_id"] in seen:
                continue
            seen.add(row["chunk_id"])
            results.append(_row_to_result(row, project_key, rank, "exact_identifier"))
            rank += 1

    return results


# ---------------------------------------------------------------------------
# Strategy D: adjudication masterplan boost (adjudication mode only)
# ---------------------------------------------------------------------------


def _search_adjudication_docs(
    conn: sqlite3.Connection,
    query_tokens: set[str],
    project_key: str,
) -> list[dict]:
    """
    In adjudication mode, surface masterplan and adjudication docs by term overlap.

    Kill-registry Strategy A surfaces the registry verdict rows, but the collision
    check also needs the *masterplan* that covers the topic (the adjudication's
    required_sources include both DO_NOT_REBUILD and the relevant masterplan).

    Rule: fetch all chunks from documents whose path contains a masterplan/adjudication
    path substring, rank by query-token overlap, return top matches.
    This is deterministic and rule-level — no per-query hardcoding.
    """
    # Build a LIKE condition covering all adjudication path substrings
    like_clauses = " OR ".join(
        f"d.path LIKE ?" for _ in _ADJUDICATION_PATH_SUBSTRINGS
    )
    like_params = [f"%{s}%" for s in _ADJUDICATION_PATH_SUBSTRINGS]

    rows = conn.execute(
        f"""
        SELECT c.chunk_id, c.document_id, c.locator, c.heading_path, c.symbol,
               d.source_uri, d.path, d.authority_class, d.visibility, d.status,
               c.text
        FROM chunks c
        JOIN documents d ON d.document_id = c.document_id
        WHERE ({like_clauses})
          AND d.tombstoned = 0
        """,
        like_params,
    ).fetchall()

    scored = []
    for row in rows:
        score = _term_overlap(query_tokens, row["text"])
        if score > 0:
            scored.append((score, row))

    scored.sort(key=lambda x: -x[0])
    results = []
    for rank, (_, row) in enumerate(scored[:30]):  # cap to top-30 per query
        results.append(_row_to_result(row, project_key, rank + 1, "adjudication_doc"))
    return results


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


_GOVERNANCE_MODES = {"adjudication", "historical", "governance"}


def structured_search(
    query: str,
    db_dir: Path,
    project_db_map: dict[str, str],
    top_n: int = 50,
    mode: str = "research",
) -> list[dict]:
    """
    Run all three structured strategies across all in-scope project DBs.
    Returns merged results deduplicated by chunk_id, ranked by strategy priority.

    Kill-registry strategy (a) only runs in governance/adjudication/historical modes
    to prevent kill-registry noise from dominating non-governance queries.
    """
    query_tokens: set[str] = set(re.findall(r'\w+', query.lower()))
    identifiers = _extract_identifiers(query)
    is_governance = mode in _GOVERNANCE_MODES

    all_results: list[dict] = []
    seen_ids: set[str] = set()

    for project_key, db_file in project_db_map.items():
        db_path = db_dir / db_file
        if not db_path.exists():
            continue
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            # (a) kill registry — GOVERNANCE/ADJUDICATION MODES ONLY
            # In code/architecture/research/operations modes, kill-registry chunks
            # add noise (any shared common word triggers term_overlap>=1), burying
            # real answers. Only surface them when the query intent is governance.
            if is_governance:
                for r in _search_kill_registry(conn, query, query_tokens, project_key):
                    if r["chunk_id"] not in seen_ids:
                        seen_ids.add(r["chunk_id"])
                        all_results.append(r)

            # (b) governance docs (ruling_graph, synapse, active_build_map)
            for r in _search_governance_docs(conn, query, query_tokens, project_key):
                if r["chunk_id"] not in seen_ids:
                    seen_ids.add(r["chunk_id"])
                    all_results.append(r)

            # (c) identifiers
            for r in _search_identifiers(conn, identifiers, project_key):
                if r["chunk_id"] not in seen_ids:
                    seen_ids.add(r["chunk_id"])
                    all_results.append(r)

            # (d) adjudication masterplan boost — adjudication mode only.
            # Surfaces the relevant masterplan/adjudication doc alongside registry
            # rows for collision-replay queries (CTX-051..CTX-066 class).
            # Rule-level: any research/* path containing _MASTERPLAN_BY_FABLE or
            # _ADJUDICATION_BY_FABLE, ranked by term overlap with the query.
            if mode == "adjudication":
                for r in _search_adjudication_docs(conn, query_tokens, project_key):
                    if r["chunk_id"] not in seen_ids:
                        seen_ids.add(r["chunk_id"])
                        all_results.append(r)
        finally:
            conn.close()

    # Re-rank: kill registry first (governance modes), governance second,
    # adjudication_doc third (boost masterplans in adjudication mode),
    # identifier fourth
    priority = {
        "kill_registry": 0,
        "governance_doc": 1,
        "adjudication_doc": 2,
        "exact_identifier": 3,
    }
    all_results.sort(key=lambda r: (priority.get(r["why"], 9), r["rank"]))
    for i, r in enumerate(all_results):
        r["rank"] = i + 1

    return all_results[:top_n]
