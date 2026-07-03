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

W4 note (screen-tier re-weight toward phase-0 evidence, 2026-07): the ``_EDGE_W`` master
switch was re-weighted toward the A/H-value leg (H3 near-GO, DSR 0.879) and away from the
southbound leg (H1 Δ-ranker NO-GO at delivery lag; its LEVEL stays only as context). This
is NOT a validated scored seam — the HK board remains a LABELED SCREEN (trust_tier stays
'screen'); nothing here graduates. See the ``_EDGE_W`` comment block for the citations and
the pre-W4 baseline weights.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# regime-conditional leg weights for the unified edge (the MASTER SWITCH). Each row sums
# to ~1 over the legs PRESENT for a name (renormalized); a name missing A/H value simply
# re-weights across southbound + beta-neutral RS + regime-fit.
#
# W4 SCREEN-TIER RE-WEIGHT toward phase-0 evidence (2026-07) — this is NOT a validated
# scored seam; it re-weights an already-labelled SCREEN toward the phase-0 verdicts, per
# the HK_CANADA constitution (DSR>=0.90 is the ONLY door into a scored seam and nothing
# here graduates). Two evidence citations drive the tilt:
#   * ahv UP — the A/H-discount own-history tilt is the near-GO leg: real, sign-stable
#     cross-sectional edge (rank-IC 0.055 @3m, HAC-t 2.23; top-5 H-leg excess +2.8%/3m,
#     positive in both split-halves and both eras), falling just short of the door at
#     DSR 0.879 < 0.90.  → reports/hkca-h3-phase0.md (ACCRUE).
#   * sb DOWN — southbound as a Δ-RANKER is NO-GO at the real delivery lag (H1); only the
#     LEVEL survives as a context input (kept on-card, not up-weighted as a ranker).
#     → reports/hk-southbound-divergence-phase0.md / hk-southbound-h1-phase0.md (NO-GO).
# Changes are MODERATE (a few points per row) and preserve BOTH regime-conditionality
# (risk-off still leads with flow+value+cushions; risk-on with RS+amplifiers) AND the
# leg-present renormalization in hk_edge().  Pre-W4 baseline kept inline for the audit:
#     Risk-off {sb .38, ahv .28, bnrs .10, fit .24}
#     Risk-on  {sb .30, ahv .14, bnrs .36, fit .20}
#     neutral  {sb .34, ahv .22, bnrs .22, fit .22}
_EDGE_W = {
    # ahv +4 / sb −4: value leads defence in risk-off; the southbound leg stays material
    # (LEVEL context) but no longer out-weighs the near-GO A/H value tilt.
    "Risk-off": {"sb": 0.34, "ahv": 0.32, "bnrs": 0.10, "fit": 0.24},
    # ahv +4 / sb −4: risk-on still leads with RS (bnrs .36 unchanged) — the tilt only
    # moves the two structural-flow/value legs, preserving the regime character.
    "Risk-on":  {"sb": 0.26, "ahv": 0.18, "bnrs": 0.36, "fit": 0.20},
    # ahv +5 / sb −5: in the neutral tape the edge is flow + value; lean it toward the
    # evidence-backed value leg.
    "neutral":  {"sb": 0.29, "ahv": 0.27, "bnrs": 0.22, "fit": 0.22},
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


# ── SFC reportable short-position CONTEXT chip (H2a — ACCRUE-labelled) ─────────
# Phase-0 verdict: LEVEL = ACCRUE, Δ4w = NO-GO (reports/h2a-phase0.md). On the PRIMARY
# days-to-cover normalization the own-history short book points the RIGHT way — names with
# a high days-to-cover percentile underperform the HSI over the next 4 weeks (Q5−Q1
# −0.39%/4w, HAC-t −1.81, sign-stable in both split-halves) — but it is sub-threshold
# (DSR 0.32 < 0.90, fails BH-FDR). Correct-signed, not decision-grade. So this is a CONTEXT
# CHIP only ("shorts P82 (accruing)"), never a rank input. Primary metric per the report:
#   days_to_cover = shorted_shares / mean(volume, 63 trading days, asof<=t)  [share-liquidity]
#   signal        = own_history_percentile(days_to_cover, window=104 weeks, min_prior=52)
_SFC_DTC_WINDOW_W = 104          # own-history percentile window (weeks) — H2a primary
_SFC_DTC_MIN_PRIOR_W = 52        # min prior weeks before a percentile is meaningful
_SFC_ADV_WIN_TD = 63             # trailing ADV window (trading days) — H2a primary
_SFC_MAX_STALE_TD = 12           # freshness guard: suppress if latest SFC week > this stale


def sfc_short_pressure(positions: pd.DataFrame | None,
                       volume_by_ticker: dict[str, "pd.Series"] | None,
                       *, asof: pd.Timestamp | str | None = None,
                       max_stale_td: int = _SFC_MAX_STALE_TD) -> dict[str, dict]:
    """Per covered HK name: current SFC days-to-cover own-history percentile — the H2a
    context read (ACCRUE-labelled, NEVER a rank input).

    ``positions`` = the ``hk_shorts/positions.parquet`` weekly panel (columns ``date``,
    ``ticker``, ``shorted_shares``). ``volume_by_ticker`` = {ticker: daily SHARE-volume
    Series (DatetimeIndex)} — used to build the trailing-63d ADV that normalizes the raw
    short share count into days-to-cover. ``asof`` optionally clips both to a leak-safe date.

    Returns {ticker: {"dtc": float, "pctile": 0..100, "as_of": "YYYY-MM-DD"}} — ONLY when
    the latest SFC week is within ``max_stale_td`` trading days of ``asof`` (freshness guard;
    the whole map is suppressed stale, matching the fail-closed contract). {} when the store
    is missing, no ticker resolves, or the panel is stale. NO rank effect.
    """
    if positions is None or getattr(positions, "empty", True) or not volume_by_ticker:
        return {}
    if not {"date", "ticker", "shorted_shares"}.issubset(set(positions.columns)):
        return {}
    pos = positions[["date", "ticker", "shorted_shares"]].copy()
    pos["date"] = pd.to_datetime(pos["date"], errors="coerce").astype("datetime64[ns]")
    pos = pos.dropna(subset=["date"])
    if asof is not None:
        try:
            pos = pos[pos["date"] <= pd.Timestamp(str(asof))]
        except Exception:  # noqa: BLE001
            pass
    if pos.empty:
        return {}
    latest_week = pos["date"].max()
    # FRESHNESS GUARD (fail-closed): if the newest SFC week is more than max_stale_td
    # trading days behind the as-of date, the whole context is suppressed rather than
    # shown stale (the H2a chip must never imply live short pressure off an old file).
    ref = pd.Timestamp(str(asof)) if asof is not None else latest_week
    stale_td = int(np.busday_count(latest_week.date(), ref.date())) if ref >= latest_week else 0
    if stale_td > max_stale_td:
        log.info("hk SFC short-pressure suppressed — latest week %s is %d trading days stale "
                 "(> %d) vs %s", latest_week.date(), stale_td, max_stale_td, ref.date())
        return {}

    out: dict[str, dict] = {}
    for t, sub in pos.groupby("ticker"):
        vol = volume_by_ticker.get(t)
        if vol is None or len(vol) < _SFC_ADV_WIN_TD:
            continue
        sub = sub.sort_values("date")[["date", "shorted_shares"]].reset_index(drop=True)
        adv = pd.to_numeric(vol, errors="coerce").rolling(
            _SFC_ADV_WIN_TD, min_periods=max(20, _SFC_ADV_WIN_TD // 3)).mean()
        adv = adv.dropna()
        if adv.empty:
            continue
        adv = adv.reset_index()
        adv.columns = ["date", "adv63"]
        adv["date"] = pd.to_datetime(adv["date"], errors="coerce").astype("datetime64[ns]")
        try:
            m = pd.merge_asof(sub, adv, on="date")          # ADV asof each short week
        except Exception:  # noqa: BLE001
            continue
        m["dtc"] = m["shorted_shares"] / m["adv63"].replace(0.0, np.nan)
        w = m["dtc"].dropna().tail(_SFC_DTC_WINDOW_W)
        if len(w) < _SFC_DTC_MIN_PRIOR_W:
            continue
        last = float(w.iloc[-1])
        if not np.isfinite(last):
            continue
        pctile = float((w < last).sum()) / float(len(w) - 1) * 100.0 if len(w) > 1 else 50.0
        out[t] = {"dtc": round(last, 2),
                  "pctile": int(round(float(np.clip(pctile, 0.0, 100.0)))),
                  "as_of": latest_week.strftime("%Y-%m-%d")}
    return out
