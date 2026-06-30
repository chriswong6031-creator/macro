"""Top-Picks score — the holistic, validated US stock-selection composite.

This is the engine behind the "Top Picks" board (site/discovery.html). It replaces the
old "Alpha leaders" board's pure residual-momentum sort with a multi-factor *conviction*
rank, while keeping entry-timing on a SEPARATE axis — the honest US analog of the China
board (which folds mean-reversion INTO its rank because A-shares mean-revert; US leaders
*continue*, so a reversal tilt in the rank dilutes it).

The construction is the one validated point-in-time in reports/top-picks-phase0.md
(deep survivorship-clean S&P panel, 2014-2025, PIT membership + EDGAR fundamentals +
Form-4): an **alpha-led conviction blend**

    top_score = ALPHA_W · alpha_z  +  TILT_W · conviction_z

      alpha_z       sector-neutral residual-momentum z   (engine/residual_alpha.py — the
                                                           validated positive-IC leg)
      conviction_z  sector-neutral z-mean of the light multi-factor confirmation legs
                    {value, quality, profitability, low_vol, insider}

beat residual-alpha ALONE on cross-sectional IC at every horizon (21/63/126d) and on
the long/short Sharpe at the shorter ones. Profitability (Novy-Marx gross profitability)
was the strongest confirming leg. The win is MODEST and still fails the multiple-testing
(DSR) haircut — so the page framing stays "context / confluence, a decayed crowded edge",
NOT an alpha machine. We rank by it because it is a *measured* improvement over the leg
the board ranked by before, not because it clears an absolute bar nothing here clears.

Entry timing (``entry_label``) is the second axis: it describes WHERE in its own trend a
leader sits — easing back (Pullback), riding it (In trend) or just spiked (Extended, wait).
This is DISPLAY/risk-placement CONTEXT, never a rank ingredient (folding it in measurably
HURTS US forward returns) and — critically — NOT a buy call: a name eases back in its trend
yet can still be downtrending on the 3D MACD/StochRSI. The actionable BUY label comes from the
validated MACD-2D x StochRSI-3D confluence gate (``engine/signal_gate.is_buyable``), which the
discovery board layers on top as a separate, hard-gated signal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# validated alpha-led weights (reports/top-picks-phase0.md). Alpha-dominant: the residual
# momentum is the only individually positive-IC leg, the tilt is a light confirmation.
ALPHA_W = 0.6
TILT_W = 0.4

# the light multi-factor confirmation legs, EXACTLY the set validated in the blend
# (do NOT cherry-pick by observed sign — that overfits). value/quality come cheap-vs-rich
# and balance-sheet; profitability is gross-profitability (the strongest confirmer);
# low_vol the anomaly; insider the size-normalised Form-4 net-buy.
TILT_LEGS = ("value", "quality", "profitability", "low_vol", "insider")
MIN_TILT_LEGS = 2          # need >=2 confirming legs or conviction is treated as neutral (0)
WINSOR_CAP = 3.0

# entry-axis labels (second axis — NOT in the rank). Mirrors engine/residual_alpha._entry.
# This is TREND-POSITION CONTEXT, not a buy call: "Pullback" = a leader easing back toward its
# trend (a constructive place to WATCH), NOT a confirmed entry. The confirmed BUY label is the
# confluence gate (engine/signal_gate) the discovery board layers on top — so a name can read
# "Pullback" here yet be downtrending on the 3D MACD/StochRSI and therefore NOT buyable.
ENTRY_LABELS = {
    # tag:       (en,          zh,       css)
    "pullback": ("Pullback", "回调",   "tp-pullback"),  # leader easing back to trend (watch, not buy)
    "intact":   ("In trend", "趋势内", "tp-steady"),    # leader, no dip/spike
    "extended": ("Extended", "过热",   "tp-extended"),  # leader just spiked → wait
    "laggard":  ("Laggard",  "落后",   "tp-laggard"),
    "neutral":  ("Neutral",  "中性",   "tp-neutral"),
}


def _winsor_z(s: pd.Series, cap: float = WINSOR_CAP) -> pd.Series:
    """Winsorised cross-sectional z (matches engine.equity_factors._winsor_z)."""
    s = s.astype(float)
    mu, sd = s.mean(), s.std()
    if not sd or np.isnan(sd):
        return pd.Series(0.0, index=s.index)
    return ((s - mu) / sd).clip(-cap, cap)


def _sector_neutral_z(s: pd.Series, sectors: pd.Series, cap: float = WINSOR_CAP) -> pd.Series:
    """Within-GICS demean then winsor-z, so every leg is sector-neutral and unit-variance
    before blending — the same neutralisation the Phase-0 harness scored."""
    s = s.astype(float)
    dem = s - s.groupby(sectors).transform("mean")
    return _winsor_z(dem, cap)


def band(score: float | None) -> str:
    """Position band from a sector-neutral z (drives row colour). Shared with the page."""
    if score is None or (isinstance(score, float) and np.isnan(score)):
        return "mid"
    if score >= 1.0:
        return "strong"
    if score >= 0.3:
        return "leader"
    if score > -0.3:
        return "mid"
    if score > -1.0:
        return "lag"
    return "deeplag"


def entry_meta(entry: str | None) -> tuple[str, str, str]:
    """(en, zh, css) trend-position CONTEXT for an entry tag — defaults to neutral. NOTE this
    is no longer a buy flag: the buy call is the confluence gate (engine/signal_gate)."""
    return ENTRY_LABELS.get(entry or "neutral", ENTRY_LABELS["neutral"])


def compute_scores(rows: list[dict]) -> dict[str, dict]:
    """Cross-sectional Top-Pick scores for the whole universe.

    ``rows`` is a list of per-ticker dicts carrying at least ``ticker``, ``sector`` and
    ``alpha`` (the sector-neutral residual-momentum z), plus any of the confirmation legs
    (``value``/``quality``/``profitability``/``low_vol``/``insider``). Returns
    ``{ticker: {top_score, alpha, conviction_z, n_legs, legs:{...}}}`` for every name that
    has an alpha (nothing to rank without it).

    The conviction tilt is the sector-neutral z-mean of the available confirmation legs;
    a name with fewer than ``MIN_TILT_LEGS`` present gets a neutral (0) tilt, so its score
    degrades to ``ALPHA_W·alpha`` — same ORDER as alpha alone, never penalised for missing
    fundamentals.
    """
    df = pd.DataFrame([r for r in rows if r.get("alpha") is not None])
    if df.empty:
        return {}
    df = df.set_index("ticker")
    sec = df.get("sector")
    if sec is None:
        sec = pd.Series("—", index=df.index)
    sec = sec.fillna("—")

    # neutralise each present leg; missing legs stay NaN (excluded from the mean)
    neutral = {}
    for leg in TILT_LEGS:
        if leg in df.columns:
            col = pd.to_numeric(df[leg], errors="coerce")
            present = col.notna()
            z = pd.Series(np.nan, index=df.index)
            if present.any():
                z.loc[present] = _sector_neutral_z(col[present], sec[present])
            neutral[leg] = z
    legs_df = pd.DataFrame(neutral) if neutral else pd.DataFrame(index=df.index)

    n_legs = legs_df.notna().sum(axis=1)
    conviction = legs_df.mean(axis=1, skipna=True)
    conviction[n_legs < MIN_TILT_LEGS] = 0.0           # too thin → neutral, not penalised
    conviction = conviction.fillna(0.0)

    alpha = pd.to_numeric(df["alpha"], errors="coerce")
    top_score = ALPHA_W * alpha + TILT_W * conviction

    out: dict[str, dict] = {}
    for tk in df.index:
        out[tk] = {
            "top_score": round(float(top_score[tk]), 3),
            "alpha": round(float(alpha[tk]), 3) if pd.notna(alpha[tk]) else None,
            "conviction_z": round(float(conviction[tk]), 3),
            "n_legs": int(n_legs[tk]),
            "legs": {leg: (round(float(neutral[leg][tk]), 2)
                          if leg in neutral and pd.notna(neutral[leg][tk]) else None)
                     for leg in TILT_LEGS},
        }
    return out
