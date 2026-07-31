"""BTC macro-regime P5: MSTR / digital-asset-treasury (DAT) demand — DISPLAY-ONLY.

Reads a manually-maintained JSON drop at data/dat_holdings.json, whose schema is:

    {
        "asof": "2026-06-20",          // ISO date of the 8-K / press release
        "btc_held": 226500,            // BTC held by the treasury
        "shares_out": 263000000,       // diluted shares outstanding
        "avg_cost_usd": 36798.0,       // average cost basis per BTC (8-K disclosed)
        "ticker": "MSTR",              // optional; defaults to MSTR
        "entity_name": "Strategy Inc"  // optional display name
    }

This is a MANUAL 8-K-sourced drop, NOT a 13F feed. 13F is filed 45 days after
quarter-end and only shows equity holdings; it does NOT capture BTC held directly
on the balance sheet.  The 8-K / press-release cadence is ~weekly for MSTR.

MSTR price is read from signals.parquet column "close" when the ticker matches
(MSTR is not in the BTC signals file — it would need to be pulled from a separate
equity store). Fallback: if the JSON includes a "price_usd" field (manually
updated), that is used directly.

Computed metrics (all DISPLAY-ONLY, DEGRADE-NEVER-RAISE):
  - mNAV      = MSTR market-cap / (btc_held × btc_price)
                where market-cap = price_usd × shares_out
  - premium_pct = (mNAV - 1) × 100   (positive = market pays premium vs BTC NAV)
  - btc_per_share = btc_held / shares_out
  - forced_sell_distance_pct = how far BTC is ABOVE the estimated margin-call
                level, which is approximately avg_cost × 0.78 (a −22% haircut
                from avg-cost basis, a conservative approximation of the leverage
                ratio disclosed in their credit agreements).  Positive = safe.
  - state: "premium" / "parity" / "discount"

Config keys (under btc_dat:):
  enabled: true
  json_path: "data/dat_holdings.json"   # relative to repo root
  margin_haircut: 0.78   # fraction of avg_cost → approximate forced-sell level
  parity_band: 0.05      # |premium_pct| <= 5 → parity
  stale_after_days: 14   # asof older than this → stale=true (manual feed health)

Dependencies: pandas, numpy (already in repo).  No new pip deps.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)


def _f(v):
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception as e:
        log.warning("btc_dat: failed to load %s: %s", path, e)
        return None


def _btc_price_from_signals() -> float | None:
    """Read the last BTC close from signals.parquet (vector store)."""
    try:
        df = store.read("vector", "signals")
        if df is None or df.empty or "close" not in df.columns:
            return None
        return _f(df["close"].dropna().iloc[-1])
    except Exception:
        return None


def compute(holdings_path: str | None = None,
            btc_price_override: float | None = None) -> dict:
    """Build the MSTR/DAT demand card. Never raises.

    Parameters
    ----------
    holdings_path:
        Override path to the holdings JSON (for testing). Defaults to the
        config value btc_dat.json_path, then "data/dat_holdings.json".
    btc_price_override:
        Force a BTC price for testing without a live store.
    """
    try:
        full_cfg = config.load()
        cfg = full_cfg.get("btc_dat") or full_cfg.get("vector", {}).get("btc_dat", {})
        if not cfg.get("enabled", True):
            return {"ok": False, "reason": "btc_dat disabled in config"}

        margin_haircut = float(cfg.get("margin_haircut", 0.78))
        parity_band = float(cfg.get("parity_band", 0.05))
        stale_after_days = int(cfg.get("stale_after_days", 14))

        # ------------------------------------------------------------------ #
        # Load holdings JSON
        # ------------------------------------------------------------------ #
        if holdings_path is None:
            rel = cfg.get("json_path", "data/dat_holdings.json")
            json_path = Path(config.ROOT) / rel
        else:
            json_path = Path(holdings_path)

        data = _load_json(json_path)
        if data is None:
            return {
                "ok": False,
                "reason": (
                    f"dat_holdings.json not found at {json_path}. "
                    "Drop a manually-sourced 8-K JSON to enable this module."
                ),
            }

        # ------------------------------------------------------------------ #
        # Required fields
        # ------------------------------------------------------------------ #
        btc_held = _f(data.get("btc_held"))
        shares_out = _f(data.get("shares_out"))
        avg_cost = _f(data.get("avg_cost_usd"))
        asof = str(data.get("asof", "unknown"))
        ticker = str(data.get("ticker", "MSTR"))
        entity_name = str(data.get("entity_name", "Strategy Inc"))

        if btc_held is None or btc_held <= 0:
            return {"ok": False, "reason": "btc_held missing or zero in dat_holdings.json"}
        if shares_out is None or shares_out <= 0:
            return {"ok": False, "reason": "shares_out missing or zero in dat_holdings.json"}

        # ------------------------------------------------------------------ #
        # BTC price
        # ------------------------------------------------------------------ #
        btc_price = btc_price_override
        price_source = "override"
        if btc_price is None:
            btc_price = _f(data.get("price_usd"))
            price_source = "json (manual)"
        if btc_price is None:
            btc_price = _btc_price_from_signals()
            price_source = "signals.parquet"
        if btc_price is None or btc_price <= 0:
            return {
                "ok": False,
                "reason": (
                    "BTC price unavailable. Add 'price_usd' to dat_holdings.json "
                    "or ensure signals.parquet is present."
                ),
            }

        # MSTR price: try json field "stock_price_usd" then degrade gracefully
        mstr_price = _f(data.get("stock_price_usd"))
        mstr_price_source = "json (manual)" if mstr_price is not None else None

        # ------------------------------------------------------------------ #
        # Metrics
        # ------------------------------------------------------------------ #
        btc_nav = btc_held * btc_price            # USD
        btc_per_share = btc_held / shares_out

        mnav: float | None = None
        premium_pct: float | None = None
        state = "unknown"

        if mstr_price is not None and mstr_price > 0:
            mktcap = mstr_price * shares_out      # USD
            mnav = mktcap / btc_nav               # dimensionless ratio
            premium_pct = (mnav - 1.0) * 100.0
            if abs(premium_pct) <= parity_band * 100:
                state = "parity"
            elif premium_pct > 0:
                state = "premium"
            else:
                state = "discount"

        # Forced-sell proximity: positive = BTC above the margin-call level
        forced_sell_distance_pct: float | None = None
        margin_trigger_usd: float | None = None
        if avg_cost is not None and avg_cost > 0:
            margin_trigger_usd = avg_cost * margin_haircut
            forced_sell_distance_pct = (btc_price / margin_trigger_usd - 1.0) * 100.0

        # Staleness of the hand-maintained drop (W4: this feed advises the
        # owner's re-entry view but must never veto sizing — a stale manual
        # JSON silently hard-blocking a buy window would be worse than no chip).
        age_days: int | None = None
        stale = True
        try:
            age_days = int((pd.Timestamp.now().normalize() - pd.Timestamp(asof)).days)
            stale = age_days > stale_after_days
        except (TypeError, ValueError):
            pass  # unparseable asof stays stale=True

        return {
            "ok": True,
            "display_only": True,
            "asof": asof,
            "age_days": age_days,
            "stale": stale,
            "ticker": ticker,
            "entity_name": entity_name,
            "btc_held": btc_held,
            "btc_price_usd": round(btc_price, 2),
            "btc_price_source": price_source,
            "btc_nav_bn": round(btc_nav / 1e9, 3),
            "btc_per_share": round(btc_per_share, 6),
            "mnav": round(mnav, 3) if mnav is not None else None,
            "premium_pct": round(premium_pct, 1) if premium_pct is not None else None,
            "state": state,
            "avg_cost_usd": round(avg_cost, 2) if avg_cost is not None else None,
            "margin_trigger_usd": round(margin_trigger_usd, 2) if margin_trigger_usd is not None else None,
            "forced_sell_distance_pct": (
                round(forced_sell_distance_pct, 1)
                if forced_sell_distance_pct is not None else None
            ),
            "mstr_price_usd": round(mstr_price, 2) if mstr_price is not None else None,
            "mstr_price_source": mstr_price_source,
            "note": (
                "Display-only. MSTR/DAT treasury demand. mNAV = MSTR mktcap / "
                "(btc_held × btc_price). forced_sell_distance_pct > 0 = BTC above "
                f"estimated margin trigger (avg_cost × {margin_haircut}). "
                "Source: manual 8-K drop — NOT 13F (13F only covers equity, not "
                "direct BTC holdings; 45-day lag)."
            ),
        }
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}
