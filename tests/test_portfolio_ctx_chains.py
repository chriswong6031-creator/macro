"""tests/test_portfolio_ctx_chains.py — TXI W4 portfolio_ctx per-ticker chains merge (deliverable C).

The transmission chains membership is added as a PER-TICKER optional block (tickers.<T>.chains),
NOT a top-level field — this avoids the #3385-class contract-drift trap. These lock:
  - _chains_index inverts the blast lists into {ticker: [membership]}, ARMED chains only
    (dormant chains contribute nothing), deduped per chain×channel
  - each membership carries chain id + bilingual label + state + tier + channel + channel label
  - build_ctx includes a name whose ONLY coverage is a chain membership; coverage.chains counts
  - the top-level key set is UNCHANGED (== manifest schema_fields) whether or not chains exist
  - absent/empty chain_state → no chains block anywhere, never raises
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIX = Path(__file__).resolve().parent / "fixtures" / "transmission" / "chain_state.json"

# the frozen top-level contract for portfolio_ctx.v1 (must not drift — #3385 class)
EXPECTED_TOP_LEVEL = sorted(
    ["asof", "built", "coverage", "gate_go", "regime", "schema", "sectors", "tickers", "v"]
)


@pytest.fixture()
def chain_state() -> dict:
    return json.loads(FIX.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# _chains_index
# ---------------------------------------------------------------------------
def test_index_armed_only_and_membership_shape(chain_state):
    from scripts.build_portfolio_ctx import _chains_index
    idx = _chains_index(chain_state)
    # NVDA is in the propagating dollar chain (2 channels) + arming oil chain (1 channel)
    nvda = idx.get("NVDA")
    assert nvda is not None
    chain_ids = {r["id"] for r in nvda}
    assert "dollar_spike_em_multinational" in chain_ids
    assert "oil_inflation_duration_derate" in chain_ids
    # dormant vol_regime never contributes a membership anywhere
    assert not any(r["id"] == "vol_regime_deleveraging" for rows in idx.values() for r in rows)
    # membership carries the display fields (bilingual label + channel)
    row = nvda[0]
    assert set(("id", "label", "state", "tier", "channel", "channel_label")).issubset(row)
    assert row["label"]["en"] and row["label"]["zh"]
    assert row["channel_label"]["en"]


def test_index_dedups_chain_channel(chain_state):
    from scripts.build_portfolio_ctx import _chains_index
    idx = _chains_index(chain_state)
    nvda = idx["NVDA"]
    pairs = [(r["id"], r["channel"]) for r in nvda]
    assert len(pairs) == len(set(pairs)), "chain×channel memberships must be deduped"


def test_index_empty_on_absent():
    from scripts.build_portfolio_ctx import _chains_index
    assert _chains_index({}) == {}
    assert _chains_index(None) == {}
    assert _chains_index({"chains": None}) == {}


# ---------------------------------------------------------------------------
# build_ctx integration — per-ticker block + coverage, contract stability
# ---------------------------------------------------------------------------
def test_build_ctx_includes_chain_only_ticker(chain_state):
    from scripts.build_portfolio_ctx import build_ctx
    payload = build_ctx({"chain_state": chain_state}, ["NVDA", "PLTR", "ZQZQ"], "2026-07-24")
    # NVDA + PLTR are in armed chains → included with a chains block; ZQZQ is in none → omitted
    assert set(payload["tickers"].keys()) == {"NVDA", "PLTR"}
    assert payload["coverage"]["chains"] == 2
    nvda = payload["tickers"]["NVDA"]
    assert "chains" in nvda and isinstance(nvda["chains"], list) and nvda["chains"]
    assert nvda["chains"][0]["state"] in ("arming", "propagating", "expressed")


def test_top_level_contract_unchanged_with_chains(chain_state):
    """The #3385-class guard: adding chains must NOT add/remove any TOP-LEVEL key."""
    from scripts.build_portfolio_ctx import build_ctx
    payload = build_ctx({"chain_state": chain_state}, None, "2026-07-24")
    assert sorted(payload.keys()) == EXPECTED_TOP_LEVEL


def test_top_level_contract_unchanged_without_chains():
    from scripts.build_portfolio_ctx import build_ctx
    payload = build_ctx({}, None, "2026-07-24")   # no chain_state at all
    assert sorted(payload.keys()) == EXPECTED_TOP_LEVEL
    # no ticker carries a chains block when the artifact is absent
    assert all("chains" not in blk for blk in payload["tickers"].values())
    assert payload["coverage"]["chains"] == 0


def test_load_chain_state_failopen(tmp_path):
    from scripts.build_portfolio_ctx import load_chain_state
    assert load_chain_state(tmp_path) == {}   # absent → {}
    d = tmp_path / "data" / "transmission"; d.mkdir(parents=True)
    (d / "chain_state.json").write_text("{ not json")
    assert load_chain_state(tmp_path) == {}   # corrupt → {}
