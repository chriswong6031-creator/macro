"""engine.neuralweb.context_risk_constants — Frozen per-archetype fingerprint constants.

Transcribed from STOCK_PERSONALITY_FIELD_GUIDE.md (2026-07-07, 223-name
survivorship-flagged deep corpus). Refresh when the field guide is re-measured.
DISPLAY-ONLY constants.

This module is a read-only reference table. It contains no forward-looking claims,
no significance tests, and no edge claims. Every number here is a measured historical
distribution from the 223-name deep corpus described in the field guide, which is
survivorship-biased toward larger, more-established, more-liquid names.

Standing warnings (from field guide §7):
  1. Label trust differs by type — high dispersion types (speculative_unprofitable 0.544)
     have low predictive power per-name; low dispersion types (financial 0.162) are far
     more predictable from archetype alone.
  2. Survivorship watermark — the 223-name deep corpus underrepresents micro-cap,
     younger, and historically-distressed names.
  3. Deep-corpus-only caveat — do NOT generalize to the full 1,722-name production
     universe without verifying representativeness.
  4. commodity_sensitive — ABSENT from deep corpus; excluded from all tables here.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# ARCHETYPE FINGERPRINT TABLE (field guide §1, Table 1 + Table 2)
# Keys: vol_med, beta_med, maxdd_med, pct_never_recover_1yr, disp,
#       upcap, dncap, skew, n_obs, n_tickers
# Columns mirror Table 1 exactly; all values are medians unless noted.
# ---------------------------------------------------------------------------

ARCHETYPE_FINGERPRINTS: dict[str, dict] = {
    "speculative_unprofitable": {
        "vol_med": 0.378,
        "beta_med": 1.258,
        "maxdd_med": -0.272,
        "pct_never_recover_1yr": 0.52,   # 52%
        "disp": 0.544,
        "upcap": 1.323,
        "dncap": 1.249,
        "skew": +0.116,
        "n_obs": 291,
        "n_tickers": 83,
    },
    "high_beta_momentum": {
        "vol_med": 0.392,
        "beta_med": 1.230,
        "maxdd_med": -0.272,
        "pct_never_recover_1yr": 0.61,   # 61%
        "disp": 0.351,
        "upcap": 1.255,
        "dncap": 1.204,
        "skew": -0.077,
        "n_obs": 95,
        "n_tickers": 12,
    },
    "secular_growth": {
        "vol_med": 0.302,
        "beta_med": 1.058,
        "maxdd_med": -0.228,
        "pct_never_recover_1yr": 0.55,   # 55%
        "disp": 0.288,
        "upcap": 1.096,
        "dncap": 1.063,
        "skew": +0.110,
        "n_obs": 73,
        "n_tickers": 34,
    },
    "broken_growth": {
        "vol_med": 0.309,
        "beta_med": 0.950,
        "maxdd_med": -0.217,
        "pct_never_recover_1yr": 0.65,   # 65%
        "disp": 0.293,
        "upcap": 0.924,
        "dncap": 1.052,
        "skew": +0.059,
        "n_obs": 49,
        "n_tickers": 21,
    },
    "rate_sensitive": {
        "vol_med": 0.267,
        "beta_med": 1.052,
        "maxdd_med": -0.200,
        "pct_never_recover_1yr": 0.47,   # 47%
        "disp": 0.198,
        "upcap": 1.045,
        "dncap": 1.070,
        "skew": -0.081,
        "n_obs": 461,
        "n_tickers": 40,
    },
    "deep_value": {
        "vol_med": 0.266,
        "beta_med": 0.881,
        "maxdd_med": -0.196,
        "pct_never_recover_1yr": 0.57,   # 57%
        "disp": 0.197,
        "upcap": 0.850,
        "dncap": 0.863,
        "skew": -0.095,
        "n_obs": 76,
        "n_tickers": 6,
    },
    "financial": {
        "vol_med": 0.251,
        "beta_med": 1.142,
        "maxdd_med": -0.187,
        "pct_never_recover_1yr": 0.49,   # 49%
        "disp": 0.162,
        "upcap": 1.110,
        "dncap": 1.090,
        "skew": +0.005,
        "n_obs": 220,
        "n_tickers": 15,
    },
    "cyclical": {
        "vol_med": 0.255,
        "beta_med": 1.107,
        "maxdd_med": -0.184,
        "pct_never_recover_1yr": 0.48,   # 48%
        "disp": 0.208,
        "upcap": 1.083,
        "dncap": 1.124,
        "skew": -0.010,
        "n_obs": 393,
        "n_tickers": 30,
    },
    "distressed": {
        "vol_med": 0.242,
        "beta_med": 0.676,
        "maxdd_med": -0.167,
        "pct_never_recover_1yr": 0.55,   # 55%
        "disp": 0.194,
        "upcap": 0.693,
        "dncap": 0.862,
        "skew": -0.154,
        "n_obs": 153,
        "n_tickers": 40,
    },
    "quality_compounder": {
        "vol_med": 0.248,
        "beta_med": 0.680,
        "maxdd_med": -0.176,
        "pct_never_recover_1yr": 0.38,   # 38%
        "disp": 0.175,
        "upcap": 0.660,
        "dncap": 0.573,
        "skew": +0.031,
        "n_obs": 48,
        "n_tickers": 3,   # SMALL-N: only 3 tickers
    },
    "mixed": {
        "vol_med": 0.224,
        "beta_med": 0.799,
        "maxdd_med": -0.162,
        "pct_never_recover_1yr": 0.48,   # 48%
        "disp": 0.239,
        "upcap": 0.778,
        "dncap": 0.789,
        "skew": -0.093,
        "n_obs": 998,
        "n_tickers": 75,
    },
    "dividend_defensive": {
        "vol_med": 0.218,
        "beta_med": 0.621,
        "maxdd_med": -0.149,
        "pct_never_recover_1yr": 0.43,   # 43%
        "disp": 0.186,
        "upcap": 0.558,
        "dncap": 0.567,
        "skew": -0.250,
        "n_obs": 53,
        "n_tickers": 4,   # SMALL-N: only 4 tickers
    },
    # commodity_sensitive: ABSENT — zero tickers in deep corpus (field guide §1 coverage note)
}

# ---------------------------------------------------------------------------
# ARCHETYPE × QUAD MATRICES (field guide §3, Table 1: Median 21d Forward Return)
# Layout: arch → quad → {median_21d, n}
# Quads: Q1=growth↑inflation↑, Q2=growth↑inflation↓,
#        Q3=growth↓inflation↑ (stagflation), Q4=growth↓inflation↓ (deflation)
# ---------------------------------------------------------------------------

ARCHETYPE_QUAD_MEDIAN: dict[str, dict[str, dict]] = {
    "broken_growth":          {"Q1": {"med": 0.023, "n": 1926},  "Q2": {"med": 0.003, "n": 3406},  "Q3": {"med": 0.008, "n": 1196},  "Q4": {"med": 0.025, "n": 3251}},
    "cyclical":               {"Q1": {"med": 0.011, "n": 16404}, "Q2": {"med": 0.014, "n": 43947}, "Q3": {"med": 0.013, "n": 7012},  "Q4": {"med": 0.023, "n": 25543}},
    "deep_value":             {"Q1": {"med": 0.015, "n": 3268},  "Q2": {"med": 0.013, "n": 8458},  "Q3": {"med": 0.024, "n": 1383},  "Q4": {"med": 0.013, "n": 4927}},
    "distressed":             {"Q1": {"med": 0.012, "n": 6428},  "Q2": {"med": 0.003, "n": 10823}, "Q3": {"med": 0.006, "n": 3925},  "Q4": {"med": 0.013, "n": 9514}},
    "dividend_defensive":     {"Q1": {"med": 0.014, "n": 2163},  "Q2": {"med": 0.016, "n": 6185},  "Q3": {"med": 0.017, "n": 887},   "Q4": {"med": 0.010, "n": 3623}},
    "financial":              {"Q1": {"med": 0.016, "n": 9355},  "Q2": {"med": 0.014, "n": 24034}, "Q3": {"med": 0.012, "n": 4120},  "Q4": {"med": 0.025, "n": 14348}},
    "high_beta_momentum":     {"Q1": {"med": 0.013, "n": 3708},  "Q2": {"med": 0.015, "n": 10733}, "Q3": {"med": 0.010, "n": 1648},  "Q4": {"med": 0.028, "n": 6008}},
    "mixed":                  {"Q1": {"med": 0.014, "n": 42616}, "Q2": {"med": 0.014, "n": 115044},"Q3": {"med": 0.008, "n": 17345}, "Q4": {"med": 0.015, "n": 65512}},
    "quality_compounder":     {"Q1": {"med": 0.017, "n": 2087},  "Q2": {"med": 0.012, "n": 5233},  "Q3": {"med": 0.013, "n": 872},   "Q4": {"med": 0.014, "n": 3198}},
    "rate_sensitive":         {"Q1": {"med": 0.007, "n": 19340}, "Q2": {"med": 0.013, "n": 49923}, "Q3": {"med": 0.009, "n": 8434},  "Q4": {"med": 0.020, "n": 31623}},
    "secular_growth":         {"Q1": {"med": 0.015, "n": 3370},  "Q2": {"med": -0.002,"n": 6024},  "Q3": {"med": -0.011,"n": 2160},  "Q4": {"med": 0.031, "n": 5861}},
    "speculative_unprofitable":{"Q1": {"med": 0.020, "n": 13559},"Q2": {"med": 0.014, "n": 33208}, "Q3": {"med": 0.026, "n": 5992},  "Q4": {"med": 0.024, "n": 17597}},
}

# ---------------------------------------------------------------------------
# ARCHETYPE × QUAD P10 (field guide §3, Table 2: Worst-Decile 21d Return)
# Layout: arch → quad → p10 (no n column in Table 2; reuse Table 1 n)
# ---------------------------------------------------------------------------

ARCHETYPE_QUAD_P10: dict[str, dict[str, float]] = {
    "broken_growth":          {"Q1": -0.093, "Q2": -0.114, "Q3": -0.093, "Q4": -0.089},
    "cyclical":               {"Q1": -0.073, "Q2": -0.071, "Q3": -0.081, "Q4": -0.085},
    "deep_value":             {"Q1": -0.067, "Q2": -0.079, "Q3": -0.056, "Q4": -0.081},
    "distressed":             {"Q1": -0.072, "Q2": -0.089, "Q3": -0.087, "Q4": -0.064},
    "dividend_defensive":     {"Q1": -0.065, "Q2": -0.061, "Q3": -0.056, "Q4": -0.064},
    "financial":              {"Q1": -0.060, "Q2": -0.071, "Q3": -0.087, "Q4": -0.080},
    "high_beta_momentum":     {"Q1": -0.104, "Q2": -0.106, "Q3": -0.107, "Q4": -0.128},
    "mixed":                  {"Q1": -0.060, "Q2": -0.063, "Q3": -0.071, "Q4": -0.070},
    "quality_compounder":     {"Q1": -0.062, "Q2": -0.067, "Q3": -0.078, "Q4": -0.076},
    "rate_sensitive":         {"Q1": -0.077, "Q2": -0.075, "Q3": -0.087, "Q4": -0.087},
    "secular_growth":         {"Q1": -0.087, "Q2": -0.100, "Q3": -0.114, "Q4": -0.078},
    "speculative_unprofitable":{"Q1": -0.099, "Q2": -0.112, "Q3": -0.114, "Q4": -0.117},
}

# ---------------------------------------------------------------------------
# ARCHETYPE × LIQUIDITY (field guide §3, Table 3: Median 21d Return)
# Layout: arch → liq_state → {median_21d, n}
# liq_state ∈ {expanding, neutral, contracting}
# ---------------------------------------------------------------------------

ARCHETYPE_LIQUIDITY_MEDIAN: dict[str, dict[str, dict]] = {
    "broken_growth":          {"expanding": {"med": 0.018, "n": 4068},  "neutral": {"med": 0.017, "n": 1430},  "contracting": {"med": 0.013, "n": 4281}},
    "cyclical":               {"expanding": {"med": 0.021, "n": 43472}, "neutral": {"med": 0.010, "n": 19349}, "contracting": {"med": 0.011, "n": 30085}},
    "deep_value":             {"expanding": {"med": 0.020, "n": 8261},  "neutral": {"med": 0.011, "n": 3705},  "contracting": {"med": 0.008, "n": 6070}},
    "distressed":             {"expanding": {"med": 0.012, "n": 12852}, "neutral": {"med": 0.008, "n": 4618},  "contracting": {"med": 0.004, "n": 13220}},
    "dividend_defensive":     {"expanding": {"med": 0.017, "n": 5878},  "neutral": {"med": 0.013, "n": 2879},  "contracting": {"med": 0.011, "n": 4101}},
    "financial":              {"expanding": {"med": 0.021, "n": 24054}, "neutral": {"med": 0.015, "n": 10626}, "contracting": {"med": 0.013, "n": 17177}},
    "high_beta_momentum":     {"expanding": {"med": 0.025, "n": 10639}, "neutral": {"med": 0.007, "n": 4547},  "contracting": {"med": 0.011, "n": 6911}},
    "mixed":                  {"expanding": {"med": 0.017, "n": 112559},"neutral": {"med": 0.013, "n": 51055}, "contracting": {"med": 0.010, "n": 76903}},
    "quality_compounder":     {"expanding": {"med": 0.018, "n": 5291},  "neutral": {"med": 0.010, "n": 2284},  "contracting": {"med": 0.010, "n": 3815}},
    "rate_sensitive":         {"expanding": {"med": 0.019, "n": 50494}, "neutral": {"med": 0.011, "n": 22257}, "contracting": {"med": 0.006, "n": 36569}},
    "secular_growth":         {"expanding": {"med": 0.017, "n": 6901},  "neutral": {"med": 0.010, "n": 2588},  "contracting": {"med": 0.006, "n": 7926}},
    "speculative_unprofitable":{"expanding": {"med": 0.026, "n": 32195},"neutral": {"med": 0.015, "n": 14294}, "contracting": {"med": 0.011, "n": 23867}},
}

# ---------------------------------------------------------------------------
# MINIMUM N THRESHOLD for "adequate cell" — matches the field guide §3 statement
# "No small-n cells; minimum n=887 (dividend_defensive/Q3)" for the quad tables.
# ---------------------------------------------------------------------------

MIN_N_ADEQUATE = 887   # minimum n in quad matrix cells (dividend_defensive Q3)
