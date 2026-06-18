"""Cross-country comparison structures for the International macro dashboard —
the centerpiece "compare them with each other" layer. Pure functions over the
per-country records assembled in engine.intl_run; plus the Eurozone periphery
(BTP-Bund) fragmentation panel. All descriptive / display-only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import intl_inputs

# (key, label_en, label_zh, higher_is_riskier) — the comparison metrics ranked
RANK_METRICS = [
    ("recession_score", "Recession pressure", "衰退压力", True),
    ("drawdown_risk", "Equity drawdown risk", "股市回撤风险", True),
    ("real_yield", "Real 10y yield", "实际10年收益", False),
    ("yield_10y", "10y yield", "10年期收益", False),
    ("fx_strength_3m", "Currency 3m", "货币3月", False),
    ("cpi_yoy", "Inflation (CPI)", "通胀", True),
]


def _val(rec: dict, key: str):
    if key in ("recession_score",):
        return rec.get("recession_score")
    if key in ("drawdown_risk",):
        return (rec.get("equity") or {}).get("drawdown_risk")
    return (rec.get("macro") or {}).get(key)


def rankings(records: list[dict]) -> dict:
    """For each comparison metric: countries sorted best->worst with values."""
    out = {}
    for key, en, zh, risk_high in RANK_METRICS:
        rows = [{"cc": r["cc"], "flag": r["flag"], "name": r["name"], "value": _val(r, key)}
                for r in records if _val(r, key) is not None]
        if not rows:
            continue
        rows.sort(key=lambda x: x["value"], reverse=risk_high)
        out[key] = {"label_en": en, "label_zh": zh, "risk_high": risk_high, "rows": rows}
    return out


def regime_heatmap(records: list[dict]) -> list[dict]:
    """Compact per-country regime cells for the heatmap (quad + scores + confidence)."""
    return [{"cc": r["cc"], "flag": r["flag"], "name": r["name"], "region": r.get("region"),
             "quad": r.get("quad"), "quad_name": r.get("quad_name"),
             "growth": r.get("growth_score"), "inflation": r.get("inflation_score"),
             "confidence": r.get("confidence"), "data_limited": r.get("data_limited", False)}
            for r in records]


def periphery_panel() -> dict | None:
    """Eurozone fragmentation: peripheral 10y spreads over the Bund (BTP/Bonos/OAT
    minus DE). Widening = risk-off in the periphery. Display-only."""
    s = intl_inputs.read_intl_macro_col      # shared single-column intl_macro reader
    de = s("de_10y")
    if de is None:
        return None
    out = {"asof": str(de.index[-1].date()), "spreads": []}
    for col, label, label_zh, flag in [
        ("it_10y", "Italy (BTP)", "意大利 (BTP)", "🇮🇹"),
        ("es_10y", "Spain (Bonos)", "西班牙 (Bonos)", "🇪🇸"),
        ("fr_10y", "France (OAT)", "法国 (OAT)", "🇫🇷"),
    ]:
        x = s(col)
        if x is None:
            continue
        idx = de.index.union(x.index)
        spread = (x.reindex(idx).ffill() - de.reindex(idx).ffill()).dropna()
        if spread.empty:
            continue
        last = float(spread.iloc[-1]) * 100  # -> basis points
        chg3m = (float(spread.iloc[-1] - spread.iloc[-64]) * 100) if len(spread) > 64 else None
        out["spreads"].append({
            "label": label, "label_zh": label_zh, "flag": flag, "bps": round(last, 0),
            "chg3m_bps": round(chg3m, 0) if chg3m is not None else None,
            "widening": bool(chg3m is not None and chg3m > 0),
        })
    return out if out["spreads"] else None


def global_summary(records: list[dict]) -> dict:
    """Headline counts for the hero + hub card."""
    quads, watch, dd_watch = {}, 0, 0
    rec_scores = []
    for r in records:
        q = r.get("quad_name") or "—"
        quads[q] = quads.get(q, 0) + 1
        if (r.get("recession_score") or 0) >= 45:
            watch += 1
        if ((r.get("equity") or {}).get("drawdown_risk") or 0) >= 35:
            dd_watch += 1
        if r.get("recession_score") is not None:
            rec_scores.append(r["recession_score"])
    dominant = max(quads.items(), key=lambda kv: kv[1])[0] if quads else "—"
    return {"n": len(records), "quad_counts": quads, "dominant_quad": dominant,
            "recession_watch": watch, "drawdown_watch": dd_watch,
            "avg_recession": round(float(np.mean(rec_scores)), 0) if rec_scores else None}
