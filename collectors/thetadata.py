"""collectors/thetadata.py — thin client for the local ThetaData Terminal v3 REST API.

ThetaData works via a local Java process ("Theta Terminal") that exposes a REST API on
localhost.  Our job is purely to call that API and return normalized DataFrames; all option
pricing, signing, and analytics live in engine/.

CONTRACT (same spirit as collectors/databento_tbbo.py and collectors/massive_flatfiles.py)
---------------------------------------------------------------------------
INERT when the terminal is unreachable:
  • Terminal unreachable / non-200 / malformed response → log one WARNING, return None or an
    empty DataFrame.  NEVER raise into a build.
  • Short connect timeout (CONNECT_TIMEOUT = 2s) for the reachability check.
  • Generous read timeout (READ_TIMEOUT = 120s) for bulk pulls that may stream many rows.

API topology (measured live 2026-07-04 against ThetaTerminal v3 20260702:79baa88):
  Base URL: http://127.0.0.1:25503  (override via THETA_TERMINAL_URL env)
  Version:  v3 (v2 paths return HTTP 410 Gone — dead)
  Account:  Options: PROFESSIONAL; Max concurrent requests: 8
  Runs on:  the same Mac as the nightly collectors; started by scripts/run_theta_terminal.sh

Concurrency ceiling:
  The terminal enforces a hard ceiling of 8 concurrent requests.  The backfill driver runs
  sequentially today; this ceiling is NOT enforced in this module.  Document and respect: do
  not fan out more than 8 concurrent calls in any future parallelization.

Strike format (v3, measured live):
  v3 uses DOLLAR FLOATS directly (e.g., 170.000 = $170.00).  The v2 1/10th-cent integer
  convention (strike / 1000 = dollars) is DEAD.  No divisor is applied; strikes are used
  as-is from the API response.
  → STRIKE_DIVISOR = 1.0  (identity; kept for backward-compat constant reference only).
  Source: measured from /v3/option/history/eod response (e.g., "SPY","2026-07-17",723.000).

Param renames (v2 → v3, verified live):
  root      → symbol
  exp       → expiration   (YYYYMMDD integer, date string "YYYY-MM-DD", or "*" wildcard)
  strike    → strike       (DOLLAR FLOAT, e.g., "170.000")
  right     → right        (requests: "call"/"put"; responses: "CALL"/"PUT")
  use_csv   → format       (format=csv|json|ndjson|html)

Response format: CSV by default (format=csv).  Streaming chunked response; no pagination.

Wildcard-expiration rule (enforced by API):
  When expiration="*", the API requires start_date == end_date (one day at a time).
  Multi-day wildcard requests are rejected with an error.  This module enforces that rule
  by iterating day-by-day when exp="*" is requested.

Endpoints implemented (measured live 2026-07-04):
  GET /v3/option/list/symbols              → reachable() probe
  GET /v3/option/history/eod              → bulk_eod()
  GET /v3/option/history/open_interest    → bulk_open_interest()
  GET /v3/option/history/greeks/eod       → bulk_greeks() (see GREEKS NOTE below)
  GET /v3/option/history/trade_quote      → trade_quote()

GREEKS NOTE (v3 doc-vs-live finding, measured 2026-07-04):
  The correct endpoint for EOD greeks is /v3/option/history/greeks/eod (NOT /greeks/all).
  /greeks/eod returns one row per contract per day with all greek orders, OHLCV, bid/ask,
  and IV — a buffered response suitable for bulk use.
  /greeks/all streams 1-second snapshots; multi-day requests require interval >= 1 minute,
  but ALL interval values are rejected with "Invalid interval: X" for this endpoint.
  greeks/eod supports wildcard expiration (expiration="*") for ONE day at a time (same rule
  as bulk_eod).  Multi-day wildcard → iterate day-by-day in this module.

CSV headers (verbatim from live API, 2026-07-04):
  EOD:  symbol,expiration,strike,right,created,last_trade,open,high,low,close,
         volume,count,bid_size,bid_exchange,bid,bid_condition,ask_size,ask_exchange,
         ask,ask_condition
  OI:   symbol,expiration,strike,right,timestamp,open_interest
  greeks/eod: symbol,expiration,strike,right,timestamp,open,high,low,close,volume,count,
              bid_size,bid_exchange,bid,bid_condition,ask_size,ask_exchange,ask,ask_condition,
              delta,theta,vega,rho,epsilon,lambda,gamma,vanna,charm,vomma,veta,vera,
              speed,zomma,color,ultima,d1,d2,dual_delta,dual_gamma,implied_vol,iv_error,
              underlying_timestamp,underlying_price
  trade_quote: symbol,expiration,strike,right,trade_timestamp,quote_timestamp,
               sequence,ext_condition1,ext_condition2,ext_condition3,ext_condition4,
               condition,size,exchange,price,bid_size,bid_exchange,bid,bid_condition,
               ask_size,ask_exchange,ask,ask_condition

OI update timing (confirmed from v2 docs, still applies in v3):
  OPRA reports OI once per day at ~06:30 ET; the value represents end-of-previous-day
  positions.  OI[t] from OPRA = positions as of EOD t-1.  Use OI[t-1] in any day-t
  signal; same-day OI is a data leak.

History depth (measured 2026-07-04, AAPL binary probe):
  Data exists from 2012-06-01 (first confirmed day with data).  2012-01-01 through
  2012-05-31 have NO data.  DEFAULT_START in backfill: 20120601.

SPXW (measured 2026-07-04):
  SPXW is confirmed as a valid distinct root in /v3/option/list/symbols.
  Add to INDEX_ROOTS alongside SPX for PM-settled weekly coverage.

AMBIGUITIES RESOLVED (as of 2026-07-04 probe):
  A1 (Bulk OI): v3 has /v3/option/history/open_interest with wildcard — CONFIRMED.
  A2 (SPXW): CONFIRMED as distinct root.
  A3 (2nd-order Greeks): greeks/eod returns all orders in one response — CONFIRMED.
  A4 (3rd-order Greeks): Same; speed/zomma/color/ultima all in greeks/eod response.
  A5 (Greeks layout): Measured — see CSV header above (all greek orders + OHLCV).
  A6 (IV endpoint): greeks/eod includes implied_vol column — no separate IV endpoint needed.
  A7 (exp=* day-by-day): Confirmed — one day at a time for wildcard requests.
  A8 (History depth): Measured — starts 2012-06-01 (NOT 2013-01-02 as initially guessed).
  A9 (Password in argv): v3 uses --api-key flag (not positional user/pass) — IMPROVED.
"""
from __future__ import annotations

import io
import logging
import os
from datetime import date, datetime, timedelta
from typing import Iterator

import pandas as pd
import requests


class _StreamTruncated(Exception):
    """Raised internally when a mid-stream read fails.

    Public methods catch this and return None (the INERT contract) so that partial
    results are NEVER silently returned as complete data.  The caller logs one WARNING
    naming the root / date-range before raising.
    """


log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Config / connectivity
# --------------------------------------------------------------------------- #

CONNECT_TIMEOUT = 2       # seconds — fast reachability check
READ_TIMEOUT = 120        # seconds — streaming reads can be slow for bulk pulls

# v3 strike format: DOLLAR FLOATS (e.g., 170.000 = $170.00).
# STRIKE_DIVISOR = 1.0 (identity) — v2's 1/10th-cent integer format is dead.
# Kept as a named constant for documentation; never divide by this in v3 code.
STRIKE_DIVISOR = 1.0

# Greek column name mapping for the order= compatibility shim.
# v3 returns all greek orders in a single /greeks/all response.
_FIRST_ORDER_COLS  = ["delta", "theta", "vega", "rho", "epsilon", "lambda",
                       "implied_vol", "iv_error", "underlying_price"]
_SECOND_ORDER_COLS = ["gamma", "vanna", "charm", "vomma", "veta", "vera"]
_THIRD_ORDER_COLS  = ["speed", "zomma", "color", "ultima"]
_ALL_GREEK_COLS    = _FIRST_ORDER_COLS + _SECOND_ORDER_COLS + _THIRD_ORDER_COLS


def _base_url() -> str:
    return os.environ.get("THETA_TERMINAL_URL", "http://127.0.0.1:25503").rstrip("/")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["Accept"] = "text/csv, application/json"
    return s


def reachable() -> bool:
    """Quick check: can we GET /v3/option/list/symbols within CONNECT_TIMEOUT seconds?

    v3 health check endpoint (verified live 2026-07-04).  HTTP 200 = terminal up.
    v2 /v2/list/roots/option is dead (returns 410 Gone) — do NOT use.
    """
    try:
        r = requests.get(f"{_base_url()}/v3/option/list/symbols",
                         timeout=CONNECT_TIMEOUT)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# Low-level HTTP helpers — CSV streaming
# --------------------------------------------------------------------------- #

def _get_csv(session: requests.Session, path: str, params: dict) -> pd.DataFrame | None:
    """Single streaming CSV GET; returns a parsed DataFrame or None on any error.

    v3 returns chunked streaming CSV.  No pagination — one continuous response.
    Errors (non-200) are logged as warnings; None is returned (INERT contract).
    """
    url = f"{_base_url()}{path}"
    params = dict(params)
    params.setdefault("format", "csv")
    try:
        r = session.get(url, params=params, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                        stream=True)
    except requests.exceptions.ConnectionError:
        log.warning("thetadata: terminal unreachable at %s — skip", _base_url())
        return None
    except Exception as e:  # noqa: BLE001
        log.warning("thetadata: request error %s %s — %s", path, params, e)
        return None

    if r.status_code in (404, 472):
        # 404: empty range for this request
        # 472: ThetaData NO_DATA — valid empty response (e.g., holiday, pre-history date)
        return pd.DataFrame()
    if r.status_code != 200:
        try:
            body = r.text[:200]
        except Exception:  # noqa: BLE001
            body = "(unreadable)"
        log.warning("thetadata: HTTP %d for %s %s — %s", r.status_code, path, params, body)
        return None

    try:
        chunks = []
        for chunk in r.iter_content(chunk_size=65536):
            if chunk:
                chunks.append(chunk)
        raw = b"".join(chunks)
    except (requests.exceptions.ChunkedEncodingError,
            requests.exceptions.ConnectionError) as e:
        raise _StreamTruncated(f"stream read error: {e}") from e
    except Exception as e:  # noqa: BLE001
        raise _StreamTruncated(f"unexpected stream error: {e}") from e

    if not raw or raw.strip() in (b"", b"No data found for your request"):
        return pd.DataFrame()

    try:
        df = pd.read_csv(io.BytesIO(raw), low_memory=False)
        return df
    except Exception as e:  # noqa: BLE001
        log.warning("thetadata: CSV parse error for %s %s — %s", path, params, e)
        return None


def _stream_lines(session: requests.Session, path: str,
                  params: dict) -> Iterator[bytes]:
    """Yield raw CSV lines from a streaming response, raising _StreamTruncated on failure.

    Used for large streaming endpoints (e.g., greeks/all) where we want to process
    incrementally rather than buffering the entire response in memory.
    """
    url = f"{_base_url()}{path}"
    params = dict(params)
    params.setdefault("format", "csv")
    try:
        r = session.get(url, params=params,
                        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), stream=True)
    except requests.exceptions.ConnectionError as e:
        log.warning("thetadata: terminal unreachable at %s — skip", _base_url())
        raise _StreamTruncated(f"connection error: {e}") from e
    except Exception as e:  # noqa: BLE001
        raise _StreamTruncated(f"request error: {e}") from e

    if r.status_code in (404, 472):
        # No data for this request — yield nothing (empty stream, not an error)
        return
    if r.status_code != 200:
        try:
            body = r.text[:200]
        except Exception:  # noqa: BLE001
            body = "(unreadable)"
        log.warning("thetadata: HTTP %d for %s %s — %s", r.status_code, path, params, body)
        raise _StreamTruncated(f"HTTP {r.status_code}")

    try:
        for line in r.iter_lines():
            yield line
    except (requests.exceptions.ChunkedEncodingError,
            requests.exceptions.ConnectionError) as e:
        raise _StreamTruncated(f"mid-stream read error: {e}") from e
    except Exception as e:  # noqa: BLE001
        raise _StreamTruncated(f"unexpected stream error: {e}") from e


def _date_int(d: date | str | int) -> int:
    """Normalize date to YYYYMMDD integer for API params."""
    if isinstance(d, int):
        return d
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return int(d.strftime("%Y%m%d"))


def _iter_days(start: date | str | int, end: date | str | int) -> Iterator[date]:
    """Yield each calendar date from start to end (inclusive)."""
    if isinstance(start, int):
        s = str(start)
        start = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    elif isinstance(start, str):
        start = date.fromisoformat(start[:10])
    if isinstance(end, int):
        s = str(end)
        end = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    elif isinstance(end, str):
        end = date.fromisoformat(end[:10])
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _normalize_right_request(right: str) -> str:
    """Normalize right value for request params: 'C'/'CALL' → 'call'; 'P'/'PUT' → 'put'."""
    r = right.upper().strip()
    if r in ("C", "CALL"):
        return "call"
    if r in ("P", "PUT"):
        return "put"
    return r.lower()


def _normalize_expiration_param(exp: int | str | date) -> str:
    """Normalize expiration to the string format the v3 API accepts.

    v3 accepts YYYYMMDD integers, ISO date strings, or "*" wildcard.
    Returns the string form suitable for the 'expiration' query param.
    """
    if isinstance(exp, str) and exp == "*":
        return "*"
    if isinstance(exp, int) and exp == 0:
        return "*"   # backward compat: exp=0 means all-expiries in v2; map to wildcard
    return str(_date_int(exp))


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def bulk_eod(root: str, exp: int | str | date, start_date: date | str | int,
             end_date: date | str | int) -> pd.DataFrame | None:
    """EOD option chain data for all strikes of a given root+expiry, over a date range.

    Endpoint: GET /v3/option/history/eod
    v3 params: symbol=ROOT, expiration=YYYYMMDD|"*", start_date=YYYYMMDD, end_date=YYYYMMDD
    Wildcard rule: when expiration="*" (or exp=0 for backward compat), iterates ONE DAY
    AT A TIME as required by the v3 API.

    v3 CSV columns: symbol,expiration,strike,right,created,last_trade,open,high,low,close,
                    volume,count,bid_size,bid_exchange,bid,bid_condition,
                    ask_size,ask_exchange,ask,ask_condition

    Strike format: v3 returns DOLLAR FLOATS (e.g., 725.000 = $725.00). No divisor applied.
    right: response returns "CALL"/"PUT"; normalized to "C"/"P" in output.

    Returns a DataFrame with columns:
      symbol, expiration (datetime64), strike (float, $), right ("C"/"P"),
      date (datetime64), open, high, low, close, volume, count, bid, ask
    or None if the terminal is unreachable or returns a permission error.
    """
    if not reachable():
        log.warning("thetadata: terminal not reachable — bulk_eod returning None")
        return None

    exp_param = _normalize_expiration_param(exp)
    start_int = _date_int(start_date)
    end_int = _date_int(end_date)

    session = _session()
    frames: list[pd.DataFrame] = []

    try:
        if exp_param == "*":
            # Wildcard: one day at a time (API enforces this).
            # An empty DataFrame for a day (472 / holiday / weekend) is FINE — skip it.
            # A None return means a real failure (non-200 error, connection error).
            for d in _iter_days(start_date, end_date):
                day_int = _date_int(d)
                params = {
                    "symbol": root.upper(),
                    "expiration": "*",
                    "start_date": day_int,
                    "end_date": day_int,
                }
                df = _get_csv(session, "/v3/option/history/eod", params)
                if df is None:
                    log.warning(
                        "thetadata: bulk_eod(%s, *, %s) day %s failed — "
                        "returning None to avoid partial data", root, d, d)
                    return None
                if not df.empty:
                    df["_date"] = pd.Timestamp(d)
                    frames.append(df)
                # Empty df for this day = weekend / holiday / no data: skip silently
        else:
            params = {
                "symbol": root.upper(),
                "expiration": exp_param,
                "start_date": start_int,
                "end_date": end_int,
            }
            df = _get_csv(session, "/v3/option/history/eod", params)
            if df is None:
                log.warning("thetadata: bulk_eod(%s, %s) failed — returning None", root, exp_param)
                return None
            if not df.empty:
                frames.append(df)

    except _StreamTruncated as e:
        log.warning("thetadata: bulk_eod(%s, start=%s, end=%s) truncated at mid-stream "
                    "— returning None to avoid persisting partial data: %s",
                    root, start_date, end_date, e)
        return None

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    return _normalize_eod_df(out, root)


def _normalize_eod_df(df: pd.DataFrame, root: str) -> pd.DataFrame:
    """Normalize a raw v3 EOD CSV DataFrame into the canonical output schema."""
    if df.empty:
        return df

    # Strip quotes from string columns (CSV may include surrounding quotes)
    for col in ("symbol", "expiration", "right"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip('"').str.strip()

    # Use _date column (set during day iteration) or derive from created/last_trade
    if "_date" in df.columns:
        df["date"] = pd.to_datetime(df["_date"])
        df = df.drop(columns=["_date"])
    elif "created" in df.columns:
        # Derive date from the 'created' timestamp (e.g., "2026-07-02T17:21:28.532")
        df["date"] = pd.to_datetime(df["created"], errors="coerce").dt.normalize()
    else:
        df["date"] = pd.NaT

    # Parse expiration
    if "expiration" in df.columns:
        df["expiration"] = pd.to_datetime(df["expiration"], errors="coerce")

    # Normalize right: "CALL" → "C", "PUT" → "P"
    if "right" in df.columns:
        df["right"] = df["right"].map({"CALL": "C", "PUT": "P"}).fillna(df["right"])

    # Strike is already a dollar float in v3 — no divisor
    if "strike" in df.columns:
        df["strike"] = pd.to_numeric(df["strike"], errors="coerce")

    # Rename symbol → root for backward compat
    if "symbol" in df.columns:
        df = df.rename(columns={"symbol": "root"})

    keep = ["root", "expiration", "strike", "right", "date",
            "open", "high", "low", "close", "volume", "count", "bid", "ask"]
    available = [c for c in keep if c in df.columns]
    return df[available].reset_index(drop=True)


def bulk_open_interest(root: str, exp: int | str | date, start_date: date | str | int,
                       end_date: date | str | int) -> pd.DataFrame | None:
    """Open interest for all contracts of a given root+expiry over a date range.

    Endpoint: GET /v3/option/history/open_interest  (bulk; wildcard supported)
    Wildcard rule: when exp="*" (or exp=0), iterates one day at a time.

    v3 CSV columns: symbol,expiration,strike,right,timestamp,open_interest
    OI timing: OPRA reports OI once per day at ~06:30 ET; the value represents
    end-of-previous-day positions.  Use OI[t-1] in any day-t signal.

    Returns DataFrame: root, expiration, strike, right, date, open_interest
    or None if terminal is unreachable.
    """
    if not reachable():
        log.warning("thetadata: terminal not reachable — bulk_open_interest returning None")
        return None

    exp_param = _normalize_expiration_param(exp)
    session = _session()
    frames: list[pd.DataFrame] = []

    try:
        if exp_param == "*":
            # Same day-by-day contract as bulk_eod; empty = weekend/holiday, None = error.
            for d in _iter_days(start_date, end_date):
                day_int = _date_int(d)
                params = {
                    "symbol": root.upper(),
                    "expiration": "*",
                    "start_date": day_int,
                    "end_date": day_int,
                }
                df = _get_csv(session, "/v3/option/history/open_interest", params)
                if df is None:
                    log.warning(
                        "thetadata: bulk_open_interest(%s, *, %s) day %s failed — "
                        "returning None to avoid partial data", root, d, d)
                    return None
                if not df.empty:
                    frames.append(df)
                # Empty df for this day = weekend / holiday / no data: skip silently
        else:
            params = {
                "symbol": root.upper(),
                "expiration": exp_param,
                "start_date": _date_int(start_date),
                "end_date": _date_int(end_date),
            }
            df = _get_csv(session, "/v3/option/history/open_interest", params)
            if df is None:
                log.warning("thetadata: bulk_open_interest(%s, %s) failed — returning None",
                            root, exp_param)
                return None
            if not df.empty:
                frames.append(df)

    except _StreamTruncated as e:
        log.warning("thetadata: bulk_open_interest(%s, start=%s, end=%s) truncated at "
                    "mid-stream — returning None: %s", root, start_date, end_date, e)
        return None

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    return _normalize_oi_df(out)


def _normalize_oi_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize raw v3 OI CSV DataFrame."""
    if df.empty:
        return df

    for col in ("symbol", "expiration", "right"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip('"').str.strip()

    if "expiration" in df.columns:
        df["expiration"] = pd.to_datetime(df["expiration"], errors="coerce")

    # OI timestamp (e.g., "2026-07-02T06:30:16.218") → date
    if "timestamp" in df.columns:
        df["date"] = pd.to_datetime(df["timestamp"], errors="coerce").dt.normalize()
    else:
        df["date"] = pd.NaT

    if "right" in df.columns:
        df["right"] = df["right"].map({"CALL": "C", "PUT": "P"}).fillna(df["right"])

    if "strike" in df.columns:
        df["strike"] = pd.to_numeric(df["strike"], errors="coerce")

    if "open_interest" in df.columns:
        df["open_interest"] = pd.to_numeric(df["open_interest"], errors="coerce")

    if "symbol" in df.columns:
        df = df.rename(columns={"symbol": "root"})

    keep = ["root", "expiration", "strike", "right", "date", "open_interest"]
    available = [c for c in keep if c in df.columns]
    return df[available].reset_index(drop=True)


def bulk_greeks(root: str, exp: int | str | date, start_date: date | str | int,
                end_date: date | str | int, *, order: int = 1) -> pd.DataFrame | None:
    """Greeks for all contracts of a given root+expiry, one row per contract per day (EOD).

    Endpoint: GET /v3/option/history/greeks/eod  (all orders in one buffered response)
    v3 behavior (measured 2026-07-04): /greeks/eod returns one row per contract per
    trading day with all greek orders + OHLCV + implied_vol + underlying_price.
    This is the correct EOD endpoint; /greeks/all streams 1-second snapshots and has
    no usable interval parameter for multi-day bulk pulls.

    WILDCARD EXPIRATION: exp=0 / exp="*" iterates day-by-day (same rule as bulk_eod).
    Multi-day wildcard is supported by collecting each calendar day independently.

    The order= parameter selects a column subset from the all-orders response:
      order=1 → first-order: delta, theta, vega, rho, epsilon, lambda,
                implied_vol, iv_error, underlying_price
      order=2 → adds second-order: gamma, vanna, charm, vomma, veta, vera
      order=3 → all columns (first + second + third order)

    Returns DataFrame: root, expiration, strike, right, date, bid, ask, [greek columns].
    None if terminal is unreachable / not entitled.
    """
    if order not in (1, 2, 3):
        raise ValueError(f"order must be 1, 2, or 3; got {order}")

    exp_param = _normalize_expiration_param(exp)

    if not reachable():
        log.warning("thetadata: terminal not reachable — bulk_greeks(order=%d) returning None",
                    order)
        return None

    session = _session()

    if exp_param == "*":
        # Wildcard: must iterate day-by-day (API enforces start_date == end_date for exp=*)
        frames: list[pd.DataFrame] = []
        for day in _iter_days(start_date, end_date):
            params = {
                "symbol": root.upper(),
                "expiration": "*",
                "start_date": int(day.strftime("%Y%m%d")),
                "end_date": int(day.strftime("%Y%m%d")),
            }
            try:
                df_day = _get_csv(session, "/v3/option/history/greeks/eod", params)
            except _StreamTruncated as e:
                log.warning(
                    "thetadata: bulk_greeks(%s, exp=*, date=%s) truncated — returning None: %s",
                    root, day, e)
                return None
            if df_day is None:
                log.warning(
                    "thetadata: bulk_greeks(%s, exp=*, date=%s) request failed — aborting",
                    root, day)
                return None
            if not df_day.empty:
                frames.append(df_day)
            # Empty (weekend/holiday 472) → skip silently
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    else:
        params = {
            "symbol": root.upper(),
            "expiration": exp_param,
            "start_date": _date_int(start_date),
            "end_date": _date_int(end_date),
        }
        try:
            df = _get_csv(session, "/v3/option/history/greeks/eod", params)
        except _StreamTruncated as e:
            log.warning("thetadata: bulk_greeks(%s, exp=%s, start=%s, end=%s) truncated — "
                        "returning None: %s", root, exp_param, start_date, end_date, e)
            return None
        if df is None:
            log.warning("thetadata: bulk_greeks(%s, exp=%s, start=%s, end=%s) request failed",
                        root, exp_param, start_date, end_date)
            return None

    if df.empty:
        return df

    # Normalize types
    for col in ("symbol", "expiration", "right"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip('"').str.strip()

    # greeks/eod uses "timestamp" = last-trade timestamp; derive calendar date from it
    if "timestamp" in df.columns:
        df["date"] = pd.to_datetime(df["timestamp"], errors="coerce").dt.normalize()
    else:
        df["date"] = pd.NaT

    if "expiration" in df.columns:
        df["expiration"] = pd.to_datetime(df["expiration"], errors="coerce")

    if "right" in df.columns:
        df["right"] = df["right"].map({"CALL": "C", "PUT": "P"}).fillna(df["right"])

    if "strike" in df.columns:
        df["strike"] = pd.to_numeric(df["strike"], errors="coerce")

    # Numeric-ify all greek columns
    for col in _ALL_GREEK_COLS + ["bid", "ask", "underlying_price"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "symbol" in df.columns:
        df = df.rename(columns={"symbol": "root"})

    # order= column slicing
    if order == 1:
        greek_cols = _FIRST_ORDER_COLS
    elif order == 2:
        greek_cols = _FIRST_ORDER_COLS + _SECOND_ORDER_COLS
    else:
        greek_cols = _ALL_GREEK_COLS

    id_cols = ["root", "expiration", "strike", "right", "date", "bid", "ask",
               "underlying_price"]
    keep = id_cols + [c for c in greek_cols if c not in id_cols and c in df.columns]
    available = [c for c in keep if c in df.columns]
    return df[available].reset_index(drop=True)


def trade_quote(root: str, exp: int | str | date, right: str, strike: float,
                start_date: date | str | int, end_date: date | str | int) -> pd.DataFrame | None:
    """Every trade paired with the prevailing NBBO at execution, for ONE specific contract.

    Endpoint: GET /v3/option/history/trade_quote
    Required params: symbol, expiration (YYYYMMDD), strike (DOLLAR FLOAT), right (call/put),
                     start_date, end_date.

    v3 CSV columns (verbatim, measured 2026-07-04):
      symbol,expiration,strike,right,trade_timestamp,quote_timestamp,sequence,
      ext_condition1,ext_condition2,ext_condition3,ext_condition4,condition,size,exchange,
      price,bid_size,bid_exchange,bid,bid_condition,ask_size,ask_exchange,ask,ask_condition

    Strike: passed as DOLLAR FLOAT (no conversion needed in v3).
    right: normalized to "call"/"put" for requests; response carries "CALL"/"PUT".

    This is the gold-standard source for quote-rule signing calibration:
    every trade is stamped with the NBBO at execution, enabling Lee-Ready signing.

    Returns DataFrame: date, trade_timestamp, price, size, bid, ask, right, strike, root, exchange
    or None if terminal is unreachable.
    """
    if not reachable():
        log.warning("thetadata: terminal not reachable — trade_quote returning None")
        return None

    params = {
        "symbol": root.upper(),
        "expiration": _normalize_expiration_param(exp),
        "strike": f"{float(strike):.3f}",   # v3 expects dollar float e.g., "580.000"
        "right": _normalize_right_request(right),
        "start_date": _date_int(start_date),
        "end_date": _date_int(end_date),
    }
    session = _session()
    rows_all: list[dict] = []

    try:
        for raw_line in _stream_lines(session, "/v3/option/history/trade_quote", params):
            if isinstance(raw_line, bytes):
                line = raw_line.decode("utf-8", errors="replace")
            else:
                line = raw_line
            line = line.strip()
            if not line:
                continue
            # Skip header row
            if line.startswith("symbol,"):
                continue
            parts = [v.strip().strip('"') for v in line.split(",")]
            # v3 CSV: symbol,expiration,strike,right,trade_timestamp,quote_timestamp,
            #         sequence,ext_condition1-4,condition,size,exchange,price,
            #         bid_size,bid_exchange,bid,bid_condition,ask_size,ask_exchange,ask,ask_condition
            if len(parts) < 23:
                continue
            rows_all.append({
                "date": parts[4][:10] if parts[4] else None,   # trade_timestamp[:10] = date
                "trade_timestamp": parts[4],
                "quote_timestamp": parts[5],
                "price": parts[14],
                "size": parts[12],
                "bid": parts[17],
                "ask": parts[21],
                "exchange": parts[13],
            })

    except _StreamTruncated as e:
        log.warning("thetadata: trade_quote(%s, exp=%s, %s, strike=%s, start=%s, end=%s) "
                    "truncated at mid-stream — returning None: %s",
                    root, exp, right, strike, start_date, end_date, e)
        return None

    if not rows_all:
        return pd.DataFrame()

    df = pd.DataFrame(rows_all)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["size"] = pd.to_numeric(df["size"], errors="coerce")
    df["bid"] = pd.to_numeric(df["bid"], errors="coerce")
    df["ask"] = pd.to_numeric(df["ask"], errors="coerce")
    df["strike"] = float(strike)
    df["right"] = right.upper()
    df["root"] = root.upper()
    return df.reset_index(drop=True)
