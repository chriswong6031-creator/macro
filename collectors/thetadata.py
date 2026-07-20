"""collectors/thetadata.py — thin client for the local ThetaData Terminal v3 REST API.

ThetaData works via a local Java process ("Theta Terminal") that exposes a REST API on
localhost.  Our job is purely to call that API and return normalized DataFrames; all option
pricing, signing, and analytics live in engine/.

CONTRACT (same spirit as collectors/databento_tbbo.py and collectors/massive_flatfiles.py)
---------------------------------------------------------------------------
INERT when the terminal is unreachable:
  • Terminal unreachable / non-200 / malformed response → log one WARNING, return None or an
    empty DataFrame.  NEVER raise into a build.
  • Short connect timeout (CONNECT_TIMEOUT = 3s) for the reachability check.
  • Generous read timeout (READ_TIMEOUT_BETWEEN_BYTES = 90s) between bytes on streaming reads.
    This is the per-read-call timeout, not the total response time.  A stalled stream (zero
    bytes flowing for >90s) raises ReadTimeout → caught as _StreamTruncated → returns None.

STALL FIX (2026-07-05):
  Live diagnosis showed that bulk "range" requests spanning months hang indefinitely: the
  terminal assembles old data server-side and starves the stream (32,768 bytes then silence).
  Short windows (≤7 calendar days) with wildcard expiration work reliably (HTTP 200, data
  flowing).  The fix: iterate ≤7-day windows with ThreadPoolExecutor(max_workers=6) so
  backfill concurrency saturates the terminal's 8-concurrent ceiling with headroom.

  Per-window retry: on stall/truncation, retry up to 2 more times with 5s/15s backoff.
  If a window still fails after retries → WHOLE call returns None (no partial DataFrame).
  Deterministic ordering: windows are submitted in chronological order; results sorted by
  window key after gather.

API topology (measured live 2026-07-04 against ThetaTerminal v3 20260702:79baa88):
  Base URL: http://127.0.0.1:25503  (override via THETA_TERMINAL_URL env)
  Version:  v3 (v2 paths return HTTP 410 Gone — dead)
  Account:  Options: PROFESSIONAL; Max concurrent requests: 8
  Runs on:  the same Mac as the nightly collectors; started by scripts/run_theta_terminal.sh

Concurrency ceiling:
  The terminal enforces a hard ceiling of 8 concurrent requests.  WINDOW_WORKERS = 6 leaves
  2 slots of headroom for other concurrent operations.

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

Wildcard-expiration rule (endpoint-specific, measured live 2026-07-04):
  /history/eod ACCEPTS multi-day wildcard (expiration="*") — but ONLY for SHORT windows
  (≤7 calendar days; measured reliable).  Long ranges stall the stream server-side.
  /history/greeks/eod REJECTS multi-day wildcard (HTTP 400: "When expiration=*, you must
  request data a day-at-a-time").  bulk_greeks keeps the day-by-day loop with concurrency.

Endpoints implemented (measured live 2026-07-04):
  GET /v3/option/list/symbols              → reachable() probe
  GET /v3/option/history/eod              → bulk_eod()
  GET /v3/option/history/open_interest    → bulk_open_interest()
  GET /v3/option/history/greeks/eod       → bulk_greeks() (see GREEKS NOTE below)
  GET /v3/option/history/trade_quote      → bulk_trade_quote() (1 right, any date range)
                                          → bulk_trade_quote_day() (both legs, 1 day)
                                          → trade_quote() (single-contract, any range)

Snapshot endpoints (measured live 2026-07-16 — U-CHAIN lane, research/THETADATA_PROBE.md):
  GET /v3/option/snapshot/greeks/first_order   → snapshot_greeks(root, order="first")
  GET /v3/option/snapshot/greeks/second_order  → snapshot_greeks(root, order="second")
  GET /v3/option/snapshot/open_interest        → snapshot_open_interest(root)
  Unlike the history greeks endpoints, snapshots ACCEPT expiration=* AND strike=*:
  one request returns the full live chain (SPY: 14,065 rows in 0.96s first-order,
  0.83s second-order, 0.21s OI).  Market closed → last-known close-ish values.

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

CSV headers (verbatim from live API, 2026-07-16 — snapshot endpoints):
  snapshot greeks/first_order:  symbol,expiration,strike,right,timestamp,bid,ask,
               delta,theta,vega,rho,epsilon,lambda,implied_vol,iv_error,
               underlying_timestamp,underlying_price
  snapshot greeks/second_order: symbol,expiration,strike,right,timestamp,bid,ask,
               gamma,vanna,charm,vomma,veta,implied_vol,iv_error,
               underlying_timestamp,underlying_price
  snapshot open_interest: timestamp,symbol,expiration,strike,right,open_interest
               (NOTE: timestamp is the FIRST column here, unlike the greeks
               snapshots — normalization is by column name, never by position)

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
  A7 (exp=* endpoint-specific): /history/eod ACCEPTS short wildcard windows (≤7d measured);
     long ranges stall (stall fix: windowed pulls). /history/greeks/eod REJECTS multi-day
     wildcard (HTTP 400) — keeps day-by-day loop.
  A8 (History depth): Measured — starts 2012-06-01 (NOT 2013-01-02 as initially guessed).
  A9 (Password in argv): v3 accepts --api-key flag OR THETADATA_API_KEY env var.
     Launcher uses the env var (2026-07-16): --api-key put the key in plaintext argv,
     readable by any local process via `ps`.
"""
from __future__ import annotations

import io
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
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

CONNECT_TIMEOUT = int(os.environ.get("THETA_CONNECT_TIMEOUT", "3"))
# THETA_CONNECT_TIMEOUT env override (item 1a): allows the live_flow_poller to
# widen the connect timeout on per-root retries without affecting backfill callers.
# Default 3s retained — backfill and all other callers are unaffected.
READ_TIMEOUT_BETWEEN_BYTES = 90   # seconds — max wait between bytes on a streaming read
# tuple form (connect, read) passed to requests:
_TIMEOUTS = (CONNECT_TIMEOUT, READ_TIMEOUT_BETWEEN_BYTES)

# v3 strike format: DOLLAR FLOATS (e.g., 170.000 = $170.00).
# STRIKE_DIVISOR = 1.0 (identity) — v2's 1/10th-cent integer format is dead.
# Kept as a named constant for documentation; never divide by this in v3 code.
STRIKE_DIVISOR = 1.0

# Stall-fix: wildcard EOD and OI iterate in windows of at most this many calendar days.
# Measured reliable: 3-day wildcard EOD → 2.4 MB in 6s.
# Measured stall: 7-month specific-expiration range → hangs after 32 KiB.
# Short windows avoid server-side assembly latency.
WINDOW_DAYS = 7

# Bounded concurrency: terminal allows 8 concurrent requests; leave 2 slots headroom.
WINDOW_WORKERS = 6

# Per-window retry: attempts 1 + 2 retries on stall/truncation.
WINDOW_MAX_RETRIES = 2
WINDOW_RETRY_BACKOFF = (5, 15)   # seconds before retry 1, retry 2

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


def reachable(connect_timeout: int | None = None) -> bool:
    """Quick check: can we GET /v3/option/list/symbols within connect_timeout seconds?

    v3 health check endpoint (verified live 2026-07-04).  HTTP 200 = terminal up.
    v2 /v2/list/roots/option is dead (returns 410 Gone) — do NOT use.

    connect_timeout: override in seconds; defaults to CONNECT_TIMEOUT (env-configurable).
    Used by the live_flow_poller for direct terminal-offline probes with a wider timeout
    (15s) to distinguish true offline from transient contention.
    """
    timeout = connect_timeout if connect_timeout is not None else CONNECT_TIMEOUT
    try:
        r = requests.get(f"{_base_url()}/v3/option/list/symbols",
                         timeout=timeout)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def list_expirations(symbol: str) -> list[str] | None:
    """Return a sorted list of ISO date strings ("YYYY-MM-DD") for all expirations.

    Endpoint: GET /v3/option/list/expirations?symbol=<UPPER>&format=csv
    Returns the FULL history (2012→ far future).  Callers MUST filter to unexpired.

    Returns None on any error (log warning, INERT contract).
    """
    try:
        r = _session().get(
            f"{_base_url()}/v3/option/list/expirations",
            params={"symbol": symbol.upper(), "format": "csv"},
            timeout=_TIMEOUTS,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("thetadata: list_expirations(%s) request error — %s", symbol, e)
        return None

    if r.status_code != 200:
        try:
            body = r.text[:200]
        except Exception:  # noqa: BLE001
            body = "(unreadable)"
        log.warning("thetadata: list_expirations(%s) HTTP %d — %s", symbol, r.status_code, body)
        return None

    expirations: list[str] = []
    try:
        for line in r.text.splitlines():
            line = line.strip()
            if not line or line.startswith("symbol,"):
                continue
            # CSV: "SPY","2026-07-10"  or  SPY,2026-07-10
            parts = [v.strip().strip('"') for v in line.split(",")]
            if len(parts) >= 2 and parts[1]:
                # Normalize to YYYY-MM-DD regardless of format
                raw = parts[1].strip()
                if len(raw) == 8 and raw.isdigit():
                    # YYYYMMDD → YYYY-MM-DD
                    raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
                if len(raw) == 10:
                    expirations.append(raw)
    except Exception as e:  # noqa: BLE001
        log.warning("thetadata: list_expirations(%s) parse error — %s", symbol, e)
        return None

    return sorted(expirations)


# --------------------------------------------------------------------------- #
# Low-level HTTP helpers — CSV streaming
# --------------------------------------------------------------------------- #

def _get_csv(session: requests.Session, path: str, params: dict) -> pd.DataFrame | None:
    """Single streaming CSV GET; returns a parsed DataFrame or None on any error.

    v3 returns chunked streaming CSV.  No pagination — one continuous response.
    Errors (non-200) are logged as warnings; None is returned (INERT contract).

    Timeout: (CONNECT_TIMEOUT, READ_TIMEOUT_BETWEEN_BYTES).  A stalled stream that
    produces no bytes for READ_TIMEOUT_BETWEEN_BYTES seconds raises ReadTimeout,
    which is caught and re-raised as _StreamTruncated so callers return None.
    """
    url = f"{_base_url()}{path}"
    params = dict(params)
    params.setdefault("format", "csv")
    try:
        r = session.get(url, params=params, timeout=_TIMEOUTS, stream=True)
    except requests.exceptions.ConnectionError:
        log.warning("thetadata: terminal unreachable at %s — skip", _base_url())
        return None
    except requests.exceptions.ReadTimeout as e:
        raise _StreamTruncated(f"read timeout (no bytes for {READ_TIMEOUT_BETWEEN_BYTES}s): {e}") from e
    except Exception as e:  # noqa: BLE001
        log.warning("thetadata: request error %s %s — %s", path, params, e)
        return None

    if r.status_code in (404, 472):
        # 404: empty range for this request
        # 472: ThetaData NO_DATA — valid empty response (e.g., holiday, pre-history date)
        return pd.DataFrame()
    if r.status_code == 400:
        # Current-day wildcard rejection: greeks/eod (and friends) refuse
        # expiration=* for TODAY on a trading day ("Cannot fetch current-day data
        # without specifying an expiration"). This is EXPECTED post-close — treat
        # it as an empty window rather than a hard failure, so the other (completed)
        # day-windows in the same bulk pull are NOT discarded by _concurrent_windows.
        # Today's greeks are then picked up on the next run (a 1-day lag) instead of
        # the whole year nulling out and the store freezing until the weekend.
        try:
            body400 = r.text[:300].lower()
        except Exception:  # noqa: BLE001
            body400 = ""
        if "specifying an expiration" in body400 or "current-day" in body400 or "current day" in body400:
            log.info("thetadata: current-day wildcard not available yet for %s (%s→%s) — skipping this window",
                     path, params.get("start_date"), params.get("end_date"))
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
    except requests.exceptions.ReadTimeout as e:
        raise _StreamTruncated(f"read timeout mid-stream (no bytes for {READ_TIMEOUT_BETWEEN_BYTES}s): {e}") from e
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
        r = session.get(url, params=params, timeout=_TIMEOUTS, stream=True)
    except requests.exceptions.ConnectionError as e:
        log.warning("thetadata: terminal unreachable at %s — skip", _base_url())
        raise _StreamTruncated(f"connection error: {e}") from e
    except requests.exceptions.ReadTimeout as e:
        raise _StreamTruncated(f"read timeout on connect: {e}") from e
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
        raise _StreamTruncated(f"HTTP {r.status_code}: {body}")

    try:
        for line in r.iter_lines():
            yield line
    except requests.exceptions.ReadTimeout as e:
        raise _StreamTruncated(f"read timeout mid-stream: {e}") from e
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


def _parse_date_int(d: date | str | int) -> date:
    """Parse YYYYMMDD int, ISO string, or date object to date."""
    if isinstance(d, date):
        return d
    if isinstance(d, int):
        s = str(d)
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    return date.fromisoformat(d[:10])


def _iter_days(start: date | str | int, end: date | str | int) -> Iterator[date]:
    """Yield each calendar date from start to end (inclusive)."""
    start = _parse_date_int(start)
    end = _parse_date_int(end)
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _iter_windows(start: date | str | int, end: date | str | int,
                  window_days: int = WINDOW_DAYS) -> Iterator[tuple[date, date]]:
    """Yield (window_start, window_end) tuples of at most window_days calendar days.

    Windows tile [start, end] exactly: no gaps, no overlaps.
    The last window may be shorter than window_days.

    Example: _iter_windows(2012-06-01, 2012-06-15, 7) →
      (2012-06-01, 2012-06-07), (2012-06-08, 2012-06-14), (2012-06-15, 2012-06-15)
    """
    s = _parse_date_int(start)
    e = _parse_date_int(end)
    cur = s
    while cur <= e:
        win_end = min(cur + timedelta(days=window_days - 1), e)
        yield cur, win_end
        cur = win_end + timedelta(days=1)


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


def _endpoint_label(path: str) -> str:
    """Human-readable label for a URL path segment used in log lines.

    `path.split("/")[-1]` on /v3/option/history/greeks/eod returns "eod", which
    is indistinguishable from the plain EOD endpoint.  For paths whose last two
    segments are "greeks/eod" (or "greeks/<anything>"), return "greeks" so log
    lines read "SPY greeks 2026-01-01→2026-01-07" instead of "SPY eod".
    """
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and parts[-2] == "greeks":
        return "greeks"
    return parts[-1] if parts else path


def _fetch_window_with_retry(
    session: requests.Session,
    path: str,
    base_params: dict,
    win_start: date,
    win_end: date,
    *,
    window_idx: int,
    root: str,
) -> pd.DataFrame | None:
    """Fetch one window with up to WINDOW_MAX_RETRIES retries on stall/truncation.

    Returns DataFrame (possibly empty) on success, None on final failure.
    Logs one INFO line per completed window (root endpoint window rows elapsed).
    """
    params = dict(base_params)
    params["start_date"] = _date_int(win_start)
    params["end_date"] = _date_int(win_end)

    for attempt in range(WINDOW_MAX_RETRIES + 1):
        t0 = time.perf_counter()
        try:
            df = _get_csv(session, path, params)
            elapsed = time.perf_counter() - t0
            rows = len(df) if df is not None and not df.empty else 0
            if df is None:
                if attempt < WINDOW_MAX_RETRIES:
                    backoff = WINDOW_RETRY_BACKOFF[attempt]
                    log.warning(
                        "thetadata: window %s %s→%s attempt %d failed, retry in %ds",
                        root, win_start, win_end, attempt + 1, backoff)
                    time.sleep(backoff)
                    continue
                log.warning(
                    "thetadata: window %s %s %s→%s failed after %d attempts — aborting",
                    root, _endpoint_label(path), win_start, win_end, WINDOW_MAX_RETRIES + 1)
                return None
            log.info("thetadata: %s %s %s→%s rows=%d elapsed=%.1fs",
                     root, _endpoint_label(path), win_start, win_end, rows, elapsed)
            return df
        except _StreamTruncated as e:
            elapsed = time.perf_counter() - t0
            if attempt < WINDOW_MAX_RETRIES:
                backoff = WINDOW_RETRY_BACKOFF[attempt]
                log.warning(
                    "thetadata: window %s %s→%s attempt %d stalled (%.1fs) — retry in %ds: %s",
                    root, win_start, win_end, attempt + 1, elapsed, backoff, e)
                time.sleep(backoff)
            else:
                log.warning(
                    "thetadata: window %s %s→%s stalled after %d attempts — aborting: %s",
                    root, win_start, win_end, WINDOW_MAX_RETRIES + 1, e)
                return None
    return None  # unreachable, satisfies type checker


def _concurrent_windows(
    path: str,
    base_params: dict,
    start_date: date | str | int,
    end_date: date | str | int,
    *,
    root: str,
    window_days: int = WINDOW_DAYS,
) -> pd.DataFrame | None:
    """Pull [start_date, end_date] in ≤window_days windows using WINDOW_WORKERS threads.

    Windows are submitted in chronological order.  Results are sorted by window start
    date after gather to ensure deterministic ordering in the concatenated DataFrame.
    On any window's final failure: cancel/drain remaining futures, return None.

    window_days=WINDOW_DAYS (7) for eod/oi wildcard (short ranges measured reliable).
    window_days=1 for greeks/eod wildcard (API rejects multi-day: HTTP 400).

    This is the stall fix: short windows avoid server-side assembly latency that causes
    the terminal to stream a few KB then hang indefinitely on long date ranges.
    """
    windows = list(_iter_windows(start_date, end_date, window_days=window_days))
    if not windows:
        return pd.DataFrame()

    results: dict[int, pd.DataFrame] = {}  # window_idx → df
    failed = False

    with ThreadPoolExecutor(max_workers=WINDOW_WORKERS) as executor:
        # Each thread gets its own session (requests.Session is not thread-safe)
        future_to_idx = {
            executor.submit(
                _fetch_window_with_retry,
                _session(),  # fresh session per thread
                path,
                base_params,
                win_start,
                win_end,
                window_idx=i,
                root=root,
            ): i
            for i, (win_start, win_end) in enumerate(windows)
        }

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                df = future.result()
            except Exception as e:  # noqa: BLE001
                log.warning("thetadata: window %d raised unexpected error — aborting: %s", idx, e)
                df = None

            if df is None:
                failed = True
                # Cancel remaining futures (best-effort; running ones will still complete)
                for f in future_to_idx:
                    f.cancel()
                break
            results[idx] = df

    if failed:
        return None

    # Concatenate in chronological order (by window index = submission order)
    frames = [results[i] for i in sorted(results) if not results[i].empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def bulk_eod(root: str, exp: int | str | date, start_date: date | str | int,
             end_date: date | str | int) -> pd.DataFrame | None:
    """EOD option chain data for all strikes of a given root+expiry, over a date range.

    Endpoint: GET /v3/option/history/eod
    v3 params: symbol=ROOT, expiration=YYYYMMDD|"*", start_date=YYYYMMDD, end_date=YYYYMMDD

    STALL FIX: when expiration="*" (or exp=0), pulls in ≤7-day windows via
    ThreadPoolExecutor(max_workers=6).  Per-window retry: up to 2 retries with 5s/15s
    backoff.  Any window's final failure → returns None (no partial DataFrame).
    Deterministic ordering: windows sorted by date after concurrent gather.

    Contrast with /history/greeks/eod: that endpoint rejects multi-day wildcard (HTTP 400)
    so bulk_greeks uses day-by-day (also concurrent).

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

    if exp_param == "*":
        # STALL FIX: iterate in ≤WINDOW_DAYS windows concurrently.
        # Each window issues one wildcard request (short ranges measured reliable 2026-07-05).
        base_params = {
            "symbol": root.upper(),
            "expiration": "*",
        }
        df = _concurrent_windows(
            "/v3/option/history/eod", base_params, start_date, end_date, root=root)
        if df is None:
            log.warning("thetadata: bulk_eod(%s, *, %s→%s) failed — returning None",
                        root, start_date, end_date)
            return None
        if df.empty:
            return pd.DataFrame()
    else:
        # Specific expiration: single-request range (no stall risk for specific-exp).
        params = {
            "symbol": root.upper(),
            "expiration": exp_param,
            "start_date": _date_int(start_date),
            "end_date": _date_int(end_date),
        }
        session = _session()
        try:
            df = _get_csv(session, "/v3/option/history/eod", params)
        except _StreamTruncated as e:
            log.warning("thetadata: bulk_eod(%s, %s, start=%s, end=%s) truncated — "
                        "returning None: %s", root, exp_param, start_date, end_date, e)
            return None
        if df is None:
            log.warning("thetadata: bulk_eod(%s, %s) failed — returning None", root, exp_param)
            return None
        if df.empty:
            return pd.DataFrame()

    return _normalize_eod_df(df, root)


def _normalize_eod_df(df: pd.DataFrame, root: str) -> pd.DataFrame:
    """Normalize a raw v3 EOD CSV DataFrame into the canonical output schema.

    API DEDUP (2026-07-05): The ThetaData v3 API, for wildcard-expiration EOD
    requests, returns each non-expiration-day contract record TWICE within the
    same response.  Contracts on their expiration day appear once (correct);
    all other trading-day rows are duplicated byte-for-byte.  Observed: SPY 2018
    eod returned 2,699,538 rows — 1,191,752 byte-identical full-row duplicates
    (44%); unique (root, expiration, strike, right, date) keys = 1,507,786.
    Root cause is in the API response, not the writer (SPY 2018 was written
    exactly once; the log confirms a single pull_root_year call).

    Fix: full-row drop_duplicates applied here, before the DataFrame is returned
    to the caller.  Any dup count > 0 is logged at INFO so it appears in the
    backfill log for observability without being noisy on clean responses.
    """
    if df.empty:
        return df

    # Strip quotes from string columns (CSV may include surrounding quotes)
    for col in ("symbol", "expiration", "right"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip('"').str.strip()

    # Derive the trading date from last_trade (the timestamp of the last fill on that day),
    # falling back to created (ingest timestamp) only if last_trade is absent.
    # Do NOT use created: it records when ThetaData ingested the record (often T+1 or later),
    # not the trading date.  last_trade is point-in-time-safe (set at market close that day).
    if "_date" in df.columns:
        df["date"] = pd.to_datetime(df["_date"])
        df = df.drop(columns=["_date"])
    elif "last_trade" in df.columns:
        df["date"] = pd.to_datetime(df["last_trade"], errors="coerce").dt.normalize()
    elif "created" in df.columns:
        # Fallback: created is the ingest timestamp (T+1 or later); use only when
        # last_trade is absent (older API responses or future schema changes).
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
    df = df[available].reset_index(drop=True)

    # API dedup: drop full-row duplicates introduced by the ThetaData v3 API
    # (see docstring).  Applied after column selection so the comparison covers
    # exactly the columns that will be written to parquet.
    n_before = len(df)
    df = df.drop_duplicates()
    n_dropped = n_before - len(df)
    if n_dropped > 0:
        log.info(
            "thetadata: _normalize_eod_df(%s) dropped %d full-row API duplicates "
            "(%d → %d rows)",
            root, n_dropped, n_before, len(df),
        )

    return df.reset_index(drop=True)


def bulk_open_interest(root: str, exp: int | str | date, start_date: date | str | int,
                       end_date: date | str | int) -> pd.DataFrame | None:
    """Open interest for all contracts of a given root+expiry over a date range.

    Endpoint: GET /v3/option/history/open_interest  (bulk; wildcard supported)

    STALL FIX: when exp="*" (or exp=0), pulls in ≤7-day windows via
    ThreadPoolExecutor(max_workers=6).  Per-window retry + no-partial law same as bulk_eod.

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

    if exp_param == "*":
        # STALL FIX: iterate in ≤WINDOW_DAYS windows concurrently.
        base_params = {
            "symbol": root.upper(),
            "expiration": "*",
        }
        df = _concurrent_windows(
            "/v3/option/history/open_interest", base_params, start_date, end_date, root=root)
        if df is None:
            log.warning(
                "thetadata: bulk_open_interest(%s, *, %s→%s) failed — returning None",
                root, start_date, end_date)
            return None
        if df.empty:
            return pd.DataFrame()
    else:
        params = {
            "symbol": root.upper(),
            "expiration": exp_param,
            "start_date": _date_int(start_date),
            "end_date": _date_int(end_date),
        }
        session = _session()
        try:
            df = _get_csv(session, "/v3/option/history/open_interest", params)
        except _StreamTruncated as e:
            log.warning("thetadata: bulk_open_interest(%s, %s, start=%s, end=%s) truncated — "
                        "returning None: %s", root, exp_param, start_date, end_date, e)
            return None
        if df is None:
            log.warning("thetadata: bulk_open_interest(%s, %s) failed — returning None",
                        root, exp_param)
            return None
        if df.empty:
            return pd.DataFrame()

    return _normalize_oi_df(df)


def _normalize_oi_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize raw v3 OI CSV DataFrame.

    API DEDUP (2026-07-07): wildcard-expiration OI pulls exhibit the same v3 API
    duplication as EOD (see _normalize_eod_df docstring) — each contract record can
    appear twice byte-for-byte in the response.  Observed in-store before this fix:
    SPY oi 9,692 full-row dups, QQQ 6,448, IWM 5,190 (repaired on disk via
    scripts/repair_thetadata_dedup --apply).  The 2026-07-05 fix covered only the
    EOD path; this applies the same full-row drop_duplicates here.
    """
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
    df = df[available].reset_index(drop=True)

    # API dedup: drop full-row duplicates introduced by the ThetaData v3 API
    # (see docstring).  Applied after column selection so the comparison covers
    # exactly the columns that will be written to parquet.
    n_before = len(df)
    df = df.drop_duplicates()
    n_dropped = n_before - len(df)
    if n_dropped > 0:
        log.info(
            "thetadata: _normalize_oi_df dropped %d full-row API duplicates "
            "(%d → %d rows)",
            n_dropped, n_before, len(df),
        )

    return df.reset_index(drop=True)


def bulk_greeks(root: str, exp: int | str | date, start_date: date | str | int,
                end_date: date | str | int, *, order: int = 1) -> pd.DataFrame | None:
    """Greeks for all contracts of a given root+expiry, one row per contract per day (EOD).

    Endpoint: GET /v3/option/history/greeks/eod  (all orders in one buffered response)
    v3 behavior (measured 2026-07-04): /greeks/eod returns one row per contract per
    trading day with all greek orders + OHLCV + implied_vol + underlying_price.
    This is the correct EOD endpoint; /greeks/all streams 1-second snapshots and has
    no usable interval parameter for multi-day bulk pulls.

    WILDCARD EXPIRATION + CONCURRENCY: exp=0 / exp="*" iterates day-by-day (API enforces
    start_date == end_date for greeks/eod wildcard: HTTP 400 on multi-day).
    Days are pulled concurrently via ThreadPoolExecutor(max_workers=WINDOW_WORKERS).
    Per-day retry: up to WINDOW_MAX_RETRIES retries with WINDOW_RETRY_BACKOFF backoff.
    Any day's final failure → whole call returns None (no partial).

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

    if exp_param == "*":
        # greeks/eod rejects multi-day wildcard (HTTP 400: "When expiration=*, you must
        # request data a day-at-a-time").  Use 1-day windows so each request has
        # start_date == end_date, satisfying the API constraint.
        # Concurrency + retry are handled by _concurrent_windows with window_days=1.
        base_params = {
            "symbol": root.upper(),
            "expiration": "*",
        }
        df = _concurrent_windows(
            "/v3/option/history/greeks/eod", base_params, start_date, end_date,
            root=root, window_days=1)
        if df is None:
            log.warning(
                "thetadata: bulk_greeks(%s, exp=*, %s→%s, order=%d) failed — returning None",
                root, start_date, end_date, order)
            return None
        if df.empty:
            return pd.DataFrame()
    else:
        params = {
            "symbol": root.upper(),
            "expiration": exp_param,
            "start_date": _date_int(start_date),
            "end_date": _date_int(end_date),
        }
        session = _session()
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

    return _normalize_greeks_df(df, order=order)


def _normalize_greeks_df(df: pd.DataFrame, *, order: int = 1) -> pd.DataFrame:
    """Normalize a raw v3 greeks/eod CSV DataFrame (column slice per order=).

    API DEDUP (2026-07-07): same v3 API full-row duplication as EOD and OI
    (see _normalize_eod_df docstring); the same drop_duplicates is applied here
    after column selection.
    """
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
    df = df[available].reset_index(drop=True)

    # API dedup: drop full-row duplicates introduced by the ThetaData v3 API
    # (see docstring).  Applied after column selection so the comparison covers
    # exactly the columns that will be written to parquet.
    n_before = len(df)
    df = df.drop_duplicates()
    n_dropped = n_before - len(df)
    if n_dropped > 0:
        log.info(
            "thetadata: _normalize_greeks_df dropped %d full-row API duplicates "
            "(%d → %d rows)",
            n_dropped, n_before, len(df),
        )

    return df.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Snapshot API — U-CHAIN intraday lane (measured live 2026-07-16)
# --------------------------------------------------------------------------- #

# Column subsets kept per snapshot endpoint (beyond the contract key + snapshot_ts).
# second_order also returns implied_vol/iv_error/bid/ask/underlying_price — kept here
# so each frame stands alone; the chain_snapshot_poller joins only the second-order
# greek columns onto the first-order base.
_SNAPSHOT_KEEP_COLS = {
    "first":  ["bid", "ask", "delta", "theta", "vega", "rho", "epsilon", "lambda",
               "implied_vol", "iv_error", "underlying_price"],
    "second": ["bid", "ask", "gamma", "vanna", "charm", "vomma", "veta",
               "implied_vol", "iv_error", "underlying_price"],
}


def _normalize_snapshot_df(df: pd.DataFrame, keep_cols: list[str],
                           label: str) -> pd.DataFrame:
    """Normalize a raw v3 snapshot CSV DataFrame (greeks or open_interest).

    Column selection is by NAME, never by position: the OI snapshot header leads
    with timestamp while the greeks snapshots lead with symbol (both measured
    verbatim 2026-07-16 — see module docstring).

    snapshot_ts is parsed from the response 'timestamp' column (the terminal's
    per-contract quote timestamp; the OI snapshot stamp is ~06:30 ET, when OPRA
    publishes EOD t-1 positions).

    API DEDUP: the same full-row drop_duplicates law as the history endpoints
    (see _normalize_eod_df docstring) is applied after column selection.
    """
    if df.empty:
        return df

    for col in ("symbol", "expiration", "right"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip('"').str.strip()

    # snapshot_ts from the response timestamp (never the wall clock)
    if "timestamp" in df.columns:
        df["snapshot_ts"] = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        df["snapshot_ts"] = pd.NaT

    if "expiration" in df.columns:
        df["expiration"] = pd.to_datetime(df["expiration"], errors="coerce")

    if "right" in df.columns:
        df["right"] = df["right"].map({"CALL": "C", "PUT": "P"}).fillna(df["right"])

    if "strike" in df.columns:
        df["strike"] = pd.to_numeric(df["strike"], errors="coerce")

    for col in keep_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "symbol" in df.columns:
        df = df.rename(columns={"symbol": "root"})

    keep = ["root", "expiration", "strike", "right", "snapshot_ts"] + keep_cols
    available = [c for c in keep if c in df.columns]
    df = df[available].reset_index(drop=True)

    # API dedup: drop full-row duplicates (same v3 API law as EOD/OI/greeks).
    n_before = len(df)
    df = df.drop_duplicates()
    n_dropped = n_before - len(df)
    if n_dropped > 0:
        log.info(
            "thetadata: _normalize_snapshot_df(%s) dropped %d full-row API duplicates "
            "(%d → %d rows)",
            label, n_dropped, n_before, len(df),
        )

    return df.reset_index(drop=True)


def _snapshot_get(root: str, path: str, keep_cols: list[str],
                  label: str) -> pd.DataFrame | None:
    """Shared fetch+normalize for the snapshot endpoints.

    NO reachable() pre-check (deliberate deviation from the bulk_* helpers):
    reachable() downloads the full 15,636-root symbol list (~0.5s) per call,
    which would roughly double a 150-root sweep at max_concurrent=1.  The
    INERT contract is preserved by _get_csv's error paths (unreachable /
    non-200 / truncated → one WARNING, return None); the chain_snapshot_poller
    probes reachable() once at startup instead.
    """
    params = {"symbol": root.upper(), "expiration": "*", "strike": "*"}
    session = _session()
    try:
        df = _get_csv(session, path, params)
    except _StreamTruncated as e:
        log.warning("thetadata: %s(%s) truncated — returning None: %s", label, root, e)
        return None
    if df is None:
        log.warning("thetadata: %s(%s) failed — returning None", label, root)
        return None
    if df.empty:
        return pd.DataFrame()
    return _normalize_snapshot_df(df, keep_cols=keep_cols, label=label)


def snapshot_greeks(root: str, order: str = "first") -> pd.DataFrame | None:
    """Live full-chain greeks snapshot for one root (U-CHAIN lane).

    Endpoint: GET /v3/option/snapshot/greeks/{first,second}_order
    v3 params: symbol=ROOT, expiration=*, strike=*  (wildcards ACCEPTED on
    snapshots, unlike /history/greeks/* — measured 2026-07-16: full SPY chain
    14,065 rows in 0.96s first-order, 0.83s second-order).

    order="first"  → delta, theta, vega, rho, epsilon, lambda, implied_vol,
                     iv_error (+ bid, ask, underlying_price)
    order="second" → gamma, vanna, charm, vomma, veta (+ bid, ask,
                     implied_vol, iv_error, underlying_price)

    Market closed → the terminal returns last-known close-ish values (still
    structurally valid; timestamps carry the truth).

    Returns DataFrame: root, expiration (datetime64), strike (float, $),
    right ("C"/"P"), snapshot_ts (datetime64, from response timestamps),
    [value columns per order] — or None on any terminal error (INERT).
    """
    if order not in ("first", "second"):
        raise ValueError(f"order must be 'first' or 'second'; got {order!r}")
    return _snapshot_get(
        root,
        f"/v3/option/snapshot/greeks/{order}_order",
        keep_cols=_SNAPSHOT_KEEP_COLS[order],
        label=f"snapshot_greeks/{order}",
    )


def snapshot_open_interest(root: str) -> pd.DataFrame | None:
    """Live full-chain open-interest snapshot for one root (U-CHAIN lane).

    Endpoint: GET /v3/option/snapshot/open_interest (expiration=*, strike=*).
    Measured 2026-07-16: full SPY chain 13,731 rows in 0.21s.

    OI TIMING LAW: the snapshot is stamped ~06:30 ET, when OPRA publishes OI —
    the value represents END-OF-PREVIOUS-DAY positions and does NOT update
    intraday.  One pull per root per day is sufficient; same-day OI in a day-t
    feature is a data leak (see the module docstring).

    Returns DataFrame: root, expiration (datetime64), strike (float, $),
    right ("C"/"P"), snapshot_ts (datetime64), open_interest (numeric)
    — or None on any terminal error (INERT).
    """
    return _snapshot_get(
        root,
        "/v3/option/snapshot/open_interest",
        keep_cols=["open_interest"],
        label="snapshot_open_interest",
    )


def bulk_trade_quote_day(root: str, target_date: date | str | int) -> pd.DataFrame | None:
    """Convenience wrapper: pull BOTH call + put legs for one root, one trading day.

    Calls bulk_trade_quote() twice (right=call, right=put), concatenates into one DataFrame.
    No-partial contract: if either leg fails (None), returns None.
    Both empty → empty DataFrame (valid: holiday or no options traded for this root).

    Ratified shape (T2A_THROUGHPUT_PROBE.md §7):
      • wildcard expiration + strike (exp=*, strike=*)
      • single-day only (multi-day wildcard → HTTP 400)
      • 2 API requests per root-day total

    Returns a DataFrame with columns:
      root, expiration, strike (float, $), right ("C"/"P"), trade_timestamp,
      date, sequence, price, size, bid, ask, exchange
    or None if the terminal is unreachable or either leg errors.
    """
    if not reachable():
        log.warning("thetadata: terminal not reachable — bulk_trade_quote_day returning None")
        return None

    frames: list[pd.DataFrame] = []
    for right_str in ("call", "put"):
        df = bulk_trade_quote(root, right_str, target_date, target_date)
        if df is None:
            log.warning(
                "thetadata: bulk_trade_quote_day(%s, %s) %s leg failed — returning None",
                root, target_date, right_str)
            return None
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _normalize_trade_quote_df(df: pd.DataFrame, root: str) -> pd.DataFrame:
    """Normalize a raw v3 trade_quote CSV DataFrame into the canonical bulk-tape schema.

    v3 CSV columns:
      symbol, expiration, strike, right, trade_timestamp, quote_timestamp,
      sequence, ext_condition1..4, condition, size, exchange,
      price, bid_size, bid_exchange, bid, bid_condition,
      ask_size, ask_exchange, ask, ask_condition

    Output columns (typed):
      root (str), expiration (datetime64), strike (float, $), right ("C"/"P"),
      trade_timestamp (str, ISO-like), price (float), size (float), bid (float), ask (float)
    """
    if df.empty:
        return df

    for col in ("symbol", "expiration", "right"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip('"').str.strip()

    # Rename symbol → root
    if "symbol" in df.columns:
        df = df.rename(columns={"symbol": "root"})
    else:
        df["root"] = root.upper()

    # Parse expiration
    if "expiration" in df.columns:
        df["expiration"] = pd.to_datetime(df["expiration"], errors="coerce")

    # Normalize right: "CALL" → "C", "PUT" → "P"
    if "right" in df.columns:
        df["right"] = df["right"].map({"CALL": "C", "PUT": "P"}).fillna(df["right"])

    # Numeric columns
    for col in ("strike", "price", "size", "bid", "ask"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    keep = ["root", "expiration", "strike", "right",
            "trade_timestamp", "price", "size", "bid", "ask"]
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


def _time_to_str(t: str | int | None) -> str | None:
    """Convert a time-of-day value to "HH:MM:SS.000" string (v3 API convention).

    Accepts:
      - None           → None (param omitted)
      - int            → treated as ms-of-day; converted to HH:MM:SS.mmm
      - "HH:MM:SS"     → normalised to "HH:MM:SS.000"
      - "HH:MM"        → normalised to "HH:MM:00.000"
      - "HH:MM:SS.mmm" → passed through as-is

    The v3 trade_quote endpoint expects start_time / end_time as "HH:MM:SS.mmm" ET.
    """
    if t is None:
        return None
    if isinstance(t, int):
        # ms-of-day → HH:MM:SS.mmm
        total_ms = int(t)
        h  =  total_ms // 3_600_000
        m  = (total_ms % 3_600_000) // 60_000
        s  = (total_ms % 60_000) // 1_000
        ms =  total_ms % 1_000
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
    parts = str(t).split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    sec_parts = parts[2].split(".") if len(parts) > 2 else ["0", "000"]
    s   = int(sec_parts[0])
    ms  = int(sec_parts[1]) if len(sec_parts) > 1 else 0
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


# Keep an alias for the old name used in tests
def _time_to_ms(t: str | int | None) -> str | int | None:
    """Alias for _time_to_str (kept for test compatibility).

    Returns the v3 time string; also accepts int ms-of-day for backwards compat.
    """
    return _time_to_str(t)


def bulk_trade_quote(root: str, right: str,
                     start_date: date | str | int,
                     end_date: date | str | int,
                     start_time: str | int | None = None,
                     end_time: str | int | None = None,
                     near_dte_cap_days: int | None = None) -> pd.DataFrame | None:
    """Full-chain trade+NBBO for ONE right (call or put) on a date range.

    Endpoint: GET /v3/option/history/trade_quote with expiration=* and strike=*.

    Live probe (2026-07-04): wildcard expiration AND strike are accepted when
    right is explicitly "call" or "put". Wildcard right= returns HTTP 400.
    Two calls per root-day (one per right) cover the entire chain.

    This is the T2a aggregate-then-discard path. Raw rows should be discarded
    by the caller after aggregation.

    Returns a DataFrame with the same schema as trade_quote() EXCEPT that
    strike is not fixed (it varies per contract in the response). The 'strike'
    column is parsed from the response CSV (each row has its own strike).
    The 'sequence' column is included in the output for dedup / watermark use.

    Optional time-of-day filtering (v3 format "HH:MM:SS.mmm" ET):
      start_time : "HH:MM:SS", "HH:MM:SS.mmm", "HH:MM", or ms-of-day int.
                   If provided, only trades at or after this time are returned.
      end_time   : same formats.  If provided, only trades at or before this
                   time are returned.
    Behavior is identical to the no-params call when both are None (additive).

    near_dte_cap_days:
      Only used on the current-day fallback path (when the wildcard expiration
      request is rejected with "specifying an expiration" for today's date).
      If set, limits per-expiration pulls to expirations where
      exp_date <= target_date + timedelta(days=near_dte_cap_days).
      None means no cap (all unexpired expirations are fetched).

    Returns None on terminal error; empty DataFrame if no trades exist.
    """
    if not reachable():
        log.warning("thetadata: terminal not reachable — bulk_trade_quote returning None")
        return None

    right_norm = _normalize_right_request(right)   # "call" or "put"
    params: dict = {
        "symbol": root.upper(),
        "expiration": "*",
        "strike": "*",
        "right": right_norm,
        "start_date": _date_int(start_date),
        "end_date": _date_int(end_date),
    }
    st_str = _time_to_str(start_time)
    et_str = _time_to_str(end_time)
    if st_str is not None:
        params["start_time"] = st_str
    if et_str is not None:
        params["end_time"] = et_str

    session = _session()
    rows_all: list[dict] = []

    # CSV header: symbol,expiration,strike,right,trade_timestamp,quote_timestamp,
    #             sequence,ext_condition1-4,condition,size,exchange,price,
    #             bid_size,bid_exchange,bid,bid_condition,ask_size,ask_exchange,ask,ask_condition
    # Indices:    0       1           2      3     4                5
    #             6       7-10        11     12    13       14
    #             15      16          17     18    19       20      21    22

    def _parse_rows(stream_iter) -> list[dict]:
        """Parse a _stream_lines iterator into row dicts. Raises _StreamTruncated on error."""
        rows: list[dict] = []
        for raw_line in stream_iter:
            if isinstance(raw_line, bytes):
                line = raw_line.decode("utf-8", errors="replace")
            else:
                line = raw_line
            line = line.strip()
            if not line:
                continue
            if line.startswith("symbol,"):
                continue
            parts = [v.strip().strip('"') for v in line.split(",")]
            if len(parts) < 23:
                continue
            rows.append({
                "date":            parts[4][:10] if parts[4] else None,
                "trade_timestamp": parts[4],
                "quote_timestamp": parts[5],
                "sequence":        parts[6],
                "expiration":      parts[1],
                "strike":          parts[2],
                "right":           parts[3],
                "price":           parts[14],
                "size":            parts[12],
                "exchange":        parts[13],
                "bid":             parts[17],
                "ask":             parts[21],
            })
        return rows

    def _build_df(rows: list[dict]) -> pd.DataFrame:
        """Coerce row dicts to the canonical bulk_trade_quote output DataFrame."""
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df["date"]     = pd.to_datetime(df["date"], errors="coerce")
        df["price"]    = pd.to_numeric(df["price"],    errors="coerce")
        df["size"]     = pd.to_numeric(df["size"],     errors="coerce")
        df["bid"]      = pd.to_numeric(df["bid"],      errors="coerce")
        df["ask"]      = pd.to_numeric(df["ask"],      errors="coerce")
        df["strike"]   = pd.to_numeric(df["strike"],   errors="coerce")
        df["sequence"] = pd.to_numeric(df["sequence"], errors="coerce")
        df["right"]    = df["right"].str.upper().str[:1]   # "CALL"→"C", "PUT"→"P"
        df["root"]     = root.upper()
        return df.reset_index(drop=True)

    try:
        rows_all = _parse_rows(
            _stream_lines(session, "/v3/option/history/trade_quote", params)
        )
    except _StreamTruncated as e:
        err_str = str(e).lower()
        if "specifying an expiration" in err_str:
            # Current-day wildcard rejected — fall back to per-expiration loop.
            return _bulk_trade_quote_per_exp(
                root=root, right=right_norm,
                start_date=start_date, end_date=end_date,
                st_str=st_str, et_str=et_str,
                near_dte_cap_days=near_dte_cap_days,
                parse_rows=_parse_rows,
                build_df=_build_df,
            )
        log.warning(
            "thetadata: bulk_trade_quote(%s, %s, %s→%s) truncated — returning None: %s",
            root, right, start_date, end_date, e)
        return None

    return _build_df(rows_all)


def _bulk_trade_quote_per_exp(
    root: str, right: str,
    start_date, end_date,
    st_str: str | None, et_str: str | None,
    near_dte_cap_days: int | None,
    parse_rows,
    build_df,
) -> pd.DataFrame | None:
    """Per-expiration fallback for current-day bulk_trade_quote.

    Used when the wildcard expiration request is rejected by ThetaData v3 for
    the current calendar day ("Cannot fetch current-day data without specifying
    an expiration").  Fetches each unexpired expiration individually.

    SEQUENTIAL (no ThreadPoolExecutor) — the poller owns concurrency, capped at
    2 by a HARD LAW.
    """
    target_date = _parse_date_int(start_date)  # always single-day for this path
    cap_date = (target_date + timedelta(days=near_dte_cap_days)
                if near_dte_cap_days is not None else None)

    exps = list_expirations(root)
    if exps is None:
        log.warning(
            "thetadata: bulk_trade_quote per-exp fallback — list_expirations(%s) failed,"
            " returning None", root)
        return None

    # Filter: keep only unexpired expirations within the DTE cap
    filtered: list[str] = []
    for exp_iso in exps:
        try:
            exp_date = date.fromisoformat(exp_iso)
        except ValueError:
            continue
        if exp_date < target_date:
            continue
        if cap_date is not None and exp_date > cap_date:
            continue
        filtered.append(exp_iso)

    session = _session()
    all_rows: list[dict] = []
    failed_count = 0

    for exp_iso in filtered:
        exp_int = _date_int(exp_iso)
        per_params: dict = {
            "symbol": root.upper(),
            "expiration": exp_int,
            "strike": "*",
            "right": right,
            "start_date": _date_int(start_date),
            "end_date": _date_int(end_date),
        }
        if st_str is not None:
            per_params["start_time"] = st_str
        if et_str is not None:
            per_params["end_time"] = et_str

        try:
            rows = parse_rows(
                _stream_lines(session, "/v3/option/history/trade_quote", per_params)
            )
            all_rows.extend(rows)
        except _StreamTruncated as e:
            log.warning(
                "thetadata: bulk_trade_quote per-exp fallback — exp %s failed, skipping: %s",
                exp_iso, e)
            failed_count += 1

    dte_label = f"<={near_dte_cap_days}" if near_dte_cap_days is not None else "all"
    log.info(
        "thetadata: bulk_trade_quote current-day fallback %s %s — %d expirations (%s DTE),"
        " %d rows", root, right, len(filtered), dte_label, len(all_rows))

    if failed_count == len(filtered) and not all_rows:
        log.warning(
            "thetadata: bulk_trade_quote per-exp fallback — ALL %d expirations failed"
            " for %s %s, returning None", len(filtered), root, right)
        return None

    return build_df(all_rows)
