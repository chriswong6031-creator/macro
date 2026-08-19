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

snapshot() returns (chain_df, census): a per-strike DataFrame carrying the engine's
input columns [K, T, iv, oi, is_call, expiry] PLUS [underlying, strike_ticker,
gamma, delta, volume, spot, asof] for the raw store, plus a per-symbol failure
CENSUS (AD-1C0) so an all-underlying vendor outage never again collapses to a
bare "empty" with no cause. engine.gex_engine.compute_gex consumes the
K/T/iv/oi/is_call subset directly.
"""
from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd
import requests

from collectors.base import Adapter, safe_exc_text
from lib import config

log = logging.getLogger(__name__)

# Frozen per-symbol failure-reason codes (AD-1C0). Every path that used to collapse
# to a bare None now returns one of these instead, so an all-symbol failure can
# never again surface as a reasonless empty snapshot. Kept as a module-level
# constant so tests and scripts/build_polygon_gex.py can validate against it.
REASON_CODES = frozenset({
    "no_spot",                     # spot() returned None (200-OK, no usable price)
    "auth_or_entitlement_failure", # HTTP 401/403 (vendor NOT_AUTHORIZED)
    "rate_limit_or_throttle",      # HTTP 429
    "vendor_or_network_error",     # any other HTTPError / ConnectionError / Timeout
    "raw_chain_empty",             # vendor 200 with zero results
    "parse_or_filter_empty",       # nonempty raw emptied by the strike/expiry/OI filter
    "other_failure",               # anything else (catch-all)
})

# If the first this-many attempted underlyings ALL come back
# auth_or_entitlement_failure with zero successes, the key is almost certainly
# de-entitled for the whole run — abort the remaining universe rather than paying
# its full retry budget on a foregone conclusion (measured: ~1,125 requests / ~13
# min at the pre-fix universe size, all 403).
AUTH_SHORT_CIRCUIT_PROBE = 5


def _classify_exception(exc: Exception) -> str:
    """Map a fetch exception to one of the frozen REASON_CODES.

    `requests.HTTPError` carries the response on `.response` for BOTH the
    library's own `raise_for_status()` raises and `Adapter.http_get`'s explicit
    raise on 429/5xx, so the status code is available in either case. A text
    fallback (vendor body / message sniff) covers the rare case a wrapper loses
    the response object.
    """
    if isinstance(exc, requests.HTTPError):
        resp = getattr(exc, "response", None)
        code = getattr(resp, "status_code", None)
        if code in (401, 403):
            return "auth_or_entitlement_failure"
        if code == 429:
            return "rate_limit_or_throttle"
        text = str(exc)
        if "NOT_AUTHORIZED" in text or "401" in text.split() or "403" in text.split():
            return "auth_or_entitlement_failure"
        if "429" in text.split():
            return "rate_limit_or_throttle"
        return "vendor_or_network_error"
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return "vendor_or_network_error"
    return "other_failure"


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

    def ticker_details(self, symbol: str) -> dict:
        """GET /v3/reference/tickers/{symbol} -> the ``results`` object (shares
        outstanding, SIC industry). Single-object endpoint: ``results`` is a
        DICT, so it must not go through _get — list.extend over that dict
        iterates its KEYS, which is exactly how the S&P 500 shares reference
        shipped all-None for four weekly sweeps (2026-07-11..08-02)."""
        r = self.http_get(f"{self.base}/v3/reference/tickers/{symbol}",
                          retries=int(self.cfg.get("retries", 3)),
                          timeout=int(self.cfg.get("request_timeout", 60)),
                          params={"apiKey": self.key})
        res = (r.json() or {}).get("results")
        return res if isinstance(res, dict) else {}

    def spot(self, symbol: str) -> float | None:
        """Last/close from the (15-min delayed) stock snapshot — fine for an EOD build.
        Prefers the day close, then the last minute, then prior close.

        RAISES on a transport/vendor failure (401/403/429/5xx/timeout/...) so the
        caller (`_one_chain`) can classify the failure by REASON instead of a bare
        None; returns None only when the vendor responds 200-OK with no usable
        price field anywhere in the payload."""
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
        return None

    def _fetch_raw_results(self, symbol: str, spot: float, asof: date) -> list[dict]:
        """The vendor GET only (no parsing) — split out from `chain()` so a caller
        can tell an EMPTY VENDOR RESPONSE (raw_chain_empty) from a NONEMPTY response
        that the strike/expiry/OI filter emptied (parse_or_filter_empty)."""
        gx = self.cfg["gex"]
        w = float(gx["strike_window_pct"])
        horizon = (pd.Timestamp(asof) + pd.Timedelta(days=int(gx["max_expiry_days"]))).date()
        return self._get(f"/v3/snapshot/options/{symbol}", {
            "expiration_date.lte": horizon.isoformat(),
            "strike_price.gte": round(spot * (1 - w), 2),
            "strike_price.lte": round(spot * (1 + w), 2),
            "limit": 250,
        })

    def chain(self, symbol: str, spot: float, asof: date) -> pd.DataFrame:
        """Server-side-filtered option chain (exp <= horizon, strike within band) ->
        per-strike frame via parse_chain. Public convenience wrapper; `snapshot()`
        drives `_fetch_raw_results`/`parse_chain` separately so it can classify an
        empty result by WHICH stage emptied it."""
        gx = self.cfg["gex"]
        results = self._fetch_raw_results(symbol, spot, asof)
        return parse_chain(results, symbol, spot, asof,
                          window_pct=float(gx["strike_window_pct"]),
                          max_expiry_days=int(gx["max_expiry_days"]))

    def _one_chain(self, sym: str, asof: date) -> tuple[pd.DataFrame | None, str | None]:
        """Spot + chain for ONE underlying (the unit of work parallelised by snapshot()).

        Returns ``(chain_df, None)`` on success or ``(None, reason_code)`` on
        failure, ``reason_code`` being one of the frozen REASON_CODES — so a failed
        symbol still drops out of the stacked frame, but WHY it failed is preserved
        for snapshot()'s census instead of collapsing to a bare None."""
        try:
            s = self.spot(sym)
        except Exception as e:  # noqa: BLE001 — classified, not swallowed blind
            reason = _classify_exception(e)
            log.warning("polygon: %s spot failed (%s): %s", sym, reason, safe_exc_text(e))
            return None, reason
        if not s:
            log.warning("polygon: no spot for %s — skipping", sym)
            return None, "no_spot"
        try:
            results = self._fetch_raw_results(sym, s, asof)
        except Exception as e:  # noqa: BLE001 — classified, not swallowed blind
            reason = _classify_exception(e)
            log.warning("polygon: %s chain failed (%s): %s", sym, reason, safe_exc_text(e))
            return None, reason
        if not results:
            log.warning("polygon: empty chain for %s", sym)
            return None, "raw_chain_empty"
        gx = self.cfg["gex"]
        ch = parse_chain(results, sym, s, asof,
                         window_pct=float(gx["strike_window_pct"]),
                         max_expiry_days=int(gx["max_expiry_days"]))
        if ch.empty:
            log.warning("polygon: parse/filter emptied chain for %s (%d raw contracts)",
                        sym, len(results))
            return None, "parse_or_filter_empty"
        log.info("polygon: %s spot=%.2f rows=%d", sym, s, len(ch))
        return ch, None

    def _run_batch(self, symbols: list[str],
                   asof: date) -> list[tuple[str, pd.DataFrame | None, str | None]]:
        """``(symbol, chain_df, reason)`` for each of `symbols`, IN INPUT ORDER —
        the ordering is load-bearing for the auth short-circuit probe in
        snapshot(), which must be able to say "the first N attempted" regardless of
        which thread happens to finish first. `ThreadPoolExecutor.map` preserves
        input order in its output even though the underlying work runs concurrently."""
        if not symbols:
            return []
        workers = max(1, int(self.cfg.get("workers", 5)))
        if workers <= 1 or len(symbols) <= 1:
            return [(sym, *self._one_chain(sym, asof)) for sym in symbols]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(workers, len(symbols))) as ex:
            outcomes = list(ex.map(lambda s: self._one_chain(s, asof), symbols))
        return [(sym, df, reason) for sym, (df, reason) in zip(symbols, outcomes)]

    def snapshot(self, symbols: list[str], asof: date) -> tuple[pd.DataFrame, dict]:
        """Spot + chain for each underlying -> (stacked per-strike frame, census).

        Partial coverage is fine — a failed symbol is logged, classified, and
        dropped from the frame; the census records every failure by REASON so an
        all-symbol failure is never reasonless again (AD-1C0).

        AUTH SHORT CIRCUIT: if the first AUTH_SHORT_CIRCUIT_PROBE attempted
        underlyings ALL classify auth_or_entitlement_failure with zero successes,
        the vendor key is almost certainly de-entitled for the whole run — abort
        the remaining universe deterministically rather than spending its full
        retry budget on a foregone conclusion. A single success, or any non-auth
        failure, among the probe disables the short circuit.

        The census dict carries ``attempted_underlyings``, ``successful_underlyings``,
        ``failure_reasons`` ({code: count}), ``failure_examples`` ({code: [<=3 syms]})
        and ``aborted_early``; scripts/build_polygon_gex.accrue() adds the
        requested-universe denominator and coverage_pct on top.
        """
        probe_n = min(AUTH_SHORT_CIRCUIT_PROBE, len(symbols))
        results = self._run_batch(symbols[:probe_n], asof)
        aborted = False
        if (probe_n == AUTH_SHORT_CIRCUIT_PROBE
                and all(reason == "auth_or_entitlement_failure" for _s, _d, reason in results)
                and not any(df is not None for _s, df, _r in results)):
            aborted = True
            log.warning(
                "polygon: first %d underlyings all auth_or_entitlement_failure — "
                "aborting the remaining %d (vendor key likely de-entitled this run)",
                probe_n, len(symbols) - probe_n)
        else:
            results = results + self._run_batch(symbols[probe_n:], asof)

        frames = [df for _s, df, _r in results if df is not None]
        raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

        failure_reasons: dict[str, int] = {}
        failure_examples: dict[str, list[str]] = {}
        for sym, df, reason in results:
            if df is None and reason:
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
                examples = failure_examples.setdefault(reason, [])
                if len(examples) < 3:
                    examples.append(sym)

        census = {
            "attempted_underlyings": len(results),
            "successful_underlyings": sum(1 for _s, df, _r in results if df is not None),
            "failure_reasons": failure_reasons,
            "failure_examples": failure_examples,
            "aborted_early": aborted,
        }
        return raw, census
