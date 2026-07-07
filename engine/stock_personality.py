"""Stock personality classifier — per-ticker v1 object assembly.

DISPLAY-ONLY context infrastructure: deterministic label assignment for the
stock_personality.v1 object.  Never scores, sizes, or gates positions.
This module is PURE: no file I/O, no network calls, no parquet/JSON reads.
All inputs are pre-computed by the caller (build_stock_library pass).

Lineage: research/STOCK_PERSONALITY_MASTERPLAN_BY_FABLE.md §2–§3.1

Public API
----------
    assess(ticker, *, as_of, path_features=None, archetype=None,
           dna_class=None, positioning=None, smart_money=None,
           basket_membership=None, etf_weight_max=None,
           attention_z=None, bo_regime=None, gex=None, events=None,
           tech=None, oracle_episode_active=None, market_cap=None) -> dict

    setup_compatibility(personality: dict, species_entries: list[dict]) -> dict

Schema: stock_personality.v1
Authority: tier=display, confidence_class=descriptive, may_rank/size/gate=False
"""
from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# v1-frozen thresholds — changes require a masterplan version bump + adjudication.
# ---------------------------------------------------------------------------

# ---- CHART PERSONALITY ----

# event_gapper: gap features dominate the chart
CHART_EVENT_GAP_CONTRIB_THRESHOLD = 0.35   # event_gap_contrib_252 >= this
CHART_GAP_SHARE_THRESHOLD = 0.45           # gap_share_252 >= this (alternate trigger)

# failed_breakout_trap: breakouts reliably fail
CHART_FAILED_BREAKOUT_THRESHOLD = 0.60    # failed_breakout_rate_63 >= this

# mean_reversion_rubber_band: returns persistently reverse
CHART_MEAN_REVERSION_THRESHOLD = -0.08    # trend_persist_60 <= this

# smooth_compounder_grind: slow, steady grind
CHART_SMOOTH_TREND_PERSIST_THRESHOLD = 0.05    # trend_persist_126 >= this
CHART_SMOOTH_PULLBACK_MEDIAN_THRESHOLD = 0.06  # pullback_median_252 <= this
CHART_SMOOTH_EXTREME_BAR_THRESHOLD = 0.02      # extreme_bar_freq_252 <= this

# stair_step_leader: breakout-and-hold pattern
CHART_STAIR_FT_RATE_THRESHOLD = 0.60           # breakout_ft_rate_63 >= this
CHART_STAIR_SLOPE_STABILITY_THRESHOLD = 0.65   # slope_stability_126 >= this

# volatile_momentum_vehicle
CHART_VMV_HV_PCTILE_THRESHOLD = 80.0    # tech.hv_pctile >= this
CHART_VMV_TREND_PERSIST_THRESHOLD = 0.0  # trend_persist_20 >= 0 (non-negative)

# basing_accumulator
CHART_BASING_RANGE_COMPRESSION_THRESHOLD = 20.0   # range_compression_pct <= this
CHART_BASING_VOL_SQUEEZE_STATES = frozenset({"COILED", "COMPRESSED"})

# defensive_range_stock
CHART_DEFENSIVE_HV_PCTILE_THRESHOLD = 40.0         # tech.hv_pctile <= this
CHART_DEFENSIVE_TREND_PERSIST_ABS_THRESHOLD = 0.03  # |trend_persist_126| <= this
CHART_DEFENSIVE_PULLBACK_P90_THRESHOLD = 0.15       # pullback_p90_252 <= this

# minimum bars for chart axis to be evaluated
CHART_MIN_BARS = 300

# maximum labels assigned for chart axis
CHART_MAX_LABELS = 2

# Precedence order (first-match-wins within the cascade; caps enforced after)
CHART_PRECEDENCE = [
    "event_gapper",
    "failed_breakout_trap",
    "mean_reversion_rubber_band",
    "smooth_compounder_grind",
    "stair_step_leader",
    "volatile_momentum_vehicle",
    "basing_accumulator",
    "defensive_range_stock",
    "mixed_chart",
]

# ---- MICROSTRUCTURE ----

# tight_spread_absorber: liquid, deep (ADV + CS-spread only)
# amihud_252 passes through into base.microstructure as a raw value for W2b
# cross-sectional percentile ranking — no absolute threshold here.
MICRO_TIGHT_ADV_THRESHOLD = 50_000_000.0   # dollar_adv_21d >= $50M
MICRO_TIGHT_CS_SPREAD_THRESHOLD = 0.006    # cs_spread_252 <= this

# wide_spread_impact: illiquid / thin
MICRO_WIDE_ADV_THRESHOLD = 5_000_000.0     # dollar_adv_21d <= $5M
MICRO_WIDE_CS_SPREAD_THRESHOLD = 0.015     # cs_spread_252 >= this (either trigger)

# gap_discontinuity_risk
MICRO_DISC_EXTREME_BAR_THRESHOLD = 0.04    # extreme_bar_freq_252 >= this
MICRO_DISC_GAP_SHARE_THRESHOLD = 0.60      # gap_share_252 >= this (alternate)

# slow_mean_reversion_liquidity
MICRO_SLOW_MR_HALF_LIFE_THRESHOLD = 5.0   # reversal_half_life <= this (fast reverter)

MICRO_MAX_LABELS = 2   # primary + optional secondary

MICROSTRUCTURE_PRECEDENCE = [
    "tight_spread_absorber",
    "wide_spread_impact",
    "gap_discontinuity_risk",
    "slow_mean_reversion_liquidity",
    "mixed_microstructure",
]

# ---- OWNERSHIP HABITAT ----

# short_interest_tinderbox
OWN_SI_TINDERBOX_SHORT_PCT = 15.0   # short_pct_float >= this
OWN_SI_TINDERBOX_DTC = 8.0          # days_to_cover >= this (alternate)

# retail_attention
OWN_RETAIL_ATTENTION_Z = 2.0        # attention_z >= this

# insider_founder_controlled
OWN_INSIDER_N_BUYERS_MIN = 3        # insider_n_buyers >= this (requires cluster=True)

# passive_index_magnet
OWN_PASSIVE_ETF_WEIGHT_THRESHOLD = 0.5      # etf_weight_max >= this
OWN_PASSIVE_MARKET_CAP_THRESHOLD = 200e9    # market_cap >= $200B

# etf_basketed_conduit
OWN_ETF_BASKET_MEMBERSHIP_MIN = 2   # len(basket_membership) >= this

# long_only_sponsor
OWN_LOS_BO_REGIME = "passive"
OWN_LOS_SHORT_PCT_MAX = 3.0         # short_pct_float <= this
OWN_LOS_ATTENTION_Z_MAX = 1.0       # attention_z < this (or None)

OWNERSHIP_MAX_LABELS = 3

OWNERSHIP_PRECEDENCE = [
    "short_interest_tinderbox",
    "retail_attention",
    "insider_founder_controlled",
    "passive_index_magnet",
    "etf_basketed_conduit",
    "long_only_sponsor",
    "mixed_ownership",
]

# ---- CURRENT MODE ----

# event_override
MODE_EVENT_DAYS_TO_EARNINGS_THRESHOLD = 5   # |days_to_earnings| <= this

# forced_liquidation
MODE_FORCED_LIQ_RET_21D_THRESHOLD = -0.25   # ret_21d <= this
MODE_FORCED_LIQ_REL_VOL_THRESHOLD = 2.0     # rel_volume >= this

# squeeze
MODE_SQUEEZE_SHORT_PCT_THRESHOLD = 15.0     # short_pct_float >= this
MODE_SQUEEZE_RET_21D_THRESHOLD = 0.25       # ret_21d >= this (upside)

# options_pin — gex_engine emits dist_to_flip_pct as signed (spot−flip)/spot·100;
# |dist_to_flip_pct| <= threshold means spot is within 2% of the gamma flip level.
MODE_PIN_FLIP_DIST_THRESHOLD = 2.0          # abs(dist_to_flip_pct) <= this (tight pin)

# post_news_attention
MODE_POST_NEWS_ATTENTION_Z = 3.0            # attention_z >= this

# stale_dead_money
MODE_STALE_MONTHS_UNDERWATER_THRESHOLD = 6.0   # months_underwater >= this
MODE_STALE_HV_PCTILE_THRESHOLD = 30.0          # hv_pctile <= this
MODE_STALE_REL_VOLUME_THRESHOLD = 0.8           # rel_volume <= this

# accumulation
MODE_ACCUM_VOL_SQUEEZE_STATES = frozenset({"COILED", "COMPRESSED"})
MODE_ACCUM_TREND_PERSIST_MIN = 0.0   # trend_persist_20 >= 0

# distribution
# off_52w_high_pct is signed (spot/52w_high - 1)*100 — NEGATIVE value, e.g., -8.5 = 8.5% below high.
# "Near high" means value is close to 0 from below: off_52w_high_pct >= -MODE_DIST_OFF_52W_HIGH_THRESHOLD.
MODE_DIST_OFF_52W_HIGH_THRESHOLD = 10.0    # off_52w_high_pct >= -this (near high, within 10%)
MODE_DIST_FAILED_BO_THRESHOLD = 0.50       # failed_breakout_rate_63 >= this

# Expiry (days) per mode
MODE_EXPIRY = {
    "options_pin": 7,
    "negative_gamma_trend": 7,
    "post_news_attention": 7,
    "event_override": 21,
    "forced_liquidation": 21,
    "squeeze": 21,
    "sector_rotation_feeder": 21,
    "stale_dead_money": 21,
    "accumulation": 21,
    "distribution": 21,
    "normal": 21,
}

MODE_MAX_LABELS = 3

# ---- CHART MUTUAL-EXCLUSION PAIRS ----
# Within each pair, once the first label is assigned the second cannot co-fire.
# This prevents conflicting characterisations: a smooth grinder is not also a
# volatile momentum vehicle; a stair-step leader is not also a mean reverter.
CHART_EXCLUSIONS: tuple[frozenset[str], ...] = (
    frozenset({"smooth_compounder_grind", "volatile_momentum_vehicle"}),
    frozenset({"mean_reversion_rubber_band", "stair_step_leader"}),
)

CURRENT_MODE_PRECEDENCE = [
    "event_override",
    "forced_liquidation",
    "squeeze",
    "options_pin",
    "negative_gamma_trend",
    "sector_rotation_feeder",
    "post_news_attention",
    "stale_dead_money",
    "accumulation",
    "distribution",
    "normal",
]

# ---- AUTHORITY STANZA — module constant, never mutated ----
_AUTHORITY = {
    "tier": "display",
    "confidence_class": "descriptive",
    "weights": "none",
    "may_rank": False,
    "may_size": False,
    "may_gate": False,
}

# Valid species validation statuses for setup_compatibility inclusion
_COMPAT_VALID_STATUSES = frozenset({"validated", "accruing", "phase0"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_float(val: Any) -> float | None:
    """Return float or None for missing/NaN."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _safe_bool(val: Any) -> bool | None:
    if val is None:
        return None
    return bool(val)


def _safe_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _pf(path_features: dict | None, key: str) -> float | None:
    """Pull a float feature from path_features dict."""
    if not path_features:
        return None
    return _safe_float(path_features.get(key))


def _pf_n_bars(path_features: dict | None) -> int:
    """Return n_bars from path_features coverage sub-dict."""
    if not path_features:
        return 0
    cov = path_features.get("coverage") or {}
    return int(cov.get("n_bars", 0) or 0)


# ---------------------------------------------------------------------------
# Chart personality cascade
# ---------------------------------------------------------------------------


def _classify_chart(
    path_features: dict | None,
    tech: dict | None,
) -> tuple[list[str] | None, list[str], dict]:
    """Return (labels_or_None, missing_inputs, feature_snapshot).

    Returns None when coverage is insufficient.
    """
    missing: list[str] = []
    snapshot: dict = {}

    n_bars = _pf_n_bars(path_features)
    if n_bars < CHART_MIN_BARS:
        missing.append("path_features.n_bars<300")
        return None, missing, snapshot

    # Pull all features used in chart cascade
    event_gap_contrib = _pf(path_features, "event_gap_contrib_252")
    gap_share = _pf(path_features, "gap_share_252")
    failed_breakout_rate = _pf(path_features, "failed_breakout_rate_63")
    trend_persist_60 = _pf(path_features, "trend_persist_60")
    trend_persist_126 = _pf(path_features, "trend_persist_126")
    trend_persist_20 = _pf(path_features, "trend_persist_20")
    pullback_median = _pf(path_features, "pullback_median_252")
    pullback_p90 = _pf(path_features, "pullback_p90_252")
    extreme_bar_freq = _pf(path_features, "extreme_bar_freq_252")
    breakout_ft_rate = _pf(path_features, "breakout_ft_rate_63")
    slope_stability = _pf(path_features, "slope_stability_126")
    range_compression = _pf(path_features, "range_compression_pct")

    hv_pctile = _safe_float((tech or {}).get("hv_pctile"))
    vol_squeeze_state = (tech or {}).get("vol_squeeze_state")

    snapshot = {
        "event_gap_contrib_252": event_gap_contrib,
        "gap_share_252": gap_share,
        "failed_breakout_rate_63": failed_breakout_rate,
        "trend_persist_20": trend_persist_20,
        "trend_persist_60": trend_persist_60,
        "trend_persist_126": trend_persist_126,
        "pullback_median_252": pullback_median,
        "pullback_p90_252": pullback_p90,
        "extreme_bar_freq_252": extreme_bar_freq,
        "breakout_ft_rate_63": breakout_ft_rate,
        "slope_stability_126": slope_stability,
        "range_compression_pct": range_compression,
        "hv_pctile": hv_pctile,
        "vol_squeeze_state": vol_squeeze_state,
    }

    labels: list[str] = []

    def _add(label: str) -> bool:
        """Add label if cap not reached and no mutual-exclusion conflict; return True if added."""
        if len(labels) >= CHART_MAX_LABELS:
            return False
        # Enforce CHART_EXCLUSIONS: skip if this label is paired with an already-assigned label
        for excl_set in CHART_EXCLUSIONS:
            if label in excl_set and any(existing in excl_set for existing in labels):
                return False
        labels.append(label)
        return True

    # 1. event_gapper
    if (event_gap_contrib is not None and event_gap_contrib >= CHART_EVENT_GAP_CONTRIB_THRESHOLD) or \
       (gap_share is not None and gap_share >= CHART_GAP_SHARE_THRESHOLD):
        _add("event_gapper")

    # 2. failed_breakout_trap
    if len(labels) < CHART_MAX_LABELS:
        if failed_breakout_rate is not None and failed_breakout_rate >= CHART_FAILED_BREAKOUT_THRESHOLD:
            _add("failed_breakout_trap")

    # 3. mean_reversion_rubber_band
    if len(labels) < CHART_MAX_LABELS:
        if trend_persist_60 is not None and trend_persist_60 <= CHART_MEAN_REVERSION_THRESHOLD:
            _add("mean_reversion_rubber_band")

    # 4. smooth_compounder_grind
    if len(labels) < CHART_MAX_LABELS:
        if (trend_persist_126 is not None and trend_persist_126 >= CHART_SMOOTH_TREND_PERSIST_THRESHOLD and
                pullback_median is not None and pullback_median <= CHART_SMOOTH_PULLBACK_MEDIAN_THRESHOLD and
                extreme_bar_freq is not None and extreme_bar_freq <= CHART_SMOOTH_EXTREME_BAR_THRESHOLD):
            _add("smooth_compounder_grind")

    # 5. stair_step_leader
    if len(labels) < CHART_MAX_LABELS:
        if (breakout_ft_rate is not None and breakout_ft_rate >= CHART_STAIR_FT_RATE_THRESHOLD and
                slope_stability is not None and slope_stability >= CHART_STAIR_SLOPE_STABILITY_THRESHOLD):
            _add("stair_step_leader")

    # 6. volatile_momentum_vehicle
    if len(labels) < CHART_MAX_LABELS:
        if (hv_pctile is not None and hv_pctile >= CHART_VMV_HV_PCTILE_THRESHOLD and
                trend_persist_20 is not None and trend_persist_20 >= CHART_VMV_TREND_PERSIST_THRESHOLD):
            _add("volatile_momentum_vehicle")

    # 7. basing_accumulator
    if len(labels) < CHART_MAX_LABELS:
        if (range_compression is not None and range_compression <= CHART_BASING_RANGE_COMPRESSION_THRESHOLD and
                vol_squeeze_state in CHART_BASING_VOL_SQUEEZE_STATES):
            _add("basing_accumulator")

    # 8. defensive_range_stock
    if len(labels) < CHART_MAX_LABELS:
        if (hv_pctile is not None and hv_pctile <= CHART_DEFENSIVE_HV_PCTILE_THRESHOLD and
                trend_persist_126 is not None and abs(trend_persist_126) <= CHART_DEFENSIVE_TREND_PERSIST_ABS_THRESHOLD and
                pullback_p90 is not None and pullback_p90 <= CHART_DEFENSIVE_PULLBACK_P90_THRESHOLD):
            _add("defensive_range_stock")

    # 9. mixed_chart — fallback when nothing matched
    if not labels:
        # Check if we had enough non-None inputs to have evaluated something
        inputs_present = [
            v for v in [
                event_gap_contrib, gap_share, failed_breakout_rate,
                trend_persist_60, trend_persist_126, trend_persist_20,
                pullback_median, pullback_p90, extreme_bar_freq,
                breakout_ft_rate, slope_stability, range_compression,
            ] if v is not None
        ]
        if inputs_present:
            labels.append("mixed_chart")
        else:
            missing.append("path_features_all_none")
            return None, missing, snapshot

    return labels, missing, snapshot


# ---------------------------------------------------------------------------
# Microstructure cascade
# ---------------------------------------------------------------------------


def _classify_microstructure(
    path_features: dict | None,
) -> tuple[list[str] | None, list[str], dict]:
    """Return (labels_or_None, missing_inputs, feature_snapshot)."""
    missing: list[str] = []
    snapshot: dict = {}

    dollar_adv = _pf(path_features, "dollar_adv_21d")
    cs_spread = _pf(path_features, "cs_spread_252")
    amihud = _pf(path_features, "amihud_252")
    extreme_bar_freq = _pf(path_features, "extreme_bar_freq_252")
    gap_share = _pf(path_features, "gap_share_252")
    reversal_hl = _pf(path_features, "reversal_half_life")

    # §2-shape microstructure sub-dict: adv_usd_21d / amihud_252 / cs_spread_252
    # amihud_252 = raw |ret|/(close·volume) ≈ 1e-12..1e-8; W2b converts to pctile.
    snapshot = {
        "adv_usd_21d": dollar_adv,
        "cs_spread_252": cs_spread,
        "amihud_252": amihud,
        "extreme_bar_freq_252": extreme_bar_freq,
        "gap_share_252": gap_share,
        "reversal_half_life": reversal_hl,
    }

    # Return None only when ALL six micro inputs are None — gap_discontinuity_risk
    # and slow_mean_reversion_liquidity remain evaluable on OHLC-only (no-volume) histories.
    if (dollar_adv is None and cs_spread is None and amihud is None and
            extreme_bar_freq is None and gap_share is None and reversal_hl is None):
        missing.append("path_features.volume_missing")
        return None, missing, snapshot

    labels: list[str] = []

    def _add(label: str) -> bool:
        if len(labels) < MICRO_MAX_LABELS:
            labels.append(label)
            return True
        return False

    # 1. tight_spread_absorber — ADV + CS-spread only; amihud passes through
    # as a raw value (amihud_252) for W2b cross-sectional percentile ranking.
    if (dollar_adv is not None and dollar_adv >= MICRO_TIGHT_ADV_THRESHOLD and
            cs_spread is not None and cs_spread <= MICRO_TIGHT_CS_SPREAD_THRESHOLD):
        _add("tight_spread_absorber")

    # 2. wide_spread_impact
    if len(labels) < MICRO_MAX_LABELS:
        if (dollar_adv is not None and dollar_adv <= MICRO_WIDE_ADV_THRESHOLD) or \
           (cs_spread is not None and cs_spread >= MICRO_WIDE_CS_SPREAD_THRESHOLD):
            _add("wide_spread_impact")

    # 3. gap_discontinuity_risk
    if len(labels) < MICRO_MAX_LABELS:
        if (extreme_bar_freq is not None and extreme_bar_freq >= MICRO_DISC_EXTREME_BAR_THRESHOLD) or \
           (gap_share is not None and gap_share >= MICRO_DISC_GAP_SHARE_THRESHOLD):
            _add("gap_discontinuity_risk")

    # 4. slow_mean_reversion_liquidity
    if len(labels) < MICRO_MAX_LABELS:
        if reversal_hl is not None and reversal_hl <= MICRO_SLOW_MR_HALF_LIFE_THRESHOLD:
            _add("slow_mean_reversion_liquidity")

    # 5. mixed fallback
    if not labels:
        labels.append("mixed_microstructure")

    return labels, missing, snapshot


# ---------------------------------------------------------------------------
# Ownership habitat cascade
# ---------------------------------------------------------------------------


def _classify_ownership(
    positioning: dict | None,
    smart_money: dict | None,
    basket_membership: list | None,
    etf_weight_max: float | None,
    attention_z: float | None,
    bo_regime: str | None,
    market_cap: float | None,
) -> tuple[list[str] | None, list[str], dict, list[str]]:
    """Return (labels_or_None, missing_inputs, snapshot, proxy_basis_list)."""
    missing: list[str] = []

    pos = positioning or {}
    short_pct = _safe_float(pos.get("short_pct_float"))
    dtc = _safe_float(pos.get("days_to_cover"))
    insider_net = _safe_float(pos.get("insider_net_usd_mn"))
    insider_cluster = _safe_bool(pos.get("insider_cluster"))
    insider_n_buyers = _safe_int(pos.get("insider_n_buyers"))

    _sm = smart_money or {}
    ownership_hhi = _safe_float(_sm.get("ownership_hhi"))
    n_holders = _safe_int(_sm.get("n_holders"))

    attention_z_f = _safe_float(attention_z)
    etf_wt = _safe_float(etf_weight_max)
    mktcap = _safe_float(market_cap)
    basket_list = basket_membership or []

    snapshot = {
        "short_pct_float": short_pct,
        "days_to_cover": dtc,
        "insider_cluster": insider_cluster,
        "insider_n_buyers": insider_n_buyers,
        "attention_z": attention_z_f,
        "etf_weight_max": etf_wt,
        "market_cap": mktcap,
        "basket_membership_count": len(basket_list),
        "bo_regime": bo_regime,
    }

    # Check if any ownership input is present
    any_input = any(v is not None for v in [
        short_pct, dtc, insider_cluster, insider_n_buyers,
        attention_z_f, etf_wt, mktcap, bo_regime,
    ]) or len(basket_list) >= OWN_ETF_BASKET_MEMBERSHIP_MIN

    if not any_input:
        missing.append("ownership_all_inputs_missing")
        return None, missing, snapshot, []

    labels: list[str] = []
    proxy_basis: list[str] = []

    def _add(label: str, basis: str) -> bool:
        if len(labels) < OWNERSHIP_MAX_LABELS:
            labels.append(label)
            proxy_basis.append(basis)
            return True
        return False

    # 1. short_interest_tinderbox
    if (short_pct is not None and short_pct >= OWN_SI_TINDERBOX_SHORT_PCT) or \
       (dtc is not None and dtc >= OWN_SI_TINDERBOX_DTC):
        _add("short_interest_tinderbox", "finra_si")

    # 2. retail_attention
    if len(labels) < OWNERSHIP_MAX_LABELS:
        if attention_z_f is not None and attention_z_f >= OWN_RETAIL_ATTENTION_Z:
            _add("retail_attention", "wiki_attention_z")

    # 3. insider_founder_controlled
    if len(labels) < OWNERSHIP_MAX_LABELS:
        if (insider_cluster is True and
                insider_n_buyers is not None and insider_n_buyers >= OWN_INSIDER_N_BUYERS_MIN):
            _add("insider_founder_controlled", "form4_cluster")

    # 4. passive_index_magnet
    if len(labels) < OWNERSHIP_MAX_LABELS:
        if (etf_wt is not None and etf_wt >= OWN_PASSIVE_ETF_WEIGHT_THRESHOLD) or \
           (mktcap is not None and mktcap >= OWN_PASSIVE_MARKET_CAP_THRESHOLD):
            _add("passive_index_magnet", "etf_weight")

    # 5. etf_basketed_conduit
    if len(labels) < OWNERSHIP_MAX_LABELS:
        if len(basket_list) >= OWN_ETF_BASKET_MEMBERSHIP_MIN:
            _add("etf_basketed_conduit", "basket_membership")

    # 6. long_only_sponsor
    if len(labels) < OWNERSHIP_MAX_LABELS:
        if (bo_regime == OWN_LOS_BO_REGIME and
                short_pct is not None and short_pct <= OWN_LOS_SHORT_PCT_MAX and
                (attention_z_f is None or attention_z_f < OWN_LOS_ATTENTION_Z_MAX)):
            _add("long_only_sponsor", "13dg_passive")

    # 7. mixed fallback
    if not labels:
        labels.append("mixed_ownership")
        proxy_basis.append("mixed")

    return labels, missing, snapshot, proxy_basis


# ---------------------------------------------------------------------------
# Current mode cascade
# ---------------------------------------------------------------------------


def _classify_current_mode(
    positioning: dict | None,
    gex: dict | None,
    events: dict | None,
    tech: dict | None,
    attention_z: float | None,
    oracle_episode_active: bool | None,
    path_features: dict | None,
) -> tuple[list[str] | None, list[str], dict, int]:
    """Return (modes_or_None, missing_inputs, evidence_dict, expires_after_days).

    Multi-mode expiry rule: when multiple modes fire, expires_after_days is the
    MINIMUM expiry across all assigned modes (shortest-lived mode governs).
    Schema stays a scalar per masterplan §2 — the scalar is min(MODE_EXPIRY[m] for m in modes).
    """
    missing: list[str] = []

    pos = positioning or {}
    short_pct = _safe_float(pos.get("short_pct_float"))

    _gex = gex or {}
    gamma_regime = _gex.get("gamma_regime")
    # dist_to_flip_pct is signed (spot−flip)/spot·100 from gex_engine;
    # use abs() so tight-pin fires regardless of whether spot is above or below flip.
    flip_dist = _safe_float(_gex.get("dist_to_flip_pct"))

    _ev = events or {}
    days_to_earnings = _safe_int(_ev.get("days_to_earnings"))
    event_window_active = _safe_bool(_ev.get("event_window_active"))

    _tech = tech or {}
    ret_21d = _safe_float(_tech.get("ret_21d"))
    rel_volume = _safe_float(_tech.get("rel_volume"))
    hv_pctile = _safe_float(_tech.get("hv_pctile"))
    obv_slope_up = _safe_bool(_tech.get("obv_slope_up"))
    off_52w_high_pct = _safe_float(_tech.get("off_52w_high_pct"))
    months_underwater = _safe_float(_tech.get("months_underwater"))
    vol_squeeze_state = _tech.get("vol_squeeze_state")

    attention_z_f = _safe_float(attention_z)
    oracle_active = _safe_bool(oracle_episode_active)

    # Path features needed for some modes
    trend_persist_20 = _pf(path_features, "trend_persist_20")
    failed_breakout_rate = _pf(path_features, "failed_breakout_rate_63")

    # If no tech block at all, mode is None
    has_tech = any(v is not None for v in [
        ret_21d, rel_volume, hv_pctile, obv_slope_up,
        off_52w_high_pct, months_underwater, vol_squeeze_state,
    ])
    if not has_tech:
        missing.append("tech_missing")
        return None, missing, {}, 21

    modes: list[str] = []
    evidence: dict = {}

    def _add_mode(mode: str, ev: dict) -> bool:
        if len(modes) < MODE_MAX_LABELS:
            modes.append(mode)
            evidence.update(ev)
            return True
        return False

    # 1. event_override
    if (event_window_active is True or
            (days_to_earnings is not None and abs(days_to_earnings) <= MODE_EVENT_DAYS_TO_EARNINGS_THRESHOLD)):
        _add_mode("event_override", {
            "event_window_active": event_window_active,
            "days_to_earnings": days_to_earnings,
        })

    # 2. forced_liquidation
    if len(modes) < MODE_MAX_LABELS:
        if (ret_21d is not None and ret_21d <= MODE_FORCED_LIQ_RET_21D_THRESHOLD and
                rel_volume is not None and rel_volume >= MODE_FORCED_LIQ_REL_VOL_THRESHOLD):
            _add_mode("forced_liquidation", {
                "ret_21d": ret_21d,
                "rel_volume": rel_volume,
            })

    # 3. squeeze
    if len(modes) < MODE_MAX_LABELS:
        if (short_pct is not None and short_pct >= MODE_SQUEEZE_SHORT_PCT_THRESHOLD and
                ret_21d is not None and ret_21d >= MODE_SQUEEZE_RET_21D_THRESHOLD):
            _add_mode("squeeze", {
                "short_pct_float": short_pct,
                "ret_21d": ret_21d,
            })

    # 4. options_pin — gex_engine "long" = dealers net long gamma (pin/dampen behavior).
    # dist_to_flip_pct is signed; abs() <= threshold means spot is near the flip level.
    if len(modes) < MODE_MAX_LABELS:
        if (gamma_regime == "long" and
                flip_dist is not None and abs(flip_dist) <= MODE_PIN_FLIP_DIST_THRESHOLD):
            _add_mode("options_pin", {
                "gamma_regime": gamma_regime,
                "dist_to_flip_pct": flip_dist,
            })

    # 5. negative_gamma_trend — gex_engine "short" = dealers net short gamma (amplify/trend).
    if len(modes) < MODE_MAX_LABELS:
        if gamma_regime == "short":
            _add_mode("negative_gamma_trend", {"gamma_regime": gamma_regime})

    # 6. sector_rotation_feeder
    if len(modes) < MODE_MAX_LABELS:
        if oracle_active is True:
            _add_mode("sector_rotation_feeder", {"oracle_episode_active": True})

    # 7. post_news_attention
    if len(modes) < MODE_MAX_LABELS:
        if attention_z_f is not None and attention_z_f >= MODE_POST_NEWS_ATTENTION_Z:
            _add_mode("post_news_attention", {"attention_z": attention_z_f})

    # 8. stale_dead_money
    if len(modes) < MODE_MAX_LABELS:
        if (months_underwater is not None and months_underwater >= MODE_STALE_MONTHS_UNDERWATER_THRESHOLD and
                hv_pctile is not None and hv_pctile <= MODE_STALE_HV_PCTILE_THRESHOLD and
                rel_volume is not None and rel_volume <= MODE_STALE_REL_VOLUME_THRESHOLD):
            _add_mode("stale_dead_money", {
                "months_underwater": months_underwater,
                "hv_pctile": hv_pctile,
                "rel_volume": rel_volume,
            })

    # 9. accumulation
    if len(modes) < MODE_MAX_LABELS:
        if (vol_squeeze_state in MODE_ACCUM_VOL_SQUEEZE_STATES and
                obv_slope_up is True and
                trend_persist_20 is not None and trend_persist_20 >= MODE_ACCUM_TREND_PERSIST_MIN):
            _add_mode("accumulation", {
                "vol_squeeze_state": vol_squeeze_state,
                "obv_slope_up": obv_slope_up,
                "trend_persist_20": trend_persist_20,
            })

    # 10. distribution — near 52-week high (off_52w_high_pct is negative, e.g., -8.5 = 8.5% below high;
    # "within 10% of high" means off_52w_high_pct >= -MODE_DIST_OFF_52W_HIGH_THRESHOLD)
    if len(modes) < MODE_MAX_LABELS:
        if (off_52w_high_pct is not None and off_52w_high_pct >= -MODE_DIST_OFF_52W_HIGH_THRESHOLD and
                failed_breakout_rate is not None and failed_breakout_rate >= MODE_DIST_FAILED_BO_THRESHOLD and
                obv_slope_up is False):
            _add_mode("distribution", {
                "off_52w_high_pct": off_52w_high_pct,
                "failed_breakout_rate_63": failed_breakout_rate,
                "obv_slope_up": obv_slope_up,
            })

    # 11. normal — default when tech present
    if not modes:
        modes.append("normal")
        evidence["reason"] = "no_special_mode_conditions_met"

    # Expiry: use the minimum (shortest-lived) expiry across assigned modes
    expiry = min(MODE_EXPIRY.get(m, 21) for m in modes)

    return modes, missing, evidence, expiry


# ---------------------------------------------------------------------------
# Coverage calculation helper
# ---------------------------------------------------------------------------


def _coverage(
    archetype: dict | None,
    dna_class: dict | None,
    positioning: dict | None,
    smart_money: dict | None,
    basket_membership: list | None,
    etf_weight_max: float | None,
    attention_z: float | None,
    path_features: dict | None,
    tech: dict | None,
    gex: dict | None,
    events: dict | None,
) -> dict:
    """Coverage fraction per axis (fraction of possible inputs that were present)."""
    cov: dict = {}

    # archetype: 1 input
    cov["archetype"] = 1.0 if (archetype and archetype.get("key")) else 0.0

    # dna_class: 1 input
    cov["dna_class"] = 1.0 if (dna_class and dna_class.get("key")) else 0.0

    # ownership: 6 possible inputs
    own_inputs = [
        (positioning or {}).get("short_pct_float"),
        (positioning or {}).get("days_to_cover"),
        (positioning or {}).get("insider_cluster"),
        attention_z,
        etf_weight_max,
        basket_membership,
    ]
    own_present = sum(1 for v in own_inputs if v is not None)
    cov["ownership"] = own_present / 6.0

    # micro: 4 path feature inputs
    micro_keys = ["dollar_adv_21d", "cs_spread_252", "amihud_252", "reversal_half_life"]
    micro_present = sum(
        1 for k in micro_keys if _pf(path_features, k) is not None
    )
    cov["micro"] = micro_present / 4.0

    # chart: 10 path feature inputs
    chart_keys = [
        "trend_persist_20", "trend_persist_60", "trend_persist_126",
        "slope_stability_126", "pullback_median_252", "pullback_p90_252",
        "breakout_ft_rate_63", "failed_breakout_rate_63",
        "event_gap_contrib_252", "gap_share_252",
    ]
    chart_present = sum(
        1 for k in chart_keys if _pf(path_features, k) is not None
    )
    cov["chart"] = chart_present / 10.0

    return cov


# ---------------------------------------------------------------------------
# Public API: assess()
# ---------------------------------------------------------------------------


def assess(
    ticker: str,
    *,
    as_of: str,
    path_features: dict | None = None,
    archetype: dict | None = None,
    dna_class: dict | None = None,
    positioning: dict | None = None,
    smart_money: dict | None = None,
    basket_membership: list | None = None,
    etf_weight_max: float | None = None,
    attention_z: float | None = None,
    bo_regime: str | None = None,
    gex: dict | None = None,
    events: dict | None = None,
    tech: dict | None = None,
    oracle_episode_active: bool | None = None,
    market_cap: float | None = None,
) -> dict:
    """Assemble the stock_personality.v1 object for one ticker.

    Parameters
    ----------
    ticker : str
        Ticker symbol (uppercase).
    as_of : str
        ISO date string "YYYY-MM-DD".
    path_features : dict | None
        Output of engine.path_personality.features() — may be None or partial.
        Gap/wick keys may be None on close-only histories.
    archetype : dict | None
        {"key": str, "confidence": float} from stock_fundamentals.v2.
    dna_class : dict | None
        {"key": str, "style_regime": str, "as_of": str} from dna_class.json (T-1).
    positioning : dict | None
        {"short_pct_float": float|None, "days_to_cover": float|None,
         "insider_net_usd_mn": float|None, "insider_cluster": bool|None,
         "insider_n_buyers": int|None}.
    smart_money : dict | None
        {"ownership_hhi": float|None, "n_holders": int|None}.
    basket_membership : list[str] | None
        Thematic basket keys the ticker belongs to.
    etf_weight_max : float | None
        Max weight_pct across tracked ETFs.
    attention_z : float | None
        Wiki/social attention z-score.
    bo_regime : str | None
        Beneficial-ownership regime: "activist"|"flip"|"passive"|"custodial"|"none".
    gex : dict | None
        {"gamma_regime": "long"|"short"|None,  ← gex_engine canonical values
         "dist_to_flip_pct": float|None}.       ← signed (spot−flip)/spot·100
    events : dict | None
        {"days_to_earnings": int|None, "event_window_active": bool|None}.
    tech : dict | None
        {"hv_pctile": float|None,          ← 0-100 from engine.stock_technicals.hv_pctile
         "rel_volume": float|None,          ← ratio; 1.0 = normal
         "obv_slope_up": bool|None,
         "off_52w_high_pct": float|None,    ← SIGNED negative pct: (px/52w_high−1)*100
                                               e.g. -15.0 = 15% below high; 0.0 = at high
         "ret_21d": float|None,             ← FRACTION e.g. -0.30 (not percent)
         "months_underwater": float|None,   ← derived from entry_primitives.time_underwater_series (bars)/21
         "vol_squeeze_state": str|None,     ← rec["vol_squeeze"]["state"] (NOT rec["tech"])
         "ladder_state": str|None}.

    W2b caller sourcing contract
    ----------------------------
    vol_squeeze_state  ← rec["vol_squeeze"]["state"]
    ret_21d            ← close.pct_change(21) as a fraction (e.g. -0.30)
    months_underwater  ← engine.entry_primitives.time_underwater_series (bars) / 21.0
    hv_pctile          ← tech.hv_pctile (0-100 scale)
    rel_volume         ← tech.rel_volume (ratio, 1.0 = normal)
    obv_slope_up       ← tech.obv_slope_up (bool)
    off_52w_high_pct   ← tech.off_52w_high_pct — SIGNED NEGATIVE percent below high
                         (stock_technicals: (px/52w_high−1)*100);
                         "near high" means off_52w_high_pct >= −10 (within 10% of high)
    gex.gamma_regime   ← gex_engine "long"|"short" (NOT "positive"/"negative")
    gex.dist_to_flip_pct ← gex_engine signed percent; options_pin uses abs(dist) <= threshold
    short_pct_float    ← positioning.short.pct_float (PERCENT 0-100)
    days_to_cover      ← positioning.short.days_to_cover
    oracle_episode_active : bool | None
        Whether the ticker's sector has an active Oracle episode.
    market_cap : float | None
        Market cap in USD.

    Returns
    -------
    dict conforming to the stock_personality.v1 schema (§2 of masterplan).
    """
    all_missing: list[str] = []
    as_of_by_axis: dict = {}

    # ---- base.archetype ----
    if archetype and archetype.get("key"):
        base_archetype = {
            "key": archetype["key"],
            "source": "stock_fundamentals.v2",
            "confidence": _safe_float(archetype.get("confidence")),
        }
        as_of_by_axis["archetype"] = as_of
    else:
        base_archetype = {"key": None, "source": "stock_fundamentals.v2", "confidence": None}
        all_missing.append("archetype")

    # ---- base.dna_class ----
    if dna_class and dna_class.get("key"):
        base_dna = {
            "key": dna_class["key"],
            "source": "site/factordata/dna_class.json",
            "as_of": dna_class.get("as_of", "T-1"),
            "style_regime": dna_class.get("style_regime"),
        }
        as_of_by_axis["dna_class"] = dna_class.get("as_of", "T-1")
    else:
        base_dna = {
            "key": None,
            "source": "site/factordata/dna_class.json",
            "as_of": "T-1",
            "style_regime": None,
        }
        all_missing.append("dna_class")

    # ---- base.chart_personality ----
    chart_labels, chart_missing, chart_snapshot = _classify_chart(path_features, tech)
    all_missing.extend(chart_missing)
    if chart_labels is not None:
        as_of_by_axis["chart"] = as_of
    base_chart = {
        "labels": chart_labels,
        "features": chart_snapshot,
    }

    # ---- base.microstructure ----
    micro_labels, micro_missing, micro_snapshot = _classify_microstructure(path_features)
    all_missing.extend(micro_missing)
    if micro_labels is not None:
        as_of_by_axis["micro"] = as_of
    base_micro = {
        "labels": micro_labels,
        **micro_snapshot,
    }

    # ---- base.ownership_habitat ----
    own_labels, own_missing, own_snapshot, own_proxy = _classify_ownership(
        positioning, smart_money, basket_membership, etf_weight_max,
        attention_z, bo_regime, market_cap,
    )
    all_missing.extend(own_missing)
    if own_labels is not None:
        as_of_by_axis["ownership"] = as_of
    base_ownership = {
        "labels": own_labels,
        "proxy_basis": own_proxy,
    }

    # ---- current_mode ----
    modes, mode_missing, mode_evidence, mode_expiry = _classify_current_mode(
        positioning, gex, events, tech, attention_z,
        oracle_episode_active, path_features,
    )
    all_missing.extend(mode_missing)

    # ---- coverage ----
    coverage = _coverage(
        archetype, dna_class, positioning, smart_money,
        basket_membership, etf_weight_max, attention_z,
        path_features, tech, gex, events,
    )

    # ---- assemble ----
    obj = {
        "schema": "stock_personality.v1",
        "as_of": as_of,
        "ticker": ticker,
        "base": {
            "archetype": base_archetype,
            "dna_class": base_dna,
            "ownership_habitat": base_ownership,
            "microstructure": base_micro,
            "chart_personality": base_chart,
        },
        "current_mode": {
            "modes": modes,
            "evidence": mode_evidence,
            "expires_after_days": mode_expiry,
        },
        "setup_compatibility": {
            "favored_species": [],
            "caution_species": [],
            "derived_from": "species_registry.archetype_scope × axes — display-only",
        },
        "evidence": {
            "coverage": coverage,
            "missing": list(dict.fromkeys(all_missing)),  # deduplicate, preserve order
            "as_of_by_axis": as_of_by_axis,
            "lineage": "research/STOCK_PERSONALITY_MASTERPLAN_BY_FABLE.md",
        },
        "authority": _AUTHORITY,
    }

    return obj


# ---------------------------------------------------------------------------
# Public API: setup_compatibility()
# ---------------------------------------------------------------------------


def setup_compatibility(personality: dict, species_entries: list[dict]) -> dict:
    """Derive favored/caution species from the archetype × species_registry.

    This is DERIVED display only (R-SP18): recomputed, never stored as truth.
    Does not modify archetype_scope automatically.

    Parameters
    ----------
    personality : dict
        A stock_personality.v1 object (from assess()).
    species_entries : list[dict]
        Species registry entries.  Each must have at minimum:
        - "id" or "species_id": str
        - "validation_status": str
        - "archetype_scope": {"applies": list|str, "hostile": list|str}

    Returns
    -------
    dict with keys: "favored_species", "caution_species", "derived_from".
    """
    archetype_key = (
        (personality.get("base") or {})
        .get("archetype", {})
        .get("key") or ""
    )

    favored: list[str] = []
    caution: list[str] = []

    for entry in species_entries:
        status = entry.get("validation_status") or ""
        if status not in _COMPAT_VALID_STATUSES:
            continue

        species_id = entry.get("id") or entry.get("species_id") or ""
        scope = entry.get("archetype_scope") or {}

        applies_raw = scope.get("applies") or []
        hostile_raw = scope.get("hostile") or []

        # Normalize to list
        applies = [applies_raw] if isinstance(applies_raw, str) else list(applies_raw)
        hostile = [hostile_raw] if isinstance(hostile_raw, str) else list(hostile_raw)

        if archetype_key and _archetype_mentioned(archetype_key, applies):
            favored.append(species_id)
        elif archetype_key and _archetype_mentioned(archetype_key, hostile):
            caution.append(species_id)

    return {
        "favored_species": favored,
        "caution_species": caution,
        "derived_from": "species_registry.archetype_scope × axes — display-only",
    }


def _archetype_mentioned(archetype_key: str, text_list: list[str]) -> bool:
    """Check if archetype_key appears (case-insensitive, underscore/hyphen/space) in any text."""
    if not archetype_key:
        return False
    # Normalize key: produce variants
    key_lower = archetype_key.lower()
    # underscore, hyphen, space variants
    variants = {
        key_lower,
        key_lower.replace("_", "-"),
        key_lower.replace("_", " "),
    }
    for text in text_list:
        text_lower = str(text).lower()
        for v in variants:
            if v in text_lower:
                return True
    return False
