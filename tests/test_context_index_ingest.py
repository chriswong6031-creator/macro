"""
CXI-1 ingestion tests.

All fixtures built in tmp_path — never touch the real repo's data/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine.context_index.ingest import run_ingest, _document_id, _chunk_id
from engine.context_index.sources import Config, SourceEntry, load_config
from engine.context_index.schema import open_db, get_meta, SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(roots_and_chunkers: list[tuple[str, str, str]]) -> Config:
    """
    roots_and_chunkers: list of (glob, chunker_name, source_type)
    Returns a Config with no extra deny patterns.
    """
    sources = [
        SourceEntry(
            id=f"src-{i}",
            roots=[r],
            authority_class="A3",
            visibility="shared",
            chunker=c,
            source_type=st,
        )
        for i, (r, c, st) in enumerate(roots_and_chunkers)
    ]
    return Config(sources=sources, deny=[])


def _mini_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a minimal fake repo with .git marker and given files."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return repo


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_deterministic_ids(tmp_path):
    """Two rebuilds produce identical document_id, chunk_id, content_hash sets."""
    repo = _mini_repo(tmp_path, {
        "docs/foo.md": "# Hello\n\nSome content here.\n",
        "docs/bar.md": "# Bar\n\nAnother doc.\n",
    })
    db_dir_1 = tmp_path / "db1"
    db_dir_2 = tmp_path / "db2"
    cfg = _make_config([("docs/**/*.md", "markdown_sections", "research")])

    run_ingest(repo, db_dir_1, cfg, rebuild=True, ingested_at="2026-01-01T00:00:00+00:00")
    run_ingest(repo, db_dir_2, cfg, rebuild=True, ingested_at="2026-01-02T00:00:00+00:00")

    conn1 = open_db(db_dir_1)
    conn2 = open_db(db_dir_2)

    docs1 = {r["document_id"]: r["content_hash"] for r in conn1.execute("SELECT document_id, content_hash FROM documents").fetchall()}
    docs2 = {r["document_id"]: r["content_hash"] for r in conn2.execute("SELECT document_id, content_hash FROM documents").fetchall()}
    assert docs1 == docs2, "document_ids or content_hashes differ between rebuilds"

    chunks1 = {r["chunk_id"]: r["content_hash"] for r in conn1.execute("SELECT chunk_id, content_hash FROM chunks").fetchall()}
    chunks2 = {r["chunk_id"]: r["content_hash"] for r in conn2.execute("SELECT chunk_id, content_hash FROM chunks").fetchall()}
    assert chunks1 == chunks2, "chunk_ids or content_hashes differ between rebuilds"


def test_ingested_at_differs_between_runs(tmp_path):
    """Only meta.built_at differs between two runs on same content."""
    repo = _mini_repo(tmp_path, {"docs/a.md": "# A\n\nContent.\n"})
    cfg = _make_config([("docs/**/*.md", "markdown_sections", "research")])
    db_dir = tmp_path / "db"

    run_ingest(repo, db_dir, cfg, rebuild=True, ingested_at="2026-01-01T00:00:00+00:00")
    conn = open_db(db_dir)
    built_at_1 = get_meta(conn, "built_at")
    conn.close()

    # Incremental run with different timestamp but same content
    run_ingest(repo, db_dir, cfg, rebuild=False, ingested_at="2026-01-02T00:00:00+00:00")
    conn = open_db(db_dir)
    built_at_2 = get_meta(conn, "built_at")
    conn.close()

    assert built_at_1 != built_at_2, "built_at should update between runs"


# ---------------------------------------------------------------------------
# Chunkers
# ---------------------------------------------------------------------------


def test_markdown_chunking_basic(tmp_path):
    repo = _mini_repo(tmp_path, {
        "docs/guide.md": "# Title\n\nIntro paragraph.\n\n## Section 1\n\nBody of section 1.\n\n## Section 2\n\nBody of section 2.\n"
    })
    cfg = _make_config([("docs/**/*.md", "markdown_sections", "research")])
    db_dir = tmp_path / "db"
    run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    chunks = conn.execute("SELECT locator, text FROM chunks ORDER BY ordinal").fetchall()
    conn.close()
    assert len(chunks) >= 2
    locators = [c["locator"] for c in chunks]
    assert any("section-1" in loc for loc in locators)
    assert any("section-2" in loc for loc in locators)


def test_markdown_chinese_headings(tmp_path):
    repo = _mini_repo(tmp_path, {
        "docs/zh.md": "# 简介\n\n中文内容在这里。\n\n## 第一节\n\n第一节内容。\n"
    })
    cfg = _make_config([("docs/**/*.md", "markdown_sections", "research")])
    db_dir = tmp_path / "db"
    run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()
    assert count >= 1  # No crash on Unicode headings


def test_python_symbols_chunking(tmp_path):
    py_content = '''\
"""Module docstring."""
import os
import sys


def foo():
    """Foo function."""
    pass


class Bar:
    """Bar class."""
    def method(self):
        pass
'''
    repo = _mini_repo(tmp_path, {"engine/mod.py": py_content})
    cfg = _make_config([("engine/**/*.py", "python_symbols", "code")])
    db_dir = tmp_path / "db"
    run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    symbols = [r["symbol"] for r in conn.execute("SELECT symbol FROM chunks").fetchall()]
    conn.close()
    assert "foo" in symbols
    assert "Bar" in symbols


def test_python_ast_fallback(tmp_path):
    """Syntax-error Python file must not crash ingestion."""
    repo = _mini_repo(tmp_path, {
        "engine/bad.py": "def foo(:\n    pass\n"  # syntax error
    })
    cfg = _make_config([("engine/**/*.py", "python_symbols", "code")])
    db_dir = tmp_path / "db"
    result = run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()
    assert count >= 1  # fallback produced at least one chunk


def test_yaml_keys_chunking(tmp_path):
    repo = _mini_repo(tmp_path, {
        "config/test.yml": "schema: test.v1\nsources:\n  - id: foo\n    roots: [docs/]\nprojects:\n  main:\n    description: main\n"
    })
    cfg = _make_config([("config/**/*.yml", "yaml_keys", "config")])
    db_dir = tmp_path / "db"
    run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()
    assert count >= 1


def test_whole_file_chunking(tmp_path):
    repo = _mini_repo(tmp_path, {
        "CLAUDE.md": "# CLAUDE\n\nThis is the constitution.\n"
    })
    cfg = _make_config([("CLAUDE.md", "whole_file", "config")])
    db_dir = tmp_path / "db"
    run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    assert count == 1
    row = conn.execute("SELECT locator FROM chunks").fetchone()
    assert "whole" in row["locator"]
    conn.close()


def test_registry_rows_status_derivation(tmp_path):
    """DO_NOT_REBUILD-style table rows get correct status derived.
    Section gate per CXI-R4/finding-11, ratified CXI-R17b: §1=forbidden,
    §2=killed, §3=unknown, §4=deferred — the section IS the status; verdict-cell
    keywords never override it. Regression cases: a §2 row quoting §1 vocabulary
    ("STRUCK — positioning-fusion illegal", the WA-R1/CTX-013 mislabel) must stay
    killed; a §1 row with killed-class-only vocabulary (REJECT-REDUNDANT) must
    stay forbidden.
    """
    dnr_content = """\
# DO NOT REBUILD

## 1. Forbidden by ruling

| Topic | Verdict |
|---|---|
| Auto wiki | FORBIDDEN by CXI-R12 |
| Standalone signal | ILLEGAL construction |
| Composite scorecard | REJECT-REDUNDANT duplicate of the radar chain |

## 2. Killed

| Topic | Verdict |
|---|---|
| Old approach | KILLED after test |
| Refuted model | REFUTED by data |
| Fused breakaway score | STRUCK — positioning-fusion illegal + Signal Commons R3 |

## 3. Methodology laws

| Topic | State |
|---|---|
| Some pattern | FORBIDDEN estimator (bad) |

## 4. Held / suspended

| Topic | Verdict |
|---|---|
| Future work | HOLD until W4 |
| Deferred pipeline | DEFER to W5 |

## 5. Notes

Some prose here.
"""
    repo = _mini_repo(tmp_path, {"research/DO_NOT_REBUILD.md": dnr_content})
    cfg = _make_config([("research/DO_NOT_REBUILD.md", "registry_rows", "ruling")])
    db_dir = tmp_path / "db"
    run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    rows = conn.execute("SELECT symbol, text FROM chunks WHERE symbol != ''").fetchall()
    symbols = [r["symbol"] for r in rows]
    conn.close()

    assert "forbidden" in symbols, f"expected 'forbidden' in {symbols}"
    assert "killed" in symbols, f"expected 'killed' in {symbols}"
    assert "deferred" in symbols, f"expected 'deferred' in {symbols}"
    by_topic = {r["text"]: r["symbol"] for r in rows}
    for text, symbol in by_topic.items():
        if "FORBIDDEN estimator" in text:
            # §3 rows must NOT derive 'forbidden' even though cell says FORBIDDEN
            assert symbol == "unknown", (
                f"§3 methodology row must derive 'unknown', got '{symbol}'"
            )
        if "Fused breakaway score" in text:
            # §2 row quoting §1 vocabulary must NOT flip to forbidden (CTX-013 class)
            assert symbol == "killed", (
                f"§2 STRUCK-illegal row must derive 'killed', got '{symbol}'"
            )
        if "Composite scorecard" in text:
            # §1 row with killed-class-only vocabulary must NOT flip to killed
            assert symbol == "forbidden", (
                f"§1 REJECT-REDUNDANT row must derive 'forbidden', got '{symbol}'"
            )


def test_registry_rows_3col_status_derivation(tmp_path):
    """
    Finding #9 (superseded by the CXI-R17b section gate): 3-column tables
    (Topic | Verdict | Ruling/source) must derive status from the row's SECTION,
    never from any cell's keywords — so ruling-column vocabulary can't leak in.
    Also validates §4 rows derive 'deferred' and §3 rows 'unknown' regardless
    of FORBIDDEN keyword.
    """
    dnr_content = """\
# DO NOT REBUILD

## 1. Forbidden by ruling

| Topic | Verdict | Ruling / source |
|---|---|---|
| Positioning fusion | ILLEGAL | Signal Commons rulings (2026-07-05) |
| Auto wiki | FORBIDDEN | CXI-R12 (2026-07-18) |

## 2. Killed topics

| Topic | Verdict | Ruling / source |
|---|---|---|
| Full-graph causal learners | KILLED for v1 | Some committee ruling |
| Refuted approach | REFUTED by data | Audit 2026 |

## 3. Methodology laws

| Topic | State | Notes |
|---|---|---|
| Some FORBIDDEN estimator | FORBIDDEN use | methodology note |

## 4. Held / suspended

| Topic | State | Ruling |
|---|---|---|
| Future lexical index | HOLD until CXI-2 | CXI-R11 |
| Deferred pipeline | DEFER to W4 | plan doc |
"""
    repo = _mini_repo(tmp_path, {"research/DO_NOT_REBUILD.md": dnr_content})
    cfg = _make_config([("research/DO_NOT_REBUILD.md", "registry_rows", "ruling")])
    db_dir = tmp_path / "db"
    run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    rows = conn.execute("SELECT symbol, text FROM chunks WHERE symbol != ''").fetchall()
    symbols = [r["symbol"] for r in rows]
    conn.close()

    assert "forbidden" in symbols, f"§1 ILLEGAL row should map to 'forbidden'; got {symbols}"
    assert "killed" in symbols, f"§2 KILLED row should map to 'killed'; got {symbols}"
    assert "deferred" in symbols, f"§4 HOLD row should map to 'deferred'; got {symbols}"
    # §3 methodology rows with FORBIDDEN keyword should be 'unknown', not 'forbidden'
    for r in rows:
        if "FORBIDDEN use" in r["text"] or "methodology" in r["text"].lower():
            assert r["symbol"] == "unknown", (
                f"§3 methodology row derived wrong status '{r['symbol']}': {r['text']}"
            )


def test_registry_rows_no_header_chunks(tmp_path):
    """
    Finding #12: header rows in registry tables must not produce spurious chunks.
    """
    dnr_content = """\
# DO NOT REBUILD

## 1. Forbidden

| Topic | Verdict | Ruling |
|---|---|---|
| Bad idea | ILLEGAL | some ruling |
"""
    repo = _mini_repo(tmp_path, {"research/DO_NOT_REBUILD.md": dnr_content})
    cfg = _make_config([("research/DO_NOT_REBUILD.md", "registry_rows", "ruling")])
    db_dir = tmp_path / "db"
    run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    table_row_chunks = conn.execute(
        "SELECT text FROM chunks WHERE text LIKE '%Topic%Verdict%'"
    ).fetchall()
    conn.close()
    assert len(table_row_chunks) == 0, (
        f"Header row emitted as chunk: {[r['text'] for r in table_row_chunks]}"
    )


def test_python_symbols_includes_decorators(tmp_path):
    """
    Finding #2: decorator lines must appear in the python_symbols chunk text.
    """
    py_content = '''\
"""Module."""
import functools


@functools.cache
def cached_fn():
    """Cached function."""
    return 42


class MyClass:
    @staticmethod
    def static_meth():
        pass
'''
    repo = _mini_repo(tmp_path, {"engine/dec.py": py_content})
    cfg = _make_config([("engine/**/*.py", "python_symbols", "code")])
    db_dir = tmp_path / "db"
    run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    chunks = conn.execute("SELECT symbol, text FROM chunks").fetchall()
    conn.close()

    cached_fn_chunk = next((c["text"] for c in chunks if c["symbol"] == "cached_fn"), None)
    assert cached_fn_chunk is not None, "cached_fn chunk not found"
    assert "@functools.cache" in cached_fn_chunk, (
        f"Decorator missing from chunk: {cached_fn_chunk[:200]}"
    )


def test_tombstone_then_readd_same_content(tmp_path):
    """
    Finding #1: tombstone-then-re-add with identical content must re-activate
    the document and restore its chunks (not silently leave it tombstoned).
    """
    repo = _repo = _mini_repo(tmp_path, {"docs/a.md": "# A\n\nContent.\n"})
    db_dir = tmp_path / "db"
    cfg = _make_config([("docs/**/*.md", "markdown_sections", "research")])

    # Initial ingest
    run_ingest(repo, db_dir, cfg, rebuild=True, ingested_at="T1")

    # Remove file → tombstoned
    (repo / "docs" / "a.md").unlink()
    run_ingest(repo, db_dir, cfg, rebuild=False, ingested_at="T2")

    conn = open_db(db_dir)
    tombstoned = conn.execute("SELECT COUNT(*) FROM documents WHERE tombstoned=1").fetchone()[0]
    conn.close()
    assert tombstoned == 1, "doc should be tombstoned after deletion"

    # Re-add with identical content → must be re-activated with chunks
    (repo / "docs" / "a.md").write_text("# A\n\nContent.\n", encoding="utf-8")
    run_ingest(repo, db_dir, cfg, rebuild=False, ingested_at="T3")

    conn = open_db(db_dir)
    active = conn.execute(
        "SELECT tombstoned FROM documents WHERE path='docs/a.md'"
    ).fetchone()
    chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()

    assert active is not None, "document row missing after re-add"
    assert active["tombstoned"] == 0, "re-added doc still tombstoned"
    assert chunk_count >= 1, "no chunks after re-adding tombstoned doc with same content"


def test_meta_schema_version_stored(tmp_path):
    repo = _mini_repo(tmp_path, {"docs/a.md": "# A\n\nContent.\n"})
    cfg = _make_config([("docs/**/*.md", "markdown_sections", "research")])
    db_dir = tmp_path / "db"
    run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    v = get_meta(conn, "schema_version")
    conn.close()
    assert v == str(SCHEMA_VERSION)


def test_fts_smoke_match(tmp_path):
    """After ingest, FTS MATCH on indexed text returns a result."""
    repo = _mini_repo(tmp_path, {
        "docs/signal.md": "# Signal Bus\n\nThe producer emits synthetic_flows artifact.\n"
    })
    cfg = _make_config([("docs/**/*.md", "markdown_sections", "research")])
    db_dir = tmp_path / "db"
    run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    hits = conn.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'synthetic_flows'"
    ).fetchall()
    conn.close()
    assert len(hits) >= 1, "FTS should find 'synthetic_flows' in indexed chunk"
