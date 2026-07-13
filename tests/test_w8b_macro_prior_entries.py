"""W8b prereg: shape tests for the AI-capex complex macro prior / sector proxy additions.

Checks that the five new entries exist with plausible values and that existing entries
are unmodified (invariance).  Does not run compute_theme_intel (no price store needed).
"""
from __future__ import annotations

import engine.theme_scoring as ts

# ------------------------------------------------------------------ W8b new baskets
W8B_BASKETS = ["ai_semiconductors", "semicap_equipment", "memory_storage",
               "data_center_power", "nuclear_power"]

# Pre-W8b entries that must remain byte-identical (regression guard).
_EXPECTED_PRIOR_LEGACY = {
    "mag7":             {"growth": 0.5, "rates": 0.3, "inflation": -0.1, "riskon": 0.7},
    "ai_infra":         {"growth": 0.7, "rates": 0.2, "inflation": 0.0,  "riskon": 0.8},
    "ai_software":      {"growth": 0.5, "rates": 0.5, "inflation": -0.2, "riskon": 0.7},
    "defense":          {"growth": 0.0, "rates": 0.0, "inflation": 0.3,  "riskon": -0.1},
    "power_grid":       {"growth": 0.3, "rates": 0.4, "inflation": 0.2,  "riskon": 0.1},
    "reshoring":        {"growth": 0.6, "rates": 0.1, "inflation": 0.4,  "riskon": 0.2},
    "regional_banks":   {"growth": 0.5, "rates": -0.3, "inflation": 0.2, "riskon": 0.4},
    "managed_care":     {"growth": -0.3, "rates": 0.1, "inflation": -0.2, "riskon": -0.3},
    "housing":          {"growth": 0.4, "rates": 0.8, "inflation": -0.2, "riskon": 0.3},
    "payments_fintech": {"growth": 0.6, "rates": 0.2, "inflation": -0.1, "riskon": 0.6},
    "energy_complex":   {"growth": 0.3, "rates": -0.1, "inflation": 0.8, "riskon": 0.1},
    "defensives":       {"growth": -0.6, "rates": 0.3, "inflation": -0.1, "riskon": -0.6},
    "travel":           {"growth": 0.7, "rates": 0.1, "inflation": -0.2, "riskon": 0.5},
    "retail":           {"growth": 0.6, "rates": 0.3, "inflation": -0.3, "riskon": 0.5},
    "crypto":           {"growth": 0.3, "rates": 0.4, "inflation": 0.1,  "riskon": 1.0},
}
_EXPECTED_PROXY_LEGACY = {
    "mag7": "XLK", "ai_infra": "SMH", "ai_software": "XLK", "defense": "XLI",
    "power_grid": "XLU", "reshoring": "XLI", "regional_banks": "XLF",
    "managed_care": "XLV", "housing": "XLY", "payments_fintech": "XLF",
    "energy_complex": "XLE", "defensives": "XLP", "travel": "XLY", "retail": "XLY",
}


def test_w8b_baskets_have_macro_prior_entries():
    """All five AI-capex baskets now have _MACRO_PRIOR entries."""
    for bid in W8B_BASKETS:
        assert bid in ts._MACRO_PRIOR, f"W8b basket {bid!r} missing from _MACRO_PRIOR"


def test_w8b_baskets_have_sector_proxy_entries():
    """All five AI-capex baskets now have _SECTOR_PROXY entries."""
    for bid in W8B_BASKETS:
        assert bid in ts._SECTOR_PROXY, f"W8b basket {bid!r} missing from _SECTOR_PROXY"


def test_w8b_prior_keys_are_valid_macro_axes():
    """Each new prior has exactly the four canonical macro axes with [-1,1]-range values."""
    required_axes = {"growth", "rates", "inflation", "riskon"}
    for bid in W8B_BASKETS:
        prior = ts._MACRO_PRIOR[bid]
        assert set(prior.keys()) == required_axes, (
            f"{bid!r}: unexpected axes {set(prior.keys()) ^ required_axes}")
        for axis, val in prior.items():
            assert -1.0 <= val <= 1.0, (
                f"{bid!r} axis {axis!r} value {val} out of [-1, 1]")


def test_w8b_sector_proxies_are_known_etfs():
    """New sector proxies are ETF tickers plausibly in the regime sector_rs."""
    # These are the ETFs the existing engine reads from regime.sector_rs.
    known_etfs = {"XLK", "SMH", "XLI", "XLU", "XLF", "XLV", "XLY", "XLE", "XLP", "XLB",
                  "XLC", "XLRE", "XLB", "XLC"}
    for bid in W8B_BASKETS:
        etf = ts._SECTOR_PROXY[bid]
        assert etf in known_etfs, (
            f"{bid!r}: sector proxy {etf!r} not in known ETF set")


def test_w8b_ai_complex_baskets_are_pro_cyclical():
    """All three semiconductor/storage baskets have positive growth AND riskon priors
    (they benefit from macro tailwinds — this is the premise of the hypothesis)."""
    for bid in ["ai_semiconductors", "semicap_equipment", "memory_storage"]:
        prior = ts._MACRO_PRIOR[bid]
        assert prior["growth"] > 0, f"{bid!r} growth prior should be positive"
        assert prior["riskon"] > 0, f"{bid!r} riskon prior should be positive"


def test_w8b_power_baskets_have_positive_inflation_component():
    """Power/nuclear baskets have a positive inflation prior (energy pricing / equipment costs)."""
    for bid in ["data_center_power", "nuclear_power"]:
        prior = ts._MACRO_PRIOR[bid]
        assert prior["inflation"] >= 0, (
            f"{bid!r} inflation prior should be non-negative (infrastructure pricing)")


def test_w8b_semiconductor_baskets_use_smh_proxy():
    """Semiconductor-family baskets (ai_semiconductors, semicap, memory) use SMH as proxy."""
    for bid in ["ai_semiconductors", "semicap_equipment", "memory_storage"]:
        assert ts._SECTOR_PROXY[bid] == "SMH", (
            f"{bid!r}: expected SMH proxy, got {ts._SECTOR_PROXY[bid]!r}")


def test_w8b_power_baskets_use_correct_proxy():
    """data_center_power uses XLI (Electrical-Equipment Industrials: Vertiv/Eaton/GE-Vernova);
    nuclear_power uses XLU (nuclear operators genuinely classify within utilities)."""
    assert ts._SECTOR_PROXY["data_center_power"] == "XLI", (
        f"data_center_power: expected XLI proxy (Industrials), got {ts._SECTOR_PROXY['data_center_power']!r}")
    assert ts._SECTOR_PROXY["nuclear_power"] == "XLU", (
        f"nuclear_power: expected XLU proxy (Utilities), got {ts._SECTOR_PROXY['nuclear_power']!r}")


def test_legacy_prior_entries_unchanged():
    """Pre-W8b _MACRO_PRIOR entries are byte-identical (invariance guard)."""
    for bid, expected in _EXPECTED_PRIOR_LEGACY.items():
        assert bid in ts._MACRO_PRIOR, f"Legacy basket {bid!r} missing from _MACRO_PRIOR"
        actual = ts._MACRO_PRIOR[bid]
        assert actual == expected, (
            f"Legacy _MACRO_PRIOR[{bid!r}] changed:\n  expected {expected}\n  got {actual}")


def test_legacy_proxy_entries_unchanged():
    """Pre-W8b _SECTOR_PROXY entries are byte-identical (invariance guard)."""
    for bid, expected in _EXPECTED_PROXY_LEGACY.items():
        assert bid in ts._SECTOR_PROXY, f"Legacy basket {bid!r} missing from _SECTOR_PROXY"
        actual = ts._SECTOR_PROXY[bid]
        assert actual == expected, (
            f"Legacy _SECTOR_PROXY[{bid!r}] changed: expected {expected!r}, got {actual!r}")


def test_macro_leg_fires_for_w8b_baskets_in_pro_growth_state():
    """With a pro-growth macro state, _macro_leg returns a positive (non-None) value for all
    W8b baskets — confirming they are no longer macro-blind."""
    mc_tailwind = {
        "state": {"growth": 0.8, "rates": 0.5, "inflation": 0.2, "riskon": 0.9},
        "sector_rs": {"SMH": 0.85, "XLU": 0.70, "XLI": 0.75},
        "display": {"fed_dir": "easing", "nfci_state": "loose"},
    }
    for bid in W8B_BASKETS:
        val, _ = ts._macro_leg(bid, mc_tailwind)
        assert val is not None, f"{bid!r}: macro leg returned None (still macro-blind)"
        assert val > 0, f"{bid!r}: expected positive macro leg in tailwind, got {val}"


def test_macro_leg_returns_none_for_unknown_basket():
    """A basket with no prior and no proxy still returns None (renormalise-out path
    unchanged for genuinely unknown baskets)."""
    mc = {"state": {"growth": 0.5, "rates": 0.3, "inflation": 0.1, "riskon": 0.5},
          "sector_rs": {}, "display": {}}
    val, _ = ts._macro_leg("unknown_basket_xyz", mc)
    assert val is None
