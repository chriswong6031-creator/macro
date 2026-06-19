"""engine/basket_mtf.py — monthly / weekly / 3-day / daily technicals + momentum for a
consolidated basket index.

Reuses the dashboard's CALIBRATED multi-timeframe engine (engine.cycles) and the
short-vs-long CONFLUENCE reconciliation (engine.btc_mtf) — exactly what the stock analyzer
and the BTC Vector use — but feeds it the basket CANDLE from engine.basket_index instead of
a single name. So a theme says the same kind of thing a stock does: where each timeframe's
MACD/RSI/StochRSI sits, whether the daily tape agrees with the weekly/monthly trend, and one
graded verdict (trend-follow / buy-the-dip / counter-trend / avoid / wait).

Output (per basket):
  {
    "tf":  {D,3D,W,M: {sign, rsi14, macd_pos, cross_up, cross_dn, approaching_up/dn,
                       days_to_cross, spark_rsi, spark_hist}},   # M omitted if history < ~900d
    "confluence": {headline, headline_zh, grade, short_sign, mid_sign, long_sign, per_tf, ...},
    "momentum_score": float in [-1,1],   # the leg theme_scoring blends in (long-TF heavier)
    "trend_aligned": bool,                # all available timeframes point the same way
    "ladder_state", "regime", "as_of"
  }

momentum_score weights the LONGER timeframes more (they are the governor, not the noise):
W and M carry the trend, D/3D the tape. It is a transparent, bounded read — not a forecast.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import btc_mtf, cycles

log = logging.getLogger(__name__)

# momentum weights — longer timeframes govern. Renormalised over the timeframes present.
_TF_W = {"D": 0.15, "3D": 0.15, "W": 0.35, "M": 0.35}


def _tf_row(tf: dict | None) -> dict:
    """Compact per-timeframe row — exactly the fields the desk + detail page render (kept lean
    so 4 timeframes × 25 baskets don't bloat baskets.json)."""
    if not tf:
        return {}
    sp = tf.get("spark_rsi") or []
    return {
        "sign": btc_mtf._tf_sign(tf),
        "rsi14": tf.get("rsi14"),
        "macd_pos": tf.get("macd_pos"),
        "cross_up": tf.get("macd_cross_up"), "cross_dn": tf.get("macd_cross_dn"),
        "approaching_up": tf.get("macd_approaching_up"), "approaching_dn": tf.get("macd_approaching_dn"),
        "days_to_cross": tf.get("macd_days_to_cross"),
        "spark_rsi": [round(float(x)) for x in sp[-16:]],   # 16-pt integer RSI sparkline
    }


def basket_mtf(candle: pd.DataFrame | None) -> dict:
    """Full D/3D/W/M technical read + confluence verdict + a bounded momentum score for one
    basket candle (columns close[,high]). {} on short history or any failure (additive caller)."""
    if candle is None or candle.empty or "close" not in candle:
        return {}
    try:
        close = candle["close"].dropna().astype(float)
        if len(close) < 60:
            return {}
        high = candle["high"].reindex(close.index).astype(float) if "high" in candle else None
        a = cycles.analyze(close, high, kind="equity")
        if not a:
            return {}
        conf = btc_mtf.confluence_verdict(a)
        mtf = a.get("mtf", {}) or {}
        tf_out = {k: _tf_row(mtf.get(k)) for k in ("D", "3D", "W", "M") if mtf.get(k)}

        # momentum score — sign-weighted over available timeframes, longer-TF heavier
        num = den = 0.0
        for k, st in tf_out.items():
            s = st.get("sign")
            if s is None:
                continue
            wgt = _TF_W.get(k, 0.1)
            num += wgt * float(s)
            den += wgt
        momentum = float(np.clip(num / den, -1, 1)) if den else 0.0

        signs = [st.get("sign") for st in tf_out.values() if st.get("sign") is not None]
        trend_aligned = bool(signs) and (all(s > 0 for s in signs) or all(s < 0 for s in signs))

        lad = a.get("ladder", {}) or {}
        return {
            "tf": tf_out,
            "confluence": {
                "headline": conf.get("headline"), "headline_zh": conf.get("headline_zh"),
                "sub": conf.get("sub"), "sub_zh": conf.get("sub_zh"),
                "grade": conf.get("grade"), "grade_zh": conf.get("grade_zh"),
                "short_sign": conf.get("short_sign"), "mid_sign": conf.get("mid_sign"),
                "long_sign": conf.get("long_sign"), "per_tf": conf.get("per_tf"),
            },
            "momentum_score": round(momentum, 3),
            "trend_aligned": trend_aligned,
            "ladder_state": lad.get("state"), "ladder_label": lad.get("label"),
            "ladder_label_zh": lad.get("label_zh"),
            "regime": lad.get("regime"),
            "as_of": str(close.index.max().date()),
            "n_bars": int(len(close)),
            "has_monthly": "M" in tf_out,
        }
    except Exception as e:  # noqa: BLE001 — additive overlay, never break the build
        log.warning("basket_mtf failed: %s", e)
        return {}
