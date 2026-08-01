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

Schema v2 adds the engine-MEASURED columns from :mod:`research_vault.probe`
(page count, text-layer density, content hash, PDF provenance, page-1 text).
They are metadata only — deliberately NOT added to the FTS table: ``first_page_text``
is a prefix of ``body``, so indexing it would double-count those postings and
silently reweight every BM25 score.

The bottom of this module holds the PROCESS-WIDE read-through cache
(:func:`corpus_connection`) and the by-id reader (:func:`get_document`) that both
``app/research.py`` and the Mastermind brain read through — see the block comment
above them for why the cache lives here rather than in the router.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

log = logging.getLogger("research_vault.corpus")

# ---------------------------------------------------------------------------
# DDL — contentless FTS5 + sync triggers (copied idiom: context_index/schema.py)
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 2

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

# Engine-measured columns (schema v2), declared EXACTLY ONCE and applied by
# ALTER TABLE in :func:`_migrate` on every open — never inline in the CREATE
# TABLE above.
#
# Why migration-only rather than "new columns in the DDL plus a migration for old
# files": ``CREATE TABLE IF NOT EXISTS`` is a no-op against the v1 corpus that
# :func:`ingest._restore_corpus` pulls from R2 at the start of every run, so the
# DDL alone would leave the live database on v1 while the INSERT below named v2
# columns — an OperationalError inside ``_ingest_one``'s catch-all, i.e. every
# document silently marked "failed". Declaring them in one place, applied through
# one idempotent path, removes that whole failure mode.
_V2_COLUMNS: tuple[tuple[str, str], ...] = (
    ("pages", "INTEGER"),
    ("language", "TEXT"),
    ("char_count", "INTEGER"),
    ("word_count", "INTEGER"),
    ("text_layer", "TEXT"),
    ("content_sha256", "TEXT"),
    ("byte_size", "INTEGER"),
    ("pdf_creator", "TEXT"),
    ("pdf_producer", "TEXT"),
    ("pdf_created_at", "TEXT"),
    ("pdf_modified_at", "TEXT"),
)

# Deliberately NOT a column: ``first_page_text``. ``body`` is truncated at the
# TAIL (BODY_MAX_CHARS), so page 1 is always inside the row we already store —
# downstream extractors read it via :func:`research_vault.probe.first_page` over
# ``body`` instead. A separate column would duplicate ~4KB per row in a file the
# API pulls whole on every corpus refresh.

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

def _existing_columns(conn: sqlite3.Connection, table: str = "documents") -> set[str]:
    """Column names currently on ``table`` ({} when the table is absent)."""
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.Error:
        return set()


def _migrate(conn: sqlite3.Connection) -> list[str]:
    """Add any missing :data:`_V2_COLUMNS` to ``documents``. Idempotent.

    Runs on EVERY open, so a fresh database and a v1 corpus restored from R2 both
    converge on the same shape. Returns the column names actually added (empty on
    an already-current database). A single failed ALTER is logged and skipped
    rather than raised: a corpus that is merely missing an enrichment column must
    still ingest and still serve search.
    """
    have = _existing_columns(conn)
    if not have:  # no documents table (should not happen — DDL ran first)
        return []
    added: list[str] = []
    for name, decl in _V2_COLUMNS:
        if name in have:
            continue
        try:
            conn.execute(f"ALTER TABLE documents ADD COLUMN {name} {decl}")
            added.append(name)
        except sqlite3.Error as exc:
            log.warning("research_vault corpus: ALTER for %s failed (%s)", name, exc)
    if "content_sha256" in have or "content_sha256" in added:
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rv_docs_sha "
                         "ON documents(content_sha256)")
        except sqlite3.Error as exc:
            log.warning("research_vault corpus: sha index failed (%s)", exc)
    if added:
        conn.commit()
        log.info("research_vault corpus: migrated to v%d (+%d columns)",
                 SCHEMA_VERSION, len(added))
    return added


def open_db(path: str | Path) -> sqlite3.Connection:
    """Open (or create) corpus.sqlite, apply DDL + migrations, stamp the version."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    _migrate(conn)
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

def summary_text(item: dict) -> str:
    """The ``summary`` FTS column value for a catalog/sidecar item.

    Defined once because TWO paths write it: :func:`upsert` at ingest, and
    ``ingest._refresh_sidecars`` when a late-arriving sidecar summary is folded
    into a row that was already published. A separate join in either place would
    let the two drift into different searchable text for the same bullets.
    """
    return " • ".join(item.get("summary_points") or [])


def upsert(conn: sqlite3.Connection, item: dict, body_text: str,
           facts: dict | None = None) -> None:
    """Insert/replace one document's searchable row.

    ``item`` is a normalized sidecar item (see sidecar.normalize). ``body_text``
    is the pdftotext-extracted body ('' when extraction failed — the row is still
    searchable by title/summary). ``facts`` is the optional engine-measured bundle
    (:func:`research_vault.probe.probe` + :func:`~research_vault.probe.text_facts`
    + ``first_page_text``); absent → the v2 columns stay NULL, which is the honest
    "not measured" state.

    Delete-then-insert keeps the FTS postings in sync via the triggers (a bare
    REPLACE would not fire the delete trigger for the old body). The column list
    is built from the columns the database ACTUALLY has, so a corpus whose
    migration partially failed still ingests every document instead of raising
    per row. Never raises on a benign duplicate.
    """
    doc_id = item.get("id") or ""
    published_at = item.get("published_at") or ""

    row: dict = {
        "doc_id": doc_id,
        "title": item.get("title") or "",
        "summary": summary_text(item),
        "institution": item.get("institution") or "",
        "side": item.get("side") or "",
        "published_at": published_at,
        "published_date": published_at[:10] if len(published_at) >= 10 else "",
        "body": (body_text or "")[:BODY_MAX_CHARS],
    }

    if facts:
        for name, _decl in _V2_COLUMNS:
            if name in facts:
                row[name] = facts[name]
        # ``language`` and ``pages`` live on the normalized item, not the probe.
        row.setdefault("language", item.get("language") or "")
        row.setdefault("pages", item.get("pages"))

    have = _existing_columns(conn)
    cols = [c for c in row if c in have] if have else list(row)
    placeholders = ",".join("?" for _ in cols)

    conn.execute("DELETE FROM documents WHERE doc_id=?", (doc_id,))
    conn.execute(
        f"INSERT INTO documents ({','.join(cols)}) VALUES ({placeholders})",
        [row[c] for c in cols],
    )
    conn.commit()


def sha_index(conn: sqlite3.Connection) -> dict[str, str]:
    """``{content_sha256: doc_id}`` for every hashed document. Never raises.

    Used to REPORT byte-identical duplicates at ingest. Deliberately not used to
    skip them: the same PDF legitimately re-arrives with a corrected sidecar, and
    skipping on a hash match would freeze the original bad metadata in place.
    Returns {} on a pre-v2 corpus where the column does not exist.
    """
    if "content_sha256" not in _existing_columns(conn):
        return {}
    try:
        rows = conn.execute(
            "SELECT content_sha256, doc_id FROM documents "
            "WHERE content_sha256 IS NOT NULL AND content_sha256 <> ''"
        ).fetchall()
    except sqlite3.Error:
        return {}
    return {r[0]: r[1] for r in rows}


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


# ---------------------------------------------------------------------------
# read-through cache + by-id reader — ONE local copy per process (W4)
# ---------------------------------------------------------------------------
# The corpus lives ONLY in R2. Until W4 the single fetcher was
# ``app/research.py::_corpus_conn``; the Mastermind brain's Pro full-report answer
# needs the same bytes and runs in the SAME FastAPI process (app/main.py imports
# brain_gateway lazily in the request path), so a second private cache there would
# mean two multi-MB downloads, two TTL clocks, and two writers racing over the one
# temp file. The machinery therefore lives here and the router delegates.
#
# ENGINE-SIDE ONLY: this module must never import ``app/*``. The store comes from
# ``research_vault.r2_store.build_store`` (the same env precedence the router used)
# or from a caller-supplied factory — the router passes its own, which is what its
# tests monkeypatch.
#
# Serve-stale-while-revalidate, unchanged from the router's original: a present
# local copy is served immediately; past the TTL exactly one background thread
# re-downloads it; only the very first call on a cold process blocks.

CORPUS_KEY = "research_vault/corpus.sqlite"   # mirrors ingest CORPUS_KEY
CORPUS_TTL = 300.0                            # seconds — local copy refresh age
CORPUS_LOCK = threading.Lock()                # guards the three globals below
_CACHE_DIRNAME = "research_vault_corpus"

_corpus_path: Path | None = None
_corpus_fetched_at: float = 0.0
_corpus_refreshing: bool = False  # guarded by CORPUS_LOCK — one refresher at a time

# The slug shape ``sidecar.slug`` produces, copied from app/research._DOC_ID_RE
# INCLUDING its anchors: ``\A``/``\Z``, never ``^``/``$`` — a ``$`` also matches
# just before a trailing newline, so "valid-id\n" would clear a ``$``-anchored
# check. Any id failing this never reaches a SQL parameter or an R2 key.
_DOC_ID_RE = re.compile(r"\A[a-z0-9][a-z0-9-]{0,120}\Z")

# The EXACT key set :func:`get_document` returns. Literal, like every other
# projection in this repo: a column added to ``documents`` later (the v2 probe
# bundle, say) cannot reach a caller — or a chat context — without someone editing
# this tuple and tripping tests/test_research_vault.py.
DOCUMENT_FIELDS: tuple[str, ...] = (
    "doc_id", "title", "institution", "side", "published_at", "summary", "body",
)


def valid_doc_id(doc_id) -> bool:
    """True iff ``doc_id`` has the catalog slug shape (shape only, not existence).

    Existence is the CALLER's gate — the router checks the catalog, the brain
    checks the catalog. This is the cheap shape check that keeps traversal,
    uppercase, slashes and trailing newlines out of the query in the first place.
    """
    return isinstance(doc_id, str) and bool(_DOC_ID_RE.match(doc_id))


def _cache_dir() -> Path:
    """Directory holding the local corpus copy (a function so tests can repoint it)."""
    return Path(tempfile.gettempdir()) / _CACHE_DIRNAME


def _default_store():
    """The private research bucket via r2_store.build_store, or None. Never raises.

    Imported lazily so this module keeps importing (and every pure-sqlite function
    keeps working) on a box with no boto3.
    """
    try:
        from engine.research_vault.r2_store import build_store  # noqa: PLC0415
        return build_store()
    except Exception as exc:  # noqa: BLE001 — no store → no corpus, never a raise
        log.debug("research_vault: store unavailable (%s)", exc)
        return None


def _resolve_store(store_factory):
    """Call the caller's factory (or the default) and swallow its failures."""
    try:
        return (store_factory or _default_store)()
    except Exception as exc:  # noqa: BLE001
        log.debug("research_vault: store factory failed (%s)", exc)
        return None


def _refresh_from_store(store_factory=None) -> Path | None:
    """Download corpus.sqlite to the local cache path (SYNCHRONOUS). Never raises.

    Returns the local path on success, None on any failure. Called inline only
    when no local copy exists yet; otherwise it runs on a background thread so a
    user's search never pays the multi-MB download (the corpus grows with the
    archive — a backfilled corpus is far too large to fetch inside a request).

    The store read is inside the try, unlike the router's original: a boto3
    exception used to propagate out of the route (a 500), which contradicts
    app/research.py's own never-raise-at-the-boundary invariant.
    """
    global _corpus_path, _corpus_fetched_at
    store = _resolve_store(store_factory)
    if store is None:
        return None
    try:
        data = store.get_bytes(CORPUS_KEY)
    except Exception as exc:  # noqa: BLE001 — a dead bucket degrades to no corpus
        log.debug("research_vault: corpus fetch failed (%s)", exc)
        return None
    if not data:
        return None
    try:
        tmp_dir = _cache_dir()
        tmp_dir.mkdir(parents=True, exist_ok=True)
        dst = tmp_dir / "corpus.sqlite"
        tmp = dst.with_suffix(".sqlite.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, dst)
        with CORPUS_LOCK:
            _corpus_path = dst
            _corpus_fetched_at = time.monotonic()
        return dst
    except Exception as exc:  # noqa: BLE001 — write failure → degrade
        log.debug("research_vault: corpus refresh failed (%s)", exc)
        return None


def _refresh_bg(store_factory=None) -> None:
    """Background-thread wrapper: refresh, then clear the in-flight flag."""
    global _corpus_refreshing
    try:
        _refresh_from_store(store_factory)
    finally:
        with CORPUS_LOCK:
            _corpus_refreshing = False


def corpus_connection(store_factory=None):
    """Open the shared local corpus copy, refreshing it WITHOUT blocking the caller.

    Returns a sqlite3 connection (caller closes it) or None. Never raises. A
    present local copy is served immediately; when it is older than
    :data:`CORPUS_TTL` a single background thread re-downloads it (dropped, not
    queued, if one is already in flight). Only the very first call on a cold
    process — no local copy at all — downloads inline.
    """
    global _corpus_refreshing
    now = time.monotonic()

    with CORPUS_LOCK:
        have_local = _corpus_path is not None and _corpus_path.exists()
        stale = not have_local or (now - _corpus_fetched_at) >= CORPUS_TTL
        path = _corpus_path
        if have_local and stale and not _corpus_refreshing:
            _corpus_refreshing = True
            threading.Thread(target=_refresh_bg, args=(store_factory,), daemon=True,
                             name="rv-corpus-refresh").start()

    if not have_local:
        # First fetch ever on this process: nothing to serve yet — block once.
        path = _refresh_from_store(store_factory)
        if path is None:
            return None

    try:
        return open_db(path)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001 — unreadable local copy → degrade
        log.debug("research_vault: corpus open failed (%s)", exc)
        return None


def reset_cache() -> None:
    """Forget the local copy (tests only — production never calls this).

    The cache is process-wide by design, so a test that seeds its own store must
    be able to drop a copy a previous test fetched; otherwise the first fetch of
    the session would decide what every later test reads.
    """
    global _corpus_path, _corpus_fetched_at, _corpus_refreshing
    with CORPUS_LOCK:
        _corpus_path = None
        _corpus_fetched_at = 0.0
        _corpus_refreshing = False


def get_document(doc_id: str, store_factory=None) -> dict | None:
    """One document's stored row by id, or None. Never raises.

    ``{doc_id, title, institution, side, published_at, summary, body}`` —
    :data:`DOCUMENT_FIELDS`, built literally. ``body`` is the pdftotext extraction
    capped at :data:`BODY_MAX_CHARS` when it was ingested; slicing it further for a
    given surface is that surface's decision, not this reader's.

    None covers every degraded case on purpose — malformed id, no store, corpus
    unreachable, unknown id, sqlite trouble — because every caller treats them the
    same: fall back to the public material and say so.
    """
    if not valid_doc_id(doc_id):
        return None
    try:
        conn = corpus_connection(store_factory=store_factory)
    except Exception as exc:  # noqa: BLE001 — belt; corpus_connection degrades already
        log.debug("research_vault: corpus connection failed (%s)", exc)
        return None
    if conn is None:
        return None

    try:
        row = conn.execute(
            "SELECT doc_id, title, institution, side, published_at, summary, body "
            "FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
    except Exception as exc:  # noqa: BLE001 — corrupt/partial copy → no document
        log.debug("research_vault: document read failed (%s)", exc)
        return None
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    if row is None:
        return None
    return {
        "doc_id": row["doc_id"] or "",
        "title": row["title"] or "",
        "institution": row["institution"] or "",
        "side": row["side"] or "",
        "published_at": row["published_at"] or "",
        "summary": row["summary"] or "",
        "body": row["body"] or "",
    }
