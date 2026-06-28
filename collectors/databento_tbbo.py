"""collectors/databento_tbbo.py — OPRA trades + prevailing NBBO ('tbbo') from Databento.

The ONE optional, ~$0 data add (Databento's $125 signup credit covers a focused universe):
the `tbbo` schema stamps every option TRADE with the prevailing national best bid/offer, so
we can compute GOLD-STANDARD quote-rule signs and CALIBRATE the cheap tick-rule our flow
engine falls back to (massive.com gives us no trade/NBBO tape). Pull a handful of underlyings
over a few dates, hand them to engine/flow_signing, and learn how trustworthy the tick rule
actually is — then state it honestly instead of guessing.

INERT until DATABENTO_API_KEY is set AND the `databento` package is installed. No key/package
-> empty frame, never raises. This is a calibration tool, run occasionally — NOT in the daily
build. Setup: pip install databento; export DATABENTO_API_KEY=...; then
  python -m scripts.calibrate_flow_signing
"""
from __future__ import annotations

import logging
import os

import pandas as pd

log = logging.getLogger(__name__)

DATASET = "OPRA.PILLAR"
SCHEMA = "tcbbo"          # trade + CONSOLIDATED BBO (the true NBBO) — OPRA's tbbo equivalent
MAX_COST_USD = 2.0        # HARD spend cap per fetch (Databento is metered + card-linked)


def enabled() -> bool:
    if not os.environ.get("DATABENTO_API_KEY"):
        return False
    try:
        import databento  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def fetch_tbbo(underlyings, day, *, window=None, max_cost_usd: float = MAX_COST_USD) -> pd.DataFrame:
    """Trades+consolidated-NBBO for `underlyings` on `day` (parent symbology). COST-GUARDED:
    estimates the spend first (free) and ABORTS if it exceeds `max_cost_usd` — Databento is
    metered against a linked card. Pass `window=(start_iso, end_iso)` to pull a short
    intraday slice (a 10-min SPY slice ≈ $0.55 and is ample for signing calibration); else
    the whole day. Returns [ticker, ts, price, size, bid, ask]; empty when disabled/over-cap."""
    if not enabled():
        log.info("databento: DATABENTO_API_KEY/package absent — skip (calibration disabled)")
        return pd.DataFrame()
    if window:
        start, end = window
    else:
        start, end = f"{day.isoformat()}T00:00", f"{day.isoformat()}T23:59"
    syms = [f"{u}.OPT" for u in (underlyings if isinstance(underlyings, list) else [underlyings])]
    try:
        import databento as db
        client = db.Historical(os.environ["DATABENTO_API_KEY"])
        kw = dict(dataset=DATASET, schema=SCHEMA, stype_in="parent", symbols=syms,
                  start=start, end=end)
        est = float(client.metadata.get_cost(**kw))
        if est > max_cost_usd:
            log.warning("databento: estimated $%.2f > cap $%.2f for %s %s..%s — ABORT (narrow the window)",
                        est, max_cost_usd, syms, start, end)
            return pd.DataFrame()
        log.info("databento: pulling %s %s..%s (est $%.2f)", syms, start, end, est)
        store = client.timeseries.get_range(**kw)
        try:
            df = store.to_df(price_type="float")           # newer client
        except TypeError:
            df = store.to_df()                              # older client: prices already float
    except Exception as e:  # noqa: BLE001 — vendor/credit/symbol issues must not raise
        log.warning("databento fetch failed: %s", e)
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.reset_index()                                   # ts_recv/ts_event off the index
    col = {c.lower(): c for c in df.columns}
    def pick(*names):
        for n in names:
            if n in col:
                return col[n]
        return None
    out = pd.DataFrame({
        "ticker": df[pick("symbol", "raw_symbol") or df.columns[0]].astype(str),
        "ts": pd.to_datetime(df[pick("ts_event", "ts_recv")], errors="coerce")
              if pick("ts_event", "ts_recv") else pd.NaT,
        "price": pd.to_numeric(df[pick("price")], errors="coerce"),
        "size": pd.to_numeric(df[pick("size")], errors="coerce"),
        "bid": pd.to_numeric(df[pick("bid_px_00", "bid_px", "bid")], errors="coerce"),
        "ask": pd.to_numeric(df[pick("ask_px_00", "ask_px", "ask")], errors="coerce"),
    })
    return out.dropna(subset=["price", "bid", "ask"]).reset_index(drop=True)
