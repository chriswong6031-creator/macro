"""Generic thematic-baskets compute core shared by every non-US market.

Pure function: given an already-loaded close matrix, a membership dict, a benchmark
close frame and a proxy-ETF reader, it produces the same two payloads the FactorWatch
baskets page renders client-side (CHART level matrix + BASKETS metadata with per-horizon
perf, enriched members, reference cross-check and hygiene flags). All the equal-weight /
level / return / perf math is reused from engine.baskets so every market page is computed
identically; this module just parameterizes the data plane (which close cache, which
benchmark, which member-name field) so China / Hong Kong / Canada are thin wrappers
(engine.baskets_china / _hk / _canada) that load their own data and call in here.

HONEST BY CONSTRUCTION (house rule): membership is curated with knowledge of the period,
so the series is HINDSIGHT-curated and descriptive — not an out-of-sample backtest and not
a buy list.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.baskets import _ew_level, _mtd_anchor, _perf, _trailing_return

log = logging.getLogger(__name__)


def _proxy_returns(proxy, idx: pd.DatetimeIndex, reader) -> pd.Series | None:
    """Daily returns of a reference sector ETF (or an equal blend), via the market's reader."""
    syms = proxy if isinstance(proxy, list) else [proxy]
    legs = []
    for s in syms:
        pe = reader(s)
        if pe is not None and "close" in pe.columns:
            legs.append(pe["close"].reindex(idx).ffill().pct_change())
    if not legs:
        return None
    return pd.concat(legs, axis=1).mean(axis=1)


def compute_region_baskets(closes: pd.DataFrame | None, mem: dict | None,
                           bench_df: pd.DataFrame | None, proxy_reader,
                           name_key: str = "name") -> dict | None:
    """Compute the baskets payload for one market.

    closes       wide [Date x ticker] adjusted-close matrix for the market universe
    mem          membership dict (baskets + benchmark_label{,_zh} + construction/note …)
    bench_df     benchmark close frame (e.g. CSI 300 / HSI / S&P-TSX), needs a 'close' col
    proxy_reader callable(sym_or_list) -> close frame|None for the etf_proxy cross-check
    name_key     which member field to surface as the display name (e.g. 'name_zh', 'name')
    """
    if not mem or not mem.get("baskets"):
        return None
    if closes is None or closes.empty:
        return None
    rets = closes.pct_change(fill_method=None)
    idx = rets.index

    if bench_df is None or "close" not in bench_df.columns:
        return None
    bench_ret = bench_df["close"].reindex(idx).ffill().pct_change()
    bench = pd.Series(np.nan, index=idx)
    bf = bench_ret.first_valid_index()
    bench.loc[bf:] = (1.0 + bench_ret.loc[bf:].fillna(0.0)).cumprod()

    year = idx.max().year
    ytd_anchor = idx[idx < pd.Timestamp(year, 1, 1)].max() if (idx < pd.Timestamp(year, 1, 1)).any() else idx[0]
    mtd_anchor = _mtd_anchor(idx)
    dates = [d.strftime("%Y-%m-%d") for d in idx]

    chart_baskets, out_baskets = {}, []
    for bid, b in mem["baskets"].items():
        members = b.get("members", [])
        tickers = [m["ticker"] for m in members]
        present = [t for t in tickers if t in rets.columns]
        missing = sorted(set(tickers) - set(present))
        if len(present) < 3:
            log.warning("basket %s skipped: only %d members in cache", bid, len(present))
            continue
        lvl = _ew_level(rets, members, idx)
        if lvl.dropna().empty:
            continue
        chart_baskets[bid] = [None if pd.isna(v) else round(float(v), 5) for v in lvl]

        perf = _perf(lvl, bench, idx, ytd_anchor, mtd_anchor)

        last_d = idx.max()
        nm = {m["ticker"]: m for m in members}
        active, partial = [], []
        for m in members:
            t = m["ticker"]
            if t not in present or (m.get("removed") and pd.Timestamp(m["removed"]) <= last_d):
                continue
            tc = closes[t].dropna()
            if tc.empty:
                continue
            first_tape = tc.index[0]
            eff_start = max(first_tape, pd.Timestamp(m["added"]))
            # window-clamped (mirrors engine/baskets.py): pre-window `added` dates must not
            # trip `gap` once the rolling calendar moves past them.
            gap = first_tape > max(pd.Timestamp(m["added"]), idx[0]) + pd.Timedelta(days=7)
            short = eff_start > idx[0] + pd.Timedelta(days=180)
            if gap or short:
                partial.append({"symbol": t, "from": eff_start.strftime("%Y-%m-%d")})
            trailing = {h: _trailing_return(tc, h) for h in (1, 5, 10, 20)}
            yseg = tc[tc.index >= ytd_anchor]
            ry = float(tc.iloc[-1] / yseg.iloc[0] - 1.0) if len(yseg) > 1 else None
            active.append({"symbol": t, "name": nm[t].get(name_key, t),
                           "added": m["added"], "rationale": m.get("rationale", ""),
                           "last": round(float(tc.iloc[-1]), 2),
                           **{f"ret_{h}d": round(v, 4) if v is not None else None
                              for h, v in trailing.items()},
                           "ret_ytd": round(ry, 4) if ry is not None else None})
        active.sort(key=lambda x: (x["ret_20d"] is None, -(x["ret_20d"] or 0)))

        reference = None
        proxy = b.get("etf_proxy")
        if proxy:
            pr = _proxy_returns(proxy, idx, proxy_reader)
            if pr is not None:
                ew_ret = lvl.pct_change()
                pair = pd.concat([ew_ret, pr, bench_ret], axis=1).dropna()
                if len(pair) > 60:
                    corr = float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
                    rc = float((pair.iloc[:, 0] - pair.iloc[:, 2]).corr(pair.iloc[:, 1] - pair.iloc[:, 2]))
                    reference = {"label": "+".join(proxy) if isinstance(proxy, list) else proxy,
                                 "name": b.get("etf_proxy_note", ""), "corr": round(corr, 2),
                                 "rel_corr": round(rc, 2), "n": int(len(pair))}

        changelog = b.get("changelog") or []
        out_baskets.append({
            "id": bid, "name": b["name"], "name_zh": b.get("name_zh", b["name"]),
            "category": b.get("category", "Other"), "category_zh": b.get("category_zh", b.get("category", "其他")),
            "thesis": b.get("thesis", ""), "thesis_zh": b.get("thesis_zh", b.get("thesis", "")),
            "weighting": b.get("weighting", "equal"), "created": b.get("created"),
            "n_members": len(active), "members": active, "changelog": changelog,
            "reference": reference, "missing": missing, "partial": partial,
            "perf": perf,
        })

    if not out_baskets:
        return None
    out_baskets.sort(key=lambda x: (x["perf"]["20d"]["rel"] is None, -(x["perf"]["20d"]["rel"] or 0)))
    cats, cats_zh = [], []
    for b in out_baskets:
        if b["category"] not in cats:
            cats.append(b["category"])
            cats_zh.append(b["category_zh"])
    lead, lag = out_baskets[0], out_baskets[-1]
    story = {"leader": lead["name"], "leader_zh": lead["name_zh"], "leader_rel": lead["perf"]["20d"]["rel"],
             "laggard": lag["name"], "laggard_zh": lag["name_zh"], "laggard_rel": lag["perf"]["20d"]["rel"],
             "n_baskets": len(out_baskets), "n_cats": len(cats)}

    return {
        "as_of": idx.max().strftime("%Y-%m-%d"),
        "benchmark_label": mem.get("benchmark_label", "Benchmark"),
        "benchmark_label_zh": mem.get("benchmark_label_zh", mem.get("benchmark_label", "基准")),
        "construction": mem.get("construction", ""),
        "history_note": mem.get("history_note", ""),
        "note": mem.get("note", ""),
        "categories": cats, "categories_zh": cats_zh, "story": story, "baskets": out_baskets,
        "chart": {"dates": dates,
                  "bench": [None if pd.isna(v) else round(float(v), 5) for v in bench],
                  "baskets": chart_baskets},
    }
