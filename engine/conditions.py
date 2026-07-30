"""Complementary macro-conditions / nowcast / risk-appetite layer.

This module is ADDITIVE. It runs alongside the split-half-validated growth/
inflation quad (engine/regime.py) and never alters it — it gives the dashboard a
second, independent lens built from the Fed-research feeds and option-implied
risk that the price-based quad lacks:

  • Financial Conditions  — Chicago Fed NFCI (+ risk/credit/leverage subindices)
                            and St. Louis stress: one broad z-scored gauge.
  • Recession risk        — a 0..100 composite of jobless CLAIMS (the validated
                            labor leg; Sahm is the graceful fallback only when the
                            claims feed is absent), the smoothed recession
                            probability, the Excess Bond Premium model prob + level,
                            and a term-premium-ADJUSTED curve slope (strips the
                            2022-24 false inversion from a low/negative term premium).
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

import functools
import json
import logging

import numpy as np
import pandas as pd

from engine.indicators import pct_rank_window
from lib import config, store

log = logging.getLogger("conditions")


# --- drawdown-risk band table: the PIT-frame RE-ISSUED numbers (audit #39) -----
# The band P(>=10% dd / 63d) table was re-measured on the leak-free PIT frame ('release')
# with the LIVE composition (jobless CLAIMS, not the retired Sahm leg) by
# scripts/validate_drawdown_risk_pit.py. The old 8/26/36/38 table was measured on
# latest-revised data + the pre-claims composition and reproduced NEITHER the live frame
# NOR the live definition (it also implicitly used a point-to-point return, while the
# label says "drawdown"). The re-issued table is stronger AND monotone. These constants
# are the committed fallback; if the artifact is present it is read live so a re-run
# updates the site without a code change. Passport travels with the numbers.
_DRAWDOWN_BAND_PIT_FALLBACK = {
    "base": 19, "low": 11, "elevated": 28, "high": 36, "extreme": 49,
    "frame": "pit", "measure_span": "1993-2026",
    "n_base": 8718, "n_extreme": 953,
}


@functools.lru_cache(maxsize=1)
def _drawdown_band_table() -> dict:
    """Re-issued per-band P(>=10% dd/63d) on the PIT ('release') frame, read from the
    committed artifact (data/regime/drawdown_risk_pit.json) if present, else the pinned
    fallback. Carries a measured-basis passport {basis, frame, n, span}."""
    try:
        p = config.data_dir() / "regime" / "drawdown_risk_pit.json"
        if p.exists():
            d = json.loads(p.read_text())
            rel = d.get("frames", {}).get("release", {}).get("bands", {})
            pas = d.get("passport", {})
            if rel and rel.get("extreme", {}).get("hit_pct") is not None:
                return {
                    "base": round(rel["_base"]["hit_pct"]),
                    "low": round(rel["low"]["hit_pct"]),
                    "elevated": round(rel["elevated"]["hit_pct"]),
                    "high": round(rel["high"]["hit_pct"]),
                    "extreme": round(rel["extreme"]["hit_pct"]),
                    "n_base": rel["_base"]["n_obs"], "n_extreme": rel["extreme"]["n_obs"],
                    "frame": "pit", "labor_leg": pas.get("labor_leg", "claims"),
                    "measure_span": "–".join(d["frames"]["release"].get("span", [])) or None,
                }
    except Exception:  # noqa: BLE001 — artifact is best-effort; fall back to pinned
        pass
    return dict(_DRAWDOWN_BAND_PIT_FALLBACK)


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


def _smooth_annual_rate(s: pd.Series, smooth_months: int) -> pd.Series:
    """Smooth an ALREADY-annualized monthly rate over N distinct monthly prints.

    The Atlanta-Fed sticky/flexible CPI inputs (FRED STICKCPIM157SFRBATL /
    FLEXCPIM157SFRBATL) are published as 'Percent Change at Annual Rate' — i.e.
    ALREADY annual-rate (~2-6%). They must NOT be re-annualized (a prior version
    applied ((1+x/100)**12-1)*100, which turned 3.2% into ~46%). The daily feature
    frame carries each month's value forward-filled, so we de-duplicate to the actual
    monthly observations, take the rolling mean, then re-broadcast onto the daily
    index — units unchanged."""
    monthly = s.dropna()
    # collapse consecutive identical ffilled values to one print per monthly change
    distinct = monthly[monthly.ne(monthly.shift())]
    sm = distinct.rolling(smooth_months, min_periods=1).mean()
    return sm.reindex(s.index).ffill()


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

    # Systemic stress — OFR FSI (level + functional + regional) + CP spreads ---
    # OFR FSI is a daily 33-variable global stress gauge with a built-in functional
    # decomposition NFCI lacks; the Funding leg embeds a free x-ccy-basis proxy and
    # the EM leg is additive. Coincident gauge -> DISPLAY + an optional, separately-
    # validated risk-OFF gate; never cross-sectional alpha. (research/DATA_SIGNAL_EXPANSION_2026.md)
    scfg = cfg.get("systemic_stress", {})
    fsi = _col(f, "ofr_fsi")
    if fsi is not None:
        out["ofr_fsi"] = fsi
        out["ofr_fsi_pctile"] = pct_rank_window(fsi, scfg.get("fsi_pctile_lookback_d", 1260))
        out["ofr_fsi_chg"] = fsi - fsi.shift(scfg.get("fsi_change_window_d", 65))
    for sub in ("ofr_fsi_credit", "ofr_fsi_equity", "ofr_fsi_safe", "ofr_fsi_funding",
                "ofr_fsi_vol", "ofr_fsi_us", "ofr_fsi_oae", "ofr_fsi_em"):
        s = _col(f, sub)
        if s is not None:
            out[sub] = s
    # Commercial-paper spreads (bps): A2/P2 = lower-tier minus top-tier CP (credit
    # quality); CP-bill = top-tier CP minus the 3m bill (funding / liquidity).
    # bill leg = us3m_bill (DTB3, discount basis) — basis-matched to the CP legs, which
    # the Fed quotes as annual discount yields. Deliberately NOT the us3m curve node
    # (DGS3MO, bond-equivalent): that runs ~13bp rich by convention alone and would
    # narrow the funding spread for a reason that is not funding stress.
    cp_look = scfg.get("cp_pctile_lookback_d", 1260)
    aa_cp, a2p2, bill = _col(f, "aa_cp_90d"), _col(f, "a2p2_cp_90d"), _col(f, "us3m_bill")
    if aa_cp is not None and a2p2 is not None:
        out["a2p2_spread"] = (a2p2 - aa_cp) * 100.0
        out["a2p2_spread_pctile"] = pct_rank_window(out["a2p2_spread"], cp_look)
    if aa_cp is not None and bill is not None:
        out["cp_bill_spread"] = (aa_cp - bill) * 100.0
        out["cp_bill_spread_pctile"] = pct_rank_window(out["cp_bill_spread"], cp_look)

    # Recession risk composite (0..100) --------------------------------------
    rc = cfg["recession"]
    w = rc["weights"]
    parts: dict[str, tuple[pd.Series, float]] = {}
    # (labor leg — jobless claims primary, Sahm fallback — added after the others below)
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
    # Labor leg — jobless CLAIMS is the primary signal (research/CLAIMS_RECESSION_VALIDATION.md:
    # claims beats the Sahm leg standalone AND in-composite at every horizon, robust to
    # point-in-time; REPLACE > AUGMENT > Sahm-only across all data modes). YoY of the 4wk-MA
    # level, recession-ward. SAHM is the graceful FALLBACK — used only when the claims feed is
    # unavailable, so the composite is never left without a labor leg (and claims-free frames
    # are unaffected). Both config-gated (weight 0 disables).
    w_claims = w.get("claims", 0.0)
    claims4 = _col(f, "initial_claims_4wk")
    if claims4 is None:
        claims4 = _col(f, "initial_claims")
    use_claims = claims4 is not None and w_claims > 0
    if use_claims:
        claims_yoy = claims4 / claims4.shift(rc.get("claims_yoy_window_d", 252)) - 1.0
        parts["claims"] = ((claims_yoy / rc.get("claims_yoy_full", 0.40)).clip(0, 1), w_claims)
    sahm = _col(f, "sahm")
    if sahm is not None and w.get("sahm", 0.0) > 0 and not use_claims:
        parts["sahm"] = ((sahm / rc["sahm_full"]).clip(0, 1), w["sahm"])
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
    # canon.vix_term (audit #12): the ONE VIX/VIX3M basis, shared with vol_regime.ts_slope
    # and vol_shock._f_vix_term so the three surfaces read one series, not three copies.
    vix3m = _col(f, "vix3m")
    if vix is not None and vix3m is not None:
        from engine import canon
        out["vix_term"] = canon.vix_term(vix, vix3m)

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
    # Each leg is the SIGNED contribution exactly as it enters the equal-weight
    # mean (six risk/fear legs negated, copper/gold positive). The legs are also
    # stored as out["roro_<key>"] columns so a DISPLAY-ONLY decomposition can read
    # the per-leg contributions straight back (mean(roro_*) == roro) without
    # recomputing them — consumed by the display-only Fear/Euphoria decomposition
    # in scripts/build_site.py. Additive columns only; never scored — nothing in
    # axes / regime / macro_risk reads them.
    zw = cfg["roro"]["z_window_d"]
    roro_legs: dict[str, pd.Series] = {}
    if vix is not None:
        roro_legs["vix"] = -_z(vix, zw)
    hy = _col(f, "hy_oas")
    if hy is not None:
        roro_legs["hy_oas"] = -_z(hy, zw)
    if skew is not None:
        roro_legs["skew"] = -_z(skew, zw)
    if "vix_term" in out:
        roro_legs["vix_term"] = -_z(out["vix_term"], zw)
    if nfci is not None:
        roro_legs["nfci"] = -_z(nfci, zw)
    cg = _col(f, "copper_gold")
    if cg is not None:
        roro_legs["copper_gold"] = _z(cg, zw)
    dxy = _col(f, "dxy")
    if dxy is not None:
        roro_legs["dxy"] = -_z(dxy.pct_change(20, fill_method=None), zw)
    if roro_legs:
        for _k, _s in roro_legs.items():
            out[f"roro_{_k}"] = _s
        out["roro"] = pd.concat(list(roro_legs.values()), axis=1).mean(axis=1)

    # Volatility-target exposure scalar ---------------------------------------
    tcfg = cfg["vol_target"]
    if spy is not None:
        rv = spy.pct_change(fill_method=None).rolling(
            tcfg["realized_window_d"]).std() * np.sqrt(252) * 100
        out["vol_target_scalar"] = (tcfg["target_vol_pct"] / rv).clip(tcfg["floor"], tcfg["cap"])

    # Drawdown-risk gauge (lean 4-factor macro stress, 0..100) ----------------
    # RE-ISSUED (audit #39, PIT frame + claims composition): extreme band ->
    # P(>=10% dd/63d) ~49% vs ~19% base (scripts/validate_drawdown_risk_pit.py). Each
    # component z-scored (causal, expanding-capped rolling), averaged, mapped to
    # an expanding percentile so the gauge is 0..100 with no look-ahead.
    dcfg = cfg["drawdown_risk"]
    src = {"recession_risk": out.get("recession_risk"), "nfci": nfci,
           "ebp": _col(f, "ebp"), "hy_oas": _col(f, "hy_oas")}
    _dd_keys = [k for k in src if k in dcfg["components"] and src[k] is not None]
    zlegs = [_z(src[k], dcfg["z_lookback_d"]) for k in _dd_keys]
    if len(zlegs) >= 2:
        _zf = pd.concat(zlegs, axis=1)
        comp = _zf.mean(axis=1)
        out["drawdown_risk"] = (comp.expanding(min_periods=252).rank(pct=True) * 100)
        # PER-ROW COMPOSITION (audit 2026-07-29). The row-mean silently skips whichever z-legs
        # are NaN that day, so when the NFCI print ages out of inputs.py's ffill_limit the gauge
        # keeps printing off 3 legs while the payload still claims the validated 4-leg basis
        # ("recession_risk, NFCI, EBP, HY OAS") AND ships a stat_passport of {basis: measured,
        # n_base: 8718} measured on that 4-leg composition. Counting the resolved legs per row is
        # what lets conditions_snapshot degrade the CLAIM instead of the number.
        out["drawdown_risk_nlegs"] = _zf.notna().sum(axis=1).astype(float)
        for k, zl in zip(_dd_keys, zlegs):
            # SOURCE presence drives the CLAIM (is there a current print for this input?) —
            # that is the condition the payload's basis string asserts.
            out[f"drawdown_risk_src_{k}"] = src[k].notna().astype(float)
            # z-leg presence drives the ARITHMETIC (did this leg enter the row mean?). The two
            # differ when an input is present but degenerate (zero variance -> undefined z), so
            # both are reported rather than conflated.
            out[f"drawdown_risk_leg_{k}"] = zl.notna().astype(float)

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

    # Complacency / hidden-fragility gauge (DISPLAY-ONLY mirror of capitulation) -
    # Capitulation reads extreme FEAR -> a measured bounce. This reads the
    # opposite tail: a CALM surface (cheap VIX, steep contango) over
    # DETERIORATING internals (breadth not confirming a strong tape, HY credit
    # quietly widening) — the 'calm but fragile' backdrop. Stored as additive
    # columns; surfaced as CONTEXT only — never folded into recession_risk /
    # drawdown_risk / RORO / MRS / any axis. 'Low VIX' is persistent and
    # ~neutral on forward returns, so this is explicitly NOT a timing signal
    # (which is also why the RORO composite above gates nothing).
    mcfg = cfg["complacency"]
    calm_legs, frag_legs = [], []
    if vix is not None:
        out["vix_pctile"] = pct_rank_window(vix, mcfg["vix_pctile_lookback_d"])
        calm_legs.append((out["vix_pctile"] < mcfg["vix_calm_pctile"]).astype(float))
    if "vix_term" in out:
        calm_legs.append((out["vix_term"] < mcfg["contango_calm"]).astype(float))
    # breadth not confirming: index near its 1y high while %>200dma sits in a low
    # percentile (a thinning tape — fewer stocks carrying the index).
    if spy is not None:
        out["spy_high_prox"] = spy / spy.rolling(252, min_periods=120).max()
    b200 = _col(f, "pct_above_200")
    if b200 is not None:
        out["breadth_above200_pctile"] = pct_rank_window(b200, mcfg["breadth_pctile_lookback_d"])
    if "spy_high_prox" in out and "breadth_above200_pctile" in out:
        frag_legs.append(((out["spy_high_prox"] >= mcfg["breadth_high_prox"]) &
                          (out["breadth_above200_pctile"] < mcfg["breadth_weak_pctile"])).astype(float))
    # credit not confirming the calm: HY OAS widening (risk being quietly repriced)
    if hy is not None:
        out["hy_oas_chg_21d"] = hy.diff(mcfg["credit_widen_window_d"])
        frag_legs.append((out["hy_oas_chg_21d"] > 0).astype(float))
    if calm_legs:
        out["complacency_calm"] = pd.concat(calm_legs, axis=1).sum(axis=1)
    if frag_legs:
        out["complacency_fragility"] = pd.concat(frag_legs, axis=1).sum(axis=1)

    return out


# --- snapshot dict (for latest.json + panels) --------------------------------
def _band(v: float | None, lo: float, hi: float, names: tuple[str, str, str]) -> str | None:
    if v is None:
        return None
    return names[0] if v < lo else (names[2] if v >= hi else names[1])


# Per-input VINTAGE reporting (audit 2026-07-29). The frame ffills slow macro series onto trading
# days (engine/inputs.py `put(..., ffill_limit=N)`), so every column carries the frame's own
# calendar date and NOTHING downstream could tell a fresh print from a 12-day-old one carried
# forward — the NFCI hole that silently narrowed the drawdown composite was invisible for exactly
# this reason. `vintages` reports the LAST DATE EACH INPUT ACTUALLY PRINTED, so a surface (and
# market_state's freshness stamp) can stop self-certifying off the price calendar.
# (key in payload, frame column, plain label, max age in CALENDAR days before genuinely late)
# The ages are DISCLOSURE thresholds, never signal gates — each is the longest a HEALTHY feed can
# legitimately go between prints, so `stale: true` means "later than this publisher ever is", not
# "older than we would like". NFCI/ANFCI/STLFSI are weekly with a Friday observation date
# published the FOLLOWING Wednesday, so a healthy print is routinely 11-12 days old by the Tuesday
# before the next release — 14 leaves one day of headroom without hiding a real miss. EBP is
# monthly with roughly a month of publication lag (an observation dated the 1st routinely arrives
# ~8 weeks later), hence 70.
_VINTAGE_INPUTS = (
    ("nfci", "nfci", "NFCI (financial conditions)", 14),
    ("anfci", "anfci", "ANFCI (adjusted)", 14),
    ("stlfsi", "stlfsi", "St. Louis Fed stress index", 14),
    ("hy_oas", "hy_oas", "High-yield OAS", 5),
    ("ebp", "ebp", "Excess bond premium", 70),
    ("ofr_fsi", "ofr_fsi", "OFR financial stress index", 6),
    ("vix", "vix", "VIX", 5),
    ("vix_term", "vix_ratio", "VIX term structure", 5),
    ("pct_above_200", "pct_above_200", "Breadth (%>200dma)", 5),
    ("us10y", "us10y", "10-year Treasury yield", 5),
    ("recession_risk", None, "Recession-risk composite", 7),
)


def _input_vintages(f: pd.DataFrame, fr: pd.DataFrame) -> dict:
    """{key: {asof, age_days, stale, label, cadence_days}} — the last date each macro input
    ACTUALLY printed, measured against the frame's own last session (never the wall clock).
    `stale` = the print is older than its expected cadence. Never raises."""
    out: dict = {}
    try:
        ref = pd.Timestamp(f.index.max())
        for key, col, label, cadence in _VINTAGE_INPUTS:
            s = None
            if col is not None and col in f.columns:
                s = f[col]
            elif key in fr.columns:
                s = fr[key]
            elif col is None and key in fr.columns:
                s = fr[key]
            if s is None:
                out[key] = {"asof": None, "age_days": None, "stale": None,
                            "label": label, "cadence_days": cadence}
                continue
            sd = s.dropna()
            if sd.empty:
                out[key] = {"asof": None, "age_days": None, "stale": None,
                            "label": label, "cadence_days": cadence}
                continue
            # the ffilled frame repeats the last print, so the VINTAGE is the last date the
            # value CHANGED-or-began, not the last non-NaN row. Collapse repeats first.
            distinct = sd[sd.ne(sd.shift())]
            last = pd.Timestamp(distinct.index.max())
            age = int((ref - last).days)
            out[key] = {"asof": str(last.date()), "age_days": age,
                        "stale": bool(age > cadence), "label": label,
                        "cadence_days": cadence}
    except Exception as e:  # noqa: BLE001 — disclosure block, never fatal
        log.warning("conditions input-vintage read failed: %s", e)
    return out


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

    # systemic stress — OFR FSI decomposition + commercial-paper spreads.
    # The functional/regional split lets a stress read NAME the channel; the LLM
    # cross-asset narrator ingests this to explain why six markets move as one.
    scfg = cfg.get("systemic_stress", {})
    elevated_p, acute_p = scfg.get("elevated_pctile", 0.80), scfg.get("acute_pctile", 0.95)
    fsi, fsi_p, fsi_chg = g("ofr_fsi"), g("ofr_fsi_pctile"), g("ofr_fsi_chg")

    def _r(name):
        v = g(name)
        return None if v is None else round(v, 3)
    functional = {k: _r(c) for k, c in
                  (("credit", "ofr_fsi_credit"), ("equity_valuation", "ofr_fsi_equity"),
                   ("safe_assets", "ofr_fsi_safe"), ("funding", "ofr_fsi_funding"),
                   ("volatility", "ofr_fsi_vol")) if _r(c) is not None}
    regional = {k: _r(c) for k, c in
                (("united_states", "ofr_fsi_us"), ("other_advanced", "ofr_fsi_oae"),
                 ("emerging_markets", "ofr_fsi_em")) if _r(c) is not None}
    _driver_label = {"credit": "Credit", "equity_valuation": "Equity valuation",
                     "safe_assets": "Safe assets", "funding": "Funding (offshore-$ / x-ccy)",
                     "volatility": "Volatility"}
    # name a leading channel only when stress is above its long-run average (fsi>0)
    leading = (max(functional, key=functional.get)
               if functional and fsi is not None and fsi > 0 else None)
    a2p2, a2p2_p = g("a2p2_spread"), g("a2p2_spread_pctile")
    cpbill, cpbill_p = g("cp_bill_spread"), g("cp_bill_spread_pctile")
    cp_p = max([p for p in (a2p2_p, cpbill_p) if p is not None], default=None)
    systemic_stress = {
        "ofr_fsi": None if fsi is None else round(fsi, 3),
        "ofr_fsi_pctile": fsi_p,
        "ofr_fsi_change_13w": None if fsi_chg is None else round(fsi_chg, 3),
        "state": (None if fsi_p is None else
                  ("acute" if fsi_p >= acute_p else
                   ("elevated" if fsi_p >= elevated_p else
                    ("normal" if (fsi or 0) >= 0 else "calm")))),
        "trend": (None if fsi_chg is None else ("rising" if fsi_chg > 0 else "easing")),
        "functional": functional,
        "regional": regional,
        "leading_driver": None if leading is None else _driver_label.get(leading, leading),
        "leading_driver_key": leading,
        "a2p2_spread_bps": None if a2p2 is None else round(a2p2, 1),
        "a2p2_spread_pctile": a2p2_p,
        "cp_bill_spread_bps": None if cpbill is None else round(cpbill, 1),
        "cp_bill_spread_pctile": cpbill_p,
        "cp_stress": (None if cp_p is None else
                      ("acute" if cp_p >= acute_p else ("elevated" if cp_p >= elevated_p else "normal"))),
        # lead/lag honesty: OFR FSI is a coincident gauge (see evidence below).
        "lead_lag": "coincident",
        "evidence": ("OFR Financial Stress Index: a daily 33-variable global stress gauge with "
                     "functional (credit / equity valuation / safe assets / funding / volatility) "
                     "and regional (US / other-advanced / EM) decomposition. A coincident gauge — "
                     "it names the stress CHANNEL when markets move as one; display + an optional "
                     "risk-OFF gate, never cross-sectional alpha."),
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
        sa = _smooth_annual_rate(sticky, sm)
        inflation["sticky_ann"] = _last(sa)
        prev = sa.dropna()
        inflation["sticky_trend"] = (
            "accelerating" if len(prev) > 70 and prev.iloc[-1] > prev.iloc[-65] else "cooling")
    if flex is not None:
        inflation["flexible_ann"] = _last(_smooth_annual_rate(flex, sm))
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
        # lead/lag honesty: a VIX/VIX3M level read — the most coincident vol gauge.
        "vix_term_lead_lag": "coincident",
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

    # drawdown-risk gauge — RE-ISSUED on the PIT frame + live composition (audit #39).
    # The per-band P(>=10% dd/63d) table is now the leak-free measurement (claims leg, not
    # Sahm) from scripts/validate_drawdown_risk_pit.py: base ~19% -> low 11% -> elevated 28%
    # -> high 36% -> extreme 49% (max-drawdown definition, matching the label). The old
    # 8/26/36/38 table was measured on revised data + the retired Sahm composition and
    # reproduced neither the live frame nor the live definition; see the report.
    # HONESTY (research/RISK_FLIP_2026-06-22.md): still a SLOW macro/credit composite
    # (recession_risk, NFCI, EBP, HY OAS) — it LAGS price. The low band no longer equals
    # the base rate (11% low vs 19% base): a "low" read carries mild information, but is NOT
    # a forward all-clear on price/vol risk (the leading gauges carry that). Tagged lagging.
    dcfg = cfg["drawdown_risk"]
    _dbt = _drawdown_band_table()
    dr = g("drawdown_risk")
    dr_band = (None if dr is None else
               ("extreme" if dr >= dcfg["extreme"] else
                ("high" if dr >= dcfg["high"] else
                 ("elevated" if dr >= dcfg["elevated"] else "low"))))
    # COMPOSITION HONESTY (audit 2026-07-29). The composite row-means over whichever z-legs
    # resolve, so a missing input silently narrows the gauge while the payload kept claiming the
    # validated 4-leg basis and shipping a {basis: measured, n_base: ...} passport measured on
    # THAT composition. Today conditions.financial_conditions is entirely None (the 2026-07-17
    # NFCI print aged past inputs.py's ffill_limit=7) so the gauge runs on 3 of 4 legs. When the
    # live composition differs from the validated set the band-probability claim + the passport
    # are marked PARTIAL and dd10_prob_pct is withheld: the measured table does not describe this
    # composition, and a number measured on a different gauge is not a null — it is wrong.
    _dd_expected = [k for k in ("recession_risk", "nfci", "ebp", "hy_oas")
                    if k in dcfg["components"]]
    # The CLAIM degrades on SOURCE presence — "is there a current print for this input?" is
    # exactly what the basis string asserts, and exactly the NFCI condition that triggered this.
    _dd_resolved = [k for k in _dd_expected if (g(f"drawdown_risk_src_{k}") or 0.0) >= 1.0]
    _dd_missing = [k for k in _dd_expected if k not in _dd_resolved]
    _dd_partial = bool(dr is not None and _dd_missing)
    # Separately: which legs actually entered the row mean. These differ when an input is
    # present but degenerate (zero variance -> undefined z-score); reported, never conflated
    # with a missing print, and never used to withhold the band odds.
    _dd_in_mean = [k for k in _dd_expected if (g(f"drawdown_risk_leg_{k}") or 0.0) >= 1.0]
    _dd_undefined = [k for k in _dd_resolved if k not in _dd_in_mean]
    _dd_basis_names = {"recession_risk": "recession risk", "nfci": "NFCI",
                       "ebp": "EBP", "hy_oas": "HY OAS"}
    drawdown = {
        "score": dr,
        "band": dr_band,
        # re-issued PIT-frame P(>=10% drawdown in 63d) per band (claims composition). WITHHELD
        # when the live composition is not the composition the table was measured on.
        "dd10_prob_pct": (None if (dr_band is None or _dd_partial) else _dbt[dr_band]),
        "base_rate_pct": _dbt["base"],
        # lead/lag honesty: slow macro/credit composite, lags price.
        "lead_lag": "lagging",
        "basis": ("macro/credit composite ("
                  + ", ".join(_dd_basis_names[k] for k in _dd_resolved) + ")"),
        "basis_expected": [_dd_basis_names[k] for k in _dd_expected],
        "basis_resolved": [_dd_basis_names[k] for k in _dd_resolved],
        "basis_missing": [_dd_basis_names[k] for k in _dd_missing],
        "n_legs": len(_dd_resolved),
        "n_legs_expected": len(_dd_expected),
        "n_legs_in_mean": len(_dd_in_mean),
        # input present but its z-score is undefined (zero variance) — it contributes nothing
        # to the composite even though the print exists
        "legs_undefined": [_dd_basis_names[k] for k in _dd_undefined],
        "partial": _dd_partial,
        "degraded_note_en": (
            ("Running on " + str(len(_dd_resolved)) + " of " + str(len(_dd_expected))
             + " inputs — no current print for "
             + " or ".join(_dd_basis_names[k] for k in _dd_missing)
             + ". The measured per-band pullback odds were calibrated on the full set, so they "
               "are withheld rather than restated for a narrower gauge.")
            if _dd_partial else None),
        "degraded_note_zh": (
            ("当前仅有 " + str(len(_dd_expected)) + " 项输入中的 " + str(len(_dd_resolved))
             + " 项——" + "、".join(_dd_basis_names[k] for k in _dd_missing)
             + " 暂无最新数据。每档回撤概率是在完整输入下测得的，因此暂不显示，而非改用较窄的口径重述。")
            if _dd_partial else None),
        # low band now sits BELOW base (mild info), so it is no longer a bare base-rate read.
        "is_base_rate": False,
        "dd10_prob_informative": bool(dr_band is not None and not _dd_partial),
        # passport: this band table is MEASURED on the PIT frame with the live composition —
        # but only while the LIVE composition still matches it.
        "stat_passport": {
            "basis": "partial" if _dd_partial else "measured",
            "frame": _dbt.get("frame", "pit"),
            "labor_leg": _dbt.get("labor_leg", "claims"),
            "n_base": None if _dd_partial else _dbt.get("n_base"),
            "n_extreme": None if _dd_partial else _dbt.get("n_extreme"),
            "span": _dbt.get("measure_span"),
            "measured_on": [_dd_basis_names[k] for k in _dd_expected],
            "live_composition": [_dd_basis_names[k] for k in _dd_resolved],
            "definition": "max peak-to-trough SPY decline over the next 63 trading days",
            "note": ((("PARTIAL: the band table was measured on "
                       + ", ".join(_dd_basis_names[k] for k in _dd_expected)
                       + " but the live gauge is currently running without "
                       + ", ".join(_dd_basis_names[k] for k in _dd_missing)
                       + " — N and the per-band odds are withheld because they do not describe "
                         "this composition. ") if _dd_partial else "")
                     + "Re-measured on the leak-free PIT ('release') frame with the "
                       "jobless-claims labor leg; replaces the stale 8/26/36/38 (Sahm-era, "
                       "revised-frame) table. Live gauge fires on 'latest'; its bands are within "
                       "CI of PIT. Overlap-inflated N + episode-driven high/extreme bands — a "
                       "risk read, not a crash oracle."),
        },
        "label": "Macro/credit drawdown pressure (lagging)",
        "label_zh": "宏观/信用回撤压力（滞后）",
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

    # complacency / hidden-fragility gauge — DISPLAY-ONLY mirror of capitulation.
    # A CALM surface (cheap VIX, steep contango) over WEAKENING internals
    # (breadth not confirming a strong tape, HY credit widening). The warning
    # fires only on the CONJUNCTION (calm AND weak); a calm tape on its own is
    # just calm. NEVER scored — low VIX is persistent and ~neutral on forward
    # returns, so this names a CONTEXT, not a trade.
    mcfg = cfg["complacency"]
    m_calm, m_frag = g("complacency_calm"), g("complacency_fragility")
    vp, vt = g("vix_pctile"), g("vix_term")
    prox, b2p = g("spy_high_prox"), g("breadth_above200_pctile")
    hychg = g("hy_oas_chg_21d")
    vix_low = vp is not None and vp < mcfg["vix_calm_pctile"]
    contango = vt is not None and vt < mcfg["contango_calm"]
    breadth_div = bool(prox is not None and b2p is not None
                       and prox >= mcfg["breadth_high_prox"] and b2p < mcfg["breadth_weak_pctile"])
    credit_widen = hychg is not None and hychg > 0
    c_warn = bool((m_calm or 0) >= 1 and (m_frag or 0) >= 1)
    c_strong = bool((m_calm or 0) >= 1 and (m_frag or 0) >= 2)
    complacency = {
        "calm": None if m_calm is None else int(m_calm),
        "fragility": None if m_frag is None else int(m_frag),
        "warning": c_warn,
        "strong": c_strong,
        "state": ("hidden_fragility" if c_strong else
                  ("watch" if c_warn else
                   ("calm" if (m_calm or 0) >= 1 else "neutral"))),
        # individual legs (bool) + underlying reads, for a bilingual breakdown
        "vix_low": bool(vix_low), "vix_pctile": vp,
        "contango": bool(contango), "vix_term": vt,
        "breadth_div": breadth_div, "spy_high_prox": prox,
        "breadth_above200_pctile": b2p,
        "credit_widen": bool(credit_widen),
        "hy_oas_chg_21d_bp": None if hychg is None else round(hychg * 100, 0),
        # UNROUNDED companion (audit 2026-07-29): the rounded value above turns a -0.4bp
        # TIGHTENING into -0.0, and `-0.0 < 0` is False — so market_state's direction copy read
        # "widening" on a session credit had actually tightened. Consumers take the direction
        # from here and the DISPLAY from the rounded value above.
        "hy_oas_chg_21d_bp_exact": None if hychg is None else round(hychg * 100, 3),
        # lead/lag honesty: breadth divergence (calm tape, thinning internals) is a
        # forward fragility tell — the leading member of this gauge.
        "lead_lag": "leading",
        # PROMOTION (research/RISK_FLIP_2026-06-22.md): breadth_div is the one gauge
        # that perceived 2026-06-22's fragility. Surface it as a ONE-WAY risk-OFF
        # caution the downstream bot can honour — it ONLY ever raises caution, never
        # signals all-clear, and it STILL does not feed recession_risk / drawdown_risk
        # / RORO / MRS / any axis (the validated quad firewall is preserved).
        "breadth_div_caution": breadth_div,
        "caution": breadth_div,
        "caution_reason": ("breadth divergence: index near its high while %>200dma is "
                           "weak (a thinning tape — fewer names carrying the index)")
                          if breadth_div else None,
        "caution_reason_zh": ("广度背离：指数接近高点但200日均线上方占比偏弱（量能变薄——"
                              "推动指数的个股减少）") if breadth_div else None,
    }

    _vint = _input_vintages(f, fr)
    return {
        # PER-INPUT VINTAGES (audit 2026-07-29) — the last date each macro input actually
        # printed, measured against the frame's own last session. Consumed by
        # market_state.persist's freshness stamp (which used to certify itself off the price
        # calendar and so reported stale:false while NFCI was 12 days old).
        "vintages": _vint,
        "stale_inputs": sorted(k for k, v in _vint.items() if v.get("stale")),
        "financial_conditions": fin,
        "systemic_stress": systemic_stress,
        "recession": recession,
        "growth_nowcast": growth,
        "labor_nowcast": labor,
        "inflation_nowcast": inflation,
        "risk_appetite": risk,
        "drawdown_risk": drawdown,
        "capitulation": capitulation,
        "complacency": complacency,
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


def _mrs_transition_high() -> float:
    """MRS weight-value the 'transition' leg contributes when the regime is actively
    TRANSITIONING / NEW_REGIME. Config-driven for a calibration A/B: the default 1.0
    is the pre-existing behaviour — the leg pushes MRS risk-OFF hardest exactly as a
    regime is in flux, which is pro-cyclical INTO a turn (it leaned risk-off harder
    right before the snap-back). Clamping to 0.5 REMOVES that amplification (sign-
    preserving, subtract-only). NOT flipped live: default 1.0 => byte-identical.
    See reports/mrs-transition-clamp-spec.md for the A/B + validation plan."""
    return float((config.load().get("engine", {}).get("macro_overlay") or {})
                 .get("transition_high", 1.0))


def _mrs_transition_val(state) -> float:
    return (_mrs_transition_high() if state in ("TRANSITIONING", "NEW_REGIME")
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
        val = val.mask(tr.isin(("TRANSITIONING", "NEW_REGIME")), _mrs_transition_high())
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
