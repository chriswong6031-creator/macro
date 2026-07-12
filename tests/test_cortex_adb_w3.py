"""ADB-W3 tests for engine.neuralweb.cortex two-way read tools.

Three suites:
  A. Full 3-way whitelist-parity test — every _READ_TOOLS name has exactly one
     schema in _tool_schemas() AND dispatches without 'unknown tool' error; every
     schema name is in the whitelist.  Enumerates dynamically so future drift fails.
  B. Happy-path and absent-path fixtures for read_master_brain_theses and
     read_master_brain_brief — caps, is_context_only, recency ordering, {absent:true}.
  C. Loop-benignity (ADB-R6) — both new tools are in _READ_TOOLS and NOT in the
     write-tool set; write-tool set is exactly its current 3 members.

ALL TESTS ARE OFFLINE — no API calls, no paid spend.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW_STR = "2026-07-12T10:00:00Z"
_PROBATION: dict = {"status": "shadow", "n": 0, "hits": 0}


def _make_minimal_repo(tmp: Path) -> Path:
    """Create the directory skeleton needed by cortex tool implementations."""
    (tmp / "data" / "neuralweb" / "cortex").mkdir(parents=True)
    (tmp / "data" / "reflexes" / "cortex_attention").mkdir(parents=True)
    (tmp / "data" / "regime").mkdir(parents=True)
    (tmp / "data" / "master_brain").mkdir(parents=True)
    (tmp / "site" / "neuralweb").mkdir(parents=True)
    (tmp / "config").mkdir(parents=True)
    # world_state.json — required by dispatch_tool for read_world_state
    ws = {
        "schema": "neuralweb.world_state.v1",
        "as_of": "2026-07-12",
        "verdict": "RISK-OFF",
        "contradictions": [],
    }
    (tmp / "data" / "neuralweb" / "world_state.json").write_text(
        json.dumps(ws), encoding="utf-8"
    )
    return tmp


@pytest.fixture
def repo(tmp_path):
    return _make_minimal_repo(tmp_path)


@pytest.fixture
def mb_repo(tmp_path):
    """Repo with master_brain fixture data for happy-path tests."""
    root = _make_minimal_repo(tmp_path)

    # theses.jsonl — 25 rows so we can verify the <=20 cap and recency order
    theses_path = root / "data" / "master_brain" / "theses.jsonl"
    rows = []
    for i in range(25):
        rows.append({"thesis_id": f"T{i:03d}", "filed_at": f"2026-07-{i+1:02d}T00:00:00Z",
                     "claim": f"claim {i}", "status": "open"})
    theses_path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    # track_record.json
    tr = {
        "scored_total": 5,
        "hit_rate": 0.6,
        "calibration_note": "too few graded calls yet",
        "as_of": "2026-07-12",
        "extra_field_should_be_excluded": True,
    }
    (root / "data" / "master_brain" / "track_record.json").write_text(
        json.dumps(tr), encoding="utf-8"
    )

    # site briefs
    for fname in ("master_brief.json", "china_brief.json", "btc_brief.json"):
        brief = {
            "summary": f"summary for {fname}",
            "regime_read": "neutral",
            "conflicts": [],
            "rotation_check": "none",
            "transmission": "clear",
            "watch_items": ["item1"],
            "confidence": "medium",
            "theses": [],
            "generated_at": "2026-07-12T06:00:00Z",
            "state_asof": "2026-07-12",
            "should_not_appear": "excluded",
        }
        (root / "site" / fname).write_text(json.dumps(brief), encoding="utf-8")

    return root


# ---------------------------------------------------------------------------
# Suite A — Full 3-way whitelist parity (ADB-W3 new requirement)
# ---------------------------------------------------------------------------

class TestFullWhitelistParity:
    """Every _READ_TOOLS name has exactly one schema AND dispatches without error.
    Every schema name is whitelisted.  Enumerates dynamically."""

    def test_every_read_tool_has_exactly_one_schema(self):
        """_READ_TOOLS names must each appear exactly once in _tool_schemas()."""
        from engine.neuralweb.cortex import _READ_TOOLS, _tool_schemas

        schemas = _tool_schemas()
        schema_names = [s["name"] for s in schemas]

        for tool_name in _READ_TOOLS:
            count = schema_names.count(tool_name)
            assert count == 1, (
                f"read tool {tool_name!r} appears {count} times in _tool_schemas() "
                f"(expected exactly 1)"
            )

    def test_every_write_tool_has_exactly_one_schema(self):
        """_WRITE_TOOLS names must each appear exactly once in _tool_schemas()."""
        from engine.neuralweb.cortex import _WRITE_TOOLS, _tool_schemas

        schemas = _tool_schemas()
        schema_names = [s["name"] for s in schemas]

        for tool_name in _WRITE_TOOLS:
            count = schema_names.count(tool_name)
            assert count == 1, (
                f"write tool {tool_name!r} appears {count} times in _tool_schemas() "
                f"(expected exactly 1)"
            )

    def test_every_schema_name_is_in_allowed_tools(self):
        """Every name returned by _tool_schemas() must be in _ALLOWED_TOOLS."""
        from engine.neuralweb.cortex import _ALLOWED_TOOLS, _tool_schemas

        for schema in _tool_schemas():
            name = schema["name"]
            assert name in _ALLOWED_TOOLS, (
                f"schema {name!r} is not in _ALLOWED_TOOLS — parity drift"
            )

    def test_every_read_tool_dispatches_without_whitelist_error(self, repo):
        """Every _READ_TOOLS name must reach a handler (no whitelist refusal and no
        forgotten-dispatch-branch: checks 'unhandled', 'unknown tool', 'not allowed')."""
        from engine.neuralweb.cortex import _READ_TOOLS, dispatch_tool

        # Tools that need specific params to not crash on path resolution
        _PARAM_OVERRIDES = {
            "read_artifact": {"path": "data/neuralweb/world_state.json"},
            "query_spine": {"query": "test"},
            "explain_options_context": {"ticker": "AAPL"},
        }

        # ALL dispatcher-origin error substrings that indicate a tool was not routed
        _DISPATCHER_ERROR_SUBSTRINGS = ("not allowed", "unknown tool", "unhandled")

        census: dict = {}
        for tool_name in _READ_TOOLS:
            params = _PARAM_OVERRIDES.get(tool_name, {})
            result = dispatch_tool(
                tool_name, params, repo, _NOW_STR, _PROBATION, census
            )
            error_msg = str(result.get("error", "")).lower()
            for bad in _DISPATCHER_ERROR_SUBSTRINGS:
                assert bad not in error_msg, (
                    f"read tool {tool_name!r} returned dispatcher error containing "
                    f"{bad!r} — registration missing from _ALLOWED_TOOLS or "
                    f"dispatch_tool has an unrouted branch"
                )

    def test_no_duplicate_schema_names(self):
        """_tool_schemas() must not contain duplicate names."""
        from engine.neuralweb.cortex import _tool_schemas

        names = [s["name"] for s in _tool_schemas()]
        seen = set()
        for n in names:
            assert n not in seen, f"duplicate schema name: {n!r}"
            seen.add(n)

    def test_prompt_read_count_matches_read_tools(self):
        """The 'READ (N)' count advertised in the deliberation system prompt must equal
        len(_READ_TOOLS).  Fails loudly if someone adds a tool without updating the prompt
        or vice-versa (prompt drift guard)."""
        import re
        import inspect
        from engine.neuralweb.cortex import _READ_TOOLS

        # Import the module to get the source with the prompt constant
        import engine.neuralweb.cortex as _cortex_mod
        source = inspect.getsource(_cortex_mod)

        match = re.search(r"READ\s*\((\d+)\)", source)
        assert match is not None, (
            "Could not find 'READ (N)' pattern in cortex.py — prompt format changed"
        )
        advertised = int(match.group(1))
        actual = len(_READ_TOOLS)
        assert advertised == actual, (
            f"Prompt says 'READ ({advertised})' but _READ_TOOLS has {actual} entries — "
            f"update the READ count in the deliberation system prompt to match"
        )


# ---------------------------------------------------------------------------
# Suite B — Happy-path and absent-path for the two new tools
# ---------------------------------------------------------------------------

class TestReadMasterBrainTheses:

    def test_happy_path_recency_order_and_cap(self, mb_repo):
        """Returns at most 20 rows, most recent first, with is_context_only."""
        from engine.neuralweb.cortex import _tool_read_master_brain_theses

        result = _tool_read_master_brain_theses(mb_repo, {})

        assert result["is_context_only"] is True
        assert result["display_only"] is True
        theses = result["theses"]
        # Cap enforced
        assert len(theses) <= 20
        # Recency: the fixture has rows T000..T024; after reverse the last written
        # (T024, filed 2026-07-25) should be first
        assert theses[0]["thesis_id"] == "T024"
        assert theses[-1]["thesis_id"] == "T005"  # 25 rows, top 20 → T005..T024

    def test_track_record_summary_fields(self, mb_repo):
        """track_record_summary contains the expected compact fields only."""
        from engine.neuralweb.cortex import _tool_read_master_brain_theses

        result = _tool_read_master_brain_theses(mb_repo, {})
        tr = result["track_record_summary"]
        assert tr is not None
        assert "scored_total" in tr
        assert "hit_rate" in tr
        assert "calibration_note" in tr
        # Excluded field must not appear
        assert "extra_field_should_be_excluded" not in tr

    def test_payload_within_50kb(self, mb_repo):
        """Total serialised response must be within the 50 KB cap."""
        from engine.neuralweb.cortex import _tool_read_master_brain_theses

        result = _tool_read_master_brain_theses(mb_repo, {})
        payload_bytes = len(json.dumps(result, ensure_ascii=False).encode())
        assert payload_bytes <= 50 * 1024, (
            f"payload {payload_bytes} bytes exceeds 50 KB cap"
        )

    def test_absent_theses_file_returns_absent_marker(self, repo):
        """Missing theses.jsonl produces absent marker, not an exception."""
        from engine.neuralweb.cortex import _tool_read_master_brain_theses

        result = _tool_read_master_brain_theses(repo, {})
        # No exception; absent marker present
        assert result.get("theses_absent") is True or len(result.get("gaps", [])) > 0
        assert result["is_context_only"] is True

    def test_absent_track_record_returns_absent_marker(self, repo):
        """Missing track_record.json produces absent marker, not an exception."""
        from engine.neuralweb.cortex import _tool_read_master_brain_theses

        result = _tool_read_master_brain_theses(repo, {})
        assert result.get("track_record_absent") is True or any(
            "track_record" in g for g in result.get("gaps", [])
        )

    def test_both_files_absent_no_exception(self, repo):
        """When both files are missing, returns structured result, never raises."""
        from engine.neuralweb.cortex import _tool_read_master_brain_theses

        # repo fixture has no master_brain data files
        result = _tool_read_master_brain_theses(repo, {})
        assert isinstance(result, dict)
        assert "error" not in result or result.get("is_context_only") is True


class TestReadMasterBrainBrief:

    def test_happy_path_content_fields_only(self, mb_repo):
        """Returns only the specified content fields, not extra fields."""
        from engine.neuralweb.cortex import _tool_read_master_brain_brief

        result = _tool_read_master_brain_brief(mb_repo, {})

        assert result["is_context_only"] is True
        assert result["display_only"] is True

        _EXPECTED = {
            "summary", "regime_read", "conflicts", "rotation_check",
            "transmission", "watch_items", "confidence", "theses",
            "generated_at", "state_asof",
        }
        for brief_key in ("macro_brief", "china_brief", "btc_brief"):
            brief = result[brief_key]
            assert isinstance(brief, dict)
            assert "absent" not in brief, f"{brief_key} unexpectedly absent"
            # Only whitelisted fields
            for k in brief:
                assert k in _EXPECTED, (
                    f"{brief_key}: unexpected field {k!r} — excluded fields leaked"
                )
            # Required content field present
            assert "summary" in brief

    def test_payload_within_50kb(self, mb_repo):
        """Total serialised response must be within the 50 KB cap."""
        from engine.neuralweb.cortex import _tool_read_master_brain_brief

        result = _tool_read_master_brain_brief(mb_repo, {})
        payload_bytes = len(json.dumps(result, ensure_ascii=False).encode())
        assert payload_bytes <= 50 * 1024, (
            f"payload {payload_bytes} bytes exceeds 50 KB cap"
        )

    def test_absent_brief_returns_absent_dict(self, repo):
        """When site brief files are missing, each key returns {absent: true}."""
        from engine.neuralweb.cortex import _tool_read_master_brain_brief

        result = _tool_read_master_brain_brief(repo, {})
        assert isinstance(result, dict)
        assert result["is_context_only"] is True
        # All three briefs absent
        for brief_key in ("macro_brief", "china_brief", "btc_brief"):
            val = result[brief_key]
            assert isinstance(val, dict)
            assert val.get("absent") is True, (
                f"{brief_key}: expected {{absent: true}}, got {val!r}"
            )

    def test_partial_absence_no_exception(self, mb_repo):
        """Removing one brief file degrades gracefully for that brief only."""
        from engine.neuralweb.cortex import _tool_read_master_brain_brief

        (mb_repo / "site" / "btc_brief.json").unlink()
        result = _tool_read_master_brain_brief(mb_repo, {})

        assert result["btc_brief"].get("absent") is True
        # Other briefs still present
        assert "summary" in result["macro_brief"]
        assert "summary" in result["china_brief"]


# ---------------------------------------------------------------------------
# Suite C — Loop benignity (ADB-R6)
# ---------------------------------------------------------------------------

class TestLoopBenignity:

    def test_new_tools_in_read_tools_not_write_tools(self):
        """read_master_brain_theses and read_master_brain_brief must be in
        _READ_TOOLS and NOT in _WRITE_TOOLS."""
        from engine.neuralweb.cortex import _READ_TOOLS, _WRITE_TOOLS

        for name in ("read_master_brain_theses", "read_master_brain_brief"):
            assert name in _READ_TOOLS, (
                f"{name!r} must be registered in _READ_TOOLS"
            )
            assert name not in _WRITE_TOOLS, (
                f"{name!r} must NOT be in _WRITE_TOOLS"
            )

    def test_write_tool_set_is_exactly_three_members(self):
        """_WRITE_TOOLS must remain exactly {flag_attention, write_memo, stake_hypothesis}.
        Any addition or removal must be a deliberate decision that fails this test."""
        from engine.neuralweb.cortex import _WRITE_TOOLS

        expected = frozenset({"flag_attention", "write_memo", "stake_hypothesis"})
        assert _WRITE_TOOLS == expected, (
            f"_WRITE_TOOLS changed unexpectedly. "
            f"Expected {sorted(expected)}, got {sorted(_WRITE_TOOLS)}"
        )

    def test_new_tools_carry_is_context_only(self, mb_repo):
        """Both new tools must carry is_context_only=True in their return payloads."""
        from engine.neuralweb.cortex import (
            _tool_read_master_brain_theses,
            _tool_read_master_brain_brief,
        )

        r1 = _tool_read_master_brain_theses(mb_repo, {})
        assert r1.get("is_context_only") is True, (
            "read_master_brain_theses did not return is_context_only=True"
        )

        r2 = _tool_read_master_brain_brief(mb_repo, {})
        assert r2.get("is_context_only") is True, (
            "read_master_brain_brief did not return is_context_only=True"
        )

    def test_new_tools_not_in_article2_surfaces(self):
        """New tools must not touch alert_triage, board_ordering, top_setups,
        attention_queue, or push_floor.  Verified by source grep."""
        import inspect
        from engine.neuralweb import cortex

        src_theses = inspect.getsource(cortex._tool_read_master_brain_theses)
        src_brief = inspect.getsource(cortex._tool_read_master_brain_brief)
        banned = [
            "alert_triage", "board_ordering", "top_setups",
            "attention_queue", "push_floor",
        ]
        for term in banned:
            assert term not in src_theses, (
                f"read_master_brain_theses touches banned surface: {term!r}"
            )
            assert term not in src_brief, (
                f"read_master_brain_brief touches banned surface: {term!r}"
            )
