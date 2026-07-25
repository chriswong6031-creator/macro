"""Cross-market PERFORMANCE & ROTATION engine for the International dashboard —
the "who is winning, in dollars, and where is capital rotating" layer that the
original comparison grid was missing.

Everything here is DISPLAY-ONLY / descriptive (consistent with the rest of the
vertical): no per-market forward backtest is claimed and nothing feeds a scored
buy/sell. The value is in re-framing data we already collect through the lens a
global allocator actually uses:

  * USD performance — a local equity index is meaningless to a USD investor until
    you fold the currency in. For every market we rebuild the primary index *in US
    dollars* (index x FX, or / FX when the pair is quoted USD/XXX) and rank the 1m
    / 3m / 6m / 12m / YTD return, decomposed EXACTLY into the local-equity leg and
    the currency leg (fx = usd - local, by construction). This is the centrepiece:
    JP can be +89% local yet only +69% in USD once a weak yen is paid for.

  * US-vs-World rotation (RRG-style) — each market's relative-strength line vs the
    US (S&P price index, already in USD) placed on a relative-level x relative-
    momentum plane: leading / weakening / lagging / improving. Plus an aggregate
    "is capital rotating out of US exceptionalism?" tilt.

  * Cross-market correlation — the diversification map: pairwise correlation of the
    USD return streams (5 international + the US), and the average off-diagonal as a
    single "how much diversification is on offer" gauge.

  * World Risk Appetite v2 — a DESCRIPTIVE display-tier 0-100 dial for how risk-on
    the WORLD equity tape is (not just the 7 ex-US intl markets). It widens the
    universe to include the US, China and Hong Kong, weights each market by a
    sqrt-dampened share of world equity market capitalisation (hand-pinned in
    config, not live data), and blends a graded trend leg, a USD-momentum leg and
    a turn-state health leg per market. Hand-pinned weights, never a forecast, and
    NEVER feeds sizing or gating. See ``risk_appetite`` for the full construction.

Pure functions over the shared parquet store; degrade-don't-crash per market.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import intl_inputs, intl_market_state
from lib import config, store

log = logging.getLogger(__name__)

_HORIZON_ORDER = ["1m", "3m", "6m", "12m", "ytd"]
_HORIZON_LABEL = {"1m": ("1M", "1月"), "3m": ("3M", "3月"), "6m": ("6M", "6月"),
                  "12m": ("12M", "12月"), "ytd": ("YTD", "年初至今")}


def _pcfg() -> dict:
    return config.load()["intl"]["engine"].get("performance", {}) or {}


def usd_series(cc: str, closes: pd.DataFrame | None = None) -> pd.Series | None:
    """A market's primary equity index expressed in US dollars.

    For a USD/XXX quote (fx_invert, e.g. USDJPY) a HIGHER pair = weaker local
    currency, so the USD value DIVIDES by the pair. For an XXX/USD quote
    (GBPUSD, EURUSD) the USD value MULTIPLIES. Verified empirically: N225 +89%
    local over 12m became +69% in USD as USDJPY rose ~145->160.
    """
    c = intl_inputs.countries()[cc]
    if closes is None:
        closes = intl_inputs._intl_closes()
    idx_col, fx_col = c["index"], c["fx"]
    if idx_col not in closes or fx_col not in closes:
        return None
    px = closes[idx_col].dropna()
    fx = closes[fx_col].dropna()
    if px.empty or fx.empty:
        return None
    idx = px.index.union(fx.index)
    px = px.reindex(idx).ffill()
    fx = fx.reindex(idx).ffill()
    usd = (px / fx) if c.get("fx_invert") else (px * fx)
    return usd.dropna()


def _local_aligned(cc: str, usd: pd.Series, closes: pd.DataFrame) -> pd.Series | None:
    """The local index reindexed onto the USD series' calendar, so the equity leg
    and the USD leg are measured over the IDENTICAL date grid. Without this the two
    legs step back a fixed N positions on different calendars (the USD series lives
    on the union of the index + FX trading days, ~260/yr after ffill; the raw index
    ~244/yr), spanning different windows and corrupting fx = usd - local."""
    idx_col = intl_inputs.countries()[cc]["index"]
    if idx_col not in closes:
        return None
    return closes[idx_col].reindex(usd.index).ffill().dropna()


def _usd_map(closes: pd.DataFrame) -> dict[str, pd.Series]:
    """Compute each market's USD index once (the four panels all need it)."""
    out: dict[str, pd.Series] = {}
    for cc in intl_inputs.countries():
        s = usd_series(cc, closes)
        if s is not None:
            out[cc] = s
    return out


def _bench_series() -> pd.Series | None:
    """Load the benchmark series (no staleness check).  Use _bench_series_fresh
    whenever a bench_note is also needed (e.g. performance_panel)."""
    bench = _pcfg().get("benchmark", "^GSPC")
    df = store.read("yahoo", bench)
    return df["close"].dropna() if (df is not None and "close" in df.columns) else None


def _bench_series_fresh(
    intl_closes: pd.DataFrame | None = None,
) -> tuple[pd.Series | None, str | None]:
    """ITR-R6 benchmark freshness fail-open.

    Returns (series, bench_note).  bench_note is non-None when SPY was
    substituted because ^GSPC is more than 5 business days stale relative to
    the newest available international index close.

    Staleness definition: the number of business days between the benchmark's
    last date and the newest intl close exceeds 5.

    The fallback loads SPY from data/yahoo/SPY.parquet (same store path as
    other yahoo tickers).  If SPY is also unavailable, returns (None, None).
    """
    _STALE_THRESHOLD_BDAYS = 5
    _SPY_TICKER = "SPY"

    primary_ticker = _pcfg().get("benchmark", "^GSPC")
    primary_df = store.read("yahoo", primary_ticker)
    primary: pd.Series | None = None
    if primary_df is not None and "close" in primary_df.columns:
        primary = primary_df["close"].dropna()

    # Determine the newest intl close date to compare against
    if intl_closes is None:
        try:
            from engine import intl_inputs as _ii
            intl_closes = _ii._intl_closes()
        except Exception:  # noqa: BLE001
            pass

    newest_intl: pd.Timestamp | None = None
    if intl_closes is not None and not intl_closes.empty:
        per_col = intl_closes.apply(lambda s: s.dropna().index[-1] if s.dropna().any() else pd.NaT)
        newest_intl = per_col.max()

    if primary is not None and newest_intl is not None and not pd.isna(newest_intl):
        bench_last = primary.index[-1]
        stale_bdays = len(pd.bdate_range(bench_last, newest_intl)) - 1
        if stale_bdays > _STALE_THRESHOLD_BDAYS:
            # Attempt SPY substitution
            spy_df = store.read("yahoo", _SPY_TICKER)
            if spy_df is not None and "close" in spy_df.columns:
                spy = spy_df["close"].dropna()
                if not spy.empty:
                    note = (
                        f"US benchmark: SPY substituted "
                        f"(^GSPC stale since {bench_last.date()})"
                    )
                    log.warning(
                        "ITR-R6: benchmark %s last date %s is %d business days stale "
                        "(threshold=%d); substituting SPY (last=%s)",
                        primary_ticker, bench_last.date(), stale_bdays,
                        _STALE_THRESHOLD_BDAYS, spy.index[-1].date(),
                    )
                    return spy, note
            # SPY also unavailable — fall through to primary (stale but non-None)
            log.warning(
                "ITR-R6: benchmark %s stale (%d bdays) and SPY unavailable; "
                "returning stale series", primary_ticker, stale_bdays,
            )

    return primary, None


def _ret(s: pd.Series, n: int) -> float | None:
    s = s.dropna()
    if len(s) <= n:
        return None
    return float(s.iloc[-1] / s.iloc[-1 - n] - 1.0) * 100.0


def _ytd_ret(s: pd.Series) -> float | None:
    s = s.dropna()
    if s.empty:
        return None
    yr = int(s.index[-1].year)
    prior = s[s.index < pd.Timestamp(yr, 1, 1)]
    if prior.empty:
        return None
    return float(s.iloc[-1] / prior.iloc[-1] - 1.0) * 100.0


def _spark(s: pd.Series, n: int = 64) -> list[float]:
    """Downsample the trailing ~1y to n points, rebased to 100, for an inline SVG."""
    s = s.dropna().tail(252)
    if len(s) < 8:
        return []
    step = max(1, len(s) // n)
    ds = s.iloc[::step]
    base = float(ds.iloc[0]) or 1.0
    return [round(float(v) / base * 100.0, 2) for v in ds]


def usd_leaderboard(closes: pd.DataFrame | None = None,
                    usd_map: dict[str, pd.Series] | None = None) -> list[dict]:
    """Per-market USD return board with an exact local/FX decomposition."""
    if closes is None:
        closes = intl_inputs._intl_closes()
    if usd_map is None:
        usd_map = _usd_map(closes)
    hz = _pcfg().get("horizons_d", {"1m": 21, "3m": 63, "6m": 126, "12m": 252})
    out: list[dict] = []
    for cc, c in intl_inputs.countries().items():
        usd = usd_map.get(cc)
        # local leg on the SAME calendar as the USD leg (see _local_aligned) so the
        # two _ret() windows step over identical dates and fx = usd - local is honest
        loc = _local_aligned(cc, usd, closes) if usd is not None else None
        if usd is None or loc is None or len(usd) < 30:
            continue
        rets: dict[str, dict] = {}
        for key, n in hz.items():
            u, l = _ret(usd, int(n)), _ret(loc, int(n))
            if u is None or l is None:
                continue
            rets[key] = {"usd": round(u, 1), "local": round(l, 1), "fx": round(u - l, 1)}
        u_ytd, l_ytd = _ytd_ret(usd), _ytd_ret(loc)
        if u_ytd is not None and l_ytd is not None:
            rets["ytd"] = {"usd": round(u_ytd, 1), "local": round(l_ytd, 1),
                           "fx": round(u_ytd - l_ytd, 1)}
        if not rets:
            continue
        ma200 = usd.rolling(200, min_periods=100).mean()
        out.append({
            "cc": cc, "name": c["name"], "name_zh": c.get("name_zh", c["name"]),
            "flag": c["flag"], "region": c.get("region"),
            "index_name": list((c.get("indices") or {c["index"]: c["index"]}).values())[0],
            "returns": rets,
            "above_200d_usd": bool(usd.iloc[-1] > ma200.iloc[-1]) if ma200.notna().iloc[-1] else None,
            "spark": _spark(usd),
        })
    # default sort by 12m USD (fallback 6m/3m), best first
    def _key(r):
        for h in ("12m", "6m", "3m", "ytd", "1m"):
            if h in r["returns"]:
                return r["returns"][h]["usd"]
        return -1e9
    out.sort(key=_key, reverse=True)
    return out


def relative_to_us(closes: pd.DataFrame | None = None,
                   bench: pd.Series | None = None,
                   usd_map: dict[str, pd.Series] | None = None) -> dict | None:
    """RRG-style relative-strength vs the US (S&P price index, already USD).

    For each market: RS = usd_index / bench. We rebase RS to 100 at its own ~1y
    mean (the "relative level" axis) and take the short-window slope of that
    rebased line as "relative momentum". Quadrant:
        level>=100, mom>=0 -> leading      (out-running the US, still accelerating)
        level>=100, mom<0  -> weakening    (still ahead but rolling over)
        level<100,  mom>=0 -> improving     (behind the US but catching up)
        level<100,  mom<0  -> lagging       (behind and still losing ground)
    """
    if closes is None:
        closes = intl_inputs._intl_closes()
    if bench is None:
        bench = _bench_series()
    if bench is None:
        return None
    if usd_map is None:
        usd_map = _usd_map(closes)
    win = int(_pcfg().get("rrg_window_d", 63))
    rows: list[dict] = []
    for cc, c in intl_inputs.countries().items():
        usd = usd_map.get(cc)
        if usd is None or len(usd) < 252:
            continue
        idx = usd.index.intersection(bench.index)
        if len(idx) < 252:
            continue
        rs = (usd.reindex(idx).ffill() / bench.reindex(idx).ffill()).dropna()
        if len(rs) < 252:
            continue
        base = float(rs.tail(252).mean()) or float(rs.iloc[-1])
        level = float(rs.iloc[-1] / base * 100.0)
        # relative momentum: % change of the rebased RS over the window, in points
        mom = float((rs.iloc[-1] / rs.iloc[-1 - win] - 1.0) * 100.0) if len(rs) > win else 0.0
        if level >= 100 and mom >= 0:
            quad, q = "leading", "lead"
        elif level >= 100 and mom < 0:
            quad, q = "weakening", "weak"
        elif level < 100 and mom >= 0:
            quad, q = "improving", "impr"
        else:
            quad, q = "lagging", "lag"
        rel_ret = {h: round(float(rs.iloc[-1] / rs.iloc[-1 - n] - 1.0) * 100.0, 1)
                   for h, n in (("3m", 63), ("6m", 126), ("12m", 252)) if len(rs) > n}
        rows.append({"cc": cc, "name": c["name"], "name_zh": c.get("name_zh", c["name"]),
                     "flag": c["flag"], "region": c.get("region"),
                     "rs_level": round(level, 1), "rs_mom": round(mom, 1),
                     "quad": quad, "q": q, "rel_ret": rel_ret})
    if not rows:
        return None
    rows.sort(key=lambda r: r["rs_mom"], reverse=True)
    leading = sum(1 for r in rows if r["q"] in ("lead", "impr"))
    med_mom = float(np.median([r["rs_mom"] for r in rows]))
    n_outperf = sum(1 for r in rows if (r["rel_ret"].get("6m") or 0) > 0)
    # capital-rotation verdict: are non-US markets, net, gaining on the US?
    if med_mom > 0.6 and leading >= max(3, len(rows) - 1):
        tilt, t_en, t_zh = "ex_us", "Capital rotating toward ex-US", "资本正流向美国以外"
    elif med_mom < -0.6 and leading <= 1:
        tilt, t_en, t_zh = "us", "US still leading the world", "美国仍领跑全球"
    else:
        tilt, t_en, t_zh = "mixed", "Mixed — no decisive US/ex-US rotation", "分化 — 美国与非美无明显轮动"
    return {"rows": rows, "tilt": tilt, "tilt_en": t_en, "tilt_zh": t_zh,
            "median_mom": round(med_mom, 2), "n_leading": leading,
            "n_outperf_6m": n_outperf, "n": len(rows),
            "benchmark": _pcfg().get("benchmark", "^GSPC")}


def correlation_matrix(closes: pd.DataFrame | None = None,
                       bench: pd.Series | None = None,
                       usd_map: dict[str, pd.Series] | None = None) -> dict | None:
    """Pairwise correlation of the USD WEEKLY-return streams (intl + US), plus the
    average off-diagonal as a one-number 'diversification on offer' read.

    Weekly (W-FRI) returns, not daily: the five markets trade on different holiday
    calendars, so a daily grid would have to ffill the non-trading days — injecting
    spurious zero-return days that bias every correlation toward 0. Resampling to
    week-end closes lets all six markets line up on one weekly clock without ffill."""
    if closes is None:
        closes = intl_inputs._intl_closes()
    if usd_map is None:
        usd_map = _usd_map(closes)
    win = int(_pcfg().get("correlation_window_d", 252))
    series: dict[str, pd.Series] = {}
    labels: dict[str, dict] = {}
    for cc, c in intl_inputs.countries().items():
        usd = usd_map.get(cc)
        if usd is not None and len(usd) > win // 2:
            series[cc] = usd
            labels[cc] = {"name": c["name"], "flag": c["flag"]}
    if bench is None:
        bench = _bench_series()
    if bench is not None:
        series["US"] = bench
        labels["US"] = {"name": "United States", "flag": "🇺🇸"}
    if len(series) < 3:
        return None
    weekly = {k: s.resample("W-FRI").last() for k, s in series.items()}
    n_weeks = max(20, win // 5)                              # ~1y window in weeks
    rets = pd.DataFrame(weekly).sort_index().pct_change(fill_method=None).tail(n_weeks)
    corr = rets.corr(min_periods=int(n_weeks * 0.5))
    keys = list(series.keys())
    cells = []
    offdiag = []
    for a in keys:
        row = []
        for b in keys:
            v = corr.loc[a, b] if (a in corr.index and b in corr.columns) else np.nan
            v = None if (v is None or pd.isna(v)) else round(float(v), 2)
            row.append(v)
            if a != b and v is not None:
                offdiag.append(v)
        cells.append(row)
    avg = float(np.mean(offdiag)) if offdiag else None
    if avg is None:
        read_en = read_zh = None
    elif avg >= 0.7:
        read_en, read_zh = "Highly correlated — thin diversification across these markets", "高度相关 — 跨市场分散有限"
    elif avg >= 0.45:
        read_en, read_zh = "Moderately correlated — some diversification on offer", "中度相关 — 有一定分散空间"
    else:
        read_en, read_zh = "Loosely correlated — meaningful diversification on offer", "低相关 — 分散价值显著"
    return {"order": keys, "labels": labels, "cells": cells,
            "avg_offdiag": round(avg, 2) if avg is not None else None,
            "read_en": read_en, "read_zh": read_zh, "window_d": win}


# --- World Risk Appetite v2 --------------------------------------------------
# Per-state health score in [0,1] — how "risk-on" a market in this turn state is.
# Keys MUST stay == set(engine.intl_market_state.STATES) (CI drift guard); a market
# with no available state renormalises its leg weights over trend + mom.
_STATE_HEALTH: dict[str, float] = {
    "uptrend":   1.0,
    "calm":      0.75,
    "recovery":  0.65,
    "extended":  0.6,
    "basing":    0.5,
    "parabolic": 0.45,
    "topping":   0.35,
    "downtrend": 0.2,
    "breaking":  0.1,
    "crash":     0.0,
}
# States that count toward the breakdown share (the "how much of the world is
# actively breaking" gauge that turns Risk-on into a Split tape).
_BREAKDOWN_STATES = {"crash", "breaking"}
# States that qualify a market as a "drag" (ranked worst-first for the headline).
_DRAG_STATES = {"crash", "breaking", "topping", "downtrend"}


def _wr_cfg() -> dict:
    return config.load()["intl"].get("world_risk", {}) or {}


def _clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


def risk_appetite(closes: pd.DataFrame | None = None,
                  usd_map: dict[str, pd.Series] | None = None,
                  extra_closes: dict[str, pd.Series] | None = None,
                  states: dict[str, dict] | None = None) -> dict | None:
    """World Risk Appetite v2 — a cap-weighted, state-aware 0-100 dial.

    DESCRIPTIVE display-tier gauge only: how risk-on the WORLD equity tape is,
    not just the 7 ex-US international markets. Widens the universe to include the
    US, China and Hong Kong and weights each market by a sqrt-dampened share of
    world equity market capitalisation (hand-pinned in config; see ``world_risk``)
    so the US counts most and no single small market can swing the whole dial.
    Hand-pinned weights, never a forecast, and NEVER feeds sizing or gating.

    Construction (all causal, close-only, fail-open per market):
      * ``w_i = sqrt(cap_share_i)`` renormalised over markets actually available.
      * Per-market health ``h_i = 0.35·trend + 0.30·mom + 0.35·state`` in [0,1]:
          trend = 0.6·g200 + 0.4·g50 (graded distance to the 200d/50d MA, LOCAL
                  currency) — a market just above its 200d but under its 50d reads
                  ~0.55, not 1.0, so rollovers are caught.
          mom   = clipped 3-month return in USD terms.
          state = the turn-state health map (uptrend 1.0 … crash 0.0); when no
                  state is available the market's leg weights renormalise over
                  trend + mom only.
      * ``score = round(100 · Σ w_i·h_i / Σ w_i)``.

    Parameters
    ----------
    closes:        the 7-market intl index/FX close frame (as usual).
    usd_map:       precomputed USD index per intl cc (reused, not reloaded).
    extra_closes:  optional {cc → LOCAL close Series} for markets outside
                   intl.countries (US bench, CN Shanghai Composite, HK ^HSI).
    states:        optional {cc → market_states dict} covering any/all markets;
                   the ``state`` key drives the state leg + drags + breakdown.
    """
    if closes is None:
        closes = intl_inputs._intl_closes()
    if usd_map is None:
        usd_map = _usd_map(closes)
    extra_closes = extra_closes or {}
    states = states or {}

    cap_share: dict[str, float] = {k: float(v) for k, v in (_wr_cfg().get("cap_share") or {}).items()}
    extra_meta: dict[str, dict] = _wr_cfg().get("extra_markets") or {}
    countries = intl_inputs.countries()

    # A CNY series lets us express the Shanghai Composite in USD. The build passes
    # it in via extra_closes["_CNY"] (loaded from the china store); it may also be
    # present as a column in `closes` (intl/forex frame). When absent we score CN
    # in local terms (a code comment marks the fallback below).
    cny = None
    _cny_extra = extra_closes.get("_CNY")
    if _cny_extra is not None and not _cny_extra.dropna().empty:
        cny = _cny_extra.dropna()
    else:
        for _c in ("USDCNY=X", "CNY=X", "USDCNH=X", "CNH=F"):
            if _c in closes:
                s = closes[_c].dropna()
                if not s.empty:
                    cny = s
                    break

    def _local_index(cc: str) -> pd.Series | None:
        """LOCAL-currency index close for a market (trend leg is local-currency)."""
        if cc in extra_closes:
            s = extra_closes[cc]
            return s.dropna() if s is not None else None
        c = countries.get(cc)
        if not c:
            return None
        col = c["index"]
        if col in closes:
            s = closes[col].dropna()
            return s if not s.empty else None
        return None

    def _usd_index(cc: str) -> pd.Series | None:
        """USD-terms index for the momentum leg."""
        if cc in usd_map:                       # the 7 intl markets are pre-converted
            return usd_map[cc]
        if cc in extra_closes:
            s = extra_closes[cc]
            s = s.dropna() if s is not None else None
            if s is None or s.empty:
                return None
            if cc == "US":
                return s                        # ^GSPC/SPY already USD
            if cc == "HK":
                return s                        # HKD is pegged to USD — treat as USD-equivalent
            if cc == "CN" and cny is not None:
                # USD/CNY quote (higher = weaker CNY) → USD value DIVIDES by the pair
                idx = s.index.union(cny.index)
                px = s.reindex(idx).ffill()
                fx = cny.reindex(idx).ffill()
                return (px / fx).dropna()
            return s                            # CN with no CNY series — local proxy (fallback)
        return None

    def _trend_leg(px: pd.Series) -> float | None:
        px = px.dropna()
        if len(px) < 200:
            return None
        ma200 = px.rolling(200, min_periods=100).mean()
        ma50 = px.rolling(50, min_periods=25).mean()
        if not (ma200.notna().iloc[-1] and ma50.notna().iloc[-1]):
            return None
        last = float(px.iloc[-1])
        dist200 = (last / float(ma200.iloc[-1]) - 1.0) * 100.0
        dist50 = (last / float(ma50.iloc[-1]) - 1.0) * 100.0
        g200 = _clip01((dist200 + 8) / 12)
        g50 = _clip01((dist50 + 6) / 9)
        return 0.6 * g200 + 0.4 * g50

    def _mom_leg(usd: pd.Series | None) -> float | None:
        if usd is None:
            return None
        r = _ret(usd, 63)
        return None if r is None else _clip01((r + 10) / 20)

    # --- per-market health -----------------------------------------------------
    per_market: dict[str, dict] = {}
    above_200d = 0
    n_above_denom = 0
    all_moms: list[float] = []          # for the hover receipt (full available universe)

    for cc in cap_share:
        local = _local_index(cc)
        usd = _usd_index(cc)
        trend = _trend_leg(local) if local is not None else None
        mom = _mom_leg(usd)
        st = (states.get(cc) or {}).get("state")
        state_h = _STATE_HEALTH.get(st) if st in _STATE_HEALTH else None
        if trend is None and mom is None and state_h is None:
            continue                    # market entirely unavailable — drop it

        # leg weights: 0.35 trend + 0.30 mom + 0.35 state; renormalise over present legs
        legs: list[tuple[float, float]] = []
        if trend is not None:
            legs.append((0.35, trend))
        if mom is not None:
            legs.append((0.30, mom))
        if state_h is not None:
            legs.append((0.35, state_h))
        wsum = sum(w for w, _ in legs)
        if wsum <= 0:
            continue
        health = sum(w * v for w, v in legs) / wsum

        # receipt aggregates over the FULL available universe (not just the 7)
        if local is not None:
            px = local.dropna()
            if len(px) >= 200:
                ma200 = px.rolling(200, min_periods=100).mean()
                if ma200.notna().iloc[-1]:
                    n_above_denom += 1
                    if px.iloc[-1] > ma200.iloc[-1]:
                        above_200d += 1
        if mom is not None and usd is not None:
            _mr = _ret(usd, 63)
            if _mr is not None:
                all_moms.append(_mr)

        per_market[cc] = {"h": round(health, 3), "state": st, "weight_pct": None,
                          "cap_share": cap_share[cc]}

    if not per_market:
        return None

    # --- cap-weighted compose (sqrt-dampened) ----------------------------------
    weights = {cc: float(np.sqrt(cap_share[cc])) for cc in per_market}
    wtot = sum(weights.values())
    for cc in per_market:
        per_market[cc]["weight_pct"] = round(100.0 * weights[cc] / wtot, 1) if wtot else None
    score = int(round(100.0 * sum(weights[cc] * per_market[cc]["h"] for cc in per_market) / wtot)) if wtot else 0

    coverage_num = sum(cap_share[cc] for cc in per_market)
    coverage_den = sum(cap_share.values()) or 1.0
    coverage_pct = round(100.0 * coverage_num / coverage_den, 1)

    # breakdown share: cap-share of markets actively breaking (crash/breaking)
    breakdown_num = sum(cap_share[cc] for cc in per_market
                        if (states.get(cc) or {}).get("state") in _BREAKDOWN_STATES)
    breakdown_share_pct = round(100.0 * breakdown_num / coverage_num, 1) if coverage_num else 0.0

    # --- verdict (display semantics — the SCORE is never floored/overridden) ---
    if score >= 60 and breakdown_share_pct < 20:
        label_en, label_zh, tone = "Risk-on", "风险偏好", "up"
    elif score >= 60 and breakdown_share_pct >= 20:
        label_en, label_zh, tone = "Split tape", "分化行情", "warn"
    elif score < 40:
        label_en, label_zh, tone = "Risk-off", "风险规避", "down"
    else:
        label_en, label_zh, tone = "Neutral", "中性", "flat"

    # --- top drags: worst markets by w_i·(1−h_i), state in the drag set --------
    def _meta(cc: str) -> dict:
        if cc in countries:
            c = countries[cc]
            return {"name": c["name"], "name_zh": c.get("name_zh", c["name"]), "flag": c.get("flag", "")}
        m = extra_meta.get(cc, {})
        return {"name": m.get("name", cc), "name_zh": m.get("name_zh", cc), "flag": m.get("flag", "")}

    drags: list[dict] = []
    for cc, pm in per_market.items():
        st = pm["state"]
        if st in _DRAG_STATES:
            meta = _meta(cc)
            sm = intl_market_state.STATES.get(st, {})
            drags.append({
                "cc": cc, "name": meta["name"], "name_zh": meta["name_zh"], "flag": meta["flag"],
                "state": st, "state_en": sm.get("en", st), "state_zh": sm.get("zh", st),
                "_rank": weights[cc] * (1.0 - pm["h"]),
            })
    drags.sort(key=lambda d: d["_rank"], reverse=True)
    top_drags = [{k: v for k, v in d.items() if k != "_rank"} for d in drags[:3]]

    med_mom = round(float(np.median(all_moms)), 1) if all_moms else None

    return {
        "score": score,
        "label_en": label_en, "label_zh": label_zh, "tone": tone,
        "breadth_above_200d": f"{above_200d}/{n_above_denom}" if n_above_denom else None,
        "median_mom_3m": med_mom,
        "coverage_pct": coverage_pct,
        "n_available": len(per_market),
        "n_universe": len(cap_share),
        "breakdown_share_pct": breakdown_share_pct,
        "top_drags": top_drags,
        "per_market": {cc: {"h": pm["h"], "state": pm["state"], "weight_pct": pm["weight_pct"]}
                       for cc, pm in per_market.items()},
    }


def global_read(records: list[dict], board: list[dict], rrg: dict | None,
                risk: dict | None) -> dict:
    """One synthesized headline sentence for the hero — woven from the regime
    mix, the USD leaderboard extremes, the US/ex-US tilt and the risk dial."""
    quads: dict[str, int] = {}
    for r in records:
        q = r.get("quad_name") or "—"
        quads[q] = quads.get(q, 0) + 1
    dom = max(quads.items(), key=lambda kv: kv[1])[0] if quads else "—"
    best = board[0] if board else None
    worst = board[-1] if board else None

    def _h(r):
        for h in ("12m", "6m", "3m", "ytd"):
            if h in r["returns"]:
                return h, r["returns"][h]["usd"]
        return None, None

    # plain-word quad map (Design Doctrine Law 2 — the raw quad label is
    # Tier-2 vocabulary; engine-composed strings bypass template translation,
    # so the plain-wording must happen HERE at composition)
    _quad_plain = {
        "Goldilocks": ("growth OK, inflation calm", "增长尚可、通胀温和"),
        "Reflation": ("growth up, inflation up", "增长回升、通胀走高"),
        "Stagflation": ("growth down, inflation up", "增长走弱、通胀走高"),
        "Deflation": ("growth down, inflation down", "增长与通胀双弱"),
    }
    dom_en, dom_zh = _quad_plain.get(dom, (dom, dom))
    parts_en, parts_zh = [], []
    parts_en.append(f"{len([r for r in records])} economies; most read {dom_en}.")
    parts_zh.append(f"{len([r for r in records])} 个经济体，多数为{dom_zh}。")
    if best and worst and best is not worst:
        hb, vb = _h(best)
        hw, vw = _h(worst)
        if vb is not None and vw is not None:
            parts_en.append(f"In USD, {best['name']} leads ({vb:+.0f}% {hb}) and "
                            f"{worst['name']} lags ({vw:+.0f}% {hw}).")
            parts_zh.append(f"以美元计，{best.get('name_zh', best['name'])} 领先（{vb:+.0f}% {hb}），"
                            f"{worst.get('name_zh', worst['name'])} 落后（{vw:+.0f}% {hw}）。")
    if rrg:
        parts_en.append(rrg["tilt_en"] + ".")
        parts_zh.append(rrg["tilt_zh"] + "。")
    if risk:
        drags = risk.get("top_drags") or []
        drag_en = drag_zh = ""
        if drags:
            names_en = ", ".join(d["name"] for d in drags[:2])
            names_zh = "、".join(d["name_zh"] for d in drags[:2])
            drag_en = f" — dragged by {names_en}"
            drag_zh = f"——受{names_zh}拖累"
        parts_en.append(f"World risk appetite {risk['label_en'].lower()} ({int(risk['score'])}/100){drag_en}.")
        parts_zh.append(f"全球风险偏好{risk['label_zh']}（{int(risk['score'])}/100）{drag_zh}。")
    return {"en": " ".join(parts_en), "zh": "".join(parts_zh), "dominant_quad": dom}


def performance_panel(closes: pd.DataFrame | None = None,
                      records: list[dict] | None = None,
                      extra_closes: dict[str, pd.Series] | None = None,
                      states: dict[str, dict] | None = None) -> dict:
    """Assemble the whole performance/rotation block for the build script.

    The returned dict gains a 'bench_note' key (str | None) that is non-None
    when SPY was substituted for a stale ^GSPC benchmark (ITR-R6).
    The fresh benchmark is also stored under 'bench' for callers such as
    build_intl that need to pass it to intl_rotation.rank().

    ``extra_closes`` (US/CN/HK LOCAL close Series) and ``states`` (per-cc turn
    states covering the full universe) are threaded into the World Risk Appetite
    v2 dial so it can weigh the US, China and Hong Kong alongside the 7 intl
    markets. Both are optional and fail-open — absent, the dial simply covers
    fewer markets (coverage_pct < 100).
    """
    if closes is None:
        closes = intl_inputs._intl_closes()
    usd_map = _usd_map(closes)            # compute each market's USD index once
    # ITR-R6: use the freshness-checked benchmark for all relative-strength reads
    bench, bench_note = _bench_series_fresh(intl_closes=closes)
    board = usd_leaderboard(closes, usd_map=usd_map)
    rrg = relative_to_us(closes, bench=bench, usd_map=usd_map)
    corr = correlation_matrix(closes, bench=bench, usd_map=usd_map)
    risk = risk_appetite(closes, usd_map=usd_map, extra_closes=extra_closes, states=states)
    read = global_read(records or [], board, rrg, risk)
    return {"leaderboard": board, "rrg": rrg, "correlation": corr,
            "risk_appetite": risk, "global_read": read,
            "bench": bench,
            "bench_note": bench_note,
            "horizons": [{"key": k, "en": _HORIZON_LABEL[k][0], "zh": _HORIZON_LABEL[k][1]}
                         for k in _HORIZON_ORDER]}
