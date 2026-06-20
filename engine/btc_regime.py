"""Bitcoin Vector — the five-tier macro-regime composite (DISPLAY-ONLY).

A transparent, transmission-ranked re-presentation of the macro backdrop, built
verbatim from the framework in research/BTC_REGIME_FRAMEWORK.md (the paper). Each
factor is scored to an integer {-2..+2} from a-priori economics ONLY (no fitting
to forward returns), weighted by the paper's fixed tier weights, summed and
renormalized over the factors that are live, mapped to a 0-100 index.

HONESTY (load-bearing — do not quietly upgrade):
  * This is NOT a live-sizing engine. The P0 kill-test (scripts/btc_regime_killtest)
    showed the textbook composite does NOT beat the hand-tuned `composite_state`
    out-of-sample in both halves (post 0.67 vs 0.72). So `exposure` here is a
    DISPLAY band only; nothing sizes off it until it clears the gate in
    scripts/calibrate_regime.py (it is not expected to).
  * Weights are FIXED and transparent (the btc_master.py contract). There is NO
    dynamic re-weighter and NO second "effective" gauge — the correlation regime
    is surfaced as a NON-NUMERIC lean chip only (engine/btc_correlation_regime).
  * Every band carries an `origin`: `apriori` (justified by sign/economics, full
    history) or `tuned` (references a specific recent calibration → counted in the
    machine n_trials and gate-scored on out-of-tuning data only).
  * 2024-> "flow" factors (ETF) are tagged context-tier: graded by the ledger,
    structurally ineligible for the validation gate until they accrue history.

Pure, NaN-safe, degrade-never-raise. Returns a render-ready dict for the template
and a persisted scorecard; the live recommend/size path never reads it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# a-priori scoring knobs — every entry is ONE explored choice the validation
# harness counts toward the machine n_trials (kept deliberately few).
Z_WINDOW = 365
SLOPE_LB = 20
TREND_MA_D = 200
TREND_MA_W = 1400            # ~200 weeks of daily bars
HIVIX_Z = 0.5               # credit accelerant only bites above this VIX z (Lee EFM 2026)
MIN_FACTORS = 6             # composite is "thin" below this many live factors
# continuous index -> display exposure knots (NOT an ECDF; a-priori, display-only)
EXPO_KNOTS_X = [0, 10, 35, 65, 90, 100]
EXPO_KNOTS_Y = [0.0, 0.0, 0.25, 0.55, 0.90, 1.0]


# --------------------------------------------------------------------------- #
# scoring primitives
# --------------------------------------------------------------------------- #
def _zc(s: pd.Series, n: int = Z_WINDOW) -> pd.Series:
    m = s.rolling(n, min_periods=max(60, n // 4))
    return (s - m.mean()) / m.std().replace(0, np.nan)


def _score_z(z: pd.Series) -> pd.Series:
    """rolling-z -> {-2,-1,0,+1,+2} with FIXED a-priori cutoffs (un-oriented)."""
    out = pd.Series(np.nan, index=z.index)
    out[z.notna()] = 0.0
    out[z > 0.5] = 1.0
    out[z > 1.5] = 2.0
    out[z < -0.5] = -1.0
    out[z < -1.5] = -2.0
    return out


def _lvl_chg(level: pd.Series, want: int, already_z: bool = False, k: int = SLOPE_LB) -> pd.Series:
    """Average a LEVEL sub-score and a SLOPE sub-score, round, orient by `want`.
    Captures the paper's 'expanding-but-decelerating = +1 not +2' nuance for free."""
    z_level = level if already_z else _zc(level)
    lvl = _score_z(z_level)
    chg = _score_z(_zc(level.diff(k)))
    return (want * (lvl + chg) / 2.0).round()


def _trend_score(close: pd.Series) -> pd.Series:
    """Paper's TREND axis (NOT extension): +2 well above a rising 200D, −2 below a
    falling 200W. Above-MA dominates; the 200D slope gates the sign."""
    ma_d = close.rolling(TREND_MA_D, min_periods=120).mean()
    ma_w = close.rolling(TREND_MA_W, min_periods=600).mean()
    ext_z = _zc(close / ma_d - 1)
    slope = ma_d.pct_change(SLOPE_LB)
    tr = _score_z(ext_z)
    tr = tr.where(slope >= 0, tr.clip(upper=0))     # falling 200D: cap positive
    tr = tr.where(slope <= 0, tr.clip(lower=0))      # rising 200D: cap negative
    tr = tr.mask((close < ma_w) & (slope < 0), -2)   # below a down-sloping 200W = max bearish
    return tr


def _equity_vix_score(df: pd.DataFrame) -> pd.Series:
    """Risk-regime score with the Lee (EFM 2026) state-switch: a widening credit
    spread only deepens the score inside a high-VIX regime; in calm tape VIX leads."""
    vix_s = -_score_z(_zc(df["vix"])) if "vix" in df else None
    if vix_s is None:
        return pd.Series(np.nan, index=df.index)
    if "hy_oas" in df:
        hy_s = -_score_z(_zc(df["hy_oas"]))
        hivix = _zc(df["vix"]) > HIVIX_Z
        return vix_s.where(~hivix, np.minimum(vix_s, hy_s)).round()
    return vix_s.round()


# --------------------------------------------------------------------------- #
# factor table (the §3 stack). origin: apriori | tuned | context(2024->)
# --------------------------------------------------------------------------- #
FACTORS = [
    # key            tier  w  want col(s)                                 origin     label
    ("netliq",       "T1", 3, +1, "net_liq_roc",   "apriori", "Net-liquidity impulse"),
    ("m2",           "T1", 2, +1, "global_m2_yoy", "apriori", "Global M2 YoY + slope"),
    ("real10y",      "T2", 3, -1, "real_yield",    "apriori", "Real 10Y yield"),
    ("dxy",          "T2", 2, -1, "dxy",           "apriori", "US dollar (DXY)"),
    ("curve",        "T3", 2, +1, "curve_score",   "apriori", "Yield-curve regime"),   # optional col
    ("fed",          "T3", 2, +1, "fed_score",     "apriori", "Fed path"),             # optional col
    ("equity_vix",   "T4", 2, -1, "__equity_vix",  "apriori", "Equity / VIX regime"),
    ("etf",          "T5", 3, +1, "etf_flow_z",    "context", "Spot-ETF net flows"),
    ("stbl",         "T5", 1, +1, "stbl_growth_z", "apriori", "Stablecoin supply Δ"),
    ("trend",        "T5", 3, +1, "__trend",       "apriori", "Trend vs 200D/200W"),
    ("onchain",      "T5", 2, -1, "mvrv_z",        "apriori", "On-chain valuation"),
]
TIER_LABELS = {"T1": "Liquidity", "T2": "Rates / Dollar", "T3": "Curve / Fed",
               "T4": "Equity / VIX", "T5": "Crypto-native"}
_ALREADY_Z = {"etf_flow_z", "stbl_growth_z"}
_PRESCORED = {"curve_score", "fed_score"}   # already emitted in {-2..+2} by btc_signals


def _factor_score(key: str, col: str, want: int, df: pd.DataFrame) -> pd.Series | None:
    """Compute one factor's −2..+2 score series, or None if its input is absent."""
    try:
        if col == "__equity_vix":
            return _equity_vix_score(df)
        if col == "__trend":
            return _trend_score(df["close"])
        if col not in df.columns:
            return None
        if df[col].dropna().empty:
            return None
        if col in _PRESCORED:               # pass through the pre-oriented discrete score
            return (df[col].clip(-2, 2) * (1 if want >= 0 else -1)).round()
        if col == "onchain" or key == "onchain":
            return (-_score_z(_zc(df[col]))).round()
        return _lvl_chg(df[col], want, already_z=(col in _ALREADY_Z))
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# composite
# --------------------------------------------------------------------------- #
def composite_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized per-factor scores + composite + index over the whole history.
    Renormalizes over LIVE factors; flags thin rows (<MIN_FACTORS live)."""
    scores, weights = {}, {}
    for key, tier, w, want, col, origin, label in FACTORS:
        s = _factor_score(key, col, want, df)
        if s is not None:
            scores[key] = s
            weights[key] = w
    if not scores:
        return pd.DataFrame(index=df.index)
    S = pd.DataFrame(scores)
    w = pd.Series(weights)
    present = S.notna()
    composite = (S.fillna(0) * w).sum(axis=1)
    wpresent = (present * w).sum(axis=1)
    n_live = present.sum(axis=1)
    idx = (50 + 50 * composite / (2 * wpresent)).where(n_live >= 1).clip(0, 100)
    out = S.copy()
    out["composite"] = composite
    out["w_present"] = wpresent
    out["n_live"] = n_live
    out["index"] = idx.where(n_live >= MIN_FACTORS)
    out["index_thin"] = idx.where((n_live > 0) & (n_live < MIN_FACTORS))
    return out


def exposure_band(index: float | None) -> float | None:
    if index is None or (isinstance(index, float) and np.isnan(index)):
        return None
    return round(float(np.interp(index, EXPO_KNOTS_X, EXPO_KNOTS_Y)), 3)


def _f(v):
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# render-ready scorecard
# --------------------------------------------------------------------------- #
def compute(df: pd.DataFrame, calib: dict | None = None) -> dict:
    """Build the regime scorecard for the dashboard. DISPLAY-ONLY. Never raises."""
    try:
        cf = composite_frame(df)
        if cf.empty or "index" not in cf:
            return {"ok": False, "reason": "no live factors"}
        last = cf.iloc[-1]
        idx_val = _f(last.get("index"))
        if idx_val is None:
            idx_val = _f(last.get("index_thin"))
        thin = bool(pd.isna(last.get("index")) and pd.notna(last.get("index_thin")))

        # per-factor + per-tier assembly
        tiers: dict[str, dict] = {}
        factor_rows = []
        for key, tier, w, want, col, origin, label in FACTORS:
            if key not in cf.columns:
                continue
            sc = _f(last.get(key))
            present = sc is not None
            factor_rows.append({
                "key": key, "tier": tier, "tier_label": TIER_LABELS[tier],
                "label": label, "weight": w, "want": want, "origin": origin,
                "score": (int(sc) if present else None), "present": present,
            })
            t = tiers.setdefault(tier, {"tier": tier, "label": TIER_LABELS[tier],
                                        "sub": 0.0, "max": 0.0, "w_live": 0.0, "factors": []})
            t["factors"].append(key)
            if present:
                t["sub"] += sc * w
                t["max"] += 2 * w
                t["w_live"] += w
        tier_rows = []
        for tcode in ["T1", "T2", "T3", "T4", "T5"]:
            if tcode in tiers:
                t = tiers[tcode]
                tier_rows.append({
                    "tier": tcode, "label": t["label"],
                    "sub": round(t["sub"], 1), "max": round(t["max"], 1),
                    "w_live": t["w_live"],
                    "norm": round(t["sub"] / t["max"], 3) if t["max"] else None,
                })

        band = _band_label(idx_val)
        # tail flags + correlation-mode lean (separate modules; degrade gracefully)
        flags = _safe_flags(df, cf)
        mode = _safe_mode(df)

        # trailing index history for a sparkline (display)
        hist = cf["index"].dropna()
        spark = [round(float(v), 1) for v in hist.iloc[-90:].tolist()] if len(hist) else []

        return {
            "ok": True,
            "display_only": True,
            "asof": str(df.index[-1].date()),
            "index": round(idx_val, 1) if idx_val is not None else None,
            "thin": thin,
            "n_live": int(_f(last.get("n_live")) or 0),
            "band": band["label"], "band_zh": band["zh"], "band_tone": band["tone"],
            "exposure_display": exposure_band(idx_val),
            "composite_raw": round(_f(last.get("composite")) or 0.0, 1),
            "w_present": round(_f(last.get("w_present")) or 0.0, 1),
            "tiers": tier_rows,
            "factors": factor_rows,
            "flags": flags,
            "mode_lean": mode,
            "spark": spark,
            "note": ("Display-only macro-regime read. Transparent fixed weights, no fitting; "
                     "does NOT size positions (it did not beat the hand-tuned allocator OOS). "
                     "Avoidance > entry precision."),
        }
    except Exception as e:  # never break the build
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def _band_label(idx: float | None) -> dict:
    if idx is None:
        return {"label": "n/a", "zh": "无数据", "tone": "neutral"}
    if idx >= 75:
        return {"label": "STRONG TAILWIND", "zh": "强顺风", "tone": "bull"}
    if idx >= 58:
        return {"label": "TAILWIND", "zh": "顺风", "tone": "bull-soft"}
    if idx >= 42:
        return {"label": "NEUTRAL", "zh": "中性", "tone": "neutral"}
    if idx >= 25:
        return {"label": "HEADWIND", "zh": "逆风", "tone": "bear-soft"}
    return {"label": "STRONG HEADWIND", "zh": "强逆风", "tone": "bear"}


def _safe_flags(df, cf):
    try:
        from engine import btc_regime_flags
        return btc_regime_flags.evaluate(df, cf)
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def _safe_mode(df):
    try:
        from engine import btc_correlation_regime
        return btc_correlation_regime.lean(df)
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}
