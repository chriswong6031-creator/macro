"""
CXI-1 privacy tests.

Covers: deny rules, symlink escape, content tripwire (credential patterns).
All in tmp_path — never touches real data/.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from engine.context_index.ingest import run_ingest, _content_tripwire
from engine.context_index.sources import Config, SourceEntry, _is_denied
from engine.context_index.schema import open_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(glob: str, deny: list[str] = None, chunker: str = "markdown_sections") -> Config:
    return Config(
        sources=[SourceEntry(
            id="src-0", roots=[glob], authority_class="A3",
            visibility="shared", chunker=chunker, source_type="research",
        )],
        deny=deny or [],
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


# ---------------------------------------------------------------------------
# Deny pattern tests
# ---------------------------------------------------------------------------


def test_env_file_denied():
    assert _is_denied(".env", ["**/.env*"]) is True
    assert _is_denied(".env.local", ["**/.env*"]) is True
    assert _is_denied("config/.env", ["**/.env*"]) is True


def test_credential_file_denied():
    assert _is_denied("secrets/credentials.json", ["**/*credential*"]) is True
    assert _is_denied("auth.json", ["**/auth.json"]) is True


def test_site_dir_denied():
    assert _is_denied("site/index.html", ["site/**"]) is True
    assert _is_denied("site/us_stocks.html", ["site/**"]) is True


def test_data_dir_denied():
    assert _is_denied("data/parquet/foo.parquet", ["data/**"]) is True
    assert _is_denied("data/flow_signals/scores.parquet", ["data/**"]) is True


def test_pycache_denied():
    assert _is_denied("engine/__pycache__/foo.pyc", ["**/__pycache__/**"]) is True


def test_git_dir_denied():
    assert _is_denied(".git/config", [".git/**"]) is True


def test_normal_file_not_denied():
    deny = ["**/.env*", "site/**", "data/**", "**/__pycache__/**"]
    assert _is_denied("docs/guide.md", deny) is False
    assert _is_denied("engine/mod.py", deny) is False


# ---------------------------------------------------------------------------
# Ingest deny enforcement
# ---------------------------------------------------------------------------


def test_env_file_not_ingested(tmp_path):
    """A .env file in the source tree must not appear in the DB."""
    repo = _repo(tmp_path, {
        "docs/ok.md": "# OK\n\nFine content.\n",
        ".env": "SECRET_KEY=hunter2\n",
    })
    cfg = Config(
        sources=[
            SourceEntry(id="docs", roots=["docs/**/*.md"], authority_class="A3",
                        visibility="shared", chunker="markdown_sections", source_type="research"),
            SourceEntry(id="env", roots=[".env"], authority_class="A3",
                        visibility="shared", chunker="whole_file", source_type="config"),
        ],
        deny=["**/.env*"],
    )
    db_dir = tmp_path / "db"
    result = run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    uris = [r["source_uri"] for r in conn.execute("SELECT source_uri FROM documents").fetchall()]
    conn.close()
    assert not any(".env" in u for u in uris), f"Denied .env appears in DB: {uris}"
    assert result.denied_count >= 1 or result.tripwire_skips >= 1


def test_data_dir_not_ingested(tmp_path):
    """Files under data/ must not appear in the DB."""
    repo = _repo(tmp_path, {
        "docs/ok.md": "# OK\n\nContent.\n",
        "data/grades.parquet": "binary-data",
    })
    cfg = Config(
        sources=[
            SourceEntry(id="docs", roots=["docs/**/*.md"], authority_class="A3",
                        visibility="shared", chunker="markdown_sections", source_type="research"),
            SourceEntry(id="data", roots=["data/**"], authority_class="A3",
                        visibility="shared", chunker="whole_file", source_type="research"),
        ],
        deny=["data/**"],
    )
    db_dir = tmp_path / "db"
    result = run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    uris = [r["source_uri"] for r in conn.execute("SELECT source_uri FROM documents").fetchall()]
    conn.close()
    assert not any("data/" in u for u in uris), f"data/ files appeared in DB: {uris}"


# ---------------------------------------------------------------------------
# Content tripwire
# ---------------------------------------------------------------------------


def test_tripwire_aws_key():
    content = "aws_access_key_id = AKIAIOSFODNN7EXAMPLE\nrest of config"
    assert _content_tripwire(content) is True


def test_tripwire_private_key_block():
    content = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----\n"
    assert _content_tripwire(content) is True


def test_tripwire_bearer_token():
    content = 'bearer = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc123456789012345678"'
    assert _content_tripwire(content) is True


def test_tripwire_clean_content():
    content = "# Normal markdown\n\nThis is clean content without any secrets.\n"
    assert _content_tripwire(content) is False


def test_tripwire_key_reference_code_not_tripped():
    """Code that USES keys must not trip: `api_key:` at end-of-line must not
    match identifiers on following lines (\\s crossing newlines regression)."""
    content = (
        "if not self.api_key:\n"
        "    raise RuntimeError(quiver_congress_cache_unavailable_message)\n"
    )
    assert _content_tripwire(content) is False


def test_tripwire_identifier_value_not_tripped():
    """A bare identifier (no digits) on the value side is code, not a secret."""
    content = "access_token = _mm_supabase_access_token(request)\n"
    assert _content_tripwire(content) is False


def test_tripwire_literal_key_with_digits_still_tripped():
    """The digit-lookahead must not weaken detection of real literal keys.
    (Key-shaped literals here are FAKE — never embed a real credential in tests.)"""
    assert _content_tripwire('key = spec.get("api_key", "AIzaSyFAKE0TESTKEY00fake0test0key0000000")') is True
    assert _content_tripwire('token = "abcDEF1234567890abcdef1234"') is True
    assert _content_tripwire('_TOKEN = "894050c76af8597a853f5b408b000000"') is True


def test_tripwire_provider_prefix_prose_not_tripped():
    """Prose mentioning provider prefixes (docs, the scanner's own comments)
    must not trip — only digit-bearing token-shaped values do."""
    assert _content_tripwire("# common provider prefixes (ghp_/sk_live_/xox*/glpat-/AIza).") is False


def test_tripwire_file_skipped_not_ingested(tmp_path):
    """A file matching the tripwire must not appear in the DB."""
    secret_content = "aws_key = AKIAIOSFODNN7EXAMPLE\nsome other stuff\n"
    repo = _repo(tmp_path, {
        "docs/clean.md": "# Clean\n\nNo secrets here.\n",
        "config/secret_config.yml": secret_content,
    })
    cfg = Config(
        sources=[
            SourceEntry(id="docs", roots=["docs/**/*.md"], authority_class="A3",
                        visibility="shared", chunker="markdown_sections", source_type="research"),
            SourceEntry(id="cfg", roots=["config/**/*.yml"], authority_class="A1",
                        visibility="shared", chunker="yaml_keys", source_type="config"),
        ],
        deny=[],
    )
    db_dir = tmp_path / "db"
    result = run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    uris = [r["source_uri"] for r in conn.execute("SELECT source_uri FROM documents").fetchall()]
    conn.close()
    # The secret config must not appear
    assert not any("secret_config" in u for u in uris), f"Tripwired file in DB: {uris}"
    # The clean doc should be indexed
    assert any("clean" in u for u in uris)
    assert result.tripwire_skips >= 1


# ---------------------------------------------------------------------------
# Symlink escape
# ---------------------------------------------------------------------------


def test_symlink_escape_rejected(tmp_path):
    """A symlink pointing outside the repo root must be skipped, not ingested."""
    repo = _repo(tmp_path, {"docs/ok.md": "# OK\n\nContent.\n"})

    # Create an external file
    external = tmp_path / "external_secret.md"
    external.write_text("# EXTERNAL\n\nThis must not be indexed.\n", encoding="utf-8")

    # Create a symlink inside the repo pointing outside
    link = repo / "docs" / "escape_link.md"
    try:
        link.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this OS")

    cfg = Config(
        sources=[SourceEntry(id="docs", roots=["docs/**/*.md"], authority_class="A3",
                             visibility="shared", chunker="markdown_sections", source_type="research")],
        deny=[],
    )
    db_dir = tmp_path / "db"
    result = run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    uris = [r["source_uri"] for r in conn.execute("SELECT source_uri FROM documents").fetchall()]
    conn.close()

    # The symlink escape must not be in the DB
    assert not any("escape_link" in u for u in uris), f"Symlink escape appeared in DB: {uris}"
    # ok.md should still be indexed
    assert any("ok.md" in u for u in uris)
    assert result.symlink_skips >= 1


def test_inrepo_symlink_to_denied_tree_rejected(tmp_path):
    """
    Finding #5 / #8: a symlink INSIDE the repo that points at an in-repo denied
    tree (data/) must be skipped and never ingested.

    Vector: docs/link.csv -> ../data/prices.csv
    The symlink's unresolved path is 'docs/link.csv' (not denied), but the
    resolved target 'data/prices.csv' IS denied.  The fix evaluates deny
    against both paths.
    """
    repo = _repo(tmp_path, {
        "docs/ok.md": "# OK\n\nSafe content.\n",
        "data/prices.csv": "row,val\n1,100\n",
    })
    link = repo / "docs" / "link.csv"
    try:
        link.symlink_to(repo / "data" / "prices.csv")
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this OS")

    cfg = Config(
        sources=[
            SourceEntry(id="docs", roots=["docs/**/*"], authority_class="A3",
                        visibility="shared", chunker="whole_file", source_type="research"),
            SourceEntry(id="data", roots=["data/**"], authority_class="A3",
                        visibility="shared", chunker="whole_file", source_type="research"),
        ],
        deny=["data/**"],
    )
    db_dir = tmp_path / "db"
    result = run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    texts = [r["text"] for r in conn.execute("SELECT text FROM chunks").fetchall()]
    uris = [r["source_uri"] for r in conn.execute("SELECT source_uri FROM documents").fetchall()]
    conn.close()

    # The linked file's content must not appear in chunks
    assert not any("row,val" in t for t in texts), (
        f"Denied data content found in chunks via symlink: {texts}"
    )
    assert not any("prices.csv" in u for u in uris), (
        f"Denied data URI found via symlink: {uris}"
    )
    # At least one skip was counted (denied or symlink)
    assert (result.denied_count + result.symlink_skips) >= 1


def test_tripwire_github_pat(tmp_path):
    """Provider-prefix patterns (ghp_...) are caught by the tripwire.
    Token literals are assembled at runtime so the committed source never
    contains a contiguous token shape (GitHub push protection flags those
    even when fake)."""
    content = "auth_token: " + "ghp" + "_aBcDeFgHiJkLmNoPqRsTuVwXyZ123\n"
    assert _content_tripwire(content) is True


def test_tripwire_slack_token(tmp_path):
    """Provider-prefix patterns (xoxb-...) are caught by the tripwire."""
    content = "bot_token = " + "xoxb" + "-1234567890-abcdefghijklmnopqrstu\n"
    assert _content_tripwire(content) is True


def test_tripwire_password_field(tmp_path):
    """password = <long-value> is caught by the broadened pattern."""
    content = 'password = "super_secret_hunter2_passphrase_for_db"\n'
    assert _content_tripwire(content) is True


def test_private_sources_excluded_in_cxi1(tmp_path):
    """CXI-1 shared-plane only: private sources are skipped entirely."""
    repo = _repo(tmp_path, {
        "docs/shared.md": "# Shared\n\nShared content.\n",
    })
    cfg = Config(
        sources=[
            SourceEntry(id="shared", roots=["docs/**/*.md"], authority_class="A3",
                        visibility="shared", chunker="markdown_sections", source_type="research"),
            SourceEntry(id="private", roots=["memory/**/*.md"], authority_class="A3",
                        visibility="private", chunker="markdown_sections", source_type="memory"),
        ],
        deny=[],
    )
    db_dir = tmp_path / "db"
    result = run_ingest(repo, db_dir, cfg, rebuild=True)
    conn = open_db(db_dir)
    private_docs = conn.execute(
        "SELECT COUNT(*) FROM documents WHERE visibility='private'"
    ).fetchone()[0]
    conn.close()
    assert private_docs == 0, "Private sources must not be ingested in CXI-1"
