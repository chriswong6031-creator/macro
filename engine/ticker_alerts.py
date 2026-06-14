"""Per-ticker / per-sector-ETF alert feed — a deterministic technical
signal-change timeline, with the cycle-ladder's standing read pinned on top.

Mirrors engine/forex_alerts.py (idempotent ``_ev`` records + ``_transitions``
walked over state columns recomputed from price history each build) and the
BTC Vector record schema in engine/btc_alerts.py (tier / edge / forward
conviction layer + bilingual ``*_zh`` fields). Unlike the GLOBAL macro alert
log (engine/alerts.py), this is PER ASSET and almost entirely reproducible from
the price series itself — so there is no fragile cross-build state to persist,
except a small append-only ladder log that lets PAST ladder transitions accrue
(the *current* transition is always derivable from the live ladder, so day-1
works with an empty log).

Events (all backfilled from the asset's own daily history):

  ladder       cycle-ladder state / action change         pinned · act
  ma_cross     50×200-DMA golden / death cross             trend · act
  trend_200    price crossing its 200-day average          trend · watch
  dcl          daily-cycle low printed                     cycle · watch
  rs           relative-strength leadership / breakdown     strength · watch
  macd_w       weekly MACD histogram cross                 momentum · watch
  macd_d       daily MACD histogram cross                  momentum · context
  stoch        StochRSI turning up out of oversold         momentum · context
  rsi          RSI into overbought / oversold              momentum · context
  range_52w    new 52-week high / low                      cycle · watch

Everything here is CONTEXT / structure, never a price target — see
LIMITATIONS.md. The build embeds the recent slice into each stockdata JSON
(stock page reads it client-side) or passes it to the sector template.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from engine.cycles import find_troughs, macd_parts, stoch_rsi
from engine.technicals import macd_hist, rsi
from engine.indicators import pct_rank_window
from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conviction + display metadata, keyed by event type. Edge/forward are honest,
# framework-level notes — NOT fabricated per-ticker backtest numbers.
# ---------------------------------------------------------------------------
FILTER_LABELS = {                       # short chip text per filter group
    "signal":   ("Signal",     "信号"),
    "trend":    ("Trend",      "趋势"),
    "momentum": ("Momentum",   "动量"),
    "strength": ("vs Market",  "相对强弱"),
    "cycle":    ("Cycle",      "周期"),
}

META: dict[str, dict] = {
    "ladder": dict(tier="act",
        edge="The cycle ladder's standing read — built for position structure, not a price target.",
        edge_zh="周期阶梯的当前判读 — 用于仓位结构，而非价格目标。",
        forward="Use it for sizing and the invalidation level, not for certainty.",
        forward_zh="用于仓位规模与失效价位，而非追求确定性。"),
    "ma_cross": dict(tier="act",
        edge="50/200-day cross — a slow, widely-watched trend filter; it lags but rarely whipsaws.",
        edge_zh="50/200日均线交叉 — 一个滞后但很少来回的、广受关注的趋势过滤器。",
        forward="A regime label, not an entry — most of the move precedes the cross.",
        forward_zh="这是趋势标签而非入场点 — 大部分行情发生在交叉之前。"),
    "trend_200": dict(tier="watch",
        edge="Price vs the 200-day average — the classic bull / bear dividing line.",
        edge_zh="价格相对200日均线 — 经典的多空分界线。",
        forward="A backdrop filter; pair it with a cycle low or momentum cross to act.",
        forward_zh="作为背景过滤器；需配合周期低点或动量交叉再行动。"),
    "dcl": dict(tier="watch",
        edge="Daily-cycle low — historically the highest-odds long-entry window in this framework.",
        edge_zh="日线周期低点 — 在本框架中历史上做多胜率最高的入场窗口。",
        forward="Confirm with a swing low and a reclaim of the 10-day average before sizing up.",
        forward_zh="加仓前以一个摆动低点并收复10日均线来确认。"),
    "rs": dict(tier="watch",
        edge="Relative strength vs SPY — momentum persistence is one of the few robust equity factors.",
        edge_zh="相对标普500的强弱 — 动量持续性是少数稳健的股票因子之一。",
        forward="Leadership tends to persist; breakdowns warn before price does.",
        forward_zh="领先往往延续；走弱常先于价格发出警示。"),
    "macd_w": dict(tier="watch",
        edge="Weekly MACD — the slower, less-whippy momentum read.",
        edge_zh="周线MACD — 更慢、更少来回的动量信号。",
        forward="Higher-timeframe confirmation; daily noise resolves around it.",
        forward_zh="更高周期的确认；日线噪音围绕它收敛。"),
    "macd_d": dict(tier="context",
        edge="Daily MACD — fast and noisy; context, not a standalone trigger.",
        edge_zh="日线MACD — 快速且嘈杂；仅作背景，而非独立触发。",
        forward="Frequent by design — filter with the weekly cross and trend.",
        forward_zh="本就频繁 — 用周线交叉与趋势加以过滤。"),
    "stoch": dict(tier="context",
        edge="StochRSI turning up out of oversold — the earliest oscillator heads-up.",
        edge_zh="StochRSI自超卖区上行 — 最早的振荡指标预警。",
        forward="An early flag, not confirmation; it can fire repeatedly in a downtrend.",
        forward_zh="早期信号而非确认；下跌趋势中可能反复出现。"),
    "rsi": dict(tier="context",
        edge="RSI extreme — stretched and mean-reversion-prone; not a timing trigger alone.",
        edge_zh="RSI极值 — 超买/超卖且易均值回归；单独不构成择时触发。",
        forward="Extremes can persist in strong trends — context, not a fade signal.",
        forward_zh="强趋势中极值可持续 — 仅作背景，而非反向信号。"),
    "range_52w": dict(tier="watch",
        edge="New 52-week extreme — a momentum / trend signal the whole market watches.",
        edge_zh="创52周新高/新低 — 全市场关注的动量/趋势信号。",
        forward="New highs beget highs more often than not; new lows cut both ways.",
        forward_zh="新高往往延续；新低则两面皆有可能。"),
}

# filter group each event type belongs to (drives the UI filter chips)
_FILTER = {"ladder": "signal", "ma_cross": "trend", "trend_200": "trend",
           "dcl": "cycle", "rs": "strength", "macd_w": "momentum",
           "macd_d": "momentum", "stoch": "momentum", "rsi": "momentum",
           "range_52w": "cycle"}

_SEV_RANK = {"high": 0, "medium": 1, "info": 2}


# ---------------------------------------------------------------------------
# Record factory + transition helper (mirrors forex_alerts)
# ---------------------------------------------------------------------------
def _ev(asset: str, type_: str, ts, severity: str, direction: str,
        headline: str, detail: str, context: dict, to_state: str,
        headline_zh: str = "", detail_zh: str = "", pinned: bool = False) -> dict:
    ts = pd.Timestamp(ts)
    bucket = ts.strftime("%Y-%m-%dT%H:%M")
    m = META.get(type_, {})
    flt = _FILTER.get(type_, "momentum")
    lab = FILTER_LABELS.get(flt, ("", ""))
    return {"id": f"equity:{asset}:{type_}:{bucket}:{to_state}", "ts": ts.isoformat(),
            "source": "equity", "asset": asset, "type": type_, "filter": flt,
            "severity": severity, "dir": direction, "tier": m.get("tier", "context"),
            "pinned": pinned, "label": lab[0], "label_zh": lab[1],
            "headline": headline, "detail": detail,
            "headline_zh": headline_zh or headline, "detail_zh": detail_zh or detail,
            "edge": m.get("edge", ""), "edge_zh": m.get("edge_zh", ""),
            "forward": m.get("forward", ""), "forward_zh": m.get("forward_zh", ""),
            "context": context, "anchor": "#af-feed"}


def _transitions(state: pd.Series):
    """(ts, from, to) at each change point; the first observation is never a
    change. Identical contract to forex_alerts._transitions."""
    s = state.dropna()
    if s.empty:
        return []
    chg = s != s.shift()
    chg.iloc[0] = False
    return [(t, s.shift()[t], s[t]) for t in s.index[chg]]


def _band(s: pd.Series, hi, lo, hi_word, lo_word, mid="mid") -> pd.Series:
    return pd.Series(np.where(s >= hi, hi_word, np.where(s <= lo, lo_word, mid)),
                     index=s.index).where(s.notna())


# ---------------------------------------------------------------------------
# Technical timeline — backfilled from the asset's own daily price history
# ---------------------------------------------------------------------------
def technical_events(asset: str, close: pd.Series, high: pd.Series | None,
                     bench: pd.Series | None) -> list[dict]:
    out: list[dict] = []
    c = close.dropna()
    # collapse any duplicate-index bars (keep the last) so .get(ts) stays scalar
    # and rolling / resample stay well-defined on malformed input
    c = c[~c.index.duplicated(keep="last")]
    if len(c) < 60:
        return out

    def px(ts) -> str:
        v = c.get(ts, float("nan"))
        return f"${v:,.2f}" if pd.notna(v) else ""

    sma50 = c.rolling(50).mean()
    sma200 = c.rolling(200).mean()

    # --- price vs the 200-day average -------------------------------------
    if sma200.notna().sum() > 2:
        trend = pd.Series(np.where(c > sma200, "above", "below"),
                          index=c.index).where(sma200.notna())
        for ts, frm, to in _transitions(trend.dropna()):
            up = to == "above"
            out.append(_ev(asset, "trend_200", ts, "medium", "up" if up else "down",
                f"{asset} reclaimed its 200-day average" if up
                else f"{asset} lost its 200-day average",
                f"Price closed {'back above' if up else 'below'} the 200-day moving average — "
                f"the classic {'bull' if up else 'bear'} dividing line. {px(ts)}.",
                {}, to,
                headline_zh=f"{asset} 收复200日均线" if up else f"{asset} 跌破200日均线",
                detail_zh=f"收盘{'重回' if up else '跌破'}200日均线 — 经典的"
                          f"{'多头' if up else '空头'}分界线。{px(ts)}。"))

    # --- 50×200 golden / death cross --------------------------------------
    if sma50.notna().sum() > 2 and sma200.notna().sum() > 2:
        gc = pd.Series(np.where(sma50 > sma200, "golden", "death"),
                       index=c.index).where(sma50.notna() & sma200.notna())
        for ts, frm, to in _transitions(gc.dropna()):
            up = to == "golden"
            out.append(_ev(asset, "ma_cross", ts, "high", "up" if up else "down",
                f"Golden cross on {asset}" if up else f"Death cross on {asset}",
                f"The 50-day average crossed {'above' if up else 'below'} the 200-day — a slow, "
                f"widely-watched {'bullish' if up else 'bearish'} trend signal. {px(ts)}.",
                {}, to,
                headline_zh=f"{asset} 金叉" if up else f"{asset} 死叉",
                detail_zh=f"50日均线{'上穿' if up else '下穿'}200日均线 — 一个滞后但广受关注的"
                          f"{'看多' if up else '看空'}趋势信号。{px(ts)}。"))

    # --- daily-cycle lows --------------------------------------------------
    for ts in find_troughs(c):
        out.append(_ev(asset, "dcl", ts, "medium", "up",
            f"{asset} printed a daily-cycle low",
            f"A confirmed local low — in this cycle framework the highest-odds long-entry "
            f"window. {px(ts)}.",
            {"price": round(float(c.get(ts, float('nan'))), 2)}, "dcl",
            headline_zh=f"{asset} 打出日线周期低点",
            detail_zh=f"一个已确认的局部低点 — 在本周期框架中做多胜率最高的入场窗口。{px(ts)}。"))

    # --- relative strength vs the benchmark (SPY) -------------------------
    if bench is not None:
        rel = (c / bench.reindex(c.index).ffill()).replace([np.inf, -np.inf], np.nan).dropna()
        if len(rel) > 120:
            rank = pct_rank_window(rel, 90) * 100
            band = _band(rank, 90, 10, "leader", "laggard", "inline")
            for ts, frm, to in _transitions(band.dropna()):
                if to == "inline":
                    continue
                lead = to == "leader"
                out.append(_ev(asset, "rs", ts, "medium", "up" if lead else "down",
                    f"{asset} took relative-strength leadership" if lead
                    else f"{asset} broke down vs the market",
                    f"Relative strength vs SPY crossed {'above the 90th' if lead else 'below the 10th'} "
                    f"percentile of the last 90 days — {'leadership tends to persist' if lead else 'weakness often leads price'}. {px(ts)}.",
                    {}, to,
                    headline_zh=f"{asset} 取得相对强弱领先" if lead else f"{asset} 相对市场走弱",
                    detail_zh=f"相对标普500的强弱{'上穿近90日的第90' if lead else '下穿近90日的第10'}百分位 — "
                              f"{'领先往往延续' if lead else '走弱常先于价格'}。{px(ts)}。"))

    # --- weekly MACD histogram cross --------------------------------------
    w = c.resample("W-FRI").last().dropna()
    if len(w) >= 40:
        hw = macd_parts(w)["hist"]
        sgn = pd.Series(np.where(hw > 0, "bull", "bear"), index=hw.index).where(hw.notna())
        for ts, frm, to in _transitions(sgn.dropna()):
            up = to == "bull"
            out.append(_ev(asset, "macd_w", ts, "medium", "up" if up else "down",
                f"{asset} weekly MACD crossed {'up' if up else 'down'}",
                f"The weekly MACD histogram turned {'positive' if up else 'negative'} — the slower, "
                f"less-whippy momentum read.",
                {}, to,
                headline_zh=f"{asset} 周线MACD{'上' if up else '下'}穿",
                detail_zh=f"周线MACD柱状图转{'正' if up else '负'} — 更慢、更少来回的动量信号。"))

    # --- daily MACD histogram cross (context; frequent) -------------------
    hd = macd_hist(c)
    sgn_d = pd.Series(np.where(hd > 0, "bull", "bear"), index=hd.index).where(hd.notna())
    for ts, frm, to in _transitions(sgn_d.dropna()):
        up = to == "bull"
        out.append(_ev(asset, "macd_d", ts, "info", "up" if up else "down",
            f"{asset} daily MACD crossed {'up' if up else 'down'}",
            f"The daily MACD histogram turned {'positive' if up else 'negative'} — fast and noisy, "
            f"context rather than a standalone trigger. {px(ts)}.",
            {}, to,
            headline_zh=f"{asset} 日线MACD{'上' if up else '下'}穿",
            detail_zh=f"日线MACD柱状图转{'正' if up else '负'} — 快速且嘈杂，仅作背景。{px(ts)}。"))

    # --- StochRSI turning up out of oversold ------------------------------
    sr = stoch_rsi(c)
    szone = _band(sr, 80, 20, "overbought", "oversold", "neutral")
    for ts, frm, to in _transitions(szone.dropna()):
        if not (frm == "oversold" and to == "neutral"):
            continue
        out.append(_ev(asset, "stoch", ts, "info", "up",
            f"{asset} StochRSI turned up from oversold",
            f"StochRSI popped back above 20 — the earliest oscillator heads-up that downside "
            f"momentum is easing. {px(ts)}.",
            {}, "turn_up",
            headline_zh=f"{asset} StochRSI自超卖区上行",
            detail_zh=f"StochRSI重回20上方 — 下行动量趋缓的最早预警。{px(ts)}。"))

    # --- RSI extremes -----------------------------------------------------
    r = rsi(c, 14)
    rzone = _band(r, 70, 30, "overbought", "oversold", "neutral")
    for ts, frm, to in _transitions(rzone.dropna()):
        if to == "neutral":
            continue
        ob = to == "overbought"
        # RSI extremes are CONTEXT, not a directional buy/sell — keep the node
        # neutral so the colour doesn't read as a bull/bear call (and can't invert
        # confusingly under the zh red=up swap).
        out.append(_ev(asset, "rsi", ts, "info", "neutral",
            f"{asset} RSI reached {'overbought' if ob else 'oversold'}",
            f"RSI(14) crossed {'above 70' if ob else 'below 30'} — {'stretched to the upside' if ob else 'washed out'}; "
            f"context, not a timing trigger alone. {px(ts)}.",
            {}, to,
            headline_zh=f"{asset} RSI进入{'超买' if ob else '超卖'}",
            detail_zh=f"RSI(14){'上穿70' if ob else '下穿30'} — {'上行过度' if ob else '超卖'}；"
                      f"仅作背景，单独不构成择时。{px(ts)}。"))

    # --- new 52-week high / low -------------------------------------------
    roll_hi = c.rolling(252, min_periods=200).max()
    roll_lo = c.rolling(252, min_periods=200).min()
    ext = pd.Series(np.where(c >= roll_hi * 0.999, "high",
                    np.where(c <= roll_lo * 1.001, "low", "mid")),
                    index=c.index).where(roll_hi.notna())
    for ts, frm, to in _transitions(ext.dropna()):
        if to == "mid":
            continue
        hi = to == "high"
        out.append(_ev(asset, "range_52w", ts, "medium", "up" if hi else "down",
            f"{asset} made a new 52-week {'high' if hi else 'low'}",
            f"Price reached a fresh 52-week {'high' if hi else 'low'} — a momentum / trend extreme the "
            f"whole market watches. {px(ts)}.",
            {}, to,
            headline_zh=f"{asset} 创52周新{'高' if hi else '低'}",
            detail_zh=f"价格创出52周新{'高' if hi else '低'} — 全市场关注的动量/趋势极值。{px(ts)}。"))

    return out


# ---------------------------------------------------------------------------
# Ladder layer — the standing read (pinned) + accruing history
# ---------------------------------------------------------------------------
def _ladder_path():
    return config.data_dir() / "ticker_alerts" / "ladder_log.parquet"


def _disp(label) -> tuple[str, str]:
    """(English, Chinese) for a ladder label/action, via the i18n glossary."""
    en = str(label or "")
    try:
        from engine.i18n import tr
        return en, tr(en)
    except Exception:  # noqa: BLE001 — i18n is best-effort
        return en, en


def _state_disp(state) -> tuple[str, str]:
    """(English, Chinese) for a raw ladder STATE — mapped to its friendly display
    label first (so e.g. 'TOP WATCH' shows as its label, translated), then glossed."""
    s = str(state or "")
    if not s:
        return "", ""
    try:
        from engine.cycles import STATE_DISPLAY
        s = (STATE_DISPLAY.get(s) or {}).get("label", s)
    except Exception:  # noqa: BLE001
        pass
    return _disp(s)


def ladder_pinned(asset: str, ladder: dict | None, asof: str | None) -> dict | None:
    """The cycle ladder's CURRENT standing read, as a pinned headline event.
    Always derivable from the live ladder — works on day 1 with no history."""
    if not ladder or not ladder.get("state"):
        return None
    when = ladder.get("signal_date") or asof
    if when is None:
        return None
    state = ladder.get("state", "")
    label_en, label_zh = _disp(ladder.get("label") or state)
    action_en, action_zh = _disp(ladder.get("action") or "")
    prev = ladder.get("prev_state")
    prev_en, prev_zh = _state_disp(prev) if prev and prev != state else ("", "")
    entry = ladder.get("entry") or {}
    head_en = (f"{prev_en} → {label_en}" if prev_en else f"Now: {label_en}")
    head_zh = (f"{prev_zh} → {label_zh}" if prev_zh else f"当前：{label_zh}")
    why_en = ladder.get("why") or ""
    why_zh = ladder.get("why_zh") or why_en
    det_en = f"{action_en}. {why_en}".strip(". ").strip() or action_en
    det_zh = f"{action_zh}。{why_zh}".strip("。 ").strip() or action_zh
    ev = _ev(asset, "ladder", pd.Timestamp(when), "high", ladder.get("dir") or "neutral",
             head_en, det_en, {"state": state, "score": ladder.get("score"),
                               "urgency": entry.get("urgency")},
             state, headline_zh=head_zh, detail_zh=det_zh, pinned=True)
    # carry the urgency so the UI can colour the pinned card like the verdict bar
    ev["urgency"] = entry.get("urgency") or "hold"
    ev["state_class"] = state.replace(" ", "_")
    return ev


def ladder_row(asset: str, ladder: dict | None, asof: str | None) -> dict | None:
    """The current ladder transition as a log row, or None when there's nothing
    to record. Builds collect these and flush once via write_ladder_log_batch."""
    if not ladder or not ladder.get("state"):
        return None
    when = str(ladder.get("signal_date") or asof or "")
    if not when:
        return None
    return {"asset": asset, "signal_date": when, "state": ladder.get("state", ""),
            "prev_state": ladder.get("prev_state") or "",
            "action": ladder.get("action") or "", "label": ladder.get("label") or "",
            "urgency": (ladder.get("entry") or {}).get("urgency") or "",
            "score": int(ladder.get("score") or 0), "dir": ladder.get("dir") or "neutral",
            "asof": str(asof or "")}


def write_ladder_log_batch(rows: list[dict]) -> int:
    """Idempotently append many ladder rows in ONE read-modify-write so a full
    build touches the shared log once, not per-ticker. Dedup key =
    (asset, signal_date, state). Atomic (temp + os.replace) so a concurrent build
    never reads a half-written file. Returns the number of new rows added."""
    rows = [r for r in rows if r]
    if not rows:
        return 0
    p = _ladder_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        old = pd.read_parquet(p) if p.exists() else pd.DataFrame()
    except Exception:  # noqa: BLE001 — a corrupt log must never break the build
        old = pd.DataFrame()
    seen: set[tuple] = set()
    if not old.empty:
        seen = set(zip(old["asset"], old["signal_date"].astype(str), old["state"]))
    fresh, batch_seen = [], set()
    for r in rows:
        k = (r["asset"], str(r["signal_date"]), r["state"])
        if k in seen or k in batch_seen:
            continue
        batch_seen.add(k)
        fresh.append(r)
    if not fresh:
        return 0
    new = pd.concat([old, pd.DataFrame(fresh)], ignore_index=True)
    tmp = p.with_suffix(".parquet.tmp")
    new.to_parquet(tmp)
    os.replace(tmp, p)
    return len(fresh)


def append_ladder_log(asset: str, ladder: dict | None, asof: str | None) -> None:
    """Single-row convenience wrapper over write_ladder_log_batch."""
    write_ladder_log_batch([ladder_row(asset, ladder, asof)])


def ladder_history_events(asset: str, exclude_when: str | None = None) -> list[dict]:
    """Past ladder transitions for `asset` from the accruing log, as timeline
    events (the current one — `exclude_when` — is shown pinned, not here)."""
    p = _ladder_path()
    if not p.exists():
        return []
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return []
    if df.empty or "asset" not in df.columns:
        return []
    rows = df[df["asset"] == asset]
    out = []
    for _, r in rows.iterrows():
        when = str(r["signal_date"])
        if exclude_when and when == str(exclude_when):
            continue
        state = str(r["state"])
        label_en, label_zh = _disp(r.get("label") or state)
        prev = str(r.get("prev_state") or "")
        prev_en, prev_zh = _state_disp(prev) if prev and prev != state else ("", "")
        head_en = f"{prev_en} → {label_en}" if prev_en else f"Signal: {label_en}"
        head_zh = f"{prev_zh} → {label_zh}" if prev_zh else f"信号：{label_zh}"
        act_en, act_zh = _disp(r.get("action") or "")
        ev = _ev(asset, "ladder", pd.Timestamp(when), "high", str(r.get("dir") or "neutral"),
                 head_en, act_en, {"state": state, "score": int(r.get("score") or 0)},
                 state, headline_zh=head_zh, detail_zh=act_zh)
        ev["state_class"] = state.replace(" ", "_")
        out.append(ev)
    return out


# ---------------------------------------------------------------------------
# Assembly + display helpers
# ---------------------------------------------------------------------------
def recent(events: list[dict], days: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - pd.Timedelta(days=days)).isoformat()
    return [e for e in events if e["ts"] >= cutoff]


def _sort_key(e: dict):
    return (e["ts"], -_SEV_RANK.get(e["severity"], 9))


def group_by_day(events: list[dict]) -> list[dict]:
    """Most-recent-day-first groups, each with a bilingual date header and its
    events ordered high-severity-first within the day."""
    by_day: dict[str, list[dict]] = {}
    for e in events:
        by_day.setdefault(e["ts"][:10], []).append(e)
    out = []
    for day in sorted(by_day, reverse=True):
        ts = pd.Timestamp(day)
        evs = sorted(by_day[day], key=lambda e: _SEV_RANK.get(e["severity"], 9))
        out.append({"date": day,
                    "daylabel": ts.strftime("%b %-d, %Y"),
                    "daylabel_zh": f"{ts.year}年{ts.month}月{ts.day}日",
                    "events": evs})
    return out


# the only event fields the (client-rendered) stock page can't reconstruct:
# `label` comes from `filter`, and `edge`/`forward` from `type` via edge_meta().
_EMBED_KEYS = ("type", "filter", "dir", "pinned", "headline", "headline_zh",
               "detail", "detail_zh")


def _slim(ev: dict) -> dict:
    return {k: ev[k] for k in _EMBED_KEYS if k in ev}


def compact_feed(feed: dict) -> dict:
    """Slim a feed for embedding in a stockdata JSON — drop everything the client
    reconstructs (static conviction text repeated across events), keeping only the
    dynamic headline/detail + classification. Cuts ~40% off each ticker JSON."""
    if not feed:
        return {"pinned": None, "timeline": [], "n_recent": 0, "n_total": 0}
    pinned = _slim(feed["pinned"]) if feed.get("pinned") else None
    timeline = [{"daylabel": d["daylabel"], "daylabel_zh": d["daylabel_zh"],
                 "events": [_slim(e) for e in d["events"]]}
                for d in feed.get("timeline", [])]
    return {"pinned": pinned, "timeline": timeline,
            "n_recent": feed.get("n_recent", 0), "n_total": feed.get("n_total", 0)}


def edge_meta() -> dict:
    """type -> {edge, edge_zh, forward, forward_zh}, embedded ONCE in the stock
    page so slimmed events can show their conviction note (mirrors META)."""
    return {k: {"edge": v.get("edge", ""), "edge_zh": v.get("edge_zh", ""),
                "forward": v.get("forward", ""), "forward_zh": v.get("forward_zh", "")}
            for k, v in META.items()}


def build_feed(asset: str, close: pd.Series, high: pd.Series | None,
               bench: pd.Series | None, ladder: dict | None, asof: str | None,
               days: int = 120, max_events: int = 50,
               persist: bool = False) -> dict:
    """Assemble one asset's feed.

    Returns ``{pinned, timeline, n_recent, n_total}``:
      pinned    — the ladder's current standing read (or None) for the top card
      timeline  — recent technical + past-ladder events, grouped by day
      n_recent  — count of events in the recent window (the toggle badge)
    Never raises — any failure yields an empty feed so a page build can't break.
    """
    try:
        if persist:
            append_ladder_log(asset, ladder, asof)
        pinned = ladder_pinned(asset, ladder, asof)
        when = (ladder or {}).get("signal_date") or asof
        events = technical_events(asset, close, high, bench)
        events += ladder_history_events(asset, exclude_when=when)
        # de-dup by id, keep deterministic order
        by_id = {e["id"]: e for e in events}
        allev = sorted(by_id.values(), key=_sort_key, reverse=True)
        win = recent(allev, days)[:max_events]
        return {"pinned": pinned, "timeline": group_by_day(win),
                "n_recent": len(win), "n_total": len(allev)}
    except Exception as e:  # noqa: BLE001 — the feed is additive, never fatal
        log.warning("ticker_alerts.build_feed(%s) failed: %s", asset, e)
        return {"pinned": None, "timeline": [], "n_recent": 0, "n_total": 0}
