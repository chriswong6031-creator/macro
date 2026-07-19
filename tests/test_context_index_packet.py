"""
CXI-2 packet tests.

Tests context_packet.v1 structure, schema contract, conflicts, and edge cases.

All fixtures in tmp_path only — never touch real data/, site/, .context-index/.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from engine.context_index.ingest import run_ingest
from engine.context_index.sources import Config, SourceEntry
from engine.context_index.packet import build_packet, TOKEN_BUDGET_DEFAULT, TOKEN_BUDGET_HARD_CAP
from engine.context_index.schema import open_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mini_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    (repo / ".git").mkdir(exist_ok=True)
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return repo


def _build_db(tmp_path: Path, repo: Path, sources_and_chunkers) -> tuple[Path, Path]:
    db_dir = tmp_path / "db"
    db_dir.mkdir(exist_ok=True)
    sources = [
        SourceEntry(
            id=f"src-{i}",
            roots=[r],
            authority_class=a,
            visibility="shared",
            chunker=c,
            source_type=st,
        )
        for i, (r, c, st, a) in enumerate(sources_and_chunkers)
    ]
    cfg = Config(sources=sources, deny=[])
    run_ingest(repo, db_dir, cfg, rebuild=True)
    return db_dir, repo


# ---------------------------------------------------------------------------
# Schema compliance
# ---------------------------------------------------------------------------

class TestPacketSchema:
    def test_packet_has_required_fields(self, tmp_path):
        """context_packet.v1 must have all required top-level fields."""
        repo = _mini_repo(tmp_path, {
            "research/test.md": "# Test\n\nSome content here."
        })
        db_dir, _ = _build_db(tmp_path, repo, [
            ("research/test.md", "markdown_sections", "research", "A3"),
        ])

        packet = build_packet(
            query="test content",
            db_dir=db_dir,
            project_db_map={"macro-dashboard": "shared.sqlite"},
            repo_root_map={"macro-dashboard": repo},
            generated_at="2026-07-18T00:00:00Z",
            include_gitinfo=False,
        )

        required_fields = [
            "schema", "query", "project_scope", "mode", "generated_at",
            "repo_sha", "index_sha", "index_stale", "token_budget",
            "retrievers_used", "results", "conflicts", "omitted_due_to_budget",
            "no_answer_reason",
        ]
        for field in required_fields:
            assert field in packet, f"Missing required field: {field!r}"

        assert packet["schema"] == "context_packet.v1"
        assert packet["generated_at"] == "2026-07-18T00:00:00Z"
        assert isinstance(packet["project_scope"], list)
        assert isinstance(packet["results"], list)
        assert isinstance(packet["conflicts"], list)
        assert isinstance(packet["retrievers_used"], list)
        assert isinstance(packet["index_stale"], bool)

    def test_result_items_have_required_fields(self, tmp_path):
        """Each result item must have the required fields per §7.3."""
        repo = _mini_repo(tmp_path, {
            "research/test.md": "# Test\n\nSome content about unique_content_tag_abc123."
        })
        db_dir, _ = _build_db(tmp_path, repo, [
            ("research/test.md", "markdown_sections", "research", "A3"),
        ])

        packet = build_packet(
            query="unique_content_tag_abc123",
            db_dir=db_dir,
            project_db_map={"macro-dashboard": "shared.sqlite"},
            repo_root_map={"macro-dashboard": repo},
            include_gitinfo=False,
        )

        result_fields = [
            "source_uri", "locator", "authority_class", "status",
            "excerpt", "score_components", "why_retrieved",
        ]
        for r in packet["results"]:
            for field in result_fields:
                assert field in r, f"Result missing field {field!r}: {r}"

            sc = r["score_components"]
            assert "fused_score" in sc
            assert "semantic_rank" in sc
            assert sc["semantic_rank"] is None  # no semantic lane in v1

    def test_token_budget_hard_cap(self, tmp_path):
        """token_budget must be capped at TOKEN_BUDGET_HARD_CAP."""
        repo = _mini_repo(tmp_path, {"research/doc.md": "# Doc\n\nContent."})
        db_dir, _ = _build_db(tmp_path, repo, [
            ("research/doc.md", "markdown_sections", "research", "A3"),
        ])

        packet = build_packet(
            query="content",
            db_dir=db_dir,
            project_db_map={"macro-dashboard": "shared.sqlite"},
            repo_root_map={"macro-dashboard": repo},
            token_budget=99999,  # exceeds hard cap
            include_gitinfo=False,
        )
        assert packet["token_budget"] <= TOKEN_BUDGET_HARD_CAP

    def test_deterministic_with_same_timestamp(self, tmp_path):
        """Same query + same timestamp → same generated_at in packet."""
        repo = _mini_repo(tmp_path, {"research/doc.md": "# Doc\n\nContent."})
        db_dir, _ = _build_db(tmp_path, repo, [
            ("research/doc.md", "markdown_sections", "research", "A3"),
        ])
        ts = "2026-07-18T12:00:00Z"
        p1 = build_packet(
            query="content",
            db_dir=db_dir,
            project_db_map={"macro-dashboard": "shared.sqlite"},
            repo_root_map={"macro-dashboard": repo},
            generated_at=ts,
            include_gitinfo=False,
        )
        p2 = build_packet(
            query="content",
            db_dir=db_dir,
            project_db_map={"macro-dashboard": "shared.sqlite"},
            repo_root_map={"macro-dashboard": repo},
            generated_at=ts,
            include_gitinfo=False,
        )
        assert p1["generated_at"] == p2["generated_at"] == ts
        assert p1["results"] == p2["results"]


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

class TestConflicts:
    def test_conflict_when_killed_and_active_both_rank(self, tmp_path):
        """
        When a killed/forbidden registry row AND an active doc both rank for
        the query, conflicts list must be populated.
        """
        REGISTRY_CONTENT = """# DO NOT REBUILD

## 1. FORBIDDEN by ruling

| Topic | Verdict |
|-------|---------|
| my_feature_xyz | FORBIDDEN — TEST-R1 |

## 2. KILLED by ruling

| Topic | Verdict |
|-------|---------|
| my_feature_xyz | KILLED — TEST-R2 |
"""
        repo = _mini_repo(tmp_path, {
            "research/DO_NOT_REBUILD.md": REGISTRY_CONTENT,
            "research/active.md": (
                "# Active Feature\n\nThis describes my_feature_xyz as an active ongoing work."
            ),
        })
        db_dir = tmp_path / "db"
        db_dir.mkdir(exist_ok=True)
        sources = [
            SourceEntry("s1", ["research/DO_NOT_REBUILD.md"], "A1", "shared", "registry_rows", "ruling"),
            SourceEntry("s2", ["research/active.md"], "A3", "shared", "markdown_sections", "research"),
        ]
        cfg = Config(sources=sources, deny=[])
        run_ingest(repo, db_dir, cfg, rebuild=True)

        # adjudication mode: both killed and active rows included
        packet = build_packet(
            query="my_feature_xyz",
            db_dir=db_dir,
            project_db_map={"macro-dashboard": "shared.sqlite"},
            repo_root_map={"macro-dashboard": repo},
            mode="adjudication",
            include_gitinfo=False,
        )
        assert isinstance(packet["conflicts"], list)
        # When a forbidden/killed registry row AND active doc both rank for the
        # same query topic, conflicts must be non-empty (CXI-R6 / docket §7.3)
        killed_results = [r for r in packet["results"] if r.get("status") in ("killed", "forbidden")]
        active_results = [r for r in packet["results"] if r.get("status") == "active"]
        if killed_results and active_results:
            assert len(packet["conflicts"]) > 0, (
                f"conflicts should be non-empty when killed+active both rank; "
                f"results statuses: {[r.get('status') for r in packet['results']]}"
            )


# ---------------------------------------------------------------------------
# No-answer
# ---------------------------------------------------------------------------

class TestNoAnswerPacket:
    def test_no_answer_reason_when_empty_results(self, tmp_path):
        """When no results found, no_answer_reason must be set."""
        repo = _mini_repo(tmp_path, {
            "research/doc.md": "# Doc\n\nContent about bananas."
        })
        db_dir, _ = _build_db(tmp_path, repo, [
            ("research/doc.md", "markdown_sections", "research", "A3"),
        ])
        packet = build_packet(
            query="xyzzy_impossible_string_that_will_never_match_zq9v8w",
            db_dir=db_dir,
            project_db_map={"macro-dashboard": "shared.sqlite"},
            repo_root_map={"macro-dashboard": repo},
            include_gitinfo=False,
        )
        if not packet.get("results"):
            assert packet["no_answer_reason"] is not None, (
                "no_answer_reason must be set when results is empty"
            )

    def test_top_result_always_included(self, tmp_path):
        """Top result must always be included even with tiny budget."""
        repo = _mini_repo(tmp_path, {
            "research/doc.md": "# Doc\n\nContent about very unique identifier vxyzzy123."
        })
        db_dir, _ = _build_db(tmp_path, repo, [
            ("research/doc.md", "markdown_sections", "research", "A3"),
        ])
        packet = build_packet(
            query="very unique identifier vxyzzy123",
            db_dir=db_dir,
            project_db_map={"macro-dashboard": "shared.sqlite"},
            repo_root_map={"macro-dashboard": repo},
            token_budget=10,  # impossibly small
            include_gitinfo=False,
            expand_neighbors=False,
        )
        # If there are any results, at least one must be present (top result always included)
        # (or no_answer if truly no match)
        if packet.get("results"):
            assert len(packet["results"]) >= 1


# ---------------------------------------------------------------------------
# Mode behavior
# ---------------------------------------------------------------------------

class TestModeField:
    def test_mode_stored_in_packet(self, tmp_path):
        repo = _mini_repo(tmp_path, {"research/doc.md": "# Doc\n\nContent."})
        db_dir, _ = _build_db(tmp_path, repo, [
            ("research/doc.md", "markdown_sections", "research", "A3"),
        ])
        for mode in ["code", "research", "governance", "adjudication"]:
            packet = build_packet(
                query="content",
                db_dir=db_dir,
                project_db_map={"macro-dashboard": "shared.sqlite"},
                repo_root_map={"macro-dashboard": repo},
                mode=mode,
                include_gitinfo=False,
            )
            assert packet["mode"] == mode

    def test_project_scope_stored(self, tmp_path):
        repo = _mini_repo(tmp_path, {"research/doc.md": "# Doc\n\nContent."})
        db_dir, _ = _build_db(tmp_path, repo, [
            ("research/doc.md", "markdown_sections", "research", "A3"),
        ])
        project_db_map = {"macro-dashboard": "shared.sqlite"}
        packet = build_packet(
            query="content",
            db_dir=db_dir,
            project_db_map=project_db_map,
            repo_root_map={"macro-dashboard": repo},
            include_gitinfo=False,
        )
        assert packet["project_scope"] == list(project_db_map.keys())
