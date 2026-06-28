"""S&P 500 sector treemap heatmap — pure compute layer.

Builds the data contract consumed by ``site/sector_heatmap.html`` (a Finviz /
Perplexity-style treemap): every S&P 500 constituent as a tile, grouped
Sector -> Sub-industry -> stock, sized by market cap and coloured by percent
change over a selectable timeframe.

Design notes
------------
* This module is **pure** — it takes already-loaded pandas objects / dicts and
  returns a JSON-serialisable dict. All disk + network I/O (parquet, Polygon)
  lives in ``scripts/build_sp500_heatmap.py`` so the maths stays unit-testable
  and offline-safe.
* Timeframe returns are derived from the daily close matrix
  (``data/breadth/_closes_cache.parquet``) for the daily group
  (1D/1W/MTD/1M/3M/6M/YTD/1Y) — fully computable with no live feed. Intraday
  groups (5m..4H) and the after-hours session are wired through the same
  contract but populated only when the corresponding data exists, so the UI
  toggles light up automatically the day a live/minute feed lands.
* Box size = market cap when real caps are supplied (Polygon reference in CI),
  otherwise a deterministic offline proxy from the SPDR sector-ETF weights
  scaled by the canonical S&P 500 sector weights — so the treemap always
  renders sensibly even with zero network access.
"""
from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd

# --- timeframe catalogue (shared contract: engine, builder, frontend, tests) --
# group: 'daily' computable from the close matrix today; 'intraday'/'session'
# populated only when intraday/after-hours data is present.
# A timeframe toggle only "lights up" once this fraction of constituents carry a
# value for it — so a half-populated intraday window (the hourly cache covers
# ~150 of 503 names) stays greyed until a broad live/minute feed lands, instead
# of rendering a mostly-grey map.
MIN_COVERAGE = 0.5

TIMEFRAMES: list[dict] = [
    {"key": "5M",  "en": "5 min",         "zh": "5分钟",   "group": "intraday"},
    {"key": "10M", "en": "10 min",        "zh": "10分钟",  "group": "intraday"},
    {"key": "15M", "en": "15 min",        "zh": "15分钟",  "group": "intraday"},
    {"key": "30M", "en": "30 min",        "zh": "30分钟",  "group": "intraday"},
    {"key": "1H",  "en": "1 hour",        "zh": "1小时",   "group": "intraday"},
    {"key": "2H",  "en": "2 hour",        "zh": "2小时",   "group": "intraday"},
    {"key": "4H",  "en": "4 hour",        "zh": "4小时",   "group": "intraday"},
    {"key": "AH",  "en": "After-hours",   "zh": "盘后",    "group": "session"},
    {"key": "1D",  "en": "1 day",         "zh": "1天",     "group": "daily"},
    {"key": "1W",  "en": "1 week",        "zh": "1周",     "group": "daily"},
    {"key": "MTD", "en": "Month to date", "zh": "本月至今", "group": "daily"},
    {"key": "1M",  "en": "1 month",       "zh": "1月",     "group": "daily"},
    {"key": "3M",  "en": "3 month",       "zh": "3月",     "group": "daily"},
    {"key": "6M",  "en": "6 month",       "zh": "6月",     "group": "daily"},
    {"key": "YTD", "en": "Year to date",  "zh": "年初至今", "group": "daily"},
    {"key": "1Y",  "en": "1 year",        "zh": "1年",     "group": "daily"},
]
DEFAULT_TIMEFRAME = "1D"

# Calendar lookbacks for the rolling daily windows (anchor = latest close date).
_DATE_OFFSETS: dict[str, pd.DateOffset] = {
    "1W": pd.DateOffset(weeks=1),
    "1M": pd.DateOffset(months=1),
    "3M": pd.DateOffset(months=3),
    "6M": pd.DateOffset(months=6),
    "1Y": pd.DateOffset(years=1),
}

# Sector -> Chinese labels (the index-level groups; sub-industry labels stay
# English, as is conventional for granular industry strings). Both the Finviz
# sector vocabulary (used by the heatmap when an industry map is supplied) and
# the legacy GICS names are covered so either classification renders bilingually.
SECTOR_ZH: dict[str, str] = {
    # Finviz sector vocabulary (primary)
    "Technology": "信息技术",
    "Communication Services": "通信服务",
    "Healthcare": "医疗保健",
    "Financial": "金融",
    "Consumer Cyclical": "非必需消费",
    "Consumer Defensive": "必需消费",
    "Industrials": "工业",
    "Energy": "能源",
    "Utilities": "公用事业",
    "Real Estate": "房地产",
    "Basic Materials": "材料",
    # Legacy GICS names (fallback when no industry map)
    "Information Technology": "信息技术",
    "Financials": "金融",
    "Health Care": "医疗保健",
    "Consumer Discretionary": "非必需消费",
    "Consumer Staples": "必需消费",
    "Materials": "材料",
}

# Canonical-ish S&P 500 sector weights (%) — FALLBACK ONLY, used to scale the
# offline market-cap proxy across sectors so Tech's block dwarfs Utilities like
# it should. Superseded entirely whenever real caps are supplied.
_SECTOR_INDEX_WEIGHT: dict[str, float] = {
    # Finviz sector vocabulary (primary)
    "Technology": 30.0,
    "Financial": 14.0,
    "Healthcare": 10.0,
    "Consumer Cyclical": 10.5,
    "Communication Services": 9.5,
    "Industrials": 9.0,
    "Consumer Defensive": 5.5,
    "Energy": 3.2,
    "Utilities": 2.5,
    "Real Estate": 2.2,
    "Basic Materials": 1.9,
    # Legacy GICS names (fallback)
    "Information Technology": 32.0,
    "Financials": 13.5,
    "Health Care": 10.0,
    "Consumer Discretionary": 10.0,
    "Consumer Staples": 5.5,
    "Materials": 1.9,
}


def _pct(now: float, ref: float) -> float | None:
    if ref is None or now is None or ref == 0 or not np.isfinite(ref) or not np.isfinite(now):
        return None
    return round((now / ref - 1.0) * 100.0, 2)


def _ref_close_on_or_before(col: pd.Series, target: pd.Timestamp) -> float | None:
    """Last non-null close at or before ``target`` (holiday/weekend safe)."""
    s = col.loc[:target].dropna()
    if s.empty:
        return None
    return float(s.iloc[-1])


def daily_returns(closes: pd.DataFrame, asof: pd.Timestamp | None = None) -> dict[str, dict[str, float]]:
    """Percent change per ticker for every *daily-group* timeframe.

    Parameters
    ----------
    closes : index = Date (ascending), columns = ticker, values = adjusted close.
    asof   : anchor date (defaults to the last index date).

    Returns ``{ticker: {"1D": pct, "1W": pct, ...}}``; a timeframe key is omitted
    when there is not enough history to compute it.
    """
    if closes is None or closes.empty:
        return {}
    closes = closes.sort_index()
    closes.index = pd.to_datetime(closes.index)
    if asof is None:
        asof = closes.index[-1]
    asof = pd.Timestamp(asof)

    # Prior-period anchors for MTD / YTD.
    month_start = asof.normalize().replace(day=1)
    prev_month_end = month_start - pd.Timedelta(days=1)
    prev_year_end = pd.Timestamp(year=asof.year, month=1, day=1) - pd.Timedelta(days=1)

    out: dict[str, dict[str, float]] = {}
    for tkr in closes.columns:
        col = closes[tkr].dropna()
        if col.empty:
            continue
        now = float(col.iloc[-1])
        perf: dict[str, float] = {}

        # 1D = latest vs previous available session.
        if len(col) >= 2:
            v = _pct(now, float(col.iloc[-2]))
            if v is not None:
                perf["1D"] = v

        for key, off in _DATE_OFFSETS.items():
            v = _pct(now, _ref_close_on_or_before(col, asof - off))
            if v is not None:
                perf[key] = v

        v = _pct(now, _ref_close_on_or_before(col, prev_month_end))
        if v is not None:
            perf["MTD"] = v
        v = _pct(now, _ref_close_on_or_before(col, prev_year_end))
        if v is not None:
            perf["YTD"] = v

        if perf:
            out[tkr] = perf
    return out


def intraday_returns(bars: Mapping[str, pd.DataFrame]) -> dict[str, dict[str, float]]:
    """Percent change over the last 1H/2H/4H from per-ticker hourly bars.

    ``bars`` maps ticker -> DataFrame with a ``close`` column ordered ascending
    (e.g. ``data/intraday/<T>.parquet``). Sub-hourly windows require minute bars
    and are intentionally not derived here (they stay null until a finer feed
    exists). Empty / missing input simply yields no keys for that ticker.
    """
    out: dict[str, dict[str, float]] = {}
    steps = {"1H": 1, "2H": 2, "4H": 4}
    for tkr, df in (bars or {}).items():
        if df is None or "close" not in getattr(df, "columns", []):
            continue
        c = df["close"].dropna()
        if len(c) < 2:
            continue
        now = float(c.iloc[-1])
        perf: dict[str, float] = {}
        for key, n in steps.items():
            if len(c) > n:
                v = _pct(now, float(c.iloc[-(n + 1)]))
                if v is not None:
                    perf[key] = v
        if perf:
            out[tkr] = perf
    return out


def _proxy_sizes(
    rows: Sequence[dict],
    weights_in_sector: Mapping[str, float] | None,
) -> dict[str, float]:
    """Offline market-cap proxy: SPDR within-sector weight scaled by the
    canonical S&P 500 sector weight, so areas are comparable across sectors.
    Tickers absent from the ETF holdings get a small per-sector floor."""
    weights_in_sector = weights_in_sector or {}
    by_sector: dict[str, list[dict]] = {}
    for r in rows:
        by_sector.setdefault(r["sector"], []).append(r)

    sizes: dict[str, float] = {}
    for sector, members in by_sector.items():
        sector_w = _SECTOR_INDEX_WEIGHT.get(sector, 2.0)
        raw: dict[str, float] = {}
        present = [weights_in_sector[m["t"]] for m in members if m["t"] in weights_in_sector]
        floor = (min(present) * 0.4) if present else 1.0
        for m in members:
            raw[m["t"]] = float(weights_in_sector.get(m["t"], floor))
        total = sum(raw.values()) or 1.0
        for t, w in raw.items():
            sizes[t] = sector_w * (w / total)
    return sizes


def build_heatmap(
    constituents: pd.DataFrame,
    closes: pd.DataFrame,
    *,
    industry_map: Mapping[str, Mapping[str, str]] | None = None,
    caps: Mapping[str, float] | None = None,
    weights_in_sector: Mapping[str, float] | None = None,
    intraday_bars: Mapping[str, pd.DataFrame] | None = None,
    live: Mapping[str, Mapping] | None = None,
    generated_utc: str | None = None,
    asof: pd.Timestamp | None = None,
) -> dict:
    """Assemble the full heatmap payload.

    Parameters
    ----------
    constituents : index = symbol, columns include ['name', 'sector'].
    closes       : daily close matrix (Date index, ticker columns).
    industry_map : ticker -> {'sub_industry': str, ...} (optional; falls back to
                   the GICS sector as the sub-group when missing).
    caps         : ticker -> market cap (real). When None an offline proxy sizes
                   the tiles from ``weights_in_sector`` + canonical sector weights.
    live         : ticker -> {'price','prev_close','price_basis','after_hours'?}
                   from a fresh snapshot; when present it overrides/fills 1D (and
                   'AH' if an after-hours print is available).
    """
    if constituents is None or constituents.empty:
        return _empty_payload(generated_utc)

    perf = daily_returns(closes, asof=asof)
    intr = intraday_returns(intraday_bars or {})

    closes_sorted = closes.sort_index() if closes is not None and not closes.empty else closes
    asof_date = ""
    if closes_sorted is not None and not closes_sorted.empty:
        asof_date = pd.Timestamp(asof or closes_sorted.index[-1]).strftime("%Y-%m-%d")

    rows: list[dict] = []
    for sym, row in constituents.iterrows():
        sector = str(row.get("sector") or "").strip()
        sub = sector
        # An industry map supplies the Finviz sector + sub-industry (subsector).
        # The Finviz sector overrides the GICS sector so the treemap groups the
        # way the reference heatmaps do (e.g. V/MA land in Financial, not Tech).
        fin = industry_map.get(sym) if industry_map else None
        if fin:
            sector = str(fin.get("sector") or sector).strip() or sector
            sub = str(fin.get("sub_industry") or fin.get("industry") or sector).strip() or sector
        if not sector:
            continue
        rows.append({
            "t": sym,
            "name": str(row.get("name") or sym),
            "sector": sector,
            "industry": sub,
        })

    # Sizes (real caps win; else deterministic proxy).
    if caps:
        sizes = {r["t"]: float(caps.get(r["t"], 0.0)) for r in rows}
        if not any(v > 0 for v in sizes.values()):
            sizes = _proxy_sizes(rows, weights_in_sector)
        else:
            # Floor any missing/zero caps so every constituent still draws.
            pos = [v for v in sizes.values() if v > 0]
            floor = (min(pos) * 0.5) if pos else 1.0
            sizes = {t: (v if v > 0 else floor) for t, v in sizes.items()}
    else:
        sizes = _proxy_sizes(rows, weights_in_sector)

    tiles: list[dict] = []
    for r in rows:
        sym = r["t"]
        p = dict(perf.get(sym, {}))
        if sym in intr:
            p.update(intr[sym])
        # Live snapshot splice: fresher 1D + after-hours when available.
        if live and sym in live:
            q = live[sym]
            price, prev = q.get("price"), q.get("prev_close")
            if price and prev:
                v = _pct(float(price), float(prev))
                if v is not None:
                    p["1D"] = v
            ah = q.get("after_hours")
            if ah and price:
                v = _pct(float(ah), float(price))
                if v is not None:
                    p["AH"] = v
        if not p and sizes.get(sym, 0) <= 0:
            continue
        tiles.append({
            "t": sym,
            "name": r["name"],
            "sector": r["sector"],
            "industry": r["industry"],
            "size": round(float(sizes.get(sym, 0.0)), 6),
            "perf": p,
        })

    # A timeframe is enabled only when enough constituents carry it (avoids a
    # mostly-grey map from a thinly-covered intraday window).
    n = len(tiles) or 1
    counts: dict[str, int] = {}
    for tile in tiles:
        for k in tile["perf"]:
            counts[k] = counts.get(k, 0) + 1
    timeframes = [
        {**tf, "available": (counts.get(tf["key"], 0) / n) >= MIN_COVERAGE}
        for tf in TIMEFRAMES
    ]

    sectors_present = []
    seen = set()
    for r in rows:
        if r["sector"] not in seen:
            seen.add(r["sector"])
            sectors_present.append({
                "key": r["sector"],
                "en": r["sector"],
                "zh": SECTOR_ZH.get(r["sector"], r["sector"]),
            })

    source = "polygon-live" if live else "daily-close"
    return {
        "asof": asof_date,
        "generated_utc": generated_utc or "",
        "source": source,
        "delay_min": 15,
        "currency": "USD",
        "default_tf": DEFAULT_TIMEFRAME,
        "timeframes": timeframes,
        "sectors": sectors_present,
        "tiles": tiles,
        "n_tiles": len(tiles),
    }


def _empty_payload(generated_utc: str | None) -> dict:
    return {
        "asof": "",
        "generated_utc": generated_utc or "",
        "source": "daily-close",
        "delay_min": 15,
        "currency": "USD",
        "default_tf": DEFAULT_TIMEFRAME,
        "timeframes": [{**tf, "available": False} for tf in TIMEFRAMES],
        "sectors": [],
        "tiles": [],
        "n_tiles": 0,
    }
