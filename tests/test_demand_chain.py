"""Tests for engine/demand_chain.py — the multi-chain customer-demand L2 leg."""
from __future__ import annotations

from engine import demand_chain as dc


def _ai(per_year):
    """AI capex spenders: split each year's total across the 5 hyperscalers."""
    rows = []
    for t in ["MSFT", "GOOGL", "AMZN", "META", "ORCL"]:
        for fy, tot in per_year.items():
            rows.append({"ticker": t, "fy": fy, "capex": tot / 5.0, "revenue": None})
    return rows


def _housing(per_year):
    """Homebuilder revenue: split across the 6 builders."""
    rows = []
    for t in ["DHI", "LEN", "PHM", "NVR", "TOL", "KBH"]:
        for fy, tot in per_year.items():
            rows.append({"ticker": t, "fy": fy, "capex": None, "revenue": tot / 6.0})
    return rows


def test_compute_signals_ai_accelerating():
    sig = dc.compute_signals(_ai({2023: 100e9, 2024: 120e9, 2025: 192e9}))
    assert "ai_datacenter" in sig
    s = sig["ai_datacenter"]
    assert s["trend"] == "accelerating" and s["yoy_pct"] == 60.0
    assert s["total_latest_bn"] == 192.0 and s["chain_key"] == "ai_datacenter"


def test_trend_labels():
    assert dc.compute_signals(_ai({2023: 100e9, 2024: 160e9, 2025: 252.8e9}))["ai_datacenter"]["trend"] == "expanding"
    assert dc.compute_signals(_ai({2023: 100e9, 2024: 160e9, 2025: 172.8e9}))["ai_datacenter"]["trend"] == "peaking"
    assert dc.compute_signals(_ai({2023: 200e9, 2024: 210e9, 2025: 150e9}))["ai_datacenter"]["trend"] == "contracting"


def test_compute_signals_housing_revenue():
    sig = dc.compute_signals(_housing({2023: 90e9, 2024: 100e9, 2025: 115e9}))
    assert "housing" in sig
    assert sig["housing"]["total_latest_bn"] == 115.0


def test_min_cover_gating():
    # only 2 AI spenders report -> below min_cover (4)
    thin = [{"ticker": "MSFT", "fy": y, "capex": 50e9, "revenue": None} for y in (2024, 2025)]
    thin += [{"ticker": "AMZN", "fy": y, "capex": 50e9, "revenue": None} for y in (2024, 2025)]
    assert "ai_datacenter" not in dc.compute_signals(thin)


def test_both_chains_coexist():
    rows = _ai({2023: 100e9, 2024: 130e9, 2025: 200e9}) + _housing({2023: 90e9, 2024: 100e9, 2025: 95e9})
    sig = dc.compute_signals(rows)
    assert set(sig) == {"ai_datacenter", "housing"}


SEMI = [{"slug": "ai_semiconductors", "name": "AI Semiconductors"}]
WFE = [{"slug": "ai_infra"}, {"slug": "semicap_equipment"}]
HOUSE = [{"slug": "housing", "name": "Housing Chain"}]
OFFCHAIN = [{"slug": "retail"}, {"slug": "housing_unrelated"}]


def _ai_sig():
    return dc.compute_signals(_ai({2023: 100e9, 2024: 130e9, 2025: 200e9}))


def test_ai_beneficiary_compute_tier():
    r = dc.chain_read(_ai_sig(), SEMI, None, ticker="NVDA")
    assert r is not None and r["chain_key"] == "ai_datacenter"
    assert r["tier"] == "compute" and r["leading"] is True
    assert r["divergence"] == "signal_only"          # no revisions


def test_wfe_precedence_over_ai_infra():
    r = dc.chain_read(_ai_sig(), WFE, {"est_chg_90d": 8.0, "breadth": 0.7}, ticker="LRCX")
    assert r["tier"] == "wfe" and r["divergence"] == "aligned"


def test_ai_ahead_of_consensus():
    r = dc.chain_read(_ai_sig(), SEMI, {"est_chg_90d": 0.2, "breadth": 0.0}, ticker="QCOM")
    assert r["divergence"] == "ahead_of_consensus"
    assert "AHEAD" in r["read"]["en"] or "ahead" in r["read"]["en"].lower()


def test_ai_consensus_at_risk():
    sig = dc.compute_signals(_ai({2023: 200e9, 2024: 210e9, 2025: 150e9}))
    r = dc.chain_read(sig, SEMI, {"est_chg_90d": 6.0, "breadth": 0.6}, ticker="NVDA")
    assert r["trend"] == "contracting" and r["divergence"] == "consensus_at_risk"


def test_non_beneficiary_returns_none():
    assert dc.chain_read(_ai_sig(), OFFCHAIN, None, ticker="WMT") is None
    assert dc.chain_read(_ai_sig(), None, None, ticker="WMT") is None


def test_housing_supplier_qualifies_builder_excluded():
    sig = dc.compute_signals(_housing({2023: 90e9, 2024: 100e9, 2025: 115e9}))
    # a supplier (BLDR) in the housing basket → qualifies, coincident & non-leading
    sup = dc.chain_read(sig, HOUSE, None, ticker="BLDR")
    assert sup is not None and sup["chain_key"] == "housing"
    assert sup["leading"] is False and sup["tier"] == "products"
    assert "end-market" in sup["caveat"]["en"].lower() or "coincident" in sup["caveat"]["en"].lower()
    # a BUILDER (DHI) is the demand SOURCE, not a beneficiary → excluded
    assert dc.chain_read(sig, HOUSE, None, ticker="DHI") is None
    # housing requires a ticker to apply the supplier allowlist
    assert dc.chain_read(sig, HOUSE, None, ticker=None) is None


def test_consensus_dir_thresholds():
    assert dc._consensus_dir({"est_chg_90d": 5.0, "breadth": 0.5}) == "rising"
    assert dc._consensus_dir({"est_chg_90d": -5.0, "breadth": -0.5}) == "falling"
    assert dc._consensus_dir({"est_chg_90d": 0.0, "breadth": 0.0}) == "flat"
    assert dc._consensus_dir(None) == "none"
    assert dc._consensus_dir({}) == "none"


def test_divergence_matrix():
    assert dc._divergence("accelerating", "rising") == "aligned"
    assert dc._divergence("accelerating", "flat") == "ahead_of_consensus"
    assert dc._divergence("contracting", "rising") == "consensus_at_risk"
    assert dc._divergence("accelerating", "none") == "signal_only"


# ── RPO (own contracted forward bookings) read ────────────────────────────────
def _rpo(rows):
    return [{"fy": fy, "rpo": rpo, "revenue": rev} for (fy, rpo, rev) in rows]


def test_rpo_read_signal_only_and_shape():
    r = dc.rpo_read(_rpo([(2023, 48e9, 31e9), (2024, 57e9, 35e9), (2025, 72e9, 41e9)]), None)
    assert r is not None
    assert r["chain_key"] == "own_rpo" and r["leading"] is True and r["tier"] == "bookings"
    assert r["divergence"] == "signal_only" and r["total_latest_bn"] == 72.0
    assert r["series"][-1] == [2025, 72.0]
    assert "×" in r["headline"]["en"]                    # RPO/revenue coverage rendered


def test_rpo_read_ahead_of_consensus():
    # RPO accelerating, consensus flat → ahead_of_consensus
    r = dc.rpo_read(_rpo([(2023, 30e9, 20e9), (2024, 39e9, 23e9), (2025, 60e9, 27e9)]),
                    {"est_chg_90d": 0.1, "breadth": 0.0})
    assert r["trend"] == "accelerating" and r["divergence"] == "ahead_of_consensus"


def test_rpo_read_consensus_at_risk():
    # RPO contracting, consensus still rising
    r = dc.rpo_read(_rpo([(2023, 60e9, 20e9), (2024, 62e9, 23e9), (2025, 45e9, 27e9)]),
                    {"est_chg_90d": 6.0, "breadth": 0.6})
    assert r["trend"] == "contracting" and r["divergence"] == "consensus_at_risk"


def test_rpo_read_none_when_too_short():
    assert dc.rpo_read(_rpo([(2025, 50e9, 30e9)]), None) is None
    assert dc.rpo_read([], None) is None
