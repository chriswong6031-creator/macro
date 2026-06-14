"""Global credit cycle — BIS credit-to-GDP gap + debt-service ratios.

ADDITIVE / leaf module — imports nothing from the scoring core, and nothing in the
scoring path imports it. The private-sector leverage / financial-stability read our
curve/credit/rates layer lacks, from the keyless BIS statistics (collectors/bis.py).

The credit-to-GDP GAP (Borio-Drehmann) is the BIS's flagship early-warning indicator:
private-non-financial credit/GDP minus its long-run trend. A large POSITIVE gap
(>10pp) has historically led banking crises 1-3y ahead; a negative gap marks
post-deleveraging (the US and China are both negative now). The debt-service ratio is
the leverage burden. CONTEXT only — quarterly, slow-moving, never wired into any score.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)


def _cfg() -> dict:
    return config.load().get("credit_cycle", {}) or {}


def _read(store_key: str) -> pd.Series | None:
    df = store.read("bis", store_key)
    if df is None or not len(getattr(df, "columns", [])):
        return None
    return df.iloc[:, 0].astype(float).dropna()


def _state(gap: float | None, cfg: dict) -> str:
    if gap is None:
        return "—"
    boom = float(cfg.get("boom_gap", 10.0))
    delev = float(cfg.get("delever_gap", -2.0))
    return ("elevated risk" if gap >= boom else "building" if gap >= 2.0
            else "deleveraging" if gap <= delev else "neutral")


def _chg(s: pd.Series, periods: int = 4) -> float | None:
    s = s.dropna()
    if len(s) <= periods:
        return None
    v = s.iloc[-1] - s.iloc[-1 - periods]
    return float(v) if np.isfinite(v) else None


def compute(series: dict[str, pd.Series], cfg: dict | None = None) -> dict | None:
    """PURE — {store_key: series} + config → the credit-cycle panel."""
    cfg = cfg if cfg is not None else _cfg()
    countries = cfg.get("countries", {}) or {}
    rows, asof = [], None
    for cid, spec in countries.items():
        gap = series.get(spec.get("gap", ""))
        dsr = series.get(spec.get("dsr", ""))
        if gap is None and dsr is None:
            continue
        gv = round(float(gap.iloc[-1]), 1) if gap is not None and not gap.empty else None
        dv = round(float(dsr.iloc[-1]), 1) if dsr is not None and not dsr.empty else None
        rows.append({
            "id": cid, "label_en": spec.get("label_en", cid), "label_zh": spec.get("label_zh", cid),
            "gap": gv, "gap_chg_1y": _r(_chg(gap)) if gap is not None else None,
            "gap_state": _state(gv, cfg),
            "dsr": dv, "dsr_chg_1y": _r(_chg(dsr)) if dsr is not None else None,
        })
        for s in (gap, dsr):
            if s is not None and not s.empty:
                asof = max(asof, s.index[-1]) if asof is not None else s.index[-1]
    if not rows:
        return None
    rows.sort(key=lambda r: (r["gap"] if r["gap"] is not None else -99), reverse=True)
    n_elevated = sum(1 for r in rows if r["gap_state"] == "elevated risk")
    top = rows[0]
    headline = (f"{n_elevated} of {len(rows)} elevated" if n_elevated else
                f"no credit booms — highest gap {top['label_en']} {top['gap']}pp")
    return {
        "asof": None if asof is None else str(asof.date()),
        "built": datetime.now(timezone.utc).isoformat(),
        "rows": rows, "n": len(rows), "n_elevated": n_elevated, "headline": headline,
        "note": ("Credit-to-GDP GAP (BIS, Borio-Drehmann) = private-non-financial credit/GDP "
                 "minus its long-run trend; a large positive gap (>10pp) has historically led "
                 "banking crises 1-3y ahead, a negative gap marks post-deleveraging. DSR = the "
                 "debt-service burden. Quarterly, slow-moving structural context — not a signal, "
                 "never scored. Source: BIS statistics (keyless), cite BIS."),
    }


def snapshot(cfg: dict | None = None) -> dict | None:
    cfg = cfg if cfg is not None else _cfg()
    keys = set()
    for spec in (cfg.get("countries", {}) or {}).values():
        keys.update([spec.get("gap"), spec.get("dsr")])
    series = {k: _read(k) for k in keys if k}
    series = {k: v for k, v in series.items() if v is not None}
    if not series:
        return None
    return compute(series, cfg)


def _r(v, nd: int = 1):
    return None if v is None or not np.isfinite(v) else round(float(v), nd)
