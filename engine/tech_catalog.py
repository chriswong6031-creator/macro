"""engine/tech_catalog.py — AI-friendly registry of every technical signal in the suite.

Single source of truth: read this file to see all available technical signals, their
families, parameters, and how to compute them on an OHLCV DataFrame.

AGGREGATION SOURCES
-------------------
Legacy (pre-integration) modules:
- engine.ma_crosses     SIGNALS dict  (ma_crosses, ma_price families)
- engine.pivots         SIGNALS dict  (pivots family)
- engine.rsi_signals    SIGNALS dict  (rsi_bands family)
- engine.formations     SIGNALS dict  (formations family)
- engine.trend_signals  SIGNALS dict  (trend, performance families)
- engine.fundamental_screens SIGNALS dict (fundamental_valuation family) — cross-sectional;
                          fn(df) returns a constant Series (requires df.attrs['ticker']).
- engine.insider_power_signals SIGNALS dict (insider family) — cross-sectional quality-weighted
                          Form-4 signals (insider_power_state, insider_buy, insider_sell).
- engine.tech_stars     golden_star_signal / death_star_signal wrappers (tech_stars family)
  Pre-registered MA pairs: (7,35), (21,100), (50,200) for both Golden Star and Death Star.
  Also includes 'new_golden_star': freshly-fired Golden Star age <= 1 trading day.
- engine.ichimoku_signals        (ichimoku family)
- engine.trend_ribbon_signals    (trend_ribbon family)
- engine.rsi_stack_signals       (rsi_stack family)
- engine.bollinger_event_signals (bollinger_events family)
- engine.momentum_events         (macd_events / rsi_events / stoch_events / stoch_events_2w)
- engine.indicators_m2           (vwap_events / volume_profile_events — daily-only, D04)

Technical Lab modules (integrated in this PR):
- engine.trend_strength_signals   (directional_trend / trend_recency / price_pressure families)
- engine.compression_signals      (compression_release / trend_efficiency / breakout_channel / volatility_range)
- engine.volume_flow_signals      (volume_money_flow / volume_participation)
- engine.adaptive_trend_signals   (adaptive_trend / atr_adaptive_trend)
- engine.rank_momentum_signals    (rsi_mean_reversion / rank_trend)
- engine.path_risk_signals        (downside_path_risk / volatility_regime / volatility_range)
- engine.momentum_context_signals (multi_horizon_momentum / benchmark_relative_strength / volatility_channel)
- engine.bar_structure_signals    (pattern_structure)
- engine.fractal_pivot_signals    (fractal_structure)
- engine.challenger_signals       (multi_horizon_momentum / double_smoothed_momentum / cycle_transform /
                                   rsi_composite / macd_cycle / gap_imbalance — challenger_only=True)

NAMESPACING
-----------
Source-module signal IDs are already collision-free except for a potential clash between
tech_stars and ma_crosses naming conventions. Both use `golden_cross_*` / `death_cross_*`
names from ma_crosses and `golden_star_*` / `death_star_*` from tech_stars — no overlap.
fundamental_screens IDs are also distinct. No prefix-mangling is needed.

HONESTY CONTRACT
----------------
Display-only / research. No 'validated' claim in any user-facing string.
No LLM-originated signals, scores, or escalations.

DESCRIPTOR KEYS
---------------
Required keys (enforced by _build_catalog):
  fn              : callable(df, **params) -> pd.Series
  kind            : 'event' | 'state'
  family          : str (source module family name)
  direction       : int  +1 / -1 / 0
  default_params  : dict
  display         : {'en': str, 'zh': str}
  glyph           : str
  dependency_family : str (signal cluster for confluence grammar)
  role            : 'context'|'setup'|'trigger'|'participation'|'risk'

Optional keys:
  screener_firing    : bool (override inference; see is_screener_firing())
  entry_stack_blocked: bool (default False; True signals must not compound with same entry)
  challenger_only    : bool (default False; True = held-out during primary combo search)
  provenance         : str (author/publication + source URL)
  actionable_lag     : int (bars delay before signal is actionable; 0 = same bar)
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Required descriptor keys — enforced by the catalog loader
# ---------------------------------------------------------------------------
_REQUIRED_KEYS: frozenset[str] = frozenset({
    "fn", "kind", "family", "direction", "default_params", "display", "glyph",
    "dependency_family", "role",
})

# ---------------------------------------------------------------------------
# Legacy metadata backfill
# ---------------------------------------------------------------------------
# Legacy source modules predate the extended descriptor contract (dependency_family,
# role, entry_stack_blocked, challenger_only, provenance, actionable_lag). Rather than
# editing every source module, we maintain a backfill table here keyed by signal_id
# (or by family where all members share the same metadata). Applied in _build_catalog().
#
# Cluster assignments follow the brief:
#   ma_crosses / ma_price / trend / trend_ribbon / tech_stars → 'moving_average_trend'
#   pivots / formations → 'pattern_structure'
#   rsi_bands / rsi_events / rsi_stack → 'rsi_mean_reversion'
#   bollinger_events → 'volatility_channel'
#   macd_events → 'macd_ma_spread'
#   stoch_events / stoch_events_2w → 'stochastic_oscillator'
#   ichimoku → 'cloud_trend'  (entry_stack_blocked=True per RUL-33-OSCSPECIES)
#   performance → 'multi_horizon_momentum'
#   fundamental_valuation → 'fundamental_value'
#   insider → 'insider_flow'
#
# Default role: events → 'trigger', states → 'context'
# Overrides: rsi oversold/overbought states → 'setup'; rsi_stack_oversold/overbought → 'setup'

_LEGACY_META_BY_FAMILY: dict[str, dict[str, Any]] = {
    "ma_crosses":         {"dependency_family": "moving_average_trend", "role": "trigger",
                           "entry_stack_blocked": False, "challenger_only": False,
                           "provenance": "Murphy, J.J. (1999) Technical Analysis of the Financial Markets",
                           "actionable_lag": 0},
    "ma_price":           {"dependency_family": "moving_average_trend", "role": "trigger",
                           "entry_stack_blocked": False, "challenger_only": False,
                           "provenance": "Murphy, J.J. (1999) Technical Analysis of the Financial Markets",
                           "actionable_lag": 0},
    "tech_stars":         {"dependency_family": "moving_average_trend", "role": "trigger",
                           "entry_stack_blocked": False, "challenger_only": False,
                           "provenance": "Adapted Golden/Death Cross composite (internal)",
                           "actionable_lag": 0},
    "trend":              {"dependency_family": "moving_average_trend", "role": "context",
                           "entry_stack_blocked": False, "challenger_only": False,
                           "provenance": "Murphy, J.J. (1999) Technical Analysis of the Financial Markets",
                           "actionable_lag": 0},
    "trend_ribbon":       {"dependency_family": "moving_average_trend",
                           "entry_stack_blocked": False, "challenger_only": False,
                           "provenance": "Darvas, N. (1960) How I Made 2,000,000 in the Stock Market",
                           "actionable_lag": 0},
    "pivots":             {"dependency_family": "pattern_structure", "role": "setup",
                           "entry_stack_blocked": False, "challenger_only": False,
                           "provenance": "Williams, L. (1999) Long-Term Secrets to Short-Term Trading",
                           "actionable_lag": 0},
    "formations":         {"dependency_family": "pattern_structure", "role": "trigger",
                           "entry_stack_blocked": False, "challenger_only": False,
                           "provenance": "Edwards, R.D. & Magee, J. (1948) Technical Analysis of Stock Trends",
                           "actionable_lag": 0},
    "rsi_bands":          {"dependency_family": "rsi_mean_reversion",
                           "entry_stack_blocked": False, "challenger_only": False,
                           "provenance": "Wilder, J.W. (1978) New Concepts in Technical Trading Systems",
                           "actionable_lag": 0},
    "rsi_events":         {"dependency_family": "rsi_mean_reversion", "role": "trigger",
                           "entry_stack_blocked": False, "challenger_only": False,
                           "provenance": "Wilder, J.W. (1978) New Concepts in Technical Trading Systems",
                           "actionable_lag": 0},
    "rsi_stack":          {"dependency_family": "rsi_mean_reversion",
                           "entry_stack_blocked": False, "challenger_only": False,
                           "provenance": "Wilder, J.W. (1978) New Concepts in Technical Trading Systems",
                           "actionable_lag": 0},
    "bollinger_events":   {"dependency_family": "volatility_channel",
                           "entry_stack_blocked": False, "challenger_only": False,
                           "provenance": "Bollinger, J. (2002) Bollinger on Bollinger Bands",
                           "actionable_lag": 0},
    "macd_events":        {"dependency_family": "macd_ma_spread", "role": "trigger",
                           "entry_stack_blocked": False, "challenger_only": False,
                           "provenance": "Appel, G. (2005) Technical Analysis: Power Tools for Active Investors",
                           "actionable_lag": 0},
    "stoch_events":       {"dependency_family": "stochastic_oscillator", "role": "trigger",
                           "entry_stack_blocked": False, "challenger_only": False,
                           "provenance": "Lane, G.C. (1984) Lane's Stochastics, Technical Analysis of Stocks & Commodities",
                           "actionable_lag": 0},
    "stoch_events_2w":    {"dependency_family": "stochastic_oscillator", "role": "trigger",
                           "entry_stack_blocked": False, "challenger_only": False,
                           "provenance": "Lane, G.C. (1984) Lane's Stochastics, Technical Analysis of Stocks & Commodities",
                           "actionable_lag": 0},
    "ichimoku":           {"dependency_family": "cloud_trend",
                           "entry_stack_blocked": True, "challenger_only": False,
                           "provenance": "Ichimoku, H. (1969) Ichimoku Kinko Hyo (one-look equilibrium chart)",
                           "actionable_lag": 0},
    "performance":        {"dependency_family": "multi_horizon_momentum",
                           "entry_stack_blocked": False, "challenger_only": False,
                           "provenance": "Internal performance composite",
                           "actionable_lag": 0},
    "fundamental_valuation": {"dependency_family": "fundamental_value",
                              "entry_stack_blocked": False, "challenger_only": False,
                              "provenance": "Fama, E.F. & French, K.R. (1992) The Cross-Section of Expected Stock Returns",
                              "actionable_lag": 0},
    "insider":            {"dependency_family": "insider_flow",
                           "entry_stack_blocked": False, "challenger_only": False,
                           "provenance": "Seyhun, H.N. (1998) Investment Intelligence from Insider Trading",
                           "actionable_lag": 0},
}

# Per-signal role overrides (applied after family defaults)
_LEGACY_ROLE_OVERRIDE: dict[str, str] = {
    # trend states
    "trend_rising_short": "context",
    "trend_falling_short": "context",
    "trend_rising_long": "context",
    "trend_falling_long": "context",
    # trend_ribbon states
    "ribbon_up": "context",
    "ribbon_down": "context",
    "ribbon_flip_up": "trigger",
    "ribbon_flip_down": "trigger",
    # rsi_bands: oversold/overbought are setups (zones entered before reversal)
    "rsi14_oversold": "setup",
    "rsi14_overbought": "setup",
    "rsi21_oversold": "setup",
    "rsi21_overbought": "setup",
    # rsi_stack states
    "rsi_stack_oversold": "setup",
    "rsi_stack_overbought": "setup",
    "rsi_stack_curl_up": "trigger",
    "rsi_stack_curl_down": "trigger",
    # bollinger states vs events
    "bb_band_walk_up": "context",
    "bb_band_walk_down": "context",
    "bb_upper_rejection": "trigger",
    "bb_lower_reclaim": "trigger",
    # ichimoku states vs events
    "ichimoku_above_cloud": "context",
    "ichimoku_below_cloud": "context",
    "ichimoku_tk_cross_up": "trigger",
    "ichimoku_tk_cross_down": "trigger",
    "ichimoku_cloud_breakout_up": "trigger",
    "ichimoku_cloud_breakdown": "trigger",
    # performance states
    "is_strong_move": "context",
    "return_1d": "context",
    "possible_runners": "trigger",
    # fundamental states
    "valuation_pctile": "context",
    "undervalued_state": "setup",
    "overvalued_state": "setup",
    # insider
    "insider_power_state": "context",
    "insider_buy": "participation",
    "insider_sell": "participation",
    # pivots are setups
    "pivot_bottom": "setup",
    "pivot_top": "setup",
}


def _apply_legacy_meta(sid: str, descriptor: dict[str, Any]) -> dict[str, Any]:
    """Backfill extended descriptor keys for a legacy signal that lacks them.

    Modifies descriptor IN PLACE and returns it.  Only fills keys that are absent
    — if the source module already set them (new modules), we leave them alone.
    """
    fam = descriptor.get("family", "")
    meta = _LEGACY_META_BY_FAMILY.get(fam, {})

    for key in ("dependency_family", "entry_stack_blocked", "challenger_only",
                "provenance", "actionable_lag"):
        if key not in descriptor:
            descriptor[key] = meta.get(key, _LEGACY_DEFAULTS[key])

    if "role" not in descriptor:
        # Per-signal override first, then family default, then kind-based default
        if sid in _LEGACY_ROLE_OVERRIDE:
            descriptor["role"] = _LEGACY_ROLE_OVERRIDE[sid]
        elif "role" in meta:
            descriptor["role"] = meta["role"]
        else:
            # kind-based default: events → 'trigger', states → 'context'
            descriptor["role"] = "trigger" if descriptor.get("kind") == "event" else "context"

    return descriptor


_LEGACY_DEFAULTS: dict[str, Any] = {
    "dependency_family": "unknown",
    "role": "context",
    "entry_stack_blocked": False,
    "challenger_only": False,
    "provenance": "",
    "actionable_lag": 0,
}


# ---------------------------------------------------------------------------
# Import source-module SIGNALS dicts
# ---------------------------------------------------------------------------

def _safe_import_signals(module_path: str, label: str) -> dict[str, dict[str, Any]]:
    """Import SIGNALS from a module, returning {} and logging a warning on failure."""
    try:
        import importlib
        mod = importlib.import_module(module_path)
        sigs = getattr(mod, "SIGNALS", None)
        if sigs is None:
            log.warning("tech_catalog: %s has no SIGNALS dict", module_path)
            return {}
        return dict(sigs)
    except Exception as exc:  # noqa: BLE001
        log.warning("tech_catalog: failed to import %s (%s): %s", label, module_path, exc)
        return {}


# ---------------------------------------------------------------------------
# tech_stars: hand-build entries for the six pre-registered star pairs + new_golden_star
# ---------------------------------------------------------------------------

def _build_tech_stars_signals() -> dict[str, dict[str, Any]]:
    """Build SIGNALS entries for Golden Star, Death Star, and new_golden_star."""
    try:
        from engine.tech_stars import (  # noqa: PLC0415
            golden_star_signal,
            death_star_signal,
            PRICE_GATE_PCT,
            ADV_FLOOR_USD,
            TREND_K,
            CONFIRM_DAYS,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("tech_catalog: cannot import engine.tech_stars: %s", exc)
        return {}

    out: dict[str, dict[str, Any]] = {}

    # Pre-registered MA pairs
    pairs = [(7, 35), (21, 100), (50, 200)]

    # Golden Star entries
    for short_n, long_n in pairs:
        sid = f"golden_star_st_{short_n}_{long_n}" if long_n < 200 else f"golden_star_lt_{short_n}_{long_n}"
        _s = short_n
        _l = long_n

        def _gs_fn(df: pd.DataFrame, s=_s, l=_l, **kw) -> pd.Series:
            return golden_star_signal(df, short_n=s, long_n=l)

        _gs_fn.__name__ = sid  # type: ignore[attr-defined]

        out[sid] = {
            "fn": _gs_fn,
            "kind": "event",
            "family": "tech_stars",
            "direction": +1,
            "default_params": {
                "short_n": short_n,
                "long_n": long_n,
                "price_gate_pct": PRICE_GATE_PCT,
                "trend_k": TREND_K,
                "adv_floor": ADV_FLOOR_USD,
                "confirm_days": CONFIRM_DAYS,
            },
            "display": {
                "en": f"Golden Star ({short_n}/{long_n}) — three-entity cross with price gate",
                "zh": f"黄金之星 ({short_n}/{long_n}) — 含价格接近门控的三实体交叉",
            },
            "glyph": "star_gold",
        }

    # Death Star entries
    for short_n, long_n in pairs:
        sid = f"death_star_st_{short_n}_{long_n}" if long_n < 200 else f"death_star_lt_{short_n}_{long_n}"
        _s = short_n
        _l = long_n

        def _ds_fn(df: pd.DataFrame, s=_s, l=_l, **kw) -> pd.Series:
            return death_star_signal(df, short_n=s, long_n=l)

        _ds_fn.__name__ = sid  # type: ignore[attr-defined]

        out[sid] = {
            "fn": _ds_fn,
            "kind": "event",
            "family": "tech_stars",
            "direction": -1,
            "default_params": {
                "short_n": short_n,
                "long_n": long_n,
                "price_gate_pct": PRICE_GATE_PCT,
                "trend_k": TREND_K,
                "adv_floor": ADV_FLOOR_USD,
                "confirm_days": CONFIRM_DAYS,
            },
            "display": {
                "en": f"Death Star ({short_n}/{long_n}) — bearish three-entity cross with price gate",
                "zh": f"死亡之星 ({short_n}/{long_n}) — 含价格接近门控的看跌三实体交叉",
            },
            "glyph": "star_red",
        }

    # new_golden_star: Golden Star fire whose age <= 1 trading day (freshly fired).
    # A "fresh" fire means: the golden_star_st_7_35 signal fires on bar t, and
    # we are now on bar t or t+1 (age = 0 or 1 trading day).
    # Implementation: convolve the golden_star_st_7_35 signal forward by 1 bar so that
    # either the fire bar (t) or the immediately following bar (t+1) is flagged.
    # Semantics: 1.0 on bar t (the fire itself) or bar t+1 (one day old).
    def _new_golden_star_fn(df: pd.DataFrame, **kw) -> pd.Series:
        """Freshly-fired Golden Star: fire bar OR the bar immediately after (age <= 1 day)."""
        base = golden_star_signal(df, short_n=7, long_n=35)
        # bar t: base == 1.0; bar t+1: base.shift(1) == 1.0
        fresh = ((base == 1.0) | (base.shift(1, fill_value=0.0) == 1.0)).astype(float)
        fresh.name = "new_golden_star"
        return fresh

    out["new_golden_star"] = {
        "fn": _new_golden_star_fn,
        "kind": "event",
        "family": "tech_stars",
        "direction": +1,
        "default_params": {"short_n": 7, "long_n": 35, "max_age_days": 1},
        "display": {
            "en": "New Golden Star — freshly fired Golden Star (7/35), age ≤ 1 trading day",
            "zh": "新黄金之星 — 最新触发的黄金之星 (7/35)，触发不超过1个交易日",
        },
        "glyph": "star_gold",
    }

    return out


# ---------------------------------------------------------------------------
# Aggregate TECH_SIGNALS
# ---------------------------------------------------------------------------

def _build_catalog() -> dict[str, dict[str, Any]]:
    """Assemble and return the full TECH_SIGNALS dict."""
    catalog: dict[str, dict[str, Any]] = {}
    missing_modules: list[str] = []

    # Legacy source modules (pre-integration)
    legacy_modules = [
        ("engine.ma_crosses",          "ma_crosses"),
        ("engine.pivots",              "pivots"),
        ("engine.rsi_signals",         "rsi_signals"),
        ("engine.formations",          "formations"),
        ("engine.trend_signals",       "trend_signals"),
        ("engine.fundamental_screens", "fundamental_screens"),
        ("engine.insider_power_signals", "insider_power_signals"),
        # Chart-grammar families (ichimoku / trend_ribbon / rsi_stack / bollinger_events)
        ("engine.ichimoku_signals",        "ichimoku_signals"),
        ("engine.trend_ribbon_signals",    "trend_ribbon_signals"),
        ("engine.rsi_stack_signals",       "rsi_stack_signals"),
        ("engine.bollinger_event_signals", "bollinger_event_signals"),
        # Momentum cross events (macd_events / rsi_events / stoch_events / stoch_events_2w)
        ("engine.momentum_events",         "momentum_events"),
    ]

    # New Technical Lab modules (D04: indicators_m2 uses full descriptors in-module — no backfill)
    lab_modules = [
        ("engine.trend_strength_signals",    "trend_strength_signals"),
        ("engine.compression_signals",       "compression_signals"),
        ("engine.volume_flow_signals",       "volume_flow_signals"),
        ("engine.adaptive_trend_signals",    "adaptive_trend_signals"),
        ("engine.rank_momentum_signals",     "rank_momentum_signals"),
        ("engine.path_risk_signals",         "path_risk_signals"),
        ("engine.momentum_context_signals",  "momentum_context_signals"),
        ("engine.bar_structure_signals",     "bar_structure_signals"),
        ("engine.fractal_pivot_signals",     "fractal_pivot_signals"),
        ("engine.challenger_signals",        "challenger_signals"),
        # Indicators M2: VWAP / Anchored VWAP / Volume Profile (D04)
        ("engine.indicators_m2",             "indicators_m2"),
    ]

    source_modules = legacy_modules + lab_modules
    legacy_labels = {label for _, label in legacy_modules}

    for module_path, label in source_modules:
        sigs = _safe_import_signals(module_path, label)
        if not sigs:
            missing_modules.append(label)
        is_legacy = label in legacy_labels
        for sid, descriptor in sigs.items():
            if sid in catalog:
                log.error(
                    "tech_catalog: DUPLICATE signal id '%s' from %s (first seen from a prior module)",
                    sid, module_path,
                )
                raise ValueError(f"Duplicate signal id in tech catalog: '{sid}' from {module_path}")
            if is_legacy:
                _apply_legacy_meta(sid, descriptor)
            catalog[sid] = descriptor

    # tech_stars built separately (also legacy — apply meta backfill)
    star_sigs = _build_tech_stars_signals()
    if not star_sigs:
        missing_modules.append("tech_stars")
    for sid, descriptor in star_sigs.items():
        if sid in catalog:
            log.error("tech_catalog: DUPLICATE signal id '%s' from tech_stars", sid)
            raise ValueError(f"Duplicate signal id in tech catalog: '{sid}' from tech_stars")
        _apply_legacy_meta(sid, descriptor)
        catalog[sid] = descriptor

    if missing_modules:
        log.warning(
            "tech_catalog: the following source modules could not be loaded and their "
            "signals are absent from the catalog: %s",
            missing_modules,
        )

    # ---------------------------------------------------------------------------
    # Validation loop — enforce _REQUIRED_KEYS on every entry
    # ---------------------------------------------------------------------------
    offenders: list[str] = []
    for sid, descriptor in catalog.items():
        missing_keys = _REQUIRED_KEYS - set(descriptor.keys())
        if missing_keys:
            offenders.append(f"'{sid}': missing {sorted(missing_keys)}")
    if offenders:
        raise ValueError(
            "tech_catalog: the following signals are missing required descriptor keys:\n"
            + "\n".join(offenders)
        )

    return catalog


# Module-level catalog — built once at import time.
TECH_SIGNALS: dict[str, dict[str, Any]] = _build_catalog()

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_signals(family: str | None = None) -> list[dict[str, Any]]:
    """Return a list of signal descriptors, optionally filtered by family.

    Parameters
    ----------
    family : str, optional
        If given, return only descriptors whose 'family' key equals this string.
        Pass None (default) to return all registered signals.

    Returns
    -------
    list of descriptor dicts, each including the signal_id under key 'signal_id'.
    """
    result = []
    for sid, desc in TECH_SIGNALS.items():
        if family is not None and desc.get("family") != family:
            continue
        entry = dict(desc)
        entry["signal_id"] = sid
        result.append(entry)
    return result


def get_signal(signal_id: str) -> dict[str, Any]:
    """Return the descriptor for a single signal by its ID.

    Parameters
    ----------
    signal_id : str
        The signal identifier (e.g. 'golden_cross_7_35', 'rsi14_oversold').

    Returns
    -------
    dict with the signal descriptor (includes 'signal_id' key).

    Raises
    ------
    KeyError
        If signal_id is not registered in the catalog.
    """
    if signal_id not in TECH_SIGNALS:
        raise KeyError(f"Signal '{signal_id}' not found in TECH_SIGNALS. "
                       f"Call signal_families() to see available families, "
                       f"or list_signals() to see all registered IDs.")
    entry = dict(TECH_SIGNALS[signal_id])
    entry["signal_id"] = signal_id
    return entry


def signal_families() -> list[str]:
    """Return the sorted list of unique signal family names in the catalog."""
    return sorted({desc["family"] for desc in TECH_SIGNALS.values()})


def is_screener_firing(descriptor: dict[str, Any]) -> bool:
    """Whether a signal belongs in the screener's "who's firing now" lists.

    A firing screen answers "which tickers is this signal flagging *right now*".
    That only makes sense for DISCRETE fire signals whose latest-bar value is a
    genuine 0/1 flag firing for a subset of the universe:

      - events            — MA crosses, pivots, formations, stars, runners
      - directional states — trend up/down, RSI zones, undervalued/overvalued,
                             insider_buy / insider_sell (0/1 per bar, direction ≠ 0)

    RAW-SCORE / continuous state signals are non-zero for ~the entire universe,
    so a firing list over them lists every ticker — not a meaningful screen:

      - insider_power_state (0–100), valuation_pctile (0–1), return_1d (raw return)

    These are excluded from the firing screen here; they remain available in the
    per-stock profile and as rank keys.

    Control:
        A descriptor may set ``screener_firing: bool`` to override the default.
        This is required for ``valuation_pctile`` (a 0–1 raw score whose
        direction is +1, so the kind/direction inference alone would wrongly
        include it). When the flag is absent, events and direction≠0 states are
        firing-eligible; direction-0 states are not.

    Parameters
    ----------
    descriptor : dict
        A signal descriptor (from TECH_SIGNALS / list_signals() / get_signal()).

    Returns
    -------
    bool
    """
    flag = descriptor.get("screener_firing")
    if flag is not None:
        return bool(flag)
    kind = descriptor.get("kind", "event")
    direction = int(descriptor.get("direction", 0) or 0)
    return kind == "event" or direction != 0


def compute(signal_id: str, df: pd.DataFrame, **overrides: Any) -> pd.Series:
    """Dispatch computation for a registered signal.

    Calls the signal's registered ``fn`` with ``df`` and the signal's
    ``default_params`` updated by any ``**overrides`` provided by the caller.

    Parameters
    ----------
    signal_id : str
        The signal identifier.
    df : pd.DataFrame
        Single-ticker OHLCV DataFrame with at minimum a 'close' column and
        a DatetimeIndex.
    **overrides : Any
        Optional parameter overrides that take precedence over default_params.

    Returns
    -------
    pd.Series
        The computed signal series aligned to df.index.

    Raises
    ------
    KeyError
        If signal_id is not in the catalog.
    TypeError, ValueError
        If the signal's fn raises for the given df / params.
    """
    descriptor = get_signal(signal_id)
    fn = descriptor["fn"]
    params = dict(descriptor.get("default_params") or {})
    params.update(overrides)
    return fn(df, **params)
