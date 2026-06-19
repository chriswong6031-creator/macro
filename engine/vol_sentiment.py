"""Vol-regime + put/call sentiment chip (DISPLAY-ONLY).

A compact volatility-regime and options-sentiment read for the thematic page header —
the "what is the weather" context a theme allocator reads before leaning into risk.

Two parts, both from caches we already keep (zero new collection):

  VOL REGIME   composes the vol fields the conditions engine already publishes in
               data/regime/latest.json (conditions.risk_appetite.vix_term[_state],
               .vrp_state; conditions.complacency.vix_pctile) PLUS the live VIX level
               (data/yahoo/_VIX) and the VIX/VIX3M term structure (data/yahoo/_VIX3M),
               into one 4-state label: CALM / QUIET / ELEVATED / STRESS.

  PUT/CALL     surfaces the CBOE equity & index put/call ratios that collectors/cboe.py
               already writes to data/cboe/putcall.parquet but that NOTHING currently
               reads — a fear/greed read (high p/c = protective/fearful, low = complacent),
               with the obs count flagged because the series is young.

HONEST BY CONSTRUCTION: context only, never scored, no forward claim. Additive — any
shortfall degrades that part to None and the chip simply shows fewer fields.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)


def _r(x, n: int = 2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return round(float(x), n)


def _regime_conditions() -> dict:
    p = config.data_dir() / "regime" / "latest.json"
    if not p.exists():
        return {}
    try:
        return (json.loads(p.read_text()).get("conditions") or {})
    except Exception:  # noqa: BLE001
        return {}


def _vix_term() -> dict:
    """Live VIX level + VIX/VIX3M term structure straight from the yahoo cache (fallback /
    cross-check for the conditions snapshot)."""
    out = {"vix": None, "vix3m": None, "term_ratio": None, "term_state": None}
    v = store.read("yahoo", "_VIX")
    v3 = store.read("yahoo", "_VIX3M")
    if v is not None and "close" in v.columns and not v["close"].dropna().empty:
        out["vix"] = _r(v["close"].dropna().iloc[-1], 1)
    if (v is not None and v3 is not None and "close" in v.columns and "close" in v3.columns):
        a, b = v["close"].dropna().align(v3["close"].dropna(), join="inner")
        if len(a):
            ratio = float(a.iloc[-1] / b.iloc[-1]) if b.iloc[-1] else None
            out["term_ratio"] = _r(ratio, 3)
            if ratio is not None:
                out["term_state"] = ("backwardation" if ratio >= 1.0
                                     else "contango" if ratio <= 0.97 else "flat")
    return out


def _vol_regime() -> dict | None:
    cond = _regime_conditions()
    ra = cond.get("risk_appetite") or {}
    comp = cond.get("complacency") or {}
    term = _vix_term()

    vix_pctile = comp.get("vix_pctile")
    vix_term_state = ra.get("vix_term_state") or ""        # e.g. "contango (calm)"
    vrp_state = ra.get("vrp_state") or ""
    # prefer the freshly-computed term state, fall back to the conditions string
    term_state = term.get("term_state") or (
        "backwardation" if "backward" in vix_term_state else
        "contango" if "contango" in vix_term_state else None)

    back = (term_state == "backwardation")
    contango = (term_state == "contango")
    p = float(vix_pctile) if isinstance(vix_pctile, (int, float)) else None
    stress = (vrp_state.startswith("stress")) or back or (p is not None and p >= 0.75)
    if stress:
        label_en, label_zh, tone = "STRESS", "压力", "neg"
    elif p is not None and p >= 0.60:
        label_en, label_zh, tone = "ELEVATED", "升温", "warn"
    elif p is not None and p <= 0.25 and contango:
        label_en, label_zh, tone = "CALM", "平静", "pos"
    elif p is not None and p <= 0.40:
        label_en, label_zh, tone = "QUIET", "温和", "pos"
    else:
        label_en, label_zh, tone = "NEUTRAL", "中性", "neu"

    out = {
        "label_en": label_en, "label_zh": label_zh, "tone": tone,
        "vix": term.get("vix"), "vix_pctile": _r(p, 3) if p is not None else None,
        "term_ratio": term.get("term_ratio"), "term_state": term_state,
        "vrp_state": vrp_state or None,
        "realized_vol": _r(ra.get("realized_vol"), 1),
        "skew": _r(ra.get("skew"), 1),
    }
    # nothing usable at all -> None so the caller can skip
    if out["vix"] is None and out["vix_pctile"] is None and term_state is None:
        return None
    return out


def _put_call() -> dict | None:
    """CBOE equity & index put/call (collected but otherwise unused). Sentiment = where the
    latest equity p/c sits in its own (young) history."""
    p = config.data_dir() / "cboe" / "putcall.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p).sort_index()
    except Exception:  # noqa: BLE001
        return None
    if df.empty or "equity_pc_ratio" not in df.columns:
        return None
    eq = df["equity_pc_ratio"].dropna()
    idx = df["index_pc_ratio"].dropna() if "index_pc_ratio" in df.columns else pd.Series(dtype=float)
    if eq.empty:
        return None
    n = int(len(eq))
    last = float(eq.iloc[-1])
    pct = float((eq <= last).mean()) if n >= 2 else None      # percentile in own history
    chg5 = (_r((last - float(eq.iloc[-6])), 3) if n > 5 else None)
    # sentiment: high p/c = puts bid = protective/fearful; low = complacent/greedy
    if pct is None:
        sent_en, sent_zh = "—", "—"
    elif pct >= 0.70:
        sent_en, sent_zh = "protective (fearful)", "防御（恐慌）"
    elif pct <= 0.30:
        sent_en, sent_zh = "complacent (greedy)", "自满（贪婪）"
    else:
        sent_en, sent_zh = "neutral", "中性"
    return {
        "equity_pc": _r(last, 3), "index_pc": (_r(idx.iloc[-1], 3) if len(idx) else None),
        "equity_pct_in_hist": _r(pct, 3) if pct is not None else None,
        "equity_chg_5d": chg5, "sentiment_en": sent_en, "sentiment_zh": sent_zh,
        "n_obs": n, "young": bool(n < 60),
        "as_of": eq.index.max().strftime("%Y-%m-%d"),
    }


def compute_vol_sentiment() -> dict | None:
    """The vol-regime + put/call chip payload. None only if BOTH halves are unavailable."""
    vol = _vol_regime()
    pc = _put_call()
    if vol is None and pc is None:
        return None
    return {
        "vol_regime": vol, "put_call": pc,
        "disclaimer_en": ("Display-only context — volatility regime from the conditions "
                          "engine + CBOE put/call. Never scored, no forward claim."),
        "disclaimer_zh": ("仅供展示的背景 — 来自状况引擎的波动率制度 + CBOE 看跌/看涨比。"
                          "不计分，无前瞻判断。"),
    }
