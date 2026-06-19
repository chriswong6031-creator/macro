"""International (developed ex-US + India) thematic baskets — the cross-country analogue of
engine.baskets_china / _hk / _canada.

Equal-weight, point-in-time dated-membership trackers over the FREE intl_search cache (~1000
developed-ex-US + India large-caps across JP/GB/EU/IN/KR/TW/AU, ~5y). The baskets are GLOBAL
sector themes that deliberately mix equities across countries (Global Semiconductors, Global
Banks, Defense & Aerospace…) plus a few single-country structural sleeves. Delegates the
equal-weight / level / return / perf math to engine.baskets_region so the page is computed
identically to every other market.

THE BENCHMARK is synthetic: there is no single index for a cross-country universe, so we build
a CAP-WEIGHTED COMPOSITE of the universe (weights = the index `weight` column in
intl_search/members.parquet) and persist it as data/intl/_INTLC.parquet — the "Intl ex-US
composite". Both this engine and the Theme Rotation Desk (engine.narrative_rotation._setup,
which reads it via lib.store) share that one series, so relative performance is measured against
the average international large-cap. The static weights make the composite a standard
index-level proxy (a mild historical-weight approximation; the page is explicitly
hindsight-descriptive, not a backtest).

HONEST BY CONSTRUCTION: membership is curated today with knowledge of the period, so the series
is HINDSIGHT-curated and descriptive — not an out-of-sample backtest and not a buy list.
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from engine.baskets_region import compute_region_baskets
from lib import config, store

log = logging.getLogger(__name__)

BENCHMARK_DEFAULT = "_INTLC"     # synthetic cap-weighted Intl ex-US composite
COMPOSITE_GROUP = "intl"         # store group → data/intl/_INTLC.parquet


def _membership() -> dict | None:
    p = config.data_dir() / "baskets_intl" / "membership.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("intl baskets membership unreadable: %s", e)
        return None


def _closes() -> pd.DataFrame | None:
    """Wide [Date × ticker] adjusted closes for the intl_search universe (~1000 names, ~5y)."""
    p = config.data_dir() / "intl_search" / "closes.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.DatetimeIndex(df.index)
        return df.sort_index()
    except Exception as e:  # noqa: BLE001
        log.warning("intl_search closes unreadable: %s", e)
        return None


def _members_meta() -> pd.DataFrame | None:
    p = config.data_dir() / "intl_search" / "members.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("intl_search members unreadable: %s", e)
        return None


def build_composite(closes: pd.DataFrame | None = None,
                    meta: pd.DataFrame | None = None) -> pd.DataFrame | None:
    """Cap-weighted composite LEVEL of the universe → a frame with a single 'close' column.

    Weights are the index `weight` column (current cap weights), held static and renormalised
    over the names that actually have a return each day (min_count=1 so a missing name doesn't
    zero the basket). Rebased to 100 at the first valid day. This is the benchmark both the
    baskets engine and the Theme Rotation Desk measure relative performance against.
    """
    closes = closes if closes is not None else _closes()
    meta = meta if meta is not None else _members_meta()
    if closes is None or closes.empty or meta is None or "weight" not in meta.columns:
        return None
    rets = closes.pct_change(fill_method=None)
    w = pd.to_numeric(meta["weight"], errors="coerce").reindex(rets.columns).fillna(0.0)
    w = w[w > 0]
    if w.empty:
        return None
    rets = rets[w.index]
    wn = w / w.sum()
    # daily cap-weighted return over the names present that day, renormalised by present weight
    present = rets.notna()
    day_w = present.mul(wn, axis=1)
    denom = day_w.sum(axis=1).replace(0.0, pd.NA)
    port_ret = (rets.mul(wn, axis=1).sum(axis=1, min_count=1)) / denom
    lvl = (1.0 + port_ret.fillna(0.0)).cumprod() * 100.0
    df = pd.DataFrame({"close": lvl.astype(float)})
    df.index.name = "date"
    return df


def refresh_composite() -> bool:
    """Recompute the composite and persist it to data/intl/_INTLC.parquet so the desk path
    (engine.narrative_rotation._setup → lib.store.read) sees the same benchmark. Returns True
    on success. Call this BEFORE compute_theme_intel('intl')."""
    df = build_composite()
    if df is None or df.empty:
        return False
    p = store._path(COMPOSITE_GROUP, BENCHMARK_DEFAULT)
    df.to_parquet(p)
    log.info("intl composite benchmark → %s (%d days, last=%.1f)", p, len(df), float(df["close"].iloc[-1]))
    return True


def build_breadth() -> bool:
    """Compute the international market-breadth tape from the universe closes and persist it to
    data/intl_breadth/breadth.parquet so engine.basket_score.market_concentration('intl') has a
    REAL (not US-fallback) breadth read. Columns: adv/dec, % above 50d/200d MA, 52-wk new
    highs/lows — the same schema as the US/China breadth tapes."""
    closes = _closes()
    if closes is None or closes.empty:
        return False
    rets = closes.pct_change(fill_method=None)
    adv = (rets > 0).sum(axis=1)
    dec = (rets < 0).sum(axis=1)
    n_valid = closes.notna().sum(axis=1).replace(0, pd.NA)
    ma50 = closes.rolling(50, min_periods=25).mean()
    ma200 = closes.rolling(200, min_periods=100).mean()
    pct50 = (closes > ma50).sum(axis=1) / n_valid * 100.0
    pct200 = (closes > ma200).sum(axis=1) / n_valid * 100.0
    hi = closes.rolling(252, min_periods=60).max()
    lo = closes.rolling(252, min_periods=60).min()
    nh = (closes >= hi * (1 - 1e-3)).sum(axis=1)
    nl = (closes <= lo * (1 + 1e-3)).sum(axis=1)
    df = pd.DataFrame({"adv": adv, "dec": dec, "pct_above_50": pct50.round(1),
                       "pct_above_200": pct200.round(1), "nh": nh, "nl": nl}).dropna(subset=["pct_above_50"])
    if df.empty:
        return False
    p = config.data_dir() / "intl_breadth" / "breadth.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)
    log.info("intl breadth tape → %s (%d days)", p, len(df))
    return True


def refresh_inputs() -> bool:
    """Refresh both the composite benchmark and the breadth tape (call before the desk computes)."""
    ok = refresh_composite()
    build_breadth()
    return ok


def compute_intl_baskets() -> dict | None:
    """Load the intl data plane (intl_search closes + the synthetic composite benchmark) and
    delegate the equal-weight/perf compute to engine.baskets_region. International members carry
    English display names; there is no per-theme sector-ETF cross-check (proxy_reader → None)."""
    mem = _membership()
    if not mem or not mem.get("baskets"):
        return None
    closes = _closes()
    bench = build_composite(closes)
    if bench is None:
        return None
    return compute_region_baskets(closes, mem, bench, lambda s: None, name_key="name")
