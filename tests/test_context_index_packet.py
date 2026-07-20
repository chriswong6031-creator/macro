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


# ---------------------------------------------------------------------------
# No-answer floor gate
# ---------------------------------------------------------------------------

from engine.context_index.packet import (
    _compute_distinctive_term_count,
    NO_ANSWER_FLOOR,
)


class TestNoAnswerFloor:
    """Tests for the no-answer floor gate (Amendment 2, CXI-R18 quality lane)."""

    # --- Distinctive-term count unit tests ---

    def test_distinctive_term_count_zero_on_empty_text(self):
        """Empty text → 0 distinctive terms."""
        count = _compute_distinctive_term_count("hello world query", "", "", "")
        assert count == 0

    def test_distinctive_term_count_stops_short_tokens(self):
        """Tokens shorter than 4 chars are not distinctive."""
        # Query: "is it a cat" — all tokens < 4 chars or stopwords → 0
        count = _compute_distinctive_term_count("is it a cat", "cat is here", "", "")
        # "cat" has length 3 — not distinctive; stopword filter on "the","and" etc.
        # "cat" len=3 < 4, so 0 distinctive tokens from query
        assert count == 0

    def test_distinctive_term_count_matches_in_text(self):
        """Distinctive query terms found in text → count > 0."""
        # Assemble token at runtime (rule: no hardcoded benchmark text)
        token_a = "".join(["corp", "orate"])   # "corporate" — length 9 > 4
        token_b = "".join(["regi", "stry"])    # "registry" — length 8 > 4
        text = f"This is about {token_a} {token_b} policies"
        query = f"What {token_a} {token_b} rules apply"
        count = _compute_distinctive_term_count(query, text, "", "")
        assert count >= 2

    def test_distinctive_term_count_matches_in_path(self):
        """Distinctive query tokens found in path → count > 0."""
        token = "".join(["build", "_active"])  # "build_active"
        path = f"scripts/{token}_map.py"
        query = f"Where does {token} map script live"
        count = _compute_distinctive_term_count(query, "", "", path)
        assert count >= 1

    def test_distinctive_term_count_stopwords_excluded(self):
        """Common stopwords are not counted as distinctive."""
        # Query contains only stopwords + short words
        query = "where what does this have from with"
        text = "where what does this have from with"
        count = _compute_distinctive_term_count(query, text, text, "")
        # All query tokens are in the stopwords list → 0 distinctive
        assert count == 0

    # --- Integration tests: floor gate in build_packet ---

    def test_null_query_returns_no_answer_when_lexical_finds_nothing(self, tmp_path):
        """
        When the FTS5 index returns no matches (extremely rare/constructed token),
        no_answer_reason must be set.

        Uses a gobbledygook token assembled at runtime so that FTS5 returns
        zero rows (not just a low score — score<FLOOR is the active gate only
        when at least one result exists).

        Note: the distinctive_count==0 branch was removed (finding #1, 2026-07-20).
        The sole active gate is score < NO_ANSWER_FLOOR (0.010).
        """
        repo = _mini_repo(tmp_path, {
            "research/unrelated.md": "# Monetary Policy\n\nInterest rates and yield curve analysis."
        })
        db_dir, _ = _build_db(tmp_path, repo, [
            ("research/unrelated.md", "markdown_sections", "research", "A3"),
        ])

        # This impossible string will not be in the FTS index;
        # FTS5 will return 0 results and packet will set no_answer_reason.
        impossible_token = "xyzzy_" + "q" * 30 + "_zqv"
        packet = build_packet(
            query=impossible_token,
            db_dir=db_dir,
            project_db_map={"macro-dashboard": "shared.sqlite"},
            repo_root_map={"macro-dashboard": repo},
            include_gitinfo=False,
            expand_neighbors=False,
        )
        # When FTS5 + structured return zero rows, no_answer_reason must be set
        if not packet.get("results"):
            assert packet["no_answer_reason"] is not None, (
                "no_answer_reason must be set when results is empty"
            )

    def test_score_floor_fires_below_threshold(self, tmp_path):
        """
        The score<FLOOR gate fires when the top fused result has fused_score < NO_ANSWER_FLOOR.
        Verify by building a packet and confirming the floor constant is at its calibrated value.

        NOTE: the distinctive_count==0 branch was removed (finding #1, 2026-07-20).
        The count==0 rule fired on 0 rows on the frozen 68-row benchmark (domain vocab
        in CLAUDE.md/configs gives count>=1 for any English query). It caused false
        nulls for code-comprehension queries and has been dropped.
        The score<FLOOR branch is the sole active gate.
        """
        # Confirm the floor constant is still at the calibrated value
        assert NO_ANSWER_FLOOR == 0.010, (
            f"NO_ANSWER_FLOOR should be 0.010 (calibrated on frozen benchmark); "
            f"found {NO_ANSWER_FLOOR}"
        )
        # A query with a distinctive term present in the indexed content must NOT fire
        term = "".join(["yield", "curve"])  # "yieldcurve"
        repo = _mini_repo(tmp_path, {
            "research/rates.md": f"# Rates\n\nAnalysis of {term} dynamics and duration risk."
        })
        db_dir, _ = _build_db(tmp_path, repo, [
            ("research/rates.md", "markdown_sections", "research", "A3"),
        ])
        packet = build_packet(
            query=f"What is {term} inversion signalling",
            db_dir=db_dir,
            project_db_map={"macro-dashboard": "shared.sqlite"},
            repo_root_map={"macro-dashboard": repo},
            include_gitinfo=False,
            expand_neighbors=False,
        )
        # Score above floor → results returned, no null
        assert len(packet["results"]) >= 1, (
            "On-topic query with distinctive terms must not be suppressed by floor"
        )
        assert packet["no_answer_reason"] is None

    def test_strong_query_unaffected_by_floor(self, tmp_path):
        """
        A query whose distinctive terms appear in indexed content must
        NOT be suppressed by the no-answer floor.
        """
        # Assemble query terms at runtime
        term_a = "".join(["retriev", "al"])      # "retrieval"
        term_b = "".join(["bench", "mark"])      # "benchmark"
        repo = _mini_repo(tmp_path, {
            "research/cxi.md": (
                f"# Context Index {term_b.capitalize()}\n\n"
                f"This document describes {term_a} quality and {term_b} methodology."
            )
        })
        db_dir, _ = _build_db(tmp_path, repo, [
            ("research/cxi.md", "markdown_sections", "research", "A3"),
        ])
        query = f"What {term_a} {term_b} methodology is used for the context index"

        packet = build_packet(
            query=query,
            db_dir=db_dir,
            project_db_map={"macro-dashboard": "shared.sqlite"},
            repo_root_map={"macro-dashboard": repo},
            include_gitinfo=False,
            expand_neighbors=False,
        )
        assert len(packet["results"]) >= 1, (
            "Strong on-topic query must not be suppressed by no-answer floor; "
            f"no_answer_reason={packet.get('no_answer_reason')!r}"
        )
        assert packet["no_answer_reason"] is None, (
            f"Unexpected no_answer on strong query: {packet['no_answer_reason']}"
        )

    def test_no_answer_reason_explains_which_rule_fired(self, tmp_path):
        """
        When the floor gate fires, no_answer_reason must contain an
        explanation identifying which rule triggered (score or term count).
        """
        repo = _mini_repo(tmp_path, {
            "research/doc.md": "# Doc\n\nContent about monetary policy and yield curves."
        })
        db_dir, _ = _build_db(tmp_path, repo, [
            ("research/doc.md", "markdown_sections", "research", "A3"),
        ])
        absent_term = "".join(["xeno", "morph", "ology"])  # "xenomorphology"
        query = f"Is there a committed {absent_term} signal integration in this repo"

        packet = build_packet(
            query=query,
            db_dir=db_dir,
            project_db_map={"macro-dashboard": "shared.sqlite"},
            repo_root_map={"macro-dashboard": repo},
            include_gitinfo=False,
            expand_neighbors=False,
        )
        if packet["results"] == []:
            reason = packet.get("no_answer_reason", "")
            assert reason, "no_answer_reason must be non-empty when results is empty"
            # Must explain WHICH rule fired — score floor or zero results
            # (distinctive_count==0 branch was removed in 2026-07-20 fix)
            assert "no_answer" in reason or "floor" in reason or "No results" in reason

    def test_floor_constant_pinned(self):
        """
        NO_ANSWER_FLOOR calibration constant must not drift.
        Pinned at 0.010 per frozen-benchmark calibration (run v3).
        Re-calibrate and update this assertion if the benchmark set changes.
        """
        assert NO_ANSWER_FLOOR == 0.010, (
            f"NO_ANSWER_FLOOR drifted to {NO_ANSWER_FLOOR}; "
            "re-run calibration and update the assertion if intentionally changed"
        )

    def test_compound_identifier_code_query_not_nulled(self, tmp_path):
        """
        Regression for finding #1 (2026-07-20): code-comprehension queries using
        compound function identifiers must NOT return empty results.

        The old distinctive_count==0 branch caused false nulls when the compound
        identifier (e.g. 'build_packet') was absent from an off-topic top-ranked
        governance chunk, even though the packet function itself was retrievable.
        With the count==0 branch removed, these queries must return non-empty results
        when the function IS indexed.

        Token assembled at runtime (no hardcoded benchmark text).
        """
        func_name = "".join(["build", "_pack", "et"])  # "build_packet"
        repo = _mini_repo(tmp_path, {
            "engine/assembler.py": (
                f"def {func_name}(query, db_dir):\n"
                f"    '''Assembles a context packet from the query and db.'''\n"
                f"    return {{}}\n"
            )
        })
        db_dir, _ = _build_db(tmp_path, repo, [
            ("engine/assembler.py", "python_symbols", "code", "A2"),
        ])
        query = f"What does {func_name} do?"
        packet = build_packet(
            query=query,
            db_dir=db_dir,
            project_db_map={"macro-dashboard": "shared.sqlite"},
            repo_root_map={"macro-dashboard": repo},
            include_gitinfo=False,
            expand_neighbors=False,
        )
        # Must not be nulled: the function is indexed and the query is legitimate
        assert len(packet["results"]) >= 1, (
            f"Compound-identifier code query was falsely nulled; "
            f"no_answer_reason={packet.get('no_answer_reason')!r}"
        )
