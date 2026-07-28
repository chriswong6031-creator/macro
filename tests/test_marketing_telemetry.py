"""tests/test_marketing_telemetry.py — Telemetry engine tests.

Covers:
- ingest_rows + load_telemetry round-trip (incl. validation rejects)
- join_provenance integrity (orphans flagged, dims correct, cashtag_tier)
- rollup medians (hand-verified)
- N-floor law (cell n < 20 → verdict="seeding")
- Empty telemetry → honest n_posts=0 artifact
- write_rollup writes valid JSON
"""
from __future__ import annotations

import json
import pathlib

import pytest

from engine.marketing.telemetry import (
    ingest_rows,
    join_provenance,
    load_telemetry,
    rollup,
    write_rollup,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────────────

def _valid_row(
    post_id: str = "post-flagship-001",
    captured_at: str = "2026-07-19T10:00:00Z",
    impressions: int = 100,
    likes: int = 5,
    replies: int = 2,
    reposts: int = 1,
    bookmarks: int = 3,
) -> dict:
    return {
        "post_id": post_id,
        "captured_at": captured_at,
        "impressions": impressions,
        "likes": likes,
        "replies": replies,
        "reposts": reposts,
        "bookmarks": bookmarks,
    }


def _make_plan(accounts=None) -> dict:
    """Minimal content_plan fixture with 2 accounts × a few queue posts."""
    if accounts is None:
        accounts = [
            {
                "id": "flagship",
                "voice": "authoritative desk",
                "queue": [
                    {
                        "id": "post-flagship-001",
                        "type": "watchlist",
                        "account": "flagship",
                        "slot": "D1-AM",
                        "cashtag": "$SBUX",
                        "ticker": "SBUX",
                        "provenance": "neural_web",
                        "status": "drafted",
                        "_copy_mode": "deterministic",
                    },
                    {
                        "id": "post-flagship-002",
                        "type": "theme_list",
                        "account": "flagship",
                        "slot": "D2-PM",
                        "cashtag": "$NVDA",
                        "ticker": "NVDA",
                        "provenance": "movers_desk",
                        "status": "drafted",
                        "_copy_mode": "llm",
                    },
                ],
            },
            {
                "id": "research_b",
                "voice": "tape reader",
                "queue": [
                    {
                        "id": "post-resb-001",
                        "type": "mover",
                        "account": "research_b",
                        "slot": "D1-PM",
                        "cashtag": "$TSLA",
                        "ticker": "TSLA",
                        "provenance": "movers_desk",
                        "status": "drafted",
                        "_copy_mode": "deterministic",
                    },
                ],
            },
        ]
    return {
        "schema_version": 1,
        "produced_by": "test-fixture",
        "produced_at": "2026-07-19T00:00:00Z",
        "schema": "marketing.content/v1",
        "as_of": "2026-07-19",
        "accounts": accounts,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Ingest + load round-trip
# ─────────────────────────────────────────────────────────────────────────────

class TestIngestLoad:
    def test_round_trip_single_row(self, tmp_path):
        row = _valid_row()
        result = ingest_rows([row], root=tmp_path)
        assert result["ok"] == 1
        assert result["rejected"] == []

        loaded = load_telemetry(tmp_path)
        assert len(loaded) == 1
        assert loaded[0]["post_id"] == "post-flagship-001"
        assert loaded[0]["impressions"] == 100

    def test_round_trip_multiple_months(self, tmp_path):
        rows = [
            _valid_row(captured_at="2026-07-01T09:00:00Z"),
            _valid_row(post_id="post-flagship-002", captured_at="2026-08-01T09:00:00Z"),
        ]
        result = ingest_rows(rows, root=tmp_path)
        assert result["ok"] == 2

        # Two monthly files should exist
        tdir = tmp_path / "data" / "marketing" / "telemetry"
        files = sorted(tdir.glob("*.jsonl"))
        assert len(files) == 2
        assert files[0].name == "2026-07.jsonl"
        assert files[1].name == "2026-08.jsonl"

        loaded = load_telemetry(tmp_path)
        assert len(loaded) == 2

    def test_reject_missing_required_field(self, tmp_path):
        row = _valid_row()
        del row["impressions"]
        # impressions is required (in _REQUIRED_FIELDS); but we need at least one metric.
        # Let's remove a required field entirely
        row2 = _valid_row()
        del row2["post_id"]

        result = ingest_rows([row2], root=tmp_path)
        assert result["ok"] == 0
        assert len(result["rejected"]) == 1
        assert "post_id" in result["rejected"][0]["reason"]

    def test_reject_negative_metric(self, tmp_path):
        row = _valid_row(impressions=-1)
        result = ingest_rows([row], root=tmp_path)
        assert result["ok"] == 0
        assert "non-negative" in result["rejected"][0]["reason"]

    def test_reject_non_int_metric(self, tmp_path):
        row = _valid_row()
        row["likes"] = "five"
        result = ingest_rows([row], root=tmp_path)
        assert result["ok"] == 0
        assert "int" in result["rejected"][0]["reason"]

    def test_reject_invalid_captured_at(self, tmp_path):
        row = _valid_row(captured_at="not-a-date")
        result = ingest_rows([row], root=tmp_path)
        assert result["ok"] == 0
        assert "captured_at" in result["rejected"][0]["reason"]

    def test_reject_empty_post_id(self, tmp_path):
        row = _valid_row()
        row["post_id"] = "   "
        result = ingest_rows([row], root=tmp_path)
        assert result["ok"] == 0
        assert "post_id" in result["rejected"][0]["reason"]

    def test_optional_fields_accepted(self, tmp_path):
        row = _valid_row()
        row["link_clicks"] = 10
        row["followers_at_post"] = 42
        result = ingest_rows([row], root=tmp_path)
        assert result["ok"] == 1
        loaded = load_telemetry(tmp_path)
        assert loaded[0]["link_clicks"] == 10
        assert loaded[0]["followers_at_post"] == 42

    def test_empty_root_returns_empty_list(self, tmp_path):
        loaded = load_telemetry(tmp_path)
        assert loaded == []

    def test_mixed_valid_invalid(self, tmp_path):
        rows = [
            _valid_row(post_id="good"),
            {"post_id": "bad"},  # missing required fields
            _valid_row(post_id="also-good"),
        ]
        result = ingest_rows(rows, root=tmp_path)
        assert result["ok"] == 2
        assert len(result["rejected"]) == 1
        loaded = load_telemetry(tmp_path)
        assert len(loaded) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Join provenance
# ─────────────────────────────────────────────────────────────────────────────

class TestJoinProvenance:
    def _rows_fixture(self):
        """Two matched rows + one orphan."""
        return [
            _valid_row(post_id="post-flagship-001"),
            _valid_row(post_id="post-resb-001", impressions=200),
            _valid_row(post_id="orphan-post-xyz"),  # not in plan
        ]

    def test_join_splits_correctly(self, tmp_path):
        rows = self._rows_fixture()
        plan = _make_plan()
        result = join_provenance(rows, plan, root=tmp_path)
        assert len(result["joined"]) == 2
        assert len(result["orphans"]) == 1

    def test_orphan_flagged(self, tmp_path):
        rows = self._rows_fixture()
        plan = _make_plan()
        result = join_provenance(rows, plan, root=tmp_path)
        orphan = result["orphans"][0]
        assert orphan["orphan"] is True
        assert orphan["post_id"] == "orphan-post-xyz"

    def test_joined_dims_correct(self, tmp_path):
        rows = [_valid_row(post_id="post-flagship-001")]
        plan = _make_plan()
        result = join_provenance(rows, plan, root=tmp_path)
        assert len(result["joined"]) == 1
        j = result["joined"][0]
        assert j["kind"] == "watchlist"
        assert j["account"] == "flagship"
        assert j["slot"] == "D1-AM"
        assert j["persona"] == "authoritative desk"
        assert j["mode"] == "deterministic"

    def test_persona_from_account_voice(self, tmp_path):
        rows = [_valid_row(post_id="post-resb-001", impressions=200)]
        plan = _make_plan()
        result = join_provenance(rows, plan, root=tmp_path)
        j = result["joined"][0]
        assert j["persona"] == "tape reader"

    def test_mode_from_copy_mode(self, tmp_path):
        rows = [_valid_row(post_id="post-flagship-002")]
        plan = _make_plan()
        result = join_provenance(rows, plan, root=tmp_path)
        j = result["joined"][0]
        assert j["mode"] == "llm"

    def test_cashtag_tier_unknown_without_tiers_file(self, tmp_path):
        rows = [_valid_row(post_id="post-flagship-001")]
        plan = _make_plan()
        result = join_provenance(rows, plan, root=tmp_path)
        j = result["joined"][0]
        assert j["cashtag_tier"] == "unknown"

    def test_cashtag_tier_from_tiers_file(self, tmp_path):
        # Write a fixture tiers file
        tiers_dir = tmp_path / "data" / "marketing"
        tiers_dir.mkdir(parents=True, exist_ok=True)
        tiers_file = tiers_dir / "cashtag_tiers.json"
        tiers_file.write_text(json.dumps({"SBUX": "T1", "NVDA": "T2"}), encoding="utf-8")

        # The row needs a cashtag field for tier lookup
        row = _valid_row(post_id="post-flagship-001")
        row["cashtag"] = "$SBUX"
        plan = _make_plan()
        result = join_provenance([row], plan, root=tmp_path)
        j = result["joined"][0]
        assert j["cashtag_tier"] == "T1"

    def test_orphan_never_dropped(self, tmp_path):
        """Orphan rows are returned in orphans list, not silently discarded."""
        rows = [
            _valid_row(post_id="does-not-exist-1"),
            _valid_row(post_id="does-not-exist-2"),
        ]
        plan = _make_plan()
        result = join_provenance(rows, plan, root=tmp_path)
        assert len(result["orphans"]) == 2
        assert len(result["joined"]) == 0

    def test_empty_plan_all_orphans(self, tmp_path):
        rows = [_valid_row()]
        plan = {"accounts": []}
        result = join_provenance(rows, plan, root=tmp_path)
        assert len(result["orphans"]) == 1
        assert result["joined"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Rollup medians (hand-checked)
# ─────────────────────────────────────────────────────────────────────────────

class TestRollup:
    def _make_joined_rows(self) -> list[dict]:
        """4 rows: 2 'watchlist/flagship' + 2 'theme_list/flagship' to test cell split."""
        base_dims = {"kind": "watchlist", "account": "flagship", "slot": "D1-AM",
                     "persona": "authoritative desk", "mode": "deterministic", "cashtag_tier": "unknown"}
        theme_dims = {"kind": "theme_list", "account": "flagship", "slot": "D2-PM",
                      "persona": "authoritative desk", "mode": "llm", "cashtag_tier": "unknown"}
        return [
            {**base_dims, "post_id": "p1", "impressions": 100, "likes": 10,
             "replies": 2, "reposts": 1, "bookmarks": 3},
            {**base_dims, "post_id": "p2", "impressions": 200, "likes": 20,
             "replies": 4, "reposts": 2, "bookmarks": 6},
            {**theme_dims, "post_id": "p3", "impressions": 500, "likes": 50,
             "replies": 10, "reposts": 5, "bookmarks": 12},
            {**theme_dims, "post_id": "p4", "impressions": 700, "likes": 70,
             "replies": 14, "reposts": 7, "bookmarks": 18},
        ]

    def test_rollup_cell_count(self):
        rows = self._make_joined_rows()
        result = rollup(rows, [], as_of="2026-07-19")
        # 2 unique dim combinations
        assert len(result["cells"]) == 2

    def test_rollup_medians_hand_checked(self):
        """
        watchlist cell: impressions=[100,200] → median=150; likes=[10,20] → median=15
        theme_list cell: impressions=[500,700] → median=600; likes=[50,70] → median=60
        """
        rows = self._make_joined_rows()
        result = rollup(rows, [], as_of="2026-07-19")
        cells_by_kind = {c["dims"]["kind"]: c for c in result["cells"]}

        wl = cells_by_kind["watchlist"]
        assert wl["med_impressions"] == 150
        assert wl["med_likes"] == 15
        assert wl["med_replies"] == 3   # [2,4] → 3.0

        tl = cells_by_kind["theme_list"]
        assert tl["med_impressions"] == 600
        assert tl["med_likes"] == 60
        assert tl["med_replies"] == 12  # [10,14] → 12.0

    def test_n_floor_verdict_seeding(self):
        """All cells with n < 20 must carry verdict='seeding'."""
        rows = self._make_joined_rows()
        result = rollup(rows, [], as_of="2026-07-19")
        for cell in result["cells"]:
            assert cell["n"] < 20
            assert cell.get("verdict") == "seeding"

    def test_n_floor_no_verdict_at_20(self):
        """A cell with exactly 20 rows should NOT carry verdict='seeding'."""
        base_dims = {"kind": "watchlist", "account": "flagship", "slot": "D1-AM",
                     "persona": "authoritative desk", "mode": "deterministic", "cashtag_tier": "unknown"}
        rows = [
            {**base_dims, "post_id": f"p{i}", "impressions": 100, "likes": 5,
             "replies": 1, "reposts": 0, "bookmarks": 0}
            for i in range(20)
        ]
        result = rollup(rows, [], as_of="2026-07-19")
        assert len(result["cells"]) == 1
        cell = result["cells"][0]
        assert cell["n"] == 20
        assert "verdict" not in cell

    def test_top_posts_by_impressions(self):
        rows = self._make_joined_rows()
        result = rollup(rows, [], as_of="2026-07-19")
        top = result["top_posts"]
        assert len(top) == 4  # only 4 unique posts
        # First is highest impressions = 700 (p4)
        assert top[0]["post_id"] == "p4"
        assert top[0]["impressions"] == 700

    def test_top_posts_max_10(self):
        """With > 10 unique posts, only top 10 returned."""
        base_dims = {"kind": "watchlist", "account": "flagship", "slot": "D1-AM",
                     "persona": "authoritative desk", "mode": "deterministic", "cashtag_tier": "unknown"}
        rows = [
            {**base_dims, "post_id": f"post-{i:02d}", "impressions": i * 10,
             "likes": 1, "replies": 0, "reposts": 0, "bookmarks": 0}
            for i in range(15)
        ]
        result = rollup(rows, [], as_of="2026-07-19")
        assert len(result["top_posts"]) == 10

    def test_orphan_count_in_rollup(self):
        orphans = [{"post_id": "x", "orphan": True, "impressions": 5,
                    "likes": 0, "replies": 0, "reposts": 0, "bookmarks": 0}]
        result = rollup([], orphans, as_of="2026-07-19")
        assert result["n_orphans"] == 1

    def test_rollup_schema_keys(self):
        result = rollup([], [], as_of="2026-07-19")
        for key in ("schema", "produced_by", "as_of", "n_posts", "n_rows", "n_orphans",
                    "cells", "top_posts", "hypotheses"):
            assert key in result, f"missing key: {key}"

    def test_hypotheses_seeding_in_w0(self):
        result = rollup([], [], as_of="2026-07-19")
        assert len(result["hypotheses"]) >= 1
        for h in result["hypotheses"]:
            assert h["state"] == "seeding"
            assert "id" in h
            assert "title" in h
            assert "n_evidence" in h

    def test_empty_telemetry_honest_artifact(self):
        """Empty telemetry → n_posts=0, no crash, no invented numbers."""
        result = rollup([], [], as_of="2026-07-19")
        assert result["n_posts"] == 0
        assert result["n_rows"] == 0
        assert result["n_orphans"] == 0
        assert result["cells"] == []
        assert result["top_posts"] == []
        assert isinstance(result["hypotheses"], list)

    def test_as_of_default_is_today(self):
        from datetime import datetime, timezone
        result = rollup([], [])
        today = datetime.now(tz=timezone.utc).date().isoformat()
        assert result["as_of"] == today


# ─────────────────────────────────────────────────────────────────────────────
# write_rollup integration
# ─────────────────────────────────────────────────────────────────────────────

class TestWriteRollup:
    def test_write_rollup_empty_creates_valid_json(self, tmp_path):
        result = write_rollup(root=tmp_path, as_of="2026-07-19")
        assert result.get("ok") is True
        assert result["n_posts"] == 0

        out_path = tmp_path / "data" / "marketing" / "lab_rollup.json"
        assert out_path.exists()
        obj = json.loads(out_path.read_text(encoding="utf-8"))
        assert obj["schema"] == "marketing.lab_rollup/v1"
        assert obj["n_posts"] == 0

    def test_write_rollup_with_telemetry_and_plan(self, tmp_path):
        # Seed the content plan
        plan_dir = tmp_path / "data" / "marketing"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan = _make_plan()
        (plan_dir / "content_plan.json").write_text(
            json.dumps(plan), encoding="utf-8"
        )

        # Ingest two rows (one matched, one orphan)
        rows = [
            _valid_row(post_id="post-flagship-001"),
            _valid_row(post_id="orphan-xyz"),
        ]
        ingest_rows(rows, root=tmp_path)

        result = write_rollup(root=tmp_path, as_of="2026-07-19")
        assert result.get("ok") is True
        assert result["n_rows"] == 2
        assert result["n_orphans"] == 1
        assert result["n_posts"] == 1  # only 1 unique post matched

        out_path = tmp_path / "data" / "marketing" / "lab_rollup.json"
        obj = json.loads(out_path.read_text(encoding="utf-8"))
        assert obj["n_orphans"] == 1
        assert len(obj["cells"]) == 1

    def test_write_rollup_never_raises(self, tmp_path):
        """write_rollup must never raise — bad state returns error dict, no exception."""
        # Make data/marketing unwritable to trigger an error
        # Instead, pass a root that would cause issues via a broken plan file
        plan_dir = tmp_path / "data" / "marketing"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "content_plan.json").write_text("NOT JSON", encoding="utf-8")

        # Should still succeed with empty plan
        result = write_rollup(root=tmp_path, as_of="2026-07-19")
        # Either ok=True (gracefully handled) or error key — must not raise
        assert isinstance(result, dict)
        assert "ok" in result or "error" in result


# ─────────────────────────────────────────────────────────────────────────────
# Fix 1 — N-floor must count POSTs not rows (dedupe to latest capture per post)
# ─────────────────────────────────────────────────────────────────────────────

class TestRollupDedupePerPost:
    """The N-floor law governs unique posts, not telemetry rows.

    W1 recaptures the same post daily, so one post with 25 capture rows must
    yield n==1 for its cell, verdict=='seeding', and medians equal to the
    latest capture's values (X metrics are cumulative — latest = current truth).
    """

    def test_single_post_25_rows_yields_n1(self):
        """25 rows for one post_id in one cell → cell n==1, verdict='seeding'."""
        base_dims = {
            "kind": "watchlist",
            "account": "flagship",
            "slot": "D1-AM",
            "persona": "authoritative desk",
            "mode": "deterministic",
            "cashtag_tier": "unknown",
        }
        # 25 rows, all same post_id, each captured a day apart with increasing metrics
        rows = [
            {
                **base_dims,
                "post_id": "single-post-001",
                "captured_at": f"2026-07-{i + 1:02d}T10:00:00Z",
                "impressions": 100 + i * 10,  # cumulative: latest = 340
                "likes": 5 + i,               # cumulative: latest = 29
                "replies": 1,
                "reposts": 0,
                "bookmarks": 0,
            }
            for i in range(25)
        ]
        result = rollup(rows, [], as_of="2026-07-19")

        assert len(result["cells"]) == 1
        cell = result["cells"][0]

        # n must be 1 (one unique post, not 25 rows)
        assert cell["n"] == 1, (
            f"Expected n==1 (one unique post), got n=={cell['n']}"
        )

        # With n==1 < 20, verdict must be 'seeding'
        assert cell.get("verdict") == "seeding", (
            f"Expected verdict='seeding' for n==1, got {cell.get('verdict')!r}"
        )

        # Median equals the latest capture's value (day 25: impressions=340, likes=29)
        assert cell["med_impressions"] == 340, (
            f"Expected median==340 (latest capture), got {cell['med_impressions']}"
        )
        assert cell["med_likes"] == 29, (
            f"Expected med_likes==29 (latest capture), got {cell['med_likes']}"
        )

    def test_multiple_posts_deduped_correctly(self):
        """3 unique posts, each with multiple rows → n==3, medians over latest captures."""
        base_dims = {
            "kind": "signal",
            "account": "flagship",
            "slot": "D1-AM",
            "persona": "authoritative desk",
            "mode": "deterministic",
            "cashtag_tier": "unknown",
        }
        # Post A: 3 captures; latest impressions=200
        # Post B: 2 captures; latest impressions=400
        # Post C: 1 capture;  latest impressions=300
        rows = [
            {**base_dims, "post_id": "post-A", "captured_at": "2026-07-01T10:00:00Z", "impressions": 100, "likes": 5, "replies": 1, "reposts": 0, "bookmarks": 0},
            {**base_dims, "post_id": "post-A", "captured_at": "2026-07-02T10:00:00Z", "impressions": 150, "likes": 8, "replies": 2, "reposts": 0, "bookmarks": 0},
            {**base_dims, "post_id": "post-A", "captured_at": "2026-07-03T10:00:00Z", "impressions": 200, "likes": 10, "replies": 3, "reposts": 0, "bookmarks": 0},
            {**base_dims, "post_id": "post-B", "captured_at": "2026-07-01T10:00:00Z", "impressions": 300, "likes": 20, "replies": 4, "reposts": 0, "bookmarks": 0},
            {**base_dims, "post_id": "post-B", "captured_at": "2026-07-02T10:00:00Z", "impressions": 400, "likes": 25, "replies": 5, "reposts": 0, "bookmarks": 0},
            {**base_dims, "post_id": "post-C", "captured_at": "2026-07-01T10:00:00Z", "impressions": 300, "likes": 15, "replies": 2, "reposts": 0, "bookmarks": 0},
        ]
        result = rollup(rows, [], as_of="2026-07-19")
        assert len(result["cells"]) == 1
        cell = result["cells"][0]

        assert cell["n"] == 3, f"Expected n==3 unique posts, got {cell['n']}"

        # Medians over [200, 400, 300] for impressions → 300
        assert cell["med_impressions"] == 300, (
            f"Expected med_impressions==300 (median of [200,300,400]), got {cell['med_impressions']}"
        )
        # Medians over likes [10, 25, 15] → 15
        assert cell["med_likes"] == 15, (
            f"Expected med_likes==15 (median of [10,15,25]), got {cell['med_likes']}"
        )

    def test_top_posts_deduped_uses_latest_capture(self):
        """top_posts must reflect latest-capture-per-post, not a stale row."""
        base_dims = {
            "kind": "signal",
            "account": "flagship",
            "slot": "D1-AM",
            "persona": "authoritative desk",
            "mode": "deterministic",
            "cashtag_tier": "unknown",
        }
        # Post A early (low impressions) + late (high impressions); latest wins
        # Post B single capture; must not appear before A's latest
        rows = [
            {**base_dims, "post_id": "post-A", "captured_at": "2026-07-01T10:00:00Z", "impressions": 100, "likes": 1, "replies": 0, "reposts": 0, "bookmarks": 0},
            {**base_dims, "post_id": "post-A", "captured_at": "2026-07-03T10:00:00Z", "impressions": 500, "likes": 50, "replies": 0, "reposts": 0, "bookmarks": 0},
            {**base_dims, "post_id": "post-B", "captured_at": "2026-07-02T10:00:00Z", "impressions": 300, "likes": 30, "replies": 0, "reposts": 0, "bookmarks": 0},
        ]
        result = rollup(rows, [], as_of="2026-07-19")

        top = result["top_posts"]
        assert len(top) == 2
        # Post A's latest capture (500 impressions) > Post B (300)
        assert top[0]["post_id"] == "post-A"
        assert top[0]["impressions"] == 500, (
            f"Expected 500 (latest capture for post-A), got {top[0]['impressions']}"
        )
        assert top[1]["post_id"] == "post-B"
        assert top[1]["impressions"] == 300

    def test_build_post_index_warns_on_duplicate_post_id(self, caplog):
        """_build_post_index must log a warning when a post_id appears in more
        than one account's queue."""
        import logging
        from engine.marketing.telemetry import _build_post_index

        plan = {
            "accounts": [
                {
                    "id": "acct-1",
                    "voice": "voice-1",
                    "queue": [{"id": "dup-post-id", "type": "signal", "slot": "D1-AM", "_copy_mode": "deterministic"}],
                },
                {
                    "id": "acct-2",
                    "voice": "voice-2",
                    "queue": [{"id": "dup-post-id", "type": "mover", "slot": "D2-PM", "_copy_mode": "llm"}],
                },
            ]
        }

        with caplog.at_level(logging.WARNING, logger="engine.marketing.telemetry"):
            index = _build_post_index(plan)

        assert "dup-post-id" in caplog.text, (
            "Expected a warning mentioning the duplicate post_id"
        )
        # Last-write-wins: acct-2's entry should win
        assert index["dup-post-id"]["account"] == "acct-2"
        assert index["dup-post-id"]["kind"] == "mover"


# ─────────────────────────────────────────────────────────────────────────────
# Live feed — post_metrics.jsonl → derived telemetry rows (read-through)
# ─────────────────────────────────────────────────────────────────────────────

def _write_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )


def _outbox_item(
    item_id: str,
    *,
    account: str = "flagship",
    kind: str = "signal",
    slot: str = "D1-AM",
    plan_item_id: str = "post-flagship-001",
    ticker: str = "ROST",
    as_of: str = "2026-07-24",
) -> dict:
    return {
        "schema": "marketing.outbox/v1",
        "id": item_id,
        "as_of": as_of,
        "account": account,
        "kind": kind,
        "text": f"${ticker} on the tape",
        "media": [],
        "scheduled_at": f"{as_of}T14:00:00Z",
        "slot": slot,
        "priority": 5,
        "provenance": "content_studio",
        "source": {"plan_item_id": plan_item_id, "ticker": ticker},
        "status": "queued",
        "created_at": f"{as_of}T12:00:00Z",
    }


def _posted_transitions(item_id: str, remote_id: str, at: str) -> list[dict]:
    """Legal queued→approved→posted ledger walk with a Buffer receipt."""
    return [
        {"id": item_id, "from": "queued", "to": "approved", "at": at, "actor": "test"},
        {
            "id": item_id,
            "from": "approved",
            "to": "posted",
            "at": at,
            "actor": "publisher",
            "note": "published",
            "receipt": {
                "backend": "buffer",
                "external_id": remote_id,
                "external_url": None,
                "at": at,
            },
        },
    ]


def _metrics_row(
    remote_id: str,
    *,
    account: str = "flagship",
    impressions: int = 0,
    likes: int = 0,
    comments: int = 0,
    reposts: int = 0,
    clicks: int = 0,
    polled_at: str = "2026-07-25T16:00:00Z",
    metrics_updated_at: str | None = None,
) -> dict:
    return {
        "remote_id": remote_id,
        "account": account,
        "external_url": None,
        "metrics": {
            "likes": likes,
            "comments": comments,
            "engagement_rate": 0,
            "reposts": reposts,
            "impressions": impressions,
            "clicks": clicks,
        },
        "metrics_raw": [],
        "metrics_updated_at": metrics_updated_at or polled_at,
        "polled_at": polled_at,
        "ok": True,
    }


def _seed_live_root(tmp_path) -> pathlib.Path:
    """Fake repo root with outbox + post_metrics + plan wired end-to-end.

    Two posted items on DIFFERENT days that share the re-issued plan id
    post-flagship-001, one measured + one zero-impression item, plus one
    orphan metrics row with no outbox item.
    """
    root = tmp_path
    mdir = root / "data" / "marketing"
    _write_jsonl(mdir / "outbox" / "items.jsonl", [
        _outbox_item("ob-2026-07-24-aaaa", as_of="2026-07-24", kind="signal",
                     slot="D1-AM", ticker="ROST"),
        _outbox_item("ob-2026-07-25-bbbb", as_of="2026-07-25", kind="watchlist",
                     slot="D1-S1", ticker="GPI"),
        _outbox_item("ob-2026-07-25-cccc", as_of="2026-07-25", kind="chart",
                     slot="D2-PM", ticker="NVDA", plan_item_id="post-flagship-009"),
    ])
    ledger = (
        _posted_transitions("ob-2026-07-24-aaaa", "buf-aaa", "2026-07-24T14:00:01Z")
        + _posted_transitions("ob-2026-07-25-bbbb", "buf-bbb", "2026-07-25T14:00:01Z")
        + _posted_transitions("ob-2026-07-25-cccc", "buf-ccc", "2026-07-25T18:00:01Z")
    )
    _write_jsonl(mdir / "outbox" / "status_ledger.jsonl", ledger)
    _write_jsonl(mdir / "post_metrics.jsonl", [
        # buf-aaa: two polls — the later one must win (metrics are cumulative)
        _metrics_row("buf-aaa", impressions=100, likes=3, comments=1,
                     reposts=1, clicks=2, polled_at="2026-07-25T16:00:00Z"),
        _metrics_row("buf-aaa", impressions=400, likes=9, comments=4,
                     reposts=2, clicks=5, polled_at="2026-07-26T16:00:00Z"),
        # buf-bbb: measured
        _metrics_row("buf-bbb", impressions=250, likes=5, comments=2,
                     polled_at="2026-07-26T16:00:00Z"),
        # buf-ccc: polled but analytics not populated yet → unmeasured NULL
        _metrics_row("buf-ccc", impressions=0, polled_at="2026-07-26T16:00:00Z"),
        # buf-zzz: no outbox item → orphan
        _metrics_row("buf-zzz", impressions=50, likes=1,
                     polled_at="2026-07-26T16:00:00Z"),
    ])
    (mdir / "content_plan.json").write_text(json.dumps(_make_plan()), encoding="utf-8")
    return root


class TestLiveFeed:
    def test_absent_ledger_yields_empty(self, tmp_path):
        from engine.marketing.telemetry import load_live_rows

        result = load_live_rows(tmp_path, {})
        assert result == {"joined": [], "orphans": [], "n_unmeasured": 0}

    def test_metric_name_mapping(self, tmp_path):
        """Buffer names map onto the telemetry row schema: comments→replies,
        clicks→link_clicks; bookmarks (unreported by Buffer) stays absent."""
        from engine.marketing.telemetry import load_live_rows

        root = _seed_live_root(tmp_path)
        result = load_live_rows(root)
        by_id = {r["post_id"]: r for r in result["joined"]}
        row = by_id["ob-2026-07-24-aaaa"]
        assert row["impressions"] == 400
        assert row["likes"] == 9
        assert row["replies"] == 4      # Buffer "comments"
        assert row["reposts"] == 2
        assert row["link_clicks"] == 5  # Buffer "clicks"
        assert "bookmarks" not in row   # unmeasured, not fabricated as 0

    def test_latest_poll_wins(self, tmp_path):
        """Metrics are cumulative — the newest poll per remote_id is the truth."""
        from engine.marketing.telemetry import load_live_rows

        root = _seed_live_root(tmp_path)
        result = load_live_rows(root)
        rows = [r for r in result["joined"] if r["remote_id"] == "buf-aaa"]
        assert len(rows) == 1
        assert rows[0]["impressions"] == 400

    def test_zero_impressions_is_null_not_zero(self, tmp_path):
        """A polled post with 0 impressions is unmeasured: excluded from
        evidence and counted, never folded in as a zero."""
        from engine.marketing.telemetry import load_live_rows

        root = _seed_live_root(tmp_path)
        result = load_live_rows(root)
        assert result["n_unmeasured"] == 1
        joined_ids = {r["post_id"] for r in result["joined"]}
        assert "ob-2026-07-25-cccc" not in joined_ids

    def test_orphan_metrics_row_kept(self, tmp_path):
        """A metrics row with no outbox item is an orphan — kept, flagged,
        never dropped."""
        from engine.marketing.telemetry import load_live_rows

        root = _seed_live_root(tmp_path)
        result = load_live_rows(root)
        assert len(result["orphans"]) == 1
        orphan = result["orphans"][0]
        assert orphan["post_id"] == "buf-zzz"
        assert orphan["orphan"] is True

    def test_dims_from_outbox_not_current_plan(self, tmp_path):
        """Dims come from the outbox item (actuation truth). The current plan
        re-issues queue ids nightly, so it cannot attribute past posts:
        ob-2026-07-24-aaaa seeded from plan id post-flagship-001 must keep its
        own kind=signal/slot=D1-AM even though today's plan reuses that id for
        a different post (watchlist / D1-AM in the fixture plan)."""
        from engine.marketing.telemetry import load_live_rows

        root = _seed_live_root(tmp_path)
        result = load_live_rows(root)
        by_id = {r["post_id"]: r for r in result["joined"]}

        row = by_id["ob-2026-07-24-aaaa"]
        assert row["kind"] == "signal"
        assert row["slot"] == "D1-AM"
        assert row["account"] == "flagship"
        assert row["persona"] == "authoritative desk"  # account→voice registry
        assert row["mode"] == "unknown"  # copy mode not recorded on outbox items
        assert row["plan_item_id"] == "post-flagship-001"
        assert row["cashtag"] == "$ROST"

    def test_plan_id_collision_does_not_collapse(self, tmp_path):
        """Two posts on different days sharing a re-issued plan id must stay
        two posts — post_id is the outbox item id, not the plan id."""
        from engine.marketing.telemetry import load_live_rows, rollup

        root = _seed_live_root(tmp_path)
        result = load_live_rows(root)
        shared = [r for r in result["joined"]
                  if r["plan_item_id"] == "post-flagship-001"]
        assert len(shared) == 2
        assert len({r["post_id"] for r in shared}) == 2

        art = rollup(result["joined"], result["orphans"], as_of="2026-07-26")
        assert art["n_posts"] == 2

    def test_cashtag_tier_lookup(self, tmp_path):
        from engine.marketing.telemetry import load_live_rows

        root = _seed_live_root(tmp_path)
        (root / "data" / "marketing" / "cashtag_tiers.json").write_text(
            json.dumps({"ROST": "t2"}), encoding="utf-8"
        )
        result = load_live_rows(root)
        by_id = {r["post_id"]: r for r in result["joined"]}
        assert by_id["ob-2026-07-24-aaaa"]["cashtag_tier"] == "t2"
        assert by_id["ob-2026-07-25-bbbb"]["cashtag_tier"] == "unknown"

    def test_malformed_ledger_line_skipped(self, tmp_path):
        from engine.marketing.telemetry import load_live_rows

        root = _seed_live_root(tmp_path)
        pm = root / "data" / "marketing" / "post_metrics.jsonl"
        pm.write_text(pm.read_text(encoding="utf-8") + "NOT JSON\n", encoding="utf-8")
        result = load_live_rows(root)
        assert len(result["joined"]) == 2  # unaffected by the bad line


class TestWriteRollupLiveFeed:
    def test_end_to_end_live_bridge(self, tmp_path):
        """write_rollup on a live-seeded root: the Lab accrues real evidence —
        n_posts > 0 — with the null and the orphan disclosed, not hidden."""
        root = _seed_live_root(tmp_path)
        result = write_rollup(root=root, as_of="2026-07-26")
        assert result.get("ok") is True
        assert result["n_posts"] == 2       # measured live posts
        assert result["n_orphans"] == 1     # buf-zzz
        assert result["n_unmeasured"] == 1  # buf-ccc, disclosed

        obj = json.loads(
            (root / "data" / "marketing" / "lab_rollup.json").read_text(encoding="utf-8")
        )
        assert obj["n_posts"] == 2
        assert obj["n_unmeasured"] == 1
        # N-floor law unchanged: 2 posts is far below 20 → every cell seeding
        assert obj["cells"], "expected live cells"
        for cell in obj["cells"]:
            assert cell["verdict"] == "seeding"
        # The unmeasured post must not appear as a zero anywhere
        for cell in obj["cells"]:
            assert cell["med_impressions"] > 0
        top_ids = {p["post_id"] for p in obj["top_posts"]}
        assert "ob-2026-07-25-cccc" not in top_ids

    def test_store_and_live_feeds_merge(self, tmp_path):
        """The manual/test-fed monthly store still contributes alongside the
        live feed (store rows join via the plan, live rows via the outbox)."""
        root = _seed_live_root(tmp_path)
        ingest_rows(
            [_valid_row(post_id="post-flagship-002",
                        captured_at="2026-07-26T10:00:00Z")],
            root=root,
        )
        result = write_rollup(root=root, as_of="2026-07-26")
        assert result.get("ok") is True
        assert result["n_posts"] == 3  # 2 live + 1 store

    def test_live_only_root_without_plan(self, tmp_path):
        """No content_plan.json: live rows still accrue (persona falls back to
        empty string); nothing raises."""
        root = _seed_live_root(tmp_path)
        (root / "data" / "marketing" / "content_plan.json").unlink()
        result = write_rollup(root=root, as_of="2026-07-26")
        assert result.get("ok") is True
        assert result["n_posts"] == 2
