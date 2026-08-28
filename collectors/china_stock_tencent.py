"""Tencent repair lane for the canonical adjusted China per-name OHLC store.

Yahoo remains the primary/deep-history source owned by ``china_stocks``.  This module
exists for one narrow failure mode: yfinance bulk downloads can omit a ticker/chunk or
return a ticker whose last trading date is several sessions behind the rest of the A
share market while the overall collector still succeeds.

Tencent is already a verified/keyless China market source in the repository source
catalog.  It is used here only as a recent-tail repair source.  A Tencent tail may extend
an existing Yahoo/store series only when overlapping closes are on the same adjustment
basis.  It never creates a second store and never fabricates sessions for suspended
names: if Tencent has no newer traded date, the frame is left unchanged.

Tencent's daily ``amount``/sixth kline field is volume in Chinese board lots (手), while
Yahoo and the canonical Macro stock stores use shares.  The parser normalizes lots x100
before a repaired row can enter the store.  The endpoint can also expose the current
session before it is final; repairs are capped at the last completed Shanghai session
(16:05 local safety boundary) so an intraday partial candle cannot become daily truth.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo

import pandas as pd

from collectors._stock_ohlc import _drop_invalid_ohlc, _drop_non_trading_placeholders
from lib import store

log = logging.getLogger(__name__)

_TENCENT_URLS = (
    "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
)
_PROBE_PREFERENCE = ("600519.SS", "000001.SZ", "600036.SS", "000858.SZ")
_DEFAULT_COUNT = 90
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_FINALIZATION_TIME = dt.time(16, 5)


def tencent_code(ticker: str) -> str | None:
    """Yahoo-style A-share ticker -> Tencent market code."""
    if ticker.endswith(".SS"):
        code = ticker[:-3]
        return f"sh{code}" if code.isdigit() else None
    if ticker.endswith(".SZ"):
        code = ticker[:-3]
        return f"sz{code}" if code.isdigit() else None
    return None


def frame_from_payload(ticker: str, payload: dict) -> pd.DataFrame | None:
    """Parse Tencent qfq daily rows into the canonical stock-OHLC frame schema."""
    code = tencent_code(ticker)
    if not code:
        return None
    node = (payload.get("data") or {}).get(code) or {}
    raw = node.get("qfqday") or node.get("day") or []
    rows: list[tuple[object, float, float, float, float, float]] = []
    for x in raw:
        if not isinstance(x, list) or len(x) < 6:
            continue
        trade_dt = pd.to_datetime(x[0], errors="coerce")
        if pd.isna(trade_dt):
            continue
        try:
            # Tencent row order: date, open, close, high, low, volume-in-lots (手).
            # Canonical Macro/Yahoo volume is shares; one A-share board lot = 100 shares.
            rows.append(
                (trade_dt, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5]) * 100.0)
            )
        except (TypeError, ValueError):
            continue
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["Date", "open", "close", "high", "low", "volume"])
    df = df.set_index("Date").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df = _drop_non_trading_placeholders(df)
    df = _drop_invalid_ohlc(df)
    return df.astype("float64") if not df.empty else None


def completed_session_cutoff(now: dt.datetime | None = None) -> pd.Timestamp:
    """Latest calendar date a Tencent daily row is allowed to represent.

    Before 16:05 Asia/Shanghai, today's daily bar is considered provisional and is
    excluded.  On weekends/holidays this is harmless: the provider has no row for the
    non-trading date, so the latest real session naturally remains earlier.
    """
    local = now or dt.datetime.now(_SHANGHAI)
    if local.tzinfo is None:
        local = local.replace(tzinfo=_SHANGHAI)
    else:
        local = local.astimezone(_SHANGHAI)
    day = local.date()
    if local.timetz().replace(tzinfo=None) < _FINALIZATION_TIME:
        day -= dt.timedelta(days=1)
    return pd.Timestamp(day)


def keep_completed_sessions(df: pd.DataFrame, now: dt.datetime | None = None) -> pd.DataFrame:
    """Drop a current/provisional Shanghai daily row from a Tencent frame."""
    cutoff = completed_session_cutoff(now)
    idx = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df.loc[idx <= cutoff]


def fetch_tencent(ticker: str, count: int = _DEFAULT_COUNT, retries: int = 2,
                  backoff_s: float = 0.5) -> pd.DataFrame | None:
    """Fetch a recent qfq daily window, trying Tencent's current then legacy host."""
    code = tencent_code(ticker)
    if not code:
        return None
    param = f"{code},day,,,{max(10, int(count))},qfq"
    last_exc: Exception | None = None
    for attempt in range(max(1, int(retries))):
        for base in _TENCENT_URLS:
            try:
                url = f"{base}?{urllib.parse.urlencode({'param': param})}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    payload = json.loads(r.read())
                if payload.get("code") not in (None, 0):
                    continue
                frame = frame_from_payload(ticker, payload)
                if frame is not None and not frame.empty:
                    frame = keep_completed_sessions(frame)
                    if not frame.empty:
                        return frame
            except Exception as exc:  # noqa: BLE001 - the second host/retry is the fallback
                last_exc = exc
        if attempt + 1 < max(1, int(retries)):
            time.sleep(backoff_s * (2 ** attempt))
    if last_exc is not None:
        log.warning("china_stocks: Tencent repair fetch failed for %s: %s", ticker, last_exc)
    return None


def _compatible_overlap(base: pd.DataFrame, fresh: pd.DataFrame, tol: float) -> bool:
    """True only when the two adjusted close planes agree on at least one date."""
    if "close" not in base.columns or "close" not in fresh.columns:
        return False
    a = base["close"].dropna().copy()
    b = fresh["close"].dropna().copy()
    if a.empty or b.empty:
        return False
    a.index = pd.to_datetime(a.index).tz_localize(None).normalize()
    b.index = pd.to_datetime(b.index).tz_localize(None).normalize()
    a = a[~a.index.duplicated(keep="last")]
    b = b[~b.index.duplicated(keep="last")]
    overlap = a.index.intersection(b.index)
    if len(overlap) == 0:
        return False
    av = a.loc[overlap].astype(float)
    bv = b.loc[overlap].astype(float)
    rel = (av - bv).abs() / bv.abs().clip(lower=1e-9)
    return bool(float(rel.max()) <= tol)


def _probe_tencent_latest(tickers: list[str], cfg: dict) -> tuple[pd.Timestamp | None, dict[str, pd.DataFrame]]:
    """Find the latest completed A-share session from several liquid sentinels."""
    ordered: list[str] = []
    wanted = set(tickers)
    for t in _PROBE_PREFERENCE:
        if t in wanted:
            ordered.append(t)
    for t in tickers:
        if t not in ordered:
            ordered.append(t)
        if len(ordered) >= 6:
            break
    cache: dict[str, pd.DataFrame] = {}
    latest: pd.Timestamp | None = None
    retries = int(cfg.get("tencent_retries", 2))
    for t in ordered[:6]:
        df = fetch_tencent(t, count=_DEFAULT_COUNT, retries=retries)
        if df is None or df.empty:
            continue
        cache[t] = df
        d = pd.Timestamp(df.index.max()).tz_localize(None).normalize()
        latest = d if latest is None else max(latest, d)
        # Two liquid sentinels agreeing on a date are enough; keep probes bounded.
        if sum(pd.Timestamp(x.index.max()).tz_localize(None).normalize() == latest for x in cache.values()) >= 2:
            break
    return latest, cache


def heal_adjusted_tails(frames: dict[str, pd.DataFrame], tickers: list[str], group: str,
                        cfg: dict) -> dict[str, pd.DataFrame]:
    """Repair Yahoo omissions/stale tails without changing the canonical store owner.

    ``frames`` is the primary yfinance result for this run.  Tencent is consulted only
    for names that are absent from that result or lag the latest completed session seen
    on liquid Tencent sentinels.  A repair must either agree with the primary frame on
    overlap or, when the primary frame is absent, pass the store's existing adjustment-
    basis guard.  Only dates newer than the primary frame are appended; the caller's
    normal ``store.upsert(overwrite_overlap=True)`` remains the sole persistence path.
    """
    if not tickers:
        return frames

    latest, cache = _probe_tencent_latest(tickers, cfg)
    if latest is None:
        log.warning("china_stocks: Tencent freshness probe unavailable; repairing primary misses only")

    candidates: list[str] = []
    for t in tickers:
        base = frames.get(t)
        if base is None or base.empty:
            candidates.append(t)
            continue
        if latest is not None:
            last = pd.Timestamp(base.index.max()).tz_localize(None).normalize()
            if last < latest:
                candidates.append(t)

    if not candidates:
        return frames

    tol = float(cfg.get("tencent_basis_tol", 5e-3))
    workers = max(1, min(int(cfg.get("tencent_workers", 12)), 24))
    retries = int(cfg.get("tencent_retries", 2))
    fetched: dict[str, pd.DataFrame | None] = {}

    def _one(t: str) -> tuple[str, pd.DataFrame | None]:
        if t in cache:
            return t, cache[t]
        return t, fetch_tencent(t, count=_DEFAULT_COUNT, retries=retries)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_one, t) for t in candidates]
        for fut in as_completed(futs):
            t, df = fut.result()
            fetched[t] = df

    healed = basis_rejected = no_extension = unavailable = 0
    for t in candidates:
        fresh = fetched.get(t)
        if fresh is None or fresh.empty:
            unavailable += 1
            continue
        base = frames.get(t)
        fresh_last = pd.Timestamp(fresh.index.max()).tz_localize(None).normalize()
        if base is not None and not base.empty:
            base_last = pd.Timestamp(base.index.max()).tz_localize(None).normalize()
            if fresh_last <= base_last:
                no_extension += 1  # normal for a genuinely suspended name
                continue
            if not _compatible_overlap(base, fresh, tol):
                basis_rejected += 1
                log.warning("china_stocks: Tencent tail rejected for %s (primary overlap basis mismatch)", t)
                continue
            tail = fresh[pd.to_datetime(fresh.index).tz_localize(None).normalize() > base_last]
            if tail.empty:
                no_extension += 1
                continue
            frames[t] = pd.concat([base, tail]).sort_index()
            frames[t] = frames[t][~frames[t].index.duplicated(keep="last")]
            healed += 1
            continue

        # Primary missed this ticker entirely.  Validate against the persisted deep store
        # before letting a secondary provider own the recent overwrite window.
        old = store.read(group, t)
        if old is not None and not old.empty and store.basis_shifted(group, t, fresh, tol=tol):
            basis_rejected += 1
            log.warning("china_stocks: Tencent tail rejected for %s (stored basis mismatch/no overlap)", t)
            continue
        frames[t] = fresh
        healed += 1

    log.info(
        "china_stocks: Tencent repair candidates=%d healed=%d suspended/no-extension=%d "
        "basis_rejected=%d unavailable=%d market_latest=%s",
        len(candidates), healed, no_extension, basis_rejected, unavailable,
        latest.date().isoformat() if latest is not None else "unknown",
    )
    return frames
