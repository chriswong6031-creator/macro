"""International stock-selection engine: pooled cross-market standouts + the
sector-rotation board for "What to act on now".

Residual alpha (engine.residual_alpha) is computed STRICTLY WITHIN each market —
sector-neutral residual momentum vs that market's own index, never pooled across
currencies — then the per-name reads are unioned and tagged with a country flag,
so the Stock dashboard can surface standouts from the whole international set on a
comparable "standout within its own market" basis (honest framing — same as the
HK board: a relative-strength lens, not a forward-edge claim).

The sector board ranks region×GICS-sector equal-weight baskets built from the
pooled universe constituents (so it works for every market incl. Korea/Taiwan,
where listed sector ETFs are too thin) — each row flagged by market.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.indicators import basket_index
from engine.residual_alpha import compute_residual_alpha
from lib import config, store

log = logging.getLogger(__name__)


def panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(closes [date x ticker], members [ticker -> name/sector/country/flag/market/weight])."""
    dd = config.data_dir() / "intl_search"
    cp, mp = dd / "closes.parquet", dd / "members.parquet"
    if not (cp.exists() and mp.exists()):
        return pd.DataFrame(), pd.DataFrame()
    closes = pd.read_parquet(cp).sort_index()
    closes = closes.loc[:, ~closes.columns.duplicated()]
    members = pd.read_parquet(mp)
    return closes, members


def _index_returns(cc: str) -> pd.Series | None:
    idx = config.load()["intl"]["countries"][cc]["index"]
    df = store.read("intl", idx)
    return df["close"].pct_change(fill_method=None) if (df is not None and "close" in df.columns) else None


def compute_intl_alpha(closes: pd.DataFrame | None = None,
                       members: pd.DataFrame | None = None) -> dict | None:
    """Per-market sector-neutral residual momentum, pooled. Returns
    {per_ticker, markets, n} or None. per_ticker[t] carries the alpha record plus
    flag/market/country for the pooled standouts board."""
    if closes is None or members is None:
        closes, members = panel()
    if closes.empty or members.empty:
        return None

    per_ticker: dict[str, dict] = {}
    markets: dict[str, dict] = {}
    for cc in members["country"].unique():
        sub_t = [t for t in members.index[members["country"] == cc] if t in closes.columns]
        if len(sub_t) < 20:
            continue
        sub = closes[sub_t]
        market = _index_returns(cc)
        if market is None:
            continue
        tkr_sector = {t: str(members.loc[t, "sector"]) for t in sub_t}
        try:
            alpha = compute_residual_alpha(sub, market, tkr_sector, min_names=20)
        except Exception as e:  # noqa: BLE001 — one market down can't kill the board
            log.warning("intl alpha %s failed: %s", cc, e)
            continue
        if not alpha:
            continue
        flag = config.load()["intl"]["countries"][cc]["flag"]
        pt = alpha.get("per_ticker", {})
        for t, rec in pt.items():
            rec = dict(rec)
            rec["flag"] = str(members.loc[t, "flag"]) if t in members.index else flag
            rec["market"] = str(members.loc[t, "market"]) if t in members.index else cc
            rec["country"] = cc
            per_ticker[t] = rec
        markets[cc] = {"flag": flag, "n": alpha.get("n"),
                       "market": config.load()["intl"]["countries"][cc]["name"]}
    if not per_ticker:
        return None
    return {"per_ticker": per_ticker, "markets": markets, "n": len(per_ticker)}


def sector_board() -> list[dict]:
    """'What to act on now' — region×GICS-sector relative-strength rotation board,
    built from equal-weight baskets of the pooled universe. Each row is flagged by
    market so the user knows where the sector is (the buyable analogue is a country/
    regional sector ETF). Ranked by 3-month momentum; display-only RS, not an edge."""
    closes, members = panel()
    if closes.empty or members.empty:
        return []
    rscfg = config.load()["intl"]["engine"]["rs_ranking"]
    m20, m60 = rscfg["momentum_windows"]
    trend_w = rscfg["trend_window"]
    flags = {cc: c["flag"] for cc, c in config.load()["intl"]["countries"].items()}
    names = {cc: c["name"] for cc, c in config.load()["intl"]["countries"].items()}

    rows = []
    for (cc, sector), grp in members.groupby(["country", "sector"]):
        tickers = [t for t in grp.index if t in closes.columns]
        if len(tickers) < 3 or str(sector) in ("—", "nan", "Cash and/or Derivatives"):
            continue
        bi = basket_index(closes, tickers).dropna()
        if len(bi) < trend_w:
            continue
        mom20 = float(bi.pct_change(m20).iloc[-1] * 100)
        mom60 = float(bi.pct_change(m60).iloc[-1] * 100)
        ma = float(bi.rolling(trend_w).mean().iloc[-1])
        rows.append({
            "cc": cc, "flag": flags.get(cc, "🌍"), "market": names.get(cc, cc),
            "sector": str(sector), "n": len(tickers),
            "mom_20d": round(mom20, 1), "mom_60d": round(mom60, 1),
            "above_trend": bool(float(bi.iloc[-1]) > ma),
        })
    rows.sort(key=lambda r: r["mom_60d"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows
