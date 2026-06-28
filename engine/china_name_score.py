"""China A-share per-name POTENTIAL score — a confluence / timing screen.

Replaces the old "reversal percentile" (the within-market percentile of a
reversal-led composite, which ranked the MOST BEATEN-DOWN name highest — the
-33%-off-high name scored 93) with a score that answers the question the user
actually asks: *is this name set up to rise FROM HERE, and can I act on it now?*

The score is a CONFLUENCE of legs combined as GATES, not an average, so a
single deep-washout reading can never carry a name that is still falling:

    score = 100 · trigger · (0.4 + 0.6·fuel) · survive · tailwind · confidence

The TRIGGER (is the turn happening now) is a pure gate that decides the tier — a
confirmed FRESH BUY clusters high, a still-declining knife gates to ~0. FUEL (how
deep the washout) only sizes the score WITHIN that tier (a 0.4 floor so a clean
fresh buy on a shallow dip still reads actionable), so depth is the tiebreaker,
never the headline.

  * fuel      — stored upside (how far below trend / off the high). The washout
                IS the validated A-share edge (mean-reversion); deep = room to run,
                extended-at-a-high = ~0. This is the MAGNITUDE.
  * trigger   — is the turn happening NOW (the cycle ladder). THE key inversion:
                washed-out-but-still-DECLINING gates to ~0 (a knife), washed-out-
                and-FRESH-BUY gates to 1.0. This is what makes a high score a BUY,
                not just a candidate.
  * survive   — subtract-only haircut for distress (margin-crowding fire-sale risk,
                a panic QVIX tape). Never a booster.
  * tailwind  — small bounded tilt from the name's narrative-basket / regime state
                (the "is the theme in play" context). Asymmetric: re-orders within
                a tier, never manufactures a buy.
  * confidence— bounded nudge from the forward anticipation cone (favourable upside/
                downside SHAPE). Honest: the cone is a drawdown / ordering lever, its
                direction is ~coin-flip, so it only re-orders WITHIN a tier.

HONEST CEILING: A-share cross-sectional NAME selection has no proven forward
return-alpha (allocation audit: rank-IC ~0; reversal is short-horizon, high
variance). So a high score is a TIMING + RISK screen for entry WITHIN a theme you
already want — vol-sized, forward-graded — NOT an alpha oracle. The companion
grader (engine/china_name_score_grader) measures it forward so it earns trust
(or admits it has none). See [[china-hk-selection-alpha-reality]],
[[china-sector-cycles-project]], [[stock-conviction-profile]].
"""
from __future__ import annotations


def _f(x):
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def _clip(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


# cycle-state -> trigger gate. The turn is the trigger: a confirmed cycle low
# (FRESH BUY) opens the window now; a name still declining gates to 0 even if it
# is the most oversold name on the board (the knife the old percentile rewarded).
_TRIGGER = {
    "FRESH BUY": 1.00, "TURN SIGNALED": 0.92,
    "RALLY ON": 0.70,            # uptrend intact — buy dips, but past the low
    "BOTTOM WATCH": 0.50,        # basing — get ready, not yet turned
    "COUNTERTREND BOUNCE": 0.30,  # a bounce inside a downtrend — suspect
    "TOP WATCH": 0.15,           # extended — don't chase
    "ROLLING OVER": 0.05, "DECLINE": 0.00,
}
# the entry-timing gauge CONFIRMS / tempers the cycle trigger (multiplicative).
_ENTRY_CONFIRM = {"buy_now": 1.00, "wait_pullback": 0.88, "hold": 0.90,
                  "extended": 0.50, "later": 0.80}

# (cutoff, css_band_key, tier, EN words, 中文 words). The css_band_key REUSES the
# existing conviction colour scale (high=green … low=grey) so no template/CSS change
# is needed; the WORDS carry the new buy-readiness meaning.
_BANDS = [(70, "high", "primed", "Primed", "蓄势待发"),
          (45, "constructive", "setting_up", "Setting up", "正在筑底"),
          (25, "neutral", "watch", "Watch", "观察"),
          (0, "low", "no_setup", "No setup", "暂无买点")]

# washout normalisers — drawdown from the 52w high is the cleaner "stored upside"
# measure (weighted higher); distance below the 200dma confirms it.
_HIGH_FULL = 35.0      # -35% off the high = full drawdown fuel
_MA_FULL = 20.0        # -20% below the 200dma = full below-trend fuel


def _fuel(tech: dict) -> tuple[float, list[str]]:
    """Stored upside in [0,1] — how much room the name has to recover. Extended
    (at/above the high, above the 200dma) -> ~0; deeply washed out -> ~1."""
    off_high = _f(tech.get("off_52w_high_pct"))     # <= 0 (pct below the 52w high)
    vs200 = _f(tech.get("pct_vs_200dma"))           # +/- % vs the 200dma
    nh = _clip((-off_high) / _HIGH_FULL, 0.0, 1.0) if off_high is not None else 0.0
    nm = _clip((-vs200) / _MA_FULL, 0.0, 1.0) if vs200 is not None else 0.0
    fuel = 0.6 * nh + 0.4 * nm
    why: list[str] = []
    if off_high is not None and off_high <= -15:
        why.append(f"{off_high:.0f}% off its high — room to recover")
    if vs200 is not None and vs200 <= -8:
        why.append(f"{vs200:.0f}% below its 200-day — washed out")
    if off_high is not None and off_high >= -3 and vs200 is not None and vs200 >= 12:
        why.append("at/near a high and stretched above trend — little room left")
    return _clip(fuel, 0.0, 1.0), why


def _trigger(rec: dict) -> tuple[float, list[str]]:
    """Is the up-turn happening now, in [0,1] — the cycle ladder gated by the
    entry-timing gauge. A still-declining tape gates the whole score toward 0."""
    lad = rec.get("ladder") or {}
    state = (lad.get("state") or "").upper()
    base = _TRIGGER.get(state, 0.4)
    es = (rec.get("entry_signal") or {}).get("status")
    conf = _ENTRY_CONFIRM.get(es, 1.0)
    trig = base * conf
    why: list[str] = []
    if base >= 0.9:
        why.append(f"cycle turning up now ({lad.get('label') or state})")
    elif base <= 0.05:
        why.append(f"still in a down-leg ({lad.get('label') or state}) — no trigger")
    elif state == "BOTTOM WATCH":
        why.append("basing near a low — not yet turned")
    elif state == "TOP WATCH":
        why.append("extended near a high — wait for a pullback")
    if es == "extended":
        why.append("entry gauge: extended")
    return _clip(trig, 0.0, 1.0), why


def _survive(rec: dict, regime_stress: float) -> tuple[float, list[str]]:
    """Subtract-only survivability haircut in [0.6,1.0]: crowded-margin fire-sale
    risk + a panic QVIX tape. Never a booster."""
    mult = 1.0
    why: list[str] = []
    frag = rec.get("fragility") or rec.get("margin_crowd") or {}
    if isinstance(frag, dict) and (frag.get("flag") or frag.get("crowded")):
        mult *= 0.78
        why.append("crowded margin financing — fire-sale risk")
    if regime_stress and regime_stress > 0:
        mult *= _clip(1.0 - 0.20 * regime_stress, 0.8, 1.0)
        why.append("stressed (QVIX) tape — size down")
    return _clip(mult, 0.6, 1.0), why


def _tailwind(rec: dict, basket_ctx: dict | None) -> tuple[float, list[str]]:
    """Bounded theme/regime tilt in [0.85,1.15]. Prefers an explicit viewing-basket
    context (the sector-cycle state of the basket the name is shown in); else the
    name's own primary narrative-basket alloc state. Asymmetric in spirit — a
    below-trend / fading theme trims, an in-play one lifts modestly."""
    tilt = 0.0
    why: list[str] = []
    ctx = basket_ctx or {}
    ba = rec.get("basket_alloc") or {}
    label = (ctx.get("label") or ba.get("label") or "").lower()
    above = ctx.get("above_trend")
    if above is None:
        above = ba.get("above_trend")
    if ctx.get("emerging") or label in ("emerging", "leading", "accumulate"):
        tilt += 0.10
        why.append("theme in play (emerging/leading)")
    if above is True:
        tilt += 0.05
    if above is False or label in ("fading", "deteriorating"):
        tilt -= 0.12
        why.append("theme below trend / fading — de-risk")
    if ba.get("crowded") or ctx.get("crowded"):
        tilt -= 0.06
        why.append("theme crowded — cap size")
    sp = rec.get("spotlight")
    if isinstance(sp, dict):
        d = sp.get("dir")
        if d == "up":
            tilt += 0.04
        elif d == "down":
            tilt -= 0.06
    return _clip(1.0 + tilt, 0.85, 1.15), why


def _confidence(rec: dict) -> tuple[float, list[str]]:
    """Bounded forward-cone nudge in [0.9,1.1] from the anticipation index — a
    favourable upside/downside SHAPE re-orders within a tier. Honest: the cone is
    a drawdown / ordering lever (direction ~coin-flip), so it is deliberately
    weak and never gates."""
    ant = rec.get("anticipation") or {}
    idx = _f(ant.get("anticipation_index"))
    if idx is None:
        return 1.0, []
    conf = 0.9 + 0.2 * _clip(idx / 100.0, 0.0, 1.0)
    why: list[str] = []
    hz = (ant.get("horizons") or {}).get("medium") or {}
    mfe, dd = _f(hz.get("mfe_med")), _f(hz.get("dd_avg"))
    if idx >= 60 and mfe and dd and dd != 0 and (mfe / abs(dd)) >= 1.3:
        why.append(f"favourable forward cone (~{mfe:.0f}% up vs ~{abs(dd):.0f}% drawdown)")
    return _clip(conf, 0.9, 1.1), why


def _band(score: int) -> dict:
    for lo, css, tier, en, zh in _BANDS:
        if score >= lo:
            return {"band": css, "tier": tier, "band_en": en, "band_zh": zh}
    lo, css, tier, en, zh = _BANDS[-1]
    return {"band": css, "tier": tier, "band_en": en, "band_zh": zh}


def potential_score(rec: dict, *, regime_stress: float = 0.0,
                    basket_ctx: dict | None = None) -> dict:
    """The per-name POTENTIAL score (0-100) + tier + components + reasoning trace.

    ``rec`` is the same normalized/per-stock record the conviction engine consumes
    (ladder / tech / entry_signal / anticipation / fragility / basket_alloc /
    spotlight). ``regime_stress`` is the live QVIX stress in [0,1]; ``basket_ctx``
    optionally carries the VIEWING basket's sector-cycle state so a name shown on a
    hot basket page is tilted by THAT theme, not only its own primary basket.

    A high score means: washed out (room to run) AND turning up now (actionable)
    AND survivable AND in a theme with wind at its back — a buy with real potential
    from here, NOT "the most fallen". Forward-graded; framed as a timing screen.
    """
    fuel, fw = _fuel(rec.get("tech") or {})
    trig, tw = _trigger(rec)
    surv, sw = _survive(rec, regime_stress)
    tail, lw = _tailwind(rec, basket_ctx)
    conf, cw = _confidence(rec)

    # trigger gates the tier; fuel sizes WITHIN it (0.4 floor so a clean fresh buy
    # on a shallow dip still reads actionable, not crushed by a low washout reading).
    raw = trig * (0.4 + 0.6 * fuel) * surv * tail * conf
    score = int(round(_clip(100.0 * raw, 0.0, 100.0)))
    band = _band(score)

    reasoning = [*tw, *fw, *sw, *lw, *cw]   # trigger first (the actionable leg)
    return {
        "score": score,
        "band": band["band"],            # css colour key (high/constructive/neutral/low)
        "tier": band["tier"],            # semantic (primed/setting_up/watch/no_setup)
        "band_en": band["band_en"], "band_zh": band["band_zh"],
        "components": {"fuel": round(fuel, 3), "trigger": round(trig, 3),
                       "survive": round(surv, 3), "tailwind": round(tail, 3),
                       "confidence": round(conf, 3)},
        "reasoning": reasoning,
        # the dated call the forward-grader logs (kept-first per date,ticker)
        "call": {"ticker": rec.get("ticker"), "score": score, "tier": band["tier"],
                 "fuel": round(fuel, 3), "trigger": round(trig, 3)},
    }
