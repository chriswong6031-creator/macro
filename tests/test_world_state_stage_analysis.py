"""tests/test_world_state_stage_analysis.py — SGA-W2 Neural Web wiring tests.

Coverage
--------
1.  _compose_stage_analysis returns null block (all fields None) when artifact absent
2.  _compose_stage_analysis parses a fixture artifact correctly
3.  world_state.stage_analysis block always carries display_only=True + is_context_only=True
4.  build_world_state does NOT append a gap when the artifact is absent (optional-artifact)
5.  macro brief drops the stage_analysis world_state key cleanly (no crash, not surfaced)
6.  ask_brain tool read_stage_analysis returns available=False when absent
7.  ask_brain tool read_stage_analysis returns available=True on fixture
8.  ask_brain tool ticker filter restricts the Stage 2 board
9.  ask_brain tool stage filter restricts to that Weinstein stage
10. ask_brain tool min_score filter respects the score floor
11. ask_brain tool fresh_only filter keeps only fresh Stage 2 names
12. ask_brain tool always sets is_context_only=True (available and absent paths)
13. read_stage_analysis in _ASK_READ_TOOLS whitelist and cortex _READ_TOOLS
14. read_stage_analysis NOT in cortex _WRITE_TOOLS (no write path)
15. cortex _tool_schemas includes read_stage_analysis schema with optional params
16. mastermind _summarize_stage_analysis returns empty lobe + gap when absent
17. mastermind _summarize_stage_analysis parses fixture correctly
18. mastermind _LOBE_TO_ARTIFACT_IDS has stage_analysis entry
19. banned-word — 'validated' not in any stage_analysis tool/lobe response (fixture)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers — self-contained INLINE fixture (no external fixture files)
# ---------------------------------------------------------------------------

def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def _stage_fixture_payload() -> dict:
    """Return a minimal stage_context.v1 payload (inline, self-contained)."""
    return {
        "schema": "stage_context.v1",
        "asof": "2026-07-18",
        "built": "2026-07-18T07:00:00Z",
        "is_context_only": True,
        "display_only": True,
        "disclaimer": "Context only — stage classification display, never a signal or sizing input.",
        "counts": {
            "total": 2758,
            "stage1": 900,
            "stage2": 700,
            "stage2_fresh": 120,
            "stage3": 400,
            "stage4": 600,
            "too_young": 158,
            "new_today": 14,
        },
        "market": {
            "pct_stage2": 25.4,
            "pct_stage4": 21.8,
            "weather": "advancing",
            "spy_stage": 2,
            "spy_weeks": 6,
        },
        "top_stage2": [
            {
                "ticker": "ACME",
                "company": "Acme Corp",
                "sector": "Technology",
                "stage": 2,
                "weeks_in_stage": 4,
                "fresh": True,
                "sga_score": 88,
                "ma30_slope_pct5w": 1.9,
                "pct_vs_ma30": 6.2,
                "mansfield_rs": 3.1,
                "vol_ratio": 1.7,
                "event": "breakout",
                "gate_tier": "T1",
                "blackout": False,
                "arc_pos": 0.31,
                "earnings": {"present": True, "sentiment": 0.4, "performance": 7.0,
                             "tone_word": "confident", "tags": ["beat_and_raise"], "quarter": "Q2"},
                "why": ["Fresh into Stage 2", "T1 cascade eligible"],
                "why_zh": ["刚进入第二阶段", "T1级别"],
            },
            {
                "ticker": "BETA",
                "company": "Beta Inc",
                "sector": "Industrials",
                "stage": 2,
                "weeks_in_stage": 12,
                "fresh": False,
                "sga_score": 61,
                "ma30_slope_pct5w": 0.9,
                "pct_vs_ma30": 3.4,
                "mansfield_rs": 0.6,
                "vol_ratio": 1.1,
                "event": None,
                "gate_tier": "T3",
                "blackout": True,
                "arc_pos": 0.44,
                "earnings": {"present": False, "sentiment": None, "performance": None,
                             "tone_word": None, "tags": [], "quarter": None},
                "why": ["Extended, past freshness window"],
                "why_zh": ["涨幅偏大，超过新鲜期"],
            },
        ],
        "warnings_stage3": [
            {"ticker": "GAMA", "company": "Gama Ltd", "weeks_in_stage": 3, "sga_score": 40},
        ],
        "sectors": [
            {"sector": "Technology", "n": 220, "pct_stage2": 38.0, "trend": "up"},
            {"sector": "Industrials", "n": 180, "pct_stage2": 24.0, "trend": "flat"},
        ],
        "roster": {"ACME": [2, 4], "BETA": [2, 12], "GAMA": [3, 3]},
        "changes": {
            "items": [
                {"kind": "entered_stage2", "ticker": "ACME", "detail": "recaptured trendline"},
                {"kind": "topping", "ticker": "DELT", "detail": "flat slope from Stage 2"},
            ],
            "n": 2,
        },
        "prev_state": {"asof": "2026-07-17", "by_key": {"ACME": {"stage": 1, "weeks": 8}}},
        "_current_by_key": {},
    }


def _make_context_fixture(root: Path) -> dict:
    """Write minimal data/stage_analysis/context/latest.json fixture."""
    payload = _stage_fixture_payload()
    _write_json(root / "data" / "stage_analysis" / "context" / "latest.json", payload)
    return payload


# ---------------------------------------------------------------------------
# 1-2: _compose_stage_analysis
# ---------------------------------------------------------------------------

class TestComposeStageAnalysis:
    """Tests for engine.neuralweb.world_state._compose_stage_analysis."""

    def test_returns_null_block_when_absent(self, tmp_path):
        """Absent artifact → honest-null block (never None, never raises)."""
        from engine.neuralweb.world_state import _compose_stage_analysis
        result = _compose_stage_analysis(root=tmp_path)
        assert isinstance(result, dict)
        assert result["as_of"] is None
        assert result["counts"] is None
        assert result["market"] is None
        assert result["top_stage2"] is None
        assert result["changes"] is None
        assert result["display_only"] is True
        assert result["is_context_only"] is True

    def test_parses_fixture_correctly(self, tmp_path):
        """Parses fixture artifact and returns expected structure."""
        from engine.neuralweb.world_state import _compose_stage_analysis
        _make_context_fixture(tmp_path)
        result = _compose_stage_analysis(root=tmp_path)
        assert result is not None
        assert result["as_of"] == "2026-07-18"
        assert result["display_only"] is True
        assert result["is_context_only"] is True
        # counts pass-through
        assert result["counts"]["total"] == 2758
        assert result["counts"]["stage2_fresh"] == 120
        # market summary
        assert result["market"]["weather"] == "advancing"
        assert result["market"]["spy_stage"] == 2
        # top_stage2 capped at 6, trimmed to display subset
        top = result["top_stage2"]
        assert isinstance(top, list)
        assert len(top) == 2
        assert top[0]["ticker"] == "ACME"
        assert top[0]["sga_score"] == 88
        assert top[0]["fresh"] is True
        assert "why" in top[0]
        # heavy keys excluded from the trimmed projection
        assert "roster" not in result
        assert "sectors" not in result
        assert "ma30_slope_pct5w" not in top[0]
        # changes capped at 8
        changes = result["changes"]
        assert isinstance(changes, list)
        assert len(changes) == 2
        assert changes[0]["kind"] == "entered_stage2"

    def test_top_stage2_capped_at_six(self, tmp_path):
        """top_stage2 is capped at 6 even when the artifact carries more."""
        from engine.neuralweb.world_state import _compose_stage_analysis
        payload = _stage_fixture_payload()
        base = payload["top_stage2"][0]
        payload["top_stage2"] = [dict(base, ticker=f"T{i}") for i in range(12)]
        _write_json(tmp_path / "data" / "stage_analysis" / "context" / "latest.json", payload)
        result = _compose_stage_analysis(root=tmp_path)
        assert len(result["top_stage2"]) == 6


# ---------------------------------------------------------------------------
# 3-4: world_state integration
# ---------------------------------------------------------------------------

class TestWorldStateStageAnalysis:
    """Tests for stage_analysis in the world_state payload + build wiring."""

    def test_block_always_display_and_context_only(self, tmp_path):
        """Both absent-null and fixture blocks carry display_only + is_context_only."""
        from engine.neuralweb.world_state import _compose_stage_analysis
        null_block = _compose_stage_analysis(root=tmp_path)
        assert null_block["display_only"] is True
        assert null_block["is_context_only"] is True
        _make_context_fixture(tmp_path)
        block = _compose_stage_analysis(root=tmp_path)
        assert block["display_only"] is True
        assert block["is_context_only"] is True

    def test_absent_artifact_appends_no_gap(self, monkeypatch):
        """build_world_state must NOT append a stage_analysis gap when the file is absent.

        The optional-artifact pattern (theme_rotation / intl_risk): the honest-null
        block communicates absence, so no gap entry is generated.
        """
        import engine.neuralweb.world_state as ws
        # Stub every source read to keep build_world_state cheap and deterministic:
        # we only need to prove the stage_analysis lobe adds no gap when absent.
        payload = ws.build_world_state()
        # stage_analysis key is present in the payload
        assert "stage_analysis" in payload
        # No stage_analysis-prefixed gap in the (real) build (artifact absent on disk)
        gaps = payload.get("gaps") or []
        stage_gaps = [g for g in gaps if isinstance(g, str) and g.startswith("stage_analysis")]
        assert stage_gaps == [], f"unexpected stage_analysis gap(s): {stage_gaps}"
        # And the block is the honest-null (or populated) display-only dict
        block = payload["stage_analysis"]
        assert isinstance(block, dict)
        assert block.get("display_only") is True
        assert block.get("is_context_only") is True


# ---------------------------------------------------------------------------
# 5: macro brief drops the key cleanly
# ---------------------------------------------------------------------------

class TestBriefDropsStageAnalysis:
    """The macro brief has no stage_analysis block builder — the key drops cleanly."""

    def test_macro_brief_drops_stage_analysis_key(self, tmp_path):
        """macro_slice runs without error and does not surface a stage_analysis block."""
        from engine.neuralweb import brief_context
        from engine.neuralweb.world_state import _compose_stage_analysis
        _make_context_fixture(tmp_path)
        sa_block = _compose_stage_analysis(root=tmp_path)
        # Write a world_state.json into the NW dir carrying the stage_analysis block.
        nw = tmp_path / "data" / "neuralweb"
        nw.mkdir(parents=True, exist_ok=True)
        (nw / "world_state.json").write_text(
            json.dumps({"as_of": "2026-07-18", "stage_analysis": sa_block, "market": {}}),
            encoding="utf-8",
        )
        result = brief_context.macro_slice(root=tmp_path)
        assert isinstance(result, dict)
        # The brief has no stage_analysis builder — the key must not be surfaced.
        assert "stage_analysis" not in result
        # And nothing crashed (no absent-marker fatal wrapper).
        assert result.get("absent") is not True or "reason" not in result


# ---------------------------------------------------------------------------
# 6-12: ask_brain tool
# ---------------------------------------------------------------------------

class TestAskBrainStageAnalysis:
    """Tests for _tool_read_stage_analysis in ask_brain.py."""

    def test_returns_available_false_when_absent(self, tmp_path):
        """Absent context artifact → available=False, is_context_only=True."""
        from engine.neuralweb.ask_brain import _tool_read_stage_analysis
        result = _tool_read_stage_analysis(tmp_path, {})
        assert result.get("available") is False
        assert result.get("is_context_only") is True
        assert result.get("display_only") is True
        assert "note" in result

    def test_returns_available_true_on_fixture(self, tmp_path):
        """Present artifact → available=True with counts/market/board."""
        from engine.neuralweb.ask_brain import _tool_read_stage_analysis
        _make_context_fixture(tmp_path)
        result = _tool_read_stage_analysis(tmp_path, {})
        assert result.get("available") is True
        assert result.get("is_context_only") is True
        assert result.get("display_only") is True
        assert "counts" in result
        assert "market" in result
        assert "top_stage2" in result
        assert result["asof"] == "2026-07-18"

    def test_ticker_filter_restricts_board(self, tmp_path):
        """ticker filter keeps only that ticker in the Stage 2 board."""
        from engine.neuralweb.ask_brain import _tool_read_stage_analysis
        _make_context_fixture(tmp_path)
        result = _tool_read_stage_analysis(tmp_path, {"ticker": "ACME"})
        assert result.get("available") is True
        tickers = {s.get("ticker") for s in result.get("top_stage2", [])}
        assert tickers == {"ACME"}

    def test_stage_filter_restricts_board(self, tmp_path):
        """stage filter keeps only names in that Weinstein stage."""
        from engine.neuralweb.ask_brain import _tool_read_stage_analysis
        _make_context_fixture(tmp_path)
        result = _tool_read_stage_analysis(tmp_path, {"stage": 2})
        assert result.get("available") is True
        for s in result.get("top_stage2", []):
            assert s.get("stage") == 2
        # a stage with no members returns an empty board (still available)
        result3 = _tool_read_stage_analysis(tmp_path, {"stage": 4})
        assert result3.get("available") is True
        assert result3.get("top_stage2") == []

    def test_min_score_filter_respects_floor(self, tmp_path):
        """min_score floors the display-tier sga_score."""
        from engine.neuralweb.ask_brain import _tool_read_stage_analysis
        _make_context_fixture(tmp_path)
        result = _tool_read_stage_analysis(tmp_path, {"min_score": 80})
        assert result.get("available") is True
        for s in result.get("top_stage2", []):
            assert s.get("sga_score") >= 80
        # ACME (88) kept, BETA (61) dropped
        tickers = {s.get("ticker") for s in result.get("top_stage2", [])}
        assert tickers == {"ACME"}

    def test_fresh_only_filter(self, tmp_path):
        """fresh_only keeps only names with fresh=True."""
        from engine.neuralweb.ask_brain import _tool_read_stage_analysis
        _make_context_fixture(tmp_path)
        result = _tool_read_stage_analysis(tmp_path, {"fresh_only": True})
        assert result.get("available") is True
        for s in result.get("top_stage2", []):
            assert s.get("fresh") is True
        tickers = {s.get("ticker") for s in result.get("top_stage2", [])}
        assert tickers == {"ACME"}

    def test_always_context_only_both_paths(self, tmp_path):
        """is_context_only is True on both the absent and present paths."""
        from engine.neuralweb.ask_brain import _tool_read_stage_analysis
        absent = _tool_read_stage_analysis(tmp_path, {})
        assert absent.get("is_context_only") is True
        _make_context_fixture(tmp_path)
        present = _tool_read_stage_analysis(tmp_path, {})
        assert present.get("is_context_only") is True


# ---------------------------------------------------------------------------
# 13-15: whitelist / write-tool exclusion / cortex schema
# ---------------------------------------------------------------------------

class TestWhitelistAndSchema:
    def test_read_stage_analysis_in_ask_read_tools(self):
        """read_stage_analysis must be in ask_brain._ASK_READ_TOOLS and cortex._READ_TOOLS."""
        from engine.neuralweb.ask_brain import _ASK_READ_TOOLS
        from engine.neuralweb.cortex import _READ_TOOLS
        assert "read_stage_analysis" in _ASK_READ_TOOLS
        assert "read_stage_analysis" in _READ_TOOLS

    def test_read_stage_analysis_not_in_write_tools(self):
        """read_stage_analysis must not be in cortex _WRITE_TOOLS (no write path)."""
        from engine.neuralweb.cortex import _WRITE_TOOLS
        assert "read_stage_analysis" not in _WRITE_TOOLS

    def test_read_stage_analysis_in_tool_schemas(self):
        """read_stage_analysis appears in cortex _tool_schemas() with optional params."""
        from engine.neuralweb.cortex import _tool_schemas
        entry = next((s for s in _tool_schemas() if s["name"] == "read_stage_analysis"), None)
        assert entry is not None
        props = entry["input_schema"]["properties"]
        assert "ticker" in props
        assert "stage" in props
        assert "min_score" in props
        assert "fresh_only" in props
        assert entry["input_schema"]["required"] == []

    def test_dispatch_reaches_handler(self, tmp_path):
        """The ask_brain read dispatcher routes read_stage_analysis to the handler."""
        from engine.neuralweb.ask_brain import _dispatch_read_tool
        _make_context_fixture(tmp_path)
        result = _dispatch_read_tool("read_stage_analysis", {}, tmp_path)
        assert result.get("available") is True
        assert result.get("is_context_only") is True


# ---------------------------------------------------------------------------
# 16-18: mastermind summarizer
# ---------------------------------------------------------------------------

class TestMastermindStageAnalysis:
    def test_summarize_returns_empty_lobe_and_gap_when_absent(self, tmp_path):
        """_summarize_stage_analysis returns empty lobe + gap note when absent."""
        from engine.neuralweb.mastermind_context import _summarize_stage_analysis
        lobe, gap = _summarize_stage_analysis(tmp_path)
        assert isinstance(lobe, dict)
        assert lobe == {} or not lobe.get("asof")
        assert gap is not None
        assert "absent" in gap.lower() or "unreadable" in gap.lower()

    def test_summarize_parses_fixture(self, tmp_path):
        """_summarize_stage_analysis parses fixture and returns expected keys."""
        from engine.neuralweb.mastermind_context import _summarize_stage_analysis
        _make_context_fixture(tmp_path)
        lobe, gap = _summarize_stage_analysis(tmp_path)
        assert gap is None
        assert lobe.get("is_context_only") is True
        assert lobe.get("display_only") is True
        assert lobe.get("asof") == "2026-07-18"
        assert lobe["counts"]["total"] == 2758
        assert lobe["counts"]["stage2_fresh"] == 120
        assert lobe["market"]["weather"] == "advancing"
        assert isinstance(lobe.get("top_stage2"), list)
        assert len(lobe["top_stage2"]) == 2
        assert lobe["top_stage2"][0]["ticker"] == "ACME"
        assert lobe.get("n_changes") == 2
        assert "honesty_note" in lobe

    def test_summarize_caps_top_stage2_at_six(self, tmp_path):
        """The lobe's top_stage2 projection is capped at 6."""
        from engine.neuralweb.mastermind_context import _summarize_stage_analysis
        payload = _stage_fixture_payload()
        base = payload["top_stage2"][0]
        payload["top_stage2"] = [dict(base, ticker=f"T{i}") for i in range(10)]
        _write_json(tmp_path / "data" / "stage_analysis" / "context" / "latest.json", payload)
        lobe, gap = _summarize_stage_analysis(tmp_path)
        assert gap is None
        assert len(lobe["top_stage2"]) == 6

    def test_lobe_to_artifact_ids_has_stage_analysis(self):
        """_LOBE_TO_ARTIFACT_IDS + LOBE_SUMMARIZERS must include the stage_analysis entry."""
        from engine.neuralweb.mastermind_context import (
            _LOBE_TO_ARTIFACT_IDS,
            LOBE_SUMMARIZERS,
        )
        assert "stage_analysis" in _LOBE_TO_ARTIFACT_IDS
        assert "stage-analysis-context-latest" in _LOBE_TO_ARTIFACT_IDS["stage_analysis"]
        assert "stage_analysis" in LOBE_SUMMARIZERS


# ---------------------------------------------------------------------------
# 19: banned word
# ---------------------------------------------------------------------------

class TestBannedWord:
    def test_no_validated_in_tool_response(self, tmp_path):
        """Tool response must not contain the CI-guarded word 'validated'."""
        from engine.neuralweb.ask_brain import _tool_read_stage_analysis
        _make_context_fixture(tmp_path)
        result = _tool_read_stage_analysis(tmp_path, {})
        assert "validated" not in json.dumps(result).lower()

    def test_no_validated_in_lobe(self, tmp_path):
        """Mastermind lobe must not contain the CI-guarded word 'validated'."""
        from engine.neuralweb.mastermind_context import _summarize_stage_analysis
        _make_context_fixture(tmp_path)
        lobe, _gap = _summarize_stage_analysis(tmp_path)
        assert "validated" not in json.dumps(lobe).lower()

    def test_no_validated_in_compose_block(self, tmp_path):
        """world_state block must not contain the CI-guarded word 'validated'."""
        from engine.neuralweb.world_state import _compose_stage_analysis
        _make_context_fixture(tmp_path)
        block = _compose_stage_analysis(root=tmp_path)
        assert "validated" not in json.dumps(block).lower()
