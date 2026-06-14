"""Thematic baskets — equal-weight, dated-membership trackers over the FREE cache.

A direct replication of FactorWatch's "Baskets": curated thematic stock baskets,
EQUAL-WEIGHTED with point-in-time dated membership (a member counts only between
its added and removed dates), buy-and-hold between. We report each basket's return
at 1d/5d/20d/60d/YTD horizons RAW and RELATIVE to SPY, a cumulative spark series, a
Sharpe/MaxDD summary, an optional reference-ETF correlation cross-check, and the
per-member weights.

HONEST BY CONSTRUCTION (house rule): membership.json is curated with knowledge of
the period, so the ~3y series is hindsight-curated and descriptive — NOT an out-of-
sample backtest, NOT a buy list. Equal-weight, one short single-regime window, free
S&P-1500 universe only (members outside it are excluded and counted in n_missing).
No scoring, no recommendations.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from engine.equity_factors import _closes, _names_sectors
from engine.validation import _maxdd, _sharpe
from lib import config, store

log = logging.getLogger(__name__)

HORIZONS = {"d1": 1, "d5": 5, "d20": 20, "d60": 60}
SPARK_POINTS = 90                      # downsample the cumulative series for the sparkline


def _membership() -> dict | None:
    p = config.data_dir() / "baskets" / "membership.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("baskets membership unreadable: %s", e)
        return None


def _hz(r: pd.Series, h: int) -> float | None:
    """Compounded return (%) over the last h observations of a daily-return series."""
    r = r.dropna()
    if len(r) <= h:
        return None
    return round(float(((1.0 + r).tail(h).prod() - 1.0) * 100), 2)


def _ytd(r: pd.Series, anchor: pd.Timestamp) -> float | None:
    seg = r[r.index >= anchor].dropna()
    if seg.empty:
        return None
    return round(float(((1.0 + seg).prod() - 1.0) * 100), 2)


def _spark(cum: pd.Series) -> list:
    cum = cum.dropna()
    if cum.empty:
        return []
    step = max(1, len(cum) // SPARK_POINTS)
    return [round(float(v), 2) for v in cum.iloc[::step]]


def compute_baskets() -> dict | None:
    """Build the baskets payload from membership.json + the price caches + SPY.
    Returns None (page hides) if membership or prices are missing."""
    mem = _membership()
    if not mem or not mem.get("baskets"):
        return None
    closes = _closes()
    if closes is None or closes.empty:
        return None
    rets = closes.pct_change(fill_method=None)
    idx = rets.index
    nm = _names_sectors()

    spy = store.read("yahoo", "SPY")
    spy_ret = None
    if spy is not None and "close" in spy.columns:
        spy_close = spy["close"].reindex(idx).ffill()
        spy_ret = spy_close.pct_change()

    year = idx.max().year
    ytd_anchor = idx[idx >= pd.Timestamp(year, 1, 1)].min()

    spy_hz = {k: _hz(spy_ret, h) for k, h in HORIZONS.items()} if spy_ret is not None else {}
    spy_hz["ytd"] = _ytd(spy_ret, ytd_anchor) if spy_ret is not None else None

    out_baskets = []
    for bid, b in mem["baskets"].items():
        members = b.get("members", [])
        tickers = [m["ticker"] for m in members]
        present = [t for t in tickers if t in rets.columns]
        n_missing = len(set(tickers)) - len(set(present))
        if len(present) < 3:                       # too thin to be a basket
            log.warning("basket %s skipped: only %d members in cache", bid, len(present))
            continue

        # point-in-time equal-weight: a member counts only within [added, removed)
        sub = rets[present]
        mask = pd.DataFrame(False, index=idx, columns=present)
        for m in members:
            t = m["ticker"]
            if t not in mask.columns:
                continue
            a = idx >= pd.Timestamp(m["added"])
            if m.get("removed"):
                a = a & (idx < pd.Timestamp(m["removed"]))
            mask[t] = a
        ew = sub.where(mask).mean(axis=1)          # EW mean of active members per day
        ew_valid = ew.dropna()
        if ew_valid.empty:
            continue

        raw = {k: _hz(ew, h) for k, h in HORIZONS.items()}
        raw["ytd"] = _ytd(ew, ytd_anchor)
        rel = {k: (round(raw[k] - spy_hz.get(k), 2) if raw.get(k) is not None and spy_hz.get(k) is not None else None)
               for k in list(HORIZONS) + ["ytd"]}

        cum = (1.0 + ew.fillna(0.0)).cumprod() - 1.0
        cum = cum[cum.index >= ew_valid.index.min()] * 100
        spark = _spark(cum)
        spy_spark = []
        if spy_ret is not None:
            spy_cum = (1.0 + spy_ret.reindex(cum.index).fillna(0.0)).cumprod() - 1.0
            spy_spark = _spark(spy_cum * 100)

        # reference-ETF correlation (only when a proxy is actually stored)
        etf_corr = None
        proxy = b.get("etf_proxy")
        if proxy:
            pe = store.read("yahoo", proxy)
            if pe is not None and "close" in pe.columns:
                pr = pe["close"].reindex(idx).ffill().pct_change()
                pair = pd.concat([ew, pr], axis=1).dropna()
                if len(pair) > 60:
                    etf_corr = round(float(pair.iloc[:, 0].corr(pair.iloc[:, 1])), 2)

        # latest active members -> weights + per-name YTD
        last = idx.max()
        active = [t for t in present if bool(mask.loc[last, t])]
        w = round(1.0 / len(active), 4) if active else None
        mlist = []
        for t in sorted(active, key=lambda x: nm.get(x, (x, ""))[0]):
            tc = closes[t].dropna()
            seg = tc[tc.index >= ytd_anchor]
            ytd_r = round(float(tc.iloc[-1] / seg.iloc[0] - 1.0) * 100, 1) if len(seg) > 1 else None
            mlist.append({"ticker": t, "name": nm.get(t, (t, "—"))[0][:24],
                          "sector": nm.get(t, (t, "—"))[1], "weight": w, "ytd": ytd_r})

        changelog = sorted(
            [{"date": m["added"], "action": "add", "ticker": m["ticker"], "note": m.get("note", "")}
             for m in members]
            + [{"date": m["removed"], "action": "drop", "ticker": m["ticker"], "note": m.get("note", "")}
               for m in members if m.get("removed")],
            key=lambda x: x["date"])

        out_baskets.append({
            "id": bid, "name": b["name"], "name_zh": b.get("name_zh", b["name"]),
            "theme": b.get("theme", ""), "category": b.get("category", "—"),
            "n": len(active), "n_missing": n_missing, "omitted": b.get("omitted", []),
            "etf_proxy": proxy, "etf_proxy_note": b.get("etf_proxy_note"), "etf_corr": etf_corr,
            "created": b.get("created"), "curated": b.get("curated"),
            "ret": {"raw": raw, "rel": rel},
            "stats": {"sharpe": round(_sharpe(ew_valid, 252), 2),
                      "maxdd_pct": round(_maxdd(ew_valid) * 100, 1),
                      "ann_vol_pct": round(float(np.std(ew_valid)) * np.sqrt(252) * 100, 1),
                      "cum_pct": round(float(cum.iloc[-1]), 1) if not cum.empty else None},
            "spark": spark, "spy_spark": spy_spark,
            "members": mlist, "changelog": changelog,
        })

    if not out_baskets:
        return None
    # default sort: strongest 20-day relative first (the FactorWatch default read)
    out_baskets.sort(key=lambda x: (x["ret"]["rel"].get("d20") is None,
                                    -(x["ret"]["rel"].get("d20") or 0)))
    cats = sorted({b["category"] for b in out_baskets})
    return {
        "as_of": idx.max().strftime("%Y-%m-%d"),
        "seed_date": mem.get("seed_date"), "curated": mem.get("curated"),
        "note": mem.get("note", ""),
        "spx_note": "Relative = basket return minus SPY over the same horizon.",
        "categories": cats, "baskets": out_baskets,
    }
