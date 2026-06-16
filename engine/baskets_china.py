"""China thematic baskets — the A-share analogue of engine.baskets.

Equal-weight, point-in-time dated-membership trackers over the FREE china_search cache
(top-market-cap A-shares, ~5y), benchmarked to the CSI 300 (沪深300, the 510300.SS ETF).
Mirrors engine.baskets.compute_baskets() exactly — and reuses its level/return/perf math
(_ew_level / _mtd_anchor / _perf) so the two pages are computed identically — but swaps the
data plane to China:

  • member closes      → data/china_search/closes.parquet  (wide [Date × ticker])
  • member display name → membership.json `name_zh` (the canonical A-share name)
  • benchmark           → store.read("china", "510300.SS")  (CSI 300 ETF)
  • etf_proxy cross-check → the china-group sector ETFs (半导体/酒/银行/证券…)

Emits the same two payloads the page renders client-side:
  CHART   = { dates:[ISO], bench:[CSI300 level], baskets:{id:[EW level series]} }
  BASKETS = { as_of, benchmark_label{,_zh}, construction, history_note, note, categories,
              categories_zh, story, baskets:[ {id,name,name_zh,category,category_zh,thesis,
              thesis_zh,weighting,created,n_members,members:[…], changelog, reference,
              missing, partial, perf} ] }

HONEST BY CONSTRUCTION (house rule): membership.json is curated with knowledge of the
period, so the series is HINDSIGHT-curated and descriptive — not an out-of-sample backtest
and not a buy list. Additive — any failure returns None and the page is skipped.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from engine.baskets import _ew_level, _mtd_anchor, _perf  # identical EW/level/return math
from lib import config, store

log = logging.getLogger(__name__)

BENCHMARK_DEFAULT = "510300.SS"   # CSI 300 ETF (沪深300)


def _membership() -> dict | None:
    p = config.data_dir() / "baskets_china" / "membership.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("china baskets membership unreadable: %s", e)
        return None


def _closes() -> pd.DataFrame | None:
    """Wide [Date × ticker] adjusted closes for the china_search universe (~800 names, ~5y)."""
    p = config.data_dir() / "china_search" / "closes.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.DatetimeIndex(df.index)
        return df.sort_index()
    except Exception as e:  # noqa: BLE001
        log.warning("china_search closes unreadable: %s", e)
        return None


def _proxy_returns(proxy, idx: pd.DatetimeIndex) -> pd.Series | None:
    """Daily returns of a reference china-group sector ETF (or an equal blend of several)."""
    syms = proxy if isinstance(proxy, list) else [proxy]
    legs = []
    for s in syms:
        pe = store.read("china", s)
        if pe is not None and "close" in pe.columns:
            legs.append(pe["close"].reindex(idx).ffill().pct_change())
    if not legs:
        return None
    return pd.concat(legs, axis=1).mean(axis=1)


def compute_china_baskets() -> dict | None:
    mem = _membership()
    if not mem or not mem.get("baskets"):
        return None
    closes = _closes()
    if closes is None or closes.empty:
        return None
    rets = closes.pct_change(fill_method=None)
    idx = rets.index

    bench_sym = mem.get("benchmark", BENCHMARK_DEFAULT)
    bench_raw = store.read("china", bench_sym)
    if bench_raw is None or "close" not in bench_raw.columns:
        return None
    bench_ret = bench_raw["close"].reindex(idx).ffill().pct_change()
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
            log.warning("china basket %s skipped: only %d members in cache", bid, len(present))
            continue
        lvl = _ew_level(rets, members, idx)
        if lvl.dropna().empty:
            continue
        chart_baskets[bid] = [None if pd.isna(v) else round(float(v), 5) for v in lvl]

        perf = _perf(lvl, bench, idx, ytd_anchor, mtd_anchor)

        # latest active members enriched with last / ret_20d / ret_ytd + partial flag
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
            gap = first_tape > pd.Timestamp(m["added"]) + pd.Timedelta(days=7)
            short = eff_start > idx[0] + pd.Timedelta(days=180)
            if gap or short:
                partial.append({"symbol": t, "from": eff_start.strftime("%Y-%m-%d")})
            r20 = float(tc.iloc[-1] / tc.iloc[-21] - 1.0) if len(tc) > 21 else None
            yseg = tc[tc.index >= ytd_anchor]
            ry = float(tc.iloc[-1] / yseg.iloc[0] - 1.0) if len(yseg) > 1 else None
            active.append({"symbol": t, "name": nm[t].get("name_zh", t),
                           "added": m["added"], "rationale": m.get("rationale", ""),
                           "last": round(float(tc.iloc[-1]), 2),
                           "ret_20d": round(r20, 4) if r20 is not None else None,
                           "ret_ytd": round(ry, 4) if ry is not None else None})
        active.sort(key=lambda x: (x["ret_20d"] is None, -(x["ret_20d"] or 0)))

        # reference-ETF cross-check: absolute + market-adjusted (beta-stripped) correlation
        reference = None
        proxy = b.get("etf_proxy")
        if proxy:
            pr = _proxy_returns(proxy, idx)
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
        "benchmark_label": mem.get("benchmark_label", "CSI 300"),
        "benchmark_label_zh": mem.get("benchmark_label_zh", "沪深300"),
        "construction": mem.get("construction", ""),
        "history_note": mem.get("history_note", ""),
        "note": mem.get("note", ""),
        "categories": cats, "categories_zh": cats_zh, "story": story, "baskets": out_baskets,
        "chart": {"dates": dates,
                  "bench": [None if pd.isna(v) else round(float(v), 5) for v in bench],
                  "baskets": chart_baskets},
    }
