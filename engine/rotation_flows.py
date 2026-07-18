"""engine/rotation_flows.py — fresh flow/options/gamma receipts (Rotation Events v2).

Flow columns are RECEIPT-ONLY — never used in any event classifier or creation gate
(Constraint 8 / family F). They are attached to velocity board rows and event payloads
as context, labeled "context, not a trigger" in the UI.

Three receipt types, each with its OWN asof stamp:
  etf_flow_receipt   — implied flow delta from data/flows/{ETF}.parquet
  options_receipt    — net_premium_mn from data/options_flow/summary_{etf}.parquet
  gamma_receipt      — gamma_regime from data/polygon_gex/summary_{etf}.parquet

NEVER reads etf_flow_proxy.parquet (16d stale — spec §2.6 note).
Missing feed → null + note field (fail-open, no crash).
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger(__name__)


# ------------------------------------------------------------------ etf flow ----

def etf_flow_receipt(etf: str, data_dir: Path | None = None) -> dict:
    """Fresh implied ETF flow receipt: delta(shares_outstanding * nav) over last 5 days.

    Reads data/flows/{ETF}.parquet (columns: nav, so_mn). Computes:
      implied = so_mn.diff() * nav   (implied $M flow per day — positive = inflow)
      flow_5d_mn = sum of last 5 trading days

    Returns {"flow_5d_mn": float_or_null, "flow_asof": "YYYY-MM-DD", "note": optional}.
    NEVER reads etf_flow_proxy.parquet.
    """
    dd = data_dir or config.data_dir()
    p = dd / "flows" / f"{etf.upper()}.parquet"
    if not p.exists():
        return {"flow_5d_mn": None, "flow_asof": None,
                "note": f"no ETF flow feed ({etf})"}
    try:
        df = pd.read_parquet(p)
        if df.empty or "so_mn" not in df.columns or "nav" not in df.columns:
            return {"flow_5d_mn": None, "flow_asof": None,
                    "note": "flow parquet missing so_mn/nav columns"}
        implied = df["so_mn"].diff() * df["nav"]
        last5 = implied.dropna().tail(5)
        if last5.empty:
            return {"flow_5d_mn": None, "flow_asof": None,
                    "note": "insufficient flow rows"}
        flow_5d = float(last5.sum())
        asof = str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1])
        return {"flow_5d_mn": round(flow_5d, 2), "flow_asof": asof}
    except Exception as exc:  # noqa: BLE001
        log.warning("rotation_flows: etf_flow_receipt(%s) failed — %s", etf, exc)
        return {"flow_5d_mn": None, "flow_asof": None,
                "note": f"read error: {type(exc).__name__}"}


# ------------------------------------------------------------------ options ----

def options_receipt(etf: str, data_dir: Path | None = None) -> dict:
    """Net premium receipt from data/options_flow/summary_{etf}.parquet.

    Returns {"net_premium_mn": float_or_null, "options_asof": "YYYY-MM-DD", "note": optional}.
    """
    dd = data_dir or config.data_dir()
    p = dd / "options_flow" / f"summary_{etf.upper()}.parquet"
    if not p.exists():
        return {"net_premium_mn": None, "options_asof": None,
                "note": f"no options flow feed ({etf})"}
    try:
        df = pd.read_parquet(p)
        if df.empty or "net_premium_mn" not in df.columns:
            return {"net_premium_mn": None, "options_asof": None,
                    "note": "net_premium_mn column missing"}
        val = df["net_premium_mn"].dropna()
        if val.empty:
            return {"net_premium_mn": None, "options_asof": None,
                    "note": "no net_premium_mn data"}
        asof = str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1])
        return {"net_premium_mn": round(float(val.iloc[-1]), 2), "options_asof": asof}
    except Exception as exc:  # noqa: BLE001
        log.warning("rotation_flows: options_receipt(%s) failed — %s", etf, exc)
        return {"net_premium_mn": None, "options_asof": None,
                "note": f"read error: {type(exc).__name__}"}


# ------------------------------------------------------------------ gamma ----

def gamma_receipt(etf: str, data_dir: Path | None = None) -> dict:
    """Gamma regime receipt from data/polygon_gex/summary_{etf}.parquet.

    Returns {"gamma_regime": str_or_null, "gex_asof": "YYYY-MM-DD", "note": optional}.
    """
    dd = data_dir or config.data_dir()
    p = dd / "polygon_gex" / f"summary_{etf.upper()}.parquet"
    if not p.exists():
        return {"gamma_regime": None, "gex_asof": None,
                "note": f"no GEX feed ({etf})"}
    try:
        df = pd.read_parquet(p)
        if df.empty or "gamma_regime" not in df.columns:
            return {"gamma_regime": None, "gex_asof": None,
                    "note": "gamma_regime column missing"}
        val = df["gamma_regime"].dropna()
        if val.empty:
            return {"gamma_regime": None, "gex_asof": None,
                    "note": "no gamma_regime data"}
        asof = str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1])
        return {"gamma_regime": str(val.iloc[-1]), "gex_asof": asof}
    except Exception as exc:  # noqa: BLE001
        log.warning("rotation_flows: gamma_receipt(%s) failed — %s", etf, exc)
        return {"gamma_regime": None, "gex_asof": None,
                "note": f"read error: {type(exc).__name__}"}


# ------------------------------------------------------------------ basket / non-ETF ----

def flow_receipt_for_series(spec: dict, data_dir: Path | None = None) -> dict:
    """Combined flow receipt for one universe series spec.

    For ETF kinds, reads all three feeds (flow, options, gamma) via their own asof.
    For basket_composite / ticker_ew — no ETF flow feed; returns nulls + note.

    Flow columns are CONTEXT ONLY — never classification inputs.
    """
    kind = spec.get("kind", "etf")
    key = spec.get("key", "?")

    if kind == "etf":
        ticker = spec.get("ticker", "")
        fl = etf_flow_receipt(ticker, data_dir)
        opt = options_receipt(ticker, data_dir)
        gex = gamma_receipt(ticker, data_dir)
        return {
            "flow_5d_mn": fl.get("flow_5d_mn"),
            "flow_asof": fl.get("flow_asof"),
            "flow_note": fl.get("note"),
            "net_premium_mn": opt.get("net_premium_mn"),
            "options_asof": opt.get("options_asof"),
            "options_note": opt.get("note"),
            "gamma_regime": gex.get("gamma_regime"),
            "gex_asof": gex.get("gex_asof"),
            "gex_note": gex.get("note"),
        }
    else:
        # baskets and ticker_ew composites have no ETF flow file
        return {
            "flow_5d_mn": None, "flow_asof": None, "flow_note": "no ETF flow feed",
            "net_premium_mn": None, "options_asof": None, "options_note": None,
            "gamma_regime": None, "gex_asof": None, "gex_note": None,
        }
