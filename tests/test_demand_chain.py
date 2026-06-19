"""Tests for engine/demand_chain.py — the customer-capex demand-chain L2 leg."""
from __future__ import annotations

from engine import demand_chain as dc


# capex_by_ticker maps ticker -> {fy: capex_usd}. Use 5 spenders so coverage holds.
def _spenders(per_year):
    """per_year: {fy: total_usd}; split evenly across 5 synthetic spenders."""
    out = {}
    for i, t in enumerate(["MSFT", "GOOGL", "AMZN", "META", "ORCL"]):
        out[t] = {fy: tot / 5.0 for fy, tot in per_year.items()}
    return out


def test_signal_accelerating():
    # YoY growth itself rising: 20% -> 60% => accelerating
    sig = dc.compute_capex_signal(_spenders({2023: 100e9, 2024: 120e9, 2025: 192e9}))
    assert sig is not None
    assert sig["fy_latest"] == 2025
    assert sig["capex_latest_bn"] == 192.0
    assert sig["yoy_pct"] == 60.0
    assert sig["trend"] == "accelerating"
    assert sig["series"][0] == [2023, 100.0]


def test_signal_expanding_when_growth_steady_or_slowing_slightly():
    # 60% then 58% — still strong, slight slow but within tolerance => expanding
    sig = dc.compute_capex_signal(_spenders({2023: 100e9, 2024: 160e9, 2025: 252.8e9}))
    assert sig["trend"] == "expanding"


def test_signal_peaking_when_growth_collapses_but_positive():
    # 60% then 8% => still growing but decelerating hard => peaking
    sig = dc.compute_capex_signal(_spenders({2023: 100e9, 2024: 160e9, 2025: 172.8e9}))
    assert sig["trend"] == "peaking"


def test_signal_contracting():
    sig = dc.compute_capex_signal(_spenders({2023: 200e9, 2024: 210e9, 2025: 150e9}))
    assert sig["trend"] == "contracting"


def test_signal_none_when_insufficient_years():
    assert dc.compute_capex_signal(_spenders({2025: 100e9})) is None


def test_signal_none_when_coverage_too_thin():
    # only 2 spenders report -> below _MIN_COVER (4) -> no comparable years
    thin = {"MSFT": {2024: 50e9, 2025: 80e9}, "AMZN": {2024: 50e9, 2025: 80e9}}
    assert dc.compute_capex_signal(thin) is None


def test_alphabet_alias_counted_once_via_builder_contract():
    # The builder resolves Alphabet to a single alias; if both are passed the
    # aggregate would double-count. We document the contract: builder must pass
    # one alias per economic spender. Here we confirm n_spenders reflects keys.
    sig = dc.compute_capex_signal(_spenders({2024: 100e9, 2025: 150e9}))
    assert sig["n_spenders"] == 5


SEMI = [{"slug": "ai_semiconductors", "name": "AI Semiconductors"}]
WFE = [{"slug": "semicap_equipment", "name": "Semiconductor Equipment (WFE)"}]
POWER = [{"slug": "nuclear_power"}]
OFFCHAIN = [{"slug": "retail"}, {"slug": "housing"}]


def test_beneficiary_tier_precedence_compute_over_power():
    bm = [{"slug": "nuclear_power"}, {"slug": "ai_semiconductors"}]
    assert dc._beneficiary_tier(bm)["key"] == "compute"


def test_beneficiary_tier_wfe_wins_over_ai_infra():
    # AMAT/LRCX/KLAC sit in BOTH ai_infra and semicap_equipment — the more accurate
    # "one step back" WFE tier must win.
    bm = [{"slug": "ai_infra"}, {"slug": "semicap_equipment"}]
    assert dc._beneficiary_tier(bm)["key"] == "wfe"


def test_non_beneficiary_returns_none():
    sig = dc.compute_capex_signal(_spenders({2024: 100e9, 2025: 150e9}))
    assert dc.chain_read(sig, OFFCHAIN, None) is None
    assert dc.chain_read(sig, None, None) is None


def test_chain_read_signal_only_without_revisions():
    sig = dc.compute_capex_signal(_spenders({2023: 100e9, 2024: 130e9, 2025: 200e9}))
    r = dc.chain_read(sig, SEMI, None)
    assert r is not None
    assert r["divergence"] == "signal_only"
    assert r["consensus_dir"] == "none"
    assert r["tier"] == "compute"
    assert "zh" in r["headline"] and r["headline"]["zh"]


def test_chain_read_ahead_of_consensus():
    sig = dc.compute_capex_signal(_spenders({2023: 100e9, 2024: 130e9, 2025: 200e9}))
    # capex accelerating, consensus flat (no drift, flat breadth)
    rev = {"est_chg_90d": 0.2, "breadth": 0.0}
    r = dc.chain_read(sig, SEMI, rev)
    assert r["divergence"] == "ahead_of_consensus"


def test_chain_read_aligned_when_consensus_also_rising():
    sig = dc.compute_capex_signal(_spenders({2023: 100e9, 2024: 130e9, 2025: 200e9}))
    rev = {"est_chg_90d": 8.0, "breadth": 0.7}
    r = dc.chain_read(sig, SEMI, rev)
    assert r["divergence"] == "aligned"


def test_chain_read_consensus_at_risk():
    # capex contracting but consensus still rising
    sig = dc.compute_capex_signal(_spenders({2023: 200e9, 2024: 210e9, 2025: 150e9}))
    rev = {"est_chg_90d": 6.0, "breadth": 0.6}
    r = dc.chain_read(sig, WFE, rev)
    assert r["trend"] == "contracting"
    assert r["divergence"] == "consensus_at_risk"
    assert r["tier"] == "wfe"


def test_consensus_dir_thresholds():
    assert dc._consensus_dir({"est_chg_90d": 5.0, "breadth": 0.5}) == "rising"
    assert dc._consensus_dir({"est_chg_90d": -5.0, "breadth": -0.5}) == "falling"
    assert dc._consensus_dir({"est_chg_90d": 0.0, "breadth": 0.0}) == "flat"
    assert dc._consensus_dir(None) == "none"
    assert dc._consensus_dir({}) == "none"
