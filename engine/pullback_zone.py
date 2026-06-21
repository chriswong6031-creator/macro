"""Pullback buy-zone — turn "Extended — don't chase" into a concrete, actionable LEVEL.

Move 3 of the leader-vs-extension compromise. The board correctly refuses to chase a name that
is >=30% above its 200d MA (engine/stock_score `_STRETCH_BLOCK`, validated: that cohort has the
worst forward returns + deepest drawdowns) or parabolic vs its own history — the verdict reads
"Extended — don't chase; wait for a pullback". But it stops there: it names no PRICE, so a user
who wants the leader is just told "no". This module emits the actual pullback levels, so the
trade becomes "wait for $X", not "give up".

The key, self-contained insight: the buy-zone's DEPTH is itself the leader-vs-chase discriminator.
  * A leader extended WITH a moderately-hot move (~+30–45% over its 200d) pulls back a few
    percent to its rising 50d / the "out of the chase zone" line — a timeable entry → ACCUMULATE.
  * A parabolic blow-off (+100%+ over its 200d, or own-history parabolic) would have to fall
    20–60% to leave the chase zone — that is a different regime, not a pullback → CHASE (no
    dip-buy; a 50d bounce is still a chase).

DISPLAY-ONLY. The levels are price arithmetic off the 50d/200d the page already shows; never a
return claim, never scored, never gates the rank. It is the actionable companion to the validated
brake, not a new edge. All from rec['tech'] (price + % vs 50d/200d) — no new data.
"""
from __future__ import annotations

# only meaningful once the name is in the board's own "don't chase" territory, so the zone never
# contradicts a "good entry" verdict: >=30% over the 200d MA (== stock_score._STRETCH_BLOCK) or
# own-history parabolic.
ZONE_MIN = 30.0
WARN_MULT = 1.25          # the 200d × 1.25 line = the board's _STRETCH_WARN (out of the chase zone)
# only frame "wait for a pullback" while the name is still near its highs / above the short trend;
# an extended name already rolling over is a sell the existing verdict handles, not a dip to buy.
NEAR_HIGH = -12.0
# if even the chase-exit line is more than this far below spot, a "pullback" can't reach a
# non-chase price cheaply — it's a regime reset, not a dip → CHASE.
CHASE_DEPTH = -15.0


def _lvl(label_en: str, label_zh: str, price: float, level: float) -> dict:
    return {"label_en": label_en, "label_zh": label_zh,
            "price": round(level, 2), "pull_pct": round((level / price - 1.0) * 100, 1)}


def compute(tech: dict | None, grade: str | None = None,
            downtrend: bool = False) -> dict | None:
    """Pullback buy-zone for an extended name, or None when not in don't-chase territory.

    tech       = rec['tech'] (engine.technicals.snapshot): price, pct_vs_200dma, pct_vs_50dma,
                 off_52w_high_pct, above50.
    grade      = rec['ext']['grade'] (engine.extension): 'parabolic' forces the chase read.
    downtrend  = the cycle ladder dir is 'down' (DECLINE / ROLLING OVER). The zone is the tool
                 for an extended leader STILL in an uptrend ("don't chase, wait for the pullback");
                 on a name already breaking down the existing 'avoid — downtrend' verdict owns it,
                 so we suppress (no accumulate-on-a-downtrend). TOP WATCH (dir 'caution') is the
                 overbought-not-yet-broken case and is kept.
    """
    tech = tech or {}
    price = tech.get("price")
    p200 = tech.get("pct_vs_200dma")
    if price is None or p200 is None or price <= 0 or downtrend:
        return None
    parabolic = grade == "parabolic"
    if not (parabolic or p200 >= ZONE_MIN):
        return None
    # extended-but-rolling-over is a sell, not a dip-to-buy — only the still-leading case gets a
    # zone (parabolic blow-offs always do; they're the headline chase to warn off).
    off_high = tech.get("off_52w_high_pct")
    near_high = off_high is None or off_high >= NEAR_HIGH
    if not parabolic and not (near_high and tech.get("above50")):
        return None

    sma200 = price / (1.0 + p200 / 100.0)
    warn_line = sma200 * WARN_MULT                     # fall to here and you're out of the chase zone
    warn_pull = round((warn_line / price - 1.0) * 100, 1)
    # warn_pull only reads negative once price is >25% over the 200d; parabolic names can be a
    # chase while barely above the 200d, so the parabolic flag carries the chase verdict there.
    stance = "chase" if (parabolic or warn_pull <= CHASE_DEPTH) else "accumulate"

    levels: list[dict] = []
    if stance == "accumulate":
        p50 = tech.get("pct_vs_50dma")
        if p50 is not None:
            sma50 = price / (1.0 + p50 / 100.0)
            if sma50 < price:                          # a rising 50d below spot = the shallow support
                levels.append(_lvl("rising 50-day average", "上升50日均线", price, sma50))
        if warn_line < price:
            levels.append(_lvl("25% over the 200-day (out of the chase zone)",
                               "高于200日均线25%（脱离追高区）", price, warn_line))
    else:                                              # chase — no 50d dip-buy; show the reset level only
        if warn_line < price:
            levels.append(_lvl("25% over the 200-day (out of the chase zone)",
                               "高于200日均线25%（脱离追高区）", price, warn_line))
        elif sma200 < price:                           # parabolic spike not far over its 200d → revert-to-trend
            levels.append(_lvl("back to the 200-day trend", "回到200日趋势", price, sma200))
    if not levels:                                     # nothing actually below spot → no zone to show
        return None
    levels.sort(key=lambda x: -x["price"])             # shallowest (closest below spot) first
    reset_pull = levels[-1]["pull_pct"]                # depth to the deepest (non-chase) level shown

    if stance == "accumulate":
        head_en = ("Don't chase the print — let it come back. Accumulate on a pullback into the "
                   "zone below: the leader you want, at a non-chase price.")
        head_zh = ("勿追当下价位 — 等它回落。回调进入下方区间时分批建仓：你想要的领涨股，以非追高价位。")
    else:
        head_en = (f"Too far above trend to dip-buy — even the non-chase entry sits "
                   f"{abs(reset_pull):.0f}% lower, a different regime rather than a pullback. "
                   f"Wait for the trend to reset, or let it pass.")
        head_zh = (f"远高于趋势，难以逢低买入 — 即便非追高入场点也在低约 {abs(reset_pull):.0f}% 处，"
                   f"是另一种状态而非回调。等趋势重置，或放弃。")
    return {
        "stance": stance,
        "price": round(float(price), 2),
        "levels": levels,
        "shallow_pull": levels[0]["pull_pct"],
        "exit_pull": reset_pull,
        "parabolic": parabolic,
        "headline_en": head_en, "headline_zh": head_zh,
    }
