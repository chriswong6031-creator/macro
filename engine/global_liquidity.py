"""Global central-bank LIQUIDITY — the major-CB balance-sheet tide, USD-aggregated.

ADDITIVE / leaf module — imports nothing from the scoring core, and nothing in the
scoring path imports it. A macro CONTEXT driver (the liquidity tide that leads risk
assets), distinct from the existing BTC-vector `global_liquidity` M2 read (that is
broad money; this is central-bank ASSETS).

Each configured central bank's raw FRED balance-sheet series is converted to local
currency (unit_mult), then to USD via the keyless Yahoo FX close (invert for USD/XXX
quotes), resampled to a common weekly grid, and summed into a global liquidity total
in USD trillions. The IMPULSE (13-week & 52-week % change of the total) is what moves
risk assets — shown as context, with an honest note on the lead/lag.

Data is keyless FRED (collectors.fred pulls the series) + keyless Yahoo FX. Degrades
to None if too few banks have data. Major CBs at usable frequency = Fed (weekly) +
ECB (weekly) + BoJ (monthly); BoE is annual-only on FRED and a clean keyless PBoC
series is unavailable, so they are omitted (stated in the panel).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)


def _cfg() -> dict:
    return config.load().get("cb_liquidity", {}) or {}


def _fred_series(series_id: str) -> pd.Series | None:
    df = store.read("fred", series_id)
    if df is None or not len(getattr(df, "columns", [])):
        return None
    return df.iloc[:, 0].astype(float).dropna()


def _fx_to_usd(fx_key: str | None, invert: bool) -> pd.Series | None:
    """USD-per-local conversion series from the keyless Yahoo FX close. None => USD."""
    if not fx_key:
        return None
    df = store.read("yahoo", fx_key)
    if df is None or "close" not in getattr(df, "columns", []):
        return None
    fx = df["close"].astype(float).dropna()
    return (1.0 / fx) if invert else fx


def bank_usd(raw: pd.Series, unit_mult: float, fx: pd.Series | None) -> pd.Series:
    """raw FRED value -> local currency (×unit_mult) -> USD (×fx-to-usd). PURE.
    fx=None means the series is already USD (the Fed). Aligned to the raw index."""
    local = raw.astype(float) * float(unit_mult)
    if fx is None:
        return local
    fxa = fx.reindex(local.index.union(fx.index)).sort_index().ffill().reindex(local.index)
    return (local * fxa).dropna()


def aggregate(bank_series: dict[str, pd.Series], freq: str = "W-FRI") -> pd.DataFrame:
    """Resample each bank's USD series to a weekly grid (ffill), align, and sum where
    ALL banks have data (so the total is comparable through time). PURE. Returns a
    frame with one column per bank (USD) + a `total` column."""
    if not bank_series:
        return pd.DataFrame()
    cols = {}
    for name, s in bank_series.items():
        if s is None or s.empty:
            continue
        cols[name] = s.resample(freq).last().ffill()
    if not cols:
        return pd.DataFrame()
    df = pd.DataFrame(cols).dropna()                 # rows where every bank is present
    if df.empty:
        return df
    df["total"] = df.sum(axis=1)
    return df


def _load(cfg: dict | None = None) -> tuple[pd.DataFrame, dict]:
    cfg = cfg if cfg is not None else _cfg()
    banks = cfg.get("banks", {}) or {}
    series, meta = {}, {}
    for bid, spec in banks.items():
        raw = _fred_series(spec.get("series", ""))
        if raw is None or len(raw) < 30:
            continue
        fx = _fx_to_usd(spec.get("fx"), bool(spec.get("invert", False)))
        if spec.get("fx") and fx is None:           # FX needed but unavailable -> skip
            continue
        series[bid] = bank_usd(raw, spec.get("unit_mult", 1.0), fx)
        meta[bid] = {"label_en": spec.get("label_en", bid), "label_zh": spec.get("label_zh", bid)}
    return aggregate(series), meta


def _impulse(total: pd.Series, weeks: int) -> float | None:
    t = total.dropna()
    if len(t) <= weeks:
        return None
    v = t.iloc[-1] / t.iloc[-1 - weeks] - 1.0
    return float(v * 100.0) if np.isfinite(v) else None


def snapshot(cfg: dict | None = None) -> dict | None:
    cfg = cfg if cfg is not None else _cfg()
    df, meta = _load(cfg)
    if df.empty or "total" not in df or len(df) < 30:
        return None
    total = df["total"]
    tn = total / 1e12                                # USD trillions
    windows = cfg.get("impulse_windows_w", [13, 52])
    imp = {f"{w}w": _round(_impulse(total, int(w))) for w in windows}
    short = imp.get(f"{windows[0]}w") or 0.0
    long = imp.get(f"{windows[-1]}w") or 0.0
    state = ("expanding" if short > 0.3 else "contracting" if short < -0.3 else "flat")
    accel = "accelerating" if short > 0 and long > 0 and short > long / 4 else (
            "decelerating" if short < long / 4 else "steady")
    banks = []
    last = df.iloc[-1]
    for bid in [c for c in df.columns if c != "total"]:
        banks.append({"id": bid, "label_en": meta[bid]["label_en"], "label_zh": meta[bid]["label_zh"],
                      "usd_tn": round(float(last[bid]) / 1e12, 2),
                      "share": round(100.0 * float(last[bid]) / float(last["total"]), 1)})
    banks.sort(key=lambda b: b["usd_tn"], reverse=True)
    spark = [round(float(v), 2) for v in tn.tail(104).tolist()]   # ~2y weekly sparkline
    return {
        "asof": str(total.index[-1].date()),
        "built": datetime.now(timezone.utc).isoformat(),
        "total_usd_tn": round(float(tn.iloc[-1]), 2),
        "impulse_pct": imp, "state": state, "accel": accel,
        "banks": banks, "n_banks": len(banks), "spark": spark,
        "note": ("Global central-bank balance-sheet liquidity (Fed + ECB + BoJ), summed in "
                 "USD. The IMPULSE — its rate of change — leads risk assets with a variable "
                 "lag (weeks to months); rising = a liquidity tailwind. Context, not a signal: "
                 "BoE (FRED annual-only) and PBoC (no clean keyless series) are omitted."),
    }


def _round(v, nd: int = 1):
    return None if v is None or not np.isfinite(v) else round(float(v), nd)
