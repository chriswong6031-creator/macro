"""Cross-sectional DISPERSION & correlation regime — the meta-signal for WHEN stock
selection pays (engine v2, display + a gross dial).

Alpha and achievable information-ratio scale with cross-sectional dispersion (S&P DJI,
Gorman-Sapra-Weigand): when names move together (low dispersion / high pairwise
correlation, a macro-driven tape) stock selection earns little no matter how good the
signal; when they fan out (high dispersion, often high-VIX) selection — and our
reversal/timing legs — pay the most. So this is the dial that sizes SELECTION
conviction (the gross taken on the cross-sectional book), kept DISTINCT from the
market-timing overlay that sizes net/long exposure.

Kept to 2-3 DISCRETE states with fixed thresholds (a continuous fitted curve is the
classic overfit trap). Point-in-time; correlation is the standard EW-var / mean-name-var
approximation (a full pairwise matrix on ~1600 names is unestimable and overfit)."""
from __future__ import annotations

import numpy as np
import pandas as pd

_HI, _LO = 0.66, 0.33          # dispersion-percentile terciles
# SHADOW gross dial — the hand-picked tercile magnitudes. DISPLAY-ONLY per the passport
# rule (US_BOARD_MEASUREMENT.md §Study 3 / audit #20): direction is suggestive and roughly
# monotone (alpha IC negative in low-dispersion, positive in mid/high) but ~8 correlated
# rebalances/bucket forbids any claim, and lean_in=1.20 grosses UP into the high-VIX stress
# the sizing layer is mandated to fade. Until a survivorship-clean selection-IR edge is
# MEASURED, the LIVE gross is clamped to 1.0 and this stays a shadow so a future measured
# promotion is one config change (flip _LIVE_CLAMP off).
_SHADOW_GROSS = {"lean_in": 1.20, "neutral": 1.0, "lean_out": 0.75}
_LIVE_CLAMP = 1.0              # what actually binds sizing while basis=prior/display-only
_LABEL = {"lean_in": ("Selection pays — high dispersion", "选股有效 — 高离散度"),
          "neutral": ("Mixed selection backdrop", "选股环境中性"),
          "lean_out": ("Macro tape — selection muted", "宏观主导 — 选股弱化")}


def assess(returns: pd.DataFrame, lookback: int = 252) -> dict | None:
    """`returns` = a wide [dates x names] daily-return panel. Returns the dispersion
    regime + a `gross_mult` for the cross-sectional book, or None when too thin."""
    r = returns.dropna(how="all")
    if len(r) < 60 or r.shape[1] < 20:
        return None
    csd = r.std(axis=1)                                   # cross-sectional dispersion per day
    disp = float(csd.iloc[-21:].mean())                  # recent ~1-month average dispersion
    hist = csd.rolling(21, min_periods=10).mean()
    h = hist.dropna()
    disp_pct = float((h <= h.iloc[-1]).mean()) if len(h) >= 60 else None
    # average pairwise correlation proxy: var(equal-weight return) / mean(single-name var)
    win = r.iloc[-63:]
    ew_var = float(win.mean(axis=1).var())
    mean_var = float(win.var().mean())
    avg_corr = float(np.clip(ew_var / mean_var, 0.0, 1.0)) if mean_var > 0 else None

    if disp_pct is None:
        state = "neutral"
    elif disp_pct >= _HI:
        state = "lean_in"
    elif disp_pct <= _LO:
        state = "lean_out"
    else:
        state = "neutral"
    en, zh = _LABEL[state]
    shadow = _SHADOW_GROSS[state]
    return {"dispersion_pct_pts": round(100 * disp, 2),
            "dispersion_pctile": round(disp_pct, 2) if disp_pct is not None else None,
            "avg_corr": round(avg_corr, 2) if avg_corr is not None else None,
            "state": state,
            # LIVE dial: clamped to display-only (basis: prior). Consumers multiply sizing
            # by this, so it must be 1.0 until a measured selection-IR edge promotes it.
            "gross_mult": _LIVE_CLAMP,
            # SHADOW: the hand-picked tercile magnitude, logged for a future measured promotion.
            "shadow_gross_mult": shadow,
            "passport": {
                "basis": "prior",
                "verdict": "display-only per US_BOARD_MEASUREMENT",
                "validation": {"artifact": "research/US_BOARD_MEASUREMENT.md#study-3",
                               "n": None, "survives": False},
                "note": ("hand-picked terciles, no measured edge on this universe; "
                         "shadow_gross_mult would gross UP into high-VIX stress — clamped "
                         "to 1.0 until a survivorship-clean selection-IR edge is measured"),
            },
            "label": en, "label_zh": zh}
