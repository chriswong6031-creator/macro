"""Advanced market-breadth internals for the US dashboard (DISPLAY-ONLY).

Beyond the snapshot "% of stocks above their 50/200-day line", a desk watches the
classic *market internals* — the second-derivative breadth gauges that describe
the QUALITY of a tape. This module computes them as pure functions of the breadth
aggregates the daily collector already stores (``BreadthAdapter.compute`` output:
``adv``/``dec``/``nh``/``nl``/``pct_above_50``/``pct_above_200``/``ad_line``):

  * **McClellan Oscillator & Summation Index** — the ratio-adjusted 19/39-day EMA
    spread of net advances, and its running total. The standard breadth-momentum
    gauge: positive & rising = thrust, negative & falling = internals rolling over.
  * **Zweig Breadth Thrust** — the 10-day EMA of the advancers' share. The famous
    0.40 -> 0.615 launch and where today's reading sits in that band.
  * **High-Low (record-high-percent) Index** — 10-day average of new highs as a
    share of (new highs + new lows): is the new-high/new-low ledger expanding?
  * **A/D-line vs price divergence** — does the cumulative advance/decline line
    confirm the index's recent highs/lows, or is the rally narrowing underneath?
  * **Participation in historical context** — where today's % > 50-day sits in its
    own multi-decade distribution, plus the large/mid/small cross-tier gap.

Everything here is **display-only and never scored.** Breadth internals are a
function of price, so they are coincident with it by construction — they cannot
*lead* it. This is a legibility layer that explains the tape's quality; it is not
a forecast and carries no edge claim.

SURVIVORSHIP CAVEAT: the deep S&P-500 series is rebuilt from *today's* members'
price history, so before ~1990 it covers a thin (<250-name) subset and rebounds
look broader than they were live. The ratio gauges (McClellan, thrust, high-low)
are universe-size robust by construction; the historical *percentile* context is
deliberately taken over the mature-universe window only.
"""
from __future__ import annotations

import pandas as pd

# Mature-universe gate for distribution/percentile context: ignore the thin,
# survivorship-distorted early decades where the current members had barely listed.
MATURE_N = 250
# Thrust-count window: only tally the strict 0.40->0.615 crossing once the proxy
# universe is broad enough that the count is meaningful (roughly 2005+).
THRUST_MATURE_N = 400


def _ratio_net_adv(adv: pd.Series, dec: pd.Series) -> pd.Series:
    """Ratio-adjusted net advances, RANA = 1000 * (adv - dec) / (adv + dec).

    The ratio-adjustment (McClellan, 1969) is what lets a breadth oscillator be
    compared across a changing universe size — it normalises out the denominator
    that grew from ~25 to ~500 names over our window."""
    tot = (adv + dec).where((adv + dec) != 0)
    return (1000.0 * (adv - dec) / tot)


def _spark(s: pd.Series, n: int = 180, dec: int = 1) -> list[float]:
    """Compact tail of a series for an inline sparkline (newest last)."""
    s = s.dropna()
    if s.empty:
        return []
    return [round(float(v), dec) for v in s.tail(n).tolist()]


def mcclellan(adv: pd.Series, dec: pd.Series, fast: int = 19, slow: int = 39) -> dict | None:
    """Ratio-adjusted McClellan Oscillator (EMA spread of net advances) and the
    Summation Index (its running total). Returns latest values, direction, a
    band key + tone, and recent sparklines. The Summation *level* is cumulative
    and therefore window-relative — its slope and sign are what carry meaning."""
    rana = _ratio_net_adv(adv, dec).dropna()
    if len(rana) < slow + 5:
        return None
    osc = rana.ewm(span=fast, adjust=False).mean() - rana.ewm(span=slow, adjust=False).mean()
    summ = osc.cumsum()
    o = float(osc.iloc[-1])
    o_prev = float(osc.iloc[-6]) if len(osc) > 6 else o          # ~1 week ago
    summ_chg = float(summ.iloc[-1] - summ.iloc[-21]) if len(summ) > 21 else 0.0
    # bands: ratio-adjusted osc empirically lives in roughly [-75, +75]
    if o >= 50:
        band, tone = "surging", "pos"
    elif o >= 10:
        band, tone = "positive", "pos"
    elif o > -10:
        band, tone = "neutral", "muted"
    elif o > -50:
        band, tone = "negative", "neg"
    else:
        band, tone = "oversold", "neg"
    return {
        "osc": round(o, 1),
        "osc_prev": round(o_prev, 1),
        "osc_rising": o > o_prev,
        "summ": round(float(summ.iloc[-1]), 0),
        "summ_chg20": round(summ_chg, 0),
        "summ_rising": summ_chg > 0,
        "band": band, "tone": tone,
        "spark": _spark(osc, 180),
        "summ_spark": _spark(summ, 180, dec=0),
    }


def breadth_thrust(adv: pd.Series, dec: pd.Series, n_members: pd.Series | None = None,
                   span: int = 10, washed: float = 0.40, thrust: float = 0.615) -> dict | None:
    """Zweig Breadth Thrust gauge: the ``span``-day EMA of advancers' share,
    ``adv / (adv + dec)``. Reports the live value and zone (washed / neutral /
    thrust), whether a strict ``washed -> thrust`` crossing fired in the last
    ~month, and a historical count over the mature-universe window.

    HONESTY: on a survivorship-biased S&P-500 proxy the strict crossing fires far
    more often than the canonical ~1/decade NYSE signal (rebounds look broader
    than they were live), so this is read as a momentum gauge, not the rare
    historic trigger."""
    tot = (adv + dec).where((adv + dec) != 0)
    bt = (adv / tot).ewm(span=span, adjust=False).mean().dropna()
    if len(bt) < span + 5:
        return None
    v = float(bt.iloc[-1])
    zone = "thrust" if v >= thrust else ("washed" if v <= washed else "neutral")
    tone = "pos" if v >= thrust else ("neg" if v <= washed else "muted")

    # strict crossing: dipped <= washed then reclaimed >= thrust within `span` days
    def _crossings(series: pd.Series) -> list[pd.Timestamp]:
        fired, below = [], None
        for i, val in enumerate(series.values):
            if val <= washed:
                below = i
            elif val >= thrust and below is not None and (i - below) <= span:
                fired.append(series.index[i])
                below = None
        return fired

    # mature window for the historical tally (avoid thin-universe noise)
    mature = bt
    if n_members is not None:
        nm = n_members.reindex(bt.index)
        mature = bt[nm >= THRUST_MATURE_N]
    fired = _crossings(mature) if len(mature) > span else []
    recent_fired = bool(_crossings(bt.tail(25)))
    return {
        "value": round(v, 3),
        "zone": zone, "tone": tone,
        "washed": washed, "thrust": thrust,
        "recent_thrust": recent_fired,
        "hist_count": len(fired),
        "last_thrust": fired[-1].strftime("%Y-%m-%d") if fired else None,
        "spark": _spark(bt, 120, dec=3),
    }


def high_low_index(nh: pd.Series, nl: pd.Series, span: int = 10) -> dict | None:
    """High-Low Index = ``span``-day SMA of the record-high percent,
    ``100 * nh / (nh + nl)``. Above 50 = new highs outpacing new lows (expansion);
    below 50 = the new-low side winning (deterioration). Also surfaces today's net
    new highs and their 10-day average."""
    tot = (nh + nl).where((nh + nl) != 0)
    rhp = (100.0 * nh / tot)
    hli = rhp.rolling(span, min_periods=max(3, span // 2)).mean().dropna()
    if hli.empty:
        return None
    h = float(hli.iloc[-1])
    net = (nh - nl)
    net_now = int(net.iloc[-1])
    net_10 = float(net.tail(span).mean())
    if h >= 70 and net_10 >= 0:
        band, tone = "expanding", "pos"
    elif h <= 30 or net_10 < 0:
        band, tone = "contracting", "neg"
    else:
        band, tone = "mixed", "muted"
    return {
        "hli": round(h, 1),
        "rhp": round(float(rhp.dropna().iloc[-1]), 1) if rhp.notna().any() else None,
        "net_nh": net_now,
        "net_nh_10": round(net_10, 1),
        "band": band, "tone": tone,
        "spark": _spark(hli, 180),
        "net_spark": _spark(net, 120, dec=0),
    }


def divergence(ad_line: pd.Series, price: pd.Series | None,
               window: int = 60, recent: int = 5) -> dict | None:
    """A/D-line vs index-price confirmation over the last ``window`` sessions.

    Reads a *recent* (last ``recent`` days) extreme against the window extreme:
    if price prints a fresh window-high but the cumulative A/D line does NOT, the
    advance is narrowing underneath (bearish divergence); a fresh price low the
    A/D line refuses to confirm is a bullish divergence. Otherwise the internals
    are confirming, or nothing is at an extreme (in-range)."""
    if price is None:
        return None
    px = price.dropna()
    ad = ad_line.reindex(px.index).dropna()
    px = px.reindex(ad.index)
    if len(ad) < window + recent:
        return None
    pw, aw = px.iloc[-window:], ad.iloc[-window:]
    px_hi = px.iloc[-recent:].max() >= pw.max()
    ad_hi = ad.iloc[-recent:].max() >= aw.max()
    px_lo = px.iloc[-recent:].min() <= pw.min()
    ad_lo = ad.iloc[-recent:].min() <= aw.min()
    corr = float(pw.corr(aw))
    if px_hi and not ad_hi:
        state, tone = "bearish_div", "neg"
    elif px_lo and not ad_lo:
        state, tone = "bullish_div", "pos"
    elif px_hi and ad_hi:
        state, tone = "confirmed_up", "pos"
    elif px_lo and ad_lo:
        state, tone = "confirmed_down", "neg"
    else:
        state, tone = "inrange", "muted"
    return {
        "state": state, "tone": tone,
        "window": window,
        "corr": round(corr, 2) if corr == corr else None,
        "ad_chg20": int(ad.diff(20).iloc[-1]) if len(ad) > 20 else None,
        "px_chg20": round(100 * (float(px.iloc[-1]) / float(px.iloc[-21]) - 1), 1) if len(px) > 21 else None,
        "spark": _spark(ad, 120, dec=0),
    }


def participation(frame: pd.DataFrame, mature_n: int = MATURE_N) -> dict | None:
    """Today's % > 50-day / % > 200-day in historical context: the 20-day change
    (participation momentum) and the percentile of today's % > 50-day within its
    own mature-universe distribution. The A/D-line direction rounds it out."""
    if frame is None or frame.empty or "pct_above_50" not in frame:
        return None
    pa50 = frame["pct_above_50"].dropna()
    if pa50.empty:
        return None
    cur = float(pa50.iloc[-1])
    chg20 = round(float(pa50.diff(20).iloc[-1]), 1) if len(pa50) > 20 else 0.0
    # percentile over the mature-universe window only
    hist = pa50
    if "n_members" in frame:
        nm = frame["n_members"].reindex(pa50.index)
        hist = pa50[nm >= mature_n]
    pctile = round(float((hist < cur).mean() * 100), 0) if len(hist) > 50 else None
    std = float(hist.std())
    z = round((cur - float(hist.mean())) / std, 2) if std and len(hist) > 50 else None
    pa200 = frame.get("pct_above_200")
    cur200 = round(float(pa200.dropna().iloc[-1]), 1) if pa200 is not None and pa200.notna().any() else None
    ad_dir = None
    if "ad_line" in frame and len(frame["ad_line"].dropna()) > 20:
        ad_dir = "up" if float(frame["ad_line"].diff(20).iloc[-1]) > 0 else "down"
    return {
        "pa50": round(cur, 1), "pa200": cur200,
        "pa50_chg20": chg20,
        "pctile": pctile, "z": z,
        "hist_from": pd.Timestamp(hist.index[0]).strftime("%Y") if len(hist) else None,
        "ad_dir": ad_dir,
        "spark": _spark(pa50, 180),
    }


def tier_gap(tiers: dict | None) -> dict | None:
    """Large/mid/small cross-tier participation gap (small minus large, % > 50-day).
    Small leading large = healthy broadening; small lagging = a narrow, mega-cap-led
    tape. ``tiers`` maps tier key -> latest % > 50-day."""
    if not tiers or "large" not in tiers or "small" not in tiers:
        return None
    lc, sc = tiers.get("large"), tiers.get("small")
    if lc is None or sc is None:
        return None
    gap = round(sc - lc, 1)
    if gap >= 5:
        state, tone = "broadening", "pos"
    elif gap <= -5:
        state, tone = "narrowing", "neg"
    else:
        state, tone = "inline", "muted"
    return {"large": round(lc, 1), "mid": round(tiers["mid"], 1) if tiers.get("mid") is not None else None,
            "small": round(sc, 1), "gap": gap, "state": state, "tone": tone}


def _tally(*tones: str | None) -> tuple[int, str, str]:
    """Roll component tones into a net read. Returns (score, key, tone)."""
    score = sum(1 if t == "pos" else (-1 if t == "neg" else 0) for t in tones)
    if score >= 2:
        return score, "firm", "pos"
    if score <= -2:
        return score, "deteriorating", "neg"
    return score, "mixed", "muted"


def advanced_breadth(frame: pd.DataFrame, price: pd.Series | None = None,
                     tiers: dict | None = None) -> dict | None:
    """Top-level orchestrator. ``frame`` is the deep large-cap (S&P 500) breadth
    frame; ``price`` an index proxy (SPY close) for the divergence leg; ``tiers``
    the latest % > 50-day per size tier for the cross-tier gap. Returns the full
    display payload (or ``None`` if the frame is unusable). DISPLAY-ONLY."""
    if frame is None or frame.empty or not {"adv", "dec"}.issubset(frame.columns):
        return None
    mcc = mcclellan(frame["adv"], frame["dec"])
    thr = breadth_thrust(frame["adv"], frame["dec"], frame.get("n_members"))
    hl = high_low_index(frame["nh"], frame["nl"]) if {"nh", "nl"}.issubset(frame.columns) else None
    div = divergence(frame["ad_line"], price) if "ad_line" in frame else None
    par = participation(frame)
    gap = tier_gap(tiers)
    if mcc is None and par is None:
        return None
    score, key, tone = _tally(
        mcc and mcc["tone"], mcc and ("pos" if mcc.get("summ_rising") else "neg"),
        thr and thr["tone"], hl and hl["tone"],
        ("pos" if par and par["pa50_chg20"] > 3 else ("neg" if par and par["pa50_chg20"] < -3 else None)),
        div and (div["tone"] if div["state"] in ("bearish_div", "bullish_div") else None),
        gap and gap["tone"],
    )
    asof = pd.Timestamp(frame.index[-1]).strftime("%Y-%m-%d")
    deep_from = pd.Timestamp(frame.index[0]).strftime("%Y")
    return {
        "asof": asof, "deep_from": deep_from,
        "n_deep": int(len(frame)),
        "mcclellan": mcc, "thrust": thr, "highlow": hl,
        "divergence": div, "participation": par, "tiergap": gap,
        "headline": {"score": score, "key": key, "tone": tone},
    }
