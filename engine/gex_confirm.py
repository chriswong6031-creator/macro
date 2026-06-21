"""engine/gex_confirm.py — dealer-gamma (GEX) as a **verifier / confirmer** for a long entry.

The board's edge is the SELECTION leg (the name). Options positioning does not pick the name —
it tells you how the *next move* is likely to behave, so it can VERIFY or CAUTION a long entry
that the price thesis already favours. This module turns a joined per-stock GEX payload
(``site/gex/<T>.json`` — regime, gamma-flip distance, call/put walls, ``vol_hole`` state, and
optionally a 25Δ risk-reversal change) into a single discrete verdict:

    CONFIRM · NEUTRAL · CAUTION

following the practitioner + academic recipe (SpotGamma / SqueezeMetrics / Soebhag 2023):

* **Regime** — negative/short gamma AMPLIFIES moves (fuel for a momentum long → confirm);
  positive/long gamma DAMPENS and pins (a breakout gets faded → caution), and the deeper above
  the flip the stronger the pin.
* **Walls** — within ~1σ of the call wall is a mechanical ceiling (caution); clear runway to the
  call wall with put-wall support below is a clean long (confirm).
* **vol_hole state** — COILED_UP is armed-to-release-up; EXPANSION is elevated realized vol;
  IN_HOLE is pinned.
* **Skew** — use the 25Δ risk-reversal *change*, never the level (equity skew is structurally
  negative). Flattening = put hedges unwinding (upward pressure); steepening = protection bid.
  Dormant until the GEX history accrues an ``rr_25d`` series — honest, never fabricated.
* **OPEX** — in the 2 sessions before monthly expiry, charm/vanna flows dominate; the verdict is
  forced to NEUTRAL ("wait for the post-OPEX session").

Two hard rules, matching both the research and the board's honesty doctrine:
1. **EXCLUDE raw charm and the absolute skew level** — they are structurally bearish and would
   make any tilt permabearish.
2. **A confirmer can only LOWER confidence**, never manufacture a buy. The engine applies this as
   a small bounded tilt and only on names the price thesis already likes; CAUTION never rescues
   and CONFIRM never overrides an AVOID / over-extended name.

Pure function; consumes the public payload shape so it is trivially testable.
"""
from __future__ import annotations

DEFAULTS = {
    "min_strikes": 6,           # options-liquidity gate
    "deep_flip_pct": 3.0,       # spot this far above the flip = deeply pinned long gamma
    "shallow_flip_pct": 1.0,    # spot this close above the flip = fragile (a dip flips it short)
    "wall_near_sigma": 1.0,     # within this many daily-σ of the call wall = ceiling
    "wall_far_sigma": 2.5,      # at least this far from the call wall = runway
    "rr_move": 0.5,             # 25Δ RR change (vol pts) that counts as a real skew shift
    "opex_suppress_days": 2,    # sessions before monthly OPEX where the verdict is NEUTRAL
    "confirm_at": 1.0,          # net score >= this -> CONFIRM
    "caution_at": -1.0,         # net score <= this -> CAUTION
}

_LABEL = {
    "confirm": ("Options confirm", "期权确认"),
    "neutral": ("Options neutral", "期权中性"),
    "caution": ("Options caution", "期权警示"),
}
_CAVEAT = ("Dealer-gamma confirmer — context for HOW the next move behaves, not a name pick. "
           "Dealer sign is an assumption (fragile for single names) and the feed is delayed EOD. "
           "It can only lower conviction, never create a buy.")
_CAVEAT_ZH = ("做市商 Gamma 确认器 — 用于判断下一步波动的“方式”，并非选股。做市商方向为假设"
              "（对个股较脆弱），数据为延迟收盘。它只能降低信心，绝不制造买入信号。")


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if (v != v) else v   # NaN-safe


def _normalize(gex: dict) -> dict | None:
    """Accept either the rich {summary, vol_hole, expected_move} payload or a flat summary
    that carries a nested vol_hole; return a flat field dict, or None if unusable."""
    if not gex:
        return None
    summ = gex.get("summary") if isinstance(gex.get("summary"), dict) else gex
    vh = gex.get("vol_hole") or summ.get("vol_hole") or {}
    return {
        "tier": summ.get("tier"),
        "n_strikes": summ.get("n_strikes"),
        "regime": summ.get("regime") or summ.get("gamma_regime"),   # rich vs flat field name
        "spot": _f(summ.get("spot")),
        "flip": _f(summ.get("gamma_flip")),
        "dist_to_flip_pct": _f(summ.get("dist_to_flip_pct")),
        "call_wall": _f(summ.get("call_wall")),
        "put_wall": _f(summ.get("put_wall")),
        "vh_state": vh.get("state"),
        "to_upper_sigma": _f(vh.get("to_upper_sigma")),
        "to_lower_sigma": _f(vh.get("to_lower_sigma")),
    }


def assess(gex: dict, *, direction: str = "up", opex_days: int | None = None,
           rr_change: float | None = None, cfg: dict | None = None) -> dict | None:
    """Return the GEX confirmer block for a LONG entry, or None when options are too thin.

    ``direction`` is the stock's own price thesis ('up' for the standard long confirmer;
    'down' caps the verdict so options can never *confirm* a long on a falling name).
    ``opex_days`` = sessions until the next monthly OPEX (suppresses to NEUTRAL when imminent).
    ``rr_change`` = recent change in the 25Δ risk-reversal (vol pts), or None (dormant)."""
    cf = {**DEFAULTS, **(cfg or {})}
    g = _normalize(gex)
    if g is None or g["tier"] in (None, "no_options"):
        return None
    if g["n_strikes"] is not None and g["n_strikes"] < cf["min_strikes"]:
        return None

    score = 0.0
    reasons: list[dict] = []

    def add(pts: float, en: str, zh: str, tone: str) -> None:
        nonlocal score
        score += pts
        reasons.append({"en": en, "zh": zh, "tone": tone})

    # ---- 1. gamma regime ---------------------------------------------------
    regime = g["regime"]
    d = g["dist_to_flip_pct"]
    if regime == "short":
        add(1.0, "negative-gamma tape — dealer hedging amplifies the move (fuel for a breakout)",
            "负 Gamma 行情 — 做市商对冲放大波动（利于突破）", "confirm")
    elif regime == "long":
        if d is not None and abs(d) >= cf["deep_flip_pct"]:
            add(-1.0, f"deep long-gamma (+{abs(d):.1f}% over the flip) — dealers pin & fade breakouts",
                f"深度多头 Gamma（高于翻转位 +{abs(d):.1f}%）— 做市商钉价、压制突破", "caution")
        elif d is not None and abs(d) <= cf["shallow_flip_pct"]:
            add(0.0, "just above the gamma flip — supportive but fragile (a dip flips dealers short)",
                "刚高于 Gamma 翻转位 — 有支撑但脆弱（回调即转为空头 Gamma）", "neutral")
        else:
            add(-0.5, "long-gamma — dealer hedging dampens the move",
                "多头 Gamma — 做市商对冲抑制波动", "caution")

    # ---- 2. call-wall proximity (the ceiling for a long) -------------------
    tu, tl = g["to_upper_sigma"], g["to_lower_sigma"]
    if tu is not None and tu <= cf["wall_near_sigma"]:
        cw = g["call_wall"]
        add(-1.0, (f"within ~1σ of the call wall ({cw:g}) — mechanical resistance overhead"
                   if cw else "within ~1σ of the call wall — mechanical resistance overhead"),
            (f"接近 Call 墙（{cw:g}）约 1σ 以内 — 上方有机械阻力" if cw
             else "接近 Call 墙约 1σ 以内 — 上方有机械阻力"), "caution")
    elif tu is not None and tu >= cf["wall_far_sigma"] and (tl is not None and tl <= 2.0):
        add(0.5, "clear runway to the call wall with put-wall support below",
            "上行至 Call 墙空间充裕，下方有 Put 墙支撑", "confirm")

    # ---- 3. vol_hole state -------------------------------------------------
    vhs = g["vh_state"]
    if vhs == "COILED_UP":
        add(0.5, "armed at the upper gamma band — a close above releases the move up",
            "在上沿 Gamma 带蓄势 — 收盘突破即向上释放", "confirm")
    elif vhs == "COILED_DOWN":
        add(-0.5, "armed at the lower gamma band — a close below releases a downside move",
            "在下沿 Gamma 带蓄势 — 收盘跌破即向下释放", "caution")
    elif vhs == "EXPANSION":
        add(-0.5, "short-gamma expansion — realized vol elevated, no suppressive band",
            "空头 Gamma 扩张 — 已实现波动升高，无抑制带", "caution")

    # ---- 4. 25Δ risk-reversal CHANGE (level is excluded; dormant when None) -
    if rr_change is not None:
        if rr_change >= cf["rr_move"]:
            add(0.5, "downside skew flattening — put hedges unwinding (upward pressure)",
                "下行偏斜走平 — 看跌对冲平仓（上行压力）", "confirm")
        elif rr_change <= -cf["rr_move"]:
            add(-0.5, "downside skew steepening — protection being bid",
                "下行偏斜变陡 — 保护性看跌被买入", "caution")

    # ---- direction guard: a long confirmer can't be positive on a falling name
    if direction == "down" and score > 0:
        score = 0.0

    # ---- OPEX suppression (overrides to NEUTRAL) ---------------------------
    opex_suppressed = (opex_days is not None and 0 <= opex_days <= cf["opex_suppress_days"])
    if opex_suppressed:
        verdict = "neutral"
        reasons.append({
            "en": f"within {opex_days}d of monthly OPEX — charm/vanna flows dominate; wait for post-OPEX",
            "zh": f"距月度期权到期 {opex_days} 天 — charm/vanna 资金流主导；等到期后再确认",
            "tone": "neutral"})
    else:
        verdict = ("confirm" if score >= cf["confirm_at"]
                   else "caution" if score <= cf["caution_at"] else "neutral")

    en, zh = _LABEL[verdict]
    return {
        "verdict": verdict, "score": round(score, 2),
        "label": en, "label_zh": zh,
        "reasons": reasons[:3],
        "levels": {"flip": g["flip"], "call_wall": g["call_wall"],
                   "put_wall": g["put_wall"], "vol_hole_state": vhs,
                   "regime": regime},
        "opex_days": opex_days, "opex_suppressed": opex_suppressed,
        "caveat": _CAVEAT, "caveat_zh": _CAVEAT_ZH,
    }
