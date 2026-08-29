"""Live (intraday, ~real-time-to-15-min-delayed) last-price fetch.

The *only* job here is to return a current price per symbol with an HONEST
freshness stamp. It is deliberately thin: no indicators, no scoring — that lives
in engine.live_overlay, which splices these prices onto the nightly close series
and recomputes just the cheap "fast leaves".

Three sources, routed by symbol:
  - Polygon snapshot (US equities/ETFs) when a key is present — the entitled,
    lowest-latency feed. Plain (suffix-less, non-future, non-crypto, non-caret)
    symbols go here.
  - Tencent ``qt.gtimg.cn`` for mainland ``.SS`` / ``.SZ`` symbols — the existing
    product's genuinely live A-share snapshot source. A successful Tencent batch
    is authoritative for whether each requested name has a current tradable print;
    a no-trade/suspension placeholder is omitted rather than painted as 0.00%.
  - Yahoo ``spark`` for every other non-US market, plus US/Tencent transport
    fallback. Yahoo can be ~15 minutes delayed, so it is availability fallback for
    China only when the Tencent REQUEST failed, never when Tencent positively
    answered a name with no current trade.

Each quote carries a ``price_basis`` (trade / minute / day / prev / regular) so a
consumer can tell a real live trade from a prior close that merely got a fresh
snapshot-refresh timestamp — the latter must NOT be treated as live.

Design for graceful degradation: each network call is isolated with light retry.
Any failure -> that symbol is absent or uses the declared delayed fallback; a fully
offline run returns ``{}`` and the caller marks everything stale.

DISPLAY / FEED ONLY — never a scored input on its own.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

from lib import config

log = logging.getLogger("live_quotes")

_YAHOO_SPARK = "https://query1.finance.yahoo.com/v7/finance/spark"
_TENCENT_QUOTES = "https://qt.gtimg.cn/q="
_POLY_SNAPSHOT = "/v2/snapshot/locale/us/markets/stocks/tickers"
_UA = "Mozilla/5.0 (macro-dashboard live_quotes)"
# Yahoo's spark endpoint hard-rejects (HTTP 400) a `symbols=` list longer than ~20
# — empirically 20 OK, 21 fails. The old batch of 50 silently dropped every intl/
# equity quote (a board like china_stocks has 100+ symbols), so the live overlay
# looked dead off-US. Keep a safe margin below the cliff.
_YAHOO_BATCH = 20
# Tencent is comfortable with several dozen comma-separated quote codes. Keep the
# same 30-name bound the Terminal quote path uses so one provider hiccup has a
# bounded blast radius and the China Prophet board still resolves in a few calls.
_TENCENT_BATCH = 30
_TENCENT_RECORD_RE = re.compile(r'v_((?:sh|sz)\d+)="([^"]*)"', re.IGNORECASE)
_CN_TZ = ZoneInfo("Asia/Shanghai")


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
    (indices/futures/crypto are not entitled on the stocks plan)."""
    s = str(sym).strip().upper()
    return bool(s) and not any(c in s for c in (".", "=", "-", "^"))


def is_cn_symbol(sym: str) -> bool:
    """Mainland Shanghai/Shenzhen symbol supported by Tencent's live quote feed."""
    s = str(sym).strip().upper()
    return s.endswith(".SS") or s.endswith(".SZ")


def _tencent_code(sym: str) -> str:
    s = str(sym).strip().upper()
    if s.endswith(".SS"):
        return "sh" + s[:-3]
    if s.endswith(".SZ"):
        return "sz" + s[:-3]
    raise ValueError(f"not a mainland Tencent symbol: {sym}")


def _tencent_symbol(code: str) -> str | None:
    c = str(code).strip().lower()
    if c.startswith("sh") and c[2:].isdigit():
        return c[2:] + ".SS"
    if c.startswith("sz") and c[2:].isdigit():
        return c[2:] + ".SZ"
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _delay_min(ts: datetime, now: datetime | None = None) -> float:
    now = now or _now()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return round(max(0.0, (now - ts).total_seconds() / 60.0), 1)


def _num(value: object) -> float | None:
    try:
        out = float(value)
        return out if out == out else None
    except (TypeError, ValueError):
        return None


def _pos(value: object) -> float | None:
    out = _num(value)
    return out if out is not None and out > 0 else None


def _tencent_timestamp(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if len(raw) < 14 or not raw[:14].isdigit():
        return None
    try:
        local = datetime.strptime(raw[:14], "%Y%m%d%H%M%S").replace(tzinfo=_CN_TZ)
    except ValueError:
        return None
    return local.astimezone(timezone.utc)


# ----------------------------------------------------------- pure parsers ----

def parse_polygon_snapshot(payload: dict, now: datetime | None = None) -> dict:
    """Polygon ``/v2/snapshot/.../tickers`` -> {symbol: quote}. Price preference:
    last trade -> last minute close -> day close -> prev-day close, recording
    which rung won as ``price_basis``. CRITICAL: the staleness timestamp is taken
    from the *trade/minute* time, NOT ``updated`` (which refreshes even with no
    trade — on a delayed plan or an illiquid name that would falsely look fresh).
    A day/prev-close basis is stamped not-live so the consumer falls back.

    ``quote_ts_synthetic`` (GD-3R1 amendment F3, additive): True exactly when the
    emitted ``quote_ts`` is NOT a real market timestamp (a trade/minute print) —
    i.e. it fell back to the snapshot's ``updated`` refresh clock or, lacking even
    that, this process's own wall clock. A consumer building an event-time receipt
    (scripts/build_risk_state.py) must never treat a synthetic clock as the real
    source-market instant (Sol's cannot-be-established -> null law). No pricing/
    staleness behavior changes — `delay_min`/`price_basis` are unaffected."""
    now = now or _now()
    out: dict[str, dict] = {}
    for row in (payload or {}).get("tickers", []) or []:
        sym = row.get("ticker")
        if not sym:
            continue
        lt, mn = row.get("lastTrade") or {}, row.get("min") or {}
        day, prev = row.get("day") or {}, row.get("prevDay") or {}
        price = basis = ts = None
        synthetic = False
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
            # GD-3R1 F3: no real market timestamp exists for this print — the
            # snapshot's `updated` refresh clock (or, lacking even that, `now`)
            # is a SYNTHETIC clock, never eligible as a source event clock.
            synthetic = True
            ts = (datetime.fromtimestamp(row["updated"] / 1e9, tz=timezone.utc)
                  if row.get("updated") else now)
        # Day volume, high, low from the day bucket (zero-extra-request: already fetched).
        day_vol = day.get("v")
        day_hi = day.get("h")
        day_lo = day.get("l")
        out[sym] = {
            "price": round(float(price), 4), "quote_ts": ts.isoformat(),
            "quote_ts_synthetic": synthetic,
            "source": "polygon", "price_basis": basis, "delay_min": _delay_min(ts, now),
            "prev_close": round(float(prev["c"]), 4) if prev.get("c") else None,
            "currency": "USD",
            "day_volume": int(day_vol) if day_vol is not None else None,
            "day_high": round(float(day_hi), 4) if day_hi is not None else None,
            "day_low": round(float(day_lo), 4) if day_lo is not None else None,
        }
    return out


def parse_yahoo_spark(payload: dict, now: datetime | None = None) -> dict:
    """Yahoo ``spark`` -> {symbol: quote}. ``regularMarketTime`` is epoch seconds
    (the last regular-session print) -> basis 'regular'.

    ``quote_ts_synthetic`` (GD-3R1 amendment F3, additive): True when Yahoo's own
    meta carries no ``regularMarketTime`` and ``quote_ts`` fell back to this
    process's wall clock — see ``parse_polygon_snapshot``'s docstring for the
    same law. No pricing/staleness behavior changes."""
    now = now or _now()
    out: dict[str, dict] = {}
    for res in (payload or {}).get("spark", {}).get("result", []) or []:
        sym = res.get("symbol")
        meta = ((res.get("response") or [{}])[0] or {}).get("meta") or {}
        price = meta.get("regularMarketPrice")
        if not sym or price is None:
            continue
        ts_s = meta.get("regularMarketTime")
        synthetic = not bool(ts_s)
        ts = datetime.fromtimestamp(ts_s, tz=timezone.utc) if ts_s else now
        # Volume, high, low from same meta object — zero extra requests.
        day_vol = meta.get("regularMarketVolume")
        day_hi = meta.get("regularMarketDayHigh")
        day_lo = meta.get("regularMarketDayLow")
        out[sym] = {
            "price": round(float(price), 4), "quote_ts": ts.isoformat(),
            "quote_ts_synthetic": synthetic,
            "source": "yahoo", "price_basis": "regular", "delay_min": _delay_min(ts, now),
            "prev_close": (round(float(meta["previousClose"]), 4)
                           if meta.get("previousClose") is not None else None),
            "currency": meta.get("currency"),
            "day_volume": int(day_vol) if day_vol is not None else None,
            "day_high": round(float(day_hi), 4) if day_hi is not None else None,
            "day_low": round(float(day_lo), 4) if day_lo is not None else None,
        }
    return out


def parse_tencent_quotes(text: str, now: datetime | None = None) -> dict:
    """Tencent ``qt.gtimg.cn`` text -> current mainland quote records.

    Field offsets mirror the existing Terminal adapter: 3 last, 4 previous close,
    5 open, 6 cumulative volume in lots, 30 exchange timestamp, 32 change %, 33
    high, 34 low, 37 turnover. The timestamp is a real Asia/Shanghai market clock.

    A suspended/no-trade name can still come back as a syntactically valid record:
    last == prevClose, change == 0, O/H/L == 0, volume == 0, turnover == 0. That
    shape is deliberately omitted. It proves no current tradable print; it must not
    overwrite the last real session with a fake 0.00% move or a fake candle.
    """
    now = now or _now()
    out: dict[str, dict] = {}
    for match in _TENCENT_RECORD_RE.finditer(text or ""):
        sym = _tencent_symbol(match.group(1))
        fields = match.group(2).split("~")
        if sym is None or len(fields) < 35:
            continue
        price = _pos(fields[3] if len(fields) > 3 else None)
        prev_close = _pos(fields[4] if len(fields) > 4 else None)
        ts = _tencent_timestamp(fields[30] if len(fields) > 30 else None)
        if price is None or ts is None:
            continue

        open_px = _pos(fields[5] if len(fields) > 5 else None)
        vol_lots = _num(fields[6] if len(fields) > 6 else None)
        chg = _num(fields[32] if len(fields) > 32 else None)
        high = _pos(fields[33] if len(fields) > 33 else None)
        low = _pos(fields[34] if len(fields) > 34 else None)
        amount = _num(fields[37] if len(fields) > 37 else None)
        if chg is None and prev_close:
            chg = (price / prev_close - 1.0) * 100.0

        same_close = (
            prev_close is not None
            and abs(price - prev_close) <= max(1e-8, abs(prev_close) * 1e-10)
        )
        zero_change = chg is not None and abs(chg) <= 1e-12
        no_volume = vol_lots is None or vol_lots <= 0
        no_turnover = amount is None or amount <= 0
        if same_close and zero_change and open_px is None and high is None and low is None \
                and no_volume and no_turnover:
            continue

        out[sym] = {
            "price": round(price, 4),
            "quote_ts": ts.isoformat(),
            "quote_ts_synthetic": False,
            "source": "tencent",
            "price_basis": "trade",
            "delay_min": _delay_min(ts, now),
            "prev_close": round(prev_close, 4) if prev_close is not None else None,
            "currency": "CNY",
            "day_volume": int(vol_lots * 100) if vol_lots is not None else None,
            "day_high": round(high, 4) if high is not None else None,
            "day_low": round(low, 4) if low is not None else None,
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


def _http_text(url: str, timeout: int = 12,
               retries: int = 2, backoff: float = 1.5) -> str | None:
    """GET Tencent's GBK-ish JavaScript envelope; numeric fields are ASCII."""
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, timeout=timeout, headers={"User-Agent": _UA})
            if r.status_code == 200:
                return r.content.decode("latin1", errors="ignore")
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


def fetch_tencent_cn(symbols: list[str]) -> tuple[dict, list[str], str]:
    """Return (current_quotes, transport_fallback_symbols, status) for mainland names.

    A successful response is authoritative even when one requested symbol produces
    no current quote (for example a suspended/no-trade placeholder filtered by the
    parser). Yahoo fallback is therefore used only for batches whose Tencent
    transport/envelope failed, never to turn an explicit no-trade state back into
    a delayed pseudo-live quote.
    """
    out: dict[str, dict] = {}
    fallback: list[str] = []
    responded_batches = 0
    failed_batches = 0
    for batch in _chunks(symbols, _TENCENT_BATCH):
        codes = [_tencent_code(s) for s in batch]
        text = _http_text(_TENCENT_QUOTES + ",".join(codes))
        if text is None or not _TENCENT_RECORD_RE.search(text):
            fallback.extend(batch)
            failed_batches += 1
            continue
        responded_batches += 1
        parsed = parse_tencent_quotes(text)
        for sym in batch:
            key = str(sym).strip().upper()
            if key in parsed:
                out[key] = parsed[key]
    if responded_batches == 0:
        status = "no_response"
    elif failed_batches:
        status = "partial"
    else:
        status = "ok"
    return out, fallback, status


def fetch_quotes(symbols: list[str], *, us_source: str | None = None,
                 offline: bool = False, diag: dict | None = None) -> dict:
    """Return {symbol: quote} for as many symbols as resolve.

    US equities prefer Polygon when entitled; mainland .SS/.SZ symbols prefer the
    genuinely live Tencent snapshot; all other international instruments use Yahoo
    spark. Yahoo is a China fallback only for a failed Tencent transport batch.
    ``offline=True`` short-circuits to ``{}``. ``diag`` exposes both provider states.
    """
    if offline or not symbols:
        if diag is not None:
            state = "offline" if offline else "unused"
            diag["polygon_status"] = state
            diag["tencent_status"] = state
        return {}
    cfg = config.load().get("live") or {}
    us_source = us_source or cfg.get("us_source", "polygon")
    key = config.secret("POLYGON_API_KEY") or config.secret("MASSIVE_API_KEY")

    us = [s for s in symbols if is_us_symbol(s)]
    cn = [s for s in symbols if is_cn_symbol(s)]
    intl = [s for s in symbols if not is_us_symbol(s) and not is_cn_symbol(s)]
    out: dict[str, dict] = {}
    poly_status = "unused"
    tencent_status = "unused"

    if us:
        if us_source == "polygon" and key and not _us_settle_window():
            # Settle-clean routing (TS-U5): post-close the trade/minute rungs
            # carry extended-hours prints; Yahoo 'regular' pins the settle.
            poly_out, poly_status = fetch_polygon(us, key)
            out.update(poly_out)
        missing = [s for s in us if s not in out]   # Yahoo fallback for any gap / no key
        if missing:
            out.update(fetch_yahoo(missing))
    if cn:
        cn_out, cn_fallback, tencent_status = fetch_tencent_cn(cn)
        out.update(cn_out)
        if cn_fallback:
            out.update(fetch_yahoo(cn_fallback))
    if intl:
        out.update(fetch_yahoo(intl))
    if diag is not None:
        diag["polygon_status"] = poly_status
        diag["tencent_status"] = tencent_status
    return out
