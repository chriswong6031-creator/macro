"""
CXI-1b multi-repo tests.

Covers:
- Two fake fixture repos (with .git dirs) + one absent project → absent skipped+counted
- Per-project DB files created separately
- External docs stamped visibility=private + correct project_ids
- macro-dashboard project unaffected when external repos are absent
- code_blocks chunker: TS export boundaries, SQL CREATE TABLE split, no-boundary fallback,
  stable block ordinals on append-only edit
- Tripwire applies to external files (fake credential in content)
- Deny of data/** inside mastermind fixture
- source_uri scheme: external = "repo://<key>/<relpath>", macro = "repo://<relpath>"

RULE: all writes go to tmp_path — never data/, site/, or .context-index/.
Token-shaped literals are assembled from fragments at runtime (GitHub push protection).
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Generator

import pytest
import yaml

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_init(path: Path) -> None:
    """Create a minimal .git directory so _resolve_root sees a valid git repo."""
    git_dir = path / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
    # Enough for subprocess git rev-parse HEAD to return something sensible.
    # We don't run git commit, so rev-parse will fail gracefully (empty string).


def _write_file(base: Path, rel: str, content: str) -> Path:
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Fake repo fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def terminal_repo(tmp_path: Path) -> Path:
    """Fake terminal repo with a minimal set of files."""
    root = tmp_path / "charting-app"
    root.mkdir()
    _git_init(root)

    _write_file(root, "README.md", "# Terminal\nA charting app.\n")
    _write_file(root, "HANDOFF.md", "# Handoff\nSome handoff notes.\n")
    _write_file(root, "docs/overview.md", "# Overview\nDetails here.\n")
    _write_file(root, "contracts/indicator.json",
                '{"schema": "mastermind.indicator/v1", "version": 1}')
    _write_file(root, "supabase/migrations/001_init.sql",
                "CREATE TABLE signals (id SERIAL PRIMARY KEY, name TEXT);\n"
                "CREATE INDEX idx_signals_name ON signals(name);\n")
    _write_file(root, "ingest/loader.py",
                "def load_data(path):\n    return []\n")
    _write_file(root, "terminal/lib/utils.ts",
                "export function formatPrice(p: number): string { return p.toFixed(2); }\n"
                "export const DEFAULT_TIMEOUT = 5000;\n")
    _write_file(root, "tests/test_loader.py",
                "def test_load():\n    assert True\n")
    # Denied file — should never appear in index
    _write_file(root, "terminal/public/data/prices.json", '{"p": 100}')
    return root


@pytest.fixture()
def mastermind_repo(tmp_path: Path) -> Path:
    """Fake mastermind repo with constitution stack + data/** that must be denied."""
    root = tmp_path / "Mastermind"
    root.mkdir()
    _git_init(root)

    _write_file(root, "CLAUDE.md", "# Mastermind Constitution\nCore law.\n")
    _write_file(root, "AGENTS.md", "# Agents\nAgent definitions.\n")
    _write_file(root, "brain/strategy.py",
                "class Strategy:\n    def run(self): pass\n")
    _write_file(root, "sql/schema.sql",
                "CREATE TABLE portfolio (id SERIAL PRIMARY KEY);\n")
    # data/** is wholesale-denied
    _write_file(root, "data/positions.json", '{"pos": []}')
    _write_file(root, "data/decisions.parquet", "binary_placeholder")
    return root


# ---------------------------------------------------------------------------
# Config builder helpers
# ---------------------------------------------------------------------------


def _make_v2_config(
    macro_root: Path,
    terminal_root: Path | None,
    mastermind_root: Path | None,
) -> dict:
    """Build a minimal v2 config dict for testing."""
    projects: dict = {}

    projects["macro-dashboard"] = {
        "root": ".",
        "visibility": "shared",
        "db": "shared.sqlite",
        "sources": [
            {
                "id": "md-constitution",
                "roots": ["CLAUDE.md"],
                "authority_class": "A0",
                "visibility": "shared",
                "chunker": "whole_file",
                "source_type": "config",
            }
        ],
        "deny": ["site/**", "data/**", ".git/**"],
    }

    if terminal_root is not None:
        projects["terminal"] = {
            "root": str(terminal_root),
            "visibility": "private",
            "db": "terminal.sqlite",
            "sources": [
                {
                    "id": "term-docs",
                    "roots": ["README.md", "HANDOFF.md", "docs/**/*.md"],
                    "authority_class": "A3",
                    "visibility": "private",
                    "chunker": "markdown_sections",
                    "source_type": "research",
                },
                {
                    "id": "term-sql",
                    "roots": ["supabase/migrations/*.sql"],
                    "authority_class": "A1",
                    "visibility": "private",
                    "chunker": "code_blocks",
                    "source_type": "config",
                },
                {
                    "id": "term-ts",
                    "roots": ["terminal/lib/**/*.ts"],
                    "authority_class": "A2",
                    "visibility": "private",
                    "chunker": "code_blocks",
                    "source_type": "code",
                },
                {
                    "id": "term-py",
                    "roots": ["ingest/**/*.py", "tests/**/*.py"],
                    "authority_class": "A2",
                    "visibility": "private",
                    "chunker": "python_symbols",
                    "source_type": "code",
                },
            ],
            "deny": ["terminal/public/data/**", ".git/**", "**/__pycache__/**"],
        }

    if mastermind_root is not None:
        projects["mastermind"] = {
            "root": str(mastermind_root),
            "visibility": "private",
            "db": "mastermind.sqlite",
            "sources": [
                {
                    "id": "mm-constitution",
                    "roots": ["CLAUDE.md", "AGENTS.md"],
                    "authority_class": "A0",
                    "visibility": "private",
                    "chunker": "markdown_sections",
                    "source_type": "config",
                },
                {
                    "id": "mm-sql",
                    "roots": ["sql/*.sql"],
                    "authority_class": "A1",
                    "visibility": "private",
                    "chunker": "code_blocks",
                    "source_type": "config",
                },
                {
                    "id": "mm-brain",
                    "roots": ["brain/**/*.py"],
                    "authority_class": "A2",
                    "visibility": "private",
                    "chunker": "python_symbols",
                    "source_type": "code",
                },
            ],
            "deny": ["data/**", "vendor/**", ".git/**", "**/*.parquet"],
        }

    return {
        "schema": "macro_context_index.config.v2",
        "projects": projects,
    }


def _write_config(cfg_dir: Path, cfg_dict: dict) -> Path:
    """Write a v2 config YAML to cfg_dir/context_index.yml and return the path."""
    p = cfg_dir / "context_index.yml"
    p.write_text(yaml.dump(cfg_dict, allow_unicode=True), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Import helpers (always use absolute import to avoid path issues)
# ---------------------------------------------------------------------------


def _load_sources():
    import sys
    repo_root = Path(__file__).parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from engine.context_index.sources import load_config, discover_files
    return load_config, discover_files


def _load_ingest():
    import sys
    repo_root = Path(__file__).parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from engine.context_index.ingest import run_ingest
    return run_ingest


def _load_health():
    import sys
    repo_root = Path(__file__).parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from engine.context_index.health import build_health_report
    return build_health_report


def _load_chunking():
    import sys
    repo_root = Path(__file__).parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from engine.context_index.chunking import code_blocks
    return code_blocks


# ---------------------------------------------------------------------------
# Macro-dashboard fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def macro_root(tmp_path: Path) -> Path:
    root = tmp_path / "macro-dashboard"
    root.mkdir()
    _git_init(root)
    # Minimal CLAUDE.md so the source has something to index
    _write_file(root, "CLAUDE.md", "# Macro Dashboard\nConstitutional rules.\n")
    return root


# ---------------------------------------------------------------------------
# Tests: absent project handling
# ---------------------------------------------------------------------------


class TestAbsentProject:
    def test_absent_project_skipped_not_fatal(self, tmp_path: Path, macro_root: Path) -> None:
        """An absent external repo root must be counted in absent_projects, not raise."""
        load_config, _ = _load_sources()
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir()

        absent_path = tmp_path / "nonexistent-repo"  # does NOT exist
        cfg = _make_v2_config(macro_root, terminal_root=None, mastermind_root=None)
        cfg["projects"]["terminal"] = {
            "root": str(absent_path),
            "visibility": "private",
            "db": "terminal.sqlite",
            "sources": [],
            "deny": [],
        }
        config_path = _write_config(cfg_dir, cfg)
        # Patch the macro-dashboard root to be resolvable
        cfg["projects"]["macro-dashboard"]["root"] = str(macro_root)
        config_path.write_text(yaml.dump(cfg, allow_unicode=True), encoding="utf-8")

        config = load_config(config_path)
        assert "terminal" in config.absent_projects
        assert len(config.projects) == 1  # only macro-dashboard
        assert config.projects[0].key == "macro-dashboard"

    def test_absent_project_absent_list_keys_only(self, tmp_path: Path, macro_root: Path) -> None:
        """absent_projects must only contain project KEYS, no paths."""
        load_config, _ = _load_sources()
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir()

        absent_path = tmp_path / "no-such-repo"
        cfg = _make_v2_config(macro_root, terminal_root=None, mastermind_root=None)
        cfg["projects"]["mastermind"] = {
            "root": str(absent_path),
            "visibility": "private",
            "db": "mastermind.sqlite",
            "sources": [],
            "deny": [],
        }
        cfg["projects"]["macro-dashboard"]["root"] = str(macro_root)
        config_path = _write_config(cfg_dir, cfg)

        config = load_config(config_path)
        assert "mastermind" in config.absent_projects
        # The absent_projects list must not contain any path strings
        for entry in config.absent_projects:
            assert "/" not in entry and "\\" not in entry, (
                f"absent_projects must contain keys only, got: {entry!r}"
            )

    def test_macro_unaffected_when_external_absent(
        self, tmp_path: Path, macro_root: Path
    ) -> None:
        """macro-dashboard must index normally even when both external repos are absent."""
        load_config, _ = _load_sources()
        run_ingest = _load_ingest()

        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir()
        cfg = _make_v2_config(macro_root, terminal_root=None, mastermind_root=None)
        cfg["projects"]["terminal"] = {
            "root": str(tmp_path / "no-terminal"),
            "visibility": "private",
            "db": "terminal.sqlite",
            "sources": [],
            "deny": [],
        }
        cfg["projects"]["macro-dashboard"]["root"] = str(macro_root)
        config_path = _write_config(cfg_dir, cfg)

        db_dir = tmp_path / "index"
        config = load_config(config_path)
        result = run_ingest(macro_root, db_dir, config, rebuild=True)

        assert "macro-dashboard" in result.projects
        assert result.projects["macro-dashboard"].total_chunks > 0
        assert "terminal" not in result.projects
        assert "terminal" in result.absent_projects
        # Only shared.sqlite created — no terminal.sqlite
        assert (db_dir / "shared.sqlite").exists()
        assert not (db_dir / "terminal.sqlite").exists()


# ---------------------------------------------------------------------------
# Tests: per-project DB files
# ---------------------------------------------------------------------------


class TestPerProjectDB:
    def test_separate_db_files_created(
        self, tmp_path: Path, macro_root: Path, terminal_repo: Path, mastermind_repo: Path
    ) -> None:
        """Each present project gets its own DB file."""
        load_config, _ = _load_sources()
        run_ingest = _load_ingest()

        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir()
        cfg = _make_v2_config(macro_root, terminal_repo, mastermind_repo)
        cfg["projects"]["macro-dashboard"]["root"] = str(macro_root)
        config_path = _write_config(cfg_dir, cfg)

        db_dir = tmp_path / "index"
        config = load_config(config_path)
        run_ingest(macro_root, db_dir, config, rebuild=True)

        assert (db_dir / "shared.sqlite").exists()
        assert (db_dir / "terminal.sqlite").exists()
        assert (db_dir / "mastermind.sqlite").exists()

    def test_project_ids_set_correctly(
        self, tmp_path: Path, macro_root: Path, terminal_repo: Path
    ) -> None:
        """Documents in the terminal project must have project_ids=['terminal']."""
        import json as _json
        load_config, _ = _load_sources()
        run_ingest = _load_ingest()

        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir()
        cfg = _make_v2_config(macro_root, terminal_repo, mastermind_root=None)
        cfg["projects"]["macro-dashboard"]["root"] = str(macro_root)
        config_path = _write_config(cfg_dir, cfg)

        db_dir = tmp_path / "index"
        config = load_config(config_path)
        run_ingest(macro_root, db_dir, config, rebuild=True)

        conn = sqlite3.connect(str(db_dir / "terminal.sqlite"))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT project_ids FROM documents WHERE tombstoned=0").fetchall()
        conn.close()

        assert rows, "terminal.sqlite must have documents"
        for row in rows:
            pids = _json.loads(row["project_ids"])
            assert pids == ["terminal"], f"Expected ['terminal'], got {pids!r}"

    def test_external_docs_visibility_private(
        self, tmp_path: Path, macro_root: Path, terminal_repo: Path
    ) -> None:
        """All terminal documents must have visibility='private'."""
        load_config, _ = _load_sources()
        run_ingest = _load_ingest()

        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir()
        cfg = _make_v2_config(macro_root, terminal_repo, mastermind_root=None)
        cfg["projects"]["macro-dashboard"]["root"] = str(macro_root)
        config_path = _write_config(cfg_dir, cfg)

        db_dir = tmp_path / "index"
        config = load_config(config_path)
        run_ingest(macro_root, db_dir, config, rebuild=True)

        conn = sqlite3.connect(str(db_dir / "terminal.sqlite"))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT visibility FROM documents WHERE tombstoned=0"
        ).fetchall()
        conn.close()

        for row in rows:
            assert row["visibility"] == "private"

    def test_external_source_uri_scheme(
        self, tmp_path: Path, macro_root: Path, terminal_repo: Path
    ) -> None:
        """External docs get repo://<key>/<relpath>; macro keeps repo://<relpath>."""
        load_config, _ = _load_sources()
        run_ingest = _load_ingest()

        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir()
        cfg = _make_v2_config(macro_root, terminal_repo, mastermind_root=None)
        cfg["projects"]["macro-dashboard"]["root"] = str(macro_root)
        config_path = _write_config(cfg_dir, cfg)

        db_dir = tmp_path / "index"
        config = load_config(config_path)
        run_ingest(macro_root, db_dir, config, rebuild=True)

        # Terminal DB: URIs must start with repo://terminal/
        conn_t = sqlite3.connect(str(db_dir / "terminal.sqlite"))
        conn_t.row_factory = sqlite3.Row
        t_uris = [r["source_uri"] for r in conn_t.execute(
            "SELECT source_uri FROM documents WHERE tombstoned=0"
        ).fetchall()]
        conn_t.close()
        for uri in t_uris:
            assert uri.startswith("repo://terminal/"), (
                f"Terminal URI must start with repo://terminal/, got {uri!r}"
            )

        # Macro DB: URIs must start with repo:// but NOT repo://macro-dashboard/
        conn_m = sqlite3.connect(str(db_dir / "shared.sqlite"))
        conn_m.row_factory = sqlite3.Row
        m_uris = [r["source_uri"] for r in conn_m.execute(
            "SELECT source_uri FROM documents WHERE tombstoned=0"
        ).fetchall()]
        conn_m.close()
        for uri in m_uris:
            assert uri.startswith("repo://"), f"Macro URI must start with repo://, got {uri!r}"
            assert not uri.startswith("repo://macro-dashboard/"), (
                f"Macro URI must NOT include project key prefix, got {uri!r}"
            )


# ---------------------------------------------------------------------------
# Tests: deny rules on external projects
# ---------------------------------------------------------------------------


class TestExternalDenyRules:
    def test_terminal_data_dir_denied(
        self, tmp_path: Path, macro_root: Path, terminal_repo: Path
    ) -> None:
        """terminal/public/data/** must not appear in terminal.sqlite."""
        load_config, _ = _load_sources()
        run_ingest = _load_ingest()

        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir()
        cfg = _make_v2_config(macro_root, terminal_repo, mastermind_root=None)
        cfg["projects"]["macro-dashboard"]["root"] = str(macro_root)
        config_path = _write_config(cfg_dir, cfg)

        db_dir = tmp_path / "index"
        config = load_config(config_path)
        run_ingest(macro_root, db_dir, config, rebuild=True)

        conn = sqlite3.connect(str(db_dir / "terminal.sqlite"))
        conn.row_factory = sqlite3.Row
        paths = [r["path"] for r in conn.execute(
            "SELECT path FROM documents WHERE tombstoned=0"
        ).fetchall()]
        conn.close()

        for p in paths:
            assert "terminal/public/data" not in p, (
                f"Denied path appeared in index: {p!r}"
            )

    def test_mastermind_data_wholesale_denied(
        self, tmp_path: Path, macro_root: Path, mastermind_repo: Path
    ) -> None:
        """data/** in mastermind must not appear in mastermind.sqlite."""
        load_config, _ = _load_sources()
        run_ingest = _load_ingest()

        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir()
        cfg = _make_v2_config(macro_root, terminal_root=None, mastermind_root=mastermind_repo)
        cfg["projects"]["macro-dashboard"]["root"] = str(macro_root)
        config_path = _write_config(cfg_dir, cfg)

        db_dir = tmp_path / "index"
        config = load_config(config_path)
        run_ingest(macro_root, db_dir, config, rebuild=True)

        conn = sqlite3.connect(str(db_dir / "mastermind.sqlite"))
        conn.row_factory = sqlite3.Row
        paths = [r["path"] for r in conn.execute(
            "SELECT path FROM documents WHERE tombstoned=0"
        ).fetchall()]
        conn.close()

        for p in paths:
            assert not p.startswith("data/"), (
                f"Mastermind data/** path appeared in index: {p!r}"
            )


# ---------------------------------------------------------------------------
# Tests: content tripwire on external files
# ---------------------------------------------------------------------------


class TestExternalTripwire:
    def test_tripwire_fires_on_external_file(
        self, tmp_path: Path, macro_root: Path, terminal_repo: Path
    ) -> None:
        """A file with a fake credential in an external repo must be tripwired."""
        # Write a file with a fake AWS-style access key (assembled from fragments)
        # Pattern: AKIA + exactly 16 uppercase/digit chars (never a real key)
        fake_key = "AKIA" + "EXAMPLEFAKE" + "00001"  # 16 chars after AKIA
        _write_file(
            terminal_repo,
            "ingest/loader_with_key.py",   # no "secret" in name — must reach tripwire
            f'aws_access_key_id = "{fake_key}"\n',
        )

        load_config, _ = _load_sources()
        run_ingest = _load_ingest()

        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir()
        cfg = _make_v2_config(macro_root, terminal_repo, mastermind_root=None)
        cfg["projects"]["macro-dashboard"]["root"] = str(macro_root)
        config_path = _write_config(cfg_dir, cfg)

        db_dir = tmp_path / "index"
        config = load_config(config_path)
        result = run_ingest(macro_root, db_dir, config, rebuild=True)

        # The tripwire should have fired at least once for the terminal project
        term_result = result.projects.get("terminal")
        assert term_result is not None
        assert term_result.tripwire_skips >= 1, (
            "Expected at least one tripwire skip for external file with fake credential"
        )

        # Verify the file is not in the DB
        conn = sqlite3.connect(str(db_dir / "terminal.sqlite"))
        conn.row_factory = sqlite3.Row
        paths = [r["path"] for r in conn.execute(
            "SELECT path FROM documents WHERE tombstoned=0"
        ).fetchall()]
        conn.close()
        assert not any("loader_with_key" in p for p in paths)


# ---------------------------------------------------------------------------
# Tests: code_blocks chunker
# ---------------------------------------------------------------------------


class TestCodeBlocksChunker:
    def test_ts_export_boundaries(self) -> None:
        """Export function/const/interface lines must start new blocks when content is large."""
        code_blocks = _load_chunking()
        # Make each export large enough that accumulation crosses _CHUNK_TARGET_MAX (~3600 chars)
        big_body = "  // " + "x" * 2000 + "\n"
        content = (
            "// preamble\nconst VERSION = '1';\n\n"
            f"export function alpha(): void {{\n{big_body}}}\n\n"
            f"export function beta(): void {{\n{big_body}}}\n\n"
            f"export function gamma(): void {{\n{big_body}}}\n"
        )
        chunks = code_blocks("utils.ts", content)
        assert len(chunks) >= 2, f"Expected >=2 chunks for large TS with exports, got {len(chunks)}"
        # All locators must use #block-<n>
        for c in chunks:
            assert "#block-" in c.locator, f"Locator must use #block-<n>: {c.locator!r}"

    def test_sql_create_table_split(self) -> None:
        """CREATE TABLE boundaries are detected; large content forces multiple chunks."""
        code_blocks = _load_chunking()
        # Use enough content per table that accumulation overflows the target size
        big_cols = ",\n    ".join(
            f"col_{i} TEXT DEFAULT 'default_val_string_{i}'" for i in range(40)
        )
        content = (
            f"CREATE TABLE signals (\n    id SERIAL PRIMARY KEY,\n    {big_cols}\n);\n"
            f"CREATE TABLE positions (\n    id SERIAL PRIMARY KEY,\n    {big_cols}\n);\n"
        )
        chunks = code_blocks("001_init.sql", content)
        assert len(chunks) >= 2, (
            f"Expected >=2 chunks for large SQL with multiple CREATE TABLE, got {len(chunks)}"
        )

    def test_no_boundary_fallback(self) -> None:
        """Content with no export/class/CREATE boundaries → fixed-size windows."""
        code_blocks = _load_chunking()
        # plain prose / config TOML with no matching patterns
        content = "[tool.poetry]\nname = 'myapp'\nversion = '0.1.0'\n" * 5
        chunks = code_blocks("pyproject.toml", content)
        # At minimum, one chunk
        assert len(chunks) >= 1
        for c in chunks:
            assert "#block-" in c.locator

    def test_stable_block_ordinals_on_append(self) -> None:
        """Appending content at the end must not change earlier block ordinals."""
        code_blocks = _load_chunking()
        # Make each function large enough to be its own chunk (>3600 chars total when combined)
        big_body = "  // " + "x" * 2000 + "\n"
        base_content = (
            f"export function alpha(): void {{\n{big_body}}}\n"
            f"export function beta(): void {{\n{big_body}}}\n"
        )
        extended_content = base_content + f"export function gamma(): void {{\n{big_body}}}\n"

        base_chunks = code_blocks("file.ts", base_content)
        ext_chunks = code_blocks("file.ts", extended_content)

        # Must produce multiple chunks (otherwise ordinal stability is trivially satisfied)
        assert len(base_chunks) >= 2, (
            f"Need >=2 base chunks to test ordinal stability, got {len(base_chunks)}"
        )

        # All base locators must still appear in the extended set (stable prefix)
        base_locators = {c.locator for c in base_chunks}
        ext_locators = {c.locator for c in ext_chunks}

        for loc in base_locators:
            assert loc in ext_locators, (
                f"Stable ordinal violated: {loc!r} disappeared after append.\n"
                f"Base: {[c.locator for c in base_chunks]}\n"
                f"Ext:  {[c.locator for c in ext_chunks]}"
            )

    def test_empty_content_returns_no_chunks(self) -> None:
        code_blocks = _load_chunking()
        assert code_blocks("empty.ts", "") == []
        assert code_blocks("empty.ts", "   \n  ") == []

    def test_sql_case_insensitive(self) -> None:
        """CREATE TABLE (lowercase) must be detected as a block boundary."""
        code_blocks = _load_chunking()
        # Use large content to force multiple chunks when boundaries exist
        big_cols = ",\n    ".join(
            f"col_{i} TEXT DEFAULT 'default_val_string_{i}'" for i in range(40)
        )
        content = (
            f"create table foo (\n    id int,\n    {big_cols}\n);\n"
            f"create table bar (\n    id int,\n    {big_cols}\n);\n"
        )
        chunks = code_blocks("lower.sql", content)
        assert len(chunks) >= 2, "Lowercase CREATE TABLE must be detected as boundary"

    def test_heading_path_from_first_line(self) -> None:
        """heading_path for each block must be derived from the first line."""
        code_blocks = _load_chunking()
        content = (
            "export function alpha(): void { return; }\n"
            "export function beta(): void { return; }\n"
        )
        chunks = code_blocks("funcs.ts", content)
        assert len(chunks) >= 1
        # Each chunk with a block boundary should have a heading_path
        for c in chunks:
            if c.heading_path:
                assert isinstance(c.heading_path, list)
                assert len(c.heading_path[0]) <= 80


# ---------------------------------------------------------------------------
# Tests: health report with multi-project
# ---------------------------------------------------------------------------


class TestHealthMultiProject:
    def test_absent_projects_in_health(
        self, tmp_path: Path, macro_root: Path
    ) -> None:
        """absent_projects in health report must match config.absent_projects."""
        load_config, _ = _load_sources()
        run_ingest = _load_ingest()
        build_health_report = _load_health()

        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir()
        cfg = _make_v2_config(macro_root, terminal_root=None, mastermind_root=None)
        cfg["projects"]["terminal"] = {
            "root": str(tmp_path / "no-terminal"),
            "visibility": "private",
            "db": "terminal.sqlite",
            "sources": [],
            "deny": [],
        }
        cfg["projects"]["macro-dashboard"]["root"] = str(macro_root)
        config_path = _write_config(cfg_dir, cfg)

        db_dir = tmp_path / "index"
        config = load_config(config_path)
        result = run_ingest(macro_root, db_dir, config, rebuild=True)
        report = build_health_report(db_dir, ingest_result=result, config=config)

        assert "absent_projects" in report
        assert "terminal" in report["absent_projects"]
        # absent_projects must be keys only
        for k in report["absent_projects"]:
            assert "/" not in k

    def test_per_project_blocks_in_health(
        self, tmp_path: Path, macro_root: Path, terminal_repo: Path
    ) -> None:
        """Health report must include per-project blocks under 'projects' key."""
        load_config, _ = _load_sources()
        run_ingest = _load_ingest()
        build_health_report = _load_health()

        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir()
        cfg = _make_v2_config(macro_root, terminal_repo, mastermind_root=None)
        cfg["projects"]["macro-dashboard"]["root"] = str(macro_root)
        config_path = _write_config(cfg_dir, cfg)

        db_dir = tmp_path / "index"
        config = load_config(config_path)
        result = run_ingest(macro_root, db_dir, config, rebuild=True)
        report = build_health_report(db_dir, ingest_result=result, config=config)

        assert "projects" in report
        assert "macro-dashboard" in report["projects"]
        assert "terminal" in report["projects"]
        assert report["projects"]["terminal"]["total_docs"] > 0
        assert report["projects"]["terminal"]["total_chunks"] > 0

    def test_health_no_external_paths_in_output(
        self, tmp_path: Path, macro_root: Path, terminal_repo: Path
    ) -> None:
        """Health report must never contain external file paths or chunk text."""
        load_config, _ = _load_sources()
        run_ingest = _load_ingest()
        build_health_report = _load_health()

        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir()
        cfg = _make_v2_config(macro_root, terminal_repo, mastermind_root=None)
        cfg["projects"]["macro-dashboard"]["root"] = str(macro_root)
        config_path = _write_config(cfg_dir, cfg)

        db_dir = tmp_path / "index"
        config = load_config(config_path)
        result = run_ingest(macro_root, db_dir, config, rebuild=True)
        import json as _json
        report_str = _json.dumps(
            build_health_report(db_dir, ingest_result=result, config=config)
        )

        # External absolute paths must not leak into health report
        external_path_str = str(terminal_repo)
        assert external_path_str not in report_str, (
            "External repo path must not appear in health report"
        )


# ---------------------------------------------------------------------------
# Tests: v1 config rejection
# ---------------------------------------------------------------------------


class TestV1ConfigRejection:
    def test_v1_config_raises_clear_error(self, tmp_path: Path) -> None:
        """Loading a v1 config must raise ValueError with a clear message."""
        load_config, _ = _load_sources()
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir()
        v1_cfg = {
            "schema": "macro_context_index.config.v1",
            "projects": {},
            "sources": [],
            "deny": [],
        }
        config_path = _write_config(cfg_dir, v1_cfg)
        with pytest.raises(ValueError, match="v1.*no longer supported|v2"):
            load_config(config_path)
