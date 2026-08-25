"""Live (intraday, ~real-time-to-15-min-delayed) last-price fetch.

The *only* job here is to return a current price per symbol with an HONEST
freshness stamp. It is deliberately thin: no indicators, no scoring — that lives
in engine.live_overlay, which splices these prices onto the nightly close series
and recomputes just the cheap "fast leaves".

Four sources, routed by symbol:
  - Polygon snapshot (US equities/ETFs) when a key is present — the entitled,
    lowest-latency feed. Plain (suffix-less, non-future, non-crypto, non-caret)
    symbols go here.
  - Tushare ``rt_k`` for mainland ``.SS`` / ``.SZ`` symbols when the existing
    ``TUSHARE_TOKEN`` is present and that account is entitled to realtime daily
    quotes. This is the preferred paid A-share snapshot because one request can
    cover the board and it carries the exchange trade clock.
  - Tencent ``qt.gtimg.cn`` is the keyless genuinely-live A-share fallback. It is
    also the live path for mainland index symbols that ``rt_k`` does not return.
    A successful Tencent batch is authoritative for whether each requested name
    has a current tradable print; a no-trade/suspension placeholder is omitted
    rather than painted as 0.00%.
  - Yahoo ``spark`` covers every other non-US market, plus US/Tencent *transport*
    fallback. Yahoo can be ~15 minutes delayed, so it is never used to overwrite
    a successful live-source no-trade/suspension answer.

Each quote carries a ``price_basis`` (trade / minute / day / prev / regular) and a
measured ``delay_min`` so a consumer can distinguish a near-current A-share print
from a delayed or prior-close snapshot.

Design for graceful degradation: each network call is isolated with light retry.
A missing/unenitled Tushare realtime permission falls through to Tencent; a Tencent
transport failure may fall through to Yahoo. A fully offline run returns ``{}``.

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
# Yahoo's spark endpoint hard-rejects (HTTP 400) a `symbols=` list longer than ~20.
_YAHOO_BATCH = 20
# Tencent is comfortable with several dozen comma-separated quote codes. Keep the
# same bound the connected Terminal quote path uses so one request hiccup is local.
_TENCENT_BATCH = 30
# Tushare rt_k can return the whole A-share market in one call, but its own docs
# recommend smaller requests for performance. 300 keeps a full Prophet board to a
# single request while a full-site snapshot stays comfortably below 50 calls/min.
_TUSHARE_RT_K_BATCH = 300
_TUSHARE_RT_K_GAP_S = 1.25  # official rt_k permission: 50 calls/minute
_TENCENT_RECORD_RE = re.compile(r'v_((?:sh|sz)\d+)="([^"]*)"', re.IGNORECASE)
_CN_TZ = ZoneInfo("Asia/Shanghai")


# --------------------------------------------------------------- routing ----

def _us_settle_window(now: datetime | None = None) -> bool:
    """True outside the US pre/RTH window (16:00 ET → next 04:00 ET + weekends).

    Post-close, Polygon's trade/minute price rungs keep updating with
    extended-hours prints — a snapshot built then stamps after-hours drift as
    the day's move (worst exactly on news days). Yahoo spark's
    regularMarketPrice pins the official settle (basis 'regular'), so US
    symbols route there instead. Premarket (04:00–09:30 ET) stays on Polygon.
    """
    from zoneinfo import ZoneInfo

    et = (now or _now()).astimezone(ZoneInfo("America/New_York"))
    if et.weekday() >= 5:
        return True
    return et.hour >= 16 or et.hour < 4


def is_us_symbol(sym: str) -> bool:
    """US equity/ETF — Polygon-routable."""
    s = str(sym).strip().upper()
    return bool(s) and not any(c in s for c in (".", "=", "-", "^"))


def is_cn_symbol(sym: str) -> bool:
    """Mainland Shanghai/Shenzhen symbol eligible for the live A-share chain."""
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


def _tushare_code(sym: str) -> str:
    s = str(sym).strip().upper()
    if s.endswith(".SS"):
        return s[:-3] + ".SH"
    if s.endswith(".SZ"):
        return s
    raise ValueError(f"not a mainland Tushare symbol: {sym}")


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


def _cn_timestamp(value: object) -> datetime | None:
    """Parse the common China market clocks used by Tushare/Tencent -> UTC."""
    raw = str(value or "").strip()
    if not raw:
        return None
    candidates = [raw]
    if len(raw) >= 14 and raw[:14].isdigit():
        candidates.insert(0, f"{raw[:4]}-{raw[4:6]}-{raw[6:8]} {raw[8:10]}:{raw[10:12]}:{raw[12:14]}")
    for candidate in candidates:
        try:
            local = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            continue
        if local.tzinfo is None:
            local = local.replace(tzinfo=_CN_TZ)
        return local.astimezone(timezone.utc)
    return None


def _no_trade_shape(*, price: float | None, prev_close: float | None,
                    open_px: float | None, high: float | None, low: float | None,
                    volume: float | None, amount: float | None,
                    chg: float | None = None) -> bool:
    """High-confidence mainland no-trade/suspension placeholder detector."""
    if price is None or prev_close is None:
        return False
    same_close = abs(price - prev_close) <= max(1e-8, abs(prev_close) * 1e-10)
    zero_change = chg is None or abs(chg) <= 1e-12
    no_volume = volume is None or volume <= 0
    no_turnover = amount is None or amount <= 0
    return (same_close and zero_change and open_px is None and high is None and low is None
            and no_volume and no_turnover)


# ----------------------------------------------------------- pure parsers ----

def parse_polygon_snapshot(payload: dict, now: datetime | None = None) -> dict:
    """Polygon snapshot -> {symbol: quote}, preserving the real market clock."""
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
        if lt.get("p"):
            price, basis = lt["p"], "trade"
            ts = datetime.fromtimestamp(lt["t"] / 1e9, tz=timezone.utc) if lt.get("t") else None
        elif mn.get("c"):
            price, basis = mn["c"], "minute"
            ts = datetime.fromtimestamp(mn["t"] / 1e3, tz=timezone.utc) if mn.get("t") else None
        elif day.get("c"):
            price, basis = day["c"], "day"
        elif prev.get("c"):
            price, basis = prev["c"], "prev"
        if not price:
            continue
        if ts is None:
            synthetic = True
            ts = (datetime.fromtimestamp(row["updated"] / 1e9, tz=timezone.utc)
                  if row.get("updated") else now)
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
    """Yahoo ``spark`` -> {symbol: quote}. Its market time is retained exactly."""
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


def _table_records(table: object) -> list[dict]:
    if table is None:
        return []
    if isinstance(table, list):
        return [row for row in table if isinstance(row, dict)]
    to_dict = getattr(table, "to_dict", None)
    if callable(to_dict):
        try:
            rows = to_dict("records")
        except Exception:  # noqa: BLE001 — parser boundary, degrade to fallback
            return []
        return [row for row in rows if isinstance(row, dict)]
    return []


def parse_tushare_rt_k(table: object, now: datetime | None = None) -> dict:
    """Tushare ``rt_k`` table -> current A-share quotes.

    ``rt_k.close`` is the latest price (not the completed-session close). A row is
    accepted as live only when ``trade_time`` is present and parseable; a vendor
    refresh clock synthesized by us can never earn live authority.
    """
    now = now or _now()
    out: dict[str, dict] = {}
    for row in _table_records(table):
        sym = str(row.get("ts_code") or "").strip().upper()
        if sym.endswith(".SH"):
            sym = sym[:-3] + ".SS"
        if not is_cn_symbol(sym):
            continue
        price = _pos(row.get("close"))
        prev_close = _pos(row.get("pre_close"))
        ts = _cn_timestamp(row.get("trade_time"))
        if price is None or ts is None:
            continue
        open_px = _pos(row.get("open"))
        high = _pos(row.get("high"))
        low = _pos(row.get("low"))
        volume = _num(row.get("vol"))
        amount = _num(row.get("amount"))
        chg = ((price / prev_close - 1.0) * 100.0) if prev_close else None
        if _no_trade_shape(price=price, prev_close=prev_close, open_px=open_px,
                           high=high, low=low, volume=volume, amount=amount, chg=chg):
            continue
        out[sym] = {
            "price": round(price, 4),
            "quote_ts": ts.isoformat(),
            "quote_ts_synthetic": False,
            "source": "tushare-rt-k",
            "price_basis": "trade",
            "delay_min": _delay_min(ts, now),
            "prev_close": round(prev_close, 4) if prev_close is not None else None,
            "currency": "CNY",
            "day_volume": int(volume) if volume is not None else None,
            "day_high": round(high, 4) if high is not None else None,
            "day_low": round(low, 4) if low is not None else None,
        }
    return out


def parse_tencent_quotes(text: str, now: datetime | None = None) -> dict:
    """Tencent ``qt.gtimg.cn`` text -> current mainland quote records."""
    now = now or _now()
    out: dict[str, dict] = {}
    for match in _TENCENT_RECORD_RE.finditer(text or ""):
        sym = _tencent_symbol(match.group(1))
        fields = match.group(2).split("~")
        if sym is None or len(fields) < 35:
            continue
        price = _pos(fields[3] if len(fields) > 3 else None)
        prev_close = _pos(fields[4] if len(fields) > 4 else None)
        ts = _cn_timestamp(fields[30] if len(fields) > 30 else None)
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
        volume_shares = vol_lots * 100 if vol_lots is not None else None
        if _no_trade_shape(price=price, prev_close=prev_close, open_px=open_px,
                           high=high, low=low, volume=volume_shares, amount=amount, chg=chg):
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
            "day_volume": int(volume_shares) if volume_shares is not None else None,
            "day_high": round(high, 4) if high is not None else None,
            "day_low": round(low, 4) if low is not None else None,
        }
    return out


# ------------------------------------------------------------- fetchers ----

def _http_json(url: str, params: dict, timeout: int = 12,
               retries: int = 2, backoff: float = 1.5) -> dict | None:
    """GET + parse JSON with light retry/backoff on 429/5xx/timeout."""
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
    """Return ({symbol: quote}, status), surfacing Polygon auth/transport state."""
    out: dict[str, dict] = {}
    status = "no_response"
    base = config.load()["polygon"]["base_url"].rstrip("/")
    for batch in _chunks(symbols, 100):
        j = _http_json(base + _POLY_SNAPSHOT, {"tickers": ",".join(batch), "apiKey": key})
        if j is None:
            continue
        s = str(j.get("status", "")).upper()
        if s in ("NOT_AUTHORIZED",):
            log.error("polygon snapshot NOT_AUTHORIZED")
            status = "not_authorized"
        elif s in ("ERROR",):
            log.error("polygon snapshot ERROR")
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


def _load_tushare_client():
    """Lazy import: the existing canonical Tushare client owns token/auth handling."""
    try:
        from collectors import tushare_client
        return tushare_client
    except Exception:  # noqa: BLE001 — optional live source, Tencent remains available
        return None


def fetch_tushare_cn(symbols: list[str]) -> tuple[dict, list[str], str]:
    """Preferred paid mainland snapshot; every miss falls through to Tencent.

    Tushare realtime is a separately entitled product. We never infer entitlement
    from the presence of the ordinary Tushare token: ``query('rt_k')`` must succeed
    with a real ``trade_time``. A disabled, denied, malformed or partial response
    therefore degrades to the keyless Tencent live leg without changing the public
    quote contract.
    """
    requested = [str(s).strip().upper() for s in symbols]
    client = _load_tushare_client()
    if client is None or not client.enabled():
        return {}, requested, "disabled"

    out: dict[str, dict] = {}
    successful_batches = 0
    failed_batches = 0
    batches = list(_chunks(requested, _TUSHARE_RT_K_BATCH))
    fields = "ts_code,pre_close,open,high,low,close,vol,amount,num,trade_time"
    for idx, batch in enumerate(batches):
        if idx:
            time.sleep(_TUSHARE_RT_K_GAP_S)
        codes = ",".join(_tushare_code(s) for s in batch)
        frame = client.query("rt_k", fields=fields, ts_code=codes, _return_empty=True)
        if frame is None:
            failed_batches += 1
            continue
        successful_batches += 1
        parsed = parse_tushare_rt_k(frame)
        for sym in batch:
            if sym in parsed:
                out[sym] = parsed[sym]

    missing = [s for s in requested if s not in out]
    if successful_batches == 0:
        status = "unavailable" if failed_batches else "empty"
    elif failed_batches:
        status = "partial"
    else:
        status = "ok"
    return out, missing, status


def fetch_tencent_cn(symbols: list[str]) -> tuple[dict, list[str], str]:
    """Return (current_quotes, yahoo_transport_fallback_symbols, status).

    A successful Tencent envelope is authoritative even when one requested symbol
    has no current trade (e.g. suspended/no-trade placeholder filtered by parser).
    Yahoo fallback is used only for an entire batch whose Tencent transport/envelope
    failed, never to turn an explicit no-trade state back into delayed pseudo-live.
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

    US: Polygon when entitled, Yahoo fallback.
    Mainland: Tushare rt_k when actually entitled -> Tencent live fallback -> Yahoo
    only on Tencent transport failure.
    Other international: Yahoo spark.
    """
    if offline or not symbols:
        if diag is not None:
            state = "offline" if offline else "unused"
            diag["polygon_status"] = state
            diag["tushare_status"] = state
            diag["tencent_status"] = state
        return {}
    cfg = config.load().get("live") or {}
    us_source = us_source or cfg.get("us_source", "polygon")
    key = config.secret("POLYGON_API_KEY") or config.secret("MASSIVE_API_KEY")

    us = [s for s in symbols if is_us_symbol(s)]
    cn = [str(s).strip().upper() for s in symbols if is_cn_symbol(s)]
    intl = [s for s in symbols if not is_us_symbol(s) and not is_cn_symbol(s)]
    out: dict[str, dict] = {}
    poly_status = "unused"
    tushare_status = "unused"
    tencent_status = "unused"

    if us:
        if us_source == "polygon" and key and not _us_settle_window():
            poly_out, poly_status = fetch_polygon(us, key)
            out.update(poly_out)
        missing = [s for s in us if s not in out]
        if missing:
            out.update(fetch_yahoo(missing))

    if cn:
        ts_out, cn_for_tencent, tushare_status = fetch_tushare_cn(cn)
        out.update(ts_out)
        if cn_for_tencent:
            tx_out, yahoo_fallback, tencent_status = fetch_tencent_cn(cn_for_tencent)
            out.update(tx_out)
            if yahoo_fallback:
                out.update(fetch_yahoo(yahoo_fallback))

    if intl:
        out.update(fetch_yahoo(intl))

    if diag is not None:
        diag["polygon_status"] = poly_status
        diag["tushare_status"] = tushare_status
        diag["tencent_status"] = tencent_status
    return out
