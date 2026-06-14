"""Complementary macro-conditions / nowcast / risk-appetite layer.

This module is ADDITIVE. It runs alongside the split-half-validated growth/
inflation quad (engine/regime.py) and never alters it — it gives the dashboard a
second, independent lens built from the Fed-research feeds and option-implied
risk that the price-based quad lacks:

  • Financial Conditions  — Chicago Fed NFCI (+ risk/credit/leverage subindices)
                            and St. Louis stress: one broad z-scored gauge.
  • Recession risk        — a 0..100 composite of the Sahm rule (concurrent),
                            the smoothed recession probability, the Excess Bond
                            Premium model prob + level, and a term-premium-
                            ADJUSTED curve slope (strips the 2022-24 false
                            inversion driven by a low/negative term premium).
  • Growth nowcast        — Weekly Economic Index + Atlanta Fed GDPNow.
  • Labor / real-activity — high-frequency leading reads that front-run the
                            monthly, revised payrolls: weekly jobless claims,
                            Indeed job postings (demand), and daily withheld
                            income-tax receipts (a wage/income flow). Additive
                            display reads — NOT in the recession/drawdown SCORE.
  • Inflation nowcast     — Atlanta sticky vs flexible CPI: is the impulse
                            persistent (sticky rising) or transitory (flexible)?
  • Risk-appetite layer   — equity volatility-risk-premium (implied-realized),
                            VIX term structure, CBOE SKEW tail pricing, realized
                            stock-bond correlation regime, a cross-asset RORO
                            composite, and a volatility-target exposure scalar.

Everything degrades gracefully: a missing input drops out of its composite and
the affected read renormalizes (or returns None) — the run never crashes.
See research/QUANT_FACTOR_EXPANSION.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.indicators import pct_rank_window
from lib import config, store


# --- small helpers -----------------------------------------------------------
def _col(f: pd.DataFrame, name: str) -> pd.Series | None:
    if name not in f.columns or f[name].isna().all():
        return None
    return f[name]


def _z(s: pd.Series, window: int) -> pd.Series:
    """Rolling z-score (causal)."""
    m = s.rolling(window, min_periods=window // 4).mean()
    sd = s.rolling(window, min_periods=window // 4).std()
    return (s - m) / sd.replace(0, np.nan)


def _last(s: pd.Series | None) -> float | None:
    if s is None:
        return None
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else None


def _ann_monthly_pct(s: pd.Series, smooth_months: int) -> pd.Series:
    """Annualize a monthly %-change series after smoothing over N distinct
    monthly prints. The daily feature frame carries each month's value
    forward-filled, so we de-duplicate to the actual monthly observations
    before the rolling mean, then re-broadcast onto the daily index."""
    monthly = s.dropna()
    # collapse consecutive identical ffilled values to one print per monthly change
    distinct = monthly[monthly.ne(monthly.shift())]
    sm = distinct.rolling(smooth_months, min_periods=1).mean()
    ann = ((1.0 + sm / 100.0) ** 12 - 1.0) * 100.0
    return ann.reindex(s.index).ffill()


# --- conditions time series (for charts + alerts) ----------------------------
def conditions_frame(f: pd.DataFrame) -> pd.DataFrame:
    """Daily time series of the derived conditions/risk signals."""
    cfg = config.load()["engine"]["conditions"]
    out = pd.DataFrame(index=f.index)

    # Financial conditions ----------------------------------------------------
    nfci = _col(f, "nfci")
    if nfci is not None:
        out["nfci"] = nfci
        out["nfci_pctile"] = pct_rank_window(nfci, cfg["nfci_pctile_lookback_d"])
        out["nfci_chg"] = nfci - nfci.shift(cfg["nfci_change_window_d"])
    for sub in ("anfci", "nfci_risk", "nfci_credit", "nfci_leverage", "stlfsi"):
        s = _col(f, sub)
        if s is not None:
            out[sub] = s

    # Recession risk composite (0..100) --------------------------------------
    rc = cfg["recession"]
    w = rc["weights"]
    parts: dict[str, tuple[pd.Series, float]] = {}
    sahm = _col(f, "sahm")
    if sahm is not None:
        parts["sahm"] = ((sahm / rc["sahm_full"]).clip(0, 1), w["sahm"])
    rprob = _col(f, "recession_prob")
    if rprob is not None:
        parts["recession_prob"] = ((rprob / 100.0).clip(0, 1), w["recession_prob"])
    eprob = _col(f, "ebp_recession_prob")
    if eprob is not None:
        parts["ebp_prob"] = (eprob.clip(0, 1), w["ebp_prob"])
    curve = _col(f, "curve_tp_adj")
    if curve is not None:
        lo, full = rc["curve_invert_level"], rc["curve_full_invert"]
        parts["curve"] = (((lo - curve) / (lo - full)).clip(0, 1), w["curve"])
    ebp = _col(f, "ebp")
    if ebp is not None:
        parts["ebp_level"] = (pct_rank_window(ebp, rc["ebp_level_pctile_lookback_d"]).clip(0, 1),
                              w["ebp_level"])
    # Jobless-claims leg — Phase-0 validated vs NBER (research/CLAIMS_RECESSION_VALIDATION.md):
    # YoY of the 4wk-MA claims level, recession-ward. Config-gated (weight 0 disables it);
    # only joins when the column exists, so older / claims-free frames are unaffected.
    w_claims = w.get("claims", 0.0)
    claims4 = _col(f, "initial_claims_4wk")
    if claims4 is None:
        claims4 = _col(f, "initial_claims")
    if claims4 is not None and w_claims > 0:
        claims_yoy = claims4 / claims4.shift(rc.get("claims_yoy_window_d", 252)) - 1.0
        parts["claims"] = ((claims_yoy / rc.get("claims_yoy_full", 0.40)).clip(0, 1), w_claims)
    if parts:
        # renormalize over AVAILABLE components per day: a NaN leg drops out of
        # both numerator and denominator instead of poisoning the whole sum.
        num = sum(s.fillna(0) * wt for s, wt in parts.values())
        den = sum(s.notna().astype(float) * wt for s, wt in parts.values())
        out["recession_risk"] = (100.0 * num / den.replace(0, np.nan))
        for name, (s, _wt) in parts.items():
            out[f"recession_{name}"] = (100.0 * s)
    if "curve_tp_adj" in f:
        out["curve_tp_adj"] = f["curve_tp_adj"]
    if "spread_2s10s" in f:
        out["curve_raw"] = f["spread_2s10s"]

    # Real-activity / labor nowcast (research/REAL_ACTIVITY_NOWCAST.md) --------
    # Leading labor + income reads that front-run the monthly, revised PAYEMS.
    # ADDITIVE display columns — deliberately NOT folded into recession_risk /
    # drawdown_risk (those feed the macro-risk SCORE), so scoring is unchanged
    # until these legs are separately validated.
    lcfg = cfg.get("labor", {})
    claims4 = _col(f, "initial_claims_4wk")
    if claims4 is None:
        claims4 = _col(f, "initial_claims")
    if claims4 is not None:
        out["initial_claims_4wk"] = claims4
        out["claims_yoy"] = (claims4 / claims4.shift(lcfg.get("claims_yoy_window_d", 252)) - 1.0) * 100
        out["claims_z"] = _z(claims4, lcfg.get("claims_z_lookback_d", 756))
    cc = _col(f, "continued_claims")
    if cc is not None:
        out["continued_claims"] = cc
    indeed = _col(f, "indeed_postings")
    if indeed is not None:
        out["indeed_postings"] = indeed
        out["indeed_chg"] = (indeed / indeed.shift(lcfg.get("indeed_chg_window_d", 63)) - 1.0) * 100
    # withheld income & employment taxes: a daily FLOW — sum the ACTUAL deposit
    # days over a trailing window, then YoY of that sum (never ffill a flow).
    wt_raw = store.read("treasury", "withheld_taxes")
    if wt_raw is not None and not wt_raw.empty:
        s = wt_raw.iloc[:, 0].copy()
        s.index = pd.to_datetime(s.index)
        s = s.sort_index()
        roll = s.rolling(lcfg.get("withheld_sum_window_d", 63), min_periods=40).sum()
        wt_yoy = (roll / roll.shift(lcfg.get("withheld_yoy_window_d", 252)) - 1.0) * 100
        out["withheld_tax_yoy"] = wt_yoy.reindex(out.index).ffill(limit=10)
    ns = _col(f, "news_sentiment")
    if ns is not None:
        out["news_sentiment"] = ns
        out["news_sentiment_z"] = _z(ns, lcfg.get("news_z_lookback_d", 252))

    # Equity volatility-risk-premium -----------------------------------------
    vcfg = cfg["vrp"]
    spy = _col(f, "SPY")
    vix = _col(f, "vix")
    if spy is not None and vix is not None:
        realized = spy.pct_change(fill_method=None).rolling(
            vcfg["realized_window_d"]).std() * np.sqrt(252) * 100
        out["realized_vol"] = realized
        out["vrp"] = vix - realized
        out["vrp_pctile"] = pct_rank_window(out["vrp"], vcfg["pctile_lookback_d"])

    # VIX term structure ------------------------------------------------------
    vix3m = _col(f, "vix3m")
    if vix is not None and vix3m is not None:
        out["vix_term"] = vix / vix3m

    # SKEW --------------------------------------------------------------------
    skew = _col(f, "skew")
    if skew is not None:
        out["skew"] = skew
        out["skew_pctile"] = pct_rank_window(skew, cfg["skew_pctile_lookback_d"])

    # Realized stock-bond correlation regime ----------------------------------
    ccfg = cfg["corr"]
    us10y = _col(f, "us10y")
    if spy is not None and us10y is not None:
        spy_ret = spy.pct_change(fill_method=None)
        bond_ret = -us10y.diff()                      # Treasury price proxy: price up when yield falls
        out["stock_bond_corr"] = spy_ret.rolling(ccfg["window_d"]).corr(bond_ret)
    # Value-vs-growth STYLE tilt driver (MEASURED §6: a rising 10y yield favours
    # value over growth — t=+3.0, holds in all four 2000-2026 sub-periods).
    if us10y is not None:
        out["yield_chg_1m"] = us10y.diff(21)          # ~1-month 10y change (pp)

    # RORO cross-asset composite (risk-on positive) ---------------------------
    zw = cfg["roro"]["z_window_d"]
    roro_parts = []
    if vix is not None:
        roro_parts.append(-_z(vix, zw))
    hy = _col(f, "hy_oas")
    if hy is not None:
        roro_parts.append(-_z(hy, zw))
    if skew is not None:
        roro_parts.append(-_z(skew, zw))
    if "vix_term" in out:
        roro_parts.append(-_z(out["vix_term"], zw))
    if nfci is not None:
        roro_parts.append(-_z(nfci, zw))
    cg = _col(f, "copper_gold")
    if cg is not None:
        roro_parts.append(_z(cg, zw))
    dxy = _col(f, "dxy")
    if dxy is not None:
        roro_parts.append(-_z(dxy.pct_change(20, fill_method=None), zw))
    if roro_parts:
        out["roro"] = pd.concat(roro_parts, axis=1).mean(axis=1)

    # Volatility-target exposure scalar ---------------------------------------
    tcfg = cfg["vol_target"]
    if spy is not None:
        rv = spy.pct_change(fill_method=None).rolling(
            tcfg["realized_window_d"]).std() * np.sqrt(252) * 100
        out["vol_target_scalar"] = (tcfg["target_vol_pct"] / rv).clip(tcfg["floor"], tcfg["cap"])

    # Drawdown-risk gauge (lean 4-factor macro stress, 0..100) ----------------
    # MEASURED: >=80 -> P(>=10% dd/63d) ~45% vs ~13% base (research §6). Each
    # component z-scored (causal, expanding-capped rolling), averaged, mapped to
    # an expanding percentile so the gauge is 0..100 with no look-ahead.
    dcfg = cfg["drawdown_risk"]
    src = {"recession_risk": out.get("recession_risk"), "nfci": nfci,
           "ebp": _col(f, "ebp"), "hy_oas": _col(f, "hy_oas")}
    zlegs = [_z(s, dcfg["z_lookback_d"]) for k, s in src.items()
             if k in dcfg["components"] and s is not None]
    if len(zlegs) >= 2:
        comp = pd.concat(zlegs, axis=1).mean(axis=1)
        out["drawdown_risk"] = (comp.expanding(min_periods=252).rank(pct=True) * 100)

    # Capitulation gauge (contrarian bounce, 0..3 signals) --------------------
    # MEASURED: VRP %ile>0.90 -> +5.8%/63d 88% pos; VIX>30 -> +7.2%; COT washout
    # -> +4.2%; stacked -> +9.6%/92% (research §6).
    ccfg = cfg["capitulation"]
    cap_parts = []
    if "vrp_pctile" in out:
        cap_parts.append((out["vrp_pctile"] > ccfg["vrp_pctile"]).astype(float))
    if vix is not None:
        cap_parts.append((vix > ccfg["vix_panic"]).astype(float))
    cot = store.read("cot", "cot_es_spx")
    if cot is not None and "net_spec_pct_oi" in cot.columns:
        ns = cot["net_spec_pct_oi"].reindex(out.index).ffill(limit=10)
        washout = pct_rank_window(ns, ccfg["cot_pctile_lookback_d"]) < ccfg["cot_washout_pctile"]
        cap_parts.append(washout.astype(float))
    if cap_parts:
        out["capitulation_score"] = pd.concat(cap_parts, axis=1).sum(axis=1)

    return out


# --- snapshot dict (for latest.json + panels) --------------------------------
def _band(v: float | None, lo: float, hi: float, names: tuple[str, str, str]) -> str | None:
    if v is None:
        return None
    return names[0] if v < lo else (names[2] if v >= hi else names[1])


def conditions_snapshot(f: pd.DataFrame) -> dict:
    cfg = config.load()["engine"]["conditions"]
    fr = conditions_frame(f)
    row = fr.dropna(how="all").iloc[-1] if len(fr.dropna(how="all")) else pd.Series(dtype=float)

    def g(name):
        v = row.get(name)
        return None if v is None or pd.isna(v) else float(v)

    # financial conditions
    nfci = g("nfci")
    fin = {
        "nfci": nfci,
        "nfci_pctile": g("nfci_pctile"),
        "nfci_change_13w": g("nfci_chg"),
        "state": _band(nfci, -0.10, 0.10, ("loose", "neutral", "tight")) if nfci is not None else None,
        "trend": (None if g("nfci_chg") is None else
                  ("tightening" if g("nfci_chg") > 0 else "loosening")),
        "subindices": {k: g(k) for k in ("nfci_risk", "nfci_credit", "nfci_leverage")
                       if g(k) is not None},
        "stlfsi": g("stlfsi"),
    }

    # recession risk
    rc = cfg["recession"]
    rr = g("recession_risk")
    recession = {
        "score": rr,
        "label": (None if rr is None else
                  ("high" if rr >= rc["high_score"] else
                   ("elevated" if rr >= rc["elevated_score"] else "low"))),
        "components": {k.replace("recession_", ""): g(k) for k in fr.columns
                       if k.startswith("recession_") and k != "recession_risk" and g(k) is not None},
        "curve_raw": g("curve_raw"),
        "curve_tp_adjusted": g("curve_tp_adj"),
        "sahm": _last(_col(f, "sahm")),
        "ebp": _last(_col(f, "ebp")),
        "ny_fed_prob": _last(_col(f, "recession_prob")),
    }
    # the headline insight: term premium can invert the curve without recession
    cr, ca = recession["curve_raw"], recession["curve_tp_adjusted"]
    if cr is not None and ca is not None:
        recession["curve_note"] = (
            "raw curve inverted but term-premium-adjusted slope is positive "
            "(low term premium, not a recession signal)"
            if cr < 0 <= ca else
            "raw and term-premium-adjusted curve agree")

    # growth nowcast
    wei = _last(_col(f, "wei"))
    wei_s = _col(f, "wei")
    wei_chg = (None if wei_s is None else _last(wei_s - wei_s.shift(65)))
    growth = {
        "wei": wei,
        "wei_trend": (None if wei_chg is None else ("rising" if wei_chg > 0 else "falling")),
        "gdpnow": _last(_col(f, "gdpnow")),
    }

    # real-activity / labor nowcast — leading reads that front-run monthly PAYEMS
    lw = cfg.get("labor", {})
    cyoy = g("claims_yoy")
    ichg = g("indeed_chg")
    wyoy = g("withheld_tax_yoy")
    labor = {
        "initial_claims_4wk": _last(_col(f, "initial_claims_4wk")),
        "continued_claims": _last(_col(f, "continued_claims")),
        "claims_yoy_pct": cyoy,
        "claims_z": g("claims_z"),
        # claims RISING => labor cooling (more separations)
        "claims_trend": (None if cyoy is None else ("rising" if cyoy > 0 else "falling")),
        "indeed_postings": _last(_col(f, "indeed_postings")),
        "indeed_chg_3m_pct": ichg,
        # postings FALLING => labor demand softening
        "indeed_trend": (None if ichg is None else ("rising" if ichg > 0 else "falling")),
        "withheld_tax_yoy_pct": wyoy,        # nominal, trailing ~3m of deposit days
        "income_trend": (None if wyoy is None else ("rising" if wyoy > 0 else "falling")),
    }
    cooling_votes = sum(bool(v) for v in (
        cyoy is not None and cyoy >= lw.get("claims_yoy_warn_pct", 10.0),
        ichg is not None and ichg <= lw.get("indeed_chg_warn_pct", -5.0),
        wyoy is not None and wyoy < 0))
    firm_votes = sum(bool(v) for v in (
        cyoy is not None and cyoy <= 0,
        ichg is not None and ichg >= 0,
        wyoy is not None and wyoy >= 2.0))
    if any(v is not None for v in (cyoy, ichg, wyoy)):
        labor["read"] = ("labor cooling" if cooling_votes >= 2 else
                         ("labor firm" if firm_votes >= 2 else "labor mixed"))

    # inflation nowcast: persistent (sticky) vs transitory (flexible)
    sm = cfg["inflation_nowcast"]["smooth_months"]
    sticky = _col(f, "sticky_cpi")
    flex = _col(f, "flex_cpi")
    inflation = {}
    if sticky is not None:
        sa = _ann_monthly_pct(sticky, sm)
        inflation["sticky_ann"] = _last(sa)
        prev = sa.dropna()
        inflation["sticky_trend"] = (
            "accelerating" if len(prev) > 70 and prev.iloc[-1] > prev.iloc[-65] else "cooling")
    if flex is not None:
        inflation["flexible_ann"] = _last(_ann_monthly_pct(flex, sm))
    inflation["median_cpi"] = _last(_col(f, "median_cpi"))
    inflation["umich_1y_exp"] = _last(_col(f, "umich_infl_exp"))
    if "sticky_ann" in inflation and "flexible_ann" in inflation \
            and inflation["sticky_ann"] is not None and inflation["flexible_ann"] is not None:
        inflation["read"] = (
            "persistent (sticky-led)" if inflation["sticky_ann"] >= inflation["flexible_ann"]
            else "transitory (flexible-led)")

    # risk-appetite layer
    vrp = g("vrp")
    vix_term = g("vix_term")
    sb = g("stock_bond_corr")
    roro = g("roro")
    rcfg = cfg["roro"]
    risk = {
        "vrp": vrp,
        "vrp_pctile": g("vrp_pctile"),
        "vrp_state": (None if vrp is None else
                      ("stress (realized > implied)" if vrp < cfg["vrp"]["stress_level"]
                       else ("rich (vol overpriced)" if (g("vrp_pctile") or 0) > 0.7 else "normal"))),
        "realized_vol": g("realized_vol"),
        "vix_term": vix_term,
        "vix_term_state": (None if vix_term is None else
                           ("backwardation (stress)" if vix_term >= cfg["term_structure"]["backwardation_ratio"]
                            else "contango (calm)")),
        "skew": g("skew"),
        "skew_pctile": g("skew_pctile"),
        "stock_bond_corr": sb,
        "stock_bond_regime": (None if sb is None else
                              ("breakdown (bonds not hedging)" if sb > cfg["corr"]["high"]
                               else ("diversifying (bonds hedge)" if sb < cfg["corr"]["low"] else "mixed"))),
        "roro": roro,
        "roro_state": (None if roro is None else
                       ("risk-on" if roro > rcfg["risk_on"] else
                        ("risk-off" if roro < rcfg["risk_off"] else "neutral"))),
        "vol_target_scalar": g("vol_target_scalar"),
        # SF Fed Daily News Sentiment: a quant complement to the LLM digests.
        # Surfaced as its own read — NOT folded into the roro composite above, to
        # keep that gauge stable until this leg is separately validated.
        "news_sentiment": g("news_sentiment"),
        "news_sentiment_z": g("news_sentiment_z"),
        "news_sentiment_state": (None if g("news_sentiment") is None else
                                 ("optimistic" if (g("news_sentiment") or 0) > 0 else "pessimistic")),
    }

    # drawdown-risk gauge (MEASURED §6: >=80 -> P(>=10% dd/63d) ~45% vs 13% base)
    dcfg = cfg["drawdown_risk"]
    dr = g("drawdown_risk")
    drawdown = {
        "score": dr,
        "band": (None if dr is None else
                 ("extreme" if dr >= dcfg["extreme"] else
                  ("high" if dr >= dcfg["high"] else
                   ("elevated" if dr >= dcfg["elevated"] else "low")))),
        # measured P(>=10% drawdown in 63d) per band (this engine's own backtest)
        "dd10_prob_pct": (None if dr is None else
                          (38 if dr >= dcfg["extreme"] else (36 if dr >= dcfg["high"]
                           else (26 if dr >= dcfg["elevated"] else 8)))),
        "base_rate_pct": 8,
    }

    # capitulation gauge (MEASURED §6: fired -> mean-reversion bounce)
    cap = g("capitulation_score")
    fired = [n for n, v in (("VRP extreme", (g("vrp_pctile") or 0) > cfg["capitulation"]["vrp_pctile"]),
                            ("VIX panic", (_last(_col(f, "vix")) or 0) > cfg["capitulation"]["vix_panic"]))
             if v]
    # value-vs-growth style tilt (MEASURED §6: 10y rising -> value)
    yc = g("yield_chg_1m")
    style = {
        "yield_chg_1m_bp": None if yc is None else round(yc * 100, 0),
        "tilt": (None if yc is None else
                 ("value" if yc > 0.10 else ("growth" if yc < -0.10 else "neutral"))),
        "driver": "10y yield direction",
        # measured: yield rising >10bp/mo -> value beat growth +0.84%/63d (t=+3.0)
        "measured": "rising 10y -> value (+0.84%/63d, t=+3.0, all 4 sub-periods); Q1->value, Q4->growth",
    }

    strong = bool(cap and cap >= 2)
    capitulation = {
        "score": None if cap is None else int(cap),
        "active": bool(cap and cap >= 1),
        "strong": strong,
        "signals_firing": fired,
        # measured forward-63d bounce (this engine's own backtest): >=1 signal
        # +4.5% / 75% positive; >=2 (stacked) +9.3% / 86% — vs +2.8% base.
        "measured_bounce_pct": 9.3 if strong else 4.5,
        "measured_hit_pct": 86 if strong else 75, "base_rate_pct": 2.8,
    }

    return {
        "financial_conditions": fin,
        "recession": recession,
        "growth_nowcast": growth,
        "labor_nowcast": labor,
        "inflation_nowcast": inflation,
        "risk_appetite": risk,
        "drawdown_risk": drawdown,
        "capitulation": capitulation,
        "style_tilt": style,
    }


# --- Macro-risk score (MRS) + per-sector sensitivity -------------------------
# ONE deterministic risk-OFF gauge in [0,1] folded from the already-computed
# conditions/regime legs, plus a coarse per-sector sensitivity. The overlay that
# consumes these (engine.technicals sector heat + engine.cycles per-stock ladder)
# is SUBTRACT-ONLY and framed as drawdown/sizing caution, never alpha — the
# cross-sectional macro edge is unproven (research/DISLOCATION_VALIDATION.md).
# MRS reads only already-lagged fields, so it adds no new look-ahead surface.
# See research/MACRO_RISK_INTEGRATION.md.

def _mrs_weights() -> dict:
    w = (config.load()["engine"].get("macro_overlay") or {}).get("mrs_weights") or {}
    # The `liquidity` leg (contracting half only) is KEPT deliberately: net-liquidity
    # withdrawal is the single mechanism that most differentially hurts cyclicals,
    # and the B-1 sign-check (scripts/research_macro_sector.py) only clears the
    # split-half bar WITH it — removing it strips out the 2018/2022 QT episodes where
    # the cross-sectional signal lives. Net liquidity ALSO has a uniform per-name
    # ladder nudge (cycles.LIQ_HEADWIND); the MRS leg adds SECTOR differentiation on
    # top of that — a small, bounded (~1pt), intentional overlap, not a bug.
    return {"recession": w.get("recession", 1.0), "drawdown": w.get("drawdown", 1.0),
            "nfci": w.get("nfci", 0.5), "liquidity": w.get("liquidity", 0.5),
            "transition": w.get("transition", 0.25)}


def _mrs_label(score: float | None) -> str | None:
    if score is None:
        return None
    return ("severe" if score >= 0.75 else "elevated" if score >= 0.5
            else "moderate" if score >= 0.25 else "low")


def _mrs_transition_val(state) -> float:
    return (1.0 if state in ("TRANSITIONING", "NEW_REGIME")
            else 0.5 if state == "WEAKENING" else 0.0)


def _combine_legs(legs: dict, w: dict):
    """Weighted mean over AVAILABLE legs (renormalized), scalar or pandas. Each leg
    is (value, available); an unavailable leg drops out of BOTH numerator and
    denominator instead of poisoning the score."""
    is_series = any(isinstance(v, pd.Series) for v, _a in legs.values())
    if is_series:
        num = sum(v.fillna(0.0) * a.astype(float) * w.get(n, 0.0)
                  for n, (v, a) in legs.items())
        den = sum(a.astype(float) * w.get(n, 0.0) for n, (_v, a) in legs.items())
        return (num / den.replace(0, np.nan)).clip(0, 1)
    num = den = 0.0
    for n, (v, a) in legs.items():
        if not a or v is None:
            continue
        num += w.get(n, 0.0) * float(v)
        den += w.get(n, 0.0)
    return (num / den) if den > 0 else None


def macro_risk_score(latest: dict) -> dict:
    """Aggregate macro-risk score MRS in [0,1] from a latest.json-shaped dict (the
    dict-path helper). Higher => more macro risk. Pure function of already-lagged
    fields — no new data, no look-ahead. Renormalizes over available legs. Returns
    {score, label, components}.

    NOTE: the engine persists latest['macro_risk'] via macro_risk_snapshot(f,
    regime), NOT this function, because `latest` can mix legs across release dates
    on a cadence-lag day (quad stale while conditions update). This helper is exact
    for a date-coherent `latest` and is retained for dict-only consumers + tests."""
    w = _mrs_weights()
    cond = (latest or {}).get("conditions") or {}
    legs: dict[str, tuple[float | None, bool]] = {}
    rec = (cond.get("recession") or {}).get("score")
    legs["recession"] = (None if rec is None else min(max(rec / 100.0, 0.0), 1.0),
                         rec is not None)
    dd = (cond.get("drawdown_risk") or {}).get("score")
    legs["drawdown"] = (None if dd is None else min(max(dd / 100.0, 0.0), 1.0),
                        dd is not None)
    fc = cond.get("financial_conditions") or {}
    nfci, nfci_pct = fc.get("nfci"), fc.get("nfci_pctile")
    if nfci is not None and nfci_pct is not None:
        tightening = fc.get("trend") == "tightening" and nfci > 0
        legs["nfci"] = (min(max(nfci_pct if tightening else 0.0, 0.0), 1.0), True)
    else:
        legs["nfci"] = (None, False)
    liq = (latest or {}).get("liquidity_overlay")
    legs["liquidity"] = (1.0 if liq == "contracting" else 0.0, liq is not None)
    tr = (latest or {}).get("transition_state")
    legs["transition"] = (_mrs_transition_val(tr), tr is not None)

    score = _combine_legs(legs, w)
    comps = {n: (None if v is None else round(float(v), 3)) for n, (v, _a) in legs.items()}
    return {"score": None if score is None else round(float(score), 4),
            "label": _mrs_label(score), "components": comps}


def _macro_risk_legs(f: pd.DataFrame, regime: pd.DataFrame):
    """Daily (value, available) Series per MRS leg, from the causal conditions_frame
    + regime labels. THE single source of truth for both the historical series and
    the live snapshot, so they cannot drift. No look-ahead (conditions_frame is
    causal; transition is an already-lagged label)."""
    cf = conditions_frame(f)
    idx = cf.index
    legs: dict[str, tuple[pd.Series, pd.Series]] = {}
    rr = cf["recession_risk"] if "recession_risk" in cf else None
    if rr is not None:
        legs["recession"] = ((rr / 100.0).clip(0, 1), rr.notna())
    dd = cf["drawdown_risk"] if "drawdown_risk" in cf else None
    if dd is not None:
        legs["drawdown"] = ((dd / 100.0).clip(0, 1), dd.notna())
    if {"nfci", "nfci_pctile", "nfci_chg"} <= set(cf.columns):
        tightening = (cf["nfci_chg"] > 0) & (cf["nfci"] > 0)
        # availability mirrors the scalar path: the leg needs BOTH the level and
        # its 5y percentile (the latter warms up slowly), else the series would keep
        # a zero leg in the denominator that the scalar drops.
        legs["nfci"] = (cf["nfci_pctile"].where(tightening, 0.0).clip(0, 1),
                        cf["nfci"].notna() & cf["nfci_pctile"].notna())
    if "liquidity" in regime.columns:
        liq = regime["liquidity"].reindex(idx)
        legs["liquidity"] = ((liq == "contracting").astype(float), liq.notna())
    if "transition_state" in regime.columns:
        tr = regime["transition_state"].reindex(idx)
        val = pd.Series(0.0, index=idx)
        val = val.mask(tr == "WEAKENING", 0.5)
        val = val.mask(tr.isin(("TRANSITIONING", "NEW_REGIME")), 1.0)
        legs["transition"] = (val, tr.notna())
    return legs, idx


def macro_risk_series(f: pd.DataFrame, regime: pd.DataFrame) -> pd.Series:
    """Daily MRS in [0,1] across history — what calibrate() folds into the honesty
    bands. Shares _macro_risk_legs with macro_risk_snapshot, so the live value and
    the bands cannot diverge."""
    legs, idx = _macro_risk_legs(f, regime)
    if not legs:
        return pd.Series(index=idx, dtype=float)
    return _combine_legs(legs, _mrs_weights())


def macro_risk_snapshot(f: pd.DataFrame, regime: pd.DataFrame) -> dict:
    """The LIVE macro-risk reading the engine persists to latest['macro_risk'].
    Derived from the SAME series calibrate() uses (one coherent as-of date), so
    live == calibrate by construction — unlike building it from a possibly
    cadence-mismatched latest.json dict. Returns {score, label, components}."""
    legs, _idx = _macro_risk_legs(f, regime)
    series = macro_risk_series(f, regime).dropna()
    if series.empty:
        return {"score": None, "label": None, "components": {}}
    last = series.index[-1]
    score = float(series.iloc[-1])
    comps = {n: (round(float(v.loc[last]), 3) if bool(a.loc[last]) else None)
             for n, (v, a) in legs.items()}
    return {"score": round(score, 4), "label": _mrs_label(score), "components": comps}


def sector_macro_beta(key) -> float:
    """Per-sector sensitivity to a risk-OFF macro reading, in [-1, +1]. Keyed by
    SPDR ticker (sector pages) OR GICS / display sector name (stock library);
    0.0 for anything not in the table (ETFs, factors, unknowns). The lookup is
    case-insensitive on names so spelling variants still resolve."""
    if not key:
        return 0.0
    tbl = config.load()["engine"]["confluence"].get("sector_macro_beta") or {}
    if key in tbl:
        return float(tbl[key])
    lk = str(key).strip().lower()
    for k, v in tbl.items():
        if str(k).strip().lower() == lk:
            return float(v)
    return 0.0
