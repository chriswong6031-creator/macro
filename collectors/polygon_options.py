"""Polygon.io / massive.com options-OI collector — the GEX accrual FOUNDATION.

The free Cboe feed (collectors/cboe.py) returns a live delayed chain, but the runner
stores only a 1-row/day GEX summary and THROWS THE PER-STRIKE CHAIN AWAY. Polygon's
options snapshot returns per-contract open_interest + implied_vol for the whole
chain (verified entitled on the stocks+options plan; index/futures/fx/crypto are
NOT — index spot I:SPX is 403, so SPX is excluded). We snapshot the GEX universe
each day and persist the RAW per-strike chain so any dealer-gamma variant can be
recomputed later from real OI — the one thing that CANNOT be backfilled (open
interest is point-in-time only; there is no historical-OI endpoint).

DISPLAY / RESEARCH ONLY, never a scored signal. Carries the same honest framing as
engine/gex_engine.py: the dealer long-call / short-put SIGN is an assumption,
single-name GEX is fragile to one large non-dealer position, and this is a
VOL-REGIME + LEVELS MAP, not alpha (see LIMITATIONS.md).

snapshot() returns a per-strike DataFrame carrying the engine's input columns
[K, T, iv, oi, is_call, expiry] PLUS [underlying, strike_ticker, gamma, delta,
volume, spot, asof] for the raw store. engine.gex_engine.compute_gex consumes the
K/T/iv/oi/is_call subset directly.
"""
from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


def _f(x) -> float:
    """Best-effort float; NaN on missing/non-finite (illiquid wings lack iv/greeks)."""
    try:
        v = float(x)
        return v if np.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def parse_chain(results: list[dict], underlying: str, spot: float, asof: date, *,
                window_pct: float, max_expiry_days: int) -> pd.DataFrame:
    """Polygon options-snapshot ``results`` -> per-strike chain frame. Pure (no I/O)
    so tests can feed canned JSON. Keeps only OI>0 contracts inside the strike/expiry
    window (zero-OI contributes nothing to GEX and only bloats the store); iv/gamma
    may be NaN on illiquid wings — preserved, since the raw OI is the irreplaceable
    bit and IV can be re-implied later."""
    if not results or not (spot and spot > 0):
        return pd.DataFrame()
    asof_ts = pd.Timestamp(asof)
    lo, hi = spot * (1 - window_pct), spot * (1 + window_pct)
    horizon = asof_ts + pd.Timedelta(days=max_expiry_days)
    rows = []
    for c in results:
        det = c.get("details") or {}
        K = det.get("strike_price")
        exp = det.get("expiration_date")
        ctype = det.get("contract_type")
        oi = c.get("open_interest")
        if K is None or exp is None or ctype not in ("call", "put") or not oi or oi <= 0:
            continue
        if not (lo <= K <= hi):
            continue
        exp_ts = pd.Timestamp(exp)
        if exp_ts < asof_ts or exp_ts > horizon:
            continue
        T = (exp_ts - asof_ts).days / 365.0
        if T <= 0:
            continue
        gk = c.get("greeks") or {}
        rows.append({
            "underlying": underlying,
            "strike_ticker": det.get("ticker"),
            "expiry": exp_ts,
            "K": float(K),
            "T": float(T),
            "is_call": ctype == "call",
            "oi": float(oi),
            "iv": _f(c.get("implied_volatility")),
            "gamma": _f(gk.get("gamma")),
            "delta": _f(gk.get("delta")),
            "volume": _f((c.get("day") or {}).get("volume")),
            "spot": float(spot),
            "asof": asof_ts,
        })
    return pd.DataFrame(rows)


class PolygonOptions(Adapter):
    """Thin Polygon REST client (reuses Adapter.http_get for retry/UA). NOT in the
    collect.py adapter registry — it is driven by scripts/build_polygon_gex.py, which
    owns the date-partitioned raw-chain persistence the standard 1-row/day upsert path
    cannot express."""

    name = "polygon_gex"
    group = "polygon_gex"

    def __init__(self) -> None:
        self.cfg = config.load()["polygon"]
        # massive.com is a Polygon clone; accept either secret name (a prior session
        # seeded MASSIVE_API_KEY in .env) so the CI accrual never silently no-ops.
        self.key = (config.secret(self.cfg.get("api_key_env", "POLYGON_API_KEY"))
                    or config.secret("MASSIVE_API_KEY"))
        self.base = self.cfg["base_url"].rstrip("/")

    def enabled(self) -> bool:
        return bool(self.key)

    def _get(self, path: str, params: dict) -> list[dict]:
        """GET base+path, following snapshot pagination (next_url) up to max_pages.
        next_url carries the cursor but not the key, so apiKey is re-attached."""
        url = f"{self.base}{path}"
        params = {**params, "apiKey": self.key}
        out: list[dict] = []
        for _ in range(int(self.cfg.get("max_pages", 40))):
            r = self.http_get(url, retries=int(self.cfg.get("retries", 3)),
                              timeout=int(self.cfg.get("request_timeout", 60)), params=params)
            j = r.json()
            out.extend(j.get("results") or [])
            nxt = j.get("next_url")
            if not nxt:
                break
            url, params = nxt, {"apiKey": self.key}
        return out

    def spot(self, symbol: str) -> float | None:
        """Last/close from the (15-min delayed) stock snapshot — fine for an EOD build.
        Prefers the day close, then the last minute, then prior close."""
        try:
            r = self.http_get(
                f"{self.base}/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}",
                retries=int(self.cfg.get("retries", 3)),
                timeout=int(self.cfg.get("request_timeout", 60)),
                params={"apiKey": self.key})
            t = (r.json() or {}).get("ticker") or {}
            for v in (t.get("day", {}).get("c"), t.get("min", {}).get("c"),
                      t.get("prevDay", {}).get("c")):
                if v and v > 0:
                    return float(v)
        except Exception as e:  # noqa: BLE001 — caller degrades per-symbol
            log.warning("polygon spot %s failed: %s", symbol, e)
        return None

    def chain(self, symbol: str, spot: float, asof: date) -> pd.DataFrame:
        """Server-side-filtered option chain (exp <= horizon, strike within band) ->
        per-strike frame via parse_chain."""
        gx = self.cfg["gex"]
        w = float(gx["strike_window_pct"])
        horizon = (pd.Timestamp(asof) + pd.Timedelta(days=int(gx["max_expiry_days"]))).date()
        results = self._get(f"/v3/snapshot/options/{symbol}", {
            "expiration_date.lte": horizon.isoformat(),
            "strike_price.gte": round(spot * (1 - w), 2),
            "strike_price.lte": round(spot * (1 + w), 2),
            "limit": 250,
        })
        return parse_chain(results, symbol, spot, asof,
                          window_pct=w, max_expiry_days=int(gx["max_expiry_days"]))

    def _one_chain(self, sym: str, asof: date) -> pd.DataFrame | None:
        """Spot + chain for ONE underlying (the unit of work parallelised by snapshot()).
        Returns None on no-spot / empty-chain / error so a failed symbol just drops out."""
        try:
            s = self.spot(sym)
            if not s:
                log.warning("polygon: no spot for %s — skipping", sym)
                return None
            ch = self.chain(sym, s, asof)
            if ch.empty:
                log.warning("polygon: empty chain for %s", sym)
                return None
            log.info("polygon: %s spot=%.2f rows=%d", sym, s, len(ch))
            return ch
        except Exception as e:  # noqa: BLE001 — partial coverage still useful
            log.warning("polygon: %s chain failed: %s", sym, e)
            return None

    def snapshot(self, symbols: list[str], asof: date) -> pd.DataFrame:
        """Spot + chain for each underlying -> one stacked per-strike frame for the day.
        Partial coverage is fine — a failed symbol is logged and skipped. The per-symbol
        REST work (2 I/O-bound calls each) is fanned across a small thread pool so the now-
        broad universe (hundreds of names) finishes in minutes; `polygon.workers` caps
        concurrency at the massive.com-safe ceiling (~5-6). workers<=1 -> serial (unchanged)."""
        workers = max(1, int(self.cfg.get("workers", 5)))
        if workers <= 1 or len(symbols) <= 1:
            frames = [c for c in (self._one_chain(sym, asof) for sym in symbols) if c is not None]
        else:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(workers, len(symbols))) as ex:
                frames = [c for c in ex.map(lambda s: self._one_chain(s, asof), symbols)
                          if c is not None]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
