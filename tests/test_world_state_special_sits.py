"""tests/test_world_state_special_sits.py — SS-NW-W1 Neural Web wiring tests.

Coverage
--------
1.  _compose_special_situations returns None when artifact absent
2.  _compose_special_situations parses a fixture artifact correctly
3.  world_state.special_situations present and has display_only=True (fixture)
4.  brief_context block drops cleanly when special_situations is None
5.  brief_context block composes when world_state has special_situations
6.  ask_brain tool read_special_situations returns available=False when absent
7.  ask_brain tool read_special_situations returns available=True on fixture
8.  ask_brain tool ticker filter returns ticker_view on fixture
9.  ask_brain tool category filter returns filtered setups_display
10. ask_brain tool min_grade filter respects grade floor
11. read_special_situations in _ASK_READ_TOOLS whitelist
12. cortex _tool_schemas includes read_special_situations schema
13. read_special_situations NOT in _WRITE_TOOLS
14. mastermind _summarize_special_sits returns empty lobe + gap when absent
15. mastermind _summarize_special_sits parses fixture correctly
16. mastermind _LOBE_TO_ARTIFACT_IDS has special_sits entry
17. banned-words — 'validated' not in any tool response (fixture)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def _make_context_fixture(root: Path) -> dict:
    """Write minimal data/special_situations/context/latest.json fixture."""
    payload = {
        "schema": "special_sits_context.v1",
        "asof": "2026-07-18",
        "built": "2026-07-18T07:00:00Z",
        "is_context_only": True,
        "disclaimer": "Context only — event tracking + display-tier setup ranking, never a signal or sizing input.",
        "counts": {
            "total": 12,
            "new_today": 2,
            "grade_a": 3,
            "grade_b": 4,
            "with_arb": 2,
            "cross_border": 1,
        },
        "top_setups": [
            {
                "ticker": "ACME",
                "company": "Acme Corp",
                "category": "M&A",
                "stage": "announced",
                "grade": "A",
                "score": 80.0,
                "tier": "T2",
                "mc_musd": 5000.0,
                "date_filed": "2026-07-10",
                "why": ["Strong prior", "T2 tier"],
                "why_zh": ["强历史胜率", "T2层级"],
            },
            {
                "ticker": "BETA",
                "company": "Beta Inc",
                "category": "Spin-off",
                "stage": "pending",
                "grade": "B",
                "score": 62.0,
                "tier": "T3",
                "mc_musd": 1500.0,
                "date_filed": "2026-07-12",
                "why": ["Sector constructive"],
                "why_zh": ["行业积极"],
            },
        ],
        "changes": {
            "items": [
                {"kind": "new", "ticker": "GAMA", "category": "Activist", "from": None, "to": "watch"},
                {"kind": "grade_up", "ticker": "ACME", "category": "M&A", "from": "B", "to": "A"},
            ],
            "n": 2,
        },
        "prev_state": {
            "asof": "2026-07-17",
            "by_key": {
                "ACME|M&A": {"stage": "announced", "grade": "B"},
            },
        },
        "risk_arb_top": [
            {
                "ticker": "ACME",
                "company": "Acme Corp",
                "gross_spread_pct": 3.2,
                "annualized_pct": 18.5,
                "days_to_close": 60,
            }
        ],
    }
    _write_json(root / "data" / "special_situations" / "context" / "latest.json", payload)
    return payload


def _make_site_fixture(root: Path) -> dict:
    """Write minimal site/allocationdata/special_situations.json fixture."""
    payload = {
        "schema": "special_situations.v2",
        "generated_at": "2026-07-18T07:00:00Z",
        "is_context_only": True,
        "disclaimer": "Context only.",
        "n": 2,
        "by_ticker": {
            "ACME": {
                "ticker": "ACME",
                "company": "Acme Corp",
                "category": "M&A",
                "stage": "announced",
                "date": "2026-07-10",
                "country": "US",
                "cross_border": False,
                "source": "edgar",
                "confidence": "high",
                "brief": "Announced acquisition by XYZ.",
                "mc_musd": 5000.0,
                "prior": {"win_20d_pct": 65.0, "med_ret_20d_pct": 2.1},
            },
        },
        "risk_arb": [],
        "activist_filers": [],
    }
    _write_json(root / "site" / "allocationdata" / "special_situations.json", payload)
    return payload


# ---------------------------------------------------------------------------
# 1-2: _compose_special_situations
# ---------------------------------------------------------------------------

class TestComposeSpecialSituations:
    """Tests for engine.neuralweb.world_state._compose_special_situations."""

    def test_returns_none_when_absent(self, tmp_path):
        """Returns None when artifact file is absent."""
        from engine.neuralweb.world_state import _compose_special_situations
        result = _compose_special_situations(root=tmp_path)
        assert result is None

    def test_parses_fixture_correctly(self, tmp_path):
        """Parses fixture artifact and returns expected structure."""
        from engine.neuralweb.world_state import _compose_special_situations
        _make_context_fixture(tmp_path)
        result = _compose_special_situations(root=tmp_path)
        assert result is not None
        assert result["asof"] == "2026-07-18"
        assert result["display_only"] is True
        assert "counts" in result
        assert result["counts"]["total"] == 12
        # setups_display capped at 6, trimmed to required keys
        setups = result["setups_display"]
        assert isinstance(setups, list)
        assert len(setups) == 2
        assert setups[0]["ticker"] == "ACME"
        assert setups[0]["grade"] == "A"
        assert "score" in setups[0]
        assert "why" in setups[0]
        # changes capped at 8
        changes = result["changes"]
        assert isinstance(changes, list)
        assert len(changes) == 2
        # risk_arb_top capped at 3
        arb = result["risk_arb_top"]
        assert isinstance(arb, list)
        assert arb[0]["ticker"] == "ACME"


# ---------------------------------------------------------------------------
# 3: world_state integration
# ---------------------------------------------------------------------------

class TestWorldStateSpecialSituations:
    """Tests for special_situations in world_state payload."""

    def test_special_situations_key_present_with_fixture(self, tmp_path):
        """world_state payload contains special_situations when artifact present."""
        from engine.neuralweb.world_state import _compose_special_situations
        _make_context_fixture(tmp_path)
        block = _compose_special_situations(root=tmp_path)
        # Key should be non-None and have display_only=True
        assert block is not None
        assert block.get("display_only") is True

    def test_special_situations_none_when_absent(self, tmp_path):
        """_compose_special_situations returns None when file absent."""
        from engine.neuralweb.world_state import _compose_special_situations
        result = _compose_special_situations(root=tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# 4-5: brief_context block
# ---------------------------------------------------------------------------

class TestBriefContextSpecialSituations:
    """Tests for _block_special_situations in brief_context.py."""

    def test_block_drops_cleanly_when_none(self):
        """_block_special_situations returns None when ws.special_situations is None."""
        from engine.neuralweb.brief_context import _block_special_situations
        result = _block_special_situations(None)
        assert result is None

    def test_block_drops_when_special_situations_absent(self):
        """_block_special_situations returns None when key missing from ws."""
        from engine.neuralweb.brief_context import _block_special_situations
        result = _block_special_situations({"market": {}, "special_situations": None})
        assert result is None

    def test_block_composes_with_fixture(self, tmp_path):
        """_block_special_situations produces compact block from fixture data."""
        from engine.neuralweb.brief_context import _block_special_situations
        from engine.neuralweb.world_state import _compose_special_situations
        _make_context_fixture(tmp_path)
        ss_block = _compose_special_situations(root=tmp_path)
        ws = {"special_situations": ss_block}
        result = _block_special_situations(ws)
        assert result is not None
        assert result["display_only"] is True
        assert result["is_context_only"] is True
        assert result["_tape_family"] == "special_situations"
        assert "setups_display" in result
        assert len(result["setups_display"]) <= 4
        assert "honesty_note" in result
        # Must not contain the word 'validated'
        dumped = json.dumps(result)
        assert "validated" not in dumped.lower()


# ---------------------------------------------------------------------------
# 6-10: ask_brain tool
# ---------------------------------------------------------------------------

class TestAskBrainSpecialSituations:
    """Tests for _tool_read_special_situations in ask_brain.py."""

    def test_returns_available_false_when_absent(self, tmp_path):
        """Returns available=False when context artifact absent."""
        from engine.neuralweb.ask_brain import _tool_read_special_situations
        result = _tool_read_special_situations(tmp_path, {})
        assert result.get("available") is False
        assert result.get("is_context_only") is True
        assert result.get("display_only") is True
        assert "note" in result

    def test_returns_available_true_on_fixture(self, tmp_path):
        """Returns available=True when context artifact present."""
        from engine.neuralweb.ask_brain import _tool_read_special_situations
        _make_context_fixture(tmp_path)
        result = _tool_read_special_situations(tmp_path, {})
        assert result.get("available") is True
        assert result.get("is_context_only") is True
        assert result.get("display_only") is True
        assert "setups_display" in result
        assert "counts" in result

    def test_ticker_filter_returns_ticker_view(self, tmp_path):
        """With ticker param, returns ticker_view from site fixture."""
        from engine.neuralweb.ask_brain import _tool_read_special_situations
        _make_context_fixture(tmp_path)
        _make_site_fixture(tmp_path)
        result = _tool_read_special_situations(tmp_path, {"ticker": "ACME"})
        assert result.get("available") is True
        assert "ticker_view" in result
        tv = result["ticker_view"]
        assert tv is not None
        assert tv.get("ticker") == "ACME"

    def test_ticker_filter_unknown_ticker(self, tmp_path):
        """With unknown ticker, ticker_view.found=False."""
        from engine.neuralweb.ask_brain import _tool_read_special_situations
        _make_context_fixture(tmp_path)
        _make_site_fixture(tmp_path)
        result = _tool_read_special_situations(tmp_path, {"ticker": "ZZZZ"})
        assert result.get("available") is True
        assert result["ticker_view"].get("found") is False

    def test_category_filter(self, tmp_path):
        """Category filter restricts setups_display to matching category."""
        from engine.neuralweb.ask_brain import _tool_read_special_situations
        _make_context_fixture(tmp_path)
        result = _tool_read_special_situations(tmp_path, {"category": "M&A"})
        assert result.get("available") is True
        for s in result.get("setups_display", []):
            assert s.get("category") == "M&A"

    def test_min_grade_filter(self, tmp_path):
        """min_grade='A' restricts setups_display to grade A only."""
        from engine.neuralweb.ask_brain import _tool_read_special_situations
        _make_context_fixture(tmp_path)
        result = _tool_read_special_situations(tmp_path, {"min_grade": "A"})
        assert result.get("available") is True
        for s in result.get("setups_display", []):
            assert s.get("grade") == "A"

    def test_no_validated_in_response(self, tmp_path):
        """Response payload must not contain the word 'validated'."""
        from engine.neuralweb.ask_brain import _tool_read_special_situations
        _make_context_fixture(tmp_path)
        result = _tool_read_special_situations(tmp_path, {})
        dumped = json.dumps(result)
        assert "validated" not in dumped.lower()


# ---------------------------------------------------------------------------
# 11: whitelist
# ---------------------------------------------------------------------------

class TestWhitelist:
    def test_read_special_situations_in_ask_read_tools(self):
        """read_special_situations must be in _ASK_READ_TOOLS."""
        from engine.neuralweb.ask_brain import _ASK_READ_TOOLS
        assert "read_special_situations" in _ASK_READ_TOOLS

    def test_read_special_situations_not_in_write_tools(self):
        """read_special_situations must not be in cortex _WRITE_TOOLS."""
        from engine.neuralweb.cortex import _WRITE_TOOLS
        assert "read_special_situations" not in _WRITE_TOOLS


# ---------------------------------------------------------------------------
# 12-13: cortex schema
# ---------------------------------------------------------------------------

class TestCortexSchema:
    def test_read_special_situations_in_tool_schemas(self):
        """read_special_situations appears in cortex _tool_schemas()."""
        from engine.neuralweb.cortex import _tool_schemas
        names = {s["name"] for s in _tool_schemas()}
        assert "read_special_situations" in names

    def test_schema_has_optional_params(self):
        """Schema exposes ticker, category, min_grade as optional params."""
        from engine.neuralweb.cortex import _tool_schemas
        schema_entry = next(s for s in _tool_schemas() if s["name"] == "read_special_situations")
        props = schema_entry["input_schema"]["properties"]
        assert "ticker" in props
        assert "category" in props
        assert "min_grade" in props
        assert schema_entry["input_schema"]["required"] == []


# ---------------------------------------------------------------------------
# 14-16: mastermind summarizer
# ---------------------------------------------------------------------------

class TestMastermindSpecialSits:
    def test_summarize_returns_empty_lobe_and_gap_when_absent(self, tmp_path):
        """_summarize_special_sits returns empty lobe + gap note when absent."""
        from engine.neuralweb.mastermind_context import _summarize_special_sits
        lobe, gap = _summarize_special_sits(tmp_path)
        assert isinstance(lobe, dict)
        assert lobe == {} or not lobe.get("asof")
        assert gap is not None
        assert "absent" in gap.lower() or "unreadable" in gap.lower()

    def test_summarize_parses_fixture(self, tmp_path):
        """_summarize_special_sits parses fixture and returns expected keys."""
        from engine.neuralweb.mastermind_context import _summarize_special_sits
        _make_context_fixture(tmp_path)
        lobe, gap = _summarize_special_sits(tmp_path)
        assert gap is None
        assert lobe.get("is_context_only") is True
        assert lobe.get("display_only") is True
        assert lobe.get("asof") == "2026-07-18"
        assert lobe.get("n_total") == 12
        assert lobe.get("n_grade_a") == 3
        assert isinstance(lobe.get("setups_display"), list)
        assert len(lobe["setups_display"]) == 2

    def test_lobe_to_artifact_ids_has_special_sits(self):
        """_LOBE_TO_ARTIFACT_IDS must include 'special_sits' entry."""
        from engine.neuralweb.mastermind_context import _LOBE_TO_ARTIFACT_IDS
        assert "special_sits" in _LOBE_TO_ARTIFACT_IDS
        assert "special-sits-context-latest" in _LOBE_TO_ARTIFACT_IDS["special_sits"]
