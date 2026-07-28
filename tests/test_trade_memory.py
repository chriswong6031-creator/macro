from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from engine.neuralweb import trade_memory as tm
from engine.neuralweb.trade_memory_store import SupabaseTradeMemoryStore
from scripts.run_trade_memory import run


def _episode(**overrides):
    base = {
        "source": "operator",
        "ticker": "JNJ",
        "market": "us",
        "side": "long",
        "entry_date": "2026-06-10",
        "exit_date": "2026-07-20",
        "entry_price": 150,
        "exit_price": 180,
        "outcome": "win",
        "thesis_at_entry": "Healthcare looked washed out.",
        "observed_result": "Sector rotation and stock alpha both helped.",
        "prophet_pick_ref": "us-2026-06-09-JNJ",
    }
    base.update(overrides)
    return base


def _autopsy_json(feature_key="sector_rotation"):
    return json.dumps({
        "schema": tm.SCHEMA_AUTOPSY,
        "summary": "Healthcare rotation plus stock-specific strength drove the result.",
        "mitigation_verdict": "not_a_failure",
        "causal_chain": [
            {
                "order": 1,
                "layer": "market_rotation",
                "factor": "Defensive rotation",
                "mechanism": "Capital moved from technology toward healthcare.",
                "evidence_status": "corroborated",
                "timing_status": "known_at_entry",
                "counterfactual": "No sector inflow would weaken the case.",
                "evidence_refs": ["return_attribution.sector_minus_market"],
            }
        ],
        "alternate_explanations": ["Broad market beta"],
        "missing_evidence": ["Fund-flow receipt"],
        "lesson": "Separate sector beta from stock alpha.",
        "signal_hypotheses": [
            {
                "feature_key": feature_key,
                "feature": "Washed-out sector turns positive",
                "measurement": "Sector residual after a drawdown",
                "expected_direction": "positive",
                "falsifier": "No lift outside one rotation episode",
                "authority": "live_signal",  # parser must overwrite this
            }
        ],
    })


def test_normalize_episode_rejects_sensitive_position_fields():
    with pytest.raises(ValueError, match="does not store"):
        tm.normalize_episode(_episode(position_size=50_000))
    with pytest.raises(ValueError, match="does not store"):
        tm.normalize_episode(_episode(realized_pnl=12_000))


def test_normalize_episode_requires_closed_exit_and_price_pair():
    with pytest.raises(ValueError, match="exit_date"):
        tm.normalize_episode(_episode(exit_date=None))
    with pytest.raises(ValueError, match="both entry_price and exit_price"):
        tm.normalize_episode(_episode(exit_price=None))


def test_normalize_episode_allows_open_entry_but_rejects_open_exit():
    episode = tm.normalize_episode(
        _episode(outcome="open", exit_date=None, entry_price=150, exit_price=None)
    )
    assert episode["entry_price"] == 150.0
    assert episode["exit_price"] is None
    with pytest.raises(ValueError, match="open outcomes cannot have"):
        tm.normalize_episode(_episode(outcome="open", exit_date="2026-07-20"))
    with pytest.raises(ValueError, match="open outcomes cannot have"):
        tm.normalize_episode(_episode(outcome="open", exit_date=None, exit_price=180))


def test_build_evidence_packet_decomposes_market_sector_stock(monkeypatch, tmp_path):
    idx = pd.to_datetime(["2026-06-10", "2026-06-20", "2026-07-20"])
    prices = {
        "JNJ": pd.Series([150.0, 170.0, 180.0], index=idx),
        "SPY": pd.Series([600.0, 606.0, 612.0], index=idx),
        "XLV": pd.Series([140.0, 147.0, 154.0], index=idx),
    }
    monkeypatch.setattr(tm, "_load_close", lambda root, ticker: prices.get(ticker))
    monkeypatch.setattr(tm, "_sector_for", lambda root, ticker: "Health Care")
    with patch(
        "engine.neuralweb.context_api.context_snapshot",
        return_value={"ticker": "JNJ", "date": "2026-06-10", "dimensions": {}},
    ):
        packet = tm.build_evidence_packet(_episode(), root=tmp_path)

    attr = packet["return_attribution"]
    assert attr["stock"]["return"] == pytest.approx(0.20)
    assert attr["market"]["return"] == pytest.approx(0.02)
    assert attr["sector_leg"]["return"] == pytest.approx(0.10)
    assert attr["sector_minus_market"] == pytest.approx(0.08)
    assert attr["stock_minus_sector"] == pytest.approx(0.10)
    assert attr["method"].endswith("not causal")
    assert packet["epistemic_rules"]["direct_authority"] is False


def test_parse_autopsy_enforces_closed_enums_and_research_only():
    packet = {"episode": {**_episode(), "id": "ep-1"}}
    parsed = tm.parse_autopsy(_autopsy_json(), packet)
    assert parsed is not None
    assert parsed["direct_authority"] is False
    assert parsed["causal_chain"][0]["timing_status"] == "known_at_entry"
    hypothesis = parsed["signal_hypotheses"][0]
    assert hypothesis["authority"] == "research_only"
    assert hypothesis["direct_authority"] is False

    raw = json.loads(_autopsy_json())
    raw["mitigation_verdict"] = "certain_winner"
    raw["causal_chain"][0]["evidence_status"] = "obviously_true"
    parsed_bad = tm.parse_autopsy(json.dumps(raw), packet)
    assert parsed_bad["mitigation_verdict"] == "invalid"
    assert parsed_bad["causal_chain"][0]["evidence_status"] == "unknown"


def test_pattern_gate_requires_contradiction_cases_and_time_clusters():
    rows = []
    specs = [
        ("1", "2026-01-02", "win"),
        ("2", "2026-02-03", "win"),
        ("3", "2026-03-04", "win"),
        ("4", "2026-03-05", "loss"),
        ("5", "2026-04-06", "flat"),
    ]
    for episode_id, entry_date, outcome in specs:
        parsed = tm.parse_autopsy(
            _autopsy_json(),
            {"episode": {"id": episode_id, "ticker": "X", "entry_date": entry_date, "outcome": outcome}},
        )
        rows.append(parsed)
    candidates = tm.build_pattern_candidates(rows)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["status"] == "ready_for_prereg"
    assert candidate["support_n"] == 3
    assert candidate["contradict_n"] == 2
    assert candidate["time_cluster_n"] == 4
    assert candidate["direct_authority"] is False

    only_wins = [r for r in rows if r["outcome"] == "win"]
    assert tm.build_pattern_candidates(only_wins)[0]["status"] == "accruing"


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = [] if payload is None else payload

    def json(self):
        return self._payload


class _Session:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return _Response(200, [{"id": "row"}])

    def patch(self, url, **kwargs):
        self.calls.append(("patch", url, kwargs))
        return _Response(204)

    def delete(self, url, **kwargs):
        self.calls.append(("delete", url, kwargs))
        return _Response(204)

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return _Response(201)


def test_store_scopes_every_episode_operation_to_operator():
    owner = "123e4567-e89b-42d3-a456-426614174000"
    session = _Session()
    store = SupabaseTradeMemoryStore(
        "https://example.supabase.co", "secret", owner, session=session
    )
    assert store.available
    assert store.fetch_pending(limit=3) == [{"id": "row"}]
    assert store.update_episode(
        "123e4567-e89b-42d3-a456-426614174001",
        {"autopsy_state": "complete", "user_id": "attacker"},
    )
    get_params = session.calls[0][2]["params"]
    patch_call = next(c for c in session.calls if c[0] == "patch")
    assert get_params["user_id"] == f"eq.{owner}"
    assert patch_call[2]["params"]["user_id"] == f"eq.{owner}"
    assert "attacker" not in patch_call[2]["data"]


class _FakeStore:
    available = True

    def __init__(self):
        self.updates = []
        self.patterns = None

    def fetch_pending(self, limit=8):
        return [{"id": "123e4567-e89b-42d3-a456-426614174001", **_episode()}]

    def update_episode(self, episode_id, patch):
        self.updates.append((episode_id, patch))
        return True

    def fetch_autopsied(self, limit=500):
        complete = next(p for _, p in self.updates if p.get("autopsy_state") == "complete")
        return [{
            "id": "123e4567-e89b-42d3-a456-426614174001",
            "entry_date": "2026-06-10",
            "outcome": "win",
            "autopsy": complete["autopsy"],
        }]

    def replace_patterns(self, patterns):
        self.patterns = patterns
        return True


def test_runner_writes_private_autopsy_and_rebuilds_patterns(monkeypatch, tmp_path):
    monkeypatch.setattr(
        tm,
        "build_evidence_packet",
        lambda episode, root=None: {"schema": tm.SCHEMA_EVIDENCE, "episode": tm.normalize_episode(episode)},
    )
    store = _FakeStore()
    result = run(
        store,
        root=tmp_path,
        model_caller=lambda system, user: _autopsy_json(),
    )
    assert result["completed"] == 1
    assert result["failed"] == 0
    assert any(p.get("autopsy_state") == "complete" for _, p in store.updates)
    assert store.patterns[0]["authority"] == "research_only"


def test_prophet_pick_autopsies_join_private_pattern_rebuild(tmp_path):
    from scripts.run_trade_memory import _load_prophet_pick_autopsies

    target = (
        tmp_path
        / "data"
        / "standout_audit"
        / "pick_autopsies"
        / "us"
        / "JNJ-2026-06-01-buy.json"
    )
    target.parent.mkdir(parents=True)
    hypotheses = [{
        "feature_key": "sector_rotation",
        "feature": "Washed-out sector rotation",
        "measurement": "Sector return minus market return",
        "authority": "research_only",
        "direct_authority": False,
    }]
    target.write_text(json.dumps({
        "schema": "prophet.pick_autopsy/v2",
        "pick_id": "JNJ-2026-06-01-buy",
        "entry_date": "2026-06-01",
        "attribution": {"excess_spy": 0.08},
        "llm": {"signal_hypotheses": hypotheses},
    }), encoding="utf-8")

    assert _load_prophet_pick_autopsies(tmp_path) == [{
        "episode_ref": "prophet:JNJ-2026-06-01-buy",
        "entry_date": "2026-06-01",
        "outcome": "win",
        "signal_hypotheses": hypotheses,
        "authority": "research_only",
        "direct_authority": False,
    }]
