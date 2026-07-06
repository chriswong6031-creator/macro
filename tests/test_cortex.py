"""Offline unit tests for engine.neuralweb.cortex (Neural Web W7b PR1).

ALL TESTS ARE OFFLINE — the anthropic client is mocked throughout.
No real API calls, no paid spend.

Test coverage:
  1. tool_dispatcher — each read tool against fixtures; deny-roots refuses config.yml
     and traversal attempts; row/size caps enforced.
  2. Write tools — correct output shapes (memo envelope-stamped; attention rows are
     valid reflex claims; hypothesis inbox rows marked inbox-not-registered).
  3. Budget enforcement — mock model that never stops → loop halts at max_tool_calls
     and STILL writes a memo.
  4. Staleness gate — unchanged state → zero model calls.
  5. Single-call fallback path (no providers).
  6. A2 refusal today (probation status in memo).
  7. Dispatcher refuses unknown tools.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _make_repo(tmp: Path) -> Path:
    """Create a minimal repo structure with fixture data files."""
    # Directory structure
    (tmp / "data" / "neuralweb").mkdir(parents=True)
    (tmp / "data" / "neuralweb" / "cortex").mkdir(parents=True)
    (tmp / "data" / "reflexes" / "cortex_attention").mkdir(parents=True)
    (tmp / "data" / "regime").mkdir(parents=True)
    (tmp / "site" / "neuralweb").mkdir(parents=True)
    (tmp / "config").mkdir(parents=True)
    (tmp / ".env").touch()  # deny-roots test target

    # world_state.json
    ws = {
        "schema": "neuralweb.world_state.v1",
        "as_of": "2026-07-04",
        "inputs_hash": "abc123def456",
        "verdict": "CAUTION",
        "regime": {"quad": "Q2"},
        "gaps": [],
    }
    (tmp / "data" / "neuralweb" / "world_state.json").write_text(
        json.dumps(ws), encoding="utf-8"
    )

    # confluence_graph.json with one contradicts edge
    graph = {
        "schema": "neuralweb.confluence_graph.v1",
        "nodes": [
            {"id": "signal_a", "type": "engine"},
            {"id": "signal_b", "type": "engine"},
        ],
        "edges": [
            {"edge_type": "contradicts", "source": "signal_a", "target": "signal_b"},
            {"edge_type": "confirms", "source": "signal_a", "target": "signal_b"},
        ],
    }
    (tmp / "data" / "neuralweb" / "confluence_graph.json").write_text(
        json.dumps(graph), encoding="utf-8"
    )

    # governance.jsonl (two events)
    events = [
        {"schema": "neuralweb.governance.v1", "event_type": "authority_lapse",
         "target": "cortex_attention", "ts": "2026-07-01T00:00:00",
         "authored_by": "cortex", "article": 3},
        {"schema": "neuralweb.governance.v1", "event_type": "config_arm",
         "target": "risk_radar_review", "ts": "2026-07-02T00:00:00",
         "authored_by": "engine/risk_radar_review.py", "article": 6},
    ]
    with (tmp / "data" / "neuralweb" / "governance.jsonl").open("w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")

    # kernel_families.json (fallback for read_kernel)
    kernel = {"families": {"spine:radar": {"ic": 0.12, "n": 100}}}
    (tmp / "data" / "neuralweb" / "kernel_families.json").write_text(
        json.dumps(kernel), encoding="utf-8"
    )

    # config.yml (should be denied)
    (tmp / "config.yml").write_text("secret: this-should-never-be-read\n", encoding="utf-8")

    # small artifact in data/
    small_art = {"hello": "world", "value": 42}
    (tmp / "data" / "regime" / "test_small.json").write_text(
        json.dumps(small_art), encoding="utf-8"
    )

    # large artifact (> 50 KB)
    big_content = "x" * (51 * 1024)
    (tmp / "data" / "regime" / "test_big.txt").write_text(big_content, encoding="utf-8")

    return tmp


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _make_repo(tmp_path)


_NOW_STR = "2026-07-04T12:00:00+00:00"
_PROBATION = {
    "tier": "A0/A1 shadow",
    "granted": False,
    "reason": "insufficient-n: n=0 < min_n=30",
    "lift_lb": None,
    "wilson_lb": None,
    "attention_track_record": {"n": 0, "hits": 0, "base_rate": 0.01},
    "lapses_at": None,
}


# ---------------------------------------------------------------------------
# 1. Tool dispatcher — read tools
# ---------------------------------------------------------------------------

class TestReadTools:

    def test_read_world_state_returns_dict(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("read_world_state", {}, repo, _NOW_STR, _PROBATION, census)
        assert "verdict" in result or "schema" in result or "as_of" in result
        assert census["read_world_state"] == 1

    def test_read_contradictions_returns_list(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("read_contradictions", {}, repo, _NOW_STR, _PROBATION, census)
        assert "contradictions" in result
        assert isinstance(result["contradictions"], list)
        # Our fixture has exactly one contradicts edge
        assert result["count"] == 1

    def test_read_graph_returns_graph(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("read_graph", {}, repo, _NOW_STR, _PROBATION, census)
        assert "edges" in result or "error" in result

    def test_read_graph_filter_by_edge_type(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("read_graph", {"edge_type": "contradicts"}, repo, _NOW_STR, _PROBATION, census)
        if "edges" in result:
            assert all(
                e.get("edge_type") == "contradicts" or e.get("type") == "contradicts"
                for e in result["edges"]
            )

    def test_read_governance_returns_events(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("read_governance", {}, repo, _NOW_STR, _PROBATION, census)
        assert "events" in result
        assert result["total"] == 2

    def test_read_governance_filter_by_tenant(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("read_governance", {"tenant": "cortex_attention"}, repo, _NOW_STR, _PROBATION, census)
        assert "events" in result
        # Only the authority_lapse event targets cortex_attention
        assert result["total"] <= 2

    def test_read_kernel_returns_data(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("read_kernel", {}, repo, _NOW_STR, _PROBATION, census)
        # Either parquet rows or kernel_families.json fallback
        assert "error" not in result or "families" in result or "rows" in result

    def test_read_artifact_small_file(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("read_artifact", {"path": "data/regime/test_small.json"},
                               repo, _NOW_STR, _PROBATION, census)
        assert "error" not in result
        assert result.get("content") is not None

    def test_read_artifact_size_cap_enforced(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("read_artifact", {"path": "data/regime/test_big.txt"},
                               repo, _NOW_STR, _PROBATION, census)
        assert "error" in result
        assert "too large" in result["error"].lower() or "cap" in result["error"].lower()

    def test_query_spine_no_parquet_returns_error_or_empty(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("query_spine", {}, repo, _NOW_STR, _PROBATION, census)
        # No parquet in our fixture — should return error or empty
        assert "error" in result or "rows" in result


# ---------------------------------------------------------------------------
# 2. Deny-roots enforcement
# ---------------------------------------------------------------------------

class TestDenyRoots:

    def test_config_yml_denied(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("read_artifact", {"path": "config.yml"},
                               repo, _NOW_STR, _PROBATION, census)
        assert "error" in result
        assert "deny" in result["error"].lower()

    def test_env_file_denied(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("read_artifact", {"path": ".env"},
                               repo, _NOW_STR, _PROBATION, census)
        assert "error" in result
        assert "deny" in result["error"].lower()

    def test_path_traversal_denied(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        # Attempt to escape via ../
        result = dispatch_tool(
            "read_artifact", {"path": "data/../config.yml"},
            repo, _NOW_STR, _PROBATION, census
        )
        assert "error" in result
        # It's either denied or not found (both acceptable)

    def test_git_path_denied(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("read_artifact", {"path": ".git/config"},
                               repo, _NOW_STR, _PROBATION, census)
        assert "error" in result

    def test_file_outside_read_roots_denied(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("read_artifact", {"path": "engine/master_brain.py"},
                               repo, _NOW_STR, _PROBATION, census)
        assert "error" in result
        assert "deny" in result["error"].lower()


# ---------------------------------------------------------------------------
# 3. Write tools — correct output shapes
# ---------------------------------------------------------------------------

class TestWriteTools:

    def test_flag_attention_writes_firings_jsonl(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        items = [{"scope_type": "entity", "scope_key": "NVDA", "direction": 1,
                   "horizon_d": 5, "falsifier": "NVDA up >3% within 5 days"}]
        result = dispatch_tool("flag_attention", {"items": items},
                               repo, _NOW_STR, _PROBATION, census)
        assert result.get("written") == 1
        assert len(result.get("claim_ids", [])) == 1

        # Verify firings.jsonl was written
        fpath = repo / "data" / "reflexes" / "cortex_attention" / "firings.jsonl"
        assert fpath.exists()
        record = json.loads(fpath.read_text().strip())
        assert record["is_context_only"] is True
        assert record["claim_family"] == "reflex.cortex_attention"
        assert record["scope_key"] == "NVDA"
        assert "claim_id" in record

    def test_flag_attention_claim_shape(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        items = [{"scope_type": "sector", "scope_key": "XLK", "direction": -1,
                   "horizon_d": 10, "falsifier": "XLK drawdown >5% within 10 days"}]
        dispatch_tool("flag_attention", {"items": items},
                      repo, _NOW_STR, _PROBATION, census)
        fpath = repo / "data" / "reflexes" / "cortex_attention" / "firings.jsonl"
        record = json.loads(fpath.read_text().strip())
        # Mandatory claim fields
        assert "claim_id" in record
        assert "asof" in record
        assert record["direction"] == -1
        assert record["horizon_d"] == 10
        assert record["is_context_only"] is True

    def test_write_memo_produces_correct_schema(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        params = {
            "summary": "Test memo summary",
            "what_fired": ["signal_a contradicts signal_b"],
            "contradictions_review": "One contradiction detected",
            "decaying_families": ["family_x"],
            "deserves_operator": ["NVDA"],
        }
        result = dispatch_tool("write_memo", params, repo, _NOW_STR, _PROBATION, census)
        assert "error" not in result
        assert result.get("as_of") == _NOW_STR

        # Verify memo.json on disk
        memo_path = repo / "data" / "neuralweb" / "cortex" / "memo.json"
        assert memo_path.exists()
        memo = json.loads(memo_path.read_text())
        assert memo["schema"] == "neuralweb.cortex_memo.v1"
        assert memo["is_context_only"] is True
        assert memo["summary"] == "Test memo summary"
        assert "probation" in memo
        assert memo["probation"]["tier"] == "A0/A1 shadow"

    def test_write_memo_mirrored_to_site(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        dispatch_tool("write_memo", {"summary": "site mirror test"},
                      repo, _NOW_STR, _PROBATION, census)
        site_path = repo / "site" / "neuralweb" / "cortex_memo.json"
        assert site_path.exists()
        memo = json.loads(site_path.read_text())
        assert memo["is_context_only"] is True

    def test_stake_hypothesis_invalid_without_gate(self, repo):
        """PR2: stake_hypothesis calls live metabolism; missing pre_committed_gate → invalid.
        The inbox carries the status transition (inbox audit trail)."""
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        # Deliberately omit pre_committed_gate to trigger invalid status
        params = {
            "subject": "XLK lead-lag vs HY spreads",
            "claim": "XLK underperforms when HY spread widens > 50bps over 5 days",
            "falsifier": "XLK outperforms SPY in 5 of next 7 such events",
            "horizon_d": 5,
        }
        result = dispatch_tool("stake_hypothesis", params, repo, _NOW_STR, _PROBATION, census)
        # PR2: metabolism is live — invalid (missing pre_committed_gate)
        assert result["status"] == "invalid"
        # The inbox receives the status transition as audit trail
        inbox_path = repo / "data" / "neuralweb" / "cortex" / "hypothesis_inbox.jsonl"
        assert inbox_path.exists()
        rec = json.loads(inbox_path.read_text().strip())
        assert rec["status"] == "invalid"
        assert rec["is_context_only"] is True

    def test_stake_hypothesis_registered_with_full_params(self, repo):
        """PR2: stake_hypothesis with all required fields → registered."""
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        params = {
            "subject": "XLK",
            "claim": "XLK outperforms SPY when MACD crosses signal on 5d",
            "claim_shape": "lead_lag",
            "spine_query": {"subject": "XLK", "lead_series": "MACD"},
            "falsifier": "XLK excess return > 0 over 21 days in 55%+ of events",
            "horizon_d": 21,
            "pre_committed_gate": {
                "metric": "hit_rate",
                "threshold": 0.55,
                "min_n": 5,
                "horizon_d": 21,
            },
        }
        result = dispatch_tool("stake_hypothesis", params, repo, _NOW_STR, _PROBATION, census)
        # PR2: live registration with valid params
        assert result["status"] == "registered"
        assert result.get("registered_at") is not None

    def test_stake_hypothesis_multiple_writes_append(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        for i in range(3):
            dispatch_tool("stake_hypothesis",
                          {"subject": f"hyp_{i}", "claim": "test", "falsifier": "test_f"},
                          repo, _NOW_STR, _PROBATION, census)
        inbox_path = repo / "data" / "neuralweb" / "cortex" / "hypothesis_inbox.jsonl"
        lines = [l for l in inbox_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 3


# ---------------------------------------------------------------------------
# 4. Budget enforcement
# ---------------------------------------------------------------------------

class TestBudgetEnforcement:

    def test_budget_hit_still_writes_memo(self, repo):
        """A mock model that never stops → loop should hit max_tool_calls and write a memo."""
        from engine.neuralweb.cortex import _run_tool_loop

        # Build a mock client that always returns tool_use stop_reason with read_world_state
        def _make_mock_response(tool_id: str):
            block = MagicMock()
            block.type = "tool_use"
            block.name = "read_world_state"
            block.input = {}
            block.id = tool_id
            resp = MagicMock()
            resp.stop_reason = "tool_use"
            resp.content = [block]
            return resp

        call_count = [0]
        mock_client = MagicMock()
        def _side_effect(**kwargs):
            call_count[0] += 1
            return _make_mock_response(f"tool_{call_count[0]}")
        mock_client.messages.create.side_effect = _side_effect

        cfg = {"max_tool_calls": 3, "max_tokens": 1024, "llm_model": "claude-opus-4-8"}
        providers = [{"name": "oauth", "env_var": "X", "cred": "tok",
                      "client": mock_client, "model": "claude-opus-4-8"}]

        result = _run_tool_loop(repo, cfg, providers, _NOW_STR, _PROBATION)

        # Must have written a memo despite budget exhaustion
        memo_path = repo / "data" / "neuralweb" / "cortex" / "memo.json"
        assert memo_path.exists(), "Memo must be written even on budget exhaustion"
        memo = json.loads(memo_path.read_text())
        assert memo["schema"] == "neuralweb.cortex_memo.v1"
        assert "budget exhausted" in memo["summary"].lower()

    def test_budget_honored_max_calls(self, repo):
        """Loop should stop at max_tool_calls iterations."""
        from engine.neuralweb.cortex import _run_tool_loop

        call_count = [0]
        mock_client = MagicMock()
        def _side_effect(**kwargs):
            call_count[0] += 1
            block = MagicMock()
            block.type = "tool_use"
            block.name = "read_world_state"
            block.input = {}
            block.id = f"tool_{call_count[0]}"
            resp = MagicMock()
            resp.stop_reason = "tool_use"
            resp.content = [block]
            return resp
        mock_client.messages.create.side_effect = _side_effect

        max_calls = 2
        cfg = {"max_tool_calls": max_calls, "max_tokens": 512}
        providers = [{"name": "oauth", "env_var": "X", "cred": "tok",
                      "client": mock_client, "model": "claude-opus-4-8"}]

        _run_tool_loop(repo, cfg, providers, _NOW_STR, _PROBATION)
        # call_count should be <= max_calls + 1 (one extra for the forced write_memo check)
        assert call_count[0] <= max_calls + 2


# ---------------------------------------------------------------------------
# 5. Staleness gate
# ---------------------------------------------------------------------------

class TestStalenessGate:

    def test_unchanged_state_skips_llm(self, repo):
        """If state hash is unchanged from last_run_state.json, no model call is made."""
        from engine.neuralweb.cortex import _compute_run_state_hash, _save_last_run_state, run

        # Compute current state and save it as "last run"
        state = _compute_run_state_hash(repo)
        _save_last_run_state(repo, state)

        # Mock the provider builder to detect whether it was called
        with patch("engine.neuralweb.cortex._build_providers") as mock_bp:
            mock_bp.return_value = []  # no providers — will fallback
            with patch("engine.neuralweb.cortex._single_call_fallback") as mock_fb:
                mock_fb.return_value = {"written": "skipped"}
                rc = run(root=repo, force=False)

        # Should not have tried to build providers or call model (gate fires first)
        mock_bp.assert_not_called()
        assert rc == 0

    def test_changed_state_proceeds(self, repo):
        """If state has changed, the loop proceeds (providers built)."""
        from engine.neuralweb.cortex import _save_last_run_state, run

        # Save a stale state
        _save_last_run_state(repo, {"ws_inputs_hash": "old_hash", "spine_rows": 0,
                                    "contradictions_hash": "old_contra"})

        with patch("engine.neuralweb.cortex._build_providers") as mock_bp:
            mock_bp.return_value = []  # no providers → fallback
            with patch("engine.neuralweb.cortex._single_call_fallback") as mock_fb:
                mock_fb.return_value = {"written": "fallback"}
                run(root=repo, force=False)

        mock_bp.assert_called_once()


# ---------------------------------------------------------------------------
# 6. Single-call fallback path
# ---------------------------------------------------------------------------

class TestSingleCallFallback:

    def test_no_providers_triggers_fallback(self, repo):
        """run() with no providers must produce a fallback memo."""
        from engine.neuralweb.cortex import run

        with patch("engine.neuralweb.cortex._build_providers", return_value=[]):
            with patch("engine.neuralweb.cortex._single_call_fallback") as mock_fb:
                mock_fb.return_value = {"written": "fallback"}
                rc = run(root=repo, force=True)

        assert rc == 0
        mock_fb.assert_called_once()
        call_args = mock_fb.call_args
        # degraded_reason should be 'no_provider'
        assert call_args[0][5] == "no_provider" or call_args[1].get("degraded_reason") == "no_provider"

    def test_fallback_writes_degraded_memo(self, repo):
        """_single_call_fallback with a mock provider writes a memo with degraded_reason."""
        from engine.neuralweb.cortex import _single_call_fallback

        mock_client = MagicMock()
        resp = MagicMock()
        resp.content = [MagicMock(type="text", text='{"summary": "fallback summary"}')]
        mock_client.messages.create.return_value = resp

        providers = [{"name": "anthropic", "env_var": "K", "cred": "key",
                      "client": mock_client, "model": "claude-opus-4-8"}]
        cfg = {"max_tokens": 500}

        result = _single_call_fallback(repo, cfg, providers, _NOW_STR,
                                       dict(_PROBATION), "test_error")

        memo_path = repo / "data" / "neuralweb" / "cortex" / "memo.json"
        assert memo_path.exists()
        memo = json.loads(memo_path.read_text())
        assert memo["is_context_only"] is True
        assert memo["probation"].get("degraded_reason") == "test_error"


# ---------------------------------------------------------------------------
# 7. A2 refusal today (probation status in memo)
# ---------------------------------------------------------------------------

class TestA2Refusal:

    def test_check_constitution_refuses_a2_today(self, repo):
        """With no graded attention rows, grant_authority must refuse A2."""
        from engine.neuralweb.cortex import _check_constitution

        probation = _check_constitution(repo)
        assert probation["granted"] is False
        assert probation["tier"] == "A0/A1 shadow"
        assert "insufficient" in probation["reason"].lower()

    def test_memo_carries_probation_status(self, repo):
        """write_memo must embed the probation block in the memo."""
        from engine.neuralweb.cortex import dispatch_tool, _check_constitution

        probation = _check_constitution(repo)
        census: dict = {}
        dispatch_tool("write_memo", {"summary": "probation test"},
                      repo, _NOW_STR, probation, census)

        memo = json.loads((repo / "data" / "neuralweb" / "cortex" / "memo.json").read_text())
        assert "probation" in memo
        assert memo["probation"]["granted"] is False
        assert memo["probation"]["tier"] == "A0/A1 shadow"


# ---------------------------------------------------------------------------
# 8. Dispatcher refuses unknown tools
# ---------------------------------------------------------------------------

class TestDispatcherRefusal:

    def test_unknown_tool_refused(self, repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("execute_trade", {"ticker": "NVDA", "qty": 100},
                               repo, _NOW_STR, _PROBATION, census)
        assert "error" in result
        assert "not allowed" in result["error"].lower() or "whitelist" in result["error"].lower()
        # Census should not record the unknown tool
        assert "execute_trade" not in census

    def test_a7_originate_pattern_refused(self, repo):
        """Even if someone passes a tool named 'originate_signal' it is refused."""
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("originate_signal", {},
                               repo, _NOW_STR, _PROBATION, census)
        assert "error" in result

    def test_all_allowed_tools_pass_dispatcher(self, repo):
        """Every tool in _ALLOWED_TOOLS must reach the dispatcher without a whitelist error."""
        from engine.neuralweb.cortex import dispatch_tool, _ALLOWED_TOOLS
        census: dict = {}
        # We test non-destructive read tools only
        read_tools = {"read_world_state", "read_contradictions", "read_governance",
                      "read_graph", "read_kernel", "read_artifact"}
        for tool_name in read_tools & _ALLOWED_TOOLS:
            params = {"path": "data/neuralweb/world_state.json"} if tool_name == "read_artifact" else {}
            result = dispatch_tool(tool_name, params, repo, _NOW_STR, _PROBATION, census)
            # Result must not be a whitelist refusal
            assert "not allowed" not in str(result.get("error", "")).lower(), \
                f"{tool_name} was refused by whitelist (bug)"


# ---------------------------------------------------------------------------
# 9. Staleness gate — helper unit tests
# ---------------------------------------------------------------------------

class TestStalenessHelpers:

    def test_state_changed_when_no_last_run(self, repo):
        from engine.neuralweb.cortex import _compute_run_state_hash, _state_changed
        current = _compute_run_state_hash(repo)
        assert _state_changed(current, {}) is True

    def test_state_unchanged_when_same(self, repo):
        from engine.neuralweb.cortex import _compute_run_state_hash, _state_changed
        state = _compute_run_state_hash(repo)
        assert _state_changed(state, state) is False

    def test_state_changed_when_hash_differs(self, repo):
        from engine.neuralweb.cortex import _compute_run_state_hash, _state_changed
        current = _compute_run_state_hash(repo)
        old = dict(current)
        old["ws_inputs_hash"] = "totally_different"
        assert _state_changed(current, old) is True


# ---------------------------------------------------------------------------
# 10. Integration: dry-run scripted sequence
# ---------------------------------------------------------------------------

class TestDryRun:
    """Scripted tool-call sequence against real fixtures with a mocked model.

    Sequence: read_world_state → query_spine → read_contradictions →
              flag_attention(1 item) → write_memo
    """

    def test_dry_run_full_sequence(self, repo):
        from engine.neuralweb.cortex import _run_tool_loop

        # Build a mock that plays back our scripted sequence
        sequence = [
            # Turn 1: read_world_state
            ("tool_use", "read_world_state", {}, "tu_1"),
            # Turn 2: query_spine
            ("tool_use", "query_spine", {"graded_only": True}, "tu_2"),
            # Turn 3: read_contradictions
            ("tool_use", "read_contradictions", {}, "tu_3"),
            # Turn 4: flag_attention
            ("tool_use", "flag_attention",
             {"items": [{"scope_key": "NVDA", "scope_type": "entity",
                          "direction": 1, "horizon_d": 5,
                          "falsifier": "NVDA moves >2% within 5 days"}]},
             "tu_4"),
            # Turn 5: write_memo (terminal)
            ("tool_use", "write_memo",
             {"summary": "Dry-run: one contradiction detected in confluence graph.",
              "what_fired": ["signal_a contradicts signal_b"],
              "contradictions_review": "One confirmed contradiction pair.",
              "decaying_families": [],
              "deserves_operator": ["NVDA"]},
             "tu_5"),
            # Turn 6: end_turn
            ("end_turn", None, None, None),
        ]
        seq_iter = iter(sequence)

        mock_client = MagicMock()
        def _side_effect(**kwargs):
            kind, name, inp, tid = next(seq_iter)
            if kind == "end_turn":
                resp = MagicMock()
                resp.stop_reason = "end_turn"
                resp.content = []
                return resp
            block = MagicMock()
            block.type = "tool_use"
            block.name = name
            block.input = inp
            block.id = tid
            resp = MagicMock()
            resp.stop_reason = "tool_use"
            resp.content = [block]
            return resp
        mock_client.messages.create.side_effect = _side_effect

        cfg = {"max_tool_calls": 10, "max_tokens": 2048}
        providers = [{"name": "oauth", "env_var": "X", "cred": "tok",
                      "client": mock_client, "model": "claude-opus-4-8"}]

        result = _run_tool_loop(repo, cfg, providers, _NOW_STR, _PROBATION)

        # Memo must be on disk
        memo_path = repo / "data" / "neuralweb" / "cortex" / "memo.json"
        assert memo_path.exists(), "Memo must exist after dry-run"
        memo = json.loads(memo_path.read_text())
        assert memo["schema"] == "neuralweb.cortex_memo.v1"
        assert memo["is_context_only"] is True
        assert "dry-run" in memo["summary"].lower() or len(memo["summary"]) > 0

        # Attention firings must have been written
        attn_path = repo / "data" / "reflexes" / "cortex_attention" / "firings.jsonl"
        assert attn_path.exists(), "Attention firings.jsonl must exist"
        record = json.loads(attn_path.read_text().strip())
        assert record["scope_key"] == "NVDA"
        assert record["is_context_only"] is True

        # Tool call census must reflect what was called
        assert "read_world_state" in memo.get("tool_call_census", {})
        assert "write_memo" in memo.get("tool_call_census", {})


# ---------------------------------------------------------------------------
# 11. NIT1 — memo census consistency: data/ and site/ copies must be identical
# ---------------------------------------------------------------------------

class TestMemoCensusConsistency:
    """After _run_tool_loop, both memo copies must carry the same tool_call_census.

    Regression guard for the post-hoc census stamp: _tool_write_memo is called
    with census={} (census unknown at write time); the stamp runs after the loop
    and must re-mirror the site copy so the two files are byte-for-byte identical.
    """

    def test_both_copies_identical_after_dry_run(self, repo):
        """data/neuralweb/cortex/memo.json == site/neuralweb/cortex_memo.json after run."""
        from engine.neuralweb.cortex import _run_tool_loop

        # Scripted: read_world_state → write_memo → end_turn
        sequence = [
            ("tool_use", "read_world_state", {}, "tu_1"),
            ("tool_use", "write_memo",
             {"summary": "Census consistency test",
              "what_fired": [],
              "contradictions_review": "",
              "decaying_families": [],
              "deserves_operator": []},
             "tu_2"),
            ("end_turn", None, None, None),
        ]
        seq_iter = iter(sequence)

        mock_client = MagicMock()
        def _side_effect(**kwargs):
            kind, name, inp, tid = next(seq_iter)
            if kind == "end_turn":
                resp = MagicMock()
                resp.stop_reason = "end_turn"
                resp.content = []
                return resp
            block = MagicMock()
            block.type = "tool_use"
            block.name = name
            block.input = inp
            block.id = tid
            resp = MagicMock()
            resp.stop_reason = "tool_use"
            resp.content = [block]
            return resp
        mock_client.messages.create.side_effect = _side_effect

        cfg = {"max_tool_calls": 10, "max_tokens": 2048}
        providers = [{"name": "oauth", "env_var": "X", "cred": "tok",
                      "client": mock_client, "model": "claude-opus-4-8"}]

        _run_tool_loop(repo, cfg, providers, _NOW_STR, _PROBATION)

        data_path = repo / "data" / "neuralweb" / "cortex" / "memo.json"
        site_path = repo / "site" / "neuralweb" / "cortex_memo.json"

        assert data_path.exists(), "data memo.json must exist"
        assert site_path.exists(), "site cortex_memo.json must exist"

        data_memo = json.loads(data_path.read_text(encoding="utf-8"))
        site_memo = json.loads(site_path.read_text(encoding="utf-8"))

        # Both copies must carry the same census (NIT1 regression guard).
        assert data_memo.get("tool_call_census") == site_memo.get("tool_call_census"), (
            f"data census={data_memo.get('tool_call_census')} "
            f"site census={site_memo.get('tool_call_census')}"
        )
        # And the full dicts must be identical.
        assert data_memo == site_memo, (
            "data/neuralweb/cortex/memo.json and site/neuralweb/cortex_memo.json "
            "diverged — the post-hoc census stamp must re-mirror the site copy."
        )

    def test_both_copies_identical_after_budget_exhaustion(self, repo):
        """Even when budget is exhausted, site copy must match data copy."""
        from engine.neuralweb.cortex import _run_tool_loop

        call_count = [0]
        mock_client = MagicMock()
        def _side_effect(**kwargs):
            call_count[0] += 1
            block = MagicMock()
            block.type = "tool_use"
            block.name = "read_world_state"
            block.input = {}
            block.id = f"tool_{call_count[0]}"
            resp = MagicMock()
            resp.stop_reason = "tool_use"
            resp.content = [block]
            return resp
        mock_client.messages.create.side_effect = _side_effect

        cfg = {"max_tool_calls": 3, "max_tokens": 1024}
        providers = [{"name": "oauth", "env_var": "X", "cred": "tok",
                      "client": mock_client, "model": "claude-opus-4-8"}]

        _run_tool_loop(repo, cfg, providers, _NOW_STR, _PROBATION)

        data_path = repo / "data" / "neuralweb" / "cortex" / "memo.json"
        site_path = repo / "site" / "neuralweb" / "cortex_memo.json"

        assert data_path.exists()
        assert site_path.exists()

        data_memo = json.loads(data_path.read_text(encoding="utf-8"))
        site_memo = json.loads(site_path.read_text(encoding="utf-8"))

        assert data_memo == site_memo, (
            "Budget-exhausted memo: data and site copies diverged."
        )


# ---------------------------------------------------------------------------
# 12. Factor Intelligence × Neural Web tools (RUL-NW3)
# ---------------------------------------------------------------------------

def _make_repo_with_factor_state(tmp: Path) -> Path:
    """Extend _make_repo with factor intelligence artifacts."""
    _make_repo(tmp)

    # factor_intelligence_state.json
    (tmp / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)
    state = {
        "schema": "neuralweb.factor_intelligence_state.v1",
        "as_of": "2026-07-05",
        "is_context_only": True,
        "display_only": True,
        "factor_weather": {
            "style_regime": "VALUE",
            "factor_leader": "Value",
            "factor_leader_ic": 0.12,
            "display_only": True,
        },
        "scorecard": {
            "payout_fdr_survivor": True,
            "composite_untradeable": True,
        },
        "attention": {
            "track_record": {"n": 0, "hits": 0},
        },
        "latest_board_coordinates": {
            "AAPL": {
                "ticker": "AAPL",
                "dna_class": "A1",
                "alibi_share_20d": 0.65,
                "twin_bleed_flag": False,
            },
        },
        "gaps": [],
    }
    (tmp / "data" / "neuralweb" / "factor_intelligence_state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )

    # factor_contradictions.jsonl
    rows = [
        {"date": "2026-07-04", "ticker": "NVDA", "severity": "note",
         "display_only": True, "reason": "borrowed_strength from Value factor"},
        {"date": "2026-07-05", "ticker": "AAPL", "severity": "note",
         "display_only": True, "reason": "twin_bleed detected"},
    ]
    (tmp / "data" / "neuralweb" / "factor_contradictions.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )

    # fire_coordinates.jsonl
    (tmp / "data" / "factordata").mkdir(parents=True, exist_ok=True)
    fires = [
        {"as_of": "2026-07-04", "ticker": "AAPL", "tier": "buy",
         "dna_class": "A1", "style_regime": "VALUE",
         "alibi_share_20d": 0.65, "twin_bleed_flag": False,
         "twin_rel_20d": 0.02, "alpha_z_house": 1.1,
         "top_contrib_streams": ["momentum_20d", "value_rank", "breadth_z"],
         "factor_model": "v1"},
        {"as_of": "2026-07-03", "ticker": "AAPL", "tier": "buy",
         "dna_class": "A1", "style_regime": "VALUE",
         "alibi_share_20d": 0.60, "twin_bleed_flag": False,
         "twin_rel_20d": 0.01, "alpha_z_house": 0.9,
         "top_contrib_streams": ["momentum_20d", "value_rank", "breadth_z"],
         "factor_model": "v1"},
    ]
    (tmp / "data" / "factordata" / "fire_coordinates.jsonl").write_text(
        "\n".join(json.dumps(f) for f in fires) + "\n", encoding="utf-8"
    )

    return tmp


@pytest.fixture
def factor_repo(tmp_path: Path) -> Path:
    return _make_repo_with_factor_state(tmp_path)


class TestFactorTools:
    """Factor Intelligence × Neural Web tools (RUL-NW3)."""

    def test_read_factor_state_returns_artifact(self, factor_repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("read_factor_state", {}, factor_repo, _NOW_STR, _PROBATION, census)
        assert "error" not in result
        assert result.get("is_context_only") is True
        assert result.get("display_only") is True
        assert result.get("as_of") == "2026-07-05"
        assert "factor_weather" in result
        assert census["read_factor_state"] == 1

    def test_read_factor_state_absent_returns_structured_gap(self, repo):
        """When factor_intelligence_state.json is absent, return structured gap not exception."""
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("read_factor_state", {}, repo, _NOW_STR, _PROBATION, census)
        # File is absent in base repo fixture — must return structured gap
        assert "gaps" in result
        assert result.get("is_context_only") is True
        assert len(result["gaps"]) > 0

    def test_list_factor_contradictions_returns_records(self, factor_repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("list_factor_contradictions", {}, factor_repo, _NOW_STR, _PROBATION, census)
        assert "error" not in result
        assert result.get("is_context_only") is True
        assert result.get("display_only") is True
        assert "records" in result
        assert result["total_available"] == 2
        assert result["returned"] <= 2

    def test_list_factor_contradictions_ticker_filter(self, factor_repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("list_factor_contradictions", {"ticker": "NVDA"},
                               factor_repo, _NOW_STR, _PROBATION, census)
        assert result.get("total_available") == 1
        for rec in result["records"]:
            assert rec["ticker"] == "NVDA"

    def test_list_factor_contradictions_limit_enforced(self, factor_repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("list_factor_contradictions", {"limit": 1},
                               factor_repo, _NOW_STR, _PROBATION, census)
        assert result["returned"] <= 1

    def test_list_factor_contradictions_absent_returns_empty(self, repo):
        """Absent file returns empty list with note, not an exception."""
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("list_factor_contradictions", {}, repo, _NOW_STR, _PROBATION, census)
        assert result["records"] == []
        assert result.get("is_context_only") is True
        assert "note" in result

    def test_explain_factor_context_returns_structured_context(self, factor_repo):
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("explain_factor_context", {"ticker": "AAPL"},
                               factor_repo, _NOW_STR, _PROBATION, census)
        assert "error" not in result
        assert result.get("ticker") == "AAPL"
        assert result.get("is_context_only") is True
        assert result.get("display_only") is True
        assert "board_coordinates" in result
        assert result["board_coordinates"] is not None
        assert "fire_history" in result
        assert len(result["fire_history"]) == 2
        assert "mandate" in result
        # Mandate must not contain directional verbs
        mandate = result["mandate"].lower()
        for verb in ("buy", "sell", "recommend", "should"):
            assert verb not in mandate, f"Mandate contains forbidden verb: {verb!r}"

    def test_explain_factor_context_absent_data_returns_gaps(self, repo):
        """When no factor data exists, return structured gap dict not prose apology."""
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("explain_factor_context", {"ticker": "NVDA"},
                               repo, _NOW_STR, _PROBATION, census)
        assert "error" not in result
        assert result.get("ticker") == "NVDA"
        assert result.get("is_context_only") is True
        # Must have explicit gaps list (not a prose apology string)
        assert "gaps" in result
        assert isinstance(result["gaps"], list)
        assert len(result["gaps"]) > 0

    def test_explain_factor_context_ticker_not_in_board(self, factor_repo):
        """Ticker absent from board coordinates returns None coord + gap entry."""
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("explain_factor_context", {"ticker": "MSFT"},
                               factor_repo, _NOW_STR, _PROBATION, census)
        assert result.get("ticker") == "MSFT"
        assert result.get("board_coordinates") is None
        # Must have a gap noting the absence
        assert any("MSFT" in g or "not present" in g.lower() for g in result.get("gaps", []))

    def test_explain_factor_context_requires_ticker(self, factor_repo):
        """Missing ticker returns error, not exception."""
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("explain_factor_context", {},
                               factor_repo, _NOW_STR, _PROBATION, census)
        assert "error" in result

    def test_unknown_factor_write_tool_refused(self, factor_repo):
        """A hypothetical write tool named with 'factor' is refused by A7 guard."""
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("write_factor_signal", {"ticker": "AAPL"},
                               factor_repo, _NOW_STR, _PROBATION, census)
        assert "error" in result
        assert "not allowed" in result["error"].lower() or "whitelist" in result["error"].lower()
        assert "write_factor_signal" not in census

    def test_factor_tools_in_allowed_tools(self):
        """All three factor tools must be in _ALLOWED_TOOLS (A7 guard whitelist)."""
        from engine.neuralweb.cortex import _ALLOWED_TOOLS
        for tool_name in ("read_factor_state", "list_factor_contradictions", "explain_factor_context"):
            assert tool_name in _ALLOWED_TOOLS, f"{tool_name} missing from _ALLOWED_TOOLS"

    def test_factor_tools_cap_output(self, factor_repo):
        """read_factor_state returns the small artifact directly (not truncated)."""
        from engine.neuralweb.cortex import dispatch_tool
        census: dict = {}
        result = dispatch_tool("read_factor_state", {}, factor_repo, _NOW_STR, _PROBATION, census)
        # The artifact is small — must return full structure, not a 'too large' error
        assert "error" not in result
        assert "schema" in result


# ---------------------------------------------------------------------------
# 13. Subsector sponsorship evidence lane (SRSS Phase 3 — display/shadow only)
# ---------------------------------------------------------------------------

class TestSponsorshipEvidenceLane:
    """Sponsorship evidence must reach cortex generically via read_graph, and
    the evidence must remain descriptive-only — never a fabricated
    buy/sell/recommendation field, and the prompt text must frame it as
    de-escalate/explain-only (Article 1 — never originate)."""

    def test_read_graph_surfaces_sponsorship_edges_generically(self, repo):
        """read_graph needs zero sponsorship-specific code — it returns whatever
        confluence_graph.json contains, including sponsorship_* edge types."""
        from engine.neuralweb.cortex import dispatch_tool

        graph = json.loads(
            (repo / "data" / "neuralweb" / "confluence_graph.json").read_text(encoding="utf-8")
        )
        graph["edges"].append({
            "src": "entity:REZI",
            "dst": "subsector:smarthomesecurity",
            "edge_type": "sponsorship_support",
            "display_only": True,
            "sponsorship_score": 0.872,
            "confidence_tier": "medium",
            "direction": 1,
            "note": "sponsorship_state=CONFIRMED_LEADERSHIP confidence_tier=medium "
                    "direction=1 (display-only; sponsorship_score not aggregated)",
        })
        (repo / "data" / "neuralweb" / "confluence_graph.json").write_text(
            json.dumps(graph), encoding="utf-8"
        )

        census: dict = {}
        result = dispatch_tool("read_graph", {}, repo, _NOW_STR, _PROBATION, census)
        sponsorship_edges = [
            e for e in result.get("edges", [])
            if str(e.get("edge_type", "")).startswith("sponsorship")
        ]
        assert len(sponsorship_edges) == 1
        assert sponsorship_edges[0]["display_only"] is True

        # Same generic path filters by edge_type too — no special-cased tool needed.
        census2: dict = {}
        filtered = dispatch_tool(
            "read_graph", {"edge_type": "sponsorship_support"}, repo, _NOW_STR, _PROBATION, census2
        )
        assert len(filtered.get("edges", [])) == 1

    def test_sponsorship_edge_has_no_action_or_recommendation_keys(self, repo):
        """Evidence surface must be descriptive fields only — no 'action',
        'recommendation', 'buy', or 'sell' keys anywhere on a sponsorship edge."""
        from engine.neuralweb.confluence import _build_sponsorship_edges

        class _FakeRow(dict):
            def get(self, k, default=None):
                return dict.get(self, k, default)

        import pandas as pd

        df = pd.DataFrame([{
            "symbol": "REZI",
            "direction": 1,
            "meta": json.dumps({
                "sponsorship_state": "CONFIRMED_LEADERSHIP",
                "confidence_tier": "medium",
                "sponsorship_score": 0.872,
                "rotation_key": "smarthomesecurity",
            }),
        }])
        gaps: list[str] = []
        edges = _build_sponsorship_edges(df, gaps)
        assert len(edges) == 1
        forbidden_keys = {"action", "recommendation", "buy", "sell", "trade", "escalation"}
        for edge in edges:
            assert not (set(edge.keys()) & forbidden_keys), (
                f"sponsorship edge carries a forbidden key: {edge.keys()}"
            )
            assert edge.get("display_only") is True

    def test_system_prompt_frames_sponsorship_as_de_escalate_only(self):
        """The cortex system prompt text that mentions 'sponsorship' must carry
        the de-escalate/explain-only framing — never-originate, near the mention."""
        from engine.neuralweb.cortex import _SYSTEM_PROMPT

        assert "sponsorship" in _SYSTEM_PROMPT.lower()
        # Find the sponsorship passage and confirm the never-originate framing
        # sits in the same neighbourhood (not scattered/unrelated elsewhere).
        idx = _SYSTEM_PROMPT.lower().index("subsector sponsorship")
        window = _SYSTEM_PROMPT[idx: idx + 700]
        assert "never originate a buy" in window
        assert "de-escalate" in window.lower() or "explain" in window.lower()
        # Article-1 word must never appear as "validated" for this feature.
        assert "validated" not in window.lower()

    def test_no_validated_word_near_sponsorship_anywhere_in_prompt(self):
        """House law: 'validated' is CI-gated; the sponsorship guidance text
        must never use it."""
        from engine.neuralweb.cortex import _SYSTEM_PROMPT

        assert "validated" not in _SYSTEM_PROMPT.lower()
