"""Analyst revision-momentum — the CHANGE in sell-side consensus, not the level.

The literature (Womack 1996; Barber-Lehavy-McNichols-Trueman 2001) and the JPM/SBSW
case study agree: the consensus *level* ("rated Buy") is near-useless and optimism-
skewed, while the *revision* (upgrades/downgrades, especially downgrades) carries the
signal. So we score the DELTA in net-buy consensus, never the level.

Feedstock = the append-only monthly Finnhub recommendation-trends snapshots that
collectors/finnhub_altdata.py already collects (data/finnhub/recommendation.parquet:
ticker, period, strongBuy, buy, hold, sell, strongSell, prev_buy). Pure + import-light;
the `consensus_pct` level is carried only as labelled CONTEXT, never the signal.

Per-individual-analyst accuracy (TipRanks-grade) needs enterprise data we don't have;
firm-level accuracy would need Finnhub Premium's upgrade/downgrade feed (~$50/mo) —
both out of scope here. This is the free revision read, built on the existing key.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config

log = logging.getLogger(__name__)


def load_recommendations() -> pd.DataFrame | None:
    p = config.data_dir() / "finnhub" / "recommendation.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None
    need = {"ticker", "period", "strongBuy", "buy", "hold", "sell", "strongSell"}
    return df if (not df.empty and need <= set(df.columns)) else None


def _net_buy(row) -> float:
    return float(row.get("strongBuy") or 0) + float(row.get("buy") or 0)


def _total(row) -> float:
    return sum(float(row.get(k) or 0)
               for k in ("strongBuy", "buy", "hold", "sell", "strongSell"))


def _weighted(row, total: float) -> float | None:
    """Normalized −2..+2 tilt (strongBuy=+2 … strongSell=−2)."""
    if total <= 0:
        return None
    score = (2 * float(row.get("strongBuy") or 0) + float(row.get("buy") or 0)
             - float(row.get("sell") or 0) - 2 * float(row.get("strongSell") or 0))
    return round(score / total, 3)


def revision_for(rows: pd.DataFrame) -> dict | None:
    """One ticker's revision-momentum read. PURE. Prefers a multi-period delta
    (latest vs prior accumulated snapshot); falls back to the stored `prev_buy`
    one-period delta when only a single snapshot exists."""
    if rows is None or rows.empty:
        return None
    df = rows.sort_values("period")
    last = df.iloc[-1]
    total = _total(last)
    if total <= 0:
        return None
    net_buy = _net_buy(last)

    if len(df) >= 2:
        prev = df.iloc[-2]
        rev_delta = net_buy - _net_buy(prev)
        wprev = _weighted(prev, _total(prev))
        wlast = _weighted(last, total)
        w_delta = (round(wlast - wprev, 3) if wlast is not None and wprev is not None
                   else None)
    else:                                    # single snapshot -> use the stored prior net-buy
        pb = last.get("prev_buy")
        rev_delta = (net_buy - float(pb)) if pb is not None and not pd.isna(pb) else None
        w_delta = None

    if rev_delta is None:
        direction = "stable"
    elif rev_delta > 0:
        direction = "upgrading"
    elif rev_delta < 0:
        direction = "downgrading"
    else:
        direction = "stable"

    return {
        "direction": direction,
        "revision_delta": round(rev_delta, 1) if rev_delta is not None else None,
        "weighted_delta": w_delta,
        "consensus_pct": round(net_buy / total * 100, 1),   # LEVEL — context only
        "n_analysts": int(total),
        "n_periods": int(len(df)),
        "latest_period": str(last["period"]),
        "confidence": "descriptive",          # revision is the signal; accrues over time
    }


def revision_map(recs: pd.DataFrame | None = None) -> dict[str, dict]:
    """{ticker: revision_for(...)} over the recommendation snapshots. Empty when the
    feed is absent (no FINNHUB key yet). PURE given an explicit frame."""
    if recs is None:
        recs = load_recommendations()
    if recs is None or recs.empty:
        return {}
    out: dict[str, dict] = {}
    for tk, rows in recs.groupby("ticker"):
        r = revision_for(rows)
        if r is not None:
            out[str(tk)] = r
    return out
