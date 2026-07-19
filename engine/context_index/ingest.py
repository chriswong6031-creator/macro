"""
CXI-1b ingestion orchestrator (multi-repo).

Per-project flow: discover → hash-diff → chunk → transactional write → tombstone → meta stamp.
Each project gets its own DB file (shared.sqlite / terminal.sqlite / mastermind.sqlite).

source_uri scheme:
  macro-dashboard: "repo://<relpath>"         (unchanged from CXI-1)
  external projects: "repo://<project-key>/<relpath>"

ABSOLUTE RULE: tests must use tmp_path; this code must never be called against
the real repo's data/ or site/ trees in tests.  The MM_DATA_GUARD tripwire
hard-fails CI on real-tree test writes.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .chunking import chunk
from .schema import (
    SCHEMA_VERSION,
    Chunk,
    Document,
    drop_and_recreate,
    get_meta,
    needs_rebuild,
    open_db,
    set_meta,
)
from .sources import Config, DiscoveredFile, MultiProjectConfig, ProjectConfig, discover_files

# ---------------------------------------------------------------------------
# Content tripwire patterns (matches → file skipped, never ingested)
# ---------------------------------------------------------------------------
_TRIPWIRE_PATTERNS: list[re.Pattern] = [
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    re.compile(r"AKIA[0-9A-Z]{16}"),                # AWS access key ID
    # Broadened value charset to include _ - . / (present in real tokens) and
    # common provider prefixes (ghp_/sk_live_/xox*/glpat-/AIza).
    # Whitespace is line-bounded ([ \t], never \s — \s crosses newlines, so
    # `api_key:` at end-of-line matched identifiers on following lines) and the
    # value must contain a digit within its first 39 chars so bare identifiers
    # (`access_token = _mm_supabase_access_token(request)`) don't trip.
    re.compile(
        r'(?:bearer|api[_\-]?key|token|password|secret[_\-]?key|'
        r'aws[_\-]secret[_\-]access[_\-]?key)'
        r'[ \t]*[=:][ \t]*["\']?(?=[A-Za-z+/_.~\-]{0,38}[0-9])[A-Za-z0-9+/_.~\-]{20,}',
        re.I,
    ),
    # Provider-prefix patterns that are self-identifying even without a key= prefix.
    # Digit lookahead: real tokens contain digits; prose mentioning the prefixes
    # (like this comment block) does not — prevents the scanner tripping itself.
    re.compile(r'\b(ghp_|gho_|ghs_|sk_live_|sk_test_|xox[baprs]-|glpat-|AIza)'
               r'(?=[A-Za-z+/_.~\-]{0,20}[0-9])[A-Za-z0-9+/_.~\-]{10,}'),
]


def _content_tripwire(content: str) -> bool:
    """Return True if content matches any credential pattern."""
    for pat in _TRIPWIRE_PATTERNS:
        if pat.search(content):
            return True
    return False


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------


def _sha256_str(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _document_id(source_uri: str) -> str:
    return hashlib.sha256(f"doc:{source_uri}".encode()).hexdigest()[:24]


def _chunk_id(document_id: str, locator: str) -> str:
    return hashlib.sha256(f"chunk:{document_id}:{locator}".encode()).hexdigest()[:24]


# ---------------------------------------------------------------------------
# source_uri scheme
# ---------------------------------------------------------------------------


def _make_source_uri(project_key: str, rel_path: str) -> str:
    """
    macro-dashboard: "repo://<relpath>"  (unchanged for backwards-compat)
    external projects: "repo://<project-key>/<relpath>"
    """
    if project_key == "macro-dashboard":
        return f"repo://{rel_path}"
    return f"repo://{project_key}/{rel_path}"


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git_rev_parse(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _git_commit_date(repo_root: Path) -> str:
    """
    Return the indexed commit's date (YYYY-MM-DD) via one git call per build.
    Used as source_as_of for all repo files, ensuring determinism across rebuilds.
    Falls back to empty string if git is unavailable.
    """
    try:
        result = subprocess.run(
            ["git", "show", "-s", "--format=%cs", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=10,
        )
        date = result.stdout.strip() if result.returncode == 0 else ""
        if date and re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            return date
        return ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Single-document ingest
# ---------------------------------------------------------------------------


def _ingest_document(
    conn: sqlite3.Connection,
    df: DiscoveredFile,
    git_sha: str,
    source_as_of: str,
    ingested_at: str,
) -> dict:
    """
    Ingest or update one document.  Returns a stats dict.
    All-or-nothing per document (atomic transaction per doc).
    """
    source_uri = _make_source_uri(df.project_key, df.rel_path)
    document_id = _document_id(source_uri)

    raw_bytes = df.abs_path.read_bytes()
    content_hash = _sha256_bytes(raw_bytes)

    stats = {"new": 0, "updated": 0, "skipped": 0, "tripwire": 0}

    # Content tripwire
    try:
        content_text = raw_bytes.decode("utf-8", errors="replace")
    except Exception:
        content_text = ""

    if _content_tripwire(content_text):
        stats["tripwire"] = 1
        return stats

    # Check if unchanged (active — not tombstoned)
    existing = conn.execute(
        "SELECT content_hash, tombstoned FROM documents WHERE document_id=?", (document_id,)
    ).fetchone()

    # Only skip when the row is active (tombstoned=0) AND content is identical.
    if existing and existing["content_hash"] == content_hash and existing["tombstoned"] == 0:
        stats["skipped"] = 1
        return stats

    is_update = existing is not None

    # Derive title from first line / heading
    title = _derive_title(content_text, df.rel_path)

    # project_ids: JSON list containing the project key
    project_ids = json.dumps([df.project_key])

    # Chunk
    draft_chunks = chunk(df.rel_path, content_text, df.chunker)

    # Build Chunk objects
    chunk_objs: list[Chunk] = []
    for ordinal, dc in enumerate(draft_chunks):
        cid = _chunk_id(document_id, dc.locator)
        chunk_objs.append(Chunk(
            chunk_id=cid,
            document_id=document_id,
            ordinal=ordinal,
            locator=dc.locator,
            text=dc.text,
            heading_path=json.dumps(dc.heading_path, ensure_ascii=False),
            symbol=dc.symbol or "",
            token_count=len(dc.text) // 4,
            content_hash=_sha256_str(dc.text),
        ))

    # Wire neighbor_before / neighbor_after
    for i, c in enumerate(chunk_objs):
        if i > 0:
            c.neighbor_before = chunk_objs[i - 1].chunk_id
        if i < len(chunk_objs) - 1:
            c.neighbor_after = chunk_objs[i + 1].chunk_id

    # Transactional write
    with conn:
        if is_update:
            conn.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
            conn.execute(
                """UPDATE documents SET
                    content_hash=?, git_sha=?, source_as_of=?, ingested_at=?,
                    title=?, tombstoned=0
                   WHERE document_id=?""",
                (content_hash, git_sha, source_as_of, ingested_at, title, document_id),
            )
        else:
            conn.execute(
                """INSERT INTO documents
                    (document_id, project_ids, source_type, source_uri, path,
                     title, authority_class, visibility, status, content_hash,
                     git_sha, source_as_of, ingested_at, tombstoned)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0)""",
                (
                    document_id, project_ids, df.source_type, source_uri, df.rel_path,
                    title, df.authority_class, df.visibility, "active",
                    content_hash, git_sha, source_as_of, ingested_at,
                ),
            )

        for c in chunk_objs:
            conn.execute(
                """INSERT INTO chunks
                    (chunk_id, document_id, ordinal, locator, heading_path,
                     symbol, text, token_count, content_hash,
                     neighbor_before, neighbor_after)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    c.chunk_id, c.document_id, c.ordinal, c.locator,
                    c.heading_path, c.symbol, c.text, c.token_count,
                    c.content_hash, c.neighbor_before, c.neighbor_after,
                ),
            )

    if is_update:
        stats["updated"] = 1
    else:
        stats["new"] = 1
    return stats


def _derive_title(content: str, rel_path: str) -> str:
    """Best-effort title: first ATX heading, else filename stem."""
    for line in content.splitlines():
        m = re.match(r"^#{1,3}\s+(.+)", line.strip())
        if m:
            return m.group(1).strip()
    return Path(rel_path).stem


# ---------------------------------------------------------------------------
# Tombstone
# ---------------------------------------------------------------------------


def _tombstone_missing(conn: sqlite3.Connection, seen_uris: set[str]) -> int:
    """Tombstone documents whose source_uri is no longer discovered."""
    existing_uris = {
        r["source_uri"]
        for r in conn.execute("SELECT source_uri FROM documents WHERE tombstoned=0").fetchall()
    }
    missing = existing_uris - seen_uris
    count = 0
    for uri in missing:
        doc_id = conn.execute(
            "SELECT document_id FROM documents WHERE source_uri=?", (uri,)
        ).fetchone()
        if doc_id:
            with conn:
                conn.execute("DELETE FROM chunks WHERE document_id=?", (doc_id["document_id"],))
                conn.execute(
                    "UPDATE documents SET tombstoned=1 WHERE source_uri=?", (uri,)
                )
            count += 1
    return count


# ---------------------------------------------------------------------------
# Per-project result
# ---------------------------------------------------------------------------


class ProjectIngestResult:
    def __init__(self, key: str) -> None:
        self.key = key
        self.new_docs = 0
        self.updated_docs = 0
        self.skipped_docs = 0
        self.tripwire_skips = 0
        self.denied_count = 0
        self.symlink_skips = 0
        self.tombstoned = 0
        self.total_chunks = 0
        self.rebuilt = False
        self.indexed_git_sha = ""


class IngestResult:
    """Aggregate result across all indexed projects."""
    def __init__(self) -> None:
        self.projects: dict[str, ProjectIngestResult] = {}
        self.absent_projects: list[str] = []

    # Legacy convenience properties (single-project callers)
    @property
    def new_docs(self) -> int:
        return sum(r.new_docs for r in self.projects.values())

    @property
    def updated_docs(self) -> int:
        return sum(r.updated_docs for r in self.projects.values())

    @property
    def skipped_docs(self) -> int:
        return sum(r.skipped_docs for r in self.projects.values())

    @property
    def tripwire_skips(self) -> int:
        return sum(r.tripwire_skips for r in self.projects.values())

    @property
    def denied_count(self) -> int:
        return sum(r.denied_count for r in self.projects.values())

    @property
    def symlink_skips(self) -> int:
        return sum(r.symlink_skips for r in self.projects.values())

    @property
    def tombstoned(self) -> int:
        return sum(r.tombstoned for r in self.projects.values())

    @property
    def total_chunks(self) -> int:
        return sum(r.total_chunks for r in self.projects.values())

    @property
    def rebuilt(self) -> bool:
        return any(r.rebuilt for r in self.projects.values())


# ---------------------------------------------------------------------------
# Per-project ingest
# ---------------------------------------------------------------------------


def _config_hash_for_project(project: ProjectConfig) -> str:
    """Stable hash of a single project's source + deny config."""
    data = json.dumps(
        {
            "key": project.key,
            "sources": [s._asdict() for s in project.sources],
            "deny": project.deny,
        },
        sort_keys=True,
    ).encode()
    return hashlib.sha256(data).hexdigest()


def run_ingest_project(
    project: ProjectConfig,
    db_dir: Path,
    rebuild: bool = False,
    ingested_at: Optional[str] = None,
) -> ProjectIngestResult:
    """
    Ingest one project into its own DB file.
    """
    result = ProjectIngestResult(project.key)

    config_hash = _config_hash_for_project(project)
    db_file = db_dir / project.db_file
    conn = open_db_file(db_file)

    if rebuild or needs_rebuild(conn, config_hash):
        drop_and_recreate(conn)
        result.rebuilt = True

    if ingested_at is None:
        ingested_at = datetime.now(timezone.utc).isoformat()

    git_sha = _git_rev_parse(project.root)
    result.indexed_git_sha = git_sha
    source_as_of = _git_commit_date(project.root) or ingested_at[:10]

    seen_uris: set[str] = set()

    for item, reason in discover_files(project, repo_root=None):
        if item is None:
            assert reason is not None
            if reason.startswith("symlink-escape"):
                result.symlink_skips += 1
            else:
                result.denied_count += 1
            continue

        source_uri = _make_source_uri(item.project_key, item.rel_path)
        seen_uris.add(source_uri)

        stats = _ingest_document(conn, item, git_sha, source_as_of, ingested_at)
        result.new_docs += stats["new"]
        result.updated_docs += stats["updated"]
        result.skipped_docs += stats["skipped"]
        result.tripwire_skips += stats["tripwire"]

    result.tombstoned = _tombstone_missing(conn, seen_uris)

    row = conn.execute("SELECT COUNT(*) as n FROM chunks").fetchone()
    result.total_chunks = row["n"] if row else 0

    with conn:
        set_meta(conn, "schema_version", str(SCHEMA_VERSION))
        set_meta(conn, "config_hash", config_hash)
        set_meta(conn, "indexed_git_sha", git_sha)
        set_meta(conn, "built_at", ingested_at)

    conn.close()
    return result


# ---------------------------------------------------------------------------
# open_db_file helper (opens a named file, not always shared.sqlite)
# ---------------------------------------------------------------------------


def open_db_file(db_path: Path) -> sqlite3.Connection:
    """Open (or create) a named SQLite DB file; apply DDL; return connection."""
    from .schema import _apply_ddl
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _apply_ddl(conn)
    return conn


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_ingest(
    repo_root: Path,
    db_dir: Path,
    config,  # MultiProjectConfig | Config (legacy single-project)
    rebuild: bool = False,
    ingested_at: Optional[str] = None,
    project_filter: Optional[str] = None,
) -> IngestResult:
    """
    Main ingestion function.

    Accepts MultiProjectConfig (v2) or legacy Config (v1 single-project, for existing tests).
    rebuild=True: drop and recreate each project's DB before ingesting.
    project_filter: if set, only ingest the named project key (v2 only).
    """
    result = IngestResult()

    if ingested_at is None:
        ingested_at = datetime.now(timezone.utc).isoformat()

    # --- v2 multi-project path ---
    if isinstance(config, MultiProjectConfig):
        result.absent_projects = list(config.absent_projects)
        for project in config.projects:
            if project_filter and project.key != project_filter:
                continue
            proj_result = run_ingest_project(
                project, db_dir, rebuild=rebuild, ingested_at=ingested_at
            )
            result.projects[project.key] = proj_result
        return result

    # --- v1 legacy path (Config with sources+deny; used by existing unit tests) ---
    legacy_result = _run_ingest_legacy(repo_root, db_dir, config, rebuild, ingested_at)
    result.projects["macro-dashboard"] = legacy_result
    return result


def _run_ingest_legacy(
    repo_root: Path,
    db_dir: Path,
    config: "Config",
    rebuild: bool,
    ingested_at: str,
) -> ProjectIngestResult:
    """Legacy single-project ingest (Config with sources+deny)."""
    from .schema import open_db, needs_rebuild, drop_and_recreate, set_meta, SCHEMA_VERSION

    result = ProjectIngestResult("macro-dashboard")

    config_bytes = json.dumps(
        {"sources": [s._asdict() for s in config.sources], "deny": config.deny},
        sort_keys=True,
    ).encode()
    config_hash = _sha256_bytes(config_bytes)

    conn = open_db(db_dir)

    if rebuild or needs_rebuild(conn, config_hash):
        drop_and_recreate(conn)
        result.rebuilt = True

    git_sha = _git_rev_parse(repo_root)
    result.indexed_git_sha = git_sha
    source_as_of = _git_commit_date(repo_root) or ingested_at[:10]

    seen_uris: set[str] = set()

    for item, reason in discover_files(config, repo_root=repo_root):
        if item is None:
            assert reason is not None
            if reason.startswith("symlink-escape"):
                result.symlink_skips += 1
            else:
                result.denied_count += 1
            continue

        source_uri = _make_source_uri(item.project_key, item.rel_path)
        seen_uris.add(source_uri)

        stats = _ingest_document(conn, item, git_sha, source_as_of, ingested_at)
        result.new_docs += stats["new"]
        result.updated_docs += stats["updated"]
        result.skipped_docs += stats["skipped"]
        result.tripwire_skips += stats["tripwire"]

    result.tombstoned = _tombstone_missing(conn, seen_uris)

    row = conn.execute("SELECT COUNT(*) as n FROM chunks").fetchone()
    result.total_chunks = row["n"] if row else 0

    with conn:
        set_meta(conn, "schema_version", str(SCHEMA_VERSION))
        set_meta(conn, "config_hash", config_hash)
        set_meta(conn, "indexed_git_sha", git_sha)
        set_meta(conn, "built_at", ingested_at)

    conn.close()
    return result
