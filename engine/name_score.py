"""Per-name POTENTIAL score — a market-aware confluence / timing (buy-readiness) screen.

The unified "is this name set up to rise FROM HERE, and can I act on it now?" score
across every market. It answers the front-running question the user asks, instead of
a lagging within-market percentile or a reversal rank that crowned the most beaten-down
name. The legs combine as GATES, not an average, so a single deep-washout reading can
never carry a name that is still falling:

    score = 100 · trigger · (0.4 + 0.6·fuel) · survive · tailwind · confidence · edge_mult

  * trigger   — is the turn happening NOW (cycle ladder, gated by the entry gauge).
                A confirmed FRESH BUY clusters high; a still-declining knife gates to ~0.
                The trigger decides the TIER (the front-running / trend-following core).
  * fuel      — stored upside (off the 52w high + below the 200dma). Sizes WITHIN the
                tier (0.4 floor so a clean shallow-dip fresh buy stays actionable).
  * survive   — subtract-only distress haircut (crowding / panic-vol). Never a booster.
  * tailwind  — bounded theme / regime tilt (re-orders within a tier).
  * confidence— bounded forward anticipation-cone nudge (favourable shape; honest:
                ordering lever, direction ~coin-flip).
  * edge_mult — THE per-market validated-selection-edge blend (PRESERVES each market's
                real alpha). For US/CA/INTL the name's selection-axis z (US = the
                event edge: insider buying / earnings-surprise / analyst revisions; CA/
                INTL = a residual-momentum prior) tilts the score ±, so a washed-out
                turning name that ALSO has insider buying outranks an identical one with
                none — front-running timing AND validated edge, not one at the cost of the
                other. CN/HK have no validated cross-sectional name edge, so edge_mult=1
                (CN's reversal edge already lives in the washout/cycle).

HONEST CEILING: this is a TIMING + RISK + (where present) EDGE screen for entry, vol-
sized and forward-graded — never an alpha oracle. CN name selection has no proven
forward return-alpha (rank-IC ~0); the US event edge is real but small. The companion
grader (engine/name_score_grader) measures it forward by market so it earns trust.
See [[china-name-potential-score]], [[stock-conviction-profile]],
[[china-hk-selection-alpha-reality]].
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
# (FRESH BUY) opens the window now; a name still declining gates to 0 even if it is
# the most oversold on the board (the knife a reversal percentile used to reward).
_TRIGGER = {
    "FRESH BUY": 1.00, "TURN SIGNALED": 0.92,
    "RALLY ON": 0.70,            # uptrend intact — buy dips, but past the low
    "BOTTOM WATCH": 0.50,        # basing — get ready, not yet turned
    "COUNTERTREND BOUNCE": 0.30,  # a bounce inside a downtrend — suspect
    "TOP WATCH": 0.15,           # extended — don't chase
    "ROLLING OVER": 0.05, "DECLINE": 0.00,
}
_ENTRY_CONFIRM = {"buy_now": 1.00, "wait_pullback": 0.88, "hold": 0.90,
                  "extended": 0.50, "later": 0.80,
                  # bounce_wait = the COUNTERTREND BOUNCE wording split off 'extended'
                  # (regime gate: daily buy fired, weekly unconfirmed). 0.50 kept
                  # DELIBERATELY: the halving prices "turn not confirmed", not extension,
                  # and _TRIGGER already discounts the state to 0.30 — so the split moves
                  # no published score. Omitting the key would default to 1.0 and double it.
                  "bounce_wait": 0.50}

# (cutoff, css_band_key, tier, EN words, 中文 words). css_band_key REUSES the existing
# conviction colour scale (high=green … low=grey) so no template/CSS change is needed.
_BANDS = [(70, "high", "primed", "Primed", "蓄势待发"),
          (45, "constructive", "setting_up", "Setting up", "正在筑底"),
          (25, "neutral", "watch", "Watch", "观察"),
          (0, "low", "no_setup", "No setup", "暂无买点")]

_HIGH_FULL = 35.0      # -35% off the high = full drawdown fuel
_MA_FULL = 20.0        # -20% below the 200dma = full below-trend fuel

# per-market validated-selection-edge blend: (K, lo, hi). A positive edge z lifts the
# score, a negative edge (insider selling / negative revisions) trims it. K scales with
# how VALIDATED the market's edge is; CN/HK get no blend (no validated name edge).
_EDGE_BLEND = {
    "US":   (0.20, 0.70, 1.35),   # real event edge (insider / SUE / revisions)
    "CA":   (0.12, 0.82, 1.20),   # residual-momentum prior (unvalidated)
    "INTL": (0.12, 0.82, 1.20),
    "HK":   (0.0, 1.0, 1.0),      # relative-strength SCREEN only — no validated edge
    "CN":   (0.0, 1.0, 1.0),      # reversal edge already lives in the washout / cycle
}
_EDGE_LABEL = {"US": ("insider / earnings / revision edge", "内幕 / 业绩 / 评级修正优势"),
               "CA": ("momentum prior", "动量先验"),
               "INTL": ("momentum prior", "动量先验")}


def _fuel(tech: dict) -> tuple[float, list[str]]:
    off_high = _f(tech.get("off_52w_high_pct"))
    vs200 = _f(tech.get("pct_vs_200dma"))
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
    mult = 1.0
    why: list[str] = []
    frag = rec.get("fragility") or rec.get("margin_crowd") or {}
    if isinstance(frag, dict) and (frag.get("flag") or frag.get("crowded")):
        mult *= 0.78
        why.append("crowded / fragile — fire-sale risk")
    if regime_stress and regime_stress > 0:
        mult *= _clip(1.0 - 0.20 * regime_stress, 0.8, 1.0)
        why.append("stressed tape — size down")
    return _clip(mult, 0.6, 1.0), why


def _tailwind(rec: dict, basket_ctx: dict | None) -> tuple[float, list[str]]:
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


def _edge_mult(market: str, edge_z: float | None) -> tuple[float, list[str]]:
    """The per-market validated-edge blend — preserves each market's real alpha."""
    k, lo, hi = _EDGE_BLEND.get(market, (0.0, 1.0, 1.0))
    z = _f(edge_z)
    if k == 0.0 or z is None:
        return 1.0, []
    mult = _clip(1.0 + k * _clip(z, -3.0, 3.0), lo, hi)
    why: list[str] = []
    lbl = _EDGE_LABEL.get(market, ("selection edge", "选股优势"))
    if mult >= 1.05:
        why.append(f"backed by a {lbl[0]}")
    elif mult <= 0.95:
        why.append(f"{lbl[0]} leans against it")
    return mult, why


def _band(score: int) -> dict:
    for lo, css, tier, en, zh in _BANDS:
        if score >= lo:
            return {"band": css, "tier": tier, "band_en": en, "band_zh": zh}
    lo, css, tier, en, zh = _BANDS[-1]
    return {"band": css, "tier": tier, "band_en": en, "band_zh": zh}


def potential_score(rec: dict, *, market: str = "CN", edge_z: float | None = None,
                    regime_stress: float = 0.0, basket_ctx: dict | None = None) -> dict:
    """Per-name POTENTIAL (buy-readiness) score 0-100 + tier + components + reasoning.

    A high score means: washed out (room) AND turning up now (actionable) AND survivable
    AND — where a market has one — carrying its validated selection edge. The trigger
    gates the tier (front-running / trend-following); fuel sizes within it; edge_mult
    blends each market's real alpha. ``edge_z`` is the name's selection-axis z (pass the
    conviction selection z); ``market`` selects the edge blend. CN/HK ignore edge_z.
    """
    m = (market or "CN").upper()
    fuel, fw = _fuel(rec.get("tech") or {})
    trig, tw = _trigger(rec)
    surv, sw = _survive(rec, regime_stress)
    tail, lw = _tailwind(rec, basket_ctx)
    conf, cw = _confidence(rec)
    emult, ew = _edge_mult(m, edge_z)

    raw = trig * (0.4 + 0.6 * fuel) * surv * tail * conf * emult
    score = int(round(_clip(100.0 * raw, 0.0, 100.0)))
    band = _band(score)

    reasoning = [*tw, *ew, *fw, *sw, *lw, *cw]   # trigger first (the actionable leg), then edge
    return {
        "score": score,
        "band": band["band"], "tier": band["tier"],
        "band_en": band["band_en"], "band_zh": band["band_zh"],
        "components": {"fuel": round(fuel, 3), "trigger": round(trig, 3),
                       "survive": round(surv, 3), "tailwind": round(tail, 3),
                       "confidence": round(conf, 3), "edge": round(emult, 3)},
        "reasoning": reasoning,
        "call": {"ticker": rec.get("ticker"), "score": score, "tier": band["tier"],
                 "fuel": round(fuel, 3), "trigger": round(trig, 3)},
    }
