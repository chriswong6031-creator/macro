"""Funding / repo plumbing stress — from the keyless OFR reference rates.

ADDITIVE / leaf module — imports nothing from the scoring core, and nothing in the
scoring path imports it. The repo/money-market PLUMBING read our Fed-balance-sheet
+ RRP liquidity layer lacks. Two recognized stress gauges, both from OFR's FRBNY
reference rates (collectors/ofr.py):

  • SOFR − EFFR spread: SOFR (secured overnight repo) persistently ABOVE the Fed's
    administered EFFR means reserves are getting scarce / repo is bid up — the
    classic post-2019 funding-stress tell (Sep-2019 repo spike).
  • SOFR dispersion (99th percentile − SOFR): a fat right tail = some borrowers
    paying well above the median, an early sign of collateral/funding pressure.

Each is scored as a trailing-window percentile; the composite 0-100 stress score
bands into calm / watch / stressed. CONTEXT only — never wired into any score.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# the OFR mnemonics this leaf consumes (must be collected by collectors/ofr.py)
SERIES = {"sofr": "FNYR-SOFR-A", "effr": "FNYR-EFFR-A", "obfr": "FNYR-OBFR-A",
          "sofr_p99": "FNYR-SOFR_99Pctl-A", "sofr_p1": "FNYR-SOFR_1Pctl-A",
          "bgcr": "FNYR-BGCR-A", "tgcr": "FNYR-TGCR-A"}


def _cfg() -> dict:
    return config.load().get("funding_stress", {}) or {}


def _read(mnemonic: str) -> pd.Series | None:
    df = store.read("ofr", mnemonic)
    if df is None or not len(getattr(df, "columns", [])):
        return None
    return df.iloc[:, 0].astype(float).dropna()


def _pctile(s: pd.Series, lookback: int) -> float | None:
    s = s.dropna()
    if len(s) < 60:
        return None
    win = s.tail(lookback)
    return float((win <= win.iloc[-1]).mean() * 100.0)


def compute(d: dict[str, pd.Series], cfg: dict | None = None) -> dict | None:
    """PURE — takes {col: series} (SOFR/EFFR/SOFR_p99/…) and returns the funding-stress
    snapshot. Spread & dispersion in basis points; each scored vs a trailing window."""
    cfg = cfg if cfg is not None else _cfg()
    lb = int(cfg.get("pctile_lookback_d", 504))
    sofr, effr = d.get("sofr"), d.get("effr")
    if sofr is None or effr is None or sofr.empty:
        return None
    idx = sofr.index.intersection(effr.index)
    spread = ((sofr.reindex(idx) - effr.reindex(idx)) * 100.0).dropna()        # bp
    p99 = d.get("sofr_p99")
    disp = (((p99.reindex(sofr.index) - sofr) * 100.0).dropna()                # bp, right tail
            if p99 is not None else pd.Series(dtype=float))
    if spread.empty:
        return None

    spread_pct = _pctile(spread, lb)
    disp_pct = _pctile(disp, lb) if not disp.empty else None
    parts = [p for p in (spread_pct, disp_pct) if p is not None]
    score = round(float(np.mean(parts)), 0) if parts else None
    state = ("stressed" if (score or 0) >= 90 else "watch" if (score or 0) >= 70 else "calm")

    rows = [{"key": "sofr_effr", "label_en": "SOFR − EFFR spread", "label_zh": "SOFR − 联邦基金利率",
             "value": round(float(spread.iloc[-1]), 1), "unit": "bp", "pctile": _r(spread_pct),
             "note": "SOFR above the Fed's administered rate = reserves scarce / repo stress."}]
    if not disp.empty:
        rows.append({"key": "sofr_disp", "label_en": "SOFR dispersion (99th − SOFR)",
                     "label_zh": "SOFR 离散度 (99分位 − SOFR)", "value": round(float(disp.iloc[-1]), 1),
                     "unit": "bp", "pctile": _r(disp_pct),
                     "note": "A fat right tail = some borrowers paying well above the median."})
    levels = []
    for k, lab in (("sofr", "SOFR"), ("effr", "EFFR"), ("obfr", "OBFR"),
                   ("bgcr", "Broad GC repo"), ("tgcr", "Tri-party GC repo")):
        s = d.get(k)
        if s is not None and not s.empty:
            levels.append({"key": k, "label": lab, "value": round(float(s.iloc[-1]), 3)})

    spark = [round(float(v), 1) for v in spread.tail(252).tolist()]
    return {
        "asof": str(spread.index[-1].date()),
        "built": datetime.now(timezone.utc).isoformat(),
        "score": score, "state": state,
        "spread_bp": round(float(spread.iloc[-1]), 1),
        "dispersion_bp": None if disp.empty else round(float(disp.iloc[-1]), 1),
        "rows": rows, "levels": levels, "spark": spark,
        "note": ("Funding/repo plumbing from the OFR FRBNY reference rates (keyless). SOFR "
                 "above EFFR and a widening SOFR distribution flag reserve scarcity / repo "
                 "stress (the Sep-2019 tell). Each scored vs its trailing ~2y range. Context, "
                 "not a signal — never wired into any score."),
    }


def snapshot(cfg: dict | None = None) -> dict | None:
    d = {col: _read(mn) for col, mn in SERIES.items()}
    d = {k: v for k, v in d.items() if v is not None}
    if "sofr" not in d or "effr" not in d:
        return None
    return compute(d, cfg)


def _r(v, nd: int = 0):
    return None if v is None or not np.isfinite(v) else round(float(v), nd)
