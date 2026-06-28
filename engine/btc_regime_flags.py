"""Bitcoin Vector — confluence tail flags (STAY-AWAY / DOUBLE-DOWN), DISPLAY-ONLY.

The paper's §4: a major tail call requires a ≥k-of-8 CONFLUENCE of independent
conditions — never a single factor (Override #4). This replaces the live
recommender's old single-factor HIGH triggers with a counted, transparent set.

Discipline carried from the design review:
  * `k` is NOT asserted. We report whether each flag fires at k∈{4,5,6} and label
    the default (k=5) "count illustrative" — on ~5 cycles the cutoff is not
    identifiable, so it is directional context, not a calibrated trigger.
  * DOUBLE-DOWN keeps "net-liquidity expanding AND accelerating" as a HARD
    PREREQUISITE (necessary, not just one-of-k) — the paper's single most
    important condition.
  * Override #1 (trend dominates in contracting liquidity) suppresses a
    DOUBLE-DOWN to NEUTRAL when price is below a down-sloping 200D and T1 is
    contracting, regardless of count.
  * The on-chain recalibration (rolling-percentile tail bands + 3-metric panel
    convergence) lives HERE so the live engine (btc_signals.market_extreme) and
    these flags share ONE definition instead of two stale fixed thresholds.

Pure, NaN-safe. `evaluate()` reads the last row; the per-condition series are also
exposed for the ledger to grade forward.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PANEL_LOOKBACK = 180        # ~6 months of daily bars for rolling percentile bands
TAIL_LO, TAIL_HI = 0.10, 0.90
K_SWEEP = [4, 5, 6]
K_DEFAULT = 5
SLOPE_LB = 20


def _zc(s: pd.Series, n: int = 365) -> pd.Series:
    m = s.rolling(n, min_periods=max(60, n // 4))
    return (s - m.mean()) / m.std().replace(0, np.nan)


def _pctile(s: pd.Series, lookback: int = PANEL_LOOKBACK) -> pd.Series:
    """Trailing rolling percentile (0-1) of the last value within its window —
    the ETF-era-robust replacement for fixed thresholds."""
    return s.rolling(lookback, min_periods=max(30, lookback // 3)).apply(
        lambda w: (w[-1] >= w).mean(), raw=True)


def onchain_panel(df: pd.DataFrame) -> dict:
    """3-metric convergence on rolling-percentile tails. Returns the per-metric
    percentiles + whether the panel co-flashes depressed (cheap) or stretched
    (rich). Single-metric silence is inconclusive in the ETF era — require ≥2 of 3."""
    metrics = {}
    if "mvrv_z" in df:
        metrics["mvrv_z"] = _pctile(df["mvrv_z"])
    if "nupl" in df:
        metrics["nupl"] = _pctile(df["nupl"])
    if "mayer" in df:                                  # price vs 200D = the trend/valuation leg
        metrics["mayer"] = _pctile(df["mayer"])
    if not metrics:
        return {"ok": False}
    P = pd.DataFrame(metrics)
    last = P.iloc[-1]
    live = last.dropna()
    n = len(live)
    depressed = int((live <= TAIL_LO).sum())
    stretched = int((live >= TAIL_HI).sum())
    return {
        "ok": True,
        "n": n,
        "pctiles": {k: (round(float(v), 2) if pd.notna(v) else None) for k, v in last.items()},
        "depressed_co_flash": bool(n >= 2 and depressed >= 2),   # cheap, panel-confirmed
        "stretched_co_flash": bool(n >= 2 and stretched >= 2),   # rich, panel-confirmed
        "n_depressed": depressed, "n_stretched": stretched,
        "_series": P,   # for the ledger / live engine
    }


def _last(s: pd.Series):
    s = s.dropna()
    return s.iloc[-1] if len(s) else np.nan


def _cond_series(df: pd.DataFrame) -> dict:
    """Per-day boolean series for every tail condition (so the ledger can grade)."""
    close = df["close"]
    out: dict[str, pd.Series] = {}

    def has(c):
        return c in df.columns and not df[c].dropna().empty

    # liquidity impulse
    if has("net_liq_roc"):
        roc = df["net_liq_roc"]
        accel = roc.diff(SLOPE_LB)
        out["SA_netliq_contracting"] = (roc < 0)
        out["DD_netliq_expanding_accel"] = (roc > 0) & (accel > 0)   # HARD PREREQUISITE
    # real yields
    if has("real_yield"):
        rz = _zc(df["real_yield"])
        rising = df["real_yield"].diff(SLOPE_LB) > 0
        out["SA_real_high_rising"] = (rz > 0.5) & rising
        out["DD_real_low_falling"] = (rz < -0.5) | (df["real_yield"] < 0)
    # dollar
    if has("dxy"):
        dz = _zc(df["dxy"])
        drise = df["dxy"].diff(SLOPE_LB) > 0
        out["SA_dollar_strong_rising"] = (dz > 0.5) & drise
        out["DD_dollar_weak_falling"] = (dz < -0.5) | (~drise & (dz < 0.25))
    # trend vs 200D/200W
    ma_d = close.rolling(200, min_periods=120).mean()
    ma_w = close.rolling(1400, min_periods=600).mean()
    slope_d = ma_d.pct_change(SLOPE_LB)
    out["SA_below_downsloping_200d"] = (close < ma_d) & (slope_d < 0)
    crossed_up = (close > ma_d) & (close.shift(SLOPE_LB) <= ma_d.shift(SLOPE_LB))
    out["DD_reclaim_200d"] = crossed_up & (slope_d > 0)
    out["_below_downsloping_200w"] = (close < ma_w) & (ma_w.pct_change(SLOPE_LB) < 0)
    # ETF flows (context-tier; 2024->)
    if has("etf_flow_z"):
        out["SA_etf_outflow"] = df["etf_flow_z"] < -0.5
        out["DD_etf_inflow"] = df["etf_flow_z"] > 0.5
    # curve / Fed (only if the optional columns are wired)
    if has("curve_score") or has("fed_score"):
        cs = df["curve_score"] if has("curve_score") else pd.Series(0, index=df.index)
        fs = df["fed_score"] if has("fed_score") else pd.Series(0, index=df.index)
        out["SA_curve_bear_or_hfl"] = (cs < 0) | (fs < 0)
        out["DD_curve_bull_or_pivot"] = (cs > 0) | (fs > 0)
    # on-chain panel (recalibrated)
    panel = onchain_panel(df)
    if panel.get("ok"):
        Pp = panel["_series"]
        stretched = (Pp >= TAIL_HI).sum(axis=1) >= 2
        depressed = (Pp <= TAIL_LO).sum(axis=1) >= 2
        rolling_over = df["mvrv_z"].diff(SLOPE_LB) < 0 if has("mvrv_z") else pd.Series(False, index=df.index)
        out["SA_onchain_stretched_rolling"] = stretched & rolling_over
        out["DD_onchain_depressed"] = depressed
    # accelerant (prov-tagged: derived from the T4 stress leg, NOT independent)
    if has("vix") and has("hy_oas"):
        out["SA_vix_oas_accelerant"] = (_zc(df["vix"]) > 1.0) & (df["hy_oas"].diff(SLOPE_LB) > 0)
    # capitulation flush (optional DD condition)
    if has("vix"):
        out["DD_capitulation_flush"] = (_zc(df["vix"]) > 1.5) & (close.pct_change(30) < -0.25)
    return out


# provenance: conditions sharing an underlying reading are flagged so the count
# does not treat them as independent.
_PROV = {"SA_vix_oas_accelerant": "derived from T4 (VIX/credit) — not independent"}

_SA_LABELS = {
    "SA_netliq_contracting": "Net liquidity contracting / QT",
    "SA_real_high_rising": "Real 10Y high & rising",
    "SA_dollar_strong_rising": "Dollar strong & rising",
    "SA_below_downsloping_200d": "Price below a down-sloping 200D",
    "SA_etf_outflow": "ETF sustained outflow",
    "SA_curve_bear_or_hfl": "Curve bear-flat or Fed higher-for-longer",
    "SA_onchain_stretched_rolling": "On-chain stretched & rolling over",
    "SA_vix_oas_accelerant": "VIX spike + HY-OAS widening (accelerant)",
}
_DD_LABELS = {
    "DD_netliq_expanding_accel": "Net liquidity expanding & accelerating (prerequisite)",
    "DD_real_low_falling": "Real yields falling / negative",
    "DD_dollar_weak_falling": "Dollar weak / falling",
    "DD_reclaim_200d": "Reclaiming the 200D from below, MA turning up",
    "DD_etf_inflow": "ETF flipping to sustained inflow",
    "DD_curve_bull_or_pivot": "Fed pivot / bull-steepening curve",
    "DD_onchain_depressed": "On-chain depressed (panel-confirmed cheap)",
    "DD_capitulation_flush": "Post-capitulation flush",
}


def _flag(cond: dict, labels: dict, prereq: str | None = None) -> dict:
    rows, fired = [], 0
    for kkey, label in labels.items():
        if kkey not in cond:
            continue
        v = _last(cond[kkey])
        f = bool(v) if pd.notna(v) else False
        rows.append({"key": kkey, "label": label, "fired": f,
                     "prov": _PROV.get(kkey)})
        if f:
            fired += 1
    n_avail = len(rows)
    prereq_ok = True
    if prereq is not None:
        pv = _last(cond[prereq]) if prereq in cond else np.nan
        prereq_ok = bool(pv) if pd.notna(pv) else False
    fires = {k: (fired >= k and prereq_ok) for k in K_SWEEP}
    return {"count": fired, "n_available": n_avail, "conditions": rows,
            "prereq": prereq, "prereq_ok": prereq_ok,
            "fires_at_k": fires, "active": fires.get(K_DEFAULT, False),
            "k_default": K_DEFAULT}


def evaluate(df: pd.DataFrame, cf: pd.DataFrame | None = None) -> dict:
    """The two confluence flags on the latest row, with the k-sweep + Override #1."""
    try:
        cond = _cond_series(df)
        sa = _flag(cond, _SA_LABELS)
        dd = _flag(cond, _DD_LABELS, prereq="DD_netliq_expanding_accel")

        # Override #1 — trend dominates in contracting liquidity.
        below_200w = _last(cond.get("_below_downsloping_200w", pd.Series(dtype=float)))
        netliq_contracting = _last(cond.get("SA_netliq_contracting", pd.Series(dtype=float)))
        veto = bool(pd.notna(below_200w) and below_200w) and bool(
            pd.notna(netliq_contracting) and netliq_contracting)
        if veto and dd["active"]:
            dd = {**dd, "active": False, "override": "suppressed by trend filter (Override #1)"}

        active = ("STAY-AWAY" if sa["active"] else
                  "DOUBLE-DOWN" if dd["active"] else "NONE")
        return {
            "ok": True, "display_only": True,
            "active": active,
            "stay_away": sa, "double_down": dd,
            "override_1_veto": veto,
            "onchain_panel": {k: v for k, v in onchain_panel(df).items() if k != "_series"},
            "note": ("Confluence tail flags — ≥k-of-8 independent conditions (no single factor). "
                     f"k={K_DEFAULT} is illustrative on ~5 cycles; see fires_at_k. "
                     "DOUBLE-DOWN needs the net-liquidity-accelerating prerequisite."),
        }
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}
