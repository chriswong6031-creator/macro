"""Playbook: turn the regime + sector data into plain-English, executable
conclusions — with every claim carrying its measured historical stat.

What the 2007->present evidence actually supports (scripts/research_playbook.py;
split-half validated):

1. INDEX-LEVEL RISK is where the regime earns its keep:
   - Fed liquidity expanding was the most robust bullish conditional in BOTH
     halves of the sample (~+1.3-2.0%/21d, 72-74% positive, shallower drawdowns).
   - Q3 (stagflation) was the weakest quad for forward returns in both halves.
   - Risk-off quads (Q3/Q4) ran materially deeper 3-month drawdowns; average
     returns there are flattered by rebounds — the ride is worse, not the mean.
   - Transition warning states preceded weaker near-term returns pre-2017;
     the post-2017 dip-buying era blunted that edge (shown honestly).

2. SECTOR PICKING vs the index has NO stable monthly-horizon edge — signs flip
   across sample halves. What does hold:
   - Chasing extended leaders lost (44.7% hit, -0.6%/3m) -> "don't chase".
   - Buying below-trend bounces lost everywhere (-0.2 to -1.2%) -> "don't
     anticipate; wait for the trend cross".
   - 12-month relative momentum, held ~3-6m, is the only mild persistent
     tilt (+0.1-0.3%, ~51%).
   So sector output is framed as: confirmed leadership (descriptive), an
   evidence-backed avoid list, and a next-rotation watchlist with explicit
   wait-for-confirmation execution rules.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

SECTOR_NAMES = {
    "XLB": "Materials", "XLC": "Communications", "XLE": "Energy",
    "XLF": "Financials", "XLI": "Industrials", "XLK": "Technology",
    "XLP": "Consumer Staples", "XLRE": "Real Estate", "XLU": "Utilities",
    "XLV": "Health Care", "XLY": "Consumer Discretionary",
    "SMH": "Semiconductors", "IWM": "Small Caps", "RSP": "Equal-Weight S&P",
    "QUAL": "Quality factor", "MTUM": "Momentum factor", "USMV": "Min-vol factor",
    "LQD": "IG Corporate Bonds", "GC=F": "Gold",
}

QUAD_MEANING = {
    "Q1": "Goldilocks — growth improving while inflation cools",
    "Q2": "Reflation — growth and inflation both heating up",
    "Q3": "Stagflation — inflation rising while growth rolls over",
    "Q4": "Growth scare — growth and inflation both falling",
}
# user-facing names — the Q-codes collide with calendar quarters in users' minds
QUAD_SHORT = {"Q1": "Goldilocks", "Q2": "Reflation",
              "Q3": "Stagflation", "Q4": "Growth scare"}

EXTENDED_PCTILE = 92

COMPONENT_PLAIN = {
    "copper_gold": "the copper-vs-gold price trend (a classic growth-expectations gauge)",
    "xly_xlp": "consumer discretionary vs staples (shopper confidence)",
    "us2y_direction": "the 2-year Treasury yield direction",
    "iwm_spy": "small caps vs large caps",
    "cyclical_defensive": "economically-sensitive sectors vs defensive ones",
    "breadth_direction": "how many S&P 500 stocks are in uptrends",
    "payrolls_trend": "the payrolls trend",
    "indpro_trend": "industrial production",
    "breakeven_10y_direction": "the bond market's 10-year inflation expectation",
    "breakeven_5y5y_direction": "long-horizon inflation expectations",
    "energy_rs": "energy sector relative strength",
    "oil_trend": "the oil price trend",
    "inflation_beta_basket": "inflation-winner sectors vs inflation-loser sectors",
    "tips_nominal_momentum": "the TIPS-vs-Treasury inflation spread",
}


# ---------------------------------------------------------------- stages ----

def stage_table(closes: pd.DataFrame, asof: pd.Timestamp | None = None) -> pd.DataFrame:
    bench = config.load()["engine"]["rs_ranking"]["benchmark"]
    sectors = config.load()["yahoo"]["tickers"]["sectors"]
    if asof is not None:
        closes = closes[closes.index <= asof]
    rows = []
    for t in sectors:
        if t not in closes.columns or bench not in closes.columns:
            continue
        rs = (closes[t] / closes[bench]).dropna()
        if len(rs) < 260:
            continue
        ma = rs.rolling(200).mean()
        above = bool(rs.iloc[-1] > ma.iloc[-1])
        mom20 = float(rs.pct_change(20).iloc[-1] * 100)
        mom60 = float(rs.pct_change(60).iloc[-1] * 100)
        mom252 = float(rs.pct_change(252).iloc[-1] * 100)
        pctile = float(rs.iloc[-252:].rank(pct=True).iloc[-1] * 100)
        if above and mom20 > 0:
            stage = "leading"
        elif above:
            stage = "weakening"
        elif mom20 > 0:
            stage = "improving"
        else:
            stage = "lagging"
        rows.append({"ticker": t, "name": SECTOR_NAMES.get(t, t), "stage": stage,
                     "mom_20d_pct": round(mom20, 2), "mom_60d_pct": round(mom60, 2),
                     "mom_252d_pct": round(mom252, 2), "above_trend": above,
                     "pctile_252d": round(pctile, 1),
                     "extended": stage == "leading" and pctile >= EXTENDED_PCTILE})
    return pd.DataFrame(rows).set_index("ticker")


# ------------------------------------------------- quad transition matrix ----

def quad_segments(quad: pd.Series) -> pd.DataFrame:
    q = quad.dropna()
    seg_id = (q != q.shift()).cumsum()
    g = q.groupby(seg_id)
    return pd.DataFrame({"quad": g.first(), "days": g.size(),
                         "start": g.apply(lambda s: s.index.min())}).reset_index(drop=True)


def transition_stats(quad: pd.Series) -> dict:
    seg = quad_segments(quad)
    out: dict = {"matrix": {}, "median_days": {}, "n_by_quad": {},
                 "n_segments": len(seg)}
    for q in ("Q1", "Q2", "Q3", "Q4"):
        nxt = seg["quad"].shift(-1)[seg["quad"] == q].dropna()
        if len(nxt):
            out["matrix"][q] = nxt.value_counts(normalize=True).round(2).to_dict()
        dur = seg.loc[seg["quad"] == q, "days"]
        if len(dur):
            out["median_days"][q] = int(dur.median())
            out["n_by_quad"][q] = int(len(dur))
    cur = seg.iloc[-1]
    out["current"] = {"quad": cur["quad"], "age_days": int(cur["days"]),
                      "median_days": out["median_days"].get(cur["quad"])}
    return out


# ------------------------------------------------------ measured evidence ----

def risk_evidence(closes: pd.DataFrame, regime: pd.DataFrame) -> dict:
    """Index-level conditional stats for the exposure dial, computed from the
    classifier's own history so the numbers shown are always current."""
    spy = closes["SPY"]
    quad = regime["quad"].reindex(spy.index)
    liq = regime["liquidity"].reindex(spy.index)
    state = regime["transition_state"].reindex(spy.index) \
        if "transition_state" in regime.columns else pd.Series(index=spy.index, dtype=object)
    weekly = pd.Series(False, index=spy.index)
    weekly.iloc[::5] = True
    fwd21 = spy.pct_change(21).shift(-21)
    dd63 = (spy.rolling(63).min().shift(-63) / spy - 1)

    def cond(mask: pd.Series) -> dict | None:
        m = mask.fillna(False) & weekly & fwd21.notna()
        if m.sum() < 40:
            return None
        return {"n": int(m.sum()),
                "fwd21_avg_pct": round(100 * fwd21[m].mean(), 2),
                "fwd21_hit_pct": round(100 * (fwd21[m] > 0).mean(), 1),
                "avg_worst_dd63_pct": round(100 * dd63[m].mean(), 2)}

    return {k: v for k, v in {
        "liquidity_expanding": cond(liq == "expanding"),
        "liquidity_contracting": cond(liq == "contracting"),
        "quad_q3": cond(quad == "Q3"),
        "risk_on_quads": cond(quad.isin(["Q1", "Q2"])),
        "risk_off_quads": cond(quad.isin(["Q3", "Q4"])),
        "risk_on_stable": cond(quad.isin(["Q1", "Q2"]) & (state == "STABLE")),
        "risk_on_warning": cond(quad.isin(["Q1", "Q2"]) & (state != "STABLE")),
    }.items() if v}


# evidence constants measured in scripts/research_playbook.py (2000->2026 grid,
# split-half checked) — recomputing the full grid daily is wasteful; re-run the
# research script after any engine change and update if materially different
SECTOR_EVIDENCE = {
    "dont_chase": {"hit_pct": 44.7, "avg_excess_pct": -0.57, "horizon": "3m",
                   "desc": "buying regime-favored sectors already at >92nd pctile RS"},
    "dont_anticipate": {"hit_pct": 45.6, "avg_excess_pct": -0.73, "horizon": "3m",
                        "desc": "buying below-trend sectors on a momentum uptick (all variants negative)"},
    "momentum_tilt": {"hit_pct": 51.0, "avg_excess_pct": 0.27, "horizon": "6m",
                      "desc": "top-3 sectors by 12m relative momentum, held ~3-6m (the only mild persistent edge)"},
}


# --------------------------------------------------------------- exposure ----

def exposure_dial(latest: dict, evidence: dict) -> dict:
    """Transparent additive rules -> posture. Every rule cites its measured stat."""
    score = 0
    reasons = []

    liq = latest["liquidity_overlay"]
    if liq == "expanding":
        score += 1
        ev = evidence.get("liquidity_expanding")
        reasons.append(("+", "Fed liquidity is expanding — historically the single most "
                        "reliable tailwind"
                        + (f" (S&P +{ev['fwd21_avg_pct']}% avg next month, "
                           f"{ev['fwd21_hit_pct']}% positive)" if ev else "")))
    elif liq == "contracting":
        score -= 1
        reasons.append(("-", "Fed liquidity is contracting — a persistent headwind for risk assets"))

    quad = latest["quad"]
    state = latest["transition_state"]
    if quad in ("Q1", "Q2") and state == "STABLE":
        score += 1
        ev = evidence.get("risk_on_stable")
        reasons.append(("+", f"Risk-friendly regime ({QUAD_SHORT[quad]}) with no transition "
                        "warnings"
                        + (f" — in this condition the S&P averaged "
                           f"+{ev['fwd21_avg_pct']}%/month, {ev['fwd21_hit_pct']}% positive"
                           if ev else "")))
    if quad == "Q3":
        score -= 1
        ev = evidence.get("quad_q3")
        reasons.append(("-", "Stagflation (Q3) was historically the weakest backdrop for stocks"
                        + (f" ({ev['fwd21_avg_pct']:+}%/month avg)" if ev else "")))
    if quad == "Q4" and "Recession" in latest.get("label", ""):
        score -= 1
        reasons.append(("-", "Growth-scare with credit confirming recession — the deep-drawdown zone"))
    if quad in ("Q3", "Q4"):
        ev_on, ev_off = evidence.get("risk_on_quads"), evidence.get("risk_off_quads")
        if ev_on and ev_off:
            reasons.append(("i", f"Risk-off regimes don't lower average returns much (rebounds), "
                            f"but 3-month drawdowns run deeper "
                            f"({ev_off['avg_worst_dd63_pct']}% vs {ev_on['avg_worst_dd63_pct']}%) "
                            f"— smaller positions, wider stops"))
    if state in ("TRANSITIONING", "NEW_REGIME"):
        score -= 1
        reasons.append(("-", f"Transition radar reads {state} — the regime is shifting; "
                        "reduce conviction bets until it settles (this early-warning "
                        "worked best pre-2017; the 2017-2021 dip-buying era blunted it)"))
    elif state == "WEAKENING":
        reasons.append(("i", "Transition radar reads WEAKENING (2+ warning flags) — "
                        "no action required yet, but stop adding regime-dependent risk"))

    if latest["confidence"] < 0.3:
        score = min(score, 0)
        reasons.append(("i", f"Signal agreement is low ({latest['confidence']:.0%}) — "
                        "the regime label itself is uncertain; neutral posture caps apply"))

    posture = {2: "AGGRESSIVE", 1: "CONSTRUCTIVE", 0: "NEUTRAL",
               -1: "CAREFUL", -2: "DEFENSIVE"}[max(-2, min(2, score))]
    meaning = {
        "AGGRESSIVE": "conditions support full risk budget; buy dips in confirmed leaders",
        "CONSTRUCTIVE": "lean long; normal position sizes in confirmed leaders",
        "NEUTRAL": "no edge either way; core holdings only, no new conviction bets",
        "CAREFUL": "reduce size, tighten stops, let cash build",
        "DEFENSIVE": "minimum equity risk; capital preservation mode",
    }[posture]
    return {"score": score, "posture": posture, "meaning": meaning, "reasons": reasons}


# --------------------------------------------------------------- assembly ----

def _trigger_lines(latest_flags: dict, flip: dict, pending: dict | None,
                   next_quad: str | None) -> list[str]:
    lines = []
    if pending and pending.get("quad"):
        pname = QUAD_SHORT.get(str(pending["quad"]), pending["quad"])
        lines.append(f"A regime change to {pname} is already counting down: "
                     f"{pending['days']} of {pending['need']} confirmation days done.")
    if flip and flip.get("component"):
        plain = COMPONENT_PLAIN.get(flip["component"], flip["component"])
        lines.append(f"The most fragile support is {plain} — if it rolls over, "
                     f"the {flip['axis']} signal flips.")
    flag_plain = {
        "flag_breadth_price": "the index is near highs but fewer stocks are participating",
        "flag_credit_equity": "stocks are up but credit markets are getting nervous",
        "flag_ratio_inflection": "risk-appetite ratios just turned against the regime",
        "flag_inflation_basket": "inflation-sensitive sectors are turning against the regime",
        "flag_confidence_decay": "the signals behind the regime are losing agreement",
        "flag_gex": "options positioning suggests a fragile, swingy market",
    }
    on = [flag_plain[k] for k, v in latest_flags.items() if v and k in flag_plain]
    lines.extend(f"Warning already active: {t}." for t in on)
    if next_quad:
        watch_by_quad = {
            "Q2": "inflation expectations and energy turning up while growth holds",
            "Q3": "inflation rising while breadth and cyclicals fade",
            "Q4": "credit spreads widening and defensives taking leadership",
            "Q1": "inflation expectations cooling while breadth holds up",
        }
        lines.append(f"For a shift to {QUAD_SHORT[next_quad]}, watch for "
                     f"{watch_by_quad[next_quad]}.")
    return lines[:4]


HEAT_BANDS = {
    "70+": ("OVERHEATED", "everything is confirmed — which historically meant late: "
            "this band UNDERperformed the index going forward. Hold with tight stops "
            "or trim; don't initiate here."),
    "55-69": ("HOT", "confirmed strength. Fine to hold; fresh entries showed no "
              "historical edge — prefer pullbacks that hold the trend."),
    "40-54": ("NEUTRAL", "mixed picture, no statistical lean either way."),
    "0-39": ("COLD", "washed out. Historically this band mildly mean-reverts upward, "
             "but timing is unreliable — wait for the confirmation trigger."),
}


def build_playbook(f: pd.DataFrame, regime: pd.DataFrame, closes: pd.DataFrame,
                   latest: dict) -> dict:
    from engine.technicals import (_score_components, band_for, calibrate,
                                   season_line, seasonality, snapshot)
    quad = latest["quad"]
    prefs = config.load()["engine"]["sector_preferences"]
    bench = config.load()["engine"]["rs_ranking"]["benchmark"]
    stages = stage_table(closes)
    trans = transition_stats(regime["quad"])
    evidence = risk_evidence(closes, regime)
    dial = exposure_dial(latest, evidence)
    heat_cal = calibrate(closes, regime)

    aligned = set(prefs.get(quad, [])) & set(stages.index)

    # --- enrich each sector with technicals, seasonality, heat, trigger gap ----
    month = int(closes.index.max().month)
    nxt_month = month % 12 + 1
    enriched: list[dict] = []
    tech_by_ticker: dict[str, dict] = {}
    for t, row in stages.iterrows():
        close = closes[t].dropna()
        tech = snapshot(close)
        seas = seasonality(close)
        heat = _score_components(t in aligned, dial["score"], row["stage"],
                                 bool(row["extended"]), tech, row["pctile_252d"])
        band = band_for(heat["score"])
        cal = heat_cal.get(band)
        rec = {**row.to_dict(), "ticker": t, **{f"tech_{k}": v for k, v in tech.items()},
               "heat": heat["score"], "heat_parts": heat, "heat_band": band,
               "heat_label": HEAT_BANDS[band][0], "heat_note": HEAT_BANDS[band][1],
               "heat_cal": cal,
               "season_this": season_line(seas, month),
               "season_next": season_line(seas, nxt_month)}
        # distance to the buy trigger for names below their RS trend
        if not row["above_trend"]:
            rs = (closes[t] / closes[bench]).dropna()
            ma200 = rs.rolling(200).mean()
            gap = float((ma200.iloc[-1] / rs.iloc[-1] - 1) * 100)
            lo60 = float(rs.iloc[-60:].min())
            denom = float(ma200.iloc[-1]) - lo60
            progress = float((rs.iloc[-1] - lo60) / denom * 100) if denom > 0 else None
            rec["trigger_gap_pct"] = round(gap, 1)
            rec["trigger_progress_pct"] = round(min(max(progress, 0), 100), 0) \
                if progress is not None else None
        enriched.append(rec)
        tech_by_ticker[t] = rec

    leaders, avoid = [], []
    for t, row in stages.iterrows():
        is_aligned = t in aligned
        if row["stage"] == "leading" and not row["extended"]:
            trend_note = (f"3-month RS {row['mom_60d_pct']:+.1f}%"
                          if row["mom_60d_pct"] > 0 else
                          f"rebuilding after a soft 3 months ({row['mom_60d_pct']:+.1f}%)")
            rec = tech_by_ticker.get(t, {})
            tech_bits = []
            if rec.get("tech_rsi14") is not None:
                tech_bits.append(f"RSI {rec['tech_rsi14']:.0f}")
            if rec.get("tech_above200") and rec.get("tech_above50"):
                tech_bits.append("above both moving averages")
            elif rec.get("tech_above200"):
                tech_bits.append("above its 200-day average")
            tech_txt = (" Tech: " + ", ".join(tech_bits) + "." if tech_bits else "")
            season_txt = f" {rec['season_this']}." if rec.get("season_this") else ""
            leaders.append({
                "ticker": t, "name": row["name"],
                "aligned": is_aligned, "mom_60d_pct": row["mom_60d_pct"],
                "why": (f"Established uptrend vs the market, short-term momentum positive "
                        f"({row['mom_20d_pct']:+.1f}% over 20d; {trend_note})"
                        + (" — and the current regime historically favored it."
                           if is_aligned else ".") + tech_txt + season_txt),
            })
        elif row["extended"]:
            avoid.append({"ticker": t, "name": row["name"], "call": "DON'T CHASE",
                          "why": (f"Leadership is real but stretched (RS at the "
                                  f"{row['pctile_252d']:.0f}th pctile of its year). "
                                  f"Historically, buying here won only "
                                  f"{SECTOR_EVIDENCE['dont_chase']['hit_pct']}% of the time "
                                  f"over 3 months. Wait for a pullback that holds the trend.")})
        elif row["stage"] == "improving":
            avoid.append({"ticker": t, "name": row["name"], "call": "TOO EARLY",
                          "why": (f"Momentum just turned up ({row['mom_20d_pct']:+.1f}% 20d) but "
                                  f"it's still below its long-term trend vs the market. Tempting — "
                                  f"and historically a losing entry "
                                  f"({SECTOR_EVIDENCE['dont_anticipate']['avg_excess_pct']}%/3m avg). "
                                  f"Wait for the trend line to actually break.")})
        elif is_aligned and row["stage"] in ("weakening", "lagging"):
            avoid.append({"ticker": t, "name": row["name"], "call": "REGIME-TAPE CONFLICT",
                          "why": (f"The regime map favors it but the market is selling it "
                                  f"({row['mom_20d_pct']:+.1f}% 20d RS). Tape wins — stand aside "
                                  f"until it stabilizes above trend.")})
    leaders.sort(key=lambda x: (not x["aligned"], -x["mom_60d_pct"]))

    mom_tilt = stages.sort_values("mom_252d_pct", ascending=False).head(3)
    momentum_tilt = {
        "tickers": [{"ticker": t, "name": r["name"], "mom_252d_pct": r["mom_252d_pct"]}
                    for t, r in mom_tilt.iterrows()],
        "note": (f"Top-3 by 12-month relative momentum — the only sector tilt with a "
                 f"persistent (if mild) historical edge: "
                 f"+{SECTOR_EVIDENCE['momentum_tilt']['avg_excess_pct']}% avg vs SPY over "
                 f"~6 months, {SECTOR_EVIDENCE['momentum_tilt']['hit_pct']}% hit rate. "
                 f"A tilt, not a trade."),
    }

    nxt = trans["matrix"].get(quad, {})
    next_quad = max(nxt, key=nxt.get) if nxt else None
    watchlist = []
    if next_quad:
        for t in prefs.get(next_quad, []):
            if t in stages.index and stages.loc[t, "stage"] in ("improving", "lagging"):
                row = stages.loc[t]
                rec = tech_by_ticker.get(t, {})
                trigger_txt = ""
                if rec.get("trigger_gap_pct") is not None:
                    trigger_txt = (f" Trigger distance: needs {rec['trigger_gap_pct']:+.1f}% "
                                   f"more outperformance vs the market to confirm")
                    if rec.get("trigger_progress_pct") is not None:
                        trigger_txt += (f" — already {rec['trigger_progress_pct']:.0f}% of the "
                                        f"way there from its recent low")
                    trigger_txt += "."
                season_txt = f" Seasonality: {rec['season_next']}." if rec.get("season_next") else ""
                watchlist.append({
                    "ticker": t, "name": row["name"],
                    "why": (f"Historically favored if the regime shifts to "
                            f"{QUAD_SHORT[next_quad]}. Currently {row['stage']} "
                            f"({row['mom_20d_pct']:+.1f}% 20d RS). Don't buy in "
                            f"anticipation — wait for the trend cross.{trigger_txt}"
                            f"{season_txt}")})

    pending = None
    last = regime.dropna(subset=["quad"]).iloc[-1]
    if last["pending_quad"] and str(last["pending_quad"]) not in ("None", "nan"):
        pending = {"quad": last["pending_quad"], "days": int(last["pending_days"]),
                   "need": config.load()["engine"]["quad"]["hysteresis_days"]}

    triggers = _trigger_lines(latest.get("transition_flags", {}),
                              latest.get("flip_condition", {}), pending, next_quad)

    headline = (f"{QUAD_MEANING[quad]}. Posture: {dial['posture']} — {dial['meaning']}.")

    # --- regime progress: where are we in this regime's typical lifespan? -----
    cur = trans["current"]
    seg = quad_segments(regime["quad"])
    durs = seg.loc[seg["quad"] == quad, "days"].to_numpy()
    progress = None
    if len(durs) >= 8:
        age = cur["age_days"]
        t33, t66, p90 = (float(np.percentile(durs, p)) for p in (33, 66, 90))
        pct_longer = float((durs > age).mean() * 100)
        longer = durs[durs > age]
        med_remaining = int(np.median(longer) - age) if len(longer) else None
        phase = ("early" if age < t33 else "mid" if age < t66
                 else "late" if age <= p90 else "overdue")
        phase_note = {
            "early": "still young — regime-aligned positions have historical room to run",
            "mid": "mid-life — ride it, but keep the next-shift watchlist warm",
            "late": "older than most — tighten stops on regime-dependent positions "
                    "and take the transition radar seriously",
            "overdue": "has outlived nearly all its predecessors — treat every "
                       "warning flag as live",
        }[phase]
        progress = {
            "age_days": int(age), "median_days": int(np.median(durs)),
            "pct_longer": round(pct_longer, 0),
            "median_remaining_days": med_remaining,
            "phase": phase, "phase_note": phase_note,
            "bar_pct": round(min(age / p90, 1.0) * 100, 1),
            "zone_early_pct": round(t33 / p90 * 100, 1),
            "zone_mid_pct": round(t66 / p90 * 100, 1),
            "n_history": int(len(durs)),
        }

    age_note = None
    if cur.get("median_days") and nxt:
        age_note = (f"This {QUAD_SHORT[quad]} stretch is {cur['age_days']} trading days old "
                    f"(historical median: {cur['median_days']}). When {QUAD_SHORT[quad]} ended, "
                    f"it went to: "
                    + ", ".join(f"{QUAD_SHORT.get(k, k)} {v:.0%}"
                                for k, v in sorted(nxt.items(), key=lambda kv: -kv[1])))

    next_list = [{"code": k, "name": QUAD_SHORT.get(k, k),
                  "meaning": QUAD_MEANING.get(k, ""), "prob_pct": round(v * 100)}
                 for k, v in sorted(nxt.items(), key=lambda kv: -kv[1])]

    # commodities & macro tape: technicals + seasonality, no heat score (no
    # RS-vs-SPY stage or regime alignment is meaningful for these)
    commodities = []
    for t, label in [("GC=F", "Gold"), ("CL=F", "Crude Oil"),
                     ("HG=F", "Copper"), ("DX-Y.NYB", "US Dollar")]:
        if t not in closes.columns:
            continue
        c = closes[t].dropna()
        if len(c) < 300:
            continue
        from engine.technicals import season_line as _sl
        from engine.technicals import seasonality as _seas
        from engine.technicals import snapshot as _snap
        tech = _snap(c)
        seas = _seas(c)
        commodities.append({"ticker": t, "name": label, **tech,
                            "season_this": _sl(seas, month),
                            "mom_60d_pct": round(float(c.pct_change(60).iloc[-1] * 100), 1)})

    return {
        "headline": headline,
        "dial": dial,
        "leaders": leaders[:4],
        "avoid": avoid[:4],
        "momentum_tilt": momentum_tilt,
        "next_quad": next_quad,
        "next_quad_name": QUAD_SHORT.get(next_quad, next_quad) if next_quad else None,
        "next_quad_probs": nxt,
        "next_list": next_list,
        "progress": progress,
        "regime_age_note": age_note,
        "watchlist": watchlist[:4],
        "triggers": triggers,
        "stages": enriched,
        "heat_calibration": heat_cal,
        "commodities": commodities,
        "evidence": evidence,
        "honesty": ("Sector picks vs the index showed no stable edge in our 2000-2026 backtest "
                    "(results flip between decades) — so sector calls here are risk filters and "
                    "confirmation tools, not return predictions. The exposure dial conditions "
                    "are the statistically robust part."),
    }
