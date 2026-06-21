"""The Hong Kong stock CONVICTION engine — HK's honest, regime-conditioned per-name edge.

HK is a macro/flow market, not a stock-selection one. The deep-history record is blunt
(research/CHINA_HK_STOCK_SIGNALS.md, reports/hk-residual-alpha-phase0.md):

  * residual momentum is DEAD — its long-short Sharpe is NEGATIVE on a 40-year panel;
  * the cross-section is BETA-DOMINATED, so a naive relative-strength sort just
    re-discovers global-risk beta (the current board's #1 is whatever ran hardest —
    an outlier that is really a high-beta name in a rip);
  * the only validated reads are the GLOBAL-RISK overlay + per-name global-risk beta.

So this engine does NOT chase a fake selection alpha. It fuses the three HONEST,
structural HK edges into ONE per-name "edge" z that the conviction profile uses as its
selection leg — explicitly a FLOW + VALUE + EXPOSURE read, regime-conditioned, never a
backtested buy signal:

  1. SOUTHBOUND smart-money (engine/hk_southbound_stocks) — is the mainland Connect
     crowd, HK's dominant marginal buyer, ADDING to this name? (the signature HK flow,
     no US analog).
  2. A/H VALUE dislocation (engine/hk_ah) — for a dual-listed name, is its HK-listed H
     line cheap vs its mainland A twin, and is that gap widening? (rotate to the cheaper
     twin — the one genuinely HK-native relative-value edge).
  3. BETA-NEUTRAL relative strength — residualize each name's return against its OWN
     global-risk beta × the market, so what survives is GENUINE idiosyncratic leadership,
     not repackaged beta (this is what de-throned the outlier the raw RS sort surfaced).

A regime MASTER SWITCH (the live hk_global risk_state) re-weights the blend: in Risk-OFF
lead with southbound + A/H value + low-beta defensives; in Risk-ON lead with beta-neutral
RS + high-beta amplifiers. Honest framing throughout — a POSITIONING/FLOW read for sizing
within the validated regime, not a selection-alpha buy list (trust_tier stays 'screen').

Pure functions over already-stored frames; every leg degrades to absent (never neutral)
so a missing feed simply drops out of the blend.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# regime-conditional leg weights for the unified edge (the MASTER SWITCH). Each row sums
# to ~1 over the legs PRESENT for a name (renormalized); a name missing A/H value simply
# re-weights across southbound + beta-neutral RS + regime-fit.
_EDGE_W = {
    "Risk-off": {"sb": 0.38, "ahv": 0.28, "bnrs": 0.10, "fit": 0.24},
    "Risk-on":  {"sb": 0.30, "ahv": 0.14, "bnrs": 0.36, "fit": 0.20},
    "neutral":  {"sb": 0.34, "ahv": 0.22, "bnrs": 0.22, "fit": 0.22},
}


def _clipz(z, cap: float = 3.0):
    if z is None or (isinstance(z, float) and np.isnan(z)):
        return None
    return float(np.clip(z, -cap, cap))


def _zscore(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    mu, sd = s.mean(), s.std(ddof=0)
    if not sd or np.isnan(sd):
        return pd.Series(0.0, index=s.index)
    return ((s - mu) / sd).clip(-3.0, 3.0)


# ── leg 3: beta-neutral relative strength ────────────────────────────────────
def beta_neutral_rs(closes: pd.DataFrame, factor_ret: pd.Series,
                    betas: dict[str, float], *, win: int = 63) -> dict[str, float]:
    """Genuine idiosyncratic strength: each name's trailing ~63d return MINUS its expected
    return from its own global-risk beta × the market's 63d return, then cross-sectionally
    z-scored. Strips the beta the HK cross-section is dominated by, so a high-beta name in a
    rip no longer screens as a 'standout' — what is left is real relative leadership.

    ``betas`` = {ticker: global_beta} (engine/hk_global_beta). ``factor_ret`` = the market
    return series (SPY/HSI daily). Returns {ticker: residual_rs_z}; empty if too thin."""
    if closes is None or closes.empty or not betas:
        return {}
    px = closes.sort_index()
    if len(px) < win + 5:
        return {}
    stock_ret = px.iloc[-1] / px.iloc[-1 - win] - 1.0
    f = pd.to_numeric(factor_ret, errors="coerce").reindex(px.index).dropna()
    if len(f) < win + 2:
        # fall back to the universe's own median 63d return as the market proxy
        mkt = float((px.iloc[-1] / px.iloc[-1 - win] - 1.0).median())
    else:
        mkt = float((1.0 + f.tail(win)).prod() - 1.0)   # compounded market return over the window
    resid = {}
    for t, r in stock_ret.items():
        b = betas.get(t)
        if b is None or pd.isna(r):
            continue
        resid[t] = float(r) - float(b) * mkt
    if len(resid) < 8:
        return {}
    z = _zscore(pd.Series(resid))
    return {t: round(float(v), 2) for t, v in z.items()}


# ── leg 2: A/H value dislocation ─────────────────────────────────────────────
def ah_value_signal(ah_by_ticker: dict[str, dict]) -> dict[str, dict]:
    """Per dual-listed H-share: a value z that rewards a CHEAP H line (its A twin trades at
    a high premium = H is the cheaper way to own the company) that is getting CHEAPER (the
    premium is widening). A high premium percentile + a positive 1y change => positive z =>
    structural rotation tailwind toward the H/HK line. Keyed by H ticker; {} if absent.

    z = mean of the premium-percentile tilt and the widening tilt (each ~unit-scaled). This
    is the one genuinely HK-native relative-value edge — left entirely unused by the old
    board."""
    if not ah_by_ticker:
        return {}
    out: dict[str, dict] = {}
    for t, blk in ah_by_ticker.items():
        pct = blk.get("pctile")
        chg = blk.get("chg_1y")
        prem = blk.get("premium_pct")
        if pct is None:
            continue
        level_z = (float(pct) - 50.0) / 25.0          # high premium pctile => H cheap
        widen_z = float(np.clip((chg or 0.0) / 8.0, -1.5, 1.5))  # premium widening => H cheaper
        z = float(np.clip((level_z + widen_z) / 2.0, -3.0, 3.0))
        out[t] = {"z": round(z, 2), "premium_pct": prem, "pctile": pct, "chg_1y": chg,
                  "a": blk.get("a"), "cheap": z >= 0.4}
    return out


# ── leg 4: regime fit (beta role × live risk_state) ──────────────────────────
def _regime_fit_z(role: str | None, tilt: str | None) -> float | None:
    """How well this name's global-risk exposure FITS the live regime. Favored => +,
    exposed/lagging => −. This is the validated global-beta overlay turned into a small
    per-name tilt that the regime master switch up-weights."""
    if tilt == "favored":
        return 0.8
    if tilt == "exposed":
        return -0.8
    if tilt == "lag":
        return -0.3
    # neutral tilt carries NO information: return None so the leg DROPS OUT of the
    # edge-z renormalization. Returning 0.0 (the old behavior) kept the leg's weight
    # in the denominator while adding 0 to the numerator, silently haircutting any
    # name that merely has a beta role by ~17-29% — a role-presence artifact that
    # distorted the cross-sectional conviction rank (the module renormalizes over
    # legs PRESENT, so an uninformative leg must be absent, not zero).
    return None


# ── the unified per-name edge ────────────────────────────────────────────────
def hk_edge(tickers: list[str], *, southbound: dict[str, dict], ah_value: dict[str, dict],
            bnrs: dict[str, float], betas_pt: dict[str, dict],
            risk_state: str = "neutral") -> dict[str, dict]:
    """Fuse the HK-native legs into ONE per-name edge z, re-weighted by the live risk_state
    master switch. Returns {ticker: {z, legs:[...], regime_lean}} — the selection leg the
    conviction profile consumes (passed in the rs_z slot). Each name renormalizes the
    weights over whichever legs are present, so a name with only southbound + RS still scores
    honestly. ``z is None`` when no HK-native leg is available (the profile then has no
    selection axis rather than a fake zero)."""
    w = _EDGE_W.get(risk_state, _EDGE_W["neutral"])
    out: dict[str, dict] = {}
    for t in tickers:
        legs: dict[str, float] = {}
        basis: list[dict] = []
        sb = (southbound or {}).get(t)
        if sb and sb.get("accum_z") is not None:
            legs["sb"] = float(sb["accum_z"])
            basis.append({"leg": "southbound", "label": "southbound flow", "label_zh": "南向资金",
                          "z": legs["sb"], "tier": "flow"})
        ahv = (ah_value or {}).get(t)
        if ahv and ahv.get("z") is not None:
            legs["ahv"] = float(ahv["z"])
            basis.append({"leg": "ah_value", "label": "A/H value", "label_zh": "A/H 价值",
                          "z": legs["ahv"], "tier": "value"})
        rs = (bnrs or {}).get(t)
        if rs is not None:
            legs["bnrs"] = float(rs)
            basis.append({"leg": "bnrs", "label": "beta-neutral RS", "label_zh": "贝塔中性相对强度",
                          "z": legs["bnrs"], "tier": "screen"})
        gb = (betas_pt or {}).get(t) or {}
        fit = _regime_fit_z(gb.get("role"), gb.get("tilt"))
        if fit is not None:
            legs["fit"] = fit
            if fit != 0.0:
                basis.append({"leg": "fit", "label": "regime fit", "label_zh": "周期契合",
                              "z": round(fit, 2), "tier": "exposure"})
        if not legs:
            continue
        num = sum(w[k] * v for k, v in legs.items())
        den = max(sum(w[k] for k in legs), 0.4)
        z = _clipz(num / den)
        out[t] = {"z": round(z, 2) if z is not None else None, "basis": basis,
                  "regime_lean": risk_state}
    return out


# ── live regime → conviction risk overlay + calm ─────────────────────────────
def hk_calm(risk_state: str = "neutral", vhsi_pctile: float | None = None) -> float:
    """0..1 'calm' score for the conviction context (1 = calm/risk-on, 0 = stress). Driven
    by HK's validated edge — the global risk_state — softened by the VHSI fear percentile."""
    base = {"Risk-on": 0.82, "Risk-off": 0.2, "neutral": 0.5}.get(risk_state, 0.5)
    if vhsi_pctile is not None:
        base = float(np.clip(base * (1.0 - 0.5 * (vhsi_pctile / 100.0)) + 0.15, 0.0, 1.0))
    return round(base, 2)


def hk_risk_overlay(risk_state: str = "neutral", vhsi_pctile: float | None = None,
                    drawdown_band: str | None = None) -> dict:
    """Macro/event RISK overlay for the conviction engine: a 0..1 ``stress`` (which taxes a
    CHASE into a hot tape and vetoes a high-conviction verb on an aggressive name) plus the
    drivers behind it. Built from the validated global risk_state + the VHSI fear percentile
    + the (uncalibrated, context) drawdown-risk band. ``stress=0`` in a calm tape => silent."""
    stress = {"Risk-off": 0.7, "neutral": 0.35, "Risk-on": 0.1}.get(risk_state, 0.35)
    drivers: list[str] = []
    if risk_state == "Risk-off":
        drivers.append("global risk-off")
    if vhsi_pctile is not None and vhsi_pctile >= 70:
        stress = max(stress, 0.55); drivers.append("VHSI fear elevated")
    if drawdown_band in ("high", "extreme"):
        stress = max(stress, 0.6); drivers.append("HK drawdown-risk %s" % drawdown_band)
    return {"stress": round(float(np.clip(stress, 0.0, 1.0)), 2), "drivers": drivers or None}


def lottery_map(closes: pd.DataFrame) -> dict[str, float]:
    """Per-ticker biggest single-day % pop in the last 21 sessions (the lottery-spike read
    that arms the conviction entry penalty). Pure price, so available for every HK name."""
    if closes is None or closes.empty:
        return {}
    R = closes.sort_index().pct_change(fill_method=None).tail(21) * 100.0
    mx = R.max()
    return {t: round(float(v), 1) for t, v in mx.items() if pd.notna(v)}
