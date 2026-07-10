"""Live (intraday, ~real-time-to-15-min-delayed) last-price fetch.

The *only* job here is to return a current price per symbol with an HONEST
freshness stamp. It is deliberately thin: no indicators, no scoring — that lives
in engine.live_overlay, which splices these prices onto the nightly close series
and recomputes just the cheap "fast leaves".

Two sources, routed by symbol:
  - Polygon snapshot (US equities/ETFs) when a key is present — the entitled,
    lowest-latency feed. Plain (suffix-less, non-future, non-crypto, non-caret)
    symbols go here.
  - Yahoo `spark` (keyless, universal) for everything else — suffixed symbols
    (``.SS`` / ``.SZ`` / ``.HK`` / ``.TO`` …), Yahoo futures (``GC=F``), crypto
    (``BTC-USD``), caret indices (``^VIX``) — and as the US fallback with no key.

Each quote carries a ``price_basis`` (trade / minute / day / prev / regular) so a
consumer can tell a real live trade from a prior close that merely got a fresh
snapshot-refresh timestamp — the latter must NOT be treated as live.

Design for graceful degradation: the network call is one isolated function with
light retry, and response parsing is pure (both unit-testable without a socket).
Any failure -> that symbol is absent; a fully offline run returns ``{}`` and the
caller marks everything stale.

DISPLAY / FEED ONLY — never a scored input on its own.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import requests

from lib import config

log = logging.getLogger("live_quotes")

_YAHOO_SPARK = "https://query1.finance.yahoo.com/v7/finance/spark"
_POLY_SNAPSHOT = "/v2/snapshot/locale/us/markets/stocks/tickers"
_UA = "Mozilla/5.0 (macro-dashboard live_quotes)"
# Yahoo's spark endpoint hard-rejects (HTTP 400) a `symbols=` list longer than ~20
# — empirically 20 OK, 21 fails. The old batch of 50 silently dropped every intl/
# equity quote (a board like china_stocks has 100+ symbols), so the live overlay
# looked dead off-US. Keep a safe margin below the cliff.
_YAHOO_BATCH = 20


# --------------------------------------------------------------- routing ----

def _us_settle_window(now: datetime | None = None) -> bool:
    """True outside the US pre/RTH window (16:00 ET → next 04:00 ET + weekends).

    Post-close, Polygon's trade/minute price rungs keep updating with
    extended-hours prints — a snapshot built then stamps after-hours drift as
    the day's move (worst exactly on news days). Yahoo spark's
    regularMarketPrice pins the official settle (basis 'regular'), so US
    symbols route there instead. Premarket (04:00–09:30 ET) stays on Polygon:
    the premarket tape is a designed feature (FTR W2c).
    """
    from zoneinfo import ZoneInfo

    et = (now or _now()).astimezone(ZoneInfo("America/New_York"))
    if et.weekday() >= 5:
        return True
    return et.hour >= 16 or et.hour < 4


def is_us_symbol(sym: str) -> bool:
    """US equity/ETF — Polygon-routable. Anything with a market suffix (``.``), a
    Yahoo future (``=``), a crypto pair (``-``) or a caret index (``^``) is not
    (indices/futures/crypto are not entitled on the stocks plan -> Yahoo)."""
    s = str(sym).strip().upper()
    return bool(s) and not any(c in s for c in (".", "=", "-", "^"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _delay_min(ts: datetime, now: datetime | None = None) -> float:
    now = now or _now()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return round(max(0.0, (now - ts).total_seconds() / 60.0), 1)


# ----------------------------------------------------------- pure parsers ----

def parse_polygon_snapshot(payload: dict, now: datetime | None = None) -> dict:
    """Polygon ``/v2/snapshot/.../tickers`` -> {symbol: quote}. Price preference:
    last trade -> last minute close -> day close -> prev-day close, recording
    which rung won as ``price_basis``. CRITICAL: the staleness timestamp is taken
    from the *trade/minute* time, NOT ``updated`` (which refreshes even with no
    trade — on a delayed plan or an illiquid name that would falsely look fresh).
    A day/prev-close basis is stamped not-live so the consumer falls back."""
    now = now or _now()
    out: dict[str, dict] = {}
    for row in (payload or {}).get("tickers", []) or []:
        sym = row.get("ticker")
        if not sym:
            continue
        lt, mn = row.get("lastTrade") or {}, row.get("min") or {}
        day, prev = row.get("day") or {}, row.get("prevDay") or {}
        price = basis = ts = None
        if lt.get("p"):                                   # real trade
            price, basis = lt["p"], "trade"
            ts = datetime.fromtimestamp(lt["t"] / 1e9, tz=timezone.utc) if lt.get("t") else None
        elif mn.get("c"):                                 # current minute bar
            price, basis = mn["c"], "minute"
            ts = datetime.fromtimestamp(mn["t"] / 1e3, tz=timezone.utc) if mn.get("t") else None
        elif day.get("c"):                                # today's session close
            price, basis = day["c"], "day"
        elif prev.get("c"):                               # prior session close
            price, basis = prev["c"], "prev"
        if not price:
            continue
        if ts is None:                                    # day/prev (or trade w/o t)
            ts = (datetime.fromtimestamp(row["updated"] / 1e9, tz=timezone.utc)
                  if row.get("updated") else now)
        out[sym] = {
            "price": round(float(price), 4), "quote_ts": ts.isoformat(),
            "source": "polygon", "price_basis": basis, "delay_min": _delay_min(ts, now),
            "prev_close": round(float(prev["c"]), 4) if prev.get("c") else None,
            "currency": "USD",
        }
    return out


def parse_yahoo_spark(payload: dict, now: datetime | None = None) -> dict:
    """Yahoo ``spark`` -> {symbol: quote}. ``regularMarketTime`` is epoch seconds
    (the last regular-session print) -> basis 'regular'."""
    now = now or _now()
    out: dict[str, dict] = {}
    for res in (payload or {}).get("spark", {}).get("result", []) or []:
        sym = res.get("symbol")
        meta = ((res.get("response") or [{}])[0] or {}).get("meta") or {}
        price = meta.get("regularMarketPrice")
        if not sym or price is None:
            continue
        ts_s = meta.get("regularMarketTime")
        ts = datetime.fromtimestamp(ts_s, tz=timezone.utc) if ts_s else now
        out[sym] = {
            "price": round(float(price), 4), "quote_ts": ts.isoformat(),
            "source": "yahoo", "price_basis": "regular", "delay_min": _delay_min(ts, now),
            "prev_close": (round(float(meta["previousClose"]), 4)
                           if meta.get("previousClose") is not None else None),
            "currency": meta.get("currency"),
        }
    return out


# ------------------------------------------------------------- fetchers ----

def _http_json(url: str, params: dict, timeout: int = 12,
               retries: int = 2, backoff: float = 1.5) -> dict | None:
    """GET + parse JSON with light retry/backoff on 429/5xx/timeout (Yahoo spark
    and Cboe-style sources hard-limit). Returns None after exhausting retries."""
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout,
                             headers={"User-Agent": _UA})
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            log.warning("live_quotes GET %s -> HTTP %s", url, r.status_code)
            return None
        except Exception as e:  # noqa: BLE001 — degrade, never abort the overlay
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            log.warning("live_quotes GET %s failed: %s", url, e)
            return None
    return None


def _chunks(xs: list, n: int):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def fetch_polygon(symbols: list[str], key: str) -> tuple[dict, str]:
    """Returns ({symbol: quote}, status) where status surfaces entitlement/auth
    problems ('ok' | 'not_authorized' | 'error' | 'no_response') so a silent Yahoo
    fallback doesn't hide an expired/unentitled key."""
    out: dict[str, dict] = {}
    status = "no_response"
    base = config.load()["polygon"]["base_url"].rstrip("/")
    for batch in _chunks(symbols, 100):
        j = _http_json(base + _POLY_SNAPSHOT, {"tickers": ",".join(batch), "apiKey": key})
        if j is None:
            continue
        s = str(j.get("status", "")).upper()
        if s in ("NOT_AUTHORIZED",):
            log.error("polygon snapshot NOT_AUTHORIZED — key wrong/unentitled: %s", j.get("message"))
            status = "not_authorized"
        elif s in ("ERROR",):
            log.error("polygon snapshot ERROR: %s", j.get("message"))
            status = "error" if status == "no_response" else status
        else:
            status = "ok"
        out.update(parse_polygon_snapshot(j))
    return out, status


def fetch_yahoo(symbols: list[str]) -> dict:
    out: dict[str, dict] = {}
    for batch in _chunks(symbols, _YAHOO_BATCH):
        j = _http_json(_YAHOO_SPARK,
                       {"symbols": ",".join(batch), "range": "1d", "interval": "5m"})
        if j:
            out.update(parse_yahoo_spark(j))
    return out


def fetch_quotes(symbols: list[str], *, us_source: str | None = None,
                 offline: bool = False, diag: dict | None = None) -> dict:
    """Return {symbol: quote} for as many symbols as resolve. US symbols go to
    Polygon when a key + ``us_source=='polygon'`` (default from config); the rest
    (and the US fallback) go to Yahoo spark. ``offline=True`` short-circuits to
    ``{}``. If ``diag`` is provided it is filled with feed diagnostics
    (e.g. ``polygon_status``) for the overlay's ``sources`` block."""
    if offline or not symbols:
        if diag is not None:
            diag["polygon_status"] = "offline" if offline else "unused"
        return {}
    cfg = config.load().get("live") or {}
    us_source = us_source or cfg.get("us_source", "polygon")
    key = config.secret("POLYGON_API_KEY") or config.secret("MASSIVE_API_KEY")

    us = [s for s in symbols if is_us_symbol(s)]
    intl = [s for s in symbols if not is_us_symbol(s)]
    out: dict[str, dict] = {}
    poly_status = "unused"

    if us:
        if us_source == "polygon" and key and not _us_settle_window():
            # Settle-clean routing (TS-U5): post-close the trade/minute rungs
            # carry extended-hours prints; Yahoo 'regular' pins the settle.
            poly_out, poly_status = fetch_polygon(us, key)
            out.update(poly_out)
        missing = [s for s in us if s not in out]   # Yahoo fallback for any gap / no key
        if missing:
            out.update(fetch_yahoo(missing))
    if intl:
        out.update(fetch_yahoo(intl))
    if diag is not None:
        diag["polygon_status"] = poly_status
    return out
