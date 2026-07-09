"""tests/test_til_nw_citizenship.py — TIL W5 NW citizenship integration tests.

Coverage
--------
1.  world_state block present — thematic_state key in world_state payload
2.  world_state block tolerant — artifact absent → null block, world_state still composes
3.  world_state compact — serialized thematic_state block < 2048 bytes
4.  world_state display_only — thematic_state.display_only always True
5.  ask_brain routing — theme question → read_theme_state in seed tools
6.  ask_brain routing (pathway) — theme+pathway question seeds read_theme_pathways
7.  ask_brain routing (non-theme) — non-theme question does NOT route to theme tools
8.  ask_brain dispatch read_theme_state present — handler returns available=True on fixture
9.  ask_brain dispatch read_theme_state absent — handler returns available=False on missing file
10. ask_brain dispatch read_theme_thesis present — handler returns n_theses
11. ask_brain dispatch read_theme_thesis absent — handler returns available=False
12. ask_brain dispatch read_theme_pathways absent — handler returns available=False
13. ask_brain read-only guarantee — no write tools in _ASK_READ_TOOLS
14. ask_brain whitelist — read_theme_state/thesis/pathways in _ASK_READ_TOOLS
15. cortex tool_schemas — read_theme_state present in schema list
16. cortex read-only — read_theme_state NOT in _WRITE_TOOLS
17. mastermind summarizer output shape — thematic_state lobe keys present
18. mastermind summarizer absent tolerance — theme_state.json absent → empty lobe + gap_note
19. mastermind _LOBE_TO_ARTIFACT_IDS — theme-state entry present
20. banned-words — "validated" not in any tool response payload (fixture)
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


def _make_theme_state(root: Path) -> dict:
    """Write a minimal theme_state.json fixture and return the dict."""
    payload = {
        "schema": "neuralweb.theme_state.v1",
        "as_of": "2026-07-09",
        "generated_at": "2026-07-09T07:13:38Z",
        "n_themes": 2,
        "themes": [
            {
                "theme_id": "ai_semiconductors",
                "name_en": "AI Semiconductors",
                "name_zh": "AI半导体",
                "foresight": {
                    "stage": "RE-RATING",
                    "tier": "P",
                    "score": 50.0,
                    "entry_ready": False,
                    "bottleneck_band": "TIGHT (text)",
                },
                "basket_ids": ["ai_semiconductors", "ai_infra"],
            },
            {
                "theme_id": "nuclear_power",
                "name_en": "Nuclear Power",
                "name_zh": "核能",
                "foresight": {
                    "stage": "WATCH",
                    "tier": "P",
                    "score": 30.0,
                    "entry_ready": False,
                    "bottleneck_band": "LOW",
                },
                "basket_ids": ["nuclear_power"],
            },
        ],
        "stale_legs": ["divergence_log[robotics]: stale"],
        "authority": {"is_context_only": True, "display_only": True},
    }
    _write_json(root / "data" / "neuralweb" / "theme_state.json", payload)
    return payload


def _make_theme_thesis(root: Path) -> dict:
    """Write a minimal site/neuralwebdata/theme_thesis.json fixture."""
    payload = {
        "schema": "neuralweb.theme_thesis.v1",
        "as_of": "2026-07-09",
        "n_theses": 2,
        "n_falsifier_fired": 1,
        "theses": [
            {
                "theme_id": "ai_semiconductors",
                "thesis_id": "ai_semiconductors.v1",
                "status": "active",
                "variant_perception_en": "Structural demand above cycle.",
                "driver": "capex",
                "falsifiers": [
                    {"id": "ai_semi_f1", "state": "ARMED", "fired": False},
                ],
                "falsifier_summary": {"n_fired": 0, "n_armed": 1, "any_fired": False},
            },
            {
                "theme_id": "nuclear_power",
                "thesis_id": "nuclear_power.v1",
                "status": "active",
                "variant_perception_en": "Policy-driven renaissance.",
                "driver": "policy",
                "falsifiers": [
                    {"id": "nuke_f1", "state": "FIRED", "fired": True},
                ],
                "falsifier_summary": {"n_fired": 1, "n_armed": 0, "any_fired": True},
            },
        ],
    }
    _write_json(root / "site" / "neuralwebdata" / "theme_thesis.json", payload)
    return payload


def _make_theme_pathways(root: Path) -> dict:
    """Write a minimal site/neuralwebdata/theme_pathways.json fixture."""
    payload = {
        "schema": "neuralweb.theme_pathways.v1",
        "as_of": "2026-07-09",
        "themes": [
            {
                "theme_id": "ai_semiconductors",
                "name_en": "AI Semiconductors",
                "winners": [{"ticker": "NVDA", "role": "direct"}],
                "losers": [{"ticker": "INTC", "role": "displaced"}],
            }
        ],
    }
    _write_json(root / "site" / "neuralwebdata" / "theme_pathways.json", payload)
    return payload


# ---------------------------------------------------------------------------
# 1-4: world_state block
# ---------------------------------------------------------------------------

class TestWorldStateThematicBlock:
    """Tests for _compose_thematic_state wired into build_world_state."""

    def _make_minimal_world_state_root(self, tmp_path: Path) -> Path:
        """Build a minimal but valid synthetic repo root for build_world_state."""
        import shutil
        repo_root = Path(__file__).resolve().parent.parent
        # Copy synapse.yml so stamp() can resolve
        (tmp_path / "config").mkdir()
        shutil.copyfile(repo_root / "config" / "synapse.yml", tmp_path / "config" / "synapse.yml")
        return tmp_path

    def test_thematic_state_key_present(self, tmp_path):
        """thematic_state key must be present in build_world_state() payload."""
        from engine.neuralweb.world_state import build_world_state
        root = self._make_minimal_world_state_root(tmp_path)
        _make_theme_state(root)
        _make_theme_thesis(root)
        payload = build_world_state(root=root)
        assert "thematic_state" in payload, "thematic_state key missing from world_state payload"

    def test_thematic_state_absent_artifact_null_block(self, tmp_path):
        """When theme_state.json is absent, thematic_state block is null (available=False)
        and world_state still composes successfully (no exception)."""
        from engine.neuralweb.world_state import build_world_state
        root = self._make_minimal_world_state_root(tmp_path)
        # Do NOT write theme_state.json — simulate absent artifact
        payload = build_world_state(root=root)
        assert "thematic_state" in payload
        block = payload["thematic_state"]
        assert isinstance(block, dict)
        assert block.get("available") is False

    def test_thematic_state_compact_under_2kb(self, tmp_path):
        """Serialized thematic_state block must be under 2048 bytes."""
        from engine.neuralweb.world_state import build_world_state
        root = self._make_minimal_world_state_root(tmp_path)
        _make_theme_state(root)
        _make_theme_thesis(root)
        payload = build_world_state(root=root)
        block = payload.get("thematic_state", {})
        serialized = json.dumps(block, ensure_ascii=False)
        assert len(serialized.encode("utf-8")) < 2048, (
            f"thematic_state block too large: {len(serialized.encode('utf-8'))} bytes "
            "(target <2KB)"
        )

    def test_thematic_state_display_only(self, tmp_path):
        """thematic_state.display_only must always be True."""
        from engine.neuralweb.world_state import build_world_state
        root = self._make_minimal_world_state_root(tmp_path)
        _make_theme_state(root)
        _make_theme_thesis(root)
        payload = build_world_state(root=root)
        block = payload.get("thematic_state", {})
        if block.get("available"):
            assert block.get("display_only") is True, "display_only must be True"
            assert block.get("is_context_only") is True, "is_context_only must be True"


# ---------------------------------------------------------------------------
# 5-13: ask_brain routing + dispatch handlers
# ---------------------------------------------------------------------------

class TestAskBrainThemeRouting:
    """Tests for _classify_question routing to theme tools."""

    def test_theme_question_routes_to_theme_state(self):
        """A question containing thematic trigger terms seeds read_theme_state."""
        from engine.neuralweb.ask_brain import _classify_question
        budget, seeds = _classify_question("What is the thematic state?", None)
        assert "read_theme_state" in seeds

    def test_theme_question_routes_to_theme_thesis(self):
        """A question about theme thesis seeds read_theme_thesis."""
        from engine.neuralweb.ask_brain import _classify_question
        budget, seeds = _classify_question("Tell me about the theme thesis integrity", None)
        assert "read_theme_thesis" in seeds

    def test_pathway_question_seeds_read_theme_pathways(self):
        """A question mentioning pathway seeds read_theme_pathways too."""
        from engine.neuralweb.ask_brain import _classify_question
        budget, seeds = _classify_question(
            "What is the thematic state and beneficiary pathway?", None
        )
        assert "read_theme_pathways" in seeds

    def test_non_theme_question_not_routed_to_theme_tools(self):
        """A generic regime question does not route to theme tools."""
        from engine.neuralweb.ask_brain import _classify_question
        budget, seeds = _classify_question("What is the current macro regime?", None)
        assert "read_theme_state" not in seeds
        assert "read_theme_thesis" not in seeds
        assert "read_theme_pathways" not in seeds

    def test_chinese_theme_question_routes(self):
        """A Chinese-language question with theme trigger terms routes to theme tools."""
        from engine.neuralweb.ask_brain import _classify_question
        budget, seeds = _classify_question("当前的主题状态是什么？", None)
        assert "read_theme_state" in seeds

    def test_dispatch_read_theme_state_present(self, tmp_path):
        """_dispatch_read_tool('read_theme_state') returns available=True on fixture."""
        from engine.neuralweb.ask_brain import _dispatch_read_tool
        _make_theme_state(tmp_path)
        _make_theme_thesis(tmp_path)
        result = _dispatch_read_tool("read_theme_state", {}, tmp_path)
        assert result.get("available") is True
        assert result.get("is_context_only") is True
        assert result.get("display_only") is True
        assert "n_themes" in result
        assert "stage_counts" in result
        assert "n_falsifiers_fired" in result

    def test_dispatch_read_theme_state_absent(self, tmp_path):
        """_dispatch_read_tool('read_theme_state') returns available=False when absent."""
        from engine.neuralweb.ask_brain import _dispatch_read_tool
        # No fixture written — simulate absent
        result = _dispatch_read_tool("read_theme_state", {}, tmp_path)
        assert result.get("available") is False

    def test_dispatch_read_theme_state_theme_id_filter(self, tmp_path):
        """theme_id param filters to a single theme record."""
        from engine.neuralweb.ask_brain import _dispatch_read_tool
        _make_theme_state(tmp_path)
        _make_theme_thesis(tmp_path)
        result = _dispatch_read_tool("read_theme_state", {"theme_id": "nuclear_power"}, tmp_path)
        assert result.get("available") is True
        assert result.get("found") is True
        assert result.get("theme_id") == "nuclear_power"

    def test_dispatch_read_theme_thesis_present(self, tmp_path):
        """_dispatch_read_tool('read_theme_thesis') returns n_theses."""
        from engine.neuralweb.ask_brain import _dispatch_read_tool
        _make_theme_thesis(tmp_path)
        result = _dispatch_read_tool("read_theme_thesis", {}, tmp_path)
        assert result.get("available") is True
        assert result.get("is_context_only") is True
        assert "n_theses" in result
        assert result.get("n_falsifier_fired") == 1

    def test_dispatch_read_theme_thesis_absent(self, tmp_path):
        """_dispatch_read_tool('read_theme_thesis') returns available=False when absent."""
        from engine.neuralweb.ask_brain import _dispatch_read_tool
        result = _dispatch_read_tool("read_theme_thesis", {}, tmp_path)
        assert result.get("available") is False

    def test_dispatch_read_theme_pathways_absent(self, tmp_path):
        """_dispatch_read_tool('read_theme_pathways') returns available=False when absent."""
        from engine.neuralweb.ask_brain import _dispatch_read_tool
        result = _dispatch_read_tool("read_theme_pathways", {}, tmp_path)
        assert result.get("available") is False

    def test_dispatch_read_theme_pathways_present(self, tmp_path):
        """_dispatch_read_tool('read_theme_pathways') returns themes list when present."""
        from engine.neuralweb.ask_brain import _dispatch_read_tool
        _make_theme_pathways(tmp_path)
        result = _dispatch_read_tool("read_theme_pathways", {}, tmp_path)
        assert result.get("available") is True
        assert result.get("is_context_only") is True

    def test_read_only_guarantee_no_write_tool_in_ask_read_tools(self):
        """_ASK_READ_TOOLS must not contain any write tools."""
        from engine.neuralweb.ask_brain import _ASK_READ_TOOLS
        write_tools = {"flag_attention", "write_memo", "stake_hypothesis"}
        overlap = _ASK_READ_TOOLS & write_tools
        assert not overlap, f"write tools found in _ASK_READ_TOOLS: {overlap}"

    def test_theme_tools_in_ask_read_tools_whitelist(self):
        """read_theme_state, read_theme_thesis, read_theme_pathways in _ASK_READ_TOOLS."""
        from engine.neuralweb.ask_brain import _ASK_READ_TOOLS
        for tool in ("read_theme_state", "read_theme_thesis", "read_theme_pathways"):
            assert tool in _ASK_READ_TOOLS, f"{tool} not in _ASK_READ_TOOLS"


# ---------------------------------------------------------------------------
# 15-16: cortex schema entry
# ---------------------------------------------------------------------------

class TestCortexThemeSchema:
    """Tests for read_theme_state entry in cortex _tool_schemas."""

    def test_read_theme_state_in_tool_schemas(self):
        """read_theme_state must appear in cortex _tool_schemas()."""
        from engine.neuralweb.cortex import _tool_schemas
        schemas = _tool_schemas()
        names = {s["name"] for s in schemas}
        assert "read_theme_state" in names, "read_theme_state missing from cortex _tool_schemas"

    def test_read_theme_state_not_in_write_tools(self):
        """read_theme_state must not be in cortex _WRITE_TOOLS."""
        from engine.neuralweb.cortex import _WRITE_TOOLS
        assert "read_theme_state" not in _WRITE_TOOLS

    def test_read_theme_state_schema_has_optional_theme_id(self):
        """read_theme_state schema must expose optional theme_id param."""
        from engine.neuralweb.cortex import _tool_schemas
        schemas = _tool_schemas()
        theme_schema = next((s for s in schemas if s["name"] == "read_theme_state"), None)
        assert theme_schema is not None
        props = theme_schema.get("input_schema", {}).get("properties", {})
        assert "theme_id" in props, "theme_id param missing from read_theme_state schema"
        # Must be optional (not in required)
        required = theme_schema.get("input_schema", {}).get("required", [])
        assert "theme_id" not in required, "theme_id must be optional (not required)"


# ---------------------------------------------------------------------------
# 17-19: mastermind_context summarizer
# ---------------------------------------------------------------------------

class TestMastermindContextThematic:
    """Tests for _summarize_thematic_state in mastermind_context."""

    def test_thematic_state_in_lobe_summarizers(self):
        """LOBE_SUMMARIZERS must contain thematic_state key."""
        from engine.neuralweb.mastermind_context import LOBE_SUMMARIZERS
        assert "thematic_state" in LOBE_SUMMARIZERS, (
            "thematic_state missing from LOBE_SUMMARIZERS"
        )

    def test_thematic_state_in_lobe_to_artifact_ids(self):
        """_LOBE_TO_ARTIFACT_IDS must contain thematic_state -> [theme-state]."""
        from engine.neuralweb.mastermind_context import _LOBE_TO_ARTIFACT_IDS
        assert "thematic_state" in _LOBE_TO_ARTIFACT_IDS
        assert "theme-state" in _LOBE_TO_ARTIFACT_IDS["thematic_state"]

    def test_summarizer_output_shape_present(self, tmp_path):
        """_summarize_thematic_state returns expected keys when artifact present."""
        from engine.neuralweb.mastermind_context import _summarize_thematic_state
        _make_theme_state(tmp_path)
        _make_theme_thesis(tmp_path)
        lobe, gap_note = _summarize_thematic_state(tmp_path)
        assert gap_note is None
        assert "as_of" in lobe
        assert "n_themes" in lobe
        assert "stage_counts" in lobe
        assert "n_falsifiers_fired" in lobe
        assert "falsifiers_fired" in lobe
        assert "n_stale_legs" in lobe
        assert "noteworthy" in lobe
        assert "standing_law" in lobe

    def test_summarizer_falsifier_fired_detected(self, tmp_path):
        """_summarize_thematic_state detects fired falsifiers from theme_thesis."""
        from engine.neuralweb.mastermind_context import _summarize_thematic_state
        _make_theme_state(tmp_path)
        _make_theme_thesis(tmp_path)
        lobe, _ = _summarize_thematic_state(tmp_path)
        assert lobe["n_falsifiers_fired"] == 1
        fired = lobe["falsifiers_fired"]
        assert len(fired) == 1
        assert fired[0]["theme_id"] == "nuclear_power"
        assert fired[0]["falsifier_id"] == "nuke_f1"

    def test_summarizer_absent_artifact_tolerance(self, tmp_path):
        """_summarize_thematic_state returns empty lobe + gap_note when artifact absent."""
        from engine.neuralweb.mastermind_context import _summarize_thematic_state
        lobe, gap_note = _summarize_thematic_state(tmp_path)
        assert lobe == {}, f"Expected empty lobe, got: {lobe}"
        assert gap_note is not None
        assert "absent" in gap_note or "unreadable" in gap_note

    def test_summarizer_size_compact(self, tmp_path):
        """Serialized thematic_state lobe must be reasonably compact."""
        from engine.neuralweb.mastermind_context import _summarize_thematic_state
        _make_theme_state(tmp_path)
        _make_theme_thesis(tmp_path)
        lobe, _ = _summarize_thematic_state(tmp_path)
        serialized = json.dumps(lobe, ensure_ascii=False)
        # Allow generous headroom but cap at 8KB (mastermind context budget discipline)
        assert len(serialized.encode("utf-8")) < 8192, (
            f"thematic_state lobe too large: {len(serialized.encode('utf-8'))} bytes"
        )

    def test_no_standalone_world_state_false(self, tmp_path):
        """world_state composition does not crash when thematic_state artifact absent."""
        from engine.neuralweb.mastermind_context import _summarize_thematic_state
        # Absent — should not raise
        lobe, gap_note = _summarize_thematic_state(tmp_path)
        assert isinstance(lobe, dict)


# ---------------------------------------------------------------------------
# 20: banned words
# ---------------------------------------------------------------------------

class TestBannedWords:
    """Banned words must not appear in tool response payloads."""

    def _check_no_validated(self, obj: object, path: str = "") -> list[str]:
        """Recursively find any string values containing 'validated'."""
        hits = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                hits.extend(self._check_no_validated(v, f"{path}.{k}"))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                hits.extend(self._check_no_validated(v, f"{path}[{i}]"))
        elif isinstance(obj, str) and "validated" in obj.lower():
            hits.append(f"{path}: {obj[:80]!r}")
        return hits

    def test_read_theme_state_no_validated(self, tmp_path):
        """read_theme_state response must not contain the word 'validated'."""
        from engine.neuralweb.ask_brain import _dispatch_read_tool
        _make_theme_state(tmp_path)
        _make_theme_thesis(tmp_path)
        result = _dispatch_read_tool("read_theme_state", {}, tmp_path)
        hits = self._check_no_validated(result)
        assert not hits, f"'validated' found in read_theme_state response: {hits}"

    def test_read_theme_thesis_no_validated(self, tmp_path):
        """read_theme_thesis response must not contain the word 'validated'."""
        from engine.neuralweb.ask_brain import _dispatch_read_tool
        _make_theme_thesis(tmp_path)
        result = _dispatch_read_tool("read_theme_thesis", {}, tmp_path)
        hits = self._check_no_validated(result)
        assert not hits, f"'validated' found in read_theme_thesis response: {hits}"

    def test_mastermind_lobe_no_validated(self, tmp_path):
        """mastermind_context thematic_state lobe must not contain 'validated'."""
        from engine.neuralweb.mastermind_context import _summarize_thematic_state
        _make_theme_state(tmp_path)
        _make_theme_thesis(tmp_path)
        lobe, _ = _summarize_thematic_state(tmp_path)
        hits = self._check_no_validated(lobe)
        assert not hits, f"'validated' found in thematic_state lobe: {hits}"

    def test_world_state_thematic_block_no_validated(self, tmp_path):
        """world_state thematic_state block must not contain 'validated'."""
        import shutil
        repo_root = Path(__file__).resolve().parent.parent
        (tmp_path / "config").mkdir()
        shutil.copyfile(
            repo_root / "config" / "synapse.yml",
            tmp_path / "config" / "synapse.yml",
        )
        _make_theme_state(tmp_path)
        _make_theme_thesis(tmp_path)
        from engine.neuralweb.world_state import build_world_state
        payload = build_world_state(root=tmp_path)
        block = payload.get("thematic_state", {})
        hits = self._check_no_validated(block)
        assert not hits, f"'validated' found in world_state thematic_state: {hits}"
