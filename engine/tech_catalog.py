"""engine/tech_catalog.py — AI-friendly registry of every technical signal in the suite.

Single source of truth: read this file to see all available technical signals, their
families, parameters, and how to compute them on an OHLCV DataFrame.

AGGREGATION SOURCES
-------------------
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
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Required descriptor keys — enforced by the catalog loader
# ---------------------------------------------------------------------------
_REQUIRED_KEYS: frozenset[str] = frozenset({"fn", "kind", "family", "direction", "default_params", "display", "glyph"})

# Optional descriptor keys (not enforced):
#   screener_firing : bool
#       Whether this signal belongs in the screener's "who's firing now" lists
#       (see is_screener_firing() below). Absent → inferred from kind/direction.

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

    source_modules = [
        ("engine.ma_crosses",          "ma_crosses"),
        ("engine.pivots",              "pivots"),
        ("engine.rsi_signals",         "rsi_signals"),
        ("engine.formations",          "formations"),
        ("engine.trend_signals",       "trend_signals"),
        ("engine.fundamental_screens", "fundamental_screens"),
        ("engine.insider_power_signals", "insider_power_signals"),
        # Chart-grammar families — DT-R18
        ("engine.ichimoku_signals",        "ichimoku_signals"),
        ("engine.trend_ribbon_signals",    "trend_ribbon_signals"),
        ("engine.rsi_stack_signals",       "rsi_stack_signals"),
        ("engine.bollinger_event_signals", "bollinger_event_signals"),
    ]

    for module_path, label in source_modules:
        sigs = _safe_import_signals(module_path, label)
        if not sigs:
            missing_modules.append(label)
        for sid, descriptor in sigs.items():
            if sid in catalog:
                log.error(
                    "tech_catalog: DUPLICATE signal id '%s' from %s (first seen from a prior module)",
                    sid, module_path,
                )
                raise ValueError(f"Duplicate signal id in tech catalog: '{sid}' from {module_path}")
            catalog[sid] = descriptor

    # tech_stars built separately
    star_sigs = _build_tech_stars_signals()
    if not star_sigs:
        missing_modules.append("tech_stars")
    for sid, descriptor in star_sigs.items():
        if sid in catalog:
            log.error("tech_catalog: DUPLICATE signal id '%s' from tech_stars", sid)
            raise ValueError(f"Duplicate signal id in tech catalog: '{sid}' from tech_stars")
        catalog[sid] = descriptor

    if missing_modules:
        log.warning(
            "tech_catalog: the following source modules could not be loaded and their "
            "signals are absent from the catalog: %s",
            missing_modules,
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
