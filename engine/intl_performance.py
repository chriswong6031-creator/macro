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

  * Risk appetite — a cross-market RORO composite (breadth above trend, median
    momentum, currency tide) as a 0-100 dial.

Pure functions over the shared parquet store; degrade-don't-crash per market.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import intl_inputs
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


def risk_appetite(closes: pd.DataFrame | None = None,
                  usd_map: dict[str, pd.Series] | None = None) -> dict | None:
    """Cross-market RORO dial (0-100): breadth above 200d (USD) + median 3m USD
    momentum. Display-only — a descriptive 'how risk-on is the international tape'
    gauge."""
    if closes is None:
        closes = intl_inputs._intl_closes()
    if usd_map is None:
        usd_map = _usd_map(closes)
    above, moms = 0, []
    n = 0
    for cc, c in intl_inputs.countries().items():
        usd = usd_map.get(cc)
        if usd is None or len(usd) < 200:
            continue
        n += 1
        ma200 = usd.rolling(200, min_periods=100).mean()
        if ma200.notna().iloc[-1] and usd.iloc[-1] > ma200.iloc[-1]:
            above += 1
        m = _ret(usd, 63)
        if m is not None:
            moms.append(m)
    if n == 0 or not moms:
        return None
    breadth = above / n                                  # 0..1
    med_mom = float(np.median(moms))                     # %
    breadth_leg = breadth                                # 0..1
    mom_leg = float(np.clip((med_mom + 10) / 20, 0, 1))  # -10%..+10% -> 0..1
    score = round((0.55 * breadth_leg + 0.45 * mom_leg) * 100, 0)
    if score >= 66:
        label_en, label_zh, tone = "Risk-on", "风险偏好", "up"
    elif score >= 40:
        label_en, label_zh, tone = "Neutral", "中性", "flat"
    else:
        label_en, label_zh, tone = "Risk-off", "风险规避", "down"
    return {"score": score, "label_en": label_en, "label_zh": label_zh, "tone": tone,
            "breadth_above_200d": f"{above}/{n}", "median_mom_3m": round(med_mom, 1)}


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
        parts_en.append(f"Cross-market risk appetite {risk['label_en'].lower()} ({int(risk['score'])}/100).")
        parts_zh.append(f"跨市场风险偏好{risk['label_zh']}（{int(risk['score'])}/100）。")
    return {"en": " ".join(parts_en), "zh": "".join(parts_zh), "dominant_quad": dom}


def performance_panel(closes: pd.DataFrame | None = None,
                      records: list[dict] | None = None) -> dict:
    """Assemble the whole performance/rotation block for the build script.

    The returned dict gains a 'bench_note' key (str | None) that is non-None
    when SPY was substituted for a stale ^GSPC benchmark (ITR-R6).
    The fresh benchmark is also stored under 'bench' for callers such as
    build_intl that need to pass it to intl_rotation.rank().
    """
    if closes is None:
        closes = intl_inputs._intl_closes()
    usd_map = _usd_map(closes)            # compute each market's USD index once
    # ITR-R6: use the freshness-checked benchmark for all relative-strength reads
    bench, bench_note = _bench_series_fresh(intl_closes=closes)
    board = usd_leaderboard(closes, usd_map=usd_map)
    rrg = relative_to_us(closes, bench=bench, usd_map=usd_map)
    corr = correlation_matrix(closes, bench=bench, usd_map=usd_map)
    risk = risk_appetite(closes, usd_map=usd_map)
    read = global_read(records or [], board, rrg, risk)
    return {"leaderboard": board, "rrg": rrg, "correlation": corr,
            "risk_appetite": risk, "global_read": read,
            "bench": bench,
            "bench_note": bench_note,
            "horizons": [{"key": k, "en": _HORIZON_LABEL[k][0], "zh": _HORIZON_LABEL[k][1]}
                         for k in _HORIZON_ORDER]}
