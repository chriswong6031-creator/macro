"""Thematic baskets — equal-weight, dated-membership trackers over the FREE cache.

A faithful rebuild of FactorWatch's "Baskets": curated thematic stock baskets,
EQUAL-WEIGHTED with point-in-time dated membership (a member counts only between its
added and removed dates), buy-and-hold between, monthly-rebalanced. The engine emits
two payloads the page renders client-side (like FactorWatch):

  CHART   = { dates:[ISO], bench:[SPY level], baskets:{id:[EW level series]} }
            full daily LEVEL matrix → the interactive lightweight-charts overlay
            (rebased per range) + the live σ/sort table (winRet/winZ run on it).
  BASKETS = { as_of, construction, history_note, note, categories, story,
              baskets:[ {id,name,name_zh,category,thesis,weighting,created,n_members,
                         members:[{symbol,name,added,removed,rationale,last,ret_20d,ret_ytd}],
                         changelog, reference:{label,name,corr,rel_corr,n,note}, missing,
                         partial, perf:{1d/5d/20d/60d/mtd/ytd/full:{ret,rel}} } ] }

HONEST BY CONSTRUCTION (house rule): membership.json is curated with knowledge of the
period, so the ~3y series is HINDSIGHT-curated and descriptive — not an out-of-sample
backtest, not a buy list. Free S&P-1500 universe only (members outside it are excluded
and surfaced as `missing`); names that begin trading mid-window are `partial`.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from engine.equity_factors import _closes, _names_sectors
from lib import config, store

log = logging.getLogger(__name__)

HORIZONS = {"1d": 1, "5d": 5, "10d": 10, "20d": 20, "60d": 60}    # fixed-window horizons (MTD/YTD computed separately)
PARTIAL_GAP_DAYS = 180   # a member whose history starts > ~6 months after the series start is flagged short-history


def _membership() -> dict | None:
    p = config.data_dir() / "baskets" / "membership.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("baskets membership unreadable: %s", e)
        return None


def _basket_extras() -> pd.DataFrame | None:
    """Off-index member closes (data/baskets/extras.parquet, from fetch_basket_extras) —
    recent IPOs and crypto/nuclear names outside the free S&P-1500 cache. Kept separate so
    the breadth/factor universe stays pure; unioned into the close matrix below. Index is
    cast to match the breadth cache unit so the join aligns exactly."""
    p = config.data_dir() / "baskets" / "extras.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.DatetimeIndex(df.index).as_unit("ms")
        return df.sort_index()
    except Exception as e:  # noqa: BLE001
        log.warning("basket extras unreadable: %s", e)
        return None


def _ew_level(rets: pd.DataFrame, members: list, idx: pd.DatetimeIndex) -> pd.Series:
    """Daily equal-weight LEVEL series (start 1.0 at first active day) with point-in-time
    dated membership — a member counts only within [added, removed). NaN before inception."""
    present = [m["ticker"] for m in members if m["ticker"] in rets.columns]
    if len(present) < 3:
        return pd.Series(np.nan, index=idx)
    mask = pd.DataFrame(False, index=idx, columns=present)
    for m in members:
        t = m["ticker"]
        if t not in present:
            continue
        a = idx >= pd.Timestamp(m["added"])
        if m.get("removed"):
            a = a & (idx < pd.Timestamp(m["removed"]))
        mask[t] = a
    ew = rets[present].where(mask).mean(axis=1)         # EW of active members each day
    first = ew.first_valid_index()
    if first is None:
        return pd.Series(np.nan, index=idx)
    lvl = pd.Series(np.nan, index=idx)
    lvl.loc[first:] = (1.0 + ew.loc[first:].fillna(0.0)).cumprod()
    return lvl


def _mtd_anchor(idx: pd.DatetimeIndex) -> pd.Timestamp:
    """Last trading day of the prior month (the close MTD bases off)."""
    last = idx.max()
    prior = idx[idx < pd.Timestamp(last.year, last.month, 1)]
    return prior.max() if len(prior) else idx[0]


def _ret(lvl: pd.Series, anchor) -> float | None:
    s = lvl.dropna()
    if s.empty or anchor is None:
        return None
    base = lvl.get(anchor)
    if base is None or pd.isna(base):
        # nearest valid level at/after anchor
        seg = lvl[lvl.index >= anchor].dropna()
        if seg.empty:
            return None
        base = seg.iloc[0]
    return float(s.iloc[-1] / base - 1.0)


def _perf(lvl: pd.Series, bench: pd.Series, idx: pd.DatetimeIndex,
          ytd_anchor, mtd_anchor) -> dict:
    """raw + (vs-SPY) relative return at every horizon, level-based (matches the client winRet)."""
    out = {}
    valid = lvl.dropna()
    li = idx.get_loc(valid.index[-1]) if not valid.empty else None
    for k, h in HORIZONS.items():
        anc = idx[li - h] if (li is not None and li - h >= 0) else None
        r, br = _ret(lvl, anc), _ret(bench, anc)
        out[k] = {"ret": r, "rel": (r - br if r is not None and br is not None else None)}
    for k, anc in (("mtd", mtd_anchor), ("ytd", ytd_anchor)):
        r, br = _ret(lvl, anc), _ret(bench, anc)
        out[k] = {"ret": r, "rel": (r - br if r is not None and br is not None else None)}
    first = valid.index[0] if not valid.empty else None
    r, br = _ret(lvl, first), _ret(bench, first)
    out["full"] = {"ret": r, "rel": (r - br if r is not None and br is not None else None)}
    return out


def _proxy_returns(proxy, idx: pd.DatetimeIndex) -> pd.Series | None:
    """Daily returns of a reference ETF, or an equal blend of several (e.g. ['XLP','XLU'])."""
    syms = proxy if isinstance(proxy, list) else [proxy]
    legs = []
    for s in syms:
        pe = store.read("yahoo", s)
        if pe is not None and "close" in pe.columns:
            legs.append(pe["close"].reindex(idx).ffill().pct_change())
    if not legs:
        return None
    return pd.concat(legs, axis=1).mean(axis=1)


def compute_baskets() -> dict | None:
    mem = _membership()
    if not mem or not mem.get("baskets"):
        return None
    closes = _closes()
    if closes is None or closes.empty:
        return None
    # Deep-history store (data/baskets/extras.parquet, from fetch_basket_extras): off-index members
    # AND a deep (~3y) tape for in-cache names the breadth caches only hold shallowly — the large-cap
    # cache is a ~15-month rolling window, so a large-cap-heavy basket would otherwise stub at ~15m and
    # flag every member `partial`. PREFER the deep extras series where present (the breadth column only
    # backfills any extras gap); new off-index columns are added outright.
    extras = _basket_extras()                              # off-index + deep tape, aligned to the cache calendar
    if extras is not None and not extras.empty:
        closes.index = pd.DatetimeIndex(closes.index).as_unit("ns")
        extras = extras.copy()
        extras.index = pd.DatetimeIndex(extras.index).as_unit("ns")
        extras = extras.reindex(closes.index)
        overlap = [c for c in extras.columns if c in closes.columns]
        fresh = [c for c in extras.columns if c not in closes.columns]
        if overlap:                                        # deep extras wins; shallow breadth backfills gaps
            closes[overlap] = extras[overlap].combine_first(closes[overlap])
        if fresh:                                          # off-index members -> add outright
            closes = pd.concat([closes, extras[fresh]], axis=1)
        closes = closes.copy()                             # de-fragment after the column-block updates
    rets = closes.pct_change(fill_method=None)
    idx = rets.index
    nm = _names_sectors()

    spy = store.read("yahoo", "SPY")
    if spy is None or "close" not in spy.columns:
        return None
    spy_ret = spy["close"].reindex(idx).ffill().pct_change()
    bench = pd.Series(np.nan, index=idx)
    bf = spy_ret.first_valid_index()
    bench.loc[bf:] = (1.0 + spy_ret.loc[bf:].fillna(0.0)).cumprod()

    year = idx.max().year
    ytd_anchor = idx[idx < pd.Timestamp(year, 1, 1)].max() if (idx < pd.Timestamp(year, 1, 1)).any() else idx[0]
    mtd_anchor = _mtd_anchor(idx)
    dates = [d.strftime("%Y-%m-%d") for d in idx]

    chart_baskets, out_baskets = {}, []
    bdict = mem["baskets"]
    items = bdict.items() if isinstance(bdict, dict) else [(b["id"], b) for b in bdict]
    for bid, b in items:
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

        # latest active members enriched with last / ret_20d / ret_ytd + partial flag
        last_d = idx.max()
        active, partial = [], []
        for m in members:
            t = m["ticker"]
            if t not in present or (m.get("removed") and pd.Timestamp(m["removed"]) <= last_d):
                continue
            tc = closes[t].dropna()
            if tc.empty:
                continue
            first_tape = tc.index[0]
            # effective in-basket history start: never before `added`, so a de-SPAC shell's
            # pre-listing tape (e.g. OKLO before 2024-05) doesn't masquerade as full history.
            eff_start = max(first_tape, pd.Timestamp(m["added"]))
            # window-clamped: an `added` that predates the rolling calendar (idx[0]) must not
            # trip `gap` forever once the window rolls past it — a full-window tape is full
            # history for the visible chart.
            gap = first_tape > max(pd.Timestamp(m["added"]), idx[0]) + pd.Timedelta(days=7)   # data lags the claimed add
            short = eff_start > idx[0] + pd.Timedelta(days=PARTIAL_GAP_DAYS)      # mid-window entrant / recent IPO
            if gap or short:
                partial.append({"symbol": t, "from": eff_start.strftime("%Y-%m-%d")})
            r20 = float(tc.iloc[-1] / tc.iloc[-21] - 1.0) if len(tc) > 21 else None
            yseg = tc[tc.index >= ytd_anchor]
            ry = float(tc.iloc[-1] / yseg.iloc[0] - 1.0) if len(yseg) > 1 else None
            active.append({"symbol": t, "name": nm.get(t, (t, "—"))[0][:26],
                           "added": m["added"], "rationale": m.get("rationale", m.get("note", "")),
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
                pair = pd.concat([ew_ret, pr, spy_ret], axis=1).dropna()
                if len(pair) > 60:
                    corr = float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
                    rc = float((pair.iloc[:, 0] - pair.iloc[:, 2]).corr(pair.iloc[:, 1] - pair.iloc[:, 2]))
                    reference = {"label": "+".join(proxy) if isinstance(proxy, list) else proxy,
                                 "name": b.get("etf_proxy_note", ""), "corr": round(corr, 2),
                                 "rel_corr": round(rc, 2), "n": int(len(pair))}

        changelog = b.get("changelog") or sorted(
            [{"date": m["added"], "action": "add", "note": (m.get("ticker", "") + ": " + m.get("rationale", m.get("note", "")))}
             for m in members], key=lambda x: x["date"])

        out_baskets.append({
            "id": bid, "name": b["name"], "name_zh": b.get("name_zh", b["name"]),
            "category": b.get("category", "Other"), "thesis": b.get("thesis", ""),
            "weighting": b.get("weighting", "equal"), "created": b.get("created"),
            "n_members": len(active), "members": active, "changelog": changelog,
            "reference": reference, "missing": missing, "partial": partial,
            "perf": perf,
        })

    if not out_baskets:
        return None
    out_baskets.sort(key=lambda x: (x["perf"]["20d"]["rel"] is None, -(x["perf"]["20d"]["rel"] or 0)))
    cats = []
    for b in out_baskets:
        if b["category"] not in cats:
            cats.append(b["category"])
    lead, lag = out_baskets[0], out_baskets[-1]
    story = {"leader": lead["name"], "leader_rel": lead["perf"]["20d"]["rel"],
             "laggard": lag["name"], "laggard_rel": lag["perf"]["20d"]["rel"],
             "n_baskets": len(out_baskets), "n_cats": len(cats)}

    return {
        "as_of": idx.max().strftime("%Y-%m-%d"),
        "construction": mem.get("construction",
            "Equal-weighted, monthly-rebalanced, buy-and-hold between rebalances; dated membership changes take effect same-day."),
        "history_note": mem.get("history_note",
            "Series before a basket's creation date are a backtest of the membership as of creation; live tracking starts at creation."),
        "note": mem.get("note", ""),
        "categories": cats, "story": story, "baskets": out_baskets,
        "chart": {"dates": dates,
                  "bench": [None if pd.isna(v) else round(float(v), 5) for v in bench],
                  "baskets": chart_baskets},
    }
