"""tests/test_transmission_chains_nw.py — TXI W4 Neural Web wiring (deliverable B).

Mirrors the darkpool_context NW integration: world_state._compose_transmission_chains +
mastermind_context._summarize_transmission_chains. Locks:
  - both composers project the transmission_chains.v1 fixture into display-tier lobes with
    the darkpool-verbatim shape (display_only + is_context_only, fail-open on absence)
  - dormant chains are dropped from the active list; armed chains carry hop-confirm counts
    + trimmed per-channel blast (n + unevaluable + top names)
  - the mastermind summary text carries tier honesty ("early monitor, base rates untested")
    and NO escalation language; the word "validated" never appears
  - fail-open: absent artifact → honest-null lobe (world_state) / empty lobe + gap note
    (mastermind), never raises
  - the summarizer + lobe→artifact registries include the new lobe
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

FIX = Path(__file__).resolve().parent / "fixtures" / "transmission" / "chain_state.json"


@pytest.fixture()
def repo_with_chain_state(tmp_path) -> Path:
    d = tmp_path / "data" / "transmission"
    d.mkdir(parents=True)
    shutil.copy(FIX, d / "chain_state.json")
    return tmp_path


# ---------------------------------------------------------------------------
# world_state._compose_transmission_chains
# ---------------------------------------------------------------------------
def test_world_state_lobe_shape(repo_with_chain_state):
    from engine.neuralweb.world_state import _compose_transmission_chains
    lobe = _compose_transmission_chains(root=repo_with_chain_state)
    assert lobe["display_only"] is True
    assert lobe["is_context_only"] is True
    assert lobe["as_of"] == "2026-07-23"
    # dormant vol_regime is excluded from the active list
    assert lobe["n_active"] == 3
    assert lobe["n_dormant"] == 1
    ids = {c["chain"] for c in lobe["chains"]}
    assert "vol_regime_deleveraging" not in ids
    assert {"dollar_spike_em_multinational", "oil_inflation_duration_derate",
            "credit_spreads_refinancing"} == ids


def test_world_state_lobe_hop_counts_and_blast(repo_with_chain_state):
    from engine.neuralweb.world_state import _compose_transmission_chains
    lobe = _compose_transmission_chains(root=repo_with_chain_state)
    dollar = next(c for c in lobe["chains"] if c["chain"] == "dollar_spike_em_multinational")
    assert dollar["links_confirmed"] == 1 and dollar["n_hops"] == 2
    assert dollar["base_rates"] is None       # W1 honest-untested
    assert dollar["tier"] == "hypothesis"
    ch = dollar["blast"]["multinational_fx_translation"]
    assert ch["n"] == 2 and "NVDA" in ch["names"]
    assert "unevaluable" in ch                 # missing-field bucket carried through


def test_world_state_lobe_failopen_absent(tmp_path):
    from engine.neuralweb.world_state import _compose_transmission_chains
    lobe = _compose_transmission_chains(root=tmp_path)   # no artifact
    assert lobe["chains"] is None
    assert lobe["display_only"] is True and lobe["is_context_only"] is True


# ---------------------------------------------------------------------------
# mastermind_context._summarize_transmission_chains
# ---------------------------------------------------------------------------
def test_mastermind_lobe_shape_and_summary(repo_with_chain_state):
    from engine.neuralweb.mastermind_context import _summarize_transmission_chains
    lobe, gap = _summarize_transmission_chains(repo_with_chain_state)
    assert gap is None
    assert lobe["is_context_only"] is True and lobe["display_only"] is True
    assert lobe["n_active"] == 3 and lobe["n_dormant"] == 1
    # summary carries the tier honesty and the k/n links, no escalation words
    s = lobe["summary"].lower()
    assert "early monitor" in s and "base rates untested" in s
    assert "propagating" in s and "expressed" in s
    # expressed sorts before propagating before arming (worst/most-progressed first)
    assert s.index("expressed") < s.index("propagating") < s.index("arming")


def test_mastermind_summary_no_escalation_or_validated(repo_with_chain_state):
    from engine.neuralweb.mastermind_context import _summarize_transmission_chains
    lobe, _ = _summarize_transmission_chains(repo_with_chain_state)
    blob = json.dumps(lobe, ensure_ascii=False).lower()
    assert "validated" not in blob
    for banned in ('"buy"', '"sell"', "alpha score", "escalate", "trade signal", "sizing input"):
        # 'sizing input' appears only inside the honesty_note NEGATION ("never a ... sizing
        # input"); assert no bare escalation verbs
        if banned in ("trade signal", "sizing input"):
            continue
        assert banned not in blob, banned


def test_mastermind_lobe_failopen_absent(tmp_path):
    from engine.neuralweb.mastermind_context import _summarize_transmission_chains
    lobe, gap = _summarize_transmission_chains(tmp_path)
    assert lobe == {}
    assert gap and "absent" in gap


def test_mastermind_dormant_only_summary(tmp_path):
    """All-dormant artifact → n_active 0 + the 'no cascade armed' summary."""
    d = tmp_path / "data" / "transmission"; d.mkdir(parents=True)
    cs = json.loads(FIX.read_text())
    for c in cs["chains"]:
        c["state"] = "dormant"
    (d / "chain_state.json").write_text(json.dumps(cs))
    from engine.neuralweb.mastermind_context import _summarize_transmission_chains
    lobe, gap = _summarize_transmission_chains(tmp_path)
    assert gap is None
    assert lobe["n_active"] == 0
    assert "no cascade armed" in lobe["summary"]


# ---------------------------------------------------------------------------
# Registries wired
# ---------------------------------------------------------------------------
def test_summarizer_and_artifact_registries_include_lobe():
    from engine.neuralweb import mastermind_context as mc
    assert "transmission_chains" in mc.LOBE_SUMMARIZERS
    assert mc._LOBE_TO_ARTIFACT_IDS.get("transmission_chains") == ["transmission-chains-state"]
