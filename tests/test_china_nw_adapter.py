"""Tests for CN-SYS W7 Neural Web adapter.

All tests are offline (no network, no real market data).

Test coverage:
1.  world_state_china_lobe_present        — market_state artifact present → lobe populated
2.  world_state_china_lobe_absent         — artifact missing → available=False, no raise
3.  world_state_china_lobe_stale          — artifact with old as_of → available=False (stale)
4.  world_state_china_lobe_authority      — authority="context_only", display_only=True always
5.  world_state_china_lobe_contradictions — contradictions_count extracted correctly
6.  world_state_china_lobe_in_payload     — china_market_state key present in build_world_state
7.  ask_brain_china_router_keywords       — China keyword triggers _CHINA_TRIGGER_TERMS
8.  ask_brain_china_router_budget         — China question returns _BUDGET_CHINA and read_world_state seed
9.  ask_brain_china_ticker_pattern        — A-share 6-digit numeric triggers China router
10. ask_brain_china_packet_present        — assemble_china_decision_packet from fixture
11. ask_brain_china_packet_absent         — assemble_china_decision_packet → available=False
12. daily_brief_china_block_present       — build() includes china_market_state key
13. daily_brief_china_block_absent        — missing artifact → available=False with note
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Minimal synapse stub so world_state envelope doesn't fail
# ---------------------------------------------------------------------------

def _write_minimal_synapse(root: Path) -> None:
    """Write a minimal synapse.yml stub so envelope stamp doesn't crash."""
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    stub = "meta:\n  version: '1.0'\nartifacts: {}\n"
    (config_dir / "synapse.yml").write_text(stub)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_GOOD_MARKET_STATE = {
    "schema": "china_market_state.v1",
    "as_of": "2026-07-08",
    "generated_utc": "2026-07-08T10:00:00Z",
    "authority": {
        "tier": "context_only",
    },
    "phase": {
        "phase": "POLICY_PUT",
        "confidence": 0.75,
        "evidence": ["turnover_z20_null"],
        "falsifiers": [
            {"id": "POLI_PP_LUP_RECOVERING", "expr": "lup5 > 1.0", "horizon_d": 10},
        ],
    },
    "participation": {
        "as_of": "2026-07-06",
        "regime": "unclear",
        "who_controls": "offshore",
        "risk": "normal",
        "contradictions": [
            {"a": "southbound_z=2.04 (inflow)", "b": "broker_rs=-0.0465 (negative)",
             "detail": "cross-market split"},
        ],
    },
    "microstructure": {
        "as_of": "2026-07-07",
        "aggregate": {
            "limit_up_count": 9.0,
            "limit_down_count": 5.0,
            "sealed_up_close": 5.0,
            "failed_up_seal_count": 4.0,
            "lianban_max": 1.0,
        },
        "name_summary": {
            "n_packets": 122,
            "chase_veto_count": 8,
            "fillable_count": 122,
        },
    },
    "policy": {
        "as_of": "2026-07-08",
        "policy_impulse": "targeted_support",
        "transmission_channel": ["fiscal_or_structural", "liquidity"],
    },
    "rotation": {
        "as_of": "2026-07-07",
        "sector_leaders": ["Electronics 75.5%", "Telecoms 67.7%"],
        "ths_heat": {
            "hot_baskets": [{"id": "ths_storage_chip", "ret_60d": 0.75}],
        },
    },
    "contradictions": [],
    "data_gaps": ["participation: northbound:DEAD post-2024-08-16 SLF-050"],
}


def _make_root_with_market_state(
    content: dict | None = _GOOD_MARKET_STATE,
    as_of_override: str | None = None,
) -> Path:
    """Create a temp root with site/chinastatedata/market_state.json."""
    d = Path(tempfile.mkdtemp())
    china_dir = d / "site" / "chinastatedata"
    china_dir.mkdir(parents=True, exist_ok=True)

    if content is not None:
        out = dict(content)
        if as_of_override is not None:
            out["as_of"] = as_of_override
        (china_dir / "market_state.json").write_text(
            json.dumps(out), encoding="utf-8"
        )

    _write_minimal_synapse(d)
    return d


# ---------------------------------------------------------------------------
# Tests 1–6: world_state china_market_state lobe
# ---------------------------------------------------------------------------

from engine.neuralweb.world_state import _compose_china_market_state, build_world_state


class TestWorldStateChinaLobe:

    def test_present(self):
        """Artifact present → available=True, expected fields populated."""
        root = _make_root_with_market_state()
        lobe = _compose_china_market_state(root=root)
        assert lobe["available"] is True
        assert lobe["phase"]["label"] == "POLICY_PUT"
        assert lobe["phase"]["confidence"] == 0.75
        assert lobe["participation"]["who_controls"] == "offshore"
        assert lobe["participation"]["risk"] == "normal"
        assert lobe["policy_impulse"] == "targeted_support"
        assert lobe["microstructure"]["limit_up_count"] == 9.0
        assert lobe["microstructure"]["chase_veto_count"] == 8
        assert lobe["data_gaps_count"] == 1

    def test_absent(self):
        """Artifact missing → available=False, no exception."""
        root = _make_root_with_market_state(content=None)
        lobe = _compose_china_market_state(root=root)
        assert lobe["available"] is False
        assert "note" in lobe

    def test_stale(self):
        """Artifact with as_of=2020-01-01 (>30h stale) → available=False (stale)."""
        root = _make_root_with_market_state(as_of_override="2020-01-01")
        lobe = _compose_china_market_state(root=root)
        assert lobe["available"] is False
        assert "stale" in (lobe.get("note") or "")

    def test_authority(self):
        """authority='context_only', display_only=True always."""
        root = _make_root_with_market_state()
        lobe = _compose_china_market_state(root=root)
        assert lobe["authority"] == "context_only"
        assert lobe["display_only"] is True

    def test_authority_always_true_on_absent(self):
        """display_only=True even when artifact is absent."""
        root = _make_root_with_market_state(content=None)
        lobe = _compose_china_market_state(root=root)
        assert lobe["display_only"] is True

    def test_contradictions_count(self):
        """contradictions_count extracted from participation.contradictions."""
        root = _make_root_with_market_state()
        lobe = _compose_china_market_state(root=root)
        # _GOOD_MARKET_STATE has 1 contradiction in participation.contradictions
        assert lobe["contradictions_count"] == 1
        assert lobe["top_contradiction"] is not None
        assert "a" in lobe["top_contradiction"]
        assert "b" in lobe["top_contradiction"]

    def test_in_payload(self):
        """build_world_state() payload includes 'china_market_state' key."""
        root = _make_root_with_market_state()
        payload = build_world_state(root=root)
        assert "china_market_state" in payload


# ---------------------------------------------------------------------------
# Tests 7–11: ask_brain China routing
# ---------------------------------------------------------------------------

from engine.neuralweb.ask_brain import (
    _CHINA_TRIGGER_TERMS,
    _BUDGET_CHINA,
    _classify_question,
    assemble_china_decision_packet,
)


class TestAskBrainChinaRouter:

    @pytest.mark.parametrize("question", [
        "What is the A-share market phase?",
        "CSI 300 regime this week?",
        "PBOC policy impulse for china market",
        "who controls the mainland china market",
        "什么是A股当前阶段",
        "southbound flow trend",
        "china policy phase",
        "What is QVIX showing?",
        "涨停板数量",
    ])
    def test_china_trigger_keywords(self, question: str):
        """Known China terms trigger _CHINA_TRIGGER_TERMS."""
        assert _CHINA_TRIGGER_TERMS.search(question) is not None, (
            f"Expected China trigger for: {question!r}"
        )

    @pytest.mark.parametrize("question", [
        "What is the US regime?",
        "Factor weather for SPY",
        "Goldman options flow",
    ])
    def test_non_china_no_trigger(self, question: str):
        """Non-China questions do NOT trigger _CHINA_TRIGGER_TERMS."""
        assert _CHINA_TRIGGER_TERMS.search(question) is None, (
            f"Expected NO China trigger for: {question!r}"
        )

    def test_china_router_budget_and_seed(self):
        """China question returns _BUDGET_CHINA budget and read_world_state seed."""
        budget, seeds = _classify_question("What is the A-share phase?", None)
        assert budget == _BUDGET_CHINA
        assert "read_world_state" in seeds

    def test_a_share_6digit_ticker(self):
        """6-digit A-share ticker pattern triggers China router."""
        # 600519 (Kweichow Moutai) — canonical A-share ticker
        assert _CHINA_TRIGGER_TERMS.search("What is the setup for 600519?") is not None

    def test_hk_ticker_trigger(self):
        """HK-listed ticker (XXXX.HK) triggers China router."""
        assert _CHINA_TRIGGER_TERMS.search("Tell me about 0700.HK") is not None

    def test_factor_question_does_not_trigger_china(self):
        """Factor-question routing takes precedence — China path not invoked."""
        # "factor leader" hits FACTOR_TRIGGER_TERMS first in _classify_question
        budget, seeds = _classify_question("What is the factor leader this week?", None)
        # Should route to factor budget (_BUDGET_FACTOR=6), not china (_BUDGET_CHINA=5)
        from engine.neuralweb.ask_brain import _BUDGET_FACTOR
        assert budget == _BUDGET_FACTOR


class TestChinaDecisionPacket:

    def test_packet_present(self):
        """assemble_china_decision_packet with fixture → available=True, correct shape."""
        root = _make_root_with_market_state()
        pkt = assemble_china_decision_packet(root=root)
        assert pkt["available"] is True
        assert pkt["schema"] == "china_decision_packet.v1"
        assert pkt["market_phase"]["label"] == "POLICY_PUT"
        assert pkt["policy_liquidity"]["impulse"] == "targeted_support"
        assert pkt["participation"]["who_controls"] == "offshore"
        assert pkt["participation"]["northbound_note"] is not None
        assert pkt["execution_constraints"]["chase_veto_count"] == 8
        assert pkt["authority"]["originates_signal"] is False
        assert pkt["authority"]["can_de_escalate"] is False
        assert pkt["authority"]["tier"] == "context_only"

    def test_packet_absent(self):
        """assemble_china_decision_packet without artifact → available=False."""
        root = _make_root_with_market_state(content=None)
        pkt = assemble_china_decision_packet(root=root)
        assert pkt["available"] is False
        assert pkt["authority"]["originates_signal"] is False

    def test_action_context_no_trade_verbs(self):
        """action_context must not contain forbidden trading verbs."""
        root = _make_root_with_market_state()
        pkt = assemble_china_decision_packet(root=root)
        ac = pkt.get("action_context", "")
        forbidden = ["buy", "sell", "hold", "add", "trim", "long", "short",
                     "overweight", "underweight"]
        for verb in forbidden:
            assert verb.lower() not in ac.lower(), (
                f"Trading verb '{verb}' found in action_context: {ac!r}"
            )


# ---------------------------------------------------------------------------
# Tests 12–13: daily_brief China block
# ---------------------------------------------------------------------------

from engine.neuralweb.daily_brief import _build_china_market_state_block


class TestDailyBriefChinaBlock:

    def test_present(self):
        """Market state artifact present → block has expected fields."""
        root = _make_root_with_market_state()
        block = _build_china_market_state_block(root)
        assert block["available"] is True
        assert block["phase"] == "POLICY_PUT"
        assert block["who_controls"] == "offshore"
        assert block["policy_impulse"] == "targeted_support"
        assert block["display_only"] is True
        assert block["data_gaps_count"] == 1

    def test_absent(self):
        """Artifact missing → available=False with note."""
        root = _make_root_with_market_state(content=None)
        block = _build_china_market_state_block(root)
        assert block["available"] is False
        assert "note" in block
        assert block["display_only"] is True

    def test_in_build_output(self):
        """build() includes 'china_market_state' key at top level."""
        from engine.neuralweb.daily_brief import build
        root = _make_root_with_market_state()
        payload = build(root=root)
        assert "china_market_state" in payload

    def test_top_contradiction_extracted(self):
        """top_contradiction pulled from participation.contradictions."""
        root = _make_root_with_market_state()
        block = _build_china_market_state_block(root)
        top = block.get("top_contradiction")
        assert top is not None
        assert "a" in top
        assert "b" in top
