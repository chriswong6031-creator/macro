"""Event-risk visibility — a NON-DIRECTIONAL attention flag for known high-impact
calendar events (FOMC / CPI / jobs / GDP / PCE / PPI), upgraded when the tape is
walking in fragile.

DISCIPLINE (honors engine/event_calendar.py + research/DATA_SIGNAL_EXPANSION_2026.md #11):
this is NOT an event-risk score and NOT a conviction dampener. Pre-FOMC drift died
after 2016 and the Savor-Wilson announcement premium is *positive*, so cutting exposure
into these days is wrong-signed. Therefore this layer:
  • NEVER predicts direction (outcomes resolve up about as often as down — it says so);
  • NEVER cuts exposure or feeds any score (display / context only, is_context_only);
  • only states: a high-impact catalyst is near, realized vol is typically elevated, so
    size / stops should reflect two-sided event noise.

The optional FRAGILITY OVERLAY is the genuinely new bit: it couples the known event
date with the dashboard's already-measured fragility (broken stock-bond hedge,
one-bet concentration, a stretched rate-path gap, an active turning-point caution) to
say "you are walking into this event positioned fragile" — still non-directional.
"""
from __future__ import annotations

from datetime import date

# Typical 1-day |S&P 500| move around the event and historical up-rate (approximate,
# long-run ballparks — DISPLAY calibration only, never a forecast). up_rate near 0.5
# is the whole point: these are two-sided.
_HIST: dict[str, dict] = {
    "FOMC": {"typ_abs": 0.9, "up_rate": 0.54},
    "CPI":  {"typ_abs": 0.9, "up_rate": 0.51},
    "NFP":  {"typ_abs": 0.8, "up_rate": 0.55},
    "PCE":  {"typ_abs": 0.5, "up_rate": 0.54},
    "GDP":  {"typ_abs": 0.5, "up_rate": 0.53},
    "PPI":  {"typ_abs": 0.4, "up_rate": 0.52},
}


def _vol_tier(typ_abs: float) -> str:
    if typ_abs >= 0.7:
        return "high"
    if typ_abs >= 0.4:
        return "elevated"
    return "normal"


def _find(obj, key):
    """First value for `key` anywhere in a nested dict/list (defensive read)."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _find(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find(v, key)
            if r is not None:
                return r
    return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fragility(latest: dict) -> dict:
    """Read the dashboard's already-measured fragility from latest.json (no new math).
    Returns {fragile, score, reasons[]} — score = count of fired fragility legs."""
    latest = latest or {}
    reasons: list[dict] = []

    tp = latest.get("turning_point") or {}
    if tp.get("present"):
        reasons.append({"en": "turning-point caution active (one-factor tape + macro shock + stretched)",
                        "zh": "转折点警示已激活（单因子盘面 + 宏观冲击 + 拉伸）"})

    ca = latest.get("cross_asset") or {}
    abss = _num(ca.get("absorption_pctile_5y"))
    if abss is not None and abss >= 0.85:
        pct = round(abss * 100)
        reasons.append({"en": f"cross-asset concentration extreme (absorption {pct}th pctile) — moves compound, not diversify",
                        "zh": f"跨资产高度集中（吸收比率 {pct} 分位）——下挫叠加而非分散"})

    sbc = _num(_find(latest, "stock_bond_corr"))
    if sbc is not None and sbc >= 0.45:
        reasons.append({"en": f"stock-bond hedge broken (corr +{sbc:.2f}) — bonds won't cushion an equity scare",
                        "zh": f"股债对冲失效（相关性 +{sbc:.2f}）——债券无法缓冲股市惊吓"})

    fp = latest.get("fed_path") or {}
    gap = (fp.get("gap") or {})
    gap_bp = _num(gap.get("gap_bp"))
    if gap_bp is not None and abs(gap_bp) >= 20:
        g = round(gap_bp)
        reasons.append({"en": f"rate-path gap stretched ({g:+d} bp vs the Fed) — repricing risk into the print",
                        "zh": f"利率路径错位（较美联储 {g:+d} 个基点）——数据公布前的重定价风险"})

    score = len(reasons)
    return {"fragile": score >= 2, "score": score, "reasons": reasons}


def _days_word(n: int) -> tuple[str, str]:
    if n <= 0:
        return "today", "今天"
    if n == 1:
        return "tomorrow", "明天"
    return f"in {n} days", f"{n} 天后"


def snapshot(latest: dict | None = None, events: list[dict] | None = None,
             today: date | None = None, horizon_days: int = 10) -> dict:
    """Build the event-risk banner dict. Pure + defensive: returns {show: False} when
    no high-impact event is inside the window or inputs are missing.

    `events` should be engine.event_calendar.high_impact_strip()-shaped dicts
    (type/date/label/time_et/md/dow). If None, computed best-effort (network)."""
    today = today or date.today()
    latest = latest or {}

    if events is None:
        try:
            from engine import event_calendar as ec
            events = ec.high_impact_strip(today, horizon_days)
        except Exception:  # noqa: BLE001
            events = []

    # nearest high-impact event at/after today within the window
    nxt, nxt_days = None, None
    for ev in events or []:
        try:
            d = date.fromisoformat(ev["date"])
        except Exception:  # noqa: BLE001
            continue
        dd = (d - today).days
        if 0 <= dd <= horizon_days and (nxt_days is None or dd < nxt_days):
            nxt, nxt_days = ev, dd

    if nxt is None:
        return {"show": False, "is_context_only": True}

    etype = nxt.get("type", "")
    hist = _HIST.get(etype, {"typ_abs": 0.4, "up_rate": 0.5})
    tier = _vol_tier(hist["typ_abs"])
    when_en, when_zh = _days_word(nxt_days)
    frag = fragility(latest)

    label = nxt.get("label", etype)
    md = nxt.get("md", nxt.get("date", ""))
    time_et = nxt.get("time_et", "")
    up_pct = round(hist["up_rate"] * 100)

    headline_en = f"⚠ Event-risk window: {label} {when_en}"
    headline_zh = f"⚠ 事件风险窗口：{label} {when_zh}"
    if nxt_days >= 1:
        headline_en += f" ({md}{(' · ' + time_et + ' ET') if time_et else ''})"
        headline_zh += f"（{md}{(' · ' + time_et + ' ET') if time_et else ''}）"

    sub_en = (f"Realized volatility is typically {tier} around this catalyst "
              f"(historically ~±{hist['typ_abs']:.1f}% on the S&P, up about {up_pct}% of the time). "
              f"Direction is a two-sided coin-flip — this is NOT a sell signal; the announcement "
              f"premium is on average positive. Size for the noise and widen stops; don't add conviction you don't have.")
    sub_zh = (f"该催化剂前后实现波动率通常{('偏高' if tier=='high' else '升高' if tier=='elevated' else '正常')}"
              f"（历史上标普约 ±{hist['typ_abs']:.1f}%，上涨概率约 {up_pct}%）。"
              f"方向是两面性的掷硬币——这不是卖出信号；公告溢价平均为正。按噪声调整仓位、放宽止损，不要凭空增加信心。")

    if frag["fragile"]:
        headline_en = f"⚠ Walking into {label} {when_en} positioned FRAGILE"
        headline_zh = f"⚠ 在仓位脆弱状态下迎接 {label}（{when_zh}）"

    return {
        "show": True,
        "is_context_only": True,
        "type": etype,
        "label": label,
        "md": md,
        "dow": nxt.get("dow", ""),
        "time_et": time_et,
        "days_to": nxt_days,
        "when_en": when_en,
        "when_zh": when_zh,
        "vol_tier": tier,
        "typ_abs": hist["typ_abs"],
        "up_rate": hist["up_rate"],
        "direction": "two-sided",
        "fragility": frag,
        "headline_en": headline_en,
        "headline_zh": headline_zh,
        "sub_en": sub_en,
        "sub_zh": sub_zh,
        "asof": today.isoformat(),
    }
