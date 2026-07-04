"""collectors/thetadata.py — thin client for the local ThetaData Terminal REST API.

ThetaData works via a local Java process ("Theta Terminal") that exposes a REST API on
localhost.  Our job is purely to call that API and return normalized DataFrames; all option
pricing, signing, and analytics live in engine/.

CONTRACT (same spirit as collectors/databento_tbbo.py and collectors/massive_flatfiles.py)
---------------------------------------------------------------------------
INERT when the terminal is unreachable:
  • Terminal unreachable / non-200 / malformed response → log one WARNING, return None or an
    empty DataFrame.  NEVER raise into a build.
  • Short connect timeout (CONNECT_TIMEOUT = 2s) for the reachability check.
  • Generous read timeout (READ_TIMEOUT = 120s) for bulk pulls that may return many pages.

API topology (documented at https://http-docs.thetadata.us, probed 2026-07-04):
  Base URL: http://127.0.0.1:25510  (override via THETA_TERMINAL_URL env)
  Version:  v2 (stable; v3 is beta)
  Runs on:  the same Mac as the nightly collectors; started by scripts/run_theta_terminal.sh

Strike format (verified from docs):
  The API uses INTEGER strike values in **units of 1/10th of a cent** (i.e. 1000× the dollar
  price).  Example: $170.00 strike → 170000.  Documented at
  https://http-docs.thetadata.us/operations/get-hist-option-trade_quote.html.
  → We normalize to float dollars in all output DataFrames by dividing by 1000.0.
  Source: "strike": integer, "Strike in 1/10th cent (e.g., $170.00 = 170000)."

Date format:
  All date parameters are YYYYMMDD integers.  Output DataFrames carry a 'date' column
  typed datetime64[ns] (UTC midnight).

Pagination (documented at https://http-docs.thetadata.us/Articles/Performance-And-Tuning/
  Pagination.html):
  • JSON responses: header["next_page"] is a full URL string when more pages exist,
    or the string "null" (or Python None) on the last page.
  • CSV responses: "Next-Page" HTTP response header.
  • We use JSON (use_csv=False) and follow header["next_page"] transparently.
  • Pages expire quickly (HTTP_PAGE_EXPIRE ms) — follow sequentially without sleeping.

Error codes (subset; full list at /Articles/Data-And-Requests/Values/Error-Codes.html):
  200 OK, 471 PERMISSION, 472 NO_DATA, 473 INVALID_PARAMS, 474 DISCONNECTED,
  477 NO_PAGE_FOUND (expired page; retry the original request), 570 LARGE_REQUEST.

Endpoints implemented:
  GET /v2/bulk_hist/option/eod      → bulk_eod()
  GET /v2/bulk_hist/option/         → (OI uses /v2/hist/option/open_interest per-contract;
                                       no bulk OI endpoint found in v2 docs)
  GET /v2/bulk_hist/option/greeks   → bulk_greeks() (first-order; IV included in response)
  GET /v2/bulk_hist/option/second_order_greeks → bulk_greeks(order=2)
  GET /v2/bulk_hist/option/third_order_greeks  → bulk_greeks(order=3)
  GET /v2/hist/option/trade_quote   → trade_quote() (per-contract; no bulk endpoint)
  GET /v2/hist/option/open_interest → _hist_oi()  (per-contract; called by bulk_open_interest)

AMBIGUITIES (to probe after subscription activates — see research/THETADATA_PROBE.md):
  • bulk_hist/option/open_interest: not confirmed in v2 docs; the docs show only
    /v2/hist/option/open_interest (per-contract).  bulk_open_interest() calls the per-contract
    endpoint across a contract list — this is likely the correct pattern; verify at probe time.
  • SPX vs SPXW: SPX (AM-settled) and SPXW (PM-settled weekly) may be separate roots.
    The backfill driver accepts both; probe which root carries weekly liquidity.
  • third_order_greeks endpoint: docs confirmed it exists; exact path not verified (using
    the canonical bulk pattern /v2/bulk_hist/option/third_order_greeks).
  • IV as separate endpoint: /v2/hist/option/implied_volatility exists per docs, but
    first-order greeks already carry implied_vol in the response array.  We use greeks.
  • Open-interest update timing: docs say "reported once per day by OPRA at approximately
    06:30 ET and represents end-of-previous-day figures."  This means OI[t] from OPRA
    corresponds to positions as of EOD t-1 — use OI[t-1] in any day-t signal.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime
from typing import Iterator

import pandas as pd
import requests

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Config / connectivity
# --------------------------------------------------------------------------- #

CONNECT_TIMEOUT = 2       # seconds — fast reachability check
READ_TIMEOUT = 120        # seconds — bulk pulls over many expiries can be slow

# Strike divisor: API integers are in 1/10th-cent units; divide by 1000 to get dollar price.
# Source: https://http-docs.thetadata.us/operations/get-hist-option-trade_quote.html
STRIKE_DIVISOR = 1000.0

# Second/third order greek endpoint suffixes (exact path validated at probe time)
_GREEKS_ENDPOINTS = {
    1: "greeks",
    2: "second_order_greeks",
    3: "third_order_greeks",
}


def _base_url() -> str:
    return os.environ.get("THETA_TERMINAL_URL", "http://127.0.0.1:25510").rstrip("/")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["Accept"] = "application/json"
    return s


def reachable() -> bool:
    """Quick check: can we GET the terminal root within CONNECT_TIMEOUT seconds?"""
    try:
        r = requests.get(f"{_base_url()}/v2/list/roots/option",
                         timeout=CONNECT_TIMEOUT, params={"use_csv": "false"})
        return r.status_code in (200, 472)   # 472 = no_data is still a live terminal
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# Low-level HTTP helpers
# --------------------------------------------------------------------------- #

def _get(session: requests.Session, path: str, params: dict) -> dict | None:
    """One JSON GET, logging non-200s as warnings (no raise). Returns parsed dict or None."""
    url = f"{_base_url()}{path}"
    try:
        r = session.get(url, params=params, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
    except requests.exceptions.ConnectionError:
        log.warning("thetadata: terminal unreachable at %s — skip", _base_url())
        return None
    except Exception as e:  # noqa: BLE001
        log.warning("thetadata: request error %s %s — %s", path, params, e)
        return None
    if r.status_code == 472:       # NO_DATA: valid response, just empty
        return {"header": {"next_page": "null"}, "response": []}
    if r.status_code == 471:
        log.warning("thetadata: PERMISSION error (471) for %s — subscription not active?", path)
        return None
    if r.status_code != 200:
        log.warning("thetadata: HTTP %d for %s %s — skip", r.status_code, path, params)
        return None
    try:
        return r.json()
    except Exception as e:  # noqa: BLE001
        log.warning("thetadata: malformed JSON from %s: %s", path, e)
        return None


def _paginate(session: requests.Session, path: str, params: dict) -> Iterator[list]:
    """Yield response rows across all pages, following header["next_page"] until exhausted.

    Pagination mechanics (from docs): header["next_page"] is a full URL string when more
    pages exist, or the string "null" / Python None on the final page.  Pages expire quickly
    so we follow sequentially without sleeping between requests.
    """
    data = _get(session, path, params)
    if data is None:
        return
    rows = data.get("response") or []
    if rows:
        yield rows
    # Follow next_page until "null"
    header = data.get("header") or {}
    next_url = header.get("next_page")
    while next_url and str(next_url).lower() != "null":
        # next_page is a full URL like http://127.0.0.1:25510/v2/page/1
        try:
            r = session.get(next_url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        except Exception as e:  # noqa: BLE001
            log.warning("thetadata: pagination fetch error: %s", e)
            break
        if r.status_code == 477:
            log.warning("thetadata: page expired (477) — pagination truncated")
            break
        if r.status_code != 200:
            log.warning("thetadata: pagination HTTP %d — stopping", r.status_code)
            break
        try:
            data = r.json()
        except Exception as e:  # noqa: BLE001
            log.warning("thetadata: pagination JSON parse error: %s", e)
            break
        rows = data.get("response") or []
        if rows:
            yield rows
        header = data.get("header") or {}
        next_url = header.get("next_page")


def _date_int(d: date | str | int) -> int:
    """Normalize date to YYYYMMDD integer for API params."""
    if isinstance(d, int):
        return d
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return int(d.strftime("%Y%m%d"))


def _to_date(val) -> pd.Timestamp | None:
    """YYYYMMDD int or string -> pandas Timestamp (UTC midnight). None on failure."""
    try:
        s = str(int(val))
        return pd.Timestamp(datetime.strptime(s, "%Y%m%d"))
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def bulk_eod(root: str, exp: int | str | date, start_date: date | str | int,
             end_date: date | str | int) -> pd.DataFrame | None:
    """EOD option chain data for all strikes of a given root+expiry, over a date range.

    Endpoint: GET /v2/bulk_hist/option/eod
    Documented response tick fields (per contract, per date):
      [ms_of_day, ms_of_day2, open, high, low, close, volume, count,
       bid_size, bid_exchange, bid, bid_condition,
       ask_size, ask_exchange, ask, ask_condition, date]

    Strike in output: float dollars (API integer / 1000.0).
    Pass exp=0 to retrieve all expiries for a root (day-by-day; slower).

    Returns a DataFrame with columns:
      root, expiration (datetime64), strike (float, $), right (C/P),
      date (datetime64), open, high, low, close, volume, count, bid, ask
    or None if the terminal is unreachable or returns a permission error.
    """
    if not reachable():
        log.warning("thetadata: terminal not reachable — bulk_eod returning None")
        return None
    params = {
        "root": root.upper(),
        "exp": _date_int(exp) if exp != 0 else 0,
        "start_date": _date_int(start_date),
        "end_date": _date_int(end_date),
        "use_csv": "false",
    }
    session = _session()
    rows_all: list[dict] = []
    for page_rows in _paginate(session, "/v2/bulk_hist/option/eod", params):
        # Each page_rows is a list of contract objects: {"ticks": [...], "contract": {...}}
        for contract_obj in page_rows:
            contract = contract_obj.get("contract", {})
            root_val = contract.get("root", root)
            exp_val = _to_date(contract.get("expiration"))
            strike_val = (contract.get("strike") or 0) / STRIKE_DIVISOR
            right_val = contract.get("right")
            for tick in (contract_obj.get("ticks") or []):
                if len(tick) < 17:
                    continue
                rows_all.append({
                    "root": root_val,
                    "expiration": exp_val,
                    "strike": strike_val,
                    "right": right_val,
                    "date": _to_date(tick[16]),
                    "open": tick[2],
                    "high": tick[3],
                    "low": tick[4],
                    "close": tick[5],
                    "volume": tick[6],
                    "count": tick[7],
                    "bid": tick[10],
                    "ask": tick[14],
                })
    if not rows_all:
        return pd.DataFrame()
    df = pd.DataFrame(rows_all)
    df["date"] = pd.to_datetime(df["date"])
    df["expiration"] = pd.to_datetime(df["expiration"])
    return df.reset_index(drop=True)


def bulk_open_interest(root: str, exp: int | str | date, start_date: date | str | int,
                       end_date: date | str | int) -> pd.DataFrame | None:
    """Open interest for all contracts of a given root+expiry over a date range.

    AMBIGUITY NOTE: The v2 docs expose /v2/hist/option/open_interest as a per-contract
    endpoint (requires exp, strike, right).  A true bulk OI endpoint (parallel to
    bulk_hist/option/eod) is not confirmed in the public v2 docs as of 2026-07-04.
    This method calls the per-contract endpoint via the hist path, iterating contracts
    discovered from bulk_eod.  Verify at probe time whether a bulk OI endpoint exists.

    OI update timing: OPRA reports OI once per day at ~06:30 ET; the value represents
    end-of-PREVIOUS-day positions.  Do not use same-day OI in any day-t signal (use OI[t-1]).

    Response tick fields: [ms_of_day, open_interest, date]

    Returns DataFrame: root, expiration, strike, right, date, open_interest
    or None if terminal is unreachable.
    """
    if not reachable():
        log.warning("thetadata: terminal not reachable — bulk_open_interest returning None")
        return None
    # First get the contract list from EOD (which always has bulk support)
    eod = bulk_eod(root, exp, start_date, end_date)
    if eod is None:
        return None
    if eod.empty:
        return pd.DataFrame()
    # Unique contracts from the EOD pull
    contracts = (eod[["root", "expiration", "strike", "right"]]
                 .drop_duplicates()
                 .to_dict("records"))
    session = _session()
    rows_all: list[dict] = []
    for c in contracts:
        exp_int = int(c["expiration"].strftime("%Y%m%d")) if pd.notna(c["expiration"]) else 0
        strike_int = int(round(c["strike"] * STRIKE_DIVISOR))
        params = {
            "root": c["root"],
            "exp": exp_int,
            "strike": strike_int,
            "right": c["right"],
            "start_date": _date_int(start_date),
            "end_date": _date_int(end_date),
            "use_csv": "false",
        }
        for page_rows in _paginate(session, "/v2/hist/option/open_interest", params):
            for tick in page_rows:
                if len(tick) < 3:
                    continue
                rows_all.append({
                    "root": c["root"],
                    "expiration": c["expiration"],
                    "strike": c["strike"],
                    "right": c["right"],
                    "date": _to_date(tick[2]),
                    "open_interest": tick[1],
                })
    if not rows_all:
        return pd.DataFrame()
    df = pd.DataFrame(rows_all)
    df["date"] = pd.to_datetime(df["date"])
    df["expiration"] = pd.to_datetime(df["expiration"])
    return df.reset_index(drop=True)


def bulk_greeks(root: str, exp: int | str | date, start_date: date | str | int,
                end_date: date | str | int, *, order: int = 1) -> pd.DataFrame | None:
    """Greeks (and implied volatility) for all contracts of a given root+expiry.

    order=1 → /v2/bulk_hist/option/greeks
      Response tick fields: [ms_of_day, bid, ask, delta, theta, vega, rho, epsilon, lambda,
                              implied_vol, iv_error, ms_of_day2, underlying_price, date]
      implied_vol is included in this response; no separate IV endpoint needed for EOD use.

    order=2 → /v2/bulk_hist/option/second_order_greeks
    order=3 → /v2/bulk_hist/option/third_order_greeks
      (Exact field layout for orders 2/3 to be confirmed at probe time; stored as raw_fields.)

    Returns DataFrame: root, expiration, strike, right, date, and Greek columns.
    For order=1: delta, theta, vega, rho, epsilon, lambda, implied_vol, underlying_price.
    For order=2/3: raw_fields list (to be formalized after entitlement probe).

    None if terminal is unreachable / not entitled.
    """
    if order not in _GREEKS_ENDPOINTS:
        raise ValueError(f"order must be 1, 2, or 3; got {order}")
    if not reachable():
        log.warning("thetadata: terminal not reachable — bulk_greeks(order=%d) returning None", order)
        return None
    path = f"/v2/bulk_hist/option/{_GREEKS_ENDPOINTS[order]}"
    params = {
        "root": root.upper(),
        "exp": _date_int(exp) if exp != 0 else 0,
        "start_date": _date_int(start_date),
        "end_date": _date_int(end_date),
        "use_csv": "false",
    }
    session = _session()
    rows_all: list[dict] = []
    for page_rows in _paginate(session, path, params):
        for contract_obj in page_rows:
            contract = contract_obj.get("contract", {})
            root_val = contract.get("root", root)
            exp_val = _to_date(contract.get("expiration"))
            strike_val = (contract.get("strike") or 0) / STRIKE_DIVISOR
            right_val = contract.get("right")
            for tick in (contract_obj.get("ticks") or []):
                if order == 1:
                    if len(tick) < 14:
                        continue
                    rows_all.append({
                        "root": root_val,
                        "expiration": exp_val,
                        "strike": strike_val,
                        "right": right_val,
                        "date": _to_date(tick[13]),
                        "bid": tick[1],
                        "ask": tick[2],
                        "delta": tick[3],
                        "theta": tick[4],
                        "vega": tick[5],
                        "rho": tick[6],
                        "epsilon": tick[7],
                        "lambda_": tick[8],    # 'lambda' is a Python reserved word
                        "implied_vol": tick[9],
                        "iv_error": tick[10],
                        "underlying_price": tick[12],
                    })
                else:
                    # order 2/3: field layout TBD — store raw for now; formalize after probe
                    rows_all.append({
                        "root": root_val,
                        "expiration": exp_val,
                        "strike": strike_val,
                        "right": right_val,
                        "date": _to_date(tick[-1]) if tick else None,
                        "raw_fields": tick,
                    })
    if not rows_all:
        return pd.DataFrame()
    df = pd.DataFrame(rows_all)
    df["date"] = pd.to_datetime(df["date"])
    df["expiration"] = pd.to_datetime(df["expiration"])
    return df.reset_index(drop=True)


def trade_quote(root: str, exp: int | str | date, right: str, strike: float,
                start_date: date | str | int, end_date: date | str | int) -> pd.DataFrame | None:
    """Every trade paired with the prevailing NBBO at execution, for ONE specific contract.

    Endpoint: GET /v2/hist/option/trade_quote
    Required params: root, exp (YYYYMMDD), strike (1/10th-cent int), right (C/P),
                     start_date, end_date.

    Response tick fields (from docs):
      [ms_of_day, sequence, ext_condition1, ext_condition2, ext_condition3, ext_condition4,
       condition, size, exchange, price, condition_flags, price_flags, volume_type,
       records_back, ms_of_day2, bid_size, bid_exchange, bid, bid_condition,
       ask_size, ask_exchange, ask, ask_condition, date]

    This is the gold-standard source for quote-rule signing calibration (F7 re-test):
    every trade is stamped with the NBBO at execution, enabling Lee-Ready signing.

    Returns DataFrame: date, ts_ms, price, size, bid, ask, right, strike, exchange
    or None if terminal is unreachable.
    """
    if not reachable():
        log.warning("thetadata: terminal not reachable — trade_quote returning None")
        return None
    strike_int = int(round(float(strike) * STRIKE_DIVISOR))
    params = {
        "root": root.upper(),
        "exp": _date_int(exp),
        "strike": strike_int,
        "right": right.upper(),
        "start_date": _date_int(start_date),
        "end_date": _date_int(end_date),
        "use_csv": "false",
    }
    session = _session()
    rows_all: list[dict] = []
    for page_rows in _paginate(session, "/v2/hist/option/trade_quote", params):
        for tick in page_rows:
            if len(tick) < 24:
                continue
            rows_all.append({
                "date": _to_date(tick[23]),
                "ts_ms": tick[0],           # ms since midnight ET
                "price": tick[9],
                "size": tick[7],
                "bid": tick[17],
                "ask": tick[21],
                "exchange": tick[8],
                "condition_flags": tick[10],
            })
    if not rows_all:
        return pd.DataFrame()
    df = pd.DataFrame(rows_all)
    df["date"] = pd.to_datetime(df["date"])
    df["strike"] = float(strike)
    df["right"] = right.upper()
    df["root"] = root.upper()
    return df.reset_index(drop=True)
